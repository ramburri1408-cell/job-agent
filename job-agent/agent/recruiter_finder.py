"""
Recruiter Finder — Playwright scrapes LinkedIn company page
to find real HR/Recruiter profiles and their contact info.
Standard job search outreach practice.
"""

import os, json, re, time
from pathlib import Path
import anthropic

client_ai = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
DATA_FILE = Path("data/jobs.json")

EMAIL_RE = re.compile(r'[\w.+-]+@[\w-]+\.[a-zA-Z]{2,}')
SKIP     = {"noreply", "no-reply", "support", "info", "help",
            "privacy", "legal", "press", "security", "abuse",
            "postmaster", "webmaster", "admin"}

RECRUITER_TITLES = [
    "recruiter", "talent acquisition", "hr manager", "human resources",
    "hiring manager", "talent partner", "people operations",
    "technical recruiter", "engineering recruiter", "hr business partner",
]


def load_jobs():
    return json.loads(DATA_FILE.read_text()) if DATA_FILE.exists() else {}

def save_jobs(jobs):
    DATA_FILE.write_text(json.dumps(jobs, indent=2))

def extract_emails(text: str) -> list:
    found = EMAIL_RE.findall(text)
    return [e for e in found
            if not any(s in e.lower() for s in SKIP)
            and len(e) < 100]

def is_recruiter_title(title: str) -> bool:
    t = title.lower()
    return any(r in t for r in RECRUITER_TITLES)

def guess_email_from_name(name: str, domain: str) -> str:
    """Generate likely email from name + domain."""
    parts = name.lower().strip().split()
    if len(parts) >= 2:
        first, last = parts[0], parts[-1]
        # Most common corporate patterns
        return f"{first}.{last}@{domain}"
    return f"careers@{domain}"

def company_to_domain(company: str) -> str:
    clean = re.sub(
        r'\s*\b(inc|llc|ltd|corp|co|company|technologies|tech|'
        r'solutions|services|group|global|systems|consulting|'
        r'staffing|professionals|bank|na)\b\s*', ' ', company.lower()
    )
    clean = re.sub(r'[^a-z0-9\s]', '', clean).strip().replace(' ', '')
    if not clean:
        clean = re.sub(r'[^a-z0-9]', '', company.lower())
    return f"{clean}.com"


def find_recruiters_on_linkedin(page, company: str, domain: str) -> list:
    """
    Search LinkedIn for HR/Recruiter people at the company.
    Returns list of {name, title, email} dicts.
    """
    recruiters = []
    try:
        # Search LinkedIn for recruiters at this company
        query = f"{company} recruiter HR talent acquisition United States"
        search_url = f"https://www.linkedin.com/search/results/people/?keywords={query.replace(' ', '%20')}&origin=GLOBAL_SEARCH_HEADER"

        print(f"  → Searching LinkedIn for recruiters at {company}")
        page.goto(search_url, timeout=25000, wait_until="domcontentloaded")
        page.wait_for_timeout(3000)

        # Check if we need to handle login wall
        if "authwall" in page.url or "login" in page.url:
            print(f"  ! LinkedIn requires login — trying public search")
            # Try Google search instead
            return find_recruiters_via_google(page, company, domain)

        # Extract people cards from LinkedIn search results
        cards = page.query_selector_all(
            '.reusable-search__result-container, '
            '[data-view-name="search-entity-result-universal-template"]'
        )

        print(f"  → Found {len(cards)} LinkedIn profiles")

        for card in cards[:10]:
            try:
                # Get name
                name_el = card.query_selector(
                    '.entity-result__title-text, '
                    'span[aria-hidden="true"], '
                    '.actor-name'
                )
                name = name_el.inner_text().strip() if name_el else ""

                # Get title/position
                title_el = card.query_selector(
                    '.entity-result__primary-subtitle, '
                    '.subline-level-1'
                )
                title = title_el.inner_text().strip() if title_el else ""

                # Only include HR/Recruiter titles
                if name and is_recruiter_title(title):
                    email = guess_email_from_name(name, domain)
                    recruiters.append({
                        "name":   name,
                        "title":  title,
                        "email":  email,
                        "source": "linkedin_search",
                    })
                    print(f"  ✓ Found recruiter: {name} — {title}")

                if len(recruiters) >= 6:
                    break

            except Exception:
                continue

    except Exception as e:
        print(f"  ! LinkedIn search error: {str(e)[:60]}")
        return find_recruiters_via_google(page, company, domain)

    return recruiters


