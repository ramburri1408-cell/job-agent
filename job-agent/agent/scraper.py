"""
Universal Job Scraper V3
Sources:
- LinkedIn via Apify actor
- Google/Apify portal discovery
- Adzuna API
- Remotive API

Goal:
US software/.NET/AI jobs posted in last 24 hours.
"""

import json, os, time, hashlib, re, requests
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import quote, urlparse
from bs4 import BeautifulSoup

DATA_FILE   = Path("data/jobs.json")
CONFIG_FILE = Path("data/config.json")

APIFY_TOKEN    = os.environ.get("APIFY_API_KEY", "")
ADZUNA_APP_ID  = os.environ.get("ADZUNA_APP_ID", "")
ADZUNA_APP_KEY = os.environ.get("ADZUNA_APP_KEY", "")

MAX_RESULTS_PER_SOURCE = int(os.environ.get("MAX_RESULTS_PER_SOURCE", "25"))
HOURS_BACK             = int(os.environ.get("JOB_LOOKBACK_HOURS", "24"))

HEADERS = {
    "User-Agent":      "Mozilla/5.0",
    "Accept-Language": "en-US,en;q=0.9",
}

PORTAL_SITES = [
    "linkedin.com/jobs",
    "dice.com/job-detail",
    "indeed.com/viewjob",
    "ziprecruiter.com/jobs",
    "monster.com/job-openings",
    "builtin.com/job",
    "greenhouse.io",
    "lever.co",
    "myworkdayjobs.com",
    "icims.com",
    "smartrecruiters.com",
    "ashbyhq.com",
    "jobs.jobvite.com",
]

IRRELEVANT = [
    "sales", "marketing", "nurse", "driver", "retail", "accountant",
    "lawyer", "teacher", "cook", "warehouse", "mechanic",
]

RELEVANT = [
    ".net", "c#", "asp.net", "dotnet", "csharp", "react", "angular",
    "typescript", "azure", "full stack", "fullstack", "software engineer",
    "software developer", "backend", "frontend", "python", "node",
    "api", "cloud", "devops", "ai", "machine learning", "automation",
]

NON_US = [
    "germany", "deutschland", "gmbh", "m/w/d", "m/f/d", "united kingdom",
    "london", "uk only", "canada only", "india only", "australia only",
    "paris", "berlin", "remote - eu", "remote eu",
]


def load_jobs():
    return json.loads(DATA_FILE.read_text()) if DATA_FILE.exists() else {}

def save_jobs(jobs):
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    DATA_FILE.write_text(json.dumps(jobs, indent=2))

def load_config():
    return json.loads(CONFIG_FILE.read_text()) if CONFIG_FILE.exists() else {}

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def clean(text):
    return re.sub(r"\s+", " ", str(text or "")).strip()

def make_id(title, company, url=""):
    raw = f"{title.lower().strip()}-{company.lower().strip()}-{url.lower().strip()}"
    return hashlib.md5(raw.encode()).hexdigest()[:12]

def infer_company_from_url(url):
    try:
        host  = urlparse(url).netloc.lower().replace("www.", "")
        parts = host.split(".")
        return parts[-2].replace("-", " ").title() if len(parts) >= 2 else host.title()
    except Exception:
        return "Unknown"

def infer_title_company(title, url):
    title = clean(title)
    for sep in [" - ", " | ", " at ", " @ "]:
        if sep in title:
            parts = [clean(p) for p in title.split(sep) if clean(p)]
            if len(parts) >= 2:
                return parts[0], parts[-1]
    return title or "Software Developer", infer_company_from_url(url)

def is_relevant(title, description, location):
    t = clean(title).lower()
    d = clean(description).lower()
    l = clean(location).lower()
    if any(x in l or x in d or x in t for x in NON_US):
        return False
    if any(x in t for x in IRRELEVANT):
        return False
    combined = f"{t} {d}"
    return any(x in combined for x in RELEVANT)

