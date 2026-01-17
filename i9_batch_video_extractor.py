import torch
import numpy as np
from PIL import Image
import os
import json
import uuid
import hashlib
import folder_paths
import comfy.utils
import server
from aiohttp import web
import shutil
import cv2

# API Routes for video batch management
@server.PromptServer.instance.routes.post("/i9/video/upload")
async def upload_batch_videos(request):
    """Handle multiple video uploads"""
    try:
        reader = await request.multipart()
        uploaded_files = []

        input_dir = folder_paths.get_input_directory()
        pool_dir = os.path.join(input_dir, "I9_VideoPool")
        os.makedirs(pool_dir, exist_ok=True)

        field = await reader.next()
        while field is not None:
            if field.name == 'video':
                filename = field.filename
                # Generate unique filename if exists
                base, ext = os.path.splitext(filename)
                counter = 1
                final_filename = filename
                while os.path.exists(os.path.join(pool_dir, final_filename)):
                    final_filename = f"{base}_{counter}{ext}"
                    counter += 1

                filepath = os.path.join(pool_dir, final_filename)

                with open(filepath, 'wb') as f:
                    while True:
                        chunk = await field.read_chunk()
                        if not chunk:
                            break
                        f.write(chunk)

                uploaded_files.append({
                    'filename': final_filename,
                    'original_name': filename,
                    'path': filepath
                })

            field = await reader.next()

        return web.json_response({
            'success': True,
            'files': uploaded_files
        })
    except Exception as e:
        return web.json_response({
            'success': False,
            'error': str(e)
        }, status=500)

@server.PromptServer.instance.routes.get("/i9/video/list")
async def list_batch_videos(request):
    """List all videos in the batch pool"""
    try:
        input_dir = folder_paths.get_input_directory()
        pool_dir = os.path.join(input_dir, "I9_VideoPool")
        os.makedirs(pool_dir, exist_ok=True)

        videos = []
        for filename in os.listdir(pool_dir):
            if filename.lower().endswith(('.mp4', '.avi', '.mov', '.mkv', '.webm', '.flv', '.wmv', '.m4v')):
                filepath = os.path.join(pool_dir, filename)
                stat = os.stat(filepath)
                videos.append({
                    'filename': filename,
                    'size': stat.st_size,
                    'modified': stat.st_mtime
                })

        # Sort by modification time (newest first)
        videos.sort(key=lambda x: x['modified'], reverse=True)

        return web.json_response({
            'success': True,
            'videos': videos
        })
    except Exception as e:
        return web.json_response({
            'success': False,
            'error': str(e)
        }, status=500)

@server.PromptServer.instance.routes.delete("/i9/video/delete")
async def delete_batch_video(request):
    """Delete a video from the batch pool"""
    try:
        data = await request.json()
        filename = data.get('filename')

        if not filename:
            return web.json_response({'success': False, 'error': 'No filename provided'}, status=400)

        input_dir = folder_paths.get_input_directory()
        pool_dir = os.path.join(input_dir, "I9_VideoPool")
        filepath = os.path.join(pool_dir, filename)

        if os.path.exists(filepath):
            os.remove(filepath)
            return web.json_response({'success': True})
        else:
            return web.json_response({'success': False, 'error': 'File not found'}, status=404)
    except Exception as e:
        return web.json_response({'success': False, 'error': str(e)}, status=500)

@server.PromptServer.instance.routes.post("/i9/video/clear")
async def clear_video_pool(request):
    """Clear all videos from the batch pool"""
    try:
        input_dir = folder_paths.get_input_directory()
        pool_dir = os.path.join(input_dir, "I9_VideoPool")

        if os.path.exists(pool_dir):
            for filename in os.listdir(pool_dir):
                filepath = os.path.join(pool_dir, filename)
                if os.path.isfile(filepath):
                    os.remove(filepath)

        return web.json_response({'success': True})
    except Exception as e:
        return web.json_response({'success': False, 'error': str(e)}, status=500)


