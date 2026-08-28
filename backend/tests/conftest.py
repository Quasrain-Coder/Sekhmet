import asyncio

import pytest
from sekhmet.config import GameConfig, ScoringWeights


@pytest.fixture(autouse=True)
async def _isolated_db(tmp_path):
    from sekhmet.models import db
    db.configure(f"sqlite+aiosqlite:///{tmp_path}/t.db")
    await db.init_db()
    yield
    # dispose 加上界：慢 runner 上曾出现 teardown 挂 60s 触发 pytest-timeout
    # （CI 抖动，2026-08-28）。测试隔离优先于优雅关闭——下一个测试用
    # 全新 engine + 独立 sqlite 文件，丢弃残留连接无副作用。
    try:
        await asyncio.wait_for(db.engine.dispose(), timeout=10)
    except Exception:
        pass


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
    # 取消泄漏的后台任务（action timer / grace timer / fire-and-forget 落库
    # 等）。它们属于本测试的 event loop，不取消就会在 loop 关闭时被强制
    # 取消，与 dispose 竞争 aiosqlite 工作线程（慢 runner 上的 60s 挂起）。
    stray = [t for t in asyncio.all_tasks()
             if t is not asyncio.current_task() and not t.done()]
    for t in stray:
        t.cancel()
    if stray:
        await asyncio.gather(*stray, return_exceptions=True)


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
