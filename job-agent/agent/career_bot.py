"""
Career Page Apply Bot — Workday / Greenhouse / Lever / iCIMS / SmartRecruiters

Unlike apply_bot.py (which live-searches Dice itself), this bot works off
jobs.json entries the pipeline already scraped and scored: it only attempts
a job whose fit_score (computed by ai_engine.py from the actual job
requirements) is at or above min_apply_score, and whose URL resolves to one
of the supported career-page platforms.

Greenhouse and Lever postings are usually a single guest form (no account
needed) and are fairly reliable to automate. Workday and iCIMS/SmartRecruiters
often require creating a candidate account first and run a multi-step wizard
that varies by company tenant — those handlers are best-effort.
"""

import json, os, time
from pathlib import Path
from urllib.parse import urlparse

from apply_bot import (
    PROFILE, MIN_APPLY_SCORE, AUTO_APPLY_ENABLED,
    fill_form_fields, log_apply, load_applied_urls, now_iso, get_resume_pdf,
)

DATA_FILE   = Path("data/jobs.json")
CONFIG_FILE = Path("data/config.json")

WORKDAY_EMAIL    = os.environ.get("WORKDAY_EMAIL", PROFILE.get("email", ""))
WORKDAY_PASSWORD = os.environ.get("WORKDAY_PASSWORD", "")


def load_jobs():
    return json.loads(DATA_FILE.read_text()) if DATA_FILE.exists() else {}


def save_jobs(jobs):
    DATA_FILE.write_text(json.dumps(jobs, indent=2))


def load_config():
    return json.loads(CONFIG_FILE.read_text()) if CONFIG_FILE.exists() else {}


def detect_platform(url: str) -> str:
    host = urlparse(url).netloc.lower()
    if "myworkdayjobs.com" in host or "workday" in host:
        return "Workday"
    if "greenhouse.io" in host:
        return "Greenhouse"
    if "lever.co" in host:
        return "Lever"
    if "icims.com" in host:
        return "iCIMS"
    if "smartrecruiters.com" in host:
        return "SmartRecruiters"
    return ""


def get_ready_jobs(jobs: dict, applied_urls: set) -> list:
    """Jobs the AI engine already scored, above the apply bar, not yet career-applied."""
    ready = []
    for jid, job in jobs.items():
        if job.get("career_applied"):
            continue
        url = job.get("url", "")
        if not url or url in applied_urls:
            continue
        score = job.get("fit_score")
        if score is None or score < MIN_APPLY_SCORE:
            continue
        ready.append((jid, job))
    return ready


def mark_result(jobs: dict, jid: str, platform: str, success: bool, reason: str):
    jobs[jid]["career_applied"]        = success
    jobs[jid]["career_apply_platform"] = platform
    jobs[jid]["career_apply_at"]       = now_iso()
    jobs[jid]["career_apply_note"]     = reason
    save_jobs(jobs)


def upload_resume(page, resume_pdf: str) -> bool:
    if not resume_pdf:
        return False
    try:
        file_inp = page.query_selector('input[type="file"]')
        if file_inp:
            file_inp.set_input_files(resume_pdf)
            page.wait_for_timeout(2000)
            return True
    except Exception:
        pass
    return False


def page_says_submitted(page) -> bool:
    try:
        body = page.inner_text("body").lower()
    except Exception:
        return False
    return any(k in body for k in [
        "application submitted", "thanks for applying", "thank you for applying",
        "successfully submitted", "application received", "we have received your application",
        "thank you for your application",
    ])


# ── GREENHOUSE ────────────────────────────────────────────────────────────────

