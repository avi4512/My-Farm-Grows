// Checkout: addresses, delivery charge, placing the order, Razorpay and the success page.
// Plain scripts loaded in order by index.html; they share one global scope.

async function loadCheckout() {
  if (!token) { notify("Please log in before checkout."); openAccount(); navigate("cart"); return; }
  try {
    cart = await api("/api/cart");
    if (!cart.items.length) { notify("Your cart is empty."); navigate("cart"); return; }
    addresses = await api("/api/addresses/");
    selectedAddressId = addresses.find(a=>a.is_default)?.id || addresses[0]?.id || null;
    renderAddresses();
    renderCheckoutSummary();
  } catch(error) { notify(error.message); }
}
// Items, offer, delivery for the selected address, and the amount to pay.
function renderCheckoutSummary() {
  const el = document.getElementById("checkout-summary");
  if (!el || !cart.items?.length) return;
  const address = addresses.find(a => a.id === selectedAddressId);
  const delivery = address ? deliveryChargeFor(address.state, cart.total) : undefined;
  const deliveryRow = delivery === undefined
    ? `<div class="flex justify-between text-sm text-stone-600"><span>Delivery</span><span>Select an address</span></div>`
    : delivery === null
      ? `<p class="text-sm text-red-700 bg-red-50 rounded-lg p-2">We deliver only in Andhra Pradesh and Telangana right now. Please choose an address in one of these states.</p>`
      : `<div class="flex justify-between text-sm ${delivery ? "text-stone-600" : "font-semibold text-brand-700"}"><span>Delivery</span><span>${delivery ? money(delivery) : "Free"}</span></div>`;
  const total = Number(cart.total) + (delivery || 0);
  el.innerHTML = cart.items.map(i=>`<div class="flex justify-between gap-3"><span>${esc(i.product_name)} × ${i.quantity}</span><b>${money(i.subtotal)}</b></div>`).join("") + `<div class="border-t pt-3 space-y-1">${cartTotalsHtml(cart).rows}${deliveryRow}<div class="flex justify-between font-bold text-base"><span>Total</span><span>${money(total)}</span></div>${cartTotalsHtml(cart).note}<p class="text-xs text-stone-500">${DELIVERY_NOTE}</p></div>`;
}
function renderAddresses() {
  const el=document.getElementById("address-list");
  if(!addresses.length) { el.innerHTML='<p class="text-sm text-amber-700 bg-amber-50 p-3 rounded-lg">Add a delivery address below to continue.</p>'; return; }
  el.innerHTML=addresses.map(a=>`<label class="addr-card block border rounded-xl p-3 cursor-pointer ${selectedAddressId===a.id?'border-brand-600 bg-brand-50':''}"><div class="flex gap-2"><input type="radio" name="selected-address" value="${a.id}" ${selectedAddressId===a.id?'checked':''} onchange="selectAddress(${a.id})"><div class="text-sm"><b>${esc(a.recipient_name)} ${a.is_default?'<span class="text-xs text-brand-700">(Default)</span>':''}</b><p>${esc(a.phone)}</p><p>${esc(a.address_line1)} ${esc(a.address_line2||'')}</p><p>${esc(a.city)}, ${esc(a.state)} ${esc(a.postal_code)}, ${esc(a.country)}</p></div></div></label>`).join("");
}
async function useCurrentLocation() {
  const button = document.getElementById("use-current-location");
  const status = document.getElementById("location-status");
  const form = document.getElementById("address-form");
  if (!navigator.geolocation) { status.textContent = "Location is not supported by this browser. Please enter your address manually."; return; }
  button.disabled = true; button.classList.add("opacity-60");
  status.textContent = "Requesting your location permission…";
  navigator.geolocation.getCurrentPosition(async position => {
    try {
      status.textContent = "Finding your address…";
      const {latitude, longitude} = position.coords;
      const response = await fetch(`https://nominatim.openstreetmap.org/reverse?format=jsonv2&lat=${encodeURIComponent(latitude)}&lon=${encodeURIComponent(longitude)}&addressdetails=1`);
      if (!response.ok) throw new Error("Address lookup service is temporarily unavailable.");
      const result = await response.json();
      const a = result.address || {};
      const setIfFound = (name, value) => { if (value && form.elements[name]) form.elements[name].value = value; };
      const house = [a.house_number, a.road].filter(Boolean).join(" ");
      setIfFound("address_line1", house || a.road || a.pedestrian || a.neighbourhood);
      setIfFound("city", a.city || a.town || a.village || a.municipality || a.county);
      setIfFound("state", a.state);
      setIfFound("postal_code", a.postcode);
      setIfFound("country", a.country || "India");
      status.textContent = "Location detected. Please verify the fields and add your flat/apartment number and landmark before saving.";
      notify("Location details filled. Please review your address.");
    } catch (error) {
      status.textContent = `${error.message} You can still enter the address manually.`;
    } finally {
      button.disabled = false; button.classList.remove("opacity-60");
    }
  }, error => {
    const messages = {1:"Location permission was denied. Allow location access in your browser settings.",2:"Your location could not be determined. Try again or enter it manually.",3:"Location request timed out. Try again."};
    status.textContent = messages[error.code] || "Could not get your location. Please enter the address manually.";
    button.disabled = false; button.classList.remove("opacity-60");
  }, {enableHighAccuracy:true, timeout:15000, maximumAge:60000});
}
document.getElementById("address-form").addEventListener("submit", async event=>{
  event.preventDefault(); const f=new FormData(event.currentTarget);
  const payload={recipient_name:f.get("recipient_name"),phone:f.get("phone"),address_line1:f.get("address_line1"),address_line2:f.get("address_line2")||null,landmark:f.get("landmark")||null,city:f.get("city"),state:f.get("state"),postal_code:f.get("postal_code"),country:f.get("country"),is_default:f.get("is_default")==="on"};
  try { const a=await api("/api/addresses/",{method:"POST",body:payload}); addresses=await api("/api/addresses/"); selectedAddressId=a.id; renderAddresses(); renderCheckoutSummary(); event.currentTarget.reset(); event.currentTarget.elements.country.value="India"; notify("Address saved."); }
  catch(error){notify(error.message);}
});
async function placeOrder() {
  if (!token || !currentUser) {
    notify("Please log in before placing an order.");
    openAccount();
    return;
  }
  if (!selectedAddressId) { notify("Please add or select a delivery address."); return; }
  const button = document.querySelector('#view-checkout button[onclick="placeOrder()"]');
  if (button) { button.disabled = true; button.textContent = "Placing order…"; }
  showOrderOverlay();
  try {
    const order = await api("/api/orders/", {
      method: "POST",
      body: {
        address_id: selectedAddressId,
        payment_method: document.getElementById("payment-method").value
      }
    });
    lastPlacedOrder = order;
    lastOrderMessage = "";
    // The server empties the cart with the order; match it so the badge and product steppers reset.
    cart = {items: [], total: 0};
    updateCartBadge();

    await finishOrderOverlay();
    if (order.payment_method === "online") {
      hideOrderOverlay();
      const result = await payOnline(order.id);
      if (result === "paid") order.payment_status = "paid";
      else lastOrderMessage = result === "failed"
        ? "Your order is saved, but the payment did not go through. You can try again from My Orders."
        : "Your order is saved and waiting for payment. You can pay any time from My Orders.";
    }
    renderOrderSuccess();
    navigate("order-success");
    launchConfetti();
    notify(`Order #${order.id} placed successfully.`);
  } catch (error) {
    notify(error.message);
  } finally {
    hideOrderOverlay();
    if (button) { button.disabled = false; button.textContent = "Place order"; }
  }
}

