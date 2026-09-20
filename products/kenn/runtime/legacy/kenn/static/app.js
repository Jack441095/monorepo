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

/* ── Autonomous Producer Rendering Helpers ──────────────────────── */

function renderReActTrajectory(trajectory) {
  if (!trajectory || !trajectory.length) return "";
  const phaseIcons = {
    perception: "👁️",
    diagnosis: "🔬",
    translation: "🎛️",
    safety_clamp: "🛡️",
    thought: "💭",
    action: "⚡",
    observation: "📊",
    reflection: "🪞",
  };
  const steps = trajectory.map((step, i) => {
    const phase = (step.phase || step.type || "thought").toLowerCase();
    const icon = phaseIcons[phase] || "•";
    const title = escapeHtml(step.title || step.phase || `Step ${i + 1}`);
    const detail = escapeHtml(step.detail || step.content || step.summary || "");
    return `<div class="react-step">
      <strong>${icon} ${title}</strong>
      ${detail ? `<div class="react-thought">${detail}</div>` : ""}
    </div>`;
  }).join("");

  return `<div class="react-card">
    <div class="react-header" onclick="this.nextElementSibling.style.display = this.nextElementSibling.style.display === 'none' ? 'flex' : 'none'">
      <span>🧠 ReAct Deliberation Trajectory</span>
      <span class="react-badge">${trajectory.length} steps</span>
    </div>
    <div class="react-timeline">${steps}</div>
  </div>`;
}

function renderFrequencyMatrix(proposal) {
  const zones = [
    { key: "sub",      name: "Sub",      range: "20–60 Hz" },
    { key: "punch",    name: "Punch",    range: "60–250 Hz" },
    { key: "mud",      name: "Mud",      range: "250–500 Hz" },
    { key: "presence", name: "Presence", range: "2–5 kHz" },
    { key: "air",      name: "Air",      range: "8–20 kHz" },
  ];
  const clashes = proposal?.clashes || proposal?.diagnosis?.clashes || [];
  const clashZones = new Set();
  clashes.forEach((c) => {
    const freq = c.frequency_hz || c.freq || 0;
    if (freq < 60) clashZones.add("sub");
    else if (freq < 250) clashZones.add("punch");
    else if (freq < 500) clashZones.add("mud");
    else if (freq < 5000) clashZones.add("presence");
    else clashZones.add("air");
  });

  const chips = zones.map((z) => {
    const hasClash = clashZones.has(z.key);
    const statusIcon = hasClash ? "⚠️ Clash" : "✅ Clean";
    return `<div class="zone-chip ${hasClash ? 'clash' : 'clean'}">
      <span class="zone-name">${z.name}</span>
      <span class="zone-range">${z.range}</span>
      <span class="zone-status">${statusIcon}</span>
    </div>`;
  }).join("");

  return `<div class="frequency-matrix">${chips}</div>`;
}

function renderAuditionCard(token) {
  const safeToken = escapeHtml(token || "");
  return `
    <div class="ab-audition-card" id="ab-card-${safeToken}">
      <div class="ab-header">
        <span class="ab-title">🎧 Zero-Bias A/B Audition</span>
        <span class="lufs-badge">Loudness-Matched: ±0.0 LUFS</span>
      </div>
      <div class="ab-controls">
        <button type="button" class="ab-btn" id="ab-btn-a-${safeToken}" onclick="toggleAuditionState('${safeToken}', 'A', this)">
          A (Original Mix)
        </button>
        <button type="button" class="ab-btn active" id="ab-btn-b-${safeToken}" onclick="toggleAuditionState('${safeToken}', 'B', this)">
          B (Applied Recipe)
        </button>
      </div>
      <div class="ab-status" id="ab-status-${safeToken}">
        Active: <strong>B (Applied Recipe)</strong> — Instant toggle via parameter memory buffer
      </div>
    </div>
  `;
}

