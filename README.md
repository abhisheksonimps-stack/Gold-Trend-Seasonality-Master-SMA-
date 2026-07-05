# Gold Telegram Signal Bot

Strategy name: **Gold Trend Seasonality Master**

Ye repo aapki Gold strategy ko daily run karke Telegram par signal bhejne ke liye hai.

## Strategy

**Name:** Gold Trend Seasonality Master

```text
LONG if SMA100 > SMA250
OR month is November, December, January, or February

Otherwise CASH
```

Signal daily close/snapshot price ke basis par calculate hota hai.

## Signal ka meaning

```text
LONG = Gold buy/hold position rakho
CASH = Position exit karo ya trade mat lo
```

CASH ka matlab short-sell nahi hai. Is strategy me sirf LONG ya no-position logic hai.

## Files

```text
strategy_bot.py                         Main Python script
requirements.txt                        Python dependencies
.env.example                            Environment variable sample
data/gold_daily.csv                     Historical daily gold data up to 03-Jul-2026
.github/workflows/daily-gold-signal.yml GitHub Actions scheduler
logs/latest_signal.json                 Last signal log, auto-created after first run
```

## Telegram setup

### 1. Telegram bot token lo

1. Telegram me `@BotFather` open karo.
2. `/newbot` command bhejo.
3. Bot ka name aur username set karo.
4. BotFather aapko `TELEGRAM_BOT_TOKEN` dega.

### 2. Chat ID lo

1. Apne new bot ko Telegram par message bhejo, example: `hi`.
2. Browser me ye URL open karo:

```text
https://api.telegram.org/botYOUR_BOT_TOKEN/getUpdates
```

3. Response me `chat` ke andar `id` dikhega. Wahi `TELEGRAM_CHAT_ID` hai.

## GitHub setup

1. GitHub par new repo banao.
2. Is folder ki files repo me upload karo.
3. GitHub repo me jao: **Settings → Secrets and variables → Actions**.
4. **Secrets** me ye add karo:

```text
TELEGRAM_BOT_TOKEN
TELEGRAM_CHAT_ID
```

5. Optional **Variables** me ye add kar sakte ho:

```text
API_URL=https://igold24.com/api/cached-gold-prices.json
PRICE_FIELD=world_ounce_usd
USER_TZ=Asia/Kolkata
STRATEGY_NAME=Gold Trend Seasonality Master
ALERT_MODE=always
```

`ALERT_MODE=always` ka matlab har run par Telegram message aayega.

`ALERT_MODE=change` ka matlab message sirf tab aayega jab signal LONG se CASH ya CASH se LONG change ho.

## Run kaise hoga

GitHub Actions workflow automatically Monday-Friday run hoga:

```text
23:30 UTC = next day 05:00 IST
```

Manual test ke liye:

1. GitHub repo me **Actions** tab open karo.
2. **Daily Gold Telegram Signal** workflow select karo.
3. **Run workflow** click karo.

## Local test

```bash
pip install -r requirements.txt
python strategy_bot.py --skip-fetch --no-send
```

Live API fetch test without Telegram:

```bash
python strategy_bot.py --no-send
```

Telegram send test:

```bash
export TELEGRAM_BOT_TOKEN="your_token"
export TELEGRAM_CHAT_ID="your_chat_id"
python strategy_bot.py
```

Windows PowerShell:

```powershell
$env:TELEGRAM_BOT_TOKEN="your_token"
$env:TELEGRAM_CHAT_ID="your_chat_id"
python strategy_bot.py
```

## API

Default API:

```text
https://igold24.com/api/cached-gold-prices.json
```

Default price field:

```text
world_ounce_usd
```

## Important limitations

- Ye system trading advice nahi hai.
- API live spot snapshot deta hai, exact exchange close nahi.
- Daily close ka meaning schedule time par available API price hai.
- Futures, spread, slippage, lot size, margin aur broker execution alag ho sakte hain.
- Live use se pehle paper trading zaroor karo.
