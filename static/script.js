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
    // Extract button
    document.getElementById("extractBtn").addEventListener("click", () => {
      this.extractVideoInfo();
    });
    // Reset button
    document.getElementById("resetBtn").addEventListener("click", () => {
      this.resetDownloader();
    });
    // Enter key on URL input
    document.getElementById("videoUrl").addEventListener("keypress", (e) => {
      if (e.key === "Enter") {
        this.extractVideoInfo();
      }
    });
    // Retry button
    document.getElementById("retryBtn").addEventListener("click", () => {
      this.hideAllSections();
      document.getElementById("videoUrl").focus();
    });
    // Reset from error button
    document
      .getElementById("resetFromErrorBtn")
      .addEventListener("click", () => {
        this.resetDownloader();
      });
    // Download another button
    document
      .getElementById("downloadAnotherBtn")
      .addEventListener("click", () => {
        this.resetDownloader();
      });
    // Refresh files button
    document.getElementById("refreshFilesBtn").addEventListener("click", () => {
      this.loadRecentFiles();
    });
  }
  // Clear all previous data and UI state
  clearPreviousData() {
    console.log("🧹 Clearing previous data...");
    // Clear video data
    this.currentVideoData = null;
    this.currentDownloadId = null;
    this.currentFilename = null;
    this.progressCheckCount = 0;
    this.lastProgressUpdate = 0;
    // Clear video info elements
    document.getElementById("videoTitle").textContent = "Video Title";
    document.getElementById("videoUploader").innerHTML =
      '<i class="fas fa-user"></i> Unknown';
    document.getElementById("videoDuration").innerHTML =
      '<i class="fas fa-clock"></i> 0:00';
    document.getElementById("videoViews").innerHTML =
      '<i class="fas fa-eye"></i> 0 views';
    document.getElementById("videoDescription").textContent = "";

    // Reset thumbnail to placeholder
    const thumbnailContainer = document.getElementById("videoThumbnail");
    thumbnailContainer.innerHTML = '<i class="fas fa-video"></i>';
    thumbnailContainer.className = "placeholder-image";
    // Clear format list
    document.getElementById("formatList").innerHTML = "";
    // Reset progress
    this.resetProgress();
    // Clear timers
    this.clearTimers();
  }
  resetProgress() {
    document.getElementById("progressFill").style.width = "0%";
    document.getElementById("progressPercent").textContent = "0%";
    document.getElementById("progressSpeed").textContent = "Speed: N/A";
    document.getElementById("progressEta").textContent = "ETA: N/A";
    document.getElementById("progressDownloaded").textContent =
      "Downloaded: 0 MB";
    document.getElementById("progressTotal").textContent = "Total: 0 MB";
    document.getElementById("downloadComplete").classList.add("hidden");
  }
  clearTimers() {
    if (this.progressInterval) {
      clearInterval(this.progressInterval);
      this.progressInterval = null;
    }
    if (this.autoResetTimer) clearTimeout(this.autoResetTimer);
    if (this.autoResetCountdown) clearInterval(this.autoResetCountdown);
  }
  async forceDownload(filename) {
    try {
      console.log(`🔽 Starting download for: ${filename}`);
      const downloadUrl = `/download_file/${encodeURIComponent(filename)}`;
      try {
        const response = await fetch(downloadUrl);
        if (!response.ok) {
          throw new Error(`HTTP error! status: ${response.status}`);
        }
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.style.display = "none";
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        setTimeout(() => {
          document.body.removeChild(a);
          window.URL.revokeObjectURL(url);
        }, 100);
        this.showToast(
          "Download started! Check your Downloads folder.",
          "success"
        );
      } catch (fetchError) {
        console.log("⚠️ Fetch method failed, trying direct link method");
        const a = document.createElement("a");
        a.href = downloadUrl;
        a.download = filename;
        a.target = "_self";
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        this.showToast(
          'Download started! If it opens in browser, right-click and "Save As"',
          "success"
        );
      }
    } catch (error) {
      console.error("❌ Download error:", error);
      this.showToast(
        "Download failed. Please try again or check the Recent Downloads section.",
        "error"
      );
    }
  }
  showToast(message, type = "success") {
    const toast = document.createElement("div");
    toast.className = `toast ${type}`;
    toast.innerHTML = `
            <i class="fas ${
              type === "success" ? "fa-check-circle" : "fa-exclamation-triangle"
            }"></i>
            <span>${message}</span>
            <button class="toast-close" onclick="this.parentElement.remove()">
                <i class="fas fa-times"></i>
            </button>
        `;
    document.getElementById("toastContainer").appendChild(toast);
    setTimeout(() => {
      toast.classList.add("show");
    }, 100);
    setTimeout(() => {
      if (toast.parentNode) {
        toast.classList.remove("show");
        setTimeout(() => {
          if (toast.parentNode) {
            toast.parentNode.removeChild(toast);
          }
        }, 300);
      }
    }, 5000);
  }
  resetDownloader() {
    console.log("🔄 Resetting downloader...");
    this.isProcessing = false;
    this.clearPreviousData();
    // Clear URL input
    document.getElementById("videoUrl").value = "";
    // Hide all sections
    this.hideAllSections();
    // Focus on URL input
    document.getElementById("videoUrl").focus();
    // Refresh files list
    this.loadRecentFiles();
    this.showToast("Downloader reset successfully!", "success");
    console.log("✅ Downloader reset complete");
  }
  // startAutoReset() {
  //   let countdown = 10;
  //   const countdownElement =
  //     document.getElementById("autoResetCountdown");
  //   this.autoResetCountdown = setInterval(() => {
  //     countdown--;
  //     if (countdownElement) {
  //       countdownElement.textContent = countdown;
  //     }
  //     if (countdown <= 0) {
  //       clearInterval(this.autoResetCountdown);
  //       this.resetDownloader();
  //     }
  //   }, 1000);
  //   this.autoResetTimer = setTimeout(() => {
  //     this.resetDownloader();
  //   }, 10000);
  // }
  cancelAutoReset() {
    this.clearTimers();
  }
  async extractVideoInfo() {
    if (this.isProcessing) {
      console.log("⚠️ Already processing, ignoring request");
      return;
    }
    const url = document.getElementById("videoUrl").value.trim();
    if (!url) {
      this.showError("Please enter a Facebook video URL");
      return;
    }
    if (!this.isValidFacebookUrl(url)) {
      this.showError(
        "Please enter a valid Facebook video URL (facebook.com, m.facebook.com, or fb.watch)"
      );
      return;
    }
    this.isProcessing = true;
    this.clearPreviousData();
    this.hideAllSections();
    this.showLoading("Extracting video information...");
    try {
      const response = await fetch("/extract_info", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ url: url }),
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || "Failed to extract video info");
      }
      this.currentVideoData = data;
      this.displayVideoInfo(data);
    } catch (error) {
      console.error("Extract error:", error);
      this.showError(error.message);
    } finally {
      this.isProcessing = false;
    }
  }
  displayVideoInfo(data) {
    this.hideAllSections();
    // Set video thumbnail with fallback
    const thumbnailContainer = document.getElementById("videoThumbnail");
    if (data.thumbnail) {
      // Create img element and replace placeholder
      const img = document.createElement("img");
      img.src = data.thumbnail;
      img.alt = "Video Thumbnail";
      img.style.width = "100%";
      img.style.height = "100%";
      img.style.objectFit = "cover";

      img.onerror = () => {
        // If image fails to load, revert to placeholder
        thumbnailContainer.innerHTML = '<i class="fas fa-video"></i>';
        thumbnailContainer.className = "placeholder-image";
      };

      img.onload = () => {
        // Replace placeholder with actual image
        thumbnailContainer.innerHTML = "";
        thumbnailContainer.appendChild(img);
        thumbnailContainer.className = "";
      };
    } else {
      // Keep placeholder
      thumbnailContainer.innerHTML = '<i class="fas fa-video"></i>';
      thumbnailContainer.className = "placeholder-image";
    }
    // Set video details
    document.getElementById("videoTitle").textContent =
      data.title || "Unknown Title";
    document.getElementById(
      "videoUploader"
    ).innerHTML = `<i class="fas fa-user"></i> ${data.uploader || "Unknown"}`;
    document.getElementById(
      "videoDuration"
    ).innerHTML = `<i class="fas fa-clock"></i> ${this.formatDuration(
      data.duration
    )}`;
    document.getElementById(
      "videoViews"
    ).innerHTML = `<i class="fas fa-eye"></i> ${this.formatNumber(
      data.view_count
    )} views`;
    // Set description
    const descElement = document.getElementById("videoDescription");
    if (data.description) {
      descElement.textContent = data.description;
      descElement.style.display = "block";
    } else {
      descElement.style.display = "none";
    }
    // Populate formats
    const formatList = document.getElementById("formatList");
    formatList.innerHTML = "";
    if (!data.formats || data.formats.length === 0) {
      formatList.innerHTML =
        '<p class="no-formats">No downloadable formats available</p>';
      document.getElementById("videoInfoSection").classList.remove("hidden");
      return;
    }
    data.formats.forEach((format) => {
      const formatItem = document.createElement("div");
      formatItem.className = "format-item";
      let priorityBadge = "";
      if (format.type === "combined" || format.type === "best_combined") {
        priorityBadge = '<span class="priority-badge">RECOMMENDED</span>';
      }
      const formatDetails = this.getFormatDetails(format);
      formatItem.innerHTML = `
                <div class="format-info">
                    <div class="format-quality">
                        <i class="fas ${
                          format.type === "audio_only" ? "fa-music" : "fa-video"
                        }"></i>
                        ${format.quality}
                        ${priorityBadge}
                    </div>
                    <div class="format-details">
                        ${formatDetails}
                    </div>
                </div>
                <button class="download-format-btn ${
                  format.type === "combined" || format.type === "best_combined"
                    ? "recommended"
                    : ""
                }" data-format-id="${format.format_id}">
                    <i class="fas fa-download"></i>
                    <span>Download</span>
                </button>
            `;
      formatItem
        .querySelector(".download-format-btn")
        .addEventListener("click", () => {
          this.downloadVideo(format.format_id);
        });
      formatList.appendChild(formatItem);
    });
    document.getElementById("videoInfoSection").classList.remove("hidden");
  }
  getFormatDetails(format) {
    if (format.type === "combined" || format.type === "best_combined") {
      return `
                <span class="format-ext">${format.ext.toUpperCase()}</span>
                <span class="format-size">${this.formatFileSize(
                  format.filesize
                )}</span>
                <span class="format-audio"><i class="fas fa-volume-up"></i> Audio</span>
                ${
                  format.fps
                    ? `<span class="format-fps">${format.fps}fps</span>`
                    : ""
                }
            `;
    } else if (format.type === "video_only") {
      return `
                <span class="format-ext">${format.ext.toUpperCase()}</span>
                <span class="format-size">${this.formatFileSize(
                  format.filesize
                )}</span>
                <span class="format-audio-warning"><i class="fas fa-volume-mute"></i> No Audio</span>
                ${
                  format.fps
                    ? `<span class="format-fps">${format.fps}fps</span>`
                    : ""
                }
            `;
    } else {
      return `
                <span class="format-ext">${format.ext.toUpperCase()}</span>
                <span class="format-size">${this.formatFileSize(
                  format.filesize
                )}</span>
                ${
                  format.abr
                    ? `<span class="format-bitrate">${format.abr}kbps</span>`
                    : ""
                }
            `;
    }
  }
  async downloadVideo(formatId) {
    if (this.isProcessing) {
      console.log("⚠️ Already processing, ignoring download request");
      return;
    }
    const url = document.getElementById("videoUrl").value.trim();
    this.isProcessing = true;
    this.hideAllSections();
    this.showLoading("Starting ultra-fast download...");
    try {
      const response = await fetch("/download", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          url: url,
          format_id: formatId,
        }),
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || "Download failed");
      }
      this.currentDownloadId = data.download_id;
      this.progressCheckCount = 0;
      this.lastProgressUpdate = Date.now();
      this.hideAllSections();
      document.getElementById("downloadSection").classList.remove("hidden");
      this.startProgressTracking();
    } catch (error) {
      console.error("Download error:", error);
      this.showError(error.message);
    } finally {
      this.isProcessing = false;
    }
  }
  startProgressTracking() {
    let attempts = 0;
    const maxAttempts = 180; // 3 minutes max (reduced from 5 minutes)
    let consecutiveNoProgress = 0;
    let lastPercent = 0;
    // Start with faster polling, then slow down
    let pollInterval = 2000; // Start with 2 seconds
    this.progressInterval = setInterval(async () => {
      attempts++;
      this.progressCheckCount++;
      if (attempts > maxAttempts) {
        clearInterval(this.progressInterval);
        this.showError("Download timeout. Please try again.");
        return;
      }
      try {
        const response = await fetch(`/progress/${this.currentDownloadId}`);
        const progress = await response.json();
        if (progress.status === "downloading") {
          this.updateProgress(progress);
          // Check if progress is stuck
          const currentPercent = progress.percent || 0;
          if (currentPercent === lastPercent) {
            consecutiveNoProgress++;
            if (consecutiveNoProgress > 10) {
              // 20 seconds of no progress
              console.log(
                "⚠️ Download appears stuck, checking for completion..."
              );
              // Don't error immediately, let backend handle it
            }
          } else {
            consecutiveNoProgress = 0;
            lastPercent = currentPercent;
            // Slow down polling as download progresses
            if (currentPercent > 50 && pollInterval < 3000) {
              clearInterval(this.progressInterval);
              pollInterval = 3000;
              this.startProgressTracking(); // Restart with slower interval
              return;
            }
          }
        } else if (progress.status === "finished") {
          this.downloadComplete(progress.filename);
          clearInterval(this.progressInterval);
        } else if (progress.status === "error") {
          this.showError(progress.error || "Download failed");
          clearInterval(this.progressInterval);
        } else if (
          progress.status === "starting" ||
          progress.status === "preparing"
        ) {
          document.getElementById("loadingText").textContent =
            progress.message || "Preparing download...";
        } else if (
          progress.status === "merging" ||
          progress.status === "processing"
        ) {
          this.updateProgress({
            ...progress,
            percent: Math.max(progress.percent || 95, 95),
          });
        }
      } catch (error) {
        console.error("Progress tracking error:", error);
        // Don't stop on network errors, but count them
        consecutiveNoProgress++;
        if (consecutiveNoProgress > 15) {
          clearInterval(this.progressInterval);
          this.showError(
            "Connection lost. Please check your internet and try again."
          );
        }
      }
    }, pollInterval);
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
    this.lastProgressUpdate = Date.now();
  }
  downloadComplete(filename) {
    document.getElementById("progressFill").style.width = "100%";
    document.getElementById("progressPercent").textContent = "100%";
    this.currentFilename = filename;
    const downloadComplete = document.getElementById("downloadComplete");
    const downloadBtn = document.getElementById("downloadFileBtn");
    downloadBtn.onclick = () => {
      this.forceDownload(filename);
    };
    downloadComplete.classList.remove("hidden");
    this.loadRecentFiles();
    // this.startAutoReset();
    console.log("✅ Download completed, auto-reset will start in 10 seconds");
  }

  showLoading(message = "Loading...") {
    document.getElementById("loadingText").textContent = message;
    document.getElementById("loadingSection").classList.remove("hidden");
  }
  showError(message) {
    this.hideAllSections();
    document.getElementById("errorMessage").textContent = message;
    document.getElementById("errorSection").classList.remove("hidden");
    this.isProcessing = false;
  }
  hideAllSections() {
    const sections = [
      "loadingSection",
      "videoInfoSection",
      // "downloadSection",
      "errorSection",
    ];
    sections.forEach((id) => {
      document.getElementById(id).classList.add("hidden");
    });
    this.clearTimers();
  }
  isValidFacebookUrl(url) {
    const lowerUrl = url.toLowerCase();
    return (
      lowerUrl.includes("facebook.com") ||
      lowerUrl.includes("fb.watch") ||
      lowerUrl.includes("m.facebook.com")
    );
  }
  formatDuration(seconds) {
    if (!seconds || seconds === 0) return "0:00";
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, "0")}`;
  }
  formatNumber(num) {
    if (!num || num === 0) return "0";
    if (num >= 1000000) return (num / 1000000).toFixed(1) + "M";
    if (num >= 1000) return (num / 1000).toFixed(1) + "K";
    return num.toString();
  }
  formatFileSize(bytes) {
    if (!bytes || bytes === 0) return "Unknown";
    const sizes = ["Bytes", "KB", "MB", "GB"];
    const i = Math.floor(Math.log(bytes) / Math.log(1024));
    return Math.round((bytes / Math.pow(1024, i)) * 100) / 100 + " " + sizes[i];
  }
  truncateFilename(filename, maxLength) {
    if (filename.length <= maxLength) return filename;
    const ext = filename.split(".").pop();
    const name = filename.substring(0, filename.lastIndexOf("."));
    const truncated = name.substring(0, maxLength - ext.length - 4) + "...";
    return truncated + "." + ext;
  }
}
// Initialize the app when DOM is loaded
let facebookDownloader;
document.addEventListener("DOMContentLoaded", () => {
  facebookDownloader = new FacebookDownloader();
  window.facebookDownloader = facebookDownloader; // Make it globally accessible
});
