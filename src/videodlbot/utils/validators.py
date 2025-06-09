import validators
import yt_dlp


def is_valid_url(url: str) -> bool:
    return validators.url(url)


def is_supported_platform(url: str) -> bool:
    extractors = yt_dlp.extractor.list_extractors()
    for ext in extractors:
        if ext.suitable(url):
            return True
    return False