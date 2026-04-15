from app.core.time import utc_now
import asyncio
import logging
import secrets
import time
from typing import Any

from fastapi import FastAPI, Depends, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging_config import (
    setup_logging,
    correlation_id,
    generate_correlation_id,
    log_event,
)
from app.core.metrics import (
    app_info,
    http_requests_total,
    http_request_duration_seconds,
)
from app.db.schema_contracts import SchemaContractMismatchError
from app.db.session import (
    get_db,
    get_db_context,
    check_db_connection,
    init_db,
    try_advisory_lock,
)
from app.services.ops.production_readiness_service import ProductionReadinessService
from app.services.ops.run_metadata_service import OperationalRunRecorder
from app.startup_runtime import (
    launch_bfarm_startup_import_thread,
    safe_record_startup_readiness_once,
)
from app.api.deps import get_current_user, get_optional_current_user

# Setup structured logging BEFORE anything else
settings = get_settings()
setup_logging(
    level=settings.LOG_LEVEL,
    json_format=settings.LOG_FORMAT == "json",
    service_name="viralflux-api",
    environment=settings.ENVIRONMENT,
    app_version=settings.APP_VERSION,
)
logger = logging.getLogger(__name__)

_STARTUP_READINESS_LOCK = "startup:readiness:record"
_STARTUP_BFARM_IMPORT_LOCK = "startup:bfarm:import"


def _api_surface_urls(settings_obj: Any | None = None) -> dict[str, str | None]:
    active_settings = settings_obj or settings
    if getattr(active_settings, "EFFECTIVE_API_DOCS_ENABLED", False):
        return {
            "docs_url": "/docs",
            "redoc_url": "/redoc",
            "openapi_url": "/openapi.json",
        }
    return {
        "docs_url": None,
        "redoc_url": None,
        "openapi_url": None,
    }


