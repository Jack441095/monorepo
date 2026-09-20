const statusEl = document.querySelector("#creative-status");
const serviceStatusEl = document.querySelector("#creative-service-status");
const authPanel = document.querySelector("#creative-auth");
const passwordInput = document.querySelector("#creative-password");
const unlockButton = document.querySelector("#creative-unlock");
const askForm = document.querySelector("#creative-ask-form");
const questionInput = document.querySelector("#creative-question");
const chatEl = document.querySelector("#creative-chat");
const promptInput = document.querySelector("#creative-prompt");
const emotionInput = document.querySelector("#creative-emotion");
const barsInput = document.querySelector("#creative-bars");
const publishInput = document.querySelector("#creative-publish");
const audioGenForm = document.querySelector("#creative-audiogen-form");
const renderSongButton = document.querySelector("#creative-render-song");
const resultEl = document.querySelector("#creative-audiogen-result");
const playerPanel = document.querySelector("#creative-player-panel");
const player = document.querySelector("#creative-player");
const playerLabel = document.querySelector("#creative-player-label");
const jobsEl = document.querySelector("#creative-jobs");
const historyEl = document.querySelector("#creative-history");
const sessionsEl = document.querySelector("#creative-sessions");
const qualityEl = document.querySelector("#creative-quality");
const repairQualityEl = document.querySelector("#creative-repair-quality");
const repairRecommendationsEl = document.querySelector("#creative-repair-recommendations");
const repairQueueEl = document.querySelector("#creative-repair-queue");
const repairComparisonEl = document.querySelector("#creative-repair-comparison");
const trainingRecordsEl = document.querySelector("#creative-training-records");
const promptLeaderboardEl = document.querySelector("#creative-prompt-leaderboard");
const sessionReplayEl = document.querySelector("#creative-session-replay");
const mixReviewResultEl = document.querySelector("#creative-mix-review-result");

const conversation = [];
let activeJobId = "";
let queueTimer = null;
let currentSessionId = window.localStorage.getItem("creativeLabSessionId") || "";
let lastKennTurn = null;
let lastAudioResult = null;
let csrfToken = "";
let csrfPromise = null;
const browserFetch = window.fetch.bind(window);

async function ensureCsrfToken() {
  if (csrfToken) return csrfToken;
  csrfPromise ||= browserFetch("/api/auth/session", { credentials: "same-origin" })
    .then((response) => response.json())
    .then((data) => {
      csrfToken = data.csrf_token || "";
      return csrfToken;
    })
    .finally(() => { csrfPromise = null; });
  return csrfPromise;
}

// NOTE: this MUST be a const arrow, not `function fetch(){}`. A top-level function
// declaration in a classic <script> is hoisted onto window.fetch *before* the
// `const browserFetch = window.fetch.bind(window)` line above runs, so browserFetch
// would capture this wrapper instead of the native fetch and every call would recurse
// infinitely ("too much recursion"). A const arrow does not clobber window.fetch.
const fetch = async (input, options = {}) => {
  const method = String(options.method || "GET").toUpperCase();
  const headers = new Headers(options.headers || {});
  if (!["GET", "HEAD", "OPTIONS"].includes(method) && String(input) !== "/api/auth/login") {
    await ensureCsrfToken();
    if (csrfToken) headers.set("X-CSRF-Token", csrfToken);
  }
  return browserFetch(input, { ...options, credentials: "same-origin", headers });
};

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function fetchOptions(options = {}) {
  return {
    ...options,
    credentials: "same-origin",
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
  };
}

async function api(path, options = {}) {
  const response = await fetch(path, fetchOptions(options));
  const data = await response.json();
  if (data.csrf_token) csrfToken = data.csrf_token;
  if (response.status === 401) {
    if (authPanel) authPanel.hidden = false;
    throw new Error(data.error || "Sign in required.");
  }
  if (!response.ok) throw new Error(data.error || data.output || "Request failed");
  return data;
}

async function sessionActive() {
  const response = await fetch("/api/auth/session", fetchOptions());
  const data = await response.json();
  csrfToken = data.csrf_token || "";
  return Boolean(data.authenticated);
}

function setStatus(message) {
  if (statusEl) statusEl.textContent = message;
}

function selectedEmotion() {
  return emotionInput?.value || "joy";
}

function setEmotion(emotion) {
  if (emotionInput) emotionInput.value = emotion || "joy";
  document.querySelectorAll("[data-creative-emotion]").forEach((button) => {
    button.classList.toggle("active", button.dataset.creativeEmotion === selectedEmotion());
  });
}

function sourceFromResult(data = {}) {
  return data.src || data.portfolio_entry?.src || "";
}

function loadPlayer(src, label = "Generated audio") {
  if (!player || !src) return;
  player.src = src;
  if (playerPanel) playerPanel.hidden = false;
  if (playerLabel) playerLabel.textContent = label;
}

function sessionTitle() {
  const prompt = promptInput?.value?.trim() || questionInput?.value?.trim() || "Audio_Gen session";
  return prompt.slice(0, 90);
}

async function recordSessionEvent(payload = {}) {
  const data = await api("/api/admin/creative-lab/session", {
    method: "POST",
    body: JSON.stringify({
      session_id: currentSessionId,
      title: sessionTitle(),
      ...payload,
    }),
  });
  currentSessionId = data.session?.id || currentSessionId;
  if (currentSessionId) window.localStorage.setItem("creativeLabSessionId", currentSessionId);
  await loadSessions();
  return data;
}

function renderServiceStatus(data = {}) {
  const kenn = data.kenn || {};
  const llm = data.llm || {};
  const audiogen = data.audiogen || {};
  serviceStatusEl.innerHTML = `
    <span class="status-pill ${kenn.running ? "ok" : "warn"}">${kenn.running ? "KENN online" : "KENN offline"}</span>
    <span class="status-pill">${llm.enabled ? "Rewrite enabled" : "Retrieval only"}</span>
    <span class="status-pill ${audiogen.ok ? "ok" : "warn"}">${audiogen.ok ? "AudioGen ready" : "AudioGen unavailable"}</span>
    <span class="status-pill">${escapeHtml(audiogen.render_history_count ?? 0)} history item(s)</span>
  `;
}

