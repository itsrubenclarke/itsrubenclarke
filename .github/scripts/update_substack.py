#!/usr/bin/env python3
"""Refresh the "Latest Substack Articles" section of README.md from an RSS feed."""
import base64
import hashlib
import html
import os
import re
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from urllib.parse import quote

FEED = os.environ.get("SUBSTACK_FEED", "https://itsrubenclarke.substack.com/feed")
MAX_POSTS = int(os.environ.get("MAX_POSTS", "3"))
LINK_TITLES = os.environ.get("LINK_TITLES", "false").lower() == "true"
README = os.environ.get("README_PATH", "README.md")
MARKER = os.environ.get("MARKER", "SUBSTACK-RECENT-ARTICLES")
HIDE_SECTION = os.environ.get("HIDE_SECTION", "false").lower() == "true"
HEADING = "### 📰 Latest Substack Articles"
START = f"<!-- {MARKER}:START -->"
END = f"<!-- {MARKER}:END -->"
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
SUMMARY_LEN = 140
PROXY_URL = "https://api.allorigins.win/raw?disableCache=true&url="
PROXY_ATTEMPTS = 5
ASSET_DIR = os.environ.get("ASSET_DIR", "assets")
ASSET_PREFIX = "substack-"
CORNER_RADIUS = 16  # in 360x203 source pixels (shown at half size)


def fetch(url, bust_cache=False):
    if bust_cache:  # Substack's CDN can serve a stale feed for the bare URL
        url += ("&" if "?" in url else "?") + f"_={int(time.time())}"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": UA, "Accept": "application/rss+xml, */*", "Cache-Control": "no-cache"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()


def fetch_feed():
    """Fetch the feed directly; Substack 403s GitHub's runner IPs, so fall back to a proxy."""
    try:
        return fetch(FEED, bust_cache=True)
    except Exception as exc:
        print(f"Direct feed fetch failed ({exc}); trying proxy", file=sys.stderr)
    for attempt in range(1, PROXY_ATTEMPTS + 1):  # the free proxy intermittently 522s
        try:
            return fetch(PROXY_URL + quote(FEED, safe=""), bust_cache=True)
        except Exception as exc:
            print(f"Proxy attempt {attempt}/{PROXY_ATTEMPTS} failed ({exc})", file=sys.stderr)
            if attempt == PROXY_ATTEMPTS:
                raise
            time.sleep(5)


def clean(text):
    text = re.sub(r"<[^>]+>", " ", text or "")
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def truncate(text, limit=SUMMARY_LEN):
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0].rstrip(".,;:!? ") + "..."


def crop_image(url):
    return "https://substackcdn.com/image/fetch/w_360,h_203,c_fill/" + quote(url, safe="")


def rounded_image(url):
    """Download the cropped thumbnail and wrap it in an SVG with rounded corners.

    GitHub strips CSS, so rounding has to be baked into the image itself.
    Returns the README-relative path, or None if the download fails.
    """
    try:
        data = fetch(crop_image(url))
    except Exception as exc:  # network/HTTP error: fall back to the plain image
        print(f"Could not fetch thumbnail ({exc}); using square image", file=sys.stderr)
        return None
    b64 = base64.b64encode(data).decode()
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
        'width="360" height="203" viewBox="0 0 360 203">'
        f'<clipPath id="c"><rect width="360" height="203" rx="{CORNER_RADIUS}"/></clipPath>'
        f'<image width="360" height="203" clip-path="url(#c)" xlink:href="data:image/jpeg;base64,{b64}"/>'
        "</svg>"
    )
    name = f"{ASSET_PREFIX}{hashlib.sha1(svg.encode()).hexdigest()[:10]}.svg"
    os.makedirs(ASSET_DIR, exist_ok=True)
    with open(os.path.join(ASSET_DIR, name), "w", encoding="utf-8") as f:
        f.write(svg)
    return f"{ASSET_DIR}/{name}"


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
        src = rounded_image(enclosure.get("url")) or crop_image(enclosure.get("url"))
        img = html.escape(src, quote=True)
        image = f'<a href="{link}"><img src="{img}" width="180" height="101" align="left" hspace="16" alt="" /></a>'
    heading = f'<a href="{link}">{title}</a>' if LINK_TITLES else title
    lines = [
        image,
        f"<b>{heading}</b><br/>",
        f"<sub>{date}</sub><br/>",
        summary,
        '<br clear="left"/>',
    ]
    return "\n".join(lines)


def main():
    root = ET.fromstring(fetch_feed())
    items = root.findall("./channel/item")[:MAX_POSTS]
    if not items:
        sys.exit("No posts found in feed; leaving README unchanged")
    block = f"{HEADING}\n\n" + "\n\n".join(render(i) for i in items)
    if HIDE_SECTION:  # keep the section up to date but invisible on the rendered README
        block = f"<!--\n{block}\n-->"

    with open(README, encoding="utf-8") as f:
        content = f.read()
    if START not in content or END not in content:
        sys.exit(f"Markers {START} / {END} not found in {README}")
    pattern = re.compile(re.escape(START) + r".*?" + re.escape(END), re.DOTALL)
    updated = pattern.sub(lambda _: f"{START}\n{block}\n{END}", content, count=1)
    # Drop generated SVGs that no section of the README references any more.
    keep = set(re.findall(re.escape(ASSET_DIR) + r"/(" + ASSET_PREFIX + r"[0-9a-f]{10}\.svg)", updated))
    if os.path.isdir(ASSET_DIR):
        for name in os.listdir(ASSET_DIR):
            if name.startswith(ASSET_PREFIX) and name.endswith(".svg") and name not in keep:
                os.remove(os.path.join(ASSET_DIR, name))
    if updated == content:
        print("README already up to date")
        return
    with open(README, "w", encoding="utf-8") as f:
        f.write(updated)
    print(f"README updated with {len(items)} post(s)")


if __name__ == "__main__":
    main()
