"""
ATS Resume Engine — Pure Python, Credit-Efficient
- Uses Ram's actual uploaded resume as master (exact content preserved)
- Uses claude-haiku (cheap) for targeted keyword extraction only
- Generates professional ATS-optimized PDF matching Ram's design
- Design: Bold name, contact, section headers with blue underlines, bullets, env italic
- Target: 98%+ ATS score
"""

import json, os, copy
from pathlib import Path
from io import BytesIO
import anthropic

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

MASTER = {
    "name":    "Ram Burri",
    "contact": "Email: Ram.burri1408@gmail.com  |  Ph: 9544454339",
    "summary": (
        "Full-Stack .NET Developer and Enterprise Programmer Analyst with 4+ years of experience "
        "designing, developing, and supporting scalable enterprise applications using ASP.NET Core, "
        "React, Angular, and cloud-native architectures on Azure. Specialized in building "
        "microservices, high-performance REST APIs, system integrations, and event-driven solutions "
        "using .NET 8, Entity Framework Core, SQL Server, and Oracle PL/SQL. Experienced in ERP "
        "system support, containerized deployments with Docker and Kubernetes, and automated CI/CD "
        "pipelines with Azure DevOps. Strong background in enterprise application development, system "
        "analysis, and database optimization including Oracle PL/SQL query tuning. Proven ability to "
        "review and improve code for performance, security, and functionality. Adept at collaborating "
        "with cross-functional teams, reporting and tracking project tasks using Jira, and conducting "
        "code reviews within SAFe Agile environments. Skilled in initiating feasibility studies, "
        "analyzing business requirements, and directing changes to existing enterprise systems."
    ),
    "skills": {
        "Frontend":        "React.js, Next.js, Angular 14/18, TypeScript, JavaScript (ES6+), HTML5, CSS3/SCSS, RxJS, Reactive Forms",
        "Backend":         "Node.js, Express.js, C#, .NET Core, .NET 8, ASP.NET MVC, ASP.NET Core, RESTful APIs, Microservices, WCF, ERP Systems Integration",
        "ORM / Data":      "Entity Framework Core, ADO.NET, LINQ, Dapper",
        "Database":        "Oracle (PL/SQL), SQL Server (T-SQL), PostgreSQL, Oracle SQL Developer, Stored Procedures, Query Optimization",
        "Messaging":       "Azure Event Hub",
        "Security":        "JWT, OAuth2, IdentityServer4, Role-Based Authorization, SOX/PCI-DSS Compliance",
        "Cloud / DevOps":  "Azure, Azure DevOps, Oracle Cloud Infrastructure (OCI), Docker, Kubernetes, Jenkins, AWS, Azure Functions",
        "Testing":         "xUnit, Jest, TDD",
        "Version Control": "Git, GitHub, Bitbucket",
        "Tools":           "SSMS, Oracle SQL Developer, Jira, Cursor AI, GitHub Copilot, Azure DevOps Boards",
        "Methodologies":   "SAFe Agile, Scrum, Code Reviews, Cross-functional Collaboration, Systems Analysis, Feasibility Studies, Project Planning",
    },
    "experience": [
        {
            "title":    "Full Stack Developer (.NET / React / Azure)",
            "company":  "Jefferson Bank",
            "location": "San Antonio, TX",
            "dates":    "Nov 2024 – Present",
            "bullets": [
                "Built multi-step React.js workflows and dynamic forms for fraud case management using React Hook Form with role-based field visibility, reducing manual review time for fraud analysts.",
                "Developed ASP.NET Core RESTful microservices for transaction lookup, account activity, and alert management with versioned endpoints and consistent error handling.",
                "Built and maintained .NET 8 backend APIs integrated with Entity Framework Core and SQL Server, supporting internal banking dashboards and operational transaction workflows.",
                "Built a shared React component library adopted across three internal banking applications, enforcing TypeScript strict mode and accessibility standards.",
                "Integrated Azure Event Hub to consume real-time transaction event streams, triggering automated fraud alert notifications on the React dashboard.",
                "Implemented JWT authentication with refresh token rotation and role-based route guards; remediated SOX/PCI-DSS compliance vulnerabilities in API input validation and React XSS exposure points.",
                "Configured Azure DevOps CI/CD pipelines with build, test, and deploy stages; containerized services with Docker and managed Kubernetes deployments with zero-downtime rolling updates.",
                "Maintained 85%+ test coverage using Jest for React components and xUnit for .NET Core API layers across critical transaction and fraud modules.",
                "Contributed to sprint planning, backlog grooming, and cross-team dependency coordination within a SAFe Agile environment; reported and tracked project tasks using Jira and Azure DevOps Boards, and conducted code reviews to ensure performance, security, and adherence to enterprise coding standards.",
                "Utilized Oracle PL/SQL to analyze and optimize legacy backlog queries; rewrote underperforming stored procedures and fine-tuned execution plans, improving query response times and reducing database load for high-volume transaction datasets.",
            ],
            "env": "React.js, Node.js, Express.js, TypeScript, HTML5, CSS/SCSS, C#, .NET 8, ASP.NET Core, Entity Framework Core, SQL Server, T-SQL, Oracle (PL/SQL), Oracle SQL Developer, Azure DevOps, Azure Event Hub, Docker, Kubernetes, JWT, OAuth2, xUnit, Jest, Jira, SAFe Agile.",
        },
        {
            "title":    "Full Stack Developer",
            "company":  "Techbion Software Systems Pvt Ltd",
            "location": "India",
            "dates":    "Jun 2022 – Aug 2023",
            "bullets": [
                "Contributed to modernization of legacy ASP.NET WebForms and jQuery-based portals, re-architecting the backend into layered ASP.NET MVC and ASP.NET Core applications.",
                "Implemented idempotent RESTful APIs using ASP.NET Core to decompose monolithic payment logic into maintainable service components, preventing duplicate transactions.",
                "Built Angular 14 components for interactive client-side workflows alongside ASP.NET MVC Razor views, progressively modernizing the frontend while maintaining legacy compatibility.",
                "Participated in architectural discussions evaluating Azure Functions for event-driven processing as part of the cloud modernization roadmap.",
                "Modernized data access using Entity Framework Core for new modules while retaining Dapper and ADO.NET in performance-critical legacy paths; optimized SQL Server stored procedures.",
                "Secured API endpoints using OAuth2, JWT, and IdentityServer4, ensuring SOX and PCI-DSS compliance across customer-facing and internal systems.",
                "Implemented structured exception handling, global error middleware, and resilient retry mechanisms to improve API reliability.",
                "Configured Jenkins and Azure DevOps pipelines for automated build, test, and deployment using Docker containerization.",
            ],
            "env": "Angular 14, TypeScript, RxJS, HTML5, CSS/SCSS, C#, ASP.NET Core, .NET Core, ADO.NET, Entity Framework Core, Dapper, SQL Server, T-SQL, Oracle, PL/SQL, OAuth2, JWT, IdentityServer4, Jenkins, Azure DevOps, Docker, Jira, Agile/Scrum.",
        },
        {
            "title":    ".NET Developer",
            "company":  "Unisys Global Services India",
            "location": "India",
            "dates":    "Nov 2020 – May 2022",
            "bullets": [
                "Developed and maintained ASP.NET MVC web applications in C# and .NET Framework with clean separation across presentation, business, and data access layers.",
                "Built responsive front-end interfaces using HTML5, CSS3, and JavaScript within ASP.NET MVC Razor views with client-side validation and AJAX-based data loading.",
                "Implemented and optimized T-SQL stored procedures, database views, and LINQ queries for SQL Server data access using ADO.NET and Entity Framework.",
                "Designed and consumed WCF-based web services with XML/XSLT transformations to support enterprise data exchange and reporting.",
                "Applied dependency injection, custom validation, and reusable ASP.NET user controls to improve maintainability across application modules.",
                "Wrote xUnit tests following TDD practices; participated in code reviews within an Agile/Scrum team.",
            ],
            "env": "C#, .NET Framework, ASP.NET MVC, ADO.NET, Entity Framework, SQL Server, T-SQL, JavaScript, HTML5, CSS3, WCF, LINQ, XML/XSLT, xUnit, Agile/Scrum.",
        },
    ],
    "certifications": [
        "Oracle Cloud Infrastructure 2025 Developer Professional (1Z0-1084-25)  |  Oracle  |  2025",
    ],
    "education": {
        "degree":     "Master of Science in Computer Science",
        "school":     "Florida Atlantic University",
        "location":   "Boca Raton, FL",
        "dates":      "Aug 2023 – May 2025",
        "gpa":        "3.72 / 4.0",
        "coursework": "Software Engineering, Information Retrieval, New Directions in Database Systems, Cloud Security, Cloud Computing, Conversational AI, Analysis of Algorithms, Data Science, Deep Learning",
    },
}


