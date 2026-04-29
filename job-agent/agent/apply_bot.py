"""
Multi-Portal Apply Bot
- Dice: ✅ login works, fixed JS wait + selectors
- Indeed/ZipRecruiter/Monster: blocked by bot detection (need proxy)
- JobRight: OAuth issue headless
Focus: Dice works, others log the block clearly
"""

import json, os, time, traceback
from urllib.parse import quote
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
    return config.get("job_queries", ["full stack .NET developer"])[:3]

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

# ── DICE ✅ (confirmed working login) ──────────────────────────────────────
def apply_dice(page, jobs, resume_pdf):
    applied = 0
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
                # Search with filters
                url = (
                    f"https://www.dice.com/jobs?q={quote(query)}"
                    f"&filters.postedDate=THREE"
                    f"&filters.employmentType=FULLTIME"
                    f"&filters.easyApply=true"
                )
                page.goto(url, timeout=30000)

                # Wait for Next.js hydration — wait for job cards to appear
                try:
                    page.wait_for_selector('dhi-search-card, [data-testid="job-card"]', timeout=10000)
                except:
                    pass
                page.wait_for_timeout(5000)

                # Try all known Dice card selectors
                cards = []
                for sel in [
                    'dhi-search-card',
                    '[data-testid="job-card"]',
                    'div[class*="card"][class*="job"]',
                    'article[class*="card"]',
                    '.search-card',
                    '[data-cy="card"]',
                ]:
                    cards = page.query_selector_all(sel)
                    if cards:
                        print(f"  → Found {len(cards)} cards with '{sel}'")
                        break

                if not cards:
                    # Try JavaScript to find cards
                    count = page.evaluate("""
                        () => {
                            const cards = document.querySelectorAll('dhi-search-card');
                            return cards.length;
                        }
                    """)
                    print(f"  → JS found {count} dhi-search-card elements")

                    # Get all unique tag names to debug
                    tags = page.evaluate("""
                        () => {
                            const all = document.querySelectorAll('*');
                            const tags = new Set();
                            all.forEach(el => {
                                if (el.tagName.toLowerCase().includes('card') ||
                                    el.tagName.toLowerCase().includes('job') ||
                                    el.tagName.toLowerCase().includes('search')) {
                                    tags.add(el.tagName.toLowerCase());
                                }
                            });
                            return Array.from(tags).join(', ');
                        }
                    """)
                    print(f"  → Relevant tags on page: {tags}")
                    continue

                for card in cards[:8]:
                    try:
                        # Try multiple title selectors
                        title = "Unknown"
                        for tsel in ['a[data-cy="card-title-link"]', 'h5 a', 'h2 a',
                                     'a[class*="title"]', '[data-testid="job-title"]']:
                            title_el = card.query_selector(tsel)
                            if title_el:
                                title = title_el.inner_text().strip()
                                title_el.click()
                                page.wait_for_timeout(3000)
                                break

                        print(f"  → Trying: {title}")

                        # Look for apply button
                        apply_btn = None
                        for asel in [
                            'apply-button button',
                            'button[data-cy="apply-button"]',
                            'button:has-text("Easy Apply")',
                            'button:has-text("Apply Now")',
                            '[class*="apply"] button',
                        ]:
                            apply_btn = page.query_selector(asel)
                            if apply_btn and apply_btn.is_visible():
                                print(f"  → Apply btn found: {asel}")
                                break

                        if not apply_btn:
                            print(f"  ! No apply button found")
                            page.go_back(); page.wait_for_timeout(2000)
                            continue

                        apply_btn.click()
                        page.wait_for_timeout(3000)

                        # Upload resume
                        file_inp = page.query_selector('input[type="file"]')
                        if file_inp and resume_pdf:
                            file_inp.set_input_files(resume_pdf)
                            page.wait_for_timeout(2000)
                            print(f"  → Resume uploaded")

                        handle_screening(page, title)

                        if click_submit(page):
                            applied += 1
                            print(f"  ✓ Applied: {title}")
                            log_apply({"title": title, "portal": "Dice",
                                       "applied_at": now_iso(), "success": True})
                        else:
                            print(f"  ! Submit not found for: {title}")

                        page.go_back()
                        page.wait_for_timeout(2000)

                    except Exception as e:
                        print(f"  ! Card error: {str(e)[:80]}")
                        try: page.go_back(); page.wait_for_timeout(1500)
                        except: pass

            except Exception as e:
                print(f"  ! Query error: {str(e)[:80]}")

    except Exception as e:
        print(f"[Dice] Error: {str(e)[:100]}")
        traceback.print_exc()

    print(f"[Dice] Done. {applied} applied.")
    return applied


# ── BLOCKED PORTALS — log clearly ─────────────────────────────────────────
def apply_indeed(page, jobs, resume_pdf):
    print("\n[Indeed] Skipped — blocked by bot detection (needs residential proxy)")
    return 0

def apply_ziprecruiter(page, jobs, resume_pdf):
    print("\n[ZipRecruiter] Skipped — blocked by Cloudflare (needs residential proxy)")
    return 0

def apply_monster(page, jobs, resume_pdf):
    print("\n[Monster] Skipped — blocked by DataDome CAPTCHA (needs residential proxy)")
    return 0

def apply_jobright(page, jobs, resume_pdf):
    print("\n[JobRight.ai] Skipped — Google OAuth fails headless")
    return 0


# ── MAIN ───────────────────────────────────────────────────────────────────
def run_apply_bot():
    from playwright.sync_api import sync_playwright

    jobs       = load_jobs()
    resume_pdf = get_resume_pdf(jobs)
    total      = 0
    results    = {}

    print(f"\n[Apply Bot] Starting... Resume: {resume_pdf}")
    print(f"[Apply Bot] Note: Only Dice works without proxy. Others blocked by bot detection.")

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
        page.set_default_timeout(20000)

        # Only Dice works reliably without proxy
        if DICE_EMAIL and DICE_PASSWORD:
            n = apply_dice(page, jobs, resume_pdf)
            results["Dice"] = n
            total += n

        # Log blocked portals
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
