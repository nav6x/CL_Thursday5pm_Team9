// Navigation setup
const navItems = document.querySelectorAll('.nav-item[data-tab]');
const tabPages = document.querySelectorAll('.tab-page');
const currentPageTitle = document.getElementById('current-page-title');

navItems.forEach(item => {
  item.addEventListener('click', (e) => {
    e.preventDefault();
    navItems.forEach(i => i.classList.remove('active'));
    tabPages.forEach(p => p.classList.remove('active'));

    item.classList.add('active');
    const tabId = item.dataset.tab;
    document.getElementById('tab-' + tabId).classList.add('active');

    // Update page path title
    if (tabId === 'dashboard') currentPageTitle.textContent = 'Sprint Kanban';
    if (tabId === 'specs') currentPageTitle.textContent = 'Technical Specs';
    if (tabId === 'timer') currentPageTitle.textContent = 'Focus & Time Track';
  });
});

// Kanban Tasks Data
const tasks = [
  { id: '1', title: 'Migrate DB to Postgres v15', assignee: 'Dev Ops', points: 5, status: 'backlog' },
  { id: '2', title: 'Implement Auth Refresh Tokens', assignee: 'Backend Lead', points: 3, status: 'in-progress' },
  { id: '3', title: 'UI Audit on Dashboard', assignee: 'Frontend Dev', points: 2, status: 'review' }
];

function renderTasks() {
  document.querySelectorAll('.card-container').forEach(c => c.innerHTML = '');

  tasks.forEach(task => {
    const card = document.createElement('div');
    card.className = 'task-card';
    card.draggable = true;
    card.dataset.id = task.id;

    const title = document.createElement('div');
    title.className = 'task-title';
    title.textContent = task.title;

    const footer = document.createElement('div');
    footer.className = 'task-footer';
    footer.innerHTML = `<span>👤 ${task.assignee}</span> <span class="pill pill-grey">${task.points} pts</span>`;

    card.appendChild(title);
    card.appendChild(footer);

    card.addEventListener('dragstart', (e) => {
      e.dataTransfer.setData('text/plain', task.id);
    });

    const targetList = document.getElementById('list-' + task.status);
    if (targetList) targetList.appendChild(card);
  });
}

// Drag & Drop
document.querySelectorAll('.kanban-col').forEach(col => {
  col.addEventListener('dragover', (e) => e.preventDefault());
  col.addEventListener('drop', (e) => {
    e.preventDefault();
    const id = e.dataTransfer.getData('text/plain');
    const status = col.id.replace('col-', '');
    const task = tasks.find(t => t.id === id);
    if (task) {
      task.status = status;
      renderTasks();
    }
  });
});

// Modal Actions
const modal = document.getElementById('task-modal');
document.getElementById('add-task-btn').onclick = () => modal.classList.add('active');
document.getElementById('close-modal-btn').onclick = () => modal.classList.remove('active');

document.getElementById('task-form').onsubmit = (e) => {
  e.preventDefault();
  tasks.push({
    id: Date.now().toString(),
    title: document.getElementById('task-title').value,
    assignee: document.getElementById('task-assignee').value,
    points: document.getElementById('task-points').value,
    status: 'backlog'
  });
  renderTasks();
  modal.classList.remove('active');
  e.target.reset();
};

// Add Code Block in Specs
document.getElementById('add-block-btn').onclick = () => {
  const block = document.createElement('div');
  block.className = 'block code-block';
  block.innerHTML = `
    <div class="code-top"><span>New Snippet</span><span class="lang-label">Code</span></div>
    <pre contenteditable="true"><code>// Type code here...</code></pre>
  `;
  document.getElementById('editor-blocks').appendChild(block);
};

// Focus Timer
let seconds = 1500;
let timer = null;
const display = document.getElementById('timer-display');

function updateDisplay() {
  const m = Math.floor(seconds / 60).toString().padStart(2, '0');
  const s = (seconds % 60).toString().padStart(2, '0');
  display.textContent = `${m}:${s}`;
}

document.getElementById('btn-start').onclick = () => {
  if (timer) return;
  timer = setInterval(() => {
    if (seconds > 0) {
      seconds--;
      updateDisplay();
    }
  }, 1000);
};

document.getElementById('btn-pause').onclick = () => {
  clearInterval(timer);
  timer = null;
};

document.getElementById('btn-reset').onclick = () => {
  clearInterval(timer);
  timer = null;
  seconds = 1500;
  updateDisplay();
};

renderTasks();