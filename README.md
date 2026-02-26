# ArchiTracker

Reflex app for Archimonster tracking, scanning, trading, and Metamob sync.

## Stack

- Python 3.12.5+
- Reflex

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
pip install -r requirements.txt
reflex run
```

## Metamob API Key

Put your key in `data/metamob.config.json`:

```json
{
  "apiKey": "YOUR_METAMOB_API_KEY"
}
```

## features Overview

- `Characters`: create/manage characters and assign server/name used by the app.
- `Scanner`: launch/stop the scan script and scan archimonsters into the selected character profile.
- `Tracker`: browse and update collected/missing archimonsters with filters and step validation.
- `Trades`: compare with another player, select give/receive picks, and build a trade message.
- `Metamob`: generate/sync payloads and manage quest settings through the Metamob API.

## Notes For Public Repo

- Sensitive/local files are gitignored:
  - `data/metamob.config.json`
  - `data/results.json`
  - `data/characters.json`
  - `.web/`, `.states/`, `logs/`, build artifacts
- Keep `data/archimonstres_par_zone.json` and `data/archimonsterImg.png` in repo if you want the app to run out of the box.
