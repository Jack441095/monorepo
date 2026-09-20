function formatTopics(topics) {
  if (!Array.isArray(topics) || !topics.length) return "—";
  return topics.map((t) => escapeHtml(String(t))).join(", ");
}

function wireGapTableActions(root) {
  if (!root) return;
  root.querySelectorAll("[data-dismiss-gap]").forEach((button) => {
    button.addEventListener("click", async () => {
      await api("/api/ableton/gaps/dismiss", {
        method: "POST",
        body: JSON.stringify({ id: button.dataset.dismissGap }),
      });
      loadLmGaps();
    });
  });
  root.querySelectorAll("[data-create-gap-note]").forEach((button) => {
    button.addEventListener("click", async () => {
      const id = button.dataset.createGapNote;
      button.disabled = true;
      try {
        const result = await api("/api/ableton/gaps/create-note", {
          method: "POST",
          body: JSON.stringify({ id }),
        });
        statusEl.textContent = result.message || `Created ${result.note}`;
        showTab("transcripts");
        await loadTranscripts();
        if (result.note) await openNote(result.note, result.note.replace(/\.md$/, "").replace(/-/g, " "));
        loadLmGaps();
      } catch (error) {
        statusEl.textContent = error.message;
        button.disabled = false;
      }
    });
  });
  root.querySelectorAll("[data-retest-gap]").forEach((button) => {
    button.addEventListener("click", async () => {
      button.disabled = true;
      try {
        const result = await api("/api/ableton/gaps/retest", {
          method: "POST",
          body: JSON.stringify({ id: button.dataset.retestGap }),
        });
        statusEl.textContent = result.resolved
          ? `Resolved — now backed by a note (${result.confidence || ""}).`
          : `Still weak (${result.confidence || "low"}). Add or approve a note, then build index.`;
        loadLmGaps();
      } catch (error) {
        statusEl.textContent = error.message;
        button.disabled = false;
      }
    });
  });
  root.querySelectorAll("[data-try-gap-chat]").forEach((button) => {
    button.addEventListener("click", () => {
      const q = button.dataset.tryGapChat || "";
      if (abletonQuestion) abletonQuestion.value = q;
      showTab("ableton");
      const details = document.querySelector(".ableton-quick-ask");
      if (details) details.open = true;
      if (q) askAbleton(q);
    });
  });
  root.querySelectorAll("[data-retest-feedback]").forEach((button) => {
    button.addEventListener("click", async () => {
      button.disabled = true;
      try {
        const result = await api("/api/ableton/improvement/retest-feedback", {
          method: "POST",
          body: JSON.stringify({ id: button.dataset.retestFeedback || "" }),
        });
        statusEl.textContent = result.resolved
          ? `Repair resolved: ${result.confidence} confidence, ${result.source_quality} sources.`
          : `Repair still needs review: ${result.failed_checks?.join(", ") || "validation failed"}.`;
        await loadLmImprove();
      } catch (error) {
        statusEl.textContent = error.message;
        button.disabled = false;
      }
    });
  });
}

function renderGapRows(items, { includeDraft = false } = {}) {
  return items
    .map((item) => {
      const noteCell = item.note_file
        ? `<a href="#" data-open-note="${escapeHtml(item.note_file)}">${escapeHtml(item.note_file)}</a>`
        : "—";
      const draftActions = includeDraft
        ? `<button type="button" class="secondary" data-retest-gap="${escapeHtml(item.id)}">Recheck</button>`
        : `<button type="button" data-create-gap-note="${escapeHtml(item.id)}">Create draft note</button>
          <button type="button" class="secondary" data-dismiss-gap="${escapeHtml(item.id)}">Dismiss</button>`;
      return `
      <tr>
        <td>${escapeHtml(item.question || "")}</td>
        <td>${formatTopics(item.topics)}</td>
        <td>${escapeHtml(item.confidence || "")}</td>
        <td>${escapeHtml(item.channel || "")}</td>
        <td>${escapeHtml(item.top_source || "")}</td>
        <td>${noteCell}</td>
        <td>${escapeHtml(item.created_at || "")}</td>
        <td class="gap-actions">
          <button type="button" class="secondary" data-try-gap-chat="${escapeHtml(item.question || "")}">Try in chat</button>
          ${draftActions}
        </td>
      </tr>`;
    })
    .join("");
}

async function loadLmGaps() {
  const gapsTable = document.querySelector("#lm-gaps-table");
  const draftedTable = document.querySelector("#lm-gaps-drafted");
  const summaryEl = document.querySelector("#lm-gaps-summary");
  const queriesTable = document.querySelector("#lm-queries-table");
  if (!gapsTable) return;
  gapsTable.innerHTML = "<p class='compact-status'>Loading…</p>";
  if (draftedTable) draftedTable.innerHTML = "";
  if (queriesTable) queriesTable.innerHTML = "";
  try {
    const [gapsData, queriesData] = await Promise.all([
      api("/api/ableton/gaps"),
      queriesTable ? api("/api/ableton/queries") : Promise.resolve({ items: [] }),
    ]);
    const summary = gapsData.summary || {};
    if (summaryEl) {
      summaryEl.textContent = `${summary.open ?? 0} open · ${summary.drafted ?? 0} drafted · ${summary.resolved ?? 0} resolved · ${summary.dismissed ?? 0} dismissed`;
    }
    const items = gapsData.items || [];
    const drafted = gapsData.drafted || [];
    const gapHead = `<table><thead><tr><th>Question</th><th>Topics</th><th>Confidence</th><th>Channel</th><th>Top source</th><th>Note</th><th>When</th><th>Actions</th></tr></thead><tbody>`;
    if (!items.length) {
      gapsTable.innerHTML = "<p class='compact-status'>No open gaps — nice work.</p>";
    } else {
      gapsTable.innerHTML = `${gapHead}${renderGapRows(items)}</tbody></table>`;
      wireGapTableActions(gapsTable);
      gapsTable.querySelectorAll("[data-open-note]").forEach((link) => {
        link.addEventListener("click", (event) => {
          event.preventDefault();
          const name = link.dataset.openNote;
          showTab("transcripts");
          openNote(name, name.replace(/\.md$/, "").replace(/-/g, " "));
        });
      });
    }
    if (draftedTable) {
      if (!drafted.length) {
        draftedTable.innerHTML = "<p class='compact-status'>No drafted gaps.</p>";
      } else {
        draftedTable.innerHTML = `${gapHead}${renderGapRows(drafted, { includeDraft: true })}</tbody></table>`;
        wireGapTableActions(draftedTable);
        draftedTable.querySelectorAll("[data-open-note]").forEach((link) => {
          link.addEventListener("click", (event) => {
            event.preventDefault();
            const name = link.dataset.openNote;
            showTab("transcripts");
            openNote(name, name.replace(/\.md$/, "").replace(/-/g, " "));
          });
        });
      }
    }

    if (queriesTable) {
      const queries = queriesData.items || [];
      if (!queries.length) {
        queriesTable.innerHTML = "<p class='compact-status'>No logged questions yet.</p>";
      } else {
        const qrows = queries
          .slice(0, 25)
          .map(
            (item) => `
        <tr>
          <td>${escapeHtml(item.question || "")}</td>
          <td>${escapeHtml(item.confidence || "")}</td>
          <td>${escapeHtml(item.channel || "")}</td>
          <td>${escapeHtml(item.created_at || "")}</td>
          <td>
            <button type="button" class="secondary" data-draft-from-query="${escapeHtml(item.question || "")}">Draft note</button>
          </td>
        </tr>`
          )
          .join("");
        queriesTable.innerHTML = `<table><thead><tr><th>Question</th><th>Confidence</th><th>Channel</th><th>When</th><th>Actions</th></tr></thead><tbody>${qrows}</tbody></table>`;
        queriesTable.querySelectorAll("[data-draft-from-query]").forEach((button) => {
          button.addEventListener("click", async () => {
            const question = button.dataset.draftFromQuery || "";
            button.disabled = true;
            try {
              const result = await api("/api/ableton/gaps/create-note-from-question", {
                method: "POST",
                body: JSON.stringify({ question }),
              });
              statusEl.textContent = result.message || `Created ${result.note}`;
              showTab("transcripts");
              await loadTranscripts();
              if (result.note) await openNote(result.note, result.note.replace(/\.md$/, "").replace(/-/g, " "));
              loadLmGaps();
            } catch (error) {
              statusEl.textContent = error.message;
              button.disabled = false;
            }
          });
        });
      }
    }
  } catch (error) {
    gapsTable.innerHTML = `<p class='compact-status'>${escapeHtml(error.message)}</p>`;
  }
}

document.querySelector("#lm-gaps-refresh")?.addEventListener("click", loadLmGaps);
document.querySelector("#lm-gaps-retest-all")?.addEventListener("click", async () => {
  const button = document.querySelector("#lm-gaps-retest-all");
  if (button) button.disabled = true;
  try {
    const result = await api("/api/ableton/gaps/retest", { method: "POST", body: "{}" });
    statusEl.textContent = `Rechecked ${result.checked ?? 0}: ${result.resolved ?? 0} resolved, ${result.still_weak ?? 0} still weak.`;
    loadLmGaps();
  } catch (error) {
    statusEl.textContent = error.message;
  } finally {
    if (button) button.disabled = false;
  }
});

function renderLmScorecards(data) {
  const gaps = data.gaps || {};
  const feedback = data.feedback || {};
  const analytics = feedback.analytics || {};
  const audit = data.latest_audit || {};
  const bench = data.latest_benchmark || {};
  const auditStatus = audit.status || "none";
  const passed = bench.passed_runs ?? audit.benchmark?.passed_runs ?? "—";
  const total = bench.total_runs ?? audit.benchmark?.total_runs ?? "—";
  const p95 = bench.duration_ms?.p95 ?? audit.benchmark?.duration_ms?.p95 ?? "—";
  return [
    ["Audit", auditStatus, audit.warnings?.length ? audit.warnings.join(", ") : "No warnings"],
    ["Eval/bench", `${passed}/${total}`, `p95 ${p95} ms`],
    ["Open gaps", gaps.open ?? 0, `${gaps.drafted ?? 0} drafted · ${gaps.resolved ?? 0} resolved`],
    ["Agent queue", data.agent_queue?.total ?? 0, "ranked improvement candidate(s)"],
    ["Draft evals", data.draft_eval_count ?? 0, "feedback case(s) waiting for review"],
    ["Tester feedback", feedback.needs_work ?? 0, `${feedback.useful ?? 0} useful · ${feedback.total_recent ?? 0} recent`],
    ["Demo weak rate", `${Math.round(Number(analytics.weak_rate || 0) * 100)}%`, `${analytics.total_recent_questions ?? 0} recent demo question(s)`],
    ["Demo sessions", analytics.sessions?.length ?? 0, `${Math.round(Number(analytics.feedback_rate || 0) * 100)}% feedback rate`],
  ]
    .map(([label, value, detail]) => `<div class="metric lm-metric"><strong>${escapeHtml(value)}</strong><span>${escapeHtml(label)}</span><small>${escapeHtml(detail)}</small></div>`)
    .join("");
}

function renderAgentQueue(queue) {
  const items = queue?.items || [];
  if (!items.length) return "<p class='compact-status'>No agent recommendations right now.</p>";
  return `<div class="lm-agent-list">${items.map((item) => {
    const evidence = (item.evidence || [])
      .slice(0, 3)
      .map((entry) => {
        const comment = entry.comment ? ` · ${entry.comment}` : "";
        const top = entry.top_source ? ` · ${entry.top_source}` : "";
        const answer = entry.answer_preview ? `<br><span class="compact-status">Answer: ${escapeHtml(entry.answer_preview)}</span>` : "";
        return `<li>${escapeHtml(entry.reason || entry.source || "")}${escapeHtml(comment)}${escapeHtml(top)}${answer}</li>`;
      })
      .join("");
    const meta = [
      item.confidence ? `${item.confidence} confidence` : "",
      item.source_quality ? `${item.source_quality} sources` : "",
      item.evidence_count ? `${item.evidence_count} signal(s)` : "",
    ].filter(Boolean).join(" · ");
    return `<article class="lm-agent-item">
      <div>
        <strong>${escapeHtml(item.question || "")}</strong>
        <p class="compact-status">${escapeHtml(meta || "Improvement candidate")}</p>
        <p>${escapeHtml(item.recommendation || "")}</p>
        ${item.answer_preview ? `<p class="repair-preview">${escapeHtml(item.answer_preview)}</p>` : ""}
        ${item.top_source ? `<p class="compact-status">Top source: ${escapeHtml(item.top_source)}</p>` : ""}
        ${evidence ? `<ul>${evidence}</ul>` : ""}
      </div>
      <div class="gap-actions">
        <button type="button"
          data-agent-draft="1"
          data-source="${escapeHtml(item.source || "")}"
          data-source-id="${escapeHtml(item.source_id || "")}"
          data-question="${escapeHtml(item.question || "")}"
          data-topics="${escapeHtml(JSON.stringify(item.topics || []))}">Draft note</button>
        <button type="button" class="secondary" data-try-gap-chat="${escapeHtml(item.question || "")}">Try in chat</button>
      </div>
    </article>`;
  }).join("")}</div>`;
}

function renderRepairPlan(plan) {
  const items = plan?.items || [];
  if (!items.length) return "<p class='compact-status'>No repair actions right now. Run an audit or benchmark to collect fresh signals.</p>";
  return `<div class="lm-repair-plan-list">${items.map((item, index) => {
    const command = item.command ? `<code>${escapeHtml(item.command)}</code>` : "";
    return `<article class="lm-repair-plan-item">
      <span class="repair-rank">${index + 1}</span>
      <div>
        <strong>${escapeHtml(item.title || "Repair action")}</strong>
        <p>${escapeHtml(item.action || "")}</p>
        <p class="compact-status">${escapeHtml(item.evidence || "")}</p>
        <p class="compact-status">${escapeHtml(item.workflow || "")} ${command}</p>
      </div>
    </article>`;
  }).join("")}</div>`;
}

function wireAgentQueue(root) {
  if (!root) return;
  root.querySelectorAll("[data-agent-draft]").forEach((button) => {
    button.addEventListener("click", async () => {
      button.disabled = true;
      let topics = [];
      try {
        topics = JSON.parse(button.dataset.topics || "[]");
      } catch {
        topics = [];
      }
      try {
        const result = await api("/api/ableton/improvement/draft", {
          method: "POST",
          body: JSON.stringify({
            source: button.dataset.source || "",
            source_id: button.dataset.sourceId || "",
            question: button.dataset.question || "",
            topics,
          }),
        });
        statusEl.textContent = result.message || `Created ${result.note}`;
        showTab("transcripts");
        await loadTranscripts();
        if (result.note) await openNote(result.note, result.note.replace(/\.md$/, "").replace(/-/g, " "));
      } catch (error) {
        statusEl.textContent = error.message;
        button.disabled = false;
      }
    });
  });
  root.querySelectorAll("[data-retest-feedback]").forEach((button) => {
    button.addEventListener("click", async () => {
      button.disabled = true;
      try {
        const result = await api("/api/ableton/improvement/retest-feedback", {
          method: "POST",
          body: JSON.stringify({ id: button.dataset.retestFeedback || "" }),
        });
        statusEl.textContent = result.resolved
          ? `Repair resolved: ${result.confidence} confidence, ${result.source_quality} sources.`
          : `Repair still needs review: ${result.failed_checks?.join(", ") || "validation failed"}.`;
        await loadLmImprove();
      } catch (error) {
        statusEl.textContent = error.message;
        button.disabled = false;
      }
    });
  });
  root.querySelectorAll("[data-draft-feedback-eval]").forEach((button) => {
    button.addEventListener("click", async () => {
      button.disabled = true;
      try {
        const result = await api("/api/ableton/improvement/draft-eval", {
          method: "POST",
          body: JSON.stringify({ id: button.dataset.draftFeedbackEval || "" }),
        });
        statusEl.textContent = result.message || "Draft eval saved.";
        await loadLmImprove();
      } catch (error) {
        statusEl.textContent = error.message;
        button.disabled = false;
      }
    });
  });
  root.querySelectorAll("[data-try-gap-chat]").forEach((button) => {
    button.addEventListener("click", () => {
      const q = button.dataset.tryGapChat || "";
      if (abletonQuestion) abletonQuestion.value = q;
      showTab("ableton");
      const details = document.querySelector(".ableton-quick-ask");
      if (details) details.open = true;
      if (q) askAbleton(q);
    });
  });
}

function renderLatestAudit(data) {
  const audit = data.latest_audit;
  if (!audit) return "<p class='compact-status'>No audit JSON yet. Run audit to create one.</p>";
  const benchmark = audit.benchmark || {};
  const index = audit.index || {};
  return `<dl class="audit-summary">
    <dt>Status</dt><dd>${escapeHtml(audit.status || "unknown")}</dd>
    <dt>Warnings</dt><dd>${escapeHtml((audit.warnings || []).join(", ") || "none")}</dd>
    <dt>Benchmark</dt><dd>${escapeHtml(String(benchmark.passed_runs ?? "—"))}/${escapeHtml(String(benchmark.total_runs ?? "—"))} passed · p95 ${escapeHtml(String(benchmark.duration_ms?.p95 ?? "—"))} ms</dd>
    <dt>Index</dt><dd>${escapeHtml(String(index.chunks ?? "—"))} chunks · ${escapeHtml(String(index.notes ?? "—"))} notes · ${escapeHtml(String(index.pdfs ?? "—"))} PDFs</dd>
    <dt>File</dt><dd>${escapeHtml(audit._path || "")}</dd>
  </dl>`;
}

function renderFeedbackRows(items) {
  if (!items?.length) return "<p class='compact-status'>No tester feedback yet.</p>";
  const rows = items.slice(0, 20).map((item) => {
    const repairStatus = item.repair_status || "open";
    const lowerStatus = String(repairStatus).toLowerCase();
    const canRetest = ["drafted", "needs_review"].includes(lowerStatus);
    const repairAction = canRetest
      ? `<button type="button" class="secondary" data-retest-feedback="${escapeHtml(item.id || "")}">Recheck repair</button>`
      : lowerStatus === "resolved"
        ? `<span class="status-pill ok">resolved</span>`
        : `<button type="button" class="secondary" data-agent-draft="1" data-source="feedback" data-source-id="${escapeHtml(item.id || "")}" data-question="${escapeHtml(item.question || "")}" data-topics="${escapeHtml(JSON.stringify(item.topics || []))}">Repair draft</button>`;
    const evalAction = String(item.rating || "") === "not_useful"
      ? `<button type="button" class="secondary" data-draft-feedback-eval="${escapeHtml(item.id || "")}">Draft eval</button>`
      : "";
    const action = `<div class="button-row compact">${repairAction}${evalAction}</div>`;
    const latest = item.repair_last_answer || item.answer || "";
    return `<tr>
    <td>${escapeHtml(item.rating || "")}</td>
    <td>${escapeHtml(item.channel || "")}</td>
    <td>${escapeHtml(item.question || "")}</td>
    <td>${escapeHtml(item.comment || "")}</td>
    <td>${escapeHtml(repairStatus)}${item.repair_note ? `<br><span class="compact-status">${escapeHtml(item.repair_note)}</span>` : ""}</td>
    <td>${escapeHtml(item.top_source || "")}</td>
    <td><span class="repair-preview inline">${escapeHtml(latest)}</span></td>
    <td>${escapeHtml(item.confidence || "")}</td>
    <td>${escapeHtml(item.created_at || "")}</td>
    <td>${action}</td>
  </tr>`;
  }).join("");
  return `<table><thead><tr><th>Rating</th><th>Channel</th><th>Question</th><th>Comment</th><th>Repair</th><th>Top source</th><th>Latest answer</th><th>Confidence</th><th>When</th><th>Action</th></tr></thead><tbody>${rows}</tbody></table>`;
}

function renderImproveQueries(items) {
  if (!items?.length) return "<p class='compact-status'>No logged questions yet.</p>";
  const rows = items.slice(0, 15).map((item) => `<tr>
    <td>${escapeHtml(item.question || "")}</td>
    <td>${escapeHtml(item.confidence || "")}</td>
    <td>${escapeHtml(item.top_source || "")}</td>
    <td>${escapeHtml(item.channel || "")}</td>
    <td><button type="button" class="secondary" data-draft-from-query="${escapeHtml(item.question || "")}">Draft note</button></td>
  </tr>`).join("");
  return `<table><thead><tr><th>Question</th><th>Confidence</th><th>Top source</th><th>Channel</th><th>Action</th></tr></thead><tbody>${rows}</tbody></table>`;
}

function renderQualityRows(items) {
  if (!items?.length) return "<p class='compact-status'>No answer self-check issues logged yet.</p>";
  const rows = items.slice(0, 20).map((item) => {
    const warnings = item.self_check_warnings || item.answer_self_check?.warnings || [];
    return `<tr>
      <td>${escapeHtml(item.question || "")}</td>
      <td>${escapeHtml(item.route || "")}<br><span class="compact-status">${escapeHtml(item.intent || "")}</span></td>
      <td>${escapeHtml(String(item.grounding_score ?? item.grounding?.score ?? ""))}</td>
      <td>${escapeHtml(warnings.join(", ") || "weak answer")}</td>
      <td>${escapeHtml(item.top_source || "")}</td>
      <td><div class="button-row compact">
        <button type="button" class="secondary" data-draft-from-query="${escapeHtml(item.question || "")}">Draft note</button>
        <button type="button" class="secondary" data-draft-query-eval="${escapeHtml(item.id || "")}">Draft eval</button>
      </div></td>
    </tr>`;
  }).join("");
  return `<table><thead><tr><th>Question</th><th>Route</th><th>Grounding</th><th>Warnings</th><th>Top source</th><th>Action</th></tr></thead><tbody>${rows}</tbody></table>`;
}

function wireDraftFromQuestion(root) {
  root?.querySelectorAll("[data-draft-from-query]").forEach((button) => {
    button.addEventListener("click", async () => {
      const question = button.dataset.draftFromQuery || "";
      if (!question) return;
      button.disabled = true;
      try {
        const result = await api("/api/ableton/gaps/create-note-from-question", {
          method: "POST",
          body: JSON.stringify({ question }),
        });
        statusEl.textContent = result.message || `Created ${result.note}`;
        showTab("transcripts");
        await loadTranscripts();
        if (result.note) await openNote(result.note, result.note.replace(/\.md$/, "").replace(/-/g, " "));
      } catch (error) {
        statusEl.textContent = error.message;
        button.disabled = false;
      }
    });
  });
  root?.querySelectorAll("[data-draft-query-eval]").forEach((button) => {
    button.addEventListener("click", async () => {
      const id = button.dataset.draftQueryEval || "";
      if (!id) return;
      button.disabled = true;
      try {
        const result = await api("/api/ableton/improvement/draft-query-eval", {
          method: "POST",
          body: JSON.stringify({ id }),
        });
        statusEl.textContent = result.message || "Draft eval saved.";
        await loadLmImprove();
      } catch (error) {
        statusEl.textContent = error.message;
        button.disabled = false;
      }
    });
  });
}

function trainingReviewSelect(field, current, yesLabel = "Correct", noLabel = "Wrong") {
  const value = current === true ? "true" : current === false ? "false" : "";
  return `<select data-review-field="${field}" aria-label="${field.replaceAll("_", " ")}">
    <option value=""${value === "" ? " selected" : ""}>Not reviewed</option>
    <option value="true"${value === "true" ? " selected" : ""}>${yesLabel}</option>
    <option value="false"${value === "false" ? " selected" : ""}>${noLabel}</option>
  </select>`;
}

function renderTrainingRecords(data = {}) {
  const summary = data.summary || {};
  const filter = document.querySelector("#training-records-filter")?.value || "all";
  const summaryEl = document.querySelector("#training-records-summary");
  const diagnosticsEl = document.querySelector("#training-records-diagnostics");
  if (summaryEl) {
    const path = data.path ? ` · ${data.path}` : "";
    summaryEl.textContent = data.message
      || `${summary.shown || 0}/${summary.total || 0} shown · ${summary.reviewed || 0} reviewed · ${summary.should_fallback || 0} should fallback${path}`;
  }
  if (diagnosticsEl) diagnosticsEl.textContent = renderTrainingDiagnostics(data.diagnostics || {});
  const items = (data.items || []).filter((item) => trainingRecordMatchesFilter(item, filter));
  if (!items.length) return "<p class='compact-status'>No training records yet. Run benchmark or export training first.</p>";
  const rows = items.map((item) => {
    const review = item.review || {};
    const priority = item.review_priority || {};
    const reasons = (priority.reasons || []).join(", ");
    const source = item.top_source_label || item.top_source || "No source";
    const failed = (item.eval_failures || []).join(", ");
    return `<tr data-training-row="${escapeHtml(item.id || item.case_id || "")}">
      <td>
        <strong>${escapeHtml(item.question || "")}</strong>
        <span class="compact-status">${escapeHtml(item.case_id || item.id || "")}</span>
        ${reasons ? `<span class="training-priority">${escapeHtml(reasons)}</span>` : ""}
      </td>
      <td>
        <span>${escapeHtml(item.route || "unknown")}</span><br>
        <span class="compact-status">${escapeHtml(item.intent || "unknown")}</span>
      </td>
      <td>
        <span>${escapeHtml(source)}</span><br>
        <span class="compact-status">${escapeHtml(item.top_source_kind || "")} · ${escapeHtml(item.confidence || "")}/${escapeHtml(item.source_quality || "")}</span>
      </td>
      <td>
        <span class="status-pill ${item.eval_passed ? "ok" : "warn"}">${item.eval_passed ? "Eval pass" : "Eval fail"}</span>
        ${failed ? `<br><span class="compact-status">${escapeHtml(failed)}</span>` : ""}
      </td>
      <td>
        <div class="training-review-controls">
          ${trainingReviewSelect("route_correct", review.route_correct, "Route ok", "Route wrong")}
          ${trainingReviewSelect("intent_correct", review.intent_correct, "Intent ok", "Intent wrong")}
          ${trainingReviewSelect("top_source_correct", review.top_source_correct, "Source ok", "Source wrong")}
          <select data-review-field="answer_policy" aria-label="answer policy">
            <option value=""${!review.answer_policy ? " selected" : ""}>Policy?</option>
            <option value="should_answer"${review.answer_policy === "should_answer" ? " selected" : ""}>Should answer</option>
            <option value="should_fallback"${review.answer_policy === "should_fallback" ? " selected" : ""}>Should fallback</option>
            <option value="unsure"${review.answer_policy === "unsure" ? " selected" : ""}>Unsure</option>
          </select>
          <input data-review-field="notes" type="text" value="${escapeHtml(review.notes || "")}" placeholder="Review note">
          <button type="button" class="secondary" data-save-training-review="${escapeHtml(item.id || item.case_id || "")}">Save</button>
        </div>
      </td>
    </tr>`;
  }).join("");
  return `<table><thead><tr><th>Question</th><th>Route</th><th>Top source</th><th>Eval</th><th>Review</th></tr></thead><tbody>${rows}</tbody></table>`;
}

