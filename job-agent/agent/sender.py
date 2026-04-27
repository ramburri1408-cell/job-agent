"""
Email Sender — sends recruiter emails via Gmail SMTP.
Uses Gmail App Password (no OAuth needed).
Auto-attaches tailored resume as PDF if weasyprint is available.
"""

import json, os, smtplib, time
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from pathlib import Path

DATA_FILE = Path("data/jobs.json")
LOG_FILE  = Path("data/email_log.jsonl")

GMAIL_USER = os.environ["GMAIL_USER"]        # your.email@gmail.com
GMAIL_PASS = os.environ["GMAIL_APP_PASSWORD"] # 16-char app password

def load_jobs() -> dict:
    return json.loads(DATA_FILE.read_text()) if DATA_FILE.exists() else {}

def save_jobs(jobs: dict):
    DATA_FILE.write_text(json.dumps(jobs, indent=2))

def log_email(entry: dict):
    LOG_FILE.parent.mkdir(exist_ok=True)
    with LOG_FILE.open("a") as f:
        f.write(json.dumps(entry) + "\n")

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def parse_draft(draft: str) -> tuple[str, str]:
    """Split 'Subject: ...\n\nbody' into (subject, body)."""
    lines = draft.strip().splitlines()
    subject = "Following up on an opportunity"
    body_lines = lines

    for i, line in enumerate(lines):
        if line.lower().startswith("subject:"):
            subject = line[len("subject:"):].strip()
            body_lines = lines[i + 1:]
            break

    body = "\n".join(body_lines).strip()
    return subject, body

def resume_to_txt(resume_text: str) -> bytes:
    """Return resume as plain UTF-8 bytes (txt attachment)."""
    return resume_text.encode("utf-8")

def send_email(to_email: str, to_name: str, subject: str, body: str,
               resume_text: str | None = None, job_title: str = "") -> bool:
    """Send email via Gmail SMTP. Returns True on success."""
    msg = MIMEMultipart("mixed")
    msg["From"]    = GMAIL_USER
    msg["To"]      = f"{to_name} <{to_email}>" if to_name else to_email
    msg["Subject"] = subject

    msg.attach(MIMEText(body, "plain"))

    # Attach tailored resume as .txt
    if resume_text:
        part = MIMEBase("application", "octet-stream")
        part.set_payload(resume_to_txt(resume_text))
        encoders.encode_base64(part)
        safe_title = "".join(c if c.isalnum() or c in " -_" else "_" for c in job_title)[:40]
        part.add_header("Content-Disposition", f'attachment; filename="Resume_{safe_title}.txt"')
        msg.attach(part)

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_USER, GMAIL_PASS)
        server.sendmail(GMAIL_USER, to_email, msg.as_string())

    return True

def run_sender():
    jobs = load_jobs()
    sent_count = 0

    for jid, job in jobs.items():
        if job.get("status") != "ai_ready":
            continue
        if job.get("email_sent"):
            continue

        to_email = job.get("recruiter_email", "").strip()
        if not to_email:
            print(f"  ✗ No recruiter email for {job['title']} @ {job['company']}, skipping.")
            jobs[jid]["status"] = "no_email"
            save_jobs(jobs)
            continue

        draft   = job.get("email_draft", "")
        subject, body = parse_draft(draft)
        resume  = job.get("tailored_resume")
        to_name = job.get("recruiter_name", "")

        print(f"\n[Sender] Sending to {to_email} for {job['title']} @ {job['company']}")
        print(f"  Subject: {subject}")

        try:
            send_email(
                to_email  = to_email,
                to_name   = to_name,
                subject   = subject,
                body      = body,
                resume_text = resume,
                job_title = job["title"],
            )
            jobs[jid]["email_sent"]    = True
            jobs[jid]["email_sent_at"] = now_iso()
            jobs[jid]["status"]        = "applied"
            save_jobs(jobs)
            sent_count += 1
            print(f"  ✓ Sent!")

            log_email({
                "job_id": jid,
                "title": job["title"],
                "company": job["company"],
                "to": to_email,
                "subject": subject,
                "sent_at": now_iso(),
                "success": True,
            })

        except Exception as e:
            print(f"  ✗ Failed: {e}")
            jobs[jid]["status"] = "email_failed"
            jobs[jid]["email_error"] = str(e)
            save_jobs(jobs)
            log_email({
                "job_id": jid,
                "title": job["title"],
                "company": job["company"],
                "to": to_email,
                "sent_at": now_iso(),
                "success": False,
                "error": str(e),
            })

        time.sleep(3)  # be polite, avoid spam flags

    print(f"\n[Sender] Done. {sent_count} emails sent.")
    return sent_count

if __name__ == "__main__":
    run_sender()
