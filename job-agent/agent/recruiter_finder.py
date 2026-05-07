"""
Recruiter Finder — Apollo free plan compatible
Uses /people/match endpoint which works on free tier
"""

import os, json, re, time
from pathlib import Path
from apify_client import ApifyClient
import anthropic
import requests

client_ai   = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
apify_token = os.environ.get("APIFY_API_KEY", "")
apollo_key  = os.environ.get("APOLLO_API_KEY", "")
DATA_FILE   = Path("data/jobs.json")

RECRUITER_TITLES = [
    "recruiter", "talent acquisition", "hr manager", "human resources",
    "hiring manager", "talent partner", "people operations",
    "technical recruiter", "engineering recruiter", "hr business partner",
    "head of talent", "director of recruiting", "sourcer", "staffing",
    "people partner", "workforce", "recruitment",
]

def load_jobs():
    return json.loads(DATA_FILE.read_text()) if DATA_FILE.exists() else {}

def save_jobs(jobs):
    DATA_FILE.write_text(json.dumps(jobs, indent=2))

def is_recruiter(title: str) -> bool:
    return any(r in title.lower() for r in RECRUITER_TITLES)

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

def scrape_company_website(domain: str) -> list:
    """
    Use Apify website-content-crawler to scrape company website
    for HR/recruiter emails. Scrapes company domain directly,
    not the Adzuna redirect URL.
    """
    if not apify_token:
        return []

    emails = []
    urls_to_try = [
        f"https://www.{domain}/careers",
        f"https://www.{domain}/about",
        f"https://www.{domain}/contact",
        f"https://{domain}",
    ]

    try:
        apify = ApifyClient(apify_token)

        for url in urls_to_try[:2]:  # Try first 2 to save credits
            try:
                print(f"  → Apify scraping: {url}")
                run = apify.actor("apify/website-content-crawler").call(
                    run_input={
                        "startUrls":   [{"url": url}],
                        "maxCrawlPages": 3,
                        "crawlerType": "cheerio",
                    },
                    timeout_secs=60,
                )

                items = list(apify.dataset(run["defaultDatasetId"]).iterate_items())
                for item in items:
                    text = item.get("text", "") or item.get("markdown", "")
                    found = re.findall(r'[\w.+-]+@[\w-]+\.[a-zA-Z]{2,}', text)
                    skip  = {"noreply", "no-reply", "support", "info", "help",
                              "privacy", "legal", "press", "admin", "abuse",
                              "example", "test", "sample", "sentry", "wix"}
                    for e in found:
                        local = e.split("@")[0].lower()
                        if not any(s in local for s in skip) and len(e) < 80:
                            emails.append(e)

                if emails:
                    break

            except Exception as e:
                print(f"  ! Scrape error: {str(e)[:60]}")
                continue

    except Exception as e:
        print(f"  ! Apify error: {str(e)[:80]}")

    return list(set(emails))[:5]

