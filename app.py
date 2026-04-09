import discord
from discord.ext import commands
from discord import app_commands
import aiohttp
import os
import re
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
        super().__init__(command_prefix="!", intents=discord.Intents.default(), help_command=None)
        self.session = None

    async def setup_hook(self):
        # 1. Initialize the API session for TSR
        self.session = aiohttp.ClientSession(headers={"Authorization": f"Bearer {TSR_API_KEY}"})
        
        # 2. Global Error Handler for the Command Tree
        # This stops late timeouts (error 10062) from filling your logs
        async def on_tree_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
            if isinstance(error, app_commands.CommandInvokeError):
                if isinstance(error.original, discord.errors.NotFound) and error.original.code == 10062:
                    return 
            print(f"Command Error: {error}")
            
        self.tree.on_error = on_tree_error

        # 3. Simple Sync on Startup
        # This registers all commands with Discord so they show in autocomplete
        try:
            synced = await self.tree.sync()
            print(f"✅ Bot started and synced {len(synced)} commands.")
        except discord.errors.HTTPException as e:
            # If you see this in your logs, you are currently rate-limited by Discord
            print(f"❌ Could not sync: {e}")

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

# ==========================================
# REFINED HELPER FUNCTION
# ==========================================

def prettify_key(key: str) -> str:
    """Helper to turn camelCase or snake_case into Title Case (e.g., discordUsername -> Discord Username)"""
    s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', key)
    return re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1).replace('_', ' ').title()

async def send_embed_dump(interaction: discord.Interaction, data: dict, title: str):
    """Dynamic Embed Builder: Professionally formats ANY TSR API JSON response."""
    if "error" in data:
        return await interaction.followup.send(f"❌ **Error:** {data['error']}")

    # 1. explicit keys to hide from the UI to keep it clean
    IGNORE_KEYS = {"userId", "discordUserId", "discordAvatarHash", "id", "impersonation"}

    # 2. Setup the Title
    primary_id = data.get("displayName") or data.get("name") or data.get("ticker")
    embed_title = f"{title}: {primary_id}" if primary_id else title
    embed = discord.Embed(title=embed_title, color=discord.Color.from_rgb(0, 204, 255))
    
    # 3. Setup Images (Avatars / Banners)
    avatar_url = data.get("avatarUrl") or data.get("avatar_url")
    thumbnail_url = data.get("thumbnailUrl") or data.get("thumbnail_url")
    image_url = data.get("imageUrl") or data.get("image_url") or data.get("banner_url")
    
    if avatar_url: embed.set_thumbnail(url=avatar_url)
    elif thumbnail_url: embed.set_thumbnail(url=thumbnail_url)
    elif image_url: embed.set_image(url=image_url)

    # 4. Iterate and Format Data
    desc_list = []
    field_count = 0

    for key, value in data.items():
        if field_count >= 25: break 
        
        # Skip useless keys, empty strings, None values, and raw URLs
        if key in IGNORE_KEYS or value in [None, ""] or "url" in key.lower() or "hash" in key.lower():
             continue

        display_key = prettify_key(key)

        # Handle Arrays (e.g., Roletags, Lists of objects)
        # Handle Arrays (e.g., Trades, Roletags, Threads)
        if isinstance(value, list):
            if not value: continue 
            
            items = []
            for item in value[:10]:
                if isinstance(item, dict):
                    # --- SMART EXTRACTION LOGIC ---
                    
                    # 1. Check for Trade Data (Side + Ticker + Amount)
                    if "side" in item and "ticker" in item:
                        side_emoji = "🟢" if item.get("side") == "BUY" else "🔴"
                        amount = format_amount(item.get("amount", 0))
                        price = format_amount(item.get("price", 0))
                        items.append(f"{side_emoji} **{item.get('side')}** {item.get('ticker')} | {amount} @ {price}")
                    
                    # 2. Check for User/Role Data (Label/Username)
                    elif any(k in item for k in ["label", "name", "discordUsername"]):
                        name = item.get("label") or item.get("name") or item.get("discordUsername")
                        items.append(f"• {str(name).title()}")
                        
                    # 3. Check for Forum/Notification Data (Title/Type)
                    elif any(k in item for k in ["title", "type"]):
                        text = item.get("title") or item.get("type")
                        items.append(f"• {text}")

                    # 4. Fallback for other objects: Hide IDs and show first 3 relevant fields
                    else:
                        summary_parts = []
                        for k, v in item.items():
                            if k.lower() in ["id", "userid", "threadid"] or v in [None, ""]:
                                continue
                            summary_parts.append(f"**{prettify_key(k)}**: {v}")
                            if len(summary_parts) >= 3: break
                        items.append(f"• " + " | ".join(summary_parts))
                else:
                    items.append(f"• {item}")
            
            if items:
                desc_list.append(f"**{display_key}**\n" + "\n".join(items))
                
        # Handle Nested Dictionaries
        elif isinstance(value, dict):
            sub_desc = []
            for k, v in value.items():
                if v in [None, ""]: continue
                val_str = format_amount(v) if any(t in k.lower() for t in ["amount", "balance", "price", "value", "score"]) else str(v)
                sub_desc.append(f"**{prettify_key(k)}**: {val_str}")
            if sub_desc:
                embed.add_field(name=display_key, value="\n".join(sub_desc)[:1024], inline=False)
                field_count += 1
                
        # Handle Standard Key/Values
        else:
            if isinstance(value, bool):
                final_value = "✅ Yes" if value else "❌ No"
            else:
                final_value = str(value)
                # Auto-format money/scores
                if any(term in key.lower() for term in ["amount", "balance", "price", "value", "score", "shares", "delta"]):
                    final_value = format_amount(value)

            embed.add_field(name=display_key, value=final_value, inline=True)
            field_count += 1
            
    if desc_list:
        embed.description = "\n\n".join(desc_list)[:4000]
        
    embed.set_footer(text="Powered by the TSR Community API")
    await interaction.followup.send(embed=embed)

