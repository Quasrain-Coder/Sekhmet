import pytest
from sekhmet.config import AppConfig, GameConfig, ScoringWeights, app_config


@pytest.fixture
def game_config():
    return GameConfig(default_stack=100, default_small_blind=1, default_big_blind=2)


@pytest.fixture
def scoring_weights():
    return ScoringWeights()
