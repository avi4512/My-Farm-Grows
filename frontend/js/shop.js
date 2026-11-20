// Navigation and history, the product catalog, product cards and the cart.
// Plain scripts loaded in order by index.html; they share one global scope.

// Each view change is recorded in browser history so the phone's back button
// steps back through the site instead of closing it.
function viewState(viewName) { return {view: viewName, category: selectedCategory}; }
function recordView(viewName) {
  const state = viewState(viewName), current = history.state;
  const url = viewName === "home" ? location.pathname + location.search : `#${viewName}`;
  if (!current || current.menu || (current.view === state.view && current.category === state.category)) history.replaceState(state, "", url);
  else history.pushState(state, "", url);
}
function navigate(viewName, options = {}) {
  document.querySelectorAll(".view-panel").forEach(el => el.classList.add("hidden"));
  const view = document.getElementById(`view-${viewName}`);
  if (view) view.classList.remove("hidden");
  if (viewName === "products") renderProducts();
  if (viewName === "cart") loadCart();
  if (viewName === "checkout") loadCheckout();
  if (viewName === "orders") loadOrders();
  if (viewName !== "tracking") stopTrackingRefresh();
  if (viewName === "tracking") loadTracking();
  if (viewName === "payments") loadPaymentHistoryView();
  if (viewName === "addresses") loadMyAddresses();
  if (viewName === "order-success") renderOrderSuccess();
  if (viewName === "dashboard") loadCustomerDashboard();
  if (["admin", "deliveries", "inventory", "inventory-history", "admin-products", "admin-payments", "admin-customers"].includes(viewName)) {
    if (!currentUser || currentUser.role !== "admin") {
      notify("Administrator access is required.");
      navigate("home", options);
      return;
    }
    if (viewName === "admin") loadAdminOrders();
    if (viewName === "deliveries") loadAdminDeliveries();
    if (viewName === "inventory") loadAdminInventory();
    if (viewName === "inventory-history") loadInventoryHistoryView();
    if (viewName === "admin-products") loadAdminProducts();
    if (viewName === "admin-payments") loadAdminPayments();
    if (viewName === "admin-customers") loadAdminCustomers();
  }
  if (!options.fromHistory) recordView(viewName);
  window.scrollTo({top:0, behavior:"smooth"});
}
function setSelectedCategory(category) {
  selectedCategory = category;
  document.querySelectorAll(".cat-btn").forEach(btn => {
    const active = btn.getAttribute("data-category") === category;
    btn.className = `cat-btn w-full text-left px-3 py-2 rounded-lg ${active ? "bg-brand-50 text-brand-700 font-semibold" : "hover:bg-stone-50 text-stone-600"}`;
  });
}
function filterCategory(category) {
  setSelectedCategory(category);
  navigate("products");
}
window.addEventListener("popstate", event => {
  const state = event.state || {view: "home", category: "All"};
  closeMobileNav();
  if (!document.getElementById("account-modal").classList.contains("hidden")) closeAccount();
  if (state.menu) return;
  if (state.category && state.category !== selectedCategory) setSelectedCategory(state.category);
  navigate(state.view || "home", {fromHistory: true});
});
let searchTimer;
function handleSearch() { clearTimeout(searchTimer); searchTimer = setTimeout(renderProducts, 250); }
// Product image paths served by FastAPI from frontend/images/.
// Windows path example: D:\\Project\\frontend\\images\\basmati-rice.jpg
// Browser URL for that file: images/basmati-rice.jpg
// An image set by the admin (products.image_url) wins; the name matching
// below only covers products created before that field existed.
function getProductImage(product) {
  if (product.image_url) return product.image_url;
  const name = String(product.name || "").toLowerCase();
  if (name.includes("sona masoori") || name.includes("sonamasuri")) return "images/sona-masoori-rice.jpg";
  if (name.includes("basmati")) return "images/basmati-rice.jpg";
  if (name.includes("brown rice")) return "images/brown-rice.jpg";
  if (name.includes("rice")) return "images/regular-rice.jpg";
  if (name.includes("toor dal")) return "images/toor-dal.jpg";
  if (name.includes("red chilli") || name.includes("red chili") || name.includes("chilli powder") || name.includes("chili powder") || name.includes("mirchi powder")) return "images/red-chilli-powder.jpg";
  if (name.includes("masoor dal")) return "images/masoor-dal.jpg";
  if (name.includes("moong dal")) return "images/moong-dal.jpg";
  if (name.includes("mirchi") || name.includes("chilli")) return "images/red-mirchi.jpg";
  if (name.includes("turmeric")) return "images/turmeric.jpg";
  if (name.includes("ghee")) return "images/ghee.jpg";
  if (name.includes("sunflower oil")) return "images/sunflower-oil.jpg";
  if (name.includes("whole green gram") || name.includes("green gram") || name.includes("mung bean")) return "images/whole-green-gram.jpg";
  if (name.includes("groundnut oil")) return "images/groundnut-oil.jpg";
  if (name.includes("sesame oil")) return "images/sesame-oil.jpg";
  if (name.includes("jaggery")) return "images/jaggery.jpg";
  if (name.includes("sugar")) return "images/sugar.jpg";
  if (name.includes("wheat flour")) return "images/wheat-flour.jpg";
  if (name.includes("ragi flour")) return "images/ragi-flour.jpg";
  if (name.includes("spice")) return "images/spices.jpg";
  return product.image_url || "";
}

