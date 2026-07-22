"""
Job Scraper — Production Grade, US-Only
Sources:
1. Adzuna API      — official US jobs API (country=us)
2. Remotive API    — remote tech jobs, filtered for US eligibility
3. LinkedIn (Apify)— largest job board, filtered via US allowlist
4. Google Jobs     — per-state "site:" searches across major US job boards

US FILTERING STRATEGY (allowlist, not denylist):
A job is considered US-based if its location field contains:
  - "united states", "usa", "u.s."
  - a full US state name (e.g. "California", "Florida")
  - a US state abbreviation as a standalone token (e.g. ", CA", ", FL")
  - "remote" combined with no foreign country marker
Anything else (foreign cities, foreign countries, ambiguous "Remote" with
no US signal) is REJECTED. This is the inverse of a denylist — instead of
trying to enumerate every foreign city/country (which is an endless list),
we only accept jobs that positively match a US location signal.

Deduplicates by title+company+url hash.
"""

import json, os, re, time, hashlib
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import quote

import requests
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


# ── US LOCATION ALLOWLIST ─────────────────────────────────────────────────────

US_STATES = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR",
    "california": "CA", "colorado": "CO", "connecticut": "CT", "delaware": "DE",
    "florida": "FL", "georgia": "GA", "hawaii": "HI", "idaho": "ID",
    "illinois": "IL", "indiana": "IN", "iowa": "IA", "kansas": "KS",
    "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
    "massachusetts": "MA", "michigan": "MI", "minnesota": "MN",
    "mississippi": "MS", "missouri": "MO", "montana": "MT", "nebraska": "NE",
    "nevada": "NV", "new hampshire": "NH", "new jersey": "NJ",
    "new mexico": "NM", "new york": "NY", "north carolina": "NC",
    "north dakota": "ND", "ohio": "OH", "oklahoma": "OK", "oregon": "OR",
    "pennsylvania": "PA", "rhode island": "RI", "south carolina": "SC",
    "south dakota": "SD", "tennessee": "TN", "texas": "TX", "utah": "UT",
    "vermont": "VT", "virginia": "VA", "washington": "WA",
    "west virginia": "WV", "wisconsin": "WI", "wyoming": "WY",
    "district of columbia": "DC",
}

US_STATE_ABBRS = set(US_STATES.values())

US_COUNTRY_MARKERS = [
    "united states", "usa", "u.s.a", "u.s.", "(us)",
]

def _has_standalone_us(loc: str) -> bool:
    """Catch 'US' as a standalone token, e.g. 'Remote - US', 'Remote, US'."""
    tokens = re.split(r"[,\-/\s]+", loc.upper().strip())
    return "US" in tokens

# Major US cities — helps catch "San Francisco" / "New York City" with no state
US_MAJOR_CITIES = [
    "new york city", "san francisco", "los angeles", "chicago", "boston",
    "seattle", "austin", "denver", "atlanta", "dallas", "houston",
    "phoenix", "philadelphia", "san diego", "miami", "minneapolis",
    "detroit", "portland", "nashville", "charlotte", "raleigh",
    "washington dc", "san jose", "columbus", "indianapolis",
    "jacksonville", "san antonio", "fort worth", "el paso",
    "memphis", "baltimore", "milwaukee", "albuquerque", "tucson",
    "sacramento", "kansas city", "mesa", "omaha", "colorado springs",
    "raleigh", "long beach", "virginia beach", "oakland", "tampa",
    "tulsa", "arlington", "new orleans", "wichita", "cleveland",
    "boca raton", "fort lauderdale", "orlando", "tampa bay",
]

# Explicit foreign-country / region markers — used as a final safety check
# even when a location string contains an ambiguous term like "Remote"
FOREIGN_MARKERS = [
    "india", "pakistan", "bangladesh", "philippines", "nigeria", "kenya",
    "vietnam", "indonesia", "sri lanka", "nepal", "egypt", "ghana",
    "germany", "deutschland", "gmbh", "m/w/d", "m/f/d", "austria",
    "switzerland", "united kingdom", "england", "scotland", "wales",
    "ireland", "france", "spain", "italy", "portugal", "netherlands",
    "belgium", "poland", "romania", "bulgaria", "hungary", "czech",
    "ukraine", "russia", "greece", "turkey", "israel",
    "canada", "mexico", "brazil", "argentina", "colombia", "chile",
    "peru", "australia", "new zealand", "singapore", "malaysia",
    "thailand", "japan", "china", "hong kong", "taiwan", "south korea",
    "south africa", "morocco", "uae", "dubai", "saudi arabia", "qatar",
    "remote - eu", "remote eu", "emea", "apac", "latam",
    "hyderabad", "bangalore", "bengaluru", "mumbai", "delhi", "pune",
    "chennai", "kolkata", "noida", "gurgaon", "gurugram", "telangana",
    "karnataka", "maharashtra", "tamil nadu", "islamabad", "lahore",
    "karachi", "budapest", "athens", "warsaw", "lisbon", "porto",
    "krakow", "bucharest", "manila", "jakarta", "ho chi minh",
]


