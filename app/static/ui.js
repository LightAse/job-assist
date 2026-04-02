function showMessage(text) {
  const message = document.getElementById("message");
  message.textContent = text;
  message.hidden = false;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function showPlaceholder(label) {
  const text = `${label} is not implemented yet.`;
  showMessage(text);
  window.alert(text);
}

function formatTitle(job) {
  return job.page_title || job.tentative_job_title || job.latest_snapshot?.title || "Untitled job";
}

function formatValue(value) {
  return value || "N/A";
}

function createMetaRow(label, value, options = {}) {
  const safeValue = escapeHtml(value);
  const valueMarkup = options.href
    ? `<a href="${escapeHtml(options.href)}" target="_blank" rel="noreferrer">${safeValue}</a>`
    : safeValue;

  return `
    <div class="${options.detail ? "detail-row" : "meta-row"}">
      <div class="${options.detail ? "detail-label" : "meta-label"}">${escapeHtml(label)}</div>
      <div class="${options.detail ? "detail-value" : "meta-value"}">${valueMarkup}</div>
    </div>
  `;
}

function createTextBlock(label, value) {
  return `
    <div class="detail-row">
      <div class="detail-label">${escapeHtml(label)}</div>
      <pre class="text-block">${escapeHtml(formatValue(value))}</pre>
    </div>
  `;
}

function renderCompatibilityCheck(check) {
  if (!check) {
    return `<p class="muted">No compatibility check has been run yet.</p>`;
  }

  return `
    <div class="compatibility-card">
      <div class="score-row">
        <div>
          <div class="detail-label">Decision</div>
          <div class="decision">${escapeHtml(check.decision)}</div>
        </div>
        <div>
          <div class="detail-label">Score</div>
          <div class="score">${escapeHtml(String(check.score))}/100</div>
        </div>
      </div>
      ${createMetaRow("Created At", formatValue(check.created_at), { detail: true })}
      ${createTextBlock("Summary", check.summary)}
      ${createTextBlock("Strengths", (check.strengths || []).join("\n"))}
      ${createTextBlock("Gaps", (check.gaps || []).join("\n"))}
    </div>
  `;
}

function renderResumeProfileOptions(profiles) {
  if (profiles.length === 0) {
    return `<option value="">Create a resume profile first</option>`;
  }

  return profiles
    .map((profile) => `<option value="${profile.id}">${escapeHtml(profile.name)}</option>`)
    .join("");
}

async function fetchJson(url, options) {
  const response = await fetch(url, options);
  if (response.status === 404) {
    return null;
  }
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    const detail = body && body.detail ? body.detail : `Request failed: ${response.status}`;
    throw new Error(detail);
  }
  if (response.status === 204) {
    return {};
  }
  return response.json();
}

async function renderJobsList(root) {
  const jobs = await fetchJson("/jobs");
  if (!jobs || jobs.length === 0) {
    root.innerHTML = `<p class="muted">No stored jobs yet.</p>`;
    return;
  }

  root.innerHTML = `
    <div class="jobs-grid">
      ${jobs
        .map(
          (job) => `
            <article class="job-card">
              <h2 class="job-title">${escapeHtml(formatTitle(job))}</h2>
              <div class="meta-list">
                ${createMetaRow("Source", formatValue(job.source))}
                ${createMetaRow("External Job ID", formatValue(job.external_job_id))}
                ${createMetaRow("Source URL", job.source_url, { href: job.source_url })}
                ${createMetaRow("Created At", formatValue(job.created_at))}
              </div>
              <div class="actions">
                <a class="button button-primary" href="/jobs/${job.id}/view">View More</a>
              </div>
            </article>
          `
        )
        .join("")}
    </div>
  `;
}

async function loadResumeProfiles() {
  return fetchJson("/resume-profiles");
}

async function createResumeProfile(name, content) {
  return fetchJson("/resume-profiles", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, content }),
  });
}

async function runCompatibilityCheck(jobId, resumeProfileId) {
  return fetchJson(`/jobs/${jobId}/compatibility-checks`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ resume_profile_id: Number(resumeProfileId) }),
  });
}

function attachResumeProfileForm(root, select) {
  const createButton = root.querySelector("#create-profile-button");
  createButton.addEventListener("click", async () => {
    const nameInput = root.querySelector("#resume-profile-name");
    const contentInput = root.querySelector("#resume-profile-content");
    const name = nameInput.value.trim();
    const content = contentInput.value.trim();

    if (!name || !content) {
      showMessage("Resume profile name and content are required.");
      return;
    }

    const profile = await createResumeProfile(name, content);
    const option = document.createElement("option");
    option.value = String(profile.id);
    option.textContent = profile.name;
    select.appendChild(option);
    select.value = String(profile.id);
    nameInput.value = "";
    contentInput.value = "";
    showMessage("Resume profile created.");
  });
}

