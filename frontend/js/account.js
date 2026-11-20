// Customer pages: dashboard, orders, tracking, payment history, addresses and receipts.
// Plain scripts loaded in order by index.html; they share one global scope.

async function loadCustomerDashboard() {
  const recent = document.getElementById("dashboard-recent-orders");
  if (!currentUser || currentUser.role === "admin" || !token) {
    recent.innerHTML = `<div class="py-8 text-center"><p class="text-sm text-stone-600 mb-3">Please log in with your customer account to view your dashboard.</p><button onclick="openAccount()" class="bg-brand-700 text-white rounded-lg px-4 py-2 text-sm font-semibold">Login</button></div>`;
    ["dashboard-total-orders", "dashboard-active-orders", "dashboard-total-spend", "dashboard-address-count"].forEach(id => { const el=document.getElementById(id); if(el) el.textContent="—"; });
    return;
  }
  document.getElementById("dashboard-customer-name").textContent = currentUser.name || "Customer";
  recent.innerHTML = '<p class="text-sm text-stone-500">Loading your orders…</p>';
  try {
    const orders = await api("/api/orders/");
    const safeOrders = Array.isArray(orders) ? orders : [];
    const active = safeOrders.filter(o => ["pending", "processing", "shipped"].includes(String(o.status || "").toLowerCase()));
    const totalSpend = safeOrders.filter(o => String(o.status || "").toLowerCase() !== "cancelled").reduce((sum, o) => sum + Number(o.total_amount || 0), 0);
    countTo(document.getElementById("dashboard-total-orders"), safeOrders.length);
    countTo(document.getElementById("dashboard-active-orders"), active.length);
    countTo(document.getElementById("dashboard-total-spend"), totalSpend, money);
    try {
      const savedAddresses = await api("/api/addresses/");
      document.getElementById("dashboard-address-count").textContent = Array.isArray(savedAddresses) ? savedAddresses.length : 0;
    } catch { document.getElementById("dashboard-address-count").textContent = "—"; }
    if (!safeOrders.length) {
      recent.innerHTML = `<div class="py-8 text-center"><div class="w-12 h-12 rounded-full bg-brand-50 text-brand-700 flex items-center justify-center mx-auto mb-3"><i data-lucide="package-open" class="w-6 h-6"></i></div><p class="font-semibold text-stone-700">No orders yet</p><p class="text-sm text-stone-500 mt-1 mb-4">Your first farm-fresh order is just a few clicks away.</p><button onclick="navigate('products')" class="bg-brand-700 text-white rounded-lg px-4 py-2 text-sm font-semibold">Browse products</button></div>`;
    } else {
      recent.innerHTML = safeOrders.slice(0, 4).map(o => {
        const status = String(o.status || "pending").toLowerCase();
        const date = o.created_at ? new Date(o.created_at).toLocaleDateString("en-IN", {day:"numeric", month:"short", year:"numeric"}) : "Date unavailable";
        return `<button onclick="navigate('orders')" class="w-full flex flex-wrap items-center justify-between gap-3 border border-stone-200 rounded-xl p-4 text-left hover:border-brand-600 transition"><div class="flex items-center gap-3"><span class="w-10 h-10 rounded-lg bg-brand-50 text-brand-700 flex items-center justify-center"><i data-lucide="package" class="w-5 h-5"></i></span><div><p class="font-semibold text-sm">Order #${esc(o.id)}</p><p class="text-xs text-stone-500 mt-1">${esc(date)} · ${Array.isArray(o.items) ? o.items.length : 0} item type(s)</p></div></div><div class="text-right"><p class="font-bold text-brand-800">${money(o.total_amount)}</p><span class="inline-block mt-1">${adminBadge(status)}</span></div></button>`;
      }).join("");
    }
    if (window.lucide) lucide.createIcons();
  } catch (error) {
    recent.innerHTML = `<p class="text-sm text-red-700">Could not load dashboard data: ${esc(error.message)}</p><button onclick="loadCustomerDashboard()" class="mt-3 text-sm text-brand-700 underline">Try again</button>`;
  }
}

