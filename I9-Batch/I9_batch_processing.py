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

# API Routes for batch management
@server.PromptServer.instance.routes.post("/i9/batch/upload")
async def upload_batch_images(request):
    """Handle multiple image uploads"""
    try:
        reader = await request.multipart()
        uploaded_files = []
        
        input_dir = folder_paths.get_input_directory()
        pool_dir = os.path.join(input_dir, "I9_ImagePool")
        os.makedirs(pool_dir, exist_ok=True)
        
        field = await reader.next()
        while field is not None:
            if field.name == 'image':
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

@server.PromptServer.instance.routes.get("/i9/batch/list")
async def list_batch_images(request):
    """List all images in the batch pool"""
    try:
        input_dir = folder_paths.get_input_directory()
        pool_dir = os.path.join(input_dir, "I9_ImagePool")
        os.makedirs(pool_dir, exist_ok=True)
        
        images = []
        for filename in os.listdir(pool_dir):
            if filename.lower().endswith(('.png', '.jpg', '.jpeg', '.webp', '.gif', '.bmp')):
                filepath = os.path.join(pool_dir, filename)
                stat = os.stat(filepath)
                images.append({
                    'filename': filename,
                    'size': stat.st_size,
                    'modified': stat.st_mtime
                })
        
        # Sort by modification time (newest first)
        images.sort(key=lambda x: x['modified'], reverse=True)
        
        return web.json_response({
            'success': True,
            'images': images
        })
    except Exception as e:
        return web.json_response({
            'success': False,
            'error': str(e)
        }, status=500)

@server.PromptServer.instance.routes.delete("/i9/batch/delete")
async def delete_batch_image(request):
    """Delete an image from the batch pool"""
    try:
        data = await request.json()
        filename = data.get('filename')
        
        if not filename:
            return web.json_response({'success': False, 'error': 'No filename provided'}, status=400)
        
        input_dir = folder_paths.get_input_directory()
        pool_dir = os.path.join(input_dir, "I9_ImagePool")
        filepath = os.path.join(pool_dir, filename)
        
        if os.path.exists(filepath):
            os.remove(filepath)
            return web.json_response({'success': True})
        else:
            return web.json_response({'success': False, 'error': 'File not found'}, status=404)
    except Exception as e:
        return web.json_response({'success': False, 'error': str(e)}, status=500)

@server.PromptServer.instance.routes.post("/i9/batch/clear")
async def clear_batch_pool(request):
    """Clear all images from the batch pool"""
    try:
        input_dir = folder_paths.get_input_directory()
        pool_dir = os.path.join(input_dir, "I9_ImagePool")
        
        if os.path.exists(pool_dir):
            for filename in os.listdir(pool_dir):
                filepath = os.path.join(pool_dir, filename)
                if os.path.isfile(filepath):
                    os.remove(filepath)
        
        return web.json_response({'success': True})
    except Exception as e:
        return web.json_response({'success': False, 'error': str(e)}, status=500)