async function loadStatus() {
  try {
    const data = await api("/api/hub/status");
    renderServiceStatus(data);
  } catch (error) {
    if (serviceStatusEl) serviceStatusEl.innerHTML = `<span class="status-pill warn">${escapeHtml(error.message)}</span>`;
  }
}

function renderChatMessage(role, content, meta = "") {
  const feedback = role === "assistant"
    ? `<div class="button-row compact creative-feedback-row">
        <button type="button" data-creative-feedback="good_idea" data-feedback-target="kenn">Good idea</button>
        <button type="button" class="secondary" data-creative-feedback="wrong_direction" data-feedback-target="kenn">Wrong direction</button>
        <button type="button" class="secondary" data-creative-feedback="bad_source" data-feedback-target="kenn">Bad source</button>
      </div>`
    : "";
  return `
    <article class="creative-message ${role === "user" ? "user" : "assistant"}">
      <strong>${role === "user" ? "You" : "KENN"}</strong>
      <p>${escapeHtml(content)}</p>
      ${meta ? `<small>${escapeHtml(meta)}</small>` : ""}
      ${feedback}
    </article>
  `;
}

function appendChat(role, content, meta = "") {
  if (!chatEl) return;
  chatEl.insertAdjacentHTML("beforeend", renderChatMessage(role, content, meta));
  chatEl.scrollTop = chatEl.scrollHeight;
}

askForm?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const question = questionInput?.value.trim() || "";
  if (!question) return;
  appendChat("user", question);
  if (questionInput) questionInput.value = "";
  setStatus("KENN is thinking...");
  try {
    const data = await api("/api/ableton/ask", {
      method: "POST",
      body: JSON.stringify({
        question,
        limit: 8,
        history: conversation.slice(-6),
        session_id: localStorage.getItem("kenn_session_id") || "",
      }),
    });
    conversation.push({ role: "user", content: question });
    if (data.answer) conversation.push({ role: "assistant", content: data.answer });
    // Persist session_id from the response
    if (data.session?.session_id) {
      localStorage.setItem("kenn_session_id", data.session.session_id);
    }
    lastKennTurn = { question, answer: data.answer || "", confidence: data.confidence || "", source_quality: data.source_quality || "" };
    await recordSessionEvent({
      type: "kenn",
      question,
      answer: data.answer || "",
    });
    const meta = [data.confidence ? `${data.confidence} confidence` : "", data.source_quality ? `${data.source_quality} sources` : ""]
      .filter(Boolean)
      .join(" · ");
    appendChat("assistant", data.answer || "No answer.", meta);
    setStatus("KENN answer ready.");
  } catch (error) {
    appendChat("assistant", error.message);
    setStatus(error.message);
  }
});

document.querySelector("#creative-clear-chat")?.addEventListener("click", () => {
  conversation.splice(0, conversation.length);
  if (chatEl) chatEl.innerHTML = "";
  setStatus("Conversation cleared.");
});

document.querySelector("#creative-new-session")?.addEventListener("click", () => {
  currentSessionId = "";
  window.localStorage.removeItem("creativeLabSessionId");
  conversation.splice(0, conversation.length);
  if (chatEl) chatEl.innerHTML = "";
  if (resultEl) resultEl.innerHTML = "";
  if (mixReviewResultEl) mixReviewResultEl.innerHTML = "";
  lastKennTurn = null;
  lastAudioResult = null;
  setStatus("New Audio_Gen session started.");
});

document.querySelectorAll("[data-creative-question]").forEach((button) => {
  button.addEventListener("click", () => {
    if (questionInput) {
      questionInput.value = button.dataset.creativeQuestion || "";
      questionInput.focus();
    }
  });
});

document.querySelectorAll("[data-creative-preset]").forEach((button) => {
  button.addEventListener("click", () => {
    setEmotion(button.dataset.creativePreset || "joy");
    if (promptInput) promptInput.value = button.dataset.prompt || "";
  });
});

document.querySelectorAll("[data-creative-emotion]").forEach((button) => {
  button.addEventListener("click", () => setEmotion(button.dataset.creativeEmotion || "joy"));
});

function renderAudioResult(data = {}, label = "Generated") {
  const src = sourceFromResult(data);
  lastAudioResult = { ...data, src };
  if (src) loadPlayer(src, `${label}: ${data.emotion || selectedEmotion()}`);
  if (!resultEl) return;
  resultEl.innerHTML = `
    <div class="answer-meta">
      <span class="status-pill ok">${escapeHtml(label)}</span>
      <span class="status-pill">${escapeHtml(data.emotion || selectedEmotion())}</span>
      ${data.bars ? `<span class="status-pill">${escapeHtml(data.bars)} bar setting</span>` : ""}
      ${data.portfolio_entry ? '<span class="status-pill ok">Published to portfolio</span>' : '<span class="status-pill">Private audio</span>'}
    </div>
    ${src ? `<div class="button-row"><button type="button" data-send-mix-review="${escapeHtml(src)}" data-review-title="${escapeHtml(`${data.emotion || selectedEmotion()} ${label}`)}">Send to Mix Review</button><button type="button" class="secondary" data-creative-feedback="useful_generation_prompt" data-feedback-target="audiogen">Useful generation prompt</button><a class="button-link secondary" href="${escapeHtml(src)}" target="_blank" rel="noreferrer">Open WAV</a></div>` : ""}
  `;
}

function setAudioBusy(isBusy, message = "") {
  audioGenForm?.querySelectorAll("button, input, textarea").forEach((item) => {
    if (item.id !== "creative-publish") item.disabled = isBusy;
  });
  if (renderSongButton) renderSongButton.disabled = isBusy;
  if (message && resultEl) resultEl.textContent = message;
}

