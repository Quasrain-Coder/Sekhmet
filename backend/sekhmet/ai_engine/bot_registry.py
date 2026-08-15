"""Bot registry — factory for creating bot instances by name.

All bots are registered here so the API layer can instantiate them
without knowing the concrete class.
"""

from __future__ import annotations

from typing import Callable

from .base_bot import BaseBot, BotPersonality
from .gto_bot import GTOBot
from .rule_bot import RuleBot


_registry: dict[str, Callable[..., BaseBot]] = {}


def register(name: str, factory: Callable[..., BaseBot]) -> None:
    """Register a bot factory under *name*."""
    _registry[name] = factory


def create(name: str, **kwargs) -> BaseBot:
    """Create a bot instance by name.

    Raises
    ------
    KeyError
        If *name* is not registered.
    """
    if name not in _registry:
        raise KeyError(f"Unknown bot: {name}. Available: {list(_registry.keys())}")
    return _registry[name](**kwargs)


def list_bots() -> list[str]:
    """Return the names of all registered bots."""
    return sorted(_registry.keys())


# ---------------------------------------------------------------------------
# Register built-in bots
# ---------------------------------------------------------------------------

register("rule_lv1", lambda **kw: RuleBot(level=1, **kw))
register("rule_lv2", lambda **kw: RuleBot(level=2, **kw))
register("rule_lv3", lambda **kw: RuleBot(level=3, **kw))

register("gto_lv4", lambda **kw: GTOBot(**kw))
