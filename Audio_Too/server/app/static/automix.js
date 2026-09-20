/**
 * Client-side controller for the Audio_Too Automix Engine.
 */

(function () {
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

  async function fetch(input, options = {}) {
    const method = String(options.method || "GET").toUpperCase();
    const headers = new Headers(options.headers || {});
    if (!["GET", "HEAD", "OPTIONS"].includes(method)) {
      await ensureCsrfToken();
      if (csrfToken) headers.set("X-CSRF-Token", csrfToken);
    }
    return browserFetch(input, { ...options, credentials: "same-origin", headers });
  }

  function idempotencyKey(prefix) {
    const random = globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(16).slice(2)}`;
    return `${prefix}:${random}`;
  }

  // DOM Elements
  const projectIdInput = document.getElementById("projectId");
  const btnGenId = document.getElementById("btnGenId");
  const genreSelect = document.getElementById("genreSelect");
  const targetLufsSelect = document.getElementById("targetLufsSelect");
  const sliderBrightWarm = document.getElementById("sliderBrightWarm");
  const sliderDynamic = document.getElementById("sliderDynamic");
  const sliderSpatial = document.getElementById("sliderSpatial");
  const sliderWidth = document.getElementById("sliderWidth");
  const chkMaskingCorrections = document.getElementById("chkMaskingCorrections");
  const chkMonoCompatCorrection = document.getElementById("chkMonoCompatCorrection");
  const chkProactiveCrestReduction = document.getElementById("chkProactiveCrestReduction");

  const uploadZone = document.getElementById("uploadZone");
  const fileInput = document.getElementById("fileInput");
  const fileList = document.getElementById("fileList");
  const btnStartMix = document.getElementById("btnStartMix");
  
  const statusBadge = document.getElementById("statusBadge");
  const progressBar = document.getElementById("progressBar");
  const consoleBody = document.getElementById("consoleBody");
  
  const resultsCard = document.getElementById("resultsCard");
  const audioPreview = document.getElementById("audioPreview");
  const btnDownload = document.getElementById("btnDownload");
  const btnViewReport = document.getElementById("btnViewReport");
  const btnViewMatchReport = document.getElementById("btnViewMatchReport");
  const btnViewDecisions = document.getElementById("btnViewDecisions");
  const advisorReview = document.getElementById("advisorReview");
  const advisorReviewOperations = document.getElementById("advisorReviewOperations");
  
  const refUploadZone = document.getElementById("refUploadZone");
  const refFileInput = document.getElementById("refFileInput");
  const refFileList = document.getElementById("refFileList");
  
  const feedbackInput = document.getElementById("feedbackInput");
  const btnSubmitRevision = document.getElementById("btnSubmitRevision");

  // State
  let files = [];
  let referenceFile = null;
  let jobId = null;
  let pollInterval = null;
  let lastStatus = null;

  // Initialize
  btnGenId.addEventListener("click", generateRandomId);
  
  // Drag & drop listeners for stems
  uploadZone.addEventListener("click", () => fileInput.click());
  fileInput.addEventListener("change", handleFileSelect);
  
  uploadZone.addEventListener("dragover", (e) => {
    e.preventDefault();
    uploadZone.classList.add("dragging");
  });
  
  uploadZone.addEventListener("dragenter", (e) => {
    e.preventDefault();
    uploadZone.classList.add("dragging");
  });
  
  uploadZone.addEventListener("dragleave", () => {
    uploadZone.classList.remove("dragging");
  });
  
  uploadZone.addEventListener("drop", (e) => {
    e.preventDefault();
    uploadZone.classList.remove("dragging");
    if (e.dataTransfer.files.length > 0) {
      files = Array.from(e.dataTransfer.files);
      updateFileList();
    }
  });

  // Drag & drop listeners for reference track
  refUploadZone.addEventListener("click", () => refFileInput.click());
  refFileInput.addEventListener("change", handleRefFileSelect);
  
  refUploadZone.addEventListener("dragover", (e) => {
    e.preventDefault();
    refUploadZone.classList.add("dragging");
  });
  
  refUploadZone.addEventListener("dragenter", (e) => {
    e.preventDefault();
    refUploadZone.classList.add("dragging");
  });
  
  refUploadZone.addEventListener("dragleave", () => {
    refUploadZone.classList.remove("dragging");
  });
  
  refUploadZone.addEventListener("drop", (e) => {
    e.preventDefault();
    refUploadZone.classList.remove("dragging");
    if (e.dataTransfer.files.length > 0) {
      referenceFile = e.dataTransfer.files[0];
      updateRefFileList();
    }
  });

  projectIdInput.addEventListener("input", validateForm);
  btnStartMix.addEventListener("click", startMixdownProcess);
  btnSubmitRevision.addEventListener("click", submitRevisionProcess);
  // M8.5: KENN NL intent parsing
  document.getElementById("btnNlAdjust")?.addEventListener("click", async () => {
    const input = document.getElementById("nlAdjustInput");
    const resultEl = document.getElementById("nlAdjustResult");
    if (!input || !resultEl) return;
    const instruction = input.value.trim();
    if (!instruction) { resultEl.textContent = "Type an instruction first."; return; }
    resultEl.textContent = "Parsing…";
    try {
      const res = await fetch("/api/automix/nl-adjust", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({project_id: projectIdInput.value.trim() || "demo", instruction}),
      });
      const data = await res.json();
      if (data.ok) {
        resultEl.textContent = data.description || JSON.stringify(data.intent);
      } else {
        resultEl.textContent = "Error: " + (data.error || "Unknown error");
      }
    } catch (e) {
      resultEl.textContent = "Failed: " + e.message;
    }
  });

  // KENN render explainability: "why did you do that", grounded in this
  // project's latest render manifest (decisions_log/quality_gate).
  document.getElementById("btnKennExplain")?.addEventListener("click", async () => {
    const input = document.getElementById("kennExplainInput");
    const resultEl = document.getElementById("kennExplainResult");
    if (!input || !resultEl) return;
    const question = input.value.trim();
    if (!question) { resultEl.textContent = "Ask a question first."; return; }
    const projectId = projectIdInput.value.trim();
    if (!projectId) { resultEl.textContent = "Enter a project ID first."; return; }
    resultEl.textContent = "Asking KENN…";
    try {
      const res = await fetch("/api/automix/explain", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({project_id: projectId, question}),
      });
      const data = await res.json();
      if (data.ok) {
        const groundedNote = data.grounded
          ? ""
          : "\n\n(No completed render found for this project yet — answered generically.)";
        resultEl.textContent = (data.answer || "").trim() + groundedNote;
      } else {
        resultEl.textContent = "Error: " + (data.error || "Unknown error");
      }
    } catch (e) {
      resultEl.textContent = "Failed: " + e.message;
    }
  });

  // 1. Generate Random ID
  function generateRandomId() {
    const chars = "abcdefghijklmnopqrstuvwxyz0123456789";
    let rand = "mix_";
    for (let i = 0; i < 6; i++) {
      rand += chars.charAt(Math.floor(Math.random() * chars.length));
    }
    projectIdInput.value = rand;
    log(`Generated new project ID: '${rand}'`, "system");
    validateForm();
  }

  // 2. Handle file selection
  function handleFileSelect(e) {
    if (e.target.files.length > 0) {
      files = Array.from(e.target.files);
      updateFileList();
    }
  }

  // Handle reference file selection
  function handleRefFileSelect(e) {
    if (e.target.files.length > 0) {
      referenceFile = e.target.files[0];
      updateRefFileList();
    }
  }

  function updateRefFileList() {
    refFileList.innerHTML = "";
    if (referenceFile) {
      const item = document.createElement("div");
      item.className = "file-item";
      item.innerHTML = `
        <span>🎵 ${referenceFile.name}</span>
        <span>${formatBytes(referenceFile.size)}</span>
      `;
      refFileList.appendChild(item);
      log(`Selected reference track: ${referenceFile.name}`, "system");
    }
  }

  // 3. Format byte size
  function formatBytes(bytes) {
    if (bytes === 0) return "0 Bytes";
    const k = 1024;
    const sizes = ["Bytes", "KB", "MB", "GB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + " " + sizes[i];
  }

  // 4. Update file list UI
  function updateFileList() {
    fileList.innerHTML = "";
    files.forEach((file) => {
      const item = document.createElement("div");
      item.className = "file-item";
      item.innerHTML = `
        <span>📄 ${file.name}</span>
        <span>${formatBytes(file.size)}</span>
      `;
      fileList.appendChild(item);
    });
    
    if (files.length > 0) {
      log(`Selected ${files.length} stem file(s) for mixing.`, "system");
    }
    validateForm();
  }

  // 5. Validate form state
  function validateForm() {
    const hasId = projectIdInput.value.trim().length > 0;
    const hasFiles = files.length > 0;
    btnStartMix.disabled = !(hasId && hasFiles);
  }

  // 6. Log to custom console body
  function log(message, type = "") {
    const line = document.createElement("div");
    line.className = "console-line";
    
    const timeSpan = document.createElement("span");
    timeSpan.className = "console-line timestamp";
    const now = new Date();
    timeSpan.textContent = `[${now.toTimeString().split(" ")[0]}]`;
    
    const textSpan = document.createElement("span");
    if (type) textSpan.className = `console-line ${type}`;
    textSpan.textContent = message;
    
    line.appendChild(timeSpan);
    line.appendChild(textSpan);
    consoleBody.appendChild(line);
    
    // Auto scroll to bottom
    consoleBody.scrollTop = consoleBody.scrollHeight;
  }

  // 7. Start Mixdown process
  async function startMixdownProcess() {
    const projectId = projectIdInput.value.trim();
    if (!projectId || files.length === 0) return;

    // Disable UI
    btnStartMix.disabled = true;
    projectIdInput.disabled = true;
    btnGenId.disabled = true;
    genreSelect.disabled = true;
    sliderBrightWarm.disabled = true;
    sliderDynamic.disabled = true;
    sliderSpatial.disabled = true;
    sliderWidth.disabled = true;
    uploadZone.style.pointerEvents = "none";
    
    resultsCard.style.display = "none";
    updateProgress(0, "queued");

    try {
      // Step A: Upload optional reference track
      if (referenceFile) {
        log(`Uploading reference track: ${referenceFile.name}...`, "system");
        const refFormData = new FormData();
        refFormData.append("project_id", projectId);
        refFormData.append("file", referenceFile);
        
        const refUploadRes = await fetch("/api/automix/reference/upload", {
          method: "POST",
          body: refFormData
        });
        const refUploadData = await refUploadRes.json();
        
        if (!refUploadRes.ok || !refUploadData.ok) {
          throw new Error(refUploadData.error || "Reference track upload failed.");
        }
        log("Reference track uploaded successfully! EQ matching enabled.", "success");
      }

      // Step B: Upload stems sequentially
      log("Initializing stem upload sequence...", "system");
      for (let i = 0; i < files.length; i++) {
        const file = files[i];
        log(`Uploading [${i + 1}/${files.length}] ${file.name} (${formatBytes(file.size)})...`);
        
        const formData = new FormData();
        formData.append("project_id", projectId);
        formData.append("file", file);
        formData.append("email", ""); // Optional
        
        const uploadRes = await fetch("/api/v1/automix/uploads", {
          method: "POST",
          headers: { "Idempotency-Key": idempotencyKey(`automix-upload-${i + 1}`) },
          body: formData
        });
        const uploadData = await uploadRes.json();
        
        if (!uploadRes.ok || !uploadData.ok) {
          throw new Error(uploadData.error || `Upload failed for ${file.name}`);
        }
      }
      log("All audio stems uploaded successfully! Glueing workspace...", "success");

      // Step B: Trigger Mix job on backend
      log("Starting Automix decision engine on server...", "system");
      const prefs = {
        bright_warm: parseFloat(sliderBrightWarm.value),
        compressed_dynamic: parseFloat(sliderDynamic.value),
        dry_wet: parseFloat(sliderSpatial.value),
        narrow_wide: parseFloat(sliderWidth.value),
        masking_corrections: chkMaskingCorrections ? chkMaskingCorrections.checked : false,
        mono_compat_correction: chkMonoCompatCorrection ? chkMonoCompatCorrection.checked : false,
        proactive_crest_reduction: chkProactiveCrestReduction ? chkProactiveCrestReduction.checked : false
      };

      const startRes = await fetch("/api/v1/automix/jobs", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Idempotency-Key": idempotencyKey("automix-job")
        },
        body: JSON.stringify({
          project_id: projectId,
          genre: genreSelect.value,
          style_prefs: prefs,
          target_lufs: targetLufsSelect ? parseFloat(targetLufsSelect.value) : -14.0,
        })
      });
      const startData = await startRes.json();

      if (!startRes.ok || !startData.ok) {
        throw new Error(startData.error || "Failed to trigger automix job");
      }

      jobId = startData.job_id;
      log(`Automix job registered in queue. Job ID: ${jobId}. Polling status...`, "system");
      
      // Step C: Start Polling
      startPolling(jobId);

    } catch (err) {
      log(`Error: ${err.message}`, "error");
      updateProgress(100, "failed");
      resetUI();
    }
  }

  // 8. Progress Map
  function updateProgress(percent, status) {
    statusBadge.textContent = status;
    statusBadge.className = `status-badge ${status}`;
    progressBar.style.width = `${percent}%`;
    
    if (status === "failed") {
      progressBar.style.background = "#ef4444";
      statusBadge.classList.add("failed");
    } else if (status === "complete") {
      progressBar.style.background = "var(--neon-green)";
      statusBadge.classList.add("complete");
    } else {
      progressBar.style.background = "linear-gradient(to right, var(--neon-cyan), var(--neon-purple))";
      statusBadge.classList.add("active");
    }
  }

  // 9. Start Polling
  function startPolling(jobId) {
    if (pollInterval) clearInterval(pollInterval);
    
    lastStatus = null;
    pollInterval = setInterval(async () => {
      try {
        const res = await fetch(`/api/v1/automix/jobs?id=${jobId}`);
        if (!res.ok) throw new Error("Status query failed.");
        const job = await res.json();
        
        const status = job.status;
        
        if (status !== lastStatus) {
          lastStatus = status;
          log(`Stage changed: ${status.toUpperCase()}`, "system");
        }

        // Map status to progress bar %
        let progress = 5;
        if (status === "classifying") progress = 15;
        else if (status === "preparing") progress = 30;
        else if (status === "analysing") progress = 50;
        else if (status === "deciding") progress = 65;
        else if (status === "processing") progress = 80;
        else if (status === "packaging") progress = 95;
        else if (status === "complete") progress = 100;
        else if (status === "failed") progress = 100;

        updateProgress(progress, status);

        if (status === "complete") {
          clearInterval(pollInterval);
          log("Automix rendering successfully complete!", "success");
          displayResults(job.project_id, job.id);
          resetUI();
        } else if (status === "failed") {
          clearInterval(pollInterval);
          log(`Automix job failed: ${job.error_message}`, "error");
          resetUI();
        }
      } catch (err) {
        log(`Polling error: ${err.message}`, "error");
      }
    }, 1500);
  }

  // 10. Display Render Results
  async function displayResults(projectId, completedJobId) {
    resultsCard.style.display = "flex";
    
    // Set audio preview src to play raw WAV
    audioPreview.src = `/api/automix/play/${projectId}?t=${Date.now()}`;
    
    // Download ZIP package
    btnDownload.onclick = () => {
      window.location.href = `/api/automix/download/${projectId}`;
    };
    
    // View HTML EQ report
    btnViewReport.onclick = () => {
      window.open(`/api/automix/report/${projectId}`, "_blank");
    };

    // View reference-match evidence report, if this render had one (curated
    // genre default or an uploaded reference) -- hidden until we confirm it
    // actually exists, since not every genre/job has a match.
    const matchReportUrl = `/api/automix/match-report/${projectId}`;
    btnViewMatchReport.style.display = "none";
    fetch(matchReportUrl, { method: "GET" })
      .then((res) => {
        if (res.ok) btnViewMatchReport.style.display = "inline-block";
      })
      .catch(() => {});
    btnViewMatchReport.onclick = () => {
      window.open(matchReportUrl, "_blank");
    };

    // View Decisions Log
    btnViewDecisions.onclick = async () => {
      try {
        const res = await fetch(`/api/automix/manifest/${projectId}`);
        const manifest = await res.json();
        
        // Show decisions in terminal log
        log("--- MIX DECISIONS LOG ---", "system");
        manifest.decisions_log.forEach((line) => {
          log(line, "success");
        });
        log("-------------------------", "system");
      } catch (err) {
        log(`Failed to load decisions log: ${err.message}`, "error");
      }
    };

    try {
      const response = await fetch(`/api/automix/manifest/${projectId}`);
      if (!response.ok) throw new Error("Manifest unavailable.");
      const manifest = await response.json();
      renderAdvisorReview(manifest, completedJobId);
    } catch (err) {
      log(`Advisor review unavailable: ${err.message}`, "system");
    }

    renderBeforeAfterComparison(projectId);
  }

  const _BEFORE_AFTER_BANDS = [
    ["sub", "Sub"], ["bass", "Bass"], ["low_mids", "Low Mid"], ["mids", "Mid"],
    ["presence", "Presence"], ["sibilance", "Sib"], ["air", "Air"],
  ];
  const _BEFORE_AFTER_STATS = [
    { key: "integrated_lufs", label: "Integrated LUFS", unit: "", digits: 1 },
    { key: "true_peak_dbfs", label: "True Peak", unit: " dBTP", digits: 1 },
    { key: "crest_factor_db", label: "Crest Factor", unit: " dB", digits: 1 },
    { key: "technical_score", label: "Technical Score", unit: "/100", digits: 0 },
  ];

  function _formatBeforeAfterValue(value, digits) {
    return typeof value === "number" ? value.toFixed(digits) : "—";
  }

  function _beforeAfterBar(value, maxValue, color) {
    const track = document.createElement("div");
    track.style.cssText = "background:rgba(255,255,255,0.06); border-radius:3px; height:6px; overflow:hidden;";
    const fill = document.createElement("div");
    const pct = Math.max(2, Math.min(100, (value / maxValue) * 100));
    fill.style.cssText = `background:${color}; height:100%; width:${pct}%; border-radius:3px;`;
    track.appendChild(fill);
    return track;
  }

  function renderBeforeAfterComparison(projectId) {
    const section = document.getElementById("beforeAfterSection");
    const statsEl = document.getElementById("beforeAfterStats");
    const bandsEl = document.getElementById("beforeAfterBands");
    if (!section || !statsEl || !bandsEl) return;

    fetch(`/api/automix/before-after/${projectId}`)
      .then((res) => {
        if (!res.ok) throw new Error("Before/after comparison not available.");
        return res.json();
      })
      .then((data) => {
        const before = data.before || {};
        const after = data.after || {};
        const deltas = data.deltas || {};

        statsEl.replaceChildren();
        _BEFORE_AFTER_STATS.forEach((def) => {
          const beforeValue = before[def.key];
          const afterValue = after[def.key];
          const delta = deltas[def.key];
          const card = document.createElement("div");
          card.style.cssText = "background:rgba(15,23,42,0.6); border:1px solid rgba(255,255,255,0.08); border-radius:8px; padding:8px 10px;";
          const labelEl = document.createElement("div");
          labelEl.style.cssText = "font-size:10px; color:var(--text-muted); text-transform:uppercase; letter-spacing:0.04em;";
          labelEl.textContent = def.label;
          const valueEl = document.createElement("div");
          valueEl.style.cssText = "font-size:14px; margin-top:2px;";
          const deltaSign = typeof delta === "number" && delta > 0 ? "+" : "";
          const deltaColor = typeof delta === "number" && Math.abs(delta) > 0.05 ? "var(--neon-cyan)" : "var(--text-muted)";
          const beforeText = _formatBeforeAfterValue(beforeValue, def.digits);
          const afterText = _formatBeforeAfterValue(afterValue, def.digits);
          const deltaText = _formatBeforeAfterValue(delta, def.digits);
          valueEl.innerHTML =
            `<span style="color:var(--text-secondary);">${beforeText}${def.unit}</span> → ` +
            `<span style="color:var(--text-main); font-weight:600;">${afterText}${def.unit}</span> ` +
            `<span style="color:${deltaColor}; font-size:11px;">(${deltaSign}${deltaText})</span>`;
          card.appendChild(labelEl);
          card.appendChild(valueEl);
          statsEl.appendChild(card);
        });

        bandsEl.replaceChildren();
        const beforeBands = before.bands || {};
        const afterBands = after.bands || {};
        const allShares = [...Object.values(beforeBands), ...Object.values(afterBands)].filter(
          (v) => typeof v === "number"
        );
        const maxShare = allShares.length ? Math.max(0.01, ...allShares) : 0.01;
        _BEFORE_AFTER_BANDS.forEach(([key, label]) => {
          const beforeValue = beforeBands[key] || 0;
          const afterValue = afterBands[key] || 0;
          const row = document.createElement("div");
          row.style.cssText = "display:grid; grid-template-columns:70px 1fr; align-items:center; gap:8px; font-size:11px;";
          const labelEl = document.createElement("div");
          labelEl.style.cssText = "color:var(--text-muted);";
          labelEl.textContent = label;
          const barsEl = document.createElement("div");
          barsEl.style.cssText = "display:flex; flex-direction:column; gap:2px;";
          barsEl.appendChild(_beforeAfterBar(beforeValue, maxShare, "rgba(113,113,122,0.8)"));
          barsEl.appendChild(_beforeAfterBar(afterValue, maxShare, "var(--neon-cyan)"));
          row.appendChild(labelEl);
          row.appendChild(barsEl);
          bandsEl.appendChild(row);
        });

        const stemsSection = document.getElementById("beforeAfterStemsSection");
        const stemsEl = document.getElementById("beforeAfterStems");
        const stemsNoteEl = document.getElementById("beforeAfterStemsNote");
        const stems = data.stems || {};
        const stemNames = Object.keys(stems);
        if (stemsSection && stemsEl && stemNames.length) {
          stemsEl.replaceChildren();
          stemNames.forEach((name) => {
            const stemData = stems[name];
            const stemDeltas = stemData?.deltas || {};
            const lufsDelta = stemDeltas.integrated_lufs;
            const scoreDelta = stemDeltas.technical_score;
            const row = document.createElement("div");
            row.style.cssText = "display:flex; justify-content:space-between; align-items:center; font-size:11px; background:rgba(15,23,42,0.5); border-radius:6px; padding:5px 8px;";
            const nameEl = document.createElement("span");
            nameEl.style.cssText = "color:var(--text-secondary);";
            nameEl.textContent = name;
            const metricsEl = document.createElement("span");
            metricsEl.style.cssText = "color:var(--text-muted); font-variant-numeric:tabular-nums;";
            const lufsText = typeof lufsDelta === "number" ? `LUFS ${lufsDelta > 0 ? "+" : ""}${lufsDelta.toFixed(1)}` : "LUFS —";
            const scoreText = typeof scoreDelta === "number" ? `score ${scoreDelta > 0 ? "+" : ""}${scoreDelta.toFixed(0)}` : "score —";
            metricsEl.textContent = `${lufsText}  ·  ${scoreText}`;
            row.appendChild(nameEl);
            row.appendChild(metricsEl);
            stemsEl.appendChild(row);
          });
          if (stemsNoteEl) {
            stemsNoteEl.textContent = data.stems_truncated
              ? `Showing ${stemNames.length} of ${data.stems_total} stems.`
              : "";
          }
          stemsSection.style.display = "block";
        } else if (stemsSection) {
          stemsSection.style.display = "none";
        }

        section.style.display = "block";
      })
      .catch(() => {
        section.style.display = "none";
      });
  }

  function ratingSelect(label, required = true) {
    const wrapper = document.createElement("label");
    wrapper.style.cssText = "font-size:11px; color:var(--text-secondary); display:flex; flex-direction:column; gap:4px;";
    wrapper.append(document.createTextNode(label));
    const select = document.createElement("select");
    select.style.cssText = "background:#111827; color:var(--text-main); border:1px solid rgba(255,255,255,.12); border-radius:5px; padding:6px;";
    const blank = document.createElement("option");
    blank.value = "";
    blank.textContent = required ? "Choose 1–5" : "Not rated";
    select.append(blank);
    for (let score = 1; score <= 5; score += 1) {
      const option = document.createElement("option");
      option.value = String(score);
      option.textContent = String(score);
      select.append(option);
    }
    wrapper.append(select);
    return { wrapper, select };
  }

  function renderSpectrumComparison(manifest) {
    const section = document.getElementById("spectrumVisualizerSection");
    const svg = document.getElementById("spectrumSvg");
    const tooltips = document.getElementById("spectrumTooltips");
    if (!section || !svg) return;

    section.style.display = "none";
    if (tooltips) tooltips.replaceChildren();

    const genre = manifest?.genre || "pop";
    const projectId = manifest?.project_id || "";
    if (!projectId) return;

    fetch(`/api/automix/spectrum-match?genre=${encodeURIComponent(genre)}&project_id=${encodeURIComponent(projectId)}`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error("spectrum match unavailable"))))
      .then((data) => {
        const mixBands = data.mix_40_bands || [];
        const refBands = data.ref_40_bands || [];
        if (!data.ok || mixBands.length !== 40 || refBands.length !== 40) {
          throw new Error("incomplete spectrum data");
        }
        section.style.display = "block";

        const bands = [];
        for (let i = 0; i < 40; i++) {
          const freq = 20 * Math.pow(1000, i / 39);
          bands.push({ freq: Math.round(freq), mixDb: mixBands[i], refDb: refBands[i] });
        }

        svg.replaceChildren();

        const gridFrequencies = [20, 100, 1000, 10000, 20000];
        gridFrequencies.forEach((f) => {
          const x = (Math.log10(f / 20) / Math.log10(1000)) * 800;
          const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
          line.setAttribute("x1", x);
          line.setAttribute("y1", 0);
          line.setAttribute("x2", x);
          line.setAttribute("y2", 200);
          line.setAttribute("stroke", "rgba(255,255,255,0.06)");
          line.setAttribute("stroke-dasharray", "2,2");
          svg.appendChild(line);

          const text = document.createElementNS("http://www.w3.org/2000/svg", "text");
          text.setAttribute("x", x + 4);
          text.setAttribute("y", 192);
          text.setAttribute("fill", "#71717a");
          text.setAttribute("font-size", "10");
          text.textContent = f >= 1000 ? `${f / 1000}k` : `${f}Hz`;
          svg.appendChild(text);
        });

        let mixPathD = "";
        let refPathD = "";

        bands.forEach((b, idx) => {
          const x = (Math.log10(b.freq / 20) / Math.log10(1000)) * 800;
          const mixY = Math.max(0, Math.min(200, 200 - ((b.mixDb + 60) / 60) * 200));
          const refY = Math.max(0, Math.min(200, 200 - ((b.refDb + 60) / 60) * 200));

          mixPathD += (idx === 0 ? `M ${x} ${mixY}` : ` L ${x} ${mixY}`);
          refPathD += (idx === 0 ? `M ${x} ${refY}` : ` L ${x} ${refY}`);
        });

        const areaD = mixPathD + " L 800 200 L 0 200 Z";
        const area = document.createElementNS("http://www.w3.org/2000/svg", "path");
        area.setAttribute("d", areaD);
        area.setAttribute("fill", "rgba(96, 165, 250, 0.12)");
        svg.appendChild(area);

        const refPath = document.createElementNS("http://www.w3.org/2000/svg", "path");
        refPath.setAttribute("d", refPathD);
        refPath.setAttribute("stroke", "#a78bfa");
        refPath.setAttribute("stroke-width", "2");
        refPath.setAttribute("fill", "none");
        refPath.setAttribute("stroke-dasharray", "4,4");
        svg.appendChild(refPath);

        const mixPath = document.createElementNS("http://www.w3.org/2000/svg", "path");
        mixPath.setAttribute("d", mixPathD);
        mixPath.setAttribute("stroke", "#60a5fa");
        mixPath.setAttribute("stroke-width", "2.5");
        mixPath.setAttribute("fill", "none");
        svg.appendChild(mixPath);

        if (tooltips) {
          const sourceLabel = data.reference_source === "curated_reference_tracks"
            ? "measured from real reference tracks"
            : "estimated genre profile (no curated reference tracks for this genre)";
          const tooltipTags = [
            `ℹ️ LTAS 40-band profile (${(data.genre || genre).toUpperCase()}) — ${sourceLabel}`,
          ];

          (data.eq_recommendations || []).forEach((eq) => {
            tooltipTags.push(`🎛️ EQ Match: ${eq.type} ${eq.gain_db > 0 ? "+" : ""}${eq.gain_db}dB @ ${eq.frequency}Hz`);
          });

          tooltipTags.forEach((t) => {
            const tag = document.createElement("span");
            tag.style.cssText = "background:rgba(30,41,59,0.5); padding:4px 8px; border-radius:4px; border:1px solid rgba(255,255,255,0.08);";
            tag.textContent = t;
            tooltips.appendChild(tag);
          });
        }
      })
      .catch((err) => {
        section.style.display = "none";
        console.warn("Spectrum match fetch failed:", err);
      });
  }

  function renderAdvisorReview(manifest, completedJobId) {
    renderSpectrumComparison(manifest);
    advisorReviewOperations.replaceChildren();
    advisorReview.style.display = "none";
    const shadow = manifest.kenn_advisor_shadow;
    if (!shadow || shadow.status !== "valid" || !shadow.artifact_id || !shadow.operations?.length) return;
    const preview = shadow.preview;
    const candidates = new Map((preview?.candidates || []).map((item) => [item.operation_index, item]));
    shadow.operations.forEach((operation, index) => {
      const candidate = candidates.get(index);
      const card = document.createElement("section");
      card.style.cssText = "margin:10px 0; padding:12px; border:1px solid rgba(139,92,246,.25); border-radius:8px; background:rgba(15,23,42,.45);";
      const title = document.createElement("div");
      title.style.cssText = "font-size:12px; font-weight:600;";
      title.textContent = `${operation.stem_id}: ${operation.operation} ${operation.value} ${operation.unit}`;
      const detail = document.createElement("p");
      detail.style.cssText = "font-size:11px; color:var(--text-secondary); margin:6px 0;";
      detail.textContent = `${operation.reason} Confidence ${Number(operation.confidence).toFixed(2)}. Evidence: ${(operation.evidence_source_ids || []).join(", ")}`;
      card.append(title, detail);

      if (candidate && preview?.baseline_artifact_id) {
        const players = document.createElement("div");
        players.style.cssText = "display:grid; grid-template-columns:1fr 1fr; gap:8px; margin:8px 0;";
        for (const [label, artifactId] of [["A · Baseline", preview.baseline_artifact_id], ["B · Candidate", candidate.preview_artifact_id]]) {
          const box = document.createElement("label");
          box.style.cssText = "font-size:10px; color:var(--text-muted);";
          box.append(document.createTextNode(label));
          const audio = document.createElement("audio");
          audio.controls = true;
          audio.preload = "none";
          audio.src = `/api/v1/automix/advisor-previews/${encodeURIComponent(artifactId)}`;
          audio.style.width = "100%";
          box.append(audio);
          players.append(box);
        }
        card.append(players);
      }

      const fields = document.createElement("div");
      fields.style.cssText = "display:grid; grid-template-columns:repeat(auto-fit,minmax(120px,1fr)); gap:8px;";
      const decision = document.createElement("select");
      decision.style.cssText = "background:#111827; color:var(--text-main); border:1px solid rgba(255,255,255,.12); border-radius:5px; padding:6px;";
      for (const [value, label] of [["", "Decision"], ["accepted", "Accept"], ["rejected", "Reject"], ["needs_work", "Needs work"]]) {
        const option = document.createElement("option"); option.value = value; option.textContent = label; decision.append(option);
      }
      const usefulness = ratingSelect("Usefulness");
      const explanation = ratingSelect("Explanation quality");
      const audible = ratingSelect("Audible improvement", false);
      audible.select.disabled = !candidate;
      fields.append(decision, usefulness.wrapper, explanation.wrapper, audible.wrapper);
      const reason = document.createElement("textarea");
      reason.maxLength = 1000;
      reason.placeholder = "Optional private note";
      reason.style.cssText = "width:100%; margin-top:8px; background:#111827; color:var(--text-main); border:1px solid rgba(255,255,255,.12); border-radius:5px; padding:7px;";
      const submit = document.createElement("button");
      submit.className = "btn-secondary";
      submit.textContent = "Save operation review";
      submit.style.marginTop = "8px";
      const status = document.createElement("span");
      status.style.cssText = "font-size:11px; margin-left:8px; color:var(--text-muted);";
      submit.onclick = async () => {
        if (!decision.value || !usefulness.select.value || !explanation.select.value) {
          status.textContent = "Choose a decision, usefulness, and explanation score.";
          return;
        }
        submit.disabled = true;
        try {
          const response = await fetch("/api/v1/automix/advisor-feedback", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              job_id: completedJobId,
              shadow_artifact_id: shadow.artifact_id,
              operation_index: index,
              decision: decision.value,
              usefulness_rating: Number(usefulness.select.value),
              explanation_quality_rating: Number(explanation.select.value),
              audible_improvement_rating: audible.select.value ? Number(audible.select.value) : null,
              preview_artifact_id: candidate?.preview_artifact_id || "",
              reason: reason.value
            })
          });
          const data = await response.json();
          if (!response.ok) throw new Error(data.error || "Review failed.");
          status.textContent = "Review saved.";
          status.style.color = "var(--neon-green)";
          for (const field of [decision, usefulness.select, explanation.select, audible.select, reason]) field.disabled = true;
        } catch (err) {
          submit.disabled = false;
          status.textContent = err.message;
          status.style.color = "#ef4444";
        }
      };
      card.append(fields, reason, submit, status);
      advisorReviewOperations.append(card);
    });
    advisorReview.style.display = "block";
  }

  // 11. Reset UI controls
  function resetUI() {
    projectIdInput.disabled = false;
    btnGenId.disabled = false;
    genreSelect.disabled = false;
    sliderBrightWarm.disabled = false;
    sliderDynamic.disabled = false;
    sliderSpatial.disabled = false;
    sliderWidth.disabled = false;
    uploadZone.style.pointerEvents = "auto";
    refUploadZone.style.pointerEvents = "auto";
    btnSubmitRevision.disabled = false;
    feedbackInput.disabled = false;
    validateForm();
  }

  // 12. Submit Revision Request
  async function submitRevisionProcess() {
    const projectId = projectIdInput.value.trim();
    const feedback = feedbackInput.value.trim();
    if (!projectId || !feedback) return;

    btnSubmitRevision.disabled = true;
    feedbackInput.disabled = true;
    btnStartMix.disabled = true;
    projectIdInput.disabled = true;
    btnGenId.disabled = true;
    
    log(`Submitting revision request: "${feedback}"`, "system");
    updateProgress(0, "queued");

    try {
      const res = await fetch("/api/v1/automix/revisions", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Idempotency-Key": idempotencyKey("automix-revision")
        },
        body: JSON.stringify({
          project_id: projectId,
          feedback: feedback
        })
      });
      const data = await res.json();
      if (!res.ok || !data.ok) {
        throw new Error(data.error || "Failed to submit revision.");
      }

      jobId = data.job_id;
      log(`Revision job queued. Job ID: ${jobId}. Polling status...`, "system");
      
      // Clear input
      feedbackInput.value = "";
      resultsCard.style.display = "none";
      
      startPolling(jobId);
    } catch (err) {
      log(`Revision failed: ${err.message}`, "error");
      updateProgress(100, "failed");
      resetUI();
    }
  }

})();
