if (!getToken()) window.location.href = "index.html";

const user = getUser();
const userNameEl = document.getElementById("userName");
if (userNameEl) userNameEl.textContent = user?.email || "";

const logoutBtn = document.getElementById("logoutBtn");
if (logoutBtn) {
  logoutBtn.addEventListener("click", () => {
    clearSession();
    window.location.href = "index.html";
  });
}

const savedTheme = localStorage.getItem("scrumptious_theme") || "slate";
const savedAccent = localStorage.getItem("scrumptious_accent") || "indigo";
document.documentElement.setAttribute("data-theme", savedTheme);
document.documentElement.setAttribute("data-accent", savedAccent);

let currentProject = null;
let currentRole = null;
let currentAgileRole = "Developer";
let projectMembers = [];
let activeColumnIdForNewTask = null;
let editingTaskId = null;
let cachedTasks = [];
let cachedColumns = [];

let activeFilterTag = "all";
let activeFilterPriority = "all";
let searchFilterText = "";

const boardEl = document.getElementById("board");
const modalOverlay = document.getElementById("taskModalOverlay");
const taskForm = document.getElementById("taskForm");
const assigneesSelect = document.getElementById("taskAssignees");
const projectSelect = document.getElementById("projectSelect");
const newProjectBtn = document.getElementById("newProjectBtn");
const topAddTaskBtn = document.getElementById("topAddTaskBtn");
const deleteTaskBtn = document.getElementById("deleteTaskBtn");
const cancelTaskBtn = document.getElementById("cancelTaskBtn");

const projectModalOverlay = document.getElementById("projectModalOverlay");
const projectForm = document.getElementById("projectForm");
const cancelProjectBtn = document.getElementById("cancelProjectBtn");

const settingsModalOverlay = document.getElementById("settingsModalOverlay");
const settingsBtn = document.getElementById("settingsBtn");
const closeSettingsBtn = document.getElementById("closeSettingsBtn");
const renameProjectForm = document.getElementById("renameProjectForm");
const renameProjectInput = document.getElementById("renameProjectInput");
const deleteProjectBtn = document.getElementById("deleteProjectBtn");
const projectDangerZone = document.getElementById("projectDangerZone");
const addMemberSection = document.getElementById("addMemberSection");
const addMemberForm = document.getElementById("addMemberForm");
const memberListContainer = document.getElementById("memberListContainer");
const workspaceUsersContainer = document.getElementById("workspaceUsersContainer");
const addAllMembersBtn = document.getElementById("addAllMembersBtn");

const tagChipsContainer = document.getElementById("tagChipsContainer");
const customTagInput = document.getElementById("customTagInput");
const addCustomTagBtn = document.getElementById("addCustomTagBtn");

const searchInput = document.getElementById("searchInput");

init();

function getRoleBadgeClass(roleTitle) {
  const lower = (roleTitle || "").toLowerCase().replace(/[\s_]+/g, "-");
  if (lower.includes("scrum")) return "scrum-master";
  if (lower.includes("leader")) return "project-leader";
  if (lower.includes("product") || lower.includes("owner")) return "product-owner";
  if (lower.includes("qa") || lower.includes("test")) return "qa-engineer";
  return "developer";
}

function showLoadingSkeleton() {
  boardEl.innerHTML = `
    <div class="board-loading">
      <div class="skeleton-column"></div>
      <div class="skeleton-column"></div>
      <div class="skeleton-column"></div>
    </div>`;
}

