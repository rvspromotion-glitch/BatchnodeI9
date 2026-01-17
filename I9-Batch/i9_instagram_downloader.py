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
from datetime import datetime
import tempfile

# Try to import instaloader - will be None if not installed
try:
    import instaloader
    INSTALOADER_AVAILABLE = True
except ImportError:
    instaloader = None
    INSTALOADER_AVAILABLE = False
    print("Warning: instaloader not installed. Instagram Downloader node will have limited functionality.")
    print("Install with: pip install instaloader>=4.10.0")

# API Routes for Instagram downloader
@server.PromptServer.instance.routes.post("/i9/instagram/download")
async def download_instagram_profile(request):
    """Download images from Instagram profile"""
    try:
        # Check if instaloader is available
        if not INSTALOADER_AVAILABLE:
            return web.json_response({
                'success': False,
                'error': 'instaloader not installed. Run: pip install instaloader>=4.10.0'
            }, status=500)

        data = await request.json()
        profile_url = data.get('profile_url', '')
        download_mode = data.get('download_mode', 'all')
        start_index = data.get('start_index', 0)
        end_index = data.get('end_index', 100)
        start_date = data.get('start_date', '')
        end_date = data.get('end_date', '')

        if not profile_url:
            return web.json_response({
                'success': False,
                'error': 'No profile URL provided'
            }, status=400)

        # Extract username from URL
        username = profile_url.strip().rstrip('/').split('/')[-1]
        if username.startswith('@'):
            username = username[1:]

        # Setup directories
        input_dir = folder_paths.get_input_directory()
        pool_dir = os.path.join(input_dir, "I9_ImagePool")
        os.makedirs(pool_dir, exist_ok=True)

        # Use temp directory for initial download
        temp_dir = tempfile.mkdtemp()

        try:
            # Initialize Instaloader
            L = instaloader.Instaloader(
                download_videos=False,
                download_video_thumbnails=False,
                download_geotags=False,
                download_comments=False,
                save_metadata=False,
                compress_json=False,
                post_metadata_txt_pattern='',
                dirname_pattern=temp_dir,
                filename_pattern='{shortcode}',
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            )

            # Try to load session from ComfyUI input directory
            session_file = os.path.join(input_dir, "instagram_session")
            if os.path.exists(session_file):
                try:
                    L.load_session_from_file(username=None, filename=session_file)
                    print(f"[Instagram] Loaded saved session from {session_file}")
                except Exception as e:
                    print(f"[Instagram] Could not load session: {e}")
            else:
                # Return error with instructions
                shutil.rmtree(temp_dir, ignore_errors=True)
                return web.json_response({
                    'success': False,
                    'error': f'Instagram requires login. Please create a session file:\n\n'
                            f'1. Install instaloader: pip install instaloader\n'
                            f'2. Run in terminal: instaloader --login YOUR_USERNAME\n'
                            f'3. Copy session file to: {input_dir}/instagram_session\n\n'
                            f'Session file should be named: instagram_session (no extension)\n\n'
                            f'Alternatively, you can download Instagram posts manually and use the regular batch processing node.'
                }, status=401)

            # Load profile
            profile = instaloader.Profile.from_username(L.context, username)

            downloaded_files = []
            post_count = 0

            # Download posts based on mode
            for post in profile.get_posts():
                # Check if we should download this post based on mode
                should_download = False

                if download_mode == 'all':
                    should_download = True
                elif download_mode == 'sequence':
                    if start_index <= post_count < end_index:
                        should_download = True
                elif download_mode == 'timeframe':
                    if start_date and end_date:
                        try:
                            post_date = post.date_utc.strftime('%Y-%m-%d')
                            if start_date <= post_date <= end_date:
                                should_download = True
                        except:
                            pass

                if should_download:
                    try:
                        # Download the post
                        L.download_post(post, target=temp_dir)

                        # Find downloaded images and move to pool
                        for filename in os.listdir(temp_dir):
                            if filename.endswith(('.jpg', '.jpeg', '.png')):
                                src_path = os.path.join(temp_dir, filename)

                                # Generate unique filename
                                base, ext = os.path.splitext(filename)
                                final_filename = f"ig_{username}_{filename}"
                                counter = 1
                                while os.path.exists(os.path.join(pool_dir, final_filename)):
                                    final_filename = f"ig_{username}_{base}_{counter}{ext}"
                                    counter += 1

                                dst_path = os.path.join(pool_dir, final_filename)
                                shutil.move(src_path, dst_path)
                                downloaded_files.append(final_filename)
                    except Exception as e:
                        print(f"Error downloading post: {e}")
                        continue

                post_count += 1

                # Stop if we've passed the sequence range
                if download_mode == 'sequence' and post_count >= end_index:
                    break

            # Cleanup temp directory
            shutil.rmtree(temp_dir, ignore_errors=True)

            return web.json_response({
                'success': True,
                'files': downloaded_files,
                'count': len(downloaded_files)
            })

        except Exception as e:
            # Cleanup on error
            shutil.rmtree(temp_dir, ignore_errors=True)
            return web.json_response({
                'success': False,
                'error': f'Error downloading from Instagram: {str(e)}'
            }, status=500)

    except Exception as e:
        return web.json_response({
            'success': False,
            'error': str(e)
        }, status=500)


