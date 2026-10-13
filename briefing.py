"""Build the daily security briefing as HTML, Markdown and JSON."""
import html
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from string import Template

from summarize import CATEGORIES, SEVERITIES, analyze_all

OUTPUT_DIR = Path("docs")
COLORS = {"Critical": "#b91c1c", "High": "#c2410c", "Medium": "#a16207",
          "Low": "#1d4ed8", "Info": "#57534e"}


def e(text):
    """Escape text so scraped content can never run as code in the page."""
    return html.escape(str(text), quote=True)


def safe_link(url):
    """Allow only web links; blocks javascript: and other dangerous schemes."""
    return url if url.startswith(("https://", "http://")) else "#"


def safe_image(url):
    """Allow only https image URLs; anything else means no picture."""
    return url if isinstance(url, str) and url.startswith("https://") else ""


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
  :root { --bg:#faf9f6; --card:#ffffff; --text:#1c1917; --muted:#6b6560; --line:#e7e5e0;
          --serif: Georgia, "Times New Roman", serif; }
  * { box-sizing: border-box; }
  [hidden] { display:none !important; }
  body { margin:0; background:var(--bg); color:var(--text);
         font-family: system-ui, -apple-system, "Segoe UI", sans-serif; line-height:1.55; }
  main { max-width:920px; margin:0 auto; padding:28px 16px 64px; }

  .masthead { text-align:center; border-bottom:3px double var(--text); padding-bottom:14px; }
  .kicker { font-size:12px; letter-spacing:.14em; text-transform:uppercase; color:var(--muted); }
  .masthead h1 { font-family:var(--serif); font-size:44px; line-height:1.1; margin:6px 0 8px;
                 letter-spacing:-.01em; }
  .dateline { margin:0; font-size:14px; color:var(--muted); border-top:1px solid var(--line);
              padding-top:8px; display:inline-block; }

  .stats { display:grid; grid-template-columns:repeat(5,1fr); gap:8px; margin:20px 0 14px; }
  .stat { background:var(--card); border:1px solid var(--line); border-radius:8px;
          padding:10px; text-align:center; font-size:13px; color:var(--muted); }
  .stat .num { display:block; font-family:var(--serif); font-size:26px; font-weight:700; }

  .filters { background:var(--card); border:1px solid var(--line); border-radius:8px;
             padding:12px 14px; margin-bottom:12px; }
  .filter-row { display:flex; flex-wrap:wrap; gap:6px; align-items:center; }
  .filter-row + .filter-row { margin-top:8px; }
  .filter-label { font-size:12px; font-weight:600; color:var(--muted); width:72px;
                  text-transform:uppercase; letter-spacing:.06em; }
  .chip { font:inherit; font-size:13px; cursor:pointer; display:inline-flex; align-items:center;
          gap:6px; border:1px solid var(--line); background:var(--card); color:var(--text);
          border-radius:999px; padding:3px 11px; }
  .chip:hover { border-color:var(--muted); }
  .chip.active { background:var(--text); color:#fff; border-color:var(--text); }
  .chip .n { font-size:11px; opacity:.7; }
  .chip .dot { width:8px; height:8px; border-radius:50%; display:inline-block; }
  .chip:disabled { opacity:.35; cursor:not-allowed; border-color:var(--line); }
  .showing { font-size:13px; color:var(--muted); margin:0 0 12px; }
  .empty { text-align:center; color:var(--muted); padding:32px; border:1px dashed var(--line);
           border-radius:8px; }

  .card { display:grid; grid-template-columns:1fr; gap:18px; background:var(--card);
          border:1px solid var(--line); border-top:4px solid; border-radius:8px;
          padding:16px 18px; margin-bottom:14px; }
  .card:has(.thumb) { grid-template-columns:1fr 200px; }
  .thumb { width:200px; height:134px; object-fit:cover; border-radius:6px;
           background:var(--line); display:block; }
  .meta { display:flex; flex-wrap:wrap; gap:8px; align-items:center; font-size:12px;
          color:var(--muted); text-transform:uppercase; letter-spacing:.05em; }
  .sev { color:#fff; font-weight:700; padding:2px 8px; border-radius:4px; }
  .card h2 { font-family:var(--serif); font-size:21px; line-height:1.25; margin:8px 0 6px; }
  .card h2 a { color:inherit; text-decoration:none; }
  .card h2 a:hover { text-decoration:underline; }
  .card p { margin:0 0 10px; color:#3f3a36; }
  .tags { display:flex; flex-wrap:wrap; gap:6px; }
  .tag { font-size:12px; border:1px solid var(--line); border-radius:4px; padding:1px 7px; color:var(--muted); }
  a.cve { color:#b91c1c; text-decoration:none; font-weight:600; }
  footer { margin-top:32px; padding-top:12px; border-top:1px solid var(--line);
           font-size:13px; color:var(--muted); }

  @media (max-width:640px) {
    .masthead h1 { font-size:32px; }
    .stats { grid-template-columns:repeat(3,1fr); }
    .filter-label { width:100%; }
    .card:has(.thumb) { grid-template-columns:1fr; }
    .thumb { width:100%; height:180px; order:-1; }
  }
</style>
</head>
<body>
<main>
  <header class="masthead">
    <div class="kicker">AI-curated &middot; Updated every morning</div>
    <h1>The Daily Security Briefing</h1>
    <p class="dateline">$date &middot; $count stories, summarized and triaged by AI</p>
  </header>
  <section class="stats">$stats</section>

  <section class="filters" aria-label="Filter stories">
    <div class="filter-row"><span class="filter-label">Severity</span>$severity_chips</div>
    <div class="filter-row"><span class="filter-label">Category</span>$category_chips</div>
  </section>
  <p class="showing" id="showing" aria-live="polite"></p>
  <p class="empty" id="empty" hidden>No stories match these filters.</p>

  $cards
  <footer>Generated automatically from public RSS feeds. Images and stories belong to their
  publishers; follow each link for the original reporting. AI summaries can contain errors.</footer>
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

        # Picture from the feed. If it fails to load, it removes itself and the
        # card falls back to a text-only layout. no-referrer stops the image host
        # from seeing which page the visitor came from.
        image_url = safe_image(s.get("image", ""))
        image = (f'<img class="thumb" src="{e(image_url)}" alt="" loading="lazy" '
                 f'referrerpolicy="no-referrer" onerror="this.remove()">'
                 if image_url else "")

        cards.append(f"""
  <article class="card" style="border-top-color:{color}"
           data-severity="{e(s['severity'])}" data-category="{e(s['category'])}">
    <div class="body">
      <div class="meta">
        <span class="sev" style="background:{color}">{e(s['severity'])}</span>
        <span>{e(s['category'])}</span><span>&middot;</span><span>{e(s['source'])}</span>
      </div>
      <h2><a href="{e(safe_link(s['link']))}" target="_blank" rel="noopener noreferrer">{e(s['title'])}</a></h2>
      <p>{e(s['summary'])}</p>
      <div class="tags">{cves}{affected}</div>
    </div>
    {image}
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