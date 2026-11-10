import base64
import html
import re
from typing import Any, Dict, List, Optional
from googleapiclient.discovery import build

from app.core.config import settings
from app.core.google_auth import (
    google_auth_manager,
    GoogleAuthRequiredError,
    GoogleTokenRevokedError,
)
from app.core.logger import app_logger
from app.tools.base import ToolResult


def _extract_plain_text_from_payload(payload: Dict[str, Any]) -> str:
    """Recursively extract plain text or stripped HTML from a Gmail message payload."""
    # Check direct body data
    body = payload.get("body", {})
    mime_type = payload.get("mimeType", "")
    data = body.get("data")

    if data:
        try:
            decoded = base64.urlsafe_b64decode(data.encode("ascii")).decode("utf-8", errors="replace")
            if "html" in mime_type:
                decoded = re.sub(r"<style[\s\S]*?</style>", "", decoded, flags=re.IGNORECASE)
                decoded = re.sub(r"<script[\s\S]*?</script>", "", decoded, flags=re.IGNORECASE)
                decoded = re.sub(r"<[^>]+>", " ", decoded)
                decoded = html.unescape(decoded)
            return re.sub(r"\s+", " ", decoded).strip()
        except Exception:
            pass

    # Check multipart parts
    parts = payload.get("parts", [])
    # 1. Prefer text/plain
    for part in parts:
        if part.get("mimeType") == "text/plain":
            text = _extract_plain_text_from_payload(part)
            if text:
                return text

    # 2. Fallback to text/html
    for part in parts:
        if "text" in part.get("mimeType", "") or "multipart" in part.get("mimeType", ""):
            text = _extract_plain_text_from_payload(part)
            if text:
                return text

    return ""


def list_gmail_messages(
    max_results: int = 5,
    query: Optional[str] = None,
    label_ids: Optional[List[str]] = None,
) -> ToolResult:
    """
    Read-only tool to list recent Gmail messages with metadata (Sender, Subject, Date, Snippet).
    Strictly read-only: does not send, delete, archive, label, or mark messages as read.
    """
    if not google_auth_manager.is_connected():
        return ToolResult(
            success=False,
            error=(
                "Google account is not connected. Please connect your Google account "
                "via /api/auth/google/url to enable Gmail tools."
            ),
        )

    # Validate arguments
    max_results = max(1, min(int(max_results), settings.MAX_GMAIL_RESULTS))
    clean_query = query.strip() if query else None
    if clean_query and len(clean_query) > 150:
        clean_query = clean_query[:150]

    effective_labels = label_ids or ["INBOX"]

    try:
        creds = google_auth_manager.get_credentials()
        service = build("gmail", "v1", credentials=creds, cache_discovery=False)

        list_call = service.users().messages().list(
            userId="me",
            q=clean_query,
            labelIds=effective_labels,
            maxResults=max_results,
        )
        list_response = list_call.execute()
        raw_messages = list_response.get("messages", [])

        if not raw_messages:
            return ToolResult(
                success=True,
                output={
                    "count": 0,
                    "messages": [],
                    "message": "No messages found matching the query/labels.",
                },
            )

        items = []
        for ref in raw_messages:
            msg_id = ref.get("id")
            detail = service.users().messages().get(
                userId="me",
                id=msg_id,
                format="metadata",
                metadataHeaders=["From", "Subject", "Date"],
            ).execute()

            headers = {h.get("name"): h.get("value") for h in detail.get("payload", {}).get("headers", [])}
            items.append({
                "id": msg_id,
                "thread_id": detail.get("threadId"),
                "sender": headers.get("From", "Unknown"),
                "subject": headers.get("Subject", "(No Subject)"),
                "date": headers.get("Date", ""),
                "snippet": detail.get("snippet", ""),
            })

        return ToolResult(
            success=True,
            output={
                "count": len(items),
                "messages": items,
                "filter_query": clean_query,
                "read_only": True,
            },
        )

    except (GoogleAuthRequiredError, GoogleTokenRevokedError) as e:
        return ToolResult(success=False, error=str(e))
    except Exception as e:
        app_logger.warning("Gmail API list_messages error: %s", e)
        return ToolResult(success=False, error=f"Gmail API error: {str(e)}")


