/* KENN Public Beta Client Application */

const form = document.querySelector("#chat-form");
const input = document.querySelector("#question");
const starterRoot = document.querySelector("#starter-questions");
const messages = document.querySelector("#messages");
const statusText = document.querySelector("#status-text");
const statusDot = document.querySelector("#status-dot");
const mixReviewForm = document.querySelector("#mix-review-form");
const mixReviewFileInput = document.querySelector("#mix-review-file");
const mixReviewCompareInput = document.querySelector("#mix-review-compare-file");
const uploadConsentCheckbox = document.querySelector("#upload-consent");

// Feedback Widget Elements
const feedbackWidget = document.querySelector("#feedback-widget");
const feedbackCommentsInput = document.querySelector("#feedback-comments");
const submitFeedbackBtn = document.querySelector("#submit-feedback-btn");
const feedbackStatusText = document.querySelector("#feedback-status");
const ratingButtons = document.querySelectorAll(".rating-btn");

let activeRequestId = null;
let selectedRating = 5;
let currentContextType = "chat";
const conversation = [];

const API_ORIGIN = window.location.protocol === "file:"
  ? "http://127.0.0.1:8090"
  : (window.location.port === "8090" ? "" : "");

function apiUrl(path) {
  return `${API_ORIGIN}${path}`;
}

function escapeHtml(value) {
  return String(value || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function setStatus(text, busy = false) {
  if (statusText) statusText.textContent = text;
  if (statusDot) statusDot.classList.toggle("busy", busy);
}

const STARTER_QUESTIONS = [
  "How do I fix harsh sibilance in vocals?",
  "What is the best way to gain stage before compression?",
  "How do I carve space between kick drum and sub-bass?",
  "Why is my master limiting causing distortion?",
];

function renderStarterButtons() {
  if (!starterRoot) return;
  starterRoot.innerHTML = STARTER_QUESTIONS
    .map((q) => `<button type="button" class="starter-btn" data-question="${escapeHtml(q)}">${escapeHtml(q)}</button>`)
    .join("");

  starterRoot.querySelectorAll(".starter-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const q = btn.dataset.question;
      if (q) ask(q);
    });
  });
}

function addMessage(role, contentHtml) {
  const node = document.createElement("div");
  node.className = `message ${role}`;
  node.innerHTML = contentHtml;
  messages?.appendChild(node);
  messages?.scrollTo({ top: messages.scrollHeight, behavior: "smooth" });
  return node;
}

function renderSourcesHtml(sources) {
  if (!sources || !sources.length) return "";
  const links = sources.map((s) => {
    const title = escapeHtml(s.title || s.label || s.source || "Source Note");
    const label = escapeHtml(s.label || title);
    return `<li><span class="source-tag">${label}</span></li>`;
  }).join("");
  return `<div class="sources-box"><p class="sources-heading">Verified Sources & Provenance:</p><ul>${links}</ul></div>`;
}

function renderAnswerPayload(data) {
  const answer = escapeHtml(data.answer || "No response provided.");
  const confidence = data.confidence || "low";
  const weakMatch = data.weak_match;
  const sourcesHtml = renderSourcesHtml(data.sources);

  let badgeClass = "badge-low";
  if (confidence === "high") badgeClass = "badge-high";
  else if (confidence === "medium") badgeClass = "badge-med";

  let warningBox = "";
  if (weakMatch || !data.found) {
    warningBox = `<div class="abstention-box">ℹ️ KENN abstained from offering an ungrounded guess because no exact approved source matched your question.</div>`;
  }

  return `
    <div class="label-row">
      <div class="label">KENN</div>
      <span class="confidence-badge ${badgeClass}">Confidence: ${escapeHtml(confidence)}</span>
    </div>
    <div class="answer-body">
      ${warningBox}
      <p style="white-space: pre-line;">${answer}</p>
      ${sourcesHtml}
    </div>
  `;
}

