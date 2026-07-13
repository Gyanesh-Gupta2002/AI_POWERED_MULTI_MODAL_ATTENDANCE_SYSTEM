document.addEventListener("DOMContentLoaded", () => {

  // ---------------- Auto-dismiss flash messages ----------------
  const flashes = document.querySelectorAll(".flash");
  flashes.forEach((el) => {
    setTimeout(() => {
      el.style.transition = "opacity 0.4s ease";
      el.style.opacity = "0";
      setTimeout(() => el.remove(), 400);
    }, 5000);
  });

  // ---------------- Confirm before triggering webcam-based actions ----------------
  const camForms = document.querySelectorAll("[data-confirm-camera]");
  camForms.forEach((form) => {
    form.addEventListener("submit", (e) => {
      const ok = confirm(
        "This will open the server's webcam window. Focus that window, " +
        "follow the on-screen instructions, and press Q when done. Continue?"
      );
      if (!ok) e.preventDefault();
    });
  });

  // ---------------- Confirm before triggering microphone-based actions ----------------
const voiceForms = document.querySelectorAll("[data-confirm-voice]");
voiceForms.forEach((form) => {
  form.addEventListener("submit", (e) => {
    const ok = confirm(
      "This will use your microphone to record 3 short voice samples. " +
      "Speak clearly when prompted. Continue?"
    );
    if (!ok) e.preventDefault();
  });
});

  // ---------------- Theme toggle ----------------
  const toggleBtn = document.getElementById("themeToggle");
  if (toggleBtn) {
    const root = document.documentElement;

    function updateButtonLabel() {
      const isLight = root.getAttribute("data-theme") === "light";
      toggleBtn.textContent = isLight ? "🌙 Dark" : "☀️ Light";
    }

    updateButtonLabel();

    toggleBtn.addEventListener("click", () => {
      const isLight = root.getAttribute("data-theme") === "light";
      if (isLight) {
        root.removeAttribute("data-theme");
        localStorage.setItem("theme", "dark");
      } else {
        root.setAttribute("data-theme", "light");
        localStorage.setItem("theme", "light");
      }
      updateButtonLabel();
    });
  }


// ---------------- RFID auto-submit ----------------
  const rfidForm = document.getElementById("rfidForm");
  const rfidInput = document.getElementById("rfid_input");
  const waitingIndicator = document.getElementById("waitingIndicator");
  const rfidStatusText = document.getElementById("rfidStatusText");

  if (rfidForm && rfidInput) {
    rfidInput.focus();

    rfidInput.addEventListener("input", () => {
      if (rfidInput.value.length > 0) {
        waitingIndicator.classList.add("detected");
        rfidStatusText.textContent = "Card detected!";
      } else {
        waitingIndicator.classList.remove("detected");
        rfidStatusText.textContent = "Waiting for card...";
      }
    });

    rfidInput.addEventListener("keypress", (e) => {
      if (e.key === "Enter") {
        rfidForm.submit();
      }
    });
  }
});