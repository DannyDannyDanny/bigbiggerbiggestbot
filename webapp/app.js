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

// ── Event logging (fire-and-forget) ─────────────────────────────
function logEvent(kind, data) {
  if (!userId) return;
  try {
    fetch(API + "/events", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Telegram-Init-Data": tg.initData,
      },
      body: JSON.stringify({ kind, data: data || null }),
      keepalive: true,
    }).catch(() => {});
  } catch (e) {
    // Never let logging break anything
  }
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

// ── Draft persistence (localStorage) ────────────────────────────
const DRAFT_EXPIRY_MS = 24 * 60 * 60 * 1000; // 24 hours

function draftKey() {
  return "draft_workout_" + userId;
}

function saveDraft() {
  if (!userId) return;
  try {
    const draft = {
      workout,
      currentExercise,
      currentSets: getCurrentSets(),
      note: noteInput?.value || "",
      editingWorkoutId,
      activeView: document.querySelector(".tab.active")?.dataset.view || "log",
      rawDetailsOpen: document.getElementById("raw-details")?.open || false,
      lastSetAt,
      savedAt: Date.now(),
    };
    localStorage.setItem(draftKey(), JSON.stringify(draft));
  } catch (e) {
    console.warn("Failed to save draft", e);
  }
}

function clearDraft() {
  if (!userId) return;
  try {
    localStorage.removeItem(draftKey());
  } catch (e) {
    console.warn("Failed to clear draft", e);
  }
}

function restoreDraft() {
  if (!userId) return false;
  try {
    const raw = localStorage.getItem(draftKey());
    if (!raw) return false;

    const draft = JSON.parse(raw);

    // Expire old drafts
    if (draft.savedAt && Date.now() - draft.savedAt > DRAFT_EXPIRY_MS) {
      clearDraft();
      return false;
    }

    // Restore completed exercises
    if (Array.isArray(draft.workout) && draft.workout.length > 0) {
      workout = draft.workout;
      renderWorkout();
    }

    // Restore in-progress exercise
    if (draft.currentExercise) {
      currentExercise = draft.currentExercise;
      setsSection.classList.remove("hidden");
      setsLabel.textContent = currentExercise.name;
      setsList.innerHTML = "";
      if (Array.isArray(draft.currentSets)) {
        draft.currentSets.forEach((s) => addSetToDOM(s.reps, s.weight_kg));
      }
    }

    // Restore active tab
    if (draft.activeView && draft.activeView !== "log") {
      document.querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
      document.querySelectorAll(".view").forEach((v) => v.classList.remove("active"));
      const tab = document.querySelector(`.tab[data-view="${draft.activeView}"]`);
      if (tab) {
        tab.classList.add("active");
        document.getElementById("view-" + draft.activeView)?.classList.add("active");
        if (draft.activeView === "history") loadHistory();
        if (draft.activeView === "stats") loadStats();
      }
    }

    // Restore note
    if (draft.note && noteInput) {
      noteInput.value = draft.note;
    }

    // Restore editing state
    if (draft.editingWorkoutId) {
      editingWorkoutId = draft.editingWorkoutId;
      updateEditingUI();
    }

    // Restore raw details open state
    if (draft.rawDetailsOpen) {
      const details = document.getElementById("raw-details");
      if (details) details.open = true;
    }

    // Resume rest timer if it was running
    if (currentExercise && getCurrentSets().length > 0 && draft.lastSetAt) {
      resumeRestTimer(draft.lastSetAt);
    }

    syncEditorUI();
    return true;
  } catch (e) {
    console.warn("Failed to restore draft", e);
    clearDraft();
    return false;
  }
}

// ── Tab navigation ──────────────────────────────────────────────
document.querySelectorAll(".tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
    document.querySelectorAll(".view").forEach((v) => v.classList.remove("active"));
    tab.classList.add("active");
    document.getElementById("view-" + tab.dataset.view).classList.add("active");
    tg.HapticFeedback.selectionChanged();
    saveDraft();

    if (tab.dataset.view === "history") loadHistory();
    if (tab.dataset.view === "stats") loadStats();
  });
});

