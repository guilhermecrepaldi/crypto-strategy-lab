"use strict";

let csrfToken = "";
let refreshTimer = null;

const byId = (id) => document.getElementById(id);
const text = (id, value) => { byId(id).textContent = value === null || value === undefined ? "—" : String(value); };

function showNotice(message, error = false) {
  const notice = byId("notice");
  notice.textContent = message;
  notice.classList.remove("hidden", "error");
  if (error) notice.classList.add("error");
  window.setTimeout(() => notice.classList.add("hidden"), 6000);
}

async function api(path, options = {}) {
  const request = {credentials: "same-origin", ...options};
  request.headers = {Accept: "application/json", ...(options.headers || {})};
  if (request.method && request.method !== "GET") request.headers["X-Operator-CSRF"] = csrfToken;
  const response = await fetch(path, request);
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || `HTTP_${response.status}`);
  return payload;
}

function setPairs(containerId, pairs) {
  const container = byId(containerId);
  container.replaceChildren();
  Object.entries(pairs).forEach(([label, value]) => {
    const row = document.createElement("div");
    const term = document.createElement("dt");
    const detail = document.createElement("dd");
    term.textContent = label;
    detail.textContent = value === null || value === undefined ? "—" : String(value);
    row.append(term, detail);
    container.append(row);
  });
}

function renderQueues(queues) {
  const grid = byId("queue-grid");
  grid.replaceChildren();
  queues.forEach((queue) => {
    const card = document.createElement("article");
    card.className = `queue-card ${queue.type === "ACTIVE_RESERVE" ? "active-reserve" : "operating"}`;
    const head = document.createElement("div"); head.className = "queue-head";
    const identity = document.createElement("div");
    const name = document.createElement("h4"); name.textContent = queue.queue_id;
    const type = document.createElement("span"); type.className = "queue-type"; type.textContent = queue.type;
    identity.append(name, type);
    const state = document.createElement("span"); state.className = "queue-state"; state.textContent = queue.status;
    head.append(identity, state);
    const values = document.createElement("dl"); values.className = "kv-list compact";
    [["Range", queue.range_low ? `${queue.range_low} → ${queue.range_high}` : "Not allocated"], ["Capital", `${queue.capital_assigned} USDT`], ["Position", queue.position_size], ["Hold age", `${queue.hold_age_seconds}s`], ["Fill", `${queue.fill_percent}%`], ["Next", queue.next_action]].forEach(([label, value]) => {
      const row = document.createElement("div"); const dt = document.createElement("dt"); const dd = document.createElement("dd");
      dt.textContent = label; dd.textContent = value; row.append(dt, dd); values.append(row);
    });
    const footer = document.createElement("div"); footer.className = "queue-footer";
    const pnl = document.createElement("span"); pnl.textContent = `PnL ${queue.realized_pnl}`;
    const lock = document.createElement("span"); lock.className = "lock-normal"; lock.textContent = queue.lock_state;
    footer.append(pnl, lock); card.append(head, values, footer); grid.append(card);
  });
}

function renderChecks(containerId, values) {
  const container = byId(containerId); container.replaceChildren();
  Object.entries(values || {}).forEach(([key, value]) => {
    if (key === "filters" || key === "balances" || typeof value === "object") return;
    const row = document.createElement("div"); row.className = "check";
    const label = document.createElement("span"); label.textContent = key.replaceAll("_", " ").toUpperCase();
    const result = document.createElement("strong"); result.textContent = String(value);
    row.append(label, result); container.append(row);
  });
}

function renderOrders(orders) {
  const body = byId("orders-body"); body.replaceChildren();
  if (!orders.length) {
    const row = document.createElement("tr"); row.className = "empty-row";
    const cell = document.createElement("td"); cell.colSpan = 9; cell.textContent = "No open orders · SHADOW does not submit exchange orders";
    row.append(cell); body.append(row); return;
  }
  const fields = ["timestamp", "queue", "side", "type", "price", "quantity", "filled", "status", "exchange_order_id"];
  orders.forEach((order) => { const row = document.createElement("tr"); fields.forEach((field) => { const cell = document.createElement("td"); cell.textContent = order[field] ?? "—"; row.append(cell); }); body.append(row); });
}