async function init(preferredProjectId = null) {
  showLoadingSkeleton();
  try {
    let projects = await api("/projects");

    if (!projects || projects.length === 0) {
      const created = await api("/projects", {
        method: "POST",
        body: { name: "Sprint 1 Workspace" },
      });
      projects = [created];
    }

    currentProject = preferredProjectId
      ? projects.find(p => p.id === preferredProjectId) || projects[0]
      : projects[0];
    currentRole = currentProject.my_role;
    currentAgileRole = currentProject.my_agile_role || (currentRole === "leader" ? "Project Leader" : "Developer");

    const badgeClass = getRoleBadgeClass(currentAgileRole);
    document.getElementById("projectName").innerHTML =
      `${escapeHtml(currentProject.name)} <span class="role-badge ${badgeClass}" id="roleBadge">${escapeHtml(currentAgileRole)}</span>`;

    if (projectSelect) {
      if (projects.length > 1) {
        projectSelect.style.display = "inline-block";
        projectSelect.innerHTML = projects
          .map(p => `<option value="${p.id}" ${p.id === currentProject.id ? "selected" : ""}>${escapeHtml(p.name)}</option>`)
          .join("");
      } else {
        projectSelect.style.display = "none";
      }
    }

    const isLeaderLevel = currentRole === "leader";
    const isProjectOwner = currentRole === "leader" && (currentAgileRole === "Project Leader" || currentProject.created_by === user?.id);

    if (projectDangerZone) {
      projectDangerZone.style.display = isProjectOwner ? "block" : "none";
    }
    if (addMemberSection) {
      addMemberSection.style.display = isLeaderLevel ? "block" : "none";
    }
    if (addAllMembersBtn) {
      addAllMembersBtn.style.display = isLeaderLevel ? "inline-block" : "none";
    }

    const [membersData, columnsData] = await Promise.all([
      api(`/projects/${currentProject.id}/members`),
      api(`/projects/${currentProject.id}/columns`),
    ]);

    projectMembers = membersData || [];
    populateAssigneeOptions();

    let tasks = await api(`/projects/${currentProject.id}/tasks`);
    if (tasks.length === 0 && columnsData.length > 0) {
      const targetColumn = columnsData.find(c => c.name === "To Do") || columnsData[0];
      await api(`/projects/${currentProject.id}/tasks`, {
        method: "POST",
        body: {
          column_id: targetColumn.id,
          name: "Welcome to Scrumptious",
          description: "[tags:Frontend,Feature] Manage sprints, organize tickets, and collaborate in real-time.",
          priority: "medium",
          story_points: 3,
        },
      });
      tasks = await api(`/projects/${currentProject.id}/tasks`);
    }

    cachedColumns = columnsData;
    cachedTasks = tasks;

    await renderBoard();
  } catch (err) {
    boardEl.innerHTML = `
      <div class="board-empty">
        <h2>Unable to load workspace</h2>
        <p>${escapeHtml(err.message)}</p>
      </div>`;
  }
}

function parseTaskDescription(rawDesc) {
  if (!rawDesc) return { tags: [], desc: "" };
  const match = rawDesc.match(/^\[tags:([^\]]*)\]\s*([\s\S]*)$/);
  if (match) {
    const tags = match[1].split(",").map(t => t.trim()).filter(Boolean);
    return { tags, desc: match[2].trim() };
  }
  return { tags: [], desc: rawDesc.trim() };
}

function packTaskDescription(tags, cleanDesc) {
  if (!tags || tags.length === 0) return cleanDesc;
  return `[tags:${tags.join(",")}] ${cleanDesc}`;
}

async function renderBoard() {
  const [columns, tasks] = await Promise.all([
    api(`/projects/${currentProject.id}/columns`),
    api(`/projects/${currentProject.id}/tasks`),
  ]);

  cachedColumns = columns;
  cachedTasks = tasks;

  boardEl.innerHTML = "";

  columns.forEach(column => {
    const columnTasks = tasks.filter(t => t.column_id === column.id);
    boardEl.appendChild(renderColumn(column, columnTasks));
  });

  if (currentRole === "leader") {
    const addColBtn = document.createElement("button");
    addColBtn.className = "add-column";
    addColBtn.textContent = "+ Add Column";
    addColBtn.addEventListener("click", handleAddColumn);
    boardEl.appendChild(addColBtn);
  }

  applyFilters();
}

