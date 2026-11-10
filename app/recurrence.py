"""반복 일정 규칙: 매일 / 매주(요일 여러 개) / 매월(N일 또는 N째 주 X요일) / 매년, 종료일 필수."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Iterator

KINDS = ("daily", "weekly", "monthly", "yearly")
KIND_LABEL = {"daily": "매일", "weekly": "매주", "monthly": "매월", "yearly": "매년"}
DAY_NAMES = "월화수목금토일"  # date.weekday() 순서
NTH_NAMES = ("첫째", "둘째", "셋째", "넷째", "다섯째")


@dataclass
class RepeatRule:
    kind: str  # KINDS 중 하나
    until: date  # 종료일 (이 날 포함)
    weekdays: tuple[int, ...] = ()  # 매주: 0=월 … 6=일
    monthly_nth: bool = False  # 매월: False = 매월 N일, True = 매월 N째 주 X요일
    skip: set[str] = field(default_factory=set)  # 빠진 날 (이 날만 지우기/바꾸기), YYYY-MM-DD


def nth_of(d: date) -> int:
    """그 달의 몇째 주 X요일인지 (1부터)."""
    return (d.day - 1) // 7 + 1


def monthly_day_text(start: date) -> str:
    return f"매월 {start.day}일"


def monthly_nth_text(start: date) -> str:
    return f"매월 {NTH_NAMES[nth_of(start) - 1]} 주 {DAY_NAMES[start.weekday()]}요일"


def occurs_on(start: date, rule: RepeatRule, d: date) -> bool:
    if d < start or d > rule.until or d.isoformat() in rule.skip:
        return False
    if rule.kind == "daily":
        return True
    if rule.kind == "weekly":
        return d.weekday() in (rule.weekdays or (start.weekday(),))
    if rule.kind == "monthly":
        if rule.monthly_nth:
            return d.weekday() == start.weekday() and nth_of(d) == nth_of(start)
        return d.day == start.day  # 31일처럼 없는 달은 건너뜀
    if rule.kind == "yearly":
        return (d.month, d.day) == (start.month, start.day)  # 2월 29일은 윤년에만
    return False


def occurrences(start: date, rule: RepeatRule, frm: date, to: date) -> Iterator[date]:
    """frm~to (포함) 사이에 이 반복 일정이 있는 날들."""
    d, end = max(frm, start), min(to, rule.until)
    while d <= end:
        if occurs_on(start, rule, d):
            yield d
        d += timedelta(days=1)


def count(start: date, rule: RepeatRule) -> int:
    return sum(1 for _ in occurrences(start, rule, start, rule.until))


def rule_text(start: date, rule: RepeatRule, with_until: bool = True) -> str:
    """'매주 월 · 수 · 금' (+ ' · 12월 31일까지')."""
    if rule.kind == "weekly":
        days = sorted(rule.weekdays or (start.weekday(),), key=lambda w: (w + 1) % 7)  # 일요일부터
        head = "매주 " + " · ".join(DAY_NAMES[w] for w in days)
    elif rule.kind == "monthly":
        head = monthly_nth_text(start) if rule.monthly_nth else monthly_day_text(start)
    elif rule.kind == "yearly":
        head = f"매년 {start.month}월 {start.day}일"
    else:
        head = "매일"
    if with_until:
        u = rule.until
        until = f"{u.month}월 {u.day}일" if u.year == start.year else f"{u.year}년 {u.month}월 {u.day}일"
        head += f" · {until}까지"
    return head
