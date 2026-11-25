
const googleLogin = document.getElementById("googleLogin");
const loginForm = document.getElementById("loginForm");
const signupLink = document.getElementById("signupLink");

googleLogin.addEventListener("click", () => {
  alert("Google Login will be connected after OAuth setup.");
});

loginForm.addEventListener("submit", (event) => {
  event.preventDefault();
  alert("Email Login will be activated after backend authentication setup.");
});

signupLink.addEventListener("click", (event) => {
  event.preventDefault();
  alert("Account registration will be activated soon.");
});
