// router.js — Client-side hash routing and workspace panel switching

function showTab(name) {
  // 1. Activate tab buttons
  tabButtons.forEach((button) => button.classList.toggle("active", button.dataset.tab === name));

  // 2. Activate panels
  tabPanels.forEach((panel) => {
    const active = panel.dataset.panel === name;
    panel.hidden = !active;
    panel.classList.toggle("active", active);
  });

  // 3. Handle consolidated navigation sections
  const activeTabButton = document.querySelector(`.control-tabs .tab[data-tab="${name}"]`);
  if (activeTabButton) {
    const subRow = activeTabButton.closest(".sub-tabs-row");
    if (subRow) {
      document.querySelectorAll(".sub-tabs-row").forEach((row) => {
        row.hidden = row !== subRow;
      });
      const category = subRow.id.replace("sub-tabs-", "");
      document.querySelectorAll(".primary-tab").forEach((btn) => {
        btn.classList.toggle("active", btn.dataset.category === category);
      });
    }
  }

  // Update hash for deep-linking
  location.hash = name;

  // 4. Trigger actions
  metricsEl.hidden = name !== "overview";
  if (name === "overview") typeof loadHub === "function" && loadHub();
  if (name === "transcripts") {
    typeof loadTranscriptLlmStatus === "function" && loadTranscriptLlmStatus();
    typeof loadTranscripts === "function" && loadTranscripts();
  }
  if (name === "activity") typeof loadActivity === "function" && loadActivity();
  if (name === "ableton") typeof checkAbletonWeb === "function" && checkAbletonWeb();
  if (name === "audiogen") typeof loadAudioGenStatus === "function" && loadAudioGenStatus();
  if (name === "lm-gaps") typeof loadLmGaps === "function" && loadLmGaps();
  if (name === "lm-improve") typeof loadLmImprove === "function" && loadLmImprove();
  if (name === "knowledge-admin") typeof loadKnowledgeAdmin === "function" && loadKnowledgeAdmin();
  if (name === "stems") typeof loadStems === "function" && loadStems();
  if (name === "portfolio-ops") typeof loadPortfolioOps === "function" && loadPortfolioOps();
  if (name === "mix-review") {
    typeof loadMixReviews === "function" && loadMixReviews();
    typeof loadMixReferences === "function" && loadMixReferences();
    typeof loadCalibrationTargets === "function" && loadCalibrationTargets();
    typeof loadMixVersionTimeline === "function" && loadMixVersionTimeline();
  }
  if (name === "calendar") {
    typeof loadCalendar === "function" && loadCalendar();
  }
}

document.querySelectorAll("[data-goto]").forEach((button) => {
  button.addEventListener("click", () => showTab(button.dataset.goto));
});

tabButtons.forEach((button) => {
  button.addEventListener("click", () => showTab(button.dataset.tab));
});

document.querySelectorAll(".primary-tab").forEach((btn) => {
  btn.addEventListener("click", () => {
    const category = btn.dataset.category;
    const subRow = document.getElementById(`sub-tabs-${category}`);
    if (subRow) {
      const firstTab = subRow.querySelector(".tab");
      if (firstTab) {
        showTab(firstTab.dataset.tab);
      }
    }
  });
});

window.addEventListener("DOMContentLoaded", () => {
  const params = new URLSearchParams(window.location.search);
  const queryTab = params.get("tab");
  const initialTab = queryTab || location.hash.replace(/^#/, "");
  if (initialTab && document.querySelector(`.control-tabs .tab[data-tab="${initialTab}"]`)) {
    showTab(initialTab);
  } else {
    showTab("overview");
  }
  sessionActive().then((active) => {
    if (active) {
      typeof loadAdmin === "function" && loadAdmin();
      typeof loadHub === "function" && loadHub();
    } else {
      statusEl.textContent = "Enter your dashboard password to unlock.";
    }
  });
});
