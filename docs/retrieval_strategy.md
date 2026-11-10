# Retrieval Strategy

Status: draft — Phase 1, Task 2
Last updated: 2026-11-01 (GDELT retrieval-path decision recorded)

This document defines how content is retrieved for each target outlet in
`config/sources.json`, with a deliberate focus on **legitimate and reproducible
access**. It is the reference point for Task 3 (Ingestion & Scraping Pipeline).

## 1. Guiding principles

The dataset underpins media-plurality and framing analysis, so its credibility
depends on access that is defensible and citable. The project therefore works to
these rules:

1. **Prefer official and licensed routes over scraping.** Where an outlet or a
   licensed aggregator offers an API or subscription, use it. It is more stable,
   more reproducible, and legally clean.
2. **No circumvention.** We do not bypass paywalls, authentication, or anti-bot
   systems (no cache/archive paywall tricks, no proxy rotation to defeat blocks,
   no CAPTCHA solving, no spoofed credentials). This is a hard boundary; it
   breaches terms of service and, for authentication, may be unlawful.
3. **Crawl politely where content is openly accessible.** Respect `robots.txt`,
   identify honestly, rate-limit, and back off on errors (see §4).
4. **Prefer bulk/archival corpora for history.** GDELT and CC-NEWS avoid live
   crawling of historical content entirely and are the default for the 3-month
   backfill.
5. **Record provenance.** Every article row should be traceable to its retrieval
   method (see `data_dictionary.md` — to be created in Task 4).

## 2. Access tiers

| Tier | Description | Example |
|---|---|---|
| A — Official API | Publisher-provided, licensed, full text | Guardian Open Platform |
| B — Bulk / archival corpus | Pre-collected datasets | Common Crawl (CC-NEWS), GDELT |
| C — Polite live crawl | Openly accessible web pages via RSS discovery + `trafilatura` | BBC, Mirror |
| D — Licensed aggregator | Library/institutional subscription | Factiva, Nexis, ProQuest |
| E — Direct agreement | Outlet grants research access | FT/Telegraph press teams |

Tiers A–B are preferred; C is acceptable for open content; D–E are the route for
paywalled outlets.

## 3. Per-outlet plan

Primary / secondary / fallback retrieval by outlet. `access` is mirrored in
`config/sources.json`.

| Outlet | Access | Primary | Secondary | Fallback |
|---|---|---|---|---|
| BBC News | Open | C — RSS + trafilatura | B — CC-NEWS | GDELT URLs |
| Reuters | Open | C — RSS + trafilatura | B — CC-NEWS | GDELT URLs |
| The Guardian | Open | **A — Guardian Open Platform API** | C — RSS + trafilatura | B — CC-NEWS |
| The Daily Telegraph | Paywalled | **D — licensed aggregator (Factiva/Nexis/ProQuest)** | E — direct research access | B — GDELT/CC-NEWS metadata + lede only |
| Daily Mail | Open | C — RSS + trafilatura | B — CC-NEWS | GDELT URLs |
| The Mirror | Open | C — RSS + trafilatura | B — CC-NEWS | GDELT URLs |
| Politico EU | Open | C — RSS + trafilatura | B — CC-NEWS | GDELT URLs |
| Financial Times | Paywalled | **D — licensed aggregator (Factiva/Nexis)** | E — FT licensed/content API | B — GDELT/CC-NEWS metadata + lede only |

Notes:
- The **Guardian Open Platform API** is free and returns full article text — it
  replaces scraping for that outlet and should be the first integration proof.
- **Paywalled outlets (Telegraph, FT) are retained deliberately** as an exercise
  in sourcing their content through legitimate means. Until a Tier D/E route is
  secured, they contribute **metadata only** (via GDELT/CC-NEWS): title, URL,
  date, and any freely available lede. Full-text framing analysis for these two
  is therefore deferred and flagged as a known limitation, not worked around by
  circumvention.

### CC-NEWS retrieval path (Task 2 finding)

The **Common Crawl CC-NEWS** corpus was measured for the 3-month window
(2024-01..03):

- WARC files are size-capped at **~1.07 GB** each, holding ~20.5k response
  records (~19 records/MB). The full window is **1,724 files ≈ 1.85 TB**.
