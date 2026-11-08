import re
from urllib.parse import urlparse
from typing import Any, Dict, List, Optional, Set, Tuple
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.logger import app_logger


class BrowserSecurityViolation(Exception):
    """Raised when a browser action attempts to violate safety boundaries."""
    pass


class SensitiveFieldViolation(BrowserSecurityViolation):
    """Raised when an action attempts to read or fill sensitive fields (passwords, payment, auth)."""
    pass


class DomainSecurityViolation(BrowserSecurityViolation):
    """Raised when an action targets a domain outside the user-approved domain."""
    pass


# Default safe domains that can be approved
DEFAULT_APPROVED_DOMAINS: Set[str] = {
    "wikipedia.org",
    "en.wikipedia.org",
    "python.org",
    "docs.python.org",
    "fastapi.tiangolo.com",
    "localhost",
    "127.0.0.1",
}

# Regex patterns identifying sensitive fields
SENSITIVE_FIELD_PATTERNS = re.compile(
    r"(?i)\b(password|passwd|pwd|passcode|secret|pin|cvv|cvc|credit[_\s-]?card|"
    r"card[_\s-]?number|card[_\s-]?num|expiry|exp[_\s-]?date|ssn|social[_\s-]?security|"
    r"token|auth[_\s-]?token|otp|two[_\s-]?factor|2fa|mfa|routing[_\s-]?number|"
    r"bank[_\s-]?account|account[_\s-]?number|billing|security[_\s-]?code)\b"
)

# Regex patterns identifying forbidden submission and purchase actions
FORBIDDEN_ACTION_PATTERNS = re.compile(
    r"(?i)\b(submit|submit[_\s-]?form|purchase|buy|pay|checkout|place[_\s-]?order|"
    r"order[_\s-]?now|send[_\s-]?message|post[_\s-]?comment|publish|confirm[_\s-]?purchase|"
    r"finish[_\s-]?quiz|submit[_\s-]?quiz|submit[_\s-]?exam|grade[_\s-]?test|"
    r"take[_\s-]?test|captcha|recaptcha|hcaptcha|bypass)\b"
)


def normalize_domain(domain_or_url: str) -> str:
    """Extract and normalize clean lowercase domain name from input."""
    if not domain_or_url:
        return ""
    clean = domain_or_url.strip().lower()
    if clean.startswith("http://") or clean.startswith("https://"):
        parsed = urlparse(clean)
        clean = parsed.netloc
    # Strip port if present
    if ":" in clean:
        clean = clean.split(":")[0]
    return clean


def is_domain_allowed(url: str, approved_domain: str) -> bool:
    """
    Check whether a URL belongs to the approved domain or a legitimate subdomain of it.
    Strictly prevents open redirects and domain spoofing (e.g., evil-wikipedia.org).
    """
    if not url or not approved_domain:
        return False

    clean_approved = normalize_domain(approved_domain)
    if not clean_approved:
        return False

    try:
        parsed = urlparse(url)
    except Exception:
        return False

    # Scheme must be http or https only (blocks javascript:, file:, data:, chrome:, etc.)
    if parsed.scheme not in ("http", "https"):
        return False

    host = (parsed.netloc or "").lower().split(":")[0]
    if not host:
        return False

    if host == clean_approved:
        return True

    # Allow subdomains (e.g. en.wikipedia.org matches wikipedia.org)
    if host.endswith("." + clean_approved):
        return True

    return False


def validate_approved_url(url: str, approved_domain: str) -> str:
    """
    Validate that a URL strictly belongs to the user-approved domain.
    Raises DomainSecurityViolation if the URL is invalid or attempts to escape the domain.
    """
    if not url or not isinstance(url, str):
        raise DomainSecurityViolation("A valid non-empty URL string is required.")

    clean_url = url.strip()
    if not clean_url.startswith(("http://", "https://")):
        raise DomainSecurityViolation(f"Unsafe URL scheme in '{url}'. Only HTTP and HTTPS are permitted.")

    if not is_domain_allowed(clean_url, approved_domain):
        raise DomainSecurityViolation(
            f"Access denied: URL '{clean_url}' does not belong to the user-approved domain '{approved_domain}'. "
            "Browser automation is strictly restricted to user-approved domains."
        )

    return clean_url


