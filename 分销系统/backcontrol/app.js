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
  energyStatsOffset: 0,
  energyStatsTotal: 0,
  energyStatsPageSize: 20,
  monthlyRows: [],
  orderRows: [],
  orderBadgeTimer: null,
  searchOptions: {},
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
  const options = state.companies || [];
  if (select.dataset.options) {
    setSearchableOptions(select, options, includeAll, "全部公司");
  } else {
    select.innerHTML = "";
    if (includeAll) {
      select.appendChild(new Option("全部公司", ""));
    }
    options.forEach((company) => select.appendChild(new Option(company, company)));
  }
  if (options.includes(current)) {
    select.value = current;
  } else if (includeAll && current) {
    select.value = "";
  } else if (!includeAll && options.length) {
    select.value = options[0];
  } else if (!includeAll) {
    select.value = "";
  }
}

function setProvinceOptions(select, includeAll = true) {
  const current = select.value;
  const options = state.provinces || [];
  if (select.dataset.options) {
    setSearchableOptions(select, options, includeAll, "全部省份");
  } else {
    select.innerHTML = "";
    if (includeAll) {
      select.appendChild(new Option("全部省份", ""));
    }
    options.forEach((province) => select.appendChild(new Option(province, province)));
  }
  if (options.includes(current)) {
    select.value = current;
  } else if (includeAll && current) {
    select.value = "";
  } else if (!includeAll && options.length) {
    select.value = options[0];
  } else if (!includeAll) {
    select.value = "";
  }
}

function setSearchableOptions(input, options, includeAll = true, allLabel = "全部") {
  state.searchOptions[input.id] = { options, includeAll, allLabel };
  renderSearchOptions(input, false);
}

function closeSearchOptions() {
  document.querySelectorAll(".search-options").forEach((node) => node.classList.add("hidden"));
}

function renderSearchOptions(input, show = true) {
  const config = state.searchOptions[input.id];
  const menu = input.dataset.options ? $(input.dataset.options) : null;
  if (!config || !menu) return;

  const keyword = input.value.trim().toLowerCase();
  const rows = [];
  if (config.includeAll && (!keyword || config.allLabel.toLowerCase().includes(keyword))) {
    rows.push({ label: config.allLabel, value: "" });
  }
  config.options
    .filter((item) => String(item || "").toLowerCase().includes(keyword))
    .slice(0, 80)
    .forEach((item) => rows.push({ label: item, value: item }));

  menu.innerHTML = rows.length
    ? rows.map((item) => `<button type="button" class="search-option" data-value="${escapeHtml(item.value)}">${escapeHtml(item.label)}</button>`).join("")
    : `<button type="button" class="search-option empty" disabled>没有匹配项</button>`;
  menu.classList.toggle("hidden", !show);
}

function setupSearchableInput(inputId) {
  const input = $(inputId);
  if (!input) return;
  input.addEventListener("focus", () => renderSearchOptions(input, true));
  input.addEventListener("input", () => renderSearchOptions(input, true));
  input.addEventListener("keydown", (event) => {
    if (event.key !== "Enter") return;
    const menu = input.dataset.options ? $(input.dataset.options) : null;
    const firstOption = menu?.querySelector(".search-option:not(.empty)");
    if (firstOption) {
      event.preventDefault();
      firstOption.dispatchEvent(new MouseEvent("mousedown", { bubbles: true }));
    }
  });
  const menu = input.dataset.options ? $(input.dataset.options) : null;
  menu?.addEventListener("mousedown", (event) => {
    const option = event.target.closest(".search-option:not(.empty)");
    if (!option) return;
    event.preventDefault();
    input.value = option.dataset.value || "";
    menu.classList.add("hidden");
    input.dispatchEvent(new Event("change", { bubbles: true }));
  });
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
  setProvinceOptions($("energyProvince"), true);
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
    loadCompaniesFor($("energyCompany"), $("energyProvince").value, true),
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
  const list = $("leaderboardCompanyOptions");
  const firstOption = list ? list.options[0] : null;
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
  if ($("globalLeaderboardSearch").value.trim()) {
    params.set("q", $("globalLeaderboardSearch").value.trim());
  }
  try {
    const data = await request(`/api/admin/global-leaderboard?${params.toString()}`);
    renderGlobalLeaderboard(data);
  } catch (error) {
    $("globalLeaderboardHead").innerHTML = "";
    $("globalLeaderboardBody").innerHTML = "";
    $("globalLeaderboardSummary").textContent = `加载失败：${error.message}`;
    $("globalLeaderboardPageInfo").textContent = `第 ${state.globalLeaderboardPage} 页`;
    $("prevGlobalLeaderboardPageBtn").disabled = true;
    $("nextGlobalLeaderboardPageBtn").disabled = true;
  }
}

