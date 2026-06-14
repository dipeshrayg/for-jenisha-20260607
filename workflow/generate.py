#!/usr/bin/env python3
"""
Automated "Definitely Illegal" Comedy Video Generator
Generates satirical animated short videos about absurd money-making "crimes".

Usage:
    python generate.py                    # generate next episode
    python generate.py --episode 3        # generate specific episode
    python generate.py --list             # list all episodes
    python generate.py --all              # generate all episodes
"""

import os
import sys
import json
import time
import argparse
import requests
from pathlib import Path
from datetime import datetime

# ── Config ──────────────────────────────────────────────────────────────────
API_KEY = os.environ.get("HIGGSFIELD_API_KEY", "")
BASE_URL = "https://api.higgsfield.ai/v1"
EPISODES_FILE = Path(__file__).parent / "episodes.json"
OUTPUT_DIR = Path(__file__).parent / "output"
STATUS_FILE = Path(__file__).parent / "generated.json"

HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
}

# ── Helpers ──────────────────────────────────────────────────────────────────
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
    generated_ids = {int(k) for k in status.keys()}
    for ep in episodes:
        if ep["id"] not in generated_ids:
            return ep
    return None

def poll_job(job_id: str, timeout: int = 300) -> dict:
    """Poll a Higgsfield job until it completes or times out."""
    deadline = time.time() + timeout
    delay = 5
    while time.time() < deadline:
        r = requests.get(f"{BASE_URL}/jobs/{job_id}", headers=HEADERS)
        r.raise_for_status()
        job = r.json()
        state = job.get("status", job.get("state", ""))
        print(f"  → job {job_id[:8]}… {state}")
        if state in ("completed", "succeeded", "done"):
            return job
        if state in ("failed", "error", "cancelled"):
            raise RuntimeError(f"Job {job_id} failed: {job}")
        time.sleep(min(delay, 30))
        delay = min(delay * 1.5, 30)
    raise TimeoutError(f"Job {job_id} timed out after {timeout}s")

def output_url(job: dict) -> str:
    """Extract download URL from a completed job."""
    # Higgsfield returns URLs in different shapes depending on media type
    for key in ("output_url", "url", "video_url", "audio_url", "image_url"):
        if key in job:
            return job[key]
    outputs = job.get("outputs") or job.get("results") or []
    if outputs:
        first = outputs[0]
        if isinstance(first, str):
            return first
        return first.get("url", "")
    return ""

def download(url: str, dest: Path):
    dest.parent.mkdir(parents=True, exist_ok=True)
    r = requests.get(url, stream=True, timeout=120)
    r.raise_for_status()
    with open(dest, "wb") as f:
        for chunk in r.iter_content(8192):
            f.write(chunk)
    print(f"  ✓ saved → {dest.relative_to(Path(__file__).parent.parent)}")
    return dest

# ── Generation steps ──────────────────────────────────────────────────────────

def generate_image(episode: dict) -> str:
    """Generate the scene image. Returns job_id."""
    print("\n[1/4] Generating scene image…")
    payload = {
        "model": "nano_banana_pro",
        "prompt": episode["scene_prompt"],
        "aspect_ratio": "9:16",
        "params": {"resolution": "2k"},
    }
    r = requests.post(f"{BASE_URL}/generate/image", headers=HEADERS, json=payload)
    r.raise_for_status()
    return r.json()["job_id"]

def generate_video(episode: dict, image_job_id: str) -> str:
    """Animate the scene image into a short video. Returns job_id."""
    print("\n[2/4] Animating image into video…")
    payload = {
        "model": "kling3_0",
        "prompt": (
            f"{episode['scene_prompt']} "
            "Funny animated motion, comedic timing, cartoon physics, "
            "characters move and react expressively."
        ),
        "duration": 8,
        "aspect_ratio": "9:16",
        "params": {"mode": "std", "sound": "off"},
        "medias": [{"value": image_job_id, "role": "start_image"}],
    }
    r = requests.post(f"{BASE_URL}/generate/video", headers=HEADERS, json=payload)
    r.raise_for_status()
    return r.json()["job_id"]

