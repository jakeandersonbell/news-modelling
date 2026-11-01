# News Modelling Project Specification

## 1. Executive Summary
This project retrieves, processes, and analyzes news article data to quantify and track narrative trends, media plurality, and editorial framing. By applying a pipeline of Natural Language Processing (NLP) models at both the document and sub-document (chunk) level, the system extracts structural metadata from unstructured text. This data drives a live interactive dashboard and API, enabling users to link perspectives across different providers reporting on the same micro-events.

## 2. Data Sources & Ingestion
To circumvent the rate limits and historical caps of commercial APIs, data retrieval operates in batches utilizing open sources and custom scrapers:
*   **Event Metadata & Discovery:** GDELT (Global Database of Events, Language, and Tone) for high-level event detection, metadata extraction, and target URL discovery via BigQuery or CSV dumps.
*   **Historical Backfilling:** Common Crawl (CC-NEWS) for populating historical datasets.
*   **Targeted Scraping:** An asynchronous Python scraping pipeline targeting specific RSS feeds, utilizing the `trafilatura` library to extract clean article text and strip out boilerplate (navigation bars, ads, cookie banners).

## 3. NLP Modeling Objectives & Methodology
The analytical engine extracts metrics across macro and micro levels, leveraging chunk-based analysis to surface perspective divergence.

*   **Unit of Analysis (Chunking):** Articles are segmented into smaller semantic units (sentences or paragraphs with high named-entity density). This allows for cross-document linking using cosine similarity to map how different providers frame the exact same micro-event.
*   **News Topic (Macro):** Categorizing articles into broad thematic verticals using an IPTC standard classifier.
*   **News Story (Micro):** Grouping distinct articles and chunks discussing the same real-world event.
    *   *Method:* Online Agglomerative Clustering with a 2-3 day active sliding window to represent the "story center."
    *   *Weighting:* Document/chunk embeddings weighted with TF-IDF to penalize journalistic boilerplate.
    *   *Lifecycle:* Stories can remain dormant for up to a week before being closed. Event similarity is subsequently calculated to capture broader story themes.
*   **Geographic Orientation:** Resolving the primary regional focus of the text.
    *   *Method:* Bypassing standard NER (which struggles with political metonyms like "Westminster"). Instead, utilizing LLM-labeling (e.g., Llama 3 8B) to generate an ISO region-coded training set, followed by fine-tuning a fast encoder (e.g., RoBERTa) for batch inference.
*   **Political Leaning:** Assessing the editorial framing and journalistic bias.
    *   *Method:* Distant supervision utilizing datasets like the Media Bias Information Capsule (MBIC) or labels scraped from media watchdogs (Ad Fontes/AllSides). Strictly avoiding political speech data (e.g., Hansard) to ensure the model captures subtle journalistic framing rather than overt rhetoric.
*   **Target-based Sentiment (ABSA):** Isolating specific entities (politicians, organizations) and measuring localized sentiment directed toward them.
    *   *Method:* Utilizing frameworks like PyABSA, applying Parameter-Efficient Fine-Tuning (QLoRA), or employing dependency parsing (e.g., spaCy) to syntactically map opinion-bearing words directly to target entities.

## 4. System Architecture & Pipeline
*   **Data Retrieval:** Asynchronous ingestion scripts handling RSS/GDELT polling and HTML parsing.
*   **Preprocessing & Chunking:** Text normalization, deduplication, and semantic segmentation for granular analysis.
*   **Inference Engine:** Batch execution of the classification, clustering, and ABSA models against the processed chunks. 
*   **Storage:** Relational database or analytical warehouse holding raw text, embeddings, and relational links between providers.
*   **Presentation:** A live, interactive dashboard and API serving time-series visualizations, media plurality metrics, and cross-provider narrative comparisons.

## 5. Repository Structure

root/
├── config/
│   ├── pipeline_config.yaml         # Hyperparameters, sliding window thresholds, API keys
│   └── sources.json                 # Target RSS feeds, GDELT parameters, watchdog labels
├── data/
│   ├── raw/                         # Raw ingested HTML/WARC files (gitignored)
│   └── processed/                   # Cleaned, chunked datasets ready for inference (gitignored)
├── docs/
│   ├── spec.md                      # Project specification
│   ├── phase_1_tasks.md             # Phase 1 task breakdown
│   ├── extension_knowledge_graph.md # Optional knowledge graph / contradiction extension
│   └── data_dictionary.md           # Schema for final modeled outputs and embeddings
├── notebooks/
│   ├── 01_ingestion_trafilatura.ipynb # Testing RSS/GDELT and text extraction
│   └── 02_agglomerative_tuning.ipynb  # Tuning TF-IDF weights and clustering thresholds
├── src/
│   ├── data_retrieval/
│   │   ├── rss_scraper.py           # Async Trafilatura scraper
│   │   ├── gdelt_client.py          # BigQuery/CSV ingestion
│   │   └── cc_news_parser.py        # Common Crawl WARC processor
│   ├── preprocessing/
│   │   ├── cleaner.py               # HTML stripping, standardizing encodings
│   │   └── chunking_utils.py        # Semantic segmentation and entity-density scoring
│   ├── modeling/
│   │   ├── iptc_classifier.py       # Macro topic modeling
│   │   ├── story_clustering.py      # Online agglomerative pipeline (sliding window)
│   │   ├── geographic_encoder.py    # LLM-distilled geographic orientation
│   │   ├── political_framing.py     # Distant supervision bias classifier
│   │   └── absa_sentiment.py        # Target-based sentiment and dependency parsing
│   ├── evaluation/
│   │   └── metrics.py               # F1 scoring, silhouette scores for clusters
│   └── presentation/
│       ├── plurality_aggregator.py  # Cross-document linking and perspective divergence
│       ├── api_endpoints.py         # Backend API routes for the dashboard
│       └── dashboard.py             # Interactive UI (e.g., Streamlit/Dash)
├── tests/
│   ├── test_clustering.py
│   └── test_extraction.py
├── .gitignore
├── pyproject.toml                   # Python dependencies and build system
└── README.md


## 6. Success Criteria & Evaluation
*   **Throughput:** Pipeline supports batch processing of high-volume daily news cycles within available compute constraints.
*   **Clustering Cohesion:** Online agglomerative clustering maintains high precision on micro-events without semantic drift over the 1-week dormancy period.
*   **Plurality Detection:** System successfully links cross-provider chunks discussing the same target event, surfacing quantifiable divergence in political leaning or target-based sentiment.
*   **Accuracy:** Geographic and Political Leaning models achieve target F1 scores against human-annotated gold-standard evaluation sets.

## 7. Phased Delivery

Work is organised into two core phases followed by an optional extension.

*   **Phase 1 — Data Foundation & Curation.** Collate a high-quality, multi-outlet, 3-month corpus spanning topic and political diversity. This dataset is the ground truth for developing the pipeline and training classifiers. Task breakdown: [docs/phase_1_tasks.md](phase_1_tasks.md).
*   **Phase 2 — Modeling & Application.** Implement the models in §3 and the pipeline and presentation layers in §4 as a working application (dashboard + API), built on top of the Phase 1 dataset.
*   **Extension — Knowledge Graph & Contradiction Engine (optional, post-MVP).** Layered on top of the working application, this extension builds a claim-level knowledge graph (`[Source] -> [CLAIMS] -> [Statement]`) to surface cross-provider contradictions. It is deliberately kept off the critical path and can be scoped, deferred, or dropped without affecting the core deliverable. Notes: [docs/extension_knowledge_graph.md](extension_knowledge_graph.md).