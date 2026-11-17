# calista-content

Publication automatique sur l'Instagram de Calista (galerie de prompts IA).

- `queue/posts.json` : la file des publications (texte, images, date et heure).
- `images/` : les visuels. Ils doivent être en JPEG.
- `scripts/publish.py` : publie les posts dont l'heure est passée.
- `.github/workflows/publish.yml` : lance le script toutes les heures.
- `.github/workflows/token.yml` : vérifie chaque lundi que le jeton Instagram est valide.

Secrets GitHub à créer (Settings > Secrets and variables > Actions) : `IG_TOKEN` et `IG_USER_ID`.

## Calendrier éditorial Décembre 2026 - Janvier 2027

`config/calendrier.json` contient les 27 publications du calendrier (date, heure, format, accroche, légende, type de visuels). Chaque dimanche à 20 h, `scripts/plan_week.py` remplit la file de la semaine suivante : pour les dates couvertes par le calendrier il suit le calendrier, sinon il suit `config/schedule.json`. Une entrée marquée `draft` (ou sans visuels adaptés) est créée en brouillon et n'est jamais publiée tant que son statut n'est pas passé à `pending` dans `queue/posts.json`.
