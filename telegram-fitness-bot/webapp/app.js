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

// ── State ───────────────────────────────────────────────────────
let activeWorkout = null;
let exercises = [];
let timerInterval = null;

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
function showToast(message) {
  let toast = document.querySelector(".toast");
  if (!toast) {
    toast = document.createElement("div");
    toast.className = "toast";
    document.body.appendChild(toast);
  }
  toast.textContent = message;
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
  });
});

// ── Timer ───────────────────────────────────────────────────────
function startTimer(startedAt) {
  if (timerInterval) clearInterval(timerInterval);
  const start = new Date(startedAt + "Z").getTime();
  const el = document.getElementById("workout-timer");

  function tick() {
    const diff = Math.floor((Date.now() - start) / 1000);
    const m = String(Math.floor(diff / 60)).padStart(2, "0");
    const s = String(diff % 60).padStart(2, "0");
    el.textContent = `${m}:${s}`;
  }
  tick();
  timerInterval = setInterval(tick, 1000);
}

function stopTimer() {
  if (timerInterval) {
    clearInterval(timerInterval);
    timerInterval = null;
  }
}

// ── Render helpers ──────────────────────────────────────────────

function renderExerciseSelect() {
  const sel = document.getElementById("sel-exercise");
  sel.innerHTML = '<option value="">Select exercise…</option>';
  exercises.forEach((ex) => {
    const opt = document.createElement("option");
    opt.value = ex.id;
    opt.textContent = ex.name;
    sel.appendChild(opt);
  });
}

function renderSets(sets) {
  const container = document.getElementById("sets-list");
  container.innerHTML = "";

  if (!sets || sets.length === 0) return;

  // Group by exercise
  const groups = {};
  sets.forEach((s) => {
    if (!groups[s.exercise_name]) groups[s.exercise_name] = [];
    groups[s.exercise_name].push(s);
  });

  for (const [name, groupSets] of Object.entries(groups)) {
    const group = document.createElement("div");
    group.className = "exercise-group";

    const heading = document.createElement("div");
    heading.className = "exercise-group-name";
    heading.textContent = name;
    group.appendChild(heading);

    groupSets.forEach((s, i) => {
      const item = document.createElement("div");
      item.className = "set-item";
      item.innerHTML = `
        <span class="set-number">Set ${i + 1}</span>
        <span class="set-detail">${s.reps} reps × ${s.weight} kg</span>
        <button class="set-delete" data-set-id="${s.id}">×</button>
      `;
      group.appendChild(item);
    });

    container.appendChild(group);
  }

  // Attach delete handlers
  container.querySelectorAll(".set-delete").forEach((btn) => {
    btn.addEventListener("click", async () => {
      tg.HapticFeedback.impactOccurred("light");
      await api("DELETE", `/sets/${btn.dataset.setId}`);
      await refreshWorkout();
    });
  });
}

function renderExercisesList() {
  const container = document.getElementById("exercises-list");
  container.innerHTML = "";

  exercises.forEach((ex) => {
    const item = document.createElement("div");
    item.className = "exercise-item";
    item.innerHTML = `
      <span>${ex.name}</span>
      <button class="exercise-delete" data-exercise-id="${ex.id}">×</button>
    `;
    container.appendChild(item);
  });

  container.querySelectorAll(".exercise-delete").forEach((btn) => {
    btn.addEventListener("click", async () => {
      tg.HapticFeedback.impactOccurred("light");
      try {
        await api("DELETE", `/exercises/${btn.dataset.exerciseId}`);
        await loadExercises();
        showToast("Exercise deleted");
      } catch (e) {
        showToast(e.message);
      }
    });
  });
}

async function renderHistory() {
  try {
    const data = await api("GET", "/workouts");
    const container = document.getElementById("history-list");
    const noHistory = document.getElementById("no-history");
    container.innerHTML = "";

    if (!data.workouts || data.workouts.length === 0) {
      noHistory.style.display = "block";
      return;
    }
    noHistory.style.display = "none";

    data.workouts.forEach((w) => {
      const card = document.createElement("div");
      card.className = "history-card";

      const date = new Date(w.started_at + "Z");
      const dateStr = date.toLocaleDateString(undefined, {
        weekday: "short",
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      });

      let exercisesHtml = "";
      if (w.summary && w.summary.exercises) {
        for (const [name, sets] of Object.entries(w.summary.exercises)) {
          const setsStr = sets
            .map((s) => `${s.reps}×${s.weight}kg`)
            .join(", ");
          exercisesHtml += `
            <div class="history-exercise">
              <div class="history-exercise-name">${name}</div>
              <div class="history-exercise-sets">${setsStr}</div>
            </div>
          `;
        }
      }

      card.innerHTML = `
        <div class="history-card-header">
          <span class="history-date">${dateStr}</span>
          <span class="history-volume">${w.summary?.total_volume || 0} kg total</span>
        </div>
        ${exercisesHtml}
      `;
      container.appendChild(card);
    });
  } catch (e) {
    console.error("Failed to load history", e);
  }
}