# ── Credit-Efficient Enhancement (Haiku = ~10x cheaper than Opus) ──────────

def enhance_for_job(job: dict) -> dict:
    """
    Uses claude-haiku for cheap targeted enhancement.
    Only extracts missing keywords + reorders bullets.
    Does NOT rewrite anything — preserves all original content.
    """
    result = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=500,
        system=(
            "ATS resume optimizer. Analyze JD vs resume. Return ONLY JSON:\n"
            '{"missing_skills": {"Frontend":"comma-sep if any","Backend":"comma-sep if any",'
            '"Cloud / DevOps":"comma-sep if any","Testing":"comma-sep if any",'
            '"Methodologies":"comma-sep if any"},'
            '"priority_bullets": [0,1,2,3],'
            '"extra_bullet": "one NEW bullet point if JD requires something completely missing, else empty string"}\n'
            "Rules: Only add skills explicitly in JD. Never invent experience. "
            "priority_bullets = indices of existing bullets most relevant to this JD (0-9). "
            "Return ONLY valid JSON."
        ),
        messages=[{"role": "user", "content": (
            f"JD Title: {job['title']} at {job['company']}\n"
            f"JD (first 1000 chars):\n{job['description'][:1000]}\n\n"
            f"Current skills: {json.dumps(MASTER['skills'])}\n"
            f"Current bullets (indexed):\n" +
            "\n".join(f"{i}: {b[:80]}" for i, b in enumerate(MASTER['experience'][0]['bullets']))
        )}]
    ).content[0].text.strip()

    try:
        return json.loads(result.replace("```json","").replace("```","").strip())
    except Exception as e:
        print(f"  ! Enhancement parse error: {e}")
        return {}


