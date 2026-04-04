const resumeUiState = {
  selectedProfileId: null,
  selectedJobId: null,
  importPreview: null,
  instructionDrafts: {
    profileId: null,
    summary: null,
    skills: null,
    experience: null,
    projects: null,
  },
  promptSettings: null,
  promptSettingsDrafts: {
    summary: null,
    skills: null,
    experience: null,
    projects: null,
  },
  profileInstructionOverrides: {
    summary: null,
    skills: null,
    experience: null,
    projects: null,
  },
  settingsTab: "api",
  sectionGeneration: {
    summary: { loading: false },
    skills: { loading: false },
  },
  editing: {
    skills: null,
    workExperiences: null,
    projects: null,
    education: null,
    certifications: null,
    languages: null,
    links: null,
  },
};

const jobsUiState = {
  jobs: [],
  batchRunActive: false,
  batchRun: null,
  batchPollTimer: null,
  batchPollInFlight: false,
  currentView: "board",
  searchQuery: "",
  statusFilter: "all",
  compatibilityFilter: "all",
  sortKey: "score_desc",
  boardPages: {},
  openBoardChangeMenuJobId: null,
  transientStatuses: {},
};

const defaultSummarySectionPrompt = `You are generating a professional resume summary tailored to a specific job.

Use ONLY the candidate's provided source material. Do not invent experience, skills, or achievements.

Goals:

Align the summary with the job requirements
Highlight relevant skills and experience
Keep a professional and concise tone

Constraints:

Maximum 80–100 words
Output must be in English
Avoid generic phrases like "hardworking" or "team player"
Focus on concrete technical strengths and relevant experience

Input will include:

Job description
Candidate summary source
Selected skills/projects/experience

Output:

A single paragraph summary`;

const defaultSectionInstructionPrompts = {
  summary: defaultSummarySectionPrompt,
  skills: "",
  experience: "",
  projects: "",
};

const masterSectionConfig = {
  skills: {
    label: "Skills",
    endpoint: "/resume-data/skills",
    idKey: "id",
    fields: [
      { name: "name", label: "Skill", type: "text", required: true, placeholder: "FastAPI" },
      { name: "proficiency_level", label: "Proficiency", type: "text", placeholder: "Advanced" },
      { name: "notes", label: "Notes", type: "textarea", placeholder: "English-first wording for this skill." },
    ],
    toPayload(formData) {
      return {
        name: formData.get("name").trim(),
        proficiency_level: optionalValue(formData.get("proficiency_level")),
        notes: optionalValue(formData.get("notes")),
      };
    },
    renderItem(item) {
      const detail = [item.proficiency_level, item.notes].filter(Boolean).join(" | ");
      return `<strong>${escapeHtml(item.name)}</strong>${detail ? `<div class="muted">${escapeHtml(detail)}</div>` : ""}`;
    },
  },
  workExperiences: {
    label: "Work Experience",
    endpoint: "/resume-data/work-experiences",
    idKey: "id",
    fields: [
      { name: "company", label: "Company", type: "text", required: true, placeholder: "Globant" },
      { name: "title", label: "Title", type: "text", required: true, placeholder: "Senior Software Engineer" },
      { name: "location", label: "Location", type: "text", placeholder: "Buenos Aires, Argentina" },
      { name: "start_date", label: "Start Date", type: "text", placeholder: "2022-01" },
      { name: "end_date", label: "End Date", type: "text", placeholder: "Present" },
      { name: "summary", label: "Summary", type: "textarea", placeholder: "Delivered backend APIs in English-speaking product teams." },
      { name: "highlights", label: "Highlights", type: "textarea", placeholder: "One bullet per line" },
    ],
    toPayload(formData) {
      return {
        company: formData.get("company").trim(),
        title: formData.get("title").trim(),
        location: optionalValue(formData.get("location")),
        start_date: optionalValue(formData.get("start_date")),
        end_date: optionalValue(formData.get("end_date")),
        summary: optionalValue(formData.get("summary")),
        highlights: linesValue(formData.get("highlights")),
      };
    },
    renderItem(item) {
      return `
        <strong>${escapeHtml(item.title)} | ${escapeHtml(item.company)}</strong>
        <div class="muted">${escapeHtml([item.location, formatDateRange(item.start_date, item.end_date)].filter(Boolean).join(" | ") || "No metadata")}</div>
        ${item.summary ? `<div>${escapeHtml(item.summary)}</div>` : ""}
      `;
    },
  },
  projects: {
    label: "Projects",
    endpoint: "/resume-data/projects",
    idKey: "id",
    fields: [
      { name: "name", label: "Project Name", type: "text", required: true, placeholder: "Internal Hiring Platform" },
      { name: "role", label: "Role", type: "text", placeholder: "Lead Backend Engineer" },
      { name: "summary", label: "Summary", type: "textarea", placeholder: "Built a deterministic workflow for job intake and screening." },
      { name: "technologies", label: "Technologies", type: "text", placeholder: "Python, FastAPI, SQLite" },
      { name: "url", label: "URL", type: "text", placeholder: "https://example.com/project" },
    ],
    toPayload(formData) {
      return {
        name: formData.get("name").trim(),
        role: optionalValue(formData.get("role")),
        summary: optionalValue(formData.get("summary")),
        technologies: commaSeparatedValue(formData.get("technologies")),
        url: optionalValue(formData.get("url")),
      };
    },
    renderItem(item) {
      const detail = [item.role, item.url].filter(Boolean).join(" | ");
      const tech = item.technologies.length ? `Technologies: ${item.technologies.join(", ")}` : "";
      return `<strong>${escapeHtml(item.name)}</strong>${detail ? `<div class="muted">${escapeHtml(detail)}</div>` : ""}${item.summary ? `<div>${escapeHtml(item.summary)}</div>` : ""}${tech ? `<div class="muted">${escapeHtml(tech)}</div>` : ""}`;
    },
  },
  education: {
    label: "Education",
    endpoint: "/resume-data/education",
    idKey: "id",
    fields: [
      { name: "institution", label: "Institution", type: "text", required: true, placeholder: "University of Buenos Aires" },
      { name: "degree", label: "Degree", type: "text", required: true, placeholder: "B.Sc. Computer Science" },
      { name: "field_of_study", label: "Field of Study", type: "text", placeholder: "Computer Science" },
      { name: "start_date", label: "Start Date", type: "text", placeholder: "2018" },
      { name: "end_date", label: "End Date", type: "text", placeholder: "2023" },
      { name: "summary", label: "Summary", type: "textarea", placeholder: "Relevant coursework and achievements in English." },
    ],
    toPayload(formData) {
      return {
        institution: formData.get("institution").trim(),
        degree: formData.get("degree").trim(),
        field_of_study: optionalValue(formData.get("field_of_study")),
        start_date: optionalValue(formData.get("start_date")),
        end_date: optionalValue(formData.get("end_date")),
        summary: optionalValue(formData.get("summary")),
      };
    },
    renderItem(item) {
      const title = item.field_of_study ? `${item.degree}, ${item.field_of_study}` : item.degree;
      return `<strong>${escapeHtml(title)} | ${escapeHtml(item.institution)}</strong><div class="muted">${escapeHtml(formatDateRange(item.start_date, item.end_date) || "No dates")}</div>${item.summary ? `<div>${escapeHtml(item.summary)}</div>` : ""}`;
    },
  },
  certifications: {
    label: "Certifications",
    endpoint: "/resume-data/certifications",
    idKey: "id",
    fields: [
      { name: "name", label: "Certification", type: "text", required: true, placeholder: "AWS Certified Developer" },
      { name: "issuer", label: "Issuer", type: "text", required: true, placeholder: "Amazon Web Services" },
      { name: "issued_on", label: "Issued On", type: "text", placeholder: "2024-08" },
      { name: "credential_id", label: "Credential ID", type: "text", placeholder: "ABC-123" },
      { name: "credential_url", label: "Credential URL", type: "text", placeholder: "https://example.com/credential" },
    ],
    toPayload(formData) {
      return {
        name: formData.get("name").trim(),
        issuer: formData.get("issuer").trim(),
        issued_on: optionalValue(formData.get("issued_on")),
        credential_id: optionalValue(formData.get("credential_id")),
        credential_url: optionalValue(formData.get("credential_url")),
      };
    },
    renderItem(item) {
      const detail = [item.issued_on, item.credential_id, item.credential_url].filter(Boolean).join(" | ");
      return `<strong>${escapeHtml(item.name)} | ${escapeHtml(item.issuer)}</strong>${detail ? `<div class="muted">${escapeHtml(detail)}</div>` : ""}`;
    },
  },
  languages: {
    label: "Languages",
    endpoint: "/resume-data/languages",
    idKey: "id",
    fields: [
      { name: "name", label: "Language", type: "text", required: true, placeholder: "English" },
      { name: "proficiency", label: "Proficiency", type: "text", required: true, placeholder: "Professional working proficiency" },
    ],
    toPayload(formData) {
      return {
        name: formData.get("name").trim(),
        proficiency: formData.get("proficiency").trim(),
      };
    },
    renderItem(item) {
      return `<strong>${escapeHtml(item.name)}</strong><div class="muted">${escapeHtml(item.proficiency)}</div>`;
    },
  },
  links: {
    label: "Links",
    endpoint: "/resume-data/links",
    idKey: "id",
    fields: [
      { name: "label", label: "Label", type: "text", required: true, placeholder: "LinkedIn" },
      { name: "url", label: "URL", type: "text", required: true, placeholder: "https://linkedin.com/in/example" },
      { name: "link_type", label: "Type", type: "text", placeholder: "linkedin" },
    ],
    toPayload(formData) {
      return {
        label: formData.get("label").trim(),
        url: formData.get("url").trim(),
        link_type: optionalValue(formData.get("link_type")),
      };
    },
    renderItem(item) {
      const detail = [item.link_type, item.url].filter(Boolean).join(" | ");
      return `<strong>${escapeHtml(item.label)}</strong><div class="muted">${escapeHtml(detail)}</div>`;
    },
  },
};

function showMessage(text) {
  const message = document.getElementById("message");
  message.textContent = text;
  message.hidden = false;
}

