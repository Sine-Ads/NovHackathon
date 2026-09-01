"""app/ingestors/clinical_trials.py — ClinicalTrials.gov Ingestor.

API Reference:
  - Official API: https://clinicaltrials.gov/data-api/api
  - Base URL: https://clinicaltrials.gov/api/v2
  - Endpoint: GET /studies
  - Conditions search: query.cond=haemophilia OR hemophilia
  - Pagination: pageToken in response; pass as pageToken in next call
  - Rate limit: ~50 requests/min (public, no auth required)
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from app.ingestors.base import BaseIngestor, RawItem
from app.utils.logging import get_logger

logger = get_logger(__name__)


class ClinicalTrialsIngestor(BaseIngestor):
    """Fetches clinical trial registrations from ClinicalTrials.gov REST API v2."""

    name: str = "clinical_trials"
    display_name: str = "ClinicalTrials.gov"
    BASE_URL: str = "https://clinicaltrials.gov/api/v2/studies"

    async def fetch(
        self, last_cursor: Optional[str] = None
    ) -> Tuple[List[RawItem], Optional[str]]:
        """Fetch clinical trials matching 'haemophilia OR hemophilia'.

        Args:
            last_cursor: pageToken string from previous run (if resuming).

        Returns:
            Tuple of (items, next_page_token)
        """
        items: List[RawItem] = []
        page_token: Optional[str] = last_cursor
        max_items = self.settings.ingestor_max_items_per_run
        page_size = min(100, max_items) if max_items > 0 else 100

        while True:
            params: Dict[str, Any] = {
                "query.cond": "haemophilia OR hemophilia",
                "pageSize": page_size,
                "format": "json",
            }
            if page_token:
                params["pageToken"] = page_token

            logger.debug("[%s] Requesting page with token: %s", self.name, page_token)
            response = await self.get_with_retry(self.BASE_URL, params=params)
            data = response.json()

            studies = data.get("studies", [])
            if not studies:
                logger.info("[%s] No more studies returned", self.name)
                page_token = None
                break

            for study in studies:
                protocol = study.get("protocolSection", {})
                ident = protocol.get("identificationModule", {})
                status_mod = protocol.get("statusModule", {})
                sponsor_mod = protocol.get("sponsorCollaboratorsModule", {})
                conditions_mod = protocol.get("conditionsModule", {})
                interventions_mod = protocol.get("interventionsModule", {})
                description_mod = protocol.get("descriptionModule", {})

                nct_id = ident.get("nctId")
                if not nct_id:
                    continue

                brief_title = ident.get("briefTitle") or ident.get("officialTitle") or "Untitled Study"
                official_title = ident.get("officialTitle")
                overall_status = status_mod.get("overallStatus")
                start_date_dict = status_mod.get("startDateStruct", {})
                start_date_str = start_date_dict.get("date")
                lead_sponsor = sponsor_mod.get("leadSponsor", {}).get("name")
                conditions = conditions_mod.get("conditions", [])
                interventions = [
                    inv.get("name")
                    for inv in interventions_mod.get("interventions", [])
                    if inv.get("name")
                ]
                brief_summary = description_mod.get("briefSummary")
                detailed_description = description_mod.get("detailedDescription")

                raw_content = detailed_description or brief_summary or ""
                date_published = self.parse_datetime(start_date_str)

                source_url = f"https://clinicaltrials.gov/study/{nct_id}"

                item = RawItem(
                    source_name=self.display_name,
                    source_id=nct_id,
                    source_url=source_url,
                    title=brief_title,
                    raw_content=raw_content,
                    date_published=date_published,
                    metadata={
                        "nct_id": nct_id,
                        "official_title": official_title,
                        "overall_status": overall_status,
                        "lead_sponsor": lead_sponsor,
                        "conditions": conditions,
                        "interventions": interventions,
                        "brief_summary": brief_summary,
                    },
                )
                items.append(item)

                if max_items > 0 and len(items) >= max_items:
                    break

            next_page_token = data.get("nextPageToken")
            if not next_page_token or (max_items > 0 and len(items) >= max_items):
                page_token = next_page_token
                break

            page_token = next_page_token

        return items, page_token
