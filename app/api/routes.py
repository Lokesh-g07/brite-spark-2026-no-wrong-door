"""
API route definitions.
"""
from fastapi import APIRouter, Query
from typing import Optional

from app.services import orchestrator
from app.models.models import UnifiedSearchResponse

router = APIRouter()

@router.get("/health")
async def health() -> dict:
    """Liveness probe for the unified API."""
    return {
        "status": "healthy",
        "service": "no-wrong-door",
    }

@router.get("/search", response_model=UnifiedSearchResponse)
async def search(
    first_name: Optional[str] = Query(None, description="Resident's first name"),
    last_name: Optional[str] = Query(None, description="Resident's last name"),
    date_of_birth: Optional[str] = Query(None, description="Resident's DOB (YYYY-MM-DD)")
):
    """
    Unified search returning matches from both the Resident Index and Benefits Register.
    Does not perform cross-system identity resolution.
    """
    return await orchestrator.search_residents(
        first_name=first_name, 
        last_name=last_name, 
        date_of_birth=date_of_birth
    )
