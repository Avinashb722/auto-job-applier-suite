import os
import csv
import json
import webbrowser
from datetime import datetime, date

BOT_DIR = os.path.dirname(os.path.abspath(__file__))
DASHBOARD_HTML_PATH = os.path.join(BOT_DIR, "dashboard.html")

PLATFORM_FILES = {
    "Naukri": "naukriapplied.csv",
    "LinkedIn": "linkedinapplied.csv",
    "Indeed": "indeedapplied.csv",
    "Foundit": "founditapplied.csv"
}

def parse_date_safely(date_str):
    """Parses date string into a datetime object for sorting."""
    date_str = (date_str or "").strip()
    if not date_str:
        return datetime.min
    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%d-%m-%Y %H:%M:%S",
        "%d/%m/%Y %H:%M:%S",
        "%Y-%m-%d",
        "%d-%m-%Y"
    ):
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            pass
    return datetime.min

def load_all_records():
    """Loads all records across all 4 platforms and calculates metrics."""
    records = []
    today = date.today()

    for platform, filename in PLATFORM_FILES.items():
        file_path = os.path.join(BOT_DIR, filename)
        if not os.path.exists(file_path):
            continue

        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                reader = csv.reader(f)
                header = next(reader, None)
                if not header:
                    continue

                for row in reader:
                    if not row or len(row) < 3:
                        continue

                    # Header expected: Timestamp,Company,Job Title,Experience,Score,Status,Reason,Job URL
                    ts_str = row[0].strip() if len(row) > 0 else ""
                    company = row[1].strip() if len(row) > 1 else "Unknown"
                    title = row[2].strip() if len(row) > 2 else "Unknown"
                    exp = row[3].strip() if len(row) > 3 else "-"
                    score_str = row[4].strip() if len(row) > 4 else "0"
                    status = row[5].strip() if len(row) > 5 else "Unknown"
                    reason = row[6].strip() if len(row) > 6 else ""
                    url = row[7].strip() if len(row) > 7 else ""

                    # Parse score
                    try:
                        score = int(float(score_str))
                    except Exception:
                        score = 0

                    dt = parse_date_safely(ts_str)
                    is_today = (dt.date() == today) if dt != datetime.min else False

                    # Normalize status
                    status_lower = status.lower()
                    if "applied" in status_lower:
                        norm_status = "Applied"
                    elif "fail" in status_lower:
                        norm_status = "Failed"
                    else:
                        norm_status = "Rejected"

                    records.append({
                        "platform": platform,
                        "timestamp": ts_str,
                        "datetime_iso": dt.isoformat() if dt != datetime.min else "",
                        "is_today": is_today,
                        "company": company,
                        "title": title,
                        "experience": exp,
                        "score": score,
                        "status": norm_status,
                        "reason": reason,
                        "url": url
                    })
        except Exception as e:
            print(f"Error loading {filename}: {e}")

    # Sort records: Today first, then most recent timestamp descending
    records.sort(
        key=lambda r: (1 if r["is_today"] else 0, parse_date_safely(r["timestamp"])),
        reverse=True
    )
    return records

