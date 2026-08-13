const REPORT_MENU = [
    ["cdr", "CDR", "Answered call detail records from the MagnusBilling OCS"],
    ["cdr-failed", "CDR Failed", "Failed and unanswered attempts from the MagnusBilling OCS"],
    ["summary-per-day", "Summary per Day", "Daily answered and failed call totals from the OCS"],
    ["summary-day-user", "Summary Day User", "Daily call totals grouped by customer"],
    ["summary-day-trunk", "Summary Day Trunk", "Daily call totals grouped by trunk"],
    ["summary-day-agent", "Summary Day Agent", "Daily call totals grouped by reseller or agent"],
    ["summary-per-month", "Summary per Month", "Monthly answered and failed call totals from the OCS"],
    ["summary-month-user", "Summary Month User", "Monthly call totals grouped by customer"],
    ["summary-month-trunk", "Summary Month Trunk", "Monthly call totals grouped by trunk"],
    ["summary-per-user", "Summary per User", "Lifetime call totals grouped by customer"],
    ["summary-per-trunk", "Summary per Trunk", "Lifetime call totals grouped by trunk"],
    ["call-archive", "Call Archive", "Archived call detail records from the MagnusBilling OCS"],
    ["summary-month-did", "Summary Month DID", "Monthly inbound totals grouped by DID"],
];

const titles = {
    dashboard: ["Dashboard", "Customers, wallets, SIP devices, and real-time charging"],
    sip: ["SIP devices", "Live registration and call status from the MagnusBilling OCS and Asterisk"],
    customers: ["Customers", "CRM in SmartVoice, balances in the MagnusBilling OCS"],
    products: ["Products", "Catalog in BSS, rate plans charged by the OCS"],
    payments: ["Payments", "Collect in BSS, apply credit through OCS refill"],
    resellers: ["Resellers", "Agent accounts and downstream customer wallets"],
    usage: ["OCS usage", "Live calls and CDRs from the online charging engine"],
    invoices: ["Invoices", "BSS invoices rolled up from OCS call charges"],
    "blocked-ip": ["Blocked IP", "Fail2ban and MagnusBilling firewall blocks, with country and reason"],
};
REPORT_MENU.forEach(([slug, title, subtitle]) => {
    titles[slug] = [title, subtitle];
});

const reportState = Object.fromEntries(REPORT_MENU.map(([slug]) => [slug, ""]));
reportState["blocked-ip"] = "";

let lastCreated = null;
let creatingView = null;
let editingId = null;
let bulkOpen = false;
let selectedCustomerIds = new Set();

const BASE = window.location.pathname.indexOf("/smartvoice") === 0 ? "/smartvoice" : "";

async function api(path, options) {
    const response = await fetch(BASE + path, Object.assign({ credentials: "same-origin", headers: { "Content-Type": "application/json" } }, options));
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
        const detail = data.detail;
        const message = typeof detail === "string" ? detail : (detail ? JSON.stringify(detail) : response.statusText);
        throw new Error(message);
    }
    return data;
}

function money(value) {
    return Number(value || 0).toFixed(4);
}

function setOcsPill(health) {
    const el = document.getElementById("ocs-pill");
    if (!health) return;
    el.textContent = health.ok ? `OCS ${health.mode}: ${health.engine}` : `OCS down: ${health.detail || "unreachable"}`;
    el.className = "pill " + (health.ok ? "ok" : "bad");
}

async function login(event) {
    event.preventDefault();
    const username = document.getElementById("username").value.trim();
    const password = document.getElementById("password").value;
    document.getElementById("login-err").textContent = "";
    try {
        await api("/api/login", { method: "POST", body: JSON.stringify({ username: username, password: password }) });
        await boot();
    } catch (err) {
        document.getElementById("login-err").textContent = err.message || "Sign-in failed";
    }
    return false;
}

async function logout() {
    await api("/api/logout", { method: "POST", body: "{}" });
    document.getElementById("app").classList.add("hidden");
    document.getElementById("login").classList.remove("hidden");
}

async function boot() {
    try {
        const session = await api("/api/session");
        document.getElementById("login").classList.add("hidden");
        document.getElementById("app").classList.remove("hidden");
        setOcsPill(session.ocs);
        await show("dashboard");
    } catch (err) {
        document.getElementById("app").classList.add("hidden");
        document.getElementById("login").classList.remove("hidden");
        const box = document.getElementById("login-err");
        if (box && err && err.message && err.message !== "Sign in required") {
            box.textContent = err.message;
        }
    }
}

let refreshTimer = null;

async function show(name) {
    if (refreshTimer) {
        clearInterval(refreshTimer);
        refreshTimer = null;
    }
    document.querySelectorAll("[data-view]").forEach((btn) => btn.classList.toggle("active", btn.dataset.view === name));
    document.querySelectorAll(".nav-group").forEach((group) => {
        if (group.querySelector(`[data-view="${name}"]`)) group.classList.add("open");
    });
    document.getElementById("title").textContent = titles[name][0];
    document.getElementById("subtitle").textContent = titles[name][1];
    const render = views[name];
    if (render) await render();
    if (name === "sip") {
        refreshTimer = setInterval(() => {
            views.sip().catch(() => {});
        }, 5000);
    }
}

document.querySelectorAll("[data-view]").forEach((btn) => btn.addEventListener("click", () => show(btn.dataset.view)));
document.querySelectorAll("[data-group-toggle]").forEach((btn) => {
    btn.addEventListener("click", () => btn.closest(".nav-group").classList.toggle("open"));
});

