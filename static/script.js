// ================= Tile navigation =================
function initTileNavigation() {
  document.querySelectorAll(".tile[data-target]").forEach(tile => {
    tile.onclick = () => {
      const target = tile.dataset.target;
      document.querySelectorAll(".card").forEach(c => c.classList.add("hidden"));
      document.getElementById(target).classList.remove("hidden");
      document.getElementById(target).scrollIntoView({behavior: "smooth", block: "start"});
    };
  });
}

// ================= Entry form =================
function initEntryForm() {
  const saveBtn = document.getElementById("saveBtn");
  if (!saveBtn) return;

  saveBtn.onclick = async () => {
    const form = document.getElementById("entryForm");
    const fd = new FormData(form);
    const payload = Object.fromEntries(fd.entries());

    if (!payload.name || !payload.phone || !payload.inspection_date || !payload.expiry_date) {
      showMsg("Please fill all required fields", "err");
      return;
    }

    const res = await fetch("/api/save", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    if (data.ok) {
      showMsg("Saved successfully! Sl No: " + data.id, "ok");
      form.reset();
      if (!document.getElementById("excelCard").classList.contains("hidden")) {
        loadExcel();
      }
    } else {
      showMsg(data.msg || "Error saving", "err");
    }
  };
}

function showMsg(text, type) {
  const m = document.getElementById("msg");
  if (!m) return;
  m.className = "msg " + type;
  m.innerText = text;
  setTimeout(() => { m.innerText = ""; }, 3000);
}

// ================= Filter bar (Excel) =================
function initFilterBar() {
  const fBtn = document.getElementById("filterBtn");
  const cBtn = document.getElementById("clearFilterBtn");
  const sBox = document.getElementById("searchBox");

  if (fBtn) fBtn.onclick = () => loadExcel();

  if (cBtn) cBtn.onclick = () => {
    if (sBox) sBox.value = "";
    const f = document.getElementById("filterFrom");
    const t = document.getElementById("filterTo");
    if (f) f.value = "";
    if (t) t.value = "";
    loadExcel();
  };

  if (sBox) {
    let timer = null;
    sBox.addEventListener("input", () => {
      clearTimeout(timer);
      timer = setTimeout(() => loadExcel(), 250);
    });
  }
}

function initSharedDataRefresh() {
  window.setInterval(() => {
    const excelCard = document.getElementById("excelCard");
    if (excelCard && !excelCard.classList.contains("hidden")) loadExcel();
  }, 15000);
}

// ================= Excel view / edit =================
async function loadExcel() {
  const fromEl = document.getElementById("filterFrom");
  const toEl = document.getElementById("filterTo");
  const searchEl = document.getElementById("searchBox");

  const fromDate = fromEl ? fromEl.value : "";
  const toDate = toEl ? toEl.value : "";
  const q = searchEl ? searchEl.value.trim() : "";

  let url = "/api/excel-view";
  const params = [];
  if (fromDate) params.push("from_date=" + encodeURIComponent(fromDate));
  if (toDate) params.push("to_date=" + encodeURIComponent(toDate));
  if (q) params.push("q=" + encodeURIComponent(q));
  if (params.length) url += "?" + params.join("&");

  const res = await fetch(url, {cache: "no-store"});
  const data = await res.json();
  const tbody = document.querySelector("#excelTable tbody");
  tbody.innerHTML = "";

  const countEl = document.getElementById("filterCount");
  if (countEl && data.ok) {
    const isFiltered = fromDate || toDate || q;
    countEl.innerText = isFiltered
      ? `Showing ${data.filtered} of ${data.total} records`
      : `Total: ${data.total} records`;
  }

  if (!data.ok || data.data.length === 0) {
    const reason = q ? ` matching "${q}"`
      : (fromDate || toDate) ? " for this date range"
      : "";
    tbody.innerHTML = `<tr><td colspan="10" style="text-align:center;color:#888;padding:20px;">
      No records found${reason}.
    </td></tr>`;
    return;
  }

  const canDelete = data.can_delete === true;

  data.data.forEach(row => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${row.sl}</td>
      <td>${escapeHtml(row.name)}</td>
      <td>${escapeHtml(row.phone)}</td>
      <td>${escapeHtml(row.email || "")}</td>
      <td>${escapeHtml(row.vehicle_type || "")}</td>
      <td>${escapeHtml(row.vehicle_no || "")}</td>
      <td>${row.inspection_date}</td>
      <td>${row.expiry_date}</td>
      <td>${escapeHtml(row.entered_by)}</td>
      <td class="row-actions no-print">
        <button class="btn-edit" data-id="${row.id}">✏️</button>
        ${canDelete ? `<button class="btn-del" data-id="${row.id}">🗑️</button>` : ""}
      </td>
    `;
    tbody.appendChild(tr);
  });

  tbody.querySelectorAll(".btn-edit").forEach(b => b.onclick = () => editRow(b.dataset.id));
  tbody.querySelectorAll(".btn-del").forEach(b => b.onclick = () => deleteRow(b.dataset.id));
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, m => ({
    "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"
  }[m]));
}

async function editRow(id) {
  const res = await fetch("/api/excel-view");
  const data = await res.json();
  const row = data.data.find(r => String(r.id) === String(id));
  if (!row) return;

  const name = prompt("Name:", row.name); if (name === null) return;
  const phone = prompt("Phone:", row.phone); if (phone === null) return;
  const email = prompt("Email:", row.email || ""); if (email === null) return;
    const vehicle_type = prompt("Vehicle Type:", row.vehicle_type || ""); if (vehicle_type === null) return;
  const vehicle_no = prompt("Vehicle No:", row.vehicle_no || ""); if (vehicle_no === null) return;
  const insp = prompt("Inspection Date (YYYY-MM-DD):", row.inspection_date); if (insp === null) return;
  const exp = prompt("Expiry Date (YYYY-MM-DD):", row.expiry_date); if (exp === null) return;

  const upd = await fetch("/api/update", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({id: row.id, name, phone, email, vehicle_type,
                          vehicle_no, inspection_date: insp, expiry_date: exp})
  });
  const udata = await upd.json();
  if (udata.ok) { alert("Updated successfully"); loadExcel(); }
  else alert("Update failed: " + (udata.msg || "unknown"));
}

async function deleteRow(id) {
  if (!confirm("Delete this record permanently?")) return;
  const res = await fetch("/api/delete", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({id})
  });
  const data = await res.json();
  if (data.ok) loadExcel();
  else alert("Delete failed: " + (data.msg || "unknown"));
}

// ================= Print =================
function initPrint() {
  const btn = document.getElementById("printBtn");
  if (!btn) return;
  btn.onclick = () => {
    const from = document.getElementById("filterFrom")?.value || "";
    const to = document.getElementById("filterTo")?.value || "";
    const q = document.getElementById("searchBox")?.value.trim() || "";
    const range = document.getElementById("printRange");
    const head = document.getElementById("printHeader");
    if (range) {
      const parts = [];
      if (from || to) parts.push(`Date: ${from || "…"} to ${to || "…"}`);
      if (q) parts.push(`Search: "${q}"`);
      range.innerText = parts.length ? parts.join("  |  ") : "All records";
    }
    if (head) head.classList.remove("hidden");
    document.body.classList.add("printing");
    window.print();
    document.body.classList.remove("printing");
    if (head) head.classList.add("hidden");
  };
}

// ================= Admin: users =================
function initUsersCard() {
  const addBtn = document.getElementById("addUserBtn");
  if (!addBtn) return;

  addBtn.onclick = async () => {
    const username = document.getElementById("newUser").value.trim();
    const password = document.getElementById("newPass").value;
    const role = document.getElementById("newRole").value;
    if (!username || !password) { showUserMsg("Enter username and password", "err"); return; }
    const res = await fetch("/api/users/add", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({username, password, role})
    });
    const data = await res.json();
    if (data.ok) {
      document.getElementById("newUser").value = "";
      document.getElementById("newPass").value = "";
      showUserMsg("User added", "ok");
      loadUsers();
    } else showUserMsg(data.msg || "Error", "err");
  };

  loadUsers();
}

function showUserMsg(text, type) {
  const m = document.getElementById("userMsg");
  if (!m) return;
  m.className = "msg " + type;
  m.innerText = text;
  setTimeout(() => { m.innerText = ""; }, 3000);
}

async function loadUsers() {
  const res = await fetch("/api/users");
  const data = await res.json();
  const tbody = document.querySelector("#usersTable tbody");
  if (!tbody) return;
  tbody.innerHTML = "";
  if (!data.ok) return;

  data.data.forEach((u, i) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${i + 1}</td>
      <td>${escapeHtml(u.username)}</td>
      <td><span class="role-pill role-${u.role}">${u.role}</span></td>
      <td>Hidden - change via Edit</td>
      <td class="row-actions">
        <button class="btn-edit" data-id="${u.id}" data-username="${escapeHtml(u.username)}" data-role="${u.role}">✏️ Edit</button>
        <button class="btn-del" data-id="${u.id}">🗑️ Remove</button>
      </td>`;
    tbody.appendChild(tr);
  });

  tbody.querySelectorAll(".btn-edit").forEach(b =>
    b.onclick = () => editUser(b.dataset.id, b.dataset.username, b.dataset.role));
  tbody.querySelectorAll(".btn-del").forEach(b =>
    b.onclick = () => removeUser(b.dataset.id, b.closest("tr").children[1].innerText));
}