function renderColumn(column, tasks) {
  const el = document.createElement("div");
  el.className = "column";
  el.dataset.columnId = column.id;

  const totalPoints = tasks.reduce((sum, t) => sum + (t.story_points || 0), 0);

  el.innerHTML = `
    <div class="column-header">
      <div class="column-header-title">
        <h2>${escapeHtml(column.name)}</h2>
        <span class="column-count">${tasks.length}</span>
      </div>
      <span class="column-pts">${totalPoints} pts</span>
    </div>
    <div class="task-list"></div>
  `;

  const list = el.querySelector(".task-list");
  if (tasks.length === 0) {
    const empty = document.createElement("p");
    empty.className = "empty-column";
    empty.textContent = "No tasks yet in this column";
    list.appendChild(empty);
  } else {
    tasks.forEach(task => list.appendChild(renderTaskCard(task)));
  }

  const addTaskBtn = document.createElement("button");
  addTaskBtn.className = "add-task-btn";
  addTaskBtn.textContent = "+ Add a task";
  addTaskBtn.addEventListener("click", () => openTaskModal(column.id));
  el.appendChild(addTaskBtn);

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

function getTagClass(tag) {
  const lower = tag.toLowerCase();
  if (["frontend", "backend", "bug", "feature", "devops", "design"].includes(lower)) {
    return lower;
  }
  return "general";
}

function renderTaskCard(task) {
  const card = document.createElement("div");
  card.className = `task-card priority-${task.priority || "medium"}`;
  card.dataset.taskId = task.id;
  card.dataset.priority = task.priority || "medium";
  card.draggable = true;

  const { tags, desc } = parseTaskDescription(task.description);
  card.dataset.tags = tags.join(",").toLowerCase();
  card.dataset.name = (task.name || "").toLowerCase();
  card.dataset.desc = desc.toLowerCase();

  card.addEventListener("dragstart", (e) => {
    e.dataTransfer.setData("text/task-id", task.id);
  });

  card.addEventListener("click", (e) => {
    if (!e.target.closest(".avatar")) {
      openTaskModal(task.column_id, task);
    }
  });

  const initials = (name) => {
    if (!name) return "";
    return name.split(" ").map(p => p[0]).slice(0, 2).join("").toUpperCase();
  };

  const tagChipsHtml = tags.length > 0
    ? `<div class="task-tags">${tags.map(t => `<span class="tag-chip ${getTagClass(t)}">${escapeHtml(t)}</span>`).join("")}</div>`
    : "";

  const validAssignees = (task.assignees || []).filter(Boolean);

  card.innerHTML = `
    <h3>${escapeHtml(task.name)}</h3>
    ${tagChipsHtml}
    ${desc ? `<p class="desc">${escapeHtml(desc)}</p>` : ""}
    <div class="task-meta">
      <span class="priority-badge ${task.priority}">${escapeHtml(task.priority)}</span>
      <span class="story-points">${task.story_points ?? 0} pts</span>
    </div>
    <div class="assignee-stack">
      ${validAssignees.map(a => `<span class="avatar" title="${escapeHtml(a.full_name || a.email || '')}">${initials(a.full_name || a.email || 'U')}</span>`).join("")}
    </div>
  `;
  return card;
}

function populateAssigneeOptions() {
  if (!assigneesSelect) return;
  assigneesSelect.innerHTML = projectMembers
    .filter(m => m && m.profiles)
    .map(m => {
      const p = m.profiles;
      const roleName = m.agile_role || (m.role === "leader" ? "Project Leader" : "Developer");
      const label = `${p.full_name || p.email} (${roleName})`;
      return `<option value="${p.id}">${escapeHtml(label)}</option>`;
    })
    .join("");
}

function openTaskModal(columnId, task = null) {
  activeColumnIdForNewTask = columnId;
  editingTaskId = task ? task.id : null;

  resetTagChips();

  if (task) {
    document.getElementById("modalTitle").textContent = "Edit Task";
    document.getElementById("taskName").value = task.name || "";

    const { tags, desc } = parseTaskDescription(task.description);
    document.getElementById("taskDescription").value = desc || "";
    document.getElementById("taskPriority").value = task.priority || "medium";
    document.getElementById("taskPoints").value = task.story_points ?? 1;

    tags.forEach(t => selectOrCreateTagChip(t));

    const assigneeIds = (task.assignees || []).filter(Boolean).map(a => a.id);
    Array.from(assigneesSelect.options).forEach(opt => {
      opt.selected = assigneeIds.includes(opt.value);
    });

    if (deleteTaskBtn) {
      deleteTaskBtn.style.display = currentRole === "leader" || task.created_by === user?.id ? "inline-block" : "none";
    }
  } else {
    document.getElementById("modalTitle").textContent = "New Task";
    taskForm.reset();
    document.getElementById("taskPoints").value = 1;
    Array.from(assigneesSelect.options).forEach(opt => {
      opt.selected = false;
    });
    if (deleteTaskBtn) {
      deleteTaskBtn.style.display = "none";
    }
  }

  modalOverlay.classList.add("open");
}

function resetTagChips() {
  const chips = tagChipsContainer.querySelectorAll(".tag-option-btn");
  chips.forEach(btn => btn.classList.remove("selected"));
}

function selectOrCreateTagChip(tag) {
  const existing = Array.from(tagChipsContainer.querySelectorAll(".tag-option-btn"))
    .find(b => b.dataset.tag.toLowerCase() === tag.toLowerCase());
  if (existing) {
    existing.classList.add("selected");
  } else {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "tag-option-btn selected";
    btn.dataset.tag = tag;
    btn.textContent = tag;
    btn.addEventListener("click", () => btn.classList.toggle("selected"));
    tagChipsContainer.appendChild(btn);
  }
}

if (tagChipsContainer) {
  tagChipsContainer.querySelectorAll(".tag-option-btn").forEach(btn => {
    btn.addEventListener("click", () => btn.classList.toggle("selected"));
  });
}

if (addCustomTagBtn && customTagInput) {
  addCustomTagBtn.addEventListener("click", () => {
    const customTag = customTagInput.value.trim();
    if (!customTag) return;
    selectOrCreateTagChip(customTag);
    customTagInput.value = "";
  });
}

if (cancelTaskBtn) {
  cancelTaskBtn.addEventListener("click", () => {
    modalOverlay.classList.remove("open");
  });
}

if (deleteTaskBtn) {
  deleteTaskBtn.addEventListener("click", async () => {
    if (!editingTaskId) return;
    if (!confirm("Are you sure you want to delete this task?")) return;
    try {
      await api(`/projects/${currentProject.id}/tasks/${editingTaskId}`, {
        method: "DELETE",
      });
      modalOverlay.classList.remove("open");
      showToast("Task deleted.", "success");
      renderBoard();
    } catch (err) {
      showToast(err.message, "error");
    }
  });
}

taskForm.addEventListener("submit", async (e) => {
  e.preventDefault();

  const selectedAssignees = Array.from(assigneesSelect.selectedOptions).map(o => o.value);
  const saveBtn = taskForm.querySelector('button[type="submit"]');
  const originalLabel = saveBtn.textContent;
  saveBtn.disabled = true;
  saveBtn.textContent = "Saving…";

  const selectedTags = Array.from(tagChipsContainer.querySelectorAll(".tag-option-btn.selected"))
    .map(btn => btn.dataset.tag);
  const cleanDescription = document.getElementById("taskDescription").value.trim();
  const packedDescription = packTaskDescription(selectedTags, cleanDescription);

  const taskData = {
    name: document.getElementById("taskName").value.trim(),
    description: packedDescription,
    priority: document.getElementById("taskPriority").value,
    story_points: parseInt(document.getElementById("taskPoints").value, 10) || 0,
  };

  try {
    if (editingTaskId) {
      await api(`/projects/${currentProject.id}/tasks/${editingTaskId}`, {
        method: "PATCH",
        body: taskData,
      });
      if (currentRole === "leader") {
        await api(`/projects/${currentProject.id}/tasks/${editingTaskId}/assignees`, {
          method: "PUT",
          body: { assignee_ids: selectedAssignees },
        });
      }
      showToast("Task updated.", "success");
    } else {
      await api(`/projects/${currentProject.id}/tasks`, {
        method: "POST",
        body: {
          ...taskData,
          column_id: activeColumnIdForNewTask,
          assignee_ids: selectedAssignees,
        },
      });
      showToast("Task created.", "success");
    }
    modalOverlay.classList.remove("open");
    renderBoard();
  } catch (err) {
    showToast(err.message, "error");
  } finally {
    saveBtn.disabled = false;
    saveBtn.textContent = originalLabel;
  }
});

async function handleAddColumn() {
  const name = prompt("Column title:");
  if (!name) return;
  try {
    await api(`/projects/${currentProject.id}/columns`, { method: "POST", body: { name: name.trim() } });
    showToast(`Column "${name.trim()}" added.`, "success");
    renderBoard();
  } catch (err) {
    showToast(err.message, "error");
  }
}

function applyFilters() {
  const cards = document.querySelectorAll(".task-card");
  const query = searchFilterText.trim().toLowerCase();

  cards.forEach(card => {
    const cardName = card.dataset.name || "";
    const cardDesc = card.dataset.desc || "";
    const cardPriority = card.dataset.priority || "";
    const cardTags = (card.dataset.tags || "").split(",").filter(Boolean);

    const matchesSearch = !query || cardName.includes(query) || cardDesc.includes(query);
    const matchesPriority = activeFilterPriority === "all" || cardPriority === activeFilterPriority;
    const matchesTag = activeFilterTag === "all" || cardTags.includes(activeFilterTag.toLowerCase());

    if (matchesSearch && matchesPriority && matchesTag) {
      card.style.display = "";
    } else {
      card.style.display = "none";
    }
  });

  document.querySelectorAll(".column").forEach(col => {
    const visibleCards = col.querySelectorAll('.task-card:not([style*="display: none"])');
    const countBadge = col.querySelector(".column-count");
    if (countBadge) countBadge.textContent = visibleCards.length;
  });
}

if (searchInput) {
  searchInput.addEventListener("input", (e) => {
    searchFilterText = e.target.value;
    applyFilters();
  });
}

document.querySelectorAll("[data-filter-tag]").forEach(btn => {
  btn.addEventListener("click", () => {
    document.querySelectorAll("[data-filter-tag]").forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
    activeFilterTag = btn.dataset.filterTag;
    applyFilters();
  });
});

document.querySelectorAll("[data-filter-priority]").forEach(btn => {
  btn.addEventListener("click", () => {
    document.querySelectorAll("[data-filter-priority]").forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
    activeFilterPriority = btn.dataset.filterPriority;
    applyFilters();
  });
});

if (newProjectBtn) {
  newProjectBtn.addEventListener("click", () => {
    if (projectForm) projectForm.reset();
    if (projectModalOverlay) projectModalOverlay.classList.add("open");
  });
}

if (cancelProjectBtn) {
  cancelProjectBtn.addEventListener("click", () => {
    if (projectModalOverlay) projectModalOverlay.classList.remove("open");
  });
}

if (projectForm) {
  projectForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const nameInput = document.getElementById("newProjectName");
    const name = nameInput ? nameInput.value.trim() : "";
    if (!name) return;
    try {
      const newProj = await api("/projects", {
        method: "POST",
        body: { name },
      });
      if (projectModalOverlay) projectModalOverlay.classList.remove("open");
      showToast(`Project "${name}" created.`, "success");
      await init(newProj.id);
    } catch (err) {
      showToast(err.message, "error");
    }
  });
}

