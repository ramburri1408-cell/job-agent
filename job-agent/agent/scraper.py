"""
Universal Job Scraper V4

Sources:
- LinkedIn via Apify REST
- Google portal discovery via Apify REST
- Adzuna
- Remotive

Fixes:
- LinkedIn company extraction
- Google company extraction
- URL-based duplicate IDs
- 24-hour lookback
- Better relevance filtering
"""

import json
import os
import time
import hashlib
import re
import requests
from pathlib import Path
from urllib.parse import quote, urlparse
from datetime import datetime, timezone, timedelta
from bs4 import BeautifulSoup

DATA_FILE = Path("data/jobs.json")
CONFIG_FILE = Path("data/config.json")

APIFY_TOKEN = os.environ.get("APIFY_API_KEY", "").strip()
ADZUNA_APP_ID = os.environ.get("ADZUNA_APP_ID", "").strip()
ADZUNA_APP_KEY = os.environ.get("ADZUNA_APP_KEY", "").strip()

JOB_LOOKBACK_HOURS = int(os.environ.get("JOB_LOOKBACK_HOURS", "24"))
MAX_RESULTS_PER_SOURCE = int(os.environ.get("MAX_RESULTS_PER_SOURCE", "40"))

HEADERS = {
    "User-Agent": "Mozilla/5.0",
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
    "sales",
    "marketing",
    "nurse",
    "driver",
    "retail",
    "accountant",
    "lawyer",
    "teacher",
    "cook",
    "warehouse",
    "mechanic",
    "paid media",
    "copywriter",
    "office assistant",
]

RELEVANT = [
    ".net",
    "c#",
    "asp.net",
    "dotnet",
    "csharp",
    "react",
    "angular",
    "typescript",
    "azure",
    "aws",
    "full stack",
    "fullstack",
    "software engineer",
    "software developer",
    "backend",
    "frontend",
    "api",
    "cloud",
    "devops",
    "microservices",
    "ai",
    "machine learning",
    "automation",
]

