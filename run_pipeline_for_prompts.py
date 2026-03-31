
import os
import json
from dotenv import load_dotenv

import subprocess
from datetime import datetime
from openai import OpenAI


PROMPTS_JSON = "Prompts.json"
VALIDATION_SCRIPT = os.path.join("code", "ontology_validation_syntax_consistency_pitfall_no_pellet_no_hermit.py")
RESULTS_DIR = os.path.join("output", "experiment_results")
RESULTS_ONTOLOGY_DIR = "GPT5Results"

# OpenAI API key (move to .env in production)

# Load environment variables from .env file
load_dotenv()
openai_api_key = os.getenv("OPENAI_API_KEY")
if not openai_api_key:
    raise RuntimeError("OPENAI_API_KEY is not set. Please set it in your environment or in a .env file.")
client = OpenAI(api_key=openai_api_key)

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
    # Dummy values for placeholders; replace with real data as needed
    values = {
        "{Persona}": "expert aquatic ecologist and knowledge engineer",
        "{Domain Name}": "AquaDiva",
        "{Domain Description}": "A domain about groundwater and subsurface life.",
        "{Keywords}": "groundwater, aquifer, microbe, carbon cycle, nitrogen cycle",
        "{Ontology Metric Counts}": "Classes: 20, Properties: 15, Individuals: 10",
        "{Existing Resource Name and Description}": "ENVO ontology, environmental terms",
        "{Few-shot examples from existing resource}": "Class: Aquifer, Property: hasDepth",
        "{Few-shot examples for entity and relationship extraction from competency questions}": "Entity: Microbe, Property: inhabits, Entity: Aquifer",
        "{Few-shot examples to demonstrate introducing data properties}": "Property: hasDepth (domain: Aquifer, range: float)",
        "{Few-shot examples of meaningful individuals}": "Individual: Aquifer1 (type: Aquifer)",
        "{RDFLib Syntax Error Message}": "Syntax error at line 10",
        "{Affected Part of the Ontology}": "@prefix : <#> .",
        "{HermiT Reasoner Error Message}": "Inconsistency detected in class hierarchy",
        "{OOPS API Error Message}": "Pitfall: Missing domain for property",
    }
    for k, v in values.items():
        prompt_text = prompt_text.replace(k, v)
    # Add validation context if provided
    if validation_context:
        prompt_text += f"\n\nPrevious validation result (please fix all issues):\n{validation_context}\n"
    # Add strict instruction for LLM output format
    prompt_text += ("\n\nReturn the complete ontology in valid Turtle syntax. "
                   "Any explanation or instructions must be included as comments (lines starting with #) at the top of the file. "
                   "Do NOT use triple backticks or any markdown formatting. Output only valid Turtle syntax, with any explanation as Turtle comments.")
    return prompt_text

def call_openai_and_save(prompt, idx, validation_context=None):
    # Compose the full prompt (system + user)
    full_prompt = fill_placeholders(prompt['text'], validation_context=validation_context)
    try:
        response = client.chat.completions.create(
            model="gpt-4o",  # or "gpt-5-mini" if available
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
