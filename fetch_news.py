"""Fetch the latest security news stories from RSS feeds."""
import feedparser

# Each source: a display name and its RSS feed URL
FEEDS = {
    "The Hacker News": "https://feeds.feedburner.com/TheHackersNews",
    "BleepingComputer": "https://www.bleepingcomputer.com/feed/",
    "Krebs on Security": "https://krebsonsecurity.com/feed/",
}

MAX_PER_FEED = 5


def fetch_stories():
    """Return a list of stories, each a dict with source, title, link, summary."""
    stories = []
    seen_links = set()

    for source, url in FEEDS.items():
        feed = feedparser.parse(url)

        # If a feed is down, skip it instead of crashing the whole run
        if feed.bozo and not feed.entries:
            print(f"[!] Could not read feed: {source}")
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
            })

    return stories


if __name__ == "__main__":
    stories = fetch_stories()
    print(f"Fetched {len(stories)} stories\n")
    for i, story in enumerate(stories, 1):
        print(f"{i}. [{story['source']}] {story['title']}")
        print(f"   {story['link']}\n")