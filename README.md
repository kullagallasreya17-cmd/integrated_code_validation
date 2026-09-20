# Coding validation agent — Sreya's portion

This is the **Orchestrator + Code Quality + Frontend** slice of the
coding-validation-agent project, built to plug into the microservices
architecture agreed on for the team:

- **Sreya** — Orchestrator + Code Quality + Frontend *(this folder)*
- **Rakshitha** — Fix & Regeneration + Security + Database & Reports
- **Shifa** — Validation + Bug & Resource + Docker Sandbox

## What's here

```text
coding-validation-agent/
├── services/
│   ├── orchestrator-service/     LangGraph workflow (FastAPI)
│   └── code-quality-service/     Ruff + Pylint + Radon (FastAPI)
├── gateway/                     API entry point (FastAPI)
├── frontend/                     React + TypeScript + Vite UI
├── shared/schemas/                Common contracts (Finding, workflow, etc.)
└── docker-compose.yml             Runs the 3 services above; teammates'
                                    services are stubbed in as comments
```

## Running it locally

### Option A — Docker Compose (recommended)

```bash
docker compose up --build
```

- Frontend: http://localhost:5173
- Gateway: http://localhost:8000 (docs at /docs)
- Orchestrator: http://localhost:8001 (internal gateway target)
- Code quality service: http://localhost:8002 (docs at /docs)

The code-quality service accepts `POST /analyze` with a `project_id`, relative
Python `.py` files, and an optional subset of `ruff`, `pylint`, and `radon`.
It returns the shared findings contract used by the orchestrator. Inputs are
bounded by `QUALITY_MAX_FILES` and `QUALITY_MAX_FILE_SIZE_BYTES`; analyzer
failures are returned as low-severity findings while preserving results from
other analyzers.

### Option B — run each service manually

```bash
# Code quality service
cd services/code-quality-service
pip install -r requirements.txt
PYTHONPATH=../.. uvicorn app.main:app --reload --port 8002

# Orchestrator (in a second terminal)
cd services/orchestrator-service
pip install -r requirements.txt
ORCH_QUALITY_SERVICE_URL=http://localhost:8002 PYTHONPATH=../.. \
  uvicorn app.main:app --reload --port 8001

# Gateway (in a third terminal)
cd gateway
pip install -r requirements.txt
GATEWAY_ORCHESTRATOR_URL=http://localhost:8001 PYTHONPATH=.. \
   uvicorn app.main:app --reload --port 8000

# Frontend (in a fourth terminal)
cd frontend
npm install
VITE_API_BASE_URL=http://localhost:8000 npm run dev
```

`PYTHONPATH=../..` (pointing at the repo root, two levels up from each
service folder) is needed because both services import
`shared.schemas.*` from the repo-level `shared/` package.

## Running tests

```bash
cd services/code-quality-service && PYTHONPATH=../.. pytest
cd services/orchestrator-service && PYTHONPATH=../.. pytest
```

## Code map and useful commands

Run these commands from the repository root to understand where the main
application code lives and how it is used.

```powershell
Set-Location D:\projects\coding-validation-agent-sreya\coding-validation-agent
```

### List application source files

```powershell
Get-ChildItem .\gateway\app, .\services, .\shared, .\frontend\src -Recurse -File |
   Where-Object { $_.Extension -in ".py", ".ts", ".tsx", ".css" } |
   Select-Object -ExpandProperty FullName
```

### Find Python entry points

```powershell
Get-ChildItem . -Recurse -Filter main.py -File |
   Where-Object { $_.FullName -notmatch "\\.venv\\|site-packages" } |
   Select-Object -ExpandProperty FullName
```

The main Python entry points are:

```text
gateway/app/main.py                                  Gateway API
services/orchestrator-service/app/main.py            LangGraph orchestrator
services/code-quality-service/app/main.py             Code Quality API
```

### Find all API routes

```powershell
rg "@(app|router)\.(get|post|put|delete)|APIRouter" gateway services -g "*.py"
```

