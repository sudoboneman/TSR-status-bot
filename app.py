import discord
from discord.ext import commands
from discord import app_commands
import aiohttp
import os
import json
from dotenv import load_dotenv
from flask import Flask
from threading import Thread

# --- FLASK KEEPALIVE SERVER ---
app = Flask('')

@app.route('/')
def home():
    return "TSR Bot is alive and fully operational!"

def run_flask():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run_flask)
    t.start()

# --- ENVIRONMENT VARIABLES ---
load_dotenv()
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
TSR_API_KEY = os.getenv("TSR_API_KEY")
BASE_URL = "https://api.tsrhub.org/v1"

# --- BOT SETUP ---
class TSRBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=discord.Intents.default())
        self.session = None

    async def setup_hook(self):
        self.session = aiohttp.ClientSession(headers={"Authorization": f"Bearer {TSR_API_KEY}"})
        try:
            synced = await self.tree.sync()
            print(f"Bot is ready! Synced {len(synced)} slash commands globally.")
        except Exception as e:
            print(f"Failed to sync commands: {e}")

    async def close(self):
        if self.session:
            await self.session.close()
        await super().close()

bot = TSRBot()

# --- HELPER FUNCTIONS ---

async def handle_response(response):
    if response.status in [200, 201]:
        return await response.json()
    elif response.status == 429:
        return {"error": "Rate limit exceeded. Try again later."}
    elif response.status in [401, 403]:
        return {"error": "API Key invalid or missing required scope."}
    else:
        try:
            data = await response.json()
            return {"error": data.get("error", f"HTTP {response.status}")}
        except:
            return {"error": f"HTTP {response.status}"}

async def fetch_tsr(endpoint: str):
    async with bot.session.get(f"{BASE_URL}{endpoint}") as response:
        return await handle_response(response)

async def post_tsr(endpoint: str, payload: dict = None):
    kwargs = {"json": payload} if payload else {}
    async with bot.session.post(f"{BASE_URL}{endpoint}", **kwargs) as response:
        return await handle_response(response)

async def delete_tsr(endpoint: str, payload: dict = None):
    kwargs = {"json": payload} if payload else {}
    async with bot.session.delete(f"{BASE_URL}{endpoint}", **kwargs) as response:
        return await handle_response(response)

def format_amount(value):
    text = str(value or "0").strip()
    if not text: return "0"
    negative = text.startswith("-")
    raw = text[1:] if negative else text
    whole, sep, frac = raw.partition(".")
    if not whole.isdigit() or (sep and not frac.isdigit()): return str(value)
    whole_formatted = f"{int(whole):,}"
    sign = "-" if negative else ""
    return f"{sign}{whole_formatted}.{frac}" if frac else f"{sign}{whole_formatted}"

async def send_json_dump(interaction, data):
    """Helper to send large JSON payloads safely."""
    if "error" in data: return await interaction.followup.send(f"Error: {data['error']}")
    formatted = json.dumps(data, indent=2)[:1980]
    await interaction.followup.send(f"```json\n{formatted}\n```")

# ==========================================
# 1. ACCOUNT & PROFILE (READ / WRITE)
# ==========================================

@bot.tree.command(name="my_basic", description="Get your basic profile and roles (API Key Owner)")
async def my_basic(interaction: discord.Interaction):
    await interaction.response.defer()
    data = await fetch_tsr("/me")
    await send_json_dump(interaction, data)

@bot.tree.command(name="my_full", description="Full account snapshot")
async def my_full(interaction: discord.Interaction):
    await interaction.response.defer()
    data = await fetch_tsr("/me/full?fresh=1")
    await send_json_dump(interaction, data)

@bot.tree.command(name="my_trades", description="View your recent trades")
async def my_trades(interaction: discord.Interaction):
    await interaction.response.defer()
    data = await fetch_tsr("/me/trades?limit=10")
    await send_json_dump(interaction, data)

@bot.tree.command(name="update_profile", description="Update your public profile display name")
async def update_profile(interaction: discord.Interaction, display_name: str):
    await interaction.response.defer()
    data = await post_tsr("/profile", {"displayName": display_name})
    if "error" in data: return await interaction.followup.send(f"Error: {data['error']}")
    await interaction.followup.send(f"✅ Profile updated! New name: **{display_name}**")

# ==========================================
# 2. TRANSFERS
# ==========================================

