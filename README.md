# 🤖 Autonomous Job Agent

Runs on **GitHub Actions (free)** — scrapes jobs every hour, tailors your resume with AI, and sends recruiter emails automatically. Zero server needed.

---

## What it does every hour

```
1. Scrape    → Adzuna, Remotive, LinkedIn, Google Jobs for your target roles
2. Analyze   → Claude scores each job's fit against your profile
3. Tailor    → Claude rewrites your resume for each job
4. Draft     → Claude writes a personalized cold email
5. Send      → Gmail SMTP fires the email with resume attached
6. Auto-apply→ Claude re-checks the job's actual requirements on Dice,
               and if they meet your bar, submits Easy Apply automatically
7. Log       → All activity committed to this repo
```

### Auto-apply

`agent/apply_bot.py` runs as the last pipeline step (requires `DICE_EMAIL` /
`DICE_PASSWORD` secrets). For each Dice "Easy Apply" listing it finds, it:

1. Opens the job and reads the actual requirements/description text.
2. Asks Claude to score how well your profile meets those requirements.
3. Only if the score is at or above `min_apply_score` does it click Easy
   Apply, fill out the form (work authorization, salary, experience, etc.),
   attach your tailored resume, and submit.
4. Logs every submission to `data/apply_log.jsonl` and skips any job URL
   it has already applied to, so it never double-applies on later runs.

Control it in `data/config.json`:

- `"auto_apply_enabled": true` — set to `false` to turn off auto-submission
  entirely (the rest of the pipeline still runs).
- `"min_apply_score": 75` — how strict the requirements match must be
  before it will actually submit an application (0–100, independent of
  `min_fit_score` which only gates the recruiter email).

Other Easy Apply portals (Indeed, ZipRecruiter, Monster, JobRight) are
currently stubbed out — they block headless browsers/bot traffic.

### Career pages (Workday / Greenhouse / Lever / iCIMS / SmartRecruiters)

`agent/career_bot.py` runs right after the Dice bot, in the same pipeline
step. Instead of live-searching, it works off the jobs already scraped and
scored earlier in the run: any job whose `fit_score` (computed by
`ai_engine.py` from its actual requirements) is at or above
`min_apply_score` is a candidate. For each candidate it opens the job's
URL (following any tracking redirect first), figures out which career
platform the final page belongs to, and applies:

| Platform | Account needed? | Reliability |
|---|---|---|
| Greenhouse | No — guest form | Reliable, standard form fields |
| Lever | No — guest form | Reliable, standard form fields |
| Workday | Yes — creates one automatically | Best-effort; wizard steps vary per company |
| iCIMS / SmartRecruiters | Usually no | Best-effort; layout varies per company |

Workday requires a candidate account per company tenant. Set these secrets
to let it create one automatically:

| Secret name | Value |
|---|---|
| `WORKDAY_EMAIL` | Your email (defaults to `profile.email` in config.json if unset) |
| `WORKDAY_PASSWORD` | A password used to create your Workday account on each new tenant |

Other config knobs (in `data/config.json`):

- `"max_career_applies_per_run": 10` — cap on how many career-page
  applications it will attempt per pipeline run.

Every submission (Dice or career page) is logged to `data/apply_log.jsonl`,
and each job in `data/jobs.json` gets `career_applied`,
`career_apply_platform`, and `career_apply_note` fields recording the
outcome, so nothing is ever double-applied to.

---

## Setup (15 minutes)

### Step 1 — Fork this repo

Click **Fork** on GitHub. Keep it **private** (your resume will be in it).

---

### Step 2 — Add your secrets

Go to your forked repo → **Settings → Secrets and variables → Actions → New repository secret**

Add these 3 secrets:

| Secret name | Value |
|---|---|
| `ANTHROPIC_API_KEY` | Get from https://console.anthropic.com |
| `GMAIL_USER` | your.email@gmail.com |
| `GMAIL_APP_PASSWORD` | See Step 3 below |

---

### Step 3 — Create Gmail App Password

Gmail App Passwords let apps send email without your real password.

1. Go to https://myaccount.google.com/security
2. Enable **2-Step Verification** if not already on
3. Go to https://myaccount.google.com/apppasswords
4. Select app: **Mail** → Select device: **Other** → type "Job Agent"
5. Copy the 16-character password → paste as `GMAIL_APP_PASSWORD` secret

---

### Step 4 — Edit your profile

Edit **`data/config.json`**:

```json
{
  "job_queries": [
    "senior software engineer",
    "staff engineer react"
  ],
  "location": "remote",
  "min_fit_score": 65,
  "profile": {
    "name": "Your Real Name",
    "email": "you@gmail.com",
    "linkedin": "linkedin.com/in/you",
    ...
  }
}
```

- `job_queries` — what to search for on job boards
- `location` — "remote", "New York, NY", etc.
- `min_fit_score` — 0–100, jobs below this score are skipped (recommended: 60–70)

---

### Step 5 — Edit your resume

Edit **`data/resume.txt`** with your actual experience. The AI will tailor this per job — put your full real resume here.

---

### Step 6 — Enable Actions

Go to your repo → **Actions tab** → click **"I understand my workflows, go ahead and enable them"**

Then manually trigger the first run:
- Actions → **Job Agent 🤖** → **Run workflow**

Watch the logs. After that it runs automatically every hour.

---

## Files

```
.github/
  workflows/
    job-agent.yml     ← GitHub Actions schedule
agent/
  pipeline.py         ← runs all 3 steps in sequence
  scraper.py          ← scrapes Indeed, Dice, Remotive
  ai_engine.py        ← Claude analyzes + tailors + drafts
  sender.py           ← sends email via Gmail SMTP
data/
  config.json         ← YOUR CONFIG (edit this)
  resume.txt          ← YOUR RESUME (edit this)
  jobs.json           ← auto-generated, all job data
  email_log.jsonl     ← auto-generated, email history
```

---

## Monitoring

All job data is in `data/jobs.json`. Each job has a `status` field:

| Status | Meaning |
|---|---|
| `new` | Just scraped, not yet processed |
| `skipped_low_score` | Fit score below your threshold |
| `ai_ready` | Tailored + email drafted, ready to send |
| `applied` | Email sent ✓ |
| `email_failed` | Something went wrong sending |
| `no_email` | Couldn't find recruiter email |

Check **Actions → Job Agent → latest run → logs** to see live output.

---

## Costs

| Service | Cost |
|---|---|
| GitHub Actions | **Free** (2,000 min/month, each run ~2 min) |
| Claude API | ~$0.01–0.05 per job processed |
| Gmail SMTP | **Free** |

Running 24 hours/day processes ~10–50 new jobs/day depending on your search terms. Estimated Claude API cost: **$0.50–$2/day**.

---

## FAQ

**Will LinkedIn block me?**
LinkedIn aggressively blocks scrapers. This agent uses Indeed, Dice, and Remotive which are more accessible. If you want LinkedIn, you need a paid scraping proxy service.

**What if I want to review emails before sending?**
In `data/config.json` set `"min_fit_score": 999` — nothing will pass the threshold and all drafts will save to `jobs.json` for you to review without sending.

**Can I add more job boards?**
Yes — add a new scraper function in `agent/scraper.py` and call it in `run_scraper()`.

**How do I stop it?**
Go to Actions → Job Agent → three dots → **Disable workflow**.
