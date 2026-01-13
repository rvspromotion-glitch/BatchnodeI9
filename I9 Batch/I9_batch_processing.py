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
                "upload": ("IMAGEUPLOAD", {"default": ""}),  # Image upload widget
            },
            "hidden": {
                "node_id": "UNIQUE_ID",
                "batch_data": ("STRING", {"default": "{}"}),
            }
        }

    RETURN_TYPES = ("IMAGE", "INT", "INT", "STRING")
    RETURN_NAMES = ("images", "index", "total", "info")
    FUNCTION = "load_batch"
    CATEGORY = "I9/Input"

    def load_batch(self, mode="Batch Tensor", resize_mode="Center Crop", batch_index=0, width=512, height=512, aspect_label="1:1", enable_img2img=True, upload="", node_id=None, batch_data="{}"):
        print(f"\n{'='*60}")
        print(f"[I9 Batch Processing] Mode: {mode} | Resize: {resize_mode} | Index: {batch_index}")
        print(f"[I9 Batch Processing] Enable img2img: {enable_img2img} | Resolution: {width}x{height} | Aspect: {aspect_label}")
        print(f"[I9 Batch Processing] Loading batch for node: {node_id}")

        try:
            data = json.loads(batch_data) if batch_data else {}
        except json.JSONDecodeError:
            print("[I9 Batch Processing] Invalid batch_data JSON, using empty.")
            data = {}

        # Process uploaded image if present
        if upload and upload != "":
            data = self._handle_upload(upload, data, node_id)

        # txt2img mode: Generate empty latents
        if not enable_img2img:
            return self._load_txt2img(data, mode, batch_index, width, height, aspect_label, node_id)

        # img2img mode: Load actual images
        images_meta = data.get('images', [])
        order = data.get('order', [])

        if not images_meta or not order:
            print("[I9 Batch Processing] No images in batch, returning empty.")
            empty = torch.zeros((1, 64, 64, 3), dtype=torch.float32)
            return (empty, 0, 0, "No images loaded. Use the upload button.")

        upload_dir = self._get_upload_dir(node_id)
        if not os.path.exists(upload_dir):
            print(f"[I9 Batch Processing] Upload directory not found: {upload_dir}")
            empty = torch.zeros((1, 64, 64, 3), dtype=torch.float32)
            return (empty, 0, 0, f"Directory not found: {upload_dir}")

        total_count = sum(img.get('repeat_count', 1) for img in images_meta)

        if mode == "Sequential":
            state_key = f"{node_id}_{hashlib.md5(batch_data.encode()).hexdigest()[:8]}"
            if state_key in self.node_states and self.node_states[state_key]['last_widget_index'] != batch_index:
                self.node_states[state_key] = {'current_index': batch_index, 'last_widget_index': batch_index}
            elif state_key not in self.node_states:
                self.node_states[state_key] = {'current_index': batch_index, 'last_widget_index': batch_index}

            current_index = self.node_states[state_key]['current_index']
            img_tensor, _, total, info = self._load_sequential(upload_dir, images_meta, order, current_index, total_count, node_id)
            next_index = (current_index + 1) % total_count
            self.node_states[state_key]['current_index'] = next_index
            self.node_states[state_key]['last_widget_index'] = batch_index
            
            return (img_tensor, current_index, total, info)
        else:
            return self._load_batch_tensor(upload_dir, images_meta, order, resize_mode, total_count, width, height, node_id)

    def _handle_upload(self, upload, data, node_id):
        """Process uploaded image and add to batch data"""
        if not data:
            data = {'images': [], 'latents': [], 'order': []}
        if 'images' not in data:
            data['images'] = []
        if 'order' not in data:
            data['order'] = []

        # Upload is the image filename that was uploaded
        image_id = f"img_{uuid.uuid4().hex[:16]}"
        data['images'].append({
            'id': image_id,
            'filename': upload,
            'original_name': upload,
            'repeat_count': 1
        })
        data['order'].append(image_id)
        
        print(f"[I9 Batch Processing] Added image to batch: {upload}")
        return data

    def _load_sequential(self, upload_dir, images_meta, order, batch_index, total_count, node_id=None):
        flat_list = []
        for img_id in order:
            img_meta = next((img for img in images_meta if img['id'] == img_id), None)
            if not img_meta: continue
            for i in range(img_meta.get('repeat_count', 1)):
                flat_list.append((img_meta, i + 1, img_meta.get('repeat_count', 1)))

        if batch_index >= len(flat_list):
            empty = torch.zeros((1, 64, 64, 3), dtype=torch.float32)
            return (empty, batch_index, total_count, "Index out of range")

        img_meta, copy_num, repeat_count = flat_list[batch_index]
        filename, original_name = img_meta['filename'], img_meta.get('original_name', img_meta['filename'])

        # Use smart path finder that checks multiple locations
        img_path = self._find_image_path(filename, node_id)
        if not img_path:
            empty = torch.zeros((1, 64, 64, 3), dtype=torch.float32)
            return (empty, batch_index, total_count, f"Image not found: {filename}")

        try:
            img = Image.open(img_path).convert('RGB')
            img_array = np.array(img).astype(np.float32) / 255.0
            img_tensor = torch.from_numpy(img_array).unsqueeze(0)
            info = f"[{batch_index}/{total_count}] {original_name} (copy {copy_num}/{repeat_count})"
            return (img_tensor, batch_index, total_count, info)
        except Exception as e:
            empty = torch.zeros((1, 64, 64, 3), dtype=torch.float32)
            return (empty, batch_index, total_count, f"Error: {e}")

    def _load_batch_tensor(self, upload_dir, images_meta, order, resize_mode, total_count, target_width, target_height, node_id=None):
        """
        Load batch tensor with ALL images resized to target_width x target_height from aspect ratio selector.
        This ensures consistent tensor dimensions controlled by the WAN/SDXL aspect ratio node.
        """
        loaded_images, info_lines = [], []
        print(f"[I9 Batch Processing] Batch Tensor Mode - Target dimensions: {target_width}x{target_height} (from aspect ratio selector)")

        for img_id in order:
            img_meta = next((img for img in images_meta if img['id'] == img_id), None)
            if not img_meta: continue

            filename, repeat_count, original_name = img_meta['filename'], img_meta.get('repeat_count', 1), img_meta.get('original_name', img_meta['filename'])

            # Use smart path finder that checks multiple locations
            img_path = self._find_image_path(filename, node_id)
            if not img_path:
                print(f"[I9 Batch Processing] Image not found: {filename}")
                continue

            try:
                img = Image.open(img_path).convert('RGB')
                img_tensor = torch.from_numpy(np.array(img).astype(np.float32) / 255.0)

                # Always resize to target dimensions (from aspect ratio selector)
                if img_tensor.shape[0] != target_height or img_tensor.shape[1] != target_width:
                    img_tensor = self._resize_image(img_tensor, target_width, target_height, resize_mode)
                    print(f"[I9 Batch Processing] Resized {original_name} from {img.size[0]}x{img.size[1]} → {target_width}x{target_height} ({resize_mode})")
                for i in range(repeat_count):
                    loaded_images.append(img_tensor)
                    info_lines.append(f"{original_name} (copy {i+1}/{repeat_count})")
            except Exception as e:
                print(f"[I9 Batch Processing] Error loading {filename}: {e}")
                continue

        if not loaded_images:
            empty = torch.zeros((1, 64, 64, 3), dtype=torch.float32)
            return (empty, 0, total_count, "Failed to load images")

        return (torch.stack(loaded_images, dim=0), 0, total_count, "\n".join(info_lines))

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

    def _load_txt2img(self, data, mode, batch_index, width, height, aspect_label, node_id):
        """
        Generate empty IMAGE tensors for txt2img mode.
        Each "latent" is actually an empty IMAGE tensor that will be used as input.
        """
        latents_meta = data.get('latents', [])
        order = data.get('order', [])

        if not latents_meta or not order:
            print(f"[I9 Batch Processing] No latents in batch, returning empty {aspect_label} latent.")
            empty = torch.zeros((1, height, width, 3), dtype=torch.float32)
            return (empty, 0, 0, f"No latents defined ({aspect_label})")

        total_count = sum(latent.get('repeat_count', 1) for latent in latents_meta)

        if mode == "Sequential":
            return self._load_txt2img_sequential(latents_meta, order, batch_index, total_count, node_id, data, width, height)
        else:
            return self._load_txt2img_batch(latents_meta, order, total_count, width, height)

    def _load_txt2img_sequential(self, latents_meta, order, batch_index, total_count, node_id, data, fallback_width, fallback_height):
        """Sequential mode for txt2img - return one empty latent at a time"""
        state_key = f"{node_id}_txt2img_{hashlib.md5(json.dumps(data).encode()).hexdigest()[:8]}"

        if state_key in self.node_states and self.node_states[state_key]['last_widget_index'] != batch_index:
            self.node_states[state_key] = {'current_index': batch_index, 'last_widget_index': batch_index}
        elif state_key not in self.node_states:
            self.node_states[state_key] = {'current_index': batch_index, 'last_widget_index': batch_index}

        current_index = self.node_states[state_key]['current_index']

        # Build flat list of all latents with repeats
        flat_list = []
        for latent_id in order:
            latent_meta = next((l for l in latents_meta if l['id'] == latent_id), None)
            if not latent_meta:
                continue
            for i in range(latent_meta.get('repeat_count', 1)):
                flat_list.append((latent_meta, i + 1, latent_meta.get('repeat_count', 1)))

        if current_index >= len(flat_list):
            empty = torch.zeros((1, 64, 64, 3), dtype=torch.float32)
            return (empty, current_index, total_count, "Index out of range")

        latent_meta, copy_num, repeat_count = flat_list[current_index]
        w, h = latent_meta.get('width', fallback_width), latent_meta.get('height', fallback_height)
        latent_id = latent_meta.get('id', 'unknown')

        # VALIDATION: Ensure dimensions are reasonable (not corrupted)
        if w < 64 or h < 64:
            print(f"[I9 Adv Loader] ⚠️ WARNING: Corrupted dimensions in latent_meta: {w}x{h}")
            print(f"[I9 Adv Loader] Using ground truth from node inputs: {fallback_width}x{fallback_height}")
            w, h = fallback_width, fallback_height

        # Generate empty tensor
        empty_tensor = torch.zeros((1, h, w, 3), dtype=torch.float32)
        info = f"[{current_index}/{total_count}] Empty latent {latent_id[:8]} {w}x{h} (copy {copy_num}/{repeat_count})"

        # Update state for next iteration
        next_index = (current_index + 1) % total_count
        self.node_states[state_key]['current_index'] = next_index
        self.node_states[state_key]['last_widget_index'] = batch_index

        return (empty_tensor, current_index, total_count, info)

    def _load_txt2img_batch(self, latents_meta, order, total_count, fallback_width, fallback_height):
        """Batch tensor mode for txt2img - return all empty latents stacked"""
        loaded_latents = []
        info_lines = []

        for latent_id in order:
            latent_meta = next((l for l in latents_meta if l['id'] == latent_id), None)
            if not latent_meta:
                continue

            w, h = latent_meta.get('width', fallback_width), latent_meta.get('height', fallback_height)

            # VALIDATION: Ensure dimensions are reasonable (not corrupted)
            if w < 64 or h < 64:
                print(f"[I9 Batch Processing] ⚠️ WARNING: Corrupted dimensions in latent_meta: {w}x{h}")
                print(f"[I9 Batch Processing] Using ground truth from node inputs: {fallback_width}x{fallback_height}")
                w, h = fallback_width, fallback_height
            repeat_count = latent_meta.get('repeat_count', 1)
            latent_display_id = latent_meta.get('id', 'unknown')[:8]

            # Create empty tensor for this latent
            empty_tensor = torch.zeros((h, w, 3), dtype=torch.float32)

            # Add to batch according to repeat count
            for i in range(repeat_count):
                loaded_latents.append(empty_tensor)
                info_lines.append(f"Empty latent {latent_display_id} {w}x{h} (copy {i+1}/{repeat_count})")

        if not loaded_latents:
            empty = torch.zeros((1, 64, 64, 3), dtype=torch.float32)
            return (empty, 0, total_count, "No latents to generate")

        # Stack all tensors into batch
        batch_tensor = torch.stack(loaded_latents, dim=0)
        return (batch_tensor, 0, total_count, "\n".join(info_lines))

    def _get_upload_dir(self, node_id=None):
        """Get the central image pool directory (node_id param kept for backwards compat but ignored)"""
        input_dir = folder_paths.get_input_directory()
        pool_dir = os.path.join(input_dir, "I9_ImagePool")
        os.makedirs(pool_dir, exist_ok=True)
        return pool_dir

    def _find_image_path(self, filename, node_id=None):
        """
        Find an image file, checking multiple locations:
        1. Central pool (I9_ImagePool)
        2. Old per-node folders (I9_BatchUploads/{node_id})
        3. All old per-node folders if node_id not found

        Auto-migrates images to pool when found in old locations.
        """
        input_dir = folder_paths.get_input_directory()
        pool_dir = os.path.join(input_dir, "I9_ImagePool")
        os.makedirs(pool_dir, exist_ok=True)

        # 1. Check central pool first
        pool_path = os.path.join(pool_dir, filename)
        if os.path.exists(pool_path):
            return pool_path

        # 2. Check old per-node folder if node_id provided
        old_base_dir = os.path.join(input_dir, "I9_BatchUploads")
        if node_id and os.path.exists(old_base_dir):
            old_node_dir = os.path.join(old_base_dir, str(node_id))
            old_path = os.path.join(old_node_dir, filename)
            if os.path.exists(old_path):
                # Auto-migrate to pool
                try:
                    shutil.copy2(old_path, pool_path)
                    print(f"[I9] Auto-migrated {filename} from node {node_id} folder to pool")
                except Exception as e:
                    print(f"[I9] Failed to migrate {filename}: {e}")
                return old_path if not os.path.exists(pool_path) else pool_path

        # 3. Search ALL old per-node folders
        if os.path.exists(old_base_dir):
            for folder in os.listdir(old_base_dir):
                folder_path = os.path.join(old_base_dir, folder)
                if os.path.isdir(folder_path):
                    old_path = os.path.join(folder_path, filename)
                    if os.path.exists(old_path):
                        # Auto-migrate to pool
                        try:
                            shutil.copy2(old_path, pool_path)
                            print(f"[I9] Auto-migrated {filename} from folder {folder} to pool")
                        except Exception as e:
                            print(f"[I9] Failed to migrate {filename}: {e}")
                        return old_path if not os.path.exists(pool_path) else pool_path

        # Not found anywhere
        return None

    @classmethod
    def IS_CHANGED(cls, mode="Batch Tensor", batch_data="{}", upload="", **kwargs):
        # Force re-execution when upload changes
        if upload and upload != "":
            import time
            return f"upload_{time.time()}_{upload}"
        
        if mode == "Sequential":
            import time
            return f"seq_{time.time()}_{hashlib.md5(batch_data.encode()).hexdigest()[:8]}"
        else:
            return hashlib.md5(batch_data.encode()).hexdigest()

    @classmethod
    def VALIDATE_INPUTS(cls, upload="", **kwargs):
        # Validate upload if provided
        if upload and upload != "":
            input_dir = folder_paths.get_input_directory()
            pool_dir = os.path.join(input_dir, "I9_ImagePool")
            img_path = os.path.join(pool_dir, upload)
            if not os.path.exists(img_path):
                # Also check in root input directory
                img_path = os.path.join(input_dir, upload)
                if not os.path.exists(img_path):
                    return f"Image not found: {upload}"
        return True

NODE_CLASS_MAPPINGS = {"I9_BatchProcessing": I9_BatchProcessing}
NODE_DISPLAY_NAME_MAPPINGS = {"I9_BatchProcessing": "🖼️ I9 Batch Processing"}
