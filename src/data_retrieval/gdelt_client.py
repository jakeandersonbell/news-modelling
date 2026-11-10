"""GDELT DOC 2.0 API client for source-coverage evaluation (Phase 1, Task 2).

Wraps the free GDELT DOC 2.0 API, which exposes article metadata (URL, title,
domain, publish time, language, source country) and supports ``domain:`` scoped
queries. Used here to assess how many URLs GDELT offers per target outlet over a
given window.

Endpoint
--------
    https://api.gdeltproject.org/api/v2/doc/doc

Known limitations (important for Task 2 conclusions)
----------------------------------------------------
* The API returns at most ``MAX_RECORDS`` (250) articles per query.
* Full-text search only covers roughly the **last 3 months**. A historical
  window older than that will silently return little or nothing — use the
  GDELT BigQuery dataset or raw CSV dumps (see the ``bigquery`` optional
  dependency) for older periods.
* The service is rate-limited to ~1 request every 5 seconds per client. This
  client enforces that interval via ``min_interval`` and retries gracefully when
  GDELT responds with its plain-text throttle notice instead of JSON.

Docs: https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/
"""

from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Sequence

import requests

logger = logging.getLogger(__name__)

GDELT_DOC_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
DEFAULT_USER_AGENT = (
    "news-modelling-research/0.1 (+https://github.com/jakeandersonbell/news-modelling)"
)
MAX_RECORDS = 250


class GdeltError(RuntimeError):
    """Raised when the GDELT DOC API cannot satisfy a request."""


def _parse_seendate(value: str | None) -> datetime | None:
    """Parse a GDELT ``seendate`` (e.g. ``20240101T120000Z``) to an aware datetime."""
    if not value:
        return None
    for fmt in ("%Y%m%dT%H%M%SZ", "%Y%m%d%H%M%S"):
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _format_dt(value: str | datetime) -> str:
    """Format a datetime (or passthrough string) as GDELT ``YYYYMMDDHHMMSS``."""
    if isinstance(value, datetime):
        return value.strftime("%Y%m%d%H%M%S")
    return str(value)


@dataclass(frozen=True)
class GdeltArticle:
    """A single article record returned by the GDELT DOC API."""

    url: str
    title: str | None = None
    domain: str | None = None
    seendate: str | None = None
    language: str | None = None
    sourcecountry: str | None = None

    @property
    def published(self) -> datetime | None:
        """Publication time as an aware UTC datetime, if parseable."""
        return _parse_seendate(self.seendate)

    def as_dict(self) -> dict:
        return asdict(self)


class GdeltClient:
    """Throttled, retrying client for the GDELT DOC 2.0 article-list API."""

    def __init__(
        self,
        min_interval: float = 5.0,
        timeout: float = 60.0,
        max_retries: int = 4,
        backoff_factor: float = 2.0,
        session: requests.Session | None = None,
        user_agent: str = DEFAULT_USER_AGENT,
    ) -> None:
        self.min_interval = min_interval
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor
        self.user_agent = user_agent
        self._session = session or requests.Session()
        self._session.headers.update({"User-Agent": user_agent})
        self._lock = threading.Lock()
        self._last_request = 0.0

    # -- internals ---------------------------------------------------------

    def _throttle(self) -> None:
        """Block so that at most one request is issued per ``min_interval``."""
        with self._lock:
            wait = self.min_interval - (time.monotonic() - self._last_request)
            if wait > 0:
                time.sleep(wait)
            self._last_request = time.monotonic()

    @staticmethod
    def build_query(
        domains: str | Sequence[str] | None = None,
        query: str | None = None,
    ) -> str:
        """Build a GDELT query string from domain filters and/or a raw query."""
        parts: list[str] = []
        if domains:
            if isinstance(domains, str):
                domains = [domains]
            parts.append("(" + " OR ".join(f"domain:{d}" for d in domains) + ")")
        if query:
            parts.append(f"({query})")
        if not parts:
            raise ValueError("Provide at least one of `domains` or `query`.")
        return " ".join(parts)

    def _request(self, params: dict) -> dict:
        """Issue a throttled request, retrying on throttle notices and errors."""
        last_error: object = None
        for attempt in range(self.max_retries + 1):
            self._throttle()
            try:
                resp = self._session.get(
                    GDELT_DOC_URL, params=params, timeout=self.timeout
                )
            except requests.RequestException as exc:  # network layer
                last_error = exc
                logger.warning("GDELT request error (attempt %s): %s", attempt + 1, exc)
            else:
                text = resp.text.strip()
                if resp.status_code == 200 and text.startswith("{"):
                    return json.loads(text)
                # GDELT returns a plain-text throttle notice with a 200 status.
                snippet = text[:200]
                last_error = GdeltError(
                    f"Non-JSON response (status {resp.status_code}): {snippet}"
                )
                logger.warning(
                    "GDELT returned non-JSON (attempt %s): %s",
                    attempt + 1,
                    snippet,
                )

            if attempt < self.max_retries:
                time.sleep(self.backoff_factor * (attempt + 1) + self.min_interval)

        raise GdeltError(
            f"GDELT request failed after {self.max_retries + 1} attempts: {last_error}"
        )

    # -- public API --------------------------------------------------------

    def query_articles(
        self,
        domains: str | Sequence[str] | None = None,
        query: str | None = None,
        start: str | datetime | None = None,
        end: str | datetime | None = None,
        timespan: str | None = None,
        max_records: int = MAX_RECORDS,
        sort: str = "datedesc",
    ) -> list[GdeltArticle]:
        """Return a list of articles matching a domain/query within a window.

        Parameters
        ----------
        domains:
            Outlet domain(s) to filter on, e.g. ``"bbc.co.uk"`` or a list.
        query:
            Optional additional GDELT query (keywords, themes, etc.).
        start, end:
            Window bounds as ``datetime`` or ``YYYYMMDDHHMMSS`` strings. Ignored
            if ``timespan`` is given.
        timespan:
            GDELT relative window, e.g. ``"3m"`` (last three months).
        max_records:
            Capped at :data:`MAX_RECORDS` (250) by the API.
        """
        params: dict = {
            "query": self.build_query(domains, query),
            "mode": "artlist",
            "format": "json",
            "maxrecords": min(int(max_records), MAX_RECORDS),
            "sort": sort,
        }
        if timespan:
            params["timespan"] = timespan
        else:
            if start:
                params["startdatetime"] = _format_dt(start)
            if end:
                params["enddatetime"] = _format_dt(end)

        data = self._request(params)
        return [
            GdeltArticle(
                url=a.get("url", ""),
                title=a.get("title"),
                domain=a.get("domain"),
                seendate=a.get("seendate"),
                language=a.get("language"),
                sourcecountry=a.get("sourcecountry"),
            )
            for a in data.get("articles", [])
        ]

    def count_articles(self, **kwargs) -> int:
        """Return the number of articles matched (capped at 250 by the API)."""
        return len(self.query_articles(**kwargs))


def articles_to_dataframe(articles: Sequence[GdeltArticle]):
    """Convert GDELT articles to a pandas DataFrame (pandas imported lazily)."""
    import pandas as pd

    rows = []
    for a in articles:
        row = a.as_dict()
        row["published"] = a.published
        rows.append(row)
    return pd.DataFrame(rows)
