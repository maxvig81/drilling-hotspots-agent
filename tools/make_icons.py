"""Generate the declarative agent's icons: an oil-drilling derrick.

Writes ``agent/appPackage/color.png`` (192x192, full colour) and
``agent/appPackage/outline.png`` (32x32, white silhouette on transparent) — the
two icons required by the Teams/M365 app manifest. Everything is drawn at 4x and
downscaled with LANCZOS for smooth anti-aliased edges.

    python tools/make_icons.py
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

OUT = Path(__file__).resolve().parent.parent / "agent" / "appPackage"

AMBER = (255, 138, 30, 255)
AMBER_HI = (255, 178, 82, 255)
NAVY_TOP = (23, 46, 71)
NAVY_BOT = (10, 20, 32)
WHITE = (255, 255, 255, 255)

# Derrick geometry in a 192x192 design space.
BASE_Y = 150.0
LEG_BL, LEG_BR = (60.0, BASE_Y), (132.0, BASE_Y)   # bottom of legs
LEG_TL, LEG_TR = (86.0, 42.0), (106.0, 42.0)       # top of legs
BRACE_LEVELS = [150.0, 128.0, 106.0, 84.0, 62.0, 44.0]


def _leg_x(y: float, left: bool) -> float:
    t = (BASE_Y - y) / (BASE_Y - LEG_TL[1])
    if left:
        return LEG_BL[0] + (LEG_TL[0] - LEG_BL[0]) * t
    return LEG_BR[0] + (LEG_TR[0] - LEG_BR[0]) * t


DESIGN = 192.0  # design-space dimension; scaled to each canvas


def _draw_derrick(d: ImageDraw.ImageDraw, sc: float, color, *, leg_w, brace_w,
                  detailed: bool):
    def p(x, y):
        return (x * sc, y * sc)

    def w(v):
        return max(1, int(round(v * sc)))

    # Platform / ground.
    d.rounded_rectangle([p(44, BASE_Y), p(148, BASE_Y + 9)],
                        radius=int(4 * sc), fill=color)
    # Legs.
    d.line([p(*LEG_BL), p(*LEG_TL)], fill=color, width=w(leg_w))
    d.line([p(*LEG_BR), p(*LEG_TR)], fill=color, width=w(leg_w))
    # Cross bracing between consecutive levels.
    for i in range(len(BRACE_LEVELS) - 1):
        y0, y1 = BRACE_LEVELS[i], BRACE_LEVELS[i + 1]
        l0, r0 = _leg_x(y0, True), _leg_x(y0, False)
        l1, r1 = _leg_x(y1, True), _leg_x(y1, False)
        # horizontal rung at the lower level
        d.line([p(l0, y0), p(r0, y0)], fill=color, width=w(brace_w))
        if detailed:
            d.line([p(l0, y0), p(r1, y1)], fill=color, width=w(brace_w))
            d.line([p(r0, y0), p(l1, y1)], fill=color, width=w(brace_w))
    # top rung
    d.line([p(_leg_x(44, True), 44), p(_leg_x(44, False), 44)],
           fill=color, width=w(brace_w))
    # Crown block + mast tip.
    d.rounded_rectangle([p(83, 33), p(109, 45)], radius=int(3 * sc), fill=color)
    d.line([p(96, 33), p(96, 20)], fill=color, width=w(leg_w + 1))
    d.ellipse([p(90, 12), p(102, 24)], fill=color)


def _lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def make_color(size: int = 192, S: int = 4) -> Image.Image:
    W = size * S
    # Vertical navy gradient.
    grad = Image.new("RGBA", (W, W))
    gd = ImageDraw.Draw(grad)
    for y in range(W):
        gd.line([(0, y), (W, y)], fill=_lerp(NAVY_TOP, NAVY_BOT, y / W) + (255,))
    mask = Image.new("L", (W, W), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, W - 1, W - 1],
                                           radius=int(W * 0.22), fill=255)
    base = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    img = Image.composite(grad, base, mask)

    # Soft orange "hotspot" glow behind the derrick.
    glow = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    gdd = ImageDraw.Draw(glow)
    cx, cy = int(W * 0.5), int(W * 0.55)
    for rad, alpha in [(0.30, 70), (0.22, 80), (0.14, 95)]:
        rr = int(W * rad)
        gdd.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], fill=(255, 120, 20, alpha))
    glow = glow.filter(ImageFilter.GaussianBlur(W * 0.03))
    glow = Image.composite(glow, Image.new("RGBA", (W, W), (0, 0, 0, 0)), mask)
    img = Image.alpha_composite(img, glow)

    d = ImageDraw.Draw(img)
    sc = W / DESIGN
    # Shadow pass then amber derrick.
    _draw_derrick(d, sc, (0, 0, 0, 90), leg_w=8, brace_w=5, detailed=True)
    _draw_derrick(d, sc, AMBER, leg_w=7, brace_w=4, detailed=True)

    return img.resize((size, size), Image.LANCZOS)


def make_outline(size: int = 32, S: int = 8) -> Image.Image:
    W = size * S
    img = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    _draw_derrick(d, W / DESIGN, WHITE, leg_w=7, brace_w=4, detailed=False)
    return img.resize((size, size), Image.LANCZOS)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    color = make_color()
    outline = make_outline()
    color.save(OUT / "color.png")
    outline.save(OUT / "outline.png")
    print(f"Wrote {OUT / 'color.png'} ({color.size}) and "
          f"{OUT / 'outline.png'} ({outline.size})")


if __name__ == "__main__":
    main()
