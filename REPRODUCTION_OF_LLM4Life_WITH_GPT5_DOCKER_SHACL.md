---

# Reproduction of LLM4Life with GPT-5, Docker & SHACL

Extends the NeOn-GPT pipeline to reproduce the LLM4Life ontology learning experiments
using OpenAI GPT-5, containerised validation, and embedding-based semantic evaluation
against the AquaDiva gold standard.

---

## 1. AI-Driven Ontology Generation

- Uses the OpenAI API (`gpt-5.4-mini` by default; switch to `gpt-5.4` for a larger context window).
- Prompts are loaded from `Prompts.json` (AppendixB section) and filled with domain-specific placeholders (persona, keywords, few-shot examples, etc.).
- The pipeline runs iteratively across all prompt variants:
  1. Generate ontology draft via LLM.
  2. Validate the draft (syntax → SHACL → pitfalls → OOPS).
  3. Feed the full validation report back into the next LLM prompt for self-correction.
- Markdown code-block markers (` ```turtle `) are stripped automatically to ensure valid Turtle output.
- API key is loaded from `.env` via `python-dotenv`.

**Output:** `GPT5Results/ontology_draft_N.ttl` (LLM draft) and `GPT5Results/ontology_N.ttl` (validated & saved).

---

## 2. Validation Pipeline

### 2a. Turtle / RDF Syntax Check
- `rdflib` parses every generated `.ttl` file and reports any syntax errors.
- On success the file is also serialised to RDF/XML (`ontology_N.rdf`) for downstream tools.

### 2b. SHACL Validation (pySHACL)
- A SHACL shapes graph enforces that every `owl:Class` carries an `rdfs:label`.
- `inference='rdfs'` is enabled so inherited constraints are checked.
- Conformance status and violation details are printed and written to `output/experiment_results/`.

### 2c. Custom Pitfall Detection (local)
- Python/rdflib checks, run before OOPS for speed:
  - **Missing labels** — `owl:Class` instances without `rdfs:label`.
  - **Unconnected classes** — classes that appear in no triple as subject or object.

### 2d. OOPS! Pitfall Scanner
Resolution order (automatic, no configuration needed):

| Priority | Endpoint | When used |
|---|---|---|
| 1 | Docker — `http://localhost/OOPS/rest` | Docker service is running |
| 2 | Public web service — `https://oops.linkeddata.es/rest` | Docker unreachable |
| 3 | Skip | Both unreachable |

The active endpoint is printed at runtime. The `OOPS_URL` environment variable overrides the Docker address if the port mapping differs.

The XML response is parsed into structured pitfall entries with code, name, importance level (Critical / Important / Minor), and affected element count.

**Pellet / HermiT reasoning** remains disabled due to Java version conflicts in the Docker base image; SHACL and OOPS cover the same ground for the current experiments.

---

## 3. Semantic Evaluation (`evaluate_gpt5_results.py`)

Reproduces the embedding-based evaluation from the paper against the AquaDiva gold standard (`VersionOne/AquaDivaMergedNew.ttl`).

### Method
Uses `sentence-transformers/all-MiniLM-L6-v2` to compute cosine similarity at two levels:

- **Entity level** — each entity is embedded as `"label [SEP] comment"` (fallback: local name). Best-match cosine similarity against every gold entity is computed via FAISS.
- **Triple level** — schema triples (`subClassOf`, `rdf:type`, `domain`, `range`, `disjointWith`) are embedded as `"subject [SEP] predicate [SEP] object"` and matched the same way.

Results are bucketed into six similarity ranges: `<50 / 50-60 / 60-70 / 70-80 / 80-90 / 90-100`.

### Table 1 — Matched Entities & Average Similarity
Entities with cosine similarity ≥ 0.70 are counted as **matched**; their average similarity is reported — matching the AML-based methodology in the paper (scores consistently in the 0.85–0.93 range).

Gold embeddings are cached to `GPT5Results/gold_embeddings_*` after the first run; subsequent runs reuse them.

### Outputs

| File | Contents |
|---|---|
| `GPT5Results/evaluation_results.json` | Per-ontology bucket stats + raw similarity scores |
| `GPT5Results/evaluation_results.csv` | Flat rows: `ontology, level, bucket, count, percent` + Table 1 rows |
| `GPT5Results/entity_alignment.pdf/png` | Stacked bar chart — entity-level alignment across all ontologies |
| `GPT5Results/triple_alignment.pdf/png` | Stacked bar chart — triple-level alignment across all ontologies |

Run:
```bash
python evaluate_gpt5_results.py
```

---

## 4. Docker & Docker Compose

### Services

| Service | Image / Build | Purpose |
|---|---|---|
| `ontology-validation` | Built from `Dockerfile` (Python 3.11) | Runs the generation + validation pipeline |
| `oops` | `mpovedavillalon/oops:v1` | OOPS! pitfall scanner (Tomcat/Java) |

### Key compose settings
- `oops` uses `platform: linux/arm64` — the image has no `amd64` build; Docker Desktop's QEMU emulation handles the translation transparently on Windows/Linux x86 hosts.
- `ontology-validation` sets `OOPS_URL=http://oops:8080/OOPS/rest` (internal Docker network port, not the host-mapped port 80).
- `depends_on: condition: service_healthy` — the pipeline waits for OOPS's Tomcat to finish starting (healthcheck polls `/OOPS/` every 10 s, up to 6 retries with a 30 s start grace period).
- Mount `./WordNet:/usr/local/tomcat/WordNet` in the `oops` service (commented out by default) for richer pitfall detection.

### Start everything
```bash
docker compose up -d --build
```

OOPS web UI is then available at `http://localhost/OOPS/`.

---

## 5. Project Structure

```
.
├── run_pipeline_for_prompts.py       # Main pipeline (generate → validate loop)
├── evaluate_gpt5_results.py          # Semantic evaluation vs AquaDiva gold standard
├── Prompts.json                      # Prompt templates (AppendixB)
├── docker-compose.yml                # ontology-validation + oops services
├── Dockerfile                        # Python 3.11 image for the pipeline
├── .env                              # OPENAI_API_KEY (not committed)
├── code/
│   └── ontology_validation_syntax_consistency_pitfall_no_pellet_no_hermit.py
├── GPT5Results/                      # Generated ontologies + evaluation outputs
├── VersionOne/                       # AquaDiva gold standard ontologies
└── output/experiment_results/        # Per-prompt validation reports
```

---

## 6. Environment Variables

| Variable | Default | Description |
|---|---|---|
| `OPENAI_API_KEY` | — | Required. Set in `.env`. |
| `OOPS_URL` | `http://localhost/OOPS/rest` | OOPS Docker endpoint. Set automatically to `http://oops:8080/OOPS/rest` inside Compose. |

---

✅ **Current pipeline:**

```
Prompts.json
    → GPT-5.4-mini (ontology draft)
    → rdflib (Turtle syntax)
    → pySHACL (SHACL constraints)
    → Custom pitfall checks (missing labels, unconnected classes)
    → OOPS! Docker / public web service (modeling quality)
    → Validation report fed back to LLM for next iteration
    → evaluate_gpt5_results.py (embedding-based semantic evaluation vs gold standard)
```
