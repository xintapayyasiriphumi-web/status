import discord
from discord import app_commands
from discord.ext import tasks
import os
import sqlite3
from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo

TOKEN = os.environ["DISCORD_TOKEN"]
STATUS_CHANNEL_ID = int(os.environ["STATUS_CHANNEL_ID"])
# ห้องที่จะส่งข้อความต้อนรับเมื่อลูกค้าเข้า server (ไม่ตั้งก็ได้ — /welcome ยังใช้ได้)
WELCOME_CHANNEL_ID = int(os.environ.get("WELCOME_CHANNEL_ID", "0") or 0)

# สี/ธีมหลักของ INSIDEX
BRAND_COLOR = 0x8B5CF6  # ม่วง

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
        "desc": "ขณะนี้ admin ว่างและพร้อม setup ให้ลูกค้าได้ทันที\nติดต่อผ่าน Ticket ได้เลยครับ\n**ซื้อสินค้าและบริการ** https://discord.com/channels/1400021255528382526/1432715699138072699",
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
# /form : ฟอร์มแจ้งปัญหาลูกค้า
# =========================================
class CustomerFormModal(discord.ui.Modal, title="แจ้งปัญหา / ข้อมูลเครื่อง"):
    specs = discord.ui.TextInput(
        label="สเปคคอม",
        placeholder="เช่น i5-12400F, RTX 3060, RAM 16GB",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=500,
    )
    problem = discord.ui.TextInput(
        label="ปัญหาที่เจอ",
        placeholder="อธิบายอาการที่เจอ",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=1000,
    )
    device_type = discord.ui.TextInput(
        label="ใช้คอมหรือโน็ตบุ๊ค",
        placeholder="คอม / โน็ตบุ๊ค",
        style=discord.TextStyle.short,
        required=True,
        max_length=50,
    )
    network_type = discord.ui.TextInput(
        label="ใช้ LAN หรือ Wifi",
        placeholder="LAN / Wifi",
        style=discord.TextStyle.short,
        required=True,
        max_length=50,
    )
    gpu_brand = discord.ui.TextInput(
        label="การ์ดจอ NVIDIA หรือ RADEON",
        placeholder="NVIDIA / RADEON",
        style=discord.TextStyle.short,
        required=True,
        max_length=50,
    )

    async def on_submit(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="📝 ข้อมูลลูกค้า",
            color=0x5865F2,
            timestamp=discord.utils.utcnow(),
        )
        embed.set_author(
            name=str(interaction.user),
            icon_url=interaction.user.display_avatar.url,
        )
        embed.add_field(name="🖥️ สเปคคอม", value=str(self.specs), inline=False)
        embed.add_field(name="⚠️ ปัญหาที่เจอ", value=str(self.problem), inline=False)
        embed.add_field(name="💻 ประเภทเครื่อง", value=str(self.device_type), inline=True)
        embed.add_field(name="🌐 การเชื่อมต่อ", value=str(self.network_type), inline=True)
        embed.add_field(name="🎮 การ์ดจอ", value=str(self.gpu_brand), inline=True)
        embed.set_footer(text="INSIDEX • FORM")

        await interaction.response.send_message(embed=embed)


