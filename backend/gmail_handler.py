import os
import base64
import json
import asyncio
import traceback
from bs4 import BeautifulSoup
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from google.auth.transport.requests import Request

# Local imports
from db import (
    get_user_tokens, save_user_tokens,
    save_draft, get_user_settings,
    update_job_status, get_processed_email_ids,
    check_draft_exists
)
from gemini import generate_reply, categorize_email

# Allow reading, replying, and modifying email
SCOPES = ['https://www.googleapis.com/auth/gmail.modify', 'https://www.googleapis.com/auth/gmail.send']


# ── Event-loop bridge ──────────────────────────────────────────────────────────
# gmail_handler runs in a sync thread (FastAPI BackgroundTask). Motor is bound
# to the main asyncio event loop. Use run_coroutine_threadsafe to schedule Motor
# coroutines on the correct loop and block until they complete.

def _run(coro, loop: asyncio.AbstractEventLoop):
    """Schedule an async coroutine on `loop` from a sync thread and block for the result."""
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    return future.result()   # blocks the worker thread, NOT the event loop


# ── Auth ───────────────────────────────────────────────────────────────────────

async def authenticate_gmail(uid: str):
    """Loads Credentials from MongoDB using the user's uid (async — called from async context)."""
    user_tokens = await get_user_tokens(uid)
    if not user_tokens:
        print(f"⚠️ No tokens found for uid {uid}")
        return None

    access_token  = user_tokens.get("google_access_token")
    refresh_token = user_tokens.get("google_refresh_token")

    if not access_token:
        print(f"⚠️ Access token missing for uid {uid}")
        return None

    env_creds = os.getenv("GOOGLE_CREDENTIALS_JSON")
    try:
        if env_creds:
            creds_data = json.loads(env_creds)
        else:
            BASE_DIR = os.path.dirname(os.path.abspath(__file__))
            CREDENTIALS_PATH = os.path.join(BASE_DIR, "credentials.json")
            with open(CREDENTIALS_PATH, 'r') as f:
                creds_data = json.load(f)
                
        client_config = creds_data.get('web') or creds_data.get('installed')
        client_id     = client_config['client_id']
        client_secret = client_config['client_secret']
        token_uri     = client_config['token_uri']
    except Exception as e:
        print("⚠️ Failed to load google credentials:", e)
        return None

    creds = Credentials(
        token=access_token,
        refresh_token=refresh_token,
        token_uri=token_uri,
        client_id=client_id,
        client_secret=client_secret,
        scopes=SCOPES
    )

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


# ── Email parsing helpers ──────────────────────────────────────────────────────

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
        data      = part.get("body", {}).get("data")

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
    keywords = [
        'noreply', 'no-reply', 'do-not-reply', 'notifications', 'notification',
        'noreply@', 'mailer-daemon', 'friendsuggestion', 'auto', 'automated',
        'donotreply', 'notify', 'no_reply', 'no.reply'
    ]
    return any(keyword in sender_email.lower() for keyword in keywords)


# ── Gmail API actions ──────────────────────────────────────────────────────────

def mark_email_as_read(service, msg_id):
    try:
        service.users().messages().modify(
            userId='me', id=msg_id,
            body={'removeLabelIds': ['UNREAD']}
        ).execute()
        print(f"📩 Email {msg_id} marked as read ✅")
    except Exception as e:
        print(f"⚠️ Failed to mark email as read: {e}")


def send_gmail_draft(service, draft_id: str) -> bool:
    try:
        service.users().drafts().send(userId='me', body={'id': draft_id}).execute()
        print(f"✅ Draft {draft_id} sent.")
        return True
    except Exception as e:
        print(f"❌ Failed to send draft {draft_id}: {e}")
        return False


def delete_gmail_draft(service, draft_id: str) -> bool:
    try:
        service.users().drafts().delete(userId='me', id=draft_id).execute()
        print(f"🗑️ Draft {draft_id} deleted.")
        return True
    except Exception as e:
        print(f"❌ Failed to delete draft {draft_id}: {e}")
        return False


