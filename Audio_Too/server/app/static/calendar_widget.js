// calendar_widget.js — Client-side Calendar App Tab

let currentYear = new Date().getFullYear();
let currentMonth = new Date().getMonth(); // 0-indexed
let calendarEvents = [];
let showCompletedEvents = true;

async function loadCalendar() {
  const gridContainer = document.querySelector("#calendar-grid-container");
  if (!gridContainer) return;

  try {
    const data = await api("/api/admin/calendar");
    calendarEvents = data.events || [];
    renderCalendarGrid();
    renderUpcomingEventsList();
  } catch (error) {
    console.error("Failed to load calendar events:", error);
    gridContainer.innerHTML = `<p class="error-text">Failed to load calendar: ${escapeHtml(error.message)}</p>`;
  }
}

function renderCalendarGrid() {
  const gridContainer = document.querySelector("#calendar-grid-container");
  const monthLabel = document.querySelector("#calendar-month-label");
  if (!gridContainer || !monthLabel) return;

  // Month names
  const monthNames = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December"
  ];
  monthLabel.textContent = `${monthNames[currentMonth]} ${currentYear}`;

  // Clear previous grid
  gridContainer.innerHTML = "";

  // Days of the week headers
  const dayNames = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
  dayNames.forEach(day => {
    const header = document.createElement("div");
    header.className = "calendar-grid-header";
    header.textContent = day;
    gridContainer.appendChild(header);
  });

  // Calculate dates
  const firstDay = new Date(currentYear, currentMonth, 1);
  // Get weekday of first day of the month (0 = Sunday, 1 = Monday, ..., 6 = Saturday)
  let startDayIndex = firstDay.getDay();
  // Adjust to Monday-indexed (0 = Mon, 1 = Tue, ..., 6 = Sun)
  startDayIndex = startDayIndex === 0 ? 6 : startDayIndex - 1;

  const daysInMonth = new Date(currentYear, currentMonth + 1, 0).getDate();
  const today = new Date();

  // Empty cells for days of previous month
  for (let i = 0; i < startDayIndex; i++) {
    const emptyCell = document.createElement("div");
    emptyCell.className = "calendar-day empty";
    gridContainer.appendChild(emptyCell);
  }

  // Days of the month
  for (let day = 1; day <= daysInMonth; day++) {
    const cell = document.createElement("div");
    cell.className = "calendar-day";
    
    // Highlight today
    if (day === today.getDate() && currentMonth === today.getMonth() && currentYear === today.getFullYear()) {
      cell.classList.add("today");
    }

    const dayNum = document.createElement("div");
    dayNum.className = "day-number";
    dayNum.textContent = day;
    cell.appendChild(dayNum);

    // Filter events for this specific day
    const cellDateStr = `${currentYear}-${String(currentMonth + 1).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
    const dayEvents = calendarEvents.filter(event => {
      if (!event.due_at) return false;
      // Compare YYYY-MM-DD
      return event.due_at.substring(0, 10) === cellDateStr;
    });

    // Render events in the day cell
    const eventsContainer = document.createElement("div");
    eventsContainer.className = "day-events-container";
    
    dayEvents.forEach(event => {
      if (event.acknowledged && !showCompletedEvents) return;
      
      const eventEl = document.createElement("div");
      eventEl.className = `calendar-event ${event.acknowledged ? "completed" : "active"}`;
      
      // Extract time if present
      let timeStr = "";
      if (event.due_at && event.due_at.includes("T")) {
        const timePart = event.due_at.split("T")[1].substring(0, 5);
        if (timePart !== "00:00") {
          timeStr = `<span class="event-time">${timePart}</span> `;
        }
      }

      eventEl.innerHTML = `${timeStr}<span class="event-text-title" title="${escapeHtml(event.text)}">${escapeHtml(event.text)}</span>`;
      
      // Click event to view/edit or acknowledge
      eventEl.addEventListener("click", (e) => {
        e.stopPropagation();
        showEventDetailModal(event);
      });

      eventsContainer.appendChild(eventEl);
    });

    cell.appendChild(eventsContainer);
    gridContainer.appendChild(cell);
  }
}

function renderUpcomingEventsList() {
  const listContainer = document.querySelector("#calendar-events-list");
  if (!listContainer) return;

  listContainer.innerHTML = "";

  // Sort events by due_at
  const sortedEvents = [...calendarEvents].sort((a, b) => {
    if (!a.due_at) return 1;
    if (!b.due_at) return -1;
    return a.due_at.localeCompare(b.due_at);
  });

  const activeEvents = sortedEvents.filter(e => !e.acknowledged);
  const completedEvents = sortedEvents.filter(e => e.acknowledged);

  const displayList = [...activeEvents];
  if (showCompletedEvents) {
    displayList.push(...completedEvents);
  }

  if (displayList.length === 0) {
    listContainer.innerHTML = `<p class="no-events">No events found.</p>`;
    return;
  }

  displayList.forEach(event => {
    const item = document.createElement("div");
    item.className = `upcoming-event-item ${event.acknowledged ? "completed" : ""}`;

    let dateDisplay = "No due date";
    if (event.due_at) {
      try {
        const dt = new Date(event.due_at);
        dateDisplay = dt.toLocaleString("en-GB", {
          weekday: "short",
          day: "numeric",
          month: "short",
          hour: "2-digit",
          minute: "2-digit"
        });
      } catch {
        dateDisplay = event.due_at;
      }
    }

    item.innerHTML = `
      <div class="event-item-info">
        <div class="event-item-title">${escapeHtml(event.text)}</div>
        <div class="event-item-date">${escapeHtml(dateDisplay)}</div>
      </div>
      <div class="event-item-actions">
        ${!event.acknowledged ? `
          <button type="button" class="btn-ack" data-id="${event.id}" title="Mark completed">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
          </button>
        ` : `
          <span class="badge-completed">Done</span>
        `}
      </div>
    `;

    item.querySelector(".btn-ack")?.addEventListener("click", async (e) => {
      e.stopPropagation();
      await acknowledgeEvent(event.id);
    });

    listContainer.appendChild(item);
  });
}

async function acknowledgeEvent(eventId) {
  try {
    const res = await api("/api/admin/calendar/acknowledge", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: eventId })
    });
    if (res.ok) {
      await loadCalendar();
    } else {
      alert("Failed to complete event: " + res.error);
    }
  } catch (error) {
    alert("Error completing event: " + error.message);
  }
}

function showEventDetailModal(event) {
  const modal = document.querySelector("#calendar-detail-modal");
  const titleEl = document.querySelector("#detail-modal-title");
  const dateEl = document.querySelector("#detail-modal-date");
  const statusEl = document.querySelector("#detail-modal-status");
  const btnComplete = document.querySelector("#detail-modal-btn-complete");

  if (!modal || !titleEl || !dateEl || !statusEl || !btnComplete) return;

  titleEl.textContent = event.text;
  
  let dateText = "No date";
  if (event.due_at) {
    dateText = new Date(event.due_at).toLocaleString("en-GB", {
      weekday: "long",
      day: "numeric",
      month: "long",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit"
    });
  }
  dateEl.textContent = dateText;
  
  statusEl.textContent = event.acknowledged ? "Completed" : "Active";
  statusEl.className = `status-badge ${event.acknowledged ? "completed" : "active"}`;

  if (event.acknowledged) {
    btnComplete.style.display = "none";
  } else {
    btnComplete.style.display = "inline-block";
    btnComplete.onclick = async () => {
      await acknowledgeEvent(event.id);
      closeCalendarModal("calendar-detail-modal");
    };
  }

  modal.classList.add("active");
}

function closeCalendarModal(modalId) {
  document.querySelector(`#${modalId}`)?.classList.remove("active");
}

