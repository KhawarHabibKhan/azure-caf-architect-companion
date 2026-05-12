"""
Azure CAF Architect Companion - FastAPI Backend
=================================================
Exposes the CAF assessment pipeline as REST endpoints.
Serves the React frontend static files in production.
"""

import json
import logging
import os
import re
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(override=True)

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from agents import run_pipeline, stream_pipeline
from tools import (
    parse_caf_input,
    run_assessment,
    run_plan,
)

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

logger = logging.getLogger("caf-companion.api")

MAX_INPUT_SIZE = 500_000  # ~500 KB

app = FastAPI(
    title="Azure CAF Architect Companion API",
    description="Automates pre-deployment phases of Microsoft's Cloud Adoption Framework.",
    version="0.1.0",
)

# CORS
_default_origins = ["http://localhost:5173", "http://localhost:8000"]
_origins = os.getenv("ALLOWED_ORIGINS", "").split(",") if os.getenv("ALLOWED_ORIGINS") else _default_origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _origins if o.strip()],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class ReviewRequest(BaseModel):
    content: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _validate_run_id(run_id: str) -> None:
    if not re.match(r"^[a-f0-9]{1,16}$", run_id):
        raise HTTPException(status_code=400, detail="Invalid run_id")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "Azure CAF Architect Companion"}


@app.get("/api/scenarios")
async def list_scenarios():
    """List available demo scenarios from the scenarios/ directory."""
    scenarios_dir = Path(__file__).parent / "scenarios"
    if not scenarios_dir.is_dir():
        return JSONResponse(content=[])

    scenarios = []
    for filepath in sorted(scenarios_dir.glob("*.txt")):
        content = filepath.read_text(encoding="utf-8")
        # Extract company name from first line (e.g. "Company: MediTrack Health Solutions")
        first_line = content.split("\n", 1)[0]
        name = first_line.replace("Company:", "").strip() if first_line.startswith("Company:") else filepath.stem.replace("_", " ").title()
        # Extract industry from second line if available
        lines = content.split("\n")
        industry = ""
        for line in lines[1:4]:
            if line.startswith("Industry:"):
                industry = line.replace("Industry:", "").strip()
                break
        scenarios.append({
            "id": filepath.stem,
            "name": name,
            "industry": industry,
            "filename": filepath.name,
            "content": content,
        })

    return JSONResponse(content=scenarios)


@app.post("/api/review")
async def review(req: ReviewRequest):
    """Run the full 3-agent CAF pipeline via the SequentialBuilder workflow."""
    if len(req.content) > MAX_INPUT_SIZE:
        raise HTTPException(status_code=400, detail=f"Input exceeds {MAX_INPUT_SIZE} characters")
    if not req.content.strip():
        raise HTTPException(status_code=400, detail="Content cannot be empty")

    try:
        report = await run_pipeline(req.content)
        return JSONResponse(content=report)
    except Exception as exc:
        logger.exception("Pipeline failed")
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/assess")
async def assess(req: ReviewRequest):
    """Run Agent 1 only: parse input + assessment."""
    if len(req.content) > MAX_INPUT_SIZE:
        raise HTTPException(status_code=400, detail=f"Input exceeds {MAX_INPUT_SIZE} characters")
    if not req.content.strip():
        raise HTTPException(status_code=400, detail="Content cannot be empty")

    try:
        caf_input = await parse_caf_input(req.content)
        assessment = await run_assessment(caf_input)
        return JSONResponse(content={"caf_input": caf_input, "assessment": assessment})
    except Exception as exc:
        logger.exception("Assessment failed")
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/plan")
async def plan(req: ReviewRequest):
    """Run Agent 1 + Agent 2: assessment + plan."""
    if len(req.content) > MAX_INPUT_SIZE:
        raise HTTPException(status_code=400, detail=f"Input exceeds {MAX_INPUT_SIZE} characters")
    if not req.content.strip():
        raise HTTPException(status_code=400, detail="Content cannot be empty")

    try:
        caf_input = await parse_caf_input(req.content)
        assessment = await run_assessment(caf_input)
        plan_result = await run_plan(caf_input, assessment)
        return JSONResponse(content={
            "caf_input": caf_input,
            "assessment": assessment,
            "plan": plan_result,
        })
    except Exception as exc:
        logger.exception("Planning failed")
        raise HTTPException(status_code=500, detail=str(exc))


