import hashlib
import json
import os
import re
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path
from urllib.parse import urljoin
import xml.etree.ElementTree as ET

import requests
from bs4 import BeautifulSoup

SITE_URL = "https://zelda.gameconcerts.com/"
DATA_FILE = Path("data/events.json")
FEED_FILE = Path("feed.xml")

MONTHS = {
    "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
    "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; ZeldaConcertRSS/1.0; +https://github.com/)"
}

def clean(s):
    return re.sub(r"\s+", " ", s or "").strip()

def parse_date(s):
    s = clean(s).upper()
    # Current site format: 22 FEB 2027 / OCT 2027
    m = re.fullmatch(r"(\d{1,2})\s+([A-Z]{3})\s+(\d{4})", s)
    if m:
        return datetime(int(m.group(3)), MONTHS[m.group(2)], int(m.group(1)), tzinfo=timezone.utc)
    m = re.fullmatch(r"([A-Z]{3})\s+(\d{4})", s)
    if m:
        return datetime(int(m.group(2)), MONTHS[m.group(1)], 1, tzinfo=timezone.utc)
    return None

def make_id(event):
    raw = "|".join(event.get(k, "") for k in
                   ("country", "city", "date", "time", "orchestra", "venue"))
    return hashlib.sha256(raw.encode()).hexdigest()[:20]

def extract_events(html):
    soup = BeautifulSoup(html, "html.parser")
    # The public page currently exposes each concert as a sequence:
    # country, city, date, time, orchestra, venue, then a ticket/info link
    # or a status such as "sold out".
    #
    # We deliberately parse text rather than depending on framework-specific
    # class names, making the scraper more tolerant of CSS redesigns.
    root = soup.find("main") or soup.body or soup

    nodes = []
    for el in root.find_all(["a", "div", "p", "span", "li", "h2", "h3", "h4"]):
        txt = clean(el.get_text(" ", strip=True))
        if txt:
            nodes.append((el, txt))

    events = []
    seen = set()

    countries = {"USA", "UK", "AUS", "SWE", "CANADA", "FRA", "DEU", "GERMANY",
                 "ITA", "ESP", "JPN", "JAPAN"}

    for i, (el, txt) in enumerate(nodes):
        # Find a country marker, then inspect the following text nodes.
        if txt.upper() not in countries:
            continue

        vals = []
        for _, t in nodes[i+1:i+12]:
            if t in vals:
                continue
            vals.append(t)

        # Identify date and time in the following window.
        date_idx = next((j for j, t in enumerate(vals) if parse_date(t)), None)
        if date_idx is None:
            continue
        date_text = vals[date_idx]
        date_obj = parse_date(date_text)

        time_idx = None
        for j in range(date_idx + 1, min(date_idx + 5, len(vals))):
            if re.fullmatch(r"\d{1,2}(?::\d{2})?\s*(?:AM|PM)", vals[j], re.I):
                time_idx = j
                break

        # TBA is used by the site for dates whose exact day/time isn't known.
        if time_idx is None:
            tba_idx = next((j for j in range(date_idx + 1, min(date_idx + 4, len(vals)))
                            if vals[j].upper() == "TBA"), None)
            if tba_idx is None:
                continue
            time_text = "TBA"
            after = vals[tba_idx + 1:]
        else:
            time_text = vals[time_idx]
            after = vals[time_idx + 1:]

        # The current site's next two text values after time are orchestra and venue.
        status = ""
        link = SITE_URL
        orchestra = ""
        venue = ""

        # Ignore generic UI text and collect the next plausible values.
        useful = [x for x in after if x.lower() not in {"tickets", "info"}]
        if useful:
            orchestra = useful[0]
        if len(useful) > 1:
            venue = useful[1]
        if len(useful) > 2 and useful[2].lower() in {"sold out"}:
            status = useful[2].lower()

        # Prefer the nearest ticket/info link in the same region.
        for _, t in nodes[i:i+20]:
            pass
        parent = el.parent
        if parent:
            a = parent.find("a", href=True)
            if a:
                link = urljoin(SITE_URL, a["href"])

        event = {
            "country": txt.upper(),
            "city": vals[0] if vals else "",
            "date": date_obj.date().isoformat() if date_obj else date_text,
            "time": time_text,
            "orchestra": orchestra,
            "venue": venue,
            "status": status,
            "url": link,
        }
        event["id"] = make_id(event)

        if event["id"] not in seen and event["city"] and event["orchestra"]:
            seen.add(event["id"])
            events.append(event)

    # Fallback: if the site's HTML structure changes, fail loudly rather than
    # publishing an empty feed.
    if not events:
        raise RuntimeError("No concerts were extracted; site structure may have changed.")

    return events

