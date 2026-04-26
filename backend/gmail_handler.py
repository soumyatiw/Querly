import os
import base64
import json
from bs4 import BeautifulSoup
from gemini import generate_reply, categorize_email
from rag import search_knowledge_base
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from google.auth.transport.requests import Request

# Import from our db module
from db import get_user_tokens, save_user_tokens, update_job_status, save_draft, get_user_settings, get_processed_email_ids
import asyncio

# Allow reading, replying, and modifying email
SCOPES = ['https://www.googleapis.com/auth/gmail.modify', 'https://www.googleapis.com/auth/gmail.send']


async def authenticate_gmail(uid: str):
    """Loads Credentials from MongoDB using the user's uid."""
    user_tokens = await get_user_tokens(uid)
    if not user_tokens:
        print(f"⚠️ No tokens found for uid {uid}")
        return None
        
    access_token = user_tokens.get("google_access_token")
    refresh_token = user_tokens.get("google_refresh_token")
    
    if not access_token:
        print(f"⚠️ Access token missing for uid {uid}")
        return None

    # Load client config from credentials.json
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    CREDENTIALS_PATH = os.path.join(BASE_DIR, "credentials.json")
    
    try:
        with open(CREDENTIALS_PATH, 'r') as f:
            creds_data = json.load(f)
            client_config = creds_data.get('web') or creds_data.get('installed')
            client_id = client_config['client_id']
            client_secret = client_config['client_secret']
            token_uri = client_config['token_uri']
    except Exception as e:
        print("⚠️ Failed to load credentials.json:", e)
        return None

    # Reconstruct Credentials object
    creds = Credentials(
        token=access_token,
        refresh_token=refresh_token,
        token_uri=token_uri,
        client_id=client_id,
        client_secret=client_secret,
        scopes=SCOPES
    )

    # Refresh if expired
    if creds and creds.expired:
        try:
            if creds.refresh_token:
                creds.refresh(Request())
                await save_user_tokens(
                    uid=uid,
                    email=user_tokens.get("email", ""),
                    access_token=creds.token,
                    refresh_token=creds.refresh_token,
                    token_expiry=creds.expiry.isoformat() if creds.expiry else None
                )
            else:
                print("⚠️ No refresh token available, re-auth required.")
                creds = None
        except Exception as e:
            print(f"⚠️ Error refreshing token for {uid}: {e}")
            creds = None

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
    keywords = ['noreply', 'no-reply', 'do-not-reply', 'notifications', 'notification', 'noreply@', 'mailer-daemon',
                'friendsuggestion', 'auto', 'automated', 'donotreply', 'notify', 'no_reply', 'no.reply']
    return any(keyword in sender_email.lower() for keyword in keywords)


def create_gmail_draft(service, to_email, subject, message_body):
    message = MIMEMultipart()
    message['to'] = to_email
    message['subject'] = f"Re: {subject}"

    msg = MIMEText(message_body)
    message.attach(msg)

    raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()

    try:
        draft = service.users().drafts().create(
            userId='me',
            body={'message': {'raw': raw_message}}
        ).execute()
        print(f"✅ Draft created successfully: {draft['id']}\n")
        return draft['id']
    except Exception as e:
        print("❌ Error creating draft:", e)
        return None

def send_gmail_draft(service, draft_id):
    try:
        service.users().drafts().send(
            userId='me',
            body={'id': draft_id}
        ).execute()
        print(f"✅ Draft sent successfully: {draft_id}\n")
        return True
    except Exception as e:
        print("❌ Error sending draft:", e)
        return False

def delete_gmail_draft(service, draft_id):
    try:
        service.users().drafts().delete(
            userId='me',
            id=draft_id
        ).execute()
        print(f"✅ Draft deleted successfully: {draft_id}\n")
        return True
    except Exception as e:
        print("❌ Error deleting draft:", e)
        return False

def update_gmail_draft(service, draft_id, to_email, subject, message_body):
    message = MIMEMultipart()
    message['to'] = to_email
    message['subject'] = f"Re: {subject}" if not subject.startswith("Re:") else subject

    msg = MIMEText(message_body)
    message.attach(msg)

    raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()

    try:
        draft = service.users().drafts().update(
            userId='me',
            id=draft_id,
            body={'message': {'raw': raw_message}}
        ).execute()
        print(f"✅ Draft updated successfully: {draft_id}\n")
        return True
    except Exception as e:
        print("❌ Error updating draft:", e)
        return False


def mark_email_as_replied(service, msg_id):
    """Remove 'UNREAD' label to mark it as read after replying"""
    try:
        service.users().messages().modify(
            userId='me',
            id=msg_id,
            body={'removeLabelIds': ['UNREAD']}
        ).execute()
        print(f"📩 Email {msg_id} marked as replied ✅\n")
    except Exception as e:
        print(f"⚠️ Failed to mark email as replied: {e}")


