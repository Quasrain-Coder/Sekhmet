"""Tests for table creation with room configuration."""

import pytest
from fastapi.testclient import TestClient

from sekhmet.main import app
from sekhmet.api import table_manager as tm
from sekhmet.api.table_manager import TableConfig
from sekhmet.game_engine.deck import Deck
from sekhmet.game_engine.action_processor import deal_new_hand
from sekhmet.game_engine.game_state import Player


async def test_create_table_with_custom_blinds():
    cfg = TableConfig(small_blind=10, big_blind=20, default_buyin=2000, max_seats=6)
    tid = await tm.create_table(cfg)
    session = await tm.get_table(tid)
    assert session is not None
    assert session.config.big_blind == 20
    assert session.n_seats == 6
    assert session.game_state.big_blind == 20


async def test_custom_blinds_reach_dealt_hand():
    cfg = TableConfig(small_blind=10, big_blind=20, default_buyin=2000)
    tid = await tm.create_table(cfg)
    await tm.sit_down(tid, 0, "A", buyin=2000)
    await tm.sit_down(tid, 1, "B", buyin=2000)
    await tm.start_hand(tid)
    session = await tm.get_table(tid)
    assert session is not None
    bets = {p.seat_idx: p.total_bet for p in session.game_state.players}
    assert sorted(bets.values()) == [10, 20]  # custom blinds posted


async def test_default_buyin_from_config():
    cfg = TableConfig(default_buyin=500)
    tid = await tm.create_table(cfg)
    await tm.sit_down(tid, 0, "A")  # no explicit buyin
    session = await tm.get_table(tid)
    assert session is not None
    assert session.game_state.player(0).stack == 500


def test_config_validation():
    with pytest.raises(ValueError, match="small_blind"):
        TableConfig(small_blind=10, big_blind=10)   # sb must be < bb
    with pytest.raises(ValueError, match="max_seats"):
        TableConfig(max_seats=10)
    with pytest.raises(ValueError, match="default_buyin"):
        TableConfig(big_blind=50, small_blind=25, default_buyin=200)  # < 20bb
    with pytest.raises(ValueError, match="Unknown"):
        TableConfig.from_dict({"blinds": 10})


def test_rest_create_table_with_config():
    client = TestClient(app)
    resp = client.post("/api/game/tables",
                       json={"small_blind": 10, "big_blind": 20, "default_buyin": 2000})
    assert resp.status_code == 200
    detail = client.get(f"/api/game/tables/{resp.json()['table_id']}")
    assert detail.json()["config"]["big_blind"] == 20


def test_rest_create_table_invalid_config_400():
    client = TestClient(app)
    resp = client.post("/api/game/tables", json={"small_blind": 20, "big_blind": 10})
    assert resp.status_code == 400


def test_rest_create_table_no_body_still_works():
    client = TestClient(app)
    resp = client.post("/api/game/tables")
    assert resp.status_code == 200


from sekhmet.game_engine.game_state import GamePhase


async def _table_with_bot(level: int) -> str:
    tid = await tm.create_table()
    await tm.sit_down(tid, 0, "Hero", buyin=200)
    await tm.sit_down(tid, 1, "Bot", buyin=200, is_human=False, bot_level=level)
    return tid


async def test_bot_level_drives_registry(monkeypatch):
    created: list[str] = []
    monkeypatch.setattr(
        "sekhmet.ai_engine.bot_registry.create",
        lambda name: created.append(name) or __import__(
            "sekhmet.ai_engine.rule_bot", fromlist=["RuleBot"]
        ).RuleBot(level=int(name[-1])),
    )
    tid = await _table_with_bot(3)
    await tm.start_hand(tid)
    await tm.auto_bot_actions(tid)
    assert "rule_lv3" in created


async def test_bot_level_default_is_2():
    tid = await tm.create_table()
    await tm.sit_down(tid, 0, "B", is_human=False)  # no level given
    session = await tm.get_table(tid)
    assert session is not None
    assert session.bot_levels[0] == 2


async def test_bot_level_out_of_range_rejected():
    tid = await tm.create_table()
    from sekhmet.game_engine import GameError
    with pytest.raises(GameError, match="bot_level"):
        await tm.sit_down(tid, 0, "B", is_human=False, bot_level=9)


async def test_table_info_shape():
    tid = await _table_with_bot(1)
    session = await tm.get_table(tid)
    info = tm.table_info(session)
    assert info["config"]["big_blind"] == 10
    seats = {s["seat_idx"]: s for s in info["seats"]}
    assert seats[0]["is_human"] is True and seats[0]["bot_level"] is None
    assert seats[1]["is_human"] is False and seats[1]["bot_level"] == 1
    assert seats[1]["stack"] == 200


def test_ws_kick_bot_and_reject_kicking_human():
    client = TestClient(app)
    tid = client.post("/api/game/tables").json()["table_id"]
    with (
        client.websocket_connect(f"/ws/{tid}") as ws1,
        client.websocket_connect(f"/ws/{tid}") as ws2,
    ):
        ws1.send_json({"type": "sit_down", "seat_idx": 0, "name": "Hero"})
        ws1.receive_json()                      # reclaim_token
        ws1.receive_json()                      # ws1's join broadcast
        ws2.send_json({"type": "sit_down", "seat_idx": 1, "name": "Friend"})
        ws2.receive_json()                      # reclaim_token
        ws2.receive_json()                      # ws2's join broadcast
        ws1.receive_json()                      # ws2's join, echoed to ws1

        # ws1 adds a bot, then kicks it
        ws1.send_json({"type": "sit_down", "seat_idx": 2, "name": "Bot",
                       "is_human": False, "bot_level": 3})
        ws1.receive_json(); ws2.receive_json()  # bot join broadcast
        ws1.send_json({"type": "stand_up", "seat_idx": 2})
        msg = ws1.receive_json()
        assert msg["type"] == "table_state"
        assert all(s["seat_idx"] != 2 for s in msg["seats"])
        ws2.receive_json()                      # drain kick broadcast on ws2

        # ws2 tries to kick the human at seat 0 — rejected
        ws2.send_json({"type": "stand_up", "seat_idx": 0})
        msg = ws2.receive_json()
        assert msg["type"] == "error"


