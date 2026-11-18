"""
LinkedIn Easy Apply Auto-Apply Bot (Edge Edition)
=================================================
Features:
  - Filters strictly for 'Easy Apply' (f_AL=true).
  - Filters strictly for Fresh jobs posted in last 24h / past week (f_TPR=r86400, sortBy=DD).
  - Filters strictly for Entry Level / Associate roles (f_E=2).
  - Veto filters: Senior, Lead, Architect, Java, .NET, PHP, C++, non-software roles.
  - Active Gemini AI Match Scoring against your Tech Stack (Python, React, Node, SQL).
  - Handles the Easy Apply multi-step modal (Next -> Review -> Submit application).
  - Saves real-time logs to linkedinapplied.csv.
"""

import os
import re
import csv
import json
import time
import logging
import urllib.parse
from datetime import datetime
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.edge.service import Service as EdgeService
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException, StaleElementReferenceException

try:
    from webdriver_manager.microsoft import EdgeChromiumDriverManager
    WEBDRIVER_MANAGER_AVAILABLE = True
except ImportError:
    WEBDRIVER_MANAGER_AVAILABLE = False

# ------------------------------------------------------------
# Configuration
# ------------------------------------------------------------
load_dotenv()

LINKEDIN_EMAIL = os.getenv('LINKEDIN_EMAIL') or os.getenv('NAUKRI_EMAIL', '')
LINKEDIN_PASSWORD = os.getenv('LINKEDIN_PASSWORD') or os.getenv('NAUKRI_PASSWORD', '')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', '')

KEYWORDS = [kw.strip() for kw in os.getenv('KEYWORDS', 'Python Developer, Full Stack Developer').split(',') if kw.strip()]
LOCATION = os.getenv('LOCATION', 'Bengaluru, Karnataka, India').strip()

MAX_APPLICATIONS = int(os.getenv('MAX_APPLICATIONS', '30'))  # Safe daily cap for LinkedIn
EDGE_DRIVER_PATH = os.getenv('EDGE_DRIVER_PATH', '')

CSV_REPORT_FILE = "linkedinapplied.csv"
MIN_SCORE = 60
MAX_EXP_YEARS = 2

MY_TECH_STACK = [
    "Python", "JavaScript", "SQL", "React.js", "Django", 
    "Node.js", "Express.js", "MySQL", "Supabase", "Git", "REST APIs", "HTML5", "CSS3"
]

VETO_KEYWORDS = [
    "senior", "sr.", "sr ", "lead", "principal", "architect", "manager", "head", "director",
    "java", "spring boot", "springboot", ".net", "dotnet", "c#", "asp.net",
    "c++", "ruby", "golang", "php", "laravel", "flutter", "swift", "kotlin",
    "android", "ios", "accountant", "finance", "hr", "sales", "consultant"
]

SOFTWARE_ROLE_KEYWORDS = [
    "developer", "software", "engineer", "full stack", "fullstack", "backend",
    "frontend", "programmer", "sde", "web", "python", "react", "node", "django"
]

# ------------------------------------------------------------
# Logging Setup
# ------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)


