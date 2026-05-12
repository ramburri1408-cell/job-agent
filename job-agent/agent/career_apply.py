"""
Career Page Apply Bot — Uses Apify Google Search to find career pages
Avoids CAPTCHA by using Apify's Google Search actor
"""

import os, json, re, time
from pathlib import Path
from datetime import datetime, timezone
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from apify_client import ApifyClient

GMAIL_USER  = os.environ.get("GMAIL_USER", "")
GMAIL_PASS  = os.environ.get("GMAIL_APP_PASSWORD", "")
APIFY_TOKEN = os.environ.get("APIFY_API_KEY", "")
RAM_EMAIL   = "Ram.burri1408@gmail.com"
DATA_FILE   = Path("data/jobs.json")
LOG_FILE    = Path("data/career_apply_log.jsonl")

JOB_BOARDS = [
    "adzuna.com", "adzuna.co.uk", "indeed.com", "dice.com",
    "ziprecruiter.com", "monster.com", "glassdoor.com",
    "linkedin.com", "remotive.com", "simplyhired.com",
    "careerbuilder.com",
]

ATS_PLATFORMS = [
    "workday", "myworkdayjobs", "icims", "greenhouse.io",
    "lever.co", "taleo", "jobvite", "smartrecruiters",
    "successfactors", "breezy.hr",
]

PROFILE = {
    "first_name":   "Ram",
    "last_name":    "Burri",
    "full_name":    "Ram Burri",
    "email":        "Ram.burri1408@gmail.com",
    "phone":        "9544454339",
    "phone_format": "(954) 445-4339",
    "city":         "Boca Raton",
    "state":        "Florida",
    "state_abbr":   "FL",
    "zip":          "33431",
    "country":      "United States",
    "linkedin":     "https://www.linkedin.com/in/ramburri",
    "experience":   "4",
    "title":        "Full Stack .NET Developer",
    "salary":       "110000",
    "authorized":   "Yes",
    "sponsorship":  "No",
    "visa":         "OPT",
    "university":   "Florida Atlantic University",
    "degree":       "Master of Science in Computer Science",
    "grad_year":    "2025",
}

def load_jobs():
    return json.loads(DATA_FILE.read_text()) if DATA_FILE.exists() else {}

def log_apply(entry):
    LOG_FILE.parent.mkdir(exist_ok=True)
    with LOG_FILE.open("a") as f:
        f.write(json.dumps(entry) + "\n")

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def is_job_board(url: str) -> bool:
    return any(board in url.lower() for board in JOB_BOARDS)

def is_ats_url(url: str) -> bool:
    return any(ats in url.lower() for ats in ATS_PLATFORMS)

def detect_platform(page) -> str:
    url  = page.url.lower()
    html = page.content().lower()
    if "myworkdayjobs.com" in url or "workday.com" in url: return "workday"
    if "icims.com" in url or "icims" in html:              return "icims"
    if "greenhouse.io" in url:                             return "greenhouse"
    if "lever.co" in url:                                  return "lever"
    if "taleo" in url or "taleo" in html:                  return "taleo"
    if "jobvite" in url:                                   return "jobvite"
    if "smartrecruiters" in url:                           return "smartrecruiters"
    if "successfactors" in url:                            return "successfactors"
    has_form = (
        page.query_selector('input[type="file"]') or
        page.query_selector('form[action*="apply"]')
    )
    if has_form: return "generic_form"
    return "listing_page"

def find_career_page_apify(company: str, job_title: str) -> str:
    """
    Use Apify Google Search actor to find company career page.
    Handles CAPTCHA automatically — no manual browser needed.
    """
    if not APIFY_TOKEN:
        print(f"  ! No Apify token")
        return ""

    queries = [
        f'"{company}" careers apply {job_title} site:myworkdayjobs.com OR site:icims.com OR site:greenhouse.io OR site:lever.co',
        f'"{company}" official careers apply jobs',
        f'{company} careers {job_title} apply now',
    ]

    apify = ApifyClient(APIFY_TOKEN)

    for query in queries:
        try:
            print(f"  → Apify searching: {query[:70]}...")
            run = apify.actor("apify/google-search-scraper").call(
                run_input={
                    "queries":        query,
                    "maxPagesPerQuery": 1,
                    "resultsPerPage": 10,
                    "languageCode":   "en",
                    "countryCode":    "us",
                },
                timeout_secs=60,
            )

            items = list(apify.dataset(run["defaultDatasetId"]).iterate_items())

            for item in items:
                results = item.get("organicResults", [])
                for result in results:
                    url = result.get("url", "")
                    if not url:
                        continue
                    if is_job_board(url):
                        continue
                    # Prefer ATS platform URLs
                    if is_ats_url(url):
                        print(f"  ✓ ATS career page found: {url[:70]}")
                        return url
                    # Accept company career pages
                    if any(k in url.lower() for k in ["career", "jobs", "apply"]):
                        if not is_job_board(url):
                            print(f"  ✓ Career page found: {url[:70]}")
                            return url

        except Exception as e:
            print(f"  ! Apify search error: {str(e)[:80]}")
            continue

    return ""

