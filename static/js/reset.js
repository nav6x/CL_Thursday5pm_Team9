/* reset.js: logic for reset-password.html
 *
 * Two states on one page:
 *  1. No token in the URL -> ask for an email and request a reset link.
 *  2. ?token_hash=...     -> (opened from the emailed link) choose a new password.
 *
 * Needs the Supabase "Reset Password" email template to link to:
 *   {{ .RedirectTo }}?token_hash={{ .TokenHash }}&type=recovery
 */

const MIN_PASSWORD_LENGTH = 8;

const errorBox = document.getElementById("formError");
const formTitle = document.getElementById("formTitle");
const formSubtitle = document.getElementById("formSubtitle");
const requestForm = document.getElementById("requestForm");
const requestBtn = document.getElementById("requestBtn");
const emailInput = document.getElementById("email");
const resetForm = document.getElementById("resetForm");
const resetBtn = document.getElementById("resetBtn");
const newPasswordInput = document.getElementById("newPassword");
const confirmPasswordInput = document.getElementById("confirmPassword");

let tokenHash = null;

/* ---------- messages (same look as the login page) ---------- */

function showMessage(text, kind) {
  errorBox.textContent = text;
  errorBox.style.color = kind === "success" ? "#059669" : "#991B1B";
  errorBox.style.background = kind === "success" ? "#DCFCE7" : "#FEE2E2";
  errorBox.style.display = "block";
}

function hideMessage() {
  errorBox.style.display = "none";
}

/* ---------- read the token from the emailed link ---------- */

(function init() {
  const query = new URLSearchParams(window.location.search);
  const hash = new URLSearchParams(window.location.hash.substring(1));

  const linkError = hash.get("error_description") || query.get("error_description");
  const token = query.get("token_hash");
  const type = query.get("type");

  if (linkError) {
    showMessage("This reset link is invalid or has expired. Request a new one below.", "error");
  } else if (query.get("code") && !token) {
    console.warn("Reset link uses ?code= (PKCE). Update the Supabase Reset Password email template to use token_hash.");
    showMessage("This reset link isn't valid. Request a new one below.", "error");
  } else if (token && (!type || type === "recovery")) {
    tokenHash = token;
    showResetStep();
  }

  // Keep the token out of the address bar and browser history.
  if (token || linkError || query.get("code")) {
    history.replaceState(null, "", window.location.pathname);
  }
})();

function showResetStep() {
  formTitle.textContent = "Choose a new password";
  formSubtitle.textContent = "Pick a password you haven't used before.";
  requestForm.style.display = "none";
  resetForm.style.display = "block";
  newPasswordInput.focus();
}

/* ---------- password rules ---------- */

function validateNewPassword(pw, confirm) {
  if (pw.length < MIN_PASSWORD_LENGTH) return `Password must be at least ${MIN_PASSWORD_LENGTH} characters.`;
  if (!/[A-Za-z]/.test(pw) || !/\d/.test(pw)) return "Password must include at least one letter and one number.";
  if (pw !== confirm) return "Passwords don't match.";
  return null;
}

/* ---------- submit handlers ---------- */

requestForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  hideMessage();

  const email = emailInput.value.trim();
  const originalLabel = requestBtn.textContent;
  requestBtn.disabled = true;
  requestBtn.textContent = "Sending…";

  try {
    await api("/auth/forgot-password", { method: "POST", body: { email } });
    // Same message whether or not the account exists, so emails can't be probed.
    showMessage("If an account exists for that email, a reset link is on its way. Check your inbox and spam folder.", "success");
    requestForm.reset();
  } catch (err) {
    showMessage(err.message, "error");
  } finally {
    requestBtn.disabled = false;
    requestBtn.textContent = originalLabel;
  }
});

resetForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  hideMessage();

  const problem = validateNewPassword(newPasswordInput.value, confirmPasswordInput.value);
  if (problem) {
    showMessage(problem, "error");
    return;
  }

  const originalLabel = resetBtn.textContent;
  resetBtn.disabled = true;
  resetBtn.textContent = "Saving…";

  try {
    await api("/auth/reset-password", {
      method: "POST",
      body: { token_hash: tokenHash, password: newPasswordInput.value },
    });
    showToast("Password updated. Log in with your new password.", "success");
    resetForm.style.display = "none";
    showMessage("Password updated. Taking you to log in…", "success");
    setTimeout(() => { window.location.href = "index.html"; }, 1800);
  } catch (err) {
    showMessage(err.message, "error");
    resetBtn.disabled = false;
    resetBtn.textContent = originalLabel;
  }
});
