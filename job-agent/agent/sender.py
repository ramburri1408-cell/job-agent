"""
Email Sender — sends recruiter emails via Gmail SMTP.
Attaches ATS-optimized PDF resume (pure Python, no LibreOffice).
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

GMAIL_USER = os.environ["GMAIL_USER"]
GMAIL_PASS = os.environ["GMAIL_APP_PASSWORD"]

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

def parse_draft(draft):
    lines   = draft.strip().splitlines()
    subject = "Following up on an opportunity"
    body_lines = lines
    for i, line in enumerate(lines):
        if line.lower().startswith("subject:"):
            subject    = line[len("subject:"):].strip()
            body_lines = lines[i + 1:]
            break
    return subject, "\n".join(body_lines).strip()

def send_email(to_email, to_name, subject, body, pdf_bytes=None, job_title=""):
    msg = MIMEMultipart("mixed")
    msg["From"]    = GMAIL_USER
    msg["To"]      = f"{to_name} <{to_email}>" if to_name else to_email
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    if pdf_bytes:
        part = MIMEBase("application", "pdf")
        part.set_payload(pdf_bytes)
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", 'attachment; filename="Ram_Burri_Resume.pdf"')
        msg.attach(part)
        print(f"  → PDF attached ({len(pdf_bytes):,} bytes)")

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_USER, GMAIL_PASS)
        server.sendmail(GMAIL_USER, to_email, msg.as_string())

    return True

def run_sender():
    jobs       = load_jobs()
    sent_count = 0

    for jid, job in jobs.items():
        if job.get("status") != "ai_ready":
            continue
        if job.get("email_sent"):
            continue

        to_email = job.get("recruiter_email", "").strip()
        if not to_email:
            print(f"  ✗ No recruiter email for {job['title']} @ {job['company']}")
            jobs[jid]["status"] = "no_email"
            save_jobs(jobs)
            continue

        draft         = job.get("email_draft", "")
        subject, body = parse_draft(draft)
        to_name       = job.get("recruiter_name", "")

        # Get PDF bytes from stored path
        pdf_bytes = None
        pdf_path  = job.get("resume_pdf")
        if pdf_path and Path(pdf_path).exists():
            pdf_bytes = Path(pdf_path).read_bytes()
        else:
            # Regenerate PDF if path missing
            try:
                from ats_resume import generate_ats_pdf
                enhanced  = json.loads(job.get("tailored_resume", "{}"))
                pdf_bytes = generate_ats_pdf(enhanced)
            except Exception as e:
                print(f"  ! PDF regeneration failed: {e}")

        print(f"\n[Sender] → {to_email} | {job['title']} @ {job['company']}")
        print(f"  Subject: {subject}")

        try:
            send_email(
                to_email  = to_email,
                to_name   = to_name,
                subject   = subject,
                body      = body,
                pdf_bytes = pdf_bytes,
                job_title = job["title"],
            )
            jobs[jid]["email_sent"]    = True
            jobs[jid]["email_sent_at"] = now_iso()
            jobs[jid]["status"]        = "applied"
            save_jobs(jobs)
            sent_count += 1
            print(f"  ✓ Sent!")

            log_email({
                "job_id":   jid,
                "title":    job["title"],
                "company":  job["company"],
                "to":       to_email,
                "subject":  subject,
                "sent_at":  now_iso(),
                "success":  True,
            })

        except Exception as e:
            print(f"  ✗ Failed: {e}")
            jobs[jid]["status"]      = "email_failed"
            jobs[jid]["email_error"] = str(e)
            save_jobs(jobs)
            log_email({
                "job_id":  jid,
                "title":   job["title"],
                "company": job["company"],
                "to":      to_email,
                "sent_at": now_iso(),
                "success": False,
                "error":   str(e),
            })

        time.sleep(3)

    print(f"\n[Sender] Done. {sent_count} emails sent.")
    return sent_count

if __name__ == "__main__":
    run_sender()