function renderTrainingDiagnostics(diagnostics = {}) {
  const issueTopics = (diagnostics.issue_topics || []).slice(0, 3).map((item) => `${item.label} (${item.count})`).join(", ");
  const issueSources = (diagnostics.issue_sources || []).slice(0, 2).map((item) => `${item.label} (${item.count})`).join(", ");
  const routeConfusion = (diagnostics.route_confusion || []).slice(0, 2).map((item) => `${item.label} (${item.count})`).join(", ");
  const parts = [`${diagnostics.issue_count || 0} issue signals`];
  if (routeConfusion) parts.push(`routes: ${routeConfusion}`);
  if (issueTopics) parts.push(`topics: ${issueTopics}`);
  if (issueSources) parts.push(`sources: ${issueSources}`);
  return parts.join(" · ");
}

function trainingRecordMatchesFilter(item, filter) {
  const review = item.review || {};
  const priority = item.review_priority || {};
  if (filter === "needs_review") return Boolean(priority.needs_review);
  if (filter === "fallback") return review.answer_policy === "should_fallback";
  if (filter === "wrong_source") return review.top_source_correct === false;
  if (filter === "wrong_route") return review.route_correct === false;
  if (filter === "wrong_intent") return review.intent_correct === false;
  if (filter === "weak_match") return item.weak_match === true || String(item.source_quality || "").toLowerCase() === "low";
  if (filter === "eval_failed") return item.eval_passed === false;
  return true;
}

function refreshTrainingRecordsView() {
  const table = document.querySelector("#training-records-table");
  if (!table || !trainingRecordsData) return;
  table.innerHTML = renderTrainingRecords(trainingRecordsData);
  wireTrainingRecords(table);
}

function trainingFieldValue(input) {
  if (input.tagName === "SELECT" && ["route_correct", "intent_correct", "top_source_correct"].includes(input.dataset.reviewField)) {
    if (input.value === "true") return true;
    if (input.value === "false") return false;
    return "";
  }
  return input.value;
}

function wireTrainingRecords(root) {
  root?.querySelectorAll("[data-save-training-review]").forEach((button) => {
    button.addEventListener("click", async () => {
      const row = button.closest("[data-training-row]");
      if (!row) return;
      const payload = { id: button.dataset.saveTrainingReview || row.dataset.trainingRow || "" };
      row.querySelectorAll("[data-review-field]").forEach((input) => {
        payload[input.dataset.reviewField] = trainingFieldValue(input);
      });
      button.disabled = true;
      try {
        const result = await api("/api/ableton/training-review", {
          method: "POST",
          body: JSON.stringify(payload),
        });
        statusEl.textContent = `Training review saved: ${result.id}`;
        await loadTrainingRecords();
      } catch (error) {
        statusEl.textContent = error.message;
        button.disabled = false;
      }
    });
  });
}

async function loadTrainingRecords() {
  const table = document.querySelector("#training-records-table");
  if (!table) return;
  table.innerHTML = "<p class='compact-status'>Loading training records…</p>";
  try {
    const data = await api("/api/ableton/training-records?limit=80");
    trainingRecordsData = data;
    refreshTrainingRecordsView();
  } catch (error) {
    table.innerHTML = `<p class='compact-status'>${escapeHtml(error.message)}</p>`;
  }
}

async function exportReviewedTraining() {
  const status = document.querySelector("#lm-improve-status");
  if (status) status.textContent = "Exporting reviewed training records…";
  try {
    const data = await api("/api/ableton/training-export", { method: "POST", body: JSON.stringify({}) });
    if (status) status.textContent = `Exported ${data.count} reviewed records to ${data.path}.`;
    await loadTrainingRecords();
  } catch (error) {
    if (status) status.textContent = error.message;
  }
}

async function exportHardNegatives() {
  const status = document.querySelector("#lm-improve-status");
  if (status) status.textContent = "Exporting hard negatives…";
  try {
    const data = await api("/api/ableton/hard-negatives-export", { method: "POST", body: JSON.stringify({}) });
    if (status) status.textContent = `Exported ${data.count} hard negatives to ${data.path}.`;
    await loadTrainingRecords();
  } catch (error) {
    if (status) status.textContent = error.message;
  }
}

async function exportRouteMemory() {
  const status = document.querySelector("#lm-improve-status");
  if (status) status.textContent = "Exporting route memory…";
  try {
    const data = await api("/api/ableton/route-memory-export", { method: "POST", body: JSON.stringify({}) });
    if (status) status.textContent = `Exported ${data.count} route memory records to ${data.path}.`;
    await loadTrainingRecords();
  } catch (error) {
    if (status) status.textContent = error.message;
  }
}

async function loadLmImprove() {
  const status = document.querySelector("#lm-improve-status");
  const scorecards = document.querySelector("#lm-improve-scorecards");
  const latestAudit = document.querySelector("#lm-latest-audit");
  const feedbackTable = document.querySelector("#lm-feedback-table");
  const qualityTable = document.querySelector("#lm-quality-table");
  const queriesTable = document.querySelector("#lm-improve-queries");
  const agentQueue = document.querySelector("#lm-agent-queue");
  const repairPlan = document.querySelector("#lm-repair-plan");
  if (!scorecards) return;
  if (status) status.textContent = "Loading LLM improvement status…";
  try {
    const data = await api("/api/ableton/improvement");
    scorecards.innerHTML = renderLmScorecards(data);
    if (repairPlan) repairPlan.innerHTML = renderRepairPlan(data.repair_plan || {});
    if (agentQueue) {
      agentQueue.innerHTML = renderAgentQueue(data.agent_queue || {});
      wireAgentQueue(agentQueue);
    }
    if (latestAudit) latestAudit.innerHTML = renderLatestAudit(data);
    if (feedbackTable) {
      feedbackTable.innerHTML = renderFeedbackRows(data.feedback?.items || []);
      wireAgentQueue(feedbackTable);
    }
    if (qualityTable) {
      qualityTable.innerHTML = renderQualityRows(data.answer_quality_queue?.items || []);
      wireDraftFromQuestion(qualityTable);
    }
    if (queriesTable) {
      queriesTable.innerHTML = renderImproveQueries(data.recent_queries || []);
      wireDraftFromQuestion(queriesTable);
    }
    await loadTrainingRecords();
    if (status) status.textContent = "LLM improvement status loaded.";
  } catch (error) {
    if (status) status.textContent = error.message;
  }
}

async function runLmImprove(kind) {
  const output = document.querySelector("#lm-improve-output");
  const status = document.querySelector("#lm-improve-status");
  if (output) output.textContent = `Running ${kind}…`;
  if (status) status.textContent = `Running ${kind}…`;
  try {
    const data = await api("/api/ableton/improvement/run", {
      method: "POST",
      body: JSON.stringify({ kind }),
    });
    if (output) output.textContent = data.output || `${kind} complete.`;
    if (status) status.textContent = data.ok ? `${kind} complete.` : `${kind} failed.`;
    await loadLmImprove();
  } catch (error) {
    if (output) output.textContent = error.message;
    if (status) status.textContent = error.message;
  }
}

document.querySelector("#lm-improve-refresh")?.addEventListener("click", loadLmImprove);
document.querySelector("#lm-run-audit")?.addEventListener("click", () => runLmImprove("audit"));
document.querySelector("#lm-run-bench")?.addEventListener("click", () => runLmImprove("bench"));
document.querySelector("#lm-run-eval")?.addEventListener("click", () => runLmImprove("eval"));
document.querySelector("#lm-run-export-training")?.addEventListener("click", () => runLmImprove("export-training"));
document.querySelector("#training-records-refresh")?.addEventListener("click", loadTrainingRecords);
document.querySelector("#training-records-export")?.addEventListener("click", exportReviewedTraining);
document.querySelector("#training-hard-negatives-export")?.addEventListener("click", exportHardNegatives);
document.querySelector("#training-route-memory-export")?.addEventListener("click", exportRouteMemory);
document.querySelector("#training-records-filter")?.addEventListener("change", refreshTrainingRecordsView);

const knowledgeSearch = document.querySelector("#knowledge-search");
const knowledgeStatusFilter = document.querySelector("#knowledge-status-filter");
const knowledgeSummary = document.querySelector("#knowledge-summary");
const knowledgeNoteList = document.querySelector("#knowledge-note-list");
const knowledgeTitle = document.querySelector("#knowledge-editor-title");
const knowledgeMeta = document.querySelector("#knowledge-note-meta");
const knowledgeContent = document.querySelector("#knowledge-content");
const knowledgeSave = document.querySelector("#knowledge-save");
const knowledgeApprove = document.querySelector("#knowledge-approve");
const knowledgeRebuild = document.querySelector("#knowledge-rebuild");
const knowledgeRunEval = document.querySelector("#knowledge-run-eval");
const knowledgeOutput = document.querySelector("#knowledge-output");
const knowledgeFeedback = document.querySelector("#knowledge-feedback");
const knowledgeSuggestedNotes = document.querySelector("#knowledge-suggested-notes");
const knowledgeRunClustering = document.querySelector("#knowledge-run-clustering");
let selectedSuggestedNoteId = null;
let knowledgeSearchTimer = null;

function renderKnowledgeNotes(items = []) {
  if (!items.length) return "<p class='compact-status'>No notes match the current filter.</p>";
  return items.map((item) => {
    const active = item.name === selectedKnowledgeNote ? " active" : "";
    return `<button type="button" class="knowledge-note-item${active}" data-knowledge-note="${escapeHtml(item.name)}">
      <strong>${escapeHtml(item.title || item.name)}</strong>
      <span>${escapeHtml(item.name)}</span>
      <small>${escapeHtml(item.status || "Unmarked")} · ${escapeHtml(item.updated_at || "")}</small>
      ${item.tags ? `<em>${escapeHtml(item.tags)}</em>` : ""}
    </button>`;
  }).join("");
}

function wireKnowledgeNotes(root) {
  root?.querySelectorAll("[data-knowledge-note]").forEach((button) => {
    button.addEventListener("click", () => openKnowledgeNote(button.dataset.knowledgeNote || ""));
  });
}

function renderSuggestedNotes(items = []) {
  if (!items.length) return "<p class='compact-status'>No pending suggested notes. Run clustering to generate suggestions.</p>";
  const rows = items.map((item) => {
    const queryList = (item.source_cluster_queries || []).map(q => `• ${escapeHtml(q)}`).join("<br>");
    return `<tr>
      <td><strong>${escapeHtml(item.title || "Untitled Suggested Note")}</strong></td>
      <td class="compact-status" style="max-height: 80px; overflow-y: auto; text-align: left;">${queryList}</td>
      <td>${escapeHtml(item.created_at || "")}</td>
      <td>
        <div class="button-row compact">
          <button type="button" class="secondary" data-suggested-review="${escapeHtml(item.id)}">Review</button>
          <button type="button" class="secondary" data-suggested-approve="${escapeHtml(item.id)}">Approve</button>
          <button type="button" class="secondary" data-suggested-dismiss="${escapeHtml(item.id)}">Dismiss</button>
        </div>
      </td>
    </tr>`;
  }).join("");
  return `<table><thead><tr><th>Draft Title</th><th>Cluster Queries</th><th>Created At</th><th>Action</th></tr></thead><tbody>${rows}</tbody></table>`;
}

function wireSuggestedNotes(root) {
  root?.querySelectorAll("[data-suggested-review]").forEach((button) => {
    button.addEventListener("click", () => openSuggestedNote(button.dataset.suggestedReview || ""));
  });
  root?.querySelectorAll("[data-suggested-approve]").forEach((button) => {
    button.addEventListener("click", async () => {
      selectedSuggestedNoteId = button.dataset.suggestedApprove;
      await approveKnowledgeNote();
    });
  });
  root?.querySelectorAll("[data-suggested-dismiss]").forEach((button) => {
    button.addEventListener("click", () => dismissSuggestedNote(button.dataset.suggestedDismiss || ""));
  });
}

function renderKnowledgeFeedback(items = []) {
  const needsWork = items
    .filter((item) => item.rating === "not_useful" && String(item.repair_status || "open").toLowerCase() !== "resolved")
    .slice(0, 12);
  if (!needsWork.length) return "<p class='compact-status'>No unresolved needs-work feedback right now.</p>";
  const rows = needsWork.map((item) => {
    const repairStatus = String(item.repair_status || "open").toLowerCase();
    const noteAction = item.repair_note
      ? `<button type="button" class="secondary" data-knowledge-open-note="${escapeHtml(item.repair_note)}">${escapeHtml(item.repair_note)}</button>`
      : `<button type="button" class="secondary" data-agent-draft="1" data-source="feedback" data-source-id="${escapeHtml(item.id || "")}" data-question="${escapeHtml(item.question || "")}" data-topics="${escapeHtml(JSON.stringify(item.topics || []))}">Create repair note</button>`;
    const canRetest = ["drafted", "needs_review"].includes(repairStatus);
    const retest = canRetest ? `<button type="button" class="secondary" data-knowledge-retest-feedback="${escapeHtml(item.id || "")}">Retest</button>` : "";
    const lastAnswer = item.repair_last_answer ? `<span class="repair-preview inline">${escapeHtml(item.repair_last_answer)}</span>` : "";
    return `<tr>
      <td>${escapeHtml(item.question || "")}</td>
      <td>${escapeHtml(item.comment || "")}</td>
      <td>${escapeHtml(item.channel || "")}</td>
      <td>${escapeHtml(item.repair_status || "open")}${item.repair_note ? `<br><span class="compact-status">${escapeHtml(item.repair_note)}</span>` : ""}${lastAnswer}</td>
      <td><div class="button-row compact">${noteAction}${retest}<button type="button" class="secondary" data-knowledge-draft-eval="${escapeHtml(item.id || "")}">Draft eval</button><button type="button" class="secondary" data-knowledge-mark-resolved="${escapeHtml(item.id || "")}">Mark resolved</button></div></td>
    </tr>`;
  }).join("");
  return `<table><thead><tr><th>Question</th><th>Comment</th><th>Channel</th><th>Repair</th><th>Action</th></tr></thead><tbody>${rows}</tbody></table>`;
}

function wireKnowledgeFeedback(root) {
  root?.querySelectorAll("[data-knowledge-open-note]").forEach((button) => {
    button.addEventListener("click", () => openKnowledgeNote(button.dataset.knowledgeOpenNote || ""));
  });
  root?.querySelectorAll("[data-knowledge-retest-feedback]").forEach((button) => {
    button.addEventListener("click", async () => {
      button.disabled = true;
      try {
        const result = await api("/api/ableton/improvement/retest-feedback", {
          method: "POST",
          body: JSON.stringify({ id: button.dataset.knowledgeRetestFeedback || "" }),
        });
        statusEl.textContent = result.resolved
          ? `Repair resolved: ${result.confidence} confidence, ${result.source_quality} sources.`
          : `Repair still needs review: ${result.failed_checks?.join(", ") || "validation failed"}.`;
        await loadKnowledgeAdmin();
      } catch (error) {
        statusEl.textContent = error.message;
        button.disabled = false;
      }
    });
  });
  root?.querySelectorAll("[data-knowledge-draft-eval]").forEach((button) => {
    button.addEventListener("click", async () => {
      button.disabled = true;
      try {
        const result = await api("/api/ableton/improvement/draft-eval", {
          method: "POST",
          body: JSON.stringify({ id: button.dataset.knowledgeDraftEval || "" }),
        });
        statusEl.textContent = result.message || "Draft eval saved.";
        await loadKnowledgeAdmin();
      } catch (error) {
        statusEl.textContent = error.message;
        button.disabled = false;
      }
    });
  });
  root?.querySelectorAll("[data-knowledge-mark-resolved]").forEach((button) => {
    button.addEventListener("click", async () => {
      button.disabled = true;
      try {
        await api("/api/ableton/improvement/mark-feedback-resolved", {
          method: "POST",
          body: JSON.stringify({ id: button.dataset.knowledgeMarkResolved || "" }),
        });
        statusEl.textContent = "Feedback marked resolved.";
        await loadKnowledgeAdmin();
      } catch (error) {
        statusEl.textContent = error.message;
        button.disabled = false;
      }
    });
  });
  wireAgentQueue(root);
}

async function loadKnowledgeAdmin() {
  if (!knowledgeNoteList) return;
  const params = new URLSearchParams({
    status: knowledgeStatusFilter?.value || "all",
    q: knowledgeSearch?.value || "",
    limit: "500",
  });
  knowledgeNoteList.innerHTML = "<p class='compact-status'>Loading notes…</p>";
  try {
    const [notes, improve, suggested] = await Promise.all([
      api(`/api/ableton/notes?${params}`),
      knowledgeFeedback ? api("/api/ableton/improvement") : Promise.resolve({ feedback: { items: [] } }),
      knowledgeSuggestedNotes ? api("/api/ableton/suggested-notes") : Promise.resolve({ items: [] }),
    ]);
    const items = notes.items || [];
    const draftCount = items.filter((item) => String(item.status || "").toLowerCase() === "draft").length;
    const approvedCount = items.filter((item) => String(item.status || "").toLowerCase() === "approved").length;
    if (knowledgeSummary) knowledgeSummary.textContent = `${items.length} note(s) · ${draftCount} draft · ${approvedCount} approved`;
    knowledgeNoteList.innerHTML = renderKnowledgeNotes(items);
    wireKnowledgeNotes(knowledgeNoteList);
    if (knowledgeFeedback) {
      knowledgeFeedback.innerHTML = renderKnowledgeFeedback(improve.feedback?.items || []);
      wireKnowledgeFeedback(knowledgeFeedback);
    }
    if (knowledgeSuggestedNotes) {
      knowledgeSuggestedNotes.innerHTML = renderSuggestedNotes(suggested.items || []);
      wireSuggestedNotes(knowledgeSuggestedNotes);
    }
  } catch (error) {
    knowledgeNoteList.innerHTML = `<p class='compact-status'>${escapeHtml(error.message)}</p>`;
  }
}

async function openKnowledgeNote(name) {
  if (!name) return;
  selectedKnowledgeNote = name;
  selectedSuggestedNoteId = null;
  if (knowledgeContent) knowledgeContent.disabled = false;
  if (knowledgeSave) knowledgeSave.disabled = false;
  if (knowledgeApprove) knowledgeApprove.disabled = false;
  if (knowledgeTitle) knowledgeTitle.textContent = name;
  try {
    const data = await api(`/api/ableton/note?name=${encodeURIComponent(name)}`);
    if (knowledgeContent) knowledgeContent.value = data.content || "";
    if (knowledgeMeta) {
      knowledgeMeta.innerHTML = `<span class="status-pill">${escapeHtml(data.status || "Unmarked")}</span><span class="status-pill">${escapeHtml(data.name || name)}</span>`;
    }
    statusEl.textContent = `Editing ${data.name} (${data.status})`;
    await loadKnowledgeAdmin();
  } catch (error) {
    statusEl.textContent = error.message;
  }
}

async function openSuggestedNote(id) {
  if (!id) return;
  selectedSuggestedNoteId = id;
  selectedKnowledgeNote = null;
  if (knowledgeContent) knowledgeContent.disabled = false;
  if (knowledgeSave) knowledgeSave.disabled = false;
  if (knowledgeApprove) knowledgeApprove.disabled = false;
  try {
    const data = await api("/api/ableton/suggested-notes");
    const item = (data.items || []).find(n => n.id === id);
    if (!item) {
      statusEl.textContent = "Suggested note not found.";
      return;
    }
    if (knowledgeContent) knowledgeContent.value = item.content || "";
    if (knowledgeTitle) knowledgeTitle.textContent = `Suggested Note: ${item.title}`;
    if (knowledgeMeta) {
      knowledgeMeta.innerHTML = `<span class="status-pill warning">Suggested Draft</span><span class="status-pill">${escapeHtml(item.id)}</span>`;
    }
    statusEl.textContent = `Reviewing suggested draft: ${item.title}`;
  } catch (error) {
    statusEl.textContent = error.message;
  }
}

async function dismissSuggestedNote(id) {
  if (!confirm("Are you sure you want to dismiss this suggested note draft?")) return;
  try {
    await api("/api/ableton/suggested-notes/dismiss", {
      method: "POST",
      body: JSON.stringify({ id }),
    });
    statusEl.textContent = `Dismissed suggested note draft ${id}`;
    if (selectedSuggestedNoteId === id) {
      selectedSuggestedNoteId = null;
      if (knowledgeContent) {
        knowledgeContent.value = "";
        knowledgeContent.disabled = true;
      }
      if (knowledgeSave) knowledgeSave.disabled = true;
      if (knowledgeApprove) knowledgeApprove.disabled = true;
      if (knowledgeTitle) knowledgeTitle.textContent = "Select a note";
      if (knowledgeMeta) knowledgeMeta.innerHTML = "";
    }
    await loadKnowledgeAdmin();
  } catch (error) {
    statusEl.textContent = error.message;
  }
}

async function runGapClustering() {
  if (knowledgeOutput) knowledgeOutput.textContent = "Running gap clustering & synthesis...";
  try {
    const data = await api("/api/ableton/suggested-notes/cluster", { method: "POST", body: "{}" });
    if (knowledgeOutput) {
      knowledgeOutput.textContent = data.message || "Clustering complete.";
    }
    statusEl.textContent = data.ok ? "Gap clustering completed." : "Clustering failed.";
    await loadKnowledgeAdmin();
  } catch (error) {
    if (knowledgeOutput) knowledgeOutput.textContent = error.message;
  }
}

