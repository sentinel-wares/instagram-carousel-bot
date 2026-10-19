"""Draws Instagram carousel slides with Pillow (free, no Canva needed).

Two looks, chosen with the CARD_STYLE variable (see render_slide):
  "radar"   (default) navy gradient + amber radar rings, bold text, numbered points, progress pills.
  "classic" the original photo background with a white tweet-style card (described below).

Classic look: a full-bleed background photo, a dark fade towards the bottom, and a
rounded white card carrying the brand name, handle and the slide text, in the
style of "tweet-like" carousel slides. Output is a 1080x1350 (4:5) JPEG, the
only image format Instagram accepts for carousels.
"""

import math
import random
import re
from pathlib import Path

from PIL import Image, ImageColor, ImageDraw, ImageFont, ImageOps

W, H = 1080, 1350
FONT_DIR = Path(__file__).parent / "fonts"
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}

CARD_X = 110
CARD_W = W - 2 * CARD_X
PAD = 46
AVATAR = 104
MAX_LINES = 5
SS = 2   # supersampling factor for smooth card edges

INK = (15, 20, 25)
MUTED = (96, 108, 120)

# Dark, security-flavoured palettes for the generated fallback background.
PALETTES = [
    ("#050b1a", "#0f3a5f"),
    ("#07110f", "#0e4b45"),
    ("#0b0a1f", "#3b2a7a"),
    ("#10080a", "#5a1f2b"),
    ("#04101c", "#12466e"),
]


def _font(name: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONT_DIR / name), size)


def list_backgrounds(folder: Path) -> list:
    if not folder.is_dir():
        return []
    return sorted(p for p in folder.iterdir() if p.suffix.lower() in IMAGE_EXTS)


def _cover(img: Image.Image) -> Image.Image:
    """Fill the canvas, cropping from slightly above centre so faces stay in frame."""
    img = ImageOps.exif_transpose(img).convert("RGB")
    return ImageOps.fit(img, (W, H), method=Image.LANCZOS, centering=(0.5, 0.3))


