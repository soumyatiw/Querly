# Querly

**Querly** is an AI-powered email assistant that reads your unread Gmail, categorises each message, drafts context-aware replies using Google Gemini, and gives you a human-in-the-loop review dashboard before anything is sent.

---

## ✨ Feature Overview

| Feature | Details |
|---|---|
| **AI Drafting** | Gemini generates replies; you approve, edit, or reject each one |
| **Email Categorisation** | Urgent · Client Inquiry · Meeting · Newsletter · Spam · Internal · Other |
| **RAG Knowledge Base** | Upload PDFs (FAQs, pricing) — Gemini references them when answering |
| **Tone & Style Settings** | Professional · Casual · Enthusiastic · Apologetic · Concise |
| **Background Jobs** | Email processing runs async; poll `/gmail/job/{id}` for status |
| **Encrypted Token Storage** | Gmail OAuth tokens encrypted at rest with Fernet |

---

## 🏗️ Tech Stack

| Layer | Technology |
|---|---|
| Frontend | Next.js 14 (App Router), CSS Modules |
| Backend | FastAPI, Python 3.11+ |
| Database | MongoDB (Atlas or local), Motor (async driver) |
| AI | Google Gemini 2.5 Pro via `google-generativeai` |
| Embeddings | `sentence-transformers` — `all-MiniLM-L6-v2` |
| PDF Parsing | PyMuPDF (`fitz`) |
| Auth | Firebase Auth (client) + Firebase Admin SDK (server) |
| Gmail | Google OAuth 2.0 + Gmail API |

---

## 📋 Prerequisites

- **Python 3.11+**
- **Node.js 18+** and **npm**
- A **MongoDB Atlas** cluster (free tier works) **or** a local MongoDB instance
- A **Google Cloud** project with the Gmail API enabled
- A **Firebase** project

---

## 🚀 Local Setup — Step by Step

### Step 1 — MongoDB Atlas

