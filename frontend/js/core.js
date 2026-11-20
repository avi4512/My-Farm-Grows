// Shared state, the API helper, formatting, motion helpers and the mobile menu.
// Plain scripts loaded in order by index.html; they share one global scope.

const API_BASE = window.location.origin;
let token = localStorage.getItem("mfg_access_token") || "";
let currentUser = null;
let authMode = "login";
let products = [];
let catalog = [];
let homeTab = "All";
let adminOrders = [];
let cart = {items: [], total: 0};
let addresses = [];
let selectedAddressId = null;
let selectedCategory = "All";
let lastPlacedOrder = null;
let lastOrderMessage = "";
let toastTimer;


// ---- Motion helpers ----
const sleep = ms => new Promise(r => setTimeout(r, ms));
function skeletonCards(n) {
  return Array.from({length:n}, () => `<div class="bg-white rounded-xl border border-stone-200 overflow-hidden"><div class="h-44 skel"></div><div class="p-4 space-y-3"><div class="h-4 w-2/3 rounded skel"></div><div class="h-3 w-full rounded skel"></div><div class="h-3 w-1/2 rounded skel"></div><div class="h-9 w-28 rounded skel mt-4"></div></div></div>`).join("");
}
function setBtnBusy(btn, label) {
  const html = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = `<span class="mini-spin"></span> ${label}`;
  return ok => {
    if (!ok) { btn.innerHTML = html; btn.disabled = false; return; }
    btn.innerHTML = "✓ Added"; btn.classList.add("btn-done");
    setTimeout(() => { btn.innerHTML = html; btn.disabled = false; btn.classList.remove("btn-done"); }, 1000);
  };
}
function bumpCartBadge() { const ic = document.querySelector(".cart-ico"); if (ic) { ic.classList.remove("cart-wig"); void ic.getBoundingClientRect(); ic.classList.add("cart-wig"); }
  const b = document.getElementById("cart-badge");
  b.classList.remove("badge-bump"); void b.offsetWidth; b.classList.add("badge-bump");
}
function flyToCart(btn) {
  const badge = document.getElementById("cart-badge");
  if (!badge || !btn || matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  const a = btn.getBoundingClientRect(), b = badge.getBoundingClientRect();
  const dot = document.createElement("div");
  dot.className = "fly-dot";
  dot.style.left = (a.left + a.width / 2 - 10) + "px";
  dot.style.top = (a.top + a.height / 2 - 10) + "px";
  document.body.appendChild(dot);
  requestAnimationFrame(() => {
    dot.style.transform = `translate(${b.left + b.width / 2 - a.left - a.width / 2}px,${b.top + b.height / 2 - a.top - a.height / 2}px) scale(.35)`;
    dot.style.opacity = ".5";
  });
  setTimeout(() => dot.remove(), 800);
}
function flashRow(itemId) {
  const row = document.getElementById("cart-row-" + itemId);
  if (row) { row.classList.add("row-flash"); setTimeout(() => row.classList.remove("row-flash"), 700); }
}
function selectAddress(id) {
  selectedAddressId = id;
  document.querySelectorAll("#address-list label").forEach(l => {
    const on = Number(l.querySelector("input").value) === id;
    l.classList.toggle("border-brand-600", on);
    l.classList.toggle("bg-brand-50", on);
    if (on) { l.classList.remove("addr-pop"); void l.offsetWidth; l.classList.add("addr-pop"); }
  });
  renderCheckoutSummary();
}
let _ovTimers = [], _ovStart = 0;
function showOrderOverlay() {
  let o = document.getElementById("order-overlay");
  if (!o) {
    o = document.createElement("div");
    o.id = "order-overlay";
    o.innerHTML = `<div class="ov-card"><div class="ov-spinner"></div><h3 id="ov-title">Placing your order…</h3><ul id="ov-steps"><li>Checking stock</li><li>Confirming delivery address</li><li>Reserving your items</li></ul></div>`;
    document.body.appendChild(o);
  }
  o.querySelector(".ov-card").classList.remove("ok");
  o.querySelector(".ov-spinner").textContent = "";
  document.getElementById("ov-title").textContent = "Placing your order…";
  const lis = [...o.querySelectorAll("#ov-steps li")];
  lis.forEach(l => l.className = "");
  lis[0].className = "active";
  _ovTimers.forEach(clearTimeout);
  _ovTimers = [
    setTimeout(() => { lis[0].className = "done"; lis[1].className = "active"; }, 550),
    setTimeout(() => { lis[1].className = "done"; lis[2].className = "active"; }, 1100)
  ];
  _ovStart = Date.now();
  o.classList.add("show");
}
async function finishOrderOverlay() {
  const wait = 1500 - (Date.now() - _ovStart);
  if (wait > 0) await sleep(wait);
  _ovTimers.forEach(clearTimeout);
  document.querySelectorAll("#ov-steps li").forEach(l => l.className = "done");
  document.getElementById("ov-title").textContent = "Order confirmed!";
  const card = document.querySelector("#order-overlay .ov-card");
  card.classList.add("ok");
  card.querySelector(".ov-spinner").textContent = "✓";
  await sleep(700);
  hideOrderOverlay();
}
function hideOrderOverlay() {
  _ovTimers.forEach(clearTimeout);
  document.getElementById("order-overlay")?.classList.remove("show");
}
function launchConfetti() {
  const colors = ["#3f7d20", "#cfe88a", "#a8763e", "#e0a526", "#c4622d"];
  const wrap = document.createElement("div");
  wrap.className = "confetti-wrap";
  for (let i = 0; i < 60; i++) {
    const p = document.createElement("i");
    p.style.cssText = `left:${Math.random()*100}%;background:${colors[i%5]};--dx:${(Math.random()-.5)*220}px;--rot:${Math.random()*720}deg;animation-delay:${Math.random()*.4}s;animation-duration:${1.6+Math.random()*1.2}s`;
    wrap.appendChild(p);
  }
  document.body.appendChild(wrap);
  setTimeout(() => wrap.remove(), 3500);
}

async function api(path, options = {}) {
  const headers = {...(options.headers || {})};
  if (options.body && !(options.body instanceof FormData) && typeof options.body !== "string") {
    headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(options.body);
  }
  if (window.location.protocol === "file:") throw new Error("this page was opened as a file. Start the server and open its address instead.");
  if (token) headers.Authorization = `Bearer ${token}`;
  const response = await fetch(`${API_BASE}${path}`, {...options, headers});
  if (response.status === 204) return null;
  const text = await response.text();
  let data = null;
  try { data = text ? JSON.parse(text) : null; } catch { data = text; }
  if (!response.ok) {
    if (response.status === 401) { token = ""; localStorage.removeItem("mfg_access_token"); currentUser = null; updateAccountButton(); }
    const detail = data && (data.detail || data.message) ? (typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail)) : `Request failed (${response.status})`;
    throw new Error(detail);
  }
  return data;
}
function notify(message) {
  const el = document.getElementById("toast");
  el.textContent = message; el.classList.remove("hidden"); el.classList.remove("toast-in"); void el.offsetWidth; el.classList.add("toast-in");
  clearTimeout(toastTimer); toastTimer = setTimeout(() => el.classList.add("hidden"), 3500);
}
function money(value) { return new Intl.NumberFormat("en-IN", {style:"currency", currency:"INR", maximumFractionDigits:2}).format(Number(value || 0)); }
function esc(value) { return String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c])); }
function updateAccountButton() {
  const btn = document.getElementById("account-button");
  btn.textContent = currentUser ? `${currentUser.name} · Logout` : "Login / Register";
  const adminNav = document.getElementById("nav-admin");
  if (adminNav) adminNav.classList.toggle("hidden", currentUser?.role !== "admin");
  document.getElementById("mobile-nav-admin").classList.toggle("hidden", currentUser?.role !== "admin");
  document.getElementById("mobile-nav-account").textContent = btn.textContent;
  btn.title = btn.textContent;
  const adminMenu = document.getElementById("admin-menu-wrap");
  const customerMenu = document.getElementById("customer-menu-wrap");
  const customerGreeting = document.getElementById("customer-menu-greeting");
  const isAdmin = currentUser?.role === "admin";
  const isCustomer = Boolean(currentUser && currentUser.role !== "admin");
  if (adminMenu) adminMenu.classList.toggle("hidden", !isAdmin);
  if (customerMenu) customerMenu.classList.toggle("hidden", !isCustomer);
  if (customerGreeting && currentUser) customerGreeting.textContent = `Hello, ${currentUser.name || "Customer"}`;
  renderFeatured();
}
function toggleMobileNav() {
  const panel = document.getElementById("mobile-nav");
  const open = panel.classList.toggle("hidden") === false;
  document.getElementById("mobile-nav-toggle").setAttribute("aria-expanded", String(open));
  // Give the open menu its own history entry so the phone's back button closes it
  // instead of leaving the site.
  if (open) history.pushState({...(history.state || {}), menu: true}, "", location.href);
  else if (history.state?.menu) history.back();
}
function closeMobileNav() {
  document.getElementById("mobile-nav").classList.add("hidden");
  document.getElementById("mobile-nav-toggle").setAttribute("aria-expanded", "false");
}
// Close the menu and drop its history entry when no navigation took its place.
function dismissMobileNav() {
  closeMobileNav();
  if (history.state?.menu) history.back();
}
function mobileNavGo(viewName) { closeMobileNav(); navigate(viewName); if (history.state?.menu) history.back(); }
function openSearch() {
  navigate("products");
  document.getElementById("search-input").focus({preventScroll: true});
}
