const form = document.querySelector("#enquiry-form");
const statusEl = document.querySelector("#form-status");

form?.addEventListener("submit", async (event) => {
  event.preventDefault();
  statusEl.textContent = "Sending…";
  const payload = Object.fromEntries(new FormData(form).entries());

  try {
    const response = await fetch("/api/enquiry", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const result = await response.json();

    if (response.status === 429) {
      statusEl.textContent = result.error || "Too many attempts. Please try again later.";
      return;
    }
    if (!response.ok) {
      statusEl.textContent = result.error || "Could not send enquiry.";
      return;
    }

    form.reset();
    statusEl.textContent = "Thank you — your enquiry was received. We will be in touch.";
  } catch {
    statusEl.textContent = "Network error. Check that the local server is running.";
  }
});