1. Go to [https://cloud.mongodb.com](https://cloud.mongodb.com) and create a free cluster.
2. Under **Database Access**, create a user with `readWrite` access.
3. Under **Network Access**, add `0.0.0.0/0` (or your IP) to the allowlist.
4. Click **Connect → Drivers** and copy the connection string:
   ```
   mongodb+srv://<user>:<password>@cluster0.xxxxx.mongodb.net/?retryWrites=true&w=majority
   ```
5. Paste it as `MONGODB_URI` in `backend/.env`.

> **Local alternative:** Install MongoDB Community Edition and use `mongodb://localhost:27017`.

---

### Step 2 — Google Cloud Console (OAuth + Gmail API)

1. Go to [https://console.cloud.google.com](https://console.cloud.google.com) and create (or select) a project.

2. **Enable the Gmail API:**
   - Navigate to **APIs & Services → Library**
   - Search for **Gmail API** → click **Enable**

3. **Configure the OAuth consent screen:**
   - Go to **APIs & Services → OAuth consent screen**
   - Select **External** → fill in the required fields
   - Add the scope `https://www.googleapis.com/auth/gmail.modify`
   - Add your email as a **test user** (required while the app is in "Testing" mode)

4. **Create OAuth 2.0 credentials:**
   - Go to **APIs & Services → Credentials → Create Credentials → OAuth client ID**
   - Application type: **Web application**
   - Authorised JavaScript origins: `http://localhost:3000`
   - Authorised redirect URIs: `http://localhost:8000/auth/google/callback`
   - Click **Create** → download the JSON

5. **Rename the downloaded file** to `credentials.json` and place it at:
   ```
   backend/credentials.json
   ```

6. Copy the **Client ID** and **Client Secret** into `backend/.env`:
   ```env
   GOOGLE_CLIENT_ID="...apps.googleusercontent.com"
   GOOGLE_CLIENT_SECRET="..."
   GOOGLE_REDIRECT_URI="http://localhost:8000/auth/google/callback"
   ```

---

### Step 3 — Firebase Project

1. Go to [https://console.firebase.google.com](https://console.firebase.google.com) → **Add project**.

2. **Enable Authentication:**
   - In the Firebase console go to **Authentication → Sign-in method**
   - Enable **Email/Password** and **Google**

3. **Get the Frontend (Client SDK) config:**
   - **Project Settings → General → Your apps → Add app → Web**
   - Copy the `firebaseConfig` object values into `frontend/.env.local`

4. **Get the Backend (Admin SDK) service account:**
   - **Project Settings → Service Accounts → Generate new private key**
   - Download the JSON file
   - Convert it to a single-line string:
     ```bash
     python3 -c "import sys, json; print(json.dumps(json.load(open('serviceAccount.json'))))"
     ```
   - Paste the output as `FIREBASE_SERVICE_ACCOUNT_JSON` in `backend/.env`

---

### Step 4 — Gemini API Key

1. Go to [https://aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey)
2. Click **Create API key** → copy it
3. Add to `backend/.env`:
   ```env
   GEMINI_API_KEY="AIza..."
   ```

---

### Step 5 — Generate the Encryption Key

Querly encrypts Gmail OAuth tokens at rest using Fernet symmetric encryption.
Run **one** of the following to generate a secure key:

```bash
# Option A — using Python secrets (recommended)
python3 -c "import secrets, base64; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())"

# Option B — using Fernet directly
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Add the output to `backend/.env`:
```env
ENCRYPTION_KEY="your-generated-key-here"
```

> ⚠️ **Keep this key constant.** Changing it will make all stored tokens unreadable.

---

### Step 6 — Backend Setup

```bash
cd backend

# Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate        # Mac/Linux
# .venv\Scripts\activate         # Windows

# Install dependencies
pip install -r requirements.txt

# Copy the example env file and fill in your values
cp .env.example .env
# nano .env  (or open in your editor)
```

**Required packages** (already in `requirements.txt`):
```
fastapi uvicorn[standard] motor pymongo python-dotenv
google-auth google-auth-oauthlib google-api-python-client
google-generativeai firebase-admin cryptography
beautifulsoup4 pymupdf sentence-transformers
```

**Start the server:**
```bash
uvicorn main:app --reload --port 8000
```

The API will be available at `http://localhost:8000`.  
Interactive docs: `http://localhost:8000/docs`

---

### Step 7 — Frontend Setup

```bash
cd frontend

# Install dependencies
npm install

# Copy the example env file and fill in your Firebase values
cp .env.local.example .env.local
# nano .env.local  (or open in your editor)
```

**Start the dev server:**
```bash
npm run dev
```

The app will be available at `http://localhost:3000`.

---

## 🔑 Environment Variable Reference

### `backend/.env`

| Variable | Description |
|---|---|
| `GEMINI_API_KEY` | Google AI Studio API key |
| `FIREBASE_SERVICE_ACCOUNT_JSON` | Full Firebase Admin SDK service account as a single-line JSON string |
| `MONGODB_URI` | MongoDB connection string |
| `ENCRYPTION_KEY` | Fernet key for encrypting Gmail tokens at rest |
| `GOOGLE_CLIENT_ID` | OAuth 2.0 client ID from Google Cloud Console |
| `GOOGLE_CLIENT_SECRET` | OAuth 2.0 client secret |
| `GOOGLE_REDIRECT_URI` | Must match the redirect URI registered in Google Cloud (`http://localhost:8000/auth/google/callback`) |
| `FRONTEND_URL` | Base URL of the frontend — used for CORS and post-OAuth redirect (`http://localhost:3000`) |

### `frontend/.env.local`

| Variable | Description |
|---|---|
| `NEXT_PUBLIC_FIREBASE_API_KEY` | Firebase web app API key |
| `NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN` | `your-project.firebaseapp.com` |
| `NEXT_PUBLIC_FIREBASE_PROJECT_ID` | Firebase project ID |
| `NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET` | `your-project.appspot.com` |
| `NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID` | Numeric sender ID |
| `NEXT_PUBLIC_FIREBASE_APP_ID` | Firebase web app ID |
| `NEXT_PUBLIC_API_URL` | Backend URL (`http://localhost:8000`) |

---

## 🗂️ Project Structure

```
Querly/
├── backend/
│   ├── main.py            # FastAPI app, all API endpoints
│   ├── db.py              # MongoDB collections + helpers
│   ├── gmail_handler.py   # Gmail OAuth, draft creation, email loop
│   ├── gemini.py          # Gemini AI — reply generation & categorisation
│   ├── rag.py             # PDF ingestion, embedding, similarity search
│   ├── credentials.json   # Google OAuth client secret (not committed)
│   ├── .env               # Secrets (not committed)
│   └── .env.example       # Template — commit this
│
└── frontend/
    ├── app/
    │   ├── page.js              # Landing page
    │   ├── login/page.js        # Login
    │   ├── signup/page.js       # Sign-up
    │   └── dashboard/
    │       ├── page.js          # Main dashboard (drafts, stats)
    │       └── settings/page.js # AI reply settings
    ├── components/
    │   └── DraftModal/          # Draft review modal
    ├── firebase.js              # Firebase client init
    ├── .env.local               # Frontend secrets (not committed)
    └── .env.local.example       # Template — commit this
```

---

## 🎉 Usage Flow

1. Open `http://localhost:3000` → **Sign up** with email or Google
2. On the **Dashboard** → click **Connect Gmail** → complete Google OAuth
3. *(Optional)* Go to **Settings** → choose your tone, add business context, upload knowledge-base PDFs
4. Back on the dashboard → click **Process Now**
5. Querly fetches unread emails, categorises them with Gemini, and creates Gmail drafts for emails that need replies
6. Each draft card appears in the dashboard — click it to open the **Review Modal**
7. Read the original email on the left, review (and optionally edit) the AI reply on the right
8. Click **Approve & Send**, **Save Edits**, or **Reject**