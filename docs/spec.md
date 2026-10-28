# Service d'extraction d'emploi du temps PRONOTE (v3 : PDF seul)

Remplace la spec v2 (PDF + capture d'écran). **La voie capture d'écran est abandonnée** : plus d'OCR, de Tesseract ni de traitement d'image.

## 1. Objectif

Transformer un **emploi du temps PRONOTE exporté en PDF** en **JSON structuré fiable**, consommé par une app Flutter via le backend Go (Airswop).

Le PDF PRONOTE est vectoriel : le texte et les rectangles sont lus directement, sans OCR. L'iCal PRONOTE, quand l'établissement l'active, reste la meilleure source ; il est hors périmètre et traité directement par l'app.

Plancher de fiabilité : les deux golden tests (§8) passent, en égalité stricte.

## 2. Décisions (ne pas rediscuter)

| Sujet | Décision | Raison |
|---|---|---|
| Entrée | **PDF exporté par PRONOTE uniquement** | Capture abandonnée (décision du 2026-10-28) : l'OCR était lent, fragile et peu fiable comparé au PDF |
| Langage | **Python 3.12** + `pdfplumber` | Caractères, mots, rectangles, couleurs, dédoublonnage du gras simulé, PDF chiffrés RC4 sans mot de passe |
| Approche | Géométrie déterministe, jamais devinée | Fiabilité, testabilité |
| Pas de LLM | Aucun appel LLM | Déterminisme, coût nul |
| Intégration | **Commande** (`python -m pronote_extractor <fichier>`) lancée par le backend Go ; pas de service HTTP | Rien à faire tourner en permanence ; ~0,5 s par import, démarrage compris (décision du 2026-10-29, NestJS abandonné) |
| Déploiement | **Sans Docker** : venv uv installé à côté du backend | Flutter ne parle qu'au backend Go |

## 3. Architecture

```
Flutter ──(PDF)──► backend Go ──(lance)──► python -m pronote_extractor <fichier>   (pdfplumber)
Flutter ◄── JSON + warnings ───┘ ◄── stdout (JSON) / stderr (refus) ──┘
Flutter : écran de validation (cours en warning et horaires estimés surlignés) → enregistrement
```

Type d'entrée détecté par **contenu** (signature `%PDF-` dans le premier Kio), jamais par l'extension. Tout autre contenu, images comprises, est refusé avec `unsupported_type`.

## 4. Arborescence

```
pronote-extractor/
├── pyproject.toml, uv.lock, README.md
├── docs/spec.md                      # ce document
├── scripts/install.sh                # uv + uv sync ; aucune dépendance système
├── src/pronote_extractor/
│   ├── schema.py     # modèle de sortie (dataclasses)
│   ├── detect.py     # signature PDF
│   ├── errors.py     # ExtractionError(code, detail)
│   ├── pdf/extract.py, pdf/parse.py
│   └── cli.py        # python -m pronote_extractor edt.pdf (interface lue par le backend)
└── tests/
    ├── fixtures/noam.pdf + noam.expected.json      # lycée, quinzaines Q1/Q2
    ├── fixtures/gounod.pdf + gounod.expected.json  # collège, semaines A/B
    ├── reference/pronote_pdf_extract.py            # prototype d'origine (spec v2, annexe A), verbatim
    ├── pdfgen.py                                   # générateur de PDF synthétiques
    └── test_*.py
```

## 5. Modèle de sortie

```json
{
  "source": "pdf",
  "etablissement": "LYCEE GUSTAVE EIFFEL",
  "creneaux": ["08:05", "09:05", "10:00", "10:15"],
  "cours": [
    { "jour": "mercredi", "debut": "10:15", "fin": "11:15", "matiere": "ALLEMAND LV2",
      "profs": ["FOUQUERAY M."], "groupe": "2GT1_ALLEMAND", "salles": ["G 2"],
      "quinzaine": "Q1", "demi_case": true, "pictogramme": false, "horaire_estime": false, "page": 1 }
  ],
  "warnings": []
}
```

| Champ | Sens |
|---|---|
| `source` | toujours `"pdf"` |
| `etablissement` | ligne d'en-tête commençant par LYCÉE / COLLÈGE, sinon `null` |
| `creneaux` | libellés de l'axe horaire, toutes pages, triés |
| `jour` | `lundi` … `samedi` |
| `debut`, `fin` | `HH:MM`, issus de l'axe ou interpolés |
| `matiere` | libellé brut PRONOTE ; les libellés lisibles sont gérés par l'app |
| `profs`, `groupe`, `salles` | tels qu'écrits dans le PDF (profs titulaires ; les remplacements ponctuels n'apparaissent pas dans l'export annuel) |
| `quinzaine` | **libellé d'alternance tel qu'écrit dans le PDF**, sans conversion : `"Q1"`/`"Q2"` (lycée), `"A"`/`"B"` (collège), `null` = toutes les semaines |
| `demi_case` | case partagée avec un autre groupe ou une autre semaine |
| `pictogramme` | glyphe d'icône PRONOTE (Unicode privé) dans la case ; sens inconnu, conservé |
| `horaire_estime` | case non alignée sur un libellé d'axe : horaire interpolé |
| `page` | page du PDF (1 = première) ; une page = une semaine, une quinzaine ou l'année type |

## 6. Algorithme

1. `page.dedupe_chars()` supprime les caractères doublés par le gras simulé.
2. Les caractères `U+E000–U+F8FF` (pictogrammes) sont retirés du texte ; leur présence est notée par case.
3. **Cadre** = plus grand rectangle ; **cours** = tous les autres rectangles de plus de 20 × 10 pt, fonds gris clairs compris.
4. **Jours** : mots d'en-tête `lundi…samedi` ; le jour d'une case est l'en-tête dont le centre x est le plus proche. Le samedi est géré s'il a un en-tête.
5. **Axe** : mots `NhMM` dont `x0` est à gauche de la grille (filtrer sur `x0`, pas `x1` : un glyphe collé à certains libellés déborde). À chaque frontière horizontale, on prend les libellés entre −12 et +6 pt : le plus tardif est le début de la ligne suivante, le plus tôt la fin de la précédente (récréations `10h00`/`10h15`).
6. **Frontière sans libellé** : interpolation linéaire entre les frontières étiquetées qui l'encadrent, arrondie à 5 min (arrondi Python, au pair), `horaire_estime: true` + warning.
7. **Marqueur de semaine** (collège) : une lettre majuscule seule dans un petit cadre (≤ 20 × 12 pt) à l'intérieur de la case. Elle est retirée du texte de la case et devient `quinzaine`.
8. **Texte** : `within_bbox(case).extract_text()`, lignes non vides.
   - Dernière ligne se terminant par `Q1`/`Q2` → `quinzaine` (prioritaire sur le marqueur).
   - Ligne `[...]` → groupe.
   - Lignes `NOM X.` → profs.
   - Première ligne restante → matière ; lignes suivantes → salles, découpées sur `/` ou `,`.
9. **demi_case** : largeur < 75 % d'une colonne jour.
10. **Fusion** : même cours (jour, matière, profs, groupe, salles, quinzaine) sur deux cases dont `fin == debut`. Deux cours séparés par une récréation restent deux entrées. La fusion ne franchit pas les pages.
11. **Multi-pages** : chaque page est traitée séparément. Une page sans grille est ignorée avec un warning ; si aucune page n'a de grille → `no_grid`. Dans un PDF de plusieurs pages, les warnings sont préfixés par `page N : `.

## 7. Interface (commande)

`python -I -m pronote_extractor <fichier>` :

| Code de sortie | Sortie |
|---|---|
| `0` | modèle du §5 en JSON sur stdout |
| `1` | refus : `{"error": <code>, "detail": <texte>}` sur stderr, stdout vide |
| `2` | mauvais usage |
| autre | plantage (trace Python sur stderr) |

| `error` | Cas |
|---|---|
| `unsupported_type` | pas un PDF (image, texte…) |
| `invalid_file` | PDF corrompu |
| `no_grid` | aucune page avec rectangles, en-têtes de jours et libellés horaires (PDF scanné) |

La taille maximale et le délai relèvent du backend. Warnings : `"<jour> <HH:MM> … : case à cheval sur un créneau, horaire interpolé"`, `"<jour> <HH:MM> : aucun prof lu"`, `"page N : pas de grille d'emploi du temps, ignorée"`.

## 8. Tests (verts en permanence)

| Fixture | Exigence |
|---|---|
| `noam.pdf` | `cours` (hors `page`) **strictement égal**, ordre compris, à `noam.expected.json` ; `creneaux` égaux. Horaires interpolés du lundi confirmés dans PRONOTE le 2026-10-29 |
| `gounod.pdf` | idem avec `gounod.expected.json` (transcrit à la main, validé le 2026-10-28) ; aucun warning |
| prototype de référence | le package reproduit sa sortie sur `noam.pdf` |
| PDF synthétiques | samedi, multi-pages, page sans grille, `no_grid`, PDF corrompu, marqueur de semaine (avec et sans cadre), séparateurs de salles, interpolation (géométrie réelle → 15:45 ; milieu exact → 15:50) |
| détection / commande | PDF renommé `.png` traité comme PDF ; texte, PNG, JPEG → `unsupported_type` ; codes de sortie et erreurs JSON sur stderr |

## 9. Règles à ne pas casser

- Les golden tests passent après chaque modification.
- Ne jamais modifier une vérité terrain pour faire passer un test. Une nouvelle fixture se transcrit à la main depuis le PDF, puis se fait valider par un humain.
- Pas de LLM, pas de service externe, pas de réseau dans le pipeline.
- Pas de Docker.
- Pas de créneau horaire codé en dur : ils viennent toujours de l'axe lu.
- Toute heuristique nouvelle est couverte par un test.

## 10. Intégration (hors de ce dépôt)

- **Backend Go (Airswop)** : `POST /api/v1/timetable/import` (clé d'API, multipart, champ `file`) lance la commande (`TIMETABLE_PYTHON`, délai `TIMETABLE_TIMEOUT` 30 s, taille `TIMETABLE_MAX_BYTES` 10 Mo) et traduit les refus en codes HTTP (`NOT_A_PDF`, `INVALID_PDF`, `NO_TIMETABLE` → 422 ; 413 ; 504).
- **Flutter** : modèle `Lesson` aligné sur le §5 ; écran de validation surlignant les cours en warning et ceux en `horaire_estime: true`, avec édition de chaque champ avant enregistrement ; filtre d'alternance sur les libellés présents dans la réponse (`Q1`/`Q2`, `A`/`B`) ; table de libellés lisibles côté app. Ordre proposé : lien iCal, sinon export PDF.

## 11. Limites connues

- Deux échantillons, des exports annuels d'une page (un lycée, un collège). Le multi-pages n'est testé que sur des PDF synthétiques.
- Sens du pictogramme inconnu.
- PDF scannés non supportés (`no_grid`).
- Ajouter des PDF d'autres établissements dès que possible, chacun validé à la main.
