const API_BASE = window.location.port === "3000" ? "http://localhost:5000/api" : "/api";

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
  }

  if (!response.ok) {
    throw new Error((data && data.error) || `Request failed (${response.status})`);
  }

  return data;
}