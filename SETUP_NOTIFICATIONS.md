# Alchemy — Notification Adapter Setup Guide

Complete step-by-step guide to configure Gmail, Telegram, and WhatsApp
alerts for trade signals, order fills, risk events, and emergency stops.

---

## 1. Gmail / SMTP (Email OTP + Alerts)

Gmail is used for two purposes:
- **Email OTP** — account verification and 2FA backup codes
- **Trade alerts** — optional email notifications for signals

### Step 1: Enable 2-Step Verification

1. Go to **myaccount.google.com**
2. Click **Security** in the left sidebar
3. Under "How you sign in to Google" click **2-Step Verification**
4. Follow the setup wizard (use your phone number)

### Step 2: Create App Password

1. Return to **myaccount.google.com → Security**
2. Scroll to **"2-Step Verification"** → click it → scroll to bottom
3. Click **"App passwords"**
4. Under "Select app" choose **Mail**
5. Under "Select device" choose **Other** → type `Alchemy`
6. Click **Generate** → copy the **16-character password** shown
   - Example: `abcd efgh ijkl mnop`
   - Remove spaces before saving: `abcdefghijklmnop`

### Step 3: Add to .env.production on VPS

```bash
nano /opt/alchemy/.env.production
```

Add or update these lines:
```env
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your.email@gmail.com
SMTP_PASSWORD=abcdefghijklmnop
SMTP_FROM=your.email@gmail.com
```

### Step 4: Restart to apply

```bash
cd /opt/alchemy && alchemy-update
```

### Step 5: Test

```bash
curl -s -X POST https://akilamirthya.in/api/auth/otp/send \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -d '{"email":"admin@alchemy.in","purpose":"verification"}'
```

✅ **Success:** Email arrives within 30 seconds
❌ **Error:** Check `docker logs alchemy-app-1 2>&1 | grep "smtp\|email"`

### Troubleshooting Gmail
| Error | Fix |
|-------|-----|
| `534 5.7.9 Application-specific password required` | 2-Step Verification not enabled |
| `535 5.7.8 Invalid credentials` | Wrong app password — regenerate |
| `Connection refused port 587` | Firewall blocking outbound — try port 465 with `SMTP_TLS=false` |
| `Email not arriving` | Check spam folder; verify SMTP_FROM matches SMTP_USER |

### Alternative: Outlook / Office 365
```env
SMTP_HOST=smtp.office365.com
SMTP_PORT=587
SMTP_USER=you@outlook.com
SMTP_PASSWORD=your_outlook_password
```

---

## 2. Telegram Bot (Trade Alerts)

Telegram is the **recommended** alert channel — free, instant, rich formatting.

### Step 1: Create a Telegram Bot

1. Open **Telegram** app on your phone or telegram.web.app
2. Search for **@BotFather** and open the chat
3. Send: `/newbot`
4. When asked for a name, send: `Alchemy Alerts`
5. When asked for a username, send: `AlchemyAlerts_YourName_bot`
   (must end in `_bot`, must be unique)
6. **Copy the bot token** — looks like:
   ```
   5432198765:AAFr8kXY-abc123def456ghi789jkl012mno
   ```

### Step 2: Get Your Chat ID

**Method A (easiest):**
1. In Telegram, search for **@userinfobot**
2. Send `/start`
3. It replies with: `Your ID: 123456789`
4. That number is your Chat ID

**Method B (via API):**
```bash
# Replace YOUR_BOT_TOKEN with your actual token
curl "https://api.telegram.org/botYOUR_BOT_TOKEN/getUpdates"
```
Send any message to your bot first, then run this.
Look for `"chat":{"id":123456789}` in the response.

### Step 3: Start the Bot

⚠️ **Critical:** You must send `/start` to your bot before it can message you.

1. In Telegram, search for your bot by username (e.g. `@AlchemyAlerts_YourName_bot`)
2. Click **Start** or send `/start`

### Step 4: Configure in Alchemy

1. Open **https://akilamirthya.in**
2. Log in → click **Notifications** in the sidebar
3. Click **+ Add Channel** → select **Telegram**
4. Fill in:
   - **Channel Name:** `My Telegram`
   - **Bot Token:** `5432198765:AAFr8kXY-abc123...`
   - **Chat ID:** `123456789`
   - **Parse Mode:** `MarkdownV2` (default)
