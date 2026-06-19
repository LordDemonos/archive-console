/* global window, document, fetch */
(function () {
  "use strict";

  var gdlState = null;
  var gdlBaselineState = null;
  var gdlActivePreset = "balanced";
  var previewTimer = null;
  var tierAGroups = [];
  var presetsCache = [];

  function esc(s) {
    var d = document.createElement("div");
    d.textContent = s == null ? "" : String(s);
    return d.innerHTML;
  }

  function deepEqual(a, b) {
    if (a === b) {
      return true;
    }
    if (a == null || b == null) {
      return false;
    }
    if (typeof a !== typeof b) {
      return false;
    }
    if (typeof a !== "object") {
      return false;
    }
    if (Array.isArray(a) !== Array.isArray(b)) {
      return false;
    }
    if (Array.isArray(a)) {
      if (a.length !== b.length) {
        return false;
      }
      for (var i = 0; i < a.length; i++) {
        if (!deepEqual(a[i], b[i])) {
          return false;
        }
      }
      return true;
    }
    var ka = Object.keys(a);
    var kb = Object.keys(b);
    if (ka.length !== kb.length) {
      return false;
    }
    for (var j = 0; j < ka.length; j++) {
      var k = ka[j];
      if (!Object.prototype.hasOwnProperty.call(b, k)) {
        return false;
      }
      if (!deepEqual(a[k], b[k])) {
        return false;
      }
    }
    return true;
  }

  function cloneState(obj) {
    return JSON.parse(JSON.stringify(obj));
  }

  function navigateParent(obj, parts, create) {
    if (parts.length === 1) {
      return { parent: obj, lastKey: parts[0] };
    }
    var cur = obj;
    for (var i = 0; i < parts.length - 1; i++) {
      var seg = String(parts[i]);
      var next = String(parts[i + 1]);
      var nextIsNum = /^\d+$/.test(next);
      if (/^\d+$/.test(seg)) {
        var ix = parseInt(seg, 10);
        if (!Array.isArray(cur)) {
          return null;
        }
        while (create && cur.length <= ix) {
          cur.push(nextIsNum ? null : {});
        }
        if (cur[ix] == null && create) {
          cur[ix] = nextIsNum ? [] : {};
        }
        if (cur[ix] == null) {
          return null;
        }
        cur = cur[ix];
      } else {
        if (!cur[seg] || typeof cur[seg] !== "object") {
          if (!create) {
            return null;
          }
          cur[seg] = nextIsNum ? [] : {};
        }
        cur = cur[seg];
      }
    }
    return { parent: cur, lastKey: parts[parts.length - 1] };
  }

  function getPath(obj, path) {
    var parts = String(path).split(".");
    var cur = obj;
    for (var i = 0; i < parts.length; i++) {
      if (cur == null) {
        return undefined;
      }
      var seg = parts[i];
      cur = /^\d+$/.test(seg) ? cur[parseInt(seg, 10)] : cur[seg];
    }
    return cur;
  }

  function setPath(obj, path, value) {
    var parts = String(path).split(".");
    var nav = navigateParent(obj, parts, true);
    if (!nav) {
      return;
    }
    var parent = nav.parent;
    var last = String(nav.lastKey);
    if (/^\d+$/.test(last)) {
      var ix = parseInt(last, 10);
      if (!Array.isArray(parent)) {
        return;
      }
      while (parent.length <= ix) {
        parent.push("");
      }
      parent[ix] = value;
    } else {
      parent[last] = value;
    }
  }

  function deletePath(obj, path) {
    var parts = String(path).split(".");
    var nav = navigateParent(obj, parts, false);
    if (!nav) {
      return;
    }
    var parent = nav.parent;
    var last = String(nav.lastKey);
    if (/^\d+$/.test(last)) {
      var ix = parseInt(last, 10);
      if (!Array.isArray(parent) || ix >= parent.length) {
        return;
      }
      parent[ix] = "";
    } else {
      delete parent[last];
    }
  }

  function debouncePreview() {
    if (previewTimer) {
      clearTimeout(previewTimer);
    }
    previewTimer = setTimeout(runPreview, 320);
  }

  function formIntoState() {
    if (!gdlState) {
      return;
    }
    document.querySelectorAll("[data-gkey]").forEach(function (el) {
      var path = el.getAttribute("data-gkey");
      if (!path) {
        return;
      }
      if (el.type === "checkbox") {
        if (path === "extractor.reddit.videos") {
          setPath(gdlState, path, el.checked ? "dash" : false);
        } else {
          setPath(gdlState, path, el.checked);
        }
      } else if (
        path === "extractor.reddit.image-filter" &&
        el.value.trim() === ""
      ) {
        deletePath(gdlState, path);
      } else if (el.type === "number") {
        if (el.value === "") {
          deletePath(gdlState, path);
        } else {
          var n = Number(el.value);
          setPath(gdlState, path, isNaN(n) ? el.value : n);
        }
      } else if (el.tagName === "SELECT") {
        if (el.value === "") {
          deletePath(gdlState, path);
        } else {
          setPath(gdlState, path, el.value);
        }
      } else {
        setPath(gdlState, path, el.value);
      }
    });
    syncRawJsonArea();
  }

  function readModelFromForm() {
    formIntoState();
    updateDirtyPill();
  }

  /** After server state + DOM sync, re-baseline so implicit form defaults (e.g. false toggles) do not read as “unsaved”. */
  function rebaselineFromForm() {
    formIntoState();
    gdlBaselineState = cloneState(gdlState);
    updateDirtyPill();
  }

  function syncFormFromState() {
    if (!gdlState) {
      return;
    }
    document.querySelectorAll("[data-gkey]").forEach(function (el) {
      var path = el.getAttribute("data-gkey");
      if (!path) {
        return;
      }
      var val = getPath(gdlState, path);
      if (el.type === "checkbox") {
        if (path === "extractor.reddit.videos") {
          el.checked = !!(val && val !== false && val !== "false");
        } else {
          el.checked = !!val;
        }
      } else if (el.type === "number") {
        el.value =
          val === undefined || val === null ? "" : String(val);
      } else if (el.tagName === "SELECT") {
        var s = val === undefined || val === null ? "" : String(val);
        el.value = s;
      } else {
        el.value = val == null ? "" : String(val);
      }
    });
    syncRawJsonArea();
  }

  function syncRawJsonArea() {
    var ta = document.getElementById("gallerydlRawJsonTa");
    if (!ta || !gdlState) {
      return;
    }
    try {
      ta.value = JSON.stringify(gdlState, null, 2);
    } catch (_e) {
      ta.value = "";
    }
  }

  function applyServerPreview(d) {
    var pre = document.getElementById("gallerydlCliPreview");
    var raw = document.getElementById("gallerydlJsonMirror");
    if (pre && d && d.preview != null) {
      pre.textContent = d.preview;
    }
    if (raw && d && d.serialized_preview != null) {
      raw.textContent = d.serialized_preview;
    }
  }

  async function runPreview() {
    readModelFromForm();
    if (!gdlState) {
      return;
    }
    try {
      var payload = { state: gdlState };
      var r = await fetch("/api/gallery-dl/setup/preview", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!r.ok) {
        var pre = document.getElementById("gallerydlCliPreview");
        var mir = document.getElementById("gallerydlJsonMirror");
        var hint =
          r.status === 404
            ? "# POST /api/gallery-dl/setup/preview returned 404 — restart Archive Console after upgrade, or check you are on the console origin (not a cached stale tab)."
            : "# Preview request failed (HTTP " + r.status + ").";
        if (pre) {
          pre.textContent = hint;
        }
        if (mir) {
          mir.textContent = "";
        }
        return;
      }
      var j = await r.json();
      applyServerPreview(j);
    } catch (_e) {
      /* ignore */
    }
  }

  function updateDirtyPill() {
    var pill = document.getElementById("gallerydlDirtyPill");
    if (!pill || !gdlState || !gdlBaselineState) {
      return;
    }
    pill.hidden = deepEqual(gdlState, gdlBaselineState);
  }

  function renderField(f) {
    var k = f.key;
    var val = getPath(gdlState, k);
    if (f.widget === "toggle") {
      var on =
        val !== false &&
        String(val).toLowerCase() !== "false" &&
        val != null &&
        val !== "";
      return (
        '<label class="chk ytdlp-row"><input type="checkbox" data-gkey="' +
        esc(k) +
        '" ' +
        (on ? "checked" : "") +
        " /> " +
        esc(f.label) +
        "</label>"
      );
    }
    if (f.widget === "select") {
      var choices = f.choices || [];
      var cur = val === undefined || val === null ? "" : String(val);
      var opts = choices
        .map(function (c) {
          var cv = c === undefined || c === null ? "" : String(c);
          return (
            '<option value="' +
            esc(cv) +
            '"' +
            (cur === cv ? " selected" : "") +
            ">" +
            esc(cv || "(default)") +
            "</option>"
          );
        })
        .join("");
      return (
        '<label class="field ytdlp-row"><span>' +
        esc(f.label) +
        '</span><select data-gkey="' +
        esc(k) +
        '">' +
        opts +
        "</select></label>"
      );
    }
    if (f.widget === "number") {
      var num =
        val === undefined || val === null ? "" : String(val);
      return (
        '<label class="field ytdlp-row"><span>' +
        esc(f.label) +
        '</span><input type="number" step="any" data-gkey="' +
        esc(k) +
        '" value="' +
        esc(num) +
        '" placeholder="' +
        esc(f.placeholder || "") +
        '" /></label>'
      );
    }
    return (
      '<label class="field ytdlp-row"><span>' +
      esc(f.label) +
      '</span><input type="text" data-gkey="' +
      esc(k) +
      '" value="' +
      esc(val == null ? "" : String(val)) +
      '" placeholder="' +
      esc(f.placeholder || "") +
      '" /></label>'
    );
  }

  function wireControlEvents(root) {
    root.querySelectorAll("[data-gkey]").forEach(function (el) {
      el.addEventListener("change", function () {
        debouncePreview();
      });
      el.addEventListener("input", function () {
        debouncePreview();
      });
    });
  }

  function renderGroupBody(g) {
    var html = "";
    if (g.doc) {
      html += '<p class="muted small">' + esc(g.doc);
      if (g.doc_url) {
        html +=
          ' <a href="' +
          esc(g.doc_url) +
          '" target="_blank" rel="noopener">Docs ↗</a>';
      }
      html += "</p>";
    } else if (g.doc_url) {
      html +=
        '<p class="muted small"><a href="' +
        esc(g.doc_url) +
        '" target="_blank" rel="noopener">Docs ↗</a></p>';
    }
    (g.fields || []).forEach(function (f) {
      html += '<div class="ytdlp-field">';
      html += renderField(f);
      if (f.help || f.doc_url) {
        html +=
          '<p class="muted small ytdlp-help">' +
          esc(f.help || "") +
          (f.doc_url
            ? ' <a href="' +
              esc(f.doc_url) +
              '" target="_blank" rel="noopener">Docs ↗</a>'
            : "") +
          "</p>";
      }
      html += "</div>";
    });
    return html;
  }

  function renderControls() {
    var host = document.getElementById("gallerydlControls");
    if (!host) {
      return;
    }
    var html = "";
    (tierAGroups || []).forEach(function (g) {
      var body = renderGroupBody(g);
      if (g.collapsible) {
        html +=
          '<details class="ytdlp-details-advanced"' +
          (g.collapsed === false ? " open" : "") +
          ">";
        html +=
          '<summary class="ytdlp-details-advanced__summary">' +
          esc(g.label) +
          "</summary>";
        html += '<div class="ytdlp-group ytdlp-group--nested">' + body + "</div>";
        html += "</details>";
      } else {
        html += '<div class="ytdlp-group"><h3>' + esc(g.label) + "</h3>";
        html += body;
        html += "</div>";
      }
    });
    host.innerHTML = html;
    wireControlEvents(host);
  }

  function renderPresetCards(presets) {
    var host = document.getElementById("gallerydlPresetCards");
    if (!host) {
      return;
    }
    host.innerHTML = (presets || [])
      .map(function (p) {
        var active = p.id === gdlActivePreset ? " is-active" : "";
        return (
          '<button type="button" class="ytdlp-preset-card' +
          active +
          '" data-gpreset="' +
          esc(p.id) +
          '"><strong>' +
          esc(p.label) +
          "</strong><br/><span class=\"muted small\">" +
          esc(p.description || "") +
          "</span></button>"
        );
      })
      .join("");
    host.querySelectorAll("[data-gpreset]").forEach(function (btn) {
      btn.addEventListener("click", async function () {
        var pid = btn.getAttribute("data-gpreset");
        var msgEl = document.getElementById("gallerydlMsg");
        var r = await fetch("/api/gallery-dl/setup/apply-preset", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ preset_id: pid }),
        });
        if (!r.ok) {
          try {
            var ej = await r.json();
            if (msgEl) {
              msgEl.textContent =
                typeof ej.detail === "string"
                  ? ej.detail
                  : JSON.stringify(ej.detail);
            }
          } catch (_e) {
            if (msgEl) {
              msgEl.textContent = await r.text();
            }
          }
          return;
        }
        var j = await r.json();
        gdlState = j.state;
        gdlActivePreset = j.active_preset_id || pid;
        if (msgEl) {
          msgEl.textContent = "Applied preset.";
        }
        renderPresetCards(presetsCache);
        renderControls();
        syncFormFromState();
        rebaselineFromForm();
        applyServerPreview(j);
        runPreview();
      });
    });
  }

  async function loadSetup() {
    var msgEl = document.getElementById("gallerydlMsg");
    if (msgEl) {
      msgEl.textContent = "Loading from disk…";
    }
    var r;
    try {
      r = await fetch("/api/gallery-dl/setup");
    } catch (_err) {
      if (msgEl) {
        msgEl.textContent =
          "Reload failed (network error). Check the Archive Console server.";
      }
      return;
    }
    if (!r.ok) {
      var errText = "Reload failed (" + r.status + ").";
      try {
        var errJson = await r.json();
        if (errJson.detail) {
          errText =
            typeof errJson.detail === "string"
              ? errJson.detail
              : JSON.stringify(errJson.detail);
        }
      } catch (_e0) {
        try {
          var t = await r.text();
          if (t) {
            errText = t;
          }
        } catch (_e1) {
          /* ignore */
        }
      }
      gdlState = null;
      gdlBaselineState = null;
      tierAGroups = [];
      presetsCache = [];
      var errBox = document.getElementById("gallerydlLoadError");
      var errDetail = document.getElementById("gallerydlLoadErrorDetail");
      if (errBox) {
        errBox.hidden = false;
        errBox.setAttribute("aria-hidden", "false");
      }
      if (errDetail) {
        errDetail.textContent = errText;
      }
      var pc = document.getElementById("gallerydlPresetCards");
      if (pc) {
        pc.innerHTML = "";
      }
      var ch = document.getElementById("gallerydlControls");
      if (ch) {
        ch.innerHTML =
          '<p class="muted small">Could not load <code>/api/gallery-dl/setup</code>. Fix the error above or restart the server after upgrading Archive Console.</p>';
      }
      var pre = document.getElementById("gallerydlCliPreview");
      var mir = document.getElementById("gallerydlJsonMirror");
      var rj = document.getElementById("gallerydlRawJsonTa");
      if (pre) {
        pre.textContent = "";
      }
      if (mir) {
        mir.textContent = "";
      }
      if (rj) {
        rj.value = "";
      }
      var pill = document.getElementById("gallerydlDirtyPill");
      if (pill) {
        pill.hidden = true;
      }
      var emptySt = document.getElementById("gallerydlEmptyState");
      if (emptySt) {
        emptySt.hidden = true;
      }
      if (msgEl) {
        msgEl.textContent = errText;
      }
      return;
    }
    var d = await r.json();
    var errOk = document.getElementById("gallerydlLoadError");
    if (errOk) {
      errOk.hidden = true;
      errOk.setAttribute("aria-hidden", "true");
    }
    gdlState = d.state;
    gdlActivePreset = d.active_preset_id || "balanced";
    tierAGroups = d.tier_a_groups || [];
    presetsCache = d.presets || [];
    var hint = document.getElementById("gallerydlPresetHint");
    var barNote = document.getElementById("gallerydlPresetBarNote");
    if (barNote && d.preset_bar_note) {
      barNote.textContent = d.preset_bar_note;
    }
    if (hint) {
      hint.textContent =
        (d.archive_root ? "Archive root: " + d.archive_root + " · " : "") +
        (d.conf_path ? "Config file: " + d.conf_path + " · " : "") +
        "User snapshot: " +
        (d.user_snapshot_present ? "yes" : "no");
    }
    var emptyEl = document.getElementById("gallerydlEmptyState");
    var emptyPath = document.getElementById("gallerydlEmptyPath");
    if (emptyEl) {
      emptyEl.hidden = !!d.conf_exists;
    }
    if (emptyPath && d.conf_path) {
      emptyPath.textContent = d.conf_path;
    }
    var mEl = document.getElementById("gallerydlMtime");
    if (mEl) {
      if (d.mtime != null) {
        mEl.textContent =
          "mtime: " + new Date(d.mtime * 1000).toLocaleString();
      } else {
        mEl.textContent = "new / missing on disk";
      }
    }
    if (document.getElementById("gallerydlRelLabel")) {
      document.getElementById("gallerydlRelLabel").textContent =
        "gallery-dl.conf";
    }
    var wEl = document.getElementById("gallerydlParseWarnings");
    if (wEl) {
      if (d.parse_warnings && d.parse_warnings.length) {
        wEl.hidden = false;
        wEl.className = "callout warn";
        wEl.innerHTML =
          '<p class="small"><strong>Load notes</strong></p><ul class="small">' +
          d.parse_warnings
            .map(function (x) {
              return "<li>" + esc(x) + "</li>";
            })
            .join("") +
          "</ul>";
      } else {
        wEl.hidden = true;
        wEl.innerHTML = "";
      }
    }
    renderPresetCards(presetsCache);
    renderControls();
    syncFormFromState();
    rebaselineFromForm();
    applyServerPreview(d);
    runPreview();
    if (msgEl) {
      msgEl.textContent = "Loaded from disk.";
      window.setTimeout(function () {
        if (msgEl.textContent === "Loaded from disk.") {
          msgEl.textContent = "";
        }
      }, 3200);
    }
  }

  async function saveGallerydl() {
    readModelFromForm();
    var msgEl = document.getElementById("gallerydlMsg");
    if (msgEl) {
      msgEl.textContent = "";
    }
    var smoke = document.getElementById("gallerydlConfSmoke");
    var r = await fetch("/api/gallery-dl/setup/save", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        state: gdlState,
        active_preset_id: gdlActivePreset,
        conf_smoke: smoke ? smoke.checked : true,
      }),
    });
    if (r.status === 409) {
      try {
        var e409 = await r.json();
        if (msgEl) {
          msgEl.textContent =
            typeof e409.detail === "string"
              ? e409.detail
              : JSON.stringify(e409.detail);
        }
      } catch (_e2) {
        if (msgEl) {
          msgEl.textContent = await r.text();
        }
      }
      return;
    }
    if (!r.ok) {
      var txt = await r.text();
      try {
        var eja = JSON.parse(txt);
        if (msgEl) {
          msgEl.textContent =
            typeof eja.detail === "string"
              ? eja.detail
              : JSON.stringify(eja.detail);
        }
      } catch (_e3) {
        if (msgEl) {
          msgEl.textContent = "Save failed: " + r.status + " " + txt;
        }
      }
      return;
    }
    var j = await r.json();
    var msg = "Saved.";
    if (j.warnings && j.warnings.length) {
      msg += " Hints: " + j.warnings.join(" ");
    }
    if (msgEl) {
      msgEl.textContent = msg;
    }
    var mEl = document.getElementById("gallerydlMtime");
    if (mEl && j.mtime != null) {
      mEl.textContent =
        "mtime: " + new Date(j.mtime * 1000).toLocaleString();
    }
    var emptyEl = document.getElementById("gallerydlEmptyState");
    if (emptyEl) {
      emptyEl.hidden = true;
    }
    gdlBaselineState = cloneState(gdlState);
    updateDirtyPill();
  }

  async function captureUser() {
    var msgEl = document.getElementById("gallerydlMsg");
    if (msgEl) {
      msgEl.textContent = "Reading gallery-dl.conf for snapshot…";
    }
    var r;
    try {
      r = await fetch("/api/gallery-dl/setup/capture-user", {
        method: "POST",
      });
    } catch (_err) {
      if (msgEl) {
        msgEl.textContent =
          "Capture failed (network error). Check the Archive Console server.";
      }
      return;
    }
    if (!r.ok) {
      try {
        var ej = await r.json();
        if (msgEl) {
          msgEl.textContent =
            typeof ej.detail === "string"
              ? ej.detail
              : JSON.stringify(ej.detail);
        }
      } catch (_e) {
        if (msgEl) {
          msgEl.textContent = await r.text();
        }
      }
      return;
    }
    var j = await r.json();
    gdlState = j.state;
    gdlActivePreset = j.active_preset_id || "user_preferences";
    if (msgEl) {
      msgEl.textContent =
        "Snapshot saved. Choose “User preferences” preset to re-apply this capture.";
    }
    renderPresetCards(presetsCache);
    renderControls();
    syncFormFromState();
    rebaselineFromForm();
    applyServerPreview(j);
    runPreview();
  }

  function applyRawJson() {
    var ta = document.getElementById("gallerydlRawJsonTa");
    var msgEl = document.getElementById("gallerydlMsg");
    if (!ta) {
      return;
    }
    try {
      var parsed = JSON.parse(ta.value);
      if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
        throw new Error("Root must be a JSON object.");
      }
      gdlState = parsed;
      renderControls();
      syncFormFromState();
      updateDirtyPill();
      debouncePreview();
      if (msgEl) {
        msgEl.textContent = "Applied raw JSON into the editor.";
      }
    } catch (e) {
      if (msgEl) {
        msgEl.textContent =
          "Invalid JSON: " + (e && e.message ? e.message : String(e));
      }
    }
  }

  async function reloadFromDisk() {
    readModelFromForm();
    if (
      gdlState &&
      gdlBaselineState &&
      !deepEqual(gdlState, gdlBaselineState)
    ) {
      if (
        !window.confirm("Discard unsaved edits in gallery-dl.conf?")
      ) {
        return;
      }
    }
    await loadSetup();
  }

  function initGallerydlButtons() {
    var bs = document.getElementById("btnGallerydlSave");
    if (bs) {
      bs.addEventListener("click", function () {
        void saveGallerydl();
      });
    }
    var br = document.getElementById("btnGallerydlReload");
    if (br) {
      br.addEventListener("click", function () {
        void reloadFromDisk();
      });
    }
    var bc = document.getElementById("btnGallerydlCapture");
    if (bc) {
      bc.addEventListener("click", function () {
        void captureUser();
      });
    }
    var ba = document.getElementById("btnGallerydlApplyRaw");
    if (ba) {
      ba.addEventListener("click", function () {
        applyRawJson();
      });
    }
  }

  window.gallerydlSetupLoad = function () {
    loadSetup();
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initGallerydlButtons);
  } else {
    initGallerydlButtons();
  }
})();
