"""달력 + 일정 편집 창."""
from __future__ import annotations

from datetime import date
from functools import lru_cache
from pathlib import Path

from PySide6.QtCore import QDate, QPoint, QPointF, QRectF, QRegularExpression, QSize, Qt, QTime, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetricsF,
    QPainter,
    QIcon,
    QPainterPath,
    QPen,
    QPixmap,
    QRegularExpressionValidator,
)
from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QStackedWidget,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QVBoxLayout,
    QWidget,
)

from .categories import CATEGORIES, category_icon
from .config import APP_TITLE, empty_image
from .messages import time_text
from .storage import Schedule, ScheduleStore
from .themes import DEFAULT_THEME, FONT_FAMILY, SATURDAY, SUNDAY, Theme, common_style

WEEKDAYS = "월화수목금토일"  # date.weekday() 순서
WEEK_HEADER = "일월화수목금토"  # 달력 위 요일 (일요일부터)

# 일정 목록 항목에 담는 값
ROLE_ID = Qt.ItemDataRole.UserRole
ROLE_TIME = Qt.ItemDataRole.UserRole + 1
ROLE_TITLE = Qt.ItemDataRole.UserRole + 2
ROLE_MEMO = Qt.ItemDataRole.UserRole + 3
ROLE_CATEGORY = Qt.ItemDataRole.UserRole + 4


@lru_cache(maxsize=32)
def _cached_pixmap(path: str) -> QPixmap:
    return QPixmap(path)


def _font(px: int) -> QFont:
    f = QFont(FONT_FAMILY)
    f.setPixelSize(px)
    return f


def qdate_to_date(q: QDate) -> date:
    return date(q.year(), q.month(), q.day())


def scaled_icon(widget: QWidget, path: Path | None, size: int) -> QPixmap:
    """그림을 size(px) 안에 맞춰 화면 배율에 맞게 선명하게 줄인다."""
    pix = QPixmap(str(path)) if path else QPixmap()
    if pix.isNull():
        return pix
    dpr = widget.devicePixelRatioF()
    pix = pix.scaled(round(size * dpr), round(size * dpr), Qt.AspectRatioMode.KeepAspectRatio,
                     Qt.TransformationMode.SmoothTransformation)
    pix.setDevicePixelRatio(dpr)
    return pix


def dialog_style(t: Theme) -> str:
    """일정 추가/수정, 삭제 확인 팝업."""
    return common_style(t) + f"""
QDialog {{ background: {t.bg}; }}
QLabel {{ color: {t.text}; }}
QLabel#title {{ font-size: 20px; color: {t.accent_deep}; }}
QLabel#section {{ font-size: 13px; color: {t.text}; }}
QLabel#message {{ font-size: 17px; color: {t.text}; }}
QLabel#sub {{ font-size: 12px; color: {t.subtext}; }}
QLineEdit, QPlainTextEdit {{
    background: {t.card}; color: {t.text}; font-size: 14px;
    border: 2px solid {t.line}; border-radius: 16px; padding: 7px 12px;
    selection-background-color: {t.accent}; selection-color: {t.on_accent};
}}
QLineEdit:focus, QPlainTextEdit:focus {{ border-color: {t.accent}; }}
QLineEdit[invalid="true"] {{ border-color: {t.accent_deep}; background: {t.soft}; }}
QPushButton#field {{
    background: {t.card}; color: {t.text}; font-size: 14px; text-align: left;
    border: 2px solid {t.line}; border-radius: 16px; padding: 8px 14px;
}}
QPushButton#field:hover {{ border-color: {t.accent}; }}
QPushButton#field:disabled {{ background: {t.bg}; color: {t.subtext}; border: 2px dashed {t.line}; }}
QFrame#popCard {{ background: {t.card}; border: 2px solid {t.line}; border-radius: 22px; }}
QLabel#popTitle {{ font-size: 13px; color: {t.subtext}; }}
QLabel#colon {{ font-size: 40px; color: {t.text}; }}
QLineEdit#timeBox {{
    font-size: 42px; color: {t.text}; background: {t.bg}; padding: 0;
    border: 2px solid {t.line}; border-radius: 18px;
    selection-background-color: transparent; selection-color: {t.accent_deep};
}}
QLineEdit#timeBox[active="true"] {{ background: {t.soft}; border: 3px solid {t.accent}; color: {t.accent_deep}; }}
QPushButton#segTop, QPushButton#segBottom {{
    font-size: 17px; color: {t.subtext}; background: {t.card}; border: 2px solid {t.line};
}}
QPushButton#segTop {{ border-top-left-radius: 16px; border-top-right-radius: 16px; border-bottom: 1px solid {t.line}; }}
QPushButton#segBottom {{ border-bottom-left-radius: 16px; border-bottom-right-radius: 16px; border-top: 1px solid {t.line}; }}
QPushButton#segTop:hover, QPushButton#segBottom:hover {{ color: {t.text}; }}
QPushButton#segTop:checked, QPushButton#segBottom:checked {{
    background: {t.accent}; color: {t.on_accent}; border-color: {t.accent};
}}
QPushButton#cat {{
    background: {t.card}; color: {t.text}; font-size: 13px;
    border: 2px solid {t.line}; border-radius: 16px; padding: 5px 8px; min-height: 20px;
}}
QPushButton#cat:hover {{ border-color: {t.accent}; }}
QPushButton#cat:checked {{ background: {t.soft}; border-color: {t.accent}; color: {t.accent_deep}; }}
QPushButton#primary, QPushButton#ghost {{ padding: 8px 24px; }}
"""