const CATEGORY_STYLES = [
  {keys: ["rice", "grain", "flour", "wheat"], icon: "wheat", bg: "#f4e6bd", ink: "#6b5317"},   // straw
  {keys: ["pulse", "dal", "gram"], icon: "bean", bg: "#f8d9a8", ink: "#7a4a12"},               // lentil
  {keys: ["spice", "mirchi", "chilli"], icon: "flame", bg: "#f6c7b4", ink: "#8a2f17"},         // red chilli
  {keys: ["oil", "ghee"], icon: "droplets", bg: "#e4e7a3", ink: "#56591a"},                    // olive gold
  {keys: ["sweet", "jaggery", "sugar"], icon: "candy", bg: "#e9cfae", ink: "#6a4320"},         // jaggery
  {keys: ["vegetable", "green"], icon: "carrot", bg: "#cfe8b4", ink: "#2f5f1a"},               // leaf
  {keys: ["fruit"], icon: "apple", bg: "#e9c8d6", ink: "#742a4c"},                             // plum
];
const DEFAULT_CATEGORY_STYLE = {icon: "sprout", bg: "#dcebd0", ink: "#33532b"};                // sage
function categoryStyle(category) {
  const name = String(category).toLowerCase();
  return CATEGORY_STYLES.find(style => style.keys.some(key => name.includes(key))) || DEFAULT_CATEGORY_STYLE;
}
function categoryVars(category) {
  const style = categoryStyle(category);
  return `--cat-bg:${style.bg};--cat-ink:${style.ink}`;
}
// Unit price for a quantity. Matches app/services/pricing.py, which applies the wholesale price from the minimum quantity.
function unitPriceFor(p, quantity) { return Number(quantity >= Number(p.min_wholesale_quantity) ? p.wholesale_price : p.retail_price); }
function singleUnitPrice(p) { return unitPriceFor(p, 1); }

// Order offer shown in the banner. The backend applies it (app/services/pricing.py); these only drive the hints.
const ORDER_OFFER = {threshold: 5000, percent: 10};
// Delivery charges. The backend charges them (DELIVERY_CHARGES in
// app/services/pricing.py); keep these values in step with it.
const DELIVERY = {charges: {"andhra pradesh": 50, "telangana": 150}, freeAbove: 2000};
const DELIVERY_NOTE = `Delivery ${money(DELIVERY.charges["andhra pradesh"])} in Andhra Pradesh, ${money(DELIVERY.charges.telangana)} in Telangana. Free above ${money(DELIVERY.freeAbove)}.`;
// Returns the charge for a state, or null when the state is not served.
function deliveryChargeFor(state, goodsTotal) {
  const aliases = {ap: "andhra pradesh", ts: "telangana", tg: "telangana", telengana: "telangana"};
  const key = String(state || "").replaceAll(".", "").toLowerCase().split(/\s+/).filter(Boolean).join(" ");
  const charge = DELIVERY.charges[aliases[key] || key];
  if (charge === undefined) return null;
  return Number(goodsTotal) > DELIVERY.freeAbove ? 0 : charge;
}

