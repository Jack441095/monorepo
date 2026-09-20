/**
 * Audio Developer Studio Controller Logic.
 */

(function () {
  const languageSelect = document.getElementById("languageSelect");
  const boilerplateSelect = document.getElementById("boilerplateSelect");
  const btnAuditCode = document.getElementById("btnAuditCode");
  const codeEditor = document.getElementById("codeEditor");
  const outputConsole = document.getElementById("outputConsole");

  async function loadBoilerplate(type) {
    if (!type) return;
    try {
      const res = await fetch("/api/audio-dev", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "generate_boilerplate", snippet_type: type })
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      if (data.ok && data.snippet) {
        if (codeEditor) codeEditor.value = data.snippet.code;
        if (languageSelect) languageSelect.value = data.snippet.language;
        if (outputConsole) outputConsole.textContent = `✅ Loaded boilerplate: ${data.snippet.title}`;
      }
    } catch (err) {
      if (outputConsole) outputConsole.textContent = `❌ Error loading boilerplate: ${err.message}`;
    }
  }

  async function runSafetyAudit() {
    const code = codeEditor ? codeEditor.value.trim() : "";
    const lang = languageSelect ? languageSelect.value : "cpp";

    if (!code) {
      if (outputConsole) outputConsole.textContent = "Please enter audio source code or select a boilerplate above.";
      return;
    }

    if (outputConsole) outputConsole.textContent = "⚡ Analyzing audio thread safety & querying KENN co-pilot...";

    try {
      const res = await fetch("/api/audio-dev", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          query: "Audit this audio processing code for real-time safety, memory allocations, and performance optimization.",
          code_context: code,
          language: lang
        })
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();

      const safetyScoreCard = document.getElementById("safetyScoreCard");
      const scoreBadge = document.getElementById("scoreBadge");
      const scoreBar = document.getElementById("scoreBar");

      if (safetyScoreCard) safetyScoreCard.style.display = "block";
      const score = data.safety_score !== undefined ? data.safety_score : 100;
      if (scoreBadge) scoreBadge.textContent = `${score} / 100`;
      if (scoreBar) {
        scoreBar.style.width = `${score}%`;
        if (score >= 90) scoreBar.style.background = "var(--accent-green)";
        else if (score >= 60) scoreBar.style.background = "var(--accent-orange)";
        else scoreBar.style.background = "#f87171";
      }

      let output = "";
      if (data.realtime_warnings && data.realtime_warnings.length > 0) {
        output += "⚠️ REAL-TIME THREAD SAFETY AUDIT BREAKDOWN:\n";
        data.realtime_warnings.forEach(w => output += `- ${w}\n`);
        output += "\n----------------------------------------\n\n";
      } else {
        output += "✅ REAL-TIME THREAD SAFETY: No obvious allocations/locks detected in audio thread.\n\n----------------------------------------\n\n";
      }

      output += `🤖 KENN AUDIO CO-PILOT ADVICE:\n${data.advice || "No specific advice."}`;

      if (outputConsole) outputConsole.textContent = output;
    } catch (err) {
      if (outputConsole) outputConsole.textContent = `❌ Audit failed: ${err.message}`;
    }
  }

  if (boilerplateSelect) {
    boilerplateSelect.addEventListener("change", (e) => {
      loadBoilerplate(e.target.value);
    });
  }

  if (btnAuditCode) {
    btnAuditCode.addEventListener("click", runSafetyAudit);
  }
})();

