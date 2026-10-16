#!/usr/bin/env python3
"""Prolonge le jeton Instagram et échoue si l'expiration approche (GitHub t'envoie alors un e-mail)."""
import json
import os
import sys
import urllib.parse
import urllib.request

token = os.environ.get("IG_TOKEN", "")
if not token:
    sys.exit("IG_TOKEN absent")
url = "https://graph.instagram.com/refresh_access_token?" + urllib.parse.urlencode(
    {"grant_type": "ig_refresh_token", "access_token": token})
try:
    with urllib.request.urlopen(url, timeout=60) as r:
        data = json.loads(r.read().decode())
except Exception as e:
    sys.exit(f"Le jeton n'a pas pu être prolongé: {e}")
days = int(data.get("expires_in", 0)) // 86400
print(f"Jeton valide encore environ {days} jours.")
sys.exit(0 if days >= 10 else "Jeton bientôt expiré: régénère-le dans l'app Meta.")