def test_failed_sit_down_does_not_hijack_victim_broadcasts():
    """A rejected sit_down (seat taken) must not overwrite the real
    occupant's clients entry — the victim must keep receiving broadcasts."""
    client = TestClient(app)
    tid = client.post("/api/game/tables").json()["table_id"]
    with (
        client.websocket_connect(f"/ws/{tid}") as ws1,
        client.websocket_connect(f"/ws/{tid}") as ws2,
    ):
        # ws1 takes seat 0 (private reclaim_token + join broadcast)
        ws1.send_json({"type": "sit_down", "seat_idx": 0, "name": "Hero"})
        ws1.receive_json()                      # reclaim_token
        ws1.receive_json()                      # ws1's join broadcast

        # ws2 tries the same seat — rejected, must not touch clients
        ws2.send_json({"type": "sit_down", "seat_idx": 0, "name": "Hijacker"})
        msg = ws2.receive_json()
        assert msg["type"] == "error"

        # ws1 seats a bot at seat 1 → table_state broadcast must still
        # reach ws1 (pre-fix, clients[0] was hijacked by ws2's socket).
        ws1.send_json({"type": "sit_down", "seat_idx": 1, "name": "Bot",
                       "is_human": False})
        msg = ws1.receive_json()
        assert msg["type"] == "table_state"
        assert any(s["seat_idx"] == 1 for s in msg["seats"])


async def test_sit_down_mid_hand_parks_humans_blocks_bots():
    """Humans may sit mid-hand (parked until the next deal — joining
    game_state.players mid-hand would corrupt the betting round); bots are
    house furniture and stay blocked between hands only."""
    from sekhmet.game_engine import GameError
    tid = await tm.create_table()
    await tm.sit_down(tid, 0, "A", buyin=200)
    await tm.sit_down(tid, 1, "B", buyin=200)
    await tm.start_hand(tid)

    # human joins mid-hand — parked, never in the running hand
    await tm.sit_down(tid, 2, "Late", buyin=200)
    session = await tm.get_table(tid)
    assert [p.seat_idx for p in session.game_state.players] == [0, 1]
    assert session.pending_seats == {2}

    # bots still rejected mid-hand
    with pytest.raises(GameError, match="between hands"):
        await tm.sit_down(tid, 3, "Bot", buyin=200, is_human=False)


async def test_stats_accumulate_over_a_hand():
    """Hands/wins/net_chips tracked per seat and exposed via table_info."""
    tid = await tm.create_table()
    await tm.sit_down(tid, 0, "Hero", buyin=200)
    await tm.sit_down(tid, 1, "Bot", buyin=200, is_human=False)
    await tm.start_hand(tid)

    session = await tm.get_table(tid)
    assert session is not None
    sb_seat = session.game_state.current_player_idx  # HU: SB acts first

    # SB folds → BB wins the 15 pot (blinds 5+10)
    await tm.handle_player_action(tid, sb_seat, "FOLD")

    session = await tm.get_table(tid)
    info = tm.table_info(session)
    seats = {s["seat_idx"]: s for s in info["seats"]}
    assert seats[0]["hands"] == 1 and seats[1]["hands"] == 1
    winner = 1 - sb_seat
    loser = sb_seat
    assert seats[winner]["wins"] == 1 and seats[loser]["wins"] == 0
    assert seats[winner]["net_chips"] == 5    # 205 - 200
    assert seats[loser]["net_chips"] == -5    # 195 - 200


async def test_stats_cleared_on_stand_up():
    tid = await tm.create_table()
    await tm.sit_down(tid, 0, "Hero", buyin=200)
    await tm.sit_down(tid, 1, "Bot", buyin=200, is_human=False)
    await tm.stand_up(tid, 1)
    session = await tm.get_table(tid)
    assert session is not None
    assert 1 not in session.stats and 1 not in session.total_buyin


async def test_wins_and_hands_accumulate_over_multiple_hands():
    """Two fold-out hands: every seated player gains hands, winners gain wins."""
    tid = await tm.create_table()
    await tm.sit_down(tid, 0, "Hero", buyin=200)
    await tm.sit_down(tid, 1, "Bot", buyin=200, is_human=False)
    for _ in range(2):
        await tm.start_hand(tid)
        session = await tm.get_table(tid)
        sb = session.game_state.current_player_idx
        await tm.handle_player_action(tid, sb, "FOLD")
    session = await tm.get_table(tid)
    info = tm.table_info(session)
    assert sum(s["wins"] for s in info["seats"]) == 2
    assert sum(s["hands"] for s in info["seats"]) == 4


def test_ws_table_state_broadcast_on_hand_end():
    """Stats ride the table_state broadcast — it must follow hand_result,
    or the leaderboard would only refresh on sit/stand."""
    import random
    random.seed(7)
    client = TestClient(app)
    tid = client.post("/api/game/tables").json()["table_id"]
    with client.websocket_connect(f"/ws/{tid}") as ws:
        ws.send_json({"type": "sit_down", "seat_idx": 0, "name": "Hero", "buyin": 200})
        ws.send_json({"type": "sit_down", "seat_idx": 1, "name": "Bot", "buyin": 200,
                      "is_human": False})
        ws.send_json({"type": "start_hand"})

        saw_hand_result = False
        for _ in range(40):
            msg = ws.receive_json()
            if msg["type"] == "hand_result":
                saw_hand_result = True
                continue
            if saw_hand_result and msg["type"] == "table_state":
                seats = {s["seat_idx"]: s for s in msg["seats"]}
                assert sum(s["hands"] for s in seats.values()) == 2
                assert sum(s["wins"] for s in seats.values()) == 1
                return
            cur = msg.get("current_player_idx")
            if msg["type"] in ("game_state_update", "hand_start") and cur == 0:
                ws.send_json({"type": "player_action", "action": "FOLD"})
        raise AssertionError("no table_state followed the hand_result")


async def test_scooping_multiple_pots_counts_one_win():
    """A player winning main + side pot in one hand gets wins += 1, not +2."""
    from sekhmet.game_engine.deck import Card, Rank, Suit
    from sekhmet.game_engine.game_state import GameState, GamePhase, PotState
    from sekhmet.api.table_manager import PlayerStats, _resolve_showdown

    # Seat 0 all-in for 50; seat 1 put in 200 and holds the royal flush, so
    # the SAME player wins both the main pot (100) and the side pot (150).
    community = (Card(Rank.ACE, Suit.SPADES), Card(Rank.KING, Suit.SPADES),
                 Card(Rank.QUEEN, Suit.SPADES), Card(Rank.TWO, Suit.HEARTS),
                 Card(Rank.THREE, Suit.CLUBS))
    p0 = Player(name="Short", seat_idx=0, stack=0, is_all_in=True,
                hole_cards=(Card(Rank.FOUR, Suit.HEARTS), Card(Rank.FIVE, Suit.HEARTS)),
                current_bet=0, total_bet=50)
    p1 = Player(name="Big", seat_idx=1, stack=0, is_all_in=True,
                hole_cards=(Card(Rank.JACK, Suit.SPADES), Card(Rank.TEN, Suit.SPADES)),
                current_bet=0, total_bet=200)
    gs = GameState(phase=GamePhase.SHOWDOWN, players=(p0, p1),
                   community_cards=community, pot=PotState(main_pot=250))
    tid = await tm.create_table()
    session = await tm.get_table(tid)
    assert session is not None
    session.game_state = gs
    session.player_names = {0: "Short", 1: "Big"}
    session.stats = {0: PlayerStats(hands=1), 1: PlayerStats(hands=1)}
    session.total_buyin = {0: 50, 1: 200}

    result = _resolve_showdown(session)

    # seat 1 (royal flush) wins main 100 + side 150 → exactly ONE win recorded
    assert len(result["awards"]) == 2
    assert all(a["seat_idx"] == 1 for a in result["awards"])
    assert session.stats[1].wins == 1
    assert session.stats[0].wins == 0