function renderMixReviewReceipt(receipt) {
  if (receipt?.schema === "kenn.audio_analysis.result.v1") {
    return renderAudioAnalysis(receipt);
  }
  const ctx = receipt.input_context || {};
  const metrics = receipt.metrics || {};
  const findings = receipt.findings || [];
  const plan = receipt.action_plan || [];
  const limitations = receipt.limitations || "";

  const durationStr = ctx.duration_seconds ? `${ctx.duration_seconds}s` : "Unknown";
  const rating = receipt.technical_rating || "Pass";

  const findingsHtml = findings.map((f) => {
    const icon = f.detected ? "⚠️" : "✅";
    const status = f.detected ? "Flagged" : "Pass";
    return `
      <div class="finding-card ${f.detected ? 'detected' : 'clean'}">
        <div class="finding-header">
          <span>${icon} <strong>${escapeHtml(f.display_name || f.fault_family)}</strong></span>
          <span class="finding-status">${status}</span>
        </div>
        <p class="finding-explanation">${escapeHtml(f.explanation || "")}</p>
        ${f.suggested_next_step ? `<p class="finding-action"><strong>Fix:</strong> ${escapeHtml(f.suggested_next_step)}</p>` : ""}
      </div>
    `;
  }).join("");

  const metricsHtml = `
    <div class="metrics-grid" style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin: 12px 0;">
      <div class="metric-card"><span class="m-label">Peak level</span><span class="m-val">${metrics.peak_dbfs !== undefined ? metrics.peak_dbfs.toFixed(2) + ' dBFS' : 'N/A'}</span></div>
      <div class="metric-card"><span class="m-label">RMS level</span><span class="m-val">${metrics.rms_dbfs !== undefined ? metrics.rms_dbfs.toFixed(2) + ' dBFS' : 'N/A'}</span></div>
      <div class="metric-card"><span class="m-label">Crest Factor</span><span class="m-val">${metrics.crest_db !== undefined ? metrics.crest_db.toFixed(2) + ' dB' : 'N/A'}</span></div>
      <div class="metric-card"><span class="m-label">Clip Runs</span><span class="m-val">${metrics.clipped_sample_runs !== undefined ? metrics.clipped_sample_runs : 0}</span></div>
      <div class="metric-card"><span class="m-label">Channel Imbalance</span><span class="m-val">${metrics.channel_imbalance_db !== undefined ? metrics.channel_imbalance_db.toFixed(2) + ' dB' : '0.00 dB'}</span></div>
      <div class="metric-card"><span class="m-label">DC Offset</span><span class="m-val">${metrics.dc_offset_flag ? 'Detected' : 'Clean'}</span></div>
    </div>
  `;

  return `
    <div class="label-row">
      <div class="label">KENN Mix Review</div>
      <span class="confidence-badge badge-high">Overall Status: ${escapeHtml(rating)}</span>
    </div>
    <div class="answer-body">
      <p><strong>Track:</strong> ${escapeHtml(ctx.filename || "Uploaded WAV")} (${escapeHtml(ctx.channel_layout || "stereo")}, ${durationStr}, ${ctx.sample_rate_hz || 44100} Hz)</p>
      ${metricsHtml}
      <h3 style="margin-top: 12px; font-size: 13px; color: var(--muted);">Diagnostic Findings</h3>
      ${findingsHtml}
      <div class="limitations-box" style="margin-top: 12px; font-size: 11px; color: var(--muted); background: rgba(255,255,255,0.03); padding: 8px; border-radius: 6px;">
        <strong>Engine Scope & Limitations:</strong> ${escapeHtml(limitations)}
      </div>
    </div>
  `;
}

function formatMetric(value, suffix = "") {
  return typeof value === "number" && Number.isFinite(value) ? `${value.toFixed(2)}${suffix}` : "N/A";
}

