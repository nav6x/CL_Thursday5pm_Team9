// ---- Guard: must be logged in ----
if (!getToken()) window.location.href = "login.html";

const user = getUser();
document.getElementById("userName").textContent = user?.email || "";
document.getElementById("logoutBtn").addEventListener("click", () => {
  clearSession();
  window.location.href = "login.html";
});

let currentProject = null;
let currentRole = null;
let projectMembers = [];
let activeColumnIdForNewTask = null;

const boardEl = document.getElementById("board");
const modalOverlay = document.getElementById("taskModalOverlay");
const taskForm = document.getElementById("taskForm");
const assigneesSelect = document.getElementById("taskAssignees");

init();

function showLoadingSkeleton() {
  boardEl.innerHTML = `
    <div class="board-loading">
      <div class="skeleton-column"></div>
      <div class="skeleton-column"></div>
      <div class="skeleton-column"></div>
    </div>`;
}

async function init() {
  showLoadingSkeleton();
  try {
    // For this MVP we load the first project the user belongs to.
    // A project switcher dropdown is the natural next addition here.
    const projects = await api("/projects");
    if (!projects.length) {
      boardEl.innerHTML = `
        <div class="board-empty">
          <h2>No project yet</h2>
          <p>Ask a Project Leader to add you to their board, or create your
          own project to get started.</p>
        </div>`;
      return;
    }
    currentProject = projects[0];
    currentRole = currentProject.my_role;

    document.getElementById("projectName").innerHTML =
      `${currentProject.name} <span class="role-badge">${currentRole === "leader" ? "Project Leader" : "Developer"}</span>`;

    projectMembers = (await api(`/projects/${currentProject.id}/members`)).map(m => m.profiles);
    populateAssigneeOptions();

    await renderBoard();
  } catch (err) {
    boardEl.innerHTML = `
      <div class="board-empty">
        <h2>Couldn't load the board</h2>
        <p>${err.message}</p>
      </div>`;
  }
}

async function renderBoard() {
  const [columns, tasks] = await Promise.all([
    api(`/projects/${currentProject.id}/columns`),
    api(`/projects/${currentProject.id}/tasks`),
  ]);

  boardEl.innerHTML = "";

  columns.forEach(column => {
    const columnTasks = tasks.filter(t => t.column_id === column.id);
    boardEl.appendChild(renderColumn(column, columnTasks));
  });

  // Leaders can grow the board with new columns; Developers work
  // within the structure the Leader has set up.
  if (currentRole === "leader") {
    const addColBtn = document.createElement("button");
    addColBtn.className = "add-column";
    addColBtn.textContent = "+ Add column";
    addColBtn.addEventListener("click", handleAddColumn);
    boardEl.appendChild(addColBtn);
  }
}

function renderColumn(column, tasks) {
  const el = document.createElement("div");
  el.className = "column";
  el.dataset.columnId = column.id;

  el.innerHTML = `
    <div class="column-header">
      <h2>${escapeHtml(column.name)}</h2>
      <span class="column-count">${tasks.length}</span>
    </div>
    <div class="task-list"></div>
  `;

  const list = el.querySelector(".task-list");
  if (tasks.length === 0) {
    const empty = document.createElement("p");
    empty.className = "empty-column";
    empty.textContent = "Nothing pinned here yet.";
    list.appendChild(empty);
  } else {
    tasks.forEach(task => list.appendChild(renderTaskCard(task)));
  }

  const addTaskBtn = document.createElement("button");
  addTaskBtn.className = "add-task-btn";
  addTaskBtn.textContent = "+ Add a task";
  addTaskBtn.addEventListener("click", () => openTaskModal(column.id));
  el.appendChild(addTaskBtn);

  // Drop target for dragging cards between columns
  el.addEventListener("dragover", (e) => e.preventDefault());
  el.addEventListener("drop", async (e) => {
    e.preventDefault();
    const taskId = e.dataTransfer.getData("text/task-id");
    if (!taskId) return;
    try {
      await api(`/projects/${currentProject.id}/tasks/${taskId}`, {
        method: "PATCH",
        body: { column_id: column.id },
      });
      renderBoard();
    } catch (err) {
      showToast(err.message, "error");
    }
  });

  return el;
}

function renderTaskCard(task) {
  const card = document.createElement("div");
  card.className = "task-card";
  card.draggable = true;
  card.addEventListener("dragstart", (e) => {
    e.dataTransfer.setData("text/task-id", task.id);
  });

  const initials = (name) => name.split(" ").map(p => p[0]).slice(0, 2).join("").toUpperCase();

  card.innerHTML = `
    <span class="pin-dot ${task.priority}"></span>
    <h3>${escapeHtml(task.name)}</h3>
    ${task.description ? `<p class="desc">${escapeHtml(task.description)}</p>` : ""}
    <div class="task-meta">
      <span class="priority-chip ${task.priority}">${task.priority}</span>
      <span class="story-points">${task.story_points}</span>
    </div>
    <div class="assignee-stack">
      ${task.assignees.map(a => `<span class="avatar" title="${escapeHtml(a.full_name)}">${initials(a.full_name)}</span>`).join("")}
    </div>
  `;
  return card;
}

// ---- Task creation modal ----

function populateAssigneeOptions() {
  assigneesSelect.innerHTML = projectMembers
    .map(m => `<option value="${m.id}">${escapeHtml(m.full_name)}</option>`)
    .join("");
}

function openTaskModal(columnId) {
  activeColumnIdForNewTask = columnId;
  taskForm.reset();
  modalOverlay.classList.add("open");
}

document.getElementById("cancelTaskBtn").addEventListener("click", () => {
  modalOverlay.classList.remove("open");
});

taskForm.addEventListener("submit", async (e) => {
  e.preventDefault();

  const selectedAssignees = Array.from(assigneesSelect.selectedOptions).map(o => o.value);
  const saveBtn = taskForm.querySelector('button[type="submit"]');
  const originalLabel = saveBtn.textContent;
  saveBtn.disabled = true;
  saveBtn.textContent = "Saving…";

  try {
    await api(`/projects/${currentProject.id}/tasks`, {
      method: "POST",
      body: {
        column_id: activeColumnIdForNewTask,
        name: document.getElementById("taskName").value.trim(),
        description: document.getElementById("taskDescription").value.trim(),
        priority: document.getElementById("taskPriority").value,
        story_points: parseInt(document.getElementById("taskPoints").value, 10) || 0,
        assignee_ids: selectedAssignees,
      },
    });
    modalOverlay.classList.remove("open");
    showToast("Task pinned to the board.", "success");
    renderBoard();
  } catch (err) {
    showToast(err.message, "error");
  } finally {
    saveBtn.disabled = false;
    saveBtn.textContent = originalLabel;
  }
});

// ---- Add column (Leader only — button is only rendered for leaders,
// but the real enforcement happens server-side in require_role) ----

async function handleAddColumn() {
  const name = prompt("New column name:");
  if (!name) return;
  try {
    await api(`/projects/${currentProject.id}/columns`, { method: "POST", body: { name } });
    showToast(`"${name}" column added.`, "success");
    renderBoard();
  } catch (err) {
    showToast(err.message, "error");
  }
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str || "";
  return div.innerHTML;
}
