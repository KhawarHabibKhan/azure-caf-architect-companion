export default function CostBreakdown({ data }) {
  if (!data) return null;

  const items = data.line_items || [];
  const total = data.total_monthly || 0;
  const withinBudget = data.within_budget;

  return (
    <div className="card">
      <h3>Cost Estimation</h3>
      <div style={{ display: "flex", gap: 24, marginBottom: 16 }}>
        <div>
          <span style={{ fontSize: 13, color: "#666" }}>Monthly Cost</span>
          <div style={{ fontSize: 24, fontWeight: 700 }}>${total.toLocaleString()}</div>
        </div>
        <div>
          <span style={{ fontSize: 13, color: "#666" }}>Budget Status</span>
          <div style={{ fontSize: 18, fontWeight: 600, color: withinBudget !== false ? "#2e7d32" : "#c62828" }}>
            {withinBudget !== false ? "Within Budget" : "Over Budget"}
          </div>
        </div>
      </div>

      {items.length > 0 && (
        <table>
          <thead><tr><th>Workload</th><th>Azure Service</th><th>Monthly Cost</th><th>Notes</th></tr></thead>
          <tbody>
            {items.map((item, i) => (
              <tr key={i}>
                <td>{item.category}</td>
                <td>{item.azure_service}</td>
                <td>${(item.monthly_cost || 0).toLocaleString()}</td>
                <td style={{ fontSize: 13, color: "#666" }}>{item.notes}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
