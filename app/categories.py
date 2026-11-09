"""일정 카테고리: (이름, 아이콘 파일). 순서대로 일정 추가 창에 나온다. 여기만 고치면 목록이 바뀐다.

아이콘은 assets/icons/categories/<파일>.png (Noto Emoji 그림).
"""
from __future__ import annotations

from pathlib import Path

from .config import ASSETS_DIR

CATEGORIES: tuple[tuple[str, str], ...] = (
    ("일", "work"),  # 💼
    ("공부", "study"),  # 📚
    ("게임", "game"),  # 🎮
    ("약속", "meet"),  # ☕
    ("운동", "exercise"),  # 💪
    ("병원", "hospital"),  # 💊
    ("여행", "travel"),  # ✈️
    ("기타", "etc"),  # 📌
)
_FILES = dict(CATEGORIES)
_ICON_DIR = ASSETS_DIR / "icons" / "categories"


def category_icon(name: str) -> Path | None:
    """카테고리 아이콘. 목록에 없는 이름(예전에 지운 카테고리)은 '기타' 아이콘."""
    if not name:
        return None
    return _ICON_DIR / f"{_FILES.get(name, 'etc')}.png"
