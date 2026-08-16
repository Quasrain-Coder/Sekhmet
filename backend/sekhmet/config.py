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
    disconnect_grace_seconds: int = 180
    runout_delay_seconds: float = 0.8
    # 每个 bot 行动前的思考间隔——bot 决策不是瞬发，像真人一样有节奏
    bot_action_delay_seconds: float = 2.0
    room_idle_timeout_seconds: int = 1800
    # 巡检（sweeper）配置：僵尸桌判定与卡死牌局处理
    empty_room_timeout_seconds: int = 300    # 无人入座且无连接的空房间
    orphan_room_timeout_seconds: int = 600   # 只有 bot 且无连接——bot 自打永不 idle
    stuck_hand_timeout_seconds: int = 120    # all-in runout 失去驱动后强制完成
    sweep_interval_seconds: float = 30.0
    # 登录 token 有效期（秒，默认 7 天）。token 是 HMAC 签名的无状态
    # token，不随后端重启失效——之前存内存，每次重启全部踢下线。
    auth_token_ttl_seconds: int = 604800
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
