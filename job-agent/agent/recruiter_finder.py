"""
Recruiter Finder — Google search company careers + LinkedIn
For each job:
1. Google search "Company careers recruiter site:linkedin.com"
2. Extract recruiter names from LinkedIn profiles in results
3. Apollo matches name + domain to get verified email
4. Falls back to careers page email or pattern guess
"""

import os, json, re, time
from pathlib import Path
from apify_client import ApifyClient
import anthropic
import requests

client_ai   = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
apify_token = os.environ.get("APIFY_API_KEY", "")
apollo_key  = os.environ.get("APOLLO_API_KEY", "")
DATA_FILE   = Path("data/jobs.json")

EMAIL_RE = re.compile(r'[\w.+-]+@[\w-]+\.[a-zA-Z]{2,}')
SKIP     = {"noreply", "no-reply", "support", "info", "help", "privacy",
            "legal", "press", "admin", "abuse", "example", "test",
            "sentry", "wix", "unsubscribe", "feedback", "news"}

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

def is_good_email(email: str) -> bool:
    local = email.split("@")[0].lower()
    return not any(s in local for s in SKIP) and len(email) < 80

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

def google_search_company(page, company: str, domain: str) -> dict:
    """
    Search Google for company careers page and LinkedIn recruiters.
    Returns {careers_url, recruiter_names, emails}
    """
    result = {"careers_url": "", "recruiter_names": [], "emails": []}

    queries = [
        # Find LinkedIn recruiter profiles
        f'site:linkedin.com/in "{company}" recruiter OR "talent acquisition" OR "HR manager"',
        # Find company careers page with contact info
        f'"{company}" careers recruiter email contact hiring',
        # Find company LinkedIn page people section
        f'site:linkedin.com/company "{company}" recruiter hiring',
    ]

    for query in queries:
        try:
            url = f"https://www.google.com/search?q={requests.utils.quote(query)}&num=10"
            page.goto(url, timeout=20000, wait_until="domcontentloaded")
            page.wait_for_timeout(2000)

            text = page.inner_text("body")

            # Skip if CAPTCHA
            if "unusual traffic" in text.lower() or "captcha" in text.lower():
                print(f"  ! Google CAPTCHA — skipping")
                break

            # Extract emails
            emails = [e for e in EMAIL_RE.findall(text) if is_good_email(e)]
            for email in emails:
                if email not in result["emails"]:
                    result["emails"].append(email)

            # Extract LinkedIn profile names (Name - Title at Company)
            lines = text.split('\n')
            for i, line in enumerate(lines):
                line = line.strip()
                # Pattern: "FirstName LastName - Recruiter at Company"
                match = re.match(
                    r'^([A-Z][a-z]+ [A-Z][a-z]+(?:\s[A-Z][a-z]+)?)\s*[-–|]\s*(.+?)(?:\s*[-–|@]\s*.+)?$',
                    line
                )
                if match:
                    name  = match.group(1).strip()
                    title = match.group(2).strip()
                    if is_recruiter(title) and name not in result["recruiter_names"]:
                        result["recruiter_names"].append(name)
                        print(f"  ✓ Found recruiter: {name} — {title}")

            # Extract careers page URL from results
            if not result["careers_url"]:
                links = page.query_selector_all('a[href*="careers"], a[href*="jobs"]')
                for link in links[:3]:
                    href = link.get_attribute("href") or ""
                    if domain.split(".")[0] in href and "google" not in href:
                        result["careers_url"] = href
                        break

            if len(result["recruiter_names"]) >= 5:
                break

            time.sleep(2)

        except Exception as e:
            print(f"  ! Google search error: {str(e)[:60]}")

    return result

def scrape_careers_page(page, url: str) -> list:
    """Scrape company careers page for HR emails."""
    emails = []
    try:
        page.goto(url, timeout=20000, wait_until="domcontentloaded")
        page.wait_for_timeout(2000)
        text   = page.inner_text("body")
        found  = [e for e in EMAIL_RE.findall(text) if is_good_email(e)]
        # Prefer HR/recruiting emails
        hr     = [e for e in found if any(k in e.lower() for k in
                   ["hr", "recruit", "talent", "hiring", "jobs", "careers", "people"])]
        emails = hr or found[:3]
    except Exception as e:
        print(f"  ! Careers page error: {str(e)[:60]}")
    return emails

def apollo_match(name: str, domain: str) -> str:
    """Use Apollo to get verified email for a person."""
    if not apollo_key or not name:
        return ""
    try:
        parts = name.lower().split()
        if len(parts) < 2:
            return ""
        resp = requests.get(
            "https://api.apollo.io/api/v1/people/match",
            params={
                "api_key":    apollo_key,
                "first_name": parts[0],
                "last_name":  parts[-1],
                "domain":     domain,
            },
            timeout=15,
        )
        if resp.status_code == 200:
            person = resp.json().get("person") or {}
            email  = person.get("email", "")
            if email and "@" in email:
                return email
    except Exception as e:
        print(f"  ! Apollo error: {str(e)[:60]}")
    return ""

