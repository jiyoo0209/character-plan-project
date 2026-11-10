"""바탕화면에 떠 있는 캐릭터 창과 말풍선."""
from __future__ import annotations

import bisect
import math
from pathlib import Path

from PySide6.QtCore import QElapsedTimer, QPoint, QPointF, QRect, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QGuiApplication, QImageReader, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

from .themes import DEFAULT_THEME, FONT_FAMILY, Theme

FRAME_MS = 33  # 약 30fps
PAD_SIDE = 14  # 기울어질 때 잘리지 않도록 여백
PAD_TOP = 34  # 점프 높이만큼 위 여백
PAD_BOTTOM = 4
IDLE_LIFT = 6  # 숨쉬기로 떠오르는 최대 높이
ALERT_LIFT = 26  # 알림 점프 최대 높이
DRAG_THRESHOLD = 4


class CharacterWidget(QWidget):
    clicked = Signal()
    moved = Signal(QPoint)
    menu_requested = Signal(QPoint)

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

        self.set_image(image, height)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self.update)
        self._timer.start(FRAME_MS)

    # ---- 외형 ----
    def set_image(self, image: Path, height: int) -> None:
        self._frames, self._frame_ends = self._load_frames(image, height)
        if self._frames:
            self._pix = self._frames[0]
        else:
            src = QPixmap(str(image))
            if src.isNull():
                raise FileNotFoundError(image)
            self._pix = src.scaledToHeight(height, Qt.TransformationMode.SmoothTransformation)
        self._art = self._opaque_rect(self._pix)
        old_bottom_center = self.geometry().center().x(), self.geometry().bottom()
        self.setFixedSize(self._pix.width() + PAD_SIDE * 2, self._pix.height() + PAD_TOP + PAD_BOTTOM)
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
        """화면 좌표 기준 캐릭터 그림 영역 (말풍선 위치 계산용)."""
        g = self.geometry()
        return QRect(g.x() + PAD_SIDE, g.y() + PAD_TOP, self._pix.width(), self._pix.height())

    @staticmethod
    def _load_frames(image: Path, height: int) -> tuple[list[QPixmap], list[int]]:
        """움직이는 GIF/WebP 면 모든 프레임을 표시 크기로 줄여 담는다.
        원본 해상도 프레임을 계속 들고 있지 않으므로 큰 GIF 도 메모리를 적게 쓴다."""
        reader = QImageReader(str(image))
        if not reader.supportsAnimation() or reader.imageCount() == 1:
            return [], []
        frames, ends, total = [], [], 0
        while reader.canRead():
            img = reader.read()
            if img.isNull():
                break
            delay = reader.nextImageDelay()  # 파일에 적힌 이 프레임의 표시 시간
            frames.append(
                QPixmap.fromImage(img).scaledToHeight(height, Qt.TransformationMode.SmoothTransformation)
            )
            total += delay if delay > 10 else 100  # 지연 0 인 GIF 는 브라우저처럼 100ms 로
            ends.append(total)
        return (frames, ends) if len(frames) > 1 else ([], [])

    def _current_pixmap(self) -> QPixmap:
        if not self._frames:
            return self._pix
        t = self._clock.elapsed() % self._frame_ends[-1]
        return self._frames[bisect.bisect_right(self._frame_ends, t)]

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
        p.drawPixmap(QPointF(-pix.width() / 2, -pix.height()), pix)
        p.end()

    # ---- 마우스: 클릭하면 달력, 끌면 이동, 우클릭 메뉴 ----
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
            Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint,
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
        self.raise_()
        self.update()
        self._hide_timer.start(int(seconds * 1000))

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