# ---------------------------------------------------------------------------
# Rebuy (busted players top up between hands)
# ---------------------------------------------------------------------------


async def _bust_player(tid: str, seat: int) -> None:
    """直接构造 0 筹码状态（比真打一手牌快且确定）。"""
    session = await tm.get_table(tid)
    assert session is not None
    gs = session.game_state
    session.game_state = gs.with_players(tuple(
        type(p)(name=p.name, seat_idx=p.seat_idx, stack=0 if p.seat_idx == seat else p.stack,
                hole_cards=p.hole_cards, is_active=p.is_active, is_all_in=p.is_all_in,
                current_bet=p.current_bet, total_bet=p.total_bet, is_human=p.is_human)
        for p in gs.players
    ))


async def test_rebuy_success_when_busted():
    tid = await tm.create_table()
    await tm.sit_down(tid, 0, "Hero", buyin=200)
    await tm.sit_down(tid, 1, "Bot", buyin=200, is_human=False)
    await _bust_player(tid, 0)

    summary = await tm.rebuy(tid, 0, 500)

    session = await tm.get_table(tid)
    assert session is not None
    assert session.game_state.player(0).stack == 500
    assert session.total_buyin[0] == 700  # 200 + 500 → net_chips 语义保持
    seat0 = next(s for s in summary["seats"] if s["seat_idx"] == 0)
    assert seat0["stack"] == 500 and seat0["net_chips"] == -200


async def test_rebuy_rejected_with_chips():
    from sekhmet.game_engine import GameError
    tid = await tm.create_table()
    await tm.sit_down(tid, 0, "Hero", buyin=200)
    with pytest.raises(GameError, match="busted"):
        await tm.rebuy(tid, 0, 500)


async def test_rebuy_rejected_mid_hand():
    from sekhmet.game_engine import GameError
    tid = await tm.create_table()
    await tm.sit_down(tid, 0, "Hero", buyin=200)
    await tm.sit_down(tid, 1, "Bot", buyin=200, is_human=False)
    await tm.start_hand(tid)
    await _bust_player(tid, 0)
    with pytest.raises(GameError, match="mid-hand"):
        await tm.rebuy(tid, 0, 500)


async def test_rebuy_amount_bounds():
    from sekhmet.game_engine import GameError
    tid = await tm.create_table()  # blinds 5/10 → bounds [200, 2000]
    await tm.sit_down(tid, 0, "Hero", buyin=200)
    await _bust_player(tid, 0)
    with pytest.raises(GameError, match="20"):
        await tm.rebuy(tid, 0, 100)   # < 20bb
    with pytest.raises(GameError, match="200"):
        await tm.rebuy(tid, 0, 5000)  # > 200bb


# ---------------------------------------------------------------------------
# Disconnect grace + name-based reclaim + safe mid-hand removal
# ---------------------------------------------------------------------------


async def test_disconnect_marks_seat_and_keeps_player():
    tid = await tm.create_table()
    await tm.sit_down(tid, 0, "Hero", buyin=200)
    await tm.handle_disconnect(tid, 0)
    session = await tm.get_table(tid)
    assert session is not None
    assert 0 in session.player_names  # 座位保留
    info = tm.table_info(session)
    assert info["seats"][0]["connected"] is False


async def test_reclaim_by_name_restores_seat():
    tid = await tm.create_table()
    await tm.sit_down(tid, 0, "Hero", buyin=200)
    session = await tm.get_table(tid)
    assert session is not None
    token = session.reclaim_tokens[0]
    await tm.handle_disconnect(tid, 0)
    result = await tm.try_reclaim(tid, "Hero", token)
    assert result is not None
    seat = result[0]
    assert seat == 0
    session = await tm.get_table(tid)
    assert session is not None
    assert tm.table_info(session)["seats"][0]["connected"] is True
    assert await tm.try_reclaim(tid, "Stranger", token) is None


async def test_grace_expiry_between_hands_removes_seat(monkeypatch):
    import asyncio
    monkeypatch.setattr(tm.app_config.game, "disconnect_grace_seconds", 0.05)
    tid = await tm.create_table()
    await tm.sit_down(tid, 0, "Hero", buyin=200)
    await tm.handle_disconnect(tid, 0)
    await asyncio.sleep(0.15)
    session = await tm.get_table(tid)
    assert session is not None
    assert 0 not in session.player_names


async def test_grace_expiry_mid_hand_force_folds(monkeypatch):
    """掉线者在手牌中且轮到TA：宽限期满 → 自动 FOLD，手牌继续。"""
    import asyncio
    monkeypatch.setattr(tm.app_config.game, "disconnect_grace_seconds", 0.05)
    tid = await tm.create_table()
    await tm.sit_down(tid, 0, "Hero", buyin=200)
    await tm.sit_down(tid, 1, "Bot", buyin=200, is_human=False)
    await tm.start_hand(tid)
    session = await tm.get_table(tid)
    assert session is not None
    cur = session.game_state.current_player_idx  # HU: SB 先行动

    await tm.handle_disconnect(tid, cur)
    await asyncio.sleep(0.2)

    session = await tm.get_table(tid)
    assert session is not None
    gs = session.game_state
    # 掉线者已被强制弃牌 → 手牌结束（fold-out），对手赢得底池
    assert gs.phase == GamePhase.SHOWDOWN
    assert gs.player(cur).is_active is False
    assert cur not in session.player_names  # 身份映射已清
    # 手牌没有卡死：另一玩家筹码增加
    winner = 1 - cur
    assert gs.player(winner).stack > 200


