"""
Multi-Portal Apply Bot
Automatically applies to jobs on:
- Indeed (Google login)
- ZipRecruiter (Google login)
- Monster (Google login)
- JobRight.ai (Google login)
- Dice (email/password)

Uses Playwright for browser automation.
AI answers all screening questions.
Uploads tailored ATS PDF resume.
"""

import json, os, time, tempfile, traceback
from pathlib import Path
from datetime import datetime, timezone
import anthropic

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

# Credentials
GOOGLE_EMAIL    = os.environ.get("GOOGLE_EMAIL", "")
GOOGLE_PASSWORD = os.environ.get("GOOGLE_PASSWORD", "")
DICE_EMAIL      = os.environ.get("DICE_EMAIL", "")
DICE_PASSWORD   = os.environ.get("DICE_PASSWORD", "")

DATA_FILE  = Path("data/jobs.json")
LOG_FILE   = Path("data/apply_log.jsonl")
CONFIG_FILE = Path("data/config.json")

PROFILE = {
    "name":       "Ram Burri",
    "email":      "Ram.burri1408@gmail.com",
    "phone":      "9544454339",
    "location":   "Boca Raton, FL",
    "linkedin":   "linkedin.com/in/ramburri",
    "github":     "github.com/ramburri",
    "experience": "4",
    "title":      "Full Stack .NET Developer",
    "salary":     "100000",
    "visa":       "OPT",
    "authorized": "Yes",
    "sponsorship":"No",
}

def load_jobs():
    return json.loads(DATA_FILE.read_text()) if DATA_FILE.exists() else {}

def save_jobs(jobs):
    DATA_FILE.write_text(json.dumps(jobs, indent=2))

def log_apply(entry):
    LOG_FILE.parent.mkdir(exist_ok=True)
    with LOG_FILE.open("a") as f:
        f.write(json.dumps(entry) + "\n")

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def ai_answer(question, job_title="", options=None):
    """Use Claude to answer screening questions."""
    opts = f"\nOptions: {options}" if options else ""
    result = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=100,
        system=(
            "You are filling out a job application for Ram Burri, "
            "a Full Stack .NET Developer with 4+ years experience. "
            "Answer screening questions briefly and professionally. "
            "For yes/no questions answer Yes or No only. "
            "For experience questions use numbers. "
            "For salary expectations say 100000-130000. "
            "Never say you are an AI."
        ),
        messages=[{"role": "user", "content":
            f"Job: {job_title}\nQuestion: {question}{opts}\n"
            f"Candidate: {json.dumps(PROFILE)}\nAnswer briefly:"
        }]
    ).content[0].text.strip()
    return result

def get_resume_pdf(job):
    """Get the ATS PDF for this job."""
    pdf_path = job.get("resume_pdf")
    if pdf_path and Path(pdf_path).exists():
        return pdf_path

    # Generate fresh PDF
    try:
        from ats_resume import generate_ats_resume
        result = generate_ats_resume(job, output_dir="/tmp")
        return result["pdf_path"]
    except Exception as e:
        print(f"  ! Could not generate PDF: {e}")
        return None


# ── Google OAuth Helper ────────────────────────────────────────────────────

def google_login(page, email, password):
    """Handle Google OAuth login flow."""
    try:
        page.wait_for_selector('input[type="email"]', timeout=10000)
        page.fill('input[type="email"]', email)
        page.click('button:has-text("Next"), #identifierNext')
        page.wait_for_timeout(2000)
        page.wait_for_selector('input[type="password"]', timeout=10000)
        page.fill('input[type="password"]', password)
        page.click('button:has-text("Next"), #passwordNext')
        page.wait_for_timeout(3000)
        print("  ✓ Google login successful")
        return True
    except Exception as e:
        print(f"  ! Google login failed: {e}")
        return False

