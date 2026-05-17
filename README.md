# USDT Market Scanner Bot Demo

Python demo application for scanning USDT trading pairs.

## What it does

- Fetches live 24h ticker data from the public Binance API.
- Filters only symbols ending in `USDT`.
- Scores each pair by liquidity, 24h momentum, volatility, and trade activity.
- Shows scanner signals: `LONG WATCH`, `SCALP WATCH`, `NEUTRAL`, and `AVOID`.
- Sends the strongest scanner alert to WhatsApp through Twilio WhatsApp API.
- Formats WhatsApp alerts with amount, profit percent, total, and buy/sell action.
- Runs as a local web dashboard.

This project is a scanner demo only. It does not place orders, store exchange API keys, or provide financial advice.

## WhatsApp setup

The app works in demo mode without credentials. To send a real WhatsApp message, set these environment variables before running:

```bash
export TWILIO_ACCOUNT_SID="your_twilio_account_sid"
export TWILIO_AUTH_TOKEN="your_twilio_auth_token"
export TWILIO_WHATSAPP_FROM="whatsapp:+14155238886"
export ALERT_WHATSAPP_TO="whatsapp:+12345678900"
```

`TWILIO_WHATSAPP_FROM` can be the Twilio WhatsApp Sandbox sender or an approved WhatsApp Business sender.

Example WhatsApp alert:

```text
USDT token: BTCUSDT

Amount: 100.00$
Winst: 20.00$
Procent: 20%

Totaal: 120.00$

Buy/sell: BUY
```

## Run

```bash
python3 app.py
```

Then open:

```text
http://127.0.0.1:8000
```

## Open on iPhone

1. Connect the iPhone and Mac to the same Wi-Fi network.
2. Run the app on the Mac:

```bash
python3 app.py
```

3. Open the iPhone URL printed in the terminal, for example:

```text
http://192.168.0.146:8000
```

If macOS asks about incoming network connections, allow Python.

## Public link deployment

For other people to open the project from any phone or computer, the app must run on a public hosting service. Local links like `127.0.0.1` or `192.168...` only work on your own computer or Wi-Fi.

This project is ready for deployment with:

- `Procfile` for simple Python web hosting.
- `render.yaml` for Render Blueprint deployment.
- `Dockerfile` for Docker-based hosting.
- `/health` endpoint for platform health checks.

### Deploy on Render

1. Push this folder to a GitHub repository.
2. In Render, create a new **Web Service** from that repository.
3. Use:

```text
Build Command: empty
Start Command: python3 app.py
Health Check Path: /health
```

4. Add environment variables if you want real WhatsApp sending:

```text
TWILIO_ACCOUNT_SID
TWILIO_AUTH_TOKEN
TWILIO_WHATSAPP_FROM
ALERT_WHATSAPP_TO
```

5. After deploy, Render gives a public URL like:

```text
https://usdt-whatsapp-scanner.onrender.com
```

That is the link you can send to other people.
