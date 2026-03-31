import os
import glob
import requests

from rdflib import Graph, RDF, RDFS, OWL
from pyshacl import validate



# ================= CONFIG =================
import sys

# Set OUTPUT_DIR to match the ontology output dir from the pipeline
INPUT_TTL = "/app/VersionOne/AquaDiva2.ttl"
OUTPUT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "GPT5Results"))

# Allow override of INPUT_TTL from command line
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

    print(f"✔ Saved Turtle: {ttl_out}")
    print(f"✔ Saved RDF/XML: {rdf_out}")


# ================= STEP 3: SHACL VALIDATION =================
def run_shacl_validation(ttl_path):
    print("\n--- SHACL Validation ---")

    # Minimal shapes graph (you can expand this)
    shapes_graph = """
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
        @prefix owl: <http://www.w3.org/2002/07/owl#> .
        @prefix ex: <http://example.org/> .   # ✅ ADD THIS

        # Rule: All classes must have a label
        ex:ClassShape
            a sh:NodeShape ;
            sh:targetClass owl:Class ;
            sh:property [
                sh:path rdfs:label ;
                sh:minCount 1 ;
            ] .
        """

    conforms, report_graph, report_text = validate(
        data_graph=ttl_path,
        shacl_graph=shapes_graph,
        inference='rdfs',
        debug=False
    )

    print(report_text)

    if conforms:
        print("✔ SHACL validation passed.")
    else:
        print("❌ SHACL validation failed.")


# ================= STEP 4: PITFALL DETECTION =================
class OntologyPitfallDetector:

    def __init__(self, ttl_file):
        self.graph = Graph()
        self.graph.parse(ttl_file, format="turtle")
        self.pitfalls = []

    def detect_missing_labels(self):
        for s in self.graph.subjects(RDF.type, RDFS.Class):
            if not (s, RDFS.label, None) in self.graph:
                self.pitfalls.append(f"Class {s} missing rdfs:label")

    def detect_unconnected_classes(self):
        for s in self.graph.subjects(RDF.type, RDFS.Class):
            if not (None, None, s) in self.graph and not (s, None, None) in self.graph:
                self.pitfalls.append(f"Class {s} unconnected")

    def run(self):
        self.detect_missing_labels()
        self.detect_unconnected_classes()
        return self.pitfalls


# ================= STEP 5: OOPS =================
def run_oops(rdf_path):
    g = Graph()
    g.parse(rdf_path, format="xml")
    rdfxml_data = g.serialize(format="xml")

    xml_request = f"""<?xml version="1.0"?>
<OOPSRequest>
  <OntologyContent><![CDATA[
{rdfxml_data}
  ]]></OntologyContent>
</OOPSRequest>"""

    response = requests.post(
        "https://oops.linkeddata.es/rest",
        headers={"Content-Type": "application/xml"},
        data=xml_request.encode("utf-8")
    )

    print("\n--- OOPS Response ---")
    print(response.text)


# ================= MAIN =================
def main():
    ttl_out, rdf_out = get_next_paths()

    # Step 1
    graph = check_syntax(INPUT_TTL)
    if not graph:
        return

    # Step 2
    save_outputs(graph, ttl_out, rdf_out)

    # Step 3 (NEW)
    run_shacl_validation(ttl_out)

    # Step 4
    print("\n--- Pitfalls ---")
    detector = OntologyPitfallDetector(ttl_out)
    pitfalls = detector.run()

    print(f"Total pitfalls: {len(pitfalls)}")
    for p in pitfalls:
        print("⚠", p)

    # Step 5
    #run_oops(rdf_out)


if __name__ == "__main__":
    main()