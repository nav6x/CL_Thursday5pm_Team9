// Initialize Icon Suite
lucide.createIcons();

// --- Tab Navigation ---
const navItems = document.querySelectorAll('.nav-item');
const tabContents = document.querySelectorAll('.tab-content');

navItems.forEach(item => {
  item.addEventListener('click', () => {
    navItems.forEach(i => i.classList.remove('active'));
    tabContents.forEach(c => c.classList.remove('active'));

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
  taskLists.forEach(list => list.innerHTML = '');

  tasks.forEach(task => {
    const card = document.createElement('div');
    card.className = 'task-card';
    card.draggable = true;
    card.dataset.id = task.id;
    card.innerHTML = `