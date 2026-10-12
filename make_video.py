#!/usr/bin/env python3
"""Generate a 2-minute animated video: a woman works out on the beach in the
morning, lifts weights, eats a healthy breakfast, then drives to work in a luxury car, with motivating music.

Usage: python3 make_video.py  ->  morning_routine.mp4
Requires: Pillow (with raqm for Arabic text), numpy, ffmpeg.
"""
import math
import os
import subprocess
import wave

import numpy as np
from PIL import Image, ImageDraw, ImageFont

W, H = 1280, 720
FPS = 24
DURATION = 120  # seconds
OUT = "morning_routine.mp4"
AUDIO = "soundtrack.wav"

FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
_fonts = {}


def font(size):
    if size not in _fonts:
        _fonts[size] = ImageFont.truetype(FONT, size, layout_engine=ImageFont.Layout.RAQM)
    return _fonts[size]


# Scene timeline (start, end) in seconds
SCENES = [
    ("title", 0, 6),
    ("jog", 6, 32),
    ("weights", 32, 62),
    ("breakfast", 62, 90),
    ("commute", 90, 114),
    ("end", 114, 120),
]

SKIN = (196, 136, 100)
HAIR = (45, 28, 20)


def lerp(a, b, t):
    return a + (b - a) * t


def lerp_col(c1, c2, t):
    return tuple(int(lerp(a, b, t)) for a, b in zip(c1, c2))


def gradient(top, bottom, h=H):
    arr = np.zeros((h, W, 3), dtype=np.uint8)
    for i, (a, b) in enumerate(zip(top, bottom)):
        arr[:, :, i] = np.linspace(a, b, h, dtype=np.float32)[:, None]
    return Image.fromarray(arr)


def text(d, xy, s, size, fill=(255, 255, 255), shadow=True, anchor="mm"):
    f = font(size)
    if shadow:
        d.text((xy[0] + 3, xy[1] + 3), s, font=f, fill=(0, 0, 0), anchor=anchor)
    d.text(xy, s, font=f, fill=fill, anchor=anchor)


def caption(d, s, t_in):
    """Top caption pill that fades/slides in (kept clear of the action below)."""
    a = min(1.0, t_in / 0.8)
    y = int(lerp(-40, 130, a))
    half = d.textlength(s, font=font(34)) / 2 + 36
    d.rounded_rectangle((W / 2 - half, y - 34, W / 2 + half, y + 34), 22, fill=(0, 0, 0))
    text(d, (W / 2, y), s, 34, shadow=False)


def clock(d, minutes):
    h, m = divmod(int(minutes), 60)
    digits = str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩")
    s = f"{h}:{m:02d}".translate(digits)
    d.rounded_rectangle((30, 26, 200, 86), 16, fill=(255, 255, 255))
    d.ellipse((44, 40, 76, 72), outline=(40, 40, 40), width=3)
    ang = (minutes % 60) / 60 * 2 * math.pi
    d.line((60, 56, 60 + 11 * math.sin(ang), 56 - 11 * math.cos(ang)), fill=(40, 40, 40), width=2)
    hang = ((minutes / 60) % 12) / 12 * 2 * math.pi
    d.line((60, 56, 60 + 7 * math.sin(hang), 56 - 7 * math.cos(hang)), fill=(200, 60, 60), width=3)
    d.text((140, 56), s, font=font(30), fill=(40, 40, 40), anchor="mm")


# ---------------------------------------------------------------- character

def limb(d, start, a1, l1, a2, l2, col, w):
    """Two-segment limb; angles in degrees from straight down, + = screen right."""
    x0, y0 = start
    r1, r2 = math.radians(a1), math.radians(a2)
    x1, y1 = x0 + l1 * math.sin(r1), y0 + l1 * math.cos(r1)
    x2, y2 = x1 + l2 * math.sin(r2), y1 + l2 * math.cos(r2)
    d.line((x0, y0, x1, y1), fill=col, width=w)
    d.line((x1, y1, x2, y2), fill=col, width=w)
    for x, y in ((x0, y0), (x1, y1)):
        d.ellipse((x - w / 2, y - w / 2, x + w / 2, y + w / 2), fill=col)
    return (x2, y2)


