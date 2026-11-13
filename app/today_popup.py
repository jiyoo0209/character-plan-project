"""캐릭터를 누르면 뜨는 '오늘 할 일' 체크리스트 (테마 색 말풍선 모양).

- 줄을 누르면 체크 / 해제 (체크한 일정은 흐려지고 테마 색 빗금이 그어진다)
- 맨 아래 '일정 관리' 를 누르면 달력 창이 열린다
- 바깥을 누르거나 Esc 를 누르면 닫힌다
"""
from __future__ import annotations

from datetime import date

from PySide6.QtCore import QElapsedTimer, QPoint, QPointF, QRect, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QGuiApplication, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QWidget

from .messages import range_day_text
from .categories import category_icon
from .character import IDLE_LIFT
from .config import ASSETS_DIR
from .recurrence import DAY_NAMES
from .storage import Occurrence, ScheduleStore
from .themes import DEFAULT_THEME, FONT_FAMILY, Theme

W = 300  # 말풍선 폭
RADIUS = 20
TAIL = 14  # 꼬리 길이
SH = 8  # 그림자 여백
GAP = IDLE_LIFT + 8  # 꼬리 끝과 캐릭터 머리 사이 (숨쉬며 떠올라도 닿지 않게)
HEAD_H = 86  # 제목 + 날짜 + 진행 막대
ROW_H = 44
EMPTY_H = 92
FOOT_H = 12 + 42 + 14  # 점선 + 일정 관리 버튼 + 아래 여백
MAX_ROWS = 7  # 이보다 많으면 휠로 넘겨 본다
CLOSE_GUARD_MS = 300  # 바깥(캐릭터)을 눌러 닫았을 때 그 클릭으로 바로 다시 열리지 않게


def _font(px: int) -> QFont:
    f = QFont(FONT_FAMILY)
    f.setPixelSize(px)
    return f


_pix_cache: dict[str, QPixmap] = {}


def _pix(path) -> QPixmap:
    key = str(path)
    if key not in _pix_cache:
        _pix_cache[key] = QPixmap(key)
    return _pix_cache[key]


def _round_pen(color: str, width: float) -> QPen:
    pen = QPen(QColor(color), width)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return pen