function renderEvents(events) {
  const list = byId("event-list"); list.replaceChildren();
  events.forEach((event) => {
    const row = document.createElement("div"); row.className = "event";
    const timestamp = document.createElement("time"); timestamp.textContent = new Date(event.timestamp).toLocaleString();
    const name = document.createElement("strong"); name.textContent = event.event;
    const toggle = document.createElement("button"); toggle.type = "button"; toggle.textContent = "DETAILS";
    const detail = document.createElement("pre"); detail.className = "event-details hidden"; detail.textContent = JSON.stringify(event.details, null, 2);
    toggle.addEventListener("click", () => detail.classList.toggle("hidden"));
    row.append(timestamp, name, toggle, detail); list.append(row);
  });
}

function drawChart(points) {
  const canvas = byId("capital-chart");
  const ratio = window.devicePixelRatio || 1;
  const width = canvas.clientWidth || 700; const height = 190;
  canvas.width = width * ratio; canvas.height = height * ratio;
  const ctx = canvas.getContext("2d"); ctx.scale(ratio, ratio); ctx.clearRect(0, 0, width, height);
  ctx.strokeStyle = "#e6ebe8"; ctx.lineWidth = 1;
  [25, 75, 125, 175].forEach((y) => { ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(width, y); ctx.stroke(); });
  const data = points.length ? points : [{total_equity: 110, operating_bank: 100, reserve: 10}];
  const values = data.flatMap((point) => [Number(point.total_equity), Number(point.operating_bank), Number(point.reserve)]);
  const min = Math.min(...values, 0); const max = Math.max(...values, 1); const range = max - min || 1;
  [["total_equity", "#14211c"], ["operating_bank", "#26966e"], ["reserve", "#c7973d"]].forEach(([field, color]) => {
    ctx.strokeStyle = color; ctx.lineWidth = 2; ctx.beginPath();
    data.forEach((point, index) => { const x = data.length === 1 ? width / 2 : (index / (data.length - 1)) * width; const y = 175 - ((Number(point[field]) - min) / range) * 150; if (index === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y); });
    ctx.stroke();
  });
}

function renderCredential(connection) {
  const credential = connection.credentials;
  text("credential-badge", credential.status);
  text("credential-meta", credential.secret_configured ? `Secret configured ✓ · ${credential.api_key_masked || "key protected"} · ${credential.vault}` : "Secret não configurada.");
  if (connection.last_test) renderChecks("connection-results", connection.last_test);
}

function render(data) {
  const status = data.status; const capital = data.capital; const health = data.machine_health;
  text("bot-status", status.bot_status); text("binance-status", status.binance); text("mode-status", status.mode); text("model-status", status.model_id);
  text("instance-id", status.operator_instance_id); text("strategy-name", status.strategy);
  text("strategy-meta", `${status.model_id} · ${status.model_hash.slice(0, 12)}… · ${status.pair}`);
  text("total-equity", capital.total_equity); text("operating-bank", capital.current_operating_bank); text("reserve-total", capital.recovery_reserve);
  text("reserve-ratio", `${Number(capital.reserve_ratio) * 100}% of operating`); text("realized-pnl", capital.realized_pnl);
  text("motor-uptime", `${health.motor_uptime_percent}%`); text("capital-uptime", `capital-weighted ${health.capital_weighted_uptime_percent}%`);
  renderQueues(data.queues); renderCredential(data.connection);
  text("market-source", data.market.source);
  setPairs("market-list", {Bid: data.market.bid, Ask: data.market.ask, Spread: data.market.spread, "Last trade": data.market.last_trade, "Trades/sec": data.market.trades_per_second, "REST latency": data.market.connection_latency_ms ? `${data.market.connection_latency_ms} ms` : "—", Heartbeat: data.market.last_rest_heartbeat ? new Date(data.market.last_rest_heartbeat).toLocaleTimeString() : "—"});
  const productive = Number(health.productive_capital_percent); text("productive-percent", `${productive}%`); byId("productive-donut").style.setProperty("--value", `${productive * 3.6}deg`);
  text("health-badge", status.bot_status === "RUNNING" ? "RUNNING" : "IDLE");
  setPairs("health-list", {"Capital weighted": `${health.capital_weighted_uptime_percent}%`, Productive: `${productive}%`, Locked: `${health.locked_capital_percent}%`, Idle: `${health.idle_capital_percent}%`, "Active queues": health.active_queues, "Zero-cycle days": health.zero_cycle_days});
  setPairs("reserve-list", {Current: `${capital.recovery_reserve} USDT`, Target: `${capital.target_reserve} USDT`, Core: `${capital.core_reserve} USDT`, Active: `${capital.active_reserve} USDT`, "Funding today": capital.funding_today, "Release spend today": capital.release_spend_today, "Recovery ratio": capital.recovery_ratio});
  setPairs("strategy-list", {Model: data.strategy.active_model, Hash: data.strategy.model_hash, Status: data.strategy.model_status, "Capital mode": data.strategy.capital_mode, "Reserve funding": data.strategy.reserve_funding_rate, "Max lock": `${data.strategy.max_lock_hours}h`, "Max queues": data.strategy.max_queues, Pair: data.strategy.pair, "Execution profile": data.strategy.execution_profile, "Trading enabled": "NO", "Owner authorized": "NO"});
  renderOrders(data.orders.open_orders); renderEvents(data.events); drawChart(data.charts);
  byId("play-button").disabled = status.bot_status === "RUNNING" || status.reconciliation === "REQUIRED";
  byId("stop-button").disabled = status.bot_status !== "RUNNING";
  if (status.reconciliation === "REQUIRED") showNotice("Recovery state found. Reconciliation is required before PLAY.", true);
}

