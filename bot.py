import discord
from discord import app_commands
from discord.ext import tasks
import os
import io
import csv
from datetime import datetime, time
from zoneinfo import ZoneInfo

TOKEN = os.environ["DISCORD_TOKEN"]
STATUS_CHANNEL_ID = int(os.environ["STATUS_CHANNEL_ID"])

intents = discord.Intents.default()
intents.members = True
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

STATUS_STORED_MESSAGE_ID = None
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

# CONFIG: Role ID สตาฟฟ์/ทีมงาน
STAFF_ROLES = {
    1477555604200489042: "OWNERX",
    1508835906369618091: "TICKET",
}

# CONFIG: ห้อง log สำหรับโพสต์สรุปอัตโนมัติทุกเที่ยงคืน
LOG_CHANNEL_ID = 1522838181047832636

BANGKOK_TZ = ZoneInfo("Asia/Bangkok")


# =========================================
# ฟังก์ชันช่วยรวบรวมข้อมูล rolestats
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
    multi_product_breakdown = {}

    for member in guild.members:
        if member.bot:
            continue
        owned = [r.id for r in member.roles if r.id in product_role_id_set]
        if len(owned) == 0:
            no_product_role_count += 1
        elif len(owned) > 1:
            multi_product_count += 1
            multi_product_breakdown[len(owned)] = multi_product_breakdown.get(len(owned), 0) + 1

    return {
        "product_counts": product_counts,
        "staff_counts": staff_counts,
        "total_members": total_members,
        "no_product_role_count": no_product_role_count,
        "multi_product_count": multi_product_count,
        "multi_product_breakdown": multi_product_breakdown,
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

    embed = discord.Embed(
        title="📊 สรุปยศสินค้า — INSIDEX",
        description=description,
        color=0x6366F1,
    )

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
    writer.writerow(["สรุป", "", "", "", ""])
    writer.writerow(["สมาชิกทั้งหมด", "", "", total, ""])
    writer.writerow(["ไม่มียศสินค้าเลย", "", "", stats["no_product_role_count"], ""])
    writer.writerow(["มีมากกว่า 1 สินค้า", "", "", stats["multi_product_count"], ""])

    buffer.seek(0)
    file_bytes = io.BytesIO(buffer.getvalue().encode("utf-8-sig"))
    filename = f"rolestats_{datetime.now(BANGKOK_TZ).strftime('%Y-%m-%d')}.csv"
    return discord.File(file_bytes, filename=filename)


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
    global STATUS_STORED_MESSAGE_ID

    cfg = STATUS_CONFIG[สถานะ]
    channel = client.get_channel(STATUS_CHANNEL_ID)

    embed = discord.Embed(
        title=f"{cfg['emoji']}  {cfg['title']}",
        description=cfg["desc"],
        color=cfg["color"],
    )
    embed.set_author(name="INSIDEX STATUS", icon_url=interaction.guild.icon.url if interaction.guild.icon else discord.Embed.Empty)
    embed.set_image(url=THUMBNAIL_URL)
    embed.set_footer(text=cfg["footer"])
    embed.timestamp = discord.utils.utcnow()

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
# /rolestats view, /rolestats export
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


# =========================================
# Auto-post ทุกเที่ยงคืน (เวลาไทย)
# =========================================
@tasks.loop(time=time(hour=0, minute=0, tzinfo=BANGKOK_TZ))
async def midnight_rolestats_post():
    for guild in client.guilds:
        await guild.chunk()
        stats = build_role_stats(guild)
        embed = build_summary_embed(guild, stats)
        file = build_csv_file(guild, stats)

        channel = client.get_channel(LOG_CHANNEL_ID)
        if channel:
            await channel.send(embed=embed, file=file)


client.run(TOKEN)