function clearMessage() {
  const message = document.getElementById("message");
  message.textContent = "";
  message.hidden = true;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function formatTitle(job) {
  return job.page_title || job.tentative_job_title || job.latest_snapshot?.title || "Untitled job";
}

function formatJobListLabel(job) {
  const company = job.latest_snapshot?.company?.trim();
  const title = job.latest_snapshot?.title?.trim() || formatTitle(job);

  if (!company) {
    return escapeHtml(title);
  }

  return `<span class="job-company-prefix">[${escapeHtml(company)}]</span> <span class="job-title-text">${escapeHtml(title)}</span>`;
}

function formatJobOptionLabel(job) {
  const company = job.latest_snapshot?.company?.trim();
  const title = job.latest_snapshot?.title?.trim() || formatTitle(job);
  return company ? `[${company}] ${title}` : title;
}

function formatValue(value) {
  return value || "N/A";
}

function optionalValue(value) {
  const normalized = String(value || "").trim();
  return normalized || null;
}

function linesValue(value) {
  return String(value || "")
    .split("\n")
    .map((item) => item.trim())
    .filter(Boolean);
}

function commaSeparatedValue(value) {
  return String(value || "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function formatDateRange(startDate, endDate) {
  if (startDate && endDate) {
    return `${startDate} - ${endDate}`;
  }
  return startDate || endDate || "";
}

function formatShortDate(value) {
  if (!value) {
    return "N/A";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return String(value).slice(0, 10);
  }
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  }).format(date);
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

function renderCandidateCompatibilitySummary(check) {
  if (!check) {
    return `<p class="muted">No candidate-data compatibility score yet.</p>`;
  }
  return `
    <div class="compatibility-card">
      <div class="score-row">
        <div>
          <div class="detail-label">Compatibility Score</div>
          <div class="score">${escapeHtml(String(check.score))}/100</div>
        </div>
      </div>
      ${createMetaRow("Created At", formatValue(check.created_at), { detail: true })}
      ${createTextBlock("Reason", check.short_reason)}
    </div>
  `;
}

function getCandidateCompatibilityTone(score) {
  if (score >= 70) {
    return "compatibility-badge-high";
  }
  if (score >= 40) {
    return "compatibility-badge-medium";
  }
  return "compatibility-badge-low";
}

function renderCandidateCompatibilityBadge(check) {
  return renderCandidateCompatibilityBadgeForVariant(check, "default");
}

function renderCandidateCompatibilityBadgeForVariant(check, variant = "default") {
  if (!check) {
    return `<div class="compatibility-badge compatibility-badge-empty">No score yet</div>`;
  }
  const text = variant === "compact"
    ? `${escapeHtml(String(check.score))}/100`
    : `Compatibility ${escapeHtml(String(check.score))}/100`;
  return `
    <div class="compatibility-badge ${getCandidateCompatibilityTone(check.score)}" aria-label="Latest candidate compatibility score">
      <span class="compatibility-badge-text">${text}</span>
    </div>
  `;
}

function renderJobCardStatus(status, tone = "muted") {
  if (!status) {
    return "";
  }
  return `<div class="job-card-status ${tone === "error" ? "job-card-status-error" : "muted"}">${escapeHtml(status)}</div>`;
}

const jobStatusConfig = [
  { key: "new", label: "New" },
  { key: "in_progress", label: "In Progress" },
  { key: "applied", label: "Applied" },
  { key: "dropped", label: "Dropped" },
  { key: "archived", label: "Archived" },
];

const boardPageSize = 3;

function getJobStatusLabel(status) {
  return jobStatusConfig.find((item) => item.key === status)?.label || "New";
}

function getCandidateCompatibilityScore(job) {
  return job.latest_candidate_compatibility_check?.score ?? null;
}

function matchesCompatibilityFilter(job, filterKey) {
  const score = getCandidateCompatibilityScore(job);
  if (filterKey === "all") {
    return true;
  }
  if (filterKey === "unscored") {
    return score === null;
  }
  if (score === null) {
    return false;
  }
  if (filterKey === "high") {
    return score >= 70;
  }
  if (filterKey === "medium") {
    return score >= 40 && score < 70;
  }
  if (filterKey === "low") {
    return score < 40;
  }
  return true;
}

function compareJobsByScoreThenCreated(a, b) {
  const scoreA = getCandidateCompatibilityScore(a);
  const scoreB = getCandidateCompatibilityScore(b);
  if (scoreA !== null && scoreB !== null && scoreA !== scoreB) {
    return scoreB - scoreA;
  }
  if (scoreA !== null && scoreB === null) {
    return -1;
  }
  if (scoreA === null && scoreB !== null) {
    return 1;
  }
  return b.id - a.id;
}

function getFilteredAndSortedJobs() {
  const query = jobsUiState.searchQuery.trim().toLowerCase();
  let jobs = [...jobsUiState.jobs];

  if (query) {
    jobs = jobs.filter((job) => {
      const company = (job.latest_snapshot?.company || "").toLowerCase();
      const title = (job.latest_snapshot?.title || formatTitle(job) || "").toLowerCase();
      return company.includes(query) || title.includes(query);
    });
  }

  if (jobsUiState.statusFilter !== "all") {
    jobs = jobs.filter((job) => job.status === jobsUiState.statusFilter);
  }

  if (jobsUiState.compatibilityFilter !== "all") {
    jobs = jobs.filter((job) => matchesCompatibilityFilter(job, jobsUiState.compatibilityFilter));
  }

  if (jobsUiState.sortKey === "score_asc") {
    jobs.sort((a, b) => compareJobsByScoreThenCreated(b, a));
  } else if (jobsUiState.sortKey === "title_asc") {
    jobs.sort((a, b) => formatJobOptionLabel(a).localeCompare(formatJobOptionLabel(b)));
  } else {
    jobs.sort(compareJobsByScoreThenCreated);
  }

  return jobs;
}

function renderJobStatusSelect(job) {
  return `
    <label class="job-status-control">
      <span class="detail-label">Status</span>
      <select class="input" data-job-status-select="${job.id}">
        ${jobStatusConfig
          .map((statusOption) => `<option value="${statusOption.key}" ${job.status === statusOption.key ? "selected" : ""}>${escapeHtml(statusOption.label)}</option>`)
          .join("")}
      </select>
    </label>
  `;
}

function renderJobCard(job, variant = "full") {
  const transientStatus = jobsUiState.transientStatuses[job.id] || { text: "", tone: "muted" };
  const isBoardCard = variant === "board";
  const fullLabelText = formatJobOptionLabel(job);
  return `
    <article class="job-card ${isBoardCard ? "job-card-compact" : ""}" data-job-card="${job.id}">
      <div class="job-card-topline">
        <div data-job-badge>${isBoardCard ? renderCandidateCompatibilityBadgeForVariant(job.latest_candidate_compatibility_check, "compact") : renderCandidateCompatibilityBadge(job.latest_candidate_compatibility_check)}</div>
        ${isBoardCard ? "" : `<div class="job-status-pill">${escapeHtml(getJobStatusLabel(job.status))}</div>`}
      </div>
      <div data-job-status>${renderJobCardStatus(transientStatus.text, transientStatus.tone)}</div>
      <h2 class="job-title ${isBoardCard ? "job-title-compact" : ""}" ${isBoardCard ? `title="${escapeHtml(fullLabelText)}"` : ""}>${formatJobListLabel(job)}</h2>
      ${
        isBoardCard
          ? `
            <div class="meta-list compact-meta-list">
              ${createMetaRow("Created", formatShortDate(job.created_at))}
            </div>
          `
          : `
            <div class="meta-list">
              ${createMetaRow("Status", getJobStatusLabel(job.status))}
              ${createMetaRow("Source", formatValue(job.source))}
              ${createMetaRow("External Job ID", formatValue(job.external_job_id))}
              ${createMetaRow("Source URL", job.source_url, { href: job.source_url })}
              ${createMetaRow("Created At", formatValue(job.created_at))}
            </div>
            <div class="job-card-controls">
              ${renderJobStatusSelect(job)}
            </div>
          `
      }
      <div class="actions">
        ${
          isBoardCard
            ? `
              <div class="board-card-actions">
                <a class="button button-primary button-compact" href="/jobs/${job.id}/view">View</a>
                <div class="board-change-menu-wrap">
                  <button class="button button-secondary button-compact" type="button" data-board-change-toggle="${job.id}">Change</button>
                  ${
                    jobsUiState.openBoardChangeMenuJobId === job.id
                      ? `
                        <div class="board-change-menu">
                          ${jobStatusConfig
                            .map(
                              (statusOption) => `
                                <button
                                  class="board-change-option"
                                  type="button"
                                  data-board-change-job="${job.id}"
                                  data-board-change-status="${statusOption.key}"
                                >
                                  ${escapeHtml(statusOption.label)}
                                </button>
                              `
                            )
                            .join("")}
                        </div>
                      `
                      : ""
                  }
                </div>
              </div>
            `
            : `<a class="button button-primary" href="/jobs/${job.id}/view">View More</a>`
        }
      </div>
    </article>
  `;
}

function renderResumeProfileOptions(profiles) {
  if (profiles.length === 0) {
    return `<option value="">Build a resume profile first</option>`;
  }

  return [
    `<option value="">Choose a resume profile</option>`,
    ...profiles.map((profile) => `<option value="${profile.id}">${escapeHtml(profile.name)}</option>`),
  ].join("");
}

function renderJobOptions(jobs) {
  if (!jobs.length) {
    return `<option value="">No stored jobs available</option>`;
  }

  return [
    `<option value="">Choose a job</option>`,
    ...jobs.map((job) => `<option value="${job.id}">${escapeHtml(formatJobOptionLabel(job))}</option>`),
  ].join("");
}

async function fetchJson(url, options) {
  const response = await fetch(url, options);
  if (response.status === 404) {
    return null;
  }
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    const detail = body && body.detail ? body.detail : `Request failed: ${response.status}`;
    const error = new Error(detail);
    error.status = response.status;
    error.detail = detail;
    throw error;
  }
  if (response.status === 204) {
    return {};
  }
  return response.json();
}

async function deleteResource(url) {
  const response = await fetch(url, { method: "DELETE" });
  if (!response.ok && response.status !== 204) {
    const body = await response.json().catch(() => null);
    throw new Error(body && body.detail ? body.detail : `Delete failed: ${response.status}`);
  }
}

function fileToBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = String(reader.result || "");
      const base64 = result.includes(",") ? result.split(",", 2)[1] : result;
      resolve(base64);
    };
    reader.onerror = () => reject(new Error("Failed to read the uploaded file."));
    reader.readAsDataURL(file);
  });
}

function renderJobsBoard(jobs) {
  return `
    <div class="jobs-board-scroll">
      <div class="jobs-board">
      ${jobStatusConfig
        .map((statusOption) => {
          const groupedJobs = jobs
            .filter((job) => job.status === statusOption.key)
            .sort(compareJobsByScoreThenCreated);
          const totalPages = Math.max(1, Math.ceil(groupedJobs.length / boardPageSize));
          const currentPage = Math.min(jobsUiState.boardPages[statusOption.key] || 1, totalPages);
          const pageStart = (currentPage - 1) * boardPageSize;
          const visibleJobs = groupedJobs.slice(pageStart, pageStart + boardPageSize);
          return `
            <section class="jobs-board-column">
              <div class="section-header">
                <div>
                  <p class="eyebrow">Status</p>
                  <h3>${escapeHtml(statusOption.label)}</h3>
                </div>
                <div class="board-count">${groupedJobs.length}</div>
              </div>
              <div class="jobs-board-cards">
                <div class="jobs-grid">
                  ${visibleJobs.length ? visibleJobs.map((job) => renderJobCard(job, "board")).join("") : `<p class="muted">No jobs in this column.</p>`}
                </div>
              </div>
              <div class="board-pagination">
                <button
                  class="button button-secondary"
                  type="button"
                  data-board-page-status="${statusOption.key}"
                  data-board-page-direction="prev"
                  ${currentPage <= 1 ? "disabled" : ""}
                >
                  Prev
                </button>
                <span class="board-pagination-label">Page ${currentPage} of ${totalPages}</span>
                <button
                  class="button button-secondary"
                  type="button"
                  data-board-page-status="${statusOption.key}"
                  data-board-page-direction="next"
                  ${currentPage >= totalPages ? "disabled" : ""}
                >
                  Next
                </button>
              </div>
            </section>
          `;
        })
        .join("")}
      </div>
    </div>
  `;
}

function renderCompatibilityFilterControls() {
  const options = [
    { key: "all", label: "All" },
    { key: "high", label: "High Match" },
    { key: "medium", label: "Medium Match" },
    { key: "low", label: "Low Match" },
    { key: "unscored", label: "Unscored" },
  ];

  return `
    <div class="jobs-match-filter" role="group" aria-label="Compatibility filter">
      ${options
        .map(
          (option) => `
            <button
              class="button ${jobsUiState.compatibilityFilter === option.key ? "button-primary" : "button-secondary"}"
              type="button"
              data-compatibility-filter="${option.key}"
            >
              ${escapeHtml(option.label)}
            </button>
          `
        )
        .join("")}
    </div>
  `;
}