def woman(d, x, ground, pose, outfit, s=1.0, face=1, ponytail_swing=0.0):
    """Draw the woman. pose = dict of joint angles; ground = y of feet."""
    top_col, bottom_col = outfit["top"], outfit["bottom"]
    shoe = outfit.get("shoe", (250, 250, 250))
    thigh, shin = 62 * s, 60 * s
    torso = 92 * s
    crouch = pose.get("crouch", 0)  # 0..1 for squats/sitting
    hip_y = ground - (thigh + shin) * math.cos(math.radians(pose.get("knee_bend", 0) * 0.5)) - pose.get("bob", 0)
    hip_y += crouch * 50 * s
    hip = (x, hip_y)
    lean = pose.get("lean", 0)
    sh = (x + torso * math.sin(math.radians(lean)), hip_y - torso * math.cos(math.radians(lean)))

    # back limbs (darker)
    dark = lambda c: tuple(int(v * 0.75) for v in c)
    f2 = limb(d, hip, pose["lthigh"], thigh, pose["lshin"], shin, dark(bottom_col), int(24 * s))
    d.ellipse((f2[0] - 14 * s + 8 * face * s, f2[1] - 8 * s, f2[0] + 14 * s + 8 * face * s, f2[1] + 6 * s), fill=dark(shoe))
    limb(d, (sh[0], sh[1] + 8 * s), pose["larm"], 48 * s, pose["lfore"], 46 * s, dark(SKIN), int(15 * s))
    if pose.get("dumbbells"):
        draw_dumbbell(d, limb_end((sh[0], sh[1] + 8 * s), pose["larm"], 48 * s, pose["lfore"], 46 * s), s, dark)

    # torso (as a thick polygon)
    tw = 22 * s
    d.polygon([(hip[0] - tw, hip[1]), (hip[0] + tw, hip[1]), (sh[0] + tw + 2, sh[1]), (sh[0] - tw - 2, sh[1])], fill=top_col)
    d.ellipse((sh[0] - tw - 4, sh[1] - 10 * s, sh[0] + tw + 4, sh[1] + 14 * s), fill=top_col)
    if outfit.get("skirt"):
        d.polygon([(hip[0] - tw - 2, hip[1] - 10 * s), (hip[0] + tw + 2, hip[1] - 10 * s),
                   (hip[0] + tw + 14 * s, hip[1] + 52 * s), (hip[0] - tw - 14 * s, hip[1] + 52 * s)], fill=bottom_col)

    # front leg
    f1 = limb(d, hip, pose["rthigh"], thigh, pose["rshin"], shin, bottom_col, int(24 * s))
    d.ellipse((f1[0] - 14 * s + 8 * face * s, f1[1] - 8 * s, f1[0] + 14 * s + 8 * face * s, f1[1] + 6 * s), fill=shoe)

    # neck + head
    hx, hy = sh[0] + 4 * face * s, sh[1] - 34 * s
    d.line((sh[0], sh[1], hx, hy + 10 * s), fill=SKIN, width=int(12 * s))
    # ponytail
    px = hx - face * 24 * s
    swing = ponytail_swing * 14 * s
    d.polygon([(px, hy - 14 * s), (px - face * 30 * s, hy + 4 * s + swing), (px - face * 22 * s, hy + 30 * s + swing),
               (px + face * 2 * s, hy + 2 * s)], fill=HAIR)
    d.ellipse((hx - 24 * s, hy - 26 * s, hx + 24 * s, hy + 24 * s), fill=SKIN)
    d.chord((hx - 26 * s, hy - 30 * s, hx + 26 * s, hy + 14 * s), 180, 360, fill=HAIR)
    d.pieslice((hx - 26 * s - face * 6 * s, hy - 30 * s, hx + 26 * s - face * 6 * s, hy + 22 * s),
               90 if face > 0 else 270, 270 if face > 0 else 450, fill=HAIR)
    # face details
    ex = hx + face * 12 * s
    d.ellipse((ex - 3 * s, hy - 4 * s, ex + 3 * s, hy + 2 * s), fill=(30, 20, 20))
    d.arc((hx + face * 2 * s, hy + 4 * s, hx + face * 18 * s + (0 if face > 0 else 16 * s), hy + 14 * s), 20, 160,
          fill=(150, 60, 60), width=max(1, int(2 * s)))
    if outfit.get("headband"):
        d.line((hx - 25 * s, hy - 12 * s, hx + 25 * s, hy - 12 * s), fill=outfit["headband"], width=int(6 * s))

    # front arm
    arm_start = (sh[0], sh[1] + 8 * s)
    end = limb(d, arm_start, pose["rarm"], 48 * s, pose["rfore"], 46 * s, SKIN, int(15 * s))
    # short sleeve
    sl = limb_end(arm_start, pose["rarm"], 20 * s, pose["rarm"], 0)
    d.line((arm_start[0], arm_start[1], sl[0], sl[1]), fill=top_col, width=int(19 * s))
    if pose.get("dumbbells"):
        draw_dumbbell(d, end, s, lambda c: c)
    if outfit.get("bag"):
        bx, by = end
        d.arc((bx - 18 * s, by - 18 * s, bx + 18 * s, by + 18 * s), 180, 360, fill=(90, 50, 30), width=int(4 * s))
        d.rounded_rectangle((bx - 26 * s, by, bx + 26 * s, by + 36 * s), int(6 * s), fill=outfit["bag"])
    return end, (hx, hy)


