"""
Foundit (Monster India) Auto-Apply Bot
======================================
Automates job applications on Foundit.in using Microsoft Edge.
Features:
  - Strict 0-1 and 1-2 years experience filter.
  - Veto skills rejection (Java, Spring Boot, .NET, C#, PHP, Android, iOS, etc.).
  - Stack Match scoring (Python, React, Node.js, SQL, etc.).
  - 1-Click Quick Apply on Foundit job cards and detail pages.
  - Real-time logging to founditapplied.csv.
"""

import os
import re
import csv
import json
import time
import logging
from datetime import datetime
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.edge.service import Service as EdgeService
from selenium.webdriver.support.ui import WebDriverWait
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

FOUNDIT_EMAIL = os.getenv('FOUNDIT_EMAIL') or os.getenv('NAUKRI_EMAIL', '')
FOUNDIT_PASSWORD = os.getenv('FOUNDIT_PASSWORD') or os.getenv('NAUKRI_PASSWORD', '')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', '')

KEYWORDS = [kw.strip() for kw in os.getenv('KEYWORDS', 'Python Developer, Full Stack Developer').split(',') if kw.strip()]
LOCATION = os.getenv('LOCATION', 'Bangalore').strip()

MAX_APPLICATIONS = int(os.getenv('MAX_APPLICATIONS', '50'))
EDGE_DRIVER_PATH = os.getenv('EDGE_DRIVER_PATH', '')

CSV_REPORT_FILE = "founditapplied.csv"
MIN_SCORE = 60
MAX_EXP_YEARS = 2

MY_TECH_STACK = [
    "Python", "JavaScript", "SQL", "React.js", "Django", 
    "Node.js", "Express.js", "MySQL", "Supabase", "Git", "REST APIs", "HTML5", "CSS3"
]

VETO_KEYWORDS = [
    "senior", "sr.", "sr ", "lead", "principal", "architect", "manager", "head",
    "java", "spring boot", "springboot", ".net", "dotnet", "c#", "asp.net",
    "c++", "ruby", "golang", "php", "laravel", "flutter", "swift", "kotlin",
    "android", "ios", "tutor", "trainer", "sales", "consultant", "devops", "cloud engineer"
]

# ------------------------------------------------------------
# Candidate Profile & Resume Text
# ------------------------------------------------------------
RESUME_PATH = os.getenv('RESUME_PATH', r"C:\Users\Hp\Downloads\resume.pdf")

def load_resume_text():
    """Extract candidate resume text directly from PDF."""
    if os.path.exists(RESUME_PATH):
        try:
            import pypdf
            reader = pypdf.PdfReader(RESUME_PATH)
            text = "\n".join([page.extract_text() for page in reader.pages if page.extract_text()])
            if text.strip():
                return text[:2000]
        except Exception:
            pass
    cand_name = os.getenv('CANDIDATE_NAME', 'Candidate')
    return f"{cand_name} | Computer Science Engineer | Full Stack Python, React.js, Node.js, Express, SQL, Git"

CANDIDATE_RESUME_TEXT = load_resume_text()
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

    # Persistent browser profile folder inside the project
    # This stores your login session permanently so you NEVER have to log in repeatedly!
    profile_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "browser_profile", "foundit")
    os.makedirs(profile_dir, exist_ok=True)
    options.add_argument(f"--user-data-dir={profile_dir}")

    if WEBDRIVER_MANAGER_AVAILABLE:
        service = EdgeService(EdgeChromiumDriverManager().install())
    elif EDGE_DRIVER_PATH:
        service = EdgeService(executable_path=EDGE_DRIVER_PATH)
    else:
        service = EdgeService()

    return webdriver.Edge(service=service, options=options)


def login_foundit(driver):
    """Log in to Foundit.in: clicks 'Login via Password', fills credentials, and verifies login."""
    logger.info("Opening Foundit.in login page...")
    driver.get('https://www.foundit.in/rio/login')
    time.sleep(4)

    try:
        # Check if already logged in (redirected to seeker dashboard or profile)
        if "login" not in driver.current_url.lower():
            logger.info("✓ Already logged in to Foundit.")
            return

        # 1. Click "Login via Password" tab
        logger.info("Clicking 'Login via Password'...")
        pwd_tabs = driver.find_elements(By.XPATH, "//*[contains(text(),'Login via Password')]")
        if pwd_tabs:
            driver.execute_script("arguments[0].click();", pwd_tabs[0])
            time.sleep(2)

        # 2. Fill Email ID / Phone Number into #userName
        uname = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "userName"))
        )
        uname.click()
        uname.clear()
        uname.send_keys(FOUNDIT_EMAIL)
        time.sleep(1)

        # 3. Fill Password into #password
        pwd = driver.find_element(By.ID, "password")
        pwd.click()
        pwd.clear()
        pwd.send_keys(FOUNDIT_PASSWORD)
        time.sleep(1)

        # 4. Submit form
        submit_btn = driver.find_element(By.ID, "loginSubmit")
        driver.execute_script("arguments[0].removeAttribute('disabled');", submit_btn)
        driver.execute_script("arguments[0].click();", submit_btn)
        logger.info("Credentials submitted.")

        # 5. Wait and verify redirect
        time.sleep(5)
        if "login" not in driver.current_url.lower():
            logger.info("✓ Foundit Login successful!")
        else:
            logger.info("ℹ️ If Foundit requires OTP verification or captcha, please complete it in the open browser window.")
            # Wait up to 25 seconds for user to complete OTP/captcha if needed
            for _ in range(25):
                if "login" not in driver.current_url.lower():
                    logger.info("✓ Login confirmed!")
                    break
                time.sleep(1)

    except Exception as e:
        logger.warning(f"Login automated step note: {e}. You can complete login in the open browser.")
        time.sleep(4)


