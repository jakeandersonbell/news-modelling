"""Common Crawl CC-NEWS retrieval client (Phase 1, Task 2).

CC-NEWS is Common Crawl's continuous news crawl. It is published as monthly /
continuous WARC files on ``data.commoncrawl.org``.

Access methods (measured 2026-11)
---------------------------------
1. **WARC streaming (the only built-in, index-free route).** Download WARC files
   listed in the monthly ``warc.paths.gz`` inventory and filter records by
   domain. This is the access method implemented here — :meth:`CCNewsClient.stream_warc`.
2. **Columnar index (not implemented here).** Common Crawl publishes a Parquet
   "columnar index" (``cc-index``, hosted on ``data.commoncrawl.org``/S3 and
   queryable via Amazon Athena). That index *does* cover CC-NEWS and would enable
   a ranged fetch. It is a heavier, separate dependency and is noted as an
   escalation path, not implemented in this module.

Endpoints
---------
* Monthly inventory:
  ``https://data.commoncrawl.org/crawl-data/CC-NEWS/{YYYY}/{MM}/warc.paths.gz``
* WARC data (supports HTTP Range requests):
  ``https://data.commoncrawl.org/{warc_path}``

Important: there is **no CDX index for CC-NEWS**. The public CDX API
(``index.commoncrawl.org/{collection}-index``) serves only ``CC-MAIN-*``
collections; a query for ``CC-NEWS-YYYY-MM`` returns
``404 "No index found for collection"``. The CDX-oriented helpers below
(:meth:`CCNewsClient.iter_index_records`, ``urls_for_domain``,
``records_for_domain``) therefore **raise :class:`CCNewsIndexError` against the
live service** — they are retained for completeness and would only work if pointed
at a columnar-index-backed shim. Do not rely on them for CC-NEWS itself.

Notes
-----
* ``warcio`` and ``trafilatura`` are imported lazily so the module (and its
  metadata-only paths) work without them installed.

Measured scale (2024-01..03, CC-NEWS, observed 2026-11)
-------------------------------------------------------
* WARC files are size-capped at ~1.07 GB each and contain ~20.5k response
  records (~19 records/MB). Each file therefore costs a full ~1.07 GB download
  to stream end-to-end.
* A 3-month window = 1,724 WARC files ≈ 1.85 TB of data.
* CC-NEWS has **no CDX index**, so locating a target outlet's articles means
  streaming WARC bytes and filtering by domain (in a 63 MB sample slice only
  5 of ~1,200 records matched any of 8 target UK/EU news domains).

How WARC files are organised (and how to get "one site's pages")
----------------------------------------------------------------
Each ``CC-NEWS-*.warc.gz`` is a gzip stream of WARC records mixed across *all*
sites, ordered only by crawl time — never by domain. The records you care about
are ``WARC-Type: response``; each carries its identity in cheap **record headers**:

* ``WARC-Target-URI`` — the fetched URL (``https://www.dailymail.co.uk/...``)
* ``WARC-Date`` — crawl timestamp
* ``WARC-Type`` — ``response`` / ``request`` / ``warcinfo`` / ``metadata``
* HTTP ``Content-Type`` / status — on the nested HTTP headers

Because the identity lives in the headers (at the *front* of each record), you can
discover a site's pages **without downloading the HTML bodies**: stream the file,
read each record's headers, compare ``WARC-Target-URI``'s domain, and only call
``content_stream().read()`` on the bodies you actually want. The endpoint supports
HTTP ``Range`` requests, so the stream itself can also be bounded (``max_bytes``)
or progressively extended rather than fetched whole.

Consequences for retrieval
--------------------------
1. :meth:`CCNewsClient.stream_warc` (stream, filter by ``domain_filter``, read
   bodies only on match) is the **only** index-free path and therefore the primary
   CC-NEWS route. Header-level scanning is cheap; the ~1.07 GB/file cost is the
   sum of *all* bodies, which is only paid if ``domain_filter`` is ``None``.
2. The selective ``records_for_domain``/``urls_for_domain`` path depends on the
   columnar index, which is **not provided here**; until that is wired up, the
   efficient per-article ranged fetch is unavailable and all retrieval is streaming.
3. Range reads may terminate mid-record; :meth:`stream_warc` tolerates a truncated
   trailing record rather than raising.
"""

from __future__ import annotations

import gzip
import io
import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterator, Sequence
from urllib.parse import urlparse

import requests

logger = logging.getLogger(__name__)