def apply_enhancement(enhanced: dict) -> dict:
    """Merge AI suggestions into master resume without changing structure."""
    resume = copy.deepcopy(MASTER)

    # Add missing skills to relevant categories
    missing = enhanced.get("missing_skills", {})
    for category, extras in missing.items():
        if extras and category in resume["skills"]:
            extra_list = [s.strip() for s in extras.split(",") if s.strip()]
            existing   = resume["skills"][category]
            new_items  = [s for s in extra_list if s.lower() not in existing.lower()]
            if new_items:
                resume["skills"][category] = existing + ", " + ", ".join(new_items)

    # Reorder top bullets for this JD
    priority = enhanced.get("priority_bullets", [])
    if priority:
        original  = resume["experience"][0]["bullets"]
        reordered = []
        seen      = set()
        for i in priority:
            if 0 <= i < len(original) and i not in seen:
                reordered.append(original[i])
                seen.add(i)
        for i, b in enumerate(original):
            if i not in seen:
                reordered.append(b)
        resume["experience"][0]["bullets"] = reordered

    # Add extra bullet if truly needed
    extra = enhanced.get("extra_bullet", "").strip()
    if extra and len(extra) > 20:
        resume["experience"][0]["bullets"].insert(2, extra)

    return resume


# ── PDF Generation ─────────────────────────────────────────────────────────

BLUE = (0.122, 0.306, 0.475)  # #1F4E79
DARK = (0.08,  0.08,  0.08)
GRAY = (0.30,  0.30,  0.30)

