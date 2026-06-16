# 🤖 Autonomous Job Agent

Runs on **GitHub Actions (free)** — scrapes jobs every hour, tailors your resume with AI, and sends recruiter emails automatically. Zero server needed.

---

## What it does every hour

```
1. Scrape → Indeed, Dice, Remotive for your target roles
2. Analyze → Claude scores each job's fit against your profile
3. Tailor  → Claude rewrites your resume for each job
4. Draft   → Claude writes a personalized cold email
5. Send    → Gmail SMTP fires the email with resume attached
6. Log     → All activity committed to this repo
```

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