def generate_voiceover(episode: dict) -> str:
    """Generate the narrator voiceover. Returns job_id."""
    print("\n[3/4] Generating voiceover…")
    payload = {
        "model": "inworld_text_to_speech",
        "prompt": episode["narration"],
        "voice": episode["voice"],
    }
    r = requests.post(f"{BASE_URL}/generate/audio", headers=HEADERS, json=payload)
    r.raise_for_status()
    return r.json()["job_id"]

def generate_music(episode: dict) -> str:
    """Generate background music. Returns job_id."""
    print("\n[4/4] Generating background music…")
    payload = {
        "model": "sonilo_music",
        "prompt": episode["music_prompt"],
        "duration": 30,
    }
    r = requests.post(f"{BASE_URL}/generate/audio", headers=HEADERS, json=payload)
    r.raise_for_status()
    return r.json()["job_id"]

# ── Main pipeline ─────────────────────────────────────────────────────────────

def run_episode(episode: dict):
    ep_id = episode["id"]
    slug = f"ep{ep_id:02d}"
    out = OUTPUT_DIR / slug
    out.mkdir(parents=True, exist_ok=True)

    print(f"\n{'='*60}")
    print(f"  DEFINITELY ILLEGAL — {episode['tagline']}")
    print(f"{'='*60}")

    # Save episode metadata
    with open(out / "episode.json", "w") as f:
        json.dump(episode, f, indent=2)

    # Step 1: Scene image
    img_jid = generate_image(episode)
    img_job = poll_job(img_jid)
    img_url = output_url(img_job)
    download(img_url, out / "scene.png")

    # Step 2: Video (uses image as start frame)
    vid_jid = generate_video(episode, img_jid)
    vid_job = poll_job(vid_jid, timeout=600)
    vid_url = output_url(vid_job)
    download(vid_url, out / "scene.mp4")

    # Step 3: Voiceover
    vo_jid = generate_voiceover(episode)
    vo_job = poll_job(vo_jid)
    vo_url = output_url(vo_job)
    download(vo_url, out / "narration.mp3")

    # Step 4: Music
    mu_jid = generate_music(episode)
    mu_job = poll_job(mu_jid)
    mu_url = output_url(mu_job)
    download(mu_url, out / "music.mp3")

    result = {
        "generated_at": datetime.utcnow().isoformat(),
        "image_url": img_url,
        "video_url": vid_url,
        "voiceover_url": vo_url,
        "music_url": mu_url,
        "output_dir": str(out),
    }

    print(f"\n✅ Episode {ep_id} complete → {out}")
    return result

def main():
    parser = argparse.ArgumentParser(description="Definitely Illegal Video Generator")
    parser.add_argument("--episode", type=int, help="Generate specific episode by ID")
    parser.add_argument("--all", action="store_true", help="Generate all episodes")
    parser.add_argument("--list", action="store_true", help="List episodes")
    args = parser.parse_args()

    if not API_KEY:
        print("ERROR: HIGGSFIELD_API_KEY environment variable not set.")
        sys.exit(1)

    episodes = load_episodes()

    if args.list:
        for ep in episodes:
            status = load_status()
            done = "✅" if str(ep["id"]) in status else "⏳"
            print(f"{done} Ep {ep['id']:02d}: {ep['title']}")
        return

    if args.all:
        targets = episodes
    elif args.episode:
        targets = [ep for ep in episodes if ep["id"] == args.episode]
        if not targets:
            print(f"Episode {args.episode} not found.")
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
        try:
            result = run_episode(ep)
            status[str(ep["id"])] = result
            save_status(status)
        except Exception as e:
            print(f"\n❌ Episode {ep['id']} failed: {e}")
            sys.exit(1)

if __name__ == "__main__":
    main()
