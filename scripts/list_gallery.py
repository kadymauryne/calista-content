#!/usr/bin/env python3
"""Affiche le contenu de la galerie Calista (titres, catégories) pour vérification. Lecture seule."""
import collections
import re
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from plan_week import fetch_prompts

ps = fetch_prompts()
print(f"{len(ps)} prompts")
print(collections.Counter(p["category"] for p in ps))
kw = re.compile(r"baddie|bad girl|noel|noël|christmas|no[eë]l", re.I)
print("--- titres contenant baddie / noël ---")
for p in ps:
    if kw.search(p["title"]):
        print(f"{p['id']} | {p['category']} | {p['title']} | premium={p['premium']}")
print("--- tous les titres de portraits ---")
for p in sorted(ps, key=lambda p: p["title"]):
    if p["category"] == "portraits":
        print(p["title"])
