
from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse, FileResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import yt_dlp
import os
import json
import uuid
from urllib.parse import urlparse, parse_qs
import threading
import time
import platform
import re
from pathlib import Path

def is_facebook_url_valid(url):
    """Enhanced Facebook URL validation"""
    if not url:
        return False
        
    url_lower = url.lower()
    valid_patterns = [
        'facebook.com/watch',
        'facebook.com/reel',
        'facebook.com/videos',
        'facebook.com/posts',
        'm.facebook.com',
        'fb.watch',
    ]
        
    return any(pattern in url_lower for pattern in valid_patterns) or 'facebook.com' in url_lower

# Initialize FastAPI app
app = FastAPI(title="Facebook Video Downloader")

# Get the current directory and create absolute paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOADS_DIR = os.path.join(BASE_DIR, 'uploads')
OUTPUTS_DIR = os.path.join(BASE_DIR, 'outputs')
STATIC_DIR = os.path.join(BASE_DIR, 'static')
TEMPLATES_DIR = os.path.join(BASE_DIR, 'templates')

# Setup templates and static files
templates = Jinja2Templates(directory=TEMPLATES_DIR)
app.mount("/static", StaticFiles(directory="static"), name="static")

# Create necessary directories with proper permissions
def create_directories():
    directories = [UPLOADS_DIR, OUTPUTS_DIR, STATIC_DIR, TEMPLATES_DIR]
    for directory in directories:
        try:
            os.makedirs(directory, exist_ok=True)
            if platform.system() != 'Windows':
                os.chmod(directory, 0o755)
            print(f"✅ Created/verified directory: {directory}")
        except Exception as e:
            print(f"❌ Error creating directory {directory}: {e}")

# Initialize directories
create_directories()

# Store download progress and completed files - OPTIMIZED
download_progress = {}
completed_downloads = {}
filename_cache = {}

# Thread locks for thread safety
progress_lock = threading.Lock()

# Pydantic models for request/response
class ExtractInfoRequest(BaseModel):
    url: str

class DownloadRequest(BaseModel):
    url: str
    format_id: str

def generate_safe_filename(title, max_length=40):
    """Generate a safe, predictable filename that matches yt-dlp output"""
    if not title or title.strip() == '':
        return f"facebook_video_{int(time.time())}"
        
    # Create cache key
    if title in filename_cache:
        return filename_cache[title]
        
    # Clean the title
    safe_name = title.strip()
        
    # Remove/replace problematic characters - keep only alphanumeric, spaces, hyphens
    safe_name = re.sub(r'[^\w\s\-]', '', safe_name)
        
    # Replace multiple spaces/underscores with single underscore
    safe_name = re.sub(r'[\s_]+', '_', safe_name)
        
    # Remove leading/trailing separators
    safe_name = safe_name.strip('_-')
        
    # Truncate to max length
    if len(safe_name) > max_length:
        safe_name = safe_name[:max_length].rstrip('_-')
        
    # Ensure minimum length
    if len(safe_name) < 3:
        safe_name = f"facebook_video_{int(time.time())}"
        
    # Cache the result
    filename_cache[title] = safe_name
    return safe_name

def find_completed_file(expected_filename, base_name):
    """Find the actual completed file, handling yt-dlp naming variations"""
    expected_path = os.path.join(OUTPUTS_DIR, expected_filename)
        
    # Check exact match first
    if os.path.exists(expected_path) and os.path.getsize(expected_path) > 0:
        return expected_filename
        
    # Search for variations
    try:
        search_patterns = [
            f"{base_name}.mp4",
            f"{base_name}.webm",
            f"{base_name}.mkv",
        ]
                
        for filename in os.listdir(OUTPUTS_DIR):
            file_path = os.path.join(OUTPUTS_DIR, filename)
                        
            # Skip if not a file or empty
            if not os.path.isfile(file_path) or os.path.getsize(file_path) == 0:
                continue
                        
            # Check if it matches our patterns and is recent
            for pattern in search_patterns:
                if filename == pattern:
                    file_age = time.time() - os.path.getmtime(file_path)
                    if file_age < 600:  # Within last 10 minutes
                        return filename
                                        
            # Also check if base_name is in filename (for yt-dlp variations)
            if base_name in filename and filename.endswith('.mp4'):
                file_age = time.time() - os.path.getmtime(file_path)
                if file_age < 600:
                    return filename
                    
    except Exception as e:
        print(f"⚠️ Error searching for completed file: {e}")
        return None

