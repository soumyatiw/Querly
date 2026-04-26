# backend/main.py
import os
from pathlib import Path
import json
from dotenv import load_dotenv
from fastapi import FastAPI, Request, HTTPException, BackgroundTasks, UploadFile, File
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

import firebase_admin
from firebase_admin import auth as firebase_auth, credentials as firebase_credentials

# Local imports
import asyncio
from pydantic import BaseModel
from gmail_handler import authenticate_gmail, read_unread_emails_with_creds, send_gmail_draft, delete_gmail_draft, update_gmail_draft
from db import init_db, save_user_tokens, get_user_tokens, save_oauth_state, get_oauth_state, create_job, get_job_status, get_user_drafts, get_draft, update_draft_status, update_draft_body, get_user_settings, save_user_settings, get_category_summary, get_processed_email_ids
from rag import ingest_pdf


load_dotenv()

app = FastAPI()

@app.on_event("startup")
async def startup_event():
    await init_db()

# ── CORS ─────────────────────────────────────────────────────────────────────
# Allow only the configured frontend origin (never a wildcard in production).
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000").rstrip("/")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_URL],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# Init firebase-admin
if not firebase_admin._apps:
    sa = json.loads(os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON"))
    cred = firebase_credentials.Certificate(sa)
    firebase_admin.initialize_app(cred)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
GOOGLE_CREDENTIALS_PATH = os.path.join(BASE_DIR, "credentials.json")

@app.get("/auth/google/start")
async def start_google_oauth(idToken: str):
    """
    Frontend provides Firebase idToken as query param or header, backend verifies it to get UID
    Returns the Google consent URL (redirect the user to it)
    """
    if not idToken:
        raise HTTPException(status_code=400, detail="Missing idToken")

    # Verify Firebase ID token
    try:
        decoded = firebase_auth.verify_id_token(idToken)
        uid = decoded["uid"]
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Invalid ID token: {e}")

    # Create the Flow with offline access (to get refresh token)
    flow = Flow.from_client_secrets_file(
        GOOGLE_CREDENTIALS_PATH,
        scopes=['https://www.googleapis.com/auth/gmail.modify', 'https://www.googleapis.com/auth/gmail.send'],
        redirect_uri=os.getenv("GOOGLE_OAUTH_REDIRECT_URI")  # must match console settings
    )

    # Generate authorization URL with 'access_type' = 'offline' to get refresh_token
    auth_url, state = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true',
        prompt='consent'
    )

    # Store the flow state in MongoDB
    await save_oauth_state(state, uid)
    
    # return URL to frontend to redirect user
    return JSONResponse({"url": auth_url})

@app.get("/auth/google/callback")
async def google_oauth_callback(request: Request):
    """
    Exchange code for tokens and save token to MongoDB for the user
    """
    params = dict(request.query_params)
    state = params.get("state")
    code = params.get("code")

    if not state or not code:
        raise HTTPException(status_code=400, detail="Missing or invalid state")

    # Verify state against MongoDB
    stored = await get_oauth_state(state)
    if not stored:
        raise HTTPException(status_code=400, detail="State not found or expired")

    uid = stored["uid"]

    flow = Flow.from_client_secrets_file(
        GOOGLE_CREDENTIALS_PATH,
        scopes=['https://www.googleapis.com/auth/gmail.modify', 'https://www.googleapis.com/auth/gmail.send'],
        redirect_uri=os.getenv("GOOGLE_OAUTH_REDIRECT_URI")
    )

    # fetch token
    flow.fetch_token(code=code)
    creds = flow.credentials

    # Optionally: store linked email
    connected_email = ""
    try:
        service = build('gmail', 'v1', credentials=creds)
        profile = service.users().getProfile(userId='me').execute()
        connected_email = profile.get('emailAddress', '')
    except:
        # Fallback to fetching Firebase email
        try:
            user_record = firebase_auth.get_user(uid)
            connected_email = user_record.email or ""
        except:
            pass

    # Save credentials to MongoDB
    await save_user_tokens(
        uid=uid,
        email=connected_email,
        access_token=creds.token,
        refresh_token=creds.refresh_token,
        token_expiry=creds.expiry.isoformat() if creds.expiry else None
    )

    # Redirect back to frontend dashboard page
    frontend_url = os.getenv("FRONTEND_AFTER_OAUTH", "http://localhost:3000/dashboard")
    return RedirectResponse(frontend_url)