async function refresh() { try { render(await api("/api/dashboard")); } catch (error) { showNotice(error.message, true); } }

async function initialize() {
  try {
    const boot = await api("/api/bootstrap"); csrfToken = boot.csrf_token; await refresh();
    refreshTimer = window.setInterval(refresh, 5000);
  } catch (error) { showNotice(error.message, true); }
}

byId("show-secret").addEventListener("click", () => { const field = byId("api-secret"); const showing = field.type === "text"; field.type = showing ? "password" : "text"; byId("show-secret").textContent = showing ? "Show" : "Hide"; });
byId("credential-form").addEventListener("submit", async (event) => { event.preventDefault(); const apiKey = byId("api-key"); const secret = byId("api-secret"); try { await api("/api/binance/configure", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({api_key: apiKey.value, api_secret: secret.value})}); apiKey.value = ""; secret.value = ""; secret.type = "password"; byId("show-secret").textContent = "Show"; showNotice("Credentials protected locally with Windows DPAPI."); await refresh(); } catch (error) { secret.value = ""; showNotice(error.message, true); } });
byId("test-connection").addEventListener("click", async () => { try { renderChecks("connection-results", await api("/api/binance/test", {method: "POST"})); showNotice("Connection test completed. No order endpoint was called."); await refresh(); } catch (error) { showNotice(error.message, true); } });
byId("disconnect").addEventListener("click", async () => { try { await api("/api/binance/disconnect", {method: "POST"}); await refresh(); } catch (error) { showNotice(error.message, true); } });
byId("delete-credentials").addEventListener("click", async () => { try { await api("/api/binance/credentials", {method: "DELETE"}); byId("api-key").value = ""; byId("api-secret").value = ""; showNotice("Local credentials deleted."); await refresh(); } catch (error) { showNotice(error.message, true); } });
byId("play-button").addEventListener("click", async () => { try { const preflight = await api("/api/preflight"); renderChecks("preflight-list", preflight.checks); byId("confirm-play").disabled = preflight.verdict !== "PASS"; byId("play-dialog").showModal(); } catch (error) { showNotice(error.message, true); } });
byId("confirm-play").addEventListener("click", async (event) => { event.preventDefault(); try { await api("/api/operator/play", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({mode: "SHADOW"})}); byId("play-dialog").close(); showNotice("Shadow engine started. Real order transport is absent."); await refresh(); } catch (error) { showNotice(error.message, true); } });
byId("stop-button").addEventListener("click", async () => { try { await api("/api/operator/stop", {method: "POST"}); showNotice("STOPPED_SAFE · state preserved · new entries disabled."); await refresh(); } catch (error) { showNotice(error.message, true); } });
byId("emergency-button").addEventListener("click", () => { byId("emergency-confirmation").value = ""; byId("emergency-dialog").showModal(); });
byId("confirm-emergency").addEventListener("click", async (event) => { event.preventDefault(); try { await api("/api/operator/emergency-stop", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({confirmation: byId("emergency-confirmation").value})}); byId("emergency-confirmation").value = ""; byId("emergency-dialog").close(); showNotice("Emergency policy applied. Holdings preserved; no liquidation was invented."); await refresh(); } catch (error) { showNotice(error.message, true); } });
byId("assistant-form").addEventListener("submit", async (event) => { event.preventDefault(); try { const question = byId("assistant-question"); const result = await api("/api/assistant", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({question: question.value})}); text("assistant-answer", result.answer); question.value = ""; } catch (error) { showNotice(error.message, true); } });
window.addEventListener("resize", () => refreshTimer && refresh());

initialize();
