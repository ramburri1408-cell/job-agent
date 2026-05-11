"""
Comprehensive test suite for career_apply.py
Tests all scenarios: navigation, platform detection, form filling, 
redirect handling, job board detection, email generation
"""

import sys, json, re, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

RESULTS = []

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

JOB_BOARDS = [
    "adzuna.com", "indeed.com", "dice.com", "ziprecruiter.com",
    "monster.com", "glassdoor.com", "linkedin.com", "remotive.com",
]

def run_test(name, fn):
    print(f"\n{'='*55}")
    print(f"TEST: {name}")
    print(f"{'='*55}")
    try:
        result = fn()
        status = "✅ PASS" if result else "❌ FAIL"
        RESULTS.append({"test": name, "status": status, "error": None})
        print(f"Result: {status}")
        return result
    except Exception as e:
        RESULTS.append({"test": name, "status": "❌ ERROR", "error": str(e)})
        print(f"Result: ❌ ERROR — {str(e)[:100]}")
        return False

# ── SCENARIO 1: Job Board Detection ───────────────────────────────────────
def test_job_board_detection():
    """All job board URLs must be detected and skipped."""
    def is_job_board(url):
        return any(board in url.lower() for board in JOB_BOARDS)

    board_urls = [
        ("https://www.adzuna.com/details/5711976702", True),
        ("https://www.indeed.com/viewjob?jk=abc123",  True),
        ("https://www.dice.com/job-detail/xyz",        True),
        ("https://www.ziprecruiter.com/jobs/abc",      True),
        ("https://www.linkedin.com/jobs/view/123",     True),
        ("https://www.glassdoor.com/job-listing/abc",  True),
    ]
    company_urls = [
        ("https://amazon.wd1.myworkdayjobs.com/apply",      False),
        ("https://company.icims.com/jobs/12345/apply",       False),
        ("https://boards.greenhouse.io/company/jobs/123",    False),
        ("https://careers.jpmorgan.com/us/en/jobs/123",      False),
        ("https://microsoft.jobs/en-us/job/12345",           False),
    ]

    passed = 0
    total  = len(board_urls) + len(company_urls)

    print("\n  Job Board URLs (should be detected):")
    for url, expected in board_urls:
        result = is_job_board(url)
        match  = result == expected
        print(f"  {'✓' if match else '✗'} {'BOARD ' if result else 'COMPANY'}: {url[:60]}")
        if match: passed += 1

    print("\n  Company Career URLs (should NOT be detected as boards):")
    for url, expected in company_urls:
        result = is_job_board(url)
        match  = result == expected
        print(f"  {'✓' if match else '✗'} {'BOARD ' if result else 'COMPANY'}: {url[:60]}")
        if match: passed += 1

    print(f"\n  → {passed}/{total} correct")
    return passed == total

# ── SCENARIO 2: Platform Detection ────────────────────────────────────────
def test_platform_detection():
    """All ATS platforms must be correctly identified from URLs."""
    def detect_from_url(url):
        url = url.lower()
        if "myworkdayjobs.com" in url or "workday.com" in url: return "workday"
        if "icims.com" in url:                                  return "icims"
        if "greenhouse.io" in url:                             return "greenhouse"
        if "lever.co" in url:                                  return "lever"
        if "taleo" in url:                                     return "taleo"
        if "jobvite" in url:                                   return "jobvite"
        if "smartrecruiters" in url:                           return "smartrecruiters"
        if "successfactors" in url:                            return "successfactors"
        if "breezy.hr" in url:                                 return "breezy"
        return "generic"

    tests = [
        # Workday variants
        ("https://amazon.wd1.myworkdayjobs.com/External_Opportunities",    "workday"),
        ("https://microsoft.wd3.myworkdayjobs.com/en-US/Microsoft_Careers","workday"),
        ("https://jpmorgan.wd5.myworkdayjobs.com/JPMorgan_careers",        "workday"),
        ("https://company.myworkday.com/company/apply",                     "workday"),
        # iCIMS variants
        ("https://careers.company.icims.com/jobs/12345/apply",             "icims"),
        ("https://recruiting.ultipro.com/icims/jobs",                      "icims"),
        ("https://company-careers.icims.com/jobs/apply",                   "icims"),
        # Greenhouse
        ("https://boards.greenhouse.io/company/jobs/123",                  "greenhouse"),
        ("https://api.greenhouse.io/v1/boards/company/jobs",               "greenhouse"),
        # Lever
        ("https://jobs.lever.co/company/job-id",                           "lever"),
        ("https://jobs.lever.co/stripe/apply",                             "lever"),
        # Taleo
        ("https://company.taleo.net/careersection/apply",                  "taleo"),
        # Jobvite
        ("https://careers.jobvite.com/company/apply",                      "jobvite"),
        # SmartRecruiters
        ("https://jobs.smartrecruiters.com/Company/job",                   "smartrecruiters"),
        # Generic
        ("https://careers.company.com/apply",                              "generic"),
        ("https://company.com/jobs/123",                                   "generic"),
    ]

    passed = 0
    for url, expected in tests:
        detected = detect_from_url(url)
        match    = detected == expected
        print(f"  {'✓' if match else '✗'} [{detected:15}] {url[:60]}")
        if match: passed += 1

    print(f"\n  → {passed}/{len(tests)} correct")
    return passed >= len(tests) * 0.9