def is_sensitive_field(
    field_type: Optional[str] = None,
    field_name: Optional[str] = None,
    field_id: Optional[str] = None,
    autocomplete: Optional[str] = None,
    label_or_desc: Optional[str] = None,
    selector: Optional[str] = None,
) -> bool:
    """
    Examines input field attributes to detect password, payment, or auth fields.
    Returns True if the field is sensitive.
    """
    # 1. Type check
    t = (field_type or "").strip().lower()
    if t in ("password", "hidden", "file"):
        return True

    # 2. Autocomplete check (RFC 7033 / WHATWG standards)
    ac = (autocomplete or "").strip().lower()
    if any(s in ac for s in ("current-password", "new-password", "cc-number", "cc-csc", "cc-exp", "one-time-code")):
        return True

    # 3. Pattern match against combined metadata (handle snake_case, camelCase, and separators)
    raw_meta = f"{field_name or ''} {field_id or ''} {label_or_desc or ''} {selector or ''}"
    spaced = re.sub(r'([a-z])([A-Z])', r'\1 \2', raw_meta)
    normalized_meta = re.sub(r'[^a-zA-Z0-9]+', ' ', spaced).lower()

    if SENSITIVE_FIELD_PATTERNS.search(normalized_meta) or SENSITIVE_FIELD_PATTERNS.search(raw_meta):
        return True

    return False


def check_forbidden_action(
    action_type: str,
    target_selector: Optional[str] = None,
    description: Optional[str] = None,
) -> None:
    """
    Verifies that the requested action is NOT an automated submission,
    purchase, message transmission, or quiz submission.
    Raises BrowserSecurityViolation if a forbidden action is detected.
    """
    act = (action_type or "").strip().lower()

    if act in ("submit_form", "click_submit", "purchase", "send_message", "submit_quiz"):
        raise BrowserSecurityViolation(
            f"Action '{action_type}' is prohibited. Jarvis cannot submit forms, make purchases, "
            "send messages, or submit quizzes on behalf of the user. The final submission controls must remain user-operated."
        )

    raw_text = f"{action_type or ''} {target_selector or ''} {description or ''}"
    spaced = re.sub(r'([a-z])([A-Z])', r'\1 \2', raw_text)
    normalized_text = re.sub(r'[^a-zA-Z0-9]+', ' ', spaced).lower()

    if FORBIDDEN_ACTION_PATTERNS.search(normalized_text) or FORBIDDEN_ACTION_PATTERNS.search(raw_text):
        raise BrowserSecurityViolation(
            f"Action '{action_type}' targets a forbidden transaction or submission control. "
            "The agent is strictly prohibited from automating submit, send, purchase, or exam actions."
        )


class BrowserAutomationManager:
    """
    Server-side manager for domain approvals, action validation,
    and safe browser operation planning.
    """

    def __init__(self):
        self._approved_domains: Set[str] = set(DEFAULT_APPROVED_DOMAINS)

    def get_approved_domains(self) -> List[str]:
        """Return list of currently approved domains."""
        return sorted(list(self._approved_domains))

    def approve_domain(self, domain: str) -> str:
        """Explicitly add a domain to the approved set."""
        clean = normalize_domain(domain)
        if not clean or "." not in clean:
            raise ValueError(f"Invalid domain format: '{domain}'. Must be a valid domain like 'wikipedia.org'.")
        self._approved_domains.add(clean)
        app_logger.info("User explicitly approved domain for browser automation: %s", clean)
        return clean

    def revoke_domain(self, domain: str) -> None:
        """Revoke a domain from the approved set."""
        clean = normalize_domain(domain)
        self._approved_domains.discard(clean)
        app_logger.info("Revoked domain for browser automation: %s", clean)

    def is_approved(self, domain: str) -> bool:
        """Check if a domain is currently approved."""
        clean = normalize_domain(domain)
        return clean in self._approved_domains or any(
            clean == d or clean.endswith("." + d) for d in self._approved_domains
        )


# Global singleton instance
browser_manager = BrowserAutomationManager()
