"""
ATS Resume Engine — Pure Python
- Claude adds missing skills from JD naturally into bullets
- Generates professional ATS-optimized PDF using reportlab
- Keeps Ram's exact design: Calibri-style fonts, blue headers, clean layout
- Target: 98%+ ATS score
- Zero external dependencies beyond reportlab
"""

import json, os
from pathlib import Path
from io import BytesIO
import anthropic

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

MASTER_RESUME = {
    "name": "Ram Burri",
    "contact": "Ram.burri1408@gmail.com  |  Ph: 9544454339  |  linkedin.com/in/ramburri",
    "summary": (
        "Full-Stack .NET Developer with 4+ years of experience designing scalable enterprise "
        "applications using ASP.NET Core, React, and cloud-native architectures on Azure. "
        "Specialized in building microservices, high-performance REST APIs, and event-driven "
        "systems using .NET 8, Entity Framework Core, and SQL Server. Experienced in containerized "
        "deployments with Docker and Kubernetes and automated CI/CD pipelines with Azure DevOps. "
        "Strong background in secure financial applications implementing OAuth2, JWT authentication, "
        "and compliance standards (SOX/PCI-DSS). Passionate about building resilient, "
        "high-availability systems and collaborating in Agile product teams to deliver reliable "
        "software at scale."
    ),
    "skills": {
        "Frontend":        "React.js, Next.js, Angular 14/18, TypeScript, JavaScript (ES6+), HTML5, CSS3/SCSS, RxJS, Reactive Forms",
        "Backend":         "Node.js, Express.js, C#, .NET Core, .NET 8, ASP.NET MVC, ASP.NET Core, RESTful APIs, Microservices",
        "ORM / Data":      "Entity Framework Core, ADO.NET, LINQ, Dapper",
        "Database":        "SQL Server (T-SQL), PostgreSQL, Oracle (PL/SQL)",
        "Messaging":       "Azure Event Hub",
        "Security":        "JWT, OAuth2, IdentityServer4, Role-Based Authorization, SOX/PCI-DSS Compliance",
        "Cloud / DevOps":  "Azure, Azure DevOps, Docker, Kubernetes, Jenkins, AWS",
        "Testing":         "xUnit, Jest, TDD",
        "Version Control": "Git, GitHub, Bitbucket",
        "Tools":           "SSMS, Oracle SQL Developer, Cursor AI, GitHub Copilot, Jira",
        "Methodologies":   "SAFe Agile, Scrum, Code Reviews, Cross-functional Collaboration",
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
                "Contributed to sprint planning, backlog grooming, and cross-team dependency coordination within a SAFe Agile environment.",
            ],
            "env": "React.js, Node.js, Express.js, TypeScript, HTML5, CSS/SCSS, C#, .NET 8, ASP.NET Core, Entity Framework Core, SQL Server, T-SQL, Azure DevOps, Azure Event Hub, Docker, Kubernetes, JWT, xUnit, Jest, Jira, SAFe Agile.",
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
    "education": {
        "degree":   "Master of Science in Computer Science",
        "school":   "Florida Atlantic University",
        "location": "Boca Raton, FL",
        "dates":    "Aug 2023 – May 2025",
        "gpa":      "3.72 / 4.0",
    },
}


# ── Step 1: AI Enhancement ─────────────────────────────────────────────────