class CustomerFormView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="กรอกฟอร์ม",
        emoji="📝",
        style=discord.ButtonStyle.primary,
        custom_id="customer_form_button",
    )
    async def open_form(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(CustomerFormModal())


@tree.command(name="form", description="สร้างฟอร์มให้ลูกค้ากรอกข้อมูลเครื่อง/ปัญหา")
async def form(interaction: discord.Interaction):
    embed = discord.Embed(
        title="📝 แจ้งปัญหา / ข้อมูลเครื่อง",
        description=(
            "กดปุ่มด้านล่างเพื่อกรอกข้อมูล\n\n"
            "• สเปคคอม\n"
            "• ปัญหาที่เจอ\n"
            "• ใช้คอมหรือโน็ตบุ๊ค\n"
            "• ใช้ LAN หรือ Wifi\n"
            "• การ์ดจอ NVIDIA หรือ RADEON\n\n"
            "กรอกครบแล้วกดยืนยัน ระบบจะแสดงข้อมูลออกมาเป็น embed ให้ครับ"
        ),
        color=0x5865F2,
    )
    embed.set_footer(text="INSIDEX • FORM")
    await interaction.response.send_message(embed=embed, view=CustomerFormView())


# =========================================
#  WELCOME PANEL
# =========================================

def build_welcome_embed() -> discord.Embed:
    """สร้าง embed ต้อนรับหน้าตาเหมือนในภาพ"""
    embed = discord.Embed(
        title="✨  WELCOME TO INSIDEX STORE",
        description=(
            "ยินดีต้อนรับสู่ **INSIDEX** แหล่งรวมบริการ "
            "FiveM Optimization และ Windows Performance\n\n"
            "**คุณกำลังมองหาบริการแบบไหน?**\n"
            "กดปุ่มด้านล่างเพื่อดูรายละเอียดแต่ละบริการได้เลยครับ 👇"
        ),
        color=BRAND_COLOR,
    )
    embed.add_field(
        name="🎮  FiveM Settings",
        value="ปรับแต่ง Setting สำหรับ FiveM",
        inline=False,
    )
    embed.add_field(
        name="⚡  Boost FPS",
        value="บริการปรับแต่งและตรวจสอบประสิทธิภาพ",
        inline=False,
    )
    embed.add_field(
        name="🖥️  Windows Optimization",
        value="บริการ Windows และ OS Optimization",
        inline=False,
    )
    embed.add_field(
        name="💬  ปรึกษาทีมงาน",
        value="ไม่รู้จะเลือกอะไรดี? กดปุ่มเพื่อแจ้งสเปกและปัญหาที่พบ",
        inline=False,
    )
    embed.set_footer(text="INSIDEX • FiveM Optimization & Windows Performance")
    return embed


# ---- ข้อความรายละเอียดของแต่ละปุ่ม (เด้งแบบ ephemeral เห็นคนเดียว) ----

def fivem_embed() -> discord.Embed:
    e = discord.Embed(
        title="🎮  FiveM Settings",
        description=(
            "ปรับแต่ง **Setting สำหรับ FiveM** ให้ลื่นและนิ่งที่สุด\n\n"
            "• ปรับค่า config / graphics ให้เหมาะกับเครื่องคุณ\n"
            "• ลด stutter และ frame drop ในเมือง\n"
            "• ตั้งค่าให้เข้ากับ server ที่คุณเล่น\n\n"
            "สนใจ? กดปุ่ม **ปรึกษาทีมงาน** เพื่อแจ้งสเปกเครื่องได้เลยครับ"
        ),
        color=BRAND_COLOR,
    )
    e.set_footer(text="INSIDEX • FiveM Settings")
    return e


def boost_embed() -> discord.Embed:
    e = discord.Embed(
        title="⚡  Boost FPS",
        description=(
            "บริการ **ปรับแต่งและตรวจสอบประสิทธิภาพ** เพิ่ม FPS\n\n"
            "• ตรวจสอบ bottleneck ของเครื่อง\n"
            "• Optimize ให้ได้ FPS สูงสุดเท่าที่เครื่องทำได้\n"
            "• ลด input lag และ latency\n\n"
            "สนใจ? กดปุ่ม **ปรึกษาทีมงาน** เพื่อแจ้งสเปกเครื่องได้เลยครับ"
        ),
        color=BRAND_COLOR,
    )
    e.set_footer(text="INSIDEX • Boost FPS")
    return e


def windows_embed() -> discord.Embed:
    e = discord.Embed(
        title="🖥️  Windows Optimization",
        description=(
            "บริการ **Windows และ OS Optimization**\n\n"
            "• ตัด bloatware / background ที่ไม่จำเป็น\n"
            "• ปรับ Windows ให้เบาและเร็วขึ้น\n"
            "• เหมาะสำหรับสาย gaming โดยเฉพาะ\n\n"
            "สนใจ? กดปุ่ม **ปรึกษาทีมงาน** เพื่อแจ้งสเปกเครื่องได้เลยครับ"
        ),
        color=BRAND_COLOR,
    )
    e.set_footer(text="INSIDEX • Windows Optimization")
    return e


def consult_embed() -> discord.Embed:
    e = discord.Embed(
        title="💬  ปรึกษาทีมงาน",
        description=(
            "ไม่รู้จะเลือกบริการไหนดี? ไม่เป็นไรครับ 🙌\n\n"
            "พิมพ์บอกข้อมูลพวกนี้ไว้ได้เลย เดี๋ยวทีมงานมาช่วยดูให้:\n"
            "• **สเปกเครื่อง** (CPU / GPU / RAM)\n"
            "• **ปัญหาที่เจอ** (เช่น FPS ตก, กระตุก, lag)\n"
            "• **เกม/server** ที่เล่นเป็นหลัก\n\n"
            "ทีมงานจะติดต่อกลับโดยเร็วที่สุดครับ"
        ),
        color=BRAND_COLOR,
    )
    e.set_footer(text="INSIDEX • Support")
    return e


class WelcomeView(discord.ui.View):
    """ปุ่ม 4 อันใต้ panel — persistent (กดได้แม้บอท restart)"""

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="FiveM Settings",
        emoji="🎮",
        style=discord.ButtonStyle.secondary,
        custom_id="insidex_welcome_fivem",
        row=0,
    )
    async def fivem(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(embed=fivem_embed(), ephemeral=True)

    @discord.ui.button(
        label="Boost FPS",
        emoji="⚡",
        style=discord.ButtonStyle.secondary,
        custom_id="insidex_welcome_boost",
        row=0,
    )
    async def boost(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(embed=boost_embed(), ephemeral=True)

    @discord.ui.button(
        label="Windows Optimization",
        emoji="🖥️",
        style=discord.ButtonStyle.secondary,
        custom_id="insidex_welcome_windows",
        row=1,
    )
    async def windows(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(embed=windows_embed(), ephemeral=True)

    @discord.ui.button(
        label="ปรึกษาทีมงาน",
        emoji="💬",
        style=discord.ButtonStyle.primary,
        custom_id="insidex_welcome_consult",
        row=1,
    )
    async def consult(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(embed=consult_embed(), ephemeral=True)



@client.event
async def on_member_join(member: discord.Member):
    """ส่ง panel ต้อนรับเมื่อมีคนเข้า server"""
    if not WELCOME_CHANNEL_ID:
        return
    channel = client.get_channel(WELCOME_CHANNEL_ID)
    if channel is None:
        print(f"[welcome] หาห้อง WELCOME_CHANNEL_ID={WELCOME_CHANNEL_ID} ไม่เจอ")
        return
    try:
        await channel.send(
            content=f"👋 ยินดีต้อนรับ {member.mention} เข้าสู่ **INSIDEX**!",
            embed=build_welcome_embed(),
            view=WelcomeView(),
        )
    except discord.HTTPException as e:
        print(f"[welcome] ส่งข้อความต้อนรับไม่สำเร็จ: {e}")


@tree.command(name="welcome", description="โพสต์ panel ต้อนรับ INSIDEX ในห้องนี้")
async def welcome(interaction: discord.Interaction):
    # ตอบ interaction ก่อน กัน "The application did not respond"
    await interaction.response.send_message("⏳ กำลังโพสต์ panel ต้อนรับ...", ephemeral=True)
    try:
        await interaction.channel.send(embed=build_welcome_embed(), view=WelcomeView())
        await interaction.edit_original_response(content="✅ โพสต์ panel ต้อนรับแล้วครับ")
    except discord.HTTPException as e:
        await interaction.edit_original_response(content=f"❌ โพสต์ไม่สำเร็จ: {e}")


# =========================================
# on_ready
# =========================================
@client.event
async def on_ready():
    await tree.sync()
    client.add_view(CustomerFormView())
    client.add_view(WelcomeView())
    await client.change_presence(activity=discord.CustomActivity(name="🟢 X STATUS"))
    if not status_auto_reset_check.is_running():
        status_auto_reset_check.start()
    if not daily_open_status.is_running():
        daily_open_status.start()
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


# =========================================
# เปิดคิวอัตโนมัติทุก 8 โมงเช้า (เวลาไทย) — ตั้งสถานะเป็น "ว่าง — รับงานได้"
# =========================================
@tasks.loop(time=time(hour=8, minute=0, tzinfo=BANGKOK_TZ))
async def daily_open_status():
    global STATUS_STORED_MESSAGE_ID, STATUS_LAST_CHANGED

    channel = client.get_channel(STATUS_CHANNEL_ID)
    if not channel:
        return

    cfg = STATUS_CONFIG["ว่าง"]
    guild = client.guilds[0] if client.guilds else None
    embed = discord.Embed(title=f"{cfg['emoji']}  {cfg['title']}", description=cfg["desc"], color=cfg["color"])
    embed.set_author(name="INSIDEX STATUS", icon_url=guild.icon.url if guild and guild.icon else None)
    embed.set_image(url=THUMBNAIL_URL)
    embed.set_footer(text=cfg["footer"] + " • เปิดคิวเช้า 08:00")
    embed.timestamp = discord.utils.utcnow()

    if STATUS_STORED_MESSAGE_ID:
        try:
            msg = await channel.fetch_message(STATUS_STORED_MESSAGE_ID)
            await msg.edit(content="@everyone", embed=embed)
        except discord.NotFound:
            STATUS_STORED_MESSAGE_ID = None

    if STATUS_STORED_MESSAGE_ID is None:
        new_msg = await channel.send(content="@everyone", embed=embed)
        STATUS_STORED_MESSAGE_ID = new_msg.id

    STATUS_LAST_CHANGED = datetime.now(BANGKOK_TZ)
    db_log_status_change("ว่าง (เปิดคิว 08:00)", "system")
    print("[daily] เปิดคิวเช้า 08:00 — ตั้งสถานะเป็นว่าง รับงานได้")


@daily_open_status.before_loop
async def before_daily_open_status():
    await client.wait_until_ready()


client.run(TOKEN)