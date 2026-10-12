#!/usr/bin/env python3
"""Render the 2-minute commercial «قبل الشمس» following ad_director_treatment.md.

Cinematic animated version: golden-hour silhouettes, camera moves, colour
grade, letterbox, Arabic voice-over subtitles and a cue-matched score.

Usage: python3 make_ad.py  ->  before_the_sun_ad.mp4
"""
import math
import os
import subprocess
import wave

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

import make_video as mv

# Reuse the character/backgrounds from make_video, without its captions/clock.
mv.caption = lambda *a, **k: None
mv.clock = lambda *a, **k: None

W, H, FPS, DUR = 1280, 720, 24, 120
BAR = 92  # letterbox bar height (≈2.39:1)
BPM = 124
BEAT = 60 / BPM
OUT = "before_the_sun_ad.mp4"
AUDIO = "ad_score.wav"
HORIZON = 330

font = mv.font
lerp = mv.lerp
SPORT, WORK = mv.SPORT, mv.WORK
SIL = (14, 10, 16)


def ease(x):
    x = min(1.0, max(0.0, x))
    return x * x * (3 - 2 * x)


# ---------------------------------------------------------------- precomputed layers

def vgrad(h, stops):
    """Vertical gradient W x h from list of (pos 0..1, rgb)."""
    ys = np.linspace(0, 1, h)
    arr = np.zeros((h, W, 3), np.float32)
    for c in range(3):
        arr[:, :, c] = np.interp(ys, [p for p, _ in stops], [col[c] for _, col in stops])[:, None]
    return Image.fromarray(arr.astype(np.uint8))


GOLD_SKY = vgrad(HORIZON, [(0, (52, 38, 92)), (0.45, (190, 90, 90)), (0.8, (255, 150, 70)), (1, (255, 200, 120))])
GOLD_SEA = vgrad(140, [(0, (150, 80, 70)), (1, (55, 35, 55))])
GOLD_SAND = vgrad(H - 470, [(0, (110, 70, 55)), (1, (38, 26, 30))])
DAWN_SKY = vgrad(H, [(0, (12, 20, 52)), (0.6, (60, 80, 140)), (0.85, (190, 140, 160)), (1, (230, 170, 150))])


def make_glow(r, col):
    size = r * 2
    yy, xx = np.mgrid[0:size, 0:size]
    d = np.sqrt((xx - r) ** 2 + (yy - r) ** 2) / r
    a = np.clip(1 - d, 0, 1) ** 2.2
    img = np.zeros((size, size, 4), np.uint8)
    img[:, :, :3] = col
    img[:, :, 3] = (a * 255).astype(np.uint8)
    return Image.fromarray(img, "RGBA")


SUN_GLOW = make_glow(420, (255, 190, 110))
WARM_GLOW = make_glow(300, (255, 230, 180))

_yy, _xx = np.mgrid[0:H, 0:W]
_r = np.sqrt(((_xx - W / 2) / (W / 2)) ** 2 + ((_yy - H / 2) / (H / 2)) ** 2)
VIGNETTE = np.clip(1 - 0.38 * _r ** 2.2, 0.35, 1)[:, :, None].astype(np.float32)
_rng = np.random.default_rng(7)
GRAIN = [_rng.normal(0, 5, (H, W, 1)).astype(np.float32) for _ in range(6)]

GRADES = {  # (gain rgb, lift rgb)
    "dawn": ((0.85, 0.93, 1.15), (0, 4, 16)),
    "gold": ((1.10, 1.0, 0.86), (10, 2, 0)),
    "warm": ((1.06, 1.02, 0.92), (8, 4, 0)),
    "lux": ((1.0, 1.0, 1.04), (0, 0, 6)),
    "night": ((1, 1, 1), (0, 0, 0)),
}


def paste_glow(img, glow, cx, cy):
    img.paste(glow.convert("RGB"), (int(cx - glow.width / 2), int(cy - glow.height / 2)),
              glow.getchannel("A"))


# ---------------------------------------------------------------- drawing helpers

def silhouette(img, draw_fn, rim=(255, 190, 110), fill=SIL):
    """Draw a figure via draw_fn(ImageDraw) as a dark silhouette with a glowing rim."""
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    res = draw_fn(ImageDraw.Draw(layer))
    a = layer.getchannel("A")
    box = a.getbbox()
    if not box:
        return res
    pad = 14
    box = (max(0, box[0] - pad), max(0, box[1] - pad), min(W, box[2] + pad), min(H, box[3] + pad))
    ac = a.crop(box)
    glow = ac.filter(ImageFilter.MaxFilter(5)).filter(ImageFilter.GaussianBlur(4))
    img.paste(Image.new("RGB", ac.size, rim), box[:2], glow)
    img.paste(Image.new("RGB", ac.size, fill), box[:2], ac)
    return res


def palm_sil(d, x, y, t, s=1.0):
    for i in range(12):
        d.ellipse((x + i * 3 * s - 11 * s, y - i * 24 * s - 12 * s, x + i * 3 * s + 11 * s, y - i * 24 * s + 12 * s), fill=SIL)
    top = (x + 34 * s, y - 280 * s)
    for a in (-170, -135, -95, -55, -15, 195):
        r = math.radians(a + 5 * math.sin(t * 1.3 + a))
        tip = (top[0] + 140 * s * math.cos(r), top[1] + 140 * s * math.sin(r) + 55 * s)
        mid = ((top[0] + tip[0]) / 2, top[1] - 22 * s)
        d.line((top, mid, tip), fill=SIL, width=int(14 * s), joint="curve")


