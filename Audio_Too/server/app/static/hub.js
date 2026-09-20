const modulesEl = document.querySelector("#hub-modules");
const statusLine = document.querySelector("#hub-status-line");
const originEl = document.querySelector("#hub-origin");
const tipsPortEl = document.querySelector("#hub-tips-port");
const frame = document.querySelector("#hub-tips-frame");
const placeholder = document.querySelector("#hub-embed-placeholder");

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function pill(running, sameServer) {
  if (running === false) return '<span class="status-pill warn">Offline</span>';
  if (sameServer) return '<span class="status-pill ok">On :8080</span>';
  return '<span class="status-pill ok">Running</span>';
}

function moduleAction(mod, label = "Open") {
  if (mod.url) {
    const target = mod.open_in === "new" ? ' target="_blank" rel="noopener"' : "";
    return `<a class="button" href="${escapeHtml(mod.url)}"${target}>${escapeHtml(label)}</a>`;
  }
  if (mod.command) {
    return `<code class="hub-cli">${escapeHtml(mod.command)}</code>`;
  }
  return "";
}

function previewRow(title, description) {
  return `
    <div class="hub-preview-row">
      <strong>${escapeHtml(title)}</strong>
      <span>${escapeHtml(description)}</span>
    </div>
  `;
}

function moduleRow(mod, label = "Open") {
  const tags = [pill(mod.running, mod.same_server)];
  if (mod.requires_auth) tags.push('<span class="status-pill">Sign-in required</span>');
  const hint = mod.hint ? `<small>${escapeHtml(mod.hint)}</small>` : "";
  return `
    <div class="hub-link-row">
      <div>
        <strong>${escapeHtml(mod.name)}</strong>
        <span>${escapeHtml(mod.description)}</span>
        ${hint}
      </div>
      <div class="hub-row-meta">${tags.join("")}${moduleAction(mod, label)}</div>
    </div>
  `;
}

