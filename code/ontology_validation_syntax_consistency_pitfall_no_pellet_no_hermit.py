import glob
import os
import sys
import xml.etree.ElementTree as ET

import requests
from pyshacl import validate
from rdflib import RDF, RDFS, Graph

# ================= CONFIG =================

# OOPS! Docker instance — start with:
#   docker run -p 80:8080 mpovedavillalon/oops:v1
# Override via env var if the port mapping differs, e.g. OOPS_URL=http://localhost:8080/OOPS/rest
OOPS_URL = os.environ.get("OOPS_URL", "http://localhost/OOPS/rest")

# Public OOPS! web service — used automatically when the Docker instance is unreachable.
OOPS_FALLBACK_URL = "https://oops.linkeddata.es/rest"

INPUT_TTL = "/app/VersionOne/AquaDiva2.ttl"
OUTPUT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "GPT5Results"))

if len(sys.argv) > 1:
    INPUT_TTL = sys.argv[1]

os.makedirs(OUTPUT_DIR, exist_ok=True)


# ================= UTIL =================

def get_next_paths():
    existing = glob.glob(os.path.join(OUTPUT_DIR, "ontology_*.ttl"))
    nums = []
    for f in existing:
        base = os.path.basename(f)
        parts = base.split("_")
        if len(parts) >= 2:
            num_part = parts[-1].split(".")[0]
            try:
                nums.append(int(num_part))
            except ValueError:
                continue
    next_num = max(nums) + 1 if nums else 1

    ttl_path = os.path.join(OUTPUT_DIR, f"ontology_{next_num}.ttl")
    rdf_path = ttl_path.replace(".ttl", ".rdf")
    return ttl_path, rdf_path


# ================= STEP 1: SYNTAX CHECK =================

def check_syntax(ttl_path):
    g = Graph()
    try:
        g.parse(ttl_path, format="turtle")
        print("✔ Turtle syntax is correct.")
        return g
    except Exception as e:
        print(f"❌ Syntax error: {e}")
        return None


# ================= STEP 2: SAVE =================

def save_outputs(graph, ttl_out, rdf_out):
    graph.serialize(destination=ttl_out, format="turtle")
    graph.serialize(destination=rdf_out, format="xml")
    print(f"✔ Saved Turtle:   {ttl_out}")
    print(f"✔ Saved RDF/XML:  {rdf_out}")


# ================= STEP 3: SHACL VALIDATION =================

def run_shacl_validation(ttl_path):
    print("\n--- SHACL Validation ---")

    shapes_graph = """
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
        @prefix owl: <http://www.w3.org/2002/07/owl#> .
        @prefix ex: <http://example.org/> .

        ex:ClassShape
            a sh:NodeShape ;
            sh:targetClass owl:Class ;
            sh:property [
                sh:path rdfs:label ;
                sh:minCount 1 ;
            ] .
        """

    conforms, _, report_text = validate(
        data_graph=ttl_path,
        shacl_graph=shapes_graph,
        inference="rdfs",
        debug=False,
    )

    print(report_text)
    if conforms:
        print("✔ SHACL validation passed.")
    else:
        print("❌ SHACL validation failed.")


# ================= STEP 4: CUSTOM PITFALL DETECTION =================

class OntologyPitfallDetector:

    def __init__(self, ttl_file):
        self.graph = Graph()
        self.graph.parse(ttl_file, format="turtle")
        self.pitfalls = []

    def detect_missing_labels(self):
        for s in self.graph.subjects(RDF.type, RDFS.Class):
            if (s, RDFS.label, None) not in self.graph:
                self.pitfalls.append(f"Class {s} missing rdfs:label")

    def detect_unconnected_classes(self):
        for s in self.graph.subjects(RDF.type, RDFS.Class):
            if (None, None, s) not in self.graph and (s, None, None) not in self.graph:
                self.pitfalls.append(f"Class {s} unconnected")

    def run(self):
        self.detect_missing_labels()
        self.detect_unconnected_classes()
        return self.pitfalls


# ================= STEP 5: OOPS! (Docker) =================

# OOPS! pitfall severity levels (from https://oops.linkeddata.es/catalogue.jsp)
_SEVERITY_EMOJI = {
    "Critical": "🔴",
    "Important": "🟠",
    "Minor": "🟡",
}


def _check_oops_available(url: str, timeout: int = 3) -> bool:
    """Return True if an OOPS endpoint responds (Docker or public web service)."""
    try:
        base = url.replace("/rest", "")
        requests.get(base, timeout=timeout)
        return True
    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
        return False