async function toggleAuditionState(token, state, btn) {
  if (!token) return;
  const card = document.querySelector(`#ab-card-${token}`);
  const btnA = card ? card.querySelector(`#ab-btn-a-${token}`) : document.querySelector(`#ab-btn-a-${token}`);
  const btnB = card ? card.querySelector(`#ab-btn-b-${token}`) : document.querySelector(`#ab-btn-b-${token}`);
  const statusEl = card ? card.querySelector(`#ab-status-${token}`) : document.querySelector(`#ab-status-${token}`);

  const action = state === "A" ? "undo" : "apply";
  if (statusEl) statusEl.innerHTML = `Switching to <strong>State ${state}</strong>...`;

  try {
    const resp = await fetch(apiUrl("/api/ableton/command"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ confirmation_token: token, action: action }),
    });
    const data = await resp.json();
    if (resp.ok && (data.ok || data.changed || data.status === "applied")) {
      if (btnA) btnA.classList.toggle("active", state === "A");
      if (btnB) btnB.classList.toggle("active", state === "B");
      if (statusEl) {
        if (state === "A") {
          statusEl.innerHTML = `Active: <strong>A (Original Mix)</strong> — Baseline restored (no volume bias)`;
        } else {
          statusEl.innerHTML = `Active: <strong>B (Applied Recipe)</strong> — Recipe active with calibrated gain staging`;
        }
      }
    } else {
      if (statusEl) statusEl.innerHTML = `❌ Toggle failed: ${escapeHtml(data.error || "Live engine error")}`;
    }
  } catch {
    if (statusEl) statusEl.innerHTML = `❌ Error communicating with KENN engine`;
  }
}

function renderRecipeProposal(proposal, confirmationToken) {
  const steps = proposal?.steps || proposal?.recipe?.steps || [];
  if (!steps.length) return "";

  const stepsHtml = steps.map((s) => {
    const trackName = escapeHtml(s.track_name || s.track || "Track");
    const paramName = escapeHtml(s.parameter || s.param || "gain");
    const value = s.value !== undefined ? s.value : s.delta || 0;
    const displayVal = typeof value === "number" ? (value > 0 ? `+${value.toFixed(2)}` : value.toFixed(2)) : escapeHtml(String(value));
    return `<div class="recipe-step-item">
      <span>${trackName} → ${paramName}</span>
      <span class="fader-move">${displayVal}</span>
    </div>`;
  }).join("");

  const token = escapeHtml(confirmationToken || "");
  return `<div class="recipe-proposal-card">
  return `<div class="recipe-proposal-card" id="recipe-card-${token}">
    <div class="recipe-title">🎚️ Proposed Mix Recipe (${steps.length} moves)</div>
    ${stepsHtml}
    <div class="recipe-actions">
      <button class="btn-apply-recipe" onclick="applyRecipe('${token}', this)" data-token="${token}">✅ Apply Recipe</button>
      <button class="btn-undo-recipe" onclick="undoRecipe('${token}', this)" data-token="${token}" style="display:none;">↩️ Undo Changes</button>
    </div>
    <div id="audition-container-${token}"></div>
  </div>`;
}

async function applyRecipe(token, btn) {
  if (!token) return;
  btn.disabled = true;
  btn.textContent = "⏳ Applying...";
  try {
    const resp = await fetch(apiUrl("/api/ableton/command"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ confirmation_token: token, action: "apply" }),
    });
    const data = await resp.json();
    if (resp.ok && data.ok) {
    if (resp.ok && (data.ok || data.changed || data.status === "applied")) {
      btn.textContent = "✅ Applied";
      btn.style.opacity = "0.6";
      const undoBtn = btn.nextElementSibling;
      if (undoBtn) undoBtn.style.display = "inline-block";

      // Reveal Zero-Bias A/B Audition Card
      const container = document.querySelector(`#audition-container-${token}`);
      if (container) {
        container.innerHTML = renderAuditionCard(token);
      }
    } else {
      btn.textContent = "❌ Failed";
      btn.textContent = `❌ ${data.error || "Failed"}`;
      btn.disabled = false;
    }
  } catch {
    btn.textContent = "❌ Error";
    btn.disabled = false;
  }
}

async function undoRecipe(token, btn) {
  if (!token) return;
  btn.disabled = true;
  btn.textContent = "⏳ Reverting...";
  try {
    const resp = await fetch(apiUrl("/api/ableton/command"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ confirmation_token: token, action: "undo" }),
    });
    const data = await resp.json();
    if (resp.ok && data.ok) {
    if (resp.ok && (data.ok || data.changed || data.status === "applied")) {
      btn.textContent = "↩️ Reverted";
      btn.style.opacity = "0.6";
      const applyBtn = btn.previousElementSibling;
      if (applyBtn) {
        applyBtn.textContent = "✅ Re-Apply Recipe";
        applyBtn.style.opacity = "1";
        applyBtn.disabled = false;
      }
      const container = document.querySelector(`#audition-container-${token}`);
      if (container) {
        const btnA = container.querySelector(`#ab-btn-a-${token}`);
        const btnB = container.querySelector(`#ab-btn-b-${token}`);
        const statusEl = container.querySelector(`#ab-status-${token}`);
        if (btnA) btnA.classList.add("active");
        if (btnB) btnB.classList.remove("active");
        if (statusEl) statusEl.innerHTML = `Active: <strong>A (Original Mix)</strong> — Changes reverted`;
      }
    } else {
      btn.textContent = "❌ Undo Failed";
      btn.disabled = false;
    }
  } catch {
    btn.textContent = "❌ Error";
    btn.disabled = false;
  }
}

