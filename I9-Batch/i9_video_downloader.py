import torch
import numpy as np
from PIL import Image
import os
import json
import hashlib
import folder_paths
import comfy.utils
import server
from aiohttp import web
import shutil
import tempfile
import subprocess

# Try to import cv2 - will be None if not installed
try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    cv2 = None
    CV2_AVAILABLE = False
    print("Warning: opencv-python not installed. Video Downloader node will have limited functionality.")
    print("Install with: pip install opencv-python>=4.8.0")

# Try to import yt_dlp - will be None if not installed
try:
    import yt_dlp
    YT_DLP_AVAILABLE = True
except ImportError:
    yt_dlp = None
    YT_DLP_AVAILABLE = False
    print("Warning: yt-dlp not installed. Video Downloader node will have limited functionality.")
    print("Install with: pip install yt-dlp>=2023.10.0")

# API Routes for video downloader
@server.PromptServer.instance.routes.post("/i9/videodownload/fetch")
async def download_single_video(request):
    """Download a single video from Instagram Reels or TikTok"""
    try:
        # Check if required dependencies are available
        if not YT_DLP_AVAILABLE:
            return web.json_response({
                'success': False,
                'error': 'yt-dlp not installed. Run: pip install yt-dlp>=2023.10.0'
            }, status=500)

        if not CV2_AVAILABLE:
            return web.json_response({
                'success': False,
                'error': 'opencv-python not installed. Run: pip install opencv-python>=4.8.0'
            }, status=500)

        data = await request.json()
        video_url = data.get('video_url', '')
        download_type = data.get('download_type', 'video')
        frame_number = data.get('frame_number', 0)

        if not video_url:
            return web.json_response({
                'success': False,
                'error': 'No video URL provided'
            }, status=400)

        # Setup directories
        input_dir = folder_paths.get_input_directory()

        if download_type == 'video':
            pool_dir = os.path.join(input_dir, "I9_VideoPool")
        else:
            pool_dir = os.path.join(input_dir, "I9_ImagePool")

        os.makedirs(pool_dir, exist_ok=True)

        # Use temp directory for initial download
        temp_dir = tempfile.mkdtemp()

        try:
            # Determine platform from URL
            platform = 'unknown'
            if 'instagram.com' in video_url or 'instagr.am' in video_url:
                platform = 'instagram'
            elif 'tiktok.com' in video_url:
                platform = 'tiktok'

            # Configure yt-dlp options
            ydl_opts = {
                'format': 'best',
                'outtmpl': os.path.join(temp_dir, '%(id)s.%(ext)s'),
                'quiet': False,
                'no_warnings': False,
            }

            # Check for cookies file (for age-restricted or login-required content)
            cookies_file = os.path.join(input_dir, "cookies.txt")
            if os.path.exists(cookies_file):
                ydl_opts['cookiefile'] = cookies_file
                print(f"[yt-dlp] Using cookies from {cookies_file}")
            else:
                print(f"[yt-dlp] No cookies.txt found at {cookies_file}")
                print("[yt-dlp] Note: Instagram and age-restricted content may require cookies")

            # Download video
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(video_url, download=True)
                video_id = info.get('id', 'video')
                video_ext = info.get('ext', 'mp4')
                temp_video_path = os.path.join(temp_dir, f"{video_id}.{video_ext}")

                if download_type == 'video':
                    # Move full video to pool
                    final_filename = f"{platform}_{video_id}.{video_ext}"
                    counter = 1
                    while os.path.exists(os.path.join(pool_dir, final_filename)):
                        final_filename = f"{platform}_{video_id}_{counter}.{video_ext}"
                        counter += 1

                    final_path = os.path.join(pool_dir, final_filename)
                    shutil.move(temp_video_path, final_path)

                    # Cleanup
                    shutil.rmtree(temp_dir, ignore_errors=True)

                    return web.json_response({
                        'success': True,
                        'type': 'video',
                        'filename': final_filename,
                        'platform': platform
                    })

                else:  # Extract frame
                    # Extract frame using OpenCV
                    cap = cv2.VideoCapture(temp_video_path)

                    if not cap.isOpened():
                        shutil.rmtree(temp_dir, ignore_errors=True)
                        return web.json_response({
                            'success': False,
                            'error': 'Could not open downloaded video'
                        }, status=500)

                    # Get total frames
                    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

                    # Validate frame number
                    if frame_number >= total_frames:
                        frame_number = 0  # Default to first frame

                    # Set frame position
                    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_number)

                    # Read frame
                    ret, frame = cap.read()
                    cap.release()

                    if not ret or frame is None:
                        shutil.rmtree(temp_dir, ignore_errors=True)
                        return web.json_response({
                            'success': False,
                            'error': f'Could not extract frame {frame_number}'
                        }, status=500)

                    # Convert BGR to RGB and save as image
                    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    img = Image.fromarray(frame_rgb)

                    # Save to image pool
                    final_filename = f"{platform}_{video_id}_frame{frame_number}.jpg"
                    counter = 1
                    while os.path.exists(os.path.join(pool_dir, final_filename)):
                        final_filename = f"{platform}_{video_id}_frame{frame_number}_{counter}.jpg"
                        counter += 1

                    final_path = os.path.join(pool_dir, final_filename)
                    img.save(final_path, 'JPEG', quality=95)

                    # Cleanup
                    shutil.rmtree(temp_dir, ignore_errors=True)

                    return web.json_response({
                        'success': True,
                        'type': 'frame',
                        'filename': final_filename,
                        'platform': platform,
                        'frame_number': frame_number
                    })

        except Exception as e:
            # Cleanup on error
            shutil.rmtree(temp_dir, ignore_errors=True)

            error_msg = str(e)

            # Check if error is related to authentication/cookies
            if 'login required' in error_msg.lower() or 'cookies' in error_msg.lower() or 'rate-limit' in error_msg.lower():
                return web.json_response({
                    'success': False,
                    'error': f'Authentication required. Please provide cookies:\n\n'
                            f'1. Install browser extension "Get cookies.txt LOCALLY"\n'
                            f'   Chrome: https://chrome.google.com/webstore (search for it)\n'
                            f'   Firefox: https://addons.mozilla.org (search for it)\n\n'
                            f'2. Login to Instagram/TikTok in your browser\n'
                            f'3. Click the extension icon and export cookies.txt\n'
                            f'4. Save cookies.txt to: {input_dir}/cookies.txt\n\n'
                            f'For age-restricted content: Use account with 18+ birthdate\n\n'
                            f'Original error: {error_msg}'
                }, status=401)

            return web.json_response({
                'success': False,
                'error': f'Download failed: {error_msg}'
            }, status=500)

    except Exception as e:
        return web.json_response({
            'success': False,
            'error': str(e)
        }, status=500)