def cleanup_intermediate_files(base_name):
    """Clean up intermediate files created during download/merge"""
    try:
        for filename in os.listdir(OUTPUTS_DIR):
            file_path = os.path.join(OUTPUTS_DIR, filename)
                        
            if os.path.isfile(file_path):
                # Remove intermediate files (contain format IDs)
                if (base_name in filename and 
                     ('f' in filename and any(ext in filename for ext in ['.f', '.part', '.ytdl', '.tmp']))):
                    try:

                        os.remove(file_path)
                        print(f"🗑️ Cleaned up intermediate file: {filename}")
                    except Exception as e:
                        print(f"⚠️ Could not remove {filename}: {e}")
                        
    except Exception as e:
        print(f"⚠️ Error during cleanup: {e}")

class OptimizedProgressHook:
    def __init__(self, download_id, expected_filename, base_name):
        self.download_id = download_id
        self.expected_filename = expected_filename
        self.base_name = base_name
        self.last_update = time.time()
        self.last_percent = 0
        self.update_threshold = 1.0  # Only update if progress changes by 1% or more
        self.time_threshold = 2.0    # Or if 2 seconds have passed
        
    def __call__(self, d):
        try:
            current_time = time.time()
                        
            if d['status'] == 'downloading':
                # Extract progress information
                downloaded = d.get('downloaded_bytes', 0) or 0
                total = d.get('total_bytes', 0) or d.get('total_bytes_estimate', 0) or 0
                                
                # Calculate percentage
                if total > 0:
                    percent = (downloaded / total) * 100
                else:
                    percent_str = d.get('_percent_str', '0%')
                    try:
                        percent = float(percent_str.replace('%', '').strip()) if percent_str != 'N/A' else 0
                    except:
                        percent = 0
                                
                # Only update if significant change or time threshold passed
                percent_change = abs(percent - self.last_percent)
                time_since_update = current_time - self.last_update
                                
                if percent_change >= self.update_threshold or time_since_update >= self.time_threshold:
                    with progress_lock:
                        download_progress[self.download_id] = {
                            'status': 'downloading',
                            'percent': min(percent, 99),
                            'speed': d.get('_speed_str', 'N/A') or 'N/A',
                            'eta': d.get('_eta_str', 'N/A') or 'N/A',
                            'downloaded': downloaded,
                            'total': total,
                            'last_update': current_time,
                            'message': 'Downloading...'
                        }
                                        
                    self.last_percent = percent
                    self.last_update = current_time
                        
            elif d['status'] == 'finished':
                filename = os.path.basename(d['filename'])
                print(f"✅ File finished: {filename}")
                                
                # Check if this is the final file (not intermediate)
                if not ('f' in filename and any(ext in filename for ext in ['v.', 'a.'])):
                    self._mark_completed(filename, d['filename'], current_time)
                        
            elif d['status'] == 'error':
                with progress_lock:
                    download_progress[self.download_id] = {
                        'status': 'error',
                        'error': d.get('error', 'Unknown download error'),
                        'percent': 0,
                        'last_update': current_time,
                        'message': 'Download failed'
                    }
                print(f"❌ Download error: {d.get('error', 'Unknown error')}")
                        
        except Exception as e:
            print(f"❌ Progress hook error: {e}")
    
    def _mark_completed(self, filename, filepath, current_time):
        """Mark download as completed"""
        with progress_lock:
            completed_downloads[self.download_id] = {
                'filename': filename,
                'filepath': filepath,
                'completed_at': current_time
            }
                        
            download_progress[self.download_id] = {
                'status': 'finished',
                'percent': 100,
                'filename': filename,
                'filepath': filepath,
                'last_update': current_time,
                'message': 'Download completed!'
            }
                
        print(f"🎉 DOWNLOAD COMPLETED: {filename}")
                
        # Clean up intermediate files
        cleanup_intermediate_files(self.base_name)

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/extract_info")
async def extract_info(request_data: ExtractInfoRequest):
    try:
        url = request_data.url.strip()
        
        if not url:
            raise HTTPException(status_code=400, detail='Please provide a valid URL')
        
        # FIXED: Enhanced URL validation and normalization
        normalized_url = normalize_facebook_url(url)
        if not normalized_url:
            raise HTTPException(status_code=400, detail='Please provide a valid Facebook video URL. Supported formats: facebook.com/watch, facebook.com/reel, fb.watch, or direct video links')
        
        print(f"🔍 Original URL: {url}")
        print(f"🔗 Normalized URL: {normalized_url}")
        
        # Try multiple extraction strategies
        video_data = None
        last_error = None
        
        # Strategy 1: Standard extraction with updated options
        try:
            video_data = await extract_with_strategy_1(normalized_url)
            if video_data:
                print("✅ Strategy 1 (Standard) succeeded")
                return video_data
        except Exception as e:
            last_error = str(e)
            print(f"⚠️ Strategy 1 failed: {e}")
        
        # Strategy 2: Alternative extraction method
        try:
            video_data = await extract_with_strategy_2(normalized_url)
            if video_data:
                print("✅ Strategy 2 (Alternative) succeeded")
                return video_data
        except Exception as e:
            last_error = str(e)
            print(f"⚠️ Strategy 2 failed: {e}")
        
        # Strategy 3: Generic extractor fallback
        try:
            video_data = await extract_with_strategy_3(normalized_url)
            if video_data:
                print("✅ Strategy 3 (Generic) succeeded")
                return video_data
        except Exception as e:
            last_error = str(e)
            print(f"⚠️ Strategy 3 failed: {e}")
        
        # If all strategies fail, provide helpful error message
        error_message = get_helpful_error_message(last_error, url)
        raise HTTPException(status_code=400, detail=error_message)
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Unexpected error in extract_info: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f'An unexpected error occurred: {str(e)}')

