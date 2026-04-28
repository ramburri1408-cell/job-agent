"""
Pipeline — runs scraper → AI engine → sender in sequence.
"""

import sys, json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from scraper   import run_scraper
from ai_engine import run_ai_engine
from sender    import run_sender

def reset_skipped_jobs():
    """Reset skipped_low_score jobs back to new so they get reprocessed."""
    data_file = Path("data/jobs.json")
    if not data_file.exists():
        return 0
    jobs = json.loads(data_file.read_text())
    count = 0
    for jid, job in jobs.items():
        if job.get("status") == "skipped_low_score":
            jobs[jid]["status"] = "new"
            count += 1
    data_file.write_text(json.dumps(jobs, indent=2))
    print(f"[Reset] {count} skipped jobs reset to 'new'")
    return count

def main():
    print("=" * 60)
    print("  JOB AGENT PIPELINE STARTED")
    print("=" * 60)

    print("\n[0/3] RESETTING SKIPPED JOBS")
    print("-" * 40)
    reset_skipped_jobs()

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
