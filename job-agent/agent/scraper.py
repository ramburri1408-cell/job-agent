"""
Production Job Scraper
Sources:
- LinkedIn (Apify)
- Google Jobs
- Adzuna
- Remotive

Filters:
- US only
- Recent jobs
- Software engineering focused
- Duplicate prevention
"""

import json
import os
import time
import hashlib
import requests

from pathlib import Path
from urllib.parse import quote
from datetime import datetime, timezone, timedelta

# ============================================================
# CONFIG
# ============================================================

DATA_FILE = Path("data/jobs.json")
CONFIG_FILE = Path("data/config.json")

APIFY_TOKEN = os.getenv("APIFY_API_KEY", "")
ADZUNA_APP_ID = os.getenv("ADZUNA_APP_ID", "")
ADZUNA_APP_KEY = os.getenv("ADZUNA_APP_KEY", "")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    )
}

RELEVANT_KEYWORDS = [
    ".net",
    "c#",
    "asp.net",
    "react",
    "angular",
    "software engineer",
    "software developer",
    "full stack",
    "backend",
    "frontend",
    "azure",
    "aws",
    "cloud",
    "api",
    "microservices",
]

BAD_KEYWORDS = [
    "sales",
    "marketing",
    "teacher",
    "nurse",
    "driver",
    "recruiter",
]

NON_US_MARKERS = [
    "germany",
    "uk",
    "india",
    "canada only",
    "europe",
    "remote-eu",
]

# ============================================================
# HELPERS
# ============================================================

def load_jobs():
    if DATA_FILE.exists():
        return json.loads(DATA_FILE.read_text())

    return {}


def save_jobs(jobs):
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    DATA_FILE.write_text(json.dumps(jobs, indent=2))


def make_id(title, company):
    raw = f"{title.lower()}-{company.lower()}"
    return hashlib.md5(raw.encode()).hexdigest()[:12]


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def is_relevant(title, desc="", location=""):
    text = f"{title} {desc} {location}".lower()

    if any(x in text for x in BAD_KEYWORDS):
        return False

    if any(x in text for x in NON_US_MARKERS):
        return False

    return any(x in text for x in RELEVANT_KEYWORDS)


def create_job(
    title,
    company,
    location,
    salary,
    description,
    url,
    source,
):
    return {
        "id": make_id(title, company),
        "title": title,
        "company": company,
        "location": location,
        "salary": salary,
        "description": description[:3000],
        "url": url,
        "portal": source,
        "scraped_at": now_iso(),
        "status": "new",
        "fit_score": None,
        "email_sent": False,
        "tailored_resume": None,
        "email_draft": None,
        "recruiter_email": "",
    }


# ============================================================
# APIFY REST
# ============================================================

def apify_run_actor(actor_id, run_input):
    try:
        url = (
            f"https://api.apify.com/v2/acts/"
            f"{actor_id.replace('/', '~')}"
            f"/run-sync-get-dataset-items"
        )

        params = {
            "token": APIFY_TOKEN,
            "timeout": 180,
        }

        res = requests.post(
            url,
            params=params,
            json=run_input,
            timeout=240,
        )

        if res.status_code >= 400:
            print(f"  [Apify] Error {res.status_code}")
            return []

        return res.json()

    except Exception as e:
        print(f"  [Apify] {e}")
        return []


# ============================================================
# LINKEDIN
# ============================================================

def linkedin_url(query):
    encoded = quote(query)

    return (
        "https://www.linkedin.com/jobs/search/"
        f"?keywords={encoded}"
        "&location=United%20States"
        "&f_TPR=r86400"
        "&sortBy=DD"
    )


def scrape_linkedin(query):
    jobs = []

    if not APIFY_TOKEN:
        return jobs

    try:
        print(f"  [LinkedIn] Searching: {query}")

        items = apify_run_actor(
            "curious_coder/linkedin-jobs-scraper",
            {
                "urls": [linkedin_url(query)],
                "count": 40,
            },
        )

        print(f"  [LinkedIn] Raw: {len(items)}")

        for item in items:
            title = str(item.get("title", ""))
            company = str(item.get("company", "Unknown"))
            location = str(item.get("location", "US"))

            description = str(
                item.get("description", "")
            )

            url = str(
                item.get("jobUrl")
                or item.get("url")
                or ""
            )

            salary = str(item.get("salary", "Not listed"))

            if not title:
                continue

            if not is_relevant(title, description, location):
                continue

            jobs.append(
                create_job(
                    title,
                    company,
                    location,
                    salary,
                    description,
                    url,
                    "LinkedIn",
                )
            )

        print(f"  [LinkedIn] Relevant: {len(jobs)}")

    except Exception as e:
        print(f"  [LinkedIn] Error: {e}")

    return jobs


