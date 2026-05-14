"""
Recruiter Finder V3 — Production Ready

- Uses Hunter.io to find and verify recruiter contacts
- Stops immediately on 429 to save monthly credits
- Max 5 searches per run to preserve free tier (25/month)
- Saves all found contacts to jobs.json for Ram's alert email
"""

import os, json, re, time
from pathlib import Path
from typing import Dict, List, Tuple
import requests
import anthropic

DATA_FILE      = Path("data/jobs.json")
HUNTER_API_KEY = os.environ.get("HUNTER_API_KEY", "").strip()
ANTHROPIC_KEY  = os.environ.get("ANTHROPIC_API_KEY", "").strip()

client_ai = anthropic.Anthropic(api_key=ANTHROPIC_KEY) if ANTHROPIC_KEY else None

# Keep low to preserve Hunter free tier (25 searches/month)
MAX_SEARCHES_PER_RUN = int(os.environ.get("MAX_HUNTER_SEARCHES", "5"))

RECRUITER_KEYWORDS = {
    "recruiter", "technical recruiter", "engineering recruiter",
    "talent acquisition", "talent partner", "talent sourcer",
    "sourcer", "human resources", "people operations",
    "staffing", "hiring", "recruiting",
}

BAD_LOCAL_PARTS = {
    "noreply", "no-reply", "donotreply", "support", "info",
    "help", "privacy", "legal", "press", "admin", "abuse",
    "test", "unsubscribe", "feedback", "phishing", "spam",
    "security", "verification", "verifications", "compliance",
    "notifications", "alerts", "careers", "jobs",
}

COMMON_DOMAIN_FIXES = {
    "caciinternational.com":      "caci.com",
    "eliassengroup.com":          "eliassen.com",
    "judgegroup.com":             "judge.com",
    "americanitsystems.com":      "americanit.com",
    "russelltobinassociates.com": "russelltobin.com",
    "teksystemscoallegis.com":    "teksystems.com",
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
        r"professionals|bank|na|the|international|associates)\b", "", text
    )
    text = re.sub(r"[^a-z0-9\s]", "", text)
    text = re.sub(r"\s+", "", text)
    if not text:
        text = re.sub(r"[^a-z0-9]", "", company.lower())
    return clean_domain(f"{text}.com")

def domain_responds(domain: str) -> bool:
    for scheme in ("https", "http"):
        try:
            res = requests.get(
                f"{scheme}://{domain}", timeout=5, allow_redirects=True,
                headers={"User-Agent": "Mozilla/5.0"}
            )
            if res.status_code < 500:
                return True
        except:
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

def is_recruiter_contact(contact: Dict, email: str) -> bool:
    text = " ".join([
        (contact.get("position") or ""),
        (contact.get("department") or ""),
        (contact.get("seniority") or ""),
    ]).lower()
    if any(kw in text for kw in RECRUITER_KEYWORDS):
        return True
    local = email.split("@")[0].lower()
    return "." in local or "_" in local

def is_hunter_acceptable(status: str, score: int) -> bool:
    status = (status or "").lower()
    score  = score or 0
    if status == "valid":                       return True
    if status == "accept_all" and score >= 75:  return True
    if status == "risky"      and score >= 80:  return True
    return False

def hunter_domain_search(domain: str) -> Tuple[List[Dict], bool]:
    """
    Search Hunter.io for contacts at domain.
    Returns (contacts, rate_limited).
    Stops immediately on 429.
    """
    if not HUNTER_API_KEY:
        return [], False
    try:
        res = requests.get(
            "https://api.hunter.io/v2/domain-search",
            params={"domain": domain, "api_key": HUNTER_API_KEY, "limit": 10},
            timeout=25,
        )
        if res.status_code == 429:
            print(f"  ! Hunter rate limit (429) — stopping to save credits")
            return [], True  # Signal caller to stop all further searches
        if res.status_code >= 400:
            print(f"  ! Hunter error {res.status_code}: {res.text[:100]}")
            return [], False
        return res.json().get("data", {}).get("emails", []) or [], False
    except Exception as e:
        print(f"  ! Hunter exception: {str(e)[:60]}")
        return [], False

def hunter_verify_email(email: str) -> Tuple[Dict, bool]:
    """
    Verify a single email via Hunter.
    Returns (result, rate_limited).
    """
    if not HUNTER_API_KEY:
        return {"status": "unknown", "score": 0, "acceptable": True}, False
    try:
        res = requests.get(
            "https://api.hunter.io/v2/email-verifier",
            params={"email": email, "api_key": HUNTER_API_KEY},
            timeout=25,
        )
        if res.status_code == 429:
            return {"status": "rate_limited", "score": 0, "acceptable": False}, True
        if res.status_code >= 400:
            return {"status": "error", "score": 0, "acceptable": False}, False
        data   = res.json().get("data", {})
        status = data.get("status", "")
        score  = data.get("score") or 0
        return {
            "status":     status,
            "score":      score,
            "acceptable": is_hunter_acceptable(status, score),
        }, False
    except Exception as e:
        return {"status": "error", "score": 0, "acceptable": False}, False

