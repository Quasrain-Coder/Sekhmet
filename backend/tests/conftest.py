import pytest
from sekhmet.config import GameConfig, ScoringWeights


@pytest.fixture(autouse=True)
async def _isolated_db(tmp_path):
    from sekhmet.models import db
    db.configure(f"sqlite+aiosqlite:///{tmp_path}/t.db")
    await db.init_db()
    yield
    await db.engine.dispose()


@pytest.fixture(autouse=True)
async def _isolated_tables():
    """Clear the in-memory table registry between tests.

    Table sessions accumulate otherwise (the manager only evicts idle
    rooms in production), and the creation cap makes late tests fail once
    the registry fills up.  Pending timer tasks from a previous test are
    harmless: they re-check ``get_table`` and no-op on a missing table.
    """
    from sekhmet.api import table_manager as tm
    tm._tables.clear()
    yield
    tm._tables.clear()


@pytest.fixture(autouse=True)
def _instant_bots():
    """Zero the bot think-delay for the whole suite.

    Bot actions now wait bot_action_delay_seconds (2s in production) before
    executing; most tests drive bots through after_action and would slow to
    a crawl.  The cadence itself is covered by a dedicated test that
    overrides the delay with monkeypatch.
    """
    from sekhmet.config import app_config
    app_config.game.bot_action_delay_seconds = 0.0
    yield
    app_config.game.bot_action_delay_seconds = 2.0


@pytest.fixture
def game_config():
    return GameConfig(default_stack=100, default_small_blind=1, default_big_blind=2)


@pytest.fixture
def scoring_weights():
    return ScoringWeights()
