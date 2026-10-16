#!/usr/bin/env python3
"""Choisit des prompts dans la galerie Calista (Firebase) et remplit la file de publication.

Utilise Pillow pour convertir les images en JPEG au bon format.
  DRY_RUN=1  affiche le plan sans rien écrire ni télécharger
  WEEKS=1    nombre de semaines à planifier (défaut 1)
"""
import json
import os
import random
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
PROJECT = "calista-75491"
API_KEY = "AIzaSyDNRUT8FHdfGrYIvCXahevX_1LZCaysOWo"  # clé publique de l'app web
COLLECTION = "prompts"
DRY = os.environ.get("DRY_RUN") == "1"
WEEKS = int(os.environ.get("WEEKS", "1"))


def load(name):
    with open(os.path.join(ROOT, name), encoding="utf-8") as f:
        return json.load(f)


def save(name, data):
    with open(os.path.join(ROOT, name), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def field(doc, key):
    v = doc.get("fields", {}).get(key, {})
    for kind in ("stringValue", "booleanValue", "integerValue", "doubleValue", "timestampValue"):
        if kind in v:
            return v[kind]
    return None


def fetch_prompts():
    base = (f"https://firestore.googleapis.com/v1/projects/{PROJECT}"
            f"/databases/(default)/documents/{COLLECTION}")
    out, token = [], None
    while True:
        q = {"pageSize": "300", "key": API_KEY}
        if token:
            q["pageToken"] = token
        with urllib.request.urlopen(base + "?" + urllib.parse.urlencode(q), timeout=60) as r:
            data = json.loads(r.read().decode())
        for d in data.get("documents", []):
            out.append({
                "id": d["name"].rsplit("/", 1)[-1],
                "title": (field(d, "title") or "").strip(),
                "category": (field(d, "category") or "").strip(),
                "image": (field(d, "image") or "").strip(),
                "premium": bool(field(d, "premium")),
            })
        token = data.get("nextPageToken")
        if not token:
            return out


def to_jpeg(url, dest):
    """Télécharge l'image et la met en JPEG, format 4:5 minimum (exigé par Instagram)."""
    from io import BytesIO
    from PIL import Image, ImageFilter
    req = urllib.request.Request(url, headers={"User-Agent": "calista-content"})
    with urllib.request.urlopen(req, timeout=60) as r:
        im = Image.open(BytesIO(r.read())).convert("RGB")
    w, h = im.size
    ratio = w / h
    if ratio < 0.8:
        if ratio >= 0.7:                       # presque bon : on rogne un peu, plus en bas
            new_h = round(w * 1.25)
            top = (h - new_h) // 3
            im = im.crop((0, top, w, top + new_h))
        else:                                  # très étroit : fond flou sur les côtés
            cw, ch = round(h * 0.8), h
            bg = im.resize((cw, ch)).filter(ImageFilter.GaussianBlur(30))
            bg.paste(im, ((cw - w) // 2, 0))
            im = bg
    elif ratio > 1.91:
        new_w = round(h * 1.91)
        left = (w - new_w) // 2
        im = im.crop((left, 0, left + new_w, h))
    im.thumbnail((1440, 1800))
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    im.save(dest, "JPEG", quality=90, optimize=True)


def make_caption(p, captions, hashtags, rng):
    models = captions["categories"].get(p["category"]) or captions["categories"]["_defaut"]
    body = rng.choice(models).replace("{titre}", p["title"])
    extra = "\n(Prompt premium)" if p["premium"] else ""
    return f"{body}\n\n{captions['appel']}{extra}\n\n{hashtags}"


def slots_for(start, weeks, slots):
    """Dates de publication à venir, à partir de demain."""
    out = []
    day = (start + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    for i in range(7 * weeks):
        d = day + timedelta(days=i)
        for s in slots:
            if d.weekday() == s["weekday"]:
                hh, mm = map(int, s["time"].split(":"))
                out.append(d.replace(hour=hh, minute=mm))
    return sorted(out)


def main():
    cfg, captions, exclude = load("config/schedule.json"), load("config/captions.json"), load("config/exclude.json")
    queue, history = load("queue/posts.json"), load("queue/history.json")
    now = datetime.now(timezone.utc)

    queued_slots = {p["scheduled_at"] for p in queue}
    wanted = [d for d in slots_for(now, WEEKS, cfg["slots"])
              if d.strftime("%Y-%m-%dT%H:%M:00Z") not in queued_slots]
    if not wanted:
        print("Rien à planifier : tous les créneaux sont déjà remplis.")
        return 0

    prompts = [p for p in fetch_prompts() if p["title"] and p["image"].startswith("http")
               and p["id"] not in exclude["ids"]]
    cutoff = (now - timedelta(days=cfg["cooldown_days"])).isoformat()
    recent = {h["id"] for h in history if h["at"] >= cutoff} | \
             {p["source_id"] for p in queue if p.get("source_id") and p["status"] in ("pending", "draft")}
    pool = [p for p in prompts if p["id"] not in recent]
    print(f"{len(prompts)} prompts utilisables, {len(pool)} pas encore publiés récemment.")
    if len(pool) < len(wanted):
        print("Pas assez de prompts neufs : on recycle les plus anciens.")
        pool = prompts

    rng = random.Random(now.strftime("%Y-%m-%d"))
    last_cats = [h["category"] for h in history[-3:]]
    chosen = []
    for _ in wanted:
        cats = sorted({p["category"] for p in pool if p["id"] not in {c["id"] for c in chosen}})
        fresh = [c for c in cats if c not in last_cats] or cats
        if not fresh:
            break
        cat = rng.choice(fresh)
        cand = [p for p in pool if p["category"] == cat and p["id"] not in {c["id"] for c in chosen}]
        pick = rng.choice(cand)
        chosen.append(pick)
        last_cats = (last_cats + [cat])[-3:]

    for when, p in zip(wanted, chosen):
        stamp = when.strftime("%Y-%m-%dT%H:%M:00Z")
        print(f"- {stamp}  [{p['category']}] {p['title']}{' (premium)' if p['premium'] else ''}")
        if DRY:
            continue
        rel = f"images/auto/{p['id']}.jpg"
        to_jpeg(p["image"], os.path.join(ROOT, rel))
        queue.append({
            "id": f"auto-{when.strftime('%Y%m%d-%H%M')}",
            "type": "image",
            "caption": make_caption(p, captions, cfg["hashtags"], rng),
            "images": [rel],
            "scheduled_at": stamp,
            "status": "pending",
            "source_id": p["id"],
        })
        history.append({"id": p["id"], "category": p["category"], "at": now.isoformat(timespec="seconds")})
    if not DRY:
        save("queue/posts.json", queue)
        save("queue/history.json", history)
    return 0


if __name__ == "__main__":
    sys.exit(main())
