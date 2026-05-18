"""
Job Scraper — Multi-source
Sources:
1. Adzuna API         — general job board
2. Remotive API       — remote jobs
3. Jobicy API         — remote tech jobs (free)
4. Arbeitnow API      — remote/EU jobs (free)
5. Apify Google Jobs  — aggregates LinkedIn, Indeed, Glassdoor, company sites
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

ADZUNA_APP_ID  = os.environ.get("ADZUNA_APP_ID", "")
ADZUNA_APP_KEY = os.environ.get("ADZUNA_APP_KEY", "")
APIFY_TOKEN    = os.environ.get("APIFY_API_KEY", "")


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

def new_job(title, company, location, salary, description, url,
            portal, recruiter_email="") -> dict:
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


# ── SOURCE 1: ADZUNA ─────────────────────────────────────────────────────────

def scrape_adzuna(query: str, max_days: int = 3) -> list:
    jobs = []
    if not ADZUNA_APP_ID or not ADZUNA_APP_KEY:
        return jobs
    try:
        url = (
            f"https://api.adzuna.com/v1/api/jobs/us/search/1"
            f"?app_id={ADZUNA_APP_ID}&app_key={ADZUNA_APP_KEY}"
            f"&results_per_page=20&what={quote(query)}"
            f"&content-type=application/json&sort_by=date&max_days_old={max_days}"
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
            jobs.append(new_job(title, company, loc, salary, desc, job_url, "Adzuna"))
        time.sleep(1)
        print(f"  [Adzuna] Found {len(jobs)} jobs for '{query}'")
    except Exception as e:
        print(f"  [Adzuna] Error: {e}")
    return jobs


# ── SOURCE 2: REMOTIVE ───────────────────────────────────────────────────────

def scrape_remotive(query: str) -> list:
    jobs = []
    try:
        url  = (
            f"https://remotive.com/api/remote-jobs"
            f"?search={quote(query)}&category=software-dev&limit=10"
        )
        resp = requests.get(url, timeout=15)
        data = resp.json()
        for item in data.get("jobs", []):
            title   = str(item.get("title", ""))
            company = str(item.get("company_name", ""))
            desc    = BeautifulSoup(
                str(item.get("description", "")), "html.parser"
            ).get_text()[:800]
            jobs.append(new_job(
                title, company, "Remote",
                str(item.get("salary", "Not listed")),
                desc, str(item.get("url", "")), "Remotive",
                str(item.get("company_email", "")),
            ))
        time.sleep(1)
        print(f"  [Remotive] Found {len(jobs)} jobs for '{query}'")
    except Exception as e:
        print(f"  [Remotive] Error: {e}")
    return jobs


# ── SOURCE 3: JOBICY ─────────────────────────────────────────────────────────

def scrape_jobicy(query: str) -> list:
    """Jobicy — free remote tech jobs API."""
    jobs = []
    try:
        url  = f"https://jobicy.com/api/v2/remote-jobs?tag={quote(query)}&count=10"
        resp = requests.get(url, headers=HEADERS, timeout=15)
        data = resp.json()
        for item in data.get("jobs", []):
            title   = str(item.get("jobTitle", ""))
            company = str(item.get("companyName", ""))
            desc    = BeautifulSoup(
                str(item.get("jobDescription", "")), "html.parser"
            ).get_text()[:800]
            job_url = str(item.get("url", ""))
            salary  = str(item.get("annualSalaryMin", "")) or "Not listed"
            jobs.append(new_job(
                title, company, "Remote", salary, desc, job_url, "Jobicy"
            ))
        time.sleep(1)
        print(f"  [Jobicy] Found {len(jobs)} jobs for '{query}'")
    except Exception as e:
        print(f"  [Jobicy] Error: {e}")
    return jobs


# ── SOURCE 4: ARBEITNOW ──────────────────────────────────────────────────────

def scrape_arbeitnow(query: str) -> list:
    """Arbeitnow — free remote job board API."""
    jobs = []
    try:
        url  = f"https://www.arbeitnow.com/api/job-board-api?search={quote(query)}"
        resp = requests.get(url, headers=HEADERS, timeout=15)
        data = resp.json()
        for item in data.get("data", [])[:10]:
            title   = str(item.get("title", ""))
            company = str(item.get("company_name", ""))
            desc    = BeautifulSoup(
                str(item.get("description", "")), "html.parser"
            ).get_text()[:800]
            job_url = str(item.get("url", ""))
            loc     = "Remote" if item.get("remote") else str(item.get("location", "US"))
            jobs.append(new_job(
                title, company, loc, "Not listed", desc, job_url, "Arbeitnow"
            ))
        time.sleep(1)
        print(f"  [Arbeitnow] Found {len(jobs)} jobs for '{query}'")
    except Exception as e:
        print(f"  [Arbeitnow] Error: {e}")
    return jobs


# ── SOURCE 5: APIFY GOOGLE JOBS ──────────────────────────────────────────────

def scrape_google_jobs(query: str) -> list:
    """
    Use Apify Google Jobs scraper.
    Aggregates jobs from LinkedIn, Indeed, Glassdoor, and company sites.
    """
    jobs = []
    if not APIFY_TOKEN:
        return jobs
    try:
        from apify_client import ApifyClient
        apify = ApifyClient(APIFY_TOKEN)

        print(f"  [Google Jobs] Searching: {query}...")
        run = apify.actor("apify/google-jobs-scraper").call(
            run_input={
                "queries":       [f"{query} United States"],
                "maxResults":    20,
                "datePosted":    "past3days",
                "countryCode":   "us",
                "languageCode":  "en",
            },
            timeout_secs=90,
        )

        items = list(apify.dataset(run["defaultDatasetId"]).iterate_items())

        for item in items:
            title   = str(item.get("title", ""))
            company = str(item.get("company", "Unknown"))
            loc     = str(item.get("location", "US"))
            desc    = str(item.get("description", ""))[:800]
            job_url = str(item.get("jobUrl", "") or item.get("url", ""))
            salary  = str(item.get("salary", "Not listed") or "Not listed")
            source  = item.get("via", "Google Jobs")

            if not title or not job_url:
                continue

            jobs.append(new_job(
                title, company, loc, salary, desc, job_url,
                f"Google Jobs ({source})"
            ))

        time.sleep(2)
        print(f"  [Google Jobs] Found {len(jobs)} jobs for '{query}'")

    except Exception as e:
        print(f"  [Google Jobs] Error: {str(e)[:80]}")

    return jobs


# ── MAIN ─────────────────────────────────────────────────────────────────────

def run_scraper() -> int:
    cfg     = json.loads(CONFIG_FILE.read_text())
    queries = cfg.get("job_queries", ["software engineer"])
    jobs    = load_jobs()
    added   = 0

    archive_old_skipped(jobs)

    # Use fewer queries for Google Jobs to save Apify credits
    google_queries = queries[:3]

    for query in queries:
        query = str(query)
        print(f"\n[Scraper] Query: '{query}'")

        # Adzuna — all queries
        for job in scrape_adzuna(query, max_days=3):
            if job["id"] not in jobs:
                jobs[job["id"]] = job
                added += 1
                print(f"  + Adzuna: {job['title']} @ {job['company']}")

        # Remotive — all queries
        for job in scrape_remotive(query):
            if job["id"] not in jobs:
                jobs[job["id"]] = job
                added += 1
                print(f"  + Remotive: {job['title']} @ {job['company']}")

        # Jobicy — all queries
        for job in scrape_jobicy(query):
            if job["id"] not in jobs:
                jobs[job["id"]] = job
                added += 1
                print(f"  + Jobicy: {job['title']} @ {job['company']}")

        # Arbeitnow — all queries
        for job in scrape_arbeitnow(query):
            if job["id"] not in jobs:
                jobs[job["id"]] = job
                added += 1
                print(f"  + Arbeitnow: {job['title']} @ {job['company']}")

    # Google Jobs — top 3 queries only (saves Apify credits)
    print(f"\n[Scraper] Google Jobs search (top {len(google_queries)} queries)...")
    for query in google_queries:
        for job in scrape_google_jobs(str(query)):
            if job["id"] not in jobs:
                jobs[job["id"]] = job
                added += 1
                print(f"  + Google Jobs: {job['title']} @ {job['company']}")

    save_jobs(jobs)
    print(f"\n[Scraper] Done. {added} new jobs added. Total: {len(jobs)}")
    return added


if __name__ == "__main__":
    run_scraper()
