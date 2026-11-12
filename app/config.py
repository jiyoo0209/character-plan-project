"""경로와 사용자 설정(settings.json)."""
from __future__ import annotations

import json
import os
import sys
import tempfile
from dataclasses import asdict, dataclass, fields
from pathlib import Path

APP_NAME = "CharacterPlan"
APP_TITLE = "캐릭터 일정 비서"


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def install_dir() -> Path:
    """설치 폴더 (exe 가 있는 폴더, 소스 실행 시 프로젝트 루트)."""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def resource_dir() -> Path:
    """번들된 리소스 위치 (PyInstaller onedir 에서는 _internal)."""
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS", install_dir()))
    return install_dir()


def _writable(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=path, delete=True):
            pass
        return True
    except OSError:
        return False


def _resolve_data_dir() -> Path:
    """기본은 설치 폴더/data. 쓰기 권한이 없으면(Program Files 등) LocalAppData 로 대체."""
    preferred = install_dir() / "data"
    if _writable(preferred):
        return preferred
    fallback = Path(os.environ.get("LOCALAPPDATA", Path.home())) / APP_NAME / "data"
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


DATA_DIR = _resolve_data_dir()
ASSETS_DIR = resource_dir() / "assets"
CHARACTERS_DIR = ASSETS_DIR / "characters"
ICON_PATH = ASSETS_DIR / "icon.ico"
FONTS_DIR = ASSETS_DIR / "fonts"  # 앱과 같이 배포하는 폰트 (*.ttf, *.otf)
SCHEDULES_FILE = DATA_DIR / "schedules.json"
SETTINGS_FILE = DATA_DIR / "settings.json"


def atomic_write_json(path: Path, data) -> None:
    """임시 파일에 쓴 뒤 교체해서, 저장 도중 꺼져도 파일이 깨지지 않게 한다."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


CHARACTER_SIZE = 160  # 캐릭터 높이(px) 기본값 (설정에서 바꿀 수 있음)
SIZE_MIN, SIZE_MAX, SIZE_STEP = 90, 260, 10
BUBBLE_SECONDS = 8  # 일반 말풍선(인사 등) 표시 시간, 고정

# 고를 수 있는 캐릭터: (id, 이름). 이미지는 assets/characters/<id>.gif (또는 .png/.webp)
CHARACTERS = (
    ("chiikawa", "치이카와"),
    ("usagi", "우사기"),
    ("kurimanju", "쿠리만쥬"),
)
DEFAULT_CHARACTER = CHARACTERS[0][0]
_IMAGE_EXTS = (".gif", ".webp", ".png")


def _find_image(stem: str) -> Path | None:
    for ext in _IMAGE_EXTS:
        p = CHARACTERS_DIR / f"{stem}{ext}"
        if p.exists():
            return p
    return None


def character_image(cid: str) -> Path | None:
    """바탕화면 캐릭터 이미지 (<id>.gif). 없으면 고르기 이미지(<id>_pick.gif)로 대신, 둘 다 없으면 None."""
    return _find_image(cid) or _find_image(f"{cid}_pick")


def pick_image(cid: str) -> Path | None:
    """설정 창 고르기 카드에 쓰는 이미지 (<id>_pick.gif). 없으면 바탕화면 이미지를 대신 쓴다."""
    return _find_image(f"{cid}_pick") or _find_image(cid)


def empty_image(cid: str) -> Path | None:
    """달력에서 일정이 없는 날 보여줄 그림 (<id>_1.png). 없으면 None (리본으로 대신)."""
    return _find_image(f"{cid}_1")


def character_path(cid: str) -> Path:
    """고른 캐릭터 이미지. 파일이 없으면 이미지가 있는 첫 캐릭터로 대체."""
    for c in (cid, *(c for c, _ in CHARACTERS)):
        p = character_image(c)
        if p:
            return p
    raise FileNotFoundError(f"캐릭터 이미지가 없습니다: {CHARACTERS_DIR}")


@dataclass
class Settings:
    user_name: str = ""  # 캐릭터가 불러줄 이름
    lead_minutes: int = 10  # 일정 몇 분 전에 미리 알려줄지 (0 이면 정각만)
    character: str = DEFAULT_CHARACTER  # CHARACTERS 의 id
    character_size: int = CHARACTER_SIZE  # 캐릭터 높이(px), SIZE_MIN ~ SIZE_MAX
    briefing: str = "startup"  # 하루 브리핑: "startup" = 컴퓨터 켤 때(앱 시작), "time" = 정해진 시간
    briefing_time: str = "08:30"  # briefing == "time" 일 때 HH:MM
    sound_volume: int = 80  # 일정 알림 효과음 크기 0~100 (0 = 조용히). 소리는 assets/sounds/<캐릭터>.mp3
    last_briefing: str = ""  # 마지막으로 브리핑한 날 (YYYY-MM-DD), 정해진 시간 브리핑을 하루 한 번만
    ride_windows: bool = True  # 활성 창 위에 올라타기
    pos_x: int | None = None  # 캐릭터 위치 (None 이면 화면 오른쪽 아래)
    pos_y: int | None = None

    @classmethod
    def load(cls) -> "Settings":
        try:
            raw = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return cls()
        known = {f.name for f in fields(cls)}
        if "sound_volume" not in raw and raw.get("sound_on") is False:  # 예전 '조용히' 설정 이어받기
            raw["sound_volume"] = 0
        s = cls(**{k: v for k, v in raw.items() if k in known})
        s.lead_minutes = max(0, int(s.lead_minutes))
        if s.character not in {c for c, _ in CHARACTERS}:
            s.character = DEFAULT_CHARACTER
        try:
            s.character_size = min(SIZE_MAX, max(SIZE_MIN, int(s.character_size)))
        except (TypeError, ValueError):
            s.character_size = CHARACTER_SIZE
        try:
            s.sound_volume = min(100, max(0, int(s.sound_volume)))
        except (TypeError, ValueError):
            s.sound_volume = 80
        if s.briefing not in ("startup", "time"):
            s.briefing = "startup"
        return s

    def save(self) -> None:
        atomic_write_json(SETTINGS_FILE, asdict(self))
