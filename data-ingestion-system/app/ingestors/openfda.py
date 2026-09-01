"""app/ingestors/openfda.py — OpenFDA Drug Adverse Events and Recalls Ingestor.

API Reference:
  - Official Docs: https://open.fda.gov/apis/
  - Adverse Events Endpoint: https://api.fda.gov/drug/event.json
  - Drug Recalls Endpoint: https://api.fda.gov/drug/enforcement.json
  - Authentication: Optional API key via OPENFDA_API_KEY (lifts limit from 240/min to 240k/day)
  - Pagination: skip + limit parameters
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from app.ingestors.base import BaseIngestor, RawItem
from app.utils.logging import get_logger

logger = get_logger(__name__)


class OpenFDAIngestor(BaseIngestor):
    """Fetches FDA adverse drug event reports and drug recalls related to haemophilia."""

    name: str = "openfda"
    display_name: str = "OpenFDA"
    EVENT_URL: str = "https://api.fda.gov/drug/event.json"
    RECALL_URL: str = "https://api.fda.gov/drug/enforcement.json"

    async def _fetch_adverse_events(
        self, start_skip: int = 0, limit: int = 50
    ) -> Tuple[List[RawItem], int]:
        """Fetch adverse events where indication or drug name matches haemophilia."""
        items: List[RawItem] = []
        skip = start_skip
        api_key = self.settings.openfda_api_key

        # Search query covering haemophilia indications & factor products
        search_query = (
            'patient.drug.drugindication:"HAEMOPHILIA"+OR+'
            'patient.drug.drugindication:"HEMOPHILIA"+OR+'
            'patient.drug.medicinalproduct:"FACTOR VIII"+OR+'
            'patient.drug.medicinalproduct:"FACTOR IX"+OR+'
            'patient.drug.medicinalproduct:"HEMLIBRA"'
        )

        params: Dict[str, Any] = {
            "search": search_query,
            "limit": limit,
            "skip": skip,
        }
        if api_key:
            params["api_key"] = api_key

        try:
            resp = await self.get_with_retry(self.EVENT_URL, params=params)
            data = resp.json()
        except Exception as e:
            logger.warning("[%s] Failed to fetch adverse events: %s", self.name, e)
            return items, skip

        results = data.get("results", [])
        for event in results:
            report_id = event.get("safetyreportid")
            if not report_id:
                continue

            receipt_date_str = event.get("receiptdate")  # Format YYYYMMDD
            date_published = self.parse_datetime(receipt_date_str)

            patient = event.get("patient", {})
            drugs = patient.get("drug", [])
            reactions = [
                r.get("reactionmeddrapt")
                for r in patient.get("reaction", [])
                if r.get("reactionmeddrapt")
            ]

            drug_names = [d.get("medicinalproduct") for d in drugs if d.get("medicinalproduct")]
            indications = [d.get("drugindication") for d in drugs if d.get("drugindication")]

            title = f"FDA Adverse Event Report {report_id} — {', '.join(drug_names[:3]) or 'Unknown Drug'}"
            content_parts = [
                f"Safety Report ID: {report_id}",
                f"Serious: {'Yes' if event.get('serious') == '1' else 'No'}",
                f"Reported Reactions: {', '.join(reactions) or 'None listed'}",
                f"Suspect/Concomitant Drugs: {', '.join(drug_names) or 'None listed'}",
                f"Reported Indications: {', '.join(indications) or 'None listed'}",
            ]
            raw_content = "\n".join(content_parts)

            source_url = f"https://api.fda.gov/drug/event.json?search=safetyreportid:{report_id}"

            item = RawItem(
                source_name=self.display_name,
                source_id=f"event_{report_id}",
                source_url=source_url,
                title=title,
                raw_content=raw_content,
                date_published=date_published,
                metadata={
                    "type": "adverse_event",
                    "safetyreportid": report_id,
                    "serious": event.get("serious"),
                    "drugs": drug_names,
                    "reactions": reactions,
                    "indications": indications,
                },
            )
            items.append(item)

        return items, skip + len(results)

    async def _fetch_recalls(
        self, start_skip: int = 0, limit: int = 50
    ) -> Tuple[List[RawItem], int]:
        """Fetch FDA drug enforcement/recall actions related to haemophilia."""
        items: List[RawItem] = []
        skip = start_skip
        api_key = self.settings.openfda_api_key

        search_query = (
            'product_description:"hemophilia"+OR+'
            'product_description:"haemophilia"+OR+'
            'product_description:"Factor VIII"+OR+'
            'product_description:"Factor IX"'
        )

        params: Dict[str, Any] = {
            "search": search_query,
            "limit": limit,
            "skip": skip,
        }
        if api_key:
            params["api_key"] = api_key

        try:
            resp = await self.get_with_retry(self.RECALL_URL, params=params)
            data = resp.json()
        except Exception as e:
            logger.warning("[%s] Failed to fetch recalls: %s", self.name, e)
            return items, skip

        results = data.get("results", [])
        for recall in results:
            recall_num = recall.get("recall_number")
            if not recall_num:
                continue

            report_date_str = recall.get("report_date")
            date_published = self.parse_datetime(report_date_str)

            product_desc = recall.get("product_description", "")
            reason = recall.get("reason_for_recall", "")
            firm = recall.get("recalling_firm", "")
            status = recall.get("status", "")
            classification = recall.get("classification", "")

            title = f"FDA Drug Recall [{classification}]: {recall_num} ({firm})"
            raw_content = f"Product: {product_desc}\n\nReason for Recall: {reason}\n\nRecalling Firm: {firm}\nStatus: {status}"

            source_url = f"https://api.fda.gov/drug/enforcement.json?search=recall_number:{recall_num}"

            item = RawItem(
                source_name=self.display_name,
                source_id=f"recall_{recall_num}",
                source_url=source_url,
                title=title,
                raw_content=raw_content,
                date_published=date_published,
                metadata={
                    "type": "drug_recall",
                    "recall_number": recall_num,
                    "classification": classification,
                    "status": status,
                    "recalling_firm": firm,
                    "reason_for_recall": reason,
                },
            )
            items.append(item)

        return items, skip + len(results)

    async def fetch(
        self, last_cursor: Optional[str] = None
    ) -> Tuple[List[RawItem], Optional[str]]:
        """Fetch adverse events and recalls, combining results."""
        event_skip = 0
        recall_skip = 0

        if last_cursor and ":" in last_cursor:
            parts = last_cursor.split(":")
            try:
                event_skip = int(parts[0])
                recall_skip = int(parts[1])
            except ValueError:
                pass

        max_items = self.settings.ingestor_max_items_per_run
        fetch_limit = min(50, max_items // 2) if max_items > 0 else 50

        event_items, next_event_skip = await self._fetch_adverse_events(
            start_skip=event_skip, limit=fetch_limit
        )
        recall_items, next_recall_skip = await self._fetch_recalls(
            start_skip=recall_skip, limit=fetch_limit
        )

        all_items = event_items + recall_items
        next_cursor = f"{next_event_skip}:{next_recall_skip}"

        return all_items, next_cursor
