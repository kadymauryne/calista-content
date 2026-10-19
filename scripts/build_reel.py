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


def pill(d, text, fnt, cy, fill, color, pad_x=44, pad_y=22, max_w=960):
    """Bandeau arrondi centré, 1 à 2 lignes. Renvoie le bas du bandeau."""
    lines = wrap(d, clean(text), fnt, max_w - 2 * pad_x)
    lh = fnt.size + 10
    h = lh * len(lines) + 2 * pad_y
    w = max(d.textlength(l, font=fnt) for l in lines) + 2 * pad_x
    x0, y0 = (W - w) / 2, cy - h / 2
    d.rounded_rectangle((x0, y0, x0 + w, y0 + h), radius=min(48, h / 2), fill=fill)
    y = y0 + pad_y - 6
    for l in lines:
        d.text(((W - d.textlength(l, font=fnt)) / 2, y), l, font=fnt, fill=color)
        y += lh
    return y0 + h


def slide_frame(src, text, index, total, hook=None, cta_line="Prompts gratuits sur CALISTA"):
    """Une image du montage : accroche en haut, image au centre, appel à l'action en bas,
    visibles sur CHAQUE image (on ne sait pas quand la personne arrête de regarder)."""
    img = open_image(src)
    bg = img.copy()
    scale = max(W / bg.width, H / bg.height)
    bg = bg.resize((round(bg.width * scale), round(bg.height * scale)))
    left, top = (bg.width - W) // 2, (bg.height - H) // 2
    bg = bg.crop((left, top, left + W, top + H)).filter(ImageFilter.GaussianBlur(45))
    bg = Image.eval(bg, lambda p: int(p * 0.55))
    frame = bg.convert("RGBA")
    d = ImageDraw.Draw(frame)

    # Accroche (zone sûre : sous l'en-tête d'Instagram)
    big = index == 1
    if hook:
        pill(d, hook, font(64 if big else 50), 300 if big else 280, SUN, GREEN_DEEP)

    # Image
    max_w, max_h = 900, 900
    s = min(max_w / img.width, max_h / img.height)
    fg = rounded(img.resize((round(img.width * s), round(img.height * s))).convert("RGBA"), 36)
    fx, fy = (W - fg.width) // 2, 460 + (max_h - fg.height) // 2
    frame.alpha_composite(fg, (fx, fy))
    d = ImageDraw.Draw(frame)

    # Titre du prompt + compteur
    label = f"{index}/{total}  ·  {text}" if text else f"{index}/{total}"
    centered(d, label, font(42), 1395, WHITE, max_w=920, spacing=8)

    # Appel à l'action permanent (au-dessus de la légende d'Instagram)
    pill(d, cta_line, font(46), 1545, GREEN_DEEP, WHITE, pad_y=18)
    centered(d, "lien en bio", font(44), 1610, SUN, shadow=True)
    return frame.convert("RGB")


GREEN_LIGHT = (46, 184, 92)
GREEN_DEEP = (12, 120, 62)
SUN = (255, 207, 51)
SUN_RAY = (255, 170, 30)
CREAM = (255, 249, 232)
ORANGE = (255, 122, 0)
CONFETTI = [(255, 207, 51), (255, 122, 0), (255, 255, 255), (255, 92, 141), (178, 255, 89), (0, 200, 255)]


def ease_out_back(x):
    c1, c3 = 1.70158, 2.70158
    return 1 + c3 * (x - 1) ** 3 + c1 * (x - 1) ** 2


def green_background():
    """Dégradé radial vert lumineux (plus clair au centre)."""
    small = Image.new("RGB", (108, 192))
    px = small.load()
    for y in range(192):
        for x in range(108):
            d = min(1.0, (((x - 54) / 70) ** 2 + ((y - 80) / 110) ** 2) ** 0.5)
            px[x, y] = tuple(round(GREEN_LIGHT[i] * (1 - d) + GREEN_DEEP[i] * d) for i in range(3))
    return small.resize((W, H), Image.BICUBIC)


