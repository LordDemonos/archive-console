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

  /**
   * Parse yt-dlp / aria2-ish progress from one log line.
   * Rejects stray "%" in video titles on [download] Destination: paths (e.g. "1% of the time").
   * @returns {{ kind: "noop" } | { kind: "indeterminate" } | { kind: "determinate"; pct: number }}
   */
  function parseLogLineProgress(text) {
    var s = String(text);
    var ytdlpStd = /\[download\]\s+(\d+\.?\d*)%\s+of\b/i.exec(s);
    if (ytdlpStd) {
      var p0 = parseFloat(ytdlpStd[1]);
      if (!isFinite(p0)) {
        return { kind: "noop" };
      }
      return {
        kind: "determinate",
        pct: Math.min(100, Math.max(0, p0)),
      };
    }
    var ytdlpTqdm = /\[download\]\s+(\d+\.?\d*)%\s*\|/.exec(s);
    if (ytdlpTqdm) {
      var p1 = parseFloat(ytdlpTqdm[1]);
      if (!isFinite(p1)) {
        return { kind: "noop" };
      }
      return {
        kind: "determinate",
        pct: Math.min(100, Math.max(0, p1)),
      };
    }
    if (/\[download\]/i.test(s) && /\[#/i.test(s)) {
      if (/\b0B\/0B\b/i.test(s) || /\b0\.0B\/0\.0B\b/i.test(s)) {
        return { kind: "indeterminate" };
      }
      var ariaParen = /\((\d+\.?\d*)%\)/.exec(s);
      if (ariaParen) {
        var p2 = parseFloat(ariaParen[1]);
        if (isFinite(p2)) {
          return {
            kind: "determinate",
            pct: Math.min(100, Math.max(0, p2)),
          };
        }
      }
      var ariaBytes =
        /\[#[^\]]+\s+([0-9.]+)\s*([KMGTPEZY]?i?B)\s*\/\s*([0-9.]+)\s*([KMGTPEZY]?i?B)/i.exec(
          s
        );
      if (ariaBytes) {
        var uA = (ariaBytes[2] || "").toLowerCase();
        var uB = (ariaBytes[4] || "").toLowerCase();
        var numB = parseFloat(ariaBytes[1]);
        var denB = parseFloat(ariaBytes[3]);
        if (uA === uB && denB > 0 && isFinite(numB) && isFinite(denB)) {
          return {
            kind: "determinate",
            pct: Math.min(100, Math.max(0, (numB / denB) * 100)),
          };
        }
        if ((!isFinite(denB) || denB <= 0) && numB <= 0) {
          return { kind: "indeterminate" };
        }
      }
    }
    if (/^\s*\[#/.test(s)) {
      if (/\b0B\/0B\b/i.test(s) || /\b0\.0B\/0\.0B\b/i.test(s)) {
        return { kind: "indeterminate" };
      }
      var ap2 = /\((\d+\.?\d*)%\)/.exec(s);
      if (ap2) {
        var p3 = parseFloat(ap2[1]);
        if (isFinite(p3)) {
          return {
            kind: "determinate",
            pct: Math.min(100, Math.max(0, p3)),
          };
        }
      }
    }
    return { kind: "noop" };
  }

  function applyParsedProgressToRow(hintEl, fillEl, trackEl, rawLine, parsed) {
    if (!hintEl || parsed.kind === "noop") {
      return;
    }
    var disp =
      rawLine.length > 160 ? rawLine.slice(0, 157) + "…" : rawLine;
    hintEl.textContent = disp;
    if (!fillEl || !trackEl) {
      return;
    }
    if (parsed.kind === "indeterminate") {
      fillEl.style.removeProperty("width");
      fillEl.style.removeProperty("margin-left");
      trackEl.classList.add("log-progress-bar-track--indeterminate");
      trackEl.setAttribute("aria-busy", "true");
      trackEl.removeAttribute("aria-valuenow");
      trackEl.setAttribute("aria-valuetext", "Total size unknown; downloading");
      return;
    }
    trackEl.classList.remove("log-progress-bar-track--indeterminate");
    trackEl.removeAttribute("aria-busy");
    trackEl.setAttribute("aria-valuenow", String(Math.round(parsed.pct)));
    trackEl.setAttribute("aria-valuetext", String(Math.round(parsed.pct)) + " percent");
    fillEl.style.marginLeft = "";
    fillEl.style.width = parsed.pct + "%";
  }

  function updateLastProgressFromLine(text) {
    try {
      if (!els.logProgressHint) {
        return;
      }
      var s = String(text);
      applyParsedProgressToRow(
        els.logProgressHint,
        els.logProgressFill,
        els.logProgressTrack,
        s,
        parseLogLineProgress(s)
      );
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
      els.logProgressFill.style.marginLeft = "";
    }
    if (els.logProgressTrack) {
      els.logProgressTrack.classList.remove(
        "log-progress-bar-track--indeterminate"
      );
      els.logProgressTrack.removeAttribute("aria-busy");
      els.logProgressTrack.removeAttribute("aria-valuenow");
      els.logProgressTrack.removeAttribute("aria-valuetext");
    }
  }

  function updateOneoffProgressFromLine(text) {
    try {
      if (!els.oneoffLogProgressHint) {
        return;
      }
      var s2 = String(text);
      applyParsedProgressToRow(
        els.oneoffLogProgressHint,
        els.oneoffLogProgressFill,
        els.oneoffLogProgressTrack,
        s2,
        parseLogLineProgress(s2)
      );
    } catch (e) {
      /* ignore */
    }
  }

  function resetOneoffLogProgressHint() {
    if (els.oneoffLogProgressHint) {
      els.oneoffLogProgressHint.textContent = "—";
    }
    if (els.oneoffLogProgressFill) {
      els.oneoffLogProgressFill.style.width = "0%";
      els.oneoffLogProgressFill.style.marginLeft = "";
    }
    if (els.oneoffLogProgressTrack) {
      els.oneoffLogProgressTrack.classList.remove(
        "log-progress-bar-track--indeterminate"
      );
      els.oneoffLogProgressTrack.removeAttribute("aria-busy");
      els.oneoffLogProgressTrack.removeAttribute("aria-valuenow");
      els.oneoffLogProgressTrack.removeAttribute("aria-valuetext");
    }
  }

  function appendOneoffLogLine(text) {
    if (!els.oneoffLogBody || !els.oneoffLogGutter) {
      return;
    }
    var t = text != null ? String(text) : "";
    oneoffLogLinesBuffer.push(t);
    oneoffLogLineCount += 1;
    els.oneoffLogGutter.appendChild(
      document.createTextNode(oneoffLogLineCount + "\n")
    );
    var hi = els.optOneoffLogHighlight && els.optOneoffLogHighlight.checked;
    if (!hi) {
      els.oneoffLogBody.appendChild(document.createTextNode(t + "\n"));
    } else {
      var span = document.createElement("span");
      span.className = classifyLogLine(t);
      span.textContent = t;
      els.oneoffLogBody.appendChild(span);
      els.oneoffLogBody.appendChild(document.createTextNode("\n"));
    }
    updateOneoffProgressFromLine(t);
    if (els.optOneoffStick && els.optOneoffStick.checked && els.oneoffLogFrame) {
      els.oneoffLogFrame.scrollTop = els.oneoffLogFrame.scrollHeight;
    }
  }

  function appendGalleryLogLine(text) {
    if (!els.galleryLogBody || !els.galleryLogGutter) {
      return;
    }
    var tg = text != null ? String(text) : "";
    galleryLogLinesBuffer.push(tg);
    galleryLogLineCount += 1;
    els.galleryLogGutter.appendChild(
      document.createTextNode(galleryLogLineCount + "\n")
    );
    var hig =
      els.optGalleryLogHighlight && els.optGalleryLogHighlight.checked;
    if (!hig) {
      els.galleryLogBody.appendChild(document.createTextNode(tg + "\n"));
    } else {
      var sg = document.createElement("span");
      sg.className = classifyLogLine(tg);
      sg.textContent = tg;
      els.galleryLogBody.appendChild(sg);
      els.galleryLogBody.appendChild(document.createTextNode("\n"));
    }
    if (
      els.optGalleryStickBottom &&
      els.optGalleryStickBottom.checked &&
      els.galleryLogFrame
    ) {
      els.galleryLogFrame.scrollTop = els.galleryLogFrame.scrollHeight;
    }
  }

  function appendStreamLine(text) {
    if (activeStreamJob === "oneoff") {
      appendOneoffLogLine(text);
    } else if (activeStreamJob === "galleries") {
      appendGalleryLogLine(text);
    } else {
      appendLogLine(text);
    }
  }

  function clearOneoffLogView() {
    oneoffLogLineCount = 0;
    oneoffLogLinesBuffer = [];
    if (els.oneoffLogGutter) {
      els.oneoffLogGutter.textContent = "";
    }
    if (els.oneoffLogBody) {
      els.oneoffLogBody.textContent = "";
    }
    resetOneoffLogProgressHint();
  }

  function clearGalleryLogView() {
    galleryLogLineCount = 0;
    galleryLogLinesBuffer = [];
    if (els.galleryLogGutter) {
      els.galleryLogGutter.textContent = "";
    }
    if (els.galleryLogBody) {
      els.galleryLogBody.textContent = "";
    }
  }

  function rebuildGalleryLogViewFromBuffer() {
    if (!els.galleryLogGutter || !els.galleryLogBody) {
      return;
    }
    galleryLogLineCount = 0;
    els.galleryLogGutter.textContent = "";
    els.galleryLogBody.textContent = "";
    var hig2 =
      els.optGalleryLogHighlight && els.optGalleryLogHighlight.checked;
    for (var gi = 0; gi < galleryLogLinesBuffer.length; gi++) {
      galleryLogLineCount += 1;
      els.galleryLogGutter.appendChild(
        document.createTextNode(String(galleryLogLineCount) + "\n")
      );
      var gt = galleryLogLinesBuffer[gi];
      if (!hig2) {
        els.galleryLogBody.appendChild(document.createTextNode(gt + "\n"));
      } else {
        var spg = document.createElement("span");
        spg.className = classifyLogLine(gt);
        spg.textContent = gt;
        els.galleryLogBody.appendChild(spg);
        els.galleryLogBody.appendChild(document.createTextNode("\n"));
      }
    }
    if (
      els.optGalleryStickBottom &&
      els.optGalleryStickBottom.checked &&
      els.galleryLogFrame
    ) {
      els.galleryLogFrame.scrollTop = els.galleryLogFrame.scrollHeight;
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
    for (var ir = logLinesBuffer.length - 1; ir >= 0; ir--) {
      var pr = parseLogLineProgress(logLinesBuffer[ir]);
      if (pr.kind !== "noop") {
        applyParsedProgressToRow(
          els.logProgressHint,
          els.logProgressFill,
          els.logProgressTrack,
          logLinesBuffer[ir],
          pr
        );
        break;
      }
    }
  }

  function rebuildOneoffLogViewFromBuffer() {
    if (!els.oneoffLogGutter || !els.oneoffLogBody) {
      return;
    }
    oneoffLogLineCount = 0;
    els.oneoffLogGutter.textContent = "";
    els.oneoffLogBody.textContent = "";
    var hi2 = els.optOneoffLogHighlight && els.optOneoffLogHighlight.checked;
    for (var j = 0; j < oneoffLogLinesBuffer.length; j++) {
      oneoffLogLineCount += 1;
      els.oneoffLogGutter.appendChild(
        document.createTextNode(String(oneoffLogLineCount) + "\n")
      );
      var t2 = oneoffLogLinesBuffer[j];
      if (!hi2) {
        els.oneoffLogBody.appendChild(document.createTextNode(t2 + "\n"));
      } else {
        var span2 = document.createElement("span");
        span2.className = classifyLogLine(t2);
        span2.textContent = t2;
        els.oneoffLogBody.appendChild(span2);
        els.oneoffLogBody.appendChild(document.createTextNode("\n"));
      }
    }
    if (els.optOneoffStick && els.optOneoffStick.checked && els.oneoffLogFrame) {
      els.oneoffLogFrame.scrollTop = els.oneoffLogFrame.scrollHeight;
    }
    for (var io = oneoffLogLinesBuffer.length - 1; io >= 0; io--) {
      var po = parseLogLineProgress(oneoffLogLinesBuffer[io]);
      if (po.kind !== "noop") {
        applyParsedProgressToRow(
          els.oneoffLogProgressHint,
          els.oneoffLogProgressFill,
          els.oneoffLogProgressTrack,
          oneoffLogLinesBuffer[io],
          po
        );
        break;
      }
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
    logProgressTrack: document.getElementById("logProgressTrack"),
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
    filesWorkspace: document.getElementById("filesWorkspace"),
    filesWorkspaceShell: document.getElementById("filesWorkspaceShell"),
    filesWorkspaceResizeY: document.getElementById("filesWorkspaceResizeY"),
    fileCrumb: document.getElementById("fileBreadcrumb"),
    btnExplorer: document.getElementById("btnExplorer"),
    fileExplorerMsg: document.getElementById("fileExplorerMsg"),
    filesSplit: document.getElementById("filesSplit"),
    filesSplitHandle: document.getElementById("filesSplitHandle"),
    filesVideo: document.getElementById("filesVideo"),
    filesVideoFrame: document.getElementById("filesVideoFrame"),
    filesMediaStage: document.getElementById("filesMediaStage"),
    filesImageA: document.getElementById("filesImageA"),
    filesImageB: document.getElementById("filesImageB"),
    filesPlayerStageMeta: document.getElementById("filesPlayerStageMeta"),
    filesPlayerStageMetaInner: document.getElementById("filesPlayerStageMetaInner"),
    filesPlayerFsHud: document.getElementById("filesPlayerFsHud"),
    filesPlayerFsPrev: document.getElementById("filesPlayerFsPrev"),
    filesPlayerFsNext: document.getElementById("filesPlayerFsNext"),
    filesPlayerFsPause: document.getElementById("filesPlayerFsPause"),
    filesPlayerFsOverlay: document.getElementById("filesPlayerFsOverlay"),
    filesPlayerFsExit: document.getElementById("filesPlayerFsExit"),
    filesPlayerSlideshowTimed: document.getElementById("filesPlayerSlideshowTimed"),
    filesPlayerSlideshowInterval: document.getElementById("filesPlayerSlideshowInterval"),
    filesPlayerTransition: document.getElementById("filesPlayerTransition"),
    filesPlayerFullscreen: document.getElementById("filesPlayerFullscreen"),
    filesPlayerOverlayToggle: document.getElementById("filesPlayerOverlayToggle"),
    filesPlayer: document.getElementById("filesPlayer"),
    filesPlayerToast: document.getElementById("filesPlayerToast"),
    filesPlayerShuffle: document.getElementById("filesPlayerShuffle"),
    filesPlayerLoop: document.getElementById("filesPlayerLoop"),
    filesPlayerPlay: document.getElementById("filesPlayerPlay"),
    filesPlayerPrev: document.getElementById("filesPlayerPrev"),
    filesPlayerNext: document.getElementById("filesPlayerNext"),
    filesPlayerNowText: document.getElementById("filesPlayerNowText"),
    filesPlayerNextWrap: document.getElementById("filesPlayerNextWrap"),
    filesPlayerNextText: document.getElementById("filesPlayerNextText"),
    filesPlayerStats: document.getElementById("filesPlayerStats"),
    filesPlayerAddFile: document.getElementById("filesPlayerAddFile"),
    filesPlayerAddFolder: document.getElementById("filesPlayerAddFolder"),
    filesPlayerRemove: document.getElementById("filesPlayerRemove"),
    filesPlayerClear: document.getElementById("filesPlayerClear"),
    filesPlayerMsg: document.getElementById("filesPlayerMsg"),
    filesPlayerError: document.getElementById("filesPlayerError"),
    filesPlayerQueue: document.getElementById("filesPlayerQueue"),
    btnLibraryQueueRename: document.getElementById("btnLibraryQueueRename"),
    renameQueueBody: document.getElementById("renameQueueBody"),
    renameQueueEmpty: document.getElementById("renameQueueEmpty"),
    renameQueueTable: document.getElementById("renameQueueTable"),
    btnRenameAddFromLibrary: document.getElementById("btnRenameAddFromLibrary"),
    btnRenameClearQueue: document.getElementById("btnRenameClearQueue"),
    optRenameUseDeepl: document.getElementById("optRenameUseDeepl"),
    optRenameUseExif: document.getElementById("optRenameUseExif"),
    selRenamePipelineOrder: document.getElementById("selRenamePipelineOrder"),
    inpRenameExifTemplate: document.getElementById("inpRenameExifTemplate"),
    selRenameExifMissing: document.getElementById("selRenameExifMissing"),
    optRenameWholeBasename: document.getElementById("optRenameWholeBasename"),
    optRenamePreserveYt: document.getElementById("optRenamePreserveYt"),
    optRenamePreserveBrackets: document.getElementById("optRenamePreserveBrackets"),
    btnRenamePreview: document.getElementById("btnRenamePreview"),
    btnRenameApply: document.getElementById("btnRenameApply"),
    renameMsg: document.getElementById("renameMsg"),
    renameUsageLine: document.getElementById("renameUsageLine"),
    renamePreviewBody: document.getElementById("renamePreviewBody"),
    renameLogBody: document.getElementById("renameLogBody"),
    renameLogDetail: document.getElementById("renameLogDetail"),
    setDeeplApiKey: document.getElementById("setDeeplApiKey"),
    optDeeplKeyClear: document.getElementById("optDeeplKeyClear"),
    setDeeplEndpointMode: document.getElementById("setDeeplEndpointMode"),
    setDeeplSourceLang: document.getElementById("setDeeplSourceLang"),
    setDeeplTargetLang: document.getElementById("setDeeplTargetLang"),
    btnSaveDeepLSettings: document.getElementById("btnSaveDeepLSettings"),
    deeplSettingsMsg: document.getElementById("deeplSettingsMsg"),
    reportPointers: document.getElementById("reportPointers"),
    reportRuns: document.getElementById("reportRuns"),
    setPort: document.getElementById("setPort"),
    setAllow: document.getElementById("setAllow"),
    setFfmpegExe: document.getElementById("setFfmpegExe"),
    setMediainfoExe: document.getElementById("setMediainfoExe"),
    setExiftoolExe: document.getElementById("setExiftoolExe"),
    setExiftoolTimeoutSec: document.getElementById("setExiftoolTimeoutSec"),
    setDuplicatesQuarantineRel: document.getElementById("setDuplicatesQuarantineRel"),
    setDuplicatesPreferQuarantine: document.getElementById(
      "setDuplicatesPreferQuarantine"
    ),
    dupRootChecks: document.getElementById("dupRootChecks"),
    btnDupAddCurrentFolder: document.getElementById("btnDupAddCurrentFolder"),
    dupIncludeVideo: document.getElementById("dupIncludeVideo"),
    dupIncludeImages: document.getElementById("dupIncludeImages"),
    btnDupScan: document.getElementById("btnDupScan"),
    dupScanProgress: document.getElementById("dupScanProgress"),
    dupResults: document.getElementById("dupResults"),
    dupPreviewOut: document.getElementById("dupPreviewOut"),
    btnDupPreviewRemove: document.getElementById("btnDupPreviewRemove"),
    btnDupApplyRemove: document.getElementById("btnDupApplyRemove"),
    dupModeQuarantine: document.getElementById("dupModeQuarantine"),
    dupModeDelete: document.getElementById("dupModeDelete"),
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
    setOneoffReportRetentionDays: document.getElementById(
      "setOneoffReportRetentionDays"
    ),
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
    btnCookieSnooze1h: document.getElementById("btnCookieSnooze1h"),
    btnCookieSnooze3h: document.getElementById("btnCookieSnooze3h"),
    setPreRunMinutes: document.getElementById("setPreRunMinutes"),
    cookieSettingsMsg: document.getElementById("cookieSettingsMsg"),
    optRequireCookieConfirm: document.getElementById("optRequireCookieConfirm"),
    optTrayNotifySchedule: document.getElementById("optTrayNotifySchedule"),
    setTrayNotifyPort: document.getElementById("setTrayNotifyPort"),
    trayNotifyFailureLine: document.getElementById("trayNotifyFailureLine"),
    cookieGateModal: document.getElementById("cookieGateModal"),
    cookieGateAck: document.getElementById("cookieGateAck"),
    cookieGateContinue: document.getElementById("cookieGateContinue"),
    cookieGateCancel: document.getElementById("cookieGateCancel"),
    cookieGateBackdrop: document.getElementById("cookieGateBackdrop"),
    shutdownGateModal: document.getElementById("shutdownGateModal"),
    shutdownGateBackdrop: document.getElementById("shutdownGateBackdrop"),
    shutdownGateInput: document.getElementById("shutdownGateInput"),
    shutdownGateToken: document.getElementById("shutdownGateToken"),
    shutdownGateCancel: document.getElementById("shutdownGateCancel"),
    shutdownGateConfirm: document.getElementById("shutdownGateConfirm"),
    shutdownGateBusy: document.getElementById("shutdownGateBusy"),
    btnShutdownServer: document.getElementById("btnShutdownServer"),
    shutdownSettingsMsg: document.getElementById("shutdownSettingsMsg"),
    runCookieGateHint: document.getElementById("runCookieGateHint"),
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
    gallerydlTextarea: document.getElementById("gallerydlTextarea"),
    gallerydlMtime: document.getElementById("gallerydlMtime"),
    gallerydlRelLabel: document.getElementById("gallerydlRelLabel"),
    gallerydlDirtyPill: document.getElementById("gallerydlDirtyPill"),
    gallerydlMsg: document.getElementById("gallerydlMsg"),
    gallerydlSaveHint: document.getElementById("gallerydlSaveHint"),
    btnGallerydlSave: document.getElementById("btnGallerydlSave"),
    btnGallerydlReload: document.getElementById("btnGallerydlReload"),
    gallerydlEmptyState: document.getElementById("gallerydlEmptyState"),
    gallerydlEmptyPath: document.getElementById("gallerydlEmptyPath"),
    linkGalleriesToGallerydl: document.getElementById("linkGalleriesToGallerydl"),
    supportedsitesFilter: document.getElementById("supportedsitesFilter"),
    btnSupportedsitesRefresh: document.getElementById("btnSupportedsitesRefresh"),
    supportedsitesMeta: document.getElementById("supportedsitesMeta"),
    supportedsitesDisclaimer: document.getElementById("supportedsitesDisclaimer"),
    supportedsitesTools: document.getElementById("supportedsitesTools"),
    dlDirWatchLater: document.getElementById("dlDirWatchLater"),
    dlDirChannels: document.getElementById("dlDirChannels"),
    dlDirVideos: document.getElementById("dlDirVideos"),
    dlDirOneoffInputs: document.getElementById("dlDirOneoffInputs"),
    dlDirOneoffPanel: document.getElementById("dlDirOneoffPanel"),
    btnSaveDownloadDirs: document.getElementById("btnSaveDownloadDirs"),
    btnOneoffSaveOutput: document.getElementById("btnOneoffSaveOutput"),
    downloadDirsMsg: document.getElementById("downloadDirsMsg"),
    downloadDirsEffective: document.getElementById("downloadDirsEffective"),
    oneoffUrlInput: document.getElementById("oneoffUrlInput"),
    optOneoffDryRun: document.getElementById("optOneoffDryRun"),
    optOneoffSkipPip: document.getElementById("optOneoffSkipPip"),
    optOneoffSkipYtdlp: document.getElementById("optOneoffSkipYtdlp"),
    btnOneoffStart: document.getElementById("btnOneoffStart"),
    btnOneoffStop: document.getElementById("btnOneoffStop"),
    oneoffStartMsg: document.getElementById("oneoffStartMsg"),
    oneoffOutputEffective: document.getElementById("oneoffOutputEffective"),
    oneoffBrowseMsg: document.getElementById("oneoffBrowseMsg"),
    oneoffRollingSummary: document.getElementById("oneoffRollingSummary"),
    oneoffRollingActions: document.getElementById("oneoffRollingActions"),
    oneoffRollingReportWrap: document.getElementById("oneoffRollingReportWrap"),
    oneoffRollingReportLink: document.getElementById("oneoffRollingReportLink"),
    btnOneoffWatchNow: document.getElementById("btnOneoffWatchNow"),
    oneoffCookieGateHint: document.getElementById("oneoffCookieGateHint"),
    oneoffCookieBanner: document.getElementById("oneoffCookieBanner"),
    btnOneoffCookieBannerAck: document.getElementById("btnOneoffCookieBannerAck"),
    oneoffLogBody: document.getElementById("oneoffLogBody"),
    oneoffLogGutter: document.getElementById("oneoffLogGutter"),
    oneoffLogFrame: document.getElementById("oneoffLogFrame"),
    optOneoffStick: document.getElementById("optOneoffStickBottom"),
    optOneoffLogWrap: document.getElementById("optOneoffLogWrap"),
    optOneoffLogHighlight: document.getElementById("optOneoffLogHighlight"),
    oneoffLogProgressHint: document.getElementById("oneoffLogProgressHint"),
    oneoffLogProgressFill: document.getElementById("oneoffLogProgressFill"),
    oneoffLogProgressTrack: document.getElementById("oneoffLogProgressTrack"),
    btnOneoffClearLog: document.getElementById("btnOneoffClearLog"),
    btnOneoffLogFontMinus: document.getElementById("btnOneoffLogFontMinus"),
    btnOneoffLogFontPlus: document.getElementById("btnOneoffLogFontPlus"),
    galleryUrlInput: document.getElementById("galleryUrlInput"),
    btnGalleryPreview: document.getElementById("btnGalleryPreview"),
    btnGalleryStart: document.getElementById("btnGalleryStart"),
    btnGalleryStop: document.getElementById("btnGalleryStop"),
    btnGallerySaveOutput: document.getElementById("btnGallerySaveOutput"),
    galleryPreviewMsg: document.getElementById("galleryPreviewMsg"),
    galleryDriftNote: document.getElementById("galleryDriftNote"),
    galleryPreviewTableWrap: document.getElementById("galleryPreviewTableWrap"),
    galleryPreviewTbody: document.getElementById("galleryPreviewTbody"),
    galleryOutputEffective: document.getElementById("galleryOutputEffective"),
    galleryBrowseMsg: document.getElementById("galleryBrowseMsg"),
    galleryStartMsg: document.getElementById("galleryStartMsg"),
    galleryCookieGateHint: document.getElementById("galleryCookieGateHint"),
    dlDirGalleriesPanel: document.getElementById("dlDirGalleriesPanel"),
    dlDirGalleriesInputs: document.getElementById("dlDirGalleriesInputs"),
    optGalleryDryRun: document.getElementById("optGalleryDryRun"),
    optGalleryVideoFallback: document.getElementById("optGalleryVideoFallback"),
    optGallerySkipPip: document.getElementById("optGallerySkipPip"),
    optGallerySkipYtdlp: document.getElementById("optGallerySkipYtdlp"),
    galleryLogBody: document.getElementById("galleryLogBody"),
    galleryLogGutter: document.getElementById("galleryLogGutter"),
    galleryLogFrame: document.getElementById("galleryLogFrame"),
    optGalleryStickBottom: document.getElementById("optGalleryStickBottom"),
    optGalleryLogWrap: document.getElementById("optGalleryLogWrap"),
    optGalleryLogHighlight: document.getElementById("optGalleryLogHighlight"),
    btnGalleryClearLog: document.getElementById("btnGalleryClearLog"),
    btnGalleryLogFontMinus: document.getElementById("btnGalleryLogFontMinus"),
    btnGalleryLogFontPlus: document.getElementById("btnGalleryLogFontPlus"),
  };

  const STORAGE_LOG_HIGHLIGHT = "archive_console_log_highlight";

  let logLineCount = 0;
  /** Raw lines for the current stream (rebuild when toggling highlight). */
  let logLinesBuffer = [];
  /** Monthly vs one-off; drives SSE line routing. */
  let activeStreamJob = null;
  let oneoffLogLineCount = 0;
  let oneoffLogLinesBuffer = [];
  let galleryLogLineCount = 0;
  let galleryLogLinesBuffer = [];
  /** @type {{ rows: unknown[], truncated?: boolean, url?: string } | null} */
  let galleryLastPreview = null;
  let logFontPx = 13;
  let oneoffCookieCheckTimer = null;
  let lastOneoffCookieReminderUnix = 0;
  /** Sidebar / URL view id (e.g. run, oneoff); used to suppress duplicate cookie UI. */
  let activeViewId = "run";
  let lastRemindersCookieShowEligible = false;
  let lastRemindersCookieMessage = "";
  let lastRemindersRequireCookieConfirmManual = false;
  let es = null;
  let filePath = "";
  let selectedRel = "";
  /** Abort in-flight MediaInfo fetch when selection changes. */
  let filesMediainfoController = null;
  /** Duplicate finder: last scan groups + allowlist cache. */
  var dupLastGroups = [];
  var dupPollTimer = null;
  var dupAllowlistPrefixes = [];
  var dupManualRoots = [];
  /** Files list: Windows-style multi-select (Ctrl/Meta toggle, Shift range). */
  var filesListSelectedSet = new Set();
  var filesListAnchorIndex = -1;
  /** Rename view: queued relative paths (allowlisted). */
  var renameQueueRels = [];
  var renamePreviewId = null;
  var renameLastPreviewRows = [];
  var renameHistoryItems = [];
  /** Snapshot of current directory rows in list order (for range + folder enqueue). */
  var filesListRowModels = [];

  function filesListApplySelectionVisual() {
    if (!els.fileList) {
      return;
    }
    els.fileList.querySelectorAll("li button").forEach(function (b) {
      var rel = b.dataset.fileRel || "";
      var on = rel && filesListSelectedSet.has(rel);
      b.classList.toggle("is-selected", on);
      b.setAttribute("aria-selected", on ? "true" : "false");
    });
  }

  function filesListPlayableSelectedInOrder() {
    var out = [];
    for (var i = 0; i < filesListRowModels.length; i++) {
      var row = filesListRowModels[i];
      if (!filesListSelectedSet.has(row.rel) || row.is_dir) {
        continue;
      }
      if (filesPlayerIsQueueableRel(row.rel)) {
        out.push(row.rel);
      }
    }
    return out;
  }

  /** Size in bytes from the current directory listing, if this rel is visible. */
  function filesListRowLookupSize(rel) {
    if (!rel) {
      return null;
    }
    for (var i = 0; i < filesListRowModels.length; i++) {
      if (filesListRowModels[i].rel === rel) {
        var z = filesListRowModels[i].ent.size;
        return z != null ? z : null;
      }
    }
    return null;
  }

  function filesPlayerContainerExt(rel) {
    if (!rel) {
      return "";
    }
    var slash = rel.lastIndexOf("/");
    var base = slash >= 0 ? rel.slice(slash + 1) : rel;
    var dot = base.lastIndexOf(".");
    if (dot < 0 || dot === base.length - 1) {
      return "";
    }
    return base.slice(dot + 1).toUpperCase();
  }

  function fpFormatDuration(sec) {
    if (!isFinite(sec) || sec < 0) {
      return "";
    }
    var s = Math.floor(sec % 60);
    var m = Math.floor((sec / 60) % 60);
    var h = Math.floor(sec / 3600);
    var pad2 = function (n) {
      return (n < 10 ? "0" : "") + n;
    };
    if (h > 0) {
      return h + ":" + pad2(m) + ":" + pad2(s);
    }
    return m + ":" + pad2(s);
  }

  function filesListSetSelectionToRange(i0, i1) {
    var a = Math.max(0, Math.min(i0, i1));
    var b = Math.min(filesListRowModels.length - 1, Math.max(i0, i1));
    filesListSelectedSet.clear();
    for (var i = a; i <= b; i++) {
      filesListSelectedSet.add(filesListRowModels[i].rel);
    }
    filesListApplySelectionVisual();
  }

  function filesListSetSelectionSingle(idx, ent) {
    filesListSelectedSet.clear();
    filesListSelectedSet.add(ent.rel);
    filesListAnchorIndex = idx;
    filesListApplySelectionVisual();
    selectFile(ent.rel, ent);
  }

  /** Last allowlisted rolling one-off media rel from GET /api/oneoff/rolling (Watch Now). */
  let oneoffLastMediaRel = "";
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
  const GALLERY_DL_CONF = "gallery-dl.conf";
  let gallerydlBaseline = "";
  let lastSupportedsitesPayload = null;

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
      var primDir = false;
      for (var ei = 0; ei < filesListRowModels.length; ei++) {
        if (
          filesListRowModels[ei].rel === selectedRel &&
          filesListRowModels[ei].is_dir
        ) {
          primDir = true;
          break;
        }
      }
      if (primDir) {
        els.btnExplorer.textContent = "Open folder in Explorer";
        els.btnExplorer.setAttribute(
          "aria-label",
          "Open the selected folder in Windows Explorer"
        );
      } else {
        els.btnExplorer.textContent = "Reveal file in Explorer";
        els.btnExplorer.setAttribute(
          "aria-label",
          "Reveal the selected file in Windows Explorer"
        );
      }
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

  /** Local media player (Library): queue + HTML5 video via allowlisted /reports/file. */
  const LIBRARY_PLAYER_LS = "archive_console_library_player_v1";
  const LEGACY_FILES_PLAYER_LS = "archive_console_files_player_v1";
  const PLAYABLE_EXT = new Set([
    ".mp4",
    ".webm",
    ".mkv",
    ".avi",
    ".mov",
    ".m4v",
    ".wmv",
    ".mp3",
    ".m4a",
    ".opus",
    ".ogg",
    ".wav",
    ".flac",
  ]);
  const SLIDESHOW_IMAGE_EXT = new Set([
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".webp",
  ]);

  function filesPlayerRelExtLower(rel) {
    var s = (rel || "").toLowerCase();
    var dot = s.lastIndexOf(".");
    if (dot < 0) {
      return "";
    }
    return s.slice(dot);
  }

  function filesPlayerIsVideoAudioRel(rel) {
    return PLAYABLE_EXT.has(filesPlayerRelExtLower(rel));
  }

  function filesPlayerIsImageRel(rel) {
    return SLIDESHOW_IMAGE_EXT.has(filesPlayerRelExtLower(rel));
  }

  /** Video, audio, or v1 slideshow image — queue and folder enqueue. */
  function filesPlayerIsQueueableRel(rel) {
    return filesPlayerIsVideoAudioRel(rel) || filesPlayerIsImageRel(rel);
  }

  /** @deprecated use filesPlayerIsQueueableRel */
  function filesPlayerIsPlayableRel(rel) {
    return filesPlayerIsQueueableRel(rel);
  }

  function filesPlayerBasename(rel) {
    var parts = (rel || "").split(/[/\\]/);
    return parts[parts.length - 1] || rel || "";
  }

  var fpBaseQueue = [];
  var fpShuffle = false;
  var fpLoopPlaylist = false;
  var fpPlayOrder = [];
  var fpPlayIndex = -1;
  var fpQueueSel = -1;
  var fpLastLoadedRel = "";
  var libraryClipPollTimer = null;
  var fpSlideshowTimer = null;
  var fpSlideshowTimed = false;
  var fpSlideshowPaused = false;
  /** After a slide shows, which layer is visually front (true = #filesImageA). */
  var fpImageShowingA = true;
  var fpImageErrorSkipCount = 0;
  var fpOverlayVisible = true;
  var fpMetaSizeByRel = Object.create(null);

  function fpCurrentRel() {
    if (fpPlayIndex < 0 || fpPlayIndex >= fpPlayOrder.length) {
      return "";
    }
    return fpPlayOrder[fpPlayIndex];
  }

  function fpUpdatePlayerActionButtons() {
    if (!els.filesPlayerPlay) {
      return;
    }
    var orderedPlay = filesListPlayableSelectedInOrder();
    var selOk =
      orderedPlay.length > 0 ||
      (!!selectedRel && filesPlayerIsQueueableRel(selectedRel));
    var hasQ = fpPlayOrder.length > 0;
    var dirOk = !!filesDirForFolderEnqueue();
    els.filesPlayerPlay.disabled = !selOk && !hasQ;
    if (els.filesPlayerAddFile) {
      els.filesPlayerAddFile.disabled = orderedPlay.length === 0;
      if (orderedPlay.length === 0) {
        els.filesPlayerAddFile.title =
          "Select queueable files: video, audio, or jpg/png/gif/webp (folders: use Add folder).";
      } else {
        els.filesPlayerAddFile.title =
          "Enqueue every selected file, in list order.";
      }
    }
    if (els.filesPlayerAddFolder) {
      els.filesPlayerAddFolder.disabled = !dirOk;
      if (dirOk) {
        var d = filesDirForFolderEnqueue();
        els.filesPlayerAddFolder.title =
          "Add video, audio, and slideshow images in folder only (not subfolders): " + d;
      } else {
        els.filesPlayerAddFolder.title =
          "Open or select a folder row so a target directory is known.";
      }
    }
    if (els.filesPlayerPrev) {
      els.filesPlayerPrev.disabled = !hasQ;
    }
    if (els.filesPlayerNext) {
      els.filesPlayerNext.disabled = !hasQ;
    }
  }

  /**
   * Directory for "Add folder (here)": first selected folder (list order), else cwd, else parent of selected file.
   */
  function filesDirForFolderEnqueue() {
    for (var i = 0; i < filesListRowModels.length; i++) {
      var row = filesListRowModels[i];
      if (filesListSelectedSet.has(row.rel) && row.is_dir) {
        return row.rel;
      }
    }
    if (filePath) {
      return filePath;
    }
    if (selectedRel) {
      var slash = selectedRel.lastIndexOf("/");
      if (slash >= 0) {
        return selectedRel.slice(0, slash);
      }
    }
    return "";
  }

  var fpToastTimer = null;

  function fpToast(msg, isError) {
    if (!msg) {
      return;
    }
    if (els.filesPlayerToast) {
      els.filesPlayerToast.textContent = msg;
      els.filesPlayerToast.hidden = false;
      els.filesPlayerToast.classList.toggle("is-error", msg && !!isError);
      window.clearTimeout(fpToastTimer);
      fpToastTimer = window.setTimeout(function () {
        if (els.filesPlayerToast) {
          els.filesPlayerToast.hidden = true;
        }
      }, isError ? 9000 : 5500);
    }
    fpMsg(msg);
  }

  function fpSave() {
    try {
      localStorage.setItem(
        LIBRARY_PLAYER_LS,
        JSON.stringify({
          v: 3,
          baseQueue: fpBaseQueue,
          shuffle: fpShuffle,
          loopPlaylist: fpLoopPlaylist,
          currentRel: fpCurrentRel() || "",
          slideshowTimed: fpSlideshowTimed,
          slideshowPaused: fpSlideshowPaused,
          slideshowIntervalSec:
            els.filesPlayerSlideshowInterval &&
            els.filesPlayerSlideshowInterval.value
              ? Number(els.filesPlayerSlideshowInterval.value)
              : 5,
          transition:
            els.filesPlayerTransition && els.filesPlayerTransition.value
              ? els.filesPlayerTransition.value
              : "crossfade",
          overlayVisible: fpOverlayVisible,
        })
      );
    } catch (_err) {
      void _err;
    }
  }

  function fpLoad() {
    try {
      var raw = localStorage.getItem(LIBRARY_PLAYER_LS);
      if (!raw) {
        raw = localStorage.getItem(LEGACY_FILES_PLAYER_LS);
        if (raw) {
          try {
            localStorage.setItem(LIBRARY_PLAYER_LS, raw);
          } catch (_mig) {
            void _mig;
          }
        }
      }
      if (!raw) {
        return;
      }
      var ob = JSON.parse(raw);
      if (!ob || !Array.isArray(ob.baseQueue)) {
        return;
      }
      fpBaseQueue = ob.baseQueue.filter(function (x) {
        return typeof x === "string" && x.length && filesPlayerIsQueueableRel(x);
      });
      if (typeof ob.slideshowTimed === "boolean") {
        fpSlideshowTimed = ob.slideshowTimed;
      }
      if (typeof ob.slideshowPaused === "boolean") {
        fpSlideshowPaused = ob.slideshowPaused;
      }
      if (typeof ob.overlayVisible === "boolean") {
        fpOverlayVisible = ob.overlayVisible;
      }
      if (
        els.filesPlayerSlideshowInterval &&
        typeof ob.slideshowIntervalSec === "number" &&
        isFinite(ob.slideshowIntervalSec)
      ) {
        var iv = Math.max(1, Math.min(120, Math.floor(ob.slideshowIntervalSec)));
        els.filesPlayerSlideshowInterval.value = String(iv);
      }
      if (
        els.filesPlayerTransition &&
        typeof ob.transition === "string" &&
        (ob.transition === "crossfade" || ob.transition === "none")
      ) {
        els.filesPlayerTransition.value = ob.transition;
      }
      if (els.filesPlayerSlideshowTimed) {
        els.filesPlayerSlideshowTimed.checked = fpSlideshowTimed;
      }
      if (els.filesPlayerOverlayToggle) {
        els.filesPlayerOverlayToggle.setAttribute(
          "aria-pressed",
          fpOverlayVisible ? "true" : "false"
        );
      }
      fpShuffle = !!ob.shuffle;
      if (typeof ob.loopPlaylist === "boolean") {
        fpLoopPlaylist = ob.loopPlaylist;
      } else if (ob.loopMode === "all") {
        fpLoopPlaylist = true;
      } else {
        fpLoopPlaylist = false;
      }
      var curRel = typeof ob.currentRel === "string" ? ob.currentRel : "";
      if (ob.v === 1 && typeof ob.playIndex === "number" && ob.playIndex >= 0) {
        var legacy = ob.baseQueue[ob.playIndex];
        if (typeof legacy === "string") {
          curRel = legacy;
        }
      }
      fpSyncShuffleUi();
      fpSyncLoopUi();
      fpRebuildOrder(false);
      fpPlayIndex =
        curRel && fpPlayOrder.indexOf(curRel) >= 0
          ? fpPlayOrder.indexOf(curRel)
          : fpPlayOrder.length
            ? 0
            : -1;
    } catch (_err) {
      void _err;
    }
  }

  function fisherYates(arr) {
    var a = arr.slice();
    for (var i = a.length - 1; i > 0; i--) {
      var j = Math.floor(Math.random() * (i + 1));
      var t = a[i];
      a[i] = a[j];
      a[j] = t;
    }
    return a;
  }

  function fpRebuildOrder(repositionByCurrent) {
    var cur = repositionByCurrent !== false ? fpCurrentRel() : "";
    if (fpShuffle) {
      fpPlayOrder = fisherYates(fpBaseQueue);
    } else {
      fpPlayOrder = fpBaseQueue.slice();
    }
    if (cur) {
      var ni = fpPlayOrder.indexOf(cur);
      fpPlayIndex = ni >= 0 ? ni : fpPlayIndex;
    }
    if (fpPlayIndex >= fpPlayOrder.length) {
      fpPlayIndex = fpPlayOrder.length ? fpPlayOrder.length - 1 : -1;
    }
  }

  function fpSetVideoLoop() {
    if (!els.filesVideo) {
      return;
    }
    /* Native video.loop can suppress `ended`; playlist looping is handled in fpEnded. */
    els.filesVideo.loop = false;
  }

  function fpPolicyPlayPromise(p) {
    if (p && typeof p.catch === "function") {
      p.catch(function () {
        fpToast(
          "Click Play on the video to continue (browser blocked autoplay).",
          false
        );
      });
    }
  }

  function fpSyncPlayPauseButton() {
    var btn = els.filesPlayerPlay;
    if (!btn || !els.filesVideo) {
      return;
    }
    var cur = fpCurrentRel();
    var playing = false;
    if (filesPlayerIsVideoAudioRel(cur) && !els.filesVideo.hidden) {
      playing = !els.filesVideo.paused;
    } else if (filesPlayerIsImageRel(cur)) {
      playing = fpSlideshowTimed && !fpSlideshowPaused;
    }
    var playIc = btn.querySelector(".files-player-ic--play");
    var pauseIc = btn.querySelector(".files-player-ic--pause");
    if (playIc) {
      playIc.hidden = playing;
    }
    if (pauseIc) {
      pauseIc.hidden = !playing;
    }
    if (filesPlayerIsImageRel(cur) && !fpSlideshowTimed) {
      if (playIc) {
        playIc.hidden = false;
      }
      if (pauseIc) {
        pauseIc.hidden = true;
      }
      btn.setAttribute("aria-label", "Play selected or resume");
      btn.title =
        "Play selected / resume (timed slideshow off — use Next for images)";
    } else {
      btn.setAttribute(
        "aria-label",
        playing ? "Pause" : "Play selected or resume"
      );
      btn.title = playing ? "Pause" : "Play selected / resume";
    }
  }

  function fpSyncFsHudPauseLabel() {
    var b = els.filesPlayerFsPause;
    if (!b) {
      return;
    }
    if (fpSlideshowTimed && !fpSlideshowPaused) {
      b.textContent = "Pause";
    } else {
      b.textContent = "Resume";
    }
  }

  function fpSyncShuffleUi() {
    var btn = els.filesPlayerShuffle;
    if (!btn) {
      return;
    }
    btn.setAttribute("aria-pressed", fpShuffle ? "true" : "false");
  }

  function fpSyncLoopUi() {
    var btn = els.filesPlayerLoop;
    if (!btn) {
      return;
    }
    btn.setAttribute("aria-pressed", fpLoopPlaylist ? "true" : "false");
  }

  function fpUpdateMediaSession(rel) {
    if (!rel || !("mediaSession" in navigator)) {
      return;
    }
    try {
      navigator.mediaSession.metadata = new MediaMetadata({
        title: filesPlayerBasename(rel),
        artist: "Archive Console",
      });
      navigator.mediaSession.setActionHandler("nexttrack", function () {
        fpNext(true);
      });
      navigator.mediaSession.setActionHandler("previoustrack", function () {
        fpPrev(true);
      });
    } catch (_err) {
      void _err;
    }
  }

  function fpClearPlayerError() {
    if (els.filesPlayerError) {
      els.filesPlayerError.hidden = true;
      els.filesPlayerError.textContent = "";
    }
  }

  function fpSetPlayerError(msg) {
    if (!els.filesPlayerError) {
      return;
    }
    if (!msg) {
      fpClearPlayerError();
      return;
    }
    els.filesPlayerError.hidden = false;
    els.filesPlayerError.textContent = msg;
  }

  function isFilesPlayerDevLog() {
    try {
      var h = String(location.hostname || "");
      return h === "localhost" || h === "127.0.0.1" || h === "[::1]";
    } catch (_e) {
      return false;
    }
  }

  /** From <video> metadata; 0 until loadedmetadata. */
  var filesPlayerVideoMetaW = 0;
  var filesPlayerVideoMetaH = 0;
  var filesPlayerPaneWidthPx = 0;
  /** #filesPlayer content box height (ResizeObserver) — caps video frame so queue stays reachable. */
  var filesPlayerSectionHeightPx = 0;
  var fpVideoLayoutRaf = 0;

  function fpClampLayout(n, lo, hi) {
    return Math.max(lo, Math.min(hi, n));
  }

  /** Sum layout height of #filesPlayer children except the video frame and playlist (measured). */
  function fpMeasureFilesPlayerChromeExcludingFrameAndQueuePx() {
    var player = els.filesPlayer;
    var frame = els.filesVideoFrame;
    var queue = els.filesPlayerQueue;
    if (!player || !frame || !queue) {
      return 200;
    }
    var sum = 0;
    var kids = player.children;
    for (var i = 0; i < kids.length; i++) {
      var el = kids[i];
      if (el === frame || el === queue) {
        continue;
      }
      if (el.hidden) {
        continue;
      }
      var r = el.getBoundingClientRect();
      sum += r.height;
    }
    /* Flex gap is not in child rects; padding already inside player box. */
    return Math.max(120, Math.ceil(sum));
  }

  function fpUpdateVideoFrameLayout() {
    var frame = els.filesVideoFrame;
    if (!frame) {
      return;
    }
    var paneW = filesPlayerPaneWidthPx;
    var rw = frame.getBoundingClientRect().width;
    if (!paneW || paneW < 32) {
      paneW = rw;
    }
    if (!paneW || paneW < 32) {
      return;
    }
    var ph = filesPlayerSectionHeightPx;
    if ((!ph || ph < 80) && els.filesPlayer) {
      ph = els.filesPlayer.getBoundingClientRect().height;
    }
    var vw = filesPlayerVideoMetaW;
    var vh = filesPlayerVideoMetaH;
    var ar = vw > 0 && vh > 0 ? vw / vh : 16 / 9;
    if (vw > 0 && vh > 0) {
      frame.style.aspectRatio = vw + " / " + vh;
    } else {
      frame.style.aspectRatio = "16 / 9";
    }
    /* Height scales with pane width (naturalH = width ÷ aspect ratio). */
    var naturalH = paneW / ar;
    /* Floor grows with width so wide panes are not stuck with a short strip. */
    var minH = fpClampLayout(paneW * 0.34, 128, 300);
    var chrome = fpMeasureFilesPlayerChromeExcludingFrameAndQueuePx();
    var queueMin = 0;
    if (els.filesPlayerQueue) {
      var qcs = window.getComputedStyle(els.filesPlayerQueue);
      var qm = parseFloat(qcs.minHeight);
      queueMin = isFinite(qm) && qm > 0 ? qm : 160;
    }
    var room =
      ph > 120 ? ph - chrome - queueMin : Math.min(naturalH, window.innerHeight * 0.5);
    var globalCap = Math.min(window.innerHeight * 0.82, 720);
    var maxH = Math.max(96, Math.min(room, globalCap));
    var lo = Math.min(minH, maxH);
    var hi = Math.max(minH, maxH);
    var targetH = fpClampLayout(naturalH, lo, hi);
    frame.style.height = targetH + "px";
    frame.style.maxHeight = maxH + "px";
    if (isFilesPlayerDevLog()) {
      console.debug("[files-player] fpUpdateVideoFrameLayout", {
        paneW: paneW,
        ar: ar,
        minH: minH,
        maxH: maxH,
        finalH: targetH,
        chromePx: chrome,
        queueMinPx: queueMin,
        ph: ph,
        targetId: "filesVideoFrame",
        videoObjectFitEl: "filesVideo",
      });
    }
  }

  function fpScheduleVideoFrameLayout() {
    if (fpVideoLayoutRaf) {
      return;
    }
    fpVideoLayoutRaf = requestAnimationFrame(function () {
      fpVideoLayoutRaf = 0;
      fpUpdateVideoFrameLayout();
    });
  }

  function fpResetVideoFrameMeta() {
    filesPlayerVideoMetaW = 0;
    filesPlayerVideoMetaH = 0;
    fpScheduleVideoFrameLayout();
  }

  var fpHadVisibleImageSlide = false;

  function fpStopSlideshowTimer() {
    if (fpSlideshowTimer) {
      window.clearTimeout(fpSlideshowTimer);
      fpSlideshowTimer = null;
    }
  }

  function fpTransitionIsNone() {
    return (
      els.filesPlayerTransition && els.filesPlayerTransition.value === "none"
    );
  }

  function fpSlideshowIntervalSeconds() {
    var raw =
      els.filesPlayerSlideshowInterval &&
      els.filesPlayerSlideshowInterval.value;
    var n = parseFloat(raw, 10);
    if (!isFinite(n) || n < 1) {
      return 5;
    }
    return Math.max(1, Math.min(120, n));
  }

  function fpRestartSlideshowTimer() {
    fpStopSlideshowTimer();
    if (!fpSlideshowTimed || fpSlideshowPaused) {
      return;
    }
    var rel = fpCurrentRel();
    if (!rel || !filesPlayerIsImageRel(rel)) {
      return;
    }
    fpSlideshowTimer = window.setTimeout(function () {
      fpSlideshowTimer = null;
      if (!fpSlideshowTimed || fpSlideshowPaused) {
        return;
      }
      fpNext(true);
    }, fpSlideshowIntervalSeconds() * 1000);
  }

  function fpClearImageLayers() {
    fpStopSlideshowTimer();
    fpHadVisibleImageSlide = false;
    if (els.filesImageA) {
      els.filesImageA.onload = null;
      els.filesImageA.onerror = null;
      els.filesImageA.removeAttribute("src");
      els.filesImageA.hidden = true;
      els.filesImageA.classList.remove("is-visible");
      els.filesImageA.classList.remove("files-player-slide--instant");
    }
    if (els.filesImageB) {
      els.filesImageB.onload = null;
      els.filesImageB.onerror = null;
      els.filesImageB.removeAttribute("src");
      els.filesImageB.hidden = true;
      els.filesImageB.classList.remove("is-visible");
      els.filesImageB.classList.remove("files-player-slide--instant");
    }
    fpImageShowingA = true;
  }

  function fpTruncateMiddle(s, maxLen) {
    if (!s || s.length <= maxLen) {
      return s || "";
    }
    var elide = Math.max(4, Math.floor((maxLen - 1) / 2));
    return s.slice(0, elide) + "…" + s.slice(s.length - elide);
  }

  function fpUpdateStageMeta(rel) {
    if (!els.filesPlayerStageMeta || !els.filesPlayerStageMetaInner) {
      return;
    }
    if (!fpOverlayVisible || !rel) {
      els.filesPlayerStageMeta.hidden = true;
      els.filesPlayerStageMetaInner.innerHTML = "";
      return;
    }
    els.filesPlayerStageMeta.hidden = false;
    var base = filesPlayerBasename(rel);
    var pathShown = fpTruncateMiddle(rel, 56);
    var sz = filesListRowLookupSize(rel);
    if (sz == null && fpMetaSizeByRel[rel] != null) {
      sz = fpMetaSizeByRel[rel];
    }
    if (sz == null) {
      fetch("/api/files/metadata?path=" + encodeURIComponent(rel))
        .then(function (r) {
          if (!r.ok) {
            return null;
          }
          return r.json();
        })
        .then(function (j) {
          if (!j || typeof j.size !== "number") {
            return;
          }
          fpMetaSizeByRel[rel] = j.size;
          if (fpCurrentRel() === rel) {
            fpUpdateStageMeta(rel);
            fpRefreshPlayerStats();
          }
        })
        .catch(function () {
          void 0;
        });
    }
    var dim =
      filesPlayerVideoMetaW > 0 && filesPlayerVideoMetaH > 0
        ? filesPlayerVideoMetaW + "×" + filesPlayerVideoMetaH
        : "—";
    var szLab = sz != null ? formatFileSize(sz) : "—";
    els.filesPlayerStageMetaInner.innerHTML =
      "<p class=\"files-player-meta-line\"><strong>" +
      esc(base) +
      "</strong></p>" +
      "<p class=\"files-player-meta-line muted\" title=\"" +
      esc(rel) +
      "\">" +
      esc(pathShown) +
      "</p>" +
      "<p class=\"files-player-meta-line muted\">" +
      esc(szLab) +
      " · " +
      esc(dim) +
      "</p>";
  }

  function fpApplyOverlayVisibility() {
    fpUpdateStageMeta(fpCurrentRel());
  }

  function fpPreloadAdjacentImages() {
    var n = fpPlayOrder.length;
    if (n < 2 || fpPlayIndex < 0) {
      return;
    }
    function preloadIdx(idx) {
      if (idx < 0 || idx >= n) {
        return;
      }
      var r = fpPlayOrder[idx];
      if (!filesPlayerIsImageRel(r)) {
        return;
      }
      var im = new Image();
      im.src = reportsFileHref(r, false);
    }
    var i = fpPlayIndex;
    if (i + 1 < n) {
      preloadIdx(i + 1);
    } else if (fpLoopPlaylist) {
      preloadIdx(0);
    }
    if (i > 0) {
      preloadIdx(i - 1);
    } else if (fpLoopPlaylist) {
      preloadIdx(n - 1);
    }
  }

  function fpApplyImageToStage(rel) {
    if (!els.filesImageA || !els.filesImageB) {
      return;
    }
    fpClearPlayerError();
    var incoming = fpImageShowingA ? els.filesImageB : els.filesImageA;
    var outgoing = fpImageShowingA ? els.filesImageA : els.filesImageB;
    var inst = fpTransitionIsNone();
    var url = reportsFileHref(rel, false);
    incoming.onload = null;
    incoming.onerror = null;
    incoming.onerror = function () {
      incoming.onerror = null;
      fpImageErrorSkipCount++;
      if (fpImageErrorSkipCount > fpPlayOrder.length + 2) {
        fpSetPlayerError("Could not load images in queue.");
        fpImageErrorSkipCount = 0;
        return;
      }
      fpSetPlayerError("Could not load image — skipping to next.");
      var n = fpPlayOrder.length;
      if (n <= 1) {
        fpPlayIndex = -1;
        fpClearImageLayers();
        if (els.filesVideo) {
          els.filesVideo.hidden = false;
        }
        fpRenderAll();
        fpSave();
        return;
      }
      if (fpPlayIndex < n - 1) {
        fpPlayIndex++;
      } else if (fpLoopPlaylist) {
        fpPlayIndex = 0;
      } else {
        fpClearImageLayers();
        if (els.filesVideo) {
          els.filesVideo.hidden = false;
        }
        fpRenderAll();
        fpSave();
        return;
      }
      fpClearPlayerError();
      fpLoadCurrentMedia(fpCurrentRel(), false);
      fpRenderAll();
      fpSave();
    };
    if (inst) {
      incoming.classList.add("files-player-slide--instant");
      outgoing.classList.add("files-player-slide--instant");
    } else {
      incoming.classList.remove("files-player-slide--instant");
      outgoing.classList.remove("files-player-slide--instant");
    }
    incoming.onload = function () {
      incoming.onload = null;
      fpImageErrorSkipCount = 0;
      var ow = incoming.naturalWidth || 0;
      var oh = incoming.naturalHeight || 0;
      if (ow > 0 && oh > 0) {
        filesPlayerVideoMetaW = ow;
        filesPlayerVideoMetaH = oh;
      } else {
        filesPlayerVideoMetaW = 0;
        filesPlayerVideoMetaH = 0;
      }
      var first = !fpHadVisibleImageSlide;
      incoming.hidden = false;
      if (first) {
        fpHadVisibleImageSlide = true;
        if (outgoing) {
          outgoing.hidden = true;
          outgoing.classList.remove("is-visible");
        }
        incoming.classList.add("is-visible");
        fpImageShowingA = incoming === els.filesImageA;
      } else if (inst) {
        outgoing.hidden = false;
        outgoing.classList.remove("is-visible");
        incoming.classList.add("is-visible");
        fpImageShowingA = incoming === els.filesImageA;
      } else {
        outgoing.hidden = false;
        window.requestAnimationFrame(function () {
          window.requestAnimationFrame(function () {
            incoming.classList.add("is-visible");
            outgoing.classList.remove("is-visible");
            fpImageShowingA = incoming === els.filesImageA;
          });
        });
      }
      fpScheduleVideoFrameLayout();
      fpRefreshPlayerStats();
      fpUpdateStageMeta(rel);
      fpSyncPlayPauseButton();
      fpSyncFsHudPauseLabel();
      fpRestartSlideshowTimer();
      fpPreloadAdjacentImages();
      fpRenderNowNext();
    };
    incoming.src = url;
  }

  function fpLoadVideoSource(rel, andPlay) {
    if (!els.filesVideo || !rel) {
      return;
    }
    fpClearImageLayers();
    fpLastLoadedRel = rel;
    fpClearPlayerError();
    fpResetVideoFrameMeta();
    els.filesVideo.hidden = false;
    els.filesVideo.src = reportsFileHref(rel, false);
    els.filesVideo.load();
    fpSetVideoLoop();
    fpUpdateMediaSession(rel);
    if (andPlay) {
      fpPolicyPlayPromise(els.filesVideo.play());
    }
    fpRefreshPlayerStats();
    fpUpdateStageMeta(rel);
    fpSyncPlayPauseButton();
    fpSyncFsHudPauseLabel();
    fpStopSlideshowTimer();
  }

  function fpLoadCurrentMedia(rel, andPlay) {
    if (!rel) {
      return;
    }
    if (!filesPlayerIsQueueableRel(rel)) {
      fpMsg(
        "Not a supported type — use video, audio, or jpg/png/gif/webp."
      );
      return;
    }
    fpStopSlideshowTimer();
    fpLastLoadedRel = rel;
    fpUpdateMediaSession(rel);
    if (filesPlayerIsVideoAudioRel(rel)) {
      fpLoadVideoSource(rel, !!andPlay);
      return;
    }
    if (filesPlayerIsImageRel(rel)) {
      if (els.filesVideo) {
        els.filesVideo.pause();
        els.filesVideo.removeAttribute("src");
        els.filesVideo.load();
        els.filesVideo.hidden = true;
      }
      fpResetVideoFrameMeta();
      fpApplyImageToStage(rel);
    }
  }

  function fpRefreshPlayerStats() {
    if (!els.filesPlayerStats) {
      return;
    }
    var rel = fpCurrentRel();
    var v = els.filesVideo;
    if (!rel) {
      els.filesPlayerStats.textContent = "";
      return;
    }
    var parts = [];
    if (v && filesPlayerIsVideoAudioRel(rel) && !v.hidden) {
      var durLabel = fpFormatDuration(v.duration);
      if (durLabel) {
        parts.push("Duration " + durLabel);
      }
    }
    if (filesPlayerVideoMetaW > 0 && filesPlayerVideoMetaH > 0) {
      parts.push(filesPlayerVideoMetaW + "×" + filesPlayerVideoMetaH);
    }
    var sz = filesListRowLookupSize(rel);
    if (sz == null && fpMetaSizeByRel[rel] != null) {
      sz = fpMetaSizeByRel[rel];
    }
    if (sz != null) {
      parts.push(formatFileSize(sz));
    }
    var ext = filesPlayerContainerExt(rel);
    if (ext) {
      parts.push(ext);
    }
    els.filesPlayerStats.textContent = parts.join(" · ");
  }

  function fpRenderNowNext() {
    var now = fpCurrentRel();
    var next = "";
    if (fpPlayIndex >= 0 && fpPlayIndex + 1 < fpPlayOrder.length) {
      next = fpPlayOrder[fpPlayIndex + 1];
    } else if (
      fpLoopPlaylist &&
      fpPlayOrder.length > 0 &&
      fpPlayIndex >= 0 &&
      fpPlayIndex >= fpPlayOrder.length - 1
    ) {
      next = fpPlayOrder[0];
    }
    if (els.filesPlayerNowText) {
      if (now) {
        els.filesPlayerNowText.textContent = now;
        els.filesPlayerNowText.setAttribute("title", now);
      } else {
        els.filesPlayerNowText.textContent =
          "Nothing cued — select a file and use Play selected, add to the queue, double-click a file row, or double-click a queue row.";
        els.filesPlayerNowText.removeAttribute("title");
      }
    }
    if (els.filesPlayerNextWrap && els.filesPlayerNextText) {
      if (next) {
        els.filesPlayerNextWrap.hidden = false;
        els.filesPlayerNextText.textContent = next;
        els.filesPlayerNextText.setAttribute("title", next);
      } else {
        els.filesPlayerNextWrap.hidden = true;
        els.filesPlayerNextText.textContent = "";
        els.filesPlayerNextText.removeAttribute("title");
      }
    }
    fpRefreshPlayerStats();
    libraryClipRefreshSource();
  }

  function libraryClipUpdatePreview() {
    var prev = document.getElementById("libraryClipPreview");
    var outDir = document.getElementById("libraryClipOutDir");
    var bn = document.getElementById("libraryClipBasename");
    var fmt = document.getElementById("libraryClipFormat");
    if (!prev || !outDir || !fmt) {
      return;
    }
    var d = (outDir.value || "").trim().replace(/\\/g, "/").replace(/\/+$/, "");
    var ext = "." + (fmt.value || "mp4");
    var stem = (bn && bn.value.trim()) || "(auto)";
    if (!d) {
      prev.innerHTML = "<strong>Output:</strong> — (set output folder)";
      return;
    }
    prev.innerHTML =
      "<strong>Output:</strong> <code>" +
      esc(d + "/" + stem + ext) +
      "</code>";
  }

  function libraryClipRefreshSource() {
    var el = document.getElementById("libraryClipSourceText");
    if (el) {
      var r = fpCurrentRel();
      el.textContent = r || "—";
    }
    libraryClipUpdatePreview();
  }

  function initLibraryClipUi() {
    var outDir = document.getElementById("libraryClipOutDir");
    var bn = document.getElementById("libraryClipBasename");
    var fmt = document.getElementById("libraryClipFormat");
    var startEl = document.getElementById("libraryClipStart");
    var durEl = document.getElementById("libraryClipDuration");
    var endEl = document.getElementById("libraryClipEnd");
    var runBtn = document.getElementById("libraryClipRun");
    var setStartBtn = document.getElementById("libraryClipSetStart");
    var browseBtn = document.getElementById("libraryClipBrowseOut");
    var msgEl = document.getElementById("libraryClipMsg");
    var resultP = document.getElementById("libraryClipResult");
    var resultLink = document.getElementById("libraryClipResultLink");
    if (!runBtn || !outDir) {
      return;
    }
    [outDir, bn, fmt].forEach(function (el) {
      if (el) {
        el.addEventListener("input", libraryClipUpdatePreview);
        el.addEventListener("change", libraryClipUpdatePreview);
      }
    });
    if (setStartBtn && els.filesVideo) {
      setStartBtn.addEventListener("click", function () {
        if (!els.filesVideo.src) {
          if (msgEl) {
            msgEl.textContent = "Load a track first.";
          }
          return;
        }
        var t = els.filesVideo.currentTime;
        if (!isFinite(t) || t < 0) {
          t = 0;
        }
        if (startEl) {
          startEl.value = String(Math.round(t * 10) / 10);
        }
        if (msgEl) {
          msgEl.textContent = "";
        }
      });
    }
    if (browseBtn) {
      browseBtn.addEventListener("click", async function () {
        if (msgEl) {
          msgEl.textContent = "";
        }
        var r = await fetch("/api/clip/browse-output", { method: "POST" });
        if (r.status === 204) {
          return;
        }
        if (r.status === 503) {
          if (msgEl) {
            msgEl.textContent = "Folder picker unavailable on this host.";
          }
          return;
        }
        if (!r.ok) {
          var detail = "Browse failed.";
          try {
            var ej = await r.json();
            if (ej.detail) {
              detail =
                typeof ej.detail === "string"
                  ? ej.detail
                  : JSON.stringify(ej.detail);
            }
          } catch (_e) {
            void _e;
          }
          if (msgEl) {
            msgEl.textContent = detail;
          }
          return;
        }
        var j = await r.json();
        if (j.rel && outDir) {
          outDir.value = j.rel;
        }
        libraryClipUpdatePreview();
      });
    }
    runBtn.addEventListener("click", async function () {
      if (libraryClipPollTimer) {
        window.clearInterval(libraryClipPollTimer);
        libraryClipPollTimer = null;
      }
      var sourceRel = fpCurrentRel();
      if (!sourceRel) {
        if (msgEl) {
          msgEl.textContent =
            "No current track — play something from the queue first.";
        }
        return;
      }
      if (!filesPlayerIsVideoAudioRel(sourceRel)) {
        if (msgEl) {
          msgEl.textContent =
            "Clip export needs a video or audio track (not an image).";
        }
        return;
      }
      var odir = (outDir.value || "").trim();
      if (!odir) {
        if (msgEl) {
          msgEl.textContent =
            "Set an output folder (relative path or browse).";
        }
        return;
      }
      var start = parseFloat(startEl && startEl.value ? startEl.value : "0");
      if (!isFinite(start) || start < 0) {
        if (msgEl) {
          msgEl.textContent = "Invalid start time.";
        }
        return;
      }
      var endRaw = endEl && endEl.value.trim() ? endEl.value.trim() : "";
      var durRaw = durEl && durEl.value.trim() ? durEl.value.trim() : "";
      var body = {
        source_rel: sourceRel,
        output_dir_rel: odir.replace(/\\/g, "/"),
        start_sec: start,
        format: fmt ? fmt.value : "mp4",
        basename: bn ? bn.value.trim() : "",
      };
      if (endRaw !== "") {
        var en = parseFloat(endRaw);
        if (!isFinite(en)) {
          if (msgEl) {
            msgEl.textContent = "Invalid end time.";
          }
          return;
        }
        body.end_sec = en;
      } else {
        var du = parseFloat(durRaw || "0");
        if (!isFinite(du) || du <= 0) {
          if (msgEl) {
            msgEl.textContent = "Set duration or end time.";
          }
          return;
        }
        body.duration_sec = du;
      }
      if (resultP) {
        resultP.hidden = true;
      }
      runBtn.disabled = true;
      if (msgEl) {
        msgEl.textContent = "Starting…";
      }
      var rs = await fetch("/api/clip/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!rs.ok) {
        runBtn.disabled = false;
        var err = "Export failed.";
        try {
          var errJ = await rs.json();
          if (errJ.detail) {
            err =
              typeof errJ.detail === "string"
                ? errJ.detail
                : JSON.stringify(errJ.detail);
          }
        } catch (_e2) {
          void _e2;
        }
        if (msgEl) {
          msgEl.textContent = err;
        }
        return;
      }
      await rs.json();
      async function pollClip() {
        var st = await fetch("/api/clip/status");
        if (!st.ok) {
          return;
        }
        var z = await st.json();
        var ph = z.phase;
        var cl = z.clip;
        if (ph === "running" && cl && msgEl) {
          msgEl.textContent = "Exporting… (" + (cl.clip_id || "") + ")";
        }
        if (ph !== "running") {
          if (libraryClipPollTimer) {
            window.clearInterval(libraryClipPollTimer);
            libraryClipPollTimer = null;
          }
          runBtn.disabled = false;
          if (cl && cl.exit_code !== 0 && cl.exit_code != null) {
            if (msgEl) {
              var tail = cl.stderr_tail ? String(cl.stderr_tail).slice(-400) : "";
              msgEl.textContent =
                "ffmpeg exited " + cl.exit_code + (tail ? ". " + tail : "");
            }
          } else if (cl && cl.output_rel) {
            if (msgEl) {
              msgEl.textContent = "Done.";
            }
            if (resultP && resultLink) {
              resultP.hidden = false;
              resultLink.href =
                "/reports/file?rel=" + encodeURIComponent(cl.output_rel);
              resultLink.textContent = cl.output_rel;
            }
          } else {
            if (msgEl) {
              msgEl.textContent = "Finished.";
            }
          }
        }
      }
      await pollClip();
      libraryClipPollTimer = window.setInterval(function () {
        void pollClip();
      }, 500);
    });
    libraryClipRefreshSource();
  }

  function fpRenderQueue() {
    if (!els.filesPlayerQueue) {
      return;
    }
    var playing = fpCurrentRel();
    els.filesPlayerQueue.innerHTML = "";
    fpBaseQueue.forEach(function (rel, idx) {
      var li = document.createElement("li");
      li.textContent = rel;
      li.title = rel;
      li.draggable = true;
      if (playing && rel === playing) {
        li.classList.add("is-now");
      }
      if (idx === fpQueueSel) {
        li.classList.add("is-sel");
      }
      li.addEventListener("click", function () {
        fpQueueSel = idx;
        /* Do not call fpRenderQueue() here — it wipes innerHTML and breaks dblclick on the same row. */
        var q = els.filesPlayerQueue;
        if (!q) {
          return;
        }
        var lis = q.children;
        for (var si = 0; si < lis.length; si++) {
          lis[si].classList.toggle("is-sel", si === fpQueueSel);
        }
      });
      li.addEventListener("dblclick", function (ev) {
        ev.preventDefault();
        fpPlayTargetRelNow(rel);
        if (els.filesVideoFrame) {
          els.filesVideoFrame.scrollIntoView({
            block: "nearest",
            behavior: "smooth",
          });
        }
      });
      li.addEventListener("dragstart", function (ev) {
        ev.dataTransfer.setData("text/plain", String(idx));
        ev.dataTransfer.effectAllowed = "move";
      });
      li.addEventListener("dragover", function (ev) {
        ev.preventDefault();
        ev.dataTransfer.dropEffect = "move";
      });
      li.addEventListener("drop", function (ev) {
        ev.preventDefault();
        var from = parseInt(ev.dataTransfer.getData("text/plain"), 10);
        var to = idx;
        if (from !== from || from === to) {
          return;
        }
        var prevRel = fpCurrentRel();
        var item = fpBaseQueue.splice(from, 1)[0];
        fpBaseQueue.splice(to, 0, item);
        fpQueueSel = to;
        fpRebuildOrder();
        if (prevRel && fpPlayOrder.indexOf(prevRel) >= 0) {
          fpPlayIndex = fpPlayOrder.indexOf(prevRel);
        }
        fpRenderAll();
        fpSave();
      });
      els.filesPlayerQueue.appendChild(li);
    });
  }

  function fpRenderAll() {
    fpRenderQueue();
    fpRenderNowNext();
    fpUpdatePlayerActionButtons();
    fpSyncPlayPauseButton();
  }

  function fpResolvePlayTargetRel() {
    var ordered = filesListPlayableSelectedInOrder();
    if (ordered.length) {
      return ordered[0];
    }
    if (selectedRel && filesPlayerIsQueueableRel(selectedRel)) {
      return selectedRel;
    }
    if (fpPlayIndex < 0 && fpPlayOrder.length) {
      fpPlayIndex = 0;
    }
    return fpCurrentRel();
  }

  function fpQueueAppendPlayable(rel, quietDup) {
    if (!rel || !filesPlayerIsQueueableRel(rel)) {
      fpMsg(
        "Not supported for this queue — use video, audio, or jpg/png/gif/webp."
      );
      return false;
    }
    if (fpBaseQueue.indexOf(rel) >= 0) {
      if (!quietDup) {
        fpMsg("Already in queue.");
      }
      return false;
    }
    fpBaseQueue.push(rel);
    fpRebuildOrder();
    if (fpPlayIndex < 0) {
      fpPlayIndex = fpBaseQueue.length - 1;
    }
    fpMsg("");
    fpClearPlayerError();
    fpRenderAll();
    fpSave();
    return true;
  }

  function fpPlayTargetRelNow(rel) {
    if (!rel || !filesPlayerIsQueueableRel(rel)) {
      fpMsg(
        "Not supported — use video, audio, or jpg/png/gif/webp."
      );
      return;
    }
    if (!els.filesVideo && !els.filesMediaStage) {
      return;
    }
    fpMsg("");
    fpClearPlayerError();
    if (fpBaseQueue.indexOf(rel) < 0) {
      fpBaseQueue.push(rel);
    }
    fpRebuildOrder(false);
    fpPlayIndex = fpPlayOrder.indexOf(rel);
    fpLoadCurrentMedia(rel, true);
    fpRenderAll();
    fpSave();
  }

  function fpMsg(text) {
    if (els.filesPlayerMsg) {
      els.filesPlayerMsg.textContent = text || "";
    }
  }

  function fpEnded() {
    if (!fpPlayOrder.length || !els.filesVideo || els.filesVideo.hidden) {
      return;
    }
    if (fpLoopPlaylist) {
      if (fpPlayIndex >= fpPlayOrder.length - 1) {
        fpPlayIndex = 0;
      } else {
        fpPlayIndex++;
      }
      fpLoadCurrentMedia(fpCurrentRel(), true);
      fpRenderAll();
      fpSave();
      return;
    }
    if (fpPlayIndex >= fpPlayOrder.length - 1) {
      fpToast("End of queue.", false);
      fpRenderAll();
      fpSave();
      return;
    }
    fpPlayIndex++;
    fpLoadCurrentMedia(fpCurrentRel(), true);
    fpRenderAll();
    fpSave();
  }

  function fpPrev(andPlay) {
    if (!fpPlayOrder.length) {
      return;
    }
    if (fpPlayIndex <= 0) {
      if (fpLoopPlaylist) {
        fpPlayIndex = fpPlayOrder.length - 1;
      } else {
        return;
      }
    } else {
      fpPlayIndex--;
    }
    fpLoadCurrentMedia(fpCurrentRel(), !!andPlay);
    fpRenderAll();
    fpSave();
  }

  function fpNext(andPlay) {
    if (!fpPlayOrder.length) {
      return;
    }
    if (fpPlayIndex >= fpPlayOrder.length - 1) {
      if (fpLoopPlaylist) {
        fpPlayIndex = 0;
      } else {
        return;
      }
    } else {
      fpPlayIndex++;
    }
    fpLoadCurrentMedia(fpCurrentRel(), !!andPlay);
    fpRenderAll();
    fpSave();
  }

  function fpInitPlayerUi() {
    if (!els.filesVideo) {
      return;
    }
    fpLoad();
    if (els.filesPlayerSlideshowTimed) {
      els.filesPlayerSlideshowTimed.checked = fpSlideshowTimed;
    }
    fpSetVideoLoop();

    function fpToggleOverlayVisible() {
      fpOverlayVisible = !fpOverlayVisible;
      if (els.filesPlayerOverlayToggle) {
        els.filesPlayerOverlayToggle.setAttribute(
          "aria-pressed",
          fpOverlayVisible ? "true" : "false"
        );
      }
      fpApplyOverlayVisibility();
      fpSave();
    }

    function fpToggleFullscreenStage() {
      var el = els.filesMediaStage;
      if (!el) {
        return;
      }
      var fsNow =
        document.fullscreenElement || document.webkitFullscreenElement;
      if (!fsNow) {
        var req =
          el.requestFullscreen ||
          el.webkitRequestFullscreen ||
          el.msRequestFullscreen;
        if (req) {
          req.call(el).catch(function () {
            fpToast("Fullscreen was blocked or is unavailable.", true);
          });
        }
      } else {
        var ex =
          document.exitFullscreen ||
          document.webkitExitFullscreen ||
          document.msExitFullscreen;
        if (ex) {
          ex.call(document);
        }
      }
    }

    function fpOnFullscreenChange() {
      var st = els.filesMediaStage;
      if (!els.filesPlayerFsHud) {
        return;
      }
      var fsEl =
        document.fullscreenElement || document.webkitFullscreenElement;
      if (st && fsEl === st) {
        els.filesPlayerFsHud.hidden = false;
      } else {
        els.filesPlayerFsHud.hidden = true;
      }
    }

    if (els.filesPlayerShuffle) {
      els.filesPlayerShuffle.addEventListener("click", function () {
        var cur = fpCurrentRel();
        fpShuffle = !fpShuffle;
        fpSyncShuffleUi();
        fpRebuildOrder(false);
        if (cur) {
          var ni = fpPlayOrder.indexOf(cur);
          fpPlayIndex = ni >= 0 ? ni : 0;
        } else {
          fpPlayIndex = fpPlayOrder.length ? 0 : -1;
        }
        fpRenderAll();
        fpSave();
      });
    }
    if (els.filesPlayerLoop) {
      els.filesPlayerLoop.addEventListener("click", function () {
        fpLoopPlaylist = !fpLoopPlaylist;
        fpSyncLoopUi();
        fpSetVideoLoop();
        fpRenderNowNext();
        fpSave();
      });
    }
    els.filesVideo.addEventListener("ended", fpEnded);
    els.filesVideo.addEventListener("play", fpSyncPlayPauseButton);
    els.filesVideo.addEventListener("pause", fpSyncPlayPauseButton);
    els.filesVideo.addEventListener("loadeddata", function () {
      fpClearPlayerError();
      fpSyncPlayPauseButton();
    });
    els.filesVideo.addEventListener("loadedmetadata", function () {
      var w = els.filesVideo.videoWidth;
      var h = els.filesVideo.videoHeight;
      if (w > 0 && h > 0) {
        filesPlayerVideoMetaW = w;
        filesPlayerVideoMetaH = h;
      } else {
        filesPlayerVideoMetaW = 0;
        filesPlayerVideoMetaH = 0;
      }
      fpScheduleVideoFrameLayout();
      fpRefreshPlayerStats();
    });
    els.filesVideo.addEventListener("durationchange", function () {
      fpRefreshPlayerStats();
    });
    els.filesVideo.addEventListener("error", function () {
      fpSetPlayerError(
        "Could not load media—check allowlist, format, codec, or network."
      );
      if (isFilesPlayerDevLog()) {
        try {
          var src = els.filesVideo.currentSrc || els.filesVideo.src || "";
          var redacted = src.replace(/([?&]rel=)([^&]+)/i, function (_m, a, relVal) {
            try {
              var v = decodeURIComponent(relVal);
              if (v.length <= 24) {
                return a + v;
              }
              return a + v.slice(0, 12) + "…" + v.slice(-8);
            } catch (_dec) {
              return a + "…";
            }
          });
          var code =
            els.filesVideo.error && els.filesVideo.error.code != null
              ? els.filesVideo.error.code
              : "";
          console.warn("[files-player] video error", code, redacted);
          if (fpLastLoadedRel) {
            var u = reportsFileHref(fpLastLoadedRel, false);
            fetch(u, { method: "HEAD", credentials: "same-origin" }).then(
              function (r) {
                console.warn("[files-player] HEAD status for last rel", r.status);
              },
              function () {
                console.warn("[files-player] HEAD request failed");
              }
            );
          }
        } catch (_logErr) {
          void _logErr;
        }
      }
    });
    if (els.filesPlayerPlay) {
      els.filesPlayerPlay.addEventListener("click", function () {
        var v = els.filesVideo;
        var cur = fpCurrentRel();
        var target = fpResolvePlayTargetRel();
        if (
          cur &&
          target === cur &&
          filesPlayerIsImageRel(cur) &&
          fpSlideshowTimed
        ) {
          fpSlideshowPaused = !fpSlideshowPaused;
          if (fpSlideshowPaused) {
            fpStopSlideshowTimer();
          } else {
            fpRestartSlideshowTimer();
          }
          fpSyncPlayPauseButton();
          fpSyncFsHudPauseLabel();
          fpSave();
          return;
        }
        if (
          v &&
          cur &&
          target === cur &&
          filesPlayerIsVideoAudioRel(cur) &&
          !v.hidden &&
          (v.currentSrc || v.src || v.getAttribute("src"))
        ) {
          if (v.paused) {
            fpPolicyPlayPromise(v.play());
          } else {
            v.pause();
          }
          fpSyncPlayPauseButton();
          return;
        }
        if (!target) {
          fpMsg(
            "Select a queueable file in the list or add tracks to the queue."
          );
          return;
        }
        fpPlayTargetRelNow(target);
      });
    }
    if (els.filesPlayerPrev) {
      els.filesPlayerPrev.addEventListener("click", function () {
        fpPrev(true);
      });
    }
    if (els.filesPlayerNext) {
      els.filesPlayerNext.addEventListener("click", function () {
        fpNext(true);
      });
    }
    if (els.filesPlayerAddFile) {
      els.filesPlayerAddFile.addEventListener("click", function () {
        var playables = filesListPlayableSelectedInOrder();
        if (!playables.length) {
          fpMsg("Select one or more playable files in the list.");
          return;
        }
        var added = 0;
        playables.forEach(function (rel) {
          if (fpQueueAppendPlayable(rel, true)) {
            added++;
          }
        });
        if (added === 0) {
          fpToast("Selected files were already in the queue.", false);
        } else {
          fpToast(
            "Added " + added + " · queue now " + fpBaseQueue.length + " tracks.",
            false
          );
        }
        fpMsg("");
      });
    }
    if (els.filesPlayerAddFolder) {
      els.filesPlayerAddFolder.addEventListener("click", async function () {
        var dirRel = filesDirForFolderEnqueue();
        if (!dirRel) {
          fpToast(
            "Navigate into a folder, select a folder row (see list help), or select a file so its parent folder can be used.",
            true
          );
          return;
        }
        fpMsg("Scanning…");
        var url =
          "/api/files/playable-enumerate?path=" +
          encodeURIComponent(dirRel) +
          "&recursive=0&max_files=1000";
        var r = await fetch(url);
        if (!r.ok) {
          var detail = r.status + " " + r.statusText;
          try {
            var ej = await r.json();
            if (ej.detail) {
              detail =
                typeof ej.detail === "string"
                  ? ej.detail
                  : JSON.stringify(ej.detail);
            }
          } catch (_e) {
            void _e;
          }
          fpToast(detail, true);
          return;
        }
        var data = await r.json();
        var rels = data.rels || [];
        var added = 0;
        var have = Object.create(null);
        fpBaseQueue.forEach(function (x) {
          have[x] = true;
        });
        rels.forEach(function (rel) {
          if (!have[rel]) {
            have[rel] = true;
            fpBaseQueue.push(rel);
            added++;
          }
        });
        fpRebuildOrder();
        if (fpPlayIndex < 0 && fpPlayOrder.length) {
          fpPlayIndex = 0;
        }
        if (isFilesPlayerDevLog() && added === 0) {
          console.warn("[files-player] Add folder: 0 new tracks", {
            dirRel: dirRel,
            serverCount: rels.length,
          });
        }
        if (rels.length === 0) {
          fpToast("No video, audio, or slideshow images in this folder.", false);
        } else if (added === 0) {
          fpToast(
            "No new files added (" +
              rels.length +
              " already in queue).",
            false
          );
        } else {
          fpToast(
            "Added " + added + " · queue now " + fpBaseQueue.length + " tracks.",
            false
          );
        }
        fpMsg("");
        fpRenderAll();
        fpSave();
      });
    }
    if (els.filesPlayerRemove) {
      els.filesPlayerRemove.addEventListener("click", function () {
        if (fpQueueSel < 0 || fpQueueSel >= fpBaseQueue.length) {
          fpMsg("Select a queue row first.");
          return;
        }
        var prevRel = fpCurrentRel();
        fpBaseQueue.splice(fpQueueSel, 1);
        fpQueueSel = -1;
        fpRebuildOrder();
        if (!fpPlayOrder.length) {
          fpPlayIndex = -1;
          fpClearImageLayers();
          els.filesVideo.removeAttribute("src");
          els.filesVideo.load();
          els.filesVideo.hidden = false;
          fpLastLoadedRel = "";
          fpClearPlayerError();
          fpResetVideoFrameMeta();
        } else {
          if (prevRel && fpPlayOrder.indexOf(prevRel) >= 0) {
            fpPlayIndex = fpPlayOrder.indexOf(prevRel);
          } else {
            fpPlayIndex = Math.min(fpPlayIndex, fpPlayOrder.length - 1);
          }
          fpLoadCurrentMedia(fpCurrentRel(), false);
        }
        fpMsg("");
        fpRenderAll();
        fpSave();
      });
    }
    if (els.filesPlayerClear) {
      els.filesPlayerClear.addEventListener("click", function () {
        fpBaseQueue = [];
        fpPlayOrder = [];
        fpPlayIndex = -1;
        fpQueueSel = -1;
        fpClearImageLayers();
        els.filesVideo.removeAttribute("src");
        els.filesVideo.load();
        els.filesVideo.hidden = false;
        fpLastLoadedRel = "";
        fpClearPlayerError();
        fpResetVideoFrameMeta();
        fpMsg("Queue cleared.");
        fpRenderAll();
        fpSave();
      });
    }
    if (els.filesPlayerSlideshowTimed) {
      els.filesPlayerSlideshowTimed.addEventListener("change", function () {
        fpSlideshowTimed = !!els.filesPlayerSlideshowTimed.checked;
        if (!fpSlideshowTimed) {
          fpStopSlideshowTimer();
        } else {
          fpRestartSlideshowTimer();
        }
        fpSyncPlayPauseButton();
        fpSyncFsHudPauseLabel();
        fpSave();
      });
    }
    if (els.filesPlayerSlideshowInterval) {
      els.filesPlayerSlideshowInterval.addEventListener("change", function () {
        fpRestartSlideshowTimer();
        fpSave();
      });
    }
    if (els.filesPlayerTransition) {
      els.filesPlayerTransition.addEventListener("change", function () {
        fpSave();
      });
    }
    if (els.filesPlayerFullscreen) {
      els.filesPlayerFullscreen.addEventListener("click", fpToggleFullscreenStage);
    }
    if (els.filesPlayerOverlayToggle) {
      els.filesPlayerOverlayToggle.addEventListener("click", function () {
        fpToggleOverlayVisible();
      });
    }
    if (els.filesPlayerFsPrev) {
      els.filesPlayerFsPrev.addEventListener("click", function () {
        fpPrev(true);
      });
    }
    if (els.filesPlayerFsNext) {
      els.filesPlayerFsNext.addEventListener("click", function () {
        fpNext(true);
      });
    }
    if (els.filesPlayerFsPause) {
      els.filesPlayerFsPause.addEventListener("click", function () {
        if (!filesPlayerIsImageRel(fpCurrentRel()) || !fpSlideshowTimed) {
          return;
        }
        fpSlideshowPaused = !fpSlideshowPaused;
        if (fpSlideshowPaused) {
          fpStopSlideshowTimer();
        } else {
          fpRestartSlideshowTimer();
        }
        fpSyncPlayPauseButton();
        fpSyncFsHudPauseLabel();
        fpSave();
      });
    }
    if (els.filesPlayerFsOverlay) {
      els.filesPlayerFsOverlay.addEventListener("click", fpToggleOverlayVisible);
    }
    if (els.filesPlayerFsExit) {
      els.filesPlayerFsExit.addEventListener("click", function () {
        var ex =
          document.exitFullscreen ||
          document.webkitExitFullscreen ||
          document.msExitFullscreen;
        if (
          ex &&
          (document.fullscreenElement || document.webkitFullscreenElement)
        ) {
          ex.call(document);
        }
      });
    }
    document.addEventListener("fullscreenchange", fpOnFullscreenChange);
    document.addEventListener("webkitfullscreenchange", fpOnFullscreenChange);

    window.addEventListener("keydown", function (ev) {
      if (activeViewId !== "files") {
        return;
      }
      var tag = ev.target && ev.target.tagName;
      if (
        tag === "INPUT" ||
        tag === "TEXTAREA" ||
        tag === "SELECT" ||
        (ev.target && ev.target.isContentEditable)
      ) {
        return;
      }
      if (ev.key === "ArrowLeft") {
        ev.preventDefault();
        fpPrev(true);
      } else if (ev.key === "ArrowRight") {
        ev.preventDefault();
        fpNext(true);
      } else if (ev.key === " " || ev.code === "Space") {
        ev.preventDefault();
        var cur = fpCurrentRel();
        var v = els.filesVideo;
        if (filesPlayerIsVideoAudioRel(cur) && v && !v.hidden && v.src) {
          if (v.paused) {
            fpPolicyPlayPromise(v.play());
          } else {
            v.pause();
          }
          fpSyncPlayPauseButton();
        } else if (filesPlayerIsImageRel(cur) && fpSlideshowTimed) {
          fpSlideshowPaused = !fpSlideshowPaused;
          if (fpSlideshowPaused) {
            fpStopSlideshowTimer();
          } else {
            fpRestartSlideshowTimer();
          }
          fpSyncPlayPauseButton();
          fpSyncFsHudPauseLabel();
          fpSave();
        }
      } else if (ev.key === "i" || ev.key === "I") {
        fpToggleOverlayVisible();
      }
    });

    if (typeof ResizeObserver !== "undefined" && els.filesVideoFrame) {
      var fpPaneRo = new ResizeObserver(function (entries) {
        if (!entries.length) {
          return;
        }
        var cw = entries[0].contentRect.width;
        if (cw > 0) {
          filesPlayerPaneWidthPx = cw;
        }
        fpScheduleVideoFrameLayout();
      });
      fpPaneRo.observe(els.filesVideoFrame);
    }
    if (typeof ResizeObserver !== "undefined" && els.filesPlayer) {
      var fpPlayerRo = new ResizeObserver(function (entries) {
        if (!entries.length) {
          return;
        }
        var ch = entries[0].contentRect.height;
        if (ch > 0) {
          filesPlayerSectionHeightPx = ch;
        }
        fpScheduleVideoFrameLayout();
      });
      fpPlayerRo.observe(els.filesPlayer);
    }
    window.addEventListener("resize", fpScheduleVideoFrameLayout);
    fpScheduleVideoFrameLayout();
    if (fpCurrentRel()) {
      fpLoadCurrentMedia(fpCurrentRel(), false);
    }
    fpApplyOverlayVisibility();
    fpSyncFsHudPauseLabel();
    fpOnFullscreenChange();
    fpRenderAll();
    initLibraryClipUi();
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
      var primary = "archive_console_library_split_pct";
      var legacy = "archive_console_files_split_pct";
      var s = localStorage.getItem(primary);
      if (s == null || s === "") {
        s = localStorage.getItem(legacy);
        if (s != null && s !== "") {
          try {
            localStorage.setItem(primary, s);
          } catch (_m) {
            void _m;
          }
        }
      }
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
      localStorage.setItem("archive_console_library_split_pct", String(pct));
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

  /** Library workspace: one pixel height for both columns (localStorage + vertical drag). */
  var FILES_WORKSPACE_HEIGHT_STORAGE = "library.workspace.height";
  var LEGACY_FILES_WORKSPACE_HEIGHT_STORAGE = "files.workspace.height";
  var FILES_WORKSPACE_MIN_PX = 520;
  var filesWorkspaceResizeDrag = null;
  var filesWorkspaceResizeWinTimer = 0;

  function filesWorkspaceMaxHeightPx() {
    var shell = els.filesWorkspaceShell;
    if (!shell || activeViewId !== "library") {
      return 960;
    }
    var top = shell.getBoundingClientRect().top;
    var bottomReserve = 8;
    return Math.max(
      FILES_WORKSPACE_MIN_PX,
      Math.floor(window.innerHeight - top - bottomReserve)
    );
  }

  function filesWorkspaceDefaultHeightPx() {
    var shell = els.filesWorkspaceShell;
    var maxH = filesWorkspaceMaxHeightPx();
    if (!shell) {
      return fpClampLayout(820, FILES_WORKSPACE_MIN_PX, maxH);
    }
    /* Default fills space to the bottom of the viewport (maxH). Older builds used ~92vh
       caps and ~520px floors, which felt too small now that Library has details, duplicates,
       and player. Operators can still drag the resize strip or shrink with arrow keys. */
    return fpClampLayout(maxH, FILES_WORKSPACE_MIN_PX, maxH);
  }

  function applyFilesWorkspaceHeightPx(h, persist) {
    if (!els.filesWorkspaceShell) {
      return;
    }
    var maxH = filesWorkspaceMaxHeightPx();
    var minH = FILES_WORKSPACE_MIN_PX;
    h = Math.round(fpClampLayout(h, minH, maxH));
    var shell = els.filesWorkspaceShell;
    shell.style.setProperty("--files-workspace-height", h + "px");
    shell.style.height = h + "px";
    shell.style.minHeight = h + "px";
    shell.style.maxHeight = h + "px";
    if (persist) {
      try {
        localStorage.setItem(FILES_WORKSPACE_HEIGHT_STORAGE, String(h));
      } catch (_e) {
        void _e;
      }
    }
    fpScheduleVideoFrameLayout();
  }

  function syncFilesWorkspaceHeightFromStorage() {
    if (!els.filesWorkspaceShell || activeViewId !== "library") {
      return;
    }
    var maxH = filesWorkspaceMaxHeightPx();
    var minH = FILES_WORKSPACE_MIN_PX;
    var raw = null;
    try {
      raw = localStorage.getItem(FILES_WORKSPACE_HEIGHT_STORAGE);
      if (raw == null || raw === "") {
        var leg = localStorage.getItem(LEGACY_FILES_WORKSPACE_HEIGHT_STORAGE);
        if (leg != null && leg !== "") {
          raw = leg;
          try {
            localStorage.setItem(FILES_WORKSPACE_HEIGHT_STORAGE, leg);
          } catch (_mig2) {
            void _mig2;
          }
        }
      }
    } catch (_e) {
      raw = null;
    }
    var px = raw != null ? parseFloat(raw) : NaN;
    var h;
    if (!isFinite(px)) {
      h = filesWorkspaceDefaultHeightPx();
      applyFilesWorkspaceHeightPx(h, true);
      return;
    }
    h = fpClampLayout(px, minH, maxH);
    if (h !== px) {
      try {
        localStorage.setItem(FILES_WORKSPACE_HEIGHT_STORAGE, String(h));
      } catch (_e2) {
        void _e2;
      }
    }
    applyFilesWorkspaceHeightPx(h, false);
  }

  function initFilesWorkspaceShellResize() {
    var shell = els.filesWorkspaceShell;
    var handle = els.filesWorkspaceResizeY;
    if (!shell || !handle) {
      return;
    }

    function onWindowResize() {
      if (filesWorkspaceResizeWinTimer) {
        clearTimeout(filesWorkspaceResizeWinTimer);
      }
      filesWorkspaceResizeWinTimer = setTimeout(function () {
        filesWorkspaceResizeWinTimer = 0;
        if (activeViewId === "library") {
          syncFilesWorkspaceHeightFromStorage();
        }
      }, 100);
    }
    window.addEventListener("resize", onWindowResize);

    function moveFromClientY(clientY) {
      if (!filesWorkspaceResizeDrag) {
        return;
      }
      var delta = clientY - filesWorkspaceResizeDrag.startY;
      var h = filesWorkspaceResizeDrag.startH + delta;
      applyFilesWorkspaceHeightPx(h, false);
    }

    function endDrag() {
      if (!filesWorkspaceResizeDrag) {
        return;
      }
      filesWorkspaceResizeDrag = null;
      document.body.style.userSelect = "";
      if (els.filesWorkspaceShell) {
        var h = Math.round(els.filesWorkspaceShell.getBoundingClientRect().height);
        applyFilesWorkspaceHeightPx(h, true);
      }
    }

    handle.addEventListener("mousedown", function (ev) {
      if (ev.button !== 0) {
        return;
      }
      ev.preventDefault();
      var rect = shell.getBoundingClientRect();
      filesWorkspaceResizeDrag = { startY: ev.clientY, startH: rect.height };
      document.body.style.userSelect = "none";
    });

    handle.addEventListener("touchstart", function (ev) {
      if (!ev.touches || !ev.touches.length) {
        return;
      }
      ev.preventDefault();
      var rect = shell.getBoundingClientRect();
      filesWorkspaceResizeDrag = {
        startY: ev.touches[0].clientY,
        startH: rect.height,
      };
    }, { passive: false });

    window.addEventListener("mousemove", function (ev) {
      moveFromClientY(ev.clientY);
    });
    window.addEventListener("mouseup", endDrag);

    window.addEventListener("touchmove", function (ev) {
      if (!filesWorkspaceResizeDrag || !ev.touches.length) {
        return;
      }
      ev.preventDefault();
      moveFromClientY(ev.touches[0].clientY);
    }, { passive: false });
    window.addEventListener("touchend", endDrag);
    window.addEventListener("touchcancel", endDrag);

    handle.addEventListener("keydown", function (ev) {
      if (ev.key === "ArrowUp" || ev.key === "ArrowDown") {
        ev.preventDefault();
        var cur = shell.getBoundingClientRect().height;
        var step = ev.shiftKey ? 48 : 16;
        var next =
          ev.key === "ArrowUp" ? cur - step : cur + step;
        applyFilesWorkspaceHeightPx(next, true);
      }
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
    if (els.btnGallerydlSave) {
      els.btnGallerydlSave.disabled = editorJobRunning;
    }
    if (els.gallerydlSaveHint) {
      if (editorJobRunning) {
        els.gallerydlSaveHint.textContent =
          "Saving disabled while a run is active.";
        els.gallerydlSaveHint.hidden = false;
      } else {
        els.gallerydlSaveHint.hidden = true;
      }
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

  function gallerydlMarkClean() {
    if (!els.gallerydlTextarea) {
      return;
    }
    gallerydlBaseline = els.gallerydlTextarea.value;
    if (els.gallerydlDirtyPill) {
      els.gallerydlDirtyPill.hidden = true;
    }
  }

  function gallerydlUpdateDirty() {
    if (!els.gallerydlTextarea || !els.gallerydlDirtyPill) {
      return;
    }
    var dirty = els.gallerydlTextarea.value !== gallerydlBaseline;
    els.gallerydlDirtyPill.hidden = !dirty;
  }

  async function loadGallerydlFile() {
    if (!els.gallerydlTextarea) {
      return;
    }
    if (els.gallerydlMsg) {
      els.gallerydlMsg.textContent = "Loading from disk…";
    }
    try {
      var rs = await fetch("/api/settings");
      if (rs.ok) {
        var st = await rs.json();
        if (els.gallerydlEmptyPath && st.archive_root) {
          var root = String(st.archive_root).replace(/[/\\]+$/, "");
          var join = root.indexOf("\\") >= 0 ? "\\" : "/";
          els.gallerydlEmptyPath.textContent = root + join + GALLERY_DL_CONF;
        }
      }
    } catch (_e0) {
      /* ignore */
    }
    var r;
    try {
      r = await fetch("/api/files/" + encodeURIComponent(GALLERY_DL_CONF));
    } catch (_e1) {
      if (els.gallerydlMsg) {
        els.gallerydlMsg.textContent =
          "Load failed (network error). Check connection and the Archive Console server.";
      }
      return;
    }
    if (!r.ok) {
      if (els.gallerydlMsg) {
        els.gallerydlMsg.textContent = "Load failed (" + r.status + ").";
      }
      return;
    }
    var j = await r.json();
    if (els.gallerydlMsg) {
      els.gallerydlMsg.textContent = "";
    }
    var existsOnDisk = j.mtime != null;
    if (els.gallerydlEmptyState) {
      els.gallerydlEmptyState.hidden = existsOnDisk;
    }
    if (els.gallerydlMtime) {
      if (j.mtime != null) {
        els.gallerydlMtime.textContent =
          "mtime: " + new Date(j.mtime * 1000).toLocaleString();
      } else {
        els.gallerydlMtime.textContent = "new / missing on disk";
      }
    }
    if (els.gallerydlRelLabel) {
      els.gallerydlRelLabel.textContent = GALLERY_DL_CONF;
    }
    els.gallerydlTextarea.value = j.content != null ? j.content : "";
    gallerydlMarkClean();
    setEditorRunning(editorJobRunning);
  }

  async function gallerydlReloadFromDisk() {
    if (!els.gallerydlTextarea) {
      return;
    }
    if (els.gallerydlTextarea.value !== gallerydlBaseline) {
      if (
        !window.confirm(
          "Discard unsaved edits in " + GALLERY_DL_CONF + "?"
        )
      ) {
        return;
      }
    }
    await loadGallerydlFile();
  }

  async function saveGallerydlFile() {
    if (!els.gallerydlTextarea) {
      return;
    }
    var r0 = await fetch("/api/run/status");
    var s0 = await r0.json();
    if (s0.phase === "running") {
      if (els.gallerydlMsg) {
        els.gallerydlMsg.textContent =
          "Save blocked: a job is running. Wait for it to finish.";
      }
      return;
    }
    var body = {
      content: els.gallerydlTextarea.value,
      strip_blank_lines: false,
      conf_smoke: false,
      unlock_cookies: false,
    };
    var r = await fetch(
      "/api/files/" + encodeURIComponent(GALLERY_DL_CONF),
      {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      }
    );
    if (r.status === 409) {
      try {
        var ej = await r.json();
        if (els.gallerydlMsg) {
          els.gallerydlMsg.textContent =
            typeof ej.detail === "string"
              ? ej.detail
              : JSON.stringify(ej.detail);
        }
      } catch (_e2) {
        if (els.gallerydlMsg) {
          els.gallerydlMsg.textContent = await r.text();
        }
      }
      return;
    }
    if (!r.ok) {
      if (els.gallerydlMsg) {
        els.gallerydlMsg.textContent = "Save failed: " + r.status;
      }
      return;
    }
    var sj = await r.json();
    var parts = ["Saved."];
    if (sj.backup) {
      parts.push("Backup: " + sj.backup);
    }
    if (els.gallerydlMsg) {
      els.gallerydlMsg.textContent = parts.join(" ");
    }
    if (sj.mtime != null && els.gallerydlMtime) {
      els.gallerydlMtime.textContent =
        "mtime: " + new Date(sj.mtime * 1000).toLocaleString();
    }
    if (els.gallerydlEmptyState) {
      els.gallerydlEmptyState.hidden = true;
    }
    gallerydlMarkClean();
  }

  function supportedsitesSafeHttpHref(u) {
    if (!u || typeof u !== "string") {
      return null;
    }
    if (u.indexOf("https://") === 0 || u.indexOf("http://") === 0) {
      return u;
    }
    return null;
  }

  function supportedsitesFilterQuery() {
    return (els.supportedsitesFilter && els.supportedsitesFilter.value) || "";
  }

  function supportedsitesRowMatches(row, q) {
    if (!q || !q.trim()) {
      return true;
    }
    var s = q.trim().toLowerCase();
    var hay = (row.label || "") + " " + (row.id || "");
    if (row.example_url) {
      hay += " " + row.example_url;
    }
    return hay.toLowerCase().indexOf(s) >= 0;
  }

  function supportedsitesRenderTools() {
    if (!els.supportedsitesTools) {
      return;
    }
    els.supportedsitesTools.textContent = "";
    var payload = lastSupportedsitesPayload;
    if (!payload || !payload.tools) {
      var empty = document.createElement("p");
      empty.className = "muted small";
      empty.textContent = "No data loaded yet.";
      els.supportedsitesTools.appendChild(empty);
      return;
    }
    var q = supportedsitesFilterQuery();
    payload.tools.forEach(function (tool) {
      var card = document.createElement("div");
      card.className = "card supportedsites-tool-card";

      var h2 = document.createElement("h2");
      var badge = document.createElement("span");
      badge.className =
        "pill small " +
        (tool.id === "gallery-dl"
          ? "supportedsites-badge-gdl"
          : "supportedsites-badge-ytdlp");
      badge.textContent = tool.label || tool.id;
      h2.appendChild(badge);
      if (tool.version) {
        var ver = document.createElement("span");
        ver.className = "muted small";
        ver.textContent = "version " + tool.version;
        h2.appendChild(ver);
      }
      card.appendChild(h2);

      if (tool.doc_note) {
        var note = document.createElement("p");
        note.className = "muted small";
        note.textContent = tool.doc_note;
        card.appendChild(note);
      }

      if (tool.error) {
        var warn = document.createElement("div");
        warn.className = "callout warn";
        var pe = document.createElement("p");
        pe.textContent = tool.error;
        warn.appendChild(pe);
        card.appendChild(warn);
      }

      var links = document.createElement("p");
      links.className = "muted small";
      if (tool.doc_hub_url) {
        var a = document.createElement("a");
        a.className = "link";
        a.href = tool.doc_hub_url;
        a.target = "_blank";
        a.rel = "noopener noreferrer";
        a.textContent = "Official supported sites (docs)";
        links.appendChild(a);
      }
      if (tool.options_doc_url) {
        if (tool.doc_hub_url) {
          links.appendChild(document.createTextNode(" · "));
        }
        var a2 = document.createElement("a");
        a2.className = "link";
        a2.href = tool.options_doc_url;
        a2.target = "_blank";
        a2.rel = "noopener noreferrer";
        a2.textContent = "CLI options";
        links.appendChild(a2);
      }
      card.appendChild(links);

      var rows = (tool.extractors || []).filter(function (row) {
        return supportedsitesRowMatches(row, q);
      });
      var count = document.createElement("p");
      count.className = "muted small";
      count.textContent =
        rows.length +
        " shown" +
        (tool.extractors && tool.extractors.length !== rows.length
          ? " (" + tool.extractors.length + " total)"
          : "") +
        (tool.truncated ? " — list may be incomplete (output cap)." : "");
      card.appendChild(count);

      if (!rows.length) {
        var none = document.createElement("p");
        none.className = "muted small";
        none.textContent = q.trim()
          ? "No matching extractors for this filter."
          : "No extractors returned.";
        card.appendChild(none);
      } else {
        var wrap = document.createElement("div");
        wrap.className = "supportedsites-table-wrap";
        var table = document.createElement("table");
        table.className = "table supportedsites-table";
        var thead = document.createElement("thead");
        var hr = document.createElement("tr");
        ["Name / id", "Documentation", "Example"].forEach(function (lab) {
          var th = document.createElement("th");
          th.textContent = lab;
          hr.appendChild(th);
        });
        thead.appendChild(hr);
        table.appendChild(thead);
        var tbody = document.createElement("tbody");
        rows.forEach(function (row) {
          var tr = document.createElement("tr");
          var td0 = document.createElement("td");
          var strong = document.createElement("strong");
          strong.textContent = row.label || row.id || "—";
          td0.appendChild(strong);
          if (row.id && row.label && row.id !== row.label) {
            td0.appendChild(document.createElement("br"));
            var code = document.createElement("code");
            code.textContent = row.id;
            td0.appendChild(code);
          }
          tr.appendChild(td0);
          var td1 = document.createElement("td");
          if (row.doc_url) {
            var da = document.createElement("a");
            da.className = "link";
            da.href = row.doc_url;
            da.target = "_blank";
            da.rel = "noopener noreferrer";
            da.textContent = row.doc_generic
              ? "Project supported sites (search)"
              : "Docs";
            td1.appendChild(da);
          } else {
            td1.textContent = "—";
          }
          tr.appendChild(td1);
          var td2 = document.createElement("td");
          var exHref = supportedsitesSafeHttpHref(row.example_url);
          if (exHref) {
            var ea = document.createElement("a");
            ea.className = "link";
            ea.href = exHref;
            ea.target = "_blank";
            ea.rel = "noopener noreferrer";
            ea.textContent = exHref.length > 64
              ? exHref.slice(0, 32) + "…" + exHref.slice(-24)
              : exHref;
            td2.appendChild(ea);
          } else {
            td2.textContent = "—";
          }
          tr.appendChild(td2);
          tbody.appendChild(tr);
        });
        table.appendChild(tbody);
        wrap.appendChild(table);
        card.appendChild(wrap);
      }

      els.supportedsitesTools.appendChild(card);
    });
  }

  async function loadSupportedsites(forceRefresh) {
    if (!els.supportedsitesTools) {
      return;
    }
    if (els.supportedsitesMeta) {
      els.supportedsitesMeta.textContent = forceRefresh
        ? "Refreshing from CLIs…"
        : "Loading…";
    }
    var url =
      "/api/supported-sites" + (forceRefresh ? "?refresh=true" : "");
    try {
      var r = await fetch(url);
      if (!r.ok) {
        if (els.supportedsitesMeta) {
          els.supportedsitesMeta.textContent = "Load failed (" + r.status + ").";
        }
        return;
      }
      var j = await r.json();
      lastSupportedsitesPayload = j;
      if (els.supportedsitesDisclaimer) {
        els.supportedsitesDisclaimer.hidden = !j.disclaimer;
        els.supportedsitesDisclaimer.textContent = j.disclaimer || "";
      }
      if (els.supportedsitesMeta) {
        var parts = [];
        parts.push(j.cached ? "Cached snapshot" : "Fresh from CLIs");
        if (j.cache_ttl_sec != null) {
          parts.push("TTL ~" + j.cache_ttl_sec + "s");
        }
        if (j.generated_unix != null) {
          parts.push(
            "generated " + new Date(j.generated_unix * 1000).toLocaleString()
          );
        }
        els.supportedsitesMeta.textContent = parts.join(" · ");
      }
      supportedsitesRenderTools();
    } catch (_err) {
      if (els.supportedsitesMeta) {
        els.supportedsitesMeta.textContent =
          "Load failed (network). Is Archive Console running?";
      }
    }
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
      oneoff: "One-off",
      galleries: "Galleries",
      clip_export: "Clip export",
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

  function applyTopCookieBannerVisibility() {
    var b = els.cookieReminderBanner;
    if (!b) {
      return;
    }
    var wantShow = lastRemindersCookieShowEligible;
    var suppressOnOneoffWithGate =
      (activeViewId === "oneoff" || activeViewId === "galleries") &&
      lastRemindersRequireCookieConfirmManual;
    if (els.cookieReminderText) {
      if (wantShow) {
        els.cookieReminderText.textContent = lastRemindersCookieMessage;
      } else {
        els.cookieReminderText.textContent = "";
      }
    }
    b.hidden = !wantShow || suppressOnOneoffWithGate;
  }

  function activateView(viewId) {
    activeViewId = viewId;
    els.nav.forEach(function (b) {
      var on = b.getAttribute("data-view") === viewId;
      b.classList.toggle("is-active", on);
    });
    els.views.forEach(function (sec) {
      sec.classList.toggle("is-active", sec.id === "view-" + viewId);
    });
    applyTopCookieBannerVisibility();
    if (viewId === "library") {
      requestAnimationFrame(function () {
        requestAnimationFrame(syncFilesWorkspaceHeightFromStorage);
      });
      syncDupRootCheckboxesFromApi();
    }
  }

  function getInitialViewFromUrl() {
    var q = new URLSearchParams(window.location.search);
    var v = q.get("view");
    if (v === "history" || v === "logs" || v === "reports") {
      return "history";
    }
    if (v === "files") {
      return "library";
    }
    if (
      v === "library" ||
      v === "rename" ||
      v === "inputs" ||
      v === "settings" ||
      v === "ytdlp" ||
      v === "gallerydl" ||
      v === "supportedsites" ||
      v === "run" ||
      v === "oneoff" ||
      v === "galleries"
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
    } else if (sec === "rename") {
      el = document.getElementById("rename-log");
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
      if (els.btnOneoffStop) {
        els.btnOneoffStop.hidden = true;
      }
      if (els.btnGalleryStop) {
        els.btnGalleryStop.hidden = true;
      }
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
      if (els.btnOneoffStop) {
        els.btnOneoffStop.hidden = run.job !== "oneoff";
      }
      if (els.btnGalleryStop) {
        els.btnGalleryStop.hidden = run.job !== "galleries";
      }
    } else if (hasEnded) {
      els.runStatusSummary.textContent =
        "Last run finished (" + jobLabel(run.job) + "). Details:";
      els.btnStopRun.hidden = true;
      if (els.btnOneoffStop) {
        els.btnOneoffStop.hidden = true;
      }
      if (els.btnGalleryStop) {
        els.btnGalleryStop.hidden = true;
      }
    } else {
      els.runStatusSummary.textContent = "Run status: " + phase;
      els.btnStopRun.hidden = true;
      if (els.btnOneoffStop) {
        els.btnOneoffStop.hidden = true;
      }
      if (els.btnGalleryStop) {
        els.btnGalleryStop.hidden = true;
      }
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
    if (els.oneoffLogBody && els.optOneoffLogWrap) {
      els.oneoffLogBody.classList.toggle("is-wrap", els.optOneoffLogWrap.checked);
    }
    if (els.galleryLogBody && els.optGalleryLogWrap) {
      els.galleryLogBody.classList.toggle("is-wrap", els.optGalleryLogWrap.checked);
    }
  }

  function applyLogFont() {
    els.logBody.style.fontSize = logFontPx + "px";
    var g = Math.max(10, logFontPx - 2);
    els.logGutter.style.fontSize = g + "px";
    if (els.oneoffLogBody && els.oneoffLogGutter) {
      els.oneoffLogBody.style.fontSize = logFontPx + "px";
      els.oneoffLogGutter.style.fontSize = g + "px";
    }
    if (els.galleryLogBody && els.galleryLogGutter) {
      els.galleryLogBody.style.fontSize = logFontPx + "px";
      els.galleryLogGutter.style.fontSize = g + "px";
    }
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
          var hr0 = msg.status.run;
          activeStreamJob =
            msg.status.phase === "running" && hr0 && hr0.job ? hr0.job : null;
        }
        refreshCookieReminder();
        return;
      }
      if (msg.type === "start") {
        activeStreamJob = msg.job || null;
        if (activeStreamJob === "oneoff") {
          clearOneoffLogView();
        } else if (activeStreamJob === "galleries") {
          clearGalleryLogView();
        } else {
          clearLogView();
        }
        var dr0 =
          msg.job === "oneoff"
            ? !!(els.optOneoffDryRun && els.optOneoffDryRun.checked)
            : msg.job === "galleries"
              ? !!(els.optGalleryDryRun && els.optGalleryDryRun.checked)
              : els.optDry.checked;
        renderRunPanel({
          phase: "running",
          run: {
            run_id: msg.run_id,
            job: msg.job,
            pid: null,
            dry_run: dr0,
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
        appendStreamLine(msg.text != null ? msg.text : "");
        return;
      }
      if (msg.type === "end") {
        var code = msg.exit_code;
        var canceled = !!msg.canceled;
        var endedOneoff = activeStreamJob === "oneoff";
        var endedGalleries = activeStreamJob === "galleries";
        if (canceled) {
          setPhase("canceled");
          appendStreamLine(
            "[console] Stopped by user — batch may leave partial files on disk."
          );
        } else {
          setPhase(code === 0 ? "success" : "failed");
        }
        activeStreamJob = null;
        disableRunButtons(false);
        editorJobRunning = false;
        setEditorRunning(false);
        refreshRunPanel();
        loadRunOverview();
        if (endedOneoff) {
          loadOneoffRolling();
        }
        if (endedGalleries) {
          loadRunOverview();
        }
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
    if (els.btnOneoffStart) {
      els.btnOneoffStart.disabled = disabled;
    }
    if (els.btnGalleryStart) {
      els.btnGalleryStart.disabled = disabled;
    }
    if (els.btnGalleryPreview) {
      els.btnGalleryPreview.disabled = disabled;
    }
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
      var clipOut =
        row.job === "clip_export" && row.clip_output_rel
          ? String(row.clip_output_rel)
          : "";
      var reportHref = clipOut
        ? "/reports/file?rel=" + encodeURIComponent(clipOut)
        : folder
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
      if (row.job === "galleries") {
        statsSubrow +=
          '<div class="muted small" style="margin-top:0.25rem">Post-run: <code>verification.json</code> in the run folder (preview vs disk, optional yt-dlp fallback).</div>';
      }
      var triedCell = hasStats ? esc(String(rs.tried)) : "—";
      var okCell = hasStats ? esc(String(rs.ok)) : "—";
      var failCell = hasStats ? esc(String(rs.fail)) : "—";
      var savedCell = hasStats ? esc(String(rs.saved)) : "—";
      tr.innerHTML =
        "<td>" +
        esc(jobLabel(row.job)) +
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
        (clipOut
          ? '<a class="link" target="_blank" rel="noopener" href="' +
            esc(reportHref) +
            '" title="' +
            esc(clipOut) +
            '">' +
            esc(clipOut) +
            "</a>"
          : folder
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

  function getOneoffDirFormValue() {
    var a = els.dlDirOneoffInputs;
    var b = els.dlDirOneoffPanel;
    var u = "";
    if (a && a.value.trim()) {
      u = a.value.trim();
    } else if (b && b.value.trim()) {
      u = b.value.trim();
    }
    return u;
  }

  function syncOneoffDirInputs(val) {
    var s = val != null ? String(val) : "";
    if (els.dlDirOneoffInputs) {
      els.dlDirOneoffInputs.value = s;
    }
    if (els.dlDirOneoffPanel) {
      els.dlDirOneoffPanel.value = s;
    }
  }

  function getGalleriesDirFormValue() {
    var a = els.dlDirGalleriesInputs;
    var b = els.dlDirGalleriesPanel;
    var u = "";
    if (a && a.value.trim()) {
      u = a.value.trim();
    } else if (b && b.value.trim()) {
      u = b.value.trim();
    }
    return u;
  }

  function syncGalleriesDirInputs(val) {
    var s = val != null ? String(val) : "";
    if (els.dlDirGalleriesInputs) {
      els.dlDirGalleriesInputs.value = s;
    }
    if (els.dlDirGalleriesPanel) {
      els.dlDirGalleriesPanel.value = s;
    }
  }

  async function refreshGalleryOutputEffective() {
    if (!els.galleryOutputEffective) {
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
      var eff = (j.download_dirs_effective || {}).galleries;
      if (!eff) {
        return;
      }
      var cr =
        eff.configured_rel != null
          ? eff.configured_rel
          : "(default: " + (eff.default_rel || "galleries") + ")";
      var abs = eff.effective_abs || "—";
      els.galleryOutputEffective.textContent =
        "Full path (files download here): " +
        abs +
        "\nRelative to archive: " +
        cr;
    } catch {
      /* ignore */
    }
  }

  async function refreshOneoffOutputEffective() {
    if (!els.oneoffOutputEffective) {
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
      var eff = (j.download_dirs_effective || {}).oneoff;
      if (!eff) {
        return;
      }
      var cr =
        eff.configured_rel != null
          ? eff.configured_rel
          : "(default: " + (eff.default_rel || "oneoff") + ")";
      var abs = eff.effective_abs || "—";
      els.oneoffOutputEffective.textContent =
        "Full path (files download here): " +
        abs +
        "\nRelative to archive: " +
        cr;
    } catch {
      /* ignore */
    }
  }

  async function loadOneoffRolling() {
    if (!els.oneoffRollingSummary) {
      return;
    }
    try {
      var r = await fetch("/api/oneoff/rolling");
      if (!r.ok) {
        els.oneoffRollingSummary.textContent = "Could not load rolling summary.";
        return;
      }
      var j = await r.json();
      var st = j.stats || {};
      var parts = [
        "Attempts logged: " + (st.total != null ? st.total : 0),
        "OK: " + (st.ok != null ? st.ok : 0),
        "Fail: " + (st.fail != null ? st.fail : 0),
      ];
      if (st.last_completed_utc) {
        parts.push("Last completed (UTC): " + st.last_completed_utc);
      }
      if (st.last_url) {
        parts.push("Last URL: " + st.last_url);
      }
      if (st.last_outcome) {
        parts.push("Last outcome: " + st.last_outcome);
      }
      els.oneoffRollingSummary.textContent = parts.join(" · ");
      oneoffLastMediaRel = String(st.last_media_rel || "").trim();
      if (els.btnOneoffWatchNow) {
        var hasMedia = !!oneoffLastMediaRel;
        els.btnOneoffWatchNow.disabled = !hasMedia;
        els.btnOneoffWatchNow.title = hasMedia
          ? "Open Files, select this download, and play in the player."
          : "No completed local file yet.";
      }
      if (
        els.oneoffRollingReportLink &&
        els.oneoffRollingReportWrap &&
        j.report_rel
      ) {
        els.oneoffRollingReportLink.href = reportsViewHref(j.report_rel);
        els.oneoffRollingReportWrap.hidden = !j.report_exists;
      }
    } catch {
      els.oneoffRollingSummary.textContent = "Could not load rolling summary.";
      oneoffLastMediaRel = "";
      if (els.btnOneoffWatchNow) {
        els.btnOneoffWatchNow.disabled = true;
        els.btnOneoffWatchNow.title = "No completed local file yet.";
      }
    }
  }

  async function syncOneoffCookieReminderFromServer() {
    try {
      var r = await fetch("/api/settings", { credentials: "same-origin" });
      if (!r.ok) {
        return;
      }
      var j = await r.json();
      if (j.oneoff_cookie_reminder_last_unix != null) {
        var srv = Number(j.oneoff_cookie_reminder_last_unix);
        if (!isFinite(srv) || srv < 0) {
          srv = 0;
        }
        var loc = Number(lastOneoffCookieReminderUnix);
        if (!isFinite(loc) || loc < 0) {
          loc = 0;
        }
        /* Do not clobber a fresh client ack with a stale 0 before state is visible on GET. */
        lastOneoffCookieReminderUnix = Math.max(loc, srv);
      }
    } catch {
      /* ignore */
    }
  }

  function clearOneoffCookieBannerTimer() {
    if (oneoffCookieCheckTimer) {
      window.clearInterval(oneoffCookieCheckTimer);
      oneoffCookieCheckTimer = null;
    }
  }

  function maybeShowOneoffCookieBanner() {
    if (!els.oneoffCookieBanner) {
      return;
    }
    if (lastRemindersRequireCookieConfirmManual) {
      els.oneoffCookieBanner.hidden = true;
      els.oneoffCookieBanner.setAttribute("hidden", "");
      return;
    }
    var now = Date.now() / 1000;
    var last = Number(lastOneoffCookieReminderUnix);
    if (!isFinite(last) || last <= 0) {
      last = 0;
    }
    if (last > 0 && now - last < 45 * 60) {
      els.oneoffCookieBanner.hidden = true;
      els.oneoffCookieBanner.setAttribute("hidden", "");
      return;
    }
    els.oneoffCookieBanner.hidden = false;
    els.oneoffCookieBanner.removeAttribute("hidden");
  }

  function scheduleOneoffCookieChecks() {
    clearOneoffCookieBannerTimer();
    syncOneoffCookieReminderFromServer().then(function () {
      maybeShowOneoffCookieBanner();
    });
    oneoffCookieCheckTimer = window.setInterval(function () {
      syncOneoffCookieReminderFromServer().then(function () {
        maybeShowOneoffCookieBanner();
      });
    }, 60 * 1000);
  }

  function renameQueueAddRels(rels) {
    var added = 0;
    (rels || []).forEach(function (rel) {
      var r = String(rel || "").trim().replace(/\\/g, "/");
      if (!r || renameQueueRels.indexOf(r) >= 0) {
        return;
      }
      renameQueueRels.push(r);
      added += 1;
    });
    return added;
  }

  function renderRenameQueue() {
    if (!els.renameQueueBody) {
      return;
    }
    els.renameQueueBody.innerHTML = "";
    renameQueueRels.forEach(function (rel) {
      var tr = document.createElement("tr");
      var td0 = document.createElement("td");
      td0.textContent = rel;
      var td1 = document.createElement("td");
      var rm = document.createElement("button");
      rm.type = "button";
      rm.className = "btn ghost small";
      rm.textContent = "Remove";
      rm.addEventListener("click", function () {
        var ix = renameQueueRels.indexOf(rel);
        if (ix >= 0) {
          renameQueueRels.splice(ix, 1);
        }
        renderRenameQueue();
      });
      td1.appendChild(rm);
      tr.appendChild(td0);
      tr.appendChild(td1);
      els.renameQueueBody.appendChild(tr);
    });
    if (els.renameQueueEmpty) {
      els.renameQueueEmpty.hidden = renameQueueRels.length > 0;
    }
    if (els.renameQueueTable) {
      els.renameQueueTable.hidden = renameQueueRels.length === 0;
    }
  }

  function renderRenamePreviewRows(rows) {
    if (!els.renamePreviewBody) {
      return;
    }
    els.renamePreviewBody.innerHTML = "";
    (rows || []).forEach(function (row) {
      var tr = document.createElement("tr");
      var td0 = document.createElement("td");
      td0.textContent = row.rel || "";
      var td1 = document.createElement("td");
      td1.textContent =
        row.proposed_basename != null ? String(row.proposed_basename) : "—";
      var tdTags = document.createElement("td");
      tdTags.className = "rename-preview-tags";
      tdTags.textContent =
        row.tags_preview != null && row.tags_preview !== ""
          ? String(row.tags_preview)
          : "—";
      var td2 = document.createElement("td");
      td2.textContent = Array.isArray(row.warnings)
        ? row.warnings.join("; ")
        : "";
      tr.appendChild(td0);
      tr.appendChild(td1);
      tr.appendChild(tdTags);
      tr.appendChild(td2);
      els.renamePreviewBody.appendChild(tr);
    });
  }

  function renderRenameLog() {
    if (!els.renameLogBody) {
      return;
    }
    els.renameLogBody.innerHTML = "";
    renameHistoryItems.forEach(function (run) {
      var tr = document.createElement("tr");
      var su = run.started_unix || 0;
      var dt =
        su > 0
          ? new Date(su * 1000).toLocaleString(undefined, {
              dateStyle: "medium",
              timeStyle: "short",
            })
          : "—";
      function td(t) {
        var x = document.createElement("td");
        x.textContent = t;
        return x;
      }
      tr.appendChild(td(dt));
      tr.appendChild(td(String(run.operation || "")));
      tr.appendChild(td(String(run.ok != null ? run.ok : "0")));
      tr.appendChild(td(String(run.skip != null ? run.skip : "0")));
      tr.appendChild(td(String(run.fail != null ? run.fail : "0")));
      tr.appendChild(td(String(run.run_id || "").slice(0, 8) + "…"));
      tr.style.cursor = "pointer";
      tr.title = "Click for per-file detail";
      tr.addEventListener("click", function () {
        if (!els.renameLogDetail) {
          return;
        }
        var lines = (run.items || []).map(function (it) {
          return (
            it.rel +
            " → " +
            (it.new_basename || "") +
            " [" +
            (it.status || "") +
            "] " +
            (it.reason || "")
          );
        });
        els.renameLogDetail.textContent = lines.join("\n") || "(no items)";
        els.renameLogDetail.hidden = false;
      });
      els.renameLogBody.appendChild(tr);
    });
  }

  async function renameRunPreview() {
    if (!els.renameMsg) {
      return;
    }
    els.renameMsg.textContent = "";
    if (els.renameUsageLine) {
      els.renameUsageLine.hidden = true;
      els.renameUsageLine.textContent = "";
    }
    renamePreviewId = null;
    renameLastPreviewRows = [];
    if (els.btnRenameApply) {
      els.btnRenameApply.disabled = true;
    }
    renderRenamePreviewRows([]);
    if (!renameQueueRels.length) {
      els.renameMsg.textContent = "Add at least one file to the queue.";
      return;
    }
    var useDeepl = !els.optRenameUseDeepl || els.optRenameUseDeepl.checked;
    var useExif = !!(els.optRenameUseExif && els.optRenameUseExif.checked);
    if (!useDeepl && !useExif) {
      els.renameMsg.textContent =
        "Enable at least one of DeepL or Exif template in Pipeline.";
      return;
    }
    if (useExif && els.inpRenameExifTemplate && !els.inpRenameExifTemplate.value.trim()) {
      els.renameMsg.textContent = "Enter an Exif template or turn off Exif template.";
      return;
    }
    var body = {
      rels: renameQueueRels.slice(),
      max_files: 50,
      options: {
        whole_basename: !!(els.optRenameWholeBasename && els.optRenameWholeBasename.checked),
        preserve_youtube_id: !els.optRenamePreserveYt || els.optRenamePreserveYt.checked,
        preserve_brackets:
          !els.optRenamePreserveBrackets || els.optRenamePreserveBrackets.checked,
        use_deepl: useDeepl,
        use_exif: useExif,
        pipeline_order:
          els.selRenamePipelineOrder && els.selRenamePipelineOrder.value
            ? els.selRenamePipelineOrder.value
            : "exif_then_deepl",
        exif_template:
          els.inpRenameExifTemplate && els.inpRenameExifTemplate.value
            ? els.inpRenameExifTemplate.value.trim()
            : "",
        exif_missing_policy:
          els.selRenameExifMissing && els.selRenameExifMissing.value
            ? els.selRenameExifMissing.value
            : "keep_basename",
      },
    };
    try {
      var r = await fetch("/api/rename/preview", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      var j = await r.json().catch(function () {
        return {};
      });
      if (!r.ok) {
        var det = j.detail != null ? j.detail : r.statusText;
        els.renameMsg.textContent =
          typeof det === "string" ? det : JSON.stringify(det);
        return;
      }
      renamePreviewId = j.preview_id || null;
      renameLastPreviewRows = j.rows || [];
      renderRenamePreviewRows(renameLastPreviewRows);
      var okApply = false;
      if (renameLastPreviewRows.length) {
        okApply = renameLastPreviewRows.some(function (row) {
          return (
            row.status !== "error" &&
            row.proposed_basename &&
            row.proposed_basename !== row.original_basename
          );
        });
      }
      if (els.btnRenameApply) {
        els.btnRenameApply.disabled = !renamePreviewId || !okApply;
      }
      els.renameMsg.textContent = "Preview ready. Review warnings, then apply if correct.";
      var u = j.usage || {};
      var ukeys = Object.keys(u);
      if (els.renameUsageLine && ukeys.length) {
        els.renameUsageLine.textContent =
          "DeepL usage fields: " + JSON.stringify(u);
        els.renameUsageLine.hidden = false;
      } else if (els.renameUsageLine) {
        els.renameUsageLine.textContent =
          "Character counts may appear here when the API returns them; otherwise see your DeepL dashboard.";
        els.renameUsageLine.hidden = false;
      }
    } catch {
      els.renameMsg.textContent = "Preview failed (network).";
    }
  }

  async function renameRunApply() {
    if (!renamePreviewId || !els.renameMsg) {
      return;
    }
    var n = renameLastPreviewRows.filter(function (row) {
      return (
        row.status !== "error" &&
        row.proposed_basename &&
        row.proposed_basename !== row.original_basename
      );
    }).length;
    if (
      !window.confirm(
        "Apply " +
          n +
          " rename(s) on disk? This cannot be undone from Archive Console."
      )
    ) {
      return;
    }
    els.renameMsg.textContent = "";
    try {
      var r = await fetch("/api/rename/apply", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ preview_id: renamePreviewId }),
      });
      var j = await r.json().catch(function () {
        return {};
      });
      if (!r.ok) {
        var det = j.detail != null ? j.detail : r.statusText;
        els.renameMsg.textContent =
          typeof det === "string" ? det : JSON.stringify(det);
        return;
      }
      els.renameMsg.textContent =
        "Done: OK " +
        (j.ok != null ? j.ok : 0) +
        ", skip " +
        (j.skip != null ? j.skip : 0) +
        ", fail " +
        (j.fail != null ? j.fail : 0) +
        ".";
      renamePreviewId = null;
      renameLastPreviewRows = [];
      if (els.btnRenameApply) {
        els.btnRenameApply.disabled = true;
      }
      renameQueueRels = [];
      renderRenameQueue();
      renderRenamePreviewRows([]);
      void loadRunOverview();
    } catch {
      els.renameMsg.textContent = "Apply failed (network).";
    }
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
        fetch("/api/rename/history"),
      ]);
      var hr = responses[0];
      var rr = responses[1];
      var rh = responses[2];
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
      if (rh.ok) {
        try {
          var rj = await rh.json();
          renameHistoryItems = rj.items || [];
        } catch {
          renameHistoryItems = [];
        }
      } else {
        renameHistoryItems = [];
      }
    } catch {
      historyRenderState.historyLoadFailed = true;
      historyRenderState.reportsLoadFailed = true;
      renameHistoryItems = [];
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
    renderRenameLog();
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

  function onFileListRowActivate(ent, btn, queueOnly) {
    if (ent.is_dir) {
      return;
    }
    selectFile(ent.rel, ent);
    if (queueOnly) {
      fpQueueAppendPlayable(ent.rel, false);
    } else {
      fpPlayTargetRelNow(ent.rel);
    }
  }

  async function browseTo(rel, options) {
    options = options || {};
    var selectRelAfter = options.selectRelAfter;
    selectedRel = "";
    filesListSelectedSet.clear();
    filesListAnchorIndex = -1;
    filesExplorerSetMessage("");
    var reqPath = rel || "";
    var q = reqPath ? "?path=" + encodeURIComponent(reqPath) : "";
    var r = await fetch("/api/files/list" + q);
    if (!r.ok) {
      els.fileList.innerHTML =
        "<li><em class=\"muted\">" + esc(r.status + " " + r.statusText) + "</em></li>";
      updateExplorerButton();
      fpUpdatePlayerActionButtons();
      return;
    }
    var j = await r.json();
    if (j.type === "file") {
      var full = j.path || reqPath;
      var slash = full.lastIndexOf("/");
      var parentDir = slash >= 0 ? full.slice(0, slash) : "";
      await browseTo(parentDir, { selectRelAfter: full });
      return;
    }
    filePath = j.virtual_root ? "" : j.path && j.path !== "." ? j.path : "";
    renderBreadcrumb(filePath);
    els.fileList.innerHTML = "";
    filesListRowModels = (j.entries || []).map(function (ent) {
      return {
        rel: ent.rel,
        is_dir: !!ent.is_dir,
        name: ent.name,
        ent: ent,
      };
    });
    filesListRowModels.forEach(function (row, idx) {
      var ent = row.ent;
      const li = document.createElement("li");
      li.setAttribute("role", "none");
      const btn = document.createElement("button");
      btn.type = "button";
      btn.setAttribute("role", "option");
      btn.dataset.fileRel = ent.rel || "";
      var label = (ent.is_dir ? "📁 " : "📄 ") + ent.name;
      btn.textContent = label;
      btn.setAttribute("title", ent.rel || ent.name);
      btn.setAttribute("aria-selected", "false");
      btn.addEventListener("click", function (ev) {
        if (ev.ctrlKey || ev.metaKey) {
          ev.preventDefault();
          if (filesListSelectedSet.has(ent.rel)) {
            filesListSelectedSet.delete(ent.rel);
          } else {
            filesListSelectedSet.add(ent.rel);
          }
          filesListAnchorIndex = idx;
          filesListApplySelectionVisual();
          selectFile(ent.rel, ent);
          fpUpdatePlayerActionButtons();
          updateExplorerButton();
          return;
        }
        if (ev.shiftKey) {
          ev.preventDefault();
          var anchor =
            filesListAnchorIndex >= 0 ? filesListAnchorIndex : idx;
          filesListSetSelectionToRange(anchor, idx);
          filesListAnchorIndex = anchor;
          selectFile(ent.rel, ent);
          fpUpdatePlayerActionButtons();
          updateExplorerButton();
          return;
        }
        filesListSetSelectionSingle(idx, ent);
        fpUpdatePlayerActionButtons();
        updateExplorerButton();
      });
      btn.addEventListener("dblclick", function (ev) {
        if (ent.is_dir) {
          ev.preventDefault();
          browseTo(ent.rel);
          return;
        }
        ev.preventDefault();
        onFileListRowActivate(ent, btn, ev.altKey);
      });
      btn.addEventListener("keydown", function (e) {
        if (e.key !== "Enter" || e.shiftKey) {
          return;
        }
        e.preventDefault();
        if (ent.is_dir) {
          browseTo(ent.rel);
          return;
        }
        onFileListRowActivate(ent, btn, e.altKey);
      });
      li.appendChild(btn);
      els.fileList.appendChild(li);
    });
    updateExplorerButton();
    fpUpdatePlayerActionButtons();
    fpRefreshPlayerStats();
    if (selectRelAfter) {
      var hitIdx = -1;
      var hitEnt = null;
      for (var hi = 0; hi < filesListRowModels.length; hi++) {
        if (filesListRowModels[hi].rel === selectRelAfter) {
          hitIdx = hi;
          hitEnt = filesListRowModels[hi].ent;
          break;
        }
      }
      if (hitIdx >= 0 && hitEnt) {
        filesListSetSelectionSingle(hitIdx, hitEnt);
      } else {
        selectFile(selectRelAfter, {
          rel: selectRelAfter,
          mtime: 0,
          size: null,
          is_dir: false,
        });
      }
      if (options.autoPlay && filesPlayerIsPlayableRel(selectRelAfter)) {
        fpPlayTargetRelNow(selectRelAfter);
        if (els.filesVideo) {
          window.setTimeout(function () {
            if (els.filesVideo && els.filesVideo.paused) {
              fpMsg(
                "Press Play — the browser may block autoplay after navigation."
              );
              if (els.filesPlayerPlay) {
                els.filesPlayerPlay.classList.add("btn-pulse-hint");
                window.setTimeout(function () {
                  if (els.filesPlayerPlay) {
                    els.filesPlayerPlay.classList.remove("btn-pulse-hint");
                  }
                }, 4500);
              }
            }
          }, 500);
        }
      }
    }
  }

  function consumeWatchIntentFromUrl() {
    var q = new URLSearchParams(window.location.search);
    var rel = q.get("watchRel") || q.get("watch_rel");
    if (!rel) {
      return null;
    }
    var play =
      q.get("watchPlay") === "1" ||
      q.get("watch_play") === "1" ||
      q.get("watchPlay") === "true";
    try {
      var u = new URL(window.location.href);
      u.searchParams.delete("watchRel");
      u.searchParams.delete("watch_rel");
      u.searchParams.delete("watchPlay");
      u.searchParams.delete("watch_play");
      history.replaceState(null, "", u.pathname + u.search + u.hash);
    } catch (_e) {
      void _e;
    }
    return { rel: rel, play: play };
  }

  async function applyFilesWatchIntent(intent) {
    if (!intent || !intent.rel) {
      return;
    }
    var rel = intent.rel;
    var play = !!intent.play;
    var slash = rel.lastIndexOf("/");
    var parentDir = slash >= 0 ? rel.slice(0, slash) : "";
    await browseTo(parentDir, {
      selectRelAfter: rel,
      autoPlay: play,
    });
  }

  async function openFilesViewWithOptionalWatch() {
    var intent = consumeWatchIntentFromUrl();
    await browseTo("");
    if (intent) {
      await applyFilesWatchIntent(intent);
    }
  }

  function renderMediainfoDetailsHtml(details) {
    if (!details || typeof details !== "object") {
      return "<p class=\"muted small\">No details.</p>";
    }
    var parts = [];
    if (details.container) {
      parts.push(
        "<tr><th scope=\"row\">Container</th><td>" +
          esc(String(details.container)) +
          "</td></tr>"
      );
    }
    if (details.format_profile) {
      parts.push(
        "<tr><th scope=\"row\">Profile</th><td>" +
          esc(String(details.format_profile)) +
          "</td></tr>"
      );
    }
    if (details.duration_ms != null) {
      var sec = Number(details.duration_ms) / 1000;
      parts.push(
        "<tr><th scope=\"row\">Duration</th><td>" +
          esc(sec.toFixed(2) + " s") +
          "</td></tr>"
      );
    }
    if (details.overall_bitrate) {
      parts.push(
        "<tr><th scope=\"row\">Overall bitrate</th><td>" +
          esc(String(details.overall_bitrate)) +
          "</td></tr>"
      );
    }
    var streams = details.streams || [];
    streams.forEach(function (s, i) {
      var label = s.kind || "Stream";
      var bits = [];
      if (s.codec) {
        bits.push("codec: " + s.codec);
      }
      if (s.width != null && s.height != null) {
        bits.push(s.width + "×" + s.height);
      }
      if (s.frame_rate) {
        bits.push(s.frame_rate + " fps");
      }
      if (s.chroma_subsampling) {
        bits.push("chroma: " + s.chroma_subsampling);
      }
      if (s.scan_type) {
        bits.push("scan: " + s.scan_type);
      }
      if (s.bitrate) {
        bits.push("bitrate: " + s.bitrate);
      }
      if (s.title) {
        bits.push("title: " + s.title);
      }
      if (s.language) {
        bits.push("lang: " + s.language);
      }
      parts.push(
        "<tr><th scope=\"row\">" +
          esc(label + " " + (i + 1)) +
          "</th><td>" +
          esc(bits.join(" · ") || "—") +
          "</td></tr>"
      );
    });
    if (details.sparse) {
      parts.push(
        "<tr><td colspan=\"2\" class=\"muted small\">Sparse metadata (e.g. some images).</td></tr>"
      );
    }
    return (
      "<table class=\"file-detail-mi-table\">" +
      "<tbody>" +
      parts.join("") +
      "</tbody></table>"
    );
  }

  async function selectFile(rel, ent) {
    if (filesMediainfoController) {
      filesMediainfoController.abort();
      filesMediainfoController = null;
    }
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
    var isDir = !!m.is_dir;
    var links =
      isDir
        ? ""
        : '<p><a class="link" target="_blank" rel="noopener" href="' +
          esc(reportsOpenHref(rel)) +
          '" title="Opens in a new browser tab">Open in new tab</a> · <a class="link" href="' +
          esc(reportsFileHref(rel, true)) +
          '">Download</a></p>';
    var miInner = isDir
      ? "<p class=\"muted small\">Media details (MediaInfo) apply to files only.</p>"
      : "<p class=\"muted small\">Loading media details…</p>";
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
      links +
      '<div class="file-detail-mediainfo" id="fileDetailMediainfo">' +
      "<h3 class=\"file-detail-mi-heading\">Media details</h3>" +
      miInner +
      "</div>";
    updateExplorerButton();
    fpUpdatePlayerActionButtons();
    if (rel && rel === fpCurrentRel()) {
      fpRefreshPlayerStats();
    }
    if (isDir || !rel) {
      return;
    }
    var ac = new AbortController();
    filesMediainfoController = ac;
    try {
      var mr = await fetch(
        "/api/files/mediainfo?path=" + encodeURIComponent(rel),
        { signal: ac.signal, credentials: "same-origin" }
      );
      var mi = mr.ok ? await mr.json() : { ok: false, error: "HTTP " + mr.status };
      if (selectedRel !== rel) {
        return;
      }
      var wrap = document.getElementById("fileDetailMediainfo");
      if (!wrap) {
        return;
      }
      var inner =
        "<h3 class=\"file-detail-mi-heading\">Media details</h3>";
      if (mi.ok && mi.details) {
        inner += renderMediainfoDetailsHtml(mi.details);
      } else {
        inner +=
          "<p class=\"file-detail-mi-error\" role=\"alert\">" +
          esc(mi.error || "MediaInfo failed") +
          "</p>";
      }
      wrap.innerHTML = inner;
    } catch (err) {
      if (err && err.name === "AbortError") {
        return;
      }
      if (selectedRel !== rel) {
        return;
      }
      var wrap2 = document.getElementById("fileDetailMediainfo");
      if (wrap2) {
        wrap2.innerHTML =
          "<h3 class=\"file-detail-mi-heading\">Media details</h3>" +
          "<p class=\"file-detail-mi-error\" role=\"alert\">" +
          esc(err && err.message ? err.message : "Request failed") +
          "</p>";
      }
    } finally {
      if (filesMediainfoController === ac) {
        filesMediainfoController = null;
      }
    }
  }

  async function syncDupRootCheckboxesFromApi() {
    if (!els.dupRootChecks) {
      return;
    }
    try {
      var r = await fetch("/api/settings", { credentials: "same-origin" });
      if (!r.ok) {
        return;
      }
      var j = await r.json();
      dupAllowlistPrefixes = j.allowlisted_rel_prefixes || [];
      renderDupRootCheckboxes();
    } catch (_e) {
      void _e;
    }
  }

  function renderDupRootCheckboxes() {
    if (!els.dupRootChecks) {
      return;
    }
    var parts = [];
    (dupAllowlistPrefixes || []).forEach(function (pref, i) {
      var p = (pref || "").trim();
      if (!p) {
        return;
      }
      var id = "dupRootPref_" + i;
      parts.push(
        '<label class="chk dup-root-label"><input type="checkbox" id="' +
          esc(id) +
          '" data-dup-root="' +
          esc(p) +
          '" /> <span>' +
          esc(p) +
          "</span></label>"
      );
    });
    dupManualRoots.forEach(function (mr, mi) {
      var id = "dupRootMan_" + mi;
      parts.push(
        '<label class="chk dup-root-label"><input type="checkbox" id="' +
          esc(id) +
          '" data-dup-root="' +
          esc(mr) +
          '" checked /> <span>' +
          esc(mr) +
          ' <button type="button" class="btn ghost small dup-root-remove" data-dup-manual="' +
          esc(mr) +
          '">Remove</button></span></label>'
      );
    });
    els.dupRootChecks.innerHTML = parts.join(" ");
    els.dupRootChecks.querySelectorAll(".dup-root-remove").forEach(function (btn) {
      btn.addEventListener("click", function (ev) {
        ev.preventDefault();
        var rel = btn.getAttribute("data-dup-manual");
        dupManualRoots = dupManualRoots.filter(function (x) {
          return x !== rel;
        });
        renderDupRootCheckboxes();
      });
    });
  }

  function collectDupScanRoots() {
    var out = [];
    if (!els.dupRootChecks) {
      return out;
    }
    els.dupRootChecks
      .querySelectorAll('input[type="checkbox"][data-dup-root]:checked')
      .forEach(function (cb) {
        var rel = cb.getAttribute("data-dup-root");
        if (rel && out.indexOf(rel) < 0) {
          out.push(rel);
        }
      });
    return out;
  }

  function stopDupPoll() {
    if (dupPollTimer) {
      clearInterval(dupPollTimer);
      dupPollTimer = null;
    }
  }

  function pollDupStatusLoop() {
    stopDupPoll();
    dupPollTimer = window.setInterval(function () {
      fetch("/api/duplicates/status", { credentials: "same-origin" })
        .then(function (r) {
          return r.json();
        })
        .then(function (j) {
          var ph = j.phase || "idle";
          var prog = j.progress || {};
          if (els.dupScanProgress) {
            els.dupScanProgress.textContent =
              ph === "running"
                ? "Scanning… files listed " +
                  (prog.files_scanned || 0) +
                  ", hashed " +
                  (prog.files_hashed || 0) +
                  ", groups " +
                  (prog.groups_found || 0)
                : ph === "success"
                  ? "Done."
                  : ph === "failed"
                    ? "Failed."
                    : "";
          }
          if (ph !== "running") {
            stopDupPoll();
          }
        })
        .catch(function () {
          stopDupPoll();
        });
    }, 450);
  }

  function renderDupResults() {
    if (!els.dupResults) {
      return;
    }
    if (!dupLastGroups.length) {
      els.dupResults.hidden = false;
      els.dupResults.innerHTML =
        "<p class=\"muted small\">No duplicate groups found.</p>";
      if (els.btnDupPreviewRemove) {
        els.btnDupPreviewRemove.disabled = true;
      }
      if (els.btnDupApplyRemove) {
        els.btnDupApplyRemove.disabled = true;
      }
      return;
    }
    var html = "";
    dupLastGroups.forEach(function (g, gi) {
      var files = g.files || [];
      html +=
        '<div class="dup-group" data-dup-gi="' +
        gi +
        '"><h4 class="dup-group__title">Group ' +
        esc(String(gi + 1)) +
        " · " +
        esc(formatFileSize(g.total_size)) +
        " · <code>" +
        esc((g.content_hash || "").slice(0, 12)) +
        "…</code></h4>";
      files.forEach(function (f, fi) {
        var rel = f.rel || "";
        html +=
          '<div class="dup-group__row">' +
          '<label class="dup-keep"><input type="radio" name="dup_keep_' +
          gi +
          '" value="' +
          esc(rel) +
          '"' +
          (fi === 0 ? " checked" : "") +
          " /> Keep</label>" +
          '<label class="dup-remove"><input type="checkbox" class="dup-cb-remove" data-gi="' +
          gi +
          '" data-rel="' +
          esc(rel) +
          '"' +
          (fi === 0 ? "" : " checked") +
          " /> Remove</label>" +
          '<span class="mono-ellipsis dup-group__path" title="' +
          esc(rel) +
          '">' +
          esc(rel) +
          "</span></div>";
      });
      html += "</div>";
    });
    els.dupResults.innerHTML = html;
    els.dupResults.hidden = false;
    if (els.btnDupPreviewRemove) {
      els.btnDupPreviewRemove.disabled = false;
    }
    if (els.btnDupApplyRemove) {
      els.btnDupApplyRemove.disabled = false;
    }
    els.dupResults.querySelectorAll(".dup-group").forEach(function (grp) {
      var gi = grp.getAttribute("data-dup-gi");
      grp.querySelectorAll('input[type="radio"][name="dup_keep_' + gi + '"]').forEach(
        function (rad) {
          rad.addEventListener("change", function () {
            var keepVal = rad.value;
            grp.querySelectorAll("input.dup-cb-remove").forEach(function (cb) {
              var rr = cb.getAttribute("data-rel");
              cb.checked = rr !== keepVal;
            });
          });
        }
      );
    });
  }

  function collectDupApplyItems() {
    var items = [];
    if (!els.dupResults) {
      return items;
    }
    dupLastGroups.forEach(function (_g, gi) {
      var wrap = els.dupResults.querySelector('[data-dup-gi="' + gi + '"]');
      if (!wrap) {
        return;
      }
      var keepInp = wrap.querySelector(
        'input[type="radio"][name="dup_keep_' + gi + '"]:checked'
      );
      var keep = keepInp ? keepInp.value : "";
      var removes = [];
      wrap.querySelectorAll("input.dup-cb-remove:checked").forEach(function (cb) {
        var rel = cb.getAttribute("data-rel");
        if (rel && rel !== keep) {
          removes.push(rel);
        }
      });
      if (keep && removes.length) {
        items.push({ keep_rel: keep, remove_rels: removes });
      }
    });
    return items;
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
        snooze_days: 0,
        snooze_minutes: opts.snoozeMinutes != null ? opts.snoozeMinutes : 0,
      }),
    });
  }

  function showCookieGateModal() {
    return new Promise(function (resolve) {
      var m = els.cookieGateModal;
      var ack = els.cookieGateAck;
      var cont = els.cookieGateContinue;
      if (!m || !ack || !cont) {
        resolve(false);
        return;
      }
      ack.checked = false;
      cont.disabled = true;
      m.hidden = false;
      m.setAttribute("aria-hidden", "false");
      function cleanup(result) {
        m.hidden = true;
        m.setAttribute("aria-hidden", "true");
        ack.removeEventListener("change", onAck);
        cont.removeEventListener("click", onCont);
        if (els.cookieGateCancel) {
          els.cookieGateCancel.removeEventListener("click", onCancel);
        }
        if (els.cookieGateBackdrop) {
          els.cookieGateBackdrop.removeEventListener("click", onCancel);
        }
        resolve(result);
      }
      function onAck() {
        cont.disabled = !ack.checked;
      }
      function onCont() {
        if (!ack.checked) {
          return;
        }
        cleanup(true);
      }
      function onCancel() {
        cleanup(false);
      }
      ack.addEventListener("change", onAck);
      cont.addEventListener("click", onCont);
      if (els.cookieGateCancel) {
        els.cookieGateCancel.addEventListener("click", onCancel);
      }
      if (els.cookieGateBackdrop) {
        els.cookieGateBackdrop.addEventListener("click", onCancel);
      }
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
      var cmsg = String(c0.message == null ? "" : c0.message).trim();
      lastRemindersCookieShowEligible = !!(c0.show && cmsg);
      lastRemindersCookieMessage = cmsg;
      lastRemindersRequireCookieConfirmManual =
        j.require_cookie_confirm_manual !== false;
      applyTopCookieBannerVisibility();
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
      if (els.runCookieGateHint) {
        if (lastRemindersRequireCookieConfirmManual) {
          els.runCookieGateHint.hidden = false;
        } else {
          els.runCookieGateHint.hidden = true;
        }
      }
      if (els.oneoffCookieGateHint) {
        if (lastRemindersRequireCookieConfirmManual) {
          els.oneoffCookieGateHint.hidden = false;
        } else {
          els.oneoffCookieGateHint.hidden = true;
        }
      }
      if (els.galleryCookieGateHint) {
        if (lastRemindersRequireCookieConfirmManual) {
          els.galleryCookieGateHint.hidden = false;
        } else {
          els.galleryCookieGateHint.hidden = true;
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
    if (els.setFfmpegExe) {
      els.setFfmpegExe.value =
        j.ffmpeg_exe != null && j.ffmpeg_exe !== undefined ? String(j.ffmpeg_exe) : "";
    }
    if (els.setMediainfoExe) {
      els.setMediainfoExe.value =
        j.mediainfo_exe != null && j.mediainfo_exe !== undefined
          ? String(j.mediainfo_exe)
          : "";
    }
    if (els.setExiftoolExe) {
      els.setExiftoolExe.value =
        j.exiftool_exe != null && j.exiftool_exe !== undefined
          ? String(j.exiftool_exe)
          : "";
    }
    if (els.setExiftoolTimeoutSec) {
      var ets = j.exiftool_timeout_sec;
      els.setExiftoolTimeoutSec.value =
        ets != null && ets !== undefined && String(ets) !== ""
          ? String(ets)
          : "45";
    }
    if (els.setDuplicatesQuarantineRel) {
      els.setDuplicatesQuarantineRel.value =
        j.duplicates_quarantine_rel != null &&
        j.duplicates_quarantine_rel !== undefined
          ? String(j.duplicates_quarantine_rel)
          : "logs/_duplicates_quarantine";
    }
    if (els.setDuplicatesPreferQuarantine) {
      els.setDuplicatesPreferQuarantine.checked =
        j.duplicates_prefer_quarantine !== false;
    }
    if (els.dupModeQuarantine && els.dupModeDelete) {
      if (j.duplicates_prefer_quarantine !== false) {
        els.dupModeQuarantine.checked = true;
        els.dupModeDelete.checked = false;
      } else {
        els.dupModeQuarantine.checked = false;
        els.dupModeDelete.checked = true;
      }
    }
    if (els.setDeeplApiKey) {
      els.setDeeplApiKey.value = "";
      els.setDeeplApiKey.placeholder = j.deepl_api_key_configured
        ? "•••••••• (saved — type a new key to replace)"
        : "Paste API key to store in state.json";
    }
    if (els.optDeeplKeyClear) {
      els.optDeeplKeyClear.checked = false;
    }
    if (els.setDeeplEndpointMode) {
      els.setDeeplEndpointMode.value =
        j.deepl_endpoint_mode === "free" || j.deepl_endpoint_mode === "pro"
          ? j.deepl_endpoint_mode
          : "auto";
    }
    if (els.setDeeplSourceLang) {
      els.setDeeplSourceLang.value =
        j.deepl_source_lang != null ? String(j.deepl_source_lang) : "";
    }
    if (els.setDeeplTargetLang) {
      var tgl = j.deepl_target_lang != null ? String(j.deepl_target_lang) : "EN-US";
      els.setDeeplTargetLang.value = tgl || "EN-US";
    }
    if (els.deeplSettingsMsg) {
      els.deeplSettingsMsg.textContent = "";
    }
    dupAllowlistPrefixes = j.allowlisted_rel_prefixes || [];
    if (activeViewId === "library" && els.dupRootChecks) {
      renderDupRootCheckboxes();
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
    if (els.setOneoffReportRetentionDays) {
      els.setOneoffReportRetentionDays.value =
        j.oneoff_report_retention_days != null
          ? j.oneoff_report_retention_days
          : 90;
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
      var cdays =
        ch.remind_interval_days != null ? ch.remind_interval_days : 0;
      els.setCookieRemindDays.value = Math.min(14, cdays);
    }
    var feats = j.features || {};
    if (els.optRequireCookieConfirm) {
      els.optRequireCookieConfirm.checked =
        feats.require_cookie_confirm_manual !== false;
    }
    if (els.optTrayNotifySchedule) {
      els.optTrayNotifySchedule.checked = !!feats.tray_notify_before_schedule;
    }
    if (els.setTrayNotifyPort) {
      els.setTrayNotifyPort.value =
        j.tray_notify_port != null ? j.tray_notify_port : 0;
    }
    if (els.trayNotifyFailureLine) {
      var fu = j.tray_notify_last_failure_unix || 0;
      var fm = String(j.tray_notify_last_failure_message || "").trim();
      if (fu > 0 && fm) {
        els.trayNotifyFailureLine.hidden = false;
        els.trayNotifyFailureLine.textContent =
          "Last tray notify error (port " +
          (j.tray_notify_effective_port != null
            ? j.tray_notify_effective_port
            : "") +
          "): " +
          fm;
      } else {
        els.trayNotifyFailureLine.hidden = true;
        els.trayNotifyFailureLine.textContent = "";
      }
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
    ["watch_later", "channels", "videos", "oneoff", "galleries"].forEach(
      function (k) {
      var o = eff[k];
      if (!o) {
        return;
      }
      var label =
        k === "watch_later"
          ? "Watch Later"
          : k === "channels"
            ? "Channels"
            : k === "videos"
              ? "Videos"
              : k === "galleries"
                ? "Galleries"
                : "One-off";
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
      syncOneoffDirInputs(dd.oneoff != null ? dd.oneoff : "");
      syncGalleriesDirInputs(dd.galleries != null ? dd.galleries : "");
      renderDownloadDirsEffective(j.download_dirs_effective);
      setDownloadDirsBrowseFeedback("");
    } catch {
      /* ignore */
    }
  }

  function setDownloadDirsActionsDisabled(disabled) {
    if (els.btnSaveDownloadDirs) {
      els.btnSaveDownloadDirs.disabled = !!disabled;
    }
    if (els.btnOneoffSaveOutput) {
      els.btnOneoffSaveOutput.disabled = !!disabled;
    }
    if (els.btnGallerySaveOutput) {
      els.btnGallerySaveOutput.disabled = !!disabled;
    }
    document.querySelectorAll(".btn-dl-browse").forEach(function (b) {
      b.disabled = !!disabled;
    });
  }

  /** Folder-picker feedback: Inputs panel + One-off (downloadDirsMsg is off-screen on One-off). */
  function setDownloadDirsBrowseFeedback(msg) {
    var t = msg || "";
    if (els.downloadDirsMsg) {
      els.downloadDirsMsg.textContent = t;
    }
    if (els.oneoffBrowseMsg) {
      els.oneoffBrowseMsg.textContent = t;
    }
    if (els.galleryBrowseMsg) {
      els.galleryBrowseMsg.textContent = t;
    }
  }

  function collectDownloadDirsPayload() {
    return {
      watch_later: (els.dlDirWatchLater && els.dlDirWatchLater.value.trim()) || "",
      channels: (els.dlDirChannels && els.dlDirChannels.value.trim()) || "",
      videos: (els.dlDirVideos && els.dlDirVideos.value.trim()) || "",
      oneoff: getOneoffDirFormValue(),
      galleries: getGalleriesDirFormValue(),
    };
  }

  /**
   * POST download_dirs to state.json. Reloads form + one-off effective line.
   * @returns {{ ok: true } | { ok: false, status: number, errorText: string }}
   */
  async function saveDownloadDirsCore() {
    var r = await fetch("/api/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        download_dirs: collectDownloadDirsPayload(),
      }),
    });
    if (!r.ok) {
      var tx = await r.text();
      return { ok: false, status: r.status, errorText: tx };
    }
    await loadDownloadDirsForm();
    await refreshOneoffOutputEffective();
    return { ok: true };
  }

  async function refreshDownloadDirsPreviewFromForm() {
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
      setDownloadDirsBrowseFeedback("");
      setDownloadDirsActionsDisabled(true);
      try {
        var r = await fetch("/api/settings/download-dirs/browse", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ field: field }),
        });
        if (r.status === 204) {
          setDownloadDirsBrowseFeedback(
            "No folder selected (dialog cancelled or closed)."
          );
          return;
        }
        if (r.status === 503) {
          var d503 = await r.json().catch(function () {
            return {};
          });
          setDownloadDirsBrowseFeedback(
            (d503.detail && String(d503.detail)) ||
              "Folder picker unavailable on this server."
          );
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
          setDownloadDirsBrowseFeedback(
            "Browse failed: " + r.status + " " + detail
          );
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
        if (j.field === "oneoff") {
          syncOneoffDirInputs(j.rel || "");
          if (els.dlDirOneoffPanel) {
            els.dlDirOneoffPanel.focus();
          } else if (els.dlDirOneoffInputs) {
            els.dlDirOneoffInputs.focus();
          }
        }
        if (j.field === "galleries") {
          syncGalleriesDirInputs(j.rel || "");
          if (els.dlDirGalleriesPanel) {
            els.dlDirGalleriesPanel.focus();
          } else if (els.dlDirGalleriesInputs) {
            els.dlDirGalleriesInputs.focus();
          }
        }
        await refreshDownloadDirsPreviewFromForm();
        await refreshOneoffOutputEffective();
        await refreshGalleryOutputEffective();
        if (j.field === "oneoff" || j.field === "galleries") {
          var sv = await saveDownloadDirsCore();
          if (sv.ok) {
            setDownloadDirsBrowseFeedback(
              "Folder selected and saved. This path is stored in settings and kept after restart."
            );
          } else {
            setDownloadDirsBrowseFeedback(
              "Folder selected — save failed (" +
                sv.status +
                "). Click Save output location or use Inputs & config → Save output folders."
            );
          }
        } else {
          setDownloadDirsBrowseFeedback(
            "Folder selected — review under Inputs & config if needed, then Save output folders to persist."
          );
        }
      } catch (ex) {
        setDownloadDirsBrowseFeedback(
          "Browse failed (network or server). Check that Archive Console is running."
        );
      } finally {
        setDownloadDirsActionsDisabled(false);
      }
    });
  });

  /* Navigation */
  els.nav.forEach(function (btn) {
    btn.addEventListener("click", function () {
      const v = btn.getAttribute("data-view");
      clearOneoffCookieBannerTimer();
      activateView(v);
      if (v === "history") {
        loadRunOverview();
      }
      if (v === "library") {
        void openFilesViewWithOptionalWatch();
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
              "yt-dlp.conf editor script did not load. Hard-refresh (Ctrl+F5) or check the browser console / Network tab for /static/ytdlp_setup.js.";
          }
        }
      }
      if (v === "gallerydl") {
        void loadGallerydlFile();
      }
      if (v === "supportedsites") {
        void loadSupportedsites(false);
      }
      if (v === "run") {
        refreshRunPanel();
        refreshCookieReminder();
      }
      if (v === "oneoff") {
        loadDownloadDirsForm();
        loadOneoffRolling();
        refreshOneoffOutputEffective();
        void refreshCookieReminder().then(function () {
          scheduleOneoffCookieChecks();
        });
      }
      if (v === "galleries") {
        loadDownloadDirsForm();
        refreshGalleryOutputEffective();
        void refreshCookieReminder();
      }
      if (v === "rename") {
        renderRenameQueue();
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

  if (els.gallerydlTextarea) {
    els.gallerydlTextarea.addEventListener("input", gallerydlUpdateDirty);
  }
  if (els.btnGallerydlReload) {
    els.btnGallerydlReload.addEventListener("click", function () {
      void gallerydlReloadFromDisk();
    });
  }
  if (els.btnGallerydlSave) {
    els.btnGallerydlSave.addEventListener("click", function () {
      void saveGallerydlFile();
    });
  }
  if (els.linkGalleriesToGallerydl) {
    els.linkGalleriesToGallerydl.addEventListener("click", function (ev) {
      ev.preventDefault();
      clearOneoffCookieBannerTimer();
      activateView("gallerydl");
      void loadGallerydlFile();
    });
  }

  if (els.supportedsitesFilter) {
    els.supportedsitesFilter.addEventListener("input", function () {
      supportedsitesRenderTools();
    });
  }
  if (els.btnSupportedsitesRefresh) {
    els.btnSupportedsitesRefresh.addEventListener("click", function () {
      void loadSupportedsites(true);
    });
  }

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
      if (els.optOneoffLogHighlight) {
        els.optOneoffLogHighlight.checked = els.optLogHighlight.checked;
      }
      if (els.optGalleryLogHighlight) {
        els.optGalleryLogHighlight.checked = els.optLogHighlight.checked;
      }
      rebuildLogViewFromBuffer();
      rebuildOneoffLogViewFromBuffer();
      rebuildGalleryLogViewFromBuffer();
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

  if (els.optOneoffLogWrap) {
    els.optOneoffLogWrap.addEventListener("change", applyLogWrap);
  }
  if (els.optOneoffLogHighlight) {
    if (els.optLogHighlight) {
      els.optOneoffLogHighlight.checked = els.optLogHighlight.checked;
    } else {
      els.optOneoffLogHighlight.checked =
        localStorage.getItem(STORAGE_LOG_HIGHLIGHT) === "1";
    }
    els.optOneoffLogHighlight.addEventListener("change", function () {
      localStorage.setItem(
        STORAGE_LOG_HIGHLIGHT,
        els.optOneoffLogHighlight.checked ? "1" : "0"
      );
      if (els.optLogHighlight) {
        els.optLogHighlight.checked = els.optOneoffLogHighlight.checked;
      }
      if (els.optGalleryLogHighlight) {
        els.optGalleryLogHighlight.checked = els.optOneoffLogHighlight.checked;
      }
      rebuildLogViewFromBuffer();
      rebuildOneoffLogViewFromBuffer();
      rebuildGalleryLogViewFromBuffer();
    });
  }
  if (els.btnOneoffClearLog) {
    els.btnOneoffClearLog.addEventListener("click", clearOneoffLogView);
  }
  if (els.btnOneoffLogFontMinus) {
    els.btnOneoffLogFontMinus.addEventListener("click", function () {
      logFontPx = Math.max(10, logFontPx - 1);
      applyLogFont();
    });
  }
  if (els.btnOneoffLogFontPlus) {
    els.btnOneoffLogFontPlus.addEventListener("click", function () {
      logFontPx = Math.min(22, logFontPx + 1);
      applyLogFont();
    });
  }

  if (els.optGalleryLogWrap) {
    els.optGalleryLogWrap.addEventListener("change", applyLogWrap);
  }
  if (els.optGalleryLogHighlight) {
    if (els.optLogHighlight) {
      els.optGalleryLogHighlight.checked = els.optLogHighlight.checked;
    } else {
      els.optGalleryLogHighlight.checked =
        localStorage.getItem(STORAGE_LOG_HIGHLIGHT) === "1";
    }
    els.optGalleryLogHighlight.addEventListener("change", function () {
      localStorage.setItem(
        STORAGE_LOG_HIGHLIGHT,
        els.optGalleryLogHighlight.checked ? "1" : "0"
      );
      if (els.optLogHighlight) {
        els.optLogHighlight.checked = els.optGalleryLogHighlight.checked;
      }
      if (els.optOneoffLogHighlight) {
        els.optOneoffLogHighlight.checked = els.optGalleryLogHighlight.checked;
      }
      rebuildLogViewFromBuffer();
      rebuildOneoffLogViewFromBuffer();
      rebuildGalleryLogViewFromBuffer();
    });
  }
  if (els.btnGalleryClearLog) {
    els.btnGalleryClearLog.addEventListener("click", clearGalleryLogView);
  }
  if (els.btnGalleryLogFontMinus) {
    els.btnGalleryLogFontMinus.addEventListener("click", function () {
      logFontPx = Math.max(10, logFontPx - 1);
      applyLogFont();
    });
  }
  if (els.btnGalleryLogFontPlus) {
    els.btnGalleryLogFontPlus.addEventListener("click", function () {
      logFontPx = Math.min(22, logFontPx + 1);
      applyLogFont();
    });
  }

  function syncOneoffPanelDirFromInputs() {
    if (els.dlDirOneoffInputs && els.dlDirOneoffPanel) {
      els.dlDirOneoffPanel.value = els.dlDirOneoffInputs.value;
    }
    refreshOneoffOutputEffective();
  }

  function syncOneoffInputsDirFromPanel() {
    if (els.dlDirOneoffInputs && els.dlDirOneoffPanel) {
      els.dlDirOneoffInputs.value = els.dlDirOneoffPanel.value;
    }
    refreshOneoffOutputEffective();
  }

  if (els.dlDirOneoffPanel) {
    els.dlDirOneoffPanel.addEventListener("change", syncOneoffInputsDirFromPanel);
    els.dlDirOneoffPanel.addEventListener("blur", syncOneoffInputsDirFromPanel);
  }
  if (els.dlDirOneoffInputs) {
    els.dlDirOneoffInputs.addEventListener("change", syncOneoffPanelDirFromInputs);
    els.dlDirOneoffInputs.addEventListener("blur", syncOneoffPanelDirFromInputs);
  }

  function syncGalleriesPanelDirFromInputs() {
    if (els.dlDirGalleriesInputs && els.dlDirGalleriesPanel) {
      els.dlDirGalleriesPanel.value = els.dlDirGalleriesInputs.value;
    }
    refreshGalleryOutputEffective();
  }

  function syncGalleriesInputsDirFromPanel() {
    if (els.dlDirGalleriesInputs && els.dlDirGalleriesPanel) {
      els.dlDirGalleriesInputs.value = els.dlDirGalleriesPanel.value;
    }
    refreshGalleryOutputEffective();
  }

  if (els.dlDirGalleriesPanel) {
    els.dlDirGalleriesPanel.addEventListener(
      "change",
      syncGalleriesInputsDirFromPanel
    );
    els.dlDirGalleriesPanel.addEventListener("blur", syncGalleriesInputsDirFromPanel);
  }
  if (els.dlDirGalleriesInputs) {
    els.dlDirGalleriesInputs.addEventListener(
      "change",
      syncGalleriesPanelDirFromInputs
    );
    els.dlDirGalleriesInputs.addEventListener("blur", syncGalleriesPanelDirFromInputs);
  }

  if (els.btnOneoffCookieBannerAck) {
    els.btnOneoffCookieBannerAck.addEventListener("click", async function () {
      var ackBtn = els.btnOneoffCookieBannerAck;
      ackBtn.setAttribute("aria-busy", "true");
      ackBtn.disabled = true;
      try {
        var nowAck = Date.now() / 1000;
        /* Same state as Settings → PATCH; avoids 404 if an older server lacks /api/oneoff/cookie-reminder-ack. */
        var r = await fetch("/api/settings", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            oneoff_cookie_reminder_last_unix: nowAck,
          }),
          credentials: "same-origin",
        });
        if (!r.ok) {
          var detail = r.status + " " + r.statusText;
          try {
            var ej = await r.json();
            if (ej.detail != null) {
              detail =
                typeof ej.detail === "string"
                  ? ej.detail
                  : JSON.stringify(ej.detail);
            }
          } catch (_parse) {
            void _parse;
          }
          if (els.oneoffStartMsg) {
            els.oneoffStartMsg.textContent =
              "Could not acknowledge cookie reminder (" + detail + ").";
          }
          return;
        }
        try {
          await r.json();
        } catch (_body) {
          void _body;
        }
        lastOneoffCookieReminderUnix = nowAck;
        if (els.oneoffCookieBanner) {
          els.oneoffCookieBanner.hidden = true;
          els.oneoffCookieBanner.setAttribute("hidden", "");
        }
        try {
          await syncOneoffCookieReminderFromServer();
        } catch (_sync) {
          void _sync;
        }
        maybeShowOneoffCookieBanner();
        if (els.oneoffStartMsg) {
          els.oneoffStartMsg.textContent = "";
        }
      } catch (_err) {
        if (els.oneoffStartMsg) {
          els.oneoffStartMsg.textContent =
            "Could not acknowledge cookie reminder (network error).";
        }
      } finally {
        ackBtn.removeAttribute("aria-busy");
        ackBtn.disabled = false;
      }
    });
  }

  if (els.btnOneoffWatchNow) {
    els.btnOneoffWatchNow.addEventListener("click", function () {
      if (!oneoffLastMediaRel || els.btnOneoffWatchNow.disabled) {
        return;
      }
      try {
        var u = new URL(window.location.href);
        u.searchParams.set("view", "library");
        u.searchParams.set("watchRel", oneoffLastMediaRel);
        u.searchParams.set("watchPlay", "1");
        history.pushState(null, "", u.toString());
      } catch (_urlErr) {
        void _urlErr;
        return;
      }
      clearOneoffCookieBannerTimer();
      activateView("library");
      void openFilesViewWithOptionalWatch();
    });
  }

  if (els.btnOneoffStart) {
    els.btnOneoffStart.addEventListener("click", async function () {
      if (els.oneoffStartMsg) {
        els.oneoffStartMsg.textContent = "";
      }
      var url = (els.oneoffUrlInput && els.oneoffUrlInput.value.trim()) || "";
      if (!url) {
        if (els.oneoffStartMsg) {
          els.oneoffStartMsg.textContent = "Enter a YouTube URL.";
        }
        return;
      }
      var body = {
        url: url,
        output_rel: getOneoffDirFormValue(),
        dry_run: !!(els.optOneoffDryRun && els.optOneoffDryRun.checked),
        skip_pip_update: !!(els.optOneoffSkipPip && els.optOneoffSkipPip.checked),
        skip_ytdlp_update: !!(
          els.optOneoffSkipYtdlp && els.optOneoffSkipYtdlp.checked
        ),
      };
      let r = await fetch("/api/oneoff/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (r.status === 428) {
        let gate = {};
        try {
          gate = await r.json();
        } catch {
          appendOneoffLogLine(
            "[console] Cookie confirmation required (bad response)."
          );
          return;
        }
        if (gate.error === "cookie_confirm_required") {
          const ok = await showCookieGateModal();
          if (!ok) {
            appendOneoffLogLine(
              "[console] One-off cancelled (cookies not confirmed)."
            );
            return;
          }
          body.cookie_confirm = true;
          r = await fetch("/api/oneoff/start", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
          });
        } else {
          appendOneoffLogLine(
            "[console] Precondition required: " +
              (gate.message || String(r.status))
          );
          return;
        }
      }
      if (r.status === 409) {
        appendOneoffLogLine("[console] " + (await r.text()));
        return;
      }
      if (r.status === 400) {
        var tx = await r.text();
        if (els.oneoffStartMsg) {
          els.oneoffStartMsg.textContent = tx || "Invalid request.";
        }
        return;
      }
      if (!r.ok) {
        if (els.oneoffStartMsg) {
          els.oneoffStartMsg.textContent = "Start failed (" + r.status + ").";
        }
        return;
      }
    });
  }

  if (els.btnOneoffStop) {
    els.btnOneoffStop.addEventListener("click", async function () {
      if (
        !window.confirm(
          "Stop this run? The job may leave partial files on disk. You can re-run or clean up manually."
        )
      ) {
        return;
      }
      var r = await fetch("/api/run/stop", { method: "POST" });
      if (r.status === 409) {
        appendStreamLine("[console] Stop: " + (await r.text()));
        return;
      }
      if (!r.ok) {
        appendStreamLine("[console] Stop failed: " + r.status);
      }
    });
  }

  function renderGalleryPreviewRows(j) {
    var tb = els.galleryPreviewTbody;
    var wrap = els.galleryPreviewTableWrap;
    if (!tb || !wrap) {
      return;
    }
    tb.innerHTML = "";
    var rows = j.rows || [];
    if (!rows.length) {
      wrap.hidden = true;
      wrap.setAttribute("hidden", "");
      return;
    }
    wrap.hidden = false;
    wrap.removeAttribute("hidden");
    rows.forEach(function (row) {
      var tr = document.createElement("tr");
      var type = esc(String(row.type || ""));
      var title = esc(String(row.title || ""));
      var urls = Array.isArray(row.media_urls) ? row.media_urls : [];
      var urlStr = esc(urls.join("\n"));
      var fn = esc(String(row.suggested_filename || ""));
      tr.innerHTML =
        "<td>" +
        type +
        "</td><td>" +
        title +
        "</td><td><code style=\"white-space:pre-wrap;word-break:break-all\">" +
        urlStr +
        "</code></td><td>" +
        fn +
        "</td>";
      tb.appendChild(tr);
    });
  }

  if (els.btnGalleryPreview) {
    els.btnGalleryPreview.addEventListener("click", async function () {
      if (els.galleryPreviewMsg) {
        els.galleryPreviewMsg.textContent = "";
      }
      if (els.galleryDriftNote) {
        els.galleryDriftNote.hidden = true;
        els.galleryDriftNote.setAttribute("hidden", "");
      }
      var url =
        (els.galleryUrlInput && els.galleryUrlInput.value.trim()) || "";
      if (!url) {
        if (els.galleryPreviewMsg) {
          els.galleryPreviewMsg.textContent = "Enter a URL.";
        }
        return;
      }
      els.btnGalleryPreview.disabled = true;
      try {
        var r = await fetch("/api/galleries/preview", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ url: url, timeout_sec: 120 }),
        });
        var j = await r.json().catch(function () {
          return {};
        });
        if (!r.ok) {
          var det =
            j.detail != null
              ? typeof j.detail === "string"
                ? j.detail
                : JSON.stringify(j.detail)
              : await r.text();
          if (els.galleryPreviewMsg) {
            els.galleryPreviewMsg.textContent = "Preview failed: " + det;
          }
          renderGalleryPreviewRows({ rows: [] });
          return;
        }
        galleryLastPreview = {
          rows: j.rows || [],
          truncated: !!j.truncated,
          url: j.url || url,
        };
        if (els.galleryDriftNote && j.drift_note) {
          els.galleryDriftNote.textContent = j.drift_note;
          els.galleryDriftNote.hidden = false;
          els.galleryDriftNote.removeAttribute("hidden");
        }
        var parts = [];
        parts.push("Rows: " + (j.rows || []).length);
        if (j.truncated) {
          parts.push("(truncated at 500)");
        }
        if (j.cookie_required_hint) {
          parts.push(
            "Empty result — try refreshing cookies.txt (Reddit NSFW/private)."
          );
        }
        if (els.galleryPreviewMsg) {
          els.galleryPreviewMsg.textContent = parts.join(" · ");
        }
        renderGalleryPreviewRows(j);
      } catch (_e) {
        if (els.galleryPreviewMsg) {
          els.galleryPreviewMsg.textContent = "Preview failed (network).";
        }
      } finally {
        els.btnGalleryPreview.disabled = false;
      }
    });
  }

  if (els.btnGallerySaveOutput) {
    els.btnGallerySaveOutput.addEventListener("click", async function () {
      if (els.galleryStartMsg) {
        els.galleryStartMsg.textContent = "";
      }
      var sv = await saveDownloadDirsCore();
      if (sv.ok) {
        if (els.galleryStartMsg) {
          els.galleryStartMsg.textContent = "Output location saved.";
        }
        await refreshGalleryOutputEffective();
      } else {
        if (els.galleryStartMsg) {
          els.galleryStartMsg.textContent =
            "Save failed (" + sv.status + "). " + (sv.errorText || "");
        }
      }
    });
  }

  if (els.btnGalleryStart) {
    els.btnGalleryStart.addEventListener("click", async function () {
      if (els.galleryStartMsg) {
        els.galleryStartMsg.textContent = "";
      }
      var url =
        (els.galleryUrlInput && els.galleryUrlInput.value.trim()) || "";
      if (!url) {
        if (els.galleryStartMsg) {
          els.galleryStartMsg.textContent = "Enter a gallery URL.";
        }
        return;
      }
      var snap = null;
      if (galleryLastPreview && galleryLastPreview.url === url) {
        snap = {
          rows: galleryLastPreview.rows,
          truncated: galleryLastPreview.truncated,
          url: galleryLastPreview.url,
        };
      }
      var body = {
        url: url,
        output_rel: getGalleriesDirFormValue(),
        dry_run: !!(els.optGalleryDryRun && els.optGalleryDryRun.checked),
        skip_pip_update: !!(
          els.optGallerySkipPip && els.optGallerySkipPip.checked
        ),
        skip_ytdlp_update: !!(
          els.optGallerySkipYtdlp && els.optGallerySkipYtdlp.checked
        ),
        video_fallback: !!(
          els.optGalleryVideoFallback && els.optGalleryVideoFallback.checked
        ),
        preview_snapshot: snap,
      };
      let r = await fetch("/api/galleries/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (r.status === 428) {
        let gate = {};
        try {
          gate = await r.json();
        } catch {
          appendGalleryLogLine(
            "[console] Cookie confirmation required (bad response)."
          );
          return;
        }
        if (gate.error === "cookie_confirm_required") {
          const ok = await showCookieGateModal();
          if (!ok) {
            appendGalleryLogLine(
              "[console] Galleries run cancelled (cookies not confirmed)."
            );
            return;
          }
          body.cookie_confirm = true;
          r = await fetch("/api/galleries/start", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
          });
        } else {
          appendGalleryLogLine(
            "[console] Precondition required: " +
              (gate.message || String(r.status))
          );
          return;
        }
      }
      if (r.status === 409) {
        appendGalleryLogLine("[console] " + (await r.text()));
        return;
      }
      if (r.status === 400) {
        var tx2 = await r.text();
        if (els.galleryStartMsg) {
          els.galleryStartMsg.textContent = tx2 || "Invalid request.";
        }
        return;
      }
      if (!r.ok) {
        if (els.galleryStartMsg) {
          els.galleryStartMsg.textContent = "Start failed (" + r.status + ").";
        }
        return;
      }
    });
  }

  if (els.btnGalleryStop) {
    els.btnGalleryStop.addEventListener("click", async function () {
      if (
        !window.confirm(
          "Stop this run? The job may leave partial files on disk. You can re-run or clean up manually."
        )
      ) {
        return;
      }
      var r = await fetch("/api/run/stop", { method: "POST" });
      if (r.status === 409) {
        appendStreamLine("[console] Stop: " + (await r.text()));
        return;
      }
      if (!r.ok) {
        appendStreamLine("[console] Stop failed: " + r.status);
      }
    });
  }

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
      appendStreamLine("[console] Stop: " + (await r.text()));
      return;
    }
    if (!r.ok) {
      appendStreamLine("[console] Stop failed: " + r.status);
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
      let r = await fetch("/api/run/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (r.status === 428) {
        let gate = {};
        try {
          gate = await r.json();
        } catch {
          appendLogLine(
            "[console] Cookie confirmation required (bad response)."
          );
          return;
        }
        if (gate.error === "cookie_confirm_required") {
          const ok = await showCookieGateModal();
          if (!ok) {
            appendLogLine(
              "[console] Run cancelled (cookies not confirmed)."
            );
            return;
          }
          body.cookie_confirm = true;
          r = await fetch("/api/run/start", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
          });
        } else {
          appendLogLine(
            "[console] Precondition required: " +
              (gate.message || String(r.status))
          );
          return;
        }
      }
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
    if (els.setFfmpegExe) {
      body.ffmpeg_exe = els.setFfmpegExe.value.trim();
    }
    if (els.setMediainfoExe) {
      body.mediainfo_exe = els.setMediainfoExe.value.trim();
    }
    if (els.setExiftoolExe) {
      body.exiftool_exe = els.setExiftoolExe.value.trim();
    }
    if (els.setExiftoolTimeoutSec) {
      body.exiftool_timeout_sec = Number(els.setExiftoolTimeoutSec.value);
    }
    if (els.setDuplicatesQuarantineRel) {
      body.duplicates_quarantine_rel = els.setDuplicatesQuarantineRel.value.trim();
    }
    if (els.setDuplicatesPreferQuarantine) {
      body.duplicates_prefer_quarantine = els.setDuplicatesPreferQuarantine.checked;
    }
    const r = await fetch("/api/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!r.ok) {
      var failDetail = "Save failed.";
      try {
        var ej = await r.json();
        if (ej.detail != null) {
          failDetail =
            typeof ej.detail === "string" ? ej.detail : JSON.stringify(ej.detail);
        }
      } catch (_e) {
        void _e;
      }
      els.settingsMsg.textContent = failDetail;
      return;
    }
    els.settingsMsg.textContent =
      "Saved. Restart the console if you changed the port.";
    syncDupRootCheckboxesFromApi();
  });

  if (els.btnSaveDeepLSettings) {
    els.btnSaveDeepLSettings.addEventListener("click", async function () {
      if (els.deeplSettingsMsg) {
        els.deeplSettingsMsg.textContent = "";
      }
      var body = {};
      if (els.setDeeplEndpointMode) {
        body.deepl_endpoint_mode = els.setDeeplEndpointMode.value;
      }
      if (els.setDeeplSourceLang) {
        body.deepl_source_lang = els.setDeeplSourceLang.value.trim();
      }
      if (els.setDeeplTargetLang) {
        body.deepl_target_lang = els.setDeeplTargetLang.value.trim() || "EN-US";
      }
      if (els.optDeeplKeyClear && els.optDeeplKeyClear.checked) {
        body.deepl_api_key_clear = true;
      } else if (els.setDeeplApiKey && els.setDeeplApiKey.value.trim()) {
        body.deepl_api_key = els.setDeeplApiKey.value.trim();
      }
      var r = await fetch("/api/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!r.ok) {
        var dmsg = "Save failed.";
        try {
          var dj = await r.json();
          if (dj.detail != null) {
            dmsg =
              typeof dj.detail === "string" ? dj.detail : JSON.stringify(dj.detail);
          }
        } catch (_d) {
          void _d;
        }
        if (els.deeplSettingsMsg) {
          els.deeplSettingsMsg.textContent = dmsg;
        }
        return;
      }
      await loadSettingsForm();
      if (els.deeplSettingsMsg) {
        els.deeplSettingsMsg.textContent = "DeepL settings saved.";
      }
    });
  }

  if (els.btnLibraryQueueRename) {
    els.btnLibraryQueueRename.addEventListener("click", function () {
      var rels = filesListPlayableSelectedInOrder();
      if (!rels.length) {
        fpMsg("Select playable file(s) in the list first.");
        return;
      }
      var a = renameQueueAddRels(rels);
      fpMsg(
        "Added " +
          a +
          " file(s) to the Rename queue (sidebar → Rename)."
      );
    });
  }

  if (els.btnRenameAddFromLibrary) {
    els.btnRenameAddFromLibrary.addEventListener("click", function () {
      var rels = filesListPlayableSelectedInOrder();
      if (!rels.length) {
        if (els.renameMsg) {
          els.renameMsg.textContent =
            "No Library selection — open Library, select files, then try again.";
        }
        return;
      }
      renameQueueAddRels(rels);
      renderRenameQueue();
      if (els.renameMsg) {
        els.renameMsg.textContent = "Queued from Library selection.";
      }
    });
  }

  if (els.btnRenameClearQueue) {
    els.btnRenameClearQueue.addEventListener("click", function () {
      renameQueueRels = [];
      renamePreviewId = null;
      renameLastPreviewRows = [];
      renderRenameQueue();
      renderRenamePreviewRows([]);
      if (els.btnRenameApply) {
        els.btnRenameApply.disabled = true;
      }
      if (els.renameMsg) {
        els.renameMsg.textContent = "";
      }
      if (els.renameUsageLine) {
        els.renameUsageLine.hidden = true;
      }
    });
  }

  if (els.btnRenamePreview) {
    els.btnRenamePreview.addEventListener("click", function () {
      void renameRunPreview();
    });
  }

  if (els.btnRenameApply) {
    els.btnRenameApply.addEventListener("click", function () {
      void renameRunApply();
    });
  }

  if (els.btnDupAddCurrentFolder) {
    els.btnDupAddCurrentFolder.addEventListener("click", function () {
      if (!filePath || !String(filePath).trim()) {
        fpMsg("Open a folder in the tree (not only virtual roots), then add it.");
        return;
      }
      if (dupManualRoots.indexOf(filePath) < 0) {
        dupManualRoots.push(filePath);
        renderDupRootCheckboxes();
      }
    });
  }

  if (els.btnDupScan) {
    els.btnDupScan.addEventListener("click", async function () {
      var roots = collectDupScanRoots();
      if (!roots.length) {
        fpMsg("Select at least one scan root (checkbox or Add current folder).");
        return;
      }
      dupLastGroups = [];
      if (els.dupResults) {
        els.dupResults.hidden = true;
        els.dupResults.innerHTML = "";
      }
      if (els.dupPreviewOut) {
        els.dupPreviewOut.hidden = true;
        els.dupPreviewOut.textContent = "";
      }
      if (els.btnDupPreviewRemove) {
        els.btnDupPreviewRemove.disabled = true;
      }
      if (els.btnDupApplyRemove) {
        els.btnDupApplyRemove.disabled = true;
      }
      if (els.dupScanProgress) {
        els.dupScanProgress.textContent = "Starting…";
      }
      pollDupStatusLoop();
      try {
        var r = await fetch("/api/duplicates/scan", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            root_rels: roots,
            include_video: !!(els.dupIncludeVideo && els.dupIncludeVideo.checked),
            include_images: !!(els.dupIncludeImages && els.dupIncludeImages.checked),
          }),
          credentials: "same-origin",
        });
        if (!r.ok) {
          var detail = r.status + " " + r.statusText;
          try {
            var ej = await r.json();
            if (ej.detail != null) {
              detail =
                typeof ej.detail === "string" ? ej.detail : JSON.stringify(ej.detail);
            }
          } catch (_p) {
            void _p;
          }
          fpMsg("Scan failed: " + detail);
          return;
        }
        for (;;) {
          await new Promise(function (res) {
            setTimeout(res, 450);
          });
          var rs = await fetch("/api/duplicates/status", {
            credentials: "same-origin",
          });
          var st = await rs.json();
          if ((st.phase || "") !== "running") {
            if (st.scan && st.scan.error) {
              fpMsg("Scan error: " + st.scan.error);
              dupLastGroups = [];
            } else {
              dupLastGroups = (st.scan && st.scan.groups) || [];
            }
            renderDupResults();
            break;
          }
        }
      } catch (e) {
        fpMsg("Scan failed: " + (e && e.message ? e.message : String(e)));
      } finally {
        stopDupPoll();
        if (els.dupScanProgress) {
          els.dupScanProgress.textContent = "";
        }
      }
    });
  }

  if (els.btnDupPreviewRemove) {
    els.btnDupPreviewRemove.addEventListener("click", async function () {
      var items = collectDupApplyItems();
      if (!items.length) {
        fpMsg("No removals selected (check Remove on duplicates to drop).");
        return;
      }
      var mode =
        els.dupModeDelete && els.dupModeDelete.checked ? "delete" : "quarantine";
      try {
        var r = await fetch("/api/duplicates/apply", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            dry_run: true,
            mode: mode,
            items: items,
            confirm: "",
          }),
          credentials: "same-origin",
        });
        var j = await r.json();
        if (!r.ok) {
          fpMsg(
            "Preview failed: " +
              (j.detail != null ? String(j.detail) : r.statusText)
          );
          return;
        }
        if (els.dupPreviewOut) {
          els.dupPreviewOut.textContent = JSON.stringify(j, null, 2);
          els.dupPreviewOut.hidden = false;
        }
        fpMsg(
          "Dry-run: would remove " +
            (j.removed_count || 0) +
            " file(s), " +
            formatFileSize(j.bytes_reclaimed) +
            "."
        );
      } catch (e) {
        fpMsg("Preview failed: " + (e && e.message));
      }
    });
  }

  if (els.btnDupApplyRemove) {
    els.btnDupApplyRemove.addEventListener("click", async function () {
      var items = collectDupApplyItems();
      if (!items.length) {
        fpMsg("No removals selected.");
        return;
      }
      var n = 0;
      var bytes = 0;
      items.forEach(function (it) {
        n += (it.remove_rels || []).length;
        /* size unknown without re-fetch; server returns on dry_run */
      });
      var mode =
        els.dupModeDelete && els.dupModeDelete.checked ? "delete" : "quarantine";
      var pr = await fetch("/api/duplicates/apply", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          dry_run: true,
          mode: mode,
          items: items,
          confirm: "",
        }),
        credentials: "same-origin",
      });
      var pj = await pr.json();
      if (pr.ok && pj.bytes_reclaimed != null) {
        bytes = pj.bytes_reclaimed;
        n = pj.removed_count || n;
      }
      var ok1 = window.confirm(
        "Remove " +
          n +
          " duplicate file(s), reclaim about " +
          formatFileSize(bytes) +
          "? This cannot be undone (except from backups)."
      );
      if (!ok1) {
        return;
      }
      var typed = window.prompt(
        'Type DELETE_DUPLICATES to confirm destructive apply:'
      );
      if ((typed || "").trim() !== "DELETE_DUPLICATES") {
        fpMsg("Apply cancelled (confirmation text did not match).");
        return;
      }
      try {
        var r = await fetch("/api/duplicates/apply", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            dry_run: false,
            mode: mode,
            items: items,
            confirm: "DELETE_DUPLICATES",
          }),
          credentials: "same-origin",
        });
        var j = await r.json();
        if (!r.ok) {
          fpMsg(
            "Apply failed: " +
              (j.detail != null ? String(j.detail) : r.statusText)
          );
          return;
        }
        fpMsg(
          "Removed " +
            (j.removed_count || 0) +
            " file(s); reclaimed " +
            formatFileSize(j.bytes_reclaimed || 0) +
            "."
        );
        dupLastGroups = [];
        if (els.dupResults) {
          els.dupResults.hidden = true;
          els.dupResults.innerHTML = "";
        }
        if (els.dupPreviewOut) {
          els.dupPreviewOut.hidden = true;
        }
        if (els.btnDupPreviewRemove) {
          els.btnDupPreviewRemove.disabled = true;
        }
        if (els.btnDupApplyRemove) {
          els.btnDupApplyRemove.disabled = true;
        }
      } catch (e) {
        fpMsg("Apply failed: " + (e && e.message));
      }
    });
  }

  function shutdownModalSyncConfirmButton() {
    var inp = els.shutdownGateInput;
    var btn = els.shutdownGateConfirm;
    if (!inp || !btn) {
      return;
    }
    btn.disabled = inp.value.trim() !== "SHUTDOWN";
  }

  var shutdownFetchController = null;
  var shutdownFetchUserAbort = false;

  function openShutdownModal() {
    if (!els.shutdownGateModal) {
      return;
    }
    shutdownFetchUserAbort = false;
    if (els.shutdownSettingsMsg) {
      els.shutdownSettingsMsg.textContent = "";
    }
    if (els.shutdownGateBusy) {
      els.shutdownGateBusy.hidden = true;
      els.shutdownGateBusy.textContent = "";
    }
    if (els.shutdownGateInput) {
      els.shutdownGateInput.value = "";
      els.shutdownGateInput.disabled = false;
    }
    if (els.shutdownGateToken) {
      els.shutdownGateToken.value = "";
      els.shutdownGateToken.disabled = false;
    }
    if (els.shutdownGateCancel) {
      els.shutdownGateCancel.disabled = false;
    }
    shutdownModalSyncConfirmButton();
    els.shutdownGateModal.hidden = false;
    els.shutdownGateModal.setAttribute("aria-hidden", "false");
    if (els.shutdownGateInput) {
      els.shutdownGateInput.focus();
    }
  }

  function closeShutdownModal() {
    if (els.shutdownGateModal) {
      els.shutdownGateModal.hidden = true;
      els.shutdownGateModal.setAttribute("aria-hidden", "true");
    }
    if (els.shutdownGateBusy) {
      els.shutdownGateBusy.hidden = true;
      els.shutdownGateBusy.textContent = "";
    }
    if (els.shutdownGateInput) {
      els.shutdownGateInput.disabled = false;
    }
    if (els.shutdownGateToken) {
      els.shutdownGateToken.disabled = false;
    }
    if (els.shutdownGateCancel) {
      els.shutdownGateCancel.disabled = false;
    }
    shutdownModalSyncConfirmButton();
  }

  if (els.btnShutdownServer) {
    els.btnShutdownServer.addEventListener("click", function () {
      openShutdownModal();
    });
  }
  if (els.shutdownGateInput) {
    els.shutdownGateInput.addEventListener("input", shutdownModalSyncConfirmButton);
  }
  function onShutdownCancel() {
    shutdownFetchUserAbort = true;
    if (shutdownFetchController) {
      try {
        shutdownFetchController.abort();
      } catch {
        /* ignore */
      }
      shutdownFetchController = null;
    }
    closeShutdownModal();
  }
  if (els.shutdownGateCancel) {
    els.shutdownGateCancel.addEventListener("click", onShutdownCancel);
  }
  if (els.shutdownGateBackdrop) {
    els.shutdownGateBackdrop.addEventListener("click", onShutdownCancel);
  }
  function showServerStoppedStaticPage() {
    var html =
      "<!DOCTYPE html><html lang=\"en\"><head><meta charset=\"utf-8\"/>" +
      "<title>Archive Console — stopped</title>" +
      "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"/>" +
      "<style>body{font-family:system-ui,-apple-system,sans-serif;background:#0a0b0d;color:#e8eaef;margin:0;padding:2rem;line-height:1.5}" +
      "h1{font-size:1.25rem;font-weight:600}p{opacity:.85;max-width:36rem;margin:0 0 1rem}</style></head><body>" +
      "<h1>Server stopped</h1>" +
      "<p>The Archive Console HTTP server has exited and the listen port should be free. You can close this tab.</p>" +
      "<p class=\"muted\" style=\"opacity:.65;font-size:.9rem\">If you use tray <strong>spawn</strong> mode, the tray icon should exit shortly after the server process ends.</p>" +
      "</body></html>";
    document.open();
    document.write(html);
    document.close();
  }

  if (els.shutdownGateConfirm) {
    els.shutdownGateConfirm.addEventListener("click", async function () {
      if (!els.shutdownGateInput || els.shutdownGateInput.value.trim() !== "SHUTDOWN") {
        return;
      }
      var headers = { "Content-Type": "application/json" };
      var tok =
        els.shutdownGateToken && els.shutdownGateToken.value
          ? els.shutdownGateToken.value.trim()
          : "";
      if (tok) {
        headers["X-Archive-Shutdown-Token"] = tok;
      }
      if (els.shutdownGateBusy) {
        els.shutdownGateBusy.hidden = false;
        els.shutdownGateBusy.textContent = "Stopping server…";
      }
      if (els.shutdownGateInput) {
        els.shutdownGateInput.disabled = true;
      }
      if (els.shutdownGateToken) {
        els.shutdownGateToken.disabled = true;
      }
      if (els.shutdownGateConfirm) {
        els.shutdownGateConfirm.disabled = true;
      }
      if (els.shutdownGateCancel) {
        els.shutdownGateCancel.disabled = false;
      }
      var ac = new AbortController();
      shutdownFetchController = ac;
      var abortTimer = window.setTimeout(function () {
        try {
          ac.abort();
        } catch {
          /* ignore */
        }
      }, 8000);
      try {
        var r = await fetch("/api/shutdown", {
          method: "POST",
          headers: headers,
          body: JSON.stringify({ confirm: "SHUTDOWN" }),
          signal: ac.signal,
        });
        window.clearTimeout(abortTimer);
        shutdownFetchController = null;
        if (!r.ok) {
          closeShutdownModal();
          var err = "Stop request failed (" + r.status + ").";
          try {
            var ej = await r.json();
            if (ej.detail) {
              err =
                typeof ej.detail === "string"
                  ? ej.detail
                  : JSON.stringify(ej.detail);
            }
          } catch {
            /* ignore */
          }
          if (els.shutdownSettingsMsg) {
            els.shutdownSettingsMsg.textContent = err;
          }
          return;
        }
        closeShutdownModal();
        window.setTimeout(function () {
          showServerStoppedStaticPage();
        }, 300);
      } catch (e) {
        window.clearTimeout(abortTimer);
        shutdownFetchController = null;
        closeShutdownModal();
        if (shutdownFetchUserAbort || (e && e.name === "AbortError")) {
          if (!shutdownFetchUserAbort && els.shutdownSettingsMsg) {
            els.shutdownSettingsMsg.textContent =
              "Stop request timed out — server may still be running; check the process or tray.";
          }
          return;
        }
        if (els.shutdownSettingsMsg) {
          els.shutdownSettingsMsg.textContent =
            "Connection lost (server may have stopped).";
        }
      }
    });
  }

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
      var oort = els.setOneoffReportRetentionDays
        ? Number(els.setOneoffReportRetentionDays.value)
        : 90;
      if (!isFinite(oort) || oort < 1) {
        if (els.storageCleanupMsg) {
          els.storageCleanupMsg.textContent =
            "One-off rolling report retention must be at least 1.";
        }
        return;
      }
      var r = await fetch("/api/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          storage_retention: pl,
          oneoff_report_retention_days: Math.floor(oort),
        }),
      });
      if (!r.ok) {
        if (els.storageCleanupMsg) {
          els.storageCleanupMsg.textContent = "Save failed.";
        }
        return;
      }
      if (els.storageCleanupMsg) {
        els.storageCleanupMsg.textContent =
          "Retention preferences saved (including one-off rolling report epoch).";
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
      var payload = {
        cookie_hygiene: {
          remind_interval_days: Math.min(
            14,
            Number(els.setCookieRemindDays.value)
          ),
          last_acknowledged_unix: lastCookieHygiene.last_acknowledged_unix || 0,
          snooze_until_unix: lastCookieHygiene.snooze_until_unix || 0,
        },
        pre_run_reminder: {
          minutes_before: Number(els.setPreRunMinutes && els.setPreRunMinutes.value),
          snooze_until_unix: lastPreRunReminder.snooze_until_unix || 0,
          acknowledged_fire_key: lastPreRunReminder.acknowledged_fire_key || "",
        },
      };
      if (els.optRequireCookieConfirm) {
        payload.require_cookie_confirm_manual =
          !!els.optRequireCookieConfirm.checked;
      }
      if (els.optTrayNotifySchedule) {
        payload.tray_notify_before_schedule =
          !!els.optTrayNotifySchedule.checked;
      }
      if (els.setTrayNotifyPort) {
        payload.tray_notify_port = Number(els.setTrayNotifyPort.value);
      }
      var r = await fetch("/api/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
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

  function bindCookieSnoozeMinutes(btn, minutes) {
    if (!btn) {
      return;
    }
    btn.addEventListener("click", async function () {
      var r = await postCookieHygieneAction({ snoozeMinutes: minutes });
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
  bindCookieSnoozeMinutes(els.btnCookieSnooze1h, 60);
  bindCookieSnoozeMinutes(els.btnCookieSnooze3h, 180);

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
      if (els.oneoffBrowseMsg) {
        els.oneoffBrowseMsg.textContent = "";
      }
      setDownloadDirsActionsDisabled(true);
      try {
        var result = await saveDownloadDirsCore();
        if (!result.ok) {
          if (els.downloadDirsMsg) {
            els.downloadDirsMsg.textContent =
              "Save failed: " + result.status + " " + result.errorText;
          }
          return;
        }
        if (els.downloadDirsMsg) {
          els.downloadDirsMsg.textContent = "Output folders saved.";
        }
      } finally {
        setDownloadDirsActionsDisabled(false);
      }
    });
  }

  if (els.btnOneoffSaveOutput) {
    els.btnOneoffSaveOutput.addEventListener("click", async function () {
      if (els.oneoffBrowseMsg) {
        els.oneoffBrowseMsg.textContent = "";
      }
      if (els.downloadDirsMsg) {
        els.downloadDirsMsg.textContent = "";
      }
      setDownloadDirsActionsDisabled(true);
      try {
        var res = await saveDownloadDirsCore();
        if (!res.ok) {
          if (els.oneoffBrowseMsg) {
            els.oneoffBrowseMsg.textContent =
              "Save failed: " + res.status + " " + res.errorText;
          }
          return;
        }
        if (els.oneoffBrowseMsg) {
          els.oneoffBrowseMsg.textContent =
            "Output location saved — same path after restart.";
        }
      } finally {
        setDownloadDirsActionsDisabled(false);
      }
    });
  }

  connectStream();
  window.setInterval(refreshReminders, 120000);
  var initialView = getInitialViewFromUrl();
  activateView(initialView);
  if (initialView === "inputs") {
    loadDownloadDirsForm();
  }
  if (initialView === "settings") {
    loadSettingsForm();
  }
  if (initialView === "oneoff") {
    loadDownloadDirsForm();
    loadOneoffRolling();
    refreshOneoffOutputEffective();
    void refreshReminders().then(function () {
      scheduleOneoffCookieChecks();
    });
  } else if (initialView === "galleries") {
    loadDownloadDirsForm();
    refreshGalleryOutputEffective();
    void refreshReminders();
  } else {
    void refreshReminders();
  }
  if (initialView === "library") {
    void openFilesViewWithOptionalWatch();
  }
  if (initialView === "rename") {
    renderRenameQueue();
  }
  if (initialView === "gallerydl") {
    void loadGallerydlFile();
  }
  if (initialView === "supportedsites") {
    void loadSupportedsites(false);
  }
  loadRunOverview();
  applyLogFont();
  applyLogWrap();
  scrollHistorySectionFromUrl();
  initFilesSplitResizer();
  initFilesWorkspaceShellResize();
  fpInitPlayerUi();
  fetch("/api/run/status")
    .then(function (r) {
      return r.json();
    })
    .then(function (j) {
      if (j.phase) {
        setPhase(j.phase);
      }
      renderRunPanel(j);
      if (j.phase === "running" && j.run && j.run.job) {
        activeStreamJob = j.run.job;
      } else {
        activeStreamJob = null;
      }
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
