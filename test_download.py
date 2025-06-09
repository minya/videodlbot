import sys
import os
import argparse
import logging
from urllib.parse import urlparse
import yt_dlp

from src.videodlbot.utils import is_valid_url as is_url

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


def test_extraction(url, verbose=False):
    """Test yt-dlp's ability to extract information from a URL."""
    logger.info(f"Testing info extraction for URL: {url}")
    
    ydl_opts = {
        'quiet': not verbose,
        'no_warnings': not verbose,
        'verbose': verbose,
        'format': 'best/bestvideo+bestaudio',
        'age_limit': 21,
        'geo_bypass': True,
        'cookiefile': 'cookies.txt' if os.path.exists('cookies.txt') else None,
        'skip_download': True,
        'listformats': verbose,
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            if not info:
                logger.error("No information returned")
                return False
            
            logger.info(f"Successfully extracted info:")
            logger.info(f"  Title: {info.get('title', 'Unknown')}")
            logger.info(f"  Duration: {info.get('duration', 'Unknown')} seconds")
            
            # Show available formats in a more readable way
            if 'formats' in info and info['formats']:
                formats = info['formats']
                logger.info(f"  Available formats: {len(formats)}")
                
                if verbose:
                    # Group formats by extension
                    format_by_ext = {}
                    for fmt in formats:
                        ext = fmt.get('ext', 'unknown')
                        if ext not in format_by_ext:
                            format_by_ext[ext] = []
                        format_by_ext[ext].append(fmt)
                    
                    # Display grouped formats
                    for ext, fmt_list in format_by_ext.items():
                        logger.info(f"  Formats with extension .{ext}: {len(fmt_list)}")
                        for fmt in fmt_list:
                            res = fmt.get('resolution', 'Unknown')
                            size = fmt.get('filesize', 0)
                            size_str = f"{size/1024/1024:.2f} MB" if size else "Unknown size"
                            logger.info(f"    - ID: {fmt.get('format_id', 'Unknown')}, Resolution: {res}, Size: {size_str}")
            else:
                logger.warning("No format information available")
            
            return True
    except Exception as e:
        logger.error(f"Error extracting information: {e}")
        return False

def test_download(url, verbose=False, format_id=None):
    """Test yt-dlp's ability to download from a URL."""
    logger.info(f"Testing download for URL: {url}")
    
    # Base format selection - try multiple approaches
    if format_id:
        format_selection = format_id
        logger.info(f"Using specified format ID: {format_id}")
    else:
        format_selection = 'best/bestvideo+bestaudio/mp4/webm'
        logger.info(f"Using automatic format selection: {format_selection}")
    
    ydl_opts = {
        'quiet': not verbose,
        'no_warnings': not verbose,
        'verbose': verbose,
        'format': format_selection,
        'age_limit': 21,
        'geo_bypass': True,
        'cookiefile': 'cookies.txt' if os.path.exists('cookies.txt') else None,
        'outtmpl': 'test_download.%(ext)s',
        'merge_output_format': 'mp4',
        'postprocessors': [{
            'key': 'FFmpegVideoConvertor',
            'preferedformat': 'mp4',
        }] if not format_id else [],  # Only use post-processors for automatic format
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
            
            # Check if file exists
            for ext in ['mp4', 'webm', 'mkv', 'mov']:
                path = f'test_download.{ext}'
                if os.path.exists(path):
                    size = os.path.getsize(path)
                    if size == 0:
                        logger.error(f"Downloaded file is empty: {path}")
                        os.unlink(path)
                        return False
                    
                    logger.info(f"Successfully downloaded file: {path} ({size/1000000:.2f} MB)")
                    
                    # Delete the file
                    os.unlink(path)
                    logger.info(f"Deleted test file: {path}")
                    return True
            
            logger.error("Download appeared to succeed but no file was found")
            return False
    except Exception as e:
        logger.error(f"Error downloading: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(description='Test yt-dlp functionality')
    parser.add_argument('url', help='URL to test')
    parser.add_argument('-v', '--verbose', action='store_true', help='Enable verbose output')
    parser.add_argument('-e', '--extract-only', action='store_true', help='Only test extraction, no download')
    parser.add_argument('-f', '--format', help='Specify a format ID to download (use with --verbose to see available formats)')
    parser.add_argument('--retry', action='store_true', help='If download fails, retry with simpler format options')
    
    args = parser.parse_args()
    
    if not is_url(args.url):
        logger.error(f"The provided string does not appear to be a valid URL: {args.url}")
        return 1
    
    # Print yt-dlp version
    logger.info(f"yt-dlp version: {yt_dlp.version.__version__}")
    
    # Test extraction
    extraction_success = test_extraction(args.url, args.verbose)
    
    # If extraction failed or extract-only is set, don't test download
    if not extraction_success:
        logger.error("Information extraction failed, skipping download test")
        return 1
    
    if args.extract_only:
        logger.info("Skipping download test as requested")
        return 0
    
    # Test download
    download_success = test_download(args.url, args.verbose, args.format)
    
    # Retry with simpler format if requested and initial download failed
    if not download_success and args.retry:
        logger.info("Retrying download with simpler format options...")
        download_success = test_download(args.url, args.verbose, "worst")
    
    if extraction_success and download_success:
        logger.info("All tests passed successfully")
        return 0
    else:
        logger.error("One or more tests failed")
        return 1

if __name__ == "__main__":
    sys.exit(main())