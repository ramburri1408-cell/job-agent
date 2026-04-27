import json, os, time, hashlib
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote as urlquote

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

def load_jobs() -> dict:
    if DATA_FILE.exists():
        return json.loads(DATA_FILE.read_text())
    return {}

def save_jobs(jobs: dict):
    DATA_FILE.write_text(json.dumps(jobs, indent=2))

def make_id(title: str, company: str) -> str:
    raw = f"{title.lower().strip()}-{company.lower().strip()}"
    return hashlib.md5(raw.encode()).hexdigest()[:12]

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def scrape_indeed(query: str, location: str = "remote") -> list:
    location = str(location)
    query = str(query)
    jobs = []
    url = (
        f"https://www.indeed.com/jobs"
        f"?q={urlquote(query)}"
        f"&l={urlquote(location)}"
        f"&sort=date&fromage=1"
    )
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(resp.text, "html.parser")
        cards = soup.select("div.job_seen_beacon")[:10]
        for card in cards:
            title_el = card.select_one("h2.jobTitle span")
            co_el    = card.select_one("[data-testid='company-name']")
            loc_el   = card.select_one("[data-testid='text-location']")
            sal_el   = card.select_one("[data-testid='attribute_snippet_testid']")
            link_el  = card.select_one("h2.jobTitle a")
            desc_el  = card.select_one("div.job-snippet")
            if not title_el or not co_el:
                continue
            title   = title_el.get_text(strip=True)
            company = co_el.get_text(strip=True)
            jid     = make_id(title, company)
            href    = link_el["href"] if link_el else ""
            full_url = f"https://www.indeed.com{href}" if href.startswith("/") else href
            jobs.append({
                "id": jid, "title": title, "company": company,
                "location": loc_el.get_text(strip=True) if loc_el else location,
                "salary": sal_el.get_text(strip=True) if sal_el else "Not listed",
                "description": desc_el.get_text(strip=True) if desc_el else "",
                "url": full_url, "portal": "Indeed",
                "scraped_at": now_iso(), "status": "new",
                "recruiter_email": "", "recruiter_name": "",
                "tailored_resume": None, "email_draft": None,
                "email_sent": False, "email_sent_at": None, "fit_score": None,
            })
        time.sleep(2)
    except Exception as e:
        print(f"[Indeed] Error: {e}")
    return jobs

def scrape_dice(query: str) -> list:
    jobs = []
    url = (
        f"https://job-search-api.svc.dhigroupinc.com/v1/dice/jobs/search"
        f"?q={urlquote(query)}&countryCode2=US&radius=30"
        f"&radiusUnit=mi&page=1&pageSize=10&filters.postedDate=ONE"
        f"&language=en&eid=21522&fj=1"
    )
    try:
        resp = requests.get(url, headers={**HEADERS, "Accept": "application/json"}, timeout=15)
        data = resp.json()
        for item in data.get("data", [])[:10]:
            title   = item.get("title", "")
            company = item.get("companyPageUrl", item.get("companyDisplay", "Unknown"))
            if "/" in company:
                company = company.rsplit("/", 1)[-1].replace("-", " ").title()
            jid = make_id(title, company)
            jobs.append({
                "id": jid, "title": title, "company": company,
                "location": item.get("location", "Remote"),
                "salary": item.get("salary", "Not listed"),
                "description": item.get("jobDescription", ""),
                "url": f"https://www.dice.com/job-detail/{item.get('id', '')}",
                "portal": "Dice", "scraped_at": now_iso(), "status": "new",
                "recruiter_email": "", "recruiter_name": "",
                "tailored_resume": None, "email_draft": None,
                "email_sent": False, "email_sent_at": None, "fit_score": None,
            })
        time.sleep(2)
    except Exception as e:
        print(f"[Dice] Error: {e}")
    return jobs

def scrape_remotive(query: str) -> list:
    jobs = []
    try:
        url = f"https://remotive.com/api/remote-jobs?search={urlquote(query)}&limit=10"
        resp = requests.get(url, timeout=15)
        data = resp.json()
        for item in data.get("jobs", []):
            title   = item.get("title", "")
            company = item.get("company_name", "")
            jid     = make_id(title, company)
            jobs.append({
                "id": jid, "title": title, "company": company,
                "location": "Remote",
                "salary": item.get("salary", "Not listed"),
                "description": BeautifulSoup(item.get("description", ""), "html.parser").get_text()[:800],
                "url": item.get("url", ""), "portal": "Remotive",
                "scraped_at": now_iso(), "status": "new",
                "recruiter_email": item.get("company_email", ""), "recruiter_name": "",
                "tailored_resume": None, "email_draft": None,
                "email_sent": False, "email_sent_at": None, "fit_score": None,
            })
        time.sleep(1)
    except Exception as e:
        print(f"[Remotive] Error: {e}")
    return jobs

def run_scraper():
    cfg      = json.loads(Path("data/config.json").read_text())
    queries  = cfg.get("job_queries", ["software engineer"])
    location = str(cfg.get("location", "remote"))
    existing = load_jobs()
    new_count = 0

    for query in queries:
        print(f"\n[Scraper] Query: '{query}'")
        for job in scrape_indeed(query, location):
            if job["id"] not in existing:
                existing[job["id"]] = job
                new_count += 1
                print(f"  + Indeed:   {job['title']} @ {job['company']}")
        for job in scrape_dice(query):
            if job["id"] not in existing:
                existing[job["id"]] = job
                new_count += 1
                print(f"  + Dice:     {job['title']} @ {job['company']}")
        for job in scrape_remotive(query):
            if job["id"] not in existing:
                existing[job["id"]] = job
                new_count += 1
                print(f"  + Remotive: {job['title']} @ {job['company']}")

    save_jobs(existing)
    print(f"\n[Scraper] Done. {new_count} new jobs added. Total: {len(existing)}")
    return new_count

if __name__ == "__main__":
    run_scraper()
