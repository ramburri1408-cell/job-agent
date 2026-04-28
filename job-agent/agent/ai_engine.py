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
DATA_FILE   = Path("data/jobs.json")
RESUME_FILE = Path("data/resume.txt")
CONFIG_FILE = Path("data/config.json")

def load_jobs():
    return json.loads(DATA_FILE.read_text()) if DATA_FILE.exists() else {}

def save_jobs(jobs):
    DATA_FILE.write_text(json.dumps(jobs, indent=2))

def load_resume():
    return RESUME_FILE.read_text() if RESUME_FILE.exists() else ""

def load_config():
    return json.loads(CONFIG_FILE.read_text()) if CONFIG_FILE.exists() else {}

def claude(system, user, max_tokens=1200):
    msg = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return msg.content[0].text.strip()

# ── Step 1: Analyze Fit ────────────────────────────────────────────────────

def analyze_fit(job, profile):
    result = claude(
        system=(
            "You are an expert technical recruiter. Analyze candidate fit. "
            "Return ONLY valid JSON, no markdown, no backticks, no extra text:\n"
            '{ "score": 75, "matched_skills": ["skill1"], "gaps": ["gap1"], '
            '"angle": "one sentence strongest selling point", '
            '"recruiter_name": "Hiring Manager", '
            '"recruiter_email": "careers@company.com" }'
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
        # Strip any accidental markdown
        clean = result.replace("```json", "").replace("```", "").strip()
        data  = json.loads(clean)
        # Force score to int
        data["score"] = int(data.get("score", 0))
        return data
    except Exception as e:
        print(f"  ! JSON parse error: {e} — raw: {result[:200]}")
        return {
            "score": 0,
            "matched_skills": [],
            "gaps": [],
            "angle": "Strong technical background",
            "recruiter_name": "Hiring Manager",
            "recruiter_email": "",
        }

# ── Step 2: Tailor Resume ──────────────────────────────────────────────────

def tailor_resume(job, resume, analysis):
    return claude(
        system=(
            "You are an expert resume writer. Rewrite the resume to strongly match "
            "this specific role. Reorder bullets to highlight most relevant experience. "
            "Adjust summary to speak to this company's needs. Keep all facts truthful. "
            "Output clean plain-text resume only — no commentary, no markdown headers."
        ),
        user=(
            f"Target role: {job['title']} at {job['company']}\n"
            f"Key angle: {analysis.get('angle', '')}\n"
            f"Top matched skills: {', '.join(analysis.get('matched_skills', [])[:6])}\n"
            f"Job description:\n{job['description'][:1000]}\n\n"
            f"Current resume:\n{resume}"
        ),
        max_tokens=1200,
    )

# ── Step 3: Draft Email ────────────────────────────────────────────────────

def draft_email(job, profile, analysis):
    recruiter = job.get("recruiter_name") or analysis.get("recruiter_name", "Hiring Manager")
    return claude(
        system=(
            f"You are writing as {profile['name']}. Write a concise confident cold outreach email. "
            "Line 1 must be: 'Subject: ...' then a blank line then the email body. "
            "3 short paragraphs: hook (why this company specifically), "
            "value (one specific achievement with numbers), ask (15-min call). "
            "Sound like a real senior engineer, not a cover letter. "
            "Never use phrases like 'I am excited' or 'I believe I would be a great fit'."
        ),
        user=(
            f"To: {recruiter} at {job['company']}\n"
            f"Role: {job['title']}\n"
            f"My angle: {analysis.get('angle', '')}\n"
            f"My top achievements: {profile.get('achievements', '')}\n"
            f"My LinkedIn: {profile.get('linkedin', '')}\n"
            f"My name: {profile['name']}"
        ),
        max_tokens=500,
    )

# ── Main ───────────────────────────────────────────────────────────────────

def run_ai_engine():
    config    = load_config()
    profile   = config.get("profile", {})
    resume    = load_resume()
    jobs      = load_jobs()
    min_score = int(config.get("min_fit_score", 45))
    processed = 0

    print(f"[AI Engine] Min fit score threshold: {min_score}")
    print(f"[AI Engine] Jobs to process: {sum(1 for j in jobs.values() if j.get('status') == 'new')}")

    for jid, job in jobs.items():
        if job.get("status") != "new":
            continue

        print(f"\n[AI] Processing: {job['title']} @ {job['company']}")

        # 1. Analyze fit
        print("  → Analyzing fit...")
        try:
            analysis = analyze_fit(job, profile)
        except Exception as e:
            print(f"  ! analyze_fit failed: {e}")
            jobs[jid]["status"] = "error"
            save_jobs(jobs)
            continue

        score = int(analysis.get("score", 0))
        print(f"  → Fit score: {score}/100 — {analysis.get('angle', '')}")

        if score < min_score:
            print(f"  ✗ Score {score} below threshold {min_score}, skipping.")
            jobs[jid]["status"] = "skipped_low_score"
            jobs[jid]["fit_score"] = score
            save_jobs(jobs)
            continue

        print(f"  ✓ Score {score} passes threshold {min_score}, continuing...")

        # Fill recruiter info if AI guessed it
        if not job.get("recruiter_email") and analysis.get("recruiter_email"):
            jobs[jid]["recruiter_email"] = analysis["recruiter_email"]
        if not job.get("recruiter_name") and analysis.get("recruiter_name"):
            jobs[jid]["recruiter_name"] = analysis["recruiter_name"]

        # 2. Tailor resume
        print("  → Tailoring resume...")
        try:
            tailored = tailor_resume(job, resume, analysis)
            jobs[jid]["tailored_resume"] = tailored
        except Exception as e:
            print(f"  ! tailor_resume failed: {e}")
            jobs[jid]["status"] = "error"
            save_jobs(jobs)
            continue

        # 3. Draft email
        print("  → Drafting recruiter email...")
        try:
            email_draft = draft_email(job, profile, analysis)
            jobs[jid]["email_draft"] = email_draft
        except Exception as e:
            print(f"  ! draft_email failed: {e}")
            jobs[jid]["status"] = "error"
            save_jobs(jobs)
            continue

        jobs[jid]["fit_score"]    = score
        jobs[jid]["fit_analysis"] = analysis
        jobs[jid]["status"]       = "ai_ready"
        save_jobs(jobs)
        processed += 1
        print(f"  ✓ Done — ready to send")

    print(f"\n[AI Engine] Complete. {processed} jobs processed.")
    return processed


if __name__ == "__main__":
    run_ai_engine()
