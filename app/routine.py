"""캐릭터의 하루: 내 오늘 일정에 맞춰 바탕화면 캐릭터 그림을 바꾼다. 소리는 내지 않는다.

캐릭터마다 정해 둔 것 (assets/routines/<캐릭터 id>.json): 일어나는 시각, 자는 시각, 밥 먹는 시각.
    {"wakeup": "11:00", "sleep": "23:30",
     "meals": [{"time": "12:00", "name": "lunch", "label": "아점"}, ...]}

지금 무슨 그림을 보여 줄지 (위에서부터 먼저 맞는 것):
    1) 잠      자는 시각 ~ 일어나는 시각
               · 내 첫 일정이 일어나는 시각보다 이르면, 그 일정 1시간 전에 일어난다
               · 내 (안 끝낸) 마지막 일정이 자는 시각 뒤에 있으면, 그 일정 1시간 뒤에 잔다
    2) 밥      밥 시각부터 1시간 (그 사이 내 일정이 시작되면 거기서 끝)
    3) 내 일정  일정 시각부터 다음 일정 전까지 (밥 먹고 나서도 이어짐)
               · 체크리스트에서 체크하면 그때 끝 → 평소 모습
               · '기타' · 카테고리 없는 일정 · 그 카테고리 그림이 없을 때는 평소 모습
    4) 기상    일어나서 30분 (그 사이 내 일정이 시작되면 거기서 끝)
    5) 평소    기본 그림 (<캐릭터 id>.gif)

그림 파일: assets/characters/routine/<캐릭터 id>_<행동>.png (.gif .webp 도 됨)
    행동 = sleep · wakeup · 밥(eat1, eat2, eat3 … 중 하나를 그 끼니마다 무작위로. 번호 개수는 자유 ·
                              breakfast/lunch/dinner 그림이 있으면 그 끼니엔 그걸) ·
           내 일정 카테고리(work study game meet exercise hospital travel)
    그림이 아직 없으면 평소 그림을 보여 준다.
"""
from __future__ import annotations

import json
import random
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .categories import CATEGORIES
from .config import ASSETS_DIR, CHARACTERS_DIR

ROUTINES_DIR = ASSETS_DIR / "routines"
ROUTINE_IMAGES_DIR = CHARACTERS_DIR / "routine"
_IMAGE_EXTS = (".png", ".gif", ".webp")
_CATEGORY_KEYS = {name: key for name, key in CATEGORIES if key != "etc"}  # '일' → 'work' ('기타'는 평소 모습)

DAY_END = 24 * 60 - 1
WAKE_BEFORE_MIN = 60  # 내 일정이 일찍 있으면 그 1시간 전에 기상
SLEEP_AFTER_MIN = 60  # 내 일정이 늦게 있으면 그 1시간 뒤에 잠
WAKEUP_MIN = 30
MEAL_MIN = 60


@dataclass(frozen=True)
class Meal:
    minute: int
    name: str  # breakfast / lunch / dinner … (그림 이름)
    label: str = ""


@dataclass(frozen=True)
class Routine:
    wakeup: int  # 0시부터 몇 분
    sleep: int
    meals: tuple[Meal, ...] = ()


@dataclass(frozen=True)
class Action:
    images: tuple[str, ...]  # 찾아볼 그림 이름 순서 (앞에 것이 없으면 다음 것). 'eat*' = eat, eat1, eat2 … 중 하나
    label: str
    seed: str = ""  # 무작위로 고를 때 기준 (같은 끼니 동안은 같은 그림)


@dataclass(frozen=True)
class Plan:  # 내 일정 한 개 (이 모듈에 필요한 것만)
    minute: int
    category: str
    title: str = ""
    done: bool = False


def _parse_time(text) -> int:
    h, m = str(text).strip().split(":")
    h, m = int(h), int(m)
    if not (0 <= h < 24 and 0 <= m < 60):
        raise ValueError(text)
    return h * 60 + m


def load_routine(cid: str) -> Routine | None:
    """캐릭터의 기상 · 잠 · 밥 시각. 파일이 없거나 잘못됐으면 None = 늘 평소 그림."""
    try:
        raw = json.loads((ROUTINES_DIR / f"{cid}.json").read_text(encoding="utf-8"))
        wakeup, sleep = _parse_time(raw["wakeup"]), _parse_time(raw["sleep"])
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return None
    if sleep <= wakeup:  # 자정을 넘겨 자는 건 아직 안 됨: 하루 끝에 잔다
        sleep = DAY_END
    meals = []
    for m in raw.get("meals", []) if isinstance(raw.get("meals"), list) else []:
        try:
            meals.append(Meal(_parse_time(m["time"]), str(m["name"]).strip(), str(m.get("label", ""))))
        except (KeyError, TypeError, ValueError):
            continue  # 잘못 적힌 줄만 건너뛴다
    meals = [m for m in meals if m.name]
    return Routine(wakeup, sleep, tuple(sorted(meals, key=lambda m: m.minute)))