def load_old():
    if not DATA_FILE.exists():
        return {}
    return {e["id"]: e for e in json.loads(DATA_FILE.read_text(encoding="utf-8"))}

def event_title(e):
    return f'{e["city"]} — {e["date"]}' + (f' — {e["time"]}' if e["time"] else "")

def event_description(e):
    parts = [
        f'Country: {e["country"]}',
        f'City: {e["city"]}',
        f'Date: {e["date"]}',
        f'Time: {e["time"]}',
        f'Orchestra: {e["orchestra"]}',
        f'Venue: {e["venue"]}',
    ]
    if e.get("status"):
        parts.append(f'Status: {e["status"]}')
    return "\n".join(parts)

def build_feed(events, changed_ids):
    ET.register_namespace("", "http://www.w3.org/2005/Atom")
    rss = ET.Element("rss", {"version": "2.0",
                             "xmlns:atom": "http://www.w3.org/2005/Atom"})
    channel = ET.SubElement(rss, "channel")
    ET.SubElement(channel, "title").text = "The Legend of Zelda 40th Anniversary Concert — Monitor"
    ET.SubElement(channel, "link").text = SITE_URL
    ET.SubElement(channel, "description").text = "New and changed concerts from the official Game Concerts site."
    ET.SubElement(channel, "language").text = "en"
    atom = ET.SubElement(channel, "{http://www.w3.org/2005/Atom}link",
                         {"href": os.environ.get("FEED_URL", "https://YOUR-USER.github.io/zelda-rss/feed.xml"),
                          "rel": "self", "type": "application/rss+xml"})

    # Include all current events so a fresh reader gets the complete schedule.
    # New/changed events are listed first.
    events_sorted = sorted(events, key=lambda e: (e["date"], e["time"], e["city"]))
    events_sorted.sort(key=lambda e: e["id"] in changed_ids, reverse=True)

    now = datetime.now(timezone.utc)
    ET.SubElement(channel, "lastBuildDate").text = format_datetime(now, usegmt=True)

    for e in events_sorted:
        item = ET.SubElement(channel, "item")
        ET.SubElement(item, "title").text = event_title(e)
        ET.SubElement(item, "link").text = e["url"]
        ET.SubElement(item, "guid", {"isPermaLink": "false"}).text = "zelda-" + e["id"]
        ET.SubElement(item, "description").text = event_description(e)
        pub = datetime.fromisoformat(e["date"]).replace(tzinfo=timezone.utc)
        if e["id"] in changed_ids:
            pub = now
        ET.SubElement(item, "pubDate").text = format_datetime(pub, usegmt=True)
        ET.SubElement(item, "category").text = e["country"]

    tree = ET.ElementTree(rss)
    ET.indent(tree, space="  ")
    FEED_FILE.write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n' +
        ET.tostring(rss, encoding="unicode"),
        encoding="utf-8"
    )

def main():
    r = requests.get(SITE_URL, headers=HEADERS, timeout=30)
    r.raise_for_status()
    r.encoding = r.apparent_encoding or "utf-8"

    events = extract_events(r.text)
    old = load_old()

    changed_ids = set()
    for e in events:
        previous = old.get(e["id"])
        if previous is None or any(previous.get(k) != e.get(k) for k in
                                   ("date", "time", "orchestra", "venue", "status", "url")):
            changed_ids.add(e["id"])

    DATA_FILE.write_text(json.dumps(events, ensure_ascii=False, indent=2), encoding="utf-8")
    build_feed(events, changed_ids)

    print(f"Extracted {len(events)} concerts; {len(changed_ids)} new/changed.")

if __name__ == "__main__":
    main()
