from __future__ import annotations

import base64
import json
import os
import socket
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse


BINANCE_24H_TICKER_URL = "https://api.binance.com/api/v3/ticker/24hr"
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))
DEFAULT_TWILIO_WHATSAPP_FROM = "whatsapp:+14155238886"


@dataclass
class TokenSignal:
    symbol: str
    price: float
    change_percent: float
    quote_volume: float
    trades: int
    high: float
    low: float
    volatility: float
    score: int
    signal: str
    reason: str


def fetch_json(url: str, timeout: int = 10) -> Any:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "python-usdt-scanner-demo/1.0",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def get_lan_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect(("8.8.8.8", 80))
            return probe.getsockname()[0]
    except OSError:
        return "127.0.0.1"


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def make_signal(row: dict[str, Any]) -> TokenSignal | None:
    symbol = str(row.get("symbol", ""))
    if not symbol.endswith("USDT"):
        return None

    price = safe_float(row.get("lastPrice"))
    change_percent = safe_float(row.get("priceChangePercent"))
    quote_volume = safe_float(row.get("quoteVolume"))
    trades = safe_int(row.get("count"))
    high = safe_float(row.get("highPrice"))
    low = safe_float(row.get("lowPrice"))

    if price <= 0 or high <= 0 or low <= 0:
        return None

    volatility = ((high - low) / price) * 100

    score = 0
    reasons: list[str] = []

    if quote_volume >= 100_000_000:
        score += 35
        reasons.append("high liquidity")
    elif quote_volume >= 30_000_000:
        score += 22
        reasons.append("solid liquidity")
    elif quote_volume >= 5_000_000:
        score += 10
        reasons.append("moderate liquidity")

    if 2 <= change_percent <= 12:
        score += 30
        reasons.append("healthy momentum")
    elif 0.5 <= change_percent < 2:
        score += 15
        reasons.append("early momentum")
    elif change_percent > 18:
        score -= 20
        reasons.append("overextended move")
    elif change_percent < -6:
        score -= 18
        reasons.append("heavy sell pressure")

    if 2 <= volatility <= 12:
        score += 20
        reasons.append("tradable volatility")
    elif volatility > 20:
        score -= 10
        reasons.append("very high volatility")

    if trades >= 200_000:
        score += 15
        reasons.append("strong activity")
    elif trades >= 50_000:
        score += 8
        reasons.append("active market")

    score = max(0, min(100, score))

    if score >= 75:
        signal = "LONG WATCH"
    elif score >= 55:
        signal = "SCALP WATCH"
    elif score >= 35:
        signal = "NEUTRAL"
    else:
        signal = "AVOID"

    return TokenSignal(
        symbol=symbol,
        price=price,
        change_percent=change_percent,
        quote_volume=quote_volume,
        trades=trades,
        high=high,
        low=low,
        volatility=volatility,
        score=score,
        signal=signal,
        reason=", ".join(reasons) or "low scanner score",
    )


def scan_market(
    min_volume: float = 5_000_000,
    min_score: int = 0,
    limit: int = 40,
    sort_by: str = "score",
) -> dict[str, Any]:
    started_at = time.time()
    rows = fetch_json(BINANCE_24H_TICKER_URL)
    signals = [signal for row in rows if (signal := make_signal(row))]
    signals = [
        signal
        for signal in signals
        if signal.quote_volume >= min_volume and signal.score >= min_score
    ]

    sort_keys = {
        "score": lambda item: item.score,
        "volume": lambda item: item.quote_volume,
        "change": lambda item: item.change_percent,
        "volatility": lambda item: item.volatility,
        "trades": lambda item: item.trades,
    }
    signals.sort(key=sort_keys.get(sort_by, sort_keys["score"]), reverse=True)
    limited = signals[: max(1, min(limit, 100))]

    return {
        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "scan_ms": round((time.time() - started_at) * 1000),
        "count": len(limited),
        "items": [asdict(item) for item in limited],
    }


def format_volume(value: float) -> str:
    if value >= 1_000_000_000:
        return f"${value / 1_000_000_000:.2f}B"
    if value >= 1_000_000:
        return f"${value / 1_000_000:.1f}M"
    if value >= 1_000:
        return f"${value / 1_000:.1f}K"
    return f"${value:.0f}"