audioGenForm?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const emotion = selectedEmotion();
  const prompt = promptInput?.value.trim() || `Generate a ${emotion} chorus loop.`;
  setAudioBusy(true, "Generating loop...");
  try {
    const data = await api("/api/admin/audiogen/generate", {
      method: "POST",
      body: JSON.stringify({
        prompt,
        emotion,
        bars: Number(barsInput?.value || 4),
        publish: Boolean(publishInput?.checked),
      }),
    });
    renderAudioResult(data, "Loop generated");
    await recordSessionEvent({
      type: "audiogen_loop",
      prompt,
      emotion,
      src: sourceFromResult(data),
    });
    await loadHistory();
    await loadStatus();
    setStatus("Loop generated.");
  } catch (error) {
    if (resultEl) resultEl.textContent = error.message;
    setStatus(error.message);
  } finally {
    setAudioBusy(false);
  }
});

renderSongButton?.addEventListener("click", async () => {
  const emotion = selectedEmotion();
  setAudioBusy(true, `Queueing full ${emotion} song...`);
  try {
    const data = await api("/api/admin/audiogen/render-song", {
      method: "POST",
      body: JSON.stringify({
        emotion,
        bars: Number(barsInput?.value || 4),
        k: 1,
        publish: Boolean(publishInput?.checked),
      }),
    });
    activeJobId = data.job?.id || "";
    if (resultEl) resultEl.textContent = `Queued full ${emotion} song render.`;
    await loadJobs();
    setStatus("Full song render queued.");
  } catch (error) {
    if (resultEl) resultEl.textContent = error.message;
    setStatus(error.message);
  } finally {
    setAudioBusy(false);
  }
});

function renderJob(job = {}) {
  const result = job.result || {};
  const src = sourceFromResult(result);
  const canOpen = job.status === "completed" && src;
  return `
    <div class="audiogen-job">
      <div>
        <strong>${escapeHtml(job.emotion || "joy")} full song</strong>
        <span>${escapeHtml(job.message || job.status || "queued")}</span>
      </div>
      <div class="audiogen-job-meta">
        <span class="status-pill ${job.status === "completed" ? "ok" : job.status === "failed" ? "warn" : ""}">${escapeHtml(job.status || "queued")}</span>
        <span class="status-pill">${escapeHtml(job.progress ?? 0)}%</span>
      </div>
      <div class="audiogen-progress"><span style="width:${Math.max(0, Math.min(100, Number(job.progress || 0)))}%"></span></div>
      ${canOpen ? `<button type="button" data-play-src="${escapeHtml(src)}" data-play-label="${escapeHtml(`${job.emotion || "AudioGen"} full song`)}">Load player</button>` : ""}
    </div>
  `;
}

async function loadJobs() {
  if (!jobsEl) return;
  try {
    const data = await api("/api/admin/audiogen/render-jobs?limit=8");
    const jobs = data.queue?.recent || [];
    jobsEl.innerHTML = jobs.length ? jobs.map(renderJob).join("") : "<p class='compact-status'>No render jobs yet.</p>";
    const active = jobs.find((job) => job.id === activeJobId);
    if (active?.status === "completed" && active.result) {
      renderAudioResult(active.result, "Full song generated");
      await recordSessionEvent({
        type: "audiogen_full_song",
        emotion: active.result.emotion || active.emotion || "",
        src: sourceFromResult(active.result),
      });
      activeJobId = "";
      await loadHistory();
    }
    const busy = jobs.some((job) => job.status === "queued" || job.status === "running");
    if (busy && !queueTimer) queueTimer = window.setInterval(loadJobs, 3000);
    if (!busy && queueTimer) {
      window.clearInterval(queueTimer);
      queueTimer = null;
    }
  } catch (error) {
    jobsEl.innerHTML = `<p class='compact-status'>${escapeHtml(error.message)}</p>`;
  }
}

function renderHistoryItem(item = {}) {
  const src = item.src || "";
  return `
    <div class="audiogen-job">
      <div>
        <strong>${escapeHtml(item.kind || "audio")} · ${escapeHtml(item.emotion || "emotion")}</strong>
        <span>${escapeHtml(item.created_at || "")}</span>
      </div>
      <div class="audiogen-job-meta">
        ${item.bars ? `<span class="status-pill">${escapeHtml(item.bars)} bar setting</span>` : ""}
        ${item.portfolio_title ? '<span class="status-pill ok">Portfolio linked</span>' : '<span class="status-pill">Private/local</span>'}
      </div>
      ${src ? `<div class="button-row"><button type="button" data-play-src="${escapeHtml(src)}" data-play-label="${escapeHtml(item.portfolio_title || `${item.emotion} ${item.kind}`)}">Load player</button><button type="button" class="secondary" data-send-mix-review="${escapeHtml(src)}" data-review-title="${escapeHtml(item.portfolio_title || `${item.emotion} ${item.kind}`)}">Send to Mix Review</button><a class="button-link secondary" href="${escapeHtml(src)}" target="_blank" rel="noreferrer">Open WAV</a></div>` : ""}
    </div>
  `;
}

async function loadHistory() {
  if (!historyEl) return;
  try {
    const data = await api("/api/admin/audiogen/history?limit=12");
    const items = data.items || [];
    historyEl.innerHTML = items.length ? items.map(renderHistoryItem).join("") : "<p class='compact-status'>No AudioGen history yet.</p>";
  } catch (error) {
    historyEl.innerHTML = `<p class='compact-status'>${escapeHtml(error.message)}</p>`;
  }
}

function renderSession(session = {}) {
  const events = session.events || [];
  const latest = events[events.length - 1] || {};
  const label = latest.type ? `${latest.type.replaceAll("_", " ")} · ${latest.created_at || ""}` : session.updated_at || "";
  return `
    <div class="audiogen-job">
      <div>
        <strong>${escapeHtml(session.title || session.id || "Audio_Gen session")}</strong>
        <span>${escapeHtml(label)}</span>
      </div>
      <div class="audiogen-job-meta">
        <span class="status-pill">${escapeHtml(events.length)} event(s)</span>
        ${session.id === currentSessionId ? '<span class="status-pill ok">Current</span>' : ""}
      </div>
      <div class="button-row">
        <button type="button" data-load-session="${escapeHtml(session.id || "")}">Use this session</button>
        <button type="button" class="secondary" data-replay-session="${escapeHtml(session.id || "")}">Replay</button>
      </div>
    </div>
  `;
}

