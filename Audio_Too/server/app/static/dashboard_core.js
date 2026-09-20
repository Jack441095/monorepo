// dashboard_core.js — Dashboard overview status panels and admin tasks

async function loadActivity() {
  const target = document.querySelector("#activity-log");
  if (!target) return;
  try {
    const data = await api("/api/activity?limit=120");
    if (!data.events.length) {
      target.innerHTML = "<p>No activity logged yet.</p>";
      return;
    }
    const rows = data.events.map((event) => `<tr><td>${escapeHtml(event.at)}</td><td>${escapeHtml(event.actor)}</td><td>${escapeHtml(event.event)}</td><td>${escapeHtml(event.detail)}</td></tr>`).join("");
    target.innerHTML = `<table><thead><tr><th>When</th><th>Actor</th><th>Event</th><th>Detail</th></tr></thead><tbody>${rows}</tbody></table>`;
  } catch (error) {
    target.innerHTML = `<p>${escapeHtml(error.message)}</p>`;
  }
}

document.querySelector("#activity-refresh")?.addEventListener("click", loadActivity);

async function loadHub() {
  const statusBox = document.querySelector("#hub-status");
  const actionsBox = document.querySelector("#hub-actions");
  const dueBox = document.querySelector("#hub-due");
  const attentionBox = document.querySelector("#hub-attention");
  const activityBox = document.querySelector("#hub-activity");
  const modulesBox = document.querySelector("#hub-modules");
  const abletonBox = document.querySelector("#hub-ableton");
  const intakeBox = document.querySelector("#client-intake-panel");
  const readinessBox = document.querySelector("#project-readiness-panel");
  if (!statusBox) return;
  try {
    const hub = await api("/api/admin/hub");
    let gapCount = 0;
    try {
      const gaps = await api("/api/ableton/gaps");
      gapCount = gaps.summary?.open ?? (gaps.items || []).length;
    } catch {
      gapCount = 0;
    }
    const s = hub.summary;
    const clientOps = hub.client_ops || {};
    const web = hub.ableton.web || {};
    const backup = hub.backup || {};
    const backupLabel = backup.latest
      ? backup.stale
        ? `Backup stale (${backup.age_days}d) — ${backup.latest}`
        : `Backup OK (${backup.age_days}d ago)`
      : "No backup yet";
    statusBox.innerHTML = `
      <span class="status-pill ${web.running ? "ok" : "warn"}">Ableton web ${web.running ? "online" : "offline"}</span>
      <span class="status-pill">${escapeHtml(String(s.new_enquiries ?? 0))} new website enquiry(ies)</span>
      <span class="status-pill ${clientOps.summary?.blocked_projects ? "warn" : "ok"}">${escapeHtml(String(clientOps.summary?.blocked_projects ?? 0))} blocked project(s)</span>
      <span class="status-pill">${escapeHtml(String(hub.ableton.transcript_drafts))} transcript draft(s)</span>
      <span class="status-pill ${gapCount ? "warn" : "ok"}">${gapCount} LM gap(s)</span>
      <span class="status-pill ${backup.stale ? "warn" : "ok"}">${escapeHtml(backupLabel)}</span>
    `;
    actionsBox.innerHTML = `
      <button type="button" class="action-card" data-goto="drafts">Review message drafts (${s.pending_drafts})</button>
      <button type="button" class="action-card" data-goto="transcripts">Transcript notes (${hub.ableton.transcript_drafts})</button>
      <button type="button" class="action-card" data-goto="lm-improve">LLM improvement</button>
      <button type="button" class="action-card" data-goto="lm-gaps">LM gaps (${gapCount})</button>
      <button type="button" class="action-card" data-goto="ableton">Ableton chat</button>
      <button type="button" class="action-card" id="hub-backup">Run backup</button>
      <button type="button" class="action-card" id="hub-build">Rebuild chatbot index</button>
      <button type="button" class="action-card" id="hub-refresh">Refresh dashboard</button>
    `;
    actionsBox.querySelectorAll("[data-goto]").forEach((el) => el.addEventListener("click", () => showTab(el.dataset.goto)));
    actionsBox.querySelector("#hub-backup")?.addEventListener("click", runBackup);
    actionsBox.querySelector("#hub-build")?.addEventListener("click", rebuildIndex);
    actionsBox.querySelector("#hub-refresh")?.addEventListener("click", () => {
      loadHub();
      loadAdmin();
    });

    if (dueBox) {
      if (!hub.due_items?.length) {
        dueBox.innerHTML = "<p>No follow-ups due today or overdue.</p>";
      } else {
        const rows = hub.due_items.map((item) => {
          const cls = item.overdue ? ' class="overdue-row"' : "";
          return `<tr${cls}><td>${escapeHtml(item.type)}</td><td>${escapeHtml(item.name || item.id)}</td><td>${escapeHtml(item.due)}</td><td>${escapeHtml(item.next_action || "—")}</td></tr>`;
        }).join("");
        dueBox.innerHTML = `<p class="compact-status">${hub.overdue_count} overdue · ${hub.due_count} due or overdue total</p><table><thead><tr><th>Type</th><th>Name</th><th>Due</th><th>Next</th></tr></thead><tbody>${rows}</tbody></table>`;
      }
    }

    const attention = [];
    (hub.recent_enquiries || []).forEach((e) => {
      if (e.status && e.status !== "New") return;
      attention.push(
        `<li><button type="button" data-goto="enquiries">${escapeHtml(e.name || "Enquiry")} — ${escapeHtml(e.service || "website")}</button></li>`
      );
    });
    hub.pending_drafts.forEach((d) => attention.push(`<li><button type="button" data-goto="drafts">${escapeHtml(d.subject || d.recipient || d.id)} — draft message</button></li>`));
    if (hub.ableton?.transcript_drafts) {
      attention.push(`<li><button type="button" data-goto="transcripts">${hub.ableton.transcript_drafts} transcript note(s) need review</button></li>`);
    }
    if (gapCount) {
      attention.push(`<li><button type="button" data-goto="lm-gaps">${gapCount} weak LM question(s) to improve</button></li>`);
    }
    if (!attention.length) attention.push("<li>Nothing flagged right now.</li>");
    attentionBox.innerHTML = `<ul class="hub-list">${attention.join("")}</ul>`;
    attentionBox.querySelectorAll("[data-goto]").forEach((el) => el.addEventListener("click", () => showTab(el.dataset.goto)));

    if (intakeBox) {
      intakeBox.innerHTML = renderClientIntake(clientOps);
      wireClientOps(intakeBox);
    }
    if (readinessBox) {
      readinessBox.innerHTML = renderProjectReadiness(clientOps);
    }

    if (!hub.activity.length) {
      activityBox.innerHTML = "<p>No activity yet.</p>";
    } else {
      const rows = hub.activity.map((e) => `<tr><td>${escapeHtml(e.at)}</td><td>${escapeHtml(e.actor)}</td><td>${escapeHtml(e.event)}</td><td>${escapeHtml(e.detail)}</td></tr>`).join("");
      activityBox.innerHTML = `<table><thead><tr><th>When</th><th>Actor</th><th>Event</th><th>Detail</th></tr></thead><tbody>${rows}</tbody></table>`;
    }

    modulesBox.innerHTML = `
      <div class="module-section">
        <h3>Website & business</h3>
        <div class="module-grid">
          <a class="module-card link-card" href="/" target="_blank" rel="noreferrer"><strong>Public website</strong><span>Enquiry form and services</span></a>
          <button type="button" class="module-card" data-goto="enquiries"><strong>Enquiries</strong><span>${s.new_enquiries ?? 0} new</span></button>
          <button type="button" class="module-card" data-goto="clients"><strong>Clients</strong><span>${s.clients} total</span></button>
          <button type="button" class="module-card" data-goto="leads"><strong>Leads</strong><span>${s.active_leads} active</span></button>
          <button type="button" class="module-card" data-goto="campaigns"><strong>Campaigns</strong><span>${s.campaigns} tracked</span></button>
          <button type="button" class="module-card" data-goto="invoices"><strong>Invoices</strong><span>${s.draft_invoices} draft · £${Number(s.draft_invoice_value).toFixed(2)}</span></button>
          <button type="button" class="module-card" data-goto="drafts"><strong>Drafts</strong><span>${s.pending_drafts} pending</span></button>
          <button type="button" class="module-card" data-goto="stems"><strong>Stem uploads</strong><span>Client delivery portal</span></button>
          <button type="button" class="module-card" data-goto="portfolio-ops"><strong>Portfolio publishing</strong><span>Projects and audio examples</span></button>
          <button type="button" class="module-card" data-goto="mix-review"><strong>Mix Review Lab</strong><span>Analyse WAV mixes</span></button>
        </div>
      </div>
      <div class="module-section">
        <h3>Ableton LLM</h3>
        <div class="module-grid">
          <a class="module-card link-card" href="/creative-lab" target="_blank" rel="noreferrer"><strong>Audio_Gen</strong><span>KENN + AudioGen workspace</span></a>
          <button type="button" class="module-card" data-goto="ableton"><strong>Ableton chat</strong><span>${web.running ? "Embedded UI ready" : "Start ./ableton web"}</span></button>
          <button type="button" class="module-card" data-goto="lm-improve"><strong>Improve LLM</strong><span>Audit, feedback, evals</span></button>
          <button type="button" class="module-card" data-goto="transcripts"><strong>Transcript review</strong><span>${hub.ableton.transcript_total} notes · ${hub.ableton.transcript_drafts} drafts</span></button>
          <button type="button" class="module-card" data-goto="lm-gaps"><strong>Knowledge gaps</strong><span>${gapCount} open</span></button>
          <a class="module-card link-card" href="/tips" target="_blank" rel="noreferrer"><strong>Studio tips</strong><span>Public retrieval Q&A</span></a>
        </div>
      </div>
      <div class="module-section">
        <h3>System</h3>
        <div class="module-grid">
          <button type="button" class="module-card" data-goto="activity"><strong>Activity log</strong><span>All agent events</span></button>
        </div>
      </div>
    `;
    modulesBox.querySelectorAll("[data-goto]").forEach((el) => el.addEventListener("click", () => showTab(el.dataset.goto)));

    abletonBox.innerHTML = `
      <p>${hub.ableton.transcript_total} training note(s) tracked · ${hub.ableton.transcript_drafts} need review.</p>
      <p class="compact-status">CLI: <code>./ableton train-chatbot "force: yes"</code> then approve in Transcript Review.</p>
      <div class="button-row">
        <button type="button" data-goto="lm-improve">Open improvement dashboard</button>
        <button type="button" data-goto="transcripts">Open transcript review</button>
        <button type="button" id="hub-train">Train from transcripts</button>
      </div>
    `;
    abletonBox.querySelectorAll("[data-goto]").forEach((el) => el.addEventListener("click", () => showTab(el.dataset.goto)));
    abletonBox.querySelector("#hub-train")?.addEventListener("click", trainFromTranscripts);
  } catch (error) {
    statusBox.textContent = error.message;
  }
}

