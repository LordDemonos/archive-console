/* global window, document, fetch */
(function () {
  "use strict";

  var ytdlpModel = null;
  var ytdlpActivePreset = "balanced";
  var previewTimer = null;
  var schemaGroups = [];
  var formatPresets = [];
  var ytdlpPresetsCache = [];

  function esc(s) {
    var d = document.createElement("div");
    d.textContent = s == null ? "" : String(s);
    return d.innerHTML;
  }

  function debouncePreview() {
    if (previewTimer) {
      clearTimeout(previewTimer);
    }
    previewTimer = setTimeout(runPreview, 320);
  }

  function readModelFromForm() {
    if (!ytdlpModel) {
      return;
    }
    document.querySelectorAll("[data-ykey]").forEach(function (el) {
      var k = el.getAttribute("data-ykey");
      if (!k || k === "format_preset") {
        return;
      }
      if (el.type === "checkbox") {
        ytdlpModel[k] = el.checked;
      } else if (el.type === "range" || el.type === "number") {
        var v = el.value === "" ? null : Number(el.value);
        ytdlpModel[k] = v;
      } else {
        ytdlpModel[k] = el.value === "" ? null : el.value;
      }
    });
  }

  function syncFormatPresetRadios() {
    var cur =
      ytdlpModel && ytdlpModel.format ? String(ytdlpModel.format) : "";
    var matched = false;
    (formatPresets || []).forEach(function (fp) {
      var r = document.querySelector(
        'input[name="ytdlp_fmt_preset"][value="' + fp.id + '"]'
      );
      if (r) {
        r.checked = fp.value === cur;
        if (r.checked) {
          matched = true;
        }
      }
    });
    var custom = document.getElementById("ytdlpFormatCustom");
    if (custom) {
      custom.checked = !matched && cur !== "";
    }
  }

  function applyServerPreview(d) {
    var pre = document.getElementById("ytdlpCliPreview");
    var raw = document.getElementById("ytdlpRawMirror");
    var tail = document.getElementById("ytdlpPreservedTail");
    if (pre && d && d.preview != null) {
      pre.textContent = d.preview;
    }
    if (raw && d && d.serialized_preview != null) {
      raw.textContent = d.serialized_preview;
    }
    if (tail && d && d.preserved_tail_preview != null) {
      tail.textContent = d.preserved_tail_preview;
    }
  }

  async function runPreview() {
    readModelFromForm();
    if (!ytdlpModel) {
      return;
    }
    try {
      var r = await fetch("/api/ytdlp/setup/preview", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ model: ytdlpModel }),
      });
      if (!r.ok) {
        return;
      }
      var j = await r.json();
      applyServerPreview(j);
    } catch (e) {
      /* ignore */
    }
  }

  function renderFormatPresets() {
    var host = document.getElementById("ytdlpFormatPresetsHost");
    if (!host || !formatPresets.length) {
      return;
    }
    var h = '<div class="ytdlp-fmt-presets"><span class="muted small">Quick format</span> ';
    formatPresets.forEach(function (fp) {
      h +=
        '<label class="chk small"><input type="radio" name="ytdlp_fmt_preset" value="' +
        esc(fp.id) +
        '" /> ' +
        esc(fp.label) +
        "</label> ";
    });
    h +=
      '<label class="chk small"><input type="radio" name="ytdlp_fmt_preset" id="ytdlpFormatCustom" value="__custom__" /> Custom</label></div>';
    host.innerHTML = h;
    host.querySelectorAll('input[name="ytdlp_fmt_preset"]').forEach(function (inp) {
      inp.addEventListener("change", function () {
        var id = inp.value;
        if (id === "__custom__") {
          debouncePreview();
          return;
        }
        var fp = formatPresets.find(function (x) {
          return x.id === id;
        });
        if (fp && ytdlpModel) {
          ytdlpModel.format = fp.value;
          var ta = document.querySelector('[data-ykey="format"]');
          if (ta) {
            ta.value = fp.value;
          }
        }
        debouncePreview();
      });
    });
  }

  function renderField(f) {
    var k = f.key;
    var val =
      ytdlpModel && ytdlpModel[k] !== undefined && ytdlpModel[k] !== null
        ? ytdlpModel[k]
        : f.widget === "toggle"
          ? false
          : "";
    if (f.widget === "toggle") {
      var on = !!val;
      return (
        '<label class="chk ytdlp-row"><input type="checkbox" data-ykey="' +
        esc(k) +
        '" ' +
        (on ? "checked" : "") +
        " /> " +
        esc(f.label) +
        "</label>"
      );
    }
    if (f.widget === "range") {
      var num =
        typeof val === "number"
          ? val
          : f.min !== undefined
            ? f.min
            : 0;
      return (
        '<label class="field ytdlp-row"><span>' +
        esc(f.label) +
        '</span><input type="range" data-ykey="' +
        esc(k) +
        '" min="' +
        esc(f.min) +
        '" max="' +
        esc(f.max) +
        '" step="' +
        esc(f.step) +
        '" value="' +
        esc(num) +
        '" /><input type="number" class="ytdlp-range-num" data-ykey-num="' +
        esc(k) +
        '" value="' +
        esc(num) +
        '" step="' +
        esc(f.step) +
        '" /></label>'
      );
    }
    if (f.widget === "select") {
      var opts = (f.choices || [])
        .map(function (c) {
          return (
            '<option value="' +
            esc(c) +
            '"' +
            (String(val) === String(c) ? " selected" : "") +
            ">" +
            esc(c || "(none)") +
            "</option>"
          );
        })
        .join("");
      return (
        '<label class="field ytdlp-row"><span>' +
        esc(f.label) +
        '</span><select data-ykey="' +
        esc(k) +
        '">' +
        opts +
        "</select></label>"
      );
    }
    if (f.widget === "textarea") {
      return (
        '<label class="field ytdlp-row"><span>' +
        esc(f.label) +
        '</span><textarea data-ykey="' +
        esc(k) +
        '" rows="' +
        (f.rows || 3) +
        '">' +
        esc(val) +
        "</textarea></label>"
      );
    }
    return (
      '<label class="field ytdlp-row"><span>' +
      esc(f.label) +
      '</span><input type="text" data-ykey="' +
      esc(k) +
      '" value="' +
      esc(val) +
      '" placeholder="' +
      esc(f.placeholder || "") +
      '" /></label>'
    );
  }

  function wireControlEvents(root) {
    root.querySelectorAll("[data-ykey]").forEach(function (el) {
      el.addEventListener("change", function () {
        debouncePreview();
      });
      el.addEventListener("input", function () {
        debouncePreview();
      });
    });
    root.querySelectorAll("[data-ykey-num]").forEach(function (el) {
      var k = el.getAttribute("data-ykey-num");
      el.addEventListener("input", function () {
        var rng = root.querySelector('[data-ykey="' + k + '"]');
        if (rng) {
          rng.value = el.value;
        }
        debouncePreview();
      });
    });
    root.querySelectorAll('input[type="range"][data-ykey]').forEach(function (rng) {
      rng.addEventListener("input", function () {
        var k = rng.getAttribute("data-ykey");
        var n = root.querySelector('[data-ykey-num="' + k + '"]');
        if (n) {
          n.value = rng.value;
        }
      });
    });
  }

  function renderControls() {
    var host = document.getElementById("ytdlpControls");
    if (!host) {
      return;
    }
    var html = '<div id="ytdlpFormatPresetsHost"></div>';
    schemaGroups.forEach(function (g) {
      html += '<div class="ytdlp-group"><h3>' + esc(g.label) + "</h3>";
      if (g.doc) {
        html += '<p class="muted small">' + esc(g.doc) + "</p>";
      }
      (g.fields || []).forEach(function (f) {
        if (f.widget === "format_preset") {
          return;
        }
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
      html += "</div>";
    });
    host.innerHTML = html;
    renderFormatPresets();
    wireControlEvents(host);
    syncFormatPresetRadios();
  }

  function renderExtraKv() {
    var host = document.getElementById("ytdlpExtraKv");
    if (!host || !ytdlpModel) {
      return;
    }
    var ek = ytdlpModel.extra_kv || {};
    var rows = Object.keys(ek)
      .map(function (k) {
        return (
          '<div class="ytdlp-extra-row">' +
          '<input type="text" class="ytdlp-ex-k" value="' +
          esc(k) +
          '" placeholder="option-name" /> ' +
          '<input type="text" class="ytdlp-ex-v" value="' +
          esc(ek[k]) +
          '" placeholder="value" /> ' +
          '<button type="button" class="btn ghost small ytdlp-ex-del">×</button></div>'
        );
      })
      .join("");
    host.innerHTML = rows || "<p class=\"muted small\">No extra options.</p>";
    host.querySelectorAll(".ytdlp-ex-del").forEach(function (btn) {
      btn.addEventListener("click", function () {
        btn.closest(".ytdlp-extra-row").remove();
        flushExtraKv();
        debouncePreview();
      });
    });
    host.querySelectorAll(".ytdlp-ex-k, .ytdlp-ex-v").forEach(function (inp) {
      inp.addEventListener("input", function () {
        flushExtraKv();
        debouncePreview();
      });
    });
  }

  function flushExtraKv() {
    if (!ytdlpModel) {
      return;
    }
    var o = {};
    document.querySelectorAll(".ytdlp-extra-row").forEach(function (row) {
      var k = row.querySelector(".ytdlp-ex-k");
      var v = row.querySelector(".ytdlp-ex-v");
      if (k && k.value.trim()) {
        o[k.value.trim()] = v ? v.value : "";
      }
    });
    ytdlpModel.extra_kv = o;
  }

  function renderPresetCards(presets) {
    var host = document.getElementById("ytdlpPresetCards");
    if (!host) {
      return;
    }
    host.innerHTML = (presets || [])
      .map(function (p) {
        var active = p.id === ytdlpActivePreset ? " is-active" :"";
        return (
          '<button type="button" class="ytdlp-preset-card' +
          active +
          '" data-preset="' +
          esc(p.id) +
          '"><strong>' +
          esc(p.label) +
          "</strong><br/><span class=\"muted small\">" +
          esc(p.description || "") +
          "</span></button>"
        );
      })
      .join("");
    host.querySelectorAll("[data-preset]").forEach(function (btn) {
      btn.addEventListener("click", async function () {
        var pid = btn.getAttribute("data-preset");
        var r = await fetch("/api/ytdlp/setup/apply-preset", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ preset_id: pid }),
        });
        if (!r.ok) {
          document.getElementById("ytdlpMsg").textContent = await r.text();
          return;
        }
        var j = await r.json();
        ytdlpModel = j.model;
        ytdlpActivePreset = j.active_preset_id || pid;
        document.getElementById("ytdlpMsg").textContent = "Applied preset.";
        renderPresetCards(ytdlpPresetsCache);
        renderControls();
        renderExtraKv();
        applyServerPreview(j);
        runPreview();
      });
    });
  }

  async function loadSetup() {
    var msgEl = document.getElementById("ytdlpMsg");
    if (msgEl) {
      msgEl.textContent = "Loading from disk…";
    }
    var r;
    try {
      r = await fetch("/api/ytdlp/setup");
    } catch (err) {
      if (msgEl) {
        msgEl.textContent =
          "Reload failed (network error). Check your connection and the Archive Console server.";
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
      } catch (e0) {
        try {
          var t = await r.text();
          if (t) {
            errText = t;
          }
        } catch (e1) {
          /* ignore */
        }
      }
      if (msgEl) {
        msgEl.textContent = errText;
      }
      return;
    }
    var d = await r.json();
    ytdlpModel = d.model;
    ytdlpActivePreset = d.active_preset_id || "balanced";
    schemaGroups = d.tier_a_groups || [];
    formatPresets = d.format_presets || [];
    ytdlpPresetsCache = d.presets || [];
    var hint = document.getElementById("ytdlpPresetHint");
    if (hint) {
      hint.textContent =
        (d.conf_path ? "Path: " + d.conf_path + " · " : "") +
        "Last save banner preset: " +
        (d.preset_from_last_save || "—") +
        " · User snapshot: " +
        (d.user_snapshot_present ? "yes" : "no");
    }
    var emptyEl = document.getElementById("ytdlpEmptyState");
    var emptyPath = document.getElementById("ytdlpEmptyPath");
    if (emptyEl) {
      emptyEl.hidden = !!d.conf_exists;
    }
    if (emptyPath && d.conf_path) {
      emptyPath.textContent = d.conf_path;
    }
    var wEl = document.getElementById("ytdlpParseWarnings");
    if (wEl) {
      if (d.parse_warnings && d.parse_warnings.length) {
        wEl.hidden = false;
        wEl.className = "callout warn";
        wEl.innerHTML =
          "<p class=\"small\"><strong>Load notes</strong></p><ul class=\"small\">" +
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
    renderPresetCards(ytdlpPresetsCache);
    renderControls();
    renderExtraKv();
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

  async function saveYtdlp() {
    readModelFromForm();
    flushExtraKv();
    document.getElementById("ytdlpMsg").textContent = "";
    var note = document.getElementById("ytdlpHumanNote");
    var smoke = document.getElementById("ytdlpConfSmoke");
    var r = await fetch("/api/ytdlp/setup/save", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        model: ytdlpModel,
        active_preset_id: ytdlpActivePreset,
        human_note: note ? note.value : "",
        conf_smoke: smoke ? smoke.checked : true,
      }),
    });
    if (!r.ok) {
      var txt = await r.text();
      try {
        var eja = JSON.parse(txt);
        document.getElementById("ytdlpMsg").textContent =
          typeof eja.detail === "string" ? eja.detail : JSON.stringify(eja.detail);
      } catch (e2) {
        document.getElementById("ytdlpMsg").textContent =
          "Save failed: " + r.status + " " + txt;
      }
      return;
    }
    var j = await r.json();
    var msg = "Saved.";
    if (j.warnings && j.warnings.length) {
      msg += " Hints: " + j.warnings.join(" ");
    }
    document.getElementById("ytdlpMsg").textContent = msg;
    loadSetup();
  }

  async function captureUser() {
    var msgEl = document.getElementById("ytdlpMsg");
    if (msgEl) {
      msgEl.textContent = "Reading yt-dlp.conf for snapshot…";
    }
    var r;
    try {
      r = await fetch("/api/ytdlp/setup/capture-user", { method: "POST" });
    } catch (err) {
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
      } catch (e) {
        if (msgEl) {
          msgEl.textContent = await r.text();
        }
      }
      return;
    }
    var j = await r.json();
    ytdlpModel = j.model;
    ytdlpActivePreset = j.active_preset_id || "user_preferences";
    if (msgEl) {
      msgEl.textContent =
        "Saved disk contents as the User preferences preset. Apply that preset from the cards above anytime.";
    }
    renderPresetCards(ytdlpPresetsCache);
    renderControls();
    renderExtraKv();
    applyServerPreview(j);
    runPreview();
  }

  function addExtraRow() {
    var host = document.getElementById("ytdlpExtraKv");
    if (!host) {
      return;
    }
    var p = host.querySelector(".muted.small");
    if (p && p.parentNode) {
      p.parentNode.removeChild(p);
    }
    var row = document.createElement("div");
    row.className = "ytdlp-extra-row";
    row.innerHTML =
      '<input type="text" class="ytdlp-ex-k" placeholder="option-name" /> ' +
      '<input type="text" class="ytdlp-ex-v" placeholder="value" /> ' +
      '<button type="button" class="btn ghost small ytdlp-ex-del">×</button>';
    host.appendChild(row);
    row.querySelector(".ytdlp-ex-del").addEventListener("click", function () {
      row.remove();
      flushExtraKv();
      debouncePreview();
    });
    row.querySelectorAll(".ytdlp-ex-k, .ytdlp-ex-v").forEach(function (inp) {
      inp.addEventListener("input", function () {
        flushExtraKv();
        debouncePreview();
      });
    });
  }

  function initYtdlpButtons() {
    var bs = document.getElementById("btnYtdlpSave");
    if (bs) {
      bs.addEventListener("click", saveYtdlp);
    }
    var br = document.getElementById("btnYtdlpReload");
    if (br) {
      br.addEventListener("click", loadSetup);
    }
    var bc = document.getElementById("btnYtdlpCapture");
    if (bc) {
      bc.addEventListener("click", captureUser);
    }
    var ba = document.getElementById("btnYtdlpAddExtra");
    if (ba) {
      ba.addEventListener("click", addExtraRow);
    }
  }

  window.ytdlpSetupLoad = function () {
    loadSetup();
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initYtdlpButtons);
  } else {
    initYtdlpButtons();
  }
})();
