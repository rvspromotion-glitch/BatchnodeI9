import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

app.registerExtension({
    name: "I9.InstagramDownloader",

    async beforeRegisterNodeDef(nodeType, nodeData, app) {
        if (nodeData.name === "I9_InstagramDownloader") {

            const onNodeCreated = nodeType.prototype.onNodeCreated;

            nodeType.prototype.onNodeCreated = function() {
                const r = onNodeCreated ? onNodeCreated.apply(this, arguments) : undefined;

                // Add download interface button
                this.addWidget("button", "download_interface", "📷 Instagram Download", () => {
                    this.showDownloadInterface();
                });

                return r;
            };

            // Show Instagram download interface
            nodeType.prototype.showDownloadInterface = async function() {
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
                    width: 90%;
                    max-width: 1400px;
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
                    <h2 style="margin: 0;">📷 Instagram Profile Downloader</h2>
                    <button id="ig_close" style="background: #c44; color: #fff; border: none; padding: 8px 16px; border-radius: 4px; cursor: pointer; font-weight: bold;">
                        ✕ Close
                    </button>
                `;

                // Main content container
                const mainContent = document.createElement("div");
                mainContent.style.cssText = `
                    display: flex;
                    flex: 1;
                    overflow: hidden;
                `;

                // Left panel - Download settings
                const leftPanel = document.createElement("div");
                leftPanel.style.cssText = `
                    width: 400px;
                    padding: 20px;
                    background: #252525;
                    overflow-y: auto;
                    border-right: 1px solid #333;
                `;

                leftPanel.innerHTML = `
                    <div style="margin-bottom: 20px;">
                        <label style="display: block; margin-bottom: 8px; font-weight: bold; color: #aaa;">Profile URL</label>
                        <input type="text" id="ig_profile_url" placeholder="https://instagram.com/username" style="width: 100%; padding: 10px; background: #1a1a1a; border: 1px solid #444; border-radius: 4px; color: #fff; font-size: 14px;">
                    </div>

                    <div style="margin-bottom: 20px;">
                        <label style="display: block; margin-bottom: 12px; font-weight: bold; color: #aaa;">Download Mode</label>

                        <div style="margin-bottom: 12px;">
                            <label style="display: flex; align-items: center; padding: 12px; background: #1a1a1a; border-radius: 4px; cursor: pointer; border: 2px solid #444;">
                                <input type="radio" name="download_mode" value="all" checked style="margin-right: 10px;">
                                <div>
                                    <div style="font-weight: bold;">Download All Posts</div>
                                    <div style="font-size: 11px; color: #888; margin-top: 2px;">Download all images from the profile</div>
                                </div>
                            </label>
                        </div>

                        <div style="margin-bottom: 12px;">
                            <label style="display: flex; align-items: center; padding: 12px; background: #1a1a1a; border-radius: 4px; cursor: pointer; border: 2px solid #444;">
                                <input type="radio" name="download_mode" value="sequence" style="margin-right: 10px;">
                                <div style="flex: 1;">
                                    <div style="font-weight: bold;">Download by Sequence</div>
                                    <div style="font-size: 11px; color: #888; margin-top: 2px;">Set range of posts to download</div>
                                </div>
                            </label>
                            <div id="sequence_settings" style="margin-top: 8px; padding: 10px; background: #0f0f0f; border-radius: 4px; display: none;">
                                <div style="display: flex; gap: 10px; align-items: center;">
                                    <div style="flex: 1;">
                                        <label style="display: block; font-size: 11px; color: #888; margin-bottom: 4px;">From</label>
                                        <input type="number" id="ig_start_index" value="0" min="0" style="width: 100%; padding: 6px; background: #1a1a1a; border: 1px solid #444; border-radius: 4px; color: #fff;">
                                    </div>
                                    <div style="flex: 1;">
                                        <label style="display: block; font-size: 11px; color: #888; margin-bottom: 4px;">To</label>
                                        <input type="number" id="ig_end_index" value="100" min="1" style="width: 100%; padding: 6px; background: #1a1a1a; border: 1px solid #444; border-radius: 4px; color: #fff;">
                                    </div>
                                </div>
                            </div>
                        </div>

                        <div style="margin-bottom: 12px;">
                            <label style="display: flex; align-items: center; padding: 12px; background: #1a1a1a; border-radius: 4px; cursor: pointer; border: 2px solid #444;">
                                <input type="radio" name="download_mode" value="timeframe" style="margin-right: 10px;">
                                <div style="flex: 1;">
                                    <div style="font-weight: bold;">Download by Timeframe</div>
                                    <div style="font-size: 11px; color: #888; margin-top: 2px;">Set date range for posts</div>
                                </div>
                            </label>
                            <div id="timeframe_settings" style="margin-top: 8px; padding: 10px; background: #0f0f0f; border-radius: 4px; display: none;">
                                <div style="margin-bottom: 8px;">
                                    <label style="display: block; font-size: 11px; color: #888; margin-bottom: 4px;">From</label>
                                    <input type="date" id="ig_start_date" value="2024-01-01" style="width: 100%; padding: 6px; background: #1a1a1a; border: 1px solid #444; border-radius: 4px; color: #fff;">
                                </div>
                                <div>
                                    <label style="display: block; font-size: 11px; color: #888; margin-bottom: 4px;">To</label>
                                    <input type="date" id="ig_end_date" value="2024-12-31" style="width: 100%; padding: 6px; background: #1a1a1a; border: 1px solid #444; border-radius: 4px; color: #fff;">
                                </div>
                            </div>
                        </div>
                    </div>

                    <button id="ig_download_btn" style="width: 100%; background: #4a4; color: #fff; border: none; padding: 14px; border-radius: 4px; cursor: pointer; font-weight: bold; font-size: 16px; margin-bottom: 10px;">
                        ⬇️ Download Images
                    </button>

                    <div id="ig_download_status" style="padding: 10px; background: #1a1a1a; border-radius: 4px; min-height: 60px; color: #888; font-size: 13px; text-align: center; display: flex; align-items: center; justify-content: center;">
                        Enter a profile URL and click download
                    </div>
                `;

                // Right panel - Image preview
                const rightPanel = document.createElement("div");
                rightPanel.style.cssText = `
                    flex: 1;
                    display: flex;
                    flex-direction: column;
                    background: #1e1e1e;
                `;

                const rightToolbar = document.createElement("div");
                rightToolbar.style.cssText = `
                    padding: 15px 20px;
                    background: #252525;
                    border-bottom: 1px solid #333;
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                `;
                rightToolbar.innerHTML = `
                    <h3 style="margin: 0; font-size: 16px;">Downloaded Images</h3>
                    <div style="display: flex; gap: 10px;">
                        <button id="ig_refresh_btn" style="background: #44a; color: #fff; border: none; padding: 8px 16px; border-radius: 4px; cursor: pointer;">
                            🔄 Refresh
                        </button>
                        <button id="ig_clear_btn" style="background: #c44; color: #fff; border: none; padding: 8px 16px; border-radius: 4px; cursor: pointer;">
                            🗑️ Clear All
                        </button>
                    </div>
                `;

                const gridContainer = document.createElement("div");
                gridContainer.style.cssText = `
                    flex: 1;
                    overflow-y: auto;
                    padding: 20px;
                `;

                const grid = document.createElement("div");
                grid.id = "ig_image_grid";
                grid.style.cssText = `
                    display: grid;
                    grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
                    gap: 15px;
                `;
                gridContainer.appendChild(grid);

                rightPanel.appendChild(rightToolbar);
                rightPanel.appendChild(gridContainer);

                mainContent.appendChild(leftPanel);
                mainContent.appendChild(rightPanel);

                dialog.appendChild(header);
                dialog.appendChild(mainContent);
                overlay.appendChild(dialog);
                document.body.appendChild(overlay);

                // Event handlers
                const closeDialog = () => document.body.removeChild(overlay);

                document.getElementById("ig_close").onclick = closeDialog;
                overlay.onclick = (e) => {
                    if (e.target === overlay) closeDialog();
                };

                // Toggle download mode settings
                const radios = document.querySelectorAll('input[name="download_mode"]');
                radios.forEach(radio => {
                    radio.onchange = () => {
                        document.getElementById('sequence_settings').style.display =
                            radio.value === 'sequence' ? 'block' : 'none';
                        document.getElementById('timeframe_settings').style.display =
                            radio.value === 'timeframe' ? 'block' : 'none';

                        // Update border color
                        radios.forEach(r => {
                            r.parentElement.style.borderColor = r.checked ? '#4a4' : '#444';
                        });
                    };
                });

                // Download button handler
                document.getElementById("ig_download_btn").onclick = async () => {
                    const profileUrl = document.getElementById("ig_profile_url").value.trim();
                    if (!profileUrl) {
                        alert("Please enter an Instagram profile URL");
                        return;
                    }

                    const downloadMode = document.querySelector('input[name="download_mode"]:checked').value;
                    const status = document.getElementById("ig_download_status");
                    const downloadBtn = document.getElementById("ig_download_btn");

                    downloadBtn.disabled = true;
                    downloadBtn.style.opacity = "0.5";
                    status.textContent = "Downloading images from Instagram...";
                    status.style.color = "#4a4";

                    const requestData = {
                        profile_url: profileUrl,
                        download_mode: downloadMode,
                        start_index: parseInt(document.getElementById("ig_start_index").value) || 0,
                        end_index: parseInt(document.getElementById("ig_end_index").value) || 100,
                        start_date: document.getElementById("ig_start_date").value,
                        end_date: document.getElementById("ig_end_date").value
                    };

                    try {
                        const response = await fetch('/i9/instagram/download', {
                            method: 'POST',
                            headers: {'Content-Type': 'application/json'},
                            body: JSON.stringify(requestData)
                        });

                        const result = await response.json();

                        if (result.success) {
                            status.textContent = `✓ Successfully downloaded ${result.count} image(s)`;
                            status.style.color = "#4a4";
                            loadImages();
                        } else {
                            status.textContent = `✗ Error: ${result.error}`;
                            status.style.color = "#c44";
                        }
                    } catch (err) {
                        status.textContent = `✗ Download failed: ${err.message}`;
                        status.style.color = "#c44";
                    } finally {
                        downloadBtn.disabled = false;
                        downloadBtn.style.opacity = "1";
                    }
                };

                // Refresh and clear handlers (use existing I9_ImagePool endpoints)
                document.getElementById("ig_refresh_btn").onclick = loadImages;

                document.getElementById("ig_clear_btn").onclick = async () => {
                    if (!confirm("Delete ALL images from the batch pool? This cannot be undone.")) return;

                    try {
                        const response = await fetch('/i9/batch/clear', {
                            method: 'POST'
                        });
                        const result = await response.json();

                        if (result.success) {
                            loadImages();
                        }
                    } catch (err) {
                        alert(`Error: ${err.message}`);
                    }
                };

                // Load and display images
                async function loadImages() {
                    const grid = document.getElementById("ig_image_grid");

                    grid.innerHTML = '<div style="grid-column: 1/-1; text-align: center; color: #888; padding: 40px;">Loading...</div>';

                    try {
                        const response = await fetch('/i9/batch/list');
                        const result = await response.json();

                        if (!result.success) {
                            grid.innerHTML = `<div style="grid-column: 1/-1; text-align: center; color: #c44; padding: 40px;">Error: ${result.error}</div>`;
                            return;
                        }

                        const images = result.images;

                        if (images.length === 0) {
                            grid.innerHTML = '<div style="grid-column: 1/-1; text-align: center; color: #888; padding: 40px;">No images downloaded yet</div>';
                            return;
                        }

                        grid.innerHTML = '';

                        images.forEach(img => {
                            const card = document.createElement("div");
                            card.style.cssText = `
                                background: #2a2a2a;
                                border-radius: 8px;
                                overflow: hidden;
                                cursor: pointer;
                                transition: transform 0.2s;
                                position: relative;
                            `;

                            card.onmouseenter = () => card.style.transform = "scale(1.05)";
                            card.onmouseleave = () => card.style.transform = "scale(1)";

                            const imgUrl = `/view?filename=${encodeURIComponent(img.filename)}&subfolder=I9_ImagePool&type=input&rand=${Math.random()}`;

                            card.innerHTML = `
                                <div style="position: relative; padding-top: 100%; background: #1a1a1a;">
                                    <img src="${imgUrl}" style="position: absolute; top: 0; left: 0; width: 100%; height: 100%; object-fit: cover;" />
                                </div>
                                <button class="ig_delete_btn" data-filename="${img.filename}" style="position: absolute; top: 4px; right: 4px; background: rgba(204,68,68,0.9); color: #fff; border: none; padding: 4px 8px; border-radius: 4px; cursor: pointer; font-size: 11px; font-weight: bold;">
                                    ✕
                                </button>
                            `;

                            grid.appendChild(card);
                        });

                        // Attach delete handlers
                        grid.querySelectorAll(".ig_delete_btn").forEach(btn => {
                            btn.onclick = async (e) => {
                                e.stopPropagation();
                                const filename = btn.dataset.filename;

                                if (!confirm(`Delete ${filename}?`)) return;

                                try {
                                    const response = await fetch('/i9/batch/delete', {
                                        method: 'DELETE',
                                        headers: {'Content-Type': 'application/json'},
                                        body: JSON.stringify({filename})
                                    });

                                    const result = await response.json();
                                    if (result.success) {
                                        loadImages();
                                    }
                                } catch (err) {
                                    alert(`Error deleting image: ${err.message}`);
                                }
                            };
                        });

                    } catch (err) {
                        grid.innerHTML = `<div style="grid-column: 1/-1; text-align: center; color: #c44; padding: 40px;">Error loading images: ${err.message}</div>`;
                    }
                }

                // Initial load
                loadImages();
            };
        }
    }
});
