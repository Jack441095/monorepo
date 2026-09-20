/**
 * Thursday Agentic Business Command Hub Logic.
 */

async function executeCommercialDispatch(event) {
  event.preventDefault();
  const clientName = document.getElementById("clientName").value.trim() || "Apex Records";
  const projectTitle = document.getElementById("projectTitle").value.trim() || "Commercial Single";
  const genre = document.getElementById("genreSelect").value;
  const statusText = document.getElementById("statusText");
  const pipelineContainer = document.getElementById("pipelineContainer");
  const pipelineGrid = document.getElementById("pipelineGrid");
  const manifestBox = document.getElementById("manifestBox");

  const genreBpmMap = { pop: 120, lofi: 90, hiphop: 95, edm: 128 };
  const bpm = genreBpmMap[genre] || 120;

  try {
    statusText.innerHTML = `System Status: <strong style="color:var(--accent-blue);">Executing Commercial Job Pipeline...</strong>`;
    pipelineContainer.style.display = "block";
    pipelineGrid.replaceChildren();
    manifestBox.textContent = "Processing 5-stage autonomous workflow...";

    const res = await fetch("/api/thursday/commercial-dispatch", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        client_name: clientName,
        project_title: projectTitle,
        genre: genre,
        bpm: bpm,
        target_lufs: -14.0,
      }),
    });

    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    statusText.innerHTML = `System Status: <strong style="color:var(--accent-green);">Job ${data.job_id} Completed & Delivered</strong>`;

    const jobPkg = data.job_package || {};
    const stages = jobPkg.stages || [];

    stages.forEach((stg) => {
      const card = document.createElement("div");
      card.className = "stage-card completed";
      card.innerHTML = `
        <div class="stage-num">STAGE ${stg.stage}</div>
        <div class="stage-title">✅ ${stg.name}</div>
        <div class="stage-details">${stg.details}</div>
      `;
      pipelineGrid.appendChild(card);
    });

    manifestBox.textContent = JSON.stringify(jobPkg, null, 2);
  } catch (err) {
    statusText.innerHTML = `System Status: <strong style="color:#f87171;">Dispatch Error: ${err.message}</strong>`;
    manifestBox.textContent = `Error executing dispatch: ${err.message}`;
  }
}

// Jarvis Studio Voice Assistant logic
(function () {
  const arcReactor = document.getElementById("arcReactor");
  const speechStatus = document.getElementById("speechStatus");
  const jarvisInput = document.getElementById("jarvisInput");
  const btnJarvisAsk = document.getElementById("btnJarvisAsk");
  const jarvisResponseCard = document.getElementById("jarvisResponseCard");
  const jarvisResponseText = document.getElementById("jarvisResponseText");

  let recognition = null;
  if ("webkitSpeechRecognition" in window || "SpeechRecognition" in window) {
    const SpeechRec = window.SpeechRecognition || window.webkitSpeechRecognition;
    recognition = new SpeechRec();
    recognition.continuous = false;
    recognition.interimResults = false;
    recognition.lang = "en-US";

    recognition.onstart = () => {
      if (speechStatus) speechStatus.textContent = "🎙️ Listening... Speak your command now";
      if (arcReactor) arcReactor.style.borderColor = "var(--accent-purple)";
    };

    recognition.onresult = (event) => {
      const transcript = event.results[0][0].transcript;
      if (jarvisInput) jarvisInput.value = transcript;
      if (speechStatus) speechStatus.textContent = `Recognized: "${transcript}"`;
      askJarvis(transcript);
    };

    recognition.onerror = (err) => {
      if (speechStatus) speechStatus.textContent = `Speech recognition error: ${err.error}`;
      if (arcReactor) arcReactor.style.borderColor = "var(--accent-blue)";
    };

    recognition.onend = () => {
      if (arcReactor) arcReactor.style.borderColor = "var(--accent-blue)";
    };
  }

  if (arcReactor) {
    arcReactor.addEventListener("click", () => {
      if (recognition) {
        try { recognition.start(); } catch (e) { console.error(e); }
      } else {
        alert("Web Speech recognition is not supported in this browser. Please type your query.");
      }
    });
  }

  if (btnJarvisAsk && jarvisInput) {
    btnJarvisAsk.addEventListener("click", () => {
      const query = jarvisInput.value.trim();
      if (query) askJarvis(query);
    });
    jarvisInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        const query = jarvisInput.value.trim();
        if (query) askJarvis(query);
      }
    });
  }

  async function askJarvis(prompt) {
    if (!prompt) return;
    if (speechStatus) speechStatus.textContent = "⚡ Asking Thursday & querying KENN knowledge engine...";

    try {
      const res = await fetch("/api/thursday/jarvis-action", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "query", prompt: prompt })
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();

      if (jarvisResponseCard) jarvisResponseCard.style.display = "block";
      if (jarvisResponseText) jarvisResponseText.textContent = data.text || "No response received.";

      if (speechStatus) speechStatus.textContent = "✅ Thursday response generated.";

      // Speak response using SpeechSynthesis API if available
      if (data.spoken_text && "speechSynthesis" in window) {
        window.speechSynthesis.cancel();
        const utterance = new SpeechSynthesisUtterance(data.spoken_text.slice(0, 300));
        utterance.rate = 1.05;
        utterance.pitch = 0.95;
        window.speechSynthesis.speak(utterance);
      }
    } catch (err) {
      if (jarvisResponseCard) jarvisResponseCard.style.display = "block";
      if (jarvisResponseText) jarvisResponseText.textContent = `Error: ${err.message}`;
      if (speechStatus) speechStatus.textContent = `❌ Request failed: ${err.message}`;
    }
  }
})();

