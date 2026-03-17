"""
Azure CAF Architect Companion - Local CLI Runner
==================================================
Usage:
    python run_local.py scenarios/meditrack_healthcare.txt
    python run_local.py --text "Company: Acme Corp, 50 employees..."
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

from tools import (
    parse_caf_input,
    run_assessment,
    run_plan,
    design_landing_zone,
    generate_landing_zone_elements,
    save_excalidraw_file,
    export_landing_zone_png,
    build_caf_report,
)

console = Console()


async def run_review(content: str) -> None:
    console.rule("[bold blue]Azure CAF Architect Companion[/bold blue]")

    # Step 1: Parse Input
    console.print()
    console.print("[dim]Step 1:[/dim] Parsing infrastructure description...")
    caf_input = await parse_caf_input(content)
    console.print(f"  Company: [bold]{caf_input.get('company_name', 'Unknown')}[/bold]")
    console.print(f"  Industry: {caf_input.get('industry', 'Unknown')}")
    console.print(f"  Applications: {len(caf_input.get('applications', []))}")
    console.print(f"  Team members: {sum(m.get('count', 0) for m in caf_input.get('team', []))}")
    console.print(f"  Compliance: {', '.join(caf_input.get('compliance_requirements', [])) or 'None'}")

    # Step 2: Assessment
    console.print()
    console.print("[dim]Step 2:[/dim] Running readiness assessment...")
    assessment = await run_assessment(caf_input)
    console.print(f"  Overall readiness: [bold]{assessment.get('overall_readiness', '')}[/bold]")
    console.print(f"  Operating model: [bold]{assessment.get('operating_model', {}).get('recommended', '')}[/bold]")

    # Skills table
    skills = assessment.get("skills_assessment", [])
    if skills:
        t = Table(title="Skills Assessment")
        t.add_column("Role")
        t.add_column("Gap")
        t.add_column("Training")
        t.add_column("Priority")
        for s in skills:
            t.add_row(s.get("role", ""), s.get("gap", "")[:50], s.get("recommended_training", ""), s.get("priority", ""))
        console.print(t)

    # Step 3: Plan & Analyze
    console.print()
    console.print("[dim]Step 3:[/dim] Classifying workloads and planning migration...")
    plan = await run_plan(caf_input, assessment)

    # Workload classification table
    workloads = plan.get("workload_inventory", [])
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

    # Wave plan
    waves = plan.get("migration_waves", [])
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

    # Cost estimation
    costs = plan.get("cost_estimation", {})
    if costs:
        console.print(Panel(
            f"Monthly cost: [bold]${costs.get('total_monthly', 0):,.2f}[/bold]\n"
            f"Within budget: {'Yes' if costs.get('within_budget', True) else '[red]No[/red]'}",
            title="Cost Estimation",
        ))

    # Risk register
    risks = plan.get("risk_register", [])
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

    # Step 4: Design Landing Zone
    console.print()
    console.print("[dim]Step 4:[/dim] Designing Azure landing zone...")
    design = await design_landing_zone(caf_input, plan)

    network = design.get("network_design", {})
    if network:
        console.print(f"  Topology: {network.get('topology', '')}")
        console.print(f"  Hub: {network.get('hub_vnet', {}).get('name', '')}")
        console.print(f"  Spokes: {len(network.get('spoke_vnets', []))}")
        console.print(f"  On-prem: {network.get('on_prem_connectivity', '')}")

    # Step 5: Generate Diagram
    console.print()
    console.print("[dim]Step 5:[/dim] Generating architecture diagram...")
    lz_elements = generate_landing_zone_elements(design)

    import uuid
    run_id = uuid.uuid4().hex[:8]

    excalidraw_path = save_excalidraw_file(
        lz_elements["elements_json"],
        f"./output/architecture_{run_id}.excalidraw",
    )
    png_path = export_landing_zone_png(
        design,
        f"./output/architecture_{run_id}.png",
    )
    console.print(f"  Excalidraw: {excalidraw_path}")
    console.print(f"  PNG: {png_path}")
    console.print(f"  Elements: {lz_elements['element_count']}")

    # Step 6: Build Report
    console.print()
    console.print("[dim]Step 6:[/dim] Building final report...")
    diagram_info = {
        "element_count": lz_elements["element_count"],
        "local_file": excalidraw_path,
        "png_file": png_path,
        "run_id": run_id,
    }
    report = build_caf_report(caf_input, assessment, plan, design, diagram_info)

    # Save report bundle
    bundle_path = "./output/caf_report_bundle.json"
    os.makedirs("./output", exist_ok=True)
    with open(bundle_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)

    # Executive summary
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

    console.print()
    console.print(f"[green]Report saved to {bundle_path}[/green]")
    console.rule("[bold blue]Done[/bold blue]")


def main():
    parser = argparse.ArgumentParser(description="Azure CAF Architect Companion - CLI")
    parser.add_argument("file", nargs="?", help="Path to infrastructure description file")
    parser.add_argument("--text", "-t", help="Inline infrastructure description")
    args = parser.parse_args()

    if args.text:
        content = args.text
    elif args.file:
        with open(args.file, "r", encoding="utf-8") as f:
            content = f.read()
    else:
        parser.print_help()
        sys.exit(1)

    asyncio.run(run_review(content))


if __name__ == "__main__":
    main()