function attachJobActions(root, jobId) {
  root.querySelector("#send-cv-button").addEventListener("click", () => {
    showPlaceholder("Send CV");
  });
  root.querySelector("#delete-button").addEventListener("click", async () => {
    const response = await fetch(`/jobs/${jobId}`, { method: "DELETE" });
    if (response.status === 204) {
      window.location.href = "/";
      return;
    }
    showMessage("Delete failed.");
  });
}

async function renderJobDetails(root, jobId) {
  const [job, resumeProfiles] = await Promise.all([
    fetchJson(`/jobs/${jobId}`),
    loadResumeProfiles(),
  ]);
  if (!job) {
    root.innerHTML = `<p class="muted">Job not found.</p>`;
    return;
  }

  const snapshot = job.latest_snapshot;
  root.innerHTML = `
    <article class="job-card">
      <h2 class="job-title">${escapeHtml(formatTitle(job))}</h2>
      <div class="detail-list">
        ${createMetaRow("ID", String(job.id), { detail: true })}
        ${createMetaRow("Source", formatValue(job.source), { detail: true })}
        ${createMetaRow("External Job ID", formatValue(job.external_job_id), { detail: true })}
        ${createMetaRow("Page Title", formatValue(job.page_title), { detail: true })}
        ${createMetaRow("Tentative Job Title", formatValue(job.tentative_job_title), { detail: true })}
        ${createMetaRow("Source URL", job.source_url, { detail: true, href: job.source_url })}
        ${createMetaRow("Created At", formatValue(job.created_at), { detail: true })}
      </div>

      <h3 class="section-title">Latest Snapshot</h3>
      <div class="detail-list">
        ${snapshot ? createMetaRow("Snapshot Title", formatValue(snapshot.title), { detail: true }) : ""}
        ${snapshot ? createMetaRow("Company", formatValue(snapshot.company), { detail: true }) : ""}
        ${snapshot ? createMetaRow("Location", formatValue(snapshot.location), { detail: true }) : ""}
        ${snapshot ? createMetaRow("Plugin", formatValue(snapshot.plugin_name), { detail: true }) : ""}
        ${snapshot ? createMetaRow("Captured At", formatValue(snapshot.captured_at), { detail: true }) : ""}
        ${snapshot ? createTextBlock("Visible Text", snapshot.visible_text) : `<p class="muted">No snapshot available.</p>`}
        ${snapshot ? createTextBlock("HTML", snapshot.html) : ""}
      </div>

      <h3 class="section-title">Compatibility Check</h3>
      <div class="detail-list">
        <div class="form-row">
          <label class="detail-label" for="resume-profile-select">Resume Profile</label>
          <select id="resume-profile-select" class="input">${renderResumeProfileOptions(resumeProfiles || [])}</select>
        </div>
        <div class="actions">
          <button id="check-button" class="button button-secondary">Check</button>
          <button id="send-cv-button" class="button button-secondary">Send CV</button>
          <button id="delete-button" class="button button-danger">Delete</button>
          <a class="button button-primary" href="/">Back</a>
        </div>
        <div class="form-row">
          <label class="detail-label" for="resume-profile-name">New Resume Profile</label>
          <input id="resume-profile-name" class="input" type="text" placeholder="Profile name">
        </div>
        <div class="form-row">
          <label class="detail-label" for="resume-profile-content">Resume Content</label>
          <textarea id="resume-profile-content" class="input input-large" placeholder="Paste resume text"></textarea>
        </div>
        <div class="actions">
          <button id="create-profile-button" class="button button-secondary">Save Resume Profile</button>
        </div>
      </div>

      <h3 class="section-title">Latest Result</h3>
      <section id="compatibility-result">
        ${renderCompatibilityCheck(job.latest_compatibility_check)}
      </section>
    </article>
  `;

  const select = root.querySelector("#resume-profile-select");
  attachResumeProfileForm(root, select);
  attachJobActions(root, jobId);

  root.querySelector("#check-button").addEventListener("click", async () => {
    if (!select.value) {
      showMessage("Choose or create a resume profile first.");
      return;
    }

    try {
      const response = await runCompatibilityCheck(jobId, select.value);
      root.querySelector("#compatibility-result").innerHTML = renderCompatibilityCheck(response.compatibility_check);
      showMessage("Compatibility check completed.");
    } catch (error) {
      showMessage(error.message);
    }
  });
}

async function init() {
  const root = document.getElementById("app");
  const route = root.dataset.route || "jobs";
  const checkAllButton = document.getElementById("check-all-button");

  if (route.startsWith("job:")) {
    checkAllButton.hidden = true;
    const jobId = route.split(":")[1];
    await renderJobDetails(root, jobId);
    return;
  }

  checkAllButton.addEventListener("click", () => {
    showPlaceholder("Check All");
  });
  await renderJobsList(root);
}

init().catch((error) => {
  showMessage(error.message || "Something went wrong while loading the page.");
});