def handle_screening_questions(page, job_title):
    """Find and answer all screening questions on the page."""
    answered = 0
    try:
        # Text inputs
        inputs = page.query_selector_all('input[type="text"], input[type="number"]')
        for inp in inputs:
            label = ""
            try:
                label_el = page.query_selector(f'label[for="{inp.get_attribute("id")}"]')
                if label_el:
                    label = label_el.inner_text()
                elif inp.get_attribute("placeholder"):
                    label = inp.get_attribute("placeholder")
                elif inp.get_attribute("aria-label"):
                    label = inp.get_attribute("aria-label")
            except:
                pass

            if not label or inp.input_value():
                continue

            answer = ai_answer(label, job_title)
            inp.fill(answer)
            answered += 1
            page.wait_for_timeout(300)

        # Dropdowns / selects
        selects = page.query_selector_all("select")
        for sel in selects:
            try:
                label = ""
                sel_id = sel.get_attribute("id")
                if sel_id:
                    label_el = page.query_selector(f'label[for="{sel_id}"]')
                    if label_el:
                        label = label_el.inner_text()

                options = [o.inner_text() for o in sel.query_selector_all("option") if o.inner_text().strip()]
                if label and options:
                    answer = ai_answer(label, job_title, options)
                    # Pick closest matching option
                    best = options[0]
                    for opt in options:
                        if answer.lower() in opt.lower() or opt.lower() in answer.lower():
                            best = opt
                            break
                    sel.select_option(label=best)
                    answered += 1
            except:
                pass

        # Radio buttons / Yes-No
        radios = page.query_selector_all('input[type="radio"]')
        seen_names = set()
        for radio in radios:
            name = radio.get_attribute("name")
            if name in seen_names:
                continue
            seen_names.add(name)
            try:
                label_el = page.query_selector(f'label[for="{radio.get_attribute("id")}"]')
                question = label_el.inner_text() if label_el else name
                answer   = ai_answer(question, job_title)
                # Click matching radio
                all_radios = page.query_selector_all(f'input[name="{name}"]')
                for r in all_radios:
                    r_label = page.query_selector(f'label[for="{r.get_attribute("id")}"]')
                    if r_label and answer.lower() in r_label.inner_text().lower():
                        r.click()
                        answered += 1
                        break
            except:
                pass

    except Exception as e:
        print(f"  ! Screening questions error: {e}")

    if answered > 0:
        print(f"  → Answered {answered} screening questions")


# ── INDEED ─────────────────────────────────────────────────────────────────

def apply_indeed(page, jobs):
    """Apply to jobs on Indeed."""
    applied = 0
    print("\n[Indeed] Starting...")

    try:
        page.goto("https://www.indeed.com/account/login", timeout=30000)
        page.wait_for_timeout(2000)

        # Click Google login
        google_btn = page.query_selector('button:has-text("Google"), a:has-text("Google")')
        if google_btn:
            google_btn.click()
            page.wait_for_timeout(2000)
            if not google_login(page, GOOGLE_EMAIL, GOOGLE_PASSWORD):
                return 0
        else:
            print("  ! Google button not found on Indeed")
            return 0

        page.wait_for_timeout(3000)

        for jid, job in jobs.items():
            if job.get("portal") not in ["Indeed", "Indeed (via Adzuna)", "Adzuna"] :
                continue
            if job.get("portal_applied"):
                continue
            if job.get("status") not in ["applied", "ai_ready"]:
                continue

            try:
                print(f"  → Applying: {job['title']} @ {job['company']}")
                job_url = job.get("url", "")
                if not job_url:
                    continue

                page.goto(job_url, timeout=30000)
                page.wait_for_timeout(2000)

                # Click Apply button
                apply_btn = page.query_selector(
                    'button:has-text("Apply now"), '
                    'button:has-text("Apply"), '
                    'a:has-text("Apply now")'
                )
                if not apply_btn:
                    print(f"  ! No apply button found")
                    continue

                apply_btn.click()
                page.wait_for_timeout(3000)

                # Upload resume if prompted
                resume_input = page.query_selector('input[type="file"]')
                if resume_input:
                    pdf_path = get_resume_pdf(job)
                    if pdf_path:
                        resume_input.set_input_files(pdf_path)
                        page.wait_for_timeout(2000)
                        print(f"  → Resume uploaded")

                # Answer screening questions
                handle_screening_questions(page, job["title"])

                # Submit
                submit_btn = page.query_selector(
                    'button:has-text("Submit"), '
                    'button:has-text("Continue"), '
                    'button[type="submit"]'
                )
                if submit_btn:
                    submit_btn.click()
                    page.wait_for_timeout(3000)
                    jobs[jid]["portal_applied"] = True
                    jobs[jid]["portal_applied_at"] = now_iso()
                    jobs[jid]["portal_applied_via"] = "Indeed"
                    save_jobs(jobs)
                    applied += 1
                    print(f"  ✓ Applied on Indeed!")
                    log_apply({"job_id": jid, "title": job["title"],
                               "company": job["company"], "portal": "Indeed",
                               "applied_at": now_iso(), "success": True})

                page.wait_for_timeout(2000)

            except Exception as e:
                print(f"  ! Error on {job.get('title')}: {e}")
                log_apply({"job_id": jid, "title": job.get("title",""),
                           "portal": "Indeed", "applied_at": now_iso(),
                           "success": False, "error": str(e)})

    except Exception as e:
        print(f"[Indeed] Fatal error: {e}")

    print(f"[Indeed] Done. {applied} applications submitted.")
    return applied


