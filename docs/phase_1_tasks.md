Phase 1: Data Foundation & Curation

Objective: Collate a robust, high-quality data sample covering 5-10 distinct news outlets over a continuous 3-month period. This dataset must contain a wide variance of topics, content lengths, and political perspectives to serve as the ground truth for developing the NLP pipeline and training classifiers.

Task 1: Outlet Curation & Coverage Matrix

Define the target sources to ensure maximum diversity across the political and stylistic spectrum.

[ ] Select 5-10 Target Outlets: Choose a mix of traditional broadsheets, tabloids, and digital-native publishers. Each must cover UK 
and international news.

[ ] Map the Political Spectrum: Ensure deliberate inclusion of left-leaning, centrist, and right-leaning publications (e.g., cross-referencing with AllSides or Ad Fontes media bias charts).

[ ] Verify Content Diversity: Ensure the selected outlets produce a mix of hard news (geopolitics, macroeconomics), opinion/editorial pieces, and localized/niche reporting to test the macro and micro classifiers.

[ ] Document the Matrix: Create a configuration file (e.g., config/sources.json) mapping each outlet to its base URLs, expected political baseline, and geographic region.

Task 2: Data Source Evaluation & Retrieval Strategy

Determine the most efficient method for retrieving the 3-month historical window for the selected outlets.

[ ] Evaluate GDELT: Query the GDELT BigQuery database or raw CSVs for the target 3-month window. Assess the volume of URLs available for the selected 5-10 outlets.

[ ] Evaluate Common Crawl (CC-NEWS): Check the CC-NEWS WARC index for the specific 3-month period. Assess the parsing overhead versus the coverage provided.

[ ] Evaluate Direct/Historical Scraping: If GDELT/CC-NEWS coverage is patchy for specific outlets, investigate using the Wayback Machine CDX API or scraping historical RSS feed aggregators for fallback URLs.

[ ] Finalize Strategy: Decide on the primary and secondary retrieval methods and document the decision.

Task 3: Ingestion & Scraping Pipeline

Build the scripts to fetch raw HTML based on the URLs gathered in Task 2.

[ ] Develop Fetcher Script: Write an asynchronous Python script (using aiohttp or httpx) to download HTML from the collated URLs. Implement polite rate-limiting and user-agent rotation.

[ ] Integrate trafilatura: Implement the trafilatura library to parse the raw HTML, extract the core article text, and strip away navigation, ads, and footers.

[ ] Error Handling: Build robust logging to track failed downloads, paywall blocks, or empty text extractions.

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