def generate_dashboard_html(records):
    """Generates a self-contained modern HTML dashboard."""
    today_str = date.today().strftime("%B %d, %Y")
    now_time_str = datetime.now().strftime("%I:%M %p")

    # Metrics
    total_all = len(records)
    applied_all = sum(1 for r in records if r["status"] == "Applied")
    rejected_all = sum(1 for r in records if r["status"] == "Rejected")
    failed_all = sum(1 for r in records if r["status"] == "Failed")

    today_records = [r for r in records if r["is_today"]]
    total_today = len(today_records)
    applied_today = sum(1 for r in today_records if r["status"] == "Applied")
    rejected_today = sum(1 for r in today_records if r["status"] == "Rejected")
    failed_today = sum(1 for r in today_records if r["status"] == "Failed")

    # Platform counts
    platform_counts = {}
    for p in PLATFORM_FILES.keys():
        p_recs = [r for r in records if r["platform"] == p]
        platform_counts[p] = {
            "total": len(p_recs),
            "applied": sum(1 for r in p_recs if r["status"] == "Applied"),
            "today_applied": sum(1 for r in p_recs if r["status"] == "Applied" and r["is_today"])
        }

    records_json = json.dumps(records)

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Multi-Platform Job Application Dashboard</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@500;700&display=swap" rel="stylesheet">
  <style>
    :root {{
      --bg-dark: #0b0f19;
      --card-bg: #111827;
      --card-border: #1f2937;
      --text-main: #f9fafb;
      --text-muted: #9ca3af;
      --accent-blue: #3b82f6;
      --emerald-500: #10b981;
      --emerald-bg: rgba(16, 185, 129, 0.12);
      --amber-500: #f59e0b;
      --amber-bg: rgba(245, 158, 11, 0.12);
      --rose-500: #f43f5e;
      --rose-bg: rgba(244, 63, 94, 0.12);
      --purple-500: #8b5cf6;
    }}

    * {{
      box-sizing: border-box;
      margin: 0;
      padding: 0;
    }}

    body {{
      font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
      background: var(--bg-dark);
      color: var(--text-main);
      padding: 24px;
      min-height: 100vh;
    }}

    .container {{
      max-width: 1440px;
      margin: 0 auto;
    }}

    /* Header */
    .header {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 16px;
      margin-bottom: 24px;
      padding-bottom: 20px;
      border-bottom: 1px solid var(--card-border);
    }}

    .header-left h1 {{
      font-size: 26px;
      font-weight: 800;
      letter-spacing: -0.5px;
      display: flex;
      align-items: center;
      gap: 10px;
    }}

    .header-left p {{
      color: var(--text-muted);
      font-size: 14px;
      margin-top: 4px;
    }}

    .header-actions {{
      display: flex;
      gap: 12px;
      align-items: center;
    }}

    .btn {{
      padding: 10px 18px;
      border-radius: 8px;
      font-weight: 600;
      font-size: 13px;
      cursor: pointer;
      border: 1px solid transparent;
      display: inline-flex;
      align-items: center;
      gap: 8px;
      text-decoration: none;
      transition: all 0.15s ease;
    }}

    .btn-primary {{
      background: #2563eb;
      color: #fff;
    }}
    .btn-primary:hover {{
      background: #1d4ed8;
    }}

    .btn-secondary {{
      background: #1f2937;
      color: #e5e7eb;
      border-color: #374151;
    }}
    .btn-secondary:hover {{
      background: #374151;
    }}

    /* Metrics Grid */
    .metrics-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 16px;
      margin-bottom: 28px;
    }}

    .metric-card {{
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 12px;
      padding: 18px;
      position: relative;
      overflow: hidden;
    }}

    .metric-card::before {{
      content: '';
      position: absolute;
      top: 0;
      left: 0;
      right: 0;
      height: 3px;
      background: var(--card-border);
    }}

    .metric-card.today-applied::before {{ background: var(--emerald-500); }}
    .metric-card.total-applied::before {{ background: var(--accent-blue); }}
    .metric-card.total-rejected::before {{ background: var(--rose-500); }}
    .metric-card.total-failed::before {{ background: var(--amber-500); }}

    .metric-label {{
      font-size: 12px;
      font-weight: 600;
      color: var(--text-muted);
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }}

    .metric-val {{
      font-size: 30px;
      font-weight: 800;
      font-family: 'JetBrains Mono', monospace;
      margin-top: 6px;
      display: flex;
      align-items: baseline;
      gap: 8px;
    }}

    .metric-sub {{
      font-size: 12px;
      color: var(--text-muted);
      margin-top: 4px;
    }}

    /* Platform Tabs */
    .platform-tabs {{
      display: flex;
      gap: 8px;
      margin-bottom: 20px;
      overflow-x: auto;
      padding-bottom: 6px;
      border-bottom: 1px solid var(--card-border);
    }}

    .tab-btn {{
      padding: 10px 18px;
      border-radius: 8px 8px 0 0;
      background: transparent;
      border: none;
      color: var(--text-muted);
      font-size: 14px;
      font-weight: 600;
      cursor: pointer;
      display: flex;
      align-items: center;
      gap: 8px;
      position: relative;
      transition: all 0.2s;
    }}

    .tab-btn:hover {{
      color: #fff;
      background: rgba(255, 255, 255, 0.04);
    }}

    .tab-btn.active {{
      color: #fff;
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-bottom: 1px solid var(--card-bg);
      margin-bottom: -1px;
    }}

    .tab-badge {{
      font-size: 11px;
      padding: 2px 7px;
      border-radius: 12px;
      background: #1f2937;
      color: #d1d5db;
    }}

    .tab-btn.active .tab-badge {{
      background: #2563eb;
      color: #fff;
    }}

    /* Control Bar */
    .control-bar {{
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 12px;
      padding: 16px;
      margin-bottom: 20px;
      display: flex;
      flex-wrap: wrap;
      justify-content: space-between;
      align-items: center;
      gap: 14px;
    }}

    .filter-group {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      align-items: center;
    }}

    .filter-pill {{
      padding: 7px 14px;
      border-radius: 20px;
      font-size: 13px;
      font-weight: 600;
      cursor: pointer;
      background: #1f2937;
      border: 1px solid #374151;
      color: #9ca3af;
      transition: all 0.15s;
    }}

    .filter-pill:hover {{
      color: #fff;
      border-color: #4b5563;
    }}

    .filter-pill.active {{
      background: #2563eb;
      border-color: #2563eb;
      color: #fff;
    }}

    .filter-pill.active.pill-applied {{
      background: var(--emerald-500);
      border-color: var(--emerald-500);
    }}
    .filter-pill.active.pill-failed {{
      background: var(--amber-500);
      border-color: var(--amber-500);
    }}
    .filter-pill.active.pill-rejected {{
      background: var(--rose-500);
      border-color: var(--rose-500);
    }}

    .search-box {{
      position: relative;
      min-width: 280px;
      flex-grow: 1;
      max-width: 450px;
    }}

    .search-input {{
      width: 100%;
      padding: 9px 14px 9px 36px;
      background: #0b0f19;
      border: 1px solid #374151;
      border-radius: 8px;
      color: #fff;
      font-size: 13px;
      outline: none;
    }}
    .search-input:focus {{
      border-color: #2563eb;
    }}

    .search-icon {{
      position: absolute;
      left: 12px;
      top: 50%;
      transform: translateY(-50%);
      color: #6b7280;
      pointer-events: none;
    }}

    /* Table */
    .table-container {{
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 12px;
      overflow-x: auto;
    }}

    table {{
      width: 100%;
      border-collapse: collapse;
      text-align: left;
      font-size: 13px;
    }}

    thead th {{
      padding: 14px 16px;
      background: #131d2e;
      color: #9ca3af;
      font-weight: 700;
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0.6px;
      border-bottom: 1px solid var(--card-border);
      white-space: nowrap;
    }}

    tbody tr {{
      border-bottom: 1px solid #1a2234;
      transition: background 0.1s;
    }}

    tbody tr:hover {{
      background: rgba(255, 255, 255, 0.02);
    }}

    tbody tr.row-today {{
      background: rgba(16, 185, 129, 0.03);
    }}

    tbody td {{
      padding: 14px 16px;
      vertical-align: middle;
    }}

    /* Badges */
    .badge {{
      display: inline-flex;
      align-items: center;
      gap: 5px;
      padding: 4px 10px;
      border-radius: 6px;
      font-size: 11px;
      font-weight: 700;
      letter-spacing: 0.3px;
      white-space: nowrap;
    }}

    .badge-today {{
      background: rgba(16, 185, 129, 0.2);
      color: #34d399;
      border: 1px solid rgba(16, 185, 129, 0.4);
      margin-left: 6px;
      padding: 2px 6px;
      border-radius: 4px;
      font-size: 10px;
    }}

    .badge-applied {{
      background: var(--emerald-bg);
      color: #34d399;
      border: 1px solid rgba(16, 185, 129, 0.3);
    }}

    .badge-failed {{
      background: var(--amber-bg);
      color: #fbbf24;
      border: 1px solid rgba(245, 158, 11, 0.3);
    }}

    .badge-rejected {{
      background: rgba(156, 163, 175, 0.1);
      color: #9ca3af;
      border: 1px solid rgba(156, 163, 175, 0.2);
    }}

    .platform-pill {{
      padding: 3px 8px;
      border-radius: 4px;
      font-size: 11px;
      font-weight: 700;
    }}
    .platform-linkedin {{ background: rgba(14, 118, 168, 0.2); color: #38bdf8; border: 1px solid rgba(14, 118, 168, 0.4); }}
    .platform-naukri {{ background: rgba(37, 99, 235, 0.2); color: #60a5fa; border: 1px solid rgba(37, 99, 235, 0.4); }}
    .platform-indeed {{ background: rgba(99, 102, 241, 0.2); color: #a5b4fc; border: 1px solid rgba(99, 102, 241, 0.4); }}
    .platform-foundit {{ background: rgba(168, 85, 247, 0.2); color: #c084fc; border: 1px solid rgba(168, 85, 247, 0.4); }}

    .score-badge {{
      font-family: 'JetBrains Mono', monospace;
      font-weight: 700;
      padding: 3px 8px;
      border-radius: 4px;
      font-size: 12px;
    }}
    .score-high {{ background: rgba(16, 185, 129, 0.15); color: #10b981; }}
    .score-mid {{ background: rgba(245, 158, 11, 0.15); color: #f59e0b; }}
    .score-low {{ background: rgba(244, 63, 94, 0.15); color: #f43f5e; }}

    .link-btn {{
      color: #38bdf8;
      text-decoration: none;
      font-weight: 600;
      display: inline-flex;
      align-items: center;
      gap: 4px;
      padding: 5px 10px;
      border-radius: 6px;
      background: rgba(56, 189, 248, 0.08);
      transition: background 0.15s;
    }}
    .link-btn:hover {{
      background: rgba(56, 189, 248, 0.18);
      text-decoration: underline;
    }}

    .empty-state {{
      text-align: center;
      padding: 60px 20px;
      color: var(--text-muted);
    }}
  </style>
</head>
<body>
  <div class="container">
    <!-- Header -->
    <div class="header">
      <div class="header-left">
        <h1>🚀 Auto-Apply Live Dashboard</h1>
        <p>Sorted by <strong>Today Applied First</strong> • Real-time logs across LinkedIn, Naukri, Indeed & Foundit</p>
      </div>
      <div class="header-actions">
        <span style="font-size: 12px; color: #9ca3af;">Last updated: {now_time_str} ({today_str})</span>
        <button onclick="location.reload()" class="btn btn-secondary">🔄 Refresh Data</button>
      </div>
    </div>

    <!-- Metrics Grid -->
    <div class="metrics-grid">
      <div class="metric-card today-applied">
        <div class="metric-label">⚡ Today Applied</div>
        <div class="metric-val" style="color: #34d399;">{applied_today} <span style="font-size: 15px; font-weight: 500; color: #9ca3af;">/ {total_today} processed</span></div>
        <div class="metric-sub">{failed_today} failed modals • {rejected_today} skipped</div>
      </div>

      <div class="metric-card total-applied">
        <div class="metric-label">🎯 Total Applied (All Time)</div>
        <div class="metric-val" style="color: #60a5fa;">{applied_all} <span style="font-size: 15px; font-weight: 500; color: #9ca3af;">/ {total_all}</span></div>
        <div class="metric-sub">Across all 4 active platforms</div>
      </div>

      <div class="metric-card total-rejected">
        <div class="metric-label">🛡️ Filtered / Vetoed</div>
        <div class="metric-val" style="color: #f43f5e;">{rejected_all}</div>
        <div class="metric-sub">Exp > 2 yrs or Senior veto</div>
      </div>

      <div class="metric-card total-failed">
        <div class="metric-label">⚠️ Failed / Needs Review</div>
        <div class="metric-val" style="color: #fbbf24;">{failed_all}</div>
        <div class="metric-sub">Complex modals or already applied</div>
      </div>
    </div>

    <!-- Platform Tabs -->
    <div class="platform-tabs">
      <button class="tab-btn active" onclick="switchPlatform('all', this)">
        🌐 All Platforms <span class="tab-badge">{total_all}</span>
      </button>
      <button class="tab-btn" onclick="switchPlatform('LinkedIn', this)">
        💼 LinkedIn <span class="tab-badge">{platform_counts['LinkedIn']['total']}</span>
      </button>
      <button class="tab-btn" onclick="switchPlatform('Naukri', this)">
        🔷 Naukri <span class="tab-badge">{platform_counts['Naukri']['total']}</span>
      </button>
      <button class="tab-btn" onclick="switchPlatform('Indeed', this)">
        🎯 Indeed <span class="tab-badge">{platform_counts['Indeed']['total']}</span>
      </button>
      <button class="tab-btn" onclick="switchPlatform('Foundit', this)">
        🟣 Foundit <span class="tab-badge">{platform_counts['Foundit']['total']}</span>
      </button>
    </div>

    <!-- Filter & Search Controls -->
    <div class="control-bar">
      <div class="filter-group">
        <span style="font-size: 12px; font-weight: 600; color: #6b7280; text-transform: uppercase;">Status:</span>
        <button class="filter-pill active" onclick="setStatusFilter('ALL', this)">All</button>
        <button class="filter-pill pill-applied" onclick="setStatusFilter('Applied', this)">✓ Applied ({applied_all})</button>
        <button class="filter-pill pill-rejected" onclick="setStatusFilter('Rejected', this)">✕ Rejected ({rejected_all})</button>
        <button class="filter-pill pill-failed" onclick="setStatusFilter('Failed', this)">⚠️ Failed ({failed_all})</button>
      </div>

      <div class="filter-group">
        <span style="font-size: 12px; font-weight: 600; color: #6b7280; text-transform: uppercase;">Date:</span>
        <button class="filter-pill active" onclick="setDateFilter('ALL', this)">All Time</button>
        <button class="filter-pill" onclick="setDateFilter('TODAY', this)">⚡ Today Only ({total_today})</button>
      </div>

      <div class="search-box">
        <span class="search-icon">🔍</span>
        <input type="text" id="searchInput" class="search-input" placeholder="Search company, job title, stack..." oninput="renderTable()">
      </div>
    </div>

    <!-- Results Table -->
    <div class="table-container">
      <table>
        <thead>
          <tr>
            <th>Timestamp</th>
            <th>Platform</th>
            <th>Company</th>
            <th>Job Title</th>
            <th>Experience</th>
            <th>Score</th>
            <th>Status</th>
            <th>Reason / Evaluation</th>
            <th>Action</th>
          </tr>
        </thead>
        <tbody id="tableBody">
          <!-- Rendered via JavaScript -->
        </tbody>
      </table>
      <div id="emptyState" class="empty-state" style="display: none;">
        <h3>No matching applications found</h3>
        <p style="margin-top: 6px;">Try adjusting your filters or search keywords.</p>
      </div>
    </div>
  </div>

  <script>
    const ALL_RECORDS = {records_json};

    let currentPlatform = 'all';
    let currentStatus = 'ALL';
    let currentDateFilter = 'ALL';

    function switchPlatform(platform, el) {{
      currentPlatform = platform;
      document.querySelectorAll('.platform-tabs .tab-btn').forEach(btn => btn.classList.remove('active'));
      el.classList.add('active');
      renderTable();
    }}

    function setStatusFilter(status, el) {{
      currentStatus = status;
      el.parentElement.querySelectorAll('.filter-pill').forEach(pill => pill.classList.remove('active'));
      el.classList.add('active');
      renderTable();
    }}

    function setDateFilter(dateFilter, el) {{
      currentDateFilter = dateFilter;
      el.parentElement.querySelectorAll('.filter-pill').forEach(pill => pill.classList.remove('active'));
      el.classList.add('active');
      renderTable();
    }}

    function renderTable() {{
      const query = (document.getElementById('searchInput').value || '').toLowerCase().trim();
      const tbody = document.getElementById('tableBody');
      const emptyState = document.getElementById('emptyState');
      tbody.innerHTML = '';

      const filtered = ALL_RECORDS.filter(r => {{
        // Platform filter
        if (currentPlatform !== 'all' && r.platform !== currentPlatform) return false;

        // Status filter
        if (currentStatus !== 'ALL' && r.status !== currentStatus) return false;

        // Date filter
        if (currentDateFilter === 'TODAY' && !r.is_today) return false;

        // Search query
        if (query) {{
          const matchStr = (r.company + ' ' + r.title + ' ' + r.reason + ' ' + r.platform).toLowerCase();
          if (!matchStr.includes(query)) return false;
        }}

        return true;
      }});

      if (filtered.length === 0) {{
        emptyState.style.display = 'block';
        return;
      }} else {{
        emptyState.style.display = 'none';
      }}

      // Display up to 500 rows for smooth UI
      filtered.slice(0, 500).forEach(r => {{
        const tr = document.createElement('tr');
        if (r.is_today) tr.classList.add('row-today');

        // Status badge class
        let statusBadge = '';
        if (r.status === 'Applied') {{
          statusBadge = '<span class="badge badge-applied">✓ Applied</span>';
        }} else if (r.status === 'Failed') {{
          statusBadge = '<span class="badge badge-failed">⚠️ Failed</span>';
        }} else {{
          statusBadge = '<span class="badge badge-rejected">✕ Rejected</span>';
        }}

        // Platform class
        const pClass = 'platform-' + r.platform.toLowerCase();
        const pBadge = `<span class="platform-pill ${{pClass}}">${{r.platform}}</span>`;

        // Score class
        let scoreClass = 'score-low';
        if (r.score >= 70) scoreClass = 'score-high';
        else if (r.score >= 50) scoreClass = 'score-mid';
        const scoreBadge = `<span class="score-badge ${{scoreClass}}">${{r.score}}/100</span>`;

        // Today pill
        const todayTag = r.is_today ? '<span class="badge-today">TODAY</span>' : '';

        // Clean link
        const linkBtn = r.url ? `<a href="${{r.url}}" target="_blank" rel="noopener noreferrer" class="link-btn">View ↗</a>` : '-';

        tr.innerHTML = `
          <td style="white-space: nowrap; font-family: 'JetBrains Mono', monospace; font-size: 12px; color: #9ca3af;">
            ${{r.timestamp}} ${{todayTag}}
          </td>
          <td>${{pBadge}}</td>
          <td style="font-weight: 600; color: #fff;">${{r.company}}</td>
          <td>${{r.title}}</td>
          <td style="white-space: nowrap; color: #9ca3af;">${{r.experience}}</td>
          <td>${{scoreBadge}}</td>
          <td>${{statusBadge}}</td>
          <td style="color: #9ca3af; max-width: 320px; font-size: 12px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${{r.reason}}">
            ${{r.reason || '-'}}
          </td>
          <td>${{linkBtn}}</td>
        `;
        tbody.appendChild(tr);
      }});
    }}

    // Initial render and hash check
    window.addEventListener('DOMContentLoaded', () => {{
      const hash = window.location.hash.replace('#', '').toLowerCase();
      if (hash) {{
        const tabs = document.querySelectorAll('.platform-tabs .tab-btn');
        tabs.forEach(btn => {{
          if (btn.textContent.toLowerCase().includes(hash)) {{
            const pName = hash === 'all' ? 'all' : (hash.charAt(0).toUpperCase() + hash.slice(1));
            switchPlatform(pName, btn);
          }}
        }});
      }} else {{
        renderTable();
      }}
    }});
  </script>
</body>
</html>
"""
    with open(DASHBOARD_HTML_PATH, "w", encoding="utf-8") as f:
        f.write(html_content)

    return DASHBOARD_HTML_PATH

def main(open_browser=True, default_platform=None):
    import sys
    if len(sys.argv) > 1 and not default_platform:
        default_platform = sys.argv[1].strip().lower()

    print("Loading application records across all platforms...")
    records = load_all_records()
    print(f"Loaded {len(records)} records.")

    html_path = generate_dashboard_html(records)
    print(f"Generated dashboard: {html_path}")

    if open_browser:
        target_url = "file://" + os.path.abspath(html_path)
        if default_platform and default_platform != "all":
            target_url += f"#{default_platform}"
        webbrowser.open(target_url)
        print(f"Opened dashboard in default browser: {target_url}")

if __name__ == "__main__":
    main()
