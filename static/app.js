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
  const usernameInput = document.getElementById("usernameInput");
  const taskHistorySelect = document.getElementById("taskHistorySelect");
  const gpuRefreshBtn = document.getElementById("gpuRefreshBtn");
  const gpuSelect = document.getElementById("gpuSelect");
  const gpuStatusArea = document.getElementById("gpuStatusArea");

  const LS_USERNAME_KEY = "webRunnerUsername";
  const LS_LAST_TASK_KEY = "webRunnerLastSelectedTaskId";
  const LS_GPU_KEY = "webRunnerPreferredGpu";

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
      ["gpu_id", task?.gpu_id],
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

  function getSelectedGpuId() {
    if (!gpuSelect || !gpuSelect.value) return "0";
    return gpuSelect.value;
  }

  function renderGpuStatus(data) {
    if (!gpuStatusArea) return;
    if (!data || data.success !== true) {
      gpuStatusArea.innerHTML =
        `<div class="kvRow"><div class="kvKey">status</div><div class="kvVal"><span class="muted">Failed to load GPU info</span></div></div>`;
      return;
    }
    if (!data.available) {
      const msg = data.message || "No NVIDIA GPU or nvidia-smi unavailable.";
      gpuStatusArea.innerHTML =
        `<div class="kvRow"><div class="kvKey">status</div><div class="kvVal">${escapeHtml(msg)}</div></div>`;
      return;
    }
    const rows = (data.gpus || []).map((g) => {
      const util = g.utilization_percent != null ? `${g.utilization_percent}%` : "—";
      const mem =
        g.memory_used_mb != null && g.memory_total_mb != null
          ? `${g.memory_used_mb} / ${g.memory_total_mb} MiB`
          : "—";
      const procs = g.process_count != null ? String(g.process_count) : "—";
      const line = `util ${util} · mem ${mem} · processes ${procs}`;
      return `<div class="kvRow"><div class="kvKey">gpu ${escapeHtml(String(g.index))}</div><div class="kvVal">${escapeHtml(line)}</div></div>`;
    });
    gpuStatusArea.innerHTML = rows.join("");
  }

  function populateGpuSelect(data) {
    if (!gpuSelect) return;
    const prev = gpuSelect.value;
    gpuSelect.innerHTML = "";
    const gpus = data && data.gpus && data.gpus.length ? data.gpus : null;
    if (gpus) {
      for (const g of gpus) {
        const opt = document.createElement("option");
        opt.value = String(g.index);
        const util = g.utilization_percent != null ? `${g.utilization_percent}%` : "?";
        const mem =
          g.memory_used_mb != null && g.memory_total_mb != null
            ? `${g.memory_used_mb}/${g.memory_total_mb} MiB`
            : "?/? MiB";
        const procs = g.process_count != null ? String(g.process_count) : "?";
        opt.textContent = `GPU ${g.index} — ${util} — ${mem} — procs ${procs}`;
        gpuSelect.appendChild(opt);
      }
    } else {
      const opt = document.createElement("option");
      opt.value = "0";
      opt.textContent = "GPU 0 (default)";
      gpuSelect.appendChild(opt);
    }
    const def = data && data.default_gpu != null ? String(data.default_gpu) : "0";
    const saved = localStorage.getItem(LS_GPU_KEY);
    const valid = saved && [...gpuSelect.options].some((o) => o.value === saved);
    gpuSelect.value = valid ? saved : def;
    if (prev && [...gpuSelect.options].some((o) => o.value === prev)) {
      gpuSelect.value = prev;
    }
  }

  async function loadGpuStatus() {
    if (!gpuSelect || !gpuStatusArea) return;
    try {
      const data = await fetchJson("/gpu/status", { method: "GET" });
      renderGpuStatus(data);
      populateGpuSelect(data);
    } catch (e) {
      gpuStatusArea.innerHTML =
        `<div class="kvRow"><div class="kvKey">status</div><div class="kvVal">${escapeHtml(e.message || String(e))}</div></div>`;
      populateGpuSelect({ default_gpu: 0, gpus: [] });
    }
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
        return null;
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
      return st;
    } catch (e) {
      setError(`Status poll failed: ${e.message || String(e)}`);
      return null;
    }
  }

  function renderTaskHistory(tasks) {
    if (!taskHistorySelect) return;
    taskHistorySelect.innerHTML = "";
    if (!tasks || tasks.length === 0) {
      const opt = document.createElement("option");
      opt.value = "";
      opt.textContent = "No tasks";
      taskHistorySelect.appendChild(opt);
      return;
    }
    for (const t of tasks) {
      const opt = document.createElement("option");
      opt.value = t.task_id;
      const filename = t.filename || t.task_id;
      const status = t.status || "unknown";
      opt.textContent = `${filename} [${status}]`;
      taskHistorySelect.appendChild(opt);
    }
  }

  async function loadTasksForUsername(username) {
    const uname = (username || "").trim() || "default";
    usernameInput && (usernameInput.value = uname);

    const data = await fetchJson(`/tasks?username=${encodeURIComponent(uname)}`, { method: "GET" });
    if (!data || data.success !== true) {
      setError(data?.error || "Failed to load task list");
      return [];
    }
    setError(null);
    return data.tasks || [];
  }

  async function showSelectedTask(taskId, { pollIfRunning } = { pollIfRunning: true }) {
    stopPolling();
    isRunning = false;
    currentTaskId = taskId || null;
    if (taskIdLabel) {
      taskIdLabel.textContent = currentTaskId ? `task: ${currentTaskId}` : "";
    }
    setButtons();
    if (!currentTaskId) return;

    const st = await pollStatus(currentTaskId);
    if (pollIfRunning && (st === "queued" || st === "running")) {
      isRunning = true;
      setButtons();
      pollTimer = setInterval(() => pollStatus(currentTaskId), 2000);
    } else {
      isRunning = false;
      setButtons();
    }
  }

  async function restoreHistoryOnLoad() {
    const savedUsername = localStorage.getItem(LS_USERNAME_KEY) || "default";
    if (usernameInput) {
      usernameInput.value = savedUsername;
    }
    const savedLastTaskId = localStorage.getItem(LS_LAST_TASK_KEY) || "";

    let tasks = [];
    try {
      tasks = await loadTasksForUsername(savedUsername);
    } catch (e) {
      setError(e.message || String(e));
      return;
    }

    renderTaskHistory(tasks);
    if (!taskHistorySelect) return;
    const taskIds = new Set((tasks || []).map((t) => t.task_id));

    let selectedId = savedLastTaskId && taskIds.has(savedLastTaskId) ? savedLastTaskId : "";
    if (!selectedId && tasks && tasks.length > 0) {
      // Prefer an in-progress task, otherwise pick the first.
      const inProgress = tasks.find((t) => (t.status || "").toLowerCase() === "running" || (t.status || "").toLowerCase() === "queued");
      selectedId = inProgress ? inProgress.task_id : tasks[0].task_id;
    }

    taskHistorySelect.value = selectedId;
    if (selectedId) {
      localStorage.setItem(LS_LAST_TASK_KEY, selectedId);
      await showSelectedTask(selectedId, { pollIfRunning: true });
    } else {
      await showSelectedTask(null, { pollIfRunning: false });
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
      const uname =
        (usernameInput && usernameInput.value ? usernameInput.value : localStorage.getItem(LS_USERNAME_KEY)) ||
        "default";
      const gpuQ = `&gpu=${encodeURIComponent(getSelectedGpuId())}`;
      const data = await fetchJson(
        `/upload?username=${encodeURIComponent((uname || "default").trim())}${gpuQ}`,
        { method: "POST", body: form }
      );
      if (!data || data.success !== true) {
        throw new Error(data?.error || "Upload failed");
      }
      // 设置当前任务id
      currentTaskId = data.task_id;
      localStorage.setItem(LS_LAST_TASK_KEY, currentTaskId);
      // 显示id
      taskIdLabel.textContent = currentTaskId ? `task: ${currentTaskId}` : "";
      if (taskHistorySelect) {
        // If the task list hasn't been loaded yet for this session, we still keep the selection in localStorage.
        taskHistorySelect.value = currentTaskId;
      }
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
      const data = await fetchJson(
        `/run/${encodeURIComponent(currentTaskId)}?gpu=${encodeURIComponent(getSelectedGpuId())}`,
        { method: "POST" }
      );
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

  if (gpuRefreshBtn && gpuSelect) {
    gpuRefreshBtn.addEventListener("click", () => {
      loadGpuStatus();
    });
    gpuSelect.addEventListener("change", () => {
      localStorage.setItem(LS_GPU_KEY, gpuSelect.value);
    });
    loadGpuStatus();
  }

  if (usernameInput && taskHistorySelect) {
    restoreHistoryOnLoad();

    usernameInput.addEventListener("change", async () => {
      const uname = (usernameInput.value || "").trim() || "default";
      localStorage.setItem(LS_USERNAME_KEY, uname);
      stopPolling();
      await showSelectedTask(null, { pollIfRunning: false });
      const tasks = await loadTasksForUsername(uname);
      renderTaskHistory(tasks);
      // Best-effort: keep last selected task if it exists for this username.
      const savedLastTaskId = localStorage.getItem(LS_LAST_TASK_KEY) || "";
      if (savedLastTaskId && tasks.some((t) => t.task_id === savedLastTaskId)) {
        taskHistorySelect.value = savedLastTaskId;
        await showSelectedTask(savedLastTaskId, { pollIfRunning: true });
      }
    });

    taskHistorySelect.addEventListener("change", async () => {
      const tid = taskHistorySelect.value || "";
      if (!tid) {
        await showSelectedTask(null, { pollIfRunning: false });
        return;
      }
      localStorage.setItem(LS_LAST_TASK_KEY, tid);
      await showSelectedTask(tid, { pollIfRunning: true });
    });
  }
})();

