# pronote-extractor

Microservice qui transforme un **emploi du temps PRONOTE exporté en PDF** en JSON structuré.

Le texte et les rectangles sont lus directement dans le PDF vectoriel avec `pdfplumber`. Il n'y a **pas d'OCR**, pas de LLM, pas de réseau et pas de Docker. Le résultat est déterministe et prend environ 0,3 s par fichier.

**Seul le PDF est accepté.** Le type est détecté par le contenu (signature `%PDF-`), jamais par l'extension. Une image (PNG, JPEG) ou tout autre fichier renvoie `unsupported_type`.

L'iCal PRONOTE, quand l'établissement l'active, reste la meilleure source. Il est traité directement par l'app, hors de ce service.

Références (égalité stricte, ordre compris) :
- `tests/fixtures/noam.pdf` (lycée Gustave Eiffel, quinzaines Q1/Q2) → **34/34 cours** (`noam.expected.json`, annexe B) ;
- `tests/fixtures/gounod.pdf` (collège Gounod, semaines A/B) → **33/33 cours** (`gounod.expected.json`, transcrit à la main depuis le rendu du PDF et validé le 2026-10-28).

## Installation (sans Docker)

```bash
scripts/install.sh      # uv (si absent) puis `uv sync --frozen` dans .venv ; aucune dépendance système
.venv/bin/pytest -q
```

Python 3.12. Dépendances figées dans `pyproject.toml` (versions exactes) et `uv.lock` : `pdfplumber`, `fastapi`, `uvicorn`, `python-multipart`, `pytest`, `httpx`.

## Utilisation

```bash
.venv/bin/python -m pronote_extractor edt.pdf > edt.json
.venv/bin/uvicorn pronote_extractor.api:app --host 127.0.0.1 --port 8765
```

Pour le faire tourner en service sous Linux : `scripts/pronote-extractor.service` (systemd ; adapter `User` et `WorkingDirectory`). Le service écoute sur `127.0.0.1` uniquement.

## API

### `POST /extract`
`multipart/form-data`, champ `file` (PDF, ≤ 10 Mo) → `200` :

```json
{
  "source": "pdf",
  "etablissement": "LYCEE GUSTAVE EIFFEL",
  "creneaux": ["08:05", "09:05", "10:00", "10:15"],
  "cours": [
    {"jour": "mercredi", "debut": "10:15", "fin": "11:15", "matiere": "ALLEMAND LV2",
     "profs": ["FOUQUERAY M."], "groupe": "2GT1_ALLEMAND", "salles": ["G 2"],
     "quinzaine": "Q1", "demi_case": true, "pictogramme": false, "horaire_estime": false, "page": 1}
  ],
  "warnings": []
}
```

| Champ | Sens |
|---|---|
| `etablissement` | lu dans l'en-tête (ligne commençant par LYCÉE / COLLÈGE) |
| `creneaux` | libellés de l'axe horaire, toutes pages confondues |
| `matiere` | libellé brut PRONOTE (les libellés lisibles sont gérés côté app) |
| `quinzaine` | alternance telle qu'écrite par PRONOTE : `"Q1"`/`"Q2"` (lycée), `"A"`/`"B"` (collège, lettre encadrée), ou `null` pour toutes les semaines |
| `demi_case` | case de largeur < 75 % d'une colonne : partagée avec un autre groupe |
| `pictogramme` | glyphe d'icône PRONOTE (zone Unicode privée) présent dans la case ; sens inconnu |
| `horaire_estime` | case non alignée sur un libellé d'axe : horaire interpolé |
| `page` | numéro de page (1 = première) ; une page = une semaine ou une quinzaine |

Erreurs : `{"error": <code>, "detail": <texte>}`

| Statut | `error` | Cas |
|---|---|---|
| 422 | `unsupported_type` | pas un PDF (image, texte…) |
| 422 | `invalid_file` | PDF corrompu |
| 422 | `no_grid` | PDF sans rectangles ni libellés horaires (par ex. scanné) : exporter le PDF depuis PRONOTE |
| 413 | `too_large` | fichier > 10 Mo |

### `GET /health`
`{"ok": true, "pdfplumber": "0.11.10"}`

### Warnings
Un warning qui porte sur un cours commence par `"<jour> <HH:MM>"`. Dans un PDF de plusieurs pages, il est préfixé par `"page N : "`.
- `case à cheval sur un créneau, horaire interpolé`
- `aucun prof lu`
- `page N : pas de grille d'emploi du temps, ignorée`

## Algorithme (`pdf/`)

