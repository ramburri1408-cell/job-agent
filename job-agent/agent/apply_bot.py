"""
Multi-Portal Apply Bot — Fixed Easy Apply modal wait
"""

import json, os, time, traceback
from urllib.parse import quote
from pathlib import Path
from datetime import datetime, timezone
import anthropic

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

DICE_EMAIL    = os.environ.get("DICE_EMAIL", "")
DICE_PASSWORD = os.environ.get("DICE_PASSWORD", "")

DATA_FILE   = Path("data/jobs.json")
LOG_FILE    = Path("data/apply_log.jsonl")
CONFIG_FILE = Path("data/config.json")

def load_config():
    return json.loads(CONFIG_FILE.read_text()) if CONFIG_FILE.exists() else {}

CONFIG        = load_config()
CFG_PROFILE   = CONFIG.get("profile", {})
MIN_APPLY_SCORE    = int(CONFIG.get("min_apply_score", CONFIG.get("min_fit_score", 70)))
AUTO_APPLY_ENABLED = bool(CONFIG.get("auto_apply_enabled", True))

PROFILE = {
    "name": CFG_PROFILE.get("name", "Janaki Ram Reddy"),
    "email": CFG_PROFILE.get("email", "janakiram.b1408@gmail.com"),
    "phone": CFG_PROFILE.get("phone", "+1 984-357-4658"),
    "location": "Boca Raton, FL",
    "experience": "4",
    "title": CFG_PROFILE.get("title", "Senior Software Engineer"),
    "salary": "110000",
    "skills": CFG_PROFILE.get("skills", ""),
    "summary": CFG_PROFILE.get("summary", ""),
}

def load_jobs():
    return json.loads(DATA_FILE.read_text()) if DATA_FILE.exists() else {}

def log_apply(entry):
    LOG_FILE.parent.mkdir(exist_ok=True)
    with LOG_FILE.open("a") as f:
        f.write(json.dumps(entry) + "\n")

def load_applied_urls() -> set:
    """URLs we've already successfully applied to, so we never double-apply."""
    urls = set()
    if LOG_FILE.exists():
        with LOG_FILE.open() as f:
            for line in f:
                try:
                    entry = json.loads(line)
                    if entry.get("success") and entry.get("url"):
                        urls.add(entry["url"])
                except Exception:
                    pass
    return urls

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def get_job_description(page) -> str:
    """Pull the job requirements text off the detail page to check fit before applying."""
    for sel in ['[data-testid="jobDescriptionHtml"]', '[class*="job-description"]',
                '[class*="jobDescription"]', 'article', 'main']:
        try:
            el = page.query_selector(sel)
            if el:
                text = el.inner_text().strip()
                if len(text) > 100:
                    return text
        except Exception:
            pass
    try:
        return page.inner_text("body")
    except Exception:
        return ""

def score_job_requirements(title: str, description: str) -> dict:
    """Ask Claude whether this job's requirements actually match the candidate before applying."""
    try:
        raw = client.messages.create(
            model="claude-opus-4-8", max_tokens=200,
            system=(
                "You are screening a job posting's requirements against a candidate profile "
                "before an application is auto-submitted. Return ONLY valid JSON, no markdown:\n"
                '{"score":80,"meets_requirements":true,"reason":"short reason"}'
            ),
            messages=[{"role": "user", "content": (
                f"Job title: {title}\n"
                f"Job requirements/description:\n{description[:2500]}\n\n"
                f"Candidate title: {PROFILE['title']}\n"
                f"Experience: {PROFILE.get('experience', '4')}+ years\n"
                f"Skills: {PROFILE.get('skills', '')}\n"
                f"Summary: {PROFILE.get('summary', '')}"
            )}],
        ).content[0].text.strip()
        clean = raw.replace("```json", "").replace("```", "").strip()
        d = json.loads(clean)
        d["score"] = int(d.get("score", 0))
        return d
    except Exception as e:
        print(f"  ! Requirement scoring error: {e}")
        return {"score": 0, "meets_requirements": False, "reason": "scoring failed"}

def get_resume_pdf(jobs):
    for jid, job in jobs.items():
        pdf = job.get("resume_pdf")
        if pdf and Path(pdf).exists():
            return pdf
    try:
        from ats_resume import generate_ats_resume
        r = generate_ats_resume({
            "title": PROFILE.get("title", "Senior Software Engineer"),
            "company": "Target",
            "description": ""
        }, "/tmp")
        return r["pdf_path"]
    except Exception as e:
        print(f"  ! PDF error: {e}")
        return None

def get_queries():
    config = json.loads(CONFIG_FILE.read_text())
    return config.get("job_queries", ["full stack Java developer"])[:4]