function renderQualityMetrics(metrics = {}) {
  if (!qualityEl) return;
  const approval = metrics.approval_rate === null || metrics.approval_rate === undefined ? "n/a" : `${metrics.approval_rate}%`;
  const mixScore = metrics.average_mix_score === null || metrics.average_mix_score === undefined ? "n/a" : `${metrics.average_mix_score}/100`;
  const repairPassRate = metrics.repair_pass_rate === null || metrics.repair_pass_rate === undefined ? "n/a" : `${metrics.repair_pass_rate}%`;
  const repairTopThreeRate = metrics.repair_top_three_rate === null || metrics.repair_top_three_rate === undefined ? "n/a" : `${metrics.repair_top_three_rate}%`;
  qualityEl.innerHTML = `
    <div class="lm-improve-card">
      <strong>${escapeHtml(metrics.sessions || 0)}</strong>
      <span>sessions</span>
    </div>
    <div class="lm-improve-card">
      <strong>${escapeHtml(metrics.generated_audio || 0)}</strong>
      <span>generated audio</span>
    </div>
    <div class="lm-improve-card">
      <strong>${escapeHtml(approval)}</strong>
      <span>approval rate</span>
    </div>
    <div class="lm-improve-card">
      <strong>${escapeHtml(mixScore)}</strong>
      <span>average mix score</span>
    </div>
    <div class="lm-improve-card">
      <strong>${escapeHtml(metrics.negative_feedback || 0)}</strong>
      <span>repair items</span>
    </div>
  `;
  if (repairQualityEl) {
    repairQualityEl.innerHTML = `
      <div class="lm-improve-card">
        <strong>${escapeHtml(repairPassRate)}</strong>
        <span>repair pass rate</span>
      </div>
      <div class="lm-improve-card">
        <strong>${escapeHtml(repairTopThreeRate)}</strong>
        <span>top-3 repair source rate</span>
      </div>
      <div class="lm-improve-card">
        <strong>${escapeHtml(metrics.repair_regressions_added || 0)}</strong>
        <span>regressions added</span>
      </div>
      <div class="lm-improve-card">
        <strong>${escapeHtml(metrics.repair_open || 0)}</strong>
        <span>open repairs</span>
      </div>
      <div class="lm-improve-card">
        <strong>${escapeHtml(metrics.repair_attempts || 0)}</strong>
        <span>repair attempts</span>
      </div>
    `;
  }
}

function renderRepairRecommendations(items = []) {
  if (!repairRecommendationsEl) return;
  repairRecommendationsEl.innerHTML = items.length
    ? `
      <div class="section-title compact">
        <div>
          <h2>Repair recommendations</h2>
          <span class="compact-status">Next actions from eval, source ranking, and regression coverage.</span>
        </div>
        <div class="button-row compact">
          <button type="button" class="secondary" data-export-repair-training="1">Export repair training</button>
          <button type="button" class="secondary" data-export-approved-repair-training="1">Export approved only</button>
          <button type="button" class="secondary" data-validate-approved-repair-training="1">Validate approved export</button>
        </div>
      </div>
      <div class="creative-recommendation-list">
        ${items.map((item) => `
          <article class="creative-recommendation">
            <div>
              <strong>${escapeHtml(item.title || "Repair recommendation")}</strong>
              <span>${escapeHtml(item.question || "")}</span>
            </div>
            <p>${escapeHtml(item.reason || "")}</p>
            <div class="audiogen-job-meta">
              <span class="status-pill ${item.priority === "high" ? "warn" : ""}">${escapeHtml(item.priority || "medium")}</span>
              <span class="status-pill">${escapeHtml(item.action || "")}</span>
            </div>
            <div class="button-row">
              ${item.feedback_id ? `<button type="button" data-run-repair-recommendation="${escapeHtml(item.feedback_id)}">Run next safe step</button>` : ""}
              ${item.feedback_id ? `<button type="button" class="secondary" data-compare-repair="${escapeHtml(item.feedback_id)}">Open repair</button>` : ""}
            </div>
          </article>
        `).join("")}
      </div>
    `
    : "<p class='compact-status'>No repair recommendations right now.</p>";
}

function renderRepairQueue(items = []) {
  if (!repairQueueEl) return;
  repairQueueEl.innerHTML = items.length
    ? items.map((item) => `
      <div class="audiogen-job creative-repair-item">
        <div>
          <strong>${escapeHtml((item.rating || "").replaceAll("_", " "))}</strong>
          <span>${escapeHtml(item.question || item.prompt || "Audio_Gen feedback")}</span>
        </div>
        <div class="audiogen-job-meta">
          <span class="status-pill warn">${escapeHtml(item.priority || "repair")}</span>
          ${item.target ? `<span class="status-pill">${escapeHtml(item.target)}</span>` : ""}
        </div>
        <p class="compact-status">${escapeHtml(item.action || "")}</p>
        ${item.answer ? `<p class="compact-status">${escapeHtml(item.answer)}</p>` : ""}
        ${item.repair_note ? `<p class="compact-status">Drafted: ${escapeHtml(item.repair_note)} · ${escapeHtml(item.eval_case_id || "")}</p>` : ""}
        ${item.last_eval_at ? `<p class="compact-status">Last eval: ${item.last_eval_passed ? "passed" : "failed"} · ${escapeHtml(item.last_eval_at)}</p>` : ""}
        ${item.main_eval_promoted_at ? `<p class="compact-status">Regression added: ${escapeHtml(item.main_eval_case_id || "")} · ${escapeHtml(item.main_eval_promoted_at)}</p>` : ""}
        ${item.repair_attempts ? `<p class="compact-status">${escapeHtml(item.repair_attempts)} repair attempt(s)</p>` : ""}
        <div class="button-row">
          ${item.id && !item.repair_note ? `<button type="button" data-create-repair="${escapeHtml(item.id)}">Create repair draft</button>` : ""}
          ${item.id && item.repair_note ? `<button type="button" data-promote-repair="${escapeHtml(item.id)}">${item.last_eval_passed ? "Rerun repair eval" : "Promote repair"}</button>` : ""}
          ${item.id && item.last_eval_passed && !item.main_eval_promoted_at ? `<button type="button" data-promote-repair-eval="${escapeHtml(item.id)}">Add to regression suite</button>` : ""}
          ${item.id ? `<button type="button" class="secondary" data-compare-repair="${escapeHtml(item.id)}">Compare</button>` : ""}
          ${item.session_id ? `<button type="button" class="secondary" data-replay-session="${escapeHtml(item.session_id)}">Replay session</button>` : ""}
        </div>
      </div>
    `).join("")
    : "<p class='compact-status'>No repair items yet.</p>";
}

