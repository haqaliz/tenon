"""The proof plan: the stages the runner executes, each an optional command."""

from dataclasses import dataclass
from typing import Sequence


def _command(value: Sequence[str]) -> tuple[str, ...]:
    if isinstance(value, str):
        raise ValueError("command must be a sequence of arguments, not a string")
    return tuple(value or ())


@dataclass(frozen=True, slots=True)
class ProofPlan:
    """The configured checks, from the weakest stage to the strongest."""

    tests: tuple[str, ...] = ()
    characterize: tuple[str, ...] = ()
    replay: tuple[str, ...] = ()
    build: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in ("tests", "characterize", "replay", "build"):
            object.__setattr__(self, name, _command(getattr(self, name)))

    def is_empty(self) -> bool:
        return not (self.tests or self.characterize or self.replay or self.build)