# Map the 3 workflow agents to the 6 step keys the frontend renders.
# Each agent's `running`/`done` event fans out to one or more step events so
# the existing ProgressTracker UI keeps lighting up the same way.
_AGENT_TO_STEPS: dict[str, tuple[str, ...]] = {
    "assessment": ("parsing", "assessment"),
    "plan":       ("planning",),
    "design":     ("design", "diagram", "report"),
}


@app.post("/api/review/stream")
async def review_stream(req: ReviewRequest):
    """Stream the full CAF pipeline step by step as SSE events.

    Drives the 3-agent SequentialBuilder workflow via `stream_pipeline()`
    and maps each agent event to the frontend's 6-step progress contract.
    """
    if len(req.content) > MAX_INPUT_SIZE:
        raise HTTPException(status_code=400, detail=f"Input exceeds {MAX_INPUT_SIZE} characters")
    if not req.content.strip():
        raise HTTPException(status_code=400, detail="Content cannot be empty")

    async def generate():
        def evt(data: dict) -> str:
            return f"data: {json.dumps(data)}\n\n"

        try:
            async for event in stream_pipeline(req.content):
                agent = event["agent"]
                status = event["status"]

                if agent == "complete":
                    if status == "done":
                        yield evt({"step": "complete", "status": "done", "data": event["data"]})
                    else:
                        yield evt({"step": "error", "status": "error",
                                   "message": event.get("error", "Pipeline failed")})
                    continue

                if status == "error":
                    yield evt({"step": "error", "status": "error",
                               "message": event.get("error", f"{agent} agent failed")})
                    continue

                for step in _AGENT_TO_STEPS.get(agent, ()):
                    yield evt({"step": step, "status": status})

        except Exception as exc:
            logger.exception("Streaming pipeline failed")
            yield f"data: {json.dumps({'step': 'error', 'status': 'error', 'message': str(exc)})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/export/markdown")
