# ArchiTracker

Reflex app for Archimonster tracking, scanning, trading, and Metamob sync.

## Stack

- Python 3.10+
- Reflex
- UI automation scanner (`scripts/scan.py`)

## Project Layout

- `architracker/`: Reflex app code (state, pages, components)
- `scripts/`: scanner and legacy utility scripts
- `data/`: runtime app data
  - `archimonstres_par_zone.json` (zones/monsters source)
  - `archimonsterImg.png` (scanner template)
  - `results.json` (scan/tracker data, local)
  - `characters.json` (character list, local)
  - `metamob.config.json` (API key, local/private)

## Local Run

```bash
python -m venv .venv
# Windows PowerShell
# .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
reflex run
```

## Notes For Public Repo

- Sensitive/local files are gitignored:
  - `data/metamob.config.json`
  - `data/results.json`
  - `data/characters.json`
  - `.web/`, `.states/`, `logs/`, build artifacts
- Keep `data/archimonstres_par_zone.json` and `data/archimonsterImg.png` in repo if you want the app to run out of the box.

## Publish This Folder Only

From inside `archiTracker/`:

```bash
git init -b main
git add .
git commit -m "Initial public release"
git remote add origin <your-public-repo-url>
git push -u origin main
```