def new_job(title, company, location, salary, description,
            url, portal, recruiter_email=""):
    return {
        "id":              make_id(title, company, url),
        "title":           clean(title),
        "company":         clean(company),
        "location":        clean(location) or "United States",
        "salary":          clean(salary) or "Not listed",
        "description":     clean(description),
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

def archive_old_skipped(jobs, days=3):
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    for job in jobs.values():
        if job.get("status") in {"skipped_low_score", "skipped_irrelevant", "no_email"}:
            try:
                if datetime.fromisoformat(job.get("scraped_at", "")) < cutoff:
                    job["status"] = "archived"
            except Exception:
                pass

def resolve_url(url):
    if not url or not url.startswith("http"):
        return url
    try:
        r = requests.get(url, headers=HEADERS, timeout=10, allow_redirects=True)
        return r.url or url
    except Exception:
        return url


# ── LINKEDIN ──────────────────────────────────────────────────────────────────

def build_linkedin_url(query):
    return (
        "https://www.linkedin.com/jobs/search/"
        f"?keywords={quote(query)}"
        "&location=United%20States"
        "&f_TPR=r86400"
        "&f_JT=F%2CC"
        "&sortBy=DD"
    )

def scrape_linkedin(query):
    jobs = []
    if not APIFY_TOKEN:
        print("  [LinkedIn] Missing APIFY_API_KEY")
        return jobs
    try:
        from apify_client import ApifyClient
        apify = ApifyClient(APIFY_TOKEN)
        print(f"  [LinkedIn] Searching: {query}")

        run = apify.actor("curious_coder/linkedin-jobs-scraper").call(
            run_input={
                "urls":  [build_linkedin_url(query)],
                "count": MAX_RESULTS_PER_SOURCE,
            }
        )

        items = list(apify.dataset(run["defaultDatasetId"]).iterate_items())
        print(f"  [LinkedIn] Raw: {len(items)}")

        for item in items:
            title    = item.get("title") or item.get("jobTitle") or ""
            company  = item.get("company") or item.get("companyName") or "Unknown"
            location = item.get("location") or "United States"
            desc     = (item.get("description") or item.get("jobDescription") or "")[:1500]
            url      = item.get("jobUrl") or item.get("url") or item.get("applyUrl") or ""
            salary   = item.get("salary") or "Not listed"

            if title and company and is_relevant(title, desc, location):
                jobs.append(new_job(title, company, location, salary, desc, url, "LinkedIn"))

        print(f"  [LinkedIn] Relevant: {len(jobs)}")

    except Exception as e:
        print(f"  [LinkedIn] Error: {str(e)[:160]}")

    return jobs


# ── GOOGLE PORTAL DISCOVERY ───────────────────────────────────────────────────

def google_queries(query):
    after = (datetime.now(timezone.utc) - timedelta(hours=HOURS_BACK)).strftime("%Y-%m-%d")
    base  = f'"{query}" software developer job United States after:{after}'
    return [
        f'{base} site:dice.com/job-detail',
        f'{base} site:indeed.com/viewjob',
        f'{base} site:ziprecruiter.com/jobs',
        f'{base} site:greenhouse.io',
        f'{base} site:lever.co',
        f'{base} site:myworkdayjobs.com',
        f'{base} site:icims.com',
        f'{base} site:smartrecruiters.com',
        f'{base} site:ashbyhq.com',
    ]

def is_portal_url(url):
    u = (url or "").lower()
    return any(site in u for site in PORTAL_SITES)

def scrape_google_portals(query):
    jobs = []
    if not APIFY_TOKEN:
        return jobs
    try:
        from apify_client import ApifyClient
        apify = ApifyClient(APIFY_TOKEN)

        for gq in google_queries(query):
            print(f"  [Google] {gq[:90]}...")

            run = apify.actor("apify/google-search-scraper").call(
                run_input={
                    "queries":          gq,
                    "maxPagesPerQuery": 1,
                    "resultsPerPage":   10,
                    "countryCode":      "us",
                    "languageCode":     "en",
                    "mobileResults":    False,
                }
            )

            dataset_id = run.get("defaultDatasetId")
            if not dataset_id:
                continue

            for item in apify.dataset(dataset_id).iterate_items():
                for result in item.get("organicResults", []) or []:
                    url       = result.get("url") or result.get("link") or ""
                    title_raw = result.get("title") or ""
                    desc      = result.get("description") or result.get("snippet") or ""

                    if not url or not is_portal_url(url):
                        continue

                    title, company = infer_title_company(title_raw, url)
                    location       = "United States / Remote"

                    if is_relevant(title, desc, location):
                        jobs.append(
                            new_job(title, company, location,
                                    "Not listed", desc, url, "Google")
                        )

            time.sleep(1.5)

        print(f"  [Google] Relevant: {len(jobs)}")

    except Exception as e:
        print(f"  [Google] Error: {str(e)[:160]}")

    return jobs


# ── ADZUNA ────────────────────────────────────────────────────────────────────

def scrape_adzuna(query):
    jobs = []
    if not ADZUNA_APP_ID or not ADZUNA_APP_KEY:
        return jobs
    try:
        url  = (
            "https://api.adzuna.com/v1/api/jobs/us/search/1"
            f"?app_id={ADZUNA_APP_ID}&app_key={ADZUNA_APP_KEY}"
            f"&results_per_page=20&what={quote(query)}"
            "&content-type=application/json&sort_by=date&max_days_old=1"
        )
        data = requests.get(url, headers=HEADERS, timeout=15).json()

        for item in data.get("results", []):
            title    = item.get("title", "")
            company  = item.get("company", {}).get("display_name", "Unknown")
            location = item.get("location", {}).get("display_name", "US")
            desc     = item.get("description", "")
            redirect = item.get("redirect_url", "")
            salary   = "Not listed"
            if item.get("salary_min") and item.get("salary_max"):
                salary = f"${int(item['salary_min']):,} - ${int(item['salary_max']):,}"

            if is_relevant(title, desc, location):
                jobs.append(
                    new_job(title, company, location, salary,
                            desc, resolve_url(redirect), "Adzuna")
                )

        print(f"  [Adzuna] Relevant: {len(jobs)}")

    except Exception as e:
        print(f"  [Adzuna] Error: {str(e)[:120]}")

    return jobs


# ── REMOTIVE ──────────────────────────────────────────────────────────────────

def scrape_remotive(query):
    jobs = []
    try:
        url  = (
            "https://remotive.com/api/remote-jobs"
            f"?search={quote(query)}&category=software-dev&limit=20"
        )
        data = requests.get(url, timeout=15).json()

        for item in data.get("jobs", []):
            title   = item.get("title", "")
            company = item.get("company_name", "")
            desc    = BeautifulSoup(
                item.get("description", ""), "html.parser"
            ).get_text()[:1500]
            job_url = item.get("url", "")
            salary  = item.get("salary", "Not listed")

            if is_relevant(title, desc, "Remote United States"):
                jobs.append(
                    new_job(title, company, "Remote / United States",
                            salary, desc, job_url, "Remotive",
                            item.get("company_email", ""))
                )

        print(f"  [Remotive] Relevant: {len(jobs)}")

    except Exception as e:
        print(f"  [Remotive] Error: {str(e)[:120]}")

    return jobs


# ── MAIN ──────────────────────────────────────────────────────────────────────

def run_scraper():
    config  = load_config()
    queries = config.get("job_queries", ["software engineer"])
    jobs    = load_jobs()

    archive_old_skipped(jobs)

    added = 0
    stats = {"LinkedIn": 0, "Google": 0, "Adzuna": 0, "Remotive": 0}

    for query in queries:
        query = str(query)
        print(f"\n[Scraper] Query: {query}")

        collected = []
        collected.extend(scrape_linkedin(query))
        collected.extend(scrape_google_portals(query))
        collected.extend(scrape_adzuna(query))
        collected.extend(scrape_remotive(query))

        for job in collected:
            if job["id"] in jobs:
                continue
            jobs[job["id"]] = job
            added += 1
            stats[job["portal"]] = stats.get(job["portal"], 0) + 1
            print(f"  + {job['portal']}: {job['title']} @ {job['company']}")

    save_jobs(jobs)
    print(f"\n[Scraper] Done. {added} new jobs added. Total: {len(jobs)}")
    print("  Sources: " + " | ".join(f"{k}: {v}" for k, v in stats.items()))
    return added


if __name__ == "__main__":
    run_scraper()