# ── ZIPRECRUITER ───────────────────────────────────────────────────────────

def apply_ziprecruiter(page, jobs):
    """Apply to jobs on ZipRecruiter."""
    applied = 0
    print("\n[ZipRecruiter] Starting...")

    try:
        page.goto("https://www.ziprecruiter.com/login", timeout=30000)
        page.wait_for_timeout(2000)

        google_btn = page.query_selector('button:has-text("Google"), a:has-text("Google")')
        if google_btn:
            google_btn.click()
            page.wait_for_timeout(2000)
            if not google_login(page, GOOGLE_EMAIL, GOOGLE_PASSWORD):
                return 0
        else:
            print("  ! Google button not found on ZipRecruiter")
            return 0

        page.wait_for_timeout(3000)

        # Search for jobs
        config  = json.loads(CONFIG_FILE.read_text())
        queries = config.get("job_queries", [])[:3]  # top 3 queries

        for query in queries:
            try:
                page.goto(
                    f"https://www.ziprecruiter.com/jobs-search?search={query.replace(' ','+')}",
                    timeout=30000
                )
                page.wait_for_timeout(3000)

                # Get job cards
                job_cards = page.query_selector_all(
                    'article.job_result, div[data-testid="job-card"], .job-listing'
                )[:10]

                for card in job_cards:
                    try:
                        title_el = card.query_selector('h2, .job_title, [data-testid="job-title"]')
                        title    = title_el.inner_text() if title_el else ""

                        # Click 1-Click Apply if available
                        one_click = card.query_selector(
                            'button:has-text("1-Click"), button:has-text("Quick Apply")'
                        )
                        if one_click:
                            one_click.click()
                            page.wait_for_timeout(3000)
                            handle_screening_questions(page, title)

                            submit = page.query_selector('button:has-text("Submit"), button[type="submit"]')
                            if submit:
                                submit.click()
                                page.wait_for_timeout(2000)
                                applied += 1
                                print(f"  ✓ 1-Click Applied: {title}")
                                log_apply({"title": title, "portal": "ZipRecruiter",
                                           "applied_at": now_iso(), "success": True})

                    except Exception as e:
                        print(f"  ! Card error: {e}")

            except Exception as e:
                print(f"  ! Query error: {e}")

    except Exception as e:
        print(f"[ZipRecruiter] Fatal error: {e}")

    print(f"[ZipRecruiter] Done. {applied} applications submitted.")
    return applied


# ── MONSTER ────────────────────────────────────────────────────────────────

