"""tests/test_ingestors.py — Unit tests for all 8 ingestors with mocked HTTP responses."""
from __future__ import annotations

import httpx
import pytest
import respx

from app.ingestors import (
    ArxivIngestor,
    ClinicalTrialsIngestor,
    MedRxivIngestor,
    OpenFDAIngestor,
    PatentsIngestor,
    PubMedIngestor,
    SecEdgarIngestor,
    WhoIctrpIngestor,
)
from tests.fixtures.mock_data import (
    MOCK_ARXIV_XML,
    MOCK_CLINICAL_TRIALS_RESPONSE,
    MOCK_MEDRXIV_RESPONSE,
    MOCK_OPENFDA_EVENTS_RESPONSE,
    MOCK_OPENFDA_RECALLS_RESPONSE,
    MOCK_PUBMED_EFETCH_XML,
    MOCK_PUBMED_ESEARCH_RESPONSE,
    MOCK_SEC_EDGAR_RESPONSE,
    MOCK_USPTO_PATENTS_RESPONSE,
    MOCK_WHO_ICTRP_CSV,
)


@pytest.mark.asyncio
@respx.mock
async def test_clinical_trials_ingestor():
    """Test ClinicalTrialsIngestor parses studies and pagination correctly."""
    respx.get("https://clinicaltrials.gov/api/v2/studies").respond(
        status_code=200, json=MOCK_CLINICAL_TRIALS_RESPONSE
    )

    ingestor = ClinicalTrialsIngestor()
    items, next_cursor = await ingestor.fetch()

    assert len(items) == 1
    item = items[0]
    assert item.source_name == "ClinicalTrials.gov"
    assert item.source_id == "NCT04567890"
    assert "Hemophilia A" in item.title
    assert item.metadata["overall_status"] == "RECRUITING"
    assert item.metadata["lead_sponsor"] == "BioMarin Pharmaceutical"
    assert next_cursor is None


@pytest.mark.asyncio
@respx.mock
async def test_pubmed_ingestor():
    """Test PubMedIngestor performs ESearch + EFetch workflow and parses XML."""
    respx.get("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi").respond(
        status_code=200, json=MOCK_PUBMED_ESEARCH_RESPONSE
    )
    respx.get("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi").respond(
        status_code=200, text=MOCK_PUBMED_EFETCH_XML
    )

    ingestor = PubMedIngestor()
    items, next_cursor = await ingestor.fetch()

    assert len(items) == 1
    item = items[0]
    assert item.source_name == "PubMed (NCBI)"
    assert item.source_id == "38123456"
    assert "Advances in Prophylactic Treatment for Haemophilia A" in item.title
    assert "Smith John" in item.metadata["authors"]
    assert item.metadata["doi"] == "10.1056/NEJMoa2301234"
    assert "MCID_65f123456789abcdef" in (next_cursor or "")


@pytest.mark.asyncio
@respx.mock
async def test_openfda_ingestor():
    """Test OpenFDAIngestor fetches adverse events and drug recalls."""
    respx.get("https://api.fda.gov/drug/event.json").respond(
        status_code=200, json=MOCK_OPENFDA_EVENTS_RESPONSE
    )
    respx.get("https://api.fda.gov/drug/enforcement.json").respond(
        status_code=200, json=MOCK_OPENFDA_RECALLS_RESPONSE
    )

    ingestor = OpenFDAIngestor()
    items, next_cursor = await ingestor.fetch()

    assert len(items) == 2
    event_item = next(i for i in items if i.metadata["type"] == "adverse_event")
    recall_item = next(i for i in items if i.metadata["type"] == "drug_recall")

    assert event_item.source_id == "event_10023456"
    assert "HEMLIBRA" in event_item.metadata["drugs"]
    assert recall_item.source_id == "recall_D-0123-2024"
    assert recall_item.metadata["classification"] == "Class II"


@pytest.mark.asyncio
@respx.mock
async def test_who_ictrp_ingestor():
    """Test WhoIctrpIngestor parses exported CSV and extracts trials."""
    respx.get("https://trialsearch.who.int/Export.aspx").respond(
        status_code=200, text=MOCK_WHO_ICTRP_CSV
    )

    ingestor = WhoIctrpIngestor()
    items, _ = await ingestor.fetch()

    assert len(items) == 1
    item = items[0]
    assert item.source_name == "WHO ICTRP"
    assert item.source_id == "CTRI/2023/01/048123"
    assert "Hemophilia" in item.title
    assert item.metadata["primary_sponsor"] == "AIIMS"


@pytest.mark.asyncio
@respx.mock
async def test_medrxiv_ingestor():
    """Test MedRxivIngestor filters preprints for haemophilia keywords."""
    respx.get(url__regex=r"https://api\.biorxiv\.org/details/medrxiv/.*").respond(
        status_code=200, json=MOCK_MEDRXIV_RESPONSE
    )

    ingestor = MedRxivIngestor()
    items, next_cursor = await ingestor.fetch()

    assert len(items) == 1
    item = items[0]
    assert item.source_name == "medRxiv"
    assert item.source_id == "10.1101/2024.01.15.24301234"
    assert "Gene Therapy in Severe Hemophilia B" in item.title
    assert item.metadata["category"] == "Hematology"


@pytest.mark.asyncio
@respx.mock
async def test_arxiv_ingestor():
    """Test ArxivIngestor parses Atom XML and extracts metadata."""
    respx.get("http://export.arxiv.org/api/query").respond(
        status_code=200, text=MOCK_ARXIV_XML
    )

    ingestor = ArxivIngestor()
    items, next_cursor = await ingestor.fetch()

    assert len(items) == 1
    item = items[0]
    assert item.source_name == "arXiv"
    assert "2401.09876" in item.source_id
    assert "PK Modeling in Haemophilia A" in item.title
    assert "Alan Turing" in item.metadata["authors"]


@pytest.mark.asyncio
@respx.mock
async def test_patents_ingestor():
    """Test PatentsIngestor fetches from USPTO Open Data Portal API."""
    respx.get("https://developer.uspto.gov/ibd-api/v1/patent/application").respond(
        status_code=200, json=MOCK_USPTO_PATENTS_RESPONSE
    )

    ingestor = PatentsIngestor()
    items, next_cursor = await ingestor.fetch()

    assert len(items) == 1
    item = items[0]
    assert item.source_name == "USPTO Patents"
    assert item.source_id == "18123456"
    assert "Factor VIII Molecules" in item.title
    assert item.metadata["applicant"] == "BioGenetics Corp"


@pytest.mark.asyncio
@respx.mock
async def test_sec_edgar_ingestor():
    """Test SecEdgarIngestor queries EFTS search index and extracts disclosures."""
    respx.get("https://efts.sec.gov/LATEST/search-index").respond(
        status_code=200, json=MOCK_SEC_EDGAR_RESPONSE
    )

    ingestor = SecEdgarIngestor()
    items, next_cursor = await ingestor.fetch()

    assert len(items) == 1
    item = items[0]
    assert item.source_name == "SEC EDGAR"
    assert "BIOMARIN PHARMACEUTICAL" in item.title
    assert item.metadata["form"] == "10-K"
    assert "0001048268" in item.metadata["ciks"]
