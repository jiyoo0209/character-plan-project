"""달력 + 일정 편집 창."""
from __future__ import annotations

from datetime import date

from PySide6.QtCore import QDate, QLocale, Qt, QTime
from PySide6.QtGui import QBrush, QColor, QFont, QTextCharFormat
from PySide6.QtWidgets import (
    QCalendarWidget,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

from .config import APP_TITLE
from .messages import time_text
from .storage import Schedule, ScheduleStore

KO = QLocale(QLocale.Language.Korean, QLocale.Country.SouthKorea)
WEEKDAYS = "월화수목금토일"


def qdate_to_date(q: QDate) -> date:
    return date(q.year(), q.month(), q.day())


class ScheduleDialog(QDialog):
    """일정 추가/수정."""

    def __init__(self, parent: QWidget, day: date, item: Schedule | None = None):
        super().__init__(parent)
        self.setWindowTitle("일정 수정" if item else "일정 추가")
        self.setMinimumWidth(320)

        self.title = QLineEdit(item.title if item else "")
        self.title.setPlaceholderText("예: 회의")
        self.date = QDateEdit(QDate(day.year, day.month, day.day))
        self.date.setCalendarPopup(True)
        self.date.setDisplayFormat("yyyy-MM-dd (ddd)")
        self.date.setLocale(KO)
        t = QTime.fromString(item.time, "HH:mm") if item else QTime(10, 0)
        self.time = QTimeEdit(t)
        self.time.setDisplayFormat("AP h:mm")
        self.time.setLocale(KO)
        self.memo = QPlainTextEdit(item.memo if item else "")
        self.memo.setPlaceholderText("메모 (선택)")
        self.memo.setFixedHeight(80)

        form = QFormLayout()
        form.addRow("제목", self.title)
        form.addRow("날짜", self.date)
        form.addRow("시간", self.time)
        form.addRow("메모", self.memo)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("저장")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("취소")
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)

        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addWidget(buttons)

    def _accept(self) -> None:
        if not self.title.text().strip():
            self.title.setFocus()
            self.title.setPlaceholderText("제목을 입력해 줘!")
            return
        self.accept()

    def values(self) -> tuple[str, date, str, str]:
        return (
            self.title.text().strip(),
            qdate_to_date(self.date.date()),
            self.time.time().toString("HH:mm"),
            self.memo.toPlainText().strip(),
        )


class CalendarWindow(QWidget):
    def __init__(self, store: ScheduleStore):
        super().__init__(None, Qt.WindowType.Window)
        self.store = store
        self.setWindowTitle(f"{APP_TITLE} - 일정")
        self.resize(640, 380)

        self.calendar = QCalendarWidget()
        self.calendar.setLocale(KO)
        self.calendar.setGridVisible(True)
        self.calendar.setVerticalHeaderFormat(QCalendarWidget.VerticalHeaderFormat.NoVerticalHeader)
        self.calendar.selectionChanged.connect(self.refresh_list)
        self.calendar.activated.connect(lambda _d: self.add())  # 날짜 더블클릭 → 바로 추가

        self.day_label = QLabel()
        f = self.day_label.font()
        f.setPointSize(f.pointSize() + 2)
        f.setBold(True)
        self.day_label.setFont(f)

        self.list = QListWidget()
        self.list.itemDoubleClicked.connect(lambda _i: self.edit())
        self.list.currentItemChanged.connect(lambda *_: self._update_buttons())

        self.btn_add = QPushButton("추가")
        self.btn_edit = QPushButton("수정")
        self.btn_del = QPushButton("삭제")
        self.btn_today = QPushButton("오늘")
        self.btn_add.clicked.connect(self.add)
        self.btn_edit.clicked.connect(self.edit)
        self.btn_del.clicked.connect(self.delete)
        self.btn_today.clicked.connect(lambda: self.calendar.setSelectedDate(QDate.currentDate()))

        buttons = QHBoxLayout()
        for b in (self.btn_today, self.btn_add, self.btn_edit, self.btn_del):
            buttons.addWidget(b)

        right = QVBoxLayout()
        right.addWidget(self.day_label)
        right.addWidget(self.list, 1)
        right.addLayout(buttons)

        lay = QHBoxLayout(self)
        lay.addWidget(self.calendar, 3)
        lay.addLayout(right, 2)

        store.changed.connect(self.refresh)
        self.refresh()

    # ---- 표시 ----
    def selected_day(self) -> date:
        return qdate_to_date(self.calendar.selectedDate())

    def refresh(self) -> None:
        self._mark_dates()
        self.refresh_list()

    def _mark_dates(self) -> None:
        self.calendar.setDateTextFormat(QDate(), QTextCharFormat())  # 전체 초기화
        fmt = QTextCharFormat()
        fmt.setFontWeight(QFont.Weight.Bold)
        fmt.setBackground(QBrush(QColor(217, 242, 225)))
        fmt.setForeground(QBrush(QColor(40, 90, 60)))
        for iso in self.store.dates_with_schedules():
            self.calendar.setDateTextFormat(QDate.fromString(iso, "yyyy-MM-dd"), fmt)

    def refresh_list(self) -> None:
        d = self.selected_day()
        self.day_label.setText(f"{d.month}월 {d.day}일 ({WEEKDAYS[d.weekday()]})")
        current = self._current_id()
        self.list.clear()
        for s in self.store.on_date(d):
            hh, mm = map(int, s.time.split(":"))
            text = f"{time_text(hh, mm)}   {s.title}"
            if s.memo:
                text += f"\n    {s.memo.splitlines()[0]}"
            it = QListWidgetItem(text)
            it.setData(Qt.ItemDataRole.UserRole, s.id)
            self.list.addItem(it)
            if s.id == current:
                self.list.setCurrentItem(it)
        if self.list.count() == 0:
            empty = QListWidgetItem("일정이 없어요. '추가'를 눌러 보세요.")
            empty.setFlags(Qt.ItemFlag.NoItemFlags)
            self.list.addItem(empty)
        self._update_buttons()

    def _current_id(self) -> str | None:
        it = self.list.currentItem()
        return it.data(Qt.ItemDataRole.UserRole) if it else None

    def _update_buttons(self) -> None:
        has = self._current_id() is not None
        self.btn_edit.setEnabled(has)
        self.btn_del.setEnabled(has)

    # ---- 편집 ----
    def add(self) -> None:
        dlg = ScheduleDialog(self, self.selected_day())
        if dlg.exec():
            title, d, t, memo = dlg.values()
            self.store.add(title, d, t, memo)
            self.calendar.setSelectedDate(QDate(d.year, d.month, d.day))

    def edit(self) -> None:
        sid = self._current_id()
        item = self.store.get(sid) if sid else None
        if not item:
            return
        dlg = ScheduleDialog(self, item.day, item)
        if dlg.exec():
            title, d, t, memo = dlg.values()
            self.store.update(sid, title, d, t, memo)
            self.calendar.setSelectedDate(QDate(d.year, d.month, d.day))

    def delete(self) -> None:
        sid = self._current_id()
        item = self.store.get(sid) if sid else None
        if not item:
            return
        ok = QMessageBox.question(self, "삭제", f"'{item.title}' 일정을 삭제할까요?")
        if ok == QMessageBox.StandardButton.Yes:
            self.store.delete(sid)

    def open(self) -> None:
        self.calendar.setSelectedDate(QDate.currentDate())
        self.refresh()
        self.showNormal()
        self.raise_()
        self.activateWindow()
