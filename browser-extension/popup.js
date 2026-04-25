const DEFAULT_BACKEND_BASE_URL = "http://127.0.0.1:8000";
const BACKEND_BASE_URL_STORAGE_KEY = "jobAssistBackendBaseUrl";

const button = document.getElementById("capture-button");
const captureVisibleButton = document.getElementById("capture-visible-button");
const exportDiagnosticsButton = document.getElementById("export-diagnostics-button");
const saveSettingsButton = document.getElementById("save-settings-button");
const backendBaseUrlInput = document.getElementById("backend-base-url");
const statusNode = document.getElementById("status");
const diagnosticsEvents = [];
const MAX_DIAGNOSTIC_EVENTS = 200;
const MAX_DIAGNOSTIC_STRING_LENGTH = 2000;
let lastDiagnosticError = null;

function serializeError(error) {
  if (!error) {
    return null;
  }
  if (error instanceof Error) {
    return {
      name: error.name,
      message: error.message,
      stack: error.stack || null,
    };
  }
  if (typeof error === "object") {
    return sanitizeForDiagnostics(error);
  }
  return {
    name: typeof error,
    message: String(error),
    stack: null,
  };
}

function sanitizeForDiagnostics(value, depth = 0, key = "") {
  if (value === null || value === undefined) {
    return value;
  }
  if (value instanceof Error) {
    return serializeError(value);
  }
  if (typeof value === "string") {
    const lowerKey = key.toLowerCase();
    const isLargeCaptureField = ["html", "visible_text", "visibletext", "raw_content"].includes(lowerKey);
    if (isLargeCaptureField) {
      return {
        type: "truncated-string",
        originalLength: value.length,
        sample: value.slice(0, 500),
      };
    }
    if (value.length > MAX_DIAGNOSTIC_STRING_LENGTH) {
      return {
        type: "truncated-string",
        originalLength: value.length,
        sample: value.slice(0, MAX_DIAGNOSTIC_STRING_LENGTH),
      };
    }
    return value;
  }
  if (typeof value !== "object") {
    return value;
  }
  if (depth >= 5) {
    return "[Max diagnostic depth reached]";
  }
  if (Array.isArray(value)) {
    return value.slice(0, 50).map((item) => sanitizeForDiagnostics(item, depth + 1));
  }

  const output = {};
  for (const [entryKey, entryValue] of Object.entries(value)) {
    output[entryKey] = sanitizeForDiagnostics(entryValue, depth + 1, entryKey);
  }
  return output;
}

function recordDiagnostic(level, message, details) {
  diagnosticsEvents.push({
    timestamp: new Date().toISOString(),
    level,
    message,
    details: sanitizeForDiagnostics(details),
  });
  if (diagnosticsEvents.length > MAX_DIAGNOSTIC_EVENTS) {
    diagnosticsEvents.splice(0, diagnosticsEvents.length - MAX_DIAGNOSTIC_EVENTS);
  }
}

function normalizeBackendBaseUrl(value) {
  const normalized = String(value || "").trim().replace(/\/+$/, "");
  if (!normalized) {
    throw new Error("Backend URL is required.");
  }
  const parsed = new URL(normalized);
  if (!/^https?:$/.test(parsed.protocol)) {
    throw new Error("Backend URL must start with http:// or https://");
  }
  return parsed.toString().replace(/\/+$/, "");
}

function getStorageArea() {
  return chrome.storage?.sync || chrome.storage?.local;
}

async function getBackendBaseUrl() {
  const storage = getStorageArea();
  if (!storage) {
    return DEFAULT_BACKEND_BASE_URL;
  }
  try {
    const stored = await storage.get(BACKEND_BASE_URL_STORAGE_KEY);
    return stored[BACKEND_BASE_URL_STORAGE_KEY] || DEFAULT_BACKEND_BASE_URL;
  } catch (error) {
    console.warn("[Job Assist][Popup] Storage unavailable while reading backend URL; using default.", {
      error,
      message: error instanceof Error ? error.message : String(error),
    });
    return DEFAULT_BACKEND_BASE_URL;
  }
}