function shipmentStatusSteps(status) {
  const steps = ["pending", "packed", "shipped", "out_for_delivery", "delivered"];
  const normalized = String(status || "pending").toLowerCase().replaceAll(" ", "_").replaceAll("-", "_");
  return {steps, normalized, index: steps.indexOf(normalized)};
}
function renderShipmentTracking(order, delivery) {
  const status = String(delivery?.status || order.delivery_status || order.status || "pending").toLowerCase().replaceAll(" ", "_").replaceAll("-", "_");
  const {steps, normalized, index} = shipmentStatusSteps(status);
  const cancelled = String(order.status || "").toLowerCase() === "cancelled";
  const delivered = normalized === "delivered" || String(order.status || "").toLowerCase() === "delivered";
  const labels = {pending:"Order received", packed:"Packed", shipped:"Shipped", out_for_delivery:"Out for delivery", delivered:"Delivered"};
  const current = cancelled ? "cancelled" : normalized;
  const currentLabel = labels[current] || current.replaceAll("_", " ").replace(/^./, c => c.toUpperCase());
  const eta = delivery?.estimated_delivery_date || order.estimated_delivery_date || order.estimated_delivery;
  const etaText = eta ? new Date(String(eta).slice(0,10) + "T12:00:00").toLocaleDateString("en-IN", {day:"numeric", month:"long", year:"numeric"}) : "Not updated yet";
  const tracking = delivery?.tracking_number || order.tracking_number || "Not assigned yet";
  const partner = delivery?.delivery_partner || order.delivery_partner || "Not assigned yet";
  const progress = cancelled ? -1 : delivered ? 4 : index;
  return `<section class="mt-4 border border-stone-200 rounded-xl p-4 sm:p-5 bg-stone-50">
    <div class="flex flex-wrap justify-between items-start gap-3"><div><h4 class="font-bold text-brand-800 flex items-center gap-2"><i data-lucide="truck" class="w-5 h-5"></i> Order tracking</h4><p class="text-xs text-stone-500 mt-1">Live shipment information provided by the seller</p></div><span class="inline-flex rounded-full px-3 py-1 text-xs font-semibold ${cancelled?'bg-red-100 text-red-700':delivered?'bg-emerald-100 text-emerald-700':'bg-blue-100 text-blue-700'}">${esc(cancelled?'Cancelled':currentLabel)}</span></div>
    <div class="grid sm:grid-cols-3 gap-3 mt-4"><div class="rounded-lg bg-white border border-stone-200 p-3"><p class="text-xs text-stone-500 mb-1">Estimated delivery</p><p class="font-semibold text-sm">${esc(delivered?'Delivered':etaText)}</p></div><div class="rounded-lg bg-white border border-stone-200 p-3"><p class="text-xs text-stone-500 mb-1">Tracking number</p><p class="font-semibold text-sm break-all">${esc(tracking)}</p></div><div class="rounded-lg bg-white border border-stone-200 p-3"><p class="text-xs text-stone-500 mb-1">Delivery partner</p><p class="font-semibold text-sm">${esc(partner)}</p></div></div>
    ${cancelled ? '<p class="mt-4 text-sm text-red-700">This order has been cancelled.</p>' : `<div class="mt-5"><p class="text-xs font-semibold text-stone-500 mb-4">SHIPMENT PROGRESS</p><div class="flex items-start w-full">${steps.map((step,i)=>{const complete=progress>=i;const active=progress===i;return `<div class="relative flex-1 min-w-0 flex flex-col items-center text-center"><div class="flex items-center w-full h-9"><span class="absolute left-0 right-0 top-4 h-1 ${i===0?'hidden':''} ${progress>=i?'bg-brand-700':'bg-stone-200'}" style="z-index:0"></span><span class="relative z-10 mx-auto flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold ${complete?'bg-brand-700 text-white':active?'bg-brand-700 text-white':'bg-white border border-stone-300 text-stone-400'}">${complete?'✓':i+1}</span></div><span class="mt-2 px-1 text-xs leading-4 ${active?'font-bold text-brand-800':complete?'text-stone-700':'text-stone-400'}">${labels[step]}</span></div>`}).join('')}</div></div>`}
    <p class="text-xs text-stone-500 mt-4">${delivered?'Your order has been delivered.':eta?'Expected to arrive by '+esc(etaText)+'.':'The estimated delivery date will appear here once the shipment is scheduled.'}</p>
  </section>`;
}
function ordersLoginPrompt() {
  return `<div class="bg-white border rounded-xl p-8 text-center">Please log in to view your orders. <button onclick="openAccount()" class="text-brand-700 underline">Login</button></div>`;
}
function ordersEmptyPrompt(message) {
  return `<div class="bg-white border rounded-xl p-8 text-center text-stone-500">${esc(message)} <button onclick="navigate('products')" class="text-brand-700 underline">Browse products</button></div>`;
}
function orderHeaderHtml(o) {
  return `<div class="flex flex-wrap justify-between gap-3"><div><h3 class="font-bold text-lg">Order #${esc(o.id)}</h3><p class="text-xs text-stone-500">${o.created_at ? esc(new Date(o.created_at).toLocaleString()) : "Date unavailable"}</p></div><div class="text-left sm:text-right"><div class="flex flex-wrap sm:justify-end gap-2"><span class="text-xs text-stone-500 self-center">Order</span>${adminBadge(String(o.status || "pending").toLowerCase())}<span class="text-xs text-stone-500 self-center ml-1">Payment</span>${adminBadge(String(o.payment_status || "pending").toLowerCase())}</div></div></div>`;
}
// Order History: order details only (items, address, total, payment, cancel).
async function loadOrders() {
  const el=document.getElementById("orders-container");
  if(!token){el.innerHTML=ordersLoginPrompt();return;}
  el.innerHTML='<p class="text-stone-500">Loading your orders…</p>';
  try {
    const orders=await api("/api/orders/");
    if(!orders.length){el.innerHTML=ordersEmptyPrompt("No orders yet.");return;}
    el.innerHTML=orders.map((o,idx)=>{
      const items=Array.isArray(o.items) ? o.items : [];
      const canCancel=String(o.status || "").toLowerCase()==="pending";
      const canPay=paymentConfig.online_enabled && o.payment_method==="online" && o.status!=="cancelled" && ["pending","failed"].includes(o.payment_status);
      return `<article class="bg-white border border-stone-200 rounded-xl p-5 fade-up" style="animation-delay:${Math.min(idx,8)*70}ms">${orderHeaderHtml(o)}<div class="border-t mt-4 pt-3 space-y-3 text-sm">${items.map(i=>`<div class="flex items-center justify-between gap-3"><div class="flex items-center gap-3 min-w-0"><img src="${esc(getProductImage({name:i.product_name, image_url:i.image_url}))}" alt="${esc(i.product_name)}" class="w-12 h-12 sm:w-14 sm:h-14 rounded-lg object-cover border border-stone-200 bg-stone-50 flex-shrink-0" onerror="this.classList.add('hidden')"><span class="min-w-0">${esc(i.product_name)} × ${esc(i.quantity)} ${esc(i.unit)}</span></div><span class="text-stone-600 flex-shrink-0">${money(i.subtotal)}</span></div>`).join("")}</div><div class="border-t mt-4 pt-3 flex flex-wrap items-start justify-between gap-3"><div class="text-xs text-stone-500">Deliver to: ${esc(o.recipient_name)}, ${esc(o.address_line1)}, ${esc(o.city)}, ${esc(o.state)} ${esc(o.postal_code)} · ${esc(String(o.payment_method || "").replaceAll("_"," "))}</div><div class="text-right">${Number(o.discount_amount) > 0 ? `<p class="text-xs text-brand-700 font-semibold">Offer −${money(o.discount_amount)}</p>` : ""}<p class="text-xs text-stone-500">Delivery ${Number(o.delivery_charge) > 0 ? money(o.delivery_charge) : "free"}</p><p class="text-xs text-stone-500">Order total</p><p class="font-bold text-brand-800">${money(o.total_amount)}</p></div></div><div class="mt-4 flex flex-wrap gap-2">${canPay?`<button onclick="payOnlineFromOrders(${Number(o.id)}, this)" class="text-sm bg-brand-700 hover:bg-brand-800 text-white rounded-lg px-3 py-2 font-semibold">Pay now</button>`:""}${canCancel?`<button onclick="cancelOrder(${Number(o.id)})" class="text-sm border border-red-300 text-red-700 rounded-lg px-3 py-2 hover:bg-red-50">Cancel order</button>`:""}<button onclick="navigate('tracking')" class="text-sm border border-stone-300 text-stone-700 rounded-lg px-3 py-2 hover:bg-stone-50">Track shipment</button>${o.status!=="cancelled"?`<button onclick="downloadReceipt(${Number(o.id)}, this)" class="text-sm border border-stone-300 text-stone-700 rounded-lg px-3 py-2 hover:bg-stone-50">Download receipt</button>`:""}</div></article>`;
    }).join("");
    if (window.lucide) lucide.createIcons();
  } catch(error){el.innerHTML=`<p class="text-red-700">${esc(error.message)}</p>`;}
}
// Order Tracking: shipment progress only (delivery partner, tracking number, ETA, progress).
// While the page is open and any order is still in transit it refreshes itself every 30 seconds.
var trackingTimer = null;
var trackingSignature = "";
var TRACKING_REFRESH_MS = 30000;
function stopTrackingRefresh() {
  if (trackingTimer) { clearInterval(trackingTimer); trackingTimer = null; }
}
function startTrackingRefresh() {
  if (trackingTimer) return;
  trackingTimer = setInterval(() => {
    const view = document.getElementById("view-tracking");
    if (!view || view.classList.contains("hidden")) { stopTrackingRefresh(); return; }
    if (document.hidden) return;
    loadTracking({silent: true});
  }, TRACKING_REFRESH_MS);
}
function orderIsInTransit(o) {
  const orderStatus = String(o.status || "").toLowerCase();
  const deliveryStatus = String(o.delivery?.status || "").toLowerCase();
  if (orderStatus === "cancelled" || orderStatus === "delivered") return false;
  return !["delivered", "returned"].includes(deliveryStatus);
}
document.addEventListener("visibilitychange", () => {
  const view = document.getElementById("view-tracking");
  if (!document.hidden && view && !view.classList.contains("hidden") && token) loadTracking({silent: true});
});
async function loadTracking(options = {}) {
  const silent = options && options.silent === true;
  const el=document.getElementById("tracking-container");
  if(!token){stopTrackingRefresh();el.innerHTML=ordersLoginPrompt();return;}
  if(!silent) el.innerHTML='<p class="text-stone-500">Loading your shipments…</p>';
  try {
    const orders=await api("/api/orders/");
    if(!orders.length){stopTrackingRefresh();el.innerHTML=ordersEmptyPrompt("No orders to track yet.");return;}
    // A background refresh with unchanged data leaves the screen (and its animations) alone.
    const signature=JSON.stringify(orders);
    if (silent && signature===trackingSignature) {
      const unchanged=document.getElementById("tracking-updated");
      if (unchanged) unchanged.textContent=`Last updated ${new Date().toLocaleTimeString()}`;
      if (orders.some(orderIsInTransit)) startTrackingRefresh(); else stopTrackingRefresh();
      return;
    }
    trackingSignature=signature;
    const animate=!silent;   // entrance animations only for a user-initiated load
    el.classList.toggle("no-anim", !animate);
    el.innerHTML=orders.map((o,idx)=>{
      const items=Array.isArray(o.items) ? o.items : [];
      const summary=items.map(i=>`${esc(i.product_name)} × ${esc(i.quantity)} ${esc(i.unit)}`).join(", ");
      return `<article class="bg-white border border-stone-200 rounded-xl p-5${animate ? " fade-up" : ""}"${animate ? ` style="animation-delay:${Math.min(idx,8)*70}ms"` : ""}><div class="flex flex-wrap justify-between gap-3"><div><h3 class="font-bold text-lg">Order #${esc(o.id)}</h3><p class="text-xs text-stone-500">${o.created_at ? esc(new Date(o.created_at).toLocaleString()) : "Date unavailable"}</p></div><button onclick="navigate('orders')" class="text-sm text-brand-700 underline self-start">View order details</button></div><p class="text-sm text-stone-600 mt-3">${summary || "No items"}</p>${renderShipmentTracking(o,o.delivery || null)}</article>`;
    }).join("");
    if (window.lucide) lucide.createIcons();
    const updated=document.getElementById("tracking-updated");
    if (updated) updated.textContent=`Last updated ${new Date().toLocaleTimeString()}`;
    if (orders.some(orderIsInTransit)) startTrackingRefresh(); else stopTrackingRefresh();
  } catch(error){
    // A failed background refresh keeps the current content on screen.
    if(!silent) el.innerHTML=`<p class="text-red-700">${esc(error.message)}</p>`;
  }
}
function loginPromptHtml(what) {
  return `<div class="bg-white border rounded-xl p-8 text-center">Please log in to view ${esc(what)}. <button onclick="openAccount()" class="text-brand-700 underline">Login</button></div>`;
}

