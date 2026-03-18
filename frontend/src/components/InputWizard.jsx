import { useState } from "react";

const SAMPLE = `MediTrack Health Solutions is a healthcare company with 200 employees operating out of a single on-premises data center in Chicago. They run 7 applications including a Patient Portal (React/Node.js, PostgreSQL, 5000 daily users), an EHR system (.NET, SQL Server 2TB, mission-critical), medical imaging storage (50TB DICOM), a legacy billing system on Oracle that is no longer vendor-supported, and dev/test VMs. HR is already on Workday. The team of 15 has no Azure experience. They must comply with HIPAA, have a $500K migration budget, $20K/month target, and need to complete the migration in 12 months.`;

export default function InputWizard({ onSubmit, loading }) {
  const [content, setContent] = useState("");

  const handleFile = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const text = await file.text();
    setContent(text);
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
        <button className="btn btn-secondary" onClick={() => setContent(SAMPLE)} disabled={loading}>
          Load Sample
        </button>
        <label className="btn btn-secondary" style={{ cursor: loading ? "not-allowed" : "pointer", opacity: loading ? 0.6 : 1 }}>
          Upload File
          <input type="file" accept=".txt,.md" onChange={handleFile} style={{ display: "none" }} disabled={loading} />
        </label>
      </div>
    </div>
  );
}
