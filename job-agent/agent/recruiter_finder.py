"""
Recruiter Finder - Hunter.io + Anthropic Fixed Version

Fixes:
- Hunter plan limit error by using limit=10
- Retries Hunter pagination_error safely
- Adds known domain corrections
- Uses Hunter verifier
- Uses Anthropic validation
- Skips email if no verified recruiter is found
"""

import os
import json
import re
import time
from pathlib import Path

import requests
import anthropic

DATA_FILE = Path("data/jobs.json")

HUNTER_API_KEY = os.environ.get("HUNTER_API_KEY", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-opus-4-20250514")

client_ai = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY) if ANTHROPIC_API_KEY else None

RECRUITER_KEYWORDS = [
    "recruiter",
    "technical recruiter",
    "engineering recruiter",
    "talent acquisition",
    "talent partner",
    "talent sourcer",
    "sourcer",
    "human resources",
    "people operations",
    "staffing",
    "hiring",
    "recruiting",
]

SKIP_EMAIL_LOCAL_PARTS = {
    "noreply", "no-reply", "donotreply", "do-not-reply",
    "support", "info", "help", "privacy", "legal", "press",
    "admin", "abuse", "example", "test", "unsubscribe",
    "feedback", "news", "phishing", "spam", "security",
    "verification", "verifications", "compliance",
    "notifications", "alerts", "employment.compliance",
    "employee.verifications",
    "careers", "jobs",
}

COMMON_DOMAIN_FIXES = {
    "caciinternational.com": "caci.com",
    "judgegroup.com": "judge.com",
    "motionrecruitment.com": "motionrecruitment.com",
    "eliassengroup.com": "eliassen.com",
    "americanitsystems.com": "americanit.com",
    "intellixsoftware.com": "intellixsoftware.com",
}


def load_jobs():
    if not DATA_FILE.exists():
        return {}
    return json.loads(DATA_FILE.read_text())


def save_jobs(jobs):
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    DATA_FILE.write_text(json.dumps(jobs, indent=2))


def clean_domain(domain: str) -> str:
    domain = (domain or "").lower().strip()
    domain = domain.replace("https://", "").replace("http://", "")
    domain = domain.replace("www.", "")
    domain = domain.split("/")[0].strip()
    return COMMON_DOMAIN_FIXES.get(domain, domain)


def company_to_domain(company: str) -> str:
    original = company.strip()
    text = company.lower().strip()

    text = re.sub(
        r"\b(inc|llc|ltd|corp|corporation|co|company|technologies|technology|"
        r"tech|solutions|services|group|global|systems|consulting|staffing|"
        r"professionals|bank|na|the|international)\b",
        "",
        text,
    )

    text = re.sub(r"[^a-z0-9\s]", "", text)
    text = re.sub(r"\s+", "", text)

    if not text:
        text = re.sub(r"[^a-z0-9]", "", original.lower())

    domain = f"{text}.com"
    return clean_domain(domain)


def is_good_email(email: str) -> bool:
    if not email or "@" not in email:
        return False

    email = email.strip().lower()
    local = email.split("@")[0]

    if len(email) > 90:
        return False

    if any(skip in local for skip in SKIP_EMAIL_LOCAL_PARTS):
        return False

    return True


def is_recruiter_contact(contact: dict) -> bool:
    position = (contact.get("position") or "").lower()
    department = (contact.get("department") or "").lower()
    seniority = (contact.get("seniority") or "").lower()

    text = f"{position} {department} {seniority}"
    return any(keyword in text for keyword in RECRUITER_KEYWORDS)


def hunter_domain_search(domain: str) -> list:
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

        if res.status_code == 400:
            try:
                data = res.json()
                errors = data.get("errors", [])
                if any(e.get("id") == "pagination_error" for e in errors):
                    print("  ! Hunter plan allows max 10 results — retrying with limit=10")
                    params["limit"] = 10
                    res = requests.get(url, params=params, timeout=25)
                else:
                    print(f"  ! Hunter domain search error 400: {res.text[:250]}")
                    return []
            except Exception:
                print(f"  ! Hunter domain search error 400: {res.text[:250]}")
                return []

        if res.status_code >= 400:
            print(f"  ! Hunter domain search error {res.status_code}: {res.text[:250]}")
            return []

        data = res.json().get("data", {})
        return data.get("emails", []) or []

    except Exception as e:
        print(f"  ! Hunter domain search exception: {str(e)[:100]}")
        return []


