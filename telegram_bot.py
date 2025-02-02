import os
import sys
from dotenv import load_dotenv

import logging
import requests
import pandas as pd
import asyncio
from telegram import Update
from telegram.ext import Application, CommandHandler, CallbackContext

from scheduler import scheduler
from resources import conn

load_dotenv()

# Enable logging
logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# API key CoinMarketCap:
CMC_API_KEY = os.environ.get("CMC_API_KEY")
CMC_URL = os.environ.get("CMC_URL")

# Get the data from web:
def get_crypto_data():
    headers = {"X-CMC_PRO_API_KEY": CMC_API_KEY}
    params = {"start": 1, "limit": 100, "convert": "USD"}
    response = requests.get(CMC_URL, headers=headers, params=params)
    
    if response.status_code != 200:
        logger.error(f"API request failed: {response.status_code} - {response.text}")
        return []
    
    try:
        data = response.json().get("data", [])
        return [{
            "symbol": coin["symbol"],
            "price": coin["quote"]["USD"]["price"],
            "percent_change_7d": coin["quote"]["USD"]["percent_change_7d"]
        } for coin in data]
    except (KeyError, TypeError, ValueError) as e:
        logger.error(f"Error processing API response: {e}")
        return []

def filter_coins(coins):
    return [coin for coin in coins if coin["percent_change_7d"] < -10]


c = conn.cursor()
c.execute(
    '''CREATE TABLE IF NOT EXISTS crypto_data
             (symbol TEXT,
            price REAL,
            percent_change_7d REAL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)
             ''')
conn.commit()

c.execute(
    '''CREATE TABLE IF NOT EXISTS tracked_coins
            (symbol TEXT PRIMARY KEY,
            added_at DATETIME DEFAULT CURRENT_TIMESTAMP)
            ''')
conn.commit()


# Store data in the database
def store_data(coins):
    with conn:
        c = conn.cursor()
        c.executemany("INSERT INTO crypto_data (symbol, price, percent_change_7d) VALUES (?, ?, ?)",
                      [(coin["symbol"], coin["price"], coin["percent_change_7d"]) for coin in coins])
        conn.commit()


# Telegram reply for start command
async def start(update: Update, context: CallbackContext):
    message = (
        "Welcome to the Crypto Bot! Here are the available commands:\n"
        "/forecast - Get coins with potential for growth\n"
        "/history - Get top results from forecast history\n"
        "/track - track the coins you choosed\n"
        "/stop_tracking - stop tracking the coin\n"
        "/stop_bot - stop bot and delete all from history"
    )
    await update.message.reply_text(message)

# Telegram reply for forecast command
async def forecast(update: Update, context: CallbackContext):
    print(f"Received message: {update.message.text}")
    coins = get_crypto_data()
    store_data(coins)
    filtered_coins = filter_coins(coins)
    message = "Coins with potential:\n" + "\n".join(
        [f"{coin['symbol']}: {coin['percent_change_7d']}% for the last 7 days" for coin in filtered_coins[:3]]
    )
    await update.message.reply_text(message if filtered_coins else "There are no coins with potential.")

async def history(update: Update, context: CallbackContext):
    print(f"Received message: {update.message.text}")
    with conn:
        c.execute("SELECT symbol, price, percent_change_7d, timestamp FROM crypto_data ORDER BY timestamp DESC LIMIT 10")
        rows = c.fetchall()
        
    if rows:
        message = "Top 10 recent records:\n" + "\n".join(
            [f"{row[0]}: ${row[1]:.2f}, {row[2]:.2f}% (as of {row[3]})" for row in rows]
        )
    else:
        message = "No data available."

    await update.message.reply_text(message)

async def track(update: Update, context: CallbackContext):
    symbols = context.args
    logger.info(f"Tracking started for: {', '.join(symbols)}")
    if not symbols:
        await update.message.reply_text("Usage: /track BTC ETH")
        return
    
    with conn:
        for symbol in symbols:
            conn.execute("INSERT OR IGNORE INTO tracked_coins (symbol) VALUES (?)", (symbol,))
    await update.message.reply_text(f"Tracking: {', '.join(symbols)}")

def send_alert(symbol, price):
    bot = Application.builder().token(os.environ.get("TELEGRAM_BOT_TOKEN")).build().bot
    bot.send_message(chat_id=os.environ.get("CHAT_ID"), text=f"⚠️ {symbol} dropped! Price: ${price:.2f}")

def check_tracked_prices():
    with conn:
        tracked_symbols = {t[0] for t in conn.execute("SELECT symbol FROM tracked_coins").fetchall()}
        if not tracked_symbols:
            return

        coins = get_crypto_data()
        for coin in coins:
            if coin["symbol"] in tracked_symbols:  # Faster lookup with a set
                last_price = conn.execute(
                    "SELECT price FROM crypto_data WHERE symbol=? ORDER BY timestamp DESC LIMIT 1",
                    (coin["symbol"],),
                ).fetchone()
                if last_price and coin["price"] < last_price[0] * 0.95:
                    logger.info(f"{coin['symbol']} dropped on 5%!")
                    send_alert(coin["symbol"], coin["price"])


async def stop_tracking(update: Update, context: CallbackContext):
    symbol = context.args[0] if context.args else None
    logger.info(f"Stopped tracking {symbol}")
    if not symbol:
        await update.message.reply_text(f"Usage: /stop_tracking {symbol}")
        return

    with conn:
        conn.execute("DELETE FROM tracked_coins WHERE symbol=?", (symbol,))
    await update.message.reply_text(f"Stopped tracking {symbol}")

async def stop_bot(update: Update, context: CallbackContext):
    with conn:
        # conn.execute("DELETE FROM crypto_data")
        conn.execute("DELETE FROM tracked_coins")
    if scheduler.running:
        scheduler.shutdown(wait=False)

    await update.message.reply_text("Bot stopped. All tracking data removed.")
    asyncio.get_event_loop().stop()

# Scheduled data update
# def scheduled_update():
#     coins = get_crypto_data()
#     store_data(coins)
#     logger.info("Scheduled data update completed.")


# Bot launch
def main():
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        logger.error("TELEGRAM_BOT_TOKEN is missing!")
        return
    
    application = Application.builder().token(token).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("forecast", forecast))
    application.add_handler(CommandHandler("history", history))
    application.add_handler(CommandHandler("track", track))
    application.add_handler(CommandHandler("stop_tracking", stop_tracking))
    application.add_handler(CommandHandler("stop_bot", stop_bot))


    # Scheduler setup
    scheduler.add_job(check_tracked_prices, 'interval', hours=1)
    scheduler.start()

    logger.info("Bot started successfully.")
    application.run_polling()

if __name__ == "__main__":
    main()