// Wire up events on document load
document.addEventListener("DOMContentLoaded", () => {
  document.querySelector("#calendar-prev-month")?.addEventListener("click", () => {
    currentMonth--;
    if (currentMonth < 0) {
      currentMonth = 11;
      currentYear--;
    }
    renderCalendarGrid();
  });

  document.querySelector("#calendar-next-month")?.addEventListener("click", () => {
    currentMonth++;
    if (currentMonth > 11) {
      currentMonth = 0;
      currentYear++;
    }
    renderCalendarGrid();
  });

  document.querySelector("#calendar-btn-add")?.addEventListener("click", () => {
    document.querySelector("#calendar-add-modal")?.classList.add("active");
  });

  document.querySelectorAll(".calendar-modal-close").forEach(btn => {
    btn.addEventListener("click", (e) => {
      const modal = e.target.closest(".calendar-modal");
      if (modal) modal.classList.remove("active");
    });
  });

  const addForm = document.querySelector("#calendar-add-form");
  addForm?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const text = document.querySelector("#add-event-title").value.trim();
    const when = document.querySelector("#add-event-when").value.trim();

    if (!text || !when) return;

    try {
      const res = await api("/api/admin/calendar", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text, when })
      });
      
      if (res.ok) {
        addForm.reset();
        closeCalendarModal("calendar-add-modal");
        await loadCalendar();
      } else {
        alert("Failed to add event: " + res.error);
      }
    } catch (error) {
      alert("Error adding event: " + error.message);
    }
  });

  const toggleCompleteCheckbox = document.querySelector("#calendar-toggle-completed");
  toggleCompleteCheckbox?.addEventListener("change", (e) => {
    showCompletedEvents = e.target.checked;
    renderCalendarGrid();
    renderUpcomingEventsList();
  });
});