def ai_answer(question: str, options: list = None) -> str:
    q = question.lower()
    if "first name"    in q: return PROFILE["first_name"]
    if "last name"     in q: return PROFILE["last_name"]
    if "full name"     in q or "your name" in q: return PROFILE["full_name"]
    if "email"         in q: return PROFILE["email"]
    if "phone"         in q or "mobile" in q: return PROFILE["phone_format"]
    if "city"          in q: return PROFILE["city"]
    if "zip"           in q or "postal" in q: return PROFILE["zip"]
    if "linkedin"      in q: return PROFILE["linkedin"]
    if "salary"        in q or "compensation" in q: return PROFILE["salary"]
    if "years of exp"  in q or "how many years" in q: return PROFILE["experience"]
    if "university"    in q or "school" in q: return PROFILE["university"]
    if "grad"          in q: return PROFILE["grad_year"]
    if "state"         in q:
        if options:
            best = next((o for o in options if "florida" in o.lower() or o.upper() == "FL"), None)
            return best or PROFILE["state"]
        return PROFILE["state"]
    if "country"       in q:
        if options:
            best = next((o for o in options if "united states" in o.lower()), None)
            return best or PROFILE["country"]
        return PROFILE["country"]
    if "degree"        in q or "education" in q:
        if options:
            best = next((o for o in options if "master" in o.lower()), None)
            return best or PROFILE["degree"]
        return PROFILE["degree"]
    if any(k in q for k in ["authorized", "eligible", "work in the us"]):
        if options:
            best = next((o for o in options if any(k in o.lower() for k in
                        ["yes", "authorized", "opt", "eligible"])
                        and "not" not in o.lower() and "no " not in o.lower()), None)
            return best or options[0]
        return "Yes"
    if any(k in q for k in ["sponsor", "sponsorship"]):
        if options:
            best = next((o for o in options if any(k in o.lower() for k in
                        ["no", "not require", "don't"])), None)
            return best or options[-1]
        return "No"
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        opts   = f"\nOptions: {options}" if options else ""
        return client.messages.create(
            model="claude-haiku-4-5-20251001", max_tokens=80,
            system="Answer job application questions for Ram Burri, Full Stack .NET Developer, 4 years exp, OPT visa. Brief direct answers.",
            messages=[{"role": "user", "content": f"Q: {question}{opts}\nA:"}]
        ).content[0].text.strip()
    except:
        return "Yes"

def generate_cover_letter(job: dict) -> str:
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        return client.messages.create(
            model="claude-haiku-4-5-20251001", max_tokens=300,
            system="Write a 3-sentence professional cover letter for Ram Burri. Be specific and confident.",
            messages=[{"role": "user", "content":
                f"Job: {job['title']} at {job['company']}\nWrite cover letter:"}]
        ).content[0].text.strip()
    except:
        return (
            f"I am excited to apply for the {job['title']} position at {job['company']}. "
            f"With 4+ years of enterprise .NET development experience with ASP.NET Core, "
            f"React, and Azure, I am confident I will contribute immediately. "
            f"I look forward to discussing how my background aligns with your needs."
        )

