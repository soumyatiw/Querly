import os
import json
import re
import traceback
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

# Fail loudly at import time if the key is missing — catches misconfigured .env early
assert os.getenv("GEMINI_API_KEY"), (
    "GEMINI_API_KEY is not set. Add it to backend/.env and restart the server."
)

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

# Use Flash for fast structured tasks (categorization)
# Use Pro for quality reply generation
_flash  = genai.GenerativeModel("models/gemini-2.5-flash")
_pro    = genai.GenerativeModel("models/gemini-2.5-pro")


# ── Reply generation ────────────────────────────────────────────────────────────

def generate_reply(email_body, tone="Professional", business_context="", persona_notes="", relevant_context=None):
    context_block = ""
    if relevant_context:
        joined = "\n---\n".join(relevant_context)
        context_block = (
            "Relevant company information to use if applicable:\n"
            f"{joined}\n\n"
        )

    prompt = (
        f"{context_block}"
        "You are an executive email assistant. Generate a reply to the following email.\n\n"
        f"Tone: {tone}\n"
        f"Business context: {business_context or 'Not specified'}\n"
        f"Style notes: {persona_notes or 'None'}\n\n"
        "Rules:\n"
        "- Match the tone exactly\n"
        "- Keep replies under 150 words unless the email genuinely demands more\n"
        "- Never start with \"I hope this email finds you well\"\n"
        "- Sign off appropriately for the tone\n"
        "- If relevant company information is provided above, use it to give accurate, specific answers\n"
        "- Output ONLY the email reply text — no subject line, no preamble, no explanation\n\n"
        f"Original email:\n{email_body}\n"
    )

    # ── Try Pro first ───────────────────────────────────────────────────────────
    try:
        response = _pro.generate_content(prompt)

        # Log safety / finish signals so we can diagnose silent failures
        if hasattr(response, "prompt_feedback") and response.prompt_feedback:
            print(f"[Gemini] prompt_feedback: {response.prompt_feedback}")
        if response.candidates:
            finish = response.candidates[0].finish_reason
            print(f"[Gemini] finish_reason: {finish}")

        # Raise clearly if the text is empty rather than returning a silent fallback
        if not response.text or not response.text.strip():
            raise ValueError(
                f"Gemini Pro returned empty text. "
                f"finish_reason={response.candidates[0].finish_reason if response.candidates else 'N/A'}"
            )

        return response.text

    except Exception as pro_err:
        print(f"[Gemini] generate_reply PRO error:")
        traceback.print_exc()

    # ── Fallback to Flash ───────────────────────────────────────────────────────
    try:
        response = _flash.generate_content(prompt)

        if hasattr(response, "prompt_feedback") and response.prompt_feedback:
            print(f"[Gemini Flash] prompt_feedback: {response.prompt_feedback}")
        if response.candidates:
            finish = response.candidates[0].finish_reason
            print(f"[Gemini Flash] finish_reason: {finish}")

        if not response.text or not response.text.strip():
            raise ValueError(
                f"Gemini Flash returned empty text. "
                f"finish_reason={response.candidates[0].finish_reason if response.candidates else 'N/A'}"
            )

        return response.text

    except Exception as flash_err:
        print(f"[Gemini] generate_reply FLASH FALLBACK error:")
        traceback.print_exc()
        # Re-raise so the caller (gmail_handler) can catch it, log the email ID,
        # record a generation_error in the job summary, and skip gracefully.
        raise flash_err


# ── Email categorization ─────────────────────────────────────────────────────────

_STRIP_MD = re.compile(r"```(?:json)?(.*?)```", re.DOTALL)

def _clean_json(text: str) -> str:
    text = text.strip()
    m = _STRIP_MD.search(text)
    if m:
        text = m.group(1).strip()
    # Remove any trailing non-JSON text after the closing brace
    brace_end = text.rfind("}")
    if brace_end != -1:
        text = text[:brace_end + 1]
    return text.strip()


def categorize_email(subject: str, body: str, sender: str) -> dict:
    body_preview = body[:1500] if len(body) > 1500 else body

    prompt = (
        "You are an email classification system. Classify the email below.\n"
        "Respond with ONLY a raw JSON object — absolutely no markdown, no backticks, no extra text.\n\n"
        f"Subject: {subject}\n"
        f"From: {sender}\n"
        f"Body: {body_preview}\n\n"
        "Required JSON format (copy this shape exactly):\n"
        '{"category":"...","priority":"...","summary":"...","should_reply":true}\n\n'
        "Rules for each field:\n"
        '- "category": MUST be one of: urgent, client_inquiry, meeting_request, newsletter, internal, spam, other\n'
        '  * urgent = needs immediate attention or has a deadline\n'
        '  * client_inquiry = question or request from a client or prospect\n'
        '  * meeting_request = scheduling, calendar invite, or availability check\n'
        '  * newsletter = marketing email, digest, mailing-list, promotional\n'
        '  * spam = unwanted bulk email\n'
        '  * internal = from a colleague or team member at the same company\n'
        '  * other = does not fit any of the above\n'
        '- "priority": MUST be one of: high, medium, low\n'
        '- "summary": one clear sentence describing what this email is about\n'
        '- "should_reply": true if a human reply is needed, false for newsletters/spam/automated\n\n'
        "Output ONLY the JSON object, nothing else."
    )

    raw_text = ""
    try:
        response = _flash.generate_content(prompt)
        raw_text = response.text
        text = _clean_json(raw_text)
        result = json.loads(text)

        # Normalise and validate
        valid_cats = {"urgent", "client_inquiry", "meeting_request", "newsletter", "internal", "spam", "other"}
        valid_pris = {"high", "medium", "low"}

        if result.get("category") not in valid_cats:
            result["category"] = "other"
        if result.get("priority") not in valid_pris:
            result["priority"] = "medium"
        if not isinstance(result.get("should_reply"), bool):
            cat = result.get("category", "other")
            result["should_reply"] = cat not in ("newsletter", "spam")
        if not result.get("summary"):
            result["summary"] = f"Email from {sender} about: {subject}"

        return result

    except json.JSONDecodeError as je:
        print(f"Categorization JSON parse error: {je}")
        print(f"Raw Gemini response: {repr(raw_text[:300])}")
        traceback.print_exc()
        # Fallback — assume reply is needed so it isn't silently dropped
        return {
            "category": "client_inquiry",
            "priority": "medium",
            "summary": f"Email from {sender} regarding: {subject}",
            "should_reply": True,
        }
    except Exception as e:
        print(f"categorize_email error: {e}")
        traceback.print_exc()
        return {
            "category": "client_inquiry",
            "priority": "medium",
            "summary": f"Email from {sender} regarding: {subject}",
            "should_reply": True,
        }
