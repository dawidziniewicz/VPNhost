"use strict";

/* ================================================================ narzędzia */
const $ = (sel, el = document) => el.querySelector(sel);
const $$ = (sel, el = document) => [...el.querySelectorAll(sel)];
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const el = (html) => { const t = document.createElement("template"); t.innerHTML = html.trim(); return t.content.firstElementChild; };
const now = () => Date.now() / 1000;

const ICONS = {
  plus: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 5v14M5 12h14"/></svg>',
  qr: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><path d="M14 14h3v3h-3zM20 14v.01M14 20h.01M17 20h4v-3"/></svg>',
  edit: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M4 20h4L19 9l-4-4L4 16z"/><path d="m13.5 6.5 4 4"/></svg>',
  trash: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3"/></svg>',
  power: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M12 3v9"/><path d="M6.3 7.5a8 8 0 1 0 11.4 0"/></svg>',
  key: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="8" cy="15" r="4"/><path d="m11 12 9-9M17 6l3 3M15 8l2 2"/></svg>',
  download: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M12 4v11M7 10l5 5 5-5M4 20h16"/></svg>',
  copy: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V5a1 1 0 0 0-1-1H5a1 1 0 0 0-1 1v10a1 1 0 0 0 1 1h3"/></svg>',
  close: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M6 6l12 12M18 6 6 18"/></svg>',
  search: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg>',
  plug: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M5 12h4l2-5 3 10 2-5h3"/></svg>',
  unplug: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M5 12h14"/></svg>',
  user: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="8" r="4"/><path d="M4 21c1-4 4-6 8-6s7 2 8 6"/></svg>',
  lock: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/></svg>',
  gear: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9 7 7M17 17l2.1 2.1M4.9 19.1 7 17M17 7l2.1-2.1"/></svg>',
  route: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="6" cy="18" r="2.5"/><circle cx="18" cy="6" r="2.5"/><path d="M8.5 18H15a3 3 0 0 0 0-6H9a3 3 0 0 1 0-6h6.5"/></svg>',
};

