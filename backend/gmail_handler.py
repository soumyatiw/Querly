import os
import base64
from bs4 import BeautifulSoup
from gemini import generate_reply

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from google.auth.transport.requests import Request

# Allow reading, replying, and modifying email
SCOPES = ['https://www.googleapis.com/auth/gmail.modify']


def authenticate_gmail():
    creds = None
    if os.path.exists('backend/token.json'):
        creds = Credentials.from_authorized_user_file('backend/token.json', SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file('backend/credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)

        with open('backend/token.json', 'w') as token:
            token.write(creds.to_json())
    return creds


def strip_html_tags(html):
    soup = BeautifulSoup(html, "html.parser")
    return soup.get_text(separator="\n")


def get_email_body(payload):
    if payload.get('body', {}).get('data'):
        try:
            decoded = base64.urlsafe_b64decode(payload['body']['data']).decode("utf-8")
            if payload.get("mimeType") == "text/html":
                return strip_html_tags(decoded)
            return decoded
        except:
            pass

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

        if "parts" in part:
            result = get_email_body(part)
            if result:
                return result

    return ""


def is_automated_sender(sender_email):
    """Return True if sender is a no-reply or automated address."""
    keywords = ['noreply', 'no-reply', 'do-not-reply', 'notifications','notification', 'noreply@', 'mailer-daemon']
    return any(keyword in sender_email.lower() for keyword in keywords)


def send_email_reply(service, to_email, subject, message_body):
    message = MIMEMultipart()
    message['to'] = to_email
    message['subject'] = f"Re: {subject}"

    msg = MIMEText(message_body)
    message.attach(msg)

    raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()

    try:
        sent_message = service.users().messages().send(
            userId='me',
            body={'raw': raw_message}
        ).execute()
        print("✅ Reply sent successfully.\n")
    except Exception as e:
        print("❌ Error sending email:", e)


def read_unread_emails():
    creds = authenticate_gmail()
    service = build('gmail', 'v1', credentials=creds)

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

        payload = msg_data.get('payload', {})
        body = get_email_body(payload) or "⚠️ Could not extract email content."

        print(f"📨 Email from: {sender}")
        print(f"📝 Subject: {subject}")
        print(f"📄 Body:\n{body}\n")

        # 🚫 Skip automated/no-reply emails
        if is_automated_sender(sender):
            print("🚫 Automated/no-reply sender detected. Skipping reply.\n")
            continue

        prompt = f"""
You are an AI email reply bot.

From: {sender}
Subject: {subject}
Message: {body}

Reply strictly and only with a professional, polite response in human-like language. Do not add any additional discounts, promotions, or marketing content. Focus on addressing the email content directly.
Do not add any introductions, explanations, or markdown.
Only reply if necessary.
"""

        try:
            ai_reply = generate_reply(prompt).strip()

            if not ai_reply:
                print("🤖 No valid reply generated. Skipping.\n")
                continue

            print("🤖 Suggested Reply:")
            print(ai_reply)

            send_email_reply(service, sender, subject, ai_reply)

        except Exception as e:
            print(f"❌ Gemini error: {e}")
            continue

        print("-" * 60)


if __name__ == "__main__":
    read_unread_emails()
