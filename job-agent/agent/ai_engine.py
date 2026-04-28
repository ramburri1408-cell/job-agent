"""
AI Engine — scores job fit, generates ATS resume, drafts email.
Pure Python — no Node.js, no LibreOffice.
"""

import json, os
from pathlib import Path
import anthropic

client    = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
DATA_FILE = Path("data/jobs.json")
CONFIG_FILE = Path("data/config.json")

def load_jobs():
    return json.loads(DATA_FILE.read_text()) if DATA_FILE.exists() else {}

def save_jobs(jobs):
    DATA_FILE.write_text(json.dumps(jobs, indent=2))

def load_config():
    return json.loads(CONFIG_FILE.read_text()) if CONFIG_FILE.exists() else {}

def claude(system, user, max_tokens=500):
    return client.messages.create(
        model="claude-opus-4-5", max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
    ).content[0].text.strip()

# ── Keyword pre-filter ─────────────────────────────────────────────────────
RELEVANT = [
    "net", "c#", "csharp", "asp", "react", "angular", "full stack",
    "fullstack", "software engineer", "software developer", "application developer",
    "frontend", "backend", "azure", "dotnet", "typescript", "node"
]

def is_relevant(job):
    text = (job.get("title","") + " " + job.get("description","")[:300]).lower()
    return any(kw in text for kw in RELEVANT)

# ── Step 1: Fit analysis ───────────────────────────────────────────────────
def analyze_fit(job, profile):
    raw = claude(
        system=(
            "Expert technical recruiter. Analyze fit. "
            "Return ONLY valid JSON no markdown:\n"
            '{"score":75,"matched_skills":["s1"],"gaps":["g1"],'
            '"angle":"one sentence selling point",'
            '"recruiter_name":"Hiring Manager",'
            '"recruiter_email":"careers@company.com"}'
        ),
        user=(
            f"Job: {job['title']} at {job['company']}\n"
            f"Location: {job['location']}\n"
            f"Description:\n{job['description'][:1500]}\n\n"
            f"Candidate skills: {profile.get('skills','')}\n"
            f"Summary: {profile.get('summary','')}"
        ),
        max_tokens=400,
    )
    try:
        d = json.loads(raw.replace("```json","").replace("```","").strip())
        d["score"] = int(d.get("score", 0))
        return d
    except Exception:
        return {"score":0,"matched_skills":[],"gaps":[],"angle":"Strong background",
                "recruiter_name":"Hiring Manager","recruiter_email":""}

# ── Step 2: Draft email ────────────────────────────────────────────────────
def draft_email(job, profile, analysis):
    recruiter = job.get("recruiter_name") or analysis.get("recruiter_name","Hiring Manager")
    return claude(
        system=(
            f"You are {profile['name']}. Write a concise cold outreach email. "
            "Line 1: 'Subject: ...' then blank line then body. "
            "3 short paragraphs: hook (why this company), value (achievement with numbers), ask (15-min call). "
            "Sound like a real engineer. No 'I am excited' or 'great fit' phrases."
        ),
        user=(
            f"To: {recruiter} at {job['company']}\n"
            f"Role: {job['title']}\n"
            f"Angle: {analysis.get('angle','')}\n"
            f"Achievements: {profile.get('achievements','')}\n"
            f"LinkedIn: {profile.get('linkedin','')}\n"
            f"Name: {profile['name']}"
        ),
        max_tokens=500,
    )

# ── Main ───────────────────────────────────────────────────────────────────
def run_ai_engine():
    config      = load_config()
    profile     = config.get("profile", {})
    jobs        = load_jobs()
    min_score   = int(config.get("min_fit_score", 45))
    max_per_run = int(config.get("max_jobs_per_run", 15))
    processed   = 0

    from ats_resume import generate_ats_resume

    new_jobs = [j for j in jobs.values() if j.get("status") == "new"]
    print(f"[AI Engine] Min score: {min_score} | Max per run: {max_per_run} | New jobs: {len(new_jobs)}")

    for jid, job in jobs.items():
        if job.get("status") != "new":
            continue
        if processed >= max_per_run:
            print(f"[AI Engine] Reached limit of {max_per_run}. Stopping.")
            break

        # Pre-filter
        if not is_relevant(job):
            print(f"  ✗ Irrelevant: {job['title']} @ {job['company']}")
            jobs[jid]["status"] = "skipped_irrelevant"
            save_jobs(jobs)
            continue

        print(f"\n[AI] {job['title']} @ {job['company']}")

        # 1. Fit score
        try:
            analysis = analyze_fit(job, profile)
        except Exception as e:
            print(f"  ! analyze_fit error: {e}")
            jobs[jid]["status"] = "error"; save_jobs(jobs); continue

        score = int(analysis.get("score", 0))
        print(f"  → Score: {score}/100 — {analysis.get('angle','')}")

        if score < min_score:
            print(f"  ✗ Below threshold {min_score}")
            jobs[jid]["status"]    = "skipped_low_score"
            jobs[jid]["fit_score"] = score
            save_jobs(jobs); continue

        # Fill recruiter info
        if not job.get("recruiter_email") and analysis.get("recruiter_email"):
            jobs[jid]["recruiter_email"] = analysis["recruiter_email"]
        if not job.get("recruiter_name") and analysis.get("recruiter_name"):
            jobs[jid]["recruiter_name"] = analysis["recruiter_name"]

        # 2. ATS Resume
        try:
            result = generate_ats_resume(job, output_dir="/tmp")
            jobs[jid]["resume_pdf"]      = result["pdf_path"]
            jobs[jid]["tailored_resume"] = json.dumps(result["enhanced"])
        except Exception as e:
            print(f"  ! ATS resume error: {e}")
            jobs[jid]["tailored_resume"] = ""

        # 3. Email draft
        try:
            jobs[jid]["email_draft"] = draft_email(job, profile, analysis)
        except Exception as e:
            print(f"  ! Email draft error: {e}")
            jobs[jid]["status"] = "error"; save_jobs(jobs); continue

        jobs[jid]["fit_score"]    = score
        jobs[jid]["fit_analysis"] = analysis
        jobs[jid]["status"]       = "ai_ready"
        save_jobs(jobs)
        processed += 1
        print(f"  ✓ Ready to send")

    print(f"\n[AI Engine] Done. {processed} processed.")
    return processed

if __name__ == "__main__":
    run_ai_engine()
