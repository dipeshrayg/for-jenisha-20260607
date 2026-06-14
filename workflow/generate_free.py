#!/usr/bin/env python3
"""
Definitely Illegal — Free Comedy Video Generator
100% free. No API keys. No accounts.

Stack:
  Images   → Pollinations.ai  (free AI image generation)
  Voice    → gTTS             (free Google Text-to-Speech)
  Video    → moviepy          (open-source, wraps ffmpeg)
  Music    → numpy tones      (synthesised in-process)

Usage:
    python generate_free.py               # generate next episode
    python generate_free.py --episode 3   # specific episode
    python generate_free.py --all         # all episodes
    python generate_free.py --list        # list status
"""

import os
import sys
import json
import time
import textwrap
import argparse
import struct
import wave
from pathlib import Path
from datetime import datetime

import requests
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from gtts import gTTS
from moviepy.editor import (
    ImageClip,
    AudioFileClip,
    VideoClip,
    concatenate_videoclips,
    CompositeAudioClip,
)

# ── Constants ─────────────────────────────────────────────────────────────────

EPISODES_FILE = Path(__file__).parent / "episodes.json"
OUTPUT_DIR    = Path(__file__).parent / "output"
STATUS_FILE   = Path(__file__).parent / "generated.json"

W, H = 1080, 1920   # 9:16 portrait (YouTube Shorts / Instagram Reels)
FPS  = 24

DARK   = (15,  15,  15)
YELLOW = (255, 210,  0)
WHITE  = (255, 255, 255)
GREY   = (160, 160, 160)

# ── Helpers ───────────────────────────────────────────────────────────────────

def load_episodes():
    with open(EPISODES_FILE) as f:
        return json.load(f)

def load_status():
    if STATUS_FILE.exists():
        with open(STATUS_FILE) as f:
            return json.load(f)
    return {}

def save_status(status):
    with open(STATUS_FILE, "w") as f:
        json.dump(status, f, indent=2)

def next_episode(episodes, status):
    done = {int(k) for k in status}
    for ep in episodes:
        if ep["id"] not in done:
            return ep
    return None

def get_font(size: int) -> ImageFont.FreeTypeFont:
    candidates = [
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
        "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/Library/Fonts/Arial Bold.ttf",
    ]
    for p in candidates:
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    # Last resort: built-in bitmap font (looks retro — also fine)
    return ImageFont.load_default()

def centered_text(draw, text, y, font, color=WHITE, shadow=True):
    bbox  = draw.textbbox((0, 0), text, font=font)
    tw    = bbox[2] - bbox[0]
    x     = (W - tw) // 2
    if shadow:
        draw.text((x + 3, y + 3), text, font=font, fill=(0, 0, 0))
    draw.text((x, y), text, font=font, fill=color)

# ── Image generation (Pollinations.ai) ────────────────────────────────────────

def fetch_scene_image(episode: dict, out_path: Path) -> Path:
    print("  [img] Calling Pollinations.ai…")
    prompt  = (
        episode["scene_prompt"]
        + ", vibrant cartoon illustration, flat 2D art style, funny, colourful, "
          "clean lines, comic book look"
    )
    encoded = requests.utils.quote(prompt)
    url = (
        f"https://image.pollinations.ai/prompt/{encoded}"
        f"?width={W}&height={H}&model=flux&nologo=true&seed={episode['id'] * 7}"
    )
    for attempt in range(4):
        try:
            r = requests.get(url, timeout=120)
            r.raise_for_status()
            out_path.write_bytes(r.content)
            img = Image.open(out_path)
            if img.size[0] > 100:
                print(f"  [img] ✓ {img.size[0]}×{img.size[1]} px")
                return out_path
        except Exception as e:
            wait = 2 ** attempt
            print(f"  [img] attempt {attempt+1} failed ({e}), retry in {wait}s…")
            time.sleep(wait)
    raise RuntimeError("Pollinations.ai image fetch failed after 4 attempts")

# ── Voiceover (gTTS) ──────────────────────────────────────────────────────────

def generate_voiceover(text: str, out_path: Path) -> Path:
    print("  [tts] Generating voiceover with gTTS…")
    gTTS(text=text, lang="en", slow=False).save(str(out_path))
    print(f"  [tts] ✓ narration.mp3")
    return out_path

# ── Background tone (synthesised, no external deps) ───────────────────────────

