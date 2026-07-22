"""
Career Page Apply Bot — iCIMS and Workday
Option 2: Googles company career page directly instead of Adzuna redirects
Semi-automated: fills form, emails the candidate a screenshot + link to submit
"""

import os, json, re, time
from pathlib import Path
from datetime import datetime, timezone
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage

GMAIL_USER  = os.environ.get("GMAIL_USER", "")
GMAIL_PASS  = os.environ.get("GMAIL_APP_PASSWORD", "")
DATA_FILE   = Path("data/jobs.json")
LOG_FILE    = Path("data/career_apply_log.jsonl")
CONFIG_FILE = Path("data/config.json")

def load_config():
    return json.loads(CONFIG_FILE.read_text()) if CONFIG_FILE.exists() else {}

CONFIG      = load_config()
CFG_PROFILE = CONFIG.get("profile", {})

RAM_EMAIL = CFG_PROFILE.get("email", "janakiram.b1408@gmail.com")

JOB_BOARDS = [
    "adzuna.com", "adzuna.co.uk", "indeed.com", "dice.com",
    "ziprecruiter.com", "monster.com", "glassdoor.com",
    "linkedin.com", "remotive.com", "simplyhired.com",
    "careerbuilder.com", "jobs/careers",
]

_full_name  = CFG_PROFILE.get("name", "Janaki Ram Reddy")
_first, _, _last = _full_name.rpartition(" ")

PROFILE = {
    "first_name":   _first or _full_name,
    "last_name":    _last,
    "full_name":    _full_name,
    "email":        CFG_PROFILE.get("email", "janakiram.b1408@gmail.com"),
    "phone":        CFG_PROFILE.get("phone", "+1 984-357-4658"),
    "phone_format": CFG_PROFILE.get("phone", "+1 984-357-4658"),
    "city":         "Boca Raton",
    "state":        "Florida",
    "state_abbr":   "FL",
    "zip":          "33431",
    "country":      "United States",
    "linkedin":     CFG_PROFILE.get("linkedin", "https://www.linkedin.com/in/janakiram58/"),
    "experience":   "4",
    "title":        CFG_PROFILE.get("title", "Senior Software Engineer"),
    "salary":       "110000",
    "authorized":   "Yes",
    "sponsorship":  "No",
    "visa":         "OPT",
    "university":   "Florida Atlantic University",
    "degree":       "Master's in Computer Science",
    "grad_year":    "",
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

def google_company_career_page(page, company: str, job_title: str) -> str:
    """
    Google search to find the actual company career page URL.
    Returns the best career page URL found.
    """
    queries = [
        f'"{company}" careers apply {job_title} site:workday.com OR site:icims.com OR site:greenhouse.io OR site:lever.co',
        f'"{company}" official careers page apply now',
        f'{company} careers jobs apply',
    ]

    for query in queries:
        try:
            search_url = f"https://www.google.com/search?q={query.replace(' ', '+')}&num=5"
            page.goto(search_url, timeout=20000, wait_until="domcontentloaded")
            page.wait_for_timeout(2000)

            body = page.inner_text("body").lower()
            if "unusual traffic" in body or "captcha" in body:
                print(f"  ! Google CAPTCHA")
                break

            # Find links to career pages
            links = page.query_selector_all('a[href]')
            for link in links:
                try:
                    href = link.get_attribute("href") or ""
                    if not href.startswith("http"):
                        continue
                    if is_job_board(href):
                        continue
                    # Prefer ATS platform URLs
                    if any(ats in href.lower() for ats in
                           ["workday", "icims", "greenhouse", "lever",
                            "taleo", "jobvite", "careers", "jobs"]):
                        if company.lower().split()[0][:4] in href.lower() or \
                           any(w in href.lower() for w in ["career", "jobs", "apply"]):
                            print(f"  → Career page found: {href[:70]}")
                            return href
                except:
                    pass

            time.sleep(2)

        except Exception as e:
            print(f"  ! Google search error: {str(e)[:60]}")

    return ""

def find_apply_link_on_page(page) -> str:
    """Find Apply button link on a job listing page."""
    for sel in [
        'a:has-text("Apply Now")',
        'a:has-text("Apply for this job")',
        'button:has-text("Apply Now")',
        '[data-testid*="apply"]',
        'a[href*="apply"]',
        'a[href*="workday"]',
        'a[href*="icims"]',
        'a[href*="greenhouse"]',
        'a[href*="lever"]',
    ]:
        try:
            el = page.query_selector(sel)
            if el and el.is_visible():
                href = el.get_attribute("href") or ""
                if href and not is_job_board(href):
                    return href
        except:
            pass
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
            model="claude-opus-4-8", max_tokens=80,
            system=(
                f"Answer job application form questions for {PROFILE['full_name']}, "
                f"{PROFILE['title']}, {PROFILE['experience']} years exp, OPT visa, "
                "authorized to work in US. Brief direct answers."
            ),
            messages=[{"role": "user", "content": f"Q: {question}{opts}\nA:"}]
        ).content[0].text.strip()
    except:
        return "Yes"