def fill_all_fields(page, job: dict) -> int:
    filled = 0
    try:
        for inp in page.query_selector_all(
            'input[type="text"], input[type="email"], input[type="tel"], '
            'input[type="number"], input[type="url"]'
        ):
            try:
                if inp.input_value() or not inp.is_visible(): continue
                lbl = ""
                iid = inp.get_attribute("id") or ""
                if iid:
                    el = page.query_selector(f'label[for="{iid}"]')
                    if el: lbl = el.inner_text()
                if not lbl:
                    lbl = (inp.get_attribute("aria-label") or
                           inp.get_attribute("placeholder") or
                           inp.get_attribute("name") or "")
                if lbl and len(lbl) > 2:
                    inp.fill(ai_answer(lbl)[:200])
                    filled += 1
            except: pass

        for ta in page.query_selector_all("textarea"):
            try:
                if ta.input_value() or not ta.is_visible(): continue
                lbl = ""
                iid = ta.get_attribute("id") or ""
                if iid:
                    el = page.query_selector(f'label[for="{iid}"]')
                    if el: lbl = el.inner_text()
                if not lbl:
                    lbl = ta.get_attribute("aria-label") or ta.get_attribute("placeholder") or ""
                if "cover" in lbl.lower() or "letter" in lbl.lower():
                    ta.fill(generate_cover_letter(job))
                elif lbl:
                    ta.fill(ai_answer(lbl))
                filled += 1
            except: pass

        for sel in page.query_selector_all("select"):
            try:
                if not sel.is_visible(): continue
                opts = [o.inner_text().strip() for o in sel.query_selector_all("option")
                        if o.inner_text().strip()]
                iid  = sel.get_attribute("id") or ""
                lbl  = ""
                if iid:
                    el = page.query_selector(f'label[for="{iid}"]')
                    if el: lbl = el.inner_text()
                if not lbl:
                    lbl = sel.get_attribute("aria-label") or ""
                if lbl and opts:
                    ans  = ai_answer(lbl, opts)
                    best = next((o for o in opts if ans.lower() in o.lower()), None)
                    if best:
                        sel.select_option(label=best)
                        filled += 1
            except: pass

        for grp in page.query_selector_all('fieldset, [role="radiogroup"]'):
            try:
                legend = grp.query_selector('legend')
                lbl    = legend.inner_text() if legend else ""
                radios = grp.query_selector_all('input[type="radio"]')
                if not radios or not lbl: continue
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
                    filled += 1
            except: pass

    except Exception as e:
        print(f"  ! Fill error: {str(e)[:60]}")
    return filled

def upload_resume(page, resume_pdf: str) -> bool:
    if not resume_pdf or not Path(resume_pdf).exists():
        return False
    try:
        for sel in ['input[type="file"]', '[accept*="pdf"]']:
            inp = page.query_selector(sel)
            if inp:
                inp.set_input_files(resume_pdf)
                page.wait_for_timeout(2000)
                print(f"  → Resume uploaded")
                return True
    except Exception as e:
        print(f"  ! Upload error: {str(e)[:60]}")
    return False

def send_review_email(job: dict, screenshot: bytes, apply_url: str, fields_filled: int):
    try:
        msg            = MIMEMultipart()
        msg["From"]    = GMAIL_USER
        msg["To"]      = RAM_EMAIL
        msg["Subject"] = f"🔔 Review & Submit: {job['title']} @ {job['company']}"
        body = f"""Hi Ram,

Your application form has been auto-filled and is ready for review!

📋 Position : {job['title']}
🏢 Company  : {job['company']}
📍 Location : {job.get('location', 'Not specified')}
⭐ Fit Score : {job.get('fit_score', 'N/A')}/100
📝 Fields filled: {fields_filled}

🔗 CLICK TO REVIEW AND SUBMIT:
{apply_url}

What was auto-filled:
✓ Name, email, phone, address (Boca Raton, FL 33431)
✓ Work authorization: Yes (OPT — authorized to work)
✓ Sponsorship required: No
✓ Years of experience: 4
✓ Education: MS CS, Florida Atlantic University (2025)
✓ LinkedIn: linkedin.com/in/ramburri
✓ Salary: $110,000
✓ Resume PDF uploaded
✓ Cover letter generated

📸 Screenshot attached — review all fields then click Submit.

Best,
Job Agent Bot"""
        msg.attach(MIMEText(body, "plain"))
        if screenshot:
            img = MIMEImage(screenshot, _subtype="png")
            img.add_header("Content-Disposition", "attachment",
                           filename=f"filled_{job['company'][:20]}.png")
            msg.attach(img)
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_USER, GMAIL_PASS)
            server.send_message(msg)
        print(f"  ✓ Review email sent to Ram")
        return True
    except Exception as e:
        print(f"  ! Email error: {str(e)[:80]}")
        return False

