from app.core.time import utc_now
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timedelta
from pydantic import BaseModel
from typing import Optional, List
import csv
import io
import json
import logging

from app.db.session import get_db
from app.models.database import InventoryLevel, MLForecast, WastewaterAggregated
from app.api.deps import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(dependencies=[Depends(get_current_user)])

VIRUS_TEST_MAP = {
    'Influenza A': 'Influenza A/B Schnelltest',
    'Influenza B': 'Influenza A/B Schnelltest',
    'SARS-CoV-2': 'SARS-CoV-2 PCR',
    'RSV A': 'RSV Schnelltest',
}

# Average daily consumption rates per test type (estimated)
BASE_CONSUMPTION = {
    'Influenza A/B Schnelltest': 35,
    'SARS-CoV-2 PCR': 25,
    'RSV Schnelltest': 15,
    'Multiplex PCR Panel': 10,
    'Adenovirus Schnelltest': 8,
}


def simulate_stockout(
    current_stock: int,
    daily_consumption: float,
    lead_time_days: int,
    forecast_trend: float = 1.0,
) -> dict:
    """Simulate when a stockout would occur and calculate reorder point.

    Args:
        current_stock: Current inventory level
        daily_consumption: Estimated daily usage rate
        lead_time_days: Days until delivery after ordering
        forecast_trend: Multiplier from ML forecast (>1 = rising demand)

    Returns:
        Dict with stockout risk analysis
    """
    adjusted_consumption = daily_consumption * forecast_trend
    safety_stock = adjusted_consumption * lead_time_days * 0.5  # 50% safety buffer

    days_until_stockout = current_stock / adjusted_consumption if adjusted_consumption > 0 else 999
    reorder_point = (adjusted_consumption * lead_time_days) + safety_stock
    needs_reorder = current_stock <= reorder_point

    # Optimal order quantity (Economic Order Quantity simplified)
    target_days = 30  # Target 30 days of stock
    optimal_quantity = max(0, int((adjusted_consumption * target_days) - current_stock + safety_stock))

    # Risk level
    if days_until_stockout <= lead_time_days:
        risk = "critical"
    elif days_until_stockout <= lead_time_days * 2:
        risk = "high"
    elif needs_reorder:
        risk = "medium"
    else:
        risk = "low"

    return {
        "days_until_stockout": round(days_until_stockout, 1),
        "reorder_point": int(reorder_point),
        "needs_reorder": needs_reorder,
        "optimal_order_quantity": optimal_quantity,
        "safety_stock": int(safety_stock),
        "adjusted_daily_consumption": round(adjusted_consumption, 1),
        "risk_level": risk,
        "forecast_multiplier": round(forecast_trend, 2),
    }


def _get_forecast_trend(db: Session, virus_typ: str) -> float:
    """Calculate demand trend multiplier from ML forecast."""
    latest_run = db.query(MLForecast).filter(
        MLForecast.virus_typ == virus_typ
    ).order_by(MLForecast.created_at.desc()).first()

    if not latest_run:
        return 1.0

    forecasts = db.query(MLForecast).filter(
        MLForecast.virus_typ == virus_typ,
        MLForecast.created_at >= latest_run.created_at - timedelta(seconds=10)
    ).order_by(MLForecast.forecast_date.asc()).limit(14).all()

    if len(forecasts) < 2:
        return 1.0

    # Compare forecast end vs start
    start_val = forecasts[0].predicted_value
    end_val = forecasts[-1].predicted_value

    if start_val <= 0:
        return 1.0

    ratio = end_val / start_val
    # Clamp between 0.5 and 2.0
    return max(0.5, min(2.0, ratio))


