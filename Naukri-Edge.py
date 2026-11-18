"""
Naukri Auto-Apply Bot - Microsoft Edge Version (Intelligent Skill & Experience Matcher)
========================================================================================
Features:
  - Opens visible Microsoft Edge browser window on desktop.
  - Strict Experience Filter: Applies only to 0-1 and 1-2 years experience.
  - Veto Skill Filter: Rejects Java, Spring Boot, .NET, C#, C++, PHP, Android, iOS, Lead/Architect.
  - Gemini AI Matching: Uses Gemini API to evaluate Job Description against your skills (Score >= 60).
  - Real-time CSV logging: Saves applied & rejected jobs to naukriapplied.csv immediately.
"""

import os
import re
import csv
import json
import time
import logging
from datetime import datetime
import pandas as pd
from dotenv import load_dotenv
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.edge.service import Service as EdgeService
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException

try:
    from webdriver_manager.microsoft import EdgeChromiumDriverManager
    WEBDRIVER_MANAGER_AVAILABLE = True
except ImportError:
    WEBDRIVER_MANAGER_AVAILABLE = False

try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False

# ------------------------------------------------------------
# Configuration
# ------------------------------------------------------------
load_dotenv()

NAUKRI_EMAIL = os.getenv('NAUKRI_EMAIL', '')
NAUKRI_PASSWORD = os.getenv('NAUKRI_PASSWORD', '')
FIRSTNAME = os.getenv('FIRSTNAME', 'Candidate')
LASTNAME = os.getenv('LASTNAME', '')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', '')

KEYWORDS = [kw.strip() for kw in os.getenv('KEYWORDS', 'Python Developer, Full Stack Developer').split(',') if kw.strip()]
LOCATION = os.getenv('LOCATION', 'Bangalore').strip()

MAX_APPLICATIONS = int(os.getenv('MAX_APPLICATIONS', '50'))
PAGES_PER_KEYWORD = int(os.getenv('PAGES_PER_KEYWORD', '2'))
EDGE_DRIVER_PATH = os.getenv('EDGE_DRIVER_PATH', '')

CSV_REPORT_FILE = "naukriapplied.csv"
MIN_SCORE = 60
MAX_EXP_YEARS = 2  # Strict: 0-1 or 1-2 years only

MY_TECH_STACK = [
    "Python", "JavaScript", "SQL", "React.js", "Django", 
    "Node.js", "Express.js", "MySQL", "Supabase", "Git", "REST APIs", "HTML5", "CSS3"
]