function renderEnergyStats(items) {
  $("energyStatsBody").innerHTML = (items || []).map((item, index) => `
    <tr>
      <td>${escapeHtml(state.energyStatsOffset + index + 1)}</td>
      <td>${escapeHtml(item.name)}</td>
      <td>${escapeHtml(item.company)}</td>
      <td><span class="pill">${escapeHtml(item.job_role_label || roleLabel(item.job_role))}</span></td>
      <td>${escapeHtml(item.phone)}</td>
      <td><strong>${escapeHtml(item.total_score)}</strong></td>
      <td>${escapeHtml(item.correct_count)}</td>
      <td>${escapeHtml(item.total_count)}</td>
    </tr>
  `).join("");
}

function renderEnergyStatsPager() {
  const start = state.energyStatsTotal ? state.energyStatsOffset + 1 : 0;
  const end = Math.min(state.energyStatsOffset + state.energyStatsPageSize, state.energyStatsTotal);
  const currentPage = Math.floor(state.energyStatsOffset / state.energyStatsPageSize) + 1;
  const totalPages = Math.max(1, Math.ceil(state.energyStatsTotal / state.energyStatsPageSize));
  $("energyStatsSummary").textContent = `共 ${state.energyStatsTotal} 人，当前 ${start}-${end}`;
  $("energyStatsPageInfo").textContent = `第 ${currentPage} / ${totalPages} 页`;
  $("prevEnergyStatsPageBtn").disabled = state.energyStatsOffset <= 0;
  $("nextEnergyStatsPageBtn").disabled = state.energyStatsOffset + state.energyStatsPageSize >= state.energyStatsTotal;
}

function buildEnergyStatsParams(includePaging = false) {
  const params = new URLSearchParams();
  if (includePaging) {
    params.set("limit", String(state.energyStatsPageSize));
    params.set("offset", String(state.energyStatsOffset));
  }
  if ($("energyProvince").value) params.set("province", $("energyProvince").value);
  if ($("energyCompany").value) params.set("company", $("energyCompany").value);
  if ($("energySearch").value.trim()) params.set("q", $("energySearch").value.trim());
  return params;
}

async function loadEnergyStats() {
  const params = buildEnergyStatsParams(true);
  const data = await request(`/api/admin/energy-stats?${params.toString()}`);
  state.energyStatsTotal = data.total || 0;
  renderEnergyStats(data.items || []);
  renderEnergyStatsPager();
}

