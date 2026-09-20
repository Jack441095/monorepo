// crm_workspaces.js — Business CRM workspace tables, updates and form triggers

async function loadAdmin() {
  try {
    const data = await api("/api/admin/dashboard");
    dashboardCache = data;
    invoiceLinkMap = {};
    if (data.records.invoices?.length) {
      const linkData = await api("/api/admin/invoice-links", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ids: data.records.invoices.map((row) => row.id) }),
      });
      invoiceLinkMap = linkData.links || {};
    }
    renderMetrics(data.summary);
    renderTable("projects", data.records.projects, ["id", "project", "client", "service", "status", "next_action"]);
    renderTable("clients", data.records.clients, ["id", "name", "contact", "status", "notes"]);
    renderTable("leads", data.records.leads, ["id", "lead", "service_fit", "status", "score", "next_action"]);
    renderTable("enquiries", data.records.enquiries, ["id", "name", "email", "service", "status", "deadline"]);
    renderTable("campaigns", data.records.campaigns, ["id", "campaign", "audience", "service", "platforms", "status"]);
    renderTable("invoices", data.records.invoices, ["id", "client", "service", "total", "status", "date"]);
    renderTable("drafts", data.drafts, ["id", "type", "recipient", "subject", "status"]);
    populateAudioGenProjects(data.records.projects || []);
    statusEl.textContent = "";
  } catch (error) {
    statusEl.textContent = error.message;
  }
}

function renderTable(name, records, fields) {
  const target = sections[name];
  if (!target) return;
  if (!records || records.length === 0) {
    target.innerHTML = "<p>No records.</p>";
    return;
  }
  const rows = records.map((record) => {
    const cells = fields.map((field) => `<td>${escapeHtml(record[field] || "-")}</td>`).join("");
    const status = record.status || "";
    const links = invoiceLinkMap[record.id] || {};
    const invoiceLinks = name === "invoices" && links.html_url
      ? `<br><a href="${escapeHtml(links.html_url)}" target="_blank" rel="noreferrer">Open</a> · <a href="${escapeHtml(links.pdf_url)}" target="_blank" rel="noreferrer">PDF</a><br><span class="compact-status">Signed link · ${links.expires_in_days || 7}d</span>`
      : "";
    const draftActions = name === "drafts" && (status === "Pending" || !status)
      ? `<td class="draft-actions"><button type="button" data-draft-status="Approved" data-id="${escapeHtml(record.id)}">Approve</button> <button type="button" class="secondary" data-draft-status="Rejected" data-id="${escapeHtml(record.id)}">Reject</button></td>`
      : name === "drafts" && status === "Approved"
        ? `<td class="draft-actions"><button type="button" data-queue-draft-delivery="${escapeHtml(record.id)}">Queue email</button> <button type="button" class="secondary" data-send-draft="${escapeHtml(record.id)}">Mark sent</button></td>`
        : name === "drafts"
          ? `<td><span class="compact-status">${escapeHtml(status)}</span></td>`
          : "";
    const enquiryActions =
      name === "enquiries" && status === "New"
        ? `<td><button type="button" data-convert-enquiry="${escapeHtml(record.id)}">Convert to client</button></td>`
        : name === "enquiries"
          ? `<td><span class="compact-status">${escapeHtml(status)}</span></td>`
          : "";
    const leadActions =
      name === "leads" && !["Converted", "Closed", "Not interested"].includes(status)
        ? `<td><button type="button" data-convert-lead="${escapeHtml(record.id)}">Convert to client</button></td>`
        : name === "leads"
          ? `<td><span class="compact-status">${escapeHtml(status)}</span></td>`
          : "";
    const projectActions =
      name === "projects"
        ? `<td class="gap-actions"><button type="button" data-project-workspace="${escapeHtml(record.id)}">Workspace</button> <button type="button" data-stem-link="${escapeHtml(record.id)}">Upload link</button></td>`
        : "";
    const actions =
      draftActions ||
      enquiryActions ||
      leadActions ||
      projectActions ||
      `<td><select data-table="${name}" data-id="${escapeHtml(record.id)}"><option>${escapeHtml(status || "Set status")}</option><option>New</option><option>Active</option><option>Warm</option><option>Quoted</option><option>Paid</option><option>Delivered</option><option>Closed</option><option>Rejected</option><option>Approved</option><option>Pending</option><option>Converted</option><option>Contacted</option></select>${invoiceLinks}</td>`;
    return `<tr>${cells}${actions}</tr>`;
  }).join("");
  const heads = fields.map((field) => `<th>${escapeHtml(field.replaceAll("_", " "))}</th>`).join("");
  const actionHead = ["enquiries", "leads", "projects"].includes(name) ? "action" : "update";
  target.innerHTML = `<table><thead><tr>${heads}<th>${actionHead}</th></tr></thead><tbody>${rows}</tbody></table>`;
}