function renderAudioAnalysis(result) {
  const metrics = result.metrics || {};
  const spectral = result.spectral || {};
  const findings = result.findings || [];
  const peaks = spectral.dominant_peaks || [];
  const localizedWindows = Array.isArray(spectral.time_localized_windows)
    ? spectral.time_localized_windows
    : [];
  const findingsHtml = findings.length
    ? findings.map((f) => `<div class="finding-card detected"><div class="finding-header"><strong>${escapeHtml(f.type || "Finding")}</strong><span class="finding-status">${escapeHtml(f.severity || "review")}</span></div><p class="finding-explanation">${escapeHtml(f.explanation || "")}</p><p class="finding-action"><strong>Listening test:</strong> ${escapeHtml(f.suggested_listening_test || "")}</p></div>`).join("")
    : `<div class="finding-card clean"><p class="finding-explanation">No bounded fault finding was triggered by these measurements.</p></div>`;
  const peakHtml = peaks.length
    ? peaks.slice(0, 6).map((p) => `<li>${formatMetric(p.frequency_hz, " Hz")} at ${formatMetric(p.level_dbfs, " dBFS")} · ${formatMetric(p.bandwidth_hz, " Hz")} bandwidth</li>`).join("")
    : "<li>No dominant peaks reported.</li>";
  const localizedHtml = localizedWindows.length
    ? localizedWindows.map((window, index) => {
      const top = window.dominant_peaks?.[0];
      const topText = top
        ? `${formatMetric(top.frequency_hz, " Hz")} at ${formatMetric(top.level_dbfs, " dBFS")}`
        : "No dominant peak";
      return `<li>Window ${index + 1}: ${formatMetric(window.start_seconds, "s")}–${formatMetric(window.end_seconds, "s")} · RMS ${formatMetric(window.rms_dbfs, " dBFS")} · ${escapeHtml(topText)}</li>`;
    }).join("")
    : "<li>Not available for this analysis.</li>";
  const limitations = (result.limitations || []).join(" ");
  return `<div class="label-row"><div class="label">KENN Audio Analysis</div><span class="confidence-badge badge-high">${escapeHtml(result.analysis_status || "unknown")}</span></div>
    <div class="answer-body"><p><strong>File:</strong> ${escapeHtml(result.filename || "Uploaded WAV")} · ${metrics.channels || "?"} channel(s) · ${metrics.sample_rate_hz || "?"} Hz</p>
    <div class="metrics-grid" style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin:12px 0;">
      <div class="metric-card"><span class="m-label">Sample peak</span><span class="m-val">${formatMetric(metrics.sample_peak_dbfs, " dBFS")}</span></div>
      <div class="metric-card"><span class="m-label">RMS</span><span class="m-val">${formatMetric(metrics.rms_dbfs, " dBFS")}</span></div>
      <div class="metric-card"><span class="m-label">Crest factor</span><span class="m-val">${formatMetric(metrics.crest_factor_db, " dB")}</span></div>
      <div class="metric-card"><span class="m-label">Clipped runs</span><span class="m-val">${metrics.clipped_run_count ?? "N/A"}</span></div>
      <div class="metric-card"><span class="m-label">Correlation</span><span class="m-val">${formatMetric(metrics.correlation)}</span></div>
      <div class="metric-card"><span class="m-label">Mono drop</span><span class="m-val">${formatMetric(metrics.mono_cancellation_drop_db, " dB")}</span></div>
    </div>
    <h3 style="margin-top:12px;font-size:13px;color:var(--muted);">Measured dominant peaks</h3><ul>${peakHtml}</ul>
    <h3 style="margin-top:12px;font-size:13px;color:var(--muted);">Time-localized FFT windows</h3><ul>${localizedHtml}</ul>
    <h3 style="margin-top:12px;font-size:13px;color:var(--muted);">Bounded findings</h3>${findingsHtml}
    <div class="limitations-box" style="margin-top:12px;font-size:11px;color:var(--muted);background:rgba(255,255,255,.03);padding:8px;border-radius:6px;"><strong>Limitations:</strong> ${escapeHtml(limitations)}</div></div>`;
}

function renderAudioComparison(result) {
  const rows = Object.entries(result.metric_deltas || {}).map(([key, value]) => `<tr><td>${escapeHtml(key)}</td><td>${escapeHtml(value.a)}</td><td>${escapeHtml(value.b)}</td><td>${escapeHtml(value.delta_b_minus_a)}</td></tr>`).join("");
  return `<div class="label-row"><div class="label">KENN Audio Comparison</div><span class="confidence-badge badge-high">Measured deltas</span></div><div class="answer-body"><p><strong>A:</strong> ${escapeHtml(result.source_a?.filename || "file A")}<br><strong>B:</strong> ${escapeHtml(result.source_b?.filename || "file B")}</p><p class="upload-mode-hint">Hashes: ${escapeHtml(result.source_a?.input_hash || "")} / ${escapeHtml(result.source_b?.input_hash || "")}</p><table style="width:100%;font-size:11px"><thead><tr><th>Metric</th><th>A</th><th>B</th><th>B−A</th></tr></thead><tbody>${rows}</tbody></table><div class="limitations-box" style="margin-top:12px;font-size:11px;color:var(--muted);"><strong>Interpretation:</strong> These are measured field deltas, not proof that one mix is musically better.</div></div>`;
}

// Show feedback capture widget and set active request ID
function activateFeedbackWidget(requestId, contextType = "chat") {
  activeRequestId = requestId;
  currentContextType = contextType;
  if (feedbackWidget) {
    feedbackWidget.style.display = "block";
    if (feedbackStatusText) feedbackStatusText.textContent = "";
  }
}

// Rating button handlers
ratingButtons.forEach((btn) => {
  btn.addEventListener("click", () => {
    ratingButtons.forEach((b) => b.style.borderColor = "var(--border)");
    btn.style.borderColor = "var(--green)";
    selectedRating = parseInt(btn.dataset.rating || "5", 10);
  });
});

submitFeedbackBtn?.addEventListener("click", async () => {
  if (!activeRequestId) return;
  const comments = feedbackCommentsInput?.value?.trim() || "";
  try {
    const resp = await fetch(apiUrl("/feedback"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        request_id: activeRequestId,
        rating: selectedRating,
        comments,
        context_type: currentContextType,
      }),
    });
    const data = await resp.json();
    if (resp.ok && data.ok) {
      if (feedbackStatusText) {
        feedbackStatusText.textContent = "✅ Thank you for your feedback!";
        feedbackStatusText.style.color = "var(--green)";
      }
      if (feedbackCommentsInput) feedbackCommentsInput.value = "";
    } else {
      throw new Error(data.detail || data.error || "Submission failed");
    }
  } catch (err) {
    if (feedbackStatusText) {
      feedbackStatusText.textContent = `❌ ${err.message}`;
      feedbackStatusText.style.color = "var(--red)";
    }
  }
});