def format_price(value: float) -> str:
    if value >= 100:
        return f"{value:.2f}"
    if value >= 1:
        return f"{value:.4f}"
    return f"{value:.6f}"


def format_usd(value: float) -> str:
    return f"{value:.2f}$"


def normalize_whatsapp_number(value: str) -> str:
    value = value.strip()
    if not value:
        return ""
    if value.startswith("whatsapp:"):
        return value
    return f"whatsapp:{value}"


def build_alert_message(
    signal: dict[str, Any],
    amount: float,
    percent: float,
    trade_action: str,
) -> str:
    action = trade_action.upper()
    if action not in {"BUY", "SELL"}:
        action = "BUY" if signal["change_percent"] >= 0 else "SELL"

    profit = amount * (percent / 100)
    total = amount + profit

    return "\n".join(
        [
            f"USDT token: {signal['symbol']}",
            "",
            f"Amount: {format_usd(amount)}",
            f"Winst: {format_usd(profit)}",
            f"Procent: {percent:.0f}%",
            "",
            f"Totaal: {format_usd(total)}",
            "",
            f"Buy/sell: {action}",
        ]
    )


def send_whatsapp_alert(message: str) -> dict[str, Any]:
    account_sid = os.getenv("TWILIO_ACCOUNT_SID", "").strip()
    auth_token = os.getenv("TWILIO_AUTH_TOKEN", "").strip()
    from_number = normalize_whatsapp_number(
        os.getenv("TWILIO_WHATSAPP_FROM", DEFAULT_TWILIO_WHATSAPP_FROM)
    )
    to_number = normalize_whatsapp_number(
        os.getenv("ALERT_WHATSAPP_TO", os.getenv("WHATSAPP_TO", ""))
    )

    missing = [
        name
        for name, value in {
            "TWILIO_ACCOUNT_SID": account_sid,
            "TWILIO_AUTH_TOKEN": auth_token,
            "ALERT_WHATSAPP_TO": to_number,
        }.items()
        if not value
    ]
    if missing:
        return {
            "sent": False,
            "mode": "demo",
            "configured": False,
            "missing": missing,
            "message": message,
        }

    url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"
    data = urlencode(
        {
            "From": from_number,
            "To": to_number,
            "Body": message,
        }
    ).encode("utf-8")
    auth = base64.b64encode(f"{account_sid}:{auth_token}".encode("utf-8")).decode(
        "ascii"
    )
    request = urllib.request.Request(
        url,
        data=data,
        headers={
            "Authorization": f"Basic {auth}",
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=12) as response:
            payload = json.loads(response.read().decode("utf-8"))
            return {
                "sent": True,
                "mode": "live",
                "configured": True,
                "message": message,
                "twilio_sid": payload.get("sid"),
                "twilio_status": payload.get("status"),
                "to": to_number,
            }
    except urllib.error.HTTPError as error:
        details = error.read().decode("utf-8", errors="replace")
        return {
            "sent": False,
            "mode": "live",
            "configured": True,
            "message": message,
            "error": f"Twilio request failed with HTTP {error.code}",
            "details": details,
        }
    except urllib.error.URLError as error:
        return {
            "sent": False,
            "mode": "live",
            "configured": True,
            "message": message,
            "error": f"Twilio request failed: {error.reason}",
        }


def create_alert(
    min_volume: float,
    threshold: int,
    amount: float,
    percent: float,
    trade_action: str,
) -> dict[str, Any]:
    scan = scan_market(
        min_volume=min_volume,
        min_score=threshold,
        limit=10,
        sort_by="score",
    )
    if not scan["items"]:
        return {
            "sent": False,
            "mode": "scanner",
            "error": "No USDT pair matched the alert threshold.",
            "threshold": threshold,
        }

    signal = scan["items"][0]
    message = build_alert_message(signal, amount, percent, trade_action)
    delivery = send_whatsapp_alert(message)
    return {
        **delivery,
        "token": signal,
        "threshold": threshold,
        "amount": amount,
        "percent": percent,
        "trade_action": trade_action,
        "updated_at": scan["updated_at"],
    }


def render_html() -> bytes:
    html = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>USDT Market Scanner Bot Demo</title>
  <style>
    :root {
      color-scheme: dark;
      --bg: #0b0f14;
      --panel: #111821;
      --panel-2: #151f2b;
      --line: #243243;
      --text: #e8eef6;
      --muted: #91a1b4;
      --green: #20d187;
      --yellow: #f3c969;
      --red: #f05f75;
      --blue: #65a8ff;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: var(--bg);
      color: var(--text);
    }
    main {
      width: min(1180px, calc(100% - 32px));
      margin: 0 auto;
      padding: 28px 0 40px;
    }
    header {
      display: flex;
      justify-content: space-between;
      gap: 16px;
      align-items: flex-end;
      margin-bottom: 20px;
    }
    h1 {
      margin: 0 0 6px;
      font-size: clamp(28px, 4vw, 46px);
      line-height: 1.05;
      letter-spacing: 0;
    }
    .subtitle {
      margin: 0;
      color: var(--muted);
      max-width: 720px;
      line-height: 1.5;
    }
    .status {
      min-width: 210px;
      padding: 12px 14px;
      border: 1px solid var(--line);
      background: var(--panel);
      border-radius: 8px;
      color: var(--muted);
      font-size: 14px;
    }
    .controls {
      display: grid;
      grid-template-columns: repeat(5, minmax(130px, 1fr));
      gap: 10px;
      margin: 18px 0;
      padding: 14px;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
    }
    label {
      display: grid;
      gap: 6px;
      color: var(--muted);
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0;
    }
    input, select, button {
      height: 38px;
      border-radius: 6px;
      border: 1px solid var(--line);
      background: var(--panel-2);
      color: var(--text);
      padding: 0 10px;
      font: inherit;
    }
    button {
      cursor: pointer;
      background: var(--blue);
      border-color: var(--blue);
      color: #06111f;
      font-weight: 700;
      align-self: end;
    }
    .link-button {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-height: 38px;
      border-radius: 6px;
      border: 1px solid var(--blue);
      background: var(--blue);
      color: #06111f;
      padding: 0 12px;
      text-decoration: none;
      font-weight: 700;
      text-align: center;
    }
    .alert-panel {
      display: grid;
      gap: 14px;
      margin-bottom: 16px;
      padding: 16px;
      border: 1px solid var(--line);
      background: var(--panel);
      border-radius: 8px;
    }
    .alert-header {
      display: flex;
      align-items: start;
      justify-content: space-between;
      gap: 16px;
    }
    .alert-header h2 {
      margin: 0 0 4px;
      font-size: 20px;
      letter-spacing: 0;
    }
    .alert-header p {
      margin: 0;
      color: var(--muted);
      line-height: 1.45;
    }
    .alert-mode {
      color: var(--green);
      font-size: 13px;
      white-space: nowrap;
    }
    .alert-actions {
      display: grid;
      grid-template-columns: repeat(4, minmax(130px, 1fr)) minmax(180px, 240px);
      gap: 10px;
      align-items: end;
    }
    .share-actions {
      display: grid;
      grid-template-columns: minmax(220px, 1fr) minmax(170px, 210px);
      gap: 10px;
      align-items: end;
    }
    .alert-output {
      min-height: 112px;
      margin: 0;
      padding: 12px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #0c1219;
      color: var(--muted);
      white-space: pre-wrap;
      overflow-wrap: anywhere;
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      font-size: 13px;
      line-height: 1.5;
    }
    .alert-output.live { color: var(--green); }
    .alert-output.demo { color: var(--yellow); }
    .alert-output.failed { color: var(--red); }
    .metrics {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 10px;
      margin-bottom: 16px;
    }
    .metric {
      border: 1px solid var(--line);
      background: var(--panel);
      border-radius: 8px;
      padding: 14px;
    }
    .metric span {
      display: block;
      color: var(--muted);
      font-size: 13px;
      margin-bottom: 6px;
    }
    .metric strong {
      font-size: 22px;
    }
    .table-wrap {
      border: 1px solid var(--line);
      border-radius: 8px;
      overflow: hidden;
      background: var(--panel);
    }
    table {
      width: 100%;
      border-collapse: collapse;
    }
    th, td {
      padding: 12px 14px;
      border-bottom: 1px solid var(--line);
      text-align: left;
      white-space: nowrap;
      font-size: 14px;
    }
    th {
      color: var(--muted);
      font-size: 12px;
      text-transform: uppercase;
      background: #0f151d;
      letter-spacing: 0;
    }
    tr:last-child td { border-bottom: 0; }
    .symbol { font-weight: 800; }
    .positive { color: var(--green); }
    .negative { color: var(--red); }
    .badge {
      display: inline-flex;
      align-items: center;
      min-height: 26px;
      padding: 0 9px;
      border-radius: 5px;
      font-weight: 800;
      font-size: 12px;
      color: #071017;
    }
    .long { background: var(--green); }
    .scalp { background: var(--yellow); }
    .neutral { background: var(--blue); }
    .avoid { background: var(--red); }
    .reason {
      white-space: normal;
      color: var(--muted);
      min-width: 210px;
      max-width: 340px;
    }
    .error {
      padding: 16px;
      color: var(--red);
    }
    footer {
      color: var(--muted);
      font-size: 13px;
      margin-top: 16px;
      line-height: 1.5;
    }
    @media (max-width: 860px) {
      header { display: grid; }
      .status { min-width: 0; }
      .controls { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .alert-header { display: grid; }
      .alert-actions { grid-template-columns: 1fr; }
      .share-actions { grid-template-columns: 1fr; }
      .alert-mode { white-space: normal; }
      .table-wrap { overflow-x: auto; }
    }
  </style>
</head>
<body>
  <main>
    <header>
      <div>
        <h1>USDT Market Scanner Bot</h1>
        <p class="subtitle">Python demo scanner for USDT trading pairs. It reads live Binance market data, ranks tokens by volume, momentum, volatility, and activity, then sends the best scanner alert to WhatsApp.</p>
      </div>
      <div class="status" id="status">Loading live market data...</div>
    </header>

    <section class="controls">
      <label>Min volume
        <input id="minVolume" type="number" value="5000000" min="0" step="1000000">
      </label>
      <label>Min score
        <input id="minScore" type="number" value="0" min="0" max="100" step="5">
      </label>
      <label>Limit
        <input id="limit" type="number" value="40" min="5" max="100" step="5">
      </label>
      <label>Sort by
        <select id="sortBy">
          <option value="score">Scanner score</option>
          <option value="volume">Volume</option>
          <option value="change">24h change</option>
          <option value="volatility">Volatility</option>
          <option value="trades">Trades</option>
        </select>
      </label>
      <button id="scanButton">Scan market</button>
    </section>

    <section class="metrics">
      <div class="metric"><span>Pairs shown</span><strong id="pairs">-</strong></div>
      <div class="metric"><span>Best signal</span><strong id="bestSignal">-</strong></div>
      <div class="metric"><span>Top volume</span><strong id="topVolume">-</strong></div>
      <div class="metric"><span>Scan speed</span><strong id="scanMs">-</strong></div>
    </section>

    <section class="alert-panel">
      <div class="alert-header">
        <div>
          <h2>WhatsApp Alert</h2>
          <p>The bot scans live USDT pairs, selects the strongest token above the threshold, and sends the alert message to WhatsApp.</p>
        </div>
        <span class="alert-mode">Twilio WhatsApp API</span>
      </div>
      <div class="alert-actions">
        <label>Alert threshold
          <input id="alertThreshold" type="number" value="55" min="0" max="100" step="5">
        </label>
        <label>Amount
          <input id="tradeAmount" type="number" value="100" min="1" step="10">
        </label>
        <label>Procent
          <input id="tradePercent" type="number" value="20" min="0" step="1">
        </label>
        <label>Buy/sell
          <select id="tradeAction">
            <option value="BUY">BUY</option>
            <option value="SELL">SELL</option>
          </select>
        </label>
        <button id="sendAlertButton">Send WhatsApp alert</button>
      </div>
      <pre class="alert-output" id="alertOutput">Waiting for scanner signal...</pre>
    </section>

    <section class="alert-panel">
      <div class="alert-header">
        <div>
          <h2>Share Demo Link</h2>
          <p>Send this public demo link through WhatsApp so clients can open the bot from any phone.</p>
        </div>
        <span class="alert-mode">Public Render URL</span>
      </div>
      <div class="share-actions">
        <label>Demo link
          <input id="demoLink" type="text" readonly value="">
        </label>
        <a class="link-button" id="whatsappShareLink" target="_blank" rel="noopener">Share on WhatsApp</a>
      </div>
    </section>

    <section class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Pair</th>
            <th>Price</th>
            <th>24h</th>
            <th>Volume</th>
            <th>Trades</th>
            <th>Volatility</th>
            <th>Score</th>
            <th>Signal</th>
            <th>Reason</th>
          </tr>
        </thead>
        <tbody id="rows"></tbody>
      </table>
    </section>

    <footer>This demo is a market scanner only. It does not place orders, store API keys, or provide financial advice.</footer>
  </main>
  <script>
    const rows = document.querySelector("#rows");
    const statusEl = document.querySelector("#status");
    const alertOutput = document.querySelector("#alertOutput");
    const fields = ["minVolume", "minScore", "limit", "sortBy"];
    const demoUrl = window.location.origin;
    const shareText = encodeURIComponent(`USDT WhatsApp Scanner Bot Demo: ${demoUrl}`);
    document.querySelector("#demoLink").value = demoUrl;
    document.querySelector("#whatsappShareLink").href = `https://wa.me/?text=${shareText}`;

    const money = (value) => {
      if (value >= 1_000_000_000) return `$${(value / 1_000_000_000).toFixed(2)}B`;
      if (value >= 1_000_000) return `$${(value / 1_000_000).toFixed(1)}M`;
      if (value >= 1_000) return `$${(value / 1_000).toFixed(1)}K`;
      return `$${value.toFixed(0)}`;
    };

    const price = (value) => {
      if (value >= 100) return value.toFixed(2);
      if (value >= 1) return value.toFixed(4);
      return value.toPrecision(5);
    };

    const badgeClass = (signal) => {
      if (signal === "LONG WATCH") return "long";
      if (signal === "SCALP WATCH") return "scalp";
      if (signal === "NEUTRAL") return "neutral";
      return "avoid";
    };

    async function scan() {
      const params = new URLSearchParams({
        min_volume: document.querySelector("#minVolume").value,
        min_score: document.querySelector("#minScore").value,
        limit: document.querySelector("#limit").value,
        sort_by: document.querySelector("#sortBy").value
      });

      statusEl.textContent = "Scanning Binance USDT pairs...";
      rows.innerHTML = "";

      try {
        const response = await fetch(`/api/scan?${params}`);
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || "Scan failed");

        document.querySelector("#pairs").textContent = data.count;
        document.querySelector("#bestSignal").textContent = data.items[0]?.signal || "-";
        document.querySelector("#topVolume").textContent = data.items[0] ? money(Math.max(...data.items.map((item) => item.quote_volume))) : "-";
        document.querySelector("#scanMs").textContent = `${data.scan_ms}ms`;
        statusEl.textContent = `Updated ${data.updated_at}`;

        rows.innerHTML = data.items.map((item) => `
          <tr>
            <td class="symbol">${item.symbol}</td>
            <td>${price(item.price)}</td>
            <td class="${item.change_percent >= 0 ? "positive" : "negative"}">${item.change_percent.toFixed(2)}%</td>
            <td>${money(item.quote_volume)}</td>
            <td>${item.trades.toLocaleString()}</td>
            <td>${item.volatility.toFixed(2)}%</td>
            <td>${item.score}/100</td>
            <td><span class="badge ${badgeClass(item.signal)}">${item.signal}</span></td>
            <td class="reason">${item.reason}</td>
          </tr>
        `).join("");
      } catch (error) {
        statusEl.textContent = "Scanner error";
        rows.innerHTML = `<tr><td class="error" colspan="9">${error.message}</td></tr>`;
      }
    }

    async function sendAlert() {
      alertOutput.className = "alert-output";
      alertOutput.textContent = "Scanning and preparing WhatsApp alert...";

      try {
        const response = await fetch("/api/alert", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            min_volume: document.querySelector("#minVolume").value,
            threshold: document.querySelector("#alertThreshold").value,
            amount: document.querySelector("#tradeAmount").value,
            percent: document.querySelector("#tradePercent").value,
            trade_action: document.querySelector("#tradeAction").value
          })
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || "Alert failed");

        if (data.mode === "demo") {
          alertOutput.className = "alert-output demo";
          alertOutput.textContent = [
            "Demo mode: WhatsApp credentials are not configured yet.",
            `Missing: ${data.missing.join(", ")}`,
            "",
            data.message
          ].join("\\n");
          return;
        }

        if (data.sent) {
          alertOutput.className = "alert-output live";
          alertOutput.textContent = [
            `WhatsApp alert sent to ${data.to}`,
            `Twilio status: ${data.twilio_status || "queued"}`,
            `Message SID: ${data.twilio_sid || "-"}`,
            "",
            data.message
          ].join("\\n");
          return;
        }

        throw new Error(data.error || "WhatsApp alert was not sent");
      } catch (error) {
        alertOutput.className = "alert-output failed";
        alertOutput.textContent = error.message;
      }
    }

    document.querySelector("#scanButton").addEventListener("click", scan);
    document.querySelector("#sendAlertButton").addEventListener("click", sendAlert);
    fields.forEach((id) => document.querySelector(`#${id}`).addEventListener("change", scan));
    scan();
    setInterval(scan, 30000);
  </script>
