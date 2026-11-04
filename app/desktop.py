"""Windows 바탕화면 레이어 고정.

방식: 캐릭터 창의 소유자(owner)를 바탕화면 창(Progman)으로 지정한다.
- 바탕화면 아이콘 '위', 일반 프로그램 창 '아래'에 머문다.
- Win+D(바탕화면 보기)를 눌러도 숨겨지지 않는다.
- 아이콘 뒤에 그리는 월페이퍼 방식(WorkerW)과 달리 클릭을 직접 받을 수 있다.

탐색기가 재시작되면 Progman 이 새로 만들어지므로, 감시 타이머가 주기적으로 다시 붙인다.
Windows 가 아니면 모든 함수가 아무 일도 하지 않는다.
"""
from __future__ import annotations

import sys

IS_WINDOWS = sys.platform == "win32"

if IS_WINDOWS:
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)

    GWLP_HWNDPARENT = -8
    SW_SHOWNOACTIVATE = 4
    HWND_TOPMOST = wintypes.HWND(-1)
    HWND_NOTOPMOST = wintypes.HWND(-2)
    HWND_BOTTOM = wintypes.HWND(1)
    SWP_NOSIZE, SWP_NOMOVE, SWP_NOACTIVATE = 0x0001, 0x0002, 0x0010
    MB_ICONASTERISK = 0x40

    user32.FindWindowW.restype = wintypes.HWND
    user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.IsIconic.argtypes = [wintypes.HWND]
    user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.SetWindowPos.argtypes = [
        wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_uint,
    ]
    user32.MessageBeep.argtypes = [ctypes.c_uint]

    # 64비트에는 SetWindowLongPtrW, 32비트에는 SetWindowLongW 만 있다.
    _set_long = getattr(user32, "SetWindowLongPtrW", user32.SetWindowLongW)
    _get_long = getattr(user32, "GetWindowLongPtrW", user32.GetWindowLongW)
    _set_long.restype = ctypes.c_ssize_t
    _set_long.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
    _get_long.restype = ctypes.c_ssize_t
    _get_long.argtypes = [wintypes.HWND, ctypes.c_int]


def _progman() -> int:
    return user32.FindWindowW("Progman", None) or 0


def pin_to_desktop(hwnd: int) -> bool:
    """창을 바탕화면 레이어에 붙인다. 이미 붙어 있으면 아무것도 안 함."""
    if not IS_WINDOWS or not hwnd:
        return False
    progman = _progman()
    if not progman:
        return False
    if _get_long(hwnd, GWLP_HWNDPARENT) != progman:
        _set_long(hwnd, GWLP_HWNDPARENT, progman)
    return True


def ensure_visible(hwnd: int) -> None:
    """바탕화면 보기/최소화 등으로 숨겨졌으면 다시 보이게 한다 (포커스는 뺏지 않음)."""
    if not IS_WINDOWS or not hwnd:
        return
    if user32.IsIconic(hwnd) or not user32.IsWindowVisible(hwnd):
        user32.ShowWindow(hwnd, SW_SHOWNOACTIVATE)


def set_topmost(hwnd: int, on: bool) -> None:
    """알림 중에는 다른 창 위로 올렸다가, 끝나면 다시 바탕화면 쪽으로 내린다."""
    if not IS_WINDOWS or not hwnd:
        return
    flags = SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE
    if on:
        # 바탕화면 소유 상태에서는 맨 위로 올라가지 않으므로 잠시 소유를 풀고 올린다
        _set_long(hwnd, GWLP_HWNDPARENT, 0)
        user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, flags)
    else:
        user32.SetWindowPos(hwnd, HWND_NOTOPMOST, 0, 0, 0, 0, flags)
        pin_to_desktop(hwnd)
        send_to_bottom(hwnd)


def send_to_bottom(hwnd: int) -> None:
    """일반 프로그램 창들 아래로 내린다 (바탕화면 아이콘보다는 위)."""
    if not IS_WINDOWS or not hwnd:
        return
    user32.SetWindowPos(hwnd, HWND_BOTTOM, 0, 0, 0, 0, SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE)


def beep() -> None:
    if IS_WINDOWS:
        user32.MessageBeep(MB_ICONASTERISK)
