"""설정 창: 이름, 알림 시간, 캐릭터 크기/이미지, 자동 실행."""
from __future__ import annotations

import shutil
from pathlib import Path

from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from . import autostart
from .config import DATA_DIR, Settings


class SettingsDialog(QDialog):
    def __init__(self, parent: QWidget | None, settings: Settings, first_run: bool = False):
        super().__init__(parent)
        self.setWindowTitle("처음 만났네! 이름을 알려줘" if first_run else "설정")
        self.setMinimumWidth(380)
        self.settings = settings
        self._image = settings.character_image

        self.name = QLineEdit(settings.user_name)
        self.name.setPlaceholderText("캐릭터가 불러줄 이름 (예: 지유)")

        self.lead = QSpinBox()
        self.lead.setRange(0, 180)
        self.lead.setSuffix(" 분 전")
        self.lead.setSpecialValueText("미리 알림 안 함")
        self.lead.setValue(settings.lead_minutes)

        self.size = QSpinBox()
        self.size.setRange(60, 400)
        self.size.setSingleStep(10)
        self.size.setSuffix(" px")
        self.size.setValue(settings.character_size)

        self.bubble = QSpinBox()
        self.bubble.setRange(3, 60)
        self.bubble.setSuffix(" 초")
        self.bubble.setValue(settings.bubble_seconds)

        self.sound = QCheckBox("알림 효과음")
        self.sound.setChecked(settings.sound)

        self.auto = QCheckBox("Windows 시작 시 자동 실행")
        self.auto.setChecked(autostart.is_enabled())
        self.auto.setEnabled(autostart.IS_WINDOWS)

        self.image_label = QLabel()
        btn_pick = QPushButton("이미지 선택…")
        btn_reset = QPushButton("기본 캐릭터")
        btn_pick.clicked.connect(self._pick_image)
        btn_reset.clicked.connect(self._reset_image)
        img_row = QHBoxLayout()
        img_row.addWidget(self.image_label, 1)
        img_row.addWidget(btn_pick)
        img_row.addWidget(btn_reset)
        self._update_image_label()

        form = QFormLayout()
        form.addRow("이름", self.name)
        form.addRow("미리 알림", self.lead)
        form.addRow("캐릭터 크기", self.size)
        form.addRow("캐릭터 이미지", img_row)
        form.addRow("말풍선 표시", self.bubble)
        form.addRow("", self.sound)
        form.addRow("", self.auto)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("확인")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("취소")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addWidget(buttons)

    def _update_image_label(self) -> None:
        self.image_label.setText(Path(self._image).name if self._image else "기본 (새싹이)")

    def _pick_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "캐릭터 이미지 선택", "", "이미지 (*.png *.webp *.gif)")
        if not path:
            return
        if QPixmap(path).isNull():
            QMessageBox.warning(self, "이미지", "이미지를 열 수 없어요.")
            return
        # 원본을 옮기거나 지워도 유지되도록 data 폴더로 복사
        dest_dir = DATA_DIR / "character"
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / Path(path).name
        if Path(path).resolve() != dest.resolve():
            shutil.copy2(path, dest)
        self._image = str(dest.relative_to(DATA_DIR))
        self._update_image_label()

    def _reset_image(self) -> None:
        self._image = ""
        self._update_image_label()

    def apply(self) -> None:
        s = self.settings
        s.user_name = self.name.text().strip()
        s.lead_minutes = self.lead.value()
        s.character_size = self.size.value()
        s.bubble_seconds = self.bubble.value()
        s.sound = self.sound.isChecked()
        s.character_image = self._image
        s.save()
        if autostart.IS_WINDOWS and self.auto.isChecked() != autostart.is_enabled():
            autostart.set_enabled(self.auto.isChecked())