async function exportEnergyStatsXlsx() {
  await downloadFile(
    "/api/admin/energy-stats/export",
    `学员能量统计-${new Date().toISOString().slice(0, 10)}.xlsx`,
  );
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
  if ($("weeklySearch").value.trim()) params.set("q", $("weeklySearch").value.trim());
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

function rewardExtraText(item) {
  if (item.type === "monthly_rank_reward") {
    return item.rank ? `第 ${item.rank} 名` : "";
  }
  const prize = item.prize_name || item.prize_level || "";
  const order = item.winner_order ? `第 ${item.winner_order} 位` : "";
  return [prize, order].filter(Boolean).join(" / ");
}

function buildRewardsParams() {
  const params = new URLSearchParams();
  params.set("month", $("rewardsMonth").value || defaultMonth());
  if ($("rewardsType").value) params.set("reward_type", $("rewardsType").value);
  if ($("rewardsSearch").value.trim()) params.set("q", $("rewardsSearch").value.trim());
  return params;
}

function renderRewards(data) {
  const items = data.items || [];
  $("rewardsSummary").textContent =
    `共 ${data.total || 0} 条，月底奖励 ${data.monthly_count || 0} 条 / ${data.monthly_amount || 0} 能量，` +
    `月初抽奖 ${data.lottery_count || 0} 条 / ${data.lottery_amount || 0} 能量，总计 ${data.total_amount || 0} 能量`;
  $("rewardsBody").innerHTML = items.map((item) => `
    <tr>
      <td>${escapeHtml(formatDateTime(item.created_at))}</td>
      <td>
        <strong>${escapeHtml(item.name || item.real_name)}</strong>
        <div class="muted">${escapeHtml(item.phone)}</div>
      </td>
      <td>${escapeHtml(item.company)}</td>
      <td><span class="pill">${escapeHtml(item.job_role_label || roleLabel(item.job_role))}</span></td>
      <td>${escapeHtml(item.type_label)}</td>
      <td>${escapeHtml(rewardExtraText(item))}</td>
      <td><strong>${escapeHtml(item.amount)}</strong></td>
      <td>
        <div>${escapeHtml(item.title)}</div>
        <div class="muted">${escapeHtml(item.description)}</div>
      </td>
    </tr>
  `).join("");
}

async function loadRewards() {
  const data = await request(`/api/admin/reward-records?${buildRewardsParams().toString()}`);
  renderRewards(data);
}

async function exportRewardsXlsx() {
  await downloadFile(
    "/api/admin/reward-records/export",
    `奖励记录-${new Date().toISOString().slice(0, 10)}.xlsx`,
  );
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
  $("rewardsMonth").value = defaultMonth();
  updateGlobalLeaderboardControls();
  await loadProvinces();
  await loadJobRoles();
  await refreshCompanyFilters();
  await Promise.all([loadLeaderboard(), loadGlobalLeaderboard(), loadEnergyStats(), loadUsers(), loadWeeklyReport(), loadMonthlyReport(), loadOrders(), loadRewards()]);
  await refreshOrderBadge();
  startOrderBadgePolling();
}

[
  "leaderboardProvince",
  "leaderboardCompany",
  "energyProvince",
  "energyCompany",
  "monthlyProvince",
  "monthlyCompany",
].forEach(setupSearchableInput);

document.addEventListener("click", (event) => {
  if (!event.target.closest(".filters label")) {
    closeSearchOptions();
  }
});

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
$("globalLeaderboardSearch").addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    state.globalLeaderboardPage = 1;
    loadGlobalLeaderboard().catch((error) => alert(error.message));
  }
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
$("refreshEnergyStatsBtn").addEventListener("click", () => loadEnergyStats().catch((error) => alert(error.message)));
$("exportEnergyStatsBtn").addEventListener("click", () => exportEnergyStatsXlsx().catch((error) => alert(error.message)));
$("searchEnergyStatsBtn").addEventListener("click", () => {
  state.energyStatsOffset = 0;
  loadEnergyStats().catch((error) => alert(error.message));
});
$("energyProvince").addEventListener("change", async () => {
  state.energyStatsOffset = 0;
  await loadCompaniesFor($("energyCompany"), $("energyProvince").value, true);
  await loadEnergyStats();
});
$("energyCompany").addEventListener("change", () => {
  state.energyStatsOffset = 0;
  loadEnergyStats().catch((error) => alert(error.message));
});
$("energySearch").addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    state.energyStatsOffset = 0;
    loadEnergyStats().catch((error) => alert(error.message));
  }
});
$("prevEnergyStatsPageBtn").addEventListener("click", () => {
  state.energyStatsOffset = Math.max(0, state.energyStatsOffset - state.energyStatsPageSize);
  loadEnergyStats().catch((error) => alert(error.message));
});
$("nextEnergyStatsPageBtn").addEventListener("click", () => {
  if (state.energyStatsOffset + state.energyStatsPageSize < state.energyStatsTotal) {
    state.energyStatsOffset += state.energyStatsPageSize;
    loadEnergyStats().catch((error) => alert(error.message));
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
$("weeklySearch").addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    loadWeeklyReport().catch((error) => alert(error.message));
  }
});
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
$("exportRewardsBtn").addEventListener("click", () => exportRewardsXlsx().catch((error) => alert(error.message)));
$("loadRewardsBtn").addEventListener("click", () => loadRewards().catch((error) => alert(error.message)));
$("rewardsMonth").addEventListener("change", () => loadRewards().catch((error) => alert(error.message)));
$("rewardsType").addEventListener("change", () => loadRewards().catch((error) => alert(error.message)));
$("rewardsSearch").addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    loadRewards().catch((error) => alert(error.message));
  }
});
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

