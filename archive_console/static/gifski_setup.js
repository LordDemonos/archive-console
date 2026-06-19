/* global window, document, fetch */
(function () {
  "use strict";

  var skyState = null;
  var skyActivePreset = "hq_reddit";
  var presetsCache = [];
  var tierAGroups = [];
  var previewTimer = null;

  function esc(s) {
    var d = document.createElement("div");
    d.textContent = s == null ? "" : String(s);
    return d.innerHTML;
  }

  function debouncePreview() {
    if (previewTimer) {
      window.clearTimeout(previewTimer);
    }
    previewTimer = window.setTimeout(function () {
      void runPreview();
    }, 320);
  }

  function readModelFromForm() {
    if (!skyState) {
      return;
    }
    document.querySelectorAll("[data-skey]").forEach(function (el) {
      var key = el.getAttribute("data-skey");
      if (!key) {
        return;
      }
      if (el.type === "checkbox") {
        skyState[key] = el.checked;
      } else if (el.type === "number") {
        if (el.value === "") {
          return;
        }
        var n = Number(el.value);
        if (!isNaN(n)) {
          skyState[key] = n;
        }
      } else if (key === "extensions") {
        skyState[key] = el.value
          .split(",")
          .map(function (x) {
            return x.trim();
          })
          .filter(Boolean);
      } else {
        skyState[key] = el.value;
      }
    });
  }

  function syncFormFromState() {
    if (!skyState) {
      return;
    }
    document.querySelectorAll("[data-skey]").forEach(function (el) {
      var key = el.getAttribute("data-skey");
      if (!key) {
        return;
      }
      var val = skyState[key];
      if (el.type === "checkbox") {
        el.checked = !!val;
      } else if (key === "extensions" && Array.isArray(val)) {
        el.value = val.join(", ");
      } else if (el.type === "number") {
        el.value = val === undefined || val === null ? "" : String(val);
      } else {
        el.value = val == null ? "" : String(val);
      }
    });
  }

  function renderField(f) {
    var k = f.key;
    var val = skyState ? skyState[k] : undefined;
    if (f.widget === "toggle" || f.widget === "checkbox") {
      return (
        '<label class="chk ytdlp-row"><input type="checkbox" data-skey="' +
        esc(k) +
        '" ' +
        (val ? "checked" : "") +
        " /> " +
        esc(f.label) +
        (f.help
          ? ' <span class="muted small">— ' + esc(f.help) + "</span>"
          : "") +
        "</label>"
      );
    }
    if (f.widget === "number") {
      var num = val === undefined || val === null ? "" : String(val);
      return (
        '<label class="field ytdlp-row"><span>' +
        esc(f.label) +
        '</span><input type="number" step="any" data-skey="' +
        esc(k) +
        '" value="' +
        esc(num) +
        '" placeholder="' +
        esc(f.placeholder || "") +
        '" /></label>' +
        (f.help ? '<p class="muted small">' + esc(f.help) + "</p>" : "")
      );
    }
    var txt = val == null ? "" : String(val);
    if (k === "extensions" && Array.isArray(val)) {
      txt = val.join(", ");
    }
    return (
      '<label class="field ytdlp-row"><span>' +
      esc(f.label) +
      '</span><input type="text" data-skey="' +
      esc(k) +
      '" value="' +
      esc(txt) +
      '" placeholder="' +
      esc(f.placeholder || "") +
      '" /></label>' +
      (f.help ? '<p class="muted small">' + esc(f.help) + "</p>" : "")
    );
  }

  function wireControlEvents(root) {
    root.querySelectorAll("[data-skey]").forEach(function (el) {
      el.addEventListener("change", debouncePreview);
      el.addEventListener("input", debouncePreview);
    });
  }

  function renderControls() {
    var host = document.getElementById("gifskyconfControls");
    if (!host) {
      return;
    }
    var html = "";
    (tierAGroups || []).forEach(function (g) {
      html += '<div class="ytdlp-group"><h3>' + esc(g.label) + "</h3>";
      (g.fields || []).forEach(function (f) {
        html += renderField(f);
      });
      html += "</div>";
    });
    host.innerHTML = html;
    wireControlEvents(host);
  }

  function renderPresetCards() {
    var host = document.getElementById("gifskyconfPresetCards");
    if (!host) {
      return;
    }
    host.textContent = "";
    (presetsCache || []).forEach(function (p) {
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className =
        "ytdlp-preset-card" + (p.id === skyActivePreset ? " is-active" : "");
      btn.innerHTML =
        "<strong>" +
        esc(p.label) +
        '</strong><span class="muted small">' +
        esc(p.description) +
        "</span>";
      btn.addEventListener("click", function () {
        void applyPreset(p.id);
      });
      host.appendChild(btn);
    });
    var hint = document.getElementById("gifskyconfPresetHint");
    if (hint) {
      hint.textContent =
        "Large GIFs? Try Compact (480px, 20 fps) or Balanced (720px). HQ Reddit matches Mp4ToGif — biggest files. Click a preset, tweak fields, then Save.";
    }
  }

  function applyServerPreview(j) {
    var prev = document.getElementById("gifskyconfPreview");
    var mir = document.getElementById("gifskyconfJsonMirror");
    if (prev && j && j.preview != null) {
      prev.textContent = j.preview;
    }
    if (mir && j && j.serialized_preview != null) {
      mir.textContent = j.serialized_preview;
    }
  }

  async function runPreview() {
    readModelFromForm();
    if (!skyState) {
      return;
    }
    try {
      var r = await fetch("/api/gifsky/setup/preview", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ state: skyState }),
      });
      if (r.ok) {
        applyServerPreview(await r.json());
      }
    } catch (_e) {
      void _e;
    }
  }

  async function loadSetup() {
    var msgEl = document.getElementById("gifskyconfMsg");
    var r;
    try {
      r = await fetch("/api/gifsky/setup");
    } catch (_err) {
      if (msgEl) {
        msgEl.textContent =
          "Could not reach /api/gifsky/setup — is Archive Console running?";
      }
      return;
    }
    if (!r.ok) {
      if (msgEl) {
        msgEl.textContent =
          "Could not load gifsky.conf (HTTP " +
          r.status +
          "). Restart the console after upgrade, then hard-refresh (Ctrl+F5).";
      }
      return;
    }
    var j = await r.json();
    skyState = j.state;
    skyActivePreset = j.active_preset_id || "hq_reddit";
    presetsCache = j.presets || [];
    tierAGroups = j.tier_a_groups || [];
    renderPresetCards();
    renderControls();
    syncFormFromState();
    applyServerPreview(j);
    var empty = document.getElementById("gifskyconfEmptyState");
    var emptyPath = document.getElementById("gifskyconfEmptyPath");
    if (empty) {
      empty.hidden = !!j.conf_exists;
    }
    if (emptyPath && j.conf_path) {
      emptyPath.textContent = j.conf_path;
    }
    if (msgEl) {
      var note = j.conf_exists ? "" : "Using defaults until you Save. ";
      if (j.parse_warnings && j.parse_warnings.length) {
        note += j.parse_warnings.join(" ");
      }
      msgEl.textContent = note;
    }
  }

  async function applyPreset(id) {
    var msgEl = document.getElementById("gifskyconfMsg");
    var r = await fetch("/api/gifsky/setup/apply-preset", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ preset_id: id }),
    });
    if (!r.ok) {
      if (msgEl) {
        try {
          var ej = await r.json();
          msgEl.textContent =
            typeof ej.detail === "string" ? ej.detail : "Preset failed.";
        } catch (_e) {
          msgEl.textContent = "Preset failed.";
        }
      }
      return;
    }
    var j = await r.json();
    skyState = j.state;
    skyActivePreset = j.active_preset_id;
    renderPresetCards();
    renderControls();
    syncFormFromState();
    applyServerPreview(j);
    if (msgEl) {
      msgEl.textContent = "Preset applied — click Save gifsky.conf to write disk.";
    }
  }

  async function saveConf() {
    readModelFromForm();
    var msgEl = document.getElementById("gifskyconfMsg");
    var r = await fetch("/api/gifsky/setup/save", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        state: skyState,
        active_preset_id: skyActivePreset,
      }),
    });
    if (!r.ok) {
      if (msgEl) {
        try {
          var ej = await r.json();
          msgEl.textContent =
            typeof ej.detail === "string"
              ? ej.detail
              : "Save failed (" + r.status + ").";
        } catch (_e) {
          msgEl.textContent = "Save failed (" + r.status + ").";
        }
      }
      return;
    }
    var j = await r.json();
    skyActivePreset = j.active_preset_id || skyActivePreset;
    if (msgEl) {
      msgEl.textContent = "Saved gifsky.conf — new Gifsky runs use these settings.";
    }
    var empty = document.getElementById("gifskyconfEmptyState");
    if (empty) {
      empty.hidden = true;
    }
    applyServerPreview(j);
    renderPresetCards();
  }

  async function captureUser() {
    var r = await fetch("/api/gifsky/setup/capture-user", { method: "POST" });
    var msgEl = document.getElementById("gifskyconfMsg");
    if (!r.ok) {
      if (msgEl) {
        msgEl.textContent = "Capture failed — save gifsky.conf first.";
      }
      return;
    }
    var j = await r.json();
    skyState = j.state;
    skyActivePreset = "user_preferences";
    renderPresetCards();
    renderControls();
    syncFormFromState();
    applyServerPreview(j);
    if (msgEl) {
      msgEl.textContent = "Captured User preferences snapshot.";
    }
  }

  function initButtons() {
    var bs = document.getElementById("btnGifskyconfSave");
    if (bs) {
      bs.addEventListener("click", function () {
        void saveConf();
      });
    }
    var br = document.getElementById("btnGifskyconfReload");
    if (br) {
      br.addEventListener("click", function () {
        void loadSetup();
      });
    }
    var bc = document.getElementById("btnGifskyconfCapture");
    if (bc) {
      bc.addEventListener("click", function () {
        void captureUser();
      });
    }
  }

  window.gifskyconfSetupLoad = function () {
    void loadSetup();
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initButtons);
  } else {
    initButtons();
  }
})();
