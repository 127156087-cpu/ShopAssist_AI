// ---------- helpers ----------
const $ = (id) => document.getElementById(id);

// Each browser gets its own conversation id, so refreshing the page keeps the same chat thread
let sessionId = localStorage.getItem("shopassist-session") || newSession();
function newSession() {
  const id = crypto.randomUUID().replaceAll("-", "").slice(0, 20);
  localStorage.setItem("shopassist-session", id);
  return id;
}

function esc(text) {
  const div = document.createElement("div");
  div.textContent = text ?? "";
  return div.innerHTML;
}

async function api(path, options = {}) {
  const headers = { "X-Session-Id": sessionId, ...(options.headers || {}) };
  const response = await fetch(path, { ...options, headers });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || "Something went wrong.");
  return data;
}

function post(data, headers = {}) {
  return { method: "POST", headers: { "Content-Type": "application/json", ...headers }, body: JSON.stringify(data) };
}

const percent = (value) => (value === null || value === undefined ? "n/a" : Math.round(value * 100) + "%");
const badge = (status) => `<span class="badge ${status}">${esc(status.replaceAll("_", " "))}</span>`;
const kv = (object) => Object.entries(object).map(([k, v]) => `<span>${esc(k)}</span><span>${esc(String(v ?? "-"))}</span>`).join("");

// ---------- tabs ----------
let activeTab = "chat";
function showTab(name) {
  activeTab = name;
  document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("active", t.dataset.tab === name));
  ["chat", "dashboard", "ticket", "eval"].forEach((t) => ($("tab-" + t).hidden = t !== name));
  if (name === "dashboard") loadDashboard();
  if (name === "eval") loadEvaluation();
}
document.querySelectorAll(".tab").forEach((tab) => (tab.onclick = () => showTab(tab.dataset.tab)));

// ---------- chat ----------
let pollTimer = null;
const log = $("chat-log");

function addMessage(kind, text) {
  const div = document.createElement("div");
  div.className = kind === "steps" ? "steps" : `msg ${kind}`;
  if (kind === "steps") div.innerHTML = text; else div.textContent = text;
  log.appendChild(div);
  log.scrollTop = log.scrollHeight;
  return div;
}

function resetChat() {
  clearInterval(pollTimer);
  log.innerHTML = "";
  addMessage("bot", "Hi! I'm ShopAssist. I can check orders, explain policies, and handle returns, refunds, replacements and cancellations.");
}

function watchTicket(ticketId) {  // when a ticket is waiting, poll until support decides, then tell the customer
  clearInterval(pollTimer);
  pollTimer = setInterval(async () => {
    const ticket = await api(`/api/tickets/${ticketId}/status`);
    if (ticket.status !== "AWAITING_APPROVAL") {
      clearInterval(pollTimer);
      addMessage("bot", ticket.resolution || `Your ticket is now ${ticket.status}.`);
    }
  }, 2000);
}

async function sendMessage(text) {
  text = (text ?? $("message").value).trim();
  if (!text) return;
  $("message").value = "";
  $("error").hidden = true;
  addMessage("user", text);
  const typing = addMessage("bot", "Working on it...");
  $("send").disabled = true;
  try {
    const reply = await api("/api/chat", post({ customer_id: $("customer").value, message: text }, { "X-Session-Id": sessionId }));
    typing.textContent = reply.response;
    const parts = [];
    if (reply.steps.length) parts.push(esc(reply.steps.join(" → ")));
    if (reply.ticket_id) parts.push(`<a data-ticket="${esc(reply.ticket_id)}">Open ${esc(reply.ticket_id)}</a>`);
    if (parts.length) addMessage("steps", parts.join(" · "));
    if (reply.waiting && reply.ticket_id) watchTicket(reply.ticket_id);
  } catch (error) {
    typing.remove();
    $("error").textContent = error.message;
    $("error").hidden = false;
  } finally {
    $("send").disabled = false;
  }
}

log.addEventListener("click", (event) => {
  if (event.target.dataset.ticket) openTicket(event.target.dataset.ticket);
});
$("send").onclick = () => sendMessage();
$("message").onkeydown = (event) => { if (event.key === "Enter") sendMessage(); };
$("new-chat").onclick = () => { sessionId = newSession(); resetChat(); showTab("chat"); };
$("examples").onclick = (event) => { if (event.target.tagName === "LI") { showTab("chat"); sendMessage(event.target.textContent); } };
document.querySelectorAll("[data-fail]").forEach((button) => (button.onclick = async () => {
  const result = await api(`/api/demo/fail-next?times=${button.dataset.fail}`, { method: "POST" });
  $("fail-msg").textContent = `The next ${result.failures_queued} execution(s) will fail.`;
}));