async function saveBackendBaseUrl() {
  const storage = getStorageArea();
  const backendBaseUrl = normalizeBackendBaseUrl(backendBaseUrlInput.value);
  if (storage) {
    try {
      await storage.set({ [BACKEND_BASE_URL_STORAGE_KEY]: backendBaseUrl });
    } catch (error) {
      console.warn("[Job Assist][Popup] Storage unavailable while saving backend URL.", {
        error,
        message: error instanceof Error ? error.message : String(error),
      });
    }
  }
  backendBaseUrlInput.value = backendBaseUrl;
  return backendBaseUrl;
}

async function loadSettings() {
  backendBaseUrlInput.value = await getBackendBaseUrl();
}

function setStatus(message, state) {
  statusNode.textContent = message;
  statusNode.dataset.state = state || "";
}

function logDebug(message, details) {
  recordDiagnostic("debug", message, details);
  if (details === undefined) {
    console.debug("[Job Assist][Popup]", message);
    return;
  }
  console.debug("[Job Assist][Popup]", message, details);
}

function setBusy(isBusy) {
  button.disabled = isBusy;
  captureVisibleButton.disabled = isBusy;
  exportDiagnosticsButton.disabled = isBusy;
}

function withSizeCap(value, maxLength) {
  if (typeof value !== "string") {
    return null;
  }
  if (value.length <= maxLength) {
    return value;
  }
  return value.slice(0, maxLength);
}

function buildPayload(tab, extraction) {
  logDebug("Building capture payload.", {
    tabUrl: tab?.url || null,
    extractionUrl: extraction?.url || null,
    extractionTitle: extraction?.title || null,
    extractionCompany: extraction?.company || null,
    extractionLocation: extraction?.location || null,
    extractionLinkedInJobId: extraction?.linkedinJobId || null,
    hasHtml: Boolean(extraction?.html),
    hasVisibleText: Boolean(extraction?.visibleText),
  });
  return {
    url: extraction.url || tab.url,
    title: extraction.title || tab.title || null,
    company: extraction.company || null,
    location: extraction.location || null,
    linkedin_job_id: extraction.linkedinJobId || null,
    html: withSizeCap(extraction.html, 750000),
    visible_text: withSizeCap(extraction.visibleText, 200000),
  };
}

async function getActiveTab() {
  const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
  return tabs[0] || null;
}

async function buildDiagnosticReport(reason, error = null) {
  const tab = await getActiveTab().catch((tabError) => ({
    diagnosticLookupError: serializeError(tabError),
  }));
  const backendBaseUrl = await getBackendBaseUrl().catch((backendError) => ({
    diagnosticLookupError: serializeError(backendError),
  }));

  return {
    generated_at: new Date().toISOString(),
    reason,
    last_error: serializeError(error || lastDiagnosticError),
    extension: {
      id: chrome.runtime?.id || null,
      manifest: sanitizeForDiagnostics(chrome.runtime?.getManifest?.() || null),
    },
    browser: {
      user_agent: navigator.userAgent,
      language: navigator.language,
      platform: navigator.platform,
    },
    popup: {
      status_text: statusNode.textContent || "",
      status_state: statusNode.dataset.state || "",
      backend_input_value: backendBaseUrlInput.value || "",
      resolved_backend_base_url: backendBaseUrl,
    },
    active_tab: sanitizeForDiagnostics(tab),
    recent_events: diagnosticsEvents.slice(),
  };
}

