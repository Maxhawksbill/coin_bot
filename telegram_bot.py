import os
from dotenv import load_dotenv
import logging
import requests
import pandas as pd
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
    data = response.json()["data"]
    return [{
        "symbol": coin["symbol"],
        "price": coin["quote"]["USD"]["price"],
        "percent_change_7d": coin["quote"]["USD"]["percent_change_7d"]
    } for coin in data]

# Filter coins that dropped last 7 days but have the potential for growth
def filter_coins(coins):
    return [coin for coin in coins if coin["percent_change_7d"] < -10]

c = conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS crypto_data
             (symbol TEXT, price REAL, percent_change_7d REAL, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')
conn.commit()

# Store data in the database
def store_data(coins):
    with conn as c:
        for coin in coins:
            c.execute("INSERT INTO crypto_data (symbol, price, percent_change_7d) VALUES (?, ?, ?)",
                      (coin["symbol"], coin["price"], coin["percent_change_7d"]))
        conn.commit()

# Telegram reply for start command
async def start(update: Update, context: CallbackContext):
    message = (
        "Welcome to the Crypto Bot! Here are the available commands:\n"
        "/forecast - Get coins with potential for growth\n"
        "/history - Get top results from forecast history\n"
        "/top_losers - not available\n"
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

    # Scheduler setup
    # scheduler.add_job(scheduled_update, 'interval', hours=1)
    # scheduler.start()

    logger.info("Bot started successfully.")
    application.run_polling()

if __name__ == "__main__":
    main()