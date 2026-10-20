import os
import sys
import time
from pathlib import Path
from dotenv import load_dotenv

# Ensure backend root is on sys.path
BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent
for p in [str(ROOT_DIR), str(BASE_DIR)]:
    if p in sys.path:
        sys.path.remove(p)
sys.path.insert(0, str(ROOT_DIR))
sys.path.insert(0, str(BASE_DIR))

load_dotenv(BASE_DIR / ".env")

from fastapi.testclient import TestClient
from main import app, vector_store, llm_service

def run_all_tests():
    print("=" * 60)
    print("RUNNING COMPREHENSIVE RAG SYSTEM TESTS")
    print("=" * 60)

    client = TestClient(app)
    start_total = time.time()

    # 1. Health check
    t0 = time.time()
    res = client.get("/api/health")
    assert res.status_code == 200, f"Health check failed: {res.text}"
    health_data = res.json()
    assert health_data["status"] == "healthy"
    print(f"[PASS] /api/health ({time.time() - t0:.3f}s) - Status: {health_data['status']}, Docs: {health_data['documents_count']}")

    # Authenticate for subsequent protected routes
    auth_email = f"suite_runner_{int(time.time())}@example.com"
    signup_res = client.post("/api/auth/signup", json={
        "name": "Suite Runner",
        "email": auth_email,
        "password": "Password123!"
    })
    assert signup_res.status_code == 200, f"Signup failed: {signup_res.text}"
    token = signup_res.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}
    client.headers.update(headers)

    # Upload test document for Suite Runner
    sample_content = b"Cloud Security Overview: Key best practices include MFA, least privilege access, encryption at rest and in transit, and continuous monitoring."
    upload_res = client.post(
        "/api/upload",
        files={"file": ("cloud_security_test.txt", sample_content, "text/plain")}
    )
    assert upload_res.status_code == 200, f"Upload failed: {upload_res.text}"

    # 2. List documents
    t0 = time.time()
    res = client.get("/api/documents")
    assert res.status_code == 200, f"Documents list failed: {res.text}"
    docs = res.json()
    assert isinstance(docs, list) and len(docs) > 0, "No documents found in registry"
    first_doc = docs[0]
    doc_id = first_doc["doc_id"]
    filename = first_doc["filename"]
    print(f"[PASS] /api/documents ({time.time() - t0:.3f}s) - {len(docs)} document(s) registered (Selected: '{filename}')")

    # 3. Get document page details
    t0 = time.time()
    res = client.get(f"/api/documents/{doc_id}/pages/1")
    assert res.status_code == 200, f"Page details failed: {res.text}"
    page_data = res.json()
    assert page_data["page"] == 1
    assert "content" in page_data
    print(f"[PASS] /api/documents/{doc_id}/pages/1 ({time.time() - t0:.3f}s) - Content length: {len(page_data['content'])} chars")

    # 4. Get document raw file endpoint
    t0 = time.time()
    res = client.get(f"/api/documents/{doc_id}/file")
    assert res.status_code == 200, f"File fetch failed: {res.text}"
    assert len(res.content) > 0
    print(f"[PASS] /api/documents/{doc_id}/file ({time.time() - t0:.3f}s) - Received {len(res.content)} bytes")

    # 5. Suggested questions endpoint
    t0 = time.time()
    res = client.get(f"/api/documents/{doc_id}/suggested-questions")
    assert res.status_code == 200, f"Suggested questions failed: {res.text}"
    sq_data = res.json()
    questions = sq_data.get("suggested_questions", []) if isinstance(sq_data, dict) else sq_data
    assert isinstance(questions, list) and len(questions) > 0
    print(f"[PASS] /api/documents/{doc_id}/suggested-questions ({time.time() - t0:.3f}s) - {len(questions)} questions returned")

    # 6. Ask question endpoint (RAG query + LLM answering)
    t0 = time.time()
    question = "What is the primary topic of this document?"
    res = client.post("/api/ask", json={"doc_id": doc_id, "question": question})
    assert res.status_code == 200, f"Ask question failed: {res.text}"
    answer_data = res.json()
    assert "answer" in answer_data and len(answer_data["answer"]) > 10
    assert "sources" in answer_data
    print(f"[PASS] /api/ask ({time.time() - t0:.3f}s)")
    print(f"       Answer preview: {answer_data['answer'][:120]}...")
    print(f"       Sources: {answer_data['sources']}")
    print(f"       Suggested follow-ups: {len(answer_data.get('suggested_questions', []))}")

    # 7. Ask question with 'all' documents
    t0 = time.time()
    res = client.post("/api/ask", json={"doc_id": "all", "question": "What skills or topics are mentioned across documents?"})
    assert res.status_code == 200, f"Ask all documents failed: {res.text}"
    all_data = res.json()
    assert len(all_data["answer"]) > 10
    print(f"[PASS] /api/ask (all documents) ({time.time() - t0:.3f}s) - Sources: {all_data['sources']}")

    # 8. Chat history
    t0 = time.time()
    res = client.get(f"/api/documents/{doc_id}/chat")
    assert res.status_code == 200, f"Chat history failed: {res.text}"
    history_data = res.json()
    messages = history_data.get("messages", []) if isinstance(history_data, dict) else history_data
    assert isinstance(messages, list)
    print(f"[PASS] /api/documents/{doc_id}/chat ({time.time() - t0:.3f}s) - {len(messages)} messages in session")

    total_time = time.time() - start_total
    print("=" * 60)
    print(f"ALL 8 TEST PHASES PASSED IN {total_time:.2f}s!")
    print("=" * 60)

if __name__ == "__main__":
    run_all_tests()
