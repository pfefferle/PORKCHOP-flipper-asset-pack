#!/usr/bin/env python3
"""Generate Flipper Zero asset pack for PORKCHOP pig character.

Based on the ASCII art from https://github.com/0ct0sec/M5PORKCHOP
Renders pig faces as 128x64 pixel PNGs, then packs using the official
Momentum asset_packer format (heatshrink-compressed .bm/.bmx files).

Dependencies: pip install Pillow heatshrink2
"""

import io
import json
import os
import shutil
import struct
import tarfile
import zipfile

import heatshrink2
from PIL import Image, ImageDraw, ImageFont, ImageOps

SCREEN_W = 128
SCREEN_H = 64
PACK_NAME = "PORKCHOP"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Next-Flip Asset-Packs structure at project root:
#   source/PORKCHOP/  = compiled pack (.bm/.bmx), ready for SD card
#   download/         = archives of source/PORKCHOP/
#   preview/          = GIF previews
#   meta.json         = pack metadata
#   png/              = editable PNG sources (works with asset_packer.py)
PACK_DIR = BASE_DIR
SOURCE_DIR = os.path.join(PACK_DIR, "source", PACK_NAME)
PREVIEW_DIR = os.path.join(PACK_DIR, "preview")
DOWNLOAD_DIR = os.path.join(PACK_DIR, "download")
PNG_DIR = os.path.join(PACK_DIR, "png")

# Adafruit GFX default 5x7 bitmap font (glcdfont.c) - same as M5Stack default
# Each character is 5 bytes, columns left to right, LSB = top pixel
# Only the chars we need for the pig face + weather
GLCDFONT = {
    ' ':  [0x00, 0x00, 0x00, 0x00, 0x00],
    '!':  [0x00, 0x00, 0x5F, 0x00, 0x00],
    '#':  [0x14, 0x7F, 0x14, 0x7F, 0x14],
    '(':  [0x00, 0x1C, 0x22, 0x41, 0x00],
    ')':  [0x00, 0x41, 0x22, 0x1C, 0x00],
    '*':  [0x14, 0x08, 0x3E, 0x08, 0x14],
    '+':  [0x08, 0x08, 0x3E, 0x08, 0x08],
    '-':  [0x08, 0x08, 0x08, 0x08, 0x08],
    '.':  [0x00, 0x00, 0x60, 0x60, 0x00],
    '/':  [0x20, 0x10, 0x08, 0x04, 0x02],
    '0':  [0x3E, 0x51, 0x49, 0x45, 0x3E],
    '=':  [0x14, 0x14, 0x14, 0x14, 0x14],
    '?':  [0x02, 0x01, 0x59, 0x09, 0x06],
    '@':  [0x3E, 0x41, 0x5D, 0x59, 0x4E],
    'O':  [0x3E, 0x41, 0x41, 0x41, 0x3E],
    'T':  [0x03, 0x01, 0x7F, 0x01, 0x03],
    '\\': [0x02, 0x04, 0x08, 0x10, 0x20],
    '^':  [0x04, 0x02, 0x01, 0x02, 0x04],
    '_':  [0x40, 0x40, 0x40, 0x40, 0x40],
    'o':  [0x38, 0x44, 0x44, 0x44, 0x38],
    'v':  [0x1C, 0x20, 0x40, 0x20, 0x1C],
    'z':  [0x61, 0x59, 0x49, 0x4D, 0x43],
    '|':  [0x00, 0x00, 0x77, 0x00, 0x00],
}

# TTF font fallback for weather text / grass
FONT_CANDIDATES = [
    "/System/Library/Fonts/Menlo.ttc",
    "/System/Library/Fonts/Monaco.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    "/usr/share/fonts/TTF/DejaVuSansMono.ttf",
    "C:\\Windows\\Fonts\\consola.ttf",
    "C:\\Windows\\Fonts\\cour.ttf",
]
FONT_PATH = None
for _p in FONT_CANDIDATES:
    if os.path.exists(_p):
        FONT_PATH = _p
        break


# ── .bm/.bmx conversion (from Momentum asset_packer.py) ──────────────────