# ============================================================
# GOOGLE JOBS
# ============================================================

def scrape_google(query):
    jobs = []

    if not APIFY_TOKEN:
        return jobs

    try:
        search = (
            f'"{query}" software engineer job '
            f'United States after:2026-05-19'
        )

        print(f"  [Google] {search[:80]}...")

        items = apify_run_actor(
            "apify/google-search-scraper",
            {
                "queries": search,
                "maxPagesPerQuery": 1,
                "resultsPerPage": 10,
                "countryCode": "us",
                "languageCode": "en",
            },
        )

        for block in items:

            results = block.get("organicResults", [])

            for result in results:

                title = result.get("title", "")
                url = result.get("url", "")
                desc = result.get("description", "")

                if not is_relevant(title, desc):
                    continue

                company = "Unknown"

                jobs.append(
                    create_job(
                        title,
                        company,
                        "United States",
                        "Not listed",
                        desc,
                        url,
                        "Google",
                    )
                )

        print(f"  [Google] Relevant: {len(jobs)}")

    except Exception as e:
        print(f"  [Google] Error: {e}")

    return jobs


# ============================================================
# ADZUNA
# ============================================================

def scrape_adzuna(query):
    jobs = []

    if not ADZUNA_APP_ID:
        return jobs

    try:
        url = (
            "https://api.adzuna.com/v1/api/jobs/us/search/1"
            f"?app_id={ADZUNA_APP_ID}"
            f"&app_key={ADZUNA_APP_KEY}"
            f"&results_per_page=20"
            f"&what={quote(query)}"
            "&sort_by=date"
            "&max_days_old=1"
        )

        r = requests.get(url, timeout=20)
        data = r.json()

        for item in data.get("results", []):

            title = item.get("title", "")
            company = item.get(
                "company",
                {}
            ).get("display_name", "Unknown")

            location = item.get(
                "location",
                {}
            ).get("display_name", "US")

            desc = item.get("description", "")
            job_url = item.get("redirect_url", "")

            if not is_relevant(title, desc, location):
                continue

            jobs.append(
                create_job(
                    title,
                    company,
                    location,
                    "Not listed",
                    desc,
                    job_url,
                    "Adzuna",
                )
            )

        print(f"  [Adzuna] Relevant: {len(jobs)}")

    except Exception as e:
        print(f"  [Adzuna] Error: {e}")

    return jobs


# ============================================================
# REMOTIVE
# ============================================================

def scrape_remotive():
    jobs = []

    try:
        r = requests.get(
            "https://remotive.com/api/remote-jobs",
            timeout=20,
        )

        data = r.json()

        for item in data.get("jobs", []):

            title = item.get("title", "")
            company = item.get("company_name", "")
            desc = item.get("description", "")
            url = item.get("url", "")

            if not is_relevant(title, desc):
                continue

            jobs.append(
                create_job(
                    title,
                    company,
                    "Remote",
                    "Not listed",
                    desc,
                    url,
                    "Remotive",
                )
            )

        print(f"  [Remotive] Relevant: {len(jobs)}")

    except Exception as e:
        print(f"  [Remotive] Error: {e}")

    return jobs


# ============================================================
# MAIN
# ============================================================

def run_scraper():

    cfg = json.loads(CONFIG_FILE.read_text())

    queries = cfg.get(
        "job_queries",
        ["software engineer"]
    )

    jobs = load_jobs()

    added = 0

    stats = {
        "LinkedIn": 0,
        "Google": 0,
        "Adzuna": 0,
        "Remotive": 0,
    }

    for query in queries:

        print(f"\n[Scraper] Query: {query}")

        all_jobs = []

        all_jobs.extend(scrape_linkedin(query))
        all_jobs.extend(scrape_google(query))
        all_jobs.extend(scrape_adzuna(query))

        if query == queries[0]:
            all_jobs.extend(scrape_remotive())

        for job in all_jobs:

            if job["id"] in jobs:
                continue

            jobs[job["id"]] = job

            added += 1

            stats[job["portal"]] += 1

            print(
                f"  + {job['portal']}: "
                f"{job['title']} @ {job['company']}"
            )

    save_jobs(jobs)

    print("\n[Scraper] COMPLETE")
    print(f"  Added: {added}")
    print(f"  Total: {len(jobs)}")

    print(
        f"  LinkedIn: {stats['LinkedIn']} | "
        f"Google: {stats['Google']} | "
        f"Adzuna: {stats['Adzuna']} | "
        f"Remotive: {stats['Remotive']}"
    )

    return added


if __name__ == "__main__":
    run_scraper()
