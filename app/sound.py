"""캐릭터 효과음: 일정 알림 때 캐릭터별 소리를 낸다.

소리 파일은 assets/sounds/<캐릭터 id>.mp3 (예: chiikawa.mp3, usagi.mp3, kurimanju.mp3). .wav 도 된다.
파일이 없거나 재생에 실패하면 윈도우 기본 알림음으로 대신한다.

윈도우에서는 윈도우에 들어 있는 재생 기능(MCI, winmm)을 쓴다: 따로 넣을 라이브러리가 없어서 앱이 가볍다.
(PySide6-Essentials 윈도우 판에는 QtMultimedia 가 없다.) 다른 OS(개발용)에서는 QtMultimedia 가 있으면 그걸 쓴다.
"""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QObject, QUrl

from .config import ASSETS_DIR

IS_WINDOWS = sys.platform == "win32"
SOUND_DIR = ASSETS_DIR / "sounds"
EXTS = (".mp3", ".wav")
ALIAS = "characterplan_sfx"


def sound_file(cid: str) -> Path | None:
    for ext in EXTS:
        p = SOUND_DIR / f"{cid}{ext}"
        if p.is_file():
            return p
    return None


def _fallback() -> None:
    from . import desktop

    desktop.beep()


class _MciBackend:
    """윈도우 MCI 로 재생 (비동기: play 는 바로 돌아오고 소리는 뒤에서 난다)."""

    def __init__(self):
        import ctypes

        self._send = ctypes.WinDLL("winmm").mciSendStringW
        self._send.restype = ctypes.c_uint32
        self._open = False

    def _cmd(self, cmd: str) -> int:
        return self._send(cmd, None, 0, None)

    def play(self, path: Path, volume: float) -> bool:
        if self._open:
            self._cmd(f"close {ALIAS}")
            self._open = False
        # mpegvideo(DirectShow) 는 mp3 · wav 둘 다 열고 소리 크기도 바꿀 수 있다
        if self._cmd(f'open "{path}" type mpegvideo alias {ALIAS}') != 0:
            return False
        self._open = True
        self._cmd(f"setaudio {ALIAS} volume to {round(volume * 1000)}")
        return self._cmd(f"play {ALIAS} from 0") == 0


class _QtBackend:
    """QtMultimedia 로 재생 (설치돼 있을 때만)."""

    def __init__(self, parent: QObject):
        from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer

        self._out = QAudioOutput(parent)
        self._player = QMediaPlayer(parent)
        self._player.setAudioOutput(self._out)
        self._player.errorOccurred.connect(lambda *_: _fallback())  # 못 읽는 파일 / 소리 장치 없음

    def play(self, path: Path, volume: float) -> bool:
        self._out.setVolume(volume)
        self._player.stop()
        self._player.setSource(QUrl.fromLocalFile(str(path)))
        self._player.play()
        return True


class SoundPlayer(QObject):
    """효과음 하나를 재생한다 (새로 틀면 이전 소리는 멈춤). 재생기는 처음 쓸 때 만든다."""

    def __init__(self):
        super().__init__()
        self._backend = None
        self._tried = False

    def _ensure(self):
        if not self._tried:
            self._tried = True
            try:
                self._backend = _MciBackend() if IS_WINDOWS else _QtBackend(self)
            except Exception:  # 재생 기능을 못 쓰면 기본 알림음만
                self._backend = None
        return self._backend

    def play(self, cid: str, volume: float = 0.8, fallback: bool = True) -> bool:
        """cid 캐릭터의 효과음 (volume 0.0 ~ 1.0). 파일이 없거나 재생에 실패하면 (fallback 이면) 기본 알림음."""
        volume = min(1.0, max(0.0, volume))
        path = sound_file(cid)
        backend = self._ensure() if path else None
        ok = False
        if backend is not None:
            try:
                ok = backend.play(path, volume)
            except Exception:
                ok = False
        if not ok and fallback:
            _fallback()
        return ok


_shared: SoundPlayer | None = None


def player() -> SoundPlayer:
    """앱 전체에서 같이 쓰는 재생기 (알림 · 설정창 '들어 보기')."""
    global _shared
    if _shared is None:
        _shared = SoundPlayer()
    return _shared
