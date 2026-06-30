"""Daily Task Scheduler — auto-run airdrop tasks on a schedule.

Schedules recurring airdrop tasks: daily check-ins, social tasks,
on-chain interactions, and campaign completions.

Usage::

    from web3_agent_kit.airdrop.scheduler import AirdropScheduler

    scheduler = AirdropScheduler()
    scheduler.add_daily("galxe_checkin", "09:00", galxe_checkin_fn)
    scheduler.add_daily("base_swap", "14:00", base_swap_fn)
    scheduler.start()
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


class ScheduleFrequency(Enum):
    """Task execution frequency."""
    ONCE = "once"
    HOURLY = "hourly"
    DAILY = "daily"
    WEEKLY = "weekly"
    CUSTOM = "custom"


class TaskExecutionStatus(Enum):
    """Status of a task execution."""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class ScheduledTask:
    """A scheduled airdrop task."""
    task_id: str
    name: str
    frequency: ScheduleFrequency
    target_time: str = "00:00"  # HH:MM format
    callback: Optional[Callable] = None
    args: tuple = ()
    kwargs: dict = field(default_factory=dict)
    enabled: bool = True
    max_retries: int = 3
    retry_delay: float = 60.0
    timeout: float = 300.0  # 5 minutes
    # State
    last_run: Optional[datetime] = None
    next_run: Optional[datetime] = None
    last_status: TaskExecutionStatus = TaskExecutionStatus.PENDING
    consecutive_failures: int = 0
    total_runs: int = 0
    total_successes: int = 0
    # Metadata
    platform: str = ""
    description: str = ""
    tags: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    @property
    def success_rate(self) -> float:
        """Calculate success rate."""
        if self.total_runs == 0:
            return 0.0
        return self.total_successes / self.total_runs

    @property
    def is_due(self) -> bool:
        """Check if task is due for execution."""
        if not self.enabled:
            return False
        if not self.next_run:
            return True
        return datetime.now(timezone.utc) >= self.next_run

    def to_dict(self) -> dict:
        """Serialize to dict."""
        return {
            "task_id": self.task_id,
            "name": self.name,
            "frequency": self.frequency.value,
            "target_time": self.target_time,
            "enabled": self.enabled,
            "platform": self.platform,
            "description": self.description,
            "last_run": self.last_run.isoformat() if self.last_run else None,
            "next_run": self.next_run.isoformat() if self.next_run else None,
            "last_status": self.last_status.value,
            "total_runs": self.total_runs,
            "total_successes": self.total_successes,
            "success_rate": round(self.success_rate * 100, 1),
            "consecutive_failures": self.consecutive_failures,
        }


@dataclass
class SchedulerConfig:
    """Configuration for the scheduler."""
    check_interval: float = 60.0  # Check every 60 seconds
    max_concurrent: int = 3
    log_path: Optional[str] = None
    state_path: Optional[str] = None
    timezone_offset: int = 0  # Hours from UTC
    randomize_minutes: int = 0  # Random delay 0-N minutes


@dataclass
class ExecutionLog:
    """Log of a task execution."""
    task_id: str
    started_at: datetime
    finished_at: Optional[datetime] = None
    status: TaskExecutionStatus = TaskExecutionStatus.PENDING
    result: Any = None
    error: str = ""
    duration_seconds: float = 0.0

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "status": self.status.value,
            "error": self.error,
            "duration_seconds": round(self.duration_seconds, 2),
        }


class AirdropScheduler:
    """Schedule and run recurring airdrop tasks.

    Manages daily check-ins, social tasks, and on-chain interactions
    that need to run on a schedule. Supports task dependencies,
    retry logic, and execution logging.

    Example::

        scheduler = AirdropScheduler()

        # Add daily tasks
        scheduler.add_daily(
            "galxe_daily",
            "09:00",
            lambda: print("Galxe check-in"),
            platform="galxe",
            description="Daily Galxe campaign check",
        )

        scheduler.add_daily(
            "base_swap",
            "14:00",
            lambda: print("Base swap"),
            platform="base",
            description="Daily swap on Aerodrome",
        )

        # Start scheduler (runs in background)
        scheduler.start()
    """

    def __init__(self, config: Optional[SchedulerConfig] = None):
        """Initialize the scheduler.

        Args:
            config: Scheduler configuration.
        """
        self.config = config or SchedulerConfig()
        self._tasks: dict[str, ScheduledTask] = {}
        self._execution_log: list[ExecutionLog] = []
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._load_state()
        logger.info("AirdropScheduler initialized")

    def add_daily(
        self,
        task_id: str,
        time_str: str,
        callback: Callable,
        *,
        name: str = "",
        platform: str = "",
        description: str = "",
        args: tuple = (),
        kwargs: Optional[dict] = None,
        max_retries: int = 3,
        enabled: bool = True,
    ) -> ScheduledTask:
        """Add a daily task.

        Args:
            task_id: Unique task identifier.
            time_str: Time to run (HH:MM format).
            callback: Function to execute.
            name: Human-readable name.
            platform: Platform name.
            description: Task description.
            args: Positional args for callback.
            kwargs: Keyword args for callback.
            max_retries: Max retry attempts.
            enabled: Whether task is enabled.

        Returns:
            The created ScheduledTask.
        """
        task = ScheduledTask(
            task_id=task_id,
            name=name or task_id,
            frequency=ScheduleFrequency.DAILY,
            target_time=time_str,
            callback=callback,
            args=args,
            kwargs=kwargs or {},
            enabled=enabled,
            max_retries=max_retries,
            platform=platform,
            description=description,
            next_run=self._calculate_next_run(ScheduleFrequency.DAILY, time_str),
        )
        self._tasks[task_id] = task
        logger.info(f"Added daily task: {task_id} at {time_str}")
        return task

    def add_hourly(
        self,
        task_id: str,
        callback: Callable,
        *,
        name: str = "",
        platform: str = "",
        description: str = "",
        args: tuple = (),
        kwargs: Optional[dict] = None,
        max_retries: int = 3,
        enabled: bool = True,
    ) -> ScheduledTask:
        """Add an hourly task.

        Args:
            task_id: Unique task identifier.
            callback: Function to execute.
            name: Human-readable name.
            platform: Platform name.
            description: Task description.
            args: Positional args for callback.
            kwargs: Keyword args for callback.
            max_retries: Max retry attempts.
            enabled: Whether task is enabled.

        Returns:
            The created ScheduledTask.
        """
        task = ScheduledTask(
            task_id=task_id,
            name=name or task_id,
            frequency=ScheduleFrequency.HOURLY,
            callback=callback,
            args=args,
            kwargs=kwargs or {},
            enabled=enabled,
            max_retries=max_retries,
            platform=platform,
            description=description,
            next_run=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        self._tasks[task_id] = task
        logger.info(f"Added hourly task: {task_id}")
        return task

    def add_weekly(
        self,
        task_id: str,
        day: int,
        time_str: str,
        callback: Callable,
        *,
        name: str = "",
        platform: str = "",
        description: str = "",
        args: tuple = (),
        kwargs: Optional[dict] = None,
        max_retries: int = 3,
        enabled: bool = True,
    ) -> ScheduledTask:
        """Add a weekly task.

        Args:
            task_id: Unique task identifier.
            day: Day of week (0=Monday, 6=Sunday).
            time_str: Time to run (HH:MM format).
            callback: Function to execute.
            name: Human-readable name.
            platform: Platform name.
            description: Task description.
            args: Positional args for callback.
            kwargs: Keyword args for callback.
            max_retries: Max retry attempts.
            enabled: Whether task is enabled.

        Returns:
            The created ScheduledTask.
        """
        task = ScheduledTask(
            task_id=task_id,
            name=name or task_id,
            frequency=ScheduleFrequency.WEEKLY,
            target_time=time_str,
            callback=callback,
            args=args,
            kwargs=kwargs or {},
            enabled=enabled,
            max_retries=max_retries,
            platform=platform,
            description=description,
            next_run=self._calculate_next_weekly(day, time_str),
        )
        self._tasks[task_id] = task
        logger.info(f"Added weekly task: {task_id} on day {day} at {time_str}")
        return task

    def add_custom(
        self,
        task_id: str,
        interval_seconds: float,
        callback: Callable,
        *,
        name: str = "",
        platform: str = "",
        description: str = "",
        args: tuple = (),
        kwargs: Optional[dict] = None,
        max_retries: int = 3,
        enabled: bool = True,
    ) -> ScheduledTask:
        """Add a task with custom interval.

        Args:
            task_id: Unique task identifier.
            interval_seconds: Interval between runs in seconds.
            callback: Function to execute.
            name: Human-readable name.
            platform: Platform name.
            description: Task description.
            args: Positional args for callback.
            kwargs: Keyword args for callback.
            max_retries: Max retry attempts.
            enabled: Whether task is enabled.

        Returns:
            The created ScheduledTask.
        """
        task = ScheduledTask(
            task_id=task_id,
            name=name or task_id,
            frequency=ScheduleFrequency.CUSTOM,
            callback=callback,
            args=args,
            kwargs=kwargs or {},
            enabled=enabled,
            max_retries=max_retries,
            platform=platform,
            description=description,
            next_run=datetime.now(timezone.utc) + timedelta(seconds=interval_seconds),
            metadata={"interval_seconds": interval_seconds},
        )
        self._tasks[task_id] = task
        logger.info(f"Added custom task: {task_id} (every {interval_seconds}s)")
        return task

    def remove_task(self, task_id: str) -> bool:
        """Remove a scheduled task.

        Args:
            task_id: Task identifier.

        Returns:
            True if task was removed.
        """
        if task_id in self._tasks:
            del self._tasks[task_id]
            logger.info(f"Removed task: {task_id}")
            return True
        return False

    def enable_task(self, task_id: str) -> bool:
        """Enable a task.

        Args:
            task_id: Task identifier.

        Returns:
            True if task was enabled.
        """
        if task_id in self._tasks:
            self._tasks[task_id].enabled = True
            return True
        return False

    def disable_task(self, task_id: str) -> bool:
        """Disable a task.

        Args:
            task_id: Task identifier.

        Returns:
            True if task was disabled.
        """
        if task_id in self._tasks:
            self._tasks[task_id].enabled = False
            return True
        return False

    def get_task(self, task_id: str) -> Optional[ScheduledTask]:
        """Get a task by ID.

        Args:
            task_id: Task identifier.

        Returns:
            The ScheduledTask, or None if not found.
        """
        return self._tasks.get(task_id)

    def get_all_tasks(self) -> list[ScheduledTask]:
        """Get all scheduled tasks.

        Returns:
            List of all tasks.
        """
        return list(self._tasks.values())

    def get_due_tasks(self) -> list[ScheduledTask]:
        """Get tasks that are due for execution.

        Returns:
            List of due tasks.
        """
        return [t for t in self._tasks.values() if t.is_due]

    def run_task_now(self, task_id: str) -> Optional[ExecutionLog]:
        """Run a task immediately.

        Args:
            task_id: Task identifier.

        Returns:
            Execution log, or None if task not found.
        """
        task = self._tasks.get(task_id)
        if not task:
            logger.error(f"Task not found: {task_id}")
            return None
        return self._execute_task(task)

    def start(self) -> None:
        """Start the scheduler in a background thread."""
        if self._running:
            logger.warning("Scheduler already running")
            return

        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        logger.info("Scheduler started")

    def stop(self) -> None:
        """Stop the scheduler."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=10)
        self._save_state()
        logger.info("Scheduler stopped")

    def get_execution_log(
        self,
        task_id: Optional[str] = None,
        limit: int = 100,
    ) -> list[ExecutionLog]:
        """Get execution log.

        Args:
            task_id: Optional filter by task ID.
            limit: Max entries to return.

        Returns:
            List of execution logs.
        """
        logs = self._execution_log
        if task_id:
            logs = [l for l in logs if l.task_id == task_id]
        return logs[-limit:]

    def get_summary(self) -> dict:
        """Get scheduler summary.

        Returns:
            Summary dict.
        """
        tasks = list(self._tasks.values())
        return {
            "total_tasks": len(tasks),
            "enabled_tasks": sum(1 for t in tasks if t.enabled),
            "disabled_tasks": sum(1 for t in tasks if not t.enabled),
            "due_now": len(self.get_due_tasks()),
            "total_executions": len(self._execution_log),
            "tasks": [t.to_dict() for t in tasks],
        }

    def export_state(self, path: str) -> None:
        """Export scheduler state to JSON.

        Args:
            path: File path to save.
        """
        state = {
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "tasks": {k: v.to_dict() for k, v in self._tasks.items()},
            "execution_log": [l.to_dict() for l in self._execution_log[-100:]],
        }
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps(state, indent=2, default=str))
        logger.info(f"Exported state to {path}")

    # ─── Private Methods ─────────────────────────────────────────

    def _run_loop(self) -> None:
        """Main scheduler loop (runs in thread)."""
        logger.info("Scheduler loop started")
        while self._running:
            try:
                due_tasks = self.get_due_tasks()
                for task in due_tasks:
                    if not self._running:
                        break
                    self._execute_task(task)
                self._save_state()
            except Exception as e:
                logger.error(f"Scheduler loop error: {e}")
            time.sleep(self.config.check_interval)  # TODO: convert to async

    async def _async_run_loop(self) -> None:
        """Async scheduler loop — uses non-blocking sleep."""
        logger.info("Async scheduler loop started")
        while self._running:
            try:
                due_tasks = self.get_due_tasks()
                for task in due_tasks:
                    if not self._running:
                        break
                    self._execute_task(task)
                self._save_state()
            except Exception as e:
                logger.error(f"Scheduler loop error: {e}")
            await asyncio.sleep(self.config.check_interval)

    def _execute_task(self, task: ScheduledTask) -> ExecutionLog:
        """Execute a single task."""
        log = ExecutionLog(
            task_id=task.task_id,
            started_at=datetime.now(timezone.utc),
        )

        if not task.callback:
            log.status = TaskExecutionStatus.SKIPPED
            log.error = "No callback defined"
            self._execution_log.append(log)
            return log

        logger.info(f"Executing task: {task.name}")
        task.last_status = TaskExecutionStatus.RUNNING

        for attempt in range(task.max_retries):
            try:
                start = time.time()
                result = task.callback(*task.args, **task.kwargs)
                duration = time.time() - start

                log.status = TaskExecutionStatus.SUCCESS
                log.result = result
                log.duration_seconds = duration
                log.finished_at = datetime.now(timezone.utc)

                task.last_run = datetime.now(timezone.utc)
                task.last_status = TaskExecutionStatus.SUCCESS
                task.total_runs += 1
                task.total_successes += 1
                task.consecutive_failures = 0
                task.next_run = self._calculate_next_run(
                    task.frequency, task.target_time
                )

                logger.info(f"Task {task.name} completed in {duration:.1f}s")
                break

            except Exception as e:
                logger.warning(
                    f"Task {task.name} failed (attempt {attempt + 1}): {e}"
                )
                if attempt < task.max_retries - 1:
                    time.sleep(task.retry_delay)  # TODO: convert to async

                log.status = TaskExecutionStatus.FAILED
                log.error = str(e)
                log.finished_at = datetime.now(timezone.utc)

                task.last_status = TaskExecutionStatus.FAILED
                task.consecutive_failures += 1
                task.total_runs += 1

        self._execution_log.append(log)
        self._log_execution(log)
        return log

    async def _async_execute_task(self, task: ScheduledTask) -> ExecutionLog:
        """Async version — uses non-blocking sleep for retries."""
        log = ExecutionLog(
            task_id=task.task_id,
            started_at=datetime.now(timezone.utc),
        )

        if not task.callback:
            log.status = TaskExecutionStatus.SKIPPED
            log.error = "No callback defined"
            self._execution_log.append(log)
            return log

        logger.info(f"Executing task (async): {task.name}")
        task.last_status = TaskExecutionStatus.RUNNING

        for attempt in range(task.max_retries):
            try:
                start = time.time()
                result = task.callback(*task.args, **task.kwargs)
                duration = time.time() - start

                log.status = TaskExecutionStatus.SUCCESS
                log.result = result
                log.duration_seconds = duration
                log.finished_at = datetime.now(timezone.utc)

                task.last_run = datetime.now(timezone.utc)
                task.last_status = TaskExecutionStatus.SUCCESS
                task.total_runs += 1
                task.total_successes += 1
                task.consecutive_failures = 0
                task.next_run = self._calculate_next_run(
                    task.frequency, task.target_time
                )

                logger.info(f"Task {task.name} completed in {duration:.1f}s")
                break

            except Exception as e:
                logger.warning(
                    f"Task {task.name} failed (attempt {attempt + 1}): {e}"
                )
                if attempt < task.max_retries - 1:
                    await asyncio.sleep(task.retry_delay)

                log.status = TaskExecutionStatus.FAILED
                log.error = str(e)
                log.finished_at = datetime.now(timezone.utc)

                task.last_status = TaskExecutionStatus.FAILED
                task.consecutive_failures += 1
                task.total_runs += 1

        self._execution_log.append(log)
        self._log_execution(log)
        return log

    async def start_async(self) -> None:
        """Start the scheduler as an async task (non-blocking sleep)."""
        if self._running:
            logger.warning("Scheduler already running")
            return
        self._running = True
        logger.info("Async scheduler started")
        await self._async_run_loop()

    def _calculate_next_run(
        self, frequency: ScheduleFrequency, time_str: str = "00:00"
    ) -> datetime:
        """Calculate next run time."""
        now = datetime.now(timezone.utc)
        hour, minute = 0, 0
        if ":" in time_str:
            parts = time_str.split(":")
            hour = int(parts[0])
            minute = int(parts[1])

        if frequency == ScheduleFrequency.DAILY:
            next_run = now.replace(
                hour=hour, minute=minute, second=0, microsecond=0
            )
            if next_run <= now:
                next_run += timedelta(days=1)
            return next_run

        elif frequency == ScheduleFrequency.HOURLY:
            return now + timedelta(hours=1)

        elif frequency == ScheduleFrequency.CUSTOM:
            interval = 3600  # default 1 hour
            return now + timedelta(seconds=interval)

        return now + timedelta(hours=1)

    def _calculate_next_weekly(self, day: int, time_str: str) -> datetime:
        """Calculate next weekly run time."""
        now = datetime.now(timezone.utc)
        hour, minute = 0, 0
        if ":" in time_str:
            parts = time_str.split(":")
            hour = int(parts[0])
            minute = int(parts[1])

        # Calculate days until target day
        current_day = now.weekday()
        days_ahead = day - current_day
        if days_ahead <= 0:
            days_ahead += 7

        next_run = now + timedelta(days=days_ahead)
        return next_run.replace(
            hour=hour, minute=minute, second=0, microsecond=0
        )

    def _log_execution(self, log: ExecutionLog) -> None:
        """Log execution to file if configured."""
        if not self.config.log_path:
            return
        try:
            path = Path(self.config.log_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "a") as f:
                f.write(json.dumps(log.to_dict(), default=str) + "\n")
        except Exception as e:
            logger.warning(f"Failed to write log: {e}")

    def _save_state(self) -> None:
        """Save scheduler state."""
        if not self.config.state_path:
            return
        try:
            state = {
                "tasks": {k: v.to_dict() for k, v in self._tasks.items()},
                "saved_at": datetime.now(timezone.utc).isoformat(),
            }
            path = Path(self.config.state_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(state, indent=2, default=str))
        except Exception as e:
            logger.warning(f"Failed to save state: {e}")

    def _load_state(self) -> None:
        """Load scheduler state from file."""
        if not self.config.state_path:
            return
        path = Path(self.config.state_path)
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text())
            logger.info(f"Loaded scheduler state: {len(data.get('tasks', {}))} tasks")
        except Exception as e:
            logger.warning(f"Failed to load state: {e}")
