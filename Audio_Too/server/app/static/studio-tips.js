const form = document.querySelector("#studio-tips-form");
const input = document.querySelector("#studio-tips-input");
const typeaheadList = document.querySelector("#studio-tips-typeahead");
const statusEl = document.querySelector("#studio-tips-status");
const answerEl = document.querySelector("#studio-tips-answer");
const sourcesEl = document.querySelector("#studio-tips-sources");
const suggestRow = document.querySelector("#studio-tips-suggest");
const disclaimerEl = document.querySelector("#tips-disclaimer");
const statusLine = document.querySelector("#tips-status-line");

let suggestTimer = null;
let suggestAbort = null;

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function hideTypeahead() {
  if (!typeaheadList) return;
  typeaheadList.hidden = true;
  typeaheadList.innerHTML = "";
}

function renderChips(questions) {
  if (!suggestRow) return;
  suggestRow.innerHTML = (questions || [])
    .map(
      (q) =>
        `<button type="button" class="chip-button" data-question="${encodeURIComponent(q)}">${escapeHtml(q)}</button>`,
    )
    .join("");
  suggestRow.querySelectorAll("button").forEach((button) => {
    button.addEventListener("click", () => {
      if (input) input.value = decodeURIComponent(button.dataset.question || "");
      hideTypeahead();
      form?.requestSubmit();
    });
  });
}

function showTypeahead(items) {
  if (!typeaheadList) return;
  if (!items.length) {
    hideTypeahead();
    return;
  }
  typeaheadList.innerHTML = items
    .map(
      (q) =>
        `<li><button type="button" data-suggest="${escapeHtml(q)}">${escapeHtml(q)}</button></li>`,
    )
    .join("");
  typeaheadList.hidden = false;
  typeaheadList.querySelectorAll("button").forEach((button) => {
    button.addEventListener("click", () => {
      const q = button.dataset.suggest || "";
      if (input) input.value = q;
      hideTypeahead();
      form?.requestSubmit();
    });
  });
}

async function fetchSuggestions(query) {
  if (suggestAbort) suggestAbort.abort();
  suggestAbort = new AbortController();
  const params = new URLSearchParams({ q: query, limit: "8" });
  const response = await fetch(`/api/public/tips/suggest?${params}`, { signal: suggestAbort.signal });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "Suggest failed");
  return data.suggestions || [];
}

function scheduleTypeahead() {
  const query = input?.value?.trim() || "";
  clearTimeout(suggestTimer);
  if (query.length < 2) {
    hideTypeahead();
    return;
  }
  suggestTimer = setTimeout(async () => {
    try {
      showTypeahead(await fetchSuggestions(query));
    } catch (error) {
      if (error.name !== "AbortError") hideTypeahead();
    }
  }, 220);
}

async function loadCatalog() {
  try {
    const response = await fetch("/api/public/tips");
    const data = await response.json();
    if (!response.ok) return;
    if (disclaimerEl && data.disclaimer) disclaimerEl.textContent = data.disclaimer;
    if (statusLine) {
      statusLine.textContent = data.retrieval_only
        ? "Retrieval-only · suggestions from your notes and recent questions"
        : "";
    }
    renderChips(data.suggested_questions);
  } catch {
    /* optional */
  }
}

function appendFollowupChips(questions) {
  if (!suggestRow || !questions?.length) return;
  questions.slice(0, 3).forEach((q) => {
    const exists = [...suggestRow.querySelectorAll("button")].some(
      (b) => decodeURIComponent(b.dataset.question || "") === q,
    );
    if (exists) return;
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "chip-button";
    btn.dataset.question = encodeURIComponent(q);
    btn.textContent = q;
    btn.addEventListener("click", () => {
      if (input) input.value = q;
      form?.requestSubmit();
    });
    suggestRow.appendChild(btn);
  });
}

form?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const question = input?.value?.trim();
  if (!question) return;
  hideTypeahead();
  if (statusEl) statusEl.textContent = "Searching your notes…";
  if (answerEl) answerEl.textContent = "";
  if (sourcesEl) sourcesEl.innerHTML = "";

  try {
    const response = await fetch("/api/public/tips/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        question,
        session_id: localStorage.getItem("kenn_session_id") || "",
      }),
    });
    const result = await response.json();

    if (response.status === 429) {
      if (statusEl) statusEl.textContent = result.error || "Too many questions.";
      return;
    }
    if (!response.ok) {
      if (statusEl) statusEl.textContent = result.error || "Could not answer.";
      return;
    }

    // Persist session_id from the response
    if (result.session?.session_id) {
      localStorage.setItem("kenn_session_id", result.session.session_id);
    }

    if (answerEl) answerEl.textContent = result.answer || "";
    const conf = result.confidence || "medium";
    if (statusEl) {
      statusEl.textContent =
        conf === "low"
          ? "Weak match — consider adding an approved note (logged for dashboard review)."
          : `Confidence: ${conf}${result.retrieval_only ? " · retrieval-only" : ""}`;
    }
    if (sourcesEl && result.sources?.length) {
      sourcesEl.innerHTML = `<p class="compact-status"><strong>Sources:</strong> ${result.sources
        .map((s) => escapeHtml(s.label || s.source || ""))
        .join(" · ")}</p>`;
    }
    appendFollowupChips(result.related_questions);
  } catch {
    if (statusEl) statusEl.textContent = "Network error. Run ./start.sh and try again.";
  }
});

input?.addEventListener("input", scheduleTypeahead);
input?.addEventListener("focus", scheduleTypeahead);
input?.addEventListener("keydown", (event) => {
  if (event.key === "Escape") hideTypeahead();
});
document.addEventListener("click", (event) => {
  if (!event.target.closest(".composer-field")) hideTypeahead();
});

loadCatalog();