def ai_answer(question: str, options: list = None) -> str:
    q = question.lower()
    # Work authorization — answer directly, save credits
    if any(k in q for k in ["authorized", "authorization", "work in the us", "eligible", "legally allowed"]):
        if options:
            for opt in options:
                o = opt.lower()
                if any(k in o for k in ["authorized", "yes", "citizen", "permanent", "opt", "eligible"]):
                    if "not" not in o and "no" not in o and "h1" not in o:
                        return opt
            return options[0]
        return "Yes, I am authorized to work in the United States"
    if any(k in q for k in ["sponsor", "sponsorship"]):
        if options:
            for opt in options:
                if any(k in opt.lower() for k in ["no", "not require", "don't"]):
                    return opt
        return "No"
    if any(k in q for k in ["salary", "compensation"]):
        return "110000"
    if any(k in q for k in ["years of experience", "how many years"]):
        return "4"
    try:
        return client.messages.create(
            model="claude-opus-4-8", max_tokens=60,
            system=(
                f"Answer job application questions for {PROFILE['name']}, "
                f"{PROFILE['title']}, {PROFILE.get('experience', '4')} years exp, "
                "authorized to work in US. Brief answers only."
            ),
            messages=[{"role": "user", "content": f"Q: {question}\nOptions: {options}\nA:"}]
        ).content[0].text.strip()
    except:
        return "Yes"

def fill_form_fields(page, title: str):
    """Fill all visible form fields."""
    answered = 0
    try:
        # Text inputs
        for inp in page.query_selector_all('input[type="text"],input[type="number"],input[type="tel"]'):
            try:
                if inp.input_value(): continue
                lbl = inp.get_attribute("aria-label") or inp.get_attribute("placeholder") or ""
                if not lbl:
                    iid = inp.get_attribute("id")
                    if iid:
                        el = page.query_selector(f'label[for="{iid}"]')
                        if el: lbl = el.inner_text()
                if lbl and len(lbl) > 2:
                    inp.fill(ai_answer(lbl)[:100])
                    answered += 1
            except: pass

        # Selects / dropdowns
        for sel in page.query_selector_all("select"):
            try:
                opts = [o.inner_text().strip() for o in sel.query_selector_all("option") if o.inner_text().strip()]
                sid  = sel.get_attribute("id") or ""
                lel  = page.query_selector(f'label[for="{sid}"]') if sid else None
                lbl  = lel.inner_text() if lel else sel.get_attribute("aria-label") or ""
                if lbl and opts:
                    ans  = ai_answer(lbl, opts)
                    best = next((o for o in opts if ans.lower() in o.lower()), opts[0])
                    sel.select_option(label=best)
                    answered += 1
            except: pass

        # Radio buttons
        for grp in page.query_selector_all('fieldset, [role="radiogroup"]'):
            try:
                legend = grp.query_selector('legend')
                lbl    = legend.inner_text() if legend else ""
                radios = grp.query_selector_all('input[type="radio"]')
                if not radios: continue
                opts = []
                for r in radios:
                    rid  = r.get_attribute("id") or ""
                    rlbl = page.query_selector(f'label[for="{rid}"]')
                    txt  = rlbl.inner_text().strip() if rlbl else r.get_attribute("value") or ""
                    opts.append((txt, r))
                if opts:
                    ans  = ai_answer(lbl, [o[0] for o in opts])
                    best = next((r for txt, r in opts if ans.lower() in txt.lower()), opts[0][1])
                    best.click()
                    answered += 1
            except: pass

    except Exception as e:
        print(f"  ! Fill error: {e}")
    if answered:
        print(f"  → Filled {answered} fields")

def wait_for_apply_modal(page) -> bool:
    """
    Wait for the Easy Apply modal/form to fully load.
    Returns True if form appeared, False if timed out.
    """
    # These selectors indicate the apply form has loaded
    form_selectors = [
        'input[type="file"]',               # Resume upload
        'button:has-text("Next")',           # Next button
        'button:has-text("Submit")',         # Submit button
        'button:has-text("Submit application")',
        '[class*="apply-form"]',             # Apply form container
        '[class*="application-form"]',
        'h2:has-text("Resume")',             # Step 1 heading
        'h2:has-text("Review")',             # Step 2 heading
        'text="Step 1"',
        'text="Step 2"',
    ]

    # Wait up to 10 seconds for any form element to appear
    for _ in range(20):
        for sel in form_selectors:
            try:
                el = page.query_selector(sel)
                if el and el.is_visible():
                    return True
            except: pass
        page.wait_for_timeout(500)

    return False

