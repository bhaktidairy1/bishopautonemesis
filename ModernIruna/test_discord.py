import os
from dotenv import load_dotenv
import requests

load_dotenv()
webhook_url = os.environ.get("DISCORD_WEBHOOK_URL")

if not webhook_url:
    print("[-] Webhook URL not found in .env")
    exit(1)

print(f"[*] Webhook URL: {webhook_url}")

with open("test_log.txt", "w") as f:
    f.write("This is a test log file from the server.\nIt contains some packet dumps.")

try:
    with open("test_log.txt", "rb") as f:
        print("[*] Sending file to discord...")
        response = requests.post(
            webhook_url,
            files={"file": ("test_log.txt", f)},
            timeout=10
        )
    print(f"[*] Response Status: {response.status_code}")
    print(f"[*] Response Body: {response.text}")
except Exception as e:
    print(f"[-] Error: {e}")
