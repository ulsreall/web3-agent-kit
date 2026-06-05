"""Form Filler — auto-fill web forms for airdrop applications.

Handles Typeform, Google Forms, custom forms, and generic HTML forms.
Auto-fills name, email, wallet, social handles, and custom fields.

Usage::

    from web3_agent_kit.airdrop.form_filler import FormFiller, FormProfile

    profile = FormProfile(
        name="John Doe",
        email="john@example.com",
        wallet="0x...",
        twitter="@johndoe",
    )
    filler = FormFiller(profile)
    result = filler.fill_typeform("https://typeform.com/to/abc123")
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class FormProfile:
    """User profile for form auto-fill."""
    # Personal
    name: str = ""
    first_name: str = ""
    last_name: str = ""
    email: str = ""
    phone: str = ""
    country: str = ""
    city: str = ""

    # Crypto
    wallet: str = ""
    wallet_evm: str = ""
    wallet_sol: str = ""
    ens: str = ""

    # Social
    twitter: str = ""
    discord: str = ""
    telegram: str = ""
    github: str = ""
    youtube: str = ""
    instagram: str = ""
    tiktok: str = ""

    # Custom fields
    custom: dict = field(default_factory=dict)

    def get(self, field_name: str) -> str:
        """Get field value by name (supports aliases)."""
        aliases = {
            "fullname": self.name,
            "full_name": self.name,
            "fname": self.first_name,
            "lname": self.last_name,
            "e-mail": self.email,
            "mail": self.email,
            "eth": self.wallet_evm or self.wallet,
            "ethereum": self.wallet_evm or self.wallet,
            "evm": self.wallet_evm or self.wallet,
            "sol": self.wallet_sol,
            "solana": self.wallet_sol,
            "x": self.twitter,
            "twitter_handle": self.twitter,
            "tg": self.telegram,
            "discord_handle": self.discord,
            "gh": self.github,
        }
        # Direct lookup
        value = getattr(self, field_name, None)
        if value:
            return str(value)
        # Alias lookup
        value = aliases.get(field_name.lower())
        if value:
            return str(value)
        # Custom field
        return self.custom.get(field_name, "")

    def to_dict(self) -> dict:
        """Serialize to dict."""
        return {k: v for k, v in self.__dict__.items() if v}

    @classmethod
    def from_json(cls, path: str) -> FormProfile:
        """Load profile from JSON file."""
        data = json.loads(Path(path).read_text())
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class FormField:
    """A detected form field."""
    name: str
    label: str
    field_type: str  # text, email, url, select, textarea, checkbox, radio
    selector: str
    required: bool = False
    placeholder: str = ""
    options: list[str] = field(default_factory=list)
    value: str = ""

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "label": self.label,
            "type": self.field_type,
            "selector": self.selector,
            "required": self.required,
        }


@dataclass
class FillResult:
    """Result of form filling."""
    url: str
    platform: str = ""
    success: bool = False
    fields_found: int = 0
    fields_filled: int = 0
    fields_skipped: int = 0
    submitted: bool = False
    screenshot_path: str = ""
    error: str = ""
    details: list[str] = field(default_factory=list)

    @property
    def fill_rate(self) -> float:
        if self.fields_found == 0:
            return 0.0
        return self.fields_filled / self.fields_found

    def to_dict(self) -> dict:
        return {
            "url": self.url,
            "platform": self.platform,
            "success": self.success,
            "fields_found": self.fields_found,
            "fields_filled": self.fields_filled,
            "fill_rate": f"{self.fill_rate:.0%}",
            "submitted": self.submitted,
            "error": self.error,
        }


# Field detection patterns
FIELD_PATTERNS: dict[str, list[str]] = {
    "email": [
        r"email", r"e-mail", r"mail", r"correo", r"メール",
    ],
    "name": [
        r"name", r"full.?name", r"your.?name", r"nombre", r"nom",
    ],
    "first_name": [
        r"first.?name", r"given.?name", r"fname",
    ],
    "last_name": [
        r"last.?name", r"family.?name", r"lname", r"surname",
    ],
    "wallet": [
        r"wallet", r"address", r"eth.?address", r"evm", r"0x",
        r"metamask", r"crypto.?address",
    ],
    "wallet_sol": [
        r"solana", r"sol.?address", r"phantom",
    ],
    "twitter": [
        r"twitter", r"x\.com", r"@", r"handle",
    ],
    "discord": [
        r"discord", r"discord.?tag", r"discord.?user",
    ],
    "telegram": [
        r"telegram", r"tg", r"@.*bot",
    ],
    "github": [
        r"github", r"gh",
    ],
    "phone": [
        r"phone", r"mobile", r"tel", r"number",
    ],
    "country": [
        r"country", r"nation", r"region",
    ],
    "referral": [
        r"referral", r"ref.?code", r"invited.?by", r"refer",
    ],
}


class FormFiller:
    """Auto-fill web forms using browser automation.

    Detects form fields, matches to profile, fills and submits.

    Example::

        profile = FormProfile(
            name="John Doe",
            email="john@example.com",
            wallet="0x123...",
            twitter="@johndoe",
        )
        filler = FormFiller(profile)
        result = filler.fill("https://example.com/form")
    """

    def __init__(self, profile: FormProfile):
        """Initialize form filler.

        Args:
            profile: User profile for auto-fill.
        """
        self.profile = profile
        self._page = None
        self._browser = None
        logger.info("FormFiller initialized")

    def fill(
        self,
        url: str,
        submit: bool = True,
        screenshot: bool = True,
    ) -> FillResult:
        """Fill a generic web form.

        Args:
            url: Form URL.
            submit: Whether to submit after filling.
            screenshot: Whether to take screenshot after filling.

        Returns:
            FillResult with details.
        """
        result = FillResult(url=url, platform="generic")

        try:
            from playwright.sync_api import sync_playwright

            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
                    )
                )
                page = context.new_page()

                # Navigate to form
                page.goto(url, wait_until="networkidle", timeout=30000)
                time.sleep(2)

                # Detect fields
                fields = self._detect_fields(page)
                result.fields_found = len(fields)

                if not fields:
                    result.error = "No form fields detected"
                    return result

                # Fill each field
                for field in fields:
                    value = self._match_field(field)
                    if value:
                        success = self._fill_field(page, field, value)
                        if success:
                            result.fields_filled += 1
                            result.details.append(f"✓ {field.label}: {value[:20]}...")
                        else:
                            result.fields_skipped += 1
                            result.details.append(f"✗ {field.label}: fill failed")
                    else:
                        result.fields_skipped += 1
                        result.details.append(f"- {field.label}: no match")

                # Screenshot before submit
                if screenshot:
                    path = f"/tmp/form_filled_{int(time.time())}.png"
                    page.screenshot(path=path)
                    result.screenshot_path = path

                # Submit
                if submit:
                    submitted = self._submit_form(page)
                    result.submitted = submitted
                    if submitted:
                        time.sleep(3)
                        result.success = True

                browser.close()

        except ImportError:
            result.error = "Playwright not installed. Run: pip install playwright"
        except Exception as e:
            result.error = str(e)

        return result

    def fill_typeform(
        self,
        url: str,
        submit: bool = True,
    ) -> FillResult:
        """Fill a Typeform.

        Args:
            url: Typeform URL.
            submit: Whether to submit after filling.

        Returns:
            FillResult with details.
        """
        result = FillResult(url=url, platform="typeform")

        try:
            from playwright.sync_api import sync_playwright

            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
                    )
                )
                page = context.new_page()
                page.goto(url, wait_until="networkidle", timeout=30000)
                time.sleep(3)

                # Typeform uses a wizard-style form
                # Each question is on a separate screen
                steps = 0
                max_steps = 20

                while steps < max_steps:
                    steps += 1

                    # Detect current question
                    question = self._detect_typeform_question(page)
                    if not question:
                        break

                    # Match and fill
                    value = self._match_typeform_field(question)
                    if value:
                        self._fill_typeform_field(page, value)
                        result.fields_filled += 1
                        result.details.append(f"✓ Step {steps}: {value[:20]}...")
                    else:
                        result.fields_skipped += 1
                        result.details.append(f"- Step {steps}: no match")

                    result.fields_found += 1

                    # Click next
                    self._typeform_next(page)
                    time.sleep(1)

                # Submit if on final screen
                if submit:
                    submitted = self._typeform_submit(page)
                    result.submitted = submitted
                    result.success = submitted

                browser.close()

        except ImportError:
            result.error = "Playwright not installed"
        except Exception as e:
            result.error = str(e)

        return result

    def fill_google_form(
        self,
        url: str,
        submit: bool = True,
    ) -> FillResult:
        """Fill a Google Form.

        Args:
            url: Google Form URL.
            submit: Whether to submit after filling.

        Returns:
            FillResult with details.
        """
        result = FillResult(url=url, platform="google_form")

        try:
            from playwright.sync_api import sync_playwright

            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
                    )
                )
                page = context.new_page()
                page.goto(url, wait_until="networkidle", timeout=30000)
                time.sleep(3)

                # Google Forms uses a specific structure
                # Each question is a div with role="listitem"
                questions = page.query_selector_all('div[role="listitem"]')
                result.fields_found = len(questions)

                for q in questions:
                    # Get question text
                    label_el = q.query_selector('div[role="heading"]')
                    label = label_el.inner_text() if label_el else ""

                    # Detect field type
                    input_el = q.query_selector('input[type="text"], input[type="email"], textarea')
                    select_el = q.query_selector('div[role="listbox"]')

                    if input_el:
                        # Text/email input
                        field_name = self._detect_field_name(label)
                        value = self.profile.get(field_name)
                        if value:
                            input_el.fill(value)
                            result.fields_filled += 1
                            result.details.append(f"✓ {label}: {value[:20]}...")
                        else:
                            result.fields_skipped += 1

                    elif select_el:
                        # Dropdown
                        field_name = self._detect_field_name(label)
                        value = self.profile.get(field_name)
                        if value:
                            self._fill_google_dropdown(page, select_el, value)
                            result.fields_filled += 1
                        else:
                            result.fields_skipped += 1

                # Submit
                if submit:
                    submit_btn = page.query_selector('div[role="button"]:has-text("Submit")')
                    if submit_btn:
                        submit_btn.click()
                        time.sleep(3)
                        result.submitted = True
                        result.success = True

                browser.close()

        except ImportError:
            result.error = "Playwright not installed"
        except Exception as e:
            result.error = str(e)

        return result

    # ─── Private Methods ─────────────────────────────────────────

    def _detect_fields(self, page) -> list[FormField]:
        """Detect form fields on a page."""
        fields = []

        # Find all input elements
        inputs = page.query_selector_all(
            'input[type="text"], input[type="email"], input[type="url"], '
            'input[type="tel"], input[type="number"], textarea, select'
        )

        for inp in inputs:
            try:
                # Get field info
                name = inp.get_attribute("name") or ""
                id_attr = inp.get_attribute("id") or ""
                placeholder = inp.get_attribute("placeholder") or ""
                field_type = inp.get_attribute("type") or "text"
                required = inp.get_attribute("required") is not None

                # Try to find label
                label = ""
                if id_attr:
                    label_el = page.query_selector(f'label[for="{id_attr}"]')
                    if label_el:
                        label = label_el.inner_text()

                if not label:
                    label = placeholder or name or id_attr

                # Build selector
                selector = ""
                if id_attr:
                    selector = f"#{id_attr}"
                elif name:
                    selector = f'[name="{name}"]'
                else:
                    selector = f'input[placeholder="{placeholder}"]'

                fields.append(FormField(
                    name=name or id_attr,
                    label=label,
                    field_type=field_type,
                    selector=selector,
                    required=required,
                    placeholder=placeholder,
                ))
            except Exception:
                continue

        return fields

    def _match_field(self, field: FormField) -> str:
        """Match a form field to profile value."""
        label_lower = field.label.lower()
        name_lower = field.name.lower()
        placeholder_lower = field.placeholder.lower()
        combined = f"{label_lower} {name_lower} {placeholder_lower}"

        for field_name, patterns in FIELD_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, combined, re.IGNORECASE):
                    value = self.profile.get(field_name)
                    if value:
                        return value

        return ""

    def _fill_field(self, page, field: FormField, value: str) -> bool:
        """Fill a form field."""
        try:
            element = page.query_selector(field.selector)
            if not element:
                return False

            if field.field_type == "select":
                # Select dropdown
                element.select_option(label=value)
            else:
                # Text input
                element.click()
                element.fill(value)

            time.sleep(0.5)
            return True
        except Exception as e:
            logger.debug(f"Fill failed for {field.name}: {e}")
            return False

    def _submit_form(self, page) -> bool:
        """Submit a form."""
        try:
            # Try common submit selectors
            selectors = [
                'button[type="submit"]',
                'input[type="submit"]',
                'button:has-text("Submit")',
                'button:has-text("Apply")',
                'button:has-text("Send")',
                'button:has-text("Next")',
                'button:has-text("Continue")',
                '.submit-btn',
                '#submit',
            ]

            for selector in selectors:
                btn = page.query_selector(selector)
                if btn and btn.is_visible():
                    btn.click()
                    time.sleep(2)
                    return True

            return False
        except Exception as e:
            logger.error(f"Submit failed: {e}")
            return False

    def _detect_field_name(self, label: str) -> str:
        """Detect field name from label text."""
        label_lower = label.lower()
        for field_name, patterns in FIELD_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, label_lower, re.IGNORECASE):
                    return field_name
        return ""

    def _detect_typeform_question(self, page) -> Optional[str]:
        """Detect current Typeform question."""
        try:
            # Typeform question selector
            question_el = page.query_selector('[data-qa="title"]')
            if question_el:
                return question_el.inner_text()
            # Fallback
            heading = page.query_selector('h1, h2, [class*="title"]')
            if heading:
                return heading.inner_text()
        except Exception:
            pass
        return None

    def _match_typeform_field(self, question: str) -> str:
        """Match Typeform question to profile value."""
        return self._match_field(FormField(
            name="", label=question, field_type="text", selector=""
        ))

    def _fill_typeform_field(self, page, value: str) -> bool:
        """Fill Typeform input field."""
        try:
            # Typeform input selectors
            input_el = page.query_selector(
                'input[data-qa="input"], textarea[data-qa="input"], '
                'input[type="text"], input[type="email"]'
            )
            if input_el:
                input_el.fill(value)
                time.sleep(0.5)
                return True
        except Exception:
            pass
        return False

    def _typeform_next(self, page) -> bool:
        """Click next button in Typeform."""
        try:
            btn = page.query_selector(
                'button[data-qa="next-button"], '
                'button:has-text("Next"), '
                'button:has-text("OK")'
            )
            if btn:
                btn.click()
                time.sleep(1)
                return True
        except Exception:
            pass
        return False

    def _typeform_submit(self, page) -> bool:
        """Submit Typeform."""
        try:
            btn = page.query_selector(
                'button[data-qa="submit-button"], '
                'button:has-text("Submit"), '
                'button:has-text("Done")'
            )
            if btn:
                btn.click()
                time.sleep(3)
                return True
        except Exception:
            pass
        return False

    def _fill_google_dropdown(self, page, select_el, value: str) -> bool:
        """Fill Google Forms dropdown."""
        try:
            select_el.click()
            time.sleep(0.5)
            # Find matching option
            options = page.query_selector_all('div[role="option"]')
            for opt in options:
                text = opt.inner_text().strip()
                if value.lower() in text.lower() or text.lower() in value.lower():
                    opt.click()
                    return True
        except Exception:
            pass
        return False
