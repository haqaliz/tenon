"""Token providers for the GitHub App remote."""

from dataclasses import dataclass
from typing import Protocol


class TokenProvider(Protocol):
    """Something that can produce a bearer token on demand."""

    def token(self) -> str: ...


@dataclass(frozen=True, slots=True)
class StaticToken:
    """A token minted elsewhere, for tests and short-lived operators."""

    value: str

    def __post_init__(self) -> None:
        if not self.value:
            raise ValueError("token must not be empty")

    def token(self) -> str:
        return self.value