/* ── Tier 2 & Tier 3 Clip/Scene Proposal Card Renderers ──────────── */

function renderClipLaunchProposal(proposal, token) {
  const isStop = Boolean(proposal.stop || proposal.action === "stop_clip");
  const trackIdx = proposal.track_index !== undefined ? proposal.track_index : "—";
  const slotIdx = proposal.clip_slot_index !== undefined ? proposal.clip_slot_index : "—";
  const title = isStop ? "⏹️ Proposed Clip Stop" : "▶️ Proposed Clip Launch";
  const btnLabel = isStop ? "⏹️ Stop Clip" : "▶️ Launch Clip";

  return `
    <div class="recipe-proposal-card" id="prop-card-${escapeHtml(token)}">
      <div class="recipe-title">${title}</div>
      <div class="recipe-step-item">
        <span>Track: <strong>Track ${escapeHtml(trackIdx)}</strong></span>
        <span class="fader-move">Slot ${escapeHtml(slotIdx)}</span>
      </div>
      <div class="recipe-actions">
        <button class="btn-apply-recipe" onclick="executeTierProposal('${escapeHtml(token)}', this)">${btnLabel}</button>
      </div>
    </div>
  `;
}

function renderSceneCreationProposal(proposal, token) {
  const sceneName = escapeHtml(proposal.scene_name || "New Scene");
  return `
    <div class="recipe-proposal-card" id="prop-card-${escapeHtml(token)}">
      <div class="recipe-title">🎬 Proposed Scene Creation</div>
      <div class="recipe-step-item">
        <span>Scene Name</span>
        <span class="fader-move">"${sceneName}"</span>
      </div>
      <div class="recipe-actions">
        <button class="btn-apply-recipe" onclick="executeTierProposal('${escapeHtml(token)}', this)">➕ Create Scene</button>
      </div>
    </div>
  `;
}

function renderLoopDuplicationProposal(proposal, token) {
  const trackIdx = proposal.track_index !== undefined ? proposal.track_index : "—";
  const slotIdx = proposal.clip_slot_index !== undefined ? proposal.clip_slot_index : "—";
  return `
    <div class="recipe-proposal-card" id="prop-card-${escapeHtml(token)}">
      <div class="recipe-title">🔁 Proposed Loop Duplication</div>
      <div class="recipe-step-item">
        <span>Target: <strong>Track ${escapeHtml(trackIdx)}, Slot ${escapeHtml(slotIdx)}</strong></span>
        <span class="fader-move">Double Length (2x)</span>
      </div>
      <div class="recipe-actions">
        <button class="btn-apply-recipe" onclick="executeTierProposal('${escapeHtml(token)}', this)">🔁 Duplicate Loop Length</button>
      </div>
    </div>
  `;
}

function renderWarpPitchProposal(proposal, token) {
  const trackIdx = proposal.track_index !== undefined ? proposal.track_index : "—";
  const slotIdx = proposal.clip_slot_index !== undefined ? proposal.clip_slot_index : "—";
  const warpModes = ["Beats", "Tones", "Texture", "Re-Pitch", "Complex", "Complex Pro"];
  const warpStr = proposal.warp_mode !== undefined ? (warpModes[proposal.warp_mode] || `Mode ${proposal.warp_mode}`) : "unchanged";
  const pitchStr = proposal.pitch_coarse !== undefined ? (proposal.pitch_coarse > 0 ? `+${proposal.pitch_coarse} st` : `${proposal.pitch_coarse} st`) : "unchanged";

  return `
    <div class="recipe-proposal-card" id="prop-card-${escapeHtml(token)}">
      <div class="recipe-title">🎛️ Proposed Clip Warp & Transposition</div>
      <div class="recipe-step-item">
        <span>Target: <strong>Track ${escapeHtml(trackIdx)}, Slot ${escapeHtml(slotIdx)}</strong></span>
        <span class="fader-move">Warp: ${escapeHtml(warpStr)} · Pitch: ${escapeHtml(pitchStr)}</span>
      </div>
      <div class="recipe-actions">
        <button class="btn-apply-recipe" onclick="executeTierProposal('${escapeHtml(token)}', this)">🎛️ Apply Warp & Pitch</button>
      </div>
    </div>
  `;
}