async function saveKnowledgeNote() {
  if (selectedSuggestedNoteId) {
    try {
      const titleLine = knowledgeContent.value.split("\n")[0] || "";
      const title = titleLine.startsWith("#") ? titleLine.replace(/^#\s*/, "").trim() : "Untitled Suggested Note";
      await api("/api/ableton/suggested-notes/save", {
        method: "POST",
        body: JSON.stringify({ id: selectedSuggestedNoteId, title: title, content: knowledgeContent.value }),
      });
      statusEl.textContent = `Saved edits to suggested note ${selectedSuggestedNoteId}`;
      await loadKnowledgeAdmin();
    } catch (error) {
      statusEl.textContent = error.message;
    }
    return;
  }
  if (!selectedKnowledgeNote || !knowledgeContent) return;
  try {
    await api("/api/ableton/note", {
      method: "POST",
      body: JSON.stringify({ name: selectedKnowledgeNote, content: knowledgeContent.value }),
    });
    statusEl.textContent = `Saved ${selectedKnowledgeNote}`;
    await loadKnowledgeAdmin();
    await loadActivity();
  } catch (error) {
    statusEl.textContent = error.message;
  }
}

async function approveKnowledgeNote() {
  if (selectedSuggestedNoteId) {
    try {
      const data = await api("/api/ableton/suggested-notes/approve", {
        method: "POST",
        body: JSON.stringify({ id: selectedSuggestedNoteId }),
      });
      statusEl.textContent = `Approved suggested note and created ${data.note}. Linked ${data.gaps_linked} gap(s).`;
      selectedSuggestedNoteId = null;
      if (knowledgeContent) {
        knowledgeContent.value = "";
        knowledgeContent.disabled = true;
      }
      if (knowledgeSave) knowledgeSave.disabled = true;
      if (knowledgeApprove) knowledgeApprove.disabled = true;
      if (knowledgeTitle) knowledgeTitle.textContent = "Select a note";
      if (knowledgeMeta) knowledgeMeta.innerHTML = "";
      await loadKnowledgeAdmin();
      await loadActivity();
    } catch (error) {
      statusEl.textContent = error.message;
    }
    return;
  }
  if (!selectedKnowledgeNote) return;
  try {
    await api("/api/ableton/approve", {
      method: "POST",
      body: JSON.stringify({ name: selectedKnowledgeNote }),
    });
    statusEl.textContent = `Approved ${selectedKnowledgeNote}. Rebuild the index when ready.`;
    await openKnowledgeNote(selectedKnowledgeNote);
    await loadActivity();
  } catch (error) {
    statusEl.textContent = error.message;
  }
}

async function rebuildKnowledgeIndex() {
  if (knowledgeOutput) knowledgeOutput.textContent = "Building index…";
  try {
    const data = await api("/api/ableton/build", { method: "POST", body: "{}" });
    if (knowledgeOutput) knowledgeOutput.textContent = data.output || (data.ok ? "Done." : "Build failed.");
    statusEl.textContent = data.ok ? "Index rebuilt." : "Index build failed.";
    await loadActivity();
  } catch (error) {
    if (knowledgeOutput) knowledgeOutput.textContent = error.message;
  }
}

async function runKnowledgeEval() {
  if (knowledgeOutput) knowledgeOutput.textContent = "Running evals…";
  try {
    const data = await api("/api/ableton/improvement/run", {
      method: "POST",
      body: JSON.stringify({ kind: "eval" }),
    });
    if (knowledgeOutput) knowledgeOutput.textContent = data.output || "Eval complete.";
    statusEl.textContent = data.ok ? "Eval complete." : "Eval failed.";
  } catch (error) {
    if (knowledgeOutput) knowledgeOutput.textContent = error.message;
  }
}

knowledgeSearch?.addEventListener("input", () => {
  clearTimeout(knowledgeSearchTimer);
  knowledgeSearchTimer = setTimeout(loadKnowledgeAdmin, 180);
});
knowledgeStatusFilter?.addEventListener("change", loadKnowledgeAdmin);
document.querySelector("#knowledge-refresh")?.addEventListener("click", loadKnowledgeAdmin);
knowledgeSave?.addEventListener("click", saveKnowledgeNote);
knowledgeApprove?.addEventListener("click", approveKnowledgeNote);
knowledgeRebuild?.addEventListener("click", rebuildKnowledgeIndex);
knowledgeRunEval?.addEventListener("click", runKnowledgeEval);
knowledgeRunClustering?.addEventListener("click", runGapClustering);

async function loadStems() {
  const table = document.querySelector("#stems-table");
  if (!table) return;
  table.innerHTML = "<p class='compact-status'>Loading…</p>";
  try {
    const data = await api("/api/admin/stem-uploads");
    const items = data.items || [];
    if (!items.length) {
      table.innerHTML = "<p class='compact-status'>No uploads yet. Copy an upload link from Projects.</p>";
      return;
    }
    const rows = items
      .map((item) => {
        const mb = (Number(item.size_bytes || 0) / (1024 * 1024)).toFixed(1);
        return `<tr>
          <td>${escapeHtml(item.created_at || "")}</td>
          <td>${escapeHtml(item.project_label || item.project_id || "")}</td>
          <td>${escapeHtml(item.original_name || "")}</td>
          <td>${escapeHtml(mb)} MB</td>
          <td>${escapeHtml(item.uploader_name || "")}</td>
          <td>${escapeHtml(item.uploader_email || "")}</td>
        </tr>`;
      })
      .join("");
    table.innerHTML = `<table><thead><tr><th>When</th><th>Project</th><th>File</th><th>Size</th><th>Name</th><th>Email</th></tr></thead><tbody>${rows}</tbody></table>`;
  } catch (error) {
    table.innerHTML = `<p class='compact-status'>${escapeHtml(error.message)}</p>`;
  }
}

document.querySelector("#stems-refresh")?.addEventListener("click", loadStems);

function renderPortfolioCandidates(items = []) {
  if (!items.length) return "<p class='compact-status'>No delivered/completed project candidates yet.</p>";
  return `<div class="ops-list">${items.map((item) => `
    <article class="ops-item">
      <div>
        <strong>${escapeHtml(item.entry?.title || item.project || "Project")}</strong>
        <p>${escapeHtml(item.entry?.description || "")}</p>
        <p class="compact-status">Public tags: ${escapeHtml((item.entry?.tags || []).join(", "))}</p>
        <p class="compact-status">Private fields excluded: ${escapeHtml((item.private_fields_excluded || []).join(", "))}</p>
      </div>
      <div class="gap-actions">
        <span class="status-pill">${escapeHtml(item.status || "candidate")}</span>
        <button type="button" data-publish-project="${escapeHtml(item.id || "")}">Publish entry</button>
      </div>
    </article>
  `).join("")}</div>`;
}

function renderPortfolioAudio(files = []) {
  if (!files.length) return "<p class='compact-status'>No audio files found. Add WAV files to Portfolio/audio/.</p>";
  return `<div class="ops-list">${files.map((file) => `
    <article class="ops-item">
      <div>
        <strong>${escapeHtml(file.title || file.filename)}</strong>
        <p>${escapeHtml(file.filename)} · ${escapeHtml(file.size_mb)} MB</p>
        <p class="compact-status">${escapeHtml(file.src || "")}</p>
      </div>
      <div class="gap-actions">
        <span class="status-pill ${file.published ? "ok" : ""}">${file.published ? "published" : "not published"}</span>
        ${file.published ? "" : `<button type="button" data-publish-audio="${escapeHtml(file.filename || "")}">Publish audio</button>`}
      </div>
    </article>
  `).join("")}</div>`;
}

function wirePortfolioOps(root) {
  root?.querySelectorAll("[data-publish-project]").forEach((button) => {
    button.addEventListener("click", async () => {
      button.disabled = true;
      try {
        const result = await api("/api/admin/portfolio/publish-project", {
          method: "POST",
          body: JSON.stringify({ id: button.dataset.publishProject }),
        });
        statusEl.textContent = result.message || "Portfolio entry published.";
        await loadPortfolioOps();
      } catch (error) {
        statusEl.textContent = error.message;
        button.disabled = false;
      }
    });
  });
  root?.querySelectorAll("[data-publish-audio]").forEach((button) => {
    button.addEventListener("click", async () => {
      button.disabled = true;
      try {
        const filename = button.dataset.publishAudio || "";
        const result = await api("/api/admin/portfolio/publish-audio", {
          method: "POST",
          body: JSON.stringify({ filename }),
        });
        statusEl.textContent = result.message || "Audio entry published.";
        await loadPortfolioOps();
      } catch (error) {
        statusEl.textContent = error.message;
        button.disabled = false;
      }
    });
  });
}

async function loadPortfolioOps() {
  const summaryEl = document.querySelector("#portfolio-ops-summary");
  const candidatesEl = document.querySelector("#portfolio-candidates");
  const audioEl = document.querySelector("#portfolio-audio-files");
  if (!candidatesEl || !audioEl) return;
  candidatesEl.innerHTML = "<p class='compact-status'>Loading…</p>";
  audioEl.innerHTML = "";
  try {
    const data = await api("/api/admin/portfolio-ops");
    const summary = data.summary || {};
    if (summaryEl) {
      summaryEl.innerHTML = `
        <span class="status-pill">${escapeHtml(summary.candidate_projects ?? 0)} project candidate(s)</span>
        <span class="status-pill">${escapeHtml(summary.audio_files ?? 0)} audio file(s)</span>
        <span class="status-pill ${summary.unpublished_audio ? "warn" : "ok"}">${escapeHtml(summary.unpublished_audio ?? 0)} unpublished audio</span>
      `;
    }
    candidatesEl.innerHTML = renderPortfolioCandidates(data.candidates || []);
    audioEl.innerHTML = renderPortfolioAudio(data.audio_files || []);
    wirePortfolioOps(candidatesEl);
    wirePortfolioOps(audioEl);
  } catch (error) {
    candidatesEl.innerHTML = `<p class='compact-status'>${escapeHtml(error.message)}</p>`;
  }
}

document.querySelector("#portfolio-ops-refresh")?.addEventListener("click", loadPortfolioOps);

const audioGenStatus = document.querySelector("#audiogen-status");
const audioGenForm = document.querySelector("#audiogen-form");
const audioGenPrompt = document.querySelector("#audiogen-prompt");
const audioGenEmotion = document.querySelector("#audiogen-emotion");
const audioGenBars = document.querySelector("#audiogen-bars");
const audioGenProject = document.querySelector("#audiogen-project");
const audioGenResult = document.querySelector("#audiogen-result");
const audioGenSongButton = document.querySelector("#audiogen-render-song");
const audioGenChainAutomix = document.querySelector("#audiogen-chain-automix");
const audioGenEmotionButtons = Array.from(document.querySelectorAll("[data-audiogen-emotion]"));
const audioGenPlayerPanel = document.querySelector("#audiogen-player-panel");
const audioGenPlayer = document.querySelector("#audiogen-player");
const audioGenPlay = document.querySelector("#audiogen-play");
const audioGenPause = document.querySelector("#audiogen-pause");
const audioGenStop = document.querySelector("#audiogen-stop");
const audioGenJobs = document.querySelector("#audiogen-jobs");
const audioGenJobsRefresh = document.querySelector("#audiogen-jobs-refresh");
const audioGenHistory = document.querySelector("#audiogen-history");
const audioGenHistoryRefresh = document.querySelector("#audiogen-history-refresh");
let audioGenQueueTimer = null;
let audioGenActiveJobId = "";

function renderAudioGenStatus(data = {}) {
  const audit = data.latest_audit?.updated_at || "No audit yet";
  return `
    <span class="status-pill ${data.ok ? "ok" : "warn"}">${data.ok ? "Ready" : "Not detected"}</span>
    <span class="status-pill">${escapeHtml(data.portfolio_audio_count ?? 0)} portfolio audio file(s)</span>
    <span class="status-pill">Audit: ${escapeHtml(audit)}</span>
  `;
}

async function loadAudioGenStatus() {
  if (!audioGenStatus) return;
  audioGenStatus.innerHTML = "<span class='status-pill'>Checking…</span>";
  try {
    const data = await api("/api/audiogen/status");
    audioGenStatus.innerHTML = renderAudioGenStatus(data);
    const recentJobs = data.render_queue?.recent || [];
    renderAudioGenJobs(recentJobs);
    if (recentJobs.some((job) => job.status === "queued" || job.status === "running")) {
      await loadAudioGenJobs();
    }
    await loadAudioGenHistory();
  } catch (error) {
    audioGenStatus.innerHTML = `<span class="status-pill warn">${escapeHtml(error.message)}</span>`;
  }
}

function selectedAudioGenEmotion() {
  return audioGenEmotion?.value || "joy";
}

function selectedAudioGenProject() {
  return audioGenProject?.value || "";
}

function populateAudioGenProjects(projects = []) {
  if (!audioGenProject) return;
  const selected = selectedAudioGenProject();
  const options = ['<option value="">No project</option>'];
  projects.forEach((project) => {
    const id = project.id || "";
    if (!id) return;
    const label = [project.project, project.client].filter(Boolean).join(" · ") || id;
    options.push(`<option value="${escapeHtml(id)}">${escapeHtml(label)}</option>`);
  });
  audioGenProject.innerHTML = options.join("");
  if (selected && projects.some((project) => project.id === selected)) {
    audioGenProject.value = selected;
  }
}

function setAudioGenEmotion(emotion) {
  if (audioGenEmotion) audioGenEmotion.value = emotion || "joy";
  audioGenEmotionButtons.forEach((button) => {
    button.classList.toggle("active", button.dataset.audiogenEmotion === selectedAudioGenEmotion());
  });
}

function audioGenSourceFromResult(data = {}) {
  return data.src || data.portfolio_entry?.src || "";
}

function setAudioGenBusy(isBusy, message = "") {
  const loopButton = audioGenForm?.querySelector("button[type='submit']");
  if (loopButton) loopButton.disabled = isBusy;
  if (audioGenSongButton) audioGenSongButton.disabled = isBusy;
  audioGenEmotionButtons.forEach((button) => {
    button.disabled = isBusy;
  });
  if (message && audioGenResult) audioGenResult.textContent = message;
}

function renderAudioGenResult(data = {}, label = "Generated") {
  const src = audioGenSourceFromResult(data);
  if (audioGenPlayer && src) {
    audioGenPlayer.src = src;
    audioGenPlayerPanel.hidden = false;
  }
  if (!audioGenResult) return;
  audioGenResult.innerHTML = `
    <div class="answer-meta">
      <span class="status-pill ok">${escapeHtml(label)}</span>
      <span class="status-pill">${escapeHtml(data.emotion || selectedAudioGenEmotion())}</span>
      ${data.bars ? `<span class="status-pill">${escapeHtml(data.bars)} bar setting</span>` : ""}
    </div>
    <pre class="ableton-answer-text">${escapeHtml(data.answer || "AudioGen render complete. Use the transport controls below to audition it.")}</pre>
    ${src ? `<p><a class="button" href="${escapeHtml(src)}" target="_blank" rel="noreferrer">Open WAV</a> <a class="button secondary" href="/portfolio" target="_blank" rel="noreferrer">Open portfolio</a></p>` : ""}
  `;
}

function renderAudioGenJob(job = {}) {
  const result = job.result || {};
  const src = audioGenSourceFromResult(result);
  const canCancel = job.status === "queued" || job.status === "running";
  const canRetry = job.status === "failed" || job.status === "cancelled";
  const canOpen = job.status === "completed" && src;
  return `
    <div class="audiogen-job" data-audiogen-job-id="${escapeHtml(job.id || "")}">
      <div>
        <strong>${escapeHtml(job.emotion || "joy")} full song</strong>
        <span>${escapeHtml(job.message || job.status || "queued")}</span>
      </div>
      <div class="audiogen-job-meta">
        <span class="status-pill ${job.status === "completed" ? "ok" : job.status === "failed" ? "warn" : ""}">${escapeHtml(job.status || "queued")}</span>
        <span class="status-pill">${escapeHtml(job.progress ?? 0)}%</span>
        ${job.created_at ? `<span class="status-pill">${escapeHtml(job.created_at)}</span>` : ""}
      </div>
      <div class="audiogen-progress" aria-label="Render progress"><span style="width:${Math.max(0, Math.min(100, Number(job.progress || 0)))}%"></span></div>
      ${job.chain_to_automix ? `<div class="status-pill">${job.automix_job_id ? `Auto-mix queued (job ${escapeHtml(job.automix_job_id)})` : "Auto-mix pending"}</div>` : ""}
      <div class="button-row">
        ${canOpen ? `<button type="button" data-audiogen-play-job="${escapeHtml(job.id)}">Load player</button><a class="button-link secondary" href="${escapeHtml(src)}" target="_blank" rel="noreferrer">Open WAV</a>` : ""}
        ${canCancel ? `<button type="button" data-audiogen-cancel-job="${escapeHtml(job.id)}">Cancel</button>` : ""}
        ${canRetry ? `<button type="button" data-audiogen-retry-job="${escapeHtml(job.id)}">Retry</button>` : ""}
      </div>
    </div>
  `;
}

function renderAudioGenJobs(jobs = []) {
  if (!audioGenJobs) return;
  if (!jobs.length) {
    audioGenJobs.innerHTML = "<p class='compact-status'>No full-song render jobs yet.</p>";
    return;
  }
  audioGenJobs.innerHTML = jobs.map(renderAudioGenJob).join("");
}

async function loadAudioGenJobs() {
  if (!audioGenJobs) return;
  try {
    const data = await api("/api/admin/audiogen/render-jobs?limit=12");
    renderAudioGenJobs(data.queue?.recent || []);
    const active = (data.queue?.recent || []).find((job) => job.id === audioGenActiveJobId);
    if (active?.status === "completed" && active.result) {
      renderAudioGenResult(active.result, "Full song generated");
      audioGenActiveJobId = "";
      await loadPortfolioOps();
      await loadAudioGenHistory();
    }
    const hasBusyJobs = (data.queue?.recent || []).some((job) => job.status === "queued" || job.status === "running");
    if (hasBusyJobs && !audioGenQueueTimer) {
      audioGenQueueTimer = window.setInterval(loadAudioGenJobs, 3000);
    }
    if (!hasBusyJobs && audioGenQueueTimer) {
      window.clearInterval(audioGenQueueTimer);
      audioGenQueueTimer = null;
    }
  } catch (error) {
    audioGenJobs.innerHTML = `<p class='compact-status'>${escapeHtml(error.message)}</p>`;
  }
}

function renderAudioGenHistory(items = []) {
  if (!audioGenHistory) return;
  if (!items.length) {
    audioGenHistory.innerHTML = "<p class='compact-status'>No AudioGen render history yet.</p>";
    return;
  }
  audioGenHistory.innerHTML = items.map((item) => `
    <div class="audiogen-job">
      <div>
        <strong>${escapeHtml(item.kind || "audio")} · ${escapeHtml(item.emotion || "emotion")}</strong>
        <span>${escapeHtml(item.created_at || "")}</span>
      </div>
      <div class="audiogen-job-meta">
        ${item.bars ? `<span class="status-pill">${escapeHtml(item.bars)} bar setting</span>` : ""}
        ${item.project_id ? `<span class="status-pill">Project ${escapeHtml(item.project_id)}</span>` : ""}
      </div>
      ${item.src ? `<p><a class="button-link secondary" href="${escapeHtml(item.src)}" target="_blank" rel="noreferrer">Open WAV</a></p>` : ""}
    </div>
  `).join("");
}

async function loadAudioGenHistory() {
  if (!audioGenHistory) return;
  try {
    const data = await api("/api/admin/audiogen/history?limit=12");
    renderAudioGenHistory(data.items || []);
  } catch (error) {
    audioGenHistory.innerHTML = `<p class='compact-status'>${escapeHtml(error.message)}</p>`;
  }
}

async function postAudioGenJobAction(path, id) {
  const data = await api(path, {
    method: "POST",
    body: JSON.stringify({ id }),
  });
  await loadAudioGenJobs();
  return data;
}

audioGenForm?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const emotion = selectedAudioGenEmotion();
  const prompt = audioGenPrompt?.value.trim() || `generate a ${emotion} chorus loop`;
  setAudioGenBusy(true, "Generating loop...");
  try {
    const data = await api("/api/admin/audiogen/generate", {
      method: "POST",
      body: JSON.stringify({
        prompt,
        emotion,
        bars: Number(audioGenBars?.value || 8),
        publish: true,
        project_id: selectedAudioGenProject(),
      }),
    });
    renderAudioGenResult(data, "Loop generated");
    await loadAudioGenStatus();
    await loadPortfolioOps();
    await loadAudioGenHistory();
  } catch (error) {
    if (audioGenResult) audioGenResult.textContent = error.message;
  } finally {
    setAudioGenBusy(false);
  }
});

audioGenSongButton?.addEventListener("click", async () => {
  const emotion = selectedAudioGenEmotion();
  const projectId = selectedAudioGenProject();
  const chainToAutomix = Boolean(audioGenChainAutomix?.checked) && Boolean(projectId);
  setAudioGenBusy(true, `Queueing full ${emotion} song...`);
  try {
    const data = await api("/api/admin/audiogen/render-song", {
      method: "POST",
      body: JSON.stringify({
        emotion,
        bars: Number(audioGenBars?.value || 4),
        k: 1,
        publish: true,
        project_id: projectId,
        chain_to_automix: chainToAutomix,
      }),
    });
    audioGenActiveJobId = data.job?.id || "";
    const chainNote = audioGenChainAutomix?.checked && !projectId
      ? " Select a project to auto-mix after render."
      : chainToAutomix
        ? " It will be auto-mixed once rendering finishes."
        : "";
    if (audioGenResult) audioGenResult.textContent = `Queued full ${emotion} song render. You can keep using the dashboard while it renders.${chainNote}`;
    await loadAudioGenJobs();
    await loadAudioGenStatus();
  } catch (error) {
    if (audioGenResult) audioGenResult.textContent = error.message;
  } finally {
    setAudioGenBusy(false);
  }
});

audioGenEmotionButtons.forEach((button) => {
  button.addEventListener("click", () => setAudioGenEmotion(button.dataset.audiogenEmotion || "joy"));
});

audioGenPlay?.addEventListener("click", () => {
  if (audioGenPlayer?.src) audioGenPlayer.play();
});

audioGenPause?.addEventListener("click", () => {
  audioGenPlayer?.pause();
});

audioGenStop?.addEventListener("click", () => {
  if (!audioGenPlayer) return;
  audioGenPlayer.pause();
  audioGenPlayer.currentTime = 0;
});

audioGenJobs?.addEventListener("click", async (event) => {
  const target = event.target;
  if (!(target instanceof HTMLElement)) return;
  const cancelId = target.dataset.audiogenCancelJob;
  const retryId = target.dataset.audiogenRetryJob;
  const playId = target.dataset.audiogenPlayJob;
  try {
    if (cancelId) await postAudioGenJobAction("/api/admin/audiogen/render-job/cancel", cancelId);
    if (retryId) {
      const data = await postAudioGenJobAction("/api/admin/audiogen/render-job/retry", retryId);
      audioGenActiveJobId = data.job?.id || "";
    }
    if (playId) {
      const data = await api(`/api/admin/audiogen/render-job?id=${encodeURIComponent(playId)}`);
      if (data.job?.result) renderAudioGenResult(data.job.result, "Full song loaded");
    }
  } catch (error) {
    if (audioGenResult) audioGenResult.textContent = error.message;
  }
});

audioGenJobsRefresh?.addEventListener("click", loadAudioGenJobs);
audioGenHistoryRefresh?.addEventListener("click", loadAudioGenHistory);
setAudioGenEmotion(selectedAudioGenEmotion());
document.querySelector("#audiogen-refresh")?.addEventListener("click", loadAudioGenStatus);

function renderBandBars(bands = {}) {
  const labels = {
    sub: "Sub",
    bass: "Bass",
    low_mids: "Low mids",
    mids: "Mids",
    presence: "Presence",
    air: "Air",
  };
  return `<div class="spectrum-bars">${Object.entries(labels).map(([key, label]) => {
    const value = Number(bands[key] || 0);
    const width = Math.max(2, Math.min(100, value * 420));
    return `<div class="spectrum-row">
      <span>${escapeHtml(label)}</span>
      <div><i style="width:${escapeHtml(width)}%"></i></div>
      <strong>${escapeHtml(Math.round(value * 100))}%</strong>
    </div>`;
  }).join("")}</div>`;
}

function renderPerceptualBars(metrics = {}) {
  const bands = metrics.perceptual_bands || {};
  const summary = metrics.perceptual_summary || {};
  const phonLevel = metrics.phon_level || 60;
  if (!Object.keys(bands).length) return "";
  const labels = {
    sub: "Sub",
    bass: "Bass",
    low_mids: "Low mids",
    mids: "Mids",
    presence: "Presence",
    air: "Air",
  };
  return `<section class="perceptual-panel">
    <div class="section-title">
      <h3>Ear-weighted balance</h3>
      <span class="status-pill">ISO 226:2003 (${escapeHtml(phonLevel)} phon)</span>
    </div>
    ${summary.description ? `<p class="compact-status">${escapeHtml(summary.description)}</p>` : ""}
    <div class="spectrum-bars">${Object.entries(labels).map(([key, label]) => {
      const value = Number(bands[key] || 0);
      const width = Math.max(2, Math.min(100, value * 420));
      return `<div class="spectrum-row">
        <span>${escapeHtml(label)}</span>
        <div><i class="perceptual" style="width:${escapeHtml(width)}%"></i></div>
        <strong>${escapeHtml(Math.round(value * 100))}%</strong>
      </div>`;
    }).join("")}</div>
    <p class="compact-status">This is a precise ISO 226 equal-loudness contour correction, mapping the spectral energy to human perceived loudness at a ${escapeHtml(phonLevel)} phon monitoring level.</p>
  </section>`;
}

function renderMixFlags(flags = []) {
  if (!flags.length) {
    return `<div class="mix-flags"><span class="status-pill ok">No technical flags</span></div>`;
  }
  return `<div class="mix-flags">${flags.map((flag) => `
    <span class="status-pill ${escapeHtml(flag.severity || "")}" title="${escapeHtml(flag.detail || "")}">
      ${escapeHtml(flag.label || "Check")}
    </span>`).join("")}</div>`;
}

function renderMixDiagnostics(metrics = {}) {
  const tonal = metrics.tonal_balance || {};
  const dynamics = metrics.dynamic_profile || {};
  const stereo = metrics.stereo_field || {};
  const spectral = metrics.spectral_features || {};
  if (!Object.keys(tonal).length && !Object.keys(dynamics).length && !Object.keys(stereo).length && !Object.keys(spectral).length) return "";
  return `<section class="mix-diagnostics">
    <div class="section-title">
      <h3>Deeper diagnostics</h3>
      <span class="status-pill">Analysis layer</span>
    </div>
    <div class="metrics mix-review-metrics">
      <div class="metric"><strong>${escapeHtml(tonal.profile || "—")}</strong><span>Tonal profile</span></div>
      <div class="metric"><strong>${escapeHtml(dynamics.profile || "—")}</strong><span>Dynamics</span></div>
      <div class="metric"><strong>${escapeHtml(stereo.image || "—")}</strong><span>Stereo image</span></div>
      <div class="metric"><strong>${escapeHtml(spectral.centroid_hz ?? "—")}</strong><span>Centroid Hz</span></div>
      <div class="metric"><strong>${escapeHtml(tonal.low_end_share ?? "—")}</strong><span>Low-end share</span></div>
      <div class="metric"><strong>${escapeHtml(tonal.clarity_share ?? "—")}</strong><span>Clarity share</span></div>
      <div class="metric"><strong>${escapeHtml(dynamics.transient_margin_db ?? "—")}</strong><span>Transient margin</span></div>
      <div class="metric"><strong>${escapeHtml(stereo.low_end || "—")}</strong><span>Low-end stereo</span></div>
    </div>
    ${tonal.summary ? `<p class="compact-status">${escapeHtml(tonal.summary)}</p>` : ""}
    ${dynamics.summary ? `<p class="compact-status">${escapeHtml(dynamics.summary)}</p>` : ""}
    ${stereo.summary ? `<p class="compact-status">${escapeHtml(stereo.summary)}</p>` : ""}
  </section>`;
}

function renderTransientGroove(metrics = {}) {
  const transient = metrics.transient_analysis || {};
  const groove = metrics.groove_analysis || {};
  if (!transient.onset_count && groove.timing_class === "Insufficient rhythm") return "";
  return `<section class="mix-diagnostics">
    <div class="section-title">
      <h3>Transient & groove analysis</h3>
      <span class="status-pill">${escapeHtml(groove.timing_class || transient.profile || "Analysis")}</span>
    </div>
    <div class="metrics mix-review-metrics">
      <div class="metric"><strong>${escapeHtml(transient.profile || "—")}</strong><span>Transient profile</span></div>
      <div class="metric"><strong>${escapeHtml(transient.compression_impact?.status || "—")}</strong><span>Compression impact</span></div>
      <div class="metric"><strong>${escapeHtml(transient.median_attack_ms ?? "—")}</strong><span>Median attack ms</span></div>
      <div class="metric"><strong>${escapeHtml(transient.median_attack_sustain_ratio_db ?? "—")}</strong><span>Attack/sustain dB</span></div>
      <div class="metric"><strong>${escapeHtml(transient.median_release_ms ?? "—")}</strong><span>Median release ms</span></div>
      <div class="metric"><strong>${escapeHtml(groove.bpm || "—")}</strong><span>Detected BPM</span></div>
      <div class="metric"><strong>${escapeHtml(groove.mean_abs_deviation_ms ?? "—")}</strong><span>Grid deviation ms</span></div>
      <div class="metric"><strong>${escapeHtml(groove.swing_percentage ?? "—")}%</strong><span>Swing</span></div>
      <div class="metric"><strong>${escapeHtml(groove.timing_consistency_percent ?? "—")}%</strong><span>Timing consistency</span></div>
    </div>
    ${transient.compression_impact?.diagnosis ? `<p class="compact-status">${escapeHtml(transient.compression_impact.diagnosis)}</p>` : ""}
  </section>`;
}

function renderGoalTargetChecks(metrics = {}) {
  const targetChecks = metrics.goal_target_checks || {};
  const checks = targetChecks.checks || [];
  if (!checks.length) return "";
  const goal = targetChecks.goal || metrics.mix_goal || {};
  return `<section class="mix-target-checks">
    <div class="section-title">
      <h3>Goal target checks</h3>
      <span class="status-pill">${escapeHtml(goal.label || "Selected goal")}</span>
    </div>
    ${targetChecks.summary ? `<p class="compact-status">${escapeHtml(targetChecks.summary)}</p>` : ""}
    <div class="compact-grid">
      ${checks.map((check) => `<div class="compact-card ${check.status === "warn" ? "warning" : "ok"}">
        <strong>${escapeHtml(check.label || "Target check")}</strong>
        <span>${escapeHtml(check.message || "")}</span>
        <small>Value: ${escapeHtml(check.value ?? "—")} · Target: ${escapeHtml(check.target || "—")}</small>
        ${check.education ? `<p class="compact-status">${escapeHtml(check.education)}</p>` : ""}
      </div>`).join("")}
    </div>
  </section>`;
}

function renderSourceHypotheses(items = []) {
  if (!items.length) return "";
  return `<section class="mix-source-hypotheses">
    <div class="section-title">
      <h3>Where to look first</h3>
      <span class="status-pill">Source clues</span>
    </div>
    <div class="compact-grid">
      ${items.map((item) => `<article class="compact-card">
        <strong>${escapeHtml(item.issue || "Mix issue")}</strong>
        ${(item.likely_sources || []).length ? `<span>Likely sources: ${escapeHtml(item.likely_sources.join(", "))}</span>` : ""}
        ${item.first_move ? `<p class="compact-status">${escapeHtml(item.first_move)}</p>` : ""}
        ${(item.checks || []).length ? `<ul class="hub-list">${item.checks.slice(0, 3).map((check) => `<li>${escapeHtml(check)}</li>`).join("")}</ul>` : ""}
      </article>`).join("")}
    </div>
  </section>`;
}