function renderAllJobsView(jobs) {
  return `
    <div class="jobs-controls panel">
      <div class="form-row">
        <div class="detail-label">Match Level</div>
        ${renderCompatibilityFilterControls()}
      </div>
      <div class="form-row">
        <label class="detail-label" for="jobs-search">Search</label>
        <input id="jobs-search" class="input" type="search" placeholder="Search company or title" value="${escapeHtml(jobsUiState.searchQuery)}">
      </div>
      <div class="jobs-filter-grid">
        <div class="form-row">
          <label class="detail-label" for="jobs-status-filter">Status</label>
          <select id="jobs-status-filter" class="input">
            <option value="all">All statuses</option>
            ${jobStatusConfig.map((statusOption) => `<option value="${statusOption.key}" ${jobsUiState.statusFilter === statusOption.key ? "selected" : ""}>${escapeHtml(statusOption.label)}</option>`).join("")}
          </select>
        </div>
        <div class="form-row">
          <label class="detail-label" for="jobs-sort">Sort</label>
          <select id="jobs-sort" class="input">
            <option value="score_desc" ${jobsUiState.sortKey === "score_desc" ? "selected" : ""}>Compatibility high to low</option>
            <option value="score_asc" ${jobsUiState.sortKey === "score_asc" ? "selected" : ""}>Compatibility low to high</option>
            <option value="title_asc" ${jobsUiState.sortKey === "title_asc" ? "selected" : ""}>Company / title A-Z</option>
          </select>
        </div>
      </div>
    </div>
    <div class="jobs-grid jobs-all-list">
      ${jobs.length ? jobs.map((job) => renderJobCard(job, "full")).join("") : `<p class="muted">No jobs match the current filters.</p>`}
    </div>
  `;
}

function renderJobsWorkspace(root) {
  const jobs = getFilteredAndSortedJobs();
  if (!jobsUiState.jobs.length) {
    root.innerHTML = `<p class="muted">No stored jobs yet.</p>`;
    refreshJobsPageActions();
    return;
  }

  root.innerHTML = `
    <section class="jobs-workspace">
      <div class="jobs-view-switcher">
        <button class="button ${jobsUiState.currentView === "board" ? "button-primary" : "button-secondary"}" type="button" data-jobs-view="board">Jobs Board</button>
        <button class="button ${jobsUiState.currentView === "all" ? "button-primary" : "button-secondary"}" type="button" data-jobs-view="all">All Jobs</button>
      </div>
      ${renderCompatibilityFilterControls()}
      <p class="muted">Use the board as a work queue and the all-jobs view for search and filtering.</p>
      ${jobsUiState.currentView === "board" ? renderJobsBoard(jobs) : renderAllJobsView(jobs)}
    </section>
  `;
  bindJobsWorkspaceEvents(root);
  refreshJobsPageActions();
}

async function loadAndRenderJobsWorkspace(root) {
  jobsUiState.jobs = (await fetchJson("/jobs")) || [];
  applyBatchRunToUi(await fetchCurrentJobCheckBatch());
  renderJobsWorkspace(root);
  if (jobsUiState.batchRunActive) {
    ensureJobCheckBatchPolling(root);
  } else {
    stopJobsBatchPolling();
  }
}

async function runCandidateCompatibilityCheck(jobId) {
  return fetchJson(`/jobs/${jobId}/candidate-compatibility-check`, {
    method: "POST",
  });
}

function setJobsBatchProgress({ current, total, completed = false, prefix = "Checking" }) {
  const status = document.getElementById("check-all-status");
  if (!status) {
    return;
  }
  if (completed) {
    status.textContent = "";
    status.hidden = true;
    return;
  }
  status.hidden = false;
  status.textContent = `${prefix} ${current}/${total}...`;
}

async function startJobCheckBatch(mode) {
  return fetchJson("/jobs/check-batch", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ mode }),
  });
}

async function fetchCurrentJobCheckBatch() {
  return fetchJson("/jobs/check-batch/current");
}

async function fetchJobCheckBatch(batchId) {
  return fetchJson(`/jobs/check-batch/${batchId}`);
}

function stopJobsBatchPolling() {
  if (jobsUiState.batchPollTimer) {
    window.clearInterval(jobsUiState.batchPollTimer);
    jobsUiState.batchPollTimer = null;
  }
}

function syncTransientStatusesFromBatch(batchRun) {
  jobsUiState.transientStatuses = {};
  if (!batchRun) {
    return;
  }
  batchRun.items.forEach((item) => {
    if (item.status === "running") {
      jobsUiState.transientStatuses[item.job_id] = { text: "Checking...", tone: "muted" };
    } else if (item.status === "completed") {
      jobsUiState.transientStatuses[item.job_id] = { text: "Checked", tone: "muted" };
    } else if (item.status === "failed") {
      jobsUiState.transientStatuses[item.job_id] = { text: formatJobFailureMessage({ detail: item.error_message || "Unknown error." }), tone: "error" };
    }
  });
}

function applyBatchRunToUi(batchRun) {
  jobsUiState.batchRun = batchRun;
  jobsUiState.batchRunActive = Boolean(batchRun && batchRun.status === "running");
  syncTransientStatusesFromBatch(batchRun);

  if (batchRun && batchRun.status === "running") {
    const prefix = batchRun.mode === "unscored" ? "Checking unscored" : "Checking";
    setJobsBatchProgress({
      current: batchRun.completed_jobs + batchRun.failed_jobs,
      total: batchRun.total_jobs,
      prefix,
    });
    return;
  }

  setJobsBatchProgress({ current: 0, total: 0, completed: true });
}

async function pollJobCheckBatch(root, { silent = false } = {}) {
  if (jobsUiState.batchPollInFlight) {
    return;
  }
  jobsUiState.batchPollInFlight = true;
  try {
    const batchRun = jobsUiState.batchRun?.id
      ? await fetchJobCheckBatch(jobsUiState.batchRun.id)
      : await fetchCurrentJobCheckBatch();
    applyBatchRunToUi(batchRun);
    jobsUiState.jobs = (await fetchJson("/jobs")) || [];
    renderJobsWorkspace(root);

    if (!batchRun || batchRun.status !== "running") {
      stopJobsBatchPolling();
      if (!silent && batchRun) {
        if (batchRun.status === "completed") {
          showMessage(`Batch finished. ${batchRun.completed_jobs} succeeded, ${batchRun.failed_jobs} failed.`);
        } else if (batchRun.last_error) {
          showMessage(batchRun.last_error);
        }
      }
    }
  } finally {
    jobsUiState.batchPollInFlight = false;
  }
}

function ensureJobCheckBatchPolling(root) {
  if (jobsUiState.batchPollTimer) {
    return;
  }
  jobsUiState.batchPollTimer = window.setInterval(async () => {
    await pollJobCheckBatch(root);
  }, 1500);
}

function updateJobCardCompatibility(jobId, compatibilityCheck) {
  const job = jobsUiState.jobs.find((item) => item.id === jobId);
  if (job) {
    job.latest_candidate_compatibility_check = compatibilityCheck;
  }
  const root = document.getElementById("app");
  if (root) {
    renderJobsWorkspace(root);
  }
  refreshJobsPageActions();
}

function updateJobCardStatus(jobId, status, tone = "muted") {
  jobsUiState.transientStatuses[jobId] = { text: status, tone };
  const jobCard = document.querySelector(`[data-job-card="${jobId}"]`);
  if (!jobCard) {
    return;
  }
  const statusContainer = jobCard.querySelector("[data-job-status]");
  if (statusContainer) {
    statusContainer.innerHTML = renderJobCardStatus(status, tone);
  }
}

function formatJobFailureMessage(error) {
  const detail = error?.detail || error?.message || "Unknown error.";
  if (isOpenRouterPrivacyPolicyFailure(error)) {
    return "Check failed: The selected OpenRouter model is unavailable under your current Privacy/Data Policy settings. Check OpenRouter Settings -> Privacy or choose another model.";
  }
  return `Check failed: ${detail}`;
}

function isSystemicUpstreamFailure(error) {
  const detail = (error?.detail || error?.message || "").toLowerCase();
  return error?.status === 502 || detail.includes("provider") || detail.includes("openrouter");
}

function isOpenRouterPrivacyPolicyFailure(error) {
  const detail = (error?.detail || error?.message || "").toLowerCase();
  return detail.includes("guardrail restrictions")
    || detail.includes("data policy")
    || detail.includes("privacy/data policy");
}

async function updateJobStatus(jobId, statusValue) {
  return fetchJson(`/jobs/${jobId}/status`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status: statusValue }),
  });
}

function bindJobsWorkspaceEvents(root) {
  root.querySelectorAll("[data-jobs-view]").forEach((button) => {
    button.addEventListener("click", () => {
      jobsUiState.currentView = button.dataset.jobsView;
      renderJobsWorkspace(root);
    });
  });

  root.querySelectorAll("[data-compatibility-filter]").forEach((button) => {
    button.addEventListener("click", () => {
      jobsUiState.compatibilityFilter = button.dataset.compatibilityFilter;
      renderJobsWorkspace(root);
    });
  });

  root.querySelectorAll("[data-board-page-status]").forEach((button) => {
    button.addEventListener("click", () => {
      const statusKey = button.dataset.boardPageStatus;
      const direction = button.dataset.boardPageDirection;
      const currentPage = jobsUiState.boardPages[statusKey] || 1;
      jobsUiState.openBoardChangeMenuJobId = null;
      jobsUiState.boardPages[statusKey] = Math.max(1, currentPage + (direction === "next" ? 1 : -1));
      renderJobsWorkspace(root);
    });
  });

  root.querySelectorAll("[data-board-change-toggle]").forEach((button) => {
    button.addEventListener("click", () => {
      const jobId = Number(button.dataset.boardChangeToggle);
      jobsUiState.openBoardChangeMenuJobId = jobsUiState.openBoardChangeMenuJobId === jobId ? null : jobId;
      renderJobsWorkspace(root);
    });
  });

  root.querySelectorAll("[data-board-change-job]").forEach((button) => {
    button.addEventListener("click", async () => {
      const jobId = Number(button.dataset.boardChangeJob);
      const nextStatus = button.dataset.boardChangeStatus;
      const job = jobsUiState.jobs.find((item) => item.id === jobId);
      const previousStatus = job?.status;
      jobsUiState.openBoardChangeMenuJobId = null;
      updateJobCardStatus(jobId, "Saving status...");
      renderJobsWorkspace(root);
      try {
        const updatedJob = await updateJobStatus(jobId, nextStatus);
        if (job) {
          job.status = updatedJob.status;
        }
        updateJobCardStatus(jobId, "Status updated");
        renderJobsWorkspace(root);
      } catch (error) {
        if (job && previousStatus) {
          job.status = previousStatus;
        }
        updateJobCardStatus(jobId, "Status update failed", "error");
        showMessage(error.message);
        renderJobsWorkspace(root);
      }
    });
  });

  const searchInput = root.querySelector("#jobs-search");
  if (searchInput) {
    searchInput.addEventListener("input", () => {
      jobsUiState.searchQuery = searchInput.value;
      renderJobsWorkspace(root);
    });
  }

  const statusFilter = root.querySelector("#jobs-status-filter");
  if (statusFilter) {
    statusFilter.addEventListener("change", () => {
      jobsUiState.statusFilter = statusFilter.value;
      renderJobsWorkspace(root);
    });
  }

  const sortSelect = root.querySelector("#jobs-sort");
  if (sortSelect) {
    sortSelect.addEventListener("change", () => {
      jobsUiState.sortKey = sortSelect.value;
      renderJobsWorkspace(root);
    });
  }

  root.querySelectorAll("[data-job-status-select]").forEach((select) => {
    select.addEventListener("change", async () => {
      const jobId = Number(select.dataset.jobStatusSelect);
      const nextStatus = select.value;
      const job = jobsUiState.jobs.find((item) => item.id === jobId);
      const previousStatus = job?.status;
      select.disabled = true;
      updateJobCardStatus(jobId, "Saving status...");
      try {
        const updatedJob = await updateJobStatus(jobId, nextStatus);
        if (job) {
          job.status = updatedJob.status;
        }
        updateJobCardStatus(jobId, "Status updated");
        renderJobsWorkspace(root);
      } catch (error) {
        if (job && previousStatus) {
          job.status = previousStatus;
        }
        updateJobCardStatus(jobId, "Status update failed", "error");
        showMessage(error.message);
        renderJobsWorkspace(root);
      }
    });
  });
}