@router.get("/stockout-analysis")
async def get_stockout_analysis(db: Session = Depends(get_db)):
    """Analyze all inventory items for stockout risk."""
    # Get latest inventory
    subq = db.query(
        InventoryLevel.test_typ,
        func.max(InventoryLevel.datum).label('max_datum')
    ).group_by(InventoryLevel.test_typ).subquery()

    latest_inv = db.query(InventoryLevel).join(
        subq,
        (InventoryLevel.test_typ == subq.c.test_typ) &
        (InventoryLevel.datum == subq.c.max_datum)
    ).all()

    analyses = []
    for inv in latest_inv:
        # Find virus type for this test
        virus_for_test = None
        for v, t in VIRUS_TEST_MAP.items():
            if t == inv.test_typ:
                virus_for_test = v
                break

        forecast_trend = _get_forecast_trend(db, virus_for_test) if virus_for_test else 1.0
        base_rate = BASE_CONSUMPTION.get(inv.test_typ, 15)

        analysis = simulate_stockout(
            current_stock=inv.aktueller_bestand,
            daily_consumption=base_rate,
            lead_time_days=inv.lieferzeit_tage or 5,
            forecast_trend=forecast_trend,
        )

        analyses.append({
            "test_typ": inv.test_typ,
            "current_stock": inv.aktueller_bestand,
            "min_stock": inv.min_bestand,
            "max_stock": inv.max_bestand,
            "lead_time_days": inv.lieferzeit_tage,
            **analysis,
        })

    # Sort by risk (critical first)
    risk_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    analyses.sort(key=lambda a: risk_order.get(a["risk_level"], 4))

    return {
        "analyses": analyses,
        "total_items": len(analyses),
        "items_needing_reorder": sum(1 for a in analyses if a["needs_reorder"]),
        "critical_items": sum(1 for a in analyses if a["risk_level"] == "critical"),
        "timestamp": utc_now().isoformat(),
    }


class OrderProposal(BaseModel):
    test_typ: str
    quantity: int
    priority: str = "normal"


@router.post("/generate-orders")
async def generate_order_proposals(db: Session = Depends(get_db)):
    """Generate order proposals for all items needing reorder."""
    # Reuse stockout analysis
    subq = db.query(
        InventoryLevel.test_typ,
        func.max(InventoryLevel.datum).label('max_datum')
    ).group_by(InventoryLevel.test_typ).subquery()

    latest_inv = db.query(InventoryLevel).join(
        subq,
        (InventoryLevel.test_typ == subq.c.test_typ) &
        (InventoryLevel.datum == subq.c.max_datum)
    ).all()

    orders = []
    for inv in latest_inv:
        virus_for_test = None
        for v, t in VIRUS_TEST_MAP.items():
            if t == inv.test_typ:
                virus_for_test = v
                break

        forecast_trend = _get_forecast_trend(db, virus_for_test) if virus_for_test else 1.0
        base_rate = BASE_CONSUMPTION.get(inv.test_typ, 15)

        analysis = simulate_stockout(
            current_stock=inv.aktueller_bestand,
            daily_consumption=base_rate,
            lead_time_days=inv.lieferzeit_tage or 5,
            forecast_trend=forecast_trend,
        )

        if analysis["needs_reorder"]:
            orders.append({
                "order_id": f"ORD-{utc_now().strftime('%Y%m%d')}-{inv.test_typ[:3].upper()}",
                "test_typ": inv.test_typ,
                "quantity": analysis["optimal_order_quantity"],
                "priority": "URGENT" if analysis["risk_level"] in ("critical", "high") else "NORMAL",
                "current_stock": inv.aktueller_bestand,
                "days_until_stockout": analysis["days_until_stockout"],
                "forecast_multiplier": analysis["forecast_multiplier"],
                "estimated_cost": round(analysis["optimal_order_quantity"] * _get_unit_price(inv.test_typ), 2),
                "supplier": _get_supplier(inv.test_typ),
                "created_at": utc_now().isoformat(),
            })

    return {
        "orders": orders,
        "total_orders": len(orders),
        "total_estimated_cost": round(sum(o["estimated_cost"] for o in orders), 2),
        "timestamp": utc_now().isoformat(),
    }


