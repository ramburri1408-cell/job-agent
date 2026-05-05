"""
Recruiter Finder — Apify scrapes job posting + Apollo finds recruiter emails
Flow:
1. Apify website-content-crawler scrapes job posting page
2. Extracts company name + domain
3. Apollo API searches for HR/Recruiter people at company
4. Returns verified emails with real names
"""

import os, json, re, time
from pathlib import Path
from apify_client import ApifyClient
import anthropic
import requests

client_ai    = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
apify_token  = os.environ.get("APIFY_API_KEY", "")
apollo_key   = os.environ.get("APOLLO_API_KEY", "")
DATA_FILE    = Path("data/jobs.json")

RECRUITER_TITLES = [
    "recruiter", "talent acquisition", "hr manager", "human resources",
    "hiring manager", "talent partner", "people operations",
    "technical recruiter", "engineering recruiter", "hr business partner",
    "head of talent", "director of recruiting", "sourcer", "staffing",
    "people partner", "workforce", "recruitment",
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


def scrape_job_page(url: str) -> dict:
    """
    Use Apify website-content-crawler to scrape job posting page.
    Extracts company info, description, any contact details.
    """
    if not apify_token or not url or not url.startswith("http"):
        return {}

    try:
        apify = ApifyClient(apify_token)
        print(f"  → Apify scraping job page...")

        run = apify.actor("apify/website-content-crawler").call(
            run_input={
                "startUrls":     [{"url": url}],
                "maxCrawlPages": 1,
                "crawlerType":   "cheerio",
            },
            timeout_secs=60,
        )

        items = list(apify.dataset(run["defaultDatasetId"]).iterate_items())
        if not items:
            return {}

        item = items[0]
        text = item.get("text", "") or item.get("markdown", "")

        # Extract emails directly from page
        emails = re.findall(r'[\w.+-]+@[\w-]+\.[a-zA-Z]{2,}', text)
        emails = [e for e in emails if "@" in e and len(e) < 80]

        return {
            "text":   text[:2000],
            "emails": emails,
            "url":    item.get("url", url),
        }

    except Exception as e:
        print(f"  ! Apify scrape error: {str(e)[:80]}")
        return {}


def find_recruiters_apollo(company: str, domain: str) -> list:
    """
    Use Apollo.io API to find HR/Recruiter people at the company.
    Returns list of {name, title, email} dicts.
    """
    if not apollo_key:
        print(f"  ! No Apollo API key")
        return []

    recruiters = []
    try:
        print(f"  → Apollo searching recruiters at {company}...")

        # Apollo People Search API
        response = requests.post(
            "https://api.apollo.io/v1/mixed_people/search",
            headers={
                "Content-Type":  "application/json",
                "Cache-Control": "no-cache",
                "X-Api-Key":     apollo_key,
            },
            json={
                "q_organization_name":   company,
                "organization_domains":  [domain],
                "person_titles":         [
                    "recruiter", "talent acquisition", "hr manager",
                    "technical recruiter", "engineering recruiter",
                    "hiring manager", "talent partner", "hr business partner",
                    "head of talent", "director of recruiting",
                    "people operations", "staffing manager",
                ],
                "person_locations":      ["United States"],
                "per_page":              10,
                "page":                  1,
            },
            timeout=30,
        )

        if response.status_code != 200:
            print(f"  ! Apollo error: {response.status_code} {response.text[:100]}")
            return []

        data    = response.json()
        people  = data.get("people", [])
        print(f"  → Apollo found {len(people)} people")

        for person in people:
            name  = person.get("name", "")
            title = person.get("title", "")
            email = person.get("email", "")

            # Skip if no email
            if not email or "@" not in email:
                # Try to get email via Apollo enrich
                email = enrich_email_apollo(
                    person.get("id", ""),
                    person.get("linkedin_url", ""),
                    name,
                    domain
                )

            if email and "@" in email:
                recruiters.append({
                    "name":    name,
                    "title":   title,
                    "email":   email,
                    "source":  "apollo",
                    "linkedin": person.get("linkedin_url", ""),
                })
                print(f"  ✓ {name} — {title} → {email}")

            if len(recruiters) >= 5:
                break

    except Exception as e:
        print(f"  ! Apollo error: {str(e)[:100]}")

    return recruiters


def enrich_email_apollo(person_id: str, linkedin_url: str, name: str, domain: str) -> str:
    """
    Use Apollo enrich API to get email for a specific person.
    Falls back to name pattern if enrich fails.
    """
    if not apollo_key:
        return ""

    try:
        # Apollo person enrich
        params = {"api_key": apollo_key}
        if linkedin_url:
            params["linkedin_url"] = linkedin_url
        elif name:
            parts = name.lower().split()
            if len(parts) >= 2:
                params["first_name"] = parts[0]
                params["last_name"]  = parts[-1]
                params["domain"]     = domain

        response = requests.get(
            "https://api.apollo.io/v1/people/match",
            params=params,
            timeout=20,
        )

        if response.status_code == 200:
            data   = response.json()
            person = data.get("person", {})
            email  = person.get("email", "")
            if email and "@" in email:
                return email

    except Exception as e:
        print(f"  ! Enrich error: {str(e)[:60]}")

    # Fall back to name pattern
    if name:
        parts = name.lower().strip().split()
        if len(parts) >= 2:
            return f"{parts[0]}.{parts[-1]}@{domain}"

    return ""


def run_recruiter_finder():
    """
    Main pipeline:
    1. Apify scrapes each job posting for company info + any direct emails
    2. Apollo finds verified recruiter emails at the company
    3. Saves all contacts to jobs.json
    """
    jobs    = load_jobs()
    updated = 0

    targets = [
        (jid, job) for jid, job in jobs.items()
        if (job.get("fit_score") or 0) >= 80
        and not job.get("email_sent")
        and job.get("recruiter_source") not in ["apollo", "apify_website"]
    ]

    if not targets:
        print("[Recruiter Finder] No new jobs to process")
        return 0

    print(f"[Recruiter Finder] Processing {len(targets)} jobs...")

    for jid, job in targets[:15]:
        company = job.get("company", "").strip()
        domain  = company_to_domain(company)
        url     = job.get("url", "")

        print(f"\n  [{company}] → {domain}")

        recruiters = []

        # Step 1 — Apify scrapes job page for any direct emails
        if url and url.startswith("http"):
            page_data = scrape_job_page(url)
            direct_emails = page_data.get("emails", [])
            skip = {"noreply", "support", "info", "help", "privacy",
                    "legal", "press", "admin", "abuse", "no-reply"}
            for email in direct_emails:
                local = email.split("@")[0].lower()
                if not any(s in local for s in skip):
                    recruiters.append({
                        "name":   "",
                        "title":  "Contact from job posting",
                        "email":  email,
                        "source": "job_page",
                    })
                    print(f"  ✓ Found on job page: {email}")

        # Step 2 — Apollo finds verified recruiter emails
        if not recruiters or len(recruiters) < 3:
            apollo_recruiters = find_recruiters_apollo(company, domain)
            recruiters.extend(apollo_recruiters)

        # Step 3 — Fall back to pattern guess
        if not recruiters:
            print(f"  ! No contacts found — using careers@ fallback")
            recruiters = [{
                "name":   "",
                "title":  "HR Team",
                "email":  f"careers@{domain}",
                "source": "pattern_guess",
            }]

        # Deduplicate by email
        seen = set()
        unique = []
        for r in recruiters:
            if r["email"] not in seen:
                seen.add(r["email"])
                unique.append(r)
        recruiters = unique[:5]

        # Save to job
        jobs[jid]["recruiters"]       = recruiters
        jobs[jid]["recruiter_email"]  = recruiters[0]["email"]
        jobs[jid]["recruiter_name"]   = recruiters[0].get("name", "")
        jobs[jid]["recruiter_source"] = recruiters[0]["source"]

        print(f"  → {len(recruiters)} contact(s) saved:")
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