def verify_firebase_token_from_auth_header(authorization_header: str):
    if not authorization_header:
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    if not authorization_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid Authorization header")
    id_token = authorization_header.split(" ")[1]
    try:
        decoded = firebase_auth.verify_id_token(id_token)
        return decoded
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Invalid ID token: {e}")

@app.post("/knowledge-base/upload")
async def upload_knowledge_base(request: Request, file: UploadFile = File(...)):
    """
    POST /knowledge-base/upload
    Accepts a PDF, extracts text, chunks it, embeds it, and stores it in MongoDB.
    Requires Authorization: Bearer <firebase idToken>
    """
    auth_header = request.headers.get("Authorization")
    decoded = verify_firebase_token_from_auth_header(auth_header)
    uid = decoded["uid"]

    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")

    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    num_chunks = await ingest_pdf(uid, file.filename, file_bytes)

    return {
        "ok": True,
        "filename": file.filename,
        "chunks_stored": num_chunks,
        "message": f"Successfully indexed {num_chunks} chunks from '{file.filename}'."
    }

@app.get("/gmail/status")
async def gmail_status(request: Request):
    """
    GET /gmail/status with Authorization: Bearer <firebase idToken>
    Returns whether user has token saved
    """
    auth_header = request.headers.get("Authorization")
    decoded = verify_firebase_token_from_auth_header(auth_header)
    uid = decoded["uid"]
    
    user_tokens = await get_user_tokens(uid)
    if user_tokens and user_tokens.get("google_access_token"):
        # We can also verify if the token actually works, but for simple status checking:
        creds = await authenticate_gmail(uid)
        if creds:
            connected_email = user_tokens.get("email")
            if not connected_email:
                try:
                    service = build('gmail', 'v1', credentials=creds)
                    profile = service.users().getProfile(userId='me').execute()
                    connected_email = profile.get('emailAddress')
                except Exception:
                    connected_email = None
            return {"connected": True, "connectedEmail": connected_email}
            
    return {"connected": False, "connectedEmail": None}

class TriggerBody(BaseModel):
    days: int = 1  # 1 = last 24h, 7 = last week, 30 = last month

@app.post("/gmail/trigger")
async def gmail_trigger(request: Request, background_tasks: BackgroundTasks, body: TriggerBody = None):
    """
    POST /gmail/trigger — kick off background email processing.
    Optional JSON body: {"days": 7}
    """
    auth_header = request.headers.get("Authorization")
    decoded = verify_firebase_token_from_auth_header(auth_header)
    uid = decoded["uid"]

    creds = await authenticate_gmail(uid)
    if not creds:
        raise HTTPException(status_code=404, detail="Gmail not connected or expired")

    days = (body.days if body else 1)
    # Clamp to sensible range
    days = max(1, min(days, 30))

    job_id = await create_job(uid)
    background_tasks.add_task(read_unread_emails_with_creds, creds, uid, job_id, days)

    return {"status": "processing", "job_id": job_id, "days": days}

