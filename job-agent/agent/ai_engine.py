"""
AI Engine — scores job fit, generates ATS resume, drafts email.
Model: claude-opus-4-8
Flow: Scrape -> ATS Resume -> Score -> Email Ram -> Email Recruiter
"""

import json, os, sys, tempfile
from pathlib import Path
import anthropic

client      = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
DATA_FILE   = Path("data/jobs.json")
CONFIG_FILE = Path("data/config.json")

# Windows-safe temp directory
TMP_DIR = Path(tempfile.gettempdir()) / "job_agent_resumes"
TMP_DIR.mkdir(parents=True, exist_ok=True)

def load_jobs():
    return json.loads(DATA_FILE.read_text(encoding="utf-8")) if DATA_FILE.exists() else {}

def save_jobs(jobs):
    DATA_FILE.write_text(json.dumps(jobs, indent=2), encoding="utf-8")

def load_config():
    return json.loads(CONFIG_FILE.read_text(encoding="utf-8")) if CONFIG_FILE.exists() else {}

def claude(system, user, max_tokens=500):
    return client.messages.create(
        model="claude-opus-4-8",
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
    ).content[0].text.strip()

# ── Keyword pre-filter ────────────────────────────────────────────────────────
RELEVANT = [
    "net", "c#", "csharp", "asp", "react", "angular", "full stack",
    "fullstack", "software engineer", "software developer", "application developer",
    "frontend", "backend", "azure", "dotnet", "typescript", "node", "python", "ai",
    "automation", "engineer", "developer"
]

def is_relevant(job):
    text = (job.get("title", "") + " " + job.get("description", "")[:300]).lower()
    return any(kw in text for kw in RELEVANT)

# ── Step 1: Fit analysis ──────────────────────────────────────────────────────
def analyze_fit(job, profile):
    raw = claude(
        system=(
            "You are an expert technical recruiter. Analyze candidate fit for this job.\n"
            "Return ONLY valid JSON, no markdown, no backticks:\n"
            '{"score":75,"matched_skills":["C#",".NET"],"gaps":["Kubernetes"],'
            '"angle":"Strong .NET developer with Azure and React experience matching this role perfectly",'
            '"recruiter_name":"Hiring Manager",'
            '"recruiter_email":"careers@company.com"}'
        ),
        user=(
            f"Job: {job['title']} at {job['company']}\n"
            f"Location: {job['location']}\n"
            f"Description:\n{job['description'][:2000]}\n\n"
            f"Candidate: {profile.get('name', 'Ram Burri')}\n"
            f"Current Role: {profile.get('current_role', '')}\n"
            f"Skills: {profile.get('skills', '')}\n"
            f"Summary: {profile.get('summary', '')}\n"
            f"Experience: {profile.get('years_experience', 4)} years"
        ),
        max_tokens=400,
    )
    try:
        clean = raw.replace("```json", "").replace("```", "").strip()
        d = json.loads(clean)
        d["score"] = int(d.get("score", 0))
        return d
    except Exception as e:
        print(f"  ! JSON parse error: {e}")
        return {"score": 0, "matched_skills": [], "gaps": [],
                "angle": "Strong .NET and Azure background",
                "recruiter_name": "Hiring Manager", "recruiter_email": ""}

# ── Step 2: Draft cold email to recruiter ─────────────────────────────────────
def draft_recruiter_email(job, profile, analysis):
    recruiter = job.get("recruiter_name") or analysis.get("recruiter_name", "Hiring Manager")
    return claude(
        system=(
            f"You are {profile['name']}, a senior software engineer applying for a job. "
            "Write a short cold outreach email to a recruiter. "
            "Format: Line 1 = 'Subject: ...' then blank line then 3 short paragraphs. "
            "Para 1: Why this company/role. Para 2: Specific achievement with numbers. Para 3: Ask for 15-min call. "
            "Be direct, sound like a real engineer. No 'excited' or 'passionate' clichés."
        ),
        user=(
            f"To: {recruiter} at {job['company']}\n"
            f"Role: {job['title']}\n"
            f"Why I fit: {analysis.get('angle', '')}\n"
            f"My achievements: {profile.get('achievements', '')}\n"
            f"LinkedIn: {profile.get('linkedin', '')}\n"
            f"GitHub: {profile.get('github', '')}\n"
            f"My name: {profile['name']}\n"
            f"My email: {profile['email']}"
        ),
        max_tokens=500,
    )