function renderRepairComparison(data = {}) {
  if (!repairComparisonEl) return;
  if (!data.ok) {
    repairComparisonEl.innerHTML = "<p class='compact-status'>Select a repair item to compare answers.</p>";
    return;
  }
  const latest = data.latest || {};
  const original = data.original || {};
  const failures = latest.failures || [];
  const sources = latest.sources || [];
  const history = data.history || [];
  const latestRanking = history.length ? history[history.length - 1].source_ranking || {} : {};
  repairComparisonEl.innerHTML = `
    <div class="creative-compare-header">
      <strong>${escapeHtml(data.question || "Repair comparison")}</strong>
      <div class="audiogen-job-meta">
        <span class="status-pill ${latest.passed ? "ok" : "warn"}">${latest.passed ? "eval passed" : "eval needs work"}</span>
        ${data.main_eval_promoted_at ? `<span class="status-pill ok">regression added</span>` : ""}
        ${latest.confidence ? `<span class="status-pill">${escapeHtml(latest.confidence)} confidence</span>` : ""}
        ${latest.source_quality ? `<span class="status-pill">${escapeHtml(latest.source_quality)} sources</span>` : ""}
      </div>
    </div>
    <div class="creative-compare-grid">
      <section>
        <h3>Original answer</h3>
        <p>${escapeHtml(original.answer || "No original answer captured.")}</p>
        ${original.comment ? `<small>${escapeHtml(original.comment)}</small>` : ""}
      </section>
      <section>
        <h3>Latest repaired answer</h3>
        <p>${escapeHtml(latest.answer || "No repaired answer has been recorded yet.")}</p>
        ${failures.length ? `<small>Failures: ${escapeHtml(failures.join("; "))}</small>` : ""}
      </section>
    </div>
    <div class="creative-source-list">
      <strong>Latest top sources</strong>
      ${sources.length ? sources.map((source) => `<span>${escapeHtml(source.label || "source")} ${source.kind ? `· ${escapeHtml(source.kind)}` : ""}${source.score !== undefined && source.score !== null ? ` · ${escapeHtml(source.score)}` : ""}</span>`).join("") : "<span>No source payload recorded yet.</span>"}
    </div>
    <div class="creative-ranking-report">
      <strong>Source ranking report</strong>
      <span>Repair note: ${escapeHtml(latestRanking.repair_note || data.repair_note || "not drafted")}</span>
      <span>Repair note rank: ${latestRanking.repair_note_rank ? escapeHtml(latestRanking.repair_note_rank) : "not in returned sources"}</span>
      <span>Top source: ${escapeHtml(latestRanking.top_source?.label || "none")}</span>
      <span>${latestRanking.repair_note_in_top_three ? "Repair note is in the top 3." : "Repair note is not ranking in the top 3 yet."}</span>
    </div>
    ${latest.passed && !data.main_eval_promoted_at ? `<button type="button" data-promote-repair-eval="${escapeHtml(data.feedback_id || "")}">Add passing case to regression suite</button>` : ""}
    <div class="creative-repair-timeline">
      <strong>Repair run history</strong>
      ${history.length ? history.map((run, index) => {
        const runSources = run.sources || [];
        const runFailures = run.failures || [];
        const ranking = run.source_ranking || {};
        return `
          <article class="creative-timeline-item">
            <div class="audiogen-job-meta">
              <span class="status-pill">${escapeHtml(index + 1)}</span>
              <span class="status-pill ${run.eval_passed ? "ok" : "warn"}">${run.eval_passed ? "passed" : "failed"}</span>
              <span class="status-pill">${run.build_ok ? "build ok" : "build failed"}</span>
              ${run.created_at ? `<span class="status-pill">${escapeHtml(run.created_at)}</span>` : ""}
            </div>
            ${runFailures.length ? `<p>Failures: ${escapeHtml(runFailures.join("; "))}</p>` : "<p>No eval failures recorded.</p>"}
            ${run.answer ? `<p>${escapeHtml(run.answer)}</p>` : ""}
            <small>Repair source rank: ${ranking.repair_note_rank ? escapeHtml(ranking.repair_note_rank) : "not returned"} · top source: ${escapeHtml(ranking.top_source?.label || "none")}</small>
            ${runSources.length ? `<small>Sources: ${runSources.map((source) => escapeHtml(source.label || "source")).join(", ")}</small>` : ""}
          </article>
        `;
      }).join("") : "<span>No repair runs yet. Promote the draft repair to create one.</span>"}
    </div>
  `;
}

