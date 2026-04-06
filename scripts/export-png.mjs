#!/usr/bin/env node
/**
 * Export an .excalidraw file to PNG using Excalidraw's native renderer.
 *
 * Usage:
 *   node scripts/export-png.mjs input.excalidraw output.png [--scale 2]
 *
 * Requires: @excalidraw/utils, @resvg/resvg-js (installed in frontend/)
 */

import { readFileSync, writeFileSync, mkdirSync } from "fs";
import { dirname, resolve, join } from "path";
import { createRequire } from "module";

// Resolve modules from frontend/node_modules
const scriptDir = dirname(new URL(import.meta.url).pathname.replace(/^\/([A-Z]:)/, "$1"));
const frontendDir = resolve(scriptDir, "../frontend");
const require = createRequire(join(frontendDir, "node_modules", "_virtual.js"));

async function main() {
  const args = process.argv.slice(2);
  if (args.length < 2) {
    console.error("Usage: node export-png.mjs <input.excalidraw> <output.png> [--scale N]");
    process.exit(1);
  }

  const inputPath = args[0];
  const outputPath = args[1];
  const scaleIdx = args.indexOf("--scale");
  const scale = scaleIdx !== -1 ? parseFloat(args[scaleIdx + 1]) || 2 : 2;

  // Read the .excalidraw file
  const raw = JSON.parse(readFileSync(inputPath, "utf-8"));
  const elements = raw.elements || [];
  const files = raw.files || {};
  const appState = raw.appState || {};

  // Try @excalidraw/utils exportToSvg
  let svgString;
  try {
    const { exportToSvg } = require("@excalidraw/utils");
    const svg = await exportToSvg({
      elements,
      appState: {
        exportBackground: true,
        viewBackgroundColor: appState.viewBackgroundColor || "#ffffff",
        exportWithDarkMode: false,
        ...appState,
      },
      files,
      exportPadding: 20,
    });
    // svg might be a string or an SVGElement
    svgString = typeof svg === "string" ? svg : svg.outerHTML || svg.toString();
  } catch (err) {
    // Fallback: build a basic SVG manually from elements
    console.error(`exportToSvg failed (${err.message}), using fallback SVG builder`);
    svgString = buildFallbackSvg(elements, files, appState);
  }

  // Convert SVG → PNG using resvg
  const { Resvg } = require("@resvg/resvg-js");
  const resvg = new Resvg(svgString, {
    fitTo: { mode: "zoom", value: scale },
    font: { loadSystemFonts: true },
  });
  const pngData = resvg.render();
  const pngBuffer = pngData.asPng();

  // Write PNG
  mkdirSync(dirname(outputPath), { recursive: true });
  writeFileSync(outputPath, pngBuffer);
  console.log(JSON.stringify({
    success: true,
    path: resolve(outputPath),
    width: pngData.width,
    height: pngData.height,
  }));
}

/**
 * Fallback: Build a basic SVG from Excalidraw elements when exportToSvg
 * is unavailable (e.g., no DOM in Node.js).
 */
function buildFallbackSvg(elements, files, appState) {
  const real = elements.filter((e) => e.type !== "cameraUpdate");
  if (real.length === 0) {
    return '<svg xmlns="http://www.w3.org/2000/svg" width="400" height="200"><text x="20" y="80">No elements</text></svg>';
  }

  // Calculate bounds
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  for (const el of real) {
    const x = el.x ?? 0;
    const y = el.y ?? 0;
    const w = el.width ?? 0;
    const h = el.height ?? 0;
    minX = Math.min(minX, x);
    minY = Math.min(minY, y);
    maxX = Math.max(maxX, x + w);
    maxY = Math.max(maxY, y + h);
  }

  const pad = 40;
  minX -= pad; minY -= pad; maxX += pad; maxY += pad;
  const width = maxX - minX;
  const height = maxY - minY;
  const bg = appState.viewBackgroundColor || "#ffffff";

  let svg = `<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="${width}" height="${height}" viewBox="${minX} ${minY} ${width} ${height}">`;
  svg += `<rect x="${minX}" y="${minY}" width="${width}" height="${height}" fill="${bg}"/>`;

  // Render elements
  for (const el of real) {
    if (el.type === "rectangle") {
      const rx = el.roundness?.type === 3 ? 8 : 0;
      const strokeDash = el.strokeStyle === "dashed" ? ' stroke-dasharray="8,4"' : "";
      svg += `<rect x="${el.x}" y="${el.y}" width="${el.width}" height="${el.height}" rx="${rx}" fill="${el.backgroundColor || "none"}" stroke="${el.strokeColor || "#000"}" stroke-width="2"${strokeDash}/>`;
    } else if (el.type === "text") {
      const lines = (el.text || "").split("\n");
      const fontSize = el.fontSize || 14;
      const color = el.strokeColor || "#1e1e1e";
      const textAnchor = el.textAlign === "center" ? "middle" : "start";
      const tx = el.textAlign === "center" ? el.x + (el.width || 0) / 2 : el.x;
      for (let i = 0; i < lines.length; i++) {
        const ty = el.y + fontSize + i * (fontSize + 4);
        svg += `<text x="${tx}" y="${ty}" font-size="${fontSize}" fill="${color}" font-family="Arial, sans-serif" text-anchor="${textAnchor}">${escapeXml(lines[i])}</text>`;
      }
    } else if (el.type === "arrow") {
      const points = el.points || [[0, 0], [0, 0]];
      const ox = el.x ?? 0;
      const oy = el.y ?? 0;
      let d = `M ${ox + points[0][0]} ${oy + points[0][1]}`;
      for (let i = 1; i < points.length; i++) {
        d += ` L ${ox + points[i][0]} ${oy + points[i][1]}`;
      }
      const strokeDash = el.strokeStyle === "dashed" ? ' stroke-dasharray="8,4"' : "";
      svg += `<path d="${d}" fill="none" stroke="${el.strokeColor || "#495057"}" stroke-width="2" marker-end="url(#arrow)"${strokeDash}/>`;
    } else if (el.type === "image") {
      const fileId = el.fileId;
      const fileData = files[fileId];
      if (fileData?.dataURL) {
        svg += `<image x="${el.x}" y="${el.y}" width="${el.width}" height="${el.height}" href="${fileData.dataURL}"/>`;
      }
    }
  }

  // Arrow marker
  svg += '<defs><marker id="arrow" markerWidth="10" markerHeight="10" refX="9" refY="3" orient="auto"><path d="M0,0 L0,6 L9,3 z" fill="#495057"/></marker></defs>';
  svg += "</svg>";
  return svg;
}

function escapeXml(s) {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

main().catch((err) => {
  console.error(JSON.stringify({ success: false, error: err.message }));
  process.exit(1);
});