# ==========================================
# 1. ACCOUNT & PROFILE (READ / WRITE)
# ==========================================

@bot.tree.command(name="my_basic", description="Get your basic profile and roles (API Key Owner)")
async def my_basic(interaction: discord.Interaction):
    await interaction.response.defer()
    data = await fetch_tsr("/me")
    await send_embed_dump(interaction, data, "👤 Basic Profile")

@bot.tree.command(name="my_full", description="Full account snapshot")
async def my_full(interaction: discord.Interaction):
    await interaction.response.defer()
    data = await fetch_tsr("/me/full?fresh=1")
    await send_embed_dump(interaction, data, "📊 Full Account Snapshot")

@bot.tree.command(name="my_trades", description="View your recent trades")
async def my_trades(interaction: discord.Interaction):
    await interaction.response.defer()
    data = await fetch_tsr("/me/trades?limit=10")
    await send_embed_dump(interaction, data, "📈 Recent Trades")

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
    payload = {"toDiscordUserId": str(user.id), "toDiscordUsername": user.name, "amount": amount}
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
    await send_embed_dump(interaction, data, "🔔 Unread Notifications")

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
    await send_embed_dump(interaction, data, f"⭐ Reputation Notes: {member.display_name}")

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

@bot.tree.command(name="stock_candles", description="Get candlestick chart data")
@app_commands.choices(interval=[
    app_commands.Choice(name="1 Minute", value="1m"),
    app_commands.Choice(name="1 Hour", value="1h"),
    app_commands.Choice(name="1 Day", value="24h")
])
async def stock_candles(interaction: discord.Interaction, ticker: str, interval: app_commands.Choice[str]):
    await interaction.response.defer()
    data = await fetch_tsr(f"/stocks/{ticker.upper()}/candles?interval={interval.value}&limit=5")
    await send_embed_dump(interaction, data, f"🕯️ {ticker.upper()} Candlesticks")

@bot.tree.command(name="stock_price", description="Latest price snapshot for a stock")
async def stock_price(interaction: discord.Interaction, ticker: str):
    await interaction.response.defer()
    data = await fetch_tsr(f"/stocks/{ticker.upper()}/price")
    await send_embed_dump(interaction, data, f"💰 {ticker.upper()} Live Price")

@bot.tree.command(name="stock_orderbook", description="View the orderbook for a stock")
async def stock_orderbook(interaction: discord.Interaction, ticker: str):
    await interaction.response.defer()
    data = await fetch_tsr(f"/stocks/{ticker.upper()}/orderbook")
    await send_embed_dump(interaction, data, f"📚 {ticker.upper()} Orderbook")

@bot.tree.command(name="stock_trades", description="View recent trades for a stock")
async def stock_trades(interaction: discord.Interaction, ticker: str):
    await interaction.response.defer()
    data = await fetch_tsr(f"/stocks/{ticker.upper()}/trades")
    await send_embed_dump(interaction, data, f"🔄 {ticker.upper()} Recent Trades")

@bot.tree.command(name="ceo_leaderboard", description="View the stock market CEO leaderboard")
async def ceo_leaderboard(interaction: discord.Interaction):
    await interaction.response.defer()
    data = await fetch_tsr("/stocks/leaderboard")
    await send_embed_dump(interaction, data, "👑 CEO Leaderboard")

# ==========================================
# 6. FORUM (READ / WRITE)
# ==========================================

@bot.tree.command(name="forum_threads", description="List recent forum threads")
async def forum_threads(interaction: discord.Interaction):
    await interaction.response.defer()
    data = await fetch_tsr("/forum/threads?sort=latest&category=all&limit=5")
    await send_embed_dump(interaction, data, "💬 Recent Forum Threads")