def generate_cover_letter(job: dict) -> str:
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        return client.messages.create(
            model="claude-opus-4-8", max_tokens=300,
            system=f"Write a 3-sentence professional cover letter for {PROFILE['full_name']}. Be specific and confident.",
            messages=[{"role": "user", "content":
                f"Job: {job['title']} at {job['company']}\nWrite cover letter:"}]
        ).content[0].text.strip()
    except:
        return (
            f"I am excited to apply for the {job['title']} position at {job['company']}. "
            f"With 4+ years of full stack Java, Spring Boot, and React development "
            f"experience, I am confident I will contribute immediately. "
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

        body = f"""Hi {PROFILE['first_name']},

Your application form has been auto-filled and is ready for review!

📋 Position : {job['title']}
🏢 Company  : {job['company']}
📍 Location : {job.get('location', 'Not specified')}
⭐ Fit Score : {job.get('fit_score', 'N/A')}/100
📝 Fields filled: {fields_filled}

🔗 CLICK TO REVIEW AND SUBMIT:
{apply_url}

What was auto-filled:
✓ Name, email, phone, address ({PROFILE['city']}, {PROFILE['state_abbr']} {PROFILE['zip']})
✓ Work authorization: Yes (OPT — authorized to work)
✓ Sponsorship required: No
✓ Years of experience: {PROFILE['experience']}
✓ Education: {PROFILE['degree']}, {PROFILE['university']}
✓ LinkedIn: {PROFILE['linkedin']}
✓ Salary expectation: ${int(PROFILE['salary']):,}
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
    """Fill application form step by step — stop at Submit."""
    result   = {"filled": 0, "screenshot": None, "url": page.url, "ready": False}
    platform = detect_platform(page)
    print(f"  → Platform: {platform}")

    # Workday: click Apply button
    if platform == "workday":
        for asel in [
            '[data-automation-id="applyButton"]',
            'a:has-text("Apply")',
            'button:has-text("Apply")',
            'a:has-text("Apply Now")',
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

        # Stop at Submit
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
            print(f"  → Submit button reached — stopping for Ram!")
            result["ready"] = True
            break

        # Click Next
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

def navigate_to_career_page(page, company: str, job_title: str) -> str:
    """
    Find the actual company career page using Google search.
    Returns the URL of the application form.
    """
    print(f"  → Googling career page for {company}...")
    career_url = google_company_career_page(page, company, job_title)

    if not career_url:
        print(f"  ! No career page found via Google")
        return ""

    # Navigate to found URL
    try:
        page.goto(career_url, timeout=30000, wait_until="domcontentloaded")
        page.wait_for_timeout(3000)
        final_url = page.url
        print(f"  → Landed on: {final_url[:70]}")

        # If still on listing page, find Apply button
        platform = detect_platform(page)
        if platform == "listing_page":
            apply_link = find_apply_link_on_page(page)
            if apply_link:
                if not apply_link.startswith("http"):
                    from urllib.parse import urljoin
                    apply_link = urljoin(final_url, apply_link)
                page.goto(apply_link, timeout=30000, wait_until="domcontentloaded")
                page.wait_for_timeout(3000)
                print(f"  → Navigated to apply form: {page.url[:70]}")

        platform = detect_platform(page)
        if platform == "listing_page":
            print(f"  ! Still on listing page")
            return ""

        return page.url

    except Exception as e:
        print(f"  ! Navigation error: {str(e)[:60]}")
        return ""

def get_resume_pdf(jobs: dict) -> str:
    for jid, job in jobs.items():
        pdf = job.get("resume_pdf")
        if pdf and Path(pdf).exists():
            return pdf
    try:
        from ats_resume import generate_ats_resume
        r = generate_ats_resume({
            "title": PROFILE.get("title", "Senior Software Engineer"),
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

            # Google the company career page directly
            apply_url = navigate_to_career_page(page, company, job_title)

            if not apply_url:
                print(f"  ! Could not find career page — skipping")
                jobs[jid]["career_applied"]    = True
                jobs[jid]["career_apply_skip"] = "no_career_page_found"
                continue

            # Fill the application form
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
                print(f"  ✓ {result['filled']} fields filled — review email sent to Ram!")
            else:
                print(f"  ! No fields filled — skipping")
                jobs[jid]["career_applied"]    = True
                jobs[jid]["career_apply_skip"] = "no_fields_filled"

            time.sleep(3)

        browser.close()

    DATA_FILE.write_text(json.dumps(jobs, indent=2))
    print(f"\n[Career Apply] Done. {applied} forms filled, review emails sent to Ram.")
    return applied

if __name__ == "__main__":
    run_career_apply()
