from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class GameConfig:
    default_stack: int = 1000
    default_small_blind: int = 5
    default_big_blind: int = 10
    max_seats_per_table: int = 9
    action_timeout_seconds: int = 30
    max_consecutive_timeouts: int = 3
    disconnect_grace_seconds: int = 60
    runout_delay_seconds: float = 0.8
    # 每个 bot 行动前的思考间隔——bot 决策不是瞬发，像真人一样有节奏
    bot_action_delay_seconds: float = 2.0
    room_idle_timeout_seconds: int = 1800
    max_tables: int = 30


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
