"""
Sender V8 — Email Ram first, then recruiter
Flow:
1. For every ai_ready job:
   a. Send Ram alert email (job link + fit score + ATS resume attached)
   b. If verified recruiter email found → send cold email to recruiter (ATS resume attached)
"""

import json, os, smtplib, time
from pathlib import Path
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders

DATA_FILE   = Path("data/jobs.json")
CONFIG_FILE = Path("data/config.json")

RAM_EMAIL       = os.environ.get("GMAIL_USER", "janakiram.b1408@gmail.com")
GMAIL_USER      = os.environ.get("GMAIL_USER", "")
GMAIL_PASSWORD  = os.environ.get("GMAIL_APP_PASSWORD", "")
MAX_EMAILS      = 20
EMAIL_DELAY     = 5  # seconds between emails


def load_jobs():
    return json.loads(DATA_FILE.read_text(encoding="utf-8")) if DATA_FILE.exists() else {}

def save_jobs(jobs):
    DATA_FILE.write_text(json.dumps(jobs, indent=2), encoding="utf-8")

def load_config():
    return json.loads(CONFIG_FILE.read_text(encoding="utf-8")) if CONFIG_FILE.exists() else {}


def get_smtp():
    server = smtplib.SMTP("smtp.gmail.com", 587)
    server.starttls()
    server.login(GMAIL_USER, GMAIL_PASSWORD)
    return server


def send_email(server, to_email, subject, body, attachment_path=None):
    msg = MIMEMultipart()
    msg["From"]    = GMAIL_USER
    msg["To"]      = to_email
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    # Attach ATS resume PDF if available
    if attachment_path and Path(attachment_path).exists():
        try:
            with open(attachment_path, "rb") as f:
                part = MIMEBase("application", "octet-stream")
                part.set_payload(f.read())
            encoders.encode_base64(part)
            filename = Path(attachment_path).name
            part.add_header("Content-Disposition", f"attachment; filename={filename}")
            msg.attach(part)
        except Exception as e:
            print(f"  ! Could not attach resume: {e}")

    server.sendmail(GMAIL_USER, to_email, msg.as_string())


def run_sender():
    jobs        = load_jobs()
    config      = load_config()
    profile     = config.get("profile", {})
    sent        = 0

    if not GMAIL_USER or not GMAIL_PASSWORD:
        print("[Sender] Missing Gmail credentials")
        return 0

    ready = [j for j in jobs.values() if j.get("status") == "ai_ready"]
    print(f"[Sender] {len(ready)} jobs ready to send")

    if not ready:
        print("[Sender] Done. 0 emails sent.")
        return 0

    try:
        server = get_smtp()
    except Exception as e:
        print(f"[Sender] SMTP connection failed: {e}")
        return 0

    for jid, job in [(j["id"], j) for j in ready]:
        if sent >= MAX_EMAILS:
            print(f"[Sender] Reached max {MAX_EMAILS} emails. Stopping.")
            break

        resume_path = job.get("resume_pdf", "")
        score       = job.get("fit_score", 0)
        company     = job.get("company", "")
        title       = job.get("title", "")

        # ── FLOW 1: Always email Ram ────────────────────────────────────────
        try:
            subject = job.get("ram_email_subject") or f"Job Match {score}/100: {title} @ {company}"
            body    = job.get("ram_email_body") or build_ram_body(job)

            send_email(server, RAM_EMAIL, subject, body, resume_path)
            print(f"  [Ram Alert] Sent: {title} @ {company} ({score}/100)")
            sent += 1
            time.sleep(EMAIL_DELAY)
        except Exception as e:
            print(f"  ! Ram email failed: {e}")
            jobs[jid]["status"] = "email_failed"
            save_jobs(jobs)
            continue

        # ── FLOW 2: Email recruiter if found ────────────────────────────────
        recruiter_email = job.get("recruiter_email", "").strip()
        recruiter_name  = job.get("recruiter_name", "Hiring Manager")
        email_draft     = job.get("email_draft", "")

        if recruiter_email and "@" in recruiter_email and recruiter_email != "careers@company.com":
            if sent < MAX_EMAILS:
                try:
                    # Parse subject from email draft
                    lines = email_draft.strip().split("\n")
                    if lines and lines[0].lower().startswith("subject:"):
                        rec_subject = lines[0][8:].strip()
                        rec_body    = "\n".join(lines[2:]).strip()
                    else:
                        rec_subject = f"Re: {title} position at {company}"
                        rec_body    = email_draft

                    send_email(server, recruiter_email, rec_subject, rec_body, resume_path)
                    print(f"  [Recruiter] Sent to {recruiter_name} <{recruiter_email}>")
                    sent += 1
                    time.sleep(EMAIL_DELAY)
                    jobs[jid]["recruiter_email_sent"] = True
                except Exception as e:
                    print(f"  ! Recruiter email failed: {e}")
        else:
            print(f"  [Recruiter] No verified email found for {company}")

        jobs[jid]["status"]       = "applied"
        jobs[jid]["email_sent"]   = True
        jobs[jid]["email_sent_at"] = __import__("datetime").datetime.utcnow().isoformat()
        save_jobs(jobs)

    try:
        server.quit()
    except Exception:
        pass

    print(f"\n[Sender] Done. {sent} emails sent.")
    return sent


def build_ram_body(job):
    """Fallback body builder if ram_email_body not pre-built."""
    score      = job.get("fit_score", 0)
    analysis   = job.get("fit_analysis", {})
    matched    = ", ".join(analysis.get("matched_skills", []))
    gaps       = ", ".join(analysis.get("gaps", []))
    angle      = analysis.get("angle", "")
    rec_name   = job.get("recruiter_name", "Not found")
    rec_email  = job.get("recruiter_email", "Not found")

    return (
        f"New job match!\n\n"
        f"POSITION : {job.get('title')}\n"
        f"COMPANY  : {job.get('company')}\n"
        f"LOCATION : {job.get('location')}\n"
        f"SALARY   : {job.get('salary', 'Not listed')}\n"
        f"SOURCE   : {job.get('portal')}\n\n"
        f"APPLY HERE: {job.get('url')}\n\n"
        f"FIT SCORE     : {score}/100\n"
        f"WHY YOU FIT   : {angle}\n"
        f"MATCHED SKILLS: {matched}\n"
        f"GAPS          : {gaps}\n\n"
        f"RECRUITER      : {rec_name}\n"
        f"RECRUITER EMAIL: {rec_email}\n\n"
        f"ATS RESUME: Attached as PDF\n\n"
        f"JOB DESCRIPTION:\n{job.get('description', '')[:2000]}"
    )


if __name__ == "__main__":
    run_sender()
