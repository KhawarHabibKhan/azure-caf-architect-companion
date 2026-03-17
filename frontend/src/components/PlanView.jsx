export default function PlanView({ workloads, waves }) {
  return (
    <>
      {workloads?.length > 0 && (
        <div className="card">
          <h3>Workload Classification (7 R's)</h3>
          <table>
            <thead><tr><th>Workload</th><th>Classification</th><th>Effort</th><th>Target Services</th><th>Rationale</th></tr></thead>
            <tbody>
              {workloads.map((w, i) => (
                <tr key={i}>
                  <td>{w.workload_name}</td>
                  <td><span className={`badge badge-${w.classification}`}>{w.classification}</span></td>
                  <td><span className={`badge badge-${w.estimated_effort}`}>{w.estimated_effort}</span></td>
                  <td>{(w.target_azure_services || []).slice(0, 3).join(", ")}</td>
                  <td style={{ fontSize: 13, color: "#666" }}>{w.rationale}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {waves?.length > 0 && (
        <div className="card">
          <h3>Migration Wave Plan</h3>
          <table>
            <thead><tr><th>Wave</th><th>Timeline</th><th>Workloads</th><th>Rationale</th></tr></thead>
            <tbody>
              {waves.map((w, i) => (
                <tr key={i}>
                  <td><strong>Wave {w.wave_number}</strong></td>
                  <td>{w.timeline}</td>
                  <td>{(w.workloads || []).join(", ")}</td>
                  <td style={{ fontSize: 13, color: "#666" }}>{w.rationale}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
