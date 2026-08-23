"""
Benefits Register adapter.
Handles XML parsing, retries with linear backoff, and timeouts.
"""
import asyncio
import httpx
import xml.etree.ElementTree as ET
from urllib.parse import quote
from typing import List, Tuple

from app.config import XML_BASE_URL, XML_MAX_ATTEMPTS, XML_TIMEOUT, XML_BACKOFF_BASE
from app.models.models import BenefitRecord, SourceStatus


def parse_benefits_xml(xml_string: str) -> List[BenefitRecord]:
    """Parse the XML string into BenefitRecord objects."""
    records = []
    root = ET.fromstring(xml_string)
    
    # Check for Fault
    if root.tag == "Fault":
        return []
        
    for record_el in root.findall(".//Record"):
        ref = record_el.findtext("Ref", "")
        name = record_el.findtext("Name", "")
        born = record_el.findtext("Born", "")
        addr = record_el.findtext("Addr", "")
        town = record_el.findtext("Town", "")
        benefit_code = record_el.findtext("BenefitCode", "")
        review_due = record_el.findtext("ReviewDue", "")
        
        records.append(BenefitRecord(
            ref=ref,
            name=name,
            born=born,
            addr=addr,
            town=town,
            benefit_code=benefit_code,
            review_due=review_due
        ))
    return records


async def fetch_all_benefits() -> Tuple[List[BenefitRecord], SourceStatus]:
    """
    Fetch all benefits from the XML service.
    Implements 3 total attempts with linear backoff.
    Circuit breaker prevents repeated calls to a persistently failing service.
    """
    from app.circuit_breaker import benefits_circuit

    # Circuit breaker check: if OPEN, fail fast
    if not benefits_circuit.should_allow_request():
        remaining = benefits_circuit.time_remaining_open()
        return [], SourceStatus(
            status="unavailable",
            records_fetched=0,
            error=f"Circuit breaker OPEN (recovery in {remaining:.0f}s)",
            attempts=0
        )

    # Normal retry loop (unchanged)
    attempt = 0
    last_error = ""

    async with httpx.AsyncClient(timeout=XML_TIMEOUT) as client:
        while attempt < XML_MAX_ATTEMPTS:
            attempt += 1
            try:
                resp = await client.get(f"{XML_BASE_URL}/records")
                if resp.status_code == 200:
                    try:
                        records = parse_benefits_xml(resp.text)
                        benefits_circuit.record_success()
                        return records, SourceStatus(
                            status="ok",
                            records_fetched=len(records),
                            attempts=attempt
                        )
                    except ET.ParseError as e:
                        last_error = f"XML Parse Error: {str(e)}"
                elif resp.status_code == 500:
                    last_error = f"HTTP 500: {resp.text[:50]}"
                else:
                    last_error = f"HTTP {resp.status_code}"
            except httpx.RequestError as e:
                last_error = f"Connection/Timeout error: {str(e)}"

            if attempt < XML_MAX_ATTEMPTS:
                await asyncio.sleep(XML_BACKOFF_BASE * attempt)

    # All retries exhausted — record failure for circuit breaker
    benefits_circuit.record_failure()
    return [], SourceStatus(
        status="unavailable",
        records_fetched=0,
        error=last_error,
        attempts=attempt
    )


async def fetch_benefit(ref: str) -> Tuple[BenefitRecord | None, SourceStatus]:
    """
    Fetch a single benefit record by ref.
    """
    attempt = 0
    last_error = ""
    encoded_ref = quote(ref, safe='')
    
    async with httpx.AsyncClient(timeout=XML_TIMEOUT) as client:
        while attempt < XML_MAX_ATTEMPTS:
            attempt += 1
            try:
                resp = await client.get(f"{XML_BASE_URL}/records/{encoded_ref}")
                if resp.status_code == 200:
                    try:
                        records = parse_benefits_xml(resp.text)
                        return records[0] if records else None, SourceStatus(
                            status="ok",
                            records_fetched=1 if records else 0,
                            attempts=attempt
                        )
                    except ET.ParseError as e:
                        last_error = f"XML Parse Error: {str(e)}"
                elif resp.status_code == 404:
                    return None, SourceStatus(
                        status="ok",
                        records_fetched=0,
                        attempts=attempt
                    )
                elif resp.status_code == 500:
                    last_error = f"HTTP 500: {resp.text[:50]}"
                else:
                    last_error = f"HTTP {resp.status_code}"
            except httpx.RequestError as e:
                last_error = f"Connection/Timeout error: {str(e)}"
                
            if attempt < XML_MAX_ATTEMPTS:
                await asyncio.sleep(XML_BACKOFF_BASE * attempt)
                
    return None, SourceStatus(
        status="unavailable",
        records_fetched=0,
        error=last_error,
        attempts=attempt
    )