def find_recruiters_apollo(company: str, domain: str) -> list:
    """
    Use Apollo free plan /people/match endpoint.
    Search for HR/Recruiter people by title at the company domain.
    """
    if not apollo_key:
        return []

    recruiters = []
    print(f"  → Apollo searching recruiters at {company}...")

    # Apollo free plan supports /people/match with domain
    # Try common recruiter first names + company domain
    recruiter_searches = [
        {"title": "recruiter",           "domain": domain},
        {"title": "talent acquisition",  "domain": domain},
        {"title": "hr manager",          "domain": domain},
        {"title": "technical recruiter", "domain": domain},
    ]

    for search in recruiter_searches:
        if len(recruiters) >= 5:
            break
        try:
            response = requests.post(
                "https://api.apollo.io/api/v1/people/search",
                headers={
                    "Content-Type": "application/json",
                    "X-Api-Key":    apollo_key,
                },
                json={
                    "person_titles":        [search["title"]],
                    "organization_domains": [search["domain"]],
                    "person_locations":     ["United States"],
                    "per_page":             5,
                },
                timeout=20,
            )

            if response.status_code == 200:
                data   = response.json()
                people = data.get("people", [])
                print(f"  → Apollo found {len(people)} people for '{search['title']}'")

                for person in people:
                    name  = person.get("name", "")
                    title = person.get("title", "")
                    email = person.get("email", "")

                    if not email:
                        email = guess_email(name, domain)

                    if email and "@" in email and name:
                        if not any(r["email"] == email for r in recruiters):
                            recruiters.append({
                                "name":    name,
                                "title":   title,
                                "email":   email,
                                "source":  "apollo",
                                "linkedin": person.get("linkedin_url", ""),
                            })
                            print(f"  ✓ {name} — {title} → {email}")

            elif response.status_code == 403:
                # Try alternative endpoint for free plan
                print(f"  ! Apollo /people/search 403 — trying /people/match...")
                response2 = requests.get(
                    "https://api.apollo.io/api/v1/people/match",
                    params={
                        "api_key":    apollo_key,
                        "domain":     domain,
                        "title":      search["title"],
                    },
                    timeout=20,
                )
                if response2.status_code == 200:
                    data   = response2.json()
                    person = data.get("person", {})
                    if person:
                        name  = person.get("name", "")
                        title = person.get("title", "")
                        email = person.get("email", "") or guess_email(name, domain)
                        if email and name:
                            recruiters.append({
                                "name":   name,
                                "title":  title,
                                "email":  email,
                                "source": "apollo",
                            })
                            print(f"  ✓ {name} — {title} → {email}")
                else:
                    print(f"  ! Apollo error: {response2.status_code} {response2.text[:100]}")
                    break
            else:
                print(f"  ! Apollo error: {response.status_code} {response.text[:100]}")
                break

            time.sleep(1)

        except Exception as e:
            print(f"  ! Apollo error: {str(e)[:80]}")
            break

    return recruiters


def run_recruiter_finder():
    jobs    = load_jobs()
    updated = 0

    targets = [
        (jid, job) for jid, job in jobs.items()
        if (job.get("fit_score") or 0) >= 80
        and not job.get("email_sent")
        and job.get("recruiter_source") not in ["apollo", "apify_website", "company_site"]
    ]

    if not targets:
        print("[Recruiter Finder] No new jobs to process")
        return 0

    print(f"[Recruiter Finder] Processing {len(targets)} jobs...")

    for jid, job in targets[:15]:
        company = job.get("company", "").strip()
        domain  = company_to_domain(company)

        print(f"\n  [{company}] → {domain}")

        recruiters = []

        # Step 1 — Apollo finds verified recruiters
        apollo_results = find_recruiters_apollo(company, domain)
        recruiters.extend(apollo_results)

        # Step 2 — Apify scrapes company website for emails
        if len(recruiters) < 3:
            web_emails = scrape_company_website(domain)
            skip = {"noreply", "support", "info", "help", "privacy",
                    "legal", "press", "admin", "abuse", "no-reply"}
            for email in web_emails:
                local = email.split("@")[0].lower()
                if not any(s in local for s in skip):
                    if not any(r["email"] == email for r in recruiters):
                        recruiters.append({
                            "name":   "",
                            "title":  "HR Contact",
                            "email":  email,
                            "source": "company_site",
                        })
                        print(f"  ✓ Website email: {email}")

        # Step 3 — Fall back to careers@ pattern
        if not recruiters:
            print(f"  ! No contacts found — using careers@ fallback")
            recruiters = [{
                "name":   "",
                "title":  "HR Team",
                "email":  f"careers@{domain}",
                "source": "pattern_guess",
            }]

        # Deduplicate and limit
        seen   = set()
        unique = []
        for r in recruiters:
            if r["email"] not in seen:
                seen.add(r["email"])
                unique.append(r)
        recruiters = unique[:5]

        # Save
        jobs[jid]["recruiters"]       = recruiters
        jobs[jid]["recruiter_email"]  = recruiters[0]["email"]
        jobs[jid]["recruiter_name"]   = recruiters[0].get("name", "")
        jobs[jid]["recruiter_source"] = recruiters[0]["source"]

        print(f"  → {len(recruiters)} contact(s) saved:")
        for r in recruiters:
            label = f" ({r['name']})" if r.get("name") else ""
            print(f"     • {r['email']}{label}")

        updated += 1
        time.sleep(2)

    save_jobs(jobs)
    print(f"\n[Recruiter Finder] Done. {updated} jobs updated.")
    return updated

if __name__ == "__main__":
    run_recruiter_finder()