1. `dedupe_chars()` supprime les caractères doublés par le gras simulé de PRONOTE. Les pictogrammes (U+E000–U+F8FF) sont retirés du texte, et leur présence est notée dans `pictogramme`.
2. Le cadre est le plus grand rectangle. Chaque autre rectangle de plus de 20 × 10 pt est un cours, y compris les fonds gris clairs.
3. Le jour d'une case est l'en-tête `lundi…samedi` le plus proche en x. Le samedi est pris en charge si son en-tête existe.
4. Axe horaire : on garde les libellés `NhMM` dont `x0` est à gauche de la grille. À chaque frontière horizontale, on regarde les libellés situés entre −12 et +6 pt : le plus tardif est le début de la ligne suivante, le plus tôt la fin de la ligne précédente. Cela gère les récréations (`10h00`/`10h15`).
5. Une frontière sans libellé (case d'une ligne et demie) est interpolée linéairement, arrondie à 5 min, avec `horaire_estime: true` et un warning. **Attention à l'arrondi** : Python arrondit au pair. Au milieu géométrique exact d'une ligne 15:20–16:15 (947,5 min), on obtient donc 15:50. Dans `noam.pdf`, la frontière réelle tombe à 947,4 min, ce qui donne 15:45. Les deux cas sont couverts par des tests.
6. Texte d'une case :
   - dernière ligne finissant par `Q1`/`Q2` → quinzaine ;
   - à défaut, lettre seule (A, B…) dans un petit cadre (≤ 20 × 12 pt) en coin de case → quinzaine (semaines A/B du collège). La lettre est reconnue par la géométrie et retirée du texte, pour ne pas finir dans les salles ;
   - ligne `[...]` → groupe ;
   - lignes `NOM X.` → profs ;
   - première ligne restante → matière ;
   - lignes suivantes → salles, découpées sur `/` (lycée) ou `,` (collège).
7. Fusion : deux cases du même cours (même jour, matière, profs, groupe, salles et quinzaine) sont fusionnées si `fin == debut`. Deux cours séparés par une récréation restent deux entrées. La fusion se fait page par page.

## Tests

| Fichier | Contenu |
|---|---|
| `test_golden_pdf.py` | prototype (annexe A) et package : égalité stricte des `cours` (ordre compris) et des `creneaux` sur noam et gounod ; entrée `bytes` |
| `test_detect.py` | signature ; PDF renommé `.png` traité comme PDF ; texte, PNG, JPEG → `unsupported_type` ; CLI |
| `test_pdf_robustness.py` | interpolation, samedi, multi-pages, page sans grille, `no_grid`, PDF corrompu, lettre de semaine encadrée (et non encadrée), séparateurs de salles |
| `test_api.py` | contrat HTTP et toutes les erreurs |

Les PDF synthétiques des tests sont générés par `tests/pdfgen.py`, sans dépendance supplémentaire. `tests/reference/pronote_pdf_extract.py` est le prototype de l'annexe A, recopié tel quel.

Règle : ne **jamais** modifier la vérité terrain pour faire passer un test.

## Limites connues

- Deux échantillons d'une page chacun : un lycée et un collège. Il manque encore un PDF de plusieurs pages réel.
- Le PDF annuel donne l'emploi du temps type, avec les profs titulaires : les remplacements ponctuels (affichés sur l'écran de la semaine dans PRONOTE) n'y figurent pas.
- Les deux cours du lundi après-midi (Physique-Chimie 14:10–15:45, SVT 15:45–17:15) ont un horaire **interpolé**, à confirmer dans PRONOTE. Si l'heure réelle diffère, il faut corriger la vérité terrain **et** l'algorithme.
- Le sens du pictogramme est inconnu.
- Les PDF scannés sont rejetés (`no_grid`).
- Il faut ajouter d'autres PDF (autres établissements, plusieurs pages), chacun vérifié à la main.

## Intégration (hors de ce repo)

### NestJS : `POST /timetable/import`

```ts
@Controller('timetable')
export class TimetableController {
  constructor(private readonly http: HttpService) {}

  @Post('import')
  @UseInterceptors(FileInterceptor('file', { limits: { fileSize: 10 * 1024 * 1024 } }))
  async import(@UploadedFile() file: Express.Multer.File) {
    const form = new FormData();
    form.append('file', new Blob([file.buffer]), file.originalname);
    try {
      const { data } = await firstValueFrom(
        this.http.post(`${process.env.EXTRACTOR_URL ?? 'http://127.0.0.1:8765'}/extract`, form, { timeout: 30_000 }),
      );
      return data;
    } catch (e) {
      const r = e.response;
      if (r?.status === 422 || r?.status === 413) throw new UnprocessableEntityException(r.data);
      throw new BadGatewayException('pronote-extractor indisponible');
    }
  }
}
```

`TimetableModule` importe `HttpModule`. Flutter ne parle qu'à NestJS.

### Flutter
- Modèle `Lesson` : `day`, `start`, `end`, `subject`, `teachers`, `group`, `rooms`, `fortnight` (Q1/Q2, A/B ou null), `halfCell`, `pictogram`, `estimatedTime`, `page`.
- Écran de validation : surligner les cours cités dans `warnings` et ceux dont `horaire_estime` vaut `true`. Chaque champ reste éditable avant l'enregistrement.
- Filtre d'alternance : les valeurs dépendent de l'établissement (`Q1`/`Q2`, `A`/`B`) ; proposer celles présentes dans la réponse.
- Table de libellés lisibles côté app (`HIST.GEO.EN.MOR.CIV.` → « Histoire-Géo · EMC »).
- Ordre proposé à l'utilisateur : lien iCal, sinon export PDF. Seul le PDF est accepté : pas de capture d'écran.
