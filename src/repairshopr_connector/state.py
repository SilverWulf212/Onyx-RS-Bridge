"""
State Management for Checkpoint/Resume

Enables crash recovery by persisting sync state to disk.
If a sync fails mid-way, it can resume from the last checkpoint.
"""

import json
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import structlog

logger = structlog.get_logger(__name__)


@dataclass
class SyncCheckpoint:
    """
    Checkpoint state for crash recovery.

    Tracks progress of each entity type independently,
    allowing partial resumes.
    """
    # Timestamps of last successful full sync
    last_full_sync: datetime | None = None

    # Timestamps of last successful poll
    last_poll: datetime | None = None

    # Entity-specific progress (for crash recovery mid-sync)
    tickets_page: int = 0
    tickets_seen_ids: set[int] = field(default_factory=set)
    tickets_complete: bool = False

    customers_page: int = 0
    customers_seen_ids: set[int] = field(default_factory=set)
    customers_complete: bool = False

    assets_page: int = 0
    assets_seen_ids: set[int] = field(default_factory=set)
    assets_complete: bool = False

    invoices_page: int = 0
    invoices_seen_ids: set[int] = field(default_factory=set)
    invoices_complete: bool = False

    # Sync metadata
    sync_started_at: datetime | None = None
    sync_type: str = ""  # "full" or "poll"
    documents_processed: int = 0
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dict."""
        return {
            "last_full_sync": self.last_full_sync.isoformat() if self.last_full_sync else None,
            "last_poll": self.last_poll.isoformat() if self.last_poll else None,
            "tickets_page": self.tickets_page,
            "tickets_seen_ids": list(self.tickets_seen_ids),
            "tickets_complete": self.tickets_complete,
            "customers_page": self.customers_page,
            "customers_seen_ids": list(self.customers_seen_ids),
            "customers_complete": self.customers_complete,
            "assets_page": self.assets_page,
            "assets_seen_ids": list(self.assets_seen_ids),
            "assets_complete": self.assets_complete,
            "invoices_page": self.invoices_page,
            "invoices_seen_ids": list(self.invoices_seen_ids),
            "invoices_complete": self.invoices_complete,
            "sync_started_at": self.sync_started_at.isoformat() if self.sync_started_at else None,
            "sync_type": self.sync_type,
            "documents_processed": self.documents_processed,
            "errors": self.errors[-100:],  # Keep last 100 errors
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SyncCheckpoint":
        """Create from JSON dict."""
        def parse_dt(val: str | None) -> datetime | None:
            if val:
                return datetime.fromisoformat(val)
            return None

        return cls(
            last_full_sync=parse_dt(data.get("last_full_sync")),
            last_poll=parse_dt(data.get("last_poll")),
            tickets_page=data.get("tickets_page", 0),
            tickets_seen_ids=set(data.get("tickets_seen_ids", [])),
            tickets_complete=data.get("tickets_complete", False),
            customers_page=data.get("customers_page", 0),
            customers_seen_ids=set(data.get("customers_seen_ids", [])),
            customers_complete=data.get("customers_complete", False),
            assets_page=data.get("assets_page", 0),
            assets_seen_ids=set(data.get("assets_seen_ids", [])),
            assets_complete=data.get("assets_complete", False),
            invoices_page=data.get("invoices_page", 0),
            invoices_seen_ids=set(data.get("invoices_seen_ids", [])),
            invoices_complete=data.get("invoices_complete", False),
            sync_started_at=parse_dt(data.get("sync_started_at")),
            sync_type=data.get("sync_type", ""),
            documents_processed=data.get("documents_processed", 0),
            errors=data.get("errors", []),
        )

    def reset_for_new_sync(self, sync_type: str) -> None:
        """Reset progress tracking for a new sync."""
        self.sync_started_at = datetime.now(timezone.utc)
        self.sync_type = sync_type
        self.documents_processed = 0
        self.errors = []

        # Reset entity progress
        self.tickets_page = 0
        self.tickets_seen_ids = set()
        self.tickets_complete = False
        self.customers_page = 0
        self.customers_seen_ids = set()
        self.customers_complete = False
        self.assets_page = 0
        self.assets_seen_ids = set()
        self.assets_complete = False
        self.invoices_page = 0
        self.invoices_seen_ids = set()
        self.invoices_complete = False

    def mark_complete(self) -> None:
        """Mark current sync as complete."""
        now = datetime.now(timezone.utc)
        if self.sync_type == "full":
            self.last_full_sync = now
        else:
            self.last_poll = now


class StateManager:
    """
    Manages sync state persistence for checkpoint/resume.

    Saves state to a JSON file after each batch, enabling
    crash recovery without re-processing everything.

    Usage:
        state_mgr = StateManager("/path/to/state.json")
        checkpoint = state_mgr.load()

        # Process data...
        checkpoint.documents_processed += len(batch)
        state_mgr.save(checkpoint)

        # On completion
        checkpoint.mark_complete()
        state_mgr.save(checkpoint)
    """

    def __init__(self, state_file: str | Path | None = None):
        """
        Initialize state manager.

        Args:
            state_file: Path to state file. If None, uses default location.
        """
        if state_file is None:
            # Default: ~/.onyx-rs-bridge/state.json
            state_dir = Path.home() / ".onyx-rs-bridge"
            state_dir.mkdir(exist_ok=True)
            state_file = state_dir / "state.json"

        self.state_file = Path(state_file)
        self._log = logger.bind(state_file=str(self.state_file))

    def load(self) -> SyncCheckpoint:
        """
        Load state from disk, or return fresh state if none exists.
        """
        if not self.state_file.exists():
            self._log.info("No existing state file, starting fresh")
            return SyncCheckpoint()

        try:
            with open(self.state_file, "r") as f:
                data = json.load(f)
            checkpoint = SyncCheckpoint.from_dict(data)
            self._log.info(
                "Loaded existing state",
                last_full_sync=checkpoint.last_full_sync,
                last_poll=checkpoint.last_poll,
                in_progress=checkpoint.sync_type if checkpoint.sync_started_at else None,
            )
            return checkpoint
        except Exception as e:
            self._log.warning("Failed to load state, starting fresh", error=str(e))
            return SyncCheckpoint()

    def save(self, checkpoint: SyncCheckpoint) -> None:
        """
        Save state to disk.

        Uses atomic write (write to temp, then rename) to prevent corruption.
        """
        try:
            # Write to temp file first
            temp_file = self.state_file.with_suffix(".tmp")
            with open(temp_file, "w") as f:
                json.dump(checkpoint.to_dict(), f, indent=2)

            # Atomic rename
            temp_file.rename(self.state_file)

            self._log.debug(
                "Saved state",
                documents_processed=checkpoint.documents_processed,
            )
        except Exception as e:
            self._log.error("Failed to save state", error=str(e))
            raise

    def clear(self) -> None:
        """Delete state file (for testing or reset)."""
        if self.state_file.exists():
            self.state_file.unlink()
            self._log.info("Cleared state file")

    def needs_full_sync(self, checkpoint: SyncCheckpoint, max_age_hours: int = 24) -> bool:
        """
        Determine if a full sync is needed.

        Returns True if:
        - No previous full sync
        - Last full sync was more than max_age_hours ago
        - Previous sync was interrupted
        """
        if checkpoint.last_full_sync is None:
            return True

        if checkpoint.sync_started_at and not self._is_sync_complete(checkpoint):
            # Previous sync was interrupted
            self._log.warning("Previous sync was interrupted, needs full sync")
            return True

        age = datetime.now(timezone.utc) - checkpoint.last_full_sync
        if age.total_seconds() > max_age_hours * 3600:
            return True

        return False

    def _is_sync_complete(self, checkpoint: SyncCheckpoint) -> bool:
        """Check if previous sync completed successfully."""
        return (
            checkpoint.tickets_complete and
            checkpoint.customers_complete and
            checkpoint.assets_complete
        )
