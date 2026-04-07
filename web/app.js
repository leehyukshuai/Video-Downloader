const state = {
  app: null,
  formatData: null,
  currentJobId: null,
  currentJob: null,
  pollTimer: null,
  supportedSites: null,
  backendStatus: "unknown",
  eventSource: null,
  siteModalLoaded: false,
};

const $ = (id) => document.getElementById(id);
const elements = {
  inputPanel: $("inputPanel"),
  backendStatusBox: $("backendStatusBox"),
  backendStatusText: $("backendStatusText"),
  openSupportedSitesButton: $("openSupportedSitesButton"),
  closeSupportedSitesButton: $("closeSupportedSitesButton"),
  authAssist: $("authAssist"),
  authAssistText: $("authAssistText"),
  chooseCookiesButton: $("chooseCookiesButton"),
  openCookieTutorialButton: $("openCookieTutorialButton"),
  clearCookiesButton: $("clearCookiesButton"),
  cookiesDisplay: $("cookiesDisplay"),
  siteModal: $("siteModal"),
  cookieTutorialModal: $("cookieTutorialModal"),
  closeCookieTutorialButton: $("closeCookieTutorialButton"),
  urlInput: $("urlInput"),
  inspectButton: $("inspectButton"),
  supportedSiteSearch: $("supportedSiteSearch"),
  supportedSiteMeta: $("supportedSiteMeta"),
  supportedSiteResults: $("supportedSiteResults"),
  supportedSiteSource: $("supportedSiteSource"),
  commonSiteChips: $("commonSiteChips"),
  message: $("message"),
  overviewPanel: $("overviewPanel"),
  thumbnail: $("thumbnail"),
  videoTitle: $("videoTitle"),
  videoMetaText: $("videoMetaText"),
  videoDescription: $("videoDescription"),
  warnings: $("warnings"),
  mergeFormat: $("mergeFormat"),
  mergeFormatShell: $("mergeFormatShell"),
  mergeFormatButton: $("mergeFormatButton"),
  mergeFormatMenu: $("mergeFormatMenu"),
  mergeFormatHint: $("mergeFormatHint"),
  outputDirDisplay: $("outputDirDisplay"),
  chooseOutputDirButton: $("chooseOutputDirButton"),
  selectionSummary: $("selectionSummary"),
  videoCount: $("videoCount"),
  audioCount: $("audioCount"),
  videoFormatsTable: $("videoFormatsTable"),
  audioFormatsTable: $("audioFormatsTable"),
  downloadButton: $("downloadButton"),
  progressPanel: $("progressPanel"),
  jobTitle: $("jobTitle"),
  jobStatus: $("jobStatus"),
  progressBar: $("progressBar"),
  progressPercent: $("progressPercent"),
  downloadedText: $("downloadedText"),
  speedText: $("speedText"),
  etaText: $("etaText"),
  logOutput: $("logOutput"),
  togglePauseButton: $("togglePauseButton"),
  cancelButton: $("cancelButton"),
  openFolderButton: $("openFolderButton"),
  toast: $("toast"),
};

function setMessage(text, type = "") {
  elements.message.textContent = text || "";
  elements.message.className = `message ${type}`.trim();
}

function isCookieRequiredError(text) {
  const value = String(text || "").toLowerCase();
  return [
    "cookies",
    "cookie",
    "登录",
    "登录态",
    "验证",
    "not a bot",
    "sign in",
    "age-restricted",
    "login required",
    "confirm you're not a bot",
    "confirm you’re not a bot",
    "cookies-from-browser",
  ].some((token) => value.includes(token));
}

function openCookieTutorialModal() {
  elements.cookieTutorialModal.classList.remove("hidden");
  elements.cookieTutorialModal.setAttribute("aria-hidden", "false");
  document.body.classList.add("modal-open");
}

function closeCookieTutorialModal() {
  elements.cookieTutorialModal.classList.add("hidden");
  elements.cookieTutorialModal.setAttribute("aria-hidden", "true");
  if (elements.siteModal.classList.contains("hidden")) {
    document.body.classList.remove("modal-open");
  }
}

