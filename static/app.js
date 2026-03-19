(() => {
  const fileInput = document.getElementById("fileInput");
  const uploadBtn = document.getElementById("uploadBtn");
  const startBtn = document.getElementById("startBtn");
  const statusBadge = document.getElementById("statusBadge");
  const statusText = document.getElementById("statusText");
  const metaArea = document.getElementById("metaArea");
  const errorArea = document.getElementById("errorArea");
  // const uploadResult = document.getElementById("uploadResult");
  const stdoutArea = document.getElementById("stdoutArea");
  const stderrArea = document.getElementById("stderrArea");
  const taskIdLabel = document.getElementById("taskIdLabel");
  const downloadBtn = document.getElementById("downloadBtn");

  let currentTaskId = null;
  let pollTimer = null;
  let isUploading = false;
  let isRunning = false;

  function setBadge(status) {
    const s = (status || "idle").toLowerCase();
    statusBadge.textContent = s;
    statusBadge.className = `badge badge-${s}`;
  }

  function setStatus(text, status = null) {
    statusText.textContent = text || "";
    if (status) setBadge(status);
  }

  function clearLogs() {
    stdoutArea.textContent = "";
    stderrArea.textContent = "";
  }

  function setError(message) {
    if (message) {
      errorArea.hidden = false;
      errorArea.textContent = message;
    } else {
      errorArea.hidden = true;
      errorArea.textContent = "";
    }
  }

  function setMeta(task) {
    const fields = [
      ["task_id", task?.task_id],
      ["filename", task?.filename],
      ["file_path", task?.file_path],
      ["status", task?.status],
      ["created_at", task?.created_at],
      ["started_at", task?.started_at],
      ["finished_at", task?.finished_at],
      ["return_code", task?.return_code],
      ["error_message", task?.error_message],
       ["output_filename", task?.output_filename],
       ["download_ready", task?.download_ready],
       ["result_message", task?.result_message],
    ];

    metaArea.innerHTML = fields
      .map(([k, v]) => {
        const value =
          v === null || v === undefined || v === "" ? "<span class=\"muted\">—</span>" : escapeHtml(String(v));
        return `<div class="kvRow"><div class="kvKey">${escapeHtml(k)}</div><div class="kvVal">${value}</div></div>`;
      })
      .join("");
  }

  // function setUploadResult(data) {
  //   const fields = [
  //     ["task_id", data?.task_id],
  //     ["filename", data?.filename],
  //     ["file_path", data?.file_path],
  //     ["status", data?.status],
  //   ];

  //   uploadResult.innerHTML = fields
  //     .map(([k, v]) => {
  //       const value =
  //         v === null || v === undefined || v === "" ? "<span class=\"muted\">—</span>" : escapeHtml(String(v));
  //       return `<div class="kvRow"><div class="kvKey">${escapeHtml(k)}</div><div class="kvVal">${value}</div></div>`;
  //     })
  //     .join("");
  // }

  function setButtons() {
    uploadBtn.disabled = isUploading || isRunning;
    fileInput.disabled = isUploading || isRunning;
    startBtn.disabled = isUploading || isRunning || !currentTaskId;
    if (downloadBtn) {
      downloadBtn.disabled = isUploading || isRunning || !currentTaskId;
    }
  }

  function stopPolling() {
    if (pollTimer) {
      clearInterval(pollTimer);
      pollTimer = null;
    }
  }

  function escapeHtml(s) {
    return s
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  async function fetchJson(url, options) {
    const res = await fetch(url, options);
    const contentType = res.headers.get("content-type") || "";
    let data = null;
    if (contentType.includes("application/json")) {
      data = await res.json();
    } else {
      const text = await res.text();
      data = { success: false, error: text || `HTTP ${res.status}` };
    }

    if (!res.ok) {
      const errMsg = (data && data.error) ? data.error : `HTTP ${res.status}`;
      throw new Error(errMsg);
    }
    return data;
  }

  async function pollStatus(taskId) {
    try {
      const data = await fetchJson(`/status/${encodeURIComponent(taskId)}`, { method: "GET" });
      if (!data || data.success !== true) {
        setError(data?.error || "Unknown error");
        return;
      }
      const task = data.task;
      setError(null);
      setBadge(task?.status || "idle");
      setStatus(task?.status ? `Status: ${task.status}` : "Status: unknown", task?.status);
      setMeta(task);
      stdoutArea.textContent = task?.stdout || "";
      stderrArea.textContent = task?.stderr || "";

      const st = (task?.status || "").toLowerCase();
      const canDownload = st === "success" && task?.download_ready === true;
      if (downloadBtn) {
        downloadBtn.hidden = !canDownload;
      }
      if (st === "success" || st === "failed") {
        stopPolling();
        isRunning = false;
        setButtons();
      }
    } catch (e) {
      setError(`Status poll failed: ${e.message || String(e)}`);
    }
  }

  uploadBtn.addEventListener("click", async () => {
    if (isUploading || isRunning) return; // 防止重复点击
    // 停止轮询，清除状态
    stopPolling();
    setError(null);
    clearLogs();

    const file = fileInput.files && fileInput.files[0];
    if (!file) {
      setError("Please choose a video file first.");
      return;
    }

    // 切换到上传状态
    isUploading = true;
    currentTaskId = null;
    taskIdLabel.textContent = "";
    // uploadResult.innerHTML = "";
    if (downloadBtn) {
      downloadBtn.hidden = true;
    }
    setButtons();
    setBadge("uploaded");
    setStatus("Uploading...", "uploaded");

    try {
      // FromData打包上传到服务器
      const form = new FormData();
      form.append("video", file, file.name);
      // 上传到服务器
      const data = await fetchJson("/upload", { method: "POST", body: form });
      if (!data || data.success !== true) {
        throw new Error(data?.error || "Upload failed");
      }
      // 设置当前任务id
      currentTaskId = data.task_id;
      // 显示id
      taskIdLabel.textContent = currentTaskId ? `task: ${currentTaskId}` : "";
      // setUploadResult(data);
      setError(null);
      setBadge("uploaded");
      setStatus("Upload successful.", "uploaded");
      // 在statustext部分显示相关信息
      setMeta({
        task_id: data.task_id,
        filename: data.filename,
        file_path: data.file_path,
        status: data.status,
        created_at: null,
        started_at: null,
        finished_at: null,
        return_code: null,
        error_message: null,
      });
    } catch (e) {
      setBadge("failed");
      setStatus("Upload failed.", "failed");
      setError(e.message || String(e));
    } finally {
      isUploading = false;
      setButtons();
    }
  });

  startBtn.addEventListener("click", async () => {
    // 防止重复点击
    if (isUploading || isRunning) return;
    // 检测是否存在task_id
    if (!currentTaskId) {
      setError("No task_id yet. Upload a file first.");
      return;
    }
    // 清除已有信息，停止轮询，切换到运行状态
    setError(null);
    clearLogs();
    stopPolling();

    isRunning = true;
    setButtons();
    // 设置为排队状态
    setBadge("queued");
    setStatus("Queued...", "queued");

    try {
      const data = await fetchJson(`/run/${encodeURIComponent(currentTaskId)}`, { method: "POST" });
      if (!data || data.success !== true) {
        throw new Error(data?.error || "Run failed");
      }
      // 设置状态为排队中或正在跑
      setBadge(data.status || "queued");
      setStatus(`Run started (${data.status || "queued"}).`, data.status || "queued");

      // 立即轮询一次状态
      await pollStatus(currentTaskId);
      // 每隔2秒轮询一次状态
      pollTimer = setInterval(() => pollStatus(currentTaskId), 2000);
    } catch (e) {
      isRunning = false;
      setButtons();
      setBadge("failed");
      setStatus("Failed to start processing.", "failed");
      setError(e.message || String(e));
    }
  });

  if (downloadBtn) {
    downloadBtn.addEventListener("click", () => {
      if (!currentTaskId) return;
      window.location.href = `/download/${encodeURIComponent(currentTaskId)}`;
    });
  }

  fileInput.addEventListener("change", () => {
    stopPolling();
    setError(null);
    clearLogs();
    currentTaskId = null;
    taskIdLabel.textContent = "";
    // uploadResult.innerHTML = "";
    setMeta(null);
    setBadge("idle");
    setStatus("Idle", "idle");
    isUploading = false;
    isRunning = false;
    if (downloadBtn) {
      downloadBtn.hidden = true;
    }
    setButtons();
  });

  // Initial UI state
  setBadge("idle");
  setStatus("Idle", "idle");
  setMeta(null);
  setButtons();
})();

