"""Campaign Discovery — auto-scan airdrop platforms for new campaigns.

Scans Galxe, Zealy, Layer3, QuestN, TaskOn, Intract, Port3, and Gleam
for new campaigns. Filters by value, deduplicates, and exports URLs for
the executor layer to process.

Usage::

    from web3_agent_kit.airdrop.discovery import CampaignDiscovery

    discovery = CampaignDiscovery()
    campaigns = discovery.discover_all()
    for c in campaigns:
        print(f"[{c.platform}] {c.title} — {c.points} pts — {c.url}")
"""

from __future__ import annotations

import json
import logging
import asyncio
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional

import requests

logger = logging.getLogger(__name__)


class CampaignStatus(Enum):
    """Campaign lifecycle status."""
    UPCOMING = "upcoming"
    ACTIVE = "active"
    ENDING_SOON = "ending_soon"
    ENDED = "ended"
    UNKNOWN = "unknown"


class CampaignCategory(Enum):
    """Campaign category."""
    DEFI = "defi"
    NFT = "nft"
    SOCIAL = "social"
    GAMING = "gaming"
    INFRA = "infra"
    BRIDGE = "bridge"
    LENDING = "lending"
    STAKING = "staking"
    DAO = "dao"
    OTHER = "other"


@dataclass
class DiscoveredCampaign:
    """A discovered campaign from any platform."""
    platform: str
    campaign_id: str
    title: str
    url: str
    description: str = ""
    points: int = 0
    status: CampaignStatus = CampaignStatus.ACTIVE
    category: CampaignCategory = CampaignCategory.OTHER
    chain: str = ""
    space_name: str = ""
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    task_count: int = 0
    participant_count: int = 0
    reward_amount: str = ""
    reward_token: str = ""
    difficulty: str = "easy"
    tags: list[str] = field(default_factory=list)
    discovered_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict = field(default_factory=dict)

    @property
    def is_high_value(self) -> bool:
        """Check if campaign is high-value (>= 100 points or has reward)."""
        return self.points >= 100 or bool(self.reward_amount)

    @property
    def is_ending_soon(self) -> bool:
        """Check if campaign ends within 24 hours."""
        if not self.end_time:
            return False
        now = datetime.now(timezone.utc)
        delta = self.end_time - now
        return delta.total_seconds() > 0 and delta.total_seconds() < 86400

    def to_dict(self) -> dict:
        """Serialize to dict."""
        return {
            "platform": self.platform,
            "campaign_id": self.campaign_id,
            "title": self.title,
            "url": self.url,
            "description": self.description[:200],
            "points": self.points,
            "status": self.status.value,
            "category": self.category.value,
            "chain": self.chain,
            "space_name": self.space_name,
            "task_count": self.task_count,
            "participant_count": self.participant_count,
            "reward_amount": self.reward_amount,
            "reward_token": self.reward_token,
            "difficulty": self.difficulty,
            "tags": self.tags,
            "discovered_at": self.discovered_at.isoformat(),
        }


@dataclass
class DiscoveryConfig:
    """Configuration for campaign discovery."""
    # Platforms to scan
    platforms: list[str] = field(default_factory=lambda: [
        "galxe", "zealy", "layer3", "questn", "taskon", "intract", "port3"
    ])
    # Minimum points to include
    min_points: int = 0
    # Only include active campaigns
    active_only: bool = True
    # Maximum campaigns per platform
    max_per_platform: int = 50
    # Categories to include (empty = all)
    categories: list[str] = field(default_factory=list)
    # Chains to include (empty = all)
    chains: list[str] = field(default_factory=list)
    # Proxy for requests
    proxy: Optional[str] = None
    # Rate limit delay between platforms
    rate_limit_delay: float = 2.0
    # Save discovered campaigns to file
    save_path: Optional[str] = None
    # Load previously seen campaigns from file
    seen_path: Optional[str] = None