def normalize_facebook_url(url):
    """FIXED: Normalize Facebook URLs to improve extraction success"""
    try:
        # Don't strip query parameters for Facebook URLs - they contain the video ID!
        if 'fb.watch' in url:
            return url
        elif 'facebook.com' in url or 'm.facebook.com' in url:
            # Convert mobile URLs to desktop but KEEP the parameters
            url = url.replace('m.facebook.com', 'www.facebook.com')
            
            # Handle different video URL patterns - PRESERVE video IDs
            if '/watch' in url or '/reel' in url or '/videos' in url or '/posts' in url:
                return url
            else:
                # Try to extract video ID from various formats
                import re
                video_id_match = re.search(r'(\d{15,})', url)
                if video_id_match:
                    video_id = video_id_match.group(1)
                    return f"https://www.facebook.com/watch/?v={video_id}"
        
        # Check if it's a valid Facebook domain
        parsed = urlparse(url)
        valid_domains = ['facebook.com', 'www.facebook.com', 'm.facebook.com', 'fb.watch']
        if any(domain in parsed.netloc.lower() for domain in valid_domains):
            return url
        
        return None
    except Exception as e:
        print(f"⚠️ URL normalization error: {e}")
        return url if 'facebook.com' in url or 'fb.watch' in url else None

async def extract_with_strategy_1(url):
    """Standard extraction with updated yt-dlp options"""
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': False,
        'skip_download': True,
        'no_check_certificate': True,
        'socket_timeout': 30,
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'extractor_args': {
            'facebook': {
                'api_version': 'v18.0'
            }
        },
        'http_headers': {
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-us,en;q=0.5',
            'Sec-Fetch-Mode': 'navigate',
        }
    }
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        if info and info.get('formats'):
            return process_video_info(info)
    return None

async def extract_with_strategy_2(url):
    """Alternative extraction with different options"""
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': False,
        'skip_download': True,
        'no_check_certificate': True,
        'socket_timeout': 45,
        'user_agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'extractor_args': {
            'facebook': {
                'api_version': 'v17.0'
            }
        },
        'cookiefile': None,  # Don't use cookies
        'age_limit': None,
    }
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        if info and info.get('formats'):
            return process_video_info(info)
    return None

async def extract_with_strategy_3(url):
    """Generic extractor fallback"""
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': False,
        'skip_download': True,
        'no_check_certificate': True,
        'socket_timeout': 60,
        'user_agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'extractor_args': {
            'generic': {
                'force_generic_extractor': True
            }
        }
    }
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        if info and info.get('formats'):
            return process_video_info(info)
    return None