def gold_beach(t, scroll=0.0, sun_x=760, sun_r=70, sun_y=HORIZON, palms=True):
    img = Image.new("RGB", (W, H))
    img.paste(GOLD_SKY, (0, 0))
    paste_glow(img, SUN_GLOW, sun_x, sun_y)
    d = ImageDraw.Draw(img)
    d.ellipse((sun_x - sun_r, sun_y - sun_r, sun_x + sun_r, sun_y + sun_r), fill=(255, 236, 190))
    img.paste(GOLD_SEA, (0, HORIZON))
    d = ImageDraw.Draw(img)
    # sun path shimmering on the water
    for y in range(HORIZON + 3, 470, 5):
        k = (y - HORIZON) / 140
        half = (sun_r * 0.8 + 140 * k) * (0.6 + 0.4 * math.sin(t * 3 + y * 0.7))
        off = 30 * math.sin(t * 2 + y * 0.31) * k
        d.line((sun_x - half + off, y, sun_x + half + off, y), fill=(255, 200, 130), width=2)
    # distant wave lines
    for k in range(5):
        y = HORIZON + 20 + k * 24
        o = (t * 25 + scroll * (0.2 + k * 0.08)) % 120
        for x in range(-120, W + 120, 120):
            d.arc((x - o, y - 4, x - o + 60, y + 4), 200, 340, fill=(220, 140, 110), width=2)
    img.paste(GOLD_SAND, (0, 470))
    d = ImageDraw.Draw(img)
    fy = 474 + 7 * math.sin(t * 1.1)
    d.polygon([(0, 470)] + [(x, fy + 5 * math.sin(x / 45 + t * 2)) for x in range(0, W + 40, 40)] + [(W, 470)],
              fill=(255, 205, 150))
    # wet-sand reflection of the sun
    d.ellipse((sun_x - 160, 486, sun_x + 160, 520), fill=(150, 95, 70))
    if palms:
        for base, sc in ((120, 1.1), (1380, 0.95), (1900, 1.2)):
            px = (base - scroll * 1.1) % (W + 700) - 300
            palm_sil(d, px, 640, t, sc)
    return img


def cam(img, zoom=1.0, cx=W / 2, cy=H / 2, shake=0.0, t=0.0):
    if shake:
        cx += shake * math.sin(t * 53)
        cy += shake * math.cos(t * 47)
    if zoom <= 1.0001 and not shake:
        return img
    zoom = max(zoom, 1.0 + (0.02 if shake else 0))
    w, h = W / zoom, H / zoom
    x0 = min(max(cx - w / 2, 0), W - w)
    y0 = min(max(cy - h / 2, 0), H - h)
    return img.resize((W, H), Image.BICUBIC, box=(x0, y0, x0 + w, y0 + h))


def run_pose(phase):
    return mv.run_pose(phase)


def squat_pose(c):
    return dict(lthigh=-60 * c, lshin=40 * c, rthigh=-55 * c, rshin=45 * c, crouch=c * 0.9,
                larm=-20, lfore=-160, rarm=-25, rfore=-165, lean=20 * c, dumbbells=True)


def press_pose(c):
    return dict(lthigh=-6, lshin=-6, rthigh=6, rshin=6, larm=lerp(-80, -170, c), lfore=lerp(-175, -180, c),
                rarm=lerp(-75, -168, c), rfore=lerp(-178, -182, c), dumbbells=True)


def lunge_pose(c):
    return dict(rthigh=lerp(8, 72, c), rshin=lerp(4, 0, c), lthigh=lerp(-8, -18, c), lshin=lerp(-4, -88, c),
                crouch=c * 0.85, larm=0, lfore=0, rarm=4, rfore=4, dumbbells=True)


def cycle(t, period):
    return (1 - math.cos(t * 2 * math.pi / period)) / 2


# ---------------------------------------------------------------- shots

def s_phone(t, dur):
    img = Image.new("RGB", (W, H), (4, 6, 14))
    paste_glow(img, WARM_GLOW.resize((900, 900)), W / 2, H / 2)
    img = Image.blend(Image.new("RGB", (W, H), (4, 6, 14)), img, 0.18)
    d = ImageDraw.Draw(img)
    on = t < 3.2
    d.rounded_rectangle((W / 2 - 150, 90, W / 2 + 150, 640), 42, fill=(20, 20, 26), outline=(70, 70, 80), width=4)
    scr = (W / 2 - 136, 104, W / 2 + 136, 626)
    d.rounded_rectangle(scr, 34, fill=(18, 28, 60) if on else (6, 8, 14))
    if on:
        d.text((W / 2, 250), "5:30", font=font(96), fill=(255, 255, 255), anchor="mm")
        d.text((W / 2, 330), "المنبه — يوم جديد", font=font(26), fill=(190, 200, 230), anchor="mm")
        k = ease((t - 2.2) / 0.8)
        d.rounded_rectangle((W / 2 - 110, 520, W / 2 + 110, 580), 30, fill=(50, 60, 100))
        kx = lerp(W / 2 - 80, W / 2 + 80, k)
        d.ellipse((kx - 26, 524, kx + 26, 576), fill=(255, 180, 90))
        d.text((W / 2 + 20 * (1 - k), 550), "إيقاف" if k < 0.5 else "", font=font(22), fill=(200, 200, 220), anchor="mm")
    return cam(img, 1 + 0.08 * t / dur, W / 2, 300)