def find_recruiters_via_google(page, company: str, domain: str) -> list:
    """
    Fallback — Google search for company recruiters.
    Finds publicly listed HR contacts.
    """
    recruiters = []
    try:
        query = f'site:linkedin.com "{company}" recruiter OR "talent acquisition" OR "HR manager"'
        url   = f"https://www.google.com/search?q={query.replace(' ', '+')}"

        page.goto(url, timeout=20000, wait_until="domcontentloaded")
        page.wait_for_timeout(2000)

        text = page.inner_text("body")

        # Extract names and emails from Google results
        emails = extract_emails(text)
        if emails:
            for email in emails[:6]:
                recruiters.append({
                    "name":   "",
                    "title":  "HR/Recruiter",
                    "email":  email,
                    "source": "google_search",
                })

    except Exception as e:
        print(f"  ! Google search error: {str(e)[:60]}")

    return recruiters


def find_recruiters_on_company_site(page, domain: str) -> list:
    """Scrape company website for HR/recruiter emails."""
    recruiters = []
    urls = [
        f"https://{domain}/careers",
        f"https://{domain}/about",
        f"https://{domain}/contact",
        f"https://www.{domain}/careers",
    ]

    for url in urls:
        try:
            page.goto(url, timeout=15000, wait_until="domcontentloaded")
            page.wait_for_timeout(1500)
            text   = page.inner_text("body")
            emails = extract_emails(text)
            for email in emails[:3]:
                recruiters.append({
                    "name":   "",
                    "title":  "HR Contact",
                    "email":  email,
                    "source": "company_site",
                })
            if recruiters:
                break
        except Exception:
            continue

    return recruiters


def run_recruiter_finder():
    """
    Main function — finds real recruiter contacts for all
    high-score jobs and saves to jobs.json.
    """
    from playwright.sync_api import sync_playwright

    jobs    = load_jobs()
    updated = 0

    # Get jobs that need recruiter finding
    targets = [
        (jid, job) for jid, job in jobs.items()
        if (job.get("fit_score") or 0) >= 80
        and not job.get("email_sent")
        and job.get("recruiter_source") != "linkedin_search"
    ]

    if not targets:
        print("[Recruiter Finder] No new jobs to process")
        return 0

    print(f"[Recruiter Finder] Finding recruiters for {len(targets)} jobs...")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox", "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
            ]
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

        for jid, job in targets[:15]:  # Process max 15 per run
            company = job.get("company", "")
            domain  = company_to_domain(company)

            print(f"\n  [{company}]")

            # Try LinkedIn first
            recruiters = find_recruiters_on_linkedin(page, company, domain)

            # Fall back to company website
            if not recruiters:
                recruiters = find_recruiters_on_company_site(page, domain)

            # Fall back to careers@ guess
            if not recruiters:
                recruiters = [{
                    "name":   "",
                    "title":  "HR Team",
                    "email":  f"careers@{domain}",
                    "source": "pattern_guess",
                }]

            # Save all found recruiters to job
            jobs[jid]["recruiters"]       = recruiters
            jobs[jid]["recruiter_email"]  = recruiters[0]["email"]
            jobs[jid]["recruiter_name"]   = recruiters[0]["name"]
            jobs[jid]["recruiter_source"] = recruiters[0]["source"]

            source = recruiters[0]["source"]
            count  = len(recruiters)
            print(f"  → {count} contact(s) found via {source}")
            for r in recruiters:
                print(f"     • {r['name']} {r['email']}")

            updated += 1
            time.sleep(2)  # Be respectful between requests

        browser.close()

    save_jobs(jobs)
    print(f"\n[Recruiter Finder] Done. {updated} jobs updated.")
    return updated


if __name__ == "__main__":
    run_recruiter_finder()
