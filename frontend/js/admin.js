// Admin screens: orders, deliveries, inventory, products, payments and customers.
// Plain scripts loaded in order by index.html; they share one global scope.

function adminStatusOptions(current) {
  const options = {
    pending: ["processing", "cancelled"],
    processing: ["shipped", "cancelled"],
    shipped: ["delivered"],
    delivered: [],
    cancelled: []
  };
  return options[current] || [];
}

function adminBadge(status) {
  const colors = {
    pending: "bg-amber-100 text-amber-800",
    processing: "bg-blue-100 text-blue-800",
    shipped: "bg-violet-100 text-violet-800",
    delivered: "bg-green-100 text-green-800",
    cancelled: "bg-red-100 text-red-800",
    paid: "bg-green-100 text-green-800",
    failed: "bg-red-100 text-red-800",
    refunded: "bg-slate-100 text-slate-800",
    refund_pending: "bg-orange-100 text-orange-800",
    partially_refunded: "bg-orange-100 text-orange-800"
  };
  return `<span class="inline-block rounded-full px-2 py-1 text-xs font-semibold ${colors[status] || "bg-stone-100 text-stone-700"}">${esc(String(status || "unknown").replaceAll("_"," "))}</span>`;
}

async function loadAdminOrders() {
  const container = document.getElementById("admin-orders-container");
  if (!currentUser || currentUser.role !== "admin") {
    container.innerHTML = '<div class="bg-red-50 text-red-700 rounded-xl p-5">Administrator access is required.</div>';
    return;
  }
  container.innerHTML = '<p class="text-stone-500">Loading orders...</p>';
  try {
    // This endpoint is added to app/api/routes/admin.py.
    const results = await Promise.all([
      api("/api/admin/orders"),
      api("/api/admin/deliveries").catch(() => [])
    ]);
    adminOrders = Array.isArray(results[0]) ? results[0] : []; _lastMaxOrder = Math.max(0, ...adminOrders.map(o => o.id));
    adminDeliveries = Array.isArray(results[1]) ? results[1] : [];
    renderAdminOrders();
  } catch (error) {
    container.innerHTML = `<div class="bg-red-50 text-red-700 rounded-xl p-5"><b>Could not load orders.</b><p class="mt-1">${esc(error.message)}</p><p class="text-sm mt-2">Confirm the updated admin.py is installed and the server has restarted.</p></div>`;
  }
}

// Inline shipment controls inside each order card make fulfilment manageable from one screen.
function renderOrderShipmentPanel(order) {
  const delivery = (adminDeliveries || []).find(d => Number(d.order_id) === Number(order.id));
  const deliveryId = delivery ? Number(delivery.id) : 0;
  const currentStatus = String(delivery?.status || "pending").toLowerCase();
  const nextStatuses = DELIVERY_TRANSITIONS[currentStatus] || [];
  const statusOptions = nextStatuses.map(s =>
    `<option value="${s}">${s.replaceAll("_", " ")}</option>`
  ).join("");
  const estimatedDate = delivery?.estimated_delivery_date ? String(delivery.estimated_delivery_date).slice(0, 10) : "";
  const tracking = delivery?.tracking_number || `MFG-ORD-${Number(order.id)}`;
  const isCancelled = String(order.status || "").toLowerCase() === "cancelled";
  return `
    <div class="border-t mt-4 pt-4">
      <div class="flex flex-wrap items-center justify-between gap-2 mb-3">
        <div><p class="text-xs font-semibold text-stone-500 mb-1">SHIPMENT & TRACKING</p>
          <p class="text-sm text-stone-500">${delivery ? `Delivery #${deliveryId} · ` : "No shipment assigned · "}${delivery ? "Update tracking and delivery progress here." : "Create a shipment directly from this order."}</p>
        </div>
        ${delivery ? deliveryStatusBadge(currentStatus) : '<span class="inline-flex rounded-full px-2.5 py-1 text-xs font-semibold bg-stone-100 text-stone-600">Not assigned</span>'}
      </div>
      ${isCancelled ? '<p class="text-sm text-red-700 bg-red-50 rounded-lg p-3">This order is cancelled. Shipment details cannot be created from this order.</p>' : `
      <form class="grid sm:grid-cols-2 xl:grid-cols-4 gap-3" onsubmit="saveOrderShipment(event, ${Number(order.id)}, ${deliveryId})">
        <div><label class="block text-xs font-semibold text-stone-600 mb-1" for="order-shipment-tracking-${Number(order.id)}">Tracking number</label>
          <input id="order-shipment-tracking-${Number(order.id)}" maxlength="100" value="${esc(tracking)}" class="w-full border rounded-lg p-2.5 text-sm" placeholder="Auto-generated from order ID"></div>
        <div><label class="block text-xs font-semibold text-stone-600 mb-1" for="order-shipment-partner-${Number(order.id)}">Delivery partner</label>
          <input id="order-shipment-partner-${Number(order.id)}" maxlength="150" value="${esc(delivery?.delivery_partner || "")}" class="w-full border rounded-lg p-2.5 text-sm" placeholder="e.g. Delivery partner"></div>
        <div><label class="block text-xs font-semibold text-stone-600 mb-1" for="order-shipment-date-${Number(order.id)}">Estimated delivery</label>
          <input id="order-shipment-date-${Number(order.id)}" type="date" value="${esc(estimatedDate)}" class="w-full border rounded-lg p-2.5 text-sm"></div>
        <div><label class="block text-xs font-semibold text-stone-600 mb-1" for="order-shipment-status-${Number(order.id)}">Delivery progress</label>
          <select id="order-shipment-status-${Number(order.id)}" class="w-full border rounded-lg p-2.5 text-sm">
            <option value="">Keep current (${esc(String(currentStatus).replaceAll("_", " "))})</option>
            ${statusOptions}
            ${!delivery ? '<option value="pending">pending</option>' : ''}
          </select></div>
        <div class="sm:col-span-2 xl:col-span-4 flex flex-wrap items-center justify-between gap-3">
          <p class="text-xs text-stone-500">Shipment progress is separate from order and payment status.</p>
          <button type="submit" class="inline-flex items-center gap-2 bg-brand-700 hover:bg-brand-800 text-white rounded-lg px-4 py-2.5 text-sm font-semibold">
            <i data-lucide="truck" class="w-4 h-4"></i> ${delivery ? "Save shipment update" : "Create shipment"}
          </button>
        </div>
      </form>`}
    </div>`;
}

async function saveOrderShipment(event, orderId, deliveryId) {
  event.preventDefault();
  if (!currentUser || currentUser.role !== "admin") {
    notify("Administrator access is required.");
    return;
  }
  const tracking = document.getElementById(`order-shipment-tracking-${orderId}`).value.trim();
  const partner = document.getElementById(`order-shipment-partner-${orderId}`).value.trim();
  const estimatedDate = document.getElementById(`order-shipment-date-${orderId}`).value;
  const status = document.getElementById(`order-shipment-status-${orderId}`).value;
  const payload = {
    order_id: Number(orderId),
    tracking_number: tracking || null,
    delivery_partner: partner || null,
    estimated_delivery_date: estimatedDate || null
  };
  if (status) payload.status = status;
  const button = event.currentTarget.querySelector('button[type="submit"]');
  if (button) { button.disabled = true; button.textContent = deliveryId ? "Saving…" : "Creating…"; }
  try {
    if (deliveryId) {
      delete payload.order_id;
      await api(`/api/admin/deliveries/${deliveryId}`, {method: "PATCH", body: payload});
      notify(`Shipment for order #${orderId} updated.`);
    } else {
      const created = await api("/api/admin/deliveries", {method: "POST", body: payload});
      // The create endpoint always starts at "pending"; apply the chosen progress afterwards.
      if (status && status !== "pending" && created && created.id) {
        await api(`/api/admin/deliveries/${created.id}`, {method: "PATCH", body: {status}});
      }
      notify(`Shipment created for order #${orderId}.`);
    }
    await loadAdminOrders();
  } catch (error) {
    notify(`Could not save shipment for order #${orderId}: ${error.message}`);
  } finally {
    if (button) { button.disabled = false; }
  }
}

