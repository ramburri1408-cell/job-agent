"""
Job Scraper — LinkedIn via Apify
Scrapes LinkedIn Jobs for .NET/full-stack positions in the US.
Uses curious_coder/linkedin-jobs-scraper actor.
Pre-filters irrelevant and non-US jobs before AI scoring.
"""

import json, os, time, hashlib, requests
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import quote
from bs4 import BeautifulSoup

DATA_FILE   = Path("data/jobs.json")
CONFIG_FILE = Path("data/config.json")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

APIFY_TOKEN    = os.environ.get("APIFY_API_KEY", "")
ADZUNA_APP_ID  = os.environ.get("ADZUNA_APP_ID", "")
ADZUNA_APP_KEY = os.environ.get("ADZUNA_APP_KEY", "")

IRRELEVANT_KEYWORDS = [
    "sales", "marketing", "nurse", "driver", "retail manager",
    "accountant", "lawyer", "teacher", "cook", "electrician",
    "plumber", "mechanic", "warehouse", "social media",
]

RELEVANT_KEYWORDS = [
    ".net", "c#", "asp.net", "dotnet", "csharp", "react",
    "angular", "typescript", "azure", "full stack", "fullstack",
    "software engineer", "software developer", "backend",
    "frontend", "python", "node", "api", "cloud", "devops",
    "ai", "machine learning", "automation",
]

NON_US_MARKERS = [
    "germany", "deutschland", "gmbh", "m/w/d", "m/f/d",
    "united kingdom", "london", "uk only", "canada only",
    "india only", "australia only", "paris", "berlin",
    "münchen", "amsterdam", "remote - eu", "remote eu",
]


def load_jobs() -> dict:
    return json.loads(DATA_FILE.read_text()) if DATA_FILE.exists() else {}

def save_jobs(jobs: dict) -> None:
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    DATA_FILE.write_text(json.dumps(jobs, indent=2))

def make_id(title: str, company: str) -> str:
    raw = f"{title.lower().strip()}-{company.lower().strip()}"
    return hashlib.md5(raw.encode()).hexdigest()[:12]

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def is_relevant(title: str, description: str, location: str) -> bool:
    title_lower = title.lower()
    desc_lower  = (description or "").lower()
    loc_lower   = (location or "").lower()
    if any(k in loc_lower or k in desc_lower for k in NON_US_MARKERS):
        return False
    if any(k in title_lower for k in IRRELEVANT_KEYWORDS):
        return False
    combined = f"{title_lower} {desc_lower}"
    return any(k in combined for k in RELEVANT_KEYWORDS)

def new_job(title, company, location, salary, description,
            url, portal, recruiter_email="") -> dict:
    return {
        "id":              make_id(title, company),
        "title":           title,
        "company":         company,
        "location":        location,
        "salary":          salary,
        "description":     description,
        "url":             url,
        "portal":          portal,
        "scraped_at":      now_iso(),
        "status":          "new",
        "recruiter_email": recruiter_email,
        "recruiter_name":  "",
        "tailored_resume": None,
        "email_draft":     None,
        "email_sent":      False,
        "email_sent_at":   None,
        "fit_score":       None,
    }

def archive_old_skipped(jobs: dict, days: int = 3) -> None:
    cutoff        = datetime.now(timezone.utc) - timedelta(days=days)
    skip_statuses = {"skipped_low_score", "skipped_irrelevant", "no_email"}
    for job in jobs.values():
        if job.get("status") in skip_statuses:
            try:
                scraped_dt = datetime.fromisoformat(job.get("scraped_at", ""))
                if scraped_dt < cutoff:
                    job["status"] = "archived"
            except Exception:
                pass


# ── SOURCE 1: LINKEDIN VIA APIFY ─────────────────────────────────────────────