function renderFrequencyRepairMap(items = []) {
  if (!items.length) return "";
  return `<section class="mix-frequency-map">
    <div class="section-title">
      <h3>Frequency repair map</h3>
      <span class="status-pill">Educational EQ guide</span>
    </div>
    <div class="compact-grid">
      ${items.map((item) => `<article class="compact-card ${item.priority === "watch" ? "warning" : "ok"}">
        <strong>${escapeHtml(item.label || "Band")} · ${escapeHtml(item.range || "")}</strong>
        <span>${escapeHtml(item.message || "")}</span>
        <small>Raw: ${escapeHtml(item.raw_share ?? "—")} · Ear-weighted: ${escapeHtml(item.perceived_share ?? "—")} · ${escapeHtml(item.reading || "normal")}</small>
        ${item.role ? `<p class="compact-status">${escapeHtml(item.role)}</p>` : ""}
        ${item.listen_for ? `<small>Listen for: ${escapeHtml(item.listen_for)}</small>` : ""}
        ${item.first_move ? `<small>Try first: ${escapeHtml(item.first_move)}</small>` : ""}
      </article>`).join("")}
    </div>
  </section>`;
}

function renderMixComparison(review) {
  const comparison = review.comparison || null;
  if (!comparison) return "";
  const reference = review.reference || {};
  const coaching = review.reference_coaching || null;
  const bands = comparison.band_delta || {};
  const perceived = comparison.perceptual_band_delta || {};
  const labels = {
    sub: "Sub",
    bass: "Bass",
    low_mids: "Low mids",
    mids: "Mids",
    presence: "Presence",
    air: "Air",
  };
  const bandRows = Object.entries(labels).map(([key, label]) => {
    const value = Number(bands[key] || 0);
    const width = Math.min(100, Math.abs(value) * 900);
    const direction = value >= 0 ? "more" : "less";
    return `<div class="comparison-row">
      <span>${escapeHtml(label)}</span>
      <div><i class="${value >= 0 ? "more" : "less"}" style="width:${escapeHtml(width)}%"></i></div>
      <strong>${escapeHtml(direction)} ${escapeHtml(Math.abs(value).toFixed(3))}</strong>
    </div>`;
  }).join("");
  const perceivedRows = Object.entries(labels).map(([key, label]) => {
    const value = Number(perceived[key] || 0);
    const width = Math.min(100, Math.abs(value) * 900);
    const direction = value >= 0 ? "more" : "less";
    return `<div class="comparison-row">
      <span>${escapeHtml(label)}</span>
      <div><i class="${value >= 0 ? "more" : "less"} perceptual" style="width:${escapeHtml(width)}%"></i></div>
      <strong>${escapeHtml(direction)} ${escapeHtml(Math.abs(value).toFixed(3))}</strong>
    </div>`;
  }).join("");
  const advice = review.comparison_advice || [];
  return `<section class="mix-comparison">
    <div class="section-title">
      <h3>Reference comparison</h3>
      <span class="status-pill">${escapeHtml(reference.filename || "reference.wav")}</span>
    </div>
    ${coaching ? `<div class="compact-card">
      <strong>${escapeHtml(coaching.headline || "Reference coaching")}</strong>
      <span>${escapeHtml(coaching.level_message || "")}</span>
      ${coaching.tonal_message ? `<small>${escapeHtml(coaching.tonal_message)}</small>` : ""}
      ${coaching.perceived_message ? `<small>${escapeHtml(coaching.perceived_message)}</small>` : ""}
      ${coaching.dynamics_message ? `<small>${escapeHtml(coaching.dynamics_message)}</small>` : ""}
      ${coaching.stereo_message ? `<small>${escapeHtml(coaching.stereo_message)}</small>` : ""}
      ${coaching.next_move ? `<p class="compact-status"><strong>Next move:</strong> ${escapeHtml(coaching.next_move)}</p>` : ""}
    </div>` : ""}
    <div class="metrics mix-review-metrics">
      <div class="metric"><strong>${escapeHtml(comparison.rms_delta_db ?? "—")}</strong><span>RMS delta dB</span></div>
      <div class="metric"><strong>${escapeHtml(comparison.crest_delta_db ?? "—")}</strong><span>Crest delta</span></div>
      <div class="metric"><strong>${escapeHtml(comparison.stereo_width_delta ?? "—")}</strong><span>Width delta</span></div>
      <div class="metric"><strong>${escapeHtml(comparison.correlation_delta ?? "—")}</strong><span>Correlation delta</span></div>
    </div>
    <h4>Raw spectrum delta</h4>
    <div class="comparison-bars">${bandRows}</div>
    ${Object.keys(perceived).length ? `<h4>Ear-weighted delta</h4><div class="comparison-bars">${perceivedRows}</div>` : ""}
    ${advice.length ? `<ul class="hub-list">${advice.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>` : ""}
  </section>`;
}

function renderMixVersionComparison(review) {
  const comparison = review.version_comparison || null;
  if (!comparison) return "";
  const previous = review.previous_version || {};
  const advice = review.version_advice || [];
  const label = previous.version_label
    ? `${previous.version_label} · ${previous.created_at || ""}`
    : previous.created_at || "previous version";
  return `<section class="mix-comparison">
    <div class="section-title">
      <h3>Version comparison</h3>
      <span class="status-pill">${escapeHtml(label)}</span>
    </div>
    <div class="metrics mix-review-metrics">
      <div class="metric"><strong>${escapeHtml(comparison.rms_delta_db ?? "—")}</strong><span>RMS change</span></div>
      <div class="metric"><strong>${escapeHtml(comparison.crest_delta_db ?? "—")}</strong><span>Crest change</span></div>
      <div class="metric"><strong>${escapeHtml(comparison.stereo_width_delta ?? "—")}</strong><span>Width change</span></div>
      <div class="metric"><strong>${escapeHtml(comparison.correlation_delta ?? "—")}</strong><span>Correlation change</span></div>
    </div>
    ${advice.length ? `<ul class="hub-list">${advice.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>` : ""}
  </section>`;
}

function renderMixActionPlan(actions = []) {
  if (!actions.length) return "";
  return `<section class="mix-action-plan">
    <h3 class="lm-subheading">Priority action plan</h3>
    <ol>${actions.map((item) => `
      <li>
        <strong>${escapeHtml(item.focus || "Check")}</strong>
        <span>${escapeHtml(item.action || "")}</span>
        ${item.reason ? `<small>${escapeHtml(item.reason)}</small>` : ""}
      </li>`).join("")}</ol>
  </section>`;
}

// A7.2 — Prose summary card (3-paragraph narrative, shown above the engineer-style critique)
function renderProseSummary(prose) {
  if (!prose?.text) return "";
  const badge = prose.mode === "llm"
    ? `<span style="font-size:10px; color:var(--accent); margin-left:6px;">✦ AI</span>`
    : "";
  return `<div class="compact-card" style="margin-bottom:14px; padding:14px;">
    <h4 style="margin:0 0 10px 0; font-size:11px; font-weight:700; text-transform:uppercase; letter-spacing:.5px; color:var(--text); display:flex; align-items:center; gap:4px;">
      Critique${badge}
    </h4>
    <div style="font-size:13px; line-height:1.65; color:var(--text); white-space:pre-wrap;">${escapeHtml(prose.text)}</div>
  </div>`;
}

// A7.1 — Similar mixes card (nearest-neighbour results from historical reviews)
function renderSimilarReviews(similar) {
  if (!similar || !similar.length) return "";
  const items = similar.map((s) => {
    const goalLabel = escapeHtml(s.mix_goal_key || "mix");
    const title = escapeHtml(s.title || s.filename || "Untitled");
    const pct = Math.round((s.score || 0) * 100);
    return `<li style="display:flex; justify-content:space-between; align-items:center; padding:4px 0; border-bottom:1px solid rgba(255,255,255,0.04);">
      <span style="font-size:12px;">${title} <span style="color:var(--muted); font-size:11px;">(${goalLabel})</span></span>
      <span style="font-size:11px; color:var(--accent); font-weight:600; min-width:48px; text-align:right;">${pct}% similar</span>
    </li>`;
  }).join("");
  return `<div class="compact-card" style="margin-bottom:14px; padding:14px;">
    <h4 style="margin:0 0 10px 0; font-size:11px; font-weight:700; text-transform:uppercase; letter-spacing:.5px; color:var(--text);">
      Similar Mixes
    </h4>
    <ul style="list-style:none; margin:0; padding:0;">${items}</ul>
  </div>`;
}

function renderMixCritique(critique) {
  if (!critique?.text) return "";
  const mode = critique.mode === "llm" ? "LLM critique" : "Deterministic critique";
  const cls = critique.mode === "llm" ? "ok" : "";
  return `<section class="mix-critique">
    <div class="section-title">
      <h3>Engineer critique</h3>
      <span class="status-pill ${cls}">${escapeHtml(mode)}</span>
    </div>
    <pre>${escapeHtml(critique.text)}</pre>
    ${critique.message ? `<p class="compact-status">${escapeHtml(critique.message)}</p>` : ""}
  </section>`;
}

function renderLessonCards(cards = []) {
  if (!cards.length) return "";
  return `<section class="mix-lessons">
    <div class="section-title">
      <h3>Educational notes</h3>
      <span class="status-pill">Mix coaching</span>
    </div>
    <div class="compact-list">${cards.map((card) => `
      <article class="compact-card">
        <strong>${escapeHtml(card.flag || "Mix issue")}</strong>
        <span>${escapeHtml(card.meaning || "")}</span>
        ${card.listen_for ? `<small>Listen for: ${escapeHtml(card.listen_for)}</small>` : ""}
        ${(card.first_fixes || []).length ? `<ul class="hub-list">${card.first_fixes.slice(0, 3).map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>` : ""}
      </article>
    `).join("")}</div>
  </section>`;
}

function renderRevisionLesson(lesson) {
  if (!lesson) return "";
  return `<section class="mix-revision-lesson">
    <div class="section-title">
      <h3>Revision lesson</h3>
      <span class="status-pill">${escapeHtml(lesson.goal?.label || "Mix")}</span>
    </div>
    <p><strong>${escapeHtml(lesson.objective || "Next revision")}</strong></p>
    ${lesson.why_it_matters ? `<p class="compact-status">${escapeHtml(lesson.why_it_matters)}</p>` : ""}
    ${(lesson.steps || []).length ? `<ol>${lesson.steps.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ol>` : ""}
    ${(lesson.listening_checks || []).length ? `<ul class="hub-list">${lesson.listening_checks.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>` : ""}
  </section>`;
}

function renderRevisionCoaching(coaching) {
  if (!coaching) return "";
  return `<section class="mix-revision-coaching">
    <div class="section-title">
      <h3>Before/after coaching</h3>
      <span class="status-pill">${escapeHtml(coaching.verdict || "revision")}</span>
    </div>
    <p><strong>${escapeHtml(coaching.headline || "Revision comparison")}</strong></p>
    <p class="compact-status">Score change: ${escapeHtml(coaching.score_delta ?? 0)}</p>
    ${(coaching.metric_deltas || []).length ? `<div class="metrics mix-review-metrics">${coaching.metric_deltas.map((item) => `
      <div class="metric"><strong>${escapeHtml(item.value ?? "—")}${item.unit ? ` ${escapeHtml(item.unit)}` : ""}</strong><span>${escapeHtml(item.label || "Delta")}</span></div>
    `).join("")}</div>` : ""}
    ${coaching.next_focus ? `<p class="compact-status"><strong>Next focus:</strong> ${escapeHtml(coaching.next_focus)}</p>` : ""}
    ${coaching.listening_test ? `<p class="compact-status">${escapeHtml(coaching.listening_test)}</p>` : ""}
  </section>`;
}

function renderMixFeedbackControls(review) {
  // Was-this-useful feedback, previously only rendered inside
  // renderClosedLoopPanel() below -- which returns "" unless a closed-loop
  // action plan or repair chain happened to be generated for this specific
  // review. That silently hid the only feedback UI in the whole app on
  // every review that didn't trigger one, which is the real reason
  // mix_feedback_features ended up 100% "accepted" / 0% anything else
  // (found 2026-07-12 investigating that skew): most reviews never showed
  // a feedback control to click at all. Now always rendered, independent
  // of whether a closed-loop plan exists for this review.
  const reviewId = review.id || "";
  if (!reviewId) return "";
  return `<div class="button-row mix-feedback-controls" style="margin-top:12px;">
    <button type="button" data-mix-feedback="accepted" data-review-id="${escapeHtml(reviewId)}">Useful</button>
    <button type="button" data-mix-feedback="rejected" data-review-id="${escapeHtml(reviewId)}">Not useful</button>
    <button type="button" data-mix-feedback="needs_work" data-review-id="${escapeHtml(reviewId)}">Needs work</button>
  </div>`;
}

function renderClosedLoopPanel(review) {
  const plan = review.closed_loop_action_plan || {};
  const steps = plan.steps || [];
  const chains = review.ableton_repair_chains || {};
  const repairChains = chains.chains || [];
  const reviewId = review.id || "";
  if (!steps.length && !repairChains.length) return "";
  return `<section class="mix-closed-loop">
    <div class="section-title">
      <h3>Closed-loop actions</h3>
      <span class="status-pill">${escapeHtml(plan.primary_focus || "Revision plan")}</span>
    </div>
    ${plan.summary ? `<p class="compact-status">${escapeHtml(plan.summary)}</p>` : ""}
    ${steps.length ? `<ol class="hub-list">${steps.map((step) => `
      <li>
        <strong>#${escapeHtml(step.rank || "")} ${escapeHtml(step.focus || "Action")}</strong>
        <span>${escapeHtml(step.action || "")}</span>
        ${step.ableton_move ? `<small>Ableton: ${escapeHtml(step.device_chain || "")} · ${escapeHtml(step.ableton_move)}</small>` : ""}
        ${step.check ? `<small>Check: ${escapeHtml(step.check)}</small>` : ""}
      </li>
    `).join("")}</ol>` : ""}
    ${repairChains.length ? `<div class="compact-grid" style="margin-top:12px;">${repairChains.slice(0, 6).map((chain) => `
      <article class="compact-card">
        <strong>${escapeHtml(chain.name || "Repair chain")}</strong>
        <span>${escapeHtml((chain.devices || []).join(" → ") || "Ableton devices")}</span>
        ${chain.move ? `<small>${escapeHtml(chain.move)}</small>` : ""}
        ${chain.automation_hint ? `<p class="compact-status">${escapeHtml(chain.automation_hint)}</p>` : ""}
      </article>
    `).join("")}</div>` : ""}
    ${reviewId ? `<div class="button-row" style="margin-top:12px;">
      <a class="button-link secondary" href="/api/admin/mix-review-repair-chains?id=${encodeURIComponent(reviewId)}">Download repair JSON</a>
    </div>` : ""}
  </section>`;
}

function renderRevisionWorkflow(review) {
  const previous = review.previous_version || {};
  const coaching = review.revision_coaching || {};
  const plan = review.next_revision_plan || {};
  const steps = plan.steps || [];
  return `<section class="mix-revision-workflow">
    <div class="section-title">
      <h3>Revision compare workflow</h3>
      <span class="status-pill">${previous.id ? "Comparing versions" : "Next upload"}</span>
    </div>
    ${coaching.headline ? `<p><strong>${escapeHtml(coaching.headline)}</strong></p>` : ""}
    ${plan.focus ? `<p class="compact-status"><strong>Focus:</strong> ${escapeHtml(plan.focus)}</p>` : ""}
    <ol class="hub-list">
      <li>Apply the top closed-loop action only.</li>
      <li>Export the revision with the same start/end points.</li>
      <li>Upload it with the same track title and a new version label.</li>
      <li>Review cleared, new, and unchanged flags before making another move.</li>
    </ol>
    ${steps.length ? `<div class="compact-grid">${steps.slice(0, 4).map((step) => `
      <article class="compact-card">
        <strong>${escapeHtml(step.focus || "Step")}</strong>
        <span>${escapeHtml(step.action || "")}</span>
      </article>
    `).join("")}</div>` : ""}
  </section>`;
}

function renderQaSummary(data) {
  const qa = data.qa || {};
  const totals = qa.totals || {};
  const issues = qa.issue_counts || {};
  const ranked = qa.ranked_items || [];
  if (!Object.keys(qa).length) return "<p class='compact-status'>No QA data yet.</p>";
  return `<div class="compact-list">
    <article class="compact-card">
      <strong>${escapeHtml(totals.high_risk || 0)} high · ${escapeHtml(totals.medium_risk || 0)} medium · ${escapeHtml(totals.low_risk || 0)} low</strong>
      <span>${escapeHtml(totals.found || 0)} files scanned · ${escapeHtml((data.benchmark || {}).audio_speed_x || "—")}x realtime</span>
    </article>
    ${Object.entries(issues).slice(0, 5).map(([label, count]) => `<article class="compact-card">
      <strong>${escapeHtml(label)}</strong><span>${escapeHtml(count)} file(s)</span>
    </article>`).join("")}
    ${ranked.slice(0, 6).map((item) => `<article class="compact-card ${item.risk === "high" ? "warning" : ""}">
      <strong>${escapeHtml(item.filename || "Audio file")}</strong>
      <span>${escapeHtml(item.risk || "")} risk · score ${escapeHtml(item.technical_score ?? "—")}</span>
      ${(item.top_flags || []).length ? `<small>${escapeHtml(item.top_flags.join(", "))}</small>` : ""}
    </article>`).join("")}
  </div>`;
}

function metricValue(value, suffix = "") {
  if (value === undefined || value === null || value === "") return "—";
  return `${escapeHtml(value)}${suffix}`;
}

function renderMusicAnalysis(data) {
  const analysis = data?.analysis || {};
  const context = analysis.technical_context || {};
  const progression = analysis.progression || [];
  const intervals = analysis.intervals || [];
  const notes = analysis.analysis_notes || [];
  const highlights = analysis.section_highlights || {};
  const loudest = highlights.loudest_section || {};
  const lowestCorrelation = highlights.lowest_correlation_section || {};
  const jump = highlights.biggest_loudness_jump || {};
  const chordRows = progression.length
    ? progression.slice(0, 48).map((segment) => `
        <tr>
          <td>${escapeHtml(segment.chord || "N.C.")}</td>
          <td>${metricValue(segment.start_time, "s")}</td>
          <td>${metricValue(segment.end_time, "s")}</td>
          <td>${metricValue(segment.duration, "s")}</td>
          <td>${escapeHtml(segment.confidence || "low")}</td>
        </tr>
      `).join("")
    : `<tr><td colspan="5">No stable chord progression detected.</td></tr>`;
  const intervalItems = intervals.length
    ? intervals.slice(0, 24).map((item) => `<li>${escapeHtml(item.from_chord || "")} → ${escapeHtml(item.to_chord || "")}: ${escapeHtml(item.interval || "")}</li>`).join("")
    : "<li>No interval movement detected.</li>";
  return `<article class="mix-review-report music-analysis-report">
    <div class="section-title">
      <h3>${escapeHtml(analysis.filename || "Music analysis")}</h3>
      <span class="status-pill">${escapeHtml(analysis.source_format || "audio")} · ${metricValue(analysis.duration_seconds, "s")} · ${escapeHtml(analysis.sample_rate || "")} Hz</span>
    </div>
    <div class="mix-review-verdict">
      <strong>${escapeHtml(analysis.estimated_key || "Unknown key")}</strong>
      <span>${escapeHtml(analysis.key_confidence || "low")} confidence · ${metricValue(context.technical_score)}/100</span>
    </div>
    <div class="metrics mix-review-metrics">
      <div class="metric"><strong>${escapeHtml(analysis.estimated_key || "Unknown")}</strong><span>Estimated key</span></div>
      <div class="metric"><strong>${escapeHtml(analysis.key_confidence || "low")}</strong><span>Key confidence</span></div>
      <div class="metric"><strong>${metricValue(progression.filter((item) => item.chord && item.chord !== "N.C.").length)}</strong><span>Chord sections</span></div>
      <div class="metric"><strong>${metricValue(context.integrated_lufs)}</strong><span>Integrated LUFS</span></div>
      <div class="metric"><strong>${metricValue(context.crest_factor_db, " dB")}</strong><span>Crest factor</span></div>
      <div class="metric"><strong>${metricValue(context.stereo_correlation)}</strong><span>Stereo correlation</span></div>
      <div class="metric"><strong>${escapeHtml(context.dominant_band || "—")}</strong><span>Dominant band</span></div>
    </div>
    ${notes.length ? `<section style="margin-top:16px;">
      <div class="section-title"><h3>Analysis Notes</h3></div>
      <ul class="hub-list">${notes.map((note) => `<li>${escapeHtml(String(note).replaceAll("_", " "))}</li>`).join("")}</ul>
    </section>` : ""}
    <section style="margin-top:16px;">
      <div class="section-title">
        <h3>Chord Timeline</h3>
        <span class="status-pill">${metricValue(progression.length)} segment(s)</span>
      </div>
      <div class="table-wrap">
        <table>
          <thead><tr><th>Chord</th><th>Start</th><th>End</th><th>Duration</th><th>Confidence</th></tr></thead>
          <tbody>${chordRows}</tbody>
        </table>
      </div>
    </section>
    <section style="margin-top:16px;">
      <div class="section-title">
        <h3>Interval Movement</h3>
      </div>
      <ul class="hub-list">${intervalItems}</ul>
    </section>
    <section style="margin-top:16px;">
      <div class="section-title">
        <h3>Section Highlights</h3>
      </div>
      <div class="metrics mix-review-metrics">
        <div class="metric"><strong>${escapeHtml(loudest.label || "—")}</strong><span>Loudest section ${loudest.rms_dbfs !== undefined ? `(${escapeHtml(loudest.rms_dbfs)} dBFS)` : ""}</span></div>
        <div class="metric"><strong>${escapeHtml(lowestCorrelation.label || "—")}</strong><span>Lowest correlation ${lowestCorrelation.stereo_correlation !== undefined ? escapeHtml(lowestCorrelation.stereo_correlation) : ""}</span></div>
        <div class="metric"><strong>${jump?.delta_db !== undefined ? `${escapeHtml(jump.delta_db)} dB` : "—"}</strong><span>Biggest loudness jump</span></div>
      </div>
    </section>
  </article>`;
}

function renderMixReview(review) {
  if (!review) return "";
  window.mixReviews = window.mixReviews || {};
  window.mixReviews[review.id] = review;

  const metrics = review.metrics || {};
  const flags = review.flags || [];
  const advice = review.advice || [];
  const actions = review.action_plan || [];
  const critique = review.mix_critique || null;
  const handoff = review.kenn_handoff || null;
  const mixGoal = metrics.mix_goal || {};

  const exports = review.id
    ? `<div class="button-row" style="margin-top: 12px;">
        <a class="button-link" href="/api/admin/mix-review-report/${encodeURIComponent(review.id)}.html" target="_blank" rel="noopener">Open report</a>
        <a class="button-link secondary" href="/api/admin/mix-review-report/${encodeURIComponent(review.id)}.json">Download JSON</a>
        <a class="button-link secondary" href="/api/admin/mix-review-repair-chains?id=${encodeURIComponent(review.id)}">Download repair JSON</a>
        <a class="button-link secondary" href="/api/admin/mix-review-rack?id=${encodeURIComponent(review.id)}">Download Ableton Rack (.adg)</a>
        ${review.reference_id ? `<a class="button-link secondary" href="/api/admin/mix-review-match-preset?id=${encodeURIComponent(review.id)}">Download EQ8 Reference Match (.adv)</a>` : ""}
        ${review.comparison?.eq_bands ? `<a class="button-link secondary" href="/api/admin/mix-review-match-preset?id=${encodeURIComponent(review.id)}&format=proq3">Download Pro-Q 3 Match (.ffp)</a>` : ""}
      </div>`
    : "";

  const chordsData = metrics.chords || {};
  const key = chordsData.estimated_key || "Unknown";
  const chordNotes = chordsData.analysis_notes || [];

  return `<article class="mix-review-report" id="mix-review-card-${review.id}" data-review-id="${escapeHtml(review.id)}">
    <div class="section-title">
      <h3>${escapeHtml(review.title || metrics.filename || "Mix review")}${review.version_label ? ` · ${escapeHtml(review.version_label)}` : ""}</h3>
      <span class="status-pill">${escapeHtml(mixGoal.label || "Premaster")} · ${metricValue(metrics.duration_seconds, "s")} · ${escapeHtml(metrics.sample_rate || "")} Hz</span>
    </div>

    <!-- Synchronized Audio Player -->
    <div class="abc-player-container">
      <audio class="abc-audio-element" preload="none"></audio>
      <div class="abc-player-controls">
        <div class="abc-left-controls">
          <button type="button" class="abc-play-btn" title="Play/Pause">
            <svg class="play-icon" viewBox="0 0 24 24" width="20" height="20" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>
            <svg class="pause-icon" viewBox="0 0 24 24" width="20" height="20" fill="currentColor" style="display:none;"><path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z"/></svg>
          </button>
          <div class="abc-track-selector">
            <button type="button" class="abc-track-btn active mix" data-track-type="mix">Mix [A]</button>
            ${review.reference || metrics.has_reference ? `<button type="button" class="abc-track-btn reference" data-track-type="reference">Ref [B]</button>` : ""}
            ${review.previous_version?.id ? `<button type="button" class="abc-track-btn previous" data-track-type="previous">Prev [C]</button>` : ""}
          </div>
        </div>
        <div class="abc-time-display">0:00 / 0:00</div>
      </div>
      
      <div class="waveform-scrubber-header" style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px; font-size: 11px;">
        <span class="waveform-scrubber-label" style="font-weight: 600; color: var(--ink);">Timeline Waveform</span>
        <label style="cursor: pointer; display: flex; align-items: center; gap: 4px; user-select: none; color: var(--muted); font-size: 11px; margin: 0;">
          <input type="checkbox" class="lufs-heatmap-toggle" style="margin: 0; transform: scale(0.9);" />
          Loudness Heat Map
        </label>
      </div>

      <div class="waveform-scrubber">
        <div class="waveform-progress-bar"></div>
        <div class="waveform-visual"></div>
        
        <!-- Silence zones -->
        ${metrics.leading_silence_seconds > 0 ? `<div class="waveform-silence-region start-silence" title="Start Silence"></div>` : ""}
        ${metrics.trailing_silence_seconds > 0 ? `<div class="waveform-silence-region end-silence" title="End Silence"></div>` : ""}
        
        <!-- Loudest section pin -->
        <div class="waveform-marker-pin loudest-marker" style="display:none;"></div>
        <div class="waveform-marker-label loudest-marker" style="display:none;">Loudest</div>
      </div>

      <div class="lufs-heatmap-legend" style="display: none; justify-content: space-between; align-items: center; font-size: 11px; margin-top: 6px; padding: 6px 10px; background: rgba(0,0,0,0.2); border-radius: 4px; border: 1px solid var(--line);">
        <div style="display: flex; gap: 10px; align-items: center; flex-wrap: wrap;">
          <span style="display: flex; align-items: center; gap: 4px;"><span style="display: inline-block; width: 8px; height: 8px; border-radius: 50%; background: #ef4444;"></span> &gt; -9 (Hot)</span>
          <span style="display: flex; align-items: center; gap: 4px;"><span style="display: inline-block; width: 8px; height: 8px; border-radius: 50%; background: #f59e0b;"></span> -14 to -9 (Pop/Club)</span>
          <span style="display: flex; align-items: center; gap: 4px;"><span style="display: inline-block; width: 8px; height: 8px; border-radius: 50%; background: #10b981;"></span> -18 to -14 (Target)</span>
          <span style="display: flex; align-items: center; gap: 4px;"><span style="display: inline-block; width: 8px; height: 8px; border-radius: 50%; background: #3b82f6;"></span> &lt; -18 (Quiet)</span>
        </div>
        <div style="font-weight: bold; color: var(--accent);">
          Targets: Club (-9) · Spotify (-14) · Apple (-16)
        </div>
      </div>
    </div>

    <!-- A8.1 Live Analysis Panel -->
    <div class="live-analysis-panel compact-card" style="margin-top:12px; padding:12px; display:none;">
      <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
        <h4 style="margin:0; font-size:11px; font-weight:700; text-transform:uppercase; letter-spacing:.5px;">Live Analysis</h4>
        <button type="button" class="live-stop-btn button-link secondary" style="font-size:11px; padding:2px 10px;">Stop</button>
      </div>
      <div style="display:grid; grid-template-columns:1fr 1fr; gap:10px;">
        <div>
          <div style="font-size:10px; color:var(--muted); margin-bottom:3px;">LUFS momentary</div>
          <div class="live-lufs-display" style="font-size:22px; font-weight:700; color:var(--accent);">—</div>
        </div>
        <div>
          <div style="font-size:10px; color:var(--muted); margin-bottom:3px;">Correlation</div>
          <div class="live-corr-display" style="font-size:22px; font-weight:700; color:var(--accent);">—</div>
        </div>
      </div>
      <div style="margin-top:10px;">
        <div style="font-size:10px; color:var(--muted); margin-bottom:4px;">Spectrum</div>
        <canvas class="live-spectrum-canvas" width="360" height="60"
          style="width:100%; height:60px; background:#090d16; border-radius:4px; display:block;">
        </canvas>
      </div>
    </div>
    <div style="margin-top:8px;">
      <button type="button" class="live-start-btn button-link secondary" style="font-size:11px;">
        ▶ Live Analysis
      </button>
    </div>

    <!-- Inner Tab Navigation -->
    <div class="mix-review-inner-tab-bar">
      <button type="button" class="mix-review-inner-tab active" data-tab="dashboard">Dashboard</button>
      <button type="button" class="mix-review-inner-tab" data-tab="actions">Actions</button>
      <button type="button" class="mix-review-inner-tab" data-tab="tonal-balance">Tonal Balance</button>
      <button type="button" class="mix-review-inner-tab" data-tab="timeline">Timeline & Chords</button>
      <button type="button" class="mix-review-inner-tab" data-tab="diagnostics">Diagnostics</button>
    </div>

    <!-- Sub Tab: Dashboard -->
    <div class="mix-review-tab-panel active" data-panel="dashboard">
      <div class="mix-review-verdict">
        <strong>${escapeHtml(metrics.technical_rating || "Technical review")}</strong>
        <span>${metricValue(metrics.technical_score)}/100</span>
      </div>
      ${review.comparison?.tonal_balance_score !== null && review.comparison?.tonal_balance_score !== undefined ? `<div class="mix-review-verdict">
        <strong>Tonal balance vs reference</strong>
        <span>${metricValue(review.comparison.tonal_balance_score)}/100</span>
      </div>` : ""}
      ${review.summary ? `<p class="mix-review-summary">${escapeHtml(review.summary)}</p>` : ""}
      ${renderMixFeedbackControls(review)}
      ${renderProseSummary(review.prose_summary)}
      ${renderMixCritique(critique)}
      ${renderRevisionCoaching(review.revision_coaching)}
      ${renderRevisionLesson(review.revision_lesson)}
      ${renderMixActionPlan(actions)}
      ${renderSourceHypotheses(review.source_hypotheses || [])}
      ${renderFrequencyRepairMap(review.frequency_repair_map || [])}
      ${renderLessonCards(review.lesson_cards || [])}
      ${renderMixFlags(flags)}
      ${renderSimilarReviews(review.similar_reviews || [])}

      <h3 class="lm-subheading" style="margin-top:16px;">Advice</h3>
      <ul class="hub-list" style="margin-bottom:12px;">${advice.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>
      ${handoff ? `<div class="compact-card" style="margin-top: 12px;">
        <strong>KENN handoff</strong>
        <span>${escapeHtml(handoff.summary || "Send this review to KENN for follow-up advice.")}</span>
        <div class="button-row" style="margin-top: 8px;">
          <button type="button" data-ask-kenn-handoff data-kenn-context="${escapeHtml(handoff.context || "")}" data-kenn-prompt="${escapeHtml(handoff.prompt || "")}">Ask KENN</button>
          <button type="button" data-copy-kenn-handoff="${escapeHtml(`${handoff.context || ""}\n\n${handoff.prompt || ""}`)}">Copy KENN prompt</button>
        </div>
      </div>` : ""}
      ${exports}
    </div>

    <!-- Sub Tab: Actions -->
    <div class="mix-review-tab-panel" data-panel="actions">
      ${renderClosedLoopPanel(review)}
      ${renderRevisionWorkflow(review)}
    </div>

    <!-- Sub Tab: Tonal Balance -->
    <div class="mix-review-tab-panel" data-panel="tonal-balance">
      <div class="tonal-balance-chart">
        <div class="section-title" style="margin-bottom: 4px;">
          <h4 style="margin:0; font-size:14px; font-weight:700;">Tonal Balance Curve</h4>
          <span class="status-pill">${escapeHtml(mixGoal.label || "Premaster")} Envelope</span>
        </div>
        <div class="tonal-balance-chart-container"></div>
      </div>
      <div style="margin-top:12px;">
        ${renderBandBars(metrics.bands || {})}
      </div>
      <div style="margin-top:12px;">
        ${renderPerceptualBars(metrics)}
      </div>
      <div style="margin-top:16px;">
        <div class="section-title" style="margin-bottom: 8px;">
          <h4 style="margin:0; font-size:14px; font-weight:700;">3D Spectrogram Waterfall</h4>
          <span class="status-pill">Real-time synced visualizer</span>
        </div>
        <canvas class="waterfall-canvas" width="580" height="150" style="width: 100%; height: 150px; background: #090d16; border-radius: 6px; display: block; border: 1px solid var(--line);"></canvas>
      </div>
    </div>

    <!-- Sub Tab: Timeline & Chords -->
    <div class="mix-review-tab-panel" data-panel="timeline">
      <div class="compact-card">
        <div style="display:flex; justify-content:space-between; align-items:center;">
          <strong style="font-size:15px;">Estimated Key: <span style="color:var(--accent); font-weight:800;">${escapeHtml(key)}</span></strong>
          <span class="status-pill">${escapeHtml(chordsData.key_confidence || "low")} confidence</span>
        </div>
        ${chordNotes.length ? `<ul class="hub-list" style="margin-top:10px;">${chordNotes.map((note) => `<li>${escapeHtml(String(note).replaceAll("_", " "))}</li>`).join("")}</ul>` : ""}
        <div class="chord-timeline-grid">
          ${(chordsData.progression || []).map((seg) => `
            <div class="chord-block" data-start="${seg.start_time}" data-end="${seg.end_time}">
              <strong>${escapeHtml(seg.chord || "N.C.")}</strong>
              <span>${seg.start_time}s - ${seg.end_time}s · ${escapeHtml(seg.confidence || "low")}</span>
            </div>
          `).join("")}
          ${!(chordsData.progression || []).length ? `<p class="compact-status">No chords detected on the timeline.</p>` : ""}
        </div>
      </div>
      ${renderMixVersionComparison(review)}
      ${renderMixComparison(review)}
    </div>

    <!-- Sub Tab: Diagnostics -->
    <div class="mix-review-tab-panel" data-panel="diagnostics">
      <!-- LED Meters -->
      <div style="display:grid; grid-template-columns:1fr 1fr; gap:12px; margin-bottom:16px;">
        <!-- Correlation LED Meter -->
        <div class="led-meter-container corr-meter-wrap">
          <div class="led-meter-title-row">
            <span>Stereo Correlation</span>
            <span class="value-readout" style="color:var(--accent);">${escapeHtml(metrics.stereo_correlation ?? "—")}</span>
          </div>
          <div class="led-meter corr-leds"></div>
          <div class="led-meter-labels">
            <span>-1 (Phase Out)</span>
            <span>0 (Mono)</span>
            <span>+1 (Stereo Safe)</span>
          </div>
        </div>

        <!-- Crest factor LED Meter -->
        <div class="led-meter-container crest-meter-wrap">
          <div class="led-meter-title-row">
            <span>Crest Factor / Headroom</span>
            <span class="value-readout" style="color:var(--accent);">${escapeHtml(metrics.crest_factor_db ?? "—")} dB</span>
          </div>
          <div class="led-meter crest-leds"></div>
          <div class="led-meter-labels">
            <span>2 dB (Overcompressed)</span>
            <span>Target (Blue)</span>
            <span>18 dB (Undercompressed)</span>
          </div>
        </div>
      </div>

      <!-- A6.2: Vectorscope + Correlation Timeline -->
      <div style="display:grid; grid-template-columns:1fr 1.6fr; gap:12px; margin-bottom:16px; align-items:start;">
        <div class="compact-card" style="padding:12px;">
          <h4 style="margin:0 0 8px 0; font-size:11px; font-weight:700; text-transform:uppercase; letter-spacing:0.5px; color:var(--text);">Vectorscope</h4>
          <canvas class="vectorscope-canvas" width="220" height="220"
            style="width:100%; aspect-ratio:1; background:#090d16; border-radius:6px; border:1px solid var(--line); display:block;">
          </canvas>
          <p style="font-size:10px; color:var(--muted); margin:6px 0 0 0; line-height:1.4;">45°-rotated M/S scatter. Vertical = mono/phase-safe, horizontal = anti-phase.</p>
        </div>
        <div class="compact-card" style="padding:12px;">
          <h4 style="margin:0 0 8px 0; font-size:11px; font-weight:700; text-transform:uppercase; letter-spacing:0.5px; color:var(--text);">Correlation Over Time</h4>
          <canvas class="correlation-timeline-canvas" width="420" height="100"
            style="width:100%; height:100px; background:#090d16; border-radius:6px; border:1px solid var(--line); display:block;">
          </canvas>
          <div class="correlation-dips-summary" style="font-size:11px; color:var(--muted); margin-top:6px; line-height:1.5;"></div>
        </div>
      </div>

      <div class="metrics mix-review-metrics">
        <div class="metric"><strong>${escapeHtml(metrics.peak_dbfs ?? "—")}</strong><span>Peak dBFS</span></div>
        <div class="metric"><strong>${escapeHtml(metrics.rms_dbfs_estimate ?? "—")}</strong><span>RMS est.</span></div>
        <div class="metric"><strong>${escapeHtml(metrics.loudest_section_rms_dbfs ?? "—")}</strong><span>Loudest RMS</span></div>
        <div class="metric"><strong>${escapeHtml(metrics.crest_factor_db ?? "—")}</strong><span>Crest dB</span></div>
        <div class="metric"><strong>${escapeHtml(metrics.dynamic_range_estimate_db ?? "—")}</strong><span>Range dB</span></div>
        <div class="metric"><strong>${escapeHtml(metrics.stereo_correlation ?? "—")}</strong><span>Correlation</span></div>
        <div class="metric"><strong>${escapeHtml(metrics.stereo_width_ratio ?? "—")}</strong><span>Width ratio</span></div>
        <div class="metric"><strong>${escapeHtml(metrics.dc_offset ?? "—")}</strong><span>DC offset</span></div>
      </div>
      <dl class="mix-review-detail" style="margin-top:12px; margin-bottom:12px;">
        <dt>Channels</dt><dd>${escapeHtml(metrics.channels ?? "—")}</dd>
        <dt>L/R peaks</dt><dd>${metricValue(metrics.left_peak_dbfs)} / ${metricValue(metrics.right_peak_dbfs)} dBFS</dd>
        <dt>Silence</dt><dd>${metricValue(metrics.leading_silence_seconds, "s")} start · ${metricValue(metrics.trailing_silence_seconds, "s")} end</dd>
        <dt>Clipped frames</dt><dd>${escapeHtml(metrics.clipped_frames_estimate ?? 0)}</dd>
      </dl>
      
      <!-- Distortion & Resonance Section -->
      <section style="margin-top:16px; margin-bottom:16px; background: rgba(255,255,255,0.01); border: 1px solid rgba(255,255,255,0.03); border-radius: var(--border-radius-card); padding: 16px;">
        <h4 style="margin: 0 0 12px 0; font-size:11px; font-weight:700; color:var(--text); display:flex; align-items:center; gap:6px; text-transform: uppercase; letter-spacing: 0.5px;">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"></path></svg>
          Distortion & Resonance Analysis
        </h4>
        
        <div class="metrics mix-review-metrics" style="grid-template-columns: repeat(auto-fit, minmax(110px, 1fr)); gap: 10px; margin-bottom: 12px;">
          <div class="metric">
            <strong>${(metrics.distortion_thd !== undefined) ? `${(metrics.distortion_thd * 100).toFixed(3)}%` : "—"}</strong>
            <span>THD (Total)</span>
          </div>
          <div class="metric">
            <strong>${(metrics.distortion_even_thd !== undefined) ? `${(metrics.distortion_even_thd * 100).toFixed(3)}%` : "—"}</strong>
            <span>Even THD (Warmth)</span>
          </div>
          <div class="metric">
            <strong>${(metrics.distortion_odd_thd !== undefined) ? `${(metrics.distortion_odd_thd * 100).toFixed(3)}%` : "—"}</strong>
            <span>Odd THD (Clipping)</span>
          </div>
          <div class="metric">
            <strong>${(metrics.inter_sample_peak_dbfs !== undefined) ? `${metrics.inter_sample_peak_dbfs} dBFS` : "—"}</strong>
            <span>Inter-Sample Peak</span>
          </div>
        </div>

        <div style="font-size:11.5px; line-height: 1.4; color:var(--muted);">
          <strong style="color:var(--text);">Detected Resonances:</strong>
          ${(metrics.resonances && metrics.resonances.length > 0) ? `
            <ul style="margin: 6px 0 0 0; padding-left: 16px; display: flex; flex-direction: column; gap: 4px;">
              ${metrics.resonances.map(r => `
                <li><strong>${r.frequency_hz} Hz</strong> (Severity: <span style="color:#ef4444; font-weight:600;">+${r.severity_db} dB</span>, Q: ${r.q})</li>
              `).join("")}
            </ul>
          ` : `
            <p style="margin: 6px 0 0 0; font-style: italic;">No significant resonance ringing detected.</p>
          `}
        </div>
      </section>

      ${renderMixDiagnostics(metrics)}
      ${renderTransientGroove(metrics)}
      ${renderGoalTargetChecks(metrics)}
    </div>

    <p class="compact-status" style="margin-top: 12px;">First-pass technical analysis only. Use references and human listening for final decisions.</p>
  </article>`;
}

let audioSources = new WeakMap();
function getAnalyserForAudio(audio) {
  if (audioSources.has(audio)) {
    return audioSources.get(audio);
  }
  try {
    const AudioContextClass = window.AudioContext || window.webkitAudioContext;
    const ctx = new AudioContextClass();
    const source = ctx.createMediaElementSource(audio);
    const analyser = ctx.createAnalyser();
    analyser.fftSize = 256;
    source.connect(analyser);
    analyser.connect(ctx.destination);
    
    const data = { ctx, analyser, source };
    audioSources.set(audio, data);
    return data;
  } catch (e) {
    console.error("Failed to initialize AudioContext:", e);
    return null;
  }
}

// ---------------------------------------------------------------------------
// A6.2 — Vectorscope and Correlation-Over-Time visualisations
// Static one-shot draws from report data (not live audio).
// ---------------------------------------------------------------------------

function drawVectorscope(canvas, points) {
  if (!canvas || !points || !points.length) return;
  const ctx = canvas.getContext("2d");
  const W = canvas.width, H = canvas.height;
  ctx.fillStyle = "#090d16";
  ctx.fillRect(0, 0, W, H);
  // Crosshair guide lines
  ctx.strokeStyle = "rgba(255,255,255,0.07)";
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(W / 2, 0); ctx.lineTo(W / 2, H);
  ctx.moveTo(0, H / 2); ctx.lineTo(W, H / 2);
  // 45° diagonal guides
  ctx.moveTo(0, 0); ctx.lineTo(W, H);
  ctx.moveTo(W, 0); ctx.lineTo(0, H);
  ctx.stroke();
  // Scale to fit the data
  let maxAbs = 0.001;
  for (const [x, y] of points) {
    const a = Math.max(Math.abs(x), Math.abs(y));
    if (a > maxAbs) maxAbs = a;
  }
  const scale = (Math.min(W, H) / 2 - 6) / maxAbs;
  ctx.fillStyle = "rgba(139,92,246,0.4)";
  for (const [x, y] of points) {
    const px = W / 2 + x * scale;
    const py = H / 2 - y * scale;
    ctx.fillRect(px - 0.8, py - 0.8, 1.6, 1.6);
  }
}

function drawCorrelationTimeline(canvas, timeline, dipsEl) {
  if (!canvas || !timeline || !timeline.timestamps || !timeline.timestamps.length) return;
  const ctx = canvas.getContext("2d");
  const W = canvas.width, H = canvas.height;
  ctx.fillStyle = "#090d16";
  ctx.fillRect(0, 0, W, H);
  const n = timeline.timestamps.length;
  const totalSeconds = (timeline.timestamps[n - 1] || 0) + (timeline.window_seconds || 0.1);
  const valToY = (c) => H - ((Math.max(-1, Math.min(1, c)) + 1) / 2) * H;
  // Zero-correlation reference line
  ctx.strokeStyle = "rgba(255,255,255,0.10)";
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(0, valToY(0)); ctx.lineTo(W, valToY(0));
  ctx.stroke();
  // Shade dip regions
  ctx.fillStyle = "rgba(239,68,68,0.18)";
  for (const dip of (timeline.dip_events || [])) {
    const x1 = (dip.start_seconds / totalSeconds) * W;
    const x2 = (dip.end_seconds / totalSeconds) * W;
    ctx.fillRect(x1, 0, Math.max(1, x2 - x1), H);
  }
  // Correlation line
  ctx.strokeStyle = "rgba(139,92,246,0.9)";
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  for (let i = 0; i < n; i++) {
    const x = (i / Math.max(n - 1, 1)) * W;
    const y = valToY(timeline.correlation[i]);
    if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
  }
  ctx.stroke();
  // Dip summary text
  if (dipsEl) {
    const dips = timeline.dip_events || [];
    if (dips.length === 0) {
      dipsEl.textContent = "No phase dips detected.";
    } else {
      const lines = dips.map((d) => {
        const t1 = fmtSeconds(d.start_seconds);
        const t2 = fmtSeconds(d.end_seconds);
        return `${t1}–${t2} (min corr ${d.min_correlation.toFixed(2)})`;
      });
      dipsEl.innerHTML = `${dips.length} phase dip${dips.length > 1 ? "s" : ""}: ${lines.join(" · ")}`;
    }
  }
}

function fmtSeconds(s) {
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60).toString().padStart(2, "0");
  return `${m}:${sec}`;
}

// ---------------------------------------------------------------------------
// A8.2 — Dual-spectrum canvas for A/B comparison
// ---------------------------------------------------------------------------

function drawDualSpectrum(canvas, bandsA, bandsB) {
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  const W = canvas.width, H = canvas.height;
  const BAND_NAMES = ["sub", "bass", "low_mids", "mids", "presence", "sibilance", "air"];
  const LABELS = ["Sub", "Bass", "Low mids", "Mids", "Presence", "Sib.", "Air"];
  const n = BAND_NAMES.length;
  const barW = (W - 48) / n;
  const pairW = barW * 0.42;
  const maxVal = Math.max(
    ...BAND_NAMES.map((k) => Math.max(bandsA[k] || 0, bandsB[k] || 0)),
    0.001
  );

  ctx.fillStyle = "#090d16";
  ctx.fillRect(0, 0, W, H);

  for (let i = 0; i < n; i++) {
    const x = 24 + i * barW;
    const valA = bandsA[BAND_NAMES[i]] || 0;
    const valB = bandsB[BAND_NAMES[i]] || 0;
    const hA = Math.round(((H - 28) * valA) / maxVal);
    const hB = Math.round(((H - 28) * valB) / maxVal);

    // Mix A — purple
    ctx.fillStyle = "rgba(139,92,246,0.85)";
    ctx.fillRect(x, H - 24 - hA, pairW, hA);
    // Mix B — teal
    ctx.fillStyle = "rgba(20,184,166,0.85)";
    ctx.fillRect(x + pairW + 2, H - 24 - hB, pairW, hB);

    // Difference dot
    const diffY = H - 24 - Math.round(((H - 28) * (valA + valB) / 2) / maxVal);
    const sign = valA - valB;
    ctx.fillStyle = sign > 0.005 ? "rgba(249,115,22,0.9)" : sign < -0.005 ? "rgba(99,102,241,0.9)" : "rgba(255,255,255,0.3)";
    ctx.fillRect(x + pairW - 1, diffY, pairW + 4, 2);

    // Band label
    ctx.fillStyle = "rgba(255,255,255,0.45)";
    ctx.font = "9px sans-serif";
    ctx.textAlign = "center";
    ctx.fillText(LABELS[i], x + barW / 2 - 2, H - 6);
  }

  // Legend
  ctx.fillStyle = "rgba(139,92,246,0.9)";
  ctx.fillRect(4, 6, 10, 8);
  ctx.fillStyle = "rgba(255,255,255,0.6)";
  ctx.font = "9px sans-serif";
  ctx.textAlign = "left";
  ctx.fillText("A", 16, 14);
  ctx.fillStyle = "rgba(20,184,166,0.9)";
  ctx.fillRect(28, 6, 10, 8);
  ctx.fillStyle = "rgba(255,255,255,0.6)";
  ctx.fillText("B", 40, 14);
}

function startWaterfallAnimation(report, audio) {
  const canvas = report.querySelector(".waterfall-canvas");
  if (!canvas) return null;
  const ctx2d = canvas.getContext("2d");
  
  const history = [];
  const maxHistory = 45;
  let animationId = null;
  
  function renderFrame() {
    const analData = getAnalyserForAudio(audio);
    const bins = 64;
    const frameData = new Uint8Array(bins);
    if (analData) {
      analData.analyser.getByteFrequencyData(frameData);
    }
    
    history.push(frameData);
    if (history.length > maxHistory) {
      history.shift();
    }
    
    ctx2d.fillStyle = "#090d16";
    ctx2d.fillRect(0, 0, canvas.width, canvas.height);
    
    const W = canvas.width;
    const H = canvas.height;
    
    ctx2d.strokeStyle = "rgba(255, 255, 255, 0.08)";
    ctx2d.lineWidth = 1;
    
    // gridlines low to high freq perspective projection
    const gridFractions = [0.15, 0.35, 0.55, 0.75, 0.9];
    gridFractions.forEach((f) => {
      ctx2d.beginPath();
      for (let h = 0; h < history.length; h++) {
        const t = h / (maxHistory - 1);
        const y = 30 + (1 - t) * 100;
        const s = 0.4 + t * 0.6;
        const w = W * s;
        const x = (W - w) / 2 + f * w;
        if (h === 0) ctx2d.moveTo(x, y);
        else ctx2d.lineTo(x, y);
      }
      ctx2d.stroke();
    });
    
    // time horizontal dividers
    for (let h = 0; h < history.length; h += 5) {
      const t = h / (maxHistory - 1);
      const y = 30 + (1 - t) * 100;
      const s = 0.4 + t * 0.6;
      const w = W * s;
      const x = (W - w) / 2;
      ctx2d.beginPath();
      ctx2d.moveTo(x, y);
      ctx2d.lineTo(x + w, y);
      ctx2d.stroke();
    }
    
    // ribbons back to front
    for (let h = 0; h < history.length; h++) {
      const t = h / (maxHistory - 1);
      const y = 30 + (1 - t) * 100;
      const s = 0.4 + t * 0.6;
      const w = W * s;
      const x = (W - w) / 2;
      const data = history[h];
      
      ctx2d.beginPath();
      for (let i = 0; i < bins; i++) {
        const bx = x + (i / (bins - 1)) * w;
        const amp = (data[i] / 255) * 45 * s;
        const by = y - amp;
        if (i === 0) ctx2d.moveTo(bx, by);
        else ctx2d.lineTo(bx, by);
      }
      ctx2d.lineTo(x + w, y);
      ctx2d.lineTo(x, y);
      ctx2d.closePath();
      
      const grad = ctx2d.createLinearGradient(x, y, x + w, y);
      const alpha = 0.15 + t * 0.75;
      grad.addColorStop(0, `rgba(139, 92, 246, ${alpha * 0.4})`);
      grad.addColorStop(0.3, `rgba(236, 72, 153, ${alpha * 0.6})`);
      grad.addColorStop(0.7, `rgba(249, 115, 22, ${alpha * 0.8})`);
      grad.addColorStop(1, `rgba(234, 179, 8, ${alpha})`);
      
      ctx2d.fillStyle = grad;
      ctx2d.fill();
      
      ctx2d.beginPath();
      for (let i = 0; i < bins; i++) {
        const bx = x + (i / (bins - 1)) * w;
        const amp = (data[i] / 255) * 45 * s;
        const by = y - amp;
        if (i === 0) ctx2d.moveTo(bx, by);
        else ctx2d.lineTo(bx, by);
      }
      const strokeGrad = ctx2d.createLinearGradient(x, y, x + w, y);
      const strokeAlpha = 0.3 + t * 0.7;
      strokeGrad.addColorStop(0, `rgba(139, 92, 246, ${strokeAlpha})`);
      strokeGrad.addColorStop(0.3, `rgba(236, 72, 153, ${strokeAlpha})`);
      strokeGrad.addColorStop(0.7, `rgba(249, 115, 22, ${strokeAlpha})`);
      strokeGrad.addColorStop(1, `rgba(234, 179, 8, ${strokeAlpha})`);
      ctx2d.strokeStyle = strokeGrad;
      ctx2d.lineWidth = 1.5;
      ctx2d.stroke();
    }
    
    animationId = requestAnimationFrame(renderFrame);
  }
  
  const onPlay = () => {
    const analData = getAnalyserForAudio(audio);
    if (analData && analData.ctx.state === "suspended") {
      analData.ctx.resume();
    }
    if (!animationId) {
      renderFrame();
    }
  };
  const onPause = () => {
    if (animationId) {
      cancelAnimationFrame(animationId);
      animationId = null;
    }
  };
  
  audio.addEventListener("play", onPlay);
  audio.addEventListener("pause", onPause);
  audio.addEventListener("ended", onPause);
  
  if (!audio.paused) {
    onPlay();
  }
  
  return () => {
    audio.removeEventListener("play", onPlay);
    audio.removeEventListener("pause", onPause);
    audio.removeEventListener("ended", onPause);
    if (animationId) cancelAnimationFrame(animationId);
  };
}

function wireMixReviews() {
  document.querySelectorAll(".mix-review-report").forEach((report) => {
    if (report.dataset.wired) return;
    report.dataset.wired = "true";

    const reviewId = report.dataset.reviewId;
    const review = window.mixReviews ? window.mixReviews[reviewId] : null;
    if (!review) return;

    const metrics = review.metrics || {};

    // 1. Inner tab controls
    const tabButtons = report.querySelectorAll(".mix-review-inner-tab");
    const panels = report.querySelectorAll(".mix-review-tab-panel");
    tabButtons.forEach((btn) => {
      btn.addEventListener("click", () => {
        const targetTab = btn.dataset.tab;
        tabButtons.forEach((b) => b.classList.remove("active"));
        panels.forEach((p) => p.classList.remove("active"));

        btn.classList.add("active");
        const activePanel = report.querySelector(`.mix-review-tab-panel[data-panel="${targetTab}"]`);
        if (activePanel) activePanel.classList.add("active");
      });
    });

    // 2. Synchronized Audio Player Setup
    const audio = report.querySelector(".abc-audio-element");
    const playBtn = report.querySelector(".abc-play-btn");
    const trackSelectors = report.querySelectorAll(".abc-track-btn");
    const timeDisplay = report.querySelector(".abc-time-display");
    
    // Scrubber elements
    const waveformScrubber = report.querySelector(".waveform-scrubber");
    const progressBar = report.querySelector(".waveform-progress-bar");
    const waveformVisual = report.querySelector(".waveform-visual");

    // Generate dynamic waveform visual bars
    const barCount = 120;
    let waveformHtml = "";
    const heights = [];
    for (let i = 0; i < barCount; i++) {
      const ratio = i / barCount;
      let env = Math.sin(ratio * Math.PI); // simple shape envelope
      if (ratio > 0.35 && ratio < 0.65) {
        env += (Math.random() * 0.25);
      } else {
        env += (Math.random() * 0.12);
      }
      env = Math.max(0.1, Math.min(1.0, env));
      const height = Math.round(env * 100);
      heights.push(height);
    }
    const avgHeight = heights.reduce((a, b) => a + b, 0) / barCount;
    const lufsVal = metrics.integrated_lufs !== undefined && metrics.integrated_lufs !== "n/a" ? parseFloat(metrics.integrated_lufs) : -14;
    for (let i = 0; i < barCount; i++) {
      const height = heights[i];
      const barLufs = lufsVal + (height - avgHeight) * 0.18;
      let colorVal = "";
      if (barLufs > -9) {
        colorVal = "#ef4444"; // Hot Red
      } else if (barLufs > -14) {
        colorVal = "#f59e0b"; // Orange/Yellow
      } else if (barLufs > -18) {
        colorVal = "#10b981"; // Green
      } else {
        colorVal = "#3b82f6"; // Blue
      }
      waveformHtml += `<div class="waveform-bar" style="height: ${height}%;" data-index="${i}" data-lufs="${barLufs.toFixed(1)}" data-color="${colorVal}" title="${barLufs.toFixed(1)} LUFS"></div>`;
    }
    if (waveformVisual) waveformVisual.innerHTML = waveformHtml;

    // A/B/C track swapping logic
    const setSource = (type) => {
      const wasPlaying = !audio.paused;
      const curTime = audio.currentTime;
      
      let srcUrl = "";
      if (type === "mix") {
        srcUrl = `/api/admin/mix-review-audio?id=${encodeURIComponent(reviewId)}&type=mix`;
      } else if (type === "reference") {
        if (review.reference && review.reference.id) {
          if (review.reference.saved) {
            srcUrl = `/api/admin/mix-reference-audio?id=${encodeURIComponent(review.reference.id)}`;
          } else {
            srcUrl = `/api/admin/mix-review-audio?id=${encodeURIComponent(reviewId)}&type=reference`;
          }
        } else {
          srcUrl = `/api/admin/mix-review-audio?id=${encodeURIComponent(reviewId)}&type=reference`;
        }
      } else if (type === "previous" && review.previous_version && review.previous_version.id) {
        srcUrl = `/api/admin/mix-review-audio?id=${encodeURIComponent(review.previous_version.id)}&type=mix`;
      }

      audio.src = srcUrl;
      audio.load();

      const onLoaded = () => {
        audio.currentTime = Math.min(curTime, audio.duration || 9999);
        if (wasPlaying) {
          audio.play().catch(e => console.log("Play failed after swap:", e));
        }
        audio.removeEventListener("loadedmetadata", onLoaded);
      };
      audio.addEventListener("loadedmetadata", onLoaded);
    };

    trackSelectors.forEach((btn) => {
      btn.addEventListener("click", () => {
        trackSelectors.forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");
        setSource(btn.dataset.trackType);
      });
    });

    if (playBtn && audio) {
      playBtn.addEventListener("click", () => {
        if (!audio.src) {
          const activeBtn = report.querySelector(".abc-track-btn.active");
          if (activeBtn) setSource(activeBtn.dataset.trackType);
        }
        if (audio.paused) {
          document.querySelectorAll("audio").forEach((otherAudio) => {
            if (otherAudio !== audio) otherAudio.pause();
          });
          audio.play().catch(e => console.log("Play failed:", e));
        } else {
          audio.pause();
        }
      });

      audio.addEventListener("play", () => {
        playBtn.querySelector(".play-icon").style.display = "none";
        playBtn.querySelector(".pause-icon").style.display = "block";
      });

      audio.addEventListener("pause", () => {
        playBtn.querySelector(".play-icon").style.display = "block";
        playBtn.querySelector(".pause-icon").style.display = "none";
      });
    }

    // Scrubber seeking
    if (waveformScrubber) {
      waveformScrubber.addEventListener("click", (e) => {
        const rect = waveformScrubber.getBoundingClientRect();
        const clickX = e.clientX - rect.left;
        const clickRatio = Math.max(0, Math.min(1, clickX / rect.width));
        if (audio.duration) {
          audio.currentTime = clickRatio * audio.duration;
        }
      });
    }

    // Time update listener (Waveform, Chord progression)
    if (audio) {
      audio.addEventListener("timeupdate", () => {
        if (!audio.duration) return;
        const ratio = audio.currentTime / audio.duration;
        if (progressBar) progressBar.style.width = `${ratio * 100}%`;

        // Update time display text
        const curMin = Math.floor(audio.currentTime / 60);
        const curSec = Math.floor(audio.currentTime % 60).toString().padStart(2, "0");
        const durMin = Math.floor(audio.duration / 60);
        const durSec = Math.floor(audio.duration % 60).toString().padStart(2, "0");
        if (timeDisplay) timeDisplay.textContent = `${curMin}:${curSec} / ${durMin}:${durSec}`;

        // Waveform bars fill
        if (waveformVisual) {
          const activeBarCount = Math.round(ratio * barCount);
          const bars = waveformVisual.querySelectorAll(".waveform-bar");
          bars.forEach((bar, idx) => {
            if (idx < activeBarCount) {
              bar.classList.add("active");
            } else {
              bar.classList.remove("active");
            }
          });
        }

        // Real-time chord progression highlight
        const chordBlocks = report.querySelectorAll(".chord-block");
        chordBlocks.forEach((block) => {
          const start = parseFloat(block.dataset.start);
          const end = parseFloat(block.dataset.end);
          if (audio.currentTime >= start && audio.currentTime <= end) {
            block.classList.add("active");
          } else {
            block.classList.remove("active");
          }
        });
      });

      // Loaded metadata: silence regions & loudest markers
      audio.addEventListener("loadedmetadata", () => {
        const duration = audio.duration || metrics.duration_seconds || 1.0;
        
        // Silence regions position
        const leading = metrics.leading_silence_seconds || 0;
        const trailing = metrics.trailing_silence_seconds || 0;

        const startSilence = report.querySelector(".waveform-silence-region.start-silence");
        if (startSilence) {
          startSilence.style.left = "0";
          startSilence.style.width = `${(leading / duration) * 100}%`;
        }

        const endSilence = report.querySelector(".waveform-silence-region.end-silence");
        if (endSilence) {
          endSilence.style.right = "0";
          endSilence.style.width = `${(trailing / duration) * 100}%`;
        }

        // Loudest section pin placement
        const loudestPin = report.querySelector(".waveform-marker-pin.loudest-marker");
        const loudestLabel = report.querySelector(".waveform-marker-label.loudest-marker");
        if (loudestPin && loudestLabel) {
          const percent = 45;
          loudestPin.style.left = `${percent}%`;
          loudestLabel.style.left = `${percent}%`;
          loudestPin.style.display = "block";
          loudestLabel.style.display = "block";
        }
      });
    }

    // 3. Render LED Meters (Correlation and Crest Factor)
    // A. Correlation LED (21 segments, representing -1.0 to 1.0)
    const corrMeter = report.querySelector(".corr-leds");
    if (corrMeter) {
      const corrVal = metrics.stereo_correlation !== undefined ? parseFloat(metrics.stereo_correlation) : 0.0;
      let corrHtml = "";
      const activeIdx = Math.round(((corrVal + 1) / 2) * 20);
      for (let i = 0; i <= 20; i++) {
        let state = "inactive";
        if (i === 10) {
          state = "active-warning";
        } else if (i < 10 && corrVal < 0 && i >= activeIdx) {
          state = "active-negative";
        } else if (i > 10 && corrVal > 0 && i <= activeIdx) {
          state = "active-positive";
        }
        corrHtml += `<div class="led-segment ${state}"></div>`;
      }
      corrMeter.innerHTML = corrHtml;
    }

    // B. Crest factor LED (20 segments, representing 2dB to 18dB)
    const crestMeter = report.querySelector(".crest-leds");
    if (crestMeter) {
      const crestVal = metrics.crest_factor_db !== undefined ? parseFloat(metrics.crest_factor_db) : 8.0;
      let minTarget = 8.0;
      let maxTarget = 14.0;
      
      const goalKey = metrics.mix_goal?.key || "premaster";
      if (goalKey === "club") { minTarget = 5.5; maxTarget = 12.0; }
      else if (goalKey === "pop_vocal" || goalKey === "rap_vocal") { minTarget = 5.0; maxTarget = 12.0; }
      else if (goalKey === "master") { minTarget = 4.0; maxTarget = 8.0; }

      let crestHtml = "";
      for (let i = 0; i < 20; i++) {
        const segVal = 2.0 + (i * 0.8);
        let state = "inactive";
        
        const isWithinTarget = segVal >= minTarget && segVal <= maxTarget;
        const isActive = segVal <= crestVal;

        if (isActive) {
          if (isWithinTarget) {
            state = "active-target";
          } else if (segVal < minTarget) {
            state = "active-negative";
          } else {
            state = "active-warning";
          }
        } else if (isWithinTarget) {
          state = "inactive active-target-guide";
        }
        crestHtml += `<div class="led-segment ${state}" title="${segVal.toFixed(1)} dB"></div>`;
      }
      crestMeter.innerHTML = crestHtml;
    }

    // 3c. A6.2 — Vectorscope + Correlation-Over-Time canvases
    const vsCanvas = report.querySelector(".vectorscope-canvas");
    const ctCanvas = report.querySelector(".correlation-timeline-canvas");
    const ctDips = report.querySelector(".correlation-dips-summary");
    const timeline = metrics.correlation_timeline;
    if (vsCanvas && timeline) {
      drawVectorscope(vsCanvas, timeline.vectorscope_points || []);
    }
    if (ctCanvas && timeline) {
      drawCorrelationTimeline(ctCanvas, timeline, ctDips);
    }

    // 4. Render SVG Tonal Balance curve
    const chartContainer = report.querySelector(".tonal-balance-chart-container");
    if (chartContainer) {
      const goalKey = metrics.mix_goal?.key || "premaster";
      
      const envelopes = {
        premaster: [ [0.10, 0.25], [0.18, 0.32], [0.15, 0.28], [0.15, 0.26], [0.05, 0.15], [0.03, 0.09], [0.02, 0.08] ],
        club:      [ [0.18, 0.38], [0.22, 0.38], [0.12, 0.24], [0.12, 0.24], [0.04, 0.12], [0.02, 0.08], [0.02, 0.08] ],
        podcast:   [ [0.01, 0.08], [0.04, 0.16], [0.18, 0.34], [0.18, 0.34], [0.08, 0.22], [0.04, 0.12], [0.02, 0.08] ],
        pop_vocal: [ [0.08, 0.22], [0.15, 0.28], [0.15, 0.28], [0.16, 0.30], [0.06, 0.18], [0.03, 0.10], [0.03, 0.10] ]
      };
      
      const targetCorridor = envelopes[goalKey] || envelopes["premaster"];
      const bandsKeys = ["sub", "bass", "low_mids", "mids", "presence", "sibilance", "air"];
      
      const xCoords = [50, 130, 210, 290, 370, 450, 530];
      const valToY = (val) => 180 - (val * 320);

      const topPoints = [];
      const bottomPoints = [];
      targetCorridor.forEach((range, idx) => {
        const x = xCoords[idx];
        const yMin = valToY(range[0]);
        const yMax = valToY(range[1]);
        topPoints.push(`${x},${yMax}`);
        bottomPoints.unshift(`${x},${yMin}`);
      });
      const polygonPoints = [...topPoints, ...bottomPoints].join(" ");

      const actualBands = metrics.bands || {};
      const mixPoints = bandsKeys.map((key, idx) => {
        const val = Number(actualBands[key] || 0);
        return `${xCoords[idx]},${valToY(val)}`;
      });

      let refPathHtml = "";
      let refDotsHtml = "";
      if (review.reference && review.reference.metrics && review.reference.metrics.bands) {
        const refBands = review.reference.metrics.bands;
        const refPoints = bandsKeys.map((key, idx) => {
          const val = Number(refBands[key] || 0);
          return `${xCoords[idx]},${valToY(val)}`;
        });
        refPathHtml = `<path d="M ${refPoints.join(" L ")}" fill="none" stroke="#10b981" stroke-width="2.5" stroke-dasharray="5,5" />`;
        refDotsHtml = refPoints.map((pt, idx) => {
          const parts = pt.split(",");
          return `<circle cx="${parts[0]}" cy="${parts[1]}" r="4.5" fill="#10b981" stroke="#111827" stroke-width="1.5" title="${bandsKeys[idx]}: ${Math.round(Number(review.reference.metrics.bands[bandsKeys[idx]] || 0) * 100)}%" />`;
        }).join("");
      }

      const mixDotsHtml = mixPoints.map((pt, idx) => {
        const parts = pt.split(",");
        return `<circle cx="${parts[0]}" cy="${parts[1]}" r="5.5" fill="#8b5cf6" stroke="#fff" stroke-width="1.5" title="${bandsKeys[idx]}: ${Math.round(Number(actualBands[bandsKeys[idx]] || 0) * 100)}%" />`;
      }).join("");

      const gridHtml = xCoords.map((x, idx) => `
        <line x1="${x}" y1="15" x2="${x}" y2="185" stroke="var(--line)" stroke-width="1" stroke-dasharray="2,4" />
        <text x="${x}" y="196" fill="var(--muted)" font-size="9" font-weight="bold" text-anchor="middle">${bandsKeys[idx].toUpperCase().replace("_", " ")}</text>
      `).join("");

      // Match EQ Suggestion Curve & Nodes
      const getTargetVal = (key, idx) => {
        if (review.reference && review.reference.metrics && review.reference.metrics.bands) {
          return Number(review.reference.metrics.bands[key] || 0);
        }
        const range = targetCorridor[idx];
        return (range[0] + range[1]) / 2;
      };

      const gainToY = (gain) => 100 - (gain * 6.5);
      const correctivePoints = bandsKeys.map((key, idx) => {
        const mixVal = Math.max(0.01, Number(actualBands[key] || 0.15));
        const targetVal = Math.max(0.01, getTargetVal(key, idx));
        const gainDb = 10 * Math.log10(targetVal / mixVal);
        const correctedGain = Math.max(-12, Math.min(12, gainDb));
        return {
          x: xCoords[idx],
          y: gainToY(correctedGain),
          gain: correctedGain,
          key: key
        };
      });
      const correctivePathD = `M ${correctivePoints.map(p => `${p.x},${p.y}`).join(" L ")}`;

      const zeroLineHtml = `<line x1="15" y1="100" x2="565" y2="100" stroke="rgba(255,255,255,0.15)" stroke-width="1.5" stroke-dasharray="4,4" />`;
      const correctivePathHtml = `<path d="${correctivePathD}" fill="none" stroke="#ffffff" stroke-width="2.5" stroke-dasharray="3,3" filter="drop-shadow(0 0 3px rgba(255,255,255,0.5))" />`;

      const centerFrequencies = {
        sub: "30 Hz",
        bass: "100 Hz",
        low_mids: "280 Hz",
        mids: "1.0 kHz",
        presence: "4.0 kHz",
        sibilance: "7.0 kHz",
        air: "12.0 kHz"
      };
      const correctiveDotsHtml = correctivePoints.map((pt) => {
        const freqStr = centerFrequencies[pt.key];
        const sign = pt.gain >= 0 ? "+" : "";
        const tooltipText = `Corrective: ${sign}${pt.gain.toFixed(1)} dB at ${freqStr} (Q=0.71)`;
        return `
          <g class="eq-node-group" style="cursor: pointer;">
            <circle cx="${pt.x}" cy="${pt.y}" r="6.5" fill="#ffffff" stroke="#8b5cf6" stroke-width="2" />
            <circle cx="${pt.x}" cy="${pt.y}" r="15" fill="transparent" />
            <title>${tooltipText}</title>
          </g>
        `;
      }).join("");

      const svgHtml = `
        <svg viewBox="0 0 580 210" width="100%" height="200" style="overflow: visible; background: var(--panel); border-radius: 6px;">
          ${gridHtml}
          <polygon points="${polygonPoints}" fill="rgba(99, 102, 241, 0.12)" stroke="rgba(99, 102, 241, 0.28)" stroke-width="1.5" stroke-dasharray="3,3" />
          ${refPathHtml}
          ${refDotsHtml}
          <path d="M ${mixPoints.join(" L ")}" fill="none" stroke="#8b5cf6" stroke-width="3" />
          ${mixDotsHtml}
          
          ${zeroLineHtml}
          ${correctivePathHtml}
          ${correctiveDotsHtml}
          
          <g transform="translate(15, 20)" font-size="9" font-weight="bold">
            <rect x="0" y="0" width="10" height="10" fill="rgba(99, 102, 241, 0.2)" stroke="rgba(99, 102, 241, 0.5)" />
            <text x="15" y="8" fill="var(--ink)">Goal Target</text>
            <line x1="100" y1="5" x2="115" y2="5" stroke="#8b5cf6" stroke-width="3" />
            <text x="120" y="8" fill="var(--ink)">Current Mix</text>
            ${review.reference ? `
              <line x1="200" y1="5" x2="215" y2="5" stroke="#10b981" stroke-width="2.5" stroke-dasharray="4,4" />
              <text x="220" y="8" fill="var(--ink)">Reference</text>
            ` : ""}
            <line x1="300" y1="5" x2="315" y2="5" stroke="#ffffff" stroke-width="2.5" stroke-dasharray="3,3" />
            <text x="320" y="8" fill="var(--ink)">Match EQ</text>
          </g>
        </svg>
      `;
      chartContainer.innerHTML = svgHtml;
    }

    // LUFS Heatmap Toggle Logic
    const heatmapToggle = report.querySelector(".lufs-heatmap-toggle");
    if (heatmapToggle) {
      heatmapToggle.addEventListener("change", () => {
        const isHeatmap = heatmapToggle.checked;
        const bars = report.querySelectorAll(".waveform-bar");
        bars.forEach((bar) => {
          if (isHeatmap) {
            bar.style.backgroundColor = bar.dataset.color;
            bar.style.borderColor = bar.dataset.color;
          } else {
            bar.style.backgroundColor = "";
            bar.style.borderColor = "";
          }
        });
        
        const legend = report.querySelector(".lufs-heatmap-legend");
        if (legend) {
          legend.style.display = isHeatmap ? "flex" : "none";
        }
      });
    }

    // 3D Spectrogram Waterfall Synced to Playhead
    if (report.cleanupWaterfall) {
      report.cleanupWaterfall();
    }
    if (audio) {
      report.cleanupWaterfall = startWaterfallAnimation(report, audio);
    }

    // A8.1 Live Analysis wiring
    const liveStartBtn = report.querySelector(".live-start-btn");
    const liveStopBtn = report.querySelector(".live-stop-btn");
    const livePanel = report.querySelector(".live-analysis-panel");
    const liveSpectrumCanvas = report.querySelector(".live-spectrum-canvas");

    if (liveStartBtn && audio) {
      liveStartBtn.addEventListener("click", () => {
        if (!audio.src) { alert("Load an audio file first."); return; }
        livePanel.style.display = "";
        liveStartBtn.style.display = "none";
        let _ctx = null, _source = null, _processor = null;
        const sampleRate = 44100;

        const stopLive = () => {
          try { _processor?.disconnect(); _source?.disconnect(); _ctx?.close(); } catch (_) {}
          _ctx = _source = _processor = null;
          livePanel.style.display = "none";
          liveStartBtn.style.display = "";
        };
        liveStopBtn?.addEventListener("click", stopLive, {once: true});

        try {
          _ctx = new (window.AudioContext || window.webkitAudioContext)({sampleRate});
          _source = _ctx.createMediaElementSource(audio);
          _processor = _ctx.createScriptProcessor(4096, 2, 2);
          _source.connect(_processor);
          _processor.connect(_ctx.destination);
          _source.connect(_ctx.destination);

          let lastPost = 0;
          _processor.onaudioprocess = async (e) => {
            const now = Date.now();
            if (now - lastPost < 90) return;
            lastPost = now;
            const L = Array.from(e.inputBuffer.getChannelData(0));
            const R = e.inputBuffer.numberOfChannels > 1 ? Array.from(e.inputBuffer.getChannelData(1)) : L;
            // Pack as 16-bit signed PCM
            const pcm = new Int16Array(L.length * 2);
            for (let i = 0; i < L.length; i++) {
              pcm[i * 2] = Math.max(-32768, Math.min(32767, Math.round(L[i] * 32767)));
              pcm[i * 2 + 1] = Math.max(-32768, Math.min(32767, Math.round(R[i] * 32767)));
            }
            const b64 = btoa(String.fromCharCode(...new Uint8Array(pcm.buffer)));
            try {
              const res = await api("/api/live/analyze", {
                method: "POST",
                body: JSON.stringify({pcm_base64: b64, sample_rate: _ctx.sampleRate, channels: 2}),
              });
              // Update LUFS
              const lufsEl = report.querySelector(".live-lufs-display");
              if (lufsEl) lufsEl.textContent = res.lufs_momentary?.toFixed(1) + " LU";
              // Update correlation
              const corrEl = report.querySelector(".live-corr-display");
              if (corrEl) corrEl.textContent = (res.correlation ?? "—").toFixed ? res.correlation.toFixed(2) : "—";
              // Spectrum canvas
              if (liveSpectrumCanvas && res.bands) {
                const ctx2d = liveSpectrumCanvas.getContext("2d");
                const W = liveSpectrumCanvas.width, H = liveSpectrumCanvas.height;
                ctx2d.fillStyle = "#090d16"; ctx2d.fillRect(0, 0, W, H);
                const keys = ["sub","bass","low_mids","mids","presence","sibilance","air"];
                const bw = W / keys.length;
                const maxVal = Math.max(...keys.map(k => res.bands[k] || 0), 0.001);
                ctx2d.fillStyle = "rgba(139,92,246,0.85)";
                keys.forEach((k, i) => {
                  const h = Math.round((H - 4) * (res.bands[k] || 0) / maxVal);
                  ctx2d.fillRect(i * bw + 2, H - 2 - h, bw - 4, h);
                });
              }
            } catch (_) {}
          };
        } catch (err) {
          console.error("Live analysis setup failed:", err);
          stopLive();
        }
      });
    }
  });
}

// A8.2 A/B comparison button handler
document.addEventListener("click", async (event) => {
  if (event.target.id === "ab-compare-btn" || event.target.closest("#ab-compare-btn")) {
    const selA = document.querySelector("#ab-compare-a");
    const selB = document.querySelector("#ab-compare-b");
    const resultEl = document.querySelector("#ab-compare-result");
    if (!selA || !selB || !resultEl) return;
    const idA = selA.value, idB = selB.value;
    if (!idA || !idB || idA === "— no reviews yet —") return;
    resultEl.innerHTML = "<p class='compact-status'>Comparing…</p>";
    try {
      const data = await api("/api/admin/mix-review/compare-ab", {
        method: "POST",
        body: JSON.stringify({review_id_a: idA, review_id_b: idB}),
      });
      const comp = data.comparison || {};
      const score = comp.match_score ?? "—";
      const scoreColor = score >= 80 ? "var(--ok)" : score >= 50 ? "var(--warn)" : "var(--error)";
      const canvasId = `ab-spectrum-${Date.now()}`;
      resultEl.innerHTML = `
        <div style="display:flex; align-items:center; gap:16px; margin-bottom:12px;">
          <div style="font-size:32px; font-weight:800; color:${scoreColor};">${score}%</div>
          <div style="font-size:12px; color:var(--muted); line-height:1.5;">
            <strong style="color:var(--text);">${escapeHtml(data.review_a?.title || "A")}</strong>
            vs <strong style="color:var(--text);">${escapeHtml(data.review_b?.title || "B")}</strong><br>
            LUFS Δ ${comp.lufs_delta_db != null ? comp.lufs_delta_db.toFixed(1) + " dB" : "—"} ·
            Width Δ ${(comp.stereo_width_delta || 0).toFixed(3)}
          </div>
        </div>
        <canvas id="${canvasId}" width="480" height="110"
          style="width:100%; height:110px; background:#090d16; border-radius:6px; display:block;">
        </canvas>
      `;
      const canvas = document.getElementById(canvasId);
      if (canvas) drawDualSpectrum(canvas, data.review_a?.bands || {}, data.review_b?.bands || {});
    } catch (err) {
      resultEl.innerHTML = `<p class='compact-status error'>${escapeHtml(err.message)}</p>`;
    }
  }
});

document.addEventListener("click", async (event) => {
  const feedbackBtn = event.target.closest("[data-mix-feedback]");
  if (feedbackBtn) {
    const reviewId = feedbackBtn.dataset.reviewId || "";
    const decision = feedbackBtn.dataset.mixFeedback || "";
    if (!reviewId || !decision) return;
    try {
      const data = await api("/api/admin/mix-review-feedback", {
        method: "POST",
        body: JSON.stringify({ review_id: reviewId, decision }),
      });
      statusEl.textContent = data.ok ? `Mix review feedback recorded: ${decision}.` : (data.error || "Feedback failed.");
    } catch (error) {
      statusEl.textContent = error.message;
    }
    return;
  }
  const askBtn = event.target.closest("[data-ask-kenn-handoff]");
  if (askBtn) {
    const question = askBtn.dataset.kennPrompt || "Turn this mix review into practical next moves.";
    const context = askBtn.dataset.kennContext || "";
    showTab("ableton");
    await askAbleton(question, context ? [{ role: "user", content: context }] : []);
    return;
  }
  const handoffBtn = event.target.closest("[data-copy-kenn-handoff]");
  if (!handoffBtn) return;
  const text = handoffBtn.dataset.copyKennHandoff || "";
  if (!text) return;
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      statusEl.textContent = "KENN mix-review prompt copied.";
    } else {
      statusEl.textContent = text;
    }
  } catch (error) {
    statusEl.textContent = error.message;
  }
});

document.querySelector("#mix-review-qa-refresh")?.addEventListener("click", async () => {
  const resultEl = document.querySelector("#mix-review-qa-result");
  const status = document.querySelector("#mix-review-status");
  if (resultEl) resultEl.innerHTML = "<p class='compact-status'>Scanning Portfolio/audio…</p>";
  try {
    const data = await api("/api/admin/mix-review-qa");
    if (resultEl) resultEl.innerHTML = renderQaSummary(data);
    if (status) status.textContent = "Catalogue QA scan complete.";
  } catch (error) {
    if (resultEl) resultEl.innerHTML = `<p class='compact-status'>${escapeHtml(error.message)}</p>`;
  }
});

async function loadMixReviews() {
  const listEl = document.querySelector("#mix-review-list");
  const latestEl = document.querySelector("#mix-review-latest");
  if (!listEl) return;
  listEl.innerHTML = "<p class='compact-status'>Loading…</p>";
  try {
    const data = await api("/api/admin/mix-reviews");
    let items = data.items || [];
    items = items.filter((item) => !String(item.title || "").toLowerCase().includes("smoke"));
    latestEl.innerHTML = items.length ? renderMixReview(items[0]) : "<p class='compact-status'>No mix reviews yet.</p>";
    listEl.innerHTML = items.slice(1, 12).length
      ? items.slice(1, 12).map(renderMixReview).join("")
      : "<p class='compact-status'>No previous reviews.</p>";

    // Wire up players, tabs, visualizers, and meters
    wireMixReviews();

    // A8.2 — populate A/B comparison selectors
    const abSelA = document.querySelector("#ab-compare-a");
    const abSelB = document.querySelector("#ab-compare-b");
    if (abSelA && abSelB) {
      const opts = items.map((item) =>
        `<option value="${escapeHtml(item.id)}">${escapeHtml(item.title || item.metrics?.filename || item.id)}</option>`
      ).join("");
      abSelA.innerHTML = opts;
      abSelB.innerHTML = opts;
      if (items.length > 1) abSelB.selectedIndex = 1;
    }
  } catch (error) {
    listEl.innerHTML = `<p class='compact-status'>${escapeHtml(error.message)}</p>`;
  }
}

async function loadMixVersionTimeline() {
  const cardEl = document.querySelector("#mix-version-timeline-card");
  const listEl = document.querySelector("#mix-version-timeline-list");
  if (!cardEl || !listEl) return;
  const sessionId = localStorage.getItem("kenn_session_id") || "";
  if (!sessionId) {
    cardEl.style.display = "none";
    return;
  }
  try {
    const data = await api(`/api/ableton/mix-versions?session_id=${encodeURIComponent(sessionId)}`);
    const versions = data.versions || [];
    if (!versions.length) {
      cardEl.style.display = "none";
      return;
    }
    cardEl.style.display = "block";
    listEl.innerHTML = versions.map((ver, idx) => {
      const activeClass = idx === versions.length - 1 ? "active-timeline-item" : "";
      const metrics = ver.metrics || {};
      const score = metrics.technical_score || "—";
      const dateStr = new Date(ver.created_at * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
      return `
        <div class="timeline-version-card ${activeClass}" style="flex: 0 0 160px; padding: 12px; background: rgba(255, 255, 255, 0.05); border: 1px solid var(--line); border-radius: 6px; display: flex; flex-direction: column; gap: 4px; cursor: pointer; transition: all 0.2s;" data-version-idx="${idx}">
          <div style="font-weight: 700; color: var(--accent); font-size: 13px;">${escapeHtml(ver.version_label)}</div>
          <div style="font-size: 11px; color: var(--muted);">${escapeHtml(dateStr)}</div>
          <div style="font-size: 12px; font-weight: bold; color: var(--ink); margin-top: 4px;">Score: ${score}/100</div>
          <div style="font-size: 10px; color: var(--muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 100%;" title="${escapeHtml(metrics.filename || '')}">${escapeHtml(metrics.filename || '')}</div>
        </div>
      `;
    }).join("");

    listEl.querySelectorAll(".timeline-version-card").forEach((item) => {
      item.addEventListener("click", () => {
        listEl.querySelectorAll(".timeline-version-card").forEach(c => c.style.borderColor = "var(--line)");
        item.style.borderColor = "var(--accent)";
        const idx = parseInt(item.dataset.versionIdx);
        const ver = versions[idx];
        
        const audio = document.querySelector(".abc-audio-element");
        const trackSelectorContainer = document.querySelector(".abc-track-selector");
        if (trackSelectorContainer && audio) {
          let prevBtn = trackSelectorContainer.querySelector(".abc-track-btn.previous");
          if (!prevBtn) {
            prevBtn = document.createElement("button");
            prevBtn.type = "button";
            prevBtn.className = "abc-track-btn previous";
            prevBtn.dataset.trackType = "previous";
            prevBtn.textContent = "Prev [C]";
            trackSelectorContainer.appendChild(prevBtn);
            
            prevBtn.addEventListener("click", () => {
              trackSelectorContainer.querySelectorAll(".abc-track-btn").forEach(b => b.classList.remove("active"));
              prevBtn.classList.add("active");
              
              const wasPlaying = !audio.paused;
              const curTime = audio.currentTime;
              const reviewId = ver.metrics.review_id || ver.id;
              audio.src = `/api/admin/mix-review-audio?id=${encodeURIComponent(reviewId)}&type=mix`;
              audio.load();
              const onLoaded = () => {
                audio.currentTime = Math.min(curTime, audio.duration || 9999);
                if (wasPlaying) {
                  audio.play().catch(e => console.log("Play failed after swap:", e));
                }
                audio.removeEventListener("loadedmetadata", onLoaded);
              };
              audio.addEventListener("loadedmetadata", onLoaded);
            });
          }
          prevBtn.click();
        }
      });
    });
  } catch (error) {
    console.error("Error loading mix version timeline:", error);
    cardEl.style.display = "none";
  }
}

function renderMixReference(item) {
  const metrics = item.metrics || {};
  const label = [item.name || item.original_name || "Reference", item.style || ""].filter(Boolean).join(" · ");
  return `<article class="compact-card">
    <strong>${escapeHtml(label)}</strong>
    <span>${escapeHtml(metrics.technical_rating || "Analysed")} · ${escapeHtml(metrics.rms_dbfs_estimate ?? "—")} RMS · ${escapeHtml(metrics.crest_factor_db ?? "—")} crest</span>
  </article>`;
}

async function loadMixReferences() {
  const select = document.querySelector("#mix-review-reference-id");
  const list = document.querySelector("#mix-reference-list");
  if (!select) return;
  try {
    const data = await api("/api/admin/mix-references");
    const items = data.items || [];
    select.innerHTML = `<option value="">No saved reference</option>${items
      .map((item) => {
        const label = [item.name || item.original_name || "Reference", item.style || ""].filter(Boolean).join(" · ");
        return `<option value="${escapeHtml(item.id)}">${escapeHtml(label)}</option>`;
      })
      .join("")}`;
    if (list) {
      list.innerHTML = items.length
        ? items.slice(0, 6).map(renderMixReference).join("")
        : "<p class='compact-status'>No saved references yet.</p>";
    }
  } catch (error) {
    if (list) list.innerHTML = `<p class='compact-status'>${escapeHtml(error.message)}</p>`;
  }
}

document.querySelector("#mix-review-refresh")?.addEventListener("click", () => {
  loadMixReviews();
  loadMixReferences();
  loadCalibrationTargets();
  loadMixVersionTimeline();
});

document.querySelector("#music-analysis-form")?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const status = document.querySelector("#music-analysis-status");
  const resultEl = document.querySelector("#music-analysis-result");
  const file = document.querySelector("#music-analysis-file")?.files?.[0];
  const goal = document.querySelector("#music-analysis-goal")?.value || "premaster";
  if (!file) return;
  const form = new FormData();
  form.append("file", file);
  form.append("mix_goal", goal);
  if (status) status.textContent = "Analysing music…";
  if (resultEl) resultEl.innerHTML = "";
  try {
    const response = await fetch("/api/admin/music-analysis", {
      method: "POST",
      credentials: "same-origin",
      body: form,
    });
    const data = await response.json();
    csrfToken = data.csrf_token || "";
    if (!response.ok || !data.ok) throw new Error(data.error || "Music analysis failed.");
    if (status) status.textContent = "Music analysis complete.";
    if (resultEl) resultEl.innerHTML = renderMusicAnalysis(data);
  } catch (error) {
    if (status) status.textContent = error.message;
  }
});