function renderAdminOrders() {
  const container = document.getElementById("admin-orders-container");
  if (!container) return;
  const today = new Date().toLocaleDateString();
  const todaysOrders = adminOrders.filter(o => o.created_at && new Date(o.created_at).toLocaleDateString() === today);
  const counts = [
    ["All orders", adminOrders.length],
    ["Today's orders", todaysOrders.length],
    ["Pending", adminOrders.filter(o => o.status === "pending").length],
    ["Processing", adminOrders.filter(o => o.status === "processing").length],
    ["Shipped", adminOrders.filter(o => o.status === "shipped").length]
  ];
  document.getElementById("admin-summary").innerHTML = counts.map(([label,value]) => `<div class="card-fx bg-white border border-stone-200 rounded-xl p-4"><p class="text-xs text-stone-500">${label}</p><p class="text-2xl font-bold text-brand-800 mt-1" data-count="${value}">${value}</p></div>`).join("");

  animateCounts(); const search = (document.getElementById("admin-order-search")?.value || "").trim().toLowerCase();
  const status = document.getElementById("admin-status-filter")?.value || "";
  const todayOnly = document.getElementById("admin-today-only")?.checked || false;
  const filtered = adminOrders.filter(o => {
    const haystack = [o.id, o.customer_id, o.recipient_name, o.status, o.payment_status, o.city].join(" ").toLowerCase();
    return (!search || haystack.includes(search)) &&
      (!status || o.status === status) &&
      (!todayOnly || (o.created_at && new Date(o.created_at).toLocaleDateString() === today));
  }).sort((a,b) => new Date(b.created_at || 0) - new Date(a.created_at || 0));

  if (!filtered.length) {
    container.innerHTML = '<div class="bg-white border rounded-xl p-8 text-center text-stone-500">No matching orders found.</div>';
    return;
  }
  container.innerHTML = filtered.map(o => {
    const allowed = adminStatusOptions(o.status);
    const statusControl = allowed.length
      ? `<div class="flex flex-wrap gap-2"><select id="admin-status-${o.id}" class="border rounded-lg p-2 text-sm">${allowed.map(s=>`<option value="${s}">${s.replaceAll("_"," ")}</option>`).join("")}</select><button onclick="updateAdminOrderStatus(${o.id}, this)" class="bg-brand-700 text-white rounded-lg px-3 py-2 text-sm">Update order</button></div>`
      : `<span class="text-xs text-stone-500">No further order status changes allowed</span>`;
    const paymentOptions = {
      pending: ["paid","failed"],
      failed: ["pending"],
      paid: ["refunded","partially_refunded"],
      partially_refunded: ["refunded"],
      refunded: []
    }[o.payment_status] || [];
    const paymentControl = paymentOptions.length
      ? `<div class="flex flex-wrap gap-2"><select id="admin-payment-${o.id}" class="border rounded-lg p-2 text-sm">${paymentOptions.map(s=>`<option value="${s}">${s.replaceAll("_"," ")}</option>`).join("")}</select><button onclick="updateAdminPaymentStatus(${o.id}, this)" class="border border-brand-600 text-brand-700 rounded-lg px-3 py-2 text-sm">Update payment</button></div>`
      : `<span class="text-xs text-stone-500">No further payment status changes allowed</span>`;
    const items = (o.items || []).map(i=>`<div class="flex items-center justify-between gap-3 py-2 text-sm">
      <div class="flex min-w-0 items-center gap-3">
        <img src="${esc(getProductImage({name: i.product_name, image_url: i.image_url}))}" alt="${esc(i.product_name || "Product")}" class="w-12 h-12 rounded-lg object-cover border border-stone-200 bg-stone-50 flex-shrink-0" onerror="this.classList.add('hidden')">
        <span class="min-w-0">${esc(i.product_name || ("Product #" + i.product_id))} × ${i.quantity} ${esc(i.unit || "")}</span>
      </div>
      <b class="whitespace-nowrap">${money(i.subtotal)}</b>
    </div>`).join("");
    return `<article class="bg-white border border-stone-200 border-l-4 rounded-xl p-5 shadow-sm hover:shadow-md transition fade-up" style="border-left-color:${ORDER_COLORS[o.status]||'#d6d3d1'}">
      <div class="flex flex-wrap justify-between gap-4">
        <div><h3 class="font-bold text-lg">Order #${o.id}</h3><p class="text-xs text-stone-500 mt-1">${o.created_at ? new Date(o.created_at).toLocaleString() : "Date unavailable"}</p><p class="text-sm mt-2">Customer ID: ${esc(o.customer_id ?? "—")} · ${esc(o.recipient_name || "Customer")}</p><p class="text-sm text-stone-500">${esc(o.phone || "")}</p></div>
        <div class="text-right"><p class="font-bold text-xl text-brand-800">${money(o.total_amount)}</p>${Number(o.discount_amount) > 0 ? `<p class="text-xs text-brand-700 font-semibold">Includes offer −${money(o.discount_amount)}</p>` : ""}<div class="flex flex-wrap gap-2 justify-end mt-2">Order ${adminBadge(o.status)} Payment ${adminBadge(o.payment_status)}</div></div>
      </div>
      <div class="grid md:grid-cols-2 gap-5 border-t mt-4 pt-4">
        <div><h4 class="font-semibold mb-2">Items</h4>${items || '<p class="text-sm text-stone-500">No item details returned.</p>'}</div>
        <div><h4 class="font-semibold mb-2">Delivery details</h4><p class="text-sm">${esc(o.recipient_name || "")}</p><p class="text-sm">${esc(o.address_line1 || "")} ${esc(o.address_line2 || "")}</p><p class="text-sm">${esc(o.city || "")}, ${esc(o.state || "")} ${esc(o.postal_code || "")}</p><p class="text-sm text-stone-500 mt-1">Payment method: ${esc(String(o.payment_method || "").replaceAll("_"," "))}</p></div>
      </div>
      <div class="border-t mt-4 pt-4 grid md:grid-cols-2 gap-4"><div><p class="text-xs font-semibold text-stone-500 mb-2">ORDER STATUS</p>${statusControl}</div><div><p class="text-xs font-semibold text-stone-500 mb-2">PAYMENT STATUS</p>${paymentControl}</div></div>
      ${renderOrderShipmentPanel(o)}
    </article>`;
  }).join("");
}

