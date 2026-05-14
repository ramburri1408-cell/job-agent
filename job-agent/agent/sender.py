"""
Cold Email Sender V5
- Sends job alert to Ram with JD + link + ATS resume
- Sends cold outreach to Hunter verified recruiters
- Fixed: properly finds and attaches ATS resume PDF
"""

import json, os, random, smtplib, ssl, time
from email.message import EmailMessage
from pathlib import Path
from typing import Dict, List

DATA_FILE          = Path("data/jobs.json")
GMAIL_USER         = os.environ.get("GMAIL_USER", "").strip()
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "").strip()
RAM_EMAIL          = "Ram.burri1408@gmail.com"

MAX_EMAILS_PER_RUN      = int(os.environ.get("MAX_EMAILS_PER_RUN", "15"))
EMAIL_MIN_DELAY_SECONDS = int(os.environ.get("EMAIL_MIN_DELAY_SECONDS", "8"))

BAD_EMAIL_PREFIXES = (
    "careers@", "jobs@", "info@", "support@", "noreply@",
    "no-reply@", "admin@", "hr@", "phishing@", "verif@",
)

SUBJECT_VARIANTS = [
    "Application for {title} - Ram Burri",
    "{title} | .NET Full Stack Developer",
    "Regarding {title} at {company}",
    "{title} — Ram Burri, .NET Developer",
]


def load_jobs() -> Dict:
    return json.loads(DATA_FILE.read_text()) if DATA_FILE.exists() else {}

def save_jobs(jobs: Dict) -> None:
    DATA_FILE.write_text(json.dumps(jobs, indent=2))

def is_sendable_email(email: str) -> bool:
    email = (email or "").lower().strip()
    if not email or "@" not in email or len(email) > 90:
        return False
    if any(email.startswith(p) for p in BAD_EMAIL_PREFIXES):
        return False
    local = email.split("@")[0]
    if local.upper() == local and len(local) > 5:
        return False
    return True

def find_resume_pdf(job: Dict) -> str:
    """
    Find ATS resume PDF for this job.
    Checks multiple locations in order of preference.
    """
    # 1. Check stored path in job
    for key in ["resume_pdf", "ats_pdf", "resume_path"]:
        path = job.get(key, "")
        if path and Path(path).exists():
            print(f"  → Resume found: {path}")
            return str(path)

    # 2. Search /tmp for company-specific PDF
    company = job.get("company", "")
    company_safe = "".join(c if c.isalnum() else "_" for c in company)[:20]

    patterns = [
        f"Ram_Burri_{company_safe}*.pdf",
        f"Ram_Burri_*.pdf",
    ]

    for pattern in patterns:
        matches = sorted(
            Path("/tmp").glob(pattern),
            key=lambda p: p.stat().st_mtime,  # newest first
            reverse=True
        )
        if matches:
            print(f"  → Resume found in /tmp: {matches[0].name}")
            return str(matches[0])

    # 3. Try to regenerate from ai_engine
    try:
        print(f"  → Regenerating ATS resume for {job.get('title')} @ {company}...")
        from ats_resume import generate_ats_resume
        result = generate_ats_resume(job, "/tmp")
        pdf_path = result.get("pdf_path", "")
        if pdf_path and Path(pdf_path).exists():
            # Save path back to job
            job["resume_pdf"] = pdf_path
            print(f"  → Resume regenerated: {pdf_path}")
            return pdf_path
    except Exception as e:
        print(f"  ! Could not regenerate resume: {str(e)[:60]}")

    print(f"  ! No resume found for: {job.get('title')} @ {company}")
    return ""

def attach_resume(msg: EmailMessage, resume_path: str) -> bool:
    if not resume_path or not Path(resume_path).exists():
        return False
    try:
        data = Path(resume_path).read_bytes()
        msg.add_attachment(
            data,
            maintype="application",
            subtype="pdf",
            filename=Path(resume_path).name,
        )
        print(f"  ✓ Resume attached: {Path(resume_path).name}")
        return True
    except Exception as e:
        print(f"  ! Attach error: {str(e)[:80]}")
        return False

def send_via_gmail(to: str, subject: str, body: str, resume_path: str = "") -> None:
    if not GMAIL_USER or not GMAIL_APP_PASSWORD:
        raise RuntimeError("Missing Gmail credentials")
    msg             = EmailMessage()
    msg["From"]     = GMAIL_USER
    msg["To"]       = to
    msg["Subject"]  = subject
    msg["Reply-To"] = GMAIL_USER
    msg.set_content(body)
    attach_resume(msg, resume_path)
    ctx = ssl.create_default_context()
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ctx) as server:
        server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        server.send_message(msg)


# ── JOB ALERT TO RAM ────────────────────────────────────────────────────────