async def read_unread_emails_with_creds(creds, uid, job_id=None, days=1):
    if not creds:
        print("No credentials passed.")
        if job_id:
            await update_job_status(job_id, "error", "No credentials passed")
        return

    user_settings = await get_user_settings(uid)
    tone = user_settings.get("tone", "Professional")
    business_context = user_settings.get("business_context", "")
    persona_notes = user_settings.get("persona_notes", "")

    if job_id:
        await update_job_status(job_id, "processing", "Fetching unread emails...")

    service = build('gmail', 'v1', credentials=creds)

    # Build date-filtered Gmail query — only fetch emails in the chosen window.
    # NOTE: We do NOT use is:unread because Querly marks emails as read after
    # processing. After a draft clear, those emails would never be found again.
    # The already_processed dedup set below prevents re-processing duplicates.
    from datetime import datetime as _dt, timedelta as _td
    after_date = (_dt.utcnow() - _td(days=days)).strftime("%Y/%m/%d")
    gmail_query = f"after:{after_date}"

    # Pre-load processed email IDs to prevent duplicate drafts on re-run
    already_processed = await get_processed_email_ids(uid)

    try:
        def fetch_messages():
            return service.users().messages().list(
                userId='me',
                q=gmail_query,
                maxResults=20
            ).execute()
        results = await asyncio.to_thread(fetch_messages)
    except Exception as e:
        print(f"Error listing messages: {e}")
        if job_id:
            await update_job_status(job_id, "error", f"Error listing messages: {e}")
        return

    all_messages = results.get('messages', [])
    # Skip emails that already have a draft / skip record in MongoDB
    messages = [m for m in all_messages if m['id'] not in already_processed]

    if not messages:
        print("No new unread emails to process.")
        if job_id:
            note = f"No new emails to process (window: {days}d, already handled: {len(all_messages)})."
            await update_job_status(job_id, "done", note)
        return

    processed_count = 0
    replied_count = 0

    for idx, msg in enumerate(messages):
        msg_id = msg['id']
        if job_id:
            await update_job_status(job_id, "processing", f"Processing email {idx + 1} of {len(messages)}...")

        def fetch_msg_data():
            return service.users().messages().get(userId='me', id=msg_id).execute()
            
        msg_data = await asyncio.to_thread(fetch_msg_data)
        headers = msg_data['payload']['headers']

        subject = sender = email_date = ""
        for header in headers:
            if header['name'] == 'Subject':
                subject = header['value']
            if header['name'] == 'From':
                sender = header['value']
            if header['name'] == 'Date':
                email_date = header['value']

        payload = msg_data.get('payload', {})
        body = get_email_body(payload) or "⚠️ Could not extract email content."

        print(f"📨 Email from: {sender}")
        print(f"📝 Subject: {subject}")
        print(f"📄 Body:\n{body}\n")

        if is_automated_sender(sender):
            print("🚫 Automated/no-reply sender detected. Skipping reply.\n")
            def mark_replied():
                mark_email_as_replied(service, msg_id)
            await asyncio.to_thread(mark_replied)
            processed_count += 1
            continue

        email_context = f"From: {sender}\nSubject: {subject}\nMessage: {body}"

        # Categorize first
        try:
            def run_categorize():
                return categorize_email(subject, body, sender)
            categorization = await asyncio.to_thread(run_categorize)
            print(f"📊 Categorization: {categorization}")
        except Exception as e:
            print("❌ Categorization failed:", e)
            categorization = {
                "category": "other",
                "priority": "low",
                "summary": "Could not categorize.",
                "should_reply": False
            }

        should_reply = categorization.get("should_reply", False)
        category = categorization.get("category", "other")

        if not should_reply or category.lower() in ["newsletter", "spam"]:
            print(f"⏭️ Skipping reply for email (Category: {category}, Should Reply: {should_reply})")
            await save_draft(
                draft_id=None,
                uid=uid,
                original_email_id=msg_id,
                original_subject=subject,
                original_sender=sender,
                original_body_snippet=body,
                ai_reply_body=None,
                tone_used=tone,
                categorization=categorization,
                email_date=email_date,
            )
            def mark_replied():
                mark_email_as_replied(service, msg_id)
            await asyncio.to_thread(mark_replied)
            processed_count += 1
            continue

        try:
            # RAG: retrieve relevant knowledge-base chunks using the email body as query
            rag_context = await search_knowledge_base(uid, body)

            def run_gemini():
                return generate_reply(
                    email_body=email_context,
                    tone=tone,
                    business_context=business_context,
                    persona_notes=persona_notes,
                    relevant_context=rag_context if rag_context else None
                ).strip()
            ai_reply = await asyncio.to_thread(run_gemini)

            if not ai_reply:
                print("🤖 No valid reply generated. Skipping.\n")
                def mark_replied():
                    mark_email_as_replied(service, msg_id)
                await asyncio.to_thread(mark_replied)
                processed_count += 1
                continue

            print("🤖 Suggested Reply:")
            print(ai_reply)

            def create_draft_and_mark():
                draft_id = create_gmail_draft(service, sender, subject, ai_reply)
                if draft_id:
                    mark_email_as_replied(service, msg_id)
                return draft_id
            
            draft_id = await asyncio.to_thread(create_draft_and_mark)
            if draft_id:
                await save_draft(
                    draft_id=draft_id,
                    uid=uid,
                    original_email_id=msg_id,
                    original_subject=subject,
                    original_sender=sender,
                    original_body_snippet=body,
                    ai_reply_body=ai_reply,
                    tone_used=tone,
                    categorization=categorization,
                    email_date=email_date,
                )
                replied_count += 1
            processed_count += 1

        except Exception as e:
            print(f"❌ Gemini error: {e}")
            continue

        print("-" * 60)
        
    if job_id:
        await update_job_status(job_id, "done", f"Processed {processed_count} emails, replied to {replied_count}.")


if __name__ == "__main__":
    pass