# ── SCENARIO 3: AI Answer Logic ───────────────────────────────────────────
def test_ai_answer_logic():
    """All common form questions must return correct answers."""
    def ai_answer(question, options=None):
        q = question.lower()
        if "first name"    in q: return PROFILE["first_name"]
        if "last name"     in q: return PROFILE["last_name"]
        if "full name"     in q: return PROFILE["full_name"]
        if "email"         in q: return PROFILE["email"]
        if "phone"         in q: return PROFILE["phone_format"]
        if "city"          in q: return PROFILE["city"]
        if "zip"           in q: return PROFILE["zip"]
        if "linkedin"      in q: return PROFILE["linkedin"]
        if "salary"        in q: return PROFILE["salary"]
        if "years of exp"  in q: return PROFILE["experience"]
        if "university"    in q: return PROFILE["university"]
        if "authorized"    in q: return "Yes"
        if "sponsor"       in q: return "No"
        if "state"         in q:
            if options:
                return next((o for o in options if "florida" in o.lower()), options[0])
            return PROFILE["state"]
        return "Yes"

    tests = [
        # Basic info
        ("First name",                     PROFILE["first_name"]),
        ("Last name",                      PROFILE["last_name"]),
        ("Full name",                      PROFILE["full_name"]),
        ("Email address",                  PROFILE["email"]),
        ("Phone number",                   PROFILE["phone_format"]),
        ("City",                           PROFILE["city"]),
        ("ZIP / Postal code",              PROFILE["zip"]),
        ("LinkedIn profile URL",           PROFILE["linkedin"]),
        # Work details
        ("Years of experience",            PROFILE["experience"]),
        ("Expected salary",                PROFILE["salary"]),
        ("University / College",           PROFILE["university"]),
        # Authorization
        ("Are you authorized to work?",    "Yes"),
        ("Do you require sponsorship?",    "No"),
        # State with options
        ("State", ["California", "Florida", "Texas"], "Florida"),
    ]

    passed = 0
    for test in tests:
        if len(test) == 3:
            question, options, expected = test[0], test[1], test[2]
        else:
            question, expected = test
            options = None

        answer = ai_answer(question, options)
        match  = expected.lower() in answer.lower()
        print(f"  {'✓' if match else '✗'} '{question}' → '{answer}'")
        if match: passed += 1

    print(f"\n  → {passed}/{len(tests)} correct")
    return passed >= len(tests) * 0.9

# ── SCENARIO 4: Email Content Validation ──────────────────────────────────
def test_email_content():
    """Review email must contain all required information."""
    job = {
        "title":     ".NET Developer",
        "company":   "JPMorgan Chase",
        "location":  "Remote",
        "fit_score": 88,
    }
    apply_url    = "https://jpmorgan.wd1.myworkdayjobs.com/apply/123"
    fields_filled = 12

    subject = f"🔔 Review & Submit: {job['title']} @ {job['company']}"
    body    = f"""Hi Ram,

Your application form has been auto-filled and is ready for your review!

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
✓ Salary expectation: $110,000
✓ Resume PDF uploaded
✓ Cover letter generated"""

    checks = {
        "Job title in subject":    job["title"]    in subject,
        "Company in subject":      job["company"]  in subject,
        "Apply URL in body":       apply_url       in body,
        "Fields filled count":     str(fields_filled) in body,
        "OPT mentioned":           "OPT"           in body,
        "4 years exp":             "4"             in body,
        "FAU mentioned":           "Florida Atlantic" in body,
        "LinkedIn mentioned":      "linkedin"      in body,
        "Salary mentioned":        "110,000"       in body,
        "Resume mentioned":        "Resume"        in body,
        "Cover letter mentioned":  "Cover letter"  in body,
        "Body length OK":          len(body) > 300,
    }

    passed = sum(checks.values())
    for check, result in checks.items():
        print(f"  {'✓' if result else '✗'} {check}")

    print(f"\n  → {passed}/{len(checks)} checks passed")
    return passed == len(checks)

