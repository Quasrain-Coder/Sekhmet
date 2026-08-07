from enum import IntEnum, Enum
from dataclasses import dataclass
import random


class Suit(Enum):
    SPADES = "♠"
    HEARTS = "♥"
    DIAMONDS = "♦"
    CLUBS = "♣"


class Rank(IntEnum):
    TWO = 2
    THREE = 3
    FOUR = 4
    FIVE = 5
    SIX = 6
    SEVEN = 7
    EIGHT = 8
    NINE = 9
    TEN = 10
    JACK = 11
    QUEEN = 12
    KING = 13
    ACE = 14

    def __str__(self):
        names = {11: "J", 12: "Q", 13: "K", 14: "A"}
        return names.get(self.value, str(self.value))


@dataclass(frozen=True)
class Card:
    rank: Rank
    suit: Suit

    def __str__(self):
        return f"{self.rank}{self.suit.value}"


class Deck:
    def __init__(self):
        self.cards = [Card(rank, suit) for rank in Rank for suit in Suit]

    def shuffle(self):
        random.shuffle(self.cards)

    def deal(self, n: int) -> list[Card]:
        if n < 0:
            raise ValueError(f"Cannot deal a negative number of cards: {n}")
        if n > len(self.cards):
            raise ValueError(
                f"Cannot deal {n} cards, only {len(self.cards)} remain"
            )
        dealt = self.cards[:n]
        self.cards = self.cards[n:]
        return dealt
