/* Archive Console Cookies — fork of https://github.com/hrdl-github/cookies-txt */
var browser = browser || chrome;

const DEFAULT_BASE = "http://127.0.0.1:8756";
const ALARM_NAME = "archiveCookiePoll";
const YOUTUBE_EXPORT_URLS = ["https://www.youtube.com"];
/** Same cookie store only — avoids pulling www.google.com from a different Google account. */
const GOOGLE_SUPPLEMENT_URLS = [
  "https://accounts.google.com/",
];
const YOUTUBE_TAB_URL_RE =
  /^https?:\/\/([a-z0-9-]+\.)?(youtube\.com|music\.youtube\.com)\//i;
const WATCH_LATER_TAB_URL_RE =
  /(?:[?&]list=WL\b|\/feed\/watch_later(?:\/|$|\?))/i;

const NETSCAPE_HEADER = [
  "# Netscape HTTP Cookie File\n",
  "# https://curl.haxx.se/rfc/cookie_spec.html\n",
  "# This is a generated file! Do not edit.\n\n",
];

function formatCookie(co) {
  return [
    [
      !co.hostOnly && co.domain && !co.domain.startsWith(".") ? "." : "",
      co.domain,
    ].join(""),
    co.hostOnly ? "FALSE" : "TRUE",
    co.path,
    co.secure ? "TRUE" : "FALSE",
    co.session || !co.expirationDate ? 0 : Math.floor(co.expirationDate),
    co.name,
    co.value + "\n",
  ].join("\t");
}