const views = {
    async dashboard() {
        const data = await api("/api/dashboard");
        setOcsPill(data.ocs);
        document.getElementById("view").innerHTML = `
            <div class="grid">
                <div class="card"><h3>Customers</h3><div class="n">${data.customers}</div></div>
                <div class="card"><h3>Resellers</h3><div class="n">${data.resellers}</div></div>
                <div class="card"><h3>Prepaid / postpaid</h3><div class="n">${data.prepaid} / ${data.postpaid}</div></div>
                <div class="card"><h3>OCS wallet</h3><div class="n">${money(data.ocs_wallet)}</div></div>
                <div class="card"><h3>Billed from CDRs</h3><div class="n">${money(data.usage_billed)}</div></div>
                <div class="card"><h3>Live calls</h3><div class="n">${data.live_calls}</div></div>
                <div class="card"><h3>SIP registered</h3><div class="n">${data.sip_registered || 0} / ${data.sip_devices || 0}</div></div>
                <div class="card"><h3>SIP offline</h3><div class="n">${data.sip_offline || 0}</div></div>
            </div>
            <div class="card"><h3>SIP devices</h3>${sipTable(data.sip || [])}</div>
            <div class="card"><h3>Recent OCS charges</h3>${table(["User", "Destination", "Seconds", "Charged"], data.recent_calls.map((r) => [r.idUserusername || r.id_user, r.calledstation, r.sessiontime, money(r.sessionbill)]))}</div>
        `;
    },
    async customers() {
        const data = await api("/api/customers");
        const creating = creatingView === "customers";
        const editing = !creating && editingId != null;
        const record = editing ? (data.rows || []).find((row) => String(row.id) === String(editingId)) : null;
        const selected = (data.rows || []).filter((row) => selectedCustomerIds.has(Number(row.id)));
        document.getElementById("view").innerHTML = `
            ${creating ? userCreateForm("createCustomer", "Create customer", data, { requireCompany: false, postpaidLocked: false, kind: "Customer" }) : ""}
            ${editing && record ? userCreateForm("saveCustomer", "Save customer", data, { requireCompany: false, postpaidLocked: false, kind: "Customer", record }) : ""}
            ${editing && !record ? `<div class="card"><p class="err">Customer not found.</p><button class="btn ghost" type="button" onclick="cancelCreate()">Back to list</button></div>` : ""}
            ${!creating && !editing && lastCreated && lastCreated.kind === "Customer" ? createdRecordCard() : ""}
            ${!creating && !editing && bulkOpen ? bulkCustomerForm(data, selected) : ""}
            ${creating || editing ? "" : customerListCard(data)}
        `;
        restoreCustomerSelection();
    },
    async products() {
        const data = await api("/api/products");
        document.getElementById("view").innerHTML = `
            <form class="form card" onsubmit="return createProduct(event)">
                <label>Name <input name="name" required></label>
                <label>Description <input name="description"></label>
                <label>Monthly fee <input name="monthly_fee" type="number" step="0.01" value="0"></label>
                <label>Included minutes <input name="included_minutes" type="number" value="0"></label>
                <label>Kind <select name="kind"><option value="prepaid">Prepaid</option><option value="postpaid">Postpaid</option></select></label>
                <button class="btn" type="submit">Add product + OCS plan</button>
            </form>
            <div class="card"><h3>BSS catalog</h3>${table(["Name", "Kind", "Fee", "Minutes", "OCS plan"], data.catalog.map((r) => [r.name, r.kind, money(r.monthly_fee), r.included_minutes, (r.ocs_plan && r.ocs_plan.name) || r.ocs_plan_id || ""]))}</div>
            <div class="card"><h3>OCS plans</h3>${table(["ID", "Name", "Signup credit"], data.ocs_plans.map((r) => [r.id, r.name, r.ini_credit]))}</div>
        `;
    },
    async payments() {
        const data = await api("/api/payments");
        document.getElementById("view").innerHTML = `
            <form class="form card" onsubmit="return createPayment(event)">
                <label>OCS user ID <input name="ocs_user_id" type="number" required></label>
                <label>Amount <input name="amount" type="number" step="0.0001" required></label>
                <label>Method <select name="method"><option>cash</option><option>bank</option><option>card</option></select></label>
                <label>Reference <input name="reference"></label>
                <button class="btn" type="submit">Take payment</button>
            </form>
            <div class="card"><h3>BSS ledger</h3>${table(["ID", "User", "Amount", "Method", "OCS refill"], data.bss.map((r) => [r.id, r.username, money(r.amount), r.method, r.ocs_refill_id || ""]))}</div>
            <div class="card"><h3>OCS refills</h3>${table(["ID", "User", "Credit", "Description"], data.ocs.map((r) => [r.id, r.idUserusername || r.id_user, money(r.credit), r.description || ""]))}</div>
        `;
    },
    async resellers() {
        const data = await api("/api/resellers");
        const creating = creatingView === "resellers";
        document.getElementById("view").innerHTML = `
            ${creating ? userCreateForm("createReseller", "Create reseller", data, { requireCompany: true, postpaidLocked: true, kind: "Reseller" }) : ""}
            ${!creating && lastCreated && lastCreated.kind === "Reseller" ? createdRecordCard() : ""}
            ${creating ? "" : `<div class="card">
                <div class="toolbar">
                    <h3>Resellers</h3>
                    <button class="btn" type="button" onclick="startCreate('resellers')">New reseller</button>
                </div>
                ${table(["ID", "Username", "Company", "Customers", "Downstream wallet", "Own credit"], data.rows.map((r) => [r.id, r.username, r.company_name, r.customers, money(r.customer_wallet), money(r.credit)]))}
            </div>`}
        `;
    },
    async sip() {
        const data = await api("/api/sip-devices");
        setOcsPill(data.ocs);
        const counts = data.counts || {};
        document.getElementById("view").innerHTML = `
            <div class="grid">
                <div class="card"><h3>Devices</h3><div class="n">${counts.total || 0}</div></div>
                <div class="card"><h3>Registered</h3><div class="n">${counts.registered || 0}</div></div>
                <div class="card"><h3>In call</h3><div class="n">${counts.in_call || 0}</div></div>
                <div class="card"><h3>Offline</h3><div class="n">${counts.offline || 0}</div></div>
                <div class="card"><h3>Unreachable</h3><div class="n">${counts.unreachable || 0}</div></div>
                <div class="card"><h3>Disabled</h3><div class="n">${counts.disabled || 0}</div></div>
            </div>
            <div class="card">
                <div class="toolbar">
                    <h3>Current SIP devices</h3>
                    <span class="muted">Updated ${esc(data.as_of || "")} · auto-refresh 5s · ${esc((data.ami && data.ami.detail) || "")}</span>
                </div>
                ${sipTable(data.rows || [])}
            </div>
        `;
    },
    async usage() {
        const data = await api("/api/usage");
        setOcsPill(data.ocs);
        document.getElementById("view").innerHTML = `
            <div class="card"><h3>Live OCS sessions</h3>${table(["Channel / user", "Destination", "Status"], (data.live || []).map((r) => [r.idUserusername || r.sip_account || r.id, r.ndiscado || r.calledstation || "", r.status || "active"]))}</div>
            <div class="card"><h3>Charged CDRs</h3>${table(["User", "Destination", "Seconds", "Charge", "Started"], data.cdrs.map((r) => [r.idUserusername || r.id_user, r.calledstation, r.sessiontime, money(r.sessionbill), r.starttime]))}</div>
        `;
    },
    async invoices() {
        const data = await api("/api/invoices");
        document.getElementById("view").innerHTML = `
            <form class="form card" onsubmit="return createInvoice(event)">
                <label>OCS user ID <input name="ocs_user_id" type="number" required></label>
                <label>Period <input name="period" placeholder="2026-08" required></label>
                <button class="btn" type="submit">Generate from OCS CDRs</button>
            </form>
            <div class="card">${table(["ID", "User", "Period", "Amount", "Status"], data.rows.map((r) => [r.id, r.username, r.period, money(r.amount), r.status]))}</div>
        `;
    },
    async ["blocked-ip"]() {
        const q = reportState["blocked-ip"] || "";
        const data = await api("/api/security/blocked-ip" + (q ? `?${q}` : ""));
        setOcsPill(data.ocs);
        const counts = data.counts || {};
        const countryCards = (data.by_country || []).slice(0, 4).map((item) => `<div class="card"><h3>${esc(item.label)}</h3><div class="n">${item.count}</div></div>`).join("");
        document.getElementById("view").innerHTML = `
            <form class="form card" onsubmit="return applyBlockedFilter(event)">
                <label>Search <input name="q" value="${esc(new URLSearchParams(q).get("q") || "")}" placeholder="IP, country, reason"></label>
                <button class="btn" type="submit">Filter</button>
            </form>
            <div class="grid">
                <div class="card"><h3>Blocked IPs</h3><div class="n">${counts.total || 0}</div></div>
                <div class="card"><h3>Temporary</h3><div class="n">${counts.temporary || 0}</div></div>
                <div class="card"><h3>Permanent</h3><div class="n">${counts.permanent || 0}</div></div>
                ${countryCards}
            </div>
            <div class="card">
                <div class="toolbar">
                    <h3>Blocked IP</h3>
                    <span class="muted">Country and Fail2ban reason from the MagnusBilling firewall</span>
                </div>
                ${table(
                    ["IP", "Country", "Reason for block", "Jail", "Action", "Date", "Server"],
                    (data.rows || []).map((r) => [
                        `<strong>${esc(r.ip)}</strong>`,
                        `${esc(r.country)}${r.country_code ? ` (${esc(r.country_code)})` : ""}`,
                        esc(r.reason),
                        esc(r.jail),
                        `<span class="tag ${r.action_id === 1 ? "post" : ""}">${esc(r.action)}</span>`,
                        esc(r.date),
                        esc(r.server),
                    ]),
                )}
            </div>
        `;
    },
};

