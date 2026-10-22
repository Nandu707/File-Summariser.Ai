import sys
import os
import requests
import json
import time

BASE_URL = "http://localhost:8000"
ADMIN_EMAIL = "admin@summariser.ai"
ADMIN_PASSWORD = "AdminPassword123!"

results = []

def record(test_num, title, passed, details=""):
    status_str = "PASS" if passed else "FAIL"
    print(f"[{status_str}] Test {test_num}: {title}")
    if details:
        print(f"       Details: {details}")
    results.append({
        "test": test_num,
        "title": title,
        "passed": passed,
        "details": details
    })

def main():
    print("=" * 70)
    print("STARTING ACCESS MODEL VERIFICATION TESTS")
    print("=" * 70)

    # Clean up any previous test users from DB if needed
    # Generate unique emails with timestamp to be idempotent
    ts = int(time.time())
    user1_email = f"user1_{ts}@example.com"
    user2_email = f"user2_{ts}@example.com"
    user3_email = f"user3_{ts}@example.com"
    user4_email = f"user4_{ts}@example.com"
    test_pwd = "UserPass123!"

    # -------------------------------------------------------------
    # TEST 1: Normal signup pending & admin signup refused
    # -------------------------------------------------------------
    # 1a. Normal signup
    res_signup = requests.post(f"{BASE_URL}/api/auth/signup", json={
        "name": "Normal User 1",
        "email": user1_email,
        "password": test_pwd
    })
    t1_signup_ok = (res_signup.status_code == 200 and res_signup.json().get("status") == "pending")

    # 1b. Normal login blocked with pending message
    res_login_pending = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": user1_email,
        "password": test_pwd
    })
    t1_login_blocked = (
        res_login_pending.status_code == 403 and
        "waiting for admin approval" in res_login_pending.json().get("detail", "").lower()
    )

    # 1c. Try signing up with ADMIN_EMAIL
    res_admin_signup = requests.post(f"{BASE_URL}/api/auth/signup", json={
        "name": "Attacker Admin",
        "email": ADMIN_EMAIL,
        "password": "HackerPassword!"
    })
    t1_admin_signup_blocked = (
        res_admin_signup.status_code == 400 and
        "cannot be used" in res_admin_signup.json().get("detail", "").lower()
    )

    t1_pass = t1_signup_ok and t1_login_blocked and t1_admin_signup_blocked
    record(1, "Sign up pending, login blocked with pending message, ADMIN_EMAIL signup refused",
           t1_pass,
           f"Signup status: {res_signup.json().get('status')}; Login msg: '{res_login_pending.json().get('detail')}'; Admin signup refusal: '{res_admin_signup.json().get('detail')}'")

    # -------------------------------------------------------------
    # TEST 2: Admin approves user1, user1 can login; Reject user2
    # -------------------------------------------------------------
    # Login as admin
    res_admin_login = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    assert res_admin_login.status_code == 200, f"Admin login failed: {res_admin_login.text}"
    admin_token = res_admin_login.json()["token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    # Clean up any leftover documents from previous runs
    existing_docs = requests.get(f"{BASE_URL}/api/documents", headers=admin_headers).json()
    if isinstance(existing_docs, list):
        for doc in existing_docs:
            requests.delete(f"{BASE_URL}/api/documents/{doc['doc_id']}", headers=admin_headers)

    # Get user list to find user1's ID
    res_users = requests.get(f"{BASE_URL}/api/auth/admin/users", headers=admin_headers)
    all_users = res_users.json()
    u1_obj = next((u for u in all_users if u["email"].lower() == user1_email.lower()), None)
    assert u1_obj, f"User1 not found in admin user list"
    u1_id = u1_obj["id"]

    # Approve user1
    res_u1_appr = requests.post(f"{BASE_URL}/api/auth/admin/users/{u1_id}/approve", headers=admin_headers)
    t2_appr_ok = (res_u1_appr.status_code == 200)

    # User1 now logs in successfully
    res_u1_login = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": user1_email,
        "password": test_pwd
    })
    t2_u1_login_ok = (res_u1_login.status_code == 200 and "token" in res_u1_login.json())
    u1_token = res_u1_login.json()["token"]
    u1_headers = {"Authorization": f"Bearer {u1_token}"}

    # Signup user2 and reject them
    requests.post(f"{BASE_URL}/api/auth/signup", json={
        "name": "Normal User 2",
        "email": user2_email,
        "password": test_pwd
    })
    res_users2 = requests.get(f"{BASE_URL}/api/auth/admin/users", headers=admin_headers)
    u2_obj = next((u for u in res_users2.json() if u["email"].lower() == user2_email.lower()), None)
    u2_id = u2_obj["id"]
    requests.post(f"{BASE_URL}/api/auth/admin/users/{u2_id}/reject", headers=admin_headers)

    res_u2_login = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": user2_email,
        "password": test_pwd
    })
    t2_u2_rejected_blocked = (
        res_u2_login.status_code == 403 and
        "rejected" in res_u2_login.json().get("detail", "").lower()
    )

    t2_pass = t2_appr_ok and t2_u1_login_ok and t2_u2_rejected_blocked
    record(2, "Admin approves user1 (login succeeds); Reject user2 (login blocked)",
           t2_pass,
           f"User1 login OK: {t2_u1_login_ok}; User2 rejected message: '{res_u2_login.json().get('detail')}'")

    # -------------------------------------------------------------
    # TEST 3: Sending 'role': 'admin' in sign-up is ignored
    # -------------------------------------------------------------
    requests.post(f"{BASE_URL}/api/auth/signup", json={
        "name": "Role Faker",
        "email": user3_email,
        "password": test_pwd,
        "role": "admin",
        "status": "approved"
    })
    res_users3 = requests.get(f"{BASE_URL}/api/auth/admin/users", headers=admin_headers)
    u3_obj = next((u for u in res_users3.json() if u["email"].lower() == user3_email.lower()), None)
    t3_pass = (u3_obj is not None and u3_obj["role"] == "user" and u3_obj["status"] == "pending")
    record(3, "Send role='admin' in signup request is ignored by server",
           t3_pass,
           f"Stored role: {u3_obj.get('role')}, stored status: {u3_obj.get('status')}")

    # -------------------------------------------------------------
    # TEST 4: Normal user calling upload, replace, delete, approve returns 403
    # -------------------------------------------------------------
    # 4a. Upload
    files_dummy = {"file": ("dummy.txt", b"Hello test content", "text/plain")}
    res_u1_upload = requests.post(f"{BASE_URL}/api/upload", files=files_dummy, headers=u1_headers)

    # 4b. Replace
    res_u1_replace = requests.post(f"{BASE_URL}/api/documents/non_existent/replace", files=files_dummy, headers=u1_headers)

    # 4c. Delete doc
    res_u1_delete_doc = requests.delete(f"{BASE_URL}/api/documents/non_existent", headers=u1_headers)

    # 4d. Approve user
    res_u1_approve = requests.post(f"{BASE_URL}/api/auth/admin/users/{u3_obj['id']}/approve", headers=u1_headers)

    t4_pass = (
        res_u1_upload.status_code == 403 and
        res_u1_replace.status_code == 403 and
        res_u1_delete_doc.status_code == 403 and
        res_u1_approve.status_code == 403
    )
    record(4, "Normal user calling upload, replace, delete, and approve endpoints returns 403",
           t4_pass,
           f"Upload status: {res_u1_upload.status_code}, Replace status: {res_u1_replace.status_code}, Delete status: {res_u1_delete_doc.status_code}, Approve status: {res_u1_approve.status_code}")

    # -------------------------------------------------------------
    # TEST 5: Admin uploads F1; user asks about F1 & gets answer with source tag
    # -------------------------------------------------------------
    with open("test_docs/file_a_project_aurora.txt", "rb") as f:
        f1_data = f.read()
    res_f1_upload = requests.post(
        f"{BASE_URL}/api/upload",
        files={"file": ("file_a_project_aurora.txt", f1_data, "text/plain")},
        headers=admin_headers
    )
    assert res_f1_upload.status_code == 200, f"F1 upload failed: {res_f1_upload.text}"
    f1_doc_id = res_f1_upload.json()["doc_id"]
    print(f"       Uploaded F1: doc_id={f1_doc_id}")

    # User asks question about F1
    res_q1 = requests.post(
        f"{BASE_URL}/api/chats/ask",
        json={
            "doc_id": f1_doc_id,
            "question": "What spectrometer does Project Aurora carry and what is its primary mission?"
        },
        headers=u1_headers
    )
    t5_q1_ok = (res_q1.status_code == 200)
    q1_answer = res_q1.json().get("answer", "")
    q1_sources = res_q1.json().get("source_documents", []) or [s.get("filename") for s in res_q1.json().get("source_details", [])]
    t5_content_ok = ("spectroscan" in q1_answer.lower() or "spectrometer" in q1_answer.lower())
    t5_source_ok = any("file_a_project_aurora" in str(s).lower() for s in q1_sources)
    t5_pass = t5_q1_ok and t5_content_ok and t5_source_ok
    record(5, "Admin uploads F1; user asks about F1 and gets answer with source tag",
           t5_pass,
           f"Answer: '{q1_answer[:100]}...'; Sources: {q1_sources}")

    # Save user1's chat ID for F1 immediately while F1 is active
    u1_f1_chat_id = res_q1.json().get("chat_id")
    if not u1_f1_chat_id:
        res_u1_chats_init = requests.get(f"{BASE_URL}/api/chats", headers=u1_headers).json()
        f1_session_init = next((s for s in res_u1_chats_init if s.get("file_id") == f1_doc_id), None)
        u1_f1_chat_id = f1_session_init["id"] if f1_session_init else None
    print(f"       User1 chat_id for F1: {u1_f1_chat_id}")

    # -------------------------------------------------------------
    # TEST 6: Admin uploads F2 without restart; user asks about F2 & both
    # -------------------------------------------------------------
    with open("test_docs/file_b_project_borealis.txt", "rb") as f:
        f2_data = f.read()
    res_f2_upload = requests.post(
        f"{BASE_URL}/api/upload",
        files={"file": ("file_b_project_borealis.txt", f2_data, "text/plain")},
        headers=admin_headers
    )
    assert res_f2_upload.status_code == 200, f"F2 upload failed: {res_f2_upload.text}"
    f2_doc_id = res_f2_upload.json()["doc_id"]
    print(f"       Uploaded F2: doc_id={f2_doc_id}")

    # User asks about F2
    res_q2 = requests.post(
        f"{BASE_URL}/api/chats/ask",
        json={
            "doc_id": f2_doc_id,
            "question": "What autonomous robotic submersibles are used in Project Borealis?"
        },
        headers=u1_headers
    )
    q2_answer = res_q2.json().get("answer", "")
    q2_sources = res_q2.json().get("source_documents", []) or [s.get("filename") for s in res_q2.json().get("source_details", [])]
    t6_f2_ok = ("subzero-4" in q2_answer.lower() or "subzero" in q2_answer.lower())

    # User asks across 'All files' requiring both F1 and F2
    res_q_all = requests.post(
        f"{BASE_URL}/api/chats/ask",
        json={
            "doc_id": "all",
            "question": "Compare Project Aurora and Project Borealis: what are their key instruments or vehicles?"
        },
        headers=u1_headers
    )
    q_all_answer = res_q_all.json().get("answer", "")
    q_all_sources = res_q_all.json().get("source_documents", []) or [s.get("filename") for s in res_q_all.json().get("source_details", [])]
    all_files_cited = {s for s in q_all_sources}
    t6_both_cited = (
        ("spectroscan" in q_all_answer.lower() or "aurora" in q_all_answer.lower()) and
        ("subzero" in q_all_answer.lower() or "borealis" in q_all_answer.lower()) and
        len(all_files_cited) >= 2
    )

    t6_pass = t6_f2_ok and t6_both_cited
    record(6, "Admin uploads F2 without restart; User asks about F2 and gets correct answer; All files queries both",
           t6_pass,
           f"F2 answer contains SubZero-4: {t6_f2_ok}; Both files cited in All files: {all_files_cited}")

    # -------------------------------------------------------------
    # TEST 7: Admin deletes F1; user chat about F1 becomes read-only;
    # Asking in All files says info not available
    # -------------------------------------------------------------
    # Get user1's chat session about F1
    u1_f1_chat_id = res_q1.json().get("chat_id")
    if not u1_f1_chat_id:
        res_u1_s_temp = requests.get(f"{BASE_URL}/api/chats", headers=u1_headers).json()
        f1_s_temp = next((s for s in res_u1_s_temp if s.get("file_id") == f1_doc_id), None)
        u1_f1_chat_id = f1_s_temp["id"] if f1_s_temp else None

    # Admin deletes F1
    res_del_f1 = requests.delete(f"{BASE_URL}/api/documents/{f1_doc_id}", headers=admin_headers)
    assert res_del_f1.status_code == 200, f"F1 delete failed: {res_del_f1.text}"

    # Verify user1's session for F1 is still visible and marked deleted
    res_u1_sessions = requests.get(f"{BASE_URL}/api/chats", headers=u1_headers)
    u1_sessions = res_u1_sessions.json()
    f1_session = next((s for s in u1_sessions if s["id"] == u1_f1_chat_id or s.get("file_id") == f1_doc_id), None)
    t7_session_marked_deleted = (
        f1_session is not None and
        (f1_session.get("is_deleted") is True or f1_session.get("is_file_deleted") is True)
    )

    # Asking a new question in the deleted file's chat fails with read-only error
    res_q_deleted_chat = requests.post(
        f"{BASE_URL}/api/chats/ask",
        json={
            "chat_id": u1_f1_chat_id,
            "question": "Tell me more about Aurora."
        },
        headers=u1_headers
    )
    t7_chat_blocked_readonly = (
        res_q_deleted_chat.status_code == 400 and
        "read-only" in res_q_deleted_chat.json().get("detail", "").lower()
    )

    # Asking in 'All files' about something only in F1 says information not available
    res_q_aurora_all = requests.post(
        f"{BASE_URL}/api/chats/ask",
        json={
            "doc_id": "all",
            "question": "What is the exact altitude and spectrometer of Project Aurora?"
        },
        headers=u1_headers
    )
    aurora_ans_after_del = res_q_aurora_all.json().get("answer", "")
    aurora_sources_after_del = res_q_aurora_all.json().get("source_documents", []) or [s.get("filename") for s in res_q_aurora_all.json().get("source_details", [])]
    # Should say not found/not mentioned/not available and cite NO F1 sources
    t7_no_f1_sources = not any("file_a_project_aurora" in str(s).lower() for s in aurora_sources_after_del)
    t7_not_available_ans = (
        "not available" in aurora_ans_after_del.lower() or
        "does not mention" in aurora_ans_after_del.lower() or
        "no information" in aurora_ans_after_del.lower() or
        "not mentioned" in aurora_ans_after_del.lower() or
        "not found" in aurora_ans_after_del.lower() or
        "not provide" in aurora_ans_after_del.lower() or
        "not contain" in aurora_ans_after_del.lower()
    )
    t7_pass = t7_session_marked_deleted and t7_chat_blocked_readonly and t7_no_f1_sources and t7_not_available_ans
    record(7, "Admin deletes F1: chat marked read-only with 'File deleted', All files says info not available",
           t7_pass,
           f"Session is_deleted: {f1_session.get('is_deleted') if f1_session else None}; Readonly blocked: {t7_chat_blocked_readonly}; F1 in sources: {not t7_no_f1_sources}; Answer: '{aurora_ans_after_del[:80]}...'")

    # -------------------------------------------------------------
    # TEST 8: Two different users cannot see or touch each other's chats
    # -------------------------------------------------------------
    # Signup & approve user4
    requests.post(f"{BASE_URL}/api/auth/signup", json={
        "name": "User 4",
        "email": user4_email,
        "password": test_pwd
    })
    res_users4 = requests.get(f"{BASE_URL}/api/auth/admin/users", headers=admin_headers)
    u4_obj = next((u for u in res_users4.json() if u["email"].lower() == user4_email.lower()), None)
    requests.post(f"{BASE_URL}/api/auth/admin/users/{u4_obj['id']}/approve", headers=admin_headers)

    res_u4_login = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": user4_email,
        "password": test_pwd
    })
    u4_token = res_u4_login.json()["token"]
    u4_headers = {"Authorization": f"Bearer {u4_token}"}

    # User4 creates a chat session
    res_u4_chat = requests.post(
        f"{BASE_URL}/api/chats/ask",
        json={"doc_id": "all", "question": "Hello from user 4"},
        headers=u4_headers
    )
    u4_chat_id = res_u4_chat.json()["chat_id"]

    # User1 attempts to view User4's chat
    res_u1_peek = requests.get(f"{BASE_URL}/api/chats/{u4_chat_id}", headers=u1_headers)
    t8_peek_blocked = (res_u1_peek.status_code in (403, 404))

    # User1 attempts to delete User4's chat
    res_u1_delete = requests.delete(f"{BASE_URL}/api/chats/{u4_chat_id}", headers=u1_headers)
    t8_delete_blocked = (res_u1_delete.status_code in (403, 404))

    # Admin also cannot peek into User4's chat (intentional design: user chats are private)
    res_admin_peek = requests.get(f"{BASE_URL}/api/chats/{u4_chat_id}", headers=admin_headers)
    t8_admin_peek_blocked = (res_admin_peek.status_code in (403, 404))

    t8_pass = t8_peek_blocked and t8_delete_blocked and t8_admin_peek_blocked
    record(8, "Chat privacy: User1 cannot read/delete User4's chat (returns 404/403); Admin cannot read user chats",
           t8_pass,
           f"User1 peek status: {res_u1_peek.status_code}; User1 delete status: {res_u1_delete.status_code}; Admin peek status: {res_admin_peek.status_code}")

    # -------------------------------------------------------------
    # TEST 9: Admin disables a logged-in user; user's next request fails & logged out
    # -------------------------------------------------------------
    res_disable = requests.post(f"{BASE_URL}/api/auth/admin/users/{u1_id}/disable", headers=admin_headers)
    assert res_disable.status_code == 200, f"Disable user failed: {res_disable.text}"

    # User1 tries to make a request with their existing token
    res_u1_after_disable = requests.get(f"{BASE_URL}/api/documents", headers=u1_headers)
    t9_pass = (
        res_u1_after_disable.status_code == 403 and
        "disabled" in res_u1_after_disable.json().get("detail", "").lower()
    )
    record(9, "Admin disables logged-in user: next request fails immediately with 403 disabled message",
           t9_pass,
           f"Response status: {res_u1_after_disable.status_code}; Detail: '{res_u1_after_disable.json().get('detail')}'")

    print("=" * 70)
    all_passed = all(r["passed"] for r in results)
    print(f"TEST SUMMARY: {sum(1 for r in results if r['passed'])} / {len(results)} PASSED")
    print("=" * 70)
    if not all_passed:
        sys.exit(1)

if __name__ == "__main__":
    main()
