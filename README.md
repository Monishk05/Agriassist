# AgriAssist - AI WhatsApp Bot for Tamil Nadu Farmers

**Diagnose crop diseases in Tamil + Voice reply in 10 seconds**  
**Free, 24/7, runs on Railway**

---

## Features

- Send crop photo → Get **Tamil diagnosis + voice MP3**
- AI powered by **GPT-4o Vision**
- Voice reply using **Google TTS**
- Rate limit: **1 photo every 2 minutes**
- Dashboard: View all cases
- Deployed on **Railway** (no ngrok, no PC needed)

---

## Live Demo (After Deploy)

**Webhook URL**:  
`https://agriassist-production.up.railway.app/whatsapp`

**Dashboard**:  
`https://agriassist-production.up.railway.app/dashboard`

---

## How to Use (For Farmers)

1. **Join the bot**:
2. **Send a crop photo**
3. **Get reply in 10 seconds**:

> ```
> நோய்: ஆர்மிலேரியா இலை பிளைட்
> ஆங்கிலம்: Leaf Blight
> நம்பிக்கை: 85%
> சிகிச்சை: 1. 50 கிராம் கார்பன்டாஸிம்..., 2. பாதிக்கப்பட்ட இலைகளை அகற்றவும்.
> செலவு: ₹150
> [Voice Message]
> ```

---

## Deploy to Railway (1-Click)

1. Go to: [https://railway.app](https://railway.app)
2. **Login with GitHub**
3. **New Project** → **Deploy from GitHub**
4. Search: `AgriAssist-Official/AgriAssist`
5. Click **Deploy**

---

## Environment Variables (Add in Railway)

| Key | Value |
|-----|-------|
| `OPENAI_API_KEY` | `sk-...` |
| `TWILIO_ACCOUNT_SID` | `AC...` |
| `TWILIO_AUTH_TOKEN` | `your_auth_token` |
| `TWILIO_WHATSAPP_NUMBER` | `whatsapp:+14155238886` |

---

## Set Webhook in Twilio (ONE TIME)

1. [https://console.twilio.com](https://console.twilio.com)
2. **Messaging → Try it out → WhatsApp**
3. **"WHEN A MESSAGE COMES IN"** → Paste:

4. **Method**: `POST`  
5. **SAVE**

---

## Local Development

```bash
# Clone
git clone https://github.com/AgriAssist-Official/AgriAssist.git
cd AgriAssist

# Install
pip install -r requirements.txt

# Run
python main.py
