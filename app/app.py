"""앱 조립: 캐릭터, 말풍선, 오늘 할 일, 달력, 알림, 트레이."""
from __future__ import annotations

import sys
import traceback
from datetime import date, datetime

from PySide6.QtCore import QLockFile, QPoint, Qt, QTimer
from PySide6.QtGui import QAction, QColor, QFont, QFontDatabase, QGuiApplication, QIcon, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from . import autostart, desktop
from .calendar_window import CalendarWindow
from .character import CharacterWidget, SpeechBubble
from .config import (
    APP_TITLE,
    ASSETS_DIR,
    BUBBLE_SECONDS,
    CHARACTERS,
    DATA_DIR,
    FONTS_DIR,
    ICON_PATH,
    SETTINGS_FILE,
    Settings,
    character_path,
    is_frozen,
)
from .messages import hello_message, meal_message, update_check_message, wake_message
from .notifier import Notifier
from .routine import (action_image, current_action, current_meal, early_wake_plan, load_routine, meal_break,
                      plans_from)
from .settings_dialog import SettingsDialog
from .sound import player as sound_player
from .themes import menu_style, theme_for
from .today_popup import TodayPopup
from .update_dialog import UpdateDialog
from .updater import Downloader, Release, UpdateChecker, launch_installer
from .version import __version__
from .storage import ScheduleStore

WATCHDOG_MS = 1500
ROUTINE_CHECK_MS = 20_000  # 하루 일과: 20초마다 지금 할 활동 확인
ALERT_SECONDS = 60  # 알림 말풍선은 클릭하거나 이 시간이 지나면 닫힘
BLINK_MS = 500  # 트레이 아이콘 깜빡이는 간격
BLINK_MAX_MS = 5 * 60 * 1000  # 안 눌러도 5분 뒤엔 깜빡임을 멈춘다
TOAST_MS = 10_000  # 윈도우 알림 표시 시간 (윈도우 설정에 따라 다를 수 있음)


def _blank_pixmap() -> QPixmap:
    pm = QPixmap(32, 32)
    pm.fill(QColor(0, 0, 0, 0))
    return pm


