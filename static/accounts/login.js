const container = document.getElementById("container");
const registerBtn = document.getElementById("register");
const loginBtn = document.getElementById("login");

registerBtn.addEventListener("click", () => {
  container.classList.add("active");
});

loginBtn.addEventListener("click", () => {
  container.classList.remove("active");
});

setTimeout(() => {
    const errBox = document.getElementById('error-message');
    if (errBox) {
      errBox.style.display = 'none';
    }
  }, 5000);

  // Automatically switch to register form if is_register is true
  document.addEventListener("DOMContentLoaded", function () {
    if (typeof is_register !== "undefined" && is_register) {
      container?.classList.add("active");
    }
  });