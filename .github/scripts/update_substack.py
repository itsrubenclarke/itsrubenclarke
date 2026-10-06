#!/usr/bin/env python3
"""Refresh the "Latest Substack Articles" section of README.md from an RSS feed."""
import base64
import hashlib
import html
import os
import re
import sys
import textwrap
import time
import urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from urllib.parse import quote

FEED = os.environ.get("SUBSTACK_FEED", "https://itsrubenclarke.substack.com/feed")
MAX_POSTS = int(os.environ.get("MAX_POSTS", "3"))
LINK_TITLES = os.environ.get("LINK_TITLES", "false").lower() == "true"
README = os.environ.get("README_PATH", "README.md")
LAYOUT = os.environ.get("LAYOUT", "list")  # "list" (image + text rows) or "grid" (2-up cards)
MARKER = os.environ.get("MARKER", "SUBSTACK-RECENT-ARTICLES")
START = f"<!-- {MARKER}:START -->"
END = f"<!-- {MARKER}:END -->"
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
SUMMARY_LEN = 140
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


def wrap(text, width, max_lines):
    lines = textwrap.wrap(text, width) or [""]
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1][: width - 1].rstrip(".,;:!? ") + "…"
    return lines


def render_card(item):
    """One bordered card (rounded border, thumbnail left, text right) as a standalone SVG.

    GitHub strips CSS, so the whole card is drawn inside the image itself.
    """
    title = wrap(clean(item.findtext("title")), 32, 1)[0]
    summary = wrap(clean(item.findtext("description")), 52, 2)
    link = html.escape(item.findtext("link", "").strip(), quote=True)
    try:
        date = parsedate_to_datetime(item.findtext("pubDate", "")).strftime("%b %d, %Y").replace(" 0", " ")
    except (TypeError, ValueError):
        date = ""
    enclosure = item.find("enclosure")
    thumb = ""
    if enclosure is not None and enclosure.get("url"):
        try:
            b64 = base64.b64encode(fetch(crop_image(enclosure.get("url")))).decode()
            thumb = (
                '<clipPath id="t"><rect x="16" y="24" width="200" height="112" rx="8"/></clipPath>'
                '<image x="16" y="24" width="200" height="112" clip-path="url(#t)" '
                f'xlink:href="data:image/jpeg;base64,{b64}"/>'
            )
        except Exception as exc:
            print(f"Could not fetch thumbnail ({exc}); card has no image", file=sys.stderr)
    esc = html.escape
    summary_svg = "".join(
        f'<text x="236" y="{112 + 20 * i}" class="s">{esc(line)}</text>' for i, line in enumerate(summary)
    )
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
        'width="640" height="160" viewBox="0 0 640 160">'
        "<style>"
        ".b{fill:#fff;stroke:#d0d7de}.t{fill:#24292f}.d{fill:#6e7781}.s{fill:#424a53}"
        "text{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif}"
        ".t{font-size:20px;font-weight:700}.d{font-size:13px}.s{font-size:14px}"
        "@media (prefers-color-scheme:dark){.b{fill:#0d1117;stroke:#30363d}.t{fill:#f0f6fc}.d{fill:#8b949e}.s{fill:#c9d1d9}}"
        "</style>"
        '<rect class="b" x="1" y="1" width="638" height="158" rx="12"/>'
        f"{thumb}"
        f'<text x="236" y="52" class="t">{esc(title)}</text>'
        f'<text x="236" y="76" class="d">{esc(date)}</text>'
        f"{summary_svg}"
        "</svg>"
    )
    name = f"{ASSET_PREFIX}card-{hashlib.sha1(svg.encode()).hexdigest()[:10]}.svg"
    os.makedirs(ASSET_DIR, exist_ok=True)
    with open(os.path.join(ASSET_DIR, name), "w", encoding="utf-8") as f:
        f.write(svg)
    alt = esc(clean(item.findtext("title")), quote=True)
    return f'<a href="{link}"><img src="{ASSET_DIR}/{name}" width="49%" alt="{alt}" /></a>'


def render_grid(items):
    rows = ["".join(render_card(i) for i in items[n : n + 2]) for n in range(0, len(items), 2)]
    return "\n<br/>\n".join(rows)


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
    root = ET.fromstring(fetch(FEED, bust_cache=True))
    items = root.findall("./channel/item")[:MAX_POSTS]
    if not items:
        sys.exit("No posts found in feed; leaving README unchanged")
    block = render_grid(items) if LAYOUT == "grid" else "\n\n".join(render(i) for i in items)

    with open(README, encoding="utf-8") as f:
        content = f.read()
    if START not in content or END not in content:
        sys.exit(f"Markers {START} / {END} not found in {README}")
    pattern = re.compile(re.escape(START) + r".*?" + re.escape(END), re.DOTALL)
    updated = pattern.sub(lambda _: f"{START}\n{block}\n{END}", content, count=1)
    # Drop generated SVGs that no section of the README references any more.
    keep = set(re.findall(re.escape(ASSET_DIR) + r"/(" + ASSET_PREFIX + r"(?:card-)?[0-9a-f]{10}\.svg)", updated))
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