# ── Step 3: Draft Ram alert email ─────────────────────────────────────────────
def draft_ram_email(job, profile, analysis, resume_path):
    score        = analysis.get("score", 0)
    matched      = ", ".join(analysis.get("matched_skills", []))
    gaps         = ", ".join(analysis.get("gaps", []))
    angle        = analysis.get("angle", "")
    recruiter    = job.get("recruiter_name") or "Not found"
    rec_email    = job.get("recruiter_email") or "Not found"

    subject = f"Job Match {score}/100: {job['title']} @ {job['company']}"
    body = (
        f"New job match found!\n\n"
        f"POSITION: {job['title']}\n"
        f"COMPANY:  {job['company']}\n"
        f"LOCATION: {job['location']}\n"
        f"SALARY:   {job.get('salary', 'Not listed')}\n"
        f"SOURCE:   {job.get('portal', '')}\n\n"
        f"APPLY HERE: {job['url']}\n\n"
        f"FIT SCORE: {score}/100\n"
        f"WHY YOU FIT: {angle}\n"
        f"MATCHED SKILLS: {matched}\n"
        f"GAPS: {gaps}\n\n"
        f"RECRUITER: {recruiter}\n"
        f"RECRUITER EMAIL: {rec_email}\n\n"
        f"ATS RESUME: Attached as PDF\n\n"
        f"JOB DESCRIPTION:\n{job.get('description', '')[:2000]}"
    )
    return subject, body

# ── Main ──────────────────────────────────────────────────────────────────────
def run_ai_engine():
    config      = load_config()
    profile     = config.get("profile", {})
    jobs        = load_jobs()
    min_score   = int(config.get("min_fit_score", 70))
    max_per_run = int(config.get("max_jobs_per_run", 15))
    processed   = 0

    if not profile.get("name"):
        print("[AI Engine] ERROR: Profile is empty in config.json!")
        return 0

    from ats_resume import generate_ats_resume

    new_jobs = [j for j in jobs.values() if j.get("status") == "new"]
    print(f"[AI Engine] Model: claude-opus-4-8 | Profile: {profile['name']} | Min score: {min_score} | New jobs: {len(new_jobs)}")

    for jid, job in jobs.items():
        if job.get("status") != "new":
            continue
        if processed >= max_per_run:
            print(f"[AI Engine] Reached limit of {max_per_run}. Stopping.")
            break

        # Pre-filter
        if not is_relevant(job):
            print(f"  x Irrelevant: {job['title']} @ {job['company']}")
            jobs[jid]["status"] = "skipped_irrelevant"
            save_jobs(jobs)
            continue

        print(f"\n[AI] {job['title']} @ {job['company']}")

        # Step 1: Score fit
        try:
            analysis = analyze_fit(job, profile)
        except Exception as e:
            print(f"  ! analyze_fit error: {e}")
            jobs[jid]["status"] = "error"
            save_jobs(jobs)
            continue

        score = int(analysis.get("score", 0))
        print(f"  Score: {score}/100 -- {analysis.get('angle', '')}")

        if score < min_score:
            print(f"  x Below threshold {min_score}")
            jobs[jid]["status"]    = "skipped_low_score"
            jobs[jid]["fit_score"] = score
            save_jobs(jobs)
            continue

        # Update recruiter info from AI analysis
        if not job.get("recruiter_email") and analysis.get("recruiter_email"):
            jobs[jid]["recruiter_email"] = analysis["recruiter_email"]
        if not job.get("recruiter_name") and analysis.get("recruiter_name"):
            jobs[jid]["recruiter_name"] = analysis["recruiter_name"]

        # Step 2: Generate ATS resume tailored to this JD
        try:
            result = generate_ats_resume(job, output_dir=str(TMP_DIR))
            jobs[jid]["resume_pdf"]      = result["pdf_path"]
            jobs[jid]["tailored_resume"] = json.dumps(result["enhanced"])
            print(f"  ATS resume: {result['pdf_path']}")
        except Exception as e:
            print(f"  ! ATS resume error: {e}")
            jobs[jid]["resume_pdf"]      = ""
            jobs[jid]["tailored_resume"] = ""

        # Step 3: Draft recruiter cold email
        try:
            jobs[jid]["email_draft"] = draft_recruiter_email(job, profile, analysis)
        except Exception as e:
            print(f"  ! Email draft error: {e}")
            jobs[jid]["email_draft"] = ""

        # Step 4: Build Ram alert email
        try:
            subject, body = draft_ram_email(job, profile, analysis, jobs[jid].get("resume_pdf", ""))
            jobs[jid]["ram_email_subject"] = subject
            jobs[jid]["ram_email_body"]    = body
        except Exception as e:
            print(f"  ! Ram email error: {e}")

        jobs[jid]["fit_score"]    = score
        jobs[jid]["fit_analysis"] = analysis
        jobs[jid]["status"]       = "ai_ready"
        save_jobs(jobs)
        processed += 1
        print(f"  Ready to send!")

    print(f"\n[AI Engine] Done. {processed} jobs processed.")
    return processed

if __name__ == "__main__":
    run_ai_engine()