def hunter_verify_email(email: str) -> dict:
    if not HUNTER_API_KEY:
        return {"verified": False, "status": "missing_key", "score": 0}

    url = "https://api.hunter.io/v2/email-verifier"

    params = {
        "email": email,
        "api_key": HUNTER_API_KEY,
    }

    try:
        res = requests.get(url, params=params, timeout=25)

        if res.status_code >= 400:
            print(f"  ! Hunter verify error {res.status_code}: {res.text[:200]}")
            return {"verified": False, "status": "error", "score": 0}

        data = res.json().get("data", {})
        status = data.get("status", "")
        score = data.get("score") or 0

        verified = status == "valid" or score >= 85

        return {
            "verified": verified,
            "status": status,
            "score": score,
        }

    except Exception as e:
        print(f"  ! Hunter verify exception: {str(e)[:100]}")
        return {"verified": False, "status": "error", "score": 0}


def ai_validate_recruiter(name: str, title: str, email: str, company: str) -> bool:
    if not client_ai:
        return True

    if not email:
        return False

    prompt = f"""
You are validating a recruiter contact for job outreach.

Company: {company}
Name: {name}
Title: {title}
Email: {email}

Is this person likely involved in hiring, recruiting, talent acquisition,
HR, staffing, sourcing, people operations, or engineering hiring?

Answer ONLY YES or NO.
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

    except Exception as e:
        print(f"  ! Anthropic validation skipped: {str(e)[:100]}")
        return True


def dedupe_recruiters(recruiters: list) -> list:
    seen = set()
    clean = []

    for recruiter in recruiters:
        email = recruiter.get("email", "").lower().strip()

        if not email or email in seen:
            continue

        seen.add(email)
        clean.append(recruiter)

    return clean


def find_recruiters_hunter(company: str, domain: str) -> list:
    print("  → Hunter domain search...")

    contacts = hunter_domain_search(domain)
    recruiters = []

    for contact in contacts:
        email = (contact.get("value") or "").lower().strip()

        if not is_good_email(email):
            continue

        if not is_recruiter_contact(contact):
            continue

        first = contact.get("first_name") or ""
        last = contact.get("last_name") or ""
        name = f"{first} {last}".strip()
        title = contact.get("position") or "Recruiter"

        print(f"  → Verifying {email}...")

        verification = hunter_verify_email(email)

        if not verification["verified"]:
            print(
                f"  ! Rejected by Hunter: {email} "
                f"status={verification['status']} score={verification['score']}"
            )
            continue

        if not ai_validate_recruiter(name, title, email, company):
            print(f"  ! Rejected by Anthropic: {email} — {title}")
            continue

        recruiters.append({
            "name": name,
            "title": title,
            "email": email,
            "source": "hunter_ai",
            "verification_status": verification["status"],
            "verification_score": verification["score"],
        })

        print(
            f"  ✓ Approved: {email} "
            f"({name or 'No Name'}) score={verification['score']}"
        )

        if len(recruiters) >= 5:
            break

        time.sleep(0.5)

    return dedupe_recruiters(recruiters)


def run_recruiter_finder():
    jobs = load_jobs()
    updated = 0

    targets = [
        (jid, job)
        for jid, job in jobs.items()
        if (job.get("fit_score") or 0) >= 80
        and not job.get("email_sent")
    ]

    if not targets:
        print("[Recruiter Finder] No new jobs to process")
        return 0

    print(f"[Recruiter Finder] Processing {len(targets)} jobs...")

    for jid, job in targets[:15]:
        company = job.get("company", "").strip()

        if not company:
            continue

        domain = clean_domain(job.get("company_domain") or company_to_domain(company))

        print(f"\n  [{company}] → {domain}")

        recruiters = find_recruiters_hunter(company, domain)

        if not recruiters:
            print("  ! No verified recruiter found — skipping email")
            jobs[jid]["recruiters"] = []
            jobs[jid]["recruiter_email"] = ""
            jobs[jid]["recruiter_name"] = ""
            jobs[jid]["recruiter_source"] = "none"
            jobs[jid]["skip_email"] = True
        else:
            jobs[jid]["recruiters"] = recruiters
            jobs[jid]["recruiter_email"] = recruiters[0]["email"]
            jobs[jid]["recruiter_name"] = recruiters[0].get("name", "")
            jobs[jid]["recruiter_source"] = "hunter_ai"
            jobs[jid]["skip_email"] = False

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
