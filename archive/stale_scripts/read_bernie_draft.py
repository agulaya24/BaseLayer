"""Read Gmail drafts and find the one mentioning Bernie Sanders."""

import base64
import os
import sys
from pathlib import Path

CREDENTIALS_FILE = Path(os.environ.get("GMAIL_CREDENTIALS", Path.home() / ".config" / "baselayer" / "credentials.json"))
TOKEN_FILE = Path(os.environ.get("GMAIL_TOKEN", Path.home() / ".config" / "baselayer" / "gmail_token.json"))
SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]


def get_credentials():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    creds = None
    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())

    if not creds or not creds.valid:
        if not CREDENTIALS_FILE.exists():
            print(f"ERROR: {CREDENTIALS_FILE} not found.")
            sys.exit(1)
        flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_FILE), SCOPES)
        creds = flow.run_local_server(port=0)
        TOKEN_FILE.write_text(creds.to_json())
        print(f"Token saved to {TOKEN_FILE}")

    return creds


def get_draft_content(service, draft_id):
    """Get the full content of a draft by ID."""
    draft = service.users().drafts().get(userId="me", id=draft_id, format="full").execute()
    msg = draft["message"]

    # Get subject
    headers = msg.get("payload", {}).get("headers", [])
    subject = next((h["value"] for h in headers if h["name"].lower() == "subject"), "(no subject)")
    to = next((h["value"] for h in headers if h["name"].lower() == "to"), "(no recipient)")

    # Get body
    payload = msg.get("payload", {})
    body_text = ""

    def extract_body(part):
        """Recursively extract body text from message parts."""
        texts = []
        mime = part.get("mimeType", "")
        if "body" in part and part["body"].get("data"):
            decoded = base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", errors="replace")
            texts.append((mime, decoded))
        for sub in part.get("parts", []):
            texts.extend(extract_body(sub))
        return texts

    parts = extract_body(payload)

    # Prefer text/plain, fall back to text/html
    plain = [t for m, t in parts if "plain" in m]
    html = [t for m, t in parts if "html" in m]
    body_text = plain[0] if plain else (html[0] if html else "(empty body)")

    return subject, to, body_text


def main():
    from googleapiclient.discovery import build

    creds = get_credentials()
    service = build("gmail", "v1", credentials=creds)

    # List recent drafts (get more to increase chance of finding Bernie)
    result = service.users().drafts().list(userId="me", maxResults=30).execute()
    drafts = result.get("drafts", [])

    if not drafts:
        print("No drafts found.")
        return

    print(f"Found {len(drafts)} drafts. Checking most recent 5 first...\n")

    # Show 5 most recent
    bernie_draft = None
    for i, draft in enumerate(drafts[:5]):
        subject, to, body = get_draft_content(service, draft["id"])
        print(f"Draft {i+1}: To={to}, Subject={subject[:80]}")
        if "bernie" in subject.lower() or "bernie" in body.lower() or "sanders" in subject.lower() or "sanders" in body.lower():
            bernie_draft = (draft["id"], subject, to, body)
            print("  ^^^ BERNIE MATCH ^^^")

    # If not found in top 5, search the rest
    if not bernie_draft and len(drafts) > 5:
        print(f"\nBernie not in top 5. Searching remaining {len(drafts) - 5} drafts...")
        for i, draft in enumerate(drafts[5:], start=6):
            subject, to, body = get_draft_content(service, draft["id"])
            if "bernie" in subject.lower() or "bernie" in body.lower() or "sanders" in subject.lower() or "sanders" in body.lower():
                bernie_draft = (draft["id"], subject, to, body)
                print(f"  Found in draft {i}: {subject[:80]}")
                break

    if bernie_draft:
        draft_id, subject, to, body = bernie_draft
        print(f"\n{'='*60}")
        print(f"BERNIE SANDERS DRAFT")
        print(f"{'='*60}")
        print(f"To: {to}")
        print(f"Subject: {subject}")
        print(f"Draft ID: {draft_id}")
        print(f"{'='*60}")
        print(f"BODY:\n")
        print(body)
    else:
        print("\nNo draft mentioning Bernie Sanders found.")


if __name__ == "__main__":
    main()