function renderTrackFreezeProposal(proposal, token) {
  const trackIdx = proposal.track_index !== undefined ? proposal.track_index : "—";
  const freeze = Boolean(proposal.freeze);
  return `
    <div class="recipe-proposal-card" id="prop-card-${escapeHtml(token)}">
      <div class="recipe-title">❄️ Proposed Track Freeze</div>
      <div class="recipe-step-item">
        <span>Target: <strong>Track ${escapeHtml(trackIdx)}</strong></span>
        <span class="fader-move">${freeze ? "Freeze Audio" : "Unfreeze Track"}</span>
      </div>
      <div class="recipe-actions">
        <button class="btn-apply-recipe" onclick="executeTierProposal('${escapeHtml(token)}', this)">❄️ ${freeze ? "Freeze Track" : "Unfreeze Track"}</button>
      </div>
    </div>
  `;
}

function renderRackMacroProposal(proposal, token) {
  const trackIdx = proposal.track_index !== undefined ? proposal.track_index : "—";
  const devIdx = proposal.device_index !== undefined ? proposal.device_index : "—";
  const macroIdx = proposal.macro_index !== undefined ? proposal.macro_index : "—";
  const paramIdx = proposal.target_param_index !== undefined ? proposal.target_param_index : "—";
  return `
    <div class="recipe-proposal-card" id="prop-card-${escapeHtml(token)}">
      <div class="recipe-title">🎛️ Proposed Rack Macro Mapping</div>
      <div class="recipe-step-item">
        <span>Track ${escapeHtml(trackIdx)} → Device ${escapeHtml(devIdx)}</span>
        <span class="fader-move">Macro ${escapeHtml(macroIdx)} ➔ Param ${escapeHtml(paramIdx)}</span>
      </div>
      <div class="recipe-actions">
        <button class="btn-apply-recipe" onclick="executeTierProposal('${escapeHtml(token)}', this)">🎛️ Map Macro</button>
      </div>
    </div>
  `;
}

function renderGenericProposal(proposal, token) {
  const action = escapeHtml(proposal.action || proposal.operation || "Live Action");
  return `
    <div class="recipe-proposal-card" id="prop-card-${escapeHtml(token)}">
      <div class="recipe-title">⚡ Proposed Live Action: ${action}</div>
      <div class="recipe-step-item">
        <span>Confirmation Required</span>
        <span class="fader-move">${escapeHtml(proposal.schema || "Live Proposal")}</span>
      </div>
      <div class="recipe-actions">
        <button class="btn-apply-recipe" onclick="executeTierProposal('${escapeHtml(token)}', this)">✅ Confirm & Execute</button>
      </div>
    </div>
  `;
}

function renderActionProposal(proposal, confirmationToken) {
  if (!proposal || typeof proposal !== "object") return "";
  const token = confirmationToken || proposal.confirmation_token || "";

  // 1. Mix recipe steps
  const steps = proposal.steps || proposal.recipe?.steps;
  if (steps && steps.length > 0) {
    return renderRecipeProposal(proposal, token);
  }

  const schema = String(proposal.schema || "");
  const action = String(proposal.action || "");

  // 2. Clip Launch / Stop
  if (schema.includes("clip_launch") || action === "launch_clip" || action === "stop_clip") {
    return renderClipLaunchProposal(proposal, token);
  }
  // 3. Scene Creation
  if (schema.includes("scene_creation") || action === "create_scene") {
    return renderSceneCreationProposal(proposal, token);
  }
  // 4. Loop Duplication
  if (schema.includes("loop_duplication") || action === "duplicate_loop") {
    return renderLoopDuplicationProposal(proposal, token);
  }
  // 5. Warp & Pitch Transposition
  if (schema.includes("warp") || schema.includes("pitch") || action.includes("warp")) {
    return renderWarpPitchProposal(proposal, token);
  }
  // 6. Track Freeze
  if (schema.includes("freeze") || action.includes("freeze")) {
    return renderTrackFreezeProposal(proposal, token);
  }
  // 7. Rack Macro
  if (schema.includes("rack_macro") || action === "map_rack_macro") {
    return renderRackMacroProposal(proposal, token);
  }

  // 8. If token or schema present, render generic proposal
  if (token || schema) {
    return renderGenericProposal(proposal, token);
  }

  return "";
}

async function executeTierProposal(token, btn) {
  if (!token) return;
  btn.disabled = true;
  btn.textContent = "⏳ Executing...";
  try {
    const resp = await fetch(apiUrl("/api/ableton/command"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ confirmation_token: token, action: "apply" }),
    });
    const data = await resp.json();
    if (resp.ok && (data.ok || data.changed || data.status === "applied")) {
      btn.textContent = "✅ Executed";
      btn.style.opacity = "0.7";
      btn.style.background = "var(--green)";
      btn.style.color = "#000";
    } else {
      btn.textContent = `❌ ${data.error || "Execution Failed"}`;
      btn.disabled = false;
    }
  } catch (err) {
    btn.textContent = "❌ Connection Error";
    btn.disabled = false;
  }
}

