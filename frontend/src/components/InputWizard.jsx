import { useState, useEffect, useRef } from "react";

export default function InputWizard({ onSubmit, loading }) {
  const [content, setContent] = useState("");
  const [scenarios, setScenarios] = useState([]);
  const [showDropdown, setShowDropdown] = useState(false);
  const dropdownRef = useRef(null);

  useEffect(() => {
    fetch("/api/scenarios")
      .then((res) => res.json())
      .then((data) => setScenarios(data))
      .catch(() => {});
  }, []);

  useEffect(() => {
    const handleClickOutside = (e) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target)) {
        setShowDropdown(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const handleFile = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const text = await file.text();
    setContent(text);
  };

  const loadScenario = (scenario) => {
    setContent(scenario.content);
    setShowDropdown(false);
  };

  return (
    <div className="input-section">
      <div className="input-label">Describe your infrastructure</div>
      <div className="input-hint">
        Include your applications, team size and experience, compliance requirements, budget, and timeline. Plain English works fine.
      </div>
      <textarea
        value={content}
        onChange={(e) => setContent(e.target.value)}
        placeholder="e.g. We are a healthcare company with 200 employees. We run a patient portal on .NET and SQL Server, a legacy billing system on Oracle, and dev/test VMs on-premises. The team has no cloud experience. We need to comply with HIPAA and migrate within 12 months with a $500K budget..."
        disabled={loading}
      />
      <div className="btn-row">
        <button
          className="btn btn-primary"
          onClick={() => onSubmit(content)}
          disabled={loading || !content.trim()}
        >
          {loading ? "Analyzing..." : "Run CAF Assessment"}
        </button>
        <div className="scenario-dropdown" ref={dropdownRef}>
          <button
            className="btn btn-secondary"
            onClick={() => setShowDropdown(!showDropdown)}
            disabled={loading || scenarios.length === 0}
          >
            Load Scenario {showDropdown ? "\u25B4" : "\u25BE"}
          </button>
          {showDropdown && (
            <div className="scenario-menu">
              {scenarios.map((s) => (
                <button
                  key={s.id}
                  className="scenario-item"
                  onClick={() => loadScenario(s)}
                >
                  <span className="scenario-name">{s.name}</span>
                  {s.industry && <span className="scenario-industry">{s.industry}</span>}
                </button>
              ))}
            </div>
          )}
        </div>
        <label className="btn btn-secondary" style={{ cursor: loading ? "not-allowed" : "pointer", opacity: loading ? 0.6 : 1 }}>
          Upload File
          <input type="file" accept=".txt,.md" onChange={handleFile} style={{ display: "none" }} disabled={loading} />
        </label>
      </div>
    </div>
  );
}