async def test_grace_expiry_mid_hand_non_current_player(monkeypatch):
    """非当前行动者掉线过期：replace 手术标记 is_active=False，手牌继续。"""
    import asyncio
    monkeypatch.setattr(tm.app_config.game, "disconnect_grace_seconds", 0.05)
    tid = await tm.create_table()
    await tm.sit_down(tid, 0, "P0", buyin=200)
    await tm.sit_down(tid, 1, "P1", buyin=200)
    await tm.sit_down(tid, 2, "P2", buyin=200)
    await tm.start_hand(tid)
    session = await tm.get_table(tid)
    assert session is not None
    cur = session.game_state.current_player_idx
    target = next(s for s in (0, 1, 2) if s != cur)

    await tm.handle_disconnect(tid, target)
    await asyncio.sleep(0.2)

    session = await tm.get_table(tid)
    assert session is not None
    gs = session.game_state
    # 手牌仍在下注轮，未被快进；行动位置不变（证明走的是 replace 分支而非
    # 引擎 FOLD —— 后者会推进 current_player/phase）
    assert gs.phase == GamePhase.PREFLOP
    assert gs.current_player_idx == cur
    assert gs.player(target).is_active is False
    assert gs.player(target) in gs.players  # 壳留到手牌结束
    assert gs.pot.main_pot >= 15            # 已投盲注留在池中
    # 身份映射已清
    assert target not in session.player_names
    assert target not in session.stats
    assert target not in session.total_buyin


async def test_grace_expiry_replace_surgery_pays_survivor(monkeypatch):
    """非当前行动者掉线过期走 replace 手术，若此后只剩 1 名活跃玩家，
    必须立即进入 SHOWDOWN 并把底池判给幸存者 —— 否则幸存者再弃牌时
    n_active=0，底池蒸发。"""
    import asyncio
    monkeypatch.setattr(tm.app_config.game, "disconnect_grace_seconds", 0.05)
    tid = await tm.create_table()
    await tm.sit_down(tid, 0, "P0", buyin=200)
    await tm.sit_down(tid, 1, "P1", buyin=200)
    await tm.sit_down(tid, 2, "P2", buyin=200)
    await tm.start_hand(tid)

    session = await tm.get_table(tid)
    assert session is not None
    # 第一人 CALL 保持活跃，第二人 FOLD —— 之后活跃者 = {第一人, 第三人}
    first = session.game_state.current_player_idx
    await tm.handle_player_action(tid, first, "CALL")
    session = await tm.get_table(tid)
    second = session.game_state.current_player_idx
    await tm.handle_player_action(tid, second, "FOLD")
    session = await tm.get_table(tid)
    survivor = session.game_state.current_player_idx
    assert survivor != first and survivor != second
    assert session.game_state.phase == GamePhase.PREFLOP  # 手牌仍在进行

    # 掉线的是 first（非当前行动者）→ replace 手术分支
    await tm.handle_disconnect(tid, first)
    await asyncio.sleep(0.2)

    session = await tm.get_table(tid)
    gs = session.game_state
    assert gs.phase == GamePhase.SHOWDOWN
    # 底池守恒：三人总筹码不变（幸存者拿到了底池）
    assert sum(p.stack for p in gs.players) == 600
    assert gs.player(survivor).stack > 200 - session.config.big_blind


def test_ws_stand_up_mid_hand_rejected():
    """手牌进行中人类玩家 stand_up 自己的座位 → 报错且座位保留。
    （想离桌应直接关标签页，走断线宽限被 fold 出去。）"""
    import random
    random.seed(7)
    client = TestClient(app)
    tid = client.post("/api/game/tables").json()["table_id"]
    with client.websocket_connect(f"/ws/{tid}") as ws:
        ws.send_json({"type": "sit_down", "seat_idx": 0, "name": "Hero", "buyin": 200})
        ws.send_json({"type": "sit_down", "seat_idx": 1, "name": "Bot", "buyin": 200,
                      "is_human": False})
        ws.send_json({"type": "start_hand"})
        ws.send_json({"type": "stand_up"})  # 自己，手牌进行中
        ws.send_json({"type": "__ping__"})  # 未知消息必回 error ⇒ stand_up 已处理完
        saw_mid_hand_error = False
        for _ in range(40):
            msg = ws.receive_json()
            if msg["type"] == "error" and "mid-hand" in msg["message"]:
                saw_mid_hand_error = True
            if msg["type"] == "error" and "Unknown message type" in msg["message"]:
                break
        assert saw_mid_hand_error, "mid-hand stand_up was not rejected"
    # 座位仍在（未被从 game_state.players 中撕掉）
    detail = client.get(f"/api/game/tables/{tid}").json()
    assert any(s["seat_idx"] == 0 for s in detail["seats"])


def test_action_timeout_auto_folds_facing_bet(monkeypatch):
    """第二手牌人类是 SB/dealer，翻前第一个行动且面临下注
    （to_call = BB − SB > 0）→ 超时必须自动 FOLD 而非 CHECK。"""
    import random
    monkeypatch.setattr(tm.app_config.game, "action_timeout_seconds", 0.1)
    random.seed(7)
    client = TestClient(app)
    tid = client.post("/api/game/tables").json()["table_id"]
    with client.websocket_connect(f"/ws/{tid}") as ws:
        ws.send_json({"type": "sit_down", "seat_idx": 0, "name": "Hero", "buyin": 200})
        ws.send_json({"type": "sit_down", "seat_idx": 1, "name": "Bot", "buyin": 200,
                      "is_human": False})
        ws.send_json({"type": "start_hand"})

        # 第一手正常打完：轮到自己时 CHECK（无注）或 FOLD（有注）
        hand1_done = False
        for _ in range(60):
            msg = ws.receive_json()
            if msg["type"] == "hand_result":
                hand1_done = True
                break
            if msg["type"] in ("game_state_update", "hand_start") \
                    and msg.get("current_player_idx") == 0:
                me = next(p for p in msg["players"] if p["seat_idx"] == 0)
                to_call = msg["current_bet"] - me["current_bet"]
                ws.send_json({"type": "player_action",
                              "action": "CHECK" if to_call == 0 else "FOLD"})
        assert hand1_done, "hand 1 did not complete"

        # 第二手：人类 SB/dealer 翻前先行动且面临下注 —— 什么都不发，等超时
        ws.send_json({"type": "start_hand"})
        for _ in range(40):
            msg = ws.receive_json()
            if msg["type"] in ("game_state_update", "hand_result"):
                folds = [a for a in msg.get("round_history", [])
                         if a["seat"] == 0 and a["action"] == "FOLD"]
                if folds:
                    return  # 超时自动 FOLD 生效
            # 注意：绝不发送 player_action
        raise AssertionError("no timeout FOLD within 40 messages")