5. Click **Test Connection** — you should receive a test message

### Step 5: Set Alert Rules

In Notifications → **Rules** tab, enable alerts for:
- 🟢 Signal generated (buy/sell)
- 🔴 Emergency stop activated
- 📋 Order filled
- ⚠️ High risk event

### Group/Channel Alerts

To send alerts to a **Telegram group** (for trading teams):

1. Create a group in Telegram
2. Add your bot to the group (search bot username → Add to Group)
3. Send any message in the group
4. Get the group Chat ID (it's a **negative number**):
   ```bash
   curl "https://api.telegram.org/botYOUR_TOKEN/getUpdates" | python3 -m json.tool
   # Look for: "chat": {"id": -100123456789, "type": "group"}
   ```
5. Use that negative ID in Alchemy's Chat ID field

### Troubleshooting Telegram
| Error | Fix |
|-------|-----|
| `400 Bad Request: chat not found` | You haven't sent /start to the bot |
| `403 Forbidden: bot was blocked` | User blocked the bot — unblock and /start again |
| `401 Unauthorized` | Bot token is wrong — check with @BotFather → /mybots |
| Messages not arriving | Bot may be in a group without Send Messages permission |

### Test via curl
```bash
# Replace TOKEN and CHAT_ID
curl -s -X POST "https://api.telegram.org/botTOKEN/sendMessage" \
  -H "Content-Type: application/json" \
  -d '{"chat_id":"CHAT_ID","text":"🔮 Alchemy test message!","parse_mode":"HTML"}'
# Should return: {"ok":true,"result":{"message_id":...}}
```

---

## 3. WhatsApp (Trade Alerts)

Two options: **Twilio** (recommended, easy sandbox) or **Meta Cloud API** (official, requires verification).

---

### Option A: Twilio WhatsApp (Recommended — 15 min setup)

#### Step 1: Create Twilio Account

1. Go to **twilio.com** → Sign Up (free trial, no credit card needed)
2. Verify your email and phone number
3. In the console, find your **Account SID** and **Auth Token**
   - Example SID: `ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`
   - Auth Token: `xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`

#### Step 2: Enable WhatsApp Sandbox

1. In Twilio Console → **Messaging** → **Try it out** → **Send a WhatsApp message**
2. You'll see a sandbox number: **+1 415 523 8886** and a join keyword
3. From your WhatsApp, send the keyword to that number:
   ```
   join KEYWORD-HERE
   ```
   Example: `join bright-river`
4. You'll receive a confirmation message from Twilio

#### Step 3: Configure in Alchemy

1. Open **https://akilamirthya.in** → Notifications → + Add Channel → WhatsApp
2. Fill in:
   - **API Provider:** `twilio`
   - **Your WhatsApp Number:** `+919876543210` (E.164 format with country code)
   - **Twilio Account SID:** `ACxxxx...`
   - **Twilio Auth Token:** `xxxx...`
   - **Twilio WhatsApp From:** `whatsapp:+14155238886`
3. Click **Test Connection**

#### Step 4: Test via curl
```bash
# Replace with your values
ACCOUNT_SID="ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
AUTH_TOKEN="xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
YOUR_NUMBER="+919876543210"

curl -X POST "https://api.twilio.com/2010-04-01/Accounts/$ACCOUNT_SID/Messages.json" \
  -u "$ACCOUNT_SID:$AUTH_TOKEN" \
  --data-urlencode "From=whatsapp:+14155238886" \
  --data-urlencode "To=whatsapp:$YOUR_NUMBER" \
  --data-urlencode "Body=🔮 Alchemy WhatsApp test!"
# Returns: {"status":"queued","sid":"SMxxx..."}
```

#### Move to Production (after testing)
- Apply for a Twilio WhatsApp number (~$1.15/month)
- Or apply for WhatsApp Business with your own number

---

### Option B: Meta Cloud API (Official)

#### Step 1: Create Meta Business Account

1. Go to **developers.facebook.com** → Create App
2. Choose **Business** → enter app details
3. Add **WhatsApp** product → click **Set Up**

#### Step 2: Get Credentials

In Meta Developer Console:
1. WhatsApp → **API Setup**
2. Copy the **Phone Number ID** (a long number like `104952272328432`)
3. Generate a **System User Access Token**:
   - Business Settings → System Users → Add
   - Assign WhatsApp permission → Generate Token
   - Copy the token (it's permanent if you use System User)

#### Step 3: Add Test Number

1. In WhatsApp → API Setup → **To** field
2. Click **Add phone number** → enter your WhatsApp number with country code
3. Enter the verification code sent to your WhatsApp

#### Step 4: Configure in Alchemy

1. Notifications → + Add Channel → WhatsApp
2. Fill in:
   - **API Provider:** `meta`
   - **Your WhatsApp Number:** `+919876543210`
   - **Meta Access Token:** `EAAxxxxxxx...`
   - **Meta Phone Number ID:** `104952272328432`
3. Click **Test Connection**

#### Test via curl
```bash
PHONE_NUMBER_ID="104952272328432"
ACCESS_TOKEN="EAAxxxxxxxxxxxxxxx"
TO_NUMBER="919876543210"   # No + for Meta

curl -X POST "https://graph.facebook.com/v19.0/$PHONE_NUMBER_ID/messages" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "messaging_product": "whatsapp",
    "to": "'"$TO_NUMBER"'",
    "type": "text",
    "text": {"body": "🔮 Alchemy WhatsApp test!"}
  }'
```

---

## 4. Environment Variables Reference

Add all configured credentials to `/opt/alchemy/.env.production`:

```env
# ── Gmail (Email OTP + alerts) ────────────────────────────────────
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your.email@gmail.com
SMTP_PASSWORD=abcdefghijklmnop     # 16-char App Password (no spaces)
SMTP_FROM=your.email@gmail.com

# ── Telegram (optional — configured via Notifications UI) ─────────
# No env vars needed — configured per-user in the Notifications page

# ── WhatsApp (optional — configured via Notifications UI) ─────────
# No env vars needed — configured per-user in the Notifications page

# ── Domain (for notification links) ──────────────────────────────
DOMAIN=akilamirthya.in
```

After editing:
```bash
cd /opt/alchemy && alchemy-update
```

---

## 5. Alert Rules Configuration

Once channels are connected, set up rules in **Notifications → Rules**:

| Event | Recommended Channel | When to Alert |
|-------|--------------------|--------------| 
| Signal Generated | Telegram | Always |
| Order Filled | Telegram + WhatsApp | Always |
| Emergency Stop | Telegram + WhatsApp | Always (critical) |
| High Risk Event | Telegram | Risk score > 60 |
| Portfolio P&L Alert | Telegram | Daily at market close |
| System Error | Email | Always |
| Login from new IP | Email | Always |

---

## 6. Quick Verification Checklist

Run all three in sequence to verify setup:

```bash
# 1. Test Gmail
docker exec alchemy-app-1 python3 -c "
from alchemy.notifications.email_service import send_email
result = send_email('admin@alchemy.in', 'Alchemy Test', '<b>Gmail works!</b>', 'Gmail works!')
print('Gmail OK' if result else 'Gmail FAILED — check SMTP_USER/SMTP_PASSWORD')
"

# 2. Test Telegram (replace BOT_TOKEN and CHAT_ID)
curl -s "https://api.telegram.org/botBOT_TOKEN/sendMessage" \
  -d "chat_id=CHAT_ID&text=🔮+Alchemy+Telegram+test"

# 3. Test WhatsApp (Twilio)
curl -X POST "https://api.twilio.com/2010-04-01/Accounts/SID/Messages.json" \
  -u "SID:TOKEN" \
  --data-urlencode "From=whatsapp:+14155238886" \
  --data-urlencode "To=whatsapp:+919876543210" \
  --data-urlencode "Body=🔮 Alchemy WhatsApp test"
```

---

## 7. Cost Reference

| Service | Free Tier | Paid |
|---------|-----------|------|
| Gmail SMTP | Free (500 emails/day) | Google Workspace $6/mo for custom domain |
| Telegram Bot | **Always free** | Free forever |
| Twilio WhatsApp Sandbox | Free (test only) | ~$0.005/message production |
| Meta WhatsApp Cloud | 1,000 free msgs/month | $0.005–$0.09/msg by country |
| Twilio SMS (backup) | $15 trial credit | ~$0.0075/SMS India |

**Recommendation:** Use Telegram for all trade alerts (free, instant, rich formatting). Use Gmail for OTP only. WhatsApp optional for critical alerts only.

