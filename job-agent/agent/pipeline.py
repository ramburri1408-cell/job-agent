"""
Pipeline — scraper → AI engine → email sender → apply bot
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from scraper    import run_scraper
from ai_engine  import run_ai_engine
from sender     import run_sender
from apply_bot  import run_apply_bot

def main():
    print("=" * 60)
    print("  JOB AGENT PIPELINE STARTED")
    print("=" * 60)

    print("\n[1/4] SCRAPING JOBS")
    print("-" * 40)
    new_jobs = run_scraper()

    print("\n[2/4] AI ANALYSIS + ATS RESUME + EMAIL DRAFTING")
    print("-" * 40)
    processed = run_ai_engine()

    print("\n[3/4] SENDING COLD EMAILS")
    print("-" * 40)
    sent = run_sender()

    print("\n[4/4] PORTAL AUTO-APPLY")
    print("-" * 40)
    applied = run_apply_bot()

    print("\n" + "=" * 60)
    print(f"  PIPELINE COMPLETE")
    print(f"  New jobs scraped    : {new_jobs}")
    print(f"  AI processed        : {processed}")
    print(f"  Cold emails sent    : {sent}")
    print(f"  Portal applications : {applied}")
    print("=" * 60)

if __name__ == "__main__":
    main()