function showCookieAssist(message = "", { autoOpen = false } = {}) {
  elements.authAssist.classList.remove("hidden");
  elements.authAssistText.textContent = message || "请选择 cookies.txt；如果不知道怎么获取，点“获取教程”。";
  if (autoOpen) openCookieTutorialModal();
}

function hideCookieAssist() {
  elements.authAssist.classList.add("hidden");
}

function showToast(text) {
  elements.toast.textContent = text;
  elements.toast.classList.remove("hidden");
  clearTimeout(showToast.timer);
  showToast.timer = setTimeout(() => elements.toast.classList.add("hidden"), 2400);
}

function escapeHtml(text) {
  return String(text ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function proxiedThumbnailUrl(url) {
  const value = String(url || "").trim();
  return value ? `/api/thumbnail?url=${encodeURIComponent(value)}` : "";
}

function setBackendStatus(status) {
  state.backendStatus = status;
  elements.backendStatusBox.className = `badge-box status-${status}`;
  const mapping = {
    running: "在线运行中",
    stopping: "正在退出…",
    offline: "连接已断开",
    unknown: "检测中…",
  };
  elements.backendStatusText.textContent = mapping[status] || mapping.unknown;
}

function closeMergeFormatMenu() {
  elements.mergeFormatShell?.classList.remove("open");
  elements.mergeFormatMenu?.classList.add("hidden");
  elements.mergeFormatButton?.setAttribute("aria-expanded", "false");
}

function syncMergeFormatControl() {
  const options = Array.from(elements.mergeFormat.options || []);
  const current = options.find((item) => item.value === elements.mergeFormat.value) || options[0] || null;
  elements.mergeFormatButton.textContent = current?.textContent || "请先选择想保留的视频和/或音频规格。";
  elements.mergeFormatButton.disabled = !!elements.mergeFormat.disabled || !options.length;
  elements.mergeFormatButton.classList.toggle("placeholder", !current);
  elements.mergeFormatMenu.innerHTML = options.map((item) => `
    <button
      type="button"
      class="select-option ${item.value === elements.mergeFormat.value ? "selected" : ""}"
      data-merge-format-value="${escapeHtml(item.value)}"
      role="option"
      aria-selected="${item.value === elements.mergeFormat.value ? "true" : "false"}"
    >${escapeHtml(item.textContent || item.value)}</button>
  `).join("");
  if (!options.length) closeMergeFormatMenu();
}

function openSiteModal() {
  elements.siteModal.classList.remove("hidden");
  elements.siteModal.setAttribute("aria-hidden", "false");
  document.body.classList.add("modal-open");
  if (!state.siteModalLoaded) {
    loadSupportedSites().catch((error) => {
      elements.supportedSiteMeta.textContent = error.message || "载入支持站点失败";
    });
    state.siteModalLoaded = true;
  }
  setTimeout(() => elements.supportedSiteSearch.focus(), 0);
}

function closeSiteModal() {
  elements.siteModal.classList.add("hidden");
  elements.siteModal.setAttribute("aria-hidden", "true");
  if (elements.cookieTutorialModal.classList.contains("hidden")) {
    document.body.classList.remove("modal-open");
  }
}

function renderCommonSiteChips(commonSites = []) {
  if (!commonSites.length) {
    elements.commonSiteChips.innerHTML = "";
    return;
  }
  elements.commonSiteChips.innerHTML = commonSites.map((item) => {
    const text = item.label || item.extractor || item.name || "";
    const keyword = String(item.extractor || item.label || item.name || "").split(":")[0];
    return `<button type="button" class="common-chip" data-site-keyword="${escapeHtml(keyword)}">${escapeHtml(text)}</button>`;
  }).join("");
}

async function fetchJSON(url, options) {
  try {
    const res = await fetch(url, options);
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || `请求失败: ${res.status}`);
    return data;
  } catch (error) {
    if (error instanceof TypeError) setBackendStatus("offline");
    throw error;
  }
}

function resetPageState() {
  state.formatData = null;
  state.currentJobId = null;
  state.currentJob = null;
  clearTimeout(state.pollTimer);
  elements.urlInput.value = "";
  elements.mergeFormat.innerHTML = "";
  elements.mergeFormat.disabled = true;
  elements.mergeFormatHint.textContent = "请先选择想保留的视频和/或音频规格。";
  syncMergeFormatControl();
  elements.inputPanel.classList.remove("hidden");
  elements.overviewPanel.classList.add("hidden");
  elements.progressPanel.classList.add("hidden");
  elements.message.textContent = "";
  elements.videoFormatsTable.innerHTML = "";
  elements.audioFormatsTable.innerHTML = "";
  elements.videoDescription.textContent = "";
  elements.warnings.innerHTML = "";
  setOutputDir("");
  setCookiesPath("");
  hideCookieAssist();
  closeCookieTutorialModal();
}

function getOutputDir() {
  return elements.outputDirDisplay.dataset.path || "";
}

function setOutputDir(path) {
  const value = String(path || "").trim();
  elements.outputDirDisplay.dataset.path = value;
  elements.outputDirDisplay.textContent = value || "未选择";
  elements.outputDirDisplay.title = value;
}

function getCookiesPath() {
  return elements.cookiesDisplay.dataset.path || "";
}

function setCookiesPath(path) {
  const value = String(path || "").trim();
  elements.cookiesDisplay.dataset.path = value;
  elements.cookiesDisplay.textContent = value || "未设置";
  elements.cookiesDisplay.title = value;
}

function renderWarnings(list = []) {
  elements.warnings.innerHTML = list.map((x) => `<div class="warning-item">${escapeHtml(x)}</div>`).join("");
}

function getSelected(name) {
  return document.querySelector(`input[name="${name}"]:checked`)?.value || "";
}

function getSelectedVideo() {
  return state.formatData?.video_formats?.find((x) => x.id === getSelected("videoFormat")) || null;
}

function getSelectedAudio() {
  return state.formatData?.audio_formats?.find((x) => x.id === getSelected("audioFormat")) || null;
}

function getKeepVideo() {
  return !!getSelected("videoFormat");
}

function getKeepAudio() {
  return !!getSelected("audioFormat");
}

function renderEmptyRow(message, columns) {
  return `<tr class="empty-row"><td colspan="${columns}">${escapeHtml(message)}</td></tr>`;
}

function normalizeExt(value) {
  return String(value || "").trim().toLowerCase();
}

function isMp4AudioExt(ext) {
  return ["m4a", "mp4", "m4b", "aac"].includes(ext);
}

function isWebmAudioExt(ext) {
  return ["webm", "weba", "opus", "ogg"].includes(ext);
}

function isMp4VideoExt(ext) {
  return ["mp4", "m4v"].includes(ext);
}

function isWebmVideoExt(ext) {
  return ["webm"].includes(ext);
}

function buildCombinedFormatOptions(video, audio) {
  const videoExt = normalizeExt(video?.ext);
  const audioExt = normalizeExt(audio?.ext);
  const options = [
    { value: "mp4", label: "MP4" },
    { value: "mkv", label: "MKV" },
    { value: "webm", label: "WebM" },
    { value: "mov", label: "MOV" },
  ];

  if (videoExt && audioExt && isMp4VideoExt(videoExt) && isMp4AudioExt(audioExt)) {
    options[0].label = "MP4（推荐）";
  } else if (videoExt && audioExt && isWebmVideoExt(videoExt) && isWebmAudioExt(audioExt)) {
    options[2].label = "WebM（推荐）";
  } else {
    options[1].label = "MKV（推荐）";
  }

  return options;
}

function defaultCombinedFormatOptions() {
  return [
    { value: "mp4", label: "MP4（兼容优先）" },
    { value: "mkv", label: "MKV（最稳妥）" },
    { value: "webm", label: "WebM" },
    { value: "mov", label: "MOV" },
  ];
}

function buildSingleFormatOptions(originalExt, kind) {
  const normalized = normalizeExt(originalExt);
  const base = kind === "audio"
    ? [normalized, "mp3", "m4a", "opus", "flac", "wav", "aac"]
    : [normalized, "mp4", "mkv", "webm", "mov"];
  return base
    .filter(Boolean)
    .filter((value, index, list) => list.indexOf(value) === index)
    .map((value) => ({
      value,
      label: value === normalized ? `${String(value).toUpperCase()}（原始格式）` : String(value).toUpperCase(),
    }));
}

function syncSelectedStyles() {
  document.querySelectorAll("[data-video-row]").forEach((row) => row.classList.remove("selected"));
  document.querySelectorAll("[data-audio-row]").forEach((row) => row.classList.remove("selected"));
  const video = getSelected("videoFormat");
  const audio = getSelected("audioFormat");
  if (video) document.querySelector(`[data-video-row="${CSS.escape(video)}"]`)?.classList.add("selected");
  if (audio) document.querySelector(`[data-audio-row="${CSS.escape(audio)}"]`)?.classList.add("selected");
}

function updateFormatOptions() {
  const keepVideo = getKeepVideo();
  const keepAudio = getKeepAudio();
  const video = getSelectedVideo();
  const audio = getSelectedAudio();

  let options = [];
  let hint = "请先选择想保留的视频和/或音频规格。";
  let disabled = true;

  if (keepVideo && keepAudio) {
    if (video && audio) {
      options = buildCombinedFormatOptions(video, audio);
      hint = "同时保留视频和音频时，可选择最终输出格式。";
    } else {
      options = defaultCombinedFormatOptions();
      hint = "请继续选择完整的视频和音频规格。";
    }
    disabled = !options.length;
  } else if (keepVideo) {
    if (video?.ext) {
      options = buildSingleFormatOptions(video.ext, "video");
      hint = "仅保留视频时，可以保留原始格式，也可以转换为其他视频格式。";
    } else {
      hint = "请先选择一个视频规格。";
    }
    disabled = !options.length;
  } else if (keepAudio) {
    if (audio?.ext) {
      options = buildSingleFormatOptions(audio.ext, "audio");
      hint = "仅保留音频时，可以保留原始格式，也可以转换为其他音频格式。";
    } else {
      hint = "请先选择一个音频规格。";
    }
    disabled = !options.length;
  }

  const current = elements.mergeFormat.value;
  elements.mergeFormat.innerHTML = options.map((item) => `<option value="${escapeHtml(item.value)}">${escapeHtml(item.label)}</option>`).join("");
  if (options.some((item) => item.value === current)) {
    elements.mergeFormat.value = current;
  } else if (options[0]) {
    elements.mergeFormat.value = options[0].value;
  }
  elements.mergeFormat.disabled = disabled || !options.length;
  elements.mergeFormatHint.textContent = hint;
  syncMergeFormatControl();
}

function updateSelectionSummary() {
  const keepVideo = getKeepVideo();
  const keepAudio = getKeepAudio();
  const v = keepVideo ? getSelectedVideo() : null;
  const a = keepAudio ? getSelectedAudio() : null;
  updateFormatOptions();

  if (!keepVideo && !keepAudio) {
    elements.selectionSummary.textContent = "请先选择视频或音频规格";
    elements.downloadButton.disabled = true;
    return;
  }

  if (keepVideo && !v) {
    elements.selectionSummary.textContent = "请先选择一个视频规格";
    elements.downloadButton.disabled = true;
    return;
  }
  if (keepAudio && !a) {
    elements.selectionSummary.textContent = "请先选择一个音频规格";
    elements.downloadButton.disabled = true;
    return;
  }

  const parts = [];
  if (keepVideo && v) parts.push(`🎞️ 视频：${v.resolution} / ${v.dynamic_range || "SDR"} / ${v.codec}`);
  if (keepAudio && a) parts.push(`🔊 音频：${a.codec} / ${a.abr || "-"} kbps / ${a.channels || "-"} 声道`);
  elements.selectionSummary.textContent = parts.join(" ｜ ");
  elements.downloadButton.disabled = false;
}

function renderTables() {
  const videos = state.formatData?.video_formats || [];
  const audios = state.formatData?.audio_formats || [];
  const keepVideo = getKeepVideo();
  const keepAudio = getKeepAudio();
  elements.videoCount.textContent = `${videos.length} 项`;
  elements.audioCount.textContent = `${audios.length} 项`;

  const currentVideo = getSelected("videoFormat");
  const currentAudio = getSelected("audioFormat");

  const videoRows = videos.map((fmt) => `
    <tr class="${currentVideo === fmt.id ? "selected" : ""}" data-video-row="${escapeHtml(fmt.id)}">
      <td><input type="radio" name="videoFormat" value="${escapeHtml(fmt.id)}" ${currentVideo === fmt.id ? "checked" : ""}></td>
      <td>${escapeHtml(fmt.id)}</td>
      <td>${escapeHtml(fmt.resolution)}</td>
      <td>${fmt.fps ?? "-"}</td>
      <td>${escapeHtml(fmt.dynamic_range || "-")}</td>
      <td>${escapeHtml(fmt.ext || "-")}</td>
      <td>${escapeHtml(fmt.codec || "-")}</td>
      <td>${escapeHtml(fmt.filesize_text || "未知")}</td>
      <td>${escapeHtml(fmt.note || "-")}</td>
    </tr>`);

  elements.videoFormatsTable.innerHTML = videoRows.join("") || renderEmptyRow("暂无可用视频规格", 9);

  const audioRows = audios.map((fmt) => `
    <tr class="${currentAudio === fmt.id ? "selected" : ""}" data-audio-row="${escapeHtml(fmt.id)}">
      <td><input type="radio" name="audioFormat" value="${escapeHtml(fmt.id)}" ${currentAudio === fmt.id ? "checked" : ""}></td>
      <td>${escapeHtml(fmt.id)}</td>
      <td>${escapeHtml(fmt.ext || "-")}</td>
      <td>${escapeHtml(fmt.codec || "-")}</td>
      <td>${fmt.abr ? `${fmt.abr} kbps` : "-"}</td>
      <td>${fmt.channels ?? "-"}</td>
      <td>${escapeHtml(fmt.filesize_text || "未知")}</td>
      <td>${escapeHtml(fmt.note || "-")}</td>
    </tr>`);

  elements.audioFormatsTable.innerHTML = audioRows.join("") || renderEmptyRow("暂无可用音频规格", 8);
  syncSelectedStyles();
  updateSelectionSummary();
}

function renderOverview(data) {
  state.formatData = data;
  elements.inputPanel.classList.remove("hidden");
  elements.overviewPanel.classList.remove("hidden");
  elements.thumbnail.src = proxiedThumbnailUrl(data.thumbnail);
  elements.videoTitle.textContent = data.title || "未知标题";
  elements.videoMetaText.textContent = `👤 ${data.uploader || "未知"} · ⏱️ ${data.duration_text || "未知"} · 🆔 ${data.id || "-"}`;
  elements.videoDescription.textContent = data.description || "暂无简介";
  renderWarnings(data.warnings || []);
  renderTables();
}

function renderJob(job) {
  state.currentJob = job;
  elements.progressPanel.classList.remove("hidden");
  elements.jobTitle.textContent = job.title || "当前任务";
  elements.jobStatus.textContent = job.stage_text || job.status_label || job.status || "-";
  elements.progressBar.style.width = `${Math.max(0, Math.min(Number(job.progress_percent || 0), 100))}%`;
  elements.progressPercent.textContent = `${Number(job.progress_percent || 0).toFixed(1)}%`;
  elements.downloadedText.textContent = `${job.downloaded_text || "0 B"} / ${job.total_text || "未知"}`;
  elements.speedText.textContent = job.speed_text || "-";
  elements.etaText.textContent = job.eta_text || "-";
  elements.logOutput.textContent = (job.logs || []).join("\n");
  elements.togglePauseButton.disabled = !job.can_pause && !job.can_resume;
  elements.togglePauseButton.textContent = job.can_resume ? "▶️ 继续" : "⏸️ 暂停";
  elements.cancelButton.disabled = !job.can_cancel;
  elements.openFolderButton.disabled = !job.final_path;
}

function renderSupportedSites(payload, query = "") {
  if (payload?.source_url) elements.supportedSiteSource.href = payload.source_url;
  renderCommonSiteChips(payload?.common_sites || []);
  const items = payload?.items || [];
  const isQuery = !!query.trim();
  const total = payload?.count || 0;
  elements.supportedSiteMeta.textContent = isQuery
    ? `找到 ${items.length} 个相关结果（列表共 ${total} 项）`
    : `可搜索的站点列表共 ${total} 项，可点击常见站点或直接搜索。`;

  if (!items.length) {
    elements.supportedSiteResults.innerHTML = `<div class="site-chip empty">没有找到匹配项</div>`;
    return;
  }

  elements.supportedSiteResults.innerHTML = items.map((item) => {
    const title = item.label || item.name || item.extractor || "-";
    const extra = item.extractor && item.extractor !== title ? `<span class="site-sub">${escapeHtml(item.extractor)}</span>` : "";
    const desc = item.description ? `<span class="site-desc">${escapeHtml(item.description)}</span>` : "";
    const broken = item.broken ? `<span class="site-flag">可能失效</span>` : "";
    return `<div class="site-chip">${broken}<strong>${escapeHtml(title)}</strong>${extra}${desc}</div>`;
  }).join("");
}

async function loadSupportedSites(query = "") {
  if (!state.supportedSites) {
    const res = await fetch("/static/supportedsites.json");
    const payload = await res.json();
    state.supportedSites = payload;
  }
  const payload = state.supportedSites;
  const q = query.trim().toLowerCase();
  let items = payload.items || [];
  if (q) {
    items = items.filter((item) => (item.search || "").includes(q));
  } else {
    items = payload.common_sites || items;
  }
  renderSupportedSites({ ...payload, items }, query);
}

function connectBackendEvents() {
  state.eventSource?.close();
  const events = new EventSource("/api/events");
  state.eventSource = events;
  events.addEventListener("status", (event) => {
    try {
      const data = JSON.parse(event.data);
      setBackendStatus(data.status || "running");
    } catch {
      setBackendStatus("running");
    }
  });
  events.onerror = () => setBackendStatus("offline");
}

async function pollJob() {
  if (!state.currentJobId) return;
  try {
    const job = await fetchJSON(`/api/downloads/${state.currentJobId}`);
    renderJob(job);
    if (job.status === "error") {
      const errorText = job.error || job.logs?.[job.logs.length - 1] || "下载失败。";
      setMessage(errorText, "error");
      if (isCookieRequiredError(errorText)) {
        elements.inputPanel.classList.remove("hidden");
        showCookieAssist("该链接可能需要登录信息。请导入 cookies.txt 后重新解析或重新下载。");
      }
    }
    if (!["completed", "error", "cancelled"].includes(job.status)) {
      state.pollTimer = setTimeout(pollJob, 1000);
    }
  } catch (error) {
    setMessage(error.message, "error");
  }
}

function getPauseAction() {
  if (!state.currentJob) return null;
  if (state.currentJob.can_resume) return "resume";
  if (state.currentJob.can_pause) return "pause";
  return null;
}

async function triggerAction(action) {
  if (!state.currentJobId) return;
  const job = await fetchJSON(`/api/downloads/${state.currentJobId}/action`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action }),
  });
  renderJob(job);
  showToast(`已${action === "pause" ? "暂停" : action === "resume" ? "继续" : "终止"}任务`);
  if (!["completed", "error", "cancelled"].includes(job.status)) {
    clearTimeout(state.pollTimer);
    state.pollTimer = setTimeout(pollJob, 1000);
  }
}

