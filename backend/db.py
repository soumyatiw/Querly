import os
import motor.motor_asyncio
import uuid
from cryptography.fernet import Fernet
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY")

if not ENCRYPTION_KEY:
    raise ValueError(
        "\n\n"
        "ENCRYPTION_KEY is missing from your .env file!\n"
        "Generate one with:\n"
        "  python3 -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\"\n"
        "Then add it to backend/.env as:\n"
        "  ENCRYPTION_KEY=\"the-generated-key-here\"\n"
        "\nWARNING: Never change this key after tokens have been stored, or all Gmail connections will break.\n"
    )

fernet = Fernet(ENCRYPTION_KEY.encode())

client = motor.motor_asyncio.AsyncIOMotorClient(MONGODB_URI)
db = client.querly

users_collection = db.users
oauth_state_collection = db.oauth_state
jobs_collection = db.jobs
drafts_collection = db.drafts

knowledge_collection = db.knowledge_base

async def init_db():
    """
    Idempotent index creation — safe to run on every startup.
    MongoDB ignores create_index calls when the index already exists.
    """
    # users — fast uid lookup; enforce uniqueness
    await users_collection.create_index("uid", unique=True)

    # oauth_state — TTL: auto-delete state tokens after 10 minutes
    await oauth_state_collection.create_index(
        "created_at", expireAfterSeconds=600
    )

    # drafts — list drafts by user + filter by status efficiently
    await drafts_collection.create_index([("uid", 1), ("status", 1)])
    # also sort by newest first
    await drafts_collection.create_index([("uid", 1), ("created_at", -1)])
    # PROBLEM 3 FIX: unique compound index prevents duplicate drafts for same email
    await drafts_collection.create_index(
        [("uid", 1), ("original_email_id", 1)],
        unique=True,
        sparse=True  # sparse so docs without original_email_id aren't affected
    )

    # knowledge_base — retrieve chunks by user
    await knowledge_collection.create_index("uid")

    print("✅ MongoDB indexes verified.")

def encrypt_token(token: str) -> str:
    if not token:
        return None
    return fernet.encrypt(token.encode()).decode()

def decrypt_token(encrypted_token: str) -> str:
    if not encrypted_token:
        return None
    return fernet.decrypt(encrypted_token.encode()).decode()

async def save_user_tokens(uid: str, email: str, access_token: str, refresh_token: str, token_expiry: str):
    update_fields = {
        "google_access_token": encrypt_token(access_token),
        "updated_at": datetime.utcnow()
    }
    
    if refresh_token:
        update_fields["google_refresh_token"] = encrypt_token(refresh_token)
    if token_expiry:
        update_fields["token_expiry"] = token_expiry
        
    existing = await users_collection.find_one({"uid": uid})
    if existing:
        await users_collection.update_one({"uid": uid}, {"$set": update_fields})
    else:
        doc = {
            "uid": uid,
            "email": email,
            "created_at": datetime.utcnow(),
            "settings": {
                "tone": "Professional",
                "business_context": "",
                "persona_notes": ""
            }
        }
        doc.update(update_fields)
        await users_collection.insert_one(doc)

async def get_user_tokens(uid: str):
    user = await users_collection.find_one({"uid": uid})
    if not user:
        return None
    
    return {
        "google_access_token": decrypt_token(user.get("google_access_token")),
        "google_refresh_token": decrypt_token(user.get("google_refresh_token")),
        "token_expiry": user.get("token_expiry"),
        "email": user.get("email")
    }

async def save_oauth_state(state: str, uid: str):
    await oauth_state_collection.insert_one({
        "state": state,
        "uid": uid,
        "created_at": datetime.utcnow()
    })

async def get_oauth_state(state: str):
    record = await oauth_state_collection.find_one({"state": state})
    if record:
        # State is single-use, so delete it after retrieval
        await oauth_state_collection.delete_one({"state": state})
        return record
    return None

async def create_job(uid: str) -> str:
    job_id = str(uuid.uuid4())
    await jobs_collection.insert_one({
        "job_id": job_id,
        "uid": uid,
        "status": "pending",
        "created_at": datetime.utcnow(),
        "result_summary": ""
    })
    return job_id

