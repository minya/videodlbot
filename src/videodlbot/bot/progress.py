import os
import logging
from typing import Dict

from ..utils import BYTES_MB

logger = logging.getLogger(__name__)


def build_download_progress_message(progress_data: Dict) -> str:
    total_bytes = progress_data.get('total_bytes', 0)
    downloaded_bytes = progress_data.get('downloaded_bytes', 0)
    eta = progress_data.get('eta', 0)
    filename = os.path.basename(progress_data.get('filename', 'video'))
    speed = progress_data.get('speed', None)
    speed_mbps = (speed / BYTES_MB) if speed else 0
    speed_mbps_str = f"{speed_mbps:.2f} MiB/s" if speed_mbps > 0 else "N/A"

    percent = (downloaded_bytes / total_bytes * 100) if total_bytes > 0 else 0
    return (f"Downloading {filename}...\t[{percent:.2f}%]\n"
            f"Downloaded: {downloaded_bytes / BYTES_MB:.2f} MiB at {speed_mbps_str}\n"
            f"Total: {total_bytes / BYTES_MB:.2f} MiB\n"
            f"ETA: {eta:.0f} seconds")


def build_pp_progress_message(progress_data: Dict) -> str:
    status = progress_data.get('status', 'unknown status')
    postprocessor = progress_data.get('postprocessor', 'unknown postprocessor')
    message = f"Postprocessing with {postprocessor}...\nStatus: {status}"
    return message