class I9_VideoDownloader:
    """Download videos from Instagram Reels or TikTok"""

    def __init__(self):
        self.last_downloaded = None

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "video_url": ("STRING", {"default": "https://www.instagram.com/reel/...", "multiline": False}),
                "download_type": (["Extract Frame", "Download Video"], {"default": "Extract Frame"}),
                "frame_number": ("INT", {"default": 0, "min": 0, "max": 999999, "step": 1}),
            },
            "optional": {
                "resize_mode": (["Center Crop", "Letterbox", "Stretch", "Fit to Largest"], {"default": "Center Crop"}),
                "width": ("INT", {"default": 512, "min": 64, "max": 8192, "step": 8}),
                "height": ("INT", {"default": 512, "min": 64, "max": 8192, "step": 8}),
            },
        }

    RETURN_TYPES = ("IMAGE", "STRING")
    RETURN_NAMES = ("image", "info")
    FUNCTION = "download_video"
    CATEGORY = "I9/Social"

    def download_video(self, video_url="", download_type="Extract Frame", frame_number=0,
                      resize_mode="Center Crop", width=512, height=512):

        print(f"\n{'='*60}")
        print(f"[I9 Video Downloader] URL: {video_url}")
        print(f"[I9 Video Downloader] Type: {download_type} | Frame: {frame_number}")

        if not video_url or video_url.startswith("https://www.instagram.com/reel/..."):
            empty = torch.zeros((1, 64, 64, 3), dtype=torch.float32)
            return (empty, "Please enter a video URL")

        # For "Extract Frame", we need to look for the extracted frame in ImagePool
        # For "Download Video", we just save to VideoPool and return a placeholder
        input_dir = folder_paths.get_input_directory()

        if download_type == "Extract Frame":
            pool_dir = os.path.join(input_dir, "I9_ImagePool")

            # Look for most recent frame extraction
            if os.path.exists(pool_dir):
                image_files = sorted(
                    [f for f in os.listdir(pool_dir) if f.lower().endswith(('.jpg', '.jpeg', '.png'))],
                    key=lambda x: os.path.getmtime(os.path.join(pool_dir, x)),
                    reverse=True
                )

                if image_files:
                    # Load the most recent image
                    img_path = os.path.join(pool_dir, image_files[0])

                    try:
                        img = Image.open(img_path).convert('RGB')
                        img_tensor = torch.from_numpy(np.array(img).astype(np.float32) / 255.0)

                        if img_tensor.shape[0] != height or img_tensor.shape[1] != width:
                            img_tensor = self._resize_image(img_tensor, width, height, resize_mode)

                        img_tensor = img_tensor.unsqueeze(0)
                        return (img_tensor, f"Extracted frame {frame_number} from {video_url}")
                    except Exception as e:
                        empty = torch.zeros((1, 64, 64, 3), dtype=torch.float32)
                        return (empty, f"Error loading frame: {e}")

            empty = torch.zeros((1, 64, 64, 3), dtype=torch.float32)
            return (empty, "No frame extracted. Use the download interface.")

        else:  # Download Video
            # Video is saved to VideoPool, return placeholder
            empty = torch.zeros((1, 64, 64, 3), dtype=torch.float32)
            return (empty, f"Video downloaded to I9_VideoPool from {video_url}")

    def _resize_image(self, img_tensor, target_width, target_height, resize_mode):
        if resize_mode == "Stretch":
            return comfy.utils.common_upscale(img_tensor.movedim(-1, 0).unsqueeze(0), target_width, target_height, "bilinear", "disabled").squeeze(0).movedim(0, -1)
        if resize_mode == "Center Crop":
            return comfy.utils.common_upscale(img_tensor.movedim(-1, 0).unsqueeze(0), target_width, target_height, "bilinear", "center").squeeze(0).movedim(0, -1)
        if resize_mode == "Letterbox":
            scale = min(target_width / img_tensor.shape[1], target_height / img_tensor.shape[0])
            new_w, new_h = int(img_tensor.shape[1] * scale), int(img_tensor.shape[0] * scale)
            resized = comfy.utils.common_upscale(img_tensor.movedim(-1, 0).unsqueeze(0), new_w, new_h, "bilinear", "disabled").squeeze(0).movedim(0, -1)
            canvas = torch.zeros((target_height, target_width, 3), dtype=torch.float32)
            pad_top, pad_left = (target_height - new_h) // 2, (target_width - new_w) // 2
            canvas[pad_top:pad_top+new_h, pad_left:pad_left+new_w, :] = resized
            return canvas
        return img_tensor

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        """Force refresh when URL changes"""
        video_url = kwargs.get('video_url', '')
        return hashlib.sha256(video_url.encode()).hexdigest()


NODE_CLASS_MAPPINGS = {"I9_VideoDownloader": I9_VideoDownloader}
NODE_DISPLAY_NAME_MAPPINGS = {"I9_VideoDownloader": "🎥 I9 Video Downloader"}
