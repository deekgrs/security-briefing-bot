"""Build the daily security briefing as HTML, Markdown and JSON, plus an archive of past days."""
import html
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from string import Template
from zoneinfo import ZoneInfo

from summarize import CATEGORIES, SEVERITIES, analyze_all, clean_action

SITE_URL = "https://deekgrs.github.io/security-briefing-bot/"
DESCRIPTION = ("Which security news matters today, and what to do about it. "
               "An AI-curated daily briefing in plain English, for everyone.")
OUTPUT_DIR = Path("docs")
DATA_DIR = OUTPUT_DIR / "data"
ARCHIVE_DIR = OUTPUT_DIR / "archive"
DATE_NAME = re.compile(r"^\d{4}-\d{2}-\d{2}$")
CVE_ID = re.compile(r"^CVE-\d{4}-\d{4,}$")
COLORS = {"Critical": "#b91c1c", "High": "#c2410c", "Medium": "#a16207",
          "Low": "#1d4ed8", "Info": "#57534e"}

# Plain-English definitions shown when a reader hovers over or taps a term.
# These are written by us, not by the AI, so they are trusted text.
GLOSSARY = {
    "zero-day": "A flaw that attackers found and used before the maker had a fix ready.",
    "zero-days": "Flaws that attackers found and used before the maker had a fix ready.",
    "CVE": "An official ID number given to a publicly known security flaw, so everyone can refer to the same one.",
    "CVSS": "A severity score for security flaws, from 0 to 10. A 10 is the most dangerous.",
    "remote code execution": "The attacker can run their own commands on a device from anywhere over the internet.",
    "RCE": "Remote code execution: the attacker can run their own commands on a device from anywhere over the internet.",
    "actively exploited": "Attackers are already using this flaw in real attacks, not just in theory.",
    "exploited": "Attackers have used this flaw to break in.",
    "exploit": "A method or piece of code that takes advantage of a flaw to break in.",
    "patched": "Fixed by a software update from the maker.",
    "patch": "A software update that fixes a flaw.",
    "Patch Tuesday": "The second Tuesday of each month, when Microsoft releases its security updates.",
    "ransomware": "Harmful software that locks your files and demands payment to unlock them.",
    "phishing": "Fake emails, texts or sites that trick people into giving away passwords or clicking harmful links.",
    "malware": "Harmful software designed to damage a device or steal from it.",
    "VPN": "A secure connection into a private network, often used by staff working remotely.",
    "botnet": "A network of hacked devices that an attacker controls together.",
    "supply chain": "Attacking a target through a supplier, product or update it already trusts.",
    "credentials": "Login details, such as usernames, passwords or access keys.",
    "unauthenticated": "Without needing to log in first.",
    "SSRF": "A trick that makes a server send requests on the attacker's behalf, reaching places the attacker can't.",
    "OAuth2": "A common system that lets apps log in to other services without sharing passwords.",
    "extortion": "Threatening to leak or damage something unless a payment is made.",
    "data breach": "When private information is stolen or exposed.",
}
TERM_PATTERN = re.compile(
    r"(?<![\w-])(" + "|".join(re.escape(t) for t in sorted(GLOSSARY, key=len, reverse=True))
    + r")(?![\w-])",
    re.IGNORECASE,
)
GLOSSARY_LOOKUP = {term.lower(): definition for term, definition in GLOSSARY.items()}


def explain_terms(escaped_text, seen):
    """Wrap the first use of each jargon word in a tappable definition.

    Runs on text that is ALREADY HTML-escaped, and only inserts our own fixed
    definitions, so it can't reintroduce any markup from the feed or the AI.
    """
    def wrap(match):
        word = match.group(0)
        key = word.lower()
        if key in seen:
            return word
        seen.add(key)
        return (f'<abbr class="term" tabindex="0" '
                f'data-def="{e(GLOSSARY_LOOKUP[key])}">{word}</abbr>')
    return TERM_PATTERN.sub(wrap, escaped_text)


def e(text):
    """Escape text so scraped content can never run as code in the page."""
    return html.escape(str(text), quote=True)


def safe_link(url):
    """Allow only web links; blocks javascript: and other dangerous schemes."""
    return url if isinstance(url, str) and url.startswith(("https://", "http://")) else "#"