def is_experience_suitable(exp_text, title=""):
    """
    Strict experience filter: Only allow 0-1 and 1-2 years max.
    Rejects Senior titles and anything > 2 years.
    """
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

    if min_exp > MAX_EXP_YEARS or max_exp > 3:
        return False
    return True


def contains_veto_skills(text):
    """Check if title or text has veto technologies."""
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


def evaluate_job(title, jd_text, experience="0-1 Yrs"):
    """
    Score job match from 0-100 using active Google Gemini AI (gemini-3.5-flash-lite).
    Compares the Job Title and Job Description with your profile and resume.
    """
    # 1. Call active Gemini model
    if GEMINI_API_KEY:
        try:
            import requests
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash-lite:generateContent?key={GEMINI_API_KEY}"
            prompt = f"""You are a strict technical job screener evaluating if a job fits an Entry-Level / Fresher Fullstack Developer.
Candidate Tech Stack: {', '.join(MY_TECH_STACK)}
Candidate Experience: 0-1 years (Fresher)
Candidate Resume Summary:
{CANDIDATE_RESUME_TEXT[:800]}

Rules:
- Must NOT require Senior, Lead, Architect, or >2 years experience.
- Must NOT require Java, Spring Boot, .NET, C#, PHP, C++ as core languages.
- Prefer Python, Django, React, Node.js, Express, JavaScript, SQL.

Job Title: {title}
Job Description:
{jd_text[:1500]}

Respond ONLY in valid JSON format:
{{"score": <integer 0-100>, "reason": "<one sentence explanation>"}}"""

            payload = {"contents": [{"parts": [{"text": prompt}]}]}
            res = requests.post(url, json=payload, timeout=6)
            if res.status_code == 200:
                raw_text = res.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
                if "```json" in raw_text:
                    raw_text = raw_text.split("```json")[1].split("```")[0].strip()
                elif "```" in raw_text:
                    raw_text = raw_text.split("```")[1].split("```")[0].strip()
                data = json.loads(raw_text)
                return int(data.get("score", 0)), f"Gemini AI: {data.get('reason', '')}"
        except Exception:
            pass

    # 2. NopeRi Stack Matcher Fallback (in case of offline/network issues)
    text_lower = (title + " " + jd_text[:2500]).lower()
    primary_skills = [
        "python", "javascript", "react", "node", "nodejs", "node.js",
        "sql", "django", "express", "full stack", "fullstack", "sde", "software engineer"
    ]
    matched = [s.title() for s in primary_skills if s in text_lower]

    base_score = 65
    if "full stack" in title.lower() or "fullstack" in title.lower() or "mern" in title.lower():
        base_score += 18
    elif "python" in title.lower() or "node" in title.lower() or "react" in title.lower():
        base_score += 15
    elif "software" in title.lower() or "sde" in title.lower() or "developer" in title.lower():
        base_score += 10

    overlap = len(set(matched))
    base_score += min(overlap * 3, 15)

    if "0-1" in experience or "0-2" in experience or "fresher" in text_lower:
        base_score += 5

    score = max(10, min(base_score, 95))
    matched_str = ", ".join(list(dict.fromkeys(matched))[:3]) if matched else "Web Developer"
    reason = f"NopeRi Stack Match: Found [{matched_str}] for {experience} (Score: {score})"

    return score, reason


