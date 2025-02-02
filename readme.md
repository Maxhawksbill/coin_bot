Crypto Bot
This is a Telegram bot that provides information about cryptocurrencies. The bot can perform the following functions:

Features
/start: Displays a welcome message with a list of available commands.
/forecast: Shows the TOP 3 coins that have dropped in price by more than 10% over the last 7 days but have potential for growth.
/history: Retrieves and displays the top 10 most recent records of cryptocurrency data.

Setup
Clone the repository:

git clone <repository-url>
cd <repository-directory>

Set up your environment variables:

Create a .env file in the root directory.
Add your API keys and tokens:
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
CMC_API_KEY=your_coinmarketcap_api_key
CMC_URL=https://pro-api.coinmarketcap.com/v1/cryptocurrency/listings/latest

Usage
Start the bot by sending the /start command.
Use /forecast to get the top 3 coins with potential for growth.
Use /history to view the top 10 most recent cryptocurrency records.

License
This project is licensed under the MIT License.