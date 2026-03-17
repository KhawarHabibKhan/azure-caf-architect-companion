import { useState } from "react";

const SAMPLE = `Company: MediTrack Health Solutions
Industry: Healthcare
Employees: 200
Compliance: HIPAA required

Current Infrastructure:
- 2 on-premises data centers (Dallas, Chicago)
- Active Directory for identity
- VMware vSphere managing 60 VMs

Applications:
1. Patient Portal - .NET Framework 4.8, SQL Server 2016 (2TB), 15K daily users, 99.9% SLA
2. EHR System - Java on 8 VMs, Oracle 19c (5TB), HL7/FHIR integrations
3. HR & Payroll - SAP SuccessFactors (SaaS), AD SSO
4. Medical Imaging (PACS) - 50TB DICOM images, 80 radiologists
5. Legacy Billing - COBOL on IBM AS/400, 20 years old
6. Wiki & File Shares - Confluence VM + 3TB file server
7. Dev/Test - 12 VMs, no production traffic

Team: 1 IT Director, 3 Sysadmins, 2 Network Engineers, 1 Security Analyst, 8 Developers (.NET/Java), no cloud experience
Budget: $800K migration, $30K/month ongoing
Timeline: 12 months`;

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
      <textarea
        value={content}
        onChange={(e) => setContent(e.target.value)}
        placeholder="Describe your current infrastructure, applications, team, budget, and timeline..."
      />
      <div className="btn-row">
        <button className="btn btn-primary" onClick={() => onSubmit(content)} disabled={loading || !content.trim()}>
          {loading ? "Analyzing..." : "Run CAF Assessment"}
        </button>
        <button className="btn btn-secondary" onClick={() => setContent(SAMPLE)}>
          Load Sample
        </button>
        <label className="btn btn-secondary" style={{ cursor: "pointer" }}>
          Upload File
          <input type="file" accept=".txt,.md,.yaml,.yml" onChange={handleFile} style={{ display: "none" }} />
        </label>
      </div>
    </div>
  );
}
