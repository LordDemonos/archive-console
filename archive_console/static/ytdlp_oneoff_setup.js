/* global window, document, fetch */
(function () {
  "use strict";

  var mountState = {};

  function esc(s) {
    var d = document.createElement("div");
    d.textContent = s == null ? "" : String(s);
    return d.innerHTML;
  }

  function q(root, sel) {
    return root.querySelector(sel);
  }

  function readModelFromMount(root, mountId) {
    var st = mountState[mountId] || { model: {} };
    var fmt = q(root, "#" + mountId + "-format");
    var merge = q(root, "#" + mountId + "-merge");
    var noplay = q(root, "#" + mountId + "-noplaylist");
    st.model = {
      format: fmt && fmt.value.trim() ? fmt.value.trim() : null,
      merge_output_format:
        merge && merge.value.trim() ? merge.value.trim() : "mkv",
      noplaylist: !!(noplay && noplay.checked),
      preserved_tail: st.preserved_tail || "",
    };
    mountState[mountId] = st;
    return st.model;
  }

  function applyPreview(root, mountId, preview) {
    var pre = q(root, "#" + mountId + "-preview");
    if (pre && preview != null) {
      pre.textContent = preview;
    }
  }

  async function runPreview(root, mountId) {
    applyPreview(
      root,
      mountId,
      buildLocalPreview(readModelFromMount(root, mountId))
    );
  }

  function buildLocalPreview(model) {
    var chunks = [
      "yt-dlp",
      "--config-locations",
      "yt-dlp.conf",
      "yt-dlp-oneoff.conf",
    ];
    if (model.format) {
      chunks.push("--format", model.format);
    }
    if (model.merge_output_format) {
      chunks.push("--merge-output-format", model.merge_output_format);
    }
    if (model.noplaylist) {
      chunks.push("--no-playlist");
    }
    return chunks.join(" ");
  }

  function renderPresetCards(root, mountId, presets, activeId) {
    var host = q(root, "#" + mountId + "-cards");
    if (!host) {
      return;
    }
    host.innerHTML = (presets || [])
      .map(function (p) {
        var active = p.id === activeId ? " is-active" : "";
        return (
          '<button type="button" class="ytdlp-preset-card' +
          active +
          '" data-preset="' +
          esc(p.id) +
          '"><strong>' +
          esc(p.label) +
          '</strong><span class="muted small">' +
          esc(p.description || "") +
          "</span></button>"
        );
      })
      .join("");
    host.querySelectorAll("[data-preset]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        void applyPreset(mountId, btn.getAttribute("data-preset"));
      });
    });
  }

  function renderFormatQuick(root, mountId, formatPresets, currentFormat) {
    var host = q(root, "#" + mountId + "-fmt-quick");
    if (!host || !formatPresets.length) {
      return;
    }
    var cur = currentFormat || "";
    var h =
      '<span class="muted small">Quick format</span> ';
    formatPresets.forEach(function (fp) {
      var checked = fp.value === cur ? " checked" : "";
      h +=
        '<label class="chk small"><input type="radio" name="' +
        mountId +
        '_fmt" value="' +
        esc(fp.id) +
        '"' +
        checked +
        " /> " +
        esc(fp.label) +
        "</label> ";
    });
    host.innerHTML = h;
    host.querySelectorAll('input[type="radio"]').forEach(function (inp) {
      inp.addEventListener("change", function () {
        var fp = formatPresets.find(function (x) {
          return x.id === inp.value;
        });
        if (!fp) {
          return;
        }
        var fmtEl = q(root, "#" + mountId + "-format");
        if (fmtEl) {
          fmtEl.value = fp.value;
        }
        void saveMount(mountId, (mountState[mountId] || {}).active_preset_id);
      });
    });
  }

  async function applyPreset(mountId, presetId) {
    var root = document.getElementById(mountId);
    if (!root) {
      return;
    }
    setMsg(root, mountId, "Applying preset…");
    try {
      var r = await fetch("/api/ytdlp-oneoff/setup/apply-preset", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ preset_id: presetId }),
      });
      if (!r.ok) {
        setMsg(root, mountId, "Preset failed (" + r.status + ").");
        return;
      }
      setMsg(root, mountId, "Saved yt-dlp-oneoff.conf (" + presetId + ").");
      await loadMount(mountId);
      if (mountId === "oneoffYtdlpSetupMount") {
        await loadMount("ytdlpOneoffSetupMount");
      } else if (mountId === "ytdlpOneoffSetupMount") {
        await loadMount("oneoffYtdlpSetupMount");
      }
    } catch {
      setMsg(root, mountId, "Preset failed (network error).");
    }
  }

  async function saveMount(mountId, presetId) {
    var root = document.getElementById(mountId);
    if (!root) {
      return;
    }
    var model = readModelFromMount(root, mountId);
    setMsg(root, mountId, "Saving…");
    try {
      var r = await fetch("/api/ytdlp-oneoff/setup/save", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          model: model,
          active_preset_id: presetId || "balanced",
          human_note: "",
        }),
      });
      if (!r.ok) {
        setMsg(root, mountId, "Save failed (" + r.status + ").");
        return;
      }
      setMsg(root, mountId, "Saved yt-dlp-oneoff.conf.");
      await loadMount(mountId);
    } catch {
      setMsg(root, mountId, "Save failed (network error).");
    }
  }

  function setMsg(root, mountId, text) {
    var el = q(root, "#" + mountId + "-msg");
    if (el) {
      el.textContent = text || "";
    }
  }

  function bindControls(root, mountId, data) {
    var fmt = q(root, "#" + mountId + "-format");
    var merge = q(root, "#" + mountId + "-merge");
    var noplay = q(root, "#" + mountId + "-noplaylist");
    var saveBtn = q(root, "#" + mountId + "-save");
    var capBtn = q(root, "#" + mountId + "-capture");
    [fmt, merge, noplay].forEach(function (el) {
      if (!el) {
        return;
      }
      el.addEventListener("input", function () {
        applyPreview(root, mountId, buildLocalPreview(readModelFromMount(root, mountId)));
      });
      el.addEventListener("change", function () {
        applyPreview(root, mountId, buildLocalPreview(readModelFromMount(root, mountId)));
      });
    });
    if (saveBtn) {
      saveBtn.addEventListener("click", function () {
        void saveMount(mountId, (mountState[mountId] || {}).active_preset_id);
      });
    }
    if (capBtn) {
      capBtn.addEventListener("click", async function () {
        setMsg(root, mountId, "Capturing…");
        try {
          var r = await fetch("/api/ytdlp-oneoff/setup/capture-user", {
            method: "POST",
          });
          if (!r.ok) {
            setMsg(root, mountId, "Capture failed.");
            return;
          }
          setMsg(root, mountId, "Captured as User preferences.");
          await loadMount(mountId);
        } catch {
          setMsg(root, mountId, "Capture failed.");
        }
      });
    }
    renderFormatQuick(root, mountId, data.format_presets || [], data.model.format);
    applyPreview(root, mountId, data.preview || buildLocalPreview(data.model));
  }

  async function loadMount(mountId) {
    var root = document.getElementById(mountId);
    if (!root) {
      return;
    }
    root.innerHTML =
      '<p class="muted small oneoff-ytdlp-loading">Loading single-download options…</p>';
    try {
      var r = await fetch("/api/ytdlp-oneoff/setup");
      if (!r.ok) {
        root.innerHTML =
          '<p class="callout warn small">Could not load <code>yt-dlp-oneoff.conf</code> (' +
          r.status +
          "). Restart Archive Console after upgrading, then hard-refresh (Ctrl+F5).</p>";
        return;
      }
      var j = await r.json();
      var active = j.active_preset_id || "balanced";
      var model = j.model || {};
      mountState[mountId] = {
        model: model,
        active_preset_id: active,
        preserved_tail: model.preserved_tail || "",
      };
      var hint =
        "Active preset: <strong>" +
        esc(active) +
        "</strong>" +
        (j.preset_from_last_save && j.preset_from_last_save !== active
          ? ' <span class="muted">(file banner: ' +
            esc(j.preset_from_last_save) +
            ")</span>"
          : "");
      root.innerHTML =
        '<p class="muted small" id="' +
        mountId +
        '-hint">' +
        hint +
        "</p>" +
        '<div class="ytdlp-preset-cards" id="' +
        mountId +
        '-cards"></div>' +
        '<div class="oneoff-ytdlp-fmt-row" id="' +
        mountId +
        '-fmt-quick"></div>' +
        '<label class="field"><span>Format (<code>-f</code>)</span>' +
        '<input type="text" id="' +
        mountId +
        '-format" autocomplete="off" value="' +
        esc(model.format || "") +
        '" /></label>' +
        '<label class="field inline-field"><span>Merge container</span>' +
        '<input type="text" id="' +
        mountId +
        '-merge" autocomplete="off" value="' +
        esc(model.merge_output_format || "mkv") +
        '" /></label>' +
        '<label class="chk"><input type="checkbox" id="' +
        mountId +
        '-noplaylist"' +
        (model.noplaylist !== false ? " checked" : "") +
        " /> <code>--no-playlist</code> (single video only)</label>" +
        '<div class="ytdlp-actions" style="margin-top:0.75rem">' +
        '<button type="button" class="btn ghost small" id="' +
        mountId +
        '-capture">Capture as User preferences</button>' +
        '<button type="button" class="btn primary small" id="' +
        mountId +
        '-save">Save yt-dlp-oneoff.conf</button>' +
        "</div>" +
        '<h3 class="small" style="margin:1rem 0 0.35rem">Effective CLI (after yt-dlp.conf)</h3>' +
        '<pre class="ytdlp-preview" id="' +
        mountId +
        '-preview"></pre>' +
        '<p class="muted small" id="' +
        mountId +
        '-msg" role="status"></p>';
      renderPresetCards(root, mountId, j.presets || [], active);
      bindControls(root, mountId, j);
    } catch {
      root.innerHTML =
        '<p class="callout warn small">Could not load single-download options (network error).</p>';
    }
  }

  window.ytdlpOneoffSetupLoad = function (mountId) {
    void loadMount(mountId || "oneoffYtdlpSetupMount");
  };

  window.ytdlpOneoffSetupLoadAll = function () {
    void loadMount("oneoffYtdlpSetupMount");
    void loadMount("ytdlpOneoffSetupMount");
  };
})();
