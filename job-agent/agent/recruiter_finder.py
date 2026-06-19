"""
Recruiter Finder - Hunter.io + Anthropic Production Version
Fixed: accepts accept_all domains (catch-all servers)
"""

import json, os, re, time
from pathlib import Path
from typing import Dict, List, Optional
import anthropic
import requests

DATA_FILE      = Path("data/jobs.json")
HUNTER_API_KEY = os.environ.get("HUNTER_API_KEY", "").strip()
ANTHROPIC_KEY  = os.environ.get("ANTHROPIC_API_KEY", "").strip()

client_ai = anthropic.Anthropic(api_key=ANTHROPIC_KEY) if ANTHROPIC_KEY else None

RECRUITER_KEYWORDS = {
    "recruiter", "technical recruiter", "engineering recruiter",
    "talent acquisition", "talent partner", "talent sourcer",
    "sourcer", "human resources", "people operations",
    "staffing", "hiring", "recruiting",
}

BAD_LOCAL_PARTS = {
    "noreply", "no-reply", "donotreply", "do-not-reply",
    "support", "info", "help", "privacy", "legal", "press",
    "admin", "abuse", "example", "test", "unsubscribe",
    "feedback", "news", "phishing", "spam", "security",
    "verification", "verifications", "compliance",
    "notifications", "alerts",
}

COMMON_DOMAIN_FIXES = {
    "caciinternational.com": "caci.com",
    "eliassengroup.com":     "eliassen.com",
    "judgegroup.com":        "judge.com",
    "americanitsystems.com": "americanit.com",
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
    domain = domain.replace("https://", "").replace("http://", "").replace("www.", "")
    domain = domain.split("/")[0].strip()
    return COMMON_DOMAIN_FIXES.get(domain, domain)

def company_to_domain(company: str) -> str:
    text = company.lower().strip()
    text = re.sub(
        r"\b(inc|llc|ltd|corp|corporation|co|company|technologies|technology|"
        r"tech|solutions|services|group|global|systems|consulting|staffing|"
        r"professionals|bank|na|the|international)\b", "", text
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
                f"{scheme}://{domain}", timeout=6, allow_redirects=True,
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
    local = email.strip().lower().split("@")[0]
    if any(bad == local or bad in local for bad in BAD_LOCAL_PARTS):
        return False
    # Block all-caps (system emails like HRSD.Employee.Verifications)
    if local.upper() == local and len(local) > 5:
        return False
    return True

def looks_like_person(email: str) -> bool:
    local = email.split("@")[0].lower()
    return "." in local or "_" in local

def is_recruiter_contact(contact: Dict, email: str) -> bool:
    position   = (contact.get("position") or "").lower()
    department = (contact.get("department") or "").lower()
    seniority  = (contact.get("seniority") or "").lower()
    text       = f"{position} {department} {seniority}"
    if any(kw in text for kw in RECRUITER_KEYWORDS):
        return True
    # Fallback: accept person-looking emails
    return looks_like_person(email)

def hunter_domain_search(domain: str) -> List[Dict]:
    if not HUNTER_API_KEY:
        return []
    try:
        res = requests.get(
            "https://api.hunter.io/v2/domain-search",
            params={"domain": domain, "api_key": HUNTER_API_KEY, "limit": 10},
            timeout=25,
        )
        if res.status_code >= 400:
            print(f"  ! Hunter error {res.status_code}: {res.text[:100]}")
            return []
        return res.json().get("data", {}).get("emails", []) or []
    except Exception as e:
        print(f"  ! Hunter exception: {str(e)[:80]}")
        return []

def hunter_verify_email(email: str) -> Dict:
    """
    Verify email via Hunter.
    Fixed: now accepts accept_all status (catch-all domains)
    accept_all means the server accepts all emails — still likely real.
    """
    if not HUNTER_API_KEY:
        return {"verified": True, "status": "unknown", "score": 0}
    try:
        res = requests.get(
            "https://api.hunter.io/v2/email-verifier",
            params={"email": email, "api_key": HUNTER_API_KEY},
            timeout=25,
        )
        if res.status_code >= 400:
            return {"verified": True, "status": "error", "score": 0}
        data   = res.json().get("data", {})
        status = data.get("status", "")
        score  = data.get("score") or 0

        # Accept: valid (confirmed) OR accept_all (catch-all, still real)
        # Reject only: invalid, disposable, webmail generics
        verified = status in ("valid", "accept_all") or score >= 70

        return {"verified": verified, "status": status, "score": score}
    except Exception as e:
        print(f"  ! Hunter verify exception: {str(e)[:60]}")
        return {"verified": True, "status": "error", "score": 0}

def ai_validate_recruiter(name: str, title: str, email: str, company: str) -> bool:
    if not client_ai:
        return True
    try:
        response = client_ai.messages.create(
            model="claude-opus-4-8",
            max_tokens=5,
            messages=[{"role": "user", "content": (
                f"Is this person likely a recruiter, HR, or talent acquisition contact?\n"
                f"Company: {company}\nName: {name or 'Unknown'}\n"
                f"Title: {title or 'Unknown'}\nEmail: {email}\n"
                f"Answer only YES or NO."
            )}],
        )
        return response.content[0].text.strip().lower().startswith("yes")
    except Exception as e:
        print(f"  ! AI validation skipped: {str(e)[:60]}")
        return True  # Don't block on AI failure

def find_recruiters_hunter(company: str, domain: str) -> List[Dict]:
    print(f"  → Hunter domain search...")
    contacts   = hunter_domain_search(domain)
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
        verify = hunter_verify_email(email)

        if not verify["verified"]:
            print(f"  ! Rejected: {email} status={verify['status']} score={verify['score']}")
            continue

        if not ai_validate_recruiter(name, title, email, company):
            print(f"  ! AI rejected: {email} — {title}")
            continue

        recruiters.append({
            "name":                name,
            "title":               title,
            "email":               email,
            "source":              "hunter_ai",
            "verification_status": verify["status"],
            "verification_score":  verify["score"],
        })
        print(f"  ✓ {email} ({name or 'No Name'}) status={verify['status']} score={verify['score']}")

        if len(recruiters) >= 5:
            break
        time.sleep(0.5)

    # Deduplicate
    seen, unique = set(), []
    for r in recruiters:
        if r["email"] not in seen:
            seen.add(r["email"])
            unique.append(r)
    return unique

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

    print(f"[Recruiter Finder] Processing {len(targets)} jobs...")

    for jid, job in targets[:15]:
        company = (job.get("company") or "").strip()
        if not company:
            continue

        domain = resolve_domain(company, job)
        print(f"\n  [{company}] → {domain}")

        recruiters = find_recruiters_hunter(company, domain)

        if not recruiters:
            print(f"  ! No verified recruiter found — skipping email")
            job["recruiters"]       = []
            job["recruiter_email"]  = ""
            job["recruiter_name"]   = ""
            job["recruiter_source"] = "none"
            job["skip_email"]       = True
        else:
            job["recruiters"]       = recruiters
            job["recruiter_email"]  = recruiters[0]["email"]
            job["recruiter_name"]   = recruiters[0].get("name", "")
            job["recruiter_source"] = "hunter_ai"
            job["skip_email"]       = False
            print(f"  → {len(recruiters)} contact(s) saved:")
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
