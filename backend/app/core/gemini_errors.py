"""Friendly Gemini error translation, retry, and time budget for chat calls.

Google's raw Gemini errors are JSON dicts (e.g. ``{'error': {'code': 503,
'message': 'This model is currently experiencing high demand...',
'status': 'UNAVAILABLE'}}``). Those must never reach the chat UI — a user
who just said "hello" should not have to read an API error dump. This
module translates them into short, human messages (English, same voice as
the rest of the Companion), and bounds how long one model call may run so
a chat request fits inside Vercel Hobby's 10s serverless function timeout
(a request that runs past it comes back to the user as a raw HTTP 504).

Rules:
- One automatic retry on 503/UNAVAILABLE (overloaded), after a short
  delay — but only when enough of the time budget remains. A slow first
  call skips the retry and fails fast with the friendly message instead.
- Optional fallback model (``GEMINI_FALLBACK_MODEL``, default empty = off):
  Google's docs point new projects at ``gemini-3.5-flash-lite`` as well as
  ``gemini-3.8-flash``; if configured, one fallback attempt is made after
  the primary model stays overloaded. The primary model is never changed
  silently — the fallback only runs when the owner configured it.
- Full technical detail stays in server logs only; the UI gets the short
  message plus a short error code (``gemini_overloaded`` etc.).
"""

import asyncio
import time
from typing import Optional, Tuple

import httpx

from app.core.logger import app_logger

# Vercel Hobby kills serverless functions at 10s. Keep one chat request
# comfortably inside that: at most ~8s of Gemini work, so the response,
# history save, and serialization still fit before the gateway times out.
CHAT_TIME_BUDGET_SECONDS = 8.0
# One Gemini call may take at most this long before the SDK aborts it
# (google-genai HttpOptions.timeout is in milliseconds). A slow call fails
# fast with the friendly timeout message instead of hanging until Vercel
# kills the function and the user sees a raw HTTP 504.
GEMINI_CALL_TIMEOUT_SECONDS = 7.0
# One retry on 503, after this delay — only when the budget allows.
GEMINI_RETRY_DELAY_SECONDS = 2.0
# A retry only starts when at least this much of the budget remains;
# otherwise fail fast with the friendly message.
GEMINI_RETRY_MIN_REMAINING_SECONDS = 5.0
# A fallback-model attempt only starts when at least this much remains.
GEMINI_FALLBACK_MIN_REMAINING_SECONDS = 3.0

# Friendly messages — exact user-facing wording, in English. The 503 one
# is the wording the user asked for.
OVERLOADED_MESSAGE = "Gemini is busy, please try again in a few minutes"
MODEL_UNAVAILABLE_MESSAGE = "This Gemini model is not available — please tell the owner."
INVALID_KEY_MESSAGE = "Your Gemini key looks invalid or expired — please check it in Settings."
RATE_LIMITED_MESSAGE = "Too many requests — please wait a bit and try again."
TIMEOUT_MESSAGE = "That took too long — please try again."
GENERIC_MESSAGE = "Something went wrong talking to Gemini — please try again."


def classify_gemini_error(exc: BaseException) -> Tuple[str, str]:
    """Map a Gemini/SDK exception to (short_code, friendly_message).

    Uses the SDK's numeric ``code`` when present (``google.genai.errors``
    sets it), and falls back to matching the error text. Never returns raw
    API JSON — the friendly message is all the UI ever shows.
    """
    code = getattr(exc, "code", None)
    status = str(getattr(exc, "status", "") or "")
    text = " ".join(part for part in (str(code or ""), status, str(exc)) if part).lower()

    if (
        isinstance(exc, (asyncio.TimeoutError, TimeoutError, httpx.TimeoutException))
        or "timeout" in text
        or "timed out" in text
    ):
        return ("gemini_timeout", TIMEOUT_MESSAGE)
    if (
        code == 503
        or "503" in text
        or "unavailable" in text
        or "overloaded" in text
        or "high demand" in text
    ):
        return ("gemini_overloaded", OVERLOADED_MESSAGE)
    if (
        code == 429
        or "429" in text
        or "resource_exhausted" in text
        or "quota" in text
        or "rate limit" in text
    ):
        return ("gemini_rate_limited", RATE_LIMITED_MESSAGE)
    if (
        code in (401, 403)
        or "401" in text
        or "403" in text
        or "api_key_invalid" in text
        or "api key not valid" in text
        or "permission_denied" in text
        or "unauthenticated" in text
    ):
        return ("gemini_invalid_key", INVALID_KEY_MESSAGE)
    if (
        code == 404
        or "404" in text
        or "not_found" in text
        or "no longer available" in text
    ):
        return ("gemini_model_unavailable", MODEL_UNAVAILABLE_MESSAGE)
    return ("gemini_error", GENERIC_MESSAGE)


def is_retryable_gemini_error(exc: BaseException) -> bool:
    """Only 503/overloaded is worth retrying — a bad key or a retired
    model will fail exactly the same way on the next attempt."""
    return classify_gemini_error(exc)[0] == "gemini_overloaded"


async def generate_content_with_retry(
    client,
    *,
    model: str,
    contents,
    config,
    fallback_model: str = "",
    deadline: Optional[float] = None,
):
    """One ``generate_content`` call with a single retry on 503.

    - Attempts the primary model, then — only if it failed with a retryable
      503 AND at least ``GEMINI_RETRY_MIN_REMAINING_SECONDS`` of the time
      budget remains — waits ``GEMINI_RETRY_DELAY_SECONDS`` and tries the
      primary model once more.
    - If the primary model stays overloaded and a fallback model is
      configured, tries the fallback once (no extra delay, only when
      ``GEMINI_FALLBACK_MIN_REMAINING_SECONDS`` remain).
    - Raises the last exception when everything fails; callers translate it
      with :func:`classify_gemini_error`. Raises ``TimeoutError`` without
      calling the model at all when the budget is already spent, so a
      multi-turn chat stops instead of starting a call Vercel would kill.
    """
    if deadline is None:
        deadline = time.monotonic() + CHAT_TIME_BUDGET_SECONDS
    fallback_model = (fallback_model or "").strip()

    last_exc: Optional[BaseException] = None
    for attempt in (1, 2):
        if time.monotonic() > deadline - 1.0:
            raise TimeoutError("Gemini call exceeded the chat time budget")
        try:
            return client.models.generate_content(
                model=model, contents=contents, config=config
            )
        except Exception as exc:  # noqa: BLE001 — classified by the caller
            last_exc = exc
            if not is_retryable_gemini_error(exc):
                raise
            if attempt == 2:
                break
            remaining = deadline - time.monotonic()
            if remaining < GEMINI_RETRY_MIN_REMAINING_SECONDS:
                app_logger.warning(
                    "Gemini overloaded but only %.1fs of the chat budget remain; "
                    "skipping the retry so the request fails fast.",
                    remaining,
                )
                break
            app_logger.warning(
                "Gemini overloaded (attempt %d), retrying once in %.0fs.",
                attempt,
                GEMINI_RETRY_DELAY_SECONDS,
            )
            await asyncio.sleep(GEMINI_RETRY_DELAY_SECONDS)

    if fallback_model and (deadline - time.monotonic()) >= GEMINI_FALLBACK_MIN_REMAINING_SECONDS:
        app_logger.info(
            "Gemini primary model %s stayed overloaded; trying fallback model %s.",
            model,
            fallback_model,
        )
        return client.models.generate_content(
            model=fallback_model, contents=contents, config=config
        )

    assert last_exc is not None  # a loop iteration always ran or raised
    raise last_exc
