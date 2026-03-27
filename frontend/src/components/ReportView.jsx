import { useState } from "react";
import { exportReportMarkdown } from "../api";

export default function ReportView({ summary, governance, fullReport }) {
  const [exporting, setExporting] = useState(false);

  if (!summary) return null;

  const breakdown = summary.classification_breakdown || {};
  const gov = governance || {};

  const handleExport = async () => {
    if (!fullReport) return;
    setExporting(true);
    try {
      await exportReportMarkdown(fullReport);
    } catch (err) {
      console.error("Export failed:", err);
    } finally {
      setExporting(false);
    }
  };

  return (
    <>
      <div className="card">
        <div className="card-header-row">
          <h3>Executive Summary</h3>
          <button
            className="btn btn-export"
            onClick={handleExport}
            disabled={exporting || !fullReport}
          >
            {exporting ? "Exporting..." : "Download Report"}
          </button>
        </div>
        <table>
          <tbody>
            <tr><td><strong>Company</strong></td><td>{summary.company_name}</td></tr>
            <tr><td><strong>Total Workloads</strong></td><td>{summary.total_workloads}</td></tr>
            <tr><td><strong>Timeline</strong></td><td>{summary.timeline_months} months</td></tr>
            <tr><td><strong>Monthly Cost</strong></td><td>${(summary.monthly_cost || 0).toLocaleString()}</td></tr>
            <tr><td><strong>Readiness</strong></td><td><span className={`badge badge-${summary.overall_readiness}`}>{summary.overall_readiness}</span></td></tr>
            <tr><td><strong>Risk Level</strong></td><td><span className={`badge badge-${summary.risk_level}`}>{summary.risk_level}</span></td></tr>
          </tbody>
        </table>
      </div>

      {Object.keys(breakdown).length > 0 && (
        <div className="card">
          <h3>Classification Breakdown</h3>
          <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
            {Object.entries(breakdown).map(([k, v]) => (
              <div key={k} style={{ textAlign: "center", padding: "8px 16px", background: "#f8f9fa", borderRadius: 6 }}>
                <div style={{ fontSize: 24, fontWeight: 700 }}>{v}</div>
                <span className={`badge badge-${k}`}>{k}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {(gov.policies?.length > 0 || gov.security?.length > 0) && (
        <div className="card">
          <h3>Governance Recommendations</h3>
          {gov.policies?.length > 0 && (
            <>
              <h4 style={{ marginTop: 8, fontSize: 14, color: "#555" }}>Policies</h4>
              <ul>{gov.policies.map((p, i) => <li key={i}>{p}</li>)}</ul>
            </>
          )}
          {gov.security?.length > 0 && (
            <>
              <h4 style={{ marginTop: 12, fontSize: 14, color: "#555" }}>Security</h4>
              <ul>{gov.security.map((s, i) => <li key={i}>{s}</li>)}</ul>
            </>
          )}
          {gov.cost_management?.length > 0 && (
            <>
              <h4 style={{ marginTop: 12, fontSize: 14, color: "#555" }}>Cost Management</h4>
              <ul>{gov.cost_management.map((c, i) => <li key={i}>{c}</li>)}</ul>
            </>
          )}
        </div>
      )}
    </>
  );
}