def generate_ats_pdf(resume: dict) -> bytes:
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.units import inch
    from reportlab.pdfgen import canvas
    from reportlab.platypus import Paragraph
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
    from reportlab.lib import colors as rlc

    buf  = BytesIO()
    W, H = letter
    ML   = 0.60 * inch
    MR   = 0.60 * inch
    MT   = 0.55 * inch
    MB   = 0.55 * inch
    CW   = W - ML - MR

    c = canvas.Canvas(buf, pagesize=letter)
    c.setTitle("Ram Burri - Resume")
    c.setAuthor("Ram Burri")
    c.setSubject("Full Stack .NET Developer")
    y = H - MT

    def new_page():
        nonlocal y
        c.showPage()
        y = H - MT

    def check(needed=0.22*inch):
        if y < MB + needed:
            new_page()

    def draw_hline(color=BLUE, width=0.8):
        nonlocal y
        c.setStrokeColorRGB(*color)
        c.setLineWidth(width)
        c.line(ML, y, W - MR, y)

    def section_hdr(title):
        nonlocal y
        check(0.5*inch)
        y -= 4
        c.setFont("Helvetica-Bold", 10.5)
        c.setFillColorRGB(*BLUE)
        c.drawString(ML, y, title.upper())
        y -= 3
        draw_hline()
        y -= 8

    def para(text, font="Helvetica", size=9.2, color=DARK,
             indent=0, after=3, width=None, align="justify"):
        nonlocal y
        if not text:
            return
        from reportlab.lib import colors as rlc
        from reportlab.platypus import Paragraph
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.lib.enums import TA_JUSTIFY, TA_LEFT

        mw  = (width or CW) - indent
        aln = TA_JUSTIFY if align == "justify" else TA_LEFT
        sty = ParagraphStyle(
            "p", fontName=font, fontSize=size, leading=size*1.32,
            alignment=aln, textColor=rlc.Color(*color),
            leftIndent=0, rightIndent=0,
        )
        p = Paragraph(
            text.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;"),
            sty
        )
        pw, ph = p.wrapOn(c, mw, H)
        check(ph + after)
        p.drawOn(c, ML + indent, y - ph)
        y -= ph + after

    def bullet_line(text, size=9.0):
        nonlocal y
        from reportlab.lib import colors as rlc
        from reportlab.platypus import Paragraph
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.lib.enums import TA_LEFT

        INDENT = 14
        sty = ParagraphStyle(
            "bl", fontName="Helvetica", fontSize=size, leading=size*1.32,
            alignment=TA_LEFT, textColor=rlc.Color(*DARK),
        )
        p = Paragraph(
            text.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;"),
            sty
        )
        pw, ph = p.wrapOn(c, CW - INDENT, H)
        check(ph + 2)
        c.setFont("Helvetica", size)
        c.setFillColorRGB(*DARK)
        c.drawString(ML + 4, y - size * 0.78, "\u2022")
        p.drawOn(c, ML + INDENT, y - ph)
        y -= ph + 2

    def skills_row(label, value):
        nonlocal y
        from reportlab.lib import colors as rlc
        from reportlab.platypus import Paragraph
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.lib.enums import TA_LEFT

        check(0.18*inch)
        lbl = label + ": "
        lw  = c.stringWidth(lbl, "Helvetica-Bold", 9.0)

        # Draw label bold
        c.setFont("Helvetica-Bold", 9.0)
        c.setFillColorRGB(*DARK)
        c.drawString(ML, y, lbl)

        # Draw value — wrap if needed
        sty = ParagraphStyle(
            "sv", fontName="Helvetica", fontSize=9.0, leading=11.5,
            alignment=TA_LEFT, textColor=rlc.Color(*DARK),
        )
        p = Paragraph(
            value.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;"),
            sty
        )
        pw, ph = p.wrapOn(c, CW - lw, H)
        p.drawOn(c, ML + lw, y - ph + 9.0 * 0.75)
        y -= max(ph, 11.5) + 2

    def env_line(text):
        nonlocal y
        from reportlab.lib import colors as rlc
        from reportlab.platypus import Paragraph
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.lib.enums import TA_LEFT

        check(0.2*inch)
        lbl = "Environment: "
        lw  = c.stringWidth(lbl, "Helvetica-BoldOblique", 8.2)
        c.setFont("Helvetica-BoldOblique", 8.2)
        c.setFillColorRGB(*GRAY)
        c.drawString(ML, y, lbl)

        sty = ParagraphStyle(
            "ev", fontName="Helvetica-Oblique", fontSize=8.2, leading=10.5,
            alignment=TA_LEFT, textColor=rlc.Color(*GRAY),
        )
        p = Paragraph(
            text.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;"),
            sty
        )
        pw, ph = p.wrapOn(c, CW - lw, H)
        p.drawOn(c, ML + lw, y - ph + 8.2 * 0.75)
        y -= max(ph, 10.5) + 6

    def job_header(title, company, location, dates):
        nonlocal y
        check(0.6*inch)
        y -= 3
        # Title bold | Company, Location | Dates
        c.setFont("Helvetica-Bold", 9.5)
        c.setFillColorRGB(*DARK)
        tw = c.stringWidth(title, "Helvetica-Bold", 9.5)
        c.drawString(ML, y, title)
        c.setFont("Helvetica", 9.0)
        c.setFillColorRGB(*GRAY)
        rest = f"  |  {company}, {location}  |  {dates}"
        c.drawString(ML + tw, y, rest)
        y -= 13

    # ── BUILD PDF ────────────────────────────────────────────────────────

    # NAME — centered, large bold
    c.setFont("Helvetica-Bold", 20)
    c.setFillColorRGB(*BLUE)
    c.drawCentredString(W/2, y, resume["name"])
    y -= 15

    # CONTACT — centered, small gray
    c.setFont("Helvetica", 8.8)
    c.setFillColorRGB(*GRAY)
    c.drawCentredString(W/2, y, resume["contact"])
    y -= 5
    draw_hline(BLUE, 1.2)
    y -= 10

    # PROFESSIONAL SUMMARY
    section_hdr("Professional Summary")
    para(resume["summary"], size=9.0, after=6)

    # TECHNICAL SKILLS
    section_hdr("Technical Skills")
    for label, value in resume["skills"].items():
        skills_row(label, value)
    y -= 4

    # PROFESSIONAL EXPERIENCE
    section_hdr("Professional Experience")
    for exp in resume["experience"]:
        job_header(exp["title"], exp["company"], exp["location"], exp["dates"])
        for b in exp["bullets"]:
            bullet_line(b)
        y -= 2
        env_line(exp["env"])

    # CERTIFICATIONS
    section_hdr("Certifications")
    for cert in resume.get("certifications", []):
        c.setFont("Helvetica-Bold", 9.0)
        c.setFillColorRGB(*DARK)
        check(0.2*inch)
        c.drawString(ML, y, cert)
        y -= 13

    # EDUCATION
    section_hdr("Education")
    edu = resume["education"]
    c.setFont("Helvetica-Bold", 9.5)
    c.setFillColorRGB(*DARK)
    check(0.2*inch)
    c.drawString(ML, y, edu["degree"])
    y -= 12
    c.setFont("Helvetica", 9.0)
    c.setFillColorRGB(*GRAY)
    check(0.15*inch)
    c.drawString(ML, y, f"{edu['school']}, {edu['location']}  |  {edu['dates']}  |  GPA: {edu['gpa']}")
    y -= 12
    # Coursework — bold label + normal text
    from reportlab.lib import colors as rlc
    from reportlab.platypus import Paragraph
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_LEFT
    lbl = "Relevant Coursework: "
    lw  = c.stringWidth(lbl, "Helvetica-Bold", 9.0)
    c.setFont("Helvetica-Bold", 9.0)
    c.setFillColorRGB(*DARK)
    c.drawString(ML, y, lbl)
    sty = ParagraphStyle("cw", fontName="Helvetica", fontSize=9.0, leading=11,
                          textColor=rlc.Color(*DARK), alignment=TA_LEFT)
    p = Paragraph(edu["coursework"].replace("&","&amp;"), sty)
    pw, ph = p.wrapOn(c, CW - lw, H)
    p.drawOn(c, ML + lw, y - ph + 9.0 * 0.75)
    y -= max(ph, 11) + 4

    c.save()
    buf.seek(0)
    return buf.read()


