import asyncio

import pytest
from sekhmet.config import GameConfig, ScoringWeights


@pytest.fixture(autouse=True)
async def _isolated_db(tmp_path):
    from sekhmet.models import db
    db.configure(f"sqlite+aiosqlite:///{tmp_path}/t.db")
    await db.init_db()
    yield
    # Teardown 三步走（2026-08-28 CI 抖动：teardown 挂 60s 触发 pytest-timeout）：
    # 1. 落库任务自然排空——cancel 中途杀 DB 操作会死在 SQLAlchemy asyncio
    #    connector 的 shield 段，孤儿任务永久悬挂，后续 await 全部卡死
    from sekhmet.models import recorder
    await recorder.drain_pending()
    # 2. 其余残留任务（action/grace timer 等纯内存任务）取消
    stray = [t for t in asyncio.all_tasks()
             if t is not asyncio.current_task() and not t.done()]
    for t in stray:
        t.cancel()
    if stray:
        await asyncio.gather(*stray, return_exceptions=True)
    # 3. dispose 加上界——测试隔离优先于优雅关闭；下一个测试用全新
    #    engine + 独立 sqlite 文件，丢弃残留连接无副作用
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
