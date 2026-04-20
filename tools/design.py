"""
CAF Companion - Design Tools (Agent 3)
Landing zone design, Excalidraw rendering, MCP integration,
PNG export, file save, diagram QA, report builder, full pipeline.
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import uuid
from typing import Any

from tools.common import _llm_call
from tools.assessment import parse_caf_input, run_assessment
from tools.planning import run_plan

logger = logging.getLogger("caf-companion")


# ═══════════════════════════════════════════════════════════════════════════
#  1.  DESIGN ENGINE (Agent 3)
# ═══════════════════════════════════════════════════════════════════════════

async def design_landing_zone(
    caf_input: dict[str, Any],
    plan: dict[str, Any],
) -> dict[str, Any]:
    """Design Azure landing zone architecture using LLM.

    Generates management group hierarchy, subscription layout,
    hub-spoke network, and identity design based on CAF Ready methodology.
    """
    from knowledge.caf_prompts import DESIGN_PROMPT

    user_content = json.dumps({
        "organization": {
            "company_name": caf_input.get("company_name", ""),
            "industry": caf_input.get("industry", ""),
            "compliance_requirements": caf_input.get("compliance_requirements", []),
        },
        "workload_inventory": plan.get("workload_inventory", []),
        "migration_waves": plan.get("migration_waves", []),
        "infrastructure": caf_input.get("current_infrastructure", []),
    }, indent=2)

    try:
        result = await _llm_call(DESIGN_PROMPT, user_content)
    except Exception as exc:
        logger.debug("[DESIGN] Landing zone design failed: %s", exc)
        return _default_landing_zone(caf_input, plan)

    # Ensure all expected keys exist
    for key in ("management_groups", "subscriptions", "network_design",
                "identity_design", "governance_baseline"):
        if key not in result:
            result[key] = {}

    return result


def _default_landing_zone(
    caf_input: dict[str, Any],
    plan: dict[str, Any],
) -> dict[str, Any]:
    """Generate a sensible default landing zone when LLM is unavailable."""
    company = caf_input.get("company_name", "Organization")
    workloads = plan.get("workload_inventory", [])

    # Build spoke VNets from workloads
    spokes = []
    cidr_counter = 1
    for w in workloads:
        classification = w.get("classification", "")
        if classification in ("retire", "retain", "replace"):
            continue
        spokes.append({
            "name": f"{w.get('workload_name', 'workload').lower().replace(' ', '-')}-spoke",
            "cidr": f"10.{cidr_counter}.0.0/16",
            "workload": w.get("workload_name", ""),
            "peering_to_hub": True,
        })
        cidr_counter += 1

    return {
        "management_groups": {
            "root": {
                "name": f"{company} Root",
                "children": [
                    {"name": "Platform", "purpose": "Shared infrastructure", "children": [
                        {"name": "Connectivity", "purpose": "Hub networking, DNS, ExpressRoute", "children": []},
                        {"name": "Identity", "purpose": "Entra ID Connect, domain controllers", "children": []},
                        {"name": "Management", "purpose": "Log Analytics, monitoring, automation", "children": []},
                    ]},
                    {"name": "Workloads", "purpose": "Application workloads", "children": [
                        {"name": "Production", "purpose": "Production subscriptions", "children": []},
                        {"name": "Non-Production", "purpose": "Dev/test/staging", "children": []},
                    ]},
                    {"name": "Decommissioned", "purpose": "Retired workloads", "children": []},
                ],
            }
        },
        "subscriptions": [
            {"name": "Connectivity", "purpose": "Hub networking", "management_group": "Platform", "workloads": []},
            {"name": "Identity", "purpose": "Identity services", "management_group": "Platform", "workloads": []},
            {"name": "Management", "purpose": "Monitoring and management", "management_group": "Platform", "workloads": []},
        ],
        "network_design": {
            "topology": "hub-spoke",
            "hub_vnet": {
                "name": "hub-vnet",
                "cidr": "10.0.0.0/16",
                "components": ["Azure Firewall", "Azure Bastion", "VPN Gateway"],
            },
            "spoke_vnets": spokes,
            "on_prem_connectivity": "VPN",
        },
        "identity_design": {
            "provider": "Microsoft Entra ID",
            "tier": "P2",
            "features": ["Conditional Access", "MFA", "PIM"],
        },
        "governance_baseline": {
            "policy_assignments": [
                "Require encryption at rest",
                "Deny public IP on VMs",
                "Require resource tagging",
            ],
            "monitoring": ["Azure Monitor", "Log Analytics"],
        },
    }


# ═══════════════════════════════════════════════════════════════════════════
#  2.  EXCALIDRAW LANDING ZONE RENDERER
# ═══════════════════════════════════════════════════════════════════════════

_AZURE_COLORS: dict[str, dict[str, str]] = {
    "management_group": {"bg": "#e3f2fd", "border": "#1565c0"},
    "subscription":     {"bg": "#e8f5e9", "border": "#2e7d32"},
    "vnet_hub":         {"bg": "#f3e5f5", "border": "#7b1fa2"},
    "vnet_spoke":       {"bg": "#ede7f6", "border": "#512da8"},
    "compute":          {"bg": "#fff3e0", "border": "#e65100"},
    "database":         {"bg": "#fffde7", "border": "#f9a825"},
    "storage":          {"bg": "#e0f7fa", "border": "#00838f"},
    "security":         {"bg": "#fce4ec", "border": "#c62828"},
    "networking":       {"bg": "#f3e5f5", "border": "#6a1b9a"},
    "identity":         {"bg": "#e8eaf6", "border": "#283593"},
    "on_premises":      {"bg": "#eceff1", "border": "#455a64"},
    "monitoring":       {"bg": "#f1f8e9", "border": "#558b2f"},
}
_AZ_DEFAULT_COL = {"bg": "#e7f5ff", "border": "#1c7ed6"}
_BOX_W, _BOX_H = 180, 85
_MG_W, _MG_H = 200, 70


from knowledge.azure_icons import CATEGORY_ICONS, SERVICE_ICONS, SERVICE_NAME_TO_ICON

# Azure service icons — real Microsoft Azure architecture icons (SVG)
_AZ_ICON_SVGS: dict[str, str] = {**CATEGORY_ICONS, **SERVICE_ICONS}


def _resolve_icon_key(label: str, color_key: str) -> str | None:
    """Find the best icon key for a given label, falling back to color_key."""
    label_lower = label.lower()
    # Check service name mappings first (most specific)
    for keyword, icon_key in SERVICE_NAME_TO_ICON.items():
        if keyword in label_lower:
            if icon_key in _AZ_ICON_SVGS:
                return icon_key
    # Fall back to color_key (category icon)
    if color_key in _AZ_ICON_SVGS:
        return color_key
    return None


def _az_rect(
    elem_id: str, label: str, color_key: str,
    x: int, y: int, w: int = _BOX_W, h: int = _BOX_H,
    dashed: bool = False, icon_key: str | None = None,
) -> list[dict]:
    """Create an Excalidraw rectangle with an icon and centered label."""
    col = _AZURE_COLORS.get(color_key, _AZ_DEFAULT_COL)
    grp = f"grp_{elem_id}"
    rect: dict = {
        "type": "rectangle", "id": elem_id,
        "x": x, "y": y, "width": w, "height": h,
        "strokeColor": col["border"], "backgroundColor": col["bg"],
        "fillStyle": "solid", "roundness": {"type": 3},
        "groupIds": [grp],
    }
    if dashed:
        rect["strokeStyle"] = "dashed"
    elems: list[dict] = [rect]

    # Resolve which icon to use
    resolved_icon = icon_key or _resolve_icon_key(label, color_key)

    # Show icon on standard boxes and small service boxes (not oversized containers)
    show_icon = resolved_icon and h <= _BOX_H
    if show_icon:
        icon_size = 20 if h <= 40 else 24
        icon_x = x + (w - icon_size) // 2
        icon_y = y + 4 if h <= 40 else y + 6
        elems.append({
            "type": "image", "id": f"{elem_id}_icon",
            "x": icon_x, "y": icon_y, "width": icon_size, "height": icon_size,
            "angle": 0, "strokeColor": "transparent", "backgroundColor": "transparent",
            "fillStyle": "hachure", "strokeWidth": 1, "roughness": 1, "opacity": 100,
            "groupIds": [grp], "fileId": f"az_icon_{resolved_icon}",
            "scale": [1, 1], "status": "saved", "isDeleted": False,
        })
        text_y = icon_y + icon_size + 2
    else:
        text_y = y + (h // 2) - 10
    elems.append({
        "type": "text", "id": f"{elem_id}_lbl",
        "x": x + 8, "y": text_y,
        "width": w - 16, "height": 20,
        "text": label, "fontSize": 13,
        "textAlign": "center", "strokeColor": "#1e1e1e",
        "groupIds": [grp],
    })
    return elems


def _az_arrow(
    elem_id: str,
    x0: int, y0: int, x1: int, y1: int,
    label: str = "", dashed: bool = False,
) -> list[dict]:
    """Create an Excalidraw arrow between two points."""
    dx, dy = x1 - x0, y1 - y0
    arrow = {
        "type": "arrow", "id": elem_id,
        "x": x0, "y": y0,
        "width": abs(dx), "height": abs(dy),
        "strokeColor": "#495057",
        "points": [[0, 0], [dx, dy]],
        "startArrowhead": None, "endArrowhead": "arrow",
    }
    if dashed:
        arrow["strokeStyle"] = "dashed"
    elems = [arrow]
    if label:
        elems.append({
            "type": "text", "id": f"{elem_id}_lbl",
            "x": x0 + dx // 2 - 50, "y": y0 + dy // 2 - 10,
            "width": 100, "height": 16,
            "text": label, "fontSize": 11,
            "textAlign": "center", "strokeColor": "#868e96",
        })
    return elems


def _render_mgmt_group_tree(
    node: dict, x: int, y: int, depth: int = 0,
) -> tuple[list[dict], int]:
    """Recursively render management group hierarchy. Returns (elements, next_x)."""
    elems: list[dict] = []
    name = node.get("name", "Unknown")
    node_id = f"mg_{name.lower().replace(' ', '_')}_{depth}"
    w = max(_MG_W, len(name) * 10 + 20)

    elems.extend(_az_rect(node_id, name, "management_group", x, y, w, _MG_H))

    children = node.get("children", [])
    if not children:
        return elems, x + w + 30

    child_y = y + _MG_H + 60
    child_x = x
    child_centers = []

    for child in children:
        child_elems, next_x = _render_mgmt_group_tree(child, child_x, child_y, depth + 1)
        elems.extend(child_elems)
        child_center_x = (child_x + next_x - 30) // 2
        child_centers.append(child_center_x)
        child_x = next_x

    # Draw lines from parent to children
    parent_cx = x + w // 2
    parent_bottom = y + _MG_H
    for i, ccx in enumerate(child_centers):
        elems.extend(_az_arrow(
            f"{node_id}_to_child_{i}",
            parent_cx, parent_bottom, ccx, child_y,
        ))

    return elems, child_x


def _section_header(elem_id: str, text: str, x: int, y: int, w: int = 600) -> list[dict]:
    """Create a section header label."""
    return [{
        "type": "text", "id": elem_id,
        "x": x, "y": y, "width": w, "height": 28,
        "text": text, "fontSize": 20, "fontFamily": 1,
        "textAlign": "left", "strokeColor": "#1565c0",
    }]


def _service_color_key(service_name: str) -> str:
    """Map an Azure service name to a color key."""
    s = service_name.lower()
    if any(k in s for k in ("sql", "database", "postgres", "mysql", "cosmos", "redis")):
        return "database"
    if any(k in s for k in ("storage", "blob", "data lake", "file")):
        return "storage"
    if any(k in s for k in ("vm", "virtual machine", "container", "app service", "function")):
        return "compute"
    if any(k in s for k in ("monitor", "log analytics", "insight", "sentinel")):
        return "monitoring"
    if any(k in s for k in ("firewall", "defender", "key vault", "waf")):
        return "security"
    if any(k in s for k in ("vnet", "gateway", "dns", "front door", "load balancer")):
        return "networking"
    if any(k in s for k in ("entra", "identity", "ad ")):
        return "identity"
    return "compute"


def _render_hub_spoke(
    network: dict, x: int, y: int,
    workloads: list[dict] | None = None,
) -> tuple[list[dict], int]:
    """Render hub-spoke network topology with workload details.

    Returns (elements, bottom_y) so the caller knows where the zone ends.
    """
    elems: list[dict] = []
    hub = network.get("hub_vnet", {})
    spokes = network.get("spoke_vnets", [])
    on_prem = network.get("on_prem_connectivity", "VPN")

    # Build workload lookup: workload_name -> target_azure_services
    wl_list = workloads or []
    wl_services: dict[str, list[str]] = {}
    for w in wl_list:
        wl_services[w.get("workload_name", "")] = w.get("target_azure_services", [])

    # ── Hub VNet ─────────────────────────────────────────────────────────
    components = hub.get("components", [])
    cols = min(len(components), 2)
    rows = math.ceil(len(components) / max(cols, 1))
    hub_comp_w, hub_comp_h = 140, 40
    hub_pad = 15
    hub_w = max(320, cols * (hub_comp_w + hub_pad) + hub_pad * 2)
    hub_h = 65 + rows * (hub_comp_h + 10) + hub_pad

    hub_name = hub.get("name", "Hub VNet")
    hub_cidr = hub.get("cidr", "10.0.0.0/16")
    elems.extend(_az_rect("hub_vnet", f"{hub_name}\n{hub_cidr}", "vnet_hub",
                          x, y, hub_w, hub_h, dashed=True))

    # Hub components inside — 2-column grid
    for i, comp_name in enumerate(components):
        col_i = i % cols
        row_i = i // cols
        cx = x + hub_pad + col_i * (hub_comp_w + hub_pad)
        cy = y + 60 + row_i * (hub_comp_h + 10)
        ctype = "security" if any(k in comp_name.lower() for k in ("firewall", "waf", "defender")) else "networking"
        elems.extend(_az_rect(f"hub_comp_{i}", comp_name, ctype,
                              cx, cy, hub_comp_w, hub_comp_h))

    hub_cx = x + hub_w // 2
    hub_cy = y + hub_h // 2

    # ── On-premises ──────────────────────────────────────────────────────
    on_prem_x = x - 250
    on_prem_y = y + hub_h // 2 - _BOX_H // 2
    elems.extend(_az_rect("on_prem", f"On-Premises\nData Center", "on_premises",
                          on_prem_x, on_prem_y))
    elems.extend(_az_arrow("on_prem_to_hub",
                           on_prem_x + _BOX_W, on_prem_y + _BOX_H // 2,
                           x, hub_cy,
                           on_prem, dashed=True))

    # ── Spokes — 2-column grid (prod left, non-prod right) ──────────────
    if not spokes:
        return elems, y + hub_h

    spoke_start_y = y + hub_h + 60
    spoke_col_w = 300
    spoke_gap_x = 40
    spoke_gap_y = 20
    svc_box_w, svc_box_h = 130, 50

    # Place spokes in 2-column grid
    cols_count = min(3, max(1, len(spokes)))
    bottom_y = spoke_start_y

    for i, spoke in enumerate(spokes):
        col_i = i % cols_count
        row_i = i // cols_count
        spoke_id = f"spoke_{i}"

        # Figure out services for this spoke (fuzzy match — spoke name may
        # combine multiple workloads like "App / API (Production)")
        wl_name = spoke.get("workload", "")
        services: list[str] = []
        for plan_name, plan_svcs in wl_services.items():
            if plan_name.lower() in wl_name.lower() or wl_name.lower() in plan_name.lower():
                for s in plan_svcs:
                    if s not in services:
                        services.append(s)
        services = services[:4]  # max 4 services shown

        # Spoke box sizing — taller if it has services
        svc_rows = math.ceil(len(services) / 2) if services else 0
        spoke_h = 55 + svc_rows * (svc_box_h + 8) + (15 if services else 0)
        spoke_w = spoke_col_w

        spoke_x = x - (cols_count * (spoke_col_w + spoke_gap_x)) // 2 + hub_w // 2 + col_i * (spoke_col_w + spoke_gap_x)
        spoke_y = spoke_start_y + row_i * (spoke_h + spoke_gap_y + 10)

        spoke_name = spoke.get("name", f"Spoke {i}")
        spoke_cidr = spoke.get("cidr", "")
        spoke_workload = spoke.get("workload", "")
        spoke_title = spoke_workload if spoke_workload else spoke_name
        spoke_subtitle = spoke_cidr
        spoke_label = f"{spoke_title}\n{spoke_subtitle}" if spoke_subtitle else spoke_title

        elems.extend(_az_rect(spoke_id, spoke_label, "vnet_spoke",
                              spoke_x, spoke_y, spoke_w, spoke_h, dashed=True))

        # Peering arrow from hub bottom to spoke top
        elems.extend(_az_arrow(
            f"hub_to_{spoke_id}",
            hub_cx, y + hub_h,
            spoke_x + spoke_w // 2, spoke_y,
            "peering",
        ))

        # Azure services inside spoke — 2-column mini-grid
        if services:
            for j, svc in enumerate(services):
                svc_col = j % 2
                svc_row = j // 2
                svc_x = spoke_x + 10 + svc_col * (svc_box_w + 10)
                svc_y = spoke_y + 50 + svc_row * (svc_box_h + 8)
                svc_color = _service_color_key(svc)
                # Shorten long names
                svc_short = svc.replace("Azure ", "").replace(" - Flexible Server", "")
                elems.extend(_az_rect(
                    f"{spoke_id}_svc_{j}", svc_short, svc_color,
                    svc_x, svc_y, svc_box_w, svc_box_h,
                ))

        bottom_y = max(bottom_y, spoke_y + spoke_h)

    return elems, bottom_y


def generate_landing_zone_elements(
    design: dict[str, Any],
    workloads: list[dict] | None = None,
) -> dict[str, Any]:
    """Build Excalidraw elements for the full landing zone architecture.

    Layout:
      Zone 1: Title
      Zone 2: Management group hierarchy
      Zone 3: Hub-spoke network with workload details
      Zone 4: Identity & Governance info panels

    Returns {"elements_json": str, "element_count": int}.
    """
    elems: list[dict] = []
    cursor_y = 0

    # ── Zone 1: Title ────────────────────────────────────────────────────
    elems.append({
        "type": "text", "id": "title",
        "x": 0, "y": cursor_y, "width": 600, "height": 32,
        "text": "Azure Landing Zone Architecture", "fontSize": 24, "fontFamily": 1,
        "textAlign": "left", "strokeColor": "#1e1e1e",
    })
    cursor_y += 50

    # ── Zone 2: Management group hierarchy ───────────────────────────────
    mg = design.get("management_groups", {})
    root = mg.get("root", mg)
    if root:
        elems.extend(_section_header("hdr_mg", "Management Group Hierarchy", 0, cursor_y))
        cursor_y += 40
        mg_elems, mg_width = _render_mgmt_group_tree(root, 0, cursor_y)
        elems.extend(mg_elems)
        # Calculate MG tree height (deepest leaf)
        mg_ys = [e.get("y", 0) + e.get("height", 0) for e in mg_elems if e.get("type") == "rectangle"]
        mg_bottom = max(mg_ys) if mg_ys else cursor_y + 200
        cursor_y = mg_bottom + 60

    # ── Zone 3: Hub-spoke network ────────────────────────────────────────
    network = design.get("network_design", {})
    if network:
        elems.extend(_section_header("hdr_network", "Network Topology (Hub & Spoke)", 0, cursor_y))
        cursor_y += 40
        hub_spoke_elems, bottom_y = _render_hub_spoke(network, 200, cursor_y, workloads)
        elems.extend(hub_spoke_elems)
        cursor_y = bottom_y + 60

    # ── Zone 4: Identity & Governance panels ─────────────────────────────
    identity = design.get("identity_design", {})
    governance = design.get("governance_baseline", {})

    if identity or governance:
        elems.extend(_section_header("hdr_infra", "Identity & Governance", 0, cursor_y))
        cursor_y += 40
        panel_x = 0

        if identity:
            provider = identity.get("provider", "Microsoft Entra ID")
            tier = identity.get("tier", "")
            features = identity.get("features", [])[:5]
            id_text = f"{provider}" + (f" ({tier})" if tier else "")
            if features:
                id_text += "\n" + "\n".join(f"• {f}" for f in features)
            id_h = 40 + len(features) * 18
            elems.extend(_az_rect("panel_identity", id_text, "identity",
                                  panel_x, cursor_y, 280, max(id_h, 80)))
            panel_x += 310

        if governance:
            policies = governance.get("policy_assignments", [])[:5]
            gov_text = "Azure Policy"
            if policies:
                gov_text += "\n" + "\n".join(f"• {p}" for p in policies)
            gov_h = 40 + len(policies) * 18
            elems.extend(_az_rect("panel_governance", gov_text, "security",
                                  panel_x, cursor_y, 320, max(gov_h, 80)))

    # ── Camera ───────────────────────────────────────────────────────────
    if elems:
        all_x = [e.get("x", 0) for e in elems if "x" in e]
        all_y = [e.get("y", 0) for e in elems if "y" in e]
        all_r = [e.get("x", 0) + e.get("width", 0) for e in elems if "width" in e]
        all_b = [e.get("y", 0) + e.get("height", 0) for e in elems if "height" in e]
        if all_x and all_y:
            cam_x = min(all_x) - 60
            cam_y = min(all_y) - 40
            cam_w = max(all_r) - cam_x + 60
            cam_h = max(all_b) - cam_y + 60
            elems.insert(0, {
                "type": "cameraUpdate",
                "x": cam_x, "y": cam_y,
                "width": cam_w, "height": cam_h,
            })

    return {"elements_json": json.dumps(elems), "element_count": len(elems)}


# ═══════════════════════════════════════════════════════════════════════════
#  3.  MCP DIAGRAM RENDERER (Excalidraw MCP Server Integration)
# ═══════════════════════════════════════════════════════════════════════════

EXCALIDRAW_MCP_URL = os.environ.get(
    "EXCALIDRAW_MCP_URL", "https://excalidraw-mcp-app.vercel.app/mcp"
)


def generate_mcp_landing_zone_elements(design: dict[str, Any]) -> dict[str, Any]:
    """Build Excalidraw elements optimised for MCP ``create_view`` streaming.

    Uses **labeled shapes** (one element per node instead of three) and
    **progressive ordering** (shape → arrows from shape → next shape)
    per the MCP server's ``read_me`` best-practices.

    Adapts the landing zone design (management groups + hub-spoke) for MCP.
    """
    elems: list[dict] = []

    # ── Camera (4:3 ratio required) ──────────────────────────────────────
    # Will be set after all elements are generated

    mg = design.get("management_groups", {})
    root = mg.get("root", mg)
    arrows: list[dict] = []

    # ── Management group hierarchy (flat progressive emit) ───────────────
    def _emit_mg(node: dict, x: int, y: int, depth: int = 0, parent_id: str | None = None) -> int:
        name = node.get("name", "Unknown")
        node_id = f"mg_{name.lower().replace(' ', '_')}_{depth}"
        w = max(_MG_W, len(name) * 10 + 20)

        elems.append({
            "type": "rectangle", "id": node_id,
            "x": x, "y": y, "width": w, "height": _MG_H,
            "strokeColor": _AZURE_COLORS["management_group"]["border"],
            "backgroundColor": _AZURE_COLORS["management_group"]["bg"],
            "fillStyle": "solid", "roundness": {"type": 3},
            "label": {"text": name, "fontSize": 14},
        })

        if parent_id:
            arrows.append({
                "type": "arrow", "id": f"{parent_id}_to_{node_id}",
                "x": 0, "y": 0, "width": 1, "height": 1,
                "strokeColor": "#868e96",
                "points": [[0, 0], [0, 0]],
                "startBinding": {"elementId": parent_id},
                "endBinding": {"elementId": node_id},
                "startArrowhead": None, "endArrowhead": "arrow",
            })

        children = node.get("children", [])
        if not children:
            return x + w + 30

        child_y = y + _MG_H + 60
        child_x = x
        for child in children:
            child_x = _emit_mg(child, child_x, child_y, depth + 1, node_id)
        return child_x

    if root:
        _emit_mg(root, 0, 0)

    # ── Hub-spoke network ────────────────────────────────────────────────
    network = design.get("network_design", {})
    if network:
        net_y = 350
        hub = network.get("hub_vnet", {})
        spokes = network.get("spoke_vnets", [])
        on_prem = network.get("on_prem_connectivity", "VPN")

        hub_name = hub.get("name", "Hub VNet")
        hub_cidr = hub.get("cidr", "10.0.0.0/16")
        hub_w, hub_h = 280, 160

        elems.append({
            "type": "rectangle", "id": "hub_vnet",
            "x": 200, "y": net_y, "width": hub_w, "height": hub_h,
            "strokeColor": _AZURE_COLORS["vnet_hub"]["border"],
            "backgroundColor": _AZURE_COLORS["vnet_hub"]["bg"],
            "fillStyle": "solid", "roundness": {"type": 3},
            "label": {"text": f"{hub_name}\n{hub_cidr}", "fontSize": 14},
        })

        # Hub components
        components = hub.get("components", [])
        comp_x = 215
        for i, comp_name in enumerate(components[:3]):
            elems.append({
                "type": "rectangle", "id": f"hub_comp_{i}",
                "x": comp_x, "y": net_y + 80, "width": 120, "height": 35,
                "strokeColor": _AZURE_COLORS.get("security" if "firewall" in comp_name.lower() else "networking", _AZURE_COLORS["networking"])["border"],
                "backgroundColor": _AZURE_COLORS.get("security" if "firewall" in comp_name.lower() else "networking", _AZURE_COLORS["networking"])["bg"],
                "fillStyle": "solid", "roundness": {"type": 3},
                "label": {"text": comp_name, "fontSize": 11},
            })
            comp_x += 130

        # On-premises
        on_prem_x = 200 - 220
        on_prem_y = net_y + hub_h // 2 - 30
        elems.append({
            "type": "rectangle", "id": "on_prem",
            "x": on_prem_x, "y": on_prem_y, "width": _BOX_W, "height": _BOX_H,
            "strokeColor": _AZURE_COLORS["on_premises"]["border"],
            "backgroundColor": _AZURE_COLORS["on_premises"]["bg"],
            "fillStyle": "solid", "roundness": {"type": 3},
            "label": {"text": f"On-Premises\n{on_prem}", "fontSize": 14},
        })
        arrows.append({
            "type": "arrow", "id": "on_prem_to_hub",
            "x": 0, "y": 0, "width": 1, "height": 1,
            "strokeColor": "#868e96", "strokeStyle": "dashed",
            "points": [[0, 0], [0, 0]],
            "startBinding": {"elementId": "on_prem"},
            "endBinding": {"elementId": "hub_vnet"},
            "startArrowhead": None, "endArrowhead": "arrow",
            "label": {"text": on_prem},
        })

        # Spokes
        spoke_x = 200 + hub_w + 80
        spoke_start_y = net_y - 40
        spoke_gap = max(90, hub_h // max(len(spokes), 1))

        for i, spoke in enumerate(spokes):
            spoke_id = f"spoke_{i}"
            spoke_name = spoke.get("name", f"Spoke {i}")
            spoke_cidr = spoke.get("cidr", "")
            spoke_label = f"{spoke_name}\n{spoke_cidr}" if spoke_cidr else spoke_name
            spoke_y = spoke_start_y + i * spoke_gap

            elems.append({
                "type": "rectangle", "id": spoke_id,
                "x": spoke_x, "y": spoke_y, "width": 200, "height": 55,
                "strokeColor": _AZURE_COLORS["vnet_spoke"]["border"],
                "backgroundColor": _AZURE_COLORS["vnet_spoke"]["bg"],
                "fillStyle": "solid", "roundness": {"type": 3},
                "label": {"text": spoke_label, "fontSize": 12},
            })
            arrows.append({
                "type": "arrow", "id": f"hub_to_{spoke_id}",
                "x": 0, "y": 0, "width": 1, "height": 1,
                "strokeColor": "#495057",
                "points": [[0, 0], [0, 0]],
                "startBinding": {"elementId": "hub_vnet"},
                "endBinding": {"elementId": spoke_id},
                "startArrowhead": None, "endArrowhead": "arrow",
                "label": {"text": "peering"},
            })

    # Add arrows after all shapes (progressive ordering)
    elems.extend(arrows)

    # ── Camera ───────────────────────────────────────────────────────────
    if elems:
        all_x = [e.get("x", 0) for e in elems if "x" in e and e.get("type") != "arrow"]
        all_y = [e.get("y", 0) for e in elems if "y" in e and e.get("type") != "arrow"]
        if all_x and all_y:
            cam_x = min(all_x) - 100
            cam_y = min(all_y) - 80
            cam_w = max(all_x) + 400 - cam_x
            cam_h = max(all_y) + 300 - cam_y
            if cam_w / max(cam_h, 1) > 4 / 3:
                cam_h = int(cam_w * 3 / 4)
            else:
                cam_w = int(cam_h * 4 / 3)
            elems.insert(0, {"type": "cameraUpdate", "x": cam_x, "y": cam_y,
                             "width": cam_w, "height": cam_h})

    return {"elements_json": json.dumps(elems), "element_count": len(elems)}


# ── Async MCP client ────────────────────────────────────────────────────


async def _render_mcp_async(
    elements_json: str, mcp_url: str = EXCALIDRAW_MCP_URL,
) -> dict[str, Any]:
    """Connect to Excalidraw MCP server and invoke ``create_view``."""
    try:
        from mcp import ClientSession  # type: ignore[import-untyped]
    except ImportError:
        return {"success": False, "error": "mcp package not installed - run: pip install mcp"}

    def _extract(result: Any) -> str:
        if hasattr(result, "content"):
            parts = []
            for block in result.content:
                parts.append(getattr(block, "text", str(block)))
            return "\n".join(parts)
        return str(result)

    def _make_httpx_client(**kwargs: Any) -> Any:
        """Custom httpx client factory - disables SSL verification when the
        standard CA bundle fails (common behind corporate proxies)."""
        import httpx  # type: ignore[import-untyped]
        if os.environ.get("CAF_NO_SSL_VERIFY", "").lower() in ("1", "true"):
            kwargs["verify"] = False
            logger.debug("[MCP] SSL verify disabled via CAF_NO_SSL_VERIFY")
        elif kwargs.get("verify", True) is not False:
            try:
                with httpx.Client(verify=True) as probe:
                    probe.head(mcp_url, timeout=5)
                logger.debug("[MCP] SSL probe OK - using default verification")
            except Exception as exc:
                kwargs["verify"] = False
                logger.warning("[MCP] SSL probe failed (%s) - disabling verification. "
                               "Set CAF_NO_SSL_VERIFY=1 to suppress this warning.", exc)
        return httpx.AsyncClient(**kwargs)

    errors: list[str] = []

    # 1. Streamable HTTP (preferred)
    try:
        from mcp.client.streamable_http import streamablehttp_client
        async with streamablehttp_client(
            mcp_url, httpx_client_factory=_make_httpx_client,
        ) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                res = await session.call_tool("create_view", {"elements": elements_json})
                return {"success": True, "transport": "streamable-http",
                        "result": _extract(res)}
    except Exception as exc:
        errors.append(f"streamable-http: {exc}")

    # 2. SSE fallback
    try:
        from mcp.client.sse import sse_client
        async with sse_client(mcp_url, httpx_client_factory=_make_httpx_client) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                res = await session.call_tool("create_view", {"elements": elements_json})
                return {"success": True, "transport": "sse",
                        "result": _extract(res)}
    except Exception as exc:
        errors.append(f"sse: {exc}")

    return {"success": False, "error": " | ".join(errors)}


def render_via_excalidraw_mcp(
    elements_json: str, mcp_url: str = EXCALIDRAW_MCP_URL,
) -> dict[str, Any]:
    """Render landing zone diagram via Excalidraw MCP server (**sync wrapper**).

    Handles both sync and async caller contexts gracefully.
    """
    import concurrent.futures

    coro = _render_mcp_async(elements_json, mcp_url)

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, coro).result(timeout=30)
    return asyncio.run(coro)


# ═══════════════════════════════════════════════════════════════════════════
#  4.  PNG EXPORT
# ═══════════════════════════════════════════════════════════════════════════

def export_landing_zone_png(
    design: dict[str, Any],
    filepath: str = "./output/architecture.png",
    scale: float = 2.0,
    workloads: list[dict] | None = None,
    excalidraw_path: str | None = None,
) -> str:
    """Export the landing zone diagram as a PNG image.

    Uses the Node.js Excalidraw-native renderer (scripts/export-png.mjs)
    which supports icons and full fidelity rendering. Falls back to a
    basic Pillow renderer if Node.js is not available.

    Args:
        design: Landing zone design dict (used only for Pillow fallback).
        filepath: Output PNG path.
        scale: Resolution multiplier.
        workloads: Workload list (used only for Pillow fallback).
        excalidraw_path: Path to the saved .excalidraw file (preferred).

    Returns absolute path to the saved PNG.
    """
    import subprocess

    # ── Primary: Node.js Excalidraw renderer ─────────────────────────────
    if excalidraw_path and os.path.exists(excalidraw_path):
        script = os.path.join(os.path.dirname(os.path.dirname(__file__)), "scripts", "export-png.mjs")
        if os.path.exists(script):
            try:
                result = subprocess.run(
                    ["node", script, excalidraw_path, filepath, "--scale", str(scale)],
                    capture_output=True, text=True, timeout=30,
                    cwd=os.path.dirname(os.path.dirname(__file__)),
                )
                if result.returncode == 0:
                    try:
                        info = json.loads(result.stdout.strip())
                        if info.get("success"):
                            logger.debug("[PNG] Exported via Node.js: %sx%s",
                                         info.get("width"), info.get("height"))
                            return info.get("path", os.path.abspath(filepath))
                    except json.JSONDecodeError:
                        pass
                logger.warning("[PNG] Node.js export failed: %s", result.stderr[:200])
            except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
                logger.warning("[PNG] Node.js not available: %s", exc)

    # ── Fallback: Pillow basic renderer (no icons) ───────────────────────
    logger.debug("[PNG] Using Pillow fallback")
    from PIL import Image, ImageDraw, ImageFont

    elements_result = generate_landing_zone_elements(design, workloads)
    raw_elems = json.loads(elements_result["elements_json"])
    elems = [e for e in raw_elems if e.get("type") not in ("cameraUpdate",)]

    if not elems:
        img = Image.new("RGB", (400, 200), "#ffffff")
        draw = ImageDraw.Draw(img)
        draw.text((20, 80), "No landing zone to render", fill="#1e1e1e")
        os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
        img.save(filepath, "PNG")
        return os.path.abspath(filepath)

    all_x = [e.get("x", 0) for e in elems if "x" in e]
    all_y = [e.get("y", 0) for e in elems if "y" in e]
    all_w = [e.get("x", 0) + e.get("width", 0) for e in elems if "width" in e]
    all_h = [e.get("y", 0) + e.get("height", 0) for e in elems if "height" in e]
    pad = 80
    min_x, min_y = min(all_x) - pad, min(all_y) - pad
    max_x, max_y = max(all_w + all_x) + pad, max(all_h + all_y) + pad
    cw, ch = int((max_x - min_x) * scale), int((max_y - min_y) * scale)
    img = Image.new("RGB", (max(cw, 100), max(ch, 100)), "#ffffff")
    draw = ImageDraw.Draw(img)

    def sx(v: float) -> float: return (v - min_x) * scale
    def sy(v: float) -> float: return (v - min_y) * scale

    try:
        font = ImageFont.truetype("arial.ttf", int(14 * scale))
        font_sm = ImageFont.truetype("arial.ttf", int(11 * scale))
    except (IOError, OSError):
        try:
            font = ImageFont.truetype("DejaVuSans.ttf", int(14 * scale))
            font_sm = ImageFont.truetype("DejaVuSans.ttf", int(11 * scale))
        except (IOError, OSError):
            font = ImageFont.load_default()
            font_sm = font

    for elem in elems:
        etype = elem.get("type", "")
        if etype == "rectangle":
            x0, y0 = sx(elem["x"]), sy(elem["y"])
            x1 = sx(elem["x"] + elem.get("width", _BOX_W))
            y1 = sy(elem["y"] + elem.get("height", _BOX_H))
            draw.rounded_rectangle([x0, y0, x1, y1], radius=8 * scale,
                                   fill=elem.get("backgroundColor", "#e7f5ff"),
                                   outline=elem.get("strokeColor", "#1c7ed6"),
                                   width=int(2 * scale))
        elif etype == "text":
            f = font_sm if elem.get("fontSize", 14) < 13 else font
            draw.text((sx(elem["x"]), sy(elem["y"])),
                      elem.get("text", ""),
                      fill=elem.get("strokeColor", "#1e1e1e"), font=f)
        elif etype == "arrow":
            points = elem.get("points", [[0, 0], [0, 0]])
            ax, ay = sx(elem["x"]), sy(elem["y"])
            for j in range(len(points) - 1):
                px0 = ax + points[j][0] * scale
                py0 = ay + points[j][1] * scale
                px1 = ax + points[j + 1][0] * scale
                py1 = ay + points[j + 1][1] * scale
                draw.line([(px0, py0), (px1, py1)],
                          fill=elem.get("strokeColor", "#495057"),
                          width=int(2 * scale))
                angle = math.atan2(py1 - py0, px1 - px0)
                al = 10 * scale
                draw.polygon([(px1, py1),
                              (px1 - al * math.cos(angle - 0.4), py1 - al * math.sin(angle - 0.4)),
                              (px1 - al * math.cos(angle + 0.4), py1 - al * math.sin(angle + 0.4))],
                             fill=elem.get("strokeColor", "#495057"))

    os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
    img.save(filepath, "PNG")
    return os.path.abspath(filepath)


# ═══════════════════════════════════════════════════════════════════════════
#  5.  FILE SAVE HELPERS
# ═══════════════════════════════════════════════════════════════════════════

def save_excalidraw_file(
    elements_json: str,
    filepath: str = "./output/architecture.excalidraw",
) -> str:
    """Save Excalidraw elements as a .excalidraw file."""
    pseudo = {"cameraUpdate", "delete", "restoreCheckpoint"}
    elements = json.loads(elements_json)
    real = [e for e in elements if e.get("type") not in pseudo]
    # Collect icon files referenced by image elements
    used_file_ids = {e["fileId"] for e in real if e.get("type") == "image" and "fileId" in e}
    files: dict[str, dict] = {}
    for file_id in used_file_ids:
        icon_key = file_id[len("az_icon_"):] if file_id.startswith("az_icon_") else file_id
        if icon_key in _AZ_ICON_SVGS:
            files[file_id] = {
                "mimeType": "image/svg+xml",
                "dataURL": _AZ_ICON_SVGS[icon_key],
                "id": file_id,
                "created": 1700000000000,
            }
    data = {
        "type": "excalidraw",
        "version": 2,
        "source": "caf-companion",
        "elements": real,
        "appState": {"viewBackgroundColor": "#ffffff"},
        "files": files,
    }
    os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    return os.path.abspath(filepath)


# ═══════════════════════════════════════════════════════════════════════════
#  6.  DIAGRAM QA AGENT (LLM-powered layout review & fix)
# ═══════════════════════════════════════════════════════════════════════════

_DIAGRAM_QA_PROMPT = """You are a diagram layout QA agent. You receive Excalidraw JSON elements
representing an Azure landing zone architecture diagram.