// ---------- dashboard ----------
async function loadDashboard() {
  const data = await api(`/api/tickets?status=${encodeURIComponent($("status-filter").value)}&q=${encodeURIComponent($("search").value)}`);
  const waiting = data.counts.AWAITING_APPROVAL || 0;
  $("counts").innerHTML =
    `<div class="chip"><b>${data.total}</b>Total</div><div class="chip" style="border-color:#f59e0b"><b>${waiting}</b>Awaiting approval</div>` +
    Object.entries(data.counts).filter(([k]) => k !== "AWAITING_APPROVAL")
      .map(([k, v]) => `<div class="chip"><b>${v}</b>${esc(k.replaceAll("_", " "))}</div>`).join("");
  $("ticket-rows").innerHTML = data.tickets.map((t) => `
    <tr class="clickable ${t.status === "AWAITING_APPROVAL" ? "hot" : ""}" data-ticket="${esc(t.ticket_id)}">
      <td>${esc(t.ticket_id)}</td><td>${esc(t.customer_id)}</td><td>${esc(t.order_id)}</td><td>${esc(t.category)}</td>
      <td>${esc(t.priority)}</td><td>${badge(t.status)}</td><td>${esc(t.created_at.replace("T", " "))}</td></tr>`).join("");
  $("no-tickets").hidden = data.tickets.length > 0;
}
$("ticket-rows").onclick = (event) => {
  const row = event.target.closest("tr");
  if (row) openTicket(row.dataset.ticket);
};
$("search").oninput = loadDashboard;
$("status-filter").onchange = loadDashboard;
setInterval(() => { if (activeTab === "dashboard") loadDashboard(); }, 4000);

// ---------- ticket details + live agent activity ----------
let currentTicket = null, stream = null, reloadTimer = null;
const ICON = { started: "▶", completed: "✔", tool_ok: "🔧✔", tool_failed: "✖", failed: "✖", waiting: "⏸", decided: "✔", info: "•" };

async function openTicket(ticketId) {
  currentTicket = ticketId;
  if (stream) stream.close();
  $("monitor").innerHTML = "";
  showTab("ticket");
  await loadTicket(true);
}

async function loadTicket(startStream = false) {
  if (!currentTicket) return;
  try {
    const t = await api(`/api/tickets/${currentTicket}`);
    const order = t.findings.order || {}, policy = t.findings.policy || {};
    $("ticket-empty").hidden = true;
    $("ticket-view").hidden = false;
    $("ticket-title").innerHTML = `${esc(t.ticket_id)} ${badge(t.status)}`;
    $("ticket-info").innerHTML = kv({
      Customer: t.customer_id, Order: `${t.order_id} (${order.product_name || ""})`, Category: t.category, Priority: t.priority,
      "Requested action": t.requested_action, Complaint: t.description, Created: t.created_at, Outcome: t.resolution || "-",
    });
    $("ticket-findings").innerHTML =
      `<b>Order Agent</b><div class="kv">${kv({ Status: order.order_status, Tracking: order.tracking_status, Amount: order.amount })}</div><br>` +
      `<b>Policy Agent</b><div class="kv">${kv({ Eligible: policy.eligible, Reason: policy.reason, "Needs approval": policy.requires_approval })}</div><br>` +
      `<b>Ticket Agent</b><div class="kv">${kv({ Summary: `${t.priority} priority ${t.category} for ${t.order_id}`, Proposal: `Execute a simulated ${t.requested_action}` })}</div>`;

    $("approval").innerHTML = t.status === "AWAITING_APPROVAL"
      ? `<p>Proposal: execute a simulated <b>${esc(t.requested_action)}</b> on ${esc(t.order_id)}.</p>
         <input type="text" id="reason" placeholder="Reason (required to reject)" style="width:100%;margin-bottom:8px">
         <div class="ask-row"><button class="good" data-decision="approve">Approve</button><button class="bad" data-decision="reject">Reject</button></div>
         <p id="approval-error" class="error"></p>`
      : `<p class="muted">No decision pending. Status: ${esc(t.status)}</p>`;

    const events = await api(`/api/tickets/${currentTicket}/events`);
    $("timeline").innerHTML = events.map((e) =>
      `<div><b>${esc(e.status)}</b> <span class="muted">${esc(e.created_at.replace("T", " "))}</span><br>${esc(e.message)}</div>`).join("");

    if (startStream) startMonitor(t.thread_id);
  } catch (error) {
    $("ticket-empty").hidden = false;
    $("ticket-empty").textContent = error.message;
    $("ticket-view").hidden = true;
  }
}

