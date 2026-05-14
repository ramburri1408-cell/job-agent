"""
Job Agent Pipeline — 4 Steps
1. Scrape jobs
2. AI analysis + ATS resume generation
3. Find verified recruiter contacts (Hunter.io)
4. Send emails:
   - Job alert to Ram (JD + link + ATS resume)
   - Cold outreach to verified recruiters
"""

def main():
    print("=" * 60)
    print("  JOB AGENT PIPELINE STARTED")
    print("=" * 60)

    # 1. SCRAPE
    print("\n[1/4] SCRAPING JOBS")
    print("-" * 40)
    from scraper import run_scraper
    new_jobs = run_scraper()

    # 2. AI ANALYSIS + ATS RESUME
    print("\n[2/4] AI ANALYSIS + ATS RESUME")
    print("-" * 40)
    from ai_engine import run_ai_engine
    processed = run_ai_engine()

    # 3. FIND RECRUITERS
    print("\n[3/4] FINDING RECRUITER CONTACTS")
    print("-" * 40)
    try:
        from recruiter_finder import run_recruiter_finder
        contacts = run_recruiter_finder()
    except Exception as e:
        print(f"[Recruiter Finder] Error: {e}")
        contacts = 0

    # 4. SEND EMAILS
    print("\n[4/4] SENDING EMAILS")
    print("-" * 40)
    from sender import run_sender
    emails_sent = run_sender()

    print("\n" + "=" * 60)
    print("  PIPELINE COMPLETE")
    print(f"  New jobs scraped    : {new_jobs}")
    print(f"  AI processed        : {processed}")
    print(f"  Recruiter contacts  : {contacts}")
    print(f"  Emails sent         : {emails_sent}")
    print("=" * 60)

if __name__ == "__main__":
    main()
