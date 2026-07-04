import discord
from discord import app_commands
from discord.ext import tasks
import os
import io
import csv
import sqlite3
import aiohttp
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

TOKEN = os.environ["DISCORD_TOKEN"]
STATUS_CHANNEL_ID = int(os.environ["STATUS_CHANNEL_ID"])

# ถ้ามี CenterX API ให้ push ข้อมูลเข้า ใส่ URL + secret ตรงนี้ (เว้นว่างได้ถ้ายังไม่ทำ)
CENTERX_PUSH_URL = os.environ.get("CENTERX_PUSH_URL", "")
CENTERX_API_SECRET = os.environ.get("CENTERX_API_SECRET", "")

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

# =========================================
# CONFIG: Role ID สินค้า
# =========================================
PRODUCT_ROLES = {
    1439625441244745769: "SUPPORTX",
    1486767602448732361: "JUNIORX",
    1455585072546713681: "INSIDEX CONFIG",
    1438409167542161469: "BOOST PRO",
    1438409059811197049: "BOOST ADVANCE",
    1438407747308621844: "BOOST BASIC",
    1506527234263879681: "GOATX",
    1480106992834969733: "ULTIMATEXPLUS 1.5",
    1457776903543853109: "ULTIMATEXPLUS",
    1480106764631412797: "ULTIMATEX 1.5",
    1446414620800712796: "ULTIMATEX",
    1488950562396438728: "SHX V.2 1.3",
    1441660472054120521: "SHX V.2",
    1435870349857263746: "SHX V.1",
    1435870475463954512: "DOTA V.1",
    1476883504372514958: "RESHADE 1 YEAR",
    1456301230459719711: "ROAD MOD",
    1441313309264580639: "BOOST STD",
    1455053310389391553: "TASK BAR 7",
    1440407277336133744: "RESHADE",
    1440746095238971533: "RESHADE MORETIME",
    1439965131575525508: "RESHADE DOTA V.1",
    1439969258363818077: "RESHADE DOTA V.2",
    1439969707229974640: "RESHADE DOTA WF",
    1439969849324343317: "RESHADE DOTA V3",
    1457404779931242516: "RESHADE DOTA SUNS",
    1445038948593307769: "RESHADE DOTA BW",
    1481664041075343471: "RESHADE DOTA INLUV 01",
    1481664328821375086: "RESHADE DOTA INLUV 02",
    1487500673279852615: "RESHADE DOTA INLUV 03",
    1495412128981582047: "RESHADE DOTA INLUV 04",
}

STAFF_ROLES = {
    1477555604200489042: "OWNERX",
    1508835906369618091: "TICKET",
}

LOG_CHANNEL_ID = 1522838181047832636
SALES_LOG_CHANNEL_ID = LOG_CHANNEL_ID  # แจ้งเตือนยศใหม่เข้าห้องเดียวกัน แก้แยกได้ถ้าต้องการ

BANGKOK_TZ = ZoneInfo("Asia/Bangkok")
DB_PATH = "insidex_rolestats.db"