def fallback_background(seed: int) -> Image.Image:
    """A deterministic dark gradient with a faint dot grid, used when no photos exist."""
    rng = random.Random(seed)
    c1, c2 = rng.choice(PALETTES)
    mask = Image.linear_gradient("L").rotate(rng.choice([0, 45, 135, 180]), expand=False).resize((W, H))
    img = ImageOps.colorize(mask, black=c1, white=c2).convert("RGB")
    dots = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(dots)
    step = 54
    for x in range(step // 2, W, step):
        for y in range(step // 2, H, step):
            d.ellipse((x - 2, y - 2, x + 2, y + 2), fill=(255, 255, 255, 22))
    return Image.alpha_composite(img.convert("RGBA"), dots).convert("RGB")


def _bottom_fade(img: Image.Image) -> Image.Image:
    """Darken towards the bottom (to near black) so the card and text stand out."""
    fade_h = int(H * 0.68)
    grad = Image.linear_gradient("L").resize((W, fade_h))
    grad = grad.point(lambda v: min(255, int(((v / 255) ** 1.35) * 255 * 1.02)))
    mask = Image.new("L", (W, H), 0)
    mask.paste(grad, (0, H - fade_h))
    out = img.copy()
    out.paste(Image.new("RGB", (W, H), (0, 0, 0)), (0, 0), mask)
    return out


def _wrap(text: str, font: ImageFont.FreeTypeFont, max_w: int) -> list:
    lines, cur = [], ""
    for word in text.split():
        trial = f"{cur} {word}".strip()
        if font.getlength(trial) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def _fit_text(text: str, max_w: int):
    """Largest font size (48 down to 34) that keeps the text within MAX_LINES."""
    for size in range(48, 33, -2):
        font = _font("Inter-Medium.otf", size)
        lines = _wrap(text, font, max_w)
        if len(lines) <= MAX_LINES:
            return font, lines, size
    return font, lines, size


def _avatar(size: int, initial: str, logo: Path | None) -> Image.Image:
    s = size * SS
    layer = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    mask = Image.new("L", (s, s), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, s - 1, s - 1), fill=255)
    if logo and logo.is_file():
        face = ImageOps.fit(Image.open(logo).convert("RGBA"), (s, s), method=Image.LANCZOS)
        layer.paste(face, (0, 0), mask)
        ImageDraw.Draw(layer).ellipse((SS, SS, s - 1 - SS, s - 1 - SS), outline=(205, 210, 216, 255), width=SS * 3)
    else:
        d = ImageDraw.Draw(layer)
        d.ellipse((0, 0, s - 1, s - 1), fill=(10, 18, 34, 255))
        d.ellipse((s * 0.06, s * 0.06, s * 0.94, s * 0.94), outline=(46, 160, 255, 255), width=SS * 4)
        f = _font("Inter-Bold.otf", int(s * 0.5))
        bbox = d.textbbox((0, 0), initial, font=f)
        d.text(((s - (bbox[2] - bbox[0])) / 2 - bbox[0], (s - (bbox[3] - bbox[1])) / 2 - bbox[1]),
               initial, font=f, fill=(255, 255, 255, 255))
    return layer.resize((size, size), Image.LANCZOS)


def _arrow_button(size: int) -> Image.Image:
    s = size * SS
    layer = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    w = SS * 4
    d.ellipse((w // 2, w // 2, s - w // 2, s - w // 2), outline=INK + (255,), width=w)
    cy, x0, x1 = s // 2, int(s * 0.26), int(s * 0.74)
    d.line((x0, cy, x1, cy), fill=INK + (255,), width=w)
    head = int(s * 0.17)
    d.line((x1 - head, cy - head, x1, cy), fill=INK + (255,), width=w)
    d.line((x1 - head, cy + head, x1, cy), fill=INK + (255,), width=w)
    return layer.resize((size, size), Image.LANCZOS)


def _card(lines: list, font, size: int, name: str, handle: str, logo: Path | None, arrow: bool) -> Image.Image:
    line_h = int(size * 1.3)
    header_h = AVATAR
    h = PAD + header_h + 30 + line_h * len(lines) + PAD - (line_h - size) // 2
    s = SS
    big = Image.new("RGBA", (CARD_W * s, h * s), (0, 0, 0, 0))
    d = ImageDraw.Draw(big)
    radius = 40 * s
    d.rounded_rectangle((0, 0, CARD_W * s - 1, h * s - 1), radius=radius, fill=(0, 0, 0, 255))
    d.rounded_rectangle((4 * s, 4 * s, CARD_W * s - 1 - 4 * s, h * s - 1 - 4 * s),
                        radius=radius - 4 * s, fill=(255, 255, 255, 255))
    card = big.resize((CARD_W, h), Image.LANCZOS)

    initial = (name.strip() or "S")[0].upper()
    card.alpha_composite(_avatar(AVATAR, initial, logo), (PAD, PAD))
    d2 = ImageDraw.Draw(card)
    tx = PAD + AVATAR + 24
    d2.text((tx, PAD + 14), name, font=_font("Inter-Bold.otf", 40), fill=INK)
    d2.text((tx, PAD + 14 + 54), handle, font=_font("Inter-Regular.otf", 32), fill=MUTED)
    if arrow:
        btn = _arrow_button(76)
        card.alpha_composite(btn, (CARD_W - PAD - 76, PAD + (AVATAR - 76) // 2))
    y = PAD + header_h + 30
    for line in lines:
        d2.text((PAD, y), line, font=font, fill=INK)
        y += line_h
    return card


def _render_classic(text: str, index: int, total: int, out_path: Path, *, background: Path | None = None,
                    seed: int = 0, name: str = "Sentinelwares", handle: str = "@sentinelwares",
                    logo: Path | None = None, footer: str = "") -> Path:
    """Render one classic (photo + white card) slide to `out_path` (JPEG) and return the path."""
    if background is not None:
        base = _cover(Image.open(background))
    else:
        base = fallback_background(seed)
    base = _bottom_fade(base)

    font, lines, size = _fit_text(text, CARD_W - 2 * PAD)
    card = _card(lines, font, size, name, handle, logo, arrow=(index == 0 and total > 1))
    top = min(int(H * 0.60), H - 190 - card.height)
    canvas = base.convert("RGBA")
    canvas.alpha_composite(card, (CARD_X, top))

    if footer and index == total - 1:
        d = ImageDraw.Draw(canvas)
        f = _font("Inter-SemiBold.otf", 34)
        tw = f.getlength(footer)
        d.text(((W - tw) / 2, H - 120), footer, font=f, fill=(255, 255, 255, 235))

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.convert("RGB").save(out_path, "JPEG", quality=90, optimize=True)
    return out_path


# ---------------------------------------------------------------------------
# "radar" style
# ---------------------------------------------------------------------------
NAVY_T = (9, 16, 32)
NAVY_B = (20, 33, 64)
AMBER = (245, 168, 0)
WHITE = (255, 255, 255)
R_MUTED = (176, 188, 210)
PILL_OFF = (70, 84, 118)
MARGIN = 80                 # keeps text inside Instagram's centre-crop grid preview
TEXT_W = W - 2 * MARGIN
TEXT_BOTTOM = 1190          # text must end above the footer
BRAND_URL = "surfacia.in"
_NUM_RE = re.compile(r"^\s*(\d{1,2})\s*[).:]\s+(.*)$")


def _rf(name: str, size: float) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONT_DIR / name), int(size * SS))


def _s(v: float) -> int:
    return int(round(v * SS))


def parse_slide(text: str):
    """'3) Change defaults' -> ('03', 'Change defaults'); unnumbered text -> (None, text)."""
    m = _NUM_RE.match(text)
    if m:
        return f"{int(m.group(1)):02d}", m.group(2).strip()
    return None, " ".join(text.split())


def _radar_dots(rng: random.Random, center, avoid: list, count: int = 8, h: int = H) -> list:
    """Seeded dot layout around the rings, kept away from the text and header areas."""
    cx, cy = center
    dots, tries = [], 0
    while len(dots) < count and tries < 400:
        tries += 1
        ang = rng.uniform(0, 2 * math.pi)
        dist = rng.uniform(60, 460)
        x, y = cx + dist * math.cos(ang), cy + dist * math.sin(ang)
        if not (40 < x < W - 40 and 40 < y < h - 40):
            continue
        if any(x0 - 30 <= x <= x1 + 30 and y0 - 30 <= y <= y1 + 30 for x0, y0, x1, y1 in avoid):
            continue
        dots.append((x, y, rng.choice([5, 6, 8]), rng.choice([150, 180, 210, 235])))
    return dots


def _radar_background(center, seed: int, avoid: list, h: int = H) -> Image.Image:
    strip = Image.new("RGB", (1, h * SS))
    px = strip.load()
    for y in range(h * SS):
        t = y / (h * SS - 1)
        px[0, y] = tuple(int(NAVY_T[i] + (NAVY_B[i] - NAVY_T[i]) * t) for i in range(3))
    base = strip.resize((W * SS, h * SS)).convert("RGBA")
    ring = Image.new("RGBA", base.size, (0, 0, 0, 0))
    rd = ImageDraw.Draw(ring)
    cx, cy = center
    for r, a in [(130, 80), (260, 58), (400, 42), (550, 30), (720, 20)]:
        rd.ellipse([_s(cx - r), _s(cy - r), _s(cx + r), _s(cy + r)], outline=AMBER + (a,), width=_s(2))
    rd.line([_s(cx - 760), _s(cy), _s(cx + 760), _s(cy)], fill=AMBER + (28,), width=_s(1.6))
    rd.line([_s(cx), _s(cy - 760), _s(cx), _s(cy + 760)], fill=AMBER + (28,), width=_s(1.6))
    for x, y, rr, a in _radar_dots(random.Random(seed), center, avoid, h=h):
        rd.ellipse([_s(x - rr * 2.6), _s(y - rr * 2.6), _s(x + rr * 2.6), _s(y + rr * 2.6)], fill=AMBER + (26,))
        rd.ellipse([_s(x - rr), _s(y - rr), _s(x + rr), _s(y + rr)], fill=AMBER + (a,))
    return Image.alpha_composite(base, ring)


def _spaced(d, x, y, text, font, fill, spacing):
    cx = _s(x)
    for ch in text:
        d.text((cx, _s(y)), ch, font=font, fill=fill)
        cx += font.getlength(ch) + _s(spacing)


def _wrap_words(words: list, font, max_w: float) -> list:
    """words: [(text, colour)]. Returns lines, each a list of (text, colour)."""
    lines, cur, cur_w = [], [], 0.0
    space = font.getlength(" ") / SS
    for text, colour in words:
        w = font.getlength(text) / SS
        add = w if not cur else w + space
        if cur and cur_w + add > max_w:
            lines.append(cur)
            cur, cur_w = [(text, colour)], w
        else:
            cur.append((text, colour))
            cur_w += add
    if cur:
        lines.append(cur)
    return lines


def _fit_lines(words: list, top: float, sizes, max_lines: int, line_ratio: float, face: str,
               bottom: float = TEXT_BOTTOM):
    """Largest size whose wrapped text has <= max_lines and ends above TEXT_BOTTOM."""
    for size in sizes:
        font = _rf(face, size)
        lines = _wrap_words(words, font, TEXT_W)
        line_h = size * line_ratio
        if len(lines) <= max_lines and top + len(lines) * line_h <= bottom:
            return font, lines, line_h
    return font, lines, line_h


def _draw_lines(d, lines, font, x, y, line_h):
    space = font.getlength(" ") / SS
    for i, line in enumerate(lines):
        cx = x
        for text, colour in line:
            d.text((_s(cx), _s(y + i * line_h)), text, font=font, fill=colour)
            cx += font.getlength(text) / SS + space


def _render_radar(text: str, index: int, total: int, out_path: Path, *, seed: int = 0,
                  footer: str = "", name: str = "Sentinelwares") -> Path:
    num, body = parse_slide(text)
    cover = index == 0
    last = index == total - 1 and total > 1
    words = body.split()
    colours = [WHITE] * len(words)
    if cover or last or num is None:
        colours[-1] = AMBER                       # last word in amber, like the cover hook
    wlist = list(zip(words, colours))

    if cover:
        top = 520
        font, lines, line_h = _fit_lines(wlist, top, range(100, 63, -4), 5, 1.18, "Inter-ExtraBold.otf")
        center = (880, 330)
    elif num:
        top = 640
        font, lines, line_h = _fit_lines(wlist, top, range(78, 51, -4), 5, 1.26, "Inter-ExtraBold.otf")
        center = (200, 1020)
    else:
        top = 430
        font, lines, line_h = _fit_lines(wlist, top, range(84, 51, -4), 7, 1.24, "Inter-ExtraBold.otf")
        center = (880, 1010) if seed % 2 else (200, 1020)

    text_box = (MARGIN, top, W - MARGIN, top + len(lines) * line_h)
    avoid = [text_box, (0, 60, W, 140), (0, 1220, W, 1320)]
    if cover:
        avoid.append((MARGIN, 440, W - MARGIN, 490))
    if num:
        avoid.append((MARGIN, 330, 560, 600))
    img = _radar_background(center, seed, avoid)
    d = ImageDraw.Draw(img)

    # header
    d.rounded_rectangle([_s(MARGIN), _s(84), _s(MARGIN + 12), _s(120)], radius=_s(3), fill=AMBER)
    _spaced(d, MARGIN + 32, 86, "SENTINELWARES", _rf("Inter-Bold.otf", 30), WHITE, 5)

    if cover:
        _spaced(d, MARGIN, 452, "SECURITY BRIEF", _rf("Inter-Bold.otf", 28), AMBER, 5)
    elif num:
        d.text((_s(MARGIN), _s(330)), num, font=_rf("Inter-ExtraBold.otf", 230), fill=AMBER)
    _draw_lines(d, lines, font, MARGIN, top, line_h)

    # footer: swipe cue (or the follow line on the last slide), url, progress pills
    if last:
        if footer:
            d.text((_s(MARGIN), _s(1236)), footer,
                   font=_rf("Inter-SemiBold.otf", 28), fill=WHITE)
    else:
        d.text((_s(MARGIN), _s(1236)), "Swipe  \u2192", font=_rf("Inter-SemiBold.otf", 34), fill=WHITE)
        f_url = _rf("Inter-Medium.otf", 30)
        d.text((_s(W - MARGIN - f_url.getlength(BRAND_URL) / SS), _s(1240)), BRAND_URL, font=f_url, fill=R_MUTED)
    x = MARGIN
    for i in range(total):
        w = 44 if i == index else 14
        d.rounded_rectangle([_s(x), _s(1296), _s(x + w), _s(1306)], radius=_s(5),
                            fill=AMBER if i == index else PILL_OFF)
        x += w + 10

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.convert("RGB").resize((W, H), Image.LANCZOS).save(out_path, "JPEG", quality=92, optimize=True)
    return out_path


STORY_W, STORY_H = 1080, 1920


def render_story(text: str, out_path: Path, *, seed: int = 0) -> Path:
    """A 1080x1920 (9:16) Instagram Story teaser for a new carousel: the hook in the radar style.
    Text stays inside the Story safe zone (clear of the top profile bar and the bottom reply bar)."""
    _, body = parse_slide(text)
    words = body.split()
    colours = [WHITE] * len(words)
    colours[-1] = AMBER
    top = 700
    font, lines, line_h = _fit_lines(list(zip(words, colours)), top, range(100, 63, -4), 6, 1.18,
                                     "Inter-ExtraBold.otf", bottom=1420)
    avoid = [(MARGIN, top - 90, W - MARGIN, top + len(lines) * line_h), (0, 230, W, 330), (0, 1440, W, 1580)]
    img = _radar_background((880, 480), seed, avoid, h=STORY_H)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([_s(MARGIN), _s(264), _s(MARGIN + 12), _s(300)], radius=_s(3), fill=AMBER)
    _spaced(d, MARGIN + 32, 266, "SENTINELWARES", _rf("Inter-Bold.otf", 30), WHITE, 5)
    _spaced(d, MARGIN, top - 80, "NEW POST", _rf("Inter-Bold.otf", 28), AMBER, 5)
    _draw_lines(d, lines, font, MARGIN, top, line_h)
    cue = "New carousel on our feed"
    f_cue = _rf("Inter-SemiBold.otf", 34)
    cw = f_cue.getlength(cue) / SS
    d.rounded_rectangle([_s(MARGIN), _s(1450), _s(MARGIN + cw + 96), _s(1530)], radius=_s(40), fill=AMBER)
    d.text((_s(MARGIN + 36), _s(1468)), cue, font=f_cue, fill=NAVY_T)
    d.text((_s(MARGIN + cw + 60), _s(1466)), "\u2193", font=f_cue, fill=NAVY_T)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.convert("RGB").resize((STORY_W, STORY_H), Image.LANCZOS).save(out_path, "JPEG", quality=92, optimize=True)
    return out_path


def render_slide(text: str, index: int, total: int, out_path: Path, *, background: Path | None = None,
                 seed: int = 0, name: str = "Sentinelwares", handle: str = "@sentinelwares",
                 logo: Path | None = None, footer: str = "", style: str = "radar") -> Path:
    """Render one slide to `out_path` (JPEG) and return the path. `style`: "radar" or "classic"."""
    if (style or "radar").lower() == "classic":
        return _render_classic(text, index, total, out_path, background=background, seed=seed, name=name,
                               handle=handle, logo=logo, footer=footer)
    return _render_radar(text, index, total, out_path, seed=seed, footer=footer, name=name)


def pick_backgrounds(photos: list, count: int, recent: list, rng: random.Random) -> list:
    """One background per slide: avoid recently used photos and never repeat one
    on adjacent slides. Returns Paths, or None entries (fallback) when there are no photos."""
    if not photos:
        return [None] * count
    recent_set = set(recent)
    pool = [p for p in photos if p.name not in recent_set] or list(photos)
    rng.shuffle(pool)
    chosen = []
    for i in range(count):
        options = [p for p in pool if not chosen or p != chosen[-1]] or list(photos)
        pick = next((p for p in options if p not in chosen), None) or rng.choice(options)
        chosen.append(pick)
    return chosen
