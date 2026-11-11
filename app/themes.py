"""캐릭터별 색 테마. 고른 캐릭터의 대표색에 맞춰 창 색이 바뀐다."""
from __future__ import annotations

from dataclasses import dataclass

from .config import ASSETS_DIR

FONT_FAMILY = "Jua"  # 주아 (assets/fonts/Jua-Regular.ttf, app._load_fonts 에서 등록)
SUNDAY = "#E57B83"  # 달력 일요일 글자
SATURDAY = "#6E97CF"  # 달력 토요일 글자


@dataclass(frozen=True)
class Theme:
    accent: str  # 포인트 (선택된 알약, 저장 버튼, 카드 테두리)
    accent_deep: str  # 포인트 진하게 (제목, 마우스 올렸을 때)
    on_accent: str  # 포인트 위 글자색
    soft: str  # 선택된 카드 배경
    line: str  # 테두리
    bg: str  # 창 배경
    text: str  # 본문 글자
    subtext: str  # 흐린 글자
    card: str = "#FFFFFF"
    key: str = ""  # 캐릭터 id

    @property
    def ribbon(self):
        """제목 옆 리본 이미지 (테마 색으로 칠한 버전)."""
        return ASSETS_DIR / "icons" / f"ribbon_{self.key}.png"


THEMES: dict[str, Theme] = {
    # 치이카와: 볼 핑크
    "chiikawa": Theme(
        key="chiikawa", accent="#F59AB0", accent_deep="#E2728F", on_accent="#FFFFFF", soft="#FFE4EB",
        line="#F6D5DC", bg="#FFF6F7", text="#5B4248", subtext="#A88E94",
    ),
    # 우사기: 크림 노랑 (밝은 색이라 포인트 위 글자는 갈색)
    "usagi": Theme(
        key="usagi", accent="#F2C94C", accent_deep="#C9961E", on_accent="#5A4630", soft="#FFF3C9",
        line="#F5E3A6", bg="#FFFBEE", text="#5A4630", subtext="#A8956E",
    ),
    # 쿠리만쥬: 구운 밤색
    "kurimanju": Theme(
        key="kurimanju", accent="#C98A52", accent_deep="#A86E3D", on_accent="#FFFFFF", soft="#F8E8D2",
        line="#EBD3B5", bg="#FFF9F2", text="#5B4232", subtext="#A88E7A",
    ),
}
DEFAULT_THEME = THEMES["chiikawa"]


def theme_for(cid: str) -> Theme:
    return THEMES.get(cid, DEFAULT_THEME)


def common_style(t: Theme) -> str:
    """여러 창이 같이 쓰는 스타일: 폰트, 알약 버튼(primary/ghost/chip)."""
    return f"""
* {{ font-family: "{FONT_FAMILY}"; }}
QPushButton#chip {{
    background: {t.card}; color: {t.text}; font-size: 13px;
    border: 2px solid {t.line}; border-radius: 15px; padding: 5px 14px; min-height: 18px;
}}
QPushButton#chip:hover {{ border-color: {t.accent}; }}
QPushButton#chip:checked {{
    background: {t.accent}; color: {t.on_accent}; border-color: {t.accent};
}}
QPushButton#primary, QPushButton#ghost {{
    font-size: 14px; border-radius: 19px; padding: 8px 22px; min-height: 20px;
}}
QPushButton#primary {{ background: {t.accent}; color: {t.on_accent}; border: 2px solid {t.accent}; }}
QPushButton#primary:hover {{ background: {t.accent_deep}; border-color: {t.accent_deep}; color: white; }}
QPushButton#primary:disabled {{ background: {t.line}; border-color: {t.line}; color: {t.card}; }}
QPushButton#ghost {{ background: transparent; color: {t.subtext}; border: 2px solid {t.line}; }}
QPushButton#ghost:hover {{ color: {t.text}; border-color: {t.accent}; }}
QPushButton#ghost:disabled {{ color: {t.line}; border-color: {t.line}; }}
"""


def menu_style(t: Theme) -> str:
    """우클릭 / 트레이 메뉴."""
    return f"""
QMenu {{
    font-family: "{FONT_FAMILY}"; background: {t.card};
    border: 2px solid {t.line}; border-radius: 16px; padding: 8px 4px;
}}
QMenu::item {{
    color: {t.text}; font-size: 14px; padding: 8px 26px 8px 10px;
    margin: 1px 4px; border-radius: 10px;
}}
QMenu::item:selected {{ background: {t.soft}; color: {t.accent_deep}; }}
QMenu::item:disabled {{ color: {t.subtext}; font-size: 12px; padding: 4px 26px 2px 10px; }}
QMenu::item:disabled:selected {{ background: transparent; color: {t.subtext}; }}
QMenu::icon {{ padding-left: 12px; }}
QMenu::separator {{ height: 2px; background: {t.line}; margin: 6px 14px; }}
QMenu::indicator {{ width: 0; height: 0; }}
"""