class I9_BatchVideoExtractor:

    def __init__(self):
        self.node_states = {}

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "mode": (["Batch Tensor", "Sequential"], {"default": "Batch Tensor"}),
                "frame_number": ("INT", {"default": 0, "min": 0, "max": 999999, "step": 1}),
            },
            "optional": {
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
    FUNCTION = "extract_frames"
    CATEGORY = "I9/Video"

    def extract_frames(self, mode="Batch Tensor", frame_number=0, resize_mode="Center Crop", batch_index=0, width=512, height=512, node_id=None):
        print(f"\n{'='*60}")
        print(f"[I9 Video Extractor] Mode: {mode} | Frame: {frame_number} | Resize: {resize_mode}")
        print(f"[I9 Video Extractor] Resolution: {width}x{height} | Batch Index: {batch_index}")
        print(f"[I9 Video Extractor] Processing videos for node: {node_id}")

        # Get all videos from pool
        input_dir = folder_paths.get_input_directory()
        pool_dir = os.path.join(input_dir, "I9_VideoPool")

        if not os.path.exists(pool_dir):
            empty = torch.zeros((1, 64, 64, 3), dtype=torch.float32)
            return (empty, 0, 0, "No videos in batch pool. Use the upload button to add videos.")

        # Get all video files
        video_files = sorted([f for f in os.listdir(pool_dir)
                            if f.lower().endswith(('.mp4', '.avi', '.mov', '.mkv', '.webm', '.flv', '.wmv', '.m4v'))])

        if not video_files:
            empty = torch.zeros((1, 64, 64, 3), dtype=torch.float32)
            return (empty, 0, 0, "No videos in batch pool. Use the upload button to add videos.")

        # Process videos
        if mode == "Sequential":
            return self._extract_sequential_from_pool(pool_dir, video_files, batch_index, frame_number, resize_mode, width, height, node_id)
        else:
            return self._extract_batch_from_pool(pool_dir, video_files, frame_number, resize_mode, width, height)

    def _extract_sequential_from_pool(self, pool_dir, video_files, batch_index, frame_number, resize_mode, width, height, node_id):
        """Extract frame from one video at a time in sequential mode"""
        total_count = len(video_files)

        if batch_index >= total_count:
            empty = torch.zeros((1, 64, 64, 3), dtype=torch.float32)
            return (empty, batch_index, total_count, "Index out of range")

        filename = video_files[batch_index]
        video_path = os.path.join(pool_dir, filename)

        try:
            frame_tensor = self._extract_frame_from_video(video_path, frame_number, width, height, resize_mode)

            if frame_tensor is None:
                empty = torch.zeros((1, 64, 64, 3), dtype=torch.float32)
                return (empty, batch_index, total_count, f"Could not extract frame {frame_number} from {filename}")

            frame_tensor = frame_tensor.unsqueeze(0)
            info = f"[{batch_index + 1}/{total_count}] {filename} - Frame {frame_number}"
            return (frame_tensor, batch_index, total_count, info)
        except Exception as e:
            empty = torch.zeros((1, 64, 64, 3), dtype=torch.float32)
            return (empty, batch_index, total_count, f"Error processing {filename}: {e}")

    def _extract_batch_from_pool(self, pool_dir, video_files, frame_number, resize_mode, target_width, target_height):
        """Extract frames from all videos as a batch tensor"""
        extracted_frames = []
        info_lines = []

        print(f"[I9 Video Extractor] Extracting frame {frame_number} from {len(video_files)} videos as batch tensor")

        for filename in video_files:
            video_path = os.path.join(pool_dir, filename)

            try:
                frame_tensor = self._extract_frame_from_video(video_path, frame_number, target_width, target_height, resize_mode)

                if frame_tensor is not None:
                    extracted_frames.append(frame_tensor)
                    info_lines.append(f"{filename} (frame {frame_number})")
                else:
                    print(f"[I9 Video Extractor] Could not extract frame {frame_number} from {filename}")
            except Exception as e:
                print(f"[I9 Video Extractor] Error processing {filename}: {e}")
                continue

        if not extracted_frames:
            empty = torch.zeros((1, 64, 64, 3), dtype=torch.float32)
            return (empty, 0, 0, f"Failed to extract frame {frame_number} from any videos")

        batch_tensor = torch.stack(extracted_frames, dim=0)
        return (batch_tensor, 0, len(extracted_frames), f"Extracted frame {frame_number} from {len(extracted_frames)} videos:\n" + "\n".join(info_lines))

    def _extract_frame_from_video(self, video_path, frame_number, target_width, target_height, resize_mode):
        """Extract a specific frame from a video file using OpenCV"""
        try:
            cap = cv2.VideoCapture(video_path)

            if not cap.isOpened():
                print(f"[I9 Video Extractor] Could not open video: {video_path}")
                return None

            # Get total frame count
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

            # Validate frame number
            if frame_number >= total_frames:
                print(f"[I9 Video Extractor] Frame {frame_number} out of range (total: {total_frames})")
                cap.release()
                return None

            # Set frame position
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_number)

            # Read the frame
            ret, frame = cap.read()
            cap.release()

            if not ret or frame is None:
                print(f"[I9 Video Extractor] Could not read frame {frame_number}")
                return None

            # Convert BGR to RGB (OpenCV uses BGR by default)
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

            # Convert to PIL Image for consistency with existing code
            img = Image.fromarray(frame)
            img_tensor = torch.from_numpy(np.array(img).astype(np.float32) / 255.0)

            # Resize if needed
            if img_tensor.shape[0] != target_height or img_tensor.shape[1] != target_width:
                img_tensor = self._resize_image(img_tensor, target_width, target_height, resize_mode)

            return img_tensor

        except Exception as e:
            print(f"[I9 Video Extractor] Exception extracting frame: {e}")
            return None

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
        pool_dir = os.path.join(input_dir, "I9_VideoPool")

        if not os.path.exists(pool_dir):
            return "empty"

        # Hash based on file list and modification times
        files = sorted(os.listdir(pool_dir))
        m = hashlib.sha256()
        for f in files:
            fpath = os.path.join(pool_dir, f)
            if os.path.isfile(fpath):
                m.update(f.encode())
                m.update(str(os.path.getmtime(fpath)).encode())

        return m.hexdigest()

NODE_CLASS_MAPPINGS = {"I9_BatchVideoExtractor": I9_BatchVideoExtractor}
NODE_DISPLAY_NAME_MAPPINGS = {"I9_BatchVideoExtractor": "🎬 I9 Batch Video Extractor"}