def handle_dice_apply(page, title: str, resume_pdf: str) -> bool:
    """
    Handle Dice Easy Apply multi-step form.
    Waits for each step to load before proceeding.
    """
    for step in range(6):
        page.wait_for_timeout(2000)

        try:
            body = page.inner_text("body").lower()
        except:
            return False

        # Check if already submitted
        if any(k in body for k in ["application submitted", "successfully submitted", "thank you for applying", "you've applied"]):
            print(f"  ✓ Confirmed submitted: {title}")
            return True

        print(f"  → Step {step+1}: processing form...")

        # Upload resume if file input visible
        try:
            file_inp = page.query_selector('input[type="file"]')
            if file_inp and file_inp.is_visible() and resume_pdf:
                file_inp.set_input_files(resume_pdf)
                page.wait_for_timeout(2000)
                print(f"  → Resume uploaded")
        except: pass

        # Fill all form fields
        fill_form_fields(page, title)
        page.wait_for_timeout(1000)

        # Try Submit button first (final step)
        submit_clicked = False
        for sel in [
            'button:has-text("Submit application")',
            'button:has-text("Submit")',
        ]:
            try:
                btn = page.query_selector(sel)
                if btn and btn.is_visible() and btn.is_enabled():
                    print(f"  → Clicking Submit")
                    btn.click()
                    page.wait_for_timeout(4000)
                    submit_clicked = True
                    break
            except: pass

        if submit_clicked:
            # Check if submission confirmed
            try:
                body = page.inner_text("body").lower()
                if any(k in body for k in ["submitted", "thank you", "applied", "received"]):
                    return True
            except: pass
            continue

        # Try Next button
        next_clicked = False
        for sel in [
            'button:has-text("Next")',
            'button:has-text("Continue")',
            'button[type="submit"]',
        ]:
            try:
                btn = page.query_selector(sel)
                if btn and btn.is_visible() and btn.is_enabled():
                    print(f"  → Clicking Next")
                    btn.click()
                    page.wait_for_timeout(3000)
                    next_clicked = True
                    break
            except: pass

        if not next_clicked:
            print(f"  ! No button found on step {step+1}")
            return False

    return False

def get_dice_jobs_js(page):
    try:
        return page.evaluate("""
            () => {
                const results = [];
                const cards = document.querySelectorAll('[data-testid="job-card"]');
                cards.forEach(card => {
                    let title = '', url = '';
                    const sels = ['a[data-cy="card-title-link"]','h5 a','h2 a','h3 a','a[href*="/job-detail/"]','h5','h2','h3'];
                    for (const s of sels) {
                        const el = card.querySelector(s);
                        if (el && el.innerText && el.innerText.trim()) {
                            title = el.innerText.trim();
                            if (el.href) url = el.href;
                            break;
                        }
                    }
                    if (!url) {
                        const link = card.querySelector('a[href*="/job-detail/"]');
                        if (link) url = link.href;
                    }
                    results.push({ title: title || 'Unknown', url: url });
                });
                return results;
            }
        """)
    except Exception as e:
        print(f"  ! JS error: {e}")
        return []

def apply_to_job(page, title: str, job_url: str, resume_pdf: str) -> bool:
    try:
        if not job_url:
            return False

        page.goto(job_url, timeout=30000)
        page.wait_for_timeout(3000)

        # Get real title from h1
        if title == "Unknown":
            try:
                h1 = page.query_selector('h1')
                if h1: title = h1.inner_text().strip()
            except: pass

        # ── Gate: only apply if the job's requirements actually match ──
        description = get_job_description(page)
        analysis    = score_job_requirements(title, description)
        score       = analysis.get("score", 0)
        print(f"  → Requirement match: {score}/100 ({analysis.get('reason', '')})")
        if score < MIN_APPLY_SCORE:
            print(f"  x Skipping, below min_apply_score {MIN_APPLY_SCORE}: {title}")
            return False

        # Find Easy Apply button
        apply_btn = None
        for asel in [
            'button:has-text("Easy Apply")',
            'apply-button-wc button',
            'button[data-cy="apply-button"]',
        ]:
            try:
                btn = page.query_selector(asel)
                if btn and btn.is_visible():
                    apply_btn = btn
                    break
            except: pass

        if not apply_btn:
            ext = page.query_selector('a:has-text("Apply on company site"), a:has-text("Apply externally")')
            print(f"  → {'External only' if ext else 'No Easy Apply'}: {title}")
            return False

        print(f"  → Easy Apply: {title}")

        # Click Easy Apply
        try:
            apply_btn.click(timeout=10000)
        except:
            page.evaluate("(el) => el.click()", apply_btn)

        # ── CRITICAL: Wait for modal/form to fully load ──
        print(f"  → Waiting for apply form...")
        form_loaded = wait_for_apply_modal(page)

        if not form_loaded:
            print(f"  ! Apply form did not load for: {title}")
            return False

        print(f"  → Form loaded, processing...")

        # Handle multi-step form
        success = handle_dice_apply(page, title, resume_pdf)

        if success:
            log_apply({
                "title": title, "url": job_url,
                "portal": "Dice", "applied_at": now_iso(), "success": True,
                "requirement_score": score, "requirement_reason": analysis.get("reason", ""),
            })

        return success

    except Exception as e:
        print(f"  ! Error ({title}): {str(e)[:80]}")
        return False