def is_us_location(location: str, description: str = "") -> bool:
    """
    Allowlist check: a job is US-based ONLY if its location string
    positively matches a US signal AND has no foreign marker.
    """
    loc = (location or "").lower().strip()
    desc_snip = (description or "").lower()[:300]

    # Hard reject: explicit foreign marker in location
    if any(marker in loc for marker in FOREIGN_MARKERS):
        return False

    # Positive signals in location string
    if any(marker in loc for marker in US_COUNTRY_MARKERS):
        return True

    if _has_standalone_us(loc):
        return True

    if any(state in loc for state in US_STATES.keys()):
        return True

    if any(city in loc for city in US_MAJOR_CITIES):
        return True

    # Check for standalone state abbreviation, e.g. "Boston, MA" or "Remote - TX"
    tokens = re.split(r"[,\-/\s]+", loc.upper())
    if any(tok in US_STATE_ABBRS for tok in tokens):
        return True

    # "Remote" with no foreign marker and no other location info —
    # check description for a US signal as a tiebreaker
    if "remote" in loc:
        if any(marker in desc_snip for marker in FOREIGN_MARKERS):
            return False
        if any(marker in desc_snip for marker in US_COUNTRY_MARKERS):
            return True
        if any(state in desc_snip for state in US_STATES.keys()):
            return True
        # Ambiguous remote with zero signals either way — reject to be safe
        return False

    # No US signal found at all — reject
    return False


# ── RELEVANCE FILTER ──────────────────────────────────────────────────────────

IRRELEVANT_KEYWORDS = [
    "sales", "marketing", "nurse", "driver", "retail manager",
    "accountant", "lawyer", "attorney", "teacher", "cook", "chef",
    "electrician", "plumber", "mechanic", "warehouse", "forklift",
    "registered nurse", "rn ", "phlebotomist", "dental", "hygienist",
    "real estate agent", "insurance agent", "loan officer",
    "construction", "hvac", "welder", "machinist", "custodian",
]

RELEVANT_KEYWORDS = [
    "java", "spring", "spring boot", "microservices", "kafka", "react", "angular",
    "typescript", "javascript", "aws", "azure", "full stack", "fullstack",
    "software engineer", "software developer", "backend", "back-end",
    "frontend", "front-end", "python", "node.js", "node", "api",
    "cloud", "devops", "ai engineer", "machine learning", "automation",
    "engineer", "developer", "programmer", "sde", "web developer",
]


def is_relevant(title: str, description: str) -> bool:
    t = (title or "").lower()
    d = (description or "").lower()[:600]

    if any(k in t for k in IRRELEVANT_KEYWORDS):
        return False

    combined = f"{t} {d}"
    return any(k in combined for k in RELEVANT_KEYWORDS)


# ── HELPERS ───────────────────────────────────────────────────────────────────

def load_jobs() -> dict:
    return json.loads(DATA_FILE.read_text()) if DATA_FILE.exists() else {}

def save_jobs(jobs: dict) -> None:
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    DATA_FILE.write_text(json.dumps(jobs, indent=2))

def load_config() -> dict:
    return json.loads(CONFIG_FILE.read_text()) if CONFIG_FILE.exists() else {}

def make_id(title: str, company: str, url: str = "") -> str:
    raw = f"{title.lower().strip()}-{company.lower().strip()}-{url.lower().strip()}"
    return hashlib.md5(raw.encode()).hexdigest()[:12]

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def clean(text) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()

def strip_html(text: str) -> str:
    return BeautifulSoup(str(text or ""), "html.parser").get_text()

