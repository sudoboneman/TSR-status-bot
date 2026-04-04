import discord
from discord.ext import commands
from discord import app_commands
import aiohttp
import os
import json
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
TSR_API_KEY = os.getenv("TSR_API_KEY")
BASE_URL = "https://api.tsrhub.org/v1"

# Bot setup
class TSRBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=discord.Intents.default())
        self.session = None

    async def setup_hook(self):
        # Create a single aiohttp session for the lifespan of the bot
        self.session = aiohttp.ClientSession(headers={"Authorization": f"Bearer {TSR_API_KEY}"})
        # Sync slash commands to Discord
        await self.tree.sync()
        print("Bot is ready and slash commands are synced.")

    async def close(self):
        if self.session:
            await self.session.close()
        await super().close()

bot = TSRBot()

# --- HELPER FUNCTIONS ---

async def fetch_tsr(endpoint: str):
    """Helper to fetch data from the TSR API."""
    async with bot.session.get(f"{BASE_URL}{endpoint}") as response:
        if response.status == 200:
            return await response.json()
        elif response.status == 429:
            return {"error": "Rate limit exceeded. Try again later."}
        elif response.status in [401, 403]:
            return {"error": "API Key invalid or missing required scope."}
        else:
            data = await response.json()
            return {"error": data.get("error", f"HTTP {response.status}")}

def format_amount(value):
    """Formats large token strings into human-readable numbers with commas."""
    text = str(value or "0").strip()
    if not text: return "0"
    negative = text.startswith("-")
    raw = text[1:] if negative else text
    whole, sep, frac = raw.partition(".")
    if not whole.isdigit() or (sep and not frac.isdigit()): return str(value)
    whole_formatted = f"{int(whole):,}"
    sign = "-" if negative else ""
    return f"{sign}{whole_formatted}.{frac}" if frac else f"{sign}{whole_formatted}"

# --- SLASH COMMANDS: PUBLIC USER DATA ---

@bot.tree.command(name="profile", description="Get a user's public TSR profile")
async def profile(interaction: discord.Interaction, member: discord.Member = None):
    # If no member provided, use the user who ran the command
    target = member or interaction.user
    await interaction.response.defer()
    
    data = await fetch_tsr(f"/users/{target.id}")
    if "error" in data:
        return await interaction.followup.send(f"Error: {data['error']}")
    
    prof = data.get("profile", {})
    embed = discord.Embed(title=f"TSR Profile: {prof.get('displayName', target.name)}", color=discord.Color.blue())
    embed.add_field(name="Role", value=prof.get("role", "USER"), inline=True)
    embed.add_field(name="Service Label", value=prof.get("serviceLabel", "None"), inline=True)
    if prof.get("avatarUrl"):
        embed.set_thumbnail(url=prof.get("avatarUrl"))
    
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="reputation", description="View a user's reputation notes")
async def reputation(interaction: discord.Interaction, member: discord.Member):
    await interaction.response.defer()
    data = await fetch_tsr(f"/users/{member.id}/reputation?limit=5")
    if "error" in data: return await interaction.followup.send(f"Error: {data['error']}")
    
    notes = data.get("notes", [])
    if not notes: return await interaction.followup.send(f"{member.display_name} has no reputation notes.")
    
    embed = discord.Embed(title=f"Reputation: {member.display_name}", color=discord.Color.green())
    for note in notes:
        embed.add_field(name=f"Value: {note.get('value')}", value=note.get('reason', 'No reason provided'), inline=False)
    await interaction.followup.send(embed=embed)


# --- SLASH COMMANDS: BOT/CLAN ACCOUNT DATA ---
# (Remember: /v1/me endpoints pull data for the API key owner)

@bot.tree.command(name="clan_bank", description="View the bot/clan account balances")
async def clan_bank(interaction: discord.Interaction):
    await interaction.response.defer()
    bal_data = await fetch_tsr("/me/balance")
    port_data = await fetch_tsr("/me/portfolio")
    
    if "error" in bal_data: return await interaction.followup.send(bal_data["error"])
    
    embed = discord.Embed(title="Clan Bank / Bot Account", color=discord.Color.gold())
    embed.add_field(name="TSR Balance", value=format_amount(bal_data.get("balance")), inline=True)
    embed.add_field(name="Rakeback", value=format_amount(bal_data.get("rakebackBalance")), inline=True)
    
    if "error" not in port_data:
        embed.add_field(name="Portfolio Value", value=format_amount(port_data.get("assetsValue")), inline=False)
        embed.add_field(name="P/L (Delta)", value=f"{format_amount(port_data.get('assetsDelta'))} ({port_data.get('assetsDeltaPercent', 0)}%)", inline=False)
    
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="clan_holdings", description="View the bot's current stock holdings")
async def clan_holdings(interaction: discord.Interaction):
    await interaction.response.defer()
    data = await fetch_tsr("/me/holdings")
    if "error" in data: return await interaction.followup.send(data["error"])
    
    holdings = data.get("holdings", [])
    shorts = data.get("shorts", [])
    text = f"**Longs:** {len(holdings)} | **Shorts:** {len(shorts)}\n"
    await interaction.followup.send(text)


# --- SLASH COMMANDS: STOCKS ---

