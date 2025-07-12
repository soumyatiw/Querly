import os
import base64
from bs4 import BeautifulSoup
from gemini import generate_reply

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from google.auth.transport.requests import Request

# Gmail read-only scope
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']


def authenticate_gmail():
    creds = None
    if os.path.exists('backend/token.json'):
        creds = Credentials.from_authorized_user_file('backend/token.json', SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                'backend/credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)

        with open('backend/token.json', 'w') as token:
            token.write(creds.to_json())
    return creds


# Function to strip HTML tags if only text/html is available
def strip_html_tags(html):
    soup = BeautifulSoup(html, "html.parser")
    return soup.get_text(separator="\n")


# Function to extract body (plain or html)
def get_email_body(payload):
    # 1. Try direct payload body
    if payload.get('body', {}).get('data'):
        try:
            decoded = base64.urlsafe_b64decode(payload['body']['data']).decode("utf-8")
            if payload.get("mimeType") == "text/html":
                return strip_html_tags(decoded)
            return decoded
        except:
            pass

    # 2. Check if parts exist (multipart message)
    parts = payload.get('parts', [])
    for part in parts:
        mime_type = part.get("mimeType", "")
        data = part.get("body", {}).get("data")

        if data:
            try:
                decoded = base64.urlsafe_b64decode(data).decode("utf-8")
                if mime_type == "text/html":
                    return strip_html_tags(decoded)
                return decoded
            except:
                pass

        # Check deeper nested parts (like multipart/alternative)
        if "parts" in part:
            result = get_email_body(part)
            if result:
                return result

    return ""



def read_unread_emails():
    creds = authenticate_gmail()
    service = build('gmail', 'v1', credentials=creds)

    # Fetch unread messages
    results = service.users().messages().list(userId='me', labelIds=['UNREAD'], maxResults=5).execute()
    messages = results.get('messages', [])

    if not messages:
        print("✅ No unread emails found.")
        return

    for msg in messages:
        msg_data = service.users().messages().get(userId='me', id=msg['id']).execute()
        headers = msg_data['payload']['headers']

        subject = sender = ""
        for header in headers:
            if header['name'] == 'Subject':
                subject = header['value']
            if header['name'] == 'From':
                sender = header['value']

        # Extract full email body
        payload = msg_data.get('payload', {})
        body = get_email_body(payload) or "⚠️ Could not extract email content."

        print(f"📨 Email from: {sender}")
        print(f"📝 Subject: {subject}")
        print(f"📄 Body:\n{body}\n")

        # Generate AI reply from Gemini
        prompt = f"""You are an AI email assistant.
Here is a new unread email:
From: {sender}
Subject: {subject}
Message: {body}

Please write a professional, polite, short reply to this email.
"""
        ai_reply = generate_reply(prompt)
        print("🤖 Suggested Reply:")
        print(ai_reply)
        print("-" * 60)


if __name__ == "__main__":
    read_unread_emails()