if (projectSelect) {
  projectSelect.addEventListener("change", (e) => {
    init(e.target.value);
  });
}

if (topAddTaskBtn) {
  topAddTaskBtn.addEventListener("click", async () => {
    try {
      const columns = await api(`/projects/${currentProject.id}/columns`);
      if (columns && columns.length > 0) {
        openTaskModal(columns[0].id);
      } else {
        showToast("Create a column first before adding tasks.", "error");
      }
    } catch (err) {
      showToast(err.message, "error");
    }
  });
}

if (settingsBtn) {
  settingsBtn.addEventListener("click", async () => {
    if (renameProjectInput) renameProjectInput.value = currentProject?.name || "";
    await refreshMemberList();
    updateActiveThemeSwatches();
    if (settingsModalOverlay) settingsModalOverlay.classList.add("open");
  });
}

if (closeSettingsBtn) {
  closeSettingsBtn.addEventListener("click", () => {
    if (settingsModalOverlay) settingsModalOverlay.classList.remove("open");
  });
}

document.querySelectorAll(".settings-tab-btn").forEach(btn => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".settings-tab-btn").forEach(b => b.classList.remove("active"));
    document.querySelectorAll(".settings-panel").forEach(p => p.classList.remove("active"));

    btn.classList.add("active");
    const tabName = btn.dataset.tab;
    const targetPanel = document.getElementById(`tab${tabName.charAt(0).toUpperCase() + tabName.slice(1)}`);
    if (targetPanel) targetPanel.classList.add("active");
  });
});