async function getOptions() {
  return browser.storage.local.get({
    enabled: true,
    baseUrl: DEFAULT_BASE,
    pollMinutes: 0.167,
    cookieStoreId: "",
    reloadBeforeExport: true,
    /** "export_tab" = Watch Later / active / Subscriptions pick; "all" = every YouTube tab */
    reloadMode: "export_tab",
  });
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * Reload a tab and wait until status is complete (or timeout).
 * @param {number} tabId
 * @param {number} [timeoutMs]
 * @returns {Promise<boolean>}
 */
async function reloadTabAndWait(tabId, timeoutMs = 45000) {
  return new Promise((resolve) => {
    let settled = false;
    const finish = (ok) => {
      if (settled) {
        return;
      }
      settled = true;
      try {
        browser.tabs.onUpdated.removeListener(onUpdated);
      } catch (_e) {
        /* ignore */
      }
      clearTimeout(timer);
      resolve(ok);
    };
    const onUpdated = (id, info) => {
      if (id === tabId && info.status === "complete") {
        finish(true);
      }
    };
    const timer = setTimeout(() => finish(false), timeoutMs);
    browser.tabs.onUpdated.addListener(onUpdated);
    Promise.resolve(browser.tabs.reload(tabId)).catch(() => finish(false));
  });
}

/**
 * Before cookie export: reload YouTube tab(s) so Firefox picks up a fresh player/session.
 * Prefer the same tab used for export (Watch Later → active → Subscriptions → any).
 * @param {{ reloadBeforeExport?: boolean, reloadMode?: string }} opts
 */
async function reloadYoutubeTabsBeforeExport(opts) {
  if (!opts.reloadBeforeExport) {
    return { reloaded: 0, mode: "off" };
  }
  const mode = opts.reloadMode === "all" ? "all" : "export_tab";
  const tabs = await browser.tabs.query({});
  const ytTabs = tabs.filter((t) => t.url && isYoutubeTabUrl(t.url));
  if (!ytTabs.length) {
    return { reloaded: 0, mode, reason: "no_youtube_tabs" };
  }

  let targets;
  if (mode === "all") {
    targets = ytTabs;
  } else {
    const pick = await findYoutubeTabForExport();
    targets = pick ? [pick] : [];
  }

  let reloaded = 0;
  for (const tab of targets) {
    if (!tab.id) {
      continue;
    }
    const ok = await reloadTabAndWait(tab.id);
    if (ok) {
      reloaded += 1;
    }
  }
  // Allow Set-Cookie / jar settle after navigation before cookies.getAll
  if (reloaded > 0) {
    await sleep(1500);
  }
  return { reloaded, mode, attempted: targets.length };
}

async function getTargetStores(cookieStoreId) {
  const stores = await browser.cookies.getAllCookieStores();
  const id = (cookieStoreId || "").trim();
  if (id) {
    return stores.filter((store) => store.id === id);
  }
  const def = stores.filter((store) => store.id === "firefox-default");
  return def.length ? def : stores.slice(0, 1);
}

async function cookiesForUrl(storeId, url) {
  try {
    return await browser.cookies.getAll({
      url,
      storeId,
      firstPartyDomain: null,
    });
  } catch (_e) {
    return new Promise((resolve) => {
      browser.cookies.getAll({ url, storeId }, resolve);
    });
  }
}

function isYoutubeTabUrl(url) {
  return typeof url === "string" && YOUTUBE_TAB_URL_RE.test(url);
}

/**
 * Pick a YouTube tab for cookie export (same idea as popup "site + container").
 * Prefers Watch Later, then the active YouTube tab, then Subscriptions, then any YouTube tab.
 */
async function findYoutubeTabForExport() {
  const tabs = await browser.tabs.query({});
  const ytTabs = tabs.filter((t) => t.url && isYoutubeTabUrl(t.url));
  if (!ytTabs.length) {
    return null;
  }
  const watchLater = ytTabs.filter((t) => WATCH_LATER_TAB_URL_RE.test(t.url));
  if (watchLater.length) {
    const activeWl = watchLater.find((t) => t.active);
    return activeWl || watchLater[0];
  }
  const active = ytTabs.find((t) => t.active);
  if (active) {
    return active;
  }
  const subs = ytTabs.filter((t) => /\/feed\/subscriptions/i.test(t.url));
  if (subs.length) {
    return subs[0];
  }
  return ytTabs[0];
}

function mergeCookieBatches(seen, cookies, storeId, batch) {
  for (const co of batch || []) {
    const key = [storeId, co.name, co.domain, co.path].join("\t");
    if (seen.has(key)) {
      continue;
    }
    seen.add(key);
    cookies.push(co);
  }
}

/**
 * Site + container export: cookies for one page URL in one Firefox cookie store.
 * @param {string} pageUrl
 * @param {string} cookieStoreId
 * @param {{ supplementalUrls?: string[] }} [opts]
 */
async function exportNetscapeForSiteAndStore(pageUrl, cookieStoreId, opts = {}) {
  const seen = new Set();
  const cookies = [];
  const urls = [pageUrl].concat(opts.supplementalUrls || []);
  for (const url of urls) {
    const batch = await cookiesForUrl(cookieStoreId, url);
    mergeCookieBatches(seen, cookies, cookieStoreId, batch);
  }
  if (!cookies.length) {
    throw new Error(
      "No cookies for this YouTube tab URL in store " + cookieStoreId
    );
  }
  return NETSCAPE_HEADER.concat(cookies.map(formatCookie)).join("");
}

/**
 * Archive Console auto path: live YouTube tab (site + container) when possible.
 * @param {{ cookieStoreId?: string }} opts
 */
async function exportNetscapeForArchiveAuto(opts = {}) {
  const storeOverride = (opts.cookieStoreId || "").trim() || undefined;
  const tab = await findYoutubeTabForExport();
  if (tab && tab.url && tab.cookieStoreId) {
    const storeId = storeOverride || tab.cookieStoreId;
    const text = await exportNetscapeForSiteAndStore(tab.url, storeId, {
      supplementalUrls: GOOGLE_SUPPLEMENT_URLS,
    });
    return {
      text,
      source: "youtube_tab",
      tabUrl: tab.url,
      cookieStoreId: storeId,
    };
  }
  const text = await exportNetscapeForUrls(YOUTUBE_EXPORT_URLS, storeOverride);
  return {
    text,
    source: "fallback_urls",
    tabUrl: null,
    cookieStoreId: storeOverride,
  };
}

/**
 * Export YouTube + Google login cookies as Netscape text (no download).
 * @param {string[]} urls
 * @param {string|undefined} cookieStoreId
 */
async function exportNetscapeForUrls(urls, cookieStoreId) {
  const targetStores = await getTargetStores(cookieStoreId);
  const seen = new Set();
  const cookies = [];

  for (const store of targetStores) {
    for (const url of urls) {
      const batch = await cookiesForUrl(store.id, url);
      mergeCookieBatches(seen, cookies, store.id, batch);
    }
  }

  if (!cookies.length) {
    throw new Error("No YouTube/Google cookies found in this Firefox profile");
  }

  return NETSCAPE_HEADER.concat(cookies.map(formatCookie)).join("");
}

async function getCookiesFilename(storeId) {
  if (storeId == "firefox-default") {
    return "cookies.txt";
  }
  let containerName;
  try {
    containerName = (await browser.contextualIdentities.get(storeId)).name;
  } catch (_e) {
    containerName = storeId;
  }
  const containerNameSafe = containerName.replaceAll(/[\/\\]/g, "_");
  return "cookies." + containerNameSafe + ".txt";
}

async function saveCookies(cookies, storeId, clipboard = false) {
  const header = NETSCAPE_HEADER.slice();
  const body = cookies.map(formatCookie);

  if (clipboard) {
    const text = header.concat(body).join("");
    const tabId = (
      await browser.tabs.query({ active: true, currentWindow: true })
    )[0].id;
    await browser.tabs.sendMessage(tabId, {
      message: "Clipboard",
      text: text,
    });
  } else {
    const blob = new Blob(header.concat(body), { type: "text/plain" });
    const cookiesFilename = await getCookiesFilename(storeId);
    if ((await browser.runtime.getPlatformInfo()).os == "android") {
      const tabId = (
        await browser.tabs.query({ active: true, currentWindow: true })
      )[0].id;
      await browser.tabs.sendMessage(tabId, {
        message: "Download",
        blob: blob,
        filename: cookiesFilename,
      });
    } else {
      const objectURL = URL.createObjectURL(blob);
      browser.downloads.download({
        url: objectURL,
        filename: cookiesFilename,
        saveAs: true,
        conflictAction: "overwrite",
      });
    }
  }
}

async function getCookies(stores_filter, clipboard = false) {
  for (const store of stores_filter.stores) {
    let query;
    let cookies;
    try {
      query = {
        ...stores_filter.filter,
        ...{
          storeId: store.id,
          firstPartyDomain: null,
        },
      };
      cookies = await browser.cookies.getAll(query);
      await saveCookies(cookies, store.id, clipboard);
    } catch (_e) {
      cookies = await browser.cookies.getAll(
        {
          ...stores_filter.filter,
          ...{ storeId: store.id },
        },
        (batch) => saveCookies(batch, store.id, clipboard)
      );
    }
  }
}

function handleClick(filter = {}) {
  const clipboard = filter.clipboard || false;
  browser.cookies.getAllCookieStores((stores) =>
    getCookies(
      {
        stores: stores.filter(
          (store) =>
            filter.cookieStoreId == undefined ||
            store.id == filter.cookieStoreId
        ),
        filter: { url: filter.url },
      },
      clipboard
    )
  );
}

function normalizeBaseUrl(raw) {
  const s = (raw || DEFAULT_BASE).trim().replace(/\/+$/, "");
  return s || DEFAULT_BASE;
}

async function pollRefreshNeeded(baseUrl) {
  const r = await fetch(`${normalizeBaseUrl(baseUrl)}/api/cookies/youtube-refresh`);
  if (!r.ok) {
    throw new Error(`refresh status ${r.status}`);
  }
  return r.json();
}

async function putCookies(baseUrl, netscapeText) {
  const r = await fetch(`${normalizeBaseUrl(baseUrl)}/api/cookies/youtube`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content: netscapeText, unlock_cookies: true }),
  });
  if (!r.ok) {
    const detail = await r.text();
    throw new Error(detail || `PUT status ${r.status}`);
  }
  return r.json();
}