async function editUser(id, currentUsername, currentRole) {
  const newUsername = prompt("Username:", currentUsername); if (newUsername === null) return;
  const newPassword = prompt("New password (leave empty to keep current):", ""); if (newPassword === null) return;
  const newRole = prompt("Role (admin/user):", currentRole); if (newRole === null) return;

  const payload = {id: parseInt(id), username: newUsername.trim() || null, role: newRole.trim()};
  if (newPassword.trim()) payload.password = newPassword.trim();

  const res = await fetch("/api/users/update", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(payload)
  });
  const data = await res.json();
  if (data.ok) loadUsers(); else alert("Error: " + (data.msg || "unknown"));
}

async function removeUser(id, username) {
  if (!confirm(`Remove user "${username}"? Their inspection records will remain.`)) return;
  const res = await fetch("/api/users/delete", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({id: parseInt(id)})
  });
  const data = await res.json();
  if (data.ok) loadUsers(); else alert("Error: " + (data.msg || "unknown"));
}

// ================= Admin: entry counts =================
function initUserCounts() {
  const fBtn = document.getElementById("ucFilterBtn");
  const cBtn = document.getElementById("ucClearBtn");
  if (!fBtn) return;

  const run = async () => {
    const from = document.getElementById("ucFrom").value;
    const to = document.getElementById("ucTo").value;
    let url = "/api/users/entry-counts";
    const q = [];
    if (from) q.push("from_date=" + encodeURIComponent(from));
    if (to) q.push("to_date=" + encodeURIComponent(to));
    if (q.length) url += "?" + q.join("&");

    const res = await fetch(url);
    const data = await res.json();
    const tbody = document.querySelector("#countsTable tbody");
    tbody.innerHTML = "";
    if (!data.ok) return;
    if (data.data.length === 0) {
      tbody.innerHTML = `<tr><td colspan="2" style="text-align:center;color:#888;">No data</td></tr>`;
      return;
    }
    data.data.forEach(row => {
      const tr = document.createElement("tr");
      tr.innerHTML = `<td>${escapeHtml(row.username)}</td><td><b>${row.count}</b></td>`;
      tbody.appendChild(tr);
    });
  };

  fBtn.onclick = run;
  cBtn.onclick = () => {
    document.getElementById("ucFrom").value = "";
    document.getElementById("ucTo").value = "";
    run();
  };
  run();
}