VETO_KEYWORDS = [
    "senior", "sr.", "sr ", "lead", "principal", "architect", "manager", "head",
    "intern", "internship", "fellow", "post doctoral", "phd", "researcher",
    "planner", "urban designer", "designer", "transportation", "civil", "mechanical", "electrical",
    "accountant", "finance", "hr", "recruiter", "sales", "marketing", "business development",
    "java", "spring boot", "springboot", ".net", "dotnet", "c#", "asp.net",
    "c++", "ruby", "golang", "php", "laravel", "flutter", "swift", "kotlin",
    "android", "ios", "tutor", "trainer", "consultant"
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

# Initialize Gemini AI
ai_model = None



def print_job_box(status_type, company, title, exp, score, reason, link):
    """Prints a clean, single-line clickable link without breaking the URL."""
    tag = "🟢 APPLIED" if status_type == "APPLIED" else ("🔴 REJECTED" if status_type == "REJECTED" else "🟡 FAILED")
    print("\n" + "=" * 70)
    print(f"[{tag}] {company} - {title} ({exp})")
    print(f"Match : {score}/100 | {reason}")
    print(f"Link  : {link}")
    print("=" * 70 + "\n")


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
        logger.warning(f"⚠️ '{CSV_REPORT_FILE}' is open in Excel/another program. Please close it to allow real-time saving.")


def record_job_status(company, title, experience, score, status, reason, link):
    """Save immediately to CSV so no data is lost if stopped midway."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for attempt in range(3):
        try:
            with open(CSV_REPORT_FILE, 'a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow([
                    timestamp, company, title, experience, 
                    score, status, reason, link
                ])
            return
        except PermissionError:
            if attempt == 0:
                logger.warning(f"⚠️ Permission denied on '{CSV_REPORT_FILE}'. If opened in Excel, please close it. Retrying in 1s...")
            time.sleep(1)
        except Exception as e:
            logger.warning(f"Could not write to CSV: {e}")
            break


def validate_config():
    """Check required config values."""
    if not NAUKRI_EMAIL or not NAUKRI_PASSWORD:
        logger.error("NAUKRI_EMAIL or NAUKRI_PASSWORD not set in .env")
        return False
    return True


def create_edge_driver():
    """Create a visible Edge browser instance."""
    options = webdriver.EdgeOptions()
    options.add_argument("--start-maximized")
    options.add_argument("--disable-notifications")

    if WEBDRIVER_MANAGER_AVAILABLE:
        service = EdgeService(EdgeChromiumDriverManager().install())
    elif EDGE_DRIVER_PATH:
        service = EdgeService(executable_path=EDGE_DRIVER_PATH)
    else:
        service = EdgeService()

    return webdriver.Edge(service=service, options=options)


def login_naukri(driver):
    """Log in to Naukri.com."""
    logger.info("Logging in to Naukri.com...")
    driver.get('https://login.naukri.com/')
    time.sleep(3)

    try:
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, 'usernameField'))
        )
        driver.find_element(By.ID, 'usernameField').send_keys(NAUKRI_EMAIL)
        passwd = driver.find_element(By.ID, 'passwordField')
        passwd.send_keys(NAUKRI_PASSWORD)
        passwd.send_keys(Keys.ENTER)
        time.sleep(7)
        logger.info("✓ Login completed.")
    except Exception as e:
        logger.error(f"Login failed: {e}")


def build_search_urls():
    """Build search URLs for every keyword and page."""
    urls = []
    for keyword in KEYWORDS:
        keyword_slug = keyword.lower().replace(' ', '-')
        for page_num in range(1, PAGES_PER_KEYWORD + 1):
            if not LOCATION:
                url = f"https://www.naukri.com/{keyword_slug}-jobs" if page_num == 1 else f"https://www.naukri.com/{keyword_slug}-jobs-{page_num}"
            else:
                loc_slug = LOCATION.lower().replace(' ', '-')
                url = f"https://www.naukri.com/{keyword_slug}-jobs-in-{loc_slug}" if page_num == 1 else f"https://www.naukri.com/{keyword_slug}-jobs-in-{loc_slug}-{page_num}"
            urls.append((keyword, url))
    return urls


def open_tabs_parallel(driver, search_urls):
    """Open all search URLs in parallel tabs."""
    original_window = driver.current_window_handle
    for keyword, url in search_urls:
        driver.execute_script(f"window.open('{url}', '_blank');")
        time.sleep(0.4)
    return original_window


def extract_job_info_from_card(job_wrapper):
    """Extract job details (title, company, exp, href) from card."""
    title_link = job_wrapper.find('a', class_='title')
    if not title_link or not title_link.get('href'):
        return None

    href = title_link.get('href')
    if href.startswith('/'):
        href = 'https://www.naukri.com' + href

    title = title_link.get_text(strip=True)

    comp_el = job_wrapper.find('a', class_='comp-name') or job_wrapper.find('span', class_='comp-name')
    company = comp_el.get_text(strip=True) if comp_el else "Unknown Company"

    exp_span = job_wrapper.find('span', class_='expwdth') or job_wrapper.find('li', class_='experience')
    exp_text = exp_span.get_text(strip=True) if exp_span else "0-1 Yrs"

    tags = [tag.get_text(strip=True).lower() for tag in job_wrapper.find_all('li', class_='dot-gt')]

    return {
        "title": title,
        "company": company,
        "href": href,
        "experience": exp_text,
        "tags": tags
    }


def is_software_engineering_role(title):
    """Ensure the job title is actually a software / web developer role."""
    t = title.lower()
    return any(w in t for w in SOFTWARE_ROLE_KEYWORDS)


def is_experience_suitable(exp_text, title=""):
    """
    Ensure job is strictly 0-1 or 1-2 years and not a Senior/Lead role.
    """
    full_text = f"{title} {exp_text}".lower()
    if any(w in full_text for w in ["senior", "sr.", "sr ", "lead", "architect", "manager", "principal", "intern", "fellow"]):
        return False

    if not exp_text:
        return True

    nums = [int(n) for n in re.findall(r'\b\d+\b', exp_text)]
    if not nums:
        return True

    min_exp = nums[0]
    max_exp = nums[1] if len(nums) > 1 else min_exp

    if min_exp > MAX_EXP_YEARS or max_exp > 3:
        return False
    return True


def contains_veto_skills(text):
    """Check if title or text has veto technologies like Java, .NET, C++, etc."""
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
        return 0, "Non-software role (urban designer, planner, fellow, etc.)"

    veto_title = contains_veto_skills(title)
    if veto_title:
        return 0, f"Title contains veto technology: {veto_title}"

    if not is_experience_suitable(experience, title):
        return 0, f"Experience {experience} > 2 Yrs or Senior/Lead role"

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
        except Exception:
            pass

    # 2. Strict Stack Matcher Fallback
    text_lower = (title + " " + jd_text[:2500]).lower()
    primary_skills = [
        "python", "javascript", "react", "node", "nodejs", "node.js",
        "sql", "django", "express", "full stack", "fullstack", "sde"
    ]
    matched = [s.title() for s in primary_skills if s in text_lower]

    # If no core software tech stack keyword is found, do NOT approve!
    if not matched:
        return 0, "No matching core skills (Python, React, Node.js, Django, SQL) found"

    base_score = 60
    if "full stack" in title.lower() or "fullstack" in title.lower() or "mern" in title.lower():
        base_score += 20
    elif "python" in title.lower() or "node" in title.lower() or "react" in title.lower():
        base_score += 15
    elif "software" in title.lower() or "sde" in title.lower() or "developer" in title.lower():
        base_score += 10

    overlap = len(set(matched))
    base_score += min(overlap * 4, 15)

    if "0-1" in experience or "0-2" in experience or "fresher" in text_lower:
        base_score += 5

    score = max(10, min(base_score, 95))
    matched_str = ", ".join(list(dict.fromkeys(matched))[:3])
    reason = f"Stack Match: Found [{matched_str}] for {experience} (Score: {score})"

    return score, reason


def collect_job_cards_from_tab(driver, window_handle):
    """Collect job information from a search tab."""
    driver.switch_to.window(window_handle)
    time.sleep(3)

    soup = BeautifulSoup(driver.page_source, 'html5lib')
    wrappers = soup.find_all('div', class_='srp-jobtuple-wrapper') or soup.find_all('div', class_='cust-job-tuple')
    logger.info(f"[{driver.title[:45]}] Found {len(wrappers)} job cards.")

    cards = []
    for w in wrappers:
        info = extract_job_info_from_card(w)
        if info:
            cards.append(info)
    return cards


def collect_all_jobs_parallel(driver, search_urls):
    """Open all searches, filter cards by experience & veto skills, return qualified jobs."""
    original_window = open_tabs_parallel(driver, search_urls)
    window_handles = driver.window_handles

    raw_jobs = []
    for handle in window_handles:
        tab_cards = collect_job_cards_from_tab(driver, handle)
        raw_jobs.extend(tab_cards)

    for handle in window_handles:
        if handle != original_window:
            try:
                driver.switch_to.window(handle)
                driver.close()
            except WebDriverException:
                pass
    driver.switch_to.window(original_window)

    seen = set()
    filtered_jobs = []
    for job in raw_jobs:
        href = job['href']
        if href in seen:
            continue
        seen.add(href)

        # 1. Experience & Role check
        if not is_experience_suitable(job['experience'], job['title']):
            reason = f"Experience > 2 yrs or Senior/Intern ({job['experience']})"
            logger.info(f"  ⏭ REJECTED: {job['company']} | {job['title'][:35]} -> {reason}")
            print_job_box("REJECTED", job['company'], job['title'], job['experience'], 0, reason, href)
            record_job_status(job['company'], job['title'], job['experience'], 0, "Rejected", reason, href)
            continue

        # 2. Software role verification
        if not is_software_engineering_role(job['title']):
            reason = "Not a software / web developer role"
            logger.info(f"  ⏭ REJECTED: {job['company']} | {job['title'][:35]} -> {reason}")
            print_job_box("REJECTED", job['company'], job['title'], job['experience'], 0, reason, href)
            record_job_status(job['company'], job['title'], job['experience'], 0, "Rejected", reason, href)
            continue

        # 2. Veto check on title
        veto_hit = contains_veto_skills(job['title'])
        if veto_hit:
            reason = f"Unwanted skill: {veto_hit}"
            logger.info(f"  ⏭ REJECTED: {job['company']} | {job['title'][:35]} -> {reason}")
            record_job_status(job['company'], job['title'], job['experience'], 0, "Rejected", reason, href)
            continue

        filtered_jobs.append(job)

    logger.info(f"Total passed initial filter (0-2 yrs & non-veto): {len(filtered_jobs)}")
    return filtered_jobs


def ask_ai_for_modal_answer(question_text, is_numeric=False):
    """Uses Gemini AI with Candidate Resume to answer unfamiliar modal/chatbot questions."""
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

    # 1. Experience Fields (Numeric / Text)
    if any(w in q for w in ["total work experience", "total experience", "overall experience", "years of overall"]):
        return "0"

    # Specific technology experience
    if "html" in q or "css" in q:
        return "2"
    if any(k in q for k in ["python", "javascript", "react", "node", "express", "sql", "mysql", "git", "github", "django"]):
        return "1"
    if any(w in q for w in ["how many years", "years of experience", "experience with", "experience in"]):
        return "1"

    # 2. Personal & Logistics Fields
    if any(w in q for w in ["current ctc", "current salary", "current compensation", "current annual", "current package"]):
        return "0"
    if any(w in q for w in ["expected ctc", "expected salary", "desired salary", "expected compensation", "expected package"]):
        # Purely numeric digits: "4" (standard 4 LPA number, no text)
        return "4"

    if any(w in q for w in ["notice", "joining", "how soon", "availability", "start date"]):
        return "15" if (is_numeric or "day" in q) else "Immediate"

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

    # 3. Short Answers (Fresher Custom Profile)
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

    # 4. If Question Did Not Match Table -> Use Gemini AI with Resume!
    logger.info(f"  🔍 Question not in predefined table: '{question_text[:40]}' -> Querying Gemini AI with Resume...")
    return ask_ai_for_modal_answer(question_text, is_numeric=is_numeric)


def is_naukri_drawer_open(driver):
    """Check if Naukri chatbot drawer or questionnaire is open."""
    try:
        drawers = driver.find_elements(
            By.CSS_SELECTOR,
            "[id*='ChatbotContainer'], .chatbot_Drawer, .drawer-wrapper, div.custom-drawer, div.apply-message"
        )
        for d in drawers:
            if d.is_displayed():
                return True
    except Exception:
        pass
    return False


def get_latest_naukri_bot_question(driver):
    """Extracts the latest question text from Naukri chatbot or modal."""
    try:
        msgs = driver.find_elements(
            By.CSS_SELECTOR,
            ".chatbot_ListItem.botItem .msg, .chatbot_ListItem .botMsg .msg, div.bot-item .msg, div.question-text"
        )
        if msgs:
            return msgs[-1].text.strip()
        labels = driver.find_elements(By.CSS_SELECTOR, ".drawer-wrapper label, .custom-drawer label, div.question")
        if labels:
            return labels[-1].text.strip()
    except Exception:
        pass
    return "Application Question"


def find_naukri_chat_text_area(driver):
    """Finds contenteditable div or text input inside Naukri chatbot."""
    try:
        elements = driver.find_elements(
            By.CSS_SELECTOR,
            ".chatbot_SendMessageContainer .textArea[contenteditable='true'], "
            ".chatbot_InputContainer .textArea[contenteditable='true'], "
            "div.textArea[contenteditable='true'], "
            "[id*='ChatbotContainer'] input[type='text'], "
            "[id*='ChatbotContainer'] input[type='number'], "
            "[id*='ChatbotContainer'] textarea"
        )
        for el in elements:
            if el.is_displayed() and el.is_enabled():
                return el
    except Exception:
        pass
    return None


def find_naukri_save_button(driver):
    """Finds Save/Send button in Naukri chatbot footer or modal."""
    try:
        selectors = [
            ".sendMsg",
            ".sendMsgbtn_container .sendMsg",
            "[class*='sendMsg']",
            "div.sendMsg",
            "[id*='ChatbotContainer'] button[type='submit']",
            "[id*='ChatbotContainer'] button.save-btn",
            "button.waves-effect"
        ]
        for sel in selectors:
            els = driver.find_elements(By.CSS_SELECTOR, sel)
            for el in els:
                if el.is_displayed():
                    return el
    except Exception:
        pass
    return None


def handle_naukri_chatbot_drawer(driver):
    """
    Handles Naukri's chatbot questionnaire drawer:
    - Auto-fills text inputs, contenteditable divs, and radio buttons using smart answers.
    - Uses Gemini AI with candidate resume as dynamic fallback.
    - Clicks Save/Send until drawer closes and application is submitted.
    """
    time.sleep(2)
    if not is_naukri_drawer_open(driver):
        return True

    logger.info("  🤖 Naukri chatbot questionnaire detected. Auto-answering...")

    for iteration in range(25):
        time.sleep(1.5)

        if not is_naukri_drawer_open(driver):
            logger.info("  ✓ Naukri questionnaire completed and drawer closed.")
            return True

        question_text = get_latest_naukri_bot_question(driver)

        # 1. Check for Radio buttons
        try:
            radio_container = driver.find_elements(By.CSS_SELECTOR, ".singleselect-radiobutton-container, .radio-container")
            if radio_container and radio_container[0].is_displayed():
                radios = radio_container[0].find_elements(By.CSS_SELECTOR, ".ssrc__radio, input[type='radio']")
                labels = radio_container[0].find_elements(By.CSS_SELECTOR, ".ssrc__label, label")

                best_answer = get_smart_answer(question_text, is_numeric=False)
                clicked_radio = False

                for rb, lbl in zip(radios, labels):
                    opt_text = (lbl.text or rb.get_attribute('value') or '').strip().lower()
                    if best_answer.lower() in opt_text or opt_text in best_answer.lower():
                        driver.execute_script("arguments[0].click();", rb)
                        logger.info(f"    🔘 Radio '{question_text[:30]}' -> Selected '{lbl.text.strip()}'")
                        clicked_radio = True
                        break

                if not clicked_radio and radios:
                    for rb, lbl in zip(radios, labels):
                        t = lbl.text.strip().lower()
                        if "yes" in t or "fresher" in t:
                            driver.execute_script("arguments[0].click();", rb)
                            logger.info(f"    🔘 Radio fallback -> Selected '{lbl.text.strip()}'")
                            clicked_radio = True
                            break
                    if not clicked_radio and radios:
                        driver.execute_script("arguments[0].click();", radios[0])

                time.sleep(1)
                save_btn = find_naukri_save_button(driver)
                if save_btn:
                    driver.execute_script("arguments[0].click();", save_btn)
                    time.sleep(1.5)
                continue
        except Exception:
            pass

        # 2. Check for Contenteditable or Text Input
        try:
            text_area = find_naukri_chat_text_area(driver)
            if text_area and text_area.is_displayed():
                is_num = any(w in question_text.lower() for w in ["how many", "years", "ctc", "salary", "experience"])
                answer = get_smart_answer(question_text, is_numeric=is_num)

                logger.info(f"    📝 Text: '{question_text[:35]}' -> Answering '{answer[:50]}'")

                driver.execute_script("""
                    arguments[0].focus();
                    if (arguments[0].tagName === 'DIV') {
                        arguments[0].innerText = arguments[1];
                    } else {
                        arguments[0].value = arguments[1];
                    }
                    arguments[0].dispatchEvent(new Event('input', {bubbles: true}));
                    arguments[0].dispatchEvent(new Event('change', {bubbles: true}));
                """, text_area, answer)
                time.sleep(0.5)

                try:
                    text_area.send_keys(Keys.RETURN)
                except Exception:
                    pass
                time.sleep(0.5)

                save_btn = find_naukri_save_button(driver)
                if save_btn:
                    driver.execute_script("arguments[0].click();", save_btn)
                    time.sleep(2)
                continue
        except Exception:
            pass

        # 3. Check for standard Save/Continue button
        try:
            save_btn = find_naukri_save_button(driver)
            if save_btn and save_btn.is_displayed():
                driver.execute_script("arguments[0].click();", save_btn)
                time.sleep(2)
                continue
        except Exception:
            pass

    return not is_naukri_drawer_open(driver)


def click_apply_button(driver):
    """Attempt to click the Apply button and handle any chatbot/questionnaire drawer."""
    time.sleep(2)
    apply_selectors = [
        (By.XPATH, "//button[contains(text(),'Apply on company site')]"),
        (By.XPATH, "//button[contains(text(),'Apply')]"),
        (By.ID, "company-site-button"),
        (By.CSS_SELECTOR, "button[class*='company-site-button']"),
        (By.CSS_SELECTOR, "[class*='apply-button-container'] button"),
        (By.XPATH, "//*[contains(@class, 'apply-button')]"),
    ]

    clicked = False
    for by, selector in apply_selectors:
        try:
            btn = WebDriverWait(driver, 3).until(EC.element_to_be_clickable((by, selector)))
            btn_text = btn.text.strip().lower()
            if "apply on company site" in btn_text:
                return False
            driver.execute_script("arguments[0].click();", btn)
            clicked = True
            break
        except (TimeoutException, NoSuchElementException):
            continue

    if not clicked:
        return False

    return handle_naukri_chatbot_drawer(driver)


def apply_to_jobs(driver, job_list):
    """Filter using Gemini score >= 60, then apply."""
    applied = 0
    failed = 0
    rejected = 0

    logger.info("=" * 50)
    logger.info(f"Evaluating and applying to jobs (Min Score: {MIN_SCORE}, Max Target: {MAX_APPLICATIONS})...")
    logger.info("=" * 50)

    try:
        for i, job in enumerate(job_list, 1):
            if applied >= MAX_APPLICATIONS:
                logger.info(f"Reached max application limit ({MAX_APPLICATIONS}). Stopping.")
                break

            title = job['title']
            company = job['company']
            exp = job['experience']
            link = job['href']

            logger.info(f"\n[{i}/{len(job_list)}] Evaluating: {company} | {title} ({exp})")

            try:
                driver.get(link)
                time.sleep(2)
            except Exception as e:
                logger.warning(f"  ✗ Failed to load page: {e}")
                record_job_status(company, title, exp, 0, "Failed", f"Failed to load: {e}", link)
                failed += 1
                continue

            # Extract full Job Description from Naukri page elements
            jd_elements = [
                "section.styles_job-desc-container__txpYf",
                "div.styles_JDC__dang-inner-html__h0K4t",
                "div.job-desc",
                "div.dang-inner-html",
                "section.job-desc-container",
                "div.clearBoth.description"
            ]
            body_text = ""
            for selector in jd_elements:
                try:
                    el = driver.find_element(By.CSS_SELECTOR, selector)
                    if el and el.text.strip():
                        body_text = el.text.strip()
                        break
                except NoSuchElementException:
                    continue

            # Fallback to full body if specific JD container wasn't matched
            if not body_text:
                try:
                    body_text = driver.find_element(By.TAG_NAME, "body").text
                except Exception:
                    body_text = ""

            # Check veto skills in JD text
            veto_jd = contains_veto_skills(body_text[:2500])
            if veto_jd:
                reason = f"Job requires '{veto_jd}' (outside tech stack)"
                logger.info(f"  ⏭ REJECTED: {reason}")
                print_job_box("REJECTED", company, title, exp, 0, reason, link)
                record_job_status(company, title, exp, 0, "Rejected", reason, link)
                rejected += 1
                continue

            # AI evaluation score
            score, reason = evaluate_job_with_ai(title, body_text, exp)

            if score < MIN_SCORE:
                rej_reason = f"Score {score} < {MIN_SCORE}: {reason}"
                logger.info(f"  ⏭ REJECTED: {rej_reason}")
                print_job_box("REJECTED", company, title, exp, score, rej_reason, link)
                record_job_status(company, title, exp, score, "Rejected", rej_reason, link)
                rejected += 1
                continue

            # Click Apply
            if click_apply_button(driver):
                applied += 1
                logger.info(f"  ✓ APPLIED: {company} | {title} (Total: {applied})")
                print_job_box("APPLIED", company, title, exp, score, reason, link)
                record_job_status(company, title, exp, score, "Applied", reason, link)
                time.sleep(2)
            else:
                failed += 1
                fail_reason = "Apply button not clickable or redirected external site"
                print_job_box("FAILED", company, title, exp, score, fail_reason, link)
                record_job_status(company, title, exp, score, "Failed", fail_reason, link)
                logger.warning("  ✗ No direct Apply button clickable.")

            try:
                if driver.find_element(By.XPATH, "//*[text()='Your daily quota has been expired.']"):
                    logger.info("Daily quota reached. Stopping.")
                    break
            except NoSuchElementException:
                pass

    except KeyboardInterrupt:
        logger.warning("\n⚠️ Process stopped manually by user (Ctrl+C). Saving current progress...")

    return applied, rejected, failed


def main():
    logger.info("=" * 50)
    logger.info("Naukri Auto-Apply (AI & Strict Skill-Match Edition)")
    logger.info("=" * 50)

    if not validate_config():
        return

    init_csv_report()

    logger.info(f"Target Keywords: {KEYWORDS}")
    logger.info(f"Location: {LOCATION}")
    logger.info(f"Experience Filter: 0-1 / 1-2 years only (Max: {MAX_EXP_YEARS} yrs)")
    logger.info(f"Vetoed Skills: Java, Spring Boot, .NET, C#, PHP, C++, etc.")
    logger.info(f"Minimum Match Score: {MIN_SCORE}/100")
    logger.info(f"Report File: {CSV_REPORT_FILE}")

    driver = None
    try:
        driver = create_edge_driver()
        login_naukri(driver)

        search_urls = build_search_urls()
        filtered_jobs = collect_all_jobs_parallel(driver, search_urls)

        if not filtered_jobs:
            logger.warning("No matching jobs found on page 1-2.")
            return

        applied, rejected, failed = apply_to_jobs(driver, filtered_jobs)

        logger.info("\n" + "=" * 50)
        logger.info("APPLICATION SUMMARY")
        logger.info(f"  ✓ Successfully Applied : {applied}")
        logger.info(f"  ⏭ Total Rejected/Skipped: {rejected}")
        logger.info(f"  ✗ Failed Applications   : {failed}")
        logger.info(f"  📁 Full report saved in : {CSV_REPORT_FILE}")
        logger.info("=" * 50)

    except Exception as e:
        logger.exception(f"Unexpected error: {e}")
    finally:
        if driver:
            try:
                driver.quit()
                logger.info("Browser closed.")
            except Exception:
                pass


if __name__ == "__main__":
    main()