// Persist raw details toggle
document.getElementById("raw-details")?.addEventListener("toggle", saveDraft);

// Persist note changes (debounced)
let noteSaveTimer;
document.getElementById("inp-note")?.addEventListener("input", () => {
  clearTimeout(noteSaveTimer);
  noteSaveTimer = setTimeout(saveDraft, 400);
});

// ── State ───────────────────────────────────────────────────────
let workout = [];
let knownExercises = [];
let currentExercise = null;
let editingWorkoutId = null; // non-null when editing a saved workout
let lastSetAt = null;        // ms-epoch of most recent addSet, or null
let restTimerInterval = null;

// ── Rest timer ──────────────────────────────────────────────────
function _fmtRest(ms) {
  const total = Math.max(0, Math.floor(ms / 1000));
  const m = Math.floor(total / 60);
  const s = total % 60;
  return String(m).padStart(2, "0") + ":" + String(s).padStart(2, "0");
}

function updateRestTimer() {
  const el = document.getElementById("rest-timer");
  if (!el) return;
  const setCount = setsList ? setsList.querySelectorAll(".set-entry").length : 0;
  if (lastSetAt === null || !currentExercise || setCount === 0) {
    el.classList.add("hidden");
    return;
  }
  el.classList.remove("hidden");
  el.textContent = _fmtRest(Date.now() - lastSetAt);
}

function startRestTimer() {
  lastSetAt = Date.now();
  if (!restTimerInterval) {
    restTimerInterval = setInterval(updateRestTimer, 1000);
  }
  updateRestTimer();
}

function stopRestTimer() {
  lastSetAt = null;
  if (restTimerInterval) {
    clearInterval(restTimerInterval);
    restTimerInterval = null;
  }
  updateRestTimer();
}

function resumeRestTimer(ts) {
  // Called during draft restore when lastSetAt was persisted.
  if (typeof ts !== "number" || !Number.isFinite(ts)) return;
  lastSetAt = ts;
  if (!restTimerInterval) {
    restTimerInterval = setInterval(updateRestTimer, 1000);
  }
  updateRestTimer();
}

// ── Structured Log View ─────────────────────────────────────────

const nameInput = document.getElementById("inp-exercise-name");
const nameInputRow = document.querySelector(".exercise-name-row");
const btnAddExercise = document.getElementById("btn-add-exercise");
const autocompleteList = document.getElementById("autocomplete-list");
const setsSection = document.getElementById("sets-section");
const setsLabel = document.getElementById("sets-label");
const setsList = document.getElementById("sets-list");
const repsInput = document.getElementById("inp-reps");
const weightInput = document.getElementById("inp-weight");
const btnAddSet = document.getElementById("btn-add-set");
const btnSaveWorkout = document.getElementById("btn-save-workout");
const workoutExercises = document.getElementById("workout-exercises");
const notesSection = document.getElementById("notes-section");
const noteInput = document.getElementById("inp-note");

// Exercise name input — autocomplete
nameInput.addEventListener("input", () => {
  const val = nameInput.value.trim().toLowerCase();
  autocompleteList.innerHTML = "";
  if (!val) {
    autocompleteList.classList.remove("visible");
    return;
  }

  const matches = knownExercises.filter((n) =>
    n.toLowerCase().includes(val)
  ).slice(0, 8);

  if (matches.length === 0) {
    autocompleteList.classList.remove("visible");
    return;
  }

  matches.forEach((name) => {
    const item = document.createElement("div");
    item.className = "autocomplete-item";
    item.textContent = name;
    item.addEventListener("click", () => {
      nameInput.value = name;
      autocompleteList.innerHTML = "";
      autocompleteList.classList.remove("visible");
      startExercise(name);
    });
    autocompleteList.appendChild(item);
  });
  autocompleteList.classList.add("visible");
});

