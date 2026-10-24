/**
 * docs.js - Interactive Engine for SIM SMS Gateway Developer Documentation
 * Features:
 *  - Multi-language Code Generator (cURL, Python, Node.js, PHP, Java)
 *  - Live API Playground with real requests, headers & latency
 *  - Tanzania Phone Normalizer & MNO Detector
 *  - GSM-7 vs UCS-2 Segment & Cost Calculator
 *  - Webhook HMAC-SHA256 Signature Verifier
 *  - Fuzzy Search (Ctrl+K) & Scrollspy
 */

(function () {
  'use strict';

  // Base API configuration
  const API_CONFIG = {
    baseUrl: window.location.origin,
    apiKey: '',
    endpoints: {
      sendSms: {
        method: 'POST',
        path: '/api/v1/messages',
        body: JSON.stringify({
          recipient: '+255712345678',
          body: 'Hello from SIM SMS Gateway! Your verification code is 849201.',
          priority: 5,
          sim_slot: 1
        }, null, 2)
      },
      bulkSms: {
        method: 'POST',
        path: '/api/v1/messages/bundle',
        body: JSON.stringify({
          messages: [
            { recipient: '+255712345678', body: 'Monthly statement ready for account A101.' },
            { recipient: '+255754998877', body: 'Reminder: Scheduled maintenance tonight at 02:00 EAT.' }
          ],
          campaign_name: 'Monthly Notifications'
        }, null, 2)
      },
      listSms: {
        method: 'GET',
        path: '/api/v1/messages?limit=20&status=sent',
        body: ''
      },
      modifySms: {
        method: 'POST',
        path: '/api/v1/messages/MSG-UUID-HERE/modify',
        body: JSON.stringify({
          body: 'Updated text content prior to device dispatch',
          priority: 10,
          sim_slot: 2
        }, null, 2)
      },
      cancelSms: {
        method: 'POST',
        path: '/api/v1/messages/MSG-UUID-HERE/cancel',
        body: ''
      },
      listIncoming: {
        method: 'GET',
        path: '/api/v1/incoming?limit=25',
        body: ''
      },
      listDevices: {
        method: 'GET',
        path: '/api/v1/devices',
        body: ''
      },
      systemHealth: {
        method: 'GET',
        path: '/health',
        body: ''
      }
    }
  };

  // ==========================================================================
  // CODE SNIPPET GENERATOR
  // ==========================================================================
  function generateSnippet(lang, method, path, body, apiKey) {
    const url = `${API_CONFIG.baseUrl}${path}`;
    const token = apiKey || 'your_api_key_or_bearer_token_here';

    switch (lang) {
      case 'curl': {
        let cmd = `curl -X ${method} "${url}" \\\n  -H "Authorization: Bearer ${token}"`;
        if (body && (method === 'POST' || method === 'PUT' || method === 'PATCH')) {
          cmd += ` \\\n  -H "Content-Type: application/json" \\\n  -d '${body.replace(/\n/g, '\n  ')}'`;
        }
        return cmd;
      }

      case 'python': {
        let py = `import requests\n\n`;
        py += `url = "${url}"\n`;
        py += `headers = {\n    "Authorization": f"Bearer ${token}",\n    "Content-Type": "application/json"\n}\n`;
        if (body && (method === 'POST' || method === 'PUT' || method === 'PATCH')) {
          py += `payload = ${body}\n\n`;
          py += `response = requests.${method.toLowerCase()}(url, json=payload, headers=headers)\n`;
        } else {
          py += `response = requests.${method.toLowerCase()}(url, headers=headers)\n`;
        }
        py += `print(response.status_code)\nprint(response.json())\n`;
        return py;
      }

      case 'javascript': {
        let js = `const url = '${url}';\n\n`;
        let options = `{\n  method: '${method}',\n  headers: {\n    'Authorization': 'Bearer ${token}',\n    'Content-Type': 'application/json'\n  }`;
        if (body && (method === 'POST' || method === 'PUT' || method === 'PATCH')) {
          options += `,\n  body: JSON.stringify(${body.replace(/\n/g, '\n  ')})`;
        }
        options += `\n};`;
        js += `const response = await fetch(url, ${options});\n`;
        js += `const data = await response.json();\nconsole.log(data);`;
        return js;
      }

      case 'php': {
        let php = `<?php\n\n$ch = curl_init("${url}");\n`;
        php += `$headers = [\n    "Authorization: Bearer ${token}",\n    "Content-Type: application/json"\n];\n`;
        php += `curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);\n`;
        php += `curl_setopt($ch, CURLOPT_HTTPHEADER, $headers);\n`;
        if (method !== 'GET') {
          php += `curl_setopt($ch, CURLOPT_CUSTOMREQUEST, "${method}");\n`;
        }
        if (body && (method === 'POST' || method === 'PUT' || method === 'PATCH')) {
          php += `$payload = json_encode(${body});\n`;
          php += `curl_setopt($ch, CURLOPT_POSTFIELDS, $payload);\n`;
        }
        php += `$response = curl_exec($ch);\ncurl_close($ch);\n\nvar_dump(json_decode($response, true));\n`;
        return php;
      }

      case 'java': {
        let j = `import java.net.URI;\nimport java.net.http.HttpClient;\nimport java.net.http.HttpRequest;\nimport java.net.http.HttpResponse;\n\n`;
        j += `HttpClient client = HttpClient.newHttpClient();\n`;
        j += `HttpRequest.Builder builder = HttpRequest.newBuilder()\n`;
        j += `    .uri(URI.create("${url}"))\n`;
        j += `    .header("Authorization", "Bearer ${token}")\n`;
        j += `    .header("Content-Type", "application/json");\n\n`;
        if (body && (method === 'POST' || method === 'PUT' || method === 'PATCH')) {
          j += `String jsonBody = """\n${body}\n""";\n`;
          j += `HttpRequest request = builder.POST(HttpRequest.BodyPublishers.ofString(jsonBody)).build();\n`;
        } else {
          j += `HttpRequest request = builder.GET().build();\n`;
        }
        j += `HttpResponse<String> response = client.send(request, HttpResponse.BodyHandlers.ofString());\n`;
        j += `System.out.println(response.statusCode() + " " + response.body());\n`;
        return j;
      }

      default:
        return '';
    }
  }

  // ==========================================================================
  // COPY TO CLIPBOARD
  // ==========================================================================
  function initCopyButtons() {
    document.querySelectorAll('.btn-copy-code').forEach(btn => {
      btn.addEventListener('click', async () => {
        const targetId = btn.getAttribute('data-target');
        const codeElem = targetId ? document.getElementById(targetId) : btn.closest('.endpoint-code-col').querySelector('pre code');
        if (!codeElem) return;

        try {
          await navigator.clipboard.writeText(codeElem.innerText);
          const originalText = btn.innerHTML;
          btn.innerHTML = `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#34d399" stroke-width="2.5"><polyline points="20 6 9 17 4 12"></polyline></svg> <span style="color: #34d399;">Copied!</span>`;
          setTimeout(() => {
            btn.innerHTML = originalText;
          }, 2000);
        } catch (e) {
          console.error('Failed to copy', e);
        }
      });
    });
  }

  // ==========================================================================
  // CODE TABS SWITCHER
  // ==========================================================================
  function initCodeTabs() {
    document.querySelectorAll('.endpoint-panel').forEach(panel => {
      const langBtns = panel.querySelectorAll('.code-lang-btn');
      const codeBlock = panel.querySelector('pre code');
      const method = panel.getAttribute('data-method') || 'GET';
      const path = panel.getAttribute('data-path') || '/';
      const rawBody = panel.getAttribute('data-body') || '';

      langBtns.forEach(btn => {
        btn.addEventListener('click', () => {
          langBtns.forEach(b => b.classList.remove('active'));
          btn.classList.add('active');
          const lang = btn.getAttribute('data-lang');
          if (codeBlock) {
            codeBlock.innerText = generateSnippet(lang, method, path, rawBody, API_CONFIG.apiKey);
          }
        });
      });

      // Default initialize to curl
      if (codeBlock) {
        codeBlock.innerText = generateSnippet('curl', method, path, rawBody, API_CONFIG.apiKey);
      }
    });
  }

  // ==========================================================================
  // TANZANIA MNO DETECTOR & PHONE NORMALIZER
  // ==========================================================================
  const MNO_PREFIXES = {
    'Vodacom': { prefixes: ['74', '75', '76'], tagClass: 'mno-voda' },
    'Airtel': { prefixes: ['68', '69', '78'], tagClass: 'mno-airtel' },
    'Tigo / Yas': { prefixes: ['65', '67', '71'], tagClass: 'mno-tigo' },
    'Halotel': { prefixes: ['61', '62'], tagClass: 'mno-halo' },
    'TTCL': { prefixes: ['73'], tagClass: 'mno-ttcl' }
  };

  function normalizeTzPhone(rawInput) {
    if (!rawInput) return null;
    let cleaned = rawInput.replace(/[^0-9+]/g, '');

    if (cleaned.startsWith('+255')) {
      cleaned = cleaned.substring(4);
    } else if (cleaned.startsWith('255')) {
      cleaned = cleaned.substring(3);
    } else if (cleaned.startsWith('0')) {
      cleaned = cleaned.substring(1);
    }

    if (cleaned.length !== 9) {
      return { valid: false, error: 'Tanzanian phone numbers must have 9 digits after +255.' };
    }

    const prefix2 = cleaned.substring(0, 2);
    let detectedMno = 'Unknown MNO';
    let tagClass = 'mno-halo';

    for (const [mno, data] of Object.entries(MNO_PREFIXES)) {
      if (data.prefixes.includes(prefix2)) {
        detectedMno = mno;
        tagClass = data.tagClass;
        break;
      }
    }

    return {
      valid: true,
      canonical: `+255${cleaned}`,
      national: `0${cleaned}`,
      mno: detectedMno,
      tagClass: tagClass,
      prefix: prefix2,
      recommendedSim: detectedMno === 'Vodacom' ? 'SIM 1 (Vodacom)' : (detectedMno === 'Airtel' ? 'SIM 2 (Airtel)' : 'Auto-fallback')
    };
  }

  function initPhoneNormalizerWidget() {
    const input = document.getElementById('tz-phone-test-input');
    const resultBox = document.getElementById('tz-phone-test-result');
    if (!input || !resultBox) return;

    input.addEventListener('input', () => {
      const val = input.value.trim();
      if (!val) {
        resultBox.style.display = 'none';
        return;
      }

      const res = normalizeTzPhone(val);
      resultBox.style.display = 'flex';

      if (!res.valid) {
        resultBox.innerHTML = `
          <div class="result-item" style="color: var(--color-rose);">
            <span>Invalid Format:</span>
            <span>${res.error}</span>
          </div>
        `;
        return;
      }

      resultBox.innerHTML = `
        <div class="result-item">
          <span class="result-label">Canonical (E.164):</span>
          <span class="result-value" style="color: var(--color-cyan);">${res.canonical}</span>
        </div>
        <div class="result-item">
          <span class="result-label">National Dialing:</span>
          <span class="result-value">${res.national}</span>
        </div>
        <div class="result-item">
          <span class="result-label">Identified Operator:</span>
          <span class="mno-tag ${res.tagClass}">${res.mno}</span>
        </div>
        <div class="result-item">
          <span class="result-label">Recommended SIM Gateway Slot:</span>
          <span class="result-value" style="color: #34d399;">${res.recommendedSim}</span>
        </div>
      `;
    });
  }

  // ==========================================================================
  // GSM-7 VS UCS-2 SEGMENT & CHAR CALCULATOR
  // ==========================================================================
  const GSM7_CHARS = "@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞ\x1bÆæßÉ !\"#¤%&'()*+,-./0123456789:;<=>?¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ`abcdefghijklmnopqrstuvwxyzäöñüà";
  const GSM7_EXTENDED = "^{}\\[~]|€";

  function analyzeSmsEncoding(text) {
    if (!text) {
      return { chars: 0, isGsm7: true, encoding: 'GSM-7 (Standard)', segments: 0, costTzs: 0 };
    }

    let isGsm7 = true;
    let gsmCharLength = 0;

    for (const char of text) {
      if (GSM7_CHARS.includes(char)) {
        gsmCharLength += 1;
      } else if (GSM7_EXTENDED.includes(char)) {
        gsmCharLength += 2; // Escape + char in GSM-7
      } else {
        isGsm7 = false;
        break;
      }
    }

    const chars = text.length;
    let segments = 0;
    let encoding = isGsm7 ? 'GSM-7 (Standard English & Swahili)' : 'UCS-2 (Unicode / Emojis)';

    if (isGsm7) {
      if (gsmCharLength <= 160) {
        segments = 1;
      } else {
        segments = Math.ceil(gsmCharLength / 153);
      }
    } else {
      if (chars <= 70) {
        segments = 1;
      } else {
        segments = Math.ceil(chars / 67);
      }
    }

    const costTzs = segments * 20; // Avg 20 TZS per bundle segment

    return {
      chars: chars,
      isGsm7: isGsm7,
      encoding: encoding,
      segments: segments,
      costTzs: costTzs
    };
  }

  function initSegmentCalculatorWidget() {
    const input = document.getElementById('sms-calc-textarea');
    const resultBox = document.getElementById('sms-calc-result');
    if (!input || !resultBox) return;

    input.addEventListener('input', () => {
      const text = input.value;
      const res = analyzeSmsEncoding(text);

      resultBox.innerHTML = `
        <div class="result-item">
          <span class="result-label">Total Characters:</span>
          <span class="result-value">${res.chars}</span>
        </div>
        <div class="result-item">
          <span class="result-label">Detected Encoding:</span>
          <span class="result-value" style="color: ${res.isGsm7 ? '#34d399' : '#f59e0b'};">${res.encoding}</span>
        </div>
        <div class="result-item">
          <span class="result-label">SMS Billable Segments:</span>
          <span class="result-value" style="font-size: 16px; color: var(--color-cyan);">${res.segments} ${res.segments === 1 ? 'Part' : 'Parts (Concatenated)'}</span>
        </div>
        <div class="result-item">
          <span class="result-label">Estimated MNO Carrier Cost:</span>
          <span class="result-value" style="color: #a5b4fc;">~${res.costTzs} TZS</span>
        </div>
      `;
    });
  }

  // ==========================================================================
  // WEBHOOK SIGNATURE CALCULATOR (HMAC-SHA256)
  // ==========================================================================
  async function computeHmacSha256(secret, payload) {
    const enc = new TextEncoder();
    const key = await crypto.subtle.importKey(
      'raw',
      enc.encode(secret),
      { name: 'HMAC', hash: 'SHA-256' },
      false,
      ['sign']
    );
    const signature = await crypto.subtle.sign('HMAC', key, enc.encode(payload));
    const hashArray = Array.from(new Uint8Array(signature));
    return hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
  }

  function initWebhookTesterWidget() {
    const secretInput = document.getElementById('wh-secret-input');
    const payloadInput = document.getElementById('wh-payload-input');
    const sigResult = document.getElementById('wh-signature-result');
    const btnCalc = document.getElementById('btn-calc-wh-sig');
    if (!secretInput || !payloadInput || !sigResult || !btnCalc) return;

    btnCalc.addEventListener('click', async () => {
      const secret = secretInput.value.trim();
      const payload = payloadInput.value.trim();
      if (!secret || !payload) {
        sigResult.innerText = 'Error: Both webhook secret and payload are required.';
        sigResult.style.color = 'var(--color-rose)';
        return;
      }

      try {
        const hex = await computeHmacSha256(secret, payload);
        sigResult.innerText = hex;
        sigResult.style.color = '#34d399';
      } catch (e) {
        sigResult.innerText = `Calculation failed: ${e.message}`;
        sigResult.style.color = 'var(--color-rose)';
      }
    });
  }

  // ==========================================================================
  // LIVE API PLAYGROUND RUNNER
  // ==========================================================================
  function initPlayground() {
    const select = document.getElementById('playground-endpoint-select');
    const methodBadge = document.getElementById('playground-method-badge');
    const pathInput = document.getElementById('playground-path-input');
    const authInput = document.getElementById('playground-auth-input');
    const bodyTextarea = document.getElementById('playground-body-input');
    const btnExecute = document.getElementById('btn-playground-execute');
    const statusBadge = document.getElementById('playground-status-badge');
    const timeBadge = document.getElementById('playground-time-badge');
    const responseOutput = document.getElementById('playground-response-output');

    if (!select || !btnExecute) return;

    // Load endpoint template on change
    select.addEventListener('change', () => {
      const key = select.value;
      const endpoint = API_CONFIG.endpoints[key];
      if (!endpoint) return;

      methodBadge.innerText = endpoint.method;
      methodBadge.className = `method-pill ${endpoint.method.toLowerCase()}`;
      pathInput.value = endpoint.path;
      bodyTextarea.value = endpoint.body;
      bodyTextarea.style.display = (endpoint.method === 'GET' || endpoint.method === 'DELETE') ? 'none' : 'block';
    });

    // Execute API Call
    btnExecute.addEventListener('click', async () => {
      const path = pathInput.value.trim();
      const method = methodBadge.innerText;
      const token = authInput.value.trim();
      const body = bodyTextarea.value.trim();

      statusBadge.innerText = 'Sending...';
      statusBadge.style.color = '#94a3b8';
      timeBadge.innerText = '...';
      responseOutput.innerText = '/* Dispatching request to live gateway... */';
      btnExecute.disabled = true;
      btnExecute.style.opacity = '0.6';

      const startTime = performance.now();
      const headers = {
        'Accept': 'application/json'
      };
      if (token) {
        headers['Authorization'] = `Bearer ${token}`;
      }
      if (body && method !== 'GET') {
        headers['Content-Type'] = 'application/json';
      }

      try {
        const fetchOptions = {
          method: method,
          headers: headers
        };
        if (body && (method === 'POST' || method === 'PUT' || method === 'PATCH')) {
          fetchOptions.body = body;
        }

        const res = await fetch(path, fetchOptions);
        const duration = Math.round(performance.now() - startTime);

        timeBadge.innerText = `${duration} ms`;
        statusBadge.innerText = `${res.status} ${res.statusText || ''}`;
        statusBadge.style.color = res.ok ? '#34d399' : (res.status === 401 ? '#f59e0b' : '#f43f5e');

        const contentType = res.headers.get('content-type') || '';
        if (contentType.includes('application/json')) {
          const json = await res.json();
          responseOutput.innerText = JSON.stringify(json, null, 2);
        } else {
          const text = await res.text();
          responseOutput.innerText = text;
        }
      } catch (err) {
        const duration = Math.round(performance.now() - startTime);
        timeBadge.innerText = `${duration} ms`;
        statusBadge.innerText = 'Network Error';
        statusBadge.style.color = '#f43f5e';
        responseOutput.innerText = `Network/CORS Error: ${err.message}\nMake sure your server is online and allows requests from this origin.`;
      } finally {
        btnExecute.disabled = false;
        btnExecute.style.opacity = '1';
      }
    });

    // Preset "Try in playground" triggers from cards
    document.querySelectorAll('.btn-try-endpoint').forEach(btn => {
      btn.addEventListener('click', () => {
        const target = btn.getAttribute('data-endpoint-key');
        if (target && API_CONFIG.endpoints[target]) {
          select.value = target;
          select.dispatchEvent(new Event('change'));
          document.getElementById('section-playground').scrollIntoView({ behavior: 'smooth' });
        }
      });
    });
  }

  // ==========================================================================
  // SEARCH MODAL (CTRL+K)
  // ==========================================================================
  function initSearchModal() {
    const trigger = document.getElementById('docs-search-trigger');
    const overlay = document.getElementById('docs-search-modal');
    const input = document.getElementById('docs-search-input');
    const resultsContainer = document.getElementById('docs-search-results');

    if (!overlay || !input || !resultsContainer) return;

    function openModal() {
      overlay.classList.add('open');
      input.value = '';
      input.focus();
      renderSearchResults('');
    }

    function closeModal() {
      overlay.classList.remove('open');
    }

    if (trigger) trigger.addEventListener('click', openModal);

    overlay.addEventListener('click', (e) => {
      if (e.target === overlay) closeModal();
    });

    window.addEventListener('keydown', (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
        e.preventDefault();
        openModal();
      }
      if (e.key === 'Escape' && overlay.classList.contains('open')) {
        closeModal();
      }
    });

    // Index searchable sections
    const searchableItems = [];
    document.querySelectorAll('[data-search-title]').forEach(el => {
      searchableItems.push({
        id: el.id,
        title: el.getAttribute('data-search-title'),
        category: el.getAttribute('data-search-cat') || 'Documentation',
        badge: el.getAttribute('data-search-badge') || ''
      });
    });

    function renderSearchResults(query) {
      const q = query.toLowerCase().trim();
      const matches = q
        ? searchableItems.filter(item => item.title.toLowerCase().includes(q) || item.category.toLowerCase().includes(q))
        : searchableItems.slice(0, 8);

      if (matches.length === 0) {
        resultsContainer.innerHTML = `<div style="padding: 24px; text-align: center; color: var(--text-dim); font-size: 13px;">No matching documentation topics found.</div>`;
        return;
      }

      resultsContainer.innerHTML = matches.map(item => `
        <a href="#${item.id}" class="search-result-item" onclick="document.getElementById('docs-search-modal').classList.remove('open')">
          <span style="font-size: 11px; text-transform: uppercase; color: var(--color-primary); font-weight: 700; width: 90px;">${item.category}</span>
          <span style="font-weight: 600; color: #fff; flex: 1;">${item.title}</span>
          ${item.badge ? `<span class="sidebar-badge ${item.badge.toLowerCase()}">${item.badge}</span>` : ''}
        </a>
      `).join('');
    }

    input.addEventListener('input', () => {
      renderSearchResults(input.value);
    });
  }

  // ==========================================================================
  // SCROLLSPY
  // ==========================================================================
  function initScrollspy() {
    const sections = document.querySelectorAll('.doc-section');
    const navLinks = document.querySelectorAll('.sidebar-link');

    window.addEventListener('scroll', () => {
      let currentId = '';
      const scrollPos = window.scrollY + 100;

      sections.forEach(sec => {
        if (sec.offsetTop <= scrollPos) {
          currentId = sec.getAttribute('id');
        }
      });

      if (currentId) {
        navLinks.forEach(link => {
          link.classList.remove('active');
          if (link.getAttribute('href') === `#${currentId}`) {
            link.classList.add('active');
          }
        });
      }
    }, { passive: true });
  }

  // ==========================================================================
  // LIVE HEALTH BADGE PROBE
  // ==========================================================================
  async function checkLiveHealth() {
    const badgeText = document.getElementById('header-health-text');
    if (!badgeText) return;

    try {
      const res = await fetch('/health');
      if (res.ok) {
        const data = await res.json();
        const activeDevices = (data.metrics && data.metrics.active_devices !== undefined) ? data.metrics.active_devices : 0;
        badgeText.innerText = `Online (${activeDevices} active ${activeDevices === 1 ? 'phone' : 'phones'})`;
      } else {
        badgeText.innerText = 'Degraded';
        badgeText.style.color = '#f59e0b';
      }
    } catch {
      badgeText.innerText = 'Connecting...';
    }
  }

  // ==========================================================================
  // BOOTSTRAP
  // ==========================================================================
  document.addEventListener('DOMContentLoaded', () => {
    initCopyButtons();
    initCodeTabs();
    initPhoneNormalizerWidget();
    initSegmentCalculatorWidget();
    initWebhookTesterWidget();
    initPlayground();
    initSearchModal();
    initScrollspy();
    checkLiveHealth();
    setInterval(checkLiveHealth, 30000);
  });

})();
