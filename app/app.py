"""앱 조립: 캐릭터, 말풍선, 달력, 알림, 트레이."""
from __future__ import annotations

import sys
import traceback
from datetime import datetime

from PySide6.QtCore import QLockFile, QPoint, Qt, QTimer
from PySide6.QtGui import QAction, QFont, QFontDatabase, QGuiApplication, QIcon
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from . import autostart, desktop
from .calendar_window import CalendarWindow
from .character import CharacterWidget, SpeechBubble
from .config import (
    APP_TITLE,
    BUBBLE_SECONDS,
    CHARACTER_SIZE,
    DATA_DIR,
    FONTS_DIR,
    ICON_PATH,
    SETTINGS_FILE,
    Settings,
    character_path,
)
from .messages import call_name
from .notifier import Notifier
from .settings_dialog import SettingsDialog
from .storage import ScheduleStore

WATCHDOG_MS = 1500
ALERT_SECONDS = 60  # 알림 말풍선은 클릭하거나 이 시간이 지나면 닫힘


def _load_fonts() -> None:
    """assets/fonts 의 폰트를 등록한다 (PC 에 설치돼 있지 않아도 쓸 수 있게)."""
    for f in sorted(FONTS_DIR.glob("*.[ot]tf")):
        QFontDatabase.addApplicationFont(str(f))


def _install_error_log() -> None:
    """창 모드 exe 는 콘솔이 없으므로 오류를 data/error.log 에 남긴다."""
    log = DATA_DIR / "error.log"

    def hook(exc_type, exc, tb):
        with open(log, "a", encoding="utf-8") as f:
            f.write(f"\n[{datetime.now():%Y-%m-%d %H:%M:%S}]\n")
            traceback.print_exception(exc_type, exc, tb, file=f)
        sys.__excepthook__(exc_type, exc, tb)

    sys.excepthook = hook


