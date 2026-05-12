"""
Cold Email Sender - Production Guardrails

Fixes:
- Sends only Hunter + AI verified recruiter contacts.
- Skips jobs with skip_email=True.
- Avoids generic/fallback inboxes.
- Adds throttling to reduce spam risk.
- Marks per-recipient sends.
"""

import json
import os
import smtplib
import ssl
import time
from email.message import EmailMessage
from pathlib import Path
from typing import Dict, List

DATA_FILE = Path("data/jobs.json")

GMAIL_USER = os.environ.get("GMAIL_USER", "").strip()
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "").strip()

MIN_DELAY_SECONDS = int(os.environ.get("EMAIL_MIN_DELAY_SECONDS", "45"))
MAX_EMAILS_PER_RUN = int(os.environ.get("MAX_EMAILS_PER_RUN", "10"))

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

    clean = []

    for recruiter in recruiters:
        email = (recruiter.get("email") or "").lower().strip()

        if not is_sendable_email(email):
            continue

        if recruiter.get("source") != "hunter_ai":
            continue

        clean.append(recruiter)

    return clean


def build_subject(job: Dict, recruiter: Dict) -> str:
    title = job.get("title") or ".NET Developer"
    company = job.get("company") or "your team"

    if len(title) > 65:
        title = title[:62] + "..."

    return f"{title} - Ram Burri"


def build_body(job: Dict, recruiter: Dict) -> str:
    name = recruiter.get("name") or ""
    first_name = name.split()[0] if name else "Hi"

    title = job.get("title") or "the role"
    company = job.get("company") or "your team"

    return f"""Hi {first_name},

I came across the {title} position at {company} and wanted to reach out directly.

I’m a .NET full-stack developer with experience in C#, ASP.NET Core, REST APIs, SQL Server, Azure, React, Angular, and secure enterprise application development. My background includes building scalable backend services, modern frontend applications, and cloud-ready solutions.

I’d be grateful if you could take a quick look at my profile for this role. I’ve attached my resume for reference.

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


def attach_resume(msg: EmailMessage, path: str) -> None:
    if not path:
        return

    resume_path = Path(path)

    if not resume_path.exists():
        print(f"  ! Resume not found: {path}")
        return

    data = resume_path.read_bytes()

    msg.add_attachment(
        data,
        maintype="application",
        subtype="pdf",
        filename=resume_path.name,
    )


def send_email(to_email: str, subject: str, body: str, attachment_path: str = "") -> None:
    if not GMAIL_USER or not GMAIL_APP_PASSWORD:
        raise RuntimeError("Missing GMAIL_USER or GMAIL_APP_PASSWORD")

    msg = EmailMessage()
    msg["From"] = GMAIL_USER
    msg["To"] = to_email
    msg["Subject"] = subject
    msg["Reply-To"] = GMAIL_USER
    msg.set_content(body)

    attach_resume(msg, attachment_path)

    context = ssl.create_default_context()

    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
        server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        server.send_message(msg)


def mark_sent(job: Dict, email: str) -> None:
    sent = job.get("emails_sent_to") or []

    if email not in sent:
        sent.append(email)

    job["emails_sent_to"] = sent

    # Mark job email_sent only after at least one real recruiter email.
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
            print(
                f"  ! Skipping: no verified recruiter contact for "
                f"{job.get('title')} @ {job.get('company')}"
            )
            continue

        if job.get("recruiter_source") != "hunter_ai":
            print(
                f"  ! Skipping unverified contact for: "
                f"{job.get('title')} @ {job.get('company')}"
            )
            continue

        recipients = get_recipients(job)

        if not recipients:
            print(
                f"  ! No verified recruiter email for: "
                f"{job.get('title')} @ {job.get('company')}"
            )
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

            print(
                f"[Sender] → {email} | "
                f"{job.get('title')} @ {job.get('company')}"
            )
            if recruiter.get("name"):
                print(f"         Recruiter: {recruiter['name']}")
            print(f"         Subject: {subject}")

            try:
                send_email(email, subject, body, resume_path)
                mark_sent(job, email)
                sent_count += 1
                print("  ✓ Sent!")

                save_jobs(jobs)
                time.sleep(MIN_DELAY_SECONDS)

            except Exception as exc:
                print(f"  ✗ Send failed: {email} — {str(exc)[:120]}")

    save_jobs(jobs)
    print(f"[Sender] Done. {sent_count} emails sent.")
    return sent_count


if __name__ == "__main__":
    run_sender()
