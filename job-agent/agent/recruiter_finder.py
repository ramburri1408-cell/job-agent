"""
Recruiter Finder V4 — Pipeline-Aligned Production Version

- Processes ONLY ai_ready jobs with ATS resume_pdf
- Uses Hunter.io to find + verify contacts
- Accepts valid, accept_all >= 75, risky >= 80
- Uses Anthropic, but does not over-reject engineers/devs/leads
- Stops safely on Hunter 429
"""

import os
import json
import re
import time
from pathlib import Path
from typing import Dict, List, Tuple

import requests
import anthropic

DATA_FILE = Path("data/jobs.json")

HUNTER_API_KEY = os.environ.get("HUNTER_API_KEY", "").strip()
ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "").strip()
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-opus-4-5-20251101").strip()

client_ai = anthropic.Anthropic(api_key=ANTHROPIC_KEY) if ANTHROPIC_KEY else None

MAX_SEARCHES_PER_RUN = int(os.environ.get("MAX_HUNTER_SEARCHES", "5"))

BAD_LOCAL_PARTS = {
    "noreply", "no-reply", "donotreply", "support", "info", "help",
    "privacy", "legal", "press", "admin", "abuse", "test", "unsubscribe",
    "feedback", "phishing", "spam", "security", "verification",
    "verifications", "compliance", "notifications", "alerts", "careers", "jobs",
}

COMMON_DOMAIN_FIXES = {
    "caciinternational.com": "caci.com",
    "eliassengroup.com": "eliassen.com",
    "judgegroup.com": "judge.com",
    "americanitsystems.com": "americanit.com",
    "russelltobinassociates.com": "russelltobin.com",
    "teksystemscoallegis.com": "teksystems.com",
    "simple.com": "simplesolutionsinc.com",
    "simplesolutions.com": "simplesolutionsinc.com",
    "stellar.com": "stellarprofessionals.com",
    "ssv.com": "ssvtechnologies.com",
    "emergere.com": "emergere-tech.com",
}


def load_jobs() -> Dict:
    return json.loads(DATA_FILE.read_text()) if DATA_FILE.exists() else {}


def save_jobs(jobs: Dict) -> None:
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    DATA_FILE.write_text(json.dumps(jobs, indent=2))


def clean_domain(domain: str) -> str:
    domain = (domain or "").lower().strip()
    domain = domain.replace("https://", "").replace("http://", "").replace("www.", "")
    domain = domain.split("/")[0].strip()
    return COMMON_DOMAIN_FIXES.get(domain, domain)


def company_to_domain(company: str) -> str:
    text = company.lower().strip()
    text = re.sub(
        r"\b(inc|llc|ltd|corp|corporation|co|company|technologies|technology|"
        r"tech|solutions|services|group|global|systems|consulting|staffing|"
        r"professionals|bank|na|the|international|associates)\b",
        "",
        text,
    )
    text = re.sub(r"[^a-z0-9\s]", "", text)
    text = re.sub(r"\s+", "", text)

    if not text:
        text = re.sub(r"[^a-z0-9]", "", company.lower())

    return clean_domain(f"{text}.com")


def domain_responds(domain: str) -> bool:
    if not domain:
        return False

    for scheme in ("https", "http"):
        try:
            res = requests.get(
                f"{scheme}://{domain}",
                timeout=5,
                allow_redirects=True,
                headers={"User-Agent": "Mozilla/5.0"},
            )
            if res.status_code < 500:
                return True
        except Exception:
            continue

    return False


def resolve_domain(company: str, job: Dict) -> str:
    existing = clean_domain(job.get("company_domain", ""))

    if existing and domain_responds(existing):
        return existing

    guessed = company_to_domain(company)

    if domain_responds(guessed):
        return guessed

    return guessed


def is_good_email(email: str) -> bool:
    if not email or "@" not in email or len(email) > 90:
        return False

    local = email.lower().strip().split("@")[0]

    if any(bad == local or bad in local for bad in BAD_LOCAL_PARTS):
        return False

    if local.upper() == local and len(local) > 5:
        return False

    return True


def is_hiring_related(title: str) -> bool:
    title = (title or "").lower()

    keywords = [
        "recruiter",
        "talent",
        "hr",
        "human resources",
        "staffing",
        "sourcer",
        "hiring",
        "recruiting",
        "manager",
        "lead",
        "director",
        "engineering",
        "engineer",
        "developer",
        "technical",
        "people",
    ]

    return any(keyword in title for keyword in keywords)


def looks_like_person_email(email: str) -> bool:
    local = email.split("@")[0].lower()
    return "." in local or "_" in local or len(local) >= 5


def is_contact_candidate(contact: Dict, email: str) -> bool:
    text = " ".join(
        [
            contact.get("position") or "",
            contact.get("department") or "",
            contact.get("seniority") or "",
        ]
    ).lower()

    if is_hiring_related(text):
        return True

    return looks_like_person_email(email)


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


def hunter_domain_search(domain: str) -> Tuple[List[Dict], bool]:
    if not HUNTER_API_KEY:
        print("  ! Missing HUNTER_API_KEY")
        return [], False

    try:
        res = requests.get(
            "https://api.hunter.io/v2/domain-search",
            params={
                "domain": domain,
                "api_key": HUNTER_API_KEY,
                "limit": 10,
            },
            timeout=25,
        )

        if res.status_code == 429:
            print("  ! Hunter rate limit 429 — stopping")
            return [], True

        if res.status_code >= 400:
            print(f"  ! Hunter domain error {res.status_code}: {res.text[:160]}")
            return [], False

        contacts = res.json().get("data", {}).get("emails", []) or []
        return contacts, False

    except Exception as exc:
        print(f"  ! Hunter domain exception: {str(exc)[:120]}")
        return [], False