def _parse_oops_response(xml_text: str) -> list[dict]:
    """
    Parse the OOPS! XML response and return a list of pitfall dicts:
      {code, name, description, importance, affected}
    Returns an empty list if the response cannot be parsed.
    """
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        print(f"  ⚠ Could not parse OOPS XML response: {exc}")
        return []

    pitfalls = []

    # The response is RDF/XML; pitfall elements live under oops:pitfall
    for pitfall_el in root.iter("{http://oops.linkeddata.es/def#}pitfall"):
        def _text(tag):
            el = pitfall_el.find(f"{{http://oops.linkeddata.es/def#}}{tag}")
            return el.text.strip() if el is not None and el.text else ""

        pitfalls.append({
            "code":        _text("hasCode"),
            "name":        _text("hasName"),
            "description": _text("hasDescription"),
            "importance":  _text("hasImportanceLevel"),
            "affected":    _text("hasNumberAffectedElements"),
        })

    return pitfalls


def _post_to_oops(endpoint: str, xml_request: str) -> str | None:
    """POST an OOPSRequest XML body to *endpoint*. Returns response text or None on error."""
    try:
        response = requests.post(
            endpoint,
            headers={"Content-Type": "application/xml"},
            data=xml_request.encode("utf-8"),
            timeout=60,
        )
        response.raise_for_status()
        return response.text
    except requests.exceptions.RequestException as exc:
        print(f"  ❌ OOPS request to {endpoint} failed: {exc}")
        return None


def run_oops(rdf_path: str) -> list[dict]:
    """
    Send the ontology (RDF/XML) to OOPS! and print a structured pitfall summary.

    Resolution order:
      1. Docker instance at OOPS_URL  (fastest, no rate limits)
      2. Public web service at OOPS_FALLBACK_URL  (used when Docker is unreachable)

    Returns the list of pitfall dicts (empty if both endpoints are unavailable
    or no pitfalls are found).
    """
    print("\n--- OOPS! Pitfall Scanner ---")

    # Choose the active endpoint
    if _check_oops_available(OOPS_URL):
        endpoint = OOPS_URL
        print(f"  Using Docker instance: {endpoint}")
    elif _check_oops_available(OOPS_FALLBACK_URL):
        endpoint = OOPS_FALLBACK_URL
        print(
            f"  Docker instance not reachable at {OOPS_URL}.\n"
            f"  Falling back to public web service: {endpoint}"
        )
    else:
        print(
            f"  ⚠ Neither Docker ({OOPS_URL}) nor the public web service "
            f"({OOPS_FALLBACK_URL}) is reachable.\n"
            "    Start Docker with:  docker run -p 80:8080 mpovedavillalon/oops:v1\n"
            "    Skipping OOPS validation."
        )
        return []

    # Build the RDF/XML request body
    g = Graph()
    g.parse(rdf_path, format="xml")
    rdfxml_data = g.serialize(format="xml")

    xml_request = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        "<OOPSRequest>\n"
        "  <OntologyContent><![CDATA[\n"
        f"{rdfxml_data}\n"
        "  ]]></OntologyContent>\n"
        "  <Pitfalls></Pitfalls>\n"
        "  <OutputFormat>RDF/XML</OutputFormat>\n"
        "</OOPSRequest>"
    )

    response_text = _post_to_oops(endpoint, xml_request)
    if response_text is None:
        return []

    pitfalls = _parse_oops_response(response_text)

    if not pitfalls:
        print("  ✔ No pitfalls detected by OOPS!")
        return []

    print(f"  Detected {len(pitfalls)} pitfall(s):\n")
    for p in pitfalls:
        emoji = _SEVERITY_EMOJI.get(p["importance"], "⚠")
        affected = f"  (affects {p['affected']} element(s))" if p["affected"] else ""
        print(f"  {emoji} [{p['code']}] {p['name']} — {p['importance']}{affected}")
        if p["description"]:
            print(f"      {p['description']}")

    return pitfalls


# ================= MAIN =================

def main():
    ttl_out, rdf_out = get_next_paths()

    # Step 1
    graph = check_syntax(INPUT_TTL)
    if not graph:
        return

    # Step 2
    save_outputs(graph, ttl_out, rdf_out)

    # Step 3
    run_shacl_validation(ttl_out)

    # Step 4
    print("\n--- Custom Pitfall Detection ---")
    detector = OntologyPitfallDetector(ttl_out)
    pitfalls = detector.run()
    print(f"Total pitfalls: {len(pitfalls)}")
    for p in pitfalls:
        print("  ⚠", p)

    # Step 5 — OOPS! via Docker
    run_oops(rdf_out)


if __name__ == "__main__":
    main()