def s_window(t, dur):
    img = DAWN_SKY.copy()
    d = ImageDraw.Draw(img)
    # room walls framing a big window
    d.rectangle((0, 0, W, 90), fill=(10, 14, 30))
    d.rectangle((0, 0, 230, H), fill=(10, 14, 30))
    d.rectangle((W - 230, 0, W, H), fill=(10, 14, 30))
    d.rectangle((0, 600, W, H), fill=(8, 10, 22))
    d.rectangle((230, 470, W - 230, 600), fill=(30, 40, 70))  # sea through window
    paste_glow(img, SUN_GLOW.resize((500, 500)), 820, 480)
    d = ImageDraw.Draw(img)
    d.rectangle((230, 470, W - 230, 600), fill=(40, 52, 88))
    for x in (640,):
        d.line((x, 90, x, 600), fill=(10, 14, 30), width=10)
    tie = math.sin(t * 2.4)
    pose = dict(lthigh=-3, lshin=-3, rthigh=3, rshin=3, larm=-150 + 8 * tie, lfore=-215, rarm=-140 - 8 * tie, rfore=-205, lean=0)
    silhouette(img, lambda dd: mv.woman(dd, 560, 640, pose, SPORT, s=1.35, face=1), rim=(150, 170, 230))
    return cam(img, 1 + 0.14 * ease(t / dur), 560, 380)


def s_aerial(t, dur):
    img = Image.new("RGB", (W, H))
    img.paste(vgrad(300, [(0, (70, 50, 100)), (0.6, (230, 120, 80)), (1, (255, 200, 120))]), (0, 0))
    sy = 300 - t * 10
    paste_glow(img, SUN_GLOW, 640, sy)
    d = ImageDraw.Draw(img)
    d.ellipse((640 - 60, sy - 60, 640 + 60, sy + 60), fill=(255, 236, 190))
    img.paste(vgrad(H - 300, [(0, (160, 90, 75)), (1, (30, 45, 70))]), (0, 300))
    d = ImageDraw.Draw(img)
    # perspective wave lines rushing towards camera
    for k in range(26):
        p = (k + (t * 2.2) % 1) / 26
        y = 300 + (H - 300) * p ** 2.2
        wdt = 2 + int(5 * p)
        col = (int(lerp(255, 160, p)), int(lerp(190, 170, p)), int(lerp(140, 190, p)))
        for x in range(-200, W + 200, int(90 + 220 * p)):
            xx = x + ((k * 37) % 90) - 45
            d.arc((xx, y - 6 * p, xx + 60 + 160 * p, y + 6 * p), 200, 340, fill=col, width=wdt)
    # shoreline arriving at the bottom with a tiny runner
    shore = H - 30 * ease((t - 2) / 3)
    d.rectangle((0, shore, W, H), fill=(200, 150, 110))
    return cam(img, 1.05 + 0.05 * t / dur, 640, 360)


def runner_frame(t, scroll, sun_x=760):
    img = gold_beach(t, scroll, sun_x=sun_x)
    phase = t * 9.5
    silhouette(img, lambda d: mv.woman(d, 520, 612, run_pose(phase), SPORT, s=1.2, ponytail_swing=math.sin(phase * 2)))
    d = ImageDraw.Draw(img)
    for k in range(5):  # kicked-up water droplets
        dx = (t * 260 + k * 60) % 300
        d.ellipse((470 - dx, 600 - (k % 3) * 6, 477 - dx, 607 - (k % 3) * 6), fill=(255, 220, 170))
    return img


def s_track(t, dur):
    return cam(runner_frame(t + 3, t * 230), 1.05, 560, 420)


def s_run_cu(t, dur):
    img = runner_frame(t + 10, (t + 7) * 230, sun_x=600)
    return cam(img, 2.1, 560, 400 + 6 * math.sin(t * 19))


def s_big_sun(t, dur):
    img = gold_beach(t + 15, 0, sun_x=640, sun_r=230, palms=False)
    x = lerp(180, 1100, t / dur)
    phase = t * 9.5
    silhouette(img, lambda d: mv.woman(d, x, 610, run_pose(phase), SPORT, s=1.3, ponytail_swing=math.sin(phase * 2)))
    return img


def s_stretch(t, dur):
    img = gold_beach(t + 20, 0)
    d = ImageDraw.Draw(img)
    d.polygon([(380, 600), (860, 600), (900, 636), (340, 636)], fill=(40, 30, 40))
    c = cycle(t, 3.4)
    pose = dict(lthigh=-12, lshin=-12, rthigh=12, rshin=12, lean=lerp(5, 70, c),
                larm=lerp(-170, 40, c), lfore=lerp(-175, 30, c), rarm=lerp(-165, 45, c), rfore=lerp(-170, 35, c))
    silhouette(img, lambda dd: mv.woman(dd, 600, 612, pose, SPORT, s=1.2))
    z = 1 + 0.25 * ease(t / dur)
    # riser: brighten towards the drop
    out = cam(img, z, 620, 470)
    if t > dur - 2:
        out = Image.blend(out, Image.new("RGB", (W, H), (255, 220, 170)), 0.25 * (t - dur + 2) / 2)
    return out


BLUR_BEACH = gold_beach(30, 0).filter(ImageFilter.GaussianBlur(14))