def convert_bm(img):
    """Convert PIL image to Flipper .bm format (heatshrink compressed)."""
    if not isinstance(img, Image.Image):
        img = Image.open(img)

    with io.BytesIO() as output:
        img = img.convert("1")
        img = ImageOps.invert(img)
        img.save(output, format="XBM")
        xbm = output.getvalue()

    f = io.StringIO(xbm.decode().strip())
    data = f.read().strip().replace("\n", "").replace(" ", "").split("=")[1][:-1]
    data_str = data[1:-1].replace(",", " ").replace("0x", "")
    data_bin = bytearray.fromhex(data_str)

    data_encoded_str = heatshrink2.compress(
        data_bin, window_sz2=8, lookahead_sz2=4
    )
    data_enc = bytearray(data_encoded_str)
    data_enc = bytearray([len(data_enc) & 0xFF, len(data_enc) >> 8]) + data_enc

    if len(data_enc) + 2 < len(data_bin) + 1:
        return b"\x01\x00" + data_enc
    else:
        return b"\x00" + data_bin


def convert_bmx(img):
    """Convert PIL image to Flipper .bmx format (width + height + .bm data)."""
    if not isinstance(img, Image.Image):
        img = Image.open(img)
    data = struct.pack("<II", *img.size)
    data += convert_bm(img)
    return data


# ── Pig face definitions ──────────────────────────────────────────────────

FACES = {
    "neutral_r": [" ?  ? ", "(o 00)", "(    )"],
    "neutral_l": [" ?  ? ", "(00 o)", "(    )z"],
    "happy_r":   [" ^  ^ ", "(^ 00)", "(    )"],
    "happy_l":   [" ^  ^ ", "(00 ^)", "(    )z"],
    "excited_r": [" !  ! ", "(@ 00)", "(    )"],
    "excited_l": [" !  ! ", "(00 @)", "(    )z"],
    "hunting_r": [" |  | ", "(= 00)", "(    )"],
    "hunting_l": [" |  | ", "(00 =)", "(    )z"],
    "sleepy_r":  [" v  v ", "(- 00)", "(    )"],
    "sleepy_l":  [" v  v ", "(00 -)", "(    )z"],
    "sad_r":     [" .  . ", "(T 00)", "(    )"],
    "sad_l":     [" .  . ", "(00 T)", "(    )z"],
    "angry_r":   [" \\  / ", "(# 00)", "(    )"],
    "angry_l":   [" \\  / ", "(00 #)", "(    )z"],
    "blink_r":   [" ?  ? ", "(- 00)", "(    )"],
    "blink_l":   [" ?  ? ", "(00 -)", "(    )z"],
    "sniff1_r":  [" ?  ? ", "(o oo)", "(    )"],
    "sniff2_r":  [" ?  ? ", "(o oO)", "(    )"],
    "sniff3_r":  [" ?  ? ", "(o Oo)", "(    )"],
}

import random

# Grass: scrolling row of random /\ like M5PORKCHOP original
# Generate 8 shifted patterns (simulates the scroll + mutation)
def _make_grass_patterns():
    patterns = []
    random.seed(42)
    base = [random.choice("/\\") for _ in range(26)]
    for frame in range(8):
        # Scroll: rotate the pattern
        shifted = base[frame % len(base):] + base[:frame % len(base)]
        # Mutate ~2 random positions per frame
        mutated = list(shifted)
        for _ in range(2):
            pos = random.randint(0, len(mutated) - 1)
            mutated[pos] = random.choice("/\\")
        patterns.append("".join(mutated))
    return patterns

GRASS_PATTERNS = _make_grass_patterns()


