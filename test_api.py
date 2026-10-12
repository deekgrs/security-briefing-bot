"""One-off check: confirm the Gemini API key works and see the raw reply."""
import os

import requests
from dotenv import load_dotenv

load_dotenv()

api_key = os.environ.get("GEMINI_API_KEY")
if not api_key:
    raise SystemExit("GEMINI_API_KEY not found. Check that .env exists in this folder.")

response = requests.post(
    "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
    headers={
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    },
    json={
        "model": "gemini-3.5-flash-lite",
        "messages": [{"role": "user", "content": "Say hello in five words."}],
    },
    timeout=30,
)

print("Status:", response.status_code)
print("Content-Type:", response.headers.get("content-type"))
print("Body:", response.text[:500])