def test_action_timeout_auto_checks(monkeypatch):
    """轮到人类且迟迟不动 → 超时自动 CHECK（无注）/FOLD（有注）。"""
    import random
    monkeypatch.setattr(tm.app_config.game, "action_timeout_seconds", 0.1)
    random.seed(7)  # bot SB 跟注，人类 BB 获得 option（无注）
    client = TestClient(app)
    tid = client.post("/api/game/tables").json()["table_id"]
    with client.websocket_connect(f"/ws/{tid}") as ws:
        ws.send_json({"type": "sit_down", "seat_idx": 0, "name": "Hero", "buyin": 200})
        ws.send_json({"type": "sit_down", "seat_idx": 1, "name": "Bot", "buyin": 200,
                      "is_human": False})
        ws.send_json({"type": "start_hand"})
        # 人类不行动，等超时：应在若干消息内看到 seat 0 的自动行动
        for _ in range(40):
            msg = ws.receive_json()
            if msg["type"] in ("game_state_update", "hand_result"):
                auto = [a for a in msg.get("round_history", [])
                        if a["seat"] == 0 and a["action"] in ("CHECK", "FOLD")]
                if auto:
                    return  # 超时自动行动生效
            # 注意：绝不发送 player_action
        raise AssertionError("no auto action within 40 messages")


def test_all_in_runout_broadcasts_each_street(monkeypatch):
    """All-in then call → clients see FLOP(3) → TURN(4) → RIVER(5) → result."""
    monkeypatch.setattr(tm.app_config.game, "runout_delay_seconds", 0)
    client = TestClient(app)
    tid = client.post("/api/game/tables").json()["table_id"]
    with (
        client.websocket_connect(f"/ws/{tid}") as ws1,
        client.websocket_connect(f"/ws/{tid}") as ws2,
    ):
        ws1.send_json({"type": "sit_down", "seat_idx": 0, "name": "A", "buyin": 200})
        ws1.receive_json()
        ws2.send_json({"type": "sit_down", "seat_idx": 1, "name": "B", "buyin": 200})
        ws2.receive_json(); ws1.receive_json()
        ws1.send_json({"type": "start_hand"})

        # 谁被问到谁 ALL_IN，另一方 CALL（按实际 current_player_idx 驱动，
        # 不预设哪个座位先手——按钮每手推进，先手座位不确定）。
        sockets = {0: ws1, 1: ws2}
        while True:
            msg = ws1.receive_json()
            if msg.get("current_player_idx") in (0, 1):
                actor = msg["current_player_idx"]
                break
        caller_seat = 1 - actor
        sockets[actor].send_json({"type": "player_action", "action": "ALL_IN"})

        # 两个 socket 都要读到"轮到 caller"再行动，保证随后读板面时队列里
        # 没有 ALL_IN 那条旧广播（其 community_cards 仍为 0 张）。
        for ws in (ws1, ws2):
            while True:
                msg = ws.receive_json()
                if msg.get("current_player_idx") == caller_seat:
                    break
        sockets[caller_seat].send_json({"type": "player_action", "action": "CALL"})

        # 现在应逐街收到广播：3 张 → 4 张 → 5 张 → hand_result
        boards = []
        for _ in range(20):
            msg = ws1.receive_json()
            if msg["type"] == "game_state_update":
                boards.append(len(msg["community_cards"]))
                # dealer/SB/BB must ride every state broadcast, not just
                # hand_start — else the D badge vanishes after the first action
                assert msg["dealer_idx"] is not None
            if msg["type"] == "hand_result":
                break
        assert boards == [3, 4, 5]
        # 位置字段
        assert msg["sb_seat"] is not None and msg["bb_seat"] is not None
        assert msg["dealer_idx"] is not None


async def test_runout_expire_seat_race_pays_pot_once(monkeypatch):
    """断线宽限过期撞上 all-in runout：底池必须只结算一次。

    回归测试（pre-fix 红）：_expire_seat → after_action 会在第一个
    auto_bot_actions 循环睡在两条街之间时，再拉起第二个循环。两个循环都从
    过期快照 runout_step（街道重复），且后者用未结算的 SHOWDOWN 覆盖前者已
    结算的状态后再 _resolve_showdown 一次 —— 底池发两遍（两条 hand_result）。
    修复后由 session.lock 串行化：恰好一条 hand_result，筹码守恒。
    """
    import asyncio
    monkeypatch.setattr(tm.app_config.game, "runout_delay_seconds", 0.2)

    hand_results: list[dict] = []
    real_broadcast = tm.broadcast

    async def spy_broadcast(table_id, message):
        if message.get("type") == "hand_result":
            hand_results.append(message)
        await real_broadcast(table_id, message)

    monkeypatch.setattr(tm, "broadcast", spy_broadcast)

    tid = await tm.create_table()
    await tm.sit_down(tid, 0, "A", buyin=200)
    await tm.sit_down(tid, 1, "B", buyin=200)
    await tm.start_hand(tid)

    session = await tm.get_table(tid)
    assert session is not None
    cur = session.game_state.current_player_idx
    assert cur is not None
    await tm.handle_player_action(tid, cur, "ALL_IN")
    await tm.handle_player_action(tid, 1 - cur, "CALL")

    session = await tm.get_table(tid)
    gs = session.game_state
    assert gs.current_player_idx is None  # runout pending
    assert gs.phase == GamePhase.FLOP

    # 宽限过期在 runout 中途触发（座位全下中，走无手术分支 → after_action
    # 拉起第二个 bot 循环，与第一个交错）。
    session.disconnected.add(0)
    await asyncio.gather(
        tm.auto_bot_actions(tid),
        tm._expire_seat(tid, 0),
    )

    session = await tm.get_table(tid)
    gs = session.game_state
    assert gs.phase == GamePhase.SHOWDOWN
    # 底池恰好结算一次
    assert len(hand_results) == 1
    awards = hand_results[0]["showdown"]["awards"]
    assert sum(a["amount"] for a in awards) == 400
    # 筹码守恒：总筹码 400，不多不少
    assert sum(p.stack for p in gs.players) == 400


# ---------------------------------------------------------------------------
# Table ownership — first human owns the table; only owner starts/kicks
# ---------------------------------------------------------------------------


async def test_first_human_becomes_owner():
    tid = await tm.create_table()
    await tm.sit_down(tid, 2, "Bot", buyin=200, is_human=False)
    await tm.sit_down(tid, 0, "Hero", buyin=200)
    session = await tm.get_table(tid)
    assert session is not None
    assert session.owner_seat == 0  # bot 不当房主；第一个人类接任
    info = tm.table_info(session)
    owners = {s["seat_idx"]: s["is_owner"] for s in info["seats"]}
    assert owners == {0: True, 2: False}