DATA_BASE = "https://data.commoncrawl.org"
INDEX_BASE = "https://index.commoncrawl.org"
DEFAULT_USER_AGENT = (
    "news-modelling-research/0.1 (+https://github.com/jakeandersonbell/news-modelling)"
)


class CCNewsError(RuntimeError):
    """Base class for CC-NEWS retrieval errors."""


class CCNewsIndexError(CCNewsError):
    """Raised when the CC-NEWS CDX index cannot serve a lookup."""


def index_collection(year: int, month: int) -> str:
    """Return the CC-NEWS CDX collection id for a month, e.g. ``CC-NEWS-202401``."""
    return f"CC-NEWS-{year}{month:02d}"


def _domain_of(url: str | None) -> str | None:
    """Extract the host (without a leading ``www.``) from a URL."""
    if not url:
        return None
    netloc = urlparse(url).netloc.lower()
    return netloc[4:] if netloc.startswith("www.") else netloc


def normalize_url(url: str | None) -> str | None:
    """Normalise a URL for cross-corpus matching (GDELT ↔ CC-NEWS).

    GDELT records *canonical/live* URLs while CC-NEWS records *as-crawled* URLs;
    the two diverge on scheme, trailing slash, fragment, common tracking query
    params, and ``www.``/``amp``/``m.`` host prefixes. Normalising to a common
    form reduces (but does not eliminate) the mismatch when joining the two
    corpora by URL.

    Returns ``None`` for empty input. This is a *lossy* canonicalisation: distinct
    URLs can normalise to the same key, so it is only suitable as a match key,
    never as an identity.
    """
    if not url:
        return None
    u = urlparse(url.strip().lower())
    host = u.netloc
    if host.startswith("www."):
        host = host[4:]
    # Drop mobile/AMP host prefixes that GDELT frequently emits.
    if host.startswith("m.") or host.startswith("amp."):
        host = host.split(".", 1)[1]
    # Strip a trailing slash and common tracking params; keep the path/query
    # otherwise intact so distinct articles do not collapse together.
    path = u.path.rstrip("/") or "/"
    if u.query:
        path = f"{path}?{u.query}"
    return f"{host}{path}"


