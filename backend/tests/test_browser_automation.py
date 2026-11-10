import pytest

from app.core.config import settings
from app.core.confirmation import confirmation_manager
from app.core.browser_automation import (
    browser_manager,
    validate_approved_url,
    is_domain_allowed,
    is_sensitive_field,
    check_forbidden_action,
    BrowserSecurityViolation,
    DomainSecurityViolation,
)
from app.tools.registry import tool_registry
from app.tools.browser_automation_tools import (
    browser_navigate,
    browser_fill_field,
)


# --- 1. Domain Restrictions & URL Validation Tests ---

def test_domain_matching_rules():
    """Verify exact match, subdomain match, and spoofing defenses."""
    approved = "wikipedia.org"

    # Exact and valid subdomains
    assert is_domain_allowed("https://wikipedia.org/wiki/Python", approved) is True
    assert is_domain_allowed("https://en.wikipedia.org/wiki/Python", approved) is True
    assert is_domain_allowed("http://de.wikipedia.org/wiki/Hauptseite", approved) is True

    # Malicious / foreign escapes
    assert is_domain_allowed("https://evil-wikipedia.org/phish", approved) is False
    assert is_domain_allowed("https://wikipedia.org.attacker.com/fake", approved) is False
    assert is_domain_allowed("https://google.com", approved) is False
    assert is_domain_allowed("javascript:alert(1)", approved) is False
    assert is_domain_allowed("file:///C:/Windows/win.ini", approved) is False
    assert is_domain_allowed("data:text/html,<b>pwned</b>", approved) is False


def test_validate_approved_url_rejection():
    """Verify validate_approved_url raises DomainSecurityViolation on escapes."""
    with pytest.raises(DomainSecurityViolation) as exc:
        validate_approved_url("https://malicious.com/steal", "python.org")
    assert "does not belong to the user-approved domain" in str(exc.value)

    with pytest.raises(DomainSecurityViolation):
        validate_approved_url("javascript:void(0)", "python.org")


def test_browser_navigate_rejects_unapproved_domain():
    """Verify navigation fails if the domain has not been approved by the user."""
    res = browser_navigate(url="https://unapproved-site.com", approved_domain="unapproved-site.com")
    assert res.success is False
    assert "is not approved" in res.error


def test_browser_navigate_rejects_escaped_url():
    """Verify navigation fails if target URL escapes the approved domain."""
    browser_manager.approve_domain("wikipedia.org")
    res = browser_navigate(url="https://phishing.com/login", approved_domain="wikipedia.org")
    assert res.success is False
    assert "does not belong to the user-approved domain" in res.error


# --- 2. Sensitive-Field Exclusion Tests ---

def test_sensitive_field_detection():
    """Verify detection of passwords, credit cards, CVVs, and auth tokens."""
    # Type check
    assert is_sensitive_field(field_type="password") is True
    assert is_sensitive_field(field_type="hidden") is True
    assert is_sensitive_field(field_type="file") is True

    # Autocomplete check
    assert is_sensitive_field(autocomplete="current-password") is True
    assert is_sensitive_field(autocomplete="cc-number") is True
    assert is_sensitive_field(autocomplete="one-time-code") is True

    # Metadata check
    assert is_sensitive_field(field_name="user_password") is True
    assert is_sensitive_field(field_id="txtCardCVV") is True
    assert is_sensitive_field(label_or_desc="Billing Credit Card Number") is True
    assert is_sensitive_field(selector="input#auth_token") is True
    assert is_sensitive_field(selector="input[name='ssn']") is True

    # Non-sensitive fields
    assert is_sensitive_field(field_type="text", field_name="q", selector="input[name='q']") is False
    assert is_sensitive_field(field_type="search", field_id="searchInput") is False
    assert is_sensitive_field(field_type="text", label_or_desc="Search articles") is False


def test_browser_fill_field_rejects_sensitive_field():
    """Verify browser_fill_field refuses to fill password or credit card fields."""
    browser_manager.approve_domain("wikipedia.org")
    res = browser_fill_field(
        selector="input[type='password']",
        value="SecretPass123",
        approved_domain="wikipedia.org",
        field_description="Account password",
    )
    assert res.success is False
    assert "Security Refusal" in res.error
    assert "sensitive field" in res.error


def test_browser_fill_field_rejects_sensitive_credentials_in_value():
    """Verify browser_fill_field refuses values containing passwords or API keys."""
    browser_manager.approve_domain("wikipedia.org")
    res = browser_fill_field(
        selector="#searchBox",
        value="my password is: SuperSecret999!",
        approved_domain="wikipedia.org",
        field_description="Search box",
    )
    assert res.success is False
    assert "Privacy Refusal" in res.error
    assert "sensitive credentials" in res.error


# --- 3. Forbidden Submission & Purchase Automation Tests ---

def test_check_forbidden_action():
    """Verify automated form submission and checkout actions are strictly blocked."""
    with pytest.raises(BrowserSecurityViolation) as exc:
        check_forbidden_action("submit_form")
    assert "is prohibited" in str(exc.value)

    with pytest.raises(BrowserSecurityViolation):
        check_forbidden_action("purchase")

    with pytest.raises(BrowserSecurityViolation):
        check_forbidden_action("click_button", target_selector="#checkout_buy_now")

    with pytest.raises(BrowserSecurityViolation):
        check_forbidden_action("submit_quiz")


def test_rule_no_submit_or_purchase_tools_in_registry():
    """
    CRITICAL SAFETY AUDIT:
    Confirm that the agent has NO tools capable of clicking submit, buying items,
    completing quizzes, or bypassing CAPTCHAs.
    """
    all_tools = [t.name.lower() for t in tool_registry.get_all_tools()]
    forbidden = [
        "submit_form",
        "click_submit",
        "click_purchase",
        "buy_now",
        "checkout",
        "submit_quiz",
        "finish_test",
        "send_message",
        "bypass_captcha",
        "solve_captcha",
    ]
    for t in all_tools:
        for f in forbidden:
            assert f not in t, f"Forbidden automated submission tool registered: {t}"