async function updateAdminOrderStatus(orderId, btn) {
  const select = document.getElementById(`admin-status-${orderId}`);
  if (!select) return;
  try {
    await withBusy(btn, "Updating…", () => api(`/api/admin/orders/${orderId}/status`, {method:"PATCH", body:{status:select.value}}));
    showPop({title:`Order #${orderId} updated`, sub:`Status is now ${select.value.replaceAll("_"," ")}`});
    await loadAdminOrders();
  } catch(error) { notify(error.message); }
}

async function updateAdminPaymentStatus(orderId, btn) {
  const select = document.getElementById(`admin-payment-${orderId}`);
  if (!select) return;
  try {
    await withBusy(btn, "Updating…", () => api(`/api/admin/orders/${orderId}/payment-status`, {method:"PATCH", body:{payment_status:select.value}}));
    showPop({title:`Order #${orderId} payment updated`, sub:`Payment is now ${select.value.replaceAll("_"," ")}`});
    await loadAdminOrders();
  } catch(error) { notify(error.message); }
}

// Delivery and shipment management (Step 11.2)
const DELIVERY_STATUSES = ["pending", "packed", "shipped", "out_for_delivery", "delivered", "failed", "returned"];
// Must match allowed_transitions in app/api/routes/admin.py.
const DELIVERY_TRANSITIONS = {
  pending: ["packed", "shipped", "out_for_delivery", "delivered", "failed"],
  packed: ["shipped", "out_for_delivery", "delivered", "failed"],
  shipped: ["out_for_delivery", "delivered", "failed", "returned"],
  out_for_delivery: ["delivered", "failed", "returned"],
  delivered: [],
  failed: ["pending", "packed", "returned"],
  returned: []
};
let adminDeliveries = [];
let eligibleDeliveryOrders = [];

function deliveryStatusBadge(status) {
  const colors = {
    pending: "bg-amber-100 text-amber-800",
    packed: "bg-blue-100 text-blue-800",
    shipped: "bg-violet-100 text-violet-800",
    out_for_delivery: "bg-indigo-100 text-indigo-800",
    delivered: "bg-green-100 text-green-800",
    failed: "bg-red-100 text-red-800",
    returned: "bg-stone-200 text-stone-700"
  };
  const label = String(status || "pending").replaceAll("_", " ");
  return `<span class="inline-flex rounded-full px-2.5 py-1 text-xs font-semibold capitalize ${colors[status] || "bg-stone-100 text-stone-700"}">${esc(label)}</span>`;
}

async function loadAdminDeliveries() {
  const container = document.getElementById("admin-deliveries-container");
  if (!currentUser || currentUser.role !== "admin") {
    container.innerHTML = '<div class="bg-red-50 text-red-700 rounded-xl p-5">Administrator access is required.</div>';
    return;
  }
  container.innerHTML = '<p class="text-sm text-stone-500">Loading delivery records…</p>';
  try {
    const results = await Promise.all([
      api("/api/admin/deliveries"),
      api("/api/admin/orders")
    ]);
    adminDeliveries = Array.isArray(results[0]) ? results[0] : [];
    const orders = Array.isArray(results[1]) ? results[1] : [];
    const deliveryOrderIds = new Set(adminDeliveries.map(d => Number(d.order_id)));
    eligibleDeliveryOrders = orders.filter(o =>
      String(o.status || "").toLowerCase() !== "cancelled" &&
      !deliveryOrderIds.has(Number(o.id))
    );
    renderDeliveryOrderOptions();
    renderAdminDeliveries();
  } catch (error) {
    container.innerHTML = `<div class="bg-red-50 text-red-700 rounded-xl p-5"><b>Could not load shipment data.</b><p class="mt-1">${esc(error.message)}</p><p class="text-xs mt-2">Confirm the three delivery endpoints are installed in admin.py and restart FastAPI.</p></div>`;
  }
  if (window.lucide) lucide.createIcons();
}

function renderDeliveryOrderOptions() {
  const select = document.getElementById("delivery-order-id");
  const previous = select.value;
  if (!eligibleDeliveryOrders.length) {
    select.innerHTML = '<option value="">No eligible orders available</option>';
    return;
  }
  select.innerHTML = '<option value="">Select an order</option>' + eligibleDeliveryOrders.map(o =>
    `<option value="${Number(o.id)}">Order #${Number(o.id)} · ${esc(o.recipient_name || "Customer")} · ${money(o.total_amount)}</option>`
  ).join("");
  if (previous && eligibleDeliveryOrders.some(o => String(o.id) === previous)) select.value = previous;
}

