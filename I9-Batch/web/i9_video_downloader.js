import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

app.registerExtension({
    name: "I9.VideoDownloader",

    async beforeRegisterNodeDef(nodeType, nodeData, app) {
        if (nodeData.name === "I9_VideoDownloader") {

            const onNodeCreated = nodeType.prototype.onNodeCreated;

            nodeType.prototype.onNodeCreated = function() {
                const r = onNodeCreated ? onNodeCreated.apply(this, arguments) : undefined;

                // Add download interface button
                this.addWidget("button", "video_download", "🎥 Download Video", () => {
                    this.showVideoDownloadInterface();
                });

                return r;
            };

            // Show video download interface
            nodeType.prototype.showVideoDownloadInterface = async function() {
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
                    width: 600px;
                    max-width: 90%;
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
                    <h2 style="margin: 0;">🎥 Instagram / TikTok Video Downloader</h2>
                    <button id="vd_close" style="background: #c44; color: #fff; border: none; padding: 8px 16px; border-radius: 4px; cursor: pointer; font-weight: bold;">
                        ✕ Close
                    </button>
                `;

                // Content
                const content = document.createElement("div");
                content.style.cssText = `
                    padding: 20px;
                `;

                content.innerHTML = `
                    <div style="margin-bottom: 20px;">
                        <label style="display: block; margin-bottom: 8px; font-weight: bold; color: #aaa;">Video URL</label>
                        <input type="text" id="vd_url" placeholder="https://www.instagram.com/reel/... or https://www.tiktok.com/..." style="width: 100%; padding: 10px; background: #1a1a1a; border: 1px solid #444; border-radius: 4px; color: #fff; font-size: 14px;">
                        <div style="margin-top: 6px; font-size: 11px; color: #888;">
                            Supports Instagram Reels and TikTok videos
                        </div>
                    </div>

                    <div style="margin-bottom: 20px;">
                        <label style="display: block; margin-bottom: 12px; font-weight: bold; color: #aaa;">Download Type</label>

                        <div style="margin-bottom: 12px;">
                            <label style="display: flex; align-items: center; padding: 12px; background: #1a1a1a; border-radius: 4px; cursor: pointer; border: 2px solid #4a4;">
                                <input type="radio" name="vd_download_type" value="frame" checked style="margin-right: 10px;">
                                <div style="flex: 1;">
                                    <div style="font-weight: bold;">Extract Frame</div>
                                    <div style="font-size: 11px; color: #888; margin-top: 2px;">Extract a specific frame as an image</div>
                                </div>
                            </label>
                            <div id="vd_frame_settings" style="margin-top: 8px; padding: 10px; background: #0f0f0f; border-radius: 4px;">
                                <label style="display: block; font-size: 11px; color: #888; margin-bottom: 4px;">Frame Number</label>
                                <input type="number" id="vd_frame_number" value="0" min="0" style="width: 100%; padding: 8px; background: #1a1a1a; border: 1px solid #444; border-radius: 4px; color: #fff;">
                                <div style="margin-top: 4px; font-size: 10px; color: #666;">0 = first frame, 30 = ~1 second (at 30fps)</div>
                            </div>
                        </div>

                        <div>
                            <label style="display: flex; align-items: center; padding: 12px; background: #1a1a1a; border-radius: 4px; cursor: pointer; border: 2px solid #444;">
                                <input type="radio" name="vd_download_type" value="video" style="margin-right: 10px;">
                                <div style="flex: 1;">
                                    <div style="font-weight: bold;">Download Full Video</div>
                                    <div style="font-size: 11px; color: #888; margin-top: 2px;">Save the complete video file</div>
                                </div>
                            </label>
                        </div>
                    </div>

                    <button id="vd_download_btn" style="width: 100%; background: #4a4; color: #fff; border: none; padding: 14px; border-radius: 4px; cursor: pointer; font-weight: bold; font-size: 16px; margin-bottom: 10px;">
                        ⬇️ Download
                    </button>

                    <div id="vd_status" style="padding: 15px; background: #1a1a1a; border-radius: 4px; min-height: 60px; color: #888; font-size: 13px; text-align: center; display: flex; align-items: center; justify-content: center;">
                        Enter a video URL and click download
                    </div>
                `;

                dialog.appendChild(header);
                dialog.appendChild(content);
                overlay.appendChild(dialog);
                document.body.appendChild(overlay);

                // Event handlers
                const closeDialog = () => document.body.removeChild(overlay);

                document.getElementById("vd_close").onclick = closeDialog;
                overlay.onclick = (e) => {
                    if (e.target === overlay) closeDialog();
                };

                // Toggle download type
                const radios = document.querySelectorAll('input[name="vd_download_type"]');
                radios.forEach(radio => {
                    radio.onchange = () => {
                        document.getElementById('vd_frame_settings').style.display =
                            radio.value === 'frame' ? 'block' : 'none';

                        // Update border color
                        radios.forEach(r => {
                            r.parentElement.style.borderColor = r.checked ? '#4a4' : '#444';
                        });
                    };
                });

                // Download button handler
                document.getElementById("vd_download_btn").onclick = async () => {
                    const videoUrl = document.getElementById("vd_url").value.trim();
                    if (!videoUrl) {
                        alert("Please enter a video URL");
                        return;
                    }

                    const downloadType = document.querySelector('input[name="vd_download_type"]:checked').value;
                    const frameNumber = parseInt(document.getElementById("vd_frame_number").value) || 0;

                    const status = document.getElementById("vd_status");
                    const downloadBtn = document.getElementById("vd_download_btn");

                    downloadBtn.disabled = true;
                    downloadBtn.style.opacity = "0.5";

                    if (downloadType === 'frame') {
                        status.textContent = `Downloading and extracting frame ${frameNumber}...`;
                    } else {
                        status.textContent = "Downloading video...";
                    }
                    status.style.color = "#4a4";

                    const requestData = {
                        video_url: videoUrl,
                        download_type: downloadType,
                        frame_number: frameNumber
                    };

                    try {
                        const response = await fetch('/i9/videodownload/fetch', {
                            method: 'POST',
                            headers: {'Content-Type': 'application/json'},
                            body: JSON.stringify(requestData)
                        });

                        const result = await response.json();

                        if (result.success) {
                            if (result.type === 'frame') {
                                status.innerHTML = `✓ Frame extracted successfully<br><small style="color: #888;">Saved as: ${result.filename}</small><br><small style="color: #888;">Execute the node to load the frame</small>`;
                            } else {
                                status.innerHTML = `✓ Video downloaded successfully<br><small style="color: #888;">Saved as: ${result.filename}</small><br><small style="color: #888;">Available in I9_VideoPool</small>`;
                            }
                            status.style.color = "#4a4";
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
            };
        }
    }
});
