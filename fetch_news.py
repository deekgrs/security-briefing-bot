"""Fetch the latest security news stories from RSS feeds."""
import re

import feedparser
import requests

# Each source: a display name and its RSS feed URL
FEEDS = {
    "The Hacker News": "https://feeds.feedburner.com/TheHackersNews",
    "BleepingComputer": "https://www.bleepingcomputer.com/feed/",
    "Krebs on Security": "https://krebsonsecurity.com/feed/",
}

MAX_PER_FEED = 5
TIMEOUT_SECONDS = 20   # never wait forever for a slow or unresponsive site
HEADERS = {
    # Identify the bot honestly, so site owners know who is reading their feed
    "User-Agent": "SecurityBriefingBot/1.0 (+https://github.com/deekgrs/security-briefing-bot)",
}
IMG_TAG = re.compile(r'<img[^>]+src=["\']([^"\']+)["\']', re.IGNORECASE)


def find_image(entry):
    """Return the story's lead image URL from the feed, or "" if there is none.

    Feeds put images in different places, so we check each in turn. Only
    https:// URLs are accepted: no plain http (mixed content), no data: or
    javascript: URLs.
    """
    candidates = []
    for media in entry.get("media_content", []) + entry.get("media_thumbnail", []):
        candidates.append(media.get("url", ""))
    for enclosure in entry.get("enclosures", []):
        if enclosure.get("type", "").startswith("image/"):
            candidates.append(enclosure.get("href", ""))
    html_parts = [entry.get("summary", "")]
    html_parts += [part.get("value", "") for part in entry.get("content", [])]
    for part in html_parts:
        candidates += IMG_TAG.findall(part)

    for url in candidates:
        url = url.strip()
        if url.startswith("https://") and len(url) < 500:
            return url
    return ""


def fetch_stories():
    """Return a list of stories, each a dict with source, title, link, summary, image."""
    stories = []
    seen_links = set()

    for source, url in FEEDS.items():
        print(f"Fetching {source}...", flush=True)
        # Download with a timeout first; feedparser on its own can hang forever
        try:
            response = requests.get(url, headers=HEADERS, timeout=TIMEOUT_SECONDS)
            response.raise_for_status()
        except requests.RequestException as error:
            print(f"[!] Could not read feed: {source} ({error})", flush=True)
            continue  # one broken feed must not stop the whole briefing

        feed = feedparser.parse(response.content)
        if not feed.entries:
            print(f"[!] No stories found in feed: {source}", flush=True)
            continue

        for entry in feed.entries[:MAX_PER_FEED]:
            link = entry.get("link", "")
            if not link or link in seen_links:
                continue  # skip duplicates
            seen_links.add(link)

            stories.append({
                "source": source,
                "title": entry.get("title", "").strip(),
                "link": link,
                "published": entry.get("published", ""),
                "summary": entry.get("summary", "").strip(),
                "image": find_image(entry),
            })

    return stories


if __name__ == "__main__":
    stories = fetch_stories()
    with_images = sum(1 for s in stories if s["image"])
    print(f"\nFetched {len(stories)} stories ({with_images} with images)\n")
    for i, story in enumerate(stories, 1):
        print(f"{i}. [{story['source']}] {story['title']}")
        print(f"   {story['link']}")
        print(f"   image: {story['image'] or '(none)'}\n")