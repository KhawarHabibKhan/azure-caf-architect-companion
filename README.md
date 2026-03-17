# Azure CAF Architect Companion

AI agent workflow that automates the pre-deployment phases of Microsoft's [Cloud Adoption Framework (CAF)](https://learn.microsoft.com/en-us/azure/cloud-adoption-framework/overview). Takes a user's infrastructure description and produces cloud adoption recommendations with architecture diagrams and a detailed report.

## What It Does

Describe your current IT environment — infrastructure, applications, team, budget, compliance — and the agent pipeline produces:

1. **Readiness Assessment** — Cloud readiness scores, operating model recommendation (centralized/shared/decentralized), skills gap analysis
2. **Workload Classification** — Each application classified using the 7 R's (retire, retain, rehost, refactor, rearchitect, rebuild, replace)
3. **Migration Wave Plan** — Sequenced migration waves respecting dependencies
4. **Cost Estimation** — Real pricing from Azure Retail Prices API
5. **Risk Register** — Risks across compliance, security, operations, cost, data, and skills
6. **Governance Recommendations** — Azure Policy, tagging strategy, security baseline, cost management
7. **Landing Zone Design** — Management group hierarchy, hub-spoke network, subscription layout
8. **Architecture Diagram** — Interactive Excalidraw diagram + PNG export

## 3-Agent Pipeline

```
User Input → Agent 1: Assessment → Agent 2: Plan & Analyze → Agent 3: Design & Report
```

| Agent | What it does | CAF Phases |
|---|---|---|
| Assessment | Readiness, operating model, skills | Strategy |
| Plan & Analyze | 7 R's, waves, costs, risks, governance | Plan + Govern + Secure |
| Design & Report | Landing zone, diagram, report | Ready |

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 20+
- Azure OpenAI endpoint with GPT-4.1 deployment

### Setup

```bash
# Clone
git clone https://github.com/KhawarHabibKhan/azure-caf-architect-companion.git
cd azure-caf-architect-companion

# Python dependencies
pip install agent-framework --pre
pip install agent-framework-azure-ai --pre
pip install fastapi uvicorn python-dotenv httpx pyyaml rich Pillow python-multipart

# Configure
cp .env.template .env
# Edit .env with your Azure OpenAI credentials

# Frontend
cd frontend && npm install && cd ..
```

### Run (Web App)

```bash
# Terminal 1: Backend
python -m uvicorn api:app --reload

# Terminal 2: Frontend
cd frontend && npm run dev
```

Open http://localhost:5173

### Run (CLI)

```bash
python run_local.py scenarios/meditrack_healthcare.txt
```

### Run (Hosted Agent)

```bash
# Set AZURE_AI_PROJECT_ENDPOINT in .env
python main.py
```

## Project Structure

```
azure-caf-architect-companion/
├── tools.py              # Core engine (all logic)
├── api.py                # FastAPI backend
├── main.py               # Hosted agent entry point
├── run_local.py           # CLI runner
├── agent.yaml            # Foundry deployment manifest
├── knowledge/
│   ├── azure_services.json      # Azure service catalog
│   ├── compliance_controls.json # Compliance frameworks
│   └── caf_prompts.py           # Agent system prompts
├── frontend/             # React + Vite + Excalidraw
├── scenarios/            # Demo inputs
├── tests/                # Pytest suite
└── output/               # Generated diagrams and reports
```

## API Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/health` | Health check |
| POST | `/api/review` | Full pipeline (all 3 agents) |
| POST | `/api/assess` | Agent 1 only |
| POST | `/api/plan` | Agent 1 + Agent 2 |
| GET | `/api/download/png/{run_id}` | Download PNG diagram |
| GET | `/api/download/excalidraw/{run_id}` | Download Excalidraw file |

## Demo Scenarios

| Scenario | File | Description |
|---|---|---|
| Healthcare | `scenarios/meditrack_healthcare.txt` | 200 employees, HIPAA, 7 workloads |
| Manufacturing | `scenarios/contoso_manufacturing.txt` | 1,200 employees, ISO 27001, 10 workloads |
| SaaS Startup | `scenarios/startup_saas.txt` | 25 employees, AWS-to-Azure migration |

## Tech Stack

- **Backend:** Python, FastAPI, Microsoft Agent Framework
- **LLM:** Azure OpenAI (GPT-4.1)
- **Frontend:** React 18, Vite, Excalidraw
- **Pricing:** Azure Retail Prices API (live, no auth)
- **Diagrams:** Excalidraw JSON + Pillow PNG export

## License

MIT