const agentTaskForm = document.querySelector("#agent-task-form");
const agentTaskOutput = document.querySelector("#agent-task-output");

agentTaskForm?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const task = document.querySelector("#agent-task-input")?.value?.trim();
  const agent = document.querySelector("#agent-task-agent")?.value || "auto";
  if (!task) return;
  if (agentTaskOutput) agentTaskOutput.textContent = "Running…";
  statusEl.textContent = "";
  try {
    const data = await api("/api/admin/agent", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ task, agent }),
    });
    if (agentTaskOutput) {
      agentTaskOutput.textContent = `[${data.agent || "agent"} · ${data.command || "task"}]\n\n${data.output || ""}`;
    }
    statusEl.textContent = data.ok ? "Agent task finished." : "Agent task failed — see output.";
    await loadAdmin();
    await loadHub();
    if (document.querySelector('.tab[data-tab="activity"]')?.classList.contains("active")) {
      await loadActivity();
    }
  } catch (error) {
    if (agentTaskOutput) agentTaskOutput.textContent = error.message;
    statusEl.textContent = error.message;
  }
});

async function runBackup() {
  statusEl.textContent = "Creating backup…";
  try {
    const data = await api("/api/admin/backup", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
    statusEl.textContent = data.message || "Backup complete.";
    await loadActivity();
    await loadHub();
  } catch (error) {
    statusEl.textContent = error.message;
  }
}

async function rebuildIndex() {
  statusEl.textContent = "Rebuilding Ableton index…";
  try {
    const data = await api("/api/ableton/build", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
    statusEl.textContent = data.ok ? "Chatbot index rebuilt." : "Index build failed.";
    await loadActivity();
  } catch (error) {
    statusEl.textContent = error.message;
  }
}

async function trainFromTranscripts() {
  if (!confirm("Paraphrase all transcripts, approve, and rebuild the index?")) return;
  statusEl.textContent = "Training chatbot from transcripts…";
  try {
    const data = await api("/api/ableton/train-chatbot", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        force: "yes",
        approve: "yes",
        build: "yes",
        llm: typeof paraphraseLlmPayload === "function" ? paraphraseLlmPayload() : null,
      }),
    });
    statusEl.textContent = data.message || "Training complete.";
    await loadHub();
    await loadAdmin();
    typeof loadTranscripts === "function" && loadTranscripts();
    await loadActivity();
  } catch (error) {
    statusEl.textContent = error.message;
  }
}

function renderMetrics(summary) {
  metricsEl.innerHTML = [
    ["Clients", summary.clients],
    ["Projects", summary.active_projects],
    ["Draft invoices", summary.draft_invoices],
    ["Draft value", `£${Number(summary.draft_invoice_value).toFixed(2)}`],
    ["Leads", summary.active_leads],
    ["Campaigns", summary.campaigns],
    ["Drafts", summary.pending_drafts],
    ["New enquiries", summary.new_enquiries ?? 0],
  ].map(([label, value]) => `<div class="metric"><strong>${escapeHtml(value)}</strong><span>${escapeHtml(label)}</span></div>`).join("");
}