class CharacterPlanApp:
    def __init__(self, qapp: QApplication):
        self.qapp = qapp
        first_run = not SETTINGS_FILE.exists()
        self.settings = Settings.load()
        self.store = ScheduleStore()
        self.notifier = Notifier(self.store, lambda: self.settings)
        self.hidden_by_user = False

        self.character = CharacterWidget(character_path(self.settings.character), CHARACTER_SIZE)
        self.bubble = SpeechBubble()
        self.calendar = CalendarWindow(self.store)
        icon = QIcon(str(ICON_PATH))
        self.qapp.setWindowIcon(icon)
        self.calendar.setWindowIcon(icon)

        self.menu = self._build_menu()
        self.tray = QSystemTrayIcon(icon)
        self.tray.setToolTip(APP_TITLE)
        self.tray.setContextMenu(self.menu)
        self.tray.activated.connect(self._on_tray)
        self.tray.show()

        self.character.clicked.connect(self._on_character_clicked)
        self.character.moved.connect(self._on_moved)
        self.character.menu_requested.connect(lambda pos: self.menu.exec(pos))
        self.notifier.alert.connect(self.alert)
        self.bubble.dismissed.connect(self._end_alert)

        self._place_character()
        self.character.show()
        self._hwnd = int(self.character.winId())
        desktop.pin_to_desktop(self._hwnd)
        desktop.send_to_bottom(self._hwnd)

        self.watchdog = QTimer()
        self.watchdog.timeout.connect(self._watch)
        self.watchdog.start(WATCHDOG_MS)

        autostart.ensure_enabled()  # 자동 실행은 항상 켜 둔다
        self.notifier.start()

        if first_run:
            QTimer.singleShot(400, self._first_run)
        else:
            QTimer.singleShot(1200, self._greet)

    # ---- 메뉴 ----
    def _build_menu(self) -> QMenu:
        m = QMenu()
        m.addAction("일정 보기", self.calendar.open)
        m.addAction("설정…", self.open_settings)
        m.addSeparator()
        self.act_hide = QAction("캐릭터 숨기기", m, checkable=True)
        self.act_hide.toggled.connect(self._set_hidden)
        m.addAction(self.act_hide)
        m.addSeparator()
        m.addAction("종료", self.qapp.quit)
        return m

    def _on_tray(self, reason) -> None:
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            self.calendar.open()

    def _set_hidden(self, hidden: bool) -> None:
        self.hidden_by_user = hidden
        self.character.setVisible(not hidden)
        if hidden:
            self.bubble.dismiss()
        else:
            desktop.pin_to_desktop(self._hwnd)

    # ---- 위치 ----
    def _place_character(self) -> None:
        s = self.settings
        c = self.character
        if s.pos_x is not None and s.pos_y is not None:
            center = QPoint(s.pos_x + c.width() // 2, s.pos_y + c.height() // 2)
            if QGuiApplication.screenAt(center):  # 모니터 구성이 바뀌어 화면 밖이면 기본 위치로
                c.move(s.pos_x, s.pos_y)
                return
        area = QGuiApplication.primaryScreen().availableGeometry()
        c.move(area.right() - c.width() - 40, area.bottom() - c.height() - 20)

    def _on_moved(self, pos: QPoint) -> None:
        self.bubble.dismiss()
        self.settings.pos_x, self.settings.pos_y = pos.x(), pos.y()
        self.settings.save()
        desktop.send_to_bottom(self._hwnd)  # 끌면서 앞으로 나온 창을 다시 아래로

    # ---- 바탕화면 고정 감시 ----
    def _watch(self) -> None:
        if self.hidden_by_user or self.character.mode == "alert":  # 알림 중엔 맨 위에 있어야 함
            return
        desktop.pin_to_desktop(self._hwnd)  # 탐색기 재시작 대비
        desktop.ensure_visible(self._hwnd)

    # ---- 말하기 / 알림 ----
    def say(self, text: str, seconds: float | None = None) -> None:
        if self.hidden_by_user:
            return
        self.bubble.say(text, self.character.body_rect(), seconds or BUBBLE_SECONDS)

    def alert(self, text: str) -> None:
        if self.hidden_by_user:
            self.act_hide.setChecked(False)  # 숨겨 둔 상태여도 일정 알림은 보여 준다
        self.character.start_alert()
        desktop.set_topmost(self._hwnd, True)
        desktop.beep()
        self.say(text, ALERT_SECONDS)

    def _end_alert(self) -> None:
        if self.character.mode == "alert":
            self.character.stop_alert()
            desktop.set_topmost(self._hwnd, False)

    def _on_character_clicked(self) -> None:
        self.bubble.dismiss()  # 알림 중이면 알림도 같이 끝남
        self.calendar.open()

    def _greet(self) -> None:
        msg = self.notifier.today_greeting()
        if msg:
            self.say(msg)

    def _first_run(self) -> None:
        self.open_settings(first_run=True)
        self.say(f"반가워, {call_name(self.settings.user_name)}!\n나를 누르면 일정을 볼 수 있어.")

    # ---- 설정 ----
    def open_settings(self, first_run: bool = False) -> None:
        dlg = SettingsDialog(None, self.settings, first_run=first_run)
        dlg.setWindowIcon(self.qapp.windowIcon())
        if dlg.exec() or first_run:
            if dlg.result():
                dlg.apply()
            else:
                self.settings.save()  # 첫 실행에서 취소해도 다음엔 묻지 않도록
            self.character.set_image(character_path(self.settings.character), CHARACTER_SIZE)


def run() -> int:
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    qapp = QApplication(sys.argv)
    qapp.setApplicationName(APP_TITLE)
    qapp.setQuitOnLastWindowClosed(False)  # 달력 창을 닫아도 계속 실행
    if sys.platform == "win32":
        qapp.setFont(QFont("Malgun Gothic", 9))
    _load_fonts()
    _install_error_log()

    # 중복 실행 방지
    lock = QLockFile(str(DATA_DIR / "app.lock"))
    lock.setStaleLockTime(0)
    if not lock.tryLock(200):
        return 0

    app = CharacterPlanApp(qapp)  # noqa: F841 (참조 유지)
    code = qapp.exec()
    lock.unlock()
    return code
