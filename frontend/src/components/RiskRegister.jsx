export default function RiskRegister({ risks }) {
  if (!risks || risks.length === 0) {
    return <div className="card"><h3>Risk Register</h3><p>No risks identified.</p></div>;
  }

  return (
    <div className="card">
      <h3>Risk Register ({risks.length} risks)</h3>
      <table>
        <thead><tr><th>ID</th><th>Risk</th><th>Category</th><th>Probability</th><th>Impact</th><th>Priority</th><th>Mitigation</th></tr></thead>
        <tbody>
          {risks.map((r, i) => (
            <tr key={i}>
              <td>{r.id}</td>
              <td>{r.risk}</td>
              <td>{r.category}</td>
              <td><span className={`badge badge-${r.probability}`}>{r.probability}</span></td>
              <td><span className={`badge badge-${r.impact}`}>{r.impact}</span></td>
              <td><span className={`badge badge-${r.priority}`}>{r.priority}</span></td>
              <td style={{ fontSize: 13 }}>{r.mitigation}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