async def test_owner_reassigned_on_removal():
    tid = await tm.create_table()
    await tm.sit_down(tid, 0, "Hero", buyin=200)
    await tm.sit_down(tid, 1, "Friend", buyin=200)
    await tm.stand_up(tid, 0)
    session = await tm.get_table(tid)
    assert session is not None
    assert session.owner_seat == 1
    await tm.stand_up(tid, 1)
    session = await tm.get_table(tid)
    assert session.owner_seat is None


def test_ws_non_owner_cannot_start_hand():
    client = TestClient(app)
    tid = client.post("/api/game/tables").json()["table_id"]
    with (
        client.websocket_connect(f"/ws/{tid}") as ws1,
        client.websocket_connect(f"/ws/{tid}") as ws2,
    ):
        ws1.send_json({"type": "sit_down", "seat_idx": 0, "name": "Owner"})
        ws1.receive_json(); ws1.receive_json()  # reclaim_token + join broadcast
        ws2.send_json({"type": "sit_down", "seat_idx": 1, "name": "Guest"})
        ws2.receive_json(); ws2.receive_json()  # reclaim_token + join broadcast
        ws1.receive_json()                      # guest join echoed to ws1
        ws2.send_json({"type": "start_hand"})
        err = ws2.receive_json()
        assert err["type"] == "error"
        assert "owner" in err["message"]
        # 房主可以发
        ws1.send_json({"type": "start_hand"})
        msg = ws1.receive_json()
        assert msg["type"] == "hand_start"


def test_ws_non_owner_cannot_kick_bot():
    client = TestClient(app)
    tid = client.post("/api/game/tables").json()["table_id"]
    with (
        client.websocket_connect(f"/ws/{tid}") as ws1,
        client.websocket_connect(f"/ws/{tid}") as ws2,
    ):
        ws1.send_json({"type": "sit_down", "seat_idx": 0, "name": "Owner"})
        ws1.receive_json(); ws1.receive_json()  # reclaim_token + join broadcast
        ws2.send_json({"type": "sit_down", "seat_idx": 1, "name": "Guest"})
        ws2.receive_json(); ws2.receive_json()  # reclaim_token + join broadcast
        ws1.receive_json()                      # guest join echoed to ws1
        ws1.send_json({"type": "sit_down", "seat_idx": 2, "name": "Bot", "is_human": False})
        ws1.receive_json(); ws2.receive_json()
        ws2.send_json({"type": "stand_up", "seat_idx": 2})
        err = ws2.receive_json()
        assert err["type"] == "error" and "owner" in err["message"]
        # 房主可以踢
        ws1.send_json({"type": "stand_up", "seat_idx": 2})
        msg = ws1.receive_json()
        assert msg["type"] == "table_state"
        assert all(s["seat_idx"] != 2 for s in msg["seats"])


def test_ws_spectator_cannot_kick_bot_on_ownerless_table():
    """无房主（纯 bot 桌）时，旁观者（未入座，my_seat=None）不能踢 bot。

    None != None 为 False，旧守卫 `my_seat != session.owner_seat` 会放行。
    """
    client = TestClient(app)
    tid = client.post("/api/game/tables").json()["table_id"]
    with client.websocket_connect(f"/ws/{tid}") as ws:
        # 旁观者连接直接坐一个 bot —— is_human=False 不会占据 my_seat，
        # 桌上无人类 → owner_seat=None。
        ws.send_json({"type": "sit_down", "seat_idx": 0, "name": "Bot", "is_human": False})
        # 旁观者不在 session.clients 中，收不到广播，无需 drain。
        ws.send_json({"type": "stand_up", "seat_idx": 0})
        # 先查 REST 确认 bot 仍在（修复前踢人成功且无回包，
        # 直接 receive 会永久阻塞）。
        seats = client.get(f"/api/game/tables/{tid}").json()["seats"]
        assert any(s["seat_idx"] == 0 for s in seats)
        err = ws.receive_json()
        assert err["type"] == "error" and "owner" in err["message"]


# ---------------------------------------------------------------------------
# Idle-room sweeper — touch refreshes activity, sweep closes stale rooms
# ---------------------------------------------------------------------------


async def test_touch_refreshes_activity():
    tid = await tm.create_table()
    session = await tm.get_table(tid)
    assert session is not None
    session.last_activity -= 100  # 手动老化
    await tm.touch(tid)
    import time
    assert time.monotonic() - session.last_activity < 5


async def test_sweep_removes_idle_room():
    import time
    tid = await tm.create_table()
    session = await tm.get_table(tid)
    assert session is not None
    session.last_activity = time.monotonic() - 3700  # 超过 30 分钟
    closed = await tm.sweep_idle_tables()
    assert tid in closed
    assert await tm.get_table(tid) is None


async def test_sweep_keeps_active_room():
    tid = await tm.create_table()
    closed = await tm.sweep_idle_tables()
    assert tid not in closed
    assert await tm.get_table(tid) is not None


# ---------------------------------------------------------------------------
# Reclaim token — per-seat token issued on sit_down, rotated on reclaim
# ---------------------------------------------------------------------------


async def test_reclaim_requires_token():
    tid = await tm.create_table()
    await tm.sit_down(tid, 0, "Hero", buyin=200)
    session = await tm.get_table(tid)
    token = session.reclaim_tokens[0]

    await tm.handle_disconnect(tid, 0)
    # 无 token / 错 token 拒
    assert await tm.try_reclaim(tid, "Hero", None) is None
    assert await tm.try_reclaim(tid, "Hero", "wrong") is None
    # 正确 token → 认领成功并轮换
    result = await tm.try_reclaim(tid, "Hero", token)
    assert result is not None
    seat, new_token = result
    assert seat == 0
    assert new_token != token
    assert session.reclaim_tokens[0] == new_token


def test_ws_sit_down_sends_private_token():
    client = TestClient(app)
    tid = client.post("/api/game/tables").json()["table_id"]
    with client.websocket_connect(f"/ws/{tid}") as ws:
        ws.send_json({"type": "sit_down", "seat_idx": 0, "name": "Hero", "buyin": 200})
        msgs = [ws.receive_json(), ws.receive_json()]
        token_msg = next(m for m in msgs if m["type"] == "reclaim_token")
        assert len(token_msg["token"]) == 32
        assert token_msg["seat"] == 0