async function runCheckAllJobs() {
  if (jobsUiState.batchRunActive) {
    return;
  }
  clearMessage();
  const batchRun = await startJobCheckBatch("all");
  applyBatchRunToUi(batchRun);
  refreshJobsPageActions();
  const root = document.getElementById("app");
  if (root) {
    ensureJobCheckBatchPolling(root);
    await pollJobCheckBatch(root, { silent: true });
  }
}

async function runCheckUnscoredJobs() {
  if (jobsUiState.batchRunActive) {
    return;
  }
  clearMessage();
  const batchRun = await startJobCheckBatch("unscored");
  applyBatchRunToUi(batchRun);
  refreshJobsPageActions();
  const root = document.getElementById("app");
  if (root) {
    ensureJobCheckBatchPolling(root);
    await pollJobCheckBatch(root, { silent: true });
  }
}

function refreshJobsPageActions() {
  const checkAllButton = document.getElementById("check-all-button");
  const checkUnscoredButton = document.getElementById("check-unscored-button");
  if (!checkAllButton || !checkUnscoredButton) {
    return;
  }

  const hasUnscoredJobs = jobsUiState.jobs.some((job) => !job.latest_candidate_compatibility_check);
  checkUnscoredButton.hidden = !hasUnscoredJobs;

  if (jobsUiState.batchRunActive) {
    checkAllButton.disabled = true;
    checkUnscoredButton.disabled = true;
    checkAllButton.textContent = jobsUiState.batchRun?.mode === "all" ? "Running..." : "Check All";
    checkUnscoredButton.textContent = jobsUiState.batchRun?.mode === "unscored" ? "Running..." : "Check Unscored";
    return;
  }

  checkAllButton.disabled = false;
  checkUnscoredButton.disabled = false;
  checkAllButton.textContent = "Check All";
  checkUnscoredButton.textContent = "Check Unscored";
}