// Close autocomplete on outside click
document.addEventListener("click", (e) => {
  if (!e.target.closest("#add-exercise-card")) {
    autocompleteList.innerHTML = "";
    autocompleteList.classList.remove("visible");
  }
});

// Enter on name input → start exercise
nameInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") {
    e.preventDefault();
    const name = nameInput.value.trim();
    if (name) {
      autocompleteList.innerHTML = "";
      autocompleteList.classList.remove("visible");
      startExercise(name);
    }
  }
});

btnAddExercise.addEventListener("click", () => {
  const name = nameInput.value.trim();
  if (name) {
    autocompleteList.innerHTML = "";
    autocompleteList.classList.remove("visible");
    startExercise(name);
  }
});

const btnDeleteExercise = document.getElementById("btn-delete-exercise");

function startExercise(name) {
  if (currentExercise && getCurrentSets().length > 0) {
    finishCurrentExercise();
  }

  currentExercise = { name, machine_id: null };
  setsSection.classList.remove("hidden");
  setsLabel.textContent = name;
  setsList.innerHTML = "";
  nameInput.value = "";
  repsInput.value = "";
  weightInput.value = "";
  repsInput.focus();
  notesSection.classList.remove("hidden");
  stopRestTimer();
  syncEditorUI();
  tg.HapticFeedback.selectionChanged();
  saveDraft();
}

function getCurrentSets() {
  return Array.from(setsList.querySelectorAll(".set-entry")).map((el) => ({
    reps: parseInt(el.dataset.reps),
    weight_kg: parseFloat(el.dataset.weight),
  }));
}

// Add a set entry to the DOM (used by both addSet and restoreDraft)
function addSetToDOM(reps, weight) {
  const entry = document.createElement("div");
  entry.className = "set-entry";
  entry.dataset.reps = reps;
  entry.dataset.weight = weight;

  const label = weight
    ? `${reps} x ${fmtWeight(weight)}kg`
    : `${reps} reps`;

  entry.innerHTML = `
    <span class="set-text">${label}</span>
    <button class="btn-remove" title="Remove">&times;</button>
  `;
  entry.querySelector(".btn-remove").addEventListener("click", () => {
    entry.remove();
    syncEditorUI();
    updateRestTimer();
    tg.HapticFeedback.selectionChanged();
    saveDraft();
  });

  setsList.appendChild(entry);
}

// Parse a weight string, accepting both comma and dot as decimal separators
function parseWeight(s) {
  if (!s) return 0;
  return parseFloat(String(s).replace(",", ".")) || 0;
}

// Add set from input fields
function addSet() {
  const reps = parseInt(repsInput.value);
  if (!reps || reps <= 0) {
    showToast("Enter reps");
    tg.HapticFeedback.notificationOccurred("error");
    return;
  }
  const weight = parseWeight(weightInput.value);

  addSetToDOM(reps, weight);
  syncEditorUI();
  startRestTimer();

  logEvent("set.add", {
    exercise: currentExercise?.name || null,
    reps,
    weight_kg: weight,
  });

  repsInput.value = "";
  weightInput.value = weight ? String(weight) : "";
  repsInput.focus();
  tg.HapticFeedback.impactOccurred("light");
  saveDraft();
}

btnAddSet.addEventListener("click", addSet);

repsInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") {
    e.preventDefault();
    if (repsInput.value.trim()) {
      weightInput.focus();
    }
    // Empty reps → stay put, keyboard stays open
  }
});
weightInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") {
    e.preventDefault();
    if (!repsInput.value.trim()) {
      // No reps yet — jump back to reps
      repsInput.focus();
      return;
    }
    addSet();
    // After addSet, focus is already on repsInput (set inside addSet)
  }
});

