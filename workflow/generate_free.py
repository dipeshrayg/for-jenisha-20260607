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

class Figure:
    """Animated stick figure. Actions: idle walk wave cheer pour point hands_up type confused."""

    def __init__(self, cx, cy_feet, height=200, color=WHITE, lw=5):
        self.cx, self.cy, self.h, self.color, self.lw = cx, cy_feet, height, color, lw

    def draw(self, draw, t, action="idle", flip=False):
        cx, cy, h, c, lw = self.cx, self.cy, self.h, self.color, self.lw

        # --- joint angles (0 = hanging straight down, positive = swings right) ---
        if action == "walk":
            p = t * 6 * math.pi
            ll, lr = math.sin(p)*35, -math.sin(p)*35
            al, ar = -math.sin(p)*40,  math.sin(p)*40
            bob = abs(math.sin(p)) * h * 0.02
        elif action == "wave":
            p = t * 4 * math.pi
            ll, lr, al, ar = 5, -5, math.sin(p)*50 - 70, 30
            bob = 0
        elif action == "cheer":
            p = t * 4 * math.pi
            ll, lr = math.sin(p)*15, -math.sin(p)*15
            al = math.sin(p)*30 - 100
            ar = -math.sin(p)*30 + 100
            bob = abs(math.sin(p)) * h * 0.03
        elif action == "pour":
            p = t * 2 * math.pi
            ll, lr = -5, 5
            al = -70 + math.sin(p)*10
            ar = math.sin(p)*15 + 10
            bob = 0
        elif action == "point":
            p = t * 2 * math.pi
            ll, lr, al = 0, 0, -30
            ar = -55 + math.sin(p)*10
            bob = 0
        elif action == "hands_up":
            p = t * 3 * math.pi
            ll, lr = 0, 0
            al = -90 + math.sin(p)*15
            ar = 90 - math.sin(p)*15
            bob = 0
        elif action == "type":
            p = t * 8 * math.pi
            ll, lr = 5, -5
            al = -40 + math.sin(p)*20
            ar = 40 - math.sin(p)*20
            bob = math.sin(p*0.5) * h * 0.01
        elif action == "confused":
            p = t * 3 * math.pi
            ll, lr = 10, -10
            al, ar = -20, -65 + math.sin(p)*20
            bob = 0
        elif action == "sneak":
            p = t * 5 * math.pi
            ll, lr = math.sin(p)*25, -math.sin(p)*25
            al, ar = math.sin(p)*20 - 40, -math.sin(p)*20 + 40
            bob = 0
            cy = cy - h * 0.08  # crouch
        else:  # idle / breathe
            p = t * 2 * math.pi
            ll, lr = 0, 0
            al = math.sin(p)*8 - 25
            ar = -math.sin(p)*8 + 25
            bob = math.sin(p) * h * 0.01

        if flip:
            ll, lr, al, ar = -lr, -ll, -ar, -al

        cy_adj = cy - bob
        head_r   = h * 0.13
        head_cy  = cy_adj - h + head_r
        neck_y   = cy_adj - h + head_r * 2.0
        shldr_y  = cy_adj - h * 0.72
        hip_y    = cy_adj - h * 0.43

        # Head
        draw.ellipse([cx-head_r, head_cy-head_r, cx+head_r, head_cy+head_r],
                     outline=c, width=lw)
        # Eyes
        ey, er = head_cy - head_r*0.1, max(2, lw//2)
        draw.ellipse([cx-head_r*.4-er, ey-er, cx-head_r*.4+er, ey+er], fill=c)
        draw.ellipse([cx+head_r*.4-er, ey-er, cx+head_r*.4+er, ey+er], fill=c)
        # Body
        draw.line([(int(cx), int(neck_y)), (int(cx), int(hip_y))], fill=c, width=lw)

        # Arms
        alen = h * 0.30
        for angle in (al, ar):
            ex, ey2 = polar(cx, shldr_y, alen, angle)
            draw.line([(int(cx), int(shldr_y)), (int(ex), int(ey2))], fill=c, width=lw)

        # Legs (two segments: thigh + shin)
        llen = h * 0.47
        for ang, ox in ((ll, -h*0.04), (lr, h*0.04)):
            knee = polar(cx+ox, hip_y, llen*0.55, ang)
            foot = polar(knee[0], knee[1], llen*0.50, ang*0.5)
            draw.line([(int(cx+ox), int(hip_y)), (int(knee[0]), int(knee[1]))], fill=c, width=lw)
            draw.line([(int(knee[0]), int(knee[1])), (int(foot[0]), int(foot[1]))], fill=c, width=lw)

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
    """Selling Premium Mountain Air"""
    img = fill_gradient(Image.new("RGB",(W,H)), (100,180,255), (210,235,255))
    d   = ImageDraw.Draw(img)
    gy  = H*68//100
    draw_mountain(d, W//2, H//4, gy)
    draw_ground(d, gy, (70,110,70))
    for cx,cy,r in [(180,200,65),(720,155,85),(930,290,55)]:
        draw_cloud(d, cx, cy, r)
    for tx in [80, 880, 1010]:
        draw_tree(d, tx, gy)

    # Criminal on mountain top
    fig = Figure(W//2, H//4+30, height=230)
    fig.draw(d, t, action="pour")

    # Jar being held out
    jx, jy = W//2+90, H//4-115
    d.rectangle([jx, jy, jx+45, jy+65], outline=WHITE, width=3, fill=(190,235,255))
    d.text((jx+5, jy+10), "AIR", fill=BLACK, font=get_font(18))

    # Customer queue at base
    for i, xp in enumerate([200, 340, 160, 460]):
        Figure(xp, gy, height=160, color=(220,220,220)).draw(d,(t+i*.25)%1, action="idle")

    # $ signs
    dollar_pop(d, [(300,H//2),(740,H//2-40),(500,H*42//100)], t, get_font(60))

    # Speech bubble
    bfont = get_font(36)
    if t > 0.25:
        speech_bubble(d, W//2, H//4-110, "$99 a jar!\nFresh!\nPremium!", bfont)

    return np.array(img)


def ep02(t):
    """Neighborhood Toll Booth"""
    img = fill_gradient(Image.new("RGB",(W,H)), (150,195,230), (100,160,200))
    d   = ImageDraw.Draw(img)
    gy  = H*58//100
    draw_ground(d, gy-55, (80,140,70))  # grass
    d.rectangle([(0,gy),(W,H)], fill=(75,75,75))  # road
    # Road markings (animated)
    for x in range(-120, W+120, 120):
        ox = int(t*120)%120
        d.rectangle([x+ox-55, gy-8, x+ox-15, gy+8], fill=YELLOW)

    for tx in [60, 170, 840, 1000]:
        draw_tree(d, tx, gy-55)

    # Toll booth box
    bx, by = W//2-90, gy-220
    d.rectangle([bx, by, bx+180, gy-60], fill=(240,220,175), outline=BLACK, width=3)
    d.rectangle([bx+30, by+20, bx+150, by+105], fill=(175,220,255), outline=BLACK, width=2)

    # Animated barrier arm
    pivot_x, pivot_y = bx+180, gy-85
    arm_angle = math.sin(t*2*math.pi)*0.35 + 0.05
    ax2 = int(pivot_x + 300*math.cos(arm_angle))
    ay2 = int(pivot_y + 300*math.sin(arm_angle))
    d.line([(pivot_x, pivot_y),(ax2, ay2)], fill=(230,50,50), width=9)
    d.ellipse([pivot_x-8, pivot_y-8, pivot_x+8, pivot_y+8], fill=(200,30,30))

    # Operator figure
    Figure(W//2, gy-60, height=175).draw(d, t, action="wave")

    # Moving car
    cx = int(W*0.85 - (t%1)*W*0.85)
    draw_simple_car(d, cx, gy)

    # Sign
    sf = get_font(34)
    d.rectangle([W//2-130, H//6, W//2+130, H//6+110], fill=YELLOW, outline=BLACK, width=3)
    d.text((W//2-100, H//6+10), "TOLL: $2.00", fill=BLACK, font=sf)
    d.text((W//2-115, H//6+55), "EXACT CHANGE", fill=BLACK, font=sf)
    d.text((W//2-85,  H//6+82), "ONLY!!", fill=(200,30,30), font=sf)

    dollar_pop(d, [(120,H//3),(880,H//3),(540,H//4)], t, get_font(55))
    return np.array(img)


def ep03(t):
    """Charging Cats Rent"""
    img = Image.new("RGB",(W,H),(240,222,185))
    d   = ImageDraw.Draw(img)
    d.rectangle([(0,H*65//100),(W,H)], fill=(160,125,85))  # floor
    d.rectangle([(0,0),(W,80)], fill=(100,70,50))  # ceiling/baseboard

    # Couch
    cy2 = H*60//100
    d.rounded_rectangle([W//5, cy2, W*4//5, cy2+170], radius=22,
                        fill=(180,100,80), outline=BLACK, width=3)
    d.rounded_rectangle([W//5, cy2-55, W*4//5, cy2+22], radius=12,
                        fill=(205,125,100), outline=BLACK, width=3)

    # Landlord with lease
    landlord = Figure(W//4-30, cy2-5, height=210)
    landlord.draw(d, t, action="point")

    # Lease document
    px, py = W//4+75, cy2-175
    d.rectangle([px,py,px+90,py+115], fill=WHITE, outline=BLACK, width=2)
    tf = get_font(20)
    d.text((px+10,py+8), "LEASE", fill=BLACK, font=tf)
    for ly in [45,62,79,96]:
        d.line([(px+5,py+ly),(px+85,py+ly)], fill=GREY, width=2)

    # Cat on couch
    draw_cat(d, W*2//3, cy2-28, t)

    # Speech bubbles
    bfont = get_font(34)
    if t > 0.2:
        speech_bubble(d, W//4-30, cy2-235, "Rent is\ndue! Sign\nthe lease!", bfont)
    if t > 0.5:
        speech_bubble(d, W*2//3, cy2-180, "...no.", get_font(38), bg=(255,240,240))

    dollar_pop(d, [(90,H//3),(870,H//3+40)], t, get_font(55))
    return np.array(img)


def ep04(t):
    """Actual Pyramid Scheme"""
    img = fill_gradient(Image.new("RGB",(W,H)), (18,18,45), (35,35,70))
    d   = ImageDraw.Draw(img)

    # Stars
    for i in range(35):
        sx, sy = (i*157+80)%W, (i*113+40)%(H//2)
        br = 0.5 + 0.5*math.sin((t+i*0.1)*5*math.pi)
        r  = max(1, int(br*3))
        d.ellipse([sx-r,sy-r,sx+r,sy+r], fill=WHITE)

    # Whiteboard
    wb_x, wb_y = W//2-10, H//5
    d.rectangle([wb_x, wb_y, wb_x+420, wb_y+370], fill=(240,240,240), outline=BLACK, width=3)

    # Pyramid diagram on board
    pc, pb, pt = wb_x+210, wb_y+355, wb_y+90
    d.polygon([(pc,pt),(pc-160,pb),(pc+160,pb)], fill=(225,195,195), outline=(200,50,50), width=3)
    for lv in [0.32, 0.62]:
        d.line([(pc-160*lv, pb-(pb-pt)*lv),(pc+160*lv, pb-(pb-pt)*lv)],
               fill=(200,50,50), width=2)
    tf = get_font(24)
    d.text((pc-22, pt+8),  "YOU", fill=BLACK, font=tf)
    d.text((pc-45, pb-85), "FRIENDS", fill=BLACK, font=tf)
    d.text((pc-92, pb-35), "FRIEND'S FRIENDS", fill=BLACK, font=tf)

    # Presenter (yellow, excited)
    Figure(W//5, H*62//100, height=230, color=YELLOW).draw(d, t, action="point")

    # Audience
    for i, ax in enumerate([100,240,800,920,1010]):
        Figure(ax, H*62//100, height=130, color=GREY).draw(d, (t+i*.2)%1, action="idle")

    # Floating tiny pyramids
    for i,(px2,py2) in enumerate([(140,H//5),(810,H//4),(890,H*3//8)]):
        bob = math.sin((t+i*.4)*2*math.pi)*18
        ppts = [(px2, int(py2+bob)), (px2-28,int(py2+58+bob)), (px2+28,int(py2+58+bob))]
        d.polygon(ppts, fill=YELLOW, outline=BLACK, width=2)

    bfont = get_font(34)
    if t > 0.3:
        speech_bubble(d, W//5, H*62//100 - 240,
                      "Buy a pyramid!\nSell pyramids!\nGet rich!", bfont)
    return np.array(img)


def ep05(t):
    """Selling Homework to Birds"""
    img = fill_gradient(Image.new("RGB",(W,H)), (255,252,220), (235,228,195))
    d   = ImageDraw.Draw(img)
    d.rectangle([(0,H*68//100),(W,H)], fill=(195,180,155))

    # Desk
    gy = H*63//100
    d.rectangle([W//8, gy, W*9//16, gy+32], fill=(180,130,80), outline=BLACK, width=2)
    for legx in [W//8+22, W*9//16-45]:
        d.rectangle([legx, gy+32, legx+22, H*68//100], fill=(155,100,60), width=2)

    # Kid
    Figure(W//3, gy, height=195).draw(d, t, action="type")

    # Papers on desk
    for i,(px2,py2) in enumerate([(W//5, gy-48),(W//5+65,gy-35),(W//5-35,gy-55)]):
        d.rectangle([px2,py2,px2+72,py2+90], fill=WHITE, outline=BLACK, width=1)
        d.text((px2+5,py2+6), "MATH\nHOMEWORK", fill=BLACK, font=get_font(16))

    # Bird queue
    for i in range(5):
        draw_bird(d, W*5//8 + i*85, H*68//100 - 55, t, i)

    # Sign
    sf = get_font(33)
    d.rectangle([W*5//8, H//8, W-20, H//8+135], fill=YELLOW, outline=BLACK, width=3)
    d.text((W*5//8+10, H//8+10),  "HOMEWORK 4 SALE", fill=BLACK, font=sf)
    d.text((W*5//8+25, H//8+55),  "3 seeds  OR", fill=BLACK, font=sf)
    d.text((W*5//8+40, H//8+90),  "50 cents", fill=BLACK, font=sf)

    dollar_pop(d, [(80,H//3),(880,H//3-30)], t, get_font(55))
    return np.array(img)


def ep06(t):
    """Counterfeiting Monopoly Money"""
    img = fill_gradient(Image.new("RGB",(W,H)), (255,205,0), (255,160,0))
    d   = ImageDraw.Draw(img)

    # Fast food counter (red top bar)
    counter_y = H*60//100
    d.rectangle([(0,counter_y),(W,counter_y+40)], fill=(200,40,40))
    d.rectangle([(0,counter_y+40),(W,H)], fill=(180,35,35))
    d.rectangle([(0,0),(W,H//8)], fill=(200,40,40))

    # Menu board
    d.rectangle([W//4, H//8, W*3//4, H//3], fill=(20,20,20), outline=WHITE, width=3)
    mf = get_font(36)
    d.text((W//4+20, H//8+20), "BURGER    $8", fill=WHITE, font=mf)
    d.text((W//4+20, H//8+65), "FRIES     $5", fill=WHITE, font=mf)
    d.text((W//4+20, H//8+110),"SHAKE     $6", fill=WHITE, font=mf)

    # Customer figure (left) holding up Monopoly money
    cust = Figure(W//4, counter_y, height=215)
    cust.draw(d, t, action="hands_up")

    # Fake bills in customer's hand
    for i in range(3):
        bob = math.sin((t+i*.2)*3*math.pi)*8
        bx = W//4 + 40 + i*30
        by = int(counter_y - 320 - i*20 + bob)
        d.rectangle([bx,by,bx+80,by+40], fill=(50,210,50), outline=(30,140,30), width=2)
        d.text((bx+5,by+8), "$500", fill=WHITE, font=get_font(18))

    # Cashier (right) hands on head
    cashier = Figure(W*3//4, counter_y, height=200, color=(200,200,200))
    cashier.draw(d, t, action="confused", flip=True)

    bfont = get_font(36)
    if t > 0.2:
        speech_bubble(d, W//4, counter_y-240, "It IS real\nmoney. I\nchecked.", bfont)
    if t > 0.5:
        speech_bubble(d, W*3//4, counter_y-200, "Sir please\nleave.", get_font(36),
                      bg=(255,220,220))
    return np.array(img)


def ep07(t):
    """Robin Hood Gets Confused"""
    img = fill_gradient(Image.new("RGB",(W,H)), (60,110,60), (40,80,40))
    d   = ImageDraw.Draw(img)
    d.rectangle([(0,H*65//100),(W,H)], fill=(50,90,40))

    for tx in [50,200,800,950,1050]:
        draw_tree(d, tx, H*65//100, size=140, tc=(35,120,35))

    gy = H*65//100

    # Rich figure (top hat, money bags)
    rich = Figure(W*4//5, gy, height=215, color=(255,220,100))
    rich.draw(d, t, action="cheer")
    # Top hat
    hx, hy = W*4//5, gy - 215 - 28
    d.rectangle([hx-35, hy-60, hx+35, hy], fill=BLACK, outline=WHITE, width=2)
    d.rectangle([hx-48, hy, hx+48, hy+18], fill=BLACK, outline=WHITE, width=2)

    # Poor figure (sad, empty hands)
    poor = Figure(W//5, gy, height=185, color=GREY)
    poor.draw(d, t, action="idle")

    # Robin Hood figure (confused, in middle)
    robin = Figure(W//2, gy, height=220, color=(40,180,40))
    robin.draw(d, t, action="confused")
    # Hood
    hcx, hcy = W//2, gy - 220 - 25
    d.polygon([(hcx,hcy-55),(hcx-50,hcy+5),(hcx+50,hcy+5)], fill=(30,140,30), outline=BLACK, width=2)

    # Money bags going to rich guy (arrow path)
    arrow_x = int(W//2 + (W*4//5 - W//2) * (t%1))
    d.ellipse([arrow_x-18, gy-120-18, arrow_x+18, gy-120+18], fill=(210,180,50), outline=BLACK, width=2)
    d.text((arrow_x-10, gy-130), "$", fill=BLACK, font=get_font(22))

    bfont = get_font(34)
    if t > 0.3:
        speech_bubble(d, W//2, gy-245, "I'm...helping?", bfont, bg=(255,255,200))
    return np.array(img)


def ep08(t):
    """Buying All the Computers"""
    img = fill_gradient(Image.new("RGB",(W,H)), (8,8,28), (20,20,50))
    d   = ImageDraw.Draw(img)

    # Screen glow
    for i in range(20):
        sx, sy = (i*157+50)%W, (i*113+60)%(H*3//4)
        d.ellipse([sx-2,sy-2,sx+2,sy+2], fill=(0,200,80))

    # Laptops scattered around
    for i in range(12):
        lx = (i*157+100)%W - 60
        ly = (i*113+120)%(H*3//5) + H//8
        lw, lh = 100, 65
        d.rectangle([lx,ly+lh-5,lx+lw,ly+lh+5], fill=(60,60,60), outline=BLACK, width=1)
        d.rectangle([lx,ly,lx+lw,ly+lh], fill=(40,40,40), outline=(80,80,80), width=1)
        # Screen shows green text
        green_blink = 0.5+0.5*math.sin((t*4+i*0.5)*math.pi)
        if green_blink > 0.5:
            d.text((lx+5,ly+5), ">_ I'M IN", fill=(0,200,80), font=get_font(14))

    # Main hacker figure (frantic typing)
    Figure(W//2, H*72//100, height=230, color=(0,200,80)).draw(d, t, action="type")

    # "I'M IN" giant bubble
    bfont = get_font(38)
    if t > 0.15:
        speech_bubble(d, W//2, H*72//100 - 245, "I'M IN\n(sort of)", bfont,
                      bg=(10,40,10), fg=(0,255,80))
    return np.array(img)


def ep09(t):
    """Terrible Art Forgery"""
    img = Image.new("RGB",(W,H),(248,245,240))
    d   = ImageDraw.Draw(img)
    d.rectangle([(0,H*65//100),(W,H)], fill=(215,205,195))
    d.rectangle([(0,0),(W,20)], fill=(140,120,100))

    # "Paintings" on wall (very bad)
    for i,(px2,py2,pcolor) in enumerate([(60,H//6,(255,180,100)),(W//2-120,H//5,(150,180,255)),(W-250,H//6,(200,255,180))]):
        d.rectangle([px2,py2,px2+180,py2+220], fill=pcolor, outline=BLACK, width=3)
        d.rectangle([px2+10,py2+10,px2+170,py2+210], fill=pcolor)
        # "Stick figure inside the painting" = hilarious forgery
        pf = Figure(px2+90, py2+215, height=120, color=BLACK, lw=3)
        pf.draw(d, (t+i*0.33)%1, action="idle")
        d.text((px2+15,py2+175), "MOONA LISA", fill=BLACK, font=get_font(16))

    # Artist figure in beret
    artist = Figure(W//2+30, H*65//100, height=225)
    artist.draw(d, t, action="point")
    # Beret
    bcx, bcy = W//2+30, H*65//100 - 225 - 25
    d.ellipse([bcx-42,bcy-20,bcx+42,bcy+20], fill=(80,60,160))
    d.ellipse([bcx+20,bcy-28,bcx+32,bcy-18], fill=(80,60,160))

    # Art critic (monocle, chin-stroke)
    critic = Figure(W*4//5, H*65//100, height=200, color=(100,80,150))
    critic.draw(d, t, action="confused", flip=True)

    # Auction price
    af = get_font(44)
    d.rectangle([W//8,H//12,W*7//8,H//12+90], fill=YELLOW, outline=BLACK, width=3)
    price = int(10000 + math.sin(t*3*math.pi)*8000 + 40000)
    d.text((W//8+20,H//12+20), f"CURRENT BID: ${price:,}", fill=BLACK, font=af)

    bfont = get_font(34)
    if t > 0.3:
        speech_bubble(d, W//2+30, H*65//100-250, "It's a\npowerful\nstatement.", bfont)
    return np.array(img)


def ep10(t):
    """Sandwich Smuggler at Airport"""
    img = fill_gradient(Image.new("RGB",(W,H)), (100,155,210), (75,130,185))
    d   = ImageDraw.Draw(img)
    gy  = H*65//100
    d.rectangle([(0,gy),(W,H)], fill=(185,185,200))

    # Airport tiles
    for tx in range(0, W, 80):
        d.line([(tx,gy),(tx,H)], fill=(170,170,185), width=2)
    for ty in range(gy, H, 80):
        d.line([(0,ty),(W,ty)], fill=(170,170,185), width=2)

    # Security arch
    d.rectangle([W//2-120, gy-300, W//2-95, gy], fill=(60,60,80), outline=BLACK, width=2)
    d.rectangle([W//2+95, gy-300, W//2+120, gy], fill=(60,60,80), outline=BLACK, width=2)
    d.rectangle([W//2-120, gy-310, W//2+120, gy-285], fill=(60,60,80), outline=BLACK, width=2)

    # Smuggler in MASSIVE coat (sweating)
    smuggler = Figure(W*3//5, gy, height=235)
    smuggler.draw(d, t, action="sneak")
    # Giant trench coat shape
    cx = W*3//5
    coat_y = gy - 235 + 30
    d.polygon([(cx-120, gy),(cx+120, gy),(cx+80, coat_y),(cx-80, coat_y)],
              fill=(80,60,40), outline=BLACK, width=3)

    # Sandwiches spilling out
    for i in range(8):
        angle = (i/8)*math.pi*2 + t*math.pi
        sx2 = int(cx + 90*math.cos(angle))
        sy2 = int(gy - 120 + 60*math.sin(angle))
        bob = math.sin((t*4+i)*math.pi)*12
        # Sandwich: two bread slices + filling
        d.rectangle([sx2-22, int(sy2+bob)-8,  sx2+22, int(sy2+bob)+2],  fill=(210,170,100))
        d.rectangle([sx2-20, int(sy2+bob)-6,  sx2+20, int(sy2+bob)+0],  fill=(80,200,80))
        d.rectangle([sx2-22, int(sy2+bob)+2,  sx2+22, int(sy2+bob)+12], fill=(210,170,100))

    # TSA agent (arms on hips)
    tsa = Figure(W//4, gy, height=215, color=(30,60,30))
    tsa.draw(d, t, action="hands_up", flip=True)

    bfont = get_font(34)
    if t > 0.25:
        speech_bubble(d, W//4, gy-240, "SIR. How\nmany is\nTHAT?!", bfont, bg=(255,220,220))
    if t > 0.6:
        speech_bubble(d, W*3//5, gy-255, "Forty\nseven.", get_font(38))
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

def generate_voiceover(text, out_path):
    print("  [tts] Generating voiceover…")
    gTTS(text=text, lang="en", slow=False).save(str(out_path))
    print("  [tts] ✓ narration.mp3")
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

    words      = episode["narration"].split()
    n_chunks   = max(4, len(words)//14)
    chunk_size = max(1, len(words)//n_chunks)
    chunks     = [" ".join(words[i:i+chunk_size]) for i in range(0, len(words), chunk_size)]
    chunk_dur  = vdur / len(chunks)
    sub_font   = get_font(42)
    scene_r    = get_renderer(episode)

    def render_frame(t):
        frame = Image.fromarray(scene_r(t / vdur))
        d = ImageDraw.Draw(frame, "RGBA")
        d.rectangle([(0,H-215),(W,H)], fill=(0,0,0,155))
        idx   = min(int(t/chunk_dur), len(chunks)-1)
        lines = textwrap.wrap(chunks[idx], width=32)
        y = H - 200
        for line in lines:
            bb = d.textbbox((0,0), line, font=sub_font)
            x  = (W - (bb[2]-bb[0])) // 2
            d.text((x+2,y+2), line, font=sub_font, fill=(0,0,0,220))
            d.text((x,  y),   line, font=sub_font, fill=(255,255,255,255))
            y += 56
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