def limb_end(start, a1, l1, a2, l2):
    r1, r2 = math.radians(a1), math.radians(a2)
    return (start[0] + l1 * math.sin(r1) + l2 * math.sin(r2), start[1] + l1 * math.cos(r1) + l2 * math.cos(r2))


def draw_dumbbell(d, p, s, shade):
    x, y = p
    d.line((x - 22 * s, y, x + 22 * s, y), fill=shade((70, 70, 70)), width=int(6 * s))
    for dx in (-22, 22):
        d.rounded_rectangle((x + dx * s - 7 * s, y - 15 * s, x + dx * s + 7 * s, y + 15 * s), int(3 * s), fill=shade((40, 40, 50)))


def run_pose(phase):
    sw = math.sin(phase)
    return dict(lthigh=-35 * sw, lshin=-35 * sw - 40 - 25 * max(0, -sw),
                rthigh=35 * sw, rshin=35 * sw - 40 - 25 * max(0, sw),
                larm=40 * sw, lfore=40 * sw + 100, rarm=-40 * sw, rfore=-40 * sw + 100,
                lean=8, bob=abs(math.cos(phase)) * 8, knee_bend=30)


def walk_pose(phase):
    sw = math.sin(phase)
    return dict(lthigh=-22 * sw, lshin=-22 * sw - 8 * max(0, -sw),
                rthigh=22 * sw, rshin=22 * sw - 8 * max(0, sw),
                larm=18 * sw, lfore=18 * sw + 15, rarm=-6 * sw, rfore=-6 * sw + 5,
                lean=2, bob=abs(math.cos(phase)) * 3)


# ---------------------------------------------------------------- backgrounds

BEACH_SKY = gradient((255, 170, 120), (255, 226, 170), 400)


def beach_bg(t, scroll=0.0):
    img = Image.new("RGB", (W, H))
    img.paste(BEACH_SKY, (0, 0))
    d = ImageDraw.Draw(img)
    # rising sun
    sy = 330 - min(t, 40) * 3
    for r, c in ((110, (255, 214, 150)), (80, (255, 200, 110)), (60, (255, 160, 70))):
        d.ellipse((900 - r, sy - r, 900 + r, sy + r), fill=c)
    # clouds
    for i, (cx, cy) in enumerate(((200, 90), (600, 140), (1100, 70))):
        cx = (cx - scroll * 0.1 + t * 6) % (W + 300) - 150
        for dx, dy, r in ((0, 0, 30), (30, -12, 36), (64, 0, 30)):
            d.ellipse((cx + dx - r, cy + dy - r, cx + dx + r, cy + dy + r), fill=(255, 240, 230))
    # sea
    d.rectangle((0, 330, W, 470), fill=(40, 130, 170))
    d.rectangle((0, 330, W, 345), fill=(70, 160, 195))
    for k in range(6):
        y = 355 + k * 20
        off = (t * 30 * (1 + k * 0.2) + scroll * (0.3 + k * 0.1)) % 80
        for x in range(-80, W + 80, 80):
            d.arc((x - off, y - 6, x - off + 40, y + 6), 200, 340, fill=(180, 225, 240), width=2)
    # shoreline foam (animated)
    foam_y = 470 + 8 * math.sin(t * 1.2)
    d.rectangle((0, 470, W, H), fill=(238, 214, 165))
    d.polygon([(0, foam_y)] + [(x, foam_y + 6 * math.sin(x / 50 + t * 2)) for x in range(0, W + 40, 40)] + [(W, 470), (0, 470)],
              fill=(250, 250, 245))
    # palm trees (scroll)
    for base in (150, 820, 1450):
        px = (base - scroll) % (W + 400) - 200
        palm(d, px, 600, t)
    return img, d