// Delete the current exercise being edited (discard without saving back)
btnDeleteExercise.addEventListener("click", () => {
  currentExercise = null;
  setsSection.classList.add("hidden");
  setsList.innerHTML = "";
  stopRestTimer();
  renderWorkout();
  tg.HapticFeedback.notificationOccurred("warning");
  saveDraft();
});

// Finish current exercise → add to workout
function finishCurrentExercise() {
  if (!currentExercise) return;
  const sets = getCurrentSets();
  if (sets.length === 0) return;

  workout.push({
    name: currentExercise.name,
    machine_id: null,
    sets_detail: sets,
    sets: sets.length,
    reps: sets[0].reps,
    weight_kg: sets[0].weight_kg,
  });

  currentExercise = null;
  setsSection.classList.add("hidden");
  setsList.innerHTML = "";
  stopRestTimer();
  renderWorkout();
  saveDraft();
}

function syncEditorUI() {
  const currentSetCount = getCurrentSets().length;
  const canSave = workout.length > 0 || currentSetCount > 0;
  btnSaveWorkout.classList.toggle("hidden", !canSave);

  // Hide the "add exercise" input while the current exercise has no sets
  // yet — prevents accidentally discarding it by typing a new name.
  const hideNameInput = currentExercise !== null && currentSetCount === 0;
  nameInputRow.classList.toggle("hidden", hideNameInput);
  if (hideNameInput) {
    autocompleteList.innerHTML = "";
    autocompleteList.classList.remove("visible");
  }

  // Escape hatch whenever a current exercise exists — needed now that the
  // name input is sometimes hidden.
  btnDeleteExercise.classList.toggle("hidden", currentExercise === null);
}

function renderWorkout() {
  workoutExercises.innerHTML = "";
  const hasAny = workout.length > 0 || currentExercise !== null;

  syncEditorUI();

  // Show notes section when there's any workout activity
  if (hasAny) {
    notesSection.classList.remove("hidden");
  } else {
    notesSection.classList.add("hidden");
  }

  workout.forEach((ex, idx) => {
    const card = document.createElement("div");
    card.className = "exercise-card";

    const machine = ex.machine_id ? ` (${ex.machine_id})` : "";
    const setsHtml = ex.sets_detail
      .map((s) => (s.weight_kg ? `${s.reps}x${fmtWeight(s.weight_kg)}kg` : `${s.reps}`))
      .join(", ");

    card.innerHTML = `
      <div class="exercise-card-header">
        <span class="exercise-card-name">${ex.name}${machine}</span>
        <button class="btn-remove btn-edit" title="Edit">&#9998;</button>
      </div>
      <div class="exercise-card-sets">${setsHtml}</div>
    `;

    card.querySelector(".btn-edit").addEventListener("click", (e) => {
      e.stopPropagation();
      editExercise(idx);
    });

    workoutExercises.appendChild(card);
  });
}

// Reopen a saved exercise to add/remove sets
function editExercise(idx) {
  // Finish any in-progress exercise first
  if (currentExercise && getCurrentSets().length > 0) {
    finishCurrentExercise();
  }

  const ex = workout[idx];
  if (!ex) return;

  // Pop it back into the current-exercise slot
  workout.splice(idx, 1);
  currentExercise = { name: ex.name, machine_id: ex.machine_id };
  setsSection.classList.remove("hidden");
  setsLabel.textContent = ex.name;
  setsList.innerHTML = "";
  (ex.sets_detail || []).forEach((s) => addSetToDOM(s.reps, s.weight_kg));
  // Pre-fill weight input with last set's weight for convenience
  const lastWeight = ex.sets_detail?.length ? ex.sets_detail[ex.sets_detail.length - 1].weight_kg : 0;
  weightInput.value = lastWeight ? String(lastWeight) : "";
  repsInput.value = "";
  repsInput.focus();

  stopRestTimer();
  renderWorkout();
  tg.HapticFeedback.selectionChanged();
  saveDraft();
}

// ── Edit saved workout ──────────────────────────────────────────