def safe_image(url):
    """Allow only https image URLs; anything else means no picture."""
    return url if isinstance(url, str) and url.startswith("https://") else ""


def sort_by_severity(stories):
    rank = {sev: i for i, sev in enumerate(SEVERITIES)}
    return sorted(stories, key=lambda s: rank.get(s["severity"], len(SEVERITIES)))


def updated_label():
    """'Last updated 4:24 AM ET', in New York time (falls back to UTC if time zones are missing)."""
    try:
        now = datetime.now(ZoneInfo("America/New_York"))
        zone = "ET"
    except Exception:
        now = datetime.now(timezone.utc)
        zone = "UTC"
    return f"Last updated {now.strftime('%I:%M %p').lstrip('0')} {zone}"


def nice_date(date_str):
    """2026-10-13 -> Tue, Oct 13, 2026"""
    return datetime.strptime(date_str, "%Y-%m-%d").strftime("%a, %b %d, %Y").replace(" 0", " ")


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
<title>The Daily Security Briefing - $nice_date</title>
<meta name="description" content="$description">
<link rel="icon" href="${asset_prefix}favicon.svg" type="image/svg+xml">
<!-- Link previews on LinkedIn, Slack, X and others: always show our own card,
     not whichever news photo happens to be first on the page -->
<meta property="og:type" content="website">
<meta property="og:site_name" content="The Daily Security Briefing">
<meta property="og:title" content="The Daily Security Briefing - $nice_date">
<meta property="og:description" content="$description">
<meta property="og:url" content="$page_url">
<meta property="og:image" content="${site_url}preview.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="627">
<meta property="og:image:alt" content="The Daily Security Briefing: which security news matters today, and what to do about it.">
<meta name="twitter:card" content="summary_large_image">
<style>
  :root { --bg:#faf9f6; --card:#ffffff; --text:#1c1917; --muted:#6b6560; --line:#e7e5e0;
          --serif: Georgia, "Times New Roman", serif; }
  * { box-sizing: border-box; }
  [hidden] { display:none !important; }
  body { margin:0; background:var(--bg); color:var(--text);
         font-family: system-ui, -apple-system, "Segoe UI", sans-serif; line-height:1.55; }
  main { max-width:920px; margin:0 auto; padding:28px 16px 64px; }
  a { color:inherit; }

  .masthead { text-align:center; border-bottom:3px double var(--text); padding-bottom:14px; }
  .kicker { font-size:12px; letter-spacing:.14em; text-transform:uppercase; color:var(--muted); }
  .masthead h1 { font-family:var(--serif); font-size:44px; line-height:1.1; margin:6px 0 8px;
                 letter-spacing:-.01em; }
  .masthead h1 a { text-decoration:none; }
  .dateline { margin:0; font-size:14px; color:var(--muted); border-top:1px solid var(--line);
              padding-top:8px; display:inline-block; }

  .banner { display:flex; flex-wrap:wrap; gap:8px 16px; justify-content:space-between;
            align-items:center; margin:16px 0 0; padding:10px 14px; font-size:14px;
            background:#fef3c7; border:1px solid #fcd34d; border-radius:8px; }
  .banner a { font-weight:600; }
  .banner .pager { display:flex; gap:14px; }

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
  .card h2 a { text-decoration:none; }
  .card h2 a:hover { text-decoration:underline; }
  .card p { margin:0 0 10px; color:#3f3a36; }
  .card p.also { font-size:13px; color:var(--muted); }
  .label { font-size:11px; font-weight:700; letter-spacing:.08em; text-transform:uppercase;
           color:var(--muted); margin-right:4px; }
  .action { margin:0 0 10px; padding:10px 12px; border-radius:6px; font-size:15px;
            background:#fef2f2; border-left:4px solid; }
  .action .label { color:inherit; }
  .action-title { display:block; font-size:11px; font-weight:700; letter-spacing:.08em;
                  text-transform:uppercase; margin-bottom:4px; }
  .action p { margin:0; color:var(--text); }
  .action p + p { margin-top:6px; }
  .action .who { font-weight:700; }
  abbr.term { text-decoration:underline dotted; text-underline-offset:3px; cursor:help;
              position:relative; outline:none; }
  abbr.term:hover::after, abbr.term:focus::after {
    content:attr(data-def); position:absolute; left:0; top:1.7em; z-index:10;
    width:min(260px, 80vw); padding:8px 10px; border-radius:6px;
    background:var(--text); color:#fff; font:400 13px/1.45 system-ui, sans-serif;
    text-transform:none; letter-spacing:0; box-shadow:0 4px 14px rgba(0,0,0,.18); }
  .jargon-note { font-size:13px; color:var(--muted); margin:0 0 12px; }
  .also a { color:var(--text); }
  .tags { display:flex; flex-wrap:wrap; gap:6px; }
  .tag { font-size:12px; border:1px solid var(--line); border-radius:4px; padding:1px 7px; color:var(--muted); }
  a.cve { color:#b91c1c; text-decoration:none; font-weight:600; }

  .archive { margin-top:32px; padding-top:16px; border-top:3px double var(--text); }
  .archive h2 { font-family:var(--serif); font-size:24px; margin:0 0 10px; }
  .archive ul { list-style:none; margin:0; padding:0; display:grid;
                grid-template-columns:repeat(auto-fill, minmax(200px, 1fr)); gap:8px; }
  .archive li { background:var(--card); border:1px solid var(--line); border-radius:8px; }
  .archive li a, .archive li span { display:block; padding:10px 12px; text-decoration:none; }
  .archive li a:hover { background:#f3f1ec; border-radius:8px; }
  .archive li.current { border-color:var(--text); }
  .archive small { display:block; color:var(--muted); font-size:12px; }

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
    <div class="kicker">AI-curated &middot; Updated every morning at 4:30 AM ET</div>
    <h1><a href="$home">The Daily Security Briefing</a></h1>
    <p class="dateline">$nice_date &middot; $count stories, summarized and triaged by AI$updated</p>
  </header>
  $banner
  <section class="stats">$stats</section>

  <section class="filters" aria-label="Filter stories">
    <div class="filter-row"><span class="filter-label">Severity</span>$severity_chips</div>
    <div class="filter-row"><span class="filter-label">Category</span>$category_chips</div>
  </section>
  <p class="jargon-note">New to security? Hover over or tap any
  <abbr class="term" tabindex="0" data-def="Like this one. Each underlined word has a short, plain-English definition.">underlined word</abbr>
  for a plain-English explanation.</p>
  <p class="showing" id="showing" aria-live="polite"></p>
  <p class="empty" id="empty" hidden>No stories match these filters.</p>

  $cards
  $archive
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


def render_banner(date_str, dates, in_archive):
    """On archive pages: say which day this is, with previous/next/today links."""
    if not in_archive:
        return ""
    newer = [d for d in dates if d > date_str]
    older = [d for d in dates if d < date_str]
    pager = []
    if older:
        pager.append(f'<a href="{max(older)}.html">&larr; {e(nice_date(max(older)))}</a>')
    if newer:
        pager.append(f'<a href="{min(newer)}.html">{e(nice_date(min(newer)))} &rarr;</a>')
    return (f'<div class="banner"><span>You are reading the archived briefing for '
            f'<strong>{e(nice_date(date_str))}</strong>. '
            f'<a href="../index.html">Go to today&rsquo;s briefing</a></span>'
            f'<span class="pager">{"".join(pager)}</span></div>')


def render_archive_list(date_str, dates, counts, in_archive):
    """The 'Past briefings' grid at the bottom of every page, newest first."""
    if len(dates) < 2:
        return ""
    prefix = "" if in_archive else "archive/"
    items = []
    for d in dates:
        n = counts.get(d, 0)
        label = f'{e(nice_date(d))}<small>{n} stories</small>'
        if d == date_str:
            items.append(f'<li class="current"><span>{label}<small>You are here</small></span></li>')
        else:
            items.append(f'<li><a href="{prefix}{d}.html">{label}</a></li>')
    return (f'<section class="archive" aria-label="Past briefings">'
            f'<h2>Past briefings</h2><ul>{"".join(items)}</ul></section>')


def render_html(stories, date_str, dates=(), counts=None, in_archive=False, updated=""):
    sev_counts = Counter(s["severity"] for s in stories)
    cat_counts = Counter(s["category"] for s in stories)

    stats = "".join(
        f'<div class="stat"><span class="num" style="color:{COLORS[sev]}">'
        f'{sev_counts.get(sev, 0)}</span>{sev}</div>'
        for sev in SEVERITIES
    )

    # Filter buttons: "All" plus one per value that actually appears that day
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

        # Other outlets' coverage of the same event, merged into this card
        also = s.get("also_covered", [])
        also_html = ""
        if also:
            links = " &middot; ".join(
                f'<a href="{e(safe_link(o["link"]))}" target="_blank" rel="noopener noreferrer">'
                f'{e(o["source"])}: {e(o["title"])}</a>'
                for o in also
            )
            also_html = f'<p class="also"><strong>Also covered:</strong> {links}</p>'

        # Urgent stories read as "what happened / what to do"; the rest as a summary.
        # Jargon is explained once per card, wherever it first appears.
        seen = set()
        summary = explain_terms(e(s["summary"]), seen)
        for_everyone = s.get("action_everyone", "")
        for_it = s.get("action_it", "")
        if for_everyone or for_it:
            summary_html = f'<p><span class="label">What happened</span>{summary}</p>'
            rows = ""
            if for_everyone:
                rows += (f'<p><span class="who">For everyone:</span> '
                         f'{explain_terms(e(for_everyone), seen)}</p>')
            if for_it:
                rows += (f'<p><span class="who">For IT teams:</span> '
                         f'{explain_terms(e(for_it), seen)}</p>')
            action_html = (f'<div class="action" style="border-color:{color}">'
                           f'<span class="action-title" style="color:{color}">What to do</span>'
                           f'{rows}</div>')
        else:
            summary_html = f'<p>{summary}</p>'
            action_html = ""

        cards.append(f"""
  <article class="card" style="border-top-color:{color}"
           data-severity="{e(s['severity'])}" data-category="{e(s['category'])}">
    <div class="body">
      <div class="meta">
        <span class="sev" style="background:{color}">{e(s['severity'])}</span>
        <span>{e(s['category'])}</span><span>&middot;</span><span>{e(s['source'])}</span>
      </div>
      <h2><a href="{e(safe_link(s['link']))}" target="_blank" rel="noopener noreferrer">{e(s['title'])}</a></h2>
      {summary_html}
      {action_html}
      {also_html}
      <div class="tags">{cves}{affected}</div>
    </div>
    {image}
  </article>""")

    return PAGE.substitute(
        date=e(date_str), nice_date=e(nice_date(date_str)), count=len(stories),
        description=e(DESCRIPTION), site_url=SITE_URL,
        asset_prefix="../" if in_archive else "",   # relative, so the icon works offline too
        updated=f" &middot; {e(updated)}" if updated else "",
        page_url=f"{SITE_URL}archive/{date_str}.html" if in_archive else SITE_URL,
        home="../index.html" if in_archive else "index.html",
        banner=render_banner(date_str, dates, in_archive),
        stats=stats, severity_chips=severity_chips, category_chips=category_chips,
        cards="".join(cards),
        archive=render_archive_list(date_str, dates, counts or {}, in_archive),
    )


def render_markdown(stories, date_str):
    lines = [f"# Daily Security Briefing - {date_str}", ""]
    for s in stories:
        lines.append(f"## [{s['severity']}] {s['title']}")
        lines.append(f"*{s['category']} · {s['source']}* - [Read more]({safe_link(s['link'])})")
        lines.append("")
        lines.append(s["summary"])
        if s.get("action_everyone"):
            lines.append(f"\n**What to do (everyone):** {s['action_everyone']}")
        if s.get("action_it"):
            lines.append(f"\n**What to do (IT teams):** {s['action_it']}")
        for o in s.get("also_covered", []):
            lines.append(f"\n*Also covered:* [{o['source']}: {o['title']}]({safe_link(o['link'])})")
        if s["cves"]:
            lines.append(f"\n**CVEs:** {', '.join(s['cves'])}")
        lines.append("")
    return "\n".join(lines)


def normalize(story):
    """Re-validate a story loaded from a saved JSON file before it goes into a page.

    The archive is rebuilt from files in the repo, so treat them as untrusted too:
    every field gets the same checks as freshly generated output.
    """
    def text(key, limit=600):
        return str(story.get(key, ""))[:limit]

    also = []
    for o in story.get("also_covered", []) if isinstance(story.get("also_covered"), list) else []:
        if isinstance(o, dict):
            also.append({"source": str(o.get("source", ""))[:60],
                         "title": str(o.get("title", ""))[:300],
                         "link": str(o.get("link", ""))})
    cves = story.get("cves", [])
    affected = story.get("affected", [])
    severity = story.get("severity") if story.get("severity") in SEVERITIES else "Info"
    return {
        "source": text("source", 60),
        "title": text("title", 300),
        "link": text("link", 1000),
        "summary": text("summary") or "Summary unavailable.",
        "severity": severity,
        "category": story.get("category") if story.get("category") in CATEGORIES else "Other",
        "cves": [c for c in (cves if isinstance(cves, list) else [])
                 if isinstance(c, str) and CVE_ID.match(c)],
        "affected": [str(a)[:60] for a in (affected if isinstance(affected, list) else [])][:5],
        "image": text("image", 500),
        "also_covered": also,
        "action_everyone": clean_action(story.get("action_everyone", ""), severity),
        "action_it": clean_action(story.get("action_it", "") or story.get("action", ""), severity),
    }


def load_day(date_str):
    """Load one day's saved stories, or None if the file is missing or broken."""
    try:
        data = json.loads((DATA_DIR / f"{date_str}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        print(f"[!] Skipping archive for {date_str} ({error})")
        return None
    if not isinstance(data, list):
        return None
    return sort_by_severity([normalize(s) for s in data if isinstance(s, dict)])


def build_archive():
    """Rebuild an archive page for every saved day. No AI calls: it only re-renders saved data."""
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    dates = sorted((p.stem for p in DATA_DIR.glob("*.json") if DATE_NAME.match(p.stem)),
                   reverse=True)
    days = {}
    for d in dates:
        stories = load_day(d)
        if stories is not None:
            days[d] = stories
    dates = [d for d in dates if d in days]
    counts = {d: len(days[d]) for d in dates}

    for d in dates:
        (ARCHIVE_DIR / f"{d}.html").write_text(
            render_html(days[d], d, dates, counts, in_archive=True), encoding="utf-8")
    return dates, counts, days


def main():
    # The briefing's date is the New York date, matching the schedule and "Last updated" time
    try:
        date_str = datetime.now(ZoneInfo("America/New_York")).strftime("%Y-%m-%d")
    except Exception:
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    stories = sort_by_severity(analyze_all())
    if not stories:
        # Every feed failed: keep yesterday's page rather than publishing an empty one,
        # and fail the run so the problem shows up in the Actions tab
        raise SystemExit("No stories fetched; leaving the existing briefing in place.")

    (OUTPUT_DIR / "briefings").mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    (OUTPUT_DIR / "briefings" / f"{date_str}.md").write_text(
        render_markdown(stories, date_str), encoding="utf-8")
    (DATA_DIR / f"{date_str}.json").write_text(
        json.dumps(stories, indent=2, ensure_ascii=False), encoding="utf-8")

    dates, counts, days = build_archive()
    (OUTPUT_DIR / "index.html").write_text(
        render_html(days[date_str], date_str, dates, counts, updated=updated_label()),
        encoding="utf-8")

    print(f"Briefing written: {len(stories)} stories -> docs/index.html")
    print(f"Archive: {len(dates)} days -> docs/archive/")


def rebuild_archive_only():
    """Re-render the archive and front page from saved data, without fetching or AI calls."""
    dates, counts, days = build_archive()
    if dates:
        latest = dates[0]
        (OUTPUT_DIR / "index.html").write_text(
            render_html(days[latest], latest, dates, counts), encoding="utf-8")
    print(f"Archive rebuilt: {len(dates)} days -> docs/archive/")


if __name__ == "__main__":
    import sys
    if "--archive-only" in sys.argv:
        rebuild_archive_only()
    else:
        main()