# --- 4. Confirmation Gates Tests ---

def test_browser_navigate_confirmation_lifecycle():
    """Verify navigation requires confirmation before execution."""
    browser_manager.approve_domain("wikipedia.org")
    url = "https://en.wikipedia.org/wiki/Artificial_intelligence"

    # 1. First call without token -> prompts confirmation
    res = browser_navigate(url=url, approved_domain="wikipedia.org")
    assert res.success is False
    assert "Confirmation required" in res.error
    conf_id = res.output["confirmation_id"]
    assert conf_id.startswith("conf_")

    # 2. Approve via confirmation manager
    confirmation_manager.confirm_action(conf_id)
    res_confirmed = browser_navigate(url=url, approved_domain="wikipedia.org", confirmation_id=conf_id)
    assert res_confirmed.success is True
    assert res_confirmed.output["status"] == "navigated"


def test_browser_fill_field_confirmation_lifecycle():
    """Verify field filling requires confirmation and requires manual user submission."""
    browser_manager.approve_domain("wikipedia.org")
    selector = "#searchInput"
    value = "FastAPI framework"

    # 1. First call without token -> prompts confirmation
    res = browser_fill_field(
        selector=selector,
        value=value,
        approved_domain="wikipedia.org",
        field_description="Wikipedia Search",
    )
    assert res.success is False
    assert "Confirmation required" in res.error
    conf_id = res.output["confirmation_id"]

    # 2. Complete with confirmed token
    confirmation_manager.confirm_action(conf_id)
    res_confirmed = browser_fill_field(
        selector=selector,
        value=value,
        approved_domain="wikipedia.org",
        field_description="Wikipedia Search",
        confirmation_id=conf_id,
    )
    assert res_confirmed.success is True
    assert res_confirmed.output["status"] == "field_filled"
    assert "Final submission must be completed manually by you" in res_confirmed.output["note"]


# --- 5. Data Privacy & Audit Log Redaction Tests ---

def test_browser_automation_never_logs_form_values_or_page_text():
    """
    CRITICAL PRIVACY TEST:
    Verify that executing browser automation actions NEVER persists
    filled form values, secret search queries, or raw page content into disk logs.
    """
    browser_manager.approve_domain("wikipedia.org")
    secret_value = "SECRET_PROJECT_CODENAME_X77"
    secret_page_text = "TOP_SECRET_INTERNAL_INTEL_CONTENT_8899"

    # Execute read page
    tool_registry.execute_tool(
        "browser_read_page",
        {"approved_domain": "wikipedia.org", "page_text": secret_page_text},
    )

    # Execute fill field (first call creates confirmation)
    res_stage = tool_registry.execute_tool(
        "browser_fill_field",
        {
            "selector": "#searchBox",
            "value": secret_value,
            "approved_domain": "wikipedia.org",
            "field_description": "Search Box",
        },
    )
    conf_id = res_stage.output["confirmation_id"]

    # Confirm and execute
    confirmation_manager.confirm_action(conf_id)
    tool_registry.execute_tool(
        "browser_fill_field",
        {
            "selector": "#searchBox",
            "value": secret_value,
            "approved_domain": "wikipedia.org",
            "field_description": "Search Box",
            "confirmation_id": conf_id,
        },
    )

    log_content = ""
    if settings.ACTION_LOG_FILE.exists():
        log_content = settings.ACTION_LOG_FILE.read_text(encoding="utf-8")

    assert secret_value not in log_content, "Filled form value leaked into action audit log!"
    assert secret_page_text not in log_content, "Raw page content leaked into action audit log!"


# --- 6. API Endpoints Tests ---

def test_browser_approved_domains_endpoints(client):
    """Verify /api/browser/approved-domains and /api/browser/approve-domain."""
    # List domains
    res = client.get("/api/browser/approved-domains")
    assert res.status_code == 200
    data = res.json()
    assert "wikipedia.org" in data["approved_domains"]

    # Approve new domain
    res_add = client.post("/api/browser/approve-domain", json={"domain": "docs.python.org"})
    assert res_add.status_code == 200
    assert "docs.python.org" in res_add.json()["approved_domains"]


def test_browser_plan_action_api(client):
    """Verify /api/browser/plan-action stages actions and enforces safety rules."""
    # 1. Navigate planning on approved domain
    res_nav = client.post(
        "/api/browser/plan-action",
        json={
            "action_type": "navigate",
            "approved_domain": "wikipedia.org",
            "url": "https://en.wikipedia.org/wiki/Python",
        },
    )
    assert res_nav.status_code == 200
    data_nav = res_nav.json()
    assert data_nav["allowed"] is True
    assert data_nav["requires_confirmation"] is True
    assert data_nav["confirmation_id"].startswith("conf_")

    # 2. Navigate escape rejected with 403
    res_escape = client.post(
        "/api/browser/plan-action",
        json={
            "action_type": "navigate",
            "approved_domain": "wikipedia.org",
            "url": "https://attacker.org/steal",
        },
    )
    assert res_escape.status_code == 403

    # 3. Fill field planning on sensitive field rejected
    res_sens = client.post(
        "/api/browser/plan-action",
        json={
            "action_type": "fill_field",
            "approved_domain": "wikipedia.org",
            "selector": "input#password",
            "value": "MyPassword123",
        },
    )
    assert res_sens.status_code == 400
    assert "Security Refusal" in res_sens.json()["detail"]
