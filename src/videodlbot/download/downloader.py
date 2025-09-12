import os
import logging
from typing import Optional, Dict, Any
import yt_dlp

from ..config import settings

logger = logging.getLogger(__name__)

FORMAT_SELECTION = 'best[ext=mp4]/bestvideo[ext=mp4]+bestaudio/best/bestvideo+bestaudio'


def extract_video_info(url: str) -> Dict[str, Any]:
    ydl_opts = {
        'age_limit': 21,
        'cookiefile': settings.COOKIE_FILE,
        'extract_flat': True,
        'format': FORMAT_SELECTION,
        'geo_bypass': True,
        'no_warnings': True,
        'quiet': True,
        'verbose': settings.DEBUG_MODE,
        'force_ipv6': True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        logger.info(f"Video information extracting: {url}")
        info = ydl.extract_info(url, download=False)
        if not info:
            return {}
        return info


def need_convert_vcodec(vcodec: str) -> bool:
    if not vcodec:
        return True
    if vcodec.startswith('avc1'):
        vcodec = 'h264'
    elif vcodec.startswith('av01'):
        vcodec = 'av01'
    elif vcodec.startswith('hvc1'):
        vcodec = 'h265'
    elif vcodec.startswith('hevc'):
        vcodec = 'h265'
    elif vcodec.startswith('h264'):
        vcodec = 'h264'
    elif vcodec.startswith('h265'):
        vcodec = 'h265'
    return vcodec not in ['h264', 'h265', 'avc1', 'av01']


def need_convert_acodec(acodec: str) -> bool:
    return acodec not in ['aac', 'mp4a.40.2', 'mp4a.40.5', 'mp4a.40.29']


def download_video(url: str, info: dict[str, Any], output_path: str, progress_data: dict) -> Optional[str]:
    def on_progress(d):
        progress_data.clear()
        progress_data.update({'download_progress': d.copy()})

    def on_postprocess(d):
        progress_data.clear()
        progress_data.update({'postprocess_progress': d.copy()})

    vcodec = info.get('vcodec', '')
    acodec = info.get('acodec', '')
    extractor = info.get('extractor', '')

    need_convert = \
        extractor == 'youtube' and \
        (need_convert_vcodec(vcodec) or need_convert_acodec(acodec))

    logger.info(f"Video codec: {vcodec}, Audio codec: {acodec}, Extractor: {extractor} Need convert: {need_convert}")
    verbose = settings.DEBUG_MODE
    
    try:
        ydl_opts = {
            'quiet': not verbose,
            'no_warnings': not verbose,
            'verbose': verbose,
            'format': FORMAT_SELECTION,
            'age_limit': 21,
            'geo_bypass': True,
            'cookiefile': settings.COOKIE_FILE,
            'outtmpl': output_path,
            'merge_output_format': 'mp4',
            'progress_hooks': [on_progress],
            'postprocessor_hooks': [on_postprocess],
            'postprocessors': [
                {
                    'key': 'FFmpegVideoConvertor',
                    'preferedformat': 'mp4',
                },
            ],
            'force_ipv6': True,
        }

        if need_convert:
            ydl_opts['postprocessors'].append({
                'key': 'FFmpegCopyStream',
            })
            v_a = 'libx264' if need_convert_vcodec(vcodec) else 'copy'
            c_a = 'aac' if need_convert_acodec(acodec) else 'copy'
            ydl_opts['postprocessor_args'] = {
                'copystream': [
                    '-c:v', f'{v_a}',
                    '-c:a', f'{c_a}',
                ],
            }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            logger.info(f"Starting download to: {output_path}")
            ydl.download([url])
            logger.info(f"Download completed. Checking file: {output_path}")
            if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                return output_path
            else:
                logger.warning("Downloaded file is empty or does not exist")
                return None
    except Exception as e:
        logger.error(f"Error downloading video: {e}")
        return None