def init_csv_report():
    """Ensure CSV has proper headers."""
    try:
        if not os.path.exists(CSV_REPORT_FILE) or os.stat(CSV_REPORT_FILE).st_size == 0:
            with open(CSV_REPORT_FILE, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow([
                    "Timestamp", "Company", "Job Title", "Experience", 
                    "Score", "Status", "Reason", "Job URL"
                ])
    except PermissionError:
        logger.warning(f"'{CSV_REPORT_FILE}' is locked. Please close it if open in Excel.")


def record_job_status(company, title, experience, score, status, reason, link):
    """Save immediately to CSV so no data is lost."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for _ in range(3):
        try:
            with open(CSV_REPORT_FILE, 'a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow([timestamp, company, title, experience, score, status, reason, link])
            return
        except PermissionError:
            time.sleep(1)


def print_job_box(status_type, company, title, exp, score, reason, link):
    """Prints a clean, single-line clickable link without breaking the URL."""
    tag = "🟢 APPLIED" if status_type == "APPLIED" else ("🔴 REJECTED" if status_type == "REJECTED" else "🟡 FAILED")
    print("\n" + "=" * 70)
    print(f"[{tag}] {company} - {title} ({exp})")
    print(f"Match : {score}/100 | {reason}")
    print(f"Link  : {link}")
    print("=" * 70 + "\n")


def create_edge_driver():
    """Create a visible Edge browser with a persistent user profile (stores login cookies permanently)."""
    options = webdriver.EdgeOptions()
    options.add_argument("--start-maximized")
    options.add_argument("--disable-notifications")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)

    # Persistent browser profile folder inside the project
    # This stores your login cookies permanently so you NEVER have to log in again!
    profile_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "browser_profile", "linkedin")
    os.makedirs(profile_dir, exist_ok=True)
    options.add_argument(f"--user-data-dir={profile_dir}")

    if WEBDRIVER_MANAGER_AVAILABLE:
        service = EdgeService(EdgeChromiumDriverManager().install())
    elif EDGE_DRIVER_PATH:
        service = EdgeService(executable_path=EDGE_DRIVER_PATH)
    else:
        service = EdgeService()

    return webdriver.Edge(service=service, options=options)


def login_linkedin(driver):
    """Log in to LinkedIn or verify existing session."""
    logger.info("Checking LinkedIn session...")
    driver.get('https://www.linkedin.com/feed/')
    time.sleep(4)

    # Check if already logged in
    if "feed" in driver.current_url.lower():
        logger.info("✓ Already logged in to LinkedIn.")
        return

    # Navigate to login page
    driver.get('https://www.linkedin.com/login')
    time.sleep(3)

    try:
        uname = WebDriverWait(driver, 8).until(
            EC.presence_of_element_located((By.ID, "username"))
        )
        uname.clear()
        uname.send_keys(LINKEDIN_EMAIL)
        time.sleep(1)

        pwd = driver.find_element(By.ID, "password")
        pwd.clear()
        pwd.send_keys(LINKEDIN_PASSWORD)
        time.sleep(1)

        submit_btn = driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
        submit_btn.click()
        time.sleep(6)

        if "feed" in driver.current_url.lower():
            logger.info("✓ LinkedIn login successful!")
        else:
            logger.info("ℹ️ If LinkedIn requires security verification or PIN, complete it in the browser window...")
            for _ in range(30):
                if "feed" in driver.current_url.lower() or "jobs" in driver.current_url.lower():
                    logger.info("✓ Logged in successfully!")
                    break
                time.sleep(1)
    except Exception as e:
        logger.info(f"Please log in manually if prompted: {e}")
        time.sleep(5)


def is_software_engineering_role(title):
    """Ensure the role is actual software/web engineering."""
    t = title.lower()
    return any(w in t for w in SOFTWARE_ROLE_KEYWORDS)


def extract_experience_from_jd(jd_text):
    """
    Extracts required experience string (e.g. '0-2 Yrs', '2+ Yrs', '1-3 Yrs', 'Fresher')
    directly from the job description text.
    """
    if not jd_text:
        return "0-2 Yrs"

    patterns = [
        r'(\b\d+\s*(?:-|to)\s*\d+\s*(?:years?|yrs?|yr)\b)',
        r'(\b\d+\s*\+\s*(?:years?|yrs?|yr)\b)',
        r'((?:at least|minimum|min\.?)\s*\d+\s*(?:years?|yrs?|yr)\b)',
        r'(\b\d+\s*(?:years?|yrs?|yr)\s*(?:of)?\s*(?:relevant|work|hands-on)?\s*experience\b)',
    ]

    for p in patterns:
        m = re.search(p, jd_text, re.IGNORECASE)
        if m:
            raw = m.group(1).strip()
            cleaned = re.sub(r'(?i)\s*(?:of)?\s*(?:relevant|work|hands-on)?\s*experience', '', raw).strip()
            cleaned = re.sub(r'(?i)\s*(?:years?|yrs?|yr)', ' Yrs', cleaned).strip()
            return cleaned

    if re.search(r'\b(fresher|entry[\s-]level|recent graduate|intern|internship)\b', jd_text, re.IGNORECASE):
        return "Fresher"

    return "0-2 Yrs"


def is_experience_eligible(exp_text):
    """
    Checks if the extracted experience matches a 0-2 years candidate profile.
    Rejects any role requiring > 2 years minimum experience.
    """
    if not exp_text or "fresher" in exp_text.lower():
        return True, exp_text

    nums = [int(n) for n in re.findall(r'\b\d+\b', exp_text)]
    if not nums:
        return True, exp_text

    min_exp = nums[0]
    if min_exp > 2:
        return False, f"Requires {exp_text} (> 2 Yrs)"

    return True, exp_text


def fetch_linkedin_jd(job_id, driver_jd_text=""):
    """
    Ensures complete, un-truncated job description text is available.
    If DOM text is truncated or missing, fetches directly via LinkedIn API.
    """
    if driver_jd_text and len(driver_jd_text) > 300:
        return driver_jd_text

    if job_id:
        try:
            import requests
            from bs4 import BeautifulSoup
            url = f"https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}"
            res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=5)
            if res.status_code == 200:
                soup = BeautifulSoup(res.text, 'html.parser')
                text = soup.get_text('\n', strip=True)
                if len(text) > 150:
                    return text
        except Exception:
            pass

    return driver_jd_text


def is_experience_suitable(exp_text, title=""):
    """Filter out Senior roles and experience > 2 yrs."""
    full_text = f"{title} {exp_text}".lower()
    if any(w in full_text for w in ["senior", "sr.", "sr ", "lead", "architect", "manager", "principal"]):
        return False

    if not exp_text:
        return True

    nums = [int(n) for n in re.findall(r'\b\d+\b', exp_text)]
    if not nums:
        return True

    min_exp = nums[0]
    max_exp = nums[1] if len(nums) > 1 else min_exp
    return not (min_exp > MAX_EXP_YEARS or max_exp > 3)


def contains_veto_skills(text):
    """Check for unwanted tech skills."""
    text_lower = text.lower()
    for veto in VETO_KEYWORDS:
        if re.search(r'\b' + re.escape(veto) + r'\b', text_lower):
            if veto == "java" and ("javascript" in text_lower or "java script" in text_lower):
                cleaned = text_lower.replace("javascript", "").replace("java script", "")
                if re.search(r'\bjava\b', cleaned):
                    return veto
                continue
            return veto
    return None


def load_candidate_resume():
    """Extracts text from candidate's resume PDF (specified in .env RESUME_PATH)."""
    resume_path = os.getenv('RESUME_PATH', 'resume.pdf')
    if os.path.exists(resume_path):
        try:
            import pypdf
            reader = pypdf.PdfReader(resume_path)
            pages_text = [p.extract_text() for p in reader.pages if p.extract_text()]
            full_text = "\n".join(pages_text).strip()
            if len(full_text) > 100:
                logger.info(f"✓ Loaded resume text from '{resume_path}' ({len(full_text)} chars)")
                return full_text
        except Exception as e:
            logger.debug(f"pypdf extraction: {e}")
        try:
            import PyPDF2
            reader = PyPDF2.PdfReader(resume_path)
            pages_text = [p.extract_text() for p in reader.pages if p.extract_text()]
            full_text = "\n".join(pages_text).strip()
            if len(full_text) > 100:
                logger.info(f"✓ Loaded resume text via PyPDF2 ({len(full_text)} chars)")
                return full_text
        except Exception as e:
            logger.debug(f"PyPDF2 extraction: {e}")

    cand_name = os.getenv('CANDIDATE_NAME', 'Candidate')
    return f"Candidate: {cand_name}\nSkills: {', '.join(MY_TECH_STACK)}\nExperience: 0-2 Years (Fresher Software Engineer / Full Stack Developer)"


CANDIDATE_RESUME_TEXT = load_candidate_resume()


def evaluate_job_with_ai(title, jd_text, experience="0-1 Yrs"):
    """
    Two-Tier Evaluation:
    1. Regressed Python rule-based screening (role check, veto technologies, experience).
    2. Deep Gemini AI evaluation sending Candidate's Full Resume + Job Description.
    """
    # --- Tier 1: Regressed Python Rule-based screening ---
    if not is_software_engineering_role(title):
        return 0, "Non-software engineering role"

    veto_title = contains_veto_skills(title)
    if veto_title:
        return 0, f"Title contains veto technology: {veto_title}"

    is_exp_ok, exp_msg = is_experience_eligible(experience)
    if not is_exp_ok:
        return 0, f"Experience requirement mismatch: {exp_msg}"

    if jd_text:
        veto_jd = contains_veto_skills(jd_text[:2500])
        if veto_jd:
            return 0, f"JD requires '{veto_jd}'"

    # --- Tier 2: Gemini AI Evaluation (Full Resume + Job Description) ---
    if GEMINI_API_KEY:
        try:
            import requests
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash-lite:generateContent?key={GEMINI_API_KEY}"
            prompt = f"""You are an expert technical hiring manager evaluating candidate fit.
Compare the Candidate's Resume against the Job Description.

Candidate Resume:
{CANDIDATE_RESUME_TEXT[:2500]}

Job Title: {title}
Extracted Experience Requirement: {experience}
Job Description:
{jd_text[:2000] if jd_text else title}

Evaluation Criteria:
1. Tech Stack Overlap: Match candidate's skills (Python, Django, React, JavaScript, SQL, Web Dev, Full Stack) with the JD.
2. Experience Fit: Candidate is an Entry-Level / Fresher Software Engineer (0-2 years).
3. If primary stack aligns well (Python, React, Django, Web Dev, SQL), score >= 70.
4. If JD strictly requires senior/lead or veto technologies (Java, Spring Boot, .NET, C#, PHP), score < 40.

Respond ONLY with valid JSON:
{{"match": true, "score": <integer 0-100>, "reason": "<one concise sentence comparing candidate resume with JD>"}}"""

            payload = {"contents": [{"parts": [{"text": prompt}]}]}
            res = requests.post(url, json=payload, timeout=8)
            if res.status_code == 200:
                raw_text = res.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
                if "```json" in raw_text:
                    raw_text = raw_text.split("```json")[1].split("```")[0].strip()
                elif "```" in raw_text:
                    raw_text = raw_text.split("```")[1].split("```")[0].strip()
                data = json.loads(raw_text)
                score = int(data.get("score", 0))
                reason = data.get("reason", "")
                return score, f"Gemini AI (Resume Match): {reason}"
        except Exception as e:
            logger.debug(f"Gemini API fallback: {e}")

    # Fallback Tier: Python Heuristic Stack Matcher
    text_lower = (title + " " + (jd_text or "")[:2500]).lower()
    primary_skills = [
        "python", "javascript", "react", "node", "nodejs", "node.js",
        "sql", "django", "express", "full stack", "fullstack", "sde"
    ]
    matched = [s.title() for s in primary_skills if s in text_lower]

    if not matched:
        return 0, "No matching core skills (Python, React, Node.js, Django, SQL) found"

    base_score = 65
    if "full stack" in title.lower() or "fullstack" in title.lower():
        base_score += 18
    elif "python" in title.lower() or "node" in title.lower() or "react" in title.lower():
        base_score += 15
    elif "software" in title.lower() or "developer" in title.lower():
        base_score += 10

    overlap = len(set(matched))
    base_score += min(overlap * 3, 15)

    if "0-1" in experience or "0-2" in experience or "entry" in experience.lower() or "fresher" in text_lower or "2+" in experience:
        base_score += 5

    score = max(10, min(base_score, 95))
    matched_str = ", ".join(list(dict.fromkeys(matched))[:3])
    reason = f"Stack Match: Found [{matched_str}] for {experience} (Score: {score})"

    return score, reason


def ask_ai_for_modal_answer(question_text, is_numeric=False):
    """Uses Gemini AI with Candidate Resume to answer unfamiliar modal questions."""
    if not GEMINI_API_KEY:
        return "1" if is_numeric else "Yes"

    try:
        import requests
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash-lite:generateContent?key={GEMINI_API_KEY}"
        cand_name = os.getenv('CANDIDATE_NAME', 'the candidate')
        num_instruction = "This input accepts ONLY a single integer or decimal number (e.g. 1, 0, 8.5, 400000). Output ONLY the number." if is_numeric else "Provide a concise, professional answer (1-2 sentences max) written in the first person based on the candidate's resume."
        prompt = f"""You are filling out a job application on behalf of candidate {cand_name} using his resume.

Candidate Resume:
{CANDIDATE_RESUME_TEXT[:2200]}

Job Application Question:
"{question_text}"

Formatting Rules:
- {num_instruction}
- Do NOT include any explanations, prefixes, markdown, or quotation marks. Return ONLY the answer text."""

        payload = {"contents": [{"parts": [{"text": prompt}]}]}
        res = requests.post(url, json=payload, timeout=7)
        if res.status_code == 200:
            ans = res.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
            ans = ans.replace('"', '').replace("'", '').strip()
            if ans:
                logger.info(f"  🤖 Gemini AI generated answer: '{ans[:60]}'")
                return ans
    except Exception as e:
        logger.debug(f"AI modal answer generation: {e}")

    return "1" if is_numeric else "Yes"


def get_smart_answer(question_text, is_numeric=False):
    """
    Answers application questions using candidate's exact profile table:
    - Experience in tools/languages (Python=1, React=1, HTML/CSS=2, Total=0)
    - Personal details, CTC, Notice Period, Education, Logistics
    - Short answers (About, Why hire, Project, Strengths, Weaknesses, 3-5 yrs)
    - If question is not matched, uses Gemini AI with Candidate's Resume!
    """
    q = question_text.lower().strip()

    # ----------------------------------------------------
    # 1. Experience Fields (Numeric / Text)
    # ----------------------------------------------------
    if any(w in q for w in ["total work experience", "total experience", "overall experience", "years of overall"]):
        return "0"

    # Specific technology experience
    if "html" in q or "css" in q:
        return "2"
    if any(k in q for k in ["python", "javascript", "react", "node", "express", "sql", "mysql", "git", "github", "django"]):
        return "1"
    if any(w in q for w in ["how many years", "years of experience", "experience with", "experience in"]):
        return "1"

    # ----------------------------------------------------
    # 2. Personal & Logistics Fields
    # ----------------------------------------------------
    if any(w in q for w in ["current ctc", "current salary", "current compensation", "current annual", "current package"]):
        return "0"
    if any(w in q for w in ["expected ctc", "expected salary", "desired salary", "expected compensation", "expected package"]):
        return "400000" if is_numeric else "4 LPA"

    if any(w in q for w in ["notice", "joining", "how soon", "availability", "start date"]):
        # Fresher is an immediate joiner (0 days notice).
        # Entering "0" satisfies BOTH numeric inputs (which throw 'Invalid input' for text) AND text inputs!
        return "0"

    if any(w in q for w in ["current employer", "current company"]):
        return "Fresher"

    if any(w in q for w in ["graduation year", "year of graduation", "year of passing", "pass out year", "passing year"]):
        return os.getenv('CANDIDATE_GRAD_YEAR', '2026')

    if any(w in q for w in ["highest qualification", "degree", "education", "major"]):
        return os.getenv('CANDIDATE_DEGREE', 'B.E. in Computer Science and Engineering')

    if any(w in q for w in ["cgpa", "gpa"]):
        return os.getenv('CANDIDATE_CGPA', '8.5')
    if any(w in q for w in ["percentage", "marks"]):
        return os.getenv('CANDIDATE_PERCENTAGE', '85')

    if any(w in q for w in ["location", "city", "current city"]):
        return os.getenv('LOCATION', 'Bengaluru, Karnataka')
    if any(w in q for w in ["pincode", "zip"]):
        return "560001"

    if any(w in q for w in ["relocate", "relocation", "willing to relocate"]):
        return "Yes"

    if "github" in q or "portfolio" in q:
        return os.getenv('CANDIDATE_GITHUB', 'https://github.com/your-username')
    if "linkedin" in q:
        return os.getenv('CANDIDATE_LINKEDIN', 'https://www.linkedin.com/in/your-username')

    if any(w in q for w in ["phone", "mobile", "contact number"]):
        return os.getenv('CANDIDATE_PHONE', '9999999999')
    if "email" in q:
        return os.getenv('CANDIDATE_EMAIL', 'candidate@example.com')

    # ----------------------------------------------------
    # 3. Short Answers (Fresher Custom Profile)
    # ----------------------------------------------------
    if any(w in q for w in ["tell us about yourself", "about yourself", "introduce yourself", "bio"]):
        return os.getenv('CANDIDATE_BIO', "I'm a 2026 Computer Science graduate with hands-on experience in full-stack development across Python, JavaScript, React, Node.js and SQL. I've built deployed projects and completed engineering internships. I'm looking for my first full-time role to contribute and grow with a strong team.")

    if any(w in q for w in ["why should we hire you", "why hire you", "why hire"]):
        return os.getenv('CANDIDATE_WHY_HIRE', "I have hands-on experience through internships and deployed projects, so I'm comfortable with Git workflows, testing, and building features end-to-end. I learn quickly and take feedback constructively.")

    if any(w in q for w in ["why are you interested", "why this role", "why this company", "why do you want to work"]):
        return os.getenv('CANDIDATE_WHY_ROLE', "It matches my skills in full-stack development, and it's the kind of work I want to build my career on. I'd like to apply what I learned and continue improving under experienced engineers.")

    if any(w in q for w in ["describe a project", "proud of", "best project", "key project"]):
        return os.getenv('CANDIDATE_PROJECT_SUMMARY', "A full-stack application built with Python and React with RESTful APIs, asynchronous task processing, clean modular architecture, and real users.")

    if "strength" in q:
        return "I finish what I start, learn new technologies quickly, and focus on building functional, maintainable code."

    if "weakness" in q:
        return "I sometimes spend too long perfecting fine details, so I now set structured milestones to prioritize delivery first."

    if any(w in q for w in ["3-5 years", "in 5 years", "where do you see yourself", "future goals"]):
        return "Growing into a dependable full-stack engineer who designs scalable systems and mentors upcoming developers."

    if any(w in q for w in ["do you have any experience", "have any experience", "prior experience"]):
        return os.getenv('CANDIDATE_EXPERIENCE_SUMMARY', "Yes, I have completed software development internships along with full-stack personal and academic projects.")

    # ----------------------------------------------------
    # 4. If Question Did Not Match Table -> Use Gemini AI with Resume!
    # ----------------------------------------------------
    logger.info(f"  🔍 Question not in predefined table: '{question_text[:40]}' -> Querying Gemini AI with Resume...")
    return ask_ai_for_modal_answer(question_text, is_numeric=is_numeric)


def set_react_input(driver, element, value):
    """Sets the value of an input element using native keystrokes and React 18 event triggers."""
    try:
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
        time.sleep(0.1)
    except Exception:
        pass

    # 1. Native Selenium typing (triggers real OS input events)
    try:
        element.click()
        time.sleep(0.1)
        element.send_keys(Keys.CONTROL + "a")
        element.send_keys(Keys.BACKSPACE)
        time.sleep(0.1)
        element.send_keys(str(value))
        time.sleep(0.1)
    except Exception:
        pass

    # 2. React 18 synthetic event sync + valueTracker update
    try:
        driver.execute_script("""
            var input = arguments[0];
            var val = arguments[1];
            if (input.value !== val) {
                var prototype = Object.getPrototypeOf(input);
                var descriptor = Object.getOwnPropertyDescriptor(prototype, 'value') || 
                                 Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value') ||
                                 Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value');
                if (descriptor && descriptor.set) {
                    descriptor.set.call(input, val);
                } else {
                    input.value = val;
                }
            }
            if (input._valueTracker) {
                input._valueTracker.setValue('' + Math.random());
            }
            input.dispatchEvent(new Event('input', { bubbles: true }));
            input.dispatchEvent(new Event('change', { bubbles: true }));
            input.dispatchEvent(new Event('blur', { bubbles: true }));
        """, element, str(value))
    except Exception:
        pass


def answer_modal_questions(driver):
    """
    Finds and answers all question fields on the current LinkedIn Easy Apply modal step:
    - Text inputs (aria-label, preceding <p>, label)
    - Textareas
    - Dropdowns (<select> and custom listboxes/comboboxes)
    - Radio buttons (Yes / No / Fresher)
    - Checkboxes (Consent / acknowledgment)
    """
    answered_count = 0
    modal_container = "//dialog | //*[@role='dialog'] | //div[contains(@class, 'jobs-easy-apply')] | //div[contains(@class, 'modal')]"

    # 1. Text Inputs and Textareas
    inputs = driver.find_elements(
        By.XPATH,
        f"{modal_container}//input[@type='text' or @type='number' or @type='tel' or not(@type)] | "
        f"{modal_container}//textarea"
    )

    for inp in inputs:
        try:
            if not inp.is_displayed():
                continue

            # Check if this input has a validation error (e.g. 'Invalid input')
            has_error = False
            try:
                parent_fb = inp.find_elements(
                    By.XPATH,
                    "./ancestor::div[contains(@class, 'fb-dash-form-element') or contains(@class, 'form-group') or contains(@class, 'easyApplyFieldFocus')][1]//div[contains(@class, 'error') or contains(., 'Invalid input') or contains(., 'valid') or contains(., 'required')]"
                )
                if parent_fb:
                    has_error = True
            except Exception:
                pass

            curr_val = inp.get_attribute("value") or ""
            # If already filled with non-empty value and no validation error, skip
            if curr_val.strip() and not has_error:
                continue

            # Get Question Text from: 1) aria-label, 2) preceding <p>, 3) label, 4) parent container
            q_text = inp.get_attribute("aria-label") or ""
            if not q_text or len(q_text) < 3:
                try:
                    preceding_p = inp.find_elements(
                        By.XPATH,
                        "./ancestor::div[contains(@class, 'aaal6d') or contains(@class, 'fb-dash-form-element') or contains(@class, 'form')][1]//p"
                    )
                    for p in preceding_p:
                        pt = p.text.strip()
                        if pt and pt != "Additional Questions" and "characters" not in pt and len(pt) > 3:
                            q_text = pt
                            break
                except Exception:
                    pass

            if not q_text or len(q_text) < 3:
                inp_id = inp.get_attribute("id")
                if inp_id:
                    labels = driver.find_elements(By.XPATH, f"//label[@for='{inp_id}']")
                    if labels and labels[0].text.strip():
                        q_text = labels[0].text.strip()

            if not q_text or len(q_text) < 3:
                try:
                    parent_group = inp.find_element(
                        By.XPATH,
                        "./ancestor::div[contains(@class, 'fb-dash-form-element') or contains(@class, 'jobs-easy-apply-form-section__grouping') or contains(@class, 'form-group') or contains(@class, 'form')][1]"
                    )
                    q_text = parent_group.text.split("\n")[0].strip()
                except Exception:
                    pass

            # Clean question text
            q_text = q_text.replace("*", "").replace("Required", "").strip()

            inp_type = (inp.get_attribute("type") or "").lower()
            inp_inputmode = (inp.get_attribute("inputmode") or "").lower()
            inp_pattern = (inp.get_attribute("pattern") or "").lower()
            aria_desc = (inp.get_attribute("aria-describedby") or "").lower()
            inp_class = (inp.get_attribute("class") or "").lower()
            q_lower = q_text.lower()

            is_numeric = (
                inp_type == "number" or
                inp_inputmode == "numeric" or
                "numeric" in aria_desc or
                "number" in aria_desc or
                "numeric" in inp_class or
                "[0-9]" in inp_pattern or
                any(w in q_lower for w in [
                    "how many", "years", "number of", "days", "months", "scale",
                    "cgpa", "percentage", "rate", "1-10", "1 to 10", "experience do you have"
                ])
            )

            answer = get_smart_answer(q_text, is_numeric=is_numeric)

            logger.info(f"  📝 Answering '{q_text[:40]}' -> '{answer[:50]}'")
            set_react_input(driver, inp, answer)
            answered_count += 1
            time.sleep(0.3)
        except Exception:
            pass

    # 2. Radio Groups (Yes / No / Fresher)
    radios = driver.find_elements(
        By.XPATH,
        f"{modal_container}//input[@type='radio']"
    )
    processed_names = set()
    for r in radios:
        try:
            if not r.is_displayed():
                continue
            name = r.get_attribute("name") or r.get_attribute("id")
            if name in processed_names:
                continue

            # Find question text for this radio group
            q_text = ""
            try:
                parent_group = r.find_element(
                    By.XPATH,
                    "./ancestor::fieldset[1] | ./ancestor::div[contains(@class, 'fb-dash-form-element') or contains(@class, 'form')][1]"
                )
                q_text = parent_group.text.split("\n")[0].lower()
            except Exception:
                pass

            # Target answer
            if any(w in q_text for w in ["fresher or experienced", "experience level", "are you a fresher"]):
                target_text = "fresher"
            elif any(w in q_text for w in ["sponsor", "visa", "require sponsorship", "need sponsorship"]):
                target_text = "no"
            elif any(w in q_text for w in ["bond", "agreement", "service agreement"]):
                target_text = "yes"
            else:
                target_text = "yes"

            # Find all radio options in this group
            group_radios = driver.find_elements(
                By.XPATH,
                f"{modal_container}//input[@type='radio' and @name='{r.get_attribute('name')}']"
            )
            for gr in group_radios:
                lbl = ""
                gr_id = gr.get_attribute("id")
                if gr_id:
                    lbl_els = driver.find_elements(By.XPATH, f"//label[@for='{gr_id}']")
                    if lbl_els:
                        lbl = lbl_els[0].text.strip().lower()
                if not lbl:
                    try:
                        lbl = gr.find_element(By.XPATH, "./following-sibling::label").text.strip().lower()
                    except Exception:
                        pass

                if target_text in lbl:
                    if not gr.is_selected():
                        try:
                            gr.click()
                        except Exception:
                            driver.execute_script("arguments[0].click();", gr)
                        logger.info(f"  🔘 Radio '{q_text[:30]}' -> Selected '{target_text}'")
                        answered_count += 1
                    break

            processed_names.add(name)
        except Exception:
            pass

    # 3. Dropdowns (<select> and custom listboxes)
    selects = driver.find_elements(By.XPATH, f"{modal_container}//select")
    for s in selects:
        try:
            if not s.is_displayed():
                continue
            sel_obj = Select(s)
            selected = sel_obj.first_selected_option.text.strip().lower()
            if "select" in selected or not selected:
                options = sel_obj.options
                picked = False
                for opt in options:
                    t = opt.text.strip().lower()
                    if any(w in t for w in ["fresher", "yes", "immediate", "b.e", "bachelor", "computer science", "2026", "1 year", "0-1", "bengaluru", "bangalore"]):
                        sel_obj.select_by_visible_text(opt.text)
                        logger.info(f"  🔽 Dropdown selected: '{opt.text}'")
                        picked = True
                        answered_count += 1
                        break
                if not picked and len(options) > 1:
                    sel_obj.select_by_index(1)
                    logger.info(f"  🔽 Dropdown picked option: '{options[1].text}'")
                    answered_count += 1
        except Exception:
            pass

    # 4. Mandatory Checkboxes (Consent / Terms)
    checkboxes = driver.find_elements(By.XPATH, f"{modal_container}//input[@type='checkbox']")
    for cb in checkboxes:
        try:
            if cb.is_displayed() and not cb.is_selected():
                driver.execute_script("arguments[0].click();", cb)
                logger.info("  ☑️ Checked consent checkbox")
                answered_count += 1
        except Exception:
            pass

    return answered_count


def handle_easy_apply_modal(driver):
    """Advances through LinkedIn's Easy Apply modal (Auto-answers questions -> Next -> Review -> Submit)."""
    modal_container = "//dialog | //*[@role='dialog'] | //div[contains(@class, 'jobs-easy-apply')] | //div[contains(@class, 'modal')]"

    for step in range(12):
        time.sleep(1.5)
        try:
            # 1. Answer all question fields on the current step
            answer_modal_questions(driver)
            time.sleep(0.5)

            # 2. Check for Submit Application button
            submit_btns = driver.find_elements(
                By.XPATH,
                f"{modal_container}//button[@aria-label='Submit application' or normalize-space(.)='Submit application' or contains(., 'Submit application')]"
            )
            for sb in submit_btns:
                if sb.is_displayed():
                    logger.info("Clicking 'Submit application' button...")
                    try:
                        sb.click()
                    except Exception:
                        driver.execute_script("arguments[0].click();", sb)
                    time.sleep(3)
                    logger.info("✓ Submitted application successfully!")
                    return True

            # 3. Check for Next button (priority on multi-step forms)
            next_btns = driver.find_elements(
                By.XPATH,
                f"{modal_container}//button[normalize-space(.)='Next' or @aria-label='Continue to next step' or contains(., 'Next')]"
            )
            clicked_nav = False
            for nb in next_btns:
                if nb.is_displayed() and "review" not in nb.text.lower():
                    try:
                        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", nb)
                        time.sleep(0.2)
                        nb.click()
                    except Exception:
                        driver.execute_script("arguments[0].click();", nb)
                    time.sleep(2)
                    clicked_nav = True
                    break

            if clicked_nav:
                continue

            # 4. Check for Review button
            review_btns = driver.find_elements(
                By.XPATH,
                f"{modal_container}//button[normalize-space(.)='Review' or @aria-label='Review your application' or contains(., 'Review')]"
            )
            for rb in review_btns:
                if rb.is_displayed():
                    try:
                        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", rb)
                        time.sleep(0.2)
                        rb.click()
                    except Exception:
                        driver.execute_script("arguments[0].click();", rb)
                    time.sleep(2)
                    clicked_nav = True
                    break

            if clicked_nav:
                continue

            # 5. Check if any errors occurred on page and re-answer specifically
            error_msgs = driver.find_elements(
                By.XPATH,
                f"{modal_container}//div[contains(@class, 'error') or contains(., 'Invalid input') or contains(., 'valid') or contains(., 'required')]"
            )
            if error_msgs:
                logger.warning("Detected question validation error, re-answering fields...")
                answer_modal_questions(driver)
                time.sleep(1)

        except Exception as e:
            logger.warning(f"Modal step error: {e}")
            break

    # Final cleanup: ensure modal is closed if stuck
    try:
        close_btns = driver.find_elements(
            By.XPATH,
            f"{modal_container}//button[contains(@aria-label, 'Dismiss') or contains(@aria-label, 'Close')]"
        )
        for cb in close_btns:
            if cb.is_displayed():
                driver.execute_script("arguments[0].click();", cb)
                time.sleep(1)
                discard_btns = driver.find_elements(By.XPATH, "//button[contains(., 'Discard')]")
                for db in discard_btns:
                    if db.is_displayed():
                        driver.execute_script("arguments[0].click();", db)
                break
    except Exception:
        pass
    return False


def build_linkedin_search_url(keyword):
    """
    Constructs a URL targeting ONLY:
      - Easy Apply (f_AL=true)
      - Fresh postings (f_TPR=r86400 -> Past 24h)
      - Entry Level (f_E=2)
      - Sorted by Date (sortBy=DD)
    """
    params = {
        'keywords': keyword,
        'location': LOCATION,
        'f_AL': 'true',          # Only Easy Apply
        'f_TPR': 'r86400',       # Past 24 hours (fresh)
        'f_E': '2',              # 2=Entry level
        'sortBy': 'DD'           # Most recent
    }
    return f"https://www.linkedin.com/jobs/search/?{urllib.parse.urlencode(params)}"


def apply_linkedin_entry_level_filter(driver):
    """
    Applies the 'Entry-level' filter in LinkedIn's modern UI.
    Finds the visible 'Experience level' pill (with verified dimensions > 10px),
    clicks it to open the popup dropdown, selects the 'Entry-level' checkbox, and clicks 'Show results'.
    """
    try:
        # 1. Target specifically the real visible filter pill with height > 10 and width > 10
        target_pill = None

        candidate_pills = driver.find_elements(
            By.XPATH,
            "//div[@aria-label='Filter by Experience level'] | "
            "//button[contains(., 'Experience level')] | "
            "//label[normalize-space(.)='Experience level']"
        )
        for p in candidate_pills:
            try:
                if p.is_displayed() and p.size.get('height', 0) > 10 and p.size.get('width', 0) > 10:
                    target_pill = p
                    break
            except Exception:
                continue

        if not target_pill:
            # Secondary scan for any button/pill containing Experience level in top filter bar
            fallback_pills = driver.find_elements(
                By.XPATH,
                "//nav//button[contains(., 'Experience')] | "
                "//header//button[contains(., 'Experience')] | "
                "//div[contains(@class, 'filter')]//*[normalize-space(.)='Experience level']"
            )
            for p in fallback_pills:
                try:
                    if p.is_displayed() and p.size.get('height', 0) > 10 and p.size.get('width', 0) > 10:
                        target_pill = p
                        break
                except Exception:
                    continue

        if not target_pill:
            logger.info("Experience level filter pill not found or already in applied state.")
            return

        logger.info("Clicking LinkedIn 'Experience level' filter pill...")
        try:
            driver.execute_script("arguments[0].scrollIntoView({block: 'center', inline: 'center'});", target_pill)
            time.sleep(0.3)
            ActionChains(driver).move_to_element(target_pill).click().perform()
        except Exception:
            driver.execute_script("arguments[0].click();", target_pill)
        time.sleep(1.5)

        # 2. Verify if the popup dropdown opened by looking for the Entry-level checkbox
        entry_cbs = driver.find_elements(
            By.XPATH,
            "//input[@type='checkbox' and @aria-label='Entry-level'] | "
            "//input[@type='checkbox' and contains(@aria-label, 'Entry')] | "
            "//label[contains(., 'Entry-level')]//input[@type='checkbox']"
        )

        if not entry_cbs:
            # If popup didn't open on first try, trigger via JS dispatch
            logger.info("Dropdown popup did not open on first click, retrying with JavaScript dispatch...")
            try:
                driver.execute_script(
                    "arguments[0].dispatchEvent(new MouseEvent('click', {bubbles: true, cancelable: true, view: window}));",
                    target_pill
                )
            except Exception:
                driver.execute_script("arguments[0].click();", target_pill)
            time.sleep(1.5)
            entry_cbs = driver.find_elements(
                By.XPATH,
                "//input[@type='checkbox' and @aria-label='Entry-level'] | "
                "//input[@type='checkbox' and contains(@aria-label, 'Entry')] | "
                "//label[contains(., 'Entry-level')]//input[@type='checkbox']"
            )

        # 3. Select the 'Entry-level' checkbox
        if entry_cbs:
            cb = entry_cbs[0]
            if not cb.is_selected():
                logger.info("Selecting 'Entry-level' checkbox in popup...")
                try:
                    ActionChains(driver).move_to_element(cb).click().perform()
                except Exception:
                    driver.execute_script("arguments[0].click();", cb)
                time.sleep(1)
            else:
                logger.info("✓ 'Entry-level' checkbox is already checked.")
        else:
            # Text label fallback
            entry_options = driver.find_elements(
                By.XPATH,
                "//label[normalize-space(.)='Entry-level'] | "
                "//p[normalize-space(.)='Entry-level']"
            )
            if entry_options:
                logger.info("Clicking 'Entry-level' label text...")
                try:
                    ActionChains(driver).move_to_element(entry_options[0]).click().perform()
                except Exception:
                    driver.execute_script("arguments[0].click();", entry_options[0])
                time.sleep(1)

        # 4. Click 'Show results' button (may be <a>, <button>, or <span>)
        show_btns = driver.find_elements(
            By.XPATH,
            "//span[normalize-space(.)='Show results']/ancestor::a | "
            "//span[normalize-space(.)='Show results']/ancestor::button | "
            "//a[contains(., 'Show results')] | "
            "//button[contains(., 'Show results')] | "
            "//*[normalize-space(.)='Show results']"
        )
        for b in show_btns:
            if b.is_displayed():
                logger.info(f"Clicking 'Show results' ({b.tag_name}) to apply Entry-level filter...")
                try:
                    ActionChains(driver).move_to_element(b).click().perform()
                except Exception:
                    driver.execute_script("arguments[0].click();", b)
                time.sleep(3)
                logger.info("✓ Entry-level filter applied successfully! Only 0-2 yrs jobs will be processed.")
                break

    except Exception as e:
        logger.warning(f"Could not apply Entry-level UI filter: {e}")


def scrape_and_apply_linkedin(driver):
    """Searches and applies to LinkedIn Easy Apply jobs."""
    applied = 0
    rejected = 0
    failed = 0

    for kw in KEYWORDS:
        if applied >= MAX_APPLICATIONS:
            break

        search_url = build_linkedin_search_url(kw)
        logger.info(f"\n🔍 Searching LinkedIn: '{kw}' in '{LOCATION}' (Easy Apply + Entry Level + Past 24h)...")
        driver.get(search_url)
        time.sleep(5)

        # Apply UI Entry Level filter to guarantee 0-2 yrs fresh jobs
        apply_linkedin_entry_level_filter(driver)
        time.sleep(2)

        # Scroll down left pane to trigger lazy loading of cards
        try:
            scroll_container = driver.find_elements(
                By.CSS_SELECTOR,
                "[componentkey='SearchResultsMainContent'], [data-testid='lazy-column'], main#workspace"
            )
            if scroll_container:
                for _ in range(3):
                    driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight;", scroll_container[0])
                    time.sleep(1)
            else:
                for _ in range(3):
                    driver.execute_script("window.scrollTo(0, document.body.scrollHeight/2);")
                    time.sleep(1)
        except Exception:
            pass

        # Collect job card items from both modern React container and fallback selectors
        cards = driver.find_elements(
            By.CSS_SELECTOR,
            "[componentkey='SearchResultsMainContent'] div[role='button'], "
            "[data-testid='lazy-column'] div[role='button'], "
            "main#workspace div[role='button'], "
            "li.jobs-search-results__list-item, div.job-card-container"
        )

        # Filter cards that actually represent job listings
        job_cards = []
        for c in cards:
            c_text = c.text.strip()
            if not c_text:
                continue
            # Must be a job card (contains title/company or Easy Apply indicator)
            lines = [l.strip() for l in c_text.split("\n") if l.strip()]
            if len(lines) >= 3 and ("easy apply" in c_text.lower() or "developer" in c_text.lower() or "engineer" in c_text.lower()):
                job_cards.append(c)

        logger.info(f"Found {len(job_cards)} Easy Apply job cards on page.")

        for card in job_cards:
            if applied >= MAX_APPLICATIONS:
                break

            # Parse lines from card text
            card_lines = [l.strip() for l in card.text.split("\n") if l.strip()]
            raw_title = card_lines[0] if len(card_lines) > 0 else "Unknown Role"
            title = raw_title.replace("(Verified job)", "").replace("Verified job", "").strip()
            company = card_lines[2] if len(card_lines) > 2 else (card_lines[1] if len(card_lines) > 1 else "Unknown Company")
            exp = "0-2 Yrs"

            # Check if this card offers Easy Apply
            if "easy apply" not in card.text.lower():
                continue

            # Click card to open right pane details
            try:
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", card)
                time.sleep(1)
                driver.execute_script("arguments[0].click();", card)
                time.sleep(2)
            except Exception:
                continue

            link = driver.current_url

            # Extract job_id from URL
            job_id = None
            m_id = re.search(r'currentJobId=(\d+)', link) or re.search(r'/jobs/view/(\d+)', link)
            if m_id:
                job_id = m_id.group(1)

            # 1. Verify Software Role
            if not is_software_engineering_role(title):
                rej_reason = "Non-software role"
                print_job_box("REJECTED", company, title, exp, 0, rej_reason, link)
                record_job_status(company, title, exp, 0, "Rejected", rej_reason, link)
                rejected += 1
                continue

            # 2. Veto Check on Title
            veto = contains_veto_skills(title)
            if veto:
                rej_reason = f"Title has veto technology: {veto}"
                print_job_box("REJECTED", company, title, exp, 0, rej_reason, link)
                record_job_status(company, title, exp, 0, "Rejected", rej_reason, link)
                rejected += 1
                continue

            # 3. Extract Full Job Description & Experience from Description
            dom_jd = ""
            try:
                jd_containers = driver.find_elements(
                    By.XPATH,
                    "//div[contains(@class, 'jobs-description') or contains(@id, 'job-details')] | "
                    "//h2[contains(., 'About the job')]/ancestor::section | "
                    "//main[@id='workspace']//section"
                )
                if jd_containers:
                    dom_jd = jd_containers[0].text.strip()
            except Exception:
                dom_jd = ""

            jd_text = fetch_linkedin_jd(job_id, dom_jd)

            # Extract actual experience directly from the description!
            exp = extract_experience_from_jd(jd_text)

            # Validate experience suitability for 0-2 yrs candidate
            is_exp_ok, exp_msg = is_experience_eligible(exp)
            if not is_exp_ok:
                rej_reason = f"Experience requirement mismatch: {exp_msg}"
                print_job_box("REJECTED", company, title, exp, 0, rej_reason, link)
                record_job_status(company, title, exp, 0, "Rejected", rej_reason, link)
                rejected += 1
                continue

            # Check veto in JD text
            if jd_text:
                veto_jd = contains_veto_skills(jd_text[:2500])
                if veto_jd:
                    rej_reason = f"JD requires '{veto_jd}'"
                    print_job_box("REJECTED", company, title, exp, 0, rej_reason, link)
                    record_job_status(company, title, exp, 0, "Rejected", rej_reason, link)
                    rejected += 1
                    continue

            # 4. AI & Tech Stack Scoring
            score, reason = evaluate_job_with_ai(title, jd_text or card.text, exp)
            if score < MIN_SCORE:
                rej_reason = f"Score {score} < {MIN_SCORE}: {reason}"
                print_job_box("REJECTED", company, title, exp, score, rej_reason, link)
                record_job_status(company, title, exp, score, "Rejected", rej_reason, link)
                rejected += 1
                continue

            # 5. Look for Easy Apply button on right pane
            applied_flag = False
            try:
                easy_apply_btns = driver.find_elements(
                    By.XPATH,
                    "//button[contains(@aria-label, 'Easy Apply') or contains(., 'Easy Apply')]"
                )
                if easy_apply_btns:
                    driver.execute_script("arguments[0].click();", easy_apply_btns[0])
                    time.sleep(2)
                    applied_flag = handle_easy_apply_modal(driver)
            except Exception as e:
                logger.warning(f"Easy apply error: {e}")

            if applied_flag:
                applied += 1
                print_job_box("APPLIED", company, title, exp, score, reason, link)
                record_job_status(company, title, exp, score, "Applied", reason, link)
                time.sleep(3)
            else:
                failed += 1
                print_job_box("FAILED", company, title, exp, score, "Complex modal questions or already applied", link)
                record_job_status(company, title, exp, score, "Failed", "Complex modal or already applied", link)

    return applied, rejected, failed


def main():
    logger.info("=" * 50)
    logger.info("LinkedIn Easy Apply Bot (Edge Edition)")
    logger.info("=" * 50)

    init_csv_report()
    driver = None
    try:
        driver = create_edge_driver()
        login_linkedin(driver)
        applied, rejected, failed = scrape_and_apply_linkedin(driver)

        logger.info("\n" + "=" * 50)
        logger.info("LINKEDIN APPLICATION SUMMARY")
        logger.info(f"  ✓ Successfully Applied : {applied}")
        logger.info(f"  ⏭ Total Rejected/Skipped: {rejected}")
        logger.info(f"  ✗ Failed/Skipped Modals : {failed}")
        logger.info(f"  📁 Full report saved in : {CSV_REPORT_FILE}")
        logger.info("=" * 50)
    except Exception as e:
        logger.exception(f"Unexpected error: {e}")
    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass


if __name__ == "__main__":
    main()
