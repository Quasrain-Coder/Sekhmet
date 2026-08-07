"""Tests for pot creation (including side pots) and pot award at showdown."""

from sekhmet.game_engine.deck import Card, Rank, Suit
from sekhmet.game_engine.game_state import Player, PotState, SidePot
from sekhmet.game_engine.hand_evaluator import HandScore, HandRank
from sekhmet.game_engine.pot_manager import create_side_pots, award_pot, PotAward


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def P(seat: int, total_bet: int = 0, stack: int = 1000, is_active: bool = True):
    return Player(
        name=f"P{seat}",
        seat_idx=seat,
        stack=stack,
        total_bet=total_bet,
        is_active=is_active,
    )


# ---------------------------------------------------------------------------
# create_side_pots
# ---------------------------------------------------------------------------


def test_empty_pot():
    players = (P(0), P(1))
    pot = create_side_pots(players)
    assert pot.main_pot == 0
    assert pot.side_pots == ()
    assert pot.total == 0


def test_simple_all_equal_bets():
    """All players bet the same amount → just a main pot."""
    players = (P(0, total_bet=10), P(1, total_bet=10), P(2, total_bet=10))
    pot = create_side_pots(players)
    assert pot.main_pot == 30
    assert pot.side_pots == ()
    assert pot.total == 30


def test_one_all_in_for_less():
    """P0 all-in for 50, P1 and P2 bet 100 each."""
    players = (
        P(0, total_bet=50),
        P(1, total_bet=100),
        P(2, total_bet=100),
    )
    pot = create_side_pots(players)

    # Main pot: 3 players × 50 = 150
    assert pot.main_pot == 150

    # Side pot: 2 players × (100-50) = 100
    assert len(pot.side_pots) == 1
    sp = pot.side_pots[0]
    assert sp.amount == 100
    assert sp.eligible_players == (1, 2)
    assert pot.total == 250


def test_two_all_ins_different_amounts():
    """P0 all-in for 30, P1 all-in for 70, P2 bets 100."""
    players = (
        P(0, total_bet=30),
        P(1, total_bet=70),
        P(2, total_bet=100),
    )
    pot = create_side_pots(players)

    # Main: 3 × 30 = 90
    assert pot.main_pot == 90

    # Side 1 (30→70): P1 + P2 = 2 × 40 = 80
    # Side 2 (70→100): P2 only = 1 × 30 = 30
    assert len(pot.side_pots) == 2
    assert pot.side_pots[0].amount == 80   # P1, P2 eligible
    assert pot.side_pots[0].eligible_players == (1, 2)
    assert pot.side_pots[1].amount == 30   # only P2 eligible
    assert pot.side_pots[1].eligible_players == (2,)
    assert pot.total == 200


def test_folded_player_does_not_affect_amounts():
    """Folded players' bets count toward pot but they can't win."""
    players = (
        P(0, total_bet=50, is_active=False),  # folded
        P(1, total_bet=100),
        P(2, total_bet=100),
    )
    pot = create_side_pots(players)
    # Main: all 3 × 50 = 150
    assert pot.main_pot == 150
    # Side: 2 × 50 = 100 (eligible: 1, 2)
    assert len(pot.side_pots) == 1
    assert pot.side_pots[0].amount == 100


def test_unequal_bets_no_all_in():
    """Just different bet amounts without all-in situations."""
    players = (
        P(0, total_bet=25),
        P(1, total_bet=50),
    )
    pot = create_side_pots(players)
    # Main: 2 × 25 = 50
    assert pot.main_pot == 50
    # Side: P1 only, 1 × 25 = 25
    assert len(pot.side_pots) == 1
    assert pot.side_pots[0].amount == 25


# ---------------------------------------------------------------------------
# award_pot
# ---------------------------------------------------------------------------


def _hs(rank: HandRank, *kickers: int) -> HandScore:
    return HandScore(rank, kickers)


def test_award_simple_win():
    """One player wins outright."""
    players = (P(0, total_bet=10), P(1, total_bet=10))
    hands = {
        0: _hs(HandRank.ONE_PAIR, 14, 13, 12, 11),
        1: _hs(HandRank.HIGH_CARD, 14, 13, 12, 11, 9),
    }
    pot = PotState(main_pot=20)
    awards = award_pot(pot, players, hands)
    assert len(awards) == 1
    assert awards[0].winner_seat_idx == 0
    assert awards[0].amount == 20
    assert "One Pair" in awards[0].hand_description


def test_award_with_side_pot():
    """P2 wins side pot, P0 wins main pot."""
    players = (
        P(0, total_bet=50),
        P(1, total_bet=100),
        P(2, total_bet=100),
    )
    hands = {
        0: _hs(HandRank.FLUSH, 14, 13, 12, 11, 9),       # best hand
        1: _hs(HandRank.HIGH_CARD, 14, 13, 12, 11, 9),   # worst
        2: _hs(HandRank.ONE_PAIR, 14, 13, 12, 11),       # middle
    }
    pot = create_side_pots(players)

    awards = award_pot(pot, players, hands)

    # Main pot (150): all 3 eligible → P0 wins with flush
    main_awards = [a for a in awards if a.amount == 150]
    assert len(main_awards) == 1
    assert main_awards[0].winner_seat_idx == 0

    # Side pot (100): P1, P2 eligible → P2 wins with pair
    side_awards = [a for a in awards if a.amount == 100]
    assert len(side_awards) == 1
    assert side_awards[0].winner_seat_idx == 2


def test_award_split_pot_on_tie():
    """Two players tie → split main pot."""
    players = (P(0, total_bet=10), P(1, total_bet=10))
    hands = {
        0: _hs(HandRank.ONE_PAIR, 14, 13, 12, 11),
        1: _hs(HandRank.ONE_PAIR, 14, 13, 12, 11),  # identical kickers
    }
    pot = PotState(main_pot=20)
    awards = award_pot(pot, players, hands)
    amounts = {a.winner_seat_idx: a.amount for a in awards}
    assert amounts[0] == 10
    assert amounts[1] == 10


def test_award_split_odd_chip():
    """Odd chip on split goes to first eligible seat."""
    players = (P(0, total_bet=10), P(1, total_bet=10))
    hands = {
        0: _hs(HandRank.ONE_PAIR, 14, 13, 12, 11),
        1: _hs(HandRank.ONE_PAIR, 14, 13, 12, 11),
    }
    pot = PotState(main_pot=25)  # odd amount
    awards = award_pot(pot, players, hands)
    amounts = {a.winner_seat_idx: a.amount for a in awards}
    # Seat 0 is first → gets 13, seat 1 gets 12
    assert amounts[0] == 13
    assert amounts[1] == 12


def test_award_folded_player_excluded():
    """Folded player doesn't get awarded even if they had the best hand."""
    players = (
        P(0, total_bet=10, is_active=False),  # folded
        P(1, total_bet=10),
    )
    # Only P1 has a hand (reached showdown)
    hands = {1: _hs(HandRank.HIGH_CARD, 14, 13, 12, 11, 9)}
    pot = PotState(main_pot=20)
    awards = award_pot(pot, players, hands)
    assert len(awards) == 1
    assert awards[0].winner_seat_idx == 1
    assert awards[0].amount == 20


def test_award_empty_pot():
    awards = award_pot(PotState(), (), {})
    assert awards == []