def palm(d, x, y, t):
    for i in range(10):
        d.ellipse((x + i * 2 - 10, y - i * 24 - 12, x + i * 2 + 10, y - i * 24 + 12), fill=(140, 95, 55))
    top = (x + 20, y - 240)
    for a in (-160, -120, -60, -20, 200):
        r = math.radians(a + 4 * math.sin(t * 1.5))
        tip = (top[0] + 110 * math.cos(r), top[1] + 110 * math.sin(r) + 40)
        d.line((top, ((top[0] + tip[0]) / 2, top[1] - 15), tip), fill=(40, 130, 60), width=12, joint="curve")
    d.ellipse((top[0] - 10, top[1] - 6, top[0] + 10, top[1] + 14), fill=(110, 70, 40))


KITCHEN = gradient((250, 240, 225), (235, 220, 200))


def kitchen_bg(t):
    img = KITCHEN.copy()
    d = ImageDraw.Draw(img)
    # window with morning light
    d.rectangle((760, 90, 1120, 330), fill=(255, 255, 255))
    d.rectangle((775, 105, 1105, 315), fill=(170, 215, 240))
    d.ellipse((990, 130, 1060, 200), fill=(255, 220, 120))
    d.line((940, 105, 940, 315), fill=(255, 255, 255), width=8)
    d.line((775, 210, 1105, 210), fill=(255, 255, 255), width=8)
    # plant
    d.rectangle((1150, 270, 1200, 330), fill=(190, 100, 70))
    for a in range(-60, 61, 30):
        r = math.radians(a - 90 + 3 * math.sin(t + a))
        d.line((1175, 272, 1175 + 60 * math.cos(r), 272 + 60 * math.sin(r)), fill=(60, 150, 70), width=8)
    # shelf
    d.rectangle((120, 150, 520, 165), fill=(160, 110, 70))
    for i, c in enumerate(((220, 80, 60), (240, 190, 60), (90, 160, 90), (120, 120, 200))):
        d.rounded_rectangle((150 + i * 90, 95, 200 + i * 90, 150), 8, fill=c)
    # floor
    d.rectangle((0, 560, W, H), fill=(190, 150, 110))
    return img, d


def city_bg(t, scroll):
    img = gradient((150, 200, 240), (220, 235, 250))
    d = ImageDraw.Draw(img)
    d.ellipse((1080, 60, 1160, 140), fill=(255, 235, 150))
    # far buildings
    rng = np.random.default_rng(3)
    widths = rng.integers(90, 160, 30)
    heights = rng.integers(180, 380, 30)
    cols = [(120, 140, 170), (140, 150, 180), (110, 125, 155)]
    x = -(scroll * 0.4) % 3500 - 3500
    for rep in range(3):
        for i, (w, h) in enumerate(zip(widths, heights)):
            if -200 < x < W + 200:
                d.rectangle((x, 560 - h, x + w, 560), fill=cols[i % 3])
                for wy in range(560 - h + 20, 540, 34):
                    for wx in range(int(x) + 14, int(x + w) - 20, 30):
                        d.rectangle((wx, wy, wx + 14, wy + 18), fill=(210, 225, 245))
            x += w + 20
    # sidewalk + road
    d.rectangle((0, 560, W, 640), fill=(200, 200, 205))
    for k in range(0, W + 120, 120):
        kx = k - scroll % 120
        d.line((kx, 560, kx - 30, 640), fill=(170, 170, 175), width=3)
    d.rectangle((0, 640, W, H), fill=(70, 70, 78))
    for k in range(0, W + 200, 200):
        kx = k - (scroll * 1.0) % 200
        d.rectangle((kx, 676, kx + 100, 684), fill=(240, 240, 240))
    # trees along sidewalk
    for base in range(0, 3000, 500):
        tx = (base - scroll) % 3000 - 300
        if -100 < tx < W + 100:
            d.rectangle((tx - 8, 470, tx + 8, 565), fill=(110, 75, 45))
            d.ellipse((tx - 55, 380, tx + 55, 490), fill=(70, 160, 80))
    return img, d