function fmtBytes(n) {
  n = Number(n) || 0;
  const u = ["B", "kB", "MB", "GB", "TB"];
  let i = 0;
  while (n >= 1000 && i < u.length - 1) { n /= 1000; i++; }
  return `${n >= 100 || i === 0 ? n.toFixed(0) : n.toFixed(1)} ${u[i]}`.replace(".", ",");
}
function fmtRate(bps) {
  let b = (Number(bps) || 0) * 8;
  const u = ["b/s", "kb/s", "Mb/s", "Gb/s"];
  let i = 0;
  while (b >= 1000 && i < u.length - 1) { b /= 1000; i++; }
  return `${b >= 100 || i === 0 ? b.toFixed(0) : b.toFixed(1)} ${u[i]}`.replace(".", ",");
}
function fmtDur(sec) {
  sec = Math.max(0, Math.floor(sec || 0));
  const d = Math.floor(sec / 86400), h = Math.floor((sec % 86400) / 3600), m = Math.floor((sec % 3600) / 60);
  if (d) return `${d} d ${h} godz.`;
  if (h) return `${h} godz. ${m} min`;
  if (m) return `${m} min`;
  return `${sec} s`;
}
function ago(ts) {
  if (!ts) return "nigdy";
  const s = Math.max(0, Math.floor(now() - ts));
  if (s < 10) return "przed chwilą";
  if (s < 60) return `${s} s temu`;
  if (s < 3600) return `${Math.floor(s / 60)} min temu`;
  if (s < 86400) return `${Math.floor(s / 3600)} godz. temu`;
  const d = Math.floor(s / 86400);
  return d === 1 ? "wczoraj" : `${d} dni temu`;
}
const pad = (n) => String(n).padStart(2, "0");
function fmtTime(ts, withSec) {
  const d = new Date(ts * 1000);
  return `${pad(d.getHours())}:${pad(d.getMinutes())}${withSec ? ":" + pad(d.getSeconds()) : ""}`;
}
function fmtDate(ts) { const d = new Date(ts * 1000); return `${pad(d.getDate())}.${pad(d.getMonth() + 1)}`; }
function fmtDateTime(ts) {
  if (!ts) return "—";
  const d = new Date(ts * 1000);
  return `${pad(d.getDate())}.${pad(d.getMonth() + 1)}.${d.getFullYear()} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}
const hostOf = (ep) => !ep ? "" : ep.startsWith("[") ? ep.slice(1, ep.indexOf("]")) : ep.replace(/:\d+$/, "");
const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();

/* ================================================================ API */
async function api(path, opts = {}) {
  const init = { method: opts.method || "GET", headers: { "X-Requested-With": "vpnhost" } };
  if (opts.body !== undefined) {
    init.headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(opts.body);
  }
  const res = await fetch(path, init);
  if (res.status === 401) { location.href = "/login"; throw new Error("Zaloguj się ponownie"); }
  const type = res.headers.get("content-type") || "";
  const data = type.includes("json") ? await res.json() : await res.text();
  if (!res.ok) throw new Error((data && data.detail) || `Błąd ${res.status}`);
  return data;
}

function toast(msg, bad) {
  const t = el(`<div class="toast ${bad ? "bad" : ""}">${esc(msg)}</div>`);
  $("#toasts").append(t);
  setTimeout(() => t.remove(), bad ? 6000 : 3500);
}

/* ================================================================ okna */
function modal({ title, body, footer, wide, onClose }) {
  const bg = el(`<div class="modal-bg"><div class="modal ${wide ? "wide" : ""}" role="dialog" aria-modal="true">
    <div class="modal-h"><h3>${esc(title)}</h3><div class="spacer"></div><button class="btn icon ghost" data-close aria-label="Zamknij">${ICONS.close}</button></div>
    <div class="modal-b"></div></div></div>`);
  const box = $(".modal", bg);
  const b = $(".modal-b", bg);
  if (typeof body === "string") b.innerHTML = body; else if (body) b.append(body);
  let f = null;
  if (footer) { f = el('<div class="modal-f"></div>'); footer.forEach((x) => f.append(x)); box.append(f); }
  const close = () => { bg.remove(); document.removeEventListener("keydown", onKey); onClose && onClose(); };
  const onKey = (e) => {
    if (e.key === "Escape") close();
    if (e.key === "Enter" && e.target.matches && e.target.matches("input:not([type=radio]):not([type=checkbox])") && box.contains(e.target)) {
      const primary = f && $$(".btn.primary", f).pop();
      if (primary && primary.tagName === "BUTTON") { e.preventDefault(); primary.click(); }
    }
  };
  bg.addEventListener("mousedown", (e) => { if (e.target === bg) close(); });
  $("[data-close]", bg).addEventListener("click", close);
  document.addEventListener("keydown", onKey);
  document.body.append(bg);
  const first = $("input, select, textarea", b);
  if (first) setTimeout(() => first.focus(), 30);
  return { close, el: box, body: b };
}
function button(label, cls, onClick) {
  const b = el(`<button class="btn ${cls || ""}" type="button">${label}</button>`);
  if (onClick) b.addEventListener("click", onClick);
  return b;
}
function confirmBox(title, text, okLabel, danger) {
  return new Promise((resolve) => {
    let done = false;
    const m = modal({
      title, body: `<p style="margin:0">${text}</p>`,
      footer: [
        button("Anuluj", "", () => m.close()),
        button(esc(okLabel), danger ? "danger solid" : "primary", () => { done = true; m.close(); }),
      ],
      onClose: () => resolve(done),
    });
  });
}
async function withBusy(btn, fn) {
  btn.disabled = true;
  try { return await fn(); } catch (e) { toast(e.message, true); } finally { btn.disabled = false; }
}

/* ================================================================ wykresy */
function niceMax(v) {
  if (v <= 0) return 125;
  const bits = v * 8;
  const p = Math.pow(10, Math.floor(Math.log10(bits)));
  const steps = [1, 1.2, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10];
  const n = bits / p;
  const s = steps.find((x) => x >= n * 1.08) || 10;
  return (s * p) / 8;
}

class LineChart {
  constructor(host, opts = {}) {
    this.host = host;
    this.opts = opts;
    host.classList.add("chart");
    if (opts.small) host.classList.add("sm");
    this.canvas = document.createElement("canvas");
    this.tip = el('<div class="tip hidden"></div>');
    host.append(this.canvas, this.tip);
    this.points = [];
    this.hoverX = null;
    this.ro = new ResizeObserver(() => this.draw());
    this.ro.observe(host);
    this.canvas.addEventListener("mousemove", (e) => { this.hoverX = e.offsetX; this.draw(); });
    this.canvas.addEventListener("mouseleave", () => { this.hoverX = null; this.tip.classList.add("hidden"); this.draw(); });
  }
  set(points, step) { this.points = points || []; this.step = step || 2; this.draw(); }
  draw() {
    const w = this.host.clientWidth, h = this.host.clientHeight;
    if (!w || !h) return;
    const dpr = window.devicePixelRatio || 1;
    this.canvas.width = w * dpr; this.canvas.height = h * dpr;
    const c = this.canvas.getContext("2d");
    c.setTransform(dpr, 0, 0, dpr, 0, 0);
    c.clearRect(0, 0, w, h);
    const L = 62, R = 10, T = 10, B = 22;
    const pw = w - L - R, ph = h - T - B;
    const pts = this.points;
    const lineCol = css("--line"), faint = css("--faint"), down = css("--down"), up = css("--up");
    c.font = "11px ui-sans-serif, system-ui, sans-serif";
    let max = 0;
    pts.forEach((p) => { max = Math.max(max, p[1], p[2]); });
    max = niceMax(max);
    // siatka
    c.strokeStyle = lineCol; c.fillStyle = faint; c.lineWidth = 1;
    c.textAlign = "right"; c.textBaseline = "middle";
    for (let i = 0; i <= 4; i++) {
      const y = T + ph - (ph * i) / 4;
      c.beginPath(); c.moveTo(L, Math.round(y) + 0.5); c.lineTo(L + pw, Math.round(y) + 0.5); c.stroke();
      c.fillText(fmtRate((max * i) / 4), L - 8, y);
    }
    if (pts.length < 2) {
      c.textAlign = "center"; c.fillText("Zbieram dane…", L + pw / 2, T + ph / 2);
      return;
    }
    const t0 = pts[0][0], t1 = pts[pts.length - 1][0];
    const X = (t) => L + ((t - t0) / Math.max(1, t1 - t0)) * pw;
    const Y = (v) => T + ph - (v / max) * ph;
    // oś czasu
    c.textAlign = "center"; c.textBaseline = "top";
    const span = t1 - t0;
    const ticks = Math.max(2, Math.min(7, Math.floor(pw / 90)));
    for (let i = 0; i <= ticks; i++) {
      const t = t0 + (span * i) / ticks;
      const label = span > 2 * 86400 ? fmtDate(t) : fmtTime(t, span < 300);
      c.fillText(label, Math.min(L + pw - 16, Math.max(L + 16, X(t))), T + ph + 6);
    }
    const series = [[2, down, 0.22], [1, up, 0.12]];
    for (const [idx, col, alpha] of series) {
      c.beginPath();
      pts.forEach((p, i) => { const x = X(p[0]), y = Y(p[idx]); i ? c.lineTo(x, y) : c.moveTo(x, y); });
      c.lineWidth = 1.8; c.strokeStyle = col; c.lineJoin = "round"; c.stroke();
      c.lineTo(X(t1), T + ph); c.lineTo(X(t0), T + ph); c.closePath();
      const g = c.createLinearGradient(0, T, 0, T + ph);
      g.addColorStop(0, col + Math.round(alpha * 255).toString(16).padStart(2, "0"));
      g.addColorStop(1, col + "00");
      c.fillStyle = g; c.fill();
    }
    if (this.hoverX !== null && this.hoverX >= L && this.hoverX <= L + pw) {
      const t = t0 + ((this.hoverX - L) / pw) * span;
      let best = pts[0];
      for (const p of pts) if (Math.abs(p[0] - t) < Math.abs(best[0] - t)) best = p;
      const x = X(best[0]);
      c.strokeStyle = faint; c.setLineDash([3, 3]);
      c.beginPath(); c.moveTo(x, T); c.lineTo(x, T + ph); c.stroke(); c.setLineDash([]);
      for (const [idx, col] of series) { c.fillStyle = col; c.beginPath(); c.arc(x, Y(best[idx]), 3.5, 0, 7); c.fill(); }
      const when = span > 2 * 86400 ? `${fmtDate(best[0])} ${fmtTime(best[0])}` : fmtTime(best[0], span < 3600);
      this.tip.innerHTML = `<div class="muted">${when}</div><div class="down">↓ ${fmtRate(best[2])}</div><div class="up">↑ ${fmtRate(best[1])}</div>`;
      this.tip.classList.remove("hidden");
      const tw = this.tip.offsetWidth;
      this.tip.style.left = `${x + 12 + tw > w ? x - tw - 12 : x + 12}px`;
      this.tip.style.top = "8px";
    }
  }
  destroy() { this.ro.disconnect(); }
}

class BarChart {
  constructor(host) {
    this.host = host;
    host.classList.add("chart");
    this.canvas = document.createElement("canvas");
    this.tip = el('<div class="tip hidden"></div>');
    host.append(this.canvas, this.tip);
    this.days = [];
    this.hover = null;
    this.ro = new ResizeObserver(() => this.draw());
    this.ro.observe(host);
    this.canvas.addEventListener("mousemove", (e) => { this.hover = e.offsetX; this.draw(); });
    this.canvas.addEventListener("mouseleave", () => { this.hover = null; this.tip.classList.add("hidden"); this.draw(); });
  }
  set(days) { this.days = days || []; this.draw(); }
  draw() {
    const w = this.host.clientWidth, h = this.host.clientHeight;
    if (!w || !h) return;
    const dpr = window.devicePixelRatio || 1;
    this.canvas.width = w * dpr; this.canvas.height = h * dpr;
    const c = this.canvas.getContext("2d");
    c.setTransform(dpr, 0, 0, dpr, 0, 0);
    c.clearRect(0, 0, w, h);
    const L = 58, R = 8, T = 10, B = 22, pw = w - L - R, ph = h - T - B;
    const days = this.days;
    const faint = css("--faint"), lineCol = css("--line"), down = css("--down"), up = css("--up");
    c.font = "11px ui-sans-serif, system-ui, sans-serif";
    let max = 0;
    days.forEach((d) => { max = Math.max(max, d.rx + d.tx); });
    if (max <= 0) max = 1e6;
    const p = Math.pow(10, Math.floor(Math.log10(max)));
    max = Math.ceil((max / p) * 1.05) * p;
    c.strokeStyle = lineCol; c.fillStyle = faint; c.textAlign = "right"; c.textBaseline = "middle";
    for (let i = 0; i <= 4; i++) {
      const y = T + ph - (ph * i) / 4;
      c.beginPath(); c.moveTo(L, Math.round(y) + 0.5); c.lineTo(L + pw, Math.round(y) + 0.5); c.stroke();
      c.fillText(fmtBytes((max * i) / 4), L - 8, y);
    }
    if (!days.length) return;
    const slot = pw / days.length, bw = Math.max(2, Math.min(28, slot * 0.68));
    let hi = null;
    days.forEach((d, i) => {
      const x = L + slot * i + (slot - bw) / 2;
      const hTx = (d.tx / max) * ph, hRx = (d.rx / max) * ph;
      const isHover = this.hover !== null && this.hover >= L + slot * i && this.hover < L + slot * (i + 1);
      if (isHover) hi = { d, x };
      c.globalAlpha = isHover || this.hover === null ? 1 : 0.6;
      c.fillStyle = down; c.fillRect(x, T + ph - hTx, bw, hTx);
      c.fillStyle = up; c.fillRect(x, T + ph - hTx - hRx, bw, hRx);
      c.globalAlpha = 1;
      const every = Math.ceil(days.length / Math.max(2, Math.floor(pw / 52)));
      if (i % every === 0 || i === days.length - 1) {
        c.fillStyle = faint; c.textAlign = "center"; c.textBaseline = "top";
        const [, mm, dd] = d.day.split("-");
        c.fillText(`${dd}.${mm}`, x + bw / 2, T + ph + 6);
      }
    });
    if (hi) {
      const [yy, mm, dd] = hi.d.day.split("-");
      this.tip.innerHTML = `<div class="muted">${dd}.${mm}.${yy}</div><div class="down">↓ do klientów ${fmtBytes(hi.d.tx)}</div><div class="up">↑ od klientów ${fmtBytes(hi.d.rx)}</div>`;
      this.tip.classList.remove("hidden");
      const tw = this.tip.offsetWidth;
      this.tip.style.left = `${hi.x + 34 + tw > w ? hi.x - tw - 8 : hi.x + 34}px`;
      this.tip.style.top = "8px";
    }
  }
  destroy() { this.ro.disconnect(); }
}

const legend = () => `<div class="legend"><span><i style="background:var(--down)"></i>do klientów (pobieranie)</span><span><i style="background:var(--up)"></i>od klientów (wysyłanie)</span></div>`;
const rangeSeg = (ranges, cur) => `<div class="seg" data-seg>${ranges.map(([k, l]) => `<button type="button" data-k="${k}" class="${k === cur ? "on" : ""}">${l}</button>`).join("")}</div>`;
const RANGES = [["live", "Na żywo"], ["1h", "1 godz."], ["24h", "24 godz."], ["7d", "7 dni"], ["30d", "30 dni"]];
function bindSeg(root, cb) {
  root.addEventListener("click", (e) => {
    const b = e.target.closest("button[data-k]");
    if (!b) return;
    $$("button", root).forEach((x) => x.classList.toggle("on", x === b));
    cb(b.dataset.k);
  });
}

/* ================================================================ stan */
const S = {
  status: null,
  view: null,
  viewObj: null,
  timer: null,
  search: "",
};

function statusBadge(c) {
  if (!c.enabled) return '<span class="badge">wyłączony</span>';
  if (c.online) return '<span class="badge ok"><span class="dot ok"></span>online</span>';
  return '<span class="badge"><span class="dot"></span>offline</span>';
}

/* ================================================================ widok: pulpit */
const Dashboard = {
  title: "Pulpit",
  range: "live",
  render(v) {
    v.innerHTML = `
      <div class="grid kpi">
        <div class="card kpi-card"><div class="label"><span class="dot" id="k-wg-dot"></span>Serwer WireGuard</div><div class="value" id="k-wg">—</div><div class="sub" id="k-wg-sub"></div></div>
        <div class="card kpi-card"><div class="label">Klienci online</div><div class="value" id="k-online">—</div><div class="sub" id="k-online-sub"></div></div>
        <div class="card kpi-card"><div class="label">Prędkość teraz</div><div class="value split-val"><span class="down" id="k-down">—</span></div><div class="sub"><span class="up" id="k-up">—</span> od klientów</div></div>
        <div class="card kpi-card"><div class="label">Aktywne połączenia</div><div class="value" id="k-conns">—</div><div class="sub" id="k-conns-sub">przez tunel VPN</div></div>
      </div>
      <div class="card" style="margin-top:16px">
        <div class="card-h"><h2>Ruch przez VPN</h2>${legend()}<div class="spacer"></div>${rangeSeg(RANGES, this.range)}</div>
        <div class="card-b"><div id="d-chart"></div><div class="muted" id="d-chart-sum" style="font-size:12px;margin-top:6px"></div></div>
      </div>
      <div class="grid two" style="margin-top:16px">
        <div class="card">
          <div class="card-h"><h2>Klienci</h2><div class="spacer"></div><a href="#clients" class="btn sm">Wszyscy</a></div>
          <div class="card-b flush table-wrap"><table><thead><tr><th>Klient</th><th class="hide-sm">Skąd</th><th class="right">↓ / ↑</th><th class="right hide-sm">Ostatnio</th></tr></thead><tbody id="d-clients"></tbody></table></div>
        </div>
        <div class="card">
          <div class="card-h"><h2>Serwer</h2><div class="spacer"></div><span class="muted" id="d-host" style="font-size:12px"></span></div>
          <div class="card-b">
            <div class="meters" id="d-meters"></div>
            <div style="height:14px"></div>
            <div class="iface" id="d-ifaces"></div>
            <div style="height:14px"></div>
            <dl class="facts" id="d-facts"></dl>
          </div>
        </div>
      </div>`;
    this.chart = new LineChart($("#d-chart", v));
    bindSeg($("[data-seg]", v), (k) => { this.range = k; this.lastHist = 0; this.loadHistory(); });
    this.lastHist = 0;
    this.loadHistory();
  },
  async loadHistory() {
    const r = await api(`/api/history?range=${this.range}`).catch(() => null);
    if (!r || !this.chart) return;
    this.lastHist = now();
    this.chart.set(r.points, r.step);
    $("#d-chart-sum").textContent = r.total_rx !== undefined
      ? `W tym okresie: ↓ ${fmtBytes(r.total_tx)} do klientów · ↑ ${fmtBytes(r.total_rx)} od klientów`
      : "Ostatnie 10 minut, odświeżane co 2 s";
  },
  update(st) {
    const wg = st.wg, srv = st.server || {};
    $("#k-wg").innerHTML = wg.up ? "Działa" : '<span style="color:var(--bad)">Nie działa</span>';
    $("#k-wg-dot").className = `dot ${wg.up ? "ok" : "bad"}`;
    $("#k-wg-sub").textContent = wg.up ? `${wg.interface} · port ${wg.listen_port ?? "?"} · ${wg.address || ""}` : (wg.error || "interfejs wyłączony");
    $("#k-online").innerHTML = `${wg.online}<small>/ ${wg.enabled}</small>`;
    $("#k-online-sub").textContent = `${wg.clients} klientów łącznie`;
    $("#k-down").textContent = `↓ ${fmtRate(wg.tx_rate)}`;
    $("#k-up").textContent = `↑ ${fmtRate(wg.rx_rate)}`;
    $("#k-conns").textContent = wg.connections;
    if (this.range === "live" || now() - this.lastHist > 60) this.loadHistory();

    const rows = st.clients.filter((c) => c.enabled).sort((a, b) => (b.online - a.online) || (b.tx_rate + b.rx_rate - a.tx_rate - a.rx_rate));
    $("#d-clients").innerHTML = rows.length ? rows.slice(0, 8).map((c) => `
      <tr class="click" data-id="${c.id}">
        <td><div class="title"><span class="dot ${c.online ? "ok" : ""}"></span>${esc(c.name)}</div><div class="subtitle mono">${esc(c.address)}</div></td>
        <td class="hide-sm mono">${c.online ? esc(hostOf(c.endpoint)) : '<span class="faint">—</span>'}</td>
        <td class="right num nowrap"><div class="down">${fmtRate(c.tx_rate)}</div><div class="up" style="font-size:12px">${fmtRate(c.rx_rate)}</div></td>
        <td class="right hide-sm muted nowrap">${c.online ? "teraz" : ago(c.latest_handshake)}</td>
      </tr>`).join("") : `<tr><td colspan="4"><div class="empty"><b>Brak klientów</b><a href="#clients">Dodaj pierwszego klienta</a></div></td></tr>`;
    $$("#d-clients tr[data-id]").forEach((tr) => tr.addEventListener("click", () => ClientDetail.open(tr.dataset.id)));

    $("#d-host").textContent = srv.hostname || "";
    const meter = (label, pct, text) => {
      const p = Math.max(0, Math.min(100, pct || 0));
      return `<div class="meter"><div class="top"><span>${label}</span><span class="num">${text}</span></div><div class="bar"><i class="${p > 90 ? "bad" : p > 75 ? "warn" : ""}" style="width:${p}%"></i></div></div>`;
    };
    const mem = srv.mem || {}, disk = srv.disk || {};
    $("#d-meters").innerHTML = [
      meter("Procesor", srv.cpu, srv.cpu == null ? "…" : `${String(srv.cpu).replace(".", ",")} %`),
      meter("Pamięć RAM", mem.percent, `${fmtBytes(mem.used)} / ${fmtBytes(mem.total)}`),
      meter("Dysk", disk.percent, `${fmtBytes(disk.used)} / ${fmtBytes(disk.total)}`),
    ].join("");
    $("#d-ifaces").innerHTML = (srv.interfaces || []).map((i) => `
      <span class="n">${esc(i.name)}</span><span class="down num right">↓ ${fmtRate(i.rx_rate)}</span><span class="up num right">↑ ${fmtRate(i.tx_rate)}</span>`).join("");
    $("#d-facts").innerHTML = `
      <dt>Temperatura</dt><dd>${srv.temp != null ? `${String(srv.temp).replace(".", ",")} °C` : "—"}</dd>
      <dt>Obciążenie</dt><dd class="num">${(srv.load || []).map((x) => x.toFixed(2)).join(" · ") || "—"}</dd>
      <dt>Działa od</dt><dd>${srv.uptime ? fmtDur(srv.uptime) : "—"}</dd>
      <dt>Procesor</dt><dd>${esc(srv.cpu_model || "—")} (${srv.cores || "?"} rdz.)</dd>
      <dt>System</dt><dd>${esc(srv.os || "—")}</dd>
      <dt>Adres VPN</dt><dd class="mono">${esc(st.wg.endpoint || "nie ustawiono")}</dd>`;
  },
  destroy() { this.chart && this.chart.destroy(); this.chart = null; },
};

/* ================================================================ widok: klienci */
const Clients = {
  title: "Klienci",
  actions() {
    const wrap = el(`<div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
      <div class="search">${ICONS.search}<input type="text" placeholder="Szukaj klienta…" id="c-search"></div></div>`);
    wrap.append(button(`${ICONS.plus}Dodaj klienta`, "primary", () => addClient()));
    $("input", wrap).value = S.search;
    $("input", wrap).addEventListener("input", (e) => { S.search = e.target.value; S.status && this.update(S.status); });
    return wrap;
  },
  render(v) {
    v.innerHTML = `<div class="card"><div class="card-b flush table-wrap"><table>
      <thead><tr><th>Klient</th><th>Stan</th><th class="hide-sm">Połączony z</th><th class="right">Prędkość ↓ / ↑</th><th class="right hide-sm">Zużycie ↓ / ↑</th><th class="right hide-sm">Ostatnio</th><th></th></tr></thead>
      <tbody id="c-rows"></tbody></table></div></div>
      <p class="muted" style="font-size:12.5px;margin-top:12px">Kliknij klienta, żeby zobaczyć jego ruch, sesje i połączenia. „↓” to dane wysłane do klienta, „↑” to dane od klienta.</p>`;
    $("#c-rows").addEventListener("click", (e) => this.onClick(e));
  },
  update(st) {
    const q = S.search.trim().toLowerCase();
    const list = st.clients.filter((c) => !q || `${c.name} ${c.note} ${c.address} ${hostOf(c.endpoint)}`.toLowerCase().includes(q));
    const tbody = $("#c-rows");
    if (!tbody) return;
    if (!st.clients.length) {
      tbody.innerHTML = `<tr><td colspan="7"><div class="empty"><b>Nie ma jeszcze klientów</b>Dodaj klienta, a dostaniesz kod QR do zeskanowania w aplikacji WireGuard.</div></td></tr>`;
      return;
    }
    tbody.innerHTML = list.map((c) => `
      <tr class="click ${c.enabled ? "" : "off"}" data-id="${c.id}">
        <td><div class="title">${esc(c.name)}${c.imported && !c.has_config ? ' <span class="badge" title="Dodany poza panelem">import</span>' : ""}</div>
            <div class="subtitle"><span class="mono">${esc(c.address)}</span> · ${esc(c.mode_label)}${c.note ? ` · ${esc(c.note)}` : ""}</div></td>
        <td>${statusBadge(c)}</td>
        <td class="hide-sm mono">${c.online ? esc(hostOf(c.endpoint)) : '<span class="faint">—</span>'}</td>
        <td class="right num nowrap"><span class="down">${fmtRate(c.tx_rate)}</span><br><span class="up" style="font-size:12px">${fmtRate(c.rx_rate)}</span></td>
        <td class="right num nowrap hide-sm"><span>${fmtBytes(c.total_tx)}</span><br><span class="muted" style="font-size:12px">${fmtBytes(c.total_rx)}</span></td>
        <td class="right hide-sm muted nowrap">${c.online ? "teraz" : ago(c.latest_handshake)}</td>
        <td><div class="actions">
          <button class="btn icon ghost" data-act="qr" title="Kod QR i konfiguracja">${ICONS.qr}</button>
          <button class="btn icon ghost" data-act="edit" title="Edytuj">${ICONS.edit}</button>
          <button class="btn icon ghost" data-act="toggle" title="${c.enabled ? "Wyłącz" : "Włącz"}">${ICONS.power}</button>
          <button class="btn icon ghost" data-act="delete" title="Usuń">${ICONS.trash}</button>
        </div></td>
      </tr>`).join("") || `<tr><td colspan="7"><div class="empty">Nic nie pasuje do „${esc(S.search)}”</div></td></tr>`;
  },
  onClick(e) {
    const tr = e.target.closest("tr[data-id]");
    if (!tr) return;
    const c = S.status.clients.find((x) => x.id === tr.dataset.id);
    if (!c) return;
    const act = e.target.closest("[data-act]");
    if (!act) return ClientDetail.open(c.id);
    e.stopPropagation();
    ({ qr: showConfig, edit: editClient, toggle: toggleClient, delete: deleteClient })[act.dataset.act](c);
  },
};

async function refresh() {
  try {
    S.status = await api("/api/status");
    applyStatus();
  } catch (e) { /* kolejna próba za chwilę */ }
}

function addClient() {
  const defMode = (S.settings && S.settings.default_mode) || "full";
  const form = el(`<form class="form">
    <label class="field">Nazwa<input type="text" name="name" maxlength="60" placeholder="np. Telefon Dawida" required></label>
    <div class="field" style="display:grid;gap:6px;font-size:12.5px;color:var(--muted);font-weight:500">Co ma iść przez VPN
      <div class="radio-cards">
        <label><input type="radio" name="mode" value="full" ${defMode === "full" ? "checked" : ""}><b>Cały ruch przez dom</b><small>Internet wychodzi z Twojego domowego adresu</small></label>
        <label><input type="radio" name="mode" value="lan" ${defMode === "lan" ? "checked" : ""}><b>Tylko sieć domowa</b><small>Dostęp do urządzeń w domu, reszta bez VPN</small></label>
      </div>
    </div>
    <label class="field">Notatka <span class="hint">opcjonalnie</span><input type="text" name="note" maxlength="300" placeholder="np. iPhone 15"></label>
    <label class="field">Serwery DNS <span class="hint">puste = domyślne z ustawień</span><input type="text" name="dns" placeholder="${esc((S.settings && S.settings.dns) || "1.1.1.1")}"></label>
  </form>`);
  const save = button(`${ICONS.plus}Utwórz`, "primary");
  const m = modal({ title: "Nowy klient", body: form, footer: [button("Anuluj", "", () => m.close()), save] });
  const submit = (e) => {
    e && e.preventDefault();
    withBusy(save, async () => {
      const c = await api("/api/clients", { method: "POST", body: { name: form.name.value, note: form.note.value, mode: form.mode.value, dns: form.dns.value } });
      m.close();
      toast(`Dodano klienta „${c.name}”`);
      await refresh();
      showConfig(c, true);
    });
  };
  form.addEventListener("submit", submit);
  save.addEventListener("click", submit);
}

async function showConfig(c, fresh) {
  if (!c.has_config) {
    const ok = await confirmBox("Brak konfiguracji",
      `Klient „${esc(c.name)}” został dodany poza panelem, więc panel nie zna jego klucza prywatnego.<br><br>Możesz wygenerować nowe klucze. Wtedy stara konfiguracja na urządzeniu przestanie działać i trzeba będzie zeskanować nowy kod QR.`,
      "Wygeneruj nowe klucze");
    if (!ok) return;
    try {
      const nc = await api(`/api/clients/${c.id}/regenerate`, { method: "POST" });
      await refresh();
      return showConfig(nc, true);
    } catch (e) { return toast(e.message, true); }
  }
  let text;
  try { text = await api(`/api/clients/${c.id}/config`); } catch (e) { return toast(e.message, true); }
  const body = el(`<div>
    ${fresh ? '<div class="notice" style="margin-bottom:14px">Klient gotowy. Zeskanuj kod w aplikacji WireGuard na telefonie albo pobierz plik na komputer.</div>' : ""}
    <div class="qr-layout">
      <div class="qr"><img src="/api/clients/${c.id}/qr.svg?t=${Date.now()}" alt="Kod QR konfiguracji"></div>
      <div>
        <ol class="steps">
          <li>Zainstaluj aplikację <b>WireGuard</b> (App Store / Google Play / wireguard.com).</li>
          <li>Wybierz <b>„+” → „Zeskanuj kod QR”</b> albo zaimportuj pobrany plik.</li>
          <li>Włącz tunel. Poza domem połączysz się przez internet.</li>
        </ol>
        <pre class="conf"></pre>
        <div class="muted" style="font-size:12px;margin-top:8px">Ten plik zawiera klucz prywatny. Nie wysyłaj go nikomu.</div>
      </div>
    </div></div>`);
  $("pre", body).textContent = text;
  const copy = button(`${ICONS.copy}Kopiuj`, "", async () => {
    try { await navigator.clipboard.writeText(text); toast("Skopiowano konfigurację"); } catch (e) { toast("Nie udało się skopiować", true); }
  });
  const dl = el(`<a class="btn primary" href="/api/clients/${c.id}/config?download=1">${ICONS.download}Pobierz .conf</a>`);
  modal({ title: `Konfiguracja: ${c.name}`, body, wide: true, footer: [copy, dl] });
}

function editClient(c) {
  const form = el(`<form class="form">
    <label class="field">Nazwa<input type="text" name="name" maxlength="60" required></label>
    <label class="field">Notatka<input type="text" name="note" maxlength="300"></label>
    <div class="form-row">
      <label class="field">Ruch przez VPN<select name="mode"><option value="full">Cały ruch przez dom</option><option value="lan">Tylko sieć domowa</option></select></label>
      <label class="field">Serwery DNS<input type="text" name="dns" placeholder="domyślne"></label>
    </div>
    <div class="notice">Zmiana trybu lub DNS dotyczy pliku konfiguracyjnego klienta. Po zmianie zeskanuj kod QR ponownie na urządzeniu.</div>
    <div class="muted mono" style="font-size:11.5px;overflow-wrap:anywhere">Klucz publiczny: ${esc(c.public_key)}</div>
  </form>`);
  form.name.value = c.name; form.note.value = c.note || ""; form.mode.value = c.mode; form.dns.value = c.dns || "";
  const save = button("Zapisz", "primary");
  const regen = button(`${ICONS.key}Nowe klucze`, "", async () => {
    const ok = await confirmBox("Nowe klucze", `Wygenerować nowe klucze dla „${esc(c.name)}”? Obecna konfiguracja na urządzeniu przestanie działać.`, "Wygeneruj", true);
    if (!ok) return;
    try {
      const nc = await api(`/api/clients/${c.id}/regenerate`, { method: "POST" });
      m.close(); await refresh(); showConfig(nc, true);
    } catch (e) { toast(e.message, true); }
  });
  regen.style.marginRight = "auto";
  const m = modal({ title: "Edytuj klienta", body: form, footer: [regen, button("Anuluj", "", () => m.close()), save] });
  const submit = (e) => {
    e && e.preventDefault();
    withBusy(save, async () => {
      await api(`/api/clients/${c.id}`, { method: "PATCH", body: { name: form.name.value, note: form.note.value, mode: form.mode.value, dns: form.dns.value } });
      m.close(); toast("Zapisano zmiany"); refresh();
    });
  };
  form.addEventListener("submit", submit);
  save.addEventListener("click", submit);
}

async function toggleClient(c) {
  if (c.enabled) {
    const ok = await confirmBox("Wyłączyć klienta?", `„${esc(c.name)}” zostanie natychmiast rozłączony i nie połączy się, dopóki go nie włączysz. Konfiguracja na urządzeniu zostaje.`, "Wyłącz", true);
    if (!ok) return;
  }
  try {
    await api(`/api/clients/${c.id}`, { method: "PATCH", body: { enabled: !c.enabled } });
    toast(c.enabled ? `Wyłączono „${c.name}”` : `Włączono „${c.name}”`);
    refresh();
  } catch (e) { toast(e.message, true); }
}

async function deleteClient(c) {
  const ok = await confirmBox("Usunąć klienta?", `Klient „${esc(c.name)}” (${esc(c.address)}) zostanie usunięty z serwera. Tej operacji nie da się cofnąć. Urządzenie będzie potrzebowało nowej konfiguracji.`, "Usuń na zawsze", true);
  if (!ok) return;
  try {
    await api(`/api/clients/${c.id}`, { method: "DELETE" });
    toast(`Usunięto „${c.name}”`);
    refresh();
  } catch (e) { toast(e.message, true); }
}

/* ================================================================ szczegóły klienta */
const ClientDetail = {
  open(id) {
    const c = S.status && S.status.clients.find((x) => x.id === id);
    if (!c) return;
    this.id = id;
    this.range = "live";
    this.tab = "traffic";
    const body = el(`<div>
      <div class="grid kpi" style="margin-bottom:16px">
        <div class="card kpi-card"><div class="label">Stan</div><div class="value" style="font-size:18px" id="cd-state"></div><div class="sub" id="cd-state-sub"></div></div>
        <div class="card kpi-card"><div class="label">Prędkość</div><div class="value" style="font-size:18px"><span class="down" id="cd-down"></span></div><div class="sub up" id="cd-up"></div></div>
        <div class="card kpi-card"><div class="label">Ta sesja</div><div class="value" style="font-size:18px" id="cd-sess"></div><div class="sub" id="cd-sess-sub"></div></div>
        <div class="card kpi-card"><div class="label">Łącznie</div><div class="value" style="font-size:18px" id="cd-total"></div><div class="sub" id="cd-total-sub"></div></div>
      </div>
      <div class="tabs"><button data-tab="traffic" class="on">Ruch</button><button data-tab="conns">Połączenia</button><button data-tab="sessions">Sesje</button></div>
      <div data-pane="traffic"><div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-bottom:10px">${legend()}<div style="flex:1"></div>${rangeSeg(RANGES, "live")}</div><div id="cd-chart"></div></div>
      <div data-pane="conns" class="hidden"><div class="table-wrap" id="cd-conns"></div></div>
      <div data-pane="sessions" class="hidden"><div class="table-wrap" id="cd-sessions"></div></div>
    </div>`);
    const footer = [
      button(`${ICONS.qr}Kod QR`, "", () => showConfig(this.current())),
      button(`${ICONS.edit}Edytuj`, "", () => editClient(this.current())),
    ];
    this.m = modal({ title: c.name, body, wide: true, footer, onClose: () => { this.chart && this.chart.destroy(); this.chart = null; this.m = null; } });
    this.chart = new LineChart($("#cd-chart", body), { small: false });
    bindSeg($("[data-seg]", body), (k) => { this.range = k; this.loadChart(); });
    $(".tabs", body).addEventListener("click", (e) => {
      const b = e.target.closest("button[data-tab]");
      if (!b) return;
      this.tab = b.dataset.tab;
      $$(".tabs button", body).forEach((x) => x.classList.toggle("on", x === b));
      $$("[data-pane]", body).forEach((p) => p.classList.toggle("hidden", p.dataset.pane !== this.tab));
      this.loadTab();
    });
    this.update();
    this.loadChart();
  },
  current() { return S.status.clients.find((x) => x.id === this.id) || {}; },
  async loadChart() {
    const r = await api(`/api/history?range=${this.range}&client=${encodeURIComponent(this.id)}`).catch(() => null);
    if (r && this.chart) this.chart.set(r.points, r.step);
  },
  async loadTab() {
    if (!this.m) return;
    if (this.tab === "conns") {
      const r = await api(`/api/connections?client=${encodeURIComponent(this.id)}`).catch(() => null);
      if (!r || !this.m) return;
      $("#cd-conns").innerHTML = connTable(r.items.slice(0, 150), false, r);
    } else if (this.tab === "sessions") {
      const r = await api(`/api/sessions?client=${encodeURIComponent(this.id)}&limit=50`).catch(() => null);
      if (!r || !this.m) return;
      $("#cd-sessions").innerHTML = sessionTable(r.items, false);
    }
  },
  update() {
    if (!this.m) return;
    const c = this.current();
    if (!c.id) { this.m.close(); return; }
    $("#cd-state").innerHTML = statusBadge(c);
    $("#cd-state-sub").textContent = c.online ? `z ${hostOf(c.endpoint)}` : `ostatnio: ${ago(c.latest_handshake)}`;
    $("#cd-down").textContent = `↓ ${fmtRate(c.tx_rate)}`;
    $("#cd-up").textContent = `↑ ${fmtRate(c.rx_rate)}`;
    $("#cd-sess").textContent = c.session_start ? fmtDur(now() - c.session_start) : "—";
    $("#cd-sess-sub").textContent = c.active ? `↓ ${fmtBytes(c.tx_session)} · ↑ ${fmtBytes(c.rx_session)} od startu WG` : "";
    $("#cd-total").textContent = `↓ ${fmtBytes(c.total_tx)}`;
    $("#cd-total-sub").textContent = `↑ ${fmtBytes(c.total_rx)} · od ${fmtDateTime(c.created_at).split(" ")[0]}`;
    if (this.range === "live") this.loadChart();
    if (this.tab === "conns") this.loadTab();
  },
};

/* ================================================================ widok: połączenia */
function connTable(items, showClient, meta) {
  if (meta && meta.error) return `<div class="notice warn" style="margin:12px 16px">${esc(meta.error)}</div>`;
  if (!items.length) return '<div class="empty"><b>Brak aktywnych połączeń</b>Gdy klient VPN otworzy stronę lub aplikację, połączenie pojawi się tutaj.</div>';
  const acct = meta && meta.accounting;
  return `<table><thead><tr>${showClient ? "<th>Klient</th>" : ""}<th>Dokąd</th><th>Usługa</th><th class="hide-sm">Stan</th>${acct ? '<th class="right">↓ / ↑</th>' : ""}</tr></thead><tbody>${items.map((c) => `
    <tr>${showClient ? `<td class="nowrap"><b>${esc(c.client)}</b></td>` : ""}
      <td><div class="title" style="font-weight:500">${esc(c.host || c.dst)}${c.local ? ' <span class="badge">sieć domowa</span>' : ""}</div><div class="subtitle mono">${esc(c.dst)}:${c.dport}</div></td>
      <td class="nowrap">${esc(c.service || c.proto.toUpperCase())} <span class="faint">${esc(c.proto)}</span></td>
      <td class="hide-sm muted nowrap">${esc(c.state ? c.state.toLowerCase() : (c.flags || []).includes("ASSURED") ? "aktywne" : "nowe")}</td>
      ${acct ? `<td class="right num nowrap"><span class="down">${fmtBytes(c.bytes_in)}</span> <span class="up" style="font-size:12px">${fmtBytes(c.bytes_out)}</span></td>` : ""}
    </tr>`).join("")}</tbody></table>`;
}

const Connections = {
  title: "Połączenia",
  filter: "",
  actions() {
    const sel = el('<select style="width:auto;min-width:200px"><option value="">Wszyscy klienci</option></select>');
    (S.status ? S.status.clients : []).forEach((c) => sel.append(new Option(c.name, c.id)));
    sel.value = this.filter;
    sel.addEventListener("change", () => { this.filter = sel.value; this.load(); });
    return sel;
  },
  render(v) {
    v.innerHTML = `
      <div class="notice" id="cn-acct" style="margin-bottom:16px" hidden></div>
      <div class="grid two">
        <div class="card"><div class="card-h"><h2>Aktywne połączenia</h2><span class="badge" id="cn-count">0</span><div class="spacer"></div><span class="muted" style="font-size:12px">odświeżane co kilka sekund</span></div>
          <div class="card-b flush table-wrap" id="cn-list"></div></div>
        <div class="card"><div class="card-h"><h2>Najczęstsze cele</h2></div>
          <div class="card-b flush table-wrap" id="cn-top"></div></div>
      </div>`;
    this.load();
  },
  async load() {
    const q = this.filter ? `?client=${encodeURIComponent(this.filter)}` : "";
    const r = await api(`/api/connections${q}`).catch(() => null);
    if (!r || S.view !== "connections") return;
    this.last = now();
    $("#cn-count").textContent = r.total;
    $("#cn-list").innerHTML = connTable(r.items, true, r);
    const acct = $("#cn-acct");
    acct.hidden = r.accounting || !r.items.length || !!r.error;
    acct.innerHTML = "Liczniki bajtów na połączenie są wyłączone w jądrze. Żeby je włączyć, uruchom na serwerze: <span class='mono'>sudo sysctl -w net.netfilter.nf_conntrack_acct=1</span> (instalator robi to automatycznie).";
    $("#cn-top").innerHTML = r.top.length ? `<table><thead><tr><th>Cel</th><th class="right">Poł.</th>${r.accounting ? '<th class="right">Dane</th>' : ""}</tr></thead><tbody>${r.top.map((d) => `
      <tr><td><div class="title" style="font-weight:500">${esc(d.dest)}</div><div class="subtitle">${esc(d.services.join(", ") || "")}${d.clients.length ? ` · ${esc(d.clients.join(", "))}` : ""}</div></td>
      <td class="right num">${d.count}</td>${r.accounting ? `<td class="right num nowrap">${fmtBytes(d.bytes_in + d.bytes_out)}</td>` : ""}</tr>`).join("")}</tbody></table>` : '<div class="empty">Brak danych</div>';
  },
  update() { if (!this.last || now() - this.last >= 4) this.load(); },
};

/* ================================================================ widok: historia */
function sessionTable(items, showClient) {
  if (!items.length) return '<div class="empty"><b>Brak sesji</b>Sesja pojawi się, gdy klient połączy się z VPN.</div>';
  return `<table><thead><tr>${showClient ? "<th>Klient</th>" : ""}<th>Początek</th><th>Czas</th><th class="hide-sm">Skąd</th><th class="right">↓ / ↑</th></tr></thead><tbody>${items.map((s) => `
    <tr>${showClient ? `<td class="nowrap"><b>${esc(s.name || "(usunięty)")}</b></td>` : ""}
      <td class="nowrap">${fmtDateTime(s.started_at)}</td>
      <td class="nowrap">${s.active ? `<span class="badge ok"><span class="dot ok"></span>trwa · ${fmtDur(now() - s.started_at)}</span>` : fmtDur((s.ended_at || s.last_seen) - s.started_at)}</td>
      <td class="hide-sm mono">${esc(hostOf(s.endpoint) || "—")}</td>
      <td class="right num nowrap"><span class="down">${fmtBytes(s.tx)}</span> <span class="up" style="font-size:12px">${fmtBytes(s.rx)}</span></td>
    </tr>`).join("")}</tbody></table>`;
}

const History = {
  title: "Historia",
  days: 30,
  render(v) {
    v.innerHTML = `
      <div class="card"><div class="card-h"><h2>Zużycie danych dziennie</h2>${legend()}<div class="spacer"></div>${rangeSeg([["7", "7 dni"], ["30", "30 dni"], ["90", "90 dni"]], String(this.days))}</div>
        <div class="card-b"><div id="h-chart"></div></div></div>
      <div class="grid two" style="margin-top:16px">
        <div class="card"><div class="card-h"><h2>Ostatnie sesje</h2></div><div class="card-b flush table-wrap" id="h-sessions"></div></div>
        <div class="card"><div class="card-h"><h2>Zużycie według klientów</h2></div><div class="card-b flush table-wrap" id="h-clients"></div></div>
      </div>`;
    this.chart = new BarChart($("#h-chart", v));
    bindSeg($("[data-seg]", v), (k) => { this.days = Number(k); this.load(); });
    this.load();
  },
  async load() {
    const [u, s] = await Promise.all([api(`/api/usage?days=${this.days}`), api("/api/sessions?limit=100")]).catch(() => [null, null]);
    if (!u || S.view !== "history") return;
    this.last = now();
    this.chart.set(u.days);
    const total = u.clients.reduce((a, c) => a + c.rx + c.tx, 0) || 1;
    $("#h-clients").innerHTML = u.clients.length ? `<table><thead><tr><th>Klient</th><th class="right">↓ do klienta</th><th class="right">↑ od klienta</th><th class="hide-sm" style="width:30%">Udział</th></tr></thead><tbody>${u.clients.map((c) => `
      <tr><td><b>${esc(c.name)}</b></td><td class="right num">${fmtBytes(c.tx)}</td><td class="right num">${fmtBytes(c.rx)}</td>
      <td class="hide-sm"><div class="bar"><i style="width:${(((c.rx + c.tx) / total) * 100).toFixed(1)}%"></i></div></td></tr>`).join("")}</tbody></table>` : '<div class="empty">Brak danych w tym okresie</div>';
    $("#h-sessions").innerHTML = sessionTable(s.items, true);
  },
  update() { if (now() - (this.last || 0) > 30) this.load(); },
  destroy() { this.chart && this.chart.destroy(); },
};

/* ================================================================ widok: dziennik */
const EVENT_KINDS = [["", "Wszystko"], ["connect", "Połączenia"], ["disconnect", "Rozłączenia"], ["client", "Klienci"], ["auth", "Logowania"], ["system", "System"]];
const EVENT_ICON = { connect: ICONS.plug, disconnect: ICONS.unplug, roam: ICONS.route, client: ICONS.user, auth: ICONS.lock, settings: ICONS.gear, system: ICONS.gear };
const Events = {
  title: "Dziennik",
  kind: "",
  render(v) {
    v.innerHTML = `<div style="margin-bottom:14px">${rangeSeg(EVENT_KINDS, this.kind)}</div><div class="card"><div id="ev-list"></div></div>`;
    bindSeg($("[data-seg]", v), (k) => { this.kind = k; this.load(); });
    this.load();
  },
  async load() {
    const r = await api(`/api/events?limit=300${this.kind ? `&kind=${this.kind}` : ""}`).catch(() => null);
    if (!r || S.view !== "events") return;
    this.last = now();
    $("#ev-list").innerHTML = r.items.length ? r.items.map((e) => `
      <div class="event"><span class="when muted nowrap">${fmtDateTime(e.ts)}</span>
      <span class="ico ${esc(e.kind)}">${EVENT_ICON[e.kind] || ICONS.gear}</span><span>${esc(e.message)}</span></div>`).join("") : '<div class="empty">Brak wpisów</div>';
  },
  update() { if (now() - (this.last || 0) > 10) this.load(); },
};

/* ================================================================ widok: ustawienia */
const Settings = {
  title: "Ustawienia",
  async render(v) {
    v.innerHTML = '<div class="empty">Wczytuję…</div>';
    let s;
    try { s = await api("/api/settings"); } catch (e) { v.innerHTML = `<div class="notice bad">${esc(e.message)}</div>`; return; }
    S.settings = s;
    const i = s.info;
    v.innerHTML = `
      <div class="grid half">
        <div class="card"><div class="card-h"><h2>Konfiguracja dla nowych klientów</h2></div><div class="card-b">
          <form class="form" id="st-form">
            <label class="field">Adres serwera (Endpoint) <span class="hint">nazwa DuckDNS lub adres IP i port, np. twoja-nazwa.duckdns.org:51820</span><input type="text" name="endpoint" required></label>
            <div class="form-row">
              <label class="field">Serwery DNS<input type="text" name="dns" placeholder="1.1.1.1, 1.0.0.1"></label>
              <label class="field">Sieć domowa<input type="text" name="lan_subnet" placeholder="192.168.1.0/24"></label>
            </div>
            <div class="form-row">
              <label class="field">Keepalive (s) <span class="hint">utrzymuje połączenie za NAT-em</span><input type="number" name="keepalive" min="0" max="600"></label>
              <label class="field">MTU <span class="hint">puste = automatycznie</span><input type="text" name="mtu" placeholder="np. 1380"></label>
            </div>
            <label class="field">Domyślny tryb nowych klientów<select name="default_mode"><option value="full">Cały ruch przez dom</option><option value="lan">Tylko sieć domowa</option></select></label>
            <div class="notice">Zmiany dotyczą plików konfiguracyjnych klientów. Istniejące urządzenia muszą ponownie zeskanować kod QR, żeby je dostać.</div>
            <div><button class="btn primary" type="submit">Zapisz ustawienia</button></div>
          </form></div></div>
        <div style="display:grid;gap:16px;align-content:start">
          <div class="card"><div class="card-h"><h2>Serwer WireGuard</h2></div><div class="card-b"><dl class="facts">
            <dt>Interfejs</dt><dd class="mono">${esc(i.interface)}</dd>
            <dt>Adres w VPN</dt><dd class="mono">${esc(i.address)}</dd>
            <dt>Port</dt><dd class="mono">${esc(i.listen_port ?? "—")}</dd>
            <dt>Klucz publiczny</dt><dd class="mono">${esc(i.public_key || "—")}</dd>
            <dt>Plik</dt><dd class="mono">${esc(i.conf_path)}</dd>
            <dt>NAT (PostUp)</dt><dd class="mono" style="font-size:11.5px">${i.post_up.length ? i.post_up.map(esc).join("<br>") : '<span style="color:var(--warn)">brak: klienci w trybie „cały ruch” nie wyjdą do internetu</span>'}</dd>
          </dl>
          ${i.save_config ? '<div class="notice warn" style="margin-top:12px">W pliku jest <b>SaveConfig = true</b>. wg-quick może nadpisać zmiany z panelu przy wyłączaniu interfejsu. Zalecane: usuń tę linię.</div>' : ""}
          ${i.conntrack_error ? `<div class="notice warn" style="margin-top:12px">${esc(i.conntrack_error)}</div>` : ""}
          </div></div>
          <div class="card"><div class="card-h"><h2>Zmiana hasła</h2><div class="spacer"></div><span class="muted" style="font-size:12px">login: ${esc(i.username)}</span></div><div class="card-b">
            <form class="form" id="pw-form">
              <label class="field">Obecne hasło<input type="password" name="current" autocomplete="current-password" required></label>
              <div class="form-row">
                <label class="field">Nowe hasło<input type="password" name="new" autocomplete="new-password" minlength="8" required></label>
                <label class="field">Powtórz<input type="password" name="repeat" autocomplete="new-password" minlength="8" required></label>
              </div>
              <div><button class="btn" type="submit">Zmień hasło</button></div>
            </form></div></div>
          <div class="card"><div class="card-h"><h2>Panel</h2></div><div class="card-b"><dl class="facts">
            <dt>Wersja</dt><dd class="mono">${esc(i.version)}</dd>
            <dt>Zbudowano</dt><dd>${esc(i.build_date || "—")}</dd>
            <dt>Aktualizacje</dt><dd>automatyczne po każdym pushu na gałąź main</dd>
          </dl></div></div>
        </div>
      </div>`;
    const f = $("#st-form", v);
    ["endpoint", "dns", "lan_subnet", "keepalive", "mtu", "default_mode"].forEach((k) => { f[k].value = s[k] ?? ""; });
    f.addEventListener("submit", (e) => {
      e.preventDefault();
      withBusy($("button[type=submit]", f), async () => {
        S.settings = { ...S.settings, ...(await api("/api/settings", { method: "PUT", body: Object.fromEntries(new FormData(f)) })) };
        toast("Zapisano ustawienia");
      });
    });
    const pf = $("#pw-form", v);
    pf.addEventListener("submit", (e) => {
      e.preventDefault();
      if (pf.new.value !== pf.repeat.value) return toast("Hasła nie są takie same", true);
      withBusy($("button[type=submit]", pf), async () => {
        await api("/api/password", { method: "POST", body: { current: pf.current.value, new: pf.new.value } });
        pf.reset();
        toast("Hasło zmienione. Inne sesje zostały wylogowane.");
      });
    });
  },
  update() {},
};

/* ================================================================ router */
const VIEWS = { dashboard: Dashboard, clients: Clients, connections: Connections, history: History, events: Events, settings: Settings };

function route() {
  const name = (location.hash || "#dashboard").slice(1);
  const view = VIEWS[name] ? name : "dashboard";
  if (S.viewObj && S.viewObj.destroy) S.viewObj.destroy();
  S.view = view;
  S.viewObj = VIEWS[view];
  $$("#nav a").forEach((a) => a.classList.toggle("active", a.dataset.view === view));
  $("#view-title").textContent = S.viewObj.title;
  const actions = $("#view-actions");
  actions.innerHTML = "";
  if (S.viewObj.actions) actions.append(S.viewObj.actions());
  $("#app").classList.remove("nav-open");
  const v = $("#view");
  v.innerHTML = "";
  S.viewObj.render(v);
  if (S.status && S.viewObj.update) S.viewObj.update(S.status);
}

function applyStatus() {
  const st = S.status;
  if (!st) return;
  $("#nav-online").textContent = st.wg.online;
  $("#nav-online").className = `badge ${st.wg.online ? "ok" : ""}`;
  const wb = $("#wg-badge");
  wb.textContent = st.wg.up ? "działa" : "nie działa";
  wb.className = `badge ${st.wg.up ? "ok" : "bad"}`;
  $("#version").textContent = st.version;
  $("#host-name").textContent = (st.server && st.server.hostname) || "WireGuard";
  $("#mock-banner").classList.toggle("hidden", !st.mock);
  if (S.viewObj && S.viewObj.update) S.viewObj.update(st);
  if (ClientDetail.m) ClientDetail.update();
}

async function loop() {
  if (!document.hidden) await refresh();
  S.timer = setTimeout(loop, 2000);
}

$("#menu-btn").addEventListener("click", () => $("#app").classList.toggle("nav-open"));
$("#theme-btn").addEventListener("click", () => {
  const next = document.documentElement.getAttribute("data-theme") === "light" ? "dark" : "light";
  document.documentElement.setAttribute("data-theme", next);
  try { localStorage.setItem("vpnhost-theme", next); } catch (e) { /* brak dostępu */ }
  if (S.viewObj && S.viewObj.chart) S.viewObj.chart.draw();
});
$("#logout-btn").addEventListener("click", async () => {
  await api("/api/logout", { method: "POST" }).catch(() => {});
  location.href = "/login";
});
window.addEventListener("hashchange", route);
document.addEventListener("visibilitychange", () => { if (!document.hidden) refresh(); });

(async () => {
  api("/api/settings").then((s) => { S.settings = s; }).catch(() => {});
  await refresh();
  route();
  S.timer = setTimeout(loop, 2000);
})();