function editSavedWorkout(workoutData) {
  // Clear any in-progress work
  if (currentExercise && getCurrentSets().length > 0) {
    finishCurrentExercise();
  }
  workout = [];
  currentExercise = null;
  setsList.innerHTML = "";
  setsSection.classList.add("hidden");
  stopRestTimer();

  // Load all exercises from the saved workout
  (workoutData.superset_groups || []).forEach((group) => {
    group.forEach((ex) => {
      workout.push({
        name: ex.name,
        machine_id: ex.machine_id || null,
        sets_detail: ex.sets_detail || [],
        sets: ex.sets || 0,
        reps: ex.reps || 0,
        weight_kg: ex.weight_kg || 0,
      });
    });
  });

  // Set note
  noteInput.value = workoutData.note || "";

  // Mark as editing
  editingWorkoutId = workoutData.id;

  // Switch to Log tab
  document.querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
  document.querySelectorAll(".view").forEach((v) => v.classList.remove("active"));
  document.querySelector('.tab[data-view="log"]').classList.add("active");
  document.getElementById("view-log").classList.add("active");

  renderWorkout();
  updateEditingUI();
  saveDraft();
  tg.HapticFeedback.impactOccurred("medium");
}

function updateEditingUI() {
  const banner = document.getElementById("editing-banner");
  if (editingWorkoutId) {
    if (banner) banner.classList.remove("hidden");
    btnSaveWorkout.textContent = "Update Workout";
  } else {
    if (banner) banner.classList.add("hidden");
    btnSaveWorkout.textContent = "Save Workout";
  }
}

function cancelEdit() {
  editingWorkoutId = null;
  workout = [];
  currentExercise = null;
  noteInput.value = "";
  setsList.innerHTML = "";
  setsSection.classList.add("hidden");
  stopRestTimer();
  renderWorkout();
  updateEditingUI();
  clearDraft();

  // Switch to history tab
  document.querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
  document.querySelectorAll(".view").forEach((v) => v.classList.remove("active"));
  document.querySelector('.tab[data-view="history"]').classList.add("active");
  document.getElementById("view-history").classList.add("active");
  loadHistory();
  tg.HapticFeedback.selectionChanged();
}

document.getElementById("btn-cancel-edit")?.addEventListener("click", cancelEdit);

// Save workout
btnSaveWorkout.addEventListener("click", async () => {
  if (currentExercise && getCurrentSets().length > 0) {
    finishCurrentExercise();
  }

  if (workout.length === 0) {
    showToast("Add at least one exercise");
    tg.HapticFeedback.notificationOccurred("error");
    return;
  }

  tg.HapticFeedback.impactOccurred("medium");

  const superset_groups = workout.map((ex) => [ex]);
  const note = noteInput.value.trim() || null;

  try {
    let data;
    if (editingWorkoutId) {
      data = await api("PUT", `/workouts/${editingWorkoutId}`, { superset_groups, note });
      showToast("Workout updated!");
    } else {
      data = await api("POST", "/workouts", { superset_groups, note });
      showToast("Workout #" + (data.user_number ?? data.workout_id) + " saved!");
    }
    workout = [];
    currentExercise = null;
    editingWorkoutId = null;
    noteInput.value = "";
    stopRestTimer();
    renderWorkout();
    updateEditingUI();
    clearDraft();
    tg.HapticFeedback.notificationOccurred("success");
  } catch (e) {
    showToast(e.message);
    tg.HapticFeedback.notificationOccurred("error");
  }
});

// ── Raw text fallback ───────────────────────────────────────────
document.getElementById("btn-save-raw").addEventListener("click", async () => {
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
    clearDraft();
    showToast("Workout #" + (data.user_number ?? data.workout_id) + " saved!");
    tg.HapticFeedback.notificationOccurred("success");
  } catch (e) {
    showToast(e.message);
    tg.HapticFeedback.notificationOccurred("error");
  }
});

