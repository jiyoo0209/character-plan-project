"""자동 업데이트: 깃허브 Releases 의 최신 버전을 확인하고, 설치 파일을 받아 조용히 설치한다.

흐름: UpdateChecker.found(Release) → (사용자가 '지금 업데이트') → Downloader → launch_installer → 앱 종료
설치 파일은 /VERYSILENT 로 돌고, 끝나면 installer.iss 의 [Run] 항목이 앱을 다시 켠다.
"""
from __future__ import annotations

import json
import os
import re
import ssl
import subprocess
import tempfile
import threading
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from .config import DATA_DIR

REPO = "jiyoo0209/character-plan-project"
LATEST_API = f"https://api.github.com/repos/{REPO}/releases/latest"
ASSET_NAME = "CharacterPlan-Setup.exe"
TIMEOUT = 10
CHUNK = 64 * 1024
LOG_FILE = DATA_DIR / "update.log"


def _contexts() -> list[ssl.SSLContext]:
    """HTTPS 인증서 확인 방법들 (앞에서부터 시도).

    1) truststore: 윈도우가 직접 인증서를 확인 (브라우저처럼 필요한 루트 인증서를 알아서 받아 옴)
    2) certifi: 앱에 같이 넣은 인증서 묶음
    3) 파이썬 기본 (윈도우 인증서 저장소를 읽기만 함: 루트 인증서가 아직 없는 PC 에선 실패할 수 있음)
    """
    out: list[ssl.SSLContext] = []
    try:
        import truststore
        out.append(truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT))
    except Exception:
        pass
    try:
        import certifi
        out.append(ssl.create_default_context(cafile=certifi.where()))
    except Exception:
        pass
    out.append(ssl.create_default_context())
    return out


_good_ctx: ssl.SSLContext | None = None  # 한 번 통한 방법은 기억해 두고 계속 쓴다


def _open(url: str):
    """url 을 연다. 인증서 문제로 실패하면 다른 확인 방법으로 다시 시도한다."""
    global _good_ctx
    tries = [_good_ctx] if _good_ctx is not None else _contexts()
    last: Exception | None = None
    for ctx in tries:
        try:
            r = urllib.request.urlopen(_request(url), timeout=TIMEOUT, context=ctx)
            _good_ctx = ctx
            return r
        except urllib.error.HTTPError:
            raise  # 서버가 대답은 했음 (404 등): 다른 방법으로 해도 같다
        except Exception as e:
            last = e
    _good_ctx = None
    raise last if last else OSError("연결 실패")


def log_error(where: str, e: BaseException) -> None:
    """업데이트 실패 이유를 data/update.log 에 남긴다 (최근 것만 짧게)."""
    try:
        old = LOG_FILE.read_text(encoding="utf-8").splitlines()[-200:] if LOG_FILE.exists() else []
        new = [f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {where}: {type(e).__name__}: {e}"]
        LOG_FILE.write_text("\n".join(old + new) + "\n", encoding="utf-8")
    except OSError:
        pass


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
    with _open(LATEST_API) as r:
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
        except Exception as e:  # 인터넷이 없거나 깃허브가 응답하지 않으면 다음에 다시
            log_error("확인", e)
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
            with _open(self.release.url) as r, open(part, "wb") as f:
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
            log_error("받기", e)
            if not self._cancel.is_set():
                self.failed.emit(str(e))


def launch_installer(path: str) -> None:
    """설치 파일을 조용히 실행한다 (앱과 따로 돌도록 분리). 호출한 뒤 앱은 바로 꺼야 한다."""
    args = [path, "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/SP-", "/CLOSEAPPLICATIONS"]
    flags = 0
    if os.name == "nt":
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    subprocess.Popen(args, creationflags=flags, close_fds=True)
