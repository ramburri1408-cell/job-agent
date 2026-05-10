"""
Job Agent Pipeline — 6 Steps
1. Scrape jobs
2. AI analysis + ATS resume + email draft
3. Find real recruiter contacts
4. Send cold emails
5. Dice portal apply
6. Career page apply (iCIMS + Workday) — emails Ram to review + submit
"""

def main():
    print("=" * 60)
    print("  JOB AGENT PIPELINE STARTED")
    print("=" * 60)

    print("\n[1/6] SCRAPING JOBS")
    print("-" * 40)
    from scraper import run_scraper
    new_jobs = run_scraper()

    print("\n[2/6] AI ANALYSIS + ATS RESUME + EMAIL DRAFTING")
    print("-" * 40)
    from ai_engine import run_ai_engine
    processed = run_ai_engine()

    print("\n[3/6] FINDING RECRUITER CONTACTS")
    print("-" * 40)
    try:
        from recruiter_finder import run_recruiter_finder
        contacts = run_recruiter_finder()
    except Exception as e:
        print(f"[Recruiter Finder] Error: {e}")
        contacts = 0

    print("\n[4/6] SENDING COLD EMAILS")
    print("-" * 40)
    from sender import run_sender
    emails_sent = run_sender()

    print("\n[5/6] PORTAL AUTO-APPLY (Dice)")
    print("-" * 40)
    from apply_bot import run_apply_bot
    portal_apps = run_apply_bot()

    print("\n[6/6] CAREER PAGE APPLY (iCIMS + Workday)")
    print("-" * 40)
    try:
        from career_apply import run_career_apply
        career_apps = run_career_apply()
    except Exception as e:
        print(f"[Career Apply] Error: {e}")
        career_apps = 0

    print("\n" + "=" * 60)
    print("  PIPELINE COMPLETE")
    print(f"  New jobs scraped    : {new_jobs}")
    print(f"  AI processed        : {processed}")
    print(f"  Recruiter contacts  : {contacts}")
    print(f"  Cold emails sent    : {emails_sent}")
    print(f"  Dice applications   : {portal_apps}")
    print(f"  Career page forms   : {career_apps}")
    print("=" * 60)

if __name__ == "__main__":
    main()