@router.get("/export-sap")
async def export_sap_orders(db: Session = Depends(get_db)):
    """Export order proposals as SAP/ERP-compatible CSV."""
    # Generate orders
    subq = db.query(
        InventoryLevel.test_typ,
        func.max(InventoryLevel.datum).label('max_datum')
    ).group_by(InventoryLevel.test_typ).subquery()

    latest_inv = db.query(InventoryLevel).join(
        subq,
        (InventoryLevel.test_typ == subq.c.test_typ) &
        (InventoryLevel.datum == subq.c.max_datum)
    ).all()

    output = io.StringIO()
    writer = csv.writer(output, delimiter=';')
    # SAP MM compatible header
    writer.writerow([
        'Bestellnummer', 'Material', 'Materialnummer', 'Menge', 'Mengeneinheit',
        'Prioritaet', 'Lieferant', 'Lieferantenummer', 'Preis_EUR', 'Werk',
        'Lagerort', 'Bestelldatum', 'Wunschlieferdatum', 'Bemerkung'
    ])

    order_num = 1
    for inv in latest_inv:
        virus_for_test = None
        for v, t in VIRUS_TEST_MAP.items():
            if t == inv.test_typ:
                virus_for_test = v
                break

        forecast_trend = _get_forecast_trend(db, virus_for_test) if virus_for_test else 1.0
        base_rate = BASE_CONSUMPTION.get(inv.test_typ, 15)
        analysis = simulate_stockout(
            current_stock=inv.aktueller_bestand,
            daily_consumption=base_rate,
            lead_time_days=inv.lieferzeit_tage or 5,
            forecast_trend=forecast_trend,
        )

        if analysis["needs_reorder"]:
            qty = analysis["optimal_order_quantity"]
            price = round(qty * _get_unit_price(inv.test_typ), 2)
            supplier = _get_supplier(inv.test_typ)
            delivery_date = (utc_now() + timedelta(days=inv.lieferzeit_tage or 5)).strftime('%Y-%m-%d')

            writer.writerow([
                f'LP-{utc_now().strftime("%Y%m%d")}-{order_num:03d}',
                inv.test_typ,
                _get_material_number(inv.test_typ),
                qty,
                'ST',  # Stueck
                'DRINGEND' if analysis["risk_level"] in ("critical", "high") else 'NORMAL',
                supplier["name"],
                supplier["number"],
                f'{price:.2f}',
                '1000',  # Werk
                'L001',  # Lagerort
                utc_now().strftime('%Y-%m-%d'),
                delivery_date,
                f'ML-Prognose: {analysis["forecast_multiplier"]:.1f}x Bedarf | Stockout in {analysis["days_until_stockout"]:.0f} Tagen',
            ])
            order_num += 1

    output.seek(0)
    return StreamingResponse(
        io.BytesIO(output.getvalue().encode('utf-8-sig')),
        media_type='text/csv',
        headers={'Content-Disposition': f'attachment; filename=ViralFlux_MediaPlan_{utc_now().strftime("%Y%m%d_%H%M")}.csv'}
    )


def _get_unit_price(test_typ: str) -> float:
    """Get estimated unit price for a test type."""
    prices = {
        'Influenza A/B Schnelltest': 4.50,
        'SARS-CoV-2 PCR': 12.80,
        'RSV Schnelltest': 6.20,
        'Multiplex PCR Panel': 28.50,
        'Adenovirus Schnelltest': 5.80,
    }
    return prices.get(test_typ, 10.0)


def _get_supplier(test_typ: str) -> dict:
    """Get supplier info for a test type."""
    suppliers = {
        'Influenza A/B Schnelltest': {"name": "Roche Diagnostics", "number": "V-10042"},
        'SARS-CoV-2 PCR': {"name": "Abbott Diagnostics", "number": "V-10089"},
        'RSV Schnelltest': {"name": "bioMerieux", "number": "V-10156"},
        'Multiplex PCR Panel': {"name": "Cepheid GmbH", "number": "V-10201"},
        'Adenovirus Schnelltest': {"name": "Meridian Bioscience", "number": "V-10178"},
    }
    return suppliers.get(test_typ, {"name": "Standard Diagnostics", "number": "V-99999"})


def _get_material_number(test_typ: str) -> str:
    """Get SAP material number for a test type."""
    numbers = {
        'Influenza A/B Schnelltest': 'MAT-DX-0142',
        'SARS-CoV-2 PCR': 'MAT-DX-0089',
        'RSV Schnelltest': 'MAT-DX-0156',
        'Multiplex PCR Panel': 'MAT-DX-0201',
        'Adenovirus Schnelltest': 'MAT-DX-0178',
    }
    return numbers.get(test_typ, 'MAT-DX-9999')