// Products sold in whole bags, by category. Prices stay per kg in the database:
// a 25 kg bag adds 25 kg to the cart at the price for 25 kg.
const BAG_SIZES = {Rice: [25, 50]};
const chosenBag = {}; // product id -> index into its bag sizes
function bagSizes(p) { return String(p.unit).toLowerCase() === "kg" ? BAG_SIZES[p.category] || null : null; }
// Quantity one tap on Add / + adds: one unit, or the chosen bag.
function buyQuantity(p) { const sizes = bagSizes(p); return sizes ? sizes[chosenBag[p.id] || 0] : 1; }
function priceHtml(p) {
  const sizes = bagSizes(p);
  if (!sizes) return `${money(singleUnitPrice(p))} <small>/ ${esc(p.unit)}</small>`;
  const kg = buyQuantity(p);
  return `${money(Math.round(unitPriceFor(p, kg) * kg * 100) / 100)} <small>/ ${kg} kg bag</small>`;
}
function sizePills(p) {
  const sizes = bagSizes(p);
  if (!sizes) return "";
  const chosen = chosenBag[p.id] || 0;
  return `<div class="size-pills" role="group" aria-label="Bag size for ${esc(p.name)}" data-sizes-for="${p.id}">${sizes.map((kg, i) =>
    `<button type="button" aria-pressed="${i === chosen}" onclick="chooseBag(${p.id},${i})">${kg} kg</button>`
  ).join("")}</div>`;
}
// Switches the bag size everywhere the product is shown, without re-rendering the cards.
function chooseBag(id, index) {
  const p = productById(id);
  if (!p) return;
  chosenBag[p.id] = index;
  document.querySelectorAll(`[data-price-for="${p.id}"]`).forEach(el => { el.innerHTML = priceHtml(p); });
  // Number the buttons inside each group: the product can be on the page more than once.
  document.querySelectorAll(`[data-sizes-for="${p.id}"]`).forEach(group =>
    group.querySelectorAll("button").forEach((b, i) => b.setAttribute("aria-pressed", String(i === index))));
  refreshCartControls();
}
function productById(id) { return catalog.find(p => Number(p.id) === Number(id)) || products.find(p => Number(p.id) === Number(id)); }
function cartLine(productId) { return (cart.items || []).find(x => Number(x.product_id) === Number(productId)); }
function cartSlot(p, variant) { return `<div class="cart-slot cart-slot-${variant}" data-product-id="${p.id}" data-variant="${variant}"></div>`; }
function cartSlotHtml(p, state, variant) {
  if (state === "out") return '<span class="out-of-stock">Out of stock</span>';
  if (state === "line") return `<div class="qty-stepper"><button aria-label="Decrease ${esc(p.name)} quantity" onclick="stepCartLine(${p.id},-1)">−</button><span class="qty-count" aria-live="polite"></span><button aria-label="Increase ${esc(p.name)} quantity" onclick="stepCartLine(${p.id},1)">+</button></div>`;
  return `<button class="add-btn" aria-label="Add ${esc(p.name)} to cart" onclick="addToCart(${p.id}, this)">${variant === "catalog" ? "Add to Cart" : "+ Add"}</button>`;
}
// Swaps a card's button only when its state changes, so cards never reload.
function refreshCartControls() {
  document.querySelectorAll(".cart-slot").forEach(slot => {
    const p = productById(slot.dataset.productId);
    if (!p) return;
    const line = cartLine(p.id);
    const state = line ? "line" : Number(p.stock_quantity) < buyQuantity(p) ? "out" : "add";
    if (slot.dataset.state !== state) {
      slot.innerHTML = cartSlotHtml(p, state, slot.dataset.variant);
      slot.dataset.state = state;
    }
    if (line) {
      const count = slot.querySelector(".qty-count");
      const text = bagSizes(p) ? `${line.quantity} kg` : String(line.quantity);
      if (count.textContent !== text) count.textContent = text;
    }
  });
}
// Category links come from the live catalog so every link leads to real products.
async function loadCatalog() {
  document.getElementById("home-featured").innerHTML = skeletonCards(4);
  try {
    catalog = await api("/api/products/?limit=100&active_only=true");
  } catch (error) {
    document.getElementById("home-featured").innerHTML = `<div class="col-span-full p-6 bg-red-50 text-red-700 rounded-xl">Could not load products: ${esc(error.message)}</div>`;
    return;
  }
  const categories = [...new Set(catalog.map(p => p.category).filter(Boolean))].sort();
  document.getElementById("category-filter-list").innerHTML = ["All", ...categories].map(c => {
    const active = c === selectedCategory;
    return `<li><button onclick="filterCategory(this.dataset.category)" data-category="${esc(c)}" class="cat-btn w-full text-left px-3 py-2 rounded-lg ${active ? "bg-brand-50 text-brand-700 font-semibold" : "hover:bg-stone-50 text-stone-600"}">${c === "All" ? "All Products" : esc(c)}</button></li>`;
  }).join("");
  document.querySelectorAll("[data-promo]").forEach(el => el.classList.toggle("hidden", !categories.includes(el.dataset.promo)));
  document.getElementById("home-tabs").innerHTML = ["All", ...categories].map(c =>
    `<button class="tab-pill" role="tab" data-tab="${esc(c)}" onclick="setHomeTab(this.dataset.tab)">${c === "All" ? "" : `<i style="--dot:${categoryStyle(c).bg}"></i>`}${esc(c)}</button>`
  ).join("");
  renderFeatured();
  if (window.lucide) lucide.createIcons();
}
function setHomeTab(category) { homeTab = category; renderFeatured(); }
let lastChipsHtml = "";
function renderHeroChips() {
  const picks = [];
  for (const p of catalog) {
    if (Number(p.stock_quantity) > 0 && getProductImage(p) && !picks.some(x => x.category === p.category)) picks.push(p);
    if (picks.length === 2) break;
  }
  const html = picks.map(p =>
    `<button class="hero-chip" data-category="${esc(p.category)}" onclick="filterCategory(this.dataset.category)"><img src="${esc(getProductImage(p))}" alt=""><span><b>${esc(p.name)}</b><span>From ${priceHtml(p).replace(/<\/?small>/g, "")}</span></span></button>`
  ).join("");
  if (html === lastChipsHtml) return;
  lastChipsHtml = html;
  const visual = document.getElementById("hero-visual");
  visual.querySelectorAll(".hero-chip").forEach(chip => chip.remove());
  visual.insertAdjacentHTML("beforeend", html);
}
let lastFeaturedHtml = "";
function renderFeatured() {
  const grid = document.getElementById("home-featured");
  if (!catalog.length) return;
  document.querySelectorAll("#home-tabs .tab-pill").forEach(tab => tab.setAttribute("aria-selected", String(tab.dataset.tab === homeTab)));
  const items = catalog.filter(p => homeTab === "All" || p.category === homeTab).slice(0, 8);
  const html = items.map((p, i) => {
    const image = getProductImage(p);
    return `<article class="feature-card fade-up" style="animation-delay:${i * 40}ms">
      <div class="feature-card-media" style="${categoryVars(p.category)}"><img src="${esc(image)}" alt="${esc(p.name)}" loading="lazy" class="${image ? "" : "hidden"}" onerror="this.classList.add('hidden')"></div>
      <h3>${esc(p.name)}</h3>
      ${sizePills(p)}
      <div class="feature-foot"><span class="feature-price" data-price-for="${p.id}">${priceHtml(p)}</span>${cartSlot(p, "featured")}</div>
    </article>`;
  }).join("");
  if (html !== lastFeaturedHtml) {
    grid.innerHTML = html;
    lastFeaturedHtml = html;
  }
  renderHeroChips();
  refreshCartControls();
}