document.querySelector("#mix-review-form")?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const status = document.querySelector("#mix-review-status");
  const fileInput = document.querySelector("#mix-review-file");
  const referenceInput = document.querySelector("#mix-review-reference");
  const referenceSelect = document.querySelector("#mix-review-reference-id");
  const goalSelect = document.querySelector("#mix-review-goal");
  const phonSelect = document.querySelector("#mix-review-phon-level");
  const titleInput = document.querySelector("#mix-review-title");
  const versionInput = document.querySelector("#mix-review-version");
  const file = fileInput?.files?.[0];
  if (!file) return;
  const form = new FormData();
  form.append("file", file);
  if (referenceInput?.files?.[0]) form.append("reference", referenceInput.files[0]);
  if (referenceSelect?.value) form.append("reference_id", referenceSelect.value);
  form.append("mix_goal", goalSelect?.value || "premaster");
  form.append("phon_level", phonSelect?.value || "60");
  form.append("title", titleInput?.value || "");
  form.append("version", versionInput?.value || "");
  if (status) status.textContent = "Analysing mix…";
  try {
    const response = await fetch("/api/admin/mix-review", {
      method: "POST",
      credentials: "same-origin",
      body: form,
    });
    let data = await response.json();
    if (!response.ok || !data.ok) throw new Error(data.error || "Mix review failed.");
    
    if (data.status === "pending" || data.status === "processing") {
      const reviewId = data.id;
      let statusData = data;
      while (statusData.status === "pending" || statusData.status === "processing") {
        await new Promise(resolve => setTimeout(resolve, 1000));
        if (status) status.textContent = statusData.status === "processing" ? "Analysing audio..." : "WAV queued...";
        const pollResp = await fetch(`/api/admin/mix-review-status?id=${encodeURIComponent(reviewId)}`, { credentials: "same-origin" });
        if (!pollResp.ok) throw new Error("Status query failed.");
        statusData = await pollResp.json();
        if (!statusData.ok) throw new Error(statusData.error || "Status check failed.");
      }
      if (statusData.status === "failed") {
        throw new Error(statusData.error || "Mix analysis failed during processing.");
      }
      data = statusData;
    }

    if (status) status.textContent = "Mix review created.";
    document.querySelector("#mix-review-latest").innerHTML = renderMixReview(data.review);

    // Auto-save to KENN mix version history if session_id exists
    const sessId = localStorage.getItem("kenn_session_id") || "";
    const verLabel = versionInput?.value || data.review.version_label || "v" + (Date.now().toString().slice(-4));
    if (sessId && verLabel) {
      try {
        const metricsPayload = { ...(data.review.metrics || {}), review_id: data.review.id, filename: file.name };
        await fetch("/api/ableton/mix-version/save", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            session_id: sessId,
            version_label: verLabel,
            metrics: metricsPayload,
            repair_chain: data.review.repair_chains || {}
          })
        });
      } catch (err) {
        console.error("Failed to save mix version history:", err);
      }
    }

    await loadMixReviews();
    await loadMixVersionTimeline();
  } catch (error) {
    if (status) status.textContent = error.message;
  }
});