def _dedupe_public_strings(values: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        deduped.append(text)
        seen.add(text)
    return deduped


def _public_blocker_reasons(snapshot: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    for blocker in list(snapshot.get("blockers") or []):
        if isinstance(blocker, dict):
            component = str(blocker.get("component") or "").strip()
            message = str(blocker.get("message") or "").strip()
            if component and message:
                reasons.append(f"{component}: {message}")
            elif message:
                reasons.append(message)
            elif component:
                reasons.append(component)
            continue
        text = str(blocker or "").strip()
        if text:
            reasons.append(text)
    return _dedupe_public_strings(reasons)


def _public_scope_warning_reason(item: dict[str, Any]) -> str | None:
    scope = str(item.get("virus_typ") or "").strip() or "Unknown scope"
    horizon = item.get("horizon_days")
    if horizon is not None:
        scope = f"{scope} h{horizon}"

    for collection_name in ("blockers", "core_scope_advisories", "live_source_advisories"):
        collection = item.get(collection_name) or []
        for reason in collection:
            text = str(reason or "").strip()
            if text:
                return f"{scope}: {text}"

    quality_gate = item.get("quality_gate") or {}
    quality_readiness = str(quality_gate.get("forecast_readiness") or "").strip().upper()
    if quality_readiness and quality_readiness != "GO":
        return f"{scope}: forecast readiness {quality_readiness}."

    status = str(item.get("status") or "").strip().lower()
    if status:
        return f"{scope}: status {status}."
    return None


def _public_forecast_monitoring_reason(item: dict[str, Any]) -> str | None:
    virus_typ = str(item.get("virus_typ") or "").strip() or "Unknown forecast"
    reasons: list[str] = []

    forecast_readiness = str(item.get("forecast_readiness") or "").strip().upper()
    if forecast_readiness and forecast_readiness != "GO":
        reasons.append(f"forecast readiness {forecast_readiness}")

    for field_name, label in (
        ("freshness_status", "freshness"),
        ("accuracy_freshness_status", "accuracy freshness"),
        ("backtest_freshness_status", "backtest freshness"),
    ):
        value = str(item.get(field_name) or "").strip().lower()
        if value and value not in {"ok", "fresh"}:
            reasons.append(f"{label} {value}")

    if not reasons:
        status = str(item.get("status") or "").strip().lower()
        if not status:
            return None
        reasons.append(f"status {status}")

    return f"{virus_typ}: {'; '.join(reasons)}."


def _public_warning_reasons(snapshot: dict[str, Any]) -> tuple[int, list[str]]:
    explicit_warnings = _dedupe_public_strings(
        [str(warning or "").strip() for warning in list(snapshot.get("warnings") or [])]
    )
    if explicit_warnings:
        return len(explicit_warnings), explicit_warnings

    components = snapshot.get("components") or {}
    warning_components = [
        (name, component)
        for name, component in components.items()
        if str((component or {}).get("status") or "").strip().lower() in {"warning", "unknown"}
    ]

    reasons: list[str] = []
    for name, component in warning_components:
        if name in {"regional_operational", "core_regional_operational"}:
            for item in list(component.get("matrix") or []):
                item_status = str(item.get("status") or "").strip().lower()
                if item_status not in {"warning", "unknown", "critical"}:
                    continue
                reason = _public_scope_warning_reason(item)
                if reason:
                    reasons.append(reason)
            continue

        if name == "forecast_monitoring":
            for item in list(component.get("items") or []):
                item_status = str(item.get("status") or "").strip().lower()
                if item_status not in {"warning", "unknown", "critical"}:
                    continue
                reason = _public_forecast_monitoring_reason(item)
                if reason:
                    reasons.append(reason)
            continue

        message = str(component.get("message") or "").strip()
        if message:
            reasons.append(f"{name}: {message}")

    return len(warning_components), _dedupe_public_strings(reasons)


def _public_readiness_payload(
    snapshot: dict[str, Any],
    *,
    settings_obj: Any | None = None,
    expose_details: bool | None = None,
) -> dict[str, Any]:
    active_settings = settings_obj or settings
    should_expose_details = (
        getattr(active_settings, "EFFECTIVE_PUBLIC_HEALTH_DETAILS_ENABLED", False)
        if expose_details is None
        else expose_details
    )
    if should_expose_details:
        return snapshot

    blocker_reasons = _public_blocker_reasons(snapshot)
    warning_count, warning_reasons = _public_warning_reasons(snapshot)
    status_reasons = blocker_reasons + warning_reasons
    payload = {
        "status": snapshot.get("status"),
        "checked_at": snapshot.get("checked_at"),
        "app_version": getattr(active_settings, "APP_VERSION", None),
        "blocker_count": len(blocker_reasons),
        "warning_count": warning_count,
    }
    if status_reasons:
        payload["status_reasons"] = status_reasons[:3]
        if len(status_reasons) > 3:
            payload["remaining_reason_count"] = len(status_reasons) - 3
    environment = str(getattr(active_settings, "ENVIRONMENT", "") or "").strip()
    if environment and environment != "production":
        payload["environment"] = environment
    return payload


def _extract_metrics_token(request: Request) -> str:
    header_token = str(request.headers.get("X-Metrics-Token") or "").strip()
    if header_token:
        return header_token
    auth_header = str(request.headers.get("Authorization") or "").strip()
    if auth_header.lower().startswith("bearer "):
        return auth_header[7:].strip()
    return ""


def _enforce_metrics_access(
    *,
    request: Request,
    current_user: dict | None,
    settings_obj: Any | None = None,
) -> None:
    active_settings = settings_obj or settings
    if getattr(active_settings, "EFFECTIVE_PUBLIC_METRICS_ENABLED", False):
        return
    if current_user and current_user.get("role") == "admin":
        return

    configured_token = str(getattr(active_settings, "METRICS_AUTH_TOKEN", "") or "").strip()
    provided_token = _extract_metrics_token(request)
    if configured_token and provided_token and secrets.compare_digest(provided_token, configured_token):
        return

    raise HTTPException(status_code=404, detail="Not found")


# FastAPI App
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Behördlich getriebene Media-Intelligence für Pharma-Marken mit 14-Tage-Frühsignal",
    **_api_surface_urls(settings),
)

# Publish app info to Prometheus
app_info.info({
    "version": settings.APP_VERSION,
    "environment": settings.ENVIRONMENT,
})

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Standardized Error Handlers ─────────────────────────────────
from fastapi.exceptions import RequestValidationError

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    cid = correlation_id.get("")
    return JSONResponse(
        status_code=422,
        content={
            "error": "validation_error",
            "detail": "Ungültige Eingabedaten",
            "fields": [
                {"field": ".".join(str(x) for x in e["loc"]), "message": e["msg"]}
                for e in exc.errors()
            ],
            "correlation_id": cid or None,
        },
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    cid = correlation_id.get("")
    log_event(
        logger,
        "unhandled_exception",
        level=logging.ERROR,
        path=str(request.url.path),
        method=request.method,
        correlation_id=cid or None,
        error_type=type(exc).__name__,
        error_message=str(exc),
    )
    return JSONResponse(
        status_code=500,
        content={
            "error": "internal_error",
            "detail": "Ein interner Fehler ist aufgetreten.",
            "correlation_id": cid or None,
        },
    )


@app.exception_handler(SchemaContractMismatchError)
async def schema_contract_exception_handler(request: Request, exc: SchemaContractMismatchError):
    cid = correlation_id.get("")
    log_event(
        logger,
        "schema_contract_mismatch",
        level=logging.ERROR,
        path=str(request.url.path),
        method=request.method,
        correlation_id=cid or None,
        error_type=type(exc).__name__,
        error_message=str(exc),
    )
    return JSONResponse(
        status_code=503,
        content={
            "error": "schema_mismatch",
            "detail": str(exc),
            "correlation_id": cid or None,
        },
    )


# ── Middleware: Correlation ID + Prometheus Metrics ──────────────
@app.middleware("http")
async def observability_middleware(request: Request, call_next) -> Response:
    cid = request.headers.get("X-Correlation-ID") or generate_correlation_id()
    token = correlation_id.set(cid)

    start = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        duration = time.perf_counter() - start
        endpoint = request.url.path
        http_requests_total.labels(request.method, endpoint, "500").inc()
        http_request_duration_seconds.labels(request.method, endpoint).observe(duration)
        log_event(
            logger,
            "http_request_failed",
            level=logging.ERROR,
            method=request.method,
            path=endpoint,
            duration_ms=round(duration * 1000.0, 2),
            correlation_id=cid,
        )
        correlation_id.reset(token)
        raise

    duration = time.perf_counter() - start
    endpoint = request.url.path
    http_requests_total.labels(request.method, endpoint, str(response.status_code)).inc()
    http_request_duration_seconds.labels(request.method, endpoint).observe(duration)

    response.headers["X-Correlation-ID"] = cid
    if endpoint not in {"/health/live", "/metrics"}:
        log_event(
            logger,
            "http_request_completed",
            level=logging.INFO,
            method=request.method,
            path=endpoint,
            status_code=response.status_code,
            duration_ms=round(duration * 1000.0, 2),
            correlation_id=cid,
        )
    correlation_id.reset(token)
    return response


@app.on_event("startup")
async def startup_event():
    """Initialize database on startup."""
    log_event(
        logger,
        "startup_begin",
        app_name=settings.APP_NAME,
        app_version=settings.APP_VERSION,
        environment=settings.ENVIRONMENT,
        strict_startup_readiness=settings.EFFECTIVE_STARTUP_STRICT_READINESS,
        startup_enable_bfarm_import=settings.STARTUP_ENABLE_BFARM_IMPORT,
    )
    
    # Startup should verify critical dependencies first instead of silently
    # mutating the schema behind the operator's back.
    db_healthy = await check_db_connection()
    if not db_healthy:
        log_event(
            logger,
            "startup_database_unavailable",
            level=logging.ERROR,
            environment=settings.ENVIRONMENT,
        )
        raise RuntimeError("Database connection check failed on startup.")
    log_event(logger, "startup_database_verified")

    db_summary = init_db()
    app.state.startup_db_summary = db_summary
    log_event(
        logger,
        "startup_database_schema_verified",
        schema_status=db_summary.get("status"),
        warnings=db_summary.get("warnings") or [],
        actions=db_summary.get("actions") or [],
    )

    readiness_snapshot = ProductionReadinessService().build_snapshot(deep_checks=False)
    app.state.startup_readiness = readiness_snapshot
    app.state.startup_completed_at = utc_now().isoformat()
    app.state.startup_run_metadata = safe_record_startup_readiness_once(
        readiness_snapshot=readiness_snapshot,
        record_once=_record_startup_readiness_once,
        settings_obj=settings,
        logger_obj=logger,
        log_event_fn=log_event,
    )

    log_event(
        logger,
        "startup_readiness_completed",
        readiness_status=readiness_snapshot.get("status"),
        blockers=readiness_snapshot.get("blockers") or [],
    )
    if settings.EFFECTIVE_STARTUP_STRICT_READINESS and readiness_snapshot.get("status") == "unhealthy":
        raise RuntimeError("Startup readiness is unhealthy. See /health/ready for blockers.")

    if settings.STARTUP_ENABLE_BFARM_IMPORT:
        log_event(
            logger,
            "startup_bfarm_import_enabled",
            level=logging.WARNING,
            mode="explicit_opt_in",
            note="Running BfArM startup import because STARTUP_ENABLE_BFARM_IMPORT=true.",
        )
        _launch_bfarm_startup_import_thread()
    else:
        log_event(
            logger,
            "startup_bfarm_import_disabled",
            mode="default_safe",
            note=(
                "Skipping hidden BfArM startup import. Set STARTUP_ENABLE_BFARM_IMPORT=true "
                "only for explicit local special cases."
            ),
        )


def _startup_skip_metadata(*, action: str, summary: str, lock_name: str) -> dict[str, Any]:
    return {
        "run_id": None,
        "action": action,
        "status": "skipped",
        "summary": summary,
        "timestamp": utc_now().isoformat(),
        "environment": settings.ENVIRONMENT,
        "app_version": settings.APP_VERSION,
        "metadata": {
            "lock_name": lock_name,
            "persisted": False,
            "singleton": True,
        },
    }


def _record_startup_readiness_once(readiness_snapshot: dict[str, Any]) -> dict[str, Any]:
    try:
        with try_advisory_lock(_STARTUP_READINESS_LOCK) as acquired:
            if not acquired:
                summary = (
                    "Startup readiness snapshot skipped on this worker because "
                    "another worker already owns the singleton startup section."
                )
                log_event(
                    logger,
                    "startup_singleton_section_skipped",
                    section="startup_readiness_record",
                    lock_name=_STARTUP_READINESS_LOCK,
                )
                return _startup_skip_metadata(
                    action="STARTUP_READINESS",
                    summary=summary,
                    lock_name=_STARTUP_READINESS_LOCK,
                )

            log_event(
                logger,
                "startup_singleton_section_started",
                section="startup_readiness_record",
                lock_name=_STARTUP_READINESS_LOCK,
            )
            with get_db_context() as db:
                run_metadata = OperationalRunRecorder(db).record_event(
                    action="STARTUP_READINESS",
                    status=readiness_snapshot["status"],
                    summary="Startup readiness snapshot recorded.",
                    metadata={
                        "components": readiness_snapshot.get("components"),
                        "blockers": readiness_snapshot.get("blockers"),
                        "checked_at": readiness_snapshot.get("checked_at"),
                    },
                )
            log_event(
                logger,
                "startup_singleton_section_completed",
                section="startup_readiness_record",
                lock_name=_STARTUP_READINESS_LOCK,
                run_id=run_metadata.get("run_id"),
                readiness_status=run_metadata.get("status"),
            )
            return run_metadata
    except Exception as exc:
        log_event(
            logger,
            "startup_singleton_section_failed",
            level=logging.ERROR,
            section="startup_readiness_record",
            lock_name=_STARTUP_READINESS_LOCK,
            error_message=str(exc),
        )
        raise


def _run_bfarm_startup_import_once() -> None:
    try:
        with try_advisory_lock(_STARTUP_BFARM_IMPORT_LOCK) as acquired:
            if not acquired:
                log_event(
                    logger,
                    "startup_singleton_section_skipped",
                    section="startup_bfarm_import",
                    lock_name=_STARTUP_BFARM_IMPORT_LOCK,
                )
                return

            log_event(
                logger,
                "startup_singleton_section_started",
                section="startup_bfarm_import",
                lock_name=_STARTUP_BFARM_IMPORT_LOCK,
            )
            from app.services.data_ingest.bfarm_service import BfarmIngestionService

            result = BfarmIngestionService().run_full_import()
            log_event(
                logger,
                "startup_bfarm_pull_completed",
                singleton=True,
                relevant_records=result.get("relevant_records", 0),
                risk_score=result.get("risk_score", 0),
            )
    except Exception as exc:
        log_event(
            logger,
            "startup_bfarm_pull_failed",
            level=logging.WARNING,
            singleton=True,
            error_message=str(exc),
        )


def _launch_bfarm_startup_import_thread() -> None:
    launch_bfarm_startup_import_thread(target=_run_bfarm_startup_import_once)


@app.on_event("shutdown")
async def shutdown_event():
    """Graceful shutdown: allow in-flight requests to complete."""
    log_event(logger, "shutdown_begin")
    await asyncio.sleep(2)
    log_event(logger, "shutdown_complete")


@app.get("/")
async def root():
    """Root endpoint with API info."""
    payload = {
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
        "health_live": "/health/live",
        "health_ready": "/health/ready",
        "health_core_ready": "/health/core-ready",
        "status": "operational",
    }
    if settings.EFFECTIVE_API_DOCS_ENABLED:
        payload["docs"] = "/docs"
    return payload


def _readiness_payload() -> dict:
    snapshot = ProductionReadinessService().build_snapshot()
    snapshot["startup"] = {
        "completed_at": getattr(app.state, "startup_completed_at", None),
        "db_summary": getattr(app.state, "startup_db_summary", None),
        "run_metadata": getattr(app.state, "startup_run_metadata", None),
    }
    return snapshot


def _core_readiness_payload() -> dict:
    snapshot = ProductionReadinessService().build_core_snapshot()
    snapshot["startup"] = {
        "completed_at": getattr(app.state, "startup_completed_at", None),
        "db_summary": getattr(app.state, "startup_db_summary", None),
        "run_metadata": getattr(app.state, "startup_run_metadata", None),
    }
    return snapshot


@app.get("/health/live")
async def health_live():
    """Liveness probe: process is running and can answer requests."""
    return {
        "status": "alive",
        "checked_at": utc_now().isoformat(),
        "app_version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
    }


@app.get("/health/ready")
async def health_ready():
    """Readiness probe with dependency, artifact and recency checks."""
    snapshot = _readiness_payload()
    return JSONResponse(
        status_code=ProductionReadinessService.http_status_code(snapshot),
        content=_public_readiness_payload(snapshot),
    )


@app.get("/health/core-ready")
async def health_core_ready():
    """Core production readiness for explicitly supported live scopes."""
    snapshot = _core_readiness_payload()
    return JSONResponse(
        status_code=ProductionReadinessService.http_status_code(snapshot),
        content=_public_readiness_payload(snapshot),
    )


@app.get("/health/ready/internal", dependencies=[Depends(get_current_user)])
async def health_ready_internal():
    """Detailed readiness payload for authenticated operators."""
    snapshot = _readiness_payload()
    return JSONResponse(
        status_code=ProductionReadinessService.http_status_code(snapshot),
        content=snapshot,
    )


@app.get("/health/core-ready/internal", dependencies=[Depends(get_current_user)])
async def health_core_ready_internal():
    """Detailed core readiness payload for authenticated operators."""
    snapshot = _core_readiness_payload()
    return JSONResponse(
        status_code=ProductionReadinessService.http_status_code(snapshot),
        content=snapshot,
    )


@app.get("/health")
async def health_check():
    """Backward-compatible detailed health endpoint."""
    return await health_ready()


@app.get("/metrics")
async def prometheus_metrics(
    request: Request,
    current_user: dict | None = Depends(get_optional_current_user),
):
    """Prometheus metrics endpoint."""
    _enforce_metrics_access(request=request, current_user=current_user)
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )


@app.get("/api/v1/status", dependencies=[Depends(get_current_user)])
async def get_status(db: Session = Depends(get_db)):
    """Get system status and data freshness."""
    from app.models.database import (
        WastewaterAggregated,
        GoogleTrendsData,
        MLForecast,
        NotaufnahmeSyndromData,
        SurvstatWeeklyData,
        SurvstatKreisData,
    )

    # Check latest data timestamps
    latest_wastewater = db.query(WastewaterAggregated).order_by(
        WastewaterAggregated.created_at.desc()
    ).first()

    latest_trends = db.query(GoogleTrendsData).order_by(
        GoogleTrendsData.created_at.desc()
    ).first()

    latest_forecast = db.query(MLForecast).order_by(
        MLForecast.created_at.desc()
    ).first()

    latest_notaufnahme = db.query(NotaufnahmeSyndromData).order_by(
        NotaufnahmeSyndromData.created_at.desc()
    ).first()

    latest_survstat = db.query(SurvstatWeeklyData).order_by(
        SurvstatWeeklyData.created_at.desc()
    ).first()

    latest_survstat_kreis = db.query(SurvstatKreisData).order_by(
        SurvstatKreisData.created_at.desc()
    ).first()

    return {
        "status": "operational",
        "data_freshness": {
            "wastewater": latest_wastewater.created_at if latest_wastewater else None,
            "google_trends": latest_trends.created_at if latest_trends else None,
            "ml_forecast": latest_forecast.created_at if latest_forecast else None,
            "notaufnahme": latest_notaufnahme.created_at if latest_notaufnahme else None,
            "survstat": latest_survstat.created_at if latest_survstat else None,
            "survstat_kreis": latest_survstat_kreis.created_at if latest_survstat_kreis else None,
        },
        "timestamp": utc_now()
    }


# Rate Limiting (slowapi) — shared limiter from core module
from app.core.rate_limit import limiter

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Import API routes
from app.api import (
    auth,
    dashboard,
    ingest,
    forecast,
    recommendations,
    inventory,
    map_data,
    ordering,
    drug_shortage,
    outbreak_score,
    marketing,
    data_import,
    webhooks,
    public_api,
    calibration,
    media,
    backtest,
    admin_ml,
)
app.include_router(auth.router, prefix="/api/auth", tags=["Auth"])
app.include_router(dashboard.router, prefix="/api/v1/dashboard", tags=["Dashboard"])
app.include_router(ingest.router, prefix="/api/v1/ingest", tags=["Data Ingestion"])
app.include_router(forecast.router, prefix="/api/v1/forecast", tags=["ML Forecast"])
app.include_router(recommendations.router, prefix="/api/v1/recommendations", tags=["Recommendations"])
app.include_router(inventory.router, prefix="/api/v1/inventory", tags=["Inventory"])
app.include_router(map_data.router, prefix="/api/v1/map", tags=["Map Data"])
app.include_router(ordering.router, prefix="/api/v1/ordering", tags=["Ordering"])
app.include_router(drug_shortage.router, prefix="/api/v1/drug-shortage", tags=["Drug Shortage"])
app.include_router(outbreak_score.router, prefix="/api/v1/outbreak-score", tags=["Outbreak Score"])
app.include_router(marketing.router, prefix="/api/v1/marketing", tags=["Marketing"])
app.include_router(media.router, prefix="/api/v1/media", tags=["Media"])
app.include_router(data_import.router, prefix="/api/v1/data-import", tags=["Data Import"])
app.include_router(webhooks.router)
app.include_router(public_api.router, prefix="/api/v1/public", tags=["Public API"])
app.include_router(calibration.router, prefix="/api/v1/calibration", tags=["Calibration"])
app.include_router(backtest.router, prefix="/api/v1/backtest", tags=["Backtest"])
app.include_router(admin_ml.router, prefix="/api/v1/admin/ml", tags=["Admin ML"])


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )
