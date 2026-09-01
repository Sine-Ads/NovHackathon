"""app/ingestors — Registry of all data source ingestor classes."""
from __future__ import annotations

from typing import Dict, Type

from app.ingestors.arxiv import ArxivIngestor
from app.ingestors.base import BaseIngestor, RawItem
from app.ingestors.clinical_trials import ClinicalTrialsIngestor
from app.ingestors.medrxiv import MedRxivIngestor
from app.ingestors.openfda import OpenFDAIngestor
from app.ingestors.patents import PatentsIngestor
from app.ingestors.pubmed import PubMedIngestor
from app.ingestors.sec_edgar import SecEdgarIngestor
from app.ingestors.who_ictrp import WhoIctrpIngestor

# Registry mapping name -> class
INGESTOR_REGISTRY: Dict[str, Type[BaseIngestor]] = {
    ClinicalTrialsIngestor.name: ClinicalTrialsIngestor,
    PubMedIngestor.name: PubMedIngestor,
    OpenFDAIngestor.name: OpenFDAIngestor,
    WhoIctrpIngestor.name: WhoIctrpIngestor,
    MedRxivIngestor.name: MedRxivIngestor,
    ArxivIngestor.name: ArxivIngestor,
    PatentsIngestor.name: PatentsIngestor,
    SecEdgarIngestor.name: SecEdgarIngestor,
}

__all__ = [
    "BaseIngestor",
    "RawItem",
    "ClinicalTrialsIngestor",
    "PubMedIngestor",
    "OpenFDAIngestor",
    "WhoIctrpIngestor",
    "MedRxivIngestor",
    "ArxivIngestor",
    "PatentsIngestor",
    "SecEdgarIngestor",
    "INGESTOR_REGISTRY",
]
