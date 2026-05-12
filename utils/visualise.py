"""
visualise_ontology.py — PKG Ontology diagram generator
Reads pkg_ontology.ttl, outputs pkg_ontology.png
Run: python visualise_ontology.py
"""
import os, re
from rdflib import Graph, RDF, RDFS, OWL, URIRef, Namespace
from rdflib.namespace import SKOS
import graphviz

TTL_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pkg_ontology.ttl")
OUT_DIR  = "/tmp"
OUT_NAME = "pkg_ontology"

PKG    = Namespace("https://pkg.chunnodu.com/ontology#")
SCHEMA = Namespace("https://schema.org/")

g = Graph()
g.parse(TTL_FILE, format="turtle")

def lbl(uri):
    rdfs = g.value(URIRef(str(uri)), RDFS.label)
    return str(rdfs) if rdfs else str(uri).split("/")[-1].split("#")[-1]

# ── Build diagram ────────────────────────────────────────────────────────────
dot = graphviz.Digraph(
    name=OUT_NAME,
    graph_attr={
        "rankdir":  "LR",
        "fontname": "Arial",
        "fontsize": "11",
        "nodesep":  "0.35",
        "ranksep":  "1.8",
        "bgcolor":  "white",
        "pad":      "0.4",
    },
    node_attr={
        "fontname": "Arial", "fontsize": "10",
        "style": "filled", "shape": "box",
        "margin": "0.12,0.08",
    },
    edge_attr={"fontname": "Arial", "fontsize": "8", "arrowsize": "0.65"},
)

# ── Cluster: Knowledge ───────────────────────────────────────────────────────
with dot.subgraph(name="cluster_concept") as c:
    c.attr(label="Knowledge", style="rounded,filled", fillcolor="#eff6ff",
           color="#bfdbfe", fontname="Arial", fontsize="10")
    c.node("Concept", label="skos:Concept", fillcolor="#dbeafe", color="#3b82f6")

# ── Cluster: Resources ───────────────────────────────────────────────────────
with dot.subgraph(name="cluster_resources") as c:
    c.attr(label="Resources", style="rounded,filled", fillcolor="#f0fdf4",
           color="#bbf7d0", fontname="Arial", fontsize="10")
    c.node("Resource",        label="Resource",              fillcolor="#dcfce7", color="#22c55e")
    c.node("WebPage",         label="schema:WebPage",        fillcolor="#dcfce7", color="#22c55e")
    c.node("Tool",            label="schema:SoftwareApp",    fillcolor="#dcfce7", color="#22c55e")
    c.node("LearningMat",     label="Learning Material",     fillcolor="#bbf7d0", color="#16a34a")
    c.node("Book",            label="schema:Book",           fillcolor="#dcfce7", color="#22c55e")
    c.node("Course",          label="schema:Course",         fillcolor="#dcfce7", color="#22c55e")
    c.node("Webinar",         label="Webinar",               fillcolor="#dcfce7", color="#22c55e")

# ── Cluster: Custom types ────────────────────────────────────────────────────
with dot.subgraph(name="cluster_custom") as c:
    c.attr(label="Custom Types", style="rounded,filled", fillcolor="#fffbeb",
           color="#fde68a", fontname="Arial", fontsize="10")
    c.node("HowTo",        label="HowTo",         fillcolor="#fef9c3", color="#ca8a04")
    c.node("Presentation", label="Presentation",  fillcolor="#fef9c3", color="#ca8a04")
    c.node("BlogPost",     label="BlogPost",       fillcolor="#fef9c3", color="#ca8a04")
    c.node("WorkingGroup", label="WorkingGroup",   fillcolor="#fef9c3", color="#ca8a04")
    c.node("PersonalNote", label="PersonalNote",   fillcolor="#fef9c3", color="#ca8a04")
    c.node("Event",        label="Event",          fillcolor="#fef9c3", color="#ca8a04")
    c.node("Task",         label="Task",           fillcolor="#fef9c3", color="#ca8a04")
    c.node("Project",      label="Project",        fillcolor="#fef9c3", color="#ca8a04")
    c.node("Goal",         label="Goal",           fillcolor="#fef9c3", color="#ca8a04")
    c.node("LogEntry",     label="LogEntry",       fillcolor="#fef9c3", color="#ca8a04")
    c.node("Organization", label="Organization",   fillcolor="#fef9c3", color="#ca8a04")

# ── subClassOf (dashed, grey) ────────────────────────────────────────────────
SC = {"style": "dashed", "color": "#94a3b8", "fontcolor": "#94a3b8",
      "arrowhead": "empty", "label": "⊆"}

dot.edge("WebPage",     "Resource",     **SC)
dot.edge("Tool",        "Resource",     **SC)
dot.edge("LearningMat", "Resource",     **SC)
dot.edge("Book",        "LearningMat",  **SC)
dot.edge("Course",      "LearningMat",  **SC)
dot.edge("Webinar",     "LearningMat",  **SC)
dot.edge("BlogPost",    "Presentation", **SC)

# ── Object properties from skos:Concept (purple) ─────────────────────────────
OP = {"color": "#6366f1", "fontcolor": "#4f46e5", "arrowhead": "vee"}

dot.edge("Concept", "Concept",      label="skos:related",        **OP)
dot.edge("Concept", "Concept",      label="hasSubTopic",         **OP)
dot.edge("Concept", "Resource",     label="hasResource",         **OP)
dot.edge("Concept", "LearningMat",  label="hasLearningMaterial", **OP)
dot.edge("Concept", "HowTo",        label="hasProcedure",        **OP)
dot.edge("Concept", "Presentation", label="hasPresentation",     **OP)
dot.edge("Concept", "PersonalNote", label="hasNote",             **OP)
dot.edge("Concept", "Task",         label="hasTask",             **OP)
dot.edge("Concept", "Project",      label="hasProject",          **OP)
dot.edge("Concept", "Goal",         label="hasGoal",             **OP)
dot.edge("Concept", "LogEntry",     label="hasLogEntry",         **OP)
dot.edge("Concept", "Organization", label="hasOrganization",     **OP)

out_path = os.path.join(OUT_DIR, OUT_NAME)
dot.render(out_path, format="png", cleanup=True)
print(f"Saved: {out_path}.png")