def cta_card(cta):
    cw, ch = 860, 860
    card = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    d = ImageDraw.Draw(card)
    d.rounded_rectangle((0, 0, cw, ch), radius=60, fill=CREAM)
    d.rounded_rectangle((14, 14, cw - 14, ch - 14), radius=50, outline=SUN, width=8)

    def line(text, fnt, y, fill):
        text = clean(text)
        for l in wrap(d, text, fnt, cw - 120):
            d.text(((cw - d.textlength(l, font=fnt)) / 2, y), l, font=fnt, fill=fill)
            y += fnt.size + 12
        return y

    y = line("CALISTA", font(130), 90, GREEN_DEEP)
    y = line("Galerie de prompts IA", font(50, bold=False), y + 10, (40, 40, 40))
    y = line("contexte afro", font(50, bold=False), y, (40, 40, 40))
    y = line(cta, font(58), y + 40, ORANGE)
    y = line("calista-app.netlify.app", font(40, bold=False), y + 6, GREEN_DEEP)
    bw, bh, by = 520, 120, ch - 200
    d.rounded_rectangle(((cw - bw) / 2, by, (cw + bw) / 2, by + bh), radius=60, fill=GREEN_DEEP)
    f = font(56)
    txt = "Lien en bio"
    d.text(((cw - d.textlength(txt, font=f)) / 2, by + (bh - f.size) / 2 - 8), txt, font=f, fill=SUN)
    return card


def cta_frames(cta, n_frames, seed=3):
    """Carte finale animée : soleil qui tourne, la carte surgit avec un rebond, pluie de confettis."""
    import math
    rnd = random.Random(seed)
    bg = green_background()
    card = cta_card(cta)
    sun_c = (W // 2, 520)
    confetti = []
    for _ in range(90):                                   # pluie qui tombe d'en haut
        confetti.append({
            "x": rnd.uniform(0, W), "y": rnd.uniform(-900, -20), "vx": rnd.uniform(-80, 80),
            "vy": rnd.uniform(500, 900), "g": 0,
            "c": rnd.choice(CONFETTI), "w": rnd.randint(16, 28), "h": rnd.randint(9, 15),
            "rot": rnd.uniform(0, 360), "vr": rnd.uniform(-540, 540)})
    for _ in range(200):                                  # explosion autour de la carte
        ang = rnd.uniform(0, 2 * math.pi)
        speed = rnd.uniform(1400, 2800)
        confetti.append({
            "x": W / 2, "y": 1150, "vx": math.cos(ang) * speed, "vy": math.sin(ang) * speed - 700, "g": 1,
            "c": rnd.choice(CONFETTI), "w": rnd.randint(14, 26), "h": rnd.randint(8, 14),
            "rot": rnd.uniform(0, 360), "vr": rnd.uniform(-540, 540)})
    for i in range(n_frames):
        t_ = i / FPS
        fr = bg.copy().convert("RGBA")
        layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        # Soleil : rayons qui tournent + halo
        rot = t_ * 25
        for k in range(16):
            a1 = math.radians(rot + k * 22.5 - 5)
            a2 = math.radians(rot + k * 22.5 + 5)
            r_out = 1300
            d.polygon([sun_c, (sun_c[0] + r_out * math.cos(a1), sun_c[1] + r_out * math.sin(a1)),
                       (sun_c[0] + r_out * math.cos(a2), sun_c[1] + r_out * math.sin(a2))],
                      fill=(*SUN_RAY, 70))
        pulse = 1 + 0.04 * math.sin(t_ * 6)
        for rr, alpha in ((260, 60), (215, 110)):
            r = rr * pulse
            d.ellipse((sun_c[0] - r, sun_c[1] - r, sun_c[0] + r, sun_c[1] + r), fill=(*SUN, alpha))
        r = 170 * pulse
        d.ellipse((sun_c[0] - r, sun_c[1] - r, sun_c[0] + r, sun_c[1] + r), fill=(*SUN, 255))
        fr.alpha_composite(layer)
        # Confettis (derrière la carte pour garder le texte lisible)
        if t_ >= 0.15:
            tc = t_ - 0.15
            cl = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            for cf in confetti:
                x = cf["x"] + cf["vx"] * tc * 0.6
                y = cf["y"] + cf["vy"] * tc * 0.6 + 900 * cf.get("g", 1) * tc * tc
                if -50 < x < W + 50 and -50 < y < H + 50:
                    piece = Image.new("RGBA", (cf["w"], cf["h"]), (*cf["c"], 255))
                    piece = piece.rotate(cf["rot"] + cf["vr"] * tc, expand=True)
                    cl.alpha_composite(piece, (int(x), int(y)))
            fr.alpha_composite(cl)
        # La carte surgit (0 -> 0,5 s) avec un rebond
        p = min(1.0, t_ / 0.5)
        sc = max(0.05, ease_out_back(p)) if t_ > 0.05 else 0.05
        cw, ch = max(2, round(card.width * sc)), max(2, round(card.height * sc))
        c = card.resize((cw, ch), Image.BICUBIC)
        shadow = Image.new("RGBA", (cw + 60, ch + 60), (0, 0, 0, 0))
        ImageDraw.Draw(shadow).rounded_rectangle((30, 40, cw + 30, ch + 40), radius=60, fill=(0, 0, 0, 70))
        shadow = shadow.filter(ImageFilter.GaussianBlur(18))
        cx, cy = (W - cw) // 2, 1150 - ch // 2
        fr.alpha_composite(shadow, (cx - 30, cy - 30))
        fr.alpha_composite(c, (cx, cy))
        yield fr.convert("RGB")


def run(cmd):
    r = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"{cmd[0]} a échoué : {r.stderr[-600:]}")


