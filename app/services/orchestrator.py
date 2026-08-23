"""
Orchestration layer.
Calls upstream adapters concurrently, assembles the unified response,
and handles failure isolation and filtering.
"""
import asyncio
from typing import Tuple, Any, Optional

from app.adapters import resident_adapter, benefits_adapter
from app.models.models import (
    SourceStatus, SourceEnvelopes, 
    UnifiedSearchData, UnifiedSearchResponse, SearchQuery
)


def unpack_or_fail(result: Any, source_name: str) -> Tuple[Any, SourceStatus]:
    """
    Helper to unpack the result of an asyncio.gather task.
    If the result is an Exception, returns empty data and an unavailable SourceStatus.
    """
    if isinstance(result, Exception):
        return [], SourceStatus(
            status="unavailable",
            records_fetched=0,
            error=f"Unexpected internal error: {str(result)}",
            attempts=1
        )
    return result


async def search_residents(
    first_name: Optional[str] = None,
    last_name: Optional[str] = None,
    date_of_birth: Optional[str] = None
) -> UnifiedSearchResponse:
    """
    Unified search endpoint.
    Fetches all data from both systems, filters them independently,
    and returns matches side-by-side without falsely merging them.
    """
    results = await asyncio.gather(
        resident_adapter.fetch_all_residents(),
        benefits_adapter.fetch_all_benefits(),
        return_exceptions=True
    )
    
    resident_records, resident_status = unpack_or_fail(results[0], "resident_index")
    benefit_records, benefit_status = unpack_or_fail(results[1], "benefits_register")
    
    # Filter Resident Index
    filtered_residents = []
    for r in resident_records:
        match = True
        if first_name and first_name.lower() not in r.first_name.lower():
            match = False
        if last_name and last_name.lower() not in r.last_name.lower():
            match = False
        if date_of_birth and date_of_birth != r.date_of_birth:
            match = False
        if match:
            filtered_residents.append(r)

    # Filter Benefits Register
    # The XML format has Name as "LASTNAME, Firstname"
    filtered_benefits = []
    for b in benefit_records:
        match = True
        b_name_lower = b.name.lower()
        if first_name and first_name.lower() not in b_name_lower:
            match = False
        if last_name and last_name.lower() not in b_name_lower:
            match = False
        if date_of_birth and date_of_birth != b.born:
            match = False
        if match:
            filtered_benefits.append(b)

    return UnifiedSearchResponse(
        data=UnifiedSearchData(
            query=SearchQuery(
                first_name=first_name,
                last_name=last_name,
                date_of_birth=date_of_birth
            ),
            resident_index_matches=filtered_residents,
            benefits_register_matches=filtered_benefits
        ),
        sources=SourceEnvelopes(
            resident_index=resident_status,
            benefits_register=benefit_status
        )
    )
