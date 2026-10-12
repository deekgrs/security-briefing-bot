"""Build the daily security briefing as HTML, Markdown and JSON."""
import html
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from string import Template

from summarize import CATEGORIES, SEVERITIES, analyze_all

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


def chip(group, value, label, count, active=False, color=None):
    """One filter button. data-group/data-value tell the script what to filter."""
    active_class = " active" if active else ""
    pressed = "true" if active else "false"
    dot = f'<span class="dot" style="background:{color}"></span>' if color else ""
    return (f'<button type="button" class="chip{active_class}" data-group="{group}" '
            f'data-value="{e(value)}" aria-pressed="{pressed}">'
            f'{dot}{e(label)} <span class="n">{count}</span></button>')


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
  [hidden] { display:none !important; }
  body { margin:0; background:var(--bg); color:var(--text);
         font-family: system-ui, -apple-system, "Segoe UI", sans-serif; line-height:1.5; }
  main { max-width:860px; margin:0 auto; padding:32px 16px 64px; }
  header h1 { margin:0; font-size:28px; }
  header p { margin:4px 0 0; color:var(--muted); }
  .stats { display:grid; grid-template-columns:repeat(5,1fr); gap:8px; margin:24px 0 16px; }
  .stat { background:var(--card); border:1px solid var(--line); border-radius:10px;
          padding:12px; text-align:center; font-size:13px; color:var(--muted); }
  .stat .num { display:block; font-size:24px; font-weight:700; }
  .filters { background:var(--card); border:1px solid var(--line); border-radius:10px;
             padding:12px 14px; margin-bottom:12px; }
  .filter-row { display:flex; flex-wrap:wrap; gap:6px; align-items:center; }
  .filter-row + .filter-row { margin-top:8px; }
  .filter-label { font-size:12px; font-weight:600; color:var(--muted); width:72px;
                  text-transform:uppercase; letter-spacing:.04em; }
  .chip { font:inherit; font-size:13px; cursor:pointer; display:inline-flex; align-items:center;
          gap:6px; border:1px solid var(--line); background:transparent; color:var(--text);
          border-radius:999px; padding:3px 11px; }
  .chip:hover { border-color:var(--muted); }
  .chip.active { background:var(--text); color:var(--bg); border-color:var(--text); }
  .chip .n { font-size:11px; opacity:.7; }
  .chip .dot { width:8px; height:8px; border-radius:50%; display:inline-block; }
  .chip:disabled { opacity:.35; cursor:not-allowed; border-color:var(--line); }
  .showing { font-size:13px; color:var(--muted); margin:0 0 12px; }
  .empty { text-align:center; color:var(--muted); padding:32px; border:1px dashed var(--line);
           border-radius:10px; }
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
  @media (max-width:600px) {
    .stats { grid-template-columns:repeat(3,1fr); }
    .filter-label { width:100%; }
  }
</style>
</head>
<body>
<main>
  <header>
    <h1>Daily Security Briefing</h1>
    <p>$date &middot; $count stories, summarized and triaged by AI</p>
  </header>
  <section class="stats">$stats</section>

  <section class="filters" aria-label="Filter stories">
    <div class="filter-row"><span class="filter-label">Severity</span>$severity_chips</div>
    <div class="filter-row"><span class="filter-label">Category</span>$category_chips</div>
  </section>
  <p class="showing" id="showing" aria-live="polite"></p>
  <p class="empty" id="empty" hidden>No stories match these filters.</p>

  $cards
  <footer>Generated automatically from public RSS feeds. AI summaries can contain
  errors; follow the links for the original reporting.</footer>
</main>
<script>
(function () {
  var state = { severity: "all", category: "all" };
  var cards = document.querySelectorAll(".card");
  var chips = document.querySelectorAll(".chip");
  var showing = document.getElementById("showing");
  var empty = document.getElementById("empty");

  function matches(card, group, value) {
    return value === "all" || card.dataset[group] === value;
  }

  // Each button's count = stories you would see if you clicked it,
  // given whatever is selected in the other row
  function updateCounts() {
    chips.forEach(function (chip) {
      var group = chip.dataset.group;
      var other = group === "severity" ? "category" : "severity";
      var n = 0;
      cards.forEach(function (card) {
        if (matches(card, group, chip.dataset.value) && matches(card, other, state[other])) n++;
      });
      chip.querySelector(".n").textContent = n;
      chip.disabled = n === 0 && !chip.classList.contains("active");
    });
  }

  function apply() {
    var shown = 0;
    cards.forEach(function (card) {
      var match = matches(card, "severity", state.severity) &&
                  matches(card, "category", state.category);
      card.hidden = !match;
      if (match) shown++;
    });
    showing.textContent = "Showing " + shown + " of " + cards.length + " stories";
    empty.hidden = shown !== 0;
    updateCounts();
  }

  chips.forEach(function (chip) {
    chip.addEventListener("click", function () {
      var group = chip.dataset.group;
      state[group] = chip.dataset.value;
      chips.forEach(function (other) {
        if (other.dataset.group !== group) return;
        var on = other === chip;
        other.classList.toggle("active", on);
        other.setAttribute("aria-pressed", on ? "true" : "false");
      });
      apply();
    });
  });

  apply();
})();
</script>
</body>
</html>
""")


def render_html(stories, date_str):
    sev_counts = Counter(s["severity"] for s in stories)
    cat_counts = Counter(s["category"] for s in stories)

    stats = "".join(
        f'<div class="stat"><span class="num" style="color:{COLORS[sev]}">'
        f'{sev_counts.get(sev, 0)}</span>{sev}</div>'
        for sev in SEVERITIES
    )

    # Filter buttons: "All" plus one per value that actually appears today
    severity_chips = chip("severity", "all", "All", len(stories), active=True) + "".join(
        chip("severity", sev, sev, sev_counts[sev], color=COLORS[sev])
        for sev in SEVERITIES if sev_counts[sev]
    )
    category_chips = chip("category", "all", "All", len(stories), active=True) + "".join(
        chip("category", cat, cat, cat_counts[cat])
        for cat in CATEGORIES if cat_counts[cat]
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
  <article class="card" style="border-left-color:{color}"
           data-severity="{e(s['severity'])}" data-category="{e(s['category'])}">
    <div class="meta">
      <span class="sev" style="background:{color}">{e(s['severity'])}</span>
      <span>{e(s['category'])}</span><span>&middot;</span><span>{e(s['source'])}</span>
    </div>
    <h2><a href="{e(safe_link(s['link']))}" target="_blank" rel="noopener noreferrer">{e(s['title'])}</a></h2>
    <p>{e(s['summary'])}</p>
    <div class="tags">{cves}{affected}</div>
  </article>""")

    return PAGE.substitute(date=e(date_str), count=len(stories), stats=stats,
                           severity_chips=severity_chips, category_chips=category_chips,
                           cards="".join(cards))


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