async function ask(question) {
  if (!question) return;
  addMessage("user", `<div class="label">You</div><p>${escapeHtml(question)}</p>`);
  setStatus("Searching verified knowledge notes...", true);
  if (input) input.value = "";

  const answerNode = addMessage("assistant", `
    <div class="label-row"><div class="label">KENN</div></div>
    <div class="answer-body"><p>Searching verified knowledge...</p></div>
  `);

  try {
    const resp = await fetch(apiUrl("/chat"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        question,
        history: conversation.slice(-4),
      }),
    });

    const resJson = await resp.json();
    if (!resp.ok || !resJson.ok) {
      throw new Error(resJson.detail || resJson.error || "Request failed");
    }

    const payload = resJson.data || resJson;
    answerNode.innerHTML = renderAnswerPayload(payload);
    setStatus("Ready");

    conversation.push({ role: "user", content: question });
    conversation.push({ role: "assistant", content: payload.answer || "" });

    if (resJson.request_id) {
      activateFeedbackWidget(resJson.request_id, "chat");
    }
  } catch (err) {
    answerNode.innerHTML = `<div class="label">Error</div><p>${escapeHtml(err.message || "Failed to reach KENN public server.")}</p>`;
    setStatus("Error");
  }
}

form?.addEventListener("submit", async (e) => {
  e.preventDefault();
  const q = input?.value?.trim();
  if (q) await ask(q);
});

mixReviewForm?.addEventListener("submit", async (e) => {
  e.preventDefault();
  const files = mixReviewFileInput?.files;
  if (!files || files.length === 0) {
    alert("Please select a 16-bit or 24-bit PCM WAV file to analyze.");
    return;
  }

  if (uploadConsentCheckbox && !uploadConsentCheckbox.checked) {
    alert("Please check the upload consent box to proceed with server-side WAV analysis.");
    return;
  }

  const file = files[0];
  if (!file.name.toLowerCase().endsWith(".wav")) {
    alert("Unsupported file format. Only .wav files are supported in the Public Beta.");
    return;
  }

  const comparisonFile = mixReviewCompareInput?.files?.[0];
  addMessage("user", `<div class="label">You</div><p>${comparisonFile ? "Comparing WAV files" : "Analyzing WAV"}: <strong>${escapeHtml(file.name)}</strong>${comparisonFile ? ` and <strong>${escapeHtml(comparisonFile.name)}</strong>` : ""} (${(file.size / (1024 * 1024)).toFixed(2)} MB)</p>`);
  setStatus("Analyzing WAV signal metrics...", true);

  const submitBtn = document.querySelector("#mix-review-submit");
  if (submitBtn) submitBtn.disabled = true;

  const formData = new FormData();
  if (comparisonFile) formData.append("file_a", file, file.name);
  else formData.append("file", file, file.name);
  if (comparisonFile) formData.append("file_b", comparisonFile, comparisonFile.name);

  try {
    const resp = await fetch(apiUrl(comparisonFile ? "/audio-analysis/compare" : "/audio-analysis"), {
      method: "POST",
      body: formData,
    });

    const resJson = await resp.json();
    if (!resp.ok || !resJson.ok) {
      throw new Error(resJson.detail || resJson.error || "Mix Review failed");
    }

    const receipt = resJson.receipt || resJson;
    const node = addMessage("assistant", comparisonFile ? renderAudioComparison(receipt) : renderMixReviewReceipt(receipt));
    setStatus(comparisonFile ? "Audio comparison complete" : "Audio analysis complete");

    if (resJson.request_id) {
      activateFeedbackWidget(resJson.request_id, "mix_review");
    }
  } catch (err) {
    addMessage("assistant", `<div class="label">Mix Review Error</div><p>${escapeHtml(err.message || "WAV Mix Review failed.")}</p>`);
    setStatus("Mix Review Error");
  } finally {
    if (submitBtn) submitBtn.disabled = false;
    if (mixReviewForm) mixReviewForm.reset();
  }
});

// Check health on startup
async function checkHealth() {
  try {
    const resp = await fetch(apiUrl("/health"));
    if (resp.ok) setStatus("Ready");
    else setStatus("Server Error");
  } catch {
    setStatus("Offline");
  }
}

// Initial setup
renderStarterButtons();
checkHealth();