def apply_dice(page, jobs, resume_pdf):
    applied      = 0
    applied_urls = load_applied_urls()
    print("\n[Dice] Starting...")

    try:
        # Login
        page.goto("https://www.dice.com/dashboard/login", timeout=30000)
        page.wait_for_timeout(3000)

        for sel in ['input[name="email"]', 'input[type="email"]', '#email']:
            try:
                el = page.query_selector(sel)
                if el and el.is_visible(): el.fill(DICE_EMAIL); break
            except: pass
        page.wait_for_timeout(500)

        for sel in ['button[type="submit"]', '#login-button', 'button:has-text("Sign In")']:
            try:
                btn = page.query_selector(sel)
                if btn and btn.is_visible(): btn.click(); break
            except: pass
        page.wait_for_timeout(2000)

        for sel in ['input[name="password"]', 'input[type="password"]', '#password']:
            try:
                el = page.query_selector(sel)
                if el and el.is_visible(): el.fill(DICE_PASSWORD); break
            except: pass
        page.wait_for_timeout(500)

        for sel in ['button[type="submit"]', '#login-button', 'button:has-text("Sign In")']:
            try:
                btn = page.query_selector(sel)
                if btn and btn.is_visible(): btn.click(); break
            except: pass
        page.wait_for_timeout(5000)
        print(f"  ✓ Logged in: {page.url[:60]}")

        for query in get_queries():
            try:
                search_url = (
                    f"https://www.dice.com/jobs"
                    f"?q={quote(query)}"
                    f"&filters.postedDate=THREE"
                    f"&filters.employmentType=FULLTIME"
                )
                page.goto(search_url, timeout=30000)
                try:
                    page.wait_for_selector('[data-testid="job-card"]', timeout=12000)
                except: pass
                page.wait_for_timeout(4000)

                job_list = get_dice_jobs_js(page)
                print(f"  → {len(job_list)} jobs for '{query}'")

                for job_data in job_list[:10]:
                    title   = job_data.get("title", "Unknown")
                    job_url = job_data.get("url", "")

                    if job_url in applied_urls:
                        print(f"  → Already applied, skipping: {title}")
                        continue

                    print(f"  → Checking: {title}")

                    if apply_to_job(page, title, job_url, resume_pdf):
                        applied += 1
                        applied_urls.add(job_url)

                    try:
                        page.goto(search_url, timeout=30000)
                        page.wait_for_timeout(3000)
                    except: pass

            except Exception as e:
                print(f"  ! Query error: {str(e)[:80]}")

    except Exception as e:
        print(f"[Dice] Fatal: {str(e)[:100]}")
        traceback.print_exc()

    print(f"[Dice] Done. {applied} applied.")
    return applied

def apply_indeed(page, jobs, resume_pdf):
    print("\n[Indeed] Skipped — blocked by bot detection"); return 0

def apply_ziprecruiter(page, jobs, resume_pdf):
    print("\n[ZipRecruiter] Skipped — blocked by Cloudflare"); return 0

def apply_monster(page, jobs, resume_pdf):
    print("\n[Monster] Skipped — blocked by DataDome CAPTCHA"); return 0

def apply_jobright(page, jobs, resume_pdf):
    print("\n[JobRight.ai] Skipped — Google OAuth fails headless"); return 0

def run_apply_bot():
    if not AUTO_APPLY_ENABLED:
        print("\n[Apply Bot] auto_apply_enabled is false in config.json — skipping.")
        return 0

    from playwright.sync_api import sync_playwright

    jobs       = load_jobs()
    resume_pdf = get_resume_pdf(jobs)
    total      = 0
    results    = {}

    print(f"\n[Apply Bot] Starting... Resume: {resume_pdf}")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox", "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
                "--window-size=1280,800",
            ]
        )
        ctx = browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            locale="en-US",
        )
        ctx.add_init_script(
            "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"
        )
        page = ctx.new_page()
        page.set_default_timeout(30000)

        if DICE_EMAIL and DICE_PASSWORD:
            n = apply_dice(page, jobs, resume_pdf)
            results["Dice"] = n; total += n

        results["Indeed"]       = apply_indeed(page, jobs, resume_pdf)
        results["ZipRecruiter"] = apply_ziprecruiter(page, jobs, resume_pdf)
        results["Monster"]      = apply_monster(page, jobs, resume_pdf)
        results["JobRight.ai"]  = apply_jobright(page, jobs, resume_pdf)

        browser.close()

    print(f"\n[Apply Bot] Results: {results}")
    print(f"[Apply Bot] Total: {total} applications")
    return total

if __name__ == "__main__":
    run_apply_bot()
