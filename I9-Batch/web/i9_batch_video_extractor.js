import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

app.registerExtension({
    name: "I9.BatchVideoExtractor",

    async beforeRegisterNodeDef(nodeType, nodeData, app) {
        if (nodeData.name === "I9_BatchVideoExtractor") {

            const onNodeCreated = nodeType.prototype.onNodeCreated;

            nodeType.prototype.onNodeCreated = function() {
                const r = onNodeCreated ? onNodeCreated.apply(this, arguments) : undefined;

                // Add custom video manager button
                this.addWidget("button", "video_manager", "🎬 Manage Batch Videos", () => {
                    this.showVideoManager();
                });

                return r;
            };

            // Show video manager dialog
            nodeType.prototype.showVideoManager = async function() {
                // Create overlay
                const overlay = document.createElement("div");
                overlay.style.cssText = `
                    position: fixed;
                    top: 0;
                    left: 0;
                    width: 100%;
                    height: 100%;
                    background: rgba(0,0,0,0.8);
                    z-index: 10000;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                `;

                // Create dialog
                const dialog = document.createElement("div");
                dialog.style.cssText = `
                    background: #1e1e1e;
                    border-radius: 8px;
                    width: 80%;
                    max-width: 1200px;
                    max-height: 90vh;
                    display: flex;
                    flex-direction: column;
                    color: #fff;
                    box-shadow: 0 8px 32px rgba(0,0,0,0.5);
                `;

                // Header
                const header = document.createElement("div");
                header.style.cssText = `
                    padding: 20px;
                    border-bottom: 1px solid #333;
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                `;
                header.innerHTML = `
                    <h2 style="margin: 0;">🎬 Batch Video Manager</h2>
                    <button id="i9_video_close" style="background: #c44; color: #fff; border: none; padding: 8px 16px; border-radius: 4px; cursor: pointer; font-weight: bold;">
                        ✕ Close
                    </button>
                `;

                // Toolbar
                const toolbar = document.createElement("div");
                toolbar.style.cssText = `
                    padding: 15px 20px;
                    background: #252525;
                    display: flex;
                    gap: 10px;
                    align-items: center;
                    flex-wrap: wrap;
                `;
                toolbar.innerHTML = `
                    <input type="file" id="i9_video_file_input" multiple accept="video/*" style="display: none;">
                    <button id="i9_video_upload_btn" style="background: #4a4; color: #fff; border: none; padding: 10px 20px; border-radius: 4px; cursor: pointer; font-weight: bold;">
                        ⬆️ Upload Videos
                    </button>
                    <button id="i9_video_refresh_btn" style="background: #44a; color: #fff; border: none; padding: 10px 20px; border-radius: 4px; cursor: pointer;">
                        🔄 Refresh
                    </button>
                    <button id="i9_video_clear_btn" style="background: #c44; color: #fff; border: none; padding: 10px 20px; border-radius: 4px; cursor: pointer;">
                        🗑️ Clear All
                    </button>
                    <span id="i9_video_status" style="margin-left: auto; color: #aaa;"></span>
                `;

                // Video grid container
                const gridContainer = document.createElement("div");
                gridContainer.style.cssText = `
                    flex: 1;
                    overflow-y: auto;
                    padding: 20px;
                `;

                const grid = document.createElement("div");
                grid.id = "i9_video_grid";
                grid.style.cssText = `
                    display: grid;
                    grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
                    gap: 15px;
                `;
                gridContainer.appendChild(grid);

                // Assemble dialog
                dialog.appendChild(header);
                dialog.appendChild(toolbar);
                dialog.appendChild(gridContainer);
                overlay.appendChild(dialog);
                document.body.appendChild(overlay);

                // Event handlers
                const closeDialog = () => document.body.removeChild(overlay);

                document.getElementById("i9_video_close").onclick = closeDialog;
                overlay.onclick = (e) => {
                    if (e.target === overlay) closeDialog();
                };

                // Upload handler
                const fileInput = document.getElementById("i9_video_file_input");
                document.getElementById("i9_video_upload_btn").onclick = () => fileInput.click();

                fileInput.onchange = async (e) => {
                    const files = Array.from(e.target.files);
                    if (files.length === 0) return;

                    const status = document.getElementById("i9_video_status");
                    status.textContent = `Uploading ${files.length} video(s)...`;
                    status.style.color = "#4a4";

                    const formData = new FormData();
                    files.forEach(file => {
                        formData.append('video', file);
                    });

                    try {
                        const response = await fetch('/i9/video/upload', {
                            method: 'POST',
                            body: formData
                        });

                        const result = await response.json();

                        if (result.success) {
                            status.textContent = `✓ Uploaded ${result.files.length} video(s)`;
                            setTimeout(() => {
                                status.textContent = '';
                            }, 3000);
                            loadVideos();
                        } else {
                            status.textContent = `✗ Upload failed: ${result.error}`;
                            status.style.color = "#c44";
                        }
                    } catch (err) {
                        status.textContent = `✗ Upload error: ${err.message}`;
                        status.style.color = "#c44";
                    }

                    fileInput.value = '';
                };

                // Refresh handler
                document.getElementById("i9_video_refresh_btn").onclick = loadVideos;

                // Clear all handler
                document.getElementById("i9_video_clear_btn").onclick = async () => {
                    if (!confirm("Delete ALL videos from the batch pool? This cannot be undone.")) return;

                    const status = document.getElementById("i9_video_status");
                    status.textContent = "Clearing...";

                    try {
                        const response = await fetch('/i9/video/clear', {
                            method: 'POST'
                        });
                        const result = await response.json();

                        if (result.success) {
                            status.textContent = "✓ Cleared all videos";
                            status.style.color = "#4a4";
                            setTimeout(() => {
                                status.textContent = '';
                            }, 2000);
                            loadVideos();
                        }
                    } catch (err) {
                        status.textContent = `✗ Error: ${err.message}`;
                        status.style.color = "#c44";
                    }
                };

                // Load and display videos
                async function loadVideos() {
                    const grid = document.getElementById("i9_video_grid");
                    const status = document.getElementById("i9_video_status");

                    grid.innerHTML = '<div style="grid-column: 1/-1; text-align: center; color: #888; padding: 40px;">Loading...</div>';

                    try {
                        const response = await fetch('/i9/video/list');
                        const result = await response.json();

                        if (!result.success) {
                            grid.innerHTML = `<div style="grid-column: 1/-1; text-align: center; color: #c44; padding: 40px;">Error: ${result.error}</div>`;
                            return;
                        }

                        const videos = result.videos;

                        if (videos.length === 0) {
                            grid.innerHTML = '<div style="grid-column: 1/-1; text-align: center; color: #888; padding: 40px;">No videos in batch. Click "Upload Videos" to add some.</div>';
                            status.textContent = '0 videos';
                            return;
                        }

                        grid.innerHTML = '';
                        status.textContent = `${videos.length} video(s)`;

                        videos.forEach(video => {
                            const card = document.createElement("div");
                            card.style.cssText = `
                                background: #2a2a2a;
                                border-radius: 8px;
                                overflow: hidden;
                                cursor: pointer;
                                transition: transform 0.2s;
                                position: relative;
                            `;

                            card.onmouseenter = () => {
                                card.style.transform = "scale(1.05)";
                            };
                            card.onmouseleave = () => {
                                card.style.transform = "scale(1)";
                            };

                            card.innerHTML = `
                                <div style="position: relative; padding-top: 56.25%; background: #1a1a1a; display: flex; align-items: center; justify-content: center;">
                                    <div style="position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); font-size: 48px;">
                                        🎬
                                    </div>
                                </div>
                                <div style="padding: 10px;">
                                    <div style="font-size: 12px; color: #ccc; margin-bottom: 5px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${video.filename}">
                                        ${video.filename}
                                    </div>
                                    <div style="font-size: 10px; color: #888;">
                                        ${formatFileSize(video.size)}
                                    </div>
                                </div>
                                <button class="i9_video_delete_btn" data-filename="${video.filename}" style="position: absolute; top: 8px; right: 8px; background: rgba(204,68,68,0.9); color: #fff; border: none; padding: 6px 10px; border-radius: 4px; cursor: pointer; font-size: 12px; font-weight: bold;">
                                    ✕
                                </button>
                            `;

                            grid.appendChild(card);
                        });

                        // Attach delete handlers
                        grid.querySelectorAll(".i9_video_delete_btn").forEach(btn => {
                            btn.onclick = async (e) => {
                                e.stopPropagation();
                                const filename = btn.dataset.filename;

                                if (!confirm(`Delete ${filename}?`)) return;

                                try {
                                    const response = await fetch('/i9/video/delete', {
                                        method: 'DELETE',
                                        headers: {'Content-Type': 'application/json'},
                                        body: JSON.stringify({filename})
                                    });

                                    const result = await response.json();
                                    if (result.success) {
                                        loadVideos();
                                    }
                                } catch (err) {
                                    alert(`Error deleting video: ${err.message}`);
                                }
                            };
                        });

                    } catch (err) {
                        grid.innerHTML = `<div style="grid-column: 1/-1; text-align: center; color: #c44; padding: 40px;">Error loading videos: ${err.message}</div>`;
                    }
                }

                function formatFileSize(bytes) {
                    if (bytes < 1024) return bytes + ' B';
                    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
                    if (bytes < 1024 * 1024 * 1024) return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
                    return (bytes / (1024 * 1024 * 1024)).toFixed(1) + ' GB';
                }

                // Initial load
                loadVideos();
            };
        }
    }
});