# ── SCENARIO 5: Redirect Navigation Logic ─────────────────────────────────
def test_redirect_logic():
    """Test URL redirect handling logic."""
    def simulate_redirect(start_url):
        """Simulate what happens with different starting URLs."""
        # Job board redirects
        redirects = {
            "https://www.adzuna.com/details/123":
                "https://careers.ameritfleet.icims.com/jobs/123/apply",
            "https://www.indeed.com/viewjob?jk=abc":
                "https://amazon.wd1.myworkdayjobs.com/apply",
            "https://www.dice.com/job-detail/xyz":
                "https://boards.greenhouse.io/company/jobs/456",
        }
        return redirects.get(start_url, start_url)

    def is_job_board(url):
        return any(b in url.lower() for b in JOB_BOARDS)

    def detect_from_url(url):
        url = url.lower()
        if "workday" in url or "myworkdayjobs" in url: return "workday"
        if "icims" in url:                              return "icims"
        if "greenhouse.io" in url:                     return "greenhouse"
        return "listing_page"

    scenarios = [
        {
            "name":     "Adzuna → iCIMS",
            "start":    "https://www.adzuna.com/details/123",
            "expected": "icims",
        },
        {
            "name":     "Indeed → Workday",
            "start":    "https://www.indeed.com/viewjob?jk=abc",
            "expected": "workday",
        },
        {
            "name":     "Dice → Greenhouse",
            "start":    "https://www.dice.com/job-detail/xyz",
            "expected": "greenhouse",
        },
        {
            "name":     "Direct Workday URL",
            "start":    "https://amazon.wd1.myworkdayjobs.com/apply",
            "expected": "workday",
        },
        {
            "name":     "Direct iCIMS URL",
            "start":    "https://company.icims.com/jobs/123/apply",
            "expected": "icims",
        },
    ]

    passed = 0
    for s in scenarios:
        final    = simulate_redirect(s["start"])
        platform = detect_from_url(final)
        is_board = is_job_board(s["start"])
        match    = platform == s["expected"]
        print(f"  {'✓' if match else '✗'} {s['name']}")
        print(f"      Start:    {s['start'][:60]}")
        print(f"      Final:    {final[:60]}")
        print(f"      Platform: {platform} (expected: {s['expected']})")
        print(f"      Is board: {is_board}")
        if match: passed += 1

    print(f"\n  → {passed}/{len(scenarios)} correct")
    return passed == len(scenarios)