function attachJobActions(root, jobId) {
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
  const job = await fetchJson(`/jobs/${jobId}`);
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
        ${createMetaRow("Status", getJobStatusLabel(job.status), { detail: true })}
        ${createMetaRow("Source", formatValue(job.source), { detail: true })}
        ${createMetaRow("External Job ID", formatValue(job.external_job_id), { detail: true })}
        ${createMetaRow("Page Title", formatValue(job.page_title), { detail: true })}
        ${createMetaRow("Tentative Job Title", formatValue(job.tentative_job_title), { detail: true })}
        ${createMetaRow("Source URL", job.source_url, { detail: true, href: job.source_url })}
        ${createMetaRow("Compatibility Score", job.latest_candidate_compatibility_check ? `${job.latest_candidate_compatibility_check.score}/100` : "Not checked", { detail: true })}
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
        ${
          snapshot
            ? `
              <div class="detail-row">
                <div class="detail-label">HTML</div>
                <div class="actions compact-actions">
                  <button id="toggle-html-button" class="button button-secondary" type="button">Show HTML</button>
                </div>
                <div id="html-block" hidden>
                  <pre class="text-block">${escapeHtml(formatValue(snapshot.html))}</pre>
                </div>
              </div>
            `
            : ""
        }
      </div>

      <h3 class="section-title">Candidate Compatibility</h3>
      <div class="detail-list">
        <p class="muted">This score uses Candidate Data directly and does not require generating a final CV first.</p>
        <div class="actions">
          <button id="check-button" class="button button-secondary" type="button">${job.latest_candidate_compatibility_check ? "Re-run Check" : "Run Check"}</button>
          <a class="button button-secondary" href="/candidate-profile/view">Open Candidate Data</a>
          <button id="delete-button" class="button button-danger">Delete</button>
          <a class="button button-primary" href="/">Back</a>
        </div>
      </div>

      <h3 class="section-title">Latest Result</h3>
      <section id="compatibility-result">
        ${renderCandidateCompatibilitySummary(job.latest_candidate_compatibility_check)}
      </section>
    </article>
  `;

  attachJobActions(root, jobId);
  const toggleHtmlButton = root.querySelector("#toggle-html-button");
  const htmlBlock = root.querySelector("#html-block");
  if (toggleHtmlButton && htmlBlock) {
    toggleHtmlButton.addEventListener("click", () => {
      const nextHidden = !htmlBlock.hidden;
      htmlBlock.hidden = nextHidden;
      toggleHtmlButton.textContent = nextHidden ? "Show HTML" : "Hide HTML";
    });
  }

  root.querySelector("#check-button").addEventListener("click", async (event) => {
    const button = event.currentTarget;
    if (!button || button.disabled) {
      return;
    }
    const idleLabel = job.latest_candidate_compatibility_check ? "Re-run Check" : "Run Check";
    button.disabled = true;
    button.textContent = "Running...";
    try {
      const response = await runCandidateCompatibilityCheck(jobId);
      root.querySelector("#compatibility-result").innerHTML = renderCandidateCompatibilitySummary(response.compatibility_check);
      showMessage("Compatibility check completed.");
    } catch (error) {
      showMessage(error.message);
    } finally {
      button.disabled = false;
      button.textContent = idleLabel;
    }
  });
}

function renderSectionForm(sectionKey, editingItem) {
  const config = masterSectionConfig[sectionKey];
  return `
    <form class="master-form" data-section-form="${sectionKey}">
      ${config.fields
        .map((field) => {
          const value = editingItem
            ? Array.isArray(editingItem[field.name])
              ? field.name === "technologies"
                ? editingItem[field.name].join(", ")
                : editingItem[field.name].join("\n")
              : editingItem[field.name] || ""
            : "";
          if (field.type === "textarea") {
            return `
              <div class="form-row">
                <label class="detail-label" for="${sectionKey}-${field.name}">${escapeHtml(field.label)}</label>
                <textarea id="${sectionKey}-${field.name}" name="${field.name}" class="input input-large" placeholder="${escapeHtml(field.placeholder || "")}">${escapeHtml(value)}</textarea>
              </div>
            `;
          }
          return `
            <div class="form-row">
              <label class="detail-label" for="${sectionKey}-${field.name}">${escapeHtml(field.label)}</label>
              <input id="${sectionKey}-${field.name}" name="${field.name}" class="input" type="${field.type}" value="${escapeHtml(value)}" placeholder="${escapeHtml(field.placeholder || "")}" ${field.required ? "required" : ""}>
            </div>
          `;
        })
        .join("")}
      <div class="actions">
        <button class="button button-primary" type="submit">${editingItem ? "Update" : "Add"} ${escapeHtml(config.label)}</button>
        ${editingItem ? `<button class="button button-secondary" type="button" data-cancel-section="${sectionKey}">Cancel</button>` : ""}
      </div>
    </form>
  `;
}

function renderMasterSection(sectionKey, items) {
  const config = masterSectionConfig[sectionKey];
  const editingId = resumeUiState.editing[sectionKey];
  const editingItem = items.find((item) => item.id === editingId) || null;

  return `
    <section class="panel master-section">
      <div class="section-header">
        <div>
          <h2>${escapeHtml(config.label)}</h2>
          <p class="muted">Structured entries stored for deterministic resume assembly.</p>
        </div>
      </div>
      ${renderSectionForm(sectionKey, editingItem)}
      <div class="collection-list">
        ${items.length === 0 ? `<p class="muted">No ${escapeHtml(config.label.toLowerCase())} yet.</p>` : ""}
        ${items
          .map(
            (item) => `
              <article class="collection-item">
                <div class="collection-copy">${config.renderItem(item)}</div>
                <div class="actions compact-actions">
                  <button class="button button-secondary" type="button" data-edit-section="${sectionKey}" data-item-id="${item.id}">Edit</button>
                  <button class="button button-danger" type="button" data-delete-section="${sectionKey}" data-item-id="${item.id}">Delete</button>
                </div>
              </article>
            `
          )
          .join("")}
      </div>
    </section>
  `;
}

function renderSelectionChecklist({ sectionKey, label, items, selectedIds, itemLabelBuilder, helperText = "" }) {
  return `
    <section class="selection-section">
      <div class="detail-label">${escapeHtml(label)}</div>
      ${helperText ? `<p class="muted">${escapeHtml(helperText)}</p>` : ""}
      <div class="checkbox-grid">
        ${
          items.length === 0
            ? `<p class="muted">No ${escapeHtml(label.toLowerCase())} available yet.</p>`
            : items
                .map(
                  (item) => `
                    <label class="checkbox-item">
                      <input type="checkbox" name="${sectionKey}" value="${item.id}" ${selectedIds.includes(item.id) ? "checked" : ""}>
                      <span>${escapeHtml(itemLabelBuilder(item))}</span>
                    </label>
                  `
                )
                .join("")
        }
      </div>
    </section>
  `;
}

function getProfileSection(profile, sectionKey) {
  return (profile.sections || []).find((section) => section.section_key === sectionKey) || null;
}

function parseGeneratedSkills(section) {
  if (!section?.generated_content) {
    return [];
  }
  return section.generated_content
    .split("\n")
    .map((line) => line.trim().replace(/^[-*]\s*/, ""))
    .filter(Boolean);
}

function renderSectionGenerationPanel(sectionKey, section, jobs, hasSavedProfile) {
  const isLoading = Boolean(resumeUiState.sectionGeneration[sectionKey]?.loading);
  const hasGeneratedContent = Boolean(section?.generated_content);
  const isBlockedByProfile = !hasSavedProfile;
  const buttonLabel = hasGeneratedContent
    ? `Regenerate ${sectionKey === "summary" ? "Summary" : "Skills"}`
    : `Generate ${sectionKey === "summary" ? "Summary" : "Skills"}`;

  let outputMarkup = `<p class="muted">No generated output yet.</p>`;
  if (sectionKey === "summary" && section?.generated_content) {
    outputMarkup = `<pre class="generated-output-block">${escapeHtml(section.generated_content)}</pre>`;
  }
  if (sectionKey === "skills") {
    const generatedSkills = parseGeneratedSkills(section);
    outputMarkup = generatedSkills.length
      ? `<ul class="generated-output-list">${generatedSkills.map((skill) => `<li>${escapeHtml(skill)}</li>`).join("")}</ul>`
      : `<p class="muted">No generated output yet.</p>`;
  }

  return `
    <div class="section-generation-panel">
      <div class="actions compact-actions">
        <button
          class="button button-secondary"
          type="button"
          data-generate-section="${sectionKey}"
          ${isLoading || jobs.length === 0 || isBlockedByProfile ? "disabled" : ""}
        >
          ${escapeHtml(buttonLabel)}
        </button>
        ${isLoading ? `<span class="generation-status">Generating...</span>` : ""}
      </div>
      ${isBlockedByProfile ? `<div class="message">Save or select a resume profile first.</div>` : ""}
      <div class="generated-output-card">
        <div class="detail-label">Generated ${escapeHtml(sectionKey === "summary" ? "Summary" : "Skills")}</div>
        ${outputMarkup}
      </div>
      ${
        jobs.length === 0
          ? `<p class="muted">Store a job first to enable OpenRouter generation.</p>`
          : ""
      }
    </div>
  `;
}

function getSelectedGenerationContext(root) {
  const profilePicker = root.querySelector("#profile-picker");
  const jobSelect = root.querySelector("#job-generation-select");
  const selectedProfileId = resumeUiState.selectedProfileId || null;
  const selectedJobId = jobSelect?.value
    ? Number(jobSelect.value)
    : (resumeUiState.selectedJobId || null);

  if (jobSelect?.value) {
    resumeUiState.selectedJobId = selectedJobId;
  }

  return { selectedProfileId, selectedJobId, jobSelect };
}

function getInstructionDraftValue(sectionKey, section) {
  return resumeUiState.instructionDrafts[sectionKey] ?? (
    section?.custom_instructions
    || resumeUiState.promptSettings?.[`${sectionKey}_prompt`]
    || defaultSectionInstructionPrompts[sectionKey]
    || ""
  );
}

function setInstructionDraftDefaults(profileDetail) {
  const sections = {
    summary: getProfileSection(profileDetail || { sections: [] }, "summary"),
    skills: getProfileSection(profileDetail || { sections: [] }, "skills"),
    experience: getProfileSection(profileDetail || { sections: [] }, "experience"),
    projects: getProfileSection(profileDetail || { sections: [] }, "projects"),
  };
  resumeUiState.instructionDrafts.profileId = profileDetail?.id || null;
  resumeUiState.instructionDrafts.summary = sections.summary?.custom_instructions || resumeUiState.promptSettings?.summary_prompt || defaultSectionInstructionPrompts.summary;
  resumeUiState.instructionDrafts.skills = sections.skills?.custom_instructions || resumeUiState.promptSettings?.skills_prompt || defaultSectionInstructionPrompts.skills;
  resumeUiState.instructionDrafts.experience = sections.experience?.custom_instructions || resumeUiState.promptSettings?.experience_prompt || defaultSectionInstructionPrompts.experience;
  resumeUiState.instructionDrafts.projects = sections.projects?.custom_instructions || resumeUiState.promptSettings?.projects_prompt || defaultSectionInstructionPrompts.projects;
  resumeUiState.profileInstructionOverrides.summary = sections.summary?.custom_instructions || null;
  resumeUiState.profileInstructionOverrides.skills = sections.skills?.custom_instructions || null;
  resumeUiState.profileInstructionOverrides.experience = sections.experience?.custom_instructions || null;
  resumeUiState.profileInstructionOverrides.projects = sections.projects?.custom_instructions || null;
}

function buildResumeProfilePayload(form) {
  const formData = new FormData(form);
  const sectionInstructions = {};
  for (const sectionKey of ["summary", "skills", "experience", "projects"]) {
    const value = resumeUiState.profileInstructionOverrides[sectionKey];
    if (typeof value === "string" && value.trim()) {
      sectionInstructions[sectionKey] = value;
    }
  }
  return {
    name: formData.get("name").trim(),
    headline: optionalValue(formData.get("headline")),
    summary: optionalValue(formData.get("summary")),
    selected_skill_ids: formData.getAll("selected_skill_ids").map(Number),
    selected_work_experience_ids: formData.getAll("selected_work_experience_ids").map(Number),
    selected_project_ids: formData.getAll("selected_project_ids").map(Number),
    selected_education_ids: formData.getAll("selected_education_ids").map(Number),
    selected_certification_ids: formData.getAll("selected_certification_ids").map(Number),
    selected_language_ids: formData.getAll("selected_language_ids").map(Number),
    section_instructions: sectionInstructions,
  };
}

async function saveResumeProfileForm(root) {
  const form = root.querySelector("#resume-profile-form");
  if (!form) {
    throw new Error("Resume profile form not found.");
  }
  const payload = buildResumeProfilePayload(form);
  if (payload.selected_skill_ids.length > 20) {
    throw new Error("A resume profile can include at most 20 skills.");
  }
  const savedProfile = await fetchJson(
    resumeUiState.selectedProfileId ? `/resume-profiles/${resumeUiState.selectedProfileId}` : "/resume-profiles",
    {
      method: resumeUiState.selectedProfileId ? "PUT" : "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }
  );
  resumeUiState.selectedProfileId = savedProfile.id;
  resumeUiState.instructionDrafts.profileId = savedProfile.id;
  resumeUiState.instructionDrafts.summary = payload.section_instructions.summary;
  resumeUiState.instructionDrafts.skills = payload.section_instructions.skills;
  resumeUiState.instructionDrafts.experience = payload.section_instructions.experience;
  resumeUiState.instructionDrafts.projects = payload.section_instructions.projects;
  return savedProfile;
}

async function rerenderResumeView(root) {
  const route = root.dataset.route || "";
  if (route === "candidate-data") {
    await renderCandidateDataPage(root);
    return;
  }
  await renderResumeProfilesPage(root);
}

async function handleSectionGenerationClick(root, profileDetail, sectionKey) {
  console.debug("[resume-builder] generation button clicked", { sectionKey });
  try {
    const { selectedProfileId, selectedJobId, jobSelect } = getSelectedGenerationContext(root);
    console.debug("[resume-builder] selected profile id", selectedProfileId);
    console.debug("[resume-builder] selected job id", selectedJobId);

    if (!selectedProfileId || !profileDetail) {
      const message = "Save the resume profile before generating sections.";
      console.debug("[resume-builder] generation blocked", { reason: message });
      showMessage(message);
      return;
    }

    if (!selectedJobId) {
      const message = "Select a job before generating sections.";
      console.debug("[resume-builder] generation blocked", { reason: message });
      if (jobSelect) {
        jobSelect.focus();
      }
      showMessage(message);
      return;
    }

    const route = sectionKey === "summary" ? "generate-summary" : "generate-skills";
    const requestPayload = {
      job_id: selectedJobId,
      resume_profile_id: selectedProfileId,
    };

    if (sectionKey === "summary") {
      console.debug("[resume-builder] saving current summary instructions before generation");
      await saveResumeProfileForm(root);
      requestPayload.resume_profile_id = resumeUiState.selectedProfileId;
    }

    const requestUrl = `/resume-profiles/${requestPayload.resume_profile_id}/${route}`;

    console.debug("[resume-builder] request URL", requestUrl);
    console.debug("[resume-builder] request payload", requestPayload);

    resumeUiState.sectionGeneration[sectionKey].loading = true;
    await renderResumeProfilesPage(root);

    try {
      const response = await fetchJson(requestUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(requestPayload),
      });
      console.debug("[resume-builder] fetch success", { sectionKey, response });
      showMessage(`${sectionKey === "summary" ? "Summary" : "Skills"} generated.`);
    } catch (error) {
      console.debug("[resume-builder] fetch failure", { sectionKey, error: error?.message || String(error) });
      throw error;
    } finally {
      resumeUiState.sectionGeneration[sectionKey].loading = false;
      await renderResumeProfilesPage(root);
    }
  } catch (error) {
    console.debug("[resume-builder] generation handler failure", { sectionKey, error: error?.message || String(error) });
    showMessage(error.message || `Failed to generate ${sectionKey}.`);
  }
}

function renderProfileSectionPreview(section) {
  if (!section) {
    return "";
  }

  return `
    <article class="section-preview-card">
      <div class="section-header">
        <div>
          <h3>${escapeHtml(section.label)}</h3>
          <p class="muted">Future OpenRouter runs should target this section independently.</p>
        </div>
      </div>
      <div class="detail-row">
        <div class="detail-label">Custom Instructions</div>
        <pre class="text-block">${escapeHtml(section.custom_instructions || "No section-specific instructions yet.")}</pre>
      </div>
      <div class="detail-row">
        <div class="detail-label">Source Material</div>
        <pre class="text-block">${escapeHtml(section.source_material || "No source material selected.")}</pre>
      </div>
      <div class="detail-row">
        <div class="detail-label">Generated Output</div>
        <pre class="text-block">${escapeHtml(section.generated_content || "Not generated yet.")}</pre>
      </div>
    </article>
  `;
}

function renderCandidateProfilePanel(candidateProfile) {
  return `
    <section class="panel profile-builder">
      <div class="section-header">
        <div>
          <h2>Candidate Profile</h2>
          <p class="muted">Master candidate summary used as source material. This is not final resume copy.</p>
        </div>
        <div class="actions compact-actions">
          <label class="button button-secondary import-button" for="cv-import-input">Import CV</label>
          <input id="cv-import-input" type="file" accept=".pdf,.docx" hidden>
        </div>
      </div>
      <form id="candidate-profile-form">
        <div class="form-row">
          <label class="detail-label" for="candidate-profile-summary">Candidate Summary / About Me Source</label>
          <textarea id="candidate-profile-summary" name="summary" class="input input-large" placeholder="Store long-term candidate summary notes here.">${escapeHtml(candidateProfile.summary || "")}</textarea>
        </div>
        <div class="actions">
          <button class="button button-secondary" type="submit">Save Candidate Profile</button>
        </div>
      </form>
    </section>
  `;
}

function renderSettingsApiPanel(settings, modelRegistry) {
  return `
    <section class="panel profile-builder">
      <div class="section-header">
        <div>
          <h2>OpenRouter API</h2>
          <p class="muted">Local-first API configuration. Secrets remain in local persistence.</p>
        </div>
      </div>
      <form id="settings-form">
        <div class="form-row">
          <label class="detail-label" for="settings-api-key">OpenRouter API Key</label>
          <input id="settings-api-key" name="api_key" class="input" type="password" placeholder="Enter a new API key to save or replace">
          <div class="muted">Current: ${escapeHtml(settings.masked_api_key || "Not configured")} (${escapeHtml(settings.api_key_source)})</div>
        </div>
        <div class="form-row">
          <label class="detail-label" for="settings-provider">Provider</label>
          <select id="settings-provider" name="provider" class="input">
            ${modelRegistry.providers.map((provider) => `<option value="${escapeHtml(provider)}" ${provider === settings.effective_provider ? "selected" : ""}>${escapeHtml(provider)}</option>`).join("")}
          </select>
        </div>
        <div class="form-row">
          <label class="detail-label" for="settings-default-model">Default OpenRouter Model</label>
          <select id="settings-default-model" name="default_model" class="input">
            <option value="">Use environment/default fallback</option>
            ${modelRegistry.models.map((model) => `<option value="${escapeHtml(model.model_id)}" ${model.model_id === (settings.saved_default_model || settings.effective_default_model) ? "selected" : ""}>${escapeHtml(model.label)} | API ID: ${escapeHtml(model.model_id)}</option>`).join("")}
          </select>
          <div class="muted">Current effective model API ID: ${escapeHtml(settings.effective_default_model || "Not configured")}</div>
          <div class="muted">The saved value must be the real OpenRouter API model id, not a display label.</div>
          <div class="muted">Model availability can change over time. Use Refresh Models to update the local registry.</div>
        </div>
        <div class="actions">
          <button id="refresh-models-button" class="button button-secondary" type="button">Refresh Models</button>
          <button class="button button-primary" type="submit">Save Settings</button>
        </div>
      </form>
      <div class="section-title">Available Models</div>
      <div class="muted">Last refreshed: ${escapeHtml(modelRegistry.updated_at || "Not refreshed yet")}</div>
      <div class="collection-list">
        ${modelRegistry.models.map((model) => `<article class="collection-item"><strong>${escapeHtml(model.label)}</strong><div class="muted">API ID: ${escapeHtml(model.model_id)}</div><div class="muted">${escapeHtml(model.provider)} | ${model.is_free ? "free" : "paid/unknown"} | ${escapeHtml(model.source)}</div></article>`).join("")}
      </div>
    </section>
  `;
}

function renderSettingsPromptsPanel() {
  return `
    <section class="panel profile-builder">
      <div class="section-header">
        <div>
          <h2>Prompt Settings</h2>
          <p class="muted">Edit default prompt instructions used for generation. Additional sections can be added here later.</p>
        </div>
      </div>
      <form id="settings-prompts-form">
        <div class="form-row">
          <label class="detail-label" for="settings-summary-prompt">Summary Prompt</label>
          <textarea id="settings-summary-prompt" name="summary_prompt" class="input input-large">${escapeHtml(resumeUiState.promptSettingsDrafts.summary ?? resumeUiState.promptSettings?.summary_prompt ?? defaultSectionInstructionPrompts.summary)}</textarea>
          <div class="actions compact-actions">
            <button id="settings-reset-summary-prompt" class="button button-secondary" type="button">Reset Summary Prompt</button>
          </div>
        </div>
        <div class="form-row">
          <label class="detail-label" for="settings-skills-prompt">Skills Prompt</label>
          <textarea id="settings-skills-prompt" name="skills_prompt" class="input">${escapeHtml(resumeUiState.promptSettingsDrafts.skills ?? resumeUiState.promptSettings?.skills_prompt ?? defaultSectionInstructionPrompts.skills)}</textarea>
          <div class="actions compact-actions">
            <button id="settings-reset-skills-prompt" class="button button-secondary" type="button">Reset Skills Prompt</button>
          </div>
        </div>
        <div class="form-row">
          <label class="detail-label" for="settings-experience-prompt">Experience Prompt</label>
          <textarea id="settings-experience-prompt" name="experience_prompt" class="input">${escapeHtml(resumeUiState.promptSettingsDrafts.experience ?? resumeUiState.promptSettings?.experience_prompt ?? defaultSectionInstructionPrompts.experience)}</textarea>
          <div class="actions compact-actions">
            <button id="settings-reset-experience-prompt" class="button button-secondary" type="button">Reset Experience Prompt</button>
          </div>
        </div>
        <div class="form-row">
          <label class="detail-label" for="settings-projects-prompt">Projects Prompt</label>
          <textarea id="settings-projects-prompt" name="projects_prompt" class="input">${escapeHtml(resumeUiState.promptSettingsDrafts.projects ?? resumeUiState.promptSettings?.projects_prompt ?? defaultSectionInstructionPrompts.projects)}</textarea>
          <div class="actions compact-actions">
            <button id="settings-reset-projects-prompt" class="button button-secondary" type="button">Reset Projects Prompt</button>
          </div>
        </div>
        <div class="actions">
          <button class="button button-primary" type="submit">Save Prompt Defaults</button>
        </div>
      </form>
    </section>
  `;
}

function renderSettingsPage(settings, modelRegistry) {
  const activeTab = resumeUiState.settingsTab || "api";
  return `
    <div class="settings-layout">
      <aside class="panel settings-sidebar">
        <div class="detail-label">Settings</div>
        <button class="button ${activeTab === "api" ? "button-primary" : "button-secondary"}" type="button" data-settings-tab="api">API</button>
        <button class="button ${activeTab === "prompts" ? "button-primary" : "button-secondary"}" type="button" data-settings-tab="prompts">Prompts</button>
      </aside>
      <div class="settings-content">
        ${activeTab === "api" ? renderSettingsApiPanel(settings, modelRegistry) : renderSettingsPromptsPanel()}
      </div>
    </div>
  `;
}

function renderImportObjectFields(items, fields, sectionName) {
  return `
    <div class="collection-list">
      ${items.length === 0 ? `<p class="muted">No ${escapeHtml(sectionName)} detected.</p>` : ""}
      ${items
        .map(
          (item, index) => `
            <article class="collection-item import-edit-card">
              ${fields
                .map((field) => {
                  const value = Array.isArray(item[field.name]) ? item[field.name].join("\n") : item[field.name] || "";
                  if (field.type === "textarea") {
                    return `
                      <div class="form-row">
                        <label class="detail-label">${escapeHtml(field.label)}</label>
                        <textarea class="input" data-import-section="${sectionName}" data-import-index="${index}" data-import-field="${field.name}">${escapeHtml(value)}</textarea>
                      </div>
                    `;
                  }
                  return `
                    <div class="form-row">
                      <label class="detail-label">${escapeHtml(field.label)}</label>
                      <input class="input" type="text" value="${escapeHtml(value)}" data-import-section="${sectionName}" data-import-index="${index}" data-import-field="${field.name}">
                    </div>
                  `;
                })
                .join("")}
              <div class="actions">
                <button class="button button-danger" type="button" data-remove-import-item="${sectionName}" data-remove-index="${index}">Remove</button>
              </div>
            </article>
          `
        )
        .join("")}
    </div>
  `;
}

function renderImportPreview(preview) {
  if (!preview) {
    return "";
  }

  return `
    <section class="panel profile-builder">
      <div class="section-header">
        <div>
          <h2>Import Preview</h2>
          <p class="muted">Parse first, review second, persist third. Nothing is saved until you confirm.</p>
        </div>
        <div class="actions compact-actions">
          <button id="clear-import-preview-button" class="button button-secondary" type="button">Clear Preview</button>
        </div>
      </div>
      ${preview.warnings.length ? `<div class="message">${preview.warnings.map(escapeHtml).join(" ")}</div>` : ""}
      ${preview.ambiguous_sections.length ? `<div class="message">Ambiguous sections: ${escapeHtml(preview.ambiguous_sections.join(", "))}</div>` : ""}
      <div class="form-row">
        <label class="detail-label" for="import-summary">Imported Summary / About Me</label>
        <textarea id="import-summary" class="input input-large" data-import-scalar="summary">${escapeHtml(preview.summary || "")}</textarea>
      </div>
      <div class="form-row">
        <label class="detail-label" for="import-skills">Imported Skills</label>
        <textarea id="import-skills" class="input input-large" data-import-skills>${escapeHtml((preview.skills || []).join("\n"))}</textarea>
      </div>
      <h3 class="section-title">Imported Work Experience</h3>
      ${renderImportObjectFields(preview.work_experiences || [], [
        { name: "company", label: "Company" },
        { name: "title", label: "Title" },
        { name: "location", label: "Location" },
        { name: "start_date", label: "Start Date" },
        { name: "end_date", label: "End Date" },
        { name: "summary", label: "Summary", type: "textarea" },
        { name: "highlights", label: "Highlights", type: "textarea" },
      ], "work_experiences")}
      <h3 class="section-title">Imported Projects</h3>
      ${renderImportObjectFields(preview.projects || [], [
        { name: "name", label: "Name" },
        { name: "role", label: "Role" },
        { name: "summary", label: "Summary", type: "textarea" },
        { name: "technologies", label: "Technologies", type: "textarea" },
        { name: "url", label: "URL" },
      ], "projects")}
      <h3 class="section-title">Imported Education</h3>
      ${renderImportObjectFields(preview.education || [], [
        { name: "institution", label: "Institution" },
        { name: "degree", label: "Degree" },
        { name: "field_of_study", label: "Field of Study" },
        { name: "start_date", label: "Start Date" },
        { name: "end_date", label: "End Date" },
        { name: "summary", label: "Summary", type: "textarea" },
      ], "education")}
      <h3 class="section-title">Imported Certifications</h3>
      ${renderImportObjectFields(preview.certifications || [], [
        { name: "name", label: "Name" },
        { name: "issuer", label: "Issuer" },
        { name: "issued_on", label: "Issued On" },
        { name: "credential_id", label: "Credential ID" },
        { name: "credential_url", label: "Credential URL" },
      ], "certifications")}
      <h3 class="section-title">Imported Languages</h3>
      ${renderImportObjectFields(preview.languages || [], [
        { name: "name", label: "Language" },
        { name: "proficiency", label: "Proficiency" },
      ], "languages")}
      <h3 class="section-title">Imported Links</h3>
      ${renderImportObjectFields(preview.links || [], [
        { name: "label", label: "Label" },
        { name: "url", label: "URL" },
        { name: "link_type", label: "Type" },
      ], "links")}
      <div class="detail-row">
        <div class="detail-label">Extracted Raw Text</div>
        <pre class="resume-preview">${escapeHtml(preview.raw_text || "")}</pre>
      </div>
      <div class="actions">
        <button id="confirm-import-button" class="button button-primary" type="button">Confirm Import</button>
      </div>
    </section>
  `;
}

function renderProfileBuilder(workspace, profileDetail, jobs) {
  const profile = profileDetail || {
    name: "",
    headline: "",
    summary: "",
    selected_skill_ids: [],
    selected_work_experience_ids: [],
    selected_project_ids: [],
    selected_education_ids: [],
    selected_certification_ids: [],
    selected_language_ids: [],
    content: "",
    sections: [],
  };

  const summarySection = getProfileSection(profile, "summary");
  const skillsSection = getProfileSection(profile, "skills");
  const experienceSection = getProfileSection(profile, "experience");
  const projectsSection = getProfileSection(profile, "projects");
  const educationSection = getProfileSection(profile, "education");
  const certificationsSection = getProfileSection(profile, "certifications");
  const languagesSection = getProfileSection(profile, "languages");
  const hasSavedProfile = Boolean(profileDetail?.id);

  return `
    <section class="panel profile-builder">
      <div class="section-header">
        <div>
          <h2>Resume Profile Builder</h2>
          <p class="muted">Create a reusable section-generation plan from candidate source data.</p>
        </div>
        <div class="actions compact-actions">
          <button id="new-profile-button" class="button button-secondary" type="button">Start New</button>
          ${
            profileDetail
              ? `<button id="delete-profile-button" class="button button-danger" type="button">Delete</button>`
              : ""
          }
        </div>
      </div>

      <div class="form-row">
        <label class="detail-label" for="profile-picker">Saved Resume Profiles</label>
        <select id="profile-picker" class="input">
          <option value="">New profile</option>
          ${workspace.resume_profiles
            .map(
              (item) => `<option value="${item.id}" ${item.id === resumeUiState.selectedProfileId ? "selected" : ""}>${escapeHtml(item.name)}</option>`
            )
            .join("")}
        </select>
      </div>

      <form id="resume-profile-form">
        <div class="form-row">
          <label class="detail-label" for="profile-name">Profile Name</label>
          <input id="profile-name" name="name" class="input" type="text" value="${escapeHtml(profile.name || "")}" placeholder="Backend - International Roles" required>
        </div>
        <div class="form-row">
          <label class="detail-label" for="profile-headline">Headline</label>
          <input id="profile-headline" name="headline" class="input" type="text" value="${escapeHtml(profile.headline || "")}" placeholder="Backend Engineer specializing in Python APIs">
        </div>
        <div class="form-row">
          <label class="detail-label" for="profile-summary">Candidate Positioning Notes</label>
          <textarea id="profile-summary" name="summary" class="input input-large" placeholder="Source guidance for future section generation, not final copy.">${escapeHtml(profile.summary || "")}</textarea>
        </div>
        <div class="form-row">
          <label class="detail-label" for="job-generation-select">Job For Section Generation</label>
          <select id="job-generation-select" class="input">
            ${renderJobOptions(jobs)}
          </select>
          <div class="muted">Generation actions use the selected job. Saving the profile does not depend on this field.</div>
        </div>
        <div class="muted">Prompt defaults are configured in Settings → Prompts.</div>
        ${renderSectionGenerationPanel("summary", summarySection, jobs, hasSavedProfile)}
        ${renderSelectionChecklist({
          sectionKey: "selected_skill_ids",
          label: "Skills",
          items: workspace.skills,
          selectedIds: profile.selected_skill_ids || [],
          itemLabelBuilder: (item) => item.proficiency_level ? `${item.name} (${item.proficiency_level})` : item.name,
          helperText: "Select up to 20 skills.",
        })}
        ${renderSectionGenerationPanel("skills", skillsSection, jobs, hasSavedProfile)}
        ${renderSelectionChecklist({
          sectionKey: "selected_work_experience_ids",
          label: "Work Experience",
          items: workspace.work_experiences,
          selectedIds: profile.selected_work_experience_ids || [],
          itemLabelBuilder: (item) => `${item.title} | ${item.company}`,
        })}
        ${renderSelectionChecklist({
          sectionKey: "selected_project_ids",
          label: "Projects",
          items: workspace.projects,
          selectedIds: profile.selected_project_ids || [],
          itemLabelBuilder: (item) => item.name,
        })}
        ${renderSelectionChecklist({
          sectionKey: "selected_education_ids",
          label: "Education",
          items: workspace.education,
          selectedIds: profile.selected_education_ids || [],
          itemLabelBuilder: (item) => `${item.degree} | ${item.institution}`,
        })}
        ${renderSelectionChecklist({
          sectionKey: "selected_certification_ids",
          label: "Certifications",
          items: workspace.certifications,
          selectedIds: profile.selected_certification_ids || [],
          itemLabelBuilder: (item) => `${item.name} | ${item.issuer}`,
        })}
        ${renderSelectionChecklist({
          sectionKey: "selected_language_ids",
          label: "Languages",
          items: workspace.languages,
          selectedIds: profile.selected_language_ids || [],
          itemLabelBuilder: (item) => `${item.name} (${item.proficiency})`,
        })}

        <div class="actions">
          <button class="button button-primary" type="submit">${profileDetail ? "Save Profile" : "Create Profile"}</button>
        </div>
      </form>

      <div class="preview-card">
        <div class="section-title">Section Preview</div>
        <p class="muted">This preview shows section-by-section source material and any future generated outputs independently.</p>
        ${renderProfileSectionPreview(summarySection)}
        ${renderProfileSectionPreview(skillsSection)}
        ${renderProfileSectionPreview(experienceSection)}
        ${renderProfileSectionPreview(projectsSection)}
        ${renderProfileSectionPreview(educationSection)}
        ${renderProfileSectionPreview(certificationsSection)}
        ${renderProfileSectionPreview(languagesSection)}
        <div class="detail-row">
          <div class="detail-label">Combined Text For Compatibility</div>
          <pre class="resume-preview">${escapeHtml(profile.content || "Save the profile to build the combined compatibility text.")}</pre>
        </div>
      </div>
    </section>
  `;
}

async function renderResumeProfilesPage(root) {
  const [workspace, jobs, promptSettings] = await Promise.all([
    fetchJson("/resume-profiles/workspace"),
    fetchJson("/jobs"),
    fetchJson("/settings/prompts"),
  ]);
  resumeUiState.promptSettings = promptSettings;
  if (!resumeUiState.selectedProfileId && workspace.resume_profiles.length > 0) {
    resumeUiState.selectedProfileId = workspace.resume_profiles[0].id;
  }
  if (
    resumeUiState.selectedJobId &&
    !(jobs || []).some((job) => job.id === resumeUiState.selectedJobId)
  ) {
    resumeUiState.selectedJobId = null;
  }
  if (
    resumeUiState.selectedProfileId &&
    !workspace.resume_profiles.some((profile) => profile.id === resumeUiState.selectedProfileId)
  ) {
    resumeUiState.selectedProfileId = workspace.resume_profiles[0]?.id || null;
  }

  const profileDetail = resumeUiState.selectedProfileId
    ? await fetchJson(`/resume-profiles/${resumeUiState.selectedProfileId}`)
    : null;
  if (resumeUiState.instructionDrafts.profileId !== (profileDetail?.id || null)) {
    setInstructionDraftDefaults(profileDetail);
  }

  root.innerHTML = `
    <div class="resume-layout">
      <div class="resume-profile-column">
        ${renderProfileBuilder(workspace, profileDetail, jobs || [])}
      </div>
    </div>
  `;

  attachResumePageHandlers(root, profileDetail);
}

async function renderCandidateDataPage(root) {
  const [workspace, promptSettings] = await Promise.all([
    fetchJson("/resume-profiles/workspace"),
    fetchJson("/settings/prompts"),
  ]);
  resumeUiState.promptSettings = promptSettings;
  root.innerHTML = `
    <div class="resume-layout">
      ${renderImportPreview(resumeUiState.importPreview)}
      ${renderCandidateProfilePanel(workspace.candidate_profile)}
      <div class="resume-master-grid">
        ${renderMasterSection("skills", workspace.skills)}
        ${renderMasterSection("workExperiences", workspace.work_experiences)}
        ${renderMasterSection("projects", workspace.projects)}
        ${renderMasterSection("education", workspace.education)}
        ${renderMasterSection("certifications", workspace.certifications)}
        ${renderMasterSection("languages", workspace.languages)}
        ${renderMasterSection("links", workspace.links)}
      </div>
    </div>
  `;

  attachResumePageHandlers(root, null);
}

async function renderSettingsView(root, selectedProvider = null) {
  const [settings, promptSettings] = await Promise.all([
    fetchJson("/settings/openrouter"),
    fetchJson("/settings/prompts"),
  ]);
  resumeUiState.promptSettings = promptSettings;
  resumeUiState.promptSettingsDrafts.summary = promptSettings.summary_prompt ?? defaultSectionInstructionPrompts.summary;
  resumeUiState.promptSettingsDrafts.skills = promptSettings.skills_prompt ?? defaultSectionInstructionPrompts.skills;
  resumeUiState.promptSettingsDrafts.experience = promptSettings.experience_prompt ?? defaultSectionInstructionPrompts.experience;
  resumeUiState.promptSettingsDrafts.projects = promptSettings.projects_prompt ?? defaultSectionInstructionPrompts.projects;
  const activeProvider = selectedProvider || settings.effective_provider || "openrouter";
  const modelRegistry = await fetchJson(`/settings/models?provider=${encodeURIComponent(activeProvider)}`);
  root.innerHTML = renderSettingsPage(
    {
      ...settings,
      effective_provider: activeProvider,
      saved_provider: settings.saved_provider || activeProvider,
    },
    modelRegistry,
  );

  root.querySelectorAll("[data-settings-tab]").forEach((button) => {
    button.addEventListener("click", async () => {
      resumeUiState.settingsTab = button.dataset.settingsTab;
      await renderSettingsView(root, activeProvider);
    });
  });

  const settingsProvider = root.querySelector("#settings-provider");
  if (settingsProvider) {
    settingsProvider.addEventListener("change", async (event) => {
      if (event.currentTarget) {
        const nextProvider = event.currentTarget.value;
        await renderSettingsView(root, nextProvider);
      }
    });
  }

  const refreshModelsButton = root.querySelector("#refresh-models-button");
  if (refreshModelsButton) {
    refreshModelsButton.addEventListener("click", async () => {
      try {
        await fetchJson("/settings/models/refresh", { method: "POST" });
        await renderSettingsView(root);
        showMessage("Model registry refreshed.");
      } catch (error) {
        showMessage(error.message);
      }
    });
  }

  const settingsForm = root.querySelector("#settings-form");
  if (settingsForm) {
    settingsForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      const formData = new FormData(event.currentTarget);
      try {
        await fetchJson("/settings/openrouter", {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            api_key: optionalValue(formData.get("api_key")),
            provider: String(formData.get("provider") || ""),
            default_model: String(formData.get("default_model") || ""),
          }),
        });
        await renderSettingsView(root);
        showMessage("Settings saved.");
      } catch (error) {
        showMessage(error.message);
      }
    });
  }

  const promptsForm = root.querySelector("#settings-prompts-form");
  if (promptsForm) {
    const summaryPrompt = root.querySelector("#settings-summary-prompt");
    const skillsPrompt = root.querySelector("#settings-skills-prompt");
    const experiencePrompt = root.querySelector("#settings-experience-prompt");
    const projectsPrompt = root.querySelector("#settings-projects-prompt");
    if (summaryPrompt) {
      summaryPrompt.addEventListener("input", () => {
        resumeUiState.promptSettingsDrafts.summary = summaryPrompt.value;
      });
    }
    if (skillsPrompt) {
      skillsPrompt.addEventListener("input", () => {
        resumeUiState.promptSettingsDrafts.skills = skillsPrompt.value;
      });
    }
    if (experiencePrompt) {
      experiencePrompt.addEventListener("input", () => {
        resumeUiState.promptSettingsDrafts.experience = experiencePrompt.value;
      });
    }
    if (projectsPrompt) {
      projectsPrompt.addEventListener("input", () => {
        resumeUiState.promptSettingsDrafts.projects = projectsPrompt.value;
      });
    }

    const resetSummaryPrompt = root.querySelector("#settings-reset-summary-prompt");
    if (resetSummaryPrompt && summaryPrompt) {
      resetSummaryPrompt.addEventListener("click", () => {
        resumeUiState.promptSettingsDrafts.summary = defaultSectionInstructionPrompts.summary;
        summaryPrompt.value = defaultSectionInstructionPrompts.summary;
        showMessage("Summary prompt reset to the built-in default. Save Prompt Defaults to persist it.");
      });
    }

    const resetSkillsPrompt = root.querySelector("#settings-reset-skills-prompt");
    if (resetSkillsPrompt && skillsPrompt) {
      resetSkillsPrompt.addEventListener("click", () => {
        resumeUiState.promptSettingsDrafts.skills = defaultSectionInstructionPrompts.skills;
        skillsPrompt.value = defaultSectionInstructionPrompts.skills;
        showMessage("Skills prompt reset to the built-in default. Save Prompt Defaults to persist it.");
      });
    }

    const resetExperiencePrompt = root.querySelector("#settings-reset-experience-prompt");
    if (resetExperiencePrompt && experiencePrompt) {
      resetExperiencePrompt.addEventListener("click", () => {
        resumeUiState.promptSettingsDrafts.experience = defaultSectionInstructionPrompts.experience;
        experiencePrompt.value = defaultSectionInstructionPrompts.experience;
        showMessage("Experience prompt reset to the built-in default. Save Prompt Defaults to persist it.");
      });
    }

    const resetProjectsPrompt = root.querySelector("#settings-reset-projects-prompt");
    if (resetProjectsPrompt && projectsPrompt) {
      resetProjectsPrompt.addEventListener("click", () => {
        resumeUiState.promptSettingsDrafts.projects = defaultSectionInstructionPrompts.projects;
        projectsPrompt.value = defaultSectionInstructionPrompts.projects;
        showMessage("Projects prompt reset to the built-in default. Save Prompt Defaults to persist it.");
      });
    }

    promptsForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      try {
        const formData = new FormData(event.currentTarget);
        const savedPrompts = await fetchJson("/settings/prompts", {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            summary_prompt: optionalValue(formData.get("summary_prompt")),
            skills_prompt: optionalValue(formData.get("skills_prompt")),
            experience_prompt: optionalValue(formData.get("experience_prompt")),
            projects_prompt: optionalValue(formData.get("projects_prompt")),
          }),
        });
        resumeUiState.promptSettings = savedPrompts;
        resumeUiState.promptSettingsDrafts.summary = savedPrompts.summary_prompt ?? defaultSectionInstructionPrompts.summary;
        resumeUiState.promptSettingsDrafts.skills = savedPrompts.skills_prompt ?? defaultSectionInstructionPrompts.skills;
        resumeUiState.promptSettingsDrafts.experience = savedPrompts.experience_prompt ?? defaultSectionInstructionPrompts.experience;
        resumeUiState.promptSettingsDrafts.projects = savedPrompts.projects_prompt ?? defaultSectionInstructionPrompts.projects;
        showMessage("Prompt defaults saved.");
      } catch (error) {
        showMessage(error.message);
      }
    });
  }
}

function attachResumePageHandlers(root, profileDetail) {
  const generationButtons = root.querySelectorAll("[data-generate-section]");
  console.debug("[resume-builder] binding generation buttons", { count: generationButtons.length });

  const jobGenerationSelect = root.querySelector("#job-generation-select");
  if (jobGenerationSelect) {
    jobGenerationSelect.value = resumeUiState.selectedJobId ? String(resumeUiState.selectedJobId) : "";
    jobGenerationSelect.addEventListener("change", () => {
      resumeUiState.selectedJobId = jobGenerationSelect.value ? Number(jobGenerationSelect.value) : null;
      console.debug("[resume-builder] selected job changed", { selectedJobId: resumeUiState.selectedJobId });
    });
  }

  const candidateProfileForm = root.querySelector("#candidate-profile-form");
  if (candidateProfileForm) {
    candidateProfileForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      try {
        const formData = new FormData(candidateProfileForm);
        await fetchJson("/candidate-profile", {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ summary: optionalValue(formData.get("summary")) }),
        });
        await rerenderResumeView(root);
        showMessage("Candidate profile updated.");
      } catch (error) {
        showMessage(error.message);
      }
    });
  }

  root.querySelectorAll("[data-edit-section]").forEach((button) => {
    button.addEventListener("click", () => {
      resumeUiState.editing[button.dataset.editSection] = Number(button.dataset.itemId);
      rerenderResumeView(root).catch(handleUiError);
    });
  });

  root.querySelectorAll("[data-cancel-section]").forEach((button) => {
    button.addEventListener("click", () => {
      resumeUiState.editing[button.dataset.cancelSection] = null;
      rerenderResumeView(root).catch(handleUiError);
    });
  });

  root.querySelectorAll("[data-delete-section]").forEach((button) => {
    button.addEventListener("click", async () => {
      try {
        const sectionKey = button.dataset.deleteSection;
        const config = masterSectionConfig[sectionKey];
        await deleteResource(`${config.endpoint}/${button.dataset.itemId}`);
        resumeUiState.editing[sectionKey] = null;
        await rerenderResumeView(root);
        showMessage(`${config.label} deleted.`);
      } catch (error) {
        showMessage(error.message);
      }
    });
  });

  root.querySelectorAll("[data-section-form]").forEach((form) => {
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const sectionKey = form.dataset.sectionForm;
      const config = masterSectionConfig[sectionKey];
      const payload = config.toPayload(new FormData(form));
      try {
        const editingId = resumeUiState.editing[sectionKey];
        await fetchJson(editingId ? `${config.endpoint}/${editingId}` : config.endpoint, {
          method: editingId ? "PUT" : "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        resumeUiState.editing[sectionKey] = null;
        await rerenderResumeView(root);
        showMessage(`${config.label} saved.`);
      } catch (error) {
        showMessage(error.message);
      }
    });
  });

  const profilePicker = root.querySelector("#profile-picker");
  if (profilePicker) {
    profilePicker.addEventListener("change", async () => {
      resumeUiState.selectedProfileId = profilePicker.value ? Number(profilePicker.value) : null;
      resumeUiState.instructionDrafts.profileId = null;
      resumeUiState.instructionDrafts.summary = null;
      resumeUiState.instructionDrafts.skills = null;
      resumeUiState.instructionDrafts.experience = null;
      resumeUiState.instructionDrafts.projects = null;
      await rerenderResumeView(root);
    });
  }

  const newProfileButton = root.querySelector("#new-profile-button");
  if (newProfileButton) {
    newProfileButton.addEventListener("click", async () => {
      resumeUiState.selectedProfileId = null;
      setInstructionDraftDefaults(null);
      await rerenderResumeView(root);
    });
  }

  const importInput = root.querySelector("#cv-import-input");
  if (importInput) {
    importInput.addEventListener("change", async () => {
      const file = importInput.files && importInput.files[0];
      if (!file) {
        return;
      }
      try {
        const contentBase64 = await fileToBase64(file);
        resumeUiState.importPreview = await fetchJson("/resume-import/parse", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            filename: file.name,
            content_base64: contentBase64,
          }),
        });
        await rerenderResumeView(root);
        showMessage("Resume parsed. Review the preview before confirming import.");
      } catch (error) {
        showMessage(error.message);
      } finally {
        importInput.value = "";
      }
    });
  }

  const clearImportButton = root.querySelector("#clear-import-preview-button");
  if (clearImportButton) {
    clearImportButton.addEventListener("click", async () => {
      resumeUiState.importPreview = null;
      await rerenderResumeView(root);
    });
  }

  const importSummary = root.querySelector("[data-import-scalar='summary']");
  if (importSummary) {
    importSummary.addEventListener("input", () => {
      resumeUiState.importPreview.summary = importSummary.value.trim() || null;
    });
  }

  const importSkills = root.querySelector("[data-import-skills]");
  if (importSkills) {
    importSkills.addEventListener("input", () => {
      resumeUiState.importPreview.skills = linesValue(importSkills.value);
    });
  }

  root.querySelectorAll("[data-import-field]").forEach((input) => {
    input.addEventListener("input", () => {
      const section = input.dataset.importSection;
      const index = Number(input.dataset.importIndex);
      const field = input.dataset.importField;
      const value = input.value;
      if (!resumeUiState.importPreview || !resumeUiState.importPreview[section]?.[index]) {
        return;
      }
      resumeUiState.importPreview[section][index][field] = ["highlights", "technologies"].includes(field)
        ? linesValue(value)
        : (value.trim() || null);
      if (["company", "title", "name", "institution", "degree", "issuer", "proficiency", "url", "label"].includes(field)) {
        resumeUiState.importPreview[section][index][field] = value.trim();
      }
    });
  });

  root.querySelectorAll("[data-remove-import-item]").forEach((button) => {
    button.addEventListener("click", async () => {
      const section = button.dataset.removeImportItem;
      const index = Number(button.dataset.removeIndex);
      if (!resumeUiState.importPreview || !Array.isArray(resumeUiState.importPreview[section])) {
        return;
      }
      resumeUiState.importPreview[section].splice(index, 1);
      await rerenderResumeView(root);
    });
  });

  const confirmImportButton = root.querySelector("#confirm-import-button");
  if (confirmImportButton) {
    confirmImportButton.addEventListener("click", async () => {
      try {
        await fetchJson("/resume-import/confirm", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            summary: resumeUiState.importPreview.summary,
            skills: resumeUiState.importPreview.skills || [],
            work_experiences: resumeUiState.importPreview.work_experiences || [],
            projects: resumeUiState.importPreview.projects || [],
            education: resumeUiState.importPreview.education || [],
            certifications: resumeUiState.importPreview.certifications || [],
            languages: resumeUiState.importPreview.languages || [],
            links: resumeUiState.importPreview.links || [],
          }),
        });
        resumeUiState.importPreview = null;
        await rerenderResumeView(root);
        showMessage("Imported resume data saved into the candidate profile database.");
      } catch (error) {
        showMessage(error.message);
      }
    });
  }

  const deleteProfileButton = root.querySelector("#delete-profile-button");
  if (deleteProfileButton) {
    deleteProfileButton.addEventListener("click", async () => {
      try {
        await deleteResource(`/resume-profiles/${resumeUiState.selectedProfileId}`);
        resumeUiState.selectedProfileId = null;
        setInstructionDraftDefaults(null);
        await rerenderResumeView(root);
        showMessage("Resume profile deleted.");
      } catch (error) {
        showMessage(error.message);
      }
    });
  }

  const resumeProfileForm = root.querySelector("#resume-profile-form");
  if (resumeProfileForm) {
    resumeProfileForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      try {
        await saveResumeProfileForm(root);
        await rerenderResumeView(root);
        showMessage("Resume profile saved.");
      } catch (error) {
        showMessage(error.message);
      }
    });
  }

  generationButtons.forEach((button) => {
    button.addEventListener("click", async () => {
      await handleSectionGenerationClick(root, profileDetail, button.dataset.generateSection);
    });
  });
}

function handleUiError(error) {
  showMessage(error.message || "Something went wrong while loading the page.");
}

async function init() {
  clearMessage();
  const root = document.getElementById("app");
  const route = root.dataset.route || "jobs";
  const checkAllButton = document.getElementById("check-all-button");
  const checkUnscoredButton = document.getElementById("check-unscored-button");

  if (route.startsWith("job:")) {
    stopJobsBatchPolling();
    checkAllButton.hidden = true;
    checkUnscoredButton.hidden = true;
    const jobId = route.split(":")[1];
    await renderJobDetails(root, jobId);
    return;
  }

  if (route === "resume-profiles") {
    stopJobsBatchPolling();
    checkAllButton.hidden = true;
    checkUnscoredButton.hidden = true;
    await renderResumeProfilesPage(root);
    return;
  }

  if (route === "candidate-data") {
    stopJobsBatchPolling();
    checkAllButton.hidden = true;
    checkUnscoredButton.hidden = true;
    await renderCandidateDataPage(root);
    return;
  }

  if (route === "profile-builder") {
    stopJobsBatchPolling();
    checkAllButton.hidden = true;
    checkUnscoredButton.hidden = true;
    await renderResumeProfilesPage(root);
    return;
  }

  if (route === "settings") {
    stopJobsBatchPolling();
    checkAllButton.hidden = true;
    checkUnscoredButton.hidden = true;
    await renderSettingsView(root);
    return;
  }

  checkAllButton.hidden = false;
  checkUnscoredButton.hidden = false;
  if (!document.getElementById("check-all-status")) {
    checkAllButton.insertAdjacentHTML("afterend", '<span id="check-all-status" class="check-all-status muted" hidden></span>');
  }
  checkAllButton.addEventListener("click", async () => {
    await runCheckAllJobs();
  });
  checkUnscoredButton.addEventListener("click", async () => {
    await runCheckUnscoredJobs();
  });
  await loadAndRenderJobsWorkspace(root);
}

init().catch(handleUiError);
