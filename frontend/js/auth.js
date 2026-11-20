// Login, registration, email OTP, password reset, Google sign-in and the account menus.
// Plain scripts loaded in order by index.html; they share one global scope.

let authStep = "credentials";
let forgotStep = "request";
let authOtpTimer = null;
let authOtpEmail = "";
let authResetToken = "";
let authOtpPurpose = "registration";
let authGoogleClientId = null;

let accountOpener = null;
function openAccount() {
  accountOpener = document.activeElement;
  document.getElementById("account-modal").classList.remove("hidden"); document.documentElement.classList.add("modal-open");
  if (!currentUser) { setAuthMode("login"); return; }
  ["account-form", "auth-tabs", "google-auth-area", "auth-back", "auth-progress", "auth-error"].forEach(id => showAuthField(id, false));
  showAuthField("account-summary", true);
  const admin = currentUser.role === "admin";
  document.getElementById("account-title").textContent = "Your account";
  document.getElementById("auth-message").textContent = "You're logged in and ready to shop.";
  document.getElementById("summary-initial").textContent = String(currentUser.name || "?").trim().charAt(0).toUpperCase();
  document.getElementById("summary-name").textContent = currentUser.name || "";
  document.getElementById("summary-email").textContent = currentUser.email || "";
  document.getElementById("summary-type").textContent = admin ? "Administrator" : currentUser.customer_type === "wholesale" ? "Wholesale customer" : "Retail customer";
  showAuthField("summary-orders", !admin);
}
function closeAccount() {
  document.getElementById("account-modal").classList.add("hidden");
  document.documentElement.classList.remove("modal-open");
  if (authOtpTimer) { clearInterval(authOtpTimer); authOtpTimer = null; }
  if (accountOpener?.isConnected) accountOpener.focus({preventScroll: true});
  accountOpener = null;
}
// A stray click outside must not throw away a registration or reset in progress.
function handleAccountBackdrop(event) {
  if (event.target !== event.currentTarget) return;
  if (authMode === "forgot" || authStep !== "credentials") return;
  closeAccount();
}
document.addEventListener("keydown", event => {
  if (event.key === "Escape" && !document.getElementById("account-modal").classList.contains("hidden")) closeAccount();
});
function showAuthError(message) {
  const box = document.getElementById("auth-error");
  box.textContent = message;
  box.classList.toggle("hidden", !message);
}
function togglePasswordVisibility(button) {
  const input = button.parentElement.querySelector("input");
  const show = input.type === "password";
  input.type = show ? "text" : "password";
  button.textContent = show ? "Hide" : "Show";
  button.setAttribute("aria-pressed", String(show));
  button.setAttribute("aria-label", show ? "Hide password" : "Show password");
}
function hidePasswords() {
  document.querySelectorAll("#account-form .auth-show").forEach(button => {
    if (button.parentElement.querySelector("input").type === "text") togglePasswordVisibility(button);
  });
}
function handleOtpInput(input) {
  input.value = input.value.replace(/\D/g, "").slice(0, 6);
  if (input.value.length === 6 && !document.getElementById("account-submit").disabled) document.getElementById("account-form").requestSubmit();
}
const AUTH_STEP_LABELS = {register: ["Your details", "Verify email", "Set password"], forgot: ["Your email", "Enter code", "New password"]};
// Shows the right chrome and fields for each step of login, registration and password reset.
function setAuthFlowStep(step) {
  const form = document.getElementById("account-form");
  const inFlow = step > 1 || authMode === "forgot";
  showAuthField("auth-tabs", !inFlow);
  showAuthField("auth-back", inFlow);
  showAuthField("google-auth-area", !inFlow);
  showAuthField("email-field", step === 1);
  showAuthError("");
  hidePasswords();
  const progress = document.getElementById("auth-progress");
  const labels = AUTH_STEP_LABELS[authMode];
  progress.classList.toggle("hidden", !labels);
  progress.innerHTML = labels ? labels.map((label, i) => `<span class="${i + 1 < step ? "done" : i + 1 === step ? "current" : ""}"${i + 1 === step ? ' aria-current="step"' : ""}>${label}</span>`).join("") : "";
  form.elements.otp.value = "";
  form.elements.password.autocomplete = authMode === "login" ? "current-password" : "new-password";
  form.elements.password.placeholder = authMode === "login" ? "Enter your password" : "At least 8 characters";
  document.getElementById("auth-password-label").textContent = authMode === "login" ? "Password" : authMode === "forgot" ? "New password" : "Create password";
  if (matchMedia("(hover: hover)").matches) {
    setTimeout(() => form.querySelector("#account-form > div:not(.hidden) input")?.focus(), 60);
  }
}
function showAuthField(id, show) { document.getElementById(id).classList.toggle("hidden", !show); }
function setAuthMode(mode) {
  authMode = mode; authStep = "credentials";
  if (authOtpTimer) { clearInterval(authOtpTimer); authOtpTimer = null; }
  const form = document.getElementById("account-form");
  showAuthField("account-summary", false);
  form.classList.remove("hidden");
  document.getElementById("account-title").textContent = mode === "login" ? "Welcome back" : "Create your account";
  showAuthField("name-field", mode === "register");
  showAuthField("customer-type-field", mode === "register");
  showAuthField("otp-field", false); showAuthField("confirm-password-field", false);
  showAuthField("password-field", mode === "login");
  showAuthField("forgot-password", mode === "login");
  showAuthField("resend-otp", false); showAuthField("otp-help", false);
  form.elements.name.required = mode === "register";
  form.elements.name.disabled = mode !== "register";
  form.elements.password.required = mode === "login";
  form.elements.confirm_password.required = false;
  form.elements.otp.required = false;
  form.elements.password.value = ""; form.elements.confirm_password.value = "";
  document.getElementById("account-submit").textContent = mode === "login" ? "Login" : "Send verification code";
  ["login", "register"].forEach(name => document.getElementById(`${name}-tab`).setAttribute("aria-selected", String(mode === name)));
  const forCart = window.pendingCartProduct ? "Log in to add this item to your cart." : "Log in to order and track your groceries.";
  document.getElementById("auth-message").textContent = mode === "register" ? "We'll email you a code to confirm it's really you." : forCart;
  setAuthFlowStep(1);
  if (window.google?.accounts?.id && authGoogleClientId) renderGoogleButton();
}
async function loadMe() {
  if (!token) return;
  try { currentUser = await api("/api/auth/me"); }
  catch { currentUser = null; token = ""; localStorage.removeItem("mfg_access_token"); }
  updateAccountButton();
}
async function logout() {
  token = ""; currentUser = null; localStorage.removeItem("mfg_access_token");
  cart = {items:[], total:0}; updateCartBadge(); updateAccountButton(); closeAccount();
  notify("You have logged out."); navigate("home");
}
function startOtpCountdown(seconds) {
  if (authOtpTimer) clearInterval(authOtpTimer);
  let remaining = seconds;
  const btn = document.getElementById("resend-otp");
  const update = () => {
    document.getElementById("otp-help").textContent = `Code expires in 5 minutes. You can request another code in ${remaining} seconds.`;
    if (remaining <= 0) { clearInterval(authOtpTimer); btn.disabled = false; btn.textContent = "Resend code"; }
    else { btn.disabled = true; btn.textContent = `Resend in ${remaining}s`; }
    remaining--;
  };
  update(); authOtpTimer = setInterval(update, 1000);
}
async function resendAuthOTP() {
  const email = authOtpEmail || document.getElementById("account-form").elements.email.value.trim();
  if (!email) return;
  try {
    const path = authOtpPurpose === "registration" ? "/api/auth/register/request-otp" : "/api/auth/password/forgot/request-otp";
    const body = authOtpPurpose === "registration"
      ? {name:document.getElementById("account-form").elements.name.value.trim(), email, customer_type:document.getElementById("account-form").elements.customer_type.value}
      : {email};
    const result = await api(path, {method:"POST", body});
    startOtpCountdown(result.resend_after_seconds || 60);
    showAuthError("");
    notify("A new verification code has been sent.");
  } catch (error) { showAuthError(error.message); }
}
async function startForgotPassword() {
  authMode = "forgot"; forgotStep = "request"; authOtpPurpose = "password_reset";
  document.getElementById("account-title").textContent = "Reset password";
  showAuthField("name-field", false); showAuthField("customer-type-field", false);
  showAuthField("password-field", false); showAuthField("confirm-password-field", false);
  document.getElementById("account-form").elements.password.required = false;
  document.getElementById("account-form").elements.otp.required = false;
  document.getElementById("account-form").elements.confirm_password.required = false;
  showAuthField("otp-field", false); showAuthField("forgot-password", false);
  showAuthField("resend-otp", false); showAuthField("otp-help", false);
  document.getElementById("account-submit").textContent = "Send reset code";
  document.getElementById("auth-message").textContent = "Enter your registered email address to receive a password reset code.";
  setAuthFlowStep(1);
}
async function finishLogin(data) {
  token = data.access_token; localStorage.setItem("mfg_access_token", token);
  currentUser = await api("/api/auth/me");
  try { cart = await api("/api/cart"); updateCartBadge(); } catch {}
  updateAccountButton(); closeAccount();
  document.getElementById("account-form").reset();
  showWelcome(currentUser);
  if (currentUser.role === "admin") { navigate("admin"); return; }
  if (window.pendingCartProduct) { const id = window.pendingCartProduct; window.pendingCartProduct = null; await addToCart(id); }
}
document.getElementById("account-form").addEventListener("submit", async event => {
  event.preventDefault();
  const formEl = event.currentTarget, f = new FormData(formEl);
  const btn = document.getElementById("account-submit");
  const submitLabel = btn.textContent;
  showAuthError("");
  btn.disabled = true; btn.innerHTML = '<span class="mini-spin"></span> Please wait…';
  try {
    const email = String(f.get("email") || "").trim().toLowerCase();
    if (authMode === "login") {
      const body = new URLSearchParams({username:email, password:f.get("password")});
      const response = await fetch(`${API_BASE}/api/auth/login`, {method:"POST", headers:{"Content-Type":"application/x-www-form-urlencoded"}, body});
      const data = await response.json(); if (!response.ok) throw new Error(data.detail || "Login failed");
      await finishLogin(data); return;
    }
    if (authMode === "register" && authStep === "credentials") {
      const result = await api("/api/auth/register/request-otp", {method:"POST", body:{name:f.get("name"), email, customer_type:f.get("customer_type")}});
      authOtpEmail = email; authOtpPurpose = "registration"; authStep = "verify";
      showAuthField("name-field", false); showAuthField("customer-type-field", false);
      showAuthField("password-field", false); showAuthField("otp-field", true);
      showAuthField("forgot-password", false); showAuthField("resend-otp", true); showAuthField("otp-help", true);
      document.getElementById("account-form").elements.otp.required = true;
      document.getElementById("account-title").textContent = "Verify your email";
      document.getElementById("account-submit").textContent = "Verify email";
      document.getElementById("auth-message").textContent = `We sent a six-digit code to ${email}.`;
      setAuthFlowStep(2);
      startOtpCountdown(result.resend_after_seconds || 60); return;
    }
    if (authMode === "register" && authStep === "verify") {
      await api("/api/auth/register/verify-otp", {method:"POST", body:{email:authOtpEmail, otp:f.get("otp")}});
      authStep = "password";
      showAuthField("otp-field", false); showAuthField("resend-otp", false); showAuthField("otp-help", false);
      formEl.elements.otp.required = false;
      showAuthField("password-field", true); showAuthField("confirm-password-field", true);
      formEl.elements.password.required = true; formEl.elements.confirm_password.required = true;
      document.getElementById("account-title").textContent = "Create password";
      document.getElementById("account-submit").textContent = "Create account";
      document.getElementById("auth-message").textContent = "Email verified. Create a password to finish registration.";
      setAuthFlowStep(3); return;
    }
    if (authMode === "register" && authStep === "password") {
      if (f.get("password") !== f.get("confirm_password")) throw new Error("Passwords do not match.");
      const data = await api("/api/auth/register/complete", {method:"POST", body:{email:authOtpEmail, password:f.get("password")}});
      await finishLogin(data); notify("Your email-verified account is ready."); return;
    }
    if (authMode === "forgot" && forgotStep === "request") {
      const result = await api("/api/auth/password/forgot/request-otp", {method:"POST", body:{email}});
      authOtpEmail = email; forgotStep = "verify"; showAuthField("otp-field", true);
      showAuthField("password-field", false); showAuthField("resend-otp", true); showAuthField("otp-help", true);
      formEl.elements.otp.required = true;
      document.getElementById("account-submit").textContent = "Verify code";
      document.getElementById("auth-message").textContent = "If the account exists, a reset code has been sent.";
      setAuthFlowStep(2);
      startOtpCountdown(result.resend_after_seconds || 60); return;
    }
    if (authMode === "forgot" && forgotStep === "verify") {
      const result = await api("/api/auth/password/forgot/verify-otp", {method:"POST", body:{email:authOtpEmail, otp:f.get("otp")}});
      authResetToken = result.reset_token; forgotStep = "reset";
      showAuthField("otp-field", false); showAuthField("resend-otp", false); showAuthField("otp-help", false);
      formEl.elements.otp.required = false;
      showAuthField("password-field", true); showAuthField("confirm-password-field", true);
      formEl.elements.password.required = true; formEl.elements.confirm_password.required = true;
      document.getElementById("account-submit").textContent = "Update password";
      document.getElementById("auth-message").textContent = "Choose a new password.";
      setAuthFlowStep(3); return;
    }
    if (authMode === "forgot" && forgotStep === "reset") {
      if (f.get("password") !== f.get("confirm_password")) throw new Error("Passwords do not match.");
      await api("/api/auth/password/forgot/reset", {method:"POST", body:{email:authOtpEmail, reset_token:authResetToken, new_password:f.get("password")}});
      notify("Password updated. Please log in."); setAuthMode("login"); return;
    }
  } catch (error) {
    btn.textContent = submitLabel;
    showAuthError(error.message);
  }
  finally { btn.disabled = false; if (authMode === "login") btn.textContent = "Login"; }
});