def s_dumbbell(t, dur):
    img = BLUR_BEACH.copy()
    d = ImageDraw.Draw(img)
    cy = 400 - 40 * ease(t / 0.6)
    d.rectangle((370, cy - 18, 910, cy + 18), fill=(70, 70, 76))
    d.line((370, cy - 12, 910, cy - 12), fill=(150, 150, 160), width=4)
    for x in (300, 900):
        d.rounded_rectangle((x, cy - 120, x + 80, cy + 120), 18, fill=(28, 28, 34))
        d.line((x + 10, cy - 105, x + 10, cy + 105), fill=(255, 190, 110), width=4)  # rim light
    d.rounded_rectangle((560, cy - 52, 720, cy + 52), 40, fill=(120, 80, 60))  # gripping fist
    for k in range(4):
        d.line((585 + k * 36, cy - 40, 585 + k * 36, cy + 10), fill=(90, 60, 45), width=3)
    rng = np.random.default_rng(int(t * 100) // 3)
    for k in range(40):  # sand falling
        sx = 320 + (k * 53) % 600
        sy = cy + 20 + ((t * 300 + k * 37) % 300)
        d.ellipse((sx, sy, sx + 4, sy + 4), fill=(230, 190, 140))
    out = cam(img, 1.08, 640, 380, shake=6 if t < 0.5 else 0, t=t)
    if t < 0.18:
        out = Image.blend(out, Image.new("RGB", (W, H), (255, 245, 230)), 1 - t / 0.18)
    return out


def weight_frame(t, kind, sun_x=640):
    img = gold_beach(t + 30, 0, sun_x=sun_x)
    d = ImageDraw.Draw(img)
    d.polygon([(380, 604), (860, 604), (900, 640), (340, 640)], fill=(40, 30, 40))
    period = 4 * BEAT
    c = cycle(t, period)
    pose = {"squat": squat_pose, "press": press_pose, "lunge": lunge_pose}[kind](c)
    silhouette(img, lambda dd: mv.woman(dd, 640, 620, pose, SPORT, s=1.25))
    return img, c


def s_squat(t, dur):
    img, c = weight_frame(t, "squat", sun_x=760)
    return cam(img, 1.45, 640, 470)


def s_press(t, dur):
    img, c = weight_frame(t, "press", sun_x=650)
    return cam(img, 1.7 - 0.1 * t / dur, 650, 330)


def s_quickcuts(t, dur):
    k = int(t / (2 * BEAT))
    if k % 2 == 0:
        img, _ = weight_frame(t, "press", 650)
        out = cam(img, 2.3, 660, 300)
    else:
        img, _ = weight_frame(t, "squat", 760)
        out = cam(img, 1.25 + 0.1 * (k % 3), 640, 470)
    if (t % (2 * BEAT)) < 0.06:
        out = Image.blend(out, Image.new("RGB", (W, H), (255, 240, 220)), 0.5)
    return out


def s_lunge(t, dur):
    img = gold_beach(t + 40, 260 * math.sin(t * 0.6), sun_x=int(640 + 260 * math.sin(t * 0.6)))
    d = ImageDraw.Draw(img)
    c = cycle(t, 4 * BEAT)
    silhouette(img, lambda dd: mv.woman(dd, 600, 620, lunge_pose(c), SPORT, s=1.25))
    return cam(img, 1.3, 640 - 60 * math.sin(t * 0.6), 450)


def s_water(t, dur):
    img = gold_beach(t + 45, 0, sun_x=820)
    drink = ease(t / 1.2) * (1 - ease((t - 3) / 1))
    pose = dict(lthigh=-3, lshin=-3, rthigh=3, rshin=3, larm=8, lfore=8,
                rarm=lerp(10, 45, drink), rfore=lerp(10, 165, drink), lean=-5 * drink)

    def draw(d):
        hand, head = mv.woman(d, 560, 620, pose, SPORT, s=1.25)
        d.rounded_rectangle((hand[0] - 9, hand[1] - 34, hand[0] + 9, hand[1] + 10), 6, fill=(255, 255, 255))
    silhouette(img, draw)
    return cam(img, 1.25 + 0.1 * t / dur, 620, 430)


# ---- breakfast

WOOD = None


def wood():
    global WOOD
    if WOOD is None:
        arr = np.zeros((H, W, 3), np.float32)
        base = np.array([150, 102, 66], np.float32)
        ys = np.arange(H)[:, None]
        xs = np.arange(W)[None, :]
        grain = 14 * np.sin(ys / 9 + 3 * np.sin(xs / 140)) + 8 * np.sin(ys / 2.7)
        for c in range(3):
            arr[:, :, c] = base[c] + grain * (1 - c * 0.25)
        for k in range(1, 5):  # plank seams
            arr[k * 150 - 2:k * 150 + 2] *= 0.55
        WOOD = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
    return WOOD.copy()


def shadowed_circle(d, cx, cy, r, fill, outline=None):
    d.ellipse((cx - r + 8, cy - r + 10, cx + r + 8, cy + r + 10), fill=(90, 60, 40))
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=fill, outline=outline, width=3)