class I9_InstagramDownloader:
    """Download images from Instagram profiles"""

    def __init__(self):
        self.download_cache = {}

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "profile_url": ("STRING", {"default": "https://instagram.com/username", "multiline": False}),
                "download_mode": (["Download All", "Download by Sequence", "Download by Timeframe"], {"default": "Download All"}),
                "mode": (["Batch Tensor", "Sequential"], {"default": "Batch Tensor"}),
            },
            "optional": {
                "start_index": ("INT", {"default": 0, "min": 0, "max": 9999, "step": 1}),
                "end_index": ("INT", {"default": 100, "min": 1, "max": 9999, "step": 1}),
                "start_date": ("STRING", {"default": "2024-01-01", "multiline": False}),
                "end_date": ("STRING", {"default": "2024-12-31", "multiline": False}),
                "resize_mode": (["Center Crop", "Letterbox", "Stretch", "Fit to Largest"], {"default": "Center Crop"}),
                "batch_index": ("INT", {"default": 0, "min": 0, "max": 9999, "step": 1}),
                "width": ("INT", {"default": 512, "min": 64, "max": 8192, "step": 8}),
                "height": ("INT", {"default": 512, "min": 64, "max": 8192, "step": 8}),
            },
            "hidden": {
                "node_id": "UNIQUE_ID",
            }
        }

    RETURN_TYPES = ("IMAGE", "INT", "INT", "STRING")
    RETURN_NAMES = ("images", "index", "total", "info")
    FUNCTION = "load_images"
    CATEGORY = "I9/Social"

    def load_images(self, profile_url="", download_mode="Download All", mode="Batch Tensor",
                   start_index=0, end_index=100, start_date="2024-01-01", end_date="2024-12-31",
                   resize_mode="Center Crop", batch_index=0, width=512, height=512, node_id=None):

        print(f"\n{'='*60}")
        print(f"[I9 Instagram Downloader] Profile: {profile_url}")
        print(f"[I9 Instagram Downloader] Download Mode: {download_mode} | Output Mode: {mode}")

        # Get images from pool
        input_dir = folder_paths.get_input_directory()
        pool_dir = os.path.join(input_dir, "I9_ImagePool")

        if not os.path.exists(pool_dir):
            empty = torch.zeros((1, 64, 64, 3), dtype=torch.float32)
            return (empty, 0, 0, "No images in pool. Use the download interface to fetch Instagram images.")

        # Get all images from pool
        image_files = sorted([f for f in os.listdir(pool_dir)
                            if f.lower().endswith(('.jpg', '.jpeg', '.png', '.webp'))])

        if not image_files:
            empty = torch.zeros((1, 64, 64, 3), dtype=torch.float32)
            return (empty, 0, 0, "No images in pool. Use the download interface to fetch Instagram images.")

        # Process images
        if mode == "Sequential":
            return self._load_sequential(pool_dir, image_files, batch_index, resize_mode, width, height)
        else:
            return self._load_batch(pool_dir, image_files, resize_mode, width, height)

    def _load_sequential(self, pool_dir, image_files, batch_index, resize_mode, width, height):
        """Load one image at a time in sequential mode"""
        total_count = len(image_files)

        if batch_index >= total_count:
            empty = torch.zeros((1, 64, 64, 3), dtype=torch.float32)
            return (empty, batch_index, total_count, "Index out of range")

        filename = image_files[batch_index]
        img_path = os.path.join(pool_dir, filename)

        try:
            img = Image.open(img_path).convert('RGB')
            img_tensor = torch.from_numpy(np.array(img).astype(np.float32) / 255.0)

            if img_tensor.shape[0] != height or img_tensor.shape[1] != width:
                img_tensor = self._resize_image(img_tensor, width, height, resize_mode)

            img_tensor = img_tensor.unsqueeze(0)
            info = f"[{batch_index + 1}/{total_count}] {filename}"
            return (img_tensor, batch_index, total_count, info)
        except Exception as e:
            empty = torch.zeros((1, 64, 64, 3), dtype=torch.float32)
            return (empty, batch_index, total_count, f"Error loading {filename}: {e}")

    def _load_batch(self, pool_dir, image_files, resize_mode, target_width, target_height):
        """Load all images as a batch tensor"""
        loaded_images = []

        for filename in image_files:
            img_path = os.path.join(pool_dir, filename)

            try:
                img = Image.open(img_path).convert('RGB')
                img_tensor = torch.from_numpy(np.array(img).astype(np.float32) / 255.0)

                if img_tensor.shape[0] != target_height or img_tensor.shape[1] != target_width:
                    img_tensor = self._resize_image(img_tensor, target_width, target_height, resize_mode)

                loaded_images.append(img_tensor)
            except Exception as e:
                print(f"Error loading {filename}: {e}")
                continue

        if not loaded_images:
            empty = torch.zeros((1, 64, 64, 3), dtype=torch.float32)
            return (empty, 0, 0, "Failed to load any images")

        batch_tensor = torch.stack(loaded_images, dim=0)
        return (batch_tensor, 0, len(loaded_images), f"Loaded {len(loaded_images)} images from Instagram")

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
        """Force update when pool contents change"""
        input_dir = folder_paths.get_input_directory()
        pool_dir = os.path.join(input_dir, "I9_ImagePool")

        if not os.path.exists(pool_dir):
            return "empty"

        files = sorted(os.listdir(pool_dir))
        m = hashlib.sha256()
        for f in files:
            fpath = os.path.join(pool_dir, f)
            if os.path.isfile(fpath):
                m.update(f.encode())
                m.update(str(os.path.getmtime(fpath)).encode())

        return m.hexdigest()


NODE_CLASS_MAPPINGS = {"I9_InstagramDownloader": I9_InstagramDownloader}
NODE_DISPLAY_NAME_MAPPINGS = {"I9_InstagramDownloader": "📷 I9 Instagram Downloader"}
