"""Common binding and lifecycle contract for live platform connectors."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class LiveSourceBinding:
    id: str
    tenant_id: str
    session_id: str
    platform: str
    account_id: str
    username: str

    @classmethod
    def from_row(cls, row: dict) -> LiveSourceBinding:
        return cls(
            id=row["id"],
            tenant_id=row["tenant_id"],
            session_id=row["session_id"],
            platform=row["platform"],
            account_id=row["account_id"],
            username=row["username"],
        )


class LiveSource(Protocol):
    """A connector owns only its platform connection, never a game rule."""

    binding: LiveSourceBinding
    should_run: bool

    def start(self) -> None: ...

    def stop(self) -> None: ...