// ── Workout flow ────────────────────────────────────────────────

function showWorkoutState(active) {
  document.getElementById("no-workout").style.display = active ? "none" : "block";
  document.getElementById("active-workout").style.display = active ? "block" : "none";
}

async function refreshWorkout() {
  try {
    const data = await api("GET", "/workouts/active");
    activeWorkout = data.workout;
    if (activeWorkout) {
      showWorkoutState(true);
      startTimer(activeWorkout.started_at);
      const setsData = await api("GET", `/workouts/${activeWorkout.id}/sets`);
      renderSets(setsData.sets);
    } else {
      showWorkoutState(false);
      stopTimer();
    }
  } catch (e) {
    showWorkoutState(false);
    stopTimer();
  }
}

// ── Event listeners ─────────────────────────────────────────────

// Start workout
document.getElementById("btn-start-workout").addEventListener("click", async () => {
  tg.HapticFeedback.impactOccurred("medium");
  try {
    const data = await api("POST", "/workouts");
    activeWorkout = data.workout;
    showWorkoutState(true);
    startTimer(activeWorkout.started_at);
    showToast("Workout started!");
  } catch (e) {
    showToast(e.message);
  }
});

// Finish workout
document.getElementById("btn-finish-workout").addEventListener("click", async () => {
  tg.HapticFeedback.notificationOccurred("success");
  try {
    await api("POST", `/workouts/${activeWorkout.id}/finish`);
    activeWorkout = null;
    showWorkoutState(false);
    stopTimer();
    showToast("Workout finished!");
    renderHistory();
  } catch (e) {
    showToast(e.message);
  }
});

// Add set
document.getElementById("btn-add-set").addEventListener("click", async () => {
  const exerciseId = document.getElementById("sel-exercise").value;
  const reps = parseInt(document.getElementById("inp-reps").value);
  const weight = parseFloat(document.getElementById("inp-weight").value);

  if (!exerciseId) {
    showToast("Pick an exercise first");
    tg.HapticFeedback.notificationOccurred("error");
    return;
  }
  if (!reps || reps < 1) {
    showToast("Enter valid reps");
    tg.HapticFeedback.notificationOccurred("error");
    return;
  }

  tg.HapticFeedback.impactOccurred("light");
  try {
    await api("POST", `/workouts/${activeWorkout.id}/sets`, {
      exercise_id: parseInt(exerciseId),
      reps,
      weight: weight || 0,
    });
    await refreshWorkout();
    showToast(`${reps} × ${weight} kg logged`);
  } catch (e) {
    showToast(e.message);
  }
});

// Add exercise
document.getElementById("btn-add-exercise").addEventListener("click", async () => {
  const input = document.getElementById("inp-exercise-name");
  const name = input.value.trim();
  if (!name) {
    showToast("Enter exercise name");
    tg.HapticFeedback.notificationOccurred("error");
    return;
  }

  tg.HapticFeedback.impactOccurred("light");
  try {
    await api("POST", "/exercises", { name });
    input.value = "";
    await loadExercises();
    showToast(`${name} added`);
  } catch (e) {
    showToast(e.message);
  }
});

// Enter key to add exercise
document.getElementById("inp-exercise-name").addEventListener("keydown", (e) => {
  if (e.key === "Enter") document.getElementById("btn-add-exercise").click();
});

// ── Data loading ────────────────────────────────────────────────

async function loadExercises() {
  try {
    const data = await api("GET", "/exercises");
    exercises = data.exercises || [];
    renderExerciseSelect();
    renderExercisesList();
  } catch (e) {
    console.error("Failed to load exercises", e);
  }
}

// ── Init ────────────────────────────────────────────────────────
async function init() {
  if (!userId) return;
  await loadExercises();
  await refreshWorkout();
  await renderHistory();
}

init();
