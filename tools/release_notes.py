"""지난 릴리스 이후 커밋에서 '달라진 점'을 뽑아 릴리스 본문(마크다운)을 만든다.

- 커밋 본문에 '- ' 로 시작하는 줄이 있으면 그 줄들을, 없으면 커밋 제목을 쓴다.
- 깃허브 웹 업로드 기본 메시지(Add files via upload, Update ... 등)는 건너뛴다.
사용: python tools/release_notes.py notes.md  (파일 이름을 안 주면 화면에 출력)
"""
import re
import subprocess
import sys

TRIVIAL = re.compile(r"^(Add files via upload|Update |Create |Delete |Rename |Merge |Revert \")", re.I)
SKIP = ("Co-Authored-By", "Claude-Session", "Signed-off-by")
MAX = 20


def git(*args: str) -> str:
    return subprocess.run(["git", *args], capture_output=True, text=True, encoding="utf-8").stdout.strip()


def main() -> None:
    prev = git("describe", "--tags", "--abbrev=0", "--match", "v*", "HEAD^")
    rng = f"{prev}..HEAD" if prev else "-1"
    log = git("log", "--no-merges", "--format=%s%x1f%b%x1e", rng)
    notes: list[str] = []
    for entry in log.split("\x1e"):
        if not entry.strip():
            continue
        subject, _, body = entry.strip().partition("\x1f")
        bullets = [ln.strip()[2:].strip() for ln in body.splitlines() if ln.strip().startswith("- ")]
        bullets = [b for b in bullets if b and not b.startswith(SKIP)]
        if bullets:
            notes += bullets
        elif subject and not TRIVIAL.match(subject):
            notes.append(subject.strip())
    seen, out = set(), []
    for n in notes:
        if n not in seen:
            seen.add(n)
            out.append(n)
    if not out:
        out = ["자잘한 수정"]
    text = "\n".join(f"- {n}" for n in out[:MAX]) + "\n"
    if len(sys.argv) > 1:
        with open(sys.argv[1], "w", encoding="utf-8") as f:
            f.write(text)
    else:
        print(text, end="")


if __name__ == "__main__":
    main()
