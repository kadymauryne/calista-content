#!/usr/bin/env python3
"""Publie sur Instagram les posts de queue/posts.json dont l'heure est passée.

Tout fonctionne avec la bibliothèque standard de Python (aucune installation).
Variables d'environnement :
  IG_TOKEN    jeton d'accès Instagram (secret GitHub)
  IG_USER_ID  identifiant du compte Instagram (secret GitHub)
  DRY_RUN=1   n'appelle pas Instagram, affiche seulement ce qui serait fait
  MAX_PER_RUN nombre maximum de publications par exécution (défaut 2)
"""
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

API = "https://graph.instagram.com/v21.0"
QUEUE = os.path.join(os.path.dirname(__file__), "..", "queue", "posts.json")
REPO = os.environ.get("GITHUB_REPOSITORY", "kadymauryne/calista-content")
BRANCH = os.environ.get("PUBLISH_BRANCH", "main")
DRY = os.environ.get("DRY_RUN") == "1"
TOKEN = os.environ.get("IG_TOKEN", "")
USER_ID = os.environ.get("IG_USER_ID", "")
MAX_PER_RUN = int(os.environ.get("MAX_PER_RUN", "2"))


def public_url(path):
    """Adresse publique d'un fichier du dépôt (Meta va le chercher lui-même)."""
    if path.startswith("http"):
        return path
    return f"https://raw.githubusercontent.com/{REPO}/{BRANCH}/{path.lstrip('/')}"


def call(method, path, params):
    params = dict(params, access_token=TOKEN)
    data = urllib.parse.urlencode(params).encode()
    url = f"{API}/{path}"
    if method == "GET":
        url += "?" + data.decode()
        data = None
    req = urllib.request.Request(url, data=data, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        raise RuntimeError(f"Instagram a répondu {e.code}: {body}") from None


def wait_ready(container_id, tries=40):
    for _ in range(tries):
        status = call("GET", container_id, {"fields": "status_code,status"})
        code = status.get("status_code")
        if code == "FINISHED":
            return
        if code in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"Traitement du média refusé: {status}")
        time.sleep(10)
    raise RuntimeError("Instagram met trop de temps à traiter le média")


def publish_container(container_id):
    wait_ready(container_id)
    return call("POST", f"{USER_ID}/media_publish", {"creation_id": container_id})["id"]


def git(*args):
    root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
    r = subprocess.run(["git", "-c", "user.name=calista-bot",
                        "-c", "user.email=calista-bot@users.noreply.github.com", *args],
                       cwd=root, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} : {r.stderr[-400:]}")
    return r.stdout.strip()


def publish_montage_reel(post):
    """Fabrique la vidéo, la dépose dans le dépôt public, puis donne à Instagram une adresse web
    (Instagram exige video_url avec ce type de connexion)."""
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.join(here, "..")
    rel = f"videos/{post['id']}.mp4"
    out = os.path.join(root, rel)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        spec = os.path.join(tmp, "spec.json")
        with open(spec, "w", encoding="utf-8") as f:
            json.dump({k: post[k] for k in ("hook", "cta", "cta_line", "slides") if k in post}, f,
                      ensure_ascii=False)
        r = subprocess.run([sys.executable, os.path.join(here, "build_reel.py"), spec, out],
                           capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError("Montage du réel impossible : " + (r.stderr or r.stdout)[-800:])
    git("add", rel)
    git("commit", "-m", f"Vidéo du réel {post['id']}")
    git("pull", "--rebase", "origin", BRANCH)
    git("push", "origin", f"HEAD:{BRANCH}")
    sha = git("rev-parse", "HEAD")
    candidates = [f"https://cdn.jsdelivr.net/gh/{REPO}@{sha}/{rel}", public_url(rel)]
    errors = []
    for url in candidates:
        try:
            c = call("POST", f"{USER_ID}/media", {"media_type": "REELS", "video_url": url,
                                                  "caption": post.get("caption", ""),
                                                  "share_to_feed": "true"})
            media_id = publish_container(c["id"])
            post["video_url"] = url
            try:
                os.remove(out)          # la vidéo n'est plus utile une fois publiée
            except OSError:
                pass
            return media_id
        except Exception as e:
            errors.append(f"{url} -> {e}")
            print(f"   tentative échouée : {url} ({str(e)[:200]})")
    raise RuntimeError(" | ".join(errors)[:1100])


def publish(post):
    kind = post.get("type", "image")
    caption = post.get("caption", "")
    if kind == "image":
        c = call("POST", f"{USER_ID}/media",
                 {"image_url": public_url(post["images"][0]), "caption": caption})
        return publish_container(c["id"])
    if kind == "carousel":
        kids = []
        for img in post["images"]:
            c = call("POST", f"{USER_ID}/media",
                     {"image_url": public_url(img), "is_carousel_item": "true"})
            kids.append(c["id"])
        for k in kids:
            wait_ready(k)
        c = call("POST", f"{USER_ID}/media",
                 {"media_type": "CAROUSEL", "children": ",".join(kids), "caption": caption})
        return publish_container(c["id"])
    if kind == "reel" and post.get("slides"):
        return publish_montage_reel(post)
    if kind == "reel":
        c = call("POST", f"{USER_ID}/media",
                 {"media_type": "REELS", "video_url": public_url(post["video"]),
                  "caption": caption, "share_to_feed": "true"})
        return publish_container(c["id"])
    raise ValueError(f"Type inconnu: {kind}")


def main():
    with open(QUEUE, encoding="utf-8") as f:
        posts = json.load(f)
    now = datetime.now(timezone.utc)
    due = [p for p in posts if p.get("status") == "pending"
           and datetime.fromisoformat(p["scheduled_at"].replace("Z", "+00:00")) <= now]
    due.sort(key=lambda p: p["scheduled_at"])
    print(f"{len(due)} publication(s) à faire maintenant.")
    failed = False
    for post in due[:MAX_PER_RUN]:
        print(f"-> {post['id']} ({post.get('type', 'image')})")
        if DRY:
            print("   [DRY_RUN] rien n'est envoyé à Instagram.")
            continue
        try:
            post["ig_media_id"] = publish(post)
            post["status"] = "published"
            post["published_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
            print(f"   publié: {post['ig_media_id']}")
        except Exception as e:  # on garde la trace et on passe au suivant
            post["status"] = "failed"
            post["error"] = str(e)[:1200]
            failed = True
            print(f"   ÉCHEC: {e}", file=sys.stderr)
        with open(QUEUE, "w", encoding="utf-8") as f:
            json.dump(posts, f, ensure_ascii=False, indent=2)
            f.write("\n")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