Your job is to review the layout and fix any issues:

1. **Overlapping text** — If a text element overflows its parent rectangle, either:
   - Shorten the text (abbreviate Azure service names, use line breaks)
   - Increase the parent rectangle's width or height
   - Adjust the text's x/y position to center it properly

2. **Overlapping elements** — If two rectangles or groups overlap, adjust positions
   to add proper spacing (minimum 20px gap between elements).

3. **Text sizing** — If text is too long for its container, abbreviate it:
   - "Azure Database for PostgreSQL - Flexible Server" → "PostgreSQL"
   - "Azure App Service" → "App Service"
   - "Azure Cache for Redis" → "Redis Cache"
   - "Azure Data Lake Storage Gen2" → "Data Lake"

4. **Container sizing** — Ensure parent rectangles (spokes, hub) are large enough
   to contain all their child elements with padding.

5. **Arrow clarity** — Ensure arrows don't cross through unrelated elements.
   Adjust start/end points if needed.

6. **Readable spacing** — Ensure at least 30px between section zones (management
   groups, network topology, identity/governance).

RULES:
- Return ONLY the corrected elements array as valid JSON (no markdown fences, no explanation)
- Keep ALL element IDs the same — only modify positions, sizes, and text content
- Do NOT add or remove elements — only fix existing ones
- Do NOT change colors, types, or structural relationships
- Preserve the cameraUpdate element (adjust if the diagram bounds changed)
- Keep the diagram compact but readable
"""


async def refine_diagram_layout(elements_json: str) -> str:
    """Send Excalidraw elements to the LLM for layout QA and fixes.

    Returns corrected elements_json string. Falls back to the original
    if the LLM call fails or returns invalid JSON.
    """
    # Strip pseudo-elements and icon metadata to reduce token count
    elements = json.loads(elements_json)
    camera = None
    compact_elems = []
    for e in elements:
        if e.get("type") == "cameraUpdate":
            camera = e
            continue
        # Strip fields the LLM doesn't need for layout analysis
        slim = {}
        for k in ("type", "id", "x", "y", "width", "height", "text",
                   "fontSize", "textAlign", "strokeColor", "backgroundColor",
                   "points", "strokeStyle", "label", "groupIds"):
            if k in e:
                slim[k] = e[k]
        compact_elems.append(slim)

    compact_json = json.dumps(compact_elems, separators=(",", ":"))
    logger.debug("[DiagramQA] Sending %d elements (%d chars) to LLM",
                 len(compact_elems), len(compact_json))

    try:
        result = await _llm_call(_DIAGRAM_QA_PROMPT, compact_json)
    except Exception as exc:
        logger.warning("[DiagramQA] LLM call failed: %s — using original", exc)
        return elements_json

    # Result should be a list of elements
    if isinstance(result, dict) and "error" in result:
        logger.warning("[DiagramQA] LLM returned error: %s", result["error"])
        return elements_json

    fixed_elems = result if isinstance(result, list) else []
    if not fixed_elems:
        logger.warning("[DiagramQA] LLM returned empty or invalid result")
        return elements_json

    # Merge LLM fixes back into original elements (preserve fields LLM didn't see)
    fixed_by_id = {e.get("id"): e for e in fixed_elems if "id" in e}
    merged = []
    if camera:
        # Check if LLM returned an updated camera
        cam_fix = fixed_by_id.pop("camera", None)
        if cam_fix and cam_fix.get("type") == "cameraUpdate":
            camera.update(cam_fix)
        merged.append(camera)

    for orig in elements:
        if orig.get("type") == "cameraUpdate":
            continue
        eid = orig.get("id")
        fix = fixed_by_id.get(eid)
        if fix:
            # Apply position/size/text fixes while keeping everything else
            for k in ("x", "y", "width", "height", "text", "fontSize",
                       "points", "label"):
                if k in fix:
                    orig[k] = fix[k]
        merged.append(orig)

    logger.debug("[DiagramQA] Merged %d fixed elements", len(merged))
    return json.dumps(merged)


# ═══════════════════════════════════════════════════════════════════════════
#  7.  REPORT BUILDER
# ═══════════════════════════════════════════════════════════════════════════

def build_caf_report(
    caf_input: dict[str, Any],
    assessment: dict[str, Any],
    plan: dict[str, Any],
    design: dict[str, Any],
    diagram_info: dict[str, Any],
) -> dict[str, Any]:
    """Compose the final CAF report from all agent outputs."""
    workloads = plan.get("workload_inventory", [])
    costs = plan.get("cost_estimation", {})
    risks = plan.get("risk_register", [])

    # Classification breakdown
    breakdown: dict[str, int] = {}
    for w in workloads:
        c = w.get("classification", "unknown")
        breakdown[c] = breakdown.get(c, 0) + 1

    # Risk level
    risk_priorities = [r.get("priority", "low") for r in risks]
    if "critical" in risk_priorities:
        risk_level = "critical"
    elif "high" in risk_priorities:
        risk_level = "high"
    elif "medium" in risk_priorities:
        risk_level = "moderate"
    else:
        risk_level = "low"

    return {
        "executive_summary": {
            "company_name": caf_input.get("company_name", ""),
            "industry": caf_input.get("industry", ""),
            "total_workloads": len(workloads),
            "classification_breakdown": breakdown,
            "timeline_months": caf_input.get("timeline_months", 12),
            "monthly_cost": costs.get("total_monthly", 0),
            "migration_budget_estimate": costs.get("migration_budget_estimate", 0),
            "within_budget": costs.get("within_budget", True),
            "overall_readiness": assessment.get("overall_readiness", ""),
            "risk_level": risk_level,
            "total_risks": len(risks),
        },
        "assessment": assessment,
        "plan": {
            "workload_inventory": workloads,
            "migration_waves": plan.get("migration_waves", []),
        },
        "cost_estimation": costs,
        "risk_register": risks,
        "governance_recommendations": plan.get("governance_recommendations", {}),
        "landing_zone": design,
        "diagram": diagram_info,
    }


# ═══════════════════════════════════════════════════════════════════════════
#  8.  PIPELINE ORCHESTRATOR
# ═══════════════════════════════════════════════════════════════════════════

async def run_full_pipeline(content: str) -> dict[str, Any]:
    """Chain Agent 1 → Agent 2 → Agent 3, returning the complete CAF report.

    This is the top-level function called by api.py, main.py, and run_local.py.
    """
    # Step 0: Parse input
    caf_input = await parse_caf_input(content)

    # Step 1: Assessment (Agent 1)
    assessment = await run_assessment(caf_input)

    # Step 2: Plan & Analyze (Agent 2)
    plan = await run_plan(caf_input, assessment)

    # Step 3: Design (Agent 3)
    design = await design_landing_zone(caf_input, plan)

    # Step 4: Generate diagram
    run_id = uuid.uuid4().hex[:8]
    workloads = plan.get("workload_inventory", [])
    lz_elements = generate_landing_zone_elements(design, workloads)

    # Step 4a: Diagram QA — LLM reviews and fixes layout issues
    lz_elements["elements_json"] = await refine_diagram_layout(
        lz_elements["elements_json"]
    )

    excalidraw_path = save_excalidraw_file(
        lz_elements["elements_json"],
        f"./output/architecture_{run_id}.excalidraw",
    )
    png_path = export_landing_zone_png(
        design,
        f"./output/architecture_{run_id}.png",
        workloads=workloads,
        excalidraw_path=excalidraw_path,
    )

    excalidraw_file = None
    try:
        with open(excalidraw_path, "r", encoding="utf-8") as f:
            excalidraw_file = json.load(f)
    except Exception:
        pass

    diagram_info = {
        "element_count": lz_elements["element_count"],
        "local_file": excalidraw_path,
        "png_file": png_path,
        "excalidraw_file": excalidraw_file,
        "run_id": run_id,
    }

    # Step 5: Build report
    return build_caf_report(caf_input, assessment, plan, design, diagram_info)
