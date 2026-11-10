"""업데이트 창: 새 버전 안내 → 받는 중(진행 막대) → 설치하고 다시 켜기."""
from __future__ import annotations

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QDialog, QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QStackedWidget, QVBoxLayout, QWidget,
)

from .calendar_window import Pill, dialog_style, scaled_icon
from .config import empty_image
from .frame import RoundFrame
from .themes import Theme

MAX_NOTES = 4


class ProgressBar(QWidget):
    """테마 색 둥근 진행 막대."""

    def __init__(self, theme: Theme, parent: QWidget | None = None):
        super().__init__(parent)
        self.theme, self.value = theme, 0.0
        self.setFixedHeight(14)

    def set_value(self, v: float) -> None:
        self.value = max(0.0, min(1.0, v))
        self.update()

    def paintEvent(self, _e) -> None:
        t = self.theme
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        p.setPen(QPen(QColor(t.line), 1.2))
        p.setBrush(QColor(t.card))
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        if self.value > 0:
            fill = QRectF(r.left() + 2, r.top() + 2, max(r.height() - 4, (r.width() - 4) * self.value), r.height() - 4)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(t.accent))
            p.drawRoundedRect(fill, fill.height() / 2, fill.height() / 2)
        p.end()


class UpdateDialog(QDialog):
    """stage: 'ask' (안내) / 'download' (받는 중) / 'install' (설치 중) / 'error'."""

    update_clicked = Signal()

    def __init__(self, parent: QWidget | None, theme: Theme, current: str, latest: str, notes: list[str]):
        super().__init__(parent)
        self.theme = theme
        self.setWindowTitle("업데이트")
        self.setStyleSheet(dialog_style(theme) + f"""
QFrame#notes {{ background: {theme.card}; border: 2px solid {theme.line}; border-radius: 16px; }}
QLabel#noteHead {{ font-size: 13px; color: {theme.accent_deep}; }}
QLabel#note {{ font-size: 13px; color: {theme.text}; }}
QLabel#arrow {{ font-size: 15px; color: {theme.subtext}; }}
""")
        self.setFixedWidth(340)

        title = QLabel("업데이트")
        title.setObjectName("title")
        ribbon = QLabel()
        ribbon.setPixmap(scaled_icon(self, theme.ribbon, 26))
        head = QHBoxLayout()
        head.setSpacing(6)
        head.addWidget(title)
        head.addWidget(ribbon, 0, Qt.AlignmentFlag.AlignVCenter)
        head.addStretch(1)

        pic = QLabel()
        pic.setAlignment(Qt.AlignmentFlag.AlignCenter)
        image = empty_image(theme.key)
        pic.setPixmap(scaled_icon(self, image, 84) if image else scaled_icon(self, theme.ribbon, 40))
        self.msg = QLabel()
        self.msg.setObjectName("message")
        self.msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.msg.setWordWrap(True)

        self.pages = QStackedWidget()
        self.pages.addWidget(self._ask_page(current, latest, notes))
        self.pages.addWidget(self._progress_page())

        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 12, 16, 16)
        lay.setSpacing(6)
        lay.addLayout(head)
        lay.addWidget(pic)
        lay.addSpacing(2)
        lay.addWidget(self.msg)
        lay.addSpacing(6)
        lay.addWidget(self.pages)

        self.frame = RoundFrame(self, theme, title_row=head)
        self.set_stage("ask")

    # ---- 페이지 ----
    def _ask_page(self, current: str, latest: str, notes: list[str]) -> QWidget:
        page = QWidget()
        old, new = Pill(self.theme), Pill(self.theme)
        old.setText(f"v{current}")
        old.set_on(False)
        new.setText(f"v{latest}")
        arrow = QLabel("→")
        arrow.setObjectName("arrow")
        ver = QHBoxLayout()
        ver.setSpacing(8)
        ver.addStretch(1)
        ver.addWidget(old)
        ver.addWidget(arrow)
        ver.addWidget(new)
        ver.addStretch(1)

        box = QFrame()
        box.setObjectName("notes")
        bl = QVBoxLayout(box)
        bl.setContentsMargins(14, 10, 14, 12)
        bl.setSpacing(4)
        nh = QLabel("달라진 점")
        nh.setObjectName("noteHead")
        bl.addWidget(nh)
        for line in notes[:MAX_NOTES]:
            lb = QLabel(f"· {line}")
            lb.setObjectName("note")
            lb.setWordWrap(True)
            bl.addWidget(lb)
        if len(notes) > MAX_NOTES:
            more = QLabel(f"· 그리고 {len(notes) - MAX_NOTES}개 더")
            more.setObjectName("sub")
            bl.addWidget(more)
        box.setVisible(bool(notes))

        later = QPushButton("나중에")
        later.setObjectName("ghost")
        go = QPushButton("지금 업데이트")
        go.setObjectName("primary")
        go.setDefault(True)
        for b in (later, go):
            b.setCursor(Qt.CursorShape.PointingHandCursor)
        later.clicked.connect(self.reject)
        go.clicked.connect(self.update_clicked)
        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        buttons.addStretch(1)
        buttons.addWidget(later)
        buttons.addWidget(go)
        buttons.addStretch(1)

        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        lay.addLayout(ver)
        lay.addWidget(box)
        lay.addSpacing(4)
        lay.addLayout(buttons)
        return page

    def _progress_page(self) -> QWidget:
        page = QWidget()
        self.bar = ProgressBar(self.theme)
        self.detail = QLabel()
        self.detail.setObjectName("sub")
        self.detail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cancel = QPushButton("그만 받기")
        self.cancel.setObjectName("ghost")
        self.cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cancel.clicked.connect(self.reject)
        lay = QVBoxLayout(page)
        lay.setContentsMargins(6, 4, 6, 0)
        lay.setSpacing(8)
        lay.addWidget(self.bar)
        lay.addWidget(self.detail)
        lay.addSpacing(4)
        lay.addWidget(self.cancel, 0, Qt.AlignmentFlag.AlignHCenter)
        return page

    # ---- 상태 ----
    def set_stage(self, stage: str, detail: str = "") -> None:
        texts = {
            "ask": "새 버전이 나왔어!",
            "download": "새 버전 받는 중…",
            "install": "설치하고 다시 켤게!\n잠깐만 기다려 줘.",
            "error": "앗, 업데이트를 못 받았어.\n다음에 켤 때 다시 해 볼게.",
        }
        self.msg.setText(texts[stage])
        cur = 0 if stage == "ask" else 1
        self.pages.setCurrentIndex(cur)
        for i in range(self.pages.count()):  # 안 보이는 페이지 크기는 무시 → 창이 내용만큼 줄어든다
            pol = QSizePolicy.Policy.Preferred if i == cur else QSizePolicy.Policy.Ignored
            self.pages.widget(i).setSizePolicy(pol, pol)
        self.bar.setVisible(stage in ("download", "install"))
        self.cancel.setVisible(stage in ("download", "error"))
        self.cancel.setText("닫기" if stage == "error" else "그만 받기")
        self.detail.setText(detail)
        self.detail.setVisible(bool(detail))
        if stage == "install":
            self.bar.set_value(1.0)
        self.pages.adjustSize()
        self.adjustSize()

    def set_progress(self, done: int, total: int) -> None:
        mb = 1024 * 1024
        frac = done / total if total else 0.0
        self.bar.set_value(frac)
        self.detail.setText(f"{round(frac * 100)}%  ·  {done / mb:.1f}MB / {total / mb:.1f}MB")
        self.detail.setVisible(True)
