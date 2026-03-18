const STEPS = [
  { key: "parsing",    label: "Parsing infrastructure description",        agent: null },
  { key: "assessment", label: "Running readiness assessment",               agent: "Agent 1" },
  { key: "planning",   label: "Classifying workloads & planning migration", agent: "Agent 2" },
  { key: "design",     label: "Designing Azure landing zone",               agent: "Agent 3" },
  { key: "diagram",    label: "Generating architecture diagram",            agent: "Agent 3" },
  { key: "report",     label: "Building final report",                      agent: "Agent 3" },
];

export default function ProgressTracker({ stepStatus }) {
  return (
    <div className="progress-tracker">
      <div className="progress-title">Running CAF Assessment Pipeline</div>
      <div className="progress-steps">
        {STEPS.map((s) => {
          const status = stepStatus[s.key];
          const isDone = status === "done" || stepStatus["complete"] === "done";
          const isRunning = status === "running";

          return (
            <div key={s.key} className={`progress-step ${isDone ? "done" : isRunning ? "running" : "pending"}`}>
              <div className="step-icon">
                {isDone ? "✓" : isRunning ? <span className="step-spinner" /> : "○"}
              </div>
              <div className="step-info">
                <span className="step-label">{s.label}</span>
                {s.agent && <span className="step-agent">{s.agent}</span>}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
