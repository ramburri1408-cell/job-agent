"""
Recruiter Finder — Uses Claude + Apify MCP to find real recruiter emails
Flow:
1. Take job URL from scraped job
2. Claude triggers Apify actor to scrape the page
3. Extract recruiter name + email + LinkedIn
4. Fall back to email pattern guessing if nothing found
"""

import os, json, re
from pathlib import Path
import anthropic

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
APIFY_API_KEY = os.environ.get("APIFY_API_KEY", "")

DATA_FILE = Path("data/jobs.json")


def load_jobs():
    return json.loads(DATA_FILE.read_text()) if DATA_FILE.exists() else {}

def save_jobs(jobs):
    DATA_FILE.write_text(json.dumps(jobs, indent=2))


def find_recruiter_with_claude(job: dict) -> dict:
    """
    Uses Claude with Apify MCP to scrape job posting
    and extract recruiter contact info.
    Returns dict with name, email, linkedin fields.
    """
    url     = job.get("url", "")
    title   = job.get("title", "")
    company = job.get("company", "")

    if not url or url == "":
        return guess_email(company)

    print(f"  → Finding recruiter for {title} @ {company}")

    try:
        # Claude uses Apify MCP to scrape the job posting page
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1000,
            system=(
                "You are a recruiter contact finder. "
                "Use the Apify web scraper to fetch the job posting URL provided. "
                "Extract recruiter/hiring manager contact information from the page. "
                "Look for: name, email address, LinkedIn profile URL, phone number. "
                "Also check the company's careers page and LinkedIn company page if needed. "
                "Return ONLY valid JSON: "
                '{"name":"","email":"","linkedin":"","phone":"","source":"apify"} '
                "If no contact found return empty strings. Never invent contacts."
            ),
            messages=[{
                "role": "user",
                "content": (
                    f"Find the recruiter or hiring manager contact info for this job:\n"
                    f"Title: {title}\n"
                    f"Company: {company}\n"
                    f"Job URL: {url}\n\n"
                    f"Scrape the page and extract any recruiter contact information. "
                    f"Also try searching for '{company} recruiter' on LinkedIn via Apify."
                )
            }],
            # Apify MCP server
            extra_body={
                "mcp_servers": [{
                    "type": "url",
                    "url": f"https://mcp.apify.com/sse?token={APIFY_API_KEY}",
                    "name": "apify-mcp"
                }]
            }
        )

        # Parse Claude's response
        text = response.content[0].text.strip()
        # Extract JSON from response
        start = text.find("{")
        end   = text.rfind("}") + 1
        if start >= 0 and end > start:
            result = json.loads(text[start:end])
            # Validate email format
            if result.get("email") and "@" in result["email"]:
                print(f"  ✓ Found via Apify: {result['name']} <{result['email']}>")
                return result
            else:
                print(f"  ! No email found via Apify, using pattern guess")
                return guess_email(company, result.get("name", ""))

    except Exception as e:
        print(f"  ! Apify MCP error: {str(e)[:80]}")

    return guess_email(company)


def guess_email(company: str, name: str = "") -> dict:
    """
    Fallback — guess email from company name pattern.
    Common patterns: careers@, jobs@, recruiting@, hr@
    """
    domain = company_to_domain(company)

    # If we have a recruiter name, try name-based patterns
    if name:
        parts = name.lower().strip().split()
        if len(parts) >= 2:
            first, last = parts[0], parts[-1]
            # Most common corporate email patterns
            emails = [
                f"{first}.{last}@{domain}",
                f"{first[0]}{last}@{domain}",
                f"{first}@{domain}",
            ]
            email = emails[0]
        else:
            email = f"careers@{domain}"
    else:
        email = f"careers@{domain}"

    return {
        "name":    name or "",
        "email":   email,
        "linkedin": "",
        "phone":   "",
        "source":  "pattern_guess",
    }


def company_to_domain(company: str) -> str:
    """Convert company name to likely domain."""
    # Clean company name
    clean = company.lower()
    clean = re.sub(r'\b(inc|llc|ltd|corp|co|company|technologies|tech|solutions|services|group|global|systems)\b', '', clean)
    clean = re.sub(r'[^a-z0-9\s]', '', clean)
    clean = clean.strip().replace(' ', '')

    if not clean:
        clean = re.sub(r'[^a-z0-9]', '', company.lower())

    return f"{clean}.com"


def run_recruiter_finder():
    """
    Find recruiter emails for all jobs that:
    - Have been scored (fit_score is set)
    - Don't have a real recruiter email yet
    - Score >= 80 (worth finding real contact)
    """
    jobs      = load_jobs()
    updated   = 0
    min_score = 80

    for jid, job in jobs.items():
        # Skip if already has a real email
        existing = job.get("recruiter_email", "")
        if existing and "@" in existing and job.get("recruiter_source") == "apify":
            continue

        # Only find contacts for high-score jobs
        score = job.get("fit_score")
        if not score or score < min_score:
            continue

        # Skip if already emailed
        if job.get("email_sent"):
            continue

        # Find recruiter
        result = find_recruiter_with_claude(job)

        if result.get("email"):
            jobs[jid]["recruiter_email"]   = result["email"]
            jobs[jid]["recruiter_name"]    = result.get("name", "")
            jobs[jid]["recruiter_linkedin"] = result.get("linkedin", "")
            jobs[jid]["recruiter_source"]  = result.get("source", "unknown")
            updated += 1
            print(f"  ✓ Updated: {job['title']} @ {job['company']} → {result['email']}")

    save_jobs(jobs)
    print(f"\n[Recruiter Finder] Done. {updated} contacts found.")
    return updated


if __name__ == "__main__":
    run_recruiter_finder()
