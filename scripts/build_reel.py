#!/usr/bin/env python3
"""Fabrique un réel vertical (1080x1920) à partir d'un montage d'images.

Usage : build_reel.py spec.json sortie.mp4
spec.json = {"hook": "...", "cta": "...", "slides": [{"image": "chemin ou URL", "text": "..."}]}
Si des fichiers audio (.mp3/.m4a/.wav) sont dans assets/music/, l'un d'eux sert de musique.
"""
import glob
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from io import BytesIO

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
W, H = 1080, 1920
SLIDE_SECONDS = 2.2
CTA_SECONDS = 2.8
FPS = 30
GOLD = (212, 175, 55)
DARK = (14, 14, 18)
WHITE = (255, 255, 255)


def font(size, bold=True):
    name = "Poppins-Bold.ttf" if bold else "Poppins-Regular.ttf"
    for path in (os.path.join(ROOT, "assets", "fonts", name),
                 "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"):
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default(size)


def open_image(src):
    if src.startswith("http"):
        req = urllib.request.Request(src, headers={"User-Agent": "calista-content"})
        with urllib.request.urlopen(req, timeout=60) as r:
            return Image.open(BytesIO(r.read())).convert("RGB")
    path = src if os.path.isabs(src) else os.path.join(ROOT, src)
    return Image.open(path).convert("RGB")


def wrap(draw, text, fnt, max_w):
    words, lines, cur = text.split(), [], ""
    for w in words:
        test = (cur + " " + w).strip()
        if draw.textlength(test, font=fnt) <= max_w:
            cur = test
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def clean(text):
    """La police n'a pas d'emojis : on les retire de l'image (ils restent dans la légende)."""
    return "".join(c for c in text if ord(c) < 0x2000 or 0x2010 <= ord(c) <= 0x206F or 0x00A0 <= ord(c) <= 0x024F).strip()


def centered(draw, text, fnt, y, fill, max_w=940, spacing=14, shadow=True):
    lines = wrap(draw, clean(text), fnt, max_w)
    for line in lines:
        w = draw.textlength(line, font=fnt)
        x = (W - w) / 2
        if shadow:
            draw.text((x + 3, y + 3), line, font=fnt, fill=(0, 0, 0))
        draw.text((x, y), line, font=fnt, fill=fill)
        y += fnt.size + spacing
    return y


def rounded(im, radius):
    mask = Image.new("L", im.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, *im.size), radius=radius, fill=255)
    out = im.copy()
    out.putalpha(mask)
    return out


def slide_frame(src, text, index, total, hook=None):
    img = open_image(src)
    bg = img.copy()
    scale = max(W / bg.width, H / bg.height)
    bg = bg.resize((round(bg.width * scale), round(bg.height * scale)))
    left, top = (bg.width - W) // 2, (bg.height - H) // 2
    bg = bg.crop((left, top, left + W, top + H)).filter(ImageFilter.GaussianBlur(45))
    bg = Image.eval(bg, lambda p: int(p * 0.45))
    frame = bg.convert("RGBA")

    max_w, max_h = 960, 1080
    s = min(max_w / img.width, max_h / img.height)
    fg = rounded(img.resize((round(img.width * s), round(img.height * s))).convert("RGBA"), 36)
    fx, fy = (W - fg.width) // 2, 430 + (max_h - fg.height) // 2
    frame.alpha_composite(fg, (fx, fy))

    d = ImageDraw.Draw(frame)
    if hook:
        centered(d, hook, font(62), 210, WHITE, max_w=940, spacing=10)
    else:
        centered(d, f"{index}/{total}", font(56), 270, GOLD)
    if text:
        centered(d, text, font(50), 1570, WHITE, max_w=900, spacing=10)
    return frame.convert("RGB")


def cta_frame(cta, hook):
    frame = Image.new("RGB", (W, H), DARK)
    d = ImageDraw.Draw(frame)
    d.rounded_rectangle((90, 560, W - 90, 1360), radius=48, outline=GOLD, width=5)
    centered(d, "CALISTA", font(120), 640, GOLD, shadow=False)
    centered(d, "Galerie de prompts IA", font(52, bold=False), 800, WHITE, shadow=False)
    centered(d, "contexte afro", font(52, bold=False), 880, WHITE, shadow=False)
    centered(d, cta, font(56), 1060, WHITE, max_w=820, shadow=False)
    centered(d, "Lien en bio", font(60), 1230, GOLD, shadow=False)
    return frame


def run(cmd):
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


def main(spec_path, out_path):
    with open(spec_path, encoding="utf-8") as f:
        spec = json.load(f)
    slides = spec["slides"]
    tmp = tempfile.mkdtemp(prefix="reel-")
    try:
        clips, total = [], len(slides)
        frames = [slide_frame(s["image"], s.get("text", ""), i + 1, total,
                              spec.get("hook") if i == 0 else None)
                  for i, s in enumerate(slides)]
        frames.append(cta_frame(spec.get("cta", "Prompts gratuits sur Calista"), spec.get("hook", "")))
        durations = [SLIDE_SECONDS] * total + [CTA_SECONDS]
        for i, (fr, dur) in enumerate(zip(frames, durations)):
            png = os.path.join(tmp, f"f{i}.png")
            fr.resize((W * 2, H * 2)).save(png)
            clip = os.path.join(tmp, f"c{i}.mp4")
            frames_n = int(dur * FPS)
            zoom = "1+0.0006*on" if i < total else "1"
            run(["ffmpeg", "-y", "-loop", "1", "-i", png, "-vf",
                 f"zoompan=z='{zoom}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames_n}:s={W}x{H}:fps={FPS},format=yuv420p",
                 "-frames:v", str(frames_n), "-c:v", "libx264", "-preset", "veryfast", "-crf", "19", clip])
            clips.append(clip)
        lst = os.path.join(tmp, "list.txt")
        with open(lst, "w") as f:
            f.writelines(f"file '{c}'\n" for c in clips)
        silent = os.path.join(tmp, "video.mp4")
        run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", silent])
        length = sum(durations)
        music = sorted(glob.glob(os.path.join(ROOT, "assets", "music", "*.[mw][pa][34v]")) +
                       glob.glob(os.path.join(ROOT, "assets", "music", "*.m4a")))
        if music:
            track = random.choice(music)
            audio = ["-stream_loop", "-1", "-i", track,
                     "-af", f"afade=t=in:d=0.5,afade=t=out:st={length - 1.5:.1f}:d=1.5,volume=0.8"]
        else:
            audio = ["-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo"]
        run(["ffmpeg", "-y", "-i", silent, *audio, "-map", "0:v", "-map", "1:a",
             "-c:v", "copy", "-c:a", "aac", "-b:a", "128k", "-t", f"{length:.1f}",
             "-movflags", "+faststart", out_path])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