def new_job(title, company, location, salary, description, url, portal,
            recruiter_email="") -> dict:
    return {
        "id":              make_id(title, company, url),
        "title":           clean(title),
        "company":         clean(company),
        "location":        clean(location) or "United States",
        "salary":          clean(salary) or "Not listed",
        "description":     clean(description),
        "url":             clean(url),
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
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    skip_statuses = {"skipped_low_score", "skipped_irrelevant", "skipped_non_us", "no_email"}
    for job in jobs.values():
        if job.get("status") in skip_statuses:
            try:
                scraped_dt = datetime.fromisoformat(job.get("scraped_at", ""))
                if scraped_dt < cutoff:
                    job["status"] = "archived"
            except Exception:
                pass


# ── SOURCE 1: ADZUNA (official US API) ───────────────────────────────────────

def scrape_adzuna(query: str, max_days: int = 1) -> list:
    """Official Adzuna API, country=us — already geo-restricted by Adzuna."""
    jobs = []
    if not ADZUNA_APP_ID or not ADZUNA_APP_KEY:
        print("  [Adzuna] Missing API credentials — skipping")
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
            loc     = str(item.get("location", {}).get("display_name", "United States"))
            sm      = item.get("salary_min")
            sx      = item.get("salary_max")
            salary  = f"${int(sm):,} - ${int(sx):,}" if sm and sx else "Not listed"
            desc    = str(item.get("description", ""))
            job_url = str(item.get("redirect_url", ""))

            if not is_relevant(title, desc):
                continue
            # Adzuna /us/ endpoint is already US-restricted, but double check
            if not is_us_location(loc, desc):
                continue

            jobs.append(new_job(title, company, loc, salary, desc, job_url, "Adzuna"))

        time.sleep(1)
        print(f"  [Adzuna] {len(jobs)} relevant US jobs for '{query}'")

    except Exception as e:
        print(f"  [Adzuna] Error: {str(e)[:100]}")

    return jobs


# ── SOURCE 2: REMOTIVE ────────────────────────────────────────────────────────

def scrape_remotive(query: str) -> list:
    """Remotive — remote tech jobs. Filtered for US eligibility."""
    jobs = []
    try:
        url = (
            f"https://remotive.com/api/remote-jobs"
            f"?search={quote(query)}&category=software-dev&limit=20"
        )
        resp = requests.get(url, headers=HEADERS, timeout=15)
        data = resp.json()

        for item in data.get("jobs", []):
            title       = str(item.get("title", ""))
            company     = str(item.get("company_name", ""))
            desc        = strip_html(item.get("description", ""))[:1500]
            candidate_loc = str(item.get("candidate_required_location", "")) or "Remote"
            job_url     = str(item.get("url", ""))
            salary      = str(item.get("salary", "")) or "Not listed"

            if not is_relevant(title, desc):
                continue
            if not is_us_location(candidate_loc, desc):
                continue

            jobs.append(new_job(
                title, company, candidate_loc, salary, desc, job_url,
                "Remotive", str(item.get("company_email", ""))
            ))

        time.sleep(1)
        print(f"  [Remotive] {len(jobs)} relevant US jobs for '{query}'")

    except Exception as e:
        print(f"  [Remotive] Error: {str(e)[:100]}")

    return jobs


# ── SOURCE 3: LINKEDIN (via Apify) ────────────────────────────────────────────

def scrape_linkedin(query: str) -> list:
    """LinkedIn jobs via Apify, filtered for US locations."""
    jobs = []
    if not APIFY_TOKEN:
        return jobs
    try:
        from apify_client import ApifyClient
        apify = ApifyClient(APIFY_TOKEN)

        print(f"  [LinkedIn] Searching: {query}")
        run = apify.actor("bebity/linkedin-jobs-scraper").call(
            run_input={
                "title": query,
                "location": "United States",
                "rows": 40,
                "publishedAt": "r86400",  # past 24 hours
            },
            timeout=timedelta(seconds=120),
        )

        items = list(apify.dataset(run["defaultDatasetId"]).iterate_items())
        print(f"  [LinkedIn] Raw: {len(items)}")

        for item in items:
            title   = str(item.get("title", ""))
            company = str(item.get("companyName", ""))
            loc     = str(item.get("location", "United States"))
            desc    = strip_html(item.get("descriptionHtml", "") or item.get("description", ""))[:1500]
            job_url = str(item.get("link", "") or item.get("applyUrl", ""))
            salary  = str(item.get("salary", "")) or "Not listed"

            if not title or not company:
                continue
            if not is_relevant(title, desc):
                continue
            if not is_us_location(loc, desc):
                continue

            jobs.append(new_job(title, company, loc, salary, desc, job_url, "LinkedIn"))

        print(f"  [LinkedIn] {len(jobs)} relevant US jobs for '{query}'")

    except Exception as e:
        print(f"  [LinkedIn] Error: {str(e)[:120]}")

    return jobs


# ── SOURCE 4: GOOGLE — PER-STATE SITE SEARCHES ───────────────────────────────

# A small rotating sample of states to search per run (avoids 50x API calls
# every run). Big tech/job hub states are weighted more heavily.
STATE_ROTATION = [
    "California", "Texas", "New York", "Florida", "Washington",
    "Massachusetts", "Illinois", "Georgia", "North Carolina",
    "Virginia", "Colorado", "Arizona", "Pennsylvania", "Ohio",
    "New Jersey", "Remote",
]

JOB_SITES = [
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
]

def _yesterday_str() -> str:
    return (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")

def scrape_google_jobs_by_state(query: str, state: str) -> list:
    """
    Google site: search restricted to a specific US state, past 24hr,
    across major job board domains.
    """
    jobs = []
    try:
        sites_clause = " OR ".join(f"site:{s}" for s in JOB_SITES)
        search_q = (
            f'"{query}" "{state}" software developer job '
            f'after:{_yesterday_str()} ({sites_clause})'
        )
        search_url = (
            f"https://www.google.com/search"
            f"?q={quote(search_q)}&tbs=qdr:d&hl=en&gl=us"
        )

        resp = requests.get(search_url, headers=HEADERS, timeout=20)
        if resp.status_code != 200:
            return jobs

        soup = BeautifulSoup(resp.text, "html.parser")

        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data  = json.loads(script.string or "")
                items = data if isinstance(data, list) else [data]
                for item in items:
                    if item.get("@type") not in ("JobPosting", "jobPosting"):
                        continue

                    title   = clean(item.get("title", ""))
                    org     = item.get("hiringOrganization", {})
                    company = clean(org.get("name", "") if isinstance(org, dict) else "")
                    loc_raw = item.get("jobLocation", {})
                    if isinstance(loc_raw, list):
                        loc_raw = loc_raw[0] if loc_raw else {}
                    addr = loc_raw.get("address", {}) if isinstance(loc_raw, dict) else {}
                    location = clean(
                        addr.get("addressLocality", "") or
                        addr.get("addressRegion", "") or
                        state
                    )
                    desc = strip_html(item.get("description", ""))[:1500]
                    job_url = clean(item.get("url") or item.get("sameAs") or "")

                    if not title or not company:
                        continue
                    if not is_relevant(title, desc):
                        continue
                    if not is_us_location(location or state, desc):
                        continue

                    jobs.append(new_job(
                        title, company, location or state, "Not listed",
                        desc, job_url, "Google Jobs"
                    ))

            except Exception:
                continue

        time.sleep(2)

    except Exception as e:
        print(f"  [Google:{state}] Error: {str(e)[:80]}")

    return jobs


# ── MAIN ──────────────────────────────────────────────────────────────────────

def run_scraper() -> int:
    cfg     = load_config()
    queries = cfg.get("job_queries", ["software engineer"])
    jobs    = load_jobs()
    added   = 0

    archive_old_skipped(jobs)

    # Rotate through states so each run covers a different slice of the US
    run_index    = int(time.time()) // 21600  # changes every 6 hours
    states_today = [
        STATE_ROTATION[(run_index + i) % len(STATE_ROTATION)]
        for i in range(4)  # 4 states per run, per query
    ]

    for query in queries:
        query = str(query)
        print(f"\n[Scraper] Query: '{query}'")

        # Adzuna — official US-only API
        for job in scrape_adzuna(query, max_days=1):
            if job["id"] not in jobs:
                jobs[job["id"]] = job
                added += 1
                print(f"  + Adzuna: {job['title']} @ {job['company']} ({job['location']})")

        # Remotive — US-eligible remote jobs
        for job in scrape_remotive(query):
            if job["id"] not in jobs:
                jobs[job["id"]] = job
                added += 1
                print(f"  + Remotive: {job['title']} @ {job['company']} ({job['location']})")

        # LinkedIn — US-filtered
        for job in scrape_linkedin(query):
            if job["id"] not in jobs:
                jobs[job["id"]] = job
                added += 1
                print(f"  + LinkedIn: {job['title']} @ {job['company']} ({job['location']})")

        # Google — per-state searches (rotates across run cycles)
        for state in states_today:
            print(f"  [Google:{state}] Searching '{query}'...")
            for job in scrape_google_jobs_by_state(query, state):
                if job["id"] not in jobs:
                    jobs[job["id"]] = job
                    added += 1
                    print(f"  + Google ({state}): {job['title']} @ {job['company']} ({job['location']})")

    save_jobs(jobs)
    print(f"\n[Scraper] Done. {added} new US jobs added. Total: {len(jobs)}")
    print(f"[Scraper] States covered this run: {', '.join(states_today)}")
    return added


if __name__ == "__main__":
    run_scraper()
