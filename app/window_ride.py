"""활성 창 위에 올라타기.

지금 쓰고 있는 창(활성 창)의 제목 표시줄 위에 캐릭터가 앉아서 창을 따라다닌다.
- 다른 창을 활성화하면 그 창으로 폴짝 뛰어 옮겨 탄다.
- 창을 닫거나 최소화/최대화하면 바탕화면 원래 자리로 떨어진다.
- 바탕화면을 클릭하거나 Win+D 를 누르면 원래 자리로 돌아간다.
- 올라타 있는 동안 가끔 제목 표시줄 위를 걸어 다닌다.
- 캐릭터를 끌어서 놓으면 그 자리가 새 집이 되고, 다른 창을 활성화하면 다시 올라탄다.

좌표는 모두 Win32 물리 픽셀 기준 (모니터 배율과 상관없이 어긋나지 않게).
그림은 기존 캐릭터 이미지 하나만 쓰고, 점프·기울기·걷기 흔들림은 코드로 만든다.
"""
from __future__ import annotations

import math
import os
import random
import sys
from typing import Callable

from PySide6.QtCore import QElapsedTimer, QObject, QTimer, Signal

from . import desktop

Rect = tuple[int, int, int, int]  # left, top, right, bottom

TICK_MS = 20
CAPTION_BUTTONS = 150  # 창 오른쪽 위 최소화/최대화/닫기 버튼 자리 (100% 배율 기준 px)
WALK_SPEED = 70  # 걷는 속도 px/s (100% 배율 기준)
FIRST_WANDER = 3.0  # 올라타고 몇 초 뒤 처음 걸을지
WANDER_EVERY = (6.0, 12.0)  # 그다음엔 이 범위에서 아무 때나


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


class Motion:
    """시작점에서 end_fn() 이 가리키는 곳까지 포물선으로 날아간다 (도착점이 움직여도 따라감)."""

    def __init__(self, start, end_fn: Callable[[], tuple[float, float]], duration, arc, fall, t0):
        self.x0, self.y0 = start
        self.end_fn = end_fn
        self.duration = duration
        self.arc = arc
        self.fall = fall  # True: 아래로 떨어짐 (중력처럼 점점 빨라짐)
        self.t0 = t0

    def at(self, t: float) -> tuple[float, float]:
        x1, y1 = self.end_fn()
        ey = t * t if self.fall else t
        return self.x0 + (x1 - self.x0) * t, self.y0 + (y1 - self.y0) * ey - self.arc * 4 * t * (1 - t)


