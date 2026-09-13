function updateClock() {
  const now = new Date();
  document.getElementById("clock").textContent =
    "Page loaded — current time: " + now.toLocaleTimeString();
}

updateClock();
setInterval(updateClock, 1000);

document.getElementById("testBtn").addEventListener("click", () => {
  document.getElementById("clickResult").textContent =
    "JavaScript is working! Button clicked at " + new Date().toLocaleTimeString();
});