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


def to_jpeg(url, dest, force_45=False):
    """Télécharge l'image et la met en JPEG, format 4:5 minimum (exigé par Instagram)."""
    from io import BytesIO
    from PIL import Image, ImageFilter
    req = urllib.request.Request(url, headers={"User-Agent": "calista-content"})
    with urllib.request.urlopen(req, timeout=60) as r:
        im = Image.open(BytesIO(r.read())).convert("RGB")
    w, h = im.size
    ratio = w / h
    if force_45 and abs(ratio - 0.8) > 0.01:
        if ratio > 0.8:                        # trop large : on rogne les côtés
            new_w = round(h * 0.8)
            left = (w - new_w) // 2
            im = im.crop((left, 0, left + new_w, h))
        else:                                  # trop haut : on rogne un peu plus en bas
            new_h = round(w * 1.25)
            top = (h - new_h) // 3
            im = im.crop((0, top, w, top + new_h))
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


CAT_LABELS = {"pub-produit": "pubs produit", "portraits": "portraits", "marque-logo": "logos et identités de marque",
              "affiches-visuels": "affiches"}


def pick_category(pool, taken, need, last_cats, rng):
    """Catégorie tirée au sort en proportion de son stock (70 portraits pèsent plus que 5 logos),
    en évitant si possible les dernières catégories publiées."""
    stock = {}
    for p in pool:
        if p["id"] not in taken:
            stock[p["category"]] = stock.get(p["category"], 0) + 1
    ok = {c: n for c, n in stock.items() if n >= need}
    fresh = {c: n for c, n in ok.items() if c not in last_cats} or ok
    if not fresh:
        return None
    cats = sorted(fresh)
    return rng.choices(cats, weights=[fresh[c] for c in cats])[0]


def take(pool, cat, n, taken, rng):
    cand = [p for p in pool if p["category"] == cat and p["id"] not in taken]
    picks = rng.sample(cand, n)
    taken |= {p["id"] for p in picks}
    return picks


def main():
    cfg, captions, exclude = load("config/schedule.json"), load("config/captions.json"), load("config/exclude.json")
    queue, history = load("queue/posts.json"), load("queue/history.json")
    now = datetime.now(timezone.utc)
    queued = {p["scheduled_at"] for p in queue}

    # Créneaux à remplir : posts (image ou carrousel) et réels
    todo = []
    for s in cfg["slots"]:
        for d in slots_for(now, WEEKS, [s]):
            todo.append((d, s.get("type", "image"), s.get("images", 1)))
    for d in slots_for(now, WEEKS, cfg.get("reel_slots", [])):
        todo.append((d, "reel", cfg.get("reel_images", 5)))
    todo = sorted(t for t in todo if t[0].strftime("%Y-%m-%dT%H:%M:00Z") not in queued)
    if not todo:
        print("Rien à planifier : tous les créneaux sont déjà remplis.")
        return 0

    prompts = [p for p in fetch_prompts() if p["title"] and p["image"].startswith("http")
               and p["id"] not in exclude["ids"]]
    # Une image ne revient pas avant cooldown_days, qu'elle ait servi en post, carrousel ou réel
    cutoff = (now - timedelta(days=cfg["cooldown_days"])).isoformat()
    recent = {h["id"] for h in history if h["at"] >= cutoff}
    for q in queue:
        if q["status"] in ("pending", "draft"):
            recent |= {q.get("source_id")} | set(q.get("source_ids", []))
    pool = [p for p in prompts if p["id"] not in recent]
    need = sum(n for _, _, n in todo)
    print(f"{len(prompts)} prompts utilisables, {len(pool)} pas encore publiés depuis {cfg['cooldown_days']} jours, "
          f"{need} nécessaires.")
    if len(pool) < need:
        last_use = {}
        for h in history:
            last_use[h["id"]] = max(last_use.get(h["id"], ""), h["at"])
        pool = sorted(prompts, key=lambda p: last_use.get(p["id"], ""))[:max(need * 2, len(pool))]
        print("Stock neuf insuffisant : on reprend les images publiées il y a le plus longtemps.")

    rng = random.Random(now.strftime("%Y-%m-%d"))
    last_cats = [h["category"] for h in history[-2:]]
    taken = set()
    r = captions["reels"]
    for when, kind, n in todo:
        stamp = when.strftime("%Y-%m-%dT%H:%M:00Z")
        cat = pick_category(pool, taken, n, last_cats, rng)
        if not cat:
            print(f"- {stamp}  {kind} : pas assez d'images neuves, créneau laissé vide.")
            continue
        picks = take(pool, cat, n, taken, rng)
        last_cats = (last_cats + [cat])[-2:]
        print(f"- {stamp}  {kind.upper()} [{cat}] " + " | ".join(p["title"] for p in picks))
        if DRY:
            continue
        ids = [p["id"] for p in picks]
        entry = {"id": f"{'reel' if kind == 'reel' else 'auto'}-{when.strftime('%Y%m%d-%H%M')}",
                 "type": kind, "scheduled_at": stamp, "status": "pending"}
        if kind == "reel":
            entry.update({
                "caption": f"{r['captions'].get(cat) or r['captions']['_defaut']}\n\n{captions['appel']}\n\n{cfg['hashtags']}",
                "hook": r["hooks"].get(cat) or r["hooks"]["_defaut"], "cta": r["cta"],
                "slides": [{"image": p["image"], "text": p["title"]} for p in picks], "source_ids": ids})
        else:
            rels = []
            for p in picks:
                rel = f"images/auto/{p['id']}.jpg"
                to_jpeg(p["image"], os.path.join(ROOT, rel), force_45=(kind == "carousel"))
                rels.append(rel)
            if kind == "carousel":
                c = captions["carousel"]
                label = CAT_LABELS.get(cat, "visuels")
                body = rng.choice(c["modeles"]).replace("{n}", str(n)).replace("{categorie}", label)
                titres = "\n".join(f"{i + 1}. {p['title']}" for i, p in enumerate(picks))
                entry.update({"caption": f"{body}\n\n{titres}\n\n{captions['appel']}\n\n{cfg['hashtags']}",
                              "images": rels, "source_ids": ids})
            else:
                entry.update({"caption": make_caption(picks[0], captions, cfg["hashtags"], rng),
                              "images": rels, "source_id": ids[0]})
        queue.append(entry)
        for p in picks:
            history.append({"id": p["id"], "category": cat, "reel": kind == "reel",
                            "at": now.isoformat(timespec="seconds")})
    if not DRY:
        save("queue/posts.json", queue)
        save("queue/history.json", history)
    return 0


if __name__ == "__main__":
    sys.exit(main())
