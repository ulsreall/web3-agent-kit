"""NFT WL Grinder — auto-apply for NFT whitelist spots.

Automates NFT whitelist applications across platforms:
- Typeform applications
- Google Forms
- Premint.xyz
- Own.ly
- Custom WL forms

Usage::

    from web3_agent_kit.airdrop.wl_grinder import WLGrinder, WLProfile

    profile = WLProfile(
        wallet="0x...",
        twitter="@user",
        discord="user#1234",
        email="user@email.com",
    )
    grinder = WLGrinder(profile)
    results = grinder.apply_bulk(wl_urls)
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class WLProfile:
    """Profile for WL applications."""
    # Wallet
    wallet: str = ""
    wallet_sol: str = ""
    ens: str = ""

    # Social
    twitter: str = ""
    discord: str = ""
    telegram: str = ""
    instagram: str = ""
    tiktok: str = ""

    # Personal
    name: str = ""
    email: str = ""
    country: str = ""

    # Referral
    referrer: str = ""
    referral_code: str = ""

    # Custom answers (for quiz-style WL)
    custom_answers: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if v}

    @classmethod
    def from_json(cls, path: str) -> WLProfile:
        data = json.loads(Path(path).read_text())
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class WLResult:
    """Result of a WL application."""
    url: str
    platform: str = ""
    project_name: str = ""
    success: bool = False
    applied: bool = False
    verified: bool = False
    position: int = 0
    screenshot_path: str = ""
    error: str = ""
    details: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "url": self.url,
            "platform": self.platform,
            "project": self.project_name,
            "success": self.success,
            "applied": self.applied,
            "verified": self.verified,
            "error": self.error,
        }


@dataclass
class WLJob:
    """A batch WL application job."""
    urls: list[str]
    results: list[WLResult] = field(default_factory=list)
    total: int = 0
    success: int = 0
    failed: int = 0
    skipped: int = 0

    @property
    def success_rate(self) -> float:
        if self.total == 0:
            return 0.0
        return self.success / self.total

    def to_dict(self) -> dict:
        return {
            "total": self.total,
            "success": self.success,
            "failed": self.failed,
            "skipped": self.skipped,
            "success_rate": f"{self.success_rate:.0%}",
        }


class WLGrinder:
    """Auto-apply for NFT whitelist spots.

    Detects platform (Typeform, Google Forms, Premint, etc.),
    fills application form, and submits.

    Example::

        profile = WLProfile(
            wallet="0x721e885...",
            twitter="@itseywacc",
            discord="user#1234",
            email="khasbimln@gmail.com",
        )
        grinder = WLGrinder(profile)
        result = grinder.apply("https://typeform.com/to/abc123")
    """

    def __init__(self, profile: WLProfile):
        """Initialize WL grinder.

        Args:
            profile: User profile for applications.
        """
        self.profile = profile
        self._applied_urls: set[str] = set()
        logger.info("WLGrinder initialized")

    def apply(self, url: str) -> WLResult:
        """Apply for a single WL spot.

        Args:
            url: WL application URL.

        Returns:
            WLResult with details.
        """
        result = WLResult(url=url)

        # Detect platform
        platform = self._detect_platform(url)
        result.platform = platform

        try:
            if platform == "typeform":
                result = self._apply_typeform(url, result)
            elif platform == "google_form":
                result = self._apply_google_form(url, result)
            elif platform == "premint":
                result = self._apply_premint(url, result)
            elif platform == "gleam":
                result = self._apply_gleam(url, result)
            else:
                result = self._apply_generic(url, result)

            if result.success:
                self._applied_urls.add(url)
                logger.info(f"✓ Applied: {url}")
            else:
                logger.warning(f"✗ Failed: {url} — {result.error}")

        except Exception as e:
            result.error = str(e)
            logger.error(f"Application failed: {e}")

        return result

    def apply_bulk(
        self,
        urls: list[str],
        delay: float = 10.0,
        skip_existing: bool = True,
    ) -> WLJob:
        """Apply for multiple WL spots.

        Args:
            urls: List of WL URLs.
            delay: Delay between applications (seconds).
            skip_existing: Skip already-applied URLs.

        Returns:
            WLJob with results.
        """
        job = WLJob(urls=urls, total=len(urls))

        for i, url in enumerate(urls):
            # Skip if already applied
            if skip_existing and url in self._applied_urls:
                job.skipped += 1
                job.results.append(WLResult(
                    url=url, success=False, error="Already applied"
                ))
                continue

            logger.info(f"[{i + 1}/{len(urls)}] Applying: {url}")
            result = self.apply(url)
            job.results.append(result)

            if result.success:
                job.success += 1
            else:
                job.failed += 1

            # Delay between applications
            if i < len(urls) - 1:
                time.sleep(delay)

        logger.info(
            f"Bulk apply complete: {job.success}/{job.total} success"
        )
        return job

    def get_applied(self) -> list[str]:
        """Get list of already-applied URLs."""
        return list(self._applied_urls)

    def export_results(self, job: WLJob, path: str) -> None:
        """Export results to JSON.

        Args:
            job: WLJob with results.
            path: File path to save.
        """
        data = {
            "summary": job.to_dict(),
            "results": [r.to_dict() for r in job.results],
        }
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps(data, indent=2))
        logger.info(f"Exported results to {path}")

    # ─── Platform Handlers ────────────────────────────────────────

    def _apply_typeform(self, url: str, result: WLResult) -> WLResult:
        """Apply via Typeform."""
        try:
            from .form_filler import FormFiller, FormProfile

            # Convert WL profile to Form profile
            form_profile = FormProfile(
                name=self.profile.name,
                email=self.profile.email,
                wallet=self.profile.wallet,
                twitter=self.profile.twitter,
                discord=self.profile.discord,
                telegram=self.profile.telegram,
            )
            filler = FormFiller(form_profile)
            fill_result = filler.fill_typeform(url)

            result.success = fill_result.success
            result.applied = fill_result.submitted
            result.details = fill_result.details

        except Exception as e:
            result.error = str(e)

        return result

    def _apply_google_form(self, url: str, result: WLResult) -> WLResult:
        """Apply via Google Forms."""
        try:
            from .form_filler import FormFiller, FormProfile

            form_profile = FormProfile(
                name=self.profile.name,
                email=self.profile.email,
                wallet=self.profile.wallet,
                twitter=self.profile.twitter,
                discord=self.profile.discord,
                telegram=self.profile.telegram,
            )
            filler = FormFiller(form_profile)
            fill_result = filler.fill_google_form(url)

            result.success = fill_result.success
            result.applied = fill_result.submitted
            result.details = fill_result.details

        except Exception as e:
            result.error = str(e)

        return result

    def _apply_premint(self, url: str, result: WLResult) -> WLResult:
        """Apply via Premint.xyz."""
        try:
            from playwright.sync_api import sync_playwright

            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context()
                page = context.new_page()

                page.goto(url, wait_until="networkidle", timeout=30000)
                time.sleep(3)

                # Premint requires wallet connection
                # Look for connect button
                connect_btn = page.query_selector(
                    'button:has-text("Connect"), '
                    'button:has-text("Sign In"), '
                    'button:has-text("Login")'
                )

                if connect_btn:
                    connect_btn.click()
                    time.sleep(2)

                    # Try to connect wallet (usually MetaMask popup)
                    # This requires wallet extension or WalletConnect
                    result.error = "Premint requires wallet connection (manual step)"
                else:
                    # Maybe already connected, look for register/apply button
                    apply_btn = page.query_selector(
                        'button:has-text("Register"), '
                        'button:has-text("Apply"), '
                        'button:has-text("Sign Up")'
                    )
                    if apply_btn:
                        apply_btn.click()
                        time.sleep(3)
                        result.applied = True
                        result.success = True

                browser.close()

        except Exception as e:
            result.error = str(e)

        return result

    def _apply_gleam(self, url: str, result: WLResult) -> WLResult:
        """Apply via Gleam.io widget."""
        try:
            from .executor.browser import BrowserManager, BrowserConfig
            from .executor.gleam_exec import GleamExecutor

            config = BrowserConfig(headless=True)
            with BrowserManager(config) as browser:
                executor = GleamExecutor(browser)
                gleam_result = executor.complete_all(url)

                result.success = gleam_result.success_rate > 0.5
                result.applied = gleam_result.completed_tasks > 0
                result.details = [
                    f"Completed: {gleam_result.completed_tasks}/{gleam_result.total_tasks}"
                ]

        except Exception as e:
            result.error = str(e)

        return result

    def _apply_generic(self, url: str, result: WLResult) -> WLResult:
        """Apply via generic form."""
        try:
            from .form_filler import FormFiller, FormProfile

            form_profile = FormProfile(
                name=self.profile.name,
                email=self.profile.email,
                wallet=self.profile.wallet,
                twitter=self.profile.twitter,
                discord=self.profile.discord,
                telegram=self.profile.telegram,
            )
            filler = FormFiller(form_profile)
            fill_result = filler.fill(url)

            result.success = fill_result.success
            result.applied = fill_result.submitted
            result.details = fill_result.details

        except Exception as e:
            result.error = str(e)

        return result

    # ─── Helpers ──────────────────────────────────────────────────

    def _detect_platform(self, url: str) -> str:
        """Detect platform from URL."""
        url_lower = url.lower()
        if "typeform.com" in url_lower:
            return "typeform"
        elif "forms.gle" in url_lower or "docs.google.com/forms" in url_lower:
            return "google_form"
        elif "premint.xyz" in url_lower:
            return "premint"
        elif "gleam.io" in url_lower:
            return "gleam"
        elif "own.ly" in url_lower:
            return "ownly"
        elif "raffall.com" in url_lower:
            return "raffall"
        else:
            return "generic"
