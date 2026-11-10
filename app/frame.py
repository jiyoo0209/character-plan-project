"""둥근 모서리 창: 윈도우 기본 테두리 대신 직접 그린 둥근 창 + 작은 창 버튼.

창 클래스에서 레이아웃을 다 만든 뒤 `self.frame = RoundFrame(self, theme)` 한 줄로 쓴다.
- 기존 레이아웃은 안쪽 판(holder)으로 옮기고, 그 위에 닫기(─ ×) 버튼 줄을 붙인다.
- 빈 곳을 끌면 창이 움직이고, resizable 이면 가장자리를 끌어 크기를 바꾼다.
- 바깥쪽 SHADOW 만큼은 투명한 그림자 영역이다.
"""
from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, QPoint, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QDialog, QHBoxLayout, QPushButton, QVBoxLayout, QWidget

from .themes import Theme

RADIUS = 18
SHADOW = 12
EDGE = 7  # 이 폭 안쪽 가장자리를 끌면 크기 조절


class WinButton(QPushButton):
    """창 오른쪽 위 동그란 버튼 (kind: 'close' / 'min')."""

    def __init__(self, kind: str, theme: Theme, parent: QWidget | None = None):
        super().__init__(parent)
        self.kind, self.theme = kind, theme
        self.setFixedSize(26, 26)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setToolTip("닫기" if kind == "close" else "내리기")

    def paintEvent(self, _e) -> None:
        t = self.theme
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        hot = self.underMouse()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(t.accent if hot else t.soft))
        p.drawEllipse(QRectF(1, 1, 24, 24))
        pen = QPen(QColor(t.on_accent if hot else t.accent_deep), 2.2)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        c, r = 13.0, 4.2
        if self.kind == "close":
            p.drawLine(QPoint(round(c - r), round(c - r)), QPoint(round(c + r), round(c + r)))
            p.drawLine(QPoint(round(c - r), round(c + r)), QPoint(round(c + r), round(c - r)))
        else:
            p.drawLine(QPoint(round(c - r), round(c)), QPoint(round(c + r), round(c)))
        p.end()

    def enterEvent(self, e) -> None:
        self.update()
        super().enterEvent(e)

    def leaveEvent(self, e) -> None:
        self.update()
        super().leaveEvent(e)


