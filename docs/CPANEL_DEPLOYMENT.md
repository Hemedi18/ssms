# Deploying SIM SMS Gateway to cPanel (`sms.edusphere.co.tz`)

This document provides a step-by-step guide for deploying and operating the **Multi-Tenant SIM SMS Gateway (Tanzania Edition)** on cPanel using **CloudLinux / Phusion Passenger ("Setup Python App")**.

---

## 1. Prerequisites on cPanel

1. **Subdomain:** Ensure `sms.edusphere.co.tz` is configured in **cPanel > Subdomains** (pointing to a document root such as `/home/eduspher/sms.edusphere.co.tz`).
2. **SSL / TLS Certificate:** Ensure **cPanel > AutoSSL** or **Let's Encrypt** has issued a valid HTTPS certificate for `sms.edusphere.co.tz`.
3. **Python Feature:** Ensure **cPanel > Setup Python App** is available.

---

## 2. Deployment Methods

### Method A: Uploading the Pre-Built Archive (Fastest)

1. Open **cPanel > File Manager**.
2. Navigate to your application root folder (e.g. `/home/eduspher/sms.edusphere.co.tz`).
3. Upload `sms_gateway_cpanel_deploy.tar.gz` from your local machine.
4. Right-click and **Extract** the archive directly into the folder.
   - The directory should now contain:
     ```
     app/
     passenger_wsgi.py
     pyproject.toml
     requirements.txt
     alembic.ini
     ```

### Method B: Via cPanel Terminal / Git

1. Open **cPanel > Terminal**.
2. Navigate to your home directory:
   ```bash
   cd /home/eduspher/sms.edusphere.co.tz
   ```
3. Copy or clone your repository files into this folder.

---

## 3. Configuring "Setup Python App" in cPanel

1. Go to **cPanel > Setup Python App**.
2. Click **Create Application**.
3. Fill in the parameters:
   - **Python Version:** Select `3.11` or `3.12`.
   - **Application Root:** `sms.edusphere.co.tz` (relative to `/home/eduspher`).
   - **Application URL:** `sms.edusphere.co.tz`.
   - **Application Startup File:** `passenger_wsgi.py`.
   - **Application Entry Point:** `application`.
   - **Passenger Log File:** `/home/eduspher/logs/passenger.log` (optional, for debugging).
4. Click **Create**.
5. Once created, cPanel will display a command to activate the virtual environment at the top of the page, e.g.:
   ```bash
   source /home/eduspher/virtualenv/sms.edusphere.co.tz/3.11/bin/activate && cd /home/eduspher/sms.edusphere.co.tz
   ```
6. Click **Run Pip Install** or run via cPanel Terminal:
   ```bash
   pip install -r requirements.txt
   ```

---

## 4. Production Environment Configuration (`.env`)

In the application root (`/home/eduspher/sms.edusphere.co.tz`), create or edit `.env`:

```ini
APP_NAME="SIM SMS Gateway"
ENVIRONMENT="production"
DEBUG=false

# Security: Generate a strong 64-char key
SECRET_KEY="replace-with-a-random-64-character-hex-string"
ALLOWED_ORIGINS=["https://sms.edusphere.co.tz"]

# Database: SQLite is supported out of the box in a secure directory,
# or you can use a cPanel MySQL / PostgreSQL database:
DATABASE_URL="sqlite:///./sms_gateway.db"
# DATABASE_URL="mysql+pymysql://eduspher_sms:YourPassword@localhost/eduspher_smsdb"

# Tanzania Gateway Defaults
DEFAULT_COUNTRY_CODE="+255"
RATE_LIMIT_PER_MINUTE=120
DEVICE_OFFLINE_THRESHOLD_SECONDS=180
```

---

## 5. Restarting the cPanel Python Application

Whenever you make changes to backend code or settings:
1. In **cPanel > Setup Python App**, click **Restart**.
2. Alternatively, via Terminal:
   ```bash
   touch /home/eduspher/sms.edusphere.co.tz/tmp/restart.txt
   ```

---

## 6. How to Use the Gateway Platform

### Step 1: Accessing the Dashboard & Super Admin Login
- Open your browser to `https://sms.edusphere.co.tz`.
- You will be greeted by the dark/light glassmorphic UI.
- Use your administrator credentials or API key:
  - Default Admin Username: `admin@gateway.local` (or legacy `admin`)
  - Default Admin Password: `admin` (update immediately in production)