def apply_greenhouse(page, job: dict, resume_pdf: str):
    try:
        for sel in ['a:has-text("Apply for this job")', 'a:has-text("Apply Now")', 'a:has-text("Apply")']:
            try:
                btn = page.query_selector(sel)
                if btn and btn.is_visible():
                    btn.click()
                    page.wait_for_timeout(1500)
                    break
            except Exception:
                pass

        if not page.query_selector("form"):
            return False, "no application form found"

        upload_resume(page, resume_pdf)
        page.wait_for_timeout(1000)

        first, *rest = (PROFILE.get("name", "") or "Candidate").split(" ") or ["Candidate"]
        last = " ".join(rest) or "Candidate"
        for sel, value in [
            ('input#first_name', first),
            ('input#last_name', last),
            ('input#email', PROFILE.get("email", "")),
            ('input#phone', PROFILE.get("phone", "")),
        ]:
            try:
                el = page.query_selector(sel)
                if el and el.is_visible() and not el.input_value():
                    el.fill(value)
            except Exception:
                pass

        fill_form_fields(page, job.get("title", ""))
        page.wait_for_timeout(500)

        submit = page.query_selector(
            'button#submit_app, input#submit_app, button:has-text("Submit Application")'
        )
        if not (submit and submit.is_visible()):
            return False, "submit button not found"
        submit.click()
        page.wait_for_timeout(4000)

        return (True, "submitted") if page_says_submitted(page) else (False, "no confirmation detected")
    except Exception as e:
        return False, f"error: {str(e)[:100]}"


# ── LEVER ─────────────────────────────────────────────────────────────────────

def apply_lever(page, job: dict, resume_pdf: str):
    try:
        if not page.url.rstrip("/").endswith("/apply"):
            page.goto(page.url.rstrip("/") + "/apply", timeout=30000)
            page.wait_for_timeout(2000)

        if not page.query_selector("form"):
            return False, "no application form found"

        upload_resume(page, resume_pdf)
        page.wait_for_timeout(1000)

        for sel, value in [
            ('input[name="name"]', PROFILE.get("name", "")),
            ('input[name="email"]', PROFILE.get("email", "")),
            ('input[name="phone"]', PROFILE.get("phone", "")),
        ]:
            try:
                el = page.query_selector(sel)
                if el and el.is_visible() and not el.input_value():
                    el.fill(value)
            except Exception:
                pass

        fill_form_fields(page, job.get("title", ""))
        page.wait_for_timeout(500)

        submit = page.query_selector('button[type="submit"]')
        if not (submit and submit.is_visible() and submit.is_enabled()):
            return False, "submit button not found"
        submit.click()
        page.wait_for_timeout(4000)

        return (True, "submitted") if page_says_submitted(page) else (False, "no confirmation detected")
    except Exception as e:
        return False, f"error: {str(e)[:100]}"


# ── WORKDAY (best-effort — UI varies per company tenant) ─────────────────────

def _workday_ensure_account(page) -> bool:
    try:
        needs_auth = page.query_selector('input[data-automation-id="email"], input[type="email"]')
        if not needs_auth:
            return True

        for sel in ['a:has-text("Create Account")', 'div[data-automation-id="createAccountLink"]',
                    'button:has-text("Create Account")']:
            try:
                el = page.query_selector(sel)
                if el and el.is_visible():
                    el.click()
                    page.wait_for_timeout(1500)
                    break
            except Exception:
                pass

        for sel in ['input[data-automation-id="email"]', 'input[type="email"]']:
            el = page.query_selector(sel)
            if el and el.is_visible():
                el.fill(WORKDAY_EMAIL)
                break

        pw_filled = 0
        for sel in ['input[data-automation-id="password"]', 'input[data-automation-id="verifyPassword"]',
                    'input[type="password"]']:
            for el in page.query_selector_all(sel):
                try:
                    if el.is_visible():
                        el.fill(WORKDAY_PASSWORD)
                        pw_filled += 1
                except Exception:
                    pass
            if pw_filled >= 2:
                break

        try:
            cb = page.query_selector('input[type="checkbox"]')
            if cb and cb.is_visible() and not cb.is_checked():
                cb.check()
        except Exception:
            pass

        for sel in ['button[data-automation-id="createAccountSubmitButton"]',
                    'button:has-text("Create Account")', 'button:has-text("Sign In")']:
            try:
                btn = page.query_selector(sel)
                if btn and btn.is_visible() and btn.is_enabled():
                    btn.click()
                    page.wait_for_timeout(3000)
                    break
            except Exception:
                pass

        return True
    except Exception:
        return False