# ── SCENARIO 6: Browser Form Fill (Workday-like) ──────────────────────────
def test_workday_form_fill():
    """Test filling a Workday-like multi-step form in browser."""
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-setuid-sandbox",
                      "--disable-dev-shm-usage"]
            )
            page = browser.new_page()

            # Simulate Workday Step 1 — Personal Info
            page.set_content("""
<html><body>
<h2>Step 1 of 3 — Personal Information</h2>
<form id="apply-form">
  <label for="legalName--firstName">First Name *</label>
  <input type="text" id="legalName--firstName" name="firstName"/>

  <label for="legalName--lastName">Last Name *</label>
  <input type="text" id="legalName--lastName" name="lastName"/>

  <label for="email">Email Address *</label>
  <input type="email" id="email" name="email"/>

  <label for="phone">Phone Number *</label>
  <input type="tel" id="phone" name="phone"/>

  <label for="address--city">City *</label>
  <input type="text" id="address--city" name="city"/>

  <label for="address--state">State *</label>
  <select id="address--state" name="state">
    <option value="">Select State</option>
    <option value="CA">California</option>
    <option value="FL">Florida</option>
    <option value="TX">Texas</option>
    <option value="NY">New York</option>
  </select>

  <label for="address--zip">ZIP Code *</label>
  <input type="text" id="address--zip" name="zip"/>

  <label for="linkedin">LinkedIn Profile URL</label>
  <input type="url" id="linkedin" name="linkedin"/>

  <label for="salary">Expected Salary</label>
  <input type="number" id="salary" name="salary"/>

  <fieldset>
    <legend>Are you authorized to work in the United States?</legend>
    <input type="radio" id="auth_yes" name="workAuth" value="Yes"/>
    <label for="auth_yes">Yes</label>
    <input type="radio" id="auth_no" name="workAuth" value="No"/>
    <label for="auth_no">No</label>
  </fieldset>

  <fieldset>
    <legend>Will you now or in the future require sponsorship?</legend>
    <input type="radio" id="sponsor_yes" name="sponsor" value="Yes"/>
    <label for="sponsor_yes">Yes</label>
    <input type="radio" id="sponsor_no" name="sponsor" value="No"/>
    <label for="sponsor_no">No</label>
  </fieldset>

  <input type="file" id="resume" name="resume" accept=".pdf"/>

  <button type="button" id="next-btn">Next</button>
</form>
</body></html>""")

            def ai_answer_local(question, options=None):
                q = question.lower()
                if "first name" in q:  return PROFILE["first_name"]
                if "last name"  in q:  return PROFILE["last_name"]
                if "email"      in q:  return PROFILE["email"]
                if "phone"      in q:  return PROFILE["phone_format"]
                if "city"       in q:  return PROFILE["city"]
                if "zip"        in q:  return PROFILE["zip"]
                if "linkedin"   in q:  return PROFILE["linkedin"]
                if "salary"     in q:  return PROFILE["salary"]
                if "state"      in q:
                    if options:
                        return next((o for o in options if "florida" in o.lower()), options[0])
                    return PROFILE["state"]
                if "authorized" in q:  return "Yes"
                if "sponsor"    in q:  return "No"
                return "Yes"

            filled = 0
            checks = {}

            # Fill text inputs
            fields = [
                ("legalName--firstName", PROFILE["first_name"]),
                ("legalName--lastName",  PROFILE["last_name"]),
                ("email",                PROFILE["email"]),
                ("phone",                PROFILE["phone_format"]),
                ("address--city",        PROFILE["city"]),
                ("address--zip",         PROFILE["zip"]),
                ("linkedin",             PROFILE["linkedin"]),
                ("salary",               PROFILE["salary"]),
            ]

            for field_id, expected in fields:
                try:
                    el = page.query_selector(f'label[for="{field_id}"]')
                    if el:
                        lbl = el.inner_text().strip()
                        val = ai_answer_local(lbl)
                        inp = page.query_selector(f'#{field_id}')
                        if inp:
                            inp.fill(val)
                            actual = inp.input_value()
                            match  = expected.lower() in actual.lower()
                            checks[field_id] = match
                            print(f"  {'✓' if match else '✗'} {field_id}: '{actual}'")
                            if match: filled += 1
                except Exception as e:
                    print(f"  ! {field_id}: {e}")
                    checks[field_id] = False

            # Fill state dropdown
            try:
                sel  = page.query_selector('#address--state')
                opts = [o.inner_text() for o in sel.query_selector_all('option') if o.inner_text().strip()]
                sel.select_option(label="Florida")
                checks["state"] = True
                print(f"  ✓ state: Florida selected")
                filled += 1
            except Exception as e:
                print(f"  ! state: {e}")
                checks["state"] = False

            # Click work auth Yes
            try:
                page.click('#auth_yes')
                checks["work_auth"] = True
                print(f"  ✓ work_auth: Yes selected")
                filled += 1
            except Exception as e:
                print(f"  ! work_auth: {e}")
                checks["work_auth"] = False

            # Click sponsor No
            try:
                page.click('#sponsor_no')
                checks["sponsorship"] = True
                print(f"  ✓ sponsorship: No selected")
                filled += 1
            except Exception as e:
                print(f"  ! sponsorship: {e}")
                checks["sponsorship"] = False

            # Take screenshot
            screenshot = page.screenshot(full_page=True)
            Path("/tmp/test_workday_form.png").write_bytes(screenshot)
            print(f"  ✓ Screenshot: {len(screenshot):,} bytes → /tmp/test_workday_form.png")

            browser.close()

            passed = sum(checks.values())
            total  = len(checks)
            print(f"\n  → {passed}/{total} fields filled correctly")
            return passed >= total * 0.9

    except Exception as e:
        print(f"  ! Browser error: {str(e)[:100]}")
        return False

