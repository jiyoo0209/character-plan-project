"""자동 업데이트: 깃허브 Releases 의 최신 버전을 확인하고, 설치 파일을 받아 조용히 설치한다.

흐름: UpdateChecker.found(Release) → (사용자가 '지금 업데이트') → Downloader → launch_installer → 앱 종료
설치 파일은 /VERYSILENT 로 돌고, 끝나면 installer.iss 의 [Run] 항목이 앱을 다시 켠다.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
import threading
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import QObject, Signal

REPO = "jiyoo0209/character-plan-project"
LATEST_API = f"https://api.github.com/repos/{REPO}/releases/latest"
ASSET_NAME = "CharacterPlan-Setup.exe"
TIMEOUT = 10
CHUNK = 64 * 1024


@dataclass
class Release:
    version: str
    url: str
    size: int = 0
    notes: list[str] = field(default_factory=list)


def parse_version(text: str) -> tuple[int, ...]:
    """'v0.2.15' → (0, 2, 15). 숫자가 아닌 조각은 0."""
    parts = text.strip().lstrip("vV").split(".")
    return tuple(int(m.group()) if (m := re.match(r"\d+", p)) else 0 for p in parts)


def is_newer(latest: str, current: str) -> bool:
    a, b = parse_version(latest), parse_version(current)
    n = max(len(a), len(b))
    return a + (0,) * (n - len(a)) > b + (0,) * (n - len(b))


def parse_notes(body: str | None) -> list[str]:
    """릴리스 본문에서 '- ' 로 시작하는 줄만 '달라진 점'으로 쓴다."""
    notes = []
    for line in (body or "").splitlines():
        line = line.strip()
        if line[:2] in ("- ", "* "):
            notes.append(line[2:].strip())
    return [n for n in notes if n]


def _request(url: str) -> urllib.request.Request:
    return urllib.request.Request(url, headers={
        "User-Agent": "CharacterPlan-updater",
        "Accept": "application/vnd.github+json",
    })


def fetch_latest() -> Release | None:
    with urllib.request.urlopen(_request(LATEST_API), timeout=TIMEOUT) as r:
        data = json.load(r)
    if data.get("draft") or data.get("prerelease"):
        return None
    asset = next((a for a in data.get("assets", []) if a.get("name") == ASSET_NAME), None)
    if not asset:
        return None
    return Release(
        version=str(data.get("tag_name", "")).lstrip("vV"),
        url=asset["browser_download_url"],
        size=int(asset.get("size") or 0),
        notes=parse_notes(data.get("body")),
    )


class UpdateChecker(QObject):
    """뒤에서 최신 버전을 확인한다. 새 버전이 있을 때만 found 를 보낸다 (오류는 조용히 넘김)."""

    found = Signal(object, bool)  # (Release, 직접 눌러서 확인했나)
    up_to_date = Signal()  # 직접 확인했을 때만
    failed = Signal()  # 직접 확인했을 때만

    def __init__(self, current: str):
        super().__init__()
        self.current = current
        self._busy = False

    def start(self, manual: bool = False) -> None:
        """manual=True: 메뉴의 '업데이트 확인' → 최신이어도 / 실패해도 알려 준다."""
        if self._busy:
            return
        self._busy = True
        threading.Thread(target=self._run, args=(manual,), daemon=True).start()

    def _run(self, manual: bool) -> None:
        try:
            rel = fetch_latest()
            if rel and is_newer(rel.version, self.current):
                self.found.emit(rel, manual)
            elif manual:
                self.up_to_date.emit()
        except Exception:  # 인터넷이 없거나 깃허브가 응답하지 않으면 다음에 다시
            if manual:
                self.failed.emit()
        finally:
            self._busy = False


class Downloader(QObject):
    """설치 파일 받기. progress(받은 바이트, 전체), done(파일 경로), failed(이유)."""

    progress = Signal(int, int)
    done = Signal(str)
    failed = Signal(str)

    def __init__(self, release: Release):
        super().__init__()
        self.release = release
        self._cancel = threading.Event()

    def start(self) -> None:
        threading.Thread(target=self._run, daemon=True).start()

    def cancel(self) -> None:
        self._cancel.set()

    def _run(self) -> None:
        target = Path(tempfile.gettempdir()) / f"CharacterPlan-Setup-{self.release.version}.exe"
        part = target.with_suffix(".part")
        try:
            with urllib.request.urlopen(_request(self.release.url), timeout=TIMEOUT) as r, open(part, "wb") as f:
                total = int(r.headers.get("Content-Length") or self.release.size or 0)
                got = 0
                while chunk := r.read(CHUNK):
                    if self._cancel.is_set():
                        break
                    f.write(chunk)
                    got += len(chunk)
                    self.progress.emit(got, total)
            if self._cancel.is_set():
                part.unlink(missing_ok=True)
                return
            if total and got != total:
                raise OSError("파일을 끝까지 받지 못했어")
            part.replace(target)
            self.done.emit(str(target))
        except Exception as e:
            part.unlink(missing_ok=True)
            if not self._cancel.is_set():
                self.failed.emit(str(e))


def launch_installer(path: str) -> None:
    """설치 파일을 조용히 실행한다 (앱과 따로 돌도록 분리). 호출한 뒤 앱은 바로 꺼야 한다."""
    args = [path, "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/SP-", "/CLOSEAPPLICATIONS"]
    flags = 0
    if os.name == "nt":
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    subprocess.Popen(args, creationflags=flags, close_fds=True)
