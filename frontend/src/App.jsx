import { useState } from "react";
import InputWizard from "./components/InputWizard";
import AssessmentView from "./components/AssessmentView";
import PlanView from "./components/PlanView";
import CostBreakdown from "./components/CostBreakdown";
import RiskRegister from "./components/RiskRegister";
import DiagramViewer from "./components/DiagramViewer";
import ReportView from "./components/ReportView";
import ProgressTracker from "./components/ProgressTracker";

const TABS = ["Assessment", "Plan", "Costs", "Risks", "Architecture", "Report"];

const TAB_SOURCES = {
  Assessment: "Scored from your team's cloud experience, infrastructure complexity, and compliance requirements",
  Plan: "Each app classified by the GPT-4.1 model using the CAF 7 R's framework",
  Costs: "Live prices fetched from the Azure Retail Prices API — no estimates, real SKU pricing",
  Risks: "Generated based on your compliance requirements, workload types, and team skill gaps",
  Architecture: "Hub-spoke landing zone designed following Microsoft CAF best practices",
  Report: "Synthesized from all three agent stages — Assessment, Plan & Analyze, and Design",
};

export default function App() {
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [activeTab, setActiveTab] = useState("Assessment");
  const [stepStatus, setStepStatus] = useState({});

  const handleSubmit = async (content) => {
    setLoading(true);
    setError(null);
    setReport(null);
    setStepStatus({});

    try {
      const response = await fetch("/api/review/stream", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content }),
      });

      if (!response.ok) {
        const err = await response.json().catch(() => ({ detail: "Request failed" }));
        throw new Error(err.detail || `HTTP ${response.status}`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop();

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          let event;
          try { event = JSON.parse(line.slice(6)); } catch { continue; }

          if (event.step === "error") {
            setError(event.message);
            setLoading(false);
            return;
          }

          setStepStatus(prev => ({ ...prev, [event.step]: event.status }));

          if (event.step === "complete" && event.status === "done") {
            setReport(event.data);
            setActiveTab("Assessment");
            setLoading(false);
          }
        }
      }
    } catch (err) {
      setError(err.message);
      setLoading(false);
    }
  };

  return (
    <div className="app">
      <div className="hero">
        <div className="hero-badge">Microsoft Cloud Adoption Framework</div>
        <h1>Azure CAF Architect Companion</h1>
        <p>Describe your current infrastructure and get a complete cloud migration plan — readiness assessment, workload classification, cost estimates, risk register, and architecture diagram.</p>
        <div className="hero-agents">
          <div className="agent-pill">Agent 1: Assessment</div>
          <div className="agent-arrow">→</div>
          <div className="agent-pill">Agent 2: Plan & Analyze</div>
          <div className="agent-arrow">→</div>
          <div className="agent-pill">Agent 3: Design & Report</div>
        </div>
      </div>

      <InputWizard onSubmit={handleSubmit} loading={loading} />

      {error && <div className="error-box">⚠ {error}</div>}

      {loading && <ProgressTracker stepStatus={stepStatus} />}

      {report && (
        <>
          <div className="tabs">
            {TABS.map((tab) => (
              <button
                key={tab}
                className={`tab ${activeTab === tab ? "active" : ""}`}
                onClick={() => setActiveTab(tab)}
              >
                {tab}
              </button>
            ))}
          </div>

          <div className="tab-source">{TAB_SOURCES[activeTab]}</div>

          {activeTab === "Assessment" && <AssessmentView data={report.assessment} summary={report.executive_summary} />}
          {activeTab === "Plan" && <PlanView workloads={report.plan?.workload_inventory} waves={report.plan?.migration_waves} />}
          {activeTab === "Costs" && <CostBreakdown data={report.cost_estimation} />}
          {activeTab === "Risks" && <RiskRegister risks={report.risk_register} />}
          {activeTab === "Architecture" && <DiagramViewer excalidrawFile={report.diagram?.excalidraw_file} runId={report.diagram?.run_id} />}
          {activeTab === "Report" && <ReportView summary={report.executive_summary} governance={report.governance_recommendations} />}
        </>
      )}
    </div>
  );
}