def office(d, x):
    d.rectangle((x, 120, x + 420, 562), fill=(60, 90, 130))
    for wy in range(150, 440, 50):
        for wx in range(x + 25, x + 400, 70):
            d.rectangle((wx, wy, wx + 45, wy + 32), fill=(170, 210, 240))
    d.rectangle((x + 160, 440, x + 260, 562), fill=(200, 230, 245))
    d.line((x + 210, 440, x + 210, 562), fill=(60, 90, 130), width=4)
    d.rectangle((x + 110, 135, x + 310, 175), fill=(250, 250, 250))
    d.text((x + 210, 155), "المكتب", font=font(26), fill=(60, 90, 130), anchor="mm")


# ---------------------------------------------------------------- scenes

SPORT = dict(top=(240, 90, 110), bottom=(40, 50, 90), shoe=(250, 250, 250), headband=(255, 255, 255))
WORK = dict(top=(30, 60, 100), bottom=(60, 60, 70), shoe=(40, 30, 30), bag=(170, 90, 60))


def scene_title(t):
    img = gradient(lerp_col((40, 30, 80), (255, 150, 110), min(1, t / 6)), (255, 210, 160))
    d = ImageDraw.Draw(img)
    sy = 600 - t * 30
    d.ellipse((W / 2 - 90, sy - 90, W / 2 + 90, sy + 90), fill=(255, 190, 90))
    d.rectangle((0, 540, W, H), fill=(40, 110, 150))
    a = min(1, t / 1.5)
    text(d, (W / 2, 250 - 30 * (1 - a)), "صباح صحي ونشيط", 84)
    if t > 1.5:
        text(d, (W / 2, 350), "تمرين على البحر • فطور صحي • إلى الدوام", 36)
    return img


def scene_jog(t):
    scroll = t * 220
    img, d = beach_bg(t + 6, scroll)
    phase = t * 9
    pose = run_pose(phase)
    woman(d, 520, 610, pose, SPORT, s=1.15, ponytail_swing=math.sin(phase * 2))
    # footprints/dust
    for k in range(4):
        dx = ((t * 220 + k * 70) % 280)
        d.ellipse((470 - dx, 612, 480 - dx, 618), fill=(215, 190, 145))
    clock(d, 6 * 60 + t * 1.2)
    if t < 13:
        caption(d, "٦:٠٠ صباحاً — جري على شاطئ البحر", t)
    else:
        caption(d, "هواء البحر المنعش يبدأ اليوم بطاقة", t - 13)
    return img


def scene_weights(t):
    img, d = beach_bg(t + 32, 0)
    # yoga mat
    d.polygon([(380, 600), (860, 600), (900, 640), (340, 640)], fill=(90, 170, 160))
    clock(d, 6 * 60 + 32 + t * 1.0)
    if t < 15:
        # squats holding dumbbells at shoulders
        c = (1 - math.cos(t * 2 * math.pi / 2.5)) / 2
        pose = dict(lthigh=-60 * c, lshin=40 * c, rthigh=-55 * c, rshin=45 * c, crouch=c * 0.9,
                    larm=-20, lfore=-160, rarm=-25, rfore=-165, lean=20 * c, dumbbells=True)
        woman(d, 640, 618, pose, SPORT, s=1.2, face=1)
        reps = int(t / 2.5) + (1 if c > 0.9 else 0)
        caption(d, "تمارين السكوات بالأوزان", t)
        label = f"سكوات: {min(reps, 6)} / ٦"
    else:
        tt = t - 15
        # shoulder press
        c = (1 - math.cos(tt * 2 * math.pi / 2.2)) / 2
        pose = dict(lthigh=-6, lshin=-6, rthigh=6, rshin=6,
                    larm=lerp(-80, -170, c), lfore=lerp(-175, -180, c), rarm=lerp(-75, -168, c), rfore=lerp(-178, -182, c),
                    dumbbells=True)
        pose["larm"], pose["rarm"] = pose["larm"], pose["rarm"]
        woman(d, 640, 618, pose, SPORT, s=1.2, face=1)
        reps = int(tt / 2.2) + (1 if c > 0.9 else 0)
        caption(d, "رفع الأوزان فوق الرأس — قوة ولياقة", tt)
        label = f"تكرار: {min(reps, 6)} / ٦"
    d.rounded_rectangle((W - 290, 30, W - 30, 90), 16, fill=(255, 255, 255))
    d.text((W - 160, 60), label, font=font(28), fill=(200, 60, 80), anchor="mm")
    return img


