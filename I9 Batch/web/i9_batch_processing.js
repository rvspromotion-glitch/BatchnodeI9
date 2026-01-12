import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

// Register the custom node extension
app.registerExtension({
    name: "I9.BatchProcessing",
    
    async beforeRegisterNodeDef(nodeType, nodeData, app) {
        if (nodeData.name === "I9_BatchProcessing") {
            
            // Store original onNodeCreated
            const onNodeCreated = nodeType.prototype.onNodeCreated;
            
            nodeType.prototype.onNodeCreated = function() {
                const r = onNodeCreated ? onNodeCreated.apply(this, arguments) : undefined;
                
                // Initialize batch data
                if (!this.properties) {
                    this.properties = {};
                }
                if (!this.properties.batch_data) {
                    this.properties.batch_data = JSON.stringify({
                        images: [],
                        latents: [],
                        order: []
                    });
                }
                
                // Add "Load Images" button
                this.addWidget("button", "load_images", "📁 Load Images", () => {
                    this.openImageLoader();
                });
                
                // Add "Clear Batch" button
                this.addWidget("button", "clear_batch", "🗑️ Clear Batch", () => {
                    this.clearBatch();
                });
                
                // Add info display
                const infoWidget = this.addWidget("text", "batch_info", "", () => {}, {
                    multiline: true,
                    disabled: true
                });
                this.infoWidget = infoWidget;
                this.updateBatchInfo();
                
                return r;
            };
            
            // Method to open file dialog
            nodeType.prototype.openImageLoader = function() {
                const input = document.createElement("input");
                input.type = "file";
                input.multiple = true;
                input.accept = "image/*";
                
                input.onchange = async (e) => {
                    const files = Array.from(e.target.files);
                    await this.uploadImages(files);
                };
                
                input.click();
            };
            
            // Upload images to ComfyUI
            nodeType.prototype.uploadImages = async function(files) {
                const batchData = JSON.parse(this.properties.batch_data || "{}");
                if (!batchData.images) batchData.images = [];
                if (!batchData.order) batchData.order = [];
                
                for (const file of files) {
                    try {
                        const formData = new FormData();
                        formData.append("image", file);
                        formData.append("subfolder", "I9_ImagePool");
                        formData.append("type", "input");
                        
                        const resp = await api.fetchApi("/upload/image", {
                            method: "POST",
                            body: formData
                        });
                        
                        const result = await resp.json();
                        
                        // Add to batch data
                        const imageId = `img_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
                        batchData.images.push({
                            id: imageId,
                            filename: result.name,
                            original_name: file.name,
                            repeat_count: 1
                        });
                        batchData.order.push(imageId);
                        
                    } catch (err) {
                        console.error("Failed to upload image:", file.name, err);
                        alert(`Failed to upload ${file.name}`);
                    }
                }
                
                this.properties.batch_data = JSON.stringify(batchData);
                this.updateBatchInfo();
            };
            
            // Clear batch
            nodeType.prototype.clearBatch = function() {
                this.properties.batch_data = JSON.stringify({
                    images: [],
                    latents: [],
                    order: []
                });
                this.updateBatchInfo();
            };
            
            // Update info display
            nodeType.prototype.updateBatchInfo = function() {
                if (!this.infoWidget) return;
                
                const batchData = JSON.parse(this.properties.batch_data || "{}");
                const imageCount = (batchData.images || []).length;
                const latentCount = (batchData.latents || []).length;
                const totalImages = (batchData.images || []).reduce((sum, img) => sum + (img.repeat_count || 1), 0);
                
                let info = `📊 Batch Status:\n`;
                info += `Images: ${imageCount} (${totalImages} total with repeats)\n`;
                info += `Latents: ${latentCount}\n`;
                
                if (imageCount > 0) {
                    info += `\n📷 Images:\n`;
                    (batchData.images || []).forEach((img, i) => {
                        info += `  ${i+1}. ${img.original_name} (×${img.repeat_count})\n`;
                    });
                }
                
                this.infoWidget.value = info;
            };
            
            // Override getExtraMenuOptions to add batch management
            const origGetExtraMenuOptions = nodeType.prototype.getExtraMenuOptions;
            nodeType.prototype.getExtraMenuOptions = function(_, options) {
                if (origGetExtraMenuOptions) {
                    origGetExtraMenuOptions.apply(this, arguments);
                }
                
                const batchData = JSON.parse(this.properties.batch_data || "{}");
                
                options.unshift(
                    {
                        content: "Manage Batch Images",
                        callback: () => {
                            this.showBatchManager();
                        }
                    },
                    null // separator
                );
            };
            
            // Batch manager dialog
            nodeType.prototype.showBatchManager = function() {
                const batchData = JSON.parse(this.properties.batch_data || "{}");
                const images = batchData.images || [];
                
                const dialog = document.createElement("div");
                dialog.style.cssText = `
                    position: fixed;
                    top: 50%;
                    left: 50%;
                    transform: translate(-50%, -50%);
                    background: #2b2b2b;
                    padding: 20px;
                    border-radius: 8px;
                    z-index: 10000;
                    min-width: 400px;
                    max-height: 80vh;
                    overflow-y: auto;
                    box-shadow: 0 4px 20px rgba(0,0,0,0.5);
                `;
                
                let html = `<h3 style="margin-top:0; color: #fff;">Batch Image Manager</h3>`;
                
                if (images.length === 0) {
                    html += `<p style="color: #aaa;">No images loaded. Click "Load Images" to add.</p>`;
                } else {
                    images.forEach((img, idx) => {
                        html += `
                            <div style="padding: 10px; margin: 5px 0; background: #1a1a1a; border-radius: 4px; display: flex; justify-content: space-between; align-items: center;">
                                <div style="color: #fff;">
                                    <strong>${img.original_name}</strong><br>
                                    <small style="color: #888;">${img.filename}</small>
                                    <div style="margin-top: 5px;">
                                        <label style="color: #aaa;">Repeats: </label>
                                        <input type="number" id="repeat_${idx}" value="${img.repeat_count || 1}" min="1" max="100" 
                                            style="width: 60px; background: #333; color: #fff; border: 1px solid #555; padding: 2px;">
                                    </div>
                                </div>
                                <button id="remove_${idx}" style="background: #c44; color: #fff; border: none; padding: 8px 12px; cursor: pointer; border-radius: 4px;">
                                    Remove
                                </button>
                            </div>
                        `;
                    });
                }
                
                html += `
                    <div style="margin-top: 20px; display: flex; gap: 10px;">
                        <button id="save_btn" style="flex: 1; background: #4a4; color: #fff; border: none; padding: 10px; cursor: pointer; border-radius: 4px;">
                            Save Changes
                        </button>
                        <button id="cancel_btn" style="flex: 1; background: #666; color: #fff; border: none; padding: 10px; cursor: pointer; border-radius: 4px;">
                            Cancel
                        </button>
                    </div>
                `;
                
                dialog.innerHTML = html;
                document.body.appendChild(dialog);
                
                // Event handlers
                const saveChanges = () => {
                    images.forEach((img, idx) => {
                        const repeatInput = document.getElementById(`repeat_${idx}`);
                        if (repeatInput) {
                            img.repeat_count = parseInt(repeatInput.value) || 1;
                        }
                    });
                    
                    batchData.images = images;
                    this.properties.batch_data = JSON.stringify(batchData);
                    this.updateBatchInfo();
                    document.body.removeChild(dialog);
                };
                
                images.forEach((img, idx) => {
                    const removeBtn = document.getElementById(`remove_${idx}`);
                    if (removeBtn) {
                        removeBtn.onclick = () => {
                            images.splice(idx, 1);
                            batchData.order = batchData.order.filter(id => id !== img.id);
                            batchData.images = images;
                            this.properties.batch_data = JSON.stringify(batchData);
                            document.body.removeChild(dialog);
                            this.showBatchManager(); // Reopen to refresh
                        };
                    }
                });
                
                document.getElementById("save_btn").onclick = saveChanges;
                document.getElementById("cancel_btn").onclick = () => {
                    document.body.removeChild(dialog);
                };
            };
            
            // Ensure batch_data is synced to the hidden widget
            const onExecuted = nodeType.prototype.onExecuted;
            nodeType.prototype.onExecuted = function(message) {
                if (onExecuted) {
                    onExecuted.apply(this, arguments);
                }
            };
            
            // Serialize properties to batch_data widget
            const onConfigure = nodeType.prototype.onConfigure;
            nodeType.prototype.onConfigure = function(info) {
                if (onConfigure) {
                    onConfigure.apply(this, arguments);
                }
                
                // Sync from properties to widget
                if (this.properties && this.properties.batch_data) {
                    const widget = this.widgets.find(w => w.name === "batch_data");
                    if (widget) {
                        widget.value = this.properties.batch_data;
                    }
                }
                
                this.updateBatchInfo();
            };
            
            const onSerialize = nodeType.prototype.onSerialize;
            nodeType.prototype.onSerialize = function(o) {
                if (onSerialize) {
                    onSerialize.apply(this, arguments);
                }
                
                // Sync properties to widget before serialization
                const widget = this.widgets.find(w => w.name === "batch_data");
                if (widget && this.properties) {
                    widget.value = this.properties.batch_data || "{}";
                }
            };
        }
    }
});
