"""Re-index all TTL files into LanceDB. Run from project root."""
import gc
import os
import lancedb
from fastembed import TextEmbedding
from ingest.embed import process_one_ttl
from retrieval.models import DB_PATH  # correct path: project_root/pkg_lancedb

OUTPUTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "outputs")

ttl_files = sorted([
    os.path.join(OUTPUTS_DIR, f)
    for f in os.listdir(OUTPUTS_DIR)
    if f.endswith(".ttl")
])

print(f"Found {len(ttl_files)} TTL files in {OUTPUTS_DIR}")
print("Loading model...")
model = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")
print("Model ready.\n")

grand_total = 0
for idx, fpath in enumerate(ttl_files):
    grand_total += process_one_ttl(fpath, model, DB_PATH, first=(idx == 0))
    gc.collect()

print(f"\nTotal concepts embedded: {grand_total:,}")

db = lancedb.connect(DB_PATH)
table = db.open_table("concepts")
print("Building FTS index...", end=" ", flush=True)
table.create_fts_index("label", replace=True)
print("done.")
print(f"Final row count: {table.count_rows():,}")
print("\nDone. Restart Claude to reload the MCP server.")
