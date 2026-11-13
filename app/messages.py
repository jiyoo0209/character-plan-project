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


# ---- 캐릭터별 말투 ----
# 치이카와: 짧은 감탄 (와…! 앗…!)  /  우사기: 야하! 우라! 하아?  /  쿠리만쥬: 느긋한 선배 (하아— ~구먼)
VOICES: dict[str, dict[str, str]] = {
    "chiikawa": {
        "checking": "새 버전 있나 볼게…!",
        "latest": "와…! 지금이 최신 버전이야!\n(v{ver})",
        "check_fail": "앗…! 확인을 못 했어.\n인터넷을 확인해 줘…!",
        "hello": "와…! 반가워, {who}!\n나를 누르면 일정을 볼 수 있어…!",
        "before": "앗…! {who}, {day} {time}에 {title} 일정 있어!\n{minutes}분 남았어…!",
        "on_time": "와…! {who}, 지금 {title} 시간이야…!",
        "none": "후…! {who}, 오늘은 남은 일정 없어.\n푹 쉬자…!",
        "today": "와…! {who}, 오늘 일정 {n}개야!",
        "more": "· 그리고 {n}개 더…!",
        "dday_today": "와…! 오늘은 {title} D-day야! 힘내…!",
        "dday": "D-day도 있어…!",
    },
    "usagi": {
        "checking": "야하! 새 버전 찾아볼게!",
        "latest": "야하! 최신 버전이야! 우라!\n(v{ver})",
        "check_fail": "하아? 확인이 안 돼!\n인터넷 좀 봐 줘!",
        "hello": "야하! 반가워, {who}!\n나 누르면 일정 보여 줄게! 우라!",
        "before": "야하! {who}! {day} {time}에 {title}!\n{minutes}분 남았어! 우라!",
        "on_time": "우라! {who}! 지금 {title} 시간이야!",
        "none": "하아? {who}, 오늘 남은 일정 없어!\n야하! 놀자!",
        "today": "야하! {who}! 오늘 일정 {n}개!",
        "more": "· 그리고 {n}개 더! 우라!",
        "dday_today": "우라! 오늘은 {title} D-day! 가자!",
        "dday": "야하! D-day도 있어!",
    },
    "kurimanju": {
        "checking": "하아— 어디 한번 볼까.",
        "latest": "하아— 이미 최신 버전이구먼.\n(v{ver})",
        "check_fail": "하아— 확인이 안 되는구먼.\n인터넷을 한번 보게나.",
        "hello": "하아— 반갑구먼, {who}.\n나를 누르면 일정을 보여 주지.",
        "before": "하아— {who}, {day} {time}에 {title} 일정이 있구먼.\n{minutes}분 남았네.",
        "on_time": "하아— {who}, 이제 {title} 시간이구먼.",
        "none": "하아— {who}, 오늘은 남은 일정이 없구먼.\n느긋하게 쉬게나.",
        "today": "하아— {who}, 오늘은 일정이 {n}개 있구먼.",
        "more": "· 그리고 {n}개 더 있네.",
        "dday_today": "하아— 오늘이 {title} D-day로구먼. 힘내게나.",
        "dday": "하아— 등록된 D-day도 알려 주지.",
    },
}


def _line(cid: str, key: str, **kw) -> str:
    return VOICES.get(cid, VOICES["chiikawa"])[key].format(**kw)


def hello_message(name: str, cid: str = "chiikawa") -> str:
    """처음 실행했을 때 인사."""
    return _line(cid, "hello", who=call_name(name))


def update_check_message(kind: str, cid: str = "chiikawa", ver: str = "") -> str:
    """메뉴의 '업데이트 확인' 말풍선. kind: checking / latest / check_fail."""
    return _line(cid, kind, ver=ver)


def before_message(name: str, title: str, when: datetime, now: datetime, cid: str = "chiikawa") -> str:
    minutes = max(1, round((when - now).total_seconds() / 60))
    return _line(
        cid, "before", who=call_name(name), title=title, minutes=minutes,
        day=day_text(when.date(), now.date()), time=time_text(when.hour, when.minute),
    )


def on_time_message(name: str, title: str, cid: str = "chiikawa") -> str:
    return _line(cid, "on_time", who=call_name(name), title=title)


def today_summary(name: str, titles_times: list[tuple[str, str]]) -> str:
    n = len(titles_times)
    title, hhmm = titles_times[0]
    hh, mm = map(int, hhmm.split(":"))
    if n == 1:
        return f"{call_name(name)}! 오늘은 {time_text(hh, mm)}에 {title} 일정이 있어."
    return f"{call_name(name)}! 오늘 남은 일정이 {n}개 있어.\n첫 번째는 {time_text(hh, mm)} {title}!"


def nights_text(days: int) -> str:
    """기간 일정 길이: 1 → '당일치기', 3 → '2박 3일'."""
    return "당일치기" if days <= 1 else f"{days - 1}박 {days}일"


def range_text(start: date, end: date) -> str:
    """'11월 20일 ~ 22일 · 2박 3일' (달이 바뀌면 '11월 30일 ~ 12월 2일 · …')."""
    days = (end - start).days + 1
    if days <= 1:
        return f"{start.month}월 {start.day}일 · 당일치기"
    tail = f"{end.day}일" if (end.year, end.month) == (start.year, start.month) else f"{end.month}월 {end.day}일"
    return f"{start.month}월 {start.day}일 ~ {tail} · {nights_text(days)}"


def range_day_text(nth: int, span: int) -> str:
    """기간 일정 그날 표시: '1일째' / 마지막 날은 '마지막 날'."""
    return "마지막 날" if nth == span and span > 1 else f"{nth}일째"


def dday_text(days: int) -> str:
    """남은 날 → 'D-3' / 'D-day'."""
    return "D-day" if days <= 0 else f"D-{days}"


def briefing_today(name: str, items: list[tuple[str, str]], cid: str = "chiikawa") -> str:
    """하루 브리핑 ①: 오늘 (남은) 일정. items = [(제목, HH:MM)] 시간 순. 시간이 '' 이면 기간 일정(여행)."""
    who = call_name(name)
    if not items:
        return _line(cid, "none", who=who)
    lines = [_line(cid, "today", who=who, n=len(items))]
    for title, hhmm in items[:4]:
        if not hhmm:
            lines.append(f"· {title}")
            continue
        hh, mm = map(int, hhmm.split(":"))
        lines.append(f"· {time_text(hh, mm)} {title}")
    if len(items) > 4:
        lines.append(_line(cid, "more", n=len(items) - 4))
    return "\n".join(lines)


def briefing_dday(ddays: list[tuple[str, int]], cid: str = "chiikawa") -> str | None:
    """하루 브리핑 ②: 등록된 D-day. ddays = [(제목, 남은 날)] 가까운 순. 없으면 None."""
    if not ddays:
        return None
    today = [t for t, n in ddays if n <= 0]
    lines = [_line(cid, "dday_today", title=today[0]) if today else _line(cid, "dday")]
    for title, n in ddays[:4]:
        if n > 0 or not today or title != today[0]:
            lines.append(f"· {title} {dday_text(n)}")
    return "\n".join(lines)