def process_video_info(info):
    """Process extracted video information"""
    if not info:
        return None
        
    # Prepare video data with safe defaults
    video_data = {
        'title': info.get('title') or info.get('id') or 'Facebook Video',
        'thumbnail': info.get('thumbnail') or '',
        'duration': info.get('duration') or 0,
        'uploader': info.get('uploader') or info.get('channel') or 'Facebook User',
        'view_count': info.get('view_count') or 0,
        'description': (info.get('description') or '')[:200] + '...' if info.get('description') else 'No description available',
        'formats': []
    }
    
    # Process available formats with enhanced logic
    formats = info.get('formats', [])
    if not formats:
        return None
        
    print(f"📊 Found {len(formats)} total formats")
    
    # Enhanced format processing
    processed_formats = process_formats_enhanced(formats)
    
    if not processed_formats:
        return None
        
    video_data['formats'] = processed_formats
    print(f"✅ Successfully processed {len(video_data['formats'])} formats for: {video_data['title']}")
    return video_data

def process_formats_enhanced(formats):
    """Enhanced format processing with better fallbacks"""
    combined_formats = []
    video_only_formats = []
    audio_only_formats = []
    
    for fmt in formats:
        try:
            format_id = fmt.get('format_id', 'unknown')
            ext = fmt.get('ext', 'mp4')
            
            # Skip formats that are clearly not video/audio
            if ext in ['jpg', 'png', 'gif', 'webp']:
                continue
                
            has_video = fmt.get('vcodec') and fmt.get('vcodec') not in ['none', 'null']
            has_audio = fmt.get('acodec') and fmt.get('acodec') not in ['none', 'null']
            
            # Get dimensions with fallbacks
            height = fmt.get('height') or 0
            width = fmt.get('width') or 0
            
            # If no height/width, try to infer from format_note or quality
            if height == 0:
                format_note = fmt.get('format_note', '').lower()
                if '1080' in format_note:
                    height = 1080
                elif '720' in format_note:
                    height = 720
                elif '480' in format_note:
                    height = 480
                elif '360' in format_note:
                    height = 360
                elif '240' in format_note:
                    height = 240
            
            filesize = fmt.get('filesize') or fmt.get('filesize_approx') or 0
            
            if has_video and has_audio and height >= 144:
                # Combined format (video + audio) - PREFERRED
                combined_formats.append({
                    'format_id': format_id,
                    'quality': f"{height}p (Video + Audio)" if height > 0 else "Video + Audio",
                    'ext': ext,
                    'filesize': filesize,
                    'type': 'combined',
                    'height': height,
                    'width': width,
                    'fps': fmt.get('fps') or 0,
                    'vcodec': fmt.get('vcodec', 'unknown'),
                    'acodec': fmt.get('acodec', 'unknown'),
                    'abr': fmt.get('abr') or 0,
                    'priority': 1
                })
            elif has_video and not has_audio and height >= 144:
                # Video only format
                video_only_formats.append({
                    'format_id': format_id,
                    'quality': f"{height}p (Video Only)" if height > 0 else "Video Only",
                    'ext': ext,
                    'filesize': filesize,
                    'type': 'video_only',
                    'height': height,
                    'width': width,
                    'fps': fmt.get('fps') or 0,
                    'vcodec': fmt.get('vcodec', 'unknown'),
                    'priority': 3
                })
            elif has_audio and not has_video:
                # Audio only format
                audio_only_formats.append({
                    'format_id': format_id,
                    'quality': 'Audio Only',
                    'ext': 'mp3' if ext in ['m4a', 'mp3'] else ext,
                    'filesize': filesize,
                    'type': 'audio_only',
                    'acodec': fmt.get('acodec', 'unknown'),
                    'abr': fmt.get('abr') or 0,
                    'priority': 2
                })
            elif not has_video and not has_audio:
                # Sometimes formats don't have codec info but are still valid
                # Try to determine based on other properties
                if height > 0 or width > 0:
                    # Likely video
                    combined_formats.append({
                        'format_id': format_id,
                        'quality': f"{height}p" if height > 0 else "Video",
                        'ext': ext,
                        'filesize': filesize,
                        'type': 'combined',
                        'height': height,
                        'width': width,
                        'fps': fmt.get('fps') or 0,
                        'vcodec': 'unknown',
                        'acodec': 'unknown',
                        'abr': fmt.get('abr') or 0,
                        'priority': 2
                    })
        except Exception as fmt_error:
            print(f"⚠️ Error processing format {fmt.get('format_id', 'unknown')}: {fmt_error}")
            continue
    
    print(f"📊 Processed formats - Combined: {len(combined_formats)}, Video-only: {len(video_only_formats)}, Audio-only: {len(audio_only_formats)}")
    
    # Create best combination if no combined formats exist
    if not combined_formats and video_only_formats and audio_only_formats:
        try:
            best_video = max(video_only_formats, key=lambda x: x.get('height', 0))
            best_audio = max(audio_only_formats, key=lambda x: x.get('abr', 0))
            
            video_size = best_video.get('filesize') or 0
            audio_size = best_audio.get('filesize') or 0
            combined_size = video_size + audio_size if video_size > 0 and audio_size > 0 else 0
            
            combined_formats.append({
                'format_id': f"{best_video['format_id']}+{best_audio['format_id']}",
                'quality': f"{best_video['height']}p (Best Quality + Audio)" if best_video['height'] > 0 else "Best Quality + Audio",
                'ext': 'mp4',
                'filesize': combined_size,
                'type': 'best_combined',
                'height': best_video.get('height', 0),
                'width': best_video.get('width', 0),
                'fps': best_video.get('fps', 0),
                'vcodec': best_video.get('vcodec', 'unknown'),
                'acodec': best_audio.get('acodec', 'unknown'),
                'abr': best_audio.get('abr', 0),
                'priority': 1
            })
            print("✅ Created best combined format")
        except Exception as combine_error:
            print(f"⚠️ Error creating combined format: {combine_error}")
    
    # Combine all formats and sort
    all_formats = combined_formats + video_only_formats + audio_only_formats
    
    if not all_formats:
        return None
    
    # Remove duplicates and sort
    seen_qualities = set()
    unique_formats = []
    
    # Sort by priority first, then by height/quality
    all_formats.sort(key=lambda x: (
        x.get('priority', 999), 
        -x.get('height', 0), 
        -x.get('abr', 0)
    ))
    
    for fmt in all_formats:
        quality_key = fmt['quality']
        if quality_key not in seen_qualities:
            unique_formats.append(fmt)
            seen_qualities.add(quality_key)
            if len(unique_formats) >= 8:  # Increased limit
                break
    
    return unique_formats

