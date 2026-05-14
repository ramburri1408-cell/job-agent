"""
Recruiter Finder V3

Fixes:
- Processes ONLY fresh AI-ready jobs with ATS resume PDF
- Avoids old backlog jobs
- Uses Hunter.io for emails
- Accepts valid + accept_all score >= 75
- Uses Anthropic, but does NOT over-reject engineers/devs/leads
- Saves contacts only if usable
"""

import os
import json
import re
import time
from pathlib import Path
from typing import Dict, List

import requests
import anthropic

DATA_FILE = Path("data/jobs.json")

HUNTER_API_KEY = os.environ.get("HUNTER_API_KEY", "").strip()
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "").strip()
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-opus-4-5-20251101").strip()

client_ai = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY) if ANTHROPIC_API_KEY else None

MAX_JOBS_PER_RUN = int(os.environ.get("MAX_RECRUITER_JOBS_PER_RUN", "10"))

COMMON_DOMAIN_FIXES = {
    "caciinternational.com": "caci.com",
    "eliassengroup.com": "eliassen.com",
    "judgegroup.com": "judge.com",
    "americanitsystems.com": "americanit.com",
    "simple.com": "simplesolutionsinc.com",
    "simplesolutions.com": "simplesolutionsinc.com",
    "stellar.com": "stellarprofessionals.com",
    "ssv.com": "ssvtechnologies.com",
    "emergere.com": "emergere-tech.com",
    "russelltobinassociates.com": "russelltobin.com",
}

BAD_EMAIL_PREFIXES = {
    "noreply", "no-reply", "donotreply", "support", "info", "help",
    "privacy", "legal", "press", "admin", "abuse", "unsubscribe",
    "careers", "jobs"
}


def load_jobs() -> Dict:
    return json.loads(DATA_FILE.read_text()) if DATA_FILE.exists() else {}


def save_jobs(jobs: Dict) -> None:
    DATA_FILE.write_text(json.dumps(jobs, indent=2))


def clean_domain(domain: str) -> str:
    domain = (domain or "").lower().strip()
    domain = domain.replace("https://", "").replace("http://", "")
    domain = domain.replace("www.", "")
    domain = domain.split("/")[0]
    return COMMON_DOMAIN_FIXES.get(domain, domain)


def company_to_domain(company: str) -> str:
    text = company.lower().strip()
    text = re.sub(
        r"\b(inc|llc|ltd|corp|corporation|company|technologies|technology|"
        r"solutions|services|group|global|systems|consulting|staffing|"
        r"associates|international|the)\b",
        "",
        text,
    )
    text = re.sub(r"[^a-z0-9\s]", "", text)
    text = re.sub(r"\s+", "", text)

    if not text:
        text = re.sub(r"[^a-z0-9]", "", company.lower())

    return clean_domain(f"{text}.com")


def resolve_domain(company: str, job: Dict) -> str:
    existing = clean_domain(job.get("company_domain", ""))
    if existing:
        return existing
    return company_to_domain(company)


def is_good_email(email: str) -> bool:
    email = (email or "").lower().strip()

    if not email or "@" not in email:
        return False

    local = email.split("@")[0]

    if len(email) > 90:
        return False

    if any(local == bad or bad in local for bad in BAD_EMAIL_PREFIXES):
        return False

    return True


def is_hunter_acceptable(status: str, score: int) -> bool:
    status = (status or "").lower()
    score = score or 0

    if status == "valid":
        return True

    if status == "accept_all" and score >= 75:
        return True

    if status == "risky" and score >= 80:
        return True

    return False


def is_hiring_related(title: str) -> bool:
    title = (title or "").lower()

    keywords = [
        "recruiter",
        "talent",
        "hr",
        "human resources",
        "staffing",
        "sourcer",
        "manager",
        "lead",
        "director",
        "engineering",
        "engineer",
        "developer",
        "technical",
    ]

    return any(k in title for k in keywords)


def looks_like_person_email(email: str) -> bool:
    local = email.split("@")[0].lower()
    return "." in local or "_" in local or len(local) >= 5


def hunter_domain_search(domain: str) -> List[Dict]:
    if not HUNTER_API_KEY:
        print("  ! Missing HUNTER_API_KEY")
        return []

    url = "https://api.hunter.io/v2/domain-search"

    params = {
        "domain": domain,
        "api_key": HUNTER_API_KEY,
        "limit": 10,
    }

    try:
        res = requests.get(url, params=params, timeout=25)

        if res.status_code >= 400:
            print(f"  ! Hunter domain search error {res.status_code}: {res.text[:250]}")
            return []

        data = res.json().get("data", {})
        return data.get("emails", []) or []

    except Exception as exc:
        print(f"  ! Hunter domain search exception: {str(exc)[:120]}")
        return []