def main(spec_path, out_path):
    with open(spec_path, encoding="utf-8") as f:
        spec = json.load(f)
    slides = spec["slides"]
    tmp = tempfile.mkdtemp(prefix="reel-")
    try:
        clips, total = [], len(slides)
        frames = [slide_frame(s["image"], s.get("text", ""), i + 1, total, spec.get("hook"),
                              spec.get("cta_line", "Prompts gratuits sur CALISTA"))
                  for i, s in enumerate(slides)]
        durations = [SLIDE_SECONDS] * total
        for i, (fr, dur) in enumerate(zip(frames, durations)):
            png = os.path.join(tmp, f"f{i}.png")
            fr.resize((W * 2, H * 2)).save(png)
            clip = os.path.join(tmp, f"c{i}.mp4")
            frames_n = int(dur * FPS)
            zoom = "1+0.0006*on"
            run(["ffmpeg", "-y", "-loop", "1", "-i", png, "-vf",
                 f"zoompan=z='{zoom}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames_n}:s={W}x{H}:fps={FPS},format=yuv420p",
                 "-frames:v", str(frames_n), "-c:v", "libx264", "-preset", "veryfast", "-crf", "19", clip])
            clips.append(clip)
        seq = os.path.join(tmp, "cta")
        os.makedirs(seq)
        for k, fr in enumerate(cta_frames(spec.get("cta", "Copie les prompts gratuits"), int(CTA_SECONDS * FPS))):
            fr.save(os.path.join(seq, f"{k:03d}.png"))
        cta_clip = os.path.join(tmp, "cta.mp4")
        run(["ffmpeg", "-y", "-framerate", str(FPS), "-i", os.path.join(seq, "%03d.png"),
             "-c:v", "libx264", "-preset", "veryfast", "-crf", "19", "-pix_fmt", "yuv420p", cta_clip])
        clips.append(cta_clip)
        durations.append(CTA_SECONDS)
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
            # La musique démarre au début de l'extrait (calé sur le drop) et s'éteint en douceur.
            audio = ["-i", track,
                     "-af", f"afade=t=out:st={max(0, length - 1.2):.1f}:d=1.2"]
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