function renderAdminDeliveries() {
  const container = document.getElementById("admin-deliveries-container");
  if (!container) return;
  const counts = [
    ["All shipments", adminDeliveries.length],
    ["Pending", adminDeliveries.filter(d => d.status === "pending").length],
    ["In transit", adminDeliveries.filter(d => ["shipped", "out_for_delivery"].includes(d.status)).length],
    ["Delivered", adminDeliveries.filter(d => d.status === "delivered").length]
  ];
  document.getElementById("delivery-summary").innerHTML = counts.map(([label, value]) =>
    `<div class="card-fx bg-white border border-stone-200 rounded-xl p-4"><p class="text-xs text-stone-500">${label}</p><p class="text-2xl font-bold text-brand-800 mt-1" data-count="${value}">${value}</p></div>`
  ).join("");

  animateCounts(); const search = (document.getElementById("delivery-search")?.value || "").trim().toLowerCase();
  const filtered = adminDeliveries.filter(d =>
    [d.id, d.order_id, d.tracking_number, d.delivery_partner, d.status].join(" ").toLowerCase().includes(search)
  ).sort((a, b) => Number(b.id) - Number(a.id));

  if (!filtered.length) {
    container.innerHTML = `<div class="text-center py-10 border border-dashed border-stone-300 rounded-xl"><div class="w-12 h-12 rounded-full bg-brand-50 text-brand-700 flex items-center justify-center mx-auto mb-3"><i data-lucide="truck" class="w-6 h-6"></i></div><p class="font-semibold text-stone-700">${search ? "No matching shipments" : "No delivery records yet"}</p><p class="text-sm text-stone-500 mt-1">${search ? "Try another search term." : "Use the form to assign a delivery to an eligible order."}</p></div>`;
    if (window.lucide) lucide.createIcons();
    return;
  }

  container.innerHTML = filtered.map(d => {
    const nextStatuses = DELIVERY_TRANSITIONS[d.status] || [];
    const options = nextStatuses.length
      ? nextStatuses.map(s => `<option value="${s}">${s.replaceAll("_", " ")}</option>`).join("")
      : "";
    const dateValue = d.estimated_delivery_date ? String(d.estimated_delivery_date).slice(0, 10) : "";
    return `<article class="border border-stone-200 rounded-xl p-4 sm:p-5">
      <div class="flex flex-wrap items-start justify-between gap-3 mb-4">
        <div><p class="text-xs text-stone-500">Delivery #${Number(d.id)}</p><h3 class="text-lg font-bold text-brand-800">Order #${Number(d.order_id)}</h3><div class="mt-2">${deliveryStatusBadge(d.status)}</div></div>
        <div class="text-right text-xs text-stone-500">${d.created_at ? `Created ${esc(new Date(d.created_at).toLocaleDateString("en-IN"))}` : ""}</div>
      </div>
      <form class="delivery-update-form grid sm:grid-cols-2 gap-3" onsubmit="saveDeliveryUpdate(event, ${Number(d.id)})">
        <div><label class="block text-xs font-semibold text-stone-600 mb-1" for="delivery-edit-tracking-${Number(d.id)}">Tracking number</label><input id="delivery-edit-tracking-${Number(d.id)}" maxlength="100" value="${esc(d.tracking_number || "")}" class="w-full border rounded-lg p-2.5 text-sm" placeholder="Tracking number"></div>
        <div><label class="block text-xs font-semibold text-stone-600 mb-1" for="delivery-edit-partner-${Number(d.id)}">Delivery partner</label><input id="delivery-edit-partner-${Number(d.id)}" maxlength="150" value="${esc(d.delivery_partner || "")}" class="w-full border rounded-lg p-2.5 text-sm" placeholder="Courier company"></div>
        <div><label class="block text-xs font-semibold text-stone-600 mb-1" for="delivery-edit-date-${Number(d.id)}">Estimated delivery date</label><input id="delivery-edit-date-${Number(d.id)}" type="date" value="${esc(dateValue)}" class="w-full border rounded-lg p-2.5 text-sm"></div>
        <div><label class="block text-xs font-semibold text-stone-600 mb-1" for="delivery-edit-status-${Number(d.id)}">Update delivery status</label><select id="delivery-edit-status-${Number(d.id)}" class="w-full border rounded-lg p-2.5 text-sm"><option value="">Keep current status (${esc(String(d.status).replaceAll("_", " "))})</option>${options}</select></div>
        <div class="sm:col-span-2 flex flex-wrap items-center justify-between gap-3 pt-2">
          <p class="text-xs text-stone-500">Order and payment statuses remain unchanged.</p>
          <button type="submit" class="bg-brand-700 hover:bg-brand-800 text-white rounded-lg px-4 py-2.5 text-sm font-semibold"><i data-lucide="save" class="w-4 h-4 inline mr-1"></i> Save shipment</button>
        </div>
      </form>
    </article>`;
  }).join("");
  if (window.lucide) lucide.createIcons();
}

document.getElementById("delivery-create-form")?.addEventListener("submit", async event => {
  event.preventDefault();
  if (!currentUser || currentUser.role !== "admin") {
    notify("Administrator access is required.");
    return;
  }
  const orderId = Number(document.getElementById("delivery-order-id").value);
  if (!orderId) {
    notify("Please select an order.");
    return;
  }
  const tracking = document.getElementById("delivery-tracking").value.trim();
  const partner = document.getElementById("delivery-partner").value.trim();
  const estimatedDate = document.getElementById("delivery-estimated-date").value;
  const payload = {
    order_id: orderId,
    tracking_number: tracking || null,
    delivery_partner: partner || null,
    estimated_delivery_date: estimatedDate || null
  };
  const button = document.getElementById("delivery-create-submit");
  button.disabled = true;
  button.textContent = "Creating…";
  try {
    const created = await api("/api/admin/deliveries", {method: "POST", body: payload});
    event.currentTarget.reset();
    notify(`Delivery #${created.id} created for order #${created.order_id}.`);
    await loadAdminDeliveries();
  } catch (error) {
    notify(`Could not create delivery: ${error.message}`);
  } finally {
    button.disabled = false;
    button.textContent = "Create delivery";
  }
});

async function saveDeliveryUpdate(event, deliveryId) {
  event.preventDefault();
  if (!currentUser || currentUser.role !== "admin") {
    notify("Administrator access is required.");
    return;
  }
  const tracking = document.getElementById(`delivery-edit-tracking-${deliveryId}`).value.trim();
  const partner = document.getElementById(`delivery-edit-partner-${deliveryId}`).value.trim();
  const estimatedDate = document.getElementById(`delivery-edit-date-${deliveryId}`).value;
  const status = document.getElementById(`delivery-edit-status-${deliveryId}`).value;
  const payload = {
    tracking_number: tracking || null,
    delivery_partner: partner || null,
    estimated_delivery_date: estimatedDate || null
  };
  if (status) payload.status = status;
  try {
    await api(`/api/admin/deliveries/${deliveryId}`, {method: "PATCH", body: payload});
    notify(`Delivery #${deliveryId} updated successfully.`);
    await loadAdminDeliveries();
  } catch (error) {
    notify(`Could not update delivery: ${error.message}`);
  }
}