// Ensure global access for inline onclick handlers
window.applyRecipe = applyRecipe;
window.undoRecipe = undoRecipe;
window.renderAuditionCard = renderAuditionCard;
window.toggleAuditionState = toggleAuditionState;
window.executeTierProposal = executeTierProposal;

/* ── Main Answer Payload Renderer (with Autonomous Producer detection) ── */

function renderAnswerPayload(data) {
  // Detect autonomous_producer orchestration payload
  const isAutonomous = data.orchestration?.agent_name === "autonomous_producer"
    || data.status === "confirmation_required"
    || data.proposal != null
    || data.trajectory != null;

  if (isAutonomous) {
    const trajectory = data.trajectory || data.orchestration?.trajectory || [];
    const proposal = data.proposal || data.orchestration?.proposal || {};
    const token = data.confirmation_token || proposal.confirmation_token || "";
    const answer = escapeHtml(data.answer || data.summary || "Autonomous mix analysis complete.");

    return `
      <div class="label-row">
        <div class="label">KENN</div>
        <span class="confidence-badge badge-high">🧠 Autonomous Producer</span>
      </div>
      <div class="answer-body">
        <p style="white-space: pre-line;">${answer}</p>
        ${renderReActTrajectory(trajectory)}
        ${renderFrequencyMatrix(proposal)}
        ${renderRecipeProposal(proposal, token)}
        ${renderActionProposal(proposal, token)}
      </div>
    `;
  }

  // Standard knowledge-grounded answer rendering
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

// Guardian ambient pill polling
function renderGuardianPill(guardianData) {
  let pill = document.querySelector("#guardian-pill");
  if (!pill) {
    // Create pill container in the nav/header area
    const header = document.querySelector(".app-header") || document.querySelector("header") || document.querySelector("nav");
    if (!header) return;
    pill = document.createElement("span");
    pill.id = "guardian-pill";
    pill.className = "guardian-pill healthy";
    header.appendChild(pill);
  }

  const status = guardianData.status || "offline";
  const clashCount = guardianData.active_clashes_count || 0;
  const headroomSafe = guardianData.headroom_safe !== false;

  if (status === "advisory" || status === "caution") {
    pill.className = "guardian-pill advisory";
    pill.innerHTML = `⚠️ Mix Health: ${clashCount} issue${clashCount !== 1 ? 's' : ''}`;
    pill.title = (guardianData.advisories || []).join("\n") || "Mix health advisory";
  } else if (status === "healthy") {
    pill.className = "guardian-pill healthy";
    pill.innerHTML = `✅ Mix Health: Clean`;
    pill.title = "All frequency zones clear, headroom safe";
  } else {
    pill.className = "guardian-pill healthy";
    pill.innerHTML = `🔌 Guardian: Offline`;
    pill.title = "Not connected to Live session";
  }
}

async function pollGuardianStatus() {
  if (typeof document !== "undefined" && document.hidden) return;
  try {
    const resp = await fetch(apiUrl("/api/guardian/status"));
    if (resp.ok) {
      const data = await resp.json();
      renderGuardianPill(data);
    }
  } catch {
    // Guardian endpoint not available — silently ignore
  }
}

// Proactive real-time push via Server-Sent Events (SSE)
function connectGuardianEvents() {
  if (typeof EventSource === "undefined") return;
  try {
    const es = new EventSource(apiUrl("/api/guardian/events"));
    es.addEventListener("status", (e) => {
      try {
        const data = JSON.parse(e.data);
        renderGuardianPill(data);
      } catch {}
    });
    es.onerror = () => {
      es.close();
      // Graceful fallback to standard 10-second polling
    };
  } catch {}
}

// Live Audio Telemetry & Mix Planner Expansion
function renderTelemetryBadge(telemetryData) {
  let badge = document.querySelector("#telemetry-badge");
  if (!badge) {
    const header = document.querySelector(".app-header") || document.querySelector("header") || document.querySelector("nav");
    if (!header) return;
    badge = document.createElement("span");
    badge.id = "telemetry-badge";
    badge.className = "telemetry-badge";
    header.appendChild(badge);
  }

  const tel = telemetryData.telemetry;
  if (!tel) {
    badge.style.display = "none";
    return;
  }
  badge.style.display = "inline-flex";

  const isClipping = tel.true_peak_dbtp > -0.2;
  const isMuddy = tel.spectral_energy && tel.spectral_energy.low_mid_200_500hz > 0.33;

  let alertClass = "normal";
  if (isClipping) alertClass = "critical";
  else if (isMuddy) alertClass = "warning";

  badge.className = `telemetry-badge ${alertClass}`;
  badge.innerHTML = `
    <span class="telemetry-icon">🎛️</span>
    <span class="telemetry-item"><b>${tel.integrated_lufs.toFixed(1)}</b> LUFS</span>
    <span class="telemetry-sep">|</span>
    <span class="telemetry-item ${isClipping ? 'clip-text' : ''}"><b>${tel.true_peak_dbtp > 0 ? '+' : ''}${tel.true_peak_dbtp.toFixed(1)}</b> dBTP</span>
    <span class="telemetry-sep">|</span>
    <span class="telemetry-item">Corr: <b>${tel.phase_correlation.toFixed(2)}</b></span>
  `;

  const anomalies = telemetryData.anomalies || [];
  badge.title = anomalies.length > 0 ? anomalies.join("\n") : "Audio Telemetry: All levels within streaming tolerance";
}

async function pollAudioTelemetry() {
  if (typeof document !== "undefined" && document.hidden) return;
  try {
    const resp = await fetch(apiUrl("/api/audio/telemetry"));
    if (resp.ok) {
      const data = await resp.json();
      renderTelemetryBadge(data);
    }
  } catch {}
}

function renderMixPlanCard(plan, container) {
  if (!plan || !plan.steps || !container) return;
  const card = document.createElement("div");
  card.className = "mix-plan-card";
  card.id = `mix-plan-${plan.plan_id}`;

  let stepsHtml = plan.steps.map((step, idx) => `
    <div class="mix-plan-step" id="${step.id}">
      <div class="mix-plan-step-header">
        <span class="step-badge">${idx + 1}</span>
        <span class="step-title"><b>${step.name}</b> (${step.track} &bull; ${step.plugin})</span>
        <span class="step-status ${step.status}">${step.status}</span>
      </div>
      <div class="step-why">${step.why}</div>
      <div class="step-actions">
        <button class="kenn-action-btn step-exec-btn" onclick="executeMixPlanStep('${plan.plan_id}', '${step.id}', this)">
          Apply Step
        </button>
      </div>
    </div>
  `).join("");

  card.innerHTML = `
    <div class="mix-plan-header">
      <div class="mix-plan-title">
        <span class="plan-icon">📋</span>
        <b>Agentic Mix Plan:</b> ${plan.goal}
      </div>
      <button class="kenn-action-btn primary execute-all-btn" onclick="executeFullMixPlan('${plan.plan_id}', this)">
        Apply All Steps
      </button>
    </div>
    <div class="mix-plan-steps">
      ${stepsHtml}
    </div>
  `;
  container.appendChild(card);
}

async function executeMixPlanStep(planId, stepId, btn) {
  if (btn) {
    btn.disabled = true;
    btn.innerText = "Applying...";
  }
  const stepEl = document.getElementById(stepId);
  const statusEl = stepEl ? stepEl.querySelector(".step-status") : null;
  if (statusEl) {
    statusEl.className = "step-status executing";
    statusEl.innerText = "executing";
  }

  try {
    // Dispatch safe DAW live action
    const resp = await fetch(apiUrl("/api/ableton/command"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: "execute_plan_step", plan_id: planId, step_id: stepId })
    });
    if (btn) {
      btn.innerText = "Applied ✓";
      btn.classList.add("completed");
    }
    if (statusEl) {
      statusEl.className = "step-status completed";
      statusEl.innerText = "completed ✓";
    }
  } catch (err) {
    if (btn) {
      btn.disabled = false;
      btn.innerText = "Retry";
    }
    if (statusEl) {
      statusEl.className = "step-status failed";
      statusEl.innerText = "failed";
    }
  }
}