let lastGridHtml = "";
let productRequest = 0;
async function renderProducts() {
  const grid = document.getElementById("product-grid");
  const request = ++productRequest;
  // Placeholders only when there is nothing to show; a refresh keeps the current cards on screen.
  if (!grid.querySelector("article")) { grid.innerHTML = skeletonCards(6); lastGridHtml = ""; }
  try {
    const query = document.getElementById("search-input")?.value.trim() || "";
    const params = new URLSearchParams({limit:"100", active_only:"true"});
    if (query) params.set("search", query);
    if (selectedCategory !== "All") params.set("category", selectedCategory);
    const results = await api(`/api/products/?${params.toString()}`);
    if (request !== productRequest) return; // A newer search has started.
    products = results;
    if (!products.length) { grid.innerHTML = '<div class="col-span-full py-12 text-center text-stone-500">No products found. Try another search or category.</div>'; lastGridHtml = ""; return; }
    const html = products.map((p, i) => {
      const image = getProductImage(p);
      return `<article class="product-card card-fx fade-up" style="animation-delay:${Math.min(i,11)*50}ms">
        <div class="product-card-media" style="${categoryVars(p.category)}">
          <img src="${esc(image)}" alt="${esc(p.name)}" class="${image ? "" : "hidden"}" onerror="this.classList.add('hidden')">
          <span class="product-badge">${esc(p.category)}</span>
        </div>
        <div class="flex-1 pt-3 px-1">
          <h3 class="text-base font-bold text-stone-800">${esc(p.name)}</h3>
          <p class="text-xs text-stone-500 mt-1">${esc(p.description || "Farm-sourced grocery essential.")}</p>
          ${bagSizes(p)
            ? `<p class="text-[11px] text-stone-500 mt-3 mb-1 font-semibold uppercase tracking-wide">Bag size</p>${sizePills(p)}`
            : `<div class="mt-2 flex flex-wrap gap-2 text-xs"><span class="bg-stone-100 px-2 py-1 rounded">${esc(p.unit)}</span><span class="bg-stone-100 px-2 py-1 rounded">${Number(p.stock_quantity)} in stock</span></div>
          ${Number(p.min_wholesale_quantity)>1 && Number(p.wholesale_price) < Number(p.retail_price) ? `<p class="text-xs text-stone-500 mt-2">${money(p.wholesale_price)} each when you buy ${p.min_wholesale_quantity} ${esc(p.unit)} or more</p>` : ""}`}
        </div>
        <div class="mt-3 px-1 pb-1 flex items-center justify-between gap-2">
          <div><p class="text-[11px] text-stone-500">Price</p><p class="feature-price text-lg" data-price-for="${p.id}">${priceHtml(p)}</p></div>
          ${cartSlot(p, "catalog")}
        </div></article>`;
    }).join("");
    if (html !== lastGridHtml) {
      grid.innerHTML = html;
      lastGridHtml = html;
    }
    refreshCartControls();
    renderFeatured();
  } catch (error) { if (request === productRequest) { grid.innerHTML = `<div class="col-span-full p-6 bg-red-50 text-red-700 rounded-xl">Could not load products: ${esc(error.message)}. Check that the FastAPI server and database are running.</div>`; lastGridHtml = ""; } }
}
async function addToCart(productId, btn) {
  if (!token || !currentUser) { window.pendingCartProduct = productId; openAccount(); notify("Please log in to add items to your cart."); return; }
  if (btn) { btn.disabled = true; btn.classList.add("is-busy"); }
  try {
    const p = productById(productId);
    cart = await api("/api/cart/items", {method:"POST", body:{product_id:productId, quantity:p ? buyQuantity(p) : 1}});
    if (btn) flyToCart(btn);
    updateCartBadge(); bumpCartBadge();
    showAddedPop(productId);
  } catch (error) {
    if (btn) { btn.disabled = false; btn.classList.remove("is-busy"); }
    notify(error.message);
  }
}
const cartUpdating = new Set();
async function stepCartLine(productId, change) {
  const line = cartLine(productId);
  if (!line || cartUpdating.has(productId)) return;
  cartUpdating.add(productId);
  const p = productById(productId);
  const quantity = Number(line.quantity) + change * (p ? buyQuantity(p) : 1);
  try {
    if (quantity < 1) {
      await api(`/api/cart/items/${line.id}`, {method:"DELETE"});
      cart = await api("/api/cart");
    } else {
      cart = await api(`/api/cart/items/${line.id}`, {method:"PATCH", body:{quantity}});
    }
    updateCartBadge();
  } catch (error) { notify(error.message); }
  finally { cartUpdating.delete(productId); }
}
function updateCartBadge() {
  // Count products, not units: 100 kg of rice is one item in the cart.
  document.getElementById("cart-badge").textContent = (cart.items || []).length;
  refreshCartControls();
}
async function loadCart() {
  const container = document.getElementById("cart-container");
  if (!token) { container.innerHTML = `<div class="text-center py-12 bg-white border rounded-xl"><p class="mb-4">Log in to view your saved cart.</p><button onclick="openAccount()" class="bg-brand-700 text-white px-5 py-2 rounded-lg">Login</button></div>`; cart={items:[],total:0}; updateCartBadge(); return; }
  try { cart = await api("/api/cart"); renderCart(); }
  catch(error) { container.innerHTML = `<p class="text-red-700">${esc(error.message)}</p>`; }
}
// Subtotal, offer discount and total rows shared by the cart and checkout.
function cartTotalsHtml(c) {
  const discount = Number(c.discount || 0);
  const subtotal = Number(c.subtotal ?? c.total ?? 0);
  const rows = discount > 0
    ? `<div class="flex justify-between text-sm text-stone-600"><span>Subtotal</span><span>${money(subtotal)}</span></div><div class="flex justify-between text-sm font-semibold text-brand-700"><span>Offer: ${ORDER_OFFER.percent}% off above ${money(ORDER_OFFER.threshold)}</span><span>−${money(discount)}</span></div>`
    : "";
  const short = ORDER_OFFER.threshold - subtotal;
  const note = discount > 0
    ? `<p class="offer-note">You saved ${money(discount)} with the ${ORDER_OFFER.percent}% offer.</p>`
    : short >= 0 && subtotal > 0 ? `<p class="offer-note">Add more than ${money(short)} to get ${ORDER_OFFER.percent}% off your order.</p>` : "";
  return { rows, note };
}
function renderCart() {
  const container = document.getElementById("cart-container");
  updateCartBadge();
  if (!cart.items?.length) { container.innerHTML = `<div class="text-center py-16 bg-white border border-stone-200 rounded-xl"><i data-lucide="shopping-cart" class="w-12 h-12 text-stone-300 mx-auto mb-3"></i><h3 class="text-lg font-bold">Your cart is empty</h3><p class="text-stone-400 text-sm mb-6">Explore the store and add products.</p><button onclick="navigate('products')" class="bg-brand-700 text-white px-6 py-2 rounded-lg">Browse Store</button></div>`; if(window.lucide)lucide.createIcons(); return; }
  container.innerHTML = `<div class="bg-white rounded-xl border border-stone-200 p-6 shadow-sm"><div class="divide-y">${cart.items.map(item=>`<div id="cart-row-${item.id}" class="cart-row py-4 flex flex-wrap gap-3 items-center justify-between"><div class="flex min-w-0 items-center gap-3"><img src="${esc(getProductImage({name:item.product_name, image_url:item.image_url}))}" alt="${esc(item.product_name)}" class="w-14 h-14 sm:w-16 sm:h-16 rounded-lg object-cover border border-stone-200 bg-stone-50 flex-shrink-0" onerror="this.classList.add('hidden')"><div class="min-w-0"><h4 class="font-bold text-sm">${esc(item.product_name)}</h4><p class="text-xs text-stone-500">${money(item.unit_price)} each · Item #${item.id}</p></div></div><div class="flex items-center gap-3"><div class="flex items-center border rounded-lg"><button onclick="changeQty(${item.id},${Number(item.quantity)-1})" class="px-3 py-1 hover:bg-stone-100">−</button><span class="px-2 text-sm">${item.quantity}</span><button onclick="changeQty(${item.id},${Number(item.quantity)+1})" class="px-3 py-1 hover:bg-stone-100">+</button></div><b class="w-24 text-right">${money(item.subtotal)}</b><button onclick="removeCartItem(${item.id})" class="text-red-600 text-sm">Remove</button></div></div>`).join("")}</div><div class="border-t mt-4 pt-4 space-y-1">${cartTotalsHtml(cart).rows}<div class="flex justify-between font-bold text-lg"><span>Total</span><span>${money(cart.total)}</span></div>${cartTotalsHtml(cart).note}<p class="text-xs text-stone-500">${DELIVERY_NOTE}</p></div><div class="mt-5 flex flex-wrap gap-3"><button onclick="clearCart()" class="border rounded-lg px-4 py-3 text-sm">Clear cart</button><button onclick="navigate('checkout')" class="flex-1 bg-brand-accent text-brand-800 font-bold py-3 rounded-lg">Proceed to checkout</button></div></div>`;
}
async function changeQty(itemId, quantity) {
  try { if (quantity < 1) await removeCartItem(itemId); else { cart=await api(`/api/cart/items/${itemId}`,{method:"PATCH",body:{quantity}}); renderCart(); flashRow(itemId); } }
  catch(error) { notify(error.message); }
}
async function removeCartItem(itemId) { try { const row = document.getElementById("cart-row-" + itemId); if (row) { row.classList.add("row-out"); await sleep(320); } await api(`/api/cart/items/${itemId}`,{method:"DELETE"}); await loadCart(); notify("Item removed."); } catch(error){notify(error.message);} }
async function clearCart() { try { await api("/api/cart",{method:"DELETE"}); await loadCart(); notify("Cart cleared."); } catch(error){notify(error.message);} }
