"""
Recruiter Finder - Hunter.io + Anthropic Production Version

Flow:
1. Pick high-fit jobs that have not been emailed.
2. Resolve the best company domain.
3. Search Hunter.io domain emails.
4. Filter recruiter / HR / talent contacts.
5. Verify every email with Hunter.
6. Validate contact relevance using Anthropic.
7. Save only verified contacts.
8. Mark jobs with no verified contacts as skip_email=True.

Required env:
- HUNTER_API_KEY
- ANTHROPIC_API_KEY
- ANTHROPIC_MODEL=claude-opus-4-5-20251101
"""

import json
import os
import re
import time
from pathlib import Path
from typing import Dict, List, Optional

import anthropic
import requests

DATA_FILE = Path("data/jobs.json")

HUNTER_API_KEY = os.environ.get("HUNTER_API_KEY", "").strip()
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "").strip()
ANTHROPIC_MODEL = os.environ.get(
    "ANTHROPIC_MODEL",
    "claude-opus-4-5-20251101",
).strip()

client_ai = (
    anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    if ANTHROPIC_API_KEY
    else None
)

RECRUITER_KEYWORDS = {
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
}

BAD_LOCAL_PARTS = {
    "noreply",
    "no-reply",
    "donotreply",
    "do-not-reply",
    "support",
    "info",
    "help",
    "privacy",
    "legal",
    "press",
    "admin",
    "abuse",
    "example",
    "test",
    "unsubscribe",
    "feedback",
    "news",
    "phishing",
    "spam",
    "security",
    "verification",
    "verifications",
    "compliance",
    "notifications",
    "alerts",
    "careers",
    "jobs",
    "hr",
}

COMMON_DOMAIN_FIXES = {
    "caciinternational.com": "caci.com",
    "eliassengroup.com": "eliassen.com",
    "judgegroup.com": "judge.com",
    "americanitsystems.com": "americanit.com",
    "simplesolutions.com": "simplesolutionsinc.com",
    "simple.com": "simplesolutionsinc.com",
    "stellar.com": "stellarprofessionals.com",
    "ssv.com": "ssvtechnologies.com",
    "emergere.com": "emergere-tech.com",
}


def load_jobs() -> Dict:
    if not DATA_FILE.exists():
        return {}
    return json.loads(DATA_FILE.read_text())


def save_jobs(jobs: Dict) -> None:
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

    return clean_domain(f"{text}.com")


def domain_responds(domain: str) -> bool:
    for scheme in ("https", "http"):
        try:
            res = requests.get(
                f"{scheme}://{domain}",
                timeout=6,
                allow_redirects=True,
                headers={"User-Agent": "Mozilla/5.0"},
            )
            if res.status_code < 500:
                return True
        except requests.RequestException:
            continue
    return False


def resolve_domain(company: str, job: Dict) -> str:
    existing = clean_domain(job.get("company_domain", ""))
    if existing:
        fixed = clean_domain(existing)
        if domain_responds(fixed):
            return fixed

    guessed = company_to_domain(company)
    if domain_responds(guessed):
        return guessed

    compact_company = re.sub(r"[^a-z0-9]", "", company.lower())
    candidates = [
        clean_domain(f"{compact_company}.com"),
        clean_domain(f"{compact_company}inc.com"),
        clean_domain(f"{compact_company}llc.com"),
        guessed,
    ]

    for domain in candidates:
        if domain and domain_responds(domain):
            return domain

    return guessed


def is_good_email(email: str) -> bool:
    if not email or "@" not in email:
        return False

    email = email.strip().lower()
    local = email.split("@")[0]

    if len(email) > 90:
        return False

    if any(bad == local or bad in local for bad in BAD_LOCAL_PARTS):
        return False

    return True


def looks_like_person_email(email: str) -> bool:
    local = email.split("@")[0].lower()
    return "." in local or "_" in local or len(local) >= 5


def is_recruiter_contact(contact: Dict, email: str) -> bool:
    position = (contact.get("position") or "").lower()
    department = (contact.get("department") or "").lower()
    seniority = (contact.get("seniority") or "").lower()

    text = f"{position} {department} {seniority}"

    if any(keyword in text for keyword in RECRUITER_KEYWORDS):
        return True

    # Relaxed fallback: Hunter sometimes misses titles/departments.
    return looks_like_person_email(email)


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

    except requests.RequestException as exc:
        print(f"  ! Hunter domain search exception: {str(exc)[:100]}")
        return []


def hunter_verify_email(email: str) -> Dict:
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

        return {
            "verified": status == "valid" or score >= 85,
            "status": status,
            "score": score,
        }

    except requests.RequestException as exc:
        print(f"  ! Hunter verify exception: {str(exc)[:100]}")
        return {"verified": False, "status": "error", "score": 0}


def ai_validate_recruiter(name: str, title: str, email: str, company: str) -> bool:
    if not client_ai:
        return True

    prompt = f"""
Validate this contact for job outreach.

Company: {company}
Name: {name or "Unknown"}
Title: {title or "Unknown"}
Email: {email}

Question:
Is this person likely related to recruiting, talent acquisition, staffing,
HR, sourcing, people operations, or technical hiring?

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
        # Do not block verified Hunter emails if AI temporarily fails.
        return True


def dedupe_recruiters(recruiters: List[Dict]) -> List[Dict]:
    seen = set()
    result = []

    for recruiter in recruiters:
        email = recruiter.get("email", "").lower().strip()
        if not email or email in seen:
            continue
        seen.add(email)
        result.append(recruiter)

    return result


def find_recruiters_hunter(company: str, domain: str) -> List[Dict]:
    print("  → Hunter domain search...")

    contacts = hunter_domain_search(domain)
    recruiters = []

    for contact in contacts:
        email = (contact.get("value") or "").lower().strip()

        if not is_good_email(email):
            continue

        if not is_recruiter_contact(contact, email):
            continue

        first = contact.get("first_name") or ""
        last = contact.get("last_name") or ""
        name = f"{first} {last}".strip()
        title = contact.get("position") or "Recruiting Contact"

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

        recruiters.append(
            {
                "name": name,
                "title": title,
                "email": email,
                "source": "hunter_ai",
                "verification_status": verification["status"],
                "verification_score": verification["score"],
            }
        )

        print(
            f"  ✓ Approved: {email} "
            f"({name or 'No Name'}) score={verification['score']}"
        )

        if len(recruiters) >= 5:
            break

        time.sleep(0.5)

    return dedupe_recruiters(recruiters)


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
        if (job.get("fit_score") or 0) >= 80
        and not job.get("email_sent")
    ]

    if not targets:
        print("[Recruiter Finder] No new jobs to process")
        return 0

    print(f"[Recruiter Finder] Processing {len(targets)} jobs...")

    for jid, job in targets[:15]:
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
            for recruiter in recruiters:
                label = f" ({recruiter['name']})" if recruiter.get("name") else ""
                print(f"     • {recruiter['email']}{label}")

        updated += 1
        time.sleep(1)

    save_jobs(jobs)

    print(f"\n[Recruiter Finder] Done. {updated} jobs updated.")
    return updated


if __name__ == "__main__":
    run_recruiter_finder()
