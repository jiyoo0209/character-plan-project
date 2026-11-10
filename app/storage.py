"""일정 저장소: data/schedules.json"""
from __future__ import annotations

import json
import shutil
import uuid
from dataclasses import asdict, dataclass, field, fields
from datetime import date, datetime, timedelta
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from .config import SCHEDULES_FILE, atomic_write_json
from .recurrence import RepeatRule, occurrences, occurs_on

FORMAT_VERSION = 1


@dataclass
class Schedule:
    title: str
    date: str  # YYYY-MM-DD (반복 일정은 시작 날짜)
    time: str  # HH:MM
    memo: str = ""
    category: str = ""  # app/categories.py 의 이름 (없으면 빈 칸)
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    notified_before: bool = False  # 미리 알림 완료 여부 (단일 일정)
    notified_on_time: bool = False  # 정각 알림 완료 여부 (단일 일정)
    # ---- 반복 일정 (repeat 가 비어 있으면 단일 일정) ----
    repeat: str = ""  # daily / weekly / monthly / yearly
    until: str = ""  # 종료일 YYYY-MM-DD (포함)
    weekdays: list[int] = field(default_factory=list)  # 매주: 0=월 … 6=일
    monthly_nth: bool = False  # 매월: True 면 'N째 주 X요일'
    skip: list[str] = field(default_factory=list)  # 빠진 날 (이 날만 지우기/바꾸기)
    dday: bool = False  # D-day 로 세기 (단일 일정 / 매년 반복)
    notified: list[str] = field(default_factory=list)  # 반복 일정 알림 기록: 'YYYY-MM-DD|b' (미리), '|a' (정각)
    done: list[str] = field(default_factory=list)  # 체크리스트에서 끝냈다고 체크한 날 'YYYY-MM-DD'

    @property
    def dt(self) -> datetime:
        return datetime.strptime(f"{self.date} {self.time}", "%Y-%m-%d %H:%M")

    @property
    def day(self) -> date:
        return self.dt.date()

    @property
    def is_repeat(self) -> bool:
        return bool(self.repeat)

    @property
    def rule(self) -> RepeatRule | None:
        if not self.repeat:
            return None
        return RepeatRule(self.repeat, date.fromisoformat(self.until), tuple(self.weekdays), self.monthly_nth,
                          set(self.skip))

    def set_rule(self, rule: RepeatRule | None) -> None:
        if rule is None:
            self.repeat, self.until, self.weekdays, self.monthly_nth = "", "", [], False
            self.skip, self.notified = [], []
        else:
            self.repeat, self.until = rule.kind, rule.until.isoformat()
            self.weekdays = sorted(rule.weekdays) if rule.kind == "weekly" else []
            self.monthly_nth = rule.monthly_nth if rule.kind == "monthly" else False

    def occurs_on(self, d: date) -> bool:
        rule = self.rule
        return d == self.day if rule is None else occurs_on(self.day, rule, d)

    def next_on_or_after(self, d: date) -> date | None:
        """d 이후(당일 포함) 첫 번째 날 (D-day 계산용). 지났으면 None."""
        rule = self.rule
        if rule is None:
            return self.day if self.day >= d else None
        return next(occurrences(self.day, rule, d, min(rule.until, d + timedelta(days=366 * 4))), None)


@dataclass
class Occurrence:
    """어떤 날 하루의 일정 (반복 일정은 그날 한 번). 원래 일정 정보는 .s 에."""

    s: Schedule
    day: date

    @property
    def dt(self) -> datetime:
        return datetime.combine(self.day, datetime.strptime(self.s.time, "%H:%M").time())

    def __getattr__(self, name):  # title, time, memo, category, id, is_repeat …
        return getattr(self.s, name)

    @property
    def done(self) -> bool:
        """오늘 할 일 체크리스트에서 체크했는지 (반복 일정은 그날만)."""
        return self.day.isoformat() in self.s.done

    # 알림 기록: 단일 일정은 원래 플래그, 반복 일정은 날짜별 기록
    def notified_flag(self, kind: str) -> bool:
        if not self.s.is_repeat:
            return self.s.notified_before if kind == "b" else self.s.notified_on_time
        return f"{self.day.isoformat()}|{kind}" in self.s.notified

    def mark_notified(self, kind: str) -> None:
        if not self.s.is_repeat:
            if kind == "b":
                self.s.notified_before = True
            else:
                self.s.notified_on_time = self.s.notified_before = True
            return
        keys = [f"{self.day.isoformat()}|{kind}"] + ([f"{self.day.isoformat()}|b"] if kind == "a" else [])
        for k in keys:
            if k not in self.s.notified:
                self.s.notified.append(k)
        # 오래된 기록은 정리 (1주일 전까지만)
        cutoff = (self.day - timedelta(days=7)).isoformat()
        self.s.notified = [k for k in self.s.notified if k[:10] >= cutoff]