function renderTrainingRecords(data = {}) {
  if (!trainingRecordsEl) return;
  const records = data.records || [];
  const approvedManifest = data.approved_manifest || {};
  const manifest = approvedManifest.manifest || {};
  if (!data.exists) {
    trainingRecordsEl.innerHTML = "<p class='compact-status'>No repair training export yet. Use Export repair training after repair runs exist.</p>";
    return;
  }
  trainingRecordsEl.innerHTML = `
    <div class="creative-training-summary">
      <span class="status-pill ok">${escapeHtml(data.count || 0)} record(s)</span>
      <span class="status-pill">${escapeHtml(data.path || "")}</span>
      ${data.skipped ? `<span class="status-pill warn">${escapeHtml(data.skipped)} skipped row(s)</span>` : ""}
      <span class="status-pill">${escapeHtml(data.review_counts?.approved || 0)} approved</span>
      <span class="status-pill">${escapeHtml(data.review_counts?.needs_work || 0)} needs work</span>
      <span class="status-pill">${escapeHtml(data.review_counts?.rejected || 0)} rejected</span>
    </div>
    <div class="creative-training-summary">
      <span class="status-pill ${approvedManifest.exists ? "ok" : "warn"}">${approvedManifest.exists ? "approved export ready" : "no approved export yet"}</span>
      ${approvedManifest.exists ? `<span class="status-pill">${escapeHtml(manifest.selected_records ?? 0)} approved record(s) exported</span>` : ""}
      ${manifest.output_path ? `<span class="status-pill">${escapeHtml(manifest.output_path)}</span>` : ""}
      ${manifest.created_at ? `<span class="status-pill">${escapeHtml(manifest.created_at)}</span>` : ""}
      ${approvedManifest.error ? `<span class="status-pill warn">${escapeHtml(approvedManifest.error)}</span>` : ""}
      ${data.validation ? `<span class="status-pill ${data.validation.valid ? "ok" : "warn"}">${data.validation.valid ? "validation passed" : "validation needs work"}</span>` : ""}
    </div>
    ${data.validation?.errors?.length ? `<p class="compact-status">${escapeHtml(data.validation.errors.join("; "))}</p>` : ""}
    ${records.length ? records.map((record) => {
      const review = record.review || {};
      const decision = review.decision || "unreviewed";
      return `
      <article class="audiogen-job creative-training-record">
        <div>
          <strong>${escapeHtml(record.label || "repair record")}</strong>
          <span>${escapeHtml(record.question || "No question captured.")}</span>
        </div>
        <div class="audiogen-job-meta">
          <span class="status-pill ${record.eval_passed ? "ok" : "warn"}">${record.eval_passed ? "eval passed" : "eval failed"}</span>
          <span class="status-pill">${record.repair_note_rank ? `rank ${escapeHtml(record.repair_note_rank)}` : "not ranked"}</span>
          ${record.needs_rerank_training ? "<span class='status-pill warn'>rerank candidate</span>" : ""}
          <span class="status-pill ${decision === "approved" ? "ok" : decision === "rejected" || decision === "needs_work" ? "warn" : ""}">${escapeHtml(decision.replaceAll("_", " "))}</span>
        </div>
        <p><strong>Original:</strong> ${escapeHtml(record.original_answer || "").slice(0, 220)}</p>
        <p><strong>Repaired:</strong> ${escapeHtml(record.repaired_answer || "").slice(0, 220)}</p>
        ${review.note ? `<small>Review note: ${escapeHtml(review.note)}</small>` : ""}
        <small>${escapeHtml((record.source_labels || []).slice(0, 3).join(", ") || "No sources recorded.")}</small>
        <div class="button-row compact">
          <button type="button" data-review-training-record="${escapeHtml(record.record_id || "")}" data-review-decision="approved">Approve</button>
          <button type="button" class="secondary" data-review-training-record="${escapeHtml(record.record_id || "")}" data-review-decision="needs_work">Needs work</button>
          <button type="button" class="secondary" data-review-training-record="${escapeHtml(record.record_id || "")}" data-review-decision="rejected">Reject</button>
        </div>
      </article>
    `;
    }).join("") : "<p class='compact-status'>Export file exists, but contains no repair records yet.</p>"}
  `;
}

async function loadRepairComparison(feedbackId) {
  if (!repairComparisonEl || !feedbackId) return;
  repairComparisonEl.innerHTML = "<p class='compact-status'>Loading repair comparison...</p>";
  try {
    const data = await api(`/api/admin/creative-lab/repair/comparison?id=${encodeURIComponent(feedbackId)}`);
    renderRepairComparison(data);
  } catch (error) {
    repairComparisonEl.innerHTML = `<p class='compact-status'>${escapeHtml(error.message)}</p>`;
  }
}

async function loadTrainingRecords(extra = {}) {
  if (!trainingRecordsEl) return;
  trainingRecordsEl.innerHTML = "<p class='compact-status'>Loading training records...</p>";
  try {
    const data = await api("/api/admin/creative-lab/repair/training-records?limit=10");
    renderTrainingRecords({ ...data, ...extra });
  } catch (error) {
    trainingRecordsEl.innerHTML = `<p class='compact-status'>${escapeHtml(error.message)}</p>`;
  }
}

function renderPromptLeaderboard(items = []) {
  if (!promptLeaderboardEl) return;
  promptLeaderboardEl.innerHTML = items.length
    ? items.map((item) => `
      <div class="audiogen-job">
        <div>
          <strong>${escapeHtml(item.emotion || "emotion")} prompt</strong>
          <span>${escapeHtml(item.prompt || "")}</span>
        </div>
        <div class="audiogen-job-meta">
          <span class="status-pill ok">${escapeHtml(item.useful_votes || 0)} useful</span>
          <span class="status-pill">${escapeHtml(item.uses || 0)} use(s)</span>
        </div>
        <div class="button-row">
          <button type="button" data-use-prompt="${escapeHtml(item.prompt || "")}" data-use-emotion="${escapeHtml(item.emotion || "joy")}">Use prompt</button>
          ${item.latest_src ? `<button type="button" class="secondary" data-play-src="${escapeHtml(item.latest_src)}" data-play-label="${escapeHtml(item.emotion || "AudioGen")} prompt result">Load player</button>` : ""}
        </div>
      </div>
    `).join("")
    : "<p class='compact-status'>No reusable prompts yet.</p>";
}