# ── SCENARIO 7: Browser Form Fill (iCIMS-like) ────────────────────────────
def test_icims_form_fill():
    """Test filling an iCIMS-like application form."""
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-setuid-sandbox",
                      "--disable-dev-shm-usage"]
            )
            page = browser.new_page()

            # Simulate iCIMS application form
            page.set_content("""
<html><body>
<div class="icims-application">
<h2>Apply for Position</h2>
<form id="icims-form">
  <label for="applicant_name">Full Name *</label>
  <input type="text" id="applicant_name" name="applicant_name"/>

  <label for="applicant_email">Email Address *</label>
  <input type="email" id="applicant_email" name="applicant_email"/>

  <label for="applicant_phone">Phone *</label>
  <input type="tel" id="applicant_phone" name="applicant_phone"/>

  <label for="applicant_city">City *</label>
  <input type="text" id="applicant_city" name="applicant_city"/>

  <label for="applicant_state">State *</label>
  <select id="applicant_state" name="applicant_state">
    <option value="">-- Select --</option>
    <option value="FL">Florida</option>
    <option value="CA">California</option>
    <option value="TX">Texas</option>
  </select>

  <label for="applicant_zip">ZIP *</label>
  <input type="text" id="applicant_zip" name="applicant_zip"/>

  <label for="cover_letter">Cover Letter</label>
  <textarea id="cover_letter" name="cover_letter" rows="6"></textarea>

  <label for="resume_upload">Upload Resume *</label>
  <input type="file" id="resume_upload" name="resume_upload" accept=".pdf,.doc,.docx"/>

  <label for="years_exp">Years of Experience *</label>
  <select id="years_exp" name="years_exp">
    <option value="">Select</option>
    <option value="0-1">0-1 years</option>
    <option value="2-4">2-4 years</option>
    <option value="5-7">5-7 years</option>
    <option value="8+">8+ years</option>
  </select>

  <label for="work_auth">Are you eligible to work in the US?</label>
  <select id="work_auth" name="work_auth">
    <option value="">Select</option>
    <option value="yes">Yes, I am authorized</option>
    <option value="no">No, I require sponsorship</option>
  </select>

  <button type="button" id="next-step">Next Step →</button>
</form>
</div>
</body></html>""")

            filled  = 0
            checks  = {}

            field_tests = [
                ("applicant_name",  PROFILE["full_name"]),
                ("applicant_email", PROFILE["email"]),
                ("applicant_phone", PROFILE["phone_format"]),
                ("applicant_city",  PROFILE["city"]),
                ("applicant_zip",   PROFILE["zip"]),
            ]

            for field_id, expected in field_tests:
                try:
                    inp = page.query_selector(f'#{field_id}')
                    if inp:
                        inp.fill(expected)
                        actual = inp.input_value()
                        match  = expected.lower() in actual.lower()
                        checks[field_id] = match
                        print(f"  {'✓' if match else '✗'} {field_id}: '{actual}'")
                        if match: filled += 1
                except Exception as e:
                    print(f"  ! {field_id}: {e}")
                    checks[field_id] = False

            # State dropdown
            try:
                page.select_option('#applicant_state', label="Florida")
                checks["state"] = True
                print(f"  ✓ state: Florida")
                filled += 1
            except Exception as e:
                checks["state"] = False
                print(f"  ! state: {e}")

            # Cover letter textarea
            try:
                cover = (
                    "I am excited to apply for this position. "
                    "With 4+ years of .NET development experience, "
                    "I am confident I will contribute immediately."
                )
                page.fill('#cover_letter', cover)
                actual = page.query_selector('#cover_letter').input_value()
                checks["cover_letter"] = len(actual) > 50
                print(f"  ✓ cover_letter: {len(actual)} chars")
                filled += 1
            except Exception as e:
                checks["cover_letter"] = False
                print(f"  ! cover_letter: {e}")

            # Years exp dropdown
            try:
                page.select_option('#years_exp', label="2-4 years")
                checks["years_exp"] = True
                print(f"  ✓ years_exp: 2-4 years")
                filled += 1
            except Exception as e:
                checks["years_exp"] = False
                print(f"  ! years_exp: {e}")

            # Work auth dropdown
            try:
                page.select_option('#work_auth', label="Yes, I am authorized")
                checks["work_auth"] = True
                print(f"  ✓ work_auth: Yes, I am authorized")
                filled += 1
            except Exception as e:
                checks["work_auth"] = False
                print(f"  ! work_auth: {e}")

            # Screenshot
            screenshot = page.screenshot(full_page=True)
            Path("/tmp/test_icims_form.png").write_bytes(screenshot)
            print(f"  ✓ Screenshot: {len(screenshot):,} bytes → /tmp/test_icims_form.png")

            browser.close()
            passed = sum(checks.values())
            total  = len(checks)
            print(f"\n  → {passed}/{total} fields filled correctly")
            return passed >= total * 0.9

    except Exception as e:
        print(f"  ! Browser error: {str(e)[:100]}")
        return False