async function inspectFormats() {
  const url = elements.urlInput.value.trim();
  if (!url) return setMessage("请先输入链接。", "error");
  setMessage("正在解析规格，请稍候…", "info");
  hideCookieAssist();
  elements.inspectButton.disabled = true;
  try {
    const data = await fetchJSON("/api/formats", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url, cookies_path: getCookiesPath() }),
    });
    renderOverview(data);
    setMessage("解析完成，请先选择要保留的视频和/或音频规格。", "success");
    showToast("解析完成");
  } catch (error) {
    setMessage(error.message, "error");
    if (isCookieRequiredError(error.message)) {
      showCookieAssist("该页面可能需要登录信息。请选择 cookies.txt；如果不知道怎么获取，可以打开教程。");
    }
  } finally {
    elements.inspectButton.disabled = false;
  }
}

async function startDownload() {
  if (!state.formatData) return setMessage("请先解析规格。", "error");
  const keepVideo = getKeepVideo();
  const keepAudio = getKeepAudio();
  const videoId = keepVideo ? getSelected("videoFormat") : "";
  const audioId = keepAudio ? getSelected("audioFormat") : "";
  if (keepVideo && !videoId) return setMessage("请先选择一个视频规格。", "error");
  if (keepAudio && !audioId) return setMessage("请先选择一个音频规格。", "error");
  if (!elements.mergeFormat.value) return setMessage("请先确认输出格式。", "error");
  const payload = {
    url: elements.urlInput.value.trim(),
    title: state.formatData.title,
    thumbnail: state.formatData.thumbnail,
    output_dir: getOutputDir() || state.app?.downloads_dir || "",
    cookies_path: getCookiesPath(),
    cookie_source: state.formatData.cookie_source || {},
    keep_video: keepVideo,
    keep_audio: keepAudio,
    audio_only: !keepVideo && !!audioId,
    merge_format: elements.mergeFormat.value,
    video_format_id: videoId,
    audio_format_id: audioId,
    video_source_ext: keepVideo && getSelectedVideo() ? normalizeExt(getSelectedVideo().ext) : "",
    audio_source_ext: keepAudio && getSelectedAudio() ? normalizeExt(getSelectedAudio().ext) : "",
  };
  try {
    const data = await fetchJSON("/api/downloads", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    state.currentJobId = data.job_id;
    elements.inputPanel.classList.add("hidden");
    elements.overviewPanel.classList.add("hidden");
    elements.progressPanel.classList.remove("hidden");
    setMessage("下载任务已启动。", "success");
    showToast("开始下载");
    pollJob();
  } catch (error) {
    setMessage(error.message, "error");
  }
}

async function openTarget() {
  if (!state.currentJob?.final_path) return;
  try {
    await fetchJSON("/api/open-target", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path: state.currentJob.final_path }),
    });
  } catch (error) {
    showToast(error.message);
  }
}

