import os
import base64
import json

from gemini import generate_reply

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from google.auth.transport.requests import Request

# If modifying these SCOPES, delete token.json
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

def authenticate_gmail():
    creds = None
    # token.json stores user's access and refresh tokens
    if os.path.exists('backend/token.json'):
        creds = Credentials.from_authorized_user_file('backend/token.json', SCOPES)
    # If there is no valid token, prompt login
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                'backend/credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        # Save the credentials
        with open('backend/token.json', 'w') as token:
            token.write(creds.to_json())
    return creds

def read_unread_emails():
    creds = authenticate_gmail()
    service = build('gmail', 'v1', credentials=creds)

    # Call the Gmail API to fetch unread messages
    results = service.users().messages().list(userId='me', labelIds=['UNREAD'], maxResults=5).execute()
    messages = results.get('messages', [])

    if not messages:
        print("No unread emails found.")
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

        # sender and subject
        print(f"📨 Email from: {sender}")
        print(f"📝 Subject: {subject}")

        # email snippet
        snippet = msg_data.get('snippet', '')

        # Prompt for Gemini
        prompt = f"""You are an AI email assistant.
            Here is a new unread email:
            From: {sender}
            Subject: {subject}
            Message: {snippet}

            Please write a professional, polite, short reply to this email.
            """

        # Gemini reply
        ai_reply = generate_reply(prompt)
        print("🤖 Suggested Reply:")
        print(ai_reply)
        print("-" * 40)


if __name__ == "__main__":
    read_unread_emails()