def menu_icon(name: str) -> QIcon:
    return QIcon(str(ASSETS_DIR / "icons" / "menu" / f"{name}.png"))


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

        self._routine = load_routine(self.settings.character)  # 캐릭터의 기상 · 잠 · 밥 (나머지는 내 일정대로)
        self._shown_image = self._routine_image()
        self._state_said: set[str] = set()  # 이미 말한 기상 · 밥 멘트 ('날짜|wake', '날짜|meal|분')
        self._state_shown: tuple[str, str] | None = None  # 지금 떠 있는 기상 · 밥 멘트 (키, 글)
        self._mark_state_said()
        self.character = CharacterWidget(self._shown_image, self.settings.character_size)
        self.bubble = SpeechBubble(theme_for(self.settings.character))
        self.calendar = CalendarWindow(self.store, theme_for(self.settings.character))
        self.today = TodayPopup(self.store, theme_for(self.settings.character))
        self.today.manage_requested.connect(self.calendar.open)
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
        self.bubble.dismissed.connect(self._say_next)
        self._queue: list[str] = []  # 차례로 말할 말풍선 (하루 브리핑: 오늘 일정 → D-day)
        self.brief_timer = QTimer()
        self.brief_timer.timeout.connect(self._check_briefing)
        self.brief_timer.start(30_000)

        # 자동 업데이트: 켜질 때 + 6시간마다 깃허브 최신 버전 확인 (설치된 exe 에서만)
        self.updater = UpdateChecker(__version__)
        self.updater.found.connect(self._on_update_found)
        self.update_timer = QTimer()
        self.updater.up_to_date.connect(lambda: self.say(update_check_message("latest", self.settings.character, __version__)))
        self.updater.failed.connect(lambda: self.say(update_check_message("check_fail", self.settings.character)))
        self.update_timer.timeout.connect(self.updater.start)
        self._update_dlg: UpdateDialog | None = None
        self._downloader: Downloader | None = None
        self._declined: set[str] = set()  # 이번에 '나중에' 누른 버전 (다시 켜면 또 물어봄)

        self._place_character()
        self.character.show()
        self._hwnd = int(self.character.winId())
        desktop.pin_to_desktop(self._hwnd)
        desktop.send_to_bottom(self._hwnd)
        self._bubble_hwnd = int(self.bubble.winId())
        desktop.pin_to_desktop(self._bubble_hwnd)

        # 일정 알림 때 작업 표시줄(트레이) 아이콘 깜빡이기: 아이콘 ↔ 빈 아이콘
        self._tray_icon = self.tray.icon()
        self._blank_icon = QIcon(_blank_pixmap())
        self._blink_on = False
        self.blink_timer = QTimer()
        self.blink_timer.setInterval(BLINK_MS)
        self.blink_timer.timeout.connect(self._blink)
        self.blink_stop = QTimer()
        self.blink_stop.setSingleShot(True)
        self.blink_stop.timeout.connect(self.stop_blink)
        self.tray.messageClicked.connect(self._on_toast_clicked)

        self.watchdog = QTimer()
        self.watchdog.timeout.connect(self._watch)
        self.watchdog.start(WATCHDOG_MS)

        self.routine_timer = QTimer()  # 지금 할 행동이 바뀌었는지 (소리 없이 그림만 서서히 바뀜)
        self.routine_timer.timeout.connect(self._tick_routine)
        self.routine_timer.start(ROUTINE_CHECK_MS)
        self.store.changed.connect(self._tick_routine)  # 일정 추가 · 체크하면 바로 반영

        autostart.ensure_enabled()  # 자동 실행은 항상 켜 둔다
        self.notifier.start()

        if first_run:
            QTimer.singleShot(400, self._first_run)
        else:
            QTimer.singleShot(1200, self._startup_briefing)
            if is_frozen():
                QTimer.singleShot(5000, self.updater.start)
        if is_frozen():
            self.update_timer.start(6 * 60 * 60 * 1000)

    # ---- 메뉴 ----
    def _build_menu(self) -> QMenu:
        """우클릭 / 트레이 메뉴 (테마 색, 둥근 모서리, 이모지 아이콘)."""
        m = QMenu()
        m.setWindowFlags(m.windowFlags() | Qt.WindowType.FramelessWindowHint | Qt.WindowType.NoDropShadowWindowHint)
        m.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)  # 둥근 모서리 바깥을 투명하게
        m.addAction(menu_icon("calendar"), "일정 보기", self.calendar.open)
        m.addAction(menu_icon("settings"), "설정", self.open_settings)
        m.addSeparator()
        self.act_hide = QAction(m, checkable=True)
        self.act_hide.toggled.connect(self._set_hidden)
        self.act_hide.toggled.connect(self._sync_hide_action)
        self._sync_hide_action(False)
        m.addAction(self.act_hide)
        m.addSeparator()
        m.addAction(menu_icon("update"), "업데이트 확인", self.check_update)
        m.addAction(menu_icon("quit"), "종료", self.qapp.quit)
        ver = m.addAction(f"버전 {__version__}")  # 맨 아래 작은 회색 글씨
        ver.setEnabled(False)
        m.setStyleSheet(menu_style(theme_for(self.settings.character)))
        return m

    def _sync_hide_action(self, hidden: bool) -> None:
        # 체크 표시 대신 글자와 아이콘이 바뀐다
        self.act_hide.setText("캐릭터 보이기" if hidden else "캐릭터 숨기기")
        self.act_hide.setIcon(menu_icon("show" if hidden else "hide"))

    def apply_theme(self) -> None:
        t = theme_for(self.settings.character)
        self.calendar.set_theme(t)
        self.bubble.set_theme(t)
        self.today.set_theme(t)
        self.menu.setStyleSheet(menu_style(t))

    def _on_tray(self, reason) -> None:
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            self.stop_blink()
            self.calendar.open()

    # ---- 트레이 깜빡임 / 윈도우 알림 ----
    def _blink(self) -> None:
        self._blink_on = not self._blink_on
        self.tray.setIcon(self._blank_icon if self._blink_on else self._tray_icon)

    def start_blink(self) -> None:
        self._blink_on = False
        self.blink_timer.start()
        self.blink_stop.start(BLINK_MAX_MS)  # 안 눌러도 몇 분 뒤엔 멈춘다

    def stop_blink(self) -> None:
        if self.blink_timer.isActive() or self._blink_on:
            self.blink_timer.stop()
            self.blink_stop.stop()
            self._blink_on = False
            self.tray.setIcon(self._tray_icon)

    def _on_toast_clicked(self) -> None:
        self.stop_blink()
        self.calendar.open()

    def _set_hidden(self, hidden: bool) -> None:
        self.hidden_by_user = hidden
        self.character.setVisible(not hidden)
        if hidden:
            self.bubble.dismiss()
            self.today.close()
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

    def _keep_on_screen(self) -> None:
        """크기를 바꾼 뒤: 발 위치는 그대로 두되 화면 밖으로 나가면 안쪽으로 당기고, 위치를 저장."""
        c = self.character
        screen = QGuiApplication.screenAt(c.geometry().center()) or QGuiApplication.primaryScreen()
        area = screen.availableGeometry()
        x = min(max(c.x(), area.left()), area.right() - c.width() + 1)
        y = min(max(c.y(), area.top()), area.bottom() - c.height() + 1)
        c.move(x, y)
        if self.settings.pos_x is not None:
            self.settings.pos_x, self.settings.pos_y = x, y
            self.settings.save()

    def _on_moved(self, pos: QPoint) -> None:
        self.bubble.dismiss()
        self.today.close()
        self.settings.pos_x, self.settings.pos_y = pos.x(), pos.y()
        self.settings.save()
        desktop.send_to_bottom(self._hwnd)  # 끌면서 앞으로 나온 창을 다시 아래로

    # ---- 바탕화면 고정 감시 ----
    def _watch(self) -> None:
        if self.hidden_by_user:
            return
        desktop.pin_to_desktop(self._hwnd)  # 탐색기 재시작 대비
        desktop.pin_to_desktop(self._bubble_hwnd)
        desktop.ensure_visible(self._hwnd)

    # ---- 말하기 / 알림 ----
    def say(self, text: str, seconds: float | None = None) -> None:
        if self.hidden_by_user:
            return
        secs = BUBBLE_SECONDS if seconds is None else seconds  # 0 이하 = 계속 떠 있음
        self.bubble.say(text, self.character.art_rect(), secs, alert=self.character.mode == "alert")
        self._stack_bubble()
        QTimer.singleShot(0, self._stack_bubble)  # Qt 가 띄우면서 앞으로 올린 경우 한 번 더

    def _stack_bubble(self) -> None:
        """말풍선을 캐릭터 바로 아래 층에 둔다 → 다른 프로그램 창 위로 올라오지 않는다."""
        desktop.pin_to_desktop(self._bubble_hwnd)
        desktop.stack_under(self._bubble_hwnd, self._hwnd)

    def alert(self, text: str) -> None:
        if self.hidden_by_user:
            self.act_hide.setChecked(False)  # 숨겨 둔 상태여도 일정 알림은 보여 준다
        self.today.close()  # 알림 말풍선이 체크리스트에 가리지 않게
        self.character.start_alert()
        # 캐릭터·말풍선은 바탕화면 층에 그대로 두고, 창에 가려져도 알 수 있게
        # 윈도우 알림을 띄우고 작업 표시줄(트레이) 아이콘을 깜빡인다.
        name = dict(CHARACTERS).get(self.settings.character, APP_TITLE)
        self.tray.showMessage(f"{name} · 일정 알림", text, self._tray_icon, TOAST_MS)
        self.start_blink()
        if self.settings.sound_volume > 0:  # 캐릭터 효과음 (파일이 없으면 기본 알림음). 0 이면 조용히
            sound_player().play(self.settings.character, self.settings.sound_volume / 100)
        self.say(text, ALERT_SECONDS)

    def _end_alert(self) -> None:
        if self.character.mode == "alert":
            self.character.stop_alert()

    def say_sequence(self, texts: list[str]) -> None:
        """말풍선 여러 개를 차례로 (하나가 닫히면 다음)."""
        texts = [t for t in texts if t]
        if not texts:
            return
        self._queue = texts[1:]
        first = texts[0]
        self.say(first, max(BUBBLE_SECONDS, 3 + 1.6 * first.count("\n")))

    def _say_next(self) -> None:
        if self._queue and self.character.mode != "alert":
            nxt = self._queue.pop(0)
            QTimer.singleShot(450, lambda: self.say(nxt, max(BUBBLE_SECONDS, 3 + 1.6 * nxt.count("\n"))))

    # ---- 하루 브리핑 ----
    def brief(self) -> None:
        """오늘 일정부터 말하고, 이어서 등록된 D-day 를 알려 준다."""
        self.settings.last_briefing = date.today().isoformat()
        self.settings.save()
        if not self.hidden_by_user and self.settings.sound_volume > 0:  # 브리핑도 캐릭터 효과음으로 알려 준다
            sound_player().play(self.settings.character, self.settings.sound_volume / 100)
        self.say_sequence(self.notifier.briefing())

    def _startup_briefing(self) -> None:
        if self.settings.briefing == "startup":
            self.brief()  # 컴퓨터 켤 때 (자동 실행으로 앱이 켜질 때)
        else:
            self._check_briefing()  # 정해진 시간이 이미 지났는데 오늘 아직 안 했으면 지금

    def _check_briefing(self) -> None:
        s = self.settings
        if s.briefing != "time" or s.last_briefing == date.today().isoformat():
            return
        if datetime.now().strftime("%H:%M") >= s.briefing_time:
            self.brief()

    def _on_character_clicked(self) -> None:
        """캐릭터 클릭: 오늘 할 일 체크리스트. 열려 있을 때 다시 누르면 닫힌다."""
        self._queue.clear()
        self.stop_blink()
        self.bubble.dismiss()  # 알림 중이면 알림도 같이 끝남
        if self.today.isVisible():
            self.today.close()
        elif not self.today.just_closed():  # 이 클릭으로 방금 닫힌 거면 다시 열지 않는다
            self.today.open_at(self.character.art_rect())

    def _first_run(self) -> None:
        self.open_settings(first_run=True)
        self.say(hello_message(self.settings.user_name, self.settings.character))

    # ---- 업데이트 ----
    def check_update(self) -> None:
        """메뉴 '업데이트 확인': 말풍선으로 확인 중 → 새 버전이면 업데이트 창, 아니면 최신이라고 알려 줌."""
        if self._update_dlg is not None:
            self._update_dlg.raise_()
            self._update_dlg.activateWindow()
            return
        self._queue.clear()
        self.say(update_check_message("checking", self.settings.character), 4)
        self.updater.start(manual=True)

    def _on_update_found(self, rel: Release, manual: bool = False) -> None:
        if self._update_dlg is not None or (rel.version in self._declined and not manual):
            return
        if manual:
            self.bubble.dismiss()
        dlg = UpdateDialog(None, theme_for(self.settings.character), __version__, rel.version, rel.notes)
        dlg.setWindowIcon(self.qapp.windowIcon())
        dlg.update_clicked.connect(lambda: self._start_update(dlg, rel))
        dlg.rejected.connect(lambda: self._close_update(rel))
        self._update_dlg = dlg
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()

    def _close_update(self, rel: Release) -> None:
        if self._downloader is not None:
            self._downloader.cancel()  # 받는 중에 '그만 받기' / ×
            self._downloader = None
        else:
            self._declined.add(rel.version)  # '나중에'
        self._update_dlg = None

    def _start_update(self, dlg: UpdateDialog, rel: Release) -> None:
        dlg.set_stage("download")
        dlg.set_progress(0, rel.size)
        dl = Downloader(rel)
        dl.progress.connect(dlg.set_progress)
        dl.done.connect(lambda path: self._install_update(dlg, path))
        dl.failed.connect(lambda _why: self._update_failed(dlg))
        self._downloader = dl
        dl.start()

    def _update_failed(self, dlg: UpdateDialog) -> None:
        self._downloader = None
        dlg.set_stage("error")

    def _install_update(self, dlg: UpdateDialog, path: str) -> None:
        self._downloader = None
        dlg.set_stage("install")
        try:
            launch_installer(path)
        except OSError:
            dlg.set_stage("error")
            return
        QTimer.singleShot(900, self.qapp.quit)  # 설치 파일이 파일을 바꿀 수 있게 앱은 꺼진다

    # ---- 캐릭터의 하루 (내 일정에 맞춰 움직임) ----
    def _routine_image(self):
        """지금 할 행동의 그림. 시각표가 없거나 그 그림을 아직 안 넣었으면 기본 그림."""
        cid = self.settings.character
        now = datetime.now()
        act = current_action(self._routine, plans_from(self.store.on_date(now.date())), now)
        return action_image(cid, act) or character_path(cid)

    def _tick_routine(self) -> None:
        img = self._routine_image()
        if img != self._shown_image:
            self._shown_image = img
            self.character.change_image(img, self.settings.character_size)
        self._update_state_bubble()

    # ---- 기상 · 밥 멘트: 그 그림인 동안 말풍선이 계속 떠 있다 ----
    def _state_now(self) -> tuple[str, object] | None:
        """지금 떠 있어야 할 멘트 (키, 만들 재료). 키는 하루에 한 번씩만 말하려고 쓴다."""
        now = datetime.now()
        plans = plans_from(self.store.on_date(now.date()))
        act = current_action(self._routine, plans, now)
        if act is None:
            return None
        if act.images[0] == "wakeup":
            return f"{now.date()}|wake", ("wake", early_wake_plan(self._routine, plans))
        meal = current_meal(self._routine, plans, now)
        if meal is not None:
            key = f"{now.date()}|meal|{meal.minute}"
            mb = meal_break(self._routine, plans, now)  # 일정 하던 중에 막 밥 시간이 됐을 때만 새로 말한다
            if mb:
                return key, ("meal", mb)
            if self._state_shown and self._state_shown[0] == key:  # 이미 띄운 밥 멘트는 다 먹을 때까지 유지
                return key, None
        return None

    def _mark_state_said(self) -> None:
        """켜자마자 밥 시간 중이면 그 끼니는 말하지 않는다 (기상은 켤 때도 말한다)."""
        st = self._state_now()
        if st and "|meal|" in st[0]:
            self._state_said.add(st[0])

    def _state_text(self, what) -> str:
        kind, data = what
        name, cid = self.settings.user_name, self.settings.character
        if kind == "wake":
            early = (data.title, data.minute // 60, data.minute % 60) if data else None
            return wake_message(name, cid, early)
        meal, plan = data
        return meal_message(name, meal.say, plan.title, cid)

    def _state_visible(self) -> bool:
        return bool(self._state_shown) and self.bubble.isVisible() and self.bubble.label.text() == self._state_shown[1]

    def _update_state_bubble(self) -> None:
        st = self._state_now()
        key = st[0] if st else None
        if self._state_shown and self._state_shown[0] != key:  # 기상 · 밥이 끝남 → 그 멘트를 닫는다
            if self._state_visible():
                self.bubble.dismiss()
            self._state_shown = None
        if self._state_shown and not self._state_visible():  # 눌러서 닫았거나 알림이 덮음 → 다시 띄우지 않음
            self._state_shown = None
        if st is None or st[1] is None or key in self._state_said or self.hidden_by_user:
            return
        if self.character.mode == "alert":  # 일정 알림이 먼저, 이 멘트는 건너뜀
            self._state_said.add(key)
            return
        if self.bubble.isVisible() or self._queue:  # 인사 · 브리핑 중이면 끝나고 나서
            return
        self._state_said.add(key)
        text = self._state_text(st[1])

        def show():
            st_now = self._state_now()
            if not st_now or st_now[0] != key:
                return  # 그새 끝남
            if self.bubble.isVisible() or self._queue or self.character.mode == "alert":
                self._state_said.discard(key)  # 그새 다른 말풍선이 떴음 → 다음 확인 때 다시
                return
            self.say(text, 0)  # 0 = 계속 떠 있음
            self._state_shown = (key, text)

        QTimer.singleShot(1200, show)  # 그림이 바뀐 뒤에 (머리 위치가 새 그림 기준이 되게)

    # ---- 설정 ----
    def open_settings(self, first_run: bool = False) -> None:
        dlg = SettingsDialog(None, self.settings, first_run=first_run)
        dlg.setWindowIcon(self.qapp.windowIcon())
        if dlg.exec() or first_run:
            if dlg.result():
                dlg.apply()
            else:
                self.settings.save()  # 첫 실행에서 취소해도 다음엔 묻지 않도록
            self._routine = load_routine(self.settings.character)
            self._shown_image = self._routine_image()
            self._mark_state_said()
            self.character.set_image(self._shown_image, self.settings.character_size)
            self._keep_on_screen()
            self.apply_theme()


def run() -> int:
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    qapp = QApplication(sys.argv)
    qapp.setApplicationName(APP_TITLE)
    qapp.setQuitOnLastWindowClosed(False)  # 달력 창을 닫아도 계속 실행
    base = QFont("Malgun Gothic", 9) if sys.platform == "win32" else qapp.font()
    # 100% 배율에서 글자를 화면 칸에 억지로 맞추면 주아체가 각지고 뭉개져 보인다 → 맞춤 끄고 부드럽게
    base.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    base.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    qapp.setFont(base)
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
