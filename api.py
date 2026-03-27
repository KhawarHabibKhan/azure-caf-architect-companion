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
import uuid
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(override=True)

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from tools import (
    parse_caf_input,
    run_assessment,
    run_plan,
    design_landing_zone,
    generate_landing_zone_elements,
    save_excalidraw_file,
    export_landing_zone_png,
    build_caf_report,
    run_full_pipeline,
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
    """Run the full 3-agent CAF pipeline."""
    if len(req.content) > MAX_INPUT_SIZE:
        raise HTTPException(status_code=400, detail=f"Input exceeds {MAX_INPUT_SIZE} characters")
    if not req.content.strip():
        raise HTTPException(status_code=400, detail="Content cannot be empty")

    try:
        report = await run_full_pipeline(req.content)
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


@app.post("/api/review/stream")
async def review_stream(req: ReviewRequest):
    """Stream the full CAF pipeline step by step as SSE events."""
    if len(req.content) > MAX_INPUT_SIZE:
        raise HTTPException(status_code=400, detail=f"Input exceeds {MAX_INPUT_SIZE} characters")
    if not req.content.strip():
        raise HTTPException(status_code=400, detail="Content cannot be empty")

    async def generate():
        def evt(data: dict) -> str:
            return f"data: {json.dumps(data)}\n\n"

        try:
            yield evt({"step": "parsing", "status": "running"})
            caf_input = await parse_caf_input(req.content)
            yield evt({"step": "parsing", "status": "done"})

            yield evt({"step": "assessment", "status": "running"})
            assessment = await run_assessment(caf_input)
            yield evt({"step": "assessment", "status": "done"})

            yield evt({"step": "planning", "status": "running"})
            plan_result = await run_plan(caf_input, assessment)
            yield evt({"step": "planning", "status": "done"})

            yield evt({"step": "design", "status": "running"})
            design = await design_landing_zone(caf_input, plan_result)
            yield evt({"step": "design", "status": "done"})

            yield evt({"step": "diagram", "status": "running"})
            run_id = uuid.uuid4().hex[:8]
            lz_elements = generate_landing_zone_elements(design)
            excalidraw_path = save_excalidraw_file(lz_elements["elements_json"], f"./output/architecture_{run_id}.excalidraw")
            png_path = export_landing_zone_png(design, f"./output/architecture_{run_id}.png")
            excalidraw_file = None
            try:
                with open(excalidraw_path, "r", encoding="utf-8") as ef:
                    excalidraw_file = json.load(ef)
            except Exception:
                pass
            diagram_info = {"run_id": run_id, "excalidraw_file": excalidraw_file, "png_file": png_path, "element_count": lz_elements["element_count"]}
            yield evt({"step": "diagram", "status": "done"})

            yield evt({"step": "report", "status": "running"})
            report = build_caf_report(caf_input, assessment, plan_result, design, diagram_info)
            yield evt({"step": "complete", "status": "done", "data": report})

        except Exception as exc:
            logger.exception("Streaming pipeline failed")
            yield f"data: {json.dumps({'step': 'error', 'status': 'error', 'message': str(exc)})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


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