// ═══════════════════════════════════════════════════════════════════════════
// 认可计划管理
// ═══════════════════════════════════════════════════════════════════════════

const AWARD_TYPE_LABELS = {
  order_guardian: "报备秩序卫士",
  distributor_pioneer: "分销商支持先锋",
  distributor_mentor: "分销商成长伯乐",
  efficiency_innovator: "效率提升创新",
};

// ── 子 Tab 切换 ──────────────────────────────────────────────────────────

document.querySelectorAll(".sub-tab-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".sub-tab-btn").forEach((b) => b.classList.remove("active"));
    document.querySelectorAll(".recognition-subview").forEach((v) => v.classList.remove("active"));
    btn.classList.add("active");
    const panelId = btn.dataset.subtab === "recognition-users" ? "recognitionUsersPanel"
      : btn.dataset.subtab === "recognition-criteria" ? "recognitionCriteriaPanel"
      : btn.dataset.subtab === "recognition-rules" ? "recognitionRulesPanel"
      : "recognitionCalcPanel";
    $(panelId).classList.add("active");
    if (btn.dataset.subtab === "recognition-users") loadRecognitionUsers();
    if (btn.dataset.subtab === "recognition-criteria") loadCriteria();
    if (btn.dataset.subtab === "recognition-rules") loadRules();
    if (btn.dataset.subtab === "recognition-calc") loadCalcPanel();
  });
});

// ── 用户角色管理 ─────────────────────────────────────────────────────────

$("recognitionRoleFilter").addEventListener("change", () => loadRecognitionUsers());
$("refreshRecognitionUsersBtn").addEventListener("click", () => loadRecognitionUsers());

async function loadRecognitionUsers() {
  const role = $("recognitionRoleFilter").value;
  const params = role ? `?role=${role}` : "";
  const users = await request(`/api/recognition/users${params}`);
  $("recognitionUsersBody").innerHTML = (users || []).map((u) => `
    <tr>
      <td>${escapeHtml(u.real_name)}</td>
      <td>${escapeHtml(u.company)}</td>
      <td>
        <select class="role-select" data-user-id="${escapeHtml(u.id)}">
          <option value="distributor"${u.recognition_role === "distributor" ? " selected" : ""}>分销商</option>
          <option value="sales"${u.recognition_role === "sales" ? " selected" : ""}>销售</option>
          <option value="specialist"${u.recognition_role === "specialist" ? " selected" : ""}>专员</option>
          <option value="manager"${u.recognition_role === "manager" ? " selected" : ""}>经理</option>
        </select>
      </td>
      <td>${escapeHtml(u.recognition_score)}</td>
      <td><span class="muted">已保存</span></td>
    </tr>
  `).join("");

  // 绑定角色切换事件
  $("recognitionUsersBody").querySelectorAll(".role-select").forEach((sel) => {
    sel.addEventListener("change", async () => {
      try {
        await request(`/api/recognition/users/${encodeURIComponent(sel.dataset.userId)}/role`, {
          method: "PUT",
          body: { recognition_role: sel.value },
        });
        sel.parentElement.nextElementSibling.nextElementSibling.querySelector("span").textContent = "已保存";
      } catch (err) {
        alert("更新角色失败：" + err.message);
        loadRecognitionUsers();
      }
    });
  });
}

