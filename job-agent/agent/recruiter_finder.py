"""
Recruiter Finder v3
- Apollo API first
- Google LinkedIn fallback
- Anthropic validation layer
- Strong email/name filtering
- Safer Playwright handling
"""

import os
import json
import re
import time
from pathlib import Path

import requests
import anthropic

DATA_FILE = Path("data/jobs.json")

APOLLO_API_KEY = os.environ.get("APOLLO_API_KEY", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

client_ai = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY) if ANTHROPIC_API_KEY else None

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[a-zA-Z]{2,}")

SKIP_EMAIL_LOCAL_PARTS = {
    "noreply", "no-reply", "donotreply", "do-not-reply",
    "support", "info", "help", "privacy", "legal", "press",
    "admin", "abuse", "example", "test", "unsubscribe",
    "feedback", "news", "phishing", "spam", "security",
    "verification", "verifications", "compliance",
    "notifications", "alerts", "employment.compliance",
    "employee.verifications",
}

FAKE_NAMES = {
    "full transparency", "application follow", "talent manager",
    "recruiting professional", "hiring manager", "hr team",
    "recruiter", "talent acquisition", "hr manager",
}

RECRUITER_TITLES = [
    "recruiter",
    "technical recruiter",
    "engineering recruiter",
    "talent acquisition",
    "talent partner",
    "talent sourcer",
    "sourcer",
    "hr business partner",
    "people operations",
    "staffing manager",
    "head of talent",
    "director of recruiting",
    "hiring manager",
]


def load_jobs():
    if not DATA_FILE.exists():
        return {}
    return json.loads(DATA_FILE.read_text())


def save_jobs(jobs):
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    DATA_FILE.write_text(json.dumps(jobs, indent=2))


def is_recruiter_title(title: str) -> bool:
    if not title:
        return False
    title = title.lower()
    return any(keyword in title for keyword in RECRUITER_TITLES)


def is_real_name(name: str) -> bool:
    if not name:
        return False

    name = name.strip()

    if name.lower() in FAKE_NAMES:
        return False

    parts = name.split()

    if len(parts) < 2 or len(parts) > 4:
        return False

    bad_words = {
        "follow", "up", "transparency", "professional",
        "manager", "recruiter", "team", "hr", "talent",
        "careers", "jobs", "support",
    }

    for part in parts:
        clean = re.sub(r"[^A-Za-z]", "", part)

        if not clean:
            return False

        if clean.lower() in bad_words:
            return False

        if len(clean) > 20:
            return False

        if not clean[0].isupper():
            return False

    return True


def is_good_email(email: str) -> bool:
    if not email or "@" not in email:
        return False

    email = email.strip().lower()

    if len(email) > 90:
        return False

    local = email.split("@")[0]

    if any(skip in local for skip in SKIP_EMAIL_LOCAL_PARTS):
        return False

    if local.upper() == local and len(local) > 5:
        return False

    return True


def company_to_domain(company: str) -> str:
    original = company
    company = company.lower().strip()

    company = re.sub(
        r"\b(inc|llc|ltd|corp|corporation|co|company|technologies|technology|"
        r"tech|solutions|services|group|global|systems|consulting|staffing|"
        r"professionals|bank|na|the)\b",
        "",
        company,
    )

    company = re.sub(r"[^a-z0-9\s]", "", company)
    company = re.sub(r"\s+", "", company)

    if not company:
        company = re.sub(r"[^a-z0-9]", "", original.lower())

    return f"{company}.com"


def guess_email(name: str, domain: str) -> str:
    parts = name.lower().strip().split()

    if len(parts) >= 2:
        return f"{parts[0]}.{parts[-1]}@{domain}"

    if parts:
        return f"{parts[0]}@{domain}"

    return f"careers@{domain}"


def ai_validate_recruiter(name: str, title: str, company: str) -> bool:
    """
    Anthropic validation layer.
    Used only after basic filters pass.
    """

    if not client_ai:
        return True

    if not name or not title:
        return True

    prompt = f"""
You are validating recruiter contact data.

Company: {company}
Name: {name}
Title: {title}

Is this person likely a real recruiter, HR, talent acquisition, sourcer,
people operations, staffing, or hiring-related contact for job outreach?

Answer only YES or NO.
"""

    try:
        response = client_ai.messages.create(
            model="claude-3-haiku-20240307",
            max_tokens=5,
            temperature=0,
            messages=[
                {"role": "user", "content": prompt}
            ],
        )

        text = response.content[0].text.strip().lower()
        return text.startswith("yes")

    except Exception as e:
        print(f"  ! Anthropic validation skipped: {str(e)[:80]}")
        return True


def dedupe_recruiters(recruiters, company=""):
    seen = set()
    clean = []

    for recruiter in recruiters:
        email = recruiter.get("email", "").lower().strip()
        name = recruiter.get("name", "").strip()
        title = recruiter.get("title", "").strip()

        if not is_good_email(email):
            continue

        if name and not is_real_name(name):
            continue

        if title and title != "HR Team" and not is_recruiter_title(title):
            continue

        if company and not ai_validate_recruiter(name, title, company):
            print(f"  ! AI rejected: {name} — {title}")
            continue

        if email in seen:
            continue

        recruiter["email"] = email
        seen.add(email)
        clean.append(recruiter)

    return clean