def oats_bowl(d, cx, cy, r, berries=True, honey=0.0):
    shadowed_circle(d, cx, cy, r, (250, 250, 248))
    d.ellipse((cx - r * 0.82, cy - r * 0.82, cx + r * 0.82, cy + r * 0.82), fill=(226, 200, 150))
    rng = np.random.default_rng(5)
    for _ in range(int(r * 1.4)):
        a, rr = rng.uniform(0, 2 * math.pi), r * 0.78 * math.sqrt(rng.uniform())
        x, y = cx + rr * math.cos(a), cy + rr * math.sin(a)
        d.ellipse((x - r * 0.04, y - r * 0.025, x + r * 0.04, y + r * 0.025), fill=(240, 220, 175))
    if honey:
        hr = r * 0.5 * honey
        d.ellipse((cx - hr, cy - hr * 0.8, cx + hr, cy + hr * 0.8), fill=(235, 165, 40))
    if berries:
        for k, (dx, dy, col) in enumerate(((0.3, -0.2, (70, 30, 90)), (0.45, 0.1, (200, 20, 50)), (0.1, 0.35, (70, 30, 90)),
                                           (-0.35, 0.25, (200, 20, 50)), (-0.2, -0.4, (70, 30, 90)), (0.5, -0.45, (240, 190, 60)))):
            br = r * 0.11
            d.ellipse((cx + dx * r - br, cy + dy * r - br, cx + dx * r + br, cy + dy * r + br), fill=col)
            d.ellipse((cx + dx * r - br * 0.3, cy + dy * r - br * 0.6, cx + dx * r + br * 0.1, cy + dy * r - br * 0.2),
                      fill=(255, 255, 255))


def s_flatlay(t, dur):
    img = wood()
    d = ImageDraw.Draw(img)
    items = []

    def oats(dd, k):
        oats_bowl(dd, 470, 330, 150)

    def toast(dd, k):
        shadowed_circle(dd, 830, 300, 145, (250, 250, 248))
        dd.rounded_rectangle((740, 220, 920, 380), 30, fill=(205, 145, 75))
        dd.rounded_rectangle((752, 232, 908, 368), 24, fill=(230, 180, 110))
        for i in range(6):
            dd.ellipse((760 + i * 24, 245 + (i % 2) * 15, 800 + i * 24, 355 - (i % 2) * 15), fill=(130, 180, 70),
                       outline=(90, 140, 50), width=3)

    def eggs(dd, k):
        for ex, ey in ((1030, 470), (1110, 510)):
            dd.ellipse((ex - 46 + 6, ey - 36 + 8, ex + 46 + 6, ey + 36 + 8), fill=(90, 60, 40))
            dd.ellipse((ex - 46, ey - 36, ex + 46, ey + 36), fill=(255, 255, 252))
            dd.ellipse((ex - 22, ey - 20, ex + 22, ey + 20), fill=(255, 185, 30))

    def juice(dd, k):
        shadowed_circle(dd, 1060, 230, 70, (255, 160, 30), outline=(255, 230, 200))
        dd.ellipse((1030, 200, 1060, 225), fill=(255, 210, 140))
        for ox, oy in ((230, 560), (330, 620)):
            dd.ellipse((ox - 55, oy - 55, ox + 55, oy + 55), fill=(250, 140, 20))
            dd.ellipse((ox - 45, oy - 45, ox + 45, oy + 45), fill=(255, 190, 70))
            for a in range(0, 360, 45):
                r = math.radians(a)
                dd.line((ox, oy, ox + 40 * math.cos(r), oy + 40 * math.sin(r)), fill=(255, 230, 160), width=3)

    def greens(dd, k):
        for sx, sy in ((620, 560), (690, 600), (760, 570)):
            dd.ellipse((sx - 26, sy - 30, sx + 26, sy + 30), fill=(210, 30, 50))
            dd.polygon([(sx - 14, sy - 28), (sx, sy - 44), (sx + 14, sy - 28)], fill=(60, 150, 60))
        for lx, ly in ((180, 200), (210, 240), (150, 250)):
            dd.ellipse((lx - 28, ly - 14, lx + 28, ly + 14), fill=(80, 170, 90))

    seq = [oats, toast, eggs, juice, greens]
    for i, fn in enumerate(seq):
        if t > i * 0.55:
            fn(d, i)
    paste_glow(img, WARM_GLOW, 1100, 120)
    return cam(img, 1.04 + 0.06 * t / dur, 640, 380)


def s_honey(t, dur):
    img = wood()
    d = ImageDraw.Draw(img)
    oats_bowl(d, 640, 430, 420, honey=ease(t / dur) * 0.9)
    # honey stream
    wv = 10 + 3 * math.sin(t * 12)
    d.line((640 + 6 * math.sin(t * 5), -10, 640, 430), fill=(240, 170, 40), width=int(wv))
    d.line((636 + 6 * math.sin(t * 5), -10, 636, 430), fill=(255, 220, 120), width=3)
    paste_glow(img, WARM_GLOW, 900, 150)
    return cam(img, 1.0 + 0.08 * t / dur, 640, 380)


def s_kitchen(t, dur):
    orig = mv.text
    mv.text = lambda *a, **k: None  # hide food labels
    try:
        img = mv.scene_breakfast(t + 8)
    finally:
        mv.text = orig
    paste_glow(img, WARM_GLOW, 1025, 165)
    if t < 5:
        return cam(img, 1.15, 600 + 30 * t / 5, 420)
    return cam(img, 1.7, 640, 360)


