"""Fetch latest YouTube channel videos via RSS (no API key required)."""
import re
import time
import urllib.request
import xml.etree.ElementTree as ET

# In-memory cache: (channel_id, max_results) -> (timestamp, list of video_ids)
_yt_cache = {}
_CACHE_SECONDS = 900  # 15 minutes


def get_latest_video_ids(channel_id: str | None, max_results: int = 8) -> list[str]:
    """
    Return latest video IDs from a YouTube channel's RSS feed.
    Uses channel_id (starts with UC...). Find it in YouTube Studio or channel page source.
    Returns empty list if channel_id missing, fetch fails, or parse fails.
    """
    if not channel_id or not channel_id.strip():
        return []

    cache_key = (channel_id.strip(), max_results)
    if cache_key in _yt_cache:
        ts, ids = _yt_cache[cache_key]
        if time.time() - ts < _CACHE_SECONDS:
            return ids
    url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id.strip()}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Sparksmetrics/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            tree = ET.parse(resp)
            root = tree.getroot()
    except Exception:
        return []

    # Atom: root is {http://www.w3.org/2005/Atom}feed, entries are {http://www.w3.org/2005/Atom}entry
    # yt:videoId is in {http://www.youtube.com/xml/schemas/2015}videoId
    ns = {"atom": "http://www.w3.org/2005/Atom", "yt": "http://www.youtube.com/xml/schemas/2015"}
    entries = root.findall("atom:entry", ns)
    video_ids = []
    for entry in entries[:max_results]:
        vid_el = entry.find("yt:videoId", ns)
        if vid_el is not None and vid_el.text:
            video_ids.append(vid_el.text.strip())
        else:
            # Fallback: get from link href="...?v=VIDEO_ID"
            link = entry.find("atom:link", ns)
            if link is not None:
                href = link.get("href") or ""
                match = re.search(r"[?&]v=([a-zA-Z0-9_-]{11})", href)
                if match:
                    video_ids.append(match.group(1))
    _yt_cache[cache_key] = (time.time(), video_ids)
    return video_ids
