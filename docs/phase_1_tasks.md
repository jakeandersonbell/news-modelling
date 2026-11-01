Phase 1: Data Foundation & Curation

Objective: Collate a robust, high-quality data sample covering 5-10 distinct news outlets over a continuous 3-month period. This dataset must contain a wide variance of topics, content lengths, and political perspectives to serve as the ground truth for developing the NLP pipeline and training classifiers.

Guiding principle: All content is collected through legitimate and reproducible means — official/licensed APIs, bulk archival corpora (GDELT/CC-NEWS), polite crawling of openly accessible pages, or licensed aggregators. Paywalls, authentication, and anti-bot controls are never circumvented. See docs/retrieval_strategy.md.

Task 1: Outlet Curation & Coverage Matrix

Define the target sources to ensure maximum diversity across the political and stylistic spectrum.

[x] Select 5-10 Target Outlets: Choose a mix of traditional broadsheets, tabloids, and digital-native publishers. Each must cover UK 
and international news.

[x] Map the Political Spectrum: Ensure deliberate inclusion of left-leaning, centrist, and right-leaning publications (e.g., cross-referencing with AllSides or Ad Fontes media bias charts).

[x] Verify Content Diversity: Ensure the selected outlets produce a mix of hard news (geopolitics, macroeconomics), opinion/editorial pieces, and localized/niche reporting to test the macro and micro classifiers.

[x] Document the Matrix: Create a configuration file (e.g., config/sources.json) mapping each outlet to its base URLs, expected political baseline, and geographic region.

Task 2: Data Source Evaluation & Retrieval Strategy

Determine the most efficient method for retrieving the 3-month historical window for the selected outlets.

[ ] Evaluate GDELT: Query the GDELT BigQuery database or raw CSVs for the target 3-month window. Assess the volume of URLs available for the selected 5-10 outlets.

[ ] Evaluate Common Crawl (CC-NEWS): Check the CC-NEWS WARC index for the specific 3-month period. Assess the parsing overhead versus the coverage provided.

[ ] Evaluate Direct/Historical Scraping: If GDELT/CC-NEWS coverage is patchy for specific outlets, investigate using the Wayback Machine CDX API or scraping historical RSS feed aggregators for fallback URLs.

[ ] Evaluate Legitimate Access Routes for Paywalled Outlets: For the paywalled publishers retained in the set (The Daily Telegraph, Financial Times), assess legitimate means of collection — official/licensed APIs, institutional library access to aggregators (Factiva/Nexis/ProQuest/Gale/PressReader), and direct research-access agreements. Confirm whether full text is obtainable without circumventing paywalls; otherwise fall back to metadata + freely available lede only. Document findings in docs/retrieval_strategy.md.

[ ] Finalize Strategy: Decide on the primary, secondary, and fallback retrieval methods per outlet and document the decision — including the ethical/legal basis for each — in docs/retrieval_strategy.md and the decision log. Mirror the per-outlet access and retrieval fields in config/sources.json.

Task 3: Ingestion & Scraping Pipeline

Build the scripts to fetch raw HTML based on the URLs gathered in Task 2.

[ ] Develop Fetcher Script: Write an asynchronous Python script (using aiohttp or httpx) to download HTML from the collated URLs. Implement polite rate-limiting and a single, honest, contactable User-Agent (no impersonation or identity rotation to evade detection).

[ ] Implement Sensible & Compliant Crawling: Fetch and honour robots.txt per host, apply conservative per-host rate limits with exponential backoff and Retry-After handling, cache/skip already-fetched URLs, and scope crawling to article pages discovered via RSS/GDELT. Explicitly do not bypass paywalls, authentication, or anti-bot controls.

[ ] Integrate trafilatura: Implement the trafilatura library to parse the raw HTML, extract the core article text, and strip away navigation, ads, and footers.

[ ] Error Handling: Build robust logging to track failed downloads, paywall blocks, robots.txt disallowals, rate-limit responses, and empty text extractions — recording gaps rather than working around them.

Task 4: Data Cleaning & Structuring

Standardize the scraped data into a clean, queryable format for the ML pipeline.

[ ] Schema Enforcement: Structure the output into a uniform format (e.g., Parquet or JSON-lines) containing fields: article_id, outlet, publish_date, url, raw_text, title, and author.

[ ] Deduplication: Implement exact and fuzzy deduplication (e.g., MinHash/LSH) to remove syndicated articles (e.g., standard Reuters wire reports published across multiple target sites) to prevent skewed clustering.

[ ] Text Normalization: Handle encoding errors, strip residual HTML tags, and standardize whitespace.

Task 5: Exploratory Data Analysis (EDA) & Validation

Verify that the collected dataset meets the requirements for pipeline development.

[ ] Volume Analysis: Generate summary statistics: Total articles per outlet, average articles per day, and text length distributions.

[ ] Diversity Check (Topics): Run a basic TF-IDF + K-Means or zero-shot classifier over a random sample to ensure a wide spread of macro-topics (politics, sports, finance) is present.

[ ] Output EDA Report: Document findings in notebooks/01_eda_and_retrieval.ipynb and confirm whether the dataset is ready for Phase 2 (Modeling Prototypes).
