"""
Job Agent Pipeline
Steps:
1. Scrape jobs
2. AI analysis + ATS resume + email draft
3. Find real recruiter emails via Claude + Apify MCP
4. Send cold emails
5. Portal auto-apply (Dice)
"""

import os, json
from pathlib import Path

def main():
    print("=" * 60)
    print("  JOB AGENT PIPELINE STARTED")
    print("=" * 60)

    # ── 1. SCRAPE ──────────────────────────────────────────────
    print("\n[1/5] SCRAPING JOBS")
    print("-" * 40)
    from scraper import run_scraper
    new_jobs = run_scraper()

    # ── 2. AI ANALYSIS ─────────────────────────────────────────
    print("\n[2/5] AI ANALYSIS + ATS RESUME + EMAIL DRAFTING")
    print("-" * 40)
    from ai_engine import run_ai_engine
    processed = run_ai_engine()

    # ── 3. FIND REAL RECRUITER EMAILS ──────────────────────────
    print("\n[3/5] FINDING RECRUITER CONTACTS (Claude + Apify MCP)")
    print("-" * 40)
    try:
        from recruiter_finder import run_recruiter_finder
        contacts_found = run_recruiter_finder()
        print(f"[Recruiter Finder] {contacts_found} real contacts found")
    except Exception as e:
        print(f"[Recruiter Finder] Error: {e}")

    # ── 4. SEND EMAILS ─────────────────────────────────────────
    print("\n[4/5] SENDING COLD EMAILS")
    print("-" * 40)
    from sender import run_sender
    emails_sent = run_sender()

    # ── 5. PORTAL APPLY ────────────────────────────────────────
    print("\n[5/5] PORTAL AUTO-APPLY")
    print("-" * 40)
    from apply_bot import run_apply_bot
    apps = run_apply_bot()

    # ── SUMMARY ────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("  PIPELINE COMPLETE")
    print(f"  New jobs scraped    : {new_jobs}")
    print(f"  AI processed        : {processed}")
    print(f"  Cold emails sent    : {emails_sent}")
    print(f"  Portal applications : {apps}")
    print("=" * 60)

if __name__ == "__main__":
    main()
