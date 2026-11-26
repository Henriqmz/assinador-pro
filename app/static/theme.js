(function () {
  const root = document.documentElement;
  function applyTheme(t) {
    root.setAttribute("data-theme", t);
    localStorage.setItem("ap-theme", t);
    const ic = document.getElementById("themeIcon");
    const lb = document.getElementById("themeLabel");
    if (ic) ic.textContent = t === "light" ? "☾" : "☀";
    if (lb) lb.textContent = t === "light" ? "Modo Escuro" : "Modo Claro";
  }
  applyTheme(localStorage.getItem("ap-theme") || "dark");
  window.addEventListener("DOMContentLoaded", () => {
    applyTheme(localStorage.getItem("ap-theme") || "dark");
    const btn = document.getElementById("themeToggle");
    if (btn) {
      btn.addEventListener("click", () => {
        applyTheme(root.getAttribute("data-theme") === "dark" ? "light" : "dark");
      });
    }
  });
  window.apToast = function (msg) {
    let el = document.getElementById("apToast");
    if (!el) {
      el = document.createElement("div");
      el.id = "apToast";
      el.className = "toast";
      document.body.appendChild(el);
    }
    el.textContent = msg;
    el.classList.add("show");
    setTimeout(() => el.classList.remove("show"), 2200);
  };
})();
