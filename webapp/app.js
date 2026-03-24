// ── Telegram Web App init ───────────────────────────────────────
const tg = window.Telegram.WebApp;
tg.ready();
tg.expand();

const API = window.location.origin + "/api";
const userId = tg.initDataUnsafe?.user?.id;

if (!userId) {
  document.getElementById("app").innerHTML =
    '<div class="empty-state"><p>Please open this app from Telegram.</p></div>';
}

// ── API helpers ─────────────────────────────────────────────────
async function api(method, path, body = null) {
  const opts = {
    method,
    headers: {
      "Content-Type": "application/json",
      "X-Telegram-Init-Data": tg.initData,
    },
  };
  if (body) opts.body = JSON.stringify(body);
  const res = await fetch(API + path, opts);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.error || `API error ${res.status}`);
  }
  return res.json();
}

// ── Toast ───────────────────────────────────────────────────────
function showToast(msg) {
  let toast = document.querySelector(".toast");
  if (!toast) {
    toast = document.createElement("div");
    toast.className = "toast";
    document.body.appendChild(toast);
  }
  toast.textContent = msg;
  toast.classList.add("show");
  setTimeout(() => toast.classList.remove("show"), 2000);
}

// ── Tab navigation ──────────────────────────────────────────────
document.querySelectorAll(".tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
    document.querySelectorAll(".view").forEach((v) => v.classList.remove("active"));
    tab.classList.add("active");
    document.getElementById("view-" + tab.dataset.view).classList.add("active");
    tg.HapticFeedback.selectionChanged();

    // Lazy-load data when switching tabs
    if (tab.dataset.view === "history") loadHistory();
    if (tab.dataset.view === "stats") loadStats();
  });
});

// ── Log View ────────────────────────────────────────────────────
let historyOffset = 0;

document.getElementById("btn-save").addEventListener("click", async () => {
  const raw = document.getElementById("inp-raw").value.trim();
  if (!raw) {
    showToast("Enter your workout first");
    tg.HapticFeedback.notificationOccurred("error");
    return;
  }

  tg.HapticFeedback.impactOccurred("medium");
  try {
    const data = await api("POST", "/workouts", { raw_text: raw });
    document.getElementById("inp-raw").value = "";
    showToast("Workout #" + data.workout_id + " saved!");
    tg.HapticFeedback.notificationOccurred("success");
  } catch (e) {
    showToast(e.message);
    tg.HapticFeedback.notificationOccurred("error");
  }
});

// Load exercise name suggestions
async function loadSuggestions() {
  try {
    const data = await api("GET", "/exercises");
    const container = document.getElementById("suggestion-chips");
    const wrapper = document.getElementById("suggestions");

    if (!data.exercises || data.exercises.length === 0) {
      wrapper.style.display = "none";
      return;
    }
    wrapper.style.display = "block";
    container.innerHTML = "";

    data.exercises.slice(0, 20).forEach((name) => {
      const chip = document.createElement("button");
      chip.className = "chip";
      chip.textContent = name;
      chip.addEventListener("click", () => {
        const textarea = document.getElementById("inp-raw");
        const val = textarea.value;
        const suffix = name + ": ";
        textarea.value = val ? val + "\n" + suffix : suffix;
        textarea.focus();
        tg.HapticFeedback.selectionChanged();
      });
      container.appendChild(chip);
    });
  } catch (e) {
    console.error("Failed to load suggestions", e);
  }
}

// ── History View ────────────────────────────────────────────────

async function loadHistory(append = false) {
  try {
    if (!append) historyOffset = 0;
    const data = await api("GET", `/workouts?limit=10&offset=${historyOffset}`);
    const container = document.getElementById("history-list");
    const noHistory = document.getElementById("no-history");
    const loadMore = document.getElementById("btn-load-more");

    if (!append) container.innerHTML = "";

    if (!data.workouts || data.workouts.length === 0) {
      if (!append) noHistory.style.display = "block";
      loadMore.style.display = "none";
      return;
    }
    noHistory.style.display = "none";

    data.workouts.forEach((w) => {
      const card = document.createElement("div");
      card.className = "history-card";

      const ts = new Date(w.timestamp);
      const dateStr = ts.toLocaleDateString(undefined, {
        weekday: "short",
        day: "numeric",
        month: "short",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      });

      // Calculate volume
      let volume = 0;
      let totalSets = 0;
      (w.superset_groups || []).forEach((group) => {
        group.forEach((ex) => {
          volume += ex.sets * ex.reps * ex.weight_kg;
          totalSets += ex.sets;
        });
      });

      let groupsHtml = "";
      (w.superset_groups || []).forEach((group) => {
        const isSuperset = group.length > 1;
        if (isSuperset) {
          groupsHtml += '<div class="history-group"><div class="superset-label">Superset</div>';
        } else {
          groupsHtml += '<div class="history-group">';
        }
        group.forEach((ex) => {
          const machine = ex.machine_id ? ` <span class="ex-machine">(${ex.machine_id})</span>` : "";
          groupsHtml += `
            <div class="history-exercise">
              <span class="ex-name">${ex.name}</span>${machine}
              <span class="ex-detail"> — ${ex.sets}x${ex.reps}x${ex.weight_kg}kg</span>
            </div>`;
        });
        groupsHtml += "</div>";
      });

      card.innerHTML = `
        <div class="history-header">
          <span class="history-date">${dateStr}</span>
          <span class="history-volume">${Math.round(volume)} kg vol</span>
        </div>
        ${groupsHtml}
      `;
      container.appendChild(card);
    });

    historyOffset += data.workouts.length;
    loadMore.style.display = historyOffset < data.total ? "block" : "none";
  } catch (e) {
    console.error("Failed to load history", e);
  }
}

document.getElementById("btn-load-more").addEventListener("click", () => {
  loadHistory(true);
});

// ── Stats View ──────────────────────────────────────────────────

async function loadStats() {
  try {
    const data = await api("GET", "/stats");
    const container = document.getElementById("stats-content");

    if (data.total_workouts === 0) {
      container.innerHTML = '<div class="empty-state"><div class="empty-icon">📊</div><p>No workouts yet</p></div>';
      return;
    }

    container.innerHTML = `
      <div class="stats-grid">
        <div class="stat-card">
          <div class="stat-value">${data.total_workouts}</div>
          <div class="stat-label">Workouts</div>
        </div>
        <div class="stat-card">
          <div class="stat-value">${data.unique_exercises}</div>
          <div class="stat-label">Exercises</div>
        </div>
        <div class="stat-card">
          <div class="stat-value">${data.total_sets.toLocaleString()}</div>
          <div class="stat-label">Total Sets</div>
        </div>
        <div class="stat-card">
          <div class="stat-value">${Math.round(data.total_volume).toLocaleString()}</div>
          <div class="stat-label">Volume (kg)</div>
        </div>
      </div>
    `;
  } catch (e) {
    console.error("Failed to load stats", e);
  }
}

// ── Init ────────────────────────────────────────────────────────
async function init() {
  if (!userId) return;
  await loadSuggestions();
}

init();
