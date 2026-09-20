// api_client.js — Shared API client and auth session management

const passwordInput = document.querySelector("#admin-password");
const unlockButton = document.querySelector("#admin-unlock");
const logoutButton = document.querySelector("#admin-logout");
const statusEl = document.querySelector("#admin-status");
const metricsEl = document.querySelector("#admin-metrics");
const sections = {
  projects: document.querySelector("#admin-projects"),
  clients: document.querySelector("#admin-clients"),
  leads: document.querySelector("#admin-leads"),
  enquiries: document.querySelector("#admin-enquiries"),
  campaigns: document.querySelector("#admin-campaigns"),
  invoices: document.querySelector("#admin-invoices"),
  drafts: document.querySelector("#admin-drafts"),
};
const projectWorkspaceEl = document.querySelector("#project-workspace");
const draftForm = document.querySelector("#draft-form");
const tabButtons = document.querySelectorAll(".control-tabs .tab");
const tabPanels = document.querySelectorAll(".tab-panel");

let dashboardCache = null;
let invoiceLinkMap = {};
let selectedNote = "";
let selectedKnowledgeNote = "";
let lastAbletonPayload = null;
let trainingRecordsData = null;
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

async function authenticatedFetch(input, options = {}) {
  const method = String(options.method || "GET").toUpperCase();
  const headers = new Headers(options.headers || {});
  if (!["GET", "HEAD", "OPTIONS"].includes(method) && String(input) !== "/api/auth/login") {
    await ensureCsrfToken();
    if (csrfToken) headers.set("X-CSRF-Token", csrfToken);
  }
  return browserFetch(input, { ...options, credentials: "same-origin", headers });
}
window.fetch = authenticatedFetch;

function fetchOptions(options = {}) {
  return {
    ...options,
    credentials: "same-origin",
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
  };
}

function idempotencyKey(prefix = "request") {
  if (globalThis.crypto?.randomUUID) return `${prefix}:${globalThis.crypto.randomUUID()}`;
  return `${prefix}:${Date.now()}:${Math.random().toString(16).slice(2)}`;
}

async function sessionActive() {
  const response = await fetch("/api/auth/session", fetchOptions());
  const data = await response.json();
  csrfToken = data.csrf_token || "";
  return Boolean(data.authenticated);
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

async function api(path, options = {}) {
  const response = await fetch(path, fetchOptions(options));
  const data = await response.json();
  if (data.csrf_token) csrfToken = data.csrf_token;
  if (response.status === 401) throw new Error(data.error || "Sign in required.");
  if (!response.ok) throw new Error(data.error || data.output || "Request failed");
  return data;
}

unlockButton.addEventListener("click", async () => {
  statusEl.textContent = "Signing in…";
  try {
    const response = await fetch(
      "/api/auth/login",
      fetchOptions({ method: "POST", body: JSON.stringify({ password: passwordInput.value }) })
    );
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Sign in failed.");
    passwordInput.value = "";
    statusEl.textContent = "Signed in.";
    await loadAdmin();
    await loadHub();
  } catch (error) {
    statusEl.textContent = error.message;
  }
});

logoutButton?.addEventListener("click", async () => {
  await fetch("/api/auth/logout", fetchOptions({ method: "POST", body: "{}" }));
  csrfToken = "";
  statusEl.textContent = "Signed out.";
});

document.querySelectorAll("[data-refresh]").forEach((button) => button.addEventListener("click", () => {
  loadAdmin();
  loadHub();
}));
