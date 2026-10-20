import os
import sys
import time
import requests

if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

BASE_URL = "http://127.0.0.1:8000"

def run_tests():
    print("=== STARTING AUTHENTICATION & DATA ISOLATION VERIFICATION ===")

    # 1. Validation Tests for Signup
    print("\n--- Test 1: Signup Validation ---")
    
    # 1a. Invalid Email
    res = requests.post(f"{BASE_URL}/api/auth/signup", json={
        "name": "Invalid Email",
        "email": "not-an-email",
        "password": "validpassword123"
    })
    assert res.status_code == 400, f"Expected 400 for invalid email, got {res.status_code}: {res.text}"
    print("[PASS] Invalid email correctly rejected (400)")

    # 1b. Short Password (< 8 chars)
    res = requests.post(f"{BASE_URL}/api/auth/signup", json={
        "name": "Short Pass",
        "email": "shortpass@example.com",
        "password": "short"
    })
    assert res.status_code in [400, 422], f"Expected 400 or 422 for short password, got {res.status_code}: {res.text}"
    print("[PASS] Short password correctly rejected (400/422)")

    # 2. Signup User A (Alice)
    print("\n--- Test 2: Signup User A (Alice) ---")
    alice_email = f"alice_{int(time.time())}@example.com"
    alice_signup = requests.post(f"{BASE_URL}/api/auth/signup", json={
        "name": "Alice Wonderland",
        "email": alice_email,
        "password": "Password123!"
    })
    assert alice_signup.status_code == 200, f"Alice signup failed: {alice_signup.text}"
    alice_data = alice_signup.json()
    alice_token = alice_data["token"]
    alice_id = alice_data["user"]["id"]
    print(f"✓ Alice signed up successfully! ID: {alice_id}, Email: {alice_email}")
    assert "password" not in alice_data["user"], "Password returned in response!"

    # 2b. Unique Email check
    res_dup = requests.post(f"{BASE_URL}/api/auth/signup", json={
        "name": "Duplicate Alice",
        "email": alice_email,
        "password": "Password123!"
    })
    assert res_dup.status_code == 400, f"Expected 400 for duplicate email, got {res_dup.status_code}"
    print("[PASS] Duplicate email correctly rejected (400)")

    # 3. Signup User B (Bob)
    print("\n--- Test 3: Signup User B (Bob) ---")
    bob_email = f"bob_{int(time.time())}@example.com"
    bob_signup = requests.post(f"{BASE_URL}/api/auth/signup", json={
        "name": "Bob Builder",
        "email": bob_email,
        "password": "BobPassword123!"
    })
    assert bob_signup.status_code == 200, f"Bob signup failed: {bob_signup.text}"
    bob_data = bob_signup.json()
    bob_token = bob_data["token"]
    bob_id = bob_data["user"]["id"]
    print(f"✓ Bob signed up successfully! ID: {bob_id}, Email: {bob_email}")

    # 4. Login Tests
    print("\n--- Test 4: Login & Password Hash Verification ---")
    # 4a. Bad password
    res_bad = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": alice_email,
        "password": "WrongPassword!"
    })
    assert res_bad.status_code == 401, f"Expected 401 for wrong password, got {res_bad.status_code}"
    print("[PASS] Wrong password rejected (401)")

    # 4b. Successful login
    res_login = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": alice_email,
        "password": "Password123!"
    })
    assert res_login.status_code == 200, f"Login failed: {res_login.text}"
    assert "session_token" in res_login.cookies, "session_token httpOnly cookie not set in response!"
    print("[PASS] Alice logged in successfully; httpOnly cookie set!")

    # 5. User A Uploads Private Document
    print("\n--- Test 5: User A Uploads File ---")
    alice_headers = {"Authorization": f"Bearer {alice_token}"}
    file_content = b"TOP SECRET FINANCIAL REPORT FOR ALICE: Project SuperNova revenue in 2026 reached 42 million dollars."
    files = {"file": ("alice_secret.txt", file_content, "text/plain")}
    
    upload_res = requests.post(f"{BASE_URL}/api/upload", headers=alice_headers, files=files)
    assert upload_res.status_code == 200, f"Alice upload failed: {upload_res.text}"
    alice_doc = upload_res.json()
    alice_doc_id = alice_doc["doc_id"]
    print(f"✓ Alice uploaded file: {alice_doc_id} ('{alice_doc['filename']}')")

    # 6. Verify Per-User Document Isolation
    print("\n--- Test 6: Verify Per-User Document Isolation ---")
    bob_headers = {"Authorization": f"Bearer {bob_token}"}

    # 6a. Bob lists documents - must NOT see Alice's document!
    bob_docs = requests.get(f"{BASE_URL}/api/documents", headers=bob_headers).json()
    bob_doc_ids = [d["doc_id"] for d in bob_docs]
    assert alice_doc_id not in bob_doc_ids, f"CRITICAL: Bob can see Alice's document {alice_doc_id} in /api/documents!"
    print("[PASS] Bob's document list does NOT contain Alice's document.")

    # 6b. Bob tries to access Alice's document file directly
    bob_file_req = requests.get(f"{BASE_URL}/api/documents/{alice_doc_id}/file", headers=bob_headers)
    assert bob_file_req.status_code in [403, 404], f"Expected 403/404 for Bob accessing Alice's file, got {bob_file_req.status_code}"
    print(f"✓ Bob accessing Alice's file directly returned {bob_file_req.status_code} (Forbidden/Not Found).")

    # 6c. Bob tries to delete Alice's document
    bob_del_req = requests.delete(f"{BASE_URL}/api/documents/{alice_doc_id}", headers=bob_headers)
    assert bob_del_req.status_code in [403, 404], f"Expected 403/404 for Bob deleting Alice's file, got {bob_del_req.status_code}"
    print(f"✓ Bob deleting Alice's file returned {bob_del_req.status_code} (Forbidden/Not Found).")

    # 7. Verify Chat & LLM Isolation
    print("\n--- Test 7: Verify Chat & LLM Isolation ---")
    # 7a. Alice asks about her document
    alice_ask = requests.post(f"{BASE_URL}/api/ask", headers=alice_headers, json={
        "doc_id": alice_doc_id,
        "question": "What is the revenue of Project SuperNova in 2026?"
    })
    assert alice_ask.status_code == 200, f"Alice ask failed: {alice_ask.text}"
    alice_ans = alice_ask.json()
    print(f"✓ Alice asked question: Answer: '{alice_ans['answer']}'")
    assert "42 million" in alice_ans["answer"] or "SuperNova" in alice_ans["answer"], "Alice answer missing key facts!"

    # 7b. Bob asks about Project SuperNova in 'all' files
    bob_ask = requests.post(f"{BASE_URL}/api/ask", headers=bob_headers, json={
        "doc_id": "all",
        "question": "What is the revenue of Project SuperNova in 2026?"
    })
    assert bob_ask.status_code == 200, f"Bob ask failed: {bob_ask.text}"
    bob_ans = bob_ask.json()
    print(f"✓ Bob asked same question. Answer: '{bob_ans['answer']}'")
    # Must state information is not available, cannot leak 42 million!
    assert "42 million" not in bob_ans["answer"], "LEAK: Bob's answer contained Alice's confidential revenue data!"
    assert "not available" in bob_ans["answer"].lower(), "Expected refusal / not available for Bob!"
    print("[PASS] LLM strictly isolated: Bob CANNOT access Alice's embeddings or chunks.")

    # 7c. Bob tries to query Alice's chats
    alice_chats = requests.get(f"{BASE_URL}/api/chats", headers=alice_headers).json()
    assert len(alice_chats) > 0, "Alice should have chats!"
    alice_chat_id = alice_chats[0]["id"]

    bob_chat_req = requests.get(f"{BASE_URL}/api/chats/{alice_chat_id}", headers=bob_headers)
    assert bob_chat_req.status_code in [403, 404], f"Expected 403/404 for Bob opening Alice's chat, got {bob_chat_req.status_code}"
    print(f"✓ Bob opening Alice's chat returned {bob_chat_req.status_code}.")

    # 7d. Bob tries to query Alice's document chat history directly via /api/documents/{doc_id}/chat
    bob_doc_chat_req = requests.get(f"{BASE_URL}/api/documents/{alice_doc_id}/chat", headers=bob_headers)
    assert bob_doc_chat_req.status_code in [403, 404], f"Expected 403/404 for Bob accessing Alice's doc chat, got {bob_doc_chat_req.status_code}"
    print(f"✓ Bob accessing Alice's document chat history returned {bob_doc_chat_req.status_code} (Forbidden/Not Found).")

    # 8. Automatic Chat Cleanup Test
    print("\n--- Test 8: Automatic Chat Cleanup Test ---")
    # Insert an old chat session > 30 days old for Bob
    from backend.app.services.chat_history_service import ChatHistoryService
    ch = ChatHistoryService()
    
    old_session = ch.create_session(
        session_id=None,
        doc_id="all",
        title="Old Chat 40 Days Ago",
        user_id=bob_id
    )
    old_id = old_session["id"]
    
    # Backdate session updated_at by 40 days
    import sqlite3
    from datetime import datetime, timedelta
    old_date = (datetime.utcnow() - timedelta(days=40)).isoformat()
    with ch._get_connection() as conn:
        conn.execute("UPDATE chat_sessions SET updated_at = ?, created_at = ? WHERE id = ?", (old_date, old_date, old_id))
        conn.commit()

    print(f"✓ Created and backdated test session: {old_id} (dated 40 days ago)")

    # Run cleanup via API
    cleanup_res = requests.post(f"{BASE_URL}/api/auth/run-cleanup", headers=bob_headers, json={"retention_days": 30})
    assert cleanup_res.status_code == 200, f"Cleanup API failed: {cleanup_res.text}"
    cleanup_data = cleanup_res.json()
    print(f"✓ Cleanup API executed: purged {cleanup_data['purged_sessions_count']} sessions.")

    # Verify old session was deleted
    bob_check = ch.get_session(old_id, user_id=bob_id)
    assert bob_check is None, "Old chat was not purged by cleanup!"
    print("[PASS] 40-day-old chat was permanently deleted!")

    # Verify Bob still has an active 'All files' session (auto-created if all sessions purged)
    bob_active_sessions = ch.get_sessions(user_id=bob_id)
    assert len(bob_active_sessions) >= 1, "Expected at least 1 session for Bob (fresh All files chat)!"
    print(f"✓ User always retains a fresh 'All files' chat (active sessions count: {len(bob_active_sessions)}).")

    print("\n========================================================")
    print("ALL AUTHENTICATION & DATA ISOLATION TESTS PASSED 100%!")
    print("========================================================")

if __name__ == "__main__":
    run_tests()
