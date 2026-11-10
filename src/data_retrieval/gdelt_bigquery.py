"""GDELT 2.0 BigQuery client (Phase 1, Task 2).

Why this exists
---------------
The GDELT **DOC API** is rate-limited by IP and only covers roughly the last
3 months, which makes it unusable for a defined historical window (we hit
persistent ``HTTP 200 + "limit requests"`` throttle responses). GDELT's
authoritative bulk data lives in the public BigQuery dataset ``gdelt-bq``.

We query the **Global Knowledge Graph (GKG)** table, which carries both the
source domain (``SourceCommonName``) and the article URL
(``DocumentIdentifier``) — so per-outlet article counts are exact and, for a
single window, all outlets can be counted in **one** query (one scan).

Requirements
------------
::

    pip install -e ".[bigquery]"          # google-cloud-bigquery
    gcloud auth application-default login # one-time, interactive
    export GOOGLE_CLOUD_PROJECT=<your-project-id>

Notes on cost
-------------
BigQuery bills by bytes scanned. GKG is large, so:

* Prefer the **partitioned** table (``gdelt-bq.gdeltv2.gkg_partitioned``) so a
  ``DATE`` filter prunes partitions.
* Use :meth:`GdeltBigQueryClient.dry_run_bytes` to check cost *before* running a
  real query. The free tier covers 1 TB of queries per month.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Sequence

logger = logging.getLogger(__name__)

#: Partitioned GKG table — a DATE filter prunes partitions, keeping scans cheap.
DEFAULT_TABLE = "gdelt-bq.gdeltv2.gkg_partitioned"


class GdeltBigQueryError(RuntimeError):
    """Raised when BigQuery access or dependencies are unavailable."""


def _format_gkg_datetime(value: str | datetime | int) -> int:
    """Format a timestamp as a GKG ``DATE`` integer (``YYYYMMDDHHMMSS``)."""
    if isinstance(value, datetime):
        return int(value.strftime("%Y%m%d%H%M%S"))
    if isinstance(value, int):
        return value
    return int(str(value))


@dataclass
class DomainCount:
    """Per-domain article count from GDELT GKG."""

    domain: str
    articles: int


class GdeltBigQueryClient:
    """Query GDELT 2.0 (GKG) for per-outlet article volume over a window."""

    def __init__(
        self,
        project: str | None = None,
        table: str = DEFAULT_TABLE,
        client=None,
    ) -> None:
        try:
            from google.cloud import bigquery
        except ImportError as exc:  # dependency not installed
            raise GdeltBigQueryError(
                "google-cloud-bigquery is not installed. "
                'Install it with:  pip install -e ".[bigquery]"'
            ) from exc

        self._bigquery = bigquery
        self.table = table

        if client is not None:
            self.client = client
        else:
            try:
                self.client = bigquery.Client(project=project)
            except Exception as exc:  # no credentials / no default project
                raise GdeltBigQueryError(
                    "Could not create a BigQuery client. Authenticate once with "
                    "`gcloud auth application-default login` and set "
                    "GOOGLE_CLOUD_PROJECT (or pass project=...). "
                    f"Underlying error: {exc}"
                ) from exc

    # -- internals ---------------------------------------------------------

    def _run(self, sql: str, params: Sequence, dry_run: bool = False):
        job_config = self._bigquery.QueryJobConfig(
            query_parameters=list(params),
            dry_run=dry_run,
            use_query_cache=not dry_run,
        )
        job = self.client.query(sql, job_config=job_config)
        if dry_run:
            return job
        return list(job.result())

    def dry_run_bytes(self, sql: str, params: Sequence = ()) -> int:
        """Return the number of bytes a query would scan, without running it."""
        job = self._run(sql, params, dry_run=True)
        return int(job.total_bytes_processed or 0)

    # -- public API --------------------------------------------------------

    def count_articles_for_domains(
        self,
        domains: Sequence[str],
        start: str | datetime | int,
        end: str | datetime | int,
        dry_run: bool = False,
    ) -> dict[str, int] | int:
        """Count distinct article URLs per domain over a window, in one scan.

        Returns ``{domain: count}`` (0 for domains with no rows), or the
        estimated bytes scanned if ``dry_run`` is True.
        """
        sql = f"""
            SELECT SourceCommonName AS domain,
                   COUNT(DISTINCT DocumentIdentifier) AS articles
            FROM `{self.table}`
            WHERE SourceCommonName IN UNNEST(@domains)
              AND DATE BETWEEN @start AND @end
            GROUP BY domain
        """
        params = [
            self._bigquery.ArrayQueryParameter("domains", "STRING", list(domains)),
            self._bigquery.ScalarQueryParameter(
                "start", "INT64", _format_gkg_datetime(start)
            ),
            self._bigquery.ScalarQueryParameter(
                "end", "INT64", _format_gkg_datetime(end)
            ),
        ]
        if dry_run:
            return self.dry_run_bytes(sql, params)

        counts = {d: 0 for d in domains}
        for row in self._run(sql, params):
            counts[row["domain"]] = int(row["articles"])
        return counts

    def count_articles(
        self,
        domain: str,
        start: str | datetime | int,
        end: str | datetime | int,
        dry_run: bool = False,
    ) -> int | int:
        """Count distinct article URLs for a single domain over a window."""
        result = self.count_articles_for_domains(
            [domain], start, end, dry_run=dry_run
        )
        if dry_run:
            return result  # type: ignore[return-value]
        return result.get(domain, 0)

    def sample_articles(
        self,
        domain: str,
        start: str | datetime | int,
        end: str | datetime | int,
        limit: int = 25,
    ) -> list[dict]:
        """Return up to ``limit`` (url, date) rows for a domain."""
        sql = f"""
            SELECT DocumentIdentifier AS url, DATE AS date
            FROM `{self.table}`
            WHERE SourceCommonName = @domain
              AND DATE BETWEEN @start AND @end
            GROUP BY url, date
            ORDER BY date DESC
            LIMIT @limit
        """
        params = [
            self._bigquery.ScalarQueryParameter("domain", "STRING", domain),
            self._bigquery.ScalarQueryParameter(
                "start", "INT64", _format_gkg_datetime(start)
            ),
            self._bigquery.ScalarQueryParameter(
                "end", "INT64", _format_gkg_datetime(end)
            ),
            self._bigquery.ScalarQueryParameter("limit", "INT64", int(limit)),
        ]
        return [dict(row) for row in self._run(sql, params)]
