"""
Cold Email Sender - Production Version
- Sends only to Hunter verified contacts (hunter_ai)
- Falls back to Google-found named recruiters if Hunter finds nothing
- Skips generic/system emails
- 8s delay between sends, max 20 per run
"""

import json, os, smtplib, ssl, time
from email.message import EmailMessage
from pathlib import Path
from typing import Dict, List

DATA_FILE = Path("data/jobs.json")

GMAIL_USER         = os.environ.get("GMAIL_USER", "").strip()
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "").strip()
MIN_DELAY_SECONDS  = int(os.environ.get("EMAIL_MIN_DELAY_SECONDS", "8"))
MAX_EMAILS_PER_RUN = int(os.environ.get("MAX_EMAILS_PER_RUN", "20"))

BAD_EMAIL_PREFIXES = (
    "noreply@", "no-reply@", "donotreply@", "do-not-reply@",
    "support@", "admin@", "abuse@", "phishing@", "spam@",
    "info@", "help@", "press@", "legal@", "privacy@",
    "verif@", "verifications@", "compliance@",
    "notifications@", "alerts@", "careers@", "jobs@", "hr@",
)

BAD_EMAIL_KEYWORDS = (
    "verif", "phish", "noreply", "donotreply",
    "compliance", "notification", "alert", "employment",
)


def load_jobs() -> Dict:
    if not DATA_FILE.exists():
        return {}
    return json.loads(DATA_FILE.read_text())

def save_jobs(jobs: Dict) -> None:
    DATA_FILE.write_text(json.dumps(jobs, indent=2))

def is_sendable_email(email: str) -> bool:
    email = (email or "").lower().strip()
    if not email or "@" not in email or len(email) > 90:
        return False
    if any(email.startswith(p) for p in BAD_EMAIL_PREFIXES):
        return False
    local = email.split("@")[0]
    if any(k in local for k in BAD_EMAIL_KEYWORDS):
        return False
    # Block all-caps locals (system emails like HRSD.Employee)
    if local.upper() == local and len(local) > 5:
        return False
    return True

def get_recipients(job: Dict) -> List[Dict]:
    """
    Priority chain:
    1. Hunter.io verified contacts (best quality)
    2. Google LinkedIn named recruiters (good quality)
    3. Skip — no fallback to generic emails
    """
    recruiters = job.get("recruiters") or []

    # Priority 1: Hunter verified
    hunter = [
        r for r in recruiters
        if r.get("source") == "hunter_ai"
        and is_sendable_email(r.get("email", ""))
    ]
    if hunter:
        return hunter[:5]

    # Priority 2: Google-found with real name
    google = [
        r for r in recruiters
        if r.get("source") in ["linkedin_google", "google_email"]
        and is_sendable_email(r.get("email", ""))
        and r.get("name", "").strip()
    ]
    if google:
        return google[:5]

    return []

def build_subject(job: Dict) -> str:
    title = (job.get("title") or ".NET Developer")[:65]
    return f"{title} - Ram Burri"

def build_body(job: Dict, recruiter: Dict) -> str:
    name       = recruiter.get("name") or ""
    first_name = name.split()[0] if name else "Hi"
    title      = job.get("title") or "the role"
    company    = job.get("company") or "your team"
    angle      = job.get("fit_angle") or (
        "I'm a .NET full-stack developer with 4+ years of enterprise experience "
        "in C#, ASP.NET Core, React, Azure, and SQL Server."
    )

    return f"""Hi {first_name},

I came across the {title} position at {company} and wanted to reach out directly.

{angle}

I've attached my resume for your review and would love to connect if this could be a fit.

Best regards,
Ram Burri
Ram.burri1408@gmail.com | (954) 445-4339
linkedin.com/in/ramburri
"""

def get_resume_path(job: Dict) -> str:
    """Find resume PDF — checks job fields then /tmp."""
    for key in ["ats_pdf", "resume_pdf", "resume_path"]:
        path = job.get(key, "")
        if path and Path(path).exists():
            return path
    # Search /tmp for any Ram Burri PDF
    company_safe = "".join(
        c if c.isalnum() else "_"
        for c in job.get("company", "")
    )[:20]
    for pattern in [
        f"Ram_Burri_{company_safe}*.pdf",
        "Ram_Burri_*.pdf",
    ]:
        matches = list(Path("/tmp").glob(pattern))
        if matches:
            return str(matches[0])
    return ""

def send_email(to_email: str, subject: str, body: str, attachment_path: str = "") -> None:
    if not GMAIL_USER or not GMAIL_APP_PASSWORD:
        raise RuntimeError("Missing Gmail credentials")

    msg             = EmailMessage()
    msg["From"]     = GMAIL_USER
    msg["To"]       = to_email
    msg["Subject"]  = subject
    msg["Reply-To"] = GMAIL_USER
    msg.set_content(body)

    if attachment_path and Path(attachment_path).exists():
        data = Path(attachment_path).read_bytes()
        msg.add_attachment(
            data,
            maintype="application",
            subtype="pdf",
            filename=Path(attachment_path).name,
        )

    ctx = ssl.create_default_context()
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ctx) as server:
        server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        server.send_message(msg)

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

        recipients  = get_recipients(job)
        resume_path = get_resume_path(job)
        emails_sent = job.get("emails_sent_to") or []

        if not recipients:
            print(f"  ! No verified recruiter for: {job.get('title')} @ {job.get('company')}")
            continue

        for recruiter in recipients:
            if sent_count >= MAX_EMAILS_PER_RUN:
                break

            email = recruiter["email"].lower().strip()
            if email in emails_sent:
                continue

            subject = build_subject(job)
            body    = build_body(job, recruiter)
            source  = recruiter.get("source", "unknown")
            name    = recruiter.get("name", "")

            print(f"\n[Sender] → {email} | {job.get('title')} @ {job.get('company')}")
            if name:
                print(f"         Recruiter: {name} [{source}]")
            print(f"         Subject: {subject}")
            if resume_path:
                print(f"         Resume: {Path(resume_path).name}")

            try:
                send_email(email, subject, body, resume_path)
                emails_sent.append(email)
                job["emails_sent_to"] = emails_sent
                job["email_sent"]     = True
                sent_count           += 1
                print("  ✓ Sent!")
                save_jobs(jobs)
                time.sleep(MIN_DELAY_SECONDS)

            except Exception as exc:
                print(f"  ✗ Failed: {str(exc)[:120]}")

    save_jobs(jobs)
    print(f"\n[Sender] Done. {sent_count} emails sent.")
    return sent_count

if __name__ == "__main__":
    run_sender()
