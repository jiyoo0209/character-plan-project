"""일정 저장소: data/schedules.json"""
from __future__ import annotations

import json
import shutil
import uuid
from dataclasses import asdict, dataclass, field, fields
from datetime import date, datetime
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from .config import SCHEDULES_FILE, atomic_write_json

FORMAT_VERSION = 1


@dataclass
class Schedule:
    title: str
    date: str  # YYYY-MM-DD
    time: str  # HH:MM
    memo: str = ""
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    notified_before: bool = False  # 미리 알림 완료 여부
    notified_on_time: bool = False  # 정각 알림 완료 여부

    @property
    def dt(self) -> datetime:
        return datetime.strptime(f"{self.date} {self.time}", "%Y-%m-%d %H:%M")

    @property
    def day(self) -> date:
        return self.dt.date()


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

    def on_date(self, d: date) -> list[Schedule]:
        key = d.isoformat()
        return sorted((s for s in self._items if s.date == key), key=lambda s: s.time)

    def dates_with_schedules(self) -> set[str]:
        return {s.date for s in self._items}

    # ---- 편집 ----
    def add(self, title: str, d: date, time_hhmm: str, memo: str = "") -> Schedule:
        s = Schedule(title=title.strip(), date=d.isoformat(), time=time_hhmm, memo=memo.strip())
        self._items.append(s)
        self.save()
        return s

    def update(self, sid: str, title: str, d: date, time_hhmm: str, memo: str = "") -> None:
        s = self.get(sid)
        if s is None:
            return
        if s.date != d.isoformat() or s.time != time_hhmm:
            # 시간이 바뀌면 알림을 다시 받을 수 있게 초기화
            s.notified_before = s.notified_on_time = False
        s.title, s.date, s.time, s.memo = title.strip(), d.isoformat(), time_hhmm, memo.strip()
        self.save()

    def delete(self, sid: str) -> None:
        self._items = [s for s in self._items if s.id != sid]
        self.save()