</body>
</html>
"""
    return html.encode("utf-8")


class ScannerHandler(BaseHTTPRequestHandler):
    def do_HEAD(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path in {"/", "/health"}:
            body = b"ok" if parsed.path == "/health" else render_html()
            self.send_response(200)
            content_type = (
                "text/plain; charset=utf-8"
                if parsed.path == "/health"
                else "text/html; charset=utf-8"
            )
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            return

        self.send_response(404)
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(render_html())
            return

        if parsed.path == "/health":
            self.send_json(200, {"status": "ok"})
            return

        if parsed.path == "/api/scan":
            params = parse_qs(parsed.query)
            try:
                min_volume = safe_float(params.get("min_volume", ["5000000"])[0])
                min_score = safe_int(params.get("min_score", ["0"])[0])
                limit = safe_int(params.get("limit", ["40"])[0])
                sort_by = params.get("sort_by", ["score"])[0]
                payload = scan_market(min_volume, min_score, limit, sort_by)
                self.send_json(200, payload)
            except (urllib.error.URLError, TimeoutError) as error:
                self.send_json(502, {"error": f"Market data request failed: {error}"})
            except Exception as error:
                self.send_json(500, {"error": f"Scanner failed: {error}"})
            return

        self.send_response(404)
        self.end_headers()

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/alert":
            try:
                body = self.read_json_body()
                min_volume = safe_float(body.get("min_volume"), 5_000_000)
                threshold = safe_int(body.get("threshold"), 55)
                amount = safe_float(body.get("amount"), 100)
                percent = safe_float(body.get("percent"), 20)
                trade_action = str(body.get("trade_action", "BUY"))
                payload = create_alert(
                    min_volume=min_volume,
                    threshold=threshold,
                    amount=amount,
                    percent=percent,
                    trade_action=trade_action,
                )

                status = 200
                if payload.get("mode") == "scanner":
                    status = 404
                elif payload.get("configured") and not payload.get("sent"):
                    status = 502
                self.send_json(status, payload)
            except (urllib.error.URLError, TimeoutError) as error:
                self.send_json(502, {"error": f"Market data request failed: {error}"})
            except Exception as error:
                self.send_json(500, {"error": f"Alert failed: {error}"})
            return

        self.send_response(404)
        self.end_headers()

    def read_json_body(self) -> dict[str, Any]:
        length = safe_int(self.headers.get("Content-Length"), 0)
        if length <= 0:
            return {}
        raw_body = self.rfile.read(length).decode("utf-8")
        payload = json.loads(raw_body)
        if isinstance(payload, dict):
            return payload
        return {}

    def send_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:
        return


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), ScannerHandler)
    lan_ip = get_lan_ip()
    print(f"USDT scanner running locally at http://127.0.0.1:{PORT}")
    print(f"Open from iPhone on the same Wi-Fi: http://{lan_ip}:{PORT}")
    print("On hosting, use the public URL provided by the platform.")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nScanner stopped.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