def ai_validate_recruiter(name: str, title: str, email: str, company: str) -> bool:
    if not client_ai:
        return True
    try:
        res = client_ai.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=5, temperature=0,
            messages=[{"role": "user", "content": (
                f"Is this person likely a recruiter, HR, or talent contact?\n"
                f"Company: {company}\nName: {name}\nTitle: {title}\nEmail: {email}\n"
                f"Answer YES or NO only."
            )}],
        )
        return res.content[0].text.strip().lower().startswith("yes")
    except:
        return True  # Don't block on AI failure

def find_recruiters_hunter(company: str, domain: str) -> Tuple[List[Dict], bool]:
    """
    Find and verify recruiter contacts at domain.
    Returns (recruiters, rate_limited).
    """
    print(f"  → Hunter domain search...")
    contacts, rate_limited = hunter_domain_search(domain)

    if rate_limited:
        return [], True

    recruiters = []
    for contact in contacts:
        email = (contact.get("value") or "").lower().strip()

        if not is_good_email(email):
            continue
        if not is_recruiter_contact(contact, email):
            continue

        first = contact.get("first_name") or ""
        last  = contact.get("last_name") or ""
        name  = f"{first} {last}".strip()
        title = contact.get("position") or "Recruiting Contact"

        print(f"  → Verifying {email}...")
        verify, rate_limited = hunter_verify_email(email)

        if rate_limited:
            print(f"  ! Rate limit on verify — stopping")
            break

        if not verify["acceptable"]:
            print(f"  ! Rejected: {email} status={verify['status']} score={verify['score']}")
            continue

        if not ai_validate_recruiter(name, title, email, company):
            print(f"  ! AI rejected: {email}")
            continue

        recruiters.append({
            "name":                name,
            "title":               title,
            "email":               email,
            "source":              "hunter_ai",
            "verification_status": verify["status"],
            "verification_score":  verify["score"],
        })
        print(f"  ✓ {email} ({name}) status={verify['status']} score={verify['score']}")

        if len(recruiters) >= 5:
            break
        time.sleep(0.5)

    # Deduplicate
    seen, unique = set(), []
    for r in recruiters:
        if r["email"] not in seen:
            seen.add(r["email"])
            unique.append(r)

    return unique, False


def run_recruiter_finder() -> int:
    jobs    = load_jobs()
    updated = 0

    targets = [
        (jid, job) for jid, job in jobs.items()
        if (job.get("fit_score") or 0) >= 80
        and not job.get("email_sent")
        and job.get("recruiter_source") != "hunter_ai"
    ]

    if not targets:
        print("[Recruiter Finder] No new jobs to process")
        return 0

    print(f"[Recruiter Finder] Processing {len(targets)} jobs "
          f"(max {MAX_SEARCHES_PER_RUN} Hunter searches this run)...")

    searches_done = 0

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
            # Stop all further searches — Hunter limit hit
            print(f"[Recruiter Finder] Hunter rate limit hit — stopping for this billing period")
            # Still save what we have for this job
            job["recruiters"]       = []
            job["recruiter_email"]  = ""
            job["recruiter_name"]   = ""
            job["recruiter_source"] = "none"
            job["skip_email"]       = False  # Still send Ram alert
            save_jobs(jobs)
            break

        if not recruiters:
            print(f"  ! No verified contacts found")
            job["recruiters"]       = []
            job["recruiter_email"]  = ""
            job["recruiter_name"]   = ""
            job["recruiter_source"] = "none"
            job["skip_email"]       = False  # Still send Ram alert
        else:
            job["recruiters"]       = recruiters
            job["recruiter_email"]  = recruiters[0]["email"]
            job["recruiter_name"]   = recruiters[0].get("name", "")
            job["recruiter_source"] = "hunter_ai"
            job["skip_email"]       = False

            print(f"  → {len(recruiters)} verified contact(s) saved:")
            for r in recruiters:
                label = f" ({r['name']})" if r.get("name") else ""
                print(f"     • {r['email']}{label}")

        updated += 1
        time.sleep(1)

    save_jobs(jobs)
    print(f"\n[Recruiter Finder] Done. {updated} jobs updated. "
          f"{searches_done} Hunter searches used.")
    return updated


if __name__ == "__main__":
    run_recruiter_finder()
