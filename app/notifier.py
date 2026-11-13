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

        # 어제~내일 (자정을 넘는 미리 알림 / 정각 알림 대비). 반복 일정은 그날 한 번씩.
        today = now.date()
        occs = [o for d in (today - timedelta(days=1), today, today + timedelta(days=1)) for o in self.store.on_date(d)]
        for o in occs:
            if o.is_range:  # 기간 일정(여행)은 시간이 없어서 알림 대신 브리핑에서만 말한다
                continue
            when = o.dt
            if not o.notified_flag("a") and when <= now < when + ON_TIME_WINDOW:
                out.append(messages.on_time_message(st.user_name, o.title, st.character))
                o.mark_notified("a")
                dirty = True
            elif lead and not o.notified_flag("b") and when - lead <= now < when:
                out.append(messages.before_message(st.user_name, o.title, when, now, st.character))
                o.mark_notified("b")
                dirty = True

        if dirty:
            self.store.save()
        if out:
            self.alert.emit("\n\n".join(out))
        return out

    def briefing(self, now: datetime | None = None) -> list[str]:
        """하루 브리핑: [오늘 남은 일정, (등록된 D-day)] 순서로 말할 문장들."""
        now = now or datetime.now()
        st = self.settings()
        name, cid = st.user_name, st.character
        occs = self.store.on_date(now.date())
        # 기간 일정(여행)은 시간 없이 맨 앞에: '제주 여행 (3일 중 2일째)'
        rest = [(f"{o.title} ({o.span}일 중 {o.nth}일째)" if o.span > 1 else o.title, "") for o in occs if o.is_range]
        rest += [(o.title, o.time) for o in occs if not o.is_range and o.dt > now]
        out = [messages.briefing_today(name, rest, cid)]
        ddays = [(s.title, (d - now.date()).days) for s, d in self.store.upcoming_ddays(now.date())]
        dmsg = messages.briefing_dday(ddays, cid)
        if dmsg:
            out.append(dmsg)
        return out

    def today_greeting(self, now: datetime | None = None) -> str | None:
        """실행 직후 오늘 남은 일정 요약."""
        now = now or datetime.now()
        rest = [(s.title, s.time) for s in self.store.on_date(now.date()) if not s.is_range and s.dt > now]
        if not rest:
            return None
        return messages.today_summary(self.settings().user_name, rest)