def get_helpful_error_message(error_msg, url):
    """Generate helpful error messages based on the error type"""
    error_lower = error_msg.lower() if error_msg else ""
    
    if "no video formats found" in error_lower:
        return """This Facebook video cannot be downloaded. Possible reasons:
• The video is private or restricted
• The video requires login to view
• The video is from a private group or page
• Facebook has changed their video format (this happens frequently)
• The video might be a live stream or story

Try these solutions:
1. Make sure the video is publicly accessible
2. Try copying the URL again from a different browser
3. Check if the video plays without logging in
4. Try a different Facebook video URL format"""
    
    elif "private" in error_lower or "login" in error_lower:
        return "This video is private or requires login. Please try with a public Facebook video that doesn't require authentication."
    
    elif "not available" in error_lower:
        return "This video is not available. It might have been deleted, made private, or restricted in your region."
    
    elif "timeout" in error_lower:
        return "Connection timeout. Please check your internet connection and try again."
    
    else:
        return f"""Unable to extract video information. This could be due to:
• Facebook's frequent changes to their video system
• The video being private or restricted
• Network connectivity issues
• The video URL format not being supported

Error details: {error_msg}

Please try:
1. A different Facebook video URL
2. Checking if the video is publicly accessible
3. Refreshing the page and trying again"""

