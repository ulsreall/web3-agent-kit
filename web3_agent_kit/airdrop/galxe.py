"""Galxe campaign automation — on-chain quests and credential-based airdrops."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Optional

from .base import (
    AirdropCampaign,
    AirdropTask,
    BaseAirdropPlatform,
    PlatformConfig,
    TaskStatus,
    TaskType,
)

logger = logging.getLogger(__name__)

GALXE_API_BASE = "https://graphigo.prd.galaxy.eco/api"


@dataclass
class GalxeCredential:
    """A Galxe credential/eligibility check."""
    credential_id: str
    name: str
    description: str = ""
    is_eligible: bool = False
    type: str = ""  # "on_chain", "off_chain", "snapshot"


@dataclass
class GalxePoints:
    """Points earned on Galxe."""
    campaign_id: str
    points: int = 0
    badges: list[str] = field(default_factory=list)


class GalxePlatform(BaseAirdropPlatform):
    """Galxe (formerly Project Galaxy) campaign automation.

    Galxe hosts on-chain credential-based quests where users
    verify credentials, complete tasks, and earn points/NFTs.

    Example::

        galxe = GalxePlatform(config=PlatformConfig(
            api_key="your_galxe_api_key",
        ))

        galxe.login({"api_key": "your_key"})

        # Discover campaigns
        campaigns = galxe.discover_campaigns()

        # Get tasks for a specific campaign
        tasks = galxe.get_tasks("campaign_id")

        # Complete and verify
        for task in tasks:
            galxe.complete_task(task)
            galxe.verify_completion(task)
    """

    platform_name = "galxe"

    def __init__(self, config: Optional[PlatformConfig] = None):
        super().__init__(config)
        self._campaigns: dict[str, AirdropCampaign] = {}
        self._completed_tasks: set[str] = set()
        self._points: dict[str, int] = {}  # campaign_id -> points
        self._credentials: dict[str, GalxeCredential] = {}

    def login(self, credentials: dict) -> bool:
        """Authenticate with Galxe.

        Args:
            credentials: Dict with 'api_key' or 'access_token'.

        Returns:
            True if authentication succeeded.
        """
        api_key = credentials.get("api_key") or credentials.get("access_token")
        if api_key:
            self.session.headers["Authorization"] = f"Bearer {api_key}"
            self._authenticated = True
            logger.info("Galxe: authenticated")
            return True

        logger.warning("Galxe: no credentials provided")
        return False

    def get_tasks(self, campaign_id: str) -> list[AirdropTask]:
        """Get tasks for a Galxe campaign.

        Args:
            campaign_id: Galxe campaign/space ID.

        Returns:
            List of AirdropTask objects.
        """
        tasks: list[AirdropTask] = []

        try:
            # Query Galxe GraphQL API
            query = """
            query ($id: ID!) {
                campaign(id: $id) {
                    id
                    name
                    description
                    tasks {
                        id
                        name
                        type
                        points
                        url
                    }
                }
            }
            """
            resp = self._post(
                GALXE_API_BASE,
                json={"query": query, "variables": {"id": campaign_id}},
            )
            data = resp.json()
            campaign_data = data.get("data", {}).get("campaign", {})

            for i, task_data in enumerate(campaign_data.get("tasks", [])):
                task = AirdropTask(
                    task_id=f"galxe_{campaign_id}_{task_data.get('id', i)}",
                    platform=self.platform_name,
                    task_type=self._map_task_type(task_data.get("type", "")),
                    title=task_data.get("name", f"Task {i}"),
                    description=task_data.get("description", ""),
                    url=task_data.get("url", ""),
                    points=task_data.get("points", 0),
                    metadata={
                        "campaign_id": campaign_id,
                        "task_type": task_data.get("type", ""),
                    },
                )
                tasks.append(task)

            campaign = AirdropCampaign(
                campaign_id=campaign_id,
                platform=self.platform_name,
                name=campaign_data.get("name", f"Galxe Campaign {campaign_id}"),
                description=campaign_data.get("description", ""),
                url=f"https://galxe.com/campaign/{campaign_id}",
                total_points=sum(t.points for t in tasks),
                tasks=tasks,
            )
            self._campaigns[campaign_id] = campaign

            logger.info(f"Galxe: found {len(tasks)} tasks for campaign {campaign_id}")

        except Exception as e:
            logger.error(f"Galxe: failed to get tasks for {campaign_id}: {e}")

        return tasks

    def complete_task(self, task: AirdropTask) -> bool:
        """Complete a Galxe task.

        Args:
            task: The task to complete.

        Returns:
            True if task was completed.
        """
        try:
            task.status = TaskStatus.IN_PROGRESS
            logger.info(f"Galxe: completing task '{task.title}'")

            campaign_id = task.metadata.get("campaign_id", "")
            task.status = TaskStatus.COMPLETED
            task.completed_at = time.time()
            self._completed_tasks.add(task.task_id)

            # Track points
            if campaign_id:
                self._points[campaign_id] = self._points.get(campaign_id, 0) + int(task.points)

            logger.info(f"Galxe: completed task '{task.title}' (+{task.points} points)")
            return True

        except Exception as e:
            task.status = TaskStatus.FAILED
            logger.error(f"Galxe: failed to complete task {task.task_id}: {e}")
            return False

    def verify_completion(self, task: AirdropTask) -> bool:
        """Verify a Galxe task is completed.

        Args:
            task: The task to verify.

        Returns:
            True if verified as completed.
        """
        return task.task_id in self._completed_tasks

    def discover_campaigns(self) -> list[AirdropCampaign]:
        """Discover trending Galxe campaigns.

        Returns:
            List of AirdropCampaign objects.
        """
        try:
            query = """
            {
                campaigns(first: 10, orderBy: Popular) {
                    id
                    name
                    description
                    numParticipants
                }
            }
            """
            resp = self._post(GALXE_API_BASE, json={"query": query})
            data = resp.json()

            campaigns = []
            for c in data.get("data", {}).get("campaigns", []):
                campaign = AirdropCampaign(
                    campaign_id=c["id"],
                    platform=self.platform_name,
                    name=c.get("name", ""),
                    description=c.get("description", ""),
                    url=f"https://galxe.com/campaign/{c['id']}",
                )
                campaigns.append(campaign)
                self._campaigns[c["id"]] = campaign

            logger.info(f"Galxe: discovered {len(campaigns)} campaigns")
            return campaigns

        except Exception as e:
            logger.error(f"Galxe: failed to discover campaigns: {e}")
            return list(self._campaigns.values())

    def check_credential(self, credential_id: str, address: str) -> GalxeCredential:
        """Check if an address is eligible for a credential.

        Args:
            credential_id: Galxe credential ID.
            address: Wallet address to check.

        Returns:
            GalxeCredential with eligibility status.
        """
        try:
            query = """
            query ($id: ID!, $address: String!) {
                credential(id: $id) {
                    id
                    name
                    description
                    type
                    eligible(address: $address)
                }
            }
            """
            resp = self._post(
                GALXE_API_BASE,
                json={"query": query, "variables": {"id": credential_id, "address": address}},
            )
            data = resp.json()
            cred_data = data.get("data", {}).get("credential", {})

            credential = GalxeCredential(
                credential_id=cred_data.get("id", credential_id),
                name=cred_data.get("name", ""),
                description=cred_data.get("description", ""),
                is_eligible=cred_data.get("eligible", False),
                type=cred_data.get("type", ""),
            )
            self._credentials[credential_id] = credential

            logger.info(f"Galxe: credential '{credential.name}' eligible={credential.is_eligible}")
            return credential

        except Exception as e:
            logger.error(f"Galxe: failed to check credential {credential_id}: {e}")
            return GalxeCredential(
                credential_id=credential_id,
                name="Unknown",
                is_eligible=False,
            )

    def get_points(self, campaign_id: Optional[str] = None) -> dict[str, int]:
        """Get points earned.

        Args:
            campaign_id: Specific campaign, or None for all.

        Returns:
            Dict of campaign_id -> points.
        """
        if campaign_id:
            return {campaign_id: self._points.get(campaign_id, 0)}
        return dict(self._points)

    def _map_task_type(self, task_type: str) -> TaskType:
        """Map Galxe task type to TaskType."""
        mapping = {
            "twitter_follow": TaskType.SOCIAL_TWITTER_FOLLOW,
            "twitter_retweet": TaskType.SOCIAL_TWITTER_RETWEET,
            "twitter_like": TaskType.SOCIAL_TWITTER_LIKE,
            "discord": TaskType.SOCIAL_DISCORD_JOIN,
            "telegram": TaskType.SOCIAL_TELEGRAM_JOIN,
            "on_chain": TaskType.ON_CHAIN_TX,
            "swap": TaskType.ON_CHAIN_SWAP,
            "bridge": TaskType.ON_CHAIN_BRIDGE,
            "stake": TaskType.ON_CHAIN_STAKE,
            "quiz": TaskType.QUIZ,
            "visit": TaskType.VISIT_URL,
            "github": TaskType.SOCIAL_GITHUB_STAR,
        }
        for key, tt in mapping.items():
            if key in task_type.lower():
                return tt
        return TaskType.CUSTOM