def plans_from(occurrences) -> list[Plan]:
    """storage.Occurrence 목록 → Plan 목록 (시각 순)."""
    out = []
    for o in occurrences:
        try:
            out.append(Plan(_parse_time(o.time), o.category or "", o.title, bool(o.done)))
        except ValueError:
            continue
    return sorted(out, key=lambda p: p.minute)


def day_bounds(r: Routine, plans: list[Plan]) -> tuple[int, int]:
    """오늘 실제로 일어나고 자는 시각 (내 일정에 맞춰 당기거나 미룸)."""
    wake, sleep = r.wakeup, r.sleep
    if plans and plans[0].minute < wake:
        wake = max(0, plans[0].minute - WAKE_BEFORE_MIN)
    open_plans = [p for p in plans if not p.done]
    if open_plans and open_plans[-1].minute >= sleep:
        sleep = min(DAY_END, open_plans[-1].minute + SLEEP_AFTER_MIN)
    return wake, sleep


def current_action(r: Routine | None, plans: list[Plan], now: datetime) -> Action | None:
    """지금 할 행동. None = 평소 모습."""
    if r is None:
        return None
    t = now.hour * 60 + now.minute
    wake, sleep = day_bounds(r, plans)
    if t < wake or t >= sleep:
        return Action(("sleep",), "쿨쿨 자는 중")

    def next_plan_from(m: int) -> int:  # m 이후(같은 분 포함) 처음 시작하는 내 일정 — 같은 분이면 내 일정이 먼저
        return next((p.minute for p in plans if p.minute >= m), sleep)

    for meal in r.meals:
        if wake <= meal.minute <= t < min(meal.minute + MEAL_MIN, next_plan_from(meal.minute), sleep):
            return Action((meal.name, "eat*"), meal.label or "밥 먹는 중", f"{now.date()}|{meal.minute}")

    started = [p for p in plans if p.minute <= t]
    if started:
        cur = started[-1]  # 가장 최근에 시작한 내 일정이 다음 일정 전까지 이어진다
        key = _CATEGORY_KEYS.get(cur.category)
        if cur.done or key is None:  # 체크해서 일찍 끝냄 · '기타' · 카테고리 없음 → 다음 일정까지 평소 모습
            return None
        return Action((key,), cur.title)

    if t < min(wake + WAKEUP_MIN, next_plan_from(wake)):
        return Action(("wakeup",), "일어나는 중")
    return None


def action_image(cid: str, act: Action | None) -> Path | None:
    """행동 그림 파일 (<캐릭터>_<행동>.png 등). 아직 안 넣었으면 None."""
    if act is None:
        return None
    for name in act.images:
        if name.endswith("*"):  # 번호 붙은 그림들 중 하나
            pool = _numbered(cid, name[:-1])
            if pool:
                return random.Random(f"{cid}|{act.seed}").choice(pool)
            continue
        for ext in _IMAGE_EXTS:
            p = ROUTINE_IMAGES_DIR / f"{cid}_{name}{ext}"
            if p.is_file():
                return p
    return None


def _numbered(cid: str, base: str) -> list[Path]:
    """<cid>_<base>.png, <cid>_<base>1.png, <cid>_<base>2.gif … (번호 개수 · 빠진 번호 상관없음). 이름 순."""
    pat = re.compile(rf"{re.escape(cid)}_{re.escape(base)}\d*", re.IGNORECASE)
    try:
        files = [f for f in ROUTINE_IMAGES_DIR.iterdir()
                 if f.is_file() and f.suffix.lower() in _IMAGE_EXTS and pat.fullmatch(f.stem)]
    except OSError:
        return []
    by_stem: dict[str, Path] = {}  # 같은 이름이 .png 와 .gif 둘 다 있으면 하나만
    for f in sorted(files, key=lambda f: _IMAGE_EXTS.index(f.suffix.lower())):
        by_stem.setdefault(f.stem.lower(), f)
    return sorted(by_stem.values(), key=lambda f: f.name.lower())