def test_ws_reclaim_token_message_carries_authoritative_seat():
    """Reclaim ignores the requested seat_idx — the private reclaim_token
    message must carry the server-assigned (old) seat so the client can
    self-correct its mySeat."""
    client = TestClient(app)
    tid = client.post("/api/game/tables").json()["table_id"]
    with client.websocket_connect(f"/ws/{tid}") as ws1:
        ws1.send_json({"type": "sit_down", "seat_idx": 0, "name": "Hero", "buyin": 200})
        token_msg = ws1.receive_json()
        token = token_msg["token"]
        ws1.receive_json()              # table_state broadcast
    # ws1 closed.  The TestClient cancels the server task on close instead of
    # delivering WebSocketDisconnect, so mark the seat disconnected at the tm
    # level (the grace timer is cancelled immediately — it belongs to this
    # throwaway loop and must not outlive it).
    import asyncio
    async def _disconnect():
        await tm.handle_disconnect(tid, 0)
        session = await tm.get_table(tid)
        timer = session.grace_timers.pop(0, None)
        if timer is not None:
            timer.cancel()
            try:
                await timer
            except asyncio.CancelledError:
                pass
    asyncio.run(_disconnect())
    # Reconnect and reclaim, but ask for a DIFFERENT (free) seat — the
    # server must answer with seat 0.
    with client.websocket_connect(f"/ws/{tid}") as ws2:
        ws2.send_json({
            "type": "sit_down", "seat_idx": 2, "name": "Hero",
            "buyin": 200, "reclaim_token": token,
        })
        msg = ws2.receive_json()
        assert msg["type"] == "reclaim_token"
        assert msg["seat"] == 0
        assert msg["token"] != token    # rotated



# ---------------------------------------------------------------------------
# Consecutive action timeouts → automatic kick
# ---------------------------------------------------------------------------


async def test_consecutive_timeout_kicks_player(monkeypatch):
    """Hitting the timeout limit mid-hand: folded out and removed."""
    import asyncio
    monkeypatch.setattr(tm.app_config.game, "action_timeout_seconds", 0.05)
    monkeypatch.setattr(tm.app_config.game, "max_consecutive_timeouts", 2)
    tid = await tm.create_table()
    await tm.sit_down(tid, 0, "Hero", buyin=200)
    await tm.sit_down(tid, 1, "Bot", buyin=200, is_human=False)
    await tm.start_hand(tid)
    await tm.after_action(tid)  # ws.py does this in production: drive bots + arm timer
    await asyncio.sleep(0.6)  # 两次超时（BB option + 翻后首条街）足够触发
    session = await tm.get_table(tid)
    assert session is not None
    assert 0 not in session.player_names          # 已踢出
    assert session.game_state.phase == GamePhase.SHOWDOWN  # 手牌善终
    assert sum(p.stack for p in session.game_state.players) == 400  # 守恒


class _RecorderSocket:
    """Stand-in WebSocket that records every JSON message sent to it."""

    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def send_json(self, message: dict) -> None:
        self.sent.append(message)


async def test_timeout_kick_between_hands_notifies_kicked_player(monkeypatch):
    """Auto-action ends the hand → kick lands on the between-hands path.

    回归测试（pre-fix 红）：not-mid-hand 分支走 stand_up 静默弹 socket，
    被踢者收不到任何通知，前端 mySeat 不重置，冻在牌桌页。
    """
    from dataclasses import replace
    monkeypatch.setattr(tm.app_config.game, "action_timeout_seconds", 0)
    monkeypatch.setattr(tm.app_config.game, "max_consecutive_timeouts", 1)
    tid = await tm.create_table()
    await tm.sit_down(tid, 0, "Hero", buyin=200)
    await tm.sit_down(tid, 1, "Bot", buyin=200, is_human=False)
    session = await tm.get_table(tid)
    assert session is not None
    sock = _RecorderSocket()
    session.clients[0] = sock
    # Hero 坐按钮/SB（heads-up 翻前先手），面对 BB 必 auto-FOLD → 一手直接
    # 结束，踢人走 not-mid-hand（stand_up）路径。
    session.game_state = replace(session.game_state, dealer_idx=1)
    await tm.start_hand(tid)
    assert session.game_state.current_player_idx == 0

    await tm._action_timeout(tid, 0)

    kicked = [m for m in sock.sent if m.get("type") == "kicked"]
    assert kicked, f"no kicked message; got {[m.get('type') for m in sock.sent]}"
    assert "timeout" in kicked[0]["message"].lower()
    # kicked 是 socket 被移除前收到的最后一条私信
    assert sock.sent[-1]["type"] == "kicked"
    assert 0 not in session.player_names
    assert 0 not in session.clients
    assert session.game_state.phase == GamePhase.SHOWDOWN  # 手牌善终


async def test_timeout_kick_mid_hand_notifies_kicked_player():
    """Mid-hand force-kick (surgery path) also notifies the kicked player."""
    tid = await tm.create_table()
    await tm.sit_down(tid, 0, "Hero", buyin=200)
    await tm.sit_down(tid, 1, "Bot", buyin=200, is_human=False)
    session = await tm.get_table(tid)
    assert session is not None
    sock = _RecorderSocket()
    session.clients[0] = sock
    await tm.start_hand(tid)
    assert session.game_state.phase not in (GamePhase.WAITING, GamePhase.SHOWDOWN)

    await tm._expire_seat(tid, 0, force=True)

    assert any(m.get("type") == "kicked" for m in sock.sent)
    assert 0 not in session.player_names
    assert 0 not in session.clients
    assert session.game_state.phase == GamePhase.SHOWDOWN  # fold-out 善终
    assert sum(p.stack for p in session.game_state.players) == 400  # 守恒


async def test_force_kick_cancels_pending_grace_timer():
    """force 踢人时挂着的断线宽限计时器必须取消，否则它会二次触发过期。"""
    import asyncio
    tid = await tm.create_table()
    await tm.sit_down(tid, 0, "Hero", buyin=200)
    await tm.sit_down(tid, 1, "Bot", buyin=200, is_human=False)
    await tm.handle_disconnect(tid, 0)  # 挂起 60s 宽限计时器
    session = await tm.get_table(tid)
    assert session is not None
    timer = session.grace_timers[0]

    await tm._expire_seat(tid, 0, force=True)
    await asyncio.sleep(0)

    assert 0 not in session.grace_timers
    assert timer.done()  # 60s 睡眠不可能自然结束 —— 只能是被取消
    assert 0 not in session.player_names


