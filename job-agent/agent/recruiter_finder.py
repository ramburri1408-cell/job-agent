"""
Recruiter Finder — Uses Apify directly to find real recruiter emails
Flow:
1. Take job URL + company name
2. Apify scrapes company website for contact/team page emails
3. Apify scrapes job posting page for recruiter email
4. Falls back to pattern guess if nothing found
"""

import os, json, re
from pathlib import Path
from apify_client import ApifyClient
import anthropic

client_ai   = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
apify_token = os.environ.get("APIFY_API_KEY", "")
DATA_FILE   = Path("data/jobs.json")


def load_jobs():
    return json.loads(DATA_FILE.read_text()) if DATA_FILE.exists() else {}

def save_jobs(jobs):
    DATA_FILE.write_text(json.dumps(jobs, indent=2))


def scrape_page_for_email(url: str) -> dict:
    """Use Apify website-content-crawler to scrape page and extract emails."""
    if not url or not apify_token:
        return {}
    try:
        apify = ApifyClient(apify_token)
        run   = apify.actor("apify/website-content-crawler").call(
            run_input={
                "startUrls":        [{"url": url}],
                "maxCrawlPages":    3,
                "maxCrawlDepth":    1,
                "includeUrlGlobs":  [],
            }
        )
        # Get scraped text
        items = list(apify.dataset(run["defaultDatasetId"]).iterate_items())
        if not items:
            return {}

        full_text = " ".join(item.get("text", "") for item in items)

        # Extract emails from scraped text
        emails = re.findall(r'[\w.+-]+@[\w-]+\.[a-zA-Z]{2,}', full_text)
        # Filter out generic/noreply emails
        skip = ["noreply", "no-reply", "support", "info", "help", "privacy", "legal", "press"]
        real_emails = [e for e in emails if not any(s in e.lower() for s in skip)]

        if not real_emails:
            return {}

        # Use Claude to pick the best recruiter email from the list
        result = client_ai.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=200,
            system="Pick the most likely recruiter/HR/talent email from this list. Return ONLY JSON: {\"email\": \"best@email.com\", \"name\": \"if found else empty\"}",
            messages=[{"role": "user", "content": f"Emails found: {real_emails[:20]}\nFull text snippet: {full_text[:500]}"}]
        ).content[0].text.strip()

        start = result.find("{")
        end   = result.rfind("}") + 1
        if start >= 0 and end > start:
            data = json.loads(result[start:end])
            if data.get("email") and "@" in data["email"]:
                return {"email": data["email"], "name": data.get("name", ""), "source": "apify_scrape"}

    except Exception as e:
        print(f"  ! Apify scrape error: {str(e)[:80]}")

    return {}


def find_recruiter_email(job: dict) -> dict:
    """
    Try multiple sources to find real recruiter email.
    1. Scrape job posting URL
    2. Scrape company careers page
    3. Scrape company about/team page
    4. Fall back to pattern guess
    """
    company = job.get("company", "")
    url     = job.get("url", "")
    domain  = company_to_domain(company)

    print(f"  → Finding recruiter: {job.get('title')} @ {company}")

    # 1. Scrape the job posting page itself
    if url and url.startswith("http"):
        result = scrape_page_for_email(url)
        if result.get("email"):
            print(f"  ✓ Found on job page: {result['email']}")
            return result

    # 2. Scrape company careers page
    careers_url = f"https://{domain}/careers"
    result = scrape_page_for_email(careers_url)
    if result.get("email"):
        print(f"  ✓ Found on careers page: {result['email']}")
        return result

    # 3. Scrape company about/contact page
    about_url = f"https://{domain}/about"
    result = scrape_page_for_email(about_url)
    if result.get("email"):
        print(f"  ✓ Found on about page: {result['email']}")
        return result

    # 4. Fall back to pattern guess
    print(f"  ! No email found, using pattern guess")
    return guess_email(company)


def guess_email(company: str, name: str = "") -> dict:
    """Fallback — common HR email patterns."""
    domain = company_to_domain(company)
    return {
        "name":   name,
        "email":  f"careers@{domain}",
        "source": "pattern_guess",
    }


def company_to_domain(company: str) -> str:
    """Convert company name to likely domain."""
    clean = company.lower()
    clean = re.sub(r'\s*\b(inc|llc|ltd|corp|co|company|technologies|tech|solutions|services|group|global|systems|consulting|staffing|professionals)\b\s*', ' ', clean)
    clean = re.sub(r'[^a-z0-9\s]', '', clean)
    clean = clean.strip().replace(' ', '')
    if not clean:
        clean = re.sub(r'[^a-z0-9]', '', company.lower())
    return f"{clean}.com"


def run_recruiter_finder():
    """Find recruiter emails for all high-score uncontacted jobs."""
    jobs    = load_jobs()
    updated = 0

    for jid, job in jobs.items():
        # Skip already found via real scraping
        if job.get("recruiter_source") == "apify_scrape":
            continue
        # Only process high-score jobs not yet emailed
        score = job.get("fit_score")
        if not score or score < 80:
            continue
        if job.get("email_sent"):
            continue

        result = find_recruiter_email(job)

        if result.get("email"):
            jobs[jid]["recruiter_email"]  = result["email"]
            jobs[jid]["recruiter_name"]   = result.get("name", "")
            jobs[jid]["recruiter_source"] = result.get("source", "unknown")
            updated += 1

    save_jobs(jobs)
    print(f"\n[Recruiter Finder] Done. {updated} contacts updated.")
    return updated


if __name__ == "__main__":
    run_recruiter_finder()
