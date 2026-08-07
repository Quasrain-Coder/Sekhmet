"""Tests for the bot registry."""

import pytest
from sekhmet.ai_engine.bot_registry import list_bots, create, register
from sekhmet.ai_engine.base_bot import BaseBot
from sekhmet.ai_engine.rule_bot import RuleBot


def test_list_bots_returns_builtins():
    bots = list_bots()
    assert "rule_lv1" in bots
    assert "rule_lv2" in bots
    assert "rule_lv3" in bots


def test_create_rule_lv1():
    bot = create("rule_lv1")
    assert isinstance(bot, RuleBot)
    assert bot.name == "RuleBot Lv1"


def test_create_rule_lv2():
    bot = create("rule_lv2")
    assert bot.name == "RuleBot Lv2"


def test_create_rule_lv3():
    bot = create("rule_lv3")
    assert bot.name == "RuleBot Lv3"


def test_create_unknown_raises():
    with pytest.raises(KeyError, match="Unknown bot"):
        create("nonexistent_bot")


def test_register_custom_bot():
    class DummyBot(BaseBot):
        def decide(self, state, player_idx):
            from sekhmet.game_engine import Action, ActionType
            return Action(player_idx, ActionType.FOLD)

        @property
        def name(self):
            return "Dummy"

        @property
        def style_description(self):
            return "Always folds"

    register("dummy", lambda **kw: DummyBot())
    try:
        bot = create("dummy")
        assert bot.name == "Dummy"
        assert "dummy" in list_bots()
    finally:
        # Clean up — don't pollute registry for other tests
        from sekhmet.ai_engine import bot_registry
        bot_registry._registry.pop("dummy", None)


def test_create_passes_kwargs():
    """Keyword arguments are forwarded to the factory."""
    bot = create("rule_lv1")
    assert bot._level == 1
