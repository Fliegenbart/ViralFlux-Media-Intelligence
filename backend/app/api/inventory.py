from app.core.time import utc_now
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime
from pydantic import BaseModel
from typing import Optional
import logging

from app.api.deps import get_current_admin, get_current_user
from app.db.session import get_db
from app.models.database import InventoryLevel

logger = logging.getLogger(__name__)
router = APIRouter(dependencies=[Depends(get_current_user)])


class InventoryUpdate(BaseModel):
    test_typ: str
    aktueller_bestand: int
    min_bestand: Optional[int] = 100
    max_bestand: Optional[int] = 1000
    empfohlener_bestand: Optional[int] = None
    lieferzeit_tage: Optional[int] = 5


@router.get("/")
async def get_all_inventory(db: Session = Depends(get_db)):
    """Get all current inventory levels."""
    from sqlalchemy import func

    # Get the latest entry for each test type
    subq = db.query(
        InventoryLevel.test_typ,
        func.max(InventoryLevel.datum).label('max_datum')
    ).group_by(InventoryLevel.test_typ).subquery()

    latest = db.query(InventoryLevel).join(
        subq,
        (InventoryLevel.test_typ == subq.c.test_typ) &
        (InventoryLevel.datum == subq.c.max_datum)
    ).all()

    return {
        "inventory": [
            {
                "id": inv.id,
                "test_typ": inv.test_typ,
                "aktueller_bestand": inv.aktueller_bestand,
                "min_bestand": inv.min_bestand,
                "max_bestand": inv.max_bestand,
                "empfohlener_bestand": inv.empfohlener_bestand,
                "lieferzeit_tage": inv.lieferzeit_tage,
                "datum": inv.datum.isoformat(),
                "updated_at": inv.updated_at.isoformat() if inv.updated_at else None
            }
            for inv in latest
        ],
        "timestamp": utc_now()
    }


@router.post("/update", dependencies=[Depends(get_current_admin)])
async def update_inventory(
    item: InventoryUpdate,
    db: Session = Depends(get_db)
):
    """Create or update inventory for a test type."""
    inv = InventoryLevel(
        datum=utc_now(),
        test_typ=item.test_typ,
        aktueller_bestand=item.aktueller_bestand,
        min_bestand=item.min_bestand,
        max_bestand=item.max_bestand,
        empfohlener_bestand=item.empfohlener_bestand,
        lieferzeit_tage=item.lieferzeit_tage
    )
    db.add(inv)
    db.commit()

    return {
        "status": "updated",
        "test_typ": item.test_typ,
        "aktueller_bestand": item.aktueller_bestand,
        "timestamp": utc_now()
    }


@router.post("/seed", dependencies=[Depends(get_current_admin)])
async def seed_inventory(db: Session = Depends(get_db)):
    """Seed initial demo inventory data."""
    demo_data = [
        {"test_typ": "Influenza A/B Schnelltest", "aktueller_bestand": 2450, "min_bestand": 500, "max_bestand": 5000, "empfohlener_bestand": 2000, "lieferzeit_tage": 3},
        {"test_typ": "SARS-CoV-2 PCR", "aktueller_bestand": 1830, "min_bestand": 300, "max_bestand": 4000, "empfohlener_bestand": 1500, "lieferzeit_tage": 5},
        {"test_typ": "RSV Schnelltest", "aktueller_bestand": 890, "min_bestand": 200, "max_bestand": 2000, "empfohlener_bestand": 800, "lieferzeit_tage": 4},
        {"test_typ": "Multiplex PCR Panel", "aktueller_bestand": 620, "min_bestand": 150, "max_bestand": 1500, "empfohlener_bestand": 500, "lieferzeit_tage": 7},
        {"test_typ": "Adenovirus Schnelltest", "aktueller_bestand": 340, "min_bestand": 100, "max_bestand": 800, "empfohlener_bestand": 300, "lieferzeit_tage": 5},
    ]

    for item in demo_data:
        inv = InventoryLevel(datum=utc_now(), **item)
        db.add(inv)

    db.commit()
    return {"status": "seeded", "items": len(demo_data), "timestamp": utc_now()}


@router.get("/history/{test_typ}")
async def get_inventory_history(
    test_typ: str,
    db: Session = Depends(get_db)
):
    """Get inventory history for a test type."""
    history = db.query(InventoryLevel).filter(
        InventoryLevel.test_typ == test_typ
    ).order_by(InventoryLevel.datum.desc()).limit(90).all()

    return {
        "test_typ": test_typ,
        "history": [
            {
                "datum": h.datum.isoformat(),
                "aktueller_bestand": h.aktueller_bestand,
                "min_bestand": h.min_bestand,
                "empfohlener_bestand": h.empfohlener_bestand
            }
            for h in history
        ]
    }