async def export_markdown(req: dict):
    """Convert a CAF report JSON into a downloadable Markdown document."""
    report = req if "executive_summary" in req else req.get("report", {})
    if not report.get("executive_summary"):
        raise HTTPException(status_code=400, detail="Invalid report data")

    md = _build_markdown_report(report)
    company = report["executive_summary"].get("company_name", "report").replace(" ", "_")
    filename = f"caf_report_{company}.md"

    return Response(
        content=md,
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _build_markdown_report(report: dict) -> str:
    """Format the full CAF report as a Markdown document."""
    s = report.get("executive_summary", {})
    lines = [
        f"# CAF Assessment Report — {s.get('company_name', 'N/A')}",
        "",
        "## Executive Summary",
        "",
        f"| Field | Value |",
        f"|-------|-------|",
        f"| Industry | {s.get('industry', 'N/A')} |",
        f"| Total Workloads | {s.get('total_workloads', 0)} |",
        f"| Timeline | {s.get('timeline_months', 'N/A')} months |",
        f"| Est. Monthly Cost | ${s.get('monthly_cost', 0):,.0f} |",
        f"| Budget Status | {'Within Budget' if s.get('within_budget', True) else 'Over Budget'} |",
        f"| Overall Readiness | {s.get('overall_readiness', 'N/A')} |",
        f"| Risk Level | {s.get('risk_level', 'N/A')} |",
        f"| Total Risks | {s.get('total_risks', 0)} |",
        "",
    ]

    # Classification breakdown
    breakdown = s.get("classification_breakdown", {})
    if breakdown:
        lines += ["### Classification Breakdown", ""]
        for k, v in breakdown.items():
            lines.append(f"- **{k.title()}**: {v}")
        lines.append("")

    # Assessment
    assessment = report.get("assessment", {})
    if assessment:
        lines += ["## Readiness Assessment", ""]
        scores = assessment.get("readiness_scores", {})
        if scores:
            lines += ["| Dimension | Score |", "|-----------|-------|"]
            for dim, score in scores.items():
                label = dim.replace("_", " ").title()
                lines.append(f"| {label} | {score} |")
            lines.append("")
        if assessment.get("readiness_summary"):
            lines += [assessment["readiness_summary"], ""]
        model = assessment.get("operating_model", {})
        if model.get("recommended"):
            lines += [
                "### Operating Model",
                "",
                f"**Recommended:** {model['recommended']}",
                "",
                model.get("rationale", ""),
                "",
            ]
        skills = assessment.get("skills_assessment", [])
        if skills:
            lines += [
                "### Skills Assessment",
                "",
                "| Role | Gap | Training | Priority |",
                "|------|-----|----------|----------|",
            ]
            for sk in skills:
                lines.append(f"| {sk.get('role', '')} | {sk.get('gap', '')} | {sk.get('recommended_training', '')} | {sk.get('priority', '')} |")
            lines.append("")

    # Workload plan
    plan = report.get("plan", {})
    workloads = plan.get("workload_inventory", [])
    if workloads:
        lines += [
            "## Workload Classification (7 R's)",
            "",
            "| Workload | Classification | Effort | Target Services | Rationale |",
            "|----------|---------------|--------|-----------------|-----------|",
        ]
        for w in workloads:
            services = ", ".join((w.get("target_azure_services") or [])[:3])
            lines.append(f"| {w.get('workload_name', '')} | {w.get('classification', '')} | {w.get('estimated_effort', '')} | {services} | {w.get('rationale', '')} |")
        lines.append("")

    waves = plan.get("migration_waves", [])
    if waves:
        lines += [
            "## Migration Wave Plan",
            "",
            "| Wave | Timeline | Workloads | Rationale |",
            "|------|----------|-----------|-----------|",
        ]
        for w in waves:
            wk = ", ".join(w.get("workloads") or [])
            lines.append(f"| Wave {w.get('wave_number', '')} | {w.get('timeline', '')} | {wk} | {w.get('rationale', '')} |")
        lines.append("")

    # Cost estimation
    costs = report.get("cost_estimation", {})
    cost_items = costs.get("line_items", [])
    if cost_items:
        lines += [
            "## Cost Estimation",
            "",
            f"**Total Monthly Cost:** ${costs.get('total_monthly', 0):,.0f}",
            "",
            "| Workload | Azure Service | Monthly Cost | Notes |",
            "|----------|--------------|-------------|-------|",
        ]
        for item in cost_items:
            lines.append(f"| {item.get('category', '')} | {item.get('azure_service', '')} | ${item.get('monthly_cost', 0):,.0f} | {item.get('notes', '')} |")
        lines.append("")

    # Risk register
    risks = report.get("risk_register", [])
    if risks:
        lines += [
            f"## Risk Register ({len(risks)} risks)",
            "",
            "| ID | Risk | Category | Probability | Impact | Priority | Mitigation |",
            "|----|------|----------|-------------|--------|----------|------------|",
        ]
        for r in risks:
            lines.append(f"| {r.get('id', '')} | {r.get('risk', '')} | {r.get('category', '')} | {r.get('probability', '')} | {r.get('impact', '')} | {r.get('priority', '')} | {r.get('mitigation', '')} |")
        lines.append("")

    # Governance
    gov = report.get("governance_recommendations", {})
    if gov:
        lines += ["## Governance Recommendations", ""]
        for section in ["policies", "security", "cost_management"]:
            items = gov.get(section, [])
            if items:
                lines.append(f"### {section.replace('_', ' ').title()}")
                lines.append("")
                for item in items:
                    lines.append(f"- {item}")
                lines.append("")

    lines += [
        "---",
        "",
        "*Generated by Azure CAF Architect Companion*",
    ]

    return "\n".join(lines)


@app.get("/api/download/png/{run_id}")
async def download_png(run_id: str):
    _validate_run_id(run_id)
    filepath = Path(f"./output/architecture_{run_id}.png")
    if not filepath.exists():
        raise HTTPException(status_code=404, detail="PNG not found")
    return FileResponse(str(filepath), media_type="image/png",
                        filename=f"caf_architecture_{run_id}.png")


@app.get("/api/download/excalidraw/{run_id}")
async def download_excalidraw(run_id: str):
    _validate_run_id(run_id)
    filepath = Path(f"./output/architecture_{run_id}.excalidraw")
    if not filepath.exists():
        raise HTTPException(status_code=404, detail="Excalidraw file not found")
    return FileResponse(str(filepath), media_type="application/json",
                        filename=f"caf_architecture_{run_id}.excalidraw")


# ---------------------------------------------------------------------------
# Static frontend (production)
# ---------------------------------------------------------------------------

_frontend_dist = Path(__file__).parent / "frontend" / "dist"
if _frontend_dist.is_dir():
    app.mount("/", StaticFiles(directory=str(_frontend_dist), html=True), name="frontend")


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("api:app", host="0.0.0.0", port=port, reload=True)
