/* ==========================================================================
   SIM SMS GATEWAY — MISSION CONTROL JAVASCRIPT
   Real-time Telemetry, Charts, Device Management, and SMS Dispatch
   ========================================================================== */

(function () {
  'use strict';

  // --- Configuration & State ---
  const API_BASE = '/api/v1';
  let authToken = localStorage.getItem('sms_admin_token') || null;
  let currentTab = 'overview';
  let currentTenantId = null;
  let currentDrawerMsgId = null;
  let isKillSwitchActive = false;
  let refreshTimer = null;
  let pairingCountdownInterval = null;
  let trafficChartInstance = null;
  let statusChartInstance = null;
  let activeStatusFilter = '';
  let activeQuarantineFilter = 'pending_approval';
  let cachedMessages = [];
  let cachedQuarantineMessages = [];
  let cachedModerationRules = [];

  // --- Helper: MNO Telecom Badge Mapper ---
  function getMnoBadge(mno) {
    if (!mno) return '<span class="mno-badge">UNKNOWN</span>';
    const m = mno.toUpperCase();
    if (m.includes('VODACOM')) return '<span class="mno-badge badge-vodacom">Vodacom TZ</span>';
    if (m.includes('AIRTEL')) return '<span class="mno-badge badge-airtel">Airtel TZ</span>';
    if (m.includes('TIGO') || m.includes('YAS')) return '<span class="mno-badge badge-tigo">Mixx/Tigo TZ</span>';
    if (m.includes('HALOTEL')) return '<span class="mno-badge badge-halotel">Halotel TZ</span>';
    if (m.includes('TTCL')) return '<span class="mno-badge badge-ttcl">TTCL TZ</span>';
    if (m.includes('INTERNATIONAL')) return '<span class="mno-badge badge-intl">International</span>';
    return `<span class="mno-badge">${escapeHtml(mno)}</span>`;
  }

  // --- DOM Elements ---
  const authView = document.getElementById('auth-view');
  const dashboardView = document.getElementById('dashboard-view');
  const loginForm = document.getElementById('login-form');
  const loginUsername = document.getElementById('login-username');
  const loginPassword = document.getElementById('login-password');
  const togglePasswordBtn = document.getElementById('toggle-password-btn');
  const logoutBtn = document.getElementById('logout-btn');
  const refreshNowBtn = document.getElementById('refresh-now-btn');
  const mobileMenuBtn = document.getElementById('mobile-menu-btn');
  const appSidebar = document.getElementById('app-sidebar');
  const quickComposeBtn = document.getElementById('quick-compose-btn');
  const overviewPairDeviceBtn = document.getElementById('overview-pair-device-btn');
  const devicesGenerateCodeBtn = document.getElementById('devices-generate-code-btn');
  const messagesComposeBtn = document.getElementById('messages-compose-btn');
  const webhooksAddBtn = document.getElementById('webhooks-add-btn');
  const apikeysCreateBtn = document.getElementById('apikeys-create-btn');
  const toastContainer = document.getElementById('toast-container');

  // --- Helper: Toast Notifications ---
  function showToast(message, type = 'info', duration = 4000) {
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.innerHTML = `
      <div style="flex: 1; font-weight: 500;">${escapeHtml(message)}</div>
    `;
    toastContainer.appendChild(toast);

    setTimeout(() => {
      toast.style.opacity = '0';
      toast.style.transform = 'translateX(50px)';
      toast.style.transition = 'all 0.3s ease';
      setTimeout(() => toast.remove(), 300);
    }, duration);
  }

  function escapeHtml(str) {
    if (!str) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  // --- API Client with Bearer Authentication ---
  async function apiFetch(endpoint, options = {}) {
    options.headers = options.headers || {};
    if (authToken) {
      options.headers['Authorization'] = `Bearer ${authToken}`;
    }
    if (!(options.body instanceof FormData) && options.body && typeof options.body === 'object') {
      options.headers['Content-Type'] = 'application/json';
      options.body = JSON.stringify(options.body);
    }

    try {
      const response = await fetch(`${API_BASE}${endpoint}`, options);

      if (response.status === 401 && !endpoint.includes('/auth/login')) {
        handleLogout();
        showToast('Session expired. Please log in again.', 'error');
        throw new Error('Unauthorized');
      }

      if (response.status === 204) {
        return null;
      }

      const data = await response.json().catch(() => ({}));

      if (!response.ok) {
        const errorMsg = data.detail || data.message || `Request failed with code ${response.status}`;
        throw new Error(errorMsg);
      }

      return data;
    } catch (err) {
      console.error(`API Error [${endpoint}]:`, err);
      throw err;
    }
  }

  // --- Authentication Handlers ---
  async function checkAuth() {
    if (!authToken) {
      showAuthView();
      return;
    }
    try {
      await apiFetch('/auth/me');
      showDashboardView();
      loadActiveTab();
      startAutoRefresh();
    } catch (err) {
      handleLogout();
    }
  }

  function showAuthView() {
    authView.style.display = 'flex';
    dashboardView.style.display = 'none';
    stopAutoRefresh();
  }

  function showDashboardView() {
    authView.style.display = 'none';
    dashboardView.style.display = 'flex';
  }

  function handleLogout() {
    authToken = null;
    localStorage.removeItem('sms_admin_token');
    showAuthView();
  }

  if (loginForm) {
    loginForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const username = loginUsername.value.trim();
      const password = loginPassword.value.trim();

      if (!username || !password) {
        showToast('Please enter both username and password.', 'error');
        return;
      }

      const submitBtn = document.getElementById('login-submit-btn');
      const originalText = submitBtn.innerHTML;
      submitBtn.disabled = true;
      submitBtn.innerHTML = `<span>Authenticating...</span>`;

      try {
        const res = await apiFetch('/auth/login', {
          method: 'POST',
          body: { username, password },
        });

        authToken = res.access_token;
        localStorage.setItem('sms_admin_token', authToken);
        showToast('Signed in successfully! Welcome, Admin.', 'success');
        showDashboardView();
        loadActiveTab();
        startAutoRefresh();
      } catch (err) {
        showToast(err.message || 'Login failed. Check credentials.', 'error');
        const card = document.querySelector('.login-card');
        card.style.animation = 'none';
        void card.offsetWidth; // trigger reflow
        card.style.animation = 'slideUp 0.3s ease';
      } finally {
        submitBtn.disabled = false;
        submitBtn.innerHTML = originalText;
      }
    });
  }

  if (togglePasswordBtn) {
    togglePasswordBtn.addEventListener('click', () => {
      const type = loginPassword.type === 'password' ? 'text' : 'password';
      loginPassword.type = type;
    });
  }

  if (logoutBtn) {
    logoutBtn.addEventListener('click', () => {
      handleLogout();
      showToast('Logged out successfully.', 'info');
    });
  }

  // --- Mobile Sidebar Toggle ---
  if (mobileMenuBtn && appSidebar) {
    mobileMenuBtn.addEventListener('click', () => {
      appSidebar.classList.toggle('open');
    });
  }

  // --- Tab Navigation ---
  document.querySelectorAll('.sidebar-nav .nav-item').forEach((item) => {
    item.addEventListener('click', (e) => {
      e.preventDefault();
      const tab = item.getAttribute('data-tab');
      if (tab) {
        switchTab(tab);
        if (window.innerWidth <= 768 && appSidebar) {
          appSidebar.classList.remove('open');
        }
      }
    });
  });

  function switchTab(tabName) {
    currentTab = tabName;
    document.querySelectorAll('.sidebar-nav .nav-item').forEach((el) => {
      el.classList.toggle('active', el.getAttribute('data-tab') === tabName);
    });

    document.querySelectorAll('.page-tab').forEach((el) => {
      el.style.display = 'none';
    });

    const activeSection = document.getElementById(`tab-${tabName}`);
    if (activeSection) {
      activeSection.style.display = 'block';
    }

    loadActiveTab();
  }

  function loadActiveTab() {
    switch (currentTab) {
      case 'overview':
        fetchOverviewStats();
        break;
      case 'devices':
        fetchDevices();
        break;
      case 'messages':
        fetchMessages();
        break;
      case 'quarantine':
        fetchQuarantineMessages();
        break;
      case 'tenants':
        fetchTenants();
        fetchUsers();
        break;
      case 'firewall':
        fetchDndList();
        fetchModerationRules();
        break;
      case 'ledger':
        fetchLedger();
        break;
      case 'inbox':
        fetchInbox();
        break;
      case 'webhooks':
        fetchWebhooks();
        break;
      case 'apikeys':
        fetchApiKeys();
        break;
      case 'settings':
        fetchSystemSettings();
        break;
    }
  }

  // --- Polling & Refresh Loop ---
  function startAutoRefresh() {
    stopAutoRefresh();
    refreshTimer = setInterval(() => {
      loadActiveTab();
    }, 5000);
  }

  function stopAutoRefresh() {
    if (refreshTimer) {
      clearInterval(refreshTimer);
      refreshTimer = null;
    }
  }

  if (refreshNowBtn) {
    refreshNowBtn.addEventListener('click', () => {
      refreshNowBtn.classList.add('spinning');
      loadActiveTab();
      setTimeout(() => refreshNowBtn.classList.remove('spinning'), 800);
      showToast('Dashboard data refreshed.', 'info', 2000);
    });
  }

  // ========================================================================
  // 1. OVERVIEW TAB & CHARTS
  // ========================================================================
  async function fetchOverviewStats() {
    try {
      const data = await apiFetch('/admin/stats');
      const summary = data.summary;

      // Update counters
      document.getElementById('stat-total-sms').textContent = summary.total_messages.toLocaleString();
      document.getElementById('stat-success-rate').textContent = `${summary.success_rate_percent}%`;
      document.getElementById('stat-delivered-count').textContent = `${summary.delivered} delivered`;
      document.getElementById('stat-queue-count').textContent = summary.queued.toLocaleString();
      document.getElementById('stat-sending-count').textContent = `${summary.sending} in transit`;
      document.getElementById('stat-devices-online').textContent = summary.devices.online.toString();
      document.getElementById('stat-devices-total').textContent = `${summary.devices.total} registered`;
      document.getElementById('stat-inbound-count').textContent = summary.incoming_messages.toLocaleString();

      // Badges in sidebar
      document.getElementById('nav-badge-devices').textContent = summary.devices.online;
      document.getElementById('nav-badge-queued').textContent = summary.queued;
      document.getElementById('nav-badge-inbox').textContent = summary.incoming_messages;

      // Render or Update Charts
      renderTrafficChart(data.charts.timeseries);
      renderStatusChart(data.charts.status_donut);

      // Render Recent Activity Stream
      renderActivityStream(data.recent_activities);
    } catch (err) {
      console.error('Failed to load overview stats:', err);
    }
  }

  function renderTrafficChart(tsData) {
    const ctx = document.getElementById('trafficChart');
    if (!ctx) return;

    if (trafficChartInstance) {
      trafficChartInstance.data.labels = tsData.labels;
      trafficChartInstance.data.datasets[0].data = tsData.sent;
      trafficChartInstance.data.datasets[1].data = tsData.delivered;
      trafficChartInstance.data.datasets[2].data = tsData.failed;
      trafficChartInstance.update();
      return;
    }

    trafficChartInstance = new Chart(ctx, {
      type: 'line',
      data: {
        labels: tsData.labels,
        datasets: [
          {
            label: 'Sent',
            data: tsData.sent,
            borderColor: '#38bdf8',
            backgroundColor: 'rgba(56, 189, 248, 0.1)',
            fill: true,
            tension: 0.35,
            borderWidth: 2,
            pointRadius: 3,
          },
          {
            label: 'Delivered',
            data: tsData.delivered,
            borderColor: '#34d399',
            backgroundColor: 'rgba(52, 211, 153, 0.15)',
            fill: true,
            tension: 0.35,
            borderWidth: 2,
            pointRadius: 3,
          },
          {
            label: 'Failed',
            data: tsData.failed,
            borderColor: '#f43f5e',
            backgroundColor: 'transparent',
            tension: 0.35,
            borderWidth: 2,
            pointRadius: 3,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: {
            position: 'top',
            labels: { color: '#94a3b8', font: { family: 'Inter', size: 11 } },
          },
        },
        scales: {
          x: {
            grid: { color: 'rgba(255, 255, 255, 0.05)' },
            ticks: { color: '#64748b', font: { family: 'JetBrains Mono', size: 10 } },
          },
          y: {
            beginAtZero: true,
            grid: { color: 'rgba(255, 255, 255, 0.05)' },
            ticks: { color: '#64748b', precision: 0 },
          },
        },
      },
    });
  }

  function renderStatusChart(donutData) {
    const ctx = document.getElementById('statusChart');
    if (!ctx) return;

    if (statusChartInstance) {
      statusChartInstance.data.datasets[0].data = donutData.data;
      statusChartInstance.update();
      return;
    }

    statusChartInstance = new Chart(ctx, {
      type: 'doughnut',
      data: {
        labels: donutData.labels,
        datasets: [
          {
            data: donutData.data,
            backgroundColor: [
              '#10b981', // Delivered
              '#06b6d4', // Sent
              '#f59e0b', // Queued
              '#ef4444', // Failed
            ],
            borderWidth: 0,
            hoverOffset: 4,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: {
            position: 'bottom',
            labels: { color: '#94a3b8', font: { family: 'Inter', size: 11 }, padding: 14 },
          },
        },
        cutout: '70%',
      },
    });
  }

  function renderActivityStream(activities) {
    const tbody = document.getElementById('overview-activity-tbody');
    if (!tbody) return;

    if (!activities || activities.length === 0) {
      tbody.innerHTML = `<tr><td colspan="4" style="text-align: center; color: var(--text-dim); padding: 20px;">No recent gateway events.</td></tr>`;
      return;
    }

    tbody.innerHTML = activities
      .map((a) => {
        const timeStr = new Date(a.created_at).toLocaleTimeString();
        const detailsStr = JSON.stringify(a.details || {}).replace(/[{}"']/g, ' ');
        return `
          <tr>
            <td class="mono-cell" style="font-size: 12px; color: var(--text-dim);">${escapeHtml(timeStr)}</td>
            <td><span class="badge badge-sent">${escapeHtml(a.action)}</span></td>
            <td class="mono-cell" style="font-size: 12px;">${escapeHtml(a.actor)}</td>
            <td style="font-size: 12px; color: var(--text-muted);">${escapeHtml(detailsStr)}</td>
          </tr>
        `;
      })
      .join('');
  }

  // ========================================================================
  // 2. ANDROID DEVICES TAB
  // ========================================================================
  async function fetchDevices() {
    try {
      const devices = await apiFetch('/devices');
      const tbody = document.getElementById('devices-tbody');
      const matrixContainer = document.getElementById('devices-matrix-container');

      if (!devices || devices.length === 0) {
        if (tbody) {
          tbody.innerHTML = `
            <tr>
              <td colspan="8" style="text-align: center; padding: 40px; color: var(--text-dim);">
                No Android devices paired yet. Click <strong>Generate Pairing Code</strong> above to connect your phone.
              </td>
            </tr>
          `;
        }
        if (matrixContainer) {
          matrixContainer.innerHTML = '';
        }
        return;
      }

      // Render Dual-SIM & Throttle Fleet Matrix
      if (matrixContainer) {
        matrixContainer.innerHTML = devices
          .map((d) => {
            const isOnline = d.is_online && !d.is_revoked;
            const batteryLevel = d.battery_level !== null ? d.battery_level : 100;
            const batteryColor = batteryLevel > 40 ? 'var(--color-emerald)' : batteryLevel > 15 ? 'var(--color-amber)' : 'var(--color-rose)';
            const maxLimit = d.max_sms_per_30_min || 28;

            const slots = (d.sim_slots_telemetry && d.sim_slots_telemetry.length > 0)
              ? d.sim_slots_telemetry
              : [{
                  slot: 0,
                  carrier: d.carrier_name || 'SIM 1',
                  number: d.phone_number || 'Detected',
                  daily_sent: 0,
                  limit: 500,
                  active: d.sim_ready
                }];

            const totalRecent = slots.reduce((acc, s) => acc + (s.daily_sent || 0), 0) % maxLimit;
            const throttlePct = Math.min(100, Math.round((totalRecent / maxLimit) * 100));
            const throttleClass = throttlePct > 80 ? 'danger' : throttlePct > 55 ? 'warn' : '';

            const slotsHtml = slots.map((s) => {
              const carrier = s.carrier || d.carrier_name || 'Carrier';
              const carrierUpper = carrier.toUpperCase();
              const carrierMno = carrierUpper.includes('VODA') ? 'VODACOM_TZ' : carrierUpper.includes('AIRTEL') ? 'AIRTEL_TZ' : carrierUpper.includes('TIGO') || carrierUpper.includes('YAS') ? 'YAS_TIGO_TZ' : carrierUpper.includes('HALO') ? 'HALOTEL_TZ' : 'UNKNOWN';
              const carrierBadge = getMnoBadge(carrierMno);
              const dailySent = s.daily_sent || 0;
              const dailyLimit = s.limit || 500;
              const dailyPct = Math.min(100, Math.round((dailySent / dailyLimit) * 100));

              return `
                <div class="sim-slot-chip">
                  <div class="sim-slot-header">
                    <span>SIM Slot ${s.slot !== undefined ? s.slot : 0}: ${escapeHtml(carrier)}</span>
                    ${carrierBadge}
                  </div>
                  <div style="font-size: 13px; font-weight: 600; color: #fff;">${escapeHtml(s.number || d.phone_number || 'No Number')}</div>
                  <div style="font-size: 11px; color: var(--text-dim); display: flex; justify-content: space-between; margin-top: 4px;">
                    <span>Daily Volume</span>
                    <span style="color: #cbd5e1; font-weight: 600;">${dailySent} / ${dailyLimit} SMS</span>
                  </div>
                  <div class="throttle-bar-outer" style="height: 5px;">
                    <div class="throttle-bar-fill" style="width: ${dailyPct}%;"></div>
                  </div>
                  <div style="font-size: 11px; margin-top: 4px; display: flex; justify-content: space-between;">
                    <span style="color: var(--text-dim);">Radio Status</span>
                    <span style="color: ${s.active !== false ? 'var(--color-emerald)' : 'var(--color-rose)'}; font-weight: 600;">
                      ${s.active !== false ? 'READY (ON-NET)' : 'OFFLINE'}
                    </span>
                  </div>
                </div>
              `;
            }).join('');

            return `
              <div class="fleet-device-card">
                <div class="fleet-card-header">
                  <div>
                    <div class="fleet-card-title">
                      ${escapeHtml(d.name)}
                      ${d.is_shared_pool ? '<span class="badge" style="background: rgba(99, 102, 241, 0.2); color: #818cf8; font-size: 10px;">Shared Pool</span>' : '<span class="badge" style="background: rgba(16, 185, 129, 0.2); color: #34d399; font-size: 10px;">Dedicated</span>'}
                    </div>
                    <div class="fleet-card-sub">${escapeHtml(d.model || 'Android Phone')} · OS ${escapeHtml(d.os_version || '11+')} · App v${escapeHtml(d.app_version || '1.0')}</div>
                  </div>
                  <div>
                    ${d.is_revoked
                      ? '<span class="badge badge-revoked">Revoked</span>'
                      : isOnline
                      ? '<span class="badge badge-online"><span class="status-dot"></span> Online</span>'
                      : '<span class="badge badge-offline">Offline</span>'}
                  </div>
                </div>

                <div class="fleet-telemetry-row">
                  <div class="fleet-telemetry-item">
                    <span>Battery</span>
                    <strong style="color: ${batteryColor};">${batteryLevel}%</strong>
                  </div>
                  <div class="fleet-telemetry-item">
                    <span>Signal</span>
                    <strong>${d.signal_level !== null ? d.signal_level : 4} / 4 bars</strong>
                  </div>
                  <div class="fleet-telemetry-item">
                    <span>Network</span>
                    <strong>${escapeHtml(d.network_type || 'LTE')}</strong>
                  </div>
                </div>

                <div>
                  <div style="display: flex; justify-content: space-between; font-size: 11px; font-weight: 600;">
                    <span style="color: var(--text-dim);">30-Min Throttle Guard (Android Limit)</span>
                    <span style="color: ${throttlePct > 80 ? 'var(--color-rose)' : '#cbd5e1'};">${totalRecent} / ${maxLimit} in 30m</span>
                  </div>
                  <div class="throttle-bar-outer">
                    <div class="throttle-bar-fill ${throttleClass}" style="width: ${throttlePct}%;"></div>
                  </div>
                </div>

                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 10px;">
                  ${slotsHtml}
                </div>

                <div style="display: flex; justify-content: flex-end; gap: 8px; margin-top: auto; padding-top: 8px; border-top: 1px solid rgba(255, 255, 255, 0.05);">
                  <button class="btn-secondary btn-sm" onclick="window.pingDevice('${d.id}')">Ping Radio</button>
                  ${!d.is_revoked ? `<button class="btn-secondary btn-sm btn-danger" onclick="window.revokeDevice('${d.id}', '${escapeHtml(d.name)}')">Revoke</button>` : ''}
                </div>
              </div>
            `;
          })
          .join('');
      }

      if (tbody) {
        tbody.innerHTML = devices
          .map((d) => {
            const isOnline = d.is_online && !d.is_revoked;
            const statusBadge = d.is_revoked
              ? `<span class="badge badge-revoked">Revoked</span>`
              : isOnline
              ? `<span class="badge badge-online"><span class="status-dot"></span> Online</span>`
              : `<span class="badge badge-offline">Offline</span>`;

            const simBadge = d.sim_ready
              ? `<span style="color: var(--color-emerald); font-weight: 600;">Ready (${d.phone_number || 'SIM 1'})</span>`
              : `<span style="color: var(--text-dim);">No SIM / Disabled</span>`;

            const batteryLevel = d.battery_level !== null ? d.battery_level : 100;
            const batteryColor = batteryLevel > 40 ? 'var(--color-emerald)' : batteryLevel > 15 ? 'var(--color-amber)' : 'var(--color-rose)';

            const lastSeen = d.last_seen_at ? formatTimeAgo(new Date(d.last_seen_at)) : 'Never';

            return `
              <tr>
                <td>
                  <div style="font-weight: 600; color: #fff;">${escapeHtml(d.name)}</div>
                  <div style="font-size: 11px; color: var(--text-dim);">${escapeHtml(d.model || 'Android Phone')} · OS ${escapeHtml(d.os_version || '11+')}</div>
                </td>
                <td>${statusBadge}</td>
                <td style="font-size: 12px;">${simBadge}</td>
                <td>
                  <div style="font-weight: 500;">${escapeHtml(d.carrier_name || 'Cellular')}</div>
                  <div style="font-size: 11px; color: var(--text-dim);">${escapeHtml(d.network_type || 'LTE/4G')}</div>
                </td>
                <td>
                  <span class="battery-meter" style="color: ${batteryColor};">
                    ${batteryLevel}%
                  </span>
                </td>
                <td>
                  <div class="signal-meter">
                    <div class="signal-bar active"></div>
                    <div class="signal-bar ${d.signal_level >= 2 ? 'active' : ''}"></div>
                    <div class="signal-bar ${d.signal_level >= 3 ? 'active' : ''}"></div>
                    <div class="signal-bar ${d.signal_level >= 4 ? 'active' : ''}"></div>
                  </div>
                </td>
                <td style="font-size: 12px; color: var(--text-muted);">${escapeHtml(lastSeen)}</td>
                <td>
                  <div style="display: flex; gap: 8px;">
                    <button class="btn-secondary btn-sm" onclick="window.pingDevice('${d.id}')" title="Ping Device">
                      Ping
                    </button>
                    ${
                      !d.is_revoked
                        ? `<button class="btn-secondary btn-sm btn-danger" onclick="window.revokeDevice('${d.id}', '${escapeHtml(d.name)}')" title="Revoke Device">Revoke</button>`
                        : ''
                    }
                  </div>
                </td>
              </tr>
            `;
          })
          .join('');
      }
    } catch (err) {
      console.error('Failed to fetch devices:', err);
    }
  }

  window.pingDevice = async function (deviceId) {
    try {
      const res = await apiFetch(`/admin/devices/${deviceId}/ping`, { method: 'POST' });
      showToast(`Device '${res.name}' is ${res.is_online ? 'ONLINE' : 'OFFLINE'} (Battery: ${res.battery_level || 100}%)`, 'info');
    } catch (err) {
      showToast(err.message, 'error');
    }
  };

  window.revokeDevice = async function (deviceId, name) {
    if (!confirm(`Are you sure you want to revoke '${name}'? It will no longer receive SMS jobs.`)) return;
    try {
      await apiFetch(`/devices/${deviceId}`, { method: 'DELETE' });
      showToast(`Device '${name}' has been revoked.`, 'success');
      fetchDevices();
    } catch (err) {
      showToast(err.message, 'error');
    }
  };

  // Pairing Code Generation Modal
  async function openPairingCodeModal() {
    try {
      const res = await apiFetch('/admin/devices/pairing-code', {
        method: 'POST',
        body: { device_name: 'Android Gateway Phone', expires_in_seconds: 600 },
      });

      document.getElementById('pairing-code-text').textContent = res.code;
      openModal('modal-pairing-code');

      // Start countdown
      let remaining = res.expires_in_seconds;
      if (pairingCountdownInterval) clearInterval(pairingCountdownInterval);

      const timerEl = document.getElementById('pairing-code-timer');
      pairingCountdownInterval = setInterval(() => {
        remaining -= 1;
        if (remaining <= 0) {
          clearInterval(pairingCountdownInterval);
          timerEl.textContent = 'Expired. Generate a new code.';
          return;
        }
        const m = Math.floor(remaining / 60);
        const s = remaining % 60;
        timerEl.textContent = `Expires in ${m}:${s < 10 ? '0' : ''}${s}`;
      }, 1000);
    } catch (err) {
      showToast(err.message, 'error');
    }
  }

  if (overviewPairDeviceBtn) overviewPairDeviceBtn.addEventListener('click', openPairingCodeModal);
  if (devicesGenerateCodeBtn) devicesGenerateCodeBtn.addEventListener('click', openPairingCodeModal);

  const copyPairingCodeBtn = document.getElementById('copy-pairing-code-btn');
  if (copyPairingCodeBtn) {
    copyPairingCodeBtn.addEventListener('click', () => {
      const code = document.getElementById('pairing-code-text').textContent;
      navigator.clipboard.writeText(code).then(() => {
        showToast(`Pairing code '${code}' copied to clipboard!`, 'success');
      });
    });
  }

  // ========================================================================
  // 3. OUTBOUND MESSAGES TAB
  // ========================================================================
  async function fetchMessages() {
    try {
      let url = `/messages?limit=100`;
      if (currentTenantId) url += `&tenant_id=${encodeURIComponent(currentTenantId)}`;
      if (activeStatusFilter) url += `&status_filter=${encodeURIComponent(activeStatusFilter)}`;
      const messages = await apiFetch(url);
      cachedMessages = messages || [];
      renderMessagesTable(cachedMessages);
      updateMessagesBatchBar();
    } catch (err) {
      console.error('Failed to fetch messages:', err);
    }
  }

  function renderMessagesTable(messages) {
    const tbody = document.getElementById('messages-tbody');
    if (!tbody) return;

    if (!messages || messages.length === 0) {
      tbody.innerHTML = `
        <tr>
          <td colspan="9" style="text-align: center; padding: 40px; color: var(--text-dim);">
            No outgoing SMS messages found for the selected filter.
          </td>
        </tr>
      `;
      return;
    }

    tbody.innerHTML = messages
      .map((m) => {
        let badgeClass = 'badge-queued';
        if (m.status === 'delivered') badgeClass = 'badge-delivered';
        else if (m.status === 'sent') badgeClass = 'badge-sent';
        else if (m.status === 'failed' || m.status === 'rejected') badgeClass = 'badge-failed';
        else if (m.status === 'sending') badgeClass = 'badge-sending';
        else if (m.status === 'pending_approval') badgeClass = 'badge-role-super';

        const timeStr = new Date(m.created_at).toLocaleString();
        const hasMod = m.original_body && m.original_body !== m.body;

        return `
          <tr>
            <td width="30"><input type="checkbox" class="msg-select-chk" value="${m.id}"></td>
            <td class="mono-cell" style="font-size: 11px; color: var(--text-dim);">${escapeHtml(m.id.substring(0, 8))}...</td>
            <td class="mono-cell" style="font-weight: 600; color: #fff;">
              ${escapeHtml(m.to)}
              <div style="margin-top: 3px;">${getMnoBadge(m.detected_mno)}</div>
            </td>
            <td style="max-width: 280px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;" title="${escapeHtml(m.body)}">
              ${escapeHtml(m.body)}
              ${hasMod ? '<span style="font-size: 10px; color: #34d399; font-weight: 700; margin-left: 4px;">[MOD]</span>' : ''}
            </td>
            <td><span class="badge ${badgeClass}">${escapeHtml(m.status)}</span></td>
            <td style="font-family: var(--font-mono); font-size: 11px;">${m.priority || 10}</td>
            <td style="font-size: 12px; color: var(--text-muted);">${escapeHtml(m.device_id ? m.device_id.substring(0, 8) : 'Pending')}</td>
            <td style="font-size: 12px; color: var(--text-dim);">${escapeHtml(timeStr)}</td>
            <td>
              <div style="display: flex; gap: 6px;">
                <button class="btn-secondary btn-sm" onclick="window.openPerSmsDrawer('${m.id}')" title="Inspect & Edit SMS">Inspect</button>
                ${
                  m.status === 'failed'
                    ? `<button class="btn-secondary btn-sm" onclick="window.retryMessage('${m.id}')" title="Retry SMS">Retry</button>`
                    : ''
                }
              </div>
            </td>
          </tr>
        `;
      })
      .join('');

    tbody.querySelectorAll('.msg-select-chk').forEach(chk => {
      chk.addEventListener('change', updateMessagesBatchBar);
    });
  }

  function updateMessagesBatchBar() {
    const selected = Array.from(document.querySelectorAll('.msg-select-chk:checked')).map(c => c.value);
    const bar = document.getElementById('messages-batch-bar');
    const countEl = document.getElementById('messages-selected-count');
    if (bar) {
      if (selected.length > 0) {
        bar.style.display = 'flex';
        if (countEl) countEl.textContent = selected.length;
      } else {
        bar.style.display = 'none';
      }
    }
  }

  const msgSelectAll = document.getElementById('messages-select-all');
  if (msgSelectAll) {
    msgSelectAll.addEventListener('change', (e) => {
      document.querySelectorAll('.msg-select-chk').forEach(chk => {
        chk.checked = e.target.checked;
      });
      updateMessagesBatchBar();
    });
  }

  const btnMsgBatchApprove = document.getElementById('btn-msg-batch-approve');
  if (btnMsgBatchApprove) {
    btnMsgBatchApprove.addEventListener('click', async () => {
      const ids = Array.from(document.querySelectorAll('.msg-select-chk:checked')).map(c => c.value);
      if (!ids.length) return;
      try {
        const res = await apiFetch('/admin/messages/batch-action', {
          method: 'POST',
          body: { message_ids: ids, action: 'approve' }
        });
        showToast(`Approved ${res.affected_count} messages for dispatch!`, 'success');
        fetchMessages();
      } catch (err) {
        showToast(err.message, 'error');
      }
    });
  }

  const btnMsgBatchReject = document.getElementById('btn-msg-batch-reject');
  if (btnMsgBatchReject) {
    btnMsgBatchReject.addEventListener('click', async () => {
      const ids = Array.from(document.querySelectorAll('.msg-select-chk:checked')).map(c => c.value);
      if (!ids.length) return;
      try {
        const res = await apiFetch('/admin/messages/batch-action', {
          method: 'POST',
          body: { message_ids: ids, action: 'reject', admin_notes: 'Batch rejected by administrator' }
        });
        showToast(`Rejected ${res.affected_count} messages. ${res.credits_refunded || 0} credits refunded.`, 'info');
        fetchMessages();
      } catch (err) {
        showToast(err.message, 'error');
      }
    });
  }

  const btnMsgBatchCancel = document.getElementById('btn-msg-batch-cancel');
  if (btnMsgBatchCancel) {
    btnMsgBatchCancel.addEventListener('click', () => {
      document.querySelectorAll('.msg-select-chk').forEach(c => c.checked = false);
      if (msgSelectAll) msgSelectAll.checked = false;
      updateMessagesBatchBar();
    });
  }

  // ========================================================================
  // 3.2 QUARANTINE & REVIEW TAB
  // ========================================================================
  async function fetchQuarantineMessages() {
    try {
      let url = `/messages?limit=100&status_filter=${encodeURIComponent(activeQuarantineFilter)}`;
      if (currentTenantId) url += `&tenant_id=${encodeURIComponent(currentTenantId)}`;
      const messages = await apiFetch(url);
      cachedQuarantineMessages = messages || [];
      renderQuarantineTable(cachedQuarantineMessages);
      updateQuarantineBatchBar();

      const badge = document.getElementById('nav-badge-quarantine');
      if (badge) badge.textContent = cachedQuarantineMessages.length;
    } catch (err) {
      console.error('Failed to fetch quarantined messages:', err);
    }
  }

  function renderQuarantineTable(messages) {
    const tbody = document.getElementById('quarantine-tbody');
    if (!tbody) return;

    if (!messages || messages.length === 0) {
      tbody.innerHTML = `
        <tr>
          <td colspan="9" style="text-align: center; padding: 40px; color: var(--text-dim);">
            No messages currently held in quarantine for '${activeQuarantineFilter}'.
          </td>
        </tr>
      `;
      return;
    }

    tbody.innerHTML = messages
      .map((m) => {
        const timeStr = new Date(m.created_at).toLocaleString();
        return `
          <tr>
            <td width="30"><input type="checkbox" class="q-select-chk" value="${m.id}"></td>
            <td class="mono-cell" style="font-size: 11px; color: var(--text-dim);">${escapeHtml(m.id.substring(0, 8))}...</td>
            <td class="mono-cell" style="font-weight: 600; color: #fff;">
              ${escapeHtml(m.to)}
              <div style="margin-top: 3px;">${getMnoBadge(m.detected_mno)}</div>
            </td>
            <td style="max-width: 240px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;" title="${escapeHtml(m.body)}">
              ${escapeHtml(m.body)}
            </td>
            <td><span class="badge ${m.status === 'rejected' ? 'badge-failed' : 'badge-queued'}">${escapeHtml(m.status)}</span></td>
            <td style="font-family: var(--font-mono); font-size: 11px;">${m.priority || 10}</td>
            <td style="font-size: 11px; color: #fda4af;">${escapeHtml(m.admin_notes || 'Content filter hold')}</td>
            <td style="font-size: 12px; color: var(--text-dim);">${escapeHtml(timeStr)}</td>
            <td>
              <div style="display: flex; gap: 6px;">
                <button class="btn-primary btn-sm" onclick="window.approveSingleMessage('${m.id}')" style="background: #10b981;">Approve</button>
                <button class="btn-secondary btn-sm" onclick="window.openPerSmsDrawer('${m.id}')">Inspect</button>
              </div>
            </td>
          </tr>
        `;
      })
      .join('');

    tbody.querySelectorAll('.q-select-chk').forEach(chk => {
      chk.addEventListener('change', updateQuarantineBatchBar);
    });
  }

  function updateQuarantineBatchBar() {
    const selected = Array.from(document.querySelectorAll('.q-select-chk:checked')).map(c => c.value);
    const bar = document.getElementById('quarantine-batch-bar');
    const countEl = document.getElementById('quarantine-selected-count');
    if (bar) {
      if (selected.length > 0) {
        bar.style.display = 'flex';
        if (countEl) countEl.textContent = selected.length;
      } else {
        bar.style.display = 'none';
      }
    }
  }

  const qSelectAll = document.getElementById('quarantine-select-all');
  if (qSelectAll) {
    qSelectAll.addEventListener('change', (e) => {
      document.querySelectorAll('.q-select-chk').forEach(chk => {
        chk.checked = e.target.checked;
      });
      updateQuarantineBatchBar();
    });
  }

  const btnBatchApprove = document.getElementById('btn-batch-approve');
  if (btnBatchApprove) {
    btnBatchApprove.addEventListener('click', async () => {
      const ids = Array.from(document.querySelectorAll('.q-select-chk:checked')).map(c => c.value);
      if (!ids.length) return;
      try {
        const res = await apiFetch('/admin/messages/batch-action', {
          method: 'POST',
          body: { message_ids: ids, action: 'approve' }
        });
        showToast(`Approved ${res.affected_count} messages for dispatch!`, 'success');
        fetchQuarantineMessages();
      } catch (err) {
        showToast(err.message, 'error');
      }
    });
  }

  const btnBatchReject = document.getElementById('btn-batch-reject');
  if (btnBatchReject) {
    btnBatchReject.addEventListener('click', async () => {
      const ids = Array.from(document.querySelectorAll('.q-select-chk:checked')).map(c => c.value);
      if (!ids.length) return;
      try {
        const res = await apiFetch('/admin/messages/batch-action', {
          method: 'POST',
          body: { message_ids: ids, action: 'reject', admin_notes: 'Quarantine rejected by admin' }
        });
        showToast(`Rejected ${res.affected_count} messages. ${res.credits_refunded || 0} credits refunded.`, 'info');
        fetchQuarantineMessages();
      } catch (err) {
        showToast(err.message, 'error');
      }
    });
  }

  const btnBatchCancel = document.getElementById('btn-batch-cancel');
  if (btnBatchCancel) {
    btnBatchCancel.addEventListener('click', () => {
      document.querySelectorAll('.q-select-chk').forEach(c => c.checked = false);
      if (qSelectAll) qSelectAll.checked = false;
      updateQuarantineBatchBar();
    });
  }

  window.approveSingleMessage = async function(id) {
    try {
      await apiFetch('/admin/messages/batch-action', {
        method: 'POST',
        body: { message_ids: [id], action: 'approve' }
      });
      showToast('Message approved for dispatch!', 'success');
      fetchQuarantineMessages();
    } catch (err) {
      showToast(err.message, 'error');
    }
  };

  document.querySelectorAll('#quarantine-filter-pills .filter-pill').forEach(pill => {
    pill.addEventListener('click', () => {
      document.querySelectorAll('#quarantine-filter-pills .filter-pill').forEach(p => p.classList.remove('active'));
      pill.classList.add('active');
      activeQuarantineFilter = pill.getAttribute('data-qstatus') || 'pending_approval';
      fetchQuarantineMessages();
    });
  });

  window.retryMessage = async function (msgId) {
    try {
      await apiFetch(`/messages/${msgId}/retry`, { method: 'POST' });
      showToast(`Message queued for retry!`, 'success');
      fetchMessages();
    } catch (err) {
      showToast(err.message, 'error');
    }
  };

  // Search & Filter Listeners
  const messagesSearchInput = document.getElementById('messages-search-input');
  if (messagesSearchInput) {
    messagesSearchInput.addEventListener('input', (e) => {
      const q = e.target.value.toLowerCase().trim();
      const filtered = cachedMessages.filter(
        (m) => m.to.toLowerCase().includes(q) || m.id.toLowerCase().includes(q) || m.body.toLowerCase().includes(q)
      );
      renderMessagesTable(filtered);
    });
  }

  document.querySelectorAll('#messages-filter-pills .filter-pill').forEach((pill) => {
    pill.addEventListener('click', () => {
      document.querySelectorAll('#messages-filter-pills .filter-pill').forEach((p) => p.classList.remove('active'));
      pill.classList.add('active');
      activeStatusFilter = pill.getAttribute('data-status') || '';
      fetchMessages();
    });
  });

  // Compose SMS Modal
  function openComposeModal(prefillTo = '') {
    const recipientInput = document.getElementById('compose-recipient');
    if (recipientInput) recipientInput.value = prefillTo;
    openModal('modal-compose-sms');
  }

  if (quickComposeBtn) quickComposeBtn.addEventListener('click', () => openComposeModal());
  if (messagesComposeBtn) messagesComposeBtn.addEventListener('click', () => openComposeModal());

  const composeBody = document.getElementById('compose-body');
  if (composeBody) {
    composeBody.addEventListener('input', () => {
      const len = composeBody.value.length;
      document.getElementById('char-counter').textContent = `${len} / 160 characters`;
      const segments = Math.max(1, Math.ceil(len / 160));
      document.getElementById('segment-counter').textContent = `${segments} SMS segment${segments > 1 ? 's' : ''} (GSM-7)`;
    });
  }

  const composeForm = document.getElementById('compose-sms-form');
  if (composeForm) {
    composeForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const to = document.getElementById('compose-recipient').value.trim();
      const body = document.getElementById('compose-body').value.trim();

      if (!to || !body) {
        showToast('Recipient and message text are required.', 'error');
        return;
      }

      try {
        const res = await apiFetch('/messages', {
          method: 'POST',
          body: { to, body },
        });

        closeModal('modal-compose-sms');
        composeForm.reset();
        document.getElementById('char-counter').textContent = `0 / 160 characters`;
        showToast(`SMS queued successfully! ID: ${res.id.substring(0, 8)}`, 'success');

        if (currentTab === 'messages') fetchMessages();
        else fetchOverviewStats();
      } catch (err) {
        showToast(err.message, 'error');
      }
    });
  }

  // ========================================================================
  // 4. INBOX / RECEIVED SMS TAB
  // ========================================================================
  async function fetchInbox() {
    try {
      const messages = await apiFetch('/incoming?limit=100');
      const tbody = document.getElementById('inbox-tbody');
      if (!tbody) return;

      if (!messages || messages.length === 0) {
        tbody.innerHTML = `
          <tr>
            <td colspan="6" style="text-align: center; padding: 40px; color: var(--text-dim);">
              No incoming SMS messages received yet. Inbound messages received by your Android phone will automatically appear here.
            </td>
          </tr>
        `;
        return;
      }

      tbody.innerHTML = messages
        .map((m) => {
          const deviceTime = new Date(m.received_at_device).toLocaleString();
          const syncedTime = formatTimeAgo(new Date(m.created_at || m.synced_at));

          return `
            <tr>
              <td class="mono-cell" style="font-weight: 600; color: #fff;">${escapeHtml(m.from_number)}</td>
              <td style="max-width: 360px;">${escapeHtml(m.body)}</td>
              <td style="font-size: 12px; color: var(--text-muted);">${escapeHtml(deviceTime)}</td>
              <td style="font-size: 12px; color: var(--text-dim);">${escapeHtml(m.device_id ? m.device_id.substring(0, 8) : 'Phone')}</td>
              <td style="font-size: 12px; color: var(--text-dim);">${escapeHtml(syncedTime)}</td>
              <td>
                <button class="btn-primary btn-sm" onclick="window.replyToMessage('${escapeHtml(m.from_number)}')">
                  Reply
                </button>
              </td>
            </tr>
          `;
        })
        .join('');
    } catch (err) {
      console.error('Failed to fetch inbox:', err);
    }
  }

  window.replyToMessage = function (phoneNumber) {
    openComposeModal(phoneNumber);
  };

  // ========================================================================
  // 5. WEBHOOKS TAB
  // ========================================================================
  async function fetchWebhooks() {
    try {
      const webhooks = await apiFetch('/webhooks');
      const tbody = document.getElementById('webhooks-tbody');
      if (!tbody) return;

      if (!webhooks || webhooks.length === 0) {
        tbody.innerHTML = `
          <tr>
            <td colspan="5" style="text-align: center; padding: 40px; color: var(--text-dim);">
              No webhooks configured. Click <strong>Add Webhook Subscription</strong> to receive instant delivery event callbacks.
            </td>
          </tr>
        `;
        return;
      }

      tbody.innerHTML = webhooks
        .map((w) => {
          const timeStr = new Date(w.created_at).toLocaleDateString();
          const eventsList = (w.events || []).map((e) => `<code style="font-size: 11px;">${escapeHtml(e)}</code>`).join(' ');

          return `
            <tr>
              <td class="mono-cell" style="font-size: 13px; color: var(--color-cyan);">${escapeHtml(w.url)}</td>
              <td>${eventsList}</td>
              <td>
                ${
                  w.is_active
                    ? `<span class="badge badge-online">Active</span>`
                    : `<span class="badge badge-offline">Inactive</span>`
                }
              </td>
              <td style="font-size: 12px; color: var(--text-dim);">${escapeHtml(timeStr)}</td>
              <td>
                <div style="display: flex; gap: 8px;">
                  <button class="btn-secondary btn-sm" onclick="window.testWebhook('${w.id}')" title="Test Webhook Ping">
                    Test Ping
                  </button>
                  <button class="btn-secondary btn-sm btn-danger" onclick="window.deleteWebhook('${w.id}')" title="Delete Webhook">
                    Delete
                  </button>
                </div>
              </td>
            </tr>
          `;
        })
        .join('');
    } catch (err) {
      console.error('Failed to fetch webhooks:', err);
    }
  }

  window.testWebhook = async function (whId) {
    try {
      showToast('Sending test ping to webhook endpoint...', 'info');
      const res = await apiFetch(`/admin/webhooks/${whId}/test`, { method: 'POST' });
      if (res.status === 'delivered') {
        showToast(`Webhook delivered successfully! HTTP ${res.http_status}`, 'success');
      } else {
        showToast(`Webhook delivery failed: ${res.error || 'HTTP ' + res.http_status}`, 'error');
      }
    } catch (err) {
      showToast(err.message, 'error');
    }
  };

  window.deleteWebhook = async function (whId) {
    if (!confirm('Are you sure you want to delete this webhook subscription?')) return;
    try {
      await apiFetch(`/webhooks/${whId}`, { method: 'DELETE' });
      showToast('Webhook deleted.', 'success');
      fetchWebhooks();
    } catch (err) {
      showToast(err.message, 'error');
    }
  };

  if (webhooksAddBtn) {
    webhooksAddBtn.addEventListener('click', () => {
      openModal('modal-create-webhook');
    });
  }

  const createWebhookForm = document.getElementById('create-webhook-form');
  if (createWebhookForm) {
    createWebhookForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const url = document.getElementById('webhook-url').value.trim();
      const events = Array.from(document.querySelectorAll('.wh-event-chk:checked')).map((c) => c.value);

      if (!url || events.length === 0) {
        showToast('Please provide a URL and select at least one event.', 'error');
        return;
      }

      try {
        await apiFetch('/webhooks', {
          method: 'POST',
          body: { url, events },
        });

        closeModal('modal-create-webhook');
        createWebhookForm.reset();
        showToast('Webhook subscription created successfully!', 'success');
        fetchWebhooks();
      } catch (err) {
        showToast(err.message, 'error');
      }
    });
  }

  // ========================================================================
  // 6. API KEYS TAB
  // ========================================================================
  async function fetchApiKeys() {
    try {
      const keys = await apiFetch('/admin/api-keys');
      const tbody = document.getElementById('apikeys-tbody');
      if (!tbody) return;

      if (!keys || keys.length === 0) {
        tbody.innerHTML = `
          <tr>
            <td colspan="7" style="text-align: center; padding: 40px; color: var(--text-dim);">
              No API keys created yet. Click <strong>Generate New API Key</strong> to connect your external apps.
            </td>
          </tr>
        `;
        return;
      }

      tbody.innerHTML = keys
        .map((k) => {
          const lastUsed = k.last_used_at ? formatTimeAgo(new Date(k.last_used_at)) : 'Never';
          const scopesStr = (k.scopes || []).map((s) => `<code style="font-size: 11px;">${escapeHtml(s)}</code>`).join(' ');

          return `
            <tr>
              <td style="font-weight: 600; color: #fff;">${escapeHtml(k.name)}</td>
              <td class="mono-cell" style="color: var(--color-primary-light);">${escapeHtml(k.key_prefix)}••••••••</td>
              <td>${scopesStr}</td>
              <td class="mono-cell">${escapeHtml(k.rate_limit)} req/min</td>
              <td>
                ${
                  k.is_active
                    ? `<span class="badge badge-online">Active</span>`
                    : `<span class="badge badge-offline">Revoked</span>`
                }
              </td>
              <td style="font-size: 12px; color: var(--text-dim);">${escapeHtml(lastUsed)}</td>
              <td>
                ${
                  k.is_active
                    ? `<button class="btn-secondary btn-sm btn-danger" onclick="window.revokeApiKey('${k.id}', '${escapeHtml(k.name)}')">Revoke</button>`
                    : '<span style="color: var(--text-dim); font-size: 11px;">Revoked</span>'
                }
              </td>
            </tr>
          `;
        })
        .join('');
    } catch (err) {
      console.error('Failed to fetch API keys:', err);
    }
  }

  window.revokeApiKey = async function (keyId, name) {
    if (!confirm(`Are you sure you want to revoke API key '${name}'? External apps using this key will immediately stop working.`)) return;
    try {
      await apiFetch(`/admin/api-keys/${keyId}`, { method: 'DELETE' });
      showToast(`API key '${name}' has been deactivated.`, 'success');
      fetchApiKeys();
    } catch (err) {
      showToast(err.message, 'error');
    }
  };

  if (apikeysCreateBtn) {
    apikeysCreateBtn.addEventListener('click', () => {
      openModal('modal-create-apikey');
    });
  }

  const createApiKeyForm = document.getElementById('create-apikey-form');
  if (createApiKeyForm) {
    createApiKeyForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const name = document.getElementById('apikey-name').value.trim();
      const scopes = [];
      if (document.getElementById('scope-sms-send').checked) scopes.push('sms:send');
      if (document.getElementById('scope-sms-read').checked) scopes.push('sms:read');
      if (document.getElementById('scope-device-manage').checked) scopes.push('device:manage');
      if (document.getElementById('scope-webhook-manage').checked) scopes.push('webhooks:manage');

      if (!name) {
        showToast('Please enter an application name.', 'error');
        return;
      }

      try {
        const res = await apiFetch('/admin/api-keys', {
          method: 'POST',
          body: { name, scopes, rate_limit: 60 },
        });

        closeModal('modal-create-apikey');
        createApiKeyForm.reset();

        // Prompt to copy raw key
        prompt('Save this API key now! It will NOT be shown again:', res.raw_key);
        showToast('API key generated successfully!', 'success');
        fetchApiKeys();
      } catch (err) {
        showToast(err.message, 'error');
      }
    });
  }

  // ========================================================================
  // 7. SYSTEM SETTINGS TAB
  // ========================================================================
  async function fetchSystemSettings() {
    try {
      const data = await apiFetch('/admin/system');
      document.getElementById('sys-python-ver').textContent = data.python_version || 'Python 3.11';
      document.getElementById('sys-db-status').textContent = data.database_status.toUpperCase();
    } catch (err) {
      console.error('Failed to fetch system settings:', err);
    }
  }

  // ========================================================================
  // 8. SLIDEOVER DRAWER: PER-SMS INSPECTOR & MODIFIER
  // ========================================================================
  window.openPerSmsDrawer = async function (msgId) {
    try {
      const msg = await apiFetch(`/messages/${msgId}`);
      currentDrawerMsgId = msg.id;
      document.getElementById('drawer-msg-id').textContent = `ID: ${msg.id}`;
      document.getElementById('drawer-recipient').textContent = msg.to;
      document.getElementById('drawer-mno-badge-wrap').innerHTML = getMnoBadge(msg.detected_mno);

      const bodyInput = document.getElementById('drawer-body-input');
      bodyInput.value = msg.body;
      updateDrawerEncodingCalculator(msg.body);

      const origContainer = document.getElementById('drawer-original-box-container');
      const origBodyEl = document.getElementById('drawer-original-body');
      if (msg.original_body && msg.original_body !== msg.body) {
        origContainer.style.display = 'block';
        origBodyEl.textContent = msg.original_body;
      } else {
        origContainer.style.display = 'none';
      }

      document.getElementById('drawer-sender-name').value = msg.sender_name || '';
      document.getElementById('drawer-sim-slot').value = msg.sim_slot !== null && msg.sim_slot !== undefined ? msg.sim_slot : '';
      document.getElementById('drawer-priority').value = msg.priority || 10;
      document.getElementById('drawer-status-pill').textContent = msg.status;
      document.getElementById('drawer-admin-notes').value = msg.admin_notes || '';

      const approveBtn = document.getElementById('drawer-approve-btn');
      const rejectBtn = document.getElementById('drawer-reject-btn');
      if (msg.status === 'pending_approval' || msg.status === 'scheduled') {
        approveBtn.style.display = 'inline-flex';
        rejectBtn.style.display = 'inline-flex';
      } else {
        approveBtn.style.display = 'none';
        rejectBtn.style.display = 'none';
      }

      document.getElementById('per-sms-drawer').classList.add('open');
      document.getElementById('drawer-backdrop').classList.add('open');
    } catch (err) {
      showToast(err.message || 'Failed to load message details', 'error');
    }
  };

  function closePerSmsDrawer() {
    const drawer = document.getElementById('per-sms-drawer');
    const backdrop = document.getElementById('drawer-backdrop');
    if (drawer) drawer.classList.remove('open');
    if (backdrop) backdrop.classList.remove('open');
    currentDrawerMsgId = null;
  }

  const drawerCloseBtn = document.getElementById('drawer-close-btn');
  const drawerCancelBtn = document.getElementById('drawer-cancel-btn');
  const drawerBackdrop = document.getElementById('drawer-backdrop');
  if (drawerCloseBtn) drawerCloseBtn.addEventListener('click', closePerSmsDrawer);
  if (drawerCancelBtn) drawerCancelBtn.addEventListener('click', closePerSmsDrawer);
  if (drawerBackdrop) drawerBackdrop.addEventListener('click', closePerSmsDrawer);

  const drawerBodyInput = document.getElementById('drawer-body-input');
  if (drawerBodyInput) {
    drawerBodyInput.addEventListener('input', (e) => {
      updateDrawerEncodingCalculator(e.target.value);
    });
  }

  function updateDrawerEncodingCalculator(text) {
    const gsm7Basic = "@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞ\x1bÆæßÉ !\"#¤%&'()*+,-./0123456789:;<=>?¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ`abcdefghijklmnopqrstuvwxyzäöñüà";
    const gsm7Ext = "|^{}\\[~]€";
    let isGsm = true;
    let septets = 0;
    for (const ch of text) {
      if (gsm7Ext.includes(ch)) {
        septets += 2;
      } else if (gsm7Basic.includes(ch)) {
        septets += 1;
      } else {
        isGsm = false;
        break;
      }
    }

    const encodingLabel = document.getElementById('drawer-encoding-label');
    const partsLabel = document.getElementById('drawer-parts-count');
    const charsLabel = document.getElementById('drawer-chars-count');

    if (isGsm) {
      encodingLabel.textContent = 'GSM_7BIT';
      encodingLabel.style.color = 'var(--color-emerald)';
      const parts = septets <= 160 ? 1 : Math.ceil(septets / 153);
      partsLabel.textContent = `${parts} part${parts > 1 ? 's' : ''}`;
      charsLabel.textContent = `${septets} septets (${text.length} chars)`;
    } else {
      encodingLabel.textContent = 'UCS_2';
      encodingLabel.style.color = 'var(--color-amber)';
      const parts = text.length <= 70 ? 1 : Math.ceil(text.length / 67);
      partsLabel.textContent = `${parts} part${parts > 1 ? 's' : ''}`;
      charsLabel.textContent = `${text.length} chars (UCS-2 Unicode)`;
    }
  }

  const drawerSaveBtn = document.getElementById('drawer-save-btn');
  if (drawerSaveBtn) {
    drawerSaveBtn.addEventListener('click', async () => {
      if (!currentDrawerMsgId) return;
      const body = document.getElementById('drawer-body-input').value.trim();
      const sender_name = document.getElementById('drawer-sender-name').value.trim() || null;
      const sim_slot_val = document.getElementById('drawer-sim-slot').value;
      const sim_slot = sim_slot_val !== '' ? parseInt(sim_slot_val, 10) : null;
      const priority = parseInt(document.getElementById('drawer-priority').value, 10) || 10;
      const admin_notes = document.getElementById('drawer-admin-notes').value.trim() || null;

      try {
        await apiFetch(`/admin/messages/${currentDrawerMsgId}/modify`, {
          method: 'PATCH',
          body: { body, sender_name, sim_slot, priority, admin_notes }
        });
        showToast('Message payload modified successfully!', 'success');
        closePerSmsDrawer();
        fetchMessages();
        if (currentTab === 'quarantine') fetchQuarantineMessages();
        fetchOverviewStats();
      } catch (err) {
        showToast(err.message, 'error');
      }
    });
  }

  const drawerApproveBtn = document.getElementById('drawer-approve-btn');
  if (drawerApproveBtn) {
    drawerApproveBtn.addEventListener('click', async () => {
      if (!currentDrawerMsgId) return;
      try {
        await apiFetch('/admin/messages/batch-action', {
          method: 'POST',
          body: { message_ids: [currentDrawerMsgId], action: 'approve' }
        });
        showToast('Message approved for immediate dispatch!', 'success');
        closePerSmsDrawer();
        fetchMessages();
        if (currentTab === 'quarantine') fetchQuarantineMessages();
      } catch (err) {
        showToast(err.message, 'error');
      }
    });
  }

  const drawerRejectBtn = document.getElementById('drawer-reject-btn');
  if (drawerRejectBtn) {
    drawerRejectBtn.addEventListener('click', async () => {
      if (!currentDrawerMsgId) return;
      const notes = document.getElementById('drawer-admin-notes').value.trim() || 'Rejected by administrator';
      try {
        const res = await apiFetch('/admin/messages/batch-action', {
          method: 'POST',
          body: { message_ids: [currentDrawerMsgId], action: 'reject', admin_notes: notes }
        });
        showToast(`Message rejected. ${res.credits_refunded || 0} credits refunded to bundle.`, 'info');
        closePerSmsDrawer();
        fetchMessages();
        if (currentTab === 'quarantine') fetchQuarantineMessages();
        fetchOverviewStats();
      } catch (err) {
        showToast(err.message, 'error');
      }
    });
  }

  // ========================================================================
  // 9. EMERGENCY KILL-SWITCH & WORKSPACE SWITCHER
  // ========================================================================
  const killSwitchBtn = document.getElementById('btn-kill-switch');
  if (killSwitchBtn) {
    killSwitchBtn.addEventListener('click', async () => {
      const targetState = !isKillSwitchActive;
      try {
        const res = await apiFetch('/admin/system/kill-switch', {
          method: 'POST',
          body: { pause: targetState }
        });
        isKillSwitchActive = res.paused;
        updateKillSwitchUI(isKillSwitchActive);
        showToast(
          isKillSwitchActive
            ? 'EMERGENCY PAUSE ENGAGED: Outbound jobs halted.'
            : 'DISPATCH RESUMED: Outbound jobs active.',
          isKillSwitchActive ? 'error' : 'success'
        );
      } catch (err) {
        showToast(err.message, 'error');
      }
    });
  }

  function updateKillSwitchUI(paused) {
    if (!killSwitchBtn) return;
    const label = document.getElementById('killswitch-text');
    if (paused) {
      killSwitchBtn.classList.add('paused');
      if (label) label.textContent = 'PAUSED (HALTED)';
    } else {
      killSwitchBtn.classList.remove('paused');
      if (label) label.textContent = 'DISPATCH ACTIVE';
    }
  }

  const workspaceSelect = document.getElementById('workspace-select');
  if (workspaceSelect) {
    workspaceSelect.addEventListener('change', (e) => {
      currentTenantId = e.target.value || null;
      showToast(`Switched workspace to ${currentTenantId ? e.target.options[e.target.selectedIndex].text : 'Global (Super Admin)'}`, 'info', 2000);
      loadActiveTab();
      fetchOverviewStats();
    });
  }

  // ========================================================================
  // 10. SMART BULK CAMPAIGN: MNO BREAKDOWN & SPINTAX
  // ========================================================================
  const bulkRecipients = document.getElementById('bulk-recipients');
  if (bulkRecipients) {
    bulkRecipients.addEventListener('input', () => {
      updateBulkCarrierBreakdown();
    });
  }

  function updateBulkCarrierBreakdown() {
    if (!bulkRecipients) return;
    const raw = bulkRecipients.value;
    const lines = raw.split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
    let vCount = 0, aCount = 0, tCount = 0, hCount = 0, ttclCount = 0;

    for (const line of lines) {
      let p = line.replace(/[\s\-\(\)]/g, '');
      if (p.startsWith('0')) p = '+255' + p.substring(1);
      else if (p.startsWith('255')) p = '+' + p;

      if (p.startsWith('+25574') || p.startsWith('+25575') || p.startsWith('+25576')) vCount++;
      else if (p.startsWith('+25568') || p.startsWith('+25569') || p.startsWith('+25578')) aCount++;
      else if (p.startsWith('+25565') || p.startsWith('+25567') || p.startsWith('+25571') || p.startsWith('+25577')) tCount++;
      else if (p.startsWith('+25561') || p.startsWith('+25562')) hCount++;
      else if (p.startsWith('+25573')) ttclCount++;
    }

    const total = vCount + aCount + tCount + hCount + ttclCount || 1;
    const cntV = document.getElementById('cnt-voda');
    const cntA = document.getElementById('cnt-airtel');
    const cntT = document.getElementById('cnt-tigo');
    const cntH = document.getElementById('cnt-halo');
    const cntTt = document.getElementById('cnt-ttcl');

    if (cntV) cntV.textContent = vCount;
    if (cntA) cntA.textContent = aCount;
    if (cntT) cntT.textContent = tCount;
    if (cntH) cntH.textContent = hCount;
    if (cntTt) cntTt.textContent = ttclCount;

    const segV = document.getElementById('mno-seg-voda');
    const segA = document.getElementById('mno-seg-airtel');
    const segT = document.getElementById('mno-seg-tigo');
    const segH = document.getElementById('mno-seg-halo');
    const segTt = document.getElementById('mno-seg-ttcl');

    if (segV) segV.style.width = `${(vCount / total) * 100}%`;
    if (segA) segA.style.width = `${(aCount / total) * 100}%`;
    if (segT) segT.style.width = `${(tCount / total) * 100}%`;
    if (segH) segH.style.width = `${(hCount / total) * 100}%`;
    if (segTt) segTt.style.width = `${(ttclCount / total) * 100}%`;
  }

  const btnPreviewSpintax = document.getElementById('btn-preview-spintax');
  if (btnPreviewSpintax) {
    btnPreviewSpintax.addEventListener('click', () => {
      const template = document.getElementById('bulk-body').value || '{Habari|Mambo|Salamu} {{name}}, uthibitisho wako ni {{amount}}';
      let text = template.replace(/\{([^{}]+)\}/g, (match, choices) => {
        const parts = choices.split('|');
        return parts[Math.floor(Math.random() * parts.length)];
      });
      text = text.replace(/\{\{\s*name\s*\}\}/gi, 'Juma')
                 .replace(/\{\{\s*amount\s*\}\}/gi, 'TZS 45,000')
                 .replace(/\{\{\s*code\s*\}\}/gi, '8821');

      const container = document.getElementById('spintax-preview-container');
      if (container) container.style.display = 'block';
      const output = document.getElementById('spintax-sample-output');
      if (output) output.textContent = text;
    });
  }

  // ========================================================================
  // 11. MULTI-TENANT & USER MANAGEMENT
  // ========================================================================
  async function fetchTenants() {
    try {
      const tenants = await apiFetch('/admin/tenants');
      const tbody = document.getElementById('tenants-tbody');
      if (tbody) {
        if (!tenants || tenants.length === 0) {
          tbody.innerHTML = '<tr><td colspan="8" style="text-align: center; padding: 24px;">No tenants registered.</td></tr>';
        } else {
          tbody.innerHTML = tenants.map(t => `
            <tr>
              <td style="font-weight: 600; color: #fff;">${escapeHtml(t.name)}</td>
              <td class="mono-cell" style="font-size: 11px;">${escapeHtml(t.slug)}</td>
              <td><span class="badge ${t.status === 'active' ? 'badge-delivered' : 'badge-failed'}">${escapeHtml(t.status)}</span></td>
              <td>${t.can_use_shared_devices ? '<span style="color:#34d399;">Yes (Shared)</span>' : '<span style="color:#fda4af;">Dedicated</span>'}</td>
              <td style="font-family: var(--font-mono);">${(t.daily_sms_limit || 0).toLocaleString()}</td>
              <td style="font-family: var(--font-mono);">${t.require_bulk_approval_threshold}</td>
              <td style="font-size: 11px; color: var(--text-muted);">${escapeHtml((t.allowed_sender_names || []).join(', ') || 'Any')}</td>
              <td style="font-size: 12px; color: var(--text-dim);">${new Date(t.created_at).toLocaleDateString()}</td>
            </tr>
          `).join('');
        }
      }

      // Populate workspace select & user tenant select
      const wsSelect = document.getElementById('workspace-select');
      const uTenantSelect = document.getElementById('user-tenant-select');
      if (wsSelect) {
        const curVal = wsSelect.value;
        let html = '<option value="">Global Workspace (Super Admin)</option>';
        tenants.forEach(t => {
          html += `<option value="${t.id}">${escapeHtml(t.name)}</option>`;
        });
        wsSelect.innerHTML = html;
        wsSelect.value = curVal;
      }
      if (uTenantSelect) {
        let html = '<option value="">Global / Super Admin</option>';
        tenants.forEach(t => {
          html += `<option value="${t.id}">${escapeHtml(t.name)}</option>`;
        });
        uTenantSelect.innerHTML = html;
      }
    } catch (err) {
      console.error('Failed to fetch tenants:', err);
    }
  }

  async function fetchUsers() {
    try {
      const users = await apiFetch('/admin/users');
      const tbody = document.getElementById('users-tbody');
      if (tbody) {
        if (!users || users.length === 0) {
          tbody.innerHTML = '<tr><td colspan="7" style="text-align: center; padding: 24px;">No users found.</td></tr>';
        } else {
          tbody.innerHTML = users.map(u => `
            <tr>
              <td style="font-weight: 600; color: #fff;">${escapeHtml(u.full_name)}</td>
              <td class="mono-cell" style="font-size: 12px;">${escapeHtml(u.email)}</td>
              <td><span class="badge ${u.role === 'super_admin' ? 'badge-role-super' : 'badge-role-tenant'}">${escapeHtml(u.role)}</span></td>
              <td style="font-size: 12px; color: var(--text-muted);">${escapeHtml(u.tenant_name || 'Global Platform')}</td>
              <td><span class="badge ${u.is_active ? 'badge-delivered' : 'badge-failed'}">${u.is_active ? 'Active' : 'Suspended'}</span></td>
              <td style="font-size: 11px; color: var(--text-dim);">${u.last_login_at ? new Date(u.last_login_at).toLocaleString() : 'Never'}</td>
              <td style="font-size: 12px; color: var(--text-dim);">${new Date(u.created_at).toLocaleDateString()}</td>
            </tr>
          `).join('');
        }
      }
    } catch (err) {
      console.error('Failed to fetch users:', err);
    }
  }

  // Modals for Tenant and User Creation
  const btnOpenCreateTenant = document.getElementById('btn-open-create-tenant');
  if (btnOpenCreateTenant) {
    btnOpenCreateTenant.addEventListener('click', () => openModal('modal-create-tenant'));
  }

  const createTenantForm = document.getElementById('create-tenant-form');
  if (createTenantForm) {
    createTenantForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const name = document.getElementById('tenant-name').value.trim();
      const slug = document.getElementById('tenant-slug').value.trim();
      const daily_sms_limit = parseInt(document.getElementById('tenant-daily-limit').value, 10) || 10000;
      const require_bulk_approval_threshold = parseInt(document.getElementById('tenant-bulk-threshold').value, 10) || 200;
      const can_use_shared_devices = document.getElementById('tenant-shared-devices').checked;
      const sendersRaw = document.getElementById('tenant-allowed-senders').value.trim();
      const allowed_sender_names = sendersRaw ? sendersRaw.split(',').map(s => s.trim()).filter(Boolean) : [];

      try {
        await apiFetch('/admin/tenants', {
          method: 'POST',
          body: { name, slug, daily_sms_limit, require_bulk_approval_threshold, can_use_shared_devices, allowed_sender_names }
        });
        showToast(`Tenant '${name}' created successfully!`, 'success');
        closeModal('modal-create-tenant');
        createTenantForm.reset();
        fetchTenants();
      } catch (err) {
        showToast(err.message, 'error');
      }
    });
  }

  const btnOpenCreateUser = document.getElementById('btn-open-create-user');
  if (btnOpenCreateUser) {
    btnOpenCreateUser.addEventListener('click', () => openModal('modal-create-user'));
  }

  const createUserForm = document.getElementById('create-user-form');
  if (createUserForm) {
    createUserForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const full_name = document.getElementById('user-full-name').value.trim();
      const email = document.getElementById('user-email').value.trim();
      const password = document.getElementById('user-password').value.trim();
      const tenant_id = document.getElementById('user-tenant-select').value || null;
      const role = document.getElementById('user-role-select').value;

      try {
        await apiFetch('/admin/users', {
          method: 'POST',
          body: { full_name, email, password, tenant_id, role }
        });
        showToast(`User '${full_name}' created successfully!`, 'success');
        closeModal('modal-create-user');
        createUserForm.reset();
        fetchUsers();
      } catch (err) {
        showToast(err.message, 'error');
      }
    });
  }

  // ========================================================================
  // 12. DND BLACKLIST & CONTENT MODERATION FIREWALL
  // ========================================================================
  async function fetchDndList() {
    try {
      const dnd = await apiFetch('/admin/dnd');
      const tbody = document.getElementById('dnd-tbody');
      if (tbody) {
        if (!dnd || dnd.length === 0) {
          tbody.innerHTML = '<tr><td colspan="4" style="text-align: center; padding: 24px;">DND Blacklist is empty.</td></tr>';
        } else {
          tbody.innerHTML = dnd.map(d => `
            <tr>
              <td class="mono-cell" style="font-weight: 700; color: #fda4af;">${escapeHtml(d.phone_number)}</td>
              <td style="font-size: 12px; color: var(--text-muted);">${d.tenant_id ? 'Tenant Scoped' : 'Global Network'}</td>
              <td><span class="badge ${d.reason === 'user_opt_out' ? 'badge-failed' : 'badge-queued'}">${escapeHtml(d.reason)}</span></td>
              <td style="font-size: 12px; color: var(--text-dim);">${new Date(d.created_at).toLocaleString()}</td>
            </tr>
          `).join('');
        }
      }
    } catch (err) {
      console.error('Failed to fetch DND list:', err);
    }
  }

  async function fetchModerationRules() {
    try {
      const rules = await apiFetch('/admin/moderation-rules');
      cachedModerationRules = rules || [];
      const tbody = document.getElementById('rules-tbody');
      if (tbody) {
        if (!rules || rules.length === 0) {
          tbody.innerHTML = '<tr><td colspan="6" style="text-align: center; padding: 24px;">No moderation rules active.</td></tr>';
        } else {
          tbody.innerHTML = rules.map(r => `
            <tr>
              <td style="font-weight: 600; color: #fff;">${escapeHtml(r.name)}</td>
              <td class="mono-cell" style="color: var(--color-cyan); font-size: 12px;">${escapeHtml(r.pattern)}</td>
              <td><span class="badge ${r.action === 'reject' ? 'badge-failed' : r.action === 'hold_for_approval' ? 'badge-queued' : 'badge-delivered'}">${escapeHtml(r.action)}</span></td>
              <td style="font-size: 12px; color: var(--text-muted);">${escapeHtml(r.replacement_text || '—')}</td>
              <td><span class="badge ${r.is_active ? 'badge-delivered' : 'badge-failed'}">${r.is_active ? 'Active' : 'Disabled'}</span></td>
              <td style="font-size: 12px; color: var(--text-dim);">${new Date(r.created_at).toLocaleDateString()}</td>
            </tr>
          `).join('');
        }
      }
    } catch (err) {
      console.error('Failed to fetch moderation rules:', err);
    }
  }

  const firewallTestBtn = document.getElementById('firewall-test-btn');
  if (firewallTestBtn) {
    firewallTestBtn.addEventListener('click', () => {
      const input = document.getElementById('firewall-test-input').value.trim();
      const resultEl = document.getElementById('firewall-test-result');
      if (!input || !resultEl) return;
      resultEl.style.display = 'block';

      let matchedRule = null;
      for (const rule of cachedModerationRules) {
        if (!rule.is_active) continue;
        try {
          const regex = new RegExp(rule.pattern, 'i');
          if (regex.test(input)) {
            matchedRule = rule;
            break;
          }
        } catch (e) {}
      }

      if (matchedRule) {
        if (matchedRule.action === 'reject') {
          resultEl.innerHTML = `<span style="color:#fb7185; font-weight:700;">[REJECT TRIGGERED]</span> Blocked by rule <strong>${escapeHtml(matchedRule.name)}</strong> (Pattern: <code>${escapeHtml(matchedRule.pattern)}</code>). SMS rejected with HTTP 400.`;
        } else if (matchedRule.action === 'hold_for_approval') {
          resultEl.innerHTML = `<span style="color:#fbbf24; font-weight:700;">[QUARANTINE TRIGGERED]</span> Flagged by rule <strong>${escapeHtml(matchedRule.name)}</strong>. Status set to <code>pending_approval</code>.`;
        } else if (matchedRule.action === 'auto_replace') {
          const regex = new RegExp(matchedRule.pattern, 'gi');
          const replaced = input.replace(regex, matchedRule.replacement_text || '');
          resultEl.innerHTML = `<span style="color:#34d399; font-weight:700;">[AUTO-REPLACE TRIGGERED]</span> Rule <strong>${escapeHtml(matchedRule.name)}</strong> rewrites to: <div class="diff-card diff-modified" style="margin-top:6px;">${escapeHtml(replaced)}</div>`;
        }
      } else {
        resultEl.innerHTML = `<span style="color:#34d399; font-weight:700;">[CLEAN]</span> No firewall rules matched. Message dispatches normally.`;
      }
    });
  }

  const btnOpenAddDnd = document.getElementById('btn-open-add-dnd');
  if (btnOpenAddDnd) btnOpenAddDnd.addEventListener('click', () => openModal('modal-add-dnd'));

  const addDndForm = document.getElementById('add-dnd-form');
  if (addDndForm) {
    addDndForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const phone_number = document.getElementById('dnd-phone').value.trim();
      const reason = document.getElementById('dnd-reason').value;

      try {
        await apiFetch('/admin/dnd', {
          method: 'POST',
          body: { phone_number, reason, tenant_id: currentTenantId }
        });
        showToast(`Number ${phone_number} added to DND blacklist.`, 'success');
        closeModal('modal-add-dnd');
        addDndForm.reset();
        fetchDndList();
      } catch (err) {
        showToast(err.message, 'error');
      }
    });
  }

  const btnOpenCreateRule = document.getElementById('btn-open-create-rule');
  if (btnOpenCreateRule) btnOpenCreateRule.addEventListener('click', () => openModal('modal-create-rule'));

  const ruleActionSelect = document.getElementById('rule-action');
  if (ruleActionSelect) {
    ruleActionSelect.addEventListener('change', (e) => {
      const repGroup = document.getElementById('rule-replacement-group');
      if (repGroup) repGroup.style.display = e.target.value === 'auto_replace' ? 'block' : 'none';
    });
  }

  const createRuleForm = document.getElementById('create-rule-form');
  if (createRuleForm) {
    createRuleForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const name = document.getElementById('rule-name').value.trim();
      const pattern = document.getElementById('rule-pattern').value.trim();
      const action = document.getElementById('rule-action').value;
      const replacement_text = document.getElementById('rule-replacement-text').value.trim() || null;

      try {
        await apiFetch('/admin/moderation-rules', {
          method: 'POST',
          body: { name, pattern, action, replacement_text, is_active: true }
        });
        showToast(`Moderation rule '${name}' created!`, 'success');
        closeModal('modal-create-rule');
        createRuleForm.reset();
        fetchModerationRules();
      } catch (err) {
        showToast(err.message, 'error');
      }
    });
  }

  // ========================================================================
  // 13. IMMUTABLE CREDIT LEDGER
  // ========================================================================
  async function fetchLedger() {
    try {
      let url = '/admin/ledger?limit=100';
      if (currentTenantId) url += `&tenant_id=${encodeURIComponent(currentTenantId)}`;
      const transactions = await apiFetch(url);
      const tbody = document.getElementById('ledger-tbody');
      if (tbody) {
        if (!transactions || transactions.length === 0) {
          tbody.innerHTML = '<tr><td colspan="6" style="text-align: center; padding: 24px;">No ledger transactions recorded yet.</td></tr>';
        } else {
          tbody.innerHTML = transactions.map(tx => {
            const isPositive = tx.amount > 0;
            const deltaColor = isPositive ? '#34d399' : '#fb7185';
            const deltaSign = isPositive ? '+' : '';
            return `
              <tr>
                <td style="font-size: 12px; color: var(--text-dim);">${new Date(tx.created_at).toLocaleString()}</td>
                <td style="font-size: 12px; color: var(--text-muted);">${escapeHtml(tx.tenant_id ? tx.tenant_id.substring(0, 8) + '...' : 'Global Tenant')}</td>
                <td><span class="badge ${tx.tx_type === 'refund' ? 'badge-delivered' : tx.tx_type === 'topup' ? 'badge-role-tenant' : 'badge-queued'}">${escapeHtml(tx.tx_type)}</span></td>
                <td style="font-family: var(--font-mono); font-weight: 700; color: ${deltaColor};">${deltaSign}${tx.amount}</td>
                <td style="font-family: var(--font-mono); font-weight: 600; color: #fff;">${tx.balance_after.toLocaleString()}</td>
                <td style="font-size: 12px; color: var(--text-muted); max-width: 320px; overflow: hidden; text-overflow: ellipsis;" title="${escapeHtml(tx.reason || '')}">${escapeHtml(tx.reason || '—')}</td>
              </tr>
            `;
          }).join('');
        }
      }
    } catch (err) {
      console.error('Failed to fetch credit ledger:', err);
    }
  }

  // --- Modal Helpers ---
  function openModal(id) {
    const modal = document.getElementById(id);
    if (modal) modal.classList.add('open');
  }

  function closeModal(id) {
    const modal = document.getElementById(id);
    if (modal) modal.classList.remove('open');
    if (id === 'modal-pairing-code' && pairingCountdownInterval) {
      clearInterval(pairingCountdownInterval);
      pairingCountdownInterval = null;
    }
  }

  document.querySelectorAll('[data-close]').forEach((btn) => {
    btn.addEventListener('click', () => {
      const modalId = btn.getAttribute('data-close');
      if (modalId) closeModal(modalId);
    });
  });

  document.querySelectorAll('.modal-overlay').forEach((overlay) => {
    overlay.addEventListener('click', (e) => {
      if (e.target === overlay) {
        closeModal(overlay.id);
      }
    });
  });

  // --- Utility: Relative Time Formatter ---
  function formatTimeAgo(date) {
    const seconds = Math.floor((new Date() - date) / 1000);
    if (seconds < 5) return 'Just now';
    if (seconds < 60) return `${seconds}s ago`;
    const minutes = Math.floor(seconds / 60);
    if (minutes < 60) return `${minutes}m ago`;
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `${hours}h ago`;
    const days = Math.floor(hours / 24);
    return `${days}d ago`;
  }

  // --- Initialize Application on Load ---
  document.addEventListener('DOMContentLoaded', () => {
    checkAuth();
  });
})();
