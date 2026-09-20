const params = new URLSearchParams(window.location.search);
const token = params.get("token") || "";

const projectLine = document.querySelector("#stem-project-line");
const hintsEl = document.querySelector("#stem-hints");
const limitsEl = document.querySelector("#stem-limits");
const invalidPanel = document.querySelector("#stem-invalid");
const formPanel = document.querySelector("#stem-form-panel");
const donePanel = document.querySelector("#stem-done");
const form = document.querySelector("#stem-upload-form");
const statusEl = document.querySelector("#stem-upload-status");
const doneMessage = document.querySelector("#stem-done-message");

async function loadInfo() {
  if (!token) {
    showInvalid();
    return;
  }
  try {
    const response = await fetch(`/api/public/stem-upload/info?token=${encodeURIComponent(token)}`);
    const data = await response.json();
    if (!response.ok || !data.ok) {
      showInvalid();
      return;
    }
    if (projectLine) {
      projectLine.textContent = `Upload stems for: ${data.project} (${data.service || "project"})`;
    }
    if (hintsEl && data.hints) {
      hintsEl.innerHTML = data.hints.map((h) => `<li>${escapeHtml(h)}</li>`).join("");
    }
    if (limitsEl) {
      limitsEl.textContent = `Max ${data.max_mb} MB · allowed: ${(data.allowed_types || []).join(", ")}`;
    }
    invalidPanel.hidden = true;
    formPanel.hidden = false;
  } catch {
    showInvalid();
  }
}

function showInvalid() {
  if (invalidPanel) invalidPanel.hidden = false;
  if (formPanel) formPanel.hidden = true;
  if (donePanel) donePanel.hidden = true;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

form?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const fileInput = form.querySelector('input[name="file"]');
  const file = fileInput?.files?.[0];
  if (!file) return;

  if (statusEl) statusEl.textContent = `Uploading ${file.name}…`;
  const formData = new FormData(form);
  formData.append("token", token);

  try {
    const response = await fetch("/api/public/stem-upload", {
      method: "POST",
      body: formData,
    });
    const result = await response.json();
    if (!response.ok || !result.ok) {
      if (statusEl) statusEl.textContent = result.error || "Upload failed.";
      return;
    }
    if (formPanel) formPanel.hidden = true;
    if (donePanel) donePanel.hidden = false;
    if (doneMessage) {
      doneMessage.textContent = result.message || "Upload received. Thank you.";
    }
  } catch {
    if (statusEl) statusEl.textContent = "Network error during upload.";
  }
});

loadInfo();