def apply_monster(page, jobs):
    """Apply to jobs on Monster."""
    applied = 0
    print("\n[Monster] Starting...")

    try:
        page.goto("https://www.monster.com/login", timeout=30000)
        page.wait_for_timeout(2000)

        google_btn = page.query_selector('button:has-text("Google"), a:has-text("Google")')
        if google_btn:
            google_btn.click()
            page.wait_for_timeout(2000)
            if not google_login(page, GOOGLE_EMAIL, GOOGLE_PASSWORD):
                return 0

        page.wait_for_timeout(3000)

        config  = json.loads(CONFIG_FILE.read_text())
        queries = config.get("job_queries", [])[:3]

        for query in queries:
            try:
                page.goto(
                    f"https://www.monster.com/jobs/search?q={query.replace(' ','+')}",
                    timeout=30000
                )
                page.wait_for_timeout(3000)

                job_cards = page.query_selector_all(
                    'section.card-content, div[data-testid="jobCard"], .job-search-result'
                )[:10]

                for card in job_cards:
                    try:
                        title_el = card.query_selector('h2, h3, .job-title')
                        title    = title_el.inner_text() if title_el else "Unknown"

                        apply_btn = card.query_selector(
                            'button:has-text("Apply"), a:has-text("Apply")'
                        )
                        if apply_btn:
                            apply_btn.click()
                            page.wait_for_timeout(3000)

                            # Upload resume
                            resume_input = page.query_selector('input[type="file"]')
                            if resume_input:
                                # Use a job from jobs dict that has a PDF
                                for jid, job in jobs.items():
                                    pdf = get_resume_pdf(job)
                                    if pdf:
                                        resume_input.set_input_files(pdf)
                                        break
                                page.wait_for_timeout(2000)

                            handle_screening_questions(page, title)

                            submit = page.query_selector(
                                'button:has-text("Submit"), button[type="submit"]'
                            )
                            if submit:
                                submit.click()
                                page.wait_for_timeout(2000)
                                applied += 1
                                print(f"  ✓ Applied: {title}")
                                log_apply({"title": title, "portal": "Monster",
                                           "applied_at": now_iso(), "success": True})

                    except Exception as e:
                        print(f"  ! Card error: {e}")

            except Exception as e:
                print(f"  ! Query error: {e}")

    except Exception as e:
        print(f"[Monster] Fatal error: {e}")

    print(f"[Monster] Done. {applied} applications submitted.")
    return applied


# ── DICE ───────────────────────────────────────────────────────────────────

def apply_dice(page, jobs):
    """Apply to jobs on Dice (email/password login)."""
    applied = 0
    print("\n[Dice] Starting...")

    try:
        page.goto("https://www.dice.com/dashboard/login", timeout=30000)
        page.wait_for_timeout(2000)

        # Email/password login
        page.fill('input[type="email"], input[name="email"]', DICE_EMAIL)
        page.fill('input[type="password"], input[name="password"]', DICE_PASSWORD)
        page.click('button[type="submit"], button:has-text("Sign In")')
        page.wait_for_timeout(3000)
        print("  ✓ Dice login successful")

        config  = json.loads(CONFIG_FILE.read_text())
        queries = config.get("job_queries", [])[:3]

        for query in queries:
            try:
                page.goto(
                    f"https://www.dice.com/jobs?q={query.replace(' ','+')}",
                    timeout=30000
                )
                page.wait_for_timeout(3000)

                job_cards = page.query_selector_all(
                    'div[data-cy="card"], dhi-search-card, .card'
                )[:10]

                for card in job_cards:
                    try:
                        title_el = card.query_selector('a.card-title-link, h5, h2')
                        title    = title_el.inner_text() if title_el else "Unknown"

                        if title_el:
                            title_el.click()
                            page.wait_for_timeout(2000)

                        apply_btn = page.query_selector(
                            'button:has-text("Easy Apply"), '
                            'button:has-text("Apply Now"), '
                            'a:has-text("Apply")'
                        )
                        if apply_btn:
                            apply_btn.click()
                            page.wait_for_timeout(3000)

                            resume_input = page.query_selector('input[type="file"]')
                            if resume_input:
                                for jid, job in jobs.items():
                                    pdf = get_resume_pdf(job)
                                    if pdf:
                                        resume_input.set_input_files(pdf)
                                        break
                                page.wait_for_timeout(2000)

                            handle_screening_questions(page, title)

                            submit = page.query_selector(
                                'button:has-text("Submit"), button[type="submit"]'
                            )
                            if submit:
                                submit.click()
                                page.wait_for_timeout(2000)
                                applied += 1
                                print(f"  ✓ Applied: {title}")
                                log_apply({"title": title, "portal": "Dice",
                                           "applied_at": now_iso(), "success": True})

                        page.go_back()
                        page.wait_for_timeout(1500)

                    except Exception as e:
                        print(f"  ! Card error: {e}")

            except Exception as e:
                print(f"  ! Query error: {e}")

    except Exception as e:
        print(f"[Dice] Fatal error: {e}")

    print(f"[Dice] Done. {applied} applications submitted.")
    return applied