// ── History View ────────────────────────────────────────────────
let historyOffset = 0;

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

      let volume = 0;
      (w.superset_groups || []).forEach((group) => {
        group.forEach((ex) => {
          const details = ex.sets_detail || [];
          if (details.length > 0) {
            details.forEach((s) => { volume += s.reps * s.weight_kg; });
          } else {
            volume += ex.sets * ex.reps * ex.weight_kg;
          }
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
          const details = ex.sets_detail || [];
          let detailStr;
          if (details.length > 0 && !details.every(
            (d) => d.reps === details[0].reps && d.weight_kg === details[0].weight_kg
          )) {
            detailStr = details.map((d) =>
              d.weight_kg ? `${d.reps}x${fmtWeight(d.weight_kg)}kg` : `${d.reps}`
            ).join(", ");
          } else {
            const w = ex.weight_kg;
            detailStr = w ? `${ex.sets}x${ex.reps}x${fmtWeight(w)}kg` : `${ex.sets}x${ex.reps}`;
          }
          groupsHtml += `
            <div class="history-exercise">
              <span class="ex-name">${ex.name}</span>${machine}
              <span class="ex-detail"> &mdash; ${detailStr}</span>
            </div>`;
        });
        groupsHtml += "</div>";
      });

      card.innerHTML = `
        <div class="history-header">
          <span class="history-date">#${w.user_number} &middot; ${dateStr}</span>
          <div class="history-header-right">
            <span class="history-volume">${Math.round(volume)} kg vol</span>
            <button class="btn-remove btn-edit btn-history-edit" title="Edit">&#9998;</button>
            <button class="btn-remove btn-history-delete" title="Delete">&#128465;</button>
          </div>
        </div>
        ${groupsHtml}
      `;

      card.querySelector(".btn-history-edit").addEventListener("click", (e) => {
        e.stopPropagation();
        editSavedWorkout(w);
      });

      card.querySelector(".btn-history-delete").addEventListener("click", (e) => {
        e.stopPropagation();
        confirmDeleteWorkout(w);
      });

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

function confirmDeleteWorkout(w) {
  const label = "Workout #" + (w.user_number ?? w.id);
  const prompt = "Delete " + label + "? This can't be undone.";
  const onConfirm = async (ok) => {
    if (!ok) return;
    try {
      await api("DELETE", "/workouts/" + w.id);
      showToast(label + " deleted");
      tg.HapticFeedback.notificationOccurred("success");
      loadHistory();
    } catch (e) {
      showToast(e.message || "Delete failed");
      tg.HapticFeedback.notificationOccurred("error");
    }
  };
  if (tg && typeof tg.showConfirm === "function") {
    tg.showConfirm(prompt, onConfirm);
  } else {
    onConfirm(window.confirm(prompt));
  }
}

// ── Stats View ──────────────────────────────────────────────────

async function loadStats() {
  try {
    const data = await api("GET", "/stats");
    const container = document.getElementById("stats-content");

    if (data.total_workouts === 0) {
      container.innerHTML = '<div class="empty-state"><p>No workouts yet</p></div>';
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

// ── Helpers ─────────────────────────────────────────────────────
function fmtWeight(w) {
  return w === Math.floor(w) ? Math.floor(w).toString() : w.toString();
}

// ── Version badge ───────────────────────────────────────────────
async function loadVersion() {
  try {
    const res = await fetch(API + "/version");
    if (!res.ok) return;
    const data = await res.json();
    const badge = document.getElementById("version-badge");
    if (badge && data.version) badge.textContent = data.version;
  } catch (e) {
    // Silent — footer just stays empty if unreachable
  }
}

// ── Init ────────────────────────────────────────────────────────
async function init() {
  loadVersion();
  if (!userId) return;
  logEvent("miniapp.open");
  try {
    const data = await api("GET", "/exercises");
    knownExercises = data.exercises || [];
  } catch (e) {
    console.error("Failed to load exercises", e);
  }
  restoreDraft();
}

init();
