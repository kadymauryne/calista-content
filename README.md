# calista-content

Publication automatique sur l'Instagram de Calista (galerie de prompts IA).

- `queue/posts.json` : la file des publications (texte, images, date et heure).
- `images/` : les visuels. Ils doivent être en JPEG.
- `scripts/publish.py` : publie les posts dont l'heure est passée.
- `.github/workflows/publish.yml` : lance le script toutes les heures.
- `.github/workflows/token.yml` : vérifie chaque lundi que le jeton Instagram est valide.

Secrets GitHub à créer (Settings > Secrets and variables > Actions) : `IG_TOKEN` et `IG_USER_ID`.
