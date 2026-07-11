"""Airdrop tracker — track active airdrops, deadlines, points, and rewards."""

from __future__ import annotations

import csv
import io
import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Optional

from .base import AirdropCampaign, AirdropTask, TaskStatus

logger = logging.getLogger(__name__)


@dataclass
class AirdropReward:
    """A reward earned from an airdrop."""
    platform: str
    campaign_id: str
    campaign_name: str
    points: float = 0
    tokens: float = 0
    token_symbol: str = ""
    claimed: bool = False
    claimed_at: Optional[float] = None
    metadata: dict = field(default_factory=dict)


@dataclass
class AirdropSummary:
    """Summary of all airdrop activity."""
    total_campaigns: int = 0
    active_campaigns: int = 0
    completed_tasks: int = 0
    total_points: float = 0
    total_rewards: list[AirdropReward] = field(default_factory=list)
    platforms: dict[str, int] = field(default_factory=dict)  # platform -> campaign count


class AirdropTracker:
    """Track all airdrop campaigns, tasks, and rewards.

    Provides persistence via JSON storage and export to JSON/CSV.

    Example::

        tracker = AirdropTracker(storage_path="./airdrop_data.json")

        # Add campaigns
        tracker.add_campaign(campaign)

        # Track task completion
        tracker.mark_task_completed(task)

        # Get summary
        summary = tracker.get_summary()
        print(f"Active campaigns: {summary.active_campaigns}")

        # Export
        tracker.export_json("./report.json")
        tracker.export_csv("./report.csv")
    """

    def __init__(self, storage_path: Optional[str] = None):
        self.storage_path = storage_path or os.path.expanduser("~/.web3-agent-kit/airdrops.json")
        self.campaigns: dict[str, AirdropCampaign] = {}
        self.rewards: list[AirdropReward] = []
        self._completed_tasks: dict[str, list[str]] = {}  # campaign_id -> [task_ids]
        self._load()

    def add_campaign(self, campaign: AirdropCampaign):
        """Add or update a campaign in the tracker.

        Args:
            campaign: The AirdropCampaign to track.
        """
        self.campaigns[campaign.campaign_id] = campaign
        if campaign.campaign_id not in self._completed_tasks:
            self._completed_tasks[campaign.campaign_id] = []
        self._save()
        logger.info(f"Tracker: added campaign '{campaign.name}' ({campaign.platform})")

    def mark_task_completed(self, task: AirdropTask):
        """Mark a task as completed and update campaign progress.

        Args:
            task: The completed AirdropTask.
        """
        # Find which campaign this task belongs to
        for campaign in self.campaigns.values():
            for t in campaign.tasks:
                if t.task_id == task.task_id:
                    t.status = TaskStatus.COMPLETED
                    t.completed_at = time.time()
                    campaign.earned_points += task.points

                    if task.task_id not in self._completed_tasks.get(campaign.campaign_id, []):
                        self._completed_tasks.setdefault(campaign.campaign_id, []).append(task.task_id)

                    self._save()
                    logger.info(f"Tracker: completed task '{task.title}' in '{campaign.name}'")
                    return

        logger.warning(f"Tracker: task {task.task_id} not found in any tracked campaign")

    def add_reward(self, reward: AirdropReward):
        """Record a reward earned from an airdrop.

        Args:
            reward: The AirdropReward to record.
        """
        self.rewards.append(reward)
        self._save()
        logger.info(f"Tracker: recorded reward ({reward.points} pts, {reward.tokens} {reward.token_symbol})")

    def get_campaign(self, campaign_id: str) -> Optional[AirdropCampaign]:
        """Get a tracked campaign by ID."""
        return self.campaigns.get(campaign_id)

    def list_campaigns(
        self,
        platform: Optional[str] = None,
        active_only: bool = True,
    ) -> list[AirdropCampaign]:
        """List tracked campaigns with optional filters.

        Args:
            platform: Filter by platform name.
            active_only: Only return active campaigns.

        Returns:
            List of matching AirdropCampaign objects.
        """
        result = list(self.campaigns.values())
        if platform:
            result = [c for c in result if c.platform == platform]
        if active_only:
            result = [c for c in result if c.is_active and not c.is_expired]
        return result

    def get_upcoming_deadlines(self, within_hours: float = 72) -> list[AirdropCampaign]:
        """Get campaigns with deadlines approaching.

        Args:
            within_hours: Only campaigns expiring within this many hours.

        Returns:
            List of campaigns with approaching deadlines, sorted by deadline.
        """
        cutoff = time.time() + (within_hours * 3600)
        upcoming = [
            c for c in self.campaigns.values()
            if c.deadline and c.deadline <= cutoff and c.deadline > time.time()
        ]
        return sorted(upcoming, key=lambda c: c.deadline or 0)

    def get_summary(self) -> AirdropSummary:
        """Get a summary of all airdrop activity.

        Returns:
            AirdropSummary with aggregated stats.
        """
        active = [c for c in self.campaigns.values() if c.is_active and not c.is_expired]
        total_completed = sum(len(tasks) for tasks in self._completed_tasks.values())
        total_points = sum(c.earned_points for c in self.campaigns.values())

        platforms: dict[str, int] = {}
        for c in self.campaigns.values():
            platforms[c.platform] = platforms.get(c.platform, 0) + 1

        return AirdropSummary(
            total_campaigns=len(self.campaigns),
            active_campaigns=len(active),
            completed_tasks=total_completed,
            total_points=total_points,
            total_rewards=list(self.rewards),
            platforms=platforms,
        )

    def export_json(self, path: str):
        """Export all tracking data to JSON.

        Args:
            path: File path to write JSON.
        """
        data = {
            "exported_at": time.time(),
            "campaigns": {},
            "rewards": [],
            "summary": {
                "total_campaigns": len(self.campaigns),
                "completed_tasks": sum(len(t) for t in self._completed_tasks.values()),
                "total_points": sum(c.earned_points for c in self.campaigns.values()),
            },
        }

        for cid, campaign in self.campaigns.items():
            data["campaigns"][cid] = {
                "name": campaign.name,
                "platform": campaign.platform,
                "url": campaign.url,
                "total_points": campaign.total_points,
                "earned_points": campaign.earned_points,
                "progress": campaign.progress,
                "is_active": campaign.is_active,
                "tasks": [
                    {
                        "task_id": t.task_id,
                        "title": t.title,
                        "type": t.task_type.value,
                        "points": t.points,
                        "status": t.status.value,
                    }
                    for t in campaign.tasks
                ],
            }

        for r in self.rewards:
            data["rewards"].append({
                "platform": r.platform,
                "campaign": r.campaign_name,
                "points": r.points,
                "tokens": r.tokens,
                "token_symbol": r.token_symbol,
                "claimed": r.claimed,
            })

        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w") as f:
            json.dump(data, f, indent=2)

        logger.info(f"Tracker: exported to {path}")

    def export_csv(self, path: str):
        """Export campaign data to CSV.

        Args:
            path: File path to write CSV.
        """
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "campaign_id", "platform", "name", "url",
            "total_points", "earned_points", "progress",
            "is_active", "tasks_completed",
        ])

        for cid, campaign in self.campaigns.items():
            completed = len(self._completed_tasks.get(cid, []))
            writer.writerow([
                cid,
                campaign.platform,
                campaign.name,
                campaign.url,
                campaign.total_points,
                campaign.earned_points,
                f"{campaign.progress:.2%}",
                campaign.is_active,
                completed,
            ])

        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", newline="") as f:
            f.write(output.getvalue())

        logger.info(f"Tracker: exported CSV to {path}")

    def _save(self):
        """Persist tracker data to disk."""
        try:
            os.makedirs(os.path.dirname(self.storage_path) or ".", exist_ok=True)
            data = {
                "campaigns": {},
                "rewards": [],
                "completed_tasks": self._completed_tasks,
            }
            for cid, c in self.campaigns.items():
                data["campaigns"][cid] = {
                    "campaign_id": c.campaign_id,
                    "platform": c.platform,
                    "name": c.name,
                    "description": c.description,
                    "url": c.url,
                    "total_points": c.total_points,
                    "earned_points": c.earned_points,
                    "is_active": c.is_active,
                    "deadline": c.deadline,
                }
            for r in self.rewards:
                data["rewards"].append({
                    "platform": r.platform,
                    "campaign_id": r.campaign_id,
                    "campaign_name": r.campaign_name,
                    "points": r.points,
                    "tokens": r.tokens,
                    "token_symbol": r.token_symbol,
                    "claimed": r.claimed,
                })
            with open(self.storage_path, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Tracker: failed to save: {e}")

    def _load(self):
        """Load tracker data from disk."""
        if not os.path.exists(self.storage_path):
            return
        try:
            with open(self.storage_path) as f:
                data = json.load(f)
            for cid, cd in data.get("campaigns", {}).items():
                self.campaigns[cid] = AirdropCampaign(
                    campaign_id=cd.get("campaign_id", cid),
                    platform=cd.get("platform", ""),
                    name=cd.get("name", ""),
                    description=cd.get("description", ""),
                    url=cd.get("url", ""),
                    total_points=cd.get("total_points", 0),
                    earned_points=cd.get("earned_points", 0),
                    is_active=cd.get("is_active", True),
                    deadline=cd.get("deadline"),
                )
            for rd in data.get("rewards", []):
                self.rewards.append(AirdropReward(
                    platform=rd.get("platform", ""),
                    campaign_id=rd.get("campaign_id", ""),
                    campaign_name=rd.get("campaign_name", ""),
                    points=rd.get("points", 0),
                    tokens=rd.get("tokens", 0),
                    token_symbol=rd.get("token_symbol", ""),
                    claimed=rd.get("claimed", False),
                ))
            self._completed_tasks = data.get("completed_tasks", {})
        except Exception as e:
            logger.error(f"Tracker: failed to load: {e}")
