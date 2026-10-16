import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from dotenv import load_dotenv
load_dotenv()

from app.services.vector_store import VectorStoreService

vs = VectorStoreService()
print(f"Persist dir: {vs.persist_dir}")
print(f"Collection name: {vs.collection.name}")
print(f"Collection count: {vs.collection.count()}")

# List all collections
cols = vs.client.list_collections()
print(f"\nAll collections: {[c.name for c in cols]}")
for c in cols:
    col = vs.client.get_collection(c.name)
    print(f"  {c.name}: {col.count()} chunks")

# Check registry
docs = vs.list_documents()
print(f"\nRegistry documents: {len(docs)}")
for d in docs:
    print(f"  {d['doc_id']}: {d['filename']} ({d['chunks']} chunks)")

# Try retrieving chunks for each document
for d in docs:
    doc_id = d['doc_id']
    chunks, metas, sources = vs.retrieve_top_chunks(doc_id, "What is this document about?", n_results=4)
    print(f"\n  retrieve_top_chunks for {d['filename']}:")
    print(f"    chunks returned: {len(chunks)}")
    print(f"    sources: {sources}")
    if chunks:
        print(f"    first chunk preview: {chunks[0][:100]}...")
    else:
        print(f"    NO CHUNKS RETURNED!")
        # Check if doc exists in collection directly
        matching = vs.collection.get(where={"doc_id": doc_id})
        print(f"    Direct get from '{vs.collection.name}': {len(matching['ids']) if matching and matching['ids'] else 0} ids")