function renderSessionReplay(data = {}) {
  if (!sessionReplayEl) return;
  const session = data.session || {};
  const events = session.events || [];
  const feedback = data.feedback || [];
  if (!session.id) {
    sessionReplayEl.innerHTML = "<p class='compact-status'>Select a session to replay it.</p>";
    return;
  }
  const feedbackBySession = feedback.length
    ? `<div class="creative-replay-feedback"><strong>Feedback</strong>${feedback.map((item) => `<span>${escapeHtml((item.rating || "").replaceAll("_", " "))}</span>`).join("")}</div>`
    : "";
  sessionReplayEl.innerHTML = `
    <div class="creative-replay-header">
      <strong>${escapeHtml(session.title || session.id)}</strong>
      <span>${escapeHtml(events.length)} event(s) · ${escapeHtml(session.updated_at || "")}</span>
    </div>
    ${events.length ? events.map((event, index) => `
      <div class="creative-replay-step">
        <span class="status-pill">${escapeHtml(index + 1)}</span>
        <div>
          <strong>${escapeHtml((event.type || "note").replaceAll("_", " "))}</strong>
          <p>${escapeHtml(event.question || event.prompt || event.summary || event.src || "Session event")}</p>
          ${event.answer ? `<p class="compact-status">${escapeHtml(event.answer)}</p>` : ""}
          ${event.technical_score !== undefined ? `<span class="status-pill ok">${escapeHtml(event.technical_score)}/100</span>` : ""}
          ${event.src ? `<button type="button" class="secondary" data-play-src="${escapeHtml(event.src)}" data-play-label="${escapeHtml(event.type || "Audio_Gen audio")}">Load player</button>` : ""}
        </div>
      </div>
    `).join("") : "<p class='compact-status'>No events recorded for this session.</p>"}
    ${feedbackBySession}
  `;
}

async function loadSessionReplay(sessionId) {
  if (!sessionReplayEl || !sessionId) return;
  sessionReplayEl.innerHTML = "<p class='compact-status'>Loading session replay...</p>";
  try {
    const data = await api(`/api/admin/creative-lab/session?id=${encodeURIComponent(sessionId)}`);
    renderSessionReplay(data);
  } catch (error) {
    sessionReplayEl.innerHTML = `<p class='compact-status'>${escapeHtml(error.message)}</p>`;
  }
}

async function loadSessions() {
  if (!sessionsEl) return;
  try {
    const data = await api("/api/admin/creative-lab/sessions?limit=10");
    const sessions = data.sessions || [];
    renderQualityMetrics(data.metrics || {});
    renderRepairRecommendations(data.repair_recommendations || []);
    renderRepairQueue(data.repair_queue || []);
    renderPromptLeaderboard(data.prompt_leaderboard || []);
    await loadTrainingRecords();
    sessionsEl.innerHTML = sessions.length ? sessions.map(renderSession).join("") : "<p class='compact-status'>No Audio_Gen sessions yet.</p>";
  } catch (error) {
    sessionsEl.innerHTML = `<p class='compact-status'>${escapeHtml(error.message)}</p>`;
  }
}

async function sendToMixReview(src, title = "") {
  if (!src) return;
  if (mixReviewResultEl) mixReviewResultEl.textContent = "Running Mix Review analysis...";
  try {
    const data = await api("/api/admin/creative-lab/mix-review", {
      method: "POST",
      body: JSON.stringify({
        session_id: currentSessionId,
        src,
        title: title || "Audio_Gen render",
        version: "Audio_Gen",
      }),
    });
    const review = data.review || {};
    if (mixReviewResultEl) {
      mixReviewResultEl.innerHTML = `
        <div class="answer-meta">
          <span class="status-pill ok">Mix Review ready</span>
          <span class="status-pill">${escapeHtml(review.metrics?.technical_score ?? "n/a")}/100</span>
        </div>
        <p>${escapeHtml(review.summary || "Mix Review complete.")}</p>
        <div class="button-row">
          <a class="button-link" href="/api/admin/mix-review-report/${encodeURIComponent(review.id)}.html" target="_blank" rel="noopener">Open report</a>
          ${review.kenn_handoff?.prompt ? `<button type="button" class="secondary" data-creative-question="${escapeHtml(review.kenn_handoff.prompt)}">Ask KENN about this review</button>` : ""}
        </div>
      `;
    }
    await loadSessions();
    setStatus("Mix Review analysis created.");
  } catch (error) {
    if (mixReviewResultEl) mixReviewResultEl.textContent = error.message;
    setStatus(error.message);
  }
}