async function chooseOutputDir() {
  try {
    const data = await fetchJSON("/api/pick-folder", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ current: getOutputDir() || state.app?.downloads_dir || "" }),
    });
    if (data.path) {
      setOutputDir(data.path);
      updateSelectionSummary();
    }
  } catch (error) {
    showToast(error.message);
  }
}

async function chooseCookiesFile() {
  try {
    const data = await fetchJSON("/api/pick-cookie", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ current: getCookiesPath() }),
    });
    if (typeof data.path === "string") {
      setCookiesPath(data.path);
    }
  } catch (error) {
    showToast(error.message);
  }
}

async function bootstrap() {
  resetPageState();
  setBackendStatus("unknown");
  const data = await fetchJSON("/api/app-state");
  state.app = data.app;
  setOutputDir(data.app.downloads_dir || "");
  setBackendStatus("running");
  connectBackendEvents();
}

elements.inspectButton.addEventListener("click", inspectFormats);
elements.downloadButton.addEventListener("click", startDownload);
elements.mergeFormat.addEventListener("change", updateSelectionSummary);
elements.mergeFormatButton.addEventListener("click", () => {
  if (elements.mergeFormatButton.disabled) return;
  const isOpen = elements.mergeFormatShell.classList.contains("open");
  closeMergeFormatMenu();
  if (!isOpen) {
    elements.mergeFormatShell.classList.add("open");
    elements.mergeFormatMenu.classList.remove("hidden");
    elements.mergeFormatButton.setAttribute("aria-expanded", "true");
  }
});
elements.chooseOutputDirButton.addEventListener("click", chooseOutputDir);
elements.chooseCookiesButton.addEventListener("click", chooseCookiesFile);
elements.openCookieTutorialButton.addEventListener("click", openCookieTutorialModal);
elements.closeCookieTutorialButton.addEventListener("click", closeCookieTutorialModal);
elements.clearCookiesButton.addEventListener("click", () => setCookiesPath(""));
elements.openSupportedSitesButton.addEventListener("click", openSiteModal);
elements.closeSupportedSitesButton.addEventListener("click", closeSiteModal);
elements.supportedSiteSearch.addEventListener("input", () => {
  clearTimeout(elements.supportedSiteSearch._timer);
  elements.supportedSiteSearch._timer = setTimeout(() => {
    loadSupportedSites(elements.supportedSiteSearch.value.trim()).catch((error) => {
      elements.supportedSiteMeta.textContent = error.message || "载入支持站点失败";
    });
  }, 180);
});
elements.togglePauseButton.addEventListener("click", () => {
  const action = getPauseAction();
  if (action) triggerAction(action);
});
elements.cancelButton.addEventListener("click", () => triggerAction("cancel"));
elements.openFolderButton.addEventListener("click", openTarget);
elements.urlInput.addEventListener("keydown", (e) => { if (e.key === "Enter") inspectFormats(); });

