"""
app/main.py
-----------
FastAPI application factory for MotherSource AI — Service 1.
Configures the app, middleware, and includes the versioned API router.
"""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from modules.routes import router as channels_router
from modules.outreach_routes import router as outreach_router
from modules.partner_routes import partner_router

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------
def create_app() -> FastAPI:
    """Instantiate and configure the FastAPI application."""
    application = FastAPI(
        title="MotherSource AI — Services 1, 2 & 3",
        description=(
            "Service 1: Mother Onboarding Finder | "
            "Service 2: Funding & Partnership Scout | "
            "Service 3: Smart Outreach Generator"
        ),
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # ── CORS (adjust origins before going to production) ──────────────────
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Routers ───────────────────────────────────────────────────────────
    application.include_router(channels_router, prefix="/api/v1")
    application.include_router(outreach_router, prefix="/api/v1")
    application.include_router(partner_router, prefix="/api/v1")


    @application.get("/health", tags=["Health"])
    async def health_check() -> dict[str, str]:
        """Liveness probe — returns OK if the process is running."""
        return {"status": "ok", "service": "mother-onboarding-finder"}

    logger.info("MotherSource AI Service 1 initialised.")
    return application


app = create_app()