// ================= Profile modal =================
function initProfile() {
  const btn = document.getElementById("profileBtn");
  const modal = document.getElementById("profileModal");
  const close = document.getElementById("profileClose");
  const cancel = document.getElementById("profileCancel");
  const save = document.getElementById("profileSave");
  if (!btn || !modal) return;

  const open = async () => {
    const res = await fetch("/api/profile");
    const data = await res.json();
    if (!data.ok) { alert("Could not load profile"); return; }
    const d = data.data;
    document.getElementById("pfUsername").value = d.username;
    document.getElementById("pfRole").value = d.role;
    document.getElementById("pfFullName").value = d.full_name || "";
    document.getElementById("pfPhone").value = d.phone || "";
    document.getElementById("pfEmail").value = d.email || "";
    document.getElementById("pfMsg").innerText = "";
    modal.classList.remove("hidden");
  };

  const hide = () => modal.classList.add("hidden");

  btn.onclick = open;
  close.onclick = hide;
  cancel.onclick = hide;
  modal.addEventListener("click", e => { if (e.target === modal) hide(); });

  save.onclick = async () => {
    const payload = {
      full_name: document.getElementById("pfFullName").value.trim(),
      phone: document.getElementById("pfPhone").value.trim(),
      email: document.getElementById("pfEmail").value.trim()
    };
    const res = await fetch("/api/profile", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    const m = document.getElementById("pfMsg");
    if (data.ok) {
      m.className = "msg ok";
      m.innerText = "Profile saved!";
      setTimeout(hide, 900);
    } else {
      m.className = "msg err";
      m.innerText = data.msg || "Error";
    }
  };
}

// ================= Overall pie chart =================
let monthlyChartInstance = null;

function initOverallChart() {
  const btn = document.getElementById("loadChartBtn");
  const yearInput = document.getElementById("chartYear");
  if (!btn || !yearInput) return;

  if (typeof Chart !== "undefined" && typeof ChartDataLabels !== "undefined") {
    Chart.register(ChartDataLabels);
  }

  const thisYear = new Date().getFullYear();
  yearInput.value = thisYear;

  const load = async () => {
    const year = yearInput.value || thisYear;
    const res = await fetch(`/api/monthly-summary?year=${encodeURIComponent(year)}`);
    const data = await res.json();
    if (!data.ok) return;

    const labels = ["Jan","Feb","Mar","Apr","May","Jun",
                    "Jul","Aug","Sep","Oct","Nov","Dec"];
    const values = data.data.map(d => d.count);
    const total = values.reduce((a, b) => a + b, 0);

    const totalEl = document.getElementById("chartTotal");
    if (totalEl) totalEl.innerText = `Total for ${year}: ${total}`;

    const ctx = document.getElementById("monthlyChart").getContext("2d");
    if (monthlyChartInstance) monthlyChartInstance.destroy();

    monthlyChartInstance = new Chart(ctx, {
      type: "pie",
      data: {
        labels: labels,
        datasets: [{
          data: values,
          backgroundColor: [
            "#2a5298", "#4e79c2", "#7ea2dd", "#a8c1ee", "#c8d7f4", "#e2eafb",
            "#f6b26b", "#e69138", "#cc4125", "#a64d79", "#674ea7", "#3d85c6"
          ],
          borderWidth: 1,
          borderColor: "#fff"
        }]
      },
      options: {
        responsive: true,
        plugins: {
          legend: {
            position: "right",
            labels: {
              generateLabels: (chart) => {
                const ds = chart.data.datasets[0];
                return chart.data.labels.map((label, i) => ({
                  text: `${label} — ${ds.data[i]}`,
                  fillStyle: ds.backgroundColor[i],
                  strokeStyle: "#fff",
                  lineWidth: 1,
                  index: i
                }));
              }
            }
          },
          tooltip: {
            callbacks: {
              label: (ctx) => {
                const v = ctx.parsed;
                const pct = total ? ((v / total) * 100).toFixed(1) : "0";
                return `${ctx.label}: ${v} (${pct}%)`;
              }
            }
          },
          datalabels: {
            color: "#fff",
            textStrokeColor: "rgba(0,0,0,0.35)",
            textStrokeWidth: 2,
            font: { weight: "bold", size: 12 },
            textAlign: "center",
            formatter: (value) => {
              if (!value) return "";
              const pct = total ? ((value / total) * 100).toFixed(1) : "0";
              return `${value}\n(${pct}%)`;
            }
          }
        }
      }
    });
  };

  btn.onclick = load;
  document.querySelector('[data-target="overallCard"]')
    ?.addEventListener("click", load);
}

// ================= Boot =================
document.addEventListener("DOMContentLoaded", () => {
  initPrint();
});