class RoundFrame(QObject):
    def __init__(self, win: QWidget, theme: Theme, minimize: bool = False, resizable: bool = False,
                 title_row: QHBoxLayout | None = None):
        """title_row 를 주면 창 버튼을 그 줄 끝에 붙인다 (제목과 × 가 같은 줄)."""
        super().__init__(win)
        self.win, self.theme, self.resizable = win, theme, resizable
        self._drag: QPoint | None = None

        win.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        win.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        # 기존 레이아웃 → 안쪽 판으로 옮기기 (Qt 가 자식 위젯도 같이 옮겨 준다)
        old = win.layout()
        m = old.contentsMargins()
        if title_row is None:
            old.setContentsMargins(m.left(), max(4, m.top() - 14), m.right(), m.bottom())
        self.holder = QWidget(win)
        self.holder.setObjectName("frameHolder")
        self.holder.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.holder.setLayout(old)

        bar = title_row if title_row is not None else QHBoxLayout()
        if title_row is None:
            bar.setContentsMargins(0, 0, 0, 0)
            bar.setSpacing(6)
            bar.addStretch(1)
        self.buttons: list[WinButton] = []
        if minimize:
            b = WinButton("min", theme)
            b.clicked.connect(win.showMinimized)
            self.buttons.append(b)
            bar.addWidget(b, 0, Qt.AlignmentFlag.AlignVCenter)
        close = WinButton("close", theme)
        close.clicked.connect(win.reject if isinstance(win, QDialog) else win.close)
        self.buttons.append(close)
        bar.addWidget(close, 0, Qt.AlignmentFlag.AlignVCenter)

        outer = QVBoxLayout(win)
        outer.setSpacing(0)
        outer.setSizeConstraint(old.sizeConstraint())
        if title_row is None:
            outer.setContentsMargins(SHADOW, SHADOW + 8, SHADOW + 8, SHADOW)
            outer.addLayout(bar)
        else:
            outer.setContentsMargins(SHADOW, SHADOW, SHADOW, SHADOW)
        outer.addWidget(self.holder, 1)

        # 고정 폭 창은 그림자만큼 넓혀 준다
        if win.minimumWidth() == win.maximumWidth() and win.minimumWidth() > 0:
            win.setFixedWidth(win.minimumWidth() + 2 * SHADOW)

        if resizable:
            win.setMouseTracking(True)
            self.holder.setMouseTracking(True)
        win.installEventFilter(self)

    # ---- 테마 ----
    def set_theme(self, t: Theme) -> None:
        self.theme = t
        for b in self.buttons:
            b.theme = t
            b.update()
        self.win.update()

    # ---- 그리기 ----
    def _body(self) -> QRectF:
        return QRectF(self.win.rect()).adjusted(SHADOW, SHADOW, -SHADOW, -SHADOW)

    def _paint(self) -> None:
        t = self.theme
        p = QPainter(self.win)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        body = self._body()
        # 부드러운 그림자: 바깥으로 갈수록 옅게, 살짝 아래로
        p.setBrush(Qt.BrushStyle.NoBrush)
        for i in range(1, SHADOW + 1):
            a = int(34 * (1 - i / (SHADOW + 1)) ** 2)
            p.setPen(QPen(QColor(60, 40, 30, a), 1.2))
            r = body.adjusted(-i, -i + 2, i, i + 2)
            p.drawRoundedRect(r, RADIUS + i, RADIUS + i)
        path = QPainterPath()
        path.addRoundedRect(body, RADIUS, RADIUS)
        p.fillPath(path, QColor(t.bg))
        p.setPen(QPen(QColor(t.line), 1.6))
        p.drawPath(path)
        p.end()

    # ---- 끌기 / 크기 조절 ----
    def _edges(self, pos: QPoint) -> Qt.Edge:
        if not self.resizable or self.win.isMaximized():
            return Qt.Edge(0)
        b = self._body().adjusted(EDGE, EDGE, -EDGE, -EDGE)
        e = Qt.Edge(0)
        if pos.x() < b.left():
            e |= Qt.Edge.LeftEdge
        elif pos.x() > b.right():
            e |= Qt.Edge.RightEdge
        if pos.y() < b.top():
            e |= Qt.Edge.TopEdge
        elif pos.y() > b.bottom():
            e |= Qt.Edge.BottomEdge
        return e

    @staticmethod
    def _cursor(e: Qt.Edge) -> Qt.CursorShape:
        L, R, T, B = Qt.Edge.LeftEdge, Qt.Edge.RightEdge, Qt.Edge.TopEdge, Qt.Edge.BottomEdge
        if e in (L | T, R | B):
            return Qt.CursorShape.SizeFDiagCursor
        if e in (R | T, L | B):
            return Qt.CursorShape.SizeBDiagCursor
        if e in (L, R):
            return Qt.CursorShape.SizeHorCursor
        if e in (T, B):
            return Qt.CursorShape.SizeVerCursor
        return Qt.CursorShape.ArrowCursor

    def eventFilter(self, obj, ev) -> bool:
        if obj is not self.win:
            return False
        et = ev.type()
        if et == QEvent.Type.Paint:
            self._paint()
            return False
        if et == QEvent.Type.MouseButtonPress and ev.button() == Qt.MouseButton.LeftButton:
            pos = ev.position().toPoint()
            handle = self.win.windowHandle()
            edges = self._edges(pos)
            if edges and handle is not None and handle.startSystemResize(edges):
                return True
            if handle is None or not handle.startSystemMove():
                self._drag = ev.globalPosition().toPoint() - self.win.frameGeometry().topLeft()
            return True
        if et == QEvent.Type.MouseMove:
            if self._drag is not None and ev.buttons() & Qt.MouseButton.LeftButton:
                self.win.move(ev.globalPosition().toPoint() - self._drag)
                return True
            if self.resizable:
                self.win.setCursor(self._cursor(self._edges(ev.position().toPoint())))
            return False
        if et == QEvent.Type.MouseButtonRelease:
            self._drag = None
            return False
        return False