### Find orchestrator workflow usage

```powershell
rg "workflow|StateGraph|add_node|add_edge|should_retry|ainvoke|astream" `
   services/orchestrator-service/app -g "*.py"
```

### Find all agent/service clients

```powershell
Get-ChildItem .\services\orchestrator-service\app\services -File |
   Select-Object Name, FullName
```

```powershell
rg "from app\.services|security_client|quality_client|bug_resource_client|repair_client|sandbox_client|validation_client" `
   services/orchestrator-service/app -g "*.py"
```

### Find Code Quality tools and their usage

```powershell
Get-ChildItem .\services\code-quality-service\app\analyzers -File |
   Select-Object Name, FullName
```

```powershell
rg "run_ruff|run_pylint|run_radon|ruff|pylint|radon|normalize" `
   services/code-quality-service services/orchestrator-service -g "*.py"
```

Current tool ownership:

```text
services/code-quality-service/app/analyzers/ruff_analyzer.py
services/code-quality-service/app/analyzers/pylint_analyzer.py
services/code-quality-service/app/analyzers/radon_analyzer.py
services/code-quality-service/app/parsers/result_normalizer.py
```

### Find frontend pages, components, and API calls

```powershell
Get-ChildItem .\frontend\src -Recurse -File |
   Where-Object { $_.Extension -in ".tsx", ".ts" } |
   Select-Object -ExpandProperty FullName
```

```powershell
rg "api\.|fetch\(|EventSource|UploadPage|AnalysisPage|ResultsPage|FindingsReviewPage|RepairHistoryPage" `
   frontend/src -g "*.ts" -g "*.tsx"
```

### Run the automated checks

```powershell
Set-Location .\services\orchestrator-service
$env:PYTHONPATH = "../.."
.\.venv\Scripts\python.exe -m pytest -q

Set-Location ..\code-quality-service
$env:PYTHONPATH = "../.."
.\.venv\Scripts\python.exe -m pytest -q

Set-Location ..\..\frontend
npm run build
```

### Run the complete Docker application

```powershell
Set-Location D:\projects\coding-validation-agent-sreya\coding-validation-agent

$env:GATEWAY_PORT = "8010"
$env:ORCHESTRATOR_PORT = "8011"
$env:QUALITY_PORT = "8012"
$env:FRONTEND_PORT = "5174"
$env:FRONTEND_API_BASE_URL = "http://localhost:8010"

docker compose config --quiet
docker compose up --build -d
docker compose ps
```

Check the running services:

```powershell
Invoke-RestMethod http://localhost:8010/health
Invoke-RestMethod http://localhost:8011/health
Invoke-RestMethod http://localhost:8012/health
```

Open the application and API documentation:

```text
Frontend:      http://localhost:5174
Gateway docs:  http://localhost:8010/docs
Orchestrator:  http://localhost:8011/docs
Quality docs:  http://localhost:8012/docs
```

View service logs:

```powershell
docker compose logs -f orchestrator
docker compose logs -f code-quality
docker compose logs -f gateway
```

Stop the Docker application:

```powershell
docker compose down
```

## Person 1 verification runbook (Windows PowerShell)

From the repository root, use separate terminals for the services:

```powershell
# Terminal 1: code-quality service
Set-Location .\services\code-quality-service
$env:PYTHONPATH = "../.."
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8002

# Terminal 2: orchestrator / manager agent
Set-Location .\services\orchestrator-service
$env:PYTHONPATH = "../.."
$env:ORCH_QUALITY_SERVICE_URL = "http://localhost:8002"
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8001

# Terminal 3: gateway
Set-Location .\gateway
$env:PYTHONPATH = ".."
$env:GATEWAY_ORCHESTRATOR_URL = "http://localhost:8001"
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8000

# Terminal 4: frontend
Set-Location .\frontend
npm install
$env:VITE_API_BASE_URL = "http://localhost:8000"
npm run dev
```

