import sys, os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ['PYTHONIOENCODING'] = 'utf-8'
from dotenv import load_dotenv
load_dotenv()

from app.services.vector_store import VectorStoreService
from app.services.llm_service import LLMService

vs = VectorStoreService()
llm = LLMService()

# Use the resume doc
doc_id = "908bda10-d215-4901-92b3-18ecdec71a7e"
question = "What is this document about?"

print(f"Gemini key set: {bool(llm.gemini_api_key)}")
print(f"OpenAI key set: {bool(llm.openai_api_key)}")

chunks, metas, sources = vs.retrieve_top_chunks(doc_id, question, n_results=4)
print(f"Chunks retrieved: {len(chunks)}")
print(f"Sources: {sources}")

if chunks:
    answer = llm.generate_answer(question, chunks, metas)
    print(f"\nAnswer: {answer}")
else:
    print("NO CHUNKS - would return fallback message")
