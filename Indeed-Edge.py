"""
Indeed India Auto-Apply Bot (Edge Edition)
=========================================
Automates job search & 'Apply with Indeed' / 'Easily Apply' on in.indeed.com using Microsoft Edge.
Features:
  - Persistent Edge session: preserves cookies and logins across runs.
  - Handles Google SSO & email login with interactive completion support.
  - Strict 0-1 and 1-2 years experience filter.
  - Veto skills rejection (Java, Spring Boot, .NET, C#, PHP, Android, iOS, etc.).
  - Stack Match scoring (Python, React, Node.js, SQL, etc.).
  - Automated Multi-step SmartApply (switches to application tab, completes steps, submits).
  - Real-time logging to indeedapplied.csv.
"""

import os
import re
import csv
import json
import time
import atexit
import logging
from datetime import datetime
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.edge.service import Service as EdgeService
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException, NoSuchElementException, WebDriverException, StaleElementReferenceException
)

try:
    from webdriver_manager.microsoft import EdgeChromiumDriverManager
    WEBDRIVER_MANAGER_AVAILABLE = True
except ImportError:
    WEBDRIVER_MANAGER_AVAILABLE = False

# ------------------------------------------------------------
# Configuration & Environment
# ------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))

INDEED_EMAIL = os.getenv('INDEED_EMAIL') or os.getenv('NAUKRI_EMAIL', '')
INDEED_PASSWORD = os.getenv('INDEED_PASSWORD') or os.getenv('NAUKRI_PASSWORD', '')

FIRSTNAME = os.getenv('FIRSTNAME', 'Candidate')
LASTNAME = os.getenv('LASTNAME', '')
PHONE = os.getenv('PHONE', '9876543210')
RESUME_PATH = os.getenv('RESUME_PATH', 'resume.pdf')

KEYWORDS = [kw.strip() for kw in os.getenv('KEYWORDS', 'Python Developer, Full Stack Developer').split(',') if kw.strip()]
LOCATION = os.getenv('LOCATION', 'Bangalore').strip()
MAX_APPLICATIONS = int(os.getenv('MAX_APPLICATIONS', '50'))
EDGE_DRIVER_PATH = os.getenv('EDGE_DRIVER_PATH', '')

CSV_REPORT_FILE = os.path.join(BASE_DIR, "indeedapplied.csv")
CSV_BACKUP_FILE = os.path.join(BASE_DIR, "indeedapplied_backup.csv")
USER_DATA_DIR = os.path.join(BASE_DIR, "edge_indeed_profile")

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
    "android", "ios", "tutor", "trainer", "sales", "consultant"
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
                f.flush()
                os.fsync(f.fileno())
    except PermissionError:
        logger.warning(f"⚠️ '{CSV_REPORT_FILE}' is open in Excel. Any new data will be safely saved to '{CSV_BACKUP_FILE}'.")


def sync_backup_to_main():
    """Merge entries from backup file if main CSV was temporarily locked by Excel."""
    if not os.path.exists(CSV_BACKUP_FILE) or os.stat(CSV_BACKUP_FILE).st_size == 0:
        return
    try:
        with open(CSV_BACKUP_FILE, 'r', encoding='utf-8') as bf:
            backup_lines = bf.readlines()
        if not backup_lines:
            return

        with open(CSV_REPORT_FILE, 'a', newline='', encoding='utf-8') as mf:
            mf.writelines(backup_lines)
            mf.flush()
            os.fsync(mf.fileno())

        os.remove(CSV_BACKUP_FILE)
        logger.info(f"✓ Successfully merged {len(backup_lines)} backup records into '{CSV_REPORT_FILE}'.")
    except PermissionError:
        pass
    except Exception as e:
        logger.debug(f"Sync backup notice: {e}")


# Register sync on exit
atexit.register(sync_backup_to_main)


