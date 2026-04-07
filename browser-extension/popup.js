const DEFAULT_BACKEND_BASE_URL = "http://127.0.0.1:8000";
const BACKEND_BASE_URL_STORAGE_KEY = "jobAssistBackendBaseUrl";

const button = document.getElementById("capture-button");
const captureVisibleButton = document.getElementById("capture-visible-button");
const saveSettingsButton = document.getElementById("save-settings-button");
const backendBaseUrlInput = document.getElementById("backend-base-url");
const statusNode = document.getElementById("status");

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
  const stored = await storage.get(BACKEND_BASE_URL_STORAGE_KEY);
  return stored[BACKEND_BASE_URL_STORAGE_KEY] || DEFAULT_BACKEND_BASE_URL;
}

async function saveBackendBaseUrl() {
  const storage = getStorageArea();
  const backendBaseUrl = normalizeBackendBaseUrl(backendBaseUrlInput.value);
  if (storage) {
    await storage.set({ [BACKEND_BASE_URL_STORAGE_KEY]: backendBaseUrl });
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

function setBusy(isBusy) {
  button.disabled = isBusy;
  captureVisibleButton.disabled = isBusy;
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

async function extractFromTab(tabId) {
  const response = await chrome.tabs.sendMessage(tabId, { type: "CAPTURE_JOB_PAGE" });
  if (!response || !response.ok) {
    const detail = response && response.error ? response.error : "No extraction response received.";
    throw new Error(detail);
  }
  return response.payload;
}

async function listVisibleLinkedInJobs(tabId) {
  const response = await chrome.tabs.sendMessage(tabId, { type: "LIST_VISIBLE_LINKEDIN_JOBS" });
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
  const response = await chrome.tabs.sendMessage(tabId, { type: "SCROLL_LINKEDIN_JOB_RAIL" });
  if (!response || !response.ok) {
    const detail = response && response.error ? response.error : "Could not scroll the LinkedIn jobs rail.";
    throw new Error(detail);
  }

  return response.payload;
}

async function captureVisibleLinkedInJob(tabId, target) {
  const response = await chrome.tabs.sendMessage(tabId, {
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
  const backendBaseUrl = await getBackendBaseUrl();
  const response = await fetch(`${backendBaseUrl}/plugins/scrape-current`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  const body = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = body && body.detail ? body.detail : `Request failed with status ${response.status}.`;
    throw new Error(detail);
  }

  return body;
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
        const payload = buildPayload(tab, extraction);
        await submitCapture(payload);
        progress.created += 1;
      } catch (_error) {
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
    setStatus(error instanceof Error ? error.message : "Bulk capture failed.", "error");
  } finally {
    setBusy(false);
  }
});

loadSettings().catch(() => {
  backendBaseUrlInput.value = DEFAULT_BACKEND_BASE_URL;
});