- **There is no CDX index for CC-NEWS.** The public CDX API serves only
  `CC-MAIN-*` collections (`collinfo.json` lists none starting `CC-NEWS-`); a
  query for `CC-NEWS-YYYY-MM-index` returns `404 "No index found for collection"`.
  The CDX/ranged-fetch helpers in `cc_news_parser.py` therefore raise
  `CCNewsIndexError` against the live service and are retained only as a
  forward-compatible stub.
- Because there is no index, locating a target outlet's articles means **streaming
  WARC files and filtering by domain**, reading each record's `WARC-Target-URI`
  header. In a probe (63 MB slice of one file, ~1,200 records) only **5 articles**
  matched any of 8 target UK/EU news domains (Daily Mail ×4, Mirror ×1).

**How to get "one site's pages" cheaply.** A WARC file is a gzip stream of records
mixed across *all* sites, ordered only by crawl time. Each `response` record's
identity (`WARC-Target-URI`, `WARC-Date`, `WARC-Type`) lives in its **headers**, so
you can filter a site's pages without downloading the HTML bodies: stream the file,
read headers, compare the domain, and only `read()` the body of matching records.
The endpoint supports HTTP `Range` requests, so the stream can be bounded
(`stream_warc(..., max_bytes=...)`) or progressively extended.

**Consequence:** `stream_warc(..., domain_filter=...)` (stream → header-filter by
domain → read only matching bodies) is the **primary** CC-NEWS path. The efficient
per-article ranged fetch depends on the **columnar index** (`cc-index` on
`data.commoncrawl.org`/Athena), which *does* cover CC-NEWS but is a heavier,
separate dependency — noted as the escalation path if/when full-window text
extraction is required. The end-to-end route (stream → `warcio` parse →
`trafilatura` text) was validated on a real WARC, yielding clean article text
(e.g. a 2,771-char Daily Mail piece from a 63 MB slice).

### GDELT retrieval path (Task 2 finding)

The **GDELT DOC 2.0 API** was evaluated and **rejected as a primary route**. It is
rate-limited by IP — observed returning `HTTP 200` with a *plain-text throttle
notice* instead of JSON on every request from our test environment, even when
spaced well beyond the stated 5-second interval — and it caps at 250 records per
query and only covers roughly the last 3 months, so it cannot serve a defined
historical window. GDELT is therefore accessed via the **public BigQuery dataset**
(`gdelt-bq`, Global Knowledge Graph table), which yields exact per-outlet article
counts and URLs for any window and counts all outlets in a single scan.
Implementation: `src/data_retrieval/gdelt_bigquery.py`. The DOC API client
(`gdelt_client.py`) is retained only as a best-effort convenience.

### Division of labour: GDELT vs CC-NEWS (Task 2 decision)

The natural-seeming pipeline — **"GDELT supplies the metadata, then fetch the
article text from CC-NEWS using that metadata"** — was evaluated and **rejected as
the primary path**. The two corpora are used **in parallel**, not chained:

| Need | Source | Method |
|------|--------|--------|
| Per-outlet **volume** & coverage sanity-check | GDELT GKG (BigQuery) | one scan, exact distinct-URL counts |
| **Which URLs** to fetch (the content universe) | CC-NEWS **WARC streaming** (`stream_warc`) | header-filter by domain over each month's files |
| **Full article text** | CC-NEWS WARC | `stream_warc` (read matching bodies) → `trafilatura` |
| Paywalled (Telegraph, FT) full text | Tier D/E only | metadata + lede otherwise |

*(The efficient per-article ranged fetch is only available via the columnar index
`cc-index`/Athena — see the CC-NEWS section above — and is not yet implemented.)*

**Why not "GDELT → CC-NEWS"?** The hand-off is a *lossy URL join*:

1. GDELT records **canonical/live** URLs; CC-NEWS records **as-crawled** URLs.
   They diverge on `www.`/`m.`/`amp.` prefixes, trailing slashes, redirects,
   query params, and shortened links. A normalised match (`normalize_url`) shrinks
   but does not close this gap — some fraction of GDELT URLs will never join to a
   CC-NEWS capture.
2. The join is **redundant**: locating an article in CC-NEWS does not require
   GDELT's URL at all — CC-NEWS's own records carry `WARC-Target-URI` directly,
   discovered by streaming. Bringing GDELT into the loop adds a match step that
   can only lose articles.
3. It costs **both** a BigQuery scan **and** a streaming pass, then still loses the
   articles that fail to join.

