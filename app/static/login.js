document.getElementById("login").addEventListener("submit", async (e) => {
  e.preventDefault();
  const form = e.target;
  const err = document.getElementById("err");
  const btn = form.querySelector("button");
  err.textContent = "";
  btn.disabled = true;
  try {
    const res = await fetch("/api/login", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Requested-With": "vpnhost" },
      body: JSON.stringify({ username: form.username.value, password: form.password.value }),
    });
    if (res.ok) {
      location.href = "/";
      return;
    }
    const data = await res.json().catch(() => ({}));
    err.textContent = data.detail || "Nie udało się zalogować";
  } catch (ex) {
    err.textContent = "Brak połączenia z panelem";
  } finally {
    btn.disabled = false;
  }
});