async function initializeGoogleSignIn() {
  try {
    const config = await api("/api/auth/config");
    authGoogleClientId = config.google_client_id;
    if (!authGoogleClientId) {
      document.getElementById("google-auth-area").innerHTML = '<p class="text-xs text-stone-500 text-center mt-4">Google sign-in is not configured yet.</p>';
      return;
    }
    const waitForGoogle = () => {
      if (window.google?.accounts?.id) renderGoogleButton();
      else setTimeout(waitForGoogle, 250);
    };
    waitForGoogle();
  } catch (error) { console.warn("Google sign-in initialization unavailable."); }
}
function renderGoogleButton() {
  const target = document.getElementById("google-signin-button");
  if (!target || !window.google?.accounts?.id || !authGoogleClientId) return;
  if (target.childElementCount) return; // already rendered; re-rendering makes the layout jump
  google.accounts.id.initialize({client_id:authGoogleClientId, callback:handleGoogleCredential});
  google.accounts.id.renderButton(target, {theme:"outline", size:"large", shape:"pill", text:"continue_with", width:Math.min(320, innerWidth - 115)});
}
async function handleGoogleCredential(response) {
  try {
    const result = await api("/api/auth/google", {method:"POST", body:{credential:response.credential}});
    await finishLogin(result); notify("Signed in with Google.");
  } catch (error) { showAuthError(error.message); }
}
initializeGoogleSignIn();

