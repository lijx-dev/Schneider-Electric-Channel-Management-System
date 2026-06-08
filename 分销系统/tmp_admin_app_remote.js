const API_BASE = window.location.protocol === "file:"
  ? "https://faq-backend-229183-5-1407839340.sh.run.tcloudbase.com"
  : window.location.origin;
const TOKEN_KEY = "schneiderBackcontrolToken";

const state = {
  token: localStorage.getItem(TOKEN_KEY) || "",
  provinces: [],
  companies: [],
  roles: [],
  users: [],
  userTotal: 0,
  userOffset: 0,
  userPageSize: 20,
  globalLeaderboardPage: 1,
  globalLeaderboardTotal: 0,
  globalLeaderboardPageSize: 20,
  monthlyRows: [],
  orderRows: [],
  orderBadgeTimer: null,
};

const $ = (id) => document.getElementById(id);

function setFeedback(node, message, isError = false) {
  node.textContent = message || "";
  node.classList.toggle("error", Boolean(isError));
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

async function request(path, options = {}) {
  const headers = {
    "Content-Type": "application/json",
    ...(options.headers || {}),
  };
  if (state.token) {
    headers.Authorization = `Bearer ${state.token}`;
  }

  const response = await fetch(`${API_BASE}${path}`, {
    method: options.method || "GET",
    headers,
    body: options.body ? JSON.stringify(options.body) : undefined,
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok || payload.code !== 0) {
    throw new Error(payload.detail || payload.message || `请求失败：${response.status}`);
  }
  return payload.data;
}

async function downloadFile(path, filename) {
  const headers = {};
  if (state.token) {
    headers.Authorization = `Bearer ${state.token}`;
  }
  const response = await fetch(`${API_BASE}${path}`, { headers });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.detail || payload.message || `请求失败：${response.status}`);
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

function showAuthed(isAuthed) {
  $("loginPanel").classList.toggle("hidden", isAuthed);
  $("dashboard").classList.toggle("hidden", !isAuthed);
}

function roleLabel(role) {
  return String(role || "").trim() || "未填写";
}

function orderStatusLabel(status) {
  return { pending: "待处理", approved: "已确认", delivered: "已发货", cancelled: "已取消" }[status] || "待处理";
}

function formatDateTime(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString("zh-CN", { hour12: false });
}

function setCompanyOptions(select, includeAll = false) {
  const current = select.value;
  select.innerHTML = "";
  if (includeAll) {
    select.appendChild(new Option("全部公司", ""));
  }
  state.companies.forEach((company) => select.appendChild(new Option(company, company)));
  if ([...select.options].some((option) => option.value === current)) {
    select.value = current;
  }
}

function setProvinceOptions(select, includeAll = true) {
  const current = select.value;
  select.innerHTML = "";
  if (includeAll) {
    select.appendChild(new Option("全部省份", ""));
  }
  state.provinces.forEach((province) => select.appendChild(new Option(province, province)));
  if ([...select.options].some((option) => option.value === current)) {
    select.value = current;
  }
}

function setRoleOptions(select) {
  const currentValues = [...select.selectedOptions].map((option) => option.value);
  const current = select.value;
  select.innerHTML = "";
  if (!select.multiple) {
    select.appendChild(new Option("全部", ""));
  }
  state.roles.forEach((role) => select.appendChild(new Option(role, role)));
  if (select.multiple) {
    [...select.options].forEach((option) => {
      option.selected = currentValues.includes(option.value);
    });
  } else if ([...select.options].some((option) => option.value === current)) {
    select.value = current;
  }
}

function renderRoleChecklist(containerId, summaryId) {
  const container = $(containerId);
  container.innerHTML = [
    `<label class="multi-option"><input type="checkbox" value="" data-all="1" checked>全部岗位</label>`,
    ...state.roles.map((role) => `<label class="multi-option"><input type="checkbox" value="${escapeHtml(role)}">${escapeHtml(role)}</label>`),
  ].join("");
  updateRoleSummary(containerId, summaryId);
}

function selectedRoleValues(containerId) {
  return [...$(containerId).querySelectorAll('input[type="checkbox"]:not([data-all]):checked')]
    .map((input) => input.value)
    .filter(Boolean);
}

function updateRoleSummary(containerId, summaryId) {
  const selected = selectedRoleValues(containerId);
  $(summaryId).textContent = selected.length ? selected.join("、") : "全部岗位";
}

function handleRoleChecklistChange(containerId, summaryId, onChange) {
  const container = $(containerId);
  container.addEventListener("change", (event) => {
    const allInput = container.querySelector('input[data-all]');
    const roleInputs = [...container.querySelectorAll('input[type="checkbox"]:not([data-all])')];
    if (event.target.dataset.all) {
      if (event.target.checked) {
        roleInputs.forEach((input) => {
          input.checked = false;
        });
      }
    } else if (allInput) {
      allInput.checked = roleInputs.every((input) => !input.checked);
    }
    updateRoleSummary(containerId, summaryId);
    onChange();
  });
}

async function loadJobRoles() {
  const data = await request("/api/admin/job-roles");
  state.roles = data.items || [];
  setRoleOptions($("userRoleFilter"));
  renderRoleChecklist("weeklyRoleOptions", "weeklyRoleSummary");
  renderRoleChecklist("monthlyRoleOptions", "monthlyRoleSummary");
}

async function loadProvinces() {
  const data = await request("/api/admin/provinces");
  state.provinces = data.items || [];
  setProvinceOptions($("leaderboardProvince"), true);
  setProvinceOptions($("userProvinceFilter"), true);
  setProvinceOptions($("monthlyProvince"), true);
  setProvinceOptions($("ordersProvince"), true);
}

async function loadCompaniesFor(select, province = "", includeAll = false) {
  const params = new URLSearchParams();
  if (province) {
    params.set("province", province);
  }
  const data = await request(`/api/admin/companies?${params.toString()}`);
  state.companies = data.items || [];
  setCompanyOptions(select, includeAll);
}

async function refreshCompanyFilters() {
  await Promise.all([
    loadCompaniesFor($("leaderboardCompany"), $("leaderboardProvince").value, false),
    loadCompaniesFor($("userCompanyFilter"), $("userProvinceFilter").value, true),
    loadCompaniesFor($("monthlyCompany"), $("monthlyProvince").value, true),
    loadCompaniesFor($("ordersCompany"), $("ordersProvince").value, true),
  ]);
}

function renderLeaderboard(items) {
  $("leaderboardBody").innerHTML = (items || []).map((item) => `
    <tr>
      <td>${escapeHtml(item.rank)}</td>
      <td>${escapeHtml(item.name)}</td>
      <td><span class="pill">${escapeHtml(item.job_role_label || roleLabel(item.job_role))}</span></td>
      <td>${escapeHtml(item.weekly_correct_count)}</td>
      <td>${escapeHtml(item.weekly_total_count)}</td>
      <td>${escapeHtml(item.weekly_time_spent)} 秒</td>
      <td>${escapeHtml(item.total_score)}</td>
    </tr>
  `).join("");
}

async function loadLeaderboard() {
  const firstOption = $("leaderboardCompany").options[0];
  const company = $("leaderboardCompany").value || (firstOption ? firstOption.value : "");
  if (!company) {
    renderLeaderboard([]);
    return;
  }
  $("leaderboardCompany").value = company;
  const data = await request(`/api/admin/company-leaderboard?company=${encodeURIComponent(company)}`);
  renderLeaderboard(data.items || []);
}

function updateGlobalLeaderboardControls() {
  const scope = $("globalLeaderboardScope").value || "total";
  $("globalLeaderboardMonthWrap").classList.toggle("hidden", scope !== "month");
}

function renderGlobalLeaderboard(data) {
  const scope = data.scope || $("globalLeaderboardScope").value || "total";
  const isMonth = scope === "month";
  const headers = isMonth
    ? ["排名", "员工", "公司", "岗位", "月答对", "月答题", "用时", "能量值"]
    : ["排名", "员工", "公司", "岗位", "答对数", "答题数", "用时", "能量值"];
  $("globalLeaderboardHead").innerHTML = `<tr>${headers.map((item) => `<th>${escapeHtml(item)}</th>`).join("")}</tr>`;
  $("globalLeaderboardBody").innerHTML = (data.items || []).map((item) => `
    <tr>
      <td>${escapeHtml(item.rank)}</td>
      <td>${escapeHtml(item.name)}</td>
      <td>${escapeHtml(item.company)}</td>
      <td><span class="pill">${escapeHtml(item.job_role_label || roleLabel(item.job_role))}</span></td>
      ${isMonth
        ? `<td>${escapeHtml(item.monthly_correct_count)}</td>
           <td>${escapeHtml(item.monthly_total_count)}</td>
           <td>${escapeHtml(item.monthly_time_spent)} 秒</td>
           <td>${escapeHtml(item.total_score)}</td>`
        : `<td>${escapeHtml(item.correct_count)}</td>
           <td>${escapeHtml(item.total_count)}</td>
           <td>${escapeHtml(item.total_time_spent)} 秒</td>
           <td>${escapeHtml(item.total_score)}</td>`}
    </tr>
  `).join("");
  state.globalLeaderboardTotal = data.total || 0;
  state.globalLeaderboardPage = data.page || state.globalLeaderboardPage;
  state.globalLeaderboardPageSize = data.page_size || 20;
  const totalPages = Math.max(1, Math.ceil(state.globalLeaderboardTotal / state.globalLeaderboardPageSize));
  $("globalLeaderboardSummary").textContent = `共 ${state.globalLeaderboardTotal} 人`;
  $("globalLeaderboardPageInfo").textContent = `第 ${state.globalLeaderboardPage} / ${totalPages} 页`;
  $("prevGlobalLeaderboardPageBtn").disabled = state.globalLeaderboardPage <= 1;
  $("nextGlobalLeaderboardPageBtn").disabled = state.globalLeaderboardPage >= totalPages;
}

async function loadGlobalLeaderboard() {
  updateGlobalLeaderboardControls();
  const scope = $("globalLeaderboardScope").value || "total";
  const params = new URLSearchParams({
    scope,
    page: String(state.globalLeaderboardPage),
    page_size: "20",
  });
  if (scope === "month") {
    params.set("month", $("globalLeaderboardMonth").value || defaultMonth());
  }
  const data = await request(`/api/admin/global-leaderboard?${params.toString()}`);
  renderGlobalLeaderboard(data);
}

function userFormPayload() {
  const form = $("userForm");
  const formData = new FormData(form);
  return {
    phone: String(formData.get("phone") || "").trim(),
    login_username: "",
    login_password: "",
    real_name: String(formData.get("real_name") || "").trim(),
    nickname: String(formData.get("nickname") || "").trim(),
    province: String(formData.get("province") || "").trim(),
    company: String(formData.get("company") || "").trim(),
    job_role: String(formData.get("job_role") || "").trim(),
    profile_verified: formData.get("profile_verified") === "on",
  };
}

function fillUserForm(user = null) {
  const form = $("userForm");
  form.id.value = user ? user.id : "";
  form.real_name.value = user ? user.real_name : "";
  form.nickname.value = user ? user.nickname : "";
  form.phone.value = user ? user.phone : "";
  form.province.value = user ? user.province : "";
  form.company.value = user ? user.company : "";
  form.job_role.value = user ? user.job_role : "";
  form.profile_verified.checked = user ? Boolean(user.profile_verified) : false;
  setFeedback($("userFeedback"), user ? `正在编辑：${user.real_name || user.nickname || user.id}` : "");
}

function renderUsers(items) {
  $("usersBody").innerHTML = (items || []).map((item) => `
    <tr>
      <td>${escapeHtml(item.real_name || item.nickname)}</td>
      <td>${escapeHtml(item.company)}</td>
      <td><span class="pill">${escapeHtml(item.job_role_label || roleLabel(item.job_role))}</span></td>
      <td>${escapeHtml(item.phone)}</td>
      <td>${item.profile_verified ? "已认证" : "未认证"}</td>
      <td>
        <div class="row-actions">
          <button class="ghost-btn edit-user-btn" data-id="${escapeHtml(item.id)}">编辑</button>
          <button class="danger-btn delete-user-btn" data-id="${escapeHtml(item.id)}">删除</button>
        </div>
      </td>
    </tr>
  `).join("");
}

async function loadUsers() {
  const params = buildUserParams(true);
  const data = await request(`/api/admin/users?${params.toString()}`);
  state.users = data.items || [];
  state.userTotal = data.total || 0;
  renderUsers(state.users);
  renderUsersPager();
}

function renderUsersPager() {
  const start = state.userTotal ? state.userOffset + 1 : 0;
  const end = Math.min(state.userOffset + state.userPageSize, state.userTotal);
  const page = Math.floor(state.userOffset / state.userPageSize) + 1;
  const totalPages = Math.max(1, Math.ceil(state.userTotal / state.userPageSize));
  $("usersPagerSummary").textContent = `共 ${state.userTotal} 条，第 ${page}/${totalPages} 页，当前 ${start}-${end} 条`;
  $("prevUsersPageBtn").disabled = state.userOffset <= 0;
  $("nextUsersPageBtn").disabled = state.userOffset + state.userPageSize >= state.userTotal;
}

function buildUserParams(includePaging = true) {
  const params = new URLSearchParams();
  const province = $("userProvinceFilter").value;
  const company = $("userCompanyFilter").value;
  const role = $("userRoleFilter").value;
  const q = $("userSearch").value.trim();
  if (province) params.set("province", province);
  if (company) params.set("company", company);
  if (role) params.set("role", role);
  if (q) params.set("q", q);
  if (includePaging) {
    params.set("limit", String(state.userPageSize));
    params.set("offset", String(state.userOffset));
  }
  return params;
}

async function exportUsersCsv() {
  const params = buildUserParams(false);
  await downloadFile(
    `/api/admin/users/export?${params.toString()}`,
    `账户名单-${new Date().toISOString().slice(0, 10)}.xlsx`,
  );
}

function defaultMonday() {
  const date = new Date();
  const day = date.getDay() || 7;
  date.setDate(date.getDate() - day + 1);
  return date.toISOString().slice(0, 10);
}

function defaultWeek() {
  return dateToWeekValue(new Date());
}

function dateToWeekValue(date) {
  const target = new Date(Date.UTC(date.getFullYear(), date.getMonth(), date.getDate()));
  const day = target.getUTCDay() || 7;
  target.setUTCDate(target.getUTCDate() + 4 - day);
  const yearStart = new Date(Date.UTC(target.getUTCFullYear(), 0, 1));
  const week = Math.ceil((((target - yearStart) / 86400000) + 1) / 7);
  return `${target.getUTCFullYear()}-W${String(week).padStart(2, "0")}`;
}

function weekValueToMonday(value) {
  const match = String(value || "").match(/^(\d{4})-W(\d{2})$/);
  if (!match) return defaultMonday();
  const year = Number(match[1]);
  const week = Number(match[2]);
  const simple = new Date(Date.UTC(year, 0, 1 + (week - 1) * 7));
  const day = simple.getUTCDay() || 7;
  const monday = new Date(simple);
  monday.setUTCDate(simple.getUTCDate() - day + 1);
  return monday.toISOString().slice(0, 10);
}

function defaultMonth() {
  return new Date().toISOString().slice(0, 7);
}

function renderWeekly(data) {
  const range = data.week_start && data.week_end ? `（${data.week_start} 至 ${data.week_end}）` : "";
  $("weeklySummary").textContent = `本周${range}共 ${data.total_companies || 0} 家公司、${data.total_users || 0} 名员工参加`;
  const rows = [];
  (data.companies || []).forEach((group) => {
    (group.participants || []).forEach((item) => {
      rows.push(`
        <tr>
          <td>${escapeHtml(group.company)}</td>
          <td>${escapeHtml(item.name)}</td>
          <td>${escapeHtml(item.job_role_label || roleLabel(item.job_role))}</td>
          <td>${escapeHtml(item.answered_count)}</td>
          <td>${escapeHtml(item.correct_count)}</td>
        </tr>
      `);
    });
  });
  $("weeklyBody").innerHTML = rows.join("");
}

async function loadWeeklyReport() {
  const params = new URLSearchParams();
  params.set("quiz_date", weekValueToMonday($("weeklyWeek").value || defaultWeek()));
  const roles = selectedRoleValues("weeklyRoleOptions");
  if (roles.length) params.set("role", roles.join(","));
  const data = await request(`/api/admin/reports/quiz-participation/weekly?${params.toString()}`);
  renderWeekly(data);
}

async function exportWeeklyXlsx() {
  const params = new URLSearchParams();
  const weekStart = weekValueToMonday($("weeklyWeek").value || defaultWeek());
  params.set("quiz_date", weekStart);
  await downloadFile(
    `/api/admin/reports/quiz-participation/weekly/export?${params.toString()}`,
    `答题参与周报-${weekStart}.xlsx`,
  );
}

function flattenMonthly(data) {
  const rows = [];
  (data.companies || []).forEach((group) => {
    (group.employees || []).forEach((item) => {
      rows.push({ company: group.company, ...item });
    });
  });
  return rows;
}

function renderMonthly(data) {
  $("monthlySummary").textContent = `共 ${data.total_companies || 0} 家公司、${data.total_users || 0} 名员工有参与记录`;
  state.monthlyRows = flattenMonthly(data);
  $("monthlyBody").innerHTML = state.monthlyRows.map((item) => `
    <tr>
      <td>${escapeHtml(item.company)}</td>
      <td>${escapeHtml(item.name)}</td>
      <td>${escapeHtml(item.job_role_label || roleLabel(item.job_role))}</td>
      <td>${escapeHtml(item.participated_weeks)}</td>
      <td>${escapeHtml((item.weeks || []).join(" / "))}</td>
      <td>${escapeHtml(item.answered_count)}</td>
      <td>${escapeHtml(item.correct_count)}</td>
    </tr>
  `).join("");
}

async function loadMonthlyReport() {
  const params = new URLSearchParams();
  params.set("month", $("monthlyMonth").value || defaultMonth());
  if ($("monthlyProvince").value) params.set("province", $("monthlyProvince").value);
  if ($("monthlyCompany").value) params.set("company", $("monthlyCompany").value);
  const roles = selectedRoleValues("monthlyRoleOptions");
  if (roles.length) params.set("role", roles.join(","));
  const data = await request(`/api/admin/reports/quiz-participation/monthly?${params.toString()}`);
  renderMonthly(data);
}

async function exportMonthlyCsv() {
  const month = $("monthlyMonth").value || defaultMonth();
  const params = new URLSearchParams({ month });
  await downloadFile(
    `/api/admin/reports/quiz-participation/monthly/export?${params.toString()}`,
    `答题参与月报-${month}.xlsx`,
  );
}

async function exportAllParticipationXlsx() {
  await downloadFile(
    "/api/admin/reports/quiz-participation/all/export",
    `全部答题统计-${new Date().toISOString().slice(0, 10)}.xlsx`,
  );
}

function buildOrdersParams() {
  const params = new URLSearchParams();
  if ($("ordersProvince").value) params.set("province", $("ordersProvince").value);
  if ($("ordersCompany").value) params.set("company", $("ordersCompany").value);
  if ($("ordersStatus").value) params.set("status", $("ordersStatus").value);
  if ($("ordersDateFrom").value) params.set("date_from", $("ordersDateFrom").value);
  if ($("ordersDateTo").value) params.set("date_to", $("ordersDateTo").value);
  if ($("ordersSearch").value.trim()) params.set("q", $("ordersSearch").value.trim());
  params.set("limit", "500");
  return params;
}

function renderOrders(data) {
  const items = data.items || [];
  state.orderRows = items;
  $("ordersSummary").textContent = `共 ${data.total || 0} 条订单，当前显示 ${items.length} 条`;
  $("ordersBody").innerHTML = items.map((item) => `
    <tr>
      <td>${escapeHtml(formatDateTime(item.created_at))}</td>
      <td>
        <strong>${escapeHtml(item.user_name || item.real_name)}</strong>
        <div class="muted">${escapeHtml(item.phone)}</div>
      </td>
      <td>${escapeHtml(item.company)}</td>
      <td>
        <strong>${escapeHtml(item.product_name)}</strong>
        <div class="muted">${escapeHtml(item.product_id)}</div>
      </td>
      <td>${escapeHtml(item.quantity)}</td>
      <td>${escapeHtml(item.total_cost)}</td>
      <td>
        <div>${escapeHtml(item.receiver_name)} ${escapeHtml(item.receiver_phone)}</div>
        <div class="muted">${escapeHtml(item.receiver_region)} ${escapeHtml(item.receiver_address)}</div>
      </td>
      <td>${escapeHtml(item.receiver_note)}</td>
      <td>
        <select class="order-status-select" data-id="${escapeHtml(item.id)}">
          <option value="pending"${item.status === "pending" ? " selected" : ""}>待处理</option>
          <option value="approved"${item.status === "approved" ? " selected" : ""}>已确认</option>
          <option value="delivered"${item.status === "delivered" ? " selected" : ""}>已发货</option>
          <option value="cancelled"${item.status === "cancelled" ? " selected" : ""}>已取消</option>
        </select>
      </td>
    </tr>
  `).join("");
}

async function loadOrders() {
  const data = await request(`/api/admin/redemption-orders?${buildOrdersParams().toString()}`);
  renderOrders(data);
}

async function refreshOrderBadge() {
  const dot = $("ordersPendingDot");
  if (!dot || !state.token) return;
  const data = await request("/api/admin/redemption-orders/pending-count");
  const count = Number(data.pending_count || 0);
  dot.classList.toggle("hidden", count <= 0);
  dot.title = count > 0 ? `${count} 条待处理兑换订单` : "";
}

function startOrderBadgePolling() {
  if (state.orderBadgeTimer) {
    clearInterval(state.orderBadgeTimer);
  }
  state.orderBadgeTimer = setInterval(() => {
    refreshOrderBadge().catch(() => {});
  }, 60000);
}

async function updateOrderStatus(orderId, status) {
  await request(`/api/admin/redemption-orders/${encodeURIComponent(orderId)}/status`, {
    method: "PUT",
    body: { status },
  });
  await loadOrders();
  await refreshOrderBadge();
}

async function exportOrdersCsv() {
  const params = buildOrdersParams();
  params.delete("limit");
  await downloadFile(
    `/api/admin/redemption-orders/export?${params.toString()}`,
    `兑换订单-${new Date().toISOString().slice(0, 10)}.xlsx`,
  );
}

async function bootDashboard() {
  $("apiBaseLabel").textContent = API_BASE;
  $("weeklyWeek").value = defaultWeek();
  $("monthlyMonth").value = defaultMonth();
  $("globalLeaderboardMonth").value = defaultMonth();
  updateGlobalLeaderboardControls();
  await loadProvinces();
  await loadJobRoles();
  await refreshCompanyFilters();
  await Promise.all([loadLeaderboard(), loadGlobalLeaderboard(), loadUsers(), loadWeeklyReport(), loadMonthlyReport(), loadOrders()]);
  await refreshOrderBadge();
  startOrderBadgePolling();
}

$("loginForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const formData = new FormData(event.currentTarget);
  try {
    const data = await request("/api/admin/auth/login", {
      method: "POST",
      body: {
        username: formData.get("username"),
        password: formData.get("password"),
      },
    });
    state.token = data.token;
    localStorage.setItem(TOKEN_KEY, state.token);
    showAuthed(true);
    await bootDashboard();
  } catch (error) {
    setFeedback($("loginFeedback"), error.message, true);
  }
});

document.querySelectorAll(".tab-btn").forEach((button) => {
  button.addEventListener("click", () => {
    document.querySelectorAll(".tab-btn").forEach((item) => item.classList.remove("active"));
    document.querySelectorAll(".view").forEach((item) => item.classList.remove("active"));
    button.classList.add("active");
    $(`${button.dataset.tab}View`).classList.add("active");
    if (button.dataset.tab === "orders") {
      refreshOrderBadge().catch(() => {});
    }
  });
});

$("logoutBtn").addEventListener("click", () => {
  if (state.orderBadgeTimer) {
    clearInterval(state.orderBadgeTimer);
    state.orderBadgeTimer = null;
  }
  state.token = "";
  localStorage.removeItem(TOKEN_KEY);
  $("ordersPendingDot")?.classList.add("hidden");
  showAuthed(false);
});

$("refreshLeaderboardBtn").addEventListener("click", () => loadLeaderboard().catch((error) => alert(error.message)));
$("leaderboardProvince").addEventListener("change", async () => {
  await loadCompaniesFor($("leaderboardCompany"), $("leaderboardProvince").value, false);
  await loadLeaderboard();
});
$("leaderboardCompany").addEventListener("change", () => loadLeaderboard().catch((error) => alert(error.message)));
$("refreshGlobalLeaderboardBtn").addEventListener("click", () => loadGlobalLeaderboard().catch((error) => alert(error.message)));
$("globalLeaderboardScope").addEventListener("change", () => {
  state.globalLeaderboardPage = 1;
  loadGlobalLeaderboard().catch((error) => alert(error.message));
});
$("globalLeaderboardMonth").addEventListener("change", () => {
  state.globalLeaderboardPage = 1;
  loadGlobalLeaderboard().catch((error) => alert(error.message));
});
$("prevGlobalLeaderboardPageBtn").addEventListener("click", () => {
  state.globalLeaderboardPage = Math.max(1, state.globalLeaderboardPage - 1);
  loadGlobalLeaderboard().catch((error) => alert(error.message));
});
$("nextGlobalLeaderboardPageBtn").addEventListener("click", () => {
  const totalPages = Math.max(1, Math.ceil(state.globalLeaderboardTotal / state.globalLeaderboardPageSize));
  if (state.globalLeaderboardPage < totalPages) {
    state.globalLeaderboardPage += 1;
    loadGlobalLeaderboard().catch((error) => alert(error.message));
  }
});
$("refreshUsersBtn").addEventListener("click", () => {
  state.userOffset = 0;
  loadUsers().catch((error) => setFeedback($("userFeedback"), error.message, true));
});
$("exportUsersBtn").addEventListener("click", () => exportUsersCsv().catch((error) => alert(error.message)));
$("prevUsersPageBtn").addEventListener("click", () => {
  state.userOffset = Math.max(0, state.userOffset - state.userPageSize);
  loadUsers().catch((error) => setFeedback($("userFeedback"), error.message, true));
});
$("nextUsersPageBtn").addEventListener("click", () => {
  if (state.userOffset + state.userPageSize < state.userTotal) {
    state.userOffset += state.userPageSize;
    loadUsers().catch((error) => setFeedback($("userFeedback"), error.message, true));
  }
});
$("userProvinceFilter").addEventListener("change", async () => {
  state.userOffset = 0;
  await loadCompaniesFor($("userCompanyFilter"), $("userProvinceFilter").value, true);
  await loadUsers();
});
$("userCompanyFilter").addEventListener("change", () => {
  state.userOffset = 0;
  loadUsers().catch((error) => setFeedback($("userFeedback"), error.message, true));
});
$("userRoleFilter").addEventListener("change", () => {
  state.userOffset = 0;
  loadUsers().catch((error) => setFeedback($("userFeedback"), error.message, true));
});
$("resetUserBtn").addEventListener("click", () => fillUserForm());
$("loadWeeklyBtn").addEventListener("click", () => loadWeeklyReport().catch((error) => alert(error.message)));
$("weeklyWeek").addEventListener("change", () => loadWeeklyReport().catch((error) => alert(error.message)));
$("weeklyRoleOptions").innerHTML = "";
handleRoleChecklistChange("weeklyRoleOptions", "weeklyRoleSummary", () => loadWeeklyReport().catch((error) => alert(error.message)));
$("exportWeeklyBtn").addEventListener("click", () => exportWeeklyXlsx().catch((error) => alert(error.message)));
$("loadMonthlyBtn").addEventListener("click", () => loadMonthlyReport().catch((error) => alert(error.message)));
$("monthlyProvince").addEventListener("change", async () => {
  await loadCompaniesFor($("monthlyCompany"), $("monthlyProvince").value, true);
  await loadMonthlyReport();
});
$("monthlyCompany").addEventListener("change", () => loadMonthlyReport().catch((error) => alert(error.message)));
$("monthlyRoleOptions").innerHTML = "";
handleRoleChecklistChange("monthlyRoleOptions", "monthlyRoleSummary", () => loadMonthlyReport().catch((error) => alert(error.message)));
$("exportMonthlyBtn").addEventListener("click", () => exportMonthlyCsv().catch((error) => alert(error.message)));
$("exportAllParticipationBtn").addEventListener("click", () => exportAllParticipationXlsx().catch((error) => alert(error.message)));
$("loadOrdersBtn").addEventListener("click", () => loadOrders().catch((error) => alert(error.message)));
$("exportOrdersBtn").addEventListener("click", () => exportOrdersCsv().catch((error) => alert(error.message)));
$("ordersProvince").addEventListener("change", async () => {
  await loadCompaniesFor($("ordersCompany"), $("ordersProvince").value, true);
  await loadOrders();
});
$("ordersCompany").addEventListener("change", () => loadOrders().catch((error) => alert(error.message)));
$("ordersStatus").addEventListener("change", () => loadOrders().catch((error) => alert(error.message)));
$("ordersDateFrom").addEventListener("change", () => loadOrders().catch((error) => alert(error.message)));
$("ordersDateTo").addEventListener("change", () => loadOrders().catch((error) => alert(error.message)));
$("ordersBody").addEventListener("change", async (event) => {
  const select = event.target.closest(".order-status-select");
  if (!select) return;
  try {
    await updateOrderStatus(select.dataset.id, select.value);
  } catch (error) {
    alert(error.message);
    await loadOrders();
  }
});

$("userForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const id = form.id.value;
  const body = userFormPayload();
  try {
    if (id) {
      await request(`/api/admin/users/${encodeURIComponent(id)}`, { method: "PUT", body });
    } else {
      await request("/api/admin/users", { method: "POST", body });
    }
    setFeedback($("userFeedback"), "账户已保存");
    fillUserForm();
    await loadProvinces();
    await loadJobRoles();
    await refreshCompanyFilters();
    await loadUsers();
  } catch (error) {
    setFeedback($("userFeedback"), error.message, true);
  }
});

$("usersBody").addEventListener("click", async (event) => {
  const editButton = event.target.closest(".edit-user-btn");
  const deleteButton = event.target.closest(".delete-user-btn");
  if (editButton) {
    const user = state.users.find((item) => item.id === editButton.dataset.id);
    if (user) fillUserForm(user);
  }
  if (deleteButton) {
    const user = state.users.find((item) => item.id === deleteButton.dataset.id);
    if (!user || !confirm(`确定删除账户：${user.real_name || user.nickname || user.id}？该用户答题记录也会被删除。`)) {
      return;
    }
    try {
      await request(`/api/admin/users/${encodeURIComponent(user.id)}`, { method: "DELETE" });
      await loadUsers();
      await loadProvinces();
      await loadJobRoles();
      await refreshCompanyFilters();
    } catch (error) {
      setFeedback($("userFeedback"), error.message, true);
    }
  }
});

if (state.token) {
  showAuthed(true);
  bootDashboard().catch((error) => {
    state.token = "";
    localStorage.removeItem(TOKEN_KEY);
    showAuthed(false);
    setFeedback($("loginFeedback"), error.message, true);
  });
} else {
  showAuthed(false);
}