def summarize_gmail_messages(
    message_ids: Optional[List[str]] = None,
    max_results: int = 3,
    query: Optional[str] = None,
    custom_instructions: Optional[str] = None,
) -> ToolResult:
    """
    Read-only tool to summarize a selected message or small recent-message set using Gemini.
    Explicitly discloses that email content is sent to Gemini for summarization.
    Does NOT store email body text in persistent memory or audit logs.
    """
    if not google_auth_manager.is_connected():
        return ToolResult(
            success=False,
            error="Google account is not connected. Please connect via /api/auth/google/url.",
        )

    max_results = max(1, min(int(max_results), 5))
    target_ids = message_ids[:5] if message_ids else []

    try:
        creds = google_auth_manager.get_credentials()
        service = build("gmail", "v1", credentials=creds, cache_discovery=False)

        # If message_ids not explicitly supplied, list top messages
        if not target_ids:
            list_res = service.users().messages().list(
                userId="me",
                q=query or "is:unread",
                maxResults=max_results,
            ).execute()
            target_ids = [m["id"] for m in list_res.get("messages", [])]

        if not target_ids:
            return ToolResult(
                success=True,
                output={
                    "count": 0,
                    "summary": "No messages found to summarize.",
                    "disclosure": "Email content is sent to Gemini only when messages exist to analyze.",
                },
            )

        collected = []
        for mid in target_ids:
            full_msg = service.users().messages().get(userId="me", id=mid, format="full").execute()
            payload = full_msg.get("payload", {})
            headers = {h.get("name"): h.get("value") for h in payload.get("headers", [])}
            body_text = _extract_plain_text_from_payload(payload)
            # Cap individual message text at 3000 chars to avoid prompt exhaustion
            capped_body = body_text[:3000] if len(body_text) > 3000 else body_text

            collected.append({
                "id": mid,
                "sender": headers.get("From", "Unknown"),
                "subject": headers.get("Subject", "(No Subject)"),
                "date": headers.get("Date", ""),
                "body": capped_body,
            })

        disclosure = "Notice: Email text from these messages is being transmitted to Google Gemini for summarization."

        # Summarize via Gemini
        summary_text = _generate_gemini_summary(collected, custom_instructions)

        # Format clean metadata without the full body text in the output
        metadata_list = [
            {"id": m["id"], "sender": m["sender"], "subject": m["subject"], "date": m["date"]}
            for m in collected
        ]

        return ToolResult(
            success=True,
            output={
                "count": len(collected),
                "summary": summary_text,
                "analyzed_messages": metadata_list,
                "disclosure": disclosure,
                "read_only": True,
            },
        )

    except (GoogleAuthRequiredError, GoogleTokenRevokedError) as e:
        return ToolResult(success=False, error=str(e))
    except Exception as e:
        app_logger.warning("Gmail summarize error: %s", e)
        return ToolResult(success=False, error=f"Gmail summarization error: {str(e)}")


def _generate_gemini_summary(messages: List[Dict[str, Any]], custom_instructions: Optional[str]) -> str:
    """Generate a structured summary using Gemini, with a deterministic fallback for test environments."""
    if not settings.GEMINI_API_KEY:
        # Fallback summary when running offline or in unit tests without API key
        lines = ["Summary of Recent Emails:"]
        for m in messages:
            lines.append(f"- From {m['sender']}: '{m['subject']}' - Key topic: {m['body'][:120]}...")
        return "\n".join(lines)

    try:
        from google import genai
        client = genai.Client(api_key=settings.GEMINI_API_KEY)

        formatted_emails = []
        for idx, m in enumerate(messages, 1):
            formatted_emails.append(
                f"[Email {idx}]\n"
                f"From: {m['sender']}\n"
                f"Subject: {m['subject']}\n"
                f"Date: {m['date']}\n"
                f"Body Content:\n{m['body']}\n"
            )

        instructions = (
            "Summarize the following email messages concisely. Identify key senders, action items, "
            "urgency, and essential updates. Format cleanly with bullet points."
        )
        if custom_instructions:
            instructions += f"\nUser Instructions: {custom_instructions}"

        prompt = f"{instructions}\n\n=== EMAILS TO SUMMARIZE ===\n" + "\n---\n".join(formatted_emails)

        response = client.models.generate_content(
            model=settings.GEMINI_MODEL,
            contents=prompt,
        )
        return response.text.strip() if response.text else "No summary generated."
    except Exception as e:
        app_logger.warning("Gemini email summarization failed: %s", e)
        # Fallback to local brief
        return f"Could not generate AI summary ({str(e)}). Found {len(messages)} messages: " + ", ".join(
            f"'{m['subject']}' from {m['sender']}" for m in messages
        )