REPORT_MENU.forEach(([slug]) => {
    views[slug] = () => renderReport(slug);
});

function causeTag(label, failed) {
    const kind = !failed && String(label).toUpperCase() === "ANSWER" ? "ok" : "post";
    return `<span class="tag ${kind}">${esc(label || "")}</span>`;
}

function formatReportCell(col, row) {
    const value = row[col.key];
    if (col.format === "money") return money(value);
    if (col.format === "int") return String(value ?? 0);
    if (col.format === "pct") return Number(value || 0).toFixed(2);
    if (col.format === "cause") return causeTag(value, row.failed);
    return esc(value ?? "");
}

function reportFilterForm(slug) {
    const params = new URLSearchParams(reportState[slug] || "");
    return `
        <form class="form card" onsubmit="return applyReport(event, '${slug}')">
            <label>Search <input name="q" value="${esc(params.get("q") || "")}" placeholder="User, trunk, DID, destination"></label>
            <label>From <input name="date_from" type="date" value="${esc(params.get("date_from") || "")}"></label>
            <label>To <input name="date_to" type="date" value="${esc(params.get("date_to") || "")}"></label>
            <button class="btn" type="submit">Run report</button>
            <a class="btn ghost" href="${BASE}/api/reports/${slug}.csv?${reportState[slug] || ""}">Export CSV</a>
        </form>
    `;
}