if (renameProjectForm) {
  renameProjectForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const newName = renameProjectInput.value.trim();
    if (!newName) return;
    try {
      await api(`/projects/${currentProject.id}`, {
        method: "PATCH",
        body: { name: newName },
      });
      currentProject.name = newName;
      const badgeClass = getRoleBadgeClass(currentAgileRole);
      document.getElementById("projectName").innerHTML =
        `${escapeHtml(newName)} <span class="role-badge ${badgeClass}">${escapeHtml(currentAgileRole)}</span>`;
      showToast("Project renamed.", "success");
    } catch (err) {
      showToast(err.message, "error");
    }
  });
}

if (deleteProjectBtn) {
  deleteProjectBtn.addEventListener("click", async () => {
    if (!currentProject) return;
    if (!confirm(`Delete "${currentProject.name}"? This action cannot be undone.`)) return;
    try {
      await api(`/projects/${currentProject.id}`, { method: "DELETE" });
      if (settingsModalOverlay) settingsModalOverlay.classList.remove("open");
      showToast("Project deleted.", "success");
      await init();
    } catch (err) {
      showToast(err.message, "error");
    }
  });
}

async function refreshMemberList() {
  if (!memberListContainer) return;
  try {
    const [members, allUsers] = await Promise.all([
      api(`/projects/${currentProject.id}/members`),
      api("/auth/users"),
    ]);

    projectMembers = members || [];
    populateAssigneeOptions();

    const isLeaderLevel = currentRole === "leader";

    if (members.length === 0) {
      memberListContainer.innerHTML = `<div style="font-size:0.85rem; color:var(--ink-muted); padding:0.5rem 0;">No members found.</div>`;
    } else {
      memberListContainer.innerHTML = members.map(m => {
        const p = m.profiles;
        if (!p) return "";
        const roleName = m.agile_role || (m.role === "leader" ? "Project Leader" : "Developer");
        const badgeClass = getRoleBadgeClass(roleName);
        const isMe = p.id === user?.id;

        let actionsHtml = "";
        if (isLeaderLevel) {
          actionsHtml = `
            <div class="member-actions">
              <select class="member-role-select" data-user-id="${p.id}">
                <option value="project_leader" ${roleName === "Project Leader" ? "selected" : ""}>Project Leader</option>
                <option value="scrum_master" ${roleName === "Scrum Master" ? "selected" : ""}>Scrum Master</option>
                <option value="product_owner" ${roleName === "Product Owner" ? "selected" : ""}>Product Owner</option>
                <option value="developer" ${roleName === "Developer" ? "selected" : ""}>Developer</option>
                <option value="qa_engineer" ${roleName === "QA Engineer" ? "selected" : ""}>QA Engineer</option>
              </select>
              ${!isMe ? `<button type="button" class="btn-ghost" data-remove-user-id="${p.id}" style="color:#DC2626; padding:0.2rem 0.5rem;">Remove</button>` : ""}
            </div>
          `;
        } else {
          actionsHtml = `<span class="role-badge ${badgeClass}">${escapeHtml(roleName)}</span>`;
        }

        return `
          <div class="member-row">
            <div class="member-info">
              <div style="display:flex; align-items:center; gap:0.4rem;">
                <span class="member-name">${escapeHtml(p.full_name || p.email)} ${isMe ? "(You)" : ""}</span>
                <span class="role-badge ${badgeClass}">${escapeHtml(roleName)}</span>
              </div>
              <span class="member-email">${escapeHtml(p.email)}</span>
            </div>
            ${actionsHtml}
          </div>
        `;
      }).join("");

      memberListContainer.querySelectorAll(".member-role-select").forEach(select => {
        select.addEventListener("change", async (e) => {
          const uid = e.target.dataset.userId;
          const newRole = e.target.value;
          try {
            await api(`/projects/${currentProject.id}/members/${uid}`, {
              method: "PATCH",
              body: { role: newRole },
            });
            showToast("Member role updated.", "success");
            await refreshMemberList();
            await init(currentProject.id);
          } catch (err) {
            showToast(err.message, "error");
          }
        });
      });

      memberListContainer.querySelectorAll("[data-remove-user-id]").forEach(btn => {
        btn.addEventListener("click", async (e) => {
          const uid = e.target.dataset.removeUserId;
          if (!confirm("Remove this member from the project?")) return;
          try {
            await api(`/projects/${currentProject.id}/members/${uid}`, {
              method: "DELETE",
            });
            showToast("Member removed.", "success");
            await refreshMemberList();
            await init(currentProject.id);
          } catch (err) {
            showToast(err.message, "error");
          }
        });
      });
    }

    if (workspaceUsersContainer) {
      const memberMap = new Map();
      projectMembers.filter(m => m.profiles).forEach(m => {
        memberMap.set(m.profiles.id, m.agile_role || (m.role === "leader" ? "Project Leader" : "Developer"));
      });

      if (!allUsers || allUsers.length === 0) {
        workspaceUsersContainer.innerHTML = `<div style="font-size:0.85rem; color:var(--ink-muted); padding:0.5rem 0;">No other registered users.</div>`;
      } else {
        workspaceUsersContainer.innerHTML = allUsers.map(u => {
          const inProject = memberMap.has(u.id);
          const currentRoleName = memberMap.get(u.id);
          const isMe = u.id === user?.id;
          const cleanName = (u.full_name || "").split("[")[0].trim() || u.email;

          return `
            <div class="member-row">
              <div class="member-info">
                <span class="member-name">${escapeHtml(cleanName)} ${isMe ? "(You)" : ""}</span>
                <span class="member-email">${escapeHtml(u.email)}</span>
              </div>
              <div>
                ${inProject
                  ? `<span class="role-badge ${getRoleBadgeClass(currentRoleName)}">${escapeHtml(currentRoleName)}</span>`
                  : isLeaderLevel
                    ? `<button type="button" class="btn-secondary" data-add-workspace-user-id="${u.id}" style="font-size:0.75rem; padding:0.25rem 0.6rem;">+ Add to Project</button>`
                    : ""
                }
              </div>
            </div>
          `;
        }).join("");

        workspaceUsersContainer.querySelectorAll("[data-add-workspace-user-id]").forEach(btn => {
          btn.addEventListener("click", async (e) => {
            const uid = e.target.dataset.addWorkspaceUserId;
            try {
              await api(`/projects/${currentProject.id}/members`, {
                method: "POST",
                body: { user_id: uid, role: "developer" },
              });
              showToast("Member added to project.", "success");
              await refreshMemberList();
              await init(currentProject.id);
            } catch (err) {
              showToast(err.message, "error");
            }
          });
        });
      }
    }
  } catch (err) {
    memberListContainer.innerHTML = `<div style="font-size:0.85rem; color:#DC2626; padding:0.5rem 0;">${escapeHtml(err.message)}</div>`;
  }
}