function downloadJsonFile(filename, data) {
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

async function exportDiagnostics(reason = "manual-export", error = null) {
  const report = await buildDiagnosticReport(reason, error);
  const timestamp = new Date().toISOString().replace(/[:.]/g, "-");
  downloadJsonFile(`job-assist-diagnostics-${timestamp}.json`, report);
  recordDiagnostic("info", "Diagnostics exported.", { reason });
  return report;
}

function isMissingContentScriptError(error) {
  const message = error instanceof Error ? error.message : String(error || "");
  return (
    message.includes("Could not establish connection") ||
    message.includes("Receiving end does not exist")
  );
}

async function ensureContentScriptInjected(tabId) {
  if (!chrome.scripting?.executeScript) {
    throw new Error("The extension cannot inject its content script in this browser.");
  }

  await chrome.scripting.executeScript({
    target: { tabId },
    files: ["content-script.js"],
  });
}

async function sendTabMessage(tabId, message) {
  logDebug("Sending message to tab.", { tabId, type: message?.type || null });
  try {
    const response = await chrome.tabs.sendMessage(tabId, message);
    logDebug("Received tab response.", {
      tabId,
      type: message?.type || null,
      ok: response?.ok ?? null,
      hasPayload: Boolean(response?.payload),
      error: response?.error || null,
    });
    return response;
  } catch (error) {
    if (!isMissingContentScriptError(error)) {
      recordDiagnostic("error", "Tab message failed.", {
        tabId,
        type: message?.type || null,
        error,
      });
      console.error("[Job Assist][Popup] Tab message failed.", {
        tabId,
        type: message?.type || null,
        error,
      });
      throw error;
    }

    logDebug("Content script missing; injecting and retrying.", { tabId });
    await ensureContentScriptInjected(tabId);
    const response = await chrome.tabs.sendMessage(tabId, message);
    logDebug("Received tab response after injection.", {
      tabId,
      type: message?.type || null,
      ok: response?.ok ?? null,
      hasPayload: Boolean(response?.payload),
      error: response?.error || null,
    });
    return response;
  }
}

async function extractFromTab(tabId) {
  const response = await sendTabMessage(tabId, { type: "CAPTURE_JOB_PAGE" });
  if (!response || !response.ok) {
    const detail = response && response.error ? response.error : "No extraction response received.";
    throw new Error(detail);
  }
  return response.payload;
}

async function listVisibleLinkedInJobs(tabId) {
  const response = await sendTabMessage(tabId, { type: "LIST_VISIBLE_LINKEDIN_JOBS" });
  if (!response || !response.ok) {
    const detail = response && response.error ? response.error : "No visible LinkedIn jobs found.";
    throw new Error(detail);
  }

  return Array.isArray(response.payload?.jobs) ? response.payload.jobs : [];
}

function delay(ms) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

async function listVisibleLinkedInJobsWithRetry(tabId, options = {}) {
  const {
    railRetryDelaysMs = [],
    renderRetryDelaysMs = [],
    railStatusMessage = null,
    renderStatusMessage = null,
    emptyMessage = "No visible LinkedIn jobs were found in the current jobs rail.",
    allowEmpty = false,
    strictRail = false,
  } = options;

  let lastError = null;

  try {
    const jobs = await listVisibleLinkedInJobs(tabId);
    if (jobs.length || !renderRetryDelaysMs.length) {
      if (!jobs.length && !allowEmpty) {
        throw new Error(emptyMessage);
      }
      return jobs;
    }
  } catch (error) {
    lastError = error;
    const message = error instanceof Error ? error.message : String(error);
    if (message !== "Could not find the LinkedIn jobs rail." || !railRetryDelaysMs.length) {
      throw error;
    }
  }

  for (const waitMs of railRetryDelaysMs) {
    if (railStatusMessage) {
      setStatus(railStatusMessage);
    }
    await delay(waitMs);

    try {
      const jobs = await listVisibleLinkedInJobs(tabId);
      if (jobs.length || !renderRetryDelaysMs.length) {
        if (!jobs.length && !allowEmpty) {
          throw new Error(emptyMessage);
        }
        return jobs;
      }
      lastError = null;
      break;
    } catch (error) {
      lastError = error;
      const message = error instanceof Error ? error.message : String(error);
      if (message !== "Could not find the LinkedIn jobs rail.") {
        throw error;
      }
    }
  }

  if (lastError) {
    if (strictRail) {
      throw lastError;
    }
    const message = lastError instanceof Error ? lastError.message : String(lastError);
    if (message === "Could not find the LinkedIn jobs rail.") {
      return [];
    }
    throw lastError;
  }

  for (const waitMs of renderRetryDelaysMs) {
    if (renderStatusMessage) {
      setStatus(renderStatusMessage);
    }
    await delay(waitMs);

    try {
      const jobs = await listVisibleLinkedInJobs(tabId);
      if (jobs.length) {
        return jobs;
      }
      lastError = null;
    } catch (error) {
      lastError = error;
      const message = error instanceof Error ? error.message : String(error);
      if (message !== "Could not find the LinkedIn jobs rail.") {
        throw error;
      }
    }
  }

  if (lastError) {
    if (strictRail) {
      throw lastError;
    }
    const message = lastError instanceof Error ? lastError.message : String(lastError);
    if (message === "Could not find the LinkedIn jobs rail.") {
      return [];
    }
    throw lastError;
  }

  if (!allowEmpty) {
    throw new Error(emptyMessage);
  }

  return [];
}

async function scrollLinkedInJobRail(tabId) {
  const response = await sendTabMessage(tabId, { type: "SCROLL_LINKEDIN_JOB_RAIL" });
  if (!response || !response.ok) {
    const detail = response && response.error ? response.error : "Could not scroll the LinkedIn jobs rail.";
    throw new Error(detail);
  }

  return response.payload;
}

async function captureVisibleLinkedInJob(tabId, target) {
  const response = await sendTabMessage(tabId, {
    type: "CAPTURE_LINKEDIN_VISIBLE_JOB",
    payload: target,
  });
  if (!response || !response.ok) {
    const detail = response && response.error ? response.error : "Could not capture the selected LinkedIn job.";
    throw new Error(detail);
  }

  return response.payload;
}

async function submitCapture(payload) {
  logDebug("submitCapture entered.", {
    payloadUrl: payload?.url || null,
    payloadTitle: payload?.title || null,
    payloadLinkedInJobId: payload?.linkedin_job_id || null,
  });

  try {
    const backendBaseUrl = await getBackendBaseUrl();
    logDebug("Resolved backend base URL.", { backendBaseUrl });

    const requestUrl = `${backendBaseUrl}/plugins/scrape-current`;
    logDebug("Submitting capture.", {
      requestUrl,
      url: payload?.url || null,
      title: payload?.title || null,
      linkedinJobId: payload?.linkedin_job_id || null,
      hasHtml: Boolean(payload?.html),
      hasVisibleText: Boolean(payload?.visible_text),
    });

    const response = await fetch(requestUrl, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    });

    const body = await response.json().catch(() => null);
    logDebug("Capture response received.", {
      requestUrl,
      status: response.status,
      ok: response.ok,
      body,
    });
    if (!response.ok) {
      const detail = body && body.detail ? body.detail : `Request failed with status ${response.status}.`;
      throw new Error(detail);
    }

    return body;
  } catch (error) {
    lastDiagnosticError = error;
    recordDiagnostic("error", "submitCapture failed.", {
      error,
      message: error instanceof Error ? error.message : String(error),
      stack: error instanceof Error ? error.stack : null,
    });
    console.error("[Job Assist][Popup] submitCapture failed.", {
      error,
      message: error instanceof Error ? error.message : String(error),
      stack: error instanceof Error ? error.stack : null,
    });
    throw error;
  }
}