// ── 评分标准管理 ─────────────────────────────────────────────────────────

$("criteriaAwardType").addEventListener("change", () => loadCriteria());
$("refreshCriteriaBtn").addEventListener("click", () => loadCriteria());

$("addCriteriaBtn").addEventListener("click", async () => {
  const body = {
    award_type: $("newCriteriaAwardType").value,
    item_name: $("newCriteriaName").value.trim(),
    item_key: $("newCriteriaKey").value.trim(),
    item_type: $("newCriteriaType").value,
    points_per_unit: parseInt($("newCriteriaPoints").value) || 0,
    unit_description: $("newCriteriaUnit").value.trim() || null,
    max_points: $("newCriteriaMax").value ? parseInt($("newCriteriaMax").value) : null,
    sort_order: parseInt($("newCriteriaSort").value) || 0,
    is_active: $("newCriteriaActive").checked,
  };
  if (!body.item_name || !body.item_key) {
    setFeedback($("criteriaFeedback"), "请填写名称和键名", true);
    return;
  }
  try {
    await request("/api/recognition/scoring-criteria", { method: "POST", body });
    setFeedback($("criteriaFeedback"), "添加成功");
    $("newCriteriaName").value = "";
    $("newCriteriaKey").value = "";
    loadCriteria();
  } catch (err) {
    setFeedback($("criteriaFeedback"), err.message, true);
  }
});

async function loadCriteria() {
  const awardType = $("criteriaAwardType").value;
  const params = awardType ? `?award_type=${awardType}` : "";
  const data = await request(`/api/recognition/scoring-criteria${params}`);
  $("criteriaBody").innerHTML = (data || []).map((c) => `
    <tr>
      <td>${escapeHtml(AWARD_TYPE_LABELS[c.award_type] || c.award_type)}</td>
      <td>${escapeHtml(c.item_name)}</td>
      <td><code>${escapeHtml(c.item_key)}</code></td>
      <td>${escapeHtml(c.item_type)}</td>
      <td>${escapeHtml(c.points_per_unit)}</td>
      <td>${c.max_points ? escapeHtml(c.max_points) : "无"}</td>
      <td>${c.is_active ? "是" : "否"}</td>
      <td><button class="danger-btn delete-criteria-btn" data-id="${c.id}">删除</button></td>
    </tr>
  `).join("");
  $("criteriaBody").querySelectorAll(".delete-criteria-btn").forEach((btn) => {
    btn.addEventListener("click", async () => {
      if (!confirm("确定删除该评分标准？")) return;
      try {
        await request(`/api/recognition/scoring-criteria/${btn.dataset.id}`, { method: "DELETE" });
        loadCriteria();
      } catch (err) { alert(err.message); }
    });
  });
}

// ── 规则配置 ─────────────────────────────────────────────────────────────

async function loadRules() {
  const data = await request("/api/recognition/rules");
  $("rulesBody").innerHTML = (data || []).map((r) => `
    <tr>
      <td><code>${escapeHtml(r.rule_key)}</code></td>
      <td><strong>${escapeHtml(r.rule_value)}</strong></td>
      <td>${escapeHtml(r.description)}</td>
      <td><input class="rule-new-value" data-key="${escapeHtml(r.rule_key)}" value="${escapeHtml(r.rule_value)}" style="width:80px"></td>
      <td><button class="ghost-btn save-rule-btn" data-key="${escapeHtml(r.rule_key)}">保存</button></td>
    </tr>
  `).join("");
  $("rulesBody").querySelectorAll(".save-rule-btn").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const key = btn.dataset.key;
      const input = document.querySelector(`.rule-new-value[data-key="${key}"]`);
      try {
        await request(`/api/recognition/rules/${encodeURIComponent(key)}`, {
          method: "PUT",
          body: { rule_value: input.value },
        });
        alert("规则已更新");
        loadRules();
      } catch (err) { alert(err.message); }
    });
  });
}