def handle_application_form(page, job: dict, resume_pdf: str) -> dict:
    result   = {"filled": 0, "screenshot": None, "url": page.url, "ready": False}
    platform = detect_platform(page)
    print(f"  → Platform: {platform}")

    if platform == "workday":
        for asel in [
            '[data-automation-id="applyButton"]',
            'a:has-text("Apply")', 'button:has-text("Apply")',
        ]:
            try:
                btn = page.query_selector(asel)
                if btn and btn.is_visible():
                    btn.click()
                    page.wait_for_timeout(3000)
                    print(f"  → Clicked Workday Apply")
                    break
            except: pass

    for step in range(8):
        page.wait_for_timeout(2000)
        upload_resume(page, resume_pdf)
        n = fill_all_fields(page, job)
        result["filled"] += n
        print(f"  → Step {step+1}: filled {n} fields")
        result["screenshot"] = page.screenshot(full_page=True)
        result["url"]        = page.url

        submit_btn = None
        for sel in [
            'button:has-text("Submit")',
            'button:has-text("Submit Application")',
            'input[value="Submit"]',
            '[data-automation-id*="submit"]',
            '[data-icims-id="submit"]',
        ]:
            try:
                btn = page.query_selector(sel)
                if btn and btn.is_visible():
                    submit_btn = btn
                    break
            except: pass

        if submit_btn:
            print(f"  → Submit reached — stopping for Ram!")
            result["ready"] = True
            break

        next_clicked = False
        for sel in [
            'button:has-text("Next")',
            'button:has-text("Continue")',
            'button:has-text("Save and Continue")',
            'input[value="Next"]',
            '[data-automation-id*="next"]',
            '[data-icims-id="next"]',
        ]:
            try:
                btn = page.query_selector(sel)
                if btn and btn.is_visible() and btn.is_enabled():
                    btn.click()
                    page.wait_for_timeout(3000)
                    next_clicked = True
                    print(f"  → Clicked Next")
                    break
            except: pass

        if not next_clicked:
            result["ready"] = True
            break

    return result

def get_resume_pdf(jobs: dict) -> str:
    for jid, job in jobs.items():
        pdf = job.get("resume_pdf")
        if pdf and Path(pdf).exists():
            return pdf
    try:
        from ats_resume import generate_ats_resume
        r = generate_ats_resume({
            "title": "Full Stack .NET Developer",
            "company": "Target", "description": ""
        }, "/tmp")
        return r["pdf_path"]
    except Exception as e:
        print(f"  ! PDF error: {e}")
        return None

def run_career_apply():
    from playwright.sync_api import sync_playwright

    jobs       = load_jobs()
    resume_pdf = get_resume_pdf(jobs)
    applied    = 0

    targets = [
        (jid, job) for jid, job in jobs.items()
        if (job.get("fit_score") or 0) >= 80
        and not job.get("career_applied")
        and job.get("status") == "applied"
    ]

    if not targets:
        print("[Career Apply] No new jobs to process")
        return 0

    targets = sorted(targets, key=lambda x: x[1].get("fit_score", 0), reverse=True)[:5]
    print(f"[Career Apply] Processing {len(targets)} jobs...")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox",
                  "--disable-dev-shm-usage",
                  "--disable-blink-features=AutomationControlled"]
        )
        ctx = browser.new_context(
            viewport={"width": 1280, "height": 900},
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
        page.set_default_timeout(25000)

        for jid, job in targets:
            company   = job.get("company", "")
            job_title = job.get("title", "")
            print(f"\n  [{job_title} @ {company}] Score:{job.get('fit_score')}/100")

            # Use Apify to find career page (no CAPTCHA)
            career_url = find_career_page_apify(company, job_title)

            if not career_url:
                print(f"  ! No career page found — skipping")
                jobs[jid]["career_applied"]    = True
                jobs[jid]["career_apply_skip"] = "no_career_page"
                continue

            # Navigate to career page
            try:
                page.goto(career_url, timeout=30000, wait_until="domcontentloaded")
                page.wait_for_timeout(3000)
                print(f"  → Landed on: {page.url[:70]}")
            except Exception as e:
                print(f"  ! Navigation error: {str(e)[:60]}")
                jobs[jid]["career_applied"]    = True
                jobs[jid]["career_apply_skip"] = "navigation_failed"
                continue

            # Fill form
            result = handle_application_form(page, job, resume_pdf)

            if result["filled"] > 0:
                send_review_email(job, result["screenshot"], result["url"], result["filled"])
                log_apply({
                    "title":         job_title,
                    "company":       company,
                    "platform":      detect_platform(page),
                    "fields_filled": result["filled"],
                    "url":           result["url"],
                    "applied_at":    now_iso(),
                    "status":        "pending_review",
                })
                jobs[jid]["career_applied"]    = True
                jobs[jid]["career_applied_at"] = now_iso()
                applied += 1
                print(f"  ✓ {result['filled']} fields filled — review email sent!")
            else:
                print(f"  ! No fields filled — skipping")
                jobs[jid]["career_applied"]    = True
                jobs[jid]["career_apply_skip"] = "no_fields_filled"

            time.sleep(3)

        browser.close()

    DATA_FILE.write_text(json.dumps(jobs, indent=2))
    print(f"\n[Career Apply] Done. {applied} forms filled, emails sent to Ram.")
    return applied

if __name__ == "__main__":
    run_career_apply()
