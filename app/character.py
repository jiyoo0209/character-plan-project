"""바탕화면에 떠 있는 캐릭터 창과 말풍선."""
from __future__ import annotations

import math
from pathlib import Path

from PySide6.QtCore import QElapsedTimer, QPoint, QPointF, QRect, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QGuiApplication, QMovie, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

FRAME_MS = 33  # 약 30fps
PAD_SIDE = 14  # 기울어질 때 잘리지 않도록 여백
PAD_TOP = 34  # 점프 높이만큼 위 여백
PAD_BOTTOM = 4
DRAG_THRESHOLD = 4


class CharacterWidget(QWidget):
    clicked = Signal()
    moved = Signal(QPoint)
    menu_requested = Signal(QPoint)

    def __init__(self, image: Path, height: int):
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnBottomHint,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setWindowTitle("character")

        self._pix = QPixmap()  # 정지 이미지 (애니메이션이면 첫 프레임, 크기 기준)
        self._movie: QMovie | None = None  # GIF 등 애니메이션 이미지
        self._frames: dict[int, QPixmap] = {}  # 크기 조절한 프레임 캐시
        self._height = height
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
        if self._movie is not None:
            self._movie.stop()
            self._movie.deleteLater()
            self._movie = None
        self._frames = {}
        self._height = height

        movie = QMovie(str(image))
        if movie.isValid() and movie.frameCount() != 1:  # 움직이는 GIF/WebP
            movie.setCacheMode(QMovie.CacheMode.CacheAll)
            movie.jumpToFrame(0)
            src = movie.currentPixmap()
            self._movie = movie
            movie.start()
        else:
            movie.deleteLater()
            src = QPixmap(str(image))
        if src.isNull():
            raise FileNotFoundError(image)
        self._pix = src.scaledToHeight(height, Qt.TransformationMode.SmoothTransformation)
        old_bottom_center = self.geometry().center().x(), self.geometry().bottom()
        self.setFixedSize(self._pix.width() + PAD_SIDE * 2, self._pix.height() + PAD_TOP + PAD_BOTTOM)
        if self.isVisible():  # 크기가 바뀌어도 발 위치는 유지
            self.move(old_bottom_center[0] - self.width() // 2, old_bottom_center[1] - self.height() + 1)

    def body_rect(self) -> QRect:
        """화면 좌표 기준 캐릭터 그림 영역 (말풍선 위치 계산용)."""
        g = self.geometry()
        return QRect(g.x() + PAD_SIDE, g.y() + PAD_TOP, self._pix.width(), self._pix.height())

    def _current_pixmap(self) -> QPixmap:
        if self._movie is None:
            return self._pix
        n = self._movie.currentFrameNumber()
        pm = self._frames.get(n)
        if pm is None:
            pm = self._movie.currentPixmap().scaledToHeight(self._height, Qt.TransformationMode.SmoothTransformation)
            self._frames[n] = pm
        return pm

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
            lift = 26 * math.sin(math.pi * p)
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
    dismissed = Signal()

    RADIUS = 14
    TAIL = 12
    BG = QColor(255, 255, 255, 245)
    BORDER = QColor(53, 89, 74)

    def __init__(self):
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self.label = QLabel()
        self.label.setWordWrap(True)
        self.label.setMaximumWidth(280)
        self.label.setStyleSheet("color:#24332c; font-size:14px;")
        lay = QHBoxLayout(self)
        lay.addWidget(self.label)

        self._tail_up = False
        self._tail_x = 40
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self.dismiss)
        self._apply_margins()

    def _apply_margins(self) -> None:
        t = self.TAIL
        self.layout().setContentsMargins(16, 12 + (t if self._tail_up else 0), 16, 12 + (0 if self._tail_up else t))

    def say(self, text: str, anchor: QRect, seconds: float) -> None:
        """anchor(캐릭터 영역) 머리 위에 말풍선을 띄운다. 위 공간이 없으면 아래에."""
        self.label.setText(text)
        # 줄바꿈 라벨은 adjustSize 시 폭이 좁게 잡히므로, 가장 긴 줄 기준으로 폭을 정한다 (최대 280px)
        fm = self.label.fontMetrics()
        longest = max(fm.horizontalAdvance(line) for line in text.splitlines() or [""])
        self.label.setFixedWidth(min(280, longest + 6))
        screen = QGuiApplication.screenAt(anchor.center()) or QGuiApplication.primaryScreen()
        area = screen.availableGeometry()

        for tail_up in (False, True):
            self._tail_up = tail_up
            self._apply_margins()
            self.adjustSize()
            y = anchor.top() - self.height() + 8 if not tail_up else anchor.bottom() - 8
            if not tail_up and y >= area.top():
                break
        x = anchor.center().x() - self.width() // 2
        x = max(area.left() + 4, min(x, area.right() - self.width() - 4))
        y = max(area.top(), min(y, area.bottom() - self.height()))
        self._tail_x = max(self.RADIUS + 8, min(anchor.center().x() - x, self.width() - self.RADIUS - 8))
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

    def paintEvent(self, _event) -> None:
        r, t = self.RADIUS, self.TAIL
        w, h = self.width() - 2, self.height() - 2
        top = t if self._tail_up else 0
        body_h = h - t
        path = QPainterPath()
        path.addRoundedRect(1, 1 + top, w, body_h, r, r)
        tail = QPainterPath()
        tx = self._tail_x
        if self._tail_up:
            tail.moveTo(tx - 9, top + 2)
            tail.lineTo(tx, 1)
            tail.lineTo(tx + 9, top + 2)
        else:
            tail.moveTo(tx - 9, body_h - 1)
            tail.lineTo(tx, h)
            tail.lineTo(tx + 9, body_h - 1)
        tail.closeSubpath()
        path = path.united(tail)

        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(self.BORDER)
        p.setBrush(self.BG)
        p.drawPath(path.simplified())
        p.end()
