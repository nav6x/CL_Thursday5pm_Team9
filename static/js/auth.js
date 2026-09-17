let mode = "login";

const form = document.getElementById("authForm");
const nameField = document.getElementById("nameField");
const fullNameInput = document.getElementById("fullName");
const formTitle = document.getElementById("formTitle");
const formSubtitle = document.getElementById("formSubtitle");
const submitBtn = document.getElementById("submitBtn");
const switchPrompt = document.getElementById("switchPrompt");
const switchLink = document.getElementById("switchLink");
const errorBox = document.getElementById("formError");

if (getToken()) window.location.href = "board.html";

switchLink.addEventListener("click", (e) => {
  e.preventDefault();
  mode = mode === "login" ? "signup" : "login";
  updateFormMode();
});

function updateFormMode() {
  errorBox.style.display = "none";
  if (mode === "signup") {
    nameField.style.display = "flex";
    fullNameInput.required = true;
    formTitle.textContent = "Create your account";
    formSubtitle.textContent = "Set up a login for your sprint board.";
    submitBtn.textContent = "Sign up";
    switchPrompt.textContent = "Already have an account?";
    switchLink.textContent = "Log in";
  } else {
    nameField.style.display = "none";
    fullNameInput.required = false;
    formTitle.textContent = "Welcome back";
    formSubtitle.textContent = "Log in to collaborate on your sprint backlog.";
    submitBtn.textContent = "Log in";
    switchPrompt.textContent = "New here?";
    switchLink.textContent = "Create an account";
  }
}

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  errorBox.style.display = "none";

  const email = document.getElementById("email").value.trim();
  const password = document.getElementById("password").value;
  const originalLabel = submitBtn.textContent;
  submitBtn.disabled = true;
  submitBtn.textContent = mode === "signup" ? "Creating account…" : "Logging in…";

  try {
    if (mode === "signup") {
      const fullName = fullNameInput.value.trim();
      await api("/auth/signup", { method: "POST", body: { email, password, full_name: fullName } });
      mode = "login";
      updateFormMode();
      errorBox.textContent = "Account created. You can log in now.";
      errorBox.style.color = "#059669";
      errorBox.style.background = "#DCFCE7";
      errorBox.style.display = "block";
    } else {
      const data = await api("/auth/login", { method: "POST", body: { email, password } });
      setSession(data.access_token, data.user);

      const projects = await api("/projects");
      if (projects.length === 0) {
        const newProject = await api("/projects", {
          method: "POST",
          body: { name: "Sprint 1 Workspace" }
        });
        
        const columns = await api(`/projects/${newProject.id}/columns`);
        const toDoColumn = columns.find(c => c.name === "To Do") || columns[0];

        if (toDoColumn) {
          await api(`/projects/${newProject.id}/tasks`, {
            method: "POST",
            body: {
              column_id: toDoColumn.id,
              name: "Welcome to Scrumptious",
              description: "[tags:Frontend,Feature] Manage sprints, organize tickets, and collaborate in real-time.",
              priority: "medium",
              story_points: 3
            }
          });
        }
      }

      window.location.href = "board.html";
    }
  } catch (err) {
    errorBox.textContent = err.message;
    errorBox.style.color = "#991B1B";
    errorBox.style.background = "#FEE2E2";
    errorBox.style.display = "block";
  } finally {
    submitBtn.disabled = false;
    submitBtn.textContent = originalLabel;
  }
});