def enhance_for_job(job: dict) -> dict:
    """Claude tailors resume content for this specific job."""
    result = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=2000,
        system=(
            "You are an expert ATS resume optimizer. Tailor this resume for maximum ATS match. "
            "Rules:\n"
            "1. Add missing JD keywords naturally into existing bullets — never invent fake experience\n"
            "2. Reorder bullets to put most relevant first\n"
            "3. Enhance summary to mirror JD language and keywords\n"
            "4. Add missing technical skills to skills section only if they appear in JD\n"
            "5. Never change company names, dates, education, or fabricate achievements\n"
            "6. Return ONLY valid JSON, no markdown, no backticks\n"
            "JSON format:\n"
            '{ "summary": "...", '
            '"skills": {"Frontend":"...","Backend":"...","ORM / Data":"...","Database":"...",'
            '"Messaging":"...","Security":"...","Cloud / DevOps":"...","Testing":"...",'
            '"Version Control":"...","Tools":"...","Methodologies":"..."}, '
            '"exp0_bullets": ["..."], "exp1_bullets": ["..."], "exp2_bullets": ["..."], '
            '"exp0_env": "...", "exp1_env": "...", "exp2_env": "..." }'
        ),
        messages=[{"role": "user", "content": (
            f"Job Title: {job['title']}\nCompany: {job['company']}\n"
            f"Job Description:\n{job['description'][:2000]}\n\n"
            f"Current Summary:\n{MASTER_RESUME['summary']}\n\n"
            f"Current Skills:\n" +
            "\n".join(f"{k}: {v}" for k, v in MASTER_RESUME['skills'].items()) +
            f"\n\nExperience 0 (Jefferson Bank) bullets:\n" +
            "\n".join(f"- {b}" for b in MASTER_RESUME['experience'][0]['bullets']) +
            f"\n\nExperience 1 (Techbion) bullets:\n" +
            "\n".join(f"- {b}" for b in MASTER_RESUME['experience'][1]['bullets']) +
            f"\n\nExperience 2 (Unisys) bullets:\n" +
            "\n".join(f"- {b}" for b in MASTER_RESUME['experience'][2]['bullets'])
        )}]
    ).content[0].text.strip()

    try:
        clean = result.replace("```json", "").replace("```", "").strip()
        return json.loads(clean)
    except Exception as e:
        print(f"  ! AI enhancement parse error: {e}")
        return {}


# ── Step 2: PDF Generation ─────────────────────────────────────────────────

BLUE       = (0.122, 0.306, 0.475)   # #1F4E79
DARK       = (0.1,   0.1,   0.1)
GRAY       = (0.35,  0.35,  0.35)
LINE_COLOR = (0.122, 0.306, 0.475)