// ── 评选计算 ─────────────────────────────────────────────────────────────

function defaultCalcMonth() {
  return new Date().toISOString().slice(0, 7);
}

async function loadCalcPanel() {
  $("calcMonth").value = defaultCalcMonth();
  loadUnpublishedAwards();
}

$("calcMonthlyBtn").addEventListener("click", async () => {
  const month = $("calcMonth").value;
  if (!month) { setFeedback($("calcMonthlyFeedback"), "请选择月份", true); return; }
  try {
    const data = await request("/api/recognition/awards/calculate-monthly", {
      method: "POST", body: { month },
    });
    $("calcMonthlyResult").textContent = JSON.stringify(data.results, null, 2);
    setFeedback($("calcMonthlyFeedback"), "计算完成");
    loadUnpublishedAwards();
  } catch (err) { setFeedback($("calcMonthlyFeedback"), err.message, true); }
});

$("calcQuarterlyBtn").addEventListener("click", async () => {
  const year = parseInt($("calcQuarterYear").value);
  const quarter = parseInt($("calcQuarter").value);
  if (!year || !quarter) { setFeedback($("calcQuarterlyFeedback"), "请填写年份和季度", true); return; }
  try {
    const data = await request("/api/recognition/awards/calculate-quarterly", {
      method: "POST", body: { year, quarter },
    });
    $("calcQuarterlyResult").textContent = JSON.stringify(data.results, null, 2);
    setFeedback($("calcQuarterlyFeedback"), "计算完成");
    loadUnpublishedAwards();
  } catch (err) { setFeedback($("calcQuarterlyFeedback"), err.message, true); }
});

$("calcAnnualBtn").addEventListener("click", async () => {
  const year = parseInt($("calcAnnualYear").value);
  if (!year) { setFeedback($("calcAnnualFeedback"), "请填写年份", true); return; }
  try {
    const data = await request("/api/recognition/awards/calculate-annual", {
      method: "POST", body: { year },
    });
    $("calcAnnualResult").textContent = JSON.stringify(data.results, null, 2);
    setFeedback($("calcAnnualFeedback"), "计算完成");
    loadUnpublishedAwards();
  } catch (err) { setFeedback($("calcAnnualFeedback"), err.message, true); }
});

$("refreshUnpublishedBtn").addEventListener("click", () => loadUnpublishedAwards());

async function loadUnpublishedAwards() {
  const data = await request("/api/recognition/awards/results?published=false");
  $("unpublishedAwardsBody").innerHTML = (data || []).map((a) => `
    <tr>
      <td><input type="checkbox" class="award-checkbox" data-id="${a.id}"></td>
      <td>${escapeHtml(a.user_name)}</td>
      <td>${escapeHtml(a.award_name)}</td>
      <td>${a.rank || "-"}</td>
      <td>${escapeHtml(a.points_awarded)}</td>
      <td>${escapeHtml(a.award_month || a.award_quarter || a.award_year)}</td>
    </tr>
  `).join("");
}

$("selectAllAwards").addEventListener("change", function () {
  document.querySelectorAll(".award-checkbox").forEach((cb) => { cb.checked = this.checked; });
});

$("publishAwardsBtn").addEventListener("click", async () => {
  const ids = [...document.querySelectorAll(".award-checkbox:checked")].map((cb) => parseInt(cb.dataset.id));
  if (!ids.length) { setFeedback($("publishFeedback"), "请选择要发布的奖项", true); return; }
  try {
    const data = await request("/api/recognition/awards/publish", {
      method: "POST", body: { award_ids: ids },
    });
    setFeedback($("publishFeedback"), data.message);
    loadUnpublishedAwards();
  } catch (err) { setFeedback($("publishFeedback"), err.message, true); }
});

// 首次加载
async function loadRecognitionData() {
  await loadRecognitionUsers();
}
