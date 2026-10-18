
(function () {
  if (typeof getToken !== "function" || !getToken()) return;

  const POLL_MS = 15000;
  const ICONS = {
    task_created: "🆕",
    task_moved: "➡️",
    task_updated: "✏️",
    task_commented: "💬",
    task_assigned: "👤",
    task_deleted: "🗑️",
    project_member_added: "📁",
    role_changed: "🔑",
  };


  const styles = document.createElement("link");
  styles.rel = "stylesheet";
  styles.href = "static/css/notifications.css";
  document.head.appendChild(styles);

  const wrapper = document.createElement("div");
  wrapper.className = "notif-wrapper";
  wrapper.innerHTML = `
    <button type="button" class="icon-btn notif-bell" id="notifBell" aria-label="Notifications" aria-haspopup="true">
      <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor"
           stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"></path>
        <path d="M13.73 21a2 2 0 0 1-3.46 0"></path>
      </svg>
      <span class="notif-badge" id="notifBadge" hidden>0</span>
    </button>
    <div class="notif-panel" id="notifPanel" hidden>
      <div class="notif-panel-header">
        <h4>Notifications</h4>
        <button type="button" class="btn-ghost" id="notifMarkAll">Mark all as read</button>
      </div>
      <div class="notif-list" id="notifList"></div>
    </div>
  `;

  const host =
    document.querySelector(".topbar-actions") ||
    document.querySelector(".topbar-user") ||
    document.querySelector(".topbar");
  if (!host) return;
  if (host.classList.contains("topbar")) host.appendChild(wrapper);
  else host.insertBefore(wrapper, host.firstChild);

  const bell = wrapper.querySelector("#notifBell");
  const badge = wrapper.querySelector("#notifBadge");
  const panel = wrapper.querySelector("#notifPanel");
  const list = wrapper.querySelector("#notifList");
  const markAllBtn = wrapper.querySelector("#notifMarkAll");


  let items = [];
  let unreadCount = 0;
  let seenIds = null; // null until the first load, so old items don't toast


  function timeAgo(iso) {
    return typeof formatCommentTime === "function" ? formatCommentTime(iso) : "";
  }

  function renderBadge() {
    badge.hidden = unreadCount === 0;
    badge.textContent = unreadCount > 99 ? "99+" : String(unreadCount);
    bell.setAttribute(
      "aria-label",
      unreadCount ? `Notifications (${unreadCount} unread)` : "Notifications"
    );
    markAllBtn.disabled = unreadCount === 0;
  }

  function renderList() {
    if (!items.length) {
      list.innerHTML = `<div class="notif-empty">You're all caught up.</div>`;
      return;
    }
    list.innerHTML = items
      .map((n) => {
        const projectName = n.projects && n.projects.name ? `${escapeHtml(n.projects.name)} · ` : "";
        return `
          <button type="button" class="notif-item ${n.is_read ? "" : "unread"}" data-id="${escapeHtml(n.id)}">
            <span class="notif-icon">${ICONS[n.type] || "🔔"}</span>
            <span class="notif-body">
              <span class="notif-message">${escapeHtml(n.message)}</span>
              <span class="notif-meta">${projectName}${escapeHtml(timeAgo(n.created_at))}</span>
            </span>
            ${n.is_read ? "" : `<span class="notif-dot" aria-label="Unread"></span>`}
          </button>`;
      })
      .join("");
  }

  function render() {
    renderBadge();
    renderList();
  }


  function announce(arrivals) {
    if (!arrivals.length) return;

    if (arrivals.length <= 2) arrivals.forEach((n) => showToast(n.message, "success", 5000));
    else showToast(`${arrivals.length} new notifications`, "success", 5000);

    // Keep the board itself fresh when a teammate changed something here.
    const modalOpen = document.getElementById("taskModalOverlay")?.classList.contains("open");
    if (modalOpen || !currentProject) return;

    const accessChanged = arrivals.some(
      (n) => n.type === "project_member_added" || n.type === "role_changed"
    );
    if (accessChanged) {
      init(currentProject.id); // refreshes the project switcher + role badge
    } else if (arrivals.some((n) => n.project_id === currentProject.id)) {
      renderBoard().catch(() => {});
    }
  }

  async function load(announceNew) {
    let data;
    try {
      data = await api("/notifications?limit=30");
    } catch (err) {
      return; // transient failure: try again next poll
    }

    const fresh = data.notifications || [];
    unreadCount = data.unread_count || 0;

    if (announceNew && seenIds) {
      announce(fresh.filter((n) => !n.is_read && !seenIds.has(n.id)));
    }
    seenIds = new Set(fresh.map((n) => n.id));
    items = fresh;
    render();
  }

 

  async function markRead(n) {
    if (n.is_read) return;
    n.is_read = true;
    unreadCount = Math.max(0, unreadCount - 1);
    render();
    try {
      await api(`/notifications/${n.id}/read`, { method: "POST" });
    } catch (err) {
      n.is_read = false;
      unreadCount += 1;
      render();
    }
  }

  async function markAllRead() {
    const before = items.map((n) => n.is_read);
    const beforeCount = unreadCount;
    items.forEach((n) => (n.is_read = true));
    unreadCount = 0;
    render();
    try {
      await api("/notifications/read-all", { method: "POST" });
    } catch (err) {
      items.forEach((n, i) => (n.is_read = before[i]));
      unreadCount = beforeCount;
      render();
      showToast(err.message, "error");
    }
  }

  async function openNotification(n) {
    markRead(n);
    panel.hidden = true;

    // Jump to the right project, then open the task if it still exists.
    if (n.project_id && currentProject && n.project_id !== currentProject.id) {
      await init(n.project_id);
    }
    if (n.task_id) {
      const task = cachedTasks.find((t) => t.id === n.task_id);
      if (task) openTaskModal(task.column_id, task);
    }
  }


  bell.addEventListener("click", () => {
    panel.hidden = !panel.hidden;
    if (!panel.hidden) load(false);
  });

  markAllBtn.addEventListener("click", markAllRead);

  list.addEventListener("click", (e) => {
    const row = e.target.closest(".notif-item");
    if (!row) return;
    const n = items.find((x) => x.id === row.dataset.id);
    if (n) openNotification(n);
  });

  document.addEventListener("click", (e) => {
    if (!wrapper.contains(e.target)) panel.hidden = true;
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") panel.hidden = true;
  });

  // Poll while the tab is visible; catch up immediately when it regains focus.
  setInterval(() => {
    if (!document.hidden) load(true);
  }, POLL_MS);
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) load(true);
  });

  load(false);
})();