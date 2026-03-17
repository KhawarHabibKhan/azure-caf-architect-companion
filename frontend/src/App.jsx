import { useState } from "react";
import { reviewInfrastructure } from "./api";
import InputWizard from "./components/InputWizard";
import AssessmentView from "./components/AssessmentView";
import PlanView from "./components/PlanView";
import CostBreakdown from "./components/CostBreakdown";
import RiskRegister from "./components/RiskRegister";
import DiagramViewer from "./components/DiagramViewer";
import ReportView from "./components/ReportView";

const TABS = ["Assessment", "Plan", "Costs", "Risks", "Architecture", "Report"];

export default function App() {
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [activeTab, setActiveTab] = useState("Assessment");

  const handleSubmit = async (content) => {
    setLoading(true);
    setError(null);
    setReport(null);
    try {
      const result = await reviewInfrastructure(content);
      setReport(result);
      setActiveTab("Assessment");
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="app">
      <div className="header">
        <h1>Azure CAF Architect Companion</h1>
        <p>Automated Cloud Adoption Framework assessment and recommendations</p>
      </div>

      <InputWizard onSubmit={handleSubmit} loading={loading} />

      {error && <div className="error">{error}</div>}

      {loading && (
        <div className="loading">
          <div className="spinner" />
          <p style={{ marginTop: 12 }}>Running CAF assessment pipeline...</p>
          <p style={{ fontSize: 13, color: "#999" }}>
            Parsing input → Assessment → Workload classification → Cost estimation → Risk analysis → Landing zone design
          </p>
        </div>
      )}

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
