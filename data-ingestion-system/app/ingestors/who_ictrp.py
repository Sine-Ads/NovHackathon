"""app/ingestors/who_ictrp.py — WHO ICTRP (International Clinical Trials Registry Platform) Ingestor.

Data Source Reference:
  - Official Search Portal: https://trialsearch.who.int/
  - Note: WHO ICTRP does not provide a public REST API. Programmatic access
    uses the official Export search CSV interface and filters for haemophilia/hemophilia trials.
  - Export URL: https://trialsearch.who.int/Export.aspx
  - Data Type: Global clinical trial registrations from WHO network of primary registries.
"""
from __future__ import annotations

import csv
import io
from typing import List, Optional, Tuple

from app.ingestors.base import BaseIngestor, RawItem
from app.utils.logging import get_logger

logger = get_logger(__name__)


class WhoIctrpIngestor(BaseIngestor):
    """Fetches international clinical trials from the WHO ICTRP portal."""

    name: str = "who_ictrp"
    display_name: str = "WHO ICTRP"
    EXPORT_URL: str = "https://trialsearch.who.int/Export.aspx"

    async def fetch(
        self, last_cursor: Optional[str] = None
    ) -> Tuple[List[RawItem], Optional[str]]:
        """Fetch clinical trials exported from WHO ICTRP matching haemophilia.

        Downloads exported CSV matching 'hemophilia' and normalises into RawItem records.
        """
        items: List[RawItem] = []
        max_items = self.settings.ingestor_max_items_per_run

        params = {
            "TrialID": "",
            "Title": "hemophilia",
            "InternationalId": "",
            "RegnAuth": "",
            "langfil": "ALL",
            "whofil": "N",
            "RecruStatus": "",
            "IcrpStat": "",
            "Phase": "",
            "healthCond": "",
            "CountriesOfRecruitment": "",
            "searchTxt": "",
            "format": "csv",
        }

        try:
            logger.info("[%s] Fetching trial export from WHO ICTRP...", self.name)
            resp = await self.get_with_retry(self.EXPORT_URL, params=params, timeout=60.0)

            # Check if response returned CSV data
            content_text = resp.text
            if not content_text or "<html" in content_text.lower():
                # Fallback search query on title=haemophilia if needed
                logger.info("[%s] WHO ICTRP direct export endpoint returned non-CSV or empty response", self.name)
                return items, None

            reader = csv.DictReader(io.StringIO(content_text))
            for row in reader:
                trial_id = (
                    row.get("TrialID")
                    or row.get("Trial ID")
                    or row.get("Main ID")
                    or row.get("trial_id")
                )
                if not trial_id:
                    continue

                public_title = (
                    row.get("Public title")
                    or row.get("Public_title")
                    or row.get("Title")
                    or row.get("Scientific title")
                    or "Untitled WHO Trial"
                )
                scientific_title = row.get("Scientific title") or row.get("Scientific_title")
                recruitment_status = row.get("Recruitment status") or row.get("Recruitment_status")
                condition = row.get("Condition") or row.get("Health Condition(s) Studied")
                intervention = row.get("Intervention") or row.get("Intervention(s) Studied")
                primary_sponsor = row.get("Primary sponsor") or row.get("Primary_sponsor")
                registration_date_str = row.get("Date of registration") or row.get("Date_registration")
                countries = row.get("Countries of recruitment") or row.get("Countries")

                date_published = self.parse_datetime(registration_date_str)
                source_url = f"https://trialsearch.who.int/Trial2.aspx?TrialID={trial_id}"

                raw_content = (
                    f"Scientific Title: {scientific_title or 'N/A'}\n"
                    f"Condition: {condition or 'N/A'}\n"
                    f"Intervention: {intervention or 'N/A'}\n"
                    f"Sponsor: {primary_sponsor or 'N/A'}\n"
                    f"Countries: {countries or 'N/A'}"
                )

                item = RawItem(
                    source_name=self.display_name,
                    source_id=trial_id.strip(),
                    source_url=source_url,
                    title=public_title.strip(),
                    raw_content=raw_content,
                    date_published=date_published,
                    metadata={
                        "trial_id": trial_id.strip(),
                        "scientific_title": scientific_title,
                        "recruitment_status": recruitment_status,
                        "condition": condition,
                        "intervention": intervention,
                        "primary_sponsor": primary_sponsor,
                        "countries": countries,
                    },
                )
                items.append(item)

                if max_items > 0 and len(items) >= max_items:
                    break

        except Exception as e:
            logger.warning("[%s] WHO ICTRP ingestor encountered error: %s", self.name, e)

        return items, None