def s_watch(t, dur):
    if t < 3:
        img = vgrad(H, [(0, (245, 232, 215)), (1, (215, 195, 175))])
        d = ImageDraw.Draw(img)
        d.polygon([(0, 520), (0, 300), (W, 200), (W, 420)], fill=mv.SKIN)  # forearm
        d.polygon([(560, 270), (720, 240), (740, 470), (580, 500)], fill=(150, 110, 60))  # strap
        cx, cy, r = 650, 365, 120
        d.ellipse((cx - r - 12, cy - r - 12, cx + r + 12, cy + r + 12), fill=(200, 160, 70))
        d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(250, 248, 240))
        for k in range(12):
            a = math.radians(k * 30)
            d.line((cx + (r - 18) * math.sin(a), cy - (r - 18) * math.cos(a), cx + (r - 6) * math.sin(a), cy - (r - 6) * math.cos(a)),
                   fill=(60, 50, 40), width=4)
        for ang, ln, w, col in ((8 * 30 + 15, 60, 8, (40, 40, 40)), (90 + 0.5 * t, 90, 5, (40, 40, 40)),
                                (int(t / BEAT) * 6, 100, 2, (200, 60, 50))):
            a = math.radians(ang)
            d.line((cx, cy, cx + ln * math.sin(a), cy - ln * math.cos(a)), fill=col, width=w)
        d.ellipse((cx - 8, cy - 8, cx + 8, cy + 8), fill=(200, 160, 70))
        return cam(img, 1.1 + 0.05 * t / 3, cx, cy)
    tt = t - 3
    img = vgrad(H, [(0, (235, 225, 210)), (1, (200, 185, 165))])
    d = ImageDraw.Draw(img)
    d.ellipse((440, 60, 840, 700), fill=(200, 160, 70))
    d.ellipse((456, 76, 824, 684), fill=(222, 228, 232))
    mv.woman(d, 640, 640, dict(lthigh=-3, lshin=-3, rthigh=3, rshin=3, larm=12, lfore=-30, rarm=-10, rfore=-150, lean=0),
             WORK, s=1.4, face=1)
    return cam(img, 1.05 + 0.08 * tt / 3, 640, 360)


def s_walk_car(t, dur):
    return cam(mv.scene_commute(t * 1.0), 1.12, 560, 480)


def s_engine(t, dur):
    img = Image.new("RGB", (W, H), (8, 8, 12))
    d = ImageDraw.Draw(img)
    press = t > 1.0
    glow = 0.5 + 0.5 * math.sin(t * 4) if not press else 1
    ring = (int(200 * glow + 30), 40, 40) if not press else (255, 255, 255)
    paste_glow(img, make_glow(170, ring if press else (200, 40, 40)), 640, 360)
    d = ImageDraw.Draw(img)
    d.ellipse((640 - 120, 360 - 120, 640 + 120, 360 + 120), fill=(40, 40, 46), outline=(180, 180, 190), width=8)
    d.ellipse((640 - 100, 360 - 100, 640 + 100, 360 + 100), outline=ring, width=5)
    d.text((640, 340), "ENGINE", font=font(30), fill=ring, anchor="mm")
    d.text((640, 385), "START", font=font(30), fill=ring, anchor="mm")
    if press:  # gauge sweep
        k = ease((t - 1) / 1.2) * (1 - ease((t - 2.2) / 0.8) * 0.6)
        for gx in (260, 1020):
            d.arc((gx - 140, 220, gx + 140, 500), 135, 405, fill=(60, 60, 70), width=10)
            d.arc((gx - 140, 220, gx + 140, 500), 135, 135 + 270 * k, fill=(255, 190, 90), width=10)
            a = math.radians(135 + 270 * k)
            d.line((gx, 360, gx + 120 * math.cos(a), 360 + 120 * math.sin(a)), fill=(255, 80, 60), width=5)
    return cam(img, 1.12 if t < 1 else 1.12 - 0.04 * (t - 1), 640, 360, shake=3 if 1 < t < 1.4 else 0, t=t)


def s_drive(t, dur):
    img = mv.scene_commute(7 + t)
    if 5 <= t < 8:
        return cam(img, 2.2, 640, 560)
    return cam(img, 1.08, 640 + 20 * math.sin(t * 0.5), 450)


def s_arrive(t, dur):
    img = mv.scene_commute(19 + t)
    return cam(img, 1.15 + 0.1 * ease((t - 1) / 4), 760, 470)


def s_turn(t, dur):
    img, d = mv.city_bg(110 + t, 0)
    mv.office(d, 760)
    pose = dict(lthigh=-4, lshin=-4, rthigh=4, rshin=4, larm=6, lfore=6, rarm=-4, rfore=-4, lean=0)
    mv.woman(d, 930, 640, pose, WORK, s=1.0, face=-1)
    return cam(img, 1.8 + 0.2 * ease(t / dur), 930, 450)


def s_end(t, dur):
    img = Image.new("RGB", (W, H), (0, 0, 0))
    k = ease(t / 1.5)
    d = ImageDraw.Draw(img)
    gold = (int(230 * k), int(185 * k), int(100 * k))
    d.text((W / 2, 320), "اللي يبدأ قبل الشمس…", font=font(62), fill=gold, anchor="mm")
    if t > 1.0:
        k2 = ease((t - 1.0) / 1.2)
        d.text((W / 2, 410), "ما يلحقه أحد.", font=font(62), fill=(int(255 * k2), int(255 * k2), int(255 * k2)), anchor="mm")
    if t > 3.5:
        a = ease((t - 3.5) / 1)
        d.line((W / 2 - 120 * a, 470, W / 2 + 120 * a, 470), fill=(230, 185, 100), width=2)
    return img


