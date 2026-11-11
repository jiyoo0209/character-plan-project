"""설정 창: 캐릭터 고르기, 이름, 미리 알림 시간. 고른 캐릭터 색으로 테마가 바뀐다."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QEasingCurve, QPointF, QRectF, QSize, Qt, QTime, QVariantAnimation
from PySide6.QtGui import QColor, QFont, QImageReader, QMovie, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (
    QAbstractButton, QButtonGroup, QDialog, QHBoxLayout, QLabel, QLineEdit, QPushButton, QSlider, QVBoxLayout, QWidget,
)

from .frame import RoundFrame
from .config import CHARACTERS, SIZE_MAX, SIZE_MIN, SIZE_STEP, Settings, character_image, pick_image
from .sound import player as sound_player, sound_file
from .themes import DEFAULT_THEME, Theme, theme_for

LEAD_CHOICES = (0, 5, 10, 30, 60)  # 미리 알림 선택지(분)


def build_style(t: Theme) -> str:
    from .calendar_window import dialog_style  # 시간 칸(TimeField) 스타일 포함

    return dialog_style(t) + f"""
QDialog {{ background: transparent; }}
QLabel {{ color: {t.text}; }}
QLabel#title {{ font-size: 20px; font-weight: bold; color: {t.accent_deep}; }}
QLabel#subtitle {{ font-size: 13px; color: {t.subtext}; }}
QLabel#section {{ font-size: 13px; font-weight: bold; color: {t.text}; }}
QLabel#sizeEnd {{ font-size: 12px; color: {t.subtext}; }}
QSlider {{ min-height: 22px; }}
QSlider::groove:horizontal {{ height: 8px; background: {t.card}; border: 1px solid {t.line}; border-radius: 4px; }}
QSlider::sub-page:horizontal {{ background: {t.accent}; border-radius: 4px; }}
QSlider::handle:horizontal {{ width: 12px; height: 12px; margin: -5px 0; border-radius: 9px;
    background: white; border: 3px solid {t.accent}; }}