async def test_manual_action_resets_timeout_counter():
    import random
    random.seed(7)
    tid = await tm.create_table()
    await tm.sit_down(tid, 0, "Hero", buyin=200)
    await tm.sit_down(tid, 1, "Bot", buyin=200, is_human=False)
    await tm.start_hand(tid)
    session = await tm.get_table(tid)
    assert session is not None
    session.consecutive_timeouts[0] = 1  # 预置计数
    await tm.auto_bot_actions(tid)       # bot 先行动（SB）
    await tm.handle_player_action(tid, 0, "CHECK")  # 人类主动行动
    assert session.consecutive_timeouts[0] == 0


async def test_concurrent_broadcasts_serialize_per_client():
    """Two overlapping broadcasts must not interleave frames on one socket —
    the per-seat send lock serializes them."""
    import asyncio

    class SlowWS:
        def __init__(self):
            self.max_concurrent = 0
            self.concurrent = 0

        async def send_json(self, message):
            self.concurrent += 1
            self.max_concurrent = max(self.max_concurrent, self.concurrent)
            await asyncio.sleep(0.02)  # interleave window
            self.concurrent -= 1

    tid = await tm.create_table()
    session = await tm.get_table(tid)
    slow = SlowWS()
    session.clients[0] = slow

    await asyncio.gather(
        tm.broadcast(tid, {"type": "a"}),
        tm.broadcast(tid, {"type": "b"}),
        tm.send_to_player(tid, 0, {"type": "c"}),
    )
    # without the lock the two sends overlap inside the sleep window
    assert slow.max_concurrent == 1
async def test_stand_up_mid_hand_rejected_direct():
    """tm.stand_up is the backstop: even a race that slips past the
    transport-level phase check cannot rip a seat out mid-hand."""
    tid = await tm.create_table()
    await tm.sit_down(tid, 0, "A", buyin=200)
    await tm.sit_down(tid, 1, "B", buyin=200)
    await tm.start_hand(tid)
    with pytest.raises(tm.GameError, match="mid-hand"):
        await tm.stand_up(tid, 0)
    # seat intact
    session = await tm.get_table(tid)
    assert session.game_state.player(0) is not None
    assert 0 in session.player_names


async def test_expire_seat_identity_cleared_under_lock(monkeypatch):
    """Grace expiry between hands removes identity + players atomically —
    start_hand afterwards must not deal a ghost seat."""
    import asyncio
    monkeypatch.setattr(tm.app_config.game, "disconnect_grace_seconds", 0.05)
    tid = await tm.create_table()
    await tm.sit_down(tid, 0, "Hero", buyin=200)
    await tm.sit_down(tid, 1, "Bot", buyin=200, is_human=False)
    await tm.handle_disconnect(tid, 0)
    await asyncio.sleep(0.15)

    # only the bot remains — start_hand refuses; and no ghost seat lingers
    with pytest.raises(tm.GameError, match="Need at least 2 players"):
        await tm.start_hand(tid)
    session = await tm.get_table(tid)
    assert len(session.game_state.players) == 1
    assert session.game_state.player(0) is None  # hero fully removed
async def test_crashing_bot_does_not_freeze_game(monkeypatch):
    """A bot whose decide() raises must fall back, not wedge the table."""
    from sekhmet.ai_engine import bot_registry
    from sekhmet.game_engine import GamePhase

    class CrashBot:
        def decide(self, state, player_idx):
            raise RuntimeError("bot bug")

    monkeypatch.setattr(bot_registry, "create", lambda name: CrashBot())

    tid = await tm.create_table()
    await tm.sit_down(tid, 0, "Hero", buyin=200)
    await tm.sit_down(tid, 1, "Bot", buyin=200, is_human=False, bot_level=1)
    await tm.start_hand(tid)

    # dealer advances to seat 1 → bot is SB and acts first; it faces the
    # big blind's 10 with 5 posted → the crash fallback folds it out and
    # the hand completes instead of freezing mid-round.
    await tm.auto_bot_actions(tid)
    session = await tm.get_table(tid)
    assert session.game_state.phase == GamePhase.SHOWDOWN
    assert session.game_state.player(0).stack == 205  # hero collected the blinds


async def test_after_action_survives_bot_phase_crash(monkeypatch):
    """Even if the bot phase blows up, the action timer still gets armed."""
    async def boom(table_id):
        raise RuntimeError("unexpected")

    monkeypatch.setattr(tm, "auto_bot_actions", boom)
    tid = await tm.create_table()
    await tm.sit_down(tid, 1, "Hero", buyin=200)   # seat 1: dealer→1, hero acts first
    await tm.sit_down(tid, 0, "Bot", buyin=200, is_human=False, bot_level=1)
    await tm.start_hand(tid)

    await tm.after_action(tid)  # must not raise
    session = await tm.get_table(tid)
    assert session.action_timer is not None  # human-to-act timer armed
    session.action_timer.cancel()
async def test_buyin_bounds_enforced():
    """Buy-in outside 20bb–200bb (incl. 0/negative grief seats) is rejected."""
    tid = await tm.create_table()  # blinds 5/10 → lo=200, hi=2000
    for bad in (0, -5, 10, 199, 2001, 99999):
        with pytest.raises(tm.GameError, match="Buy-in must be between"):
            await tm.sit_down(tid, 0, "A", buyin=bad)
    await tm.sit_down(tid, 0, "A", buyin=200)   # exactly 20bb — ok
    await tm.sit_down(tid, 1, "B", buyin=2000)  # exactly 200bb — ok
    session = await tm.get_table(tid)
    assert session.game_state.player(0).stack == 200
    assert session.game_state.player(1).stack == 2000


async def test_owner_token_claims_ownership():
    """The creator's token wins ownership even when a stranger sits first."""
    tid = await tm.create_table()
    token = (await tm.get_table(tid)).owner_token
    assert token is not None and len(token) == 32

    await tm.sit_down(tid, 0, "Stranger")               # no token
    assert (await tm.get_table(tid)).owner_seat == 0
    # token holder sits later at a higher seat — takes over the room
    await tm.sit_down(tid, 5, "Creator", owner_token=token)
    assert (await tm.get_table(tid)).owner_seat == 5


async def test_owner_token_claims_ownership_when_first():
    tid = await tm.create_table()
    token = (await tm.get_table(tid)).owner_token
    await tm.sit_down(tid, 5, "Creator", owner_token=token)
    await tm.sit_down(tid, 0, "Stranger")
    assert (await tm.get_table(tid)).owner_seat == 5  # token beats lowest-human


async def test_table_creation_cap(monkeypatch):
    from sekhmet.config import app_config
    tm._tables.clear()
    monkeypatch.setattr(app_config.game, "max_tables", 1)
    await tm.create_table()
    with pytest.raises(tm.GameError, match="limit"):
        await tm.create_table()