function startMonitor(threadId) {  // real LangGraph events, pushed by the server (SSE)
  stream = new EventSource(`/api/workflows/${threadId}/stream`);
  stream.onmessage = (message) => {
    const e = JSON.parse(message.data);
    $("monitor").insertAdjacentHTML("beforeend",
      `<div class="${esc(e.status)}">${ICON[e.status] || ""} <b>${esc(e.node)}</b> ${esc(e.status)} ${esc(e.message)}</div>`);
    $("monitor").scrollTop = $("monitor").scrollHeight;
    clearTimeout(reloadTimer);
    reloadTimer = setTimeout(() => loadTicket(false), 300);  // refresh the details when something happens
  };
}

$("approval").onclick = async (event) => {
  const decision = event.target.dataset.decision;
  if (!decision) return;
  const reason = $("reason").value;
  if (decision === "reject" && !reason.trim()) { $("approval-error").textContent = "Please give a reason for rejecting."; return; }
  event.target.parentElement.querySelectorAll("button").forEach((b) => (b.disabled = true));
  try {
    await api(`/api/tickets/${currentTicket}/${decision}`, post({ reason }, { "X-Role": "support" }));
  } catch (error) {
    alert(error.message);
  }
  loadTicket(false);
};

// ---------- evaluation ----------
function renderEvaluation(data) {
  const saved = (data.saved || {}).workflow_evaluation;
  $("scenario-count").textContent = `the ${data.scenarios}`;
  if (!saved) { $("eval-results").innerHTML = '<p class="muted">No saved results yet. Click "Run evaluation".</p>'; return; }

  const rows = saved.results.map((r) => `<tr><td>${esc(r.classifier)}</td><td>${percent(r.intent_accuracy)}</td>
    <td>${percent(r.outcome_accuracy)}</td><td>${percent(r.safety)}</td><td><b>${percent(r.pass_rate)}</b></td>
    <td>${r.avg_latency_s === null ? "n/a" : r.avg_latency_s.toFixed(2) + "s"}</td><td>${r.errors}</td></tr>`).join("");

  const first = saved.results[0];
  const categories = Object.entries(first.by_category).map(([name, value]) =>
    `<tr><td>${esc(name)}</td><td>${percent(value)}</td><td><div class="bar"><div style="width:${Math.round(value * 100)}%"></div></div></td></tr>`).join("");

  const failures = saved.results.flatMap((r) => r.failures.map((f) => `
    <div class="failure"><b>[${esc(r.classifier)}] ${esc(f.id)}</b> (${esc(f.category)}): ${esc(f.question)}<br>
    <span class="muted">expected: ${esc(f.expected)}<br>got: ${esc(f.got)}</span></div>`)).join("");

  $("eval-results").innerHTML = `
    <div class="card"><h3>Results (${saved.scenarios} scenarios)</h3>
      <table><thead><tr><th>Classifier</th><th>Intent</th><th>Outcome</th><th>Safety</th><th>Pass rate</th><th>Latency</th><th>Errors</th></tr></thead><tbody>${rows}</tbody></table></div>
    <div class="card"><h3>Pass rate by category (${esc(first.classifier)})</h3>
      <table><tbody>${categories}</tbody></table></div>
    ${failures ? `<div class="card"><h3>Failed scenarios</h3>${failures}</div>` : ""}`;
}

async function loadEvaluation() {
  renderEvaluation(await api("/api/evaluation"));
}

$("eval-btn").onclick = async () => {
  $("eval-btn").disabled = true;
  $("eval-status").textContent = "Running...";
  try {
    renderEvaluation(await api("/api/evaluation/run", { method: "POST" }));
    $("eval-status").textContent = "Done.";
  } catch (error) {
    $("eval-status").textContent = error.message;
  } finally {
    $("eval-btn").disabled = false;
  }
};

// ---------- start ----------
api("/api/customers").then((list) => {
  $("customer").innerHTML = list.map((c) => `<option value="${esc(c.customer_id)}">${esc(c.name)} (${esc(c.customer_id)})</option>`).join("");
});
resetChat();
