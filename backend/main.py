# backend/main.py
import os
from pathlib import Path
import json
from dotenv import load_dotenv
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials

import firebase_admin
from firebase_admin import auth as firebase_auth, credentials as firebase_credentials

# Local imports
from gmail_handler import save_credentials_to_file, authenticate_gmail, read_unread_emails_with_creds


load_dotenv()

app = FastAPI()

origins = [
    "http://localhost:3000",  # frontend URL
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# Init firebase-admin
if not firebase_admin._apps:
    sa = json.loads(os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON"))
    cred = firebase_credentials.Certificate(sa)
    firebase_admin.initialize_app(cred)

# Where your Google client_secret.json (credentials.json) lives
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
GOOGLE_CREDENTIALS_PATH = os.path.join(BASE_DIR, "credentials.json")
TOKENS_DIR = Path("tokens")
TOKENS_DIR.mkdir(exist_ok=True)

# In-memory state store for flows (for demo only — use DB or redis in prod)
oauth_flows = {}

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
        user_email = decoded.get("email")
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

    # store the flow in memory keyed by state, along with uid
    oauth_flows[state] = {"flow": flow, "uid": uid}
    # return URL to frontend to redirect user
    return JSONResponse({"url": auth_url})

@app.get("/auth/google/callback")
async def google_oauth_callback(request: Request):
    """
    Exchange code for tokens and save token JSON for the user
    Google will call this endpoint after user consenting.
    Query params will include state and code.
    """
    params = dict(request.query_params)
    state = params.get("state")
    code = params.get("code")

    if not state or not code or state not in oauth_flows:
        raise HTTPException(status_code=400, detail="Missing or invalid state")

    stored = oauth_flows.pop(state)
    flow = stored["flow"]
    uid = stored["uid"]

    # fetch token
    flow.fetch_token(code=code)
    creds = flow.credentials  # google.oauth2.credentials.Credentials

    # Save credentials json to backend/tokens/{uid}_token.json
    token_path = TOKENS_DIR / f"{uid}_token.json"
    save_credentials_to_file(creds, str(token_path))

    # Optionally: store linked email (fetch profile via Gmail API or from creds.id_token)
    # Here we attempt to read profile_email from creds.id_token if available
    connected_email = None
    try:
        id_info = creds.id_token  # may or may not be present
        # Note: id_token might not exist; safer to call Gmail profiles API
    except:
        id_info = None

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

@app.get("/gmail/status")
async def gmail_status(request: Request):
    """
    GET /gmail/status with Authorization: Bearer <firebase idToken>
    Returns whether user has token saved
    """
    auth_header = request.headers.get("Authorization")
    decoded = verify_firebase_token_from_auth_header(auth_header)
    uid = decoded["uid"]
    token_path = TOKENS_DIR / f"{uid}_token.json"
    if token_path.exists():
        # attempt to load and ensure valid
        creds = authenticate_gmail(str(token_path), GOOGLE_CREDENTIALS_PATH)
        if creds:
            # optionally get connected email via gmail profile
            try:
                service = build('gmail', 'v1', credentials=creds)
                profile = service.users().getProfile(userId='me').execute()
                connected_email = profile.get('emailAddress')
            except Exception:
                connected_email = None
            return {"connected": True, "connectedEmail": connected_email}
    return {"connected": False, "connectedEmail": None}

@app.post("/gmail/trigger")
async def gmail_trigger(request: Request):
    """
    POST /gmail/trigger with Authorization header to trigger read_unread_emails_with_creds
    """
    auth_header = request.headers.get("Authorization")
    decoded = verify_firebase_token_from_auth_header(auth_header)
    uid = decoded["uid"]
    token_path = TOKENS_DIR / f"{uid}_token.json"
    if not token_path.exists():
        raise HTTPException(status_code=404, detail="Gmail not connected")

    creds = authenticate_gmail(str(token_path), GOOGLE_CREDENTIALS_PATH)
    if not creds:
        raise HTTPException(status_code=500, detail="Invalid or expired credentials")

    # Run job synchronously (or spawn background task)
    read_unread_emails_with_creds(creds)
    return {"ok": True, "message": "Triggered Gmail read job"}
