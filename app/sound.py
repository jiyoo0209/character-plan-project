"""캐릭터 효과음: 일정 알림 때 캐릭터별 소리를 낸다.

소리 파일은 assets/sounds/<캐릭터 id>.mp3 (예: chiikawa.mp3, usagi.mp3, kurimanju.mp3).
.wav / .ogg / .m4a 도 된다. 파일이 없거나 재생에 실패하면 윈도우 기본 알림음으로 대신한다.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QUrl

from .config import ASSETS_DIR

SOUND_DIR = ASSETS_DIR / "sounds"
EXTS = (".mp3", ".wav", ".ogg", ".m4a")
VOLUME = 0.8  # 0.0 ~ 1.0


def sound_file(cid: str) -> Path | None:
    for ext in EXTS:
        p = SOUND_DIR / f"{cid}{ext}"
        if p.is_file():
            return p
    return None


def _fallback() -> None:
    from . import desktop

    desktop.beep()


class SoundPlayer(QObject):
    """효과음 하나를 재생한다 (새로 틀면 이전 소리는 멈춤). 재생기는 처음 쓸 때 만든다."""

    def __init__(self):
        super().__init__()
        self._player = None
        self._out = None

    def _ensure(self) -> bool:
        if self._player is not None:
            return True
        try:
            from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
        except ImportError:
            return False
        self._out = QAudioOutput(self)
        self._out.setVolume(VOLUME)
        self._player = QMediaPlayer(self)
        self._player.setAudioOutput(self._out)
        self._player.errorOccurred.connect(lambda *_: _fallback())  # 못 읽는 파일 / 소리 장치 없음
        return True

    def play(self, cid: str, fallback: bool = True) -> bool:
        """cid 캐릭터의 효과음. 파일이 없거나 재생기를 못 만들면 (fallback 이면) 기본 알림음."""
        path = sound_file(cid)
        if path is None or not self._ensure():
            if fallback:
                _fallback()
            return False
        self._player.stop()
        self._player.setSource(QUrl.fromLocalFile(str(path)))
        self._player.play()
        return True


_shared: SoundPlayer | None = None


def player() -> SoundPlayer:
    """앱 전체에서 같이 쓰는 재생기 (알림 · 설정창 '들어 보기')."""
    global _shared
    if _shared is None:
        _shared = SoundPlayer()
    return _shared
