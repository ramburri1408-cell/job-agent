"""
Recruiter Finder — Uses Apify LinkedIn Company Employees Scraper
Actor: automation-lab/linkedin-company-employees-scraper
- Cookie-free mode (no LinkedIn login needed)
- Finds HR/Recruiter employees at each company
- Builds likely email from name + domain
"""

import os, json, re, time
from pathlib import Path
from apify_client import ApifyClient
import anthropic

client_ai   = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
apify_token = os.environ.get("APIFY_API_KEY", "")
DATA_FILE   = Path("data/jobs.json")

RECRUITER_TITLES = [
    "recruiter", "talent acquisition", "hr manager", "human resources",
    "hiring manager", "talent partner", "people operations",
    "technical recruiter", "engineering recruiter", "hr business partner",
    "head of talent", "director of recruiting", "sourcer", "staffing",
]

def load_jobs():
    return json.loads(DATA_FILE.read_text()) if DATA_FILE.exists() else {}

def save_jobs(jobs):
    DATA_FILE.write_text(json.dumps(jobs, indent=2))

def is_recruiter(title: str) -> bool:
    return any(r in title.lower() for r in RECRUITER_TITLES)

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

def find_recruiters_apify(company: str, domain: str) -> list:
    """
    Use Apify LinkedIn Company Employees Scraper to find
    HR/Recruiter employees at the company.
    Cookie-free mode — no LinkedIn login needed.
    """
    if not apify_token:
        print(f"  ! No Apify token")
        return []

    recruiters = []
    try:
        apify  = ApifyClient(apify_token)

        print(f"  → Searching LinkedIn employees at {company} via Apify...")

        run = apify.actor("automation-lab/linkedin-company-employees-scraper").call(
            run_input={
                "companyName":   company,
                "cookieFree":    True,       # No LinkedIn login needed
                "filterByTitle": "recruiter,HR,talent acquisition,hiring,people",
                "maxResults":    10,
                "country":       "United States",
            },
            timeout_secs=120,
        )

        # Get results
        items = list(apify.dataset(run["defaultDatasetId"]).iterate_items())
        print(f"  → Apify returned {len(items)} employees")

        for item in items:
            name  = item.get("name", "") or item.get("fullName", "")
            title = item.get("title", "") or item.get("headline", "")
            loc   = item.get("location", "")

            if not name:
                continue

            # Filter to US-based HR/Recruiter people
            is_us = not loc or any(k in loc.lower() for k in
                                   ["united states", "us", "usa", ", tx", ", ny",
                                    ", ca", ", fl", ", wa", ", il", ", ga"])

            if is_recruiter(title) and is_us:
                email = guess_email(name, domain)
                recruiters.append({
                    "name":    name,
                    "title":   title,
                    "email":   email,
                    "source":  "apify_linkedin",
                    "linkedin": item.get("profileUrl", ""),
                })
                print(f"  ✓ {name} — {title} → {email}")

            if len(recruiters) >= 6:
                break

    except Exception as e:
        print(f"  ! Apify error: {str(e)[:100]}")

    return recruiters


def run_recruiter_finder():
    """Find real recruiter contacts for all high-score uncontacted jobs."""
    jobs    = load_jobs()
    updated = 0

    targets = [
        (jid, job) for jid, job in jobs.items()
        if (job.get("fit_score") or 0) >= 80
        and not job.get("email_sent")
        and job.get("recruiter_source") != "apify_linkedin"
    ]

    if not targets:
        print("[Recruiter Finder] No new jobs to process")
        return 0

    print(f"[Recruiter Finder] Finding recruiters for {len(targets)} jobs...")

    for jid, job in targets[:15]:
        company = job.get("company", "")
        domain  = company_to_domain(company)

        print(f"\n  [{company}] → {domain}")

        # Use Apify to find real recruiters
        recruiters = find_recruiters_apify(company, domain)

        # Fall back to careers@ if nothing found
        if not recruiters:
            print(f"  ! No recruiters found — using careers@ fallback")
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
            label = f" ({r['name']})" if r.get("name") else ""
            print(f"     • {r['email']}{label}")

        updated += 1
        time.sleep(2)

    save_jobs(jobs)
    print(f"\n[Recruiter Finder] Done. {updated} jobs updated.")
    return updated


if __name__ == "__main__":
    run_recruiter_finder()
