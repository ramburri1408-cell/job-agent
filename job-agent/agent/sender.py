"""
Cold Email Sender V6 — Production Ready

Two independent flows:

FLOW 1 — RAM ALERT (always runs):
  Sends Ram a complete job alert email containing:
  - Job title, company, location, fit score
  - Why he's a good fit (AI angle)
  - Apply link
  - Recruiter contacts:
      * Hunter subscription active → verified contacts only
      * Hunter limit hit / no subscription → all contacts found (Ram verifies manually)
  - ATS resume attached

FLOW 2 — RECRUITER COLD EMAIL (autonomous, unchanged):
  Sends cold outreach to Hunter verified contacts only.
  Runs independently of Flow 1.
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

RECRUITER_SUBJECT_VARIANTS = [
    "Application for {title} - Ram Burri",
    "{title} | .NET Full Stack Developer",
    "Regarding {title} at {company}",
    "{title} — Ram Burri, .NET Developer",
]


# ── UTILITIES ────────────────────────────────────────────────────────────────

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
    """Find ATS resume — checks stored path, /tmp, then regenerates."""
    for key in ["resume_pdf", "ats_pdf", "resume_path"]:
        path = job.get(key, "")
        if path and Path(path).exists():
            return str(path)

    company_safe = "".join(
        c if c.isalnum() else "_" for c in job.get("company", "")
    )[:20]

    for pattern in [f"Ram_Burri_{company_safe}*.pdf", "Ram_Burri_*.pdf"]:
        matches = sorted(
            Path("/tmp").glob(pattern),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if matches:
            return str(matches[0])

    # Regenerate if not found
    try:
        from ats_resume import generate_ats_resume
        result   = generate_ats_resume(job, "/tmp")
        pdf_path = result.get("pdf_path", "")
        if pdf_path and Path(pdf_path).exists():
            job["resume_pdf"] = pdf_path
            return pdf_path
    except Exception as e:
        print(f"  ! Resume regeneration failed: {str(e)[:60]}")

    return ""

def attach_resume(msg: EmailMessage, resume_path: str) -> bool:
    if not resume_path or not Path(resume_path).exists():
        return False
    try:
        msg.add_attachment(
            Path(resume_path).read_bytes(),
            maintype="application",
            subtype="pdf",
            filename=Path(resume_path).name,
        )
        print(f"  ✓ Resume attached: {Path(resume_path).name}")
        return True
    except Exception as e:
        print(f"  ! Attach error: {str(e)[:60]}")
        return False

def send_via_gmail(
    to: str, subject: str, body: str, resume_path: str = ""
) -> None:
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


# ── FLOW 1: RAM ALERT ────────────────────────────────────────────────────────

def format_recruiter_section(job: Dict) -> str:
    """
    Format recruiter contacts for Ram's alert email.

    - Hunter subscription active → show only verified contacts (source=hunter_ai)
    - Hunter limit hit / no subscription → show all contacts found (Ram verifies manually)
    """
    all_recruiters      = job.get("recruiters") or []
    verified_recruiters = [
        r for r in all_recruiters if r.get("source") == "hunter_ai"
    ]
    hunter_active       = len(verified_recruiters) > 0

    # Decide which list to show
    if hunter_active:
        contacts_to_show = verified_recruiters
        section_title    = "👥 RECRUITER CONTACTS (Hunter.io Verified)"
        note             = "These contacts have been verified by Hunter.io."
    elif all_recruiters:
        contacts_to_show = all_recruiters
        section_title    = "👥 RECRUITER CONTACTS (Unverified — Please Verify Manually)"
        note             = (
            "Hunter.io subscription limit reached. "
            "These contacts were found but not verified. "
            "Please review and reach out to the right person."
        )
    else:
        return (
            "👥 RECRUITER CONTACTS:\n"
            "   No contacts found for this company this run.\n"
            "   Try searching LinkedIn for HR/Talent Acquisition at this company."
        )

    lines = [f"{section_title}:", f"   ({note})", ""]

    for r in contacts_to_show:
        name   = r.get("name", "Unknown")
        email  = r.get("email", "")
        title  = r.get("title", "")
        score  = r.get("verification_score", "")
        status = r.get("verification_status", "")
        source = r.get("source", "")

        lines.append(f"   • Name  : {name}")
        if title:
            lines.append(f"     Title : {title}")
        lines.append(f"     Email : {email}")
        if score:
            lines.append(f"     Score : {score} | Status: {status}")
        lines.append("")

    return "\n".join(lines)

def send_job_alert_to_ram(job: Dict, resume_path: str) -> bool:
    """
    Send Ram a complete job alert email with all info needed to apply.
    """
    title    = job.get("title", "Unknown")
    company  = job.get("company", "Unknown")
    location = job.get("location", "Not specified")
    score    = job.get("fit_score", "N/A")
    angle    = job.get("fit_angle", "Strong match based on your profile")
    url      = job.get("url", "No link available")
    desc     = (job.get("description") or "No description available")[:2000]
    contacts = format_recruiter_section(job)
    resume_note = (
        f"✅ ATS resume tailored for this role is attached — {Path(resume_path).name}"
        if resume_path
        else "⚠️ Resume not found — re-run pipeline to regenerate"
    )

    subject = f"🎯 Job Match {score}/100: {title} @ {company}"

    body = f"""Hi Ram,

