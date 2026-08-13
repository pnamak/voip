const titles = {
    dashboard: ["Dashboard", "Customers, wallets, and real-time charging"],
    customers: ["Customers", "CRM in SmartVoice, balances in the MagnusBilling OCS"],
    products: ["Products", "Catalog in BSS, rate plans charged by the OCS"],
    payments: ["Payments", "Collect in BSS, apply credit through OCS refill"],
    resellers: ["Resellers", "Agent accounts and downstream customer wallets"],
    usage: ["OCS usage", "Live calls and CDRs from the online charging engine"],
    invoices: ["Invoices", "BSS invoices rolled up from OCS call charges"],
};

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

async function show(name) {
    document.querySelectorAll(".nav button").forEach((btn) => btn.classList.toggle("active", btn.dataset.view === name));
    document.getElementById("title").textContent = titles[name][0];
    document.getElementById("subtitle").textContent = titles[name][1];
    const render = views[name];
    if (render) await render();
}

document.querySelectorAll(".nav button").forEach((btn) => btn.addEventListener("click", () => show(btn.dataset.view)));

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
            </div>
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
};

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
