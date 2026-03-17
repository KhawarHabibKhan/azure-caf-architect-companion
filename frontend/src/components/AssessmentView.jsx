export default function AssessmentView({ data, summary }) {
  if (!data) return null;

  const scores = data.readiness_scores || {};
  const model = data.operating_model || {};
  const skills = data.skills_assessment || [];

  return (
    <>
      <div className="card">
        <h3>Readiness Assessment</h3>
        <p><strong>Overall Readiness:</strong> <span className={`badge badge-${data.overall_readiness}`}>{data.overall_readiness}</span></p>
        {data.readiness_summary && <p style={{ marginTop: 8 }}>{data.readiness_summary}</p>}
        <table style={{ marginTop: 12 }}>
          <thead><tr><th>Dimension</th><th>Score</th></tr></thead>
          <tbody>
            {Object.entries(scores).map(([k, v]) => (
              <tr key={k}>
                <td>{k.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase())}</td>
                <td><span className={`badge badge-${v}`}>{v}</span></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="card">
        <h3>Operating Model</h3>
        <p><strong>Recommended:</strong> <span className="badge badge-medium">{model.recommended}</span></p>
        <p style={{ marginTop: 8 }}>{model.rationale}</p>
      </div>

      {skills.length > 0 && (
        <div className="card">
          <h3>Skills Assessment</h3>
          <table>
            <thead><tr><th>Role</th><th>Gap</th><th>Training</th><th>Priority</th></tr></thead>
            <tbody>
              {skills.map((s, i) => (
                <tr key={i}>
                  <td>{s.role}</td>
                  <td>{s.gap}</td>
                  <td>{s.recommended_training}</td>
                  <td><span className={`badge badge-${s.priority === "immediate" ? "high" : s.priority === "short-term" ? "medium" : "low"}`}>{s.priority}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