async function loadAdminInventory() {
  if (!currentUser || currentUser.role !== "admin") { notify("Administrator access is required."); return; }
  const productsEl = document.getElementById("admin-inventory-products");
  const productSelect = document.getElementById("inventory-product");
  const historySelect = document.getElementById("inventory-history-product");
  productsEl.innerHTML = '<p class="text-sm text-stone-500">Loading product stock...</p>';
  try {
    const inventoryProducts = await api("/api/products/?limit=100&active_only=false");
    const currentSelection = productSelect.value, historySelection = historySelect.value;
    productSelect.innerHTML = '<option value="">Select a product</option>' + inventoryProducts.map(p => `<option value="${p.id}">${esc(p.name)} (ID: ${p.id})</option>`).join("");
    historySelect.innerHTML = '<option value="">All products</option>' + inventoryProducts.map(p => `<option value="${p.id}">${esc(p.name)}</option>`).join("");
    if (currentSelection) productSelect.value = currentSelection;
    if (historySelection) historySelect.value = historySelection;
    if (!inventoryProducts.length) productsEl.innerHTML = '<p class="text-sm text-stone-500">No products found.</p>';
    else productsEl.innerHTML = inventoryProducts.map(p => {
      const stock = Number(p.stock_quantity || 0), low = stock <= 10;
      return `<div class="flex flex-wrap items-center justify-between gap-3 border-b last:border-b-0 pb-3 last:pb-3"><div class="flex items-center gap-3 min-w-0"><img src="${esc(getProductImage(p))}" alt="${esc(p.name)}" class="w-14 h-14 rounded-lg object-cover border border-stone-200 bg-stone-50 flex-shrink-0 ${getProductImage(p) ? "" : "hidden"}" onerror="this.classList.add('hidden')"><div class="min-w-0"><p class="font-semibold text-sm">${esc(p.name)}</p><p class="text-xs text-stone-500">Product #${p.id} · ${esc(p.unit || "")}</p></div></div><div class="text-right"><p class="text-lg font-bold ${stock <= 0 ? "text-red-700" : low ? "text-amber-700" : "text-brand-800"}">${stock} ${esc(p.unit || "")}</p><p class="text-xs ${stock <= 0 ? "text-red-600" : low ? "text-amber-600" : "text-stone-500"}">${stock <= 0 ? "Out of stock" : low ? "Low stock (10 or less)" : "In stock"}</p></div></div>`;
    }).join("");
  } catch (error) { productsEl.innerHTML = `<p class="text-sm text-red-700">${esc(error.message)}</p>`; notify(`Could not load inventory: ${error.message}`); }
}

async function loadInventoryHistoryView() {
  if (!currentUser || currentUser.role !== "admin") return;
  try {
    const productsForHistory = await api("/api/products/?limit=100&active_only=false");
    const historySelect = document.getElementById("inventory-history-product");
    if (historySelect) {
      const selected = historySelect.value;
      historySelect.innerHTML = '<option value="">All products</option>' + productsForHistory.map(p =>
        `<option value="${p.id}">${esc(p.name)}</option>`
      ).join("");
      if (selected) historySelect.value = selected;
    }
    await loadInventoryMovements();
  } catch (error) {
    const container = document.getElementById("admin-inventory-movements");
    if (container) container.innerHTML = `<p class="text-sm text-red-700">${esc(error.message)}</p>`;
  }
}

async function loadInventoryMovements() {
  const container = document.getElementById("admin-inventory-movements");
  if (!container || !currentUser || currentUser.role !== "admin") return;
  container.innerHTML = '<p class="text-sm text-stone-500">Loading inventory movements...</p>';
  try {
    const productId = document.getElementById("inventory-history-product")?.value || "";
    const query = productId ? `?product_id=${encodeURIComponent(productId)}` : "";
    const movements = await api(`/api/admin/inventory/movements${query}`);
    if (!Array.isArray(movements) || !movements.length) { container.innerHTML = '<p class="text-sm text-stone-500 py-4">No inventory movements found.</p>'; return; }
    container.innerHTML = `<table class="min-w-full text-sm"><thead><tr class="text-left border-b text-xs uppercase tracking-wide text-stone-500"><th class="py-3 pr-4">Date</th><th class="py-3 pr-4">Product</th><th class="py-3 pr-4">Movement</th><th class="py-3 pr-4">Change</th><th class="py-3 pr-4">Previous</th><th class="py-3 pr-4">New stock</th><th class="py-3">Reason</th></tr></thead><tbody>${movements.map(m => { const change=Number(m.quantity_change || 0); return `<tr class="border-b last:border-b-0 align-top"><td class="py-3 pr-4 whitespace-nowrap">${m.created_at ? esc(new Date(m.created_at).toLocaleString()) : "—"}</td><td class="py-3 pr-4"><div class="flex items-center gap-2 min-w-40"><img src="${esc(getProductImage({name:m.product_name || "", image_url:m.image_url || ""}))}" alt="${esc(m.product_name || "Product")}" class="w-9 h-9 rounded-md object-cover border border-stone-200 bg-stone-50 flex-shrink-0" onerror="this.classList.add('hidden')"><span>${esc(m.product_name || `Product #${m.product_id}`)}</span></div></td><td class="py-3 pr-4 capitalize">${esc(String(m.movement_type || "adjustment").replaceAll("_", " "))}</td><td class="py-3 pr-4 font-semibold ${change < 0 ? "text-red-700" : "text-green-700"}">${change > 0 ? "+" : ""}${change}</td><td class="py-3 pr-4">${esc(m.previous_stock ?? "—")}</td><td class="py-3 pr-4 font-semibold">${esc(m.new_stock ?? "—")}</td><td class="py-3 min-w-48">${esc(m.reason || "—")}${m.order_id ? `<p class="text-xs text-stone-500 mt-1">Order #${esc(m.order_id)}</p>` : ""}</td></tr>`; }).join("")}</tbody></table>`;
  } catch (error) { container.innerHTML = `<p class="text-sm text-red-700 py-3">Could not load inventory movements: ${esc(error.message)}</p>`; }
}