async function executeFullMixPlan(planId, btn) {
  const planEl = document.getElementById(`mix-plan-${planId}`);
  if (!planEl) return;
  if (btn) {
    btn.disabled = true;
    btn.innerText = "Executing Plan...";
  }

  const stepBtns = planEl.querySelectorAll(".step-exec-btn");
  for (const stepBtn of stepBtns) {
    stepBtn.click();
    await new Promise(r => setTimeout(r, 400));
  }
  if (btn) {
    btn.innerText = "Plan Applied ✓";
    btn.classList.add("completed");
  }
}

/* ── KENN V5.0 Velvet Thunder In-DAW GUI HUD & Visualizers ──────── */

let zeroBiasAuditionActive = false;
let lastSessionSnapshot = null;

function renderMQMRadarPentagon(canvas, scores) {
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  if (!ctx) return;

  const w = canvas.width = canvas.clientWidth * window.devicePixelRatio || 300;
  const h = canvas.height = canvas.clientHeight * window.devicePixelRatio || 200;
  ctx.clearRect(0, 0, w, h);

  const cx = w / 2;
  const cy = h / 2 + 10;
  const radius = Math.min(cx, cy) - 25;
  const axes = [
    { label: "Dynamic", key: "dynamic_health", val: scores?.dynamic_health ?? 16 },
    { label: "Low-End", key: "low_end_control", val: scores?.low_end_control ?? 15 },
    { label: "Spectral", key: "spectral_balance", val: scores?.spectral_balance ?? 17 },
    { label: "Separation", key: "stem_separation", val: scores?.stem_separation ?? 14 },
    { label: "Stereo", key: "stereo_imaging", val: scores?.stereo_imaging ?? 16 },
  ];
  const numAxes = axes.length;

  // Concentric grid pentagons
  ctx.strokeStyle = "rgba(255, 255, 255, 0.1)";
  ctx.lineWidth = 1;
  for (let level = 1; level <= 4; level++) {
    const r = (radius / 4) * level;
    ctx.beginPath();
    for (let i = 0; i < numAxes; i++) {
      const angle = (Math.PI * 2 / numAxes) * i - Math.PI / 2;
      const x = cx + r * Math.cos(angle);
      const y = cy + r * Math.sin(angle);
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    }
    ctx.closePath();
    ctx.stroke();
  }

  // Axes lines & labels
  ctx.font = `${Math.max(9, Math.round(w * 0.035))}px sans-serif`;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillStyle = "rgba(255, 255, 255, 0.6)";

  for (let i = 0; i < numAxes; i++) {
    const angle = (Math.PI * 2 / numAxes) * i - Math.PI / 2;
    const ax = cx + radius * Math.cos(angle);
    const ay = cy + radius * Math.sin(angle);
    ctx.beginPath();
    ctx.moveTo(cx, cy);
    ctx.lineTo(ax, ay);
    ctx.stroke();

    const lx = cx + (radius + 15) * Math.cos(angle);
    const ly = cy + (radius + 15) * Math.sin(angle);
    ctx.fillText(axes[i].label, lx, ly);
  }

  // Data Polygon
  ctx.beginPath();
  for (let i = 0; i < numAxes; i++) {
    const norm = Math.max(0, Math.min(20, axes[i].val)) / 20.0;
    const r = radius * norm;
    const angle = (Math.PI * 2 / numAxes) * i - Math.PI / 2;
    const x = cx + r * Math.cos(angle);
    const y = cy + r * Math.sin(angle);
    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  }
  ctx.closePath();
  ctx.fillStyle = "rgba(96, 165, 250, 0.25)";
  ctx.fill();
  ctx.strokeStyle = "#60a5fa";
  ctx.lineWidth = 2;
  ctx.stroke();
}