class Rider(QObject):
    moved = Signal()  # 캐릭터 창 위치가 바뀜 (말풍선 따라가기)
    landed = Signal(bool)  # 착지. True = 바탕화면 자리로 돌아옴

    def __init__(self, backend, character, enabled: Callable[[], bool]):
        super().__init__()
        self.b = backend
        self.ch = character
        self.enabled = enabled
        self.state = "home"  # home | fly | ride
        self.target = 0  # 올라탄(또는 날아가는) 창
        self.want = 0  # 올라타고 싶은 창 (지금 활성 창)
        self.home: tuple[int, int] | None = None  # 바탕화면 자리 (물리 px, 창 왼쪽 위)
        self.offset = 0.0  # 창 왼쪽 끝 ~ 캐릭터 가운데
        self.motion: Motion | None = None
        self.walk_goal: float | None = None
        self.next_wander = 0.0
        self._last_perch: tuple[float, float] | None = None
        self._clock = QElapsedTimer()
        self._clock.start()
        self._last_tick = 0.0
        self._last_fg = backend.foreground() if backend else ("ignore", 0)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.tick)

    def start(self) -> None:
        if self.b is not None:
            self._timer.start(TICK_MS)

    @property
    def at_home(self) -> bool:
        return self.state == "home"

    def now(self) -> float:
        return self._clock.elapsed() / 1000.0

    @property
    def s(self) -> float:
        return self.ch.devicePixelRatioF() or 1.0

    def _rect(self, h: int) -> Rect | None:
        if not h:
            return None
        return self.b.perch_rect(h, self.ch.art_height() * self.s * 0.8)

    # ---- 매 프레임 ----
    def tick(self) -> None:
        now = self.now()
        dt = min(0.1, now - self._last_tick)
        self._last_tick = now
        if self.ch.is_pressed():  # 사용자가 끌고 있는 중
            return
        if not self.enabled():
            if self.target:
                self.go_home()
        else:
            fg = self.b.foreground()
            if fg != self._last_fg:
                self._last_fg = fg
                kind, h = fg
                if kind == "window":
                    self.want = h
                elif kind == "desktop":
                    self.want = 0
                    if self.target:
                        self.go_home()
            if self.want and self.want != self.target and self._rect(self.want):
                self.jump_to(self.want)
        rect = self._rect(self.target)
        if self.target and rect is None:  # 닫힘 / 최소화 / 최대화 / 화면 맨 위로 감
            self.go_home()
        if self.motion is not None:
            self._fly(now)
        elif self.state == "ride":
            self._ride(now, dt, rect)

    # ---- 동작 ----
    def jump_to(self, h: int) -> None:
        rect = self._rect(h)
        if rect is None:
            return
        if self.state == "home":
            self.home = self._pos()
            self.b.detach()
        self.target = h
        lo, hi = self._offset_range(rect)
        self.offset = lo + (hi - lo) * 0.3
        self._launch(self._perch_pos, fall=False)

    def go_home(self) -> None:
        self.target = 0
        self.walk_goal = None
        if self.home is None:
            self.state = "home"
            return
        home = self.home
        self._launch(lambda: home, fall=home[1] >= self._pos()[1])

    def on_dropped(self) -> None:
        """사용자가 캐릭터를 끌어다 놓음 → 그 자리가 새 집. 다른 창을 활성화하면 다시 올라탄다."""
        if self.b is None:
            return
        self.want = self.target = 0
        self.motion = None
        self.walk_goal = None
        self.ch.air = 0
        self.ch.walking = self.ch.grounded = False
        if self.state != "home":
            self.state = "home"
            self.b.set_air(False)
            self.b.attach_desktop()
            self.landed.emit(True)
        self.home = None

    def _launch(self, end_fn, fall: bool) -> None:
        x0, y0 = self._pos()
        x1, y1 = end_fn()
        s = self.s
        dist = math.hypot(x1 - x0, y1 - y0)
        if fall:
            dur, arc = _clamp(0.3 + dist / (2600 * s), 0.35, 0.9), 25 * s
        else:
            dur, arc = _clamp(0.35 + dist / (2200 * s), 0.4, 0.8), 70 * s + max(0, y0 - y1) * 0.3
        self.motion = Motion((x0, y0), end_fn, dur, arc, fall, self.now())
        self.state = "fly"
        self.walk_goal = None
        self.ch.walking = self.ch.grounded = False
        self.ch.air = 1 if x1 >= x0 else -1
        self.b.set_air(True)  # 날아가는 동안엔 모든 창 위로

    def _fly(self, now: float) -> None:
        m = self.motion
        t = min(1.0, (now - m.t0) / m.duration)
        self._move(*m.at(t))
        if t < 1:
            return
        self.motion = None
        self.ch.air = 0
        self.ch.poke()  # 착지하면서 말랑
        self.b.set_air(False)
        if self.target:
            self.state = "ride"
            self.ch.grounded = True
            self.next_wander = now + FIRST_WANDER
            self.b.keep_above(self.target)
            self.landed.emit(False)
        else:
            self.state = "home"
            self.b.attach_desktop()
            self.landed.emit(True)

    def _ride(self, now: float, dt: float, rect: Rect | None) -> None:
        if rect is None:
            return
        s = self.s
        lo, hi = self._offset_range(rect)
        if self.walk_goal is None and now >= self.next_wander and self.ch.mode != "alert":
            if hi - lo > 80 * s:
                goal = random.uniform(lo, hi)
                for _ in range(6):
                    if abs(goal - self.offset) >= 60 * s:
                        break
                    goal = random.uniform(lo, hi)
                self.walk_goal = goal
                self.ch.walking = True
            else:
                self.next_wander = now + WANDER_EVERY[1]
        if self.walk_goal is not None:
            goal = _clamp(self.walk_goal, lo, hi)
            step = WALK_SPEED * s * dt
            if abs(goal - self.offset) <= step:
                self.offset = goal
                self.walk_goal = None
                self.ch.walking = False
                self.next_wander = now + random.uniform(*WANDER_EVERY)
            else:
                self.offset += step if goal > self.offset else -step
        self._move(*self._perch_pos(rect))
        self.b.keep_above(self.target)

    # ---- 위치 계산 ----
    def _offset_range(self, rect: Rect) -> tuple[float, float]:
        """캐릭터 창 가운데가 갈 수 있는 범위 (창 왼쪽 끝 기준).
        그림이 보이는 부분이 창 안에 있고, 오른쪽 위 버튼은 가리지 않게."""
        s = self.s
        half = self._size()[0] / 2
        art_l, art_r = (v * s for v in self.ch.art_span())
        w = rect[2] - rect[0]
        lo = half - art_l + 6 * s
        hi = w - CAPTION_BUTTONS * s - art_r + half
        if hi < lo:  # 좁은 창은 가운데
            lo = hi = w / 2 - (art_l + art_r) / 2 + half
        return lo, hi

    def _perch_pos(self, rect: Rect | None = None) -> tuple[float, float]:
        """캐릭터 발이 제목 표시줄 윗변에 닿는 창 위치."""
        if rect is None:
            rect = self._rect(self.target)
        if rect is None:
            return self._last_perch or self._pos()
        lo, hi = self._offset_range(rect)
        off = _clamp(self.offset, lo, hi)
        ow, oh = self._size()
        s = self.s
        x = rect[0] + off - ow / 2
        y = rect[1] - oh + self.ch.foot_offset() * s + 2 * s
        wa = self.b.work_area(int(x + ow / 2), rect[1])
        x = _clamp(x, wa[0], wa[2] - ow)
        self._last_perch = (x, y)
        return x, y

    def _pos(self) -> tuple[int, int]:
        r = self.b.our_rect()
        return r[0], r[1]

    def _size(self) -> tuple[int, int]:
        r = self.b.our_rect()
        return r[2] - r[0], r[3] - r[1]

    def _move(self, x: float, y: float) -> None:
        x, y = round(x), round(y)
        if (x, y) != self._pos():
            self.b.move(x, y)
            self.moved.emit()


