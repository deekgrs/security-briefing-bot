"""Build the daily security briefing as HTML, Markdown and JSON."""
import html
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from string import Template

from summarize import SEVERITIES, analyze_all

OUTPUT_DIR = Path("docs")
COLORS = {"Critical": "#dc2626", "High": "#ea580c", "Medium": "#ca8a04",
          "Low": "#2563eb", "Info": "#6b7280"}


def e(text):
    """Escape text so scraped content can never run as code in the page."""
    return html.escape(str(text), quote=True)


def safe_link(url):
    """Allow only web links; blocks javascript: and other dangerous schemes."""
    return url if url.startswith(("https://", "http://")) else "#"


def sort_by_severity(stories):
    rank = {sev: i for i, sev in enumerate(SEVERITIES)}
    return sorted(stories, key=lambda s: rank.get(s["severity"], len(SEVERITIES)))


PAGE = Template("""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Security Briefing - $date</title>
<style>
  :root { --bg:#f8fafc; --card:#ffffff; --text:#0f172a; --muted:#64748b; --line:#e2e8f0; }
  @media (prefers-color-scheme: dark) {
    :root { --bg:#0b1120; --card:#111827; --text:#e5e7eb; --muted:#94a3b8; --line:#1f2937; }
  }
  * { box-sizing: border-box; }
  body { margin:0; background:var(--bg); color:var(--text);
         font-family: system-ui, -apple-system, "Segoe UI", sans-serif; line-height:1.5; }
  main { max-width:860px; margin:0 auto; padding:32px 16px 64px; }
  header h1 { margin:0; font-size:28px; }
  header p { margin:4px 0 0; color:var(--muted); }
  .stats { display:grid; grid-template-columns:repeat(5,1fr); gap:8px; margin:24px 0; }
  .stat { background:var(--card); border:1px solid var(--line); border-radius:10px;
          padding:12px; text-align:center; font-size:13px; color:var(--muted); }
  .stat .num { display:block; font-size:24px; font-weight:700; }
  .card { background:var(--card); border:1px solid var(--line); border-left:5px solid;
          border-radius:10px; padding:16px 18px; margin-bottom:14px; }
  .meta { display:flex; flex-wrap:wrap; gap:8px; align-items:center; font-size:12px; color:var(--muted); }
  .sev { color:#fff; font-weight:700; padding:2px 8px; border-radius:999px; }
  .card h2 { font-size:18px; margin:8px 0 6px; }
  .card h2 a { color:inherit; text-decoration:none; }
  .card h2 a:hover { text-decoration:underline; }
  .card p { margin:0 0 10px; }
  .tags { display:flex; flex-wrap:wrap; gap:6px; }
  .tag { font-size:12px; border:1px solid var(--line); border-radius:6px; padding:1px 7px; color:var(--muted); }
  a.cve { color:#dc2626; text-decoration:none; font-weight:600; }
  footer { margin-top:32px; font-size:13px; color:var(--muted); }
  @media (max-width:600px) { .stats { grid-template-columns:repeat(3,1fr); } }
</style>
</head>
<body>
<main>
  <header>
    <h1>Daily Security Briefing</h1>
    <p>$date &middot; $count stories, summarized and triaged by AI</p>
  </header>
  <section class="stats">$stats</section>
  $cards
  <footer>Generated automatically from public RSS feeds. AI summaries can contain
  errors; follow the links for the original reporting.</footer>
</main>
</body>
</html>
""")


def render_html(stories, date_str):
    counts = Counter(s["severity"] for s in stories)
    stats = "".join(
        f'<div class="stat"><span class="num" style="color:{COLORS[sev]}">'
        f'{counts.get(sev, 0)}</span>{sev}</div>'
        for sev in SEVERITIES
    )
    cards = []
    for s in stories:
        color = COLORS.get(s["severity"], COLORS["Info"])
        # CVE IDs were validated against the CVE format, so they are safe in a URL
        cves = "".join(
            f'<a class="tag cve" href="https://nvd.nist.gov/vuln/detail/{c}" '
            f'target="_blank" rel="noopener noreferrer">{c}</a>'
            for c in s["cves"]
        )
        affected = "".join(f'<span class="tag">{e(a)}</span>' for a in s["affected"])
        cards.append(f"""
  <article class="card" style="border-left-color:{color}">
    <div class="meta">
      <span class="sev" style="background:{color}">{e(s['severity'])}</span>
      <span>{e(s['category'])}</span><span>&middot;</span><span>{e(s['source'])}</span>
    </div>
    <h2><a href="{e(safe_link(s['link']))}" target="_blank" rel="noopener noreferrer">{e(s['title'])}</a></h2>
    <p>{e(s['summary'])}</p>
    <div class="tags">{cves}{affected}</div>
  </article>""")
    return PAGE.substitute(date=e(date_str), count=len(stories),
                           stats=stats, cards="".join(cards))


def render_markdown(stories, date_str):
    lines = [f"# Daily Security Briefing - {date_str}", ""]
    for s in stories:
        lines.append(f"## [{s['severity']}] {s['title']}")
        lines.append(f"*{s['category']} · {s['source']}* - [Read more]({safe_link(s['link'])})")
        lines.append("")
        lines.append(s["summary"])
        if s["cves"]:
            lines.append(f"\n**CVEs:** {', '.join(s['cves'])}")
        lines.append("")
    return "\n".join(lines)


def main():
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    stories = sort_by_severity(analyze_all())

    (OUTPUT_DIR / "briefings").mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "data").mkdir(parents=True, exist_ok=True)

    (OUTPUT_DIR / "index.html").write_text(render_html(stories, date_str), encoding="utf-8")
    (OUTPUT_DIR / "briefings" / f"{date_str}.md").write_text(
        render_markdown(stories, date_str), encoding="utf-8")
    (OUTPUT_DIR / "data" / f"{date_str}.json").write_text(
        json.dumps(stories, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"Briefing written: {len(stories)} stories -> docs/index.html")


if __name__ == "__main__":
    main()