// ---- Online payment (Razorpay Checkout) ----
// The server creates the Razorpay order and verifies the result; the browser
// only opens the payment window. No secret ever reaches this page.
let paymentConfig = {online_enabled: false, key_id: null};
async function loadPaymentConfig() {
  try { paymentConfig = await api("/api/payments/config"); } catch { paymentConfig = {online_enabled: false, key_id: null}; }
  const option = document.getElementById("online-pay-option");
  option.disabled = !paymentConfig.online_enabled;
  option.textContent = paymentConfig.online_enabled ? "Pay online (UPI, card, netbanking)" : "Pay online (coming soon)";
  const notice = document.getElementById("admin-payments-notice");
  if (notice && paymentConfig.online_enabled) {
    notice.textContent = "Online payments are confirmed by Razorpay automatically. Use Mark paid only for payments you have checked in the Razorpay dashboard.";
  }
}
let razorpayScript = null;
function loadRazorpayScript() {
  if (window.Razorpay) return Promise.resolve();
  razorpayScript ??= new Promise((resolve, reject) => {
    const tag = document.createElement("script");
    tag.src = "https://checkout.razorpay.com/v1/checkout.js";
    tag.onload = resolve;
    tag.onerror = () => { razorpayScript = null; reject(new Error("Could not load the payment window. Check your internet connection.")); };
    document.head.appendChild(tag);
  });
  return razorpayScript;
}
// Opens Razorpay for one order. Resolves to "paid", "failed" or "dismissed".
async function payOnline(orderId) {
  try {
    const [session] = await Promise.all([
      api("/api/payments/razorpay/order", {method: "POST", body: {order_id: orderId}}),
      loadRazorpayScript(),
    ]);
    return await new Promise(resolve => {
      let failed = false;
      const checkout = new window.Razorpay({
        key: session.key_id,
        order_id: session.razorpay_order_id,
        amount: session.amount,
        currency: session.currency,
        name: "My Farm Grow",
        description: `Order #${session.order_id}`,
        prefill: {name: session.customer_name, email: session.customer_email},
        theme: {color: "#3f7d20"},
        handler: async response => {
          try {
            const payment = await api("/api/payments/razorpay/verify", {method: "POST", body: response});
            if (payment.status === "paid") { notify("Payment received. Thank you!"); resolve("paid"); }
            else { notify("The payment did not go through."); resolve("failed"); }
          } catch (error) { notify(error.message); resolve("failed"); }
        },
        modal: {ondismiss: () => resolve(failed ? "failed" : "dismissed")},
      });
      // Razorpay lets the customer retry inside the window, so only remember the failure.
      checkout.on("payment.failed", () => { failed = true; });
      checkout.open();
    });
  } catch (error) {
    notify(error.message);
    return "failed";
  }
}
async function payOnlineFromOrders(orderId, button) {
  if (button) { button.disabled = true; button.textContent = "Opening…"; }
  await payOnline(orderId);
  await loadOrders();
}