def plate(d, cx, cy, r):
    d.ellipse((cx - r, cy - r * 0.35, cx + r, cy + r * 0.35), fill=(250, 250, 250), outline=(210, 210, 210), width=2)


def scene_breakfast(t):
    img, d = kitchen_bg(t)
    clock(d, 7 * 60 + 30 + t * 0.8)
    # chair back
    d.rounded_rectangle((540, 300, 700, 470), 18, fill=(150, 100, 60))
    # woman seated behind table: legs hidden, draw from hips up
    eat = (1 - math.cos(t * 2 * math.pi / 3.5)) / 2  # spoon to mouth cycle
    pose = dict(lthigh=-80, lshin=0, rthigh=-80, rshin=0, crouch=0,
                larm=25, lfore=-60,
                rarm=lerp(30, 5, eat), rfore=lerp(-60, -170, eat), lean=0)
    hand, head = woman(d, 620, 560, pose, dict(top=(250, 200, 80), bottom=(80, 100, 140), shoe=(250, 250, 250)), s=1.15)
    # spoon in hand
    d.line((hand[0], hand[1], hand[0] + 18, hand[1] - 14), fill=(190, 190, 200), width=5)
    d.ellipse((hand[0] + 14, hand[1] - 22, hand[0] + 28, hand[1] - 10), fill=(190, 190, 200))
    # table
    d.rectangle((280, 470, 1000, 500), fill=(170, 120, 75))
    d.rectangle((300, 500, 330, 640), fill=(140, 95, 55))
    d.rectangle((950, 500, 980, 640), fill=(140, 95, 55))
    d.polygon([(260, 470), (1020, 470), (980, 430), (300, 430)], fill=(200, 150, 100))
    # oats bowl with berries
    d.chord((520, 400, 640, 470), 0, 180, fill=(250, 250, 250))
    d.ellipse((520, 418, 640, 446), fill=(230, 205, 160))
    for bx, c in ((545, (120, 40, 120)), (565, (220, 40, 60)), (590, (120, 40, 120)), (612, (250, 200, 60))):
        d.ellipse((bx - 7, 422, bx + 7, 436), fill=c)
    # avocado toast plate
    plate(d, 760, 448, 80)
    d.rounded_rectangle((715, 425, 805, 455), 8, fill=(215, 160, 90))
    d.ellipse((722, 427, 798, 450), fill=(140, 190, 80))
    # boiled egg
    d.ellipse((815, 425, 845, 455), fill=(255, 255, 255), outline=(220, 220, 220))
    d.ellipse((822, 432, 838, 448), fill=(255, 190, 40))
    # orange juice + water
    d.rectangle((390, 380, 430, 452), fill=(255, 165, 40), outline=(220, 220, 220), width=2)
    d.rectangle((440, 395, 472, 452), fill=(200, 230, 250), outline=(220, 220, 220), width=2)
    # fruit bowl
    for fx, fy, c in ((880, 420, (230, 60, 50)), (910, 410, (250, 200, 40)), (935, 425, (255, 140, 30))):
        d.ellipse((fx - 18, fy - 18, fx + 18, fy + 18), fill=c)
    # labels
    if t > 4:
        for (lx, ly, s) in ((580, 385, "شوفان وتوت"), (760, 395, "توست أفوكادو"), (830, 470, "بيض"),
                            (420, 360, "عصير برتقال"), (910, 380, "فواكه")):
            text(d, (lx, ly - 10), s, 20, fill=(60, 40, 30), shadow=False)
    if t < 14:
        caption(d, "فطور صحي بعد التمرين", t)
    else:
        caption(d, "بروتين، ألياف، وفيتامينات لطاقة طول اليوم", t - 14)
    return img


