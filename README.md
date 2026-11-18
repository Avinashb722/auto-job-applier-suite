# Auto Job Applier Suite 🚀

> Autonomous, multi-platform job application bot suite supporting **LinkedIn Easy Apply**, **Naukri**, **Indeed**, and **Foundit** with Microsoft Edge automation, Gemini AI resume match scoring, dynamic question answering, and a real-time web dashboard.

---

## ✨ Features

- **Multi-Platform Support**:
  - 💼 **LinkedIn**: Easy Apply automation, entry-level & fresh posting filter, multi-step modal question answering.
  - 🔷 **Naukri**: Single-click apply, dynamic chatbot questionnaire drawer answering, quota monitoring.
  - 🎯 **Indeed**: Automated apply flows with smart input filling.
  - 🟣 **Foundit**: Monster India search, filter, and application automation.
- **Two-Tier Intelligent Evaluation**:
  - **Tier 1 (Fast Rule Screening)**: Experience requirement parser (filters >2 yrs), senior/lead veto checks, and veto technology filters.
  - **Tier 2 (Gemini AI Match)**: Evaluates candidate resume against the exact Job Description (JD) and scores candidate fit from 0 to 100.
- **Dynamic Question Answering**:
  - Automatically answers modal questions (Notice period, CTC, experience, tools, graduation year, degree, CGPA, short answers).
  - Unfamiliar questions are automatically answered via Gemini AI using the candidate's resume.
- **Live Web Dashboard (`dashboard.html`)**:
  - Sorted with **Today Applied First** by default.
  - Real-time status filters: `Applied` (Green), `Rejected / Skipped` (Slate), and `Failed` (Amber).
  - Instant live search and direct `View ↗` links to job postings.
- **One-Click Desktop Launcher (`Job-AutoApply-Suite.bat`)**:
  - Interactive console launcher to run any single platform, run all platforms sequentially, or inspect the web dashboard.
- **Privacy & Security First**:
  - All personal details, passwords, cookies, and resumes are kept strictly local in `.env` and `.gitignore`.

---

## 🛠️ Installation & Setup

### 1. Clone the Repository
```bash
git clone https://github.com/Avinashb722/auto-job-applier-suite.git
cd auto-job-applier-suite
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Configure Environment Variables
Copy `.env.example` to `.env` and configure your settings:
```bash
cp .env.example .env
```
Fill in your details in `.env`:
- `GEMINI_API_KEY`: Your Google Gemini API key for AI scoring and question answering.
- `NAUKRI_EMAIL` & `NAUKRI_PASSWORD`: Your credentials (stored locally only).
- `RESUME_PATH`: Path to your local `resume.pdf`.
- `KEYWORDS` & `LOCATION`: Your target job titles and city (e.g. `Python Developer`, `Bangalore`).

---

## 🚀 Usage

### Option A: Interactive Launcher (Recommended)
Double-click `Job-AutoApply-Suite.bat` or run:
```cmd
Job-AutoApply-Suite.bat
```
Select a menu option:
* `[1]` Run Naukri Bot
* `[2]` Run LinkedIn Easy Apply Bot
* `[3]` Run Indeed Bot
* `[4]` Run Foundit Bot
* `[5]` Run All Platforms Sequentially
* `[6]` Open Web Dashboard

### Option B: Run Individual Bots
```bash
# Run LinkedIn Bot
python LinkedIn-Edge.py

# Run Naukri Bot
python Naukri-Edge.py

# Run Foundit Bot
python Foundit-Edge.py

# Run Indeed Bot
python Indeed-Edge.py

# Open Web Dashboard
python dashboard.py
```

---

## 📊 Live Application Dashboard

Run `python dashboard.py` at any time to open `dashboard.html` in your default browser:
* **All Platforms Tab**: Consolidated view across LinkedIn, Naukri, Indeed, and Foundit.
* **Platform Specific Tabs**: Filter applications per portal.
* **Status Badges**: Filter by `Applied`, `Rejected`, or `Failed`.
* **Date Filters**: View `Today Only` or `All Time`.

---

## 🔒 Security & Privacy Notice
* **Never commit `.env`** or `browser_profile/` to git.
* All session cookies, credentials, application history CSV files, and resume PDFs are excluded via `.gitignore`.

---

## 📄 License
MIT License. Created for educational and personal automation purposes.
