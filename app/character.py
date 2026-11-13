"""바탕화면에 떠 있는 캐릭터 창과 말풍선."""
from __future__ import annotations

import bisect
import math
import threading
from pathlib import Path

from PySide6.QtCore import QElapsedTimer, QPoint, QPointF, QRect, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (QColor, QFont, QGuiApplication, QImage, QImageReader, QPainter, QPainterPath, QPen,
                           QPixmap)
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

from .themes import DEFAULT_THEME, FONT_FAMILY, Theme

FRAME_MS = 33  # 약 30fps
PAD_SIDE = 14  # 기울어질 때 잘리지 않도록 여백
PAD_TOP = 34  # 점프 높이만큼 위 여백
PAD_BOTTOM = 4
IDLE_LIFT = 6  # 숨쉬기로 떠오르는 최대 높이
ALERT_LIFT = 26  # 알림 점프 최대 높이
DRAG_THRESHOLD = 4
FADE_S = 0.9  # 일과 그림이 바뀔 때 서서히 바뀌는 시간


def decode_image(image: Path, height: int) -> tuple[list[QImage], list[int]]:
    """그림 파일을 표시 크기로 줄인 프레임들로 (다른 스레드에서 불러도 됨: QImage 만 다룬다).
    움직이는 GIF/WebP 면 (프레임들, 각 프레임이 끝나는 누적 시각 ms), 정지 그림이면 ([그림], [])."""
    reader = QImageReader(str(image))
    if reader.supportsAnimation() and reader.imageCount() != 1:
        frames, ends, total = [], [], 0
        while reader.canRead():
            img = reader.read()
            if img.isNull():
                break
            delay = reader.nextImageDelay()  # 파일에 적힌 이 프레임의 표시 시간
            frames.append(img.scaledToHeight(height, Qt.TransformationMode.SmoothTransformation))
            total += delay if delay > 10 else 100  # 지연 0 인 GIF 는 브라우저처럼 100ms 로
            ends.append(total)
        if len(frames) > 1:
            return frames, ends
        if frames:
            return frames[:1], []
    img = QImage(str(image))
    if img.isNull():
        raise FileNotFoundError(image)
    return [img.scaledToHeight(height, Qt.TransformationMode.SmoothTransformation)], []