# ---------------------------------------------------------------- Windows
if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    _u = ctypes.WinDLL("user32", use_last_error=True)
    _dwm = ctypes.WinDLL("dwmapi")
    _H = wintypes.HWND

    class _MONITORINFO(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
            ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD),
        ]

    _u.GetForegroundWindow.restype = _H
    _u.GetWindowThreadProcessId.argtypes = [_H, ctypes.POINTER(wintypes.DWORD)]
    _u.GetWindowThreadProcessId.restype = wintypes.DWORD
    _u.GetClassNameW.argtypes = [_H, wintypes.LPWSTR, ctypes.c_int]
    for _name in ("IsWindow", "IsWindowVisible", "IsIconic", "IsZoomed", "GetWindowTextLengthW"):
        getattr(_u, _name).argtypes = [_H]
    _u.GetAncestor.argtypes = [_H, wintypes.UINT]
    _u.GetAncestor.restype = _H
    _u.GetWindow.argtypes = [_H, wintypes.UINT]
    _u.GetWindow.restype = _H
    _u.GetWindowLongW.argtypes = [_H, ctypes.c_int]
    _u.GetWindowLongW.restype = ctypes.c_long
    _u.GetWindowRect.argtypes = [_H, ctypes.POINTER(wintypes.RECT)]
    _u.SetWindowPos.argtypes = [_H, _H, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_uint]
    _u.MonitorFromPoint.argtypes = [wintypes.POINT, wintypes.DWORD]
    _u.MonitorFromPoint.restype = wintypes.HANDLE
    _u.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.POINTER(_MONITORINFO)]
    _u.GetDpiForWindow.argtypes = [_H]
    _u.GetDpiForWindow.restype = wintypes.UINT
    _dwm.DwmGetWindowAttribute.argtypes = [_H, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
    _dwm.DwmGetWindowAttribute.restype = ctypes.c_long

    GA_ROOT, GW_HWNDPREV, GWL_EXSTYLE = 2, 3, -20
    WS_EX_TOPMOST, WS_EX_TOOLWINDOW, WS_EX_NOACTIVATE = 0x8, 0x80, 0x08000000
    DWMWA_EXTENDED_FRAME_BOUNDS, DWMWA_CLOAKED = 9, 14
    SWP_NOSIZE, SWP_NOMOVE, SWP_NOZORDER, SWP_NOACTIVATE, SWP_NOOWNERZORDER = 0x1, 0x2, 0x4, 0x10, 0x200
    HWND_TOPMOST, HWND_NOTOPMOST = _H(-1), _H(-2)


class WinBackend:
    DESKTOP = {"Progman", "WorkerW"}
    # 작업 표시줄, 시작 메뉴, 알림 창 등: 올라타지도 않고 '바탕화면 클릭'으로도 치지 않는다
    SKIP = {
        "Shell_TrayWnd", "Shell_SecondaryTrayWnd", "Windows.UI.Core.CoreWindow", "NotifyIconOverflowWindow",
        "TopLevelWindowForOverflowXamlIsland", "XamlExplorerHostIslandWindow", "ForegroundStaging",
        "MultitaskingViewFrame", "TaskListThumbnailWnd", "#32768",
    }

    def __init__(self, hwnd: int):
        self.hwnd = hwnd
        self.pid = os.getpid()

    def _class(self, h: int) -> str:
        buf = ctypes.create_unicode_buffer(256)
        _u.GetClassNameW(h, buf, 256)
        return buf.value

    def _is_ours(self, h: int) -> bool:
        pid = wintypes.DWORD()
        _u.GetWindowThreadProcessId(h, ctypes.byref(pid))
        return pid.value == self.pid

    def foreground(self) -> tuple[str, int]:
        h = _u.GetForegroundWindow() or 0
        if not h or self._is_ours(h):  # 우리 창(캐릭터, 달력 등)을 눌렀을 땐 그대로
            return ("ignore", 0)
        cls = self._class(h)
        if cls in self.DESKTOP:
            return ("desktop", 0)
        if cls in self.SKIP:
            return ("ignore", 0)
        return ("window", h)

    def _frame(self, h: int) -> Rect:
        r = wintypes.RECT()
        # GetWindowRect 는 보이지 않는 테두리까지 포함하므로 실제로 보이는 창 테두리를 쓴다
        if _dwm.DwmGetWindowAttribute(h, DWMWA_EXTENDED_FRAME_BOUNDS, ctypes.byref(r), ctypes.sizeof(r)) != 0:
            _u.GetWindowRect(h, ctypes.byref(r))
        return r.left, r.top, r.right, r.bottom

    def perch_rect(self, h: int, need_above: float) -> Rect | None:
        """올라탈 수 있는 창이면 창 테두리, 아니면 None."""
        if not _u.IsWindow(h) or not _u.IsWindowVisible(h) or _u.IsIconic(h) or _u.IsZoomed(h):
            return None
        if (_u.GetAncestor(h, GA_ROOT) or 0) != h:
            return None
        if _u.GetWindowLongW(h, GWL_EXSTYLE) & (WS_EX_TOPMOST | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE):
            return None
        if _u.GetWindowTextLengthW(h) == 0:
            return None
        cls = self._class(h)
        if cls in self.DESKTOP or cls in self.SKIP:
            return None
        cloaked = wintypes.DWORD()  # 다른 가상 데스크톱 / 숨겨진 앱 창
        if _dwm.DwmGetWindowAttribute(h, DWMWA_CLOAKED, ctypes.byref(cloaked), 4) == 0 and cloaked.value:
            return None
        l, t, r, b = self._frame(h)
        sc = (_u.GetDpiForWindow(h) or 96) / 96
        if r - l < 240 * sc or b - t < 120 * sc:
            return None
        if t - need_above < self.work_area((l + r) // 2, t)[1]:  # 위에 앉을 자리가 없음 (전체화면 등)
            return None
        return l, t, r, b

    def work_area(self, x: int, y: int) -> Rect:
        mi = _MONITORINFO()
        mi.cbSize = ctypes.sizeof(mi)
        mon = _u.MonitorFromPoint(wintypes.POINT(x, y), 2)  # MONITOR_DEFAULTTONEAREST
        if mon and _u.GetMonitorInfoW(mon, ctypes.byref(mi)):
            w = mi.rcWork
            return w.left, w.top, w.right, w.bottom
        return (-(10**6), -(10**6), 10**6, 10**6)

    def our_rect(self) -> Rect:
        r = wintypes.RECT()
        _u.GetWindowRect(self.hwnd, ctypes.byref(r))
        return r.left, r.top, r.right, r.bottom

    def move(self, x: int, y: int) -> None:
        _u.SetWindowPos(self.hwnd, None, x, y, 0, 0,
                        SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_NOOWNERZORDER)

    def keep_above(self, target: int) -> None:
        """캐릭터를 target 창 바로 위 층에 둔다 (다른 창이 target 을 덮으면 캐릭터도 같이 가려짐)."""
        prev = _u.GetWindow(target, GW_HWNDPREV) or 0
        while prev and self._is_ours(prev):  # 사이에 우리 말풍선이 있어도 괜찮다
            if prev == self.hwnd:
                return
            prev = _u.GetWindow(prev, GW_HWNDPREV) or 0
        if prev and _u.GetWindowLongW(prev, GWL_EXSTYLE) & WS_EX_TOPMOST:
            prev = 0  # target 이 일반 창 중 맨 위 → 일반 창 맨 위로
        _u.SetWindowPos(self.hwnd, prev or None, 0, 0, 0, 0, SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE)

    def set_air(self, on: bool) -> None:
        _u.SetWindowPos(self.hwnd, HWND_TOPMOST if on else HWND_NOTOPMOST, 0, 0, 0, 0,
                        SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE)

    def detach(self) -> None:
        desktop.unpin(self.hwnd)

    def attach_desktop(self) -> None:
        desktop.pin_to_desktop(self.hwnd)
        desktop.send_to_bottom(self.hwnd)


def backend_for(hwnd: int):
    return WinBackend(hwnd) if sys.platform == "win32" else None