async function exportToArchiveConsole({ force = false } = {}) {
  const opts = await getOptions();
  if (!opts.enabled && !force) {
    return { skipped: true, reason: "disabled" };
  }

  const baseUrl = normalizeBaseUrl(opts.baseUrl);

  if (!force) {
    let status;
    try {
      status = await pollRefreshNeeded(baseUrl);
    } catch (e) {
      return { skipped: true, reason: "console_unreachable", error: String(e) };
    }
    if (!status.refresh_needed && !status.preflight_needed) {
      return { skipped: true, reason: "not_needed", status };
    }
  }

  // yt-dlp "The page needs to be reloaded" / stale session: refresh tab(s) first
  const reloadInfo = await reloadYoutubeTabsBeforeExport(opts);

  const exported = await exportNetscapeForArchiveAuto(opts);
  const result = await putCookies(baseUrl, exported.text);
  return {
    ok: true,
    result,
    source: exported.source,
    tabUrl: exported.tabUrl,
    cookieStoreId: exported.cookieStoreId,
    reload: reloadInfo,
  };
}

async function rescheduleAlarm() {
  const opts = await getOptions();
  await browser.alarms.clear(ALARM_NAME);
  if (!opts.enabled) {
    return;
  }
  const period = Math.max(0.1, Number(opts.pollMinutes) || 0.167);
  browser.alarms.create(ALARM_NAME, { periodInMinutes: period });
}

browser.alarms.onAlarm.addListener(async (alarm) => {
  if (alarm.name !== ALARM_NAME) {
    return;
  }
  try {
    await exportToArchiveConsole({ force: false });
  } catch (e) {
    console.warn("[archive-console-cookies]", e);
  }
});

browser.storage.onChanged.addListener((changes, area) => {
  if (
    area === "local" &&
    (changes.enabled || changes.pollMinutes || changes.baseUrl)
  ) {
    rescheduleAlarm();
  }
});

browser.runtime.onInstalled.addListener(() => {
  rescheduleAlarm();
});
browser.runtime.onStartup.addListener(() => {
  rescheduleAlarm();
});

browser.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg && msg.action === "exportToConsole") {
    exportToArchiveConsole({ force: true })
      .then((r) => sendResponse(r))
      .catch((e) => sendResponse({ ok: false, error: String(e) }));
    return true;
  }
  if (msg && msg.action === "exportYoutubeFiltered") {
    exportNetscapeForArchiveAuto({ cookieStoreId: msg.cookieStoreId })
      .then((exported) => exported.text)
      .then((text) => {
        if (msg.clipboard) {
          return navigator.clipboard.writeText(text).then(() => ({ ok: true }));
        }
        const blob = new Blob([text], { type: "text/plain" });
        const objectURL = URL.createObjectURL(blob);
        return browser.downloads.download({
          url: objectURL,
          filename: "cookies.txt",
          saveAs: true,
          conflictAction: "overwrite",
        }).then((id) => ({ ok: true, downloadId: id }));
      })
      .then((r) => sendResponse(r))
      .catch((e) => sendResponse({ ok: false, error: String(e) }));
    return true;
  }
  handleClick(msg || {});
});
