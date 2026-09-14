// Initialize Icons
lucide.createIcons();

// --- Tab Navigation ---
const navItems = document.querySelectorAll('.nav-item');
const tabContents = document.querySelectorAll('.tab-content');

navItems.forEach(function(item) {
  item.addEventListener('click', function() {
    navItems.forEach(function(i) { i.classList.remove('active'); });
    tabContents.forEach(function(c) { c.classList.remove('active'); });

    item.classList.add('active');
    document.getElementById(item.dataset.tab).classList.add('active');
  });
});

// --- Kanban Task Management & Drag-and-Drop ---
const taskLists = document.querySelectorAll('.task-list');
const addTaskBtn = document.getElementById('add-task-btn');
const taskModal = document.getElementById('task-modal');
const closeModal = document.getElementById('close-modal');
const taskForm = document.getElementById('task-form');

// Default initial tasks
const tasks = [
  { id: '1', title: 'Migrate DB to Postgres v15', assignee: 'Dev Ops', points: 5, status: 'backlog' },
  { id: '2', title: 'Implement Auth Refresh Tokens', assignee: 'Backend Lead', points: 3, status: 'in-progress' },
  { id: '3', title: 'UI Audit on Dashboard', assignee: 'Frontend Dev', points: 2, status: 'review' }
];

function renderTasks() {
  taskLists.forEach(function(list) { list.innerHTML = ''; });

  tasks.forEach(function(task) {
    const card = document.createElement('div');
    card.className = 'task-card';
    card.draggable = true;
    card.dataset.id = task.id;

    const titleDiv = document.createElement('div');
    titleDiv.className = 'task-title';
    titleDiv.textContent = task.title;

    const footerDiv = document.createElement('div');
    footerDiv.className = 'task-footer';

    const assigneeSpan = document.createElement('span');
    assigneeSpan.textContent = '👤 ' + task.assignee;

    const pointsSpan = document.createElement('span');
    pointsSpan.className = 'points-tag';
    pointsSpan.textContent = task.points + ' pts';

    footerDiv.appendChild(assigneeSpan);
    footerDiv.appendChild(pointsSpan);

    card.appendChild(titleDiv);
    card.appendChild(footerDiv);

    card.addEventListener('dragstart', function(e) {
      e.dataTransfer.setData('text/plain', task.id);
    });

    const targetList = document.getElementById('list-' + task.status);
    if (targetList) {
      targetList.appendChild(card);
    }
  });
}

// Drag & Drop event listeners
taskLists.forEach(function(list) {
  list.addEventListener('dragover', function(e) {
    e.preventDefault();
  });
  
  list.addEventListener('drop', function(e) {
    e.preventDefault();
    const taskId = e.dataTransfer.getData('text/plain');
    const newStatus = list.id.replace('list-', '');
    
    const task = tasks.find(function(t) { return t.id === taskId; });
    if (task) {
      task.status = newStatus;
      renderTasks();
    }
  });
});

// Modal Logic
addTaskBtn.addEventListener('click', function() {
  taskModal.classList.add('active');
});

closeModal.addEventListener('click', function() {
  taskModal.classList.remove('active');
});

taskForm.addEventListener('submit', function(e) {
  e.preventDefault();
  const newTask = {
    id: Date.now().toString(),
    title: document.getElementById('task-title').value,
    assignee: document.getElementById('task-assignee').value,
    points: document.getElementById('task-points').value,
    status: 'backlog'
  };
  
  tasks.push(newTask);
  renderTasks();
  taskModal.classList.remove('active');
  taskForm.reset();
});

// --- Notion-style Document Block Extension ---
const addCodeBlockBtn = document.getElementById('add-code-block');
const blocksContainer = document.getElementById('blocks-container');

addCodeBlockBtn.addEventListener('click', function() {
  const codeBlock = document.createElement('div');
  codeBlock.className = 'block code-block';

  const header = document.createElement('div');
  header.className = 'code-header';

  const titleSpan = document.createElement('span');
  titleSpan.textContent = 'Snippet / Command';

  const langSpan = document.createElement('span');
  langSpan.className = 'lang-tag';
  langSpan.textContent = 'Code';

  header.appendChild(titleSpan);
  header.appendChild(langSpan);

  const pre = document.createElement('pre');
  pre.contentEditable = "true";

  const code = document.createElement('code');
  code.textContent = '// Add your code or log output here...';

  pre.appendChild(code);
  codeBlock.appendChild(header);
  codeBlock.appendChild(pre);

  blocksContainer.appendChild(codeBlock);
});

// --- Time Tracking & Focus Timer ---
let timerInterval = null;
let secondsRemaining = 25 * 60; // 25 Minutes

const timeDisplay = document.getElementById('time-display');
const startBtn = document.getElementById('start-timer');
const pauseBtn = document.getElementById('pause-timer');
const resetBtn = document.getElementById('reset-timer');

function updateTimerDisplay() {
  const mins = Math.floor(secondsRemaining / 60);
  const secs = secondsRemaining % 60;
  timeDisplay.textContent = mins.toString().padStart(2, '0') + ':' + secs.toString().padStart(2, '0');
}

startBtn.addEventListener('click', function() {
  if (timerInterval) return;
  timerInterval = setInterval(function() {
    if (secondsRemaining > 0) {
      secondsRemaining--;
      updateTimerDisplay();
    } else {
      clearInterval(timerInterval);
      timerInterval = null;
      alert('Focus session complete!');
    }
  }, 1000);
});

pauseBtn.addEventListener('click', function() {
  clearInterval(timerInterval);
  timerInterval = null;
});

resetBtn.addEventListener('click', function() {
  clearInterval(timerInterval);
  timerInterval = null;
  secondsRemaining = 25 * 60;
  updateTimerDisplay();
});

// Initial Render
renderTasks();