document.getElementById("inventory-adjust-form")?.addEventListener("submit", async event => {
  event.preventDefault();
  if (!currentUser || currentUser.role !== "admin") { notify("Administrator access is required."); return; }
  const productId=document.getElementById("inventory-product").value;
  const quantityChange=Number(document.getElementById("inventory-quantity").value);
  const reason=document.getElementById("inventory-reason").value.trim();
  if (!productId) { notify("Please select a product."); return; }
  if (!Number.isInteger(quantityChange) || quantityChange === 0) { notify("Quantity change must be a non-zero whole number."); return; }
  if (!reason) { notify("Please enter a reason for the stock change."); return; }
  try {
    const result=await api(`/api/admin/products/${productId}/inventory`, {method:"POST", body:{quantity_change:quantityChange, reason}});
    notify(`Stock updated successfully. New stock: ${result.new_stock}.`);
    document.getElementById("inventory-quantity").value=""; document.getElementById("inventory-reason").value="";
    await loadAdminInventory();
  } catch(error) { notify(`Stock update failed: ${error.message}`); }
});


// ---- Admin: products ----
// Files in frontend/images, offered as suggestions in the image field.
const PRODUCT_IMAGE_FILES = ["regular-rice.jpg", "brown-rice.jpg", "red-chilli-powder.jpg", "ghee.jpg", "basmati-rice.jpg", "sona-masoori-rice.jpg", "toor-dal.jpg", "masoor-dal.jpg", "moong-dal.jpg", "whole-green-gram.jpg", "red-mirchi.jpg", "turmeric.jpg", "spices.jpg", "desi-ghee.jpg", "groundnut-oil.jpg", "sesame-oil.jpg", "sunflower-oil.jpg", "jaggery.jpg", "sugar.jpg", "wheat-flour.jpg", "ragi-flour.jpg"];
let adminProducts = [];

async function loadAdminProducts() {
  const list = document.getElementById("admin-products-list");
  list.innerHTML = '<p class="text-sm text-stone-500">Loading products...</p>';
  document.getElementById("pf-images").innerHTML = PRODUCT_IMAGE_FILES.map(f => `<option value="images/${f}">`).join("");
  try {
    adminProducts = await api("/api/products/?limit=100&active_only=false");
    document.getElementById("pf-categories").innerHTML = [...new Set(adminProducts.map(p => p.category))].map(c => `<option value="${esc(c)}">`).join("");
    renderAdminProducts();
  } catch (error) { list.innerHTML = `<p class="text-sm text-red-700">${esc(error.message)}</p>`; }
}

function renderAdminProducts() {
  const list = document.getElementById("admin-products-list");
  const q = document.getElementById("admin-product-search").value.trim().toLowerCase();
  const showHidden = document.getElementById("admin-product-show-hidden").checked;
  const rows = adminProducts.filter(p => (showHidden || p.is_active) && (!q || `${p.name} ${p.category}`.toLowerCase().includes(q)));
  if (!rows.length) { list.innerHTML = '<p class="text-sm text-stone-500 py-4">No products found. Use "New product" to add one, or run <code>uv run python -m app.cli seed-products</code>.</p>'; return; }
  list.innerHTML = `<table class="min-w-full text-sm"><thead><tr class="text-left border-b text-xs uppercase tracking-wide text-stone-500"><th class="py-3 pr-3">Product</th><th class="py-3 pr-3">Retail</th><th class="py-3 pr-3">Wholesale</th><th class="py-3 pr-3">Stock</th><th class="py-3"></th></tr></thead><tbody>${rows.map(p => {
    const img = getProductImage(p);
    return `<tr class="border-b last:border-b-0 align-middle ${p.is_active ? "" : "opacity-60"}">
      <td class="py-3 pr-3"><div class="flex items-center gap-3 min-w-48">${img ? `<img src="${esc(img)}" alt="" class="w-11 h-11 rounded-lg object-cover border border-stone-200 bg-stone-50 flex-shrink-0" onerror="this.style.visibility='hidden'">` : `<span class="w-11 h-11 rounded-lg bg-stone-100 flex-shrink-0"></span>`}<div class="min-w-0"><p class="font-semibold">${esc(p.name)}${p.is_active ? "" : ' <span class="text-xs font-semibold bg-stone-200 text-stone-700 rounded-full px-2 py-0.5">Hidden</span>'}</p><p class="text-xs text-stone-500">${esc(p.category)} · per ${esc(p.unit)}${p.image_url ? "" : " · no image set"}</p></div></div></td>
      <td class="py-3 pr-3 whitespace-nowrap">${money(p.retail_price)}</td>
      <td class="py-3 pr-3 whitespace-nowrap">${money(p.wholesale_price)}<p class="text-xs text-stone-500">from ${esc(p.min_wholesale_quantity)} ${esc(p.unit)}</p></td>
      <td class="py-3 pr-3 whitespace-nowrap ${Number(p.stock_quantity) <= 0 ? "text-red-700 font-semibold" : ""}">${esc(p.stock_quantity)}</td>
      <td class="py-3"><div class="flex flex-wrap gap-2 justify-end"><button class="border rounded-lg px-3 py-1 text-xs hover:bg-stone-50" onclick="editProduct(${p.id})">Edit</button><button class="border rounded-lg px-3 py-1 text-xs hover:bg-stone-50" onclick="toggleProductActive(${p.id}, this)">${p.is_active ? "Hide" : "Show"}</button><button class="border border-red-200 text-red-700 rounded-lg px-3 py-1 text-xs hover:bg-red-50" onclick="deleteProduct(${p.id})">Delete</button></div></td></tr>`;
  }).join("")}</tbody></table>`;
}

function updateProductImagePreview() {
  const value = document.getElementById("pf-image").value.trim();
  const img = document.getElementById("pf-image-preview");
  img.classList.toggle("hidden", !value);
  if (value) { img.onerror = () => img.classList.add("hidden"); img.src = value; }
}
document.getElementById("pf-image")?.addEventListener("input", updateProductImagePreview);

function startNewProduct() {
  const form = document.getElementById("admin-product-form");
  form.reset();
  form.elements.id.value = "";
  document.getElementById("admin-product-form-title").textContent = "New product";
  document.getElementById("pf-submit").textContent = "Create product";
  document.getElementById("pf-stock-wrap").classList.remove("hidden");
  document.getElementById("pf-stock-note").classList.add("hidden");
  updateProductImagePreview();
  form.elements.name.focus();
}

