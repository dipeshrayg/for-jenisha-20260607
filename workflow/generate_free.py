#!/usr/bin/env python3
"""
Definitely Illegal — Stick Figure Animation Video Generator
Draws animated stick figure scenes entirely in Python. No AI APIs needed.

Usage:
    python generate_free.py               # generate next episode
    python generate_free.py --episode 3   # specific episode
    python generate_free.py --all         # all episodes
    python generate_free.py --list        # list status
"""

import os, sys, json, time, textwrap, argparse, wave, math
from pathlib import Path
from datetime import datetime

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from gtts import gTTS
from moviepy.editor import (
    AudioFileClip, VideoClip, ImageClip,
    concatenate_videoclips, CompositeAudioClip,
)

# ── Constants ──────────────────────────────────────────────────────────────────
EPISODES_FILE = Path(__file__).parent / "episodes.json"
OUTPUT_DIR    = Path(__file__).parent / "output"
STATUS_FILE   = Path(__file__).parent / "generated.json"

W, H = 1080, 1920
FPS  = 24

DARK   = (15,  15,  15)
YELLOW = (255, 210,   0)
WHITE  = (255, 255, 255)
GREY   = (160, 160, 160)
BLACK  = (0,   0,   0)
GREEN  = (50,  200,  50)

# ── Data helpers ───────────────────────────────────────────────────────────────

def load_episodes():
    with open(EPISODES_FILE) as f:
        return json.load(f)

def load_status():
    return json.loads(STATUS_FILE.read_text()) if STATUS_FILE.exists() else {}

def save_status(status):
    STATUS_FILE.write_text(json.dumps(status, indent=2))

def next_episode(episodes, status):
    done = {int(k) for k in status}
    for ep in episodes:
        if ep["id"] not in done:
            return ep
    return None

def get_font(size):
    candidates = [
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/Library/Fonts/Arial Bold.ttf",
    ]
    for p in candidates:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass
    return ImageFont.load_default()

def centered_text(draw, text, y, font, color=WHITE, shadow=True):
    bbox = draw.textbbox((0, 0), text, font=font)
    x = (W - (bbox[2] - bbox[0])) // 2
    if shadow:
        draw.text((x + 3, y + 3), text, font=font, fill=BLACK)
    draw.text((x, y), text, font=font, fill=color)

# ── Math helpers ───────────────────────────────────────────────────────────────

def polar(cx, cy, length, angle_deg):
    """Endpoint of a line from (cx, cy) of given length at angle (0 = straight down)."""
    r = math.radians(angle_deg)
    return (cx + length * math.sin(r), cy + length * math.cos(r))

def fill_gradient(img, top_color, bot_color):
    arr = np.zeros((img.height, img.width, 3), dtype=np.uint8)
    for y in range(img.height):
        t = y / img.height
        arr[y, :] = [int(top_color[i]*(1-t) + bot_color[i]*t) for i in range(3)]
    return Image.fromarray(arr)

# ── Stick figure ───────────────────────────────────────────────────────────────

TALKY = {"explain", "wave", "cheer", "pour", "point", "hands_up", "type", "confused"}