if (addAllMembersBtn) {
  addAllMembersBtn.addEventListener("click", async () => {
    try {
      await api(`/projects/${currentProject.id}/members/all`, { method: "POST" });
      showToast("All workspace users added to project.", "success");
      await refreshMemberList();
      await init(currentProject.id);
    } catch (err) {
      showToast(err.message, "error");
    }
  });
}

if (addMemberForm) {
  addMemberForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const emailInput = document.getElementById("newMemberEmail");
    const roleInput = document.getElementById("newMemberRole");
    const email = emailInput ? emailInput.value.trim() : "";
    const role = roleInput ? roleInput.value : "developer";
    if (!email) return;

    try {
      await api(`/projects/${currentProject.id}/members`, {
        method: "POST",
        body: { email, role },
      });
      emailInput.value = "";
      showToast(`Added ${email} to project.`, "success");
      await refreshMemberList();
      await init(currentProject.id);
    } catch (err) {
      showToast(err.message, "error");
    }
  });
}

function updateActiveThemeSwatches() {
  const curTheme = document.documentElement.getAttribute("data-theme") || "slate";
  const curAccent = document.documentElement.getAttribute("data-accent") || "indigo";

  document.querySelectorAll("[data-set-theme]").forEach(c => {
    c.classList.toggle("active", c.dataset.setTheme === curTheme);
  });

  document.querySelectorAll("[data-set-accent]").forEach(s => {
    s.classList.toggle("active", s.dataset.setAccent === curAccent);
  });
}

document.querySelectorAll("[data-set-theme]").forEach(card => {
  card.addEventListener("click", () => {
    const themeName = card.dataset.setTheme;
    document.documentElement.setAttribute("data-theme", themeName);
    localStorage.setItem("scrumptious_theme", themeName);
    updateActiveThemeSwatches();
  });
});

document.querySelectorAll("[data-set-accent]").forEach(swatch => {
  swatch.addEventListener("click", () => {
    const accentName = swatch.dataset.setAccent;
    document.documentElement.setAttribute("data-accent", accentName);
    localStorage.setItem("scrumptious_accent", accentName);
    updateActiveThemeSwatches();
  });
});

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str || "";
  return div.innerHTML;
}