@app.post("/download")
async def download_video(request_data: DownloadRequest, background_tasks: BackgroundTasks):
    try:
        url = request_data.url.strip()
        format_id = request_data.format_id
                
        if not url or not format_id:
            raise HTTPException(status_code=400, detail='URL and format are required')
                
        # Generate unique download ID
        download_id = str(uuid.uuid4())
                
        # Initialize progress
        with progress_lock:
            download_progress[download_id] = {
                'status': 'starting',
                'percent': 0,
                'message': 'Initializing...'
            }
                
        print(f"🚀 Starting download with ID: {download_id}")
                
        # Start download in background
        background_tasks.add_task(download_video_background, url, format_id, download_id)
                
        return {'download_id': download_id}
                
    except Exception as e:
        print(f"❌ Error in download_video: {e}")
        raise HTTPException(status_code=500, detail=f'Download failed: {str(e)}')

def download_video_background(url, format_id, download_id):
    try:
        print(f"📥 Background download started for ID: {download_id}")
        print(f"🔗 URL: {url}")
        print(f"🎬 Format ID: {format_id}")
                
        # Set initial status
        with progress_lock:
            download_progress[download_id] = {
                'status': 'starting',
                'percent': 0,
                'message': 'Getting video information...',
                'last_update': time.time()
            }
                
        # Get video info for filename
        try:
            with yt_dlp.YoutubeDL({'quiet': True, 'no_warnings': True, 'socket_timeout': 10}) as ydl_info:
                info = ydl_info.extract_info(url, download=False)
                original_title = info.get('title', 'facebook_video')
                safe_filename = generate_safe_filename(original_title)
        except Exception as info_error:
            print(f"⚠️ Error getting video info for filename: {info_error}")
            safe_filename = f"facebook_video_{int(time.time())}"
                
        print(f"📁 Generated safe filename: {safe_filename}")
                
        # Expected final filename
        expected_final_filename = f"{safe_filename}.mp4"
                
        # Determine the best format strategy
        final_format = format_id
                
        # Check if it's a combined format (video+audio)
        if '+' in format_id:
            # This is our custom best_combined format
            video_format, audio_format = format_id.split('+')
            final_format = f"{video_format}+{audio_format}"
            print(f"🎬 Using combined format: {final_format}")
        elif 'Video Only' in format_id or 'video_only' in str(format_id):
            # For video-only formats, merge with best audio
            actual_format_id = format_id.split()[0] if ' ' in format_id else format_id
            final_format = f"{actual_format_id}+bestaudio"
            print(f"🎬 Merging video with audio: {final_format}")
        else:
            # Use the format as-is
            print(f"🎬 Using direct format: {final_format}")
                
        # Update progress
        with progress_lock:
            download_progress[download_id] = {
                'status': 'preparing',
                'percent': 5,
                'message': 'Preparing download...',
                'last_update': time.time()
            }
                
        # Create progress hook
        progress_hook = OptimizedProgressHook(download_id, expected_final_filename, safe_filename)
                
        # Configure yt-dlp options for download with MAXIMUM OPTIMIZATIONS
        ydl_opts = {
            'format': final_format,
            'outtmpl': os.path.join(OUTPUTS_DIR, f'{safe_filename}.%(ext)s'),
            'progress_hooks': [progress_hook],
            'quiet': False,
            'no_warnings': False,
            'no_check_certificate': True,
            'writeinfojson': False,
            'writesubtitles': False,
            'writeautomaticsub': False,
            'restrictfilenames': True,
            'windowsfilenames': True,
                        
            # MAXIMUM SPEED OPTIMIZATIONS
            'concurrent_fragment_downloads': 8,  # Increased for maximum speed
            'fragment_retries': 2,  # Reduced retries for speed
            'retries': 3,  # Reduced retries
            'file_access_retries': 2,
            'http_chunk_size': 4194304,  # 4MB chunks for maximum speed
            'socket_timeout': 20,  # Reduced timeout
            'buffersize': 4194304,  # 4MB buffer
                        
            # FASTEST MERGE OPTIONS - NO RE-ENCODING
            'merge_output_format': 'mp4',
            'postprocessors': [{
                'key': 'FFmpegVideoConvertor',
                'preferedformat': 'mp4',
            }],
            'postprocessor_args': {
                'ffmpeg': [
                    '-c:v', 'copy',  # COPY VIDEO - NO RE-ENCODING (FASTEST)
                    '-c:a', 'copy',  # COPY AUDIO - NO RE-ENCODING (FASTEST)
                    '-movflags', '+faststart',  # Optimize for streaming
                    '-threads', str(min(os.cpu_count() or 4, 8)),  # Use optimal CPU cores
                    '-preset', 'ultrafast',  # Fastest preset
                    '-avoid_negative_ts', 'make_zero'  # Fix timestamp issues
                ]
            },
                        
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
                
        print(f"📁 Downloading: {safe_filename}")
        print(f"🎵 Format: {final_format}")
        print(f"📂 Output directory: {OUTPUTS_DIR}")
        print(f"🎯 Expected final file: {expected_final_filename}")
                
        # Update progress to downloading
        with progress_lock:
            download_progress[download_id] = {
                'status': 'downloading',
                'percent': 10,
                'message': 'Starting download...',
                'last_update': time.time()
            }
                
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            print(f"🚀 Starting yt-dlp download...")
            ydl.download([url])
            print(f"✅ yt-dlp download completed")
                
        # Final verification if hooks didn't catch completion
        if download_id not in completed_downloads:
            print(f"🔍 Verifying completion for: {expected_final_filename}")
                        
            # Look for the completed file
            final_filename = find_completed_file(expected_final_filename, safe_filename)
                        
            if final_filename:
                final_path = os.path.join(OUTPUTS_DIR, final_filename)
                with progress_lock:
                    completed_downloads[download_id] = {
                        'filename': final_filename,
                        'filepath': final_path,
                        'completed_at': time.time()
                    }
                    download_progress[download_id] = {
                        'status': 'finished',
                        'percent': 100,
                        'filename': final_filename,
                        'filepath': final_path,
                        'last_update': time.time(),
                        'message': 'Download completed!'
                    }
                print(f"✅ Verification found completed file: {final_filename}")
                                
                # Clean up intermediate files
                cleanup_intermediate_files(safe_filename)
            else:
                print(f"⚠️ Could not find completed file")
                # List available files for debugging
                try:
                    available_files = [f for f in os.listdir(OUTPUTS_DIR) if f.endswith('.mp4')]
                    print(f"📂 Available MP4 files: {available_files}")
                except Exception as list_error:
                    print(f"⚠️ Error listing files: {list_error}")
                
        print(f"✅ Download process completed for ID: {download_id}")
                
        # Final status check
        with progress_lock:
            final_status = download_progress.get(download_id, {})
        if final_status.get('status') == 'finished':
            print(f"🎉 DOWNLOAD SUCCESS: {final_status.get('filename')}")
        else:
            print(f"⚠️ Download status: {final_status.get('status')} - {final_status.get('message', 'Unknown')}")
            
    except yt_dlp.DownloadError as e:
        error_msg = str(e)
        print(f"❌ yt-dlp error for ID {download_id}: {error_msg}")
        with progress_lock:
            download_progress[download_id] = {
                'status': 'error',
                'error': f'Download failed: {error_msg}',
                'percent': 0,
                'last_update': time.time(),
                'message': 'Download failed'
            }
    except Exception as e:
        print(f"❌ Unexpected error for ID {download_id}: {e}")
        import traceback
        traceback.print_exc()
        with progress_lock:
            download_progress[download_id] = {
                'status': 'error',
                'error': f'Unexpected error: {str(e)}',
                'percent': 0,
                'last_update': time.time(),
                'message': 'Download failed'
            }

@app.get("/progress/{download_id}")
async def get_progress(download_id: str):
    with progress_lock:
        progress = download_progress.get(download_id, {'status': 'not_found'}).copy()
        
    # Check if download is stale (no updates for 2 minutes while downloading) - REDUCED TIMEOUT
    if progress.get('status') in ['downloading', 'merging', 'processing']:
        last_update = progress.get('last_update', 0)
        if time.time() - last_update > 120:  # 2 minutes timeout (reduced from 3)
            print(f"⚠️ Download {download_id} appears stale, checking for completed files...")
                        
            # Check if download actually completed
            if download_id in completed_downloads:
                completed = completed_downloads[download_id]
                progress = {
                    'status': 'finished',
                    'percent': 100,
                    'filename': completed['filename'],
                    'filepath': completed['filepath'],
                    'last_update': time.time(),
                    'message': 'Download completed!'
                }
                with progress_lock:
                    download_progress[download_id] = progress
                print(f"✅ Found completed download after stale detection")
            else:
                # Look for recent MP4 files
                try:
                    files = [f for f in os.listdir(OUTPUTS_DIR) if f.endswith('.mp4')]
                    if files:
                        # Get the most recent file
                        latest_file = max(files, key=lambda f: os.path.getmtime(os.path.join(OUTPUTS_DIR, f)))
                        file_time = os.path.getmtime(os.path.join(OUTPUTS_DIR, latest_file))
                                                
                        # If the file was created recently, assume it's our download
                        if time.time() - file_time < 180:  # Within last 3 minutes
                            progress = {
                                'status': 'finished',
                                'percent': 100,
                                'filename': latest_file,
                                'filepath': os.path.join(OUTPUTS_DIR, latest_file),
                                'last_update': time.time(),
                                'message': 'Download completed!'
                            }
                            with progress_lock:
                                download_progress[download_id] = progress
                                completed_downloads[download_id] = {
                                    'filename': latest_file,
                                    'filepath': os.path.join(OUTPUTS_DIR, latest_file),
                                    'completed_at': time.time()
                                }
                            print(f"✅ Found recent file after stale detection: {latest_file}")
                        else:
                            # Mark as error if no recent files
                            progress = {
                                'status': 'error',
                                'error': 'Download timeout - please try again',
                                'percent': 0,
                                'last_update': time.time(),
                                'message': 'Download timed out'
                            }
                            with progress_lock:
                                download_progress[download_id] = progress
                except Exception as check_error:
                    print(f"⚠️ Error checking for completed files: {check_error}")
                    progress = {
                        'status': 'error',
                        'error': 'Download timeout - please try again',
                        'percent': 0,
                        'last_update': time.time(),
                        'message': 'Download timed out'
                    }
                    with progress_lock:
                        download_progress[download_id] = progress
        
    return progress


# check this 

from fastapi import BackgroundTasks

@app.get("/download_file/{filename}")
async def download_file(filename: str, background_tasks: BackgroundTasks):
    try:
        # Sanitize filename to prevent directory traversal
        safe_filename = os.path.basename(filename)
        file_path = os.path.join(OUTPUTS_DIR, safe_filename)

        print(f"📥 Download request for: {safe_filename}")
        print(f"📁 Looking for file at: {file_path}")

        # Check if the requested file exists
        if not os.path.exists(file_path):
            print(f"❌ File not found: {safe_filename}")
            raise HTTPException(status_code=404, detail='File not found')

        if not os.path.isfile(file_path):
            raise HTTPException(status_code=400, detail='Invalid file')

        print(f"📤 Serving file: {safe_filename}")

        # Add delete task with 0.1 second delay
        background_tasks.add_task(delete_file_after_delay, file_path, delay=0)

        return FileResponse(
            path=file_path,
            filename=safe_filename,
            media_type='application/octet-stream'
        )

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error serving file {filename}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Helper function
import asyncio

async def delete_file_after_delay(file_path: str, delay: float):
    try:
        await asyncio.sleep(delay)
        if os.path.exists(file_path):
            os.remove(file_path)
            print(f"🗑️ Deleted file: {file_path}")
    except Exception as e:
        print(f"⚠️ Failed to delete {file_path}: {e}")






# @app.get("/list_filess")
# async def list_files():
#     try:
#         files = []
#         if os.path.exists(OUTPUTS_DIR):
#             for filename in os.listdir(OUTPUTS_DIR):
#                 file_path = os.path.join(OUTPUTS_DIR, filename)
#                 if os.path.isfile(file_path) and filename.endswith(('.mp4', '.webm', '.mkv')):
#                     file_size = os.path.getsize(file_path)
#                     files.append({
#                         'name': filename,
#                         'size': file_size,
#                         'modified': os.path.getmtime(file_path)
#                     })
        
#         # Sort by modification time (newest first)
#         files.sort(key=lambda x: x['modified'], reverse=True)
#         return files[:10]  # Return only the 10 most recent files
        
#     except Exception as e:
#         print(f"❌ Error listing files: {e}")
#         return []

@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
    return JSONResponse(
        status_code=404,
        content={'error': 'Endpoint not found'}
    )

@app.exception_handler(500)
async def internal_error_handler(request: Request, exc):
    return JSONResponse(
        status_code=500,
        content={'error': 'Internal server error'}
    )

if __name__ == '__main__':
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("app:app", host="0.0.0.0", port=port)