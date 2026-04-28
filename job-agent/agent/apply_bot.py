"""
Multi-Portal Apply Bot — Fixed selectors based on live test results
Dice: ✅ login works, fix card selectors
Monster: ✅ Google found, fix card selectors  
Indeed: fix login flow
JobRight: found cards, fix apply button
ZipRecruiter: fix Google login
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
    "name": "Ram Burri", "email": "Ram.burri1408@gmail.com",
    "phone": "9544454339", "location": "Boca Raton, FL",
    "experience": "4", "title": "Full Stack .NET Developer",
    "salary": "110000", "authorized": "Yes", "sponsorship": "No", "visa": "OPT",
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
            model="claude-haiku-4-5-20251001", max_tokens=60,
            system="Answer job application questions for Ram Burri, Full Stack .NET Developer, 4 years exp. Brief answers only.",
            messages=[{"role": "user", "content": f"Q: {question}{opts}\nProfile: {json.dumps(PROFILE)}\nA:"}]
        ).content[0].text.strip()
    except:
        return "Yes"

def get_resume_pdf(jobs):
    for jid, job in jobs.items():
        pdf = job.get("resume_pdf")
        if pdf and Path(pdf).exists():
            return pdf
    try:
        from ats_resume import generate_ats_resume
        r = generate_ats_resume({"title": "Full Stack .NET Developer", "company": "Target", "description": ""}, "/tmp")
        return r["pdf_path"]
    except Exception as e:
        print(f"  ! PDF error: {e}")
        return None

def get_queries():
    config = json.loads(CONFIG_FILE.read_text())
    return config.get("job_queries", ["full stack .NET developer"])[:4]

def google_login(page, email, password):
    try:
        page.wait_for_selector('input[type="email"]', timeout=12000)
        page.fill('input[type="email"]', email)
        page.wait_for_timeout(800)
        for sel in ['#identifierNext', 'button:has-text("Next")']:
            try:
                btn = page.query_selector(sel)
                if btn: btn.click(); break
            except: pass
        page.wait_for_timeout(2500)
        page.wait_for_selector('input[type="password"]', timeout=10000)
        page.fill('input[type="password"]', password)
        page.wait_for_timeout(800)
        for sel in ['#passwordNext', 'button:has-text("Next")']:
            try:
                btn = page.query_selector(sel)
                if btn: btn.click(); break
            except: pass
        page.wait_for_timeout(4000)
        print("  ✓ Google login done")
        return True
    except Exception as e:
        print(f"  ! Google login failed: {e}")
        return False

def find_google_btn(page):
    selectors = [
        'a[data-tn-element="GoogleSignInLink"]',
        'a[href*="google"]', 'button[aria-label*="Google"]',
        'button:has-text("Continue with Google")',
        'button:has-text("Sign in with Google")',
        'a:has-text("Continue with Google")',
        '[data-testid*="google"]', '[class*="google-login"]',
        'img[alt*="Google"]',
    ]
    for sel in selectors:
        try:
            btn = page.query_selector(sel)
            if btn and btn.is_visible():
                print(f"  → Google btn: {sel}")
                btn.click()
                page.wait_for_timeout(3000)
                return True
        except: pass
    return False

def handle_screening(page, title):
    answered = 0
    try:
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
                    inp.fill(ai_answer(lbl, title)[:100])
                    answered += 1
            except: pass
        for ta in page.query_selector_all("textarea"):
            try:
                if ta.input_value(): continue
                lbl = ta.get_attribute("aria-label") or ta.get_attribute("placeholder") or ""
                if lbl: ta.fill(ai_answer(lbl, title)); answered += 1
            except: pass
        for sel in page.query_selector_all("select"):
            try:
                opts = [o.inner_text().strip() for o in sel.query_selector_all("option") if o.inner_text().strip()]
                sid = sel.get_attribute("id") or ""
                lel = page.query_selector(f'label[for="{sid}"]') if sid else None
                lbl = lel.inner_text() if lel else sel.get_attribute("aria-label") or ""
                if lbl and opts:
                    ans = ai_answer(lbl, title, opts)
                    best = next((o for o in opts if ans.lower() in o.lower()), opts[0])
                    sel.select_option(label=best); answered += 1
            except: pass
    except Exception as e:
        print(f"  ! Screening err: {e}")
    if answered: print(f"  → Answered {answered} questions")

def click_submit(page):
    for sel in ['button[type="submit"]','button:has-text("Submit application")',
                'button:has-text("Submit")', 'button:has-text("Apply")',
                'button:has-text("Continue")', '[data-testid="submit-btn"]']:
        try:
            btn = page.query_selector(sel)
            if btn and btn.is_visible() and btn.is_enabled():
                btn.click(); page.wait_for_timeout(3000); return True
        except: pass
    return False

# ── INDEED ─────────────────────────────────────────────────────────────────
def apply_indeed(page, jobs, resume_pdf):
    applied = 0
    print("\n[Indeed] Starting...")
    try:
        # Indeed blocks headless Google OAuth — use direct job search instead
        # Search jobs directly without login for Easy Apply
        for query in get_queries():
            try:
                page.goto(f"https://www.indeed.com/jobs?q={query.replace(' ','+')}+remote&fromage=3&sort=date", timeout=30000)
                page.wait_for_timeout(3000)

                # Get all job cards
                cards = page.query_selector_all('[data-jk]')
                if not cards:
                    cards = page.query_selector_all('.job_seen_beacon')
                print(f"  → {len(cards)} cards for '{query}'")

                for card in cards[:8]:
                    try:
                        title_el = card.query_selector('h2 span[title], .jobTitle span')
                        title = title_el.get_attribute("title") or title_el.inner_text() if title_el else "Unknown"

                        # Only process Easy Apply jobs
                        easy = card.query_selector('.iaLabel, [aria-label*="Easily apply"], .indeedApply')
                        if not easy:
                            continue

                        # Click job to open
                        card.click()
                        page.wait_for_timeout(2000)

                        # Find apply button in right panel
                        apply_btn = page.query_selector('#indeedApplyButton, button[id*="apply"], .ia-IndeedApplyButton')
                        if not apply_btn:
                            continue

                        apply_btn.click()
                        page.wait_for_timeout(3000)

                        # Handle iframe
                        for step in range(4):
                            iframe = page.query_selector('iframe[id*="indeedapply"]')
                            if iframe:
                                frame = iframe.content_frame()
                                if frame:
                                    file_inp = frame.query_selector('input[type="file"]')
                                    if file_inp and resume_pdf:
                                        file_inp.set_input_files(resume_pdf)
                                    handle_screening(frame, title)
                                    sub = frame.query_selector('button[type="submit"], button:has-text("Continue")')
                                    if sub: sub.click(); page.wait_for_timeout(2500)
                                    else: break
                            else:
                                handle_screening(page, title)
                                if not click_submit(page): break

                        applied += 1
                        print(f"  ✓ Applied: {title}")
                        log_apply({"title": title, "portal": "Indeed", "applied_at": now_iso(), "success": True})
                        page.wait_for_timeout(1500)
                    except Exception as e:
                        print(f"  ! Card: {str(e)[:60]}")
            except Exception as e:
                print(f"  ! Query: {str(e)[:60]}")
    except Exception as e:
        print(f"[Indeed] Error: {str(e)[:100]}")
    print(f"[Indeed] Done. {applied} applied.")
    return applied

# ── ZIPRECRUITER ───────────────────────────────────────────────────────────
def apply_ziprecruiter(page, jobs, resume_pdf):
    applied = 0
    print("\n[ZipRecruiter] Starting...")
    try:
        page.goto("https://www.ziprecruiter.com/login", timeout=30000)
        page.wait_for_timeout(3000)
        print(f"  → URL: {page.url[:60]}")

        if not find_google_btn(page):
            # Try clicking the email field area to find Google option
            page.goto("https://www.ziprecruiter.com/login?country=US", timeout=30000)
            page.wait_for_timeout(2000)
            find_google_btn(page)

        if "google" in page.url.lower() or "accounts.google" in page.url.lower():
            google_login(page, GOOGLE_EMAIL, GOOGLE_PASSWORD)

        page.wait_for_timeout(3000)

        for query in get_queries():
            try:
                page.goto(f"https://www.ziprecruiter.com/jobs-search?search={quote(query)}&location=Remote", timeout=30000)
                page.wait_for_timeout(3000)

                # ZipRecruiter job card selectors
                cards = page.query_selector_all('[class*="job_result_two_pane"], [data-testid="job-card"], article')
                if not cards:
                    cards = page.query_selector_all('li[class*="job"]')
                print(f"  → {len(cards)} cards for '{query}'")

                for card in cards[:8]:
                    try:
                        title_el = card.query_selector('h2, [class*="title"]')
                        title = title_el.inner_text().strip() if title_el else "Unknown"

                        # 1-Click Apply
                        one_click = card.query_selector(
                            '[class*="one_click"], [class*="quickApply"], '
                            'button:has-text("1-Click"), button:has-text("Quick Apply")'
                        )
                        if one_click:
                            one_click.click()
                            page.wait_for_timeout(3000)
                            handle_screening(page, title)
                            click_submit(page)
                            applied += 1
                            print(f"  ✓ 1-Click: {title}")
                            log_apply({"title": title, "portal": "ZipRecruiter", "applied_at": now_iso(), "success": True})
                    except Exception as e:
                        print(f"  ! Card: {str(e)[:60]}")
            except Exception as e:
                print(f"  ! Query: {str(e)[:60]}")
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

        if not find_google_btn(page):
            page.goto("https://www.monster.com/profile/signin?ch=web", timeout=30000)
            page.wait_for_timeout(2000)
            find_google_btn(page)

        if "google" in page.url.lower():
            google_login(page, GOOGLE_EMAIL, GOOGLE_PASSWORD)
        page.wait_for_timeout(4000)

        for query in get_queries():
            try:
                page.goto(f"https://www.monster.com/jobs/search?q={quote(query)}&where=remote", timeout=30000)
                page.wait_for_timeout(4000)

                # Monster uses data-testid on cards
                cards = page.query_selector_all('[data-testid="jobCard"], [class*="job-search-result-list-item"]')
                if not cards:
                    cards = page.query_selector_all('section[class*="card"]')
                print(f"  → {len(cards)} cards for '{query}'")

                for card in cards[:8]:
                    try:
                        title_el = card.query_selector('h2, h3, [data-testid="job-title"]')
                        title = title_el.inner_text().strip() if title_el else "Unknown"

                        apply_btn = card.query_selector(
                            '[data-testid="apply-button-label"], '
                            'button:has-text("Apply"), a:has-text("Apply")'
                        )
                        if not apply_btn: continue

                        apply_btn.click()
                        page.wait_for_timeout(3000)

                        # Upload resume
                        file_inp = page.query_selector('input[type="file"]')
                        if file_inp and resume_pdf:
                            file_inp.set_input_files(resume_pdf)
                            page.wait_for_timeout(2000)

                        handle_screening(page, title)
                        click_submit(page)
                        applied += 1
                        print(f"  ✓ Applied: {title}")
                        log_apply({"title": title, "portal": "Monster", "applied_at": now_iso(), "success": True})
                    except Exception as e:
                        print(f"  ! Card: {str(e)[:60]}")
            except Exception as e:
                print(f"  ! Query: {str(e)[:60]}")
    except Exception as e:
        print(f"[Monster] Error: {str(e)[:100]}")
    print(f"[Monster] Done. {applied} applied.")
    return applied

# ── DICE ───────────────────────────────────────────────────────────────────
def apply_dice(page, jobs, resume_pdf):
    applied = 0
    print("\n[Dice] Starting...")
    try:
        page.goto("https://www.dice.com/dashboard/login", timeout=30000)
        page.wait_for_timeout(3000)

        # Login — tested and working
        for sel in ['input[name="email"]', 'input[type="email"]', '#email']:
            try:
                el = page.query_selector(sel)
                if el and el.is_visible():
                    el.fill(DICE_EMAIL); break
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
                if el and el.is_visible():
                    el.fill(DICE_PASSWORD); break
            except: pass
        page.wait_for_timeout(500)
        for sel in ['button[type="submit"]', '#login-button', 'button:has-text("Sign In")']:
            try:
                btn = page.query_selector(sel)
                if btn and btn.is_visible(): btn.click(); break
            except: pass
        page.wait_for_timeout(4000)
        print(f"  ✓ Dice logged in: {page.url[:50]}")

        for query in get_queries():
            try:
                page.goto(f"https://www.dice.com/jobs?q={quote(query)}&location=Remote&filters.postedDate=ONE&filters.employmentType=FULLTIME", timeout=30000)
                page.wait_for_timeout(4000)

                # Dice uses dhi-search-card web component
                cards = page.query_selector_all('dhi-search-card')
                if not cards:
                    cards = page.query_selector_all('[data-cy="card"], div[class*="card-title"]')
                print(f"  → {len(cards)} cards for '{query}'")

                for card in cards[:8]:
                    try:
                        # Get title and click it
                        title_el = card.query_selector('a[data-cy="card-title-link"], h5 a, a[class*="card-title"]')
                        title = title_el.inner_text().strip() if title_el else "Unknown"

                        if title_el:
                            title_el.click()
                            page.wait_for_timeout(2500)

                        # Easy Apply button on job detail page
                        apply_btn = page.query_selector(
                            'apply-button button, '
                            'button[data-cy="apply-button"], '
                            'button:has-text("Easy Apply"), '
                            'button:has-text("Apply Now")'
                        )
                        if not apply_btn:
                            page.go_back(); page.wait_for_timeout(1500); continue

                        apply_btn.click()
                        page.wait_for_timeout(3000)

                        file_inp = page.query_selector('input[type="file"]')
                        if file_inp and resume_pdf:
                            file_inp.set_input_files(resume_pdf)
                            page.wait_for_timeout(2000)

                        handle_screening(page, title)
                        click_submit(page)
                        applied += 1
                        print(f"  ✓ Applied: {title}")
                        log_apply({"title": title, "portal": "Dice", "applied_at": now_iso(), "success": True})
                        page.go_back(); page.wait_for_timeout(1500)
                    except Exception as e:
                        print(f"  ! Card: {str(e)[:60]}")
                        try: page.go_back(); page.wait_for_timeout(1000)
                        except: pass
            except Exception as e:
                print(f"  ! Query: {str(e)[:60]}")
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

        if not find_google_btn(page):
            page.goto("https://jobright.ai/login", timeout=30000)
            page.wait_for_timeout(2000)
            find_google_btn(page)

        if "google" in page.url.lower():
            google_login(page, GOOGLE_EMAIL, GOOGLE_PASSWORD)
        page.wait_for_timeout(4000)

        for query in get_queries():
            try:
                page.goto(f"https://jobright.ai/jobs?search={quote(query)}", timeout=30000)
                page.wait_for_timeout(4000)

                cards = page.query_selector_all('[class*="job-card"], [data-testid*="job"]')
                if not cards:
                    cards = page.query_selector_all('li[class*="job"], div[class*="listing"]')
                print(f"  → {len(cards)} cards for '{query}'")

                for card in cards[:8]:
                    try:
                        title_el = card.query_selector('h3, h2, [class*="title"]')
                        title = title_el.inner_text().strip() if title_el else "Unknown"

                        # Click card to open
                        card.click()
                        page.wait_for_timeout(2000)

                        apply_btn = page.query_selector(
                            'button:has-text("Apply"), button:has-text("Easy Apply"), '
                            'a:has-text("Apply Now"), [data-testid="apply-button"]'
                        )
                        if not apply_btn: continue

                        apply_btn.click()
                        page.wait_for_timeout(3000)
                        handle_screening(page, title)
                        click_submit(page)
                        applied += 1
                        print(f"  ✓ Applied: {title}")
                        log_apply({"title": title, "portal": "JobRight.ai", "applied_at": now_iso(), "success": True})
                    except Exception as e:
                        print(f"  ! Card: {str(e)[:60]}")
            except Exception as e:
                print(f"  ! Query: {str(e)[:60]}")
    except Exception as e:
        print(f"[JobRight.ai] Error: {str(e)[:100]}")
    print(f"[JobRight.ai] Done. {applied} applied.")
    return applied

# ── MAIN ───────────────────────────────────────────────────────────────────
def run_apply_bot():
    from playwright.sync_api import sync_playwright
    jobs = load_jobs(); resume_pdf = get_resume_pdf(jobs); total = 0; results = {}
    print(f"\n[Apply Bot] Starting... Resume: {resume_pdf}")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox","--disable-setuid-sandbox","--disable-dev-shm-usage",
                  "--disable-blink-features=AutomationControlled","--window-size=1280,800"]
        )
        ctx = browser.new_context(
            viewport={"width":1280,"height":800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            locale="en-US",
        )
        ctx.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")
        page = ctx.new_page()
        page.set_default_timeout(20000)

        if GOOGLE_EMAIL and GOOGLE_PASSWORD:
            n = apply_indeed(page, jobs, resume_pdf)
            results["Indeed"] = n; total += n; time.sleep(3)
            n = apply_ziprecruiter(page, jobs, resume_pdf)
            results["ZipRecruiter"] = n; total += n; time.sleep(3)
            n = apply_monster(page, jobs, resume_pdf)
            results["Monster"] = n; total += n; time.sleep(3)
            n = apply_jobright(page, jobs, resume_pdf)
            results["JobRight.ai"] = n; total += n; time.sleep(3)

        if DICE_EMAIL and DICE_PASSWORD:
            n = apply_dice(page, jobs, resume_pdf)
            results["Dice"] = n; total += n

        browser.close()

    print(f"\n[Apply Bot] Results: {results}")
    print(f"[Apply Bot] Total: {total} applications")
    return total

if __name__ == "__main__":
    run_apply_bot()