@bot.tree.command(name="transfer", description="Send TSR tokens to another user")
async def transfer(interaction: discord.Interaction, user: discord.Member, amount: str, memo: str = None):
    await interaction.response.defer()
    payload = {
        "toDiscordUserId": str(user.id),
        "toDiscordUsername": user.name,
        "amount": amount
    }
    if memo: payload["memo"] = memo
    
    data = await post_tsr("/transfers", payload)
    if "error" in data: return await interaction.followup.send(f"❌ Transfer Failed: {data['error']}")
    
    await interaction.followup.send(f"💸 **Transfer Successful!** Sent {amount} TSR to {user.mention}.")

# ==========================================
# 3. NOTIFICATIONS
# ==========================================

@bot.tree.command(name="notifications", description="View your unread notifications")
async def notifications(interaction: discord.Interaction):
    await interaction.response.defer()
    data = await fetch_tsr("/notifications?unread=1")
    await send_json_dump(interaction, data)

@bot.tree.command(name="mark_notification_read", description="Mark a specific notification ID as read")
async def mark_notification_read(interaction: discord.Interaction, notif_id: str):
    await interaction.response.defer()
    data = await post_tsr("/notifications/read", {"ids": [notif_id]})
    if "error" in data: return await interaction.followup.send(f"Error: {data['error']}")
    await interaction.followup.send("✅ Notification marked as read.")

# ==========================================
# 4. USERS & REPUTATION
# ==========================================

@bot.tree.command(name="profile", description="Get a user's public TSR profile")
async def profile(interaction: discord.Interaction, member: discord.Member = None):
    target = member or interaction.user
    await interaction.response.defer()
    data = await fetch_tsr(f"/users/{target.id}")
    if "error" in data: return await interaction.followup.send(f"Error: {data['error']}")
    
    prof = data.get("profile", {})
    embed = discord.Embed(title=f"TSR Profile: {prof.get('displayName', target.name)}", color=discord.Color.blue())
    embed.add_field(name="Role", value=prof.get("role", "USER"), inline=True)
    embed.add_field(name="Service Label", value=prof.get("serviceLabel", "None"), inline=True)
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="reputation", description="View a user's reputation notes")
async def reputation(interaction: discord.Interaction, member: discord.Member):
    await interaction.response.defer()
    data = await fetch_tsr(f"/users/{member.id}/reputation?limit=5")
    await send_json_dump(interaction, data)

@bot.tree.command(name="add_reputation", description="Leave a reputation note for a user")
@app_commands.choices(value=[app_commands.Choice(name="Positive (+1)", value=1), app_commands.Choice(name="Negative (-1)", value=-1)])
async def add_reputation(interaction: discord.Interaction, member: discord.Member, value: app_commands.Choice[int], reason: str):
    await interaction.response.defer()
    data = await post_tsr(f"/users/{member.id}/reputation", {"value": value.value, "reason": reason})
    if "error" in data: return await interaction.followup.send(f"❌ Error: {data['error']}")
    await interaction.followup.send(f"✅ Reputation added to {member.mention}!")

@bot.tree.command(name="view_profile", description="Ping the API to record a profile view for a user")
async def view_profile(interaction: discord.Interaction, member: discord.Member):
    await interaction.response.defer()
    data = await post_tsr(f"/users/{member.id}/views", {"viewerId": str(interaction.user.id)})
    if "error" in data: return await interaction.followup.send(f"Error: {data['error']}")
    await interaction.followup.send(f"👁️ View recorded for {member.display_name}.")

# ==========================================
# 5. STOCKS
# ==========================================

@bot.tree.command(name="stocks", description="List top active stocks")
async def stocks(interaction: discord.Interaction):
    await interaction.response.defer()
    data = await fetch_tsr("/stocks")
    stocks_list = data.get("stocks", [])[:10]
    desc = "\n".join([f"**{s.get('ticker')}**: {s.get('name')} (Price: {format_amount(s.get('initialPrice'))})" for s in stocks_list])
    embed = discord.Embed(title="TSR Stock Market", description=desc, color=discord.Color.dark_purple())
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="stock_info", description="Get details for a specific stock ticker")
async def stock_info(interaction: discord.Interaction, ticker: str):
    await interaction.response.defer()
    data = await fetch_tsr(f"/stocks/{ticker.upper()}")
    if "error" in data: return await interaction.followup.send(f"Error: {data['error']}")
    stock, stats = data.get("stock", {}), data.get("stats", {})
    embed = discord.Embed(title=f"${stock.get('ticker')} - {stock.get('name')}", color=discord.Color.brand_green())
    embed.add_field(name="Total Shares", value=format_amount(stats.get("totalShares")))
    embed.add_field(name="All-Time High", value=format_amount(stats.get("allTimeHigh")))
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="stock_candles", description="Get candlestick chart data (JSON)")
@app_commands.choices(interval=[
    app_commands.Choice(name="1 Minute", value="1m"),
    app_commands.Choice(name="1 Hour", value="1h"),
    app_commands.Choice(name="1 Day", value="24h")
])
async def stock_candles(interaction: discord.Interaction, ticker: str, interval: app_commands.Choice[str]):
    await interaction.response.defer()
    data = await fetch_tsr(f"/stocks/{ticker.upper()}/candles?interval={interval.value}&limit=5")
    await send_json_dump(interaction, data)

