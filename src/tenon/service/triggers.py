"""Parse the operator's event-to-bundle mapping for webhook-triggered runs."""

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from .api import resolve_bundle


@dataclass(frozen=True, slots=True)
class Trigger:
    """One GitHub event/action and the registered bundle it queues."""

    event: str
    action: str | None
    bundle: str


def _token(value: str, label: str, source: str) -> str:
    """One non-empty, whitespace-free token, named with the trigger value."""
    text = value.strip() if isinstance(value, str) else ""
    if not text or text.split() != [text]:
        raise ValueError(
            f"trigger {source!r}: {label} must be a non-empty token"
        )
    return text


# Spec AC1/AC2: EVENT[.ACTION]=BUNDLE, with the bundle confined to --bundles.
def parse_trigger(value: str, bundles: Path) -> Trigger:
    key, separator, bundle = value.partition("=")
    if not separator:
        raise ValueError(f"trigger must be EVENT[.ACTION]=BUNDLE: {value!r}")
    event, dot, action = key.partition(".")
    event = _token(event, "event", value)
    action = _token(action, "action", value) if dot else None
    name = _token(bundle, "bundle", value)
    if resolve_bundle(bundles, name) is None:
        raise ValueError(
            f"{value!r}: bundle is not a .json file under the bundle directory"
        )
    return Trigger(event, action, name)


# Spec AC3: an actionless and an action-specific trigger for the same event coexist.
def parse_triggers(
    values: Sequence[str], bundles: Path
) -> dict[tuple[str, str | None], str]:
    triggers: dict[tuple[str, str | None], str] = {}
    for value in values:
        trigger = parse_trigger(value, bundles)
        key = (trigger.event, trigger.action)
        if key in triggers:
            label = trigger.event
            if trigger.action is not None:
                label = f"{trigger.event}.{trigger.action}"
            raise ValueError(f"duplicate trigger: {label}")
        triggers[key] = trigger.bundle
    return triggers