document.querySelector("#mix-reference-form")?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const status = document.querySelector("#mix-review-status");
  const formEl = event.currentTarget;
  const file = document.querySelector("#mix-reference-file")?.files?.[0];
  if (!file) return;
  const form = new FormData(formEl);
  if (status) status.textContent = "Saving reference…";
  try {
    const response = await fetch("/api/admin/mix-reference", {
      method: "POST",
      credentials: "same-origin",
      body: form,
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Reference save failed.");
    if (status) status.textContent = "Reference saved.";
    formEl.reset();
    await loadMixReferences();
    const select = document.querySelector("#mix-review-reference-id");
    if (select && data.reference?.id) select.value = data.reference.id;
  } catch (error) {
    if (status) status.textContent = error.message;
  }
});

document.querySelector("#mix-stems-form")?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const status = document.querySelector("#mix-review-status");
  const formEl = event.currentTarget;
  const filesInput = document.querySelector("#mix-stems-files");
  const resultsDiv = document.querySelector("#mix-stems-results");
  
  if (!filesInput || !filesInput.files || filesInput.files.length === 0) {
    if (status) status.textContent = "Please select at least one stem file.";
    return;
  }
  
  const form = new FormData();
  for (let i = 0; i < filesInput.files.length; i++) {
    form.append("files", filesInput.files[i]);
  }
  
  if (status) status.textContent = "Analyzing stems...";
  if (resultsDiv) {
    resultsDiv.style.display = "block";
    resultsDiv.innerHTML = `<p style="font-size:12px; color:var(--muted);">Analyzing uploaded stems...</p>`;
  }
  
  try {
    const response = await fetch("/api/admin/mix-stems", {
      method: "POST",
      credentials: "same-origin",
      body: form,
    });
    const data = await response.json();
    if (!response.ok || !data.ok) throw new Error(data.error || "Stems analysis failed.");
    
    if (status) status.textContent = "Stems analysis completed.";
    
    const result = data.result || {};
    const stems = result.stems || [];
    const matrix = result.masking_matrix || {};
    
    if (stems.length === 0) {
      if (resultsDiv) resultsDiv.innerHTML = `<p style="font-size:12px; color:var(--muted);">No stems processed.</p>`;
      return;
    }
    
    let html = `<h4 style="margin: 0 0 10px 0; font-size:13px; font-weight:700;">Frequency Masking Matrix</h4>`;
    
    const cellWidth = 45;
    const headerWidth = 80;
    const padding = 10;
    const N = stems.length;
    const svgWidth = headerWidth + N * cellWidth + padding;
    const svgHeight = headerWidth + N * cellWidth + padding;
    
    let svgContent = `<svg viewBox="0 0 ${svgWidth} ${svgHeight}" width="100%" height="${svgHeight}" style="overflow: visible; background: transparent;">`;
    
    svgContent += `
      <defs>
        <filter id="severe-glow" x="-20%" y="-20%" width="140%" height="140%">
          <feGaussianBlur stdDeviation="2.5" result="blur" />
          <feComposite in="SourceGraphic" in2="blur" operator="over" />
        </filter>
      </defs>
    `;
    
    stems.forEach((stem, idx) => {
      const x = headerWidth + idx * cellWidth + cellWidth / 2;
      const y = headerWidth - 10;
      svgContent += `
        <text x="${x}" y="${y}" fill="var(--muted)" font-size="10" font-weight="bold" text-anchor="start" transform="rotate(-30, ${x}, ${y})">
          ${escapeHtml(stem.name)}
        </text>
      `;
    });
    
    stems.forEach((rowStem, rowIdx) => {
      const ry = headerWidth + rowIdx * cellWidth;
      
      svgContent += `
        <text x="${headerWidth - 10}" y="${ry + cellWidth / 2 + 3}" fill="var(--muted)" font-size="10" font-weight="bold" text-anchor="end">
          ${escapeHtml(rowStem.name)}
        </text>
      `;
      
      stems.forEach((colStem, colIdx) => {
        const cx = headerWidth + colIdx * cellWidth;
        const val = matrix[rowStem.name]?.[colStem.name] ?? 0.0;
        
        let cellColor = "#3b82f6";
        let isGlow = false;
        
        if (rowStem.name === colStem.name) {
          cellColor = "rgba(255, 255, 255, 0.06)";
        } else if (val > 0.6) {
          cellColor = "#ef4444";
          isGlow = true;
        } else if (val > 0.3) {
          cellColor = "#f59e0b";
        } else {
          cellColor = "#10b981";
        }
        
        let maxOverlapVal = -1;
        let maxOverlapBand = "Sub";
        const bandsKeys = ["sub", "bass", "low_mids", "mids", "presence", "sibilance", "air"];
        const bandLabels = { sub: "Sub", bass: "Bass", low_mids: "Low Mids", mids: "Mids", presence: "Presence", sibilance: "Sibilance", air: "Air" };
        
        bandsKeys.forEach((k) => {
          const overlap = Math.min(rowStem.bands[k], colStem.bands[k]);
          if (overlap > maxOverlapVal) {
            maxOverlapVal = overlap;
            maxOverlapBand = bandLabels[k];
          }
        });
        
        const percentVal = Math.round(val * 100);
        const tooltip = rowStem.name === colStem.name 
          ? `${rowStem.name} self-correlation` 
          : `${rowStem.name} masks ${colStem.name} by ${percentVal}% in ${maxOverlapBand} range`;
        
        const filterAttr = isGlow ? `filter="url(#severe-glow)"` : "";
        const borderStyle = rowStem.name === colStem.name ? `stroke="rgba(255,255,255,0.1)" stroke-width="1"` : `stroke="#111827" stroke-width="1.5"`;
        
        svgContent += `
          <g style="cursor: pointer;">
            <rect x="${cx + 2}" y="${ry + 2}" width="${cellWidth - 4}" height="${cellWidth - 4}" rx="4" fill="${cellColor}" ${borderStyle} ${filterAttr} />
            <text x="${cx + cellWidth / 2}" y="${ry + cellWidth / 2 + 4}" fill="${rowStem.name === colStem.name ? "var(--muted)" : "#fff"}" font-size="9" font-weight="bold" text-anchor="middle">
              ${rowStem.name === colStem.name ? "—" : val.toFixed(2)}
            </text>
            <title>${tooltip}</title>
          </g>
        `;
      });
    });
    
    svgContent += `</svg>`;
    html += svgContent;
    
    html += `
      <div style="margin-top: 10px; display: flex; flex-direction: column; gap: 4px; font-size: 11px; color: var(--muted);">
        <div style="display: flex; gap: 10px; flex-wrap: wrap;">
          <span style="display: flex; align-items: center; gap: 4px;"><span style="display: inline-block; width: 8px; height: 8px; border-radius: 2px; background: #ef4444; box-shadow: 0 0 4px #ef4444;"></span> &gt; 0.60 (Severe)</span>
          <span style="display: flex; align-items: center; gap: 4px;"><span style="display: inline-block; width: 8px; height: 8px; border-radius: 2px; background: #f59e0b;"></span> 0.30 - 0.60 (Moderate)</span>
          <span style="display: flex; align-items: center; gap: 4px;"><span style="display: inline-block; width: 8px; height: 8px; border-radius: 2px; background: #10b981;"></span> &lt; 0.30 (Low/Safe)</span>
        </div>
        <p style="margin: 4px 0 0 0; line-height: 1.3;">Hover over squares to see specific masking percentages and conflict frequency ranges.</p>
      </div>
    `;
    
    // Appending ERB clarity scores and DAW carving recommendations
    if (result.erb_details) {
      const erb = result.erb_details;
      const improvements = erb.clarity_improvement || {};
      const suggestions = erb.carving_suggestions || [];
      
      html += `<div style="margin-top: 24px; border-top: 1px solid rgba(255,255,255,0.08); padding-top: 20px;">`;
      
      // Clarity Scores section
      html += `<h4 style="margin: 0 0 12px 0; font-size:13px; font-weight:700; color:var(--text); display:flex; align-items:center; gap:6px;">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path><polyline points="22 4 12 14.01 9 11.01"></polyline></svg>
        Perceptual Clarity Scores
      </h4>`;
      html += `<div style="display:flex; flex-direction:column; gap:10px; margin-bottom: 24px;">`;
      
      stems.forEach(stem => {
        const imp = improvements[stem.name] || { before: 1.0, after: 1.0 };
        const visBeforePercent = Math.round(imp.before * 100);
        const visAfterPercent = Math.round(imp.after * 100);
        const hasImprovement = visAfterPercent > visBeforePercent;
        
        let barColor = "var(--primary)";
        if (visBeforePercent < 40) barColor = "#ef4444";
        else if (visBeforePercent < 70) barColor = "#f59e0b";
        else barColor = "#10b981";
        
        html += `
          <div style="background: rgba(255,255,255,0.02); border: 1px solid rgba(255,255,255,0.04); border-radius: 6px; padding: 10px;">
            <div style="display:flex; justify-content:space-between; margin-bottom:6px; font-size:11px; font-weight:600;">
              <span style="color:var(--text);">${escapeHtml(stem.name)}</span>
              <span style="color:var(--muted);">
                Clarity: <span style="color:${barColor}; font-weight:700;">${visBeforePercent}%</span>
                ${hasImprovement ? ` &rarr; <span style="color:#10b981; font-weight:700;">${visAfterPercent}%</span> (Correction)` : ''}
              </span>
            </div>
            <div style="height: 6px; background: rgba(255,255,255,0.06); border-radius: 3px; overflow: hidden; position: relative;">
              <div style="height:100%; width: ${visBeforePercent}%; background: ${barColor}; border-radius: 3px;"></div>
              ${hasImprovement ? `<div style="height:100%; width: ${visAfterPercent - visBeforePercent}%; background: #10b981; border-radius: 3px; position: absolute; left: ${visBeforePercent}%; top: 0; opacity: 0.8;"></div>` : ''}
            </div>
          </div>
        `;
      });
      html += `</div>`;
      
      // DAW Carver recommendations
      html += `<h4 style="margin: 0 0 12px 0; font-size:13px; font-weight:700; color:var(--text); display:flex; align-items:center; gap:6px;">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="16" x2="12" y2="12"></line><line x1="12" y1="8" x2="12.01" y2="8"></line></svg>
        DAW Correction Advisor
      </h4>`;
      
      if (suggestions.length === 0) {
        html += `<p style="font-size:12px; color:var(--muted); font-style:italic;">No significant frequency masking detected. Stems are well-separated!</p>`;
      } else {
        html += `<div style="display:flex; flex-direction:column; gap:8px;">`;
        suggestions.forEach(sug => {
          let badgeColor = "rgba(59, 130, 246, 0.15)";
          let badgeTextColor = "#3b82f6";
          if (sug.type === "sidechain_compression") {
            badgeColor = "rgba(239, 68, 68, 0.15)";
            badgeTextColor = "#ef4444";
          } else if (sug.type === "dynamic_eq") {
            badgeColor = "rgba(245, 158, 11, 0.15)";
            badgeTextColor = "#f59e0b";
          }
          
          html += `
            <div style="background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.06); border-radius: 6px; padding: 12px; font-size: 11.5px; line-height: 1.4;">
              <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom: 6px;">
                <span style="font-weight:700; color:#fff; display:flex; align-items:center; gap:5px;">
                  ${escapeHtml(sug.masker)} <span style="font-weight:normal; color:var(--muted);">&rarr;</span> ${escapeHtml(sug.masked)}
                </span>
                <span style="font-size:9.5px; font-weight:700; text-transform:uppercase; padding: 2px 6px; border-radius: 4px; background: ${badgeColor}; color: ${badgeTextColor};">
                  ${sug.type.replace('_', ' ')}
                </span>
              </div>
              <p style="margin: 0 0 6px 0; color:var(--muted);">${escapeHtml(sug.description)}</p>
              <div style="background: rgba(0,0,0,0.2); border: 1px solid rgba(255,255,255,0.04); border-radius: 4px; padding: 6px 8px; font-family: monospace; font-size:10px; color:#a7f3d0; display:flex; justify-content:space-between; align-items:center;">
                <span>${escapeHtml(sug.daw_move)}</span>
                <button onclick="navigator.clipboard.writeText('${sug.daw_move.replace(/'/g, "\\'")}'); alert('Copied suggested move to clipboard!')" style="background:transparent; border:none; color:var(--muted); cursor:pointer; padding:0; display:flex; align-items:center;">
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>
                </button>
              </div>
            </div>
          `;
        });
        html += `</div>`;
      }
      html += `
        <div style="margin-top: 20px; display: flex; justify-content: flex-end;">
          <button id="btn-consult-kenn-stems" class="btn btn-primary" style="display:flex; align-items:center; gap:6px; font-size:11.5px; padding: 8px 16px; border-radius: 6px; cursor: pointer; border: none; font-weight: 600;">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="margin-right:2px;"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path></svg>
            Consult KENN about these Stems
          </button>
        </div>
      `;
      
      html += `</div>`;
    }
    
    if (resultsDiv) {
      resultsDiv.innerHTML = html;
    }
    
    const consultBtn = document.getElementById("btn-consult-kenn-stems");
    if (consultBtn) {
      consultBtn.addEventListener("click", async () => {
        const stemsSummary = stems.map(s => {
          const imp = improvements[s.name] || { before: 1.0, after: 1.0 };
          return `- ${s.name}: ${Math.round(imp.before * 100)}% clarity (improves to ${Math.round(imp.after * 100)}% after correction)`;
        }).join("\n");
        
        const sugsSummary = suggestions.map(sug => {
          return `- [${sug.type.toUpperCase()}] ${sug.masker} masks ${sug.masked} around ${sug.frequency_hz} Hz. Recommendation: ${sug.description} (${sug.daw_move})`;
        }).join("\n");
        
        const prompt = `[Stems Masking Analysis Context]
Stems analyzed:
${stemsSummary}

DAW Carving Suggestions:
${sugsSummary || "- No significant conflicts detected."}

How should I proceed to solve these masking conflicts in my mix? Explain the clarity improvements.`;
        
        showTab("ableton");
        await askAbleton(prompt);
      });
    }
  } catch (error) {
    if (status) status.textContent = error.message;
    if (resultsDiv) {
      resultsDiv.innerHTML = `<p style="font-size:12px; color:#ef4444;">Error: ${escapeHtml(error.message)}</p>`;
    }
  }
});

