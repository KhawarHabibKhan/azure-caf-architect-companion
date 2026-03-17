const BASE = "/api";

export async function reviewInfrastructure(content) {
  const res = await fetch(`${BASE}/review`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content }),
  });
  if (!res.ok) throw new Error(`Review failed: ${res.status}`);
  return res.json();
}

export async function assessOnly(content) {
  const res = await fetch(`${BASE}/assess`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content }),
  });
  if (!res.ok) throw new Error(`Assessment failed: ${res.status}`);
  return res.json();
}

export function pngDownloadUrl(runId) {
  return `${BASE}/download/png/${runId}`;
}

export function excalidrawDownloadUrl(runId) {
  return `${BASE}/download/excalidraw/${runId}`;
}

export async function fetchPngBlobUrl(runId) {
  const res = await fetch(pngDownloadUrl(runId));
  if (!res.ok) return null;
  const blob = await res.blob();
  return URL.createObjectURL(blob);
}

export function downloadFile(url, filename) {
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
}