def scrape_linkedin(query: str) -> list:
    """
    Scrape LinkedIn Jobs via Apify curious_coder/linkedin-jobs-scraper.
    No cookies required — uses public LinkedIn job listings.
    """
    jobs = []
    if not APIFY_TOKEN:
        print("  [LinkedIn] No Apify token — skipping")
        return jobs
    try:
        from apify_client import ApifyClient
        apify = ApifyClient(APIFY_TOKEN)

        print(f"  [LinkedIn] Searching: '{query}'...")

        run = apify.actor("curious_coder/linkedin-jobs-scraper").call(
            run_input={
                "keyword":    query,
                "location":   "United States",
                "count":      25,
                "datePosted": "r604800",  # past week in seconds
            },
        )

        items = list(apify.dataset(run["defaultDatasetId"]).iterate_items())
        print(f"  [LinkedIn] Raw: {len(items)} results")

        for item in items:
            title   = str(item.get("title", "") or item.get("jobTitle", ""))
            company = str(item.get("company", "") or item.get("companyName", "Unknown"))
            loc     = str(item.get("location", "United States"))
            desc    = str(item.get("description", "") or
                         item.get("jobDescription", ""))[:1000]
            job_url = str(item.get("jobUrl", "") or
                         item.get("url", "") or
                         item.get("applyUrl", ""))
            salary  = str(item.get("salary", "") or "Not listed")

            if not title or not company:
                continue
            if not is_relevant(title, desc, loc):
                continue

            jobs.append(new_job(
                title, company, loc, salary,
                desc, job_url, "LinkedIn"
            ))

        time.sleep(2)
        print(f"  [LinkedIn] {len(jobs)} relevant jobs for '{query}'")

    except Exception as e:
        print(f"  [LinkedIn] Error: {str(e)[:100]}")

    return jobs


# ── SOURCE 2: ADZUNA (fallback) ───────────────────────────────────────────────

def scrape_adzuna(query: str, max_days: int = 3) -> list:
    """Adzuna API as fallback if LinkedIn has issues."""
    jobs = []
    if not ADZUNA_APP_ID or not ADZUNA_APP_KEY:
        return jobs
    try:
        url = (
            f"https://api.adzuna.com/v1/api/jobs/us/search/1"
            f"?app_id={ADZUNA_APP_ID}&app_key={ADZUNA_APP_KEY}"
            f"&results_per_page=20&what={quote(query)}"
            f"&content-type=application/json&sort_by=date"
            f"&max_days_old={max_days}"
        )
        resp = requests.get(url, headers=HEADERS, timeout=15)
        data = resp.json()
        for item in data.get("results", []):
            title   = str(item.get("title", ""))
            company = str(item.get("company", {}).get("display_name", "Unknown"))
            loc     = str(item.get("location", {}).get("display_name", "US"))
            sm      = item.get("salary_min")
            sx      = item.get("salary_max")
            salary  = f"${int(sm):,} - ${int(sx):,}" if sm and sx else "Not listed"
            desc    = str(item.get("description", ""))
            job_url = str(item.get("redirect_url", ""))
            if not is_relevant(title, desc, loc):
                continue
            jobs.append(new_job(title, company, loc, salary, desc, job_url, "Adzuna"))
        time.sleep(1)
        print(f"  [Adzuna] {len(jobs)} relevant jobs for '{query}'")
    except Exception as e:
        print(f"  [Adzuna] Error: {e}")
    return jobs


# ── MAIN ─────────────────────────────────────────────────────────────────────

def run_scraper() -> int:
    cfg     = json.loads(CONFIG_FILE.read_text())
    queries = cfg.get("job_queries", ["software engineer"])
    jobs    = load_jobs()
    added   = 0

    archive_old_skipped(jobs)

    stats = {"LinkedIn": 0, "Adzuna": 0}

    for query in queries:
        query = str(query)
        print(f"\n[Scraper] Query: '{query}'")

        # Primary: LinkedIn
        for job in scrape_linkedin(query):
            if job["id"] not in jobs:
                jobs[job["id"]] = job
                added += 1
                stats["LinkedIn"] += 1
                print(f"  + LinkedIn: {job['title']} @ {job['company']}")

        # Fallback: Adzuna
        for job in scrape_adzuna(query, max_days=3):
            if job["id"] not in jobs:
                jobs[job["id"]] = job
                added += 1
                stats["Adzuna"] += 1
                print(f"  + Adzuna: {job['title']} @ {job['company']}")

    save_jobs(jobs)
    print(f"\n[Scraper] Done. {added} new jobs added. Total: {len(jobs)}")
    print(f"  Sources: LinkedIn: {stats['LinkedIn']} | Adzuna: {stats['Adzuna']}")
    return added


if __name__ == "__main__":
    run_scraper()
