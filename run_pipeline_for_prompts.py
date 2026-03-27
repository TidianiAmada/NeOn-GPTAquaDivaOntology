import os
import json
import subprocess
from datetime import datetime

PROMPTS_JSON = "Prompts.json"
VALIDATION_SCRIPT = os.path.join("code", "ontology_validation_syntax_consistency_pitfall_no_pellet_no_hermit.py")
RESULTS_DIR = os.path.join("output", "experiment_results")

# Ensure results directory exists
def ensure_results_dir():
    os.makedirs(RESULTS_DIR, exist_ok=True)

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
def run_validation_for_prompts(prompts):
    for idx, prompt in enumerate(prompts, 1):
        # Save prompt to a temp file for traceability
        prompt_file = os.path.join(RESULTS_DIR, f"prompt_{idx}.txt")
        with open(prompt_file, "w", encoding="utf-8") as pf:
            pf.write(f"{prompt['title']}\n{prompt['text']}\n")
        # Call the validation script (customize input/output as needed)
        result_file = os.path.join(RESULTS_DIR, f"validation_result_{idx}.txt")
        try:
            proc = subprocess.run([
                "python", VALIDATION_SCRIPT
            ], capture_output=True, text=True, check=False)
            with open(result_file, "w", encoding="utf-8") as rf:
                rf.write(proc.stdout)
                if proc.stderr:
                    rf.write("\n--- STDERR ---\n")
                    rf.write(proc.stderr)
            print(f"[✓] Ran validation for {prompt['title']}, result saved to {result_file}")
        except Exception as e:
            print(f"[!] Error running validation for {prompt['title']}: {e}")

def main():
    ensure_results_dir()
    prompts = load_prompts()
    run_validation_for_prompts(prompts)

if __name__ == "__main__":
    main()