@bot.tree.command(name="stock_price", description="Latest price snapshot for a stock")
async def stock_price(interaction: discord.Interaction, ticker: str):
    await interaction.response.defer()
    data = await fetch_tsr(f"/stocks/{ticker.upper()}/price")
    await send_json_dump(interaction, data)

@bot.tree.command(name="stock_orderbook", description="View the orderbook for a stock")
async def stock_orderbook(interaction: discord.Interaction, ticker: str):
    await interaction.response.defer()
    data = await fetch_tsr(f"/stocks/{ticker.upper()}/orderbook")
    await send_json_dump(interaction, data)

@bot.tree.command(name="stock_trades", description="View recent trades for a stock")
async def stock_trades(interaction: discord.Interaction, ticker: str):
    await interaction.response.defer()
    data = await fetch_tsr(f"/stocks/{ticker.upper()}/trades")
    await send_json_dump(interaction, data)

@bot.tree.command(name="ceo_leaderboard", description="View the stock market CEO leaderboard")
async def ceo_leaderboard(interaction: discord.Interaction):
    await interaction.response.defer()
    data = await fetch_tsr("/stocks/leaderboard")
    await send_json_dump(interaction, data)

# ==========================================
# 6. FORUM (READ / WRITE)
# ==========================================

@bot.tree.command(name="forum_threads", description="List recent forum threads")
async def forum_threads(interaction: discord.Interaction):
    await interaction.response.defer()
    data = await fetch_tsr("/forum/threads?sort=latest&category=all&limit=5")
    await send_json_dump(interaction, data)

@bot.tree.command(name="forum_read", description="Read a specific forum thread")
async def forum_read(interaction: discord.Interaction, thread_id: str):
    await interaction.response.defer()
    data = await fetch_tsr(f"/forum/threads/{thread_id}")
    await send_json_dump(interaction, data)

@bot.tree.command(name="forum_replies", description="Read replies to a thread")
async def forum_replies(interaction: discord.Interaction, thread_id: str):
    await interaction.response.defer()
    data = await fetch_tsr(f"/forum/threads/{thread_id}/posts?limit=5")
    await send_json_dump(interaction, data)

@bot.tree.command(name="forum_create_thread", description="Create a new forum thread")
async def forum_create_thread(interaction: discord.Interaction, category_id: str, title: str, content: str):
    await interaction.response.defer()
    payload = {"categoryId": category_id, "title": title, "content": content, "attachments": []}
    data = await post_tsr("/forum/threads", payload)
    if "error" in data: return await interaction.followup.send(f"Error: {data['error']}")
    await interaction.followup.send(f"✅ Thread created! ID: `{data.get('thread', {}).get('id')}`")

@bot.tree.command(name="forum_reply", description="Reply to a forum thread")
async def forum_reply(interaction: discord.Interaction, thread_id: str, content: str):
    await interaction.response.defer()
    payload = {"content": content, "parentId": None, "attachments": []}
    data = await post_tsr(f"/forum/threads/{thread_id}/posts", payload)
    if "error" in data: return await interaction.followup.send(f"Error: {data['error']}")
    await interaction.followup.send("✅ Reply posted successfully.")

@bot.tree.command(name="forum_vote", description="Upvote or Downvote a thread")
@app_commands.choices(vote=[app_commands.Choice(name="Upvote", value="UP"), app_commands.Choice(name="Downvote", value="DOWN")])
async def forum_vote(interaction: discord.Interaction, thread_id: str, vote: app_commands.Choice[str]):
    await interaction.response.defer()
    data = await post_tsr(f"/forum/threads/{thread_id}/vote", {"vote": vote.value})
    if "error" in data: return await interaction.followup.send(f"Error: {data['error']}")
    await interaction.followup.send(f"✅ Voted {vote.name} on thread.")

