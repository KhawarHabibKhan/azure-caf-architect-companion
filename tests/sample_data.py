"""Sample test data for CAF Companion tests."""

MEDITRACK_INPUT = """
Company: MediTrack Health Solutions
Industry: Healthcare
Employees: 200
Compliance: HIPAA required

Current Infrastructure:
- 2 on-premises data centers (Dallas, Chicago)
- Active Directory for identity
- VMware vSphere managing 60 VMs

Applications:
1. Patient Portal (public-facing)
   - .NET Framework 4.8 monolith
   - SQL Server 2016 database (2TB)
   - 15,000 daily active users
   - SLA: 99.9% uptime required

2. Electronic Health Records (EHR) System
   - Java-based, runs on 8 VMs
   - Oracle Database 19c (5TB)
   - Used by 500 staff daily
   - Integrates with 3 external lab systems via HL7/FHIR APIs

3. Internal HR & Payroll
   - Off-the-shelf SAP SuccessFactors (SaaS)
   - Connected to on-prem AD for SSO

4. Medical Imaging Storage (PACS)
   - 50TB of DICOM images
   - Accessed by 80 radiologists
   - Requires low-latency access

5. Legacy Billing System
   - COBOL-based, runs on an IBM AS/400
   - 20 years old, 2 people know how it works
   - Processes 10,000 claims/month

6. Internal Wiki & File Shares
   - Confluence on a VM
   - 3TB of shared files on Windows file server

7. Dev/Test Environments
   - 12 VMs for development and QA
   - No production traffic

Team:
- 1 IT Director
- 3 System Administrators (Windows/Linux)
- 2 Network Engineers
- 1 Security Analyst
- 8 Developers (.NET and Java)
- No cloud experience on the team

Budget: $800K for migration, $30K/month target for ongoing cloud costs
Timeline: Want to be migrated within 12 months
"""

MEDITRACK_PARSED = {
    "company_name": "MediTrack Health Solutions",
    "industry": "Healthcare",
    "employee_count": 200,
    "compliance_requirements": ["HIPAA"],
    "current_infrastructure": [
        {"name": "Dallas Data Center", "type": "data_center", "description": "On-premises data center", "location": "Dallas"},
        {"name": "Chicago Data Center", "type": "data_center", "description": "On-premises data center", "location": "Chicago"},
        {"name": "Active Directory", "type": "identity", "description": "On-prem identity management", "location": ""},
        {"name": "VMware vSphere", "type": "virtualization", "description": "Managing 60 VMs", "location": ""},
    ],
    "applications": [
        {
            "name": "Patient Portal",
            "description": "Public-facing patient portal",
            "technology_stack": ".NET Framework 4.8",
            "database": "SQL Server 2016",
            "data_size_gb": 2000,
            "daily_users": 15000,
            "sla_requirement": "99.9%",
            "integrations": [],
            "criticality": "high",
        },
        {
            "name": "Electronic Health Records (EHR)",
            "description": "Java-based EHR system on 8 VMs",
            "technology_stack": "Java",
            "database": "Oracle Database 19c",
            "data_size_gb": 5000,
            "daily_users": 500,
            "sla_requirement": "",
            "integrations": ["HL7", "FHIR", "3 external lab systems"],
            "criticality": "high",
        },
        {
            "name": "HR & Payroll",
            "description": "SAP SuccessFactors SaaS",
            "technology_stack": "SaaS",
            "database": "",
            "data_size_gb": 0,
            "daily_users": 0,
            "sla_requirement": "",
            "integrations": ["Active Directory SSO"],
            "criticality": "medium",
        },
        {
            "name": "Medical Imaging (PACS)",
            "description": "50TB DICOM image storage for radiologists",
            "technology_stack": "",
            "database": "",
            "data_size_gb": 50000,
            "daily_users": 80,
            "sla_requirement": "",
            "integrations": [],
            "criticality": "high",
        },
        {
            "name": "Legacy Billing System",
            "description": "COBOL on IBM AS/400, 20 years old",
            "technology_stack": "COBOL",
            "database": "",
            "data_size_gb": 0,
            "daily_users": 0,
            "sla_requirement": "",
            "integrations": [],
            "criticality": "medium",
        },
        {
            "name": "Internal Wiki & File Shares",
            "description": "Confluence VM + 3TB Windows file server",
            "technology_stack": "Confluence",
            "database": "",
            "data_size_gb": 3000,
            "daily_users": 0,
            "sla_requirement": "",
            "integrations": [],
            "criticality": "low",
        },
        {
            "name": "Dev/Test Environments",
            "description": "12 VMs for development and QA",
            "technology_stack": "",
            "database": "",
            "data_size_gb": 0,
            "daily_users": 0,
            "sla_requirement": "",
            "integrations": [],
            "criticality": "low",
        },
    ],
    "team": [
        {"role": "IT Director", "count": 1, "current_skills": ["IT management"], "cloud_experience": "none"},
        {"role": "System Administrator", "count": 3, "current_skills": ["Windows", "Linux"], "cloud_experience": "none"},
        {"role": "Network Engineer", "count": 2, "current_skills": ["networking"], "cloud_experience": "none"},
        {"role": "Security Analyst", "count": 1, "current_skills": ["security"], "cloud_experience": "none"},
        {"role": "Developer", "count": 8, "current_skills": [".NET", "Java"], "cloud_experience": "none"},
    ],
    "budget_migration": 800000,
    "budget_monthly_target": 30000,
    "timeline_months": 12,
    "additional_context": "",
}
