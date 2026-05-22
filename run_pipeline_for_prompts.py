
import os
import json
import re
import subprocess
from dotenv import load_dotenv
from openai import OpenAI
from rdflib import Graph, OWL, RDF, RDFS


PROMPTS_JSON = "Prompts.json"
VALIDATION_SCRIPT = os.path.join("code", "ontology_validation_syntax_consistency_pitfall_no_pellet_no_hermit.py")
RESULTS_DIR = os.path.join("output", "experiment_results")
RESULTS_ONTOLOGY_DIR = "GPT5Results"

# Paths to domain resource files
_BASE = os.path.dirname(os.path.abspath(__file__))
_PERSONA_FILE          = os.path.join(_BASE, "Persona.txt")
_DOMAIN_DESC_FILE      = os.path.join(_BASE, "OntologyDescription", "AquaDiva.txt")
_KEYWORDS_FILE         = os.path.join(_BASE, "AquaDivakeywords.json")
_EXAMPLES_FILE         = os.path.join(_BASE, "Few-shotExamplesExtractedFromAquaDiva", "AquaDivaExamples.txt")
_CQ_FILE               = os.path.join(_BASE, "CompetencyQuestions", "Competency Questions for the AquaDiva Ontology (Version 1).txt")
_GOLD_ONTOLOGY_FILE    = os.path.join(_BASE, "gold_standard", "ad-ontology-merged-updated.owl")

load_dotenv()
openai_api_key = os.getenv("OPENAI_API_KEY")
if not openai_api_key:
    raise RuntimeError("OPENAI_API_KEY is not set. Please set it in your environment or in a .env file.")
client = OpenAI(api_key=openai_api_key)


# ================= RESOURCE LOADERS =================