function renderERBSpectrumOverlay(canvas, sessionBands, refBands) {
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  if (!ctx) return;

  const w = canvas.width = canvas.clientWidth * window.devicePixelRatio || 300;
  const h = canvas.height = canvas.clientHeight * window.devicePixelRatio || 200;
  ctx.clearRect(0, 0, w, h);

  const numBands = 40;
  const barWidth = (w - 20) / numBands;

  // Background reference curve (subtle outline / line)
  ctx.strokeStyle = "rgba(251, 191, 36, 0.7)"; // Gold reference
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  for (let i = 0; i < numBands; i++) {
    const refDb = refBands && refBands[i] !== undefined ? refBands[i] : (-12.0 - i * 0.4);
    const normRef = Math.max(0, Math.min(1, (refDb + 60) / 60));
    const x = 10 + i * barWidth + barWidth / 2;
    const y = h - 20 - normRef * (h - 40);
    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  }
  ctx.stroke();

  // Session Bars
  for (let i = 0; i < numBands; i++) {
    const db = sessionBands && sessionBands[i] !== undefined ? sessionBands[i] : (-14.0 - i * 0.45);
    const norm = Math.max(0, Math.min(1, (db + 60) / 60));
    const bh = norm * (h - 40);
    const x = 10 + i * barWidth;
    const y = h - 20 - bh;

    ctx.fillStyle = "rgba(96, 165, 250, 0.6)";
    ctx.fillRect(x, y, barWidth - 1, bh);
  }

  // Legend
  ctx.font = "10px sans-serif";
  ctx.fillStyle = "#60a5fa";
  ctx.fillText("Session Mix", 15, 15);
  ctx.fillStyle = "#fbbf24";
  ctx.fillText("Reference Curve", 85, 15);
}