async def update_job_status(job_id: str, status: str, result_summary: str = ""):
    await jobs_collection.update_one(
        {"job_id": job_id},
        {"$set": {"status": status, "result_summary": result_summary}}
    )

async def get_job_status(job_id: str):
    return await jobs_collection.find_one({"job_id": job_id}, {"_id": 0})

async def save_draft(
    draft_id: str,
    uid: str,
    original_email_id: str,
    original_subject: str,
    original_sender: str,
    original_body_snippet: str,
    ai_reply_body: str,
    tone_used: str,
    categorization: dict = None,
    email_date: str = None,
):
    snippet = original_body_snippet[:300] + "\u2026" if len(original_body_snippet) > 300 else original_body_snippet
    doc = {
        "draft_id":              draft_id,
        "uid":                   uid,
        "original_email_id":     original_email_id,
        "original_subject":      original_subject,
        "original_sender":       original_sender,
        # PROBLEM 4 FIX: separate fields — original_body for context, ai_reply_body for display
        "original_body":         original_body_snippet,  # full original email text
        "original_body_snippet": snippet,                # short preview for card
        "ai_reply_body":         ai_reply_body,
        "tone_used":             tone_used,
        # PROBLEM 2 FIX: explicit type tag so queries can distinguish AI drafts from anything else
        "type":                  "ai_draft",
        "status":                "pending_review" if draft_id else "skipped",
        "created_at":            datetime.utcnow(),
        "email_date":            email_date,       # raw Date header from Gmail
    }
    if categorization:
        doc["categorization"] = categorization
    await drafts_collection.insert_one(doc)

async def get_user_drafts(uid: str, days: int = None, pending_only: bool = False):
    # PROBLEM 2 FIX: always scope to ai_draft type; optionally also filter status
    query = {"uid": uid, "type": "ai_draft"}
    if pending_only:
        query["status"] = "pending_review"
    if days:
        from datetime import timedelta
        cutoff = datetime.utcnow() - timedelta(days=days)
        query["created_at"] = {"$gte": cutoff}
    cursor = drafts_collection.find(query).sort("created_at", -1)
    return await cursor.to_list(length=200)

async def get_processed_email_ids(uid: str) -> set:
    """Return the set of original_email_ids already stored for this user to prevent re-processing."""
    cursor = drafts_collection.find(
        {"uid": uid},
        {"original_email_id": 1, "_id": 0}
    )
    docs = await cursor.to_list(length=10000)
    return {d["original_email_id"] for d in docs if d.get("original_email_id")}

async def check_draft_exists(uid: str, email_id: str) -> bool:
    """Returns True if a draft/skipped record already exists for this email ID."""
    doc = await drafts_collection.find_one({"uid": uid, "original_email_id": email_id})
    return doc is not None

async def get_draft(draft_id: str):
    return await drafts_collection.find_one({"draft_id": draft_id})

async def update_draft_status(draft_id: str, status: str):
    await drafts_collection.update_one({"draft_id": draft_id}, {"$set": {"status": status}})

async def update_draft_body(draft_id: str, ai_reply_body: str):
    await drafts_collection.update_one({"draft_id": draft_id}, {"$set": {"ai_reply_body": ai_reply_body}})

async def save_user_settings(uid: str, tone: str, business_context: str, persona_notes: str):
    await users_collection.update_one(
        {"uid": uid},
        {"$set": {
            "settings": {
                "tone": tone,
                "business_context": business_context,
                "persona_notes": persona_notes
            }
        }},
        upsert=True
    )

async def get_user_settings(uid: str):
    user = await users_collection.find_one({"uid": uid})
    if user and "settings" in user:
        return user["settings"]
    return {
        "tone": "Professional",
        "business_context": "",
        "persona_notes": ""
    }

async def get_category_summary(uid: str, days: int = 7):
    from datetime import timedelta
    cutoff = datetime.utcnow() - timedelta(days=days)
    pipeline = [
        {"$match": {"uid": uid, "created_at": {"$gte": cutoff}}},
        {"$group": {"_id": "$categorization.category", "count": {"$sum": 1}}}
    ]
    cursor = drafts_collection.aggregate(pipeline)
    results = await cursor.to_list(length=100)
    summary = {}
    for r in results:
        category = r["_id"] if r["_id"] else "unknown"
        summary[category] = r["count"]
    return summary
