import urllib.request
import json
import time

t0 = time.time()
payload = json.dumps({"question": "Summarize the key information."}).encode("utf-8")
req = urllib.request.Request(
    "http://127.0.0.1:8000/api/ask",
    data=payload,
    headers={"Content-Type": "application/json"}
)

try:
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        print(f"Total Response Time: {time.time() - t0:.2f}s")
        print(f"Model: {data.get('model_used')}")
        print(f"Suggested questions: {data.get('suggested_questions')}")
        print(f"Answer: {data.get('answer')[:120]}...")
except Exception as e:
    print(f"Request failed: {e}")
