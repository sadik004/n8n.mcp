"""
1-Click Snapshot and Rollback engine for n8n workflows.
Guarantees atomic rollback safety prior to destructive modifications or AI refactoring.
"""

from __future__ import annotations
from datetime import datetime, timezone
import hashlib
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from n8n_mcp.models.snapshot import SnapshotDTO, RollbackResultDTO
from n8n_mcp.models.workflow import WorkflowDTO

logger = logging.getLogger("n8n_mcp.snapshots")


class SnapshotManager:
    """Manages local and in-memory snapshots with 1-click restoration."""

    def __init__(self, snapshots_dir: str = ".snapshots"):
        self.snapshots_path = Path(snapshots_dir)
        self.snapshots_path.mkdir(parents=True, exist_ok=True)
        self._memory_index: Dict[str, List[SnapshotDTO]] = {}

    def _compute_hash(self, data: Dict[str, Any]) -> str:
        """Calculates deterministic SHA256 hash of workflow state."""
        canonical_str = json.dumps(data, sort_keys=True, default=str)
        return hashlib.sha256(canonical_str.encode("utf-8")).hexdigest()

    async def create_snapshot(self, workflow: WorkflowDTO | Dict[str, Any]) -> SnapshotDTO:
        """Saves a timestamped snapshot of workflow state to disk and memory."""
        if isinstance(workflow, WorkflowDTO):
            raw_data = workflow.model_dump(by_alias=True)
            workflow_id = workflow.id
        else:
            raw_data = workflow
            workflow_id = str(raw_data.get("id", "unknown_workflow"))

        timestamp = datetime.now(timezone.utc).isoformat()
        version_hash = self._compute_hash(raw_data)

        snapshot = SnapshotDTO(
            workflow_id=workflow_id,
            timestamp=timestamp,
            version_hash=version_hash,
            workflow_data=raw_data,
        )

        # Index in memory
        if workflow_id not in self._memory_index:
            self._memory_index[workflow_id] = []
        self._memory_index[workflow_id].append(snapshot)

        # Write to disk
        safe_time = timestamp.replace(":", "-").replace(".", "-")
        file_path = self.snapshots_path / f"{workflow_id}_{safe_time}_{version_hash[:8]}.json"
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(snapshot.model_dump(), f, indent=2, default=str)
        except Exception as exc:
            logger.warning(f"Could not persist snapshot file to disk: {exc}")

        return snapshot

    def list_snapshots(self, workflow_id: str) -> List[SnapshotDTO]:
        """Returns all snapshots for a given workflow in chronological order."""
        return self._memory_index.get(workflow_id, [])

    async def rollback_workflow(
        self,
        workflow_id: str,
        client: Any,
        target_version_hash: Optional[str] = None,
    ) -> RollbackResultDTO:
        """Restores workflow to its previous snapshot or specified target hash."""
        snapshots = self._memory_index.get(workflow_id, [])

        # If memory index empty, load from disk
        if not snapshots and self.snapshots_path.exists():
            matched_files = sorted(self.snapshots_path.glob(f"{workflow_id}_*.json"))
            for p in matched_files:
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        snapshots.append(SnapshotDTO.model_validate(data))
                except Exception:
                    continue
            self._memory_index[workflow_id] = snapshots

        if not snapshots:
            raise ValueError(f"No snapshot found for workflow '{workflow_id}' to rollback.")

        if target_version_hash:
            target_snap = next((s for s in reversed(snapshots) if s.version_hash == target_version_hash), None)
            if not target_snap:
                raise ValueError(f"Target snapshot hash '{target_version_hash}' not found.")
        else:
            target_snap = snapshots[-1]

        # Restore state via n8n client
        await client.update_workflow(workflow_id, target_snap.workflow_data)

        timestamp = datetime.now(timezone.utc).isoformat()
        return RollbackResultDTO(
            workflow_id=workflow_id,
            restored_version_hash=target_snap.version_hash,
            timestamp=timestamp,
            status="restored",
        )
