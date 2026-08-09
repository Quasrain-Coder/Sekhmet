from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class GameConfig:
    default_stack: int = 1000
    default_small_blind: int = 5
    default_big_blind: int = 10
    max_seats_per_table: int = 9
    action_timeout_seconds: int = 30
    disconnect_grace_seconds: int = 60


@dataclass
class ScoringWeights:
    action_match: float = 0.60
    sizing_precision: float = 0.25
    timing_judgment: float = 0.15


@dataclass
class AppConfig:
    game: GameConfig = field(default_factory=GameConfig)
    scoring: ScoringWeights = field(default_factory=ScoringWeights)
    database_url: str = "sqlite+aiosqlite:///sekhmet.db"
    data_dir: Path = Path("data")


app_config = AppConfig()