function renderOrderSuccess() {
  const order = lastPlacedOrder;
  if (!order) {
    document.getElementById("order-success-id").textContent = "No recent order";
    document.getElementById("order-success-total").textContent = money(0);
    document.getElementById("order-success-status").textContent = "Unavailable";
    document.getElementById("order-success-method").textContent = "—";
    document.getElementById("order-success-payment").textContent = "—";
    return;
  }

  const status = String(order.status || "pending").toLowerCase();
  const paymentStatus = String(order.payment_status || (order.payment_method === "cash_on_delivery" ? "pending" : "pending")).toLowerCase();
  document.getElementById("order-success-id").textContent = `Order #${order.id}`;
  document.getElementById("order-success-total").textContent = money(order.total_amount);
  document.getElementById("order-success-status").outerHTML = `<span id="order-success-status" class="inline-flex rounded-full px-3 py-1.5 text-sm font-bold ${status === "delivered" ? "bg-green-100 text-green-800" : status === "cancelled" ? "bg-red-100 text-red-800" : status === "shipped" ? "bg-violet-100 text-violet-800" : status === "processing" ? "bg-blue-100 text-blue-800" : "bg-amber-100 text-amber-800"}">${esc(status.replaceAll("_", " "))}</span>`;
  document.getElementById("order-success-method").textContent = String(order.payment_method || "—").replaceAll("_", " ");
  document.getElementById("order-success-payment").innerHTML = adminBadge(paymentStatus);

  const message = document.getElementById("order-success-message");
  if (lastOrderMessage) {
    message.textContent = lastOrderMessage;
    message.className = "text-sm rounded-lg p-3 mb-5 border border-amber-200 bg-amber-50 text-amber-800";
  } else if (order.payment_method === "online") {
    message.textContent = "Payment received. Thank you!";
    message.className = "text-sm rounded-lg p-3 mb-5 border border-green-200 bg-green-50 text-green-800";
  } else {
    message.textContent = "Please pay the order amount to the delivery partner when your order arrives.";
    message.className = "text-sm rounded-lg p-3 mb-5 border border-green-200 bg-green-50 text-green-800";
  }
  if (window.lucide) lucide.createIcons();
}