class CharacterWidget(QWidget):
    clicked = Signal()
    moved = Signal(QPoint)
    menu_requested = Signal(QPoint)
    _decoded = Signal(int, object)  # (요청 번호, (프레임들, 끝 시각들) 또는 예외) — 불러오기 스레드 → 화면

    def __init__(self, image: Path, height: int):
        super().__init__(
            None,
            # 'WindowStaysOnBottomHint' 는 쓰지 않는다: Windows 에서 Qt 가 매번 맨 아래로 끌어내려
            # 알림 때 위로 올릴 수가 없다. 쌓임 순서는 desktop.py 에서 직접 관리한다.
            Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setWindowTitle("character")

        self._pix = QPixmap()  # 정지 이미지 (애니메이션이면 첫 프레임, 크기 기준)
        self._frames: list[QPixmap] = []  # 애니메이션 프레임 (표시 크기로 미리 축소)
        self._frame_ends: list[int] = []  # 각 프레임이 끝나는 누적 시각(ms)
        self.mode = "idle"  # idle | alert
        self._poke_until = 0.0
        self._clock = QElapsedTimer()
        self._clock.start()
        self._press: QPoint | None = None
        self._press_win: QPoint | None = None
        self._dragging = False
        self._fade_from: tuple[list[QPixmap], list[int], QPixmap] | None = None  # 바뀌기 전 그림
        self._fade_start = 0.0
        self._fade_size: tuple[int, int] | None = None  # 서서히 바뀐 뒤 맞출 창 크기
        self._req = 0  # 그림 바꾸기 요청 번호 (늦게 온 예전 결과는 버림)
        self._decoded.connect(self._on_decoded)

        self.set_image(image, height)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self.update)
        self._timer.start(FRAME_MS)

    # ---- 외형 ----
    def set_image(self, image: Path, height: int) -> None:
        """그림을 바로 바꾼다 (처음 켤 때 · 설정을 바꿨을 때)."""
        self._req += 1  # 불러오던 일과 그림이 있으면 버린다
        self._fade_from = self._fade_size = None
        self._apply(*decode_image(image, height))
        self._resize_keep_foot(*self._size_for(self._pix))

    def change_image(self, image: Path, height: int) -> None:
        """그림을 서서히 바꾼다 (하루 일과). 큰 GIF 도 멈칫하지 않게 다른 스레드에서 불러온다."""
        self._req += 1
        req = self._req

        def work():
            try:
                result = decode_image(image, height)
            except Exception as e:  # 못 읽는 파일: 지금 그림 그대로
                result = e
            self._decoded.emit(req, result)

        threading.Thread(target=work, daemon=True).start()

    def _on_decoded(self, req: int, result) -> None:
        if req != self._req or isinstance(result, Exception):
            return
        if self.isVisible():  # 지금 보이는 모습에서 새 그림으로 서서히
            self._fade_from = (self._frames, self._frame_ends, self._current_pixmap())
            self._fade_start = self._now()
        old_w, old_h = self.width(), self.height()
        self._apply(*result)
        w, h = self._size_for(self._pix)
        if self._fade_from is not None:  # 바뀌는 동안은 둘 다 들어가게 크게, 끝나면 새 그림 크기로
            self._fade_size = (w, h)
            w, h = max(w, old_w), max(h, old_h)
        self._resize_keep_foot(w, h)

    def _apply(self, images: list[QImage], ends: list[int]) -> None:
        pixes = [QPixmap.fromImage(img) for img in images]
        self._pix = pixes[0]
        self._frames, self._frame_ends = (pixes, ends) if ends else ([], [])
        self._art = self._opaque_rect(self._pix)

    @staticmethod
    def _size_for(pix: QPixmap) -> tuple[int, int]:
        return pix.width() + PAD_SIDE * 2, pix.height() + PAD_TOP + PAD_BOTTOM

    def _resize_keep_foot(self, w: int, h: int) -> None:
        if (w, h) == (self.width(), self.height()):
            return
        old_bottom_center = self.geometry().center().x(), self.geometry().bottom()
        self.setFixedSize(w, h)
        if self.isVisible():  # 크기가 바뀌어도 발 위치는 유지
            self.move(old_bottom_center[0] - self.width() // 2, old_bottom_center[1] - self.height() + 1)

    @staticmethod
    def _opaque_rect(pix: QPixmap) -> QRect:
        """그림에서 실제로 보이는 부분(투명하지 않은 곳)의 영역. 말풍선 꼬리를 머리에 맞추는 데 쓴다."""
        img = pix.toImage()
        w, h = img.width(), img.height()
        if w == 0 or h == 0:
            return QRect(0, 0, w, h)
        step = 2
        rows = [y for y in range(0, h, step) if any(img.pixelColor(x, y).alpha() > 40 for x in range(0, w, step))]
        cols = [x for x in range(0, w, step) if any(img.pixelColor(x, y).alpha() > 40 for y in range(0, h, step))]
        if not rows or not cols:
            return QRect(0, 0, w, h)
        return QRect(cols[0], rows[0], cols[-1] - cols[0] + 1, rows[-1] - rows[0] + 1)

    def art_rect(self) -> QRect:
        """화면 좌표 기준, 캐릭터 그림 중 실제로 보이는 부분 (머리 위 = top)."""
        b = self.body_rect()
        return self._art.translated(b.topLeft())

    def body_rect(self) -> QRect:
        """화면 좌표 기준 캐릭터 그림 영역 (말풍선 위치 계산용). 그림은 발 아래 가운데 기준으로 그린다."""
        g = self.geometry()
        w, h = self._pix.width(), self._pix.height()
        return QRect(g.x() + (g.width() - w) // 2, g.y() + g.height() - PAD_BOTTOM - h, w, h)

    def _frame_at(self, frames: list[QPixmap], ends: list[int], still: QPixmap) -> QPixmap:
        if not frames:
            return still
        t = self._clock.elapsed() % ends[-1]
        return frames[bisect.bisect_right(ends, t)]

    def _current_pixmap(self) -> QPixmap:
        return self._frame_at(self._frames, self._frame_ends, self._pix)

    # ---- 동작 ----
    def start_alert(self) -> None:
        self.mode = "alert"

    def stop_alert(self) -> None:
        self.mode = "idle"

    def poke(self) -> None:
        self._poke_until = self._now() + 0.45

    def _now(self) -> float:
        return self._clock.elapsed() / 1000.0

    def _pose(self) -> tuple[float, float, float, float]:
        """(위로 뜨는 높이, 회전 각도, 가로 배율, 세로 배율)"""
        t = self._now()
        if self.mode == "alert":
            period = 0.55
            p = (t % period) / period
            lift = ALERT_LIFT * math.sin(math.pi * p)
            angle = 7 * math.sin(2 * math.pi * t / 0.9)
            land = p < 0.1 or p > 0.9  # 착지할 때 찌그러짐
            sx, sy = (1.08, 0.9) if land else (0.97, 1.04)
        else:
            s = math.sin(2 * math.pi * t / 2.6)  # 숨쉬기
            lift = 3 + 3 * s
            angle = 0.0
            sx, sy = 1 + 0.015 * s, 1 - 0.015 * s

        if t < self._poke_until:  # 눌렸을 때 말랑
            p = 1 - (self._poke_until - t) / 0.45
            k = math.sin(math.pi * p)
            sx, sy = sx * (1 + 0.12 * k), sy * (1 - 0.16 * k)
        return lift, angle, sx, sy

    def paintEvent(self, _event) -> None:
        lift, angle, sx, sy = self._pose()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        # 기준점: 발 아래 가운데
        p.translate(self.width() / 2, self.height() - PAD_BOTTOM - lift)
        p.rotate(angle)
        p.scale(sx, sy)
        pix = self._current_pixmap()
        k = 1.0
        if self._fade_from is not None:
            k = (self._now() - self._fade_start) / FADE_S
            if k >= 1:
                k = 1.0
                self._fade_from = None
                if self._fade_size:
                    QTimer.singleShot(0, lambda size=self._fade_size: self._resize_keep_foot(*size))
                    self._fade_size = None
            else:
                k = k * k * (3 - 2 * k)  # 부드럽게 (smoothstep)
                frames, ends, still = self._fade_from
                old = self._frame_at(frames, ends, still) if frames else still
                # 둘 다 반투명해서 비쳐 보이는 순간이 짧게: 예전 그림은 뒤 절반에, 새 그림은 앞 절반에 몰아서
                p.setOpacity(min(1.0, 2 * (1 - k)))
                p.drawPixmap(QPointF(-old.width() / 2, -old.height()), old)
                k = min(1.0, 2 * k)
        p.setOpacity(k)
        p.drawPixmap(QPointF(-pix.width() / 2, -pix.height()), pix)
        p.end()

    # ---- 마우스: 클릭하면 오늘 할 일, 끌면 이동, 우클릭 메뉴 ----
    def mousePressEvent(self, e) -> None:
        if e.button() == Qt.MouseButton.LeftButton:
            self._press = e.globalPosition().toPoint()
            self._press_win = self.pos()
            self._dragging = False

    def mouseMoveEvent(self, e) -> None:
        if self._press is None or not (e.buttons() & Qt.MouseButton.LeftButton):
            return
        delta = e.globalPosition().toPoint() - self._press
        if self._dragging or delta.manhattanLength() > DRAG_THRESHOLD:
            self._dragging = True
            self.move(self._press_win + delta)

    def mouseReleaseEvent(self, e) -> None:
        if e.button() != Qt.MouseButton.LeftButton or self._press is None:
            return
        if self._dragging:
            self.moved.emit(self.pos())
        else:
            self.poke()
            self.clicked.emit()
        self._press = None
        self._dragging = False

    def contextMenuEvent(self, e) -> None:
        self.menu_requested.emit(e.globalPos())


class SpeechBubble(QWidget):
    """캐릭터 머리 위 말풍선 (테마 색).

    꼬리는 항상 캐릭터 머리 꼭대기를 가리킨다. 캐릭터가 화면 오른쪽에 있으면 말풍선은 왼쪽으로,
    왼쪽에 있으면 오른쪽으로 펼쳐져서 화면 끝에 눌리지 않는다. 위 공간이 없으면 발밑에 뜬다.
    """

    dismissed = Signal()

    RADIUS = 18
    TAIL = 14  # 꼬리 길이
    SHADOW = 4  # 아래 그림자 여백
    GAP = 4  # 꼬리 끝과 캐릭터 사이 틈
    MAX_TEXT_W = 340

    def __init__(self, theme: Theme = DEFAULT_THEME):
        super().__init__(
            None,
            # 항상 맨 위가 아니라 캐릭터처럼 바탕화면 층에 뜬다 (다른 창이 위에 있으면 가려짐).
            # 쌓임 순서는 app.py 에서 desktop.stack_under 로 캐릭터 바로 아래에 맞춘다.
            Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self.label = QLabel()
        self.label.setWordWrap(True)
        self.label.setMaximumWidth(self.MAX_TEXT_W)
        lay = QHBoxLayout(self)
        lay.addWidget(self.label)

        self.theme = theme
        self.alert = False  # 일정 알림이면 테두리를 포인트 색으로
        self._tail_up = False
        self._tail_x = 40
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self.dismiss)
        self.set_theme(theme)
        self._apply_margins()

    def set_theme(self, t: Theme) -> None:
        self.theme = t
        f = QFont(FONT_FAMILY)
        f.setPixelSize(15)
        self.label.setFont(f)
        self.label.setStyleSheet(f"color: {t.text}; background: transparent;")
        self.update()

    def _apply_margins(self) -> None:
        t, sh = self.TAIL, self.SHADOW
        self.layout().setContentsMargins(
            18, 13 + (t if self._tail_up else 0), 18, 13 + sh + (0 if self._tail_up else t)
        )

    def say(self, text: str, anchor: QRect, seconds: float, alert: bool = False) -> None:
        """anchor(캐릭터 그림이 보이는 영역) 머리 위에 말풍선을 띄운다."""
        self.alert = alert
        self.label.setText(text)
        # 줄바꿈 라벨은 adjustSize 시 폭이 좁게 잡히므로, 가장 긴 줄 기준으로 폭을 정한다
        fm = self.label.fontMetrics()
        longest = max(fm.horizontalAdvance(line) for line in text.splitlines() or [""])
        self.label.setFixedWidth(min(self.MAX_TEXT_W, longest + 6))
        screen = QGuiApplication.screenAt(anchor.center()) or QGuiApplication.primaryScreen()
        area = screen.availableGeometry()
        head = QPoint(anchor.center().x(), anchor.top())

        for tail_up in (False, True):
            self._tail_up = tail_up
            self._apply_margins()
            self.adjustSize()
            if not tail_up:
                # 꼬리 끝이 머리 위로 살짝 떨어지게. 캐릭터가 떠오르거나 점프해도 말풍선에 닿지 않도록
                # 움직이는 높이만큼 더 띄운다 (말풍선이 캐릭터를 가리지 않게)
                clearance = (ALERT_LIFT + 8 if alert else IDLE_LIFT + 4) + self.GAP
                y = head.y() - clearance - (self.height() - self.SHADOW)
                if y >= area.top():
                    break
            else:
                y = anchor.bottom() + self.GAP  # 위가 모자라면 발밑에
        # 캐릭터가 화면 오른쪽이면 말풍선은 왼쪽으로 (꼬리는 말풍선의 오른쪽 70% 지점), 반대도 마찬가지
        frac = 0.72 if head.x() > area.center().x() else 0.28
        x = head.x() - round(self.width() * frac)
        x = max(area.left() + 4, min(x, area.right() - self.width() - 4))
        y = max(area.top(), min(y, area.bottom() - self.height()))
        self._tail_x = max(self.RADIUS + 12, min(head.x() - x, self.width() - self.RADIUS - 12))
        self.move(x, y)
        self.show()
        self.update()
        if seconds > 0:  # 0 이하면 계속 떠 있음 (기상 · 밥 멘트: 그 그림이 끝날 때 앱이 닫는다)
            self._hide_timer.start(int(seconds * 1000))
        else:
            self._hide_timer.stop()

    def dismiss(self) -> None:
        self._hide_timer.stop()
        if self.isVisible():
            self.hide()
            self.dismissed.emit()

    def mouseReleaseEvent(self, _e) -> None:
        self.dismiss()

    def _shape(self) -> QPainterPath:
        r, t, sh = self.RADIUS, self.TAIL, self.SHADOW
        w, h = self.width() - 3, self.height() - 3 - sh
        top = t if self._tail_up else 0
        body = QRectF(1.5, 1.5 + top, w, h - t)
        path = QPainterPath()
        path.addRoundedRect(body, r, r)
        tx = self._tail_x
        tail = QPainterPath()
        if self._tail_up:  # 위로 향한 꼬리 (말풍선이 발밑에 있을 때)
            base = body.top() + 1
            tail.moveTo(tx - 11, base)
            tail.quadTo(tx - 2, base - 3, tx + 1, 1.5)
            tail.quadTo(tx + 4, base - 4, tx + 9, base)
        else:  # 아래로 향한 꼬리: 살짝 휘어진 말랑한 모양
            base = body.bottom() - 1
            tail.moveTo(tx - 11, base)
            tail.quadTo(tx - 2, base + 3, tx + 1, h + 1.5)
            tail.quadTo(tx + 4, base + 4, tx + 9, base)
        tail.closeSubpath()
        return path.united(tail).simplified()

    def paintEvent(self, _event) -> None:
        t = self.theme
        shape = self._shape()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        # 아래로 살짝 그림자
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 28))
        p.drawPath(shape.translated(0, self.SHADOW - 1))
        # 본체
        p.setPen(QPen(QColor(t.accent if self.alert else t.line), 3 if self.alert else 2))
        p.setBrush(QColor(t.card))
        p.drawPath(shape)
        p.end()