def generate_ats_pdf(enhanced: dict) -> bytes:
    """Build professional ATS-optimized PDF from enhanced resume data."""
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.units import inch
    from reportlab.pdfgen import canvas
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import Paragraph
    from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY

    buf    = BytesIO()
    W, H   = letter
    ML     = 0.65 * inch   # left margin
    MR     = 0.65 * inch   # right margin
    MT     = 0.65 * inch   # top margin
    MB     = 0.65 * inch   # bottom margin
    CW     = W - ML - MR   # content width

    c = canvas.Canvas(buf, pagesize=letter)
    c.setTitle("Ram Burri - Resume")
    c.setAuthor("Ram Burri")
    c.setSubject("Full Stack .NET Developer")

    # Track Y position
    y = H - MT

    def check_page(needed=0.3*inch):
        nonlocal y
        if y < MB + needed:
            c.showPage()
            y = H - MT

    def draw_name():
        nonlocal y
        c.setFont("Helvetica-Bold", 20)
        c.setFillColorRGB(*BLUE)
        c.drawCentredString(W/2, y, "Ram Burri")
        y -= 16

    def draw_contact():
        nonlocal y
        c.setFont("Helvetica", 9)
        c.setFillColorRGB(*GRAY)
        c.drawCentredString(W/2, y, MASTER_RESUME["contact"])
        y -= 6
        # Divider line
        c.setStrokeColorRGB(*LINE_COLOR)
        c.setLineWidth(1.2)
        c.line(ML, y, W - MR, y)
        y -= 10

    def draw_section_header(title):
        nonlocal y
        check_page(0.5*inch)
        c.setFont("Helvetica-Bold", 11)
        c.setFillColorRGB(*BLUE)
        c.drawString(ML, y, title.upper())
        y -= 3
        c.setStrokeColorRGB(*LINE_COLOR)
        c.setLineWidth(0.8)
        c.line(ML, y, W - MR, y)
        y -= 9

    def draw_paragraph(text, font="Helvetica", size=9, color=DARK,
                        indent=0, spacing_after=4, max_width=None):
        nonlocal y
        if not text:
            return
        from reportlab.platypus import Paragraph as Para
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.lib.enums import TA_JUSTIFY

        mw = max_width or (CW - indent)
        style = ParagraphStyle(
            "s", fontName=font, fontSize=size,
            leading=size * 1.35, alignment=TA_JUSTIFY,
            textColor=(int(color[0]*255), int(color[1]*255), int(color[2]*255)),
            leftIndent=indent, rightIndent=0,
            spaceAfter=0, spaceBefore=0,
        )
        # Use reportlab color objects
        from reportlab.lib import colors as rlc
        rc = rlc.Color(color[0], color[1], color[2])
        style.textColor = rc

        p = Para(text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"), style)
        pw, ph = p.wrapOn(c, mw, H)
        check_page(ph + spacing_after)
        p.drawOn(c, ML + indent, y - ph)
        y -= ph + spacing_after

    def draw_bullet(text, font="Helvetica", size=9):
        nonlocal y
        bullet_x  = ML + 8
        text_x    = ML + 18
        text_w    = CW - 18

        from reportlab.platypus import Paragraph as Para
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.lib.enums import TA_LEFT
        from reportlab.lib import colors as rlc

        style = ParagraphStyle(
            "b", fontName=font, fontSize=size,
            leading=size * 1.35, alignment=TA_LEFT,
            textColor=rlc.Color(DARK[0], DARK[1], DARK[2]),
            leftIndent=0, rightIndent=0,
        )
        p = Para(text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"), style)
        pw, ph = p.wrapOn(c, text_w, H)
        check_page(ph + 3)
        # Draw bullet dot
        c.setFillColorRGB(*DARK)
        c.setFont("Helvetica", size)
        c.drawString(bullet_x, y - size * 0.8, "\u2022")
        p.drawOn(c, text_x, y - ph)
        y -= ph + 3

    def draw_skills(skills_dict):
        nonlocal y
        for category, value in skills_dict.items():
            check_page(0.2*inch)
            # Category label (bold)
            label = f"{category}: "
            c.setFont("Helvetica-Bold", 9)
            c.setFillColorRGB(*DARK)
            lw = c.stringWidth(label, "Helvetica-Bold", 9)
            c.drawString(ML, y, label)
            # Value (normal) — wrap if needed
            from reportlab.platypus import Paragraph as Para
            from reportlab.lib.styles import ParagraphStyle
            from reportlab.lib import colors as rlc
            style = ParagraphStyle(
                "sv", fontName="Helvetica", fontSize=9,
                leading=12, textColor=rlc.Color(*DARK),
                leftIndent=lw, firstLineIndent=-lw,
            )
            p = Para(
                (" " * 0 + value).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;"),
                style
            )
            pw, ph = p.wrapOn(c, CW, H)
            # Draw on same line
            c.setFont("Helvetica", 9)
            c.drawString(ML + lw, y, value[:int((CW - lw) / 5.2)])
            y -= 13

    def draw_job(exp, bullets, env):
        nonlocal y
        check_page(0.8*inch)
        # Job title | Company, Location | Dates
        title_str   = exp["title"]
        company_str = f"{exp['company']}, {exp['location']}  |  {exp['dates']}"

        c.setFont("Helvetica-Bold", 9.5)
        c.setFillColorRGB(*DARK)
        c.drawString(ML, y, title_str)
        tw = c.stringWidth(title_str, "Helvetica-Bold", 9.5)

        c.setFont("Helvetica", 9)
        c.setFillColorRGB(*GRAY)
        c.drawString(ML + tw + 5, y, "  |  " + company_str)
        y -= 13

        for bullet in bullets:
            draw_bullet(bullet)

        # Environment line
        check_page(0.2*inch)
        c.setFont("Helvetica-Oblique", 8)
        c.setFillColorRGB(*GRAY)
        # Wrap env
        env_label = "Environment: "
        lw = c.stringWidth(env_label, "Helvetica-BoldOblique", 8)
        c.setFont("Helvetica-BoldOblique", 8)
        c.drawString(ML, y, env_label)
        c.setFont("Helvetica-Oblique", 8)

        # Simple word wrap for env
        words = env.split(", ")
        line  = ""
        first = True
        for word in words:
            test = line + (", " if line else "") + word
            tw2  = c.stringWidth(test, "Helvetica-Oblique", 8)
            max_w = CW - (lw if first else 0)
            if tw2 > max_w and line:
                c.drawString(ML + (lw if first else 0), y, line)
                y -= 11
                line  = word
                first = False
            else:
                line = test
        if line:
            c.drawString(ML + (lw if first else 0), y, line)
        y -= 13

    # ── BUILD PDF ──────────────────────────────────────────────────────────

    # Merge enhanced data with master
    summary  = enhanced.get("summary", MASTER_RESUME["summary"])
    skills   = enhanced.get("skills",  MASTER_RESUME["skills"])
    exp      = MASTER_RESUME["experience"]
    bullets0 = enhanced.get("exp0_bullets", exp[0]["bullets"])
    bullets1 = enhanced.get("exp1_bullets", exp[1]["bullets"])
    bullets2 = enhanced.get("exp2_bullets", exp[2]["bullets"])
    env0     = enhanced.get("exp0_env", exp[0]["env"])
    env1     = enhanced.get("exp1_env", exp[1]["env"])
    env2     = enhanced.get("exp2_env", exp[2]["env"])
    edu      = MASTER_RESUME["education"]

    draw_name()
    draw_contact()

    # Summary
    draw_section_header("Professional Summary")
    draw_paragraph(summary, size=9, spacing_after=8)

    # Skills
    draw_section_header("Technical Skills")
    draw_skills(skills)
    y -= 4

    # Experience
    draw_section_header("Professional Experience")
    draw_job(exp[0], bullets0, env0)
    y -= 4
    draw_job(exp[1], bullets1, env1)
    y -= 4
    draw_job(exp[2], bullets2, env2)

    # Education
    draw_section_header("Education")
    c.setFont("Helvetica-Bold", 9.5)
    c.setFillColorRGB(*DARK)
    c.drawString(ML, y, edu["degree"])
    y -= 13
    c.setFont("Helvetica", 9)
    c.setFillColorRGB(*GRAY)
    c.drawString(ML, y,
        f"{edu['school']}, {edu['location']}  |  {edu['dates']}  |  GPA: {edu['gpa']}")
    y -= 13

    c.save()
    buf.seek(0)
    return buf.read()


# ── Main Entry Point ───────────────────────────────────────────────────────

def generate_ats_resume(job: dict, output_dir: str = "/tmp") -> dict:
    """
    Full pipeline:
    1. Claude enhances resume for this job (adds missing keywords)
    2. Generates ATS-optimized PDF
    Returns pdf_bytes and enhanced data.
    """
    print(f"  → Enhancing resume for: {job['title']} @ {job['company']}")
    enhanced = enhance_for_job(job)

    print(f"  → Generating ATS PDF...")
    pdf_bytes = generate_ats_pdf(enhanced)

    safe = "".join(c if c.isalnum() else "_" for c in job['company'])[:20]
    pdf_path = f"{output_dir}/Ram_Burri_{safe}.pdf"
    Path(pdf_path).write_bytes(pdf_bytes)

    print(f"  ✓ ATS PDF ready ({len(pdf_bytes):,} bytes)")
    return {
        "pdf_path":  pdf_path,
        "pdf_bytes": pdf_bytes,
        "enhanced":  enhanced,
    }


if __name__ == "__main__":
    # Quick test
    test_job = {
        "title": "Senior Full Stack .NET Developer",
        "company": "TestCorp",
        "description": (
            "Looking for Senior .NET developer with C#, ASP.NET Core, React, Angular, "
            "Azure, Microservices, SQL Server, Docker, Kubernetes, GraphQL, Redis, "
            "Blazor, SignalR, SOLID principles, CI/CD GitHub Actions experience."
        )
    }
    result = generate_ats_resume(test_job, "/tmp")
    print(f"PDF saved: {result['pdf_path']}")
