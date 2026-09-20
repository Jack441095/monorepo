const loginForm = document.querySelector("#demo-login-form");
const passwordInput = document.querySelector("#demo-password");
const statusEl = document.querySelector("#demo-status");
const appEl = document.querySelector("#demo-app");
const startersEl = document.querySelector("#demo-starters");
const messagesEl = document.querySelector("#demo-messages");
const askForm = document.querySelector("#demo-ask-form");
const questionInput = document.querySelector("#demo-question");
const logoutButton = document.querySelector("#demo-logout");
const statsEl = document.querySelector("#demo-session-stats");
const liveSuggestEl = document.querySelector("#demo-live-suggest");

const conversation = [];
const payloads = new Map();
let localQuestionCount = 0;
let messageId = 0;
let suggestTimer = null;
let greetingRendered = false;

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
  if (!response.ok) throw new Error(data.error || "Request failed");
  return data;
}

function setUnlocked(unlocked) {
  appEl.hidden = !unlocked;
  loginForm.hidden = unlocked;
}

function renderStats(analytics = {}) {
  if (!statsEl) return;
  const total = analytics.total_recent_questions ?? 0;
  const weakRate = Math.round(Number(analytics.weak_rate || 0) * 100);
  const feedbackRate = Math.round(Number(analytics.feedback_rate || 0) * 100);
  statsEl.innerHTML = `
    <div><strong>${escapeHtml(localQuestionCount)}</strong><span>Your questions</span></div>
    <div><strong>${escapeHtml(total)}</strong><span>Recent demo asks</span></div>
    <div><strong>${escapeHtml(`${weakRate}%`)}</strong><span>Weak-answer rate</span></div>
    <div><strong>${escapeHtml(`${feedbackRate}%`)}</strong><span>Feedback rate</span></div>
  `;
}

function appendMessage(role, html) {
  const item = document.createElement("article");
  item.className = `demo-message ${role}`;
  item.innerHTML = html;
  messagesEl.append(item);
  messagesEl.scrollTop = messagesEl.scrollHeight;
  return item;
}

function renderWelcome() {
  if (greetingRendered || !messagesEl) return;
  greetingRendered = true;
  appendMessage(
    "assistant",
    `<div class="demo-answer-head">
       <div>
         <strong>KENN</strong>
         <p class="compact-status">Grounded chat from approved notes</p>
       </div>
     </div>
     <p>Hi. Ask me about Ableton, mixing, mastering, stems, vocals, or game-audio workflow. I will answer from the local knowledge base and suggest useful next questions.</p>`
  );
}

function renderQuestionButtons(container, questions) {
  if (!container) return;
  container.innerHTML = (questions || [])
    .slice(0, 6)
    .map((question) => `<button type="button" class="chip-button" data-question="${escapeHtml(question)}">${escapeHtml(question)}</button>`)
    .join("");
  container.querySelectorAll("[data-question]").forEach((button) => {
    button.addEventListener("click", () => askQuestion(button.dataset.question || ""));
  });
}

function renderAnswer(payload) {
  const sourceQuality = payload.source_quality ? `${payload.source_quality} sources` : "source check pending";
  const id = `answer-${++messageId}`;
  payloads.set(id, payload);
  const sources = (payload.sources || [])
    .slice(0, 4)
    .map((source) => `<li>${escapeHtml(source.label || source.title || source.source || "source")}</li>`)
    .join("");
  const followups = (payload.related_questions || [])
    .slice(0, 4)
    .map((question) => `<button type="button" class="chip-button" data-question="${escapeHtml(question)}">${escapeHtml(question)}</button>`)
    .join("");
  const assistantName = payload.conversation_only ? "KENN" : "Answer";
  appendMessage(
    "assistant",
     `<div class="demo-answer-head">
       <div>
         <strong>${escapeHtml(assistantName)}</strong>
         <p class="compact-status">${escapeHtml((payload.topics || []).join(", ") || "No topic match")}</p>
       </div>
       ${payload.conversation_only ? "" : `<span class="status-pill">${escapeHtml(payload.confidence || "unknown")} confidence · ${escapeHtml(sourceQuality)}</span>`}
     </div>
     <pre class="ableton-answer-text">${escapeHtml(payload.answer || "No answer.")}</pre>
     ${sources ? `<h3>Sources</h3><ul>${sources}</ul>` : ""}
     ${followups ? `<div class="chip-row">${followups}</div>` : ""}
     ${payload.conversation_only ? "" : `<form class="demo-feedback" data-answer-id="${escapeHtml(id)}">
       <input name="comment" placeholder="Optional feedback for improving this answer">
       <button type="button" data-rating="useful">Useful</button>
       <button type="button" class="secondary" data-rating="not_useful">Needs work</button>
     </form>`}`
  );
  messagesEl.querySelectorAll("[data-question]").forEach((button) => {
    button.addEventListener("click", () => askQuestion(button.dataset.question || ""));
  });
  messagesEl.querySelectorAll("[data-rating]").forEach((button) => {
    button.addEventListener("click", () => sendFeedback(button));
  });
}