function toggleCustomerMenu() {
  if (!currentUser || currentUser.role === "admin") {
    notify("Please log in with a customer account to open this menu.");
    return;
  }
  closeAdminMenu();
  const panel = document.getElementById("customer-menu-panel");
  const toggle = document.getElementById("customer-menu-toggle");
  if (!panel || !toggle) return;
  const willOpen = panel.classList.contains("hidden");
  panel.classList.toggle("hidden", !willOpen);
  toggle.setAttribute("aria-expanded", String(willOpen));
}

function closeCustomerMenu() {
  document.getElementById("customer-menu-panel")?.classList.add("hidden");
  document.getElementById("customer-menu-toggle")?.setAttribute("aria-expanded", "false");
}

function customerMenuAction(action) {
  closeCustomerMenu();
  if (!currentUser || currentUser.role === "admin") {
    notify("Please log in with a customer account to continue.");
    openAccount();
    return;
  }
  if (action === "orders") {
    navigate("orders");
  } else if (action === "dashboard") {
    navigate("dashboard");
  } else if (action === "addresses") {
    navigate("addresses");
  } else if (action === "profile") {
    openAccount();
  } else if (action === "support") {
    navigate("contact");
  } else if (action === "tracking") {
    navigate("tracking");
  } else if (action === "payments") {
    navigate("payments");
  } else {
    const labels = {
      payments: "Payment History",
      tracking: "Order Tracking",
      addresses: "My Addresses",
      profile: "My Profile",
      support: "Help & Support"
    };
    notify(`${labels[action] || "This section"} will be connected in the next dashboard steps.`);
  }
}