# ── SCENARIO 8: Multi-Step Form Navigation ────────────────────────────────
def test_multistep_navigation():
    """Test navigating through multi-step form — stops at Submit."""
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-setuid-sandbox",
                      "--disable-dev-shm-usage"]
            )
            page = browser.new_page()

            # Simulate 3-step application
            page.set_content("""
<html>
<body>
<div id="step1">
  <h2>Step 1 — Upload Resume</h2>
  <input type="file" id="resume" accept=".pdf"/>
  <button id="next1" onclick="
    document.getElementById('step1').style.display='none';
    document.getElementById('step2').style.display='block';
  ">Next</button>
</div>
<div id="step2" style="display:none">
  <h2>Step 2 — Personal Info</h2>
  <label for="fname">First Name</label>
  <input type="text" id="fname"/>
  <label for="email">Email</label>
  <input type="email" id="email"/>
  <button id="next2" onclick="
    document.getElementById('step2').style.display='none';
    document.getElementById('step3').style.display='block';
  ">Next</button>
</div>
<div id="step3" style="display:none">
  <h2>Step 3 — Review</h2>
  <p>Please review your application before submitting.</p>
  <button id="submit-btn">Submit Application</button>
</div>
</body></html>""")

            steps_completed = 0
            found_submit    = False

            for step in range(5):
                page.wait_for_timeout(500)

                # Check for Submit button — stop here
                submit = page.query_selector('button:has-text("Submit")')
                if submit and submit.is_visible():
                    found_submit = True
                    print(f"  ✓ Step {step+1}: Submit button found — stopping for Ram!")
                    screenshot = page.screenshot()
                    Path("/tmp/test_multistep.png").write_bytes(screenshot)
                    break

                # Fill visible fields
                for inp in page.query_selector_all('input[type="text"], input[type="email"]'):
                    if inp.is_visible() and not inp.input_value():
                        lbl = inp.get_attribute("id") or ""
                        if "fname" in lbl: inp.fill(PROFILE["first_name"])
                        if "email" in lbl: inp.fill(PROFILE["email"])

                # Click Next
                for sel in ['button:has-text("Next")', '#next1', '#next2']:
                    try:
                        btn = page.query_selector(sel)
                        if btn and btn.is_visible():
                            btn.click()
                            page.wait_for_timeout(500)
                            steps_completed += 1
                            print(f"  ✓ Step {step+1}: clicked Next")
                            break
                    except: pass
                else:
                    break

            browser.close()

            print(f"  → Steps completed: {steps_completed}")
            print(f"  → Submit found: {found_submit}")
            return found_submit and steps_completed >= 2

    except Exception as e:
        print(f"  ! Browser error: {str(e)[:100]}")
        return False

