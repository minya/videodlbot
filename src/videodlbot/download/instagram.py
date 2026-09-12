import json
import logging
import os
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

import yt_dlp
from yt_dlp.networking import Request

from ..config import settings

logger = logging.getLogger(__name__)

INSTAGRAM_REFERER = 'https://www.instagram.com/'
INSTAGRAM_API_BASE_URL = 'https://i.instagram.com/api/v1'
INSTAGRAM_API_HEADERS = {
    'X-IG-App-ID': '936619743392459',
    'X-ASBD-ID': '198387',
    'X-IG-WWW-Claim': '0',
    'Origin': 'https://www.instagram.com',
    'Accept': '*/*',
}

MEDIA_TYPE_IMAGE = 1
MEDIA_TYPE_VIDEO = 2
MEDIA_TYPE_CAROUSEL = 8

_POST_URL_RE = re.compile(
    r'https?://(?:www\.)?instagram\.com(?:/(?!share/)[^/?#]+)?/(?:p|tv|reels?(?!/audio/))/(?P<id>[A-Za-z0-9_-]+)'
)
_SHORTCODE_ALPHABET = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_'
_DOWNLOAD_CHUNK_SIZE = 256 * 1024

MediaKind = Literal['image', 'video']


@dataclass
class InstagramMedia:
    kind: MediaKind
    url: str
    width: int | None = None
    height: int | None = None


@dataclass
class InstagramPost:
    shortcode: str
    username: str | None
    caption: str | None
    is_carousel: bool
    items: list[InstagramMedia] = field(default_factory=list)

    @property
    def has_images(self) -> bool:
        return any(item.kind == 'image' for item in self.items)


@dataclass
class DownloadedMedia:
    media: InstagramMedia
    path: str
    size: int


def instagram_shortcode(url: str) -> str | None:
    match = _POST_URL_RE.match(url)
    return match.group('id') if match else None


def is_instagram_post_url(url: str) -> bool:
    return instagram_shortcode(url) is not None


def shortcode_to_pk(shortcode: str) -> int:
    # Private posts append 28 extra characters to the shortcode
    if len(shortcode) > 28:
        shortcode = shortcode[:-28]
    pk = 0
    for char in shortcode:
        pk = pk * 64 + _SHORTCODE_ALPHABET.index(char)
    return pk


def _make_ydl() -> yt_dlp.YoutubeDL:
    return yt_dlp.YoutubeDL({
        'quiet': True,
        'no_warnings': True,
        'cookiefile': settings.COOKIE_FILE,
        'force_ipv6': True,
    })


def _has_session_cookie(ydl: yt_dlp.YoutubeDL) -> bool:
    return any(
        cookie.name == 'sessionid' and 'instagram.com' in cookie.domain
        for cookie in ydl.cookiejar
    )


def _best_by_area(candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
    valid = [c for c in candidates if isinstance(c, dict) and c.get('url')]
    if not valid:
        return None
    return max(valid, key=lambda c: (c.get('width') or 0) * (c.get('height') or 0))


def _parse_media(media: dict[str, Any]) -> InstagramMedia | None:
    media_type = media.get('media_type')
    if media_type == MEDIA_TYPE_VIDEO:
        best = _best_by_area(media.get('video_versions') or [])
        kind: MediaKind = 'video'
    elif media_type == MEDIA_TYPE_IMAGE:
        best = _best_by_area((media.get('image_versions2') or {}).get('candidates') or [])
        kind = 'image'
    else:
        logger.warning(f"Unknown Instagram media type: {media_type}")
        return None

    if not best:
        logger.warning(f"No downloadable URL for Instagram media type {media_type}")
        return None
    return InstagramMedia(kind=kind, url=best['url'], width=best.get('width'), height=best.get('height'))


def _parse_post(item: dict[str, Any], shortcode: str) -> InstagramPost:
    user: dict[str, Any] = item.get('user') or {}
    caption: dict[str, Any] = item.get('caption') or {}
    post = InstagramPost(
        shortcode=item.get('code') or shortcode,
        username=user.get('username'),
        caption=caption.get('text') or None,
        is_carousel=item.get('media_type') == MEDIA_TYPE_CAROUSEL,
    )

    sources: list[dict[str, Any]] = item.get('carousel_media') or [] if post.is_carousel else [item]
    for source in sources:
        media = _parse_media(source)
        if media:
            post.items.append(media)
    return post


def fetch_instagram_post(url: str) -> InstagramPost | None:
    """Fetch post metadata from the Instagram API. Requires a logged-in session cookie."""
    shortcode = instagram_shortcode(url)
    if not shortcode:
        return None

    with _make_ydl() as ydl:
        if not _has_session_cookie(ydl):
            logger.info("No Instagram session cookie found, skipping native post extraction")
            return None

        api_url = f'{INSTAGRAM_API_BASE_URL}/media/{shortcode_to_pk(shortcode)}/info/'
        logger.info(f"Fetching Instagram post info: {shortcode}")
        try:
            with ydl.urlopen(Request(api_url, headers=INSTAGRAM_API_HEADERS)) as response:
                data: dict[str, Any] = json.loads(response.read())
        except Exception as e:
            logger.warning(f"Failed to fetch Instagram post info for {shortcode}: {e}")
            return None

    items = data.get('items') or []
    if not items or not isinstance(items[0], dict):
        logger.warning(f"Instagram API returned no items for {shortcode}")
        return None

    post = _parse_post(items[0], shortcode)
    logger.info(
        f"Instagram post {post.shortcode}: carousel={post.is_carousel}, "
        f"items={[item.kind for item in post.items]}"
    )
    return post


def _download_file(ydl: yt_dlp.YoutubeDL, url: str, path: str) -> int:
    request = Request(url, headers={'Referer': INSTAGRAM_REFERER})
    size = 0
    with ydl.urlopen(request) as response, open(path, 'wb') as out:
        while True:
            chunk = response.read(_DOWNLOAD_CHUNK_SIZE)
            if not chunk:
                break
            size += len(chunk)
            if size > settings.MAX_FILE_SIZE:
                raise ValueError(f"File exceeds maximum size of {settings.MAX_FILE_SIZE} bytes")
            out.write(chunk)
    return size


def download_instagram_media(
    post: InstagramPost,
    temp_dir: str,
    on_item_done: Callable[[int, int], None] | None = None,
) -> list[DownloadedMedia]:
    """Download every item of the post into temp_dir. Items that fail are skipped."""
    downloaded: list[DownloadedMedia] = []
    total = len(post.items)

    with _make_ydl() as ydl:
        for index, media in enumerate(post.items, start=1):
            ext = 'mp4' if media.kind == 'video' else 'jpg'
            path = os.path.join(temp_dir, f'{post.shortcode}_{index}.{ext}')
            try:
                size = _download_file(ydl, media.url, path)
                if size == 0:
                    raise ValueError("Downloaded file is empty")
                downloaded.append(DownloadedMedia(media=media, path=path, size=size))
                logger.info(f"Downloaded Instagram {media.kind} {index}/{total} ({size} bytes)")
            except Exception as e:
                logger.error(f"Failed to download Instagram {media.kind} {index}/{total}: {e}")
                if os.path.exists(path):
                    os.unlink(path)
            if on_item_done:
                on_item_done(index, total)

    return downloaded
