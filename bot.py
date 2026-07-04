import discord
from discord import app_commands
from discord.ext import tasks
import os
import sqlite3
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

TOKEN = os.environ["DISCORD_TOKEN"]
STATUS_CHANNEL_ID = int(os.environ["STATUS_CHANNEL_ID"])

intents = discord.Intents.default()
intents.members = True
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

STATUS_STORED_MESSAGE_ID = None
STATUS_LAST_CHANGED = None
STATUS_AUTO_RESET_HOURS = 6

THUMBNAIL_URL = "https://cdn.discordapp.com/attachments/1446487555091730544/1496205094138417262/34.png?ex=69fccf94&is=69fb7e14&hm=48e3775ced506320521d1a7315b34dbac19a9cf6d445aa04ee7e6a7dba6b410c&"

STATUS_CONFIG = {
    "ว่าง": {
        "color": 0x39FF14,
        "emoji": "🟢",
        "title": "ว่าง — รับงานได้",
        "desc": "ขณะนี้ admin ว่างและพร้อม setup ให้ลูกค้าได้ทันที\nติดต่อผ่าน Ticket ได้เลยครับ\n**ซื้อ Setting** https://discord.com/channels/1400021255528382526/1432715699138072699\n**ลง Windows** https://discord.com/channels/1400021255528382526/1485640881653420062",
        "footer": "INSIDEX • STATUS",
    },
    "ยุ่ง": {
        "color": 0xEF9F27,
        "emoji": "🟡",
        "title": "ยุ่ง — กำลัง setup ให้ลูกค้าอยู่",
        "desc": "ขณะนี้ admin กำลัง setup ให้ลูกค้าอยู่\nอาจตอบช้าหน่อย แต่รับคิวได้ครับ",
        "footer": "INSIDEX • STATUS",
    },
    "เต็ม": {
        "color": 0xE24B4A,
        "emoji": "🔴",
        "title": "เต็ม — Ticket ล้น !",
        "desc": "ขณะนี้คิวเต็มล้น ! รับงานได้\nเเต่จะให้บริการล่าช้านิดหน่อยครับผม",
        "footer": "INSIDEX • STATUS",
    },
}

BANGKOK_TZ = ZoneInfo("Asia/Bangkok")
DB_PATH = "status_log.db"


# =========================================
# DATABASE: เก็บประวัติการเปลี่ยนสถานะ
# =========================================
def db_init():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS status_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            status TEXT NOT NULL,
            changed_at TEXT NOT NULL,
            changed_by TEXT
        )
    """)
    conn.commit()
    conn.close()


def db_log_status_change(status: str, changed_by: str):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO status_log (status, changed_at, changed_by) VALUES (?, ?, ?)",
        (status, datetime.now(BANGKOK_TZ).isoformat(), changed_by),
    )
    conn.commit()
    conn.close()


db_init()


# =========================================
# on_ready
# =========================================
@client.event
async def on_ready():
    await tree.sync()
    await client.change_presence(activity=discord.CustomActivity(name="🟢 X STATUS"))
    if not status_auto_reset_check.is_running():
        status_auto_reset_check.start()
    print(f"Bot ready : {client.user}")


# =========================================
# /setstatus
# =========================================
@tree.command(name="setstatus", description="เปลี่ยนสถานะ INSIDEX (ว่าง / ยุ่ง / เต็ม)")
@app_commands.describe(สถานะ="เลือกสถานะ: ว่าง, ยุ่ง, เต็ม")
@app_commands.choices(สถานะ=[
    app_commands.Choice(name="🟢 ว่าง", value="ว่าง"),
    app_commands.Choice(name="🟡 ยุ่ง", value="ยุ่ง"),
    app_commands.Choice(name="🔴 เต็ม", value="เต็ม"),
])
async def setstatus(interaction: discord.Interaction, สถานะ: str):
    global STATUS_STORED_MESSAGE_ID, STATUS_LAST_CHANGED

    cfg = STATUS_CONFIG[สถานะ]
    channel = client.get_channel(STATUS_CHANNEL_ID)

    embed = discord.Embed(title=f"{cfg['emoji']}  {cfg['title']}", description=cfg["desc"], color=cfg["color"])
    embed.set_author(name="INSIDEX STATUS", icon_url=interaction.guild.icon.url if interaction.guild.icon else discord.Embed.Empty)
    embed.set_image(url=THUMBNAIL_URL)
    embed.set_footer(text=cfg["footer"])
    embed.timestamp = discord.utils.utcnow()

    STATUS_LAST_CHANGED = datetime.now(BANGKOK_TZ)
    db_log_status_change(สถานะ, str(interaction.user))

    if STATUS_STORED_MESSAGE_ID:
        try:
            old_msg = await channel.fetch_message(STATUS_STORED_MESSAGE_ID)
            await old_msg.edit(content="@everyone", embed=embed)
            await interaction.response.send_message(f"✅ อัปเดตสถานะเป็น **{สถานะ}** แล้วครับ", ephemeral=True)
            return
        except discord.NotFound:
            STATUS_STORED_MESSAGE_ID = None

    new_msg = await channel.send(content="@everyone", embed=embed)
    STATUS_STORED_MESSAGE_ID = new_msg.id
    await interaction.response.send_message(f"✅ โพสต์สถานะ **{สถานะ}** ในห้องแล้วครับ", ephemeral=True)


# =========================================
# Auto-reset สถานะกลับเป็น "ว่าง" ถ้าลืมเปลี่ยนนานเกินไป
# =========================================
@tasks.loop(minutes=30)
async def status_auto_reset_check():
    global STATUS_STORED_MESSAGE_ID, STATUS_LAST_CHANGED

    if STATUS_LAST_CHANGED is None or STATUS_STORED_MESSAGE_ID is None:
        return

    elapsed = datetime.now(BANGKOK_TZ) - STATUS_LAST_CHANGED
    if elapsed < timedelta(hours=STATUS_AUTO_RESET_HOURS):
        return

    channel = client.get_channel(STATUS_CHANNEL_ID)
    if not channel:
        return

    try:
        msg = await channel.fetch_message(STATUS_STORED_MESSAGE_ID)
    except discord.NotFound:
        STATUS_STORED_MESSAGE_ID = None
        return

    if msg.embeds and "ว่าง" in msg.embeds[0].title:
        return

    cfg = STATUS_CONFIG["ว่าง"]
    embed = discord.Embed(title=f"{cfg['emoji']}  {cfg['title']}", description=cfg["desc"], color=cfg["color"])
    embed.set_image(url=THUMBNAIL_URL)
    embed.set_footer(text=cfg["footer"] + " • auto-reset")
    embed.timestamp = discord.utils.utcnow()

    await msg.edit(content="@everyone", embed=embed)
    STATUS_LAST_CHANGED = datetime.now(BANGKOK_TZ)
    db_log_status_change("ว่าง (auto-reset)", "system")
    print(f"[auto-reset] สถานะถูกรีเซ็ตเป็นว่าง หลังไม่มีการเปลี่ยนแปลง {STATUS_AUTO_RESET_HOURS} ชม.")


client.run(TOKEN)