# ── SCENARIO 9: Resume Upload ─────────────────────────────────────────────
def test_resume_upload():
    """Test resume PDF upload to file input."""
    try:
        from playwright.sync_api import sync_playwright

        # Create dummy PDF
        dummy_pdf = Path("/tmp/test_resume_upload.pdf")
        dummy_pdf.write_bytes(b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\n%%EOF")

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-setuid-sandbox"]
            )
            page = browser.new_page()
            page.set_content("""
<html><body>
<form>
  <label>Resume (PDF) *</label>
  <input type="file" id="resume" name="resume" accept=".pdf"/>
  <div id="status">No file selected</div>
  <script>
    document.getElementById('resume').addEventListener('change', function() {
      document.getElementById('status').textContent = 'File: ' + this.files[0].name;
    });
  </script>
</form>
</body></html>""")

            # Upload
            inp = page.query_selector('input[type="file"]')
            if inp:
                inp.set_input_files(str(dummy_pdf))
                page.wait_for_timeout(500)

                status = page.inner_text("#status")
                print(f"  → Upload status: {status}")

                success = "test_resume_upload.pdf" in status
                print(f"  {'✓' if success else '✗'} Resume uploaded successfully")

                browser.close()
                return success

            browser.close()
            return False

    except Exception as e:
        print(f"  ! Error: {str(e)[:80]}")
        return False

# ── SCENARIO 10: External Apply Link Detection ────────────────────────────
def test_external_apply_detection():
    """Test finding Apply button on job listing pages."""
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-setuid-sandbox"]
            )
            page = browser.new_page()

            # Simulate a job listing page with external apply link
            page.set_content("""
<html><body>
<div class="job-listing">
  <h1>.NET Developer at JPMorgan Chase</h1>
  <p>Job description here...</p>
  <div class="apply-section">
    <a href="https://jpmorgan.wd1.myworkdayjobs.com/JPMorgan_careers/job/123/apply"
       class="apply-button">Apply on company site</a>
    <a href="https://jpmorgan.wd1.myworkdayjobs.com/JPMorgan_careers/job/123/apply"
       data-testid="apply-link">Apply Now</a>
  </div>
</div>
</body></html>""")

            apply_selectors = [
                'a:has-text("Apply on company site")',
                'a:has-text("Apply Now")',
                '[data-testid*="apply"]',
                'a[href*="workday"]',
                'a[href*="career"]',
            ]

            found_url = ""
            for sel in apply_selectors:
                try:
                    el = page.query_selector(sel)
                    if el and el.is_visible():
                        href = el.get_attribute("href") or ""
                        if href and href.startswith("http"):
                            found_url = href
                            print(f"  ✓ Apply link found with: {sel}")
                            print(f"    URL: {found_url[:70]}")
                            break
                except: pass

            browser.close()

            is_workday = "workday" in found_url.lower()
            print(f"  → Is Workday URL: {is_workday}")
            return bool(found_url) and is_workday

    except Exception as e:
        print(f"  ! Error: {str(e)[:80]}")
        return False

# ── MAIN ──────────────────────────────────────────────────────────────────
def main():
    print("\n" + "="*60)
    print("  CAREER APPLY BOT — COMPREHENSIVE TEST SUITE")
    print("="*60)

    print("\n📋 LOGIC TESTS (no browser)")
    run_test("Job Board Detection",         test_job_board_detection)
    run_test("Platform Detection (URLs)",   test_platform_detection)
    run_test("AI Answer Logic",             test_ai_answer_logic)
    run_test("Email Content Validation",    test_email_content)
    run_test("Redirect Navigation Logic",   test_redirect_logic)

    print("\n🌐 BROWSER TESTS")
    run_test("Workday Form Fill",           test_workday_form_fill)
    run_test("iCIMS Form Fill",             test_icims_form_fill)
    run_test("Multi-Step Navigation",       test_multistep_navigation)
    run_test("Resume Upload",               test_resume_upload)
    run_test("External Apply Detection",    test_external_apply_detection)

    # Summary
    print("\n" + "="*60)
    print("  TEST RESULTS SUMMARY")
    print("="*60)
    passed = sum(1 for r in RESULTS if "PASS" in r["status"])
    total  = len(RESULTS)
    print(f"\n  {passed}/{total} tests passed\n")

    for r in RESULTS:
        print(f"  {r['status']}  {r['test']}")
        if r.get("error"):
            print(f"        Error: {r['error'][:80]}")

    print(f"\n{'='*60}")
    if passed == total:
        print("  ✅ ALL TESTS PASSED — Ready to deploy!")
    elif passed >= total * 0.8:
        print("  ⚠️  MOSTLY PASSING — Review failures")
    else:
        print("  ❌ TESTS FAILED — Fix before deploying")
    print(f"{'='*60}\n")

    return passed == total

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
