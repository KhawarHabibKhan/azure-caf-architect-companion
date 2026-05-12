"""
Azure CAF Architect Companion - Local CLI Runner
==================================================
Drives the full 3-agent SequentialBuilder workflow via `stream_pipeline()`
from `agents`. Prints per-agent progress as each agent finishes, then
renders the familiar rich tables (readiness, workloads, waves, costs,
risks, executive summary) from the streamed event data.

Usage:
    python run_local.py scenarios/meditrack_healthcare.txt
    python run_local.py --text "Company: Acme Corp, 50 employees..."
    python run_local.py scenarios/meditrack_healthcare.txt --render
"""

import argparse
import asyncio
import io
import json
import logging
import os
import sys

# Ensure UTF-8 output on Windows
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from dotenv import load_dotenv
load_dotenv(override=True)

from rich.console import Console
from rich.table import Table
from rich.panel import Panel

logging.getLogger("caf-companion").setLevel(logging.CRITICAL)

from agents import stream_pipeline
from tools.design import (
    generate_mcp_landing_zone_elements,
    render_via_excalidraw_mcp,
)

console = Console()


AGENT_LABELS = {
    "assessment": ("1/3", "Assessment Agent"),
    "plan":       ("2/3", "Plan Agent"),
    "design":     ("3/3", "Design Agent"),
}


def _render_assessment(data: dict) -> None:
    caf_input = data.get("caf_input", {})
    console.print(f"  Company: [bold]{caf_input.get('company_name', 'Unknown')}[/bold]")
    console.print(f"  Industry: {caf_input.get('industry', 'Unknown')}")
    console.print(f"  Applications: {len(caf_input.get('applications', []))}")
    console.print(f"  Team members: {sum(m.get('count', 0) for m in caf_input.get('team', []))}")
    console.print(f"  Compliance: {', '.join(caf_input.get('compliance_requirements', [])) or 'None'}")
    console.print(f"  Overall readiness: [bold]{data.get('overall_readiness', '')}[/bold]")
    console.print(f"  Operating model: [bold]{data.get('operating_model', {}).get('recommended', '')}[/bold]")

    skills = data.get("skills_assessment", [])
    if skills:
        t = Table(title="Skills Assessment")
        t.add_column("Role")
        t.add_column("Gap")
        t.add_column("Training")
        t.add_column("Priority")
        for s in skills:
            t.add_row(
                s.get("role", ""),
                s.get("gap", "")[:50],
                s.get("recommended_training", ""),
                s.get("priority", ""),
            )
        console.print(t)


def _render_plan(data: dict) -> None:
    workloads = data.get("workload_inventory", [])
    if workloads:
        t = Table(title="Workload Classification (7 R's)")
        t.add_column("Workload")
        t.add_column("Classification")
        t.add_column("Effort")
        t.add_column("Target Services")
        for w in workloads:
            services = ", ".join(w.get("target_azure_services", [])[:3])
            t.add_row(
                w.get("workload_name", ""),
                w.get("classification", ""),
                w.get("estimated_effort", ""),
                services,
            )
        console.print(t)

    waves = data.get("migration_waves", [])
    if waves:
        t = Table(title="Migration Wave Plan")
        t.add_column("Wave")
        t.add_column("Timeline")
        t.add_column("Workloads")
        for w in waves:
            t.add_row(
                str(w.get("wave_number", "")),
                w.get("timeline", ""),
                ", ".join(w.get("workloads", [])),
            )
        console.print(t)

    costs = data.get("cost_estimation", {})
    if costs:
        console.print(Panel(
            f"Monthly cost: [bold]${costs.get('total_monthly', 0):,.2f}[/bold]\n"
            f"Within budget: {'Yes' if costs.get('within_budget', True) else '[red]No[/red]'}",
            title="Cost Estimation",
        ))

    risks = data.get("risk_register", [])
    if risks:
        t = Table(title="Risk Register")
        t.add_column("ID")
        t.add_column("Risk")
        t.add_column("Category")
        t.add_column("Priority")
        t.add_column("Mitigation")
        for r in risks[:10]:
            t.add_row(
                r.get("id", ""),
                r.get("risk", "")[:60],
                r.get("category", ""),
                r.get("priority", ""),
                r.get("mitigation", "")[:60],
            )
        console.print(t)