def draw_grass(draw, grass_frame, y):
    """Draw scrolling /\\ grass row like the original M5PORKCHOP.

    Uses the bitmap font at 1x scale, tiled across the full width.
    """
    pattern = GRASS_PATTERNS[grass_frame % len(GRASS_PATTERNS)]
    # Tile to fill screen width (each char = 6px at 1x)
    chars_needed = (SCREEN_W // 6) + 2
    full = (pattern * 2)[:chars_needed]
    draw_bitmap_text(draw, full, 0, y, scale=1)

# Cloud patterns (top of screen)
CLOUDS = [
    "  .--._   ._--.  ",
    " .--._    .--._  ",
    "._--.   .--._    ",
    "   .--._   ._--. ",
]

# Rain drop positions (x offsets for varied patterns)
random.seed(42)  # deterministic for reproducible builds
RAIN_PATTERNS = []
for _ in range(8):
    drops = [(random.randint(0, 127), random.randint(8, 48)) for _ in range(18)]
    RAIN_PATTERNS.append(drops)

# Star positions for night sky
STAR_PATTERNS = []
random.seed(7)
for _ in range(4):
    stars = [(random.randint(2, 125), random.randint(2, 30)) for _ in range(12)]
    STAR_PATTERNS.append(stars)


# ── Rendering ─────────────────────────────────────────────────────────────

def draw_glyph(draw, ch, x, y, scale=1, fill=0):
    """Draw a single character using the Adafruit GFX bitmap font.

    Each glyph is 5 columns x 7 rows. Scale multiplies pixel size.
    """
    if ch not in GLCDFONT:
        return
    cols = GLCDFONT[ch]
    for col_idx, col_byte in enumerate(cols):
        for row in range(7):
            if col_byte & (1 << row):
                px = x + col_idx * scale
                py = y + row * scale
                if scale == 1:
                    draw.point((px, py), fill=fill)
                else:
                    draw.rectangle(
                        [px, py, px + scale - 1, py + scale - 1], fill=fill
                    )


def draw_bitmap_text(draw, text, x, y, scale=1, fill=0):
    """Draw a string using the Adafruit GFX bitmap font.

    Character cell is (5*scale + scale) wide = 6*scale pixels per char.
    """
    cell_w = 6 * scale
    for i, ch in enumerate(text):
        if ch != " ":
            draw_glyph(draw, ch, x + i * cell_w, y, scale=scale, fill=fill)


def draw_text_fixedwidth(draw, text, x, y, font, cell_w, fill=0):
    """Draw text using TTF font on a fixed-width grid (for grass/weather)."""
    for i, ch in enumerate(text):
        if ch != " ":
            bbox = draw.textbbox((0, 0), ch, font=font)
            glyph_w = bbox[2] - bbox[0]
            glyph_x_offset = bbox[0]
            cx = x + i * cell_w + (cell_w - glyph_w) // 2 - glyph_x_offset
            draw.text((cx, y), ch, fill=fill, font=font)


def draw_weather(draw, weather=None, weather_frame=0):
    """Draw weather effects on the image."""
    if weather is None:
        return

    if weather == "clouds":
        font = ImageFont.truetype(FONT_PATH, 8)
        cloud_text = CLOUDS[weather_frame % len(CLOUDS)]
        full = (cloud_text * 2)[:28]
        # Shift clouds slowly
        offset = (weather_frame * 3) % 20
        draw_text_fixedwidth(draw, full, -offset, 0, font, 5)

    elif weather == "rain":
        pattern = RAIN_PATTERNS[weather_frame % len(RAIN_PATTERNS)]
        for dx, dy in pattern:
            # Rain drops: 2-3 pixel vertical lines
            drop_len = 2 + (dx % 2)
            for py in range(drop_len):
                if 0 <= dy + py < SCREEN_H - 10:
                    draw.point((dx, dy + py), fill=0)

    elif weather == "stars":
        pattern = STAR_PATTERNS[weather_frame % len(STAR_PATTERNS)]
        for sx, sy in pattern:
            draw.point((sx, sy), fill=0)
            # Some stars are brighter (cross pattern)
            if (sx + sy) % 3 == 0:
                for ddx, ddy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                    nx, ny = sx + ddx, sy + ddy
                    if 0 <= nx < SCREEN_W and 0 <= ny < SCREEN_H:
                        draw.point((nx, ny), fill=0)

    elif weather == "storm":
        # Rain + darker sky (inverted band at top)
        pattern = RAIN_PATTERNS[weather_frame % len(RAIN_PATTERNS)]
        for dx, dy in pattern:
            drop_len = 3
            for py in range(drop_len):
                if 0 <= dy + py < SCREEN_H - 10:
                    draw.point((dx, dy + py), fill=0)
        # Lightning flash on certain frames
        if weather_frame % 6 == 0:
            # Zig-zag lightning bolt
            lx = 15 + (weather_frame * 17) % 90
            for ly in range(2, 20):
                lx += random.choice([-1, 0, 1])
                lx = max(0, min(SCREEN_W - 1, lx))
                draw.point((lx, ly), fill=0)
                draw.point((lx + 1, ly), fill=0)


def render_face(face_lines, grass_line=None, weather=None, weather_frame=0):
    """Render a pig face as a 128x64 1-bit PIL Image.

    Uses the Adafruit GFX 5x7 bitmap font (same as M5Stack default).
    Black text on white background (matching Flipper LCD appearance).
    """
    img = Image.new("1", (SCREEN_W, SCREEN_H), 1)  # white background
    draw = ImageDraw.Draw(img)

    # Pig face at 2x scale: 12px per char wide, 14px tall
    scale = 2
    char_w = 6 * scale  # 12px
    line_spacing = 7 * scale + 2  # 16px

    base_width = 6
    face_pixel_w = base_width * char_w
    x_start = (SCREEN_W - face_pixel_w) // 2

    # Pig sits at bottom, grass below
    grass_y = SCREEN_H - 8
    face_h = 3 * line_spacing
    y_start = grass_y - face_h

    for i, line in enumerate(face_lines):
        y = y_start + i * line_spacing
        draw_bitmap_text(draw, line[:base_width], x_start, y, scale=scale)
        if len(line) > base_width:
            tail = line[base_width:]
            tail_x = x_start + base_width * char_w + 2
            tail_y = y + scale * 3
            draw_bitmap_text(draw, tail, tail_x, tail_y, scale=1)

    # Scrolling /\ grass at the bottom, like M5PORKCHOP original
    if grass_line is not None:
        draw_grass(draw, grass_line, grass_y)

    # Weather effects
    draw_weather(draw, weather, weather_frame)

    return img


def render_icon(face_lines, width, height):
    """Render a pig face as a WxH 1-bit image for icons using bitmap font."""
    img = Image.new("1", (width, height), 1)  # white background
    draw = ImageDraw.Draw(img)

    # Choose scale based on icon size
    scale = max(1, min(width // (6 * 6), height // (3 * 9)))
    char_w = 6 * scale
    char_h = 7 * scale
    line_spacing = char_h + scale

    base_width = 6
    face_pixel_w = base_width * char_w
    x_start = (width - face_pixel_w) // 2
    y_start = (height - len(face_lines) * line_spacing) // 2

    for i, line in enumerate(face_lines):
        y = y_start + i * line_spacing
        draw_bitmap_text(draw, line[:base_width], x_start, y, scale=scale)

    return img


# ── Frame saving ──────────────────────────────────────────────────────────

def save_frame_png(anim_dir, frame_num, img):
    """Save frame as PNG (source format)."""
    path = os.path.join(anim_dir, f"frame_{frame_num}.png")
    img.save(path)


def save_frame_bm(anim_dir, frame_num, img):
    """Save frame as .bm (packed format)."""
    path = os.path.join(anim_dir, f"frame_{frame_num}.bm")
    with open(path, "wb") as f:
        f.write(convert_bm(img))


# ── meta.txt / manifest.txt ──────────────────────────────────────────────

def write_meta(dirs, passive_frames, active_frames, frames_order,
               active_cycles=0, frame_rate=5, bubble_slots=None):
    """Write meta.txt for an animation to all given directories."""
    order_str = " ".join(str(f) for f in frames_order)
    content = (
        f"Filetype: Flipper Animation\n"
        f"Version: 1\n"
        f"\n"
        f"Width: 128\n"
        f"Height: 64\n"
        f"Passive frames: {passive_frames}\n"
        f"Active frames: {active_frames}\n"
        f"Frames order: {order_str}\n"
        f"Active cycles: {active_cycles}\n"
        f"Frame rate: {frame_rate}\n"
        f"Duration: 3600\n"
        f"Active cooldown: 0\n"
        f"\n"
        f"Bubble slots: {len(bubble_slots) if bubble_slots else 0}\n"
    )

    if bubble_slots:
        for i, slot in enumerate(bubble_slots):
            content += (
                f"\n"
                f"Slot: {i}\n"
                f"X: {slot['x']}\n"
                f"Y: {slot['y']}\n"
                f"Text: {slot['text']}\n"
                f"AlignH: {slot.get('alignH', 'Left')}\n"
                f"AlignV: {slot.get('alignV', 'Top')}\n"
                f"StartFrame: {slot['start']}\n"
                f"EndFrame: {slot['end']}\n"
            )

    if isinstance(dirs, str):
        dirs = [dirs]
    for d in dirs:
        with open(os.path.join(d, "meta.txt"), "w", newline="\n") as f:
            f.write(content)


def write_manifest(anims_dir, animation_names):
    """Write root manifest.txt."""
    content = (
        "Filetype: Flipper Animation Manifest\n"
        "Version: 1\n"
    )
    for name in animation_names:
        weight = 7 if "Idle" in name else (5 if "Happy" in name else 3)
        content += (
            f"\n"
            f"Name: {name}\n"
            f"Min butthurt: 0\n"
            f"Max butthurt: 14\n"
            f"Min level: 1\n"
            f"Max level: 30\n"
            f"Weight: {weight}\n"
        )

    with open(os.path.join(anims_dir, "manifest.txt"), "w", newline="\n") as f:
        f.write(content)


# ── Animation generators ─────────────────────────────────────────────────

def make_anim_dir(name):
    """Create animation directory in both source (compiled) and png (editable)."""
    src = os.path.join(SOURCE_DIR, "Anims", name)
    png = os.path.join(PNG_DIR, "Anims", name)
    os.makedirs(src, exist_ok=True)
    os.makedirs(png, exist_ok=True)
    return src, png


def save_frame(src_dir, png_dir, frame_num, img):
    """Save a frame as .bm (compiled) and .png (editable source)."""
    save_frame_bm(src_dir, frame_num, img)
    save_frame_png(png_dir, frame_num, img)


def generate_idle():
    """Idle: neutral face with clouds drifting by."""
    name = "Porkchop_Idle"
    src, png = make_anim_dir(name)

    n = 0
    for i in range(4):
        save_frame(src, png, n, render_face(
            FACES["neutral_r"], grass_line=i, weather="clouds", weather_frame=i))
        n += 1
    save_frame(src, png, n, render_face(
        FACES["blink_r"], grass_line=0, weather="clouds", weather_frame=4))
    n += 1
    for i in range(4):
        save_frame(src, png, n, render_face(
            FACES["neutral_l"], grass_line=i, weather="clouds", weather_frame=i + 4))
        n += 1
    save_frame(src, png, n, render_face(
        FACES["blink_l"], grass_line=0, weather="clouds", weather_frame=8))
    n += 1

    order = [
        0, 0, 0, 1, 1, 1, 2, 2, 2, 3, 3, 3,
        4,
        0, 0, 1, 1, 2, 2, 3, 3,
        5, 5, 5, 6, 6, 6, 7, 7, 7, 8, 8, 8,
        9,
        5, 5, 6, 6, 7, 7, 8, 8,
    ]

    write_meta([src, png], passive_frames=len(order), active_frames=0,
               frames_order=order, frame_rate=4)
    return name


def generate_happy():
    """Happy: clear sky, excited bursts."""
    name = "Porkchop_Happy"
    src, png = make_anim_dir(name)

    n = 0
    for i in range(4):
        save_frame(src, png, n, render_face(FACES["happy_r"], grass_line=i))
        n += 1
    for i in range(4):
        save_frame(src, png, n, render_face(FACES["happy_l"], grass_line=i))
        n += 1
    save_frame(src, png, n, render_face(FACES["excited_r"], grass_line=0))
    n += 1
    save_frame(src, png, n, render_face(FACES["excited_l"], grass_line=1))
    n += 1

    order = [
        0, 0, 1, 1, 2, 2, 3, 3,
        8, 8, 9, 9,
        4, 4, 5, 5, 6, 6, 7, 7,
        8, 8, 9, 9,
    ]

    bubbles = [
        {"x": 70, "y": 2, "text": "OINK!", "alignH": "Left", "alignV": "Top",
         "start": 8, "end": 11},
    ]

    write_meta([src, png], passive_frames=len(order), active_frames=0,
               frames_order=order, frame_rate=5, bubble_slots=bubbles)
    return name


def generate_hunting():
    """Hunting: clouds, sniff sequence."""
    name = "Porkchop_Hunting"
    src, png = make_anim_dir(name)

    n = 0
    for i in range(4):
        save_frame(src, png, n, render_face(
            FACES["hunting_r"], grass_line=i, weather="clouds", weather_frame=i))
        n += 1
    for i in range(3):
        face = ["sniff1_r", "sniff2_r", "sniff3_r"][i]
        save_frame(src, png, n, render_face(
            FACES[face], grass_line=i, weather="clouds", weather_frame=i + 4))
        n += 1
    for i in range(4):
        save_frame(src, png, n, render_face(
            FACES["hunting_l"], grass_line=i, weather="clouds", weather_frame=i + 7))
        n += 1

    order = [
        0, 0, 0, 1, 1, 2, 2, 3, 3,
        4, 5, 6, 4, 5, 6,
        0, 0, 1, 1,
        7, 7, 7, 8, 8, 9, 9, 10, 10,
    ]

    bubbles = [
        {"x": 68, "y": 5, "text": "*sniff*\\n*sniff*", "alignH": "Left",
         "alignV": "Top", "start": 9, "end": 14},
    ]

    write_meta([src, png], passive_frames=len(order), active_frames=0,
               frames_order=order, frame_rate=5, bubble_slots=bubbles)
    return name


def generate_sleepy():
    """Sleepy: slow, drowsy face."""
    name = "Porkchop_Sleepy"
    src, png = make_anim_dir(name)

    n = 0
    for i in range(4):
        save_frame(src, png, n, render_face(FACES["sleepy_r"], grass_line=i))
        n += 1
    for i in range(4):
        save_frame(src, png, n, render_face(FACES["sleepy_l"], grass_line=i))
        n += 1

    order = [
        0, 0, 0, 0, 1, 1, 1, 1, 2, 2, 2, 2, 3, 3, 3, 3,
        4, 4, 4, 4, 5, 5, 5, 5, 6, 6, 6, 6, 7, 7, 7, 7,
    ]

    bubbles = [
        {"x": 80, "y": 18, "text": "Zzz...", "alignH": "Left", "alignV": "Top",
         "start": 0, "end": 15},
    ]

    write_meta([src, png], passive_frames=len(order), active_frames=0,
               frames_order=order, frame_rate=3, bubble_slots=bubbles)
    return name


def generate_angry():
    """Angry: shaking face."""
    name = "Porkchop_Angry"
    src, png = make_anim_dir(name)

    n = 0
    for i in range(4):
        save_frame(src, png, n, render_face(FACES["angry_r"], grass_line=i))
        n += 1
    for i in range(4):
        save_frame(src, png, n, render_face(FACES["angry_l"], grass_line=i))
        n += 1

    order = [
        0, 1, 0, 2, 0, 3, 0, 1,
        4, 5, 4, 6, 4, 7, 4, 5,
    ]

    bubbles = [
        {"x": 68, "y": 20, "text": "GRRR!", "alignH": "Left", "alignV": "Top",
         "start": 0, "end": 7},
    ]

    write_meta([src, png], passive_frames=len(order), active_frames=0,
               frames_order=order, frame_rate=6, bubble_slots=bubbles)
    return name


def generate_sad():
    """Sad: slow, moping face."""
    name = "Porkchop_Sad"
    src, png = make_anim_dir(name)

    n = 0
    for i in range(4):
        save_frame(src, png, n, render_face(FACES["sad_r"], grass_line=i))
        n += 1
    for i in range(4):
        save_frame(src, png, n, render_face(FACES["sad_l"], grass_line=i))
        n += 1

    order = [
        0, 0, 0, 0, 1, 1, 1, 1, 2, 2, 2, 2, 3, 3, 3, 3,
        4, 4, 4, 4, 5, 5, 5, 5, 6, 6, 6, 6, 7, 7, 7, 7,
    ]

    write_meta([src, png], passive_frames=len(order), active_frames=0,
               frames_order=order, frame_rate=3)
    return name


# ── Icons ─────────────────────────────────────────────────────────────────

def generate_icons():
    """Generate Passport and Dolphin icons as both PNG (source) and .bmx (packed)."""
    passport_faces = {
        "passport_happy_46x49": (FACES["happy_r"], 46, 49),
        "passport_okay_46x49": (FACES["neutral_r"], 46, 49),
        "passport_bad_46x49": (FACES["sad_r"], 46, 49),
    }
    dolphin_faces = {
        "DolphinMafia_119x62": (FACES["hunting_r"], 119, 62),
        "DolphinSaved_92x58": (FACES["happy_r"], 92, 58),
    }

    for subdir, icons in [("Passport", passport_faces), ("Dolphin", dolphin_faces)]:
        src_dir = os.path.join(SOURCE_DIR, "Icons", subdir)
        png_dir = os.path.join(PNG_DIR, "Icons", subdir)
        os.makedirs(src_dir, exist_ok=True)
        os.makedirs(png_dir, exist_ok=True)

        for name, (face, w, h) in icons.items():
            img = render_icon(face, w, h)
            # Compiled .bmx for source/ (goes on SD card)
            with open(os.path.join(src_dir, f"{name}.bmx"), "wb") as f:
                f.write(convert_bmx(img))
            # Editable PNG for png/
            img.save(os.path.join(png_dir, f"{name}.png"))
            print(f"  {subdir}/{name}")


# ── Previews ──────────────────────────────────────────────────────────────

def generate_previews(animation_names):
    """Generate preview GIFs for each animation."""
    os.makedirs(PREVIEW_DIR, exist_ok=True)

    # (face, grass, weather, weather_frame) tuples
    def seq(face, grass, weather=None, wf=0):
        return (face, grass, weather, wf)

    anim_sequences = {
        "Porkchop_Idle": {
            "seq": [
                *[seq("neutral_r", i, "clouds", i) for i in range(4) for _ in range(3)],
                seq("blink_r", 0, "clouds", 4),
                *[seq("neutral_r", i, "clouds", i+4) for i in range(2) for _ in range(2)],
                *[seq("neutral_l", i, "clouds", i+6) for i in range(4) for _ in range(3)],
                seq("blink_l", 0, "clouds", 10),
                *[seq("neutral_l", i, "clouds", i+10) for i in range(2) for _ in range(2)],
            ],
            "fps": 4,
        },
        "Porkchop_Happy": {
            "seq": [
                *[seq("happy_r", i) for i in range(4) for _ in range(2)],
                seq("excited_r", 0), seq("excited_r", 0),
                seq("excited_l", 1), seq("excited_l", 1),
                *[seq("happy_l", i) for i in range(4) for _ in range(2)],
                seq("excited_r", 0), seq("excited_r", 0),
                seq("excited_l", 1), seq("excited_l", 1),
            ],
            "fps": 5,
        },
        "Porkchop_Hunting": {
            "seq": [
                *[seq("hunting_r", i, "clouds", i) for i in range(3) for _ in range(2)],
                seq("sniff1_r", 0, "clouds", 4),
                seq("sniff2_r", 0, "clouds", 5),
                seq("sniff3_r", 1, "clouds", 6),
                seq("sniff1_r", 0, "clouds", 7),
                seq("sniff2_r", 0, "clouds", 8),
                seq("sniff3_r", 1, "clouds", 9),
                *[seq("hunting_l", i, "clouds", i+10) for i in range(3) for _ in range(2)],
            ],
            "fps": 5,
        },
        "Porkchop_Angry": {
            "seq": [
                seq("angry_r", 0), seq("angry_r", 1), seq("angry_r", 0), seq("angry_r", 2),
                seq("angry_r", 0), seq("angry_r", 3), seq("angry_r", 0), seq("angry_r", 1),
                seq("angry_l", 0), seq("angry_l", 1), seq("angry_l", 0), seq("angry_l", 2),
                seq("angry_l", 0), seq("angry_l", 3), seq("angry_l", 0), seq("angry_l", 1),
            ],
            "fps": 6,
        },
        "Porkchop_Sleepy": {
            "seq": [
                *[seq("sleepy_r", i) for i in range(4) for _ in range(4)],
                *[seq("sleepy_l", i) for i in range(4) for _ in range(4)],
            ],
            "fps": 3,
        },
        "Porkchop_Sad": {
            "seq": [
                *[seq("sad_r", i) for i in range(4) for _ in range(4)],
                *[seq("sad_l", i) for i in range(4) for _ in range(4)],
            ],
            "fps": 3,
        },
    }

    preview_num = 1
    for name in animation_names:
        if name not in anim_sequences:
            continue
        anim = anim_sequences[name]
        frames = []
        for face_key, grass_idx, weather, wf in anim["seq"]:
            img = render_face(FACES[face_key], grass_line=grass_idx,
                              weather=weather, weather_frame=wf)
            scaled = img.resize((SCREEN_W * 4, SCREEN_H * 4), Image.NEAREST)
            frames.append(scaled.convert("P"))

        duration = 1000 // anim["fps"]
        gif_path = os.path.join(PREVIEW_DIR, f"{preview_num}.gif")
        frames[0].save(gif_path, save_all=True, append_images=frames[1:],
                       duration=duration, loop=0)
        print(f"  {preview_num}.gif: {name} ({len(frames)} frames)")
        preview_num += 1


# ── Pack metadata & downloads ─────────────────────────────────────────────

def write_meta_json():
    meta = {
        "name": "PORKCHOP",
        "author": "0ct0sec / pfefferle",
        "source_url": "https://github.com/0ct0sec/M5PORKCHOP",
        "description": "The PORKCHOP pig companion from M5PORKCHOP - "
                       "7 emotional states with blink, sniff, and grass animations"
    }
    path = os.path.join(PACK_DIR, "meta.json")
    with open(path, "w") as f:
        json.dump(meta, f, indent="\t")
        f.write("\n")


def generate_downloads():
    """Create .tar.gz and .zip archives of source/PORKCHOP/ (the SD card pack)."""
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)

    tar_path = os.path.join(DOWNLOAD_DIR, "porkchop.tar.gz")
    with tarfile.open(tar_path, "w:gz") as tar:
        tar.add(SOURCE_DIR, arcname=PACK_NAME)

    zip_path = os.path.join(DOWNLOAD_DIR, "porkchop.zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(SOURCE_DIR):
            for fn in files:
                full = os.path.join(root, fn)
                arcname = os.path.join(
                    PACK_NAME, os.path.relpath(full, SOURCE_DIR)
                )
                zf.write(full, arcname)


# ── Main ──────────────────────────────────────────────────────────────────

def main():
    # Clean generated output (not the script itself)
    for d in [SOURCE_DIR, PREVIEW_DIR, DOWNLOAD_DIR, PNG_DIR]:
        if os.path.exists(d):
            shutil.rmtree(d)

    src_anims = os.path.join(SOURCE_DIR, "Anims")
    os.makedirs(src_anims, exist_ok=True)

    print("Generating PORKCHOP Flipper Zero Asset Pack...\n")

    print("Animations:")
    names = []
    for gen_func in [generate_idle, generate_happy, generate_hunting,
                     generate_sleepy, generate_angry, generate_sad]:
        name = gen_func()
        names.append(name)
        print(f"  {name}")

    write_manifest(src_anims, names)
    # Also write manifest to PNG dir so it works with asset_packer.py
    png_anims = os.path.join(PNG_DIR, "Anims")
    os.makedirs(png_anims, exist_ok=True)
    write_manifest(png_anims, names)

    print("\nIcons:")
    generate_icons()

    print("\nPreviews:")
    generate_previews(names)

    write_meta_json()
    generate_downloads()

    # Stats
    total_frames = 0
    for name in names:
        d = os.path.join(src_anims, name)
        total_frames += len([f for f in os.listdir(d) if f.endswith(".bm")])

    print(f"\n{len(names)} animations, {total_frames} frames")
    print(f"Pack:      {PACK_DIR}/")
    print(f"PNG:       {PNG_DIR}/")


if __name__ == "__main__":
    main()
