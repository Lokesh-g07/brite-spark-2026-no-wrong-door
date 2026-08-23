import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch
import xml.etree.ElementTree as ET

from app.main import app
from app.models.models import Resident, BenefitRecord, SourceStatus
from app.adapters.benefits_adapter import parse_benefits_xml

client = TestClient(app)

MOCK_RESIDENT = Resident(
    id="R-1", first_name="Maria", last_name="Delgado", date_of_birth="1971-04-02",
    address_line="1", city="C", phone="123", program_status="Active", last_contact="2020-01-01"
)
MOCK_BENEFIT = BenefitRecord(
    ref="REF-1", name="DELGADO, Maria", born="1971-04-02", addr="1", town="C",
    benefit_code="X", review_due="2021-01-01"
)

def test_xml_pascalcase_parsing():
    """Verify the XML parser correctly extracts PascalCase tags."""
    xml_data = '''<?xml version="1.0" encoding="UTF-8"?>
<BenefitsRegister>
  <Record>
    <Ref>NO/2019/4234</Ref>
    <Name>DELGADO, Maria</Name>
    <Born>1971-04-02</Born>
    <Addr>118 Cedar Avenue</Addr>
    <Town>Northgate</Town>
    <BenefitCode>HSP-B</BenefitCode>
    <ReviewDue>2026-05-14</ReviewDue>
  </Record>
</BenefitsRegister>
'''
    records = parse_benefits_xml(xml_data)
    assert len(records) == 1
    assert records[0].ref == "NO/2019/4234"
    assert records[0].name == "DELGADO, Maria"
    assert records[0].born == "1971-04-02"
    assert records[0].addr == "118 Cedar Avenue"
    assert records[0].town == "Northgate"
    assert records[0].benefit_code == "HSP-B"
    assert records[0].review_due == "2026-05-14"

@patch('app.adapters.resident_adapter.fetch_all_residents')
@patch('app.adapters.benefits_adapter.fetch_all_benefits')
def test_unified_search_success(mock_benefits, mock_residents):
    """Test successful search hitting both services."""
    mock_residents.return_value = ([MOCK_RESIDENT], SourceStatus(status="ok", records_fetched=1, attempts=1))
    mock_benefits.return_value = ([MOCK_BENEFIT], SourceStatus(status="ok", records_fetched=1, attempts=1))
    
    resp = client.get("/search?last_name=Delgado")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["data"]["resident_index_matches"]) == 1
    assert len(data["data"]["benefits_register_matches"]) == 1
    assert data["sources"]["resident_index"]["status"] == "ok"
    assert data["sources"]["benefits_register"]["status"] == "ok"

@patch('app.adapters.resident_adapter.fetch_all_residents')
@patch('app.adapters.benefits_adapter.fetch_all_benefits')
def test_resident_only_degradation(mock_benefits, mock_residents):
    """Test Resident failure leaves Benefits intact."""
    mock_residents.side_effect = Exception("REST down")
    mock_benefits.return_value = ([MOCK_BENEFIT], SourceStatus(status="ok", records_fetched=1, attempts=1))
    
    resp = client.get("/search")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["data"]["resident_index_matches"]) == 0
    assert len(data["data"]["benefits_register_matches"]) == 1
    assert data["sources"]["resident_index"]["status"] == "unavailable"
    assert data["sources"]["benefits_register"]["status"] == "ok"

@patch('app.adapters.resident_adapter.fetch_all_residents')
@patch('app.adapters.benefits_adapter.fetch_all_benefits')
def test_benefits_only_degradation(mock_benefits, mock_residents):
    """Test Benefits failure leaves Residents intact."""
    mock_residents.return_value = ([MOCK_RESIDENT], SourceStatus(status="ok", records_fetched=1, attempts=1))
    mock_benefits.side_effect = Exception("XML down")
    
    resp = client.get("/search")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["data"]["resident_index_matches"]) == 1
    assert len(data["data"]["benefits_register_matches"]) == 0
    assert data["sources"]["resident_index"]["status"] == "ok"
    assert data["sources"]["benefits_register"]["status"] == "unavailable"
    assert "XML down" in data["sources"]["benefits_register"]["error"]

@patch('app.adapters.resident_adapter.fetch_all_residents')
@patch('app.adapters.benefits_adapter.fetch_all_benefits')
def test_both_sources_failing(mock_benefits, mock_residents):
    """Test both failing returns empty lists gracefully."""
    mock_residents.side_effect = Exception("REST down")
    mock_benefits.side_effect = Exception("XML down")
    
    resp = client.get("/search")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["data"]["resident_index_matches"]) == 0
    assert len(data["data"]["benefits_register_matches"]) == 0
    assert data["sources"]["resident_index"]["status"] == "unavailable"
    assert data["sources"]["benefits_register"]["status"] == "unavailable"

@patch('app.adapters.resident_adapter.fetch_all_residents')
@patch('app.adapters.benefits_adapter.fetch_all_benefits')
def test_filtering_logic(mock_benefits, mock_residents):
    """Test the name/dob filtering on both arrays."""
    mock_residents.return_value = ([
        MOCK_RESIDENT,
        Resident(id="R-2", first_name="John", last_name="Smith", date_of_birth="2000-01-01", address_line="", city="", phone="", program_status="", last_contact="")
    ], SourceStatus(status="ok", records_fetched=2, attempts=1))
    
    mock_benefits.return_value = ([
        MOCK_BENEFIT,
        BenefitRecord(ref="REF-2", name="SMITH, John", born="2000-01-01", addr="", town="", benefit_code="", review_due="")
    ], SourceStatus(status="ok", records_fetched=2, attempts=1))
    
    # Filter by Delgado
    resp = client.get("/search?last_name=Delgado")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["data"]["resident_index_matches"]) == 1
    assert len(data["data"]["benefits_register_matches"]) == 1
    assert data["data"]["resident_index_matches"][0]["id"] == "R-1"

    # Filter by John
    resp2 = client.get("/search?first_name=John")
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert len(data2["data"]["resident_index_matches"]) == 1
    assert len(data2["data"]["benefits_register_matches"]) == 1
    assert data2["data"]["resident_index_matches"][0]["id"] == "R-2"

@patch('app.adapters.resident_adapter.fetch_all_residents')
@patch('app.adapters.benefits_adapter.fetch_all_benefits')
def test_repeated_identical_requests(mock_benefits, mock_residents):
    """Test idempotency: identical requests yield identical results."""
    mock_residents.return_value = ([MOCK_RESIDENT], SourceStatus(status="ok", records_fetched=1, attempts=1))
    mock_benefits.return_value = ([MOCK_BENEFIT], SourceStatus(status="ok", records_fetched=1, attempts=1))
    
    resp1 = client.get("/search?last_name=Delgado")
    resp2 = client.get("/search?last_name=Delgado")
    assert resp1.json() == resp2.json()