class I9_BatchProcessing:

    def __init__(self):
        self.node_states = {}

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "mode": (["Batch Tensor", "Sequential"], {"default": "Batch Tensor"}),
            },
            "optional": {
                "resize_mode": (["Center Crop", "Letterbox", "Stretch", "Fit to Largest"], {"default": "Center Crop"}),
                "batch_index": ("INT", {"default": 0, "min": 0, "max": 9999, "step": 1}),
                "width": ("INT", {"default": 512, "min": 64, "max": 8192, "step": 8}),
                "height": ("INT", {"default": 512, "min": 64, "max": 8192, "step": 8}),
                "aspect_label": ("STRING", {"default": "1:1"}),
                "enable_img2img": ("BOOLEAN", {"default": True}),
            },
            "hidden": {
                "node_id": "UNIQUE_ID",
            }
        }

    RETURN_TYPES = ("IMAGE", "INT", "INT", "STRING")
    RETURN_NAMES = ("images", "index", "total", "info")
    FUNCTION = "load_batch"
    CATEGORY = "I9/Input"

    def load_batch(self, mode="Batch Tensor", resize_mode="Center Crop", batch_index=0, width=512, height=512, aspect_label="1:1", enable_img2img=True, node_id=None):
        print(f"\n{'='*60}")
        print(f"[I9 Batch Processing] Mode: {mode} | Resize: {resize_mode} | Index: {batch_index}")
        print(f"[I9 Batch Processing] Enable img2img: {enable_img2img} | Resolution: {width}x{height} | Aspect: {aspect_label}")
        print(f"[I9 Batch Processing] Loading batch for node: {node_id}")

        # Get all images from pool
        input_dir = folder_paths.get_input_directory()
        pool_dir = os.path.join(input_dir, "I9_ImagePool")
        
        if not os.path.exists(pool_dir):
            empty = torch.zeros((1, 64, 64, 3), dtype=torch.float32)
            return (empty, 0, 0, "No images in batch pool. Use the upload button to add images.")

        # Get all image files
        image_files = sorted([f for f in os.listdir(pool_dir) 
                            if f.lower().endswith(('.png', '.jpg', '.jpeg', '.webp', '.gif', '.bmp'))])
        
        if not image_files:
            empty = torch.zeros((1, 64, 64, 3), dtype=torch.float32)
            return (empty, 0, 0, "No images in batch pool. Use the upload button to add images.")

        # txt2img mode
        if not enable_img2img:
            empty = torch.zeros((1, height, width, 3), dtype=torch.float32)
            return (empty, 0, len(image_files), f"txt2img mode - {len(image_files)} images in pool")

        # img2img mode - load images
        if mode == "Sequential":
            return self._load_sequential_from_pool(pool_dir, image_files, batch_index, resize_mode, width, height, node_id)
        else:
            return self._load_batch_from_pool(pool_dir, image_files, resize_mode, width, height)

    def _load_sequential_from_pool(self, pool_dir, image_files, batch_index, resize_mode, width, height, node_id):
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
            
            # Resize if needed
            if img_tensor.shape[0] != height or img_tensor.shape[1] != width:
                img_tensor = self._resize_image(img_tensor, width, height, resize_mode)
            
            img_tensor = img_tensor.unsqueeze(0)
            info = f"[{batch_index + 1}/{total_count}] {filename}"
            return (img_tensor, batch_index, total_count, info)
        except Exception as e:
            empty = torch.zeros((1, 64, 64, 3), dtype=torch.float32)
            return (empty, batch_index, total_count, f"Error loading {filename}: {e}")

    def _load_batch_from_pool(self, pool_dir, image_files, resize_mode, target_width, target_height):
        """Load all images as a batch tensor"""
        loaded_images = []
        info_lines = []
        
        print(f"[I9 Batch Processing] Loading {len(image_files)} images as batch tensor")

        for filename in image_files:
            img_path = os.path.join(pool_dir, filename)
            
            try:
                img = Image.open(img_path).convert('RGB')
                img_tensor = torch.from_numpy(np.array(img).astype(np.float32) / 255.0)

                # Resize to target dimensions
                if img_tensor.shape[0] != target_height or img_tensor.shape[1] != target_width:
                    img_tensor = self._resize_image(img_tensor, target_width, target_height, resize_mode)
                
                loaded_images.append(img_tensor)
                info_lines.append(filename)
            except Exception as e:
                print(f"[I9 Batch Processing] Error loading {filename}: {e}")
                continue

        if not loaded_images:
            empty = torch.zeros((1, 64, 64, 3), dtype=torch.float32)
            return (empty, 0, 0, "Failed to load any images")

        batch_tensor = torch.stack(loaded_images, dim=0)
        return (batch_tensor, 0, len(loaded_images), f"Loaded {len(loaded_images)} images:\n" + "\n".join(info_lines))

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
        
        # Hash based on file list and modification times
        files = sorted(os.listdir(pool_dir))
        m = hashlib.sha256()
        for f in files:
            fpath = os.path.join(pool_dir, f)
            if os.path.isfile(fpath):
                m.update(f.encode())
                m.update(str(os.path.getmtime(fpath)).encode())
        
        return m.hexdigest()

NODE_CLASS_MAPPINGS = {"I9_BatchProcessing": I9_BatchProcessing}
NODE_DISPLAY_NAME_MAPPINGS = {"I9_BatchProcessing": "🖼️ I9 Batch Processing"}
