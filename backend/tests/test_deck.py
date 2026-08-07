import pytest
from sekhmet.game_engine.deck import Card, Suit, Rank, Deck


def test_card_creation():
    card = Card(Rank.ACE, Suit.SPADES)
    assert card.rank == Rank.ACE
    assert card.suit == Suit.SPADES
    assert str(card) == "A♠"


def test_card_equality():
    assert Card(Rank.KING, Suit.HEARTS) == Card(Rank.KING, Suit.HEARTS)
    assert Card(Rank.KING, Suit.HEARTS) != Card(Rank.KING, Suit.SPADES)


def test_full_deck_has_52_cards():
    deck = Deck()
    assert len(deck.cards) == 52


def test_deck_is_unique():
    deck = Deck()
    assert len(set(deck.cards)) == 52


def test_shuffle_changes_order():
    deck1 = Deck()
    deck2 = Deck()
    deck2.shuffle()
    assert deck1.cards != deck2.cards


def test_deal_negative_raises():
    deck = Deck()
    with pytest.raises(ValueError, match="negative"):
        deck.deal(-1)


def test_deal_removes_cards_from_deck():
    deck = Deck()
    deck.shuffle()
    initial = len(deck.cards)
    cards = deck.deal(5)
    assert len(cards) == 5
    assert len(deck.cards) == initial - 5


def test_deal_too_many_raises():
    deck = Deck()
    with pytest.raises(ValueError):
        deck.deal(53)