function editProduct(id) {
  const p = adminProducts.find(x => x.id === id);
  if (!p) return;
  const f = document.getElementById("admin-product-form").elements;
  f.id.value = p.id; f.name.value = p.name; f.category.value = p.category; f.unit.value = p.unit;
  f.description.value = p.description || ""; f.retail_price.value = p.retail_price; f.wholesale_price.value = p.wholesale_price;
  f.min_wholesale_quantity.value = p.min_wholesale_quantity; f.image_url.value = p.image_url || ""; f.is_active.checked = p.is_active;
  document.getElementById("admin-product-form-title").textContent = `Edit ${p.name}`;
  document.getElementById("pf-submit").textContent = "Save changes";
  // Stock changes go through Inventory so they are recorded with a reason.
  document.getElementById("pf-stock-wrap").classList.add("hidden");
  document.getElementById("pf-stock-note").classList.remove("hidden");
  updateProductImagePreview();
  document.getElementById("admin-product-form").scrollIntoView({behavior: "smooth", block: "start"});
}

document.getElementById("admin-product-form")?.addEventListener("submit", async event => {
  event.preventDefault();
  const f = event.currentTarget.elements, id = f.id.value;
  const retail = Number(f.retail_price.value), wholesale = Number(f.wholesale_price.value);
  if (wholesale > retail) { notify("Wholesale price cannot be higher than retail price."); return; }
  const body = {
    name: f.name.value.trim(), category: f.category.value.trim(), unit: f.unit.value.trim(),
    description: f.description.value.trim() || null, retail_price: retail, wholesale_price: wholesale,
    min_wholesale_quantity: Number(f.min_wholesale_quantity.value), image_url: f.image_url.value.trim() || null,
    is_active: f.is_active.checked,
  };
  if (!id) body.stock_quantity = Number(f.stock_quantity.value || 0);
  try {
    await withBusy(document.getElementById("pf-submit"), "Saving…", () =>
      api(id ? `/api/products/${id}` : "/api/products/", {method: id ? "PUT" : "POST", body}));
    notify(id ? "Product updated." : "Product created.");
    startNewProduct();
    await loadAdminProducts();
    loadCatalog();
  } catch (error) { notify(`Could not save product: ${error.message}`); }
});

async function toggleProductActive(id, btn) {
  const p = adminProducts.find(x => x.id === id);
  if (!p) return;
  try {
    await withBusy(btn, "…", () => api(`/api/products/${id}`, {method: "PUT", body: {is_active: !p.is_active}}));
    notify(p.is_active ? `${p.name} is hidden from the storefront.` : `${p.name} is back on the storefront.`);
    await loadAdminProducts();
    loadCatalog();
  } catch (error) { notify(error.message); }
}

async function deleteProduct(id) {
  const p = adminProducts.find(x => x.id === id);
  if (!p || !confirm(`Delete ${p.name} permanently? Products that have orders can only be hidden.`)) return;
  try {
    await api(`/api/products/${id}`, {method: "DELETE"});
    notify(`${p.name} deleted.`);
    await loadAdminProducts();
    loadCatalog();
  } catch (error) { notify(error.message); }
}

// ---- Admin: payments ----
let adminPayments = [];
const RECON_LABELS = {
  order_paid_without_successful_transaction: "Order marked paid, but no paid transaction exists",
  successful_transaction_order_not_paid: "A transaction is paid, but the order is not marked paid",
  multiple_successful_transactions: "More than one paid transaction (possible double charge)",
};

async function loadAdminPayments() {
  const list = document.getElementById("admin-payments-list");
  list.innerHTML = '<p class="text-sm text-stone-500">Loading payments...</p>';
  try {
    const [payments, recon] = await Promise.all([api("/api/payments/admin/history"), api("/api/payments/admin/reconciliation")]);
    adminPayments = payments;
    const sum = s => payments.filter(p => p.status === s).reduce((a, p) => a + Number(p.amount), 0);
    const count = s => payments.filter(p => p.status === s).length;
    document.getElementById("admin-payments-summary").innerHTML = [["Paid", "paid"], ["Pending", "pending"], ["Failed", "failed"]].map(([label, s]) =>
      `<div class="bg-white border border-stone-200 rounded-xl p-4"><p class="text-xs text-stone-500">${label} (${count(s)})</p><p class="text-xl font-bold">${money(sum(s))}</p></div>`).join("")
      + `<div class="bg-white border border-stone-200 rounded-xl p-4"><p class="text-xs text-stone-500">Orders checked</p><p class="text-xl font-bold">${esc(recon.total_orders_checked)}</p></div>`;
    document.getElementById("admin-payments-recon").innerHTML = recon.discrepancy_count
      ? `<div class="bg-red-50 border border-red-200 rounded-xl p-4"><p class="font-semibold text-red-800 mb-2">${recon.discrepancy_count} payment problem${recon.discrepancy_count === 1 ? "" : "s"} found</p><ul class="text-sm text-red-900 space-y-1">${recon.discrepancies.map(d => `<li>Order #${esc(d.order_id)}: ${esc(RECON_LABELS[d.issue] || d.issue)}</li>`).join("")}</ul></div>`
      : '<div class="bg-green-50 border border-green-200 text-green-800 rounded-xl p-4 text-sm">Reconciliation: every order payment status matches its transactions.</div>';
    renderAdminPayments();
  } catch (error) { list.innerHTML = `<p class="text-sm text-red-700">${esc(error.message)}</p>`; }
}

