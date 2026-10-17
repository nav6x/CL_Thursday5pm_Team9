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

// Check if redirected from Supabase email verification link
(function checkEmailVerification() {
  const hashParams = new URLSearchParams(window.location.hash.substring(1));
  const searchParams = new URLSearchParams(window.location.search);
  const authType = hashParams.get("type") || searchParams.get("type");
  const errorDesc = hashParams.get("error_description") || searchParams.get("error_description");

  if (errorDesc) {
    errorBox.textContent = decodeURIComponent(errorDesc.replace(/\+/g, " "));
    errorBox.style.color = "#991B1B";
    errorBox.style.background = "#FEE2E2";
    errorBox.style.display = "block";
    history.replaceState(null, "", window.location.pathname);
  } else if (authType === "signup" || authType === "email_confirmation") {
    errorBox.textContent = "Email verified successfully! You can now log in.";
    errorBox.style.color = "#059669";
    errorBox.style.background = "#DCFCE7";
    errorBox.style.display = "block";
    history.replaceState(null, "", window.location.pathname);
  }
})();

const emailInput = document.getElementById("email");
const passwordInput = document.getElementById("password");

switchLink.addEventListener("click", (e) => {
  e.preventDefault();
  mode = mode === "login" ? "signup" : "login";
  passwordInput.value = "";
  updateFormMode();
});

function updateFormMode() {
  errorBox.style.display = "none";
  if (mode === "signup") {
    nameField.style.display = "flex";
    fullNameInput.required = true;
    passwordInput.setAttribute("autocomplete", "new-password");
    formTitle.textContent = "Create your account";
    formSubtitle.textContent = "Set up a login for your sprint board.";
    submitBtn.textContent = "Sign up";
    switchPrompt.textContent = "Already have an account?";
    switchLink.textContent = "Log in";
  } else {
    nameField.style.display = "none";
    fullNameInput.required = false;
    fullNameInput.value = "";
    passwordInput.setAttribute("autocomplete", "current-password");
    formTitle.textContent = "Welcome back";
    formSubtitle.textContent = "Log in to collaborate on your sprint backlog.";
    submitBtn.textContent = "Log in";
    switchPrompt.textContent = "New here?";
    switchLink.textContent = "Create an account";
  }
}

const mfaForm = document.getElementById("mfaForm");
const mfaCodeInput = document.getElementById("mfaCode");
const mfaSubmitBtn = document.getElementById("mfaSubmitBtn");
const mfaBackBtn = document.getElementById("mfaBackBtn");
const authSwitch = document.querySelector(".auth-switch");

let currentMfa = null;

function showMfaChallenge() {
  form.style.display = "none";
  if (authSwitch) authSwitch.style.display = "none";
  mfaForm.style.display = "block";
  mfaCodeInput.value = "";
  formTitle.textContent = "Two-Factor Verification";
  formSubtitle.textContent = "Enter the 6-digit code from your authenticator app.";
  errorBox.style.display = "none";
  mfaCodeInput.focus();
}

function hideMfaChallenge() {
  currentMfa = null;
  mfaForm.style.display = "none";
  form.style.display = "block";
  if (authSwitch) authSwitch.style.display = "block";
  updateFormMode();
}

if (mfaBackBtn) {
  mfaBackBtn.addEventListener("click", () => {
    hideMfaChallenge();
  });
}

async function initWorkspaceAndRedirect() {
  const projects = await api("/projects");
  if (projects.length === 0) {
    const newProject = await api("/projects", {
      method: "POST",
      body: { name: "Sprint 1 Workspace" },
    });

    const columns = await api(`/projects/${newProject.id}/columns`);
    const toDoColumn = columns.find((c) => c.name === "To Do") || columns[0];

    if (toDoColumn) {
      await api(`/projects/${newProject.id}/tasks`, {
        method: "POST",
        body: {
          column_id: toDoColumn.id,
          name: "Welcome to Scrumptious",
          description: "[tags:Frontend,Feature] Manage sprints, organize tickets, and collaborate in real-time.",
          priority: "medium",
          story_points: 3,
        },
      });
    }
  }

  window.location.href = "board.html";
}

if (mfaForm) {
  mfaForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    errorBox.style.display = "none";
    const code = mfaCodeInput.value.trim();
    if (!code || code.length !== 6) {
      errorBox.textContent = "Please enter a valid 6-digit code.";
      errorBox.style.color = "#991B1B";
      errorBox.style.background = "#FEE2E2";
      errorBox.style.display = "block";
      return;
    }

    const origLabel = mfaSubmitBtn.textContent;
    mfaSubmitBtn.disabled = true;
    mfaSubmitBtn.textContent = "Verifying…";

    try {
      const data = await api("/auth/mfa/verify-login", {
        method: "POST",
        body: {
          temp_token: currentMfa.temp_token,
          factor_id: currentMfa.factor_id,
          code: code,
        },
      });

      setSession(data.access_token, data.user || currentMfa.user);
      await initWorkspaceAndRedirect();
    } catch (err) {
      errorBox.textContent = err.message || "Invalid verification code. Please try again.";
      errorBox.style.color = "#991B1B";
      errorBox.style.background = "#FEE2E2";
      errorBox.style.display = "block";
    } finally {
      mfaSubmitBtn.disabled = false;
      mfaSubmitBtn.textContent = origLabel;
    }
  });
}

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  errorBox.style.display = "none";

  const email = emailInput.value.trim();
  const password = passwordInput.value;
  const originalLabel = submitBtn.textContent;
  submitBtn.disabled = true;
  submitBtn.textContent = mode === "signup" ? "Creating account…" : "Logging in…";

  try {
    if (mode === "signup") {
      const fullName = fullNameInput.value.trim();
      const res = await api("/auth/signup", { method: "POST", body: { email, password, full_name: fullName } });

      // Cleanly reset password and name, switch to login view
      passwordInput.value = "";
      fullNameInput.value = "";
      mode = "login";
      updateFormMode();

      errorBox.textContent = res.message || "Account created! A confirmation email has been sent. Please verify your email before logging in.";
      errorBox.style.color = "#059669";
      errorBox.style.background = "#DCFCE7";
      errorBox.style.display = "block";
    } else {
      const data = await api("/auth/login", { method: "POST", body: { email, password } });

      if (data.mfa_required) {
        currentMfa = {
          factor_id: data.factor_id,
          temp_token: data.temp_token,
          user: data.user,
        };
        showMfaChallenge();
        return;
      }

      setSession(data.access_token, data.user);
      await initWorkspaceAndRedirect();
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