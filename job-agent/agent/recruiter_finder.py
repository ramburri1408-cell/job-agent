"""
Recruiter Finder — Google search for LinkedIn recruiter profiles
Fixed: filters out bad emails, fake names, HR verification addresses
"""

import os, json, re, time
from pathlib import Path
import anthropic
import requests

client_ai = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
apollo_key = os.environ.get("APOLLO_API_KEY", "")
DATA_FILE  = Path("data/jobs.json")

EMAIL_RE = re.compile(r'[\w.+-]+@[\w-]+\.[a-zA-Z]{2,}')

# Emails to always skip
SKIP_EMAILS = {
    "noreply", "no-reply", "support", "info", "help", "privacy",
    "legal", "press", "admin", "abuse", "example", "test",
    "unsubscribe", "feedback", "news", "phishing", "spam",
    "security", "verification", "verifications", "compliance",
    "donotreply", "do-not-reply", "notifications", "alerts",
    "employment.compliance", "employee.verifications",
}

# Fake/bad recruiter names to filter out
FAKE_NAMES = {
    "full transparency", "application follow", "talent manager",
    "recruiting professional", "hiring manager", "hr team",
    "recruiter", "talent acquisition", "hr manager",
}

RECRUITER_TITLES = [
    "recruiter", "talent acquisition", "hr business partner",
    "technical recruiter", "engineering recruiter", "talent partner",
    "head of talent", "director of recruiting", "sourcer",
    "staffing manager", "people operations", "hiring manager",
]

def load_jobs():
    return json.loads(DATA_FILE.read_text()) if DATA_FILE.exists() else {}

def save_jobs(jobs):
    DATA_FILE.write_text(json.dumps(jobs, indent=2))

def is_recruiter_title(title: str) -> bool:
    return any(r in title.lower() for r in RECRUITER_TITLES)

def is_real_name(name: str) -> bool:
    """Check if name looks like a real person's name."""
    name = name.strip()
    # Must have at least 2 words
    parts = name.split()
    if len(parts) < 2:
        return False
    # Each part should start with capital letter
    if not all(p[0].isupper() for p in parts if p):
        return False
    # Must not be in fake names list
    if name.lower() in FAKE_NAMES:
        return False
    # Name parts should be reasonable length
    if any(len(p) > 20 for p in parts):
        return False
    # Should not contain common non-name words
    skip_words = {"follow", "up", "transparency", "professional",
                  "manager", "recruiter", "team", "hr", "talent"}
    if any(p.lower() in skip_words for p in parts):
        return False
    return True

def is_good_email(email: str) -> bool:
    """Check if email looks like a real recruiter email."""
    if not email or "@" not in email or len(email) > 80:
        return False
    local = email.split("@")[0].lower()
    # Skip generic/system emails
    if any(s in local for s in SKIP_EMAILS):
        return False
    # Skip all-caps emails (usually system emails)
    if local.upper() == local and len(local) > 5:
        return False
    return True

def company_to_domain(company: str) -> str:
    clean = re.sub(
        r'\s*\b(inc|llc|ltd|corp|co|company|technologies|tech|'
        r'solutions|services|group|global|systems|consulting|'
        r'staffing|professionals|bank|na|the)\b\s*',
        ' ', company.lower()
    )
    clean = re.sub(r'[^a-z0-9\s]', '', clean).strip().replace(' ', '')
    if not clean:
        clean = re.sub(r'[^a-z0-9]', '', company.lower())
    return f"{clean}.com"

def guess_email(name: str, domain: str) -> str:
    parts = name.lower().strip().split()
    if len(parts) >= 2:
        return f"{parts[0]}.{parts[-1]}@{domain}"
    elif parts:
        return f"{parts[0]}@{domain}"
    return f"careers@{domain}"

def parse_recruiter_from_line(line: str, company: str) -> dict:
    """
    Extract recruiter name and title from a Google result line.
    Pattern: "Name — Title at Company"
    """
    line = line.strip()

    # Pattern: "FirstName LastName — Title at Company"
    match = re.match(
        r'^([A-Z][a-z]+ (?:[A-Z][a-z]+ )?[A-Z][a-z]+)\s*[-–—]\s*(.+?)(?:\s+at\s+.+)?$',
        line
    )
    if match:
        name  = match.group(1).strip()
        title = match.group(2).strip()
        if is_real_name(name) and is_recruiter_title(title):
            return {"name": name, "title": title}

    return {}

