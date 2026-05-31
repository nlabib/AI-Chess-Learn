from __future__ import annotations

import os
import shutil
from dataclasses import dataclass


@dataclass(frozen=True)
class DifficultyProfile:
    key: str
    label: str
    stockfish_skill: int
    move_time_seconds: float
    fallback_depth: int


DIFFICULTIES = {
    "easy": DifficultyProfile(
        key="easy",
        label="Easy",
        stockfish_skill=4,
        move_time_seconds=0.08,
        fallback_depth=1,
    ),
    "medium": DifficultyProfile(
        key="medium",
        label="Medium",
        stockfish_skill=10,
        move_time_seconds=0.18,
        fallback_depth=2,
    ),
    "hard": DifficultyProfile(
        key="hard",
        label="Hard",
        stockfish_skill=16,
        move_time_seconds=0.35,
        fallback_depth=3,
    ),
}

DEFAULT_DIFFICULTY = "medium"


@dataclass(frozen=True)
class AppConfig:
    host: str
    port: int
    stockfish_path: str | None
    lm_studio_base_url: str
    lm_studio_model: str | None
    lm_studio_api_key: str
    lm_studio_timeout_seconds: float
    review_depth: int
    allow_cors_origin: str | None


def load_config() -> AppConfig:
    stockfish_path = os.getenv("STOCKFISH_PATH") or shutil.which("stockfish")

    return AppConfig(
        host=os.getenv("COACH_CHESS_HOST", "127.0.0.1"),
        port=int(os.getenv("COACH_CHESS_PORT", "8000")),
        stockfish_path=stockfish_path,
        lm_studio_base_url=os.getenv("LM_STUDIO_BASE_URL", "http://127.0.0.1:1234/v1").rstrip("/"),
        lm_studio_model=os.getenv("LM_STUDIO_MODEL") or None,
        lm_studio_api_key=os.getenv("LM_STUDIO_API_KEY", "lm-studio"),
        lm_studio_timeout_seconds=float(os.getenv("LM_STUDIO_TIMEOUT_SECONDS", "90")),
        review_depth=int(os.getenv("COACH_CHESS_REVIEW_DEPTH", "12")),
        allow_cors_origin=os.getenv("ALLOW_CORS_ORIGIN") or None,
    )


def get_difficulty(name: str | None) -> DifficultyProfile:
    if not name:
        return DIFFICULTIES[DEFAULT_DIFFICULTY]
    return DIFFICULTIES.get(name.lower(), DIFFICULTIES[DEFAULT_DIFFICULTY])