class Figure:
    """Lively animated stick figure with moving mouth, blinking eyes and big gestures.

    Actions: idle walk wave cheer pour point hands_up type confused sneak explain.
    Pass talk=True/False to force the mouth chatter; defaults to on for talky actions.
    """

    def __init__(self, cx, cy_feet, height=200, color=WHITE, lw=None):
        self.cx, self.cy, self.h, self.color = cx, cy_feet, height, color
        # Bold line weight that scales with the figure (reference uses thick clean lines)
        self.lw = lw if lw is not None else max(4, int(height * 0.045))

    def draw(self, draw, t, action="idle", flip=False, talk=None):
        cx, cy, h, c, lw = self.cx, self.cy, self.h, self.color, self.lw
        sway = 0.0  # horizontal body shift for liveliness

        # --- joint angles (0 = hanging straight down, positive = swings right) ---
        if action == "walk":
            p = t * 6 * math.pi
            ll, lr = math.sin(p)*48, -math.sin(p)*48
            al, ar = -math.sin(p)*52,  math.sin(p)*52
            bob = abs(math.sin(p)) * h * 0.04
        elif action == "explain":  # frank narrator: gesturing, weight-shifting, alive
            p = t * 5 * math.pi
            ll, lr = math.sin(p*0.5)*6, -math.sin(p*0.5)*6
            al = -45 + math.sin(p)*40
            ar =  45 - math.sin(p + 1.3)*40
            bob  = abs(math.sin(p*0.5)) * h * 0.02
            sway = math.sin(t * 4 * math.pi) * h * 0.04
        elif action == "wave":
            p = t * 6 * math.pi
            ll, lr, al, ar = 6, -6, math.sin(p)*65 - 75, 35
            bob = abs(math.sin(p*0.5)) * h * 0.015
        elif action == "cheer":
            p = t * 6 * math.pi
            ll, lr = math.sin(p)*20, -math.sin(p)*20
            al = math.sin(p)*35 - 110
            ar = -math.sin(p)*35 + 110
            bob = abs(math.sin(p)) * h * 0.06  # hopping
        elif action == "pour":
            p = t * 3 * math.pi
            ll, lr = -6, 6
            al = -78 + math.sin(p)*14
            ar = math.sin(p)*22 + 12
            bob = math.sin(p) * h * 0.01
        elif action == "point":
            p = t * 4 * math.pi
            ll, lr, al = 0, 0, -32 + math.sin(p*0.5)*12
            ar = -60 + math.sin(p)*16
            bob = math.sin(p*0.5) * h * 0.012
            sway = math.sin(t * 3 * math.pi) * h * 0.02
        elif action == "hands_up":
            p = t * 5 * math.pi
            ll, lr = math.sin(p*0.5)*8, -math.sin(p*0.5)*8
            al = -100 + math.sin(p)*22
            ar =  100 - math.sin(p)*22
            bob = abs(math.sin(p*0.5)) * h * 0.02
        elif action == "type":
            p = t * 12 * math.pi
            ll, lr = 6, -6
            al = -42 + math.sin(p)*26
            ar =  42 - math.sin(p)*26
            bob = math.sin(p*0.5) * h * 0.015
        elif action == "confused":
            p = t * 4 * math.pi
            ll, lr = 12, -12
            al, ar = -22 + math.sin(p*0.5)*10, -68 + math.sin(p)*26
            bob = math.sin(p*0.5) * h * 0.01
            sway = math.sin(t * 2.5 * math.pi) * h * 0.03
        elif action == "sneak":
            p = t * 6 * math.pi
            ll, lr = math.sin(p)*32, -math.sin(p)*32
            al, ar = math.sin(p)*26 - 45, -math.sin(p)*26 + 45
            bob = 0
            cy = cy - h * 0.08  # crouch
        else:  # idle / breathe
            p = t * 2 * math.pi
            ll, lr = 0, 0
            al = math.sin(p)*10 - 25
            ar = -math.sin(p)*10 + 25
            bob = math.sin(p) * h * 0.015

        if flip:
            ll, lr, al, ar = -lr, -ll, -ar, -al
            sway = -sway

        cx = cx + sway
        cy_adj = cy - bob
        head_r   = h * 0.13
        head_cy  = cy_adj - h + head_r
        neck_y   = cy_adj - h + head_r * 2.0
        shldr_y  = cy_adj - h * 0.72
        hip_y    = cy_adj - h * 0.43

        # Head
        draw.ellipse([cx-head_r, head_cy-head_r, cx+head_r, head_cy+head_r],
                     outline=c, width=lw)

        hand_fill = WHITE if c != WHITE else (245, 245, 245)
        hr = max(3, int(lw * 1.5))   # hand / foot blob radius

        # Eyes — big friendly dots that blink
        eye_dx, eye_dy = head_r*0.42, head_r*0.10
        er = max(2, int(lw*0.75))
        blink = math.sin(t * 8 * math.pi) > 0.93
        for sx in (-1, 1):
            ex0 = cx + sx*eye_dx
            if blink:
                draw.line([(ex0-er, head_cy-eye_dy), (ex0+er, head_cy-eye_dy)],
                          fill=c, width=max(2, lw//2))
            else:
                draw.ellipse([ex0-er, head_cy-eye_dy-er, ex0+er, head_cy-eye_dy+er], fill=c)

        # Eyebrows — a little attitude (the "frank" look)
        brow_y = head_cy - head_r*0.42
        for sx in (-1, 1):
            draw.line([(cx+sx*eye_dx-er*1.6, brow_y+er*0.8),
                       (cx+sx*eye_dx+er*1.6, brow_y)], fill=c, width=max(2, lw//2))

        # Mouth — smiles, and opens to "talk" while narrating
        if talk is None:
            talk = action in TALKY
        my = head_cy + head_r*0.42
        if talk and math.sin(t * 34 * math.pi) > 0:
            draw.ellipse([cx-head_r*0.30, my-head_r*0.12,
                          cx+head_r*0.30, my+head_r*0.32], fill=c)  # open mouth
        else:
            draw.arc([cx-head_r*0.42, my-head_r*0.45, cx+head_r*0.42, my+head_r*0.35],
                     20, 160, fill=c, width=max(2, lw//2))            # smile

        # Body
        draw.line([(int(cx), int(neck_y)), (int(cx), int(hip_y))], fill=c, width=lw)

        # Arms (two segments so elbows bend) ending in white blob hands
        alen = h * 0.30
        for angle in (al, ar):
            elbow = polar(cx, shldr_y, alen*0.55, angle)
            hand  = polar(elbow[0], elbow[1], alen*0.55, angle*0.7)
            draw.line([(int(cx), int(shldr_y)), (int(elbow[0]), int(elbow[1]))], fill=c, width=lw)
            draw.line([(int(elbow[0]), int(elbow[1])), (int(hand[0]), int(hand[1]))], fill=c, width=lw)
            draw.ellipse([hand[0]-hr, hand[1]-hr, hand[0]+hr, hand[1]+hr],
                         fill=hand_fill, outline=c, width=max(2, lw//2))

        # Legs (two segments) ending in white blob feet
        llen = h * 0.47
        for ang, ox in ((ll, -h*0.04), (lr, h*0.04)):
            knee = polar(cx+ox, hip_y, llen*0.55, ang)
            foot = polar(knee[0], knee[1], llen*0.50, ang*0.5)
            draw.line([(int(cx+ox), int(hip_y)), (int(knee[0]), int(knee[1]))], fill=c, width=lw)
            draw.line([(int(knee[0]), int(knee[1])), (int(foot[0]), int(foot[1]))], fill=c, width=lw)
            draw.ellipse([foot[0]-hr*1.2, foot[1]-hr*0.7, foot[0]+hr*1.2, foot[1]+hr*0.7],
                         fill=hand_fill, outline=c, width=max(2, lw//2))

# ── Props & scene helpers ──────────────────────────────────────────────────────

def speech_bubble(draw, cx, cy, text, font, bg=WHITE, fg=BLACK):
    lines = textwrap.wrap(text, width=16)
    pad, lh = 18, 40
    bw = max((len(l) for l in lines), default=1) * 19 + pad*2
    bh = len(lines)*lh + pad*2
    bx, by = cx - bw//2, cy - bh - 35
    draw.rounded_rectangle([bx, by, bx+bw, by+bh], radius=15, fill=bg, outline=BLACK, width=3)
    draw.polygon([(cx-12, by+bh), (cx+12, by+bh), (cx, cy)], fill=bg, outline=BLACK)
    ty = by + pad
    for line in lines:
        bb = draw.textbbox((0,0), line, font=font)
        draw.text((bx + (bw - (bb[2]-bb[0]))//2, ty), line, fill=fg, font=font)
        ty += lh

def dollar_pop(draw, positions, t, font):
    """Animate floating $ signs."""
    for i, (sx, sy) in enumerate(positions):
        bob = math.sin((t + i*0.35) * 3*math.pi) * 28
        draw.text((sx, int(sy + bob)), "$", fill=GREEN, font=font)

def draw_ground(draw, y, color):
    draw.rectangle([(0, y), (W, H)], fill=color)

def draw_mountain(draw, cx, peak_y, base_y, rock=(200,200,210)):
    draw.polygon([(cx-420, base_y), (cx+420, base_y), (cx, peak_y)], fill=rock)
    draw.polygon([(cx-90, peak_y+110), (cx+90, peak_y+110), (cx, peak_y)], fill=WHITE)

def draw_tree(draw, cx, gy, size=90, tc=(40,140,40)):
    tw = size//6
    draw.rectangle([cx-tw//2, gy-size//3, cx+tw//2, gy], fill=(130,85,40))
    draw.polygon([(cx, gy-size//3-size), (cx-size//2, gy-size//3), (cx+size//2, gy-size//3)], fill=tc)

def draw_cloud(draw, cx, cy, r):
    for ox, oy in [(-r//2,0), (0,-r//3), (r//2,0), (0,0)]:
        draw.ellipse([cx+ox-r//2, cy+oy-r//3, cx+ox+r//2, cy+oy+r//3], fill=WHITE)

def draw_simple_car(draw, x, y, color=(200,60,60)):
    draw.rounded_rectangle([x, y-60, x+200, y], radius=18, fill=color, outline=BLACK, width=2)
    draw.ellipse([x+20, y-15, x+60, y+15], fill=BLACK)
    draw.ellipse([x+130, y-15, x+170, y+15], fill=BLACK)
    draw.rounded_rectangle([x+30, y-110, x+170, y-65], radius=12, fill=color, outline=BLACK, width=2)
    draw.rectangle([x+40, y-105, x+160, y-70], fill=(160,220,255))

def draw_cat(draw, cx, cy, t):
    """Simple cute/unimpressed cat."""
    r = 48
    # Body
    draw.ellipse([cx-r, cy-r//2, cx+r, cy+r//2], fill=(140,140,160), outline=BLACK, width=3)
    # Head
    draw.ellipse([cx-r//1.4, cy-r*1.9, cx+r//1.4, cy-r//2], fill=(140,140,160), outline=BLACK, width=3)
    hcx, hcy = cx, cy - r*1.4
    # Ears
    for sx in (-1, 1):
        draw.polygon([(hcx+sx*22, hcy-5), (hcx+sx*8, hcy-28), (hcx+sx*5, hcy-2)],
                     fill=(140,140,160), outline=BLACK, width=2)
    # Unimpressed flat eyes
    draw.line([(hcx-18, hcy-8), (hcx-6, hcy-8)], fill=BLACK, width=3)
    draw.line([(hcx+6,  hcy-8), (hcx+18, hcy-8)], fill=BLACK, width=3)
    # Tail
    tail_bob = math.sin(t*3*math.pi)*22
    draw.line([(cx+r, cy), (cx+r+45, cy-35+tail_bob), (cx+r+65, cy-65+tail_bob)],
              fill=(140,140,160), width=9)

def draw_bird(draw, cx, cy, t, i=0):
    """Simple pigeon."""
    bob = math.sin((t+i*0.25)*2*math.pi)*5
    by = cy + bob
    draw.ellipse([cx-20, by-15, cx+20, by+15], fill=(100,100,150), outline=BLACK, width=2)
    draw.ellipse([cx-10, by-35, cx+10, by-15], fill=(100,100,150), outline=BLACK, width=2)
    draw.polygon([(cx+10,by-28),(cx+22,by-25),(cx+10,by-22)], fill=(255,180,0))
    draw.ellipse([cx-8, by+8, cx+8, by+24], fill=(210,190,50), outline=BLACK, width=2)

# ── Episode scene renderers ────────────────────────────────────────────────────

def ep01(t):
    """Selling Premium Mountain Air — big seller on peak, queue of customers below."""
    # Rich layered sky: deep blue at top fading to pale horizon
    img = fill_gradient(Image.new("RGB",(W,H)), (45,110,200), (185,220,255))
    d   = ImageDraw.Draw(img)

    # Far mountains (muted blue-grey for atmospheric depth)
    for mx, mw, mh, mc in [(160, 500, 420, (145,165,205)), (820, 440, 380, (135,155,195))]:
        d.polygon([(mx-mw//2, H//2+80), (mx+mw//2, H//2+80), (mx, H//2+80-mh)], fill=mc)
        # Snow on far peaks
        d.polygon([(mx, H//2+80-mh), (mx-55, H//2+80-mh+85), (mx+55, H//2+80-mh+85)],
                  fill=(230,238,255))

    # Main mountain — large, central
    peak_y = H*17//100
    base_y = H*63//100
    draw_mountain(d, W//2, peak_y, base_y, rock=(170,182,198))

    # Ground / meadow with subtle texture
    draw_ground(d, base_y, (52,132,58))
    for gy2 in range(base_y, base_y + 70, 16):
        d.line([(0, gy2), (W, gy2)], fill=(46,122,52), width=2)

    # Clouds — multiple sizes, slow animated drift
    for i, (ccx, ccy, cr) in enumerate([(90, 145, 95), (365, 108, 72), (780, 128, 105), (985, 192, 68)]):
        drift = math.sin((t + i * 0.28) * 1.4 * math.pi) * 16
        draw_cloud(d, int(ccx + drift), ccy, cr)

    # Trees framing the base (both sides)
    for tx in [35, 118, 872, 975, 1048]:
        draw_tree(d, tx, base_y, size=140, tc=(32,128,32))

    # ── MAIN SELLER on mountain peak ──
    seller_cx = W // 2
    seller_cy = peak_y + 240  # push feet far enough down so head stays in frame
    Figure(seller_cx, seller_cy, height=420, color=DARK).draw(d, t, action="pour")

    # Big premium jar prop
    jx, jy = seller_cx + 130, peak_y - 210
    # Jar body — glassy blue
    d.rectangle([jx, jy, jx+90, jy+130], fill=(185,232,255), outline=BLACK, width=5)
    # Lid
    d.rectangle([jx - 8, jy - 18, jx + 98, jy + 10], fill=(175,178,182), outline=BLACK, width=4)
    # Label panel
    d.rectangle([jx + 8, jy + 28, jx + 82, jy + 95], fill=WHITE, outline=(130,130,130), width=2)
    d.text((jx + 12, jy + 30), "FRESH", fill=(25,95,195), font=get_font(22))
    d.text((jx + 16, jy + 56), "AIR", fill=(25,95,195), font=get_font(30))
    d.text((jx + 10, jy + 90), "PREMIUM", fill=BLACK, font=get_font(17))

    # Animated air particles pouring from seller's hand into the jar
    for i in range(6):
        pour_phase = (t * 3.5 + i * 0.18) % 1.0
        px2 = int(seller_cx + 65 + pour_phase * 60)
        py2 = int(peak_y - 185 - pour_phase * 40)
        pr  = max(2, int(9 * (1 - pour_phase)))
        d.ellipse([px2 - pr, py2 - pr, px2 + pr, py2 + pr], fill=(210, 242, 255))

    # Price sign on mountain side
    sign_x, sign_y = W // 2 + 190, peak_y + 100
    d.rectangle([sign_x, sign_y, sign_x + 240, sign_y + 120], fill=YELLOW, outline=BLACK, width=5)
    d.text((sign_x + 12, sign_y + 8),  "MOUNTAIN AIR", fill=BLACK, font=get_font(28))
    d.text((sign_x + 42, sign_y + 46), "$99 / JAR",    fill=(200,28,28), font=get_font(35))
    d.text((sign_x + 16, sign_y + 88), "CERTIFIED FRESH", fill=BLACK, font=get_font(21))

    # Speech bubble from seller
    if t > 0.18:
        speech_bubble(d, seller_cx - 60, peak_y - 250,
                      "$99 a jar!\nFresh!\nPremium!", get_font(44))

    # ── CUSTOMER QUEUE at base ──
    queue_y = base_y
    # Queue rope
    d.line([(110, queue_y - 14), (540, queue_y - 14)], fill=(150,115,55), width=5)

    cust_colors = [(228,198,198), (198,228,198), (198,198,230)]
    for i, xp in enumerate([178, 315, 452]):
        Figure(xp, queue_y, height=290, color=cust_colors[i]).draw(d, (t + i * 0.33) % 1, action="idle")
        # Each customer holds a money bag
        mb_x, mb_y = xp + 60, queue_y - 175
        d.ellipse([mb_x, mb_y, mb_x + 44, mb_y + 52], fill=(208,178,48), outline=BLACK, width=3)
        d.text((mb_x + 10, mb_y + 14), "$", fill=BLACK, font=get_font(26))

    # "QUEUE HERE" arrow sign
    d.rectangle([72, queue_y - 118, 280, queue_y - 52], fill=WHITE, outline=BLACK, width=3)
    d.text((82, queue_y - 110), "QUEUE",  fill=BLACK,       font=get_font(30))
    d.text((82, queue_y - 76),  "HERE →", fill=(200,30,30), font=get_font(30))

    return np.array(img)


def ep02(t):
    """Neighborhood Toll Booth — animated barrier, moving car, big operator."""
    # Sky gradient — clear suburban day
    img = fill_gradient(Image.new("RGB",(W,H)), (135,195,240), (210,232,255))
    d   = ImageDraw.Draw(img)

    gy = H * 60 // 100  # ground level

    # Distant suburb silhouette
    for bx, bw2, bh2 in [(60,80,120),(155,100,155),(650,90,130),(780,70,100),(900,110,145)]:
        d.rectangle([bx, gy-bh2, bx+bw2, gy], fill=(175,185,200))
        # Windows
        for wy in range(gy-bh2+15, gy-15, 28):
            for wx2 in range(bx+10, bx+bw2-10, 24):
                d.rectangle([wx2, wy, wx2+12, wy+16], fill=(255,235,150))

    # Grass verge
    draw_ground(d, gy - 50, (75,148,65))
    # Road surface
    d.rectangle([(0, gy), (W, H)], fill=(68,68,68))
    # Animated road lane dashes
    dash_offset = int(t * 130) % 130
    for x in range(-130, W + 130, 130):
        d.rectangle([x + dash_offset - 55, gy + 18, x + dash_offset - 12, gy + 34], fill=YELLOW)

    # Trees lining the road
    for tx in [48, 145, 855, 968, 1055]:
        draw_tree(d, tx, gy - 50, size=155, tc=(38,138,38))

    # Toll booth building
    bx, by = W // 2 - 100, gy - 260
    # Booth body
    d.rectangle([bx, by, bx + 200, gy - 55], fill=(240,222,172), outline=BLACK, width=4)
    # Booth window
    d.rectangle([bx + 28, by + 18, bx + 172, by + 118], fill=(168,218,255), outline=BLACK, width=3)
    # Roof stripe
    d.rectangle([bx, by, bx + 200, by + 22], fill=(220,50,50), outline=BLACK, width=2)
    # Booth sign
    d.rectangle([bx + 18, by + 128, bx + 182, by + 175], fill=YELLOW, outline=BLACK, width=2)
    d.text((bx + 22, by + 132), "TOLL BOOTH", fill=BLACK, font=get_font(22))

    # Animated barrier arm
    pivot_x, pivot_y = bx + 200, gy - 92
    # Arm sweeps up/down
    arm_angle = math.sin(t * 2 * math.pi) * 0.38 + 0.06
    ax2 = int(pivot_x + 330 * math.cos(arm_angle))
    ay2 = int(pivot_y + 330 * math.sin(arm_angle))
    # Striped arm: alternate red/white segments
    n_segs = 6
    for seg in range(n_segs):
        frac0, frac1 = seg / n_segs, (seg + 1) / n_segs
        sx0 = int(pivot_x + (ax2 - pivot_x) * frac0)
        sy0 = int(pivot_y + (ay2 - pivot_y) * frac0)
        sx1 = int(pivot_x + (ax2 - pivot_x) * frac1)
        sy1 = int(pivot_y + (ay2 - pivot_y) * frac1)
        seg_color = (225,45,45) if seg % 2 == 0 else WHITE
        d.line([(sx0, sy0), (sx1, sy1)], fill=seg_color, width=12)
    d.ellipse([pivot_x - 10, pivot_y - 10, pivot_x + 10, pivot_y + 10], fill=(190,28,28))

    # Operator — big figure inside booth, waving
    Figure(W // 2, gy - 60, height=400, color=WHITE).draw(d, t, action="wave")

    # Big toll sign on a post
    post_x, post_y = W // 2 - 280, gy - 55
    d.rectangle([post_x - 4, post_y - 240, post_x + 4, post_y], fill=BLACK)
    d.rectangle([post_x - 145, post_y - 240, post_x + 145, post_y - 110],
                fill=YELLOW, outline=BLACK, width=4)
    sf = get_font(36)
    d.text((post_x - 130, post_y - 232), "TOLL: $2.00",   fill=BLACK, font=sf)
    d.text((post_x - 138, post_y - 188), "EXACT CHANGE",  fill=BLACK, font=sf)
    d.text((post_x - 105, post_y - 144), "ONLY!!",        fill=(200,30,30), font=sf)

    # Moving car approaching from right
    car_x = int(W + 50 - (t % 1) * (W + 300))
    draw_simple_car(d, car_x, gy, color=(210,55,55))

    # Wave speech bubble
    if t > 0.3:
        speech_bubble(d, W // 2, gy - 440, "That'll be\n$2 please!\nExact change!", get_font(40))

    return np.array(img)


def ep03(t):
    """Charging Cats Rent — big indoor room, landlord vs unimpressed cat on couch."""
    # Warm interior walls
    img = Image.new("RGB", (W, H), (238, 218, 182))
    d   = ImageDraw.Draw(img)

    floor_y = H * 66 // 100

    # Ceiling cornice
    d.rectangle([(0, 0), (W, 55)], fill=(95,65,45))
    d.rectangle([(0, 55), (W, 75)], fill=(115,85,60))

    # Wall details — vertical wallpaper stripes
    for wx in range(0, W, 55):
        d.line([(wx, 75), (wx, floor_y)], fill=(228,208,172), width=2)

    # Framed picture on wall (left side)
    d.rectangle([55, 140, 265, 340], fill=(200,180,140), outline=BLACK, width=5)
    d.rectangle([72, 157, 248, 323], fill=(150,200,180))
    d.text((88, 220), "ART", fill=BLACK, font=get_font(34))

    # Window on right wall with daylight
    d.rectangle([760, 120, 990, 380], fill=(168,218,255), outline=BLACK, width=6)
    d.line([(875, 120), (875, 380)], fill=BLACK, width=4)
    d.line([(760, 250), (990, 250)], fill=BLACK, width=4)
    # Sunlight rays
    for ray_ang in range(-30, 31, 12):
        rx = int(875 + 250 * math.sin(math.radians(ray_ang)))
        ry = int(250 + 250 * math.cos(math.radians(ray_ang)))
        d.line([(875, 250), (rx, ry)], fill=(255,250,200), width=2)

    # Floor
    d.rectangle([(0, floor_y), (W, H)], fill=(148,112,72))
    # Floor boards
    for fx in range(0, W, 95):
        d.line([(fx, floor_y), (fx, H)], fill=(135,100,62), width=2)
    for fy in range(floor_y, H, 40):
        d.line([(0, fy), (W, fy)], fill=(138,104,65), width=1)

    # Rug / carpet under couch
    couch_y = floor_y - 30
    d.ellipse([W // 5 - 40, couch_y + 90, W * 4 // 5 + 40, couch_y + 190],
              fill=(165, 88, 88))
    d.ellipse([W // 5 - 20, couch_y + 100, W * 4 // 5 + 20, couch_y + 180],
              fill=(185, 105, 105))

    # Couch — big and detailed
    # Seat cushions
    d.rounded_rectangle([W // 5, couch_y, W * 4 // 5, couch_y + 175],
                        radius=28, fill=(178,95,75), outline=BLACK, width=4)
    # Backrest
    d.rounded_rectangle([W // 5, couch_y - 65, W * 4 // 5, couch_y + 28],
                        radius=18, fill=(202,118,95), outline=BLACK, width=4)
    # Cushion divider
    d.line([(W // 2, couch_y), (W // 2, couch_y + 175)], fill=(155,78,62), width=4)
    # Armrests
    d.rounded_rectangle([W // 5 - 38, couch_y - 50, W // 5 + 15, couch_y + 175],
                        radius=18, fill=(190,105,82), outline=BLACK, width=3)
    d.rounded_rectangle([W * 4 // 5 - 15, couch_y - 50, W * 4 // 5 + 38, couch_y + 175],
                        radius=18, fill=(190,105,82), outline=BLACK, width=3)

    # Side table with coffee mug
    d.rectangle([W * 4 // 5 + 30, couch_y - 45, W * 4 // 5 + 135, couch_y - 8],
                fill=(165,120,70), outline=BLACK, width=3)
    d.rectangle([W * 4 // 5 + 58, couch_y - 92, W * 4 // 5 + 108, couch_y - 45],
                fill=WHITE, outline=BLACK, width=3)
    d.text((W * 4 // 5 + 64, couch_y - 82), "☕", fill=BLACK, font=get_font(24))

    # ── LANDLORD (left side, large) ──
    landlord_cx = W // 4 - 45
    Figure(landlord_cx, floor_y, height=460, color=WHITE).draw(d, t, action="point")

    # Lease document the landlord holds
    lx, ly = landlord_cx + 130, floor_y - 390
    d.rectangle([lx, ly, lx + 110, ly + 145], fill=WHITE, outline=BLACK, width=3)
    # Document header bar
    d.rectangle([lx, ly, lx + 110, ly + 28], fill=(200,28,28))
    d.text((lx + 8, ly + 4),  "LEASE", fill=WHITE, font=get_font(22))
    tf = get_font(16)
    for ly2 in [45, 62, 79, 96, 113]:
        d.line([(lx + 8, ly + ly2), (lx + 102, ly + ly2)], fill=GREY, width=2)
    d.text((lx + 8, ly + 120), "SIGN →", fill=(200,28,28), font=get_font(18))

    # ── CAT on couch (right side, large) ──
    # Draw a bigger cat
    cat_cx, cat_cy = W * 2 // 3 + 20, couch_y - 10
    cat_r = 80
    # Cat body (lying on couch)
    d.ellipse([cat_cx - cat_r, cat_cy - cat_r // 2, cat_cx + cat_r, cat_cy + cat_r // 2],
              fill=(135,138,160), outline=BLACK, width=4)
    # Cat head
    d.ellipse([cat_cx - cat_r // 1.3, cat_cy - cat_r * 1.95,
               cat_cx + cat_r // 1.3, cat_cy - cat_r // 2],
              fill=(135,138,160), outline=BLACK, width=4)
    hcx, hcy = cat_cx, int(cat_cy - cat_r * 1.4)
    # Ears
    for sx in (-1, 1):
        d.polygon([(hcx + sx*36, hcy - 8), (hcx + sx*14, hcy - 46), (hcx + sx*8, hcy - 4)],
                  fill=(135,138,160), outline=BLACK, width=3)
        d.polygon([(hcx + sx*30, hcy - 10), (hcx + sx*16, hcy - 38), (hcx + sx*12, hcy - 8)],
                  fill=(200,160,160))
    # Unimpressed FLAT eyes (the comedy)
    d.line([(hcx - 28, hcy - 12), (hcx - 9, hcy - 12)], fill=BLACK, width=5)
    d.line([(hcx + 9,  hcy - 12), (hcx + 28, hcy - 12)], fill=BLACK, width=5)
    # Whiskers
    for wy, wx0, wx1 in [(-4, -72, -32), (0, -75, -32), (4, -72, -32),
                          (-4, 32, 72),  (0, 32, 75),   (4, 32, 72)]:
        d.line([(hcx + wx0, hcy + wy), (hcx + wx1, hcy + wy)], fill=BLACK, width=2)
    # Nose
    d.polygon([(hcx, hcy + 6), (hcx - 8, hcy - 2), (hcx + 8, hcy - 2)],
              fill=(210,130,130))
    # Tail with animated bob
    tail_bob = math.sin(t * 3 * math.pi) * 28
    d.line([(cat_cx + cat_r, cat_cy),
            (cat_cx + cat_r + 58, cat_cy - 45 + tail_bob),
            (cat_cx + cat_r + 85, cat_cy - 90 + tail_bob)],
           fill=(135,138,160), width=12)

    # Speech bubbles
    if t > 0.18:
        speech_bubble(d, landlord_cx, floor_y - 498,
                      "Rent is due!\nSign the\nlease!", get_font(44))
    if t > 0.5:
        speech_bubble(d, cat_cx, cat_cy - 195, "...no.", get_font(46),
                      bg=(255,238,238))

    return np.array(img)


def ep04(t):
    """Actual Pyramid Scheme — presenter at whiteboard, audience, floating pyramids."""
    # Dark conference-room gradient
    img = fill_gradient(Image.new("RGB",(W,H)), (16,16,42), (32,32,68))
    d   = ImageDraw.Draw(img)

    # Stars / dim ceiling lights
    for i in range(40):
        sx = (i * 163 + 75) % W
        sy = (i * 109 + 38) % (H // 3)
        br = 0.45 + 0.55 * math.sin((t + i * 0.08) * 5 * math.pi)
        r  = max(1, int(br * 3))
        d.ellipse([sx - r, sy - r, sx + r, sy + r], fill=WHITE)

    # Floor
    d.rectangle([(0, H * 65 // 100), (W, H)], fill=(22, 22, 38))
    for fx in range(0, W, 110):
        d.line([(fx, H * 65 // 100), (fx, H)], fill=(28,28,46), width=2)

    # Whiteboard — big and central, left-of-center
    wb_x, wb_y = W // 2 - 40, H // 8
    wb_w, wb_h = 490, 430
    # Board frame
    d.rectangle([wb_x - 8, wb_y - 8, wb_x + wb_w + 8, wb_y + wb_h + 8],
                fill=(80,70,55), outline=BLACK, width=3)
    # Board surface
    d.rectangle([wb_x, wb_y, wb_x + wb_w, wb_y + wb_h], fill=(235,238,232))
    # Marker tray
    d.rectangle([wb_x, wb_y + wb_h, wb_x + wb_w, wb_y + wb_h + 18], fill=(175,165,148))

    # Pyramid diagram on whiteboard
    pc = wb_x + wb_w // 2
    pb = wb_y + wb_h - 30
    pt = wb_y + 48
    d.polygon([(pc, pt), (pc - 188, pb), (pc + 188, pb)],
              fill=(228,195,195), outline=(200,48,48), width=4)
    for lv in [0.30, 0.60]:
        lx0 = int(pc - 188 * lv)
        lx1 = int(pc + 188 * lv)
        ly2 = int(pb - (pb - pt) * lv)
        d.line([(lx0, ly2), (lx1, ly2)], fill=(200,48,48), width=3)
    tf = get_font(26)
    d.text((pc - 24, pt + 10),  "YOU",             fill=BLACK, font=tf)
    d.text((pc - 50, pb - 98),  "FRIENDS",         fill=BLACK, font=tf)
    d.text((pc - 105, pb - 44), "FRIEND'S FRIENDS", fill=BLACK, font=tf)
    # Down-arrows indicating money flow
    arrow_bob = int(math.sin(t * 4 * math.pi) * 8)
    d.text((pc - 14, pt + 55 + arrow_bob), "↓", fill=(200,48,48), font=get_font(32))

    # ── PRESENTER — big, yellow, energetic ──
    pres_cx, pres_cy = W * 19 // 100, H * 65 // 100
    Figure(pres_cx, pres_cy, height=450, color=YELLOW).draw(d, t, action="point")

    # Presenter's pointer stick
    p_hand_x = int(pres_cx + 200 * math.sin(math.radians(-60 + math.sin(t * 4 * math.pi) * 14)))
    p_hand_y = int(pres_cy - 450 * 0.72 + 200 * math.cos(math.radians(-60)))
    d.line([(pres_cx, pres_cy - int(450 * 0.72)), (wb_x + 5, wb_y + wb_h // 2)],
           fill=WHITE, width=4)

    # ── AUDIENCE — small figures in front ──
    aud_y = H * 65 // 100
    for i, ax in enumerate([70, 195, 815, 940, 1040]):
        aud_h = 170 + i * 8
        Figure(ax, aud_y, height=aud_h, color=GREY).draw(d, (t + i * 0.18) % 1, action="idle")

    # Floating pyramid decorations (animated bob)
    for i, (px2, py2) in enumerate([(108, H // 5 - 40), (820, H // 4 - 20), (880, H * 3 // 8)]):
        bob = math.sin((t + i * 0.38) * 2 * math.pi) * 22
        pts = [(px2, int(py2 + bob)),
               (px2 - 34, int(py2 + 68 + bob)),
               (px2 + 34, int(py2 + 68 + bob))]
        d.polygon(pts, fill=YELLOW, outline=BLACK, width=3)
        d.text((px2 - 8, int(py2 + 22 + bob)), "$", fill=BLACK, font=get_font(24))

    # Speech bubble
    if t > 0.28:
        speech_bubble(d, pres_cx, pres_cy - 490,
                      "Buy a pyramid!\nSell pyramids!\nGet rich!", get_font(44))

    return np.array(img)


def ep05(t):
    """Selling Homework to Birds — kid at desk, pigeon queue, price signs."""
    # Classroom / bedroom gradient
    img = fill_gradient(Image.new("RGB",(W,H)), (252,250,215), (232,225,190))
    d   = ImageDraw.Draw(img)

    floor_y = H * 68 // 100

    # Wall — light yellow
    # Floor
    d.rectangle([(0, floor_y), (W, H)], fill=(188,172,148))
    for fx in range(0, W, 90):
        d.line([(fx, floor_y), (fx, H)], fill=(178,162,138), width=2)

    # Blackboard / chalkboard on wall (left)
    d.rectangle([42, 140, 378, 380], fill=(48,88,58), outline=BLACK, width=5)
    d.rectangle([55, 153, 365, 367], fill=(52,94,62))
    cf = get_font(24)
    d.text((68, 165), "MATH TEST", fill=WHITE, font=cf)
    d.text((68, 198), "Due: Today", fill=(200,255,200), font=cf)
    # Chalk smudges
    for ci2 in range(6):
        cx2 = 68 + ci2 * 48
        cy2 = 235 + (ci2 % 3) * 32
        d.line([(cx2, cy2), (cx2 + 38, cy2)], fill=(180,210,180), width=3)

    # Shelf / bookcase (right background)
    d.rectangle([750, 130, 1040, 420], fill=(160,118,68), outline=BLACK, width=4)
    for shelf_y in [190, 258, 325, 392]:
        d.line([(755, shelf_y), (1035, shelf_y)], fill=(140,100,55), width=3)
    # Books on shelves
    book_colors = [(200,60,60),(60,60,200),(60,180,60),(200,160,60),(180,60,200)]
    for bi, (bx2, by2) in enumerate([(760,145),(820,145),(882,145),(760,210),(822,210),(888,210),
                                      (760,275),(830,275),(760,342),(825,342)]):
        d.rectangle([bx2, by2, bx2+48, by2+44], fill=book_colors[bi%5], outline=BLACK, width=2)

    # ── DESK — big, central ──
    desk_y = H * 63 // 100
    desk_x1, desk_x2 = W // 9, W * 58 // 100
    # Desk top surface
    d.rectangle([desk_x1, desk_y, desk_x2, desk_y + 38], fill=(172,122,72), outline=BLACK, width=4)
    # Legs
    for legx in [desk_x1 + 25, desk_x2 - 50]:
        d.rectangle([legx, desk_y + 38, legx + 28, floor_y], fill=(148,95,52), outline=BLACK, width=2)

    # Papers stacked on desk
    for i, (px2, py2, angle) in enumerate([(desk_x1+25, desk_y-58, 3),
                                            (desk_x1+95, desk_y-45, -4),
                                            (desk_x1+50, desk_y-72, 7)]):
        d.rectangle([px2, py2, px2 + 85, py2 + 108], fill=WHITE, outline=BLACK, width=2)
        d.text((px2 + 6, py2 + 8),  "MATH",     fill=BLACK, font=get_font(18))
        d.text((px2 + 6, py2 + 32), "HOMEWORK", fill=BLACK, font=get_font(18))
        # Grade on top paper
        if i == 0:
            d.text((px2 + 50, py2 + 60), "A+", fill=(200,28,28), font=get_font(28))
        for line_y in range(py2 + 62, py2 + 100, 14):
            d.line([(px2+6, line_y), (px2+78, line_y)], fill=GREY, width=1)

    # ── KID at desk — big figure ──
    kid_cx = W * 37 // 100
    Figure(kid_cx, desk_y, height=430, color=WHITE).draw(d, t, action="type")

    # Laptop / notebook on desk in front of kid
    d.rectangle([kid_cx - 60, desk_y - 28, kid_cx + 60, desk_y - 4],
                fill=(55,55,55), outline=BLACK, width=2)
    d.rectangle([kid_cx - 55, desk_y - 80, kid_cx + 55, desk_y - 30],
                fill=(38,38,38), outline=(75,75,75), width=2)
    d.text((kid_cx - 48, desk_y - 72), ">_ COPYING", fill=(0,210,80), font=get_font(16))

    # ── PIGEON QUEUE ──
    # Bigger pigeons, with a proper queue line
    pigeon_y = floor_y - 5
    queue_start = W * 54 // 100

    # Queue rope for birds
    d.line([(queue_start, pigeon_y - 28), (queue_start + 400, pigeon_y - 28)],
           fill=(150,115,55), width=3)

    for i in range(5):
        bx2 = queue_start + 18 + i * 80
        # Larger bird
        bob = math.sin((t + i * 0.25) * 2 * math.pi) * 7
        by2 = pigeon_y - 5 + bob
        # Body
        d.ellipse([bx2 - 28, by2 - 22, bx2 + 28, by2 + 22],
                  fill=(95,98,148), outline=BLACK, width=3)
        # Head
        d.ellipse([bx2 - 14, by2 - 52, bx2 + 14, by2 - 22],
                  fill=(95,98,148), outline=BLACK, width=3)
        # Beak
        d.polygon([(bx2 + 14, by2 - 40), (bx2 + 28, by2 - 37), (bx2 + 14, by2 - 34)],
                  fill=(255,185,0))
        # Feet
        d.ellipse([bx2 - 10, by2 + 18, bx2 + 10, by2 + 35],
                  fill=(208,188,48), outline=BLACK, width=2)
        # Seeds / coins in beak for first bird
        if i == 0:
            sc_bob = math.sin(t * 4 * math.pi) * 5
            d.ellipse([bx2 + 22, by2 - 55 + sc_bob, bx2 + 38, by2 - 42 + sc_bob],
                      fill=YELLOW, outline=BLACK, width=2)

    # ── PRICE SIGN on post ──
    sign_post_x = W * 58 // 100 + 30
    d.rectangle([sign_post_x - 4, floor_y - 275, sign_post_x + 4, floor_y],
                fill=(110,80,40))
    d.rectangle([sign_post_x - 148, floor_y - 275, sign_post_x + 152, floor_y - 118],
                fill=YELLOW, outline=BLACK, width=4)
    sf = get_font(34)
    d.text((sign_post_x - 138, floor_y - 268), "HOMEWORK",    fill=BLACK, font=sf)
    d.text((sign_post_x - 125, floor_y - 228), "4 SALE",      fill=(200,28,28), font=sf)
    d.text((sign_post_x - 138, floor_y - 188), "3 seeds OR",  fill=BLACK, font=get_font(28))
    d.text((sign_post_x - 120, floor_y - 152), "50 cents",    fill=BLACK, font=get_font(28))

    # Kid speech bubble
    if t > 0.25:
        speech_bubble(d, kid_cx, desk_y - 470, "Fresh batch!\nAll A+\nguaranteed!", get_font(42))

    return np.array(img)


def ep06(t):
    """Counterfeiting Monopoly Money — fast-food counter, customer with fake bills, confused cashier."""
    # Vibrant fast-food interior — yellow/red color scheme
    img = fill_gradient(Image.new("RGB",(W,H)), (255,200,0), (255,155,0))
    d   = ImageDraw.Draw(img)

    counter_y = H * 60 // 100

    # Back wall / kitchen area (red)
    d.rectangle([(0, 0), (W, counter_y + 45)], fill=(195,38,38))
    # Floor (checkered tile)
    d.rectangle([(0, counter_y + 45), (W, H)], fill=(240,235,225))
    tile_size = 88
    for ty in range(counter_y + 45, H, tile_size):
        for tx in range(0, W, tile_size):
            if ((tx // tile_size) + (ty // tile_size)) % 2 == 0:
                d.rectangle([tx, ty, tx + tile_size, ty + tile_size], fill=(215,210,200))

    # Counter surface
    d.rectangle([(0, counter_y), (W, counter_y + 48)], fill=(188,32,32))
    d.rectangle([(0, counter_y + 48), (W, counter_y + 90)], fill=(165,28,28))

    # Menu board (dark, illuminated)
    d.rectangle([W // 4 - 10, 48, W * 3 // 4 + 10, H // 3 + 10],
                fill=(18,18,18), outline=WHITE, width=4)
    # Menu board LED strip top
    d.rectangle([W // 4 - 10, 48, W * 3 // 4 + 10, 62], fill=(255,210,60))
    mf = get_font(38)
    d.text((W // 4 + 14, 68),  "BURGER   $8.99", fill=WHITE, font=mf)
    d.text((W // 4 + 14, 114), "FRIES    $4.99", fill=WHITE, font=mf)
    d.text((W // 4 + 14, 160), "SHAKE    $5.99", fill=WHITE, font=mf)
    d.text((W // 4 + 14, 206), "MEAL     $18.99", fill=YELLOW, font=mf)
    # "SPECIALS" badge
    d.ellipse([W * 3 // 4 - 95, H // 3 - 100, W * 3 // 4 + 8, H // 3 + 8],
              fill=(200,28,28))
    d.text((W * 3 // 4 - 82, H // 3 - 72), "SALE", fill=YELLOW, font=get_font(28))

    # Cash register on counter
    reg_x, reg_y = W // 2 - 60, counter_y - 115
    d.rectangle([reg_x, reg_y, reg_x + 120, counter_y], fill=(45,45,45), outline=BLACK, width=3)
    d.rectangle([reg_x + 8, reg_y + 8, reg_x + 112, reg_y + 62], fill=(20,180,20))
    d.text((reg_x + 14, reg_y + 18), "$8.99", fill=WHITE, font=get_font(26))
    d.rectangle([reg_x + 8, reg_y + 72, reg_x + 112, reg_y + 95], fill=(80,80,80))

    # ── CUSTOMER (left) — big, waving Monopoly money ──
    cust_cx = W // 4 - 20
    Figure(cust_cx, counter_y, height=450, color=WHITE).draw(d, t, action="hands_up")

    # Big stack of fake Monopoly bills waving in hand
    for i in range(4):
        bob = math.sin((t + i * 0.22) * 3 * math.pi) * 10
        bx2 = cust_cx + 50 + i * 32
        by2 = int(counter_y - 440 - i * 22 + bob)
        bw2, bh2 = 95, 48
        # Bill body (bright monopoly green)
        d.rectangle([bx2, by2, bx2 + bw2, by2 + bh2],
                    fill=(42,200,42), outline=(24,130,24), width=3)
        # Inner border
        d.rectangle([bx2 + 5, by2 + 5, bx2 + bw2 - 5, by2 + bh2 - 5],
                    outline=(24,130,24), width=2)
        d.text((bx2 + 8, by2 + 10), "$500", fill=WHITE, font=get_font(20))
        d.text((bx2 + 30, by2 + 30), "MONOPOLY", fill=WHITE, font=get_font(14))

    # ── CASHIER (right) — big, very confused ──
    cash_cx = W * 3 // 4 + 20
    Figure(cash_cx, counter_y, height=430, color=(198,198,198)).draw(d, t, action="confused", flip=True)

    # Cashier hat
    hat_cx, hat_cy = cash_cx, counter_y - 430 - 35
    d.rectangle([hat_cx - 52, hat_cy - 45, hat_cx + 52, hat_cy + 5],
                fill=(188,32,32), outline=BLACK, width=3)
    d.rectangle([hat_cx - 65, hat_cy + 5, hat_cx + 65, hat_cy + 22],
                fill=(188,32,32), outline=BLACK, width=2)
    d.text((hat_cx - 40, hat_cy - 35), "CREW", fill=YELLOW, font=get_font(22))

    # Question marks floating above cashier
    for i in range(3):
        qm_bob = math.sin((t + i * 0.38) * 3 * math.pi) * 20
        qm_x = cash_cx - 80 + i * 60
        qm_y = int(counter_y - 520 + qm_bob)
        d.text((qm_x, qm_y), "?", fill=YELLOW, font=get_font(42))

    # Speech bubbles
    if t > 0.18:
        speech_bubble(d, cust_cx - 30, counter_y - 490,
                      "It IS real\nmoney. I\nchecked.", get_font(44))
    if t > 0.52:
        speech_bubble(d, cash_cx + 20, counter_y - 470,
                      "Sir please\nleave.", get_font(42), bg=(255,218,218))

    return np.array(img)


def ep07(t):
    """Robin Hood Gets Confused — forest, rich vs poor, money arcs to wrong target."""
    # Forest gradient — deep greens
    img = fill_gradient(Image.new("RGB",(W,H)), (48,105,48), (32,75,32))
    d   = ImageDraw.Draw(img)

    gy = H * 65 // 100

    # Ground
    d.rectangle([(0, gy), (W, H)], fill=(44,85,38))
    for fx in range(0, W, 85):
        d.line([(fx, gy), (fx, H)], fill=(40,78,34), width=2)

    # Background trees (far, dark)
    for tx in [30, 155, 295, 445, 598, 688, 798, 918, 1025]:
        draw_tree(d, tx, gy, size=int(155 + (tx % 40)), tc=(28,105,28))

    # Mid-ground trees (bigger)
    for tx in [45, 188, 848, 968, 1058]:
        draw_tree(d, tx, gy, size=190, tc=(35,128,35))

    # Sunbeams through canopy
    for ray_i in range(4):
        rx = 180 + ray_i * 200
        for ry in range(H // 6, gy, 60):
            alpha = 0.3 + 0.2 * math.sin((t + ray_i * 0.25) * 2 * math.pi)
            beam_w = 12 + ray_i * 4
            beam_color = (int(255 * alpha), int(248 * alpha), int(180 * alpha))
            d.line([(rx - beam_w, ry), (rx + beam_w, ry + 58)], fill=beam_color, width=3)

    # ── POOR FIGURE (left) — tired, ragged ──
    poor_cx = W // 5
    Figure(poor_cx, gy, height=390, color=GREY).draw(d, t, action="idle")
    # Patched hat
    d.ellipse([poor_cx - 38, gy - 390 - 52, poor_cx + 38, gy - 390 - 10],
              fill=(100,90,80), outline=BLACK, width=3)
    # Empty coin purse
    d.ellipse([poor_cx + 58, gy - 220, poor_cx + 92, gy - 188],
              fill=(148,128,90), outline=BLACK, width=2)
    d.text((poor_cx + 62, gy - 215), "∅", fill=BLACK, font=get_font(24))
    # Label
    d.text((poor_cx - 62, gy + 8), "PEASANT", fill=(200,200,200), font=get_font(24))

    # ── ROBIN HOOD (center) — confused, green costume ──
    robin_cx = W // 2
    Figure(robin_cx, gy, height=460, color=(38,178,38)).draw(d, t, action="confused")
    # Pointed hood
    hood_cx, hood_cy = robin_cx, gy - 460 - 30
    d.polygon([(hood_cx, hood_cy - 75),
               (hood_cx - 65, hood_cy + 10),
               (hood_cx + 65, hood_cy + 10)],
              fill=(28,145,28), outline=BLACK, width=3)
    # Feather in hood
    d.line([(hood_cx + 35, hood_cy - 30),
            (hood_cx + 55, hood_cy - 65),
            (hood_cx + 48, hood_cy - 85)], fill=(210,190,40), width=4)
    # Quiver on back
    d.rectangle([robin_cx + 22, gy - 350, robin_cx + 48, gy - 200],
                fill=(138,95,45), outline=BLACK, width=2)
    for arr_i in range(3):
        d.line([(robin_cx + 28 + arr_i * 8, gy - 345),
                (robin_cx + 28 + arr_i * 8, gy - 205)], fill=(175,148,68), width=3)

    # ── RICH FIGURE (right) — top hat, gleeful ──
    rich_cx = W * 4 // 5
    Figure(rich_cx, gy, height=430, color=(252,218,95)).draw(d, t, action="cheer")
    # Top hat
    hat_cx, hat_cy = rich_cx, gy - 430 - 30
    d.rectangle([hat_cx - 44, hat_cy - 75, hat_cx + 44, hat_cy + 5],
                fill=BLACK, outline=WHITE, width=3)
    d.rectangle([hat_cx - 62, hat_cy + 5, hat_cx + 62, hat_cy + 22],
                fill=BLACK, outline=WHITE, width=3)
    d.rectangle([hat_cx - 30, hat_cy - 50, hat_cx + 30, hat_cy - 32],
                fill=(35,35,35))
    # Monocle
    d.ellipse([rich_cx + 22, gy - 430 + 60, rich_cx + 52, gy - 430 + 90],
              outline=YELLOW, width=4)
    # Money bags around rich guy
    for mb_i, (mb_dx, mb_dy) in enumerate([(-75, -105), (65, -88), (-55, -55)]):
        mb_bob = math.sin((t + mb_i * 0.3) * 2.5 * math.pi) * 12
        mb_x2, mb_y2 = rich_cx + mb_dx, int(gy + mb_dy + mb_bob)
        d.ellipse([mb_x2 - 22, mb_y2 - 22, mb_x2 + 22, mb_y2 + 22],
                  fill=(205,175,45), outline=BLACK, width=3)
        d.text((mb_x2 - 10, mb_y2 - 12), "$", fill=BLACK, font=get_font(22))
    # Label
    d.text((rich_cx - 50, gy + 8), "RICHEST GUY", fill=YELLOW, font=get_font(22))

    # ── MONEY BAG arcing from Robin Hood toward rich guy ──
    # Parabolic arc: starts near Robin, ends near Rich
    arc_frac = t % 1.0
    start_x, start_y = float(robin_cx), float(gy - 250)
    end_x,   end_y   = float(rich_cx),  float(gy - 200)
    arc_x = int(start_x + (end_x - start_x) * arc_frac)
    arc_y = int(start_y + (end_y - start_y) * arc_frac - 200 * math.sin(arc_frac * math.pi))
    # Draw bag
    d.ellipse([arc_x - 24, arc_y - 24, arc_x + 24, arc_y + 24],
              fill=(208,178,48), outline=BLACK, width=3)
    d.line([(arc_x, arc_y - 24), (arc_x, arc_y - 40)], fill=BLACK, width=3)
    d.ellipse([arc_x - 8, arc_y - 46, arc_x + 8, arc_y - 38], fill=(208,178,48), outline=BLACK, width=2)
    d.text((arc_x - 12, arc_y - 14), "$", fill=BLACK, font=get_font(22))

    # Speech bubble from Robin Hood
    if t > 0.28:
        speech_bubble(d, robin_cx, gy - 508,
                      "I'm...\nhelping?", get_font(48), bg=(255,255,200))

    return np.array(img)


def ep08(t):
    """Hacker surrounded by floating laptops, dark matrix aesthetic."""
    # Very dark gradient — deep midnight
    img = fill_gradient(Image.new("RGB",(W,H)), (5,6,22), (14,18,45))
    d   = ImageDraw.Draw(img)

    # Matrix rain columns (animated green characters)
    char_pool = "01ABCDEF><{}[]"
    for col_i in range(16):
        cx2 = 35 + col_i * 62
        col_speed = 0.8 + col_i * 0.055
        for row_i in range(22):
            phase = (t * col_speed * 3 + row_i * 0.12 + col_i * 0.31) % 1.0
            brightness = max(0, 1 - phase * 3.5)
            if brightness > 0.05:
                char_idx = (col_i * 7 + row_i * 3 + int(t * 12)) % len(char_pool)
                green_val = int(brightness * 220)
                char_y = int(phase * H) + row_i * 62
                if 0 <= char_y < H:
                    d.text((cx2, char_y), char_pool[char_idx],
                           fill=(0, green_val, int(green_val * 0.28)), font=get_font(22))

    # Floor glow (subtle)
    d.rectangle([(0, H * 74 // 100), (W, H)], fill=(8,18,12))

    # ── FLOATING LAPTOPS orbiting/surrounding hacker ──
    center_x, center_y = W // 2, H * 74 // 100 - 280
    for i in range(10):
        orbit_r   = 260 + (i % 3) * 80
        orbit_spd = 0.4 + i * 0.08
        angle     = (t * orbit_spd * 2 * math.pi + i * (2 * math.pi / 10))
        lx2 = int(center_x + orbit_r * math.cos(angle))
        ly2 = int(center_y + orbit_r * math.sin(angle) * 0.45)  # flattened orbit
        lw2, lh2 = 115, 75
        # Laptop base
        d.rectangle([lx2, ly2 + lh2 - 6, lx2 + lw2, ly2 + lh2 + 8],
                    fill=(55,55,55), outline=BLACK, width=2)
        # Screen
        d.rectangle([lx2, ly2, lx2 + lw2, ly2 + lh2],
                    fill=(32,38,32), outline=(68,85,68), width=2)
        # Screen content — green text blink
        blink_phase = 0.5 + 0.5 * math.sin((t * 5 + i * 0.6) * math.pi)
        if blink_phase > 0.45:
            d.text((lx2 + 6, ly2 + 6),  ">_ ACCESS", fill=(0,205,75), font=get_font(15))
            d.text((lx2 + 6, ly2 + 28), "GRANTED",   fill=(0,205,75), font=get_font(15))
        # Screen glow halo
        for glow_r in range(3):
            glow_alpha = int((0.3 - glow_r * 0.08) * 80)
            d.rectangle([lx2 - glow_r * 3, ly2 - glow_r * 2,
                         lx2 + lw2 + glow_r * 3, ly2 + lh2 + glow_r * 2],
                        outline=(0, int(glow_alpha * 2.5), glow_alpha))

    # ── MAIN HACKER — very big, neon green ──
    hacker_cy = H * 74 // 100
    Figure(W // 2, hacker_cy, height=470, color=(0,210,80)).draw(d, t, action="type")

    # Hoodie silhouette for hacker
    hh_cx = W // 2
    hh_top = hacker_cy - 470 + 25
    d.polygon([(hh_cx - 105, hacker_cy - 180),
               (hh_cx + 105, hacker_cy - 180),
               (hh_cx + 85,  hh_top + 45),
               (hh_cx - 85,  hh_top + 45)],
              fill=(18,28,18), outline=(0,120,45), width=3)

    # Central laptop / terminal in front of hacker
    lap_x, lap_y = W // 2 - 75, hacker_cy - 215
    d.rectangle([lap_x, lap_y + 88, lap_x + 150, lap_y + 100],
                fill=(60,60,60), outline=BLACK, width=2)
    d.rectangle([lap_x, lap_y, lap_x + 150, lap_y + 90],
                fill=(22,28,22), outline=(0,150,60), width=3)
    d.text((lap_x + 8, lap_y + 8),  ">_ MAINFRAME", fill=(0,200,75), font=get_font(16))
    d.text((lap_x + 8, lap_y + 32), "CONNECTING..", fill=(0,180,65), font=get_font(16))
    blink_cur = "|" if math.sin(t * 8 * math.pi) > 0 else " "
    d.text((lap_x + 8, lap_y + 56), f"DONE {blink_cur}",   fill=(0,255,90), font=get_font(16))

    # "I'M IN" speech bubble — big, dark themed
    if t > 0.12:
        speech_bubble(d, W // 2, hacker_cy - 510,
                      "I'M IN\n(sort of)", get_font(50),
                      bg=(8,38,8), fg=(0,255,80))

    # Scanlines overlay effect (subtle)
    for sl_y in range(0, H, 6):
        d.line([(0, sl_y), (W, sl_y)], fill=(0,0,0), width=1)

    return np.array(img)


def ep09(t):
    """Terrible Art Forgery — gallery, bad paintings, artist in beret, critic, bid counter."""
    # Gallery wall — warm off-white
    img = Image.new("RGB", (W, H), (245,242,236))
    d   = ImageDraw.Draw(img)

    floor_y = H * 65 // 100

    # Crown moulding
    d.rectangle([(0, 0),  (W, 18)],  fill=(125,105,85))
    d.rectangle([(0, 18), (W, 40)],  fill=(145,122,100))

    # Parquet floor
    d.rectangle([(0, floor_y), (W, H)], fill=(182,148,95))
    for fx in range(0, W, 55):
        d.line([(fx, floor_y), (fx, H)], fill=(168,135,85), width=2)
    for fy in range(floor_y, H, 38):
        d.line([(0, fy), (W, fy)], fill=(168,135,85), width=1)

    # Gallery rail (picture hanging rail)
    d.rectangle([(0, 88), (W, 100)], fill=(110,90,68))

    # ── THREE "TERRIBLE" PAINTINGS on wall ──
    painting_data = [
        (65,  H // 6, (252,178,98),  "MOONA LISA",  (0,0,0)),
        (W//2 - 130, H // 5 + 10, (148,178,255), "STARRY NITE", (0,0,0)),
        (W - 262, H // 6, (198,255,178), "SCREAM II", (0,0,0)),
    ]
    for i, (px2, py2, pcolor, title, tcol) in enumerate(painting_data):
        pw2, ph2 = 195, 245
        # Ornate frame
        d.rectangle([px2 - 12, py2 - 12, px2 + pw2 + 12, py2 + ph2 + 12],
                    fill=(165,132,62), outline=BLACK, width=2)
        d.rectangle([px2 - 6, py2 - 6, px2 + pw2 + 6, py2 + ph2 + 6],
                    fill=(185,152,78), outline=BLACK, width=2)
        # Canvas
        d.rectangle([px2, py2, px2 + pw2, py2 + ph2], fill=pcolor)
        # "Masterpiece" inside — terrible stick figure
        pf = Figure(px2 + pw2 // 2, py2 + ph2 - 10, height=135, color=BLACK, lw=3)
        pf.draw(d, (t + i * 0.33) % 1, action="idle")
        # Title plaque
        d.rectangle([px2, py2 + ph2, px2 + pw2, py2 + ph2 + 36],
                    fill=(155,128,62), outline=BLACK, width=2)
        d.text((px2 + 8, py2 + ph2 + 6), title, fill=WHITE, font=get_font(17))
        # Hanging wire from rail
        d.line([(px2 + pw2 // 3, 100), (px2 + pw2 // 2, py2 - 12)], fill=(110,95,70), width=2)
        d.line([(px2 + pw2 * 2 // 3, 100), (px2 + pw2 // 2, py2 - 12)], fill=(110,95,70), width=2)

    # ── ARTIST in beret — big, confident ──
    artist_cx = W // 2 + 28
    Figure(artist_cx, floor_y, height=460, color=WHITE).draw(d, t, action="point")
    # Beret
    bcx, bcy = artist_cx, floor_y - 460 - 28
    d.ellipse([bcx - 52, bcy - 24, bcx + 52, bcy + 24], fill=(75,55,155))
    d.ellipse([bcx + 24, bcy - 34, bcx + 38, bcy - 20], fill=(75,55,155))
    # Palette (artist holds it)
    pal_x, pal_y = artist_cx + 150, floor_y - 380
    d.ellipse([pal_x, pal_y, pal_x + 80, pal_y + 60], fill=(220,200,160), outline=BLACK, width=3)
    for dot_c, dot_x, dot_y in [(200,28,28),(28,200,28),(28,28,200),(200,200,28)]:
        d.ellipse([pal_x + dot_x, pal_y + dot_y,
                   pal_x + dot_x + 14, pal_y + dot_y + 14], fill=dot_c)
    # Paint brush
    d.line([(pal_x + 40, pal_y + 30), (pal_x + 100, pal_y - 18)],
           fill=(155,118,62), width=5)
    d.ellipse([pal_x + 96, pal_y - 24, pal_x + 108, pal_y - 12], fill=(200,28,28))

    # ── ART CRITIC — monocle, confused ──
    critic_cx = W * 4 // 5 + 10
    Figure(critic_cx, floor_y, height=420, color=(95,75,148)).draw(d, t, action="confused", flip=True)
    # Monocle on critic
    mon_cx, mon_cy = critic_cx + 28, floor_y - 420 + 60
    d.ellipse([mon_cx - 18, mon_cy - 18, mon_cx + 18, mon_cy + 18],
              outline=YELLOW, width=4)
    d.line([(mon_cx + 18, mon_cy + 10), (mon_cx + 35, mon_cy + 28)],
           fill=YELLOW, width=3)
    # Clipboard for critic
    d.rectangle([critic_cx - 115, floor_y - 320, critic_cx - 52, floor_y - 215],
                fill=WHITE, outline=BLACK, width=2)
    d.text((critic_cx - 110, floor_y - 315), "NOTES:", fill=BLACK, font=get_font(16))
    d.text((critic_cx - 108, floor_y - 292), "...bad?",  fill=(150,28,28), font=get_font(15))

    # ── AUCTION BID COUNTER ──
    af = get_font(46)
    d.rectangle([W // 10, H // 14, W * 9 // 10, H // 14 + 95],
                fill=YELLOW, outline=BLACK, width=4)
    price = int(48000 + math.sin(t * 3.5 * math.pi) * 9500)
    d.text((W // 10 + 18, H // 14 + 22), f"CURRENT BID: ${price:,}", fill=BLACK, font=af)
    # Bid up/down indicator
    bid_arrow = "↑" if math.sin(t * 3.5 * math.pi) > 0 else "↓"
    bid_col   = (28,155,28) if bid_arrow == "↑" else (200,28,28)
    d.text((W * 9 // 10 - 60, H // 14 + 16), bid_arrow, fill=bid_col, font=get_font(50))

    # Speech bubbles
    if t > 0.28:
        speech_bubble(d, artist_cx - 30, floor_y - 502,
                      "It's a\npowerful\nstatement.", get_font(44))

    return np.array(img)


def ep10(t):
    """Sandwich Smuggler at Airport — huge coat, TSA agent, sandwiches flying."""
    # Airport interior — clean, institutional
    img = fill_gradient(Image.new("RGB",(W,H)), (188,208,235), (155,185,220))
    d   = ImageDraw.Draw(img)

    gy = H * 65 // 100

    # Far background — departure board / windows
    for wx2, wy2 in [(55, 88), (195, 110), (580, 75), (720, 95), (880, 80)]:
        d.rectangle([wx2, wy2, wx2 + 145, wy2 + 145],
                    fill=(140,165,210), outline=(110,140,185), width=3)
        # Window pane divisions
        d.line([(wx2 + 72, wy2), (wx2 + 72, wy2 + 145)], fill=(110,140,185), width=2)
        d.line([(wx2, wy2 + 72), (wx2 + 145, wy2 + 72)], fill=(110,140,185), width=2)

    # Departure board
    d.rectangle([W // 4, 42, W * 3 // 4, 148], fill=(18,18,28), outline=WHITE, width=3)
    d.text((W // 4 + 14, 52),  "DEPARTURES", fill=YELLOW, font=get_font(28))
    d.text((W // 4 + 14, 90),  "NYC  10:45  ON TIME", fill=WHITE, font=get_font(22))
    d.text((W // 4 + 14, 118), "LAX  11:30  DELAYED", fill=(200,80,80), font=get_font(22))

    # Floor — polished tile
    d.rectangle([(0, gy), (W, H)], fill=(182,186,200))
    tile = 88
    for ty in range(gy, H, tile):
        for tx in range(0, W, tile):
            if ((tx // tile) + (ty // tile)) % 2 == 0:
                d.rectangle([tx, ty, tx + tile, ty + tile], fill=(170,174,188))
    # Floor shine
    d.line([(0, gy + 12), (W, gy + 12)], fill=(210,215,228), width=4)

    # ── SECURITY ARCH — big, intimidating ──
    arch_cx = W // 2
    arch_h  = 380
    arch_w  = 52
    d.rectangle([arch_cx - 145, gy - arch_h, arch_cx - 145 + arch_w, gy],
                fill=(55,58,80), outline=BLACK, width=3)
    d.rectangle([arch_cx + 145 - arch_w, gy - arch_h, arch_cx + 145, gy],
                fill=(55,58,80), outline=BLACK, width=3)
    d.rectangle([arch_cx - 145, gy - arch_h, arch_cx + 145, gy - arch_h + arch_w],
                fill=(55,58,80), outline=BLACK, width=3)
    # Security arch glow (red when triggered)
    glow_intensity = 0.5 + 0.5 * math.sin(t * 6 * math.pi)
    glow_r = int(200 * glow_intensity)
    d.rectangle([arch_cx - 140, gy - arch_h + arch_w, arch_cx + 140, gy],
                outline=(glow_r, 20, 20), width=4)
    # "BEEP" text
    if math.sin(t * 6 * math.pi) > 0.5:
        d.text((arch_cx - 48, gy - arch_h // 2), "BEEP!", fill=(255,40,40), font=get_font(38))
    # Conveyor belt through arch
    d.rectangle([arch_cx - 140, gy - 48, arch_cx + 140, gy - 22],
                fill=(60,60,65), outline=BLACK, width=2)
    belt_offset = int(t * 45) % 45
    for bx2 in range(arch_cx - 140, arch_cx + 140, 45):
        d.line([(bx2 + belt_offset, gy - 48), (bx2 + belt_offset, gy - 22)],
               fill=(48,48,52), width=2)

    # ── TSA AGENT (left) — big, alarmed ──
    tsa_cx = W // 4 - 10
    Figure(tsa_cx, gy, height=450, color=(28,58,28)).draw(d, t, action="hands_up", flip=True)
    # TSA cap
    tsa_hat_cx, tsa_hat_cy = tsa_cx, gy - 450 - 32
    d.rectangle([tsa_hat_cx - 52, tsa_hat_cy - 42, tsa_hat_cx + 52, tsa_hat_cy + 5],
                fill=(25,52,25), outline=BLACK, width=3)
    d.rectangle([tsa_hat_cx - 65, tsa_hat_cy + 5, tsa_hat_cx + 65, tsa_hat_cy + 20],
                fill=(25,52,25), outline=BLACK, width=2)
    d.text((tsa_hat_cx - 28, tsa_hat_cy - 32), "TSA", fill=YELLOW, font=get_font(24))
    # TSA badge
    d.rectangle([tsa_cx - 38, gy - 315, tsa_cx - 2, gy - 278],
                fill=YELLOW, outline=BLACK, width=2)
    d.text((tsa_cx - 35, gy - 312), "TSA", fill=BLACK, font=get_font(18))

    # ── SMUGGLER (right of arch) — huge trench coat ──
    smug_cx = W * 3 // 5 + 20
    Figure(smug_cx, gy, height=460, color=WHITE).draw(d, t, action="sneak")
    # GIANT trench coat (drawn over the figure)
    coat_top_y = gy - 460 + 38
    coat_bot_y = gy
    d.polygon([(smug_cx - 145, coat_bot_y),
               (smug_cx + 145, coat_bot_y),
               (smug_cx + 95,  coat_top_y),
               (smug_cx - 95,  coat_top_y)],
              fill=(72,52,32), outline=BLACK, width=4)
    # Coat lapels
    d.polygon([(smug_cx - 35, coat_top_y + 60),
               (smug_cx,      coat_top_y + 150),
               (smug_cx + 35, coat_top_y + 60)],
              fill=(88,65,40), outline=BLACK, width=2)
    # Coat buttons
    for btn_y in range(coat_top_y + 175, coat_bot_y - 40, 55):
        d.ellipse([smug_cx - 8, btn_y - 8, smug_cx + 8, btn_y + 8],
                  fill=(52,38,22), outline=BLACK, width=2)
    # Sweat drops
    for sw_i in range(3):
        sw_phase = (t * 2.5 + sw_i * 0.38) % 1.0
        sw_x = smug_cx + 95 + sw_i * 20
        sw_y = int(coat_top_y + 40 + sw_phase * 80)
        d.ellipse([sw_x - 6, sw_y - 6, sw_x + 6, sw_y + 6], fill=(120,190,255))

    # ── SANDWICHES flying out of coat ──
    for i in range(10):
        # Each sandwich follows a different arc / spin out of the coat
        angle   = (i / 10) * math.pi * 2 + t * 2.2 * math.pi + i * 0.6
        orb_r_x = 110 + (i % 3) * 45
        orb_r_y = 65  + (i % 4) * 30
        sx2 = int(smug_cx + orb_r_x * math.cos(angle))
        sy2 = int(gy - 145 + orb_r_y * math.sin(angle))
        # Sandwich layers (bread / filling / bread)
        sandwich_w, sandwich_h = 46, 12
        d.rounded_rectangle([sx2 - sandwich_w, sy2 - sandwich_h * 2,
                              sx2 + sandwich_w, sy2 - sandwich_h],
                            radius=4, fill=(208,168,95), outline=(155,120,60), width=2)
        d.rounded_rectangle([sx2 - sandwich_w + 3, sy2 - sandwich_h,
                              sx2 + sandwich_w - 3, sy2],
                            radius=2, fill=(75,195,75))
        d.rounded_rectangle([sx2 - sandwich_w, sy2,
                              sx2 + sandwich_w, sy2 + sandwich_h],
                            radius=4, fill=(208,168,95), outline=(155,120,60), width=2)

    # Speech bubbles
    if t > 0.22:
        speech_bubble(d, tsa_cx, gy - 496,
                      "SIR. How\nmany is\nTHAT?!", get_font(44), bg=(255,218,218))
    if t > 0.58:
        speech_bubble(d, smug_cx, gy - 512,
                      "Forty\nseven.", get_font(46))

    return np.array(img)


# Map episode id → renderer
RENDERERS = {1:ep01, 2:ep02, 3:ep03, 4:ep04, 5:ep05,
             6:ep06, 7:ep07, 8:ep08, 9:ep09, 10:ep10}

def get_renderer(episode):
    r = RENDERERS.get(episode["id"])
    if r:
        return lambda t: r(t)
    # Generic fallback for any future episodes
    def _generic(t):
        img = fill_gradient(Image.new("RGB",(W,H)),(50,50,100),(100,80,150))
        d   = ImageDraw.Draw(img)
        gy  = H*65//100
        d.rectangle([(0,gy),(W,H)], fill=(60,90,60))
        Figure(W//2, gy, height=220).draw(d, t, action="cheer")
        Figure(W//4, gy, height=180, color=GREY).draw(d, t, action="confused", flip=True)
        centered_text(d, episode["title"].upper(), H//4, get_font(44), YELLOW)
        dollar_pop(d, [(150,H//3),(800,H//3-30)], t, get_font(60))
        if t > 0.3:
            speech_bubble(d, W//2, gy-250, "Trust me,\nit's legal.", get_font(36))
        return np.array(img)
    return _generic

# ── Title / End cards ──────────────────────────────────────────────────────────

def render_title_frame(episode):
    img = Image.new("RGB",(W,H), DARK)
    d   = ImageDraw.Draw(img)
    d.rectangle([(0,0),(W,14)], fill=YELLOW)
    d.rectangle([(0,H-14),(W,H)], fill=YELLOW)
    centered_text(d, "DEFINITELY", H//4-80,  get_font(96), YELLOW)
    centered_text(d, "ILLEGAL",    H//4+30,  get_font(96), YELLOW)
    centered_text(d, f"Episode {episode['id']}", H//4+160, get_font(38), GREY, shadow=False)
    y = H//2 - 20
    for line in textwrap.wrap(episode["title"], width=22):
        centered_text(d, line, y, get_font(52), WHITE)
        y += 72
    y += 30
    for line in textwrap.wrap(episode["tagline"], width=42):
        centered_text(d, line, y, get_font(32), GREY, shadow=False)
        y += 46
    return np.array(img)

def render_end_frame():
    img = Image.new("RGB",(W,H), DARK)
    d   = ImageDraw.Draw(img)
    d.rectangle([(0,0),(W,14)], fill=YELLOW)
    d.rectangle([(0,H-14),(W,H)], fill=YELLOW)
    centered_text(d, "DEFINITELY",             H//3-60,  get_font(96), YELLOW)
    centered_text(d, "ILLEGAL",                H//3+50,  get_font(96), YELLOW)
    centered_text(d, "New episode every week.", H//2+80,  get_font(50), WHITE)
    centered_text(d, "Subscribe before it's too late.", H//2+160, get_font(36), GREY, shadow=False)
    return np.array(img)

# ── Audio ──────────────────────────────────────────────────────────────────────

# Frank, casual American male narrator. Slight speed-up + lower pitch = blunt delivery.
MALE_VOICE = os.environ.get("VOICE", "en-US-GuyNeural")
VOICE_RATE  = "+10%"
VOICE_PITCH = "-3Hz"

def _edge_tts(text, out_path):
    """Natural neural male voice via Microsoft Edge TTS (free, no API key)."""
    import asyncio, edge_tts
    async def _run():
        comm = edge_tts.Communicate(text, MALE_VOICE, rate=VOICE_RATE, pitch=VOICE_PITCH)
        await comm.save(str(out_path))
    asyncio.run(_run())

def generate_voiceover(text, out_path):
    print(f"  [tts] Generating voiceover ({MALE_VOICE})…")
    try:
        _edge_tts(text, out_path)
        print("  [tts] ✓ narration.mp3 (edge-tts male voice)")
    except Exception as e:
        print(f"  [tts] edge-tts failed ({e}); falling back to gTTS")
        gTTS(text=text, lang="en", tld="com", slow=False).save(str(out_path))
        print("  [tts] ✓ narration.mp3 (gTTS fallback)")
    return out_path

def generate_tone_music(duration, out_path):
    sr  = 44100
    n   = int(sr * duration)
    t   = np.linspace(0, duration, n, endpoint=False)
    beat  = 0.5
    freqs = [130.8, 110.0, 87.3, 98.0]
    ci    = (t / beat).astype(int) % len(freqs)
    bass  = 0.35 * np.sin(2*np.pi * np.array([freqs[i] for i in ci]) * t)
    env   = np.zeros(n)
    for i in range(int(duration/beat)):
        if i % 2 == 1:
            s = int(i*beat*sr); e = min(s+int(0.05*sr), n)
            env[s:e] = np.linspace(0.5, 0, e-s)
    snare = env * np.random.uniform(-1, 1, n)
    audio = np.clip(bass+snare, -1, 1)
    with wave.open(str(out_path), "w") as wf:
        wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(sr)
        wf.writeframes((audio*32767).astype(np.int16).tobytes())
    print(f"  [mus] ✓ music.wav ({duration:.1f}s)")
    return out_path

# ── Video assembly ─────────────────────────────────────────────────────────────

def assemble_video(episode, voiceover_path, music_path, out_path):
    print("  [vid] Assembling stick figure animation…")
    from moviepy.editor import afx

    vo   = AudioFileClip(str(voiceover_path))
    vdur = vo.duration
    total_dur = 3 + vdur + 3

    mu = AudioFileClip(str(music_path)).volumex(0.18)
    if mu.duration < total_dur:
        mu = mu.fx(afx.audio_loop, duration=total_dur)
    mu = mu.subclip(0, total_dur)

    # Word-by-word karaoke captions (1-2 words at a time), TikTok style
    words     = episode["narration"].split()
    group     = 2
    chunks    = [" ".join(words[i:i+group]) for i in range(0, len(words), group)] or [""]
    chunk_dur = vdur / len(chunks)
    cap_font  = get_font(104)
    stroke    = 9
    scene_r   = get_renderer(episode)

    def render_frame(t):
        frame = Image.fromarray(scene_r(t / vdur))
        d = ImageDraw.Draw(frame, "RGBA")
        idx  = min(int(t/chunk_dur), len(chunks)-1)
        word = chunks[idx].upper()
        # subtle "pop" scale at the start of each word for liveliness
        local = (t - idx*chunk_dur) / chunk_dur
        scale = 1.0 + 0.12*max(0.0, 1 - local*6)
        fnt   = get_font(int(104*scale))
        bb = d.textbbox((0,0), word, font=fnt, stroke_width=stroke)
        x  = (W - (bb[2]-bb[0])) // 2
        y  = int(H*0.66)
        # thick black outline + bright yellow fill = the reference caption look
        d.text((x, y), word, font=fnt, fill=YELLOW, stroke_width=stroke, stroke_fill=BLACK)
        return np.array(frame.convert("RGB"))

    title_clip = ImageClip(render_title_frame(episode), duration=3).set_fps(FPS)
    scene_clip = VideoClip(render_frame, duration=vdur).set_fps(FPS).set_audio(vo)
    end_clip   = ImageClip(render_end_frame(), duration=3).set_fps(FPS)

    video = concatenate_videoclips([title_clip, scene_clip, end_clip], method="compose")
    video = video.set_audio(CompositeAudioClip([video.audio, mu]))
    video.write_videofile(str(out_path), fps=FPS, codec="libx264", audio_codec="aac",
                          temp_audiofile=str(out_path.parent/"tmp_audio.m4a"),
                          remove_temp=True, logger=None, threads=4)
    print("  [vid] ✓ video.mp4 saved")
    return out_path

# ── Pipeline ───────────────────────────────────────────────────────────────────

def run_episode(episode):
    ep_id = episode["id"]
    out   = OUTPUT_DIR / f"ep{ep_id:02d}"
    out.mkdir(parents=True, exist_ok=True)
    print(f"\n{'='*60}\n  {episode['tagline']}\n{'='*60}")

    vo      = generate_voiceover(episode["narration"], out/"narration.mp3")
    vo_dur  = AudioFileClip(str(vo)).duration
    music   = generate_tone_music(3 + vo_dur + 3 + 2, out/"music.wav")
    video   = assemble_video(episode, vo, music, out/"video.mp4")

    result = {"generated_at": datetime.utcnow().isoformat(),
               "video": str(video), "voiceover": str(vo)}
    print(f"\n✅  Episode {ep_id} complete → {out}/video.mp4")
    return result

# ── CLI ────────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--episode", type=int)
    ap.add_argument("--all",  action="store_true")
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args()
    episodes = load_episodes()

    if args.list:
        status = load_status()
        for ep in episodes:
            print(f"{'✅' if str(ep['id']) in status else '⏳'}  Ep {ep['id']:02d}: {ep['title']}")
        return

    targets = (episodes if args.all else
               [e for e in episodes if e["id"] == args.episode] if args.episode else
               [next_episode(episodes, load_status())])
    if not targets or targets[0] is None:
        print("All episodes generated!" if not args.episode else f"Episode {args.episode} not found.")
        return

    status = load_status()
    for ep in targets:
        result = run_episode(ep)
        status[str(ep["id"])] = result
        save_status(status)

if __name__ == "__main__":
    main()
