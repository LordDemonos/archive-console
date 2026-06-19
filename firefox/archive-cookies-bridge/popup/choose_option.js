if (typeof browser === "undefined") var browser = chrome;

for (const elem of document.querySelectorAll("[data-i18n]")) {
  elem.textContent = browser.i18n.getMessage(elem.attributes['data-i18n'].value);
}

queryWithCurrentTab = (tabToMsgFn) => {
  var query = (typeof browser === "undefined") ? { active: true, windowId: browser.windows.WINDOW_ID_CURRENT }
    : { active: true, currentWindow: true };
  browser.tabs.query(query, tabs => {
    if (tabs.length > 0) {
      browser.runtime.sendMessage(tabToMsgFn(tabs[0]));
    }
  });
  window.close();
};

//download buttons
document.querySelector("#all .download").addEventListener("click", () => {
  browser.runtime.sendMessage({});
  window.close();
});
document.querySelector("#current .download").addEventListener("click", () => queryWithCurrentTab((tab) => ({ url: tab.url })));
document.querySelector("#container-all .download").addEventListener("click", () => queryWithCurrentTab((tab) => ({ cookieStoreId: tab.cookieStoreId })));
document.querySelector("#container-current .download").addEventListener("click", () => queryWithCurrentTab((tab) => ({ url: tab.url, cookieStoreId: tab.cookieStoreId })));

//copy buttons
document.querySelector("#all .copy").addEventListener("click", () => {
  browser.runtime.sendMessage({ clipboard: true });
  window.close();
});
document.querySelector("#current .copy").addEventListener("click", () => queryWithCurrentTab((tab) => ({ url: tab.url, clipboard: true })));
document.querySelector("#container-all .copy").addEventListener("click", () => queryWithCurrentTab((tab) => ({ cookieStoreId: tab.cookieStoreId, clipboard: true })));
document.querySelector("#container-current .copy").addEventListener("click", () => queryWithCurrentTab((tab) => ({ url: tab.url, cookieStoreId: tab.cookieStoreId, clipboard: true })));

document.querySelector("#btnYoutubeDownload").addEventListener("click", () => {
  browser.runtime.sendMessage({ action: "exportYoutubeFiltered" });
  window.close();
});

const consoleStatus = document.getElementById("consoleExportStatus");
document.getElementById("btnConsoleExport").addEventListener("click", () => {
  if (consoleStatus) {
    consoleStatus.hidden = false;
    consoleStatus.textContent = "Sending…";
  }
  browser.runtime.sendMessage({ action: "exportToConsole" }, (response) => {
    if (consoleStatus) {
      if (browser.runtime.lastError) {
        consoleStatus.textContent = browser.runtime.lastError.message;
        return;
      }
      if (response && response.ok) {
        var detail = "Sent to Archive Console (cookies.txt updated).";
        if (response.source === "youtube_tab" && response.tabUrl) {
          detail +=
            " From open tab: " +
            response.tabUrl.replace(/^https?:\/\//, "").slice(0, 60);
        } else if (response.source === "fallback_urls") {
          detail +=
            " No YouTube tab found — used youtube.com + google.com fallback.";
        }
        consoleStatus.textContent = detail;
      } else if (response && response.skipped) {
        consoleStatus.textContent =
          "Skipped: " + (response.reason || "unknown") +
          (response.error ? " — " + response.error : "");
      } else {
        consoleStatus.textContent =
          (response && response.error) || "Export failed.";
      }
    }
  });
});