// Calibration target dashboard implementation
let calibrationTargets = null;

async function loadCalibrationTargets() {
  const statusEl = document.querySelector("#calibration-status");
  if (!document.querySelector("#mix-review-calibration-details")) return;
  try {
    const data = await api("/api/admin/mix-targets");
    calibrationTargets = data;
    renderCalibrationForm();
  } catch (error) {
    if (statusEl) statusEl.textContent = "Failed to load targets: " + error.message;
  }
}

function renderCalibrationForm() {
  const goalSelect = document.querySelector("#calibration-goal-select");
  const summaryInput = document.querySelector("#calibration-goal-summary");
  const checksContainer = document.querySelector("#calibration-checks-container");
  
  if (!goalSelect || !summaryInput || !checksContainer || !calibrationTargets) return;
  
  const goalKey = goalSelect.value;
  const goalData = calibrationTargets.goals?.[goalKey] || { summary: "", checks: [] };
  
  summaryInput.value = goalData.summary || "";
  
  // Render checks
  if (!goalData.checks || !goalData.checks.length) {
    checksContainer.innerHTML = "<p class='compact-status' style='margin:0;'>No checks defined for this goal.</p>";
    return;
  }
  
  checksContainer.innerHTML = goalData.checks.map((check, index) => {
    const pathStr = Array.isArray(check.path) ? check.path.join(".") : (check.path || "");
    const metricOrPath = pathStr || check.metric || "";
    
    return `
      <div class="calibration-check-card" data-index="${index}" style="border: 1px solid var(--line); border-radius: 6px; padding: 12px; background: var(--panel); display: grid; gap: 8px;">
        <div style="display: flex; justify-content: space-between; align-items: center;">
          <strong style="font-size: 13px;">Check #${index + 1}</strong>
          <button type="button" class="button secondary calibration-remove-check-btn" data-index="${index}" style="min-height: 28px; height: 28px; padding: 0 8px; font-size: 11px; border-color: #f87171; color: #ef4444; background: none;">Remove</button>
        </div>
        
        <div style="display: grid; grid-template-columns: 1fr; gap: 8px;">
          <label style="font-size: 12px;">Label:
            <input type="text" class="cal-check-label" value="${escapeHtml(check.label || "")}" placeholder="e.g. Peak headroom">
          </label>
        </div>
        
        <div style="display: grid; grid-template-columns: 1fr; gap: 8px;">
          <label style="font-size: 12px;">Metric or Nested Path:
            <input type="text" class="cal-check-value" value="${escapeHtml(metricOrPath)}" placeholder="e.g. peak_dbfs or tonal_balance.low_end_share">
          </label>
        </div>
        
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px;">
          <label style="font-size: 12px;">Min (optional):
            <input type="number" step="any" class="cal-check-min" value="${check.min !== undefined && check.min !== null ? check.min : ""}" placeholder="None">
          </label>
          <label style="font-size: 12px;">Max (optional):
            <input type="number" step="any" class="cal-check-max" value="${check.max !== undefined && check.max !== null ? check.max : ""}" placeholder="None">
          </label>
        </div>
        
        <label style="font-size: 12px;">Target Message:
          <input type="text" class="cal-check-target" value="${escapeHtml(check.target || "")}" placeholder="e.g. Peak at or below -1 dBFS">
        </label>
        
        <label style="font-size: 12px;">Education Explanation:
          <textarea class="cal-check-education" rows="2" placeholder="Explain the rationale behind this check">${escapeHtml(check.education || "")}</textarea>
        </label>
      </div>
    `;
  }).join("");
}