@bot.tree.command(name="forum_read", description="Read a specific forum thread")
async def forum_read(interaction: discord.Interaction, thread_id: str):
    await interaction.response.defer()
    data = await fetch_tsr(f"/forum/threads/{thread_id}")
    await send_embed_dump(interaction, data, "📄 Forum Thread")

@bot.tree.command(name="forum_replies", description="Read replies to a thread")
async def forum_replies(interaction: discord.Interaction, thread_id: str):
    await interaction.response.defer()
    data = await fetch_tsr(f"/forum/threads/{thread_id}/posts?limit=5")
    await send_embed_dump(interaction, data, "💬 Thread Replies")

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
    await send_embed_dump(interaction, data, "⚔️ Yapwars List")

@bot.tree.command(name="yapwar_rules", description="Read the rules of Yapwars")
async def yapwar_rules(interaction: discord.Interaction):
    await interaction.response.defer()
    data = await fetch_tsr("/yapwars/rules")
    await send_embed_dump(interaction, data, "📜 Yapwar Rules")

@bot.tree.command(name="yapwar_stats", description="Get stats for a specific Yapwar")
async def yapwar_stats(interaction: discord.Interaction, war_id: str):
    await interaction.response.defer()
    data = await fetch_tsr(f"/yapwars/{war_id}/stats")
    await send_embed_dump(interaction, data, "📊 Yapwar Stats")

@bot.tree.command(name="yapwar_activity", description="Recent activity feed for a Yapwar")
async def yapwar_activity(interaction: discord.Interaction, war_id: str):
    await interaction.response.defer()
    data = await fetch_tsr(f"/yapwars/{war_id}/activity")
    await send_embed_dump(interaction, data, "⚡ Yapwar Activity Feed")

# ==========================================
# 8. SHOP & GOALS
# ==========================================

@bot.tree.command(name="shop", description="View active shop products")
async def shop(interaction: discord.Interaction):
    await interaction.response.defer()
    data = await fetch_tsr("/shop/products")
    products = data.get("products", [])
    desc = "\n".join([f"**{p.get('name')}** - {format_amount(p.get('price'))} TSR" for p in products if p.get("active")])
    embed = discord.Embed(title="🛒 TSR Shop", description=desc or "Shop is empty.", color=discord.Color.magenta())
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="goals", description="View active community goals")
async def goals(interaction: discord.Interaction):
    await interaction.response.defer()
    data = await fetch_tsr("/community-goals")
    await send_embed_dump(interaction, data, "🎯 Community Goals")

# ==========================================
# 9. REFERRALS
# ==========================================

@bot.tree.command(name="referrals", description="List your referral invites")
async def referrals(interaction: discord.Interaction):
    await interaction.response.defer()
    data = await fetch_tsr("/account/referrals/invites")
    await send_embed_dump(interaction, data, "🔗 My Referrals")

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

# ==========================================
# 10. HELP COMMAND
# ==========================================

@bot.tree.command(name="help", description="View a list of all available TSR bot commands")
async def help_command(interaction: discord.Interaction):
    # Respond instantly to prevent 10062 timeouts on the help menu
    embed = discord.Embed(
        title="🤖 TSR Bot Command Guide", 
        description="Here is everything I can do. Type `/` and click my icon to see the required inputs for each command!", 
        color=discord.Color.blurple()
    )
    
    embed.add_field(name="👤 Account & Profile", value="`/my_basic` `/my_full` `/my_trades` `/update_profile`", inline=False)
    embed.add_field(name="💸 Transfers & Notifications", value="`/transfer` `/notifications` `/mark_notification_read`", inline=False)
    embed.add_field(name="👥 Community & Reputation", value="`/profile` `/reputation` `/add_reputation` `/view_profile`", inline=False)
    embed.add_field(name="📈 Stock Market", value="`/stocks` `/stock_info` `/stock_price` `/stock_candles` `/stock_orderbook` `/stock_trades` `/ceo_leaderboard`", inline=False)
    embed.add_field(name="💬 Forum", value="`/forum_threads` `/forum_read` `/forum_replies` `/forum_create_thread` `/forum_reply` `/forum_vote` `/forum_tip`", inline=False)
    embed.add_field(name="⚔️ Yapwars", value="`/yapwar_active` `/yapwar_list` `/yapwar_rules` `/yapwar_stats` `/yapwar_activity`", inline=False)
    embed.add_field(name="🛒 Shop, Goals & Referrals", value="`/shop` `/goals` `/referrals` `/create_referral` `/ping_referral`", inline=False)
    
    embed.set_footer(text="Powered by the TSR Community API")
    await interaction.response.send_message(embed=embed)


if __name__ == "__main__":
    if not DISCORD_TOKEN or not TSR_API_KEY:
        print("Error: Make sure DISCORD_TOKEN and TSR_API_KEY are set in your .env file.")
    else:
        keep_alive()
        bot.run(DISCORD_TOKEN)