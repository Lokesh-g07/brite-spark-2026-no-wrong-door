"""
Resident Index adapter.
Handles pagination, deduplication by 'id', and returning canonical models.
"""
import httpx
from typing import List, Tuple

from app.config import REST_BASE_URL, REST_TIMEOUT
from app.models.models import Resident, SourceStatus


async def fetch_all_residents() -> Tuple[List[Resident], SourceStatus]:
    """
    Fetch all residents, traversing pages sequentially and deduplicating by 'id'.
    """
    seen_ids = set()
    output_list = []
    duplicates_removed = 0
    
    page = 1
    has_more = True
    
    try:
        async with httpx.AsyncClient(timeout=REST_TIMEOUT) as client:
            while has_more:
                resp = await client.get(f"{REST_BASE_URL}/residents", params={"page": page})
                
                # If we get a non-200, stop and treat as unavailable.
                if resp.status_code != 200:
                    error_msg = f"HTTP {resp.status_code}: {resp.text}"
                    return [], SourceStatus(
                        status="unavailable", 
                        records_fetched=0, 
                        error=error_msg
                    )
                
                data = resp.json()
                results = data.get("results", [])
                
                for r in results:
                    rid = r.get("id")
                    if rid not in seen_ids:
                        seen_ids.add(rid)
                        output_list.append(Resident(**r))
                    else:
                        duplicates_removed += 1
                        
                has_more = data.get("has_more", False)
                if has_more:
                    page += 1
                    
        return output_list, SourceStatus(
            status="ok",
            records_fetched=len(output_list) + duplicates_removed,
            duplicates_removed=duplicates_removed,
            attempts=1
        )
    except httpx.RequestError as e:
        return [], SourceStatus(
            status="unavailable",
            records_fetched=0,
            error=f"Connection/Timeout error: {str(e)}"
        )


async def fetch_resident(resident_id: str) -> Tuple[Resident | None, SourceStatus]:
    """
    Fetch a single resident by ID.
    """
    try:
        async with httpx.AsyncClient(timeout=REST_TIMEOUT) as client:
            resp = await client.get(f"{REST_BASE_URL}/residents/{resident_id}")
            
            if resp.status_code == 200:
                data = resp.json()
                return Resident(**data), SourceStatus(
                    status="ok",
                    records_fetched=1,
                    duplicates_removed=0,
                    attempts=1
                )
            elif resp.status_code == 404:
                return None, SourceStatus(
                    status="ok",
                    records_fetched=0,
                    duplicates_removed=0,
                    attempts=1
                )
            else:
                return None, SourceStatus(
                    status="unavailable",
                    records_fetched=0,
                    error=f"HTTP {resp.status_code}: {resp.text}"
                )
    except httpx.RequestError as e:
        return None, SourceStatus(
            status="unavailable",
            records_fetched=0,
            error=f"Connection/Timeout error: {str(e)}"
        )
