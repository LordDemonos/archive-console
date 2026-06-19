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
    optPreflightViaExtension: document.getElementById("optPreflightViaExtension"),
    optPreflightWaitRow: document.getElementById("optPreflightWaitRow"),
    optPreflightWaitSec: document.getElementById("optPreflightWaitSec"),
    optPauseOnCookieError: document.getElementById("optPauseOnCookieError"),
    optCookieAuthPollRow: document.getElementById("optCookieAuthPollRow"),
    optCookieAuthPollSec: document.getElementById("optCookieAuthPollSec"),
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
    filesListFilter: document.getElementById("filesListFilter"),
    btnLibraryFileListFontMinus: document.getElementById(
      "btnLibraryFileListFontMinus"
    ),
    btnLibraryFileListFontPlus: document.getElementById(
      "btnLibraryFileListFontPlus"
    ),
    fileDetail: document.getElementById("fileDetail"),
    fileDetailMain: document.getElementById("fileDetailMain"),
    btnFileDetailSendRename: document.getElementById("btnFileDetailSendRename"),
    btnFileDetailAddPlayerQueue: document.getElementById("btnFileDetailAddPlayerQueue"),
    fileDetailRenameSendHint: document.getElementById("fileDetailRenameSendHint"),
    fileDetailPlayerQueueHint: document.getElementById("fileDetailPlayerQueueHint"),
    filesWorkspace: document.getElementById("filesWorkspace"),
    filesWorkspaceShell: document.getElementById("filesWorkspaceShell"),
    filesLibraryPlayerBand: document.getElementById("filesLibraryPlayerBand"),
    filesLibraryExportBand: document.getElementById("filesLibraryExportBand"),
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
    libraryViewToast: document.getElementById("libraryViewToast"),
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
    renameQueueBody: document.getElementById("renameQueueBody"),
    renameQueueEmpty: document.getElementById("renameQueueEmpty"),
    renameQueueTable: document.getElementById("renameQueueTable"),
    btnRenameBrowseFiles: document.getElementById("btnRenameBrowseFiles"),
    btnRenameClearQueue: document.getElementById("btnRenameClearQueue"),
    inpRenameFolderRel: document.getElementById("inpRenameFolderRel"),
    btnRenameBrowseFolder: document.getElementById("btnRenameBrowseFolder"),
    optRenameFolderRecursive: document.getElementById("optRenameFolderRecursive"),
    optRenameFolderSkipDone: document.getElementById("optRenameFolderSkipDone"),
    optRenameFolderTouchMtime: document.getElementById("optRenameFolderTouchMtime"),
    selRenameFolderBatchSize: document.getElementById("selRenameFolderBatchSize"),
    btnRenameFolderScan: document.getElementById("btnRenameFolderScan"),
    btnRenameFolderRun: document.getElementById("btnRenameFolderRun"),
    btnRenameFolderStop: document.getElementById("btnRenameFolderStop"),
    renameFolderStatus: document.getElementById("renameFolderStatus"),
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
    renameDeeplQuotaLine: document.getElementById("renameDeeplQuotaLine"),
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
    setAllowSummary: document.getElementById("setAllowSummary"),
    setFfmpegExe: document.getElementById("setFfmpegExe"),
    setGifskiExe: document.getElementById("setGifskiExe"),
    setCzkawkaExe: document.getElementById("setCzkawkaExe"),
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
    btnDupReset: document.getElementById("btnDupReset"),
    dupScanProgress: document.getElementById("dupScanProgress"),
    dupResults: document.getElementById("dupResults"),
    dupPreviewOut: document.getElementById("dupPreviewOut"),
    btnDupPreviewRemove: document.getElementById("btnDupPreviewRemove"),
    btnDupApplyRemove: document.getElementById("btnDupApplyRemove"),
    dupModeQuarantine: document.getElementById("dupModeQuarantine"),
    dupModeDelete: document.getElementById("dupModeDelete"),
    btnSaveSettings: document.getElementById("btnSaveSettings"),
    settingsMsg: document.getElementById("settingsMsg"),
    setArchiveRoot: document.getElementById("setArchiveRoot"),
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
    optSchedulerEnabled: document.getElementById("optSchedulerEnabled"),
    btnSaveSchedulerGlobal: document.getElementById("btnSaveSchedulerGlobal"),
    schedulerGlobalSaveMsg: document.getElementById("schedulerGlobalSaveMsg"),
    youtubeSchedulerHint: document.getElementById("youtubeSchedulerHint"),
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
    optGotifyEnabled: document.getElementById("optGotifyEnabled"),
    setGotifyBaseUrl: document.getElementById("setGotifyBaseUrl"),
    setGotifyAppToken: document.getElementById("setGotifyAppToken"),
    optGotifyNotifyStart: document.getElementById("optGotifyNotifyStart"),
    optGotifyNotifyComplete: document.getElementById("optGotifyNotifyComplete"),
    optGotifyNotifyScheduled: document.getElementById("optGotifyNotifyScheduled"),
    optGotifyNotifyManual: document.getElementById("optGotifyNotifyManual"),
    setGotifyPriority: document.getElementById("setGotifyPriority"),
    btnSaveGotifySettings: document.getElementById("btnSaveGotifySettings"),
    btnGotifyTest: document.getElementById("btnGotifyTest"),
    gotifySettingsMsg: document.getElementById("gotifySettingsMsg"),
    gotifyFailureLine: document.getElementById("gotifyFailureLine"),
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
    cookiesCalloutText: document.getElementById("cookiesCalloutText"),
    optUnlockCookies: document.getElementById("optUnlockCookies"),
    siteCookiesList: document.getElementById("siteCookiesList"),
    siteCookiesEmpty: document.getElementById("siteCookiesEmpty"),
    siteCookieNewName: document.getElementById("siteCookieNewName"),
    btnSiteCookieAdd: document.getElementById("btnSiteCookieAdd"),
    btnSiteCookiesRefresh: document.getElementById("btnSiteCookiesRefresh"),
    siteCookiesMsg: document.getElementById("siteCookiesMsg"),
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
    btnGalleryRunSelected: document.getElementById("btnGalleryRunSelected"),
    btnGallerySaveCurrent: document.getElementById("btnGallerySaveCurrent"),
    btnGallerySourcesSelectAll: document.getElementById("btnGallerySourcesSelectAll"),
    btnGallerySourcesSelectNone: document.getElementById("btnGallerySourcesSelectNone"),
    btnGalleryRemoveSelected: document.getElementById("btnGalleryRemoveSelected"),
    gallerySourcesTbody: document.getElementById("gallerySourcesTbody"),
    gallerySourcesTableWrap: document.getElementById("gallerySourcesTableWrap"),
    gallerySourcesScroll: document.getElementById("gallerySourcesScroll"),
    gallerySourcesCountBadge: document.getElementById("gallerySourcesCountBadge"),
    gallerySourcesEmpty: document.getElementById("gallerySourcesEmpty"),
    gallerySourcesMsg: document.getElementById("gallerySourcesMsg"),
    gallerySourcesScheduleEnabled: document.getElementById("gallerySourcesScheduleEnabled"),
    gallerySourcesScheduleFreq: document.getElementById("gallerySourcesScheduleFreq"),
    gallerySourcesScheduleDowWrap: document.getElementById("gallerySourcesScheduleDowWrap"),
    gallerySourcesScheduleDow: document.getElementById("gallerySourcesScheduleDow"),
    gallerySourcesScheduleDayWrap: document.getElementById("gallerySourcesScheduleDayWrap"),
    gallerySourcesScheduleDay: document.getElementById("gallerySourcesScheduleDay"),
    gallerySourcesScheduleHour: document.getElementById("gallerySourcesScheduleHour"),
    gallerySourcesScheduleMin: document.getElementById("gallerySourcesScheduleMin"),
    gallerySourcesScheduleMaxHours: document.getElementById("gallerySourcesScheduleMaxHours"),
    btnSaveGallerySourcesSchedule: document.getElementById("btnSaveGallerySourcesSchedule"),
    gallerySourcesScheduleStatus: document.getElementById("gallerySourcesScheduleStatus"),
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
    optGalleryUpdateGalleryDl: document.getElementById("optGalleryUpdateGalleryDl"),
    galleryLogBody: document.getElementById("galleryLogBody"),
    galleryLogGutter: document.getElementById("galleryLogGutter"),
    galleryLogFrame: document.getElementById("galleryLogFrame"),
    optGalleryStickBottom: document.getElementById("optGalleryStickBottom"),
    optGalleryLogWrap: document.getElementById("optGalleryLogWrap"),
    optGalleryLogHighlight: document.getElementById("optGalleryLogHighlight"),
    btnGalleryClearLog: document.getElementById("btnGalleryClearLog"),
    btnGalleryLogFontMinus: document.getElementById("btnGalleryLogFontMinus"),
    btnGalleryLogFontPlus: document.getElementById("btnGalleryLogFontPlus"),
    gifskyGalleriesRoot: document.getElementById("gifskyGalleriesRoot"),
    btnGifskyScan: document.getElementById("btnGifskyScan"),
    btnGifskyStart: document.getElementById("btnGifskyStart"),
    btnGifskyFoldersSelectAll: document.getElementById("btnGifskyFoldersSelectAll"),
    btnGifskyFoldersSelectNone: document.getElementById("btnGifskyFoldersSelectNone"),
    btnGifskyCancel: document.getElementById("btnGifskyCancel"),
    optGifskyDeleteSource: document.getElementById("optGifskyDeleteSource"),
    optGifskyDryRun: document.getElementById("optGifskyDryRun"),
    gifskyScanSummary: document.getElementById("gifskyScanSummary"),
    gifskyMsg: document.getElementById("gifskyMsg"),
    gifskyFolderTbody: document.getElementById("gifskyFolderTbody"),
    gifskyFolderTableWrap: document.getElementById("gifskyFolderTableWrap"),
    gifskyFolderScroll: document.getElementById("gifskyFolderScroll"),
    gifskyLogBody: document.getElementById("gifskyLogBody"),
    gifskyLogFrame: document.getElementById("gifskyLogFrame"),
    btnGifskyClearLog: document.getElementById("btnGifskyClearLog"),
    linkGifskyToConf: document.getElementById("linkGifskyToConf"),
    navGettingStarted: document.getElementById("navGettingStarted"),
    gsPlatformHint: document.getElementById("gsPlatformHint"),
    setShowGettingStarted: document.getElementById("setShowGettingStarted"),
    setDefaultLandingView: document.getElementById("setDefaultLandingView"),
    btnGsVerifyAll: document.getElementById("btnGsVerifyAll"),
    gsVerifyAllHint: document.getElementById("gsVerifyAllHint"),
    btnGsOpenCookies: document.getElementById("btnGsOpenCookies"),
    btnGsOpenSiteCookies: document.getElementById("btnGsOpenSiteCookies"),
    btnGsOpenInputs: document.getElementById("btnGsOpenInputs"),
    btnGsOpenYtdlp: document.getElementById("btnGsOpenYtdlp"),
    btnGsOpenGallerydl: document.getElementById("btnGsOpenGallerydl"),
    btnGsOpenGifsky: document.getElementById("btnGsOpenGifsky"),
    btnGsOpenLibrary: document.getElementById("btnGsOpenLibrary"),
    btnGsOpenSettings: document.getElementById("btnGsOpenSettings"),
    homeFlameDatetime: document.getElementById("homeFlameDatetime"),
    homeFlameGreeting: document.getElementById("homeFlameGreeting"),
    homeWeatherIcon: document.getElementById("homeWeatherIcon"),
    homeWeatherLine1: document.getElementById("homeWeatherLine1"),
    homeWeatherLine2: document.getElementById("homeWeatherLine2"),
    optHomeClock24: document.getElementById("optHomeClock24"),
    homeFlameApps: document.getElementById("homeFlameApps"),
    homeApplicationsToggle: document.getElementById("homeApplicationsToggle"),
    btnHomeAddBookmark: document.getElementById("btnHomeAddBookmark"),
    homeBookmarkGrid: document.getElementById("homeBookmarkGrid"),
    homeBookmarkEmpty: document.getElementById("homeBookmarkEmpty"),
    homeBookmarkModal: document.getElementById("homeBookmarkModal"),
    homeBookmarkModalBackdrop: document.getElementById("homeBookmarkModalBackdrop"),
    inpHomeBookmarkUrl: document.getElementById("inpHomeBookmarkUrl"),
    homeBookmarkUrlMsg: document.getElementById("homeBookmarkUrlMsg"),
    btnHomeBookmarkCancel: document.getElementById("btnHomeBookmarkCancel"),
    btnHomeBookmarkSave: document.getElementById("btnHomeBookmarkSave"),
    homeBookmarkModalTitle: document.getElementById("homeBookmarkModalTitle"),
    setWeatherLat: document.getElementById("setWeatherLat"),
    setWeatherLon: document.getElementById("setWeatherLon"),
    setOpenweatherApiKey: document.getElementById("setOpenweatherApiKey"),
    optOpenweatherKeyClear: document.getElementById("optOpenweatherKeyClear"),
    btnSaveHomeWeather: document.getElementById("btnSaveHomeWeather"),
    homeWeatherSettingsMsg: document.getElementById("homeWeatherSettingsMsg"),
  };

  const STORAGE_LOG_HIGHLIGHT = "archive_console_log_highlight";
  /** Library file list density (same px range as log A+/A−). */
  const STORAGE_LIBRARY_FILE_LIST_FONT = "archive_console_library_file_list_font_px";
  const LS_GS_CHECKLIST = "archive_console.getting_started.checklist.v1";
  const HOME_LS_BOOKMARKS = "archive_console.home.bookmarks.v1";
  const HOME_LS_CLOCK24 = "archive_console.home.clock24.v1";
  const HOME_URL_DEBOUNCE_MS = 300;
  const HOME_DEFAULT_ICON =
    "data:image/svg+xml," +
    encodeURIComponent(
      '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="%238b939e"><path d="M3.9 12c0-1.71 1.39-3.1 3.1-3.1h4V7H7c-2.76 0-5 2.24-5 5s2.24 5 5 5h4v-1.9H7c-1.71 0-3.1-1.39-3.1-3.1zM8 13h8v-2H8v2zm9-6h-4v1.9h4c1.71 0 3.1 1.39 3.1 3.1s-1.39 3.1-3.1 3.1h-4V17h4c2.76 0 5-2.24 5-5s-2.24-5-5-5z"/></svg>'
    );
  const GS_VERIFY_DEBOUNCE_MS = 2000;
  const GS_INPUT_DEEP_FILES = {
    "playlists_input.txt": true,
    "channels_input.txt": true,
    "videos_input.txt": true,
    "yt-dlp.conf": true,
    "cookies.txt": true,
  };

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
  let galleryBatchQueue = [];
  let galleryBatchTotal = 0;
  let gallerySourcesEntries = [];
  let logFontPx = 13;
  let libraryFileListFontPx = 13;
  let oneoffCookieCheckTimer = null;
  let lastOneoffCookieReminderUnix = 0;
  /** Sidebar / URL view id (e.g. run, oneoff); used to suppress duplicate cookie UI. */
  let activeViewId = "run";
  /** Home view: bookmarks `{ id, url, createdAt }` (server-persisted; localStorage cache). */
  let homeBookmarks = [];
  let homeClockTimer = null;
  let homeBookmarkModalEditId = null;
  /** When true, Home Bookmarks section shows Add and per-row edit/delete. */
  let homeApplicationsEdit = false;
  let homeUrlDebounceTimer = null;
  var lastShowGettingStarted = true;
  var lastGsToolsVerifyAt = 0;
  let lastRemindersCookieShowEligible = false;
  let lastRemindersCookieMessage = "";
  let lastRemindersRequireCookieConfirmManual = false;
  let es = null;
  let filePath = "";
  let selectedRel = "";
  /** Abort in-flight MediaInfo fetch when selection changes. */
  let filesMediainfoController = null;
  /** Duplicate finder: last scan groups + download output roots cache. */
  var dupLastGroups = [];
  var dupScanBusy = false;
  var dupDownloadOutputRoots = [];
  var dupManualRoots = [];
  var DUP_OUTPUT_JOB_ORDER = [
    "watch_later",
    "channels",
    "videos",
    "oneoff",
    "galleries",
  ];
  var DUP_OUTPUT_JOB_LABELS = {
    watch_later: "Watch Later",
    channels: "Channels",
    videos: "Videos",
    oneoff: "Single download",
    galleries: "Galleries",
  };

  function dupOutputRootsFromSettings(j) {
    var eff = (j && j.download_dirs_effective) || {};
    var seen = {};
    var out = [];
    DUP_OUTPUT_JOB_ORDER.forEach(function (key) {
      var o = eff[key];
      if (!o || !o.effective_rel) {
        return;
      }
      var rel = String(o.effective_rel).trim();
      if (!rel || seen[rel]) {
        return;
      }
      seen[rel] = true;
      out.push({
        key: key,
        label: DUP_OUTPUT_JOB_LABELS[key] || key,
        rel: rel,
      });
    });
    return out;
  }
  /** Files list: Windows-style multi-select (Ctrl/Meta toggle, Shift range). */
  var filesListSelectedSet = new Set();
  var filesListAnchorIndex = -1;
  /** Rename view: queued relative paths (allowlisted). */
  var renameQueueRels = [];
  var RENAME_PREVIEW_MAX_FILES = 200;
  var renameFolderBatchAbort = false;
  var renameFolderBatchState = null;
  var renamePreviewId = null;
  var renameLastPreviewRows = [];
  var renameHistoryItems = [];
  /** Full current-directory rows from the last list API response. */
  var filesListAllRowModels = [];
  /** Visible rows after folder search filter (for range + folder enqueue). */
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
    libraryUpdateSendRenameButton();
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
    for (var i = 0; i < filesListAllRowModels.length; i++) {
      if (filesListAllRowModels[i].rel === rel) {
        var z = filesListAllRowModels[i].ent.size;
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
    globalErrors: [],
  };

  const COOKIES_FILE = "cookies.txt";
  const YTDLP_CONF = "yt-dlp.conf";
  const GALLERY_DL_CONF = "gallery-dl.conf";
  const SITE_COOKIES_REL_RE = /^cookies\/[a-z0-9][a-z0-9_-]{0,62}\.txt$/i;

  function isSiteCookiesRel(rel) {
    return SITE_COOKIES_REL_RE.test(rel || "");
  }

  function isSensitiveCookieRel(rel) {
    return rel === COOKIES_FILE || isSiteCookiesRel(rel);
  }

  function isInputsDeepLinkFile(f) {
    return !!GS_INPUT_DEEP_FILES[f] || isSiteCookiesRel(f);
  }
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
      for (var ei = 0; ei < filesListAllRowModels.length; ei++) {
        if (
          filesListAllRowModels[ei].rel === selectedRel &&
          filesListAllRowModels[ei].is_dir
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
  var libraryViewToastTimer = null;

  function libraryViewToast(msg, isError) {
    if (!msg) {
      return;
    }
    if (els.libraryViewToast) {
      els.libraryViewToast.textContent = msg;
      els.libraryViewToast.hidden = false;
      els.libraryViewToast.classList.toggle("is-error", msg && !!isError);
      window.clearTimeout(libraryViewToastTimer);
      libraryViewToastTimer = window.setTimeout(function () {
        if (els.libraryViewToast) {
          els.libraryViewToast.hidden = true;
        }
      }, isError ? 9000 : 5500);
    }
  }

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

  function fpMediaDisplayMode() {
    var cur = fpCurrentRel();
    if (cur && filesPlayerIsVideoAudioRel(cur)) {
      return "video";
    }
    if (cur && filesPlayerIsImageRel(cur)) {
      return "image";
    }
    return "idle";
  }

  function fpSyncMediaBandMode() {
    var mode = fpMediaDisplayMode();
    if (els.filesLibraryPlayerBand) {
      els.filesLibraryPlayerBand.hidden = mode === "idle";
    }
    if (els.filesLibraryExportBand) {
      els.filesLibraryExportBand.hidden = mode !== "video";
    }
    if (els.filesPlayer) {
      els.filesPlayer.classList.remove(
        "is-video-mode",
        "is-image-mode",
        "is-idle-mode"
      );
      els.filesPlayer.classList.add(
        mode === "video"
          ? "is-video-mode"
          : mode === "image"
            ? "is-image-mode"
            : "is-idle-mode"
      );
    }
    if (els.filesVideo) {
      if (mode === "video") {
        els.filesVideo.hidden = false;
        els.filesVideo.controls = true;
      } else if (mode === "image") {
        els.filesVideo.pause();
        els.filesVideo.controls = false;
        els.filesVideo.hidden = true;
      }
    }
  }

  function fpReadSlideshowTimedFromUi() {
    if (els.filesPlayerSlideshowTimed) {
      fpSlideshowTimed = !!els.filesPlayerSlideshowTimed.checked;
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
      fpReadSlideshowTimedFromUi();
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
    btn.setAttribute("aria-pressed", playing ? "true" : "false");
    btn.classList.toggle("is-playing", playing);
    if (filesPlayerIsImageRel(cur)) {
      fpReadSlideshowTimedFromUi();
    }
    if (filesPlayerIsImageRel(cur) && !fpSlideshowTimed) {
      if (playIc) {
        playIc.hidden = false;
      }
      if (pauseIc) {
        pauseIc.hidden = true;
      }
      btn.setAttribute("aria-pressed", "false");
      btn.classList.remove("is-playing");
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
  var fpVideoLayoutRaf = 0;

  function fpClampLayout(n, lo, hi) {
    return Math.max(lo, Math.min(hi, n));
  }

  /** Library R2: #filesVideoFrame size is CSS (16:9 stage in .files-library-player-band). Clear legacy inline styles; keep width for observers/logging. */
  function fpUpdateVideoFrameLayout() {
    var frame = els.filesVideoFrame;
    if (!frame) {
      return;
    }
    frame.style.height = "";
    frame.style.maxHeight = "";
    frame.style.aspectRatio = "";
    var rw = frame.getBoundingClientRect().width;
    if (rw > 0) {
      filesPlayerPaneWidthPx = rw;
    }
    if (isFilesPlayerDevLog()) {
      console.debug("[files-player] fpUpdateVideoFrameLayout", {
        frameWidthPx: rw,
        targetId: "filesVideoFrame",
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
    fpReadSlideshowTimedFromUi();
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

  /** Pause/resume timed slideshow for the current image track (not list selection). */
  function fpToggleTimedSlideshowPause() {
    var cur = fpCurrentRel();
    fpReadSlideshowTimedFromUi();
    if (!fpSlideshowTimed || !cur || !filesPlayerIsImageRel(cur)) {
      return false;
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
    return true;
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
    fpSyncMediaBandMode();
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
    if (andPlay) {
      fpSlideshowPaused = false;
    }
    if (filesPlayerIsVideoAudioRel(rel)) {
      fpLoadVideoSource(rel, !!andPlay);
      return;
    }
    if (filesPlayerIsImageRel(rel)) {
      if (els.filesVideo) {
        els.filesVideo.pause();
        els.filesVideo.removeAttribute("src");
        els.filesVideo.load();
        els.filesVideo.controls = false;
        els.filesVideo.hidden = true;
      }
      fpResetVideoFrameMeta();
      fpApplyImageToStage(rel);
      fpSyncMediaBandMode();
      fpSyncPlayPauseButton();
      fpSyncFsHudPauseLabel();
    }
  }

  function fpHandlePlayPauseAction() {
    var cur = fpCurrentRel();
    var v = els.filesVideo;

    if (cur && filesPlayerIsImageRel(cur)) {
      fpReadSlideshowTimedFromUi();
      if (fpSlideshowTimed) {
        fpToggleTimedSlideshowPause();
        return;
      }
      fpMsg("Enable Timed to auto-advance images, or use Next / Previous.");
      return;
    }

    if (
      cur &&
      filesPlayerIsVideoAudioRel(cur) &&
      v &&
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

    var target = fpResolvePlayTargetRel();
    if (!target) {
      fpMsg(
        "Select a queueable file in the list or add tracks to the queue."
      );
      return;
    }
    fpPlayTargetRelNow(target);
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
    fpSyncMediaBandMode();
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

  function fpAddPlayablesToQueue(playables) {
    if (!playables || !playables.length) {
      return 0;
    }
    var added = 0;
    playables.forEach(function (rel) {
      if (fpQueueAppendPlayable(rel, true)) {
        added++;
      }
    });
    return added;
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
        "Could not load media—check download folder access, format, codec, or network."
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
      els.filesPlayerPlay.addEventListener("click", fpHandlePlayPauseAction);
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
        var added = fpAddPlayablesToQueue(playables);
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
          fpSlideshowPaused = false;
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
        fpToggleTimedSlideshowPause();
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
      if (activeViewId !== "library") {
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
        fpHandlePlayPauseAction();
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
        return 36;
      }
      return n;
    }

    /* Library R1: first column = file list %; second region = .files-library-r1-right (metadata | dup). */
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

  /* Library R1/R2/R3 sizing is CSS (min-height, 16:9 stage); vertical band resize removed. */

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
      isSensitiveCookieRel(editorFile) && !els.optUnlockCookies.checked;
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
    const isCookies = isSensitiveCookieRel(editorFile);
    els.cookiesCallout.hidden = !isCookies;
    if (els.cookiesCalloutText && isCookies) {
      var cookieLabel =
        editorFile === COOKIES_FILE ? "cookies.txt" : editorFile;
      els.cookiesCalloutText.innerHTML =
        "<strong>" +
        esc(cookieLabel) +
        "</strong> is sensitive. Content is hidden until you unlock. Avoid leaving this open where screen captures or shared logs could leak tokens.";
    }
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
      isSensitiveCookieRel(editorFile) && els.optUnlockCookies.checked;
    var q = isSensitiveCookieRel(editorFile)
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
      isSensitiveCookieRel(editorFile) &&
      !els.optUnlockCookies.checked
    ) {
      els.editorMsg.textContent = "Enable unlock to save this cookie file.";
      return;
    }
    var body = {
      content: els.editorTextarea.value,
      strip_blank_lines: els.optStripBlanks.checked,
      conf_smoke: els.optConfSmoke.checked,
      unlock_cookies:
        isSensitiveCookieRel(editorFile) && els.optUnlockCookies.checked,
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

  function loadGallerydlFile() {
    if (typeof window.gallerydlSetupLoad === "function") {
      window.gallerydlSetupLoad();
      return;
    }
    var gWarn = document.getElementById("gallerydlMsg");
    if (gWarn) {
      gWarn.textContent =
        "gallery-dl.conf editor script did not load. Hard-refresh (Ctrl+F5) or check /static/gallerydl_setup.js.";
    }
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
    if (row.cookie_file) {
      hay += " " + row.cookie_file;
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

      if (tool.cookie_note) {
        var cnote = document.createElement("p");
        cnote.className = "muted small supportedsites-cookie-note";
        cnote.textContent = tool.cookie_note;
        card.appendChild(cnote);
      }

      if (tool.cookie_convention) {
        var gnote = document.createElement("p");
        gnote.className = "muted small supportedsites-cookie-note";
        gnote.textContent = tool.cookie_convention;
        card.appendChild(gnote);
      }

      if (
        tool.id === "gallery-dl" &&
        tool.site_cookies_on_disk &&
        tool.site_cookies_on_disk.length
      ) {
        var onDisk = document.createElement("p");
        onDisk.className = "muted small";
        onDisk.textContent =
          "On disk: " +
          tool.site_cookies_on_disk
            .map(function (x) {
              return x.rel;
            })
            .join(", ");
        card.appendChild(onDisk);
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
        var headers = ["Name / id", "Documentation", "Example"];
        if (tool.id === "gallery-dl") {
          headers.push("Site cookie (gallery-dl)");
        }
        headers.forEach(function (lab) {
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
          if (tool.id === "gallery-dl") {
            var td3 = document.createElement("td");
            if (row.cookie_file) {
              var cf = document.createElement("code");
              cf.textContent = row.cookie_file;
              td3.appendChild(cf);
              if (row.cookie_present) {
                td3.appendChild(document.createElement("br"));
                var editBtn = document.createElement("button");
                editBtn.type = "button";
                editBtn.className = "btn ghost small supportedsites-cookie-edit";
                editBtn.textContent = "on disk — edit";
                editBtn.addEventListener("click", function () {
                  goToSiteCookieFile(row.cookie_file);
                });
                td3.appendChild(editBtn);
              } else {
                td3.appendChild(document.createElement("br"));
                var hint = document.createElement("span");
                hint.className = "muted small";
                hint.textContent = "if needed";
                td3.appendChild(hint);
              }
            } else {
              td3.textContent = "—";
            }
            tr.appendChild(td3);
          }
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

  async function refreshSiteCookiesPanel() {
    if (!els.siteCookiesList) {
      return;
    }
    try {
      var r = await fetch("/api/cookies/site-files");
      if (!r.ok) {
        if (els.siteCookiesMsg) {
          els.siteCookiesMsg.textContent = "Could not load site cookies list.";
        }
        return;
      }
      var j = await r.json();
      var files = j.files || [];
      els.siteCookiesList.innerHTML = "";
      files.forEach(function (row) {
        var li = document.createElement("li");
        var btn = document.createElement("button");
        btn.type = "button";
        btn.className = "site-cookie-row";
        if (row.rel === editorFile) {
          btn.classList.add("is-selected");
        }
        var size =
          row.size != null ? formatFileSize(Number(row.size)) : "—";
        btn.textContent = row.rel + " (" + size + ")";
        btn.title = "Edit " + row.rel;
        btn.addEventListener("click", function () {
          goToSiteCookieFile(row.rel);
        });
        li.appendChild(btn);
        els.siteCookiesList.appendChild(li);
      });
      if (els.siteCookiesEmpty) {
        els.siteCookiesEmpty.hidden = files.length > 0;
      }
      if (els.siteCookiesMsg) {
        var parts = [];
        if (j.cookies_txt_present) {
          parts.push("cookies.txt present (yt-dlp)");
        } else {
          parts.push("no cookies.txt yet (yt-dlp / optional gallery fallback)");
        }
        if (files.length) {
          parts.push(
            files.length +
              " site file(s) auto-wired at Galleries run (see Supported sites)"
          );
        }
        if (!j.allowlist_has_cookies_dir) {
          parts.push(
            "cookies/ should be included automatically — refresh Settings if Library cannot browse this folder"
          );
        }
        els.siteCookiesMsg.textContent = parts.join(" · ");
      }
    } catch (_e) {
      if (els.siteCookiesMsg) {
        els.siteCookiesMsg.textContent = "Site cookies list unavailable.";
      }
    }
  }

  function goToSiteCookieFile(rel) {
    if (!rel || !isSiteCookiesRel(rel)) {
      return;
    }
    activateView("inputs");
    replaceStateView("inputs", rel);
    loadDownloadDirsForm();
    editorTrySwitchTab(rel);
    void refreshSiteCookiesPanel();
  }

  async function addSiteCookieFile() {
    if (!els.siteCookieNewName) {
      return;
    }
    var name = (els.siteCookieNewName.value || "").trim();
    if (!name) {
      if (els.siteCookiesMsg) {
        els.siteCookiesMsg.textContent = "Enter a site name (e.g. instagram).";
      }
      return;
    }
    var r = await fetch("/api/cookies/site-files", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: name }),
    });
    var j = {};
    try {
      j = await r.json();
    } catch (_e) {
      void _e;
    }
    if (!r.ok) {
      if (els.siteCookiesMsg) {
        els.siteCookiesMsg.textContent =
          (j && j.detail) || "Could not create site cookie file.";
      }
      return;
    }
    els.siteCookieNewName.value = "";
    await refreshSiteCookiesPanel();
    if (j.rel) {
      goToSiteCookieFile(j.rel);
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
      var on = f === editorFile && !isSiteCookiesRel(editorFile);
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
    if (phase !== "running") {
      stopRunStatusPoll();
    }
  }

  var runStatusPollTimer = null;

  function stopRunStatusPoll() {
    if (runStatusPollTimer) {
      clearInterval(runStatusPollTimer);
      runStatusPollTimer = null;
    }
  }

  function startRunStatusPoll() {
    if (runStatusPollTimer) {
      return;
    }
    runStatusPollTimer = setInterval(function () {
      fetch("/api/run/status")
        .then(function (r) {
          return r.json();
        })
        .then(function (j) {
          if (j && j.phase && j.phase !== "running") {
            applyRunStatusFromServer(j);
          }
        })
        .catch(function () {});
    }, 5000);
  }

  function applyRunStatusFromServer(j) {
    if (j && j.phase) {
      setPhase(j.phase);
    }
    renderRunPanel(j);
    var running = j && j.phase === "running";
    if (running && j.run && j.run.job) {
      activeStreamJob = j.run.job;
      disableRunButtons(true);
      editorJobRunning = true;
      setEditorRunning(true);
      startRunStatusPoll();
    } else {
      activeStreamJob = null;
      disableRunButtons(false);
      editorJobRunning = false;
      setEditorRunning(false);
      stopRunStatusPoll();
    }
  }

  async function postRunStop() {
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
      appendStreamLine(
        "[console] Stop failed (" + r.status + ") — trying force-reset…"
      );
      await fetch("/api/run/force-reset", { method: "POST" });
    }
    try {
      var st = await fetch("/api/run/status");
      if (st.ok) {
        applyRunStatusFromServer(await st.json());
      }
    } catch (_e) {
      void _e;
    }
    appendStreamLine(
      "[console] Stop finished — Run galleries is enabled again if no job is running."
    );
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
      oneoff: "Single download",
      galleries: "Gallery batch",
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

  function homeValidateUrl(raw) {
    var s = (raw || "").trim();
    if (!s) {
      return null;
    }
    try {
      var u = new URL(s);
      if (u.protocol !== "http:" && u.protocol !== "https:") {
        return null;
      }
      if (!u.hostname) {
        return null;
      }
      u.hash = "";
      return u.href;
    } catch (_e) {
      return null;
    }
  }

  function homeNormalizeBookmarks(arr) {
    var out = [];
    if (!Array.isArray(arr)) {
      return out;
    }
    arr.forEach(function (row) {
      var vu =
        row && typeof row.url === "string" ? homeValidateUrl(row.url) : null;
      if (row && typeof row.id === "string" && vu) {
        out.push({
          id: row.id,
          url: vu,
          createdAt:
            typeof row.createdAt === "number" ? row.createdAt : Date.now(),
        });
      }
    });
    return out;
  }

  function homeReadBookmarksFromLs() {
    try {
      return homeNormalizeBookmarks(JSON.parse(localStorage.getItem(HOME_LS_BOOKMARKS)));
    } catch (_err) {
      void _err;
      return [];
    }
  }

  /** Load bookmarks from the server (port-independent); migrate legacy localStorage once. */
  async function homeLoadBookmarks() {
    homeBookmarks = [];
    try {
      var resp = await fetch("/api/bookmarks", {
        headers: { Accept: "application/json" },
      });
      if (resp.ok) {
        var data = await resp.json();
        homeBookmarks = homeNormalizeBookmarks(data && data.bookmarks);
        if (homeBookmarks.length === 0) {
          var legacy = homeReadBookmarksFromLs();
          if (legacy.length > 0) {
            homeBookmarks = legacy;
            await homeSaveBookmarks();
          }
        }
        return;
      }
    } catch (_e) {
      void _e;
    }
    homeBookmarks = homeReadBookmarksFromLs();
  }

  /** Persist to the server (source of truth); keep a localStorage cache for offline use. */
  async function homeSaveBookmarks() {
    try {
      localStorage.setItem(HOME_LS_BOOKMARKS, JSON.stringify(homeBookmarks));
    } catch (_e) {
      void _e;
    }
    try {
      await fetch("/api/bookmarks", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ bookmarks: homeBookmarks }),
      });
    } catch (_e2) {
      void _e2;
    }
  }

  function homeApplyClock24FromLs() {
    if (!els.optHomeClock24) {
      return;
    }
    try {
      var v = localStorage.getItem(HOME_LS_CLOCK24);
      els.optHomeClock24.checked = v === "1";
    } catch (_x) {
      void _x;
    }
  }

  function homeWeatherIconSvg(condition, hour) {
    var c = (condition || "").toLowerCase();
    if (
      c.indexOf("cloud") >= 0 ||
      c.indexOf("overcast") >= 0 ||
      c.indexOf("fog") >= 0 ||
      c.indexOf("rain") >= 0 ||
      c.indexOf("snow") >= 0 ||
      c.indexOf("drizzle") >= 0 ||
      c.indexOf("storm") >= 0
    ) {
      return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">' +
        '<path d="M6.5 19a4.5 4.5 0 01-.37-8.98 6.002 6.002 0 0111.16-3.48A4.502 4.502 0 0117.5 19h-11z"/>' +
        "</svg>"
      );
    }
    if (hour < 6 || hour >= 20) {
      return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">' +
        '<path d="M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79z"/>' +
        "</svg>"
      );
    }
    return (
      '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">' +
      '<circle cx="12" cy="12" r="5"/>' +
      "</svg>"
    );
  }

  function tickHomeClock() {
    if (activeViewId !== "home" || !els.homeFlameDatetime) {
      return;
    }
    var now = new Date();
    var use24 = !!(els.optHomeClock24 && els.optHomeClock24.checked);
    var datePart = "";
    try {
      datePart = new Intl.DateTimeFormat("en-US", {
        weekday: "long",
        month: "long",
        day: "numeric",
        year: "numeric",
      }).format(now);
    } catch (_e) {
      datePart = now.toLocaleDateString();
    }
    var timePart = "";
    try {
      timePart = new Intl.DateTimeFormat("en-US", {
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
        hour12: !use24,
      }).format(now);
    } catch (_e2) {
      timePart = now.toLocaleTimeString();
    }
    els.homeFlameDatetime.textContent = (datePart + " — " + timePart).toUpperCase();

    var h = now.getHours();
    var greet = "Good evening!";
    if (h < 5 || h >= 22) {
      greet = "Good night!";
    } else if (h < 12) {
      greet = "Good morning!";
    } else if (h < 17) {
      greet = "Good afternoon!";
    }
    if (els.homeFlameGreeting) {
      els.homeFlameGreeting.textContent = greet;
    }
  }

  function homeSetApplicationsEdit(on) {
    homeApplicationsEdit = !!on;
    var wrap = els.homeFlameApps;
    if (wrap) {
      wrap.classList.toggle("is-edit", homeApplicationsEdit);
    }
    if (els.homeApplicationsToggle) {
      els.homeApplicationsToggle.setAttribute(
        "aria-expanded",
        homeApplicationsEdit ? "true" : "false"
      );
    }
    if (els.btnHomeAddBookmark) {
      els.btnHomeAddBookmark.hidden = !homeApplicationsEdit;
    }
  }

  async function homeFetchLabels(urls) {
    try {
      var r = await fetch("/api/bookmarks/labels", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ urls: urls }),
      });
      if (!r.ok) {
        return null;
      }
      return await r.json();
    } catch (_e) {
      return null;
    }
  }

  function homeFallbackLabels(urls) {
    return urls.map(function (u) {
      try {
        var x = new URL(u);
        return x.hostname.replace(/^\[|\]$/g, "") || u;
      } catch (_e) {
        return u;
      }
    });
  }

  async function homeRenderBookmarks() {
    if (!els.homeBookmarkGrid) {
      return;
    }
    els.homeBookmarkGrid.textContent = "";
    var urls = homeBookmarks.map(function (b) {
      return b.url;
    });
    var labels = homeFallbackLabels(urls);
    var titles = urls.slice();
    var payload = await homeFetchLabels(urls);
    if (
      payload &&
      Array.isArray(payload.labels) &&
      payload.labels.length === urls.length
    ) {
      labels = payload.labels;
      titles = Array.isArray(payload.titles) ? payload.titles : titles;
    }
    if (els.homeBookmarkEmpty) {
      els.homeBookmarkEmpty.hidden = urls.length > 0;
    }
    homeBookmarks.forEach(function (b, i) {
      var card = document.createElement("article");
      card.className = "home-bookmark-row";
      var labelText = labels[i] || b.url;
      var titleText = titles[i] || b.url;
      var titleUpper = String(labelText || "").toUpperCase();
      var rawTitle = String(titles[i] || "").trim();
      var descUpper = "";
      if (rawTitle && rawTitle !== labelText) {
        var shortT =
          rawTitle.length > 52 ? rawTitle.slice(0, 49).trim() + "…" : rawTitle;
        descUpper = shortT.toUpperCase();
      } else {
        try {
          var uh = new URL(b.url);
          descUpper = (
            uh.hostname.replace(/^www\./i, "") || titleUpper
          ).toUpperCase();
        } catch (_eu) {
          descUpper = titleUpper;
        }
      }
      var main = document.createElement("div");
      main.className = "home-bookmark-row__main";
      var link = document.createElement("a");
      link.className = "home-bookmark-row__link";
      link.href = b.url;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      link.title = titleText;
      var img = document.createElement("img");
      img.className = "home-bookmark-row__icon";
      img.alt = "";
      img.loading = "lazy";
      img.src = "/api/bookmark-icon?url=" + encodeURIComponent(b.url);
      img.onerror = function () {
        img.onerror = null;
        img.src = HOME_DEFAULT_ICON;
      };
      var meta = document.createElement("div");
      meta.className = "home-bookmark-row__meta";
      var spanTitle = document.createElement("span");
      spanTitle.className = "home-bookmark-row__title";
      spanTitle.textContent = titleUpper;
      var spanDesc = document.createElement("span");
      spanDesc.className = "home-bookmark-row__desc";
      spanDesc.textContent = descUpper;
      meta.appendChild(spanTitle);
      meta.appendChild(spanDesc);
      link.appendChild(img);
      link.appendChild(meta);
      var actions = document.createElement("div");
      actions.className = "home-bookmark-row__actions";
      var btnEdit = document.createElement("button");
      btnEdit.type = "button";
      btnEdit.className = "btn ghost small";
      btnEdit.textContent = "Edit";
      btnEdit.setAttribute("aria-label", "Edit bookmark");
      btnEdit.addEventListener("click", function (ev) {
        ev.preventDefault();
        ev.stopPropagation();
        openHomeBookmarkModal(b.id);
      });
      var btnDel = document.createElement("button");
      btnDel.type = "button";
      btnDel.className = "btn ghost small";
      btnDel.textContent = "Delete";
      btnDel.setAttribute("aria-label", "Delete bookmark");
      btnDel.addEventListener("click", function (ev) {
        ev.preventDefault();
        ev.stopPropagation();
        homeBookmarks = homeBookmarks.filter(function (x) {
          return x.id !== b.id;
        });
        void homeSaveBookmarks();
        void homeRenderBookmarks();
      });
      actions.appendChild(btnEdit);
      actions.appendChild(btnDel);
      main.appendChild(link);
      card.appendChild(main);
      card.appendChild(actions);
      els.homeBookmarkGrid.appendChild(card);
    });
  }

  async function refreshHomeWeather() {
    if (!els.homeWeatherLine1) {
      return;
    }
    els.homeWeatherLine1.classList.remove("is-weather-primary");
    els.homeWeatherLine1.textContent = "LOADING…";
    if (els.homeWeatherLine2) {
      els.homeWeatherLine2.textContent = "";
    }
    if (els.homeWeatherIcon) {
      els.homeWeatherIcon.innerHTML = "";
    }
    try {
      var r = await fetch("/api/weather");
      var j = await r.json();
      var nowH = new Date().getHours();
      if (!j || j.ok === false) {
        var msg =
          (j && j.message) ||
          (j && j.error === "not_configured"
            ? "SET COORDINATES IN SETTINGS"
            : "WEATHER UNAVAILABLE");
        els.homeWeatherLine1.textContent = String(msg).toUpperCase();
        if (els.homeWeatherLine2) {
          els.homeWeatherLine2.textContent = "";
        }
        if (els.homeWeatherIcon) {
          els.homeWeatherIcon.innerHTML = homeWeatherIconSvg("", nowH);
        }
        return;
      }
      if (j.temp_c != null) {
        var tempF = Math.round(Number(j.temp_c) * (9 / 5) + 32);
        els.homeWeatherLine1.textContent = tempF + "°F";
        els.homeWeatherLine1.classList.add("is-weather-primary");
      } else {
        els.homeWeatherLine1.textContent = "—";
      }
      if (els.homeWeatherLine2) {
        if (j.humidity_pct != null) {
          els.homeWeatherLine2.textContent = String(j.humidity_pct) + "%";
        } else {
          els.homeWeatherLine2.textContent = "";
        }
      }
      if (els.homeWeatherIcon) {
        els.homeWeatherIcon.innerHTML = homeWeatherIconSvg(
          j.condition || "",
          nowH
        );
      }
    } catch (_e) {
      els.homeWeatherLine1.classList.remove("is-weather-primary");
      els.homeWeatherLine1.textContent = "WEATHER UNREACHABLE";
      if (els.homeWeatherLine2) {
        els.homeWeatherLine2.textContent = "";
      }
      if (els.homeWeatherIcon) {
        els.homeWeatherIcon.innerHTML = homeWeatherIconSvg(
          "",
          new Date().getHours()
        );
      }
    }
  }

  function homeCloseBookmarkModal() {
    var m = els.homeBookmarkModal;
    if (!m) {
      return;
    }
    m.hidden = true;
    m.setAttribute("aria-hidden", "true");
    homeBookmarkModalEditId = null;
    if (els.inpHomeBookmarkUrl) {
      els.inpHomeBookmarkUrl.value = "";
    }
    if (els.homeBookmarkUrlMsg) {
      els.homeBookmarkUrlMsg.textContent = "";
    }
    if (els.btnHomeBookmarkSave) {
      els.btnHomeBookmarkSave.disabled = true;
    }
    document.removeEventListener("keydown", homeOnModalKeydown, true);
  }

  function homeOnModalKeydown(ev) {
    if (ev.key === "Escape") {
      homeCloseBookmarkModal();
      ev.preventDefault();
    }
  }

  function openHomeBookmarkModal(editId) {
    var m = els.homeBookmarkModal;
    if (!m || !els.inpHomeBookmarkUrl) {
      return;
    }
    homeBookmarkModalEditId = editId || null;
    if (els.homeBookmarkModalTitle) {
      els.homeBookmarkModalTitle.textContent = editId
        ? "Edit bookmark"
        : "Add bookmark";
    }
    var preset = "";
    if (editId) {
      var found = homeBookmarks.filter(function (x) {
        return x.id === editId;
      });
      preset = found[0] ? found[0].url : "";
    }
    els.inpHomeBookmarkUrl.value = preset;
    if (els.homeBookmarkUrlMsg) {
      els.homeBookmarkUrlMsg.textContent = "";
    }
    m.hidden = false;
    m.setAttribute("aria-hidden", "false");
    document.addEventListener("keydown", homeOnModalKeydown, true);
    window.setTimeout(function () {
      els.inpHomeBookmarkUrl.focus();
      els.inpHomeBookmarkUrl.select();
    }, 0);
    homeSyncBookmarkSaveEnabled();
  }

  function homeSyncBookmarkSaveEnabled() {
    if (!els.btnHomeBookmarkSave || !els.inpHomeBookmarkUrl) {
      return;
    }
    els.btnHomeBookmarkSave.disabled = !homeValidateUrl(
      els.inpHomeBookmarkUrl.value.trim()
    );
  }

  function homeCommitBookmarkFromModal() {
    var u = homeValidateUrl(
      (els.inpHomeBookmarkUrl && els.inpHomeBookmarkUrl.value) || ""
    );
    if (!u) {
      return;
    }
    if (homeBookmarkModalEditId) {
      homeBookmarks = homeBookmarks.map(function (x) {
        return x.id === homeBookmarkModalEditId
          ? { id: x.id, url: u, createdAt: x.createdAt }
          : x;
      });
    } else {
      var nid =
        window.crypto && typeof window.crypto.randomUUID === "function"
          ? window.crypto.randomUUID()
          : String(Date.now()) + "-" + Math.random().toString(36).slice(2, 8);
      homeBookmarks.push({ id: nid, url: u, createdAt: Date.now() });
    }
    void homeSaveBookmarks();
    homeCloseBookmarkModal();
    void homeRenderBookmarks();
  }

  function initHomeView() {
    homeSetApplicationsEdit(false);
    homeApplyClock24FromLs();
    void refreshHomeWeather();
    tickHomeClock();
    void homeLoadBookmarks().then(function () {
      void homeRenderBookmarks();
    });
  }

  function markGettingStartedSeenOnServer() {
    void fetch("/api/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ getting_started_seen: true }),
    });
  }

  function activateView(viewId) {
    if (homeClockTimer != null) {
      window.clearInterval(homeClockTimer);
      homeClockTimer = null;
    }
    var prevViewId = activeViewId;
    if (prevViewId === "getting-started" && viewId !== "getting-started") {
      markGettingStartedSeenOnServer();
    }
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
        requestAnimationFrame(function () {
          fpScheduleVideoFrameLayout();
        });
      });
      syncDupRootCheckboxesFromApi();
    }
    if (viewId === "home") {
      homeClockTimer = window.setInterval(tickHomeClock, 1000);
      tickHomeClock();
    }
    if (viewId === "czkawka" && typeof window.czkawkaOnViewEnter === "function") {
      window.czkawkaOnViewEnter();
    }
    if (typeof window.czkawkaSyncScanState === "function") {
      void window.czkawkaSyncScanState();
    }
    if (viewId === "run") {
      void loadYoutubeScheduleForm();
    }
    if (viewId === "rename") {
      void refreshRenameDeepLUsage();
    }
  }

  var DEFAULT_LANDING_VIEW_IDS = {
    "getting-started": true,
    home: true,
    run: true,
    oneoff: true,
    galleries: true,
    history: true,
    library: true,
    czkawka: true,
    rename: true,
    inputs: true,
    ytdlp: true,
    gallerydl: true,
    gifsky: true,
    gifskyconf: true,
    supportedsites: true,
    settings: true,
  };

  function normalizeDefaultLandingView(v) {
    var s = String(v || "").trim();
    return DEFAULT_LANDING_VIEW_IDS[s] ? s : "run";
  }

  function mapViewQueryToViewId(raw) {
    var v = (raw || "").trim();
    if (v === "history" || v === "logs" || v === "reports") {
      return "history";
    }
    if (v === "files") {
      return "library";
    }
    if (
      v === "library" ||
      v === "czkawka" ||
      v === "rename" ||
      v === "inputs" ||
      v === "settings" ||
      v === "ytdlp" ||
      v === "gallerydl" ||
      v === "gifsky" ||
      v === "gifskyconf" ||
      v === "supportedsites" ||
      v === "run" ||
      v === "oneoff" ||
      v === "galleries" ||
      v === "getting-started" ||
      v === "home"
    ) {
      return v;
    }
    return "run";
  }

  /** @returns {string | null} view id if ?view= is present, else null */
  function getExplicitViewFromUrl() {
    var q = new URLSearchParams(window.location.search);
    if (!q.has("view")) {
      return null;
    }
    return mapViewQueryToViewId(q.get("view"));
  }

  function resolveInitialViewFromSettings(settingsPayload) {
    var explicit = getExplicitViewFromUrl();
    if (explicit !== null) {
      return explicit;
    }
    if (settingsPayload && settingsPayload.getting_started_seen === false) {
      return "getting-started";
    }
    return normalizeDefaultLandingView(
      settingsPayload && settingsPayload.default_landing_view
    );
  }

  function runInitialViewBootstrap(viewId) {
    if (viewId === "inputs") {
      var gsInputsFile = getInitialInputsFileFromUrl(viewId);
      if (gsInputsFile) {
        editorFile = gsInputsFile;
        els.editorTabs.forEach(function (t) {
          var f = t.getAttribute("data-file");
          var on = f === editorFile && !isSiteCookiesRel(editorFile);
          t.classList.toggle("is-active", on);
          t.setAttribute("aria-selected", on ? "true" : "false");
        });
      }
      loadDownloadDirsForm();
      void refreshSiteCookiesPanel();
      loadEditorFile(editorFile);
    }
    if (viewId === "inputs") {
      loadDownloadDirsForm();
      void refreshSiteCookiesPanel();
    }
    if (viewId === "run") {
      void loadYoutubeScheduleForm();
    }
    if (viewId === "settings") {
      loadSettingsForm();
    }
    if (viewId === "oneoff") {
      loadDownloadDirsForm();
      loadOneoffRolling();
      refreshOneoffOutputEffective();
      void refreshReminders().then(function () {
        scheduleOneoffCookieChecks();
      });
    } else if (viewId === "galleries") {
      loadDownloadDirsForm();
      refreshGalleryOutputEffective();
      void loadGallerySources();
      void refreshReminders();
    } else if (viewId === "gifsky") {
      loadDownloadDirsForm();
      void loadGifskyScan();
      void refreshReminders();
    } else {
      void refreshReminders();
    }
    if (viewId === "library") {
      void openFilesViewWithOptionalWatch();
    }
    if (viewId === "rename") {
      renderRenameQueue();
    }
    if (viewId === "gallerydl") {
      loadGallerydlFile();
    }
    if (viewId === "gifskyconf" && window.gifskyconfSetupLoad) {
      window.gifskyconfSetupLoad();
    }
    if (viewId === "supportedsites") {
      void loadSupportedsites(false);
    }
    if (viewId === "getting-started") {
      initGettingStartedView();
    }
    if (viewId === "home") {
      initHomeView();
    }
  }

  function getInitialInputsFileFromUrl(viewId) {
    if (viewId !== "inputs") {
      return null;
    }
    var q = new URLSearchParams(window.location.search);
    var f = (q.get("file") || "").trim();
    if (!f || !isInputsDeepLinkFile(f)) {
      return null;
    }
    return f;
  }

  function replaceStateView(viewId, fileOpt) {
    try {
      var u = new URL(window.location.href);
      u.searchParams.set("view", viewId);
      if (fileOpt) {
        u.searchParams.set("file", fileOpt);
      } else {
        u.searchParams.delete("file");
      }
      history.replaceState(null, "", u.pathname + u.search + u.hash);
    } catch (_e) {
      void _e;
    }
  }

  function syncGettingStartedSidebar(show) {
    if (!els.navGettingStarted) {
      return;
    }
    var on = show !== false;
    els.navGettingStarted.hidden = !on;
    els.navGettingStarted.setAttribute("aria-hidden", on ? "false" : "true");
  }

  function applyShowGettingStartedFromSettingsPayload(j) {
    lastShowGettingStarted = j.show_getting_started !== false;
    syncGettingStartedSidebar(lastShowGettingStarted);
  }

  function goToInputsFile(nextFile) {
    if (!nextFile || !isInputsDeepLinkFile(nextFile)) {
      return;
    }
    activateView("inputs");
    replaceStateView("inputs", nextFile);
    loadDownloadDirsForm();
    editorTrySwitchTab(nextFile);
  }

  function initGettingStartedView() {
    if (els.gsPlatformHint) {
      var ua = typeof navigator !== "undefined" ? navigator.userAgent || "" : "";
      if (/windows/i.test(ua)) {
        els.gsPlatformHint.hidden = false;
        els.gsPlatformHint.textContent =
          "Windows: prefer the console venv under archive_console/.venv (Scripts) for drivers; add tools to PATH or set explicit paths in Settings.";
      } else {
        els.gsPlatformHint.hidden = true;
        els.gsPlatformHint.textContent = "";
      }
    }
    try {
      var raw = window.localStorage.getItem(LS_GS_CHECKLIST) || "{}";
      var data = JSON.parse(raw);
      if (data.gifski) {
        data.gifsky = true;
        delete data.gifski;
      }
      document.querySelectorAll("[data-gs-check]").forEach(function (inp) {
        if (!(inp instanceof HTMLInputElement) || inp.type !== "checkbox") {
          return;
        }
        var id = inp.getAttribute("data-gs-check") || "";
        if (data[id]) {
          inp.checked = true;
        }
      });
    } catch (_e) {
      void _e;
    }
  }

  function persistGettingStartedChecklist() {
    var data = {};
    document.querySelectorAll("[data-gs-check]").forEach(function (inp) {
      if (!(inp instanceof HTMLInputElement) || inp.type !== "checkbox") {
        return;
      }
      var id = inp.getAttribute("data-gs-check") || "";
      if (id && inp.checked) {
        data[id] = true;
      }
    });
    try {
      window.localStorage.setItem(LS_GS_CHECKLIST, JSON.stringify(data));
    } catch (_e) {
      void _e;
    }
  }

  function applyToolRowStatus(toolId, row) {
    var sel = '[data-gs-tool-status="' + toolId + '"]';
    var el = document.querySelector(sel);
    if (!el) {
      return;
    }
    if (row.ok && row.version) {
      el.textContent = "OK — " + row.version;
    } else if (row.error === "not found") {
      el.textContent = "Missing (not on PATH or not configured).";
    } else {
      el.textContent =
        "Problem: " + (row.error || "unknown") + (row.version ? " — " + row.version : "");
    }
  }

  /**
   * @param {boolean} busy
   * @param {HTMLElement | null | undefined} activeButton — per-tool button when verifying one tool; null/undefined = "Verify all" (all tool rows busy)
   */
  function setGsVerifyBusy(busy, activeButton) {
    var allMode = busy && (activeButton == null);
    document.querySelectorAll("[data-gs-verify-tool]").forEach(function (btn) {
      if (!busy) {
        btn.disabled = false;
        btn.setAttribute("aria-busy", "false");
      } else if (allMode) {
        btn.disabled = true;
        btn.setAttribute("aria-busy", "true");
      } else {
        var isThis = btn === activeButton;
        btn.disabled = isThis;
        btn.setAttribute("aria-busy", isThis ? "true" : "false");
      }
    });
    if (els.btnGsVerifyAll) {
      if (!busy) {
        els.btnGsVerifyAll.disabled = false;
        els.btnGsVerifyAll.setAttribute("aria-busy", "false");
      } else if (allMode) {
        els.btnGsVerifyAll.disabled = true;
        els.btnGsVerifyAll.setAttribute("aria-busy", "true");
      } else {
        els.btnGsVerifyAll.disabled = true;
        els.btnGsVerifyAll.setAttribute("aria-busy", "false");
      }
    }
  }

  async function fetchAndApplyToolVersions(singleTool, clickedButton) {
    var now = Date.now();
    if (now - lastGsToolsVerifyAt < GS_VERIFY_DEBOUNCE_MS) {
      if (els.gsVerifyAllHint) {
        els.gsVerifyAllHint.textContent = "Wait a moment before verifying again.";
      }
      return;
    }
    lastGsToolsVerifyAt = now;
    if (els.gsVerifyAllHint) {
      els.gsVerifyAllHint.textContent = "";
    }
    setGsVerifyBusy(
      true,
      singleTool == null ? null : clickedButton instanceof HTMLElement ? clickedButton : null
    );
    try {
      var r = await fetch("/api/tools/versions", { credentials: "same-origin" });
      if (!r.ok) {
        if (els.gsVerifyAllHint) {
          els.gsVerifyAllHint.textContent = "Verify failed (" + r.status + ").";
        }
        return;
      }
      var j = await r.json();
      var rows = (j && j.tools) || [];
      rows.forEach(function (row) {
        if (!row || !row.tool) {
          return;
        }
        if (singleTool && row.tool !== singleTool) {
          return;
        }
        applyToolRowStatus(row.tool, row);
      });
    } finally {
      setGsVerifyBusy(false, null);
    }
  }

  function scrollHistorySectionFromUrl() {
    if (activeViewId !== "history") {
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
      applyRunStatusFromServer(j);
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

  function applyLibraryFileListFont() {
    if (!els.fileList) {
      return;
    }
    els.fileList.style.setProperty(
      "--library-file-list-font",
      libraryFileListFontPx + "px"
    );
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
        startRunStatusPoll();
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
        stopRunStatusPoll();
        refreshRunPanel();
        loadRunOverview();
        if (endedOneoff) {
          loadOneoffRolling();
        }
        if (endedGalleries) {
          loadRunOverview();
          if (galleryBatchQueue.length) {
            continueGalleryBatchIfAny();
          } else {
            if (galleryBatchTotal > 0 && els.gallerySourcesMsg) {
              els.gallerySourcesMsg.textContent = "Batch finished.";
            }
            galleryBatchTotal = 0;
            void loadGallerySources();
          }
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
    if (els.btnGalleryRunSelected) {
      els.btnGalleryRunSelected.disabled = disabled;
    }
  }


  function renderGlobalConsoleErrors() {
    var wrap = document.getElementById("globalConsoleErrorsWrap");
    var body = document.getElementById("globalConsoleErrorsBody");
    if (!wrap || !body) {
      return;
    }
    var errs = historyRenderState.globalErrors || [];
    if (!errs.length) {
      wrap.hidden = true;
      body.innerHTML = "";
      return;
    }
    wrap.hidden = false;
    var table = document.createElement("table");
    table.className = "table";
    table.innerHTML =
      "<thead><tr><th>Time (UTC)</th><th>Stage</th><th>Severity</th><th>Operation</th><th>Message</th></tr></thead>";
    var tbody = document.createElement("tbody");
    errs.slice(0, 80).forEach(function (er) {
      var tr = document.createElement("tr");
      function td(t, cls) {
        var x = document.createElement("td");
        if (cls) {
          x.className = cls;
        }
        x.textContent = t != null ? String(t) : "";
        return x;
      }
      tr.appendChild(td(er.ts_utc || "—"));
      tr.appendChild(td(er.stage || "—"));
      var sev = (er.severity || "error").toLowerCase();
      tr.appendChild(
        td(sev, sev === "warning" ? "exit-stopped" : "exit-fail"),
      );
      tr.appendChild(td(er.operation || "—"));
      tr.appendChild(td(er.message || "—"));
      tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    body.innerHTML = "";
    body.appendChild(table);
  }

  function renderHistoryRows() {
    var tb = els.historyTable;
    tb.innerHTML = "";
    if (historyRenderState.historyLoadFailed) {
      var trErr = document.createElement("tr");
      trErr.innerHTML =
        '<td colspan="9" class="muted">Could not load run history (request failed). Refresh the page.</td>';
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
        '<td colspan="9" class="muted">No recorded runs yet. Start a job from <strong>Run</strong>; finished jobs appear here with exit code, item stats, and folder.</td>';
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
      var errList = Array.isArray(row.errors) ? row.errors : [];
      var nErr = errList.length;
      var errCell =
        nErr === 0
          ? "—"
          : folder && !clipOut
            ? '<a class="link" target="_blank" rel="noopener" href="' +
              esc(reportsViewHref(folder + "/report.html")) +
              '#archive-console-errors">' +
              esc(String(nErr)) +
              "</a>"
            : esc(String(nErr));
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
        '</td><td class="hist-stat hist-stat-wide">' +
        errCell +
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

  function formatRenameDeepLUsage(j) {
    if (!j) {
      return "";
    }
    if (!j.configured) {
      return j.message || "DeepL API key not configured (Settings → DeepL).";
    }
    if (j.error_code && j.message) {
      return j.message;
    }
    var parts = [];
    if (j.character_limit > 0) {
      var rem =
        j.character_remaining != null
          ? j.character_remaining
          : Math.max(0, j.character_limit - j.character_count);
      parts.push(
        "DeepL: " +
          Number(j.character_count).toLocaleString() +
          " / " +
          Number(j.character_limit).toLocaleString() +
          " characters this period (" +
          Number(rem).toLocaleString() +
          " remaining)."
      );
    } else if (j.character_count != null) {
      parts.push(
        "DeepL: " + Number(j.character_count).toLocaleString() + " characters used this period."
      );
    }
    var q = renameQueueRels.length;
    if (q > 0) {
      parts.push(
        "Queue: " +
          q +
          " file(s); preview processes up to " +
          RENAME_PREVIEW_MAX_FILES +
          " per batch."
      );
      if (j.estimated_api_batches > 0) {
        parts.push(
          "~" +
            j.estimated_api_batches +
            " DeepL API call(s) if every stem needs translation."
        );
      }
    }
    if (j.limits_note) {
      parts.push(j.limits_note);
    }
    return parts.join(" ");
  }

  function formatRenamePreviewUsage(u) {
    if (!u || !Object.keys(u).length) {
      return "";
    }
    var parts = [];
    if (u.character_count != null) {
      parts.push(
        "This preview billed ~" + Number(u.character_count).toLocaleString() + " characters."
      );
    }
    if (u.character_count_before != null && u.character_limit > 0) {
      var after =
        Number(u.character_count_before) + Number(u.character_count || 0);
      parts.push(
        "Period total after preview: ~" +
          after.toLocaleString() +
          " / " +
          Number(u.character_limit).toLocaleString() +
          "."
      );
    }
    if (u.batches > 1) {
      parts.push("Sent in " + u.batches + " batched API requests.");
    }
    return parts.join(" ");
  }

  async function refreshRenameDeepLUsage() {
    if (!els.renameDeeplQuotaLine) {
      return;
    }
    var q = renameQueueRels.length;
    try {
      var r = await fetch(
        "/api/rename/deepl-usage?queue_size=" + encodeURIComponent(String(q))
      );
      var j = await r.json().catch(function () {
        return {};
      });
      if (!r.ok) {
        els.renameDeeplQuotaLine.textContent = "Could not load DeepL usage.";
        return;
      }
      els.renameDeeplQuotaLine.textContent = formatRenameDeepLUsage(j);
    } catch (_e) {
      els.renameDeeplQuotaLine.textContent = "Could not load DeepL usage (network).";
    }
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

  var LIBRARY_LAST_FOLDER_LS = "archive_console_library_last_folder_v1";

  function libraryReadLastFolderPayload() {
    try {
      var raw = localStorage.getItem(LIBRARY_LAST_FOLDER_LS);
      if (!raw) {
        return null;
      }
      return JSON.parse(raw);
    } catch (_e) {
      return null;
    }
  }

  function libraryPersistCurrentFolder(pathAfterList) {
    try {
      var pathStr = pathAfterList != null ? String(pathAfterList) : "";
      void fetch("/api/settings", { credentials: "same-origin" })
        .then(function (r) {
          return r.ok ? r.json() : null;
        })
        .then(function (sj) {
          if (!sj || !sj.archive_root) {
            return;
          }
          localStorage.setItem(
            LIBRARY_LAST_FOLDER_LS,
            JSON.stringify({
              archive_root: String(sj.archive_root),
              folder_rel: pathStr,
            })
          );
        });
    } catch (_e) {
      void _e;
    }
  }

  /** Non-directory rels for Rename: selected files if any selection; else all files in current listing. */
  function libraryCollectRelsForRenameSend() {
    var out = [];
    var hasSel = filesListSelectedSet.size > 0;
    var i;
    if (hasSel) {
      for (i = 0; i < filesListRowModels.length; i++) {
        var row = filesListRowModels[i];
        if (!filesListSelectedSet.has(row.rel) || row.is_dir) {
          continue;
        }
        out.push(row.rel);
      }
      return out;
    }
    for (i = 0; i < filesListRowModels.length; i++) {
      var row2 = filesListRowModels[i];
      if (!row2.is_dir) {
        out.push(row2.rel);
      }
    }
    return out;
  }

  /** Queueable media for player: selected files if any selection; else all queueable in listing. */
  function libraryCollectPlayablesForPlayerSend() {
    var out = [];
    var hasSel = filesListSelectedSet.size > 0;
    var i;
    for (i = 0; i < filesListRowModels.length; i++) {
      var row = filesListRowModels[i];
      if (row.is_dir) {
        continue;
      }
      if (hasSel && !filesListSelectedSet.has(row.rel)) {
        continue;
      }
      if (filesPlayerIsQueueableRel(row.rel)) {
        out.push(row.rel);
      }
    }
    return out;
  }

  function libraryUpdateSelectionActionButtons() {
    if (els.btnFileDetailSendRename) {
      var renameRels = libraryCollectRelsForRenameSend();
      var renameN = renameRels.length;
      els.btnFileDetailSendRename.disabled = renameN === 0;
      if (els.fileDetailRenameSendHint) {
        if (filesListSelectedSet.size > 0) {
          els.fileDetailRenameSendHint.textContent = renameN
            ? "Selection active: " +
              renameN +
              " file(s) will be added (folders skipped). Clear selection to use every file in this folder list."
            : "Selection is only folders or empty — select files, or clear selection to use all files in this folder.";
        } else {
          els.fileDetailRenameSendHint.textContent = renameN
            ? "No selection — all " +
              renameN +
              " file(s) in this folder listing will be added (folders skipped)."
            : "No files in this folder listing to add.";
        }
      }
    }
    if (els.btnFileDetailAddPlayerQueue) {
      var playables = libraryCollectPlayablesForPlayerSend();
      var playN = playables.length;
      els.btnFileDetailAddPlayerQueue.disabled = playN === 0;
      if (els.fileDetailPlayerQueueHint) {
        if (filesListSelectedSet.size > 0) {
          els.fileDetailPlayerQueueHint.textContent = playN
            ? "Selection active: " +
              playN +
              " queueable file(s) will be added in list order (folders and unsupported types skipped)."
            : "Selection has no queueable files — use video, audio, or jpg/png/gif/webp, or clear selection to add every queueable file in this folder.";
        } else {
          els.fileDetailPlayerQueueHint.textContent = playN
            ? "No selection — all " +
              playN +
              " queueable file(s) in this folder listing will be added."
            : "No queueable files in this folder listing (video, audio, or jpg/png/gif/webp).";
        }
      }
    }
  }

  function libraryUpdateSendRenameButton() {
    libraryUpdateSelectionActionButtons();
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
    void refreshRenameDeepLUsage();
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

  async function refreshRenameHistoryOnly() {
    if (!els.renameLogBody) {
      return;
    }
    try {
      var r = await fetch("/api/rename/history");
      if (r.ok) {
        var j = await r.json();
        renameHistoryItems = j.items || [];
        renderRenameLog();
      }
    } catch {
      void 0;
    }
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
      var isFail =
        run.status === "fail" ||
        (run.ledger_kind &&
          String(run.ledger_kind).indexOf("_failed") >= 0);
      var resultLabel = isFail ? "Failed" : "OK";
      tr.appendChild(td(dt));
      tr.appendChild(td(String(run.operation || "")));
      tr.appendChild(td(resultLabel));
      tr.appendChild(
        td(isFail ? "—" : String(run.ok != null ? run.ok : "0")),
      );
      tr.appendChild(
        td(isFail ? "—" : String(run.skip != null ? run.skip : "0")),
      );
      tr.appendChild(
        td(isFail ? "—" : String(run.fail != null ? run.fail : "0")),
      );
      tr.appendChild(td(String(run.run_id || "").slice(0, 8) + "…"));
      tr.style.cursor = "pointer";
      tr.title = isFail
        ? "Click for error summary (sanitized)"
        : "Click for per-file detail";
      tr.className = isFail ? "rename-log-row-fail" : "";
      tr.addEventListener("click", function () {
        if (!els.renameLogDetail) {
          return;
        }
        if (isFail) {
          var bits = [];
          if (run.error_code) {
            bits.push("Code: " + String(run.error_code));
          }
          if (run.message) {
            bits.push("Message: " + String(run.message));
          }
          if (run.diagnostic_ref) {
            bits.push(
              "Diagnostic ref (correlate with server log): " +
                String(run.diagnostic_ref),
            );
          }
          if (run.rel_count != null && run.rel_count !== "") {
            bits.push("Files in request: " + String(run.rel_count));
          }
          if (run.preview_id) {
            bits.push("Preview id: " + String(run.preview_id).slice(0, 16) + "…");
          }
          if (run.errors && run.errors.length) {
            bits.push("Structured errors:");
            run.errors.forEach(function (er) {
              bits.push(
                (er.ts_utc || "—") +
                  " [" +
                  (er.stage || "") +
                  "] " +
                  (er.message || ""),
              );
            });
          }
          els.renameLogDetail.textContent = bits.length
            ? bits.join("\n")
            : "(no detail)";
          els.renameLogDetail.hidden = false;
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
        if (run.errors && run.errors.length) {
          lines.push("— Structured warnings (partial failures) —");
          run.errors.forEach(function (er) {
            lines.push(
              (er.ts_utc || "—") +
                " [" +
                (er.stage || "") +
                "] " +
                (er.message || ""),
            );
          });
        }
        els.renameLogDetail.textContent = lines.join("\n") || "(no items)";
        els.renameLogDetail.hidden = false;
      });
      els.renameLogBody.appendChild(tr);
    });
  }

  function renameBuildPipelineOptions() {
    var useDeepl = !els.optRenameUseDeepl || els.optRenameUseDeepl.checked;
    var useExif = !!(els.optRenameUseExif && els.optRenameUseExif.checked);
    return {
      useDeepl: useDeepl,
      useExif: useExif,
      options: {
        whole_basename: !!(els.optRenameWholeBasename && els.optRenameWholeBasename.checked),
        preserve_youtube_id: els.optRenamePreserveYt
          ? els.optRenamePreserveYt.checked
          : true,
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
          els.selRenameExifMissing && els.selRenameExifMissing.value === "skip"
            ? "skip"
            : "keep_basename",
      },
    };
  }

  function renameValidatePipeline(pipe) {
    if (!pipe.useDeepl && !pipe.useExif) {
      return "Enable at least one of DeepL or Exif template in Pipeline.";
    }
    if (pipe.useExif && !pipe.options.exif_template) {
      return "Enter an Exif template or turn off Exif template.";
    }
    return "";
  }

  function renameFolderSetStatus(text) {
    if (els.renameFolderStatus) {
      els.renameFolderStatus.textContent = text || "";
    }
  }

  async function renameFolderScan() {
    renameFolderSetStatus("");
    renameFolderBatchState = null;
    if (els.btnRenameFolderRun) {
      els.btnRenameFolderRun.disabled = true;
    }
    var folderRel =
      els.inpRenameFolderRel && els.inpRenameFolderRel.value
        ? els.inpRenameFolderRel.value.trim().replace(/\\/g, "/")
        : "";
    if (!folderRel) {
      renameFolderSetStatus("Enter a folder path or use Browse folder…");
      return;
    }
    var pipe = renameBuildPipelineOptions();
    var pipeErr = renameValidatePipeline(pipe);
    if (pipeErr) {
      renameFolderSetStatus(pipeErr);
      return;
    }
    try {
      var r = await fetch("/api/rename/folder-candidates", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          folder_rel: folderRel,
          recursive: !!(els.optRenameFolderRecursive && els.optRenameFolderRecursive.checked),
          skip_done: !!(els.optRenameFolderSkipDone && els.optRenameFolderSkipDone.checked),
          options: pipe.options,
        }),
      });
      var j = await r.json().catch(function () {
        return {};
      });
      if (!r.ok) {
        var det = j.detail != null ? j.detail : r.statusText;
        renameFolderSetStatus(typeof det === "string" ? det : JSON.stringify(det));
        return;
      }
      renameFolderBatchState = j;
      var msg =
        "Found " +
        (j.total_in_folder != null ? j.total_in_folder : 0) +
        " file(s) in folder";
      if (j.skipped_done) {
        msg += "; " + j.skipped_done + " already renamed (skipped)";
      }
      msg += "; " + (j.pending_count != null ? j.pending_count : 0) + " pending";
      if (j.done_log_entries) {
        msg += " (" + j.done_log_entries + " in done log for this pipeline)";
      }
      renameFolderSetStatus(msg);
      if (els.btnRenameFolderRun) {
        els.btnRenameFolderRun.disabled = !(j.pending_count > 0);
      }
    } catch (_e) {
      renameFolderSetStatus("Scan failed (network).");
    }
  }

  async function renameFolderBatchRun() {
    if (!renameFolderBatchState || !renameFolderBatchState.pending_rels) {
      await renameFolderScan();
      if (!renameFolderBatchState || !renameFolderBatchState.pending_count) {
        return;
      }
    }
    var pipe = renameBuildPipelineOptions();
    var pipeErr = renameValidatePipeline(pipe);
    if (pipeErr) {
      renameFolderSetStatus(pipeErr);
      return;
    }
    var pending = renameFolderBatchState.pending_rels.slice();
    var batchSize = 200;
    if (els.selRenameFolderBatchSize && els.selRenameFolderBatchSize.value) {
      batchSize = Math.min(200, Math.max(1, parseInt(els.selRenameFolderBatchSize.value, 10) || 50));
    }
    var totalBatches = Math.ceil(pending.length / batchSize) || 0;
    if (
      !window.confirm(
        "Rename up to " +
          pending.length +
          " file(s) in " +
          totalBatches +
          " batch(es)? Already-renamed files are skipped. This cannot be undone from Archive Console."
      )
    ) {
      return;
    }
    renameFolderBatchAbort = false;
    if (els.btnRenameFolderRun) {
      els.btnRenameFolderRun.disabled = true;
    }
    if (els.btnRenameFolderScan) {
      els.btnRenameFolderScan.disabled = true;
    }
    if (els.btnRenameFolderStop) {
      els.btnRenameFolderStop.hidden = false;
    }
    var folderRel = renameFolderBatchState.folder_rel;
    var pipelineFp = renameFolderBatchState.pipeline_fp;
    var touchMtime = !!(els.optRenameFolderTouchMtime && els.optRenameFolderTouchMtime.checked);
    var processed = 0;
    var totalOk = 0;
    var totalSkip = 0;
    var totalFail = 0;
    for (var offset = 0; offset < pending.length; offset += batchSize) {
      if (renameFolderBatchAbort) {
        break;
      }
      var chunk = pending.slice(offset, offset + batchSize);
      var batchNum = Math.floor(offset / batchSize) + 1;
      renameFolderSetStatus(
        "Batch " +
          batchNum +
          "/" +
          totalBatches +
          " — previewing " +
          chunk.length +
          " file(s)… (" +
          processed +
          "/" +
          pending.length +
          " done so far)"
      );
      try {
        var pr = await fetch("/api/rename/preview", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            rels: chunk,
            max_files: chunk.length,
            options: pipe.options,
          }),
        });
        var pj = await pr.json().catch(function () {
          return {};
        });
        if (!pr.ok) {
          var pdet = pj.detail != null ? pj.detail : pr.statusText;
          renameFolderSetStatus(
            "Batch " +
              batchNum +
              " preview failed: " +
              (typeof pdet === "string" ? pdet : JSON.stringify(pdet))
          );
          break;
        }
        renameFolderSetStatus(
          "Batch " + batchNum + "/" + totalBatches + " — applying renames…"
        );
        var ar = await fetch("/api/rename/apply", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            preview_id: pj.preview_id,
            folder_batch: {
              folder_rel: folderRel,
              pipeline_fp: pipelineFp,
              touch_mtime: touchMtime,
            },
          }),
        });
        var aj = await ar.json().catch(function () {
          return {};
        });
        if (!ar.ok) {
          var adet = aj.detail != null ? aj.detail : ar.statusText;
          renameFolderSetStatus(
            "Batch " +
              batchNum +
              " apply failed: " +
              (typeof adet === "string" ? adet : JSON.stringify(adet))
          );
          break;
        }
        processed += chunk.length;
        totalOk += aj.ok != null ? aj.ok : 0;
        totalSkip += aj.skip != null ? aj.skip : 0;
        totalFail += aj.fail != null ? aj.fail : 0;
        renameFolderSetStatus(
          "Batch " +
            batchNum +
            "/" +
            totalBatches +
            " complete — OK " +
            (aj.ok != null ? aj.ok : 0) +
            ", skip " +
            (aj.skip != null ? aj.skip : 0) +
            ", fail " +
            (aj.fail != null ? aj.fail : 0) +
            " (" +
            processed +
            "/" +
            pending.length +
            " processed; running totals OK " +
            totalOk +
            ", fail " +
            totalFail +
            ")"
        );
      } catch (_e2) {
        renameFolderSetStatus("Batch " + batchNum + " failed (network).");
        break;
      }
    }
    if (renameFolderBatchAbort) {
      renameFolderSetStatus(
        "Stopped. Totals — OK " + totalOk + ", skip " + totalSkip + ", fail " + totalFail + "."
      );
    } else if (processed >= pending.length) {
      renameFolderSetStatus(
        "Folder batch finished — OK " +
          totalOk +
          ", skip " +
          totalSkip +
          ", fail " +
          totalFail +
          ". Re-scan to confirm nothing pending."
      );
    }
    renameFolderBatchAbort = false;
    renameFolderBatchState = null;
    if (els.btnRenameFolderRun) {
      els.btnRenameFolderRun.disabled = true;
    }
    if (els.btnRenameFolderScan) {
      els.btnRenameFolderScan.disabled = false;
    }
    if (els.btnRenameFolderStop) {
      els.btnRenameFolderStop.hidden = true;
    }
    void loadRunOverview();
    void refreshRenameHistoryOnly();
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
    var pipe = renameBuildPipelineOptions();
    var pipeErr = renameValidatePipeline(pipe);
    if (pipeErr) {
      els.renameMsg.textContent = pipeErr;
      return;
    }
    if (renameQueueRels.length > RENAME_PREVIEW_MAX_FILES) {
      els.renameMsg.textContent =
        "Queue has " +
        renameQueueRels.length +
        " files (max " +
        RENAME_PREVIEW_MAX_FILES +
        " per manual preview). Use Folder batch or remove files from the queue.";
      return;
    }
    var body = {
      rels: renameQueueRels.slice(),
      max_files: Math.min(renameQueueRels.length, RENAME_PREVIEW_MAX_FILES),
      options: pipe.options,
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
        if (det != null && typeof det === "object" && !Array.isArray(det)) {
          var dm = det.message != null ? String(det.message) : "";
          els.renameMsg.textContent =
            dm ||
            (det.error_code
              ? String(det.error_code) + " — see server log."
              : JSON.stringify(det));
        } else {
          els.renameMsg.textContent =
            typeof det === "string" ? det : JSON.stringify(det);
        }
        void refreshRenameHistoryOnly();
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
      var usageText = formatRenamePreviewUsage(j.usage || {});
      if (els.renameUsageLine) {
        if (usageText) {
          els.renameUsageLine.textContent = usageText;
          els.renameUsageLine.hidden = false;
        } else if (pipe.useDeepl) {
          els.renameUsageLine.textContent =
            "DeepL did not return character counts for this preview; see your DeepL dashboard.";
          els.renameUsageLine.hidden = false;
        } else {
          els.renameUsageLine.hidden = true;
        }
      }
      void refreshRenameDeepLUsage();
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
        void refreshRenameHistoryOnly();
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
        historyRenderState.globalErrors = [];
      } else {
        var hj = await hr.json();
        histItems = hj.items || [];
        historyRenderState.globalErrors = hj.global_errors || [];
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
      historyRenderState.globalErrors = [];
      renameHistoryItems = [];
    }
    historyRenderState.items = histItems;
    historyRenderState.pointers = rep.pointers || {};
    historyRenderState.recentRuns = rep.recent_runs || [];
    historyRenderState.latestFolders = latestFoldersFromPointers(
      historyRenderState.pointers
    );
    renderHistoryRows();
    renderGlobalConsoleErrors();
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
      btn.title = rel ? rel : "Download output folders";
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

  function filesListFilterQuery() {
    return (els.filesListFilter && els.filesListFilter.value.trim().toLowerCase()) || "";
  }

  function filesListEnsureAllRowModels() {
    if (filesListAllRowModels.length > 0) {
      return;
    }
    if (filesListRowModels.length > 0) {
      filesListAllRowModels = filesListRowModels.slice();
      return;
    }
    if (!els.fileList) {
      return;
    }
    var rebuilt = [];
    els.fileList.querySelectorAll("li button[data-file-rel]").forEach(function (btn) {
      var rel = btn.dataset.fileRel || "";
      if (!rel) {
        return;
      }
      var title = btn.getAttribute("title") || rel;
      var text = btn.textContent || "";
      var isDir = text.indexOf("📁") === 0;
      var slash = title.lastIndexOf("/");
      var name = slash >= 0 ? title.slice(slash + 1) : title;
      if (!name) {
        name = text.replace(/^📁\s|^📄\s/, "");
      }
      rebuilt.push({
        rel: rel,
        is_dir: isDir,
        name: name,
        ent: { rel: rel, is_dir: isDir, name: name, mtime: 0, size: null },
      });
    });
    if (rebuilt.length) {
      filesListAllRowModels = rebuilt;
    }
  }

  function filesListFilteredRowModels() {
    filesListEnsureAllRowModels();
    var q = filesListFilterQuery();
    if (!q) {
      return filesListAllRowModels.slice();
    }
    return filesListAllRowModels.filter(function (row) {
      var name = String(row.name || "").toLowerCase();
      var rel = String(row.rel || "").toLowerCase();
      return name.indexOf(q) >= 0 || rel.indexOf(q) >= 0;
    });
  }

  function filesListOnFilterInput() {
    filesListAnchorIndex = -1;
    renderFilesList();
  }

  function renderFilesList() {
    if (!els.fileList) {
      return;
    }
    filesListRowModels = filesListFilteredRowModels();
    els.fileList.innerHTML = "";
    if (!filesListRowModels.length) {
      var emptyLi = document.createElement("li");
      var emptyEm = document.createElement("em");
      emptyEm.className = "muted";
      emptyEm.textContent = filesListFilterQuery()
        ? "No matching files in this folder."
        : "This folder is empty.";
      emptyLi.appendChild(emptyEm);
      els.fileList.appendChild(emptyLi);
      updateExplorerButton();
      fpUpdatePlayerActionButtons();
      return;
    }
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
    filesListApplySelectionVisual();
    updateExplorerButton();
    fpUpdatePlayerActionButtons();
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
      filesListAllRowModels = [];
      filesListRowModels = [];
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
    if (els.filesListFilter) {
      els.filesListFilter.value = "";
    }
    filesListAllRowModels = (j.entries || []).map(function (ent) {
      return {
        rel: ent.rel,
        is_dir: !!ent.is_dir,
        name: ent.name,
        ent: ent,
      };
    });
    renderFilesList();
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
    libraryPersistCurrentFolder(filePath);
    libraryUpdateSendRenameButton();
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
    if (intent) {
      await browseTo("");
      await applyFilesWatchIntent(intent);
      libraryUpdateSendRenameButton();
      return;
    }
    var curRoot = "";
    try {
      var sr = await fetch("/api/settings", { credentials: "same-origin" });
      if (sr.ok) {
        var sj = await sr.json();
        curRoot = String(sj.archive_root || "");
      }
    } catch (_e) {
      void _e;
    }
    var saved = libraryReadLastFolderPayload();
    if (
      curRoot &&
      saved &&
      String(saved.archive_root || "") === curRoot &&
      typeof saved.folder_rel === "string"
    ) {
      var pathTry = saved.folder_rel;
      var lr = await fetch(
        "/api/files/list?path=" + encodeURIComponent(pathTry),
        { credentials: "same-origin" }
      );
      if (lr.ok) {
        var lj = await lr.json();
        if (lj.type !== "file") {
          await browseTo(pathTry);
          return;
        }
      }
    }
    await browseTo("");
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
    var fdTarget = els.fileDetailMain || els.fileDetail;
    if (fdTarget) {
      fdTarget.innerHTML =
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
    }
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
        if (mi.help_url) {
          inner +=
            "<p class=\"muted small file-detail-mi-help\"><a class=\"link\" href=\"" +
            esc(String(mi.help_url)) +
            "\" target=\"_blank\" rel=\"noopener noreferrer\">MediaInfo CLI — official download</a>" +
            " · or set the executable path under <strong>Settings</strong>.</p>";
        }
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
      dupDownloadOutputRoots = dupOutputRootsFromSettings(j);
      renderDupRootCheckboxes();
      restoreDupResultsIfReady();
    } catch (_e) {
      void _e;
    }
  }

  function renderDupRootCheckboxes() {
    if (!els.dupRootChecks) {
      return;
    }
    var parts = [];
    (dupDownloadOutputRoots || []).forEach(function (item, i) {
      var id = "dupRootOut_" + i;
      parts.push(
        '<label class="chk dup-root-label"><input type="checkbox" id="' +
          esc(id) +
          '" data-dup-root="' +
          esc(item.rel) +
          '" /> <span>' +
          esc(item.label) +
          ' <span class="muted">(' +
          esc(item.rel) +
          ")</span></span></label>"
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

  function setDupScanUiBusy(busy) {
    dupScanBusy = !!busy;
    if (els.btnDupScan) {
      els.btnDupScan.disabled = dupScanBusy;
    }
    if (els.btnDupReset) {
      els.btnDupReset.hidden = !dupScanBusy;
    }
  }

  function updateDupScanProgressFromStatus(j) {
    if (!els.dupScanProgress) {
      return;
    }
    var ph = (j && j.phase) || "idle";
    var prog = (j && j.progress) || {};
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

  async function fetchDupStatusLite() {
    var rs = await fetch("/api/duplicates/status", { credentials: "same-origin" });
    return rs.json();
  }

  async function fetchDupResults() {
    var rs = await fetch("/api/duplicates/results", { credentials: "same-origin" });
    if (!rs.ok) {
      return { groups: [] };
    }
    return rs.json();
  }

  async function waitForDupScanComplete() {
    for (;;) {
      await new Promise(function (res) {
        setTimeout(res, 450);
      });
      var st = await fetchDupStatusLite();
      updateDupScanProgressFromStatus(st);
      if ((st.phase || "") !== "running") {
        return st;
      }
    }
  }

  async function restoreDupResultsIfReady() {
    if (dupScanBusy || dupLastGroups.length) {
      return;
    }
    try {
      var st = await fetchDupStatusLite();
      if ((st.phase || "") === "running") {
        setDupScanUiBusy(true);
        updateDupScanProgressFromStatus(st);
        st = await waitForDupScanComplete();
        setDupScanUiBusy(false);
      }
      if ((st.phase || "") !== "success") {
        return;
      }
      var res = await fetchDupResults();
      dupLastGroups = res.groups || [];
      renderDupResults();
    } catch (_e) {
      void _e;
    }
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

  var SCHEDULE_WEEKDAYS = [
    ["0", "Monday"],
    ["1", "Tuesday"],
    ["2", "Wednesday"],
    ["3", "Thursday"],
    ["4", "Friday"],
    ["5", "Saturday"],
    ["6", "Sunday"],
  ];
  var YOUTUBE_SCHEDULE_JOBS = ["watch_later", "channels", "videos"];
  var GALLERY_SCHEDULE_JOB = "gallery_sources";

  function syncScheduleRowFields(row) {
    if (!row) {
      return;
    }
    var freqEl = row.querySelector(".sch-freq");
    var dayWrap = row.querySelector(".sch-day-wrap");
    var dowWrap = row.querySelector(".sch-dow-wrap");
    if (!freqEl) {
      return;
    }
    var f = freqEl.value || "monthly";
    if (dayWrap) {
      dayWrap.hidden = f !== "monthly";
    }
    if (dowWrap) {
      dowWrap.hidden = f !== "weekly";
    }
  }

  function scheduleJobLabel(job) {
    if (job === "gallery_sources") {
      return "Gallery saved sources (all)";
    }
    return job;
  }

  function syncGallerySourcesScheduleFields() {
    if (!els.gallerySourcesScheduleFreq) {
      return;
    }
    var f = els.gallerySourcesScheduleFreq.value || "daily";
    if (els.gallerySourcesScheduleDayWrap) {
      els.gallerySourcesScheduleDayWrap.hidden = f !== "monthly";
    }
    if (els.gallerySourcesScheduleDowWrap) {
      els.gallerySourcesScheduleDowWrap.hidden = f !== "weekly";
    }
  }

  function galleryScheduleMaxHoursFromSec(sec) {
    var n = typeof sec === "number" ? sec : parseInt(sec, 10);
    if (!n || n <= 0) {
      return 0;
    }
    return Math.min(24, Math.max(1, Math.round(n / 3600)));
  }

  function renderGallerySourcesSchedule(payload) {
    var sch = payload && payload.schedule;
    var enabled = !!(sch && sch.enabled);
    if (els.gallerySourcesScheduleEnabled) {
      els.gallerySourcesScheduleEnabled.checked = enabled;
    }
    if (sch) {
      if (els.gallerySourcesScheduleFreq) {
        els.gallerySourcesScheduleFreq.value = sch.frequency || "daily";
      }
      if (els.gallerySourcesScheduleDow) {
        els.gallerySourcesScheduleDow.value = String(
          typeof sch.day_of_week === "number" ? sch.day_of_week : 0
        );
      }
      if (els.gallerySourcesScheduleDay) {
        els.gallerySourcesScheduleDay.value = String(sch.day_of_month || 1);
      }
      if (els.gallerySourcesScheduleHour) {
        els.gallerySourcesScheduleHour.value = String(sch.hour != null ? sch.hour : 2);
      }
      if (els.gallerySourcesScheduleMin) {
        els.gallerySourcesScheduleMin.value = String(sch.minute != null ? sch.minute : 0);
      }
    }
    if (els.gallerySourcesScheduleMaxHours) {
      var maxSec =
        payload && typeof payload.scheduled_max_run_sec === "number"
          ? payload.scheduled_max_run_sec
          : 7200;
      els.gallerySourcesScheduleMaxHours.value = String(galleryScheduleMaxHoursFromSec(maxSec));
    }
    syncGallerySourcesScheduleFields();
    if (els.gallerySourcesScheduleStatus) {
      var parts = [];
      if (payload && payload.next_run && enabled) {
        parts.push("Next run (local): " + payload.next_run);
      } else if (enabled) {
        parts.push("Next run: —");
      }
      var capH =
        payload && typeof payload.scheduled_max_run_sec === "number"
          ? galleryScheduleMaxHoursFromSec(payload.scheduled_max_run_sec)
          : 2;
      parts.push(capH > 0 ? "Per-source limit: " + capH + "h" : "Per-source limit: none");
      if (payload && payload.scheduler_enabled === false) {
        parts.push(
          "Scheduler is off — enable it under Settings → Automatic scheduling, save, and restart the server."
        );
      }
      els.gallerySourcesScheduleStatus.textContent = parts.join(" · ");
    }
  }

  async function loadGallerySourcesSchedule() {
    try {
      var r = await fetch("/api/galleries/sources/schedule");
      if (r.status === 404) {
        if (els.gallerySourcesScheduleStatus) {
          els.gallerySourcesScheduleStatus.textContent =
            "Scheduled crawl requires a server restart — stop and start Archive Console, then hard-refresh this page (Ctrl+F5).";
        }
        return;
      }
      if (!r.ok) {
        return;
      }
      var j = await r.json();
      renderGallerySourcesSchedule(j);
    } catch {
      /* ignore */
    }
  }

  async function saveGallerySourcesSchedule() {
    if (!els.gallerySourcesScheduleEnabled) {
      return;
    }
    var freq = (els.gallerySourcesScheduleFreq && els.gallerySourcesScheduleFreq.value) || "daily";
    var body = {
      enabled: !!els.gallerySourcesScheduleEnabled.checked,
      frequency: freq,
      day_of_month: Math.min(
        31,
        Math.max(1, parseInt(els.gallerySourcesScheduleDay && els.gallerySourcesScheduleDay.value, 10) || 1)
      ),
      day_of_week: Math.min(
        6,
        Math.max(0, parseInt(els.gallerySourcesScheduleDow && els.gallerySourcesScheduleDow.value, 10) || 0)
      ),
      hour: Math.min(
        23,
        Math.max(0, parseInt(els.gallerySourcesScheduleHour && els.gallerySourcesScheduleHour.value, 10) || 0)
      ),
      minute: Math.min(
        59,
        Math.max(0, parseInt(els.gallerySourcesScheduleMin && els.gallerySourcesScheduleMin.value, 10) || 0)
      ),
      scheduled_max_run_sec: (function () {
        var maxH = Math.min(
          24,
          Math.max(
            0,
            parseInt(
              els.gallerySourcesScheduleMaxHours && els.gallerySourcesScheduleMaxHours.value,
              10
            ) || 0
          )
        );
        return maxH <= 0 ? 0 : maxH * 3600;
      })(),
    };
    try {
      var r = await fetch("/api/galleries/sources/schedule", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!r.ok) {
        var tx = await r.text();
        if (els.gallerySourcesScheduleStatus) {
          if (r.status === 404) {
            els.gallerySourcesScheduleStatus.textContent =
              "Save failed: server is running an older build. Restart Archive Console, hard-refresh (Ctrl+F5), then save again.";
          } else {
            els.gallerySourcesScheduleStatus.textContent =
              "Save failed: " + r.status + " " + tx;
          }
        }
        return;
      }
      var j = await r.json();
      renderGallerySourcesSchedule(j);
      if (els.gallerySourcesScheduleStatus) {
        var okMsg = body.enabled ? "Schedule saved." : "Schedule saved (disabled).";
        if (j.scheduler_enabled === false && body.enabled) {
          okMsg +=
            " Enable the scheduler under Settings → Automatic scheduling, save, and restart the server.";
        }
        var hint = els.gallerySourcesScheduleStatus.textContent || "";
        els.gallerySourcesScheduleStatus.textContent = hint
          ? okMsg + " · " + hint
          : okMsg;
      }
    } catch {
      if (els.gallerySourcesScheduleStatus) {
        els.gallerySourcesScheduleStatus.textContent = "Save failed (network).";
      }
    }
  }

  function scheduleHintForYoutube(hints) {
    return (hints || []).filter(function (h) {
      return h && h.schedule && h.schedule.job !== GALLERY_SCHEDULE_JOB;
    });
  }

  function schedulesForYoutube(schedules) {
    return (schedules || []).filter(function (s) {
      return s && s.job !== GALLERY_SCHEDULE_JOB;
    });
  }

  function updateYoutubeSchedulerHint(j) {
    if (!els.youtubeSchedulerHint) {
      return;
    }
    var feats = (j && j.features) || {};
    if (!feats.scheduler_enabled) {
      els.youtubeSchedulerHint.textContent =
        "Scheduler is off — enable it under Settings → Automatic scheduling, save, and restart the server.";
      return;
    }
    if (j && j.scheduler_backend_active) {
      els.youtubeSchedulerHint.textContent =
        "Scheduler is active on this server. Enabled entries below run automatically.";
      return;
    }
    els.youtubeSchedulerHint.textContent =
      "Scheduler is enabled in settings but inactive until you restart Archive Console.";
  }

  var ytdlpBatchRunSaveTimer = null;
  var lastYtdlpPreflightViaExtension = true;

  function syncYtdlpPreflightUi() {
    var on = !!(els.optPreflightViaExtension && els.optPreflightViaExtension.checked);
    if (els.optPreflightWaitRow) {
      els.optPreflightWaitRow.classList.toggle("is-disabled", !on);
    }
    if (els.optPreflightWaitSec) {
      els.optPreflightWaitSec.disabled = !on;
    }
  }

  function syncRunCookieGateHint() {
    if (!els.runCookieGateHint) {
      return;
    }
    if (lastYtdlpPreflightViaExtension) {
      els.runCookieGateHint.hidden = false;
      els.runCookieGateHint.textContent =
        "Before each run, the Firefox extension should refresh cookies.txt from an open YouTube tab (preflight below). Dry-run skips preflight.";
      return;
    }
    if (lastRemindersRequireCookieConfirmManual) {
      els.runCookieGateHint.hidden = false;
      els.runCookieGateHint.textContent =
        "Manual runs require confirming cookies.txt before start (Settings → Cookie hygiene). Dry-run skips this gate.";
      return;
    }
    els.runCookieGateHint.hidden = true;
    els.runCookieGateHint.textContent = "";
  }

  function syncYtdlpCookiePollUi() {
    var on = !!(els.optPauseOnCookieError && els.optPauseOnCookieError.checked);
    if (els.optCookieAuthPollRow) {
      els.optCookieAuthPollRow.classList.toggle("is-disabled", !on);
    }
    if (els.optCookieAuthPollSec) {
      els.optCookieAuthPollSec.disabled = !on;
    }
  }

  function applyYtdlpBatchRunFromSettings(j) {
    var ybr = (j && j.ytdlp_batch_run) || {};
    if (els.optPreflightViaExtension) {
      els.optPreflightViaExtension.checked =
        ybr.preflight_via_extension !== false;
    }
    if (els.optPreflightWaitSec) {
      var wait = ybr.preflight_wait_sec;
      els.optPreflightWaitSec.value = String(
        wait != null && wait !== undefined && isFinite(Number(wait))
          ? Number(wait)
          : 120
      );
    }
    lastYtdlpPreflightViaExtension =
      ybr.preflight_via_extension !== false;
    if (els.optPauseOnCookieError) {
      els.optPauseOnCookieError.checked = !!ybr.pause_on_cookie_error;
    }
    if (els.optCookieAuthPollSec) {
      var poll = ybr.cookie_auth_poll_sec;
      els.optCookieAuthPollSec.value = String(
        poll != null && poll !== undefined && isFinite(Number(poll)) ? Number(poll) : 15
      );
    }
    syncYtdlpPreflightUi();
    syncYtdlpCookiePollUi();
    syncRunCookieGateHint();
  }

  function readYtdlpBatchRunPatch() {
    var waitRaw =
      els.optPreflightWaitSec && els.optPreflightWaitSec.value != null
        ? parseInt(String(els.optPreflightWaitSec.value), 10)
        : 120;
    var waitSec = isFinite(waitRaw) ? waitRaw : 120;
    waitSec = Math.min(600, Math.max(10, waitSec));
    if (els.optPreflightWaitSec) {
      els.optPreflightWaitSec.value = String(waitSec);
    }
    var pollRaw =
      els.optCookieAuthPollSec && els.optCookieAuthPollSec.value != null
        ? parseInt(String(els.optCookieAuthPollSec.value), 10)
        : 15;
    var poll = isFinite(pollRaw) ? pollRaw : 15;
    poll = Math.min(3600, Math.max(5, poll));
    if (els.optCookieAuthPollSec) {
      els.optCookieAuthPollSec.value = String(poll);
    }
    lastYtdlpPreflightViaExtension = !!(
      els.optPreflightViaExtension && els.optPreflightViaExtension.checked
    );
    return {
      preflight_via_extension: lastYtdlpPreflightViaExtension,
      preflight_wait_sec: waitSec,
      pause_on_cookie_error: !!(els.optPauseOnCookieError && els.optPauseOnCookieError.checked),
      cookie_auth_poll_sec: poll,
    };
  }

  function scheduleSaveYtdlpBatchRunSettings() {
    window.clearTimeout(ytdlpBatchRunSaveTimer);
    ytdlpBatchRunSaveTimer = window.setTimeout(function () {
      void saveYtdlpBatchRunSettings();
    }, 400);
  }

  async function saveYtdlpBatchRunSettings() {
    try {
      var r = await fetch("/api/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "same-origin",
        body: JSON.stringify({ ytdlp_batch_run: readYtdlpBatchRunPatch() }),
      });
      if (!r.ok) {
        return;
      }
    } catch {
      /* ignore */
    }
  }

  async function loadYoutubeScheduleForm() {
    try {
      var r = await fetch("/api/settings");
      if (!r.ok) {
        return;
      }
      var j = await r.json();
      applyYtdlpBatchRunFromSettings(j);
      updateYoutubeSchedulerHint(j);
      renderScheduleEditor(
        schedulesForYoutube(j.schedules),
        scheduleHintForYoutube(j.schedule_hints),
        YOUTUBE_SCHEDULE_JOBS
      );
      if (els.scheduleSaveMsg) {
        els.scheduleSaveMsg.textContent = "";
      }
    } catch {
      /* ignore */
    }
  }

  async function mergeAndSaveSchedules(youtubeRows) {
    var cur = await fetch("/api/settings");
    if (!cur.ok) {
      throw new Error("Could not load current schedules.");
    }
    var cj = await cur.json();
    var galleryRows = (cj.schedules || []).filter(function (s) {
      return s && s.job === GALLERY_SCHEDULE_JOB;
    });
    var merged = galleryRows.concat(youtubeRows || []);
    var r = await fetch("/api/settings/schedules", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ schedules: merged }),
    });
    if (!r.ok) {
      var tx = await r.text();
      throw new Error(r.status + " " + tx);
    }
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
            esc(scheduleJobLabel(j)) +
            "</option>"
          );
        })
        .join("");
      var freq = s.frequency || "monthly";
      var freqOpts = ["daily", "weekly", "monthly"]
        .map(function (f) {
          return (
            "<option value=\"" +
            f +
            "\"" +
            (String(freq) === f ? " selected" : "") +
            ">" +
            f.charAt(0).toUpperCase() +
            f.slice(1) +
            "</option>"
          );
        })
        .join("");
      var dow = typeof s.day_of_week === "number" ? s.day_of_week : 0;
      var dowOpts = SCHEDULE_WEEKDAYS.map(function (pair) {
        return (
          "<option value=\"" +
          pair[0] +
          "\"" +
          (String(dow) === pair[0] ? " selected" : "") +
          ">" +
          esc(pair[1]) +
          "</option>"
        );
      }).join("");
      row.innerHTML =
        "<input type=\"hidden\" class=\"sch-id\" value=\"" +
        esc(sid) +
        "\" />" +
        "<label class=\"field compact\"><span>Job</span><select class=\"sch-job\">" +
        jobOpts +
        "</select></label>" +
        "<label class=\"field compact\"><span>Repeat</span><select class=\"sch-freq\">" +
        freqOpts +
        "</select></label>" +
        "<label class=\"field compact sch-day-wrap\"><span>Day (1–31)</span><input type=\"number\" class=\"sch-day\" min=\"1\" max=\"31\" value=\"" +
        esc(s.day_of_month) +
        "\" /></label>" +
        "<label class=\"field compact sch-dow-wrap\"><span>Weekday</span><select class=\"sch-dow\">" +
        dowOpts +
        "</select></label>" +
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
      var freqEl = row.querySelector(".sch-freq");
      if (freqEl) {
        freqEl.addEventListener("change", function () {
          syncScheduleRowFields(row);
        });
      }
      syncScheduleRowFields(row);
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
      var freq = row.querySelector(".sch-freq");
      var day = row.querySelector(".sch-day");
      var dow = row.querySelector(".sch-dow");
      var hour = row.querySelector(".sch-hour");
      var min = row.querySelector(".sch-min");
      var en = row.querySelector(".sch-en");
      if (!job) {
        return;
      }
      var frequency = (freq && freq.value) || "monthly";
      if (frequency !== "daily" && frequency !== "weekly" && frequency !== "monthly") {
        frequency = "monthly";
      }
      out.push({
        id: idEl ? idEl.value || "" : "",
        job: job.value,
        frequency: frequency,
        day_of_month: Math.min(31, Math.max(1, parseInt(day && day.value, 10) || 1)),
        day_of_week: Math.min(6, Math.max(0, parseInt(dow && dow.value, 10) || 0)),
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
      syncRunCookieGateHint();
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
    if (els.setAllowSummary) {
      var allowParts = (j.allowlisted_rel_prefixes || []).join(", ");
      var allowNote = j.allowlist_note || "";
      els.setAllowSummary.textContent = allowParts
        ? "Accessible: " + allowParts + (allowNote ? " — " + allowNote : "")
        : allowNote ||
          "Accessible folders come from Download output folders plus logs/ and cookies/.";
    }
    if (els.setArchiveRoot) {
      els.setArchiveRoot.value =
        j.archive_root != null && j.archive_root !== undefined
          ? String(j.archive_root)
          : "";
    }
    if (els.setEditorBackupMax) {
      els.setEditorBackupMax.value = j.editor_backup_max != null ? j.editor_backup_max : 10;
    }
    if (els.setFfmpegExe) {
      els.setFfmpegExe.value =
        j.ffmpeg_exe != null && j.ffmpeg_exe !== undefined ? String(j.ffmpeg_exe) : "";
    }
    if (els.setGifskiExe) {
      els.setGifskiExe.value =
        j.gifski_exe != null && j.gifski_exe !== undefined ? String(j.gifski_exe) : "";
    }
    if (els.setCzkawkaExe) {
      els.setCzkawkaExe.value =
        j.czkawka_exe != null && j.czkawka_exe !== undefined ? String(j.czkawka_exe) : "";
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
    if (els.setWeatherLat) {
      els.setWeatherLat.value =
        j.weather_latitude != null ? String(j.weather_latitude) : "";
    }
    if (els.setWeatherLon) {
      els.setWeatherLon.value =
        j.weather_longitude != null ? String(j.weather_longitude) : "";
    }
    if (els.setOpenweatherApiKey) {
      els.setOpenweatherApiKey.value = "";
      var owmSaved = !!j.openweather_api_key_saved;
      var owmEff = !!j.openweather_api_key_configured;
      if (owmSaved) {
        els.setOpenweatherApiKey.placeholder =
          "•••••••• (saved in state — type a new key to replace)";
      } else if (owmEff) {
        els.setOpenweatherApiKey.placeholder =
          "Using OPENWEATHER_API_KEY from environment (optional: store here)";
      } else {
        els.setOpenweatherApiKey.placeholder =
          "Optional — Open-Meteo used when blank";
      }
    }
    if (els.optOpenweatherKeyClear) {
      els.optOpenweatherKeyClear.checked = false;
    }
    if (els.homeWeatherSettingsMsg) {
      els.homeWeatherSettingsMsg.textContent = "";
    }
    homeApplyClock24FromLs();
    dupDownloadOutputRoots = dupOutputRootsFromSettings(j);
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
    if (els.optSchedulerEnabled) {
      els.optSchedulerEnabled.checked = !!feats.scheduler_enabled;
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
    if (els.optGotifyEnabled) {
      els.optGotifyEnabled.checked = !!j.gotify_enabled;
    }
    if (els.setGotifyBaseUrl) {
      els.setGotifyBaseUrl.value = j.gotify_base_url || "";
    }
    if (els.setGotifyAppToken) {
      els.setGotifyAppToken.value = "";
      els.setGotifyAppToken.placeholder = j.gotify_app_token_saved
        ? "Token saved (paste new token to replace, then Save)"
        : "Paste application token from Gotify → Apps";
    }
    if (els.optGotifyNotifyStart) {
      els.optGotifyNotifyStart.checked = j.gotify_notify_on_start !== false;
    }
    if (els.optGotifyNotifyComplete) {
      els.optGotifyNotifyComplete.checked = j.gotify_notify_on_complete !== false;
    }
    if (els.optGotifyNotifyScheduled) {
      els.optGotifyNotifyScheduled.checked = j.gotify_notify_scheduled !== false;
    }
    if (els.optGotifyNotifyManual) {
      els.optGotifyNotifyManual.checked = !!j.gotify_notify_manual;
    }
    if (els.setGotifyPriority) {
      els.setGotifyPriority.value =
        j.gotify_priority != null ? j.gotify_priority : 5;
    }
    if (els.gotifySettingsMsg) {
      els.gotifySettingsMsg.textContent = "";
    }
    if (els.gotifyFailureLine) {
      var gfu = j.gotify_last_failure_unix || 0;
      var gfm = String(j.gotify_last_failure_message || "").trim();
      if (gfu > 0 && gfm) {
        els.gotifyFailureLine.hidden = false;
        els.gotifyFailureLine.textContent = "Last Gotify error: " + gfm;
      } else {
        els.gotifyFailureLine.hidden = true;
        els.gotifyFailureLine.textContent = "";
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
    if (els.schedulerGlobalSaveMsg) {
      els.schedulerGlobalSaveMsg.textContent = "";
    }
    if (els.setShowGettingStarted) {
      els.setShowGettingStarted.checked = j.show_getting_started !== false;
    }
    if (els.setDefaultLandingView) {
      var dl = normalizeDefaultLandingView(j.default_landing_view);
      els.setDefaultLandingView.value = dl;
    }
    applyShowGettingStartedFromSettingsPayload(j);
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
                : "Single download";
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
    if (activeViewId === "library") {
      syncDupRootCheckboxesFromApi();
    }
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

  document.querySelectorAll(".btn-settings-browse").forEach(function (btn) {
    btn.addEventListener("click", async function () {
      var kind = btn.getAttribute("data-settings-browse") || "file";
      var targetId = btn.getAttribute("data-settings-target");
      var title = btn.getAttribute("data-settings-title") || "";
      var input = targetId ? document.getElementById(targetId) : null;
      if (!input || btn.disabled) {
        return;
      }
      function hostBrowseFeedback(text) {
        var statusId = btn.getAttribute("data-settings-status");
        if (statusId) {
          var node = document.getElementById(statusId);
          if (node) {
            node.textContent = text || "";
            return;
          }
        }
        if (els.settingsMsg) {
          els.settingsMsg.textContent = text || "";
        }
      }
      hostBrowseFeedback(
        kind === "file"
          ? "Opening file picker on this PC… (check behind this window if you do not see it)."
          : "Opening folder picker on this PC… (check behind this window if you do not see it)."
      );
      btn.disabled = true;
      try {
        var browseBody = { kind: kind, title: title };
        var currentPath = (input.value || "").trim();
        if (currentPath) {
          browseBody.initial_path = currentPath;
        }
        var r = await fetch("/api/settings/browse-host", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(browseBody),
        });
        if (r.status === 204) {
          hostBrowseFeedback(
            "No path selected. If no dialog appeared, it may be behind this window — try again or type the path manually."
          );
          return;
        }
        if (r.status === 503) {
          var d503 = await r.json().catch(function () {
            return {};
          });
          hostBrowseFeedback(
            (d503.detail && String(d503.detail)) ||
              "Native picker unavailable on this server — type the path manually."
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
          hostBrowseFeedback("Browse failed: " + r.status + " " + detail);
          return;
        }
        var j = await r.json();
        if (kind === "archive_relative" && j.rel != null) {
          input.value = j.rel || "";
        } else if (j.path != null) {
          input.value = j.path || "";
        }
        input.focus();
        if (btn.getAttribute("data-settings-status")) {
          hostBrowseFeedback(
            kind === "archive_relative" && j.rel
              ? "Selected " + j.rel + ". Click Scan folder."
              : "Path selected."
          );
        } else {
          hostBrowseFeedback("Path selected — click Save general to persist.");
        }
      } catch (ex) {
        hostBrowseFeedback(
          "Browse failed (network or server). Check that Archive Console is running."
        );
      } finally {
        btn.disabled = false;
      }
    });
  });

  /* Navigation */
  els.nav.forEach(function (btn) {
    btn.addEventListener("click", function () {
      const v = btn.getAttribute("data-view");
      var prevNavView = activeViewId;
      clearOneoffCookieBannerTimer();
      activateView(v);
      if (v === "history") {
        loadRunOverview();
      }
      if (v === "library" && prevNavView !== "library") {
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
        loadGallerydlFile();
      }
      if (v === "gifskyconf") {
        if (typeof window.gifskyconfSetupLoad === "function") {
          window.gifskyconfSetupLoad();
        } else {
          var gifskyWarn = document.getElementById("gifskyconfMsg");
          if (gifskyWarn) {
            gifskyWarn.textContent =
              "gifsky.conf editor script did not load. Hard-refresh (Ctrl+F5) or check Network for /static/gifski_setup.js.";
          }
        }
      }
      if (v === "supportedsites") {
        void loadSupportedsites(false);
      }
      if (v === "getting-started") {
        replaceStateView("getting-started", null);
        initGettingStartedView();
      }
      if (v === "home") {
        replaceStateView("home", null);
        initHomeView();
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
        void loadGallerySources();
        void refreshCookieReminder();
      }
      if (v === "gifsky") {
        loadDownloadDirsForm();
        void loadGifskyScan();
        void refreshCookieReminder();
      }
      if (v === "rename") {
        renderRenameQueue();
      }
    });
  });

  (function bindGettingStartedUi() {
    if (els.btnGsVerifyAll) {
      els.btnGsVerifyAll.addEventListener("click", function () {
        void fetchAndApplyToolVersions(null, null);
      });
    }
    document.querySelectorAll("[data-gs-verify-tool]").forEach(function (btn) {
      btn.addEventListener("click", function (ev) {
        var t = btn.getAttribute("data-gs-verify-tool");
        var el = ev.currentTarget;
        void fetchAndApplyToolVersions(t || null, el instanceof HTMLElement ? el : null);
      });
    });
    if (els.btnGsOpenCookies) {
      els.btnGsOpenCookies.addEventListener("click", function () {
        clearOneoffCookieBannerTimer();
        goToInputsFile("cookies.txt");
      });
    }
    if (els.btnGsOpenSiteCookies) {
      els.btnGsOpenSiteCookies.addEventListener("click", function () {
        clearOneoffCookieBannerTimer();
        activateView("inputs");
        replaceStateView("inputs", null);
        loadDownloadDirsForm();
        void refreshSiteCookiesPanel();
        var panel = document.getElementById("siteCookiesPanel");
        if (panel && panel.scrollIntoView) {
          panel.scrollIntoView({ behavior: "smooth", block: "start" });
        }
      });
    }
    if (els.btnSiteCookieAdd) {
      els.btnSiteCookieAdd.addEventListener("click", function () {
        void addSiteCookieFile();
      });
    }
    if (els.btnSiteCookiesRefresh) {
      els.btnSiteCookiesRefresh.addEventListener("click", function () {
        void refreshSiteCookiesPanel();
      });
    }
    if (els.btnGsOpenInputs) {
      els.btnGsOpenInputs.addEventListener("click", function () {
        clearOneoffCookieBannerTimer();
        activateView("inputs");
        replaceStateView("inputs", null);
        loadEditorFile(editorFile);
        loadDownloadDirsForm();
      });
    }
    if (els.btnGsOpenYtdlp) {
      els.btnGsOpenYtdlp.addEventListener("click", function () {
        clearOneoffCookieBannerTimer();
        activateView("ytdlp");
        replaceStateView("ytdlp", null);
        if (typeof window.ytdlpSetupLoad === "function") {
          window.ytdlpSetupLoad();
        }
      });
    }
    if (els.btnGsOpenGallerydl) {
      els.btnGsOpenGallerydl.addEventListener("click", function () {
        clearOneoffCookieBannerTimer();
        activateView("gallerydl");
        replaceStateView("gallerydl", null);
        loadGallerydlFile();
      });
    }
    function gsOpenGifskyconf() {
      clearOneoffCookieBannerTimer();
      activateView("gifskyconf");
      replaceStateView("gifskyconf", null);
      if (typeof window.gifskyconfSetupLoad === "function") {
        window.gifskyconfSetupLoad();
      }
    }
    if (els.btnGsOpenGifsky) {
      els.btnGsOpenGifsky.addEventListener("click", function () {
        clearOneoffCookieBannerTimer();
        activateView("gifsky");
        replaceStateView("gifsky", null);
        loadDownloadDirsForm();
        void loadGifskyScan();
      });
    }
    if (els.btnGsOpenLibrary) {
      els.btnGsOpenLibrary.addEventListener("click", function () {
        clearOneoffCookieBannerTimer();
        activateView("library");
        replaceStateView("library", null);
        var dup = document.getElementById("libraryDuplicates");
        if (dup && dup.scrollIntoView) {
          dup.scrollIntoView({ behavior: "smooth", block: "start" });
        }
      });
    }
    var btnGsOpenCzkawka = document.getElementById("btnGsOpenCzkawka");
    if (btnGsOpenCzkawka) {
      btnGsOpenCzkawka.addEventListener("click", function () {
        clearOneoffCookieBannerTimer();
        activateView("czkawka");
        replaceStateView("czkawka", null);
      });
    }
    document.querySelectorAll(".js-gs-open-gifskyconf, #btnGsOpenGifskyconf").forEach(function (btn) {
      btn.addEventListener("click", gsOpenGifskyconf);
    });
    if (els.btnGsOpenSettings) {
      els.btnGsOpenSettings.addEventListener("click", function () {
        clearOneoffCookieBannerTimer();
        activateView("settings");
        replaceStateView("settings", null);
        loadSettingsForm();
      });
    }
    var gsView = document.getElementById("view-getting-started");
    if (gsView) {
      gsView.addEventListener("change", function (ev) {
        var t = ev.target;
        if (t && t.matches && t.matches("[data-gs-check]")) {
          persistGettingStartedChecklist();
        }
      });
    }
  })();

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

  if (els.linkGalleriesToGallerydl) {
    els.linkGalleriesToGallerydl.addEventListener("click", function (ev) {
      ev.preventDefault();
      clearOneoffCookieBannerTimer();
      activateView("gallerydl");
      loadGallerydlFile();
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

  if (els.btnLibraryFileListFontMinus) {
    els.btnLibraryFileListFontMinus.addEventListener("click", function () {
      libraryFileListFontPx = Math.max(10, libraryFileListFontPx - 1);
      try {
        localStorage.setItem(
          STORAGE_LIBRARY_FILE_LIST_FONT,
          String(libraryFileListFontPx)
        );
      } catch (_e) {
        void _e;
      }
      applyLibraryFileListFont();
    });
  }
  if (els.btnLibraryFileListFontPlus) {
    els.btnLibraryFileListFontPlus.addEventListener("click", function () {
      libraryFileListFontPx = Math.min(22, libraryFileListFontPx + 1);
      try {
        localStorage.setItem(
          STORAGE_LIBRARY_FILE_LIST_FONT,
          String(libraryFileListFontPx)
        );
      } catch (_e2) {
        void _e2;
      }
      applyLibraryFileListFont();
    });
  }
  document.addEventListener("input", function (ev) {
    var t = ev.target;
    if (!t || t.id !== "filesListFilter") {
      return;
    }
    filesListOnFilterInput();
  });
  document.addEventListener("search", function (ev) {
    var t = ev.target;
    if (!t || t.id !== "filesListFilter") {
      return;
    }
    filesListOnFilterInput();
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
      if (r.status === 503) {
        var d503one = await r.json().catch(function () {
          return {};
        });
        appendOneoffLogLine(
          "[console] Cookie preflight timed out: " +
            ((d503one.detail && String(d503one.detail)) ||
              "enable Archive cookies bridge and keep a YouTube tab open.")
        );
        return;
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
    els.btnOneoffStop.addEventListener("click", function () {
      void postRunStop();
    });
  }

  function galleryPreviewHttpHref(raw) {
    try {
      var u = new URL(String(raw).trim());
      if (u.protocol !== "http:" && u.protocol !== "https:") {
        return "";
      }
      return u.href;
    } catch (_e) {
      return "";
    }
  }

  function galleryPreviewTruncateUrl(href, maxLen) {
    if (href.length <= maxLen) {
      return href;
    }
    var keep = Math.max(16, maxLen - 21);
    return href.slice(0, keep) + "…" + href.slice(-16);
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
      var td0 = document.createElement("td");
      td0.textContent = String(row.type || "");
      var td1 = document.createElement("td");
      td1.textContent = String(row.title || "");
      var td2 = document.createElement("td");
      td2.className = "gallery-preview-media-cell";
      var urls = Array.isArray(row.media_urls) ? row.media_urls : [];
      urls.forEach(function (u, idx) {
        if (idx > 0) {
          td2.appendChild(document.createElement("br"));
        }
        var href = galleryPreviewHttpHref(u);
        if (href) {
          var a = document.createElement("a");
          a.href = href;
          a.target = "_blank";
          a.rel = "noopener noreferrer";
          a.title = href;
          a.textContent = galleryPreviewTruncateUrl(href, 80);
          td2.appendChild(a);
        } else {
          var span = document.createElement("span");
          span.textContent = String(u);
          td2.appendChild(span);
        }
      });
      var td3 = document.createElement("td");
      td3.textContent = String(row.suggested_filename || "");
      tr.appendChild(td0);
      tr.appendChild(td1);
      tr.appendChild(td2);
      tr.appendChild(td3);
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
        if (j.cookies_passed_to_gallery_dl === false) {
          parts.push(
            "no root cookies.txt — optional gallery fallback; map cookies/<site>.txt in gallery-dl.conf for other sites."
          );
        }
        if (j.cookie_required_hint) {
          parts.push(
            "Preview empty or blocked — Reddit: OAuth or cookies/reddit.txt; other sites: cookies/<site>.txt in gallery-dl.conf, or skip preview and Run."
          );
        }
        if (j.stderr_preview) {
          parts.push("gallery-dl: " + j.stderr_preview);
        }
        if (j.parse_warnings && j.parse_warnings.length) {
          parts.push(
            "Parse / job: " + j.parse_warnings.slice(0, 4).join(" · ")
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

  function formatGallerySourceDisplayUrl(url) {
    var u = String(url || "").trim();
    if (!u) {
      return "";
    }
    return u.replace(
      /^(https?:\/\/(?:www\.)?reddit\.com\/user\/[^/?#]+)\/submitted\/?(?=[?#]|$)/i,
      "$1"
    );
  }

  function formatGalleryUtc(unix) {
    var n = Number(unix);
    if (!isFinite(n) || n <= 0) {
      return "—";
    }
    try {
      return new Date(n * 1000).toISOString().replace("T", " ").slice(0, 19);
    } catch {
      return "—";
    }
  }

  function buildGalleryStartBody(url) {
    var snap = null;
    if (galleryLastPreview && galleryLastPreview.url === url) {
      snap = {
        rows: galleryLastPreview.rows,
        truncated: galleryLastPreview.truncated,
        url: galleryLastPreview.url,
      };
    }
    return {
      url: url,
      output_rel: getGalleriesDirFormValue(),
      dry_run: !!(els.optGalleryDryRun && els.optGalleryDryRun.checked),
      video_fallback: !!(
        els.optGalleryVideoFallback && els.optGalleryVideoFallback.checked
      ),
      update_gallery_dl: !!(
        els.optGalleryUpdateGalleryDl && els.optGalleryUpdateGalleryDl.checked
      ),
      preview_snapshot: snap,
    };
  }

  async function startGalleryRunWithUrl(url) {
    var u = String(url || "").trim();
    if (!u) {
      if (els.galleryStartMsg) {
        els.galleryStartMsg.textContent = "Enter a gallery URL.";
      }
      return false;
    }
    if (els.galleryUrlInput) {
      els.galleryUrlInput.value =
        formatGallerySourceDisplayUrl(u) || u;
    }
    var body = buildGalleryStartBody(u);
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
        return false;
      }
      if (gate.error === "cookie_confirm_required") {
        if (els.galleryStartMsg) {
          els.galleryStartMsg.textContent =
            gate.message || "Confirm cookies in the dialog to continue.";
        }
        appendGalleryLogLine(
          "[console] Cookie confirmation required — confirm in the dialog or use Dry-run to skip."
        );
        const ok = await showCookieGateModal();
        if (!ok) {
          appendGalleryLogLine(
            "[console] Galleries run cancelled (cookies not confirmed)."
          );
          if (els.galleryStartMsg) {
            els.galleryStartMsg.textContent = "";
          }
          return false;
        }
        if (els.galleryStartMsg) {
          els.galleryStartMsg.textContent = "";
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
        return false;
      }
    }
    if (r.status === 409) {
      var t409g = await r.text();
      if (els.galleryStartMsg) {
        els.galleryStartMsg.textContent =
          t409g || "Another job is already running.";
      }
      appendGalleryLogLine("[console] " + (t409g || "Conflict (409)."));
      return false;
    }
    if (r.status === 400) {
      var tx2 = await r.text();
      var tx2s = tx2 || "Invalid request.";
      if (els.galleryStartMsg) {
        els.galleryStartMsg.textContent = tx2s;
      }
      appendGalleryLogLine("[console] Galleries start rejected: " + tx2s);
      return false;
    }
    if (!r.ok) {
      var failDetail = "Start failed (" + r.status + ").";
      try {
        var ej = await r.json();
        if (ej.detail != null) {
          failDetail =
            typeof ej.detail === "string"
              ? ej.detail
              : JSON.stringify(ej.detail);
        }
      } catch (_fe) {
        void _fe;
      }
      if (els.galleryStartMsg) {
        els.galleryStartMsg.textContent = failDetail;
      }
      appendGalleryLogLine("[console] " + failDetail);
      return false;
    }
    try {
      await r.json();
    } catch (_rj) {
      void _rj;
    }
    activeStreamJob = "galleries";
    return true;
  }

  function renderGallerySources(entries) {
    gallerySourcesEntries = Array.isArray(entries) ? entries : [];
    var tbody = els.gallerySourcesTbody;
    var wrap = els.gallerySourcesTableWrap;
    var scroll = els.gallerySourcesScroll;
    var countBadge = els.gallerySourcesCountBadge;
    var empty = els.gallerySourcesEmpty;
    if (!tbody) {
      return;
    }
    tbody.textContent = "";
    var count = gallerySourcesEntries.length;
    var has = count > 0;
    if (wrap) {
      wrap.hidden = !has;
    }
    if (scroll) {
      scroll.classList.toggle("is-scrollable", count > 10);
    }
    if (countBadge) {
      countBadge.textContent = has ? " (" + count + ")" : "";
    }
    if (empty) {
      empty.hidden = has;
    }
    gallerySourcesEntries.forEach(function (row) {
      var tr = document.createElement("tr");
      var tdCb = document.createElement("td");
      tdCb.className = "gallery-sources-check-col";
      var cb = document.createElement("input");
      cb.type = "checkbox";
      cb.className = "gallery-source-row-cb";
      cb.checked = true;
      cb.dataset.sourceId = String(row.id || "");
      cb.dataset.sourceUrl = String(row.url || "");
      tdCb.appendChild(cb);
      tr.appendChild(tdCb);
      function tdText(t, cls) {
        var td = document.createElement("td");
        if (cls) {
          td.className = cls;
        }
        td.textContent = t != null ? String(t) : "";
        return td;
      }
      tr.appendChild(tdText(row.label || "—", "gallery-source-label"));
      var tdUrl = document.createElement("td");
      tdUrl.className = "gallery-source-url muted small";
      var displayUrl =
        row.url_display ||
        formatGallerySourceDisplayUrl(row.url_input || row.url || "");
      tdUrl.textContent = displayUrl;
      tdUrl.title = displayUrl;
      tr.appendChild(tdUrl);
      tr.appendChild(tdText(formatGalleryUtc(row.last_run_unix)));
      tr.appendChild(tdText(row.run_count != null ? row.run_count : "0"));
      var exit =
        row.last_exit_code != null && row.last_exit_code !== ""
          ? String(row.last_exit_code)
          : "—";
      tr.appendChild(tdText(exit));
      tbody.appendChild(tr);
    });
  }

  async function loadGallerySources() {
    try {
      var r = await fetch("/api/galleries/sources");
      if (!r.ok) {
        if (els.gallerySourcesMsg) {
          els.gallerySourcesMsg.textContent = "Could not load saved sources.";
        }
        return;
      }
      var j = await r.json();
      renderGallerySources(j.entries || []);
      void loadGallerySourcesSchedule();
      if (els.gallerySourcesMsg) {
        els.gallerySourcesMsg.textContent = "";
      }
    } catch {
      if (els.gallerySourcesMsg) {
        els.gallerySourcesMsg.textContent = "Could not load saved sources.";
      }
    }
  }

  function getSelectedGallerySourceUrls() {
    var urls = [];
    document.querySelectorAll(".gallery-source-row-cb:checked").forEach(function (cb) {
      var u = cb.dataset.sourceUrl || "";
      if (u) {
        urls.push(u);
      }
    });
    return urls;
  }

  function getSelectedGallerySourceIds() {
    var ids = [];
    document.querySelectorAll(".gallery-source-row-cb:checked").forEach(function (cb) {
      var id = cb.dataset.sourceId || "";
      if (id) {
        ids.push(id);
      }
    });
    return ids;
  }

  async function runGalleryBatch(urls) {
    if (!urls.length) {
      if (els.gallerySourcesMsg) {
        els.gallerySourcesMsg.textContent = "Select at least one source.";
      }
      return;
    }
    if (els.galleryStartMsg) {
      els.galleryStartMsg.textContent = "";
    }
    galleryBatchTotal = urls.length;
    galleryBatchQueue = urls.slice(1);
    if (els.gallerySourcesMsg) {
      els.gallerySourcesMsg.textContent =
        "Batch 1/" + galleryBatchTotal + "…";
    }
    var ok = await startGalleryRunWithUrl(urls[0]);
    if (!ok) {
      galleryBatchQueue = [];
      galleryBatchTotal = 0;
      if (els.gallerySourcesMsg) {
        els.gallerySourcesMsg.textContent = "Batch stopped (could not start run).";
      }
    }
  }

  function continueGalleryBatchIfAny() {
    if (!galleryBatchQueue.length) {
      return;
    }
    var url = galleryBatchQueue.shift();
    var done = galleryBatchTotal - galleryBatchQueue.length;
    if (els.gallerySourcesMsg) {
      els.gallerySourcesMsg.textContent =
        "Batch " + done + "/" + galleryBatchTotal + "…";
    }
    void startGalleryRunWithUrl(url);
  }

  if (els.btnGalleryStart) {
    els.btnGalleryStart.addEventListener("click", async function () {
      if (els.galleryStartMsg) {
        els.galleryStartMsg.textContent = "";
      }
      galleryBatchQueue = [];
      galleryBatchTotal = 0;
      if (els.gallerySourcesMsg) {
        els.gallerySourcesMsg.textContent = "";
      }
      var url =
        (els.galleryUrlInput && els.galleryUrlInput.value.trim()) || "";
      await startGalleryRunWithUrl(url);
    });
  }

  if (els.btnGalleryRunSelected) {
    els.btnGalleryRunSelected.addEventListener("click", function () {
      void runGalleryBatch(getSelectedGallerySourceUrls());
    });
  }

  if (els.btnGallerySaveCurrent) {
    els.btnGallerySaveCurrent.addEventListener("click", async function () {
      var url =
        (els.galleryUrlInput && els.galleryUrlInput.value.trim()) || "";
      if (!url) {
        if (els.gallerySourcesMsg) {
          els.gallerySourcesMsg.textContent = "Enter a URL to save.";
        }
        return;
      }
      try {
        var r = await fetch("/api/galleries/sources", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ url: url }),
        });
        if (!r.ok) {
          var tx = await r.text();
          if (els.gallerySourcesMsg) {
            els.gallerySourcesMsg.textContent = tx || "Save failed.";
          }
          return;
        }
        if (els.gallerySourcesMsg) {
          els.gallerySourcesMsg.textContent =
            "Saved (not run). Use Run selected or Run galleries when ready.";
        }
        await loadGallerySources();
      } catch {
        if (els.gallerySourcesMsg) {
          els.gallerySourcesMsg.textContent = "Save failed.";
        }
      }
    });
  }

  if (els.btnGallerySourcesSelectAll) {
    els.btnGallerySourcesSelectAll.addEventListener("click", function () {
      document
        .querySelectorAll(".gallery-source-row-cb")
        .forEach(function (cb) {
          cb.checked = true;
        });
    });
  }

  if (els.btnGallerySourcesSelectNone) {
    els.btnGallerySourcesSelectNone.addEventListener("click", function () {
      document
        .querySelectorAll(".gallery-source-row-cb")
        .forEach(function (cb) {
          cb.checked = false;
        });
    });
  }

  if (els.btnGalleryRemoveSelected) {
    els.btnGalleryRemoveSelected.addEventListener("click", async function () {
      var ids = getSelectedGallerySourceIds();
      if (!ids.length) {
        if (els.gallerySourcesMsg) {
          els.gallerySourcesMsg.textContent = "Select sources to remove.";
        }
        return;
      }
      if (
        !window.confirm(
          "Remove " + ids.length + " saved source(s) from the list? (Files on disk are kept.)"
        )
      ) {
        return;
      }
      try {
        var r = await fetch("/api/galleries/sources/remove", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ ids: ids }),
        });
        if (!r.ok) {
          if (els.gallerySourcesMsg) {
            els.gallerySourcesMsg.textContent = "Remove failed.";
          }
          return;
        }
        await loadGallerySources();
        if (els.gallerySourcesMsg) {
          els.gallerySourcesMsg.textContent = "Removed selected sources.";
        }
      } catch {
        if (els.gallerySourcesMsg) {
          els.gallerySourcesMsg.textContent = "Remove failed.";
        }
      }
    });
  }

  if (els.gallerySourcesScheduleFreq) {
    els.gallerySourcesScheduleFreq.addEventListener("change", syncGallerySourcesScheduleFields);
  }
  if (els.btnSaveGallerySourcesSchedule) {
    els.btnSaveGallerySourcesSchedule.addEventListener("click", function () {
      void saveGallerySourcesSchedule();
    });
  }

  var gifskyPollTimer = null;

  function appendGifskyLogLine(line) {
    if (!els.gifskyLogBody) {
      return;
    }
    els.gifskyLogBody.textContent += String(line) + "\n";
    if (els.gifskyLogFrame) {
      els.gifskyLogFrame.scrollTop = els.gifskyLogFrame.scrollHeight;
    }
  }

  function clearGifskyLogView() {
    if (els.gifskyLogBody) {
      els.gifskyLogBody.textContent = "";
    }
  }

  function formatGifskyComparison(comp) {
    if (!comp || comp.video_bytes == null || comp.gif_bytes == null) {
      return "—";
    }
    var line =
      formatFileSize(comp.video_bytes) +
      " → " +
      formatFileSize(comp.gif_bytes);
    if (comp.label) {
      line += " (" + comp.label + ")";
    }
    return line;
  }

  function renderGifskyScan(j) {
    var tbody = els.gifskyFolderTbody;
    var wrap = els.gifskyFolderTableWrap;
    var scroll = els.gifskyFolderScroll;
    if (!tbody) {
      return;
    }
    tbody.textContent = "";
    var folders = (j && j.folders) || [];
    var has = folders.length > 0;
    if (wrap) {
      wrap.hidden = !has;
    }
    if (scroll) {
      scroll.classList.toggle("is-scrollable", folders.length > 10);
    }
    folders.forEach(function (row) {
      var tr = document.createElement("tr");
      var pendingN = row.pending_count != null ? row.pending_count : 0;
      var tdCb = document.createElement("td");
      tdCb.className = "gallery-sources-check-col";
      var cb = document.createElement("input");
      cb.type = "checkbox";
      cb.className = "gifsky-folder-row-cb";
      cb.checked = pendingN > 0;
      cb.disabled = pendingN <= 0;
      cb.dataset.folderRel = String(row.rel || "");
      tdCb.appendChild(cb);
      tr.appendChild(tdCb);
      function td(t) {
        var el = document.createElement("td");
        el.textContent = t != null ? String(t) : "";
        tr.appendChild(el);
      }
      td(row.rel || "");
      td(row.video_count != null ? row.video_count : "0");
      td(pendingN);
      td(row.gif_count != null ? row.gif_count : "0");
      var comp = row.size_comparison;
      td(comp && comp.video_bytes != null ? formatFileSize(comp.video_bytes) : "—");
      td(comp && comp.gif_bytes != null ? formatFileSize(comp.gif_bytes) : "—");
      td(formatGifskyComparison(comp));
      tbody.appendChild(tr);
    });
    if (els.gifskyGalleriesRoot && j && j.galleries_root_rel) {
      els.gifskyGalleriesRoot.textContent = j.galleries_root_rel + "/";
    }
    if (els.gifskyScanSummary && j && j.totals) {
      var t = j.totals;
      var summary =
        "Videos: " +
        (t.videos || 0) +
        " | pending conversion: " +
        (t.pending || 0) +
        " | existing GIFs: " +
        (t.gifs || 0) +
        " | skipped by rules: " +
        (t.skipped || 0);
      if (j.scan_warnings && j.scan_warnings.length) {
        summary += " — " + j.scan_warnings.join(" ");
      }
      if (j.size_comparison && j.size_comparison.paired_count) {
        summary +=
          " | paired vid→gif: " + formatGifskyComparison(j.size_comparison);
      }
      els.gifskyScanSummary.textContent = summary;
    }
  }

  async function loadGifskyScan() {
    if (els.gifskyMsg) {
      els.gifskyMsg.textContent = "Scanning…";
    }
    try {
      var r = await fetch("/api/gifsky/scan");
      if (!r.ok) {
        var tx = await r.text();
        if (els.gifskyMsg) {
          els.gifskyMsg.textContent = "Scan failed: " + tx;
        }
        return;
      }
      var j = await r.json();
      renderGifskyScan(j);
      if (els.gifskyMsg) {
        els.gifskyMsg.textContent = "";
      }
    } catch {
      if (els.gifskyMsg) {
        els.gifskyMsg.textContent = "Scan failed (network).";
      }
    }
  }

  function stopGifskyPoll() {
    if (gifskyPollTimer != null) {
      window.clearInterval(gifskyPollTimer);
      gifskyPollTimer = null;
    }
  }

  function startGifskyPoll() {
    stopGifskyPoll();
    gifskyPollTimer = window.setInterval(function () {
      void pollGifskyStatus();
    }, 800);
  }

  var gifskyLastLogLen = 0;

  async function pollGifskyStatus() {
    try {
      var r = await fetch("/api/gifsky/status");
      if (!r.ok) {
        return;
      }
      var j = await r.json();
      var logs = j.logs || [];
      for (var i = gifskyLastLogLen; i < logs.length; i++) {
        appendGifskyLogLine(logs[i]);
      }
      gifskyLastLogLen = logs.length;
      var phase = j.phase || "idle";
      var running = phase === "running";
      if (els.btnGifskyStart) {
        els.btnGifskyStart.disabled = running;
      }
      if (els.btnGifskyCancel) {
        els.btnGifskyCancel.disabled = !running;
      }
      if (!running && gifskyPollTimer != null) {
        stopGifskyPoll();
        void loadGifskyScan();
        if (els.gifskyMsg && j.job) {
          var msg =
            "Finished — converted " +
            (j.job.converted || 0) +
            ", failed " +
            (j.job.failed || 0);
          if (j.job.size_comparison && j.job.size_comparison.gif_bytes) {
            msg += " | " + formatGifskyComparison(j.job.size_comparison);
          }
          els.gifskyMsg.textContent = msg;
        }
      }
    } catch {
      /* ignore poll errors */
    }
  }

  function getSelectedGifskyFolderRels() {
    var rels = [];
    document.querySelectorAll(".gifsky-folder-row-cb:checked").forEach(function (cb) {
      var rel = cb.dataset.folderRel || "";
      if (rel) {
        rels.push(rel);
      }
    });
    return rels;
  }

  function setAllGifskyFolderChecks(checked) {
    document.querySelectorAll(".gifsky-folder-row-cb").forEach(function (cb) {
      if (!cb.disabled) {
        cb.checked = checked;
      }
    });
  }

  async function startGifskyBatch() {
    var folderRels = getSelectedGifskyFolderRels();
    if (!folderRels.length) {
      if (els.gifskyMsg) {
        els.gifskyMsg.textContent =
          "Select at least one folder with pending videos.";
      }
      return;
    }
    var deleteSrc =
      els.optGifskyDeleteSource && els.optGifskyDeleteSource.checked;
    var dryRun = els.optGifskyDryRun && els.optGifskyDryRun.checked;
    if (deleteSrc && !dryRun) {
      if (
        !window.confirm(
          "Delete each source video after its GIF passes verification? This cannot be undone."
        )
      ) {
        return;
      }
    }
    clearGifskyLogView();
    gifskyLastLogLen = 0;
    if (els.gifskyMsg) {
      els.gifskyMsg.textContent = "Starting…";
    }
    try {
      var r = await fetch("/api/gifsky/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          delete_source_after_verify: !!deleteSrc,
          dry_run: !!dryRun,
          folder_rels: folderRels,
        }),
      });
      if (!r.ok) {
        if (els.gifskyMsg) {
          els.gifskyMsg.textContent = "Start failed: " + (await r.text());
        }
        return;
      }
      var j = await r.json();
      var logs = (j.status && j.status.logs) || [];
      logs.forEach(function (ln) {
        appendGifskyLogLine(ln);
      });
      gifskyLastLogLen = logs.length;
      if (els.gifskyMsg) {
        els.gifskyMsg.textContent = "";
      }
      startGifskyPoll();
    } catch {
      if (els.gifskyMsg) {
        els.gifskyMsg.textContent = "Start failed (network).";
      }
    }
  }

  if (els.btnGifskyScan) {
    els.btnGifskyScan.addEventListener("click", function () {
      void loadGifskyScan();
    });
  }
  if (els.btnGifskyFoldersSelectAll) {
    els.btnGifskyFoldersSelectAll.addEventListener("click", function () {
      setAllGifskyFolderChecks(true);
    });
  }
  if (els.btnGifskyFoldersSelectNone) {
    els.btnGifskyFoldersSelectNone.addEventListener("click", function () {
      setAllGifskyFolderChecks(false);
    });
  }
  if (els.btnGifskyStart) {
    els.btnGifskyStart.addEventListener("click", function () {
      void startGifskyBatch();
    });
  }
  if (els.btnGifskyCancel) {
    els.btnGifskyCancel.addEventListener("click", function () {
      void fetch("/api/gifsky/cancel", { method: "POST" }).then(function () {
        void pollGifskyStatus();
      });
    });
  }
  if (els.btnGifskyClearLog) {
    els.btnGifskyClearLog.addEventListener("click", clearGifskyLogView);
  }
  if (els.linkGifskyToConf) {
    els.linkGifskyToConf.addEventListener("click", function (ev) {
      ev.preventDefault();
      activateView("gifskyconf");
      replaceStateView("gifskyconf", null);
      if (window.gifskyconfSetupLoad) {
        window.gifskyconfSetupLoad();
      }
    });
  }

  if (els.btnGalleryStop) {
    els.btnGalleryStop.addEventListener("click", function () {
      void postRunStop();
    });
  }

  els.btnStopRun.addEventListener("click", function () {
    void postRunStop();
  });

  els.btnCopyRunId.addEventListener("click", function () {
    var id = els.runMetaId.textContent;
    if (!id || id === "—") {
      return;
    }
    navigator.clipboard.writeText(id).catch(function () {});
  });

  if (els.optPreflightViaExtension) {
    els.optPreflightViaExtension.addEventListener("change", function () {
      syncYtdlpPreflightUi();
      syncRunCookieGateHint();
      scheduleSaveYtdlpBatchRunSettings();
    });
  }
  if (els.optPreflightWaitSec) {
    els.optPreflightWaitSec.addEventListener("change", scheduleSaveYtdlpBatchRunSettings);
    els.optPreflightWaitSec.addEventListener("input", scheduleSaveYtdlpBatchRunSettings);
  }
  if (els.optPauseOnCookieError) {
    els.optPauseOnCookieError.addEventListener("change", function () {
      syncYtdlpCookiePollUi();
      scheduleSaveYtdlpBatchRunSettings();
    });
  }
  if (els.optCookieAuthPollSec) {
    els.optCookieAuthPollSec.addEventListener("change", scheduleSaveYtdlpBatchRunSettings);
    els.optCookieAuthPollSec.addEventListener("input", scheduleSaveYtdlpBatchRunSettings);
  }

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
      if (r.status === 503) {
        var d503run = await r.json().catch(function () {
          return {};
        });
        appendLogLine(
          "[console] Cookie preflight timed out: " +
            ((d503run.detail && String(d503run.detail)) ||
              "enable Archive cookies bridge and keep a YouTube tab open.")
        );
        return;
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
    var body = {
      port: Number(els.setPort.value),
    };
    if (els.setArchiveRoot) {
      body.archive_root = els.setArchiveRoot.value.trim();
    }
    if (els.setEditorBackupMax) {
      body.editor_backup_max = Number(els.setEditorBackupMax.value);
    }
    if (els.setFfmpegExe) {
      body.ffmpeg_exe = els.setFfmpegExe.value.trim();
    }
    if (els.setGifskiExe) {
      body.gifski_exe = els.setGifskiExe.value.trim();
    }
    if (els.setCzkawkaExe) {
      body.czkawka_exe = els.setCzkawkaExe.value.trim();
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
    if (els.setShowGettingStarted) {
      body.show_getting_started = !!els.setShowGettingStarted.checked;
    }
    if (els.setDefaultLandingView) {
      body.default_landing_view = normalizeDefaultLandingView(
        els.setDefaultLandingView.value
      );
    }
    const r = await fetch("/api/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!r.ok) {
      var failDetail = "Save failed (" + r.status + ").";
      try {
        var errText = await r.text();
        if (errText) {
          try {
            var ej = JSON.parse(errText);
            if (ej.detail != null) {
              failDetail =
                typeof ej.detail === "string" ? ej.detail : JSON.stringify(ej.detail);
            } else {
              failDetail = "Save failed (" + r.status + "): " + errText.slice(0, 240);
            }
          } catch (_parseErr) {
            failDetail = "Save failed (" + r.status + "): " + errText.slice(0, 240);
          }
        }
      } catch (_e) {
        void _e;
      }
      els.settingsMsg.textContent = failDetail;
      return;
    }
    els.settingsMsg.textContent =
      "Saved. Restart the console if you changed the port or archive root.";
    syncDupRootCheckboxesFromApi();
    if (els.setShowGettingStarted) {
      lastShowGettingStarted = !!els.setShowGettingStarted.checked;
      syncGettingStartedSidebar(lastShowGettingStarted);
    }
  });

  if (els.btnSaveHomeWeather) {
    els.btnSaveHomeWeather.addEventListener("click", async function () {
      if (els.homeWeatherSettingsMsg) {
        els.homeWeatherSettingsMsg.textContent = "";
      }
      var body = {};
      if (els.setWeatherLat) {
        body.weather_latitude = els.setWeatherLat.value.trim();
      }
      if (els.setWeatherLon) {
        body.weather_longitude = els.setWeatherLon.value.trim();
      }
      if (els.optOpenweatherKeyClear && els.optOpenweatherKeyClear.checked) {
        body.openweather_api_key_clear = true;
      } else if (
        els.setOpenweatherApiKey &&
        els.setOpenweatherApiKey.value.trim()
      ) {
        body.openweather_api_key = els.setOpenweatherApiKey.value.trim();
      }
      var rw = await fetch("/api/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!rw.ok) {
        var wmsg = "Save failed.";
        try {
          var wj = await rw.json();
          if (wj.detail != null) {
            wmsg =
              typeof wj.detail === "string" ? wj.detail : JSON.stringify(wj.detail);
          }
        } catch (_w) {
          void _w;
        }
        if (els.homeWeatherSettingsMsg) {
          els.homeWeatherSettingsMsg.textContent = wmsg;
        }
        return;
      }
      await loadSettingsForm();
      if (els.homeWeatherSettingsMsg) {
        els.homeWeatherSettingsMsg.textContent = "Weather settings saved.";
      }
      if (activeViewId === "home") {
        void refreshHomeWeather();
      }
    });
  }

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

  if (els.btnFileDetailSendRename) {
    els.btnFileDetailSendRename.addEventListener("click", function () {
      var rels = libraryCollectRelsForRenameSend();
      if (!rels.length) {
        libraryViewToast(
          "No files to add — select files or open a folder that lists files.",
          true
        );
        return;
      }
      var a = renameQueueAddRels(rels);
      renderRenameQueue();
      libraryViewToast(
        "Added " + a + " path(s) to Rename queue (sidebar → Rename).",
        false
      );
    });
  }

  if (els.btnFileDetailAddPlayerQueue) {
    els.btnFileDetailAddPlayerQueue.addEventListener("click", function () {
      var playables = libraryCollectPlayablesForPlayerSend();
      if (!playables.length) {
        libraryViewToast(
          "No queueable files — select video, audio, or images, or open a folder that lists them.",
          true
        );
        return;
      }
      var added = fpAddPlayablesToQueue(playables);
      if (added === 0) {
        libraryViewToast("Those files were already in the player queue.", false);
      } else {
        libraryViewToast(
          "Added " +
            added +
            " to player queue (" +
            fpBaseQueue.length +
            " track(s) total). Open the player below to play.",
          false
        );
      }
      fpMsg("");
    });
  }

  if (els.btnRenameBrowseFiles) {
    els.btnRenameBrowseFiles.addEventListener("click", async function () {
      if (els.renameMsg) {
        els.renameMsg.textContent =
          "Opening file picker on this PC… (check behind this window if you do not see it).";
      }
      els.btnRenameBrowseFiles.disabled = true;
      try {
        var r = await fetch("/api/rename/browse-files", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({}),
        });
        if (r.status === 204) {
          if (els.renameMsg) {
            els.renameMsg.textContent = "";
          }
          return;
        }
        if (r.status === 503) {
          var d503 = await r.json().catch(function () {
            return {};
          });
          if (els.renameMsg) {
            els.renameMsg.textContent =
              (d503.detail && String(d503.detail)) ||
              "Native picker unavailable on this host — use Library → Send to Rename queue.";
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
              : "Browse failed.";
          if (els.renameMsg) {
            els.renameMsg.textContent = detail;
          }
          return;
        }
        var j = await r.json();
        var added = renameQueueAddRels(j.rels || []);
        renderRenameQueue();
        if (els.renameMsg) {
          var msg =
            added > 0
              ? "Added " + added + " file(s) to queue."
              : "No new files added (already queued or duplicates skipped).";
          if (j.skipped && j.skipped.length) {
            msg += " Skipped " + j.skipped.length + ".";
            if (j.skipped[0] && j.skipped[0].reason) {
              msg += " " + j.skipped[0].reason + ".";
            }
          }
          els.renameMsg.textContent = msg;
        }
      } catch (ex) {
        if (els.renameMsg) {
          els.renameMsg.textContent =
            "Browse failed: " + (ex && ex.message ? ex.message : String(ex));
        }
      } finally {
        els.btnRenameBrowseFiles.disabled = false;
      }
    });
  }

  if (els.btnRenameFolderScan) {
    els.btnRenameFolderScan.addEventListener("click", function () {
      void renameFolderScan();
    });
  }

  if (els.btnRenameFolderRun) {
    els.btnRenameFolderRun.addEventListener("click", function () {
      void renameFolderBatchRun();
    });
  }

  if (els.btnRenameFolderStop) {
    els.btnRenameFolderStop.addEventListener("click", function () {
      renameFolderBatchAbort = true;
      renameFolderSetStatus("Stopping after current batch…");
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
      if (dupScanBusy) {
        return;
      }
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
      setDupScanUiBusy(true);
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
          if (r.status === 409) {
            fpMsg(
              "Scan already running (UI may be out of sync). Click Reset scan, then try again."
            );
            if (els.btnDupReset) {
              els.btnDupReset.hidden = false;
            }
          } else {
            fpMsg("Scan failed: " + detail);
          }
          return;
        }
        var st = await waitForDupScanComplete();
        if (st.scan && st.scan.error) {
          fpMsg("Scan error: " + st.scan.error);
          dupLastGroups = [];
        } else if ((st.phase || "") === "success") {
          var res = await fetchDupResults();
          dupLastGroups = res.groups || [];
        } else {
          dupLastGroups = [];
        }
        renderDupResults();
      } catch (e) {
        fpMsg("Scan failed: " + (e && e.message ? e.message : String(e)));
      } finally {
        setDupScanUiBusy(false);
        if (els.dupScanProgress && !dupScanBusy) {
          var keepDone =
            dupLastGroups.length &&
            els.dupScanProgress.textContent === "Done.";
          if (!keepDone) {
            els.dupScanProgress.textContent = "";
          }
        }
      }
    });
  }

  if (els.btnDupReset) {
    els.btnDupReset.addEventListener("click", async function () {
      try {
        var r = await fetch("/api/duplicates/reset", {
          method: "POST",
          credentials: "same-origin",
        });
        var j = await r.json();
        if (!r.ok) {
          fpMsg("Reset failed: " + r.statusText);
          return;
        }
        setDupScanUiBusy(false);
        if (els.dupScanProgress) {
          els.dupScanProgress.textContent = "";
        }
        fpMsg(
          j.reset
            ? "Scan state cleared — you can run a new scan."
            : "No running scan to reset."
        );
      } catch (e) {
        fpMsg("Reset failed: " + (e && e.message ? e.message : String(e)));
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
        if (els.dupScanProgress) {
          els.dupScanProgress.textContent = "";
        }
        if (els.btnDupPreviewRemove) {
          els.btnDupPreviewRemove.disabled = true;
        }
        if (els.btnDupApplyRemove) {
          els.btnDupApplyRemove.disabled = true;
        }
        if (activeViewId === "library" && filePath) {
          void browseTo(filePath);
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
        job: YOUTUBE_SCHEDULE_JOBS[0] || "watch_later",
        frequency: "daily",
        day_of_month: 1,
        day_of_week: 0,
        hour: 2,
        minute: 0,
        enabled: false,
      });
      renderScheduleEditor(cur, [], YOUTUBE_SCHEDULE_JOBS);
    });
  }

  if (els.btnSaveSchedules) {
    els.btnSaveSchedules.addEventListener("click", async function () {
      if (els.scheduleSaveMsg) {
        els.scheduleSaveMsg.textContent = "";
      }
      var rows = collectSchedulesFromForm();
      try {
        await mergeAndSaveSchedules(rows);
      } catch (ex) {
        if (els.scheduleSaveMsg) {
          els.scheduleSaveMsg.textContent =
            "Save failed: " + (ex && ex.message ? ex.message : String(ex));
        }
        return;
      }
      await loadYoutubeScheduleForm();
      if (els.scheduleSaveMsg) {
        els.scheduleSaveMsg.textContent = "Schedules saved.";
      }
    });
  }

  if (els.btnSaveSchedulerGlobal) {
    els.btnSaveSchedulerGlobal.addEventListener("click", async function () {
      if (els.schedulerGlobalSaveMsg) {
        els.schedulerGlobalSaveMsg.textContent = "";
      }
      var r = await fetch("/api/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          scheduler_enabled: !!(els.optSchedulerEnabled && els.optSchedulerEnabled.checked),
        }),
      });
      if (!r.ok) {
        var tx = await r.text();
        if (els.schedulerGlobalSaveMsg) {
          els.schedulerGlobalSaveMsg.textContent = "Save failed: " + r.status + " " + tx;
        }
        return;
      }
      await loadSettingsForm();
      void loadYoutubeScheduleForm();
      if (els.schedulerGlobalSaveMsg) {
        els.schedulerGlobalSaveMsg.textContent =
          "Saved. Restart Archive Console for the scheduler to start or stop.";
      }
    });
  }

  function collectGotifySettingsPayload() {
    var payload = {
      gotify_enabled: !!(els.optGotifyEnabled && els.optGotifyEnabled.checked),
      gotify_base_url: els.setGotifyBaseUrl
        ? els.setGotifyBaseUrl.value.trim()
        : "",
      gotify_notify_on_start: !!(
        els.optGotifyNotifyStart && els.optGotifyNotifyStart.checked
      ),
      gotify_notify_on_complete: !!(
        els.optGotifyNotifyComplete && els.optGotifyNotifyComplete.checked
      ),
      gotify_notify_scheduled: !!(
        els.optGotifyNotifyScheduled && els.optGotifyNotifyScheduled.checked
      ),
      gotify_notify_manual: !!(
        els.optGotifyNotifyManual && els.optGotifyNotifyManual.checked
      ),
      gotify_priority: els.setGotifyPriority
        ? Number(els.setGotifyPriority.value)
        : 5,
    };
    if (els.setGotifyAppToken && els.setGotifyAppToken.value.trim()) {
      payload.gotify_app_token = els.setGotifyAppToken.value.trim();
    }
    return payload;
  }

  async function saveGotifySettingsFromForm() {
    if (els.gotifySettingsMsg) {
      els.gotifySettingsMsg.textContent = "";
    }
    var rg = await fetch("/api/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(collectGotifySettingsPayload()),
    });
    if (!rg.ok) {
      var gfail = "Save failed.";
      try {
        var ge = await rg.json();
        if (ge.detail != null) {
          gfail =
            typeof ge.detail === "string" ? ge.detail : JSON.stringify(ge.detail);
        }
      } catch (_ge) {
        void _ge;
      }
      if (els.gotifySettingsMsg) {
        els.gotifySettingsMsg.textContent = gfail;
      }
      return false;
    }
    await loadSettingsForm();
    return true;
  }

  if (els.btnSaveGotifySettings) {
    els.btnSaveGotifySettings.addEventListener("click", async function () {
      var ok = await saveGotifySettingsFromForm();
      if (ok && els.gotifySettingsMsg) {
        els.gotifySettingsMsg.textContent = "Gotify settings saved.";
      }
    });
  }

  if (els.btnGotifyTest) {
    els.btnGotifyTest.addEventListener("click", async function () {
      if (els.gotifySettingsMsg) {
        els.gotifySettingsMsg.textContent = "";
      }
      var tokenInForm =
        els.setGotifyAppToken && els.setGotifyAppToken.value.trim();
      if (tokenInForm) {
        var saved = await saveGotifySettingsFromForm();
        if (!saved) {
          return;
        }
      }
      var rt = await fetch("/api/settings/gotify/test", { method: "POST" });
      if (!rt.ok) {
        var tmsg = "Test failed.";
        try {
          var tj = await rt.json();
          if (tj.detail != null) {
            tmsg =
              typeof tj.detail === "string" ? tj.detail : JSON.stringify(tj.detail);
          }
        } catch (_tj) {
          void _tj;
        }
        if (els.gotifySettingsMsg) {
          els.gotifySettingsMsg.textContent = tmsg;
        }
        return;
      }
      await loadSettingsForm();
      if (els.gotifyFailureLine) {
        els.gotifyFailureLine.hidden = true;
        els.gotifyFailureLine.textContent = "";
      }
      if (els.gotifySettingsMsg) {
        els.gotifySettingsMsg.textContent = "Test message sent.";
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

  if (els.homeApplicationsToggle) {
    els.homeApplicationsToggle.addEventListener("click", function () {
      homeSetApplicationsEdit(!homeApplicationsEdit);
    });
  }
  if (els.btnHomeAddBookmark) {
    els.btnHomeAddBookmark.addEventListener("click", function () {
      openHomeBookmarkModal(null);
    });
  }
  if (els.btnHomeBookmarkCancel) {
    els.btnHomeBookmarkCancel.addEventListener("click", homeCloseBookmarkModal);
  }
  if (els.homeBookmarkModalBackdrop) {
    els.homeBookmarkModalBackdrop.addEventListener("click", homeCloseBookmarkModal);
  }
  if (els.btnHomeBookmarkSave) {
    els.btnHomeBookmarkSave.addEventListener("click", function () {
      homeCommitBookmarkFromModal();
    });
  }
  if (els.inpHomeBookmarkUrl) {
    els.inpHomeBookmarkUrl.addEventListener("input", function () {
      window.clearTimeout(homeUrlDebounceTimer);
      homeUrlDebounceTimer = window.setTimeout(function () {
        var raw =
          (els.inpHomeBookmarkUrl && els.inpHomeBookmarkUrl.value) || "";
        var ok = homeValidateUrl(raw.trim());
        if (els.homeBookmarkUrlMsg) {
          if (!raw.trim()) {
            els.homeBookmarkUrlMsg.textContent = "";
          } else if (!ok) {
            els.homeBookmarkUrlMsg.textContent =
              "Enter a valid http or https URL.";
          } else {
            els.homeBookmarkUrlMsg.textContent = "";
          }
        }
        homeSyncBookmarkSaveEnabled();
      }, HOME_URL_DEBOUNCE_MS);
    });
    els.inpHomeBookmarkUrl.addEventListener("keydown", function (ev) {
      if (
        ev.key === "Enter" &&
        els.btnHomeBookmarkSave &&
        !els.btnHomeBookmarkSave.disabled
      ) {
        homeCommitBookmarkFromModal();
      }
    });
  }
  if (els.optHomeClock24) {
    els.optHomeClock24.addEventListener("change", function () {
      try {
        localStorage.setItem(
          HOME_LS_CLOCK24,
          els.optHomeClock24.checked ? "1" : "0"
        );
      } catch (_e) {
        void _e;
      }
      tickHomeClock();
    });
  }

  connectStream();
  window.setInterval(refreshReminders, 120000);
  void (async function bootstrapArchiveConsoleUi() {
    var settingsPayload = null;
    try {
      var sr = await fetch("/api/settings");
      settingsPayload = await sr.json();
    } catch (_se) {
      void _se;
    }
    applyShowGettingStartedFromSettingsPayload(settingsPayload || {});
    applyYtdlpBatchRunFromSettings(settingsPayload || {});
    var initialView = resolveInitialViewFromSettings(settingsPayload);
    activateView(initialView);
    var fileOpt =
      initialView === "inputs"
        ? getInitialInputsFileFromUrl(initialView)
        : null;
    replaceStateView(initialView, fileOpt);
    runInitialViewBootstrap(initialView);
    void loadGallerySources();
    loadRunOverview();
    try {
      var _lfv = localStorage.getItem(STORAGE_LIBRARY_FILE_LIST_FONT);
      var _lfn = _lfv != null ? parseInt(_lfv, 10) : NaN;
      if (isFinite(_lfn) && _lfn >= 10 && _lfn <= 22) {
        libraryFileListFontPx = _lfn;
      }
    } catch (_lx) {
      void _lx;
    }
    applyLibraryFileListFont();
    applyLogFont();
    applyLogWrap();
    scrollHistorySectionFromUrl();
    initFilesSplitResizer();
    fpInitPlayerUi();
    fetch("/api/run/status")
    .then(function (r) {
      return r.json();
    })
    .then(function (j) {
      applyRunStatusFromServer(j);
    });
  })();

})();
