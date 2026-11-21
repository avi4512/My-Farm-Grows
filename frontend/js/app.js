// Interaction effects (pops, counters, live admin alerts) and page start-up. Loaded last.
// Plain scripts loaded in order by index.html; they share one global scope.

// ---- Interaction layer: pops, scroll, hover, click, counters, live admin alerts ----
const ORDER_COLORS = {pending:"#f59e0b", processing:"#3b82f6", shipped:"#8b5cf6", delivered:"#22c55e", cancelled:"#ef4444"};
let _lastMaxOrder = null;
const _cnt = {};
function showPop({img, title, sub, icon, logo, action, ms = 3400}) {
  let st = document.getElementById("pop-stack");
  if (!st) { st = document.createElement("div"); st.id = "pop-stack"; document.body.appendChild(st); }
  const el = document.createElement("div");
  el.className = "pop";
  const lead = logo ? '<svg class="w-11 h-11 flex-shrink-0 logo-float"><use href="#mfg-logo"/></svg>'
    : img ? `<img src="${esc(img)}" alt="" onerror="this.remove()">` : `<span class="pop-ic">${icon || "✓"}</span>`;
  el.innerHTML = `${lead}<div class="min-w-0 flex-1"><p class="font-bold text-sm truncate">${esc(title)}</p><p class="text-xs text-stone-500 truncate">${esc(sub || "")}</p></div>${action ? `<button class="pop-act" onclick="${action.fn}; this.closest('.pop').remove()">${esc(action.label)}</button>` : ""}<i class="pop-bar" style="animation-duration:${ms}ms"></i>`;
  st.prepend(el);
  while (st.children.length > 4) st.lastChild.remove();
  setTimeout(() => { el.classList.add("out"); setTimeout(() => el.remove(), 300); }, ms);
}
function showAddedPop(productId) {
  const p = productById(productId);
  const line = (cart.items || []).find(i => Number(i.product_id) === Number(productId));
  showPop({img: p ? getProductImage(p) : "", title: p?.name || line?.product_name || "Item", sub: `Added to cart${line ? " · " + line.quantity + " in cart" : ""}`, action: {label: "View cart", fn: "navigate('cart')"}});
}
function showWelcome(u) {
  const admin = u.role === "admin";
  showPop({logo: true, title: `Welcome${admin ? "" : " back"}, ${u.name}`, sub: admin ? "Your dashboard is ready" : "Fresh stock is waiting for you", ms: 3000});
}
function shakeEl(el) { if (!el) return; el.classList.remove("shake"); void el.offsetWidth; el.classList.add("shake"); }
async function withBusy(btn, label, fn) {
  if (!btn) return fn();
  const h = btn.innerHTML; btn.disabled = true; btn.innerHTML = `<span class="mini-spin"></span> ${label}`;
  try { return await fn(); } finally { btn.disabled = false; btn.innerHTML = h; }
}
function countTo(el, to, fmt = v => Math.round(v), from = 0) {
  if (!el) return;
  to = Number(to) || 0;
  if (from === to || matchMedia("(prefers-reduced-motion: reduce)").matches) { el.textContent = fmt(to); return; }
  const t0 = performance.now();
  (function f(t) { const k = Math.min(1, (t - t0) / 700), e = 1 - Math.pow(1 - k, 3); el.textContent = fmt(from + (to - from) * e); if (k < 1) requestAnimationFrame(f); })(t0);
}
function animateCounts() {
  document.querySelectorAll("[data-count]").forEach(el => {
    const key = (el.closest("[id]")?.id || "") + (el.previousElementSibling?.textContent || "");
    const to = Number(el.dataset.count);
    countTo(el, to, undefined, _cnt[key] ?? 0); _cnt[key] = to; el.removeAttribute("data-count");
  });
}
function setActiveNav(v) {
  document.querySelectorAll("header nav button").forEach(b => b.classList.toggle("nav-active", b.id === "nav-" + v));
  document.querySelectorAll("#app-tabbar button[data-view]").forEach(b => {
    const on = b.dataset.view === v;
    b.classList.toggle("is-active", on);
    if (on) b.setAttribute("aria-current", "page"); else b.removeAttribute("aria-current");
  });
}
const _origNavigate = navigate;
window.navigate = function (v, options) { _origNavigate(v, options); setActiveNav(v); };
setActiveNav("home");