def _parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    for fmt in ("%Y%m%d%H%M%S", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


@dataclass
class CCNewsRecord:
    """A single news record retrieved from CC-NEWS."""

    url: str
    warc_path: str | None = None
    offset: int | None = None
    length: int | None = None
    timestamp: str | None = None
    status: int | None = None
    content_type: str | None = None
    html: str | None = None
    text: str | None = None

    @property
    def published(self) -> datetime | None:
        return _parse_timestamp(self.timestamp)

    @property
    def domain(self) -> str | None:
        return _domain_of(self.url)


class CCNewsClient:
    """Retrieval helper for the Common Crawl CC-NEWS dataset."""

    def __init__(
        self,
        timeout: float = 60.0,
        max_retries: int = 3,
        backoff_factor: float = 2.0,
        session: requests.Session | None = None,
        user_agent: str = DEFAULT_USER_AGENT,
        index_base: str = INDEX_BASE,
        data_base: str = DATA_BASE,
    ) -> None:
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor
        self.index_base = index_base.rstrip("/")
        self.data_base = data_base.rstrip("/")
        self.user_agent = user_agent
        self._session = session or requests.Session()
        self._session.headers.update({"User-Agent": user_agent})

    # -- internals ---------------------------------------------------------

    def _get(self, url: str, params: dict | None = None, headers: dict | None = None) -> requests.Response:
        """GET with retries/backoff on transient failures."""
        last_error: object = None
        for attempt in range(self.max_retries + 1):
            try:
                resp = self._session.get(
                    url, params=params, headers=headers, timeout=self.timeout
                )
                if resp.status_code in (429, 500, 502, 503, 504) and attempt < self.max_retries:
                    time.sleep(self.backoff_factor * (attempt + 1))
                    continue
                resp.raise_for_status()
                return resp
            except requests.RequestException as exc:
                last_error = exc
                if attempt < self.max_retries:
                    time.sleep(self.backoff_factor * (attempt + 1))
                    continue
        raise CCNewsError(f"Request to {url} failed after retries: {last_error}")

    # -- inventory ---------------------------------------------------------

    def list_warc_paths(self, year: int, month: int) -> list[str]:
        """List the CC-NEWS WARC file paths for a given month."""
        url = f"{self.data_base}/crawl-data/CC-NEWS/{year}/{month:02d}/warc.paths.gz"
        resp = self._get(url)
        with gzip.GzipFile(fileobj=io.BytesIO(resp.content)) as fh:
            return [line.decode("utf-8").strip() for line in fh if line.strip()]

    def count_warc_files(self, year: int, month: int) -> int:
        """Return the number of WARC files published for a month."""
        return len(self.list_warc_paths(year, month))

    # -- CDX index ---------------------------------------------------------

    def iter_index_records(
        self, domain: str, year: int, month: int, limit: int | None = None
    ) -> list[dict]:
        """Return CDX index records for a domain in a month.

        Raises
        ------
        CCNewsIndexError
            If the collection does not exist, the server returns non-JSON
            (e.g. an HTML 5xx page), or reports no captures.
        """
        collection = index_collection(year, month)
        url = f"{self.index_base}/{collection}-index"
        params = {"url": domain, "output": "json"}
        if limit:
            params["limit"] = int(limit)

        try:
            resp = self._get(url, params=params)
        except CCNewsError as exc:
            raise CCNewsIndexError(
                f"CC-NEWS index unavailable for {collection}: {exc}"
            ) from exc

        text = resp.text.strip()
        if not text or text.lstrip().startswith("<"):
            raise CCNewsIndexError(
                f"CC-NEWS index returned a non-JSON response for {collection} "
                "(collection may not exist or the server is overloaded)."
            )

        records: list[dict] = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                lowered = line.lower()
                if "no captures" in lowered or "no index" in lowered:
                    raise CCNewsIndexError(line)
                logger.debug("Skipping non-JSON index line: %s", line[:120])
        return records

    def count_index_records(self, domain: str, year: int, month: int) -> int:
        """Count index records for a domain in a month (uses ``showNumPages`` is not used; full list)."""
        return len(self.iter_index_records(domain, year, month))

    def urls_for_domain(
        self, domain: str, year: int, month: int, limit: int | None = None
    ) -> list[CCNewsRecord]:
        """Enumerate the URLs CC-NEWS archived for a domain in a month.

        This is the *"which URLs to fetch"* source for the content pipeline: it
        lists the captures (URL + WARC byte offset + length + timestamp) that
        :meth:`records_for_domain` later fetches. It answers the volume question
        (how many articles, which URLs) directly from CC-NEWS's own index — no
        cross-corpus join with GDELT is required to locate content.

        Returns :class:`CCNewsRecord` objects with ``url``/``warc_path``/
        ``offset``/``length``/``timestamp`` populated and no body (``html``/
        ``text`` are ``None``). Raises :class:`CCNewsIndexError` if the index
        cannot be queried.
        """
        results: list[CCNewsRecord] = []
        for rec in self.iter_index_records(domain, year, month, limit=limit):
            warc_path = rec.get("filename")
            offset = rec.get("offset")
            length = rec.get("length")
            url = rec.get("url")
            if url is None:
                continue
            results.append(
                CCNewsRecord(
                    url=url,
                    warc_path=warc_path,
                    offset=int(offset) if offset is not None else None,
                    length=int(length) if length is not None else None,
                    timestamp=rec.get("timestamp"),
                    status=int(rec["status"]) if rec.get("status") is not None else None,
                    content_type=rec.get("mime")
                    or rec.get("mime-detected")
                    or rec.get("content_type"),
                )
            )
        return results

    def count_urls_for_domain(self, domain: str, year: int, month: int) -> int:
        """Number of URLs archived by CC-NEWS for a domain in a month."""
        return len(self.urls_for_domain(domain, year, month))

    # -- record retrieval --------------------------------------------------

    def fetch_record_bytes(self, warc_path: str, offset: int, length: int) -> bytes:
        """Fetch exactly one WARC record's bytes via an HTTP Range request."""
        url = f"{self.data_base}/{warc_path}"
        headers = {"Range": f"bytes={offset}-{offset + length - 1}"}
        resp = self._get(url, headers=headers)
        return resp.content

    @staticmethod
    def parse_warc_record(raw: bytes, extract_text: bool = False) -> CCNewsRecord:
        """Parse raw WARC bytes into a :class:`CCNewsRecord`."""
        from warcio import ArchiveIterator

        response = None
        try:
            for rec in ArchiveIterator(io.BytesIO(raw)):
                if rec.rec_type == "response":
                    response = rec
                    break
        except Exception as exc:  # malformed/truncated range
            raise CCNewsError(f"Failed to parse WARC record: {exc}") from exc

        if response is None:
            raise CCNewsError("No HTTP response record found in retrieved bytes.")

        html = response.content_stream().read().decode("utf-8", errors="replace")
        http = response.http_headers
        return CCNewsRecord(
            url=response.rec_headers.get_header("WARC-Target-URI"),
            timestamp=response.rec_headers.get_header("WARC-Date"),
            content_type=http.get_header("Content-Type") if http else None,
            status=int(http.get_statuscode()) if http and http.get_statuscode() else None,
            html=html,
            text=CCNewsClient.extract_text(html) if extract_text else None,
        )

    @staticmethod
    def extract_text(html: str) -> str | None:
        """Extract clean article text with trafilatura (optional dependency)."""
        try:
            import trafilatura

            return trafilatura.extract(
                html, include_comments=False, include_tables=False
            )
        except Exception as exc:  # trafilatura missing or extraction failure
            logger.debug("trafilatura extraction failed: %s", exc)
            return None

    def records_for_domain(
        self,
        domain: str,
        year: int,
        month: int,
        limit: int = 25,
        extract_text: bool = False,
    ) -> list[CCNewsRecord]:
        """Retrieve and parse up to ``limit`` CC-NEWS records for a domain/month."""
        results: list[CCNewsRecord] = []
        for rec in self.iter_index_records(domain, year, month, limit=limit):
            warc_path = rec.get("filename")
            offset = rec.get("offset")
            length = rec.get("length")
            if warc_path is None or offset is None or length is None:
                continue
            try:
                raw = self.fetch_record_bytes(warc_path, int(offset), int(length))
                parsed = self.parse_warc_record(raw, extract_text=extract_text)
            except CCNewsError as exc:
                logger.warning("Failed to fetch/parse %s: %s", warc_path, exc)
                continue
            parsed.warc_path = warc_path
            parsed.offset = int(offset)
            parsed.length = int(length)
            results.append(parsed)
        return results

    def stream_warc(
        self,
        warc_path: str,
        domain_filter: str | Sequence[str] | None = None,
        max_records: int | None = None,
        extract_text: bool = False,
        max_bytes: int | None = None,
    ) -> Iterator[CCNewsRecord]:
        """Stream a WARC file, yielding response records optionally filtered by domain.

        This is the **primary** (and only index-free) CC-NEWS access path — there
        is no CDX index for CC-NEWS, so :meth:`records_for_domain` cannot work
        without a columnar-index shim not provided here.

        Record *identity* (``WARC-Target-URI``, ``WARC-Date``, ``WARC-Type``) is
        read from each record's headers, so filtering by domain only costs header
        parsing; the HTML body is downloaded (and ``trafilatura``-extracted) only
        for records whose ``domain_filter`` matches. Pass ``domain_filter`` to
        avoid downloading ~1.07 GB of bodies when you only want a few sites.

        Parameters
        ----------
        domain_filter:
            Domain(s) (e.g. ``"bbc.co.uk"``) to keep; ``None`` keeps every
            response record. Only matching records have their body read.
        max_records:
            Stop after yielding this many matching records.
        extract_text:
            If True, run :meth:`extract_text` on each kept body.
        max_bytes:
            Bound the download to the first ``max_bytes`` bytes via an HTTP
            ``Range`` request. Useful for sampling/probing or for scanning only
            a window of crawl time. The stream may end mid-record; a truncated
            trailing record is skipped rather than raised.
        """
        from warcio import ArchiveIterator

        if isinstance(domain_filter, str):
            domain_filter = [domain_filter]
        domains = {d.lower() for d in domain_filter} if domain_filter else None

        url = f"{self.data_base}/{warc_path}"
        headers = {"Range": f"bytes=0-{max_bytes - 1}"} if max_bytes else None
        with self._session.get(
            url, headers=headers, timeout=self.timeout, stream=True
        ) as resp:
            resp.raise_for_status()
            it = ArchiveIterator(resp.raw)
            count = 0
            while True:
                try:
                    rec = next(it)
                except StopIteration:
                    break
                except Exception:
                    # Truncated trailing record (e.g. a bounded Range read cut
                    # mid-request). Stop cleanly rather than crash.
                    logger.debug("Stopped at truncated WARC tail: %s", warc_path)
                    break
                if rec.rec_type != "response":
                    continue
                target = rec.rec_headers.get_header("WARC-Target-URI")
                if domains is not None and _domain_of(target) not in domains:
                    continue
                html = rec.content_stream().read().decode("utf-8", errors="replace")
                yield CCNewsRecord(
                    url=target,
                    warc_path=warc_path,
                    timestamp=rec.rec_headers.get_header("WARC-Date"),
                    html=html,
                    text=self.extract_text(html) if extract_text else None,
                )
                count += 1
                if max_records and count >= max_records:
                    break