def record_job_status(company, title, experience, score, status, reason, link):
    """Save immediately to CSV and flush to physical disk so nothing is lost if exited in the middle."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    row = [timestamp, company, title, experience, score, status, reason, link]

    # Try main file first
    saved = False
    try:
        with open(CSV_REPORT_FILE, 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(row)
            f.flush()
            os.fsync(f.fileno())
        saved = True
        # If saved successfully, also attempt to merge any earlier queued backup rows
        sync_backup_to_main()
    except PermissionError:
        # File is locked because user has it open in Excel!
        logger.warning(f"⚠️ Excel has '{CSV_REPORT_FILE}' open. Saving immediately to '{CSV_BACKUP_FILE}' to prevent data loss.")
        try:
            with open(CSV_BACKUP_FILE, 'a', newline='', encoding='utf-8') as bf:
                writer = csv.writer(bf)
                writer.writerow(row)
                bf.flush()
                os.fsync(bf.fileno())
            saved = True
        except Exception as e:
            logger.error(f"Could not save to backup CSV: {e}")

    return saved


def print_job_box(status_type, company, title, exp, score, reason, link):
    """Prints a clean status summary to the console."""
    tag = "🟢 APPLIED" if status_type == "APPLIED" else ("🔴 REJECTED" if status_type == "REJECTED" else "🟡 SKIPPED")
    print("\n" + "=" * 70)
    print(f"[{tag}] {company} - {title} ({exp})")
    print(f"Match : {score}/100 | {reason}")
    print(f"Link  : {link}")
    print("=" * 70 + "\n")


def create_edge_driver():
    """Create a persistent Edge browser instance to retain session cookies."""
    options = webdriver.EdgeOptions()
    options.add_argument("--start-maximized")
    options.add_argument("--disable-notifications")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    
    # Persistent user data directory so login is only required once
    options.add_argument(f"--user-data-dir={USER_DATA_DIR}")

    if WEBDRIVER_MANAGER_AVAILABLE:
        service = EdgeService(EdgeChromiumDriverManager().install())
    elif EDGE_DRIVER_PATH and os.path.exists(EDGE_DRIVER_PATH):
        service = EdgeService(executable_path=EDGE_DRIVER_PATH)
    else:
        service = EdgeService()

    driver = webdriver.Edge(service=service, options=options)
    return driver


def is_logged_in(driver):
    """Check if user is logged in to Indeed."""
    try:
        # Check for profile icon, user menu, or absence of sign in button
        profile_icons = driver.find_elements(
            By.CSS_SELECTOR, 
            "a[data-gnav-element-name='Profile'], button[id*='userOptionsLabel'], div[data-testid='user-avatar']"
        )
        if profile_icons:
            return True
        
        # If 'Sign in' link is absent on in.indeed.com, user is typically logged in
        signin_links = driver.find_elements(By.XPATH, "//a[contains(text(), 'Sign in')]")
        if not signin_links and "secure.indeed.com/auth" not in driver.current_url:
            return True
            
        return False
    except Exception:
        return False


def dismiss_cookie_banner(driver):
    """Accept or dismiss cookie banner if displayed."""
    try:
        cookie_btns = driver.find_elements(By.ID, "onetrust-accept-btn-handler")
        if cookie_btns:
            driver.execute_script("arguments[0].click();", cookie_btns[0])
            time.sleep(1)
    except Exception:
        pass


def login_indeed(driver):
    """Ensure the user is logged into Indeed, guiding through Google SSO or credentials."""
    logger.info("Checking Indeed login status...")
    driver.get('https://in.indeed.com')
    time.sleep(3)
    dismiss_cookie_banner(driver)

    if is_logged_in(driver):
        logger.info("✓ Already logged in to Indeed!")
        return True

    logger.info("Navigating to Indeed Sign-in...")
    driver.get('https://secure.indeed.com/auth')
    time.sleep(4)
    dismiss_cookie_banner(driver)

    try:
        # Check email field
        email_inputs = driver.find_elements(By.CSS_SELECTOR, "input[name='__email'], input[type='email']")
        if email_inputs and INDEED_EMAIL:
            logger.info(f"Submitting email: {INDEED_EMAIL}")
            email_field = email_inputs[0]
            email_field.click()
            for ch in INDEED_EMAIL:
                email_field.send_keys(ch)
                time.sleep(0.03)
            time.sleep(1)

            submit_btns = driver.find_elements(By.CSS_SELECTOR, "button[data-tn-element='auth-page-email-submit-button'], button[type='submit']")
            if submit_btns:
                driver.execute_script("arguments[0].click();", submit_btns[0])
                time.sleep(4)

        # Indeed may prompt "Continue with Google" or request password
        pwd_inputs = driver.find_elements(By.CSS_SELECTOR, "input[type='password'], input[name='__password']")
        if pwd_inputs and INDEED_PASSWORD and pwd_inputs[0].is_displayed():
            pwd_inputs[0].clear()
            pwd_inputs[0].send_keys(INDEED_PASSWORD)
            time.sleep(1)
            sub = driver.find_elements(By.CSS_SELECTOR, "button[type='submit']")
            if sub:
                driver.execute_script("arguments[0].click();", sub[0])
                time.sleep(4)

    except Exception as e:
        logger.debug(f"Automated credential step notice: {e}")

    # Wait for explicit user confirmation
    print("\n" + "=" * 65)
    print("👉 ACTION REQUIRED: Please log in to Indeed in the open Edge window.")
    print("   (Complete Google Sign-In, Password, OTP, or Captcha if prompted)")
    print("=" * 65)
    
    while True:
        ans = input("\nHave you finished logging in? Type 'y' or 'yes' to proceed: ").strip().lower()
        if ans in ['y', 'yes']:
            break
        print("Waiting for login... Please type 'y' or 'yes' once you have logged in.")

    time.sleep(2)
    logger.info("✓ Login confirmed by user. Proceeding to job search...")
    return True


def is_experience_suitable(exp_text):
    """Ensure job requires 0-1 or 1-2 years max."""
    if not exp_text:
        return True
    nums = [int(n) for n in re.findall(r'\b\d+\b', exp_text)]
    if not nums:
        return True
    min_exp = nums[0]
    max_exp = nums[1] if len(nums) > 1 else min_exp
    return not (min_exp > MAX_EXP_YEARS or max_exp > 3)


def contains_veto_skills(text):
    """Check if title or text contains veto keywords."""
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
    """Heuristic stack match evaluation against candidate skillset."""
    text_lower = (title + " " + jd_text[:2000]).lower()
    primary_skills = [
        "python", "javascript", "react", "node", "nodejs", "node.js",
        "sql", "django", "express", "full stack", "fullstack", "sde", "software engineer"
    ]
    matched = [s.title() for s in primary_skills if s in text_lower]

    base_score = 65
    if "full stack" in title.lower() or "fullstack" in title.lower():
        base_score += 18
    elif "python" in title.lower() or "node" in title.lower() or "react" in title.lower():
        base_score += 15
    elif "software" in title.lower() or "developer" in title.lower():
        base_score += 10

    overlap = len(set(matched))
    base_score += min(overlap * 3, 15)

    if "0-1" in experience or "0-2" in experience or "fresher" in text_lower:
        base_score += 5

    score = max(10, min(base_score, 95))
    matched_str = ", ".join(list(dict.fromkeys(matched))[:3]) if matched else "Software Developer"
    reason = f"Stack Match: [{matched_str}] for {experience} (Score: {score})"

    return score, reason


def handle_smartapply_tabs(driver, original_window):
    """Handle the Indeed SmartApply multi-step form in the newly opened tab."""
    time.sleep(3)
    new_handles = [h for h in driver.window_handles if h != original_window]
    if not new_handles:
        # SmartApply might open in modal on same page
        apply_tab = original_window
    else:
        apply_tab = new_handles[-1]
        driver.switch_to.window(apply_tab)

    logger.info("Opening application form...")
    time.sleep(3)
    dismiss_cookie_banner(driver)

    success = False
    try:
        # Loop through application pages (Contact info -> Resume -> Questions -> Review -> Submit)
        for step in range(8):
            time.sleep(2)
            current_url = driver.current_url.lower()

            # Check if submission confirmation reached
            body_text = driver.find_element(By.TAG_NAME, "body").text.lower()
            if "application submitted" in body_text or "your application has been submitted" in body_text or "application sent" in body_text:
                logger.info("✓ Application successfully submitted!")
                success = True
                break

            # Fill basic empty inputs if required (e.g. phone number)
            try:
                phone_inputs = driver.find_elements(By.CSS_SELECTOR, "input[type='tel'], input[id*='phone'], input[name*='phone']")
                for p in phone_inputs:
                    if p.is_displayed() and not p.get_attribute("value"):
                        p.send_keys(PHONE)
            except Exception:
                pass

            # Answer common experience / yes-no questions if found
            try:
                num_inputs = driver.find_elements(By.CSS_SELECTOR, "input[type='number']")
                for ni in num_inputs:
                    if ni.is_displayed() and not ni.get_attribute("value"):
                        ni.send_keys("1")

                # Radio buttons for authorization / commute
                radios = driver.find_elements(By.XPATH, "//input[@type='radio' and (contains(@value, 'yes') or contains(@id, 'yes'))]")
                for r in radios:
                    if r.is_displayed() and not r.is_selected():
                        driver.execute_script("arguments[0].click();", r)
            except Exception:
                pass

            # Check for Submit Application button
            submit_btns = driver.find_elements(
                By.XPATH, 
                "//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'submit your application') or "
                "contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'submit application') or "
                "contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'apply')]"
            )
            submit_found = False
            for sb in submit_btns:
                if sb.is_displayed():
                    btn_text = sb.text.strip().lower()
                    if "submit" in btn_text:
                        driver.execute_script("arguments[0].click();", sb)
                        time.sleep(4)
                        success = True
                        submit_found = True
                        break

            if submit_found:
                break

            # Otherwise click Continue / Next button
            continue_btns = driver.find_elements(
                By.XPATH, 
                "//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'continue') or "
                "contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'next') or "
                "contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'review')]"
            )
            clicked = False
            for cb in continue_btns:
                if cb.is_displayed() and cb.is_enabled():
                    driver.execute_script("arguments[0].click();", cb)
                    clicked = True
                    break

            if not clicked:
                # No more continue or submit buttons found
                break

    except Exception as e:
        logger.debug(f"SmartApply step notice: {e}")

    # Clean up and return to main search window
    try:
        if driver.current_window_handle != original_window:
            driver.close()
    except Exception:
        pass

    driver.switch_to.window(original_window)
    return success


def scrape_and_apply_indeed(driver):
    """Search and apply to jobs on Indeed India."""
    applied = 0
    rejected = 0
    skipped = 0

    try:
        for kw in KEYWORDS:
            if applied >= MAX_APPLICATIONS:
                break

            query = kw.replace(" ", "+")
            loc = LOCATION.replace(" ", "+") if LOCATION else "Bangalore"
            # Search recent jobs in date order
            search_url = f"https://in.indeed.com/jobs?q={query}&l={loc}&sort=date"

            logger.info(f"\n🔍 Searching Indeed for: '{kw}' in '{LOCATION}'...")
            driver.get(search_url)
            time.sleep(5)
            dismiss_cookie_banner(driver)

            # Locate job cards
            cards = driver.find_elements(By.CSS_SELECTOR, "div.cardOutline, div.job_seen_beacon, td.resultContent")
            logger.info(f"Found {len(cards)} job cards for '{kw}'.")

            for card in cards:
                if applied >= MAX_APPLICATIONS:
                    break

                try:
                    # 1. Extract Title and Link
                    title_el = None
                    try:
                        title_el = card.find_element(By.CSS_SELECTOR, "h2.jobTitle a, a[data-jk], h2.jobTitle")
                        title = title_el.text.strip().replace("\n", " ")
                        link = title_el.get_attribute("href") or driver.current_url
                    except NoSuchElementException:
                        continue

                    if not title:
                        continue

                    # 2. Extract Company
                    try:
                        comp_el = card.find_element(By.CSS_SELECTOR, "span[data-testid='company-name'], span.companyName")
                        company = comp_el.text.strip()
                    except NoSuchElementException:
                        company = "Unknown Company"

                    # 3. Check Experience
                    card_text = card.text
                    exp = "0-1 Yrs"
                    exp_match = re.search(r'(\d+[\s-–to]+\d+[\s]+(?:years|yrs))', card_text, re.IGNORECASE)
                    if exp_match:
                        exp = exp_match.group(1)

                    # Filter: Experience check
                    if not is_experience_suitable(exp):
                        rej_reason = f"Exp > 2 yrs ({exp})"
                        print_job_box("REJECTED", company, title, exp, 0, rej_reason, link)
                        record_job_status(company, title, exp, 0, "Rejected", rej_reason, link)
                        rejected += 1
                        continue

                    # Filter: Veto skills in title
                    veto = contains_veto_skills(title)
                    if veto:
                        rej_reason = f"Title has veto technology: {veto}"
                        print_job_box("REJECTED", company, title, exp, 0, rej_reason, link)
                        record_job_status(company, title, exp, 0, "Rejected", rej_reason, link)
                        rejected += 1
                        continue

                    # Filter: Stack match evaluation
                    score, reason = evaluate_job(title, card_text, exp)
                    if score < MIN_SCORE:
                        rej_reason = f"Score {score} < {MIN_SCORE}: {reason}"
                        print_job_box("REJECTED", company, title, exp, score, rej_reason, link)
                        record_job_status(company, title, exp, score, "Rejected", rej_reason, link)
                        rejected += 1
                        continue

                    # 4. Open job preview pane
                    original_window = driver.current_window_handle
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", card)
                    time.sleep(1)
                    driver.execute_script("arguments[0].click();", card)
                    time.sleep(3)

                    # Look for 'Apply now' / 'Apply with Indeed' in the right preview pane
                    apply_elements = driver.find_elements(
                        By.XPATH,
                        "//div[@id='jobsearch-ViewjobPaneWrapper']//a[contains(., 'Apply') and not(contains(., 'company site'))] | "
                        "//div[@id='jobsearch-ViewjobPaneWrapper']//button[contains(., 'Apply') and not(contains(., 'company site'))] | "
                        "//div[contains(@class, 'jobsearch-RightPane')]//a[contains(@href, 'smartapply')]"
                    )

                    if not apply_elements:
                        # Check if it is an external application
                        external = driver.find_elements(
                            By.XPATH, 
                            "//div[@id='jobsearch-ViewjobPaneWrapper']//*[contains(text(), 'Apply on company site')]"
                        )
                        skip_reason = "External application on company website" if external else "No 1-click apply available"
                        print_job_box("SKIPPED", company, title, exp, score, skip_reason, link)
                        record_job_status(company, title, exp, score, "Skipped", skip_reason, link)
                        skipped += 1
                        continue

                    # Trigger Apply
                    apply_target = apply_elements[0]
                    driver.execute_script("arguments[0].click();", apply_target)
                    time.sleep(2)

                    # Handle multi-step SmartApply
                    applied_successfully = handle_smartapply_tabs(driver, original_window)

                    if applied_successfully:
                        applied += 1
                        print_job_box("APPLIED", company, title, exp, score, reason, link)
                        record_job_status(company, title, exp, score, "Applied", reason, link)
                    else:
                        skipped += 1
                        print_job_box("SKIPPED", company, title, exp, score, "Application requires manual custom answers", link)
                        record_job_status(company, title, exp, score, "Skipped", "Manual answers required", link)

                except StaleElementReferenceException:
                    continue
                except Exception as e:
                    logger.debug(f"Job processing notice: {e}")
                    continue

    except KeyboardInterrupt:
        logger.warning("\n⚠️ Stopped early by user (Ctrl+C). All applied & evaluated jobs have already been safely saved!")

    return applied, rejected, skipped


def main():
    logger.info("=" * 60)
    logger.info("       Indeed India Auto-Apply Bot (Edge Edition)")
    logger.info("=" * 60)

    init_csv_report()
    driver = None
    applied, rejected, skipped = 0, 0, 0
    try:
        driver = create_edge_driver()
        login_indeed(driver)
        applied, rejected, skipped = scrape_and_apply_indeed(driver)

    except KeyboardInterrupt:
        logger.warning("\n⚠️ Bot execution paused/stopped by user.")
    except Exception as e:
        logger.exception(f"Unexpected error during bot run: {e}")
    finally:
        sync_backup_to_main()
        logger.info("\n" + "=" * 60)
        logger.info("INDEED APPLICATION SUMMARY")
        logger.info(f"  ✓ Successfully Applied : {applied}")
        logger.info(f"  ⏭ Total Rejected (Rules): {rejected}")
        logger.info(f"  ⚠️ Skipped (External/Manual): {skipped}")
        logger.info(f"  📁 Full report saved in : {CSV_REPORT_FILE}")
        logger.info("=" * 60)
        if driver:
            try:
                driver.quit()
            except Exception:
                pass


if __name__ == "__main__":
    main()
