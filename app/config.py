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
DEFAULT_CHARACTER = ASSETS_DIR / "character.png"
ICON_PATH = ASSETS_DIR / "icon.ico"
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


@dataclass
class Settings:
    user_name: str = ""  # 캐릭터가 불러줄 이름
    lead_minutes: int = 10  # 일정 몇 분 전에 미리 알려줄지 (0 이면 정각만)
    character_size: int = 160  # 캐릭터 높이(px)
    character_image: str = ""  # 비어 있으면 기본 캐릭터
    bubble_seconds: int = 8  # 일반 말풍선 표시 시간
    sound: bool = True  # 알림 시 효과음
    pos_x: int | None = None  # 캐릭터 위치 (None 이면 화면 오른쪽 아래)
    pos_y: int | None = None

    @classmethod
    def load(cls) -> "Settings":
        try:
            raw = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return cls()
        known = {f.name for f in fields(cls)}
        s = cls(**{k: v for k, v in raw.items() if k in known})
        s.lead_minutes = max(0, int(s.lead_minutes))
        s.character_size = min(400, max(60, int(s.character_size)))
        return s

    def save(self) -> None:
        atomic_write_json(SETTINGS_FILE, asdict(self))

    def character_path(self) -> Path:
        if self.character_image:
            p = Path(self.character_image)
            if not p.is_absolute():
                p = DATA_DIR / p
            if p.exists():
                return p
        return DEFAULT_CHARACTER
