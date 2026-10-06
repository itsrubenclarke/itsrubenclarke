#!/usr/bin/env python3
"""Refresh the "Latest Substack Articles" section of README.md from an RSS feed."""
import html
import os
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from urllib.parse import quote

FEED = os.environ.get("SUBSTACK_FEED", "https://itsrubenclarke.substack.com/feed")
MAX_POSTS = int(os.environ.get("MAX_POSTS", "3"))
LINK_TITLES = os.environ.get("LINK_TITLES", "false").lower() == "true"
README = os.environ.get("README_PATH", "README.md")
START = "<!-- SUBSTACK-RECENT-ARTICLES:START -->"
END = "<!-- SUBSTACK-RECENT-ARTICLES:END -->"
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
SUMMARY_LEN = 140


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/rss+xml, */*"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()


def clean(text):
    text = re.sub(r"<[^>]+>", " ", text or "")
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def truncate(text, limit=SUMMARY_LEN):
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0].rstrip(".,;:!? ") + "..."


def crop_image(url):
    return "https://substackcdn.com/image/fetch/w_360,h_240,c_fill/" + quote(url, safe="")


def render(item):
    title = html.escape(clean(item.findtext("title")))
    link = html.escape(item.findtext("link", "").strip(), quote=True)
    try:
        date = parsedate_to_datetime(item.findtext("pubDate", "")).strftime("%b %d, %Y").replace(" 0", " ")
    except (TypeError, ValueError):
        date = ""
    summary = html.escape(truncate(clean(item.findtext("description"))))
    enclosure = item.find("enclosure")
    image = ""
    if enclosure is not None and enclosure.get("url"):
        img = html.escape(crop_image(enclosure.get("url")), quote=True)
        image = f'<a href="{link}"><img src="{img}" width="180" height="120" alt="" /></a>'
    heading = f'<a href="{link}">{title}</a>' if LINK_TITLES else title
    lines = [
        '<table cellpadding="10" cellspacing="0">',
        "<tr>",
        f'<td width="180" valign="top">{image}</td>',
        '<td valign="top">',
        f"<b>{heading}</b><br/>",
        f"<sub>{date}</sub><br/>",
        summary,
        "</td>",
        "</tr>",
        "</table>",
    ]
    return "\n".join(lines)


def main():
    root = ET.fromstring(fetch(FEED))
    items = root.findall("./channel/item")[:MAX_POSTS]
    if not items:
        sys.exit("No posts found in feed; leaving README unchanged")
    block = "\n\n".join(render(i) for i in items)

    with open(README, encoding="utf-8") as f:
        content = f.read()
    if START not in content or END not in content:
        sys.exit(f"Markers {START} / {END} not found in {README}")
    pattern = re.compile(re.escape(START) + r".*?" + re.escape(END), re.DOTALL)
    updated = pattern.sub(lambda _: f"{START}\n{block}\n{END}", content, count=1)
    if updated == content:
        print("README already up to date")
        return
    with open(README, "w", encoding="utf-8") as f:
        f.write(updated)
    print(f"README updated with {len(items)} post(s)")


if __name__ == "__main__":
    main()