document.addEventListener("click", async (event) => {
  const workspaceBtn = event.target.closest("[data-project-workspace]");
  if (workspaceBtn) {
    const projectId = workspaceBtn.dataset.projectWorkspace;
    if (!projectWorkspaceEl || !projectId) return;
    projectWorkspaceEl.innerHTML = "<p class='compact-status'>Loading project workspace...</p>";
    try {
      const data = await api(`/api/admin/projects/workspace?id=${encodeURIComponent(projectId)}`);
      projectWorkspaceEl.innerHTML = renderProjectWorkspace(data);
    } catch (error) {
      projectWorkspaceEl.innerHTML = `<p class='compact-status'>${escapeHtml(error.message)}</p>`;
    }
    return;
  }
  const stemBtn = event.target.closest("[data-stem-link]");
  if (stemBtn) {
    const projectId = stemBtn.dataset.stemLink;
    try {
      const data = await api("/api/admin/projects/stem-link", {
        method: "POST",
        body: JSON.stringify({ project_id: projectId, ttl_days: 14 }),
      });
      const url = data.upload_url || "";
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(url);
        statusEl.textContent = `Upload link copied (${data.expires_in_days || 14} days).`;
      } else {
        statusEl.textContent = url;
      }
    } catch (error) {
      statusEl.textContent = error.message;
    }
    return;
  }
  const convertLead = event.target.closest("[data-convert-lead]");
  if (convertLead) {
    if (!confirm("Create a client and project from this lead?")) return;
    try {
      await api("/api/v1/business/leads/conversions", {
        method: "POST",
        headers: { "Idempotency-Key": idempotencyKey("lead-conversion") },
        body: JSON.stringify({ id: convertLead.dataset.convertLead }),
      });
      await loadAdmin();
      await loadHub();
      statusEl.textContent = "Lead converted to client and project.";
    } catch (error) {
      statusEl.textContent = error.message;
    }
    return;
  }
  const convert = event.target.closest("[data-convert-enquiry]");
  if (convert) {
    if (!confirm("Create client, project, and lead from this enquiry?")) return;
    try {
      await api("/api/v1/business/enquiries/conversions", {
        method: "POST",
        headers: { "Idempotency-Key": idempotencyKey("enquiry-conversion") },
        body: JSON.stringify({ id: convert.dataset.convertEnquiry }),
      });
      await loadAdmin();
      await loadHub();
      statusEl.textContent = "Enquiry converted to client, project, and lead.";
    } catch (error) {
      statusEl.textContent = error.message;
    }
    return;
  }
  const target = event.target.closest("[data-draft-status]");
  const queueDelivery = event.target.closest("[data-queue-draft-delivery]");
  if (queueDelivery) {
    const recipientEmail = prompt("Recipient email address:", "")?.trim();
    if (!recipientEmail) return;
    if (!confirm(`Queue this approved draft for email delivery to ${recipientEmail}?`)) return;
    try {
      const data = await api("/api/v1/business/draft-deliveries", {
        method: "POST",
        headers: { "Idempotency-Key": idempotencyKey("draft-delivery") },
        body: JSON.stringify({
          id: queueDelivery.dataset.queueDraftDelivery,
          recipient_email: recipientEmail,
        }),
      });
      await loadAdmin();
      await loadHub();
      statusEl.textContent = `Delivery ${data.delivery.id} queued. External email remains policy-controlled.`;
    } catch (error) {
      statusEl.textContent = error.message;
    }
    return;
  }
  const sendDraft = event.target.closest("[data-send-draft]");
  if (sendDraft) {
    if (!confirm("Mark this approved draft as sent and schedule a follow-up?")) return;
    try {
      const data = await api("/api/v1/business/drafts/sends", {
        method: "POST",
        headers: { "Idempotency-Key": idempotencyKey("draft-send") },
        body: JSON.stringify({ id: sendDraft.dataset.sendDraft }),
      });
      await loadAdmin();
      await loadHub();
      statusEl.textContent = data.already_sent
        ? "Draft was already sent."
        : "Draft marked sent and follow-up scheduled.";
    } catch (error) {
      statusEl.textContent = error.message;
    }
    return;
  }
  if (!target) return;
  try {
    await api("/api/admin/status", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ table: "drafts", id: target.dataset.id, status: target.dataset.draftStatus }),
    });
    await loadAdmin();
    await loadHub();
    if (document.querySelector('.tab[data-tab="activity"]')?.classList.contains("active")) {
      await loadActivity();
    }
  } catch (error) {
    statusEl.textContent = error.message;
  }
});

function renderProjectWorkspace(data = {}) {
  const project = data.project || {};
  const summary = data.summary || {};
  return `
    <article class="compact-card project-workspace-card">
      <strong>${escapeHtml(project.project || project.service || "Project workspace")}</strong>
      <span>${escapeHtml(project.client || "No client")} · ${escapeHtml(project.status || "No status")}</span>
      <div class="hub-status">
        <span class="status-pill">${escapeHtml(summary.uploads ?? 0)} upload(s)</span>
        <span class="status-pill">${escapeHtml(summary.mix_reviews ?? 0)} mix review(s)</span>
        <span class="status-pill">${escapeHtml(summary.audio ?? 0)} audio item(s)</span>
        <span class="status-pill">${escapeHtml(summary.invoices ?? 0)} invoice(s)</span>
      </div>
      <p class="compact-status">${escapeHtml(project.next_action || "Set a next action for this project.")}</p>
    </article>
  `;
}

document.addEventListener("change", async (event) => {
  const target = event.target;
  if (!target.matches("select[data-table]")) return;
  const tableMap = {
    projects: "projects",
    clients: "clients",
    leads: "leads",
    campaigns: "campaigns",
    invoices: "invoices",
    drafts: "drafts",
  };
  try {
    await api("/api/admin/status", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ table: tableMap[target.dataset.table], id: target.dataset.id, status: target.value }),
    });
    await loadAdmin();
    if (document.querySelector('.tab[data-tab="activity"]')?.classList.contains("active")) {
      await loadActivity();
    }
  } catch (error) {
    statusEl.textContent = error.message;
  }
});

draftForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const payload = Object.fromEntries(new FormData(draftForm).entries());
  try {
    await api("/api/admin/draft", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ type: "message", source: "admin", ...payload }),
    });
    draftForm.reset();
    await loadAdmin();
    await loadActivity();
  } catch (error) {
    statusEl.textContent = error.message;
  }
});
