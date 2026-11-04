"""주기적으로 일정을 확인해서 알림 신호를 보낸다."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Callable

from PySide6.QtCore import QObject, QTimer, Signal

from . import messages
from .config import Settings
from .storage import ScheduleStore

CHECK_INTERVAL_MS = 15_000
ON_TIME_WINDOW = timedelta(minutes=5)  # 정각 알림은 이 시간 안에만 (PC 가 꺼져 있던 지난 일정은 무시)


class Notifier(QObject):
    alert = Signal(str)  # 캐릭터가 말할 문장

    def __init__(self, store: ScheduleStore, settings: Callable[[], Settings]):
        super().__init__()
        self.store = store
        self.settings = settings
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.check)

    def start(self) -> None:
        self.timer.start(CHECK_INTERVAL_MS)
        QTimer.singleShot(1500, self.check)

    def check(self, now: datetime | None = None) -> list[str]:
        now = now or datetime.now()
        st = self.settings()
        lead = timedelta(minutes=st.lead_minutes)
        out: list[str] = []
        dirty = False

        for s in self.store.all():
            when = s.dt
            if not s.notified_on_time and when <= now < when + ON_TIME_WINDOW:
                out.append(messages.on_time_message(st.user_name, s.title))
                s.notified_on_time = s.notified_before = True
                dirty = True
            elif lead and not s.notified_before and when - lead <= now < when:
                out.append(messages.before_message(st.user_name, s.title, when, now))
                s.notified_before = True
                dirty = True

        if dirty:
            self.store.save()
        if out:
            self.alert.emit("\n\n".join(out))
        return out

    def today_greeting(self, now: datetime | None = None) -> str | None:
        """실행 직후 오늘 남은 일정 요약."""
        now = now or datetime.now()
        rest = [(s.title, s.time) for s in self.store.on_date(now.date()) if s.dt > now]
        if not rest:
            return None
        return messages.today_summary(self.settings().user_name, rest)