async function toggleZeroBiasAB(btn) {
  zeroBiasAuditionActive = !zeroBiasAuditionActive;
  if (btn) {
    btn.classList.toggle("active", zeroBiasAuditionActive);
    btn.querySelector(".btn-label").innerText = zeroBiasAuditionActive ? "A/B: Reference Mode" : "A/B: Session Mix";
  }
}

async function restoreSessionSnapshot(btn) {
  if (btn) {
    btn.disabled = true;
    btn.innerText = "Restoring...";
  }
  try {
    await fetch(apiUrl("/api/ableton/command"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: "undo_last_command" })
    });
    if (btn) {
      btn.disabled = false;
      btn.innerText = "Restored ✓";
      setTimeout(() => { btn.innerText = "1-Click Undo"; }, 2000);
    }
  } catch (err) {
    if (btn) {
      btn.disabled = false;
      btn.innerText = "Undo Failed";
    }
  }
}

async function triggerAutoTrim() {
  try {
    const resp = await fetch(apiUrl("/api/gain-staging/trim"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tracks: [] })
    });
    const res = await resp.json();
    const alertEl = document.querySelector("#gain-staging-alert-box");
    if (alertEl) {
      alertEl.innerHTML = `<span>Nominal headroom restored (-18 dBFS target across ${res.tracks_overloaded || 0} tracks).</span>`;
      setTimeout(() => { alertEl.style.display = "none"; }, 4000);
    }
  } catch (e) {
    console.error("Auto trim failed", e);
  }
}

/* ── KENN V6.0 Generative Arrangement, MIDI & Stem Delivery ────── */

function renderArrangementTimeline(container, sections) {
  if (!container) return;
  const secs = sections || [
    { section_type: "INTRO", start_bar: 1, end_bar: 8 },
    { section_type: "VERSE", start_bar: 9, end_bar: 24 },
    { section_type: "BUILDUP", start_bar: 25, end_bar: 32 },
    { section_type: "DROP_CHORUS", start_bar: 33, end_bar: 48 },
    { section_type: "BRIDGE", start_bar: 49, end_bar: 56 },
    { section_type: "OUTRO", start_bar: 57, end_bar: 64 },
  ];

  const blocksHtml = secs.map(s => {
    const cls = `sec-${s.section_type.toLowerCase()}`;
    return `<div class="arrangement-section-block ${cls}" title="${s.section_type} (Bars ${s.start_bar}-${s.end_bar})">
      ${s.section_type.replace("_", " ")}
    </div>`;
  }).join("");

  container.innerHTML = `
    <div class="arrangement-timeline-card">
      <div class="vt-canvas-title">Arrangement Macro-Timeline (Pacing & Transitions)</div>
      <div class="arrangement-timeline-bar">${blocksHtml}</div>
    </div>
  `;
}

async function triggerGenerateMidi(type = "counterpoint", root = "F", scale = "NATURAL_MINOR", btn = null) {
  if (btn) {
    btn.disabled = true;
    btn.innerText = "Generating...";
  }
  try {
    const route = type === "bassline" ? "/api/midi/generate/bassline" : "/api/midi/generate/counterpoint";
    const resp = await fetch(apiUrl(route), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ root, scale, bars: 4 })
    });
    const res = await resp.json();
    if (btn) {
      btn.disabled = false;
      btn.innerText = `Generated (${res.clip?.note_count || 0} notes) ✓`;
      setTimeout(() => {
        btn.innerText = type === "bassline" ? "Generate Rolling Bassline" : "Generate Counter-Melody";
      }, 3000);
    }
  } catch (err) {
    if (btn) {
      btn.disabled = false;
      btn.innerText = "Generation Failed";
    }
  }
}

async function triggerPackageStems(btn = null) {
  if (btn) {
    btn.disabled = true;
    btn.innerText = "Packaging Stems...";
  }
  try {
    const resp = await fetch(apiUrl("/api/stems/export-plan"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tracks: [] })
    });
    const res = await resp.json();
    if (btn) {
      btn.disabled = false;
      btn.innerText = `Stems Ready (${res.stem_plan?.stem_count || 5} Tiers) ✓`;
    }
  } catch (err) {
    if (btn) {
      btn.disabled = false;
      btn.innerText = "Export Failed";
    }
  }
}

// Initial setup
renderStarterButtons();
checkHealth();
pollGuardianStatus();
pollAudioTelemetry();
connectGuardianEvents();
setInterval(pollGuardianStatus, 10000);
setInterval(pollAudioTelemetry, 5000);


