"""
Pydantic data models for the internal canonical representation.
"""
from typing import List, Optional
from pydantic import BaseModel


class Resident(BaseModel):
    """Resident record from the Resident Index."""
    id: str
    first_name: str
    last_name: str
    date_of_birth: str
    address_line: str
    city: str
    phone: str
    program_status: str
    last_contact: str


class BenefitRecord(BaseModel):
    """Benefit record from the Benefits Register."""
    ref: str
    name: str
    born: str
    addr: str
    town: str
    benefit_code: str
    review_due: str


class SourceStatus(BaseModel):
    """Status information for a specific upstream source."""
    status: str  # "ok" | "degraded" | "unavailable"
    records_fetched: int = 0
    duplicates_removed: Optional[int] = None
    error: Optional[str] = None
    attempts: int = 1


class SourceEnvelopes(BaseModel):
    """Status for all sources."""
    resident_index: SourceStatus
    benefits_register: SourceStatus


class SearchQuery(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    date_of_birth: Optional[str] = None


class UnifiedSearchData(BaseModel):
    """Data payload for /search."""
    query: SearchQuery
    resident_index_matches: List[Resident]
    benefits_register_matches: List[BenefitRecord]


class UnifiedSearchResponse(BaseModel):
    """Response envelope for /search."""
    data: UnifiedSearchData
    sources: SourceEnvelopes
