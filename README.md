# TSR Community Discord Bot

A feature-rich, asynchronous Discord bot built with `discord.py` that integrates directly with the **TSR Community API**. This bot allows users to interact with the TSR economy, stock market, forums, and community events directly from your Discord server using official Slash Commands.

## Features

* **Real-time Stock Market:** View live prices, orderbooks, recent trades, and candlestick data for TSR stocks.
* **Economy & Transfers:** Check balances, portfolio values, and send TSR tokens to other users seamlessly.
* **User Profiles & Reputation:** View public TSR profiles and leave positive/negative reputation notes.
* **Forum Integration:** Read the latest threads, post replies, upvote, and tip authors in TSR.
* **Community Events:** Track active community goals, view Yapwar leaderboards, and browse the TSR shop.
* **Built-in Keep-Alive:** Includes a lightweight Flask web server designed to keep the bot awake on free hosting platforms like Render or Replit.

## Prerequisites

Before you begin, ensure you have the following:
* **Python 3.8** or higher installed.
* A **Discord Bot Token** (Create one at the Discord Developer Portal). Ensure the `applications.commands` scope is enabled when inviting the bot.
* A **TSR Community API Key** (Generated from your account settings in the TSR webapp).

## Installation & Setup

1. **Clone or Download the Repository:**
   Place `app.py` and `requirements.txt` into your project folder.

2. **Install Dependencies:**
   Run the following command in your terminal to install the required Python libraries:
   pip install -r requirements.txt

3. **Configure Environment Variables:**
   Create a file named `.env` in the root directory of your project and add your credentials:
   DISCORD_TOKEN=your_discord_bot_token_here
   TSR_API_KEY=your_tsr_community_api_key_here

4. **Run the Bot:**
   python app.py

## Hosting on Render / Replit (Avoiding Timeouts)

This bot includes a built-in Flask server that runs on port `8080`. Free hosting services put apps to sleep after 15 minutes of inactivity, which causes Discord to throw a `10062: Unknown Interaction` error when the bot takes too long to wake up.

**To keep the bot awake 24/7:**
1. Find the public web URL provided by your host (e.g., `https://your-bot-name.onrender.com`).
2. Go to a free pinging service like UptimeRobot.
3. Create an HTTP(s) Monitor that pings your web URL every 5 minutes.

## Command Categories

The bot registers the following slash commands globally. *(Note: Global commands can take up to an hour to appear in Discord upon first boot. Refresh your client with Ctrl+R or Cmd+R).*

* `/help` - View the in-app command guide.
* **Account:** `/my_basic`, `/my_full`, `/my_trades`, `/update_profile`
* **Transfers:** `/transfer`, `/notifications`, `/mark_notification_read`
* **Community:** `/profile`, `/reputation`, `/add_reputation`, `/view_profile`
* **Stocks:** `/stocks`, `/stock_info`, `/stock_price`, `/stock_candles`, `/stock_orderbook`, `/stock_trades`, `/ceo_leaderboard`
* **Forums:** `/forum_threads`, `/forum_read`, `/forum_replies`, `/forum_create_thread`, `/forum_reply`, `/forum_vote`, `/forum_tip`
* **Events:** `/yapwar_active`, `/yapwar_list`, `/yapwar_rules`, `/yapwar_stats`, `/yapwar_activity`
* **Misc:** `/shop`, `/goals`, `/referrals`, `/create_referral`, `/ping_referral`

---
*Powered by the TSR Community API*