def scrape_and_apply_foundit(driver):
    """Search and apply to jobs on Foundit."""
    applied = 0
    rejected = 0
    failed = 0

    for kw in KEYWORDS:
        if applied >= MAX_APPLICATIONS:
            break

        query = kw.replace(" ", "+")
        loc = LOCATION.replace(" ", "+") if LOCATION else "bangalore"
        search_url = f"https://www.foundit.in/srp/results?query={query}&locations={loc}"

        logger.info(f"\n🔍 Searching Foundit for: '{kw}' in '{LOCATION}'...")
        driver.get(search_url)
        time.sleep(5)

        # Scroll to load dynamic jobs
        for _ in range(3):
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight/2);")
            time.sleep(1)

        # Collect cards on Foundit with stale element protection
        card_count = len(driver.find_elements(By.CSS_SELECTOR, "div.cardContainer, div.srpResultCardContainer"))
        logger.info(f"Found {card_count} job cards on page.")

        for idx in range(card_count):
            if applied >= MAX_APPLICATIONS:
                break

            try:
                current_cards = driver.find_elements(By.CSS_SELECTOR, "div.cardContainer, div.srpResultCardContainer")
                if idx >= len(current_cards):
                    break
                card = current_cards[idx]
            except Exception:
                continue

            try:
                title_el = card.find_element(By.CSS_SELECTOR, "div.jobTitle, [class*='jobTitle']")
                title = title_el.text.strip()
            except (NoSuchElementException, StaleElementReferenceException):
                continue

            try:
                company_el = card.find_element(By.CSS_SELECTOR, "div.companyName, [class*='companyName']")
                company = company_el.text.strip()
            except (NoSuchElementException, StaleElementReferenceException):
                company = "Unknown Company"

            try:
                exp_el = card.find_element(By.CSS_SELECTOR, "div.bodyRow span.details, [class*='briefcase'] + span")
                exp = exp_el.text.strip()
            except (NoSuchElementException, StaleElementReferenceException):
                exp = "0-1 Yrs"

            # Direct link or card ID link
            card_id = card.get_attribute("id") or ""
            if card_id and card_id.isdigit():
                link = f"https://www.foundit.in/seeker/job-details?id={card_id}"
            else:
                try:
                    link_el = card.find_element(By.CSS_SELECTOR, "a[href*='job']")
                    link = link_el.get_attribute("href") or driver.current_url
                except Exception:
                    link = driver.current_url

            # 1. Experience & Senior check
            if not is_experience_suitable(exp, title):
                rej_reason = f"Exp > 2 yrs or Senior role ({exp})"
                print_job_box("REJECTED", company, title, exp, 0, rej_reason, link)
                record_job_status(company, title, exp, 0, "Rejected", rej_reason, link)
                rejected += 1
                continue

            # 2. Veto check
            veto = contains_veto_skills(title)
            if veto:
                rej_reason = f"Title has veto technology: {veto}"
                print_job_box("REJECTED", company, title, exp, 0, rej_reason, link)
                record_job_status(company, title, exp, 0, "Rejected", rej_reason, link)
                rejected += 1
                continue

            # 3. Stack match evaluation
            card_text = card.text
            score, reason = evaluate_job(title, card_text, exp)

            if score < MIN_SCORE:
                rej_reason = f"Score {score} < {MIN_SCORE}: {reason}"
                print_job_box("REJECTED", company, title, exp, score, rej_reason, link)
                record_job_status(company, title, exp, score, "Rejected", rej_reason, link)
                rejected += 1
                continue

            # 4. Apply on Foundit: Click card to open JD side panel, then trigger real #applyNowBtn
            applied_flag = False
            try:
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", card)
                time.sleep(1)
                
                # Click the card to open right panel
                driver.execute_script("arguments[0].click();", card)
                time.sleep(2)

                # Target the exact real Apply Now button: #applyNowBtn
                apply_btns = driver.find_elements(By.CSS_SELECTOR, "button#applyNowBtn, [id='applyNowBtn'], button.btn-apply")
                if apply_btns:
                    btn = apply_btns[0]
                    btn_text = btn.text.strip().lower()

                    if "applied" in btn_text:
                        logger.info(f"Already applied to {company} | {title}")
                        continue

                    # Click the real button directly
                    try:
                        btn.click()
                    except Exception:
                        driver.execute_script("arguments[0].click();", btn)

                    time.sleep(3)
                    # Verify real application: button text changes to 'Applied'
                    if "applied" in btn.text.strip().lower():
                        applied_flag = True
                    else:
                        # Check if application completed on page
                        body = driver.find_element(By.TAG_NAME, "body").text
                        if any(w in body.lower() for w in ["successfully applied", "application submitted", "applied"]):
                            applied_flag = True
            except Exception as e:
                logger.warning(f"Apply error: {e}")

            if applied_flag:
                applied += 1
                print_job_box("APPLIED", company, title, exp, score, reason, link)
                record_job_status(company, title, exp, score, "Applied", reason, link)
            else:
                failed += 1
                print_job_box("FAILED", company, title, exp, score, "No direct apply button", link)
                record_job_status(company, title, exp, score, "Failed", "No direct apply button", link)

    return applied, rejected, failed


def main():
    logger.info("=" * 50)
    logger.info("Foundit (Monster India) Auto-Apply Bot")
    logger.info("=" * 50)

    init_csv_report()
    driver = None
    try:
        driver = create_edge_driver()
        login_foundit(driver)
        applied, rejected, failed = scrape_and_apply_foundit(driver)

        logger.info("\n" + "=" * 50)
        logger.info("FOUNDIT APPLICATION SUMMARY")
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
            except Exception:
                pass


if __name__ == "__main__":
    main()