function renderAdminPayments() {
  const list = document.getElementById("admin-payments-list");
  const q = document.getElementById("admin-payment-search").value.trim().toLowerCase().replace(/^#/, "");
  const status = document.getElementById("admin-payment-status").value;
  const rows = adminPayments.filter(p => (!status || p.status === status) && (!q || String(p.order_id) === q || String(p.transaction_reference || "").toLowerCase().includes(q)));
  if (!rows.length) { list.innerHTML = '<p class="text-sm text-stone-500 py-4">No payments found. Payment records are created when a customer chooses online payment.</p>'; return; }
  list.innerHTML = `<table class="min-w-full text-sm"><thead><tr class="text-left border-b text-xs uppercase tracking-wide text-stone-500"><th class="py-3 pr-3">#</th><th class="py-3 pr-3">Order</th><th class="py-3 pr-3">Method</th><th class="py-3 pr-3">Amount</th><th class="py-3 pr-3">Status</th><th class="py-3 pr-3">Date</th><th class="py-3"></th></tr></thead><tbody>${rows.map(p => `
    <tr class="border-b last:border-b-0 align-top"><td class="py-3 pr-3">${esc(p.id)}</td><td class="py-3 pr-3">#${esc(p.order_id)}</td>
    <td class="py-3 pr-3">${p.payment_method === "online" ? "Online" : "Cash on delivery"}${p.transaction_reference ? `<p class="text-xs text-stone-500">${esc(p.transaction_reference)}</p>` : ""}</td>
    <td class="py-3 pr-3 whitespace-nowrap">${money(p.amount)}</td><td class="py-3 pr-3">${adminBadge(p.status)}${p.failure_reason ? `<p class="text-xs text-stone-500 mt-1">${esc(p.failure_reason)}</p>` : ""}</td>
    <td class="py-3 pr-3 whitespace-nowrap">${esc(new Date(p.created_at).toLocaleString())}</td>
    <td class="py-3">${p.status === "pending" ? `<div class="flex gap-2 justify-end"><button class="border border-green-300 text-green-800 rounded-lg px-3 py-1 text-xs hover:bg-green-50" onclick="setPaymentStatus(${p.id}, 'paid', this)">Mark paid</button><button class="border border-red-200 text-red-700 rounded-lg px-3 py-1 text-xs hover:bg-red-50" onclick="setPaymentStatus(${p.id}, 'failed', this)">Mark failed</button></div>` : ""}</td></tr>`).join("")}</tbody></table>`;
}

async function setPaymentStatus(id, status, btn) {
  const body = {status};
  if (status === "paid" && !confirm(`Mark payment #${id} as paid? Do this only after confirming the money was received.`)) return;
  if (status === "failed") {
    const reason = prompt("Reason for failure (optional):", "");
    if (reason === null) return;
    body.failure_reason = reason.trim() || null;
  }
  try {
    await withBusy(btn, "…", () => api(`/api/payments/admin/${id}/status`, {method: "PATCH", body}));
    notify(`Payment #${id} marked ${status}.`);
    await loadAdminPayments();
  } catch (error) { notify(error.message); }
}

// ---- Admin: customers ----
let adminCustomers = [];

async function loadAdminCustomers() {
  const list = document.getElementById("admin-customers-list");
  list.innerHTML = '<p class="text-sm text-stone-500">Loading customers...</p>';
  try { adminCustomers = await api("/api/admin/customers"); renderAdminCustomers(); }
  catch (error) { list.innerHTML = `<p class="text-sm text-red-700">${esc(error.message)}</p>`; }
}

function renderAdminCustomers() {
  const list = document.getElementById("admin-customers-list");
  const q = document.getElementById("admin-customer-search").value.trim().toLowerCase();
  const role = document.getElementById("admin-customer-role").value;
  const rows = adminCustomers.filter(c => (!role || c.role === role) && (!q || `${c.name} ${c.email}`.toLowerCase().includes(q)));
  if (!rows.length) { list.innerHTML = '<p class="text-sm text-stone-500 py-4">No customers found.</p>'; return; }
  list.innerHTML = `<table class="min-w-full text-sm"><thead><tr class="text-left border-b text-xs uppercase tracking-wide text-stone-500"><th class="py-3 pr-3">Customer</th><th class="py-3 pr-3">Type</th><th class="py-3 pr-3">Role</th><th class="py-3 pr-3">Orders</th><th class="py-3 pr-3">Joined</th><th class="py-3"></th></tr></thead><tbody>${rows.map(c => {
    const self = c.id === currentUser?.id;
    return `<tr class="border-b last:border-b-0 align-top ${c.is_active ? "" : "opacity-60"}">
      <td class="py-3 pr-3"><p class="font-semibold">${esc(c.name)}${self ? ' <span class="text-xs text-stone-500">(you)</span>' : ""}${c.is_active ? "" : ' <span class="text-xs font-semibold bg-red-100 text-red-800 rounded-full px-2 py-0.5">Inactive</span>'}</p><p class="text-xs text-stone-500">${esc(c.email)}${c.has_google_login ? " · Google" : ""}${c.email_verified ? "" : " · not verified"}</p></td>
      <td class="py-3 pr-3"><select class="border rounded-lg p-1 text-xs" onchange="updateCustomer(${c.id}, {customer_type: this.value})"><option value="retail" ${c.customer_type === "retail" ? "selected" : ""}>Retail</option><option value="wholesale" ${c.customer_type === "wholesale" ? "selected" : ""}>Wholesale</option></select></td>
      <td class="py-3 pr-3">${c.role === "admin" ? '<span class="text-xs font-semibold bg-brand-100 text-brand-800 rounded-full px-2 py-0.5">Admin</span>' : "Customer"}</td>
      <td class="py-3 pr-3">${esc(c.order_count)}</td>
      <td class="py-3 pr-3 whitespace-nowrap">${esc(new Date(c.created_at).toLocaleDateString())}</td>
      <td class="py-3">${self ? "" : `<div class="flex flex-wrap gap-2 justify-end">
        <button class="border rounded-lg px-3 py-1 text-xs hover:bg-stone-50" onclick="toggleCustomerRole(${c.id})">${c.role === "admin" ? "Remove admin" : "Make admin"}</button>
        <button class="border ${c.is_active ? "border-red-200 text-red-700 hover:bg-red-50" : "hover:bg-stone-50"} rounded-lg px-3 py-1 text-xs" onclick="toggleCustomerActive(${c.id})">${c.is_active ? "Deactivate" : "Reactivate"}</button></div>`}</td></tr>`;
  }).join("")}</tbody></table>`;
}

// Only the numeric id goes into onclick; names are looked up here, so a
// customer name can never break out of the attribute.
function toggleCustomerRole(id) {
  const c = adminCustomers.find(x => x.id === id);
  if (!c) return;
  const makeAdmin = c.role !== "admin";
  updateCustomer(id, {role: makeAdmin ? "admin" : "customer"}, `${makeAdmin ? "Give admin access to" : "Remove admin access from"} ${c.name}?`);
}
function toggleCustomerActive(id) {
  const c = adminCustomers.find(x => x.id === id);
  if (!c) return;
  updateCustomer(id, {is_active: !c.is_active}, c.is_active ? `Deactivate ${c.name}? They will not be able to log in.` : `Reactivate ${c.name}?`);
}

async function updateCustomer(id, changes, question) {
  if (question && !confirm(question)) { renderAdminCustomers(); return; }
  try {
    const updated = await api(`/api/admin/customers/${id}`, {method: "PATCH", body: changes});
    adminCustomers = adminCustomers.map(c => c.id === id ? updated : c);
    renderAdminCustomers();
    notify(`${updated.name} updated.`);
  } catch (error) { notify(error.message); renderAdminCustomers(); }
}