Open `http://localhost:5173`. The currently available services are the
frontend, gateway, orchestrator, and code-quality agent. Security, repair,
sandbox, validation, and bug/resource services remain commented out in
`docker-compose.yml`; the orchestrator records those unavailable stages as
controlled failures and never marks unvalidated code as passed.

Useful checks after the services start:

```powershell
Invoke-RestMethod http://localhost:8000/health
Invoke-RestMethod http://localhost:8001/health
Invoke-RestMethod http://localhost:8002/health

Set-Location .\services\orchestrator-service
$env:PYTHONPATH = "../.."
python -m pytest -q

Set-Location ..\code-quality-service
$env:PYTHONPATH = "../.."
python -m pytest -q

Set-Location ..\..\frontend
npm run build
```

The manager status endpoint is available at
`GET http://localhost:8000/analysis/status/{project_id}` while a run is
queued or running, and after the final report is produced.

## A2A orchestrator integration

The orchestrator exposes an A2A-compatible task boundary in addition to its
existing gateway workflow APIs:

- `GET /.well-known/agent-card.json` discovers the orchestrator skills.
- `POST /a2a/v1/tasks` accepts `workflow.start`, `workflow.status`, and
   `agent.result` messages.

The A2A `workflow.start` task is translated into the existing
`StartAnalysisRequest` and runs through the same LangGraph workflow, so A2A
does not create a second orchestration path. Specialized agents can submit
normalized results with `agent.result`; their internal implementations remain
independent of the orchestrator.

## SRS coverage and current boundaries

Implemented in this repository: React/Monaco intake and review, Code Quality
Agent, AST-based Code Analysis, LangGraph coordination, shared finding
aggregation, bounded repair/validation routing, sandbox-gated validation,
stage/error history, repair-attempt records, report generation, status/SSE
progress, findings/report retrieval, structured workflow logging, and durable
local run history.

The Security, Bug & Resource, Fix & Regeneration, Docker Sandbox, and
Validation services are represented by HTTP adapters because their teammate
services are not present in this repository. The orchestrator will preserve
their failure evidence and will never mark a run passed when sandbox or
validation evidence is unavailable. PostgreSQL is also not present in the
current tree; `ORCH_RUN_STORE_PATH` provides a durable JSON fallback with the
same run-history boundary until a PostgreSQL service and credentials are
added. No LLM provider is configured, so explanations and repairs remain
downstream integration points rather than being fabricated locally.

## How this integrates with Rakshitha and Shifa's work

The orchestrator never imports another agent's code directly — it only
calls HTTP clients in `services/orchestrator-service/app/services/`:

| Client file | Calls | Owned by |
|---|---|---|
| `quality_client.py` | code-quality-service | Sreya (done) |
| `security_client.py` | security-service | Rakshitha |
| `repair_client.py` | repair-service | Rakshitha |
| `bug_resource_client.py` | bug-resource-service | Shifa |
| `sandbox_client.py` | sandbox-service | Shifa |
| `validation_client.py` | validation-service | Shifa |

Until those services exist, every placeholder client fails **gracefully**
(returns an empty findings list / a failed validation, never raises) so
the full LangGraph workflow can already be run and demoed end-to-end.
Once a teammate's service is ready, add its URL as an env var (see
`services/orchestrator-service/.env.example`) and uncomment its block in
`docker-compose.yml` — no orchestrator code needs to change, because the
integration boundary is already the shared `Finding` contract in
`shared/schemas/`.

## Next steps toward the final app

1. Rakshitha and Shifa add their six services under `services/`, each
   with its own `Dockerfile` and a `/analyze`, `/repair`, `/execute`, or
   `/validate` endpoint matching the shapes in `shared/schemas/workflow.py`.
2. Add an `gateway/` API-entry-point service in front of all of them
   (per the original architecture doc) so the frontend talks to one
   URL instead of the orchestrator directly.
3. Uncomment the corresponding services in `docker-compose.yml`.
4. Add `tests/integration/test_end_to_end.py` once all six agents exist.