@bot.tree.command(name="stocks", description="List top active stocks")
async def stocks(interaction: discord.Interaction):
    await interaction.response.defer()
    data = await fetch_tsr("/stocks")
    if "error" in data: return await interaction.followup.send(data["error"])
    
    stocks_list = data.get("stocks", [])[:10] # Grab top 10
    desc = "\n".join([f"**{s.get('ticker')}**: {s.get('name')} (Price: {format_amount(s.get('initialPrice'))})" for s in stocks_list])
    
    embed = discord.Embed(title="TSR Stock Market", description=desc, color=discord.Color.dark_purple())
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="stock_info", description="Get details for a specific stock ticker")
async def stock_info(interaction: discord.Interaction, ticker: str):
    await interaction.response.defer()
    data = await fetch_tsr(f"/stocks/{ticker.upper()}")
    if "error" in data: return await interaction.followup.send(data["error"])
    
    stock = data.get("stock", {})
    stats = data.get("stats", {})
    
    embed = discord.Embed(title=f"${stock.get('ticker')} - {stock.get('name')}", color=discord.Color.brand_green())
    embed.add_field(name="Holders", value=stats.get("holders", 0))
    embed.add_field(name="Total Shares", value=format_amount(stats.get("totalShares")))
    embed.add_field(name="Weekly High", value=format_amount(stats.get("weeklyHigh")))
    embed.add_field(name="All-Time High", value=format_amount(stats.get("allTimeHigh")))
    embed.add_field(name="Dividend/1000", value=format_amount(stats.get("dividendPer1000")))
    
    await interaction.followup.send(embed=embed)


# --- SLASH COMMANDS: YAPWARS ---

@bot.tree.command(name="yapwar", description="Check the active Yapwar")
async def yapwar(interaction: discord.Interaction):
    await interaction.response.defer()
    data = await fetch_tsr("/yapwars/active")
    if "error" in data: return await interaction.followup.send(data["error"])
    
    active = data.get("active")
    if not active:
        return await interaction.followup.send("No Yapwar is currently active.")
    
    embed = discord.Embed(title=f"Active Yapwar: {active.get('name')}", description=f"Status: {active.get('status')}", color=discord.Color.red())
    embed.set_footer(text=f"War ID: {active.get('id')}")
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="yapwar_leaderboard", description="View the leaderboard for a specific Yapwar")
async def yapwar_leaderboard(interaction: discord.Interaction, war_id: str):
    await interaction.response.defer()
    data = await fetch_tsr(f"/yapwars/{war_id}/leaderboard")
    if "error" in data: return await interaction.followup.send(data["error"])
    
    board = data.get("leaderboard", [])[:10] # Top 10
    desc = "\n".join([f"**#{u.get('rank')}** {u.get('discordUsername')} - {format_amount(u.get('score'))} pts" for u in board])
    
    embed = discord.Embed(title="Yapwar Leaderboard", description=desc or "No participants yet.", color=discord.Color.orange())
    await interaction.followup.send(embed=embed)


# --- SLASH COMMANDS: COMMUNITY & SHOP ---

@bot.tree.command(name="shop", description="View active shop products")
async def shop(interaction: discord.Interaction):
    await interaction.response.defer()
    data = await fetch_tsr("/shop/products")
    if "error" in data: return await interaction.followup.send(data["error"])
    
    products = data.get("products", [])
    desc = "\n".join([f"**{p.get('name')}** - {format_amount(p.get('price'))} TSR\n*{p.get('description')}*" for p in products if p.get("active")])
    
    embed = discord.Embed(title="TSR Shop", description=desc or "Shop is empty.", color=discord.Color.magenta())
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="goals", description="View active community goals")
async def goals(interaction: discord.Interaction):
    await interaction.response.defer()
    data = await fetch_tsr("/community-goals")
    if "error" in data: return await interaction.followup.send(data["error"])
    
    # Structure depends on API payload, assuming a 'goals' array based on docs
    goals_list = data.get("goals", [])
    text = f"Found {len(goals_list)} active community goals." if data.get("active") else "Community goals are currently inactive."
    await interaction.followup.send(text)


# --- DATA DUMP COMMANDS (For endpoints that just return raw arrays/data) ---

async def dump_data(interaction: discord.Interaction, endpoint: str):
    """Utility command to dump raw json formatted nicely for developers/debug."""
    await interaction.response.defer()
    data = await fetch_tsr(endpoint)
    if "error" in data: return await interaction.followup.send(data["error"])
    
    formatted = json.dumps(data, indent=2)[:1980] # Keep under Discord's 2000 char limit
    await interaction.followup.send(f"```json\n{formatted}\n```")

@bot.tree.command(name="dev_health", description="Check API health")
async def dev_health(interaction: discord.Interaction):
    await dump_data(interaction, "/health")

@bot.tree.command(name="dev_threads", description="Dump latest forum threads JSON")
async def dev_threads(interaction: discord.Interaction):
    await dump_data(interaction, "/forum/threads?sort=latest&category=all&limit=5")

@bot.tree.command(name="dev_transfers", description="Dump bot transfer history")
async def dev_transfers(interaction: discord.Interaction):
    await dump_data(interaction, "/transfers/history?limit=5")

if __name__ == "__main__":
    if not DISCORD_TOKEN or not TSR_API_KEY:
        print("Error: Make sure DISCORD_TOKEN and TSR_API_KEY are set in your .env file.")
    else:
        bot.run(DISCORD_TOKEN)