if (typeof browser === "undefined") var browser = chrome;

async function download(filename, blob) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

async function onMessage(message, sender, sendResponse) {
  if (message.message == "Download") {
    download(message.filename, message.blob);
  } else if (message.message == "Clipboard") {
    await navigator.clipboard.writeText(message.text);
  }
}

browser.runtime.onMessage.addListener(onMessage);
