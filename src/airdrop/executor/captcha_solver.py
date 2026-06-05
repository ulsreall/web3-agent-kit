"""Universal CAPTCHA solving integration.

Supports multiple CAPTCHA solving providers (anticaptcha.com, 2captcha.com)
for solving reCAPTCHA v2/v3, hCaptcha, GeeTest, and Cloudflare Turnstile.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional

import requests

logger = logging.getLogger(__name__)


class CaptchaProvider(Enum):
    """Supported CAPTCHA solving providers."""
    ANTICAPTCHA = "anticaptcha"
    TWOCAPTCHA = "2captcha"


@dataclass
class CaptchaConfig:
    """Configuration for CAPTCHA solver."""
    provider: CaptchaProvider = CaptchaProvider.ANTICAPTCHA
    api_key: Optional[str] = None
    timeout: int = 120
    max_retries: int = 3
    retry_delay: float = 5.0
    poll_interval: float = 5.0


class CaptchaSolver:
    """Universal CAPTCHA solver supporting multiple providers.

    Supports: reCAPTCHA v2/v3, hCaptcha, GeeTest, Cloudflare Turnstile.

    Example::

        solver = CaptchaSolver(CaptchaConfig(
            provider=CaptchaProvider.ANTICAPTCHA,
            api_key="your-api-key",
        ))

        # Solve reCAPTCHA v2
        token = solver.solve_recaptcha_v2(
            site_key="6Le-wvkSAAAAAPBMRTvw0Q4Muexq9bi0DJwx_mJ-",
            url="https://example.com",
        )

        # Solve GeeTest (for Galxe)
        solution = solver.solve_geetest(
            gt="abc123",
            challenge="def456",
            api_server="api.geetest.com",
        )
    """

    # Provider API endpoints
    ANTICAPTCHA_API = "https://api.anti-captcha.com"
    TWOCAPTCHA_API = "http://2captcha.com"

    def __init__(self, config: Optional[CaptchaConfig] = None):
        """Initialize the CAPTCHA solver.

        Args:
            config: Optional CAPTCHA configuration.
        """
        self.config = config or CaptchaConfig()
        self.session = requests.Session()

        # Try to get API key from environment if not provided
        if not self.config.api_key:
            if self.config.provider == CaptchaProvider.ANTICAPTCHA:
                self.config.api_key = os.environ.get("ANTICAPTCHA_API_KEY")
            elif self.config.provider == CaptchaProvider.TWOCAPTCHA:
                self.config.api_key = os.environ.get("TWOCAPTCHA_API_KEY")

        if not self.config.api_key:
            logger.warning(
                f"No API key configured for {self.config.provider.value}. "
                "Set via config or environment variable."
            )

    def solve_recaptcha_v2(
        self,
        site_key: str,
        url: str,
        invisible: bool = False,
    ) -> str:
        """Solve reCAPTCHA v2.

        Args:
            site_key: The reCAPTCHA site key.
            url: The page URL where CAPTCHA appears.
            invisible: Whether it's an invisible reCAPTCHA.

        Returns:
            The solved CAPTCHA token.

        Raises:
            CaptchaSolvingError: If solving fails.
        """
        logger.info(f"Solving reCAPTCHA v2 for {url}")

        if self.config.provider == CaptchaProvider.ANTICAPTCHA:
            task_type = "RecaptchaV2TaskProxyless"
            task_data = {
                "websiteURL": url,
                "websiteKey": site_key,
            }
            if invisible:
                task_data["isInvisible"] = "true"
        else:
            # 2captcha
            return self._solve_2captcha(
                method="userrecaptcha",
                site_key=site_key,
                url=url,
                invisible=invisible,
            )

        return self._solve_anticaptcha(task_type, task_data)

    def solve_recaptcha_v3(
        self,
        site_key: str,
        url: str,
        action: str = "verify",
        min_score: float = 0.7,
    ) -> str:
        """Solve reCAPTCHA v3.

        Args:
            site_key: The reCAPTCHA site key.
            url: The page URL.
            action: The reCAPTCHA action name.
            min_score: Minimum score threshold.

        Returns:
            The solved CAPTCHA token.

        Raises:
            CaptchaSolvingError: If solving fails.
        """
        logger.info(f"Solving reCAPTCHA v3 for {url} (action={action})")

        if self.config.provider == CaptchaProvider.ANTICAPTCHA:
            task_data = {
                "websiteURL": url,
                "websiteKey": site_key,
                "pageAction": action,
                "minScore": min_score,
            }
            return self._solve_anticaptcha("RecaptchaV3TaskProxyless", task_data)
        else:
            return self._solve_2captcha(
                method="userrecaptcha",
                site_key=site_key,
                url=url,
                version="v3",
                action=action,
                min_score=min_score,
            )

    def solve_hcaptcha(
        self,
        site_key: str,
        url: str,
    ) -> str:
        """Solve hCaptcha.

        Args:
            site_key: The hCaptcha site key.
            url: The page URL.

        Returns:
            The solved CAPTCHA token.

        Raises:
            CaptchaSolvingError: If solving fails.
        """
        logger.info(f"Solving hCaptcha for {url}")

        if self.config.provider == CaptchaProvider.ANTICAPTCHA:
            task_data = {
                "websiteURL": url,
                "websiteKey": site_key,
            }
            return self._solve_anticaptcha("HCaptchaTaskProxyless", task_data)
        else:
            return self._solve_2captcha(
                method="hcaptcha",
                site_key=site_key,
                url=url,
            )

    def solve_geetest(
        self,
        gt: str,
        challenge: str,
        api_server: str,
        url: Optional[str] = None,
    ) -> dict:
        """Solve GeeTest CAPTCHA.

        Args:
            gt: The GeeTest gt parameter.
            challenge: The GeeTest challenge parameter.
            api_server: The GeeTest API server URL.
            url: Optional page URL.

        Returns:
            Dict with solution: challenge, validate, seccode.

        Raises:
            CaptchaSolvingError: If solving fails.
        """
        logger.info(f"Solving GeeTest (gt={gt[:10]}...)")

        if self.config.provider == CaptchaProvider.ANTICAPTCHA:
            task_data = {
                "websiteURL": url or "https://example.com",
                "gt": gt,
                "challenge": challenge,
                "geetestApiServerSubdomain": api_server,
            }
            result = self._solve_anticaptcha("GeeTestTaskProxyless", task_data)
            if isinstance(result, dict):
                return result
            return {"challenge": challenge, "validate": result, "seccode": ""}
        else:
            # 2captcha GeeTest
            result = self._solve_2captcha_geetest(gt, challenge, api_server, url)
            return result

    def solve_turnstile(
        self,
        site_key: str,
        url: str,
    ) -> str:
        """Solve Cloudflare Turnstile.

        Args:
            site_key: The Turnstile site key.
            url: The page URL.

        Returns:
            The solved CAPTCHA token.

        Raises:
            CaptchaSolvingError: If solving fails.
        """
        logger.info(f"Solving Turnstile for {url}")

        if self.config.provider == CaptchaProvider.ANTICAPTCHA:
            task_data = {
                "websiteURL": url,
                "websiteKey": site_key,
                "domain": "challenges.cloudflare.com",
            }
            return self._solve_anticaptcha("TurnstileTaskProxyless", task_data)
        else:
            return self._solve_2captcha(
                method="turnstile",
                site_key=site_key,
                url=url,
            )

    def get_balance(self) -> float:
        """Check the CAPTCHA provider account balance.

        Returns:
            Account balance in USD.

        Raises:
            CaptchaSolvingError: If balance check fails.
        """
        if self.config.provider == CaptchaProvider.ANTICAPTCHA:
            return self._get_anticaptcha_balance()
        else:
            return self._get_2captcha_balance()

    # ─── Anticaptcha API ─────────────────────────────────────────

    def _solve_anticaptcha(self, task_type: str, task_data: dict) -> Any:
        """Solve a CAPTCHA using anticaptcha.com API.

        Args:
            task_type: The anticaptcha task type.
            task_data: Task-specific data.

        Returns:
            The solved token or solution dict.

        Raises:
            CaptchaSolvingError: If solving fails.
        """
        if not self.config.api_key:
            raise CaptchaSolvingError("No anticaptcha API key configured")

        # Create task
        create_payload = {
            "clientKey": self.config.api_key,
            "task": {
                "type": task_type,
                **task_data,
            },
        }

        try:
            response = self.session.post(
                f"{self.ANTICAPTCHA_API}/createTask",
                json=create_payload,
                timeout=self.config.timeout,
            )
            response.raise_for_status()
            result = response.json()

            if result.get("errorId", 0) != 0:
                raise CaptchaSolvingError(
                    f"Anticaptcha error: {result.get('errorDescription', 'Unknown')}"
                )

            task_id = result.get("taskId")
            if not task_id:
                raise CaptchaSolvingError("No taskId returned")

            logger.info(f"Anticaptcha task created: {task_id}")

        except requests.RequestException as e:
            raise CaptchaSolvingError(f"Failed to create anticaptcha task: {e}")

        # Poll for result
        return self._poll_anticaptcha(task_id)

    def _poll_anticaptcha(self, task_id: int) -> Any:
        """Poll anticaptcha for task result.

        Args:
            task_id: The task ID to poll.

        Returns:
            The solved token or solution.

        Raises:
            CaptchaSolvingError: If timeout or error.
        """
        start_time = time.time()

        while time.time() - start_time < self.config.timeout:
            time.sleep(self.config.poll_interval)

            try:
                response = self.session.post(
                    f"{self.ANTICAPTCHA_API}/getTaskResult",
                    json={
                        "clientKey": self.config.api_key,
                        "taskId": task_id,
                    },
                    timeout=30,
                )
                response.raise_for_status()
                result = response.json()

                if result.get("errorId", 0) != 0:
                    raise CaptchaSolvingError(
                        f"Anticaptcha error: {result.get('errorDescription')}"
                    )

                status = result.get("status")
                if status == "ready":
                    solution = result.get("solution", {})
                    # For GeeTest, return the full solution dict
                    if isinstance(solution, dict) and "challenge" in solution:
                        logger.info("GeeTest solved successfully")
                        return solution
                    # For reCAPTCHA/hCaptcha, return the token
                    token = solution.get("gRecaptchaResponse") or solution.get("token") or solution.get("text", "")
                    logger.info(f"CAPTCHA solved: {token[:30]}...")
                    return token

                # Still processing
                logger.debug(f"Anticaptcha task {task_id} status: {status}")

            except requests.RequestException as e:
                logger.warning(f"Anticaptcha poll error: {e}")

        raise CaptchaSolvingError(f"Anticaptcha timeout after {self.config.timeout}s")

    def _get_anticaptcha_balance(self) -> float:
        """Get anticaptcha account balance."""
        if not self.config.api_key:
            raise CaptchaSolvingError("No anticaptcha API key configured")

        try:
            response = self.session.post(
                f"{self.ANTICAPTCHA_API}/getBalance",
                json={"clientKey": self.config.api_key},
                timeout=30,
            )
            response.raise_for_status()
            result = response.json()

            if result.get("errorId", 0) != 0:
                raise CaptchaSolvingError(
                    f"Anticaptcha error: {result.get('errorDescription')}"
                )

            return float(result.get("balance", 0))

        except requests.RequestException as e:
            raise CaptchaSolvingError(f"Failed to get balance: {e}")

    # ─── 2Captcha API ────────────────────────────────────────────

    def _solve_2captcha(
        self,
        method: str,
        site_key: str,
        url: str,
        invisible: bool = False,
        version: str = "v2",
        action: str = "",
        min_score: float = 0.7,
    ) -> str:
        """Solve a CAPTCHA using 2captcha.com API.

        Args:
            method: CAPTCHA method (userrecaptcha, hcaptcha, turnstile).
            site_key: The site key.
            url: The page URL.
            invisible: Whether CAPTCHA is invisible.
            version: reCAPTCHA version.
            action: reCAPTCHA v3 action.
            min_score: reCAPTCHA v3 min score.

        Returns:
            The solved token.

        Raises:
            CaptchaSolvingError: If solving fails.
        """
        if not self.config.api_key:
            raise CaptchaSolvingError("No 2captcha API key configured")

        # Submit task
        params = {
            "key": self.config.api_key,
            "method": method,
            "googlekey": site_key,
            "pageurl": url,
            "json": 1,
        }

        if method == "userrecaptcha":
            if invisible:
                params["invisible"] = 1
            if version == "v3":
                params["version"] = "v3"
                params["action"] = action
                params["min_score"] = min_score

        try:
            response = self.session.post(
                f"{self.TWOCAPTCHA_API}/in.php",
                data=params,
                timeout=30,
            )
            response.raise_for_status()
            result = response.json()

            if result.get("status") != 1:
                raise CaptchaSolvingError(
                    f"2captcha error: {result.get('request', 'Unknown')}"
                )

            task_id = result.get("request")
            logger.info(f"2captcha task created: {task_id}")

        except requests.RequestException as e:
            raise CaptchaSolvingError(f"Failed to submit to 2captcha: {e}")

        # Poll for result
        return self._poll_2captcha(str(task_id))

    def _solve_2captcha_geetest(
        self,
        gt: str,
        challenge: str,
        api_server: str,
        url: Optional[str] = None,
    ) -> dict:
        """Solve GeeTest using 2captcha."""
        if not self.config.api_key:
            raise CaptchaSolvingError("No 2captcha API key configured")

        params = {
            "key": self.config.api_key,
            "method": "geetest",
            "gt": gt,
            "challenge": challenge,
            "api_server": api_server,
            "pageurl": url or "https://example.com",
            "json": 1,
        }

        try:
            response = self.session.post(
                f"{self.TWOCAPTCHA_API}/in.php",
                data=params,
                timeout=30,
            )
            response.raise_for_status()
            result = response.json()

            if result.get("status") != 1:
                raise CaptchaSolvingError(
                    f"2captcha GeeTest error: {result.get('request')}"
                )

            task_id = result.get("request")
            logger.info(f"2captcha GeeTest task created: {task_id}")

        except requests.RequestException as e:
            raise CaptchaSolvingError(f"Failed to submit GeeTest to 2captcha: {e}")

        # Poll and parse
        raw = self._poll_2captcha(str(task_id))

        # Parse GeeTest response
        if isinstance(raw, str):
            import json as json_mod
            try:
                parts = json_mod.loads(raw)
                return {
                    "challenge": parts.get("challenge", challenge),
                    "validate": parts.get("validate", ""),
                    "seccode": parts.get("seccode", ""),
                }
            except (ValueError, AttributeError):
                return {"challenge": challenge, "validate": raw, "seccode": ""}

        return raw if isinstance(raw, dict) else {"challenge": challenge, "validate": raw, "seccode": ""}

    def _poll_2captcha(self, task_id: str) -> str:
        """Poll 2captcha for task result.

        Args:
            task_id: The task ID to poll.

        Returns:
            The solved token.

        Raises:
            CaptchaSolvingError: If timeout or error.
        """
        start_time = time.time()

        # Wait before first poll (2captcha needs time)
        time.sleep(10)

        while time.time() - start_time < self.config.timeout:
            try:
                response = self.session.get(
                    f"{self.TWOCAPTCHA_API}/res.php",
                    params={
                        "key": self.config.api_key,
                        "action": "get",
                        "id": task_id,
                        "json": 1,
                    },
                    timeout=30,
                )
                response.raise_for_status()
                result = response.json()

                if result.get("status") == 1:
                    token = result.get("request", "")
                    logger.info(f"2captcha solved: {token[:30]}...")
                    return str(token)

                if result.get("request") == "CAPCHA_NOT_READY":
                    logger.debug("2captcha: not ready yet")
                    time.sleep(self.config.poll_interval)
                    continue

                raise CaptchaSolvingError(
                    f"2captcha error: {result.get('request', 'Unknown')}"
                )

            except requests.RequestException as e:
                logger.warning(f"2captcha poll error: {e}")
                time.sleep(self.config.poll_interval)

        raise CaptchaSolvingError(f"2captcha timeout after {self.config.timeout}s")

    def _get_2captcha_balance(self) -> float:
        """Get 2captcha account balance."""
        if not self.config.api_key:
            raise CaptchaSolvingError("No 2captcha API key configured")

        try:
            response = self.session.get(
                f"{self.TWOCAPTCHA_API}/res.php",
                params={
                    "key": self.config.api_key,
                    "action": "getbalance",
                    "json": 1,
                },
                timeout=30,
            )
            response.raise_for_status()
            result = response.json()

            if result.get("status") != 1:
                raise CaptchaSolvingError(
                    f"2captcha error: {result.get('request')}"
                )

            return float(result.get("request", 0))

        except requests.RequestException as e:
            raise CaptchaSolvingError(f"Failed to get 2captcha balance: {e}")


class CaptchaSolvingError(Exception):
    """Exception raised when CAPTCHA solving fails."""
    pass
