---


# Project Update: Ontology Validation, AI Drafting, & Local OOPS Implementation

## 1️⃣ AI-Driven Ontology Drafting & Iterative Validation
- Integrated OpenAI API to generate ontology drafts from prompt templates, with placeholder filling and context injection.
- Pipeline now iteratively:
  - Generates ontology drafts using LLM (OpenAI gpt-5-mini or similar).
  - Validates each draft and feeds back validation errors to the next LLM prompt for self-correction.
- Automatically strips markdown code block markers (```/```turtle) from LLM output to ensure valid Turtle syntax.
- Supports .env file for secure API key management (python-dotenv).

## 2️⃣ Turtle / RDF Syntax & SHACL Validation
- All Turtle (.ttl) files from the LLM are validated for syntax using rdflib.
- Conversion to RDF/XML is performed for compatibility.
- pySHACL is used for local SHACL validation:
  - Ensures constraints (mandatory properties, cardinalities, datatypes) are respected.
  - Eliminates errors related to unbound prefixes by ensuring all namespaces are correctly declared.
- Reports include conformance status and validation errors.

## 3️⃣ Pellet / OWL Reasoning (Status)
- Pellet (via Owlready2) was tested for reasoning but is currently disabled due to Java version conflicts in Docker.
- The pipeline relies on SHACL and local checks for now; external reasoning can be re-enabled if Java issues are resolved.

## 4️⃣ Docker & Docker Compose Setup
- Docker environment includes:
  - Python 3.13
  - All required libraries (rdflib, pySHACL, openai, python-dotenv, etc.)
  - Optional Java for future reasoning support
- Docker Compose supports multi-container setups for modularity and reproducibility.

## 5️⃣ OOPS Integration
- OOPS API (oops.linkeddata.es) is currently disabled due to SSL errors and unreliability.
- All OOPS-like checks are now performed locally.

## 6️⃣ Local OOPS Implementation
- Python-based local OOPS engine (rdflib):
  - P01: Missing labels (rdfs:label)
  - P02: Missing comments (rdfs:comment)
  - P03: Orphan classes (no triples)
  - P04: Classes without hierarchy (rdfs:subClassOf)
  - P05: Cyclic subclassing
  - P06: Properties missing domain or range
- Outputs a report with pitfalls and an optional quality score.

## 7️⃣ Overall Pipeline
- The pipeline is now AI-driven and fully local:
  - Prompts → OpenAI LLM (ontology draft) → rdflib (syntax) → pySHACL (constraints) → Local OOPS (modeling quality) → Report & Score
- Iterative: Each validation result is fed back to the LLM for self-correction.
- Fully self-contained: no external services required.
- Can be run via Docker for consistency.
- Provides both structural validation (SHACL) and quality checks (OOPS-like).

## 8️⃣ Next Steps (Optional Enhancements)
- Automatic label/comment suggestions using AI.
- JSON/REST API for ontology quality reports.
- Integration with future reasoning engines when Java version issues are resolved.
- Auto-fix simple pitfalls and re-validate automatically.
- More advanced prompt engineering for LLM self-healing.
- Support for additional LLM providers.

---


**Note:**
- OOPS API is currently disabled as oops.linkeddata.es does not respond. All OOPS-like checks are performed locally.
- OpenAI API key is loaded from .env for security and reproducibility.

✅ **Result:**
We now have a robust, AI-driven, fully local ontology validation pipeline that:
- Iteratively generates and corrects ontologies using LLMs and validation feedback.
- Validates syntax and SHACL constraints.
- Detects modeling pitfalls (OOPS-like rules) locally.
- Can be run reproducibly via Docker.
