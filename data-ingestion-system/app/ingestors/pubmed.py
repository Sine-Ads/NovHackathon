"""app/ingestors/pubmed.py — PubMed (NCBI Entrez E-utilities) Ingestor.

API Reference:
  - Official API: https://www.ncbi.nlm.nih.gov/books/NBK25500/
  - Base URL: https://eutils.ncbi.nlm.nih.gov/entrez/eutils/
  - Search endpoint: esearch.fcgi?db=pubmed&term=haemophilia+OR+hemophilia&usehistory=y
  - Fetch endpoint: efetch.fcgi?db=pubmed&WebEnv=...&query_key=...&rettype=abstract&retmode=xml
  - Authentication: Optional API key via NCBI_API_KEY (lifts limit from 3 to 10 req/s)
  - Rate limits: 3 req/s without key, 10 req/s with key
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional, Tuple

import defusedxml.ElementTree as DefusedET

from app.ingestors.base import BaseIngestor, RawItem
from app.utils.logging import get_logger

logger = get_logger(__name__)


class PubMedIngestor(BaseIngestor):
    """Fetches peer-reviewed medical publications from NCBI PubMed using E-utilities."""

    name: str = "pubmed"
    display_name: str = "PubMed (NCBI)"
    ESEARCH_URL: str = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    EFETCH_URL: str = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"

    async def fetch(
        self, last_cursor: Optional[str] = None
    ) -> Tuple[List[RawItem], Optional[str]]:
        """Fetch PubMed publications matching 'haemophilia OR hemophilia'.

        Uses ESearch with usehistory=y to get WebEnv + query_key, then
        pages through EFetch with retstart/retmax.

        Args:
            last_cursor: String encoded as "{webenv}|{query_key}|{retstart}"
                         or integer offset string.
        """
        items: List[RawItem] = []
        max_items = self.settings.ingestor_max_items_per_run
        batch_size = 50

        # Optional NCBI API key
        api_key = self.settings.ncbi_api_key

        webenv: Optional[str] = None
        query_key: Optional[str] = None
        retstart = 0
        total_count = 0

        # Parse last_cursor if available
        if last_cursor and "|" in last_cursor:
            parts = last_cursor.split("|")
            if len(parts) == 3:
                webenv, query_key, retstart_str = parts
                try:
                    retstart = int(retstart_str)
                except ValueError:
                    retstart = 0

        # If we don't have active history server credentials, perform ESearch
        if not webenv or not query_key:
            search_params: Dict[str, Any] = {
                "db": "pubmed",
                "term": "haemophilia OR hemophilia",
                "usehistory": "y",
                "retmode": "json",
                "retmax": 0,
                "tool": "haemophilia_data_ingestion",
                "email": "admin@example.com",
            }
            if api_key:
                search_params["api_key"] = api_key

            logger.info("[%s] Executing ESearch for haemophilia literature...", self.name)
            search_resp = await self.get_with_retry(self.ESEARCH_URL, params=search_params)
            search_data = search_resp.json()
            esearch_result = search_data.get("esearchresult", {})

            total_count = int(esearch_result.get("count", 0))
            webenv = esearch_result.get("webenv")
            query_key = esearch_result.get("querykey")
            retstart = 0

            logger.info(
                "[%s] ESearch matched %d articles. WebEnv=%s, QueryKey=%s",
                self.name,
                total_count,
                webenv,
                query_key,
            )

        if not webenv or not query_key:
            logger.warning("[%s] ESearch failed to produce WebEnv/QueryKey", self.name)
            return items, None

        # Loop EFetch in batches
        while True:
            fetch_params: Dict[str, Any] = {
                "db": "pubmed",
                "WebEnv": webenv,
                "query_key": query_key,
                "retstart": retstart,
                "retmax": batch_size,
                "rettype": "abstract",
                "retmode": "xml",
                "tool": "haemophilia_data_ingestion",
                "email": "admin@example.com",
            }
            if api_key:
                fetch_params["api_key"] = api_key

            logger.debug("[%s] Fetching records retstart=%d retmax=%d", self.name, retstart, batch_size)
            fetch_resp = await self.get_with_retry(self.EFETCH_URL, params=fetch_params)

            try:
                root = DefusedET.fromstring(fetch_resp.text)
            except Exception as e:
                logger.error("[%s] Failed to parse PubMed XML response: %s", self.name, e)
                break

            articles = root.findall(".//PubmedArticle")
            if not articles:
                logger.info("[%s] No articles returned in batch retstart=%d", self.name, retstart)
                break

            for article in articles:
                pmid_elem = article.find(".//MedlineCitation/PMID")
                pmid = pmid_elem.text.strip() if pmid_elem is not None and pmid_elem.text else None
                if not pmid:
                    continue

                # Title
                title_elem = article.find(".//MedlineCitation/Article/ArticleTitle")
                title = "".join(title_elem.itertext()).strip() if title_elem is not None else "Untitled"

                # Abstract
                abstract_texts = []
                for abs_elem in article.findall(".//MedlineCitation/Article/Abstract/AbstractText"):
                    label = abs_elem.attrib.get("Label", "")
                    text_val = "".join(abs_elem.itertext()).strip()
                    if label:
                        abstract_texts.append(f"{label}: {text_val}")
                    elif text_val:
                        abstract_texts.append(text_val)
                abstract = "\n\n".join(abstract_texts)

                # Authors
                authors = []
                for auth in article.findall(".//MedlineCitation/Article/AuthorList/Author"):
                    last = auth.findtext("LastName", "")
                    fore = auth.findtext("ForeName", "")
                    if last or fore:
                        authors.append(f"{last} {fore}".strip())

                # Journal
                journal_title = article.findtext(".//MedlineCitation/Article/Journal/Title", "")
                journal_iso = article.findtext(".//MedlineCitation/Article/Journal/ISOAbbreviation", "")

                # Date
                pub_date_year = article.findtext(".//MedlineCitation/Article/Journal/JournalIssue/PubDate/Year")
                pub_date_month = article.findtext(".//MedlineCitation/Article/Journal/JournalIssue/PubDate/Month", "01")
                pub_date_day = article.findtext(".//MedlineCitation/Article/Journal/JournalIssue/PubDate/Day", "01")
                date_str = f"{pub_date_year}-{pub_date_month}-{pub_date_day}" if pub_date_year else None
                date_published = self.parse_datetime(date_str)

                # DOI
                doi = None
                for article_id in article.findall(".//PubmedData/ArticleIdList/ArticleId"):
                    if article_id.attrib.get("IdType") == "doi" and article_id.text:
                        doi = article_id.text.strip()
                        break

                # MeSH Headings
                mesh_terms = [
                    m.findtext("DescriptorName", "")
                    for m in article.findall(".//MedlineCitation/MeshHeadingList/MeshHeading")
                    if m.findtext("DescriptorName")
                ]

                source_url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"

                item = RawItem(
                    source_name=self.display_name,
                    source_id=pmid,
                    source_url=source_url,
                    title=title,
                    raw_content=abstract,
                    date_published=date_published,
                    metadata={
                        "pmid": pmid,
                        "doi": doi,
                        "authors": authors,
                        "journal": journal_title or journal_iso,
                        "mesh_terms": mesh_terms,
                    },
                )
                items.append(item)

                if max_items > 0 and len(items) >= max_items:
                    break

            retstart += len(articles)

            if len(articles) < batch_size or (max_items > 0 and len(items) >= max_items):
                break

        next_cursor = f"{webenv}|{query_key}|{retstart}"
        return items, next_cursor