Here's a high-scoring job match for you to review and apply!

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📋 POSITION  : {title}
🏢 COMPANY   : {company}
📍 LOCATION  : {location}
⭐ FIT SCORE : {score}/100
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🔗 APPLY HERE:
{url}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📝 WHY YOU'RE A GOOD FIT:
{angle}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{contacts}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📄 JOB DESCRIPTION:
{desc}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📎 RESUME: {resume_note}

Good luck!
Job Agent Bot"""

    try:
        send_via_gmail(RAM_EMAIL, subject, body, resume_path)
        print(f"  ✓ Job alert sent to Ram: {title} @ {company}")
        return True
    except Exception as e:
        print(f"  ! Ram alert failed: {str(e)[:80]}")
        return False


# ── FLOW 2: AUTONOMOUS COLD EMAIL TO RECRUITERS ──────────────────────────────

def get_verified_recruiters(job: Dict) -> List[Dict]:
    """Only Hunter.io verified contacts for autonomous outreach."""
    return [
        r for r in (job.get("recruiters") or [])
        if r.get("source") == "hunter_ai"
        and is_sendable_email(r.get("email", ""))
    ]

def build_recruiter_subject(job: Dict) -> str:
    title   = (job.get("title") or ".NET Developer")[:65]
    company = job.get("company") or ""
    return random.choice(RECRUITER_SUBJECT_VARIANTS).format(
        title=title, company=company
    )

def build_recruiter_body(job: Dict, recruiter: Dict) -> str:
    name    = recruiter.get("name") or ""
    first   = name.split()[0] if name else "there"
    title   = job.get("title") or "the role"
    company = job.get("company") or "your team"
    desc    = (job.get("description") or "").lower()

    extra = ""
    if "azure"    in desc:
        extra = (
            "I've worked extensively with Azure-based deployments, "
            "CI/CD pipelines, and cloud-ready .NET services.\n\n"
        )
    elif "react"  in desc:
        extra = (
            "I've built React-based frontend workflows and reusable "
            "component libraries connected to secure .NET APIs.\n\n"
        )
    elif "angular" in desc:
        extra = (
            "I've worked on Angular enterprise applications with .NET APIs, "
            "SQL Server, and secure authentication flows.\n\n"
        )

    return f"""Hi {first},

I came across the {title} role at {company} and wanted to reach out directly.

{extra}I'm a .NET full-stack developer with experience in C#, ASP.NET Core, REST APIs, SQL Server, Azure, React, Angular, and secure enterprise application development.

I've attached an ATS-tailored resume generated specifically for this role.

Would you be open to a quick 10-15 minute conversation this week?

Best regards,
Ram Burri
Ram.burri1408@gmail.com | (954) 445-4339
linkedin.com/in/ramburri"""

def send_recruiter_cold_email(
    job: Dict, recruiter: Dict, resume_path: str
) -> bool:
    """Send autonomous cold email to a single verified recruiter."""
    email   = recruiter["email"].lower().strip()
    subject = build_recruiter_subject(job)
    body    = build_recruiter_body(job, recruiter)

    print(f"\n[Sender] Recruiter → {email} | {job.get('title')} @ {job.get('company')}")
    if recruiter.get("name"):
        print(f"         Name: {recruiter['name']} [{recruiter.get('title', '')}]")
    print(f"         Subject: {subject}")

    try:
        send_via_gmail(email, subject, body, resume_path)
        print("  ✓ Sent!")
        return True
    except Exception as e:
        print(f"  ✗ Failed: {str(e)[:120]}")
        return False


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

        if (job.get("fit_score") or 0) < 80:
            continue

        emails_sent = job.get("emails_sent_to") or []
        resume_path = find_resume_pdf(job)

        # ── FLOW 1: Send job alert to Ram ────────────────────────────────
        if RAM_EMAIL not in emails_sent:
            print(
                f"\n[Sender] Ram alert → "
                f"{job.get('title')} @ {job.get('company')}"
            )
            success = send_job_alert_to_ram(job, resume_path)
            if success:
                emails_sent.append(RAM_EMAIL)
                job["emails_sent_to"] = emails_sent
                job["ram_alerted"]    = True
                sent_count           += 1
                save_jobs(jobs)
                time.sleep(EMAIL_MIN_DELAY_SECONDS)

        # ── FLOW 2: Autonomous cold email to verified recruiters ──────────
        verified = get_verified_recruiters(job)
        for recruiter in verified:
            if sent_count >= MAX_EMAILS_PER_RUN:
                break

            email = recruiter["email"].lower().strip()
            if email in emails_sent:
                continue
            if not resume_path:
                print(f"  ! No resume — skipping recruiter cold email")
                continue

            success = send_recruiter_cold_email(job, recruiter, resume_path)
            if success:
                emails_sent.append(email)
                job["emails_sent_to"] = emails_sent
                job["email_sent"]     = True
                sent_count           += 1
                save_jobs(jobs)
                time.sleep(EMAIL_MIN_DELAY_SECONDS)

        # Mark job as fully processed
        job["email_sent"]     = True
        job["emails_sent_to"] = emails_sent
        save_jobs(jobs)

    save_jobs(jobs)
    print(f"\n[Sender] Done. {sent_count} emails sent.")
    return sent_count


if __name__ == "__main__":
    run_sender()