def send_job_alert_to_ram(job: Dict, resume_path: str) -> bool:
    """
    Email Ram the full job details with ATS resume attached.
    Includes: Title, Company, Score, Fit Angle, Description, Apply Link.
    """
    title    = job.get("title", "Unknown")
    company  = job.get("company", "Unknown")
    location = job.get("location", "Not specified")
    score    = job.get("fit_score", "N/A")
    angle    = job.get("fit_angle", "Strong match based on your profile")
    url      = job.get("url", "")
    desc     = (job.get("description") or "No description available")[:1500]

    subject = f"🎯 Job Match {score}/100: {title} @ {company}"

    body = f"""Hi Ram,

Here's a high-scoring job match for you to review and apply!

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📋 POSITION  : {title}
🏢 COMPANY   : {company}
📍 LOCATION  : {location}
⭐ FIT SCORE : {score}/100
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🔗 APPLY HERE:
{url}

📝 WHY YOU'RE A GOOD FIT:
{angle}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📄 JOB DESCRIPTION:
{desc}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Your ATS-tailored resume for this role is attached.

Good luck!
Job Agent Bot"""

    try:
        send_via_gmail(RAM_EMAIL, subject, body, resume_path)
        if resume_path:
            print(f"  ✓ Job alert sent to Ram with resume: {title} @ {company}")
        else:
            print(f"  ✓ Job alert sent to Ram (no resume): {title} @ {company}")
        return True
    except Exception as e:
        print(f"  ! Alert email failed: {str(e)[:80]}")
        return False


# ── COLD EMAIL TO RECRUITER ──────────────────────────────────────────────────

def get_recruiter_recipients(job: Dict) -> List[Dict]:
    recruiters = job.get("recruiters") or []
    return [
        r for r in recruiters
        if r.get("source") == "hunter_ai"
        and is_sendable_email(r.get("email", ""))
    ]

def build_recruiter_subject(job: Dict) -> str:
    title   = (job.get("title") or ".NET Developer")[:65]
    company = job.get("company") or ""
    return random.choice(SUBJECT_VARIANTS).format(title=title, company=company)

def build_recruiter_body(job: Dict, recruiter: Dict) -> str:
    name    = recruiter.get("name") or ""
    first   = name.split()[0] if name else "there"
    title   = job.get("title") or "the role"
    company = job.get("company") or "your team"
    desc    = (job.get("description") or "").lower()

    extra = ""
    if "azure"   in desc: extra = "I've worked extensively with Azure-based deployments, CI/CD pipelines, and cloud-ready .NET services.\n\n"
    elif "react"  in desc: extra = "I've built React-based frontend workflows and reusable component libraries connected to secure .NET APIs.\n\n"
    elif "angular" in desc: extra = "I've worked on Angular enterprise applications with .NET APIs, SQL Server, and secure authentication flows.\n\n"

    return f"""Hi {first},

I came across the {title} role at {company} and wanted to reach out directly.

{extra}I'm a .NET full-stack developer with experience in C#, ASP.NET Core, REST APIs, SQL Server, Azure, React, Angular, and secure enterprise application development.

I've attached an ATS-tailored resume generated specifically for this role.

Would you be open to a quick 10-15 minute conversation this week?

Best regards,
Ram Burri
Ram.burri1408@gmail.com | (954) 445-4339
linkedin.com/in/ramburri"""


# ── MAIN ────────────────────────────────────────────────────────────────────

def run_sender() -> int:
    jobs       = load_jobs()
    sent_count = 0

    for jid, job in jobs.items():
        if sent_count >= MAX_EMAILS_PER_RUN:
            print(f"[Sender] Reached max {MAX_EMAILS_PER_RUN} emails per run")
            break

        if job.get("email_sent"):
            continue
        if job.get("skip_email"):
            continue
        if (job.get("fit_score") or 0) < 80:
            continue

        emails_sent = job.get("emails_sent_to") or []

        # Find resume PDF
        resume_path = find_resume_pdf(job)

        # ── 1. Send job alert to Ram ──────────────────────────────────────
        if RAM_EMAIL not in emails_sent:
            print(f"\n[Sender] Job alert → Ram: {job.get('title')} @ {job.get('company')}")
            success = send_job_alert_to_ram(job, resume_path)
            if success:
                emails_sent.append(RAM_EMAIL)
                job["emails_sent_to"] = emails_sent
                job["ram_alerted"]    = True
                sent_count += 1
                save_jobs(jobs)
                time.sleep(EMAIL_MIN_DELAY_SECONDS)

        # ── 2. Send cold email to verified Hunter recruiters ──────────────
        recruiters = get_recruiter_recipients(job)
        for recruiter in recruiters:
            if sent_count >= MAX_EMAILS_PER_RUN:
                break

            email = recruiter["email"].lower().strip()
            if email in emails_sent:
                continue

            if not resume_path:
                print(f"  ! Skipping recruiter email — no resume found")
                continue

            subject = build_recruiter_subject(job)
            body    = build_recruiter_body(job, recruiter)

            print(f"\n[Sender] → {email} | {job.get('title')} @ {job.get('company')}")
            if recruiter.get("name"):
                print(f"         Recruiter: {recruiter['name']} [hunter_ai]")
            print(f"         Subject: {subject}")

            try:
                send_via_gmail(email, subject, body, resume_path)
                emails_sent.append(email)
                job["emails_sent_to"] = emails_sent
                job["email_sent"]     = True
                sent_count           += 1
                print("  ✓ Sent!")
                save_jobs(jobs)
                time.sleep(EMAIL_MIN_DELAY_SECONDS)
            except Exception as e:
                print(f"  ✗ Failed: {str(e)[:120]}")

        # Mark job fully processed
        job["email_sent"]     = True
        job["emails_sent_to"] = emails_sent
        save_jobs(jobs)

    save_jobs(jobs)
    print(f"\n[Sender] Done. {sent_count} emails sent.")
    return sent_count

if __name__ == "__main__":
    run_sender()