def car(d, x, y, wheel, driver=False):
    """Luxury sports sedan; (x, y) = front-left of body bottom line."""
    body = (20, 20, 28)
    d.polygon([(x, y), (x + 360, y), (x + 372, y - 40), (x + 330, y - 62), (x + 250, y - 70),
               (x + 200, y - 112), (x + 110, y - 114), (x + 60, y - 72), (x + 8, y - 58), (x - 6, y - 30)], fill=body)
    # windows
    d.polygon([(x + 120, y - 106), (x + 152, y - 106), (x + 152, y - 74), (x + 76, y - 74)], fill=(120, 150, 180))
    d.polygon([(x + 162, y - 106), (x + 196, y - 106), (x + 236, y - 74), (x + 162, y - 74)], fill=(120, 150, 180))
    if driver:
        d.ellipse((x + 168, y - 104, x + 194, y - 76), fill=SKIN)
        d.chord((x + 166, y - 108, x + 196, y - 84), 180, 360, fill=HAIR)
        d.polygon([(x + 168, y - 98), (x + 152, y - 90), (x + 158, y - 78), (x + 170, y - 88)], fill=HAIR)
    # chrome line, lights, gold accent
    d.line((x + 10, y - 34, x + 360, y - 34), fill=(200, 200, 210), width=3)
    d.ellipse((x + 346, y - 50, x + 372, y - 38), fill=(255, 250, 210))
    d.rectangle((x - 6, y - 50, x + 6, y - 38), fill=(220, 30, 40))
    d.line((x + 162, y - 72, x + 162, y - 8), fill=(60, 60, 70), width=2)
    d.rectangle((x + 196, y - 56, x + 214, y - 52), fill=(210, 170, 60))
    for wx in (x + 70, x + 290):
        d.ellipse((wx - 36, y - 26, wx + 36, y + 46), fill=(15, 15, 15))
        d.ellipse((wx - 22, y - 12, wx + 22, y + 32), fill=(200, 200, 210))
        for k in range(5):
            a = wheel + k * 2 * math.pi / 5
            d.line((wx, y + 10, wx + 20 * math.cos(a), y + 10 + 20 * math.sin(a)), fill=(120, 120, 130), width=4)
        d.ellipse((wx - 5, y + 5, wx + 5, y + 15), fill=(210, 170, 60))


def scene_commute(t):
    if t < 5:  # walk to the parked car
        img, d = city_bg(t, 0)
        car(d, 560, 640, 0)
        x = lerp(220, 700, t / 4.2)
        if t < 4.2:
            woman(d, x, 640, walk_pose(t * 6), WORK, s=1.0, face=1)
        caption(d, "٨:١٥ — إلى الدوام بسيارتها الفخمة", t)
    elif t < 19:  # driving through the city
        tt = t - 5
        speed = min(1, tt / 2) * 900
        scroll = 900 * max(0, tt - 1) + 450 * min(tt, 1) ** 2 if tt > 1 else 450 * tt ** 2
        img, d = city_bg(t, scroll)
        bounce = 2 * math.sin(t * 20)
        car(d, 460, 650 + bounce, scroll / 36, driver=True)
        for k in range(6):  # speed lines
            ly = 560 + k * 15
            lx = (k * 230 - scroll * 2) % (W + 200) - 100
            d.line((lx, ly, lx + 80, ly), fill=(255, 255, 255), width=2)
        caption(d, "قيادة بثقة وموسيقى محفزة" if tt < 8 else "جاهزة ليوم عمل ناجح", tt if tt < 8 else tt - 8)
    else:  # arrive at the office and step out
        tt = t - 19
        img, d = city_bg(t, 0)
        office(d, 760)
        car(d, 240, 650, 0, driver=tt < 1)
        if tt >= 1:
            x = lerp(560, 970, min(1, (tt - 1) / 2.5))
            pose = walk_pose(tt * 6) if tt < 3.5 else dict(lthigh=-3, lshin=-3, rthigh=3, rshin=3, larm=10, lfore=10,
                                                          rarm=-150 + 20 * math.sin(t * 8), rfore=-170, lean=0)
            woman(d, x, 640, pose, WORK, s=1.0, face=1)
        caption(d, "وصلت الدوام بنشاط وتركيز", tt)
    clock(d, 8 * 60 + 15 + t * 0.6)
    return img


def scene_end(t):
    img = gradient((255, 160, 120), (120, 80, 160))
    d = ImageDraw.Draw(img)
    a = min(1, t / 1.2)
    text(d, (W / 2, 290), "يوم جديد... بداية صحية", 72)
    if t > 1.2:
        text(d, (W / 2, 390), "رياضة  +  أكل صحي  =  يوم ناجح", 40)
    return img


RENDER = {"title": scene_title, "jog": scene_jog, "weights": scene_weights,
          "breakfast": scene_breakfast, "commute": scene_commute, "end": scene_end}