# =========================================
# DATABASE: เก็บ snapshot รายวัน + history
# =========================================
def db_init():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS role_snapshots (
            snapshot_date TEXT NOT NULL,
            role_id INTEGER NOT NULL,
            role_name TEXT NOT NULL,
            member_count INTEGER NOT NULL,
            PRIMARY KEY (snapshot_date, role_id)
        )
    """)
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


def db_save_snapshot(snapshot_date: str, product_counts):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    for name, role_id, count in product_counts:
        cur.execute("""
            INSERT INTO role_snapshots (snapshot_date, role_id, role_name, member_count)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(snapshot_date, role_id) DO UPDATE SET member_count=excluded.member_count
        """, (snapshot_date, role_id, name, count))
    conn.commit()
    conn.close()


def db_get_snapshot(snapshot_date: str):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT role_id, role_name, member_count FROM role_snapshots WHERE snapshot_date = ?", (snapshot_date,))
    rows = cur.fetchall()
    conn.close()
    return {role_id: (name, count) for role_id, name, count in rows}


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
# ฟังก์ชันรวบรวมข้อมูล rolestats
# =========================================
def build_role_stats(guild: discord.Guild):
    product_counts = []
    staff_counts = []

    for role_id, name in PRODUCT_ROLES.items():
        role = guild.get_role(role_id)
        count = len(role.members) if role else 0
        product_counts.append((name, role_id, count))

    for role_id, name in STAFF_ROLES.items():
        role = guild.get_role(role_id)
        count = len(role.members) if role else 0
        staff_counts.append((name, role_id, count))

    product_counts.sort(key=lambda x: x[2], reverse=True)
    staff_counts.sort(key=lambda x: x[2], reverse=True)

    product_role_id_set = set(PRODUCT_ROLES.keys())
    total_members = guild.member_count
    no_product_role_count = 0
    multi_product_count = 0

    for member in guild.members:
        if member.bot:
            continue
        owned = [r.id for r in member.roles if r.id in product_role_id_set]
        if len(owned) == 0:
            no_product_role_count += 1
        elif len(owned) > 1:
            multi_product_count += 1

    return {
        "product_counts": product_counts,
        "staff_counts": staff_counts,
        "total_members": total_members,
        "no_product_role_count": no_product_role_count,
        "multi_product_count": multi_product_count,
    }


def build_summary_embed(guild: discord.Guild, stats: dict) -> discord.Embed:
    total = stats["total_members"]
    lines = []
    for name, role_id, count in stats["product_counts"]:
        if count == 0:
            continue
        pct = (count / total * 100) if total else 0
        lines.append(f"**{name}** — {count} คน ({pct:.1f}%)")

    description = "\n".join(lines) if lines else "ไม่พบสมาชิกที่มียศสินค้า"
    if len(description) > 4000:
        description = description[:4000] + "\n... (ตัดรายการเนื่องจากยาวเกินไป)"

    embed = discord.Embed(title="📊 สรุปยศสินค้า — INSIDEX", description=description, color=0x6366F1)

    staff_lines = [f"{name} — {count} คน" for name, _, count in stats["staff_counts"]]
    if staff_lines:
        embed.add_field(name="🛠️ ยศทีมงาน", value="\n".join(staff_lines), inline=False)

    embed.add_field(
        name="👥 ภาพรวมสมาชิก",
        value=(
            f"สมาชิกทั้งหมด: **{total}** คน\n"
            f"ยังไม่มียศสินค้าเลย: **{stats['no_product_role_count']}** คน\n"
            f"มีมากกว่า 1 สินค้า (ลูกค้าประจำ): **{stats['multi_product_count']}** คน"
        ),
        inline=False,
    )
    embed.set_footer(text="INSIDEX • Role Stats")
    embed.timestamp = discord.utils.utcnow()
    return embed


def build_csv_file(guild: discord.Guild, stats: dict) -> discord.File:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["ประเภท", "ชื่อยศ", "Role ID", "จำนวนคน", "% ของสมาชิกทั้งหมด"])
    total = stats["total_members"]
    for name, role_id, count in stats["product_counts"]:
        pct = (count / total * 100) if total else 0
        writer.writerow(["สินค้า", name, role_id, count, f"{pct:.2f}%"])
    for name, role_id, count in stats["staff_counts"]:
        writer.writerow(["สตาฟฟ์", name, role_id, count, ""])
    writer.writerow([])
    writer.writerow(["สมาชิกทั้งหมด", "", "", total, ""])
    writer.writerow(["ไม่มียศสินค้าเลย", "", "", stats["no_product_role_count"], ""])
    writer.writerow(["มีมากกว่า 1 สินค้า", "", "", stats["multi_product_count"], ""])
    buffer.seek(0)
    file_bytes = io.BytesIO(buffer.getvalue().encode("utf-8-sig"))
    filename = f"rolestats_{datetime.now(BANGKOK_TZ).strftime('%Y-%m-%d')}.csv"
    return discord.File(file_bytes, filename=filename)


async def push_to_centerx(snapshot_date: str, stats: dict):
    """ส่งข้อมูลเข้า CenterX dashboard ถ้าตั้งค่า URL ไว้"""
    if not CENTERX_PUSH_URL:
        return
    payload = {
        "date": snapshot_date,
        "products": [{"role_id": rid, "name": n, "count": c} for n, rid, c in stats["product_counts"]],
        "total_members": stats["total_members"],
        "no_product_role_count": stats["no_product_role_count"],
        "multi_product_count": stats["multi_product_count"],
    }
    headers = {"Authorization": f"Bearer {CENTERX_API_SECRET}"} if CENTERX_API_SECRET else {}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(CENTERX_PUSH_URL, json=payload, headers=headers, timeout=10) as resp:
                if resp.status >= 300:
                    print(f"[CenterX push] failed: {resp.status}")
    except Exception as e:
        print(f"[CenterX push] error: {e}")


# =========================================
# on_ready
# =========================================
@client.event
async def on_ready():
    tree.add_command(rolestats_group)
    await tree.sync()
    await client.change_presence(activity=discord.CustomActivity(name="🟢 X STATUS"))
    if not midnight_rolestats_post.is_running():
        midnight_rolestats_post.start()
    if not status_auto_reset_check.is_running():
        status_auto_reset_check.start()
    print(f"Bot ready : {client.user}")


# =========================================
# on_member_update: แจ้งเตือนยศสินค้าใหม่แบบ real-time
# =========================================
@client.event
async def on_member_update(before: discord.Member, after: discord.Member):
    before_role_ids = {r.id for r in before.roles}
    after_role_ids = {r.id for r in after.roles}
    new_role_ids = after_role_ids - before_role_ids

    new_product_roles = [rid for rid in new_role_ids if rid in PRODUCT_ROLES]
    if not new_product_roles:
        return

    channel = client.get_channel(SALES_LOG_CHANNEL_ID)
    if not channel:
        return

    for role_id in new_product_roles:
        product_name = PRODUCT_ROLES[role_id]
        embed = discord.Embed(
            title="🛒 ลูกค้าใหม่ได้รับยศสินค้า",
            description=f"{after.mention} ได้รับยศ **{product_name}**",
            color=0x39FF14,
        )
        embed.set_thumbnail(url=after.display_avatar.url)
        embed.set_footer(text="INSIDEX • Sales Notification")
        embed.timestamp = discord.utils.utcnow()
        await channel.send(embed=embed)


# =========================================
# /setstatus (เพิ่ม log การเปลี่ยนสถานะ)
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
# /rolestats group
# =========================================
rolestats_group = app_commands.Group(name="rolestats", description="สถิติยศสมาชิก INSIDEX")


@rolestats_group.command(name="view", description="ดูสรุปจำนวนสมาชิกตามยศสินค้า")
async def rolestats_view(interaction: discord.Interaction):
    await interaction.response.defer(thinking=True)
    guild = interaction.guild
    await guild.chunk()
    stats = build_role_stats(guild)
    embed = build_summary_embed(guild, stats)
    await interaction.followup.send(embed=embed)


@rolestats_group.command(name="export", description="ส่งออกสถิติยศเป็นไฟล์ CSV")
async def rolestats_export(interaction: discord.Interaction):
    await interaction.response.defer(thinking=True)
    guild = interaction.guild
    await guild.chunk()
    stats = build_role_stats(guild)
    file = build_csv_file(guild, stats)
    await interaction.followup.send(content="📄 ไฟล์สรุปสถิติยศ", file=file)


@rolestats_group.command(name="compare", description="เทียบยอดยศวันนี้กับย้อนหลัง")
@app_commands.describe(ช่วงเวลา="เทียบกับกี่วันก่อน")
@app_commands.choices(ช่วงเวลา=[
    app_commands.Choice(name="เมื่อวาน (1 วัน)", value=1),
    app_commands.Choice(name="สัปดาห์ก่อน (7 วัน)", value=7),
    app_commands.Choice(name="เดือนก่อน (30 วัน)", value=30),
])
async def rolestats_compare(interaction: discord.Interaction, ช่วงเวลา: app_commands.Choice[int]):
    await interaction.response.defer(thinking=True)
    guild = interaction.guild
    await guild.chunk()

    days_ago = ช่วงเวลา.value
    stats = build_role_stats(guild)
    past_date = (datetime.now(BANGKOK_TZ) - timedelta(days=days_ago)).strftime("%Y-%m-%d")

    past_snapshot = db_get_snapshot(past_date)

    if not past_snapshot:
        await interaction.followup.send(
            f"❌ ไม่พบข้อมูลย้อนหลัง {days_ago} วัน (วันที่ {past_date})\n"
            f"ระบบเก็บ snapshot ทุกเที่ยงคืน ต้องรอให้มีข้อมูลสะสมก่อนถึงจะเทียบได้ครับ"
        )
        return

    lines = []
    for name, role_id, current_count in stats["product_counts"]:
        past_name, past_count = past_snapshot.get(role_id, (name, 0))
        diff = current_count - past_count
        if diff > 0:
            arrow = f"▲ +{diff}"
        elif diff < 0:
            arrow = f"▼ {diff}"
        else:
            arrow = "— 0"
        if current_count == 0 and past_count == 0:
            continue
        lines.append(f"**{name}** — {current_count} คน ({arrow})")

    description = "\n".join(lines) if lines else "ไม่มีข้อมูลเปรียบเทียบ"
    if len(description) > 4000:
        description = description[:4000] + "\n... (ตัดรายการเนื่องจากยาวเกินไป)"

    embed = discord.Embed(
        title=f"📈 เทียบยอดยศ: วันนี้ vs {days_ago} วันก่อน ({past_date})",
        description=description,
        color=0x6366F1,
    )
    embed.set_footer(text="INSIDEX • Role Stats Compare")
    embed.timestamp = discord.utils.utcnow()
    await interaction.followup.send(embed=embed)


# =========================================
# Auto-post ทุกเที่ยงคืน: บันทึก snapshot + โพสต์สรุป + push CenterX
# =========================================
@tasks.loop(time=time(hour=0, minute=0, tzinfo=BANGKOK_TZ))
async def midnight_rolestats_post():
    today_str = datetime.now(BANGKOK_TZ).strftime("%Y-%m-%d")

    for guild in client.guilds:
        await guild.chunk()
        stats = build_role_stats(guild)

        # 1) บันทึก snapshot ลง DB (ใช้เป็นฐานสำหรับ /rolestats compare ในอนาคต)
        db_save_snapshot(today_str, stats["product_counts"])

        # 2) โพสต์สรุปเข้าห้อง log
        embed = build_summary_embed(guild, stats)
        file = build_csv_file(guild, stats)
        channel = client.get_channel(LOG_CHANNEL_ID)
        if channel:
            await channel.send(embed=embed, file=file)

        # 3) push เข้า CenterX ถ้าตั้งค่า ENV ไว้ (CENTERX_PUSH_URL)
        await push_to_centerx(today_str, stats)


client.run(TOKEN)