async function renderReport(slug) {
    const qs = reportState[slug] ? `?${reportState[slug]}` : "";
    const data = await api("/api/reports/" + slug + qs);
    setOcsPill(data.ocs);
    const summary = data.summary || {};
    const columns = data.columns || [];
    const kind = data.kind || "";
    const causeCards = (summary.top_causes || []).map((item) => `<div class="card"><h3>${esc(item.label)}</h3><div class="n">${item.count}</div></div>`).join("");
    const rows = (data.rows || []).map((row) => columns.map((col) => formatReportCell(col, row)));
    const metricCards = kind === "summary"
        ? `<div class="card"><h3>Rows</h3><div class="n">${summary.count || 0}</div></div>
            <div class="card"><h3>Calls</h3><div class="n">${summary.calls || 0}</div></div>
            <div class="card"><h3>Failed</h3><div class="n">${summary.failed_calls || 0}</div></div>
            <div class="card"><h3>ASR</h3><div class="n">${Number(summary.asr || 0).toFixed(1)}%</div></div>
            <div class="card"><h3>Duration</h3><div class="n">${esc(summary.duration || "0:00")}</div></div>
            <div class="card"><h3>Billed</h3><div class="n">${money(summary.billed)}</div></div>`
        : `<div class="card"><h3>${kind === "cdr-failed" ? "Failed attempts" : "CDRs"}</h3><div class="n">${summary.count || 0}</div></div>
            ${kind === "cdr-failed" ? "" : `<div class="card"><h3>Talk time</h3><div class="n">${esc(summary.duration || "0:00")}</div></div>
            <div class="card"><h3>Billed</h3><div class="n">${money(summary.billed)}</div></div>
            <div class="card"><h3>Margin</h3><div class="n">${money(summary.margin)}</div></div>`}
            ${causeCards}`;
    document.getElementById("view").innerHTML = `
        ${reportFilterForm(slug)}
        <div class="grid">${metricCards}</div>
        <div class="card">
            <div class="toolbar">
                <h3>${esc(data.title || slug)}</h3>
                <span class="muted">${data.ocs_count != null ? `${data.ocs_count} in OCS` : ""}</span>
            </div>
            ${table(columns.map((col) => col.label), rows)}
        </div>
    `;
}

function applyReport(event, name) {
    event.preventDefault();
    const form = new FormData(event.target);
    const params = new URLSearchParams();
    ["q", "date_from", "date_to"].forEach((key) => {
        const value = String(form.get(key) || "").trim();
        if (value) params.set(key, value);
    });
    reportState[name] = params.toString();
    show(name);
    return false;
}

function applyBlockedFilter(event) {
    event.preventDefault();
    const value = String(new FormData(event.target).get("q") || "").trim();
    reportState["blocked-ip"] = value ? new URLSearchParams({ q: value }).toString() : "";
    show("blocked-ip");
    return false;
}