QLineEdit {{
    background: {t.card}; color: {t.text}; font-size: 14px;
    border: 2px solid {t.line}; border-radius: 16px; padding: 7px 14px;
    selection-background-color: {t.accent}; selection-color: {t.on_accent};
}}
QLineEdit:focus {{ border-color: {t.accent}; }}
QPushButton#primary, QPushButton#ghost {{ padding: 8px 26px; }}
QPushButton#chip[mini="true"] {{ padding: 3px 12px; font-size: 12px; border-radius: 12px; }}  /* 낮은 버튼은 반지름이 높이의 반을 넘으면 네모로 그려진다 */
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
        self._just_toggled = False
        self.toggled.connect(self._on_toggled)
        self.clicked.connect(self._on_clicked)

    def _on_boing(self, v) -> None:
        self._boing = float(v)
        self.update()

    def boing(self) -> None:
        self._anim.stop()
        self._anim.start()

    def _on_clicked(self) -> None:
        # 이미 고른 카드를 한 번 더 누르면 뽀잉 + GIF 를 다시 보여준다
        if self._just_toggled:
            self._just_toggled = False
        elif self.isChecked():
            self.boing()
            self.play_once()

    def _on_toggled(self, on: bool) -> None:
        self._just_toggled = on
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

        # 캐릭터 크기: 슬라이더 (10px 단위) + 지금 값
        from .calendar_window import Pill

        self.size = QSlider(Qt.Orientation.Horizontal)
        self.size.setRange(SIZE_MIN // SIZE_STEP, SIZE_MAX // SIZE_STEP)
        self.size.setPageStep(2)
        self.size.setValue(round(settings.character_size / SIZE_STEP))
        self.size.setCursor(Qt.CursorShape.PointingHandCursor)
        self.size_pill = Pill(theme_for(settings.character))
        self.size.valueChanged.connect(lambda v: self.size_pill.setText(f"{v * SIZE_STEP}px"))
        self.size_pill.setText(f"{self.size.value() * SIZE_STEP}px")
        size_row = QHBoxLayout()
        size_row.setSpacing(10)
        small, big = QLabel("작게"), QLabel("크게")
        for lb in (small, big):
            lb.setObjectName("sizeEnd")
        size_row.addWidget(small)
        size_row.addWidget(self.size, 1)
        size_row.addWidget(big)
        size_row.addSpacing(4)
        size_row.addWidget(self._pill_slot(self.size_pill))

        # 알림 소리 크기: 슬라이더 (5% 단위, 0 = 조용히) + 지금 값. 손을 떼면 그 크기로 들려 준다
        self.volume = QSlider(Qt.Orientation.Horizontal)
        self.volume.setRange(0, 20)
        self.volume.setPageStep(2)
        self.volume.setValue(round(settings.sound_volume / 5))
        self.volume.setCursor(Qt.CursorShape.PointingHandCursor)
        self.volume_pill = Pill(theme_for(settings.character))
        self.volume.valueChanged.connect(self._on_volume_changed)
        self.volume.sliderReleased.connect(self._preview_sound)
        self._on_volume_changed(self.volume.value())
        volume_row = QHBoxLayout()
        volume_row.setSpacing(10)
        quiet, loud = QLabel("작게"), QLabel("크게")
        for lb in (quiet, loud):
            lb.setObjectName("sizeEnd")
        volume_row.addWidget(quiet)
        volume_row.addWidget(self.volume, 1)
        volume_row.addWidget(loud)
        volume_row.addSpacing(4)
        volume_row.addWidget(self._pill_slot(self.volume_pill))
        self.preview = QPushButton("▶ 들어 보기")
        self.preview.setObjectName("chip")
        self.preview.setProperty("mini", True)
        self.preview.setCursor(Qt.CursorShape.PointingHandCursor)
        self.preview.clicked.connect(self._preview_sound)
        volume_head = QHBoxLayout()
        volume_head.setContentsMargins(0, 0, 0, 0)
        volume_head.addWidget(self._section("알림 소리는 얼마나 크게 할까?"))
        volume_head.addStretch(1)
        volume_head.addWidget(self.preview)

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

        # 하루 브리핑: 컴퓨터 켤 때 / 정해진 시간
        from .calendar_window import TimeField

        self.brief_mode = QButtonGroup(self)
        self.brief_mode.setExclusive(True)
        brief_row = QHBoxLayout()
        brief_row.setSpacing(6)
        for i, (key, text) in enumerate((("startup", "컴퓨터 켤 때"), ("time", "정해진 시간"))):
            chip = QPushButton(text)
            chip.setObjectName("chip")
            chip.setCheckable(True)
            chip.setCursor(Qt.CursorShape.PointingHandCursor)
            chip.setChecked(settings.briefing == key)
            self.brief_mode.addButton(chip, i)
            brief_row.addWidget(chip)
        self.brief_time = TimeField(QTime.fromString(settings.briefing_time, "HH:mm"), theme_for(settings.character))
        self.brief_time.setFixedWidth(130)
        brief_row.addWidget(self.brief_time)
        brief_row.addStretch(1)
        self.brief_mode.idToggled.connect(lambda *_: self.brief_time.setEnabled(self.brief_mode.checkedId() == 1))
        self.brief_time.setEnabled(settings.briefing == "time")

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
        lay.setContentsMargins(18, 12, 18, 16)
        lay.setSpacing(6)
        title_row = QHBoxLayout()
        title_row.setSpacing(6)
        title_row.addWidget(title)
        title_row.addWidget(self.ribbon, 0, Qt.AlignmentFlag.AlignVCenter)
        title_row.addStretch(1)
        lay.addLayout(title_row)
        lay.addWidget(subtitle)
        lay.addSpacing(10)
        lay.addWidget(self._section("같이 지낼 친구"))
        lay.addLayout(card_row)
        lay.addSpacing(10)
        lay.addWidget(self._section("크기는 얼마나 할까?"))
        lay.addLayout(size_row)
        lay.addSpacing(10)
        lay.addLayout(volume_head)
        lay.addLayout(volume_row)
        lay.addSpacing(10)
        lay.addWidget(self._section("뭐라고 불러줄까?"))
        lay.addWidget(self.name)
        lay.addSpacing(10)
        lay.addWidget(self._section("일정은 언제 미리 알려줄까?"))
        lay.addLayout(lead_row)
        lay.addSpacing(10)
        lay.addWidget(self._section("하루 브리핑은 언제 해 줄까?"))
        brief_hint = QLabel("오늘 일정을 먼저 말하고, 등록된 D-day도 알려 줘")
        brief_hint.setObjectName("subtitle")
        lay.addWidget(brief_hint)
        lay.addLayout(brief_row)
        lay.addSpacing(14)
        lay.addLayout(btn_row)
        self.frame = RoundFrame(self, theme_for(settings.character), title_row=title_row)

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
        self._refresh_preview()

    def _refresh_preview(self) -> None:
        """들어 보기: 고른 캐릭터의 효과음 파일이 있고 소리가 0 이 아닐 때만."""
        if not hasattr(self, "preview"):
            return
        card = self.cards.checkedButton()
        has = card is not None and sound_file(card.cid) is not None
        self.preview.setEnabled(has and self.volume.value() > 0)
        self.preview.setToolTip("" if has else "이 친구는 아직 효과음이 없어")

    @staticmethod
    def _pill_slot(pill: QWidget) -> QWidget:
        """알약을 고정 폭 자리에 오른쪽 맞춤으로 (값이 바뀌어도 슬라이더 길이가 그대로)."""
        slot = QWidget()
        slot.setFixedWidth(64)
        row = QHBoxLayout(slot)
        row.setContentsMargins(0, 0, 0, 0)
        row.addStretch(1)
        row.addWidget(pill)
        return slot

    def _on_volume_changed(self, v: int) -> None:
        self.volume_pill.setText(f"{v * 5}%" if v else "조용히")
        self.volume_pill.set_on(v > 0)
        self._refresh_preview()

    def _preview_sound(self) -> None:
        card = self.cards.checkedButton()
        v = self.volume.value() * 5
        if card is not None and v > 0:
            sound_player().play(card.cid, v / 100, fallback=False)

    def apply_theme(self, t: Theme) -> None:
        self.setStyleSheet(build_style(t))
        if hasattr(self, "frame"):
            self.frame.set_theme(t)
        for card in self.cards.buttons():
            card.theme = t
            card.update()
        for pill in (self.size_pill, self.volume_pill):
            pill.theme = t
            pill.update()
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
        s.character_size = self.size.value() * SIZE_STEP
        s.briefing = "time" if self.brief_mode.checkedId() == 1 else "startup"
        s.briefing_time = self.brief_time.time().toString("HH:mm")
        s.sound_volume = self.volume.value() * 5
        card = self.cards.checkedButton()
        if card is not None and card.available:
            s.character = card.cid
        s.save()