def generate_tone_music(duration: float, out_path: Path) -> Path:
    """Generate a simple comedic bass-bump loop using pure numpy."""
    sr     = 44100
    n      = int(sr * duration)
    t      = np.linspace(0, duration, n, endpoint=False)

    # Simple four-chord comedy loop (C  Am  F  G  repeating)
    beat   = 0.5                        # one chord every half-second
    freqs  = [130.8, 110.0, 87.3, 98.0]  # C2 A1 F1 G1 bass notes
    chord_idx = (t / beat).astype(int) % len(freqs)
    bass   = 0.35 * np.sin(2 * np.pi * np.array([freqs[i] for i in chord_idx]) * t)

    # Snare-ish noise on beats 2 & 4 (half-beat offset)
    snare_env  = np.zeros(n)
    for i in range(int(duration / beat)):
        if i % 2 == 1:
            start = int(i * beat * sr)
            end   = min(start + int(0.05 * sr), n)
            snare_env[start:end] = np.linspace(0.5, 0, end - start)
    snare = snare_env * np.random.uniform(-1, 1, n)

    audio = np.clip(bass + snare, -1, 1)
    audio_int16 = (audio * 32767).astype(np.int16)

    with wave.open(str(out_path), "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(audio_int16.tobytes())

    print(f"  [mus] ✓ music.wav ({duration:.1f}s)")
    return out_path

# ── Frame renderers ───────────────────────────────────────────────────────────

def render_title_frame(episode: dict) -> np.ndarray:
    img  = Image.new("RGB", (W, H), DARK)
    draw = ImageDraw.Draw(img)

    draw.rectangle([(0, 0), (W, 14)], fill=YELLOW)
    draw.rectangle([(0, H - 14), (W, H)], fill=YELLOW)

    f96 = get_font(96)
    f52 = get_font(52)
    f38 = get_font(38)
    f32 = get_font(32)

    centered_text(draw, "DEFINITELY",  H // 4 - 80, f96, YELLOW)
    centered_text(draw, "ILLEGAL",     H // 4 + 30, f96, YELLOW)
    centered_text(draw, f"Episode {episode['id']}", H // 4 + 160, f38, GREY, shadow=False)

    y = H // 2 - 20
    for line in textwrap.wrap(episode["title"], width=22):
        centered_text(draw, line, y, f52, WHITE)
        y += 72

    y += 30
    for line in textwrap.wrap(episode["tagline"], width=42):
        centered_text(draw, line, y, f32, GREY, shadow=False)
        y += 46

    return np.array(img)


def render_end_frame() -> np.ndarray:
    img  = Image.new("RGB", (W, H), DARK)
    draw = ImageDraw.Draw(img)
    draw.rectangle([(0, 0), (W, 14)], fill=YELLOW)
    draw.rectangle([(0, H - 14), (W, H)], fill=YELLOW)

    centered_text(draw, "DEFINITELY",            H // 3 - 60, get_font(96), YELLOW)
    centered_text(draw, "ILLEGAL",               H // 3 + 50, get_font(96), YELLOW)
    centered_text(draw, "New episode every week.",H // 2 + 80, get_font(50), WHITE)
    centered_text(draw, "Subscribe before it's too late.", H // 2 + 160, get_font(36), GREY, shadow=False)
    return np.array(img)


def make_scene_renderer(base_img: Image.Image, duration: float,
                        chunks: list[str], chunk_dur: float):
    font = get_font(44)

    def render(t: float) -> np.ndarray:
        # Ken Burns slow zoom in
        zoom   = 1.0 + 0.10 * (t / duration)
        nw, nh = int(W / zoom), int(H / zoom)
        l      = (W - nw) // 2
        top_px = (H - nh) // 2
        frame  = base_img.crop((l, top_px, l + nw, top_px + nh)).resize((W, H), Image.LANCZOS)
        draw   = ImageDraw.Draw(frame, "RGBA")

        # Dark subtitle bar
        bar_top = H - 280
        draw.rectangle([(0, bar_top), (W, H)], fill=(0, 0, 0, 160))

        # Subtitle text
        idx   = min(int(t / chunk_dur), len(chunks) - 1)
        lines = textwrap.wrap(chunks[idx], width=30)
        y     = bar_top + 20
        for line in lines:
            bb = draw.textbbox((0, 0), line, font=font)
            x  = (W - (bb[2] - bb[0])) // 2
            draw.text((x + 2, y + 2), line, font=font, fill=(0, 0, 0, 220))
            draw.text((x, y),         line, font=font, fill=(255, 255, 255, 255))
            y += 60

        return np.array(frame.convert("RGB"))

    return render

# ── Video assembly ─────────────────────────────────────────────────────────────

def assemble_video(episode: dict, scene_img_path: Path,
                   voiceover_path: Path, music_path: Path,
                   out_path: Path) -> Path:
    print("  [vid] Assembling video with moviepy…")

    base = Image.open(scene_img_path).convert("RGB").resize((W, H), Image.LANCZOS)
    vo   = AudioFileClip(str(voiceover_path))
    vdur = vo.duration

    # Music loops under full video; lower volume so narration is clear
    total_dur = 3 + vdur + 3
    mu = AudioFileClip(str(music_path)).volumex(0.18)
    if mu.duration < total_dur:
        from moviepy.editor import afx
        mu = mu.fx(afx.audio_loop, duration=total_dur)
    mu = mu.subclip(0, total_dur)

    # Subtitle chunks
    words      = episode["narration"].split()
    n_chunks   = max(4, len(words) // 14)
    chunk_size = max(1, len(words) // n_chunks)
    chunks     = [" ".join(words[i: i + chunk_size]) for i in range(0, len(words), chunk_size)]
    chunk_dur  = vdur / len(chunks)

    # Clips
    title_clip  = ImageClip(render_title_frame(episode), duration=3).set_fps(FPS)
    scene_clip  = (
        VideoClip(make_scene_renderer(base, vdur, chunks, chunk_dur), duration=vdur)
        .set_fps(FPS)
        .set_audio(vo)
    )
    end_clip    = ImageClip(render_end_frame(), duration=3).set_fps(FPS)

    video = concatenate_videoclips([title_clip, scene_clip, end_clip], method="compose")

    # Mix voiceover + background music
    final_audio = CompositeAudioClip([video.audio, mu])
    video       = video.set_audio(final_audio)

    video.write_videofile(
        str(out_path), fps=FPS,
        codec="libx264", audio_codec="aac",
        temp_audiofile=str(out_path.parent / "tmp_audio.m4a"),
        remove_temp=True,
        logger=None,
        threads=4,
    )
    print(f"  [vid] ✓ video.mp4 saved")
    return out_path

# ── Episode pipeline ───────────────────────────────────────────────────────────

def run_episode(episode: dict) -> dict:
    ep_id = episode["id"]
    out   = OUTPUT_DIR / f"ep{ep_id:02d}"
    out.mkdir(parents=True, exist_ok=True)

    print(f"\n{'='*60}")
    print(f"  {episode['tagline']}")
    print(f"{'='*60}")

    scene_img  = fetch_scene_image(episode,          out / "scene.png")
    voiceover  = generate_voiceover(episode["narration"], out / "narration.mp3")

    # Total video duration = 3 (title) + narration + 3 (end)
    vo_dur     = AudioFileClip(str(voiceover)).duration
    total_dur  = 3 + vo_dur + 3
    music      = generate_tone_music(total_dur + 2,  out / "music.wav")

    video      = assemble_video(episode, scene_img, voiceover, music, out / "video.mp4")

    result = {
        "generated_at": datetime.utcnow().isoformat(),
        "video": str(video),
        "image": str(scene_img),
        "voiceover": str(voiceover),
    }
    print(f"\n✅  Episode {ep_id} complete → {out}/video.mp4")
    return result

# ── CLI ────────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="Definitely Illegal — free video generator")
    ap.add_argument("--episode", type=int, help="Episode ID to generate")
    ap.add_argument("--all",     action="store_true", help="Generate all episodes")
    ap.add_argument("--list",    action="store_true", help="List episode status")
    args = ap.parse_args()

    episodes = load_episodes()

    if args.list:
        status = load_status()
        for ep in episodes:
            mark = "✅" if str(ep["id"]) in status else "⏳"
            print(f"{mark}  Ep {ep['id']:02d}: {ep['title']}")
        return

    if args.all:
        targets = episodes
    elif args.episode:
        targets = [e for e in episodes if e["id"] == args.episode]
        if not targets:
            print(f"No episode with id={args.episode}")
            sys.exit(1)
    else:
        status = load_status()
        ep = next_episode(episodes, status)
        if not ep:
            print("All episodes have been generated!")
            return
        targets = [ep]

    status = load_status()
    for ep in targets:
        result = run_episode(ep)
        status[str(ep["id"])] = result
        save_status(status)

if __name__ == "__main__":
    main()
