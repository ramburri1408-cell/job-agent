"""
Email Sender — Sends personalized cold emails to ALL recruiters found
for each high-score job. Uses ATS resume PDF as attachment.
"""

import os, json, smtplib, time
from pathlib import Path
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from datetime import datetime, timezone
import anthropic

client    = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
DATA_FILE = Path("data/jobs.json")
LOG_FILE  = Path("data/email_log.jsonl")

GMAIL_USER     = os.environ.get("GMAIL_USER", "")
GMAIL_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "")


def load_jobs():
    return json.loads(DATA_FILE.read_text()) if DATA_FILE.exists() else {}

def save_jobs(jobs):
    DATA_FILE.write_text(json.dumps(jobs, indent=2))

def log_email(entry):
    LOG_FILE.parent.mkdir(exist_ok=True)
    with LOG_FILE.open("a") as f:
        f.write(json.dumps(entry) + "\n")

def now_iso():
    return datetime.now(timezone.utc).isoformat()


def draft_email(job: dict, recruiter_name: str) -> tuple[str, str]:
    """Use Claude Haiku to draft personalized subject + body."""
    greeting = f"Hi {recruiter_name.split()[0]}," if recruiter_name else "Hi,"

    result = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=300,
        system=(
            "Write a short cold email from Ram Burri applying for a job. "
            "3 sentences max. Professional, confident, specific to the role. "
            "Return ONLY JSON: {\"subject\": \"...\", \"body\": \"...\"}"
        ),
        messages=[{"role": "user", "content": (
            f"Job: {job['title']} at {job['company']}\n"
            f"Score: {job.get('fit_score', 80)}/100\n"
            f"Angle: {job.get('fit_angle', 'Strong .NET full-stack developer')}\n"
            f"Greeting: {greeting}"
        )}]
    ).content[0].text.strip()

    try:
        start = result.find("{")
        end   = result.rfind("}") + 1
        data  = json.loads(result[start:end])
        return data.get("subject", f"Full Stack .NET Developer — {job['title']}"), \
               data.get("body", "")
    except Exception:
        return (
            f"Full Stack .NET Developer — {job['title']}",
            f"{greeting}\n\nI'm a Full Stack .NET Developer with 4+ years of enterprise experience and would love to discuss the {job['title']} role at {job['company']}.\n\nBest,\nRam Burri\nRam.burri1408@gmail.com | 9544454339"
        )


def send_email(to: str, subject: str, body: str, pdf_bytes: bytes = None, pdf_name: str = "Ram_Burri_Resume.pdf") -> bool:
    """Send email via Gmail SMTP."""
    try:
        msg = MIMEMultipart()
        msg["From"]    = GMAIL_USER
        msg["To"]      = to
        msg["Subject"] = subject

        # Full email body with signature
        full_body = f"""{body}

--
Ram Burri
Full Stack .NET Developer | 4+ Years Enterprise Experience
Email: Ram.burri1408@gmail.com | Ph: 9544454339
Stack: .NET 8 · ASP.NET Core · React · Angular · Azure · SQL Server
Oracle Cloud Infrastructure 2025 Certified"""

        msg.attach(MIMEText(full_body, "plain"))

        # Attach PDF resume
        if pdf_bytes:
            pdf_part = MIMEApplication(pdf_bytes, _subtype="pdf")
            pdf_part.add_header("Content-Disposition", "attachment", filename=pdf_name)
            msg.attach(pdf_part)

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_USER, GMAIL_PASSWORD)
            server.send_message(msg)

        return True

    except Exception as e:
        print(f"  ! Send error: {str(e)[:80]}")
        return False


def run_sender():
    """
    Send emails to ALL recruiters found for each high-score job.
    If multiple recruiters found, emails all of them.
    """
    if not GMAIL_USER or not GMAIL_PASSWORD:
        print("[Sender] Gmail credentials not set")
        return 0

    jobs      = load_jobs()
    sent      = 0
    max_run   = 20  # Max emails per run

    for jid, job in jobs.items():
        if sent >= max_run:
            break

        # Skip if already emailed
        if job.get("email_sent"):
            continue

        # Only email high-score jobs
        if (job.get("fit_score") or 0) < 80:
            continue

        # Get all recruiters found
        recruiters = job.get("recruiters", [])

        # Fall back to single recruiter_email if no list
        if not recruiters and job.get("recruiter_email"):
            recruiters = [{
                "name":  job.get("recruiter_name", ""),
                "email": job["recruiter_email"],
            }]

        if not recruiters:
            print(f"  ! No recruiter email for: {job['title']} @ {job['company']}")
            continue

        # Get PDF resume
        pdf_bytes = None
        pdf_name  = "Ram_Burri_Resume.pdf"
        pdf_path  = job.get("resume_pdf")
        if pdf_path and Path(pdf_path).exists():
            pdf_bytes = Path(pdf_path).read_bytes()
            safe      = "".join(c if c.isalnum() else "_" for c in job.get("company", ""))[:20]
            pdf_name  = f"Ram_Burri_{safe}_Resume.pdf"

        # Get email draft — use job's stored draft or generate new one
        email_draft = job.get("email_draft", "")

        # Send to each recruiter found
        job_sent = False
        for recruiter in recruiters[:6]:  # Max 6 per company
            to_email = recruiter.get("email", "")
            name     = recruiter.get("name", "")

            if not to_email or "@" not in to_email:
                continue

            # Draft personalized email
            subject, body = draft_email(job, name)

            print(f"\n[Sender] → {to_email} | {job['title']} @ {job['company']}")
            if name:
                print(f"         Recruiter: {name}")
            print(f"         Subject: {subject}")

            success = send_email(to_email, subject, body, pdf_bytes, pdf_name)

            if success:
                print(f"  ✓ Sent!")
                sent += 1
                job_sent = True
                log_email({
                    "job_id":   jid,
                    "title":    job["title"],
                    "company":  job["company"],
                    "to":       to_email,
                    "name":     name,
                    "subject":  subject,
                    "success":  True,
                    "sent_at":  now_iso(),
                })
                time.sleep(2)  # Avoid Gmail rate limits
            else:
                log_email({
                    "job_id":  jid,
                    "title":   job["title"],
                    "company": job["company"],
                    "to":      to_email,
                    "success": False,
                    "sent_at": now_iso(),
                })

        # Mark job as emailed if at least one email sent
        if job_sent:
            jobs[jid]["email_sent"]    = True
            jobs[jid]["email_sent_at"] = now_iso()
            jobs[jid]["status"]        = "applied"

    save_jobs(jobs)
    print(f"\n[Sender] Done. {sent} emails sent.")
    return sent


if __name__ == "__main__":
    run_sender()