def find_recruiters_apollo(company: str, domain: str) -> list:
    if not APOLLO_API_KEY:
        return []

    print("  → Apollo search...")

    url = "https://api.apollo.io/v1/mixed_people/search"

    payload = {
        "api_key": APOLLO_API_KEY,
        "q_organization_domains": domain,
        "person_titles": RECRUITER_TITLES,
        "page": 1,
        "per_page": 10,
    }

    try:
        response = requests.post(url, json=payload, timeout=20)

        if response.status_code >= 400:
            print(f"  ! Apollo error: {response.status_code}")
            return []

        data = response.json()
        people = data.get("people", []) or data.get("contacts", [])

        recruiters = []

        for person in people:
            first = person.get("first_name") or ""
            last = person.get("last_name") or ""
            name = f"{first} {last}".strip()
            title = person.get("title") or ""
            email = person.get("email") or ""

            if not email:
                email = guess_email(name, domain)

            recruiters.append({
                "name": name,
                "title": title,
                "email": email.lower(),
                "source": "apollo",
            })

            print(f"  ✓ Apollo candidate: {name} — {title} — {email}")

        return dedupe_recruiters(recruiters, company)[:10]

    except Exception as e:
        print(f"  ! Apollo exception: {str(e)[:80]}")
        return []


def parse_recruiter_from_line(line: str) -> dict:
    line = line.strip()

    match = re.match(
        r"^([A-Z][a-z]+ (?:[A-Z][a-z]+ )?[A-Z][a-z]+)\s*[-–—]\s*(.+?)$",
        line,
    )

    if not match:
        return {}

    name = match.group(1).strip()
    title = match.group(2).strip()

    if not is_real_name(name):
        return {}

    if not is_recruiter_title(title):
        return {}

    return {
        "name": name,
        "title": title,
    }


def find_recruiters_google(page, company: str, domain: str) -> list:
    print("  → Google LinkedIn fallback...")

    recruiters = []

    queries = [
        f'site:linkedin.com/in "{company}" "technical recruiter"',
        f'site:linkedin.com/in "{company}" "talent acquisition"',
        f'site:linkedin.com/in "{company}" recruiter',
        f'site:linkedin.com/in "{company}" sourcer',
    ]

    for query in queries:
        try:
            url = f"https://www.google.com/search?q={query.replace(' ', '+')}&num=10"

            page.goto(url, timeout=25000, wait_until="domcontentloaded")
            page.wait_for_timeout(2500)

            body = page.inner_text("body")

            if "unusual traffic" in body.lower() or "captcha" in body.lower():
                print("  ! Google CAPTCHA — skipping fallback")
                break

            for line in body.splitlines():
                if len(line.strip()) < 8 or len(line.strip()) > 220:
                    continue

                result = parse_recruiter_from_line(line)

                if result:
                    email = guess_email(result["name"], domain)

                    recruiters.append({
                        "name": result["name"],
                        "title": result["title"],
                        "email": email,
                        "source": "linkedin_google",
                    })

                    print(f"  ✓ Google candidate: {result['name']} — {result['title']}")

                if len(recruiters) >= 10:
                    break

            emails = EMAIL_RE.findall(body)

            for email in emails:
                email = email.lower()

                if not is_good_email(email):
                    continue

                email_domain = email.split("@")[1]

                if domain.replace("www.", "") in email_domain:
                    recruiters.append({
                        "name": "",
                        "title": "Recruiter",
                        "email": email,
                        "source": "google_email",
                    })

                    print(f"  ✓ Email found: {email}")

            recruiters = dedupe_recruiters(recruiters, company)

            if len(recruiters) >= 5:
                break

            time.sleep(2)

        except Exception as e:
            print(f"  ! Google search error: {str(e)[:80]}")

    return dedupe_recruiters(recruiters, company)[:10]


def build_fallback_contact(domain: str) -> list:
    return [{
        "name": "",
        "title": "HR Team",
        "email": f"careers@{domain}",
        "source": "pattern_guess",
    }]


def run_recruiter_finder():
    from playwright.sync_api import sync_playwright

    jobs = load_jobs()
    updated = 0

    targets = [
        (jid, job)
        for jid, job in jobs.items()
        if (job.get("fit_score") or 0) >= 80
        and not job.get("email_sent")
        and job.get("recruiter_source") not in [
            "apollo",
            "linkedin_google",
            "google_email",
        ]
    ]

    if not targets:
        print("[Recruiter Finder] No new jobs to process")
        return 0

    print(f"[Recruiter Finder] Processing {len(targets)} jobs...")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
            ],
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
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )

        page = ctx.new_page()
        page.set_default_timeout(20000)

        for jid, job in targets[:15]:
            company = job.get("company", "").strip()

            if not company:
                continue

            domain = job.get("company_domain") or company_to_domain(company)

            print(f"\n  [{company}] → {domain}")

            recruiters = []

            recruiters.extend(find_recruiters_apollo(company, domain))

            if len(recruiters) < 3:
                google_recruiters = find_recruiters_google(page, company, domain)
                recruiters.extend(google_recruiters)

            recruiters = dedupe_recruiters(recruiters, company)

            if not recruiters:
                print("  ! No contacts found — using careers@ fallback")
                recruiters = build_fallback_contact(domain)

            jobs[jid]["recruiters"] = recruiters
            jobs[jid]["recruiter_email"] = recruiters[0]["email"]
            jobs[jid]["recruiter_name"] = recruiters[0].get("name", "")
            jobs[jid]["recruiter_source"] = recruiters[0]["source"]

            print(f"  → {len(recruiters)} contact(s) saved:")

            for recruiter in recruiters:
                label = f" ({recruiter['name']})" if recruiter.get("name") else ""
                print(f"     • {recruiter['email']}{label}")

            updated += 1
            time.sleep(2)

        browser.close()

    save_jobs(jobs)

    print(f"\n[Recruiter Finder] Done. {updated} jobs updated.")
    return updated


if __name__ == "__main__":
    run_recruiter_finder()
