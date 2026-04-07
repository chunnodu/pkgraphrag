import os
import xml.etree.ElementTree as ET
from datetime import datetime
from rdflib import Graph, URIRef, Literal, RDF, Namespace
from rdflib.namespace import SKOS, DC, XSD

# Namespaces
PKG = Namespace("https://pkg.chunnodu.com/ontology#")
PKGC = Namespace("https://pkg.chunnodu.com/concept/")
PKGR = Namespace("https://pkg.chunnodu.com/resource/")
PKGN = Namespace("https://pkg.chunnodu.com/note/")
SCHEMA = Namespace("https://schema.org/")

# Permanently Excluded Maps
EXCLUDED_MAPS = {"pitchstone.mm", "neogov.mm"}

def parse_epoch(millis_str):
    try:
        millis = int(millis_str)
        return datetime.fromtimestamp(millis / 1000.0).date().isoformat()
    except (TypeError, ValueError):
        return None

def process_map(filepath, output_dir):
    filename = os.path.basename(filepath)
    if filename in EXCLUDED_MAPS:
        print(f"Skipping excluded map: {filename} (PROPRIETARY)")
        return

    print(f"Parsing: {filepath}")
    g = Graph()
    g.bind("pkg", PKG)
    g.bind("pkgc", PKGC)
    g.bind("pkgr", PKGR)
    g.bind("pkgn", PKGN)
    g.bind("skos", SKOS)
    g.bind("schema", SCHEMA)
    g.bind("dc", DC)

    try:
        tree = ET.parse(filepath)
        root = tree.getroot()
    except Exception as e:
        print(f"  Error parsing XML for {filename}: {e}")
        return

    # Recursive function to traverse the Freeplane nodes
    def traverse(node_elem, parent_uri=None):
        node_id = node_elem.get("ID")
        if not node_id:
            # Fallback if no ID is present (rare in valid .mm files)
            node_id = f"gen_{hash(node_elem.get('TEXT', ''))}"
            
        text = node_elem.get("TEXT", "")

        # Freeplane stores HTML-formatted node text in <richcontent TYPE="NODE">
        # when the node uses rich text instead of plain TEXT attribute.
        # Extract it here as a fallback when TEXT is empty.
        if not text:
            for rc in node_elem.findall("richcontent"):
                if rc.get("TYPE") == "NODE":
                    rc_text = " ".join(rc.itertext()).split()
                    if rc_text:
                        text = " ".join(rc_text)
                    break

        # Concept URI mapped directly from Freeplane ID
        concept_uri = PKGC[node_id]

        # 1. Add base type and labels
        g.add((concept_uri, RDF.type, SKOS.Concept))
        if text:
            g.add((concept_uri, SKOS.prefLabel, Literal(text)))
        g.add((concept_uri, PKG.sourceMap, Literal(filename)))

        # 2. Add dates
        created = node_elem.get("CREATED")
        if created:
            date_str = parse_epoch(created)
            if date_str:
                g.add((concept_uri, DC.date, Literal(date_str, datatype=XSD.date)))
        
        # 3. Handle structure (SubTopics)
        if parent_uri:
            g.add((parent_uri, PKG.hasSubTopic, concept_uri))

        # 4. Handle external links (Resources)
        link = node_elem.get("LINK")
        if link and link.startswith("http"):
            res_id = f"res_{node_id}"
            res_uri = PKGR[res_id]
            g.add((res_uri, RDF.type, SCHEMA.WebPage))
            g.add((res_uri, SCHEMA.url, Literal(link, datatype=XSD.anyURI)))
            g.add((concept_uri, PKG.hasResource, res_uri))

        # 5. Handle Rich Content Notes (PersonalNote)
        for rc in node_elem.findall("richcontent"):
            if rc.get("TYPE") == "NOTE":
                # Extract inner text to strip HTML tags naturally
                text_content = "".join(rc.itertext()).strip()
                if text_content:
                    note_id = f"note_{node_id}"
                    note_uri = PKGN[note_id]
                    g.add((note_uri, RDF.type, PKG.PersonalNote))
                    g.add((note_uri, DC.title, Literal(text_content)))
                    g.add((concept_uri, PKG.hasNote, note_uri))

        # 6. Handle cross-links (arrowlink) -> skos:related
        for arrow in node_elem.findall("arrowlink"):
            dest = arrow.get("DESTINATION")
            if dest:
                dest_uri = PKGC[dest]
                g.add((concept_uri, SKOS.related, dest_uri))

        # 7. Basic Icon detection (e.g. Tasks mapping)
        for icon in node_elem.findall("icon"):
            builtin = icon.get("BUILTIN")
            if builtin == "button_ok":
                # Map to Task as defined in pkg_ontology.ttl
                task_uri = URIRef(str(concept_uri) + "_task")
                g.add((task_uri, RDF.type, PKG.Task))
                g.add((task_uri, PKG.status, Literal("done")))
                if text:
                    g.add((task_uri, DC.title, Literal(text)))
                g.add((concept_uri, PKG.hasTask, task_uri))

        # Recurse children
        for child in node_elem.findall("node"):
            traverse(child, parent_uri=concept_uri)

    # Begin traversal on root node(s)
    # The map structure has <node> as immediate children of <map>
    for child in root.findall("node"):
        traverse(child, parent_uri=None)

    # Save to file
    out_file = os.path.join(output_dir, filename.replace(".mm", ".ttl"))
    g.serialize(destination=out_file, format="turtle")
    print(f"  Success: Extracted {len(g)} triples -> {out_file}")

if __name__ == "__main__":
    maps_dir = "/Users/chunnodu/Library/Mobile Documents/com~apple~CloudDocs/Career/MindMaps"
    out_dir = "/Users/chunnodu/projects/graphrag/outputs"
    
    os.makedirs(out_dir, exist_ok=True)
    
    # Process all mm files directly to generate triples per map
    for f in os.listdir(maps_dir):
        if f.endswith(".mm") and not f.startswith("."):
            process_map(os.path.join(maps_dir, f), out_dir)