document.addEventListener("change", (e) => {
  if (e.target.matches('input[name="videoFormat"], input[name="audioFormat"]')) {
    syncSelectedStyles();
    updateSelectionSummary();
  }
});

document.addEventListener("pointerdown", (e) => {
  const radio = e.target.closest('input[type="radio"][name="videoFormat"], input[type="radio"][name="audioFormat"]');
  if (radio) {
    radio.dataset.wasChecked = radio.checked ? "true" : "false";
  }
});

document.addEventListener("click", (e) => {
  const radio = e.target.closest('input[type="radio"][name="videoFormat"], input[type="radio"][name="audioFormat"]');
  if (radio && radio.dataset.wasChecked === "true") {
    radio.checked = false;
    delete radio.dataset.wasChecked;
    syncSelectedStyles();
    updateSelectionSummary();
    return;
  }
  const vr = e.target.closest("[data-video-row]");
  if (vr && !e.target.matches('input[name="videoFormat"]')) {
    const input = vr.querySelector('input[name="videoFormat"]');
    if (input?.checked) {
      input.checked = false;
      syncSelectedStyles();
      updateSelectionSummary();
      return;
    }
    input?.click();
  }
  const ar = e.target.closest("[data-audio-row]");
  if (ar && !e.target.matches('input[name="audioFormat"]')) {
    const input = ar.querySelector('input[name="audioFormat"]');
    if (input?.checked) {
      input.checked = false;
      syncSelectedStyles();
      updateSelectionSummary();
      return;
    }
    input?.click();
  }
  const chip = e.target.closest("[data-site-keyword]");
  if (chip) {
    const keyword = chip.getAttribute("data-site-keyword") || "";
    elements.supportedSiteSearch.value = keyword;
    loadSupportedSites(keyword).catch((error) => {
      elements.supportedSiteMeta.textContent = error.message || "载入支持站点失败";
    });
  }
  const mergeOption = e.target.closest("[data-merge-format-value]");
  if (mergeOption) {
    elements.mergeFormat.value = mergeOption.getAttribute("data-merge-format-value") || "";
    syncMergeFormatControl();
    closeMergeFormatMenu();
    updateSelectionSummary();
    return;
  }
  if (!e.target.closest("#mergeFormatShell")) closeMergeFormatMenu();
  if (e.target.closest("[data-close-modal='true']")) closeSiteModal();
  if (e.target.closest("[data-close-cookie-modal='true']")) closeCookieTutorialModal();
});

document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") closeMergeFormatMenu();
  if (e.key === "Escape" && !elements.siteModal.classList.contains("hidden")) {
    closeSiteModal();
  }
  if (e.key === "Escape" && !elements.cookieTutorialModal.classList.contains("hidden")) {
    closeCookieTutorialModal();
  }
});

window.addEventListener("beforeunload", () => state.eventSource?.close());

bootstrap().catch((error) => setMessage(error.message || "初始化失败", "error"));