# ── Main Entry ─────────────────────────────────────────────────────────────

def generate_ats_resume(job: dict, output_dir: str = "/tmp") -> dict:
    """Full pipeline: enhance → build PDF. Returns pdf_bytes + path."""
    print(f"  → ATS: {job['title']} @ {job['company']}")

    enhanced = enhance_for_job(job)
    resume   = apply_enhancement(enhanced)
    pdf_bytes = generate_ats_pdf(resume)

    safe     = "".join(c if c.isalnum() else "_" for c in job.get("company","X"))[:20]
    pdf_path = f"{output_dir}/Ram_Burri_{safe}.pdf"
    Path(pdf_path).write_bytes(pdf_bytes)

    print(f"  ✓ ATS PDF ready ({len(pdf_bytes):,} bytes)")
    return {"pdf_path": pdf_path, "pdf_bytes": pdf_bytes, "enhanced": enhanced}


if __name__ == "__main__":
    test = {
        "title": "Senior Full Stack .NET Developer",
        "company": "TestCorp",
        "description": (
            "Looking for .NET Core, C#, React, Angular, Azure, Microservices, "
            "SQL Server, Docker, Kubernetes, GraphQL, Redis, SignalR, Blazor, "
            "SOLID principles, CI/CD GitHub Actions, Agile Scrum experience."
        )
    }
    r = generate_ats_resume(test, "/tmp")
    print(f"Saved: {r['pdf_path']}")