def hunter_verify_email(email: str) -> Dict:
    url = "https://api.hunter.io/v2/email-verifier"

    params = {
        "email": email,
        "api_key": HUNTER_API_KEY,
    }

    try:
        res = requests.get(url, params=params, timeout=25)

        if res.status_code >= 400:
            print(f"  ! Hunter verify error {res.status_code}: {res.text[:200]}")
            return {"status": "error", "score": 0, "acceptable": False}

        data = res.json().get("data", {})
        status = data.get("status", "")
        score = data.get("score") or 0

        return {
            "status": status,
            "score": score,
            "acceptable": is_hunter_acceptable(status, score),
        }

    except Exception as exc:
        print(f"  ! Hunter verify exception: {str(exc)[:120]}")
        return {"status": "error", "score": 0, "acceptable": False}


def ai_validate_contact(name: str, title: str, email: str, company: str) -> bool:
    if not client_ai:
        return True

    prompt = f"""
Validate this contact for job outreach.

Company: {company}
Name: {name or "Unknown"}
Title: {title or "Unknown"}
Email: {email}

Is this person likely related to recruiting, staffing, HR, talent acquisition,
engineering, software development, technical leadership, or hiring decisions?

Answer only YES or NO.
"""

    try:
        response = client_ai.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=5,
            temperature=0,
            messages=[{"role": "user", "content": prompt}],
        )

        answer = response.content[0].text.strip().lower()
        return answer.startswith("yes")

    except Exception as exc:
        print(f"  ! Anthropic validation skipped: {str(exc)[:120]}")
        return True


def dedupe_contacts(contacts: List[Dict]) -> List[Dict]:
    seen = set()
    clean = []

    for c in contacts:
        email = c.get("email", "").lower().strip()

        if not email or email in seen:
            continue

        seen.add(email)
        clean.append(c)

    return clean


def find_recruiters_hunter(company: str, domain: str) -> List[Dict]:
    print("  → Hunter domain search...")

    contacts = hunter_domain_search(domain)
    approved = []

    for contact in contacts:
        email = (contact.get("value") or "").lower().strip()

        if not is_good_email(email):
            continue

        first = contact.get("first_name") or ""
        last = contact.get("last_name") or ""
        name = f"{first} {last}".strip()
        title = contact.get("position") or "Technical Contact"

        if not is_hiring_related(title) and not looks_like_person_email(email):
            continue

        print(f"  → Verifying {email}...")

        verification = hunter_verify_email(email)

        if not verification["acceptable"]:
            print(
                f"  ! Rejected by Hunter: {email} "
                f"status={verification['status']} score={verification['score']}"
            )
            continue

        ai_ok = ai_validate_contact(name, title, email, company)

        if not ai_ok and not is_hiring_related(title):
            print(f"  ! Rejected by Anthropic: {email} — {title}")
            continue

        approved.append({
            "name": name,
            "title": title,
            "email": email,
            "source": "hunter_ai",
            "verification_status": verification["status"],
            "verification_score": verification["score"],
        })

        print(
            f"  ✓ Approved: {email} "
            f"status={verification['status']} score={verification['score']}"
        )

        if len(approved) >= 5:
            break

        time.sleep(0.5)

    return dedupe_contacts(approved)


def mark_no_contact(job: Dict) -> None:
    job["recruiters"] = []
    job["recruiter_email"] = ""
    job["recruiter_name"] = ""
    job["recruiter_source"] = "none"
    job["skip_email"] = True


def save_contacts(job: Dict, recruiters: List[Dict]) -> None:
    job["recruiters"] = recruiters
    job["recruiter_email"] = recruiters[0]["email"]
    job["recruiter_name"] = recruiters[0].get("name", "")
    job["recruiter_source"] = "hunter_ai"
    job["skip_email"] = False


def run_recruiter_finder() -> int:
    jobs = load_jobs()
    updated = 0

    targets = [
        (jid, job)
        for jid, job in jobs.items()
        if job.get("status") == "ai_ready"
        and job.get("resume_pdf")
        and (job.get("fit_score") or 0) >= 70
        and not job.get("email_sent")
        and job.get("recruiter_source") != "hunter_ai"
    ]

    if not targets:
        print("[Recruiter Finder] No fresh AI-ready jobs with ATS resumes to process")
        return 0

    print(f"[Recruiter Finder] Processing {len(targets)} fresh AI-ready jobs...")

    for jid, job in targets[:MAX_JOBS_PER_RUN]:
        company = (job.get("company") or "").strip()

        if not company:
            continue

        domain = resolve_domain(company, job)

        print(f"\n  [{company}] → {domain}")

        recruiters = find_recruiters_hunter(company, domain)

        if not recruiters:
            print("  ! No verified recruiter found — skipping email")
            mark_no_contact(job)
        else:
            save_contacts(job, recruiters)

            print(f"  → {len(recruiters)} verified contact(s) saved:")
            for r in recruiters:
                label = f" ({r['name']})" if r.get("name") else ""
                print(f"     • {r['email']}{label}")

        updated += 1
        time.sleep(1)

    save_jobs(jobs)

    print(f"\n[Recruiter Finder] Done. {updated} jobs updated.")
    return updated


if __name__ == "__main__":
    run_recruiter_finder()
