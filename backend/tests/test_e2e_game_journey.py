"""End-to-end test: the complete user journey through REST + WebSocket.

Simulates exactly what the frontend does, start to finish:

1. Lobby: create a room WITH config (blinds / buyin / max seats)
2. Join panel: GET room detail (what the confirmation page shows)
3. Sit down as the human
4. Add two bots with different levels (the "+ Bot" picker)
5. Play two full hands — acting on every turn, bots auto-play
6. Mid-hand join is rejected (guard)
7. Kick a bot between hands
8. Play a third hand with the remaining players

Assertions cover poker invariants (board runs out, awards, chip
conservation across hands) and room invariants (config, seat details,
dealer button advancement).
"""

import random

from fastapi.testclient import TestClient

from sekhmet.main import app

TOTAL_CHIPS = 3 * 2000  # three seats × 2000 buyin


def test_complete_game_journey():
    random.seed(20260809)
    client = TestClient(app)

    # ---- 1. Lobby: create a configured room ----
    resp = client.post("/api/game/tables", json={
        "small_blind": 10, "big_blind": 20, "default_buyin": 2000, "max_seats": 6,
    })
    assert resp.status_code == 200
    tid = resp.json()["table_id"]

    # Invalid config is rejected with a useful status
    assert client.post("/api/game/tables", json={
        "small_blind": 50, "big_blind": 20,
    }).status_code == 400

    # ---- 2. Join panel: room detail for the confirmation page ----
    detail = client.get(f"/api/game/tables/{tid}").json()
    assert detail["config"] == {
        "small_blind": 10, "big_blind": 20, "default_buyin": 2000, "max_seats": 6,
    }
    assert detail["seats"] == []
    assert client.get("/api/game/tables/doesnotexist").status_code == 404

    with client.websocket_connect(f"/ws/{tid}") as ws:

        def recv_until(pred, what, limit=50):
            for _ in range(limit):
                msg = ws.receive_json()
                if pred(msg):
                    return msg
            raise AssertionError(f"never received {what}")

        # ---- 3. Sit down (human, from the join panel) ----
        ws.send_json({"type": "sit_down", "seat_idx": 0, "name": "Hero", "buyin": 2000})
        ts = recv_until(lambda m: m["type"] == "table_state", "table_state")
        assert ts["seats"] == [{
            "seat_idx": 0, "name": "Hero", "is_human": True,
            "bot_level": None, "stack": 2000,
        }]
        assert ts["config"]["big_blind"] == 20

        # ---- 4. Add two bots with levels ("+ Bot" → L1 / L3) ----
        ws.send_json({"type": "sit_down", "seat_idx": 1, "name": "Bot L1",
                      "is_human": False, "bot_level": 1})
        ws.send_json({"type": "sit_down", "seat_idx": 2, "name": "Bot L3",
                      "is_human": False, "bot_level": 3})
        ts = recv_until(
            lambda m: m["type"] == "table_state" and len(m["seats"]) == 3,
            "3-seat table_state",
        )
        assert {s["seat_idx"]: s["bot_level"] for s in ts["seats"]} == {0: None, 1: 1, 2: 3}

        # ---- 5/6. Play two full hands ----
        dealers = []
        for hand_no in (1, 2):
            ws.send_json({"type": "start_hand"})
            if hand_no == 1:
                # Late join attempt while the hand is running → rejected
                ws.send_json({"type": "sit_down", "seat_idx": 3, "name": "Late"})

            result = None
            saw_mid_hand_error = False
            for _ in range(150):
                msg = ws.receive_json()
                mtype = msg["type"]

                if mtype == "error":
                    # The only error this journey should ever produce
                    assert "mid-hand" in msg["message"], msg
                    saw_mid_hand_error = True
                    continue
                if mtype == "hole_cards":
                    assert len(msg["cards"]) == 2
                    continue
                if mtype == "hand_start":
                    dealers.append(msg["dealer_idx"])
                    assert msg["small_blind"] == 10 and msg["big_blind"] == 20
                    # Chip conservation at the start of every hand
                    chips = sum(p["stack"] for p in msg["players"]) + msg["pot"]
                    assert chips == TOTAL_CHIPS, f"hand {hand_no}: chips={chips}"
                if mtype == "hand_result":
                    result = msg
                    break
                # Act whenever it's our turn (simple check/call strategy)
                cur = msg.get("current_player_idx")
                if mtype in ("game_state_update", "hand_start") and cur == 0:
                    me = next(p for p in msg["players"] if p["seat_idx"] == 0)
                    to_call = msg["current_bet"] - me["current_bet"]
                    ws.send_json({
                        "type": "player_action",
                        "action": "CALL" if to_call > 0 else "CHECK",
                        "amount": 0,
                    })

            assert result is not None, f"hand {hand_no} never reached showdown"
            if hand_no == 1:
                assert saw_mid_hand_error, "mid-hand join was not rejected"

            # Showdown integrity: either someone won by fold-out (no hands
            # revealed), or the board ran out to 5 cards and every award
            # names a real hand.
            showdown = result["showdown"]
            if showdown["hands"]:
                assert len(result["community_cards"]) == 5
            assert showdown["awards"], "pot was not awarded"
            assert sum(a["amount"] for a in showdown["awards"]) > 0

        # Dealer button advanced across hands (3 seated players)
        assert dealers == [1, 2]

        # ---- 7. Kick the L3 bot between hands ----
        # (its stack leaves the table with it — record for conservation)
        kicked_stack = next(
            p["stack"] for p in result["players"] if p["seat_idx"] == 2
        )
        ws.send_json({"type": "stand_up", "seat_idx": 2})
        ts = recv_until(
            lambda m: m["type"] == "table_state" and len(m["seats"]) == 2,
            "2-seat table_state after kick",
        )
        assert all(s["seat_idx"] != 2 for s in ts["seats"])

        # ---- 8. Third hand with two players still completes ----
        ws.send_json({"type": "start_hand"})
        result = None
        for _ in range(150):
            msg = ws.receive_json()
            if msg["type"] == "hand_result":
                result = msg
                break
            if msg["type"] == "hole_cards":
                continue
            cur = msg.get("current_player_idx")
            if msg["type"] in ("game_state_update", "hand_start") and cur == 0:
                me = next(p for p in msg["players"] if p["seat_idx"] == 0)
                to_call = msg["current_bet"] - me["current_bet"]
                ws.send_json({
                    "type": "player_action",
                    "action": "CALL" if to_call > 0 else "CHECK",
                    "amount": 0,
                })
        assert result is not None, "heads-up hand after kick never finished"

    # Chips are still all accounted for at the end of the journey:
    # remaining players' stacks + what the kicked bot took with it = total.
    detail = client.get(f"/api/game/tables/{tid}").json()
    stacks = {s["seat_idx"]: s["stack"] for s in detail["seats"]}
    assert set(stacks) == {0, 1}
    assert sum(stacks.values()) + kicked_stack == TOTAL_CHIPS