# ── JOBRIGHT.AI ────────────────────────────────────────────────────────────

def apply_jobright(page, jobs):
    """Apply to jobs on JobRight.ai."""
    applied = 0
    print("\n[JobRight.ai] Starting...")

    try:
        page.goto("https://jobright.ai/login", timeout=30000)
        page.wait_for_timeout(2000)

        google_btn = page.query_selector('button:has-text("Google"), a:has-text("Google")')
        if google_btn:
            google_btn.click()
            page.wait_for_timeout(2000)
            if not google_login(page, GOOGLE_EMAIL, GOOGLE_PASSWORD):
                return 0

        page.wait_for_timeout(3000)

        # Search jobs
        config  = json.loads(CONFIG_FILE.read_text())
        queries = config.get("job_queries", [])[:2]

        for query in queries:
            try:
                page.goto(f"https://jobright.ai/jobs?search={query.replace(' ','+')}",
                          timeout=30000)
                page.wait_for_timeout(3000)

                job_cards = page.query_selector_all('.job-card, [data-testid="job-item"]')[:10]

                for card in job_cards:
                    try:
                        title_el = card.query_selector('h3, h2, .job-title')
                        title    = title_el.inner_text() if title_el else "Unknown"

                        apply_btn = card.query_selector(
                            'button:has-text("Apply"), a:has-text("Apply")'
                        )
                        if apply_btn:
                            apply_btn.click()
                            page.wait_for_timeout(3000)
                            handle_screening_questions(page, title)

                            submit = page.query_selector(
                                'button:has-text("Submit"), button[type="submit"]'
                            )
                            if submit:
                                submit.click()
                                page.wait_for_timeout(2000)
                                applied += 1
                                print(f"  ✓ Applied: {title}")
                                log_apply({"title": title, "portal": "JobRight.ai",
                                           "applied_at": now_iso(), "success": True})

                    except Exception as e:
                        print(f"  ! Card error: {e}")

            except Exception as e:
                print(f"  ! Query error: {e}")

    except Exception as e:
        print(f"[JobRight.ai] Fatal error: {e}")

    print(f"[JobRight.ai] Done. {applied} applications submitted.")
    return applied


# ── MAIN ───────────────────────────────────────────────────────────────────

def run_apply_bot():
    from playwright.sync_api import sync_playwright

    jobs        = load_jobs()
    total       = 0
    portal_results = {}

    print("\n[Apply Bot] Starting multi-portal application...")
    print(f"[Apply Bot] Portals: Indeed, ZipRecruiter, Monster, Dice, JobRight.ai")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
                "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36",
            ]
        )

        context = browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            java_script_enabled=True,
        )

        page = context.new_page()

        # Hide automation flags
        page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            window.chrome = { runtime: {} };
        """)

        if GOOGLE_EMAIL and GOOGLE_PASSWORD:
            n = apply_indeed(page, jobs)
            portal_results["Indeed"] = n
            total += n
            time.sleep(3)

            n = apply_ziprecruiter(page, jobs)
            portal_results["ZipRecruiter"] = n
            total += n
            time.sleep(3)

            n = apply_monster(page, jobs)
            portal_results["Monster"] = n
            total += n
            time.sleep(3)

            n = apply_jobright(page, jobs)
            portal_results["JobRight.ai"] = n
            total += n
            time.sleep(3)

        if DICE_EMAIL and DICE_PASSWORD:
            n = apply_dice(page, jobs)
            portal_results["Dice"] = n
            total += n

        browser.close()

    print(f"\n[Apply Bot] COMPLETE")
    print(f"[Apply Bot] Results: {portal_results}")
    print(f"[Apply Bot] Total applications submitted: {total}")
    return total


if __name__ == "__main__":
    run_apply_bot()