function esc(value) {
    return String(value ?? "").replace(/[&<>"']/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]));
}

function presenceLabel(presence) {
    return {
        registered: "Registered",
        in_call: "In call",
        offline: "Offline",
        unreachable: "Unreachable",
        disabled: "Disabled",
        unknown: "Unknown",
    }[presence] || presence || "Unknown";
}

function sipTable(rows) {
    return table(
        ["Device", "Customer", "Caller ID", "Status", "Contact", "Latency", "Live call", "Host"],
        rows.map((r) => [
            `<strong>${esc(r.name)}</strong>`,
            esc(r.customer),
            esc(r.callerid),
            `<span class="status ${esc(r.presence)}"><i></i>${esc(presenceLabel(r.presence))}</span><div class="muted">${esc(r.line_status || r.endpoint_state || "")}</div>`,
            esc(r.contact || "—"),
            r.rtt_ms != null && r.rtt_ms !== "" ? `${esc(r.rtt_ms)} ms` : "—",
            r.in_call ? `${esc(r.live_destination || "active")} (${esc(r.live_duration || 0)}s)` : "idle",
            esc(r.host || ""),
        ]),
    );
}

function table(headers, rows) {
    if (!rows.length) return '<p class="muted">No records yet.</p>';
    return `<table><thead><tr>${headers.map((h) => `<th>${h}</th>`).join("")}</tr></thead><tbody>${rows.map((row) => `<tr>${row.map((c) => `<td>${c ?? ""}</td>`).join("")}</tr>`).join("")}</tbody></table>`;
}

function options(items, valueKey, labelFn, selected) {
    return (items || []).map((item) => {
        const value = item[valueKey];
        const label = labelFn(item);
        const sel = String(value) === String(selected) ? " selected" : "";
        return `<option value="${esc(value)}"${sel}>${esc(label)}</option>`;
    }).join("");
}

function randomUsername() {
    const chars = "abcdefghijklmnopqrstuvwxyz0123456789";
    const buf = new Uint32Array(7);
    crypto.getRandomValues(buf);
    let out = "u";
    for (let i = 0; i < 7; i++) out += chars[buf[i] % chars.length];
    return out;
}

function randomPassword() {
    const chars = "ABCDEFGHJKLMNPQRSTUWXYZabcdefghijkmnpqrstuvwxyz123456789";
    const buf = new Uint32Array(10);
    crypto.getRandomValues(buf);
    let out = "";
    for (let i = 0; i < 10; i++) out += chars[buf[i] % chars.length];
    return out;
}

function fillSecret(button, field) {
    const input = button.closest("label").querySelector(`input[name="${field}"]`);
    if (input) input.value = field === "username" ? randomUsername() : randomPassword();
}

function startCreate(viewName) {
    creatingView = viewName;
    editingId = null;
    bulkOpen = false;
    lastCreated = null;
    selectedCustomerIds = new Set();
    show(viewName);
}

function startEditCustomer(id) {
    creatingView = null;
    editingId = Number(id);
    bulkOpen = false;
    lastCreated = null;
    show("customers");
}

function openBulkCustomers() {
    if (!selectedCustomerIds.size) {
        alert("Select at least one customer.");
        return;
    }
    creatingView = null;
    editingId = null;
    lastCreated = null;
    bulkOpen = true;
    show("customers");
}

function cancelCreate() {
    const viewName = creatingView === "resellers" ? "resellers" : "customers";
    creatingView = null;
    editingId = null;
    bulkOpen = false;
    show(viewName);
}

function dismissCreated() {
    const viewName = lastCreated && lastCreated.kind === "Reseller" ? "resellers" : "customers";
    lastCreated = null;
    show(viewName);
}

function switchUserTab(el, name) {
    const form = el.closest("form");
    if (!form) return;
    form.querySelectorAll(".tab-btn").forEach((btn) => btn.classList.toggle("active", btn.dataset.tab === name));
    form.querySelectorAll(".tab-panel").forEach((panel) => panel.classList.toggle("active", panel.dataset.tab === name));
}

function stepUserTab(el, delta) {
    const form = el.closest("form");
    const tabs = ["general", "personal", "supplementary"];
    const current = (form.querySelector(".tab-btn.active") || {}).dataset.tab || "general";
    const next = tabs[Math.max(0, Math.min(tabs.length - 1, tabs.indexOf(current) + delta))];
    switchUserTab(form, next);
}

function profileValue(value) {
    if (value === undefined || value === null) return "";
    return String(value).trim();
}

function profileSection(title, pairs) {
    const items = pairs.filter(([, value]) => profileValue(value) !== "");
    if (!items.length) return "";
    return `<div class="profile-section">
        <h4>${esc(title)}</h4>
        <dl class="profile-grid">${items.map(([label, value]) => `<div><dt>${esc(label)}</dt><dd>${value}</dd></div>`).join("")}</dl>
    </div>`;
}

function createdRecordCard() {
    const item = lastCreated;
    if (!item) return "";
    const row = item.data || {};
    const name = `${row.firstname || ""} ${row.lastname || ""}`.trim();
    const paid = Number(row.typepaid) === 1 ? "Postpaid" : "Prepaid";
    const active = Number(row.active) === 1 ? "Active" : "Inactive";
    const unlimited = (value) => (value === -1 || value === "-1" ? "Unlimited" : value);
    const title = item.action === "updated" ? `${item.kind} updated on the OCS` : `${item.kind} created on the OCS`;
    const secretLine = item.password
        ? `<p>Username <code>${esc(item.username)}</code> · Password / SIP secret <code>${esc(item.password)}</code></p>
        <p class="muted">Copy the SIP secret now. It is not stored in the BSS.</p>`
        : `<p>Username <code>${esc(item.username)}</code></p>`;
    return `<div class="card credentials">
        <div class="toolbar">
            <h3>${esc(title)}</h3>
            <button class="btn ghost" type="button" onclick="dismissCreated()">Close</button>
        </div>
        ${secretLine}
        ${profileSection("General", [
            ["Name", esc(name)],
            ["Company", esc(row.company_name)],
            ["Plan", esc(row.idPlanname || row.id_plan)],
            ["Type", paid],
            ["Status", active],
            ["Opening credit", money(row.credit)],
            ["Credit limit", row.creditlimit],
            ["Language", esc(row.language)],
        ])}
        ${profileSection("Personal", [
            ["Email", esc(row.email)],
            ["Email 2", esc(row.email2)],
            ["Phone", esc(row.phone)],
            ["Mobile", esc(row.mobile)],
            ["Address", esc(row.address)],
            ["City", esc(row.city)],
            ["Neighborhood", esc(row.neighborhood)],
            ["State", esc(row.state)],
            ["Country", esc(row.country)],
            ["Zip code", esc(row.zipcode)],
            ["VAT", esc(row.vat)],
            ["Document", esc(row.doc)],
        ])}
        ${profileSection("Supplementary", [
            ["Local prefix", esc(row.prefix_local)],
            ["Call limit", unlimited(row.calllimit)],
            ["SIP account limit", unlimited(row.sipaccountlimit)],
            ["Inbound call limit", unlimited(row.inbound_call_limit)],
            ["CPS limit", unlimited(row.cpslimit)],
            ["Description", esc(row.description)],
        ])}
    </div>`;
}

function optionSelected(current, value) {
    return String(current) === String(value) ? " selected" : "";
}

function inputVal(record, name, fallback) {
    if (!record || record[name] == null || record[name] === "") return fallback == null ? "" : fallback;
    return record[name];
}

function userCreateForm(handler, submitLabel, data, optionsCfg) {
    const record = optionsCfg.record || null;
    const editing = Boolean(record);
    const plans = data.plans || [];
    const parents = data.parents || [];
    const defaultPlan = record && record.id_plan ? record.id_plan : (plans[0] ? plans[0].id : "");
    const parentOpts = options(parents, "id", (p) => `${p.username}${p.company_name ? " — " + p.company_name : ""} (${p.kind})`, record ? record.id_user : 1);
    const planOpts = options(plans, "id", (p) => p.name, defaultPlan);
    const typeValue = record ? Number(record.typepaid || 0) : 0;
    const typeField = optionsCfg.postpaidLocked
        ? `<label>Account type <select name="typepaid" disabled><option value="1" selected>Postpaid</option></select></label>`
        : `<label>Account type <select name="typepaid"><option value="0"${optionSelected(typeValue, 0)}>Prepaid</option><option value="1"${optionSelected(typeValue, 1)}>Postpaid</option></select></label>`;
    const kind = optionsCfg.kind || "Customer";
    const language = inputVal(record, "language", "en");
    const active = record ? Number(record.active == null ? 1 : record.active) : 1;
    const restriction = record ? Number(record.restriction || 0) : 0;
    const recordCall = record ? Number(record.record_call || 0) : 0;
    return `
        <form class="form-create card" data-mode="${editing ? "edit" : "create"}" data-id="${editing ? esc(record.id) : ""}" data-require-company="${optionsCfg.requireCompany ? "1" : "0"}" novalidate onsubmit="return ${handler}(event)">
            <div class="toolbar">
                <h3>${editing ? `Edit ${esc(kind.toLowerCase())}` : `New ${esc(kind.toLowerCase())}`}</h3>
                <button class="btn ghost" type="button" onclick="cancelCreate()">Cancel</button>
            </div>
            <p class="muted">${editing ? "Update the tabs, then save the customer on the MagnusBilling OCS. Leave password blank to keep the current SIP secret." : `Use the tabs for general, personal, and supplementary details, then create the ${esc(kind.toLowerCase())} on the MagnusBilling OCS.`}</p>
            <div class="tabs" role="tablist">
                <button type="button" class="tab-btn active" data-tab="general" onclick="switchUserTab(this, 'general')">General</button>
                <button type="button" class="tab-btn" data-tab="personal" onclick="switchUserTab(this, 'personal')">Personal</button>
                <button type="button" class="tab-btn" data-tab="supplementary" onclick="switchUserTab(this, 'supplementary')">Supplementary</button>
            </div>
            <div class="tab-panel active" data-tab="general">
                <label>Username
                    <span class="with-action">
                        <input name="username" minlength="4" maxlength="20" placeholder="4-20 characters, no spaces" value="${esc(inputVal(record, "username", ""))}">
                        ${editing ? "" : `<button class="btn ghost" type="button" onclick="fillSecret(this, 'username')">Generate</button>`}
                    </span>
                </label>
                <label>Password
                    <span class="with-action">
                        <input name="password" minlength="6" maxlength="100" autocomplete="new-password" placeholder="${editing ? "Leave blank to keep current" : "Also used as the SIP secret"}">
                        <button class="btn ghost" type="button" onclick="fillSecret(this, 'password')">Generate</button>
                    </span>
                </label>
                <label>Plan <select name="id_plan">${planOpts}</select></label>
                <label>Parent <select name="id_user">${parentOpts || '<option value="1">Admin</option>'}</select></label>
                <label>Language <select name="language">
                    <option value="en"${optionSelected(language, "en")}>English</option>
                    <option value="es"${optionSelected(language, "es")}>Spanish</option>
                    <option value="pt_BR"${optionSelected(language, "pt_BR")}>Portuguese</option>
                    <option value="fr"${optionSelected(language, "fr")}>French</option>
                    <option value="it"${optionSelected(language, "it")}>Italian</option>
                </select></label>
                <label>Status <select name="active"><option value="1"${optionSelected(active, 1)}>Active</option><option value="0"${optionSelected(active, 0)}>Inactive</option></select></label>
                ${typeField}
                <label>${editing ? "OCS credit" : "Opening credit"} <input name="credit" type="number" step="0.0001" value="${esc(inputVal(record, "credit", 0))}"></label>
                <label>Credit limit <input name="creditlimit" type="number" step="1" value="${esc(inputVal(record, "creditlimit", 0))}"></label>
            </div>
            <div class="tab-panel" data-tab="personal">
                <label>First name <input name="firstname" value="${esc(inputVal(record, "firstname", ""))}"></label>
                <label>Last name <input name="lastname" value="${esc(inputVal(record, "lastname", ""))}"></label>
                <label>Company <input name="company_name" value="${esc(inputVal(record, "company_name", ""))}"></label>
                <label>Trade name <input name="commercial_name" value="${esc(inputVal(record, "commercial_name", ""))}"></label>
                <label>Website <input name="company_website" value="${esc(inputVal(record, "company_website", ""))}"></label>
                <label>Email <input name="email" type="email" placeholder="Must be unique on the OCS" value="${esc(inputVal(record, "email", ""))}"></label>
                <label>Email 2 <input name="email2" type="email" value="${esc(inputVal(record, "email2", ""))}"></label>
                <label>Phone <input name="phone" value="${esc(inputVal(record, "phone", ""))}"></label>
                <label>Mobile <input name="mobile" value="${esc(inputVal(record, "mobile", ""))}"></label>
                <label>VAT <input name="vat" value="${esc(inputVal(record, "vat", ""))}"></label>
                <label>Document <input name="doc" value="${esc(inputVal(record, "doc", ""))}"></label>
                <label class="span">Address <input name="address" value="${esc(inputVal(record, "address", ""))}"></label>
                <label>City <input name="city" value="${esc(inputVal(record, "city", ""))}"></label>
                <label>Neighborhood <input name="neighborhood" value="${esc(inputVal(record, "neighborhood", ""))}"></label>
                <label>State <input name="state" value="${esc(inputVal(record, "state", ""))}"></label>
                <label>Country <input name="country" placeholder="e.g. VUT" value="${esc(inputVal(record, "country", ""))}"></label>
                <label>Zip code <input name="zipcode" value="${esc(inputVal(record, "zipcode", ""))}"></label>
            </div>
            <div class="tab-panel" data-tab="supplementary">
                <label>Local prefix <input name="prefix_local" placeholder="Optional dial prefix" value="${esc(inputVal(record, "prefix_local", ""))}"></label>
                <label>Call limit <input name="calllimit" type="number" value="${esc(inputVal(record, "calllimit", -1))}" title="-1 is unlimited"></label>
                <label>SIP account limit <input name="sipaccountlimit" type="number" value="${esc(inputVal(record, "sipaccountlimit", -1))}"></label>
                <label>Inbound call limit <input name="inbound_call_limit" type="number" value="${esc(inputVal(record, "inbound_call_limit", -1))}"></label>
                <label>CPS limit <input name="cpslimit" type="number" value="${esc(inputVal(record, "cpslimit", -1))}"></label>
                <label>Restriction <select name="restriction"><option value="0"${optionSelected(restriction, 0)}>None</option><option value="1"${optionSelected(restriction, 1)}>Cannot dial</option><option value="2"${optionSelected(restriction, 2)}>Cannot receive</option></select></label>
                <label>Record calls <select name="record_call"><option value="0"${optionSelected(recordCall, 0)}>No</option><option value="1"${optionSelected(recordCall, 1)}>Yes</option></select></label>
                <label class="span">Description <textarea name="description">${esc(inputVal(record, "description", ""))}</textarea></label>
                <label class="span">BSS note <input name="note" value="${esc(inputVal(record, "bss_note", inputVal(record, "note", "")))}"></label>
            </div>
            <div class="actions">
                <button class="btn ghost" type="button" onclick="stepUserTab(this, -1)">Back</button>
                <button class="btn ghost" type="button" onclick="stepUserTab(this, 1)">Next</button>
                <button class="btn" type="submit">${esc(submitLabel)}</button>
                <p class="err form-err"></p>
            </div>
        </form>
    `;
}

function formObject(form) {
    const raw = Object.fromEntries(new FormData(form).entries());
    const ints = ["typepaid", "id_plan", "id_user", "active", "calllimit", "sipaccountlimit", "inbound_call_limit", "cpslimit", "restriction", "record_call", "creditlimit"];
    const floats = ["credit"];
    ints.forEach((key) => {
        if (!(key in raw) || raw[key] === "") {
            delete raw[key];
            return;
        }
        raw[key] = Number(raw[key]);
    });
    floats.forEach((key) => {
        if (!(key in raw) || raw[key] === "") {
            delete raw[key];
            return;
        }
        raw[key] = Number(raw[key]);
    });
    Object.keys(raw).forEach((key) => {
        if (raw[key] === "" && form.dataset.mode !== "edit") delete raw[key];
    });
    return raw;
}

function missingCreateFields(form) {
    const checks = [
        ["username", "general", "Username"],
        ["id_plan", "general", "Plan"],
        ["firstname", "personal", "First name"],
    ];
    if (form.dataset.mode !== "edit") {
        checks.splice(1, 0, ["password", "general", "Password"]);
    }
    if (form.dataset.requireCompany === "1") {
        checks.push(["company_name", "personal", "Company"]);
    }
    for (const [name, tab, label] of checks) {
        const el = form.elements[name];
        if (!el || !String(el.value || "").trim()) {
            return { name, tab, label };
        }
    }
    return null;
}

function customerListCard(data) {
    const rows = data.rows || [];
    const selectedCount = selectedCustomerIds.size;
    return `<div class="card">
        <div class="toolbar">
            <h3>Customers</h3>
            <div class="toolbar-actions">
                <button class="btn ghost" type="button" onclick="openBulkCustomers()">Bulk update</button>
                <button class="btn ghost danger" type="button" onclick="bulkDeleteCustomers()">Delete selected</button>
                <button class="btn" type="button" onclick="startCreate('customers')">New customer</button>
            </div>
        </div>
        <p class="muted">${selectedCount ? `${selectedCount} selected` : "Select customers to edit in bulk, or open one to change."}</p>
        ${customerTable(rows)}
    </div>`;
}

function customerTable(rows) {
    if (!rows.length) return '<p class="muted">No records yet.</p>';
    return `<table>
        <thead><tr>
            <th><input type="checkbox" id="customer-check-all" onchange="toggleAllCustomers(this)"></th>
            <th>ID</th><th>Username</th><th>Name</th><th>Email</th><th>Type</th><th>OCS credit</th><th>Plan</th><th>Active</th><th></th>
        </tr></thead>
        <tbody>${rows.map((r) => `<tr>
            <td><input type="checkbox" class="row-check" value="${esc(r.id)}" onchange="toggleCustomerRow(this)"></td>
            <td>${esc(r.id)}</td>
            <td>${esc(r.username)}</td>
            <td>${esc(`${r.firstname || ""} ${r.lastname || ""}`.trim())}</td>
            <td>${esc(r.email || "")}</td>
            <td>${esc(r.paid_kind)}</td>
            <td>${money(r.credit)}</td>
            <td>${esc(r.idPlanname || r.id_plan || "")}</td>
            <td>${Number(r.active) === 1 ? "yes" : "no"}</td>
            <td class="row-actions">
                <button class="btn ghost" type="button" onclick="startEditCustomer(${Number(r.id)})">Edit</button>
                <button class="btn ghost danger" type="button" onclick="deleteCustomer(${Number(r.id)})">Delete</button>
            </td>
        </tr>`).join("")}</tbody>
    </table>`;
}

function restoreCustomerSelection() {
    document.querySelectorAll(".row-check").forEach((box) => {
        box.checked = selectedCustomerIds.has(Number(box.value));
    });
    const all = document.getElementById("customer-check-all");
    const boxes = document.querySelectorAll(".row-check");
    if (all && boxes.length) {
        all.checked = Array.from(boxes).every((box) => box.checked);
    }
}

function toggleCustomerRow(box) {
    const id = Number(box.value);
    if (box.checked) selectedCustomerIds.add(id);
    else selectedCustomerIds.delete(id);
}

function toggleAllCustomers(box) {
    document.querySelectorAll(".row-check").forEach((item) => {
        item.checked = box.checked;
        toggleCustomerRow(item);
    });
}

function bulkCustomerForm(data, selected) {
    const plans = data.plans || [];
    const parents = data.parents || [];
    const names = selected.map((row) => row.username).join(", ");
    return `<form class="form-create card" novalidate onsubmit="return applyBulkCustomers(event)">
        <div class="toolbar">
            <h3>Bulk update ${selected.length} customer${selected.length === 1 ? "" : "s"}</h3>
            <button class="btn ghost" type="button" onclick="cancelCreate()">Cancel</button>
        </div>
        <p class="muted">Empty fields are left unchanged. Applying to: ${esc(names)}</p>
        <div class="tab-panel active">
            <label>Plan <select name="id_plan"><option value="">No change</option>${options(plans, "id", (p) => p.name, "")}</select></label>
            <label>Parent <select name="id_user"><option value="">No change</option>${options(parents, "id", (p) => `${p.username}${p.company_name ? " — " + p.company_name : ""}`, "")}</select></label>
            <label>Language <select name="language"><option value="">No change</option><option value="en">English</option><option value="es">Spanish</option><option value="pt_BR">Portuguese</option><option value="fr">French</option><option value="it">Italian</option></select></label>
            <label>Status <select name="active"><option value="">No change</option><option value="1">Active</option><option value="0">Inactive</option></select></label>
            <label>Account type <select name="typepaid"><option value="">No change</option><option value="0">Prepaid</option><option value="1">Postpaid</option></select></label>
            <label>OCS credit <input name="credit" type="number" step="0.0001" placeholder="No change"></label>
            <label>Credit limit <input name="creditlimit" type="number" step="1" placeholder="No change"></label>
            <label>Call limit <input name="calllimit" type="number" placeholder="No change"></label>
            <label>Restriction <select name="restriction"><option value="">No change</option><option value="0">None</option><option value="1">Cannot dial</option><option value="2">Cannot receive</option></select></label>
            <label>Record calls <select name="record_call"><option value="">No change</option><option value="0">No</option><option value="1">Yes</option></select></label>
            <label>Local prefix <input name="prefix_local" placeholder="No change"></label>
        </div>
        <div class="actions">
            <button class="btn" type="submit">Apply to selected</button>
            <p class="err form-err"></p>
        </div>
    </form>`;
}

async function saveCustomer(event) {
    event.preventDefault();
    const form = event.target;
    const err = form.querySelector(".form-err");
    if (err) err.textContent = "";
    const missing = missingCreateFields(form);
    if (missing) {
        switchUserTab(form, missing.tab);
        if (err) err.textContent = `${missing.label} is required`;
        const el = form.elements[missing.name];
        if (el && el.focus) el.focus();
        return false;
    }
    try {
        const result = await api("/api/customers/" + form.dataset.id, { method: "PUT", body: JSON.stringify(formObject(form)) });
        const creds = result.credentials || {};
        lastCreated = {
            kind: "Customer",
            action: "updated",
            username: creds.username || (result.data && result.data.username) || "",
            password: creds.password || "",
            data: result.data || {},
        };
        creatingView = null;
        editingId = null;
        show("customers");
    } catch (exc) {
        if (err) err.textContent = exc.message || "Save failed";
        else alert(exc.message || "Save failed");
    }
    return false;
}

async function deleteCustomer(id) {
    if (!confirm("Delete this customer from the MagnusBilling OCS? This cannot be undone.")) return false;
    try {
        await api("/api/customers/" + id, { method: "DELETE" });
        selectedCustomerIds.delete(Number(id));
        lastCreated = null;
        editingId = null;
        show("customers");
    } catch (exc) {
        alert(exc.message || "Delete failed");
    }
    return false;
}

async function bulkDeleteCustomers() {
    const ids = Array.from(selectedCustomerIds);
    if (!ids.length) {
        alert("Select at least one customer.");
        return false;
    }
    if (!confirm(`Delete ${ids.length} customer${ids.length === 1 ? "" : "s"} from the MagnusBilling OCS? This cannot be undone.`)) return false;
    try {
        const result = await api("/api/customers/bulk", { method: "POST", body: JSON.stringify({ ids, action: "delete" }) });
        selectedCustomerIds = new Set();
        bulkOpen = false;
        lastCreated = null;
        show("customers");
        if (result.errors && result.errors.length) {
            alert(result.errors.map((item) => `#${item.id}: ${item.detail}`).join("\n"));
        }
    } catch (exc) {
        alert(exc.message || "Bulk delete failed");
    }
    return false;
}

async function applyBulkCustomers(event) {
    event.preventDefault();
    const form = event.target;
    const err = form.querySelector(".form-err");
    if (err) err.textContent = "";
    const ids = Array.from(selectedCustomerIds);
    if (!ids.length) {
        if (err) err.textContent = "Select at least one customer";
        return false;
    }
    const fields = formObject(form);
    if (!Object.keys(fields).length) {
        if (err) err.textContent = "Choose at least one field to update";
        return false;
    }
    try {
        const result = await api("/api/customers/bulk", { method: "POST", body: JSON.stringify(Object.assign({ ids, action: "update" }, fields)) });
        bulkOpen = false;
        lastCreated = null;
        if (result.errors && result.errors.length) {
            alert(result.errors.map((item) => `#${item.id}: ${item.detail}`).join("\n"));
        }
        show("customers");
    } catch (exc) {
        if (err) err.textContent = exc.message || "Bulk update failed";
        else alert(exc.message || "Bulk update failed");
    }
    return false;
}

async function submitUser(event, path, kind, viewName) {
    event.preventDefault();
    const form = event.target;
    const err = form.querySelector(".form-err");
    if (err) err.textContent = "";
    const missing = missingCreateFields(form);
    if (missing) {
        switchUserTab(form, missing.tab);
        if (err) err.textContent = `${missing.label} is required`;
        const el = form.elements[missing.name];
        if (el && el.focus) el.focus();
        return false;
    }
    try {
        const result = await api(path, { method: "POST", body: JSON.stringify(formObject(form)) });
        const creds = result.credentials || {};
        lastCreated = {
            kind,
            username: creds.username || (result.data && result.data.username) || "",
            password: creds.password || (result.data && result.data.password) || "",
            data: result.data || {},
        };
        creatingView = null;
        editingId = null;
        show(viewName);
    } catch (exc) {
        if (err) err.textContent = exc.message || "Create failed";
        else alert(exc.message || "Create failed");
    }
    return false;
}

async function createCustomer(event) {
    return submitUser(event, "/api/customers", "Customer", "customers");
}

async function createProduct(event) {
    event.preventDefault();
    const f = Object.fromEntries(new FormData(event.target).entries());
    f.monthly_fee = Number(f.monthly_fee || 0);
    f.included_minutes = Number(f.included_minutes || 0);
    await api("/api/products", { method: "POST", body: JSON.stringify(f) });
    show("products");
    return false;
}

async function createPayment(event) {
    event.preventDefault();
    const f = Object.fromEntries(new FormData(event.target).entries());
    f.ocs_user_id = Number(f.ocs_user_id);
    f.amount = Number(f.amount);
    await api("/api/payments", { method: "POST", body: JSON.stringify(f) });
    show("payments");
    return false;
}

async function createReseller(event) {
    return submitUser(event, "/api/resellers", "Reseller", "resellers");
}

async function createInvoice(event) {
    event.preventDefault();
    const f = Object.fromEntries(new FormData(event.target).entries());
    f.ocs_user_id = Number(f.ocs_user_id);
    await api("/api/invoices", { method: "POST", body: JSON.stringify(f) });
    show("invoices");
    return false;
}

boot();
