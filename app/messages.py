"""캐릭터 대사 만들기 (호격 조사, 시간 표현)."""
from __future__ import annotations

from datetime import date, datetime


def _has_batchim(ch: str) -> bool | None:
    code = ord(ch) - 0xAC00
    if 0 <= code < 11172:
        return code % 28 != 0
    return None  # 한글이 아님


def call_name(name: str) -> str:
    """'지유' -> '지유야', '민준' -> '민준아', 이름 없으면 '저기'."""
    name = name.strip()
    if not name:
        return "저기"
    b = _has_batchim(name[-1])
    if b is None:
        return name
    return name + ("아" if b else "야")


def time_text(hh: int, mm: int) -> str:
    ampm = "오전" if hh < 12 else "오후"
    h12 = hh % 12 or 12
    return f"{ampm} {h12}시" + (f" {mm}분" if mm else "")


def day_text(d: date, today: date) -> str:
    delta = (d - today).days
    if delta == 0:
        return "오늘"
    if delta == 1:
        return "내일"
    return f"{d.month}월 {d.day}일"


def before_message(name: str, title: str, when: datetime, now: datetime) -> str:
    minutes = max(1, round((when - now).total_seconds() / 60))
    return (
        f"{call_name(name)}! {day_text(when.date(), now.date())} "
        f"{time_text(when.hour, when.minute)}에 {title} 일정이 있어!\n"
        f"{minutes}분 남았어."
    )


def on_time_message(name: str, title: str) -> str:
    return f"{call_name(name)}! 지금 {title} 시간이야!"


def today_summary(name: str, titles_times: list[tuple[str, str]]) -> str:
    n = len(titles_times)
    title, hhmm = titles_times[0]
    hh, mm = map(int, hhmm.split(":"))
    if n == 1:
        return f"{call_name(name)}! 오늘은 {time_text(hh, mm)}에 {title} 일정이 있어."
    return f"{call_name(name)}! 오늘 남은 일정이 {n}개 있어.\n첫 번째는 {time_text(hh, mm)} {title}!"
