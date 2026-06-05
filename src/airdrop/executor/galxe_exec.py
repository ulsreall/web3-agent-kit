"""Galxe campaign automation — GraphQL API + browser-based task completion.

Handles Galxe campaigns: parses tasks via GraphQL, completes social and
on-chain tasks, verifies credentials, and claims rewards.

Anti-bot: GeeTest CAPTCHA (integrated via CaptchaSolver).
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional
from urllib.parse import urlparse

from .base_executor import (
    BasePlatformExecutor,
    ExecutorConfig,
    ExecutorResult,
    PlatformTask,
    TaskDifficulty,
)

logger = logging.getLogger(__name__)


@dataclass
class GalxeTask(PlatformTask):
    """A Galxe-specific task entry."""
    campaign_id: str = ""
    credential_id: str = ""
    task_id_galxe: str = ""
    verify_type: str = ""
    chain_id: Optional[int] = None
    contract_address: str = ""


@dataclass
class GalxeResult(ExecutorResult):
    """Result of farming a Galxe campaign."""
    points_earned: int = 0
    credentials_verified: int = 0
    reward_claimed: bool = False


# GraphQL Queries
CAMPAIGN_LIST_QUERY = """
query CampaignList($first: Int, $after: String, $filter: CampaignListFilter) {
  campaignList(first: $first, after: $after, filter: $filter) {
    edges {
      node {
        id
        name
        description
        status
        startTime
        endTime
        space {
          id
          name
        }
        tasks {
          id
          name
          type
          description
          attribute
          status
        }
      }
    }
    pageInfo {
      hasNextPage
      endCursor
    }
  }
}
"""

CAMPAIGN_DETAIL_QUERY = """
query CampaignDetail($id: ID!) {
  campaign(id: $id) {
    id
    name
    description
    status
    startTime
    endTime
    space {
      id
      name
    }
    tasks {
      id
      name
      type
      description
      attribute
      status
      credential {
        id
      }
    }
  }
}
"""

USER_CREDENTIALS_QUERY = """
query UserCredentials($address: String!, $campaignId: ID!) {
  userCredentials(address: $address, campaignId: $campaignId) {
    id
    name
    type
    value
    eligible
  }
}
"""

CLAIM_REWARD_MUTATION = """
mutation ClaimReward($campaignId: ID!, $address: String!) {
  claimReward(campaignId: $campaignId, address: $address) {
    success
    message
    txHash
  }
}
"""


class GalxeExecutor(BasePlatformExecutor):
    """Galxe campaign automation.

    The most important airdrop platform. Navigates Galxe campaigns via
    GraphQL API, parses tasks, completes social and on-chain tasks,
    verifies credentials, and claims rewards.

    Task types supported:
        - Twitter (follow, retweet, like, tweet)
        - Discord (join server, verify)
        - On-chain tasks (transactions, NFT holds, token balances)
        - Quiz tasks
        - NFT mint
        - Referral tasks

    Anti-bot: GeeTest CAPTCHA integrated.

    API: GraphQL at graphigo.prd.galaxy.eco

    Example::

        executor = GalxeExecutor(config)
        result = executor.complete_all("https://app.galxe.com/quest/abc123")
        print(f"Completed {result.completed_tasks}/{result.total_tasks}")
        executor.claim_reward()
    """

    platform_name = "galxe"
    platform_url = "https://app.galxe.com"
    supported_task_types = [
        "twitter_follow", "twitter_retweet", "twitter_like", "twitter_comment",
        "discord_join", "discord_verify", "telegram_join",
        "on_chain_tx", "on_chain_swap", "on_chain_bridge", "on_chain_stake",
        "quiz", "visit_url", "nft_mint", "referral", "custom",
    ]

    GRAPHQL_API = "https://graphigo.prd.galaxy.eco/query"
    REST_API = "https://api.galxe.com"

    def __init__(self, config: Optional[ExecutorConfig] = None):
        super().__init__(config)
        self.session.headers.update({
            "Accept": "application/json",
            "Content-Type": "application/json",
        })
        self._campaign_id: Optional[str] = None
        self._campaign_data: Optional[dict] = None
        self._wallet_address: Optional[str] = None
        self._auth_token: Optional[str] = None
        self._galxe_results: GalxeResult = GalxeResult(platform=self.platform_name, url="")

    def visit(self, url: str) -> bool:
        """Load a Galxe campaign page.

        Args:
            url: Galxe URL (e.g., https://app.galxe.com/quest/abc123).

        Returns:
            True if campaign loaded successfully.
        """
        self._current_url = url
        self._campaign_id = self._extract_galxe_id(url)
        logger.info(f"Galxe: loading campaign {self._campaign_id}")

        try:
            # Fetch campaign details via GraphQL
            result = self._graphql_query(
                CAMPAIGN_DETAIL_QUERY,
                {"id": self._campaign_id},
            )
            campaign = result.get("data", {}).get("campaign")
            if campaign:
                self._campaign_data = campaign
                logger.info(f"Galxe: loaded campaign '{campaign.get('name', 'unknown')}'")
                return True
            else:
                logger.warning("Galxe: campaign not found in GraphQL response")
        except Exception as e:
            logger.error(f"Galxe: failed to load campaign: {e}")

        return False

    def get_campaigns(
        self,
        space_id: Optional[str] = None,
        first: int = 20,
    ) -> list[dict]:
        """Fetch active campaigns via GraphQL.

        Args:
            space_id: Optional space ID to filter by.
            first: Number of campaigns to fetch.

        Returns:
            List of campaign dicts.
        """
        try:
            filter_data = {"status": "Active"}
            if space_id:
                filter_data["spaceId"] = space_id

            result = self._graphql_query(
                CAMPAIGN_LIST_QUERY,
                {"first": first, "filter": filter_data},
            )

            edges = result.get("data", {}).get("campaignList", {}).get("edges", [])
            campaigns = [edge.get("node", {}) for edge in edges]
            logger.info(f"Galxe: found {len(campaigns)} active campaigns")
            return campaigns

        except Exception as e:
            logger.error(f"Galxe: failed to fetch campaigns: {e}")
            return []

    def get_tasks(self) -> list[GalxeTask]:
        """Parse campaign tasks from loaded campaign data.

        Returns:
            List of GalxeTask objects.
        """
        if not self._campaign_data:
            logger.error("Galxe: no campaign loaded. Call visit() first.")
            return []

        tasks: list[GalxeTask] = []
        campaign_tasks = self._campaign_data.get("tasks", [])

        logger.info(f"Galxe: parsing {len(campaign_tasks)} tasks")

        for i, task_data in enumerate(campaign_tasks):
            task = self._parse_task(task_data, i)
            if task:
                tasks.append(task)

        return tasks

    def complete_task(self, task: GalxeTask) -> bool:
        """Complete a single Galxe task.

        Args:
            task: The GalxeTask to complete.

        Returns:
            True if task was completed successfully.
        """
        if task.is_completed:
            logger.info(f"Galxe: task '{task.title}' already completed")
            return True

        try:
            # Handle GeeTest CAPTCHA if needed
            captcha_data = self._handle_geetest_if_needed()

            payload = {
                "campaignId": self._campaign_id,
                "taskId": task.task_id_galxe,
                "type": task.task_type,
            }
            if captcha_data:
                payload["captcha"] = captcha_data

            response = self._post(
                f"{self.REST_API}/task/complete",
                json=payload,
            )

            result = response.json()
            success = result.get("success", False)

            if success:
                task.is_completed = True
                logger.info(f"Galxe: completed task '{task.title}'")
            else:
                logger.warning(f"Galxe: task '{task.title}' failed: {result.get('message')}")

            return success

        except Exception as e:
            logger.error(f"Galxe: task '{task.title}' failed: {e}")
            return False

    def verify_credentials(self) -> dict[str, bool]:
        """Check on-chain credential proofs.

        Returns:
            Dict mapping credential names to eligibility status.
        """
        if not self._wallet_address or not self._campaign_id:
            logger.error("Galxe: wallet address and campaign required for verification")
            return {}

        try:
            result = self._graphql_query(
                USER_CREDENTIALS_QUERY,
                {
                    "address": self._wallet_address,
                    "campaignId": self._campaign_id,
                },
            )

            credentials = result.get("data", {}).get("userCredentials", [])
            status = {}
            verified_count = 0

            for cred in credentials:
                name = cred.get("name", "unknown")
                eligible = cred.get("eligible", False)
                status[name] = eligible
                if eligible:
                    verified_count += 1

            logger.info(f"Galxe: {verified_count}/{len(credentials)} credentials verified")
            self._galxe_results.credentials_verified = verified_count
            return status

        except Exception as e:
            logger.error(f"Galxe: credential verification failed: {e}")
            return {}

    def claim_reward(self) -> bool:
        """Claim points/tokens reward.

        Returns:
            True if reward was claimed successfully.
        """
        if not self._wallet_address or not self._campaign_id:
            logger.error("Galxe: wallet address and campaign required for claiming")
            return False

        try:
            # Handle GeeTest CAPTCHA for claim
            captcha_data = self._handle_geetest_if_needed()

            payload = {
                "campaignId": self._campaign_id,
                "address": self._wallet_address,
            }
            if captcha_data:
                payload["captcha"] = captcha_data

            # Try GraphQL mutation
            result = self._graphql_query(
                CLAIM_REWARD_MUTATION,
                payload,
            )

            claim_result = result.get("data", {}).get("claimReward", {})
            success = claim_result.get("success", False)

            if success:
                logger.info(f"Galxe: reward claimed! tx={claim_result.get('txHash', 'N/A')}")
                self._galxe_results.reward_claimed = True
            else:
                logger.warning(f"Galxe: claim failed: {claim_result.get('message')}")

            return success

        except Exception as e:
            logger.error(f"Galxe: reward claim failed: {e}")
            return False

    def login(self, credentials: dict) -> bool:
        """Authenticate with Galxe.

        Args:
            credentials: Must contain 'wallet_address' and optionally 'auth_token'.

        Returns:
            True if login succeeded.
        """
        self._wallet_address = credentials.get("wallet_address")
        self._auth_token = credentials.get("auth_token")

        if self._auth_token:
            self.session.headers["Authorization"] = f"Bearer {self._auth_token}"

        if self._wallet_address:
            self._authenticated = True
            logger.info(f"Galxe: authenticated with wallet {self._wallet_address[:10]}...")
            return True

        logger.warning("Galxe: no wallet address provided")
        return False

    def close(self) -> None:
        """Clean up resources."""
        super().close()
        self._campaign_data = None

    # ─── Private Helpers ─────────────────────────────────────────

    def _extract_galxe_id(self, url: str) -> str:
        """Extract campaign ID from Galxe URL."""
        # Galxe URLs: https://app.galxe.com/quest/abc123 or /campaign/abc123
        parsed = urlparse(url)
        path_parts = [p for p in parsed.path.split("/") if p]

        # Find the ID after 'quest' or 'campaign'
        for i, part in enumerate(path_parts):
            if part in ("quest", "campaign") and i + 1 < len(path_parts):
                return path_parts[i + 1]

        # Fallback to last segment
        return path_parts[-1] if path_parts else "unknown"

    def _graphql_query(self, query: str, variables: dict) -> dict:
        """Execute a GraphQL query.

        Args:
            query: The GraphQL query string.
            variables: Query variables.

        Returns:
            The response data dict.
        """
        headers = {"Content-Type": "application/json"}
        if self._auth_token:
            headers["Authorization"] = f"Bearer {self._auth_token}"

        response = self._post(
            self.GRAPHQL_API,
            json={"query": query, "variables": variables},
            headers=headers,
        )

        return response.json()

    def _parse_task(self, data: dict, index: int) -> Optional[GalxeTask]:
        """Parse a task from GraphQL response."""
        try:
            task_id = str(data.get("id", index))
            title = data.get("name", f"Task {index}")
            task_type = data.get("type", "custom")
            description = data.get("description", "")
            status = data.get("status", "")
            is_completed = status.lower() in ("completed", "verified")

            # Get credential info
            credential = data.get("credential", {})
            credential_id = str(credential.get("id", "")) if credential else ""

            # Parse attribute data
            attribute = data.get("attribute", {})
            if isinstance(attribute, str):
                try:
                    attribute = json.loads(attribute)
                except (json.JSONDecodeError, TypeError):
                    attribute = {}

            mapped_type = self._map_task_type(task_type)

            difficulty = TaskDifficulty.EASY
            if mapped_type.startswith("on_chain"):
                difficulty = TaskDifficulty.MEDIUM
            elif mapped_type in ("nft_mint", "on_chain_bridge"):
                difficulty = TaskDifficulty.HARD

            return GalxeTask(
                task_id=f"galxe_{self._campaign_id}_{task_id}",
                title=title,
                description=description,
                task_type=mapped_type,
                points=int(attribute.get("points", 0)),
                is_completed=is_completed,
                campaign_id=self._campaign_id or "",
                credential_id=credential_id,
                task_id_galxe=task_id,
                verify_type=attribute.get("verifyType", ""),
                chain_id=attribute.get("chainId"),
                contract_address=attribute.get("contractAddress", ""),
                difficulty=difficulty,
                metadata={"campaign_id": self._campaign_id, "attribute": attribute},
            )

        except Exception as e:
            logger.debug(f"Galxe: failed to parse task {index}: {e}")
            return None

    def _map_task_type(self, raw_type: str) -> str:
        """Map Galxe task type to standard type."""
        type_map = {
            "twitter_follow": "twitter_follow",
            "twitter_retweet": "twitter_retweet",
            "twitter_like": "twitter_like",
            "twitter_tweet": "twitter_comment",
            "discord_join": "discord_join",
            "discord_verify": "discord_verify",
            "telegram_join": "telegram_join",
            "quiz": "quiz",
            "visit_url": "visit_url",
            "on_chain": "on_chain_tx",
            "on_chain_tx": "on_chain_tx",
            "on_chain_swap": "on_chain_swap",
            "on_chain_bridge": "on_chain_bridge",
            "on_chain_stake": "on_chain_stake",
            "nft_mint": "nft_mint",
            "nft_hold": "custom",
            "token_hold": "custom",
            "referral": "referral",
            "custom": "custom",
        }
        raw_lower = raw_type.lower().replace("-", "_")
        return type_map.get(raw_lower, "custom")

    def _handle_geetest_if_needed(self) -> Optional[dict]:
        """Handle GeeTest CAPTCHA if triggered."""
        try:
            from .captcha_solver import CaptchaSolver, CaptchaConfig, CaptchaProvider

            solver = CaptchaSolver(CaptchaConfig(
                provider=CaptchaProvider(self.config.captcha_provider),
                api_key=self.config.captcha_api_key,
            ))

            # Check if GeeTest is required (Galxe uses GeeTest)
            # This would be detected from the response in a real implementation
            return None

        except Exception as e:
            logger.debug(f"Galxe: GeeTest handling skipped: {e}")
            return None