class DateField(QPushButton):
    """날짜 칸 (고정). 달력에서 고른 날짜를 보여주기만 하고 바꿀 수 없다."""

    def __init__(self, d: date, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("field")
        self._date = d
        self.setText(f"{d.year}년 {d.month}월 {d.day}일 ({WEEKDAYS[d.weekday()]})")
        self.setEnabled(False)
        self.setToolTip("날짜는 달력에서 골라 줘")

    def date(self) -> date:
        return self._date


class CategoryPicker(QWidget):
    """카테고리 알약 버튼들. 하나만 고르고, 고른 걸 한 번 더 누르면 해제."""

    COLS = 4

    def __init__(self, theme: Theme, current: str = "", parent: QWidget | None = None):
        super().__init__(parent)
        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(6)
        self.buttons: dict[str, QPushButton] = {}
        for i, (name, _file) in enumerate(CATEGORIES):
            b = QPushButton(f" {name}")
            b.setObjectName("cat")
            b.setCheckable(True)
            b.setChecked(name == current)
            b.setIcon(QIcon(str(category_icon(name))))
            b.setIconSize(QSize(16, 16))
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda on, n=name: self._picked(n, on))
            self.buttons[name] = b
            grid.addWidget(b, i // self.COLS, i % self.COLS)

    def _picked(self, name: str, on: bool) -> None:
        if on:
            for n, b in self.buttons.items():
                if n != name:
                    b.setChecked(False)

    def value(self) -> str:
        return next((n for n, b in self.buttons.items() if b.isChecked()), "")


def place_popup(pop: QWidget, field: QWidget, align_right: bool = False) -> None:
    """팝업을 칸 바로 아래에 띄운다 (화면 아래가 모자라면 칸 위로)."""
    pop.adjustSize()
    x = field.width() - pop.width() if align_right else 0
    pos = field.mapToGlobal(QPoint(x, field.height() + 6))
    screen = field.screen().availableGeometry() if field.screen() else None
    if screen is not None:
        if pos.y() + pop.height() > screen.bottom():
            pos.setY(field.mapToGlobal(QPoint(0, 0)).y() - pop.height() - 6)
        pos.setX(max(screen.left(), min(pos.x(), screen.right() - pop.width())))
    pop.move(pos)


class StepArrow(QPushButton):
    """숫자 칸 위아래의 ▲▼. 누르고 있으면 계속 바뀐다."""

    def __init__(self, up: bool, theme: Theme, parent: QWidget | None = None):
        super().__init__(parent)
        self.is_up, self.theme = up, theme
        self.setFixedSize(46, 20)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAutoRepeat(True)
        self.setAutoRepeatDelay(350)
        self.setAutoRepeatInterval(90)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setStyleSheet("background: transparent; border: none;")

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        cx, cy = self.width() / 2, self.height() / 2
        s = 1 if self.is_up else -1
        path = QPainterPath(QPointF(cx - 7, cy + 3 * s))
        path.lineTo(cx, cy - 4 * s)
        path.lineTo(cx + 7, cy + 3 * s)
        color = self.theme.accent_deep if (self.underMouse() or self.isDown()) else self.theme.accent
        p.setPen(QPen(QColor(color), 2.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        p.drawPath(path)
        p.end()


class TimeBox(QLineEdit):
    """큰 숫자 칸 (시 또는 분). 휠·↑↓ 키로도 바꾼다. 들어오면 테마 색으로 강조."""

    stepped = Signal(int)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("timeBox")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFixedSize(88, 72)
        self.setMaxLength(2)
        self.setValidator(QRegularExpressionValidator(QRegularExpression(r"\d{0,2}"), self))
        self.setProperty("active", False)

    def _set_active(self, on: bool) -> None:
        self.setProperty("active", on)
        self.style().unpolish(self)
        self.style().polish(self)

    def focusInEvent(self, e) -> None:
        super().focusInEvent(e)
        self._set_active(True)
        QTimer.singleShot(0, self.selectAll)

    def focusOutEvent(self, e) -> None:
        super().focusOutEvent(e)
        self._set_active(False)

    def wheelEvent(self, e) -> None:
        self.stepped.emit(1 if e.angleDelta().y() > 0 else -1)

    def keyPressEvent(self, e) -> None:
        if e.key() == Qt.Key.Key_Up:
            self.stepped.emit(1)
        elif e.key() == Qt.Key.Key_Down:
            self.stepped.emit(-1)
        else:
            super().keyPressEvent(e)


class TimePopup(QWidget):
    """시간 입력 창: [오전/오후] [시 ▲▼] : [분 ▲▼]  취소 / 확인.

    - 시 칸에 숫자를 치면 (두 자리, 또는 2~9 한 자리) 분 칸으로 넘어간다
    - ▲▼, 마우스 휠, ↑↓ 키: 시는 1씩, 분은 5분 단위로
    - 엔터 = 확인, Esc 나 바깥 클릭 = 취소
    """

    def __init__(self, field: "TimeField"):
        super().__init__(field, Qt.WindowType.Popup)
        self.field = field
        theme = field.theme
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self._h, self._m = field.time().hour(), field.time().minute()

        card = QFrame(self)
        card.setObjectName("popCard")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(card)
        lay = QVBoxLayout(card)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(8)
        title = QLabel("시간 입력")
        title.setObjectName("popTitle")
        lay.addWidget(title)

        # 오전 / 오후 (위아래로 붙은 칸, 숫자 칸 높이에 맞춤)
        self.am, self.pm = QPushButton("오전"), QPushButton("오후")
        self.am.setObjectName("segTop")
        self.pm.setObjectName("segBottom")
        seg = QVBoxLayout()
        seg.setSpacing(0)
        seg.addStretch(1)  # 위아래 여백을 같게 → 두 칸이 붙어서 숫자 칸 가운데 높이에 온다
        group = QButtonGroup(self)
        for b, pm in ((self.am, False), (self.pm, True)):
            b.setCheckable(True)
            b.setFixedSize(64, 36)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            b.clicked.connect(lambda _c=False, pm=pm: self._set_pm(pm))
            group.addButton(b)
            seg.addWidget(b)
        seg.addStretch(1)

        self.hour, self.minute = TimeBox(), TimeBox()
        self.hour.textEdited.connect(self._hour_typed)
        self.minute.textEdited.connect(self._minute_typed)
        self.hour.editingFinished.connect(self._hour_done)
        self.minute.editingFinished.connect(self._minute_done)
        self.hour.stepped.connect(self._step_hour)
        self.minute.stepped.connect(self._step_minute)

        colon = QLabel(":")
        colon.setObjectName("colon")
        colon.setAlignment(Qt.AlignmentFlag.AlignCenter)

        row = QHBoxLayout()
        row.setSpacing(10)
        row.addLayout(seg)
        row.addSpacing(6)
        row.addLayout(self._stepper(self.hour, self._step_hour, theme))
        row.addWidget(colon, 0, Qt.AlignmentFlag.AlignVCenter)
        row.addLayout(self._stepper(self.minute, self._step_minute, theme))
        lay.addLayout(row)

        cancel, ok = QPushButton("취소"), QPushButton("확인")
        cancel.setObjectName("ghost")
        ok.setObjectName("primary")
        for b in (cancel, ok):
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        cancel.clicked.connect(self.close)
        ok.clicked.connect(self._ok)
        foot = QHBoxLayout()
        foot.addStretch(1)
        foot.addWidget(cancel)
        foot.addWidget(ok)
        lay.addSpacing(4)
        lay.addLayout(foot)

        self._sync()

    @staticmethod
    def _stepper(box: TimeBox, step, theme: Theme) -> QVBoxLayout:
        col = QVBoxLayout()
        col.setSpacing(2)
        up, down = StepArrow(True, theme), StepArrow(False, theme)
        up.clicked.connect(lambda: step(1))
        down.clicked.connect(lambda: step(-1))
        col.addWidget(up, 0, Qt.AlignmentFlag.AlignHCenter)
        col.addWidget(box)
        col.addWidget(down, 0, Qt.AlignmentFlag.AlignHCenter)
        return col

    # ---- 값 ----
    def _h12(self) -> int:
        return self._h % 12 or 12

    def _sync(self) -> None:
        self.hour.setText(f"{self._h12():02d}")
        self.minute.setText(f"{self._m:02d}")
        (self.pm if self._h >= 12 else self.am).setChecked(True)

    def _set_hour12(self, h12: int) -> None:
        self._h = h12 % 12 + (12 if self._h >= 12 else 0)

    def _set_pm(self, pm: bool) -> None:
        self._h = self._h % 12 + (12 if pm else 0)
        self._sync()

    # ---- 타이핑 ----
    def _hour_typed(self, text: str) -> None:
        if not text:
            return
        v = int(text)
        if len(text) == 2 or v >= 2:  # 다 쳤다
            if 1 <= v <= 12:
                self._set_hour12(v)
                self.hour.setText(f"{v:02d}")
                self.minute.setFocus()
            else:  # 13, 00 같은 건 되돌린다
                self.hour.setText(f"{self._h12():02d}")
                self.hour.selectAll()

    def _minute_typed(self, text: str) -> None:
        if len(text) == 2:
            v = int(text)
            if v <= 59:
                self._m = v
            else:
                self.minute.setText(f"{self._m:02d}")
                self.minute.selectAll()

    def _hour_done(self) -> None:
        t = self.hour.text()
        if t and 1 <= int(t) <= 12:
            self._set_hour12(int(t))
        self.hour.setText(f"{self._h12():02d}")

    def _minute_done(self) -> None:
        t = self.minute.text()
        if t and int(t) <= 59:
            self._m = int(t)
        self.minute.setText(f"{self._m:02d}")

    # ---- ▲▼ / 휠 / 화살표 키 ----
    def _step_hour(self, d: int) -> None:
        self._hour_done()
        self._set_hour12((self._h12() - 1 + d) % 12 + 1)
        self._sync()
        self.hour.setFocus()
        self.hour.selectAll()

    def _step_minute(self, d: int) -> None:
        self._minute_done()
        self._m = ((self._m // 5 + 1) * 5 if d > 0 else ((self._m - 1) // 5) * 5) % 60
        self._sync()
        self.minute.setFocus()
        self.minute.selectAll()

    # ---- 확인 ----
    def _ok(self) -> None:
        self._hour_done()
        self._minute_done()
        self.field.set_time(QTime(self._h, self._m))
        self.close()

    def keyPressEvent(self, e) -> None:
        if e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._ok()
        else:
            super().keyPressEvent(e)

    def showEvent(self, e) -> None:
        super().showEvent(e)
        self.hour.setFocus()


class TimeField(QPushButton):
    """시간 칸. 누르면 시간 입력 창(TimePopup)이 열린다."""

    def __init__(self, t: QTime, theme: Theme, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("field")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.theme = theme
        self._time = t
        self._sync()
        self.clicked.connect(self._open)

    def time(self) -> QTime:
        return self._time

    def set_time(self, t: QTime) -> None:
        self._time = t
        self._sync()

    def _sync(self) -> None:
        self.setText(time_text(self._time.hour(), self._time.minute()))

    def _open(self) -> None:
        pop = TimePopup(self)
        place_popup(pop, self, align_right=True)
        pop.show()


class ScheduleDialog(QDialog):
    """일정 추가/수정."""

    def __init__(self, parent: QWidget, day: date, item: Schedule | None = None, theme: Theme | None = None):
        super().__init__(parent)
        self.theme = theme or getattr(parent, "theme", DEFAULT_THEME)
        self.setWindowTitle("일정 수정" if item else "일정 추가")
        self.setMinimumWidth(380)
        self.setStyleSheet(dialog_style(self.theme))

        title = QLabel("일정 수정" if item else "일정 추가")
        title.setObjectName("title")
        ribbon = QLabel()
        ribbon.setPixmap(scaled_icon(self, self.theme.ribbon, 26))
        head = QHBoxLayout()
        head.setSpacing(6)
        head.addWidget(title)
        head.addWidget(ribbon, 0, Qt.AlignmentFlag.AlignVCenter)
        head.addStretch(1)

        self.title = QLineEdit(item.title if item else "")
        self.title.setPlaceholderText("예: 회의")
        self.title.textChanged.connect(lambda _t: self._mark_invalid(False))
        self.date = DateField(day)
        self.category = CategoryPicker(self.theme, item.category if item else "")
        self.time = TimeField(QTime.fromString(item.time, "HH:mm") if item else QTime(10, 0), self.theme)
        self.memo = QPlainTextEdit(item.memo if item else "")
        self.memo.setPlaceholderText("메모 (안 적어도 돼)")
        self.memo.setFixedHeight(86)

        when = QHBoxLayout()
        when.setSpacing(8)
        when.addWidget(self.date, 3)
        when.addWidget(self.time, 2)

        cancel = QPushButton("취소")
        cancel.setObjectName("ghost")
        ok = QPushButton("저장" if item else "추가")
        ok.setObjectName("primary")
        ok.setDefault(True)
        for b in (cancel, ok):
            b.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel.clicked.connect(self.reject)
        ok.clicked.connect(self._accept)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(cancel)
        buttons.addWidget(ok)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.setSpacing(6)
        lay.addLayout(head)
        lay.addSpacing(10)
        for label, field in (("무슨 일정이야?", self.title), ("언제?", when), ("카테고리", self.category),
                             ("메모", self.memo)):
            sec = QLabel(label)
            sec.setObjectName("section")
            lay.addWidget(sec)
            if isinstance(field, QHBoxLayout):
                lay.addLayout(field)
            else:
                lay.addWidget(field)
            lay.addSpacing(8)
        lay.addSpacing(6)
        lay.addLayout(buttons)

    def _mark_invalid(self, on: bool) -> None:
        if self.title.property("invalid") != on:
            self.title.setProperty("invalid", on)
            self.title.style().unpolish(self.title)
            self.title.style().polish(self.title)

    def _accept(self) -> None:
        if not self.title.text().strip():
            self.title.setFocus()
            self.title.setPlaceholderText("제목을 입력해 줘!")
            self._mark_invalid(True)
            return
        self.accept()

    def values(self) -> tuple[str, date, str, str, str]:
        """(제목, 날짜, HH:MM, 메모, 카테고리)"""
        return (
            self.title.text().strip(),
            self.date.date(),
            self.time.time().toString("HH:mm"),
            self.memo.toPlainText().strip(),
            self.category.value(),
        )


class ConfirmDialog(QDialog):
    """테마 색 확인 창 (예: 일정 삭제). 위에 캐릭터 그림을 띄운다."""

    def __init__(self, parent: QWidget, theme: Theme, message: str, sub: str = "",
                 ok_text: str = "확인", cancel_text: str = "취소", window_title: str = ""):
        super().__init__(parent)
        self.setWindowTitle(window_title or APP_TITLE)
        self.setStyleSheet(dialog_style(theme))
        self.setMinimumWidth(320)

        pic = QLabel()
        pic.setAlignment(Qt.AlignmentFlag.AlignCenter)
        image = empty_image(theme.key)
        pic.setPixmap(scaled_icon(self, image, 84) if image else scaled_icon(self, theme.ribbon, 40))
        msg = QLabel(message)
        msg.setObjectName("message")
        msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        msg.setWordWrap(True)

        cancel = QPushButton(cancel_text)
        cancel.setObjectName("ghost")
        ok = QPushButton(ok_text)
        ok.setObjectName("primary")
        for b in (cancel, ok):
            b.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel.setDefault(True)  # 엔터는 '취소' 쪽 (실수로 지우지 않게)
        cancel.clicked.connect(self.reject)
        ok.clicked.connect(self.accept)
        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        buttons.addStretch(1)
        buttons.addWidget(cancel)
        buttons.addWidget(ok)
        buttons.addStretch(1)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 22, 24, 20)
        lay.setSpacing(6)
        lay.addWidget(pic)
        lay.addSpacing(8)
        lay.addWidget(msg)
        if sub:
            s = QLabel(sub)
            s.setObjectName("sub")
            s.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lay.addWidget(s)
        lay.addSpacing(14)
        lay.addLayout(buttons)


class MonthCalendar(QWidget):
    """테마 색으로 직접 그리는 한 달 달력.

    - 선택한 날: 포인트 색 동그라미, 오늘: 포인트 색 테두리, 일정 있는 날: 숫자 아래 점
    - 위쪽: 'YYYY년 M월', 오늘 버튼, ‹ › 달 넘기기 (마우스 휠로도 넘김)
    - 날짜 한 번 클릭 = 선택, 두 번 클릭 = activated (일정 추가)
    """

    selectionChanged = Signal()
    activated = Signal(QDate)

    PAD, HEADER, WEEK_H = 14, 48, 26

    def __init__(self, theme: Theme = DEFAULT_THEME, parent: QWidget | None = None):
        super().__init__(parent)
        self.theme = theme
        today = QDate.currentDate()
        self._sel = today
        self._year, self._month = today.year(), today.month()
        self._marks: set[QDate] = set()
        self._hover: object = None  # QDate 또는 "prev"/"next"/"today"
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMinimumSize(QSize(320, 300))

    # ---- 바깥에서 쓰는 것 ----
    def selectedDate(self) -> QDate:
        return self._sel

    def setSelectedDate(self, d: QDate) -> None:
        self._year, self._month = d.year(), d.month()
        changed = d != self._sel
        self._sel = d
        self.update()
        if changed:
            self.selectionChanged.emit()

    def setMarkedDates(self, dates: set[QDate]) -> None:
        self._marks = set(dates)
        self.update()

    def set_theme(self, t: Theme) -> None:
        self.theme = t
        self.update()

    # ---- 위치 계산 ----
    def _card(self) -> QRectF:
        return QRectF(self.rect()).adjusted(1, 1, -1, -1)

    def _first_cell(self) -> QDate:
        first = QDate(self._year, self._month, 1)
        return first.addDays(-(first.dayOfWeek() % 7))  # 일요일부터

    def _grid(self) -> QRectF:
        c = self._card()
        top = c.top() + self.HEADER + self.WEEK_H
        return QRectF(c.left() + self.PAD, top, c.width() - 2 * self.PAD, c.bottom() - self.PAD - top)

    def _cell(self, i: int) -> QRectF:
        g = self._grid()
        cw, ch = g.width() / 7, g.height() / 6
        return QRectF(g.left() + (i % 7) * cw, g.top() + (i // 7) * ch, cw, ch)

    def _buttons(self) -> dict[str, QRectF]:
        c = self._card()
        y = c.top() + (self.HEADER - 30) / 2 + 4
        nxt = QRectF(c.right() - self.PAD - 30, y, 30, 30)
        prev = QRectF(nxt.left() - 34, y, 30, 30)
        today = QRectF(prev.left() - 54, y + 2, 48, 26)
        return {"prev": prev, "next": nxt, "today": today}

    def _hit(self, pos: QPointF) -> object:
        for name, r in self._buttons().items():
            if r.contains(pos):
                return name
        for i in range(42):
            if self._cell(i).contains(pos):
                return self._first_cell().addDays(i)
        return None

    def _radius(self) -> float:
        r = self._cell(0)
        return min(17.0, min(r.width(), r.height()) / 2 - 2)

    # ---- 그리기 ----
    def paintEvent(self, _e) -> None:
        t = self.theme
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 카드 바탕
        p.setPen(QPen(QColor(t.line), 2))
        p.setBrush(QColor(t.card))
        p.drawRoundedRect(self._card().adjusted(1, 1, -1, -1), 22, 22)

        # 제목: 2026년 11월
        c = self._card()
        p.setFont(_font(19))
        p.setPen(QColor(t.text))
        p.drawText(QRectF(c.left() + self.PAD + 4, c.top() + 4, 200, self.HEADER),
                   Qt.AlignmentFlag.AlignVCenter, f"{self._year}년 {self._month}월")

        # 오늘 / ‹ › 버튼
        btn = self._buttons()
        r = btn["today"]
        p.setPen(QPen(QColor(t.accent if self._hover == "today" else t.line), 2))
        p.setBrush(QColor(t.card))
        p.drawRoundedRect(r, 13, 13)
        p.setFont(_font(12))
        p.setPen(QColor(t.text))
        p.drawText(r, Qt.AlignmentFlag.AlignCenter, "오늘")
        for name in ("prev", "next"):
            r = btn[name]
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(t.soft if self._hover == name else t.bg))
            p.drawEllipse(r)
            cx, cy, d = r.center().x(), r.center().y(), 4.5
            sign = -1 if name == "prev" else 1
            path = QPainterPath(QPointF(cx - sign * d / 2, cy - d))
            path.lineTo(cx + sign * d / 2, cy)
            path.lineTo(cx - sign * d / 2, cy + d)
            p.setPen(QPen(QColor(t.accent_deep), 2.4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                          Qt.PenJoinStyle.RoundJoin))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(path)

        # 요일
        g = self._grid()
        p.setFont(_font(12))
        for i, w in enumerate(WEEK_HEADER):
            color = SUNDAY if i == 0 else SATURDAY if i == 6 else t.subtext
            p.setPen(QColor(color))
            p.drawText(QRectF(g.left() + i * g.width() / 7, g.top() - self.WEEK_H, g.width() / 7, self.WEEK_H),
                       Qt.AlignmentFlag.AlignCenter, w)

        # 날짜
        today = QDate.currentDate()
        first = self._first_cell()
        rad = self._radius()
        p.setFont(_font(14))
        for i in range(42):
            d = first.addDays(i)
            cell = self._cell(i)
            cen = QPointF(cell.center().x(), cell.center().y() - 1)
            in_month = d.month() == self._month
            sel, is_today = d == self._sel, d == today
            p.setOpacity(1.0 if in_month else 0.35)
            if sel:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(t.accent))
                p.drawEllipse(cen, rad, rad)
            elif self._hover == d:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(t.soft))
                p.drawEllipse(cen, rad, rad)
            if is_today and not sel:
                p.setPen(QPen(QColor(t.accent), 2))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawEllipse(cen, rad - 1, rad - 1)
            if sel:
                color = t.on_accent
            elif i % 7 == 0:
                color = SUNDAY
            elif i % 7 == 6:
                color = SATURDAY
            else:
                color = t.text
            p.setPen(QColor(color))
            p.drawText(QRectF(cen.x() - rad, cen.y() - rad - 1, 2 * rad, 2 * rad), Qt.AlignmentFlag.AlignCenter,
                       str(d.day()))
            if d in self._marks:  # 일정 있는 날: 아래 점
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(t.on_accent if sel else t.accent_deep))
                p.drawEllipse(QPointF(cen.x(), cen.y() + rad - 5.5), 2.6, 2.6)
        p.setOpacity(1.0)
        p.end()

    # ---- 마우스 / 키보드 ----
    def _move_month(self, delta: int) -> None:
        m = self._year * 12 + (self._month - 1) + delta
        self._year, self._month = m // 12, m % 12 + 1
        self.update()

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
        if e.button() != Qt.MouseButton.LeftButton:
            return
        hit = self._hit(e.position())
        if hit == "prev":
            self._move_month(-1)
        elif hit == "next":
            self._move_month(1)
        elif hit == "today":
            self.setSelectedDate(QDate.currentDate())
        elif isinstance(hit, QDate):
            self.setSelectedDate(hit)

    def mouseDoubleClickEvent(self, e) -> None:
        hit = self._hit(e.position())
        if isinstance(hit, QDate):
            self.activated.emit(hit)

    def wheelEvent(self, e) -> None:
        self._move_month(-1 if e.angleDelta().y() > 0 else 1)

    def keyPressEvent(self, e) -> None:
        step = {Qt.Key.Key_Left: -1, Qt.Key.Key_Right: 1, Qt.Key.Key_Up: -7, Qt.Key.Key_Down: 7}.get(e.key())
        if step:
            self.setSelectedDate(self._sel.addDays(step))
        elif e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.activated.emit(self._sel)
        else:
            super().keyPressEvent(e)


class ScheduleDelegate(QStyledItemDelegate):
    """일정 한 줄을 카드처럼: [시간 알약] 제목 / 메모 첫 줄."""

    def __init__(self, theme: Theme, parent=None):
        super().__init__(parent)
        self.theme = theme

    def sizeHint(self, option, index) -> QSize:
        return QSize(option.rect.width(), 74 if index.data(ROLE_MEMO) else 56)

    def paint(self, p: QPainter, option: QStyleOptionViewItem, index) -> None:
        t = self.theme
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(option.rect).adjusted(2, 4, -4, -4)
        sel = bool(option.state & QStyle.StateFlag.State_Selected)
        hover = bool(option.state & QStyle.StateFlag.State_MouseOver)
        p.setPen(QPen(QColor(t.accent if sel else (t.soft if hover else t.line)), 2))
        p.setBrush(QColor(t.soft if sel else t.card))
        p.drawRoundedRect(r, 16, 16)

        # 시간 알약
        time_s = index.data(ROLE_TIME)
        p.setFont(_font(12))
        tw = QFontMetricsF(p.font()).horizontalAdvance(time_s) + 18
        pill = QRectF(r.left() + 12, r.top() + 12, tw, 24)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(t.card if sel else t.soft))
        p.drawRoundedRect(pill, 12, 12)
        p.setPen(QColor(t.accent_deep))
        p.drawText(pill, Qt.AlignmentFlag.AlignCenter, time_s)

        # 카테고리 꼬리표 (오른쪽 위): ● 이름
        right = r.right() - 12
        category = index.data(ROLE_CATEGORY) or ""
        icon = category_icon(category)
        if icon:
            p.setFont(_font(12))
            cw = QFontMetricsF(p.font()).horizontalAdvance(category) + 44
            tag = QRectF(right - cw, pill.top(), cw, 24)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(t.card if sel else t.soft))
            p.drawRoundedRect(tag, 12, 12)
            p.drawPixmap(QRectF(tag.left() + 9, tag.center().y() - 8, 16, 16), _cached_pixmap(str(icon)), QRectF(0, 0, 64, 64))
            p.setPen(QColor(t.text))
            p.drawText(tag.adjusted(31, 0, -10, 0), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, category)
            right = tag.left() - 8

        # 제목, 메모
        left = pill.right() + 10
        p.setFont(_font(15))
        p.setPen(QColor(t.text))
        title = QFontMetricsF(p.font()).elidedText(index.data(ROLE_TITLE), Qt.TextElideMode.ElideRight, right - left)
        p.drawText(QRectF(left, pill.top(), right - left, pill.height()), Qt.AlignmentFlag.AlignVCenter, title)
        memo = index.data(ROLE_MEMO)
        if memo:
            p.setFont(_font(12))
            p.setPen(QColor(t.subtext))
            memo = QFontMetricsF(p.font()).elidedText(memo, Qt.TextElideMode.ElideRight, r.right() - pill.left() - 12)
            p.drawText(QRectF(pill.left() + 2, pill.bottom() + 6, r.right() - pill.left() - 12, 18),
                       Qt.AlignmentFlag.AlignVCenter, memo)
        p.restore()


def window_style(t: Theme) -> str:
    return common_style(t) + f"""
QWidget#calwin {{ background: {t.bg}; }}
QLabel {{ color: {t.text}; }}
QLabel#dayTitle {{ font-size: 21px; color: {t.accent_deep}; }}
QLabel#dayCount {{ font-size: 13px; color: {t.subtext}; }}
QLabel#emptyTitle {{ font-size: 15px; color: {t.text}; }}
QLabel#emptySub {{ font-size: 12px; color: {t.subtext}; }}
QListWidget#schedules {{ background: transparent; border: none; outline: none; }}
QListWidget#schedules::item {{ background: transparent; border: none; }}
QScrollBar:vertical {{ background: transparent; width: 8px; margin: 4px 0; }}
QScrollBar::handle:vertical {{ background: {t.line}; border-radius: 4px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {t.accent}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
QPushButton#primary, QPushButton#ghost {{ font-size: 13px; padding: 6px 16px; border-radius: 17px; }}
"""


class CalendarWindow(QWidget):
    def __init__(self, store: ScheduleStore, theme: Theme = DEFAULT_THEME):
        super().__init__(None, Qt.WindowType.Window)
        self.store = store
        self.theme = theme
        self.setObjectName("calwin")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setWindowTitle(f"{APP_TITLE} - 일정")
        self.resize(720, 440)

        self.calendar = MonthCalendar(theme)
        self.calendar.selectionChanged.connect(self.refresh_list)
        self.calendar.activated.connect(lambda _d: self.add())  # 날짜 두 번 클릭 → 바로 추가

        # 오른쪽: 날짜 제목 + 리본 + 일정 수
        self.day_label = QLabel()
        self.day_label.setObjectName("dayTitle")
        self.ribbon = QLabel()
        self.count_label = QLabel()
        self.count_label.setObjectName("dayCount")
        head = QHBoxLayout()
        head.setSpacing(6)
        head.addWidget(self.day_label)
        head.addWidget(self.ribbon, 0, Qt.AlignmentFlag.AlignVCenter)
        head.addStretch(1)
        head.addWidget(self.count_label, 0, Qt.AlignmentFlag.AlignBottom)

        # 일정 목록 (없으면 안내 화면)
        self.list = QListWidget()
        self.list.setObjectName("schedules")
        self.list.setMouseTracking(True)
        self.list.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.delegate = ScheduleDelegate(theme, self.list)
        self.list.setItemDelegate(self.delegate)
        self.list.itemDoubleClicked.connect(lambda _i: self.edit())
        self.list.currentItemChanged.connect(lambda *_: self._update_buttons())

        empty = QWidget()
        ev = QVBoxLayout(empty)
        ev.addStretch(1)
        self.empty_icon = QLabel()
        self.empty_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        t1 = QLabel("일정이 없어요")
        t1.setObjectName("emptyTitle")
        t2 = QLabel("날짜를 두 번 누르거나\n'일정 추가'를 눌러 봐.")
        t2.setObjectName("emptySub")
        for w in (self.empty_icon, t1, t2):
            w.setAlignment(Qt.AlignmentFlag.AlignCenter)
            ev.addWidget(w)
            if w is self.empty_icon:
                ev.addSpacing(10)  # 그림과 글자 사이
        ev.addStretch(2)
        self.stack = QStackedWidget()
        self.stack.addWidget(self.list)
        self.stack.addWidget(empty)

        self.btn_add = QPushButton("+ 일정 추가")
        self.btn_add.setObjectName("primary")
        self.btn_edit = QPushButton("수정")
        self.btn_edit.setObjectName("ghost")
        self.btn_del = QPushButton("삭제")
        self.btn_del.setObjectName("ghost")
        for b in (self.btn_add, self.btn_edit, self.btn_del):
            b.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_add.clicked.connect(self.add)
        self.btn_edit.clicked.connect(self.edit)
        self.btn_del.clicked.connect(self.delete)

        buttons = QHBoxLayout()
        buttons.setSpacing(6)
        buttons.addWidget(self.btn_edit)
        buttons.addWidget(self.btn_del)
        buttons.addStretch(1)
        buttons.addWidget(self.btn_add)

        right = QVBoxLayout()
        right.setSpacing(8)
        right.addLayout(head)
        right.addWidget(self.stack, 1)
        right.addLayout(buttons)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(18, 18, 18, 18)
        lay.setSpacing(18)
        lay.addWidget(self.calendar, 11)
        lay.addLayout(right, 9)

        self.set_theme(theme)
        store.changed.connect(self.refresh)
        self.refresh()

    # ---- 테마 ----
    def set_theme(self, t: Theme) -> None:
        self.theme = t
        self.setStyleSheet(window_style(t))
        self.calendar.set_theme(t)
        self.delegate.theme = t
        self.list.viewport().update()
        self.ribbon.setPixmap(scaled_icon(self, t.ribbon, 24))
        # 일정 없는 날 그림: 캐릭터 그림(<id>_1.png), 없으면 큰 리본
        pic = empty_image(t.key)
        self.empty_icon.setPixmap(scaled_icon(self, pic, 96) if pic else scaled_icon(self, t.ribbon, 44))

    # ---- 표시 ----
    def selected_day(self) -> date:
        return qdate_to_date(self.calendar.selectedDate())

    def refresh(self) -> None:
        self.calendar.setMarkedDates({QDate.fromString(iso, "yyyy-MM-dd") for iso in self.store.dates_with_schedules()})
        self.refresh_list()

    def refresh_list(self) -> None:
        d = self.selected_day()
        self.day_label.setText(f"{d.month}월 {d.day}일 ({WEEKDAYS[d.weekday()]})")
        current = self._current_id()
        self.list.clear()
        items = self.store.on_date(d)
        for s in items:
            hh, mm = map(int, s.time.split(":"))
            it = QListWidgetItem()
            it.setData(ROLE_ID, s.id)
            it.setData(ROLE_TIME, time_text(hh, mm))
            it.setData(ROLE_TITLE, s.title)
            it.setData(ROLE_MEMO, s.memo.splitlines()[0] if s.memo else "")
            it.setData(ROLE_CATEGORY, s.category)
            it.setToolTip(s.memo)
            self.list.addItem(it)
            if s.id == current:
                self.list.setCurrentItem(it)
        self.count_label.setText(f"일정 {len(items)}개" if items else "")
        self.stack.setCurrentIndex(0 if items else 1)
        self._update_buttons()

    def _current_id(self) -> str | None:
        it = self.list.currentItem()
        return it.data(ROLE_ID) if it else None

    def _update_buttons(self) -> None:
        has = self._current_id() is not None
        self.btn_edit.setEnabled(has)
        self.btn_del.setEnabled(has)

    # ---- 편집 ----
    def add(self) -> None:
        dlg = ScheduleDialog(self, self.selected_day())
        if dlg.exec():
            title, d, t, memo, category = dlg.values()
            self.store.add(title, d, t, memo, category)
            self.calendar.setSelectedDate(QDate(d.year, d.month, d.day))

    def edit(self) -> None:
        sid = self._current_id()
        item = self.store.get(sid) if sid else None
        if not item:
            return
        dlg = ScheduleDialog(self, item.day, item)
        if dlg.exec():
            title, d, t, memo, category = dlg.values()
            self.store.update(sid, title, d, t, memo, category)
            self.calendar.setSelectedDate(QDate(d.year, d.month, d.day))

    def delete(self) -> None:
        sid = self._current_id()
        item = self.store.get(sid) if sid else None
        if not item:
            return
        dlg = ConfirmDialog(self, self.theme, f"'{item.title}' 일정을 지울까?", "지우면 되돌릴 수 없어.",
                            ok_text="지울래", cancel_text="아니", window_title="일정 삭제")
        if dlg.exec():
            self.store.delete(sid)

    def open(self) -> None:
        self.calendar.setSelectedDate(QDate.currentDate())
        self.refresh()
        self.showNormal()
        self.raise_()
        self.activateWindow()