# (start, end, renderer, grade, dip-to-black at start)
SHOTS = [
    (0, 4, s_phone, "night", False),
    (4, 12, s_window, "dawn", False),
    (12, 17, s_aerial, "gold", True),
    (17, 24, s_track, "gold", False),
    (24, 28, s_run_cu, "gold", False),
    (28, 33, s_big_sun, "gold", False),
    (33, 40, s_stretch, "gold", False),
    (40, 42, s_dumbbell, "gold", False),
    (42, 47, s_squat, "gold", False),
    (47, 51, s_press, "gold", False),
    (51, 55, s_quickcuts, "gold", False),
    (55, 60, s_lunge, "gold", False),
    (60, 65, s_water, "gold", False),
    (65, 69, s_flatlay, "warm", True),
    (69, 72, s_honey, "warm", False),
    (72, 82, s_kitchen, "warm", False),
    (82, 88, s_watch, "warm", False),
    (88, 92, s_walk_car, "lux", True),
    (92, 95, s_engine, "night", False),
    (95, 105, s_drive, "lux", False),
    (105, 110, s_arrive, "lux", False),
    (110, 114, s_turn, "lux", False),
    (114, 120, s_end, "night", True),
]

VO = [
    (5, 9.5, "كل يوم… فيه لحظة تختارين فيها."),
    (13, 17.5, "تقومين… أو تأجلين."),
    (22, 27, "البحر ما ينتظر أحد… والشمس بعد."),
    (42.5, 47.5, "القوة مو صدفة… القوة قرار يتكرر."),
    (58, 63, "وكل رفعة… تقرّبك من نفسك."),
    (70, 75, "وكل لقمة… طاقة لليوم كله."),
    (89, 94.5, "يوم ثاني ينتظرك… وأنتِ جاهزة له."),
]


def finish(img, t, grade):
    arr = np.asarray(img, dtype=np.float32)
    gain, lift = GRADES[grade]
    arr = arr * np.array(gain, np.float32) + np.array(lift, np.float32)
    arr = arr * VIGNETTE + GRAIN[int(t * FPS) % len(GRAIN)]
    img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
    d = ImageDraw.Draw(img)
    d.rectangle((0, 0, W, BAR), fill=(0, 0, 0))
    d.rectangle((0, H - BAR, W, H), fill=(0, 0, 0))
    for s, e, line in VO:
        if s <= t < e:
            a = min(1, (t - s) / 0.5, (e - t) / 0.5)
            v = int(255 * a)
            d.text((W / 2, H - BAR / 2), line, font=font(34), fill=(v, v, v), anchor="mm")
    return img


def frame_at(t):
    for s, e, fn, grade, dip in SHOTS:
        if s <= t < e:
            img = finish(fn(t - s, e - s), t, grade)
            k = 1.0
            if dip:
                k = min(k, (t - s) / 0.4)
            nxt = [x for x in SHOTS if x[0] == e]
            if (nxt and nxt[0][4]) or e == DUR:
                k = min(k, (e - t) / 0.4)
            if k < 1:
                img = Image.blend(Image.new("RGB", (W, H)), img, max(0.0, k))
            return img
    return Image.new("RGB", (W, H))


# ---------------------------------------------------------------- score

SR = 44100