function renderModules(data) {
  const modules = data.modules || [];
  const byId = Object.fromEntries(modules.map((mod) => [mod.id, mod]));
  const llm = data.llm || {};
  const tips = byId.tips_web;
  const kennPill = tips?.running
    ? '<span class="status-pill ok">KENN online</span>'
    : '<span class="status-pill warn">KENN chat offline</span>';
  const rewritePill = llm.enabled
    ? '<span class="status-pill ok">Rewrite on</span>'
    : '<span class="status-pill">Retrieval only</span>';

  const websiteRows = ["public", "dashboard", "faq", "stem_upload"]
    .map((id) => byId[id] && moduleRow(byId[id], id === "dashboard" ? "Open dashboard" : "Open"))
    .filter(Boolean)
    .join("");
  const llmRows = ["demo", "tips_web", "studio_tips", "tips_cli"]
    .map((id) => byId[id] && moduleRow(byId[id], id === "tips_web" ? "Open chat" : "Open"))
    .filter(Boolean)
    .join("");
  const audiogen = byId.audiogen;
  const audiogenStatus = data.audiogen?.ok
    ? '<span class="status-pill ok">Ready</span>'
    : '<span class="status-pill warn">Not detected</span>';
  const latestAudit = data.audiogen?.latest_audit?.updated_at || "No audit yet";
  const audiogenRows = [
    previewRow("KENN prompts", "Ask for production direction, arrangement ideas, and generation prompts."),
    previewRow("Quick phrase", "Generate a loop from emotion presets."),
    previewRow("Render song", "Queue a full-song render and audition it in the browser."),
    previewRow("Latest audit", latestAudit),
    previewRow("Portfolio audio", `${data.audiogen?.portfolio_audio_count || 0} files`),
  ]
    .filter(Boolean)
    .join("");
  const portfolioPreview = [
    previewRow("Codebases", "Audio_Too systems, agents, dashboards, and LLM tooling."),
    previewRow("Music & audio", "Production work, examples, masters, and audio case studies."),
    previewRow("Project stories", "Readable summaries of what was built and why it matters."),
  ].join("");

  modulesEl.innerHTML = `
    <article class="hub-workspace">
      <div class="hub-workspace-head">
        <div>
          <p class="eyebrow">Workspace 1</p>
          <h2>Website & business</h2>
        </div>
        <span class="status-pill ok">Website :${escapeHtml(String(data.website_port))}</span>
      </div>
      <p>Public site, client enquiries, CRM records, invoices, drafts, and client file delivery.</p>
      <div class="hub-primary-actions hub-primary-actions-vertical">
        ${byId.dashboard ? moduleAction(byId.dashboard, "Open dashboard") : ""}
        ${byId.public ? moduleAction(byId.public, "Open public site") : ""}
      </div>
      <div class="hub-link-list">${websiteRows}</div>
    </article>

    <article class="hub-workspace">
      <div class="hub-workspace-head">
        <div>
          <p class="eyebrow">Workspace 2</p>
          <h2>Portfolio</h2>
        </div>
        <span class="status-pill ok">Standalone</span>
      </div>
      <p>Separate showcase for codebases, systems, music, production work, and audio examples.</p>
      <div class="hub-preview-list">${portfolioPreview}</div>
      <div class="hub-primary-actions">
        ${byId.portfolio ? moduleAction(byId.portfolio, "Open portfolio") : ""}
      </div>
    </article>

    <article class="hub-workspace">
      <div class="hub-workspace-head">
        <div>
          <p class="eyebrow">Workspace 3</p>
          <h2>Audio_Gen</h2>
        </div>
        <div class="hub-status-pair">${kennPill}${rewritePill}${audiogenStatus}</div>
      </div>
      <p>Private writing room for KENN guidance, AudioGen loops, full-song renders, playback, and local history.</p>
      <div class="hub-primary-actions">
        ${byId.creative_lab ? moduleAction(byId.creative_lab, "Open Audio_Gen") : ""}
      </div>
      <div class="hub-link-list">${audiogenRows}</div>
    </article>

    <article class="hub-workspace">
      <div class="hub-workspace-head">
        <div>
          <p class="eyebrow">Workspace 4</p>
          <h2>KENN services</h2>
        </div>
        <div class="hub-status-pair">${kennPill}${rewritePill}</div>
      </div>
      <p>Direct chat, tester demo, public tips, and terminal access for the retrieval-first production assistant.</p>
      <div class="hub-primary-actions">
        ${byId.demo ? moduleAction(byId.demo, "Open tester demo") : ""}
        ${byId.tips_web ? moduleAction(byId.tips_web, "Open chat") : ""}
        ${byId.studio_tips ? moduleAction(byId.studio_tips, "Open public tips") : ""}
      </div>
      <div class="hub-link-list">${llmRows}</div>
    </article>
  `;

  if (tips && tips.running && tips.url && frame) {
    frame.src = tips.url;
    frame.hidden = false;
    if (placeholder) placeholder.hidden = true;
  } else if (frame) {
    frame.hidden = true;
    frame.removeAttribute("src");
    if (placeholder) {
      placeholder.hidden = false;
      placeholder.textContent = tips?.hint || "Start chat with ./start.sh or ./ableton web";
    }
  }
}

async function loadHub() {
  try {
    const response = await fetch("/api/hub/status");
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Status failed");

    if (originEl) originEl.textContent = `http://${data.host}:${data.website_port}`;
    if (tipsPortEl) tipsPortEl.textContent = String(data.tips_port);

    const tips = (data.modules || []).find((m) => m.id === "tips_web");
    const tipsLabel = tips?.running ? "Tips chat :8090 up" : "Tips chat :8090 down";
    const llmLabel = data.llm?.enabled ? " · rewrite enabled" : " · retrieval-only answers";
    const audioGenLabel = data.audiogen?.ok ? " · AudioGen ready" : " · AudioGen unavailable";
    if (statusLine) statusLine.textContent = `Website :${data.website_port} · ${tipsLabel}${llmLabel}${audioGenLabel}`;

    renderModules(data);
  } catch (error) {
    if (statusLine) statusLine.textContent = `Could not load hub status (${error.message}). Is ./start.sh running?`;
  }
}

loadHub();