def _decline_voluntary_disclosures(page):
    """Best-effort: pick a 'decline to answer' option on EEO / self-identify steps."""
    decline_texts = ["decline to self identify", "i do not wish to answer",
                     "prefer not to answer", "do not wish to answer"]
    try:
        for combo in page.query_selector_all('button[aria-haspopup="listbox"]'):
            try:
                combo.click()
                page.wait_for_timeout(300)
                for opt in page.query_selector_all('[role="option"]'):
                    text = (opt.inner_text() or "").strip().lower()
                    if any(d in text for d in decline_texts):
                        opt.click()
                        break
                page.keyboard.press("Escape")
            except Exception:
                pass
    except Exception:
        pass


def apply_workday(page, job: dict, resume_pdf: str):
    try:
        for sel in ['a:has-text("Apply")', 'button:has-text("Apply")']:
            try:
                btn = page.query_selector(sel)
                if btn and btn.is_visible():
                    btn.click()
                    page.wait_for_timeout(2500)
                    break
            except Exception:
                pass

        for sel in ['button:has-text("Autofill with Resume")', 'div[data-automation-id="autofillWithResume"]']:
            try:
                btn = page.query_selector(sel)
                if btn and btn.is_visible():
                    btn.click()
                    page.wait_for_timeout(1000)
                    upload_resume(page, resume_pdf)
                    page.wait_for_timeout(3000)
                    break
            except Exception:
                pass

        if not _workday_ensure_account(page):
            return False, "account creation failed"

        for step in range(10):
            page.wait_for_timeout(2000)
            if page_says_submitted(page):
                return True, "submitted"

            upload_resume(page, resume_pdf)
            fill_form_fields(page, job.get("title", ""))
            _decline_voluntary_disclosures(page)
            page.wait_for_timeout(500)

            submitted = False
            for sel in ['button:has-text("Submit")',
                        'button[data-automation-id="bottom-navigation-next-button"]:has-text("Submit")']:
                try:
                    btn = page.query_selector(sel)
                    if btn and btn.is_visible() and btn.is_enabled():
                        btn.click()
                        page.wait_for_timeout(4000)
                        submitted = True
                        break
                except Exception:
                    pass
            if submitted:
                continue

            advanced = False
            for sel in ['button[data-automation-id="bottom-navigation-next-button"]',
                        'button:has-text("Next")', 'button:has-text("Continue")']:
                try:
                    btn = page.query_selector(sel)
                    if btn and btn.is_visible() and btn.is_enabled():
                        btn.click()
                        page.wait_for_timeout(2500)
                        advanced = True
                        break
                except Exception:
                    pass
            if not advanced:
                return False, f"stuck at step {step + 1}, no Next/Submit found"

        return False, "exceeded max steps"
    except Exception as e:
        return False, f"error: {str(e)[:100]}"


# ── iCIMS / SmartRecruiters (best-effort generic wizard, no account) ─────────