async function sendCreativeFeedback(rating, target) {
  const payload = {
    session_id: currentSessionId,
    rating,
    target,
    question: lastKennTurn?.question || "",
    answer: lastKennTurn?.answer || "",
    prompt: promptInput?.value?.trim() || "",
    emotion: selectedEmotion(),
    src: lastAudioResult?.src || "",
  };
  try {
    await api("/api/admin/creative-lab/feedback", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    setStatus("Audio_Gen feedback saved.");
    await loadSessions();
  } catch (error) {
    setStatus(error.message);
  }
}

async function createRepairDraft(feedbackId) {
  if (!feedbackId) return;
  setStatus("Creating KENN repair draft...");
  try {
    const data = await api("/api/admin/creative-lab/repair", {
      method: "POST",
      body: JSON.stringify({ feedback_id: feedbackId }),
    });
    setStatus(data.message || "KENN repair draft created.");
    await loadSessions();
  } catch (error) {
    setStatus(error.message);
  }
}

async function promoteRepair(feedbackId) {
  if (!feedbackId) return;
  setStatus("Promoting repair, rebuilding KENN, and running eval...");
  try {
    const data = await api("/api/admin/creative-lab/repair/promote", {
      method: "POST",
      body: JSON.stringify({ feedback_id: feedbackId }),
    });
    const failures = data.eval?.failures || [];
    setStatus(failures.length ? `${data.message} ${failures.join("; ")}` : data.message || "Repair promoted.");
    await loadSessions();
    await loadRepairComparison(feedbackId);
  } catch (error) {
    setStatus(error.message);
  }
}

async function promoteRepairEval(feedbackId) {
  if (!feedbackId) return;
  setStatus("Adding passing repair case to KENN regression suite...");
  try {
    const data = await api("/api/admin/creative-lab/repair/promote-eval", {
      method: "POST",
      body: JSON.stringify({ feedback_id: feedbackId }),
    });
    setStatus(data.message || "Repair case added to regression suite.");
    await loadSessions();
    await loadRepairComparison(feedbackId);
  } catch (error) {
    setStatus(error.message);
  }
}

async function runRepairRecommendation(feedbackId) {
  if (!feedbackId) return;
  setStatus("Running repair recommendation...");
  try {
    const data = await api("/api/admin/creative-lab/repair/run-recommendation", {
      method: "POST",
      body: JSON.stringify({ feedback_id: feedbackId }),
    });
    setStatus(data.message || data.recommendation?.action || "Repair recommendation completed.");
    await loadSessions();
    await loadRepairComparison(feedbackId);
  } catch (error) {
    setStatus(error.message);
    await loadRepairComparison(feedbackId);
  }
}

async function exportRepairTraining() {
  setStatus("Exporting Audio_Gen repair training records...");
  try {
    const data = await api("/api/admin/creative-lab/repair/export-training", {
      method: "POST",
      body: JSON.stringify({}),
    });
    setStatus(`${data.message || "Repair training export complete."} ${data.path || ""}`.trim());
    await loadTrainingRecords();
  } catch (error) {
    setStatus(error.message);
  }
}

async function exportApprovedRepairTraining() {
  setStatus("Exporting approved Audio_Gen repair training records...");
  try {
    const data = await api("/api/admin/creative-lab/repair/export-approved-training", {
      method: "POST",
      body: JSON.stringify({}),
    });
    setStatus(`${data.message || "Approved repair training export complete."} ${data.path || ""}`.trim());
    await loadTrainingRecords();
  } catch (error) {
    setStatus(error.message);
  }
}

async function validateApprovedRepairTraining() {
  setStatus("Validating approved Audio_Gen repair training export...");
  try {
    const data = await api("/api/admin/creative-lab/repair/validate-approved-training", {
      method: "POST",
      body: JSON.stringify({}),
    });
    setStatus(data.message || "Approved repair training validation complete.");
    await loadTrainingRecords({ validation: data });
  } catch (error) {
    setStatus(error.message);
  }
}

async function reviewTrainingRecord(recordId, decision) {
  if (!recordId || !decision) return;
  setStatus(`Marking training record as ${decision.replaceAll("_", " ")}...`);
  try {
    const data = await api("/api/admin/creative-lab/repair/review-training-record", {
      method: "POST",
      body: JSON.stringify({ record_id: recordId, decision }),
    });
    setStatus(data.message || "Training record reviewed.");
    await loadTrainingRecords();
  } catch (error) {
    setStatus(error.message);
  }
}

document.addEventListener("click", (event) => {
  const target = event.target;
  if (!(target instanceof HTMLElement)) return;
  const src = target.dataset.playSrc;
  if (src) loadPlayer(src, target.dataset.playLabel || "AudioGen audio");
  const delegatedQuestion = target.dataset.creativeQuestion;
  if (delegatedQuestion && questionInput) {
    questionInput.value = delegatedQuestion;
    questionInput.focus();
  }
  const reviewSrc = target.dataset.sendMixReview;
  if (reviewSrc) sendToMixReview(reviewSrc, target.dataset.reviewTitle || "");
  const feedback = target.dataset.creativeFeedback;
  if (feedback) sendCreativeFeedback(feedback, target.dataset.feedbackTarget || "");
  const repairId = target.dataset.createRepair;
  if (repairId) createRepairDraft(repairId);
  const promoteId = target.dataset.promoteRepair;
  if (promoteId) promoteRepair(promoteId);
  const promoteEvalId = target.dataset.promoteRepairEval;
  if (promoteEvalId) promoteRepairEval(promoteEvalId);
  const runRecommendationId = target.dataset.runRepairRecommendation;
  if (runRecommendationId) runRepairRecommendation(runRecommendationId);
  if (target.dataset.exportRepairTraining) exportRepairTraining();
  if (target.dataset.exportApprovedRepairTraining) exportApprovedRepairTraining();
  if (target.dataset.validateApprovedRepairTraining) validateApprovedRepairTraining();
  const trainingRecordId = target.dataset.reviewTrainingRecord;
  if (trainingRecordId) reviewTrainingRecord(trainingRecordId, target.dataset.reviewDecision || "");
  const compareId = target.dataset.compareRepair;
  if (compareId) loadRepairComparison(compareId);
  const sessionId = target.dataset.loadSession;
  if (sessionId) {
    currentSessionId = sessionId;
    window.localStorage.setItem("creativeLabSessionId", sessionId);
    setStatus(`Loaded Audio_Gen session ${sessionId}.`);
    loadSessions();
    loadSessionReplay(sessionId);
  }
  const replaySession = target.dataset.replaySession;
  if (replaySession) {
    loadSessionReplay(replaySession);
  }
  const usePrompt = target.dataset.usePrompt;
  if (usePrompt) {
    if (promptInput) promptInput.value = usePrompt;
    setEmotion(target.dataset.useEmotion || "joy");
    promptInput?.focus();
    setStatus("Prompt loaded into AudioGen.");
  }
});

document.querySelector("#creative-play")?.addEventListener("click", () => {
  if (player?.src) player.play();
});

document.querySelector("#creative-pause")?.addEventListener("click", () => {
  player?.pause();
});

document.querySelector("#creative-stop")?.addEventListener("click", () => {
  if (!player) return;
  player.pause();
  player.currentTime = 0;
});

document.querySelector("#creative-refresh")?.addEventListener("click", () => {
  loadStatus();
  loadJobs();
  loadHistory();
});
document.querySelector("#creative-jobs-refresh")?.addEventListener("click", loadJobs);
document.querySelector("#creative-history-refresh")?.addEventListener("click", loadHistory);
document.querySelector("#creative-sessions-refresh")?.addEventListener("click", loadSessions);
document.querySelector("#creative-training-refresh")?.addEventListener("click", loadTrainingRecords);

unlockButton?.addEventListener("click", async () => {
  setStatus("Signing in...");
  try {
    await api("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ password: passwordInput?.value || "" }),
    });
    if (passwordInput) passwordInput.value = "";
    if (authPanel) authPanel.hidden = true;
    await boot();
  } catch (error) {
    setStatus(error.message);
  }
});

async function boot() {
  const active = await sessionActive();
  if (authPanel) authPanel.hidden = active;
  if (!active) {
    setStatus("Enter your dashboard password to unlock Audio_Gen.");
    await loadStatus();
    return;
  }
  setStatus("Audio_Gen ready.");
  await loadStatus();
  await loadJobs();
  await loadHistory();
  await loadSessions();
}

setEmotion(selectedEmotion());
boot();