NON_US = [
    "germany",
    "deutschland",
    "gmbh",
    "m/w/d",
    "m/f/d",
    "united kingdom",
    "london",
    "uk only",
    "canada only",
    "india only",
    "australia only",
    "paris",
    "berlin",
    "remote eu",
    "remote - eu",
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


def get_nested(d, path, default=""):
    cur = d
    for key in path.split("."):
        if not isinstance(cur, dict):
            return default
        cur = cur.get(key)
    return cur or default


def extract_company(item):
    company = (
        item.get("companyName")
        or item.get("company_name")
        or item.get("company")
        or item.get("companyTitle")
        or get_nested(item, "companyDetails.name")
        or get_nested(item, "companyDetails.companyName")
        or get_nested(item, "companyInfo.name")
        or ""
    )

    if isinstance(company, dict):
        company = (
            company.get("name")
            or company.get("companyName")
            or company.get("title")
            or ""
        )

    return clean(company) or "Unknown"


def infer_company_from_url(url):
    try:
        host = urlparse(url).netloc.lower().replace("www.", "")
        parts = host.split(".")
        if len(parts) >= 2:
            return parts[-2].replace("-", " ").title()
        return host.title()
    except Exception:
        return "Unknown"


def infer_title_company(raw_title, url):
    raw_title = clean(raw_title)

    for sep in [" - ", " | ", " at ", " @ "]:
        if sep in raw_title:
            parts = [clean(p) for p in raw_title.split(sep) if clean(p)]
            if len(parts) >= 2:
                return parts[0], parts[-1]

    return raw_title or "Software Developer", infer_company_from_url(url)


def is_relevant(title, description="", location=""):
    t = clean(title).lower()
    d = clean(description).lower()
    l = clean(location).lower()

    if any(x in f"{t} {d} {l}" for x in NON_US):
        return False

    if any(x in t for x in IRRELEVANT):
        return False

    return any(x in f"{t} {d}" for x in RELEVANT)


def is_portal_url(url):
    url = (url or "").lower()
    return any(site in url for site in PORTAL_SITES)


def new_job(title, company, location, salary, description, url, portal, recruiter_email=""):
    title = clean(title)
    company = clean(company) or "Unknown"
    url = clean(url)

    return {
        "id": make_id(title, company, url),
        "title": title,
        "company": company,
        "location": clean(location) or "United States",
        "salary": clean(salary) or "Not listed",
        "description": clean(description)[:3000],
        "url": url,
        "portal": portal,
        "scraped_at": now_iso(),
        "status": "new",
        "company_domain": "",
        "recruiter_email": recruiter_email,
        "recruiter_name": "",
        "tailored_resume": None,
        "email_draft": None,
        "email_sent": False,
        "email_sent_at": None,
        "fit_score": None,
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


def apify_run_actor(actor_id, run_input):
    if not APIFY_TOKEN:
        return []

    try:
        url = (
            "https://api.apify.com/v2/acts/"
            f"{actor_id.replace('/', '~')}"
            "/run-sync-get-dataset-items"
        )

        res = requests.post(
            url,
            params={"token": APIFY_TOKEN, "timeout": 180},
            json=run_input,
            timeout=240,
        )

        if res.status_code >= 400:
            print(f"  [Apify] Error {res.status_code}: {res.text[:180]}")
            return []

        return res.json()

    except Exception as exc:
        print(f"  [Apify] Error: {str(exc)[:160]}")
        return []


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

    print(f"  [LinkedIn] Searching: {query}")

    items = apify_run_actor(
        "curious_coder/linkedin-jobs-scraper",
        {
            "urls": [build_linkedin_url(query)],
            "count": MAX_RESULTS_PER_SOURCE,
        },
    )

    print(f"  [LinkedIn] Raw: {len(items)}")

    if items:
        print(f"  [LinkedIn] Sample keys: {list(items[0].keys())[:15]}")

    for item in items:
        title = clean(item.get("title") or item.get("jobTitle") or "")
        company = extract_company(item)
        location = clean(item.get("location") or "United States")
        description = clean(item.get("description") or item.get("jobDescription") or "")
        url = clean(item.get("jobUrl") or item.get("url") or item.get("applyUrl") or "")
        salary = clean(item.get("salary") or "Not listed")

        if not title:
            continue

        if not is_relevant(title, description, location):
            continue

        jobs.append(new_job(title, company, location, salary, description, url, "LinkedIn"))

    print(f"  [LinkedIn] Relevant: {len(jobs)}")
    return jobs


def google_queries(query):
    after = (datetime.now(timezone.utc) - timedelta(hours=JOB_LOOKBACK_HOURS)).strftime("%Y-%m-%d")
    base = f'"{query}" software developer job United States after:{after}'

    return [
        f"{base} site:dice.com/job-detail",
        f"{base} site:indeed.com/viewjob",
        f"{base} site:ziprecruiter.com/jobs",
        f"{base} site:monster.com/job-openings",
        f"{base} site:builtin.com/job",
        f"{base} site:greenhouse.io",
        f"{base} site:lever.co",
        f"{base} site:myworkdayjobs.com",
        f"{base} site:icims.com",
        f"{base} site:smartrecruiters.com",
        f"{base} site:ashbyhq.com",
        f"{base} site:jobs.jobvite.com",
    ]


def scrape_google_portals(query):
    jobs = []

    if not APIFY_TOKEN:
        print("  [Google] Missing APIFY_API_KEY")
        return jobs

    for gq in google_queries(query):
        print(f"  [Google] {gq[:95]}...")

        items = apify_run_actor(
            "apify/google-search-scraper",
            {
                "queries": gq,
                "maxPagesPerQuery": 1,
                "resultsPerPage": 10,
                "countryCode": "us",
                "languageCode": "en",
                "mobileResults": False,
            },
        )

        for block in items:
            for result in block.get("organicResults", []) or []:
                url = result.get("url") or result.get("link") or ""
                raw_title = result.get("title") or ""
                desc = result.get("description") or result.get("snippet") or ""

                if not url or not is_portal_url(url):
                    continue

                title, company = infer_title_company(raw_title, url)

                if is_relevant(title, desc, "United States"):
                    jobs.append(
                        new_job(
                            title,
                            company,
                            "United States / Remote",
                            "Not listed",
                            desc,
                            url,
                            "Google",
                        )
                    )

        time.sleep(1)

    print(f"  [Google] Relevant: {len(jobs)}")
    return jobs


def resolve_url(url):
    if not url or not url.startswith("http"):
        return url

    try:
        res = requests.get(
            url,
            headers=HEADERS,
            timeout=10,
            allow_redirects=True,
        )
        return res.url or url
    except Exception:
        return url


def scrape_adzuna(query):
    jobs = []

    if not ADZUNA_APP_ID or not ADZUNA_APP_KEY:
        print("  [Adzuna] Missing credentials")
        return jobs

    try:
        url = (
            "https://api.adzuna.com/v1/api/jobs/us/search/1"
            f"?app_id={ADZUNA_APP_ID}&app_key={ADZUNA_APP_KEY}"
            f"&results_per_page=20&what={quote(query)}"
            "&content-type=application/json&sort_by=date&max_days_old=1"
        )

        data = requests.get(url, headers=HEADERS, timeout=20).json()

        for item in data.get("results", []):
            title = item.get("title", "")
            company = item.get("company", {}).get("display_name", "Unknown")
            location = item.get("location", {}).get("display_name", "US")
            desc = item.get("description", "")
            redirect = item.get("redirect_url", "")

            salary = "Not listed"
            if item.get("salary_min") and item.get("salary_max"):
                salary = f"${int(item['salary_min']):,} - ${int(item['salary_max']):,}"

            if is_relevant(title, desc, location):
                jobs.append(
                    new_job(
                        title,
                        company,
                        location,
                        salary,
                        desc,
                        resolve_url(redirect),
                        "Adzuna",
                    )
                )

        print(f"  [Adzuna] Relevant: {len(jobs)}")

    except Exception as exc:
        print(f"  [Adzuna] Error: {str(exc)[:120]}")

    return jobs


def scrape_remotive(query):
    jobs = []

    try:
        url = (
            "https://remotive.com/api/remote-jobs"
            f"?search={quote(query)}&category=software-dev&limit=20"
        )

        data = requests.get(url, timeout=20).json()

        for item in data.get("jobs", []):
            title = item.get("title", "")
            company = item.get("company_name", "")
            desc = BeautifulSoup(item.get("description", ""), "html.parser").get_text()[:3000]
            job_url = item.get("url", "")
            salary = item.get("salary", "Not listed")

            if is_relevant(title, desc, "Remote United States"):
                jobs.append(
                    new_job(
                        title,
                        company,
                        "Remote / United States",
                        salary,
                        desc,
                        job_url,
                        "Remotive",
                        item.get("company_email", ""),
                    )
                )

        print(f"  [Remotive] Relevant: {len(jobs)}")

    except Exception as exc:
        print(f"  [Remotive] Error: {str(exc)[:120]}")

    return jobs


def run_scraper():
    config = load_config()
    queries = config.get("job_queries", ["software engineer"])

    jobs = load_jobs()
    archive_old_skipped(jobs)

    added = 0
    stats = {
        "LinkedIn": 0,
        "Google": 0,
        "Adzuna": 0,
        "Remotive": 0,
    }

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
            print(f"    URL: {job['url'][:100]}")

    save_jobs(jobs)

    print(f"\n[Scraper] Done. {added} new jobs added. Total: {len(jobs)}")
    print("  Sources: " + " | ".join(f"{k}: {v}" for k, v in stats.items()))

    return added


if __name__ == "__main__":
    run_scraper()