saveSettingsButton.addEventListener("click", async () => {
  try {
    const backendBaseUrl = await saveBackendBaseUrl();
    setStatus(`Saved backend URL:\n${backendBaseUrl}`, "success");
  } catch (error) {
    setStatus(error instanceof Error ? error.message : "Could not save backend URL.", "error");
  }
});

async function captureCurrentTab() {
  const tab = await getActiveTab();
  if (!tab || !tab.id || !tab.url) {
    throw new Error("No active browser tab is available.");
  }

  const extraction = await extractFromTab(tab.id);
  const payload = buildPayload(tab, extraction);
  logDebug("Current-tab payload built.", payload);
  return submitCapture(payload);
}

function formatBatchStatus(progress) {
  return [
    `Capture Visible Jobs: ${progress.processed}/${progress.discovered}`,
    `Created: ${progress.created}`,
    `Skipped duplicates: ${progress.skippedDuplicates}`,
    `Failed: ${progress.failed}`,
  ].join("\n");
}

function getBatchJobKey(job) {
  return job.linkedinJobId || job.fallbackKey || job.title || null;
}

async function captureVisibleJobs() {
  const tab = await getActiveTab();
  if (!tab || !tab.id || !tab.url) {
    throw new Error("No active browser tab is available.");
  }

  const progress = {
    discovered: 0,
    processed: 0,
    created: 0,
    skippedDuplicates: 0,
    failed: 0,
    scrolls: 0,
    errors: [],
  };
  const processedKeys = new Set();
  const discoveredKeys = new Set();
  const duplicateKeys = new Set();
  const maxNoProgressRetries = 3;
  const postScrollRailRetryDelaysMs = [500, 1000, 1500, 2000];
  const postScrollRenderRetryDelaysMs = [500, 1000, 1500, 2000];
  let noProgressRetries = 0;

  const initialJobs = await listVisibleLinkedInJobsWithRetry(tab.id, {
    railRetryDelaysMs: postScrollRailRetryDelaysMs,
    renderRetryDelaysMs: postScrollRenderRetryDelaysMs,
    railStatusMessage: "Waiting for LinkedIn jobs rail to reappear…",
    renderStatusMessage: "Waiting for LinkedIn jobs to render…",
    emptyMessage: "No visible LinkedIn jobs were found in the current jobs rail.",
    strictRail: true,
    allowEmpty: false,
  });

  while (true) {
    const visibleJobs = progress.scrolls
      ? await listVisibleLinkedInJobsWithRetry(tab.id, {
          railRetryDelaysMs: postScrollRailRetryDelaysMs,
          renderRetryDelaysMs: postScrollRenderRetryDelaysMs,
          railStatusMessage: `${formatBatchStatus(progress)}\n\nWaiting for LinkedIn jobs rail to reappear…`,
          renderStatusMessage: `${formatBatchStatus(progress)}\n\nWaiting for jobs to render…`,
          allowEmpty: true,
        })
      : initialJobs;
    const pendingJobs = [];
    const scanKeys = new Set();

    for (const job of visibleJobs) {
      const batchKey = getBatchJobKey(job);
      if (!batchKey) {
        continue;
      }

      if (scanKeys.has(batchKey)) {
        if (!duplicateKeys.has(batchKey)) {
          duplicateKeys.add(batchKey);
          progress.skippedDuplicates += 1;
        }
        continue;
      }
      scanKeys.add(batchKey);

      if (!discoveredKeys.has(batchKey)) {
        discoveredKeys.add(batchKey);
        progress.discovered += 1;
      }

      if (processedKeys.has(batchKey)) {
        if (!duplicateKeys.has(batchKey)) {
          duplicateKeys.add(batchKey);
          progress.skippedDuplicates += 1;
        }
      } else {
        pendingJobs.push({ ...job, batchKey });
      }
    }

    if (pendingJobs.length) {
      noProgressRetries = 0;
    }

    for (const job of pendingJobs) {
      setStatus(`${formatBatchStatus(progress)}\n\nOpening: ${job.title || job.linkedinJobId || "job"}`);

      try {
        const extraction = await captureVisibleLinkedInJob(tab.id, job);
        logDebug("Captured visible LinkedIn job.", {
          batchKey: job.batchKey,
          title: job.title || null,
          linkedinJobId: job.linkedinJobId || null,
          extraction,
        });
        const payload = buildPayload(tab, extraction);
        logDebug("Visible-job payload built.", {
          batchKey: job.batchKey,
          payload,
        });
        await submitCapture(payload);
        progress.created += 1;
      } catch (error) {
        lastDiagnosticError = error;
        recordDiagnostic("error", "Visible-job capture failed.", {
          batchKey: job.batchKey,
          title: job.title || null,
          linkedinJobId: job.linkedinJobId || null,
          error,
        });
        console.error("[Job Assist][Popup] Visible-job capture failed.", {
          batchKey: job.batchKey,
          title: job.title || null,
          linkedinJobId: job.linkedinJobId || null,
          error,
        });
        progress.errors.push({
          batchKey: job.batchKey,
          title: job.title || null,
          linkedinJobId: job.linkedinJobId || null,
          error: serializeError(error),
        });
        progress.failed += 1;
      } finally {
        processedKeys.add(job.batchKey);
        progress.processed += 1;
        setStatus(formatBatchStatus(progress));
      }
    }

    const scrollState = await scrollLinkedInJobRail(tab.id);
    progress.scrolls += 1;
    setStatus(`${formatBatchStatus(progress)}\n\nScrolling...`);

    const afterScrollJobs = await listVisibleLinkedInJobsWithRetry(tab.id, {
      railRetryDelaysMs: postScrollRailRetryDelaysMs,
      renderRetryDelaysMs: postScrollRenderRetryDelaysMs,
      railStatusMessage: `${formatBatchStatus(progress)}\n\nWaiting for LinkedIn jobs rail to reappear…`,
      renderStatusMessage: `${formatBatchStatus(progress)}\n\nWaiting for jobs to render…`,
      allowEmpty: true,
    });
    let foundNewAfterScroll = false;
    for (const job of afterScrollJobs) {
      const batchKey = getBatchJobKey(job);
      if (!batchKey) {
        continue;
      }
      if (!discoveredKeys.has(batchKey)) {
        discoveredKeys.add(batchKey);
        progress.discovered += 1;
        foundNewAfterScroll = true;
      }
    }

    if (foundNewAfterScroll) {
      noProgressRetries = 0;
      setStatus(`${formatBatchStatus(progress)}\n\nScrolled for more jobs…`);
      continue;
    }

    noProgressRetries += 1;

    if (scrollState.atEnd || noProgressRetries >= maxNoProgressRetries) {
      setStatus(`${formatBatchStatus(progress)}\n\nReached the end of the LinkedIn jobs rail.`);
      break;
    }

    setStatus(
      `${formatBatchStatus(progress)}\n\nScrolling for more jobs… (${noProgressRetries}/${maxNoProgressRetries})`
    );
  }

  return progress;
}

