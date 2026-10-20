"""بوت ديوان شعري - ديسكورد
التثبيت:  pip install discord.py
التشغيل:  DISCORD_TOKEN=xxxx python discord_bot.py
يستخدم نفس ملف poems.json
"""
import datetime
import json
import os
import random

import discord
from discord import app_commands
from discord.ext import tasks

with open("poems.json", encoding="utf-8") as f:
    POEMS = json.load(f)

POETS = sorted({p["poet"] for p in POEMS})

# القصائد اللي لها نص تنفع لقصيدة اليوم
WITH_TEXT = [i for i, p in enumerate(POEMS) if p["text"]]

# يحفظ روم قصيدة اليوم لكل سيرفر. على Railway اجعل DATA_DIR يشير لمسار الـ Volume (مثل /data)
DATA_DIR = os.environ.get("DATA_DIR", ".")
try:
    os.makedirs(DATA_DIR, exist_ok=True)
except OSError:
    DATA_DIR = "."
CONFIG_FILE = os.path.join(DATA_DIR, "daily.json")

# وقت النشر: 9 صباحًا بتوقيت +3 (السعودية/الكويت/قطر). للإمارات غيّر hours=4
DAILY_TIME = datetime.time(hour=9, minute=0, tzinfo=datetime.timezone(datetime.timedelta(hours=3)))


def load_config() -> dict:
    try:
        with open(CONFIG_FILE, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def save_config(cfg: dict):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f)


class DiwanClient(discord.Client):
    def __init__(self):
        super().__init__(intents=discord.Intents.default())
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        await self.tree.sync()
        daily_poem.start()


client = DiwanClient()
tree = client.tree


def poem_embed(i: int) -> discord.Embed:
    p = POEMS[i]
    e = discord.Embed(
        title=f"📜 {p['title']}",
        description=p["text"] or "(النص الكامل قيد الإضافة)",
        color=0x8B6F47,
    )
    e.set_author(name=p["poet"])
    e.set_footer(text=p["era"])
    return e


class PoemSelect(discord.ui.Select):
    def __init__(self, ids):
        options = [
            discord.SelectOption(
                label=POEMS[i]["title"][:100],
                value=str(i),
                description=POEMS[i]["poet"][:100],
            )
            for i in ids[:25]
        ]
        super().__init__(placeholder="اختر قصيدة...", options=options)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_message(embed=poem_embed(int(self.values[0])))


class PoemView(discord.ui.View):
    def __init__(self, ids):
        super().__init__(timeout=300)
        self.add_item(PoemSelect(ids))


@tree.command(name="poets", description="قائمة الشعراء في الديوان")
async def poets(interaction: discord.Interaction):
    e = discord.Embed(
        title=f"📚 الديوان: {len(POEMS)} قصيدة لـ {len(POETS)} شاعر",
        description="\n".join(f"• {name}" for name in POETS),
        color=0x8B6F47,
    )
    await interaction.response.send_message(embed=e)


@tree.command(name="poet", description="قصائد شاعر معين")
@app_commands.describe(name="اسم الشاعر")
async def poet(interaction: discord.Interaction, name: str):
    ids = [i for i, p in enumerate(POEMS) if p["poet"] == name]
    if not ids:
        await interaction.response.send_message("ما لقيت هذا الشاعر، اختره من القائمة.", ephemeral=True)
        return
    await interaction.response.send_message(f"قصائد **{name}**:", view=PoemView(ids))


@poet.autocomplete("name")
async def poet_autocomplete(interaction: discord.Interaction, current: str):
    return [app_commands.Choice(name=n, value=n) for n in POETS if current in n][:25]


@tree.command(name="poem", description="اعرض قصيدة بالعنوان")
@app_commands.describe(title="عنوان القصيدة")
async def poem(interaction: discord.Interaction, title: str):
    if not title.isdigit() or int(title) >= len(POEMS):
        await interaction.response.send_message("اختر القصيدة من القائمة المقترحة.", ephemeral=True)
        return
    await interaction.response.send_message(embed=poem_embed(int(title)))


@poem.autocomplete("title")
async def poem_autocomplete(interaction: discord.Interaction, current: str):
    out = []
    for i, p in enumerate(POEMS):
        label = f"{p['title']} - {p['poet']}"
        if current in label:
            out.append(app_commands.Choice(name=label[:100], value=str(i)))
    return out[:25]


@tree.command(name="random", description="قصيدة عشوائية")
async def random_poem(interaction: discord.Interaction):
    await interaction.response.send_message(embed=poem_embed(random.choice(WITH_TEXT)))


@tree.command(name="search", description="بحث في الديوان بكلمة")
@app_commands.describe(term="كلمة من اسم الشاعر أو العنوان أو النص")
async def search(interaction: discord.Interaction, term: str):
    ids = [i for i, p in enumerate(POEMS)
           if term in p["poet"] or term in p["title"] or term in p["text"]]
    if not ids:
        await interaction.response.send_message("ما لقيت نتيجة، جرّب كلمة ثانية.", ephemeral=True)
        return
    await interaction.response.send_message(f"نتائج البحث ({len(ids)}):", view=PoemView(ids))


@tasks.loop(time=DAILY_TIME)
async def daily_poem():
    # نفس القصيدة لكل السيرفرات في اليوم الواحد
    i = WITH_TEXT[datetime.date.today().toordinal() % len(WITH_TEXT)]
    embed = poem_embed(i)
    embed.title = f"🌅 قصيدة اليوم: {POEMS[i]['title']}"
    for guild_id, channel_id in load_config().items():
        channel = client.get_channel(channel_id)
        if channel is None:
            continue
        try:
            await channel.send(embed=embed)
        except discord.HTTPException:
            pass  # ما عنده صلاحية أو الروم انحذف


@tree.command(name="setdaily", description="حدد هذا الروم لقصيدة اليوم")
@app_commands.guild_only()
@app_commands.default_permissions(manage_guild=True)
async def setdaily(interaction: discord.Interaction):
    cfg = load_config()
    cfg[str(interaction.guild_id)] = interaction.channel_id
    save_config(cfg)
    await interaction.response.send_message("تم ✅ بتنزل قصيدة اليوم في هذا الروم كل صباح.")


@tree.command(name="stopdaily", description="إيقاف قصيدة اليوم في هذا السيرفر")
@app_commands.guild_only()
@app_commands.default_permissions(manage_guild=True)
async def stopdaily(interaction: discord.Interaction):
    cfg = load_config()
    cfg.pop(str(interaction.guild_id), None)
    save_config(cfg)
    await interaction.response.send_message("تم الإيقاف.")


client.run(os.environ["DISCORD_TOKEN"])