def frame_at(t):
    for name, s, e in SCENES:
        if s <= t < e:
            img = RENDER[name](t - s)
            # fade in/out at scene boundaries
            fade = min(1.0, (t - s) / 0.5, (e - t) / 0.5)
            if fade < 1:
                img = Image.blend(Image.new("RGB", (W, H)), img, max(0.0, fade))
            return img
    return Image.new("RGB", (W, H))


# ---------------------------------------------------------------- audio

def make_audio(path):
    sr = 44100
    n = sr * DURATION
    t = np.arange(n) / sr
    rng = np.random.default_rng(1)
    # ocean waves: low-passed noise with slow swell, only during beach scenes
    noise = rng.standard_normal(n)
    kernel = np.ones(60) / 60
    waves = np.convolve(noise, kernel, mode="same")
    swell = 0.5 + 0.5 * np.sin(2 * np.pi * t / 7.0)
    beach_env = np.clip((62 - t) / 2, 0, 1) * np.clip((t - 4) / 2, 0, 1)
    out = waves * swell * beach_env * 1.4
    out *= 0.35
    # motivating electronic track, 124 BPM
    bpm = 124
    beat = 60 / bpm
    nbeats = int(DURATION / beat)
    music = np.zeros(n)

    def add(start, sig):
        i0 = int(start * sr)
        if i0 >= n:
            return
        sig = sig[:n - i0]
        music[i0:i0 + len(sig)] += sig

    kt = np.arange(int(sr * 0.35)) / sr
    kick = np.sin(2 * np.pi * (45 + 110 * np.exp(-kt * 30)) * kt) * np.exp(-kt * 9)
    ht = np.arange(int(sr * 0.05)) / sr
    hat = np.diff(rng.standard_normal(len(ht) + 1)) * np.exp(-ht * 80) * 0.25
    ct = np.arange(int(sr * 0.2)) / sr
    clap = rng.standard_normal(len(ct)) * np.exp(-ct * 25) * 0.35
    # chord progression (Am - F - C - G), one bar each
    prog = [(220.0, [0, 3, 7]), (174.61, [0, 4, 7]), (261.63, [0, 4, 7]), (196.0, [0, 4, 7])]
    st = np.arange(int(sr * beat / 2)) / sr
    for b in range(nbeats):
        tb = b * beat
        intro = tb < 6  # sparse intro during the title
        add(tb, kick * (0.5 if intro else 0.9))
        if not intro:
            add(tb + beat / 2, hat)
            if b % 2 == 1:
                add(tb, clap)
        root, chord = prog[(b // 4) % 4]
        # pulsing saw-ish bass on 8ths
        for h in range(2):
            f = root / 2
            saw = sum(np.sin(2 * np.pi * f * k * st) / k for k in range(1, 6))
            add(tb + h * beat / 2, 0.16 * saw * np.exp(-st * 6))
        # arpeggio lead on 16ths (after intro)
        if not intro:
            for q in range(4):
                semis = chord[(b * 4 + q) % 3] + 12 * ((b * 4 + q) // 3 % 2)
                f = root * 2 ** (semis / 12)
                at = np.arange(int(sr * beat / 4)) / sr
                sq = np.sign(np.sin(2 * np.pi * f * at)) * 0.5 + np.sin(2 * np.pi * f * at)
                add(tb + q * beat / 4, 0.05 * sq * np.exp(-at * 14))
    out += music
    fade = np.clip(t / 2, 0, 1) * np.clip((DURATION - t) / 3, 0, 1)
    out *= fade
    out = out / np.max(np.abs(out)) * 0.8
    pcm = (out * 32767).astype(np.int16)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())


def main():
    make_audio(AUDIO)
    proc = subprocess.Popen(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
         "-r", str(FPS), "-i", "-", "-i", AUDIO, "-c:v", "libx264", "-preset", "medium", "-crf", "22",
         "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", "-shortest", "-movflags", "+faststart", OUT],
        stdin=subprocess.PIPE)
    total = FPS * DURATION
    for i in range(total):
        proc.stdin.write(frame_at(i / FPS).tobytes())
        if i % (FPS * 10) == 0:
            print(f"{i // FPS}s / {DURATION}s", flush=True)
    proc.stdin.close()
    proc.wait()
    os.remove(AUDIO)
    print("done ->", OUT)


if __name__ == "__main__":
    main()