def update_gmail_draft(service, draft_id: str, to_email: str, subject: str, body: str) -> bool:
    try:
        message = MIMEMultipart()
        message['to']      = to_email
        message['subject'] = f"Re: {subject}"
        message.attach(MIMEText(body))
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
        service.users().drafts().update(
            userId='me', id=draft_id,
            body={'message': {'raw': raw}}
        ).execute()
        print(f"✏️ Draft {draft_id} updated.")
        return True
    except Exception as e:
        print(f"❌ Failed to update draft {draft_id}: {e}")
        return False


def create_gmail_draft(service, to_email: str, subject: str, body: str) -> str | None:
    """Creates a Gmail draft and returns its draft_id, or None on failure."""
    message = MIMEMultipart()
    message['to']      = to_email
    message['subject'] = f"Re: {subject}"
    message.attach(MIMEText(body))
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    try:
        draft = service.users().drafts().create(
            userId='me',
            body={'message': {'raw': raw}}
        ).execute()
        return draft['id']
    except Exception as e:
        print(f"❌ Error creating Gmail draft: {e}")
        return None


# ── Main background processing loop ───────────────────────────────────────────

def read_unread_emails_with_creds(
    creds,
    uid: str,
    job_id: str,
    days: int = 1,
    loop: asyncio.AbstractEventLoop = None
):
    """
    Synchronous function run inside a FastAPI BackgroundTask (worker thread).
    All Motor/async calls go through _run(coro, loop) which schedules them back
    on the main event loop via run_coroutine_threadsafe — fixing the
    'Future attached to a different loop' RuntimeError.
    """

    # Fallback: try to get the running loop if not passed (should not happen)
    if loop is None:
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()

    drafts_created    = 0
    already_processed = 0
    not_actionable    = 0
    generation_errors = 0

    _run(update_job_status(job_id, "processing", "Starting email processing…"), loop)

    service = build('gmail', 'v1', credentials=creds)

    from datetime import datetime, timedelta
    cutoff_date = (datetime.utcnow() - timedelta(days=days)).strftime("%Y/%m/%d")
    gmail_query = f"is:unread after:{cutoff_date}"

    try:
        results = service.users().messages().list(
            userId='me', q=gmail_query, maxResults=20
        ).execute()
    except Exception as e:
        print("❌ Error listing messages:", e)
        _run(update_job_status(job_id, "error", f"Failed to list messages: {e}"), loop)
        return

    messages = results.get('messages', [])
    if not messages:
        print("✅ No unread emails found.")
        _run(update_job_status(job_id, "done", "No unread emails found."), loop)
        return

    # Pre-fetch already-processed IDs to skip unnecessary API calls
    processed_ids   = _run(get_processed_email_ids(uid), loop)
    message_ids     = [m['id'] for m in messages]
    new_message_ids = [mid for mid in message_ids if mid not in processed_ids]
    already_processed = len(message_ids) - len(new_message_ids)

    print(f"📊 Total unread: {len(message_ids)} | Already processed: {already_processed} | New: {len(new_message_ids)}")

    if not new_message_ids:
        summary_msg = f"Done: 0 new drafts. {already_processed} emails already processed."
        _run(update_job_status(job_id, "done", summary_msg), loop)
        return

    # Fetch user settings
    user_settings = _run(get_user_settings(uid), loop)
    tone          = user_settings.get("tone", "Professional")
    business_ctx  = user_settings.get("business_context", "")
    persona_notes = user_settings.get("persona_notes", "")

    try:
        from rag import query_knowledge_base
        rag_available = True
        print("[RAG] module loaded — knowledge base search enabled")
    except ImportError as e:
        print(f"[RAG] module unavailable: {e}")
        rag_available = False
    except Exception as e:
        print(f"[RAG] unexpected error loading module: {e}")
        rag_available = False

    for msg_id in new_message_ids:
        # Race-condition guard: check DB before processing
        if _run(check_draft_exists(uid, msg_id), loop):
            print(f"⏭️  Email {msg_id} already has a draft, skipping.")
            already_processed += 1
            continue

        try:
            msg_data = service.users().messages().get(userId='me', id=msg_id).execute()
        except Exception as e:
            print(f"❌ Failed to fetch message {msg_id}: {e}")
            generation_errors += 1
            continue

        headers    = msg_data['payload']['headers']
        subject    = sender = email_date = ""
        for header in headers:
            if header['name'] == 'Subject': subject    = header['value']
            if header['name'] == 'From':    sender     = header['value']
            if header['name'] == 'Date':    email_date = header['value']

        payload = msg_data.get('payload', {})
        body    = get_email_body(payload) or "⚠️ Could not extract email content."

        print(f"\n📨 Processing: [{msg_id}] {subject} — from {sender}")

        # Skip automated senders — save a skipped record so we never revisit
        if is_automated_sender(sender):
            print("🚫 Automated/no-reply sender — skipping.")
            mark_email_as_read(service, msg_id)
            not_actionable += 1
            _run(save_draft(
                draft_id=None, uid=uid, original_email_id=msg_id,
                original_subject=subject, original_sender=sender,
                original_body_snippet=body, ai_reply_body="",
                tone_used=tone, email_date=email_date,
            ), loop)
            continue

        # Categorize
        categorization = categorize_email(subject, body, sender)
        print(f"🏷️  Category: {categorization.get('category')} | should_reply: {categorization.get('should_reply')}")

        if not categorization.get("should_reply", True):
            print("📭 Not actionable — skipping reply.")
            mark_email_as_read(service, msg_id)
            not_actionable += 1
            _run(save_draft(
                draft_id=None, uid=uid, original_email_id=msg_id,
                original_subject=subject, original_sender=sender,
                original_body_snippet=body, ai_reply_body="",
                tone_used=tone, categorization=categorization, email_date=email_date,
            ), loop)
            continue

        # RAG context (optional) — search user's knowledge base
        relevant_context = None
        if rag_available:
            try:
                relevant_context = _run(
                    query_knowledge_base(uid, f"{subject}\n{body[:500]}"),
                    loop
                )
                if relevant_context:
                    print(f"[RAG] {len(relevant_context)} chunk(s) retrieved for email {msg_id}")
                else:
                    print(f"[RAG] no matching chunks for email {msg_id} (knowledge base may be empty)")
            except Exception as rag_err:
                print(f"[RAG] query failed for {msg_id}: {rag_err}")

        # Generate AI reply — raise on failure, skip gracefully
        try:
            ai_reply = generate_reply(
                email_body=body, tone=tone,
                business_context=business_ctx, persona_notes=persona_notes,
                relevant_context=relevant_context
            ).strip()
        except Exception as gen_err:
            print(f"❌ AI generation failed for email {msg_id}: {gen_err}")
            traceback.print_exc()
            generation_errors += 1
            _run(save_draft(
                draft_id=None, uid=uid, original_email_id=msg_id,
                original_subject=subject, original_sender=sender,
                original_body_snippet=body, ai_reply_body="",
                tone_used=tone, categorization=categorization, email_date=email_date,
            ), loop)
            mark_email_as_read(service, msg_id)
            continue

        # Create Gmail draft
        gmail_draft_id = create_gmail_draft(service, sender, subject, ai_reply)
        if not gmail_draft_id:
            print(f"❌ Failed to create Gmail draft for {msg_id}")
            generation_errors += 1
            continue

        # Save to MongoDB
        _run(save_draft(
            draft_id=gmail_draft_id, uid=uid, original_email_id=msg_id,
            original_subject=subject, original_sender=sender,
            original_body_snippet=body, ai_reply_body=ai_reply,
            tone_used=tone, categorization=categorization, email_date=email_date,
        ), loop)

        mark_email_as_read(service, msg_id)
        drafts_created += 1
        print(f"✅ Draft saved: {gmail_draft_id}")
        print("-" * 60)

    # Build result summary for the frontend toast
    parts = [f"{drafts_created} draft(s) created"]
    if already_processed:   parts.append(f"{already_processed} already processed")
    if not_actionable:      parts.append(f"{not_actionable} skipped (not actionable)")
    if generation_errors:   parts.append(f"{generation_errors} skipped (AI error)")

    summary_msg = "Done: " + ", ".join(parts) + "."
    _run(update_job_status(job_id, "done", summary_msg), loop)
    print(f"\n🏁 Job {job_id} complete — {summary_msg}")
