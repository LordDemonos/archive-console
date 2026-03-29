(function () {
  "use strict";

  function esc(s) {
    const d = document.createElement("div");
    d.textContent = s == null ? "" : String(s);
    return d.innerHTML;
  }

  /** Allowlisted file viewer: inline by default; download=1 forces attachment. */
  function reportsFileHref(rel, wantDownload) {
    var qs = "rel=" + encodeURIComponent(rel);
    if (wantDownload) {
      qs += "&download=1";
    }
    return "/reports/file?" + qs;
  }

  /** HTML reports: same-origin view with file:// links rewritten (see /reports/view). */
  function reportsViewHref(rel) {
    return "/reports/view?rel=" + encodeURIComponent(rel);
  }

  function reportsOpenHref(rel) {
    var l = (rel || "").toLowerCase();
    if (l.length >= 5 && l.slice(-5) === ".html") {
      return reportsViewHref(rel);
    }
    if (l.length >= 4 && l.slice(-4) === ".htm") {
      return reportsViewHref(rel);
    }
    return reportsFileHref(rel, false);
  }

  /**
   * Display-only styling for streamed lines. Safe if rules throw; never changes server or disk logs.
   * First matching rule wins (order matters).
   */
  function classifyLogLine(text) {
    try {
      var s = String(text);
      var low = s.toLowerCase();
      if (
        /traceback/i.test(s) ||
        /^\s*file "[^"]+", line \d+/i.test(s)
      ) {
        return "log-line log-line--err";
      }
      if (/\. was unexpected at this time/i.test(low)) {
        return "log-line log-line--err";
      }
      if (
        /^error\b/i.test(s) ||
        /^ERROR:\s+/i.test(s) ||
        /: error:/i.test(s) ||
        /\berror: /i.test(s)
      ) {
        return "log-line log-line--err";
      }
      if (/finished with errors/i.test(s)) {
        return "log-line log-line--err";
      }
      if (
        /\bexception\b|\bfatal\b|keyboardinterrupt|syntaxerror|eoferror/i.test(
          low
        )
      ) {
        return "log-line log-line--err";
      }
      if (
        /\[archive\][^\n]*success \(exit 0\)/i.test(s) ||
        /\[archive\][^\n]*:\s*SUCCESS\b/i.test(s) ||
        (/\[archive\]/i.test(s) &&
          /\bSUCCESS\b/i.test(s) &&
          /\bexit\s*0\b/i.test(s))
      ) {
        return "log-line log-line--ok";
      }
      if (/all scheduled steps finished/i.test(low)) {
        return "log-line log-line--ok";
      }
      if (
        /pip self-upgrade finished ok|yt-dlp pip update finished ok/i.test(s)
      ) {
        return "log-line log-line--ok";
      }
      if (/^warning\b|\bwarning:/i.test(s)) {
        return "log-line log-line--warn";
      }
      if (
        /dry.?run|ARCHIVE_DRY_RUN|--simulate|passing --simulate/i.test(s)
      ) {
        return "log-line log-line--warn";
      }
      if (/skipping pip|skipping yt-dlp update/i.test(low)) {
        return "log-line log-line--warn";
      }
      if (
        /\[archive\].*(pause|cookie|cookie-auth|operator|auth issue)/i.test(s)
      ) {
        return "log-line log-line--warn";
      }
      if (/^={3,}\s*$/.test(s)) {
        return "log-line log-line--meta";
      }
      if (
        /^(run logs written|run id:|open report:|report:|log directory:)/i.test(
          s.trim()
        )
      ) {
        return "log-line log-line--meta";
      }
      if (/latest .+ run log directory:|channel run pointer|playlist pointer|video list pointer/i.test(s)) {
        return "log-line log-line--meta";
      }
      if (/^\[console\]/.test(s)) {
        return "log-line log-line--info";
      }
      if (/\[archive\].*finished with errors/i.test(s)) {
        return "log-line log-line--err";
      }
      if (/^\[archive\]/.test(s)) {
        return "log-line log-line--info";
      }
      if (/requirement already satisfied|already satisfied/i.test(low)) {
        return "log-line log-line--muted";
      }
      if (/^\[debug\]/i.test(s)) {
        return "log-line log-line--muted";
      }
      if (
        /^\[download\]|^\[info\] destination:|^\[merge\]|^\[Merger\]|^\[Fixup\]/i.test(
          s
        )
      ) {
        return "log-line log-line--accent";
      }
      if (/\d+\.?\d*\s*%.*\b(of|eta)\b/i.test(low)) {
        return "log-line log-line--accent";
      }
      if (/\|\s*\d+\.?\d*%\s*\|/.test(s)) {
        return "log-line log-line--accent";
      }
      return "log-line";
    } catch (e) {
      return "log-line";
    }
  }

  function updateLastProgressFromLine(text) {
    try {
      if (!els.logProgressHint) {
        return;
      }
      var s = String(text);
      var m = /\[download\][^\n]*?(\d+\.?\d*)%/.exec(s);
      if (m) {
        els.logProgressHint.textContent =
          s.length > 160 ? s.slice(0, 157) + "…" : s;
        if (els.logProgressFill) {
          var pct = parseFloat(m[1]);
          if (!isFinite(pct)) {
            pct = 0;
          }
          pct = Math.min(100, Math.max(0, pct));
          els.logProgressFill.style.width = pct + "%";
        }
      }
    } catch (e) {
      /* ignore */
    }
  }

  function resetLogProgressHint() {
    if (els.logProgressHint) {
      els.logProgressHint.textContent = "—";
    }
    if (els.logProgressFill) {
      els.logProgressFill.style.width = "0%";
    }
  }

  function rebuildLogViewFromBuffer() {
    logLineCount = 0;
    els.logGutter.textContent = "";
    els.logBody.textContent = "";
    var hi = els.optLogHighlight && els.optLogHighlight.checked;
    for (var i = 0; i < logLinesBuffer.length; i++) {
      logLineCount += 1;
      els.logGutter.appendChild(
        document.createTextNode(String(logLineCount) + "\n")
      );
      var t = logLinesBuffer[i];
      if (!hi) {
        els.logBody.appendChild(document.createTextNode(t + "\n"));
      } else {
        var span = document.createElement("span");
        span.className = classifyLogLine(t);
        span.textContent = t;
        els.logBody.appendChild(span);
        els.logBody.appendChild(document.createTextNode("\n"));
      }
    }
    if (els.optStick.checked) {
      els.logFrame.scrollTop = els.logFrame.scrollHeight;
    }
  }

  const els = {
    nav: document.querySelectorAll(".nav-item"),
    views: document.querySelectorAll(".view"),
    globalPill: document.getElementById("globalStatusPill"),
    logBody: document.getElementById("logBody"),
    logGutter: document.getElementById("logGutter"),
    logFrame: document.getElementById("logFrame"),
    optStick: document.getElementById("optStickBottom"),
    optLogWrap: document.getElementById("optLogWrap"),
    optLogHighlight: document.getElementById("optLogHighlight"),
    logProgressHint: document.getElementById("logProgressHint"),
    logProgressFill: document.getElementById("logProgressFill"),
    logProgressRow: document.getElementById("logProgressRow"),
    btnLogFontMinus: document.getElementById("btnLogFontMinus"),
    btnLogFontPlus: document.getElementById("btnLogFontPlus"),
    btnClearLog: document.getElementById("btnClearLog"),
    btnStopRun: document.getElementById("btnStopRun"),
    btnCopyRunId: document.getElementById("btnCopyRunId"),
    runBtns: document.querySelectorAll(".btn-run"),
    optDry: document.getElementById("optDryRun"),
    optSkipPip: document.getElementById("optSkipPip"),
    optSkipYtdlp: document.getElementById("optSkipYtdlp"),
    runStatusSummary: document.getElementById("runStatusSummary"),
    runDetail: document.getElementById("runDetail"),
    runMetaId: document.getElementById("runMetaId"),
    runMetaPid: document.getElementById("runMetaPid"),
    runMetaExit: document.getElementById("runMetaExit"),
    runMetaDurationRow: document.getElementById("runMetaDurationRow"),
    runMetaDuration: document.getElementById("runMetaDuration"),
    runMetaEndedRow: document.getElementById("runMetaEndedRow"),
    runMetaEnded: document.getElementById("runMetaEnded"),
    runMetaFolder: document.getElementById("runMetaFolder"),
    runMetaFolderRow: document.getElementById("runMetaFolderRow"),
    historyTable: document.querySelector("#historyTable tbody"),
    historyMoreWrap: document.getElementById("historyMoreWrap"),
    btnHistoryMore: document.getElementById("btnHistoryMore"),
    fileList: document.getElementById("fileList"),
    fileDetail: document.getElementById("fileDetail"),
    fileCrumb: document.getElementById("fileBreadcrumb"),
    btnExplorer: document.getElementById("btnExplorer"),
    fileExplorerMsg: document.getElementById("fileExplorerMsg"),
    filesSplit: document.getElementById("filesSplit"),
    filesSplitHandle: document.getElementById("filesSplitHandle"),
    reportPointers: document.getElementById("reportPointers"),
    reportRuns: document.getElementById("reportRuns"),
    setPort: document.getElementById("setPort"),
    setAllow: document.getElementById("setAllow"),
    btnSaveSettings: document.getElementById("btnSaveSettings"),
    settingsMsg: document.getElementById("settingsMsg"),
    settingsArchiveRoot: document.getElementById("settingsArchiveRoot"),
    setEditorBackupMax: document.getElementById("setEditorBackupMax"),
    setBackupDest: document.getElementById("setBackupDest"),
    setBackupIncState: document.getElementById("setBackupIncState"),
    setBackupIncLogs: document.getElementById("setBackupIncLogs"),
    setBackupExtraPrefixes: document.getElementById("setBackupExtraPrefixes"),
    setBackupRetentionFiles: document.getElementById("setBackupRetentionFiles"),
    setBackupRetentionDays: document.getElementById("setBackupRetentionDays"),
    setRetentionDays: document.getElementById("setRetentionDays"),
    optPruneArchiveRuns: document.getElementById("optPruneArchiveRuns"),
    optPruneOperatorZips: document.getElementById("optPruneOperatorZips"),
    btnSaveRetention: document.getElementById("btnSaveRetention"),
    btnStorageCleanupPreview: document.getElementById("btnStorageCleanupPreview"),
    btnStorageCleanupRun: document.getElementById("btnStorageCleanupRun"),
    storageCleanupMsg: document.getElementById("storageCleanupMsg"),
    storageCleanupPreview: document.getElementById("storageCleanupPreview"),
    btnSaveBackupSettings: document.getElementById("btnSaveBackupSettings"),
    btnRunOperatorBackup: document.getElementById("btnRunOperatorBackup"),
    operatorBackupMsg: document.getElementById("operatorBackupMsg"),
    lastBackupResult: document.getElementById("lastBackupResult"),
    scheduleEditor: document.getElementById("scheduleEditor"),
    btnAddSchedule: document.getElementById("btnAddSchedule"),
    btnSaveSchedules: document.getElementById("btnSaveSchedules"),
    scheduleSaveMsg: document.getElementById("scheduleSaveMsg"),
    schedulerStatusLine: document.getElementById("schedulerStatusLine"),
    setCookieRemindDays: document.getElementById("setCookieRemindDays"),
    btnSaveCookieSettings: document.getElementById("btnSaveCookieSettings"),
    btnCookieAck: document.getElementById("btnCookieAck"),
    btnCookieSnooze: document.getElementById("btnCookieSnooze"),
    setPreRunMinutes: document.getElementById("setPreRunMinutes"),
    cookieSettingsMsg: document.getElementById("cookieSettingsMsg"),
    reminderBannerError: document.getElementById("reminderBannerError"),
    cookieReminderBanner: document.getElementById("cookieReminderBanner"),
    cookieReminderText: document.getElementById("cookieReminderText"),
    btnCookieBannerAck: document.getElementById("btnCookieBannerAck"),
    btnCookieBannerSnooze15: document.getElementById("btnCookieBannerSnooze15"),
    preRunReminderBanner: document.getElementById("preRunReminderBanner"),
    preRunReminderText: document.getElementById("preRunReminderText"),
    btnPreRunAck: document.getElementById("btnPreRunAck"),
    btnPreRunSnooze: document.getElementById("btnPreRunSnooze"),
    editorTabs: document.querySelectorAll("#editorTabs .tab"),
    editorTextarea: document.getElementById("editorTextarea"),
    editorMtime: document.getElementById("editorMtime"),
    editorRelLabel: document.getElementById("editorRelLabel"),
    editorDirtyPill: document.getElementById("editorDirtyPill"),
    editorOptionsStrip: document.getElementById("editorOptionsStrip"),
    editorOptionsConf: document.getElementById("editorOptionsConf"),
    optStripBlanks: document.getElementById("optStripBlanks"),
    optConfSmoke: document.getElementById("optConfSmoke"),
    cookiesCallout: document.getElementById("cookiesCallout"),
    optUnlockCookies: document.getElementById("optUnlockCookies"),
    btnSaveEditor: document.getElementById("btnSaveEditor"),
    editorMsg: document.getElementById("editorMsg"),
    editorSaveHint: document.getElementById("editorSaveHint"),
    dlDirWatchLater: document.getElementById("dlDirWatchLater"),
    dlDirChannels: document.getElementById("dlDirChannels"),
    dlDirVideos: document.getElementById("dlDirVideos"),
    btnSaveDownloadDirs: document.getElementById("btnSaveDownloadDirs"),
    downloadDirsMsg: document.getElementById("downloadDirsMsg"),
    downloadDirsEffective: document.getElementById("downloadDirsEffective"),
  };

  const STORAGE_LOG_HIGHLIGHT = "archive_console_log_highlight";

  let logLineCount = 0;
  /** Raw lines for the current stream (rebuild when toggling highlight). */
  let logLinesBuffer = [];
  let logFontPx = 13;
  let es = null;
  let filePath = "";
  let selectedRel = "";
  let editorFile = "playlists_input.txt";
  let editorBaseline = "";
  let editorJobRunning = false;

  const HISTORY_PAGE = 30;
  /** Last storage cleanup preview API response (for Run confirmation). */
  let lastStorageCleanupPreview = null;
  const historyRenderState = {
    items: [],
    pointers: {},
    latestFolders: {},
    shown: HISTORY_PAGE,
    historyLoadFailed: false,
    reportsLoadFailed: false,
  };

  const COOKIES_FILE = "cookies.txt";
  const YTDLP_CONF = "yt-dlp.conf";

  function formatFileSize(bytes) {
    if (bytes == null) {
      return "—";
    }
    var n = Number(bytes);
    if (!isFinite(n) || n < 0) {
      return "—";
    }
    if (n === 0) {
      return "0 B";
    }
    var units = ["B", "KB", "MB", "GB", "TB"];
    var i = 0;
    var v = n;
    while (v >= 1024 && i < units.length - 1) {
      v /= 1024;
      i++;
    }
    var decimals = i === 0 ? 0 : v >= 100 ? 0 : v >= 10 ? 1 : 2;
    return (
      v.toLocaleString(undefined, {
        maximumFractionDigits: decimals,
        minimumFractionDigits: 0,
      }) +
      " " +
      units[i]
    );
  }

  function filesExplorerSetMessage(text) {
    if (els.fileExplorerMsg) {
      els.fileExplorerMsg.textContent = text || "";
    }
  }

  function updateExplorerButton() {
    if (!els.btnExplorer) {
      return;
    }
    var atVirtualRoot = !filePath;
    var targetPath = selectedRel || filePath;
    var can = !atVirtualRoot && !!targetPath;
    els.btnExplorer.disabled = !can;
    if (selectedRel) {
      els.btnExplorer.textContent = "Reveal file in Explorer";
      els.btnExplorer.setAttribute(
        "aria-label",
        "Reveal the selected file in Windows Explorer"
      );
    } else if (filePath) {
      els.btnExplorer.textContent = "Open folder in Explorer";
      els.btnExplorer.setAttribute(
        "aria-label",
        "Open the current folder in Windows Explorer"
      );
    } else {
      els.btnExplorer.textContent = "Open in Explorer";
      els.btnExplorer.setAttribute(
        "aria-label",
        "Open in Windows Explorer"
      );
    }
  }

  function initFilesSplitResizer() {
    var split = els.filesSplit;
    var handle = els.filesSplitHandle;
    if (!split || !handle) {
      return;
    }

    function isWideLayout() {
      return window.matchMedia("(min-width: 801px)").matches;
    }

    function readStoredPct() {
      var s = localStorage.getItem("archive_console_files_split_pct");
      var n = parseFloat(s);
      if (!isFinite(n) || n < 28 || n > 75) {
        return 42;
      }
      return n;
    }

    function applyPct(pct) {
      if (!isWideLayout()) {
        split.style.gridTemplateColumns = "";
        return;
      }
      pct = Math.max(28, Math.min(75, pct));
      split.style.gridTemplateColumns = pct + "% 5px 1fr";
      localStorage.setItem(
        "archive_console_files_split_pct",
        String(pct)
      );
    }

    applyPct(readStoredPct());

    window.addEventListener("resize", function () {
      applyPct(readStoredPct());
    });

    handle.addEventListener("keydown", function (ev) {
      if (!isWideLayout()) {
        return;
      }
      if (ev.key === "ArrowLeft" || ev.key === "ArrowRight") {
        ev.preventDefault();
        var delta = ev.key === "ArrowLeft" ? -3 : 3;
        applyPct(readStoredPct() + delta);
      }
    });

    var dragging = false;
    handle.addEventListener("mousedown", function (downEv) {
      if (!isWideLayout()) {
        return;
      }
      downEv.preventDefault();
      dragging = true;

      function onMove(moveEv) {
        if (!dragging) {
          return;
        }
        var rect = split.getBoundingClientRect();
        if (rect.width <= 0) {
          return;
        }
        var x = moveEv.clientX - rect.left;
        var pct = (x / rect.width) * 100;
        applyPct(pct);
      }

      function onUp() {
        dragging = false;
        document.removeEventListener("mousemove", onMove);
        document.removeEventListener("mouseup", onUp);
      }

      document.addEventListener("mousemove", onMove);
      document.addEventListener("mouseup", onUp);
    });
  }

  function editorMarkClean() {
    editorBaseline = els.editorTextarea.value;
    els.editorDirtyPill.hidden = true;
  }

  function editorUpdateDirty() {
    const dirty = els.editorTextarea.value !== editorBaseline;
    els.editorDirtyPill.hidden = !dirty;
  }

  function setEditorRunning(running) {
    editorJobRunning = !!running;
    var cookiesBlocked =
      editorFile === COOKIES_FILE && !els.optUnlockCookies.checked;
    els.btnSaveEditor.disabled = editorJobRunning || cookiesBlocked;
    if (editorJobRunning) {
      els.editorSaveHint.textContent =
        "Saving disabled while a run is active.";
      els.editorSaveHint.hidden = false;
    } else if (cookiesBlocked) {
      els.editorSaveHint.textContent =
        "Unlock cookies to load and save this file.";
      els.editorSaveHint.hidden = false;
    } else {
      els.editorSaveHint.hidden = true;
    }
  }

  function editorTabOptionsVisible() {
    const isInputList =
      editorFile === "playlists_input.txt" ||
      editorFile === "channels_input.txt" ||
      editorFile === "videos_input.txt";
    els.editorOptionsStrip.hidden = !isInputList;
    els.editorOptionsConf.hidden = editorFile !== YTDLP_CONF;
    const isCookies = editorFile === COOKIES_FILE;
    els.cookiesCallout.hidden = !isCookies;
    if (!isCookies) {
      els.optUnlockCookies.checked = false;
    }
    els.editorTextarea.disabled =
      isCookies && !els.optUnlockCookies.checked;
    if (isCookies && !els.optUnlockCookies.checked) {
      els.editorTextarea.placeholder =
        "Locked — enable “Unlock cookies” to load this file.";
      els.editorTextarea.value = "";
      editorMarkClean();
    } else {
      els.editorTextarea.placeholder = "";
    }
  }

  async function loadEditorFile(force) {
    editorFile = force || editorFile;
    els.editorRelLabel.textContent = editorFile;
    editorTabOptionsVisible();
    var unlock =
      editorFile === COOKIES_FILE && els.optUnlockCookies.checked;
    var q =
      editorFile === COOKIES_FILE
        ? "?unlock_cookies=" + (unlock ? "1" : "0")
        : "";
    var r = await fetch(
      "/api/files/" + encodeURIComponent(editorFile) + q
    );
    if (!r.ok) {
      els.editorMsg.textContent = "Load failed: " + r.status;
      return;
    }
    var j = await r.json();
    els.editorMsg.textContent = "";
    if (j.mtime != null) {
      els.editorMtime.textContent =
        "mtime: " + new Date(j.mtime * 1000).toLocaleString();
    } else {
      els.editorMtime.textContent = "new / missing on disk";
    }
    if (j.locked) {
      (j.warnings || []).forEach(function (w) {
        els.editorMsg.textContent += (els.editorMsg.textContent ? " " : "") + w;
      });
      editorMarkClean();
      setEditorRunning(editorJobRunning);
      return;
    }
    els.editorTextarea.value = j.content != null ? j.content : "";
    editorMarkClean();
    setEditorRunning(editorJobRunning);
  }

  async function saveEditorFile() {
    var r0 = await fetch("/api/run/status");
    var s0 = await r0.json();
    if (s0.phase === "running") {
      els.editorMsg.textContent =
        "Save blocked: a job is running. Wait for it to finish.";
      return;
    }
    if (
      editorFile === COOKIES_FILE &&
      !els.optUnlockCookies.checked
    ) {
      els.editorMsg.textContent = "Enable unlock to save cookies.txt.";
      return;
    }
    var body = {
      content: els.editorTextarea.value,
      strip_blank_lines: els.optStripBlanks.checked,
      conf_smoke: els.optConfSmoke.checked,
      unlock_cookies:
        editorFile === COOKIES_FILE && els.optUnlockCookies.checked,
    };
    var r = await fetch(
      "/api/files/" + encodeURIComponent(editorFile),
      {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      }
    );
    if (r.status === 409) {
      try {
        var ej = await r.json();
        els.editorMsg.textContent =
          typeof ej.detail === "string"
            ? ej.detail
            : JSON.stringify(ej.detail);
      } catch (e) {
        els.editorMsg.textContent = await r.text();
      }
      return;
    }
    if (!r.ok) {
      els.editorMsg.textContent = "Save failed: " + r.status;
      return;
    }
    var j = await r.json();
    var parts = ["Saved."];
    if (j.backup) {
      parts.push("Backup: " + j.backup);
    }
    if (j.warnings && j.warnings.length) {
      parts.push("Hints: " + j.warnings.join(" "));
    }
    els.editorMsg.textContent = parts.join(" ");
    if (j.mtime != null) {
      els.editorMtime.textContent =
        "mtime: " + new Date(j.mtime * 1000).toLocaleString();
    }
    editorMarkClean();
  }

  function editorTrySwitchTab(nextFile) {
    if (els.editorTextarea.value !== editorBaseline) {
      if (
        !window.confirm(
          "Discard unsaved edits in " + editorFile + "?"
        )
      ) {
        return false;
      }
    }
    editorFile = nextFile;
    els.editorTabs.forEach(function (t) {
      var f = t.getAttribute("data-file");
      var on = f === editorFile;
      t.classList.toggle("is-active", on);
      t.setAttribute("aria-selected", on ? "true" : "false");
    });
    loadEditorFile(editorFile);
    return true;
  }

  function setPhase(phase) {
    els.globalPill.dataset.phase = phase;
    var labels = {
      idle: "idle",
      running: "running",
      success: "succeeded",
      failed: "failed",
      canceled: "canceled",
    };
    els.globalPill.textContent = labels[phase] || phase;
  }

  function formatDur(seconds) {
    if (seconds == null || isNaN(seconds)) {
      return "—";
    }
    var s = Math.max(0, Math.floor(seconds));
    var m = Math.floor(s / 60);
    s = s % 60;
    if (m >= 60) {
      var h = Math.floor(m / 60);
      m = m % 60;
      return h + "h " + m + "m " + s + "s";
    }
    if (m > 0) {
      return m + "m " + s + "s";
    }
    return s + "s";
  }

  function jobLabel(job) {
    var map = {
      watch_later: "Watch Later / playlists",
      channels: "Channels",
      videos: "Video list",
    };
    return map[job] || job || "job";
  }

  function latestFoldersFromPointers(pointers) {
    var m = {};
    Object.keys(pointers || {}).forEach(function (job) {
      var rel =
        pointers[job] && pointers[job].resolved_folder_rel;
      if (rel) {
        m[job] = rel;
      }
    });
    return m;
  }

  function activateView(viewId) {
    els.nav.forEach(function (b) {
      var on = b.getAttribute("data-view") === viewId;
      b.classList.toggle("is-active", on);
    });
    els.views.forEach(function (sec) {
      sec.classList.toggle("is-active", sec.id === "view-" + viewId);
    });
  }

  function getInitialViewFromUrl() {
    var q = new URLSearchParams(window.location.search);
    var v = q.get("view");
    if (v === "history" || v === "logs" || v === "reports") {
      return "history";
    }
    if (
      v === "files" ||
      v === "inputs" ||
      v === "settings" ||
      v === "ytdlp" ||
      v === "run"
    ) {
      return v;
    }
    return "run";
  }

  function scrollHistorySectionFromUrl() {
    if (getInitialViewFromUrl() !== "history") {
      return;
    }
    var q = new URLSearchParams(window.location.search);
    var sec = q.get("section");
    var el = null;
    if (sec === "outcomes") {
      el = document.getElementById("run-outcomes");
    } else if (sec === "reports") {
      el = document.getElementById("reports-downloads");
    }
    if (el) {
      window.requestAnimationFrame(function () {
        el.scrollIntoView({ block: "start", behavior: "smooth" });
      });
    }
  }

  function renderRunPanel(status) {
    var phase = (status && status.phase) || "idle";
    var run = status && status.run;
    var isRunning = phase === "running";
    var hasEnded =
      run &&
      (phase === "success" ||
        phase === "failed" ||
        phase === "canceled");

    if (phase === "idle" || !run) {
      els.runStatusSummary.textContent = "No job running.";
      els.runStatusSummary.classList.add("muted");
      els.runStatusSummary.classList.remove("run-status-live");
      els.runDetail.hidden = true;
      els.btnStopRun.hidden = true;
      return;
    }

    els.runDetail.hidden = false;
    els.runStatusSummary.classList.toggle("run-status-live", isRunning);
    els.runStatusSummary.classList.toggle("muted", !isRunning);

    if (isRunning) {
      var bits = ["Running: " + jobLabel(run.job)];
      if (run.dry_run) {
        bits.push("dry-run");
      }
      els.runStatusSummary.textContent =
        bits.join(" · ") + " — live output below.";
      els.btnStopRun.hidden = false;
    } else if (hasEnded) {
      els.runStatusSummary.textContent =
        "Last run finished (" + jobLabel(run.job) + "). Details:";
      els.btnStopRun.hidden = true;
    } else {
      els.runStatusSummary.textContent = "Run status: " + phase;
      els.btnStopRun.hidden = true;
    }

    els.runMetaId.textContent = run.run_id || "—";
    els.runMetaPid.textContent =
      run.pid != null ? String(run.pid) : "—";

    if (phase === "canceled") {
      els.runMetaExit.textContent = "stopped";
    } else if (isRunning) {
      els.runMetaExit.textContent = "—";
    } else if (run.exit_code != null) {
      els.runMetaExit.textContent = String(run.exit_code);
    } else {
      els.runMetaExit.textContent = "—";
    }

    if (hasEnded && run.started_unix && run.ended_unix) {
      els.runMetaDurationRow.hidden = false;
      els.runMetaDuration.textContent = formatDur(
        run.ended_unix - run.started_unix
      );
      els.runMetaEndedRow.hidden = false;
      els.runMetaEnded.textContent = new Date(
        run.ended_unix * 1000
      ).toLocaleString();
    } else {
      els.runMetaDurationRow.hidden = true;
      els.runMetaEndedRow.hidden = true;
    }

    if (run.log_folder_rel) {
      var rel = run.log_folder_rel;
      els.runMetaFolderRow.hidden = false;
      els.runMetaFolder.href = reportsViewHref(rel + "/report.html");
      els.runMetaFolder.textContent = rel;
      els.runMetaFolder.title = rel;
    } else {
      els.runMetaFolderRow.hidden = true;
      els.runMetaFolder.removeAttribute("title");
    }
  }

  async function refreshRunPanel() {
    try {
      const r = await fetch("/api/run/status");
      const j = await r.json();
      renderRunPanel(j);
    } catch {
      /* ignore */
    }
  }

  function applyLogWrap() {
    els.logBody.classList.toggle("is-wrap", els.optLogWrap.checked);
  }

  function applyLogFont() {
    els.logBody.style.fontSize = logFontPx + "px";
    var g = Math.max(10, logFontPx - 2);
    els.logGutter.style.fontSize = g + "px";
  }

  function appendLogLine(text) {
    var t = text != null ? String(text) : "";
    logLinesBuffer.push(t);
    logLineCount += 1;
    els.logGutter.appendChild(document.createTextNode(logLineCount + "\n"));
    var hi = els.optLogHighlight && els.optLogHighlight.checked;
    if (!hi) {
      els.logBody.appendChild(document.createTextNode(t + "\n"));
    } else {
      var span = document.createElement("span");
      span.className = classifyLogLine(t);
      span.textContent = t;
      els.logBody.appendChild(span);
      els.logBody.appendChild(document.createTextNode("\n"));
    }
    updateLastProgressFromLine(t);
    if (els.optStick.checked) {
      els.logFrame.scrollTop = els.logFrame.scrollHeight;
    }
  }

  function clearLogView() {
    logLineCount = 0;
    logLinesBuffer = [];
    els.logGutter.textContent = "";
    els.logBody.textContent = "";
    resetLogProgressHint();
  }

  function connectStream() {
    if (es) {
      es.close();
    }
    es = new EventSource("/api/run/stream");
    es.onmessage = function (ev) {
      let msg;
      try {
        msg = JSON.parse(ev.data);
      } catch {
        return;
      }
      if (msg.type === "hello") {
        if (msg.status && msg.status.phase) {
          setPhase(msg.status.phase);
          renderRunPanel(msg.status);
        }
        refreshCookieReminder();
        return;
      }
      if (msg.type === "start") {
        clearLogView();
        renderRunPanel({
          phase: "running",
          run: {
            run_id: msg.run_id,
            job: msg.job,
            pid: null,
            dry_run: els.optDry.checked,
          },
        });
        setPhase("running");
        disableRunButtons(true);
        editorJobRunning = true;
        setEditorRunning(true);
        refreshRunPanel();
        return;
      }
      if (msg.type === "line") {
        appendLogLine(msg.text != null ? msg.text : "");
        return;
      }
      if (msg.type === "end") {
        var code = msg.exit_code;
        var canceled = !!msg.canceled;
        if (canceled) {
          setPhase("canceled");
          appendLogLine(
            "[console] Stopped by user — batch may leave partial files on disk."
          );
        } else {
          setPhase(code === 0 ? "success" : "failed");
        }
        disableRunButtons(false);
        editorJobRunning = false;
        setEditorRunning(false);
        refreshRunPanel();
        loadRunOverview();
        return;
      }
    };
    es.onerror = function () {
      /* browser auto-reconnects EventSource */
    };
  }

  function disableRunButtons(disabled) {
    els.runBtns.forEach(function (b) {
      b.disabled = disabled;
    });
  }


  function renderHistoryRows() {
    var tb = els.historyTable;
    tb.innerHTML = "";
    if (historyRenderState.historyLoadFailed) {
      var trErr = document.createElement("tr");
      trErr.innerHTML =
        '<td colspan="8" class="muted">Could not load run history (request failed). Refresh the page.</td>';
      tb.appendChild(trErr);
      if (els.historyMoreWrap) {
        els.historyMoreWrap.hidden = true;
      }
      return;
    }
    var items = historyRenderState.items;
    var latestFolders = historyRenderState.latestFolders;
    var n = historyRenderState.shown;
    if (!items.length) {
      var tr0 = document.createElement("tr");
      tr0.innerHTML =
        '<td colspan="8" class="muted">No recorded runs yet. Start a job from <strong>Run</strong>; finished jobs appear here with exit code, item stats, and folder.</td>';
      tb.appendChild(tr0);
      if (els.historyMoreWrap) {
        els.historyMoreWrap.hidden = true;
      }
      return;
    }
    var slice = items.slice(0, Math.min(n, items.length));
    slice.forEach(function (row) {
      var tr = document.createElement("tr");
      var dt = new Date((row.started_unix || 0) * 1000);
      var folder = row.log_folder_rel || "";
      var reportHref = folder
        ? reportsViewHref(folder + "/report.html")
        : "#";
      var exitDisp =
        row.phase === "canceled"
          ? "stopped"
          : row.exit_code != null
            ? String(row.exit_code)
            : "—";
      var exitClass = "exit-cell";
      if (row.phase === "canceled") {
        exitClass += " exit-stopped";
      } else if (row.exit_code != null && row.exit_code !== 0) {
        exitClass += " exit-fail";
      } else if (row.exit_code === 0) {
        exitClass += " exit-ok";
      }
      var latestTag = "";
      if (
        folder &&
        latestFolders[row.job] &&
        latestFolders[row.job] === folder
      ) {
        latestTag =
          ' <span class="pill dim latest-pill" title="Matches latest pointer for this job">Latest</span>';
      }
      var rs = row.run_stats;
      var hasStats =
        rs &&
        typeof rs.tried === "number" &&
        typeof rs.ok === "number" &&
        typeof rs.fail === "number" &&
        typeof rs.saved === "number";
      var statsSubrow;
      if (hasStats) {
        statsSubrow =
          '<div class="history-job-stats muted small" role="group" aria-label="Run item stats">' +
          "Tried " +
          esc(String(rs.tried)) +
          " · OK " +
          esc(String(rs.ok)) +
          " · Fail " +
          esc(String(rs.fail)) +
          " · Saved " +
          esc(String(rs.saved)) +
          "</div>";
      } else {
        statsSubrow =
          '<div class="history-job-stats muted small" role="status">Item stats: —</div>';
      }
      var triedCell = hasStats ? esc(String(rs.tried)) : "—";
      var okCell = hasStats ? esc(String(rs.ok)) : "—";
      var failCell = hasStats ? esc(String(rs.fail)) : "—";
      var savedCell = hasStats ? esc(String(rs.saved)) : "—";
      tr.innerHTML =
        "<td>" +
        esc(row.job) +
        statsSubrow +
        "</td><td>" +
        esc(dt.toLocaleString()) +
        '</td><td class="' +
        esc(exitClass) +
        '">' +
        esc(exitDisp) +
        '</td><td class="hist-stat hist-stat-wide">' +
        triedCell +
        '</td><td class="hist-stat hist-stat-wide">' +
        okCell +
        '</td><td class="hist-stat hist-stat-wide">' +
        failCell +
        '</td><td class="hist-stat hist-stat-wide">' +
        savedCell +
        '</td><td class="history-folder-cell">' +
        (folder
          ? '<a class="link" target="_blank" rel="noopener" href="' +
            esc(reportHref) +
            '" title="' +
            esc(folder) +
            '">' +
            esc(folder) +
            "</a>"
          : "—") +
        latestTag +
        "</td>";
      tb.appendChild(tr);
    });
    if (els.historyMoreWrap) {
      els.historyMoreWrap.hidden = items.length <= slice.length;
    }
  }

  function renderReportCards() {
    els.reportPointers.innerHTML = "";
    if (historyRenderState.reportsLoadFailed) {
      var p = document.createElement("p");
      p.className = "muted";
      p.textContent =
        "Could not load latest run pointers. Check the console server and try again.";
      els.reportPointers.appendChild(p);
      return;
    }
    var ptrs = historyRenderState.pointers;
    Object.keys(ptrs).forEach(function (job) {
      var p = ptrs[job];
      var card = document.createElement("div");
      card.className = "card";
      var folder = p.resolved_folder_rel || "";
      var viewHref = folder
        ? reportsViewHref(folder + "/report.html")
        : "";
      var dlHref = folder
        ? reportsFileHref(folder + "/report.html", true)
        : "";
      var actions = "";
      if (viewHref) {
        actions =
          '<p><a class="link" target="_blank" rel="noopener" href="' +
          esc(viewHref) +
          '">Open report</a> · <a class="link muted small" href="' +
          esc(dlHref) +
          '">Download</a></p>';
      } else {
        actions =
          '<p class="muted small">No folder resolved yet (pointer missing, empty, or path not found). Run the job or check <code>' +
          esc(p.pointer_file) +
          "</code>.</p>";
      }
      var raw = p.pointer_raw || "(empty)";
      card.innerHTML =
        "<h2>" +
        esc(jobLabel(job)) +
        '</h2><p class="muted small">Job key: <code class="mono-ellipsis" title="' +
        esc(job) +
        '">' +
        esc(job) +
        '</code> · Pointer: <code class="mono-ellipsis" title="' +
        esc(p.pointer_file || "") +
        '">' +
        esc(p.pointer_file) +
        '</code></p><p class="muted small">Path from pointer:</p><p><code class="mono-ellipsis" title="' +
        esc(p.pointer_raw || "") +
        '">' +
        esc(raw) +
        "</code></p>" +
        actions;
      els.reportPointers.appendChild(card);
    });
  }

  function renderRecentRuns() {
    var ul = els.reportRuns;
    ul.innerHTML = "";
    if (historyRenderState.reportsLoadFailed) {
      var liFail = document.createElement("li");
      liFail.innerHTML =
        "<em class=\"muted\">Could not load folder list.</em>";
      ul.appendChild(liFail);
      return;
    }
    var names = historyRenderState.recentRuns || [];
    if (!names.length) {
      var li0 = document.createElement("li");
      li0.innerHTML =
        "<em class=\"muted\">No <code>archive_run_*</code> folders found under <code>logs/</code> yet.</em>";
      ul.appendChild(li0);
      return;
    }
    names.forEach(function (name) {
      var li = document.createElement("li");
      var runPath = "logs/" + name;
      var href = reportsViewHref(runPath + "/report.html");
      var dl = reportsFileHref(runPath + "/report.html", true);
      li.innerHTML =
        '<a class="link run-folder-link mono-ellipsis" target="_blank" rel="noopener" href="' +
        esc(href) +
        '" title="' +
        esc(runPath) +
        '">' +
        esc(name) +
        '</a> <span class="muted small">·</span> <a class="link muted small" href="' +
        esc(dl) +
        '">Download</a>';
      ul.appendChild(li);
    });
  }

  async function loadRunOverview() {
    historyRenderState.shown = HISTORY_PAGE;
    var histItems = [];
    var rep = {
      pointers: {},
      recent_runs: [],
    };
    historyRenderState.historyLoadFailed = false;
    historyRenderState.reportsLoadFailed = false;
    try {
      var responses = await Promise.all([
        fetch("/api/history"),
        fetch("/api/reports/latest"),
      ]);
      var hr = responses[0];
      var rr = responses[1];
      if (!hr.ok) {
        historyRenderState.historyLoadFailed = true;
      } else {
        var hj = await hr.json();
        histItems = hj.items || [];
      }
      if (!rr.ok) {
        historyRenderState.reportsLoadFailed = true;
      } else {
        rep = await rr.json();
      }
    } catch {
      historyRenderState.historyLoadFailed = true;
      historyRenderState.reportsLoadFailed = true;
    }
    historyRenderState.items = histItems;
    historyRenderState.pointers = rep.pointers || {};
    historyRenderState.recentRuns = rep.recent_runs || [];
    historyRenderState.latestFolders = latestFoldersFromPointers(
      historyRenderState.pointers
    );
    renderHistoryRows();
    renderReportCards();
    renderRecentRuns();
  }

  function renderBreadcrumb(path) {
    els.fileCrumb.innerHTML = "";
    const parts = path ? path.split("/") : [];
    const acc = [];
    function addLabel(label, rel) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.textContent = label;
      btn.title = rel ? rel : "Allowlisted roots";
      btn.addEventListener("click", function () {
        browseTo(rel);
      });
      els.fileCrumb.appendChild(btn);
    }
    addLabel("roots", "");
    parts.forEach(function (seg, i) {
      acc.push(seg);
      els.fileCrumb.appendChild(document.createTextNode(" / "));
      addLabel(seg, acc.join("/"));
    });
  }

  async function browseTo(rel) {
    filePath = rel || "";
    selectedRel = "";
    filesExplorerSetMessage("");
    renderBreadcrumb(filePath);
    const q = filePath ? "?path=" + encodeURIComponent(filePath) : "";
    const r = await fetch("/api/files/list" + q);
    if (!r.ok) {
      els.fileList.innerHTML =
        "<li><em class=\"muted\">" + esc(r.status + " " + r.statusText) + "</em></li>";
      updateExplorerButton();
      return;
    }
    const j = await r.json();
    els.fileList.innerHTML = "";
    if (j.type === "file") {
      selectFile(j.path, j);
      return;
    }
    (j.entries || []).forEach(function (ent) {
      const li = document.createElement("li");
      const btn = document.createElement("button");
      btn.type = "button";
      var label = (ent.is_dir ? "📁 " : "📄 ") + ent.name;
      btn.textContent = label;
      btn.setAttribute("title", ent.rel || ent.name);
      btn.addEventListener("click", function () {
        if (ent.is_dir) {
          browseTo(ent.rel);
        } else {
          document
            .querySelectorAll(".file-list button")
            .forEach(function (x) {
              x.classList.remove("is-selected");
            });
          btn.classList.add("is-selected");
          selectFile(ent.rel, ent);
        }
      });
      li.appendChild(btn);
      els.fileList.appendChild(li);
    });
    updateExplorerButton();
  }

  async function selectFile(rel, ent) {
    selectedRel = rel;
    filesExplorerSetMessage("");
    const r = await fetch(
      "/api/files/metadata?path=" + encodeURIComponent(rel)
    );
    const m = r.ok ? await r.json() : {};
    const mt = new Date((m.mtime || ent.mtime || 0) * 1000);
    var rawSize = m.size != null ? m.size : ent.size;
    var sizeTitle =
      rawSize != null
        ? Number(rawSize).toLocaleString() + " bytes"
        : "";
    els.fileDetail.innerHTML =
      "<p><strong title=\"" +
      esc(rel) +
      "\">" +
      esc(rel) +
      "</strong></p>" +
      '<p title="' +
      esc(sizeTitle) +
      '">Size: ' +
      esc(formatFileSize(rawSize)) +
      "</p>" +
      "<p>Modified: " +
      esc(mt.toLocaleString()) +
      "</p>" +
      (m.is_dir
        ? ""
        : '<p><a class="link" target="_blank" rel="noopener" href="' +
          esc(reportsOpenHref(rel)) +
          '">Open</a> · <a class="link" href="' +
          esc(reportsFileHref(rel, true)) +
          '">Download</a></p>');
    updateExplorerButton();
  }

  var settingsJobsCache = [];
  var lastCookieHygiene = {};
  var lastPreRunReminder = {
    snooze_until_unix: 0,
    acknowledged_fire_key: "",
  };

  function renderLastOperatorBackup(info) {
    if (!els.lastBackupResult) {
      return;
    }
    if (!info) {
      els.lastBackupResult.textContent = "No operator ZIP backup run yet.";
      return;
    }
    var ok = info.success ? "ok" : "failed";
    var t = new Date((info.finished_unix || 0) * 1000);
    var tStr = t.getTime() ? t.toLocaleString() : "—";
    els.lastBackupResult.textContent =
      "Last backup (" + ok + ") " + tStr + " — " + (info.summary || "—");
  }

  function renderScheduleEditor(schedList, hints, jobKeys) {
    if (!els.scheduleEditor) {
      return;
    }
    settingsJobsCache = jobKeys || settingsJobsCache;
    var jobs = settingsJobsCache;
    var hintMap = {};
    (hints || []).forEach(function (h) {
      if (h && h.schedule && h.schedule.id) {
        hintMap[h.schedule.id] = h.next_run;
      }
    });
    els.scheduleEditor.innerHTML = "";
    (schedList || []).forEach(function (s) {
      var row = document.createElement("div");
      row.className = "schedule-row";
      var sid = s.id || "sch_" + Date.now() + "_" + Math.floor(Math.random() * 1e6);
      var next = hintMap[s.id] || "";
      var nextTxt = next ? "Next run (local): " + next : "Next run: — (disabled or n/a)";
      var jobOpts = jobs
        .map(function (j) {
          return (
            "<option value=\"" +
            esc(j) +
            "\"" +
            (String(s.job) === String(j) ? " selected" : "") +
            ">" +
            esc(j) +
            "</option>"
          );
        })
        .join("");
      row.innerHTML =
        "<input type=\"hidden\" class=\"sch-id\" value=\"" +
        esc(sid) +
        "\" />" +
        "<label class=\"field compact\"><span>Job</span><select class=\"sch-job\">" +
        jobOpts +
        "</select></label>" +
        "<label class=\"field compact\"><span>Day (1–31)</span><input type=\"number\" class=\"sch-day\" min=\"1\" max=\"31\" value=\"" +
        esc(s.day_of_month) +
        "\" /></label>" +
        "<label class=\"field compact\"><span>Hour</span><input type=\"number\" class=\"sch-hour\" min=\"0\" max=\"23\" value=\"" +
        esc(s.hour) +
        "\" /></label>" +
        "<label class=\"field compact\"><span>Min</span><input type=\"number\" class=\"sch-min\" min=\"0\" max=\"59\" value=\"" +
        esc(s.minute) +
        "\" /></label>" +
        "<label class=\"chk compact\"><input type=\"checkbox\" class=\"sch-en\"" +
        (s.enabled ? " checked" : "") +
        " /> Enabled</label>" +
        "<button type=\"button\" class=\"btn ghost small sch-del\">Remove</button>" +
        "<p class=\"muted small sch-next\">" +
        esc(nextTxt) +
        "</p>";
      row.querySelector(".sch-del").addEventListener("click", function () {
        row.remove();
      });
      els.scheduleEditor.appendChild(row);
    });
  }

  function collectSchedulesFromForm() {
    var out = [];
    if (!els.scheduleEditor) {
      return out;
    }
    els.scheduleEditor.querySelectorAll(".schedule-row").forEach(function (row) {
      var idEl = row.querySelector(".sch-id");
      var job = row.querySelector(".sch-job");
      var day = row.querySelector(".sch-day");
      var hour = row.querySelector(".sch-hour");
      var min = row.querySelector(".sch-min");
      var en = row.querySelector(".sch-en");
      if (!job) {
        return;
      }
      out.push({
        id: idEl ? idEl.value || "" : "",
        job: job.value,
        day_of_month: Math.min(31, Math.max(1, parseInt(day && day.value, 10) || 1)),
        hour: Math.min(23, Math.max(0, parseInt(hour && hour.value, 10) || 0)),
        minute: Math.min(59, Math.max(0, parseInt(min && min.value, 10) || 0)),
        enabled: !!(en && en.checked),
      });
    });
    return out;
  }

  function showReminderError(text) {
    var el = els.reminderBannerError;
    if (!el) {
      return;
    }
    window.clearTimeout(showReminderError._t);
    if (text) {
      el.hidden = false;
      el.textContent = text;
      showReminderError._t = window.setTimeout(function () {
        el.hidden = true;
        el.textContent = "";
      }, 8000);
    } else {
      el.hidden = true;
      el.textContent = "";
    }
  }

  function postCookieHygieneAction(opts) {
    opts = opts || {};
    return fetch("/api/settings/cookie-hygiene/ack", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        snooze_days: opts.snoozeDays != null ? opts.snoozeDays : 0,
        snooze_minutes: opts.snoozeMinutes != null ? opts.snoozeMinutes : 0,
      }),
    });
  }

  async function syncCookieHygieneFromServer() {
    try {
      var r = await fetch("/api/settings");
      if (!r.ok) {
        return;
      }
      var j = await r.json();
      var ch = j.cookie_hygiene || {};
      lastCookieHygiene = {
        last_acknowledged_unix: ch.last_acknowledged_unix || 0,
        snooze_until_unix: ch.snooze_until_unix || 0,
      };
    } catch {
      /* ignore */
    }
  }

  function setReminderActionBusy(busy) {
    [
      els.btnCookieBannerAck,
      els.btnCookieBannerSnooze15,
      els.btnPreRunAck,
      els.btnPreRunSnooze,
    ].forEach(function (btn) {
      if (btn) {
        btn.disabled = !!busy;
      }
    });
  }

  async function refreshReminders() {
    showReminderError("");
    try {
      var r = await fetch("/api/settings/reminders");
      if (!r.ok) {
        showReminderError("Could not load reminders (HTTP " + r.status + ").");
        return;
      }
      var j = await r.json();
      var c0 = j.cookie_reminder || {};
      var b = els.cookieReminderBanner;
      var cmsg = String(c0.message == null ? "" : c0.message).trim();
      if (b) {
        if (c0.show && cmsg) {
          b.hidden = false;
          if (els.cookieReminderText) {
            els.cookieReminderText.textContent = cmsg;
          }
        } else {
          b.hidden = true;
          if (els.cookieReminderText) {
            els.cookieReminderText.textContent = "";
          }
        }
      }
      var pr0 = j.pre_run_reminder || {};
      var pb = els.preRunReminderBanner;
      var pt = els.preRunReminderText;
      var pmsg = String(pr0.message == null ? "" : pr0.message).trim();
      if (pb && pt) {
        if (pr0.show && pmsg) {
          pb.hidden = false;
          pt.textContent = pmsg;
        } else {
          pb.hidden = true;
          pt.textContent = "";
        }
      }
    } catch {
      showReminderError("Reminder check failed (network).");
    }
  }

  async function refreshCookieReminder() {
    await refreshReminders();
  }

  async function loadSettingsForm() {
    const r = await fetch("/api/settings");
    const j = await r.json();
    els.setPort.value = j.port;
    els.setAllow.value = (j.allowlisted_rel_prefixes || []).join(", ");
    els.settingsArchiveRoot.textContent = "Archive root: " + j.archive_root;
    if (els.setEditorBackupMax) {
      els.setEditorBackupMax.value = j.editor_backup_max != null ? j.editor_backup_max : 10;
    }
    var ob = j.operator_backup || {};
    if (els.setBackupDest) {
      els.setBackupDest.value = ob.destination_rel || "logs/archive_console_backups";
    }
    if (els.setBackupIncState) {
      els.setBackupIncState.checked = !!ob.include_state_json;
    }
    if (els.setBackupIncLogs) {
      els.setBackupIncLogs.checked = ob.include_logs_dir !== false;
    }
    if (els.setBackupExtraPrefixes) {
      els.setBackupExtraPrefixes.value = (ob.include_extra_rel_prefixes || []).join(", ");
    }
    if (els.setBackupRetentionFiles) {
      els.setBackupRetentionFiles.value = ob.retention_max_files != null ? ob.retention_max_files : 20;
    }
    if (els.setBackupRetentionDays) {
      els.setBackupRetentionDays.value = ob.retention_days != null ? ob.retention_days : 0;
    }
    var sr = j.storage_retention || {};
    if (els.setRetentionDays) {
      els.setRetentionDays.value =
        sr.retention_days != null ? sr.retention_days : 90;
    }
    if (els.optPruneArchiveRuns) {
      els.optPruneArchiveRuns.checked =
        sr.prune_archive_runs !== false;
    }
    if (els.optPruneOperatorZips) {
      els.optPruneOperatorZips.checked =
        sr.prune_operator_backup_zips !== false;
    }
    if (els.storageCleanupMsg) {
      els.storageCleanupMsg.textContent = "";
    }
    if (els.storageCleanupPreview) {
      els.storageCleanupPreview.hidden = true;
      els.storageCleanupPreview.textContent = "";
    }
    lastStorageCleanupPreview = null;
    renderLastOperatorBackup(j.last_operator_backup);
    if (els.operatorBackupMsg) {
      els.operatorBackupMsg.textContent = "";
    }
    var ch = j.cookie_hygiene || {};
    lastCookieHygiene = {
      last_acknowledged_unix: ch.last_acknowledged_unix || 0,
      snooze_until_unix: ch.snooze_until_unix || 0,
    };
    if (els.setCookieRemindDays) {
      els.setCookieRemindDays.value = ch.remind_interval_days != null ? ch.remind_interval_days : 0;
    }
    var prs = j.pre_run_reminder_settings || {};
    lastPreRunReminder = {
      snooze_until_unix: prs.snooze_until_unix || 0,
      acknowledged_fire_key: prs.acknowledged_fire_key || "",
    };
    if (els.setPreRunMinutes) {
      els.setPreRunMinutes.value = prs.minutes_before != null ? prs.minutes_before : 0;
    }
    if (els.cookieSettingsMsg) {
      els.cookieSettingsMsg.textContent = "";
    }
    if (els.schedulerStatusLine) {
      els.schedulerStatusLine.textContent = j.scheduler_note || "";
    }
    var jobKeys = j.jobs || ["watch_later", "channels", "videos"];
    renderScheduleEditor(j.schedules || [], j.schedule_hints || [], jobKeys);
    if (els.scheduleSaveMsg) {
      els.scheduleSaveMsg.textContent = "";
    }
    refreshCookieReminder();
  }

  if (els.btnHistoryMore) {
    els.btnHistoryMore.addEventListener("click", function () {
      historyRenderState.shown += HISTORY_PAGE;
      renderHistoryRows();
    });
  }

  function renderDownloadDirsEffective(eff) {
    var el = els.downloadDirsEffective;
    if (!el || !eff) {
      return;
    }
    var lines = [];
    ["watch_later", "channels", "videos"].forEach(function (k) {
      var o = eff[k];
      if (!o) {
        return;
      }
      var label =
        k === "watch_later"
          ? "Watch Later"
          : k === "channels"
            ? "Channels"
            : "Videos";
      var abs = o.effective_abs || "—";
      var cr =
        o.configured_rel != null
          ? o.configured_rel
          : "(default: " + (o.default_rel || "") + ")";
      lines.push(label + ": configured " + cr + " → effective " + abs);
    });
    el.innerHTML = lines
      .map(function (t) {
        return "<p class=\"small\" style=\"margin:0.25rem 0\">" + esc(t) + "</p>";
      })
      .join("");
  }

  async function loadDownloadDirsForm() {
    if (!els.dlDirWatchLater) {
      return;
    }
    try {
      var r = await fetch("/api/settings");
      if (!r.ok) {
        return;
      }
      var j = await r.json();
      var dd = j.download_dirs || {};
      els.dlDirWatchLater.value = dd.watch_later != null ? dd.watch_later : "";
      els.dlDirChannels.value = dd.channels != null ? dd.channels : "";
      els.dlDirVideos.value = dd.videos != null ? dd.videos : "";
      renderDownloadDirsEffective(j.download_dirs_effective);
      if (els.downloadDirsMsg) {
        els.downloadDirsMsg.textContent = "";
      }
    } catch {
      /* ignore */
    }
  }

  function setDownloadDirsActionsDisabled(disabled) {
    if (els.btnSaveDownloadDirs) {
      els.btnSaveDownloadDirs.disabled = !!disabled;
    }
    document.querySelectorAll(".btn-dl-browse").forEach(function (b) {
      b.disabled = !!disabled;
    });
  }

  function collectDownloadDirsPayload() {
    return {
      watch_later: (els.dlDirWatchLater && els.dlDirWatchLater.value.trim()) || "",
      channels: (els.dlDirChannels && els.dlDirChannels.value.trim()) || "",
      videos: (els.dlDirVideos && els.dlDirVideos.value.trim()) || "",
    };
  }

  async function refreshDownloadDirsPreviewFromForm() {
    if (!els.dlDirWatchLater) {
      return;
    }
    try {
      var r = await fetch("/api/settings/download-dirs/preview", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(collectDownloadDirsPayload()),
      });
      if (!r.ok) {
        return;
      }
      var j = await r.json();
      renderDownloadDirsEffective(j.download_dirs_effective);
    } catch {
      /* ignore */
    }
  }

  document.querySelectorAll(".btn-dl-browse").forEach(function (btn) {
    btn.addEventListener("click", async function () {
      var field = btn.getAttribute("data-dl-field");
      if (!field || btn.disabled) {
        return;
      }
      if (els.downloadDirsMsg) {
        els.downloadDirsMsg.textContent = "";
      }
      setDownloadDirsActionsDisabled(true);
      try {
        var r = await fetch("/api/settings/download-dirs/browse", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ field: field }),
        });
        if (r.status === 204) {
          if (els.downloadDirsMsg) {
            els.downloadDirsMsg.textContent =
              "No folder selected (dialog cancelled or closed).";
          }
          return;
        }
        if (r.status === 503) {
          var d503 = await r.json().catch(function () {
            return {};
          });
          if (els.downloadDirsMsg) {
            els.downloadDirsMsg.textContent =
              (d503.detail && String(d503.detail)) ||
              "Folder picker unavailable on this server.";
          }
          return;
        }
        if (!r.ok) {
          var errJ = await r.json().catch(function () {
            return null;
          });
          var detail =
            errJ && errJ.detail != null
              ? typeof errJ.detail === "string"
                ? errJ.detail
                : JSON.stringify(errJ.detail)
              : await r.text();
          if (els.downloadDirsMsg) {
            els.downloadDirsMsg.textContent = "Browse failed: " + r.status + " " + detail;
          }
          return;
        }
        var j = await r.json();
        if (j.field === "watch_later" && els.dlDirWatchLater) {
          els.dlDirWatchLater.value = j.rel || "";
          els.dlDirWatchLater.focus();
        }
        if (j.field === "channels" && els.dlDirChannels) {
          els.dlDirChannels.value = j.rel || "";
          els.dlDirChannels.focus();
        }
        if (j.field === "videos" && els.dlDirVideos) {
          els.dlDirVideos.value = j.rel || "";
          els.dlDirVideos.focus();
        }
        await refreshDownloadDirsPreviewFromForm();
        if (els.downloadDirsMsg) {
          els.downloadDirsMsg.textContent =
            "Folder selected — review below, then Save output folders to persist.";
        }
      } catch (ex) {
        if (els.downloadDirsMsg) {
          els.downloadDirsMsg.textContent =
            "Browse failed (network or server). Check that Archive Console is running.";
        }
      } finally {
        setDownloadDirsActionsDisabled(false);
      }
    });
  });

  /* Navigation */
  els.nav.forEach(function (btn) {
    btn.addEventListener("click", function () {
      const v = btn.getAttribute("data-view");
      activateView(v);
      if (v === "history") {
        loadRunOverview();
      }
      if (v === "files") {
        browseTo("");
      }
      if (v === "settings") {
        loadSettingsForm();
      }
      if (v === "inputs") {
        loadEditorFile(editorFile);
        loadDownloadDirsForm();
      }
      if (v === "ytdlp") {
        if (typeof window.ytdlpSetupLoad === "function") {
          window.ytdlpSetupLoad();
        } else {
          var ytdlpWarn = document.getElementById("ytdlpMsg");
          if (ytdlpWarn) {
            ytdlpWarn.textContent =
              "Download settings script did not load. Hard-refresh (Ctrl+F5) or check the browser console / Network tab for /static/ytdlp_setup.js.";
          }
        }
      }
      if (v === "run") {
        refreshRunPanel();
        refreshCookieReminder();
      }
    });
  });

  els.editorTabs.forEach(function (tab) {
    tab.addEventListener("click", function () {
      var f = tab.getAttribute("data-file");
      if (f) {
        editorTrySwitchTab(f);
      }
    });
  });

  els.editorTextarea.addEventListener("input", editorUpdateDirty);

  els.optUnlockCookies.addEventListener("change", function () {
    editorTabOptionsVisible();
    loadEditorFile(editorFile);
  });

  els.btnSaveEditor.addEventListener("click", function () {
    saveEditorFile();
  });

  els.btnClearLog.addEventListener("click", clearLogView);

  els.optLogWrap.addEventListener("change", applyLogWrap);

  if (els.optLogHighlight) {
    var hlStored = localStorage.getItem(STORAGE_LOG_HIGHLIGHT);
    els.optLogHighlight.checked = hlStored === "1";
    els.optLogHighlight.addEventListener("change", function () {
      localStorage.setItem(
        STORAGE_LOG_HIGHLIGHT,
        els.optLogHighlight.checked ? "1" : "0"
      );
      rebuildLogViewFromBuffer();
    });
  }

  els.btnLogFontMinus.addEventListener("click", function () {
    logFontPx = Math.max(10, logFontPx - 1);
    applyLogFont();
  });
  els.btnLogFontPlus.addEventListener("click", function () {
    logFontPx = Math.min(22, logFontPx + 1);
    applyLogFont();
  });

  els.btnStopRun.addEventListener("click", async function () {
    if (
      !window.confirm(
        "Stop this run? The batch may leave partial files on disk (download state, pointers). You can re-run or clean up manually."
      )
    ) {
      return;
    }
    var r = await fetch("/api/run/stop", { method: "POST" });
    if (r.status === 409) {
      appendLogLine("[console] Stop: " + (await r.text()));
      return;
    }
    if (!r.ok) {
      appendLogLine("[console] Stop failed: " + r.status);
    }
  });

  els.btnCopyRunId.addEventListener("click", function () {
    var id = els.runMetaId.textContent;
    if (!id || id === "—") {
      return;
    }
    navigator.clipboard.writeText(id).catch(function () {});
  });

  els.runBtns.forEach(function (btn) {
    btn.addEventListener("click", async function () {
      const job = btn.getAttribute("data-job");
      const body = {
        job: job,
        dry_run: els.optDry.checked,
        skip_pip_update: els.optSkipPip.checked,
        skip_ytdlp_update: els.optSkipYtdlp.checked,
      };
      const r = await fetch("/api/run/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (r.status === 409) {
        appendLogLine("[console] " + (await r.text()));
        return;
      }
      if (!r.ok) {
        appendLogLine("[console] start failed: " + r.status);
        return;
      }
    });
  });

  els.btnExplorer.addEventListener("click", async function () {
    var path = selectedRel || filePath;
    if (!path) {
      return;
    }
    filesExplorerSetMessage("Opening…");
    var r = await fetch("/api/files/open-explorer", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path: path }),
    });
    if (r.ok) {
      filesExplorerSetMessage("Launched Windows Explorer.");
      window.setTimeout(function () {
        filesExplorerSetMessage("");
      }, 4000);
      return;
    }
    var msg = "Could not open Explorer (" + r.status + ").";
    try {
      var ej = await r.json();
      if (ej.detail) {
        msg =
          typeof ej.detail === "string"
            ? ej.detail
            : JSON.stringify(ej.detail);
      }
    } catch {
      try {
        msg = (await r.text()) || msg;
      } catch {
        /* ignore */
      }
    }
    filesExplorerSetMessage(msg);
  });

  els.btnSaveSettings.addEventListener("click", async function () {
    els.settingsMsg.textContent = "";
    const prefixes = els.setAllow.value
      .split(",")
      .map(function (s) {
        return s.trim();
      })
      .filter(Boolean);
    var body = {
      port: Number(els.setPort.value),
      allowlisted_rel_prefixes: prefixes,
    };
    if (els.setEditorBackupMax) {
      body.editor_backup_max = Number(els.setEditorBackupMax.value);
    }
    const r = await fetch("/api/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!r.ok) {
      els.settingsMsg.textContent = "Save failed.";
      return;
    }
    els.settingsMsg.textContent =
      "Saved. Restart the console if you changed the port.";
  });

  function storageRetentionPayloadFromForm() {
    return {
      retention_days: Number(els.setRetentionDays && els.setRetentionDays.value),
      prune_archive_runs: !!(els.optPruneArchiveRuns && els.optPruneArchiveRuns.checked),
      prune_operator_backup_zips: !!(
        els.optPruneOperatorZips && els.optPruneOperatorZips.checked
      ),
    };
  }

  if (els.btnSaveRetention) {
    els.btnSaveRetention.addEventListener("click", async function () {
      if (els.storageCleanupMsg) {
        els.storageCleanupMsg.textContent = "";
      }
      var pl = storageRetentionPayloadFromForm();
      if (!pl.retention_days || pl.retention_days < 1) {
        if (els.storageCleanupMsg) {
          els.storageCleanupMsg.textContent = "Retention days must be at least 1.";
        }
        return;
      }
      var r = await fetch("/api/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ storage_retention: pl }),
      });
      if (!r.ok) {
        if (els.storageCleanupMsg) {
          els.storageCleanupMsg.textContent = "Save failed.";
        }
        return;
      }
      if (els.storageCleanupMsg) {
        els.storageCleanupMsg.textContent = "Retention preferences saved.";
      }
    });
  }

  if (els.btnStorageCleanupPreview) {
    els.btnStorageCleanupPreview.addEventListener("click", async function () {
      if (els.storageCleanupMsg) {
        els.storageCleanupMsg.textContent = "Preview…";
      }
      var pl = storageRetentionPayloadFromForm();
      if (!pl.retention_days || pl.retention_days < 1) {
        if (els.storageCleanupMsg) {
          els.storageCleanupMsg.textContent = "Retention days must be at least 1.";
        }
        return;
      }
      var r = await fetch("/api/settings/storage-cleanup/preview", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(pl),
      });
      var j = null;
      try {
        j = await r.json();
      } catch {
        j = null;
      }
      if (!r.ok) {
        lastStorageCleanupPreview = null;
        if (els.storageCleanupMsg) {
          els.storageCleanupMsg.textContent =
            (j && j.detail) ||
            "Preview failed (" + r.status + ").";
        }
        if (els.storageCleanupPreview) {
          els.storageCleanupPreview.hidden = true;
        }
        return;
      }
      lastStorageCleanupPreview = j;
      var ar = j.categories && j.categories.archive_runs;
      var oz = j.categories && j.categories.operator_zips;
      var n1 = ar ? ar.count : 0;
      var n2 = oz ? oz.count : 0;
      var b1 = ar ? ar.bytes : 0;
      var b2 = oz ? oz.bytes : 0;
      var mb = ((b1 + b2) / (1024 * 1024)).toFixed(2);
      if (els.storageCleanupMsg) {
        els.storageCleanupMsg.textContent =
          "Candidates: " +
          n1 +
          " run folder(s), " +
          n2 +
          " ZIP(s); ~" +
          mb +
          " MiB total. Skipped pointer-protected: " +
          (j.skipped_protected_pointer || 0) +
          "; skipped active-run protected: " +
          (j.skipped_active_run || 0) +
          ".";
      }
      if (els.storageCleanupPreview) {
        els.storageCleanupPreview.hidden = false;
        els.storageCleanupPreview.textContent = JSON.stringify(j, null, 2);
      }
    });
  }

  if (els.btnStorageCleanupRun) {
    els.btnStorageCleanupRun.addEventListener("click", async function () {
      if (els.storageCleanupMsg) {
        els.storageCleanupMsg.textContent = "";
      }
      var pl = storageRetentionPayloadFromForm();
      if (!pl.retention_days || pl.retention_days < 1) {
        if (els.storageCleanupMsg) {
          els.storageCleanupMsg.textContent = "Retention days must be at least 1.";
        }
        return;
      }
      var j0 = lastStorageCleanupPreview;
      var nTotal = 0;
      var mb = "0";
      if (j0 && j0.categories) {
        var ar0 = j0.categories.archive_runs;
        var oz0 = j0.categories.operator_zips;
        nTotal = (ar0 ? ar0.count : 0) + (oz0 ? oz0.count : 0);
        var bt =
          (ar0 ? ar0.bytes : 0) + (oz0 ? oz0.bytes : 0);
        mb = (bt / (1024 * 1024)).toFixed(2);
      }
      if (
        !window.confirm(
          "Delete " +
            nTotal +
            " item(s), about " +
            mb +
            " MiB? This cannot be undone. Run folder pointers may be cleared if targets were missing."
        )
      ) {
        return;
      }
      var r = await fetch("/api/settings/storage-cleanup/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(
          Object.assign({ confirm: true }, pl),
        ),
      });
      var j = null;
      try {
        j = await r.json();
      } catch {
        j = null;
      }
      if (r.status === 409) {
        if (els.storageCleanupMsg) {
          els.storageCleanupMsg.textContent =
            (j && j.detail) || "Cannot cleanup while a job is running.";
        }
        return;
      }
      if (!r.ok) {
        if (els.storageCleanupMsg) {
          els.storageCleanupMsg.textContent =
            (j && j.detail) || "Cleanup failed (" + r.status + ").";
        }
        return;
      }
      if (els.storageCleanupMsg) {
        els.storageCleanupMsg.textContent =
          "Deleted " +
          (j.deleted_count || 0) +
          " item(s); freed ~" +
          ((j.bytes_freed || 0) / (1024 * 1024)).toFixed(2) +
          " MiB in " +
          (j.duration_s || 0) +
          "s. Pointers repaired: " +
          (j.pointers_cleared || 0) +
          ".";
      }
      lastStorageCleanupPreview = null;
      if (els.storageCleanupPreview) {
        els.storageCleanupPreview.hidden = false;
        els.storageCleanupPreview.textContent = JSON.stringify(j, null, 2);
      }
    });
  }

  if (els.btnSaveBackupSettings) {
    els.btnSaveBackupSettings.addEventListener("click", async function () {
      if (els.operatorBackupMsg) {
        els.operatorBackupMsg.textContent = "";
      }
      var extra = (els.setBackupExtraPrefixes.value || "")
        .split(",")
        .map(function (s) {
          return s.trim();
        })
        .filter(Boolean);
      var r = await fetch("/api/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          operator_backup: {
            destination_rel: els.setBackupDest.value.trim(),
            include_state_json: !!els.setBackupIncState.checked,
            include_logs_dir: !!els.setBackupIncLogs.checked,
            include_extra_rel_prefixes: extra,
            retention_max_files: Number(els.setBackupRetentionFiles.value),
            retention_days: Number(els.setBackupRetentionDays.value),
          },
        }),
      });
      if (!r.ok) {
        if (els.operatorBackupMsg) {
          els.operatorBackupMsg.textContent = "Save failed.";
        }
        return;
      }
      if (els.operatorBackupMsg) {
        els.operatorBackupMsg.textContent = "Backup options saved.";
      }
    });
  }

  if (els.btnRunOperatorBackup) {
    els.btnRunOperatorBackup.addEventListener("click", async function () {
      if (els.operatorBackupMsg) {
        els.operatorBackupMsg.textContent = "Running backup…";
      }
      var r = await fetch("/api/settings/operator-backup/run", {
        method: "POST",
      });
      var j = null;
      try {
        j = await r.json();
      } catch {
        j = null;
      }
      if (!r.ok) {
        var det =
          j && j.detail
            ? typeof j.detail === "string"
              ? j.detail
              : JSON.stringify(j.detail)
            : "Backup failed (" + r.status + ").";
        if (els.operatorBackupMsg) {
          els.operatorBackupMsg.textContent = det;
        }
        return;
      }
      renderLastOperatorBackup(j);
      if (els.operatorBackupMsg) {
        els.operatorBackupMsg.textContent = j.success
          ? "Backup completed."
          : "Backup finished with errors.";
      }
    });
  }

  if (els.btnAddSchedule) {
    els.btnAddSchedule.addEventListener("click", function () {
      var cur = collectSchedulesFromForm();
      cur.push({
        id: "sch_" + Date.now(),
        job: settingsJobsCache[0] || "watch_later",
        day_of_month: 1,
        hour: 3,
        minute: 0,
        enabled: false,
      });
      renderScheduleEditor(cur, [], settingsJobsCache);
    });
  }

  if (els.btnSaveSchedules) {
    els.btnSaveSchedules.addEventListener("click", async function () {
      if (els.scheduleSaveMsg) {
        els.scheduleSaveMsg.textContent = "";
      }
      var rows = collectSchedulesFromForm();
      var r = await fetch("/api/settings/schedules", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ schedules: rows }),
      });
      if (!r.ok) {
        var tx = await r.text();
        if (els.scheduleSaveMsg) {
          els.scheduleSaveMsg.textContent = "Save failed: " + r.status + " " + tx;
        }
        return;
      }
      await loadSettingsForm();
      if (els.scheduleSaveMsg) {
        els.scheduleSaveMsg.textContent = "Schedules saved.";
      }
    });
  }

  if (els.btnSaveCookieSettings) {
    els.btnSaveCookieSettings.addEventListener("click", async function () {
      if (els.cookieSettingsMsg) {
        els.cookieSettingsMsg.textContent = "";
      }
      var r = await fetch("/api/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          cookie_hygiene: {
            remind_interval_days: Number(els.setCookieRemindDays.value),
            last_acknowledged_unix: lastCookieHygiene.last_acknowledged_unix || 0,
            snooze_until_unix: lastCookieHygiene.snooze_until_unix || 0,
          },
          pre_run_reminder: {
            minutes_before: Number(els.setPreRunMinutes && els.setPreRunMinutes.value),
            snooze_until_unix: lastPreRunReminder.snooze_until_unix || 0,
            acknowledged_fire_key: lastPreRunReminder.acknowledged_fire_key || "",
          },
        }),
      });
      if (!r.ok) {
        if (els.cookieSettingsMsg) {
          els.cookieSettingsMsg.textContent = "Save failed.";
        }
        return;
      }
      await loadSettingsForm();
      if (els.cookieSettingsMsg) {
        els.cookieSettingsMsg.textContent = "Cookie reminder settings saved.";
      }
    });
  }

  function postCookieAck(snoozeDays) {
    return postCookieHygieneAction({
      snoozeDays: snoozeDays || 0,
      snoozeMinutes: 0,
    });
  }

  if (els.btnCookieAck) {
    els.btnCookieAck.addEventListener("click", async function () {
      var r = await postCookieHygieneAction({});
      if (!r.ok) {
        if (els.cookieSettingsMsg) {
          els.cookieSettingsMsg.textContent = "Ack failed.";
        }
        return;
      }
      await loadSettingsForm();
      await refreshCookieReminder();
    });
  }

  if (els.btnCookieSnooze) {
    els.btnCookieSnooze.addEventListener("click", async function () {
      var r = await postCookieHygieneAction({ snoozeDays: 7 });
      if (!r.ok) {
        if (els.cookieSettingsMsg) {
          els.cookieSettingsMsg.textContent = "Snooze failed.";
        }
        return;
      }
      await loadSettingsForm();
      await refreshCookieReminder();
    });
  }

  if (els.btnCookieBannerAck) {
    els.btnCookieBannerAck.addEventListener("click", async function () {
      setReminderActionBusy(true);
      showReminderError("");
      try {
        var r = await postCookieHygieneAction({});
        if (!r.ok) {
          showReminderError("Could not save acknowledgment. Try again.");
          return;
        }
        await syncCookieHygieneFromServer();
        await refreshReminders();
      } finally {
        setReminderActionBusy(false);
      }
    });
  }

  if (els.btnCookieBannerSnooze15) {
    els.btnCookieBannerSnooze15.addEventListener("click", async function () {
      setReminderActionBusy(true);
      showReminderError("");
      try {
        var r = await postCookieHygieneAction({ snoozeMinutes: 15 });
        if (!r.ok) {
          showReminderError("Could not save snooze. Try again.");
          return;
        }
        await syncCookieHygieneFromServer();
        await refreshReminders();
      } finally {
        setReminderActionBusy(false);
      }
    });
  }

  async function syncPreRunReminderState() {
    try {
      var r = await fetch("/api/settings");
      if (!r.ok) {
        return;
      }
      var j = await r.json();
      var prs = j.pre_run_reminder_settings || {};
      lastPreRunReminder.snooze_until_unix = prs.snooze_until_unix || 0;
      lastPreRunReminder.acknowledged_fire_key = prs.acknowledged_fire_key || "";
    } catch {
      /* ignore */
    }
  }

  async function postPreRunAction(body) {
    return fetch("/api/settings/pre-run-reminder/action", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  }

  if (els.btnPreRunAck) {
    els.btnPreRunAck.addEventListener("click", async function () {
      setReminderActionBusy(true);
      showReminderError("");
      try {
        var r = await postPreRunAction({ ack: true, snooze_minutes: 0 });
        if (!r.ok) {
          showReminderError("Could not update scheduled-run reminder.");
          return;
        }
        await syncPreRunReminderState();
        await refreshReminders();
      } finally {
        setReminderActionBusy(false);
      }
    });
  }

  if (els.btnPreRunSnooze) {
    els.btnPreRunSnooze.addEventListener("click", async function () {
      setReminderActionBusy(true);
      showReminderError("");
      try {
        var r = await postPreRunAction({ ack: false, snooze_minutes: 15 });
        if (!r.ok) {
          showReminderError("Could not snooze scheduled-run reminder.");
          return;
        }
        await syncPreRunReminderState();
        await refreshReminders();
      } finally {
        setReminderActionBusy(false);
      }
    });
  }

  if (els.btnSaveDownloadDirs) {
    els.btnSaveDownloadDirs.addEventListener("click", async function () {
      if (els.downloadDirsMsg) {
        els.downloadDirsMsg.textContent = "";
      }
      setDownloadDirsActionsDisabled(true);
      try {
        var r = await fetch("/api/settings", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            download_dirs: collectDownloadDirsPayload(),
          }),
        });
        if (!r.ok) {
          var tx = await r.text();
          if (els.downloadDirsMsg) {
            els.downloadDirsMsg.textContent = "Save failed: " + r.status + " " + tx;
          }
          return;
        }
        await loadDownloadDirsForm();
        if (els.downloadDirsMsg) {
          els.downloadDirsMsg.textContent = "Output folders saved.";
        }
      } finally {
        setDownloadDirsActionsDisabled(false);
      }
    });
  }

  connectStream();
  window.setInterval(refreshReminders, 120000);
  refreshReminders();
  var initialView = getInitialViewFromUrl();
  activateView(initialView);
  if (initialView === "inputs") {
    loadDownloadDirsForm();
  }
  if (initialView === "settings") {
    loadSettingsForm();
  }
  loadRunOverview();
  applyLogFont();
  applyLogWrap();
  scrollHistorySectionFromUrl();
  initFilesSplitResizer();
  fetch("/api/run/status")
    .then(function (r) {
      return r.json();
    })
    .then(function (j) {
      if (j.phase) {
        setPhase(j.phase);
      }
      renderRunPanel(j);
      if (j.phase === "running") {
        disableRunButtons(true);
        editorJobRunning = true;
        setEditorRunning(true);
      } else {
        editorJobRunning = false;
        setEditorRunning(false);
      }
    });

})();