async function sendFeedback(button) {
  const form = button.closest(".demo-feedback");
  const answerId = form?.dataset.answerId || "";
  const payload = payloads.get(answerId);
  if (!payload) return;
  const comment = form?.querySelector("input")?.value || "";
  try {
    await api("/api/demo/feedback", {
      method: "POST",
      body: JSON.stringify({
        question: payload.question,
        rating: button.dataset.rating,
        comment,
        confidence: payload.confidence,
        source_quality: payload.source_quality,
        answer: payload.answer,
        sources: payload.sources || [],
        topics: payload.topics || [],
      }),
    });
    statusEl.textContent = button.dataset.rating === "not_useful" ? "Feedback saved. This will be reviewed as an improvement candidate." : "Feedback saved.";
    form.classList.add("feedback-saved");
    form.querySelectorAll("button").forEach((item) => {
      item.disabled = true;
    });
  } catch (error) {
    statusEl.textContent = error.message;
  }
}

async function askQuestion(question) {
  const clean = question.trim();
  if (!clean) return;
  renderWelcome();
  appendMessage("user", `<strong>You</strong><p>${escapeHtml(clean)}</p>`);
  questionInput.value = "";
  renderQuestionButtons(liveSuggestEl, []);
  statusEl.textContent = "Thinking...";
  try {
    const payload = await api("/api/demo/ask", {
      method: "POST",
      body: JSON.stringify({
        question: clean,
        history: conversation.slice(-6),
        session_id: localStorage.getItem("kenn_session_id") || "",
      }),
    });
    localQuestionCount += 1;
    conversation.push({ role: "user", content: clean });
    conversation.push({ role: "assistant", content: payload.answer || "" });
    // Persist session_id from the response
    if (payload.session?.session_id) {
      localStorage.setItem("kenn_session_id", payload.session.session_id);
    }
    renderAnswer(payload);
    const session = await api("/api/demo/session");
    renderStats(session.analytics || {});
    statusEl.textContent = "";
  } catch (error) {
    statusEl.textContent = error.message;
  }
}

async function loadCatalog() {
  try {
    const catalog = await api("/api/demo/catalog");
    renderQuestionButtons(startersEl, catalog.suggested_questions || []);
    renderQuestionButtons(liveSuggestEl, (catalog.suggested_questions || []).slice(0, 4));
  } catch (error) {
    statusEl.textContent = error.message;
  }
}

async function updateLiveSuggestions() {
  const query = questionInput?.value?.trim() || "";
  if (!query) {
    try {
      const catalog = await api("/api/demo/catalog");
      renderQuestionButtons(liveSuggestEl, (catalog.suggested_questions || []).slice(0, 4));
    } catch {
      renderQuestionButtons(liveSuggestEl, []);
    }
    return;
  }
  try {
    const data = await api(`/api/demo/suggest?q=${encodeURIComponent(query)}`);
    renderQuestionButtons(liveSuggestEl, data.suggestions || []);
  } catch {
    renderQuestionButtons(liveSuggestEl, []);
  }
}

async function checkSession() {
  const session = await api("/api/demo/session");
  if (!session.configured) {
    statusEl.textContent = "Demo access is not configured. Set AUDIO_TOO_DEMO_PASSWORD in .env.";
    setUnlocked(false);
    return;
  }
  setUnlocked(session.authenticated);
  if (session.authenticated) {
    renderWelcome();
    renderStats(session.analytics || {});
    loadCatalog();
  }
}

loginForm?.addEventListener("submit", async (event) => {
  event.preventDefault();
  statusEl.textContent = "Signing in...";
  try {
    await api("/api/demo/login", {
      method: "POST",
      body: JSON.stringify({ password: passwordInput.value }),
    });
    passwordInput.value = "";
    statusEl.textContent = "";
    setUnlocked(true);
    renderWelcome();
    const session = await api("/api/demo/session");
    renderStats(session.analytics || {});
    loadCatalog();
  } catch (error) {
    statusEl.textContent = error.message;
  }
});

logoutButton?.addEventListener("click", async () => {
  await api("/api/demo/logout", { method: "POST", body: "{}" });
  setUnlocked(false);
});

askForm?.addEventListener("submit", (event) => {
  event.preventDefault();
  askQuestion(questionInput.value || "");
});

questionInput?.addEventListener("input", () => {
  clearTimeout(suggestTimer);
  suggestTimer = setTimeout(updateLiveSuggestions, 180);
});

checkSession().catch((error) => {
  statusEl.textContent = error.message;
});
