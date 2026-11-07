"""The corpus record: one benchmark run with a deterministic identity."""

import json
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from hashlib import sha256


class Outcome(StrEnum):
    """What a human decided happened to the change, before anything is merged."""

    PENDING = "PENDING"
    MERGED = "MERGED"
    REJECTED = "REJECTED"
    CLOSED = "CLOSED"
    INCIDENT = "INCIDENT"
    LOCAL_ONLY = "LOCAL_ONLY"


def _canonical_json(payload: object) -> str:
    return json.dumps(
        payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )


def record_id(repo: str, commit: str, change: dict, proposal: dict) -> str:
    """The first 12 hex of the canonical run identity; the outcome is not in it."""
    payload = {
        "repo": repo,
        "commit": commit,
        "change": change,
        "proposal": proposal.get("diff", ""),
    }
    return sha256(_canonical_json(payload).encode("utf-8")).hexdigest()[:12]


@dataclass(frozen=True, slots=True)
class CorpusRecord:
    """One recorded run: what changed, what proved it, and what a human decided."""

    id: str
    repo: str
    commit: str
    change: dict
    proposal: dict
    proof: dict
    pr: dict | None
    outcome: Outcome
    recorded: str
    outcome_url: str | None = None
    notes: str = ""
    evidence: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.repo, str) or not self.repo:
            raise ValueError("repo must be a non-empty string")
        if not isinstance(self.commit, str) or not self.commit:
            raise ValueError("commit must be a non-empty string")
        for name in ("change", "proposal", "proof"):
            if not isinstance(getattr(self, name), dict):
                raise ValueError(f"{name} must be a mapping")
        if self.pr is not None and not isinstance(self.pr, dict):
            raise ValueError("pr must be a mapping or None")
        for name in ("id", "recorded", "notes", "evidence"):
            if not isinstance(getattr(self, name), str):
                raise ValueError(f"{name} must be a string")
        if self.outcome_url is not None and not isinstance(self.outcome_url, str):
            raise ValueError("outcome_url must be a string or None")
        if (
            len(self.recorded) != 10
            or self.recorded[4] != "-"
            or self.recorded[7] != "-"
        ):
            raise ValueError("recorded must be YYYY-MM-DD")
        try:
            date.fromisoformat(self.recorded)
        except ValueError as exc:
            raise ValueError("recorded must be a real YYYY-MM-DD date") from exc
        outcome = self.outcome
        if not isinstance(outcome, Outcome):
            outcome = Outcome(outcome)
        object.__setattr__(self, "outcome", outcome)
        if self.id != record_id(self.repo, self.commit, self.change, self.proposal):
            raise ValueError(
                "id does not match record_id(repo, commit, change, proposal)"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "repo": self.repo,
            "commit": self.commit,
            "change": self.change,
            "proposal": self.proposal,
            "proof": self.proof,
            "pr": self.pr,
            "outcome": self.outcome.value,
            "recorded": self.recorded,
            "outcome_url": self.outcome_url,
            "notes": self.notes,
            "evidence": self.evidence,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "CorpusRecord":
        return cls(**data)

    def to_json(self) -> str:
        return _canonical_json(self.to_dict())
