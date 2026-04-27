"""
AI Engine — uses Claude to:
  1. Score job fit
  2. Tailor resume
  3. Draft recruiter email
"""

import json, os
from pathlib import Path
import anthropic

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
DATA_FILE  = Path("data/jobs.json")
RESUME_FILE = Path("data/resume.txt")
CONFIG_FILE = Path("data/config.json")

def load_jobs() -> dict:
    return json.loads(DATA_FILE.read_text()) if DATA_FILE.exists() else {}

def save_jobs(jobs: dict):
    DATA_FILE.write_text(json.dumps(jobs, indent=2))

def load_resume() -> str:
    return RESUME_FILE.read_text() if RESUME_FILE.exists() else ""

def load_config() -> dict:
    return json.loads(CONFIG_FILE.read_text()) if CONFIG_FILE.exists() else {}

def claude(system: str, user: str, max_tokens: int = 1200) -> str:
    msg = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return msg.content[0].text.strip()

# ── Step 1: Analyze Fit ────────────────────────────────────────────────────

def analyze_fit(job: dict, profile: dict) -> dict:
    result = claude(
        system=(
            "You are an expert technical recruiter. Analyze candidate fit. "
            "Return ONLY valid JSON, no markdown, no backticks:\n"
            '{ "score": 0-100, "matched_skills": [], "gaps": [], '
            '"angle": "one sentence strongest selling point", '
            '"recruiter_name": "guess from company if unknown", '
            '"recruiter_email": "guess company careers email if unknown" }'
        ),
        user=(
            f"Job: {job['title']} at {job['company']}\n"
            f"Location: {job['location']}\n"
            f"Description:\n{job['description'][:1500]}\n\n"
            f"Candidate skills: {profile.get('skills', '')}\n"
            f"Experience summary: {profile.get('summary', '')}"
        ),
        max_tokens=400,
    )
    try:
        data = json.loads(result)
    except Exception:
        data = {"score": 60, "matched_skills": [], "gaps": [], "angle": "Strong technical background",
                "recruiter_name": "Hiring Manager", "recruiter_email": ""}
    return data

# ── Step 2: Tailor Resume ──────────────────────────────────────────────────

def tailor_resume(job: dict, resume: str, analysis: dict) -> str:
    return claude(
        system=(
            "You are an expert resume writer. Rewrite the resume to strongly match "
            "this specific role. Reorder bullets to highlight most relevant experience. "
            "Adjust summary to speak to this company's needs. Keep all facts truthful. "
            "Output clean plain-text resume only — no commentary, no markdown headers."
        ),
        user=(
            f"Target role: {job['title']} at {job['company']}\n"
            f"Key angle: {analysis.get('angle','')}\n"
            f"Top matched skills: {', '.join(analysis.get('matched_skills',[])[:6])}\n"
            f"Job description:\n{job['description'][:1000]}\n\n"
            f"Current resume:\n{resume}"
        ),
        max_tokens=1200,
    )

# ── Step 3: Draft Email ────────────────────────────────────────────────────

def draft_email(job: dict, profile: dict, analysis: dict) -> str:
    recruiter = job.get("recruiter_name") or analysis.get("recruiter_name", "Hiring Manager")
    return claude(
        system=(
            f"You are writing as {profile['name']}. Write a concise confident cold outreach email. "
            "Line 1: 'Subject: ...' then blank line then email body. "
            "3 short paragraphs: hook (why this company specifically), "
            "value (one specific achievement with numbers), ask (15-min call). "
            "Sound like a real senior engineer, not a cover letter. "
            "No phrases like 'I am excited' or 'I believe I would be a great fit'."
        ),
        user=(
            f"To: {recruiter} at {job['company']}\n"
            f"Role: {job['title']}\n"
            f"My angle: {analysis.get('angle','')}\n"
            f"My top achievements: {profile.get('achievements','')}\n"
            f"My LinkedIn: {profile.get('linkedin','')}\n"
            f"My name: {profile['name']}"
        ),
        max_tokens=500,
    )

# ── Main ───────────────────────────────────────────────────────────────────

def run_ai_engine():
    config  = load_config()
    profile = config.get("profile", {})
    resume  = load_resume()
    jobs    = load_jobs()

    min_score  = config.get("min_fit_score", 60)
    processed  = 0

    for jid, job in jobs.items():
        # Only process new jobs not yet AI-processed
        if job.get("status") != "new":
            continue

        print(f"\n[AI] Processing: {job['title']} @ {job['company']}")

        # 1. Analyze
        print("  → Analyzing fit...")
        analysis = analyze_fit(job, profile)
        score    = analysis.get("score", 0)
        print(f"  → Fit score: {score}/100 — {analysis.get('angle','')}")

        if score < min_score:
            print(f"  ✗ Score below threshold ({min_score}), skipping.")
            jobs[jid]["status"] = "skipped_low_score"
            jobs[jid]["fit_score"] = score
            save_jobs(jobs)
            continue

        # Fill in recruiter info if AI guessed it
        if not job.get("recruiter_email") and analysis.get("recruiter_email"):
            jobs[jid]["recruiter_email"] = analysis["recruiter_email"]
        if not job.get("recruiter_name") and analysis.get("recruiter_name"):
            jobs[jid]["recruiter_name"] = analysis["recruiter_name"]

        # 2. Tailor resume
        print("  → Tailoring resume...")
        tailored = tailor_resume(job, resume, analysis)
        jobs[jid]["tailored_resume"] = tailored

        # 3. Draft email
        print("  → Drafting recruiter email...")
        email_draft = draft_email(job, profile, analysis)
        jobs[jid]["email_draft"] = email_draft

        jobs[jid]["fit_score"] = score
        jobs[jid]["fit_analysis"] = analysis
        jobs[jid]["status"] = "ai_ready"
        save_jobs(jobs)
        processed += 1
        print(f"  ✓ Done — ready to send")

    print(f"\n[AI Engine] Complete. {processed} jobs processed.")
    return processed


if __name__ == "__main__":
    run_ai_engine()