def _render_design(data: dict) -> None:
    landing_zone = data.get("landing_zone", {})
    network = landing_zone.get("network_design", {})
    if network:
        console.print(f"  Topology: {network.get('topology', '')}")
        console.print(f"  Hub: {network.get('hub_vnet', {}).get('name', '')}")
        console.print(f"  Spokes: {len(network.get('spoke_vnets', []))}")
        console.print(f"  On-prem: {network.get('on_prem_connectivity', '')}")

    diagram = data.get("diagram", {})
    if diagram:
        console.print(f"  Excalidraw: {diagram.get('local_file', '')}")
        console.print(f"  PNG: {diagram.get('png_file', '')}")
        console.print(f"  Elements: {diagram.get('element_count', 0)}")


def _render_executive_summary(report: dict) -> None:
    es = report.get("executive_summary", {})
    console.print()
    console.print(Panel(
        f"Company: [bold]{es.get('company_name', '')}[/bold]\n"
        f"Workloads: {es.get('total_workloads', 0)}\n"
        f"Readiness: {es.get('overall_readiness', '')}\n"
        f"Risk level: {es.get('risk_level', '')}\n"
        f"Monthly cost: ${es.get('monthly_cost', 0):,.2f}\n"
        f"Timeline: {es.get('timeline_months', 0)} months",
        title="Executive Summary",
    ))


async def run_review(content: str, render_mcp: bool = False) -> None:
    console.rule("[bold blue]Azure CAF Architect Companion[/bold blue]")
    console.print()

    final_report: dict | None = None

    async for event in stream_pipeline(content):
        agent_key = event["agent"]
        status = event["status"]

        if agent_key == "complete":
            if status == "error":
                console.print(f"[red]Pipeline error:[/red] {event.get('error', 'unknown')}")
                return
            final_report = event["data"]
            continue

        label = AGENT_LABELS.get(agent_key, ("?/3", agent_key.title()))
        step, name = label

        if status == "running":
            console.print(f"[dim]Step {step}:[/dim] {name} running...")
        elif status == "done":
            console.print(f"  [green]\u2713 {name} done[/green]")
            data = event.get("data") or {}
            if agent_key == "assessment":
                _render_assessment(data)
            elif agent_key == "plan":
                _render_plan(data)
            elif agent_key == "design":
                _render_design(data)
            console.print()
        elif status == "error":
            console.print(f"[red]\u2717 {name} failed:[/red] {event.get('error', 'unknown')}")
            return

    if final_report is None:
        console.print("[red]Pipeline finished without a final report[/red]")
        return

    # Optional MCP rendering pass over the landing-zone design
    if render_mcp and final_report.get("landing_zone"):
        console.print("[dim]\u21b3 Rendering via Excalidraw MCP server...[/dim]")
        mcp_elems = generate_mcp_landing_zone_elements(final_report["landing_zone"])
        mcp_result = render_via_excalidraw_mcp(mcp_elems["elements_json"])
        diagram = final_report.setdefault("diagram", {})
        diagram["mcp_render"] = mcp_result
        if mcp_result.get("success"):
            console.print(
                f"  [green]\u2713 MCP:[/green]       Success via {mcp_result.get('transport', 'unknown')}"
            )
        else:
            console.print(f"  [red]\u2717 MCP:[/red]       {mcp_result.get('error', 'unknown')}")

    # Save report bundle
    bundle_path = "./output/caf_report_bundle.json"
    os.makedirs("./output", exist_ok=True)
    with open(bundle_path, "w", encoding="utf-8") as f:
        json.dump(final_report, f, indent=2, default=str)

    _render_executive_summary(final_report)
    console.print()
    console.print(f"[green]Report saved to {bundle_path}[/green]")
    console.rule("[bold blue]Done[/bold blue]")


def main():
    parser = argparse.ArgumentParser(description="Azure CAF Architect Companion - CLI")
    parser.add_argument("file", nargs="?", help="Path to infrastructure description file")
    parser.add_argument("--text", "-t", help="Inline infrastructure description")
    parser.add_argument("--render", "-r", action="store_true",
                        help="Render diagram via Excalidraw MCP server")
    args = parser.parse_args()

    if args.text:
        content = args.text
    elif args.file:
        with open(args.file, "r", encoding="utf-8") as f:
            content = f.read()
    else:
        parser.print_help()
        sys.exit(1)

    asyncio.run(run_review(content, render_mcp=args.render))


if __name__ == "__main__":
    main()