class ScheduleStore(QObject):
    changed = Signal()

    def __init__(self, path: Path = SCHEDULES_FILE):
        super().__init__()
        self.path = path
        self._items: list[Schedule] = []
        self.load()

    # ---- 파일 입출력 ----
    def load(self) -> None:
        if not self.path.exists():
            self._items = []
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            known = {f.name for f in fields(Schedule)}
            items = [Schedule(**{k: v for k, v in r.items() if k in known}) for r in raw.get("schedules", [])]
            for s in items:
                s.dt  # 형식 검증
                s.rule  # 반복 규칙 형식 검증
            self._items = items
        except (OSError, ValueError, TypeError, AttributeError):
            # 손상된 파일은 백업해 두고 빈 상태로 시작
            backup = self.path.with_name(f"schedules.broken-{datetime.now():%Y%m%d-%H%M%S}.json")
            shutil.copy2(self.path, backup)
            self._items = []

    def save(self) -> None:
        self._items.sort(key=lambda s: (s.date, s.time))
        atomic_write_json(
            self.path,
            {"version": FORMAT_VERSION, "schedules": [asdict(s) for s in self._items]},
        )
        self.changed.emit()

    # ---- 조회 ----
    def all(self) -> list[Schedule]:
        return list(self._items)

    def get(self, sid: str) -> Schedule | None:
        return next((s for s in self._items if s.id == sid), None)

    def on_date(self, d: date) -> list[Occurrence]:
        """그날의 일정 (반복 일정 포함), 시간 순."""
        return sorted((Occurrence(s, d) for s in self._items if s.occurs_on(d)), key=lambda o: o.time)

    def dates_between(self, frm: date, to: date) -> set[date]:
        """frm~to 사이에 일정이 하나라도 있는 날들 (달력 점 표시용)."""
        out: set[date] = set()
        for s in self._items:
            rule = s.rule
            if rule is None:
                if frm <= s.day <= to:
                    out.add(s.day)
            else:
                out.update(occurrences(s.day, rule, frm, to))
        return out

    def upcoming_ddays(self, today: date, limit: int | None = None) -> list[tuple[Schedule, date]]:
        """다가오는 D-day (오늘 포함, 가까운 순). 지난 D-day 는 빠진다 (일정 자체는 그대로)."""
        out = [(s, n) for s in self._items if s.dday and (n := s.next_on_or_after(today)) is not None]
        out.sort(key=lambda x: (x[1], x[0].time))
        return out[:limit] if limit else out

    def dday_dates_between(self, frm: date, to: date, today: date) -> set[date]:
        """frm~to 사이 D-day 날짜 (오늘 이후만, 달력 별 표시용)."""
        start = max(frm, today)
        out: set[date] = set()
        for s in self._items:
            if not s.dday:
                continue
            rule = s.rule
            if rule is None:
                if start <= s.day <= to:
                    out.add(s.day)
            else:
                out.update(occurrences(s.day, rule, start, to))
        return out

    def dates_with_schedules(self) -> set[str]:
        return {s.date for s in self._items}

    # ---- 편집 ----
    def add(self, title: str, d: date, time_hhmm: str, memo: str = "", category: str = "",
            repeat: RepeatRule | None = None, dday: bool = False) -> Schedule:
        s = Schedule(title=title.strip(), date=d.isoformat(), time=time_hhmm, memo=memo.strip(), category=category,
                     dday=dday)
        s.set_rule(repeat)
        self._items.append(s)
        self.save()
        return s

    def update(self, sid: str, title: str, d: date, time_hhmm: str, memo: str = "", category: str = "",
               repeat: RepeatRule | None = None, dday: bool = False) -> None:
        """일정 하나(반복 일정이면 전체)를 바꾼다. repeat=None 이면 단일 일정이 된다."""
        s = self.get(sid)
        if s is None:
            return
        if s.date != d.isoformat() or s.time != time_hhmm:
            # 시간이 바뀌면 알림을 다시 받을 수 있게 초기화
            s.notified_before = s.notified_on_time = False
            s.notified = []
        if s.date != d.isoformat() and not s.is_repeat and repeat is None:
            s.done = []  # 다른 날로 옮긴 단일 일정은 체크도 풀린다
        s.title, s.date, s.time, s.memo = title.strip(), d.isoformat(), time_hhmm, memo.strip()
        s.category = category
        s.dday = dday
        s.set_rule(repeat)
        self.save()

    def set_done(self, sid: str, d: date, on: bool) -> None:
        """체크리스트 체크 / 해제. 반복 일정은 날짜별로 따로 기록한다."""
        s = self.get(sid)
        if s is None:
            return
        key = d.isoformat()
        if on and key not in s.done:
            s.done.append(key)
        elif not on and key in s.done:
            s.done.remove(key)
        if s.is_repeat:  # 오래된 기록은 정리 (두 달 전까지만)
            cutoff = (d - timedelta(days=60)).isoformat()
            s.done = [k for k in s.done if k >= cutoff]
        self.save()

    def delete(self, sid: str) -> None:
        self._items = [s for s in self._items if s.id != sid]
        self.save()

    # ---- 반복 일정: 이 날만 / 이 날부터 ----
    def skip_day(self, sid: str, d: date, save: bool = True) -> None:
        """반복 일정에서 이 날 하나만 뺀다 (이 날만 지우기)."""
        s = self.get(sid)
        if s is None or not s.is_repeat:
            return
        if d.isoformat() not in s.skip:
            s.skip.append(d.isoformat())
        if not any(True for _ in occurrences(s.day, s.rule, s.day, s.rule.until)):
            self._items.remove(s)  # 남은 날이 없으면 일정 자체를 지운다
        if save:
            self.save()

    def end_before(self, sid: str, d: date, save: bool = True) -> None:
        """반복 일정을 이 날 전날까지로 줄인다 (이 날부터 쭉 지우기). 첫날이면 통째로 지운다."""
        s = self.get(sid)
        if s is None or not s.is_repeat:
            return
        last = d - timedelta(days=1)
        if last < s.day or not any(True for _ in occurrences(s.day, s.rule, s.day, last)):
            self._items.remove(s)
        else:
            s.until = last.isoformat()
            s.skip = [k for k in s.skip if k <= s.until]
        if save:
            self.save()

    def edit_one(self, sid: str, d: date, title: str, time_hhmm: str, memo: str, category: str,
                 dday: bool = False) -> None:
        """이 날만 바꾸기: 반복에서 이 날을 빼고, 그 자리에 단일 일정을 하나 만든다."""
        self.skip_day(sid, d, save=False)
        self._items.append(Schedule(title=title.strip(), date=d.isoformat(), time=time_hhmm, memo=memo.strip(),
                                    category=category, dday=dday))
        self.save()

    def edit_from(self, sid: str, d: date, title: str, time_hhmm: str, memo: str, category: str,
                  repeat: RepeatRule | None, dday: bool = False) -> None:
        """이 날부터 쭉 바꾸기: 원래 반복은 전날까지로 줄이고, 이 날부터 새 반복(또는 단일)을 만든다."""
        s = self.get(sid)
        if s is None:
            return
        if d <= s.day:
            self.update(sid, title, d, time_hhmm, memo, category, repeat, dday)
            return
        self.end_before(sid, d, save=False)
        new = Schedule(title=title.strip(), date=d.isoformat(), time=time_hhmm, memo=memo.strip(), category=category,
                       dday=dday)
        new.set_rule(repeat)
        self._items.append(new)
        self.save()
