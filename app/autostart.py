"""Windows 시작 시 자동 실행 (HKCU\\...\\Run 레지스트리, 관리자 권한 불필요)."""
from __future__ import annotations

import sys
from pathlib import Path

from .config import APP_NAME, install_dir, is_frozen

IS_WINDOWS = sys.platform == "win32"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"

if IS_WINDOWS:
    import winreg


def launch_command() -> str:
    if is_frozen():
        return f'"{sys.executable}"'
    # 소스 실행: 콘솔 창이 안 뜨도록 pythonw 사용
    exe = Path(sys.executable)
    pythonw = exe.with_name("pythonw.exe")
    if pythonw.exists():
        exe = pythonw
    return f'"{exe}" "{install_dir() / "main.py"}"'


def is_enabled() -> bool:
    if not IS_WINDOWS:
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.QueryValueEx(key, APP_NAME)
            return True
    except OSError:
        return False


def set_enabled(enabled: bool) -> None:
    if not IS_WINDOWS:
        return
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if enabled:
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, launch_command())
        else:
            try:
                winreg.DeleteValue(key, APP_NAME)
            except FileNotFoundError:
                pass


def refresh_path() -> None:
    """이미 켜져 있으면 현재 실행 경로로 갱신 (설치 폴더를 옮긴 경우 대비)."""
    if is_enabled():
        set_enabled(True)
