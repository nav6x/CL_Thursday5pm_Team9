// Talks to the Flask API. Adjust API_BASE if your backend runs
// somewhere other than localhost:5000 (e.g. once you deploy it).
const API_BASE = "http://localhost:5000/api";

// ---- Token / user storage ----
// Login happens on index.html but the board lives on board.html, so
// the session has to survive a full page navigation — a JS variable
// wouldn't make it across that reload, localStorage does.

function getToken() {
  return localStorage.getItem("token");
}

function getUser() {
  const raw = localStorage.getItem("user");
  return raw ? JSON.parse(raw) : null;
}

function setSession(token, user) {
  localStorage.setItem("token", token);
  localStorage.setItem("user", JSON.stringify(user));
}

function clearSession() {
  localStorage.removeItem("token");
  localStorage.removeItem("user");
}

// ---- Fetch wrapper ----
// Every call site does `await api(path, {...})` and expects back the
// parsed JSON on success, or a thrown Error whose .message is
// human-readable (that message is what ends up in errorBox.textContent
// on the login page, and in showToast(...) on the board).
async function api(path, { method = "GET", body } = {}) {
  const headers = { "Content-Type": "application/json" };

  const token = getToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const response = await fetch(`${API_BASE}${path}`, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });

  let data = null;
  try {
    data = await response.json();
  } catch {
    // some error responses may not have a JSON body — that's fine,
    // we just fall through with data = null below
  }

  if (!response.ok) {
    throw new Error((data && data.error) || `Request failed (${response.status})`);
  }

  return data;
}