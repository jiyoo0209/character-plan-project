"""기본 캐릭터 '새싹이' 이미지를 생성합니다.

머리에 새싹이 난 동글동글한 민트색 모찌 캐릭터(오리지널 디자인).
실행: python tools/make_character.py
결과: assets/character.png (투명 배경), assets/icon.ico
"""
import math
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"

S = 1024  # 작업 캔버스(고해상도로 그린 뒤 축소해 안티앨리어싱)
OUT = 512

BODY = (217, 242, 225, 255)
BODY_SHADE = (196, 230, 207, 255)
LINE = (53, 89, 74, 255)
LEAF = (126, 196, 120, 255)
LEAF_DARK = (86, 150, 88, 255)
CHEEK = (255, 182, 160, 200)
EYE = (40, 52, 46, 255)
W = 22  # 외곽선 두께


def leaf_points(base, angle_deg, length, width, n=40):
    """끝이 뾰족한 잎사귀 모양 다각형 좌표."""
    bx, by = base
    a = math.radians(angle_deg)
    ux, uy = math.cos(a), math.sin(a)  # 잎 진행 방향
    px, py = -uy, ux  # 수직 방향
    pts = []
    for i in range(n + 1):
        t = i / n
        w = math.sin(math.pi * t) * width / 2
        pts.append((bx + ux * length * t + px * w, by + uy * length * t + py * w))
    for i in range(n, -1, -1):
        t = i / n
        w = math.sin(math.pi * t) * width / 2
        pts.append((bx + ux * length * t - px * w, by + uy * length * t - py * w))
    return pts


def draw():
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # 발
    for cx in (400, 624):
        d.ellipse((cx - 70, 860, cx + 70, 940), fill=BODY_SHADE, outline=LINE, width=W)

    # 몸통 (아래가 살짝 퍼진 모찌형)
    d.ellipse((170, 330, 854, 920), fill=BODY, outline=LINE, width=W)
    # 배 쪽 음영
    d.ellipse((300, 700, 724, 880), fill=BODY_SHADE)

    # 팔
    d.ellipse((130, 610, 250, 730), fill=BODY, outline=LINE, width=W)
    d.ellipse((774, 610, 894, 730), fill=BODY, outline=LINE, width=W)
    # 팔과 몸통 이음새 덮기
    d.ellipse((205, 600, 300, 740), fill=BODY)
    d.ellipse((724, 600, 819, 740), fill=BODY)

    # 새싹 줄기
    stem = [(512, 345), (508, 300), (515, 255), (526, 215)]
    d.line(stem, fill=LEAF_DARK, width=26, joint="curve")
    # 잎 두 장
    for base, ang, ln, wd in (((522, 225), 205, 190, 110), ((526, 220), -25, 210, 120)):
        pts = leaf_points(base, ang, ln, wd)
        d.polygon(pts, fill=LEAF, outline=LINE)
        d.line(pts + [pts[0]], fill=LINE, width=14, joint="curve")
        # 잎맥
        a = math.radians(ang)
        d.line(
            (base[0], base[1], base[0] + math.cos(a) * ln * 0.75, base[1] + math.sin(a) * ln * 0.75),
            fill=LEAF_DARK,
            width=9,
        )

    # 볼
    d.ellipse((290, 600, 390, 660), fill=CHEEK)
    d.ellipse((634, 600, 734, 660), fill=CHEEK)

    # 눈 (세로로 긴 점눈 + 하이라이트)
    for cx in (395, 629):
        d.ellipse((cx - 26, 520, cx + 26, 595), fill=EYE)
        d.ellipse((cx - 10, 533, cx + 8, 556), fill=(255, 255, 255, 255))

    # 입 (작게 벌린 웃는 입)
    d.chord((472, 600, 552, 670), start=0, end=180, fill=(214, 96, 96, 255), outline=LINE, width=12)

    return img.resize((OUT, OUT), Image.LANCZOS)


def main():
    ASSETS.mkdir(exist_ok=True)
    img = draw()
    img = img.crop(img.getbbox())  # 여백 제거
    img.save(ASSETS / "character.png")

    # 아이콘: 정사각형 캔버스 가운데에 배치
    side = max(img.size)
    icon = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    icon.paste(img, ((side - img.width) // 2, (side - img.height) // 2), img)
    icon.save(ASSETS / "icon.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print("saved", ASSETS / "character.png", img.size)


if __name__ == "__main__":
    main()