function toggleAdminMenu() {
  closeCustomerMenu();
  const panel = document.getElementById("admin-menu-panel");
  const toggle = document.getElementById("admin-menu-toggle");
  if (!panel || !toggle) return;
  const willOpen = panel.classList.contains("hidden");
  panel.classList.toggle("hidden", !willOpen);
  toggle.setAttribute("aria-expanded", String(willOpen));
}

function closeAdminMenu() {
  document.getElementById("admin-menu-panel")?.classList.add("hidden");
  document.getElementById("admin-menu-toggle")?.setAttribute("aria-expanded", "false");
}

function adminMenuAction(action) {
  closeAdminMenu();
  if (!currentUser || currentUser.role !== "admin") {
    notify("Administrator access is required.");
    return;
  }
  if (action === "orders") {
    navigate("admin");
  } else if (action === "deliveries") {
    navigate("deliveries");
  } else if (action === "inventory") {
    navigate("inventory");
  } else if (action === "inventory-history") {
    navigate("inventory-history");
  } else if (action === "products") {
    navigate("admin-products");
  } else if (action === "payments") {
    navigate("admin-payments");
  } else if (action === "customers") {
    navigate("admin-customers");
  }
}

document.addEventListener("click", event => {
  const adminWrap = document.getElementById("admin-menu-wrap");
  const customerWrap = document.getElementById("customer-menu-wrap");
  if (adminWrap && !adminWrap.contains(event.target)) closeAdminMenu();
  if (customerWrap && !customerWrap.contains(event.target)) closeCustomerMenu();
});
