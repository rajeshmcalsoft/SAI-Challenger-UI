# SAI-Challenger-UI

A web UI for the SAI-Challenger PoC. It shows targets, runs, results and comparisons, and can start runs through
`scripts/poc/run_poc.sh` in the SAI-Challenger checkout.

- `server/` is the Python API (FastAPI).
- `web/` is the React front end (Vite, TypeScript).

New to the project? Start with [How the SAI Conformance UI works](docs/HOW_THE_UI_WORKS.md): the background, the goal,
how every part works, the project steps and why they were chosen, and answers to common questions.

## Requirements

- Linux with Python 3.12 or newer
- Node.js 20 or newer, with npm
- A SAI-Challenger checkout (default location: `~/SAI-Challenger`)

## Setup and install

```bash
git clone git@github.com:rajeshmcalsoft/SAI-Challenger-UI.git
cd SAI-Challenger-UI

# Server
cd server
python3 -m venv .venv
.venv/bin/pip install -e ".[server,dev]"

# Web app
cd ../web
npm install
npm run build
```

## Run

```bash
cd server
.venv/bin/sai-challenger-ui --port 8770
```

Open http://127.0.0.1:8770 in a browser. The server listens on this machine only by default.

If your SAI-Challenger checkout is not in `~/SAI-Challenger`, set its path first:

```bash
export SAI_CHALLENGER_UI_SC_ROOT=/path/to/SAI-Challenger
```

## Develop (optional)

```bash
# Terminal 1: API on port 8765
cd server && .venv/bin/sai-challenger-ui

# Terminal 2: web app with hot reload on http://localhost:5173
cd web && npm run dev
```

## Test

```bash
cd server
.venv/bin/pytest -q
```
