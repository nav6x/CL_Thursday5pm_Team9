let mode = "login"; // or "signup"

const form = document.getElementById("authForm");
const nameField = document.getElementById("nameField");
const fullNameInput = document.getElementById("fullName");
const formTitle = document.getElementById("formTitle");
const formSubtitle = document.getElementById("formSubtitle");
const submitBtn = document.getElementById("submitBtn");
const switchPrompt = document.getElementById("switchPrompt");
const switchLink = document.getElementById("switchLink");
const errorBox = document.getElementById("formError");

// If already logged in, skip straight to the board.
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
    formSubtitle.textContent = "Set up a login for your project board.";
    submitBtn.textContent = "Sign up";
    switchPrompt.textContent = "Already have an account?";
    switchLink.textContent = "Log in";
  } else {
    nameField.style.display = "none";
    fullNameInput.required = false;
    formTitle.textContent = "Welcome back";
    formSubtitle.textContent = "Log in to see what your team's working on.";
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
      errorBox.textContent = "Account created — you can log in now.";
      errorBox.style.color = "#2F6F6B";
      errorBox.style.background = "#EAF2F1";
      errorBox.style.display = "block";
    } else {
      // 1. Log in
      const data = await api("/auth/login", { method: "POST", body: { email, password } });
      setSession(data.access_token, data.user);

      // 2. Check for existing projects; if none exist, auto-create one
      const projects = await api("/projects");
      if (projects.length === 0) {
        const newProject = await api("/projects", {
          method: "POST",
          body: { name: "My First Project" }
        });
        
        // Fetch default columns created by backend (To Do, In Progress, Done)
        const columns = await api(`/projects/${newProject.id}/columns`);
        const toDoColumn = columns.find(c => c.name === "To Do") || columns[0];

        // 3. Create initial sample tasks in the new project
        if (toDoColumn) {
          await api(`/projects/${newProject.id}/tasks`, {
            method: "POST",
            body: {
              column_id: toDoColumn.id,
              name: "Welcome to Corkboard!",
              description: "This is your first task. Drag it across columns or create new ones.",
              priority: "medium",
              story_points: 1
            }
          });
        }
      }

      // 4. Redirect to board page
      window.location.href = "board.html";
    }
  } catch (err) {
    errorBox.textContent = err.message;
    errorBox.style.color = "#A8402F";
    errorBox.style.background = "#FBEAE7";
    errorBox.style.display = "block";
  } finally {
    submitBtn.disabled = false;
    submitBtn.textContent = originalLabel;
  }
});