def find_recruiters(page, company: str, domain: str) -> list:
    """
    Full flow:
    1. Google search for LinkedIn recruiter profiles + company careers page
    2. Extract recruiter names
    3. Apollo verifies their emails
    4. Scrape careers page for direct emails
    5. Fall back to pattern guess
    """
    recruiters = []

    print(f"  → Googling recruiters at {company}...")
    google_data = google_search_company(page, company, domain)

    # Step 1: Apollo verify names found via Google
    for name in google_data["recruiter_names"][:5]:
        email = apollo_match(name, domain)
        if not email:
            email = guess_email(name, domain)
        if not any(r["email"] == email for r in recruiters):
            recruiters.append({
                "name":   name,
                "title":  "Recruiter",
                "email":  email,
                "source": "google_linkedin",
            })
            print(f"  → {name} → {email}")

    # Step 2: Use emails found directly in Google results
    if len(recruiters) < 3:
        for email in google_data["emails"][:3]:
            if email not in [r["email"] for r in recruiters]:
                recruiters.append({
                    "name":   "",
                    "title":  "HR Contact",
                    "email":  email,
                    "source": "google_email",
                })
                print(f"  → Email from Google: {email}")

    # Step 3: Scrape careers page
    if len(recruiters) < 2:
        careers_urls = [
            google_data.get("careers_url", ""),
            f"https://www.{domain}/careers",
            f"https://www.{domain}/about",
        ]
        for curl in careers_urls:
            if not curl:
                continue
            emails = scrape_careers_page(page, curl)
            for email in emails:
                if email not in [r["email"] for r in recruiters]:
                    recruiters.append({
                        "name":   "",
                        "title":  "HR Contact",
                        "email":  email,
                        "source": "careers_page",
                    })
                    print(f"  → Careers page email: {email}")
            if recruiters:
                break

    # Step 4: Apollo search by title + domain
    if not recruiters and apollo_key:
        for title in ["recruiter", "talent acquisition", "hr manager"]:
            try:
                resp = requests.get(
                    "https://api.apollo.io/api/v1/people/match",
                    params={"api_key": apollo_key, "domain": domain, "title": title},
                    timeout=15,
                )
                if resp.status_code == 200:
                    person = resp.json().get("person") or {}
                    name   = person.get("name", "")
                    email  = person.get("email", "") or guess_email(name, domain)
                    if name and email:
                        recruiters.append({
                            "name":   name,
                            "title":  person.get("title", title),
                            "email":  email,
                            "source": "apollo",
                        })
                        print(f"  ✓ Apollo: {name} → {email}")
                        break
                time.sleep(1)
            except Exception as e:
                print(f"  ! Apollo: {str(e)[:60]}")

    return recruiters

def run_recruiter_finder():
    from playwright.sync_api import sync_playwright

    jobs    = load_jobs()
    updated = 0

    targets = [
        (jid, job) for jid, job in jobs.items()
        if (job.get("fit_score") or 0) >= 80
        and not job.get("email_sent")
        and job.get("recruiter_source") not in
            ["google_linkedin", "google_email", "careers_page", "apollo"]
    ]

    if not targets:
        print("[Recruiter Finder] No new jobs to process")
        return 0

    print(f"[Recruiter Finder] Processing {len(targets)} jobs...")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox",
                  "--disable-dev-shm-usage",
                  "--disable-blink-features=AutomationControlled"]
        )
        ctx = browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            locale="en-US",
        )
        ctx.add_init_script(
            "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"
        )
        page = ctx.new_page()
        page.set_default_timeout(20000)

        for jid, job in targets[:15]:
            company = job.get("company", "").strip()
            domain  = company_to_domain(company)

            print(f"\n  [{company}] → {domain}")

            recruiters = find_recruiters(page, company, domain)

            if not recruiters:
                print(f"  ! No contacts found — using careers@ fallback")
                recruiters = [{
                    "name":   "",
                    "title":  "HR Team",
                    "email":  f"careers@{domain}",
                    "source": "pattern_guess",
                }]

            # Deduplicate
            seen, unique = set(), []
            for r in recruiters:
                if r["email"] not in seen:
                    seen.add(r["email"])
                    unique.append(r)
            recruiters = unique[:5]

            jobs[jid]["recruiters"]       = recruiters
            jobs[jid]["recruiter_email"]  = recruiters[0]["email"]
            jobs[jid]["recruiter_name"]   = recruiters[0].get("name", "")
            jobs[jid]["recruiter_source"] = recruiters[0]["source"]

            print(f"  → {len(recruiters)} contact(s) saved:")
            for r in recruiters:
                label = f" ({r['name']})" if r.get("name") else ""
                print(f"     • {r['email']}{label}")

            updated += 1
            time.sleep(3)

        browser.close()

    save_jobs(jobs)
    print(f"\n[Recruiter Finder] Done. {updated} jobs updated.")
    return updated

if __name__ == "__main__":
    run_recruiter_finder()
