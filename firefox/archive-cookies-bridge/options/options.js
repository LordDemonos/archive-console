if (typeof browser === "undefined") {
  var browser = chrome;
}

const DEFAULT_BASE = "http://127.0.0.1:8756";

const els = {
  enabled: document.getElementById("enabled"),
  baseUrl: document.getElementById("baseUrl"),
  pollMinutes: document.getElementById("pollMinutes"),
  cookieStoreId: document.getElementById("cookieStoreId"),
  save: document.getElementById("save"),
  status: document.getElementById("status"),
};

async function load() {
  const opts = await browser.storage.local.get({
    enabled: true,
    baseUrl: DEFAULT_BASE,
    pollMinutes: 0.167,
    cookieStoreId: "",
  });
  els.enabled.checked = !!opts.enabled;
  els.baseUrl.value = opts.baseUrl || DEFAULT_BASE;
  els.pollMinutes.value = String(opts.pollMinutes != null ? opts.pollMinutes : 0.167);
  els.cookieStoreId.value = opts.cookieStoreId || "";
}

async function save() {
  const poll = parseFloat(els.pollMinutes.value, 10);
  await browser.storage.local.set({
    enabled: els.enabled.checked,
    baseUrl: (els.baseUrl.value || DEFAULT_BASE).trim(),
    pollMinutes: isFinite(poll) && poll >= 0.1 ? poll : 0.167,
    cookieStoreId: (els.cookieStoreId.value || "").trim(),
  });
  els.status.textContent = "Saved.";
  setTimeout(() => {
    els.status.textContent = "";
  }, 2000);
}

els.save.addEventListener("click", () => {
  save().catch((e) => {
    els.status.textContent = String(e);
  });
});

load();
