import json, os, time, hashlib
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

DATA_FILE = Path("data/jobs.json")
DATA_FILE.parent.mkdir(exist_ok=True)

ADZUNA_APP_ID  = os.environ.get("ADZUNA_APP_ID", "")
ADZUNA_APP_KEY = os.environ.get("ADZUNA_APP_KEY", "")

def load_jobs():
    if DATA_FILE.exists():
        return json.loads(DATA_FILE.read_text())
    return {}

def save_jobs(jobs):
    DATA_FILE.write_text(json.dumps(jobs, indent=2))

def make_id(title, company):
    raw = f"{title.lower().strip()}-{company.lower().strip()}"
    return hashlib.md5(raw.encode()).hexdigest()[:12]

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def new_job(title, company, location, salary, description, url, portal, recruiter_email=""):
    return {
        "id": make_id(title, company),
        "title": title,
        "company": company,
        "location": location,
        "salary": salary,
        "description": description,
        "url": url,
        "portal": portal,
        "scraped_at": now_iso(),
        "status": "new",
        "recruiter_email": recruiter_email,
        "recruiter_name": "",
        "tailored_resume": None,
        "email_draft": None,
        "email_sent": False,
        "email_sent_at": None,
        "fit_score": None,
    }

def scrape_adzuna(query, max_results=20):
    jobs = []
    if not ADZUNA_APP_ID or not ADZUNA_APP_KEY:
        print("[Adzuna] Missing API credentials, skipping.")
        return jobs
    try:
        url = (
            f"https://api.adzuna.com/v1/api/jobs/us/search/1"
            f"?app_id={ADZUNA_APP_ID}"
            f"&app_key={ADZUNA_APP_KEY}"
            f"&results_per_page={max_results}"
            f"&what={quote(str(query))}"
            f"&content-type=application/json"
            f"&sort_by=date"
            f"&max_days_old=1"
        )
        resp = requests.get(url, headers=HEADERS, timeout=15)
        data = resp.json()
        for item in data.get("results", []):
            title    = str(item.get("title", ""))
            company  = str(item.get("company", {}).get("display_name", "Unknown"))
            loc      = str(item.get("location", {}).get("display_name", "US"))
            sal_min  = item.get("salary_min")
            sal_max  = item.get("salary_max")
            salary   = f"${int(sal_min):,} - ${int(sal_max):,}" if sal_min and sal_max else "Not listed"
            desc     = str(item.get("description", ""))
            job_url  = str(item.get("redirect_url", ""))
            portal   = "Adzuna"
            adref    = item.get("adref", "").lower()
            if "indeed"  in adref: portal = "Indeed (via Adzuna)"
            elif "monster" in adref: portal = "Monster (via Adzuna)"
            elif "zip"   in adref: portal = "ZipRecruiter (via Adzuna)"
            elif "career" in adref: portal = "CareerBuilder (via Adzuna)"
            jobs.append(new_job(title, company, loc, salary, desc, job_url, portal))
        time.sleep(1)
        print(f"  [Adzuna] Found {len(jobs)} jobs for '{query}'")
    except Exception as e:
        print(f"  [Adzuna] Error: {e}")
    return jobs

def scrape_remotive(query):
    jobs = []
    try:
        url = f"https://remotive.com/api/remote-jobs?search={quote(str(query))}&category=software-dev&limit=10"
        resp = requests.get(url, timeout=15)
        data = resp.json()
        for item in data.get("jobs", []):
            title   = str(item.get("title", ""))
            company = str(item.get("company_name", ""))
            desc    = BeautifulSoup(str(item.get("description", "")), "html.parser").get_text()[:800]
            jobs.append(new_job(
                title, company, "Remote",
                str(item.get("salary", "Not listed")),
                desc, str(item.get("url", "")),
                "Remotive", str(item.get("company_email", ""))
            ))
        time.sleep(1)
        print(f"  [Remotive] Found {len(jobs)} jobs for '{query}'")
    except Exception as e:
        print(f"  [Remotive] Error: {e}")
    return jobs

def scrape_themuse(query):
    jobs = []
    try:
        url = "https://www.themuse.com/api/public/jobs?descending=true&page=1&category=Software Engineer&level=Senior Level,Mid Level"
        resp = requests.get(url, headers=HEADERS, timeout=15)
        data = resp.json()
        query_words = str(query).lower().split()
        for item in data.get("results", [])[:20]:
            title   = str(item.get("name", ""))
            company = str(item.get("company", {}).get("name", "Unknown"))
            if not any(w in title.lower() for w in query_words):
                continue
            refs     = item.get("refs", {})
            job_url  = str(refs.get("landing_page", ""))
            locs     = item.get("locations", [])
            location = locs[0].get("name", "Remote") if locs else "Remote"
            desc     = BeautifulSoup(str(item.get("contents", "")), "html.parser").get_text()[:800]
            jobs.append(new_job(title, company, location, "Not listed", desc, job_url, "The Muse"))
        time.sleep(1)
        print(f"  [TheMuse] Found {len(jobs)} jobs for '{query}'")
    except Exception as e:
        print(f"  [TheMuse] Error: {e}")
    return jobs

def run_scraper():
    cfg      = json.loads(Path("data/config.json").read_text())
    queries  = cfg.get("job_queries", ["software engineer"])
    existing = load_jobs()
    new_count = 0

    for query in queries:
        query = str(query)
        print(f"\n[Scraper] Query: '{query}'")

        for job in scrape_adzuna(query):
            if job["id"] not in existing:
                existing[job["id"]] = job
                new_count += 1
                print(f"  + {job['portal']}: {job['title']} @ {job['company']}")

        for job in scrape_remotive(query):
            if job["id"] not in existing:
                existing[job["id"]] = job
                new_count += 1
                print(f"  + Remotive: {job['title']} @ {job['company']}")

        for job in scrape_themuse(query):
            if job["id"] not in existing:
                existing[job["id"]] = job
                new_count += 1
                print(f"  + TheMuse: {job['title']} @ {job['company']}")

    save_jobs(existing)
    print(f"\n[Scraper] Done. {new_count} new jobs added. Total: {len(existing)}")
    return new_count

if __name__ == "__main__":
    run_scraper()
