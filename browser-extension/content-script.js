(function () {
  const BLOCKED_SELECTOR = "script, style, noscript, template";
  const LOCATION_LABELS = /location|locations|based in|job location/i;
  const COMPANY_LABELS = /company|employer|organization|organisation/i;
  const LINKEDIN_JOB_TARGET_SELECTOR = [
    "a[href*='/jobs/view/']",
    "a[href*='currentJobId=']",
    "[data-job-id]",
    "[data-occludable-job-id]",
    "[data-entity-urn*='jobPosting']",
  ].join(", ");
  const LINKEDIN_DEBUG_PREFIX = "[Job Assist][LinkedIn Rail]";
  const INVALID_EXTENSION_RESOURCE_URL = /^chrome-extension:\/\/invalid(?:\/|$)/i;
  let linkedInDebugRail = null;
  let linkedInDebugRailStyles = null;
  let invalidExtensionResourceNoMatchLogged = false;
  const loggedInvalidExtensionResourceReferences = new Set();

  function collapseWhitespace(value) {
    return value.replace(/\s+/g, " ").trim();
  }

  function unique(values) {
    return Array.from(new Set(values));
  }

  function detectSourceType(url) {
    try {
      const host = new URL(url).hostname.toLowerCase();
      if (host.includes("linkedin.com")) {
        return "linkedin";
      }
      if (host.includes("greenhouse.io")) {
        return "greenhouse";
      }
      if (host.includes("lever.co")) {
        return "lever";
      }
      if (host.includes("myworkdayjobs.com") || host.includes("workday.com")) {
        return "workday";
      }
    } catch (_error) {
      return "generic";
    }
    return "generic";
  }

  function normalizedVisibleText(root = document.documentElement) {
    const clone = root.cloneNode(true);
    clone.querySelectorAll(BLOCKED_SELECTOR).forEach((node) => node.remove());
    return collapseWhitespace(clone.textContent || "");
  }

  function firstContent(values) {
    for (const value of values) {
      const normalized = collapseWhitespace(value || "");
      if (normalized) {
        return normalized;
      }
    }
    return null;
  }

  function getMetaContent(name, attribute = "property") {
    const element = document.querySelector(`meta[${attribute}="${name}"]`);
    return element ? element.getAttribute("content") : null;
  }

  function candidateText(selector) {
    return Array.from(document.querySelectorAll(selector))
      .map((node) => collapseWhitespace(node.textContent || ""))
      .filter(Boolean);
  }

  function scopedCandidateText(root, selector) {
    if (!root) {
      return [];
    }
    return Array.from(root.querySelectorAll(selector))
      .map((node) => collapseWhitespace(node.textContent || ""))
      .filter(Boolean);
  }

  function firstContentFromRoot(root, selectors) {
    return firstContent(selectors.flatMap((selector) => scopedCandidateText(root, selector)));
  }

  function detectLinkedInCompany() {
    return firstContent([
      ...candidateText(".job-details-jobs-unified-top-card__company-name"),
      ...candidateText(".topcard__org-name-link"),
    ]);
  }

  function detectLinkedInLocation() {
    return firstContent([
      ...candidateText(".job-details-jobs-unified-top-card__primary-description-container"),
      ...candidateText(".topcard__flavor--bullet"),
    ]);
  }

  function detectLinkedInCompanyFromRoot(root) {
    return firstContentFromRoot(root, [
      ".job-details-jobs-unified-top-card__company-name",
      ".topcard__org-name-link",
      ".job-details-jobs-unified-top-card__primary-description a",
    ]);
  }

  function detectLinkedInLocationFromRoot(root) {
    return firstContentFromRoot(root, [
      ".job-details-jobs-unified-top-card__primary-description-container",
      ".job-details-jobs-unified-top-card__primary-description",
      ".topcard__flavor--bullet",
      ".jobs-unified-top-card__subtitle-primary-grouping",
    ]);
  }

  function parseLinkedInJobIdFromUrl(url) {
    if (!url) {
      return null;
    }

    try {
      const parsed = new URL(url, window.location.href);
      const pathnameMatch = parsed.pathname.match(/\/jobs\/view\/(\d+)/);
      if (pathnameMatch) {
        return pathnameMatch[1];
      }
      return parsed.searchParams.get("currentJobId");
    } catch (_error) {
      const directMatch = String(url).match(/\/jobs\/view\/(\d+)/);
      return directMatch ? directMatch[1] : null;
    }
  }

  function getLinkedInJobIdFromCurrentUrl() {
    return parseLinkedInJobIdFromUrl(window.location.href);
  }

  function buildLinkedInCanonicalJobUrl(jobId) {
    return jobId ? `https://www.linkedin.com/jobs/view/${jobId}/` : window.location.href;
  }

  function detectLinkedInJobId(root = document) {
    const selectors = [
      "[data-job-id]",
      "[data-entity-urn*='fsd_jobPosting:']",
      "a[href*='/jobs/view/']",
    ];
    for (const selector of selectors) {
      const element = root.querySelector(selector);
      if (!element) {
        continue;
      }

      const attributeId =
        element.getAttribute("data-job-id") ||
        parseLinkedInJobIdFromUrl(element.getAttribute("href")) ||
        parseLinkedInJobIdFromUrl(element.getAttribute("data-job-url"));
      if (attributeId) {
        return attributeId;
      }

      const urn = element.getAttribute("data-entity-urn") || "";
      const urnMatch = urn.match(/fsd_jobPosting:(\d+)/);
      if (urnMatch) {
        return urnMatch[1];
      }
    }

    return getLinkedInJobIdFromCurrentUrl();
  }

  function detectGreenhouseCompany() {
    return firstContent([
      ...candidateText("#header .company-name"),
      ...candidateText(".company-name"),
    ]);
  }

  function detectGreenhouseLocation() {
    return firstContent(candidateText(".location"));
  }

  function detectLeverCompany() {
    return firstContent([
      ...candidateText(".main-header-text"),
      ...candidateText("[data-qa='company-name']"),
    ]);
  }

  function detectLeverLocation() {
    return firstContent(candidateText(".posting-categories .location, .location"));
  }

  function detectWorkdayLocation() {
    return firstContent(candidateText('[data-automation-id="locations"]'));
  }

  function detectCompany(sourceType) {
    if (sourceType === "linkedin") {
      return detectLinkedInCompany();
    }
    if (sourceType === "greenhouse") {
      return detectGreenhouseCompany();
    }
    if (sourceType === "lever") {
      return detectLeverCompany();
    }

    return firstContent([
      getMetaContent("og:site_name"),
      getMetaContent("twitter:site", "name"),
      ...candidateText("[data-company], [data-qa='company-name'], .company, .company-name"),
    ]);
  }

  function detectLocation(sourceType) {
    if (sourceType === "linkedin") {
      return detectLinkedInLocation();
    }
    if (sourceType === "greenhouse") {
      return detectGreenhouseLocation();
    }
    if (sourceType === "lever") {
      return detectLeverLocation();
    }
    if (sourceType === "workday") {
      return detectWorkdayLocation();
    }

    return firstContent([
      ...candidateText("[data-location], [data-qa='location'], .location"),
    ]);
  }

  function detectLabeledValue(pattern) {
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    while (walker.nextNode()) {
      const text = collapseWhitespace(walker.currentNode.textContent || "");
      if (!text || !pattern.test(text)) {
        continue;
      }

      const nearby = collapseWhitespace(walker.currentNode.parentElement?.textContent || "");
      if (!nearby) {
        continue;
      }
      const parts = nearby.split(/:|\n/).map((part) => collapseWhitespace(part)).filter(Boolean);
      if (parts.length >= 2) {
        return parts[1];
      }
    }
    return null;
  }

  function detectLabeledValueInRoot(root, pattern) {
    if (!root) {
      return null;
    }

    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    while (walker.nextNode()) {
      const text = collapseWhitespace(walker.currentNode.textContent || "");
      if (!text || !pattern.test(text)) {
        continue;
      }

      const nearby = collapseWhitespace(walker.currentNode.parentElement?.textContent || "");
      if (!nearby) {
        continue;
      }
      const parts = nearby.split(/:|\n/).map((part) => collapseWhitespace(part)).filter(Boolean);
      if (parts.length >= 2) {
        return parts[1];
      }
    }

    return null;
  }

  function getLinkedInPageKind() {
    const { pathname, searchParams } = new URL(window.location.href);
    if (/^\/jobs\/view\//.test(pathname)) {
      return "detail";
    }
    if (
      /^\/jobs\/(search|collections)\//.test(pathname) ||
      /^\/jobs\/search-results\//.test(pathname) ||
      pathname === "/jobs/" ||
      searchParams.has("currentJobId")
    ) {
      return "listing";
    }
    return "unknown";
  }

  function findLinkedInDetailRoot() {
    const selectors = [
      ".jobs-search__job-details--container",
      ".jobs-details",
      ".job-view-layout",
      ".job-details-jobs-unified-top-card__container--two-pane",
      ".job-details-jobs-unified-top-card",
      ".job-view-container",
      "main .scaffold-layout__detail",
    ];

    for (const selector of selectors) {
      const root = document.querySelector(selector);
      if (!root) {
        continue;
      }

      const title = firstContentFromRoot(root, [
        ".job-details-jobs-unified-top-card__job-title",
        ".t-24.job-details-jobs-unified-top-card__job-title",
        "h1",
      ]);
      if (title) {
        return root;
      }
    }

    return null;
  }

  function distinctLinkedInJobCardTitles(root) {
    const selectors = [
      ".job-card-list__title",
      ".job-card-container__link",
      ".job-card-container__primary-description",
      "a[href*='/jobs/view/']",
      "[data-job-id] a",
    ];

    const values = selectors.flatMap((selector) => scopedCandidateText(root, selector));
    return unique(
      values.filter((value) => {
        if (value.length < 8 || value.length > 160) {
          return false;
        }
        return !/see who linkedin/i.test(value);
      })
    );
  }

  function extractLinkedInPayload() {
    logInvalidExtensionResourceReferences();

    const pageKind = getLinkedInPageKind();
    const detailRoot = findLinkedInDetailRoot();
    const currentJobId = getLinkedInJobIdFromCurrentUrl();

    if (pageKind === "listing" && !detailRoot) {
      throw new Error("Select a LinkedIn job in the results page before capturing.");
    }

    const root = detailRoot || document.documentElement;
    const multipleJobCards = distinctLinkedInJobCardTitles(root);
    if (!detailRoot && multipleJobCards.length > 1) {
      throw new Error("Select a single LinkedIn job detail before capturing.");
    }

    const title = firstContent([
      firstContentFromRoot(root, [
        ".job-details-jobs-unified-top-card__job-title",
        ".t-24.job-details-jobs-unified-top-card__job-title",
        "h1",
      ]),
      getMetaContent("og:title"),
      document.title,
    ]);

    const company = firstContent([
      detectLinkedInCompanyFromRoot(root),
      detectLinkedInCompany(),
      detectLabeledValueInRoot(root, COMPANY_LABELS),
      detectLabeledValue(COMPANY_LABELS),
    ]);
    const location = firstContent([
      detectLinkedInLocationFromRoot(root),
      detectLinkedInLocation(),
      detectLabeledValueInRoot(root, LOCATION_LABELS),
      detectLabeledValue(LOCATION_LABELS),
    ]);

    if (!title || !company) {
      throw new Error("The selected LinkedIn job detail is still loading. Try again after the detail pane finishes rendering.");
    }

    const linkedinJobId = detectLinkedInJobId(root) || currentJobId;
    return {
      title,
      url: linkedinJobId ? buildLinkedInCanonicalJobUrl(linkedinJobId) : window.location.href,
      html: root.outerHTML,
      visibleText: normalizedVisibleText(root),
      sourceType: "linkedin",
      linkedinJobId,
      company,
      location,
    };
  }

  function isElementVisible(element) {
    if (!element) {
      return false;
    }

    const rect = element.getBoundingClientRect();
    if (rect.width <= 0 || rect.height <= 0) {
      return false;
    }

    return rect.bottom > 0 && rect.top < window.innerHeight;
  }

  function logLinkedInRailDebug(message, details) {
    if (details === undefined) {
      console.debug(LINKEDIN_DEBUG_PREFIX, message);
      return;
    }
    console.debug(LINKEDIN_DEBUG_PREFIX, message, details);
  }

  function logInvalidExtensionResourceReferences() {
    const selectors = [
      "img[src]",
      "iframe[src]",
      "script[src]",
      "source[src]",
      "source[srcset]",
      "video[src]",
      "audio[src]",
      "img[srcset]",
      "link[href]",
      "a[href]",
      "use[href]",
      "image[href]",
    ];
    const invalidReferences = [];

    for (const selector of selectors) {
      for (const element of document.querySelectorAll(selector)) {
        const attribute = element.hasAttribute("src") ? "src" : element.hasAttribute("href") ? "href" : "srcset";
        const value = element.getAttribute(attribute) || "";
        if (!INVALID_EXTENSION_RESOURCE_URL.test(value)) {
          continue;
        }

        const key = `${selector}|${value}|${describeElement(element)}`;
        if (loggedInvalidExtensionResourceReferences.has(key)) {
          continue;
        }
        loggedInvalidExtensionResourceReferences.add(key);

        invalidReferences.push({
          element: describeElement(element),
          attribute,
          value,
        });
      }
    }

    if (invalidReferences.length) {
      console.warn("[Job Assist][Extension Resource]", "Found invalid extension resource references in page DOM.", {
        invalidReferences,
        runtimeId: chrome.runtime?.id || null,
      });
    } else if (!invalidExtensionResourceNoMatchLogged) {
      invalidExtensionResourceNoMatchLogged = true;
      console.debug("[Job Assist][Extension Resource]", "No invalid extension resource references found in page DOM.", {
        runtimeId: chrome.runtime?.id || null,
      });
    }
  }

  function startInvalidExtensionResourceDiagnostics() {
    if (detectSourceType(window.location.href) !== "linkedin") {
      return;
    }

    logInvalidExtensionResourceReferences();
    if (!window.MutationObserver || !document.documentElement) {
      return;
    }

    const observer = new MutationObserver(() => {
      logInvalidExtensionResourceReferences();
    });
    observer.observe(document.documentElement, {
      subtree: true,
      childList: true,
      attributes: true,
      attributeFilter: ["src", "href", "srcset"],
    });
    window.setTimeout(() => observer.disconnect(), 15000);
  }

  function describeElement(element) {
    if (!element) {
      return "<null>";
    }
    const tag = element.tagName.toLowerCase();
    const id = element.id ? `#${element.id}` : "";
    const className = typeof element.className === "string"
      ? element.className.trim().split(/\s+/).filter(Boolean).slice(0, 4).join(".")
      : "";
    return `${tag}${id}${className ? `.${className}` : ""}`;
  }

  function clearLinkedInRailHighlight() {
    if (!linkedInDebugRail || !linkedInDebugRailStyles) {
      linkedInDebugRail = null;
      linkedInDebugRailStyles = null;
      return;
    }

    linkedInDebugRail.style.outline = linkedInDebugRailStyles.outline;
    linkedInDebugRail.style.outlineOffset = linkedInDebugRailStyles.outlineOffset;
    linkedInDebugRail.style.boxShadow = linkedInDebugRailStyles.boxShadow;
    linkedInDebugRail.removeAttribute("data-job-assist-linkedin-rail");
    linkedInDebugRail = null;
    linkedInDebugRailStyles = null;
  }

  function highlightLinkedInRail(element) {
    clearLinkedInRailHighlight();
    if (!element) {
      return;
    }

    linkedInDebugRail = element;
    linkedInDebugRailStyles = {
      outline: element.style.outline,
      outlineOffset: element.style.outlineOffset,
      boxShadow: element.style.boxShadow,
    };
    element.style.outline = "3px solid #ff5a36";
    element.style.outlineOffset = "-2px";
    element.style.boxShadow = "inset 0 0 0 2px rgba(255, 90, 54, 0.2)";
    element.setAttribute("data-job-assist-linkedin-rail", "true");
  }

  function isLinkedInJobTarget(element) {
    if (!element) {
      return false;
    }

    if (element.matches?.("a[href*='/jobs/view/'], a[href*='currentJobId=']")) {
      return true;
    }

    return Boolean(
      element.getAttribute?.("data-job-id") ||
      element.getAttribute?.("data-occludable-job-id") ||
      element.getAttribute?.("data-entity-urn")?.includes("jobPosting")
    );
  }

  function getLinkedInJobTargets(root = document) {
    return Array.from(root.querySelectorAll(LINKEDIN_JOB_TARGET_SELECTOR)).filter(isLinkedInJobTarget);
  }

  function getLinkedInJobCardFromTarget(target, root) {
    const selectors = [
      "[data-occludable-job-id]",
      "[data-job-id]",
      "[data-entity-urn*='jobPosting']",
      "li",
      "[role='listitem']",
      "article",
      ".job-card-container",
      ".jobs-search-results-list__list-item",
      ".scaffold-layout__list-item",
      ".artdeco-list__item",
    ];

    for (const selector of selectors) {
      const candidate = target.closest(selector);
      if (!candidate || (root && !root.contains(candidate))) {
        continue;
      }

      const rect = candidate.getBoundingClientRect();
      if (rect.width > 0 && rect.height > 0) {
        return candidate;
      }
    }

    let current = target.parentElement;
    while (current && current !== root && current !== document.body) {
      const rect = current.getBoundingClientRect();
      if (rect.width > 120 && rect.height > 24 && rect.height < 420) {
        return current;
      }
      current = current.parentElement;
    }

    return target;
  }

  function uniqueElements(elements) {
    return Array.from(new Set(elements.filter(Boolean)));
  }

  function getLinkedInJobCardDiscovery(root = document, { log = false } = {}) {
    const selectorMatches = [];
    const explicitSelectors = [
      ".jobs-search-results-list__list-item",
      ".scaffold-layout__list-item",
      ".job-card-container",
      "li[data-occludable-job-id]",
      "[data-job-id]",
      "[data-occludable-job-id]",
      "[data-entity-urn*='jobPosting']",
      "[role='listitem']",
      "li",
      "article",
    ];

    const cards = [];
    for (const selector of explicitSelectors) {
      const matched = Array.from(root.querySelectorAll(selector)).filter((element) => {
        return getLinkedInJobTargets(element).length > 0;
      });
      if (matched.length) {
        selectorMatches.push({ selector, count: matched.length });
        cards.push(...matched);
      }
    }

    const targets = getLinkedInJobTargets(root);
    const targetCards = targets.map((target) => getLinkedInJobCardFromTarget(target, root));
    if (targetCards.length) {
      selectorMatches.push({ selector: LINKEDIN_JOB_TARGET_SELECTOR, count: targetCards.length });
      cards.push(...targetCards);
    }

    const uniqueCards = uniqueElements(cards).filter((element) => root.contains(element));
    if (log) {
      logLinkedInRailDebug(`Detected ${uniqueCards.length} LinkedIn job card candidates.`, {
        selectorMatches,
        jobTargets: targets.length,
      });
    }

    return {
      cards: uniqueCards,
      selectorMatches,
      jobTargets: targets,
    };
  }

  function getLinkedInJobCards(root = document) {
    return getLinkedInJobCardDiscovery(root).cards;
  }

  function isLinkedInRailScrollContainer(element) {
    if (!element || element === document.body || element === document.documentElement) {
      return false;
    }

    const rect = element.getBoundingClientRect();
    return (
      rect.width > 140 &&
      rect.height > 120 &&
      rect.bottom > 0 &&
      rect.top < window.innerHeight &&
      element.scrollHeight > element.clientHeight + 20
    );
  }

  function inferLinkedInRailFromCards(cards) {
    const visibleCards = cards.filter((card) => isElementVisible(card));
    const candidates = [];

    for (const card of visibleCards) {
      let current = card.parentElement;
      while (current && current !== document.body && current !== document.documentElement) {
        if (isLinkedInRailScrollContainer(current)) {
          const containedVisibleCards = visibleCards.filter((candidateCard) => current.contains(candidateCard));
          candidates.push({
            element: current,
            containedVisibleCards: containedVisibleCards.length,
          });
          break;
        }
        current = current.parentElement;
      }
    }

    const uniqueCandidates = uniqueElements(candidates.map((candidate) => candidate.element)).map((element) => {
      const containedVisibleCards = visibleCards.filter((card) => element.contains(card)).length;
      const rect = element.getBoundingClientRect();
      const leftish = rect.left < window.innerWidth * 0.55;
      return {
        element,
        containedVisibleCards,
        rect,
        score: containedVisibleCards * 20 + Math.min(element.clientHeight, window.innerHeight) / 8 + (leftish ? 30 : 0),
      };
    });

    uniqueCandidates.sort((left, right) => right.score - left.score);
    return uniqueCandidates.find((candidate) => candidate.containedVisibleCards >= 2)?.element || null;
  }

  function buildLinkedInRailCandidate(element) {
    const rect = element.getBoundingClientRect();
    const reasons = [];
    const jobTargets = getLinkedInJobTargets(element);
    const jobCards = getLinkedInJobCards(element);
    const isScrollable = element.scrollHeight > element.clientHeight + 40;
    const visible = rect.width > 140 && rect.height > 180 && rect.bottom > 0 && rect.top < window.innerHeight;
    const leftish = rect.left < window.innerWidth * 0.55;
    const notTooWide = rect.width < window.innerWidth * 0.75;

    if (!visible) {
      reasons.push("rejected: not sufficiently visible");
      return { element, rect, reasons, accepted: false, score: 0, jobTargets, jobCards, isScrollable };
    }
    if (!isScrollable) {
      reasons.push("rejected: not scrollable");
      return { element, rect, reasons, accepted: false, score: 0, jobTargets, jobCards, isScrollable };
    }
    if (jobTargets.length < 2) {
      reasons.push(`rejected: only ${jobTargets.length} job targets`);
      return { element, rect, reasons, accepted: false, score: 0, jobTargets, jobCards, isScrollable };
    }
    if (jobCards.length < 2) {
      reasons.push(`rejected: only ${jobCards.length} job cards`);
      return { element, rect, reasons, accepted: false, score: 0, jobTargets, jobCards, isScrollable };
    }

    let score = 0;
    score += Math.min(jobCards.length, 20) * 12;
    score += Math.min(jobTargets.length, 30) * 6;
    score += Math.min(element.clientHeight, window.innerHeight) / 8;
    score += leftish ? 35 : 0;
    score += notTooWide ? 20 : -25;
    score += rect.left < window.innerWidth * 0.4 ? 25 : 0;
    score += rect.top < window.innerHeight * 0.4 ? 10 : 0;
    score += element.tagName === "ASIDE" ? 10 : 0;
    score += ["UL", "OL", "SECTION", "DIV"].includes(element.tagName) ? 4 : 0;

    reasons.push(`accepted: ${jobCards.length} job cards`);
    reasons.push(`accepted: ${jobTargets.length} job targets`);
    reasons.push(`accepted: scrollHeight ${element.scrollHeight}, clientHeight ${element.clientHeight}`);
    if (leftish) {
      reasons.push("accepted: positioned on left half of viewport");
    }
    if (notTooWide) {
      reasons.push("accepted: width consistent with rail");
    }

    return {
      element,
      rect,
      reasons,
      accepted: true,
      score,
      jobTargets,
      jobCards,
      isScrollable,
    };
  }

  function getLinkedInLeftRailContainer() {
    const discovery = getLinkedInJobCardDiscovery(document, { log: true });
    const inferredRail = inferLinkedInRailFromCards(discovery.cards);
    if (inferredRail) {
      highlightLinkedInRail(inferredRail);
      const visibleCards = discovery.cards.filter((card) => inferredRail.contains(card) && isElementVisible(card));
      logLinkedInRailDebug(`Inferred ${describeElement(inferredRail)} as rail from detected job cards.`, {
        visibleJobCards: visibleCards.length,
        totalDetectedCards: discovery.cards.length,
        scrollHeight: inferredRail.scrollHeight,
        clientHeight: inferredRail.clientHeight,
      });
      return inferredRail;
    }

    logLinkedInRailDebug("Could not infer rail from job card ancestors; falling back to container scoring.");
    const pool = Array.from(document.querySelectorAll("div, section, aside, ul, ol, main"));
    logLinkedInRailDebug(`Evaluating ${pool.length} candidate containers.`);

    const evaluations = pool.map(buildLinkedInRailCandidate);
    const accepted = evaluations.filter((evaluation) => evaluation.accepted);

    evaluations.forEach((evaluation) => {
      logLinkedInRailDebug(`${describeElement(evaluation.element)} score=${evaluation.score}`, {
        accepted: evaluation.accepted,
        rect: {
          top: Math.round(evaluation.rect.top),
          left: Math.round(evaluation.rect.left),
          width: Math.round(evaluation.rect.width),
          height: Math.round(evaluation.rect.height),
        },
        jobTargets: evaluation.jobTargets.length,
        jobCards: evaluation.jobCards.length,
        scrollHeight: evaluation.element.scrollHeight,
        clientHeight: evaluation.element.clientHeight,
        reasons: evaluation.reasons,
      });
    });

    logLinkedInRailDebug(`Accepted ${accepted.length} rail candidates.`);
    if (!accepted.length) {
      clearLinkedInRailHighlight();
      return null;
    }

    accepted.sort((left, right) => right.score - left.score);
    const selected = accepted[0];
    highlightLinkedInRail(selected.element);
    logLinkedInRailDebug(`Selected ${describeElement(selected.element)} as rail.`, {
      score: selected.score,
      visibleJobCards: selected.jobCards.filter((card) => isElementVisible(card)).length,
      totalJobCards: selected.jobCards.length,
    });

    return selected.element;
  }

  function extractLinkedInJobIdFromCard(card) {
    if (!card) {
      return null;
    }

    const directId =
      card.getAttribute("data-job-id") ||
      card.getAttribute("data-occludable-job-id") ||
      parseLinkedInJobIdFromUrl(card.getAttribute("data-job-url"));
    if (directId) {
      return directId;
    }

    const urnNode = card.querySelector("[data-entity-urn*='fsd_jobPosting:']");
    const urn = urnNode?.getAttribute("data-entity-urn") || "";
    const urnMatch = urn.match(/fsd_jobPosting:(\d+)/);
    if (urnMatch) {
      return urnMatch[1];
    }

    const link = card.querySelector("a[href*='/jobs/view/']");
    return parseLinkedInJobIdFromUrl(link?.href || link?.getAttribute("href"));
  }

  function extractLinkedInCardTitle(card) {
    return firstContent([
      ...scopedCandidateText(card, ".job-card-list__title"),
      ...scopedCandidateText(card, ".job-card-container__link"),
      ...scopedCandidateText(card, "a[href*='/jobs/view/']"),
      ...scopedCandidateText(card, "strong"),
    ]);
  }

  function extractLinkedInCardCompany(card) {
    return firstContent([
      ...scopedCandidateText(card, ".job-card-container__primary-description"),
      ...scopedCandidateText(card, ".artdeco-entity-lockup__subtitle"),
      ...scopedCandidateText(card, ".job-card-container__company-name"),
    ]);
  }

  function buildLinkedInFallbackKey(card) {
    const href = card.querySelector("a[href*='/jobs/view/']")?.getAttribute("href") || "";
    const title = extractLinkedInCardTitle(card) || "";
    const company = extractLinkedInCardCompany(card) || "";
    const preview = collapseWhitespace([href, title, company].filter(Boolean).join("|"));
    return preview || collapseWhitespace(card.textContent || "").slice(0, 160);
  }

  function buildLinkedInJobReference(card, index) {
    const linkedinJobId = extractLinkedInJobIdFromCard(card);
    return {
      index,
      linkedinJobId,
      fallbackKey: buildLinkedInFallbackKey(card),
      title: extractLinkedInCardTitle(card),
    };
  }

  function listVisibleLinkedInJobs() {
    if (detectSourceType(window.location.href) !== "linkedin") {
      throw new Error("Open LinkedIn jobs before using bulk capture.");
    }

    logInvalidExtensionResourceReferences();

    const pageKind = getLinkedInPageKind();
    if (pageKind !== "listing") {
      throw new Error("Open a LinkedIn jobs listing with the visible jobs rail before using bulk capture.");
    }

    const rail = getLinkedInLeftRailContainer();
    if (!rail) {
      throw new Error("Could not find the LinkedIn jobs rail.");
    }

    const visibleCards = getLinkedInJobCards(rail)
      .filter((card) => isElementVisible(card));
    logLinkedInRailDebug(`Found ${visibleCards.length} visible job cards inside selected rail.`);

    return visibleCards
      .map((card, index) => buildLinkedInJobReference(card, index))
      .filter((job) => job.linkedinJobId || job.title);
  }

  function scrollLinkedInLeftRail() {
    const rail = getLinkedInLeftRailContainer();
    if (!rail) {
      throw new Error("Could not find the LinkedIn jobs rail.");
    }

    const previousScrollTop = rail.scrollTop;
    const step = Math.max(Math.floor(rail.clientHeight * 0.8), 320);
    const maxScrollTop = Math.max(0, rail.scrollHeight - rail.clientHeight);
    rail.scrollTop = Math.min(maxScrollTop, previousScrollTop + step);

    return new Promise((resolve) => {
      window.setTimeout(() => {
        const currentScrollTop = rail.scrollTop;
        const advanced = currentScrollTop > previousScrollTop;
        const atEnd = currentScrollTop >= maxScrollTop - 4;

        resolve({
          previousScrollTop,
          currentScrollTop,
          advanced,
          atEnd,
        });
      }, 400);
    });
  }

  function findLinkedInJobCard(target) {
    const rail = getLinkedInLeftRailContainer();
    const cards = getLinkedInJobCards(rail || document);
    if (target.linkedinJobId) {
      const matched = cards.find((card) => extractLinkedInJobIdFromCard(card) === target.linkedinJobId);
      if (matched) {
        return matched;
      }
    }

    if (target.fallbackKey) {
      const matched = cards.find((card) => buildLinkedInFallbackKey(card) === target.fallbackKey);
      if (matched) {
        return matched;
      }
    }

    if (typeof target.index === "number" && cards[target.index]) {
      return cards[target.index];
    }

    if (target.title) {
      return cards.find((card) => extractLinkedInCardTitle(card) === target.title) || null;
    }

    return null;
  }

  function findLinkedInJobCardActivator(card) {
    return (
      card?.querySelector("a[href*='/jobs/view/']") ||
      card?.querySelector(".job-card-container__link") ||
      card?.querySelector(".job-card-list__title") ||
      card
    );
  }

  function isLinkedInJobCardSelected(card) {
    if (!card) {
      return false;
    }

    const selectedSelectors = [
      "[aria-selected='true']",
      "[aria-current='true']",
      ".job-card-container--active",
      ".jobs-search-results-list__list-item--active",
      ".scaffold-layout__list-item--active",
      ".artdeco-list__item--active",
    ];

    if (selectedSelectors.some((selector) => card.matches?.(selector) || card.querySelector?.(selector))) {
      return true;
    }

    const className = typeof card.className === "string" ? card.className : "";
    return /selected|active|current/i.test(className);
  }

  function activateLinkedInJobCard(card) {
    const activator = findLinkedInJobCardActivator(card);
    if (!activator?.click) {
      throw new Error("Could not activate the requested LinkedIn job card.");
    }

    const preventFullPageNavigation = (event) => {
      const link = event.target?.closest?.("a[href*='/jobs/view/']");
      if (link && card.contains(link)) {
        event.preventDefault();
      }
    };

    document.addEventListener("click", preventFullPageNavigation, true);
    try {
      activator.click();
    } finally {
      window.setTimeout(() => {
        document.removeEventListener("click", preventFullPageNavigation, true);
      }, 0);
    }
  }

  function getLinkedInDetailSignature() {
    try {
      const payload = extractLinkedInPayload();
      return JSON.stringify({
        linkedinJobId: payload.linkedinJobId,
        title: payload.title,
        company: payload.company,
      });
    } catch (_error) {
      return null;
    }
  }

  function normalizeLinkedInTitle(value) {
    return collapseWhitespace(value || "").toLowerCase();
  }

  function waitForLinkedInDetailUpdate(target, previousSignature, card, timeoutMs = 12000) {
    const startedAt = Date.now();

    return new Promise((resolve, reject) => {
      function check() {
        let payload = null;
        try {
          payload = extractLinkedInPayload();
        } catch (_error) {
          payload = null;
        }

        if (payload) {
          const currentSignature = JSON.stringify({
            linkedinJobId: payload.linkedinJobId,
            title: payload.title,
            company: payload.company,
          });
          const urlJobId = getLinkedInJobIdFromCurrentUrl();
          const titleMatches =
            target.title &&
            normalizeLinkedInTitle(payload.title) &&
            normalizeLinkedInTitle(target.title).includes(normalizeLinkedInTitle(payload.title));
          const idMatches =
            !target.linkedinJobId ||
            payload.linkedinJobId === target.linkedinJobId ||
            urlJobId === target.linkedinJobId;
          const selectedMatches = isLinkedInJobCardSelected(card);
          const changed = currentSignature !== previousSignature;
          if (idMatches && (changed || titleMatches || selectedMatches)) {
            resolve(payload);
            return;
          }
        }

        if (Date.now() - startedAt >= timeoutMs) {
          reject(new Error("Timed out waiting for LinkedIn to load the selected job detail. Try again, or capture the currently open job page."));
          return;
        }

        window.setTimeout(check, 150);
      }

      check();
    });
  }

  async function captureVisibleLinkedInJob(target) {
    const card = findLinkedInJobCard(target);
    if (!card) {
      throw new Error("Could not find the requested LinkedIn job card.");
    }

    const currentPayload = (() => {
      try {
        return extractLinkedInPayload();
      } catch (_error) {
        return null;
      }
    })();
    if (target.linkedinJobId && currentPayload?.linkedinJobId === target.linkedinJobId) {
      return currentPayload;
    }

    card.scrollIntoView({ block: "center", behavior: "auto" });

    const previousSignature = getLinkedInDetailSignature();
    activateLinkedInJobCard(card);

    return waitForLinkedInDetailUpdate(target, previousSignature, card);
  }

  function extractPayload() {
    const sourceType = detectSourceType(window.location.href);
    if (sourceType === "linkedin") {
      return extractLinkedInPayload();
    }

    const title = firstContent([
      getMetaContent("og:title"),
      document.title,
      ...candidateText("h1"),
    ]);

    const company = firstContent([
      detectCompany(sourceType),
      detectLabeledValue(COMPANY_LABELS),
    ]);
    const location = firstContent([
      detectLocation(sourceType),
      detectLabeledValue(LOCATION_LABELS),
    ]);

    return {
      title,
      html: document.documentElement.outerHTML,
      visibleText: normalizedVisibleText(),
      sourceType,
      company,
      location,
    };
  }

  startInvalidExtensionResourceDiagnostics();

  chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
    if (!message || !message.type) {
      return false;
    }

    if (message.type === "CAPTURE_JOB_PAGE") {
      try {
        sendResponse({
          ok: true,
          payload: extractPayload(),
        });
      } catch (error) {
        sendResponse({
          ok: false,
          error: error instanceof Error ? error.message : "Page extraction failed.",
        });
      }

      return false;
    }

    if (message.type === "LIST_VISIBLE_LINKEDIN_JOBS") {
      try {
        sendResponse({
          ok: true,
          payload: {
            jobs: listVisibleLinkedInJobs(),
          },
        });
      } catch (error) {
        sendResponse({
          ok: false,
          error: error instanceof Error ? error.message : "Could not list visible LinkedIn jobs.",
        });
      }

      return false;
    }

    if (message.type === "SCROLL_LINKEDIN_JOB_RAIL") {
      scrollLinkedInLeftRail()
        .then((payload) => {
          sendResponse({
            ok: true,
            payload,
          });
        })
        .catch((error) => {
          sendResponse({
            ok: false,
            error: error instanceof Error ? error.message : "Could not scroll the LinkedIn jobs rail.",
          });
        });

      return true;
    }

    if (message.type === "CAPTURE_LINKEDIN_VISIBLE_JOB") {
      captureVisibleLinkedInJob(message.payload || {})
        .then((payload) => {
          sendResponse({
            ok: true,
            payload,
          });
        })
        .catch((error) => {
          sendResponse({
            ok: false,
            error: error instanceof Error ? error.message : "Could not capture LinkedIn job detail.",
          });
        });

      return true;
    }

    return false;
  });
})();
