const askForm = document.querySelector("#business-ask-form");
const askInput = document.querySelector("#business-ask-input");
const askStatus = document.querySelector("#business-ask-status");
const askAnswer = document.querySelector("#business-ask-answer");
const askDisclaimer = document.querySelector("#business-ask-disclaimer");
const suggestRow = document.querySelector("#business-suggest-row");

async function loadCatalog() {
  try {
    const response = await fetch("/api/public/business");
    const data = await response.json();
    if (!response.ok || !suggestRow) return;
    const questions = data.suggested_questions || [];
    suggestRow.innerHTML = questions
      .map(
        (q) =>
          `<button type="button" class="chip-button" data-question="${encodeURIComponent(q)}">${escapeHtml(q)}</button>`
      )
      .join("");
    suggestRow.querySelectorAll("button").forEach((button) => {
      button.addEventListener("click", () => {
        if (askInput) askInput.value = decodeURIComponent(button.dataset.question || "");
        askForm?.requestSubmit();
      });
    });
    if (askDisclaimer && data.disclaimer) {
      askDisclaimer.textContent = data.disclaimer;
    }
  } catch {
    /* catalog is optional for UX */
  }
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

askForm?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const question = askInput?.value?.trim();
  if (!question) return;
  if (askStatus) askStatus.textContent = "Looking up…";
  if (askAnswer) askAnswer.textContent = "";

  try {
    const response = await fetch("/api/public/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    });
    const result = await response.json();

    if (response.status === 429) {
      if (askStatus) askStatus.textContent = result.error || "Too many questions. Try again later.";
      return;
    }
    if (!response.ok) {
      if (askStatus) askStatus.textContent = result.error || "Could not answer that question.";
      return;
    }

    if (askAnswer) askAnswer.textContent = result.answer || "";
    if (askDisclaimer && result.disclaimer) askDisclaimer.textContent = result.disclaimer;
    const confidence = result.confidence || "medium";
    if (askStatus) {
      askStatus.textContent =
        confidence === "low"
          ? "General guidance — send an enquiry for a confirmed quote."
          : "Indicative answer — use the enquiry form below to confirm scope and price.";
    }
  } catch {
    if (askStatus) askStatus.textContent = "Network error. Check that the local server is running.";
  }
});

loadCatalog();