class CampaignDiscovery:
    """Auto-scan airdrop platforms for new campaigns.

    Discovers campaigns from multiple platforms, filters by value/category,
    deduplicates against previously seen campaigns, and exports URLs.

    Example::

        discovery = CampaignDiscovery()
        campaigns = discovery.discover_all()

        # Filter high-value only
        high_value = [c for c in campaigns if c.is_high_value]

        # Export URLs for executor
        urls = [c.url for c in campaigns]
    """

    # Galxe GraphQL
    GALXE_API = "https://graphigo.prd.galaxy.eco/query"
    GALXE_CAMPAIGNS_QUERY = """
    query CampaignList($first: Int, $after: String, $filter: CampaignListFilter) {
      campaignList(first: $first, after: $after, filter: $filter) {
        edges {
          node {
            id name description status startTime endTime
            space { id name }
            tasks { id name type }
            thumbnail
          }
        }
        pageInfo { hasNextPage endCursor }
      }
    }
    """

    # Zealy
    ZEALY_API = "https://api.zealy.io"

    # Layer3
    LAYER3_API = "https://layer3.xyz/api"

    # QuestN
    QUESTN_API = "https://api.questn.com"

    # TaskOn
    TASKON_API = "https://api.taskon.xyz"

    # Intract
    INTRACT_API = "https://api.intract.io"

    # Port3
    PORT3_API = "https://api.port3.io"

    def __init__(self, config: Optional[DiscoveryConfig] = None):
        """Initialize campaign discovery.

        Args:
            config: Discovery configuration.
        """
        self.config = config or DiscoveryConfig()
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json",
        })
        if self.config.proxy:
            self.session.proxies = {
                "http": self.config.proxy,
                "https": self.config.proxy,
            }
        self._seen_campaigns: set[str] = set()
        self._load_seen()
        logger.info("CampaignDiscovery initialized")

    def discover_all(self) -> list[DiscoveredCampaign]:
        """Scan all configured platforms for campaigns.

        Returns:
            List of discovered campaigns, sorted by points (desc).
        """
        all_campaigns: list[DiscoveredCampaign] = []
        scanners = {
            "galxe": self._scan_galxe,
            "zealy": self._scan_zealy,
            "layer3": self._scan_layer3,
            "questn": self._scan_questn,
            "taskon": self._scan_taskon,
            "intract": self._scan_intract,
            "port3": self._scan_port3,
        }

        for platform in self.config.platforms:
            scanner = scanners.get(platform)
            if not scanner:
                logger.warning(f"Unknown platform: {platform}")
                continue

            try:
                logger.info(f"Scanning {platform}...")
                campaigns = scanner()
                new_campaigns = [
                    c for c in campaigns
                    if self._campaign_key(c) not in self._seen_campaigns
                ]
                all_campaigns.extend(new_campaigns)
                logger.info(
                    f"{platform}: found {len(campaigns)} total, "
                    f"{len(new_campaigns)} new"
                )
                time.sleep(self.config.rate_limit_delay)  # TODO: convert to async
            except Exception as e:
                logger.error(f"Failed to scan {platform}: {e}")

        # Apply filters
        filtered = self._filter_campaigns(all_campaigns)

        # Sort by points desc
        filtered.sort(key=lambda c: c.points, reverse=True)

        # Save seen campaigns
        self._save_seen(filtered)

        logger.info(
            f"Discovery complete: {len(filtered)} campaigns "
            f"(from {len(all_campaigns)} raw)"
        )
        return filtered

    async def async_discover_all(self) -> list[DiscoveredCampaign]:
        """Async version of discover_all — non-blocking sleep between platforms.

        Returns:
            List of discovered campaigns, sorted by points (desc).
        """
        all_campaigns: list[DiscoveredCampaign] = []
        scanners = {
            "galxe": self._scan_galxe,
            "zealy": self._scan_zealy,
            "layer3": self._scan_layer3,
            "questn": self._scan_questn,
            "taskon": self._scan_taskon,
            "intract": self._scan_intract,
            "port3": self._scan_port3,
        }

        for platform in self.config.platforms:
            scanner = scanners.get(platform)
            if not scanner:
                logger.warning(f"Unknown platform: {platform}")
                continue

            try:
                logger.info(f"Scanning {platform}...")
                campaigns = scanner()
                new_campaigns = [
                    c for c in campaigns
                    if self._campaign_key(c) not in self._seen_campaigns
                ]
                all_campaigns.extend(new_campaigns)
                logger.info(
                    f"{platform}: found {len(campaigns)} total, "
                    f"{len(new_campaigns)} new"
                )
                await asyncio.sleep(self.config.rate_limit_delay)
            except Exception as e:
                logger.error(f"Failed to scan {platform}: {e}")

        filtered = self._filter_campaigns(all_campaigns)
        filtered.sort(key=lambda c: c.points, reverse=True)
        self._save_seen(filtered)

        logger.info(
            f"Discovery complete: {len(filtered)} campaigns "
            f"(from {len(all_campaigns)} raw)"
        )
        return filtered

    def discover_platform(self, platform: str) -> list[DiscoveredCampaign]:
        """Scan a single platform for campaigns.

        Args:
            platform: Platform name (galxe, zealy, etc.).

        Returns:
            List of discovered campaigns from that platform.
        """
        scanners = {
            "galxe": self._scan_galxe,
            "zealy": self._scan_zealy,
            "layer3": self._scan_layer3,
            "questn": self._scan_questn,
            "taskon": self._scan_taskon,
            "intract": self._scan_intract,
            "port3": self._scan_port3,
        }
        scanner = scanners.get(platform)
        if not scanner:
            raise ValueError(f"Unknown platform: {platform}")
        return scanner()

    def get_new_campaigns(self) -> list[DiscoveredCampaign]:
        """Get only campaigns not seen before.

        Returns:
            List of new (unseen) campaigns.
        """
        all_campaigns = self.discover_all()
        return [
            c for c in all_campaigns
            if self._campaign_key(c) not in self._seen_campaigns
        ]

    def get_high_value_campaigns(
        self, min_points: int = 100
    ) -> list[DiscoveredCampaign]:
        """Get only high-value campaigns.

        Args:
            min_points: Minimum points threshold.

        Returns:
            List of high-value campaigns.
        """
        all_campaigns = self.discover_all()
        return [c for c in all_campaigns if c.points >= min_points]

    def export_urls(self, campaigns: list[DiscoveredCampaign]) -> list[str]:
        """Extract URLs from campaigns for executor processing.

        Args:
            campaigns: List of discovered campaigns.

        Returns:
            List of campaign URLs.
        """
        return [c.url for c in campaigns]

    def export_json(
        self,
        campaigns: list[DiscoveredCampaign],
        path: Optional[str] = None,
    ) -> str:
        """Export campaigns to JSON.

        Args:
            campaigns: List of discovered campaigns.
            path: Optional file path to save.

        Returns:
            JSON string.
        """
        data = {
            "discovered_at": datetime.now(timezone.utc).isoformat(),
            "total": len(campaigns),
            "campaigns": [c.to_dict() for c in campaigns],
        }
        json_str = json.dumps(data, indent=2, default=str)

        if path:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            Path(path).write_text(json_str)
            logger.info(f"Exported {len(campaigns)} campaigns to {path}")

        return json_str

    # ─── Platform Scanners ────────────────────────────────────────

    def _scan_galxe(self) -> list[DiscoveredCampaign]:
        """Scan Galxe for active campaigns."""
        campaigns = []
        cursor = None
        fetched = 0

        while fetched < self.config.max_per_platform:
            try:
                variables: dict[str, Any] = {
                    "first": min(20, self.config.max_per_platform - fetched),
                    "filter": {"status": "Active"},
                }
                if cursor:
                    variables["after"] = cursor

                resp = self.session.post(
                    self.GALXE_API,
                    json={"query": self.GALXE_CAMPAIGNS_QUERY, "variables": variables},
                    timeout=15,
                )
                resp.raise_for_status()
                data = resp.json()

                edges = (
                    data.get("data", {})
                    .get("campaignList", {})
                    .get("edges", [])
                )
                page_info = (
                    data.get("data", {})
                    .get("campaignList", {})
                    .get("pageInfo", {})
                )

                for edge in edges:
                    node = edge.get("node", {})
                    campaign = self._parse_galxe_campaign(node)
                    if campaign:
                        campaigns.append(campaign)
                    fetched += 1

                if not page_info.get("hasNextPage"):
                    break
                cursor = page_info.get("endCursor")

            except Exception as e:
                logger.error(f"Galxe scan error: {e}")
                break

        return campaigns

    def _scan_zealy(self) -> list[DiscoveredCampaign]:
        """Scan Zealy for active communities/quests."""
        campaigns = []
        try:
            # Zealy public community listing
            resp = self.session.get(
                f"{self.ZEALY_API}/communities",
                params={"limit": self.config.max_per_platform, "sort": "popular"},
                timeout=15,
            )
            if resp.status_code == 200:
                data = resp.json()
                communities = data if isinstance(data, list) else data.get("data", [])
                for comm in communities[:self.config.max_per_platform]:
                    slug = comm.get("slug", "")
                    name = comm.get("name", "")
                    campaigns.append(DiscoveredCampaign(
                        platform="zealy",
                        campaign_id=slug,
                        title=f"{name} Community Quests",
                        url=f"https://zealy.io/c/{slug}",
                        description=comm.get("description", "")[:200],
                        space_name=name,
                        participant_count=comm.get("memberCount", 0),
                        tags=comm.get("tags", []),
                    ))
        except Exception as e:
            logger.error(f"Zealy scan error: {e}")
        return campaigns

    def _scan_layer3(self) -> list[DiscoveredCampaign]:
        """Scan Layer3 for active quests."""
        campaigns = []
        try:
            resp = self.session.get(
                f"{self.LAYER3_API}/quests",
                params={"status": "active", "limit": self.config.max_per_platform},
                timeout=15,
            )
            if resp.status_code == 200:
                data = resp.json()
                quests = data if isinstance(data, list) else data.get("data", [])
                for quest in quests[:self.config.max_per_platform]:
                    campaigns.append(DiscoveredCampaign(
                        platform="layer3",
                        campaign_id=str(quest.get("id", "")),
                        title=quest.get("title", "Untitled"),
                        url=f"https://layer3.xyz/quests/{quest.get('slug', quest.get('id', ''))}",
                        description=quest.get("description", "")[:200],
                        points=quest.get("xp", 0),
                        chain=quest.get("chain", ""),
                        participant_count=quest.get("completions", 0),
                        reward_amount=str(quest.get("reward", "")),
                        reward_token=quest.get("rewardToken", ""),
                        tags=quest.get("tags", []),
                    ))
        except Exception as e:
            logger.error(f"Layer3 scan error: {e}")
        return campaigns

    def _scan_questn(self) -> list[DiscoveredCampaign]:
        """Scan QuestN for active campaigns."""
        campaigns = []
        try:
            resp = self.session.get(
                f"{self.QUESTN_API}/v2/campaigns",
                params={"status": "active", "page": 1, "size": self.config.max_per_platform},
                timeout=15,
            )
            if resp.status_code == 200:
                data = resp.json()
                items = data.get("data", {}).get("list", [])
                for item in items:
                    campaigns.append(DiscoveredCampaign(
                        platform="questn",
                        campaign_id=str(item.get("id", "")),
                        title=item.get("title", "Untitled"),
                        url=f"https://questn.com/detail/{item.get('id', '')}",
                        description=item.get("description", "")[:200],
                        points=item.get("points", 0),
                        participant_count=item.get("participantCount", 0),
                        tags=item.get("tags", []),
                    ))
        except Exception as e:
            logger.error(f"QuestN scan error: {e}")
        return campaigns

    def _scan_taskon(self) -> list[DiscoveredCampaign]:
        """Scan TaskOn for active campaigns."""
        campaigns = []
        try:
            resp = self.session.get(
                f"{self.TASKON_API}/v1/campaigns",
                params={"status": "ongoing", "pageSize": self.config.max_per_platform},
                timeout=15,
            )
            if resp.status_code == 200:
                data = resp.json()
                items = data.get("data", {}).get("list", [])
                for item in items:
                    campaigns.append(DiscoveredCampaign(
                        platform="taskon",
                        campaign_id=str(item.get("id", "")),
                        title=item.get("title", "Untitled"),
                        url=item.get("url", f"https://taskon.xyz/campaign/{item.get('id', '')}"),
                        description=item.get("description", "")[:200],
                        points=item.get("points", 0),
                        participant_count=item.get("participantCount", 0),
                    ))
        except Exception as e:
            logger.error(f"TaskOn scan error: {e}")
        return campaigns

    def _scan_intract(self) -> list[DiscoveredCampaign]:
        """Scan Intract for active campaigns."""
        campaigns = []
        try:
            resp = self.session.get(
                f"{self.INTRACT_API}/campaigns",
                params={"status": "active", "limit": self.config.max_per_platform},
                timeout=15,
            )
            if resp.status_code == 200:
                data = resp.json()
                items = data if isinstance(data, list) else data.get("data", [])
                for item in items[:self.config.max_per_platform]:
                    campaigns.append(DiscoveredCampaign(
                        platform="intract",
                        campaign_id=str(item.get("id", "")),
                        title=item.get("title", "Untitled"),
                        url=f"https://intract.io/quest/{item.get('slug', item.get('id', ''))}",
                        description=item.get("description", "")[:200],
                        points=item.get("xp", 0),
                        participant_count=item.get("participants", 0),
                        tags=item.get("tags", []),
                    ))
        except Exception as e:
            logger.error(f"Intract scan error: {e}")
        return campaigns

    def _scan_port3(self) -> list[DiscoveredCampaign]:
        """Scan Port3 for active quests."""
        campaigns = []
        try:
            resp = self.session.get(
                f"{self.PORT3_API}/quests",
                params={"status": "active", "limit": self.config.max_per_platform},
                timeout=15,
            )
            if resp.status_code == 200:
                data = resp.json()
                items = data if isinstance(data, list) else data.get("data", [])
                for item in items[:self.config.max_per_platform]:
                    campaigns.append(DiscoveredCampaign(
                        platform="port3",
                        campaign_id=str(item.get("id", "")),
                        title=item.get("title", "Untitled"),
                        url=f"https://port3.io/quest/{item.get('id', '')}",
                        description=item.get("description", "")[:200],
                        points=item.get("points", 0),
                        participant_count=item.get("participants", 0),
                    ))
        except Exception as e:
            logger.error(f"Port3 scan error: {e}")
        return campaigns

    # ─── Helpers ──────────────────────────────────────────────────

    def _parse_galxe_campaign(self, node: dict) -> Optional[DiscoveredCampaign]:
        """Parse a Galxe campaign from GraphQL response."""
        try:
            campaign_id = str(node.get("id", ""))
            if not campaign_id:
                return None

            tasks = node.get("tasks", [])
            start_time = node.get("startTime")
            end_time = node.get("endTime")
            space = node.get("space", {})

            # Parse times
            start_dt = None
            end_dt = None
            if start_time:
                try:
                    start_dt = datetime.fromtimestamp(int(start_time), tz=timezone.utc)
                except (ValueError, TypeError):
                    pass
            if end_time:
                try:
                    end_dt = datetime.fromtimestamp(int(end_time), tz=timezone.utc)
                except (ValueError, TypeError):
                    pass

            # Determine status
            status = CampaignStatus.ACTIVE
            now = datetime.now(timezone.utc)
            if end_dt and end_dt < now:
                status = CampaignStatus.ENDED
            elif end_dt and (end_dt - now).total_seconds() < 86400:
                status = CampaignStatus.ENDING_SOON

            # Estimate points from tasks
            points = len(tasks) * 10  # rough estimate

            return DiscoveredCampaign(
                platform="galxe",
                campaign_id=campaign_id,
                title=node.get("name", "Untitled"),
                url=f"https://app.galxe.com/quest/{campaign_id}",
                description=node.get("description", "")[:200],
                points=points,
                status=status,
                space_name=space.get("name", ""),
                start_time=start_dt,
                end_time=end_dt,
                task_count=len(tasks),
                tags=[],
            )
        except Exception as e:
            logger.debug(f"Failed to parse Galxe campaign: {e}")
            return None

    def _filter_campaigns(
        self, campaigns: list[DiscoveredCampaign]
    ) -> list[DiscoveredCampaign]:
        """Apply configured filters to campaigns."""
        filtered = []
        for c in campaigns:
            # Min points filter
            if self.config.min_points > 0 and c.points < self.config.min_points:
                continue
            # Active only filter
            if self.config.active_only and c.status == CampaignStatus.ENDED:
                continue
            # Category filter
            if self.config.categories and c.category.value not in self.config.categories:
                continue
            # Chain filter
            if self.config.chains and c.chain and c.chain not in self.config.chains:
                continue
            filtered.append(c)
        return filtered

    def _campaign_key(self, campaign: DiscoveredCampaign) -> str:
        """Generate unique key for a campaign."""
        return f"{campaign.platform}:{campaign.campaign_id}"

    def _load_seen(self) -> None:
        """Load previously seen campaigns from file."""
        if not self.config.seen_path:
            return
        path = Path(self.config.seen_path)
        if path.exists():
            try:
                data = json.loads(path.read_text())
                self._seen_campaigns = set(data.get("seen", []))
                logger.info(f"Loaded {len(self._seen_campaigns)} seen campaigns")
            except Exception as e:
                logger.warning(f"Failed to load seen campaigns: {e}")

    def _save_seen(self, campaigns: list[DiscoveredCampaign]) -> None:
        """Save seen campaign keys to file."""
        if not self.config.save_path:
            return
        for c in campaigns:
            self._seen_campaigns.add(self._campaign_key(c))
        path = Path(self.config.save_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            data = {
                "seen": list(self._seen_campaigns),
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "count": len(self._seen_campaigns),
            }
            path.write_text(json.dumps(data, indent=2))
            logger.info(f"Saved {len(self._seen_campaigns)} seen campaigns")
        except Exception as e:
            logger.warning(f"Failed to save seen campaigns: {e}")
