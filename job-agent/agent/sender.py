"""
Cold Email Sender V2

Fixes:
- Sends only hunter_ai verified contacts
- Skips old unverified jobs silently
- Limits sends per run
- Adds delay between sends
- Avoids generic inboxes
"""

import json
import os
import random
import smtplib
import ssl
import time
from email.message import EmailMessage
from pathlib import Path
from typing import Dict, List

DATA_FILE = Path("data/jobs.json")

GMAIL_USER = os.environ.get("GMAIL_USER", "").strip()
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "").strip()

MAX_EMAILS_PER_RUN = int(os.environ.get("MAX_EMAILS_PER_RUN", "5"))
EMAIL_MIN_DELAY_SECONDS = int(os.environ.get("EMAIL_MIN_DELAY_SECONDS", "60"))

BAD_EMAIL_PREFIXES = (
    "careers@",
    "jobs@",
    "info@",
    "support@",
    "noreply@",
    "no-reply@",
    "admin@",
    "hr@",
)

SUBJECT_VARIANTS = [
    "{title} - Ram Burri",
    "Regarding {title}",
    "Application for {title}",
    "{title} opportunity",
    "Interested in {title}",
]


def load_jobs() -> Dict:
    if not DATA_FILE.exists():
        return {}
    return json.loads(DATA_FILE.read_text())


def save_jobs(jobs: Dict) -> None:
    DATA_FILE.write_text(json.dumps(jobs, indent=2))


def is_sendable_email(email: str) -> bool:
    email = (email or "").lower().strip()

    if not email or "@" not in email:
        return False

    if any(email.startswith(prefix) for prefix in BAD_EMAIL_PREFIXES):
        return False

    return True


def get_recipients(job: Dict) -> List[Dict]:
    recruiters = job.get("recruiters") or []
    result = []

    for recruiter in recruiters:
        email = (recruiter.get("email") or "").lower().strip()

        if not is_sendable_email(email):
            continue

        if recruiter.get("source") != "hunter_ai":
            continue

        result.append(recruiter)

    return result


def build_subject(job: Dict, recruiter: Dict) -> str:
    title = job.get("title") or ".NET Developer"

    if len(title) > 60:
        title = title[:57] + "..."

    return random.choice(SUBJECT_VARIANTS).format(title=title)


def build_body(job: Dict, recruiter: Dict) -> str:
    name = recruiter.get("name") or ""
    first_name = name.split()[0] if name else "there"

    title = job.get("title") or "the role"
    company = job.get("company") or "your team"

    return f"""Hi {first_name},

I came across the {title} role at {company} and wanted to reach out directly.

I’m a .NET full-stack developer with experience in C#, ASP.NET Core, REST APIs, SQL Server, Azure, React, Angular, and secure enterprise application development.

My background includes building scalable backend services, modern frontend applications, and cloud-ready systems with a focus on reliability, security, and clean API design.

I would appreciate the chance to be considered for this role. I’ve attached my resume for reference.

Best regards,
Ram Burri
ram.burri1408@gmail.com
"""


def get_resume_path(job: Dict) -> str:
    return (
        job.get("ats_pdf")
        or job.get("resume_pdf")
        or job.get("resume_path")
        or ""
    )


def attach_resume(msg: EmailMessage, resume_path: str) -> None:
    if not resume_path:
        return

    path = Path(resume_path)

    if not path.exists():
        print(f"  ! Resume not found: {resume_path}")
        return

    msg.add_attachment(
        path.read_bytes(),
        maintype="application",
        subtype="pdf",
        filename=path.name,
    )


def send_email(to_email: str, subject: str, body: str, resume_path: str = "") -> None:
    if not GMAIL_USER or not GMAIL_APP_PASSWORD:
        raise RuntimeError("Missing GMAIL_USER or GMAIL_APP_PASSWORD")

    msg = EmailMessage()
    msg["From"] = GMAIL_USER
    msg["To"] = to_email
    msg["Subject"] = subject
    msg["Reply-To"] = GMAIL_USER
    msg.set_content(body)

    attach_resume(msg, resume_path)

    context = ssl.create_default_context()

    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
        server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        server.send_message(msg)


def mark_sent(job: Dict, email: str) -> None:
    sent = job.get("emails_sent_to") or []

    if email not in sent:
        sent.append(email)

    job["emails_sent_to"] = sent
    job["email_sent"] = True


def run_sender() -> int:
    jobs = load_jobs()
    sent_count = 0

    for jid, job in jobs.items():
        if sent_count >= MAX_EMAILS_PER_RUN:
            print(f"[Sender] Reached max emails per run: {MAX_EMAILS_PER_RUN}")
            break

        if job.get("email_sent"):
            continue

        if job.get("skip_email"):
            continue

        if job.get("recruiter_source") != "hunter_ai":
            continue

        recipients = get_recipients(job)

        if not recipients:
            continue

        resume_path = get_resume_path(job)

        for recruiter in recipients:
            if sent_count >= MAX_EMAILS_PER_RUN:
                break

            email = recruiter["email"]

            if email in (job.get("emails_sent_to") or []):
                continue

            subject = build_subject(job, recruiter)
            body = build_body(job, recruiter)

            print(f"[Sender] → {email} | {job.get('title')} @ {job.get('company')}")

            if recruiter.get("name"):
                print(f"         Recruiter: {recruiter['name']}")

            print(f"         Subject: {subject}")

            try:
                send_email(email, subject, body, resume_path)
                mark_sent(job, email)
                sent_count += 1
                save_jobs(jobs)
                print("  ✓ Sent!")

                time.sleep(EMAIL_MIN_DELAY_SECONDS)

            except Exception as exc:
                print(f"  ✗ Send failed: {email} — {str(exc)[:120]}")

    save_jobs(jobs)
    print(f"[Sender] Done. {sent_count} emails sent.")
    return sent_count


if __name__ == "__main__":
    run_sender()