def hunter_verify_email(email: str) -> Tuple[Dict, bool]:
    if not HUNTER_API_KEY:
        return {"status": "unknown", "score": 0, "acceptable": False}, False

    try:
        res = requests.get(
            "https://api.hunter.io/v2/email-verifier",
            params={
                "email": email,
                "api_key": HUNTER_API_KEY,
            },
            timeout=25,
        )

        if res.status_code == 429:
            return {"status": "rate_limited", "score": 0, "acceptable": False}, True

        if res.status_code >= 400:
            return {"status": "error", "score": 0, "acceptable": False}, False

        data = res.json().get("data", {})
        status = data.get("status", "")
        score = data.get("score") or 0

        return {
            "status": status,
            "score": score,
            "acceptable": is_hunter_acceptable(status, score),
        }, False

    except Exception:
        return {"status": "error", "score": 0, "acceptable": False}, False


def ai_validate_contact(name: str, title: str, email: str, company: str) -> bool:
    if not client_ai:
        return True

    try:
        res = client_ai.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=5,
            temperature=0,
            messages=[
                {
                    "role": "user",
                    "content": (
                        "Is this person useful for job outreach? "
                        "They can be recruiter, HR, talent, hiring manager, "
                        "engineering manager, technical lead, software engineer, "
                        "or developer who may refer candidates.\n\n"
                        f"Company: {company}\n"
                        f"Name: {name}\n"
                        f"Title: {title}\n"
                        f"Email: {email}\n\n"
                        "Answer YES or NO only."
                    ),
                }
            ],
        )

        return res.content[0].text.strip().lower().startswith("yes")

    except Exception as exc:
        print(f"  ! Anthropic validation skipped: {str(exc)[:120]}")
        return True


def find_recruiters_hunter(company: str, domain: str) -> Tuple[List[Dict], bool]:
    print("  → Hunter domain search...")

    contacts, rate_limited = hunter_domain_search(domain)

    if rate_limited:
        return [], True

    recruiters = []

    for contact in contacts:
        email = (contact.get("value") or "").lower().strip()

        if not is_good_email(email):
            continue

        if not is_contact_candidate(contact, email):
            continue

        first = contact.get("first_name") or ""
        last = contact.get("last_name") or ""
        name = f"{first} {last}".strip()
        title = contact.get("position") or "Technical Contact"

        print(f"  → Verifying {email}...")

        verify, verify_limited = hunter_verify_email(email)

        if verify_limited:
            print("  ! Hunter verify rate limit — stopping")
            return recruiters, True

        if not verify["acceptable"]:
            print(
                f"  ! Rejected by Hunter: {email} "
                f"status={verify['status']} score={verify['score']}"
            )
            continue

        ai_ok = ai_validate_contact(name, title, email, company)

        if not ai_ok and not is_hiring_related(title):
            print(f"  ! AI rejected: {email} — {title}")
            continue

        recruiters.append(
            {
                "name": name,
                "title": title,
                "email": email,
                "source": "hunter_ai",
                "verification_status": verify["status"],
                "verification_score": verify["score"],
            }
        )

        print(
            f"  ✓ Approved: {email} ({name or 'No Name'}) "
            f"status={verify['status']} score={verify['score']}"
        )

        if len(recruiters) >= 5:
            break

        time.sleep(0.5)

    seen = set()
    unique = []

    for recruiter in recruiters:
        if recruiter["email"] not in seen:
            seen.add(recruiter["email"])
            unique.append(recruiter)

    return unique, False


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
    searches_done = 0

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

    print(
        f"[Recruiter Finder] Processing {len(targets)} fresh AI-ready jobs "
        f"(max {MAX_SEARCHES_PER_RUN} Hunter searches)"
    )

    for jid, job in targets:
        if searches_done >= MAX_SEARCHES_PER_RUN:
            print(f"[Recruiter Finder] Reached max {MAX_SEARCHES_PER_RUN} searches — stopping")
            break

        company = (job.get("company") or "").strip()

        if not company:
            continue

        domain = resolve_domain(company, job)

        print(f"\n  [{company}] → {domain}")

        recruiters, rate_limited = find_recruiters_hunter(company, domain)
        searches_done += 1

        if rate_limited:
            print("[Recruiter Finder] Hunter rate limit hit — stopping")
            if recruiters:
                save_contacts(job, recruiters)
            else:
                mark_no_contact(job)
            updated += 1
            break

        if recruiters:
            save_contacts(job, recruiters)

            print(f"  → {len(recruiters)} verified contact(s) saved:")
            for recruiter in recruiters:
                label = f" ({recruiter['name']})" if recruiter.get("name") else ""
                print(f"     • {recruiter['email']}{label}")
        else:
            print("  ! No verified contacts found")
            mark_no_contact(job)

        updated += 1
        time.sleep(1)

    save_jobs(jobs)

    print(
        f"\n[Recruiter Finder] Done. {updated} jobs updated. "
        f"{searches_done} Hunter searches used."
    )
    return updated


if __name__ == "__main__":
    run_recruiter_finder()
