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
        document.getElementById("view").innerHTML = `
            <form class="form card" onsubmit="return createCustomer(event)">
                <label>First name <input name="firstname" required></label>
                <label>Last name <input name="lastname"></label>
                <label>Username <input name="username"></label>
                <label>Email <input name="email" type="email"></label>
                <label>Company <input name="company_name"></label>
                <label>Opening credit <input name="credit" type="number" step="0.0001" value="0"></label>
                <label>Type <select name="typepaid"><option value="0">Prepaid</option><option value="1">Postpaid</option></select></label>
                <label>Credit limit <input name="creditlimit" type="number" step="0.01" value="0"></label>
                <label>Note <input name="note"></label>
                <button class="btn" type="submit">Create customer</button>
            </form>
            <div class="card">${table(["ID", "Username", "Name", "Type", "OCS credit", "Plan", "Note"], data.rows.map((r) => [r.id, r.username, `${r.firstname || ""} ${r.lastname || ""}`.trim(), r.paid_kind, money(r.credit), r.idPlanname || r.id_plan, r.bss_note || ""]))}</div>
        `;
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
        document.getElementById("view").innerHTML = `
            <form class="form card" onsubmit="return createReseller(event)">
                <label>Company <input name="company_name" required></label>
                <label>Username <input name="username"></label>
                <label>Email <input name="email" type="email"></label>
                <label>First name <input name="firstname"></label>
                <label>Wholesale credit <input name="credit" type="number" step="0.01" value="0"></label>
                <button class="btn" type="submit">Create reseller</button>
            </form>
            <div class="card">${table(["ID", "Username", "Company", "Customers", "Downstream wallet", "Own credit"], data.rows.map((r) => [r.id, r.username, r.company_name, r.customers, money(r.customer_wallet), money(r.credit)]))}</div>
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

async function createCustomer(event) {
    event.preventDefault();
    const f = Object.fromEntries(new FormData(event.target).entries());
    f.credit = Number(f.credit || 0);
    f.creditlimit = Number(f.creditlimit || 0);
    f.typepaid = Number(f.typepaid);
    await api("/api/customers", { method: "POST", body: JSON.stringify(f) });
    show("customers");
    return false;
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
    event.preventDefault();
    const f = Object.fromEntries(new FormData(event.target).entries());
    f.credit = Number(f.credit || 0);
    await api("/api/resellers", { method: "POST", body: JSON.stringify(f) });
    show("resellers");
    return false;
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