def _read(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read().strip()


def _load_keywords() -> str:
    """Flatten all keyword strings from AquaDivakeywords.json into one comma-separated list."""
    with open(_KEYWORDS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    seen = set()
    flat = []
    for entry in data:
        for kw in re.split(r"[;,]", str(entry.get("keywords", ""))):
            kw = kw.strip()
            if kw and kw.lower() not in seen:
                seen.add(kw.lower())
                flat.append(kw)
    return ", ".join(flat)


def _load_examples() -> dict:
    """
    Parse AquaDivaExamples.txt into three sections keyed by:
      'cq_triples'   – Subject-relation-object examples from CQs
      'data_props'   – Data property examples
      'individuals'  – Meaningful individual examples
    """
    text = _read(_EXAMPLES_FILE)
    sections = {}

    markers = [
        ("cq_triples",   "Subject-relation-object from Competency Questions examples:"),
        ("data_props",   "Data property with domain and range examples:"),
        ("individuals",  "Meaningful individuals examples:"),
    ]

    for i, (key, header) in enumerate(markers):
        start = text.find(header)
        if start == -1:
            sections[key] = ""
            continue
        start += len(header)
        end = len(text)
        for _, next_header in markers[i + 1:]:
            pos = text.find(next_header)
            if pos != -1:
                end = pos
                break
        sections[key] = text[start:end].strip()

    return sections


def _load_competency_questions() -> str:
    """Return the full CQ list as a numbered string."""
    return _read(_CQ_FILE)


def _compute_ontology_metrics() -> str:
    """Count classes, properties, and individuals in the AquaDiva gold standard TTL."""
    g = Graph()
    g.parse(_GOLD_ONTOLOGY_FILE)
    classes     = len(set(g.subjects(RDF.type, OWL.Class)))
    obj_props   = len(set(g.subjects(RDF.type, OWL.ObjectProperty)))
    data_props  = len(set(g.subjects(RDF.type, OWL.DatatypeProperty)))
    individuals = len(set(g.subjects(RDF.type, OWL.NamedIndividual)))
    subclass    = len(list(g.subject_objects(RDFS.subClassOf)))
    return (
        f"Classes: {classes}, ObjectProperties: {obj_props}, "
        f"DatatypeProperties: {data_props}, Individuals: {individuals}, "
        f"SubClassOf relations: {subclass}"
    )

# Ensure results directory exists
def ensure_results_dir():
    os.makedirs(RESULTS_DIR, exist_ok=True)
    os.makedirs(RESULTS_ONTOLOGY_DIR, exist_ok=True)

# Load prompts from Prompts.json
def load_prompts():
    with open(PROMPTS_JSON, "r", encoding="utf-8") as f:
        data = json.load(f)
    prompts = []
    for section in data.get("AppendixB", {}).get("prompts", []):
        for prompt in section.get("prompts", []):
            for k, v in prompt.items():
                if k.startswith("Prompt "):
                    prompts.append({"title": k, "text": v})
    return prompts

# Run validation script for each prompt

def fill_placeholders(prompt_text, validation_context=None):
    examples = _load_examples()

    values = {
        # ── Identity / domain ────────────────────────────────────────────────
        "{Persona}":              _read(_PERSONA_FILE),
        "{Domain Name}":          "AquaDiva",
        "{Domain Description}":   _read(_DOMAIN_DESC_FILE),
        "{Keywords}":             _load_keywords(),

        # ── Gold-standard metrics (computed live from AquaDivaMergedNew.ttl) ─
        "{Ontology Metric Counts}": _compute_ontology_metrics(),

        # ── Existing resource ────────────────────────────────────────────────
        "{Existing Resource Name and Description}":
            "AquaDiva ontology (AquaDivaMergedNew.ttl) — a life-science ontology "
            "covering groundwater ecosystems, microbial ecology, hydrogeology, "
            "karst systems, and geochemistry.",

        # ── Few-shot examples (parsed from AquaDivaExamples.txt) ────────────
        "{Few-shot examples from existing resource}":
            examples["cq_triples"],
        "{Few-shot examples for entity and relationship extraction from competency questions}":
            examples["cq_triples"],
        "{Few-shot examples to demonstrate introducing data properties}":
            examples["data_props"],
        "{Few-shot examples of meaningful individuals}":
            examples["individuals"],

        # ── Error message placeholders (filled by the iterative loop) ────────
        "{RDFLib Syntax Error Message}":    validation_context or "",
        "{Affected Part of the Ontology}":  "",
        "{HermiT Reasoner Error Message}":  "",
        "{OOPS API Error Message}":         "",
    }

    for k, v in values.items():
        prompt_text = prompt_text.replace(k, v)

    # Inject the competency questions when the prompt asks to work from them.
    # The CQ file is referenced by text but has no dedicated placeholder in Prompts.json.
    if "Competency Question" in prompt_text:
        cqs = _load_competency_questions()
        prompt_text = (
            f"Competency Questions for the AquaDiva ontology:\n{cqs}\n\n"
            + prompt_text
        )

    if validation_context:
        prompt_text += f"\n\nPrevious validation result (please fix all issues):\n{validation_context}\n"

    prompt_text += (
        "\n\nReturn the complete ontology in valid Turtle syntax. "
        "Any explanation or instructions must be included as comments (lines starting with #) at the top of the file. "
        "Do NOT use triple backticks or any markdown formatting. "
        "Output only valid Turtle syntax, with any explanation as Turtle comments."
    )
    return prompt_text

def call_openai_and_save(prompt, idx, validation_context=None):
    # Compose the full prompt (system + user)
    full_prompt = fill_placeholders(prompt['text'], validation_context=validation_context)
    try:
        response = client.chat.completions.create(
            model="gpt-5.4-mini",  # or "gpt-5.4" alternatively for bigger context window, but "mini" is faster and cheaper for iterative testing
            messages=[
                {"role": "system", "content": "You are an expert ontology engineer."},
                {"role": "user", "content": full_prompt}
            ],
        )
        generated_ontology_ttl = response.choices[0].message.content
    except Exception as e:
        generated_ontology_ttl = f"[OpenAI API Error]: {e}"

    # Remove triple backticks and optional 'turtle' from start/end
    import re
    if generated_ontology_ttl:
        # Remove leading/trailing whitespace
        s = generated_ontology_ttl.strip()
        # Remove code block markers at start
        s = re.sub(r'^```turtle\s*', '', s, flags=re.IGNORECASE)
        s = re.sub(r'^```\s*', '', s)
        # Remove code block markers at end
        s = re.sub(r'\s*```$', '', s)
        generated_ontology_ttl = s

    # Save the generated ontology to the Results folder
    ontology_output_path = os.path.join(RESULTS_ONTOLOGY_DIR, f"ontology_draft_{idx}.ttl")
    with open(ontology_output_path, "w", encoding="utf-8") as f:
        f.write(generated_ontology_ttl)
    print(f"[✓] Ontology draft generated and saved as {ontology_output_path}")
    return ontology_output_path

def run_validation_for_prompts(prompts):
    previous_validation_result = None
    for idx, prompt in enumerate(prompts, 1):
        # Save prompt to a temp file for traceability
        prompt_file = os.path.join(RESULTS_DIR, f"prompt_{idx}.txt")
        with open(prompt_file, "w", encoding="utf-8") as pf:
            pf.write(f"{prompt['title']}\n{prompt['text']}\n")

        # Call OpenAI API and save ontology draft, passing previous validation result if any
        ontology_output_path = call_openai_and_save(prompt, idx, validation_context=previous_validation_result)

        # Call the validation script on the generated ontology file
        result_file = os.path.join(RESULTS_DIR, f"validation_result_{idx}.txt")
        try:
            proc = subprocess.run([
                "python", VALIDATION_SCRIPT, ontology_output_path
            ], capture_output=True, text=True, check=False)
            with open(result_file, "w", encoding="utf-8") as rf:
                rf.write(proc.stdout)
                if proc.stderr:
                    rf.write("\n--- STDERR ---\n")
                    rf.write(proc.stderr)
            print(f"[✓] Ran validation for {prompt['title']} on {ontology_output_path}, result saved to {result_file}")
            # Read validation result for next iteration
            with open(result_file, "r", encoding="utf-8") as rf:
                previous_validation_result = rf.read()
        except Exception as e:
            print(f"[!] Error running validation for {prompt['title']} on {ontology_output_path}: {e}")
            previous_validation_result = str(e)

def main():
    ensure_results_dir()
    prompts = load_prompts()
    run_validation_for_prompts(prompts)

if __name__ == "__main__":
    main()