(function initInteractions() {
  // Splash with logo
  const splash = document.createElement("div");
  splash.id = "splash";
  splash.innerHTML = '<svg class="logo-float" width="84" height="84"><use href="#mfg-logo"/></svg><span>My Farm Grow</span>';
  document.body.appendChild(splash);
  addEventListener("load", () => setTimeout(() => { splash.classList.add("out"); setTimeout(() => splash.remove(), 600); }, 700));
  // Scroll progress, sticky header, back-to-top, hero parallax
  const bar = document.createElement("div"); bar.id = "scroll-bar"; document.body.appendChild(bar);
  const up = document.createElement("button"); up.id = "to-top"; up.setAttribute("aria-label", "Back to top"); up.textContent = "↑";
  up.onclick = () => scrollTo({top: 0, behavior: "smooth"}); document.body.appendChild(up);
  const hdr = document.querySelector("header"); let tick = false;
  addEventListener("scroll", () => {
    if (tick) return; tick = true;
    requestAnimationFrame(() => {
      const y = scrollY, h = document.documentElement.scrollHeight - innerHeight;
      bar.style.width = (h > 0 ? y / h * 100 : 0) + "%";
      hdr.classList.toggle("scrolled", y > 30); up.classList.toggle("show", y > 500);
      tick = false;
    });
  }, {passive: true});
  // Scroll reveal for home sections and footer
  const io = new IntersectionObserver(es => es.forEach(e => {
    if (!e.isIntersecting) return;
    e.target.classList.add("in"); io.unobserve(e.target);
    setTimeout(() => { e.target.removeAttribute("data-reveal"); e.target.classList.remove("in"); e.target.style.transitionDelay = ""; }, 1100);
  }), {threshold: .12});
  document.querySelectorAll("#view-home .grid > div, #view-home h2, footer .grid > div").forEach((el, i) => {
    el.setAttribute("data-reveal", ""); el.style.transitionDelay = ((i % 6) * 90) + "ms"; io.observe(el);
  });
  document.querySelectorAll("#view-home .grid > div").forEach(el => el.classList.add("card-fx"));
  // Cursor: card tilt + hero spotlight
  const fine = !matchMedia("(hover: none)").matches;
  document.addEventListener("mousemove", e => {
    if (!fine) return;
    const c = e.target.closest?.(".card-fx");
    if (c && !c.hasAttribute("data-reveal")) {
      const r = c.getBoundingClientRect(), x = (e.clientX - r.left) / r.width - .5, y = (e.clientY - r.top) / r.height - .5;
      const s = r.width > 500 ? 0 : 6;
      c.style.transform = `perspective(700px) rotateY(${x * s}deg) rotateX(${-y * s}deg) translateY(-3px)`;
    }
    const hero = e.target.closest?.("#view-home > div:first-child");
    if (hero) { const r = hero.getBoundingClientRect(); hero.style.setProperty("--hx", (e.clientX - r.left) + "px"); hero.style.setProperty("--hy", (e.clientY - r.top) + "px"); }
  });
  document.addEventListener("mouseout", e => { const c = e.target.closest?.(".card-fx"); if (c && !c.contains(e.relatedTarget)) c.style.transform = ""; });
  // Click ripple on every button
  document.addEventListener("click", e => {
    const b = e.target.closest("button");
    if (!b || b.disabled || b.id === "to-top" || b.querySelector("#cart-badge")) return;
    const r = b.getBoundingClientRect(), d = Math.max(r.width, r.height), s = document.createElement("span");
    s.className = "ripple"; s.style.cssText = `width:${d}px;height:${d}px;left:${e.clientX - r.left - d / 2}px;top:${e.clientY - r.top - d / 2}px`;
    if (getComputedStyle(b).position === "static") b.style.position = "relative";
    b.style.overflow = "hidden"; b.appendChild(s); setTimeout(() => s.remove(), 650);
  });
  // Live alert for admins when a new order arrives
  setInterval(async () => {
    if (!currentUser || currentUser.role !== "admin" || document.hidden) return;
    try {
      const os = await api("/api/admin/orders"); const m = Math.max(0, ...os.map(o => o.id));
      if (_lastMaxOrder !== null && m > _lastMaxOrder) {
        const n = os.find(o => o.id === m);
        showPop({icon: "🛒", title: `New order #${m}`, sub: `${n.recipient_name} · ${money(n.total_amount)}`, action: {label: "Review", fn: "navigate('admin')"}, ms: 7000});
        if (!document.getElementById("view-admin").classList.contains("hidden")) { adminOrders = os; renderAdminOrders(); }
      }
      _lastMaxOrder = m;
    } catch {}
  }, 20000);
})();


async function loadPaymentHistory() { try { return await api("/api/payments/history"); } catch(error) { notify(error.message); return []; } }
window.addEventListener("DOMContentLoaded", async ()=>{
  if(window.lucide) lucide.createIcons();
  loadPaymentConfig();
  await loadMe();
  if(token){try{cart=await api("/api/cart");updateCartBadge();}catch{}}
  await loadCatalog();
  await renderProducts();
  showPaymentReturn();
  // Open the view named in the address (e.g. #products) and seed the history entry.
  const startView = location.hash.slice(1);
  if (startView && startView !== "home" && document.getElementById(`view-${startView}`)) navigate(startView);
  else history.replaceState(viewState("home"), "", location.href);
});
