
"use strict";

const googleLogin = document.getElementById("googleLogin");
const loginForm = document.getElementById("loginForm");
const signupLink = document.getElementById("signupLink");

let signupMode = false;

// Google Login
if (googleLogin) {
  googleLogin.addEventListener("click", () => {
    window.location.href = "/auth/google";
  });
}

// Show error message
function showAuthMessage(message, success = false) {
  let messageBox = document.getElementById("authMessage");

  if (!messageBox) {
    messageBox = document.createElement("p");
    messageBox.id = "authMessage";
    messageBox.setAttribute("role", "status");

    if (loginForm) {
      loginForm.insertAdjacentElement("beforebegin", messageBox);
    }
  }

  messageBox.textContent = message;
  messageBox.style.color = success ? "green" : "red";
  messageBox.style.margin = "10px 0";
  messageBox.style.fontSize = "14px";
}

// Add name field for signup
function updateFormMode() {
  if (!loginForm) return;

  const emailInput = loginForm.querySelector('input[type="email"]');
  const passwordInput = loginForm.querySelector('input[type="password"]');
  const submitButton = loginForm.querySelector('button[type="submit"]');

  let nameInput = document.getElementById("signupName");

  if (signupMode) {
    if (!nameInput) {
      nameInput = document.createElement("input");
      nameInput.type = "text";
      nameInput.id = "signupName";
      nameInput.name = "name";
      nameInput.placeholder = "Your name";
      nameInput.autocomplete = "name";
      nameInput.required = true;

      loginForm.insertBefore(nameInput, emailInput);
    }

    submitButton.textContent = "Create account";
    signupLink.textContent = "Already have an account? Login";
  } else {
    if (nameInput) {
      nameInput.remove();
    }

    submitButton.textContent = "Login";
    signupLink.textContent = "New here? Create account";
  }

  passwordInput.autocomplete = signupMode
    ? "new-password"
    : "current-password";

  showAuthMessage("");
}

// Toggle Login / Signup
if (signupLink) {
  signupLink.addEventListener("click", (event) => {
    event.preventDefault();

    signupMode = !signupMode;
    updateFormMode();
  });
}

// Email Login / Signup
if (loginForm) {
  loginForm.addEventListener("submit", async (event) => {
    event.preventDefault();

    const emailInput = loginForm.querySelector('input[type="email"]');
    const passwordInput = loginForm.querySelector('input[type="password"]');
    const nameInput = document.getElementById("signupName");
    const submitButton = loginForm.querySelector('button[type="submit"]');

    const email = emailInput.value.trim();
    const password = passwordInput.value;
    const name = nameInput ? nameInput.value.trim() : "";

    const endpoint = signupMode
      ? "/api/auth/signup"
      : "/api/auth/login";

    const payload = signupMode
      ? { name, email, password }
      : { email, password };

    submitButton.disabled = true;
    showAuthMessage(signupMode ? "Creating account..." : "Logging in...");

    try {
      const response = await fetch(endpoint, {
        method: "POST",
        credentials: "same-origin",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify(payload)
      });

      const result = await response.json().catch(() => ({}));

      if (!response.ok) {
        throw new Error(
          result.detail || "Something went wrong. Please try again."
        );
      }

      showAuthMessage(
        signupMode ? "Account created successfully!" : "Login successful!",
        true
      );

      window.location.href = "/";
    } catch (error) {
      showAuthMessage(error.message || "Network error. Please try again.");
    } finally {
      submitButton.disabled = false;
    }
  });
}

// Initialize
updateFormMode();
