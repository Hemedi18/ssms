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
  let refreshTimer = null;
  let pairingCountdownInterval = null;
  let trafficChartInstance = null;
  let statusChartInstance = null;
  let activeStatusFilter = '';
  let cachedMessages = [];

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
      if (!tbody) return;

      if (!devices || devices.length === 0) {
        tbody.innerHTML = `
          <tr>
            <td colspan="8" style="text-align: center; padding: 40px; color: var(--text-dim);">
              No Android devices paired yet. Click <strong>Generate Pairing Code</strong> above to connect your phone.
            </td>
          </tr>
        `;
        return;
      }

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
      const messages = await apiFetch(`/messages?limit=100${activeStatusFilter ? '&status_filter=' + activeStatusFilter : ''}`);
      cachedMessages = messages || [];
      renderMessagesTable(cachedMessages);
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
          <td colspan="7" style="text-align: center; padding: 40px; color: var(--text-dim);">
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
        else if (m.status === 'failed') badgeClass = 'badge-failed';
        else if (m.status === 'sending') badgeClass = 'badge-sending';

        const timeStr = new Date(m.created_at).toLocaleString();

        return `
          <tr>
            <td class="mono-cell" style="font-size: 11px; color: var(--text-dim);">${escapeHtml(m.id.substring(0, 8))}...</td>
            <td class="mono-cell" style="font-weight: 600; color: #fff;">${escapeHtml(m.to)}</td>
            <td style="max-width: 320px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;" title="${escapeHtml(m.body)}">
              ${escapeHtml(m.body)}
            </td>
            <td><span class="badge ${badgeClass}">${escapeHtml(m.status)}</span></td>
            <td style="font-size: 12px; color: var(--text-muted);">${escapeHtml(m.device_id ? m.device_id.substring(0, 8) : 'Pending')}</td>
            <td style="font-size: 12px; color: var(--text-dim);">${escapeHtml(timeStr)}</td>
            <td>
              <div style="display: flex; gap: 6px;">
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
  }

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