def make_score(path):
    n = SR * DUR
    tt = np.arange(n) / SR
    rng = np.random.default_rng(11)
    out = np.zeros(n)

    def add(start, sig, gain=1.0):
        i0 = int(start * SR)
        if i0 >= n or i0 < 0:
            return
        sig = sig[:n - i0]
        out[i0:i0 + len(sig)] += gain * sig

    def env_t(sec):
        return np.arange(int(SR * sec)) / SR

    kt = env_t(0.4)
    kick = np.sin(2 * np.pi * (42 + 120 * np.exp(-kt * 28)) * kt) * np.exp(-kt * 8)
    ht = env_t(0.05)
    hat = np.diff(rng.standard_normal(len(ht) + 1)) * np.exp(-ht * 90) * 0.22
    ct = env_t(0.22)
    clap = rng.standard_normal(len(ct)) * np.exp(-ct * 22) * 0.4

    def piano(f, sec=2.5, g=0.25):
        x = env_t(sec)
        s = sum(np.sin(2 * np.pi * f * k * x) * (0.6 ** k) for k in range(1, 6))
        return g * s * np.exp(-x * 1.8) * np.minimum(1, x * 200)

    def pluck(f, sec=0.8, g=0.12):
        x = env_t(sec)
        s = sum(np.sin(2 * np.pi * f * k * x) * np.exp(-x * (4 + 3 * k)) / k for k in range(1, 7))
        return g * s

    def saw(f, sec, g):
        x = env_t(sec)
        return g * sum(np.sin(2 * np.pi * f * k * x) / k for k in range(1, 7)) * np.exp(-x * 5)

    def whoosh(sec=0.7, g=0.5):
        x = env_t(sec)
        nz = np.convolve(rng.standard_normal(len(x)), np.ones(8) / 8, "same")
        return g * nz * np.sin(np.pi * x / sec) ** 2

    prog = [(220.0, [0, 3, 7]), (174.61, [0, 4, 7]), (261.63, [0, 4, 7]), (196.0, [0, 4, 7])]
    motif = [440.0, 659.25, 523.25, 493.88, 440.0, 392.0]

    # Act 1: solo piano motif
    for i, f in enumerate(motif):
        add(0.5 + i * 1.9, piano(f))
    # ocean (12-65)
    nz = np.convolve(rng.standard_normal(n), np.ones(70) / 70, "same")
    sea_env = np.clip((tt - 11) / 2, 0, 1) * np.clip((65 - tt) / 1.5, 0, 1) * (0.55 + 0.45 * np.sin(2 * np.pi * tt / 7))
    out += nz * sea_env * 1.6

    nb = int(DUR / BEAT)
    for b in range(nb):
        t0 = b * BEAT
        root, chord = prog[(b // 4) % 4]
        if 12 <= t0 < 38.5:  # build
            prog_k = (t0 - 12) / 26
            if t0 >= 18:
                add(t0, kick, 0.35 + 0.5 * prog_k)
            if t0 >= 26:
                add(t0 + BEAT / 2, hat, 0.6 + 0.4 * prog_k)
            for q in range(2):
                semis = chord[(b * 2 + q) % 3] + 12
                add(t0 + q * BEAT / 2, pluck(root * 2 ** (semis / 12), g=0.05 + 0.07 * prog_k))
        elif 40 <= t0 < 65 or 110 <= t0 < 114.4:  # drop / climax
            add(t0, kick, 1.0)
            add(t0 + BEAT / 2, hat)
            if b % 2 == 1:
                add(t0, clap)
            for h in range(2):
                add(t0 + h * BEAT / 2, saw(root / 2, BEAT / 2, 0.16))
            for q in range(4):
                semis = chord[(b * 4 + q) % 3] + 12 * ((b * 4 + q) // 3 % 2)
                f = root * 2 ** (semis / 12)
                x = env_t(BEAT / 4)
                sq = np.sign(np.sin(2 * np.pi * f * x)) * 0.4 + np.sin(2 * np.pi * f * x)
                add(t0 + q * BEAT / 4, 0.055 * sq * np.exp(-x * 12))
        elif 65 <= t0 < 88:  # breakfast: soft guitar-like plucks
            if b % 2 == 0:
                add(t0, kick, 0.35)
            for q in range(2):
                semis = chord[(b * 2 + q) % 3] + (12 if q else 0)
                add(t0 + q * BEAT / 2, pluck(root * 2 ** (semis / 12), sec=1.2, g=0.13))
            if 82 <= t0 < 88:
                tick = rng.standard_normal(200) * np.exp(-np.arange(200) / 30) * 0.3
                add(t0, tick)
        elif 88 <= t0 < 110:  # commute: deep, confident
            add(t0, kick, 0.95)
            add(t0 + BEAT / 2, hat, 0.8)
            if b % 2 == 1:
                add(t0, clap, 0.8)
            x = env_t(BEAT)
            add(t0, 0.22 * np.sin(2 * np.pi * root / 4 * x) * np.exp(-x * 1.5))
            add(t0, saw(root / 2, BEAT, 0.08))
            if b % 4 == 0:
                add(t0, pluck(root * 2, sec=1.5, g=0.07))

    # riser into the drop + silence + impact
    x = env_t(5.5)
    riser = (np.diff(rng.standard_normal(len(x) + 1)) * 0.25 + np.sin(2 * np.pi * (200 + 900 * (x / 5.5) ** 2) * x) * 0.15) * (x / 5.5) ** 2
    add(34, riser)
    out[int(39.55 * SR):int(40 * SR)] *= 0.05
    for t_hit, g in ((40, 1.0), (110, 0.8), (114.4, 1.0)):
        x = env_t(2.5)
        boom = np.sin(2 * np.pi * (35 + 60 * np.exp(-x * 6)) * x) * np.exp(-x * 1.6)
        crash = rng.standard_normal(len(x)) * np.exp(-x * 2.5) * 0.25
        add(t_hit, g * (boom + np.diff(np.concatenate([[0], crash]))))
    # sfx
    for t_w in (11.7, 64.7, 87.7):
        add(t_w, whoosh())
    add(21.3, whoosh(0.4, 0.4))  # splash
    x = env_t(2.0)
    rev = 0.3 * np.sign(np.sin(2 * np.pi * (55 + 70 * np.sin(np.pi * x / 2.0)) * x)) * np.exp(-x * 0.8)
    add(93.0, np.convolve(rev, np.ones(30) / 30, "same"))  # engine
    # ending: piano motif returns
    for i, f in enumerate(motif[:4]):
        add(115 + i * 1.2, piano(f, 3.5, 0.3))

    out *= np.clip(tt / 0.5, 0, 1) * np.clip((DUR - tt) / 1.5, 0, 1)
    out = np.tanh(out / np.max(np.abs(out)) * 1.6)
    out = out / np.max(np.abs(out)) * 0.85
    with wave.open(path, "wb") as wv:
        wv.setnchannels(1)
        wv.setsampwidth(2)
        wv.setframerate(SR)
        wv.writeframes((out * 32767).astype(np.int16).tobytes())


def main():
    make_score(AUDIO)
    proc = subprocess.Popen(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
         "-r", str(FPS), "-i", "-", "-i", AUDIO, "-c:v", "libx264", "-preset", "slow", "-b:v", "1700k", "-maxrate", "2300k", "-bufsize", "4600k",
         "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", "-shortest", "-movflags", "+faststart", OUT],
        stdin=subprocess.PIPE)
    for i in range(FPS * DUR):
        proc.stdin.write(frame_at(i / FPS).tobytes())
        if i % (FPS * 10) == 0:
            print(f"{i // FPS}s / {DUR}s", flush=True)
    proc.stdin.close()
    proc.wait()
    os.remove(AUDIO)
    print("done ->", OUT)


if __name__ == "__main__":
    main()
