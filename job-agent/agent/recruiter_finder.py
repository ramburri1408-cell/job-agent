"""
Recruiter Finder — Uses Apify actors to find real recruiter emails
Strategy:
1. website-contact-finder scrapes company website for HR emails
2. Falls back to pattern guess if nothing found
"""

import os, json, re, time
from pathlib import Path
from apify_client import ApifyClient
import anthropic

client_ai   = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
apify_token = os.environ.get("APIFY_API_KEY", "")
DATA_FILE   = Path("data/jobs.json")

SKIP_EMAILS = {"noreply", "no-reply", "support", "info", "help",
               "privacy", "legal", "press", "security", "abuse",
               "postmaster", "webmaster", "admin", "accessibility",
               "unsubscribe", "contact", "hello", "team", "sales",
               "marketing", "media", "news", "feedback", "billing"}

HR_KEYWORDS = ["hr", "recruit", "talent", "hiring", "jobs",
               "careers", "people", "staffing", "workforce"]


def load_jobs():
    return json.loads(DATA_FILE.read_text()) if DATA_FILE.exists() else {}

def save_jobs(jobs):
    DATA_FILE.write_text(json.dumps(jobs, indent=2))

def company_to_domain(company: str) -> str:
    clean = re.sub(
        r'\s*\b(inc|llc|ltd|corp|co|company|technologies|tech|'
        r'solutions|services|group|global|systems|consulting|'
        r'staffing|professionals|bank|na|the)\b\s*',
        ' ', company.lower()
    )
    clean = re.sub(r'[^a-z0-9\s]', '', clean).strip().replace(' ', '')
    if not clean:
        clean = re.sub(r'[^a-z0-9]', '', company.lower())
    return f"{clean}.com"

def guess_email(name: str, domain: str) -> str:
    parts = name.lower().strip().split()
    if len(parts) >= 2:
        return f"{parts[0]}.{parts[-1]}@{domain}"
    elif parts:
        return f"{parts[0]}@{domain}"
    return f"careers@{domain}"

def is_good_email(email: str) -> bool:
    """Filter out generic/system emails."""
    local = email.split("@")[0].lower()
    return not any(s in local for s in SKIP_EMAILS)

def is_hr_email(email: str) -> bool:
    """Check if email looks like HR/recruiting."""
    local = email.split("@")[0].lower()
    return any(k in local for k in HR_KEYWORDS)

def find_emails_on_website(company: str, domain: str) -> list:
    """Use Apify website-contact-finder to get real emails from company site."""
    if not apify_token:
        return []

    recruiters = []
    try:
        apify = ApifyClient(apify_token)
        print(f"  → Scanning website: {domain}")

        run = apify.actor("automation-lab/website-contact-finder").call(
            run_input={
                "urls":            [f"https://www.{domain}"],
                "maxPagesPerSite": 10,
            },
            timeout_secs=120,
        )

        items = list(apify.dataset(run["defaultDatasetId"]).iterate_items())

        for item in items:
            emails = item.get("emails", [])
            if not emails:
                continue

            # Prefer HR emails, then any good email
            hr_emails  = [e for e in emails if is_hr_email(e) and is_good_email(e)]
            all_emails = [e for e in emails if is_good_email(e)]
            target     = hr_emails or all_emails

            for email in target[:5]:
                recruiters.append({
                    "name":   "",
                    "title":  "HR Contact",
                    "email":  email,
                    "source": "apify_website",
                })
                print(f"  ✓ Found: {email}")

    except Exception as e:
        print(f"  ! Website scan error: {str(e)[:80]}")

    return recruiters


def pick_best_emails(recruiters: list, company: str) -> list:
    """Use Claude to pick best recruiter emails from list."""
    if len(recruiters) <= 3:
        return recruiters

    emails = [r["email"] for r in recruiters]
    try:
        result = client_ai.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=150,
            system=(
                "Pick the 3 best recruiter/HR/talent emails. "
                "Prefer: recruit@, hr@, talent@, hiring@, jobs@, careers@, people@. "
                "Return ONLY JSON array: [\"email1\", \"email2\", \"email3\"]"
            ),
            messages=[{"role": "user", "content": f"Company: {company}\nEmails: {emails}"}]
        ).content[0].text.strip()

        start = result.find("[")
        end   = result.rfind("]") + 1
        if start >= 0 and end > start:
            best = json.loads(result[start:end])
            return [r for r in recruiters if r["email"] in best][:3]
    except:
        pass

    return recruiters[:3]


def run_recruiter_finder():
    """Find real recruiter contacts for all high-score uncontacted jobs."""
    jobs    = load_jobs()
    updated = 0

    targets = [
        (jid, job) for jid, job in jobs.items()
        if (job.get("fit_score") or 0) >= 80
        and not job.get("email_sent")
        and job.get("recruiter_source") not in ["apify_website", "apify_linkedin"]
    ]

    if not targets:
        print("[Recruiter Finder] No new jobs to process")
        return 0

    print(f"[Recruiter Finder] Finding recruiters for {len(targets)} jobs...")

    for jid, job in targets[:15]:
        company = job.get("company", "").strip()
        domain  = company_to_domain(company)

        print(f"\n  [{company}] → {domain}")

        # Try Apify website contact finder
        recruiters = find_emails_on_website(company, domain)

        # Pick best emails if many found
        if len(recruiters) > 3:
            recruiters = pick_best_emails(recruiters, company)

        # Fall back to careers@ pattern
        if not recruiters:
            print(f"  ! No emails found — using careers@ fallback")
            recruiters = [{
                "name":   "",
                "title":  "HR Team",
                "email":  f"careers@{domain}",
                "source": "pattern_guess",
            }]

        # Save to job
        jobs[jid]["recruiters"]       = recruiters
        jobs[jid]["recruiter_email"]  = recruiters[0]["email"]
        jobs[jid]["recruiter_name"]   = recruiters[0].get("name", "")
        jobs[jid]["recruiter_source"] = recruiters[0]["source"]

        print(f"  → {len(recruiters)} contact(s) saved")
        for r in recruiters:
            print(f"     • {r['email']}")

        updated += 1
        time.sleep(2)

    save_jobs(jobs)
    print(f"\n[Recruiter Finder] Done. {updated} jobs updated.")
    return updated


if __name__ == "__main__":
    run_recruiter_finder()