button.addEventListener("click", async () => {
  setBusy(true);
  setStatus("Capturing current page…");

  try {
    const result = await captureCurrentTab();
    const title = result?.structured_data?.tentative_job_title || result?.structured_data?.page_title || "job";
    const source = result?.structured_data?.source || "generic";
    setStatus(`Saved ${title}.\nSource: ${source}\nPlugin: ${result.plugin_name}`, "success");
  } catch (error) {
    lastDiagnosticError = error;
    recordDiagnostic("error", "Capture Job failed.", { error });
    await exportDiagnostics("capture-job-failed", error).catch((diagnosticError) => {
      console.error("[Job Assist][Popup] Could not export diagnostics.", diagnosticError);
    });
    setStatus(error instanceof Error ? error.message : "Capture failed.", "error");
  } finally {
    setBusy(false);
  }
});

captureVisibleButton.addEventListener("click", async () => {
  setBusy(true);
  setStatus("Collecting visible LinkedIn jobs…");

  try {
    const summary = await captureVisibleJobs();
    if (summary.failed) {
      await exportDiagnostics("capture-visible-jobs-had-failures", summary.errors.at(-1)?.error || null).catch(
        (diagnosticError) => {
          console.error("[Job Assist][Popup] Could not export diagnostics.", diagnosticError);
        }
      );
    }
    setStatus(
      [
        "Capture Visible Jobs complete.",
        `Created: ${summary.created}`,
        `Skipped duplicates: ${summary.skippedDuplicates}`,
        `Failed: ${summary.failed}`,
      ].join("\n"),
      summary.failed ? "error" : "success"
    );
  } catch (error) {
    lastDiagnosticError = error;
    recordDiagnostic("error", "Capture Visible Jobs failed.", { error });
    await exportDiagnostics("capture-visible-jobs-failed", error).catch((diagnosticError) => {
      console.error("[Job Assist][Popup] Could not export diagnostics.", diagnosticError);
    });
    setStatus(error instanceof Error ? error.message : "Bulk capture failed.", "error");
  } finally {
    setBusy(false);
  }
});

exportDiagnosticsButton.addEventListener("click", async () => {
  try {
    await exportDiagnostics("manual-export");
    setStatus("Diagnostics exported.", "success");
  } catch (error) {
    setStatus(error instanceof Error ? error.message : "Could not export diagnostics.", "error");
  }
});

loadSettings().catch(() => {
  backendBaseUrlInput.value = DEFAULT_BACKEND_BASE_URL;
});
