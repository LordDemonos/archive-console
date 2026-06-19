/* global window, document, fetch, localStorage */
(function () {
  "use strict";

  var pollTimer = null;
  var elapsedTimer = null;
  var scanBusy = false;
  var czkScanStartedAt = 0;
  var czkLastScanId = null;
  var czkLastMode = null;
  var czkLastGroups = [];
  var CZK_QUAR_STORAGE = "archive_console.czk.quarantine_abs.v1";
  var CZK_APPLY_CONFIRM = "DELETE_CZKAWKA_DUPLICATES";

  function $(id) {
    return document.getElementById(id);
  }

  function esc(s) {
    var d = document.createElement("div");
    d.textContent = s == null ? "" : String(s);
    return d.innerHTML;
  }

  function formatBytes(n) {
    var x = Number(n);
    if (!isFinite(x) || x < 0) {
      return "—";
    }
    if (x < 1024) {
      return x + " B";
    }
    if (x < 1024 * 1024) {
      return (x / 1024).toFixed(1) + " KB";
    }
    if (x < 1024 * 1024 * 1024) {
      return (x / (1024 * 1024)).toFixed(2) + " MB";
    }
    return (x / (1024 * 1024 * 1024)).toFixed(2) + " GB";
  }

  function splitPaths(text) {
    return String(text || "")
      .split(/\r?\n/)
      .map(function (line) {
        return line.trim();
      })
      .filter(Boolean);
  }

  function setMsg(el, text) {
    if (!el) {
      return;
    }
    el.textContent = text || "";
  }

  function formatElapsed(seconds) {
    var sec = Math.max(0, Math.floor(Number(seconds) || 0));
    var m = Math.floor(sec / 60);
    var s = sec % 60;
    return m > 0 ? m + "m " + s + "s" : s + "s";
  }

  function runningProgressText() {
    var msg = "Scan running…";
    if (czkScanStartedAt > 0) {
      msg += " (" + formatElapsed(Date.now() / 1000 - czkScanStartedAt) + ")";
    }
    return msg;
  }

  function startElapsedTimer() {
    stopElapsedTimer();
    elapsedTimer = window.setInterval(function () {
      if (scanBusy) {
        setMsg($("czkScanProgress"), runningProgressText());
      }
    }, 1000);
  }

  function stopElapsedTimer() {
    if (elapsedTimer) {
      window.clearInterval(elapsedTimer);
      elapsedTimer = null;
    }
  }

  function setStopButtonVisible(visible) {
    var stopBtn = $("btnCzkStop");
    if (stopBtn) {
      stopBtn.hidden = !visible;
      stopBtn.disabled = !visible;
    }
  }

  function setScanBusy(busy) {
    scanBusy = !!busy;
    var btn = $("btnCzkScan");
    if (btn) {
      btn.disabled = scanBusy;
      btn.setAttribute("aria-busy", scanBusy ? "true" : "false");
    }
    setStopButtonVisible(scanBusy);
    if (scanBusy) {
      startElapsedTimer();
    } else {
      stopElapsedTimer();
      czkScanStartedAt = 0;
    }
  }

  function syncModePanels() {
    var mode = ($("czkMode") && $("czkMode").value) || "dup";
    var dupOnly = document.querySelectorAll(".czk-dup-only");
    var bigOnly = document.querySelectorAll(".czk-big-only");
    dupOnly.forEach(function (el) {
      el.hidden = mode !== "dup";
    });
    bigOnly.forEach(function (el) {
      el.hidden = mode !== "big";
    });
  }

  function collectExtensionMacros() {
    var out = [];
    if ($("czkExtVideo") && $("czkExtVideo").checked) {
      out.push("VIDEO");
    }
    if ($("czkExtImage") && $("czkExtImage").checked) {
      out.push("IMAGE");
    }
    if ($("czkExtMusic") && $("czkExtMusic").checked) {
      out.push("MUSIC");
    }
    return out;
  }

  function setApplyButtonsEnabled(enabled) {
    var on = !!enabled && czkLastMode === "dup" && czkLastGroups.length > 0;
    if ($("btnCzkPreviewRemove")) {
      $("btnCzkPreviewRemove").disabled = !on;
    }
    if ($("btnCzkApplyRemove")) {
      $("btnCzkApplyRemove").disabled = !on;
    }
  }

  function syncQuarantineFieldVisibility() {
    var del = $("czkModeDelete") && $("czkModeDelete").checked;
    var field = document.querySelector(".czk-quarantine-field");
    if (field) {
      field.hidden = !!del;
    }
  }

  function rememberQuarantineDir() {
    var inp = $("czkQuarantineDir");
    if (!inp || !inp.value.trim()) {
      return;
    }
    try {
      localStorage.setItem(CZK_QUAR_STORAGE, inp.value.trim());
    } catch (_e) {
      void _e;
    }
  }

  async function loadDefaultQuarantineDir() {
    var inp = $("czkQuarantineDir");
    if (!inp) {
      return;
    }
    try {
      var saved = localStorage.getItem(CZK_QUAR_STORAGE);
      if (saved && saved.trim()) {
        inp.value = saved.trim();
        return;
      }
    } catch (_s) {
      void _s;
    }
    try {
      var r = await fetch("/api/settings", { credentials: "same-origin" });
      if (!r.ok) {
        return;
      }
      var j = await r.json();
      var root = j.archive_root != null ? String(j.archive_root) : "";
      var rel =
        j.duplicates_quarantine_rel != null
          ? String(j.duplicates_quarantine_rel)
          : "logs/_duplicates_quarantine";
      if (root) {
        inp.value = root.replace(/[/\\]+$/, "") + "\\" + rel.replace(/\//g, "\\");
      }
      if (j.duplicates_prefer_quarantine === false && $("czkModeDelete") && $("czkModeQuarantine")) {
        $("czkModeDelete").checked = true;
        $("czkModeQuarantine").checked = false;
        syncQuarantineFieldVisibility();
      }
    } catch (_e) {
      void _e;
    }
  }

  function renderDupApplyGroups() {
    var wrap = $("czkDupResults");
    if (!wrap) {
      return;
    }
    if (!czkLastGroups.length) {
      wrap.innerHTML = '<p class="muted small">No duplicate groups found.</p>';
      setApplyButtonsEnabled(false);
      return;
    }
    var html = "";
    czkLastGroups.forEach(function (g, gi) {
      var files = g.files || [];
      var gid = g.group_id || "group_" + gi;
      var sizeLabel = formatBytes(g.size_bytes);
      html +=
        '<div class="dup-group" data-czk-gi="' +
        gi +
        '" data-czk-gid="' +
        esc(gid) +
        '"><h4 class="dup-group__title">Group ' +
        esc(String(gi + 1)) +
        " · " +
        esc(sizeLabel) +
        "</h4>";
      files.forEach(function (f, fi) {
        var path = f.path || "";
        html +=
          '<div class="dup-group__row">' +
          '<label class="dup-keep"><input type="radio" name="czk_keep_' +
          gi +
          '" value="' +
          esc(path) +
          '"' +
          (fi === 0 ? " checked" : "") +
          " /> Keep</label>" +
          '<label class="dup-remove"><input type="checkbox" class="czk-cb-remove" data-gi="' +
          gi +
          '" data-path="' +
          esc(path) +
          '"' +
          (fi === 0 ? "" : " checked") +
          " /> Remove</label>" +
          '<span class="mono-ellipsis dup-group__path" title="' +
          esc(path) +
          '">' +
          esc(path) +
          "</span></div>";
      });
      html += "</div>";
    });
    wrap.innerHTML = html;
    wrap.querySelectorAll(".dup-group").forEach(function (grp) {
      var gi = grp.getAttribute("data-czk-gi");
      grp.querySelectorAll('input[type="radio"][name="czk_keep_' + gi + '"]').forEach(
        function (rad) {
          rad.addEventListener("change", function () {
            var keepVal = rad.value;
            grp.querySelectorAll("input.czk-cb-remove").forEach(function (cb) {
              var p = cb.getAttribute("data-path");
              cb.checked = p !== keepVal;
            });
          });
        }
      );
    });
    setApplyButtonsEnabled(true);
  }

  function renderSummaryTable(groups) {
    var tableWrap = $("czkResultsTableWrap");
    var tbody = $("czkResultsTbody");
    if (!tbody || !tableWrap) {
      return;
    }
    tbody.innerHTML = "";
    if (!groups.length) {
      tableWrap.hidden = true;
      return;
    }
    tableWrap.hidden = false;
    groups.slice(0, 200).forEach(function (g, idx) {
      var tr = document.createElement("tr");
      var files = g.files || [];
      var pathsHtml = files
        .map(function (f) {
          return "<code>" + esc(f.path || "") + "</code>";
        })
        .join("<br />");
      tr.innerHTML =
        "<td>" +
        esc(g.group_id || "group_" + idx) +
        "</td><td>" +
        esc(formatBytes(g.size_bytes)) +
        "</td><td class=\"small\">" +
        pathsHtml +
        "</td>";
      tbody.appendChild(tr);
    });
    if (groups.length > 200) {
      var tr2 = document.createElement("tr");
      tr2.innerHTML =
        '<td colspan="3" class="muted small">… ' +
        (groups.length - 200) +
        " more groups (see JSON file)</td>";
      tbody.appendChild(tr2);
    }
  }

  function renderResults(data) {
    var card = $("czkResultsCard");
    var summary = $("czkResultsSummary");
    var raw = $("czkResultsRaw");
    var jsonPath = $("czkJsonPath");
    var applySection = $("czkDupApplySection");
    if (!card || !summary) {
      return;
    }
    card.hidden = false;
    var results = (data && data.results) || {};
    var groups = results.groups || [];
    czkLastGroups = groups;
    czkLastScanId = data.scan_id || czkLastScanId;
    czkLastMode = data.mode || czkLastMode;
    var count = results.group_count != null ? results.group_count : groups.length;
    setMsg(
      summary,
      "Groups: " +
        count +
        (data.mode ? " · mode " + data.mode : "") +
        (results.parse ? " · " + results.parse : "")
    );
    if (jsonPath) {
      if (data.json_rel) {
        jsonPath.hidden = false;
        jsonPath.textContent = "Raw JSON saved under archive: " + data.json_rel;
      } else {
        jsonPath.hidden = true;
        jsonPath.textContent = "";
      }
    }
    if ($("czkApplyPreview")) {
      $("czkApplyPreview").hidden = true;
      $("czkApplyPreview").textContent = "";
    }
    setMsg($("czkApplyMsg"), "");

    var isDup = czkLastMode === "dup" && groups.length > 0;
    if (applySection) {
      applySection.hidden = !isDup;
    }
    if ($("czkResultsTableWrap")) {
      $("czkResultsTableWrap").hidden = isDup;
    }
    if (isDup) {
      renderDupApplyGroups();
    } else {
      setApplyButtonsEnabled(false);
      renderSummaryTable(groups);
    }
    if (raw) {
      if (groups.length === 0 && results.top_level_keys) {
        raw.hidden = false;
        raw.textContent = "JSON top-level keys: " + results.top_level_keys.join(", ");
      } else if (groups.length === 0) {
        raw.hidden = false;
        raw.textContent =
          "No duplicate groups in parsed output. Open the saved JSON for full details.";
      } else if (!isDup) {
        raw.hidden = false;
        raw.textContent =
          "Apply removal is available in Duplicates (dup) mode only. Switch mode and re-scan to quarantine or delete.";
      } else {
        raw.hidden = true;
        raw.textContent = "";
      }
    }
  }

  function collectCzkApplyItems() {
    var items = [];
    var wrap = $("czkDupResults");
    if (!wrap) {
      return items;
    }
    czkLastGroups.forEach(function (g, gi) {
      var grp = wrap.querySelector('[data-czk-gi="' + gi + '"]');
      if (!grp) {
        return;
      }
      var gid = grp.getAttribute("data-czk-gid") || g.group_id || "group_" + gi;
      var keepInp = grp.querySelector(
        'input[type="radio"][name="czk_keep_' + gi + '"]:checked'
      );
      var keep = keepInp ? keepInp.value : "";
      var removes = [];
      grp.querySelectorAll("input.czk-cb-remove:checked").forEach(function (cb) {
        var p = cb.getAttribute("data-path");
        if (p && p !== keep) {
          removes.push(p);
        }
      });
      if (keep && removes.length) {
        items.push({
          group_id: gid,
          keep_path: keep,
          remove_paths: removes,
        });
      }
    });
    return items;
  }

  function applyMode() {
    return $("czkModeDelete") && $("czkModeDelete").checked ? "delete" : "quarantine";
  }

  function quarantineDirPayload() {
    if (applyMode() === "delete") {
      return null;
    }
    var inp = $("czkQuarantineDir");
    return inp && inp.value.trim() ? inp.value.trim() : null;
  }

  async function previewRemoval() {
    var items = collectCzkApplyItems();
    if (!items.length) {
      setMsg($("czkApplyMsg"), "No removals selected (check Remove on duplicates to drop).");
      return;
    }
    if (!czkLastScanId) {
      setMsg($("czkApplyMsg"), "No scan id — run a scan first.");
      return;
    }
    setMsg($("czkApplyMsg"), "Running dry-run…");
    try {
      var r = await fetch("/api/czkawka/apply", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "same-origin",
        body: JSON.stringify({
          scan_id: czkLastScanId,
          dry_run: true,
          mode: applyMode(),
          quarantine_dir: quarantineDirPayload(),
          items: items,
          confirm: "",
        }),
      });
      var j = await r.json();
      if (!r.ok) {
        setMsg(
          $("czkApplyMsg"),
          "Preview failed: " +
            (j.detail != null ? String(j.detail) : r.status + " " + r.statusText)
        );
        return;
      }
      if ($("czkApplyPreview")) {
        $("czkApplyPreview").textContent = JSON.stringify(j, null, 2);
        $("czkApplyPreview").hidden = false;
      }
      setMsg(
        $("czkApplyMsg"),
        "Dry-run: would remove " +
          (j.removed_count || 0) +
          " file(s), " +
          formatBytes(j.bytes_reclaimed) +
          (j.quarantine_dir ? " → " + j.quarantine_dir : "") +
          "."
      );
    } catch (e) {
      setMsg($("czkApplyMsg"), "Preview failed: " + String(e));
    }
  }

  async function applyRemoval() {
    var items = collectCzkApplyItems();
    if (!items.length) {
      setMsg($("czkApplyMsg"), "No removals selected.");
      return;
    }
    if (!czkLastScanId) {
      setMsg($("czkApplyMsg"), "No scan id — run a scan first.");
      return;
    }
    rememberQuarantineDir();
    var pr = await fetch("/api/czkawka/apply", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      body: JSON.stringify({
        scan_id: czkLastScanId,
        dry_run: true,
        mode: applyMode(),
        quarantine_dir: quarantineDirPayload(),
        items: items,
        confirm: "",
      }),
    });
    var pj = await pr.json();
    var n = pj.removed_count || 0;
    var bytes = pj.bytes_reclaimed || 0;
    if (!pr.ok) {
      setMsg(
        $("czkApplyMsg"),
        "Dry-run failed: " +
          (pj.detail != null ? String(pj.detail) : pr.status + " " + pr.statusText)
      );
      return;
    }
    var modeLabel = applyMode() === "delete" ? "permanently delete" : "quarantine";
    var ok1 = window.confirm(
      modeLabel.charAt(0).toUpperCase() +
        modeLabel.slice(1) +
        " " +
        n +
        " duplicate file(s), reclaim about " +
        formatBytes(bytes) +
        "?"
    );
    if (!ok1) {
      setMsg($("czkApplyMsg"), "Apply cancelled.");
      return;
    }
    var typed = window.prompt(
      'Type "' + CZK_APPLY_CONFIRM + '" to confirm destructive apply:'
    );
    if ((typed || "").trim() !== CZK_APPLY_CONFIRM) {
      setMsg($("czkApplyMsg"), "Apply cancelled (confirmation text did not match).");
      return;
    }
    setMsg($("czkApplyMsg"), "Applying…");
    try {
      var r = await fetch("/api/czkawka/apply", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "same-origin",
        body: JSON.stringify({
          scan_id: czkLastScanId,
          dry_run: false,
          mode: applyMode(),
          quarantine_dir: quarantineDirPayload(),
          items: items,
          confirm: CZK_APPLY_CONFIRM,
        }),
      });
      var j = await r.json();
      if (!r.ok) {
        setMsg(
          $("czkApplyMsg"),
          "Apply failed: " +
            (j.detail != null ? String(j.detail) : r.status + " " + r.statusText)
        );
        return;
      }
      if (j.results) {
        renderResults({
          scan_id: czkLastScanId,
          mode: czkLastMode,
          results: j.results,
          json_rel: $("czkJsonPath") ? $("czkJsonPath").textContent.replace(/^Raw JSON saved under archive: /, "") : "",
        });
      }
      setMsg(
        $("czkApplyMsg"),
        "Applied: removed " +
          (j.removed_count || 0) +
          " file(s), " +
          formatBytes(j.bytes_reclaimed) +
          "."
      );
      if ($("czkApplyPreview")) {
        $("czkApplyPreview").hidden = true;
      }
    } catch (e) {
      setMsg($("czkApplyMsg"), "Apply failed: " + String(e));
    }
  }

  async function refreshToolStatus() {
    var el = $("czkToolStatus");
    if (!el) {
      return;
    }
    try {
      var r = await fetch("/api/tools/versions", { credentials: "same-origin" });
      if (!r.ok) {
        setMsg(el, "Could not verify czkawka_cli.");
        return;
      }
      var j = await r.json();
      var tools = j.tools || [];
      var row = null;
      tools.forEach(function (t) {
        if (t.tool === "czkawka") {
          row = t;
        }
      });
      if (row && row.ok) {
        setMsg(el, "czkawka_cli OK — " + (row.version || ""));
      } else if (row && row.error === "not found") {
        setMsg(
          el,
          "czkawka_cli not found. Set the full exe path under Settings → General → Czkawka CLI executable."
        );
      } else {
        setMsg(el, "czkawka problem: " + ((row && row.error) || "unknown"));
      }
    } catch (_e) {
      setMsg(el, "Could not verify czkawka_cli.");
    }
  }

  function updateGlobalScanChrome(running) {
    var banner = $("czkScanActiveBanner");
    var bannerText = $("czkScanActiveBannerText");
    var navSub = $("navCzkawkaSub");
    if (banner) {
      banner.hidden = !running;
    }
    if (bannerText && running) {
      bannerText.textContent = runningProgressText().replace(
        "Scan running",
        "Czkawka scan running"
      );
    }
    if (navSub) {
      navSub.textContent = running ? "Czkawka · scanning…" : "Czkawka CLI";
    }
  }

  function ensurePollTimerRunning() {
    if (pollTimer) {
      return;
    }
    pollTimer = window.setInterval(function () {
      void syncScanStateFromServer();
    }, 1200);
  }

  function applyStatusPayload(j) {
    var phase = (j && j.phase) || "idle";
    var scan = j && j.scan;
    var prog = $("czkScanProgress");
    if (phase === "running") {
      if (scan && scan.started_unix) {
        czkScanStartedAt = Number(scan.started_unix) || czkScanStartedAt;
      }
      if (scan && scan.scan_id) {
        czkLastScanId = scan.scan_id;
      }
      if (scan && scan.mode) {
        czkLastMode = scan.mode;
      }
      setScanBusy(true);
      setMsg(prog, runningProgressText());
      updateGlobalScanChrome(true);
      ensurePollTimerRunning();
      return;
    }
    if (pollTimer) {
      window.clearInterval(pollTimer);
      pollTimer = null;
    }
    setScanBusy(false);
    updateGlobalScanChrome(false);
    if (phase === "success" && scan) {
      setMsg(prog, "Done.");
      renderResults({
        scan_id: scan.scan_id,
        mode: scan.mode,
        results: scan.results,
        json_rel: scan.json_rel,
      });
    } else if (phase === "failed" && scan) {
      var err = scan.error || "unknown";
      if (/stopped/i.test(err)) {
        setMsg(prog, "Stopped.");
      } else {
        var tail = scan.stderr_tail ? " " + String(scan.stderr_tail).slice(-200) : "";
        setMsg(prog, "Failed: " + err + tail);
      }
    } else if (phase === "idle") {
      if (!scanBusy) {
        setMsg(prog, "");
      }
    }
  }

  async function syncScanStateFromServer() {
    try {
      var r = await fetch("/api/czkawka/status?include_results=1", {
        credentials: "same-origin",
      });
      if (!r.ok) {
        return;
      }
      applyStatusPayload(await r.json());
    } catch (_e) {
      void _e;
    }
  }

  async function pollStatus() {
    await syncScanStateFromServer();
  }

  async function startScan() {
    if (scanBusy) {
      return;
    }
    var dirs = splitPaths($("czkDirectories") && $("czkDirectories").value);
    if (!dirs.length) {
      setMsg($("czkScanProgress"), "Add at least one scan directory.");
      return;
    }
    setMsg($("czkScanProgress"), "Starting…");
    if ($("czkResultsCard")) {
      $("czkResultsCard").hidden = true;
    }
    czkLastGroups = [];
    czkLastScanId = null;
    setApplyButtonsEnabled(false);
    czkScanStartedAt = Date.now() / 1000;
    setScanBusy(true);
    setMsg($("czkScanProgress"), "Starting…");
    try {
      var body = {
        mode: ($("czkMode") && $("czkMode").value) || "dup",
        directories: dirs,
        exclude_directories: splitPaths($("czkExcludeDirs") && $("czkExcludeDirs").value),
        dup_method: ($("czkDupMethod") && $("czkDupMethod").value) || "HASH",
        hash_type: ($("czkHashType") && $("czkHashType").value) || "BLAKE3",
        minimal_file_size_kb: Number(($("czkMinKb") && $("czkMinKb").value) || 8),
        extension_macros: collectExtensionMacros(),
        number_of_big_files: Number(($("czkBigCount") && $("czkBigCount").value) || 50),
      };
      var r = await fetch("/api/czkawka/scan", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "same-origin",
        body: JSON.stringify(body),
      });
      if (!r.ok) {
        var detail = r.status + " " + r.statusText;
        try {
          var ej = await r.json();
          if (ej.detail != null) {
            detail = typeof ej.detail === "string" ? ej.detail : JSON.stringify(ej.detail);
          }
        } catch (_p) {
          void _p;
        }
        setScanBusy(false);
        setMsg($("czkScanProgress"), "Start failed: " + detail);
        return;
      }
      var sj = await r.json();
      czkLastScanId = sj.scan_id || null;
      czkLastMode = body.mode;
      if (pollTimer) {
        window.clearInterval(pollTimer);
      }
      pollTimer = window.setInterval(function () {
        void syncScanStateFromServer();
      }, 1200);
      void syncScanStateFromServer();
    } catch (e) {
      setScanBusy(false);
      setMsg($("czkScanProgress"), "Start failed: " + String(e));
    }
  }

  async function browseDirectoryInto(textareaId) {
    try {
      var r = await fetch("/api/czkawka/browse-directory", {
        method: "POST",
        credentials: "same-origin",
      });
      if (r.status === 503) {
        setMsg($("czkScanProgress"), "Folder picker unavailable on this host.");
        return;
      }
      if (!r.ok) {
        return;
      }
      var j = await r.json();
      if (!j.ok || j.cancelled || !j.path) {
        return;
      }
      var ta = $(textareaId);
      if (!ta) {
        return;
      }
      var lines = splitPaths(ta.value);
      if (lines.indexOf(j.path) < 0) {
        lines.push(j.path);
      }
      ta.value = lines.join("\n");
    } catch (_e) {
      setMsg($("czkScanProgress"), "Browse failed.");
    }
  }

  async function stopScan() {
    if (!scanBusy) {
      await syncScanStateFromServer();
    }
    if (!scanBusy) {
      setMsg($("czkScanProgress"), "No scan is running.");
      return;
    }
    var ok = window.confirm(
      "Stop the Czkawka scan? Partial results may be incomplete or missing."
    );
    if (!ok) {
      return;
    }
    var stopBtn = $("btnCzkStop");
    if (stopBtn) {
      stopBtn.disabled = true;
    }
    setMsg($("czkScanProgress"), "Stopping…");
    try {
      var r = await fetch("/api/czkawka/reset", {
        method: "POST",
        credentials: "same-origin",
      });
      var j = await r.json().catch(function () {
        return {};
      });
      if (!r.ok) {
        setMsg($("czkScanProgress"), "Stop failed: " + r.status + " " + r.statusText);
        setStopButtonVisible(true);
        return;
      }
      if (pollTimer) {
        window.clearInterval(pollTimer);
        pollTimer = null;
      }
      setScanBusy(false);
      setMsg(
        $("czkScanProgress"),
        j.stopped || j.reset ? "Stopped." : "No running scan to stop."
      );
      void syncScanStateFromServer();
    } catch (e) {
      setMsg($("czkScanProgress"), "Stop failed: " + String(e));
      setStopButtonVisible(scanBusy);
    }
  }

  function openCzkawkaView() {
    var navBtn = document.querySelector('.nav-item[data-view="czkawka"]');
    if (navBtn) {
      navBtn.click();
    }
  }

  function bind() {
    if ($("czkMode")) {
      $("czkMode").addEventListener("change", syncModePanels);
    }
    if ($("btnCzkBrowse")) {
      $("btnCzkBrowse").addEventListener("click", function () {
        void browseDirectoryInto("czkDirectories");
      });
    }
    if ($("btnCzkBrowseExclude")) {
      $("btnCzkBrowseExclude").addEventListener("click", function () {
        void browseDirectoryInto("czkExcludeDirs");
      });
    }
    if ($("btnCzkClearDirs")) {
      $("btnCzkClearDirs").addEventListener("click", function () {
        if ($("czkDirectories")) {
          $("czkDirectories").value = "";
        }
      });
    }
    if ($("btnCzkClearExclude")) {
      $("btnCzkClearExclude").addEventListener("click", function () {
        if ($("czkExcludeDirs")) {
          $("czkExcludeDirs").value = "";
        }
      });
    }
    if ($("btnCzkScan")) {
      $("btnCzkScan").addEventListener("click", function () {
        void startScan();
      });
    }
    if ($("btnCzkStop")) {
      $("btnCzkStop").addEventListener("click", function () {
        void stopScan();
      });
    }
    if ($("btnCzkBannerOpen")) {
      $("btnCzkBannerOpen").addEventListener("click", function () {
        openCzkawkaView();
      });
    }
    if ($("btnCzkBannerStop")) {
      $("btnCzkBannerStop").addEventListener("click", function () {
        void stopScan();
      });
    }
    if ($("czkModeQuarantine")) {
      $("czkModeQuarantine").addEventListener("change", syncQuarantineFieldVisibility);
    }
    if ($("czkModeDelete")) {
      $("czkModeDelete").addEventListener("change", syncQuarantineFieldVisibility);
    }
    if ($("czkQuarantineDir")) {
      $("czkQuarantineDir").addEventListener("change", rememberQuarantineDir);
    }
    if ($("btnCzkPreviewRemove")) {
      $("btnCzkPreviewRemove").addEventListener("click", function () {
        void previewRemoval();
      });
    }
    if ($("btnCzkApplyRemove")) {
      $("btnCzkApplyRemove").addEventListener("click", function () {
        void applyRemoval();
      });
    }
    syncModePanels();
    syncQuarantineFieldVisibility();
  }

  window.czkawkaOnViewEnter = function () {
    void refreshToolStatus();
    void loadDefaultQuarantineDir();
  };

  window.czkawkaSyncScanState = syncScanStateFromServer;

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () {
      bind();
      void syncScanStateFromServer();
    });
  } else {
    bind();
    void syncScanStateFromServer();
  }
})();