### Step 2: Pairing the Android Gateway Smartphone
1. Open the **SIM Gateway** app on your physical Android phone (with SIM cards from Vodacom, Airtel, Tigo/Yas, or Halotel inserted).
2. Set the **Server URL** in the Android app to:
   ```
   https://sms.edusphere.co.tz
   ```
3. In the Web Dashboard, navigate to **Devices** tab and click **Generate Pairing Code**.
4. Enter the generated 6-digit code on the Android phone.
5. Once paired, the phone appears in the **SIM Card & Hardware Fleet Matrix** showing:
   - Rolling 30-min throttle guard gauge (`X / 28 SMS in 30m`).
   - Battery health & temperature.
   - Per-SIM slot status (Slot 0 and Slot 1, carrier names, and On-Net indicators).

### Step 3: Sending Single & Bulk SMS
- **REST API:**
  ```bash
  curl -X POST https://sms.edusphere.co.tz/api/v1/messages \
    -H "Authorization: Bearer <YOUR_API_KEY>" \
    -H "Content-Type: application/json" \
    -d '{
      "to": "+255754123456",
      "body": "{Habari|Mambo} Juma, salio lako la EduSphere ni Tsh 50,000.",
      "message_type": "transactional",
      "priority": 10
    }'
  ```
- **Web UI Campaign Studio:**
  1. Open **Messages > Compose**.
  2. Paste recipient numbers or upload a CSV file with columns (`phone`, `name`, `amount`).
  3. Use Spintax syntax `{Habari|Mambo|Ndugu}` to prevent carrier spam fingerprinting.
  4. View the live **Tanzanian MNO Breakdown** chart (Vodacom vs Airtel vs Yas vs Halotel) and click **Send**.

### Step 4: Per-SMS Quarantine & Pre-Dispatch Modification
- Click on any message in the **Quarantine** or **Messages** table.
- The **Slide-Over Drawer** opens:
  - Inspect the **Original Body** vs **Modified Body**.
  - Review live **GSM-7 / UCS-2 character & septet counts**.
  - Modify the text or force-reroute to a specific SIM slot before it hits the phone radio.
  - Approve or Reject with automatic credit refunds.

### Step 5: TCRA Quiet Hours & Auto-Opt-Out Compliance
- Promotional quiet hours (21:00 to 06:00 EAT) automatically delay `promotional` messages to 06:00 EAT while transactional OTPs dispatch immediately.
- Any incoming SMS matching `STOP`, `ONDOA`, `JIONDOE`, or `UNSUBSCRIBE` automatically inserts the number into the **DND Blacklist**, preventing further promotional dispatches.

### Step 6: Emergency Kill Switch
- In case of network anomalies, click the **Emergency Kill Switch** button in the top navigation bar to immediately halt outbound job leasing across devices without losing queued messages or dropping incoming webhooks.

---

## 7. AI Auto-Response Control & Owner Escalation (Email Forwarder Setup)

### Setting Up cPanel Email Forwarder for Owner Alerts:
When a customer sends an SMS containing **"I need to communicate with owner"** (or in Swahili *"nataka kuongea na mmliki/bosi"*):
1. The AI auto-response is **immediately paused** for that specific customer.
2. An urgent alert email is dispatched to `notifications@edusphere.co.tz` and `hemedimdoe18@gmail.com`.

**To ensure forwarders are active in cPanel:**
1. Log into your cPanel account for `edusphere.co.tz`.
2. Navigate to **Email > Forwarders** (`/cpsess.../email/fwd.html`).
3. Click **Add Forwarder**.
4. In **Address to Forward**, enter:
   - `notifications` @ `edusphere.co.tz`
5. In **Destination**, select **Forward to Email Address** and enter:
   - `hemedimdoe18@gmail.com`
6. Click **Add Forwarder**.
7. Now, every alert delivered to `notifications@edusphere.co.tz` will automatically copy `hemedimdoe18@gmail.com` in real time with the customer's phone number and full recent chat transcript.

### Managing AI Smart Switch & Blocked Numbers:
- **On the Android Gateway App:**
  - In **Received Messages**, each message card features a **Smart Switch** to toggle AI replies ON/OFF for that contact, plus a **Block** button.
  - In **Message Details**, you can view and control the contact's AI auto-reply state or unblock them at any time.
- **On the Backend API:**
  - `GET /api/v1/incoming/chat-preferences` lists all per-number preferences.
  - `POST /api/v1/incoming/chat-preferences` allows updating `is_ai_enabled`, `is_blocked`, and `is_escalated`.
