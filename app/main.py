"""
FastAPI application factory.

Creates and configures the No Wrong Door unified API.
"""

from fastapi import FastAPI

from app.api.routes import router


def create_app() -> FastAPI:
    """Build and return the FastAPI application instance."""
    application = FastAPI(
        title="No Wrong Door — Unified Resident API",
        description=(
            "Aggregates the Calder County Resident Index and Benefits Register "
            "into a single, resilient API."
        ),
        version="0.1.0",
    )
    application.include_router(router)
    return application


app = create_app()