def find_recruiters_google(page, company: str, domain: str) -> list:
    """Search Google for LinkedIn recruiter profiles at the company."""
    recruiters = []
    queries = [
        f'site:linkedin.com/in "{company}" recruiter',
        f'site:linkedin.com/in "{company}" "talent acquisition"',
        f'site:linkedin.com/in "{company}" "technical recruiter"',
    ]

    for query in queries:
        try:
            url = f"https://www.google.com/search?q={query.replace(' ', '+')}&num=10"
            page.goto(url, timeout=20000, wait_until="domcontentloaded")
            page.wait_for_timeout(2000)

            body = page.inner_text("body")

            if "unusual traffic" in body.lower() or "captcha" in body.lower():
                print(f"  ! Google CAPTCHA — skipping")
                break

            # Extract recruiter names from results
            lines = body.split('\n')
            for line in lines:
                if len(line.strip()) < 5 or len(line.strip()) > 200:
                    continue
                result = parse_recruiter_from_line(line, company)
                if result and result["name"]:
                    # Check not already found
                    if not any(r["name"] == result["name"] for r in recruiters):
                        email = guess_email(result["name"], domain)
                        recruiters.append({
                            "name":   result["name"],
                            "title":  result["title"],
                            "email":  email,
                            "source": "linkedin_google",
                        })
                        print(f"  ✓ Found: {result['name']} — {result['title']}")

                if len(recruiters) >= 5:
                    break

            # Also find direct emails — but filter strictly
            emails = EMAIL_RE.findall(body)
            for email in emails:
                if not is_good_email(email):
                    continue
                # Only accept emails from company domain
                email_domain = email.split("@")[1].lower()
                if domain.split(".")[0] in email_domain:
                    if not any(r["email"] == email for r in recruiters):
                        recruiters.append({
                            "name":   "",
                            "title":  "Recruiter",
                            "email":  email,
                            "source": "google_email",
                        })
                        print(f"  ✓ Email found: {email}")

            if len(recruiters) >= 5:
                break

            time.sleep(2)

        except Exception as e:
            print(f"  ! Search error: {str(e)[:60]}")

    return recruiters[:5]

def run_recruiter_finder():
    from playwright.sync_api import sync_playwright

    jobs    = load_jobs()
    updated = 0

    targets = [
        (jid, job) for jid, job in jobs.items()
        if (job.get("fit_score") or 0) >= 80
        and not job.get("email_sent")
        and job.get("recruiter_source") not in
            ["linkedin_google", "google_email", "apollo"]
    ]

    if not targets:
        print("[Recruiter Finder] No new jobs to process")
        return 0

    print(f"[Recruiter Finder] Processing {len(targets)} jobs...")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox",
                  "--disable-dev-shm-usage",
                  "--disable-blink-features=AutomationControlled"]
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
            "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"
        )
        page = ctx.new_page()
        page.set_default_timeout(20000)

        for jid, job in targets[:15]:
            company = job.get("company", "").strip()
            domain  = company_to_domain(company)

            print(f"\n  [{company}] → {domain}")

            recruiters = find_recruiters_google(page, company, domain)

            if not recruiters:
                print(f"  ! No contacts — using careers@ fallback")
                recruiters = [{
                    "name":   "",
                    "title":  "HR Team",
                    "email":  f"careers@{domain}",
                    "source": "pattern_guess",
                }]

            # Final validation — remove any bad emails that slipped through
            recruiters = [
                r for r in recruiters
                if is_good_email(r["email"])
                and (not r["name"] or is_real_name(r["name"]))
            ]

            if not recruiters:
                recruiters = [{
                    "name":   "",
                    "title":  "HR Team",
                    "email":  f"careers@{domain}",
                    "source": "pattern_guess",
                }]

            jobs[jid]["recruiters"]       = recruiters
            jobs[jid]["recruiter_email"]  = recruiters[0]["email"]
            jobs[jid]["recruiter_name"]   = recruiters[0].get("name", "")
            jobs[jid]["recruiter_source"] = recruiters[0]["source"]

            print(f"  → {len(recruiters)} contact(s) saved:")
            for r in recruiters:
                label = f" ({r['name']})" if r.get("name") else ""
                print(f"     • {r['email']}{label}")

            updated += 1
            time.sleep(3)

        browser.close()

    save_jobs(jobs)
    print(f"\n[Recruiter Finder] Done. {updated} jobs updated.")
    return updated

if __name__ == "__main__":
    run_recruiter_finder()