@app.get("/gmail/job/{job_id}")
async def get_job(job_id: str, request: Request):
    """
    GET /gmail/job/{job_id} to check job status
    """
    auth_header = request.headers.get("Authorization")
    decoded = verify_firebase_token_from_auth_header(auth_header)
    uid = decoded["uid"]
    
    job = await get_job_status(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
        
    if job["uid"] != uid:
        raise HTTPException(status_code=403, detail="Not authorized to view this job")
        
    # Convert datetime to string for JSON serialization
    if "created_at" in job and job["created_at"]:
        job["created_at"] = job["created_at"].isoformat()
    return job

class SettingsBody(BaseModel):
    tone: str
    business_context: str
    persona_notes: str

@app.put("/settings")
async def update_settings(body: SettingsBody, request: Request):
    auth_header = request.headers.get("Authorization")
    decoded = verify_firebase_token_from_auth_header(auth_header)
    uid = decoded["uid"]
    
    await save_user_settings(uid, body.tone, body.business_context, body.persona_notes)
    return {"ok": True, "message": "Settings updated"}

@app.get("/settings")
async def get_settings(request: Request):
    auth_header = request.headers.get("Authorization")
    decoded = verify_firebase_token_from_auth_header(auth_header)
    uid = decoded["uid"]
    
    settings = await get_user_settings(uid)
    return settings

class DraftUpdateBody(BaseModel):
    ai_reply_body: str

@app.get("/drafts")
async def list_drafts(request: Request, days: int = None):
    """
    GET /drafts — list drafts for the logged-in user.
    Optional ?days=7 to filter to the last N days.
    """
    auth_header = request.headers.get("Authorization")
    decoded = verify_firebase_token_from_auth_header(auth_header)
    uid = decoded["uid"]

    drafts = await get_user_drafts(uid, days=days)
    for d in drafts:
        d["_id"] = str(d["_id"])
        if "created_at" in d and d["created_at"]:
            d["created_at"] = d["created_at"].isoformat()
    return {"drafts": drafts}

@app.get("/emails/summary")
async def get_emails_summary(request: Request):
    auth_header = request.headers.get("Authorization")
    decoded = verify_firebase_token_from_auth_header(auth_header)
    uid = decoded["uid"]
    
    summary = await get_category_summary(uid, days=7)
    return {"summary": summary}

@app.get("/drafts/{draft_id}")
async def get_draft_details(draft_id: str, request: Request):
    auth_header = request.headers.get("Authorization")
    decoded = verify_firebase_token_from_auth_header(auth_header)
    uid = decoded["uid"]
    
    draft = await get_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")
    if draft["uid"] != uid:
        raise HTTPException(status_code=403, detail="Not authorized")
        
    draft["_id"] = str(draft["_id"])
    if "created_at" in draft and draft["created_at"]:
        draft["created_at"] = draft["created_at"].isoformat()
    return draft

@app.post("/drafts/{draft_id}/approve")
async def approve_draft(draft_id: str, request: Request):
    auth_header = request.headers.get("Authorization")
    decoded = verify_firebase_token_from_auth_header(auth_header)
    uid = decoded["uid"]
    
    draft = await get_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")
    if draft["uid"] != uid:
        raise HTTPException(status_code=403, detail="Not authorized")
        
    creds = await authenticate_gmail(uid)
    if not creds:
        raise HTTPException(status_code=400, detail="Gmail not connected")
        
    service = build('gmail', 'v1', credentials=creds)
    
    success = await asyncio.to_thread(send_gmail_draft, service, draft_id)
    if success:
        await update_draft_status(draft_id, "sent")
        return {"ok": True, "message": "Draft sent"}
    else:
        raise HTTPException(status_code=500, detail="Failed to send draft")

@app.post("/drafts/{draft_id}/reject")
async def reject_draft(draft_id: str, request: Request):
    auth_header = request.headers.get("Authorization")
    decoded = verify_firebase_token_from_auth_header(auth_header)
    uid = decoded["uid"]
    
    draft = await get_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")
    if draft["uid"] != uid:
        raise HTTPException(status_code=403, detail="Not authorized")
        
    creds = await authenticate_gmail(uid)
    if not creds:
        raise HTTPException(status_code=400, detail="Gmail not connected")
        
    service = build('gmail', 'v1', credentials=creds)
    
    success = await asyncio.to_thread(delete_gmail_draft, service, draft_id)
    if success:
        await update_draft_status(draft_id, "rejected")
        return {"ok": True, "message": "Draft deleted"}
    else:
        raise HTTPException(status_code=500, detail="Failed to delete draft")

@app.put("/drafts/{draft_id}")
async def update_draft(draft_id: str, body: DraftUpdateBody, request: Request):
    auth_header = request.headers.get("Authorization")
    decoded = verify_firebase_token_from_auth_header(auth_header)
    uid = decoded["uid"]
    
    draft = await get_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")
    if draft["uid"] != uid:
        raise HTTPException(status_code=403, detail="Not authorized")
        
    creds = await authenticate_gmail(uid)
    if not creds:
        raise HTTPException(status_code=400, detail="Gmail not connected")
        
    service = build('gmail', 'v1', credentials=creds)
    
    success = await asyncio.to_thread(
        update_gmail_draft, 
        service, 
        draft_id, 
        draft["original_sender"], 
        draft["original_subject"], 
        body.ai_reply_body
    )
    if success:
        await update_draft_body(draft_id, body.ai_reply_body)
        return {"ok": True, "message": "Draft updated"}
    else:
        raise HTTPException(status_code=500, detail="Failed to update draft")
