import discord
from discord import app_commands
import os

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



@client.event
async def on_ready():
    await tree.sync()
    await client.change_presence(activity=discord.CustomActivity(name="🟢 X STATUS"))
    print(f"Bot ready : {client.user}")


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
    
@tree.command(name="rolestats", description="ดูจำนวนสมาชิกที่มีแต่ละยศในเซิร์ฟเวอร์")
async def rolestats(interaction: discord.Interaction):
    await interaction.response.defer(thinking=True)

    guild = interaction.guild
    # ต้อง fetch members ให้ครบก่อน (ต้องเปิด Server Members Intent ใน Dev Portal)
    await guild.chunk()

    # นับจำนวนคนต่อยศ ข้าม @everyone
    role_counts = []
    for role in guild.roles:
        if role.is_default():
            continue
        count = len(role.members)
        if count > 0:
            role_counts.append((role, count))

    # เรียงจากคนเยอะไปน้อย
    role_counts.sort(key=lambda x: x[1], reverse=True)

    if not role_counts:
        await interaction.followup.send("❌ ไม่พบยศที่มีสมาชิกครับ")
        return

    lines = [f"{role.mention} — **{count}** คน" for role, count in role_counts]

    # แบ่งหน้าถ้ายศเยอะเกิน (embed description limit ~4096 ตัวอักษร)
    description = "\n".join(lines)
    if len(description) > 4000:
        description = description[:4000] + "\n... (ตัดรายการเนื่องจากยาวเกินไป)"

    embed = discord.Embed(
        title="📊 สรุปจำนวนสมาชิกตามยศ",
        description=description,
        color=0x6366F1,
    )
    embed.set_footer(text=f"รวมทั้งหมด {len(guild.roles) - 1} ยศ • สมาชิกทั้งหมด {guild.member_count} คน")
    embed.timestamp = discord.utils.utcnow()

    await interaction.followup.send(embed=embed)


client.run(TOKEN)