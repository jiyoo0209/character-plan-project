"""설정 창: 캐릭터 고르기, 이름, 미리 알림 시간. 고른 캐릭터 색으로 테마가 바뀐다."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QEasingCurve, QPointF, QRectF, QSize, Qt, QVariantAnimation
from PySide6.QtGui import QColor, QFont, QImageReader, QMovie, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (
    QAbstractButton,
    QButtonGroup,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .config import CHARACTERS, Settings, character_image, pick_image
from .themes import DEFAULT_THEME, Theme, theme_for

FONT_FAMILY = "Jua"  # 주아 (assets/fonts/Jua-Regular.ttf, app._load_fonts 에서 등록)
LEAD_CHOICES = (0, 5, 10, 30, 60)  # 미리 알림 선택지(분)


def build_style(t: Theme) -> str:
    return f"""
* {{ font-family: "{FONT_FAMILY}"; }}
QDialog {{ background: {t.bg}; }}
QLabel {{ color: {t.text}; }}
QLabel#title {{ font-size: 20px; font-weight: bold; color: {t.accent_deep}; }}
QLabel#subtitle {{ font-size: 13px; color: {t.subtext}; }}
QLabel#section {{ font-size: 13px; font-weight: bold; color: {t.text}; }}
QLineEdit {{
    background: {t.card}; color: {t.text}; font-size: 14px;
    border: 2px solid {t.line}; border-radius: 16px; padding: 7px 14px;
    selection-background-color: {t.accent}; selection-color: {t.on_accent};
}}
QLineEdit:focus {{ border-color: {t.accent}; }}
QPushButton#chip {{
    background: {t.card}; color: {t.text}; font-size: 13px;
    border: 2px solid {t.line}; border-radius: 15px; padding: 5px 14px; min-height: 18px;
}}
QPushButton#chip:hover {{ border-color: {t.accent}; }}
QPushButton#chip:checked {{
    background: {t.accent}; color: {t.on_accent}; font-weight: bold; border-color: {t.accent};
}}
QPushButton#primary, QPushButton#ghost {{
    font-size: 14px; font-weight: bold; border-radius: 19px; padding: 8px 26px; min-height: 20px;
}}
QPushButton#primary {{ background: {t.accent}; color: {t.on_accent}; border: 2px solid {t.accent}; }}
QPushButton#primary:hover {{ background: {t.accent_deep}; border-color: {t.accent_deep}; color: white; }}
QPushButton#primary:disabled {{ background: {t.line}; border-color: {t.line}; color: {t.card}; }}
QPushButton#ghost {{ background: transparent; color: {t.subtext}; border: 2px solid {t.line}; }}
QPushButton#ghost:hover {{ color: {t.text}; border-color: {t.accent}; }}
"""


# 뽀잉: 고른 카드의 그림이 꾹 눌렸다가 튀어 오르고, 착지해서 말랑하게 흔들린다.
# (진행도, 위로 뜬 높이 px, 가로 배율, 세로 배율) — 그림 아래쪽 가운데를 기준으로 늘이고 줄인다.
BOING_KEYS = (
    (0.00, 0.0, 1.00, 1.00),
    (0.12, 0.0, 1.12, 0.86),  # 꾹 (준비)
    (0.30, 9.0, 0.94, 1.06),  # 뽀잉 (위로 늘어나며 점프)
    (0.46, 0.0, 1.10, 0.88),  # 착지 (납작)
    (0.60, 3.0, 0.97, 1.03),  # 작게 한 번 더
    (0.74, 0.0, 1.03, 0.97),
    (0.87, 0.0, 0.99, 1.01),
    (1.00, 0.0, 1.00, 1.00),
)
BOING_MS = 650


def boing_at(t: float) -> tuple[float, float, float]:
    """진행도 t(0~1)에서 (위로 뜬 높이, 가로 배율, 세로 배율)."""
    for (t0, *a), (t1, *b) in zip(BOING_KEYS, BOING_KEYS[1:]):
        if t <= t1:
            k = (t - t0) / (t1 - t0) if t1 > t0 else 1.0
            k = k * k * (3 - 2 * k)  # 부드럽게 (smoothstep)
            return tuple(x + (y - x) * k for x, y in zip(a, b))
    return 0.0, 1.0, 1.0


def _lead_text(m: int) -> str:
    if m == 0:
        return "안 함"
    if m % 60 == 0:
        return f"{m // 60}시간 전"
    return f"{m}분 전"


class CharacterCard(QAbstractButton):
    """캐릭터 고르기 카드.

    평소엔 그림이 첫 장면으로 멈춰 있고, 고르는 순간 뽀잉 튀어 오르면서
    GIF 를 PICK_LOOPS 바퀴 재생한 뒤 다시 첫 장면으로 멈춘다.
    """

    PICK_LOOPS = 1  # 골랐을 때 GIF 재생 바퀴 수

    W, H, IMG, IMG_TOP = 118, 146, 82, 18

    def __init__(self, cid: str, name: str, image: Path | None, available: bool, parent: QWidget | None = None):
        super().__init__(parent)
        self.cid = cid
        self.setText(name)
        self.setCheckable(True)
        self.setFixedSize(self.W, self.H)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._hover = False
        self._movie: QMovie | None = None
        self._pix = QPixmap()
        self._size = QSize()  # 그림 표시 크기 (선명하게 2배로 디코딩해서 줄여 그림)
        self.theme = DEFAULT_THEME
        self.available = available  # 그림이 하나도 없으면 고를 수 없음
        self._loops_left = 0  # 남은 재생 바퀴
        self._frames_played = 0
        self._boing = 1.0  # 뽀잉 진행도 (1 이면 멈춤)
        self._anim = QVariantAnimation(self, startValue=0.0, endValue=1.0, duration=BOING_MS)
        self._anim.setEasingCurve(QEasingCurve.Type.Linear)
        self._anim.valueChanged.connect(self._on_boing)

        self.setEnabled(available)
        if image is not None:
            reader = QImageReader(str(image))
            self._size = reader.size().scaled(QSize(self.IMG, self.IMG), Qt.AspectRatioMode.KeepAspectRatio)
            if reader.supportsAnimation() and reader.imageCount() != 1:
                self._movie = QMovie(str(image), parent=self)
                self._movie.setScaledSize(self._size * 2)
                self._movie.frameChanged.connect(self._on_frame)
                self._movie.jumpToFrame(0)
            else:
                self._pix = QPixmap(str(image)).scaled(
                    self._size * 2, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
                )
        self.toggled.connect(self._on_toggled)

    def _on_boing(self, v) -> None:
        self._boing = float(v)
        self.update()

    def boing(self) -> None:
        self._anim.stop()
        self._anim.start()

    def _on_toggled(self, on: bool) -> None:
        if on:
            self.boing()
            self.play_once()
        elif self._movie:
            self._stop_movie()
        self.update()

    def play_once(self) -> None:
        """GIF 를 PICK_LOOPS 바퀴 재생하고 첫 장면에서 멈춘다."""
        if not self._movie:
            return
        self._loops_left = self.PICK_LOOPS
        self._frames_played = 0
        self._movie.stop()
        self._movie.jumpToFrame(0)
        self._movie.start()

    def _on_frame(self, n: int) -> None:
        # 마지막 장면을 지나 0번 장면으로 돌아오면 한 바퀴 끝 (시작하자마자 0번이 오는 경우는 무시)
        if self._movie.state() != QMovie.MovieState.Running:
            self.update()
            return
        self._frames_played += 1
        if n == 0 and self._frames_played > 1:
            self._loops_left -= 1
            if self._loops_left <= 0:
                self._stop_movie()
        self.update()

    def _stop_movie(self) -> None:
        self._loops_left = 0
        self._movie.stop()
        self._movie.jumpToFrame(0)

    def enterEvent(self, e) -> None:
        self._hover = True
        self.update()
        super().enterEvent(e)

    def leaveEvent(self, e) -> None:
        self._hover = False
        self.update()
        super().leaveEvent(e)

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        on = self.isChecked()
        t = self.theme
        if not self.available:
            p.setOpacity(0.55)

        # 카드
        r = QRectF(self.rect()).adjusted(2.5, 2.5, -2.5, -2.5)
        p.setPen(QPen(QColor(t.accent if on else (t.soft if self._hover else t.line)), 2.5))
        p.setBrush(QColor(t.soft if on else t.card))
        p.drawRoundedRect(r, 22, 22)

        # 캐릭터 그림 (뽀잉 중이면 아래 가운데 기준으로 늘이고 줄이고 띄운다)
        box = QRectF((self.width() - self.IMG) / 2, self.IMG_TOP, self.IMG, self.IMG)
        p.save()
        if self._boing < 1.0:
            lift, sx, sy = boing_at(self._boing)
            anchor = QPointF(box.center().x(), box.bottom())
            p.translate(anchor.x(), anchor.y() - lift)
            p.scale(sx, sy)
            p.translate(-anchor.x(), -anchor.y())
        pix = self._movie.currentPixmap() if self._movie else self._pix
        if not pix.isNull():
            pw, ph = self._size.width(), self._size.height()
            p.drawPixmap(QRectF(box.center().x() - pw / 2, box.bottom() - ph, pw, ph), pix, QRectF(pix.rect()))
        else:  # 이미지 없음: 점선 동그라미 + 물음표
            mark = QColor(t.accent if on else t.line)
            pen = QPen(mark, 2.5, Qt.PenStyle.DashLine)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(box.adjusted(10, 10, -10, -10))
            f = QFont(self.font())
            f.setPixelSize(28)
            f.setBold(True)
            p.setFont(f)
            p.setPen(mark)
            p.drawText(box, Qt.AlignmentFlag.AlignCenter, "?")
        p.restore()

        # 이름
        f = QFont(self.font())
        f.setPixelSize(13)
        f.setBold(on)
        p.setFont(f)
        p.setPen(QColor(t.accent_deep if on else t.text))
        name_box = QRectF(r.left(), box.bottom() + 6, r.width(), 22)
        p.drawText(name_box, Qt.AlignmentFlag.AlignCenter, self.text())

        # 고른 표시: 오른쪽 위 분홍 동그라미 + 체크
        if on:
            c = QPointF(r.right() - 16, r.top() + 16)
            p.setPen(QPen(QColor("white"), 2))
            p.setBrush(QColor(t.accent))
            p.drawEllipse(c, 11, 11)
            check = QPainterPath(QPointF(c.x() - 5, c.y()))
            check.lineTo(c.x() - 1.5, c.y() + 3.5)
            check.lineTo(c.x() + 5, c.y() - 3.5)
            p.setPen(QPen(QColor(t.on_accent), 2.4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(check)
        p.end()


class SettingsDialog(QDialog):
    def __init__(self, parent: QWidget | None, settings: Settings, first_run: bool = False):
        super().__init__(parent)
        self.setWindowTitle("처음 만났네!" if first_run else "설정")
        self.settings = settings

        title = QLabel("처음 만났네!" if first_run else "설정")
        title.setObjectName("title")
        self.ribbon = QLabel()
        subtitle = QLabel("같이 지낼 친구랑 이름을 알려줘." if first_run else "언제든 다시 바꿀 수 있어.")
        subtitle.setObjectName("subtitle")

        # 캐릭터 고르기: 누르면 그 캐릭터 색으로 테마가 바뀐다
        self.cards = QButtonGroup(self)
        self.cards.setExclusive(True)
        card_row = QHBoxLayout()
        card_row.setSpacing(10)
        for cid, name in CHARACTERS:
            card = CharacterCard(cid, name, pick_image(cid), character_image(cid) is not None)
            self.cards.addButton(card)
            card_row.addWidget(card)

        # 이름
        self.name = QLineEdit(settings.user_name)
        self.name.setPlaceholderText("캐릭터가 불러줄 이름")

        # 미리 알림: 알약 모양 선택지
        self.leads = QButtonGroup(self)
        self.leads.setExclusive(True)
        lead_row = QHBoxLayout()
        lead_row.setSpacing(6)
        choices = sorted(set(LEAD_CHOICES) | {settings.lead_minutes})
        for m in choices:
            chip = QPushButton(_lead_text(m))
            chip.setObjectName("chip")
            chip.setCheckable(True)
            chip.setCursor(Qt.CursorShape.PointingHandCursor)
            chip.setChecked(m == settings.lead_minutes)
            self.leads.addButton(chip, m)
            lead_row.addWidget(chip)
        lead_row.addStretch(1)

        # 버튼
        cancel = QPushButton("취소")
        cancel.setObjectName("ghost")
        self.ok = QPushButton("저장")
        self.ok.setObjectName("primary")
        self.ok.setDefault(True)
        for b in (cancel, self.ok):
            b.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel.clicked.connect(self.reject)
        self.ok.clicked.connect(self.accept)
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        btn_row.addWidget(cancel)
        btn_row.addWidget(self.ok)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(26, 22, 26, 22)
        lay.setSpacing(6)
        title_row = QHBoxLayout()
        title_row.setSpacing(6)
        title_row.addWidget(title)
        title_row.addWidget(self.ribbon, 0, Qt.AlignmentFlag.AlignVCenter)
        title_row.addStretch(1)
        lay.addLayout(title_row)
        lay.addWidget(subtitle)
        lay.addSpacing(14)
        lay.addWidget(self._section("같이 지낼 친구"))
        lay.addLayout(card_row)
        lay.addSpacing(14)
        lay.addWidget(self._section("뭐라고 불러줄까?"))
        lay.addWidget(self.name)
        lay.addSpacing(14)
        lay.addWidget(self._section("일정은 언제 미리 알려줄까?"))
        lay.addLayout(lead_row)
        lay.addSpacing(20)
        lay.addLayout(btn_row)

        # 처음 선택: 저장된 캐릭터 → 그림이 있는 첫 캐릭터 → 첫 캐릭터
        buttons = self.cards.buttons()
        current = (
            next((b for b in buttons if b.cid == settings.character and b.available), None)
            or next((b for b in buttons if b.available), None)
            or buttons[0]
        )
        self.cards.buttonToggled.connect(self._on_card_toggled)
        # 창을 열 때는 조용히 선택만 (뽀잉·GIF 재생은 직접 골랐을 때만)
        current.blockSignals(True)
        current.setChecked(True)
        current.blockSignals(False)
        self._on_card_toggled(current, True)

    def _on_card_toggled(self, card: CharacterCard, on: bool) -> None:
        if not on:
            return
        self.apply_theme(theme_for(card.cid))

    def apply_theme(self, t: Theme) -> None:
        self.setStyleSheet(build_style(t))
        for card in self.cards.buttons():
            card.theme = t
            card.update()
        self.ribbon.setPixmap(self._icon(t.ribbon, 28))

    def _icon(self, path: Path, size: int) -> QPixmap:
        pix = QPixmap(str(path))
        if pix.isNull():
            return pix
        dpr = self.devicePixelRatioF()
        pix = pix.scaled(round(size * dpr), round(size * dpr), Qt.AspectRatioMode.KeepAspectRatio,
                         Qt.TransformationMode.SmoothTransformation)
        pix.setDevicePixelRatio(dpr)
        return pix

    @staticmethod
    def _section(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("section")
        return label

    def apply(self) -> None:
        s = self.settings
        s.user_name = self.name.text().strip()
        s.lead_minutes = max(0, self.leads.checkedId())
        card = self.cards.checkedButton()
        if card is not None and card.available:
            s.character = card.cid
        s.save()
