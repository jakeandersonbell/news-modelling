Extension: Knowledge Graph & Contradiction Engine

Positioning: This is an optional extension to the core application, not a stand-alone delivery phase. It layers a claim-level knowledge graph on top of the working app produced by Phase 2 (Modeling & Application), using the cleaned, chunked corpus from Phase 1. Treat it as post-MVP: build it once the core pipeline, dashboard, and API work end to end. It is documented separately so it can be scoped, deferred, or dropped without affecting the core deliverable.

Objective: Transform the unstructured, cleaned text from Phase 1 into a structured knowledge graph prototype using LLMs. This extension focuses on extracting entities, mapping relationships (claims and provenance), and solving entity resolution on a targeted subset of the data before any full-scale processing.

Guiding principle: Prioritize schema strictness over extraction volume. The LLM must adhere rigidly to the predefined epistemic ontology ([Source] -> [CLAIMS] -> [Statement]) to ensure the resulting graph is programmatically queryable, minimizing hallucinations, generic nodes, and untyped edges.

Task 1: Graph Schema & Ontology Definition

Define the strict blueprint for how news events, entities, and journalistic claims will be modeled.

[ ] Define Node Types: Establish core entities explicitly required for the use case, such as Source, Event, Person, Organization, Location, and Statement.

[ ] Define Edge Types: Establish rigid relationship connections such as REPORTS_ON, CLAIMS, INVOLVES, and CONTRADICTS.

[ ] Document Ontology: Create a reference configuration (e.g., config/schema.yaml) to guide the LLM extraction prompts and graph database constraints.

Task 2: LLM Extraction Pipeline Setup

Build the prompt chains and tools to convert raw text chunks into graph structures.

[ ] Select LLM & Framework: Set up LangChain's LLMGraphTransformer (or a similar structured output framework) combined with a highly capable instruction-following LLM (e.g., GPT-4o or Claude 3.5 Sonnet) for the initial prototype.

[ ] Chunking Strategy: Implement semantic text chunking (e.g., splitting by paragraphs or natural structural breaks) to ensure the LLM receives enough context to extract claims accurately without losing focus or dropping entities.

[ ] Prompt Engineering: Design few-shot prompts that enforce the schema. Explicitly instruct the LLM to model reporting rather than absolute truth (focusing on who claimed what, rather than verifying the fact itself).

Task 3: Entity Resolution & Canonicalization (The Deduplication Engine)

Address the critical bottleneck of fragmented graph nodes (e.g., ensuring "The Prime Minister", "PM", and "Keir Starmer" resolve to the same node).

[ ] Vector Similarity Matching: Implement a pre-ingestion step where newly extracted nodes are embedded and compared against existing nodes in the graph using cosine similarity.

[ ] LLM-Assisted Merging: Build an agentic check that triggers when similarity is high (e.g., >0.85), asking a lightweight LLM to verify if the two nodes represent the exact same entity within the current context.

[ ] Cypher Merge Logic: Write the graph database queries to merge verified identical nodes and re-route their existing edges so no connections are lost.

Task 4: Graph Database Deployment & Ingestion

Deploy the storage layer and push the structured, deduplicated data into it.

[ ] Provision Graph DB: Set up a local Neo4j instance or Neo4j AuraDB workspace.

[ ] Apply DB Constraints: Enforce uniqueness constraints and indexes on node properties (e.g., Source_URL, Entity_Name) to prevent basic duplicates at the database level and speed up querying.

[ ] Ingest Extracted Data: Pipe the validated output from Task 2 and Task 3 into the database, verifying that the Nodes and Edges populate correctly without schema violations. Document pipeline in scripts/ingest_to_graph.py.

Task 5: Contradiction Engine Proof of Concept (PoC)

Prove the core thesis by writing queries to surface conflicting claims on the exact same event.

[ ] Cypher Query Development: Write structural queries to find pattern overlaps. (e.g., Find where (Source A)-[:CLAIMS]->(Statement 1)-[:ABOUT]->(Event X) AND (Source B)-[:CLAIMS]->(Statement 2)-[:ABOUT]->(Event X)).

[ ] Conflict Evaluation Agent: Pass the retrieved Statement 1 and Statement 2 back to an LLM evaluator to classify if they logically contradict, diverge in sentiment, or report completely different metrics.

[ ] Output Synthesis: Generate a structured markdown table or JSON payload visualizing the discovered contradictions (Source A vs Source B on Event X) for human review and validation.
