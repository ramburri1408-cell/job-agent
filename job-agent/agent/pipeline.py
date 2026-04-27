"""
Pipeline — runs scraper → AI engine → sender in sequence.
Called by GitHub Actions on schedule.
"""

import sys
from pathlib import Path

# Ensure agent/ is on path when run from repo root
sys.path.insert(0, str(Path(__file__).parent))

from scraper   import run_scraper
from ai_engine import run_ai_engine
from sender    import run_sender

def main():
    print("=" * 60)
    print("  JOB AGENT PIPELINE STARTED")
    print("=" * 60)

    print("\n[1/3] SCRAPING JOBS")
    print("-" * 40)
    new_jobs = run_scraper()

    print("\n[2/3] AI ANALYSIS + RESUME TAILORING")
    print("-" * 40)
    processed = run_ai_engine()

    print("\n[3/3] SENDING EMAILS")
    print("-" * 40)
    sent = run_sender()

    print("\n" + "=" * 60)
    print(f"  PIPELINE COMPLETE")
    print(f"  New jobs scraped : {new_jobs}")
    print(f"  AI processed     : {processed}")
    print(f"  Emails sent      : {sent}")
    print("=" * 60)

if __name__ == "__main__":
    main()
