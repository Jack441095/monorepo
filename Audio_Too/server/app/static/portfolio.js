const codebaseGrid = document.querySelector("#portfolio-codebases");
const audioGrid = document.querySelector("#portfolio-audio");
const statGrid = document.querySelector("#portfolio-stats");
const statusEl = document.querySelector("#portfolio-status");

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function renderCodebases(items = []) {
  if (!codebaseGrid) return;
  codebaseGrid.innerHTML = items
    .map(
      (item) => `
        <article class="portfolio-feature">
          <p class="eyebrow">${escapeHtml(item.type || "Project")}</p>
          <h3>${escapeHtml(item.title)}</h3>
          <p>${escapeHtml(item.description)}</p>
          <ul class="portfolio-tags">
            ${(item.tags || []).map((tag) => `<li>${escapeHtml(tag)}</li>`).join("")}
          </ul>
        </article>
      `
    )
    .join("");
}

function renderStats(items = []) {
  if (!statGrid) return;
  statGrid.innerHTML = items
    .map((item) => `<div><strong>${escapeHtml(item.value)}</strong><span>${escapeHtml(item.label)}</span></div>`)
    .join("");
}

function renderAudio(items = []) {
  if (!audioGrid) return;
  audioGrid.innerHTML = items
    .map(
      (item) => `
        <article>
          <h3>${escapeHtml(item.title)}</h3>
          <p>${escapeHtml(item.description)}</p>
          <audio controls preload="none" src="${escapeHtml(item.src)}"></audio>
        </article>
      `
    )
    .join("");
}

async function loadPortfolio() {
  try {
    const response = await fetch("/api/portfolio");
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Could not load portfolio.");
    renderCodebases(data.codebases || []);
    renderStats(data.stats || []);
    renderAudio(data.audio || []);
    if (statusEl) statusEl.textContent = "";
  } catch (error) {
    if (statusEl) statusEl.textContent = error.message;
  }
}

loadPortfolio();