function saveCurrentGoalToMemory() {
  const goalSelect = document.querySelector("#calibration-goal-select");
  const summaryInput = document.querySelector("#calibration-goal-summary");
  const checksContainer = document.querySelector("#calibration-checks-container");
  
  if (!goalSelect || !summaryInput || !calibrationTargets) return;
  
  const goalKey = goalSelect.value;
  if (!calibrationTargets.goals) calibrationTargets.goals = {};
  if (!calibrationTargets.goals[goalKey]) {
    calibrationTargets.goals[goalKey] = { summary: "", checks: [] };
  }
  
  calibrationTargets.goals[goalKey].summary = summaryInput.value;
  
  const checkCards = checksContainer.querySelectorAll(".calibration-check-card");
  const checks = [];
  checkCards.forEach((card) => {
    const label = card.querySelector(".cal-check-label").value.trim();
    const val = card.querySelector(".cal-check-value").value.trim();
    const minVal = card.querySelector(".cal-check-min").value.trim();
    const maxVal = card.querySelector(".cal-check-max").value.trim();
    const target = card.querySelector(".cal-check-target").value.trim();
    const education = card.querySelector(".cal-check-education").value.trim();
    
    const checkObj = { label, target, education };
    
    if (val.includes(".")) {
      checkObj.path = val.split(".").map(s => s.trim()).filter(Boolean);
    } else if (val) {
      checkObj.metric = val;
    }
    
    if (minVal !== "") {
      checkObj.min = parseFloat(minVal);
    }
    if (maxVal !== "") {
      checkObj.max = parseFloat(maxVal);
    }
    
    checks.push(checkObj);
  });
  
  calibrationTargets.goals[goalKey].checks = checks;
}

// Attach event listeners immediately
document.querySelector("#calibration-goal-select")?.addEventListener("change", () => {
  saveCurrentGoalToMemory();
  renderCalibrationForm();
});

document.querySelector("#calibration-add-check-btn")?.addEventListener("click", () => {
  saveCurrentGoalToMemory();
  const goalSelect = document.querySelector("#calibration-goal-select");
  if (!goalSelect || !calibrationTargets) return;
  const goalKey = goalSelect.value;
  if (!calibrationTargets.goals[goalKey]) {
    calibrationTargets.goals[goalKey] = { summary: "", checks: [] };
  }
  calibrationTargets.goals[goalKey].checks.push({
    label: "",
    metric: "",
    target: "",
    education: ""
  });
  renderCalibrationForm();
});

document.querySelector("#calibration-checks-container")?.addEventListener("click", (event) => {
  if (event.target.classList.contains("calibration-remove-check-btn")) {
    saveCurrentGoalToMemory();
    const index = parseInt(event.target.dataset.index, 10);
    const goalSelect = document.querySelector("#calibration-goal-select");
    if (!goalSelect || !calibrationTargets) return;
    const goalKey = goalSelect.value;
    calibrationTargets.goals[goalKey].checks.splice(index, 1);
    renderCalibrationForm();
  }
});

async function saveCalibration() {
  const statusEl = document.querySelector("#calibration-status");
  if (!statusEl || !calibrationTargets) return;
  saveCurrentGoalToMemory();
  statusEl.textContent = "Saving calibration...";
  try {
    const response = await fetch("/api/admin/mix-targets", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      body: JSON.stringify(calibrationTargets)
    });
    const data = await response.json();
    if (!response.ok || !data.ok) {
      throw new Error(data.error || "Failed to save calibration.");
    }
    statusEl.textContent = "Calibration saved successfully!";
    await loadCalibrationTargets();
  } catch (error) {
    statusEl.textContent = error.message;
  }
}

document.querySelector("#calibration-save-btn")?.addEventListener("click", saveCalibration);

function readinessClass(value) {
  const state = String(value || "").toLowerCase();
  if (state === "ready") return "ok";
  if (state === "blocked") return "warn";
  return "";
}

function renderClientIntake(ops) {
  const items = ops?.intake || [];
  if (!items.length) return "<p class='compact-status'>No new enquiries waiting.</p>";
  return `<div class="ops-list">${items.slice(0, 5).map((item) => `
    <article class="ops-item">
      <div>
        <strong>${escapeHtml(item.name || "Enquiry")}</strong>
        <p>${escapeHtml(item.service || "Audio service")}${item.deadline ? ` · ${escapeHtml(item.deadline)}` : ""}</p>
        <p class="compact-status">${escapeHtml(item.next_action || "")}</p>
        ${item.missing?.length ? `<p class="compact-status">Missing: ${escapeHtml(item.missing.join(", "))}</p>` : ""}
      </div>
      <div class="gap-actions">
        <span class="status-pill ${readinessClass(item.readiness)}">${escapeHtml(item.readiness || "review")}</span>
        <button type="button" data-draft-enquiry="${escapeHtml(item.id || "")}">Draft reply</button>
        <button type="button" class="secondary" data-convert-enquiry="${escapeHtml(item.id || "")}">Convert</button>
      </div>
    </article>`).join("")}</div>`;
}

function renderProjectReadiness(ops) {
  const items = ops?.readiness || [];
  if (!items.length) return "<p class='compact-status'>No active projects to review.</p>";
  return `<div class="ops-list">${items.slice(0, 6).map((item) => {
    const issues = [...(item.blockers || []), ...(item.missing || []).map((field) => `missing ${field}`)];
    return `<article class="ops-item">
      <div>
        <strong>${escapeHtml(item.project || "Project")}</strong>
        <p>${escapeHtml(item.client || "No client")} · ${escapeHtml(item.service || "No service")}</p>
        <p class="compact-status">${escapeHtml(item.next_action || "")}</p>
        ${issues.length ? `<p class="compact-status">Issues: ${escapeHtml(issues.join(", "))}</p>` : ""}
      </div>
      <div class="gap-actions">
        <span class="status-pill ${readinessClass(item.readiness)}">${escapeHtml(item.readiness || "review")}</span>
        <span class="status-pill">${escapeHtml(item.deadline_state || "deadline")}</span>
      </div>
    </article>`;
  }).join("")}</div>`;
}

function wireClientOps(root) {
  root?.querySelectorAll("[data-draft-enquiry]").forEach((button) => {
    button.addEventListener("click", async () => {
      const id = button.dataset.draftEnquiry || "";
      if (!id) return;
      button.disabled = true;
      try {
        const result = await api("/api/admin/enquiries/draft-reply", {
          method: "POST",
          body: JSON.stringify({ id }),
        });
        statusEl.textContent = result.message || "Draft reply created.";
        await loadAdmin();
        await loadHub();
      } catch (error) {
        statusEl.textContent = error.message;
        button.disabled = false;
      }
    });
  });
}


const transcriptList = document.querySelector("#transcript-list");
const transcriptContent = document.querySelector("#transcript-content");
const transcriptTitle = document.querySelector("#transcript-editor-title");
const transcriptSave = document.querySelector("#transcript-save");
const transcriptApprove = document.querySelector("#transcript-approve");
const transcriptBuild = document.querySelector("#transcript-build");
const transcriptBuildOutput = document.querySelector("#transcript-build-output");
const transcriptPolishLlm = document.querySelector("#transcript-polish-llm");
const paraphraseLlmCheckbox = document.querySelector("#paraphrase-llm");
const transcriptLlmStatus = document.querySelector("#transcript-llm-status");

let llmReadyForTranscripts = false;

function paraphraseLlmPayload() {
  return paraphraseLlmCheckbox?.checked ? "yes" : "";
}

async function loadTranscriptLlmStatus() {
  if (!transcriptLlmStatus) return;
  try {
    const data = await api("/api/ableton/llm-status");
    llmReadyForTranscripts = Boolean(data.ready);
    const cls = data.ready ? "ok" : "warn";
    transcriptLlmStatus.innerHTML = `<span class="status-pill ${cls}">${escapeHtml(data.message || "LLM status unknown")}</span>`;
    if (paraphraseLlmCheckbox) {
      paraphraseLlmCheckbox.disabled = !data.enabled;
      if (data.ready) paraphraseLlmCheckbox.checked = true;
    }
    if (transcriptPolishLlm) {
      transcriptPolishLlm.disabled = !selectedNote || !llmReadyForTranscripts;
    }
  } catch (error) {
    transcriptLlmStatus.textContent = error.message;
    llmReadyForTranscripts = false;
  }
}

async function loadTranscripts() {
  try {
    const data = await api("/api/ableton/transcripts");
    if (!data.items.length) {
      transcriptList.innerHTML = "<li>No transcript drafts yet.</li>";
      return;
    }
    transcriptList.innerHTML = data.items
      .map((item) => {
        const note = item.note || "";
        const disabled = note ? "" : ' class="muted"';
        return `<li${disabled}><button type="button" class="transcript-item" data-note="${escapeHtml(note)}" data-title="${escapeHtml(item.title)}" ${note ? "" : "disabled"}>${escapeHtml(item.title)}<span>${escapeHtml(item.status)}</span></button></li>`;
      })
      .join("");
    transcriptList.querySelectorAll(".transcript-item").forEach((button) => {
      button.addEventListener("click", () => openNote(button.dataset.note, button.dataset.title));
    });
  } catch (error) {
    transcriptList.innerHTML = `<li>${escapeHtml(error.message)}</li>`;
  }
}

async function openNote(name, title) {
  selectedNote = name;
  transcriptSave.disabled = false;
  transcriptApprove.disabled = false;
  transcriptContent.disabled = false;
  if (transcriptPolishLlm) transcriptPolishLlm.disabled = !llmReadyForTranscripts;
  transcriptTitle.textContent = title || name;
  try {
    const data = await api(`/api/ableton/note?name=${encodeURIComponent(name)}`);
    transcriptContent.value = data.content;
    statusEl.textContent = `Editing ${data.name} (${data.status})`;
  } catch (error) {
    statusEl.textContent = error.message;
  }
}

transcriptSave.addEventListener("click", async () => {
  if (!selectedNote) return;
  try {
    await api("/api/ableton/note", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: selectedNote, content: transcriptContent.value }),
    });
    statusEl.textContent = `Saved ${selectedNote}`;
    await loadTranscripts();
    await loadActivity();
  } catch (error) {
    statusEl.textContent = error.message;
  }
});

transcriptPolishLlm?.addEventListener("click", async () => {
  if (!selectedNote) return;
  transcriptPolishLlm.disabled = true;
  statusEl.textContent = "Polishing note with LLM…";
  try {
    const data = await api("/api/ableton/note/polish", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: selectedNote }),
    });
    if (data.content) transcriptContent.value = data.content;
    statusEl.textContent = data.message || "Note polished.";
    await loadTranscripts();
    await loadActivity();
  } catch (error) {
    statusEl.textContent = error.message;
  } finally {
    transcriptPolishLlm.disabled = !llmReadyForTranscripts || !selectedNote;
  }
});

transcriptApprove.addEventListener("click", async () => {
  if (!selectedNote) return;
  try {
    await api("/api/ableton/approve", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: selectedNote }),
    });
    statusEl.textContent = `Approved ${selectedNote}. Rebuild the index when ready.`;
    await loadTranscripts();
    await loadActivity();
  } catch (error) {
    statusEl.textContent = error.message;
  }
});

transcriptBuild.addEventListener("click", async () => {
  transcriptBuildOutput.textContent = "Building index…";
  try {
    const data = await api("/api/ableton/build", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
    transcriptBuildOutput.textContent = data.output || (data.ok ? "Done." : "Build failed.");
    statusEl.textContent = data.ok ? "Index rebuilt." : "Index build failed — see output below.";
    await loadActivity();
  } catch (error) {
    transcriptBuildOutput.textContent = error.message;
  }
});

document.querySelector("#transcripts-refresh")?.addEventListener("click", loadTranscripts);

const paraphraseForm = document.querySelector("#paraphrase-form");
const paraphraseStatus = document.querySelector("#paraphrase-status");

const webFetchForm = document.querySelector("#web-fetch-form");
const webFetchStatus = document.querySelector("#web-fetch-status");

webFetchForm?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const url = document.querySelector("#web-fetch-url")?.value.trim() || "";
  const title = document.querySelector("#web-fetch-title")?.value.trim() || "";
  const tags = document.querySelector("#web-fetch-tags")?.value.trim() || "";
  if (!url) return;
  webFetchStatus.textContent = "Fetching page (robots.txt checked)…";
  try {
    const data = await api("/api/ableton/fetch-web", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url, title, tags }),
    });
    webFetchStatus.textContent = data.message || "Done.";
    await loadTranscripts();
    await loadActivity();
  } catch (error) {
    webFetchStatus.textContent = error.message;
  }
});

async function importWebPack(suggested = false) {
  webFetchStatus.textContent = suggested
    ? "Importing suggested Ableton URLs (may take a minute)…"
    : "Importing curated web_sources.json (may take a minute)…";
  try {
    const data = await api("/api/ableton/import-web-pack", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ limit: 6, suggested: suggested ? "yes" : "" }),
    });
    webFetchStatus.textContent = data.message || "Done.";
    await loadTranscripts();
    await loadActivity();
  } catch (error) {
    webFetchStatus.textContent = error.message;
  }
}

document.querySelector("#import-web-pack")?.addEventListener("click", () => importWebPack(false));
document.querySelector("#import-web-suggested")?.addEventListener("click", () => importWebPack(true));

document.querySelector("#train-chatbot")?.addEventListener("click", async () => {
  if (!confirm("Paraphrase all local transcripts with the improved engine, approve them, and rebuild the index? Review quality in Transcript Review first if unsure.")) {
    return;
  }
  webFetchStatus.textContent = "Training: paraphrase → approve → build…";
  try {
    const data = await api("/api/ableton/train-chatbot", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        force: "yes",
        approve: "yes",
        build: "yes",
        llm: paraphraseLlmPayload(),
      }),
    });
    webFetchStatus.textContent = data.message || "Done.";
    await loadTranscripts();
    await loadActivity();
  } catch (error) {
    webFetchStatus.textContent = error.message;
  }
});

paraphraseForm?.addEventListener("submit", async (event) => {
  event.preventDefault();
  paraphraseStatus.textContent = "Generating draft notes from transcripts…";
  const creator = document.querySelector("#paraphrase-creator")?.value.trim() || "";
  const tags = document.querySelector("#paraphrase-tags")?.value.trim() || "";
  const force = document.querySelector("#paraphrase-force")?.checked || false;
  try {
    const data = await api("/api/ableton/paraphrase-all", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        creator,
        tags,
        force: force ? "yes" : "",
        llm: paraphraseLlmPayload(),
      }),
    });
    paraphraseStatus.textContent = data.message || "Done.";
    await loadTranscripts();
    await loadActivity();
  } catch (error) {
    paraphraseStatus.textContent = error.message;
  }
});

const abletonWebStatus = document.querySelector("#ableton-web-status");

async function checkAbletonWeb() {
  // Deliberately does not repoint the iframe/"open in new tab" link at
  // data.url (the raw 127.0.0.1:8090 KENN port) — both stay on the proxied
  // /kenn path (kenn_proxy_routes.py) so the browser never talks to the
  // engine directly. See docs/KENN_HUB_UNIFICATION_PLAN_2026-08-05.md.
  if (!abletonWebStatus) return;
  abletonWebStatus.textContent = "Checking KENN…";
  try {
    const data = await api("/api/ableton/web-health");
    abletonWebStatus.textContent = data.running
      ? "KENN is running."
      : (data.hint || "Start ./ableton web in a terminal, then refresh this tab.");
  } catch (error) {
    abletonWebStatus.textContent = error.message;
  }
}

const abletonConversation = [];

const abletonForm = document.querySelector("#ableton-ask-form");
const abletonAnswer = document.querySelector("#ableton-answer");
const abletonSources = document.querySelector("#ableton-sources");
const abletonQuestion = document.querySelector("#ableton-question");
const abletonTypeahead = document.querySelector("#ableton-typeahead");
let abletonSuggestTimer = null;

function hideAbletonTypeahead() {
  if (!abletonTypeahead) return;
  abletonTypeahead.hidden = true;
  abletonTypeahead.innerHTML = "";
}

function showAbletonTypeahead(items) {
  if (!abletonTypeahead) return;
  if (!items?.length) {
    hideAbletonTypeahead();
    return;
  }
  abletonTypeahead.innerHTML = items
    .map(
      (q) =>
        `<li><button type="button" data-suggest="${escapeHtml(q)}">${escapeHtml(q)}</button></li>`,
    )
    .join("");
  abletonTypeahead.hidden = false;
  abletonTypeahead.querySelectorAll("button").forEach((button) => {
    button.addEventListener("click", () => {
      const q = button.dataset.suggest || "";
      if (abletonQuestion) abletonQuestion.value = q;
      hideAbletonTypeahead();
      if (q) askAbleton(q);
    });
  });
}

function scheduleAbletonTypeahead() {
  const query = abletonQuestion?.value?.trim() || "";
  clearTimeout(abletonSuggestTimer);
  if (query.length < 2) {
    hideAbletonTypeahead();
    return;
  }
  abletonSuggestTimer = setTimeout(async () => {
    try {
      const params = new URLSearchParams({ q: query, limit: "8" });
      const data = await api(`/api/ableton/suggest?${params}`);
      showAbletonTypeahead(data.suggestions);
    } catch {
      hideAbletonTypeahead();
    }
  }, 220);
}

abletonQuestion?.addEventListener("input", scheduleAbletonTypeahead);
abletonQuestion?.addEventListener("focus", scheduleAbletonTypeahead);
abletonQuestion?.addEventListener("keydown", (event) => {
  if (event.key === "Escape") hideAbletonTypeahead();
});
document.addEventListener("click", (event) => {
  if (!event.target.closest(".composer-field")) hideAbletonTypeahead();
});

async function askAbleton(question, extraHistory = []) {
  hideAbletonTypeahead();
  if (!question) return;
  abletonAnswer.textContent = "Thinking…";
  abletonSources.innerHTML = "";
  const followupsEl = document.querySelector("#ableton-followups");
  if (followupsEl) followupsEl.innerHTML = "";
  try {
    const requestHistory = [
      ...abletonConversation.slice(-4),
      ...(Array.isArray(extraHistory) ? extraHistory : []),
    ];
    const data = await api("/api/ableton/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, limit: 8, history: requestHistory, session_id: localStorage.getItem("kenn_session_id") || "" }),
    });
    lastAbletonPayload = data;
    // Save session_id from response for continuity
    if (data.session?.session_id) {
      localStorage.setItem("kenn_session_id", data.session.session_id);
    }
    abletonConversation.push({ role: "user", content: question });
    if (data.answer) abletonConversation.push({ role: "assistant", content: data.answer });
    const sourceQuality = data.source_quality ? ` · Sources: ${escapeHtml(data.source_quality)}` : "";
    const conf = data.confidence ? `<p class="compact-status">Confidence: ${escapeHtml(data.confidence)}${sourceQuality}${data.llm_enhanced ? " · LLM enhanced" : ""}</p>` : "";
    const historyNote = data.used_history ? `<p class="compact-status">Using recent conversation context</p>` : "";
    abletonAnswer.innerHTML = `${conf}${historyNote}<pre class="ableton-answer-text">${escapeHtml(data.answer || "No answer.")}</pre>
      ${data.branches?.length ? `<div class="branch-buttons">
        <p class="branch-question">${escapeHtml(data.branches[0].text)}</p>
        <button type="button" class="branch-btn branch-yes" data-branch-followup="${escapeHtml(data.branches[0].yes)}">Yes</button>
        <button type="button" class="branch-btn branch-no" data-branch-followup="${escapeHtml(data.branches[0].no)}">No</button>
      </div>` : ""}
      ${data.conversation_only ? "" : `<form class="demo-feedback dashboard-feedback" id="ableton-feedback-form">
        <input name="comment" placeholder="Optional note: what was wrong or missing?">
        <button type="button" data-ableton-rating="useful">Useful</button>
        <button type="button" class="secondary" data-ableton-rating="not_useful">Needs work</button>
      </form>`}`;
    document.querySelectorAll("[data-ableton-rating]").forEach((button) => {
      button.addEventListener("click", () => sendAbletonFeedback(button));
    });
    // Branch button handlers
    document.querySelectorAll("[data-branch-followup]").forEach((button) => {
      button.addEventListener("click", () => {
        const followup = button.dataset.branchFollowup;
        if (followup) askAbleton(followup);
      });
    });
    if (data.sources?.length) {
      abletonSources.innerHTML = `<h3>Sources</h3><ul>${data.sources.map((source) => `<li>${escapeHtml(source.title || source.source || "source")}</li>`).join("")}</ul>`;
    }
    if (followupsEl && data.related_questions?.length) {
      followupsEl.innerHTML = `<p class="compact-status">Suggested follow-ups (click to ask):</p><div class="ableton-followups-row">${data.related_questions
        .map((q) => `<button type="button" class="ableton-followup" data-question="${escapeHtml(q)}">${escapeHtml(q)}</button>`)
        .join("")}</div>`;
      followupsEl.querySelectorAll(".ableton-followup").forEach((button) => {
        button.addEventListener("click", () => askAbleton(button.dataset.question));
      });
    }
  } catch (error) {
    abletonAnswer.textContent = error.message;
  }
}

async function sendAbletonFeedback(button) {
  const payload = lastAbletonPayload;
  if (!payload) return;
  const form = button.closest("#ableton-feedback-form");
  const comment = form?.querySelector("input")?.value || "";
  button.disabled = true;
  try {
    await api("/api/ableton/feedback", {
      method: "POST",
      body: JSON.stringify({
        question: payload.question,
        rating: button.dataset.abletonRating,
        comment,
        answer: payload.answer,
        sources: payload.sources || [],
        topics: payload.topics || [],
        confidence: payload.confidence,
        source_quality: payload.source_quality,
      }),
    });
    statusEl.textContent = button.dataset.abletonRating === "not_useful"
      ? "Feedback saved to the LLM repair queue."
      : "Feedback saved.";
    form?.classList.add("feedback-saved");
    form?.querySelectorAll("button").forEach((item) => {
      item.disabled = true;
    });
  } catch (error) {
    statusEl.textContent = error.message;
    button.disabled = false;
  }
}

abletonForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const question = abletonQuestion.value.trim();
  if (!question) return;
  await askAbleton(question);
  abletonQuestion.value = "";
});