The two sources answer *different questions*. GDELT's GKG is clean, deduplicated,
and editorialized (themes, tone) — ideal for the **volume** question Task 2 asks
("how many articles per outlet, any gaps?"). CC-NEWS is the raw crawl — ideal for
the **content** question ("give me the full text"). Chaining them conflates the two
and adds a fragile join for no benefit.

The **only** legitimate use of a GDELT→CC-NEWS join is a **cross-check / backfill**:
if CC-NEWS under-crawls an outlet (e.g. `mirror.co.uk`), GDELT's URL list can be
fetched against CC-NEWS (or Wayback) by normalised URL. This is a rare fallback,
measured in `notebooks/01_source_evaluation.ipynb`, not the default.

## 4. Sensible crawling rules (Tier C)

For openly accessible outlets only:

- **`robots.txt`**: fetch and honour it per host; never request disallowed paths.
- **Identification**: a single, honest, contactable `User-Agent`
  (e.g. `newsmodelling-research/0.1 (+mailto:…)`). Do not impersonate browsers
  or rotate identities to evade detection.
- **Rate limiting**: conservative per-host delay (e.g. 1 req/sec/host, configurable
  in `config/pipeline_config.yaml`) with a global concurrency cap.
- **Backoff**: exponential backoff on 429/503; respect `Retry-After`; abandon a
  host after repeated failures rather than retrying aggressively.
- **Caching**: never re-fetch a URL already stored (dedupe by URL hash) to
  minimise load.
- **Conditional requests**: send `If-Modified-Since` / `ETag` where useful.
- **Scope**: only fetch article pages discovered via RSS/GDELT, not site-wide
  crawling.

## 5. Legal & policy notes

- Public-page scraping sits in a tolerated grey area (cf. US *hiQ v. LinkedIn*)
  but is still subject to each site's terms of service. Circumventing paywalls or
  authentication is a materially higher risk and is out of scope here.
- Research text-and-data-mining exceptions (e.g. EU DSM Directive Arts. 3–4,
  and the narrower UK exception) may permit certain non-commercial research use;
  scope and applicability must be confirmed before relying on them.
- Institutional library access (Tier D) is the standard academic route for
  paywalled news and is the recommended path for Telegraph/FT.

## 6. Open decisions (Task 2 to close)

- [ ] Confirm whether institutional (library) access to Factiva/Nexis/ProQuest
      is available — this determines whether Telegraph/FT stay full-text.
- [ ] Test Guardian Open Platform API coverage vs. the RSS feed for the target
      window.
- [ ] Measure GDELT (via BigQuery) vs. CC-NEWS URL coverage per outlet for the
      3-month window.
- [ ] Authenticate BigQuery (`gcloud auth application-default login` +
      `GOOGLE_CLOUD_PROJECT`) and run the coverage comparison in
      `notebooks/01_source_evaluation.ipynb`.
- [ ] Approach FT / Telegraph research teams for Tier E access.
- [ ] Record the final primary/secondary decision per outlet below.

### Decision log

| Date | Outlet | Decision | Rationale |
|---|---|---|---|
| 2026-11-01 | _all_ | GDELT accessed via public BigQuery (`gdelt-bq` GKG), not the DOC API | DOC API is IP-throttled (plain-text 200 responses), capped at 250 records, and limited to ~3 recent months — cannot serve a defined historical window |
| 2026-11-01 | _all_ | CC-NEWS primary = WARC streaming with header-level domain filtering (`stream_warc`); there is **no CDX index** | `index.commoncrawl.org/CC-NEWS-*-index` returns 404 "No index found"; files ~1.07 GB each (window ≈ 1.85 TB), mixed across sites, so identity (URL/domain) is read from each record's headers and only matching bodies are downloaded; columnar index (Athena) is the escalation path |
| 2026-11-01 | _all_ | GDELT & CC-NEWS run **in parallel**, not chained (no "GDELT metadata → CC-NEWS text" hand-off) | The join is a lossy URL match (canonical vs as-crawled URLs) and redundant — CC-NEWS records carry their own `WARC-Target-URI` (discovered by streaming), so a cross-corpus join can only lose articles; the join is a cross-check/backfill only |
| _TBD_ | _all_ | _pending GDELT-vs-CC-NEWS coverage comparison_ | |