class TodayPopup(QWidget):
    manage_requested = Signal()  # '일정 관리'

    def __init__(self, store: ScheduleStore, theme: Theme = DEFAULT_THEME):
        super().__init__(None, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.NoDropShadowWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMouseTracking(True)
        self.store = store
        self.theme = theme
        self.day = date.today()
        self.items: list[Occurrence] = []
        self._scroll = 0  # 맨 위에 보이는 줄 번호
        self._hover: object = None  # 줄 번호(int) / 'manage' / None
        self._press: object = None
        self._tail_up = False
        self._tail_x = W // 2
        self._closed = QElapsedTimer()
        store.changed.connect(self._reload)

    # ---- 바깥에서 쓰는 것 ----
    def set_theme(self, t: Theme) -> None:
        self.theme = t
        self.update()

    def just_closed(self) -> bool:
        """방금(바깥 클릭으로) 닫혔는지. 캐릭터 클릭으로 닫힌 경우 다시 열지 않으려고 쓴다."""
        return self._closed.isValid() and self._closed.elapsed() < CLOSE_GUARD_MS

    def open_at(self, anchor: QRect) -> None:
        """anchor(캐릭터 그림이 보이는 영역) 머리 위에 띄운다. 위가 모자라면 발밑에."""
        self.day = date.today()
        self._scroll = 0
        self._hover = self._press = None
        self._reload()
        bw, bh = W, self._body_h()
        self.setFixedSize(bw + 2 * SH, bh + TAIL + 2 * SH)

        screen = QGuiApplication.screenAt(anchor.center()) or QGuiApplication.primaryScreen()
        area = screen.availableGeometry()
        head = QPoint(anchor.center().x(), anchor.top())
        self._tail_up = False
        y = head.y() - GAP - (self.height() - SH)
        if y < area.top():
            self._tail_up = True
            y = anchor.bottom() + GAP - SH
        # 캐릭터가 화면 오른쪽이면 왼쪽으로 펼친다 (말풍선과 같은 규칙)
        frac = 0.72 if head.x() > area.center().x() else 0.28
        x = head.x() - SH - round(bw * frac)
        x = max(area.left() + 4 - SH, min(x, area.right() - self.width() + SH - 4))
        y = max(area.top() - SH, min(y, area.bottom() - self.height() + SH))
        self._tail_x = max(RADIUS + 12, min(head.x() - x - SH, bw - RADIUS - 12))
        self.move(x, y)
        self.show()
        self.raise_()
        self.activateWindow()

    # ---- 내용 ----
    def _reload(self) -> None:
        self.items = self.store.on_date(self.day)
        self._scroll = max(0, min(self._scroll, len(self.items) - MAX_ROWS))
        if self.isVisible() and self.height() != self._body_h() + TAIL + 2 * SH:
            # 일정 수가 바뀌면(달력에서 추가/삭제) 크기를 다시 맞춘다. 발밑 기준은 그대로 둔다
            bottom = self.geometry().bottom()
            self.setFixedSize(W + 2 * SH, self._body_h() + TAIL + 2 * SH)
            if not self._tail_up:
                self.move(self.x(), bottom - self.height() + 1)
        self.update()

    def _visible_rows(self) -> int:
        return min(len(self.items), MAX_ROWS)

    def _body_h(self) -> int:
        rows = self._visible_rows()
        return HEAD_H + (rows * ROW_H if rows else EMPTY_H) + FOOT_H

    def _body(self) -> QRectF:
        return QRectF(SH, SH + (TAIL if self._tail_up else 0), W, self._body_h())

    def _list_rect(self) -> QRectF:
        b = self._body()
        rows = self._visible_rows()
        return QRectF(b.left(), b.top() + HEAD_H, W, rows * ROW_H if rows else EMPTY_H)

    def _row_rect(self, i: int) -> QRectF:
        lr = self._list_rect()
        k = i - self._scroll
        return QRectF(lr.left() + 10, lr.top() + k * ROW_H + 2, W - 20, ROW_H - 4)

    def _manage_rect(self) -> QRectF:
        lr = self._list_rect()
        return QRectF(lr.left() + 10, lr.bottom() + 12, W - 20, 42)

    def _hit(self, pos: QPointF) -> object:
        if self._manage_rect().contains(pos):
            return "manage"
        if self._list_rect().contains(pos):
            for i in range(self._scroll, self._scroll + self._visible_rows()):
                if self._row_rect(i).contains(pos):
                    return i
        return None

    # ---- 마우스 / 키보드 ----
    def mouseMoveEvent(self, e) -> None:
        hit = self._hit(e.position())
        if hit != self._hover:
            self._hover = hit
            self.setCursor(Qt.CursorShape.PointingHandCursor if hit is not None else Qt.CursorShape.ArrowCursor)
            self.update()

    def leaveEvent(self, _e) -> None:
        self._hover = None
        self.update()

    def mousePressEvent(self, e) -> None:
        if not self.rect().contains(e.position().toPoint()):
            super().mousePressEvent(e)  # 바깥 클릭: Qt 가 팝업을 닫는다
            return
        self._press = self._hit(e.position()) if e.button() == Qt.MouseButton.LeftButton else None

    def mouseReleaseEvent(self, e) -> None:
        hit = self._hit(e.position())
        pressed, self._press = self._press, None
        if hit is None or hit != pressed:
            return
        if hit == "manage":
            self.close()
            self.manage_requested.emit()
        else:
            occ = self.items[hit]
            self.store.set_done(occ.id, self.day, not occ.done)  # 저장하면 _reload 로 다시 그린다

    def wheelEvent(self, e) -> None:
        extra = len(self.items) - MAX_ROWS
        if extra <= 0:
            return
        step = -1 if e.angleDelta().y() > 0 else 1
        self._scroll = max(0, min(self._scroll + step, extra))
        self._hover = self._hit(e.position())
        self.update()

    def keyPressEvent(self, e) -> None:
        if e.key() == Qt.Key.Key_Escape:
            self.close()
            return
        super().keyPressEvent(e)

    def hideEvent(self, e) -> None:
        self._closed.start()
        super().hideEvent(e)

    # ---- 그리기 ----
    def _shape(self) -> QPainterPath:
        body = self._body()
        path = QPainterPath()
        path.addRoundedRect(body, RADIUS, RADIUS)
        tx = body.left() + self._tail_x
        tail = QPainterPath()
        if self._tail_up:
            base = body.top() + 1
            tail.moveTo(tx - 11, base)
            tail.quadTo(tx - 2, base - 3, tx + 1, base - TAIL)
            tail.quadTo(tx + 4, base - 4, tx + 9, base)
        else:
            base = body.bottom() - 1
            tail.moveTo(tx - 11, base)
            tail.quadTo(tx - 2, base + 3, tx + 1, base + TAIL)
            tail.quadTo(tx + 4, base + 4, tx + 9, base)
        tail.closeSubpath()
        return path.united(tail).simplified()

    def paintEvent(self, _e) -> None:
        t = self.theme
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        shape = self._shape()
        body = self._body()
        x, y = body.left(), body.top()

        # 그림자 + 본체
        p.setPen(Qt.PenStyle.NoPen)
        for dy, a in ((6, 10), (4, 14), (2, 18)):
            p.setBrush(QColor(0, 0, 0, a))
            p.drawPath(shape.translated(0, dy))
        p.setPen(QPen(QColor(t.line), 2))
        p.setBrush(QColor(t.card))
        p.drawPath(shape)

        self._paint_head(p, t, x, y)
        self._paint_rows(p, t)
        self._paint_foot(p, t)
        p.end()

    def _paint_head(self, p: QPainter, t: Theme, x: float, y: float) -> None:
        head = QPainterPath()
        head.addRoundedRect(QRectF(x + 6, y + 6, W - 12, 72), RADIUS - 5, RADIUS - 5)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(t.bg))
        p.drawPath(head)

        p.setFont(_font(19))
        p.setPen(QColor(t.accent_deep))
        title = "오늘 할 일"
        tw = QFontMetricsF(p.font()).horizontalAdvance(title)
        p.drawText(QRectF(x + 20, y + 16, tw + 4, 26), Qt.AlignmentFlag.AlignVCenter, title)
        ribbon = _pix(t.ribbon)
        if not ribbon.isNull():
            p.drawPixmap(QRectF(x + 20 + tw + 6, y + 18, 22, 22), ribbon, QRectF(ribbon.rect()))
        d = self.day
        p.setFont(_font(12))
        p.setPen(QColor(t.subtext))
        p.drawText(QRectF(x + 20, y + 42, 180, 18), Qt.AlignmentFlag.AlignVCenter,
                   f"{d.month}월 {d.day}일 {DAY_NAMES[d.weekday()]}요일")

        n = len(self.items)
        if not n:
            return
        done = sum(1 for o in self.items if o.done)
        all_done = done == n
        # 몇 개 했는지 알약
        p.setFont(_font(13))
        s = f"{done} / {n}"
        sw = QFontMetricsF(p.font()).horizontalAdvance(s) + 22
        pill = QRectF(x + W - 20 - sw, y + 19, sw, 24)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(t.accent if all_done else t.soft))
        p.drawRoundedRect(pill, 12, 12)
        p.setPen(QColor(t.on_accent if all_done else t.accent_deep))
        p.drawText(pill, Qt.AlignmentFlag.AlignCenter, s)
        # 진행 막대
        bar = QRectF(x + 20, y + 64, W - 40, 6)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(t.line))
        p.drawRoundedRect(bar, 3, 3)
        if done:
            p.setBrush(QColor(t.accent))
            p.drawRoundedRect(QRectF(bar.left(), bar.top(), bar.width() * done / n, 6), 3, 3)

    def _paint_rows(self, p: QPainter, t: Theme) -> None:
        lr = self._list_rect()
        if not self.items:
            p.setFont(_font(15))
            p.setPen(QColor(t.text))
            p.drawText(QRectF(lr.left(), lr.top() + 18, W, 24), Qt.AlignmentFlag.AlignCenter, "오늘은 일정이 없어요")
            p.setFont(_font(12))
            p.setPen(QColor(t.subtext))
            p.drawText(QRectF(lr.left(), lr.top() + 44, W, 20), Qt.AlignmentFlag.AlignCenter, "느긋하게 쉬어도 좋아 ♪")
            return

        p.save()
        p.setClipRect(lr)
        for i in range(self._scroll, self._scroll + self._visible_rows()):
            occ = self.items[i]
            on, hover = occ.done, self._hover == i
            row = self._row_rect(i)
            cy = row.center().y()
            if hover:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(t.soft))
                p.drawRoundedRect(row, 14, 14)
            self._paint_check(p, t, QPointF(row.left() + 20, cy), 11, on, hover)

            # 시간 알약
            p.setFont(_font(12))
            time_s = range_day_text(occ.nth, occ.span) if occ.is_range else occ.time
            pw = QFontMetricsF(p.font()).horizontalAdvance(time_s) + 16
            pill = QRectF(row.left() + 40, cy - 11, pw, 22)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(t.bg if on else (t.card if hover else t.soft)))
            p.drawRoundedRect(pill, 11, 11)
            p.setPen(QColor(t.subtext if on else t.accent_deep))
            p.drawText(pill, Qt.AlignmentFlag.AlignCenter, time_s)

            left = pill.right() + 8
            icon = category_icon(occ.category)
            if icon:
                ic = _pix(icon)
                p.setOpacity(0.45 if on else 1)
                p.drawPixmap(QRectF(left, cy - 9, 18, 18), ic, QRectF(ic.rect()))
                p.setOpacity(1)
                left += 24

            # 제목 (체크하면 흐리게 + 테마 색 빗금)
            p.setFont(_font(15))
            fm = QFontMetricsF(p.font())
            title = fm.elidedText(occ.title, Qt.TextElideMode.ElideRight, row.right() - 10 - left)
            p.setPen(QColor(t.subtext if on else t.text))
            p.drawText(QRectF(left, row.top(), row.right() - left, row.height()), Qt.AlignmentFlag.AlignVCenter, title)
            if on:
                p.setPen(_round_pen(t.accent, 2.2))
                p.drawLine(QPointF(left - 2, cy + 1), QPointF(left + fm.horizontalAdvance(title) + 2, cy + 1))
        p.restore()

        # 넘겨 볼 게 더 있으면 오른쪽에 얇은 스크롤 표시
        extra = len(self.items) - MAX_ROWS
        if extra > 0:
            track = QRectF(lr.right() - 6, lr.top() + 6, 3, lr.height() - 12)
            hh = track.height() * MAX_ROWS / len(self.items)
            top = track.top() + (track.height() - hh) * self._scroll / extra
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(t.line))
            p.drawRoundedRect(QRectF(track.left(), top, 3, hh), 1.5, 1.5)

    @staticmethod
    def _paint_check(p: QPainter, t: Theme, c: QPointF, r: float, on: bool, hover: bool) -> None:
        if on:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(t.accent))
            p.drawEllipse(c, r, r)
            path = QPainterPath(QPointF(c.x() - r * 0.45, c.y() + r * 0.02))
            path.lineTo(c.x() - r * 0.1, c.y() + r * 0.38)
            path.lineTo(c.x() + r * 0.48, c.y() - r * 0.32)
            p.setPen(_round_pen(t.on_accent, 2.4))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(path)
        else:
            p.setPen(QPen(QColor(t.accent), 2.2))
            p.setBrush(QColor(t.soft if hover else t.card))
            p.drawEllipse(c, r - 1, r - 1)

    def _paint_foot(self, p: QPainter, t: Theme) -> None:
        lr = self._list_rect()
        yline = lr.bottom() + 4
        pen = _round_pen(t.line, 2)
        pen.setDashPattern([2, 3])
        p.setPen(pen)
        p.drawLine(QPointF(lr.left() + 22, yline), QPointF(lr.left() + W - 22, yline))

        row = self._manage_rect()
        hot = self._hover == "manage"
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(t.accent if hot else t.soft))
        p.drawRoundedRect(row, 16, 16)
        ic = _pix(ASSETS_DIR / "icons" / "menu" / "calendar.png")
        p.drawPixmap(QRectF(row.left() + 14, row.center().y() - 10, 20, 20), ic, QRectF(ic.rect()))
        col = t.on_accent if hot else t.accent_deep
        p.setFont(_font(15))
        p.setPen(QColor(col))
        p.drawText(QRectF(row.left() + 44, row.top(), 150, row.height()), Qt.AlignmentFlag.AlignVCenter, "일정 관리")
        p.setPen(_round_pen(col, 2.2))
        ax, ay = row.right() - 20, row.center().y()
        p.drawPolyline([QPointF(ax - 4, ay - 6), QPointF(ax + 2, ay), QPointF(ax - 4, ay + 6)])