// ---------- Payment History ----------
async function loadPaymentHistoryView() {
  const el=document.getElementById("payments-container");
  if(!token){el.innerHTML=loginPromptHtml("your payment history");return;}
  el.innerHTML='<p class="text-stone-500">Loading your payments…</p>';
  try {
    const [payments, orders]=await Promise.all([api("/api/payments/history"), api("/api/orders/")]);
    const paidOrderIds=new Set(payments.map(p=>Number(p.order_id)));
    // Cash-on-delivery orders have no payment transaction, so show the payment status stored on the order.
    const orderRows=orders.filter(o=>!paidOrderIds.has(Number(o.id))).map(o=>({
      key:`order-${o.id}`, payment_id:null, order_id:o.id,
      method:o.payment_method, amount:o.total_amount,
      status:String(o.payment_status||"pending").toLowerCase(),
      reference:null, failure_reason:null, created_at:o.created_at
    }));
    const paymentRows=payments.map(p=>({
      key:`payment-${p.id}`, payment_id:p.id, order_id:p.order_id,
      method:p.payment_method, amount:p.amount,
      status:String(p.status||"pending").toLowerCase(),
      reference:p.transaction_reference, failure_reason:p.failure_reason, created_at:p.created_at
    }));
    const rows=[...paymentRows,...orderRows].sort((a,b)=>new Date(b.created_at)-new Date(a.created_at));
    if(!rows.length){el.innerHTML='<div class="bg-white border rounded-xl p-8 text-center text-stone-500">No payments yet. Your payments will appear here after you place an order.</div>';return;}
    const totalPaid=rows.filter(r=>r.status==="paid").reduce((sum,r)=>sum+Number(r.amount||0),0);
    const pending=rows.filter(r=>r.status==="pending").length;
    el.innerHTML=`<div class="grid sm:grid-cols-2 gap-4 fade-up"><div class="bg-white border border-stone-200 rounded-xl p-5"><p class="text-xs text-stone-500">Total paid</p><p class="text-2xl font-bold text-brand-800 mt-1">${money(totalPaid)}</p></div><div class="bg-white border border-stone-200 rounded-xl p-5"><p class="text-xs text-stone-500">Pending payments</p><p class="text-2xl font-bold text-brand-800 mt-1">${pending}</p></div></div>
      <div class="bg-white border border-stone-200 rounded-xl overflow-x-auto fade-up" style="animation-delay:120ms"><table class="min-w-full text-sm"><thead><tr class="text-left border-b text-xs uppercase tracking-wide text-stone-500"><th class="py-3 px-4">Date</th><th class="py-3 px-4">Order</th><th class="py-3 px-4">Method</th><th class="py-3 px-4">Amount</th><th class="py-3 px-4">Status</th><th class="py-3 px-4">Reference</th></tr></thead><tbody>${rows.map(r=>`<tr class="border-b last:border-0 align-top"><td class="py-3 px-4 whitespace-nowrap">${r.created_at?esc(new Date(r.created_at).toLocaleString()):"—"}</td><td class="py-3 px-4"><button onclick="navigate('orders')" class="text-brand-700 underline">#${esc(r.order_id)}</button></td><td class="py-3 px-4">${esc(String(r.method||"").replaceAll("_"," "))}</td><td class="py-3 px-4 font-semibold">${money(r.amount)}</td><td class="py-3 px-4">${adminBadge(r.status)}${r.failure_reason?`<p class="text-xs text-red-700 mt-1">${esc(r.failure_reason)}</p>`:""}</td><td class="py-3 px-4 break-all text-stone-600">${r.reference?esc(r.reference):"—"}</td></tr>`).join("")}</tbody></table></div>
      <p class="text-xs text-stone-500">Cash-on-delivery orders show the payment status recorded on the order.</p>`;
  } catch(error){el.innerHTML=`<p class="text-red-700">${esc(error.message)}</p>`;}
}

// ---------- My Addresses ----------
let myAddresses=[];
let editingAddressId=null;
async function loadMyAddresses() {
  const el=document.getElementById("my-address-list");
  resetMyAddressForm();
  if(!token){el.innerHTML=loginPromptHtml("your saved addresses");return;}
  el.innerHTML='<p class="text-stone-500">Loading your addresses…</p>';
  try { myAddresses=await api("/api/addresses/"); renderMyAddresses(); }
  catch(error){el.innerHTML=`<p class="text-red-700">${esc(error.message)}</p>`;}
}
function renderMyAddresses() {
  const el=document.getElementById("my-address-list");
  if(!myAddresses.length){el.innerHTML='<div class="bg-white border rounded-xl p-6 text-center text-stone-500 text-sm">No saved addresses yet. Add your first address using the form.</div>';return;}
  el.innerHTML=myAddresses.map((a,idx)=>`<article class="bg-white border ${a.is_default?'border-brand-600':'border-stone-200'} rounded-xl p-4 fade-up" style="animation-delay:${Math.min(idx,8)*70}ms"><div class="flex items-start justify-between gap-3"><div class="text-sm min-w-0"><p class="font-semibold">${esc(a.recipient_name)} ${a.is_default?'<span class="ml-1 text-xs font-semibold bg-brand-50 text-brand-700 rounded-full px-2 py-0.5">Default</span>':''}</p><p class="text-stone-600">${esc(a.phone)}</p><p class="mt-1">${esc(a.address_line1)}${a.address_line2?', '+esc(a.address_line2):''}</p>${a.landmark?`<p class="text-stone-500">Landmark: ${esc(a.landmark)}</p>`:''}<p>${esc(a.city)}, ${esc(a.state)} ${esc(a.postal_code)}, ${esc(a.country)}</p></div></div><div class="mt-3 flex flex-wrap gap-2"><button onclick="editMyAddress(${Number(a.id)})" class="text-sm border border-stone-300 rounded-lg px-3 py-1.5 hover:bg-stone-50">Edit</button>${a.is_default?'':`<button onclick="makeDefaultAddress(${Number(a.id)})" class="text-sm border border-stone-300 rounded-lg px-3 py-1.5 hover:bg-stone-50">Set as default</button>`}<button onclick="deleteMyAddress(${Number(a.id)})" class="text-sm border border-red-300 text-red-700 rounded-lg px-3 py-1.5 hover:bg-red-50">Delete</button></div></article>`).join("");
}
function resetMyAddressForm() {
  const form=document.getElementById("my-address-form");
  if(!form) return;
  editingAddressId=null;
  form.reset();
  form.elements.country.value="India";
  form.elements.is_default.disabled=false;
  document.getElementById("my-address-form-title").textContent="Add a new address";
  document.getElementById("my-address-submit").textContent="Save address";
  document.getElementById("my-address-cancel").classList.add("hidden");
}
function editMyAddress(id) {
  const a=myAddresses.find(x=>Number(x.id)===Number(id));
  if(!a) return;
  const form=document.getElementById("my-address-form");
  editingAddressId=a.id;
  for (const name of ["recipient_name","phone","address_line1","address_line2","landmark","city","state","postal_code","country"]) form.elements[name].value=a[name]||"";
  form.elements.is_default.checked=!!a.is_default;
  form.elements.is_default.disabled=!!a.is_default; // a default address stays default until another one is chosen
  document.getElementById("my-address-form-title").textContent=`Edit address #${a.id}`;
  document.getElementById("my-address-submit").textContent="Update address";
  document.getElementById("my-address-cancel").classList.remove("hidden");
  form.scrollIntoView({behavior:"smooth", block:"center"});
}
async function saveMyAddress(event) {
  event.preventDefault();
  const form=event.currentTarget;
  const f=new FormData(form);
  const payload={recipient_name:f.get("recipient_name").trim(),phone:f.get("phone").trim(),address_line1:f.get("address_line1").trim(),address_line2:(f.get("address_line2")||"").trim()||null,landmark:(f.get("landmark")||"").trim()||null,city:f.get("city").trim(),state:f.get("state").trim(),postal_code:f.get("postal_code").trim(),country:f.get("country").trim()};
  const button=document.getElementById("my-address-submit");
  button.disabled=true;
  try {
    if(editingAddressId){
      if(form.elements.is_default.checked && !form.elements.is_default.disabled) payload.is_default=true;
      await api(`/api/addresses/${editingAddressId}`,{method:"PUT",body:payload});
      notify("Address updated.");
    } else {
      payload.is_default=f.get("is_default")==="on";
      await api("/api/addresses/",{method:"POST",body:payload});
      notify("Address saved.");
    }
    await loadMyAddresses();
  } catch(error){ notify(error.message); }
  finally { button.disabled=false; }
}
async function makeDefaultAddress(id) {
  try { await api(`/api/addresses/${id}`,{method:"PUT",body:{is_default:true}}); notify("Default address updated."); await loadMyAddresses(); }
  catch(error){ notify(error.message); }
}
async function deleteMyAddress(id) {
  if(!confirm("Delete this address?")) return;
  try { await api(`/api/addresses/${id}`,{method:"DELETE"}); notify("Address deleted."); await loadMyAddresses(); }
  catch(error){ notify(error.message); }
}

// The receipt needs the login token, so fetch it and save it from a blob URL.
async function downloadReceipt(id, button) {
  button.disabled = true;
  try {
    const response = await fetch(`${API_BASE}/api/orders/${id}/receipt`, {headers: {Authorization: `Bearer ${token}`}});
    if (!response.ok) {
      const data = await response.json().catch(() => null);
      throw new Error(data?.detail || `Could not download the receipt (${response.status})`);
    }
    const url = URL.createObjectURL(await response.blob());
    const link = Object.assign(document.createElement("a"), {href: url, download: `myfarmgrow-receipt-${id}.pdf`});
    document.body.appendChild(link); link.click(); link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  } catch (error) { notify(error.message); }
  finally { button.disabled = false; }
}
async function cancelOrder(id) { if(!confirm(`Cancel order #${id}?`))return; try{await api(`/api/orders/${id}/cancel`,{method:"POST"});notify("Order cancelled and eligible stock restored.");loadOrders();}catch(error){notify(error.message);} }
async function reorderOrder(orderId) {
  if (!token || !currentUser) {
    notify("Please log in to reorder items.");
    openAccount();
    return;
  }

  try {
    const orders = await api("/api/orders/");
    const order = orders.find(item => Number(item.id) === Number(orderId));
    if (!order) {
      notify("Could not find that order. Refresh your order history and try again.");
      return;
    }

    const items = Array.isArray(order.items) ? order.items : [];
    if (!items.length) {
      notify("This order has no items available to reorder.");
      return;
    }

    // Resolve product IDs from the order item first, then from already-loaded products by name.
    let productCatalog = Array.isArray(products) ? products : [];
    if (!productCatalog.length) {
      try {
        const loaded = await api("/api/products/");
        productCatalog = Array.isArray(loaded) ? loaded : (loaded?.items || loaded?.products || []);
        products = productCatalog;
      } catch (_) {
        // The order item's product_id can still be used without loading the catalog.
      }
    }

    const resolvedItems = items.map(item => {
      const name = item.product_name || item.name || "";
      const matchedProduct = productCatalog.find(product =>
        String(product.name || product.product_name || "").trim().toLowerCase() === String(name).trim().toLowerCase()
      );
      return {
        productId: Number(item.product_id ?? item.product?.id ?? matchedProduct?.id),
        quantity: Math.max(1, Number(item.quantity) || 1),
        name
      };
    });

    const unresolved = resolvedItems.filter(item => !Number.isFinite(item.productId) || item.productId <= 0);
    if (unresolved.length) {
      notify("Some order items do not include product IDs, so they could not be added. Please add those products from the catalog.");
      return;
    }

    let addedCount = 0;
    for (const item of resolvedItems) {
      await api("/api/cart/items", {
        method: "POST",
        body: { product_id: item.productId, quantity: item.quantity }
      });
      addedCount++;
    }

    cart = await api("/api/cart");
    updateCartBadge();
    notify(`Re-order added ${addedCount} item${addedCount === 1 ? "" : "s"} to your cart.`);
    navigate("cart");
  } catch (error) {
    notify(`Could not complete re-order: ${error.message}`);
    try { cart = await api("/api/cart"); updateCartBadge(); } catch (_) {}
  }
}
