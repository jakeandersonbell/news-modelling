# Retrieval Strategy

Status: draft — Phase 1, Task 2
Last updated: initial draft

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
- [ ] Measure GDELT vs. CC-NEWS URL coverage per outlet for the 3-month window.
- [ ] Approach FT / Telegraph research teams for Tier E access.
- [ ] Record the final primary/secondary decision per outlet below.

### Decision log

| Date | Outlet | Decision | Rationale |
|---|---|---|---|
| _TBD_ | _all_ | _pending Task 2 evaluation_ | |
