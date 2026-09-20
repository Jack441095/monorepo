/**
 * Blind A/B Multitrack Producer Listening Benchmark Logic.
 */

let currentSession = null;
let activeMixIndex = 1;

// Rating submission is an authenticated dashboard write (internal-evaluation
// panel, not a public form) -- attach the CSRF token the same way automix.js
// does, since the browser session cookie alone isn't enough for POST.
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

async function authedFetch(input, options = {}) {
  const method = String(options.method || "GET").toUpperCase();
  const headers = new Headers(options.headers || {});
  if (!["GET", "HEAD", "OPTIONS"].includes(method)) {
    await ensureCsrfToken();
    if (csrfToken) headers.set("X-CSRF-Token", csrfToken);
  }
  return browserFetch(input, { ...options, credentials: "same-origin", headers });
}

function updateVal(elementId, val) {
  const el = document.getElementById(elementId);
  if (el) el.textContent = `${val} / 5`;
}

function switchMix(idx) {
  activeMixIndex = idx;
  const btn1 = document.getElementById("btnMix1");
  const btn2 = document.getElementById("btnMix2");
  const audio = document.getElementById("benchmarkAudio");

  if (idx === 1) {
    btn1.classList.add("active");
    btn2.classList.remove("active");
  } else {
    btn2.classList.add("active");
    btn1.classList.remove("active");
  }

  if (currentSession && audio) {
    const curTime = audio.currentTime || 0;
    const isPlaying = !audio.paused;

    audio.src = idx === 1 ? currentSession.mix1_url : currentSession.mix2_url;
    audio.currentTime = curTime;

    if (isPlaying) {
      audio.play().catch((err) => console.warn("Audio play blocked:", err));
    }
  }
}

async function loadSession() {
  const projName = document.getElementById("projName");
  const projGenre = document.getElementById("projGenre");
  const audio = document.getElementById("benchmarkAudio");

  try {
    const res = await fetch("/api/benchmark/session");
    if (!res.ok) throw new Error(`HTTP error ${res.status}`);
    const data = await res.json();

    currentSession = data;
    if (projName) projName.textContent = data.project_title || data.project_id || "Multitrack Session #1";
    if (projGenre) projGenre.textContent = (data.genre || "Pop").toUpperCase();

    if (audio && data.mix1_url) {
      audio.src = data.mix1_url;
    }
  } catch (err) {
    console.warn("Failed to load benchmark session:", err);
    if (projName) projName.textContent = "Demo Session";
    currentSession = {
      session_id: "demo_session_001",
      project_id: "demo_proj_001",
      mix1_url: "/api/automix/play/demo1",
      mix2_url: "/api/automix/play/demo2",
      genre: "pop",
    };
  }
}

async function submitRating(event) {
  event.preventDefault();
  const statusMsg = document.getElementById("statusMsg");
  const form = document.getElementById("benchmarkForm");

  const clarity = parseInt(document.getElementById("scoreClarity").value, 10);
  const bass = parseInt(document.getElementById("scoreBass").value, 10);
  const width = parseInt(document.getElementById("scoreWidth").value, 10);
  const punch = parseInt(document.getElementById("scorePunch").value, 10);

  const prefEl = form.querySelector('input[name="preference"]:checked');
  const preference = prefEl ? prefEl.value : "equal";

  const producerName = document.getElementById("producerName").value.trim();
  const feedbackText = document.getElementById("feedbackText").value.trim();

  const payload = {
    session_id: currentSession ? currentSession.session_id : "demo_session",
    project_id: currentSession ? currentSession.project_id : "demo_proj",
    active_mix_evaluated: activeMixIndex,
    clarity,
    bass,
    width,
    punch,
    preference,
    producer_name: producerName,
    feedback_text: feedbackText,
  };

  try {
    statusMsg.style.color = "var(--text-muted)";
    statusMsg.textContent = "Submitting producer review...";

    const res = await authedFetch("/api/benchmark/rate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    if (res.ok) {
      statusMsg.style.color = "var(--accent-green)";
      statusMsg.textContent = "✅ Benchmark rating recorded! Thank you for participating in the study.";
      form.reset();
      updateVal("valClarity", 3);
      updateVal("valBass", 3);
      updateVal("valWidth", 3);
      updateVal("valPunch", 3);
    } else {
      throw new Error(`Server returned status ${res.status}`);
    }
  } catch (err) {
    statusMsg.style.color = "#f87171";
    statusMsg.textContent = `Submission failed: ${err.message}`;
  }
}

document.addEventListener("DOMContentLoaded", loadSession);
