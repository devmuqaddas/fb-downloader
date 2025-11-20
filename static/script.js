class FacebookDownloader {
  constructor() {
    this.currentVideoData = null;
    this.currentDownloadId = null;
    this.progressInterval = null;
    this.currentFilename = null;
    this.isProcessing = false;
    this.progressCheckCount = 0;
    this.lastProgressUpdate = 0;
    this.init();
  }

  init() {
    this.bindEvents();
    this.loadRecentFiles();
  }

  bindEvents() {
    document.getElementById("urlForm").addEventListener("submit", (e) => {
      e.preventDefault();
      this.extractVideoInfo();
    });

    document.getElementById("extractBtn").addEventListener("click", () => {
      this.extractVideoInfo();
    });

    document.querySelectorAll(".format-tab").forEach((tab) => {
      tab.addEventListener("click", () => this.switchFormatTab(tab));
    });

    document
      .getElementById("downloadAnotherBtn")
      .addEventListener("click", () => {
        this.resetDownloader();
      });

    document.getElementById("refreshFilesBtn").addEventListener("click", () => {
      this.loadRecentFiles();
    });
  }

  switchFormatTab(tab) {
    const tabType = tab.dataset.tab;
    document
      .querySelectorAll(".format-tab")
      .forEach((t) => t.classList.remove("active"));
    document
      .querySelectorAll(".formats-grid")
      .forEach((g) => g.classList.remove("active"));
    tab.classList.add("active");
    document.getElementById(`${tabType}FormatsGrid`).classList.add("active");
  }

  showElement(id) {
    document.getElementById(id).classList.add("active");
  }

  hideElement(id) {
    document.getElementById(id).classList.remove("active");
  }

  hideAllSections() {
    this.hideElement("loading");
    this.hideElement("videoInfo");
    this.hideElement("error");
    this.hideElement("success");
    if (this.progressInterval) clearInterval(this.progressInterval);
  }

  async extractVideoInfo() {
    if (this.isProcessing) return;

    const url = document.getElementById("videoUrl").value.trim();
    if (!url) {
      this.showError("Please enter a Facebook video URL");
      return;
    }

    this.isProcessing = true;
    this.hideAllSections();
    this.showElement("loading");

    try {
      const response = await fetch("/extract_info", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url }),
      });

      const data = await response.json();
      if (!response.ok)
        throw new Error(data.detail || "Failed to extract video info");

      this.currentVideoData = data;
      this.displayVideoInfo(data);
    } catch (error) {
      this.showError(error.message);
    } finally {
      this.isProcessing = false;
    }
  }

  displayVideoInfo(data) {
    this.hideAllSections();

    // Set thumbnail
    const thumbnail = document.getElementById("thumbnail");
    if (data.thumbnail) {
      thumbnail.src = data.thumbnail;
    } else {
      thumbnail.style.display = "none";
    }

    // Set video details
    document.getElementById("videoTitle").textContent =
      data.title || "Unknown Title";
    document.querySelector("#videoUploader span").textContent =
      data.uploader || "Unknown";
    document.querySelector("#videoDuration span").textContent =
      this.formatDuration(data.duration);
    document.querySelector("#videoViews span").textContent =
      this.formatNumber(data.view_count) + " views";
    document.getElementById("videoDescription").textContent =
      data.description || "";

    // Populate formats
    const videoGrid = document.getElementById("videoFormatsGrid");
    const audioGrid = document.getElementById("audioFormatsGrid");
    videoGrid.innerHTML = "";
    audioGrid.innerHTML = "";

    if (!data.formats || data.formats.length === 0) {
      videoGrid.innerHTML = "<p>No formats available</p>";
      this.showElement("videoInfo");
      return;
    }

    data.formats.forEach((format) => {
      const card = this.createFormatCard(format);
      if (format.type === "audio_only") {
        audioGrid.appendChild(card);
      } else {
        videoGrid.appendChild(card);
      }
    });

    this.showElement("videoInfo");
  }

  createFormatCard(format) {
    const card = document.createElement("div");
    card.className = "format-card";

    if (format.type === "combined" || format.type === "best_combined") {
      card.classList.add("recommended");
    } else if (format.type === "audio_only") {
      card.classList.add("audio-only");
    }

    card.innerHTML = `
                    <div>
                        <div class="format-quality">${format.quality}</div>
                        <div class="format-details">
                            <div class="format-detail-item">${format.ext.toUpperCase()}</div>
                            ${
                              format.filesize
                                ? `<div class="format-detail-item">${this.formatFileSize(
                                    format.filesize
                                  )}</div>`
                                : ""
                            }
                            ${
                              format.fps
                                ? `<div class="format-detail-item">${format.fps}fps</div>`
                                : ""
                            }
                        </div>
                    </div>
                    <button class="btn-download-format" data-format-id="${
                      format.format_id
                    }">
                        <i class="fas fa-download"></i> Download
                    </button>
                `;

    card.querySelector(".btn-download-format").addEventListener("click", () => {
      this.downloadVideo(format.format_id);
    });

    return card;
  }

  async downloadVideo(formatId) {
    if (this.isProcessing) return;

    const url = document.getElementById("videoUrl").value.trim();
    this.isProcessing = true;
    this.hideAllSections();
    this.showElement("downloadSection");

    try {
      const response = await fetch("/download", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url, format_id: formatId }),
      });

      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Download failed");

      this.currentDownloadId = data.download_id;
      this.startProgressTracking();
    } catch (error) {
      this.showError(error.message);
    } finally {
      this.isProcessing = false;
    }
  }

  startProgressTracking() {
    let attempts = 0;
    const maxAttempts = 180;

    this.progressInterval = setInterval(async () => {
      attempts++;
      if (attempts > maxAttempts) {
        clearInterval(this.progressInterval);
        this.showError("Download timeout");
        return;
      }

      try {
        const response = await fetch(`/progress/${this.currentDownloadId}`);
        const progress = await response.json();

        if (progress.status === "downloading") {
          this.updateProgress(progress);
        } else if (progress.status === "finished") {
          this.downloadComplete(progress.filename);
          clearInterval(this.progressInterval);
        } else if (progress.status === "error") {
          this.showError(progress.error || "Download failed");
          clearInterval(this.progressInterval);
        }
      } catch (error) {
        console.error("Progress error:", error);
      }
    }, 2000);
  }

  updateProgress(progress) {
    const percent = Math.min(progress.percent || 0, 100);
    document.getElementById("progressFill").style.width = `${percent}%`;
    document.getElementById("progressPercent").textContent = `${Math.round(
      percent
    )}%`;
    document.getElementById("progressSpeed").textContent = `Speed: ${
      progress.speed || "N/A"
    }`;
    document.getElementById("progressEta").textContent = `ETA: ${
      progress.eta || "N/A"
    }`;
    if (progress.downloaded) {
      document.getElementById(
        "progressDownloaded"
      ).textContent = `Downloaded: ${this.formatFileSize(progress.downloaded)}`;
    }
    if (progress.total) {
      document.getElementById(
        "progressTotal"
      ).textContent = `Total: ${this.formatFileSize(progress.total)}`;
    }
  }

  downloadComplete(filename) {
    document.getElementById("progressFill").style.width = "100%";
    document.getElementById("progressPercent").textContent = "100%";
    this.currentFilename = filename;
    document.getElementById("downloadComplete").classList.add("active");
    document.getElementById("downloadFileBtn").onclick = () =>
      this.forceDownload(filename);
    this.loadRecentFiles();
  }

  async forceDownload(filename) {
    try {
      const downloadUrl = `/download_file/${encodeURIComponent(filename)}`;
      const response = await fetch(downloadUrl);
      if (!response.ok)
        throw new Error(`HTTP error! status: ${response.status}`);
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      setTimeout(() => {
        document.body.removeChild(a);
        window.URL.revokeObjectURL(url);
      }, 100);
    } catch (error) {
      console.error("Download error:", error);
    }
  }

  async loadRecentFiles() {
    try {
      const response = await fetch("/list_files");
      const files = await response.json();
      const filesList = document.getElementById("filesList");
      filesList.innerHTML = "";

      if (!files || files.length === 0) {
        filesList.innerHTML = '<div class="no-files">No downloads yet</div>';
        return;
      }

      files.forEach((file) => {
        const item = document.createElement("div");
        item.className = "file-item";
        item.innerHTML = `
                            <div class="file-info">
                                <i class="fas fa-file-video file-icon"></i>
                                <div class="file-details">
                                    <div class="file-name">${file.name}</div>
                                    <div class="file-size">${this.formatFileSize(
                                      file.size
                                    )}</div>
                                </div>
                            </div>
                            <button class="file-download-btn" onclick="facebookDownloader.forceDownload('${
                              file.name
                            }')">
                                <i class="fas fa-download"></i> Download
                            </button>
                        `;
        filesList.appendChild(item);
      });
    } catch (error) {
      console.error("Error loading files:", error);
    }
  }

  showError(message) {
    this.hideAllSections();
    document.getElementById("error").textContent = message;
    this.showElement("error");
  }

  resetDownloader() {
    this.isProcessing = false;
    this.hideAllSections();
    document.getElementById("videoUrl").value = "";
    document.getElementById("videoUrl").focus();
    this.loadRecentFiles();
  }

  formatDuration(seconds) {
    if (!seconds) return "0:00";
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, "0")}`;
  }

  formatNumber(num) {
    if (!num) return "0";
    if (num >= 1000000) return (num / 1000000).toFixed(1) + "M";
    if (num >= 1000) return (num / 1000).toFixed(1) + "K";
    return num.toString();
  }

  formatFileSize(bytes) {
    if (!bytes) return "0 B";
    const sizes = ["B", "KB", "MB", "GB"];
    const i = Math.floor(Math.log(bytes) / Math.log(1024));
    return Math.round((bytes / Math.pow(1024, i)) * 100) / 100 + " " + sizes[i];
  }
}

let facebookDownloader;
document.addEventListener("DOMContentLoaded", () => {
  facebookDownloader = new FacebookDownloader();
});
