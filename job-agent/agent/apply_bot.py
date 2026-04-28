"""
Multi-Portal Apply Bot — Fixed selectors
Portals: Indeed, ZipRecruiter, Monster, Dice, JobRight.ai
"""

import json, os, time, traceback
from pathlib import Path
from datetime import datetime, timezone
import anthropic

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

GOOGLE_EMAIL    = os.environ.get("GOOGLE_EMAIL", "")
GOOGLE_PASSWORD = os.environ.get("GOOGLE_PASSWORD", "")
DICE_EMAIL      = os.environ.get("DICE_EMAIL", "")
DICE_PASSWORD   = os.environ.get("DICE_PASSWORD", "")

DATA_FILE   = Path("data/jobs.json")
LOG_FILE    = Path("data/apply_log.jsonl")
CONFIG_FILE = Path("data/config.json")

PROFILE = {
    "name":       "Ram Burri",
    "email":      "Ram.burri1408@gmail.com",
    "phone":      "9544454339",
    "location":   "Boca Raton, FL",
    "linkedin":   "linkedin.com/in/ramburri",
    "experience": "4",
    "title":      "Full Stack .NET Developer",
    "salary":     "110000",
    "authorized": "Yes",
    "sponsorship": "No",
    "visa":       "OPT",
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
    opts = f"\nOptions: {options}" if options else ""
    try:
        return client.messages.create(
            model="claude-opus-4-5", max_tokens=80,
            system=(
                "Fill job application for Ram Burri, Full Stack .NET Developer, 4+ years exp. "
                "Answer briefly. Yes/No for yes-no questions. Numbers for experience. "
                "Never reveal you are AI."
            ),
            messages=[{"role": "user", "content":
                f"Job: {job_title}\nQuestion: {question}{opts}\n"
                f"Profile: {json.dumps(PROFILE)}\nAnswer:"
            }]
        ).content[0].text.strip()
    except:
        return "Yes"

def get_resume_pdf(jobs):
    """Get any available PDF resume from jobs."""
    for jid, job in jobs.items():
        pdf_path = job.get("resume_pdf")
        if pdf_path and Path(pdf_path).exists():
            return pdf_path
    # Generate fresh one
    try:
        from ats_resume import generate_ats_resume
        sample_job = {"title": "Full Stack .NET Developer", "company": "Target", "description": ""}
        result = generate_ats_resume(sample_job, output_dir="/tmp")
        return result["pdf_path"]
    except Exception as e:
        print(f"  ! PDF generation failed: {e}")
        return None

def get_queries():
    config = json.loads(CONFIG_FILE.read_text())
    return config.get("job_queries", ["full stack .NET developer"])[:3]

# ── Google OAuth ───────────────────────────────────────────────────────────

def google_oauth_login(page, email, password, timeout=15000):
    """Handle Google OAuth popup or redirect."""
    try:
        # Wait for Google email field
        page.wait_for_selector('input[type="email"]', timeout=timeout)
        page.fill('input[type="email"]', email)
        page.wait_for_timeout(1000)

        # Click Next
        next_btn = page.query_selector('#identifierNext button, button:has-text("Next")')
        if next_btn:
            next_btn.click()
        else:
            page.keyboard.press("Enter")

        page.wait_for_timeout(2000)

        # Password
        page.wait_for_selector('input[type="password"]', timeout=timeout)
        page.fill('input[type="password"]', password)
        page.wait_for_timeout(1000)

        pwd_next = page.query_selector('#passwordNext button, button:has-text("Next")')
        if pwd_next:
            pwd_next.click()
        else:
            page.keyboard.press("Enter")

        page.wait_for_timeout(4000)
        print("  ✓ Google OAuth completed")
        return True
    except Exception as e:
        print(f"  ! Google OAuth failed: {e}")
        return False

def click_google_button(page, timeout=10000):
    """Try multiple selectors to find Google login button."""
    selectors = [
        'a[href*="google"]',
        'button[aria-label*="Google"]',
        'div[aria-label*="Google"]',
        '[data-testid*="google"]',
        'button:has-text("Continue with Google")',
        'button:has-text("Sign in with Google")',
        'button:has-text("Log in with Google")',
        'a:has-text("Continue with Google")',
        'a:has-text("Sign in with Google")',
        '[class*="google"]',
        'img[alt*="Google"]',
    ]
    for sel in selectors:
        try:
            btn = page.query_selector(sel)
            if btn and btn.is_visible():
                print(f"  → Found Google button: {sel}")
                btn.click()
                page.wait_for_timeout(3000)
                return True
        except:
            continue
    return False

def handle_screening(page, job_title, max_questions=10):
    """Answer screening questions on current page."""
    answered = 0
    try:
        # Text/number inputs
        for inp in page.query_selector_all('input[type="text"], input[type="number"], input[type="tel"]'):
            try:
                if inp.input_value():
                    continue
                label = ""
                for attr in ["aria-label", "placeholder", "name"]:
                    val = inp.get_attribute(attr)
                    if val:
                        label = val
                        break
                if not label:
                    inp_id = inp.get_attribute("id")
                    if inp_id:
                        lbl = page.query_selector(f'label[for="{inp_id}"]')
                        if lbl:
                            label = lbl.inner_text()
                if label and len(label) > 2:
                    ans = ai_answer(label, job_title)
                    inp.fill(ans[:100])
                    answered += 1
                    page.wait_for_timeout(200)
            except:
                pass

        # Textareas
        for ta in page.query_selector_all("textarea"):
            try:
                if ta.input_value():
                    continue
                label = ta.get_attribute("aria-label") or ta.get_attribute("placeholder") or ""
                if label:
                    ans = ai_answer(label, job_title)
                    ta.fill(ans)
                    answered += 1
            except:
                pass

        # Selects
        for sel in page.query_selector_all("select"):
            try:
                opts = [o.inner_text().strip() for o in sel.query_selector_all("option") if o.inner_text().strip() and o.get_attribute("value")]
                if not opts:
                    continue
                sel_id = sel.get_attribute("id") or ""
                lbl = page.query_selector(f'label[for="{sel_id}"]')
                label = lbl.inner_text() if lbl else sel.get_attribute("aria-label") or ""
                if label:
                    ans = ai_answer(label, job_title, opts)
                    best = opts[0]
                    for opt in opts:
                        if ans.lower() in opt.lower():
                            best = opt
                            break
                    sel.select_option(label=best)
                    answered += 1
            except:
                pass

    except Exception as e:
        print(f"  ! Screening error: {e}")

    if answered:
        print(f"  → Answered {answered} questions")
    return answered

def click_submit(page):
    """Try to click submit/continue button."""
    for sel in [
        'button[type="submit"]',
        'button:has-text("Submit")',
        'button:has-text("Apply")',
        'button:has-text("Continue")',
        'button:has-text("Next")',
        '[data-testid="submit"]',
    ]:
        try:
            btn = page.query_selector(sel)
            if btn and btn.is_visible() and btn.is_enabled():
                btn.click()
                page.wait_for_timeout(3000)
                return True
        except:
            continue
    return False

# ── INDEED ─────────────────────────────────────────────────────────────────

def apply_indeed(page, jobs, resume_pdf):
    applied = 0
    print("\n[Indeed] Starting...")

    try:
        # Go to Indeed login
        page.goto("https://secure.indeed.com/auth", timeout=30000)
        page.wait_for_timeout(3000)

        # Try Google login
        if not click_google_button(page):
            # Try alternative Indeed login page
            page.goto("https://www.indeed.com/account/login", timeout=30000)
            page.wait_for_timeout(2000)
            if not click_google_button(page):
                print("  ! Could not find Google button on Indeed")
                # Try direct URL with Google
                page.goto("https://secure.indeed.com/auth?hl=en&co=US&continue=https%3A%2F%2Fwww.indeed.com%2F&tmpl=desktop&service=my&from=gnav-util-homepage&jsContinue=&empContinue=", timeout=30000)
                page.wait_for_timeout(2000)
                click_google_button(page)

        # Handle Google OAuth
        page.wait_for_timeout(2000)
        if "google" in page.url.lower() or "accounts.google" in page.url.lower():
            google_oauth_login(page, GOOGLE_EMAIL, GOOGLE_PASSWORD)

        page.wait_for_timeout(3000)
        print(f"  → Current URL: {page.url[:60]}")

        # Search and apply
        for query in get_queries():
            try:
                search_url = f"https://www.indeed.com/jobs?q={query.replace(' ', '+')}&l=Remote&sort=date&fromage=1"
                page.goto(search_url, timeout=30000)
                page.wait_for_timeout(3000)

                # Get job cards
                cards = page.query_selector_all('[data-jk], .job_seen_beacon, [data-testid="slider_item"]')
                print(f"  → Found {len(cards)} job cards for '{query}'")

                for card in cards[:5]:
                    try:
                        title_el = card.query_selector('h2 a, .jobTitle a, [data-testid="job-title"]')
                        title    = title_el.inner_text().strip() if title_el else "Unknown"

                        # Click the job
                        if title_el:
                            title_el.click()
                            page.wait_for_timeout(2000)

                        # Look for Easy Apply button in right panel
                        apply_btn = page.query_selector(
                            'button[id*="apply"], '
                            'button:has-text("Apply now"), '
                            'a:has-text("Apply on company site")'
                        )

                        if not apply_btn:
                            continue

                        btn_text = apply_btn.inner_text()
                        if "company site" in btn_text.lower():
                            continue  # Skip external applications

                        apply_btn.click()
                        page.wait_for_timeout(3000)

                        # Handle multi-step application
                        for step in range(5):
                            # Upload resume if prompted
                            file_input = page.query_selector('input[type="file"]')
                            if file_input and resume_pdf:
                                file_input.set_input_files(resume_pdf)
                                page.wait_for_timeout(2000)

                            handle_screening(page, title)

                            if not click_submit(page):
                                break

                            # Check if done
                            if any(x in page.url for x in ["applied", "confirmation", "success"]):
                                break
                            if page.query_selector(':has-text("Application submitted"), :has-text("successfully applied")'):
                                break

                        applied += 1
                        print(f"  ✓ Applied: {title}")
                        log_apply({"title": title, "portal": "Indeed",
                                   "applied_at": now_iso(), "success": True})
                        page.wait_for_timeout(2000)

                    except Exception as e:
                        print(f"  ! Job error: {str(e)[:80]}")
                        continue

            except Exception as e:
                print(f"  ! Query error: {str(e)[:80]}")

    except Exception as e:
        print(f"[Indeed] Error: {str(e)[:100]}")
        traceback.print_exc()

    print(f"[Indeed] Done. {applied} applied.")
    return applied

# ── ZIPRECRUITER ───────────────────────────────────────────────────────────

def apply_ziprecruiter(page, jobs, resume_pdf):
    applied = 0
    print("\n[ZipRecruiter] Starting...")

    try:
        page.goto("https://www.ziprecruiter.com/login", timeout=30000)
        page.wait_for_timeout(3000)

        if not click_google_button(page):
            page.goto("https://www.ziprecruiter.com/login?country=US", timeout=30000)
            page.wait_for_timeout(2000)
            click_google_button(page)

        page.wait_for_timeout(2000)
        if "google" in page.url.lower():
            google_oauth_login(page, GOOGLE_EMAIL, GOOGLE_PASSWORD)

        page.wait_for_timeout(4000)

        for query in get_queries():
            try:
                page.goto(
                    f"https://www.ziprecruiter.com/jobs-search?search={query.replace(' ','+')}",
                    timeout=30000
                )
                page.wait_for_timeout(3000)

                cards = page.query_selector_all(
                    'article[class*="job"], div[class*="job_result"], [data-testid="job-card"]'
                )
                print(f"  → Found {len(cards)} cards for '{query}'")

                for card in cards[:5]:
                    try:
                        title_el = card.query_selector('h2, .job_title, [data-testid="job-title"]')
                        title    = title_el.inner_text().strip() if title_el else "Unknown"

                        # 1-Click Apply
                        one_click = card.query_selector(
                            'button:has-text("1-Click"), '
                            'button:has-text("Quick Apply"), '
                            'button[class*="one_click"]'
                        )
                        if one_click:
                            one_click.click()
                            page.wait_for_timeout(3000)
                            handle_screening(page, title)
                            click_submit(page)
                            applied += 1
                            print(f"  ✓ 1-Click: {title}")
                            log_apply({"title": title, "portal": "ZipRecruiter",
                                       "applied_at": now_iso(), "success": True})

                    except Exception as e:
                        print(f"  ! Card error: {str(e)[:60]}")

            except Exception as e:
                print(f"  ! Query error: {str(e)[:60]}")

    except Exception as e:
        print(f"[ZipRecruiter] Error: {str(e)[:100]}")

    print(f"[ZipRecruiter] Done. {applied} applied.")
    return applied

# ── MONSTER ────────────────────────────────────────────────────────────────

def apply_monster(page, jobs, resume_pdf):
    applied = 0
    print("\n[Monster] Starting...")

    try:
        page.goto("https://www.monster.com/login", timeout=30000)
        page.wait_for_timeout(3000)

        if not click_google_button(page):
            page.goto("https://www.monster.com/profile/signin", timeout=30000)
            page.wait_for_timeout(2000)
            click_google_button(page)

        page.wait_for_timeout(2000)
        if "google" in page.url.lower():
            google_oauth_login(page, GOOGLE_EMAIL, GOOGLE_PASSWORD)

        page.wait_for_timeout(4000)

        for query in get_queries():
            try:
                page.goto(
                    f"https://www.monster.com/jobs/search?q={query.replace(' ','+')}",
                    timeout=30000
                )
                page.wait_for_timeout(3000)

                cards = page.query_selector_all(
                    '[data-testid="jobCard"], .job-search-result, '
                    'section[class*="card"], div[class*="job-card"]'
                )
                print(f"  → Found {len(cards)} cards for '{query}'")

                for card in cards[:5]:
                    try:
                        title_el = card.query_selector('h2, h3, [data-testid="job-title"]')
                        title    = title_el.inner_text().strip() if title_el else "Unknown"

                        apply_btn = card.query_selector(
                            'button:has-text("Apply"), a:has-text("Apply")'
                        )
                        if not apply_btn:
                            continue

                        apply_btn.click()
                        page.wait_for_timeout(3000)

                        file_input = page.query_selector('input[type="file"]')
                        if file_input and resume_pdf:
                            file_input.set_input_files(resume_pdf)
                            page.wait_for_timeout(2000)

                        handle_screening(page, title)
                        click_submit(page)
                        applied += 1
                        print(f"  ✓ Applied: {title}")
                        log_apply({"title": title, "portal": "Monster",
                                   "applied_at": now_iso(), "success": True})

                    except Exception as e:
                        print(f"  ! Card error: {str(e)[:60]}")

            except Exception as e:
                print(f"  ! Query error: {str(e)[:60]}")

    except Exception as e:
        print(f"[Monster] Error: {str(e)[:100]}")

    print(f"[Monster] Done. {applied} applied.")
    return applied

# ── DICE ───────────────────────────────────────────────────────────────────

def apply_dice(page, jobs, resume_pdf):
    applied = 0
    print("\n[Dice] Starting...")

    try:
        # Dice login with email/password
        page.goto("https://www.dice.com/dashboard/login", timeout=30000)
        page.wait_for_timeout(3000)

        # Try multiple selectors for email field
        email_selectors = [
            'input[name="email"]',
            'input[type="email"]',
            '#email',
            'input[placeholder*="email" i]',
            'input[placeholder*="Email" i]',
        ]
        email_filled = False
        for sel in email_selectors:
            try:
                el = page.query_selector(sel)
                if el and el.is_visible():
                    el.fill(DICE_EMAIL)
                    email_filled = True
                    print(f"  → Filled email with: {sel}")
                    break
            except:
                continue

        if not email_filled:
            # Try clicking "Sign In" first
            page.click('button:has-text("Sign In"), a:has-text("Sign In")')
            page.wait_for_timeout(2000)
            for sel in email_selectors:
                try:
                    el = page.query_selector(sel)
                    if el:
                        el.fill(DICE_EMAIL)
                        email_filled = True
                        break
                except:
                    continue

        page.wait_for_timeout(1000)

        # Click Next or Continue after email
        for sel in ['button:has-text("Next")', 'button:has-text("Continue")',
                    'button[type="submit"]', '#login-button']:
            try:
                btn = page.query_selector(sel)
                if btn and btn.is_visible():
                    btn.click()
                    break
            except:
                continue

        page.wait_for_timeout(2000)

        # Password
        pwd_selectors = [
            'input[name="password"]',
            'input[type="password"]',
            '#password',
            'input[placeholder*="password" i]',
        ]
        for sel in pwd_selectors:
            try:
                el = page.query_selector(sel)
                if el and el.is_visible():
                    el.fill(DICE_PASSWORD)
                    print(f"  → Filled password")
                    break
            except:
                continue

        page.wait_for_timeout(500)

        # Submit login
        for sel in ['button[type="submit"]', 'button:has-text("Sign In")',
                    'button:has-text("Log In")', '#login-button']:
            try:
                btn = page.query_selector(sel)
                if btn and btn.is_visible():
                    btn.click()
                    break
            except:
                continue

        page.wait_for_timeout(4000)
        print(f"  → Dice URL after login: {page.url[:60]}")

        for query in get_queries():
            try:
                page.goto(
                    f"https://www.dice.com/jobs?q={query.replace(' ','+')}",
                    timeout=30000
                )
                page.wait_for_timeout(3000)

                cards = page.query_selector_all(
                    'div[data-cy="card"], dhi-search-card, '
                    '[data-testid="job-search-result"], .card'
                )
                print(f"  → Found {len(cards)} cards for '{query}'")

                for card in cards[:5]:
                    try:
                        title_el = card.query_selector(
                            'a.card-title-link, h5 a, h2 a, [data-cy="job-title"]'
                        )
                        title = title_el.inner_text().strip() if title_el else "Unknown"

                        if title_el:
                            title_el.click()
                            page.wait_for_timeout(2000)

                        apply_btn = page.query_selector(
                            'apply-button button, '
                            'button:has-text("Easy Apply"), '
                            'button:has-text("Apply Now")'
                        )
                        if not apply_btn:
                            page.go_back()
                            page.wait_for_timeout(1000)
                            continue

                        apply_btn.click()
                        page.wait_for_timeout(3000)

                        file_input = page.query_selector('input[type="file"]')
                        if file_input and resume_pdf:
                            file_input.set_input_files(resume_pdf)
                            page.wait_for_timeout(2000)

                        handle_screening(page, title)
                        click_submit(page)
                        applied += 1
                        print(f"  ✓ Applied: {title}")
                        log_apply({"title": title, "portal": "Dice",
                                   "applied_at": now_iso(), "success": True})

                        page.go_back()
                        page.wait_for_timeout(1500)

                    except Exception as e:
                        print(f"  ! Card error: {str(e)[:60]}")
                        try:
                            page.go_back()
                        except:
                            pass

            except Exception as e:
                print(f"  ! Query error: {str(e)[:60]}")

    except Exception as e:
        print(f"[Dice] Error: {str(e)[:100]}")

    print(f"[Dice] Done. {applied} applied.")
    return applied

# ── JOBRIGHT ───────────────────────────────────────────────────────────────

def apply_jobright(page, jobs, resume_pdf):
    applied = 0
    print("\n[JobRight.ai] Starting...")

    try:
        page.goto("https://jobright.ai/sign-in", timeout=30000)
        page.wait_for_timeout(3000)

        if not click_google_button(page):
            page.goto("https://jobright.ai/login", timeout=30000)
            page.wait_for_timeout(2000)
            click_google_button(page)

        page.wait_for_timeout(2000)
        if "google" in page.url.lower():
            google_oauth_login(page, GOOGLE_EMAIL, GOOGLE_PASSWORD)

        page.wait_for_timeout(4000)

        for query in get_queries():
            try:
                page.goto(
                    f"https://jobright.ai/jobs/search?keywords={query.replace(' ','+')}",
                    timeout=30000
                )
                page.wait_for_timeout(3000)

                cards = page.query_selector_all(
                    '.job-card, [data-testid="job-item"], '
                    'div[class*="job-listing"], li[class*="job"]'
                )
                print(f"  → Found {len(cards)} cards for '{query}'")

                for card in cards[:5]:
                    try:
                        title_el = card.query_selector('h3, h2, [class*="title"]')
                        title    = title_el.inner_text().strip() if title_el else "Unknown"

                        apply_btn = card.query_selector(
                            'button:has-text("Apply"), a:has-text("Apply"), '
                            'button:has-text("Easy Apply")'
                        )
                        if not apply_btn:
                            continue

                        apply_btn.click()
                        page.wait_for_timeout(3000)
                        handle_screening(page, title)
                        click_submit(page)
                        applied += 1
                        print(f"  ✓ Applied: {title}")
                        log_apply({"title": title, "portal": "JobRight.ai",
                                   "applied_at": now_iso(), "success": True})

                    except Exception as e:
                        print(f"  ! Card error: {str(e)[:60]}")

            except Exception as e:
                print(f"  ! Query error: {str(e)[:60]}")

    except Exception as e:
        print(f"[JobRight.ai] Error: {str(e)[:100]}")

    print(f"[JobRight.ai] Done. {applied} applied.")
    return applied

# ── MAIN ───────────────────────────────────────────────────────────────────

def run_apply_bot():
    from playwright.sync_api import sync_playwright

    jobs       = load_jobs()
    resume_pdf = get_resume_pdf(jobs)
    total      = 0
    results    = {}

    print("\n[Apply Bot] Starting...")
    if resume_pdf:
        print(f"[Apply Bot] Resume PDF: {resume_pdf}")
    else:
        print("[Apply Bot] Warning: No resume PDF available")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars",
                "--window-size=1280,800",
            ]
        )
        context = browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            locale="en-US",
        )
        # Hide webdriver
        context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )
        page = context.new_page()
        page.set_default_timeout(20000)

        if GOOGLE_EMAIL and GOOGLE_PASSWORD:
            n = apply_indeed(page, jobs, resume_pdf)
            results["Indeed"] = n; total += n; time.sleep(5)

            n = apply_ziprecruiter(page, jobs, resume_pdf)
            results["ZipRecruiter"] = n; total += n; time.sleep(5)

            n = apply_monster(page, jobs, resume_pdf)
            results["Monster"] = n; total += n; time.sleep(5)

            n = apply_jobright(page, jobs, resume_pdf)
            results["JobRight.ai"] = n; total += n; time.sleep(5)

        if DICE_EMAIL and DICE_PASSWORD:
            n = apply_dice(page, jobs, resume_pdf)
            results["Dice"] = n; total += n

        browser.close()

    print(f"\n[Apply Bot] Results: {results}")
    print(f"[Apply Bot] Total: {total} applications")
    return total

if __name__ == "__main__":
    run_apply_bot()