@bot.tree.command(name="forum_tip", description="Tip a thread author in TSR")
async def forum_tip(interaction: discord.Interaction, thread_id: str, amount: str):
    await interaction.response.defer()
    data = await post_tsr(f"/forum/threads/{thread_id}/tip", {"amount": amount})
    if "error" in data: return await interaction.followup.send(f"Error: {data['error']}")
    await interaction.followup.send(f"💸 Tipped {amount} TSR to the thread author!")

# ==========================================
# 7. YAPWARS
# ==========================================

@bot.tree.command(name="yapwar_active", description="Check the active Yapwar")
async def yapwar_active(interaction: discord.Interaction):
    await interaction.response.defer()
    data = await fetch_tsr("/yapwars/active")
    active = data.get("active")
    if not active: return await interaction.followup.send("No Yapwar is currently active.")
    embed = discord.Embed(title=f"Active Yapwar: {active.get('name')}", description=f"Status: {active.get('status')}", color=discord.Color.red())
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="yapwar_list", description="List all recent Yapwars")
async def yapwar_list(interaction: discord.Interaction):
    await interaction.response.defer()
    data = await fetch_tsr("/yapwars")
    await send_json_dump(interaction, data)

@bot.tree.command(name="yapwar_rules", description="Read the rules of Yapwars")
async def yapwar_rules(interaction: discord.Interaction):
    await interaction.response.defer()
    data = await fetch_tsr("/yapwars/rules")
    await send_json_dump(interaction, data)

@bot.tree.command(name="yapwar_stats", description="Get stats for a specific Yapwar")
async def yapwar_stats(interaction: discord.Interaction, war_id: str):
    await interaction.response.defer()
    data = await fetch_tsr(f"/yapwars/{war_id}/stats")
    await send_json_dump(interaction, data)

@bot.tree.command(name="yapwar_activity", description="Recent activity feed for a Yapwar")
async def yapwar_activity(interaction: discord.Interaction, war_id: str):
    await interaction.response.defer()
    data = await fetch_tsr(f"/yapwars/{war_id}/activity")
    await send_json_dump(interaction, data)

# ==========================================
# 8. SHOP & GOALS
# ==========================================

@bot.tree.command(name="shop", description="View active shop products")
async def shop(interaction: discord.Interaction):
    await interaction.response.defer()
    data = await fetch_tsr("/shop/products")
    products = data.get("products", [])
    desc = "\n".join([f"**{p.get('name')}** - {format_amount(p.get('price'))} TSR" for p in products if p.get("active")])
    embed = discord.Embed(title="TSR Shop", description=desc or "Shop is empty.", color=discord.Color.magenta())
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="goals", description="View active community goals")
async def goals(interaction: discord.Interaction):
    await interaction.response.defer()
    data = await fetch_tsr("/community-goals")
    await send_json_dump(interaction, data)

# ==========================================
# 9. REFERRALS
# ==========================================

@bot.tree.command(name="referrals", description="List your referral invites")
async def referrals(interaction: discord.Interaction):
    await interaction.response.defer()
    data = await fetch_tsr("/account/referrals/invites")
    await send_json_dump(interaction, data)

@bot.tree.command(name="create_referral", description="Create a new referral invite code")
async def create_referral(interaction: discord.Interaction, label: str, custom_code: str = None):
    await interaction.response.defer()
    payload = {"label": label}
    if custom_code: payload["code"] = custom_code
    data = await post_tsr("/account/referrals/invites", payload)
    if "error" in data: return await interaction.followup.send(f"Error: {data['error']}")
    await interaction.followup.send(f"✅ Referral code created!")

@bot.tree.command(name="ping_referral", description="Ping referral activity")
async def ping_referral(interaction: discord.Interaction):
    await interaction.response.defer()
    data = await post_tsr("/account/referrals/activity")
    if "error" in data: return await interaction.followup.send(f"Error: {data['error']}")
    await interaction.followup.send("✅ Activity pinged successfully.")


if __name__ == "__main__":
    if not DISCORD_TOKEN or not TSR_API_KEY:
        print("Error: Make sure DISCORD_TOKEN and TSR_API_KEY are set in your .env file.")
    else:
        keep_alive()
        bot.run(DISCORD_TOKEN)