def apply_generic_wizard(page, job: dict, resume_pdf: str):
    try:
        for sel in ['a:has-text("Apply")', 'button:has-text("Apply")', 'a:has-text("Apply Now")']:
            try:
                btn = page.query_selector(sel)
                if btn and btn.is_visible():
                    btn.click()
                    page.wait_for_timeout(2000)
                    break
            except Exception:
                pass

        for step in range(8):
            page.wait_for_timeout(1500)
            if page_says_submitted(page):
                return True, "submitted"

            upload_resume(page, resume_pdf)
            fill_form_fields(page, job.get("title", ""))

            submitted = False
            for sel in ['button:has-text("Submit")', 'button:has-text("Submit Application")',
                        'input[type="submit"]']:
                try:
                    btn = page.query_selector(sel)
                    if btn and btn.is_visible() and btn.is_enabled():
                        btn.click()
                        page.wait_for_timeout(4000)
                        submitted = True
                        break
                except Exception:
                    pass
            if submitted:
                continue

            advanced = False
            for sel in ['button:has-text("Next")', 'button:has-text("Continue")']:
                try:
                    btn = page.query_selector(sel)
                    if btn and btn.is_visible() and btn.is_enabled():
                        btn.click()
                        page.wait_for_timeout(2000)
                        advanced = True
                        break
                except Exception:
                    pass
            if not advanced:
                return False, f"stuck at step {step + 1}"

        return False, "exceeded max steps"
    except Exception as e:
        return False, f"error: {str(e)[:100]}"


def apply_icims(page, job, resume_pdf):
    return apply_generic_wizard(page, job, resume_pdf)


def apply_smartrecruiters(page, job, resume_pdf):
    return apply_generic_wizard(page, job, resume_pdf)


PLATFORM_HANDLERS = {
    "Greenhouse":      apply_greenhouse,
    "Lever":           apply_lever,
    "Workday":         apply_workday,
    "iCIMS":           apply_icims,
    "SmartRecruiters": apply_smartrecruiters,
}


def resolve_and_apply(page, job: dict, resume_pdf: str):
    url = job.get("url", "")
    if not url:
        return False, "no url", ""
    try:
        page.goto(url, timeout=30000)
        page.wait_for_timeout(2500)
    except Exception as e:
        return False, f"navigation error: {str(e)[:100]}", ""

    # Resolve off the final URL (after redirects), not the stored one — many
    # scraped links go through Adzuna/Google tracking redirects first.
    platform = detect_platform(page.url)
    if not platform:
        return False, f"unsupported career platform ({urlparse(page.url).netloc})", ""

    handler = PLATFORM_HANDLERS[platform]
    try:
        success, reason = handler(page, job, resume_pdf)
    except Exception as e:
        success, reason = False, f"handler error: {str(e)[:100]}"
    return success, reason, platform


def run_career_bot():
    if not AUTO_APPLY_ENABLED:
        print("\n[Career Bot] auto_apply_enabled is false in config.json — skipping.")
        return 0

    config       = load_config()
    max_per_run  = int(config.get("max_career_applies_per_run", 10))

    jobs         = load_jobs()
    applied_urls = load_applied_urls()
    candidates   = get_ready_jobs(jobs, applied_urls)[:max_per_run]

    print(f"\n[Career Bot] {len(candidates)} requirement-matched jobs to check "
          f"(min_apply_score={MIN_APPLY_SCORE})")
    if not candidates:
        print("[Career Bot] Done. 0 applications submitted.")
        return 0

    resume_pdf = get_resume_pdf(jobs)
    total = 0

    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox", "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
                "--window-size=1280,800",
            ],
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
        ctx.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")
        page = ctx.new_page()
        page.set_default_timeout(30000)

        for jid, job in candidates:
            print(f"\n[Career Bot] {job.get('title')} @ {job.get('company')} "
                  f"(fit {job.get('fit_score')})")
            success, reason, platform = resolve_and_apply(page, job, resume_pdf)
            print(f"  {'OK Applied' if success else 'x Not applied'} [{platform or 'n/a'}]: {reason}")

            mark_result(jobs, jid, platform, success, reason)

            if success:
                total += 1
                log_apply({
                    "title": job.get("title"), "url": job.get("url"), "portal": platform,
                    "applied_at": now_iso(), "success": True,
                    "requirement_score": job.get("fit_score"),
                    "requirement_reason": job.get("fit_analysis", {}).get("angle", ""),
                })

            time.sleep(2)

        browser.close()

    print(f"\n[Career Bot] Done. {total} applications submitted.")
    return total


if __name__ == "__main__":
    run_career_bot()
