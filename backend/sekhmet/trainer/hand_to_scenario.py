"""Rebuild training scenarios from recorded real hands.

Every completed hand is persisted (``hand_records``) with the full
action sequence and — since the hole-card patch — everyone's hole
cards.  We replay the actions through the immutable engine to
reconstruct the exact ``GameState`` at every decision point, then
pick one where the account lost the hand and turn it into a training
scenario: the reference action comes from the GTO bot's decision at
that exact state.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from ..game_engine import Action, ActionType, GamePhase, GameState, Player
from ..game_engine.action_processor import execute
from ..game_engine.deck import Card, Rank, Suit
from ..ai_engine.gto_bot import GTOBot
from ..trainer.scenario_library import Scenario, ScenarioCategory

logger = logging.getLogger(__name__)

_RANK = {"2": 2, "3": 3, "4": 4, "5": 5, "6": 6, "7": 7, "8": 8, "9": 9,
         "10": 10, "J": 11, "Q": 12, "K": 13, "A": 14}
_SUIT = {"♠": Suit.SPADES, "♥": Suit.HEARTS, "♦": Suit.DIAMONDS, "♣": Suit.CLUBS}


def parse_card(text: str) -> Card:
    """'A♠' → Card.  Rank may be '10' (two chars)."""
    rank_str = text[:-1]
    return Card(Rank(_RANK[rank_str]), _SUIT[text[-1]])


def rebuild_states(
    players_meta: list[dict], board: list[str], actions: list[dict],
    small_blind: int, big_blind: int,
) -> list[tuple[GameState, int]]:
    """Replay the action log and return every (state, actor) decision point.

    The engine is a pure state machine, so executing the same actions
    from the deal reproduces the exact states of the original hand.
    """
    seats = [p["seat_idx"] for p in players_meta]
    dealer = seats[-1]  # last seat dealt acts as button in our deal order
    players = tuple(
        Player(
            name=p["name"], seat_idx=p["seat_idx"],
            stack=p["stack_before"],
            hole_cards=tuple(parse_card(c) for c in p.get("hole_cards", [])),
            is_human=p["is_human"],
        )
        for p in players_meta
    )
    sb_seat = seats[0]
    bb_seat = seats[1] if len(seats) > 1 else seats[0]
    # Faithfully rebuild the post-deal state: blinds posted, bet-to-match
    # at big blind, pot collected — otherwise replaying the first action
    # fails validation (nothing to call / nothing to raise).
    sb_bet = min(small_blind, players[0].stack if players else 0)
    bb_bet = min(big_blind, players[1].stack if len(players) > 1 else 0)
    dealt = tuple(
        Player(
            name=p.name, seat_idx=p.seat_idx, stack=p.stack - (
                sb_bet if p.seat_idx == sb_seat else
                bb_bet if p.seat_idx == bb_seat else 0),
            hole_cards=p.hole_cards, is_human=p.is_human,
            current_bet=sb_bet if p.seat_idx == sb_seat else
                       bb_bet if p.seat_idx == bb_seat else 0,
            total_bet=sb_bet if p.seat_idx == sb_seat else
                      bb_bet if p.seat_idx == bb_seat else 0,
        )
        for p in players
    )
    from ..game_engine.game_state import PotState
    from ..game_engine.action_processor import _next_active_seat
    n_seats = max((p.seat_idx + 1 for p in players), default=0)
    first_to_act = _next_active_seat(dealt, bb_seat, n_seats)

    # Rebuild the remaining deck: unknown cards, then the board in
    # street order at the tail — the engine deals community cards off
    # the end, so the replay reproduces the exact flop/turn/river.
    board_cards = [parse_card(c) for c in board]
    known = {(c.rank.value, c.suit.value) for p in players
             for c in (p.hole_cards or [])} | {
        (c.rank.value, c.suit.value) for c in board_cards}
    deck_cards = [Card(r, s) for r in Rank for s in Suit
                  if (r.value, s.value) not in known] + board_cards

    gs = GameState(
        phase=GamePhase.PREFLOP,
        players=dealt,
        deck=tuple(deck_cards),
        dealer_idx=dealer,
        current_player_idx=first_to_act,
        current_bet=big_blind,
        min_raise=big_blind,
        small_blind=small_blind,
        big_blind=big_blind,
        sb_seat=sb_seat,
        bb_seat=bb_seat,
        pot=PotState(main_pot=sb_bet + bb_bet),
    )

    points: list[tuple[GameState, int]] = []
    for a in actions:
        seat = a["seat"]
        at = ActionType[a["action"]]
        action = Action(player_idx=seat, type=at, amount=a.get("amount", 0))
        points.append((gs, seat))
        try:
            gs = execute(gs, action)
        except Exception:
            logger.exception("replay diverged at %s — stopping", a)
            break
    return points


def build_scenario_from_hand(
    hand: dict[str, Any],
    seat: int,
    player_name: str,
    decision_idx: int = -1,
) -> Scenario | None:
    """Build a training scenario from one decision point of a recorded hand.

    Picks the decision point *decision_idx* before the end (default: the
    last decision) where *seat* acts.  The GTO bot's decision at that
    exact state is the reference; the description hides the outcome.
    """
    players_meta = hand.get("players", [])
    me = next((p for p in players_meta if p["seat_idx"] == seat), None)
    if me is None or not me.get("hole_cards"):
        return None

    points = rebuild_states(
        players_meta, hand.get("board", []), hand.get("actions", []),
        hand.get("small_blind") or 5, hand.get("big_blind") or 10,
    )
    mine = [(gs, s) for gs, s in points if s == seat]
    if not mine:
        return None
    gs, _ = mine[decision_idx]

    # The GTO bot's decision at this exact state is the reference.
    bot = GTOBot()
    ref = bot.decide(gs, seat)
    optimal = {"type": ref.type.name, "amount": ref.amount}
    hole = " ".join(str(c) for c in gs.player(seat).hole_cards)  # type: ignore[union-attr]
    board = " ".join(str(c) for c in gs.community_cards) or "翻前"

    return Scenario(
        id=f"hand-{hand.get('id')}-{seat}",
        title=f"复盘：{board} 阶段（{hole}）",
        description=(
            f"来自真实对局（{player_name} 的这手牌），轮到你了。"
            f"底池 {gs.pot.main_pot}，跟注需要 {max(0, gs.current_bet - gs.player(seat).current_bet)}。"
            "选择你认为最优的动作。"
        ),
        category=ScenarioCategory.PREFLOP_RANGE
        if gs.phase == GamePhase.PREFLOP else ScenarioCategory.POSTFLOP_VALUE,
        difficulty=3,
        optimal_action=optimal,
        acceptable_range={optimal["type"]: [0.6, 1.0]},
        hints=[
            f"当前阶段 {gs.phase.name}，位置 {seat} 号位",
            f"参考解（GTO bot）：{optimal['type']}"
            + (f" {optimal['amount']}" if optimal["amount"] else ""),
        ],
        analysis={"equity_vs_range": 0.5},
        frozen_state=gs,
    )


def hands_containing(records: list[dict], username: str) -> list[dict]:
    """Recorded hands where *username* appears (with hole cards)."""
    out = []
    for r in records:
        players = r.get("players", [])
        if any(p.get("name") == username and p.get("hole_cards")
               for p in players):
            out.append(r)
    return out


def lost_hands_for(records: list[dict], username: str, limit: int = 20) -> list[dict]:
    """Hands where *username* ended with a smaller stack than they started."""
    out = []
    for r in records:
        players = r.get("players", [])
        me = next((p for p in players if p.get("name") == username), None)
        if me is None:
            continue
        before = me.get("stack_before")
        after = me.get("stack_after")
        if before is not None and after is not None and after < before:
            out.append(r)
        if len(out) >= limit:
            break
    return out
