"""
Cold Email Sender V3

Sends only verified recruiter contacts and attaches the ATS resume PDF
created specifically for that job.

Uses:
- job["resume_pdf"] from ai_engine.py
- job["recruiters"] from recruiter_finder.py
- source must be hunter_ai
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
EMAIL_MIN_DELAY_SECONDS = int(os.environ.get("EMAIL_MIN_DELAY_SECONDS", "90"))


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
    "Application for {title} - Ram Burri",
    "{title} | .NET Full Stack Developer",
    "Regarding {title} at {company}",
    "{title} opportunity",
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


def get_resume_path(job: Dict) -> str:
    """
    Uses the ATS PDF created for this exact job.
    ai_engine.py stores this in job["resume_pdf"].
    """

    path = (
        job.get("resume_pdf")
        or job.get("ats_pdf")
        or job.get("resume_path")
        or ""
    )

    if not path:
        print("  ! No ATS resume path found for this job")
        return ""

    resume_path = Path(path)

    if not resume_path.exists():
        print(f"  ! ATS resume file missing: {path}")
        return ""

    return str(resume_path)


def attach_resume(msg: EmailMessage, resume_path: str) -> bool:
    if not resume_path:
        return False

    path = Path(resume_path)

    if not path.exists():
        print(f"  ! Resume not found: {resume_path}")
        return False

    try:
        msg.add_attachment(
            path.read_bytes(),
            maintype="application",
            subtype="pdf",
            filename=path.name,
        )
        print(f"  ✓ Attached ATS resume: {path.name}")
        return True

    except Exception as exc:
        print(f"  ! Failed to attach resume: {str(exc)[:120]}")
        return False


def build_subject(job: Dict, recruiter: Dict) -> str:
    title = job.get("title") or ".NET Developer"
    company = job.get("company") or ""

    if len(title) > 65:
        title = title[:62] + "..."

    return random.choice(SUBJECT_VARIANTS).format(
        title=title,
        company=company,
    )


def build_body(job: Dict, recruiter: Dict) -> str:
    name = recruiter.get("name") or ""
    first = name.split()[0] if name else "there"

    title = job.get("title") or "the role"
    company = job.get("company") or "your team"
    description = (job.get("description") or "").lower()

    extra = ""

    if "azure" in description:
        extra = (
            "I’ve also worked with Azure-based deployments, CI/CD pipelines, "
            "and cloud-ready .NET services.\n\n"
        )
    elif "react" in description:
        extra = (
            "I’ve built React-based frontend workflows and reusable component "
            "libraries connected to secure backend APIs.\n\n"
        )
    elif "angular" in description:
        extra = (
            "I’ve worked on Angular-based enterprise applications with .NET APIs, "
            "SQL Server, and secure authentication flows.\n\n"
        )

    return f"""Hi {first},

I came across the {title} role at {company} and wanted to reach out directly.

{extra}I’m a .NET full-stack developer with experience in C#, ASP.NET Core, REST APIs, SQL Server, Azure, React, Angular, and secure enterprise application development.

I’ve attached an ATS-tailored resume generated specifically for this role.

Would you be open to a quick 10–15 minute conversation this week?

Best regards,
Ram Burri
ram.burri1408@gmail.com
"""


def send_email(
    to_email: str,
    subject: str,
    body: str,
    resume_path: str,
) -> None:
    if not GMAIL_USER or not GMAIL_APP_PASSWORD:
        raise RuntimeError("Missing GMAIL_USER or GMAIL_APP_PASSWORD")

    msg = EmailMessage()
    msg["From"] = GMAIL_USER
    msg["To"] = to_email
    msg["Subject"] = subject
    msg["Reply-To"] = GMAIL_USER
    msg.set_content(body)

    attached = attach_resume(msg, resume_path)

    if not attached:
        raise RuntimeError("ATS resume attachment failed")

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
    job["email_sent_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


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

        if not resume_path:
            print(
                f"  ! Skipping: ATS resume missing for "
                f"{job.get('title')} @ {job.get('company')}"
            )
            continue

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
            print(f"         Resume: {resume_path}")

            try:
                send_email(email, subject, body, resume_path)
                mark_sent(job, email)
                sent_count += 1
                save_jobs(jobs)

                print("  ✓ Sent with ATS resume attached!")

                time.sleep(EMAIL_MIN_DELAY_SECONDS)

            except Exception as exc:
                print(f"  ✗ Send failed: {email} — {str(exc)[:160]}")

    save_jobs(jobs)
    print(f"[Sender] Done. {sent_count} emails sent.")
    return sent_count


if __name__ == "__main__":
    run_sender()
