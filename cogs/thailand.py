import discord
from discord.ext import commands
from discord import app_commands
import json
import os
import random
import asyncio

PROVINCES_FILE = "json/provinces.json"
LOCATIONS_FILE = "json/user_locations.json"
COUNTRIES_FILE = "json/countries.json"

class CountryInputModal(discord.ui.Modal, title="ระบุประเทศที่ต้องการเดินทางไป"):
    country_name = discord.ui.TextInput(
        label="ชื่อประเทศ (ไทย หรือ อังกฤษ)",
        placeholder="ตัวอย่าง: ญี่ปุ่น หรือ Japan",
        min_length=2,
        max_length=50
    )

    def __init__(self, cog, vehicle: str):
        super().__init__()
        self.cog = cog
        self.vehicle = vehicle

    async def on_submit(self, interaction: discord.Interaction):
        input_value = self.country_name.value.strip()
        
        # ค้นหาประเทศ
        found_country = None
        for country in self.cog.countries:
            if input_value.lower() == country["thai_name"].lower() or input_value.lower() == country["english_name"].lower():
                found_country = country["thai_name"]
                break
        
        if not found_country:
            await interaction.response.send_message(f"<:w_:1459388961943457934> ไม่พบประเทศชื่อ '{input_value}' ในระบบ กรุณาลองใหม่อีกครั้งครับ", ephemeral=True)
            return

        user_id = str(interaction.user.id)
        
        # เช็คว่ากำลังเดินทางอยู่ไหม
        if user_id in self.cog.traveling_users:
            await interaction.response.send_message("<:w_:1459388961943457934> คุณกำลังอยู่ระหว่างการเดินทาง กรุณารอสักครู่ครับ!", ephemeral=True)
            return

        self.cog.traveling_users.add(user_id)
        
        # กำหนดช่วงเวลาตามยานพาหนะ
        if self.vehicle == "เดินเท้า":
            delay = random.randint(80, 120)
            action_text = "กำลังเดินเท้าไป"
        elif self.vehicle == "รถยนต์/รถโดยสาร":
            delay = random.randint(30, 70)
            action_text = "กำลังนั่งรถไป"
        else: # เครื่องบิน
            delay = random.randint(5, 20)
            action_text = "กำลังบินไป"

        minutes, seconds = divmod(delay, 60)
        time_text = f"{minutes} นาที {seconds} วินาที" if minutes > 0 else f"{seconds} วินาที"
        
        await interaction.response.send_message(f"✈️ {action_text} **{found_country}**... จะใช้เวลาเดินทางประมาณ **{time_text}** กรุณารอสักครู่นะครับ", ephemeral=True)
        
        await asyncio.sleep(delay)

        target_location = f"ต่างประเทศ ({found_country})"
        self.cog.locations["users"][user_id] = target_location
        self.cog.save_locations()

        # จัดการเรื่อง Role ต่างประเทศ
        abroad_role_id = os.getenv('ABROAD_ROLE_ID')
        if abroad_role_id:
            try:
                role_id = int(abroad_role_id)
                role = interaction.guild.get_role(role_id)
                if role:
                    await interaction.user.add_roles(role)
            except Exception as e:
                print(f"Error handling abroad role: {e}")

        self.cog.traveling_users.remove(user_id)
        await interaction.followup.send(f"✈️ คุณเดินทางมาถึง **{target_location}** โดย**{self.vehicle}** เรียบร้อยแล้ว! (ใช้เวลาวน {time_text})", ephemeral=True)
        await self.cog._update_population_dashboard()

class ThailandMap(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.load_data()
        self.traveling_users = set()  # เก็บรายชื่อคนกำลังเดินทาง

    # โหลดข้อมูลจังหวัดและตำแหน่งผู้เล่น
    def load_data(self):
        if not os.path.exists(PROVINCES_FILE):
             # ถ้าไม่มีไฟล์ ควรสร้างค่าเริ่มต้นไว้ แต่ตอนนี้เราถือว่ามีไฟล์แล้ว
             self.provinces = {}
        else:
            with open(PROVINCES_FILE, "r", encoding="utf-8") as f:
                self.provinces = json.load(f)

        if not os.path.exists(COUNTRIES_FILE):
            self.countries = []
        else:
            with open(COUNTRIES_FILE, "r", encoding="utf-8") as f:
                self.countries = json.load(f)

        if not os.path.exists(LOCATIONS_FILE):
            self.locations = {"users": {}, "dashboard": None}
            self.save_locations()
        else:
            with open(LOCATIONS_FILE, "r", encoding="utf-8") as f:
                self.locations = json.load(f)
                # Migration to new structure if needed
                if "users" not in self.locations:
                    old_data = self.locations
                    self.locations = {"users": old_data, "dashboard": None}
                    self.save_locations()

    # บันทึกตำแหน่งผู้เล่น
    def save_locations(self):
        with open(LOCATIONS_FILE, "w", encoding="utf-8") as f:
            json.dump(self.locations, f, indent=4)

    @app_commands.command(name="travel", description="เดินทางไปยังจังหวัดต่างๆ หรือ ต่างประเทศ")
    @app_commands.describe(
        province="ชื่อจังหวัดที่ต้องการไป หรือ 'ต่างประเทศ'",
        vehicle="เลือกยานพาหนะในการเดินทาง"
    )
    @app_commands.choices(vehicle=[
        app_commands.Choice(name="👣 เดินเท้า (ช้ามาก)", value="เดินเท้า"),
        app_commands.Choice(name="🚗 รถยนต์/รถโดยสาร (ปกติ)", value="รถยนต์/รถโดยสาร"),
        app_commands.Choice(name="✈️ เครื่องบิน (เร็วที่สุด)", value="เครื่องบิน")
    ])
    @app_commands.checks.cooldown(1, 60, key=lambda i: i.user.id)
    async def travel(self, interaction: discord.Interaction, province: str, vehicle: str):
        # Special case: ต่างประเทศ
        if province == "ต่างประเทศ":
            await interaction.response.send_modal(CountryInputModal(self, vehicle))
            return

        target_province = None
        # Find province (Thai only as per previous setup)
        for key in self.provinces.keys():
            if province.lower() == key.lower():
                target_province = key
                break
        
        if not target_province:
            await interaction.response.send_message(f"<:w_:1459388961943457934> ไม่พบจังหวัดหรือพื้นที่: {province}", ephemeral=True)
            return

        user_id = str(interaction.user.id)
        
        # เช็คว่ากำลังเดินทางอยู่ไหม
        if user_id in self.traveling_users:
            await interaction.response.send_message("<:w_:1459388961943457934> คุณกำลังอยู่ระหว่างการเดินทาง กรุณารอสักครู่ครับ!", ephemeral=True)
            return

        self.traveling_users.add(user_id)

        # กำหนดช่วงเวลาและข้อความตามยานพาหนะ
        if vehicle == "เดินเท้า":
            delay = random.randint(80, 120)
            action_text = "กำลังเดินเท้าไปยัง"
        elif vehicle == "รถยนต์/รถโดยสาร":
            delay = random.randint(30, 70)
            action_text = "กำลังขับรถ/นั่งรถไปยัง"
        else: # เครื่องบิน
            delay = random.randint(5, 20)
            action_text = "กำลังนั่งเครื่องบินไปยัง"

        minutes, seconds = divmod(delay, 60)
        time_text = f"{minutes} นาที {seconds} วินาที" if minutes > 0 else f"{seconds} วินาที"

        await interaction.response.send_message(f"{action_text} **{target_province}**... จะใช้เวลาประมาณ **{time_text}** กรุณารอนิดหนึ่งนะครับ", ephemeral=True)
        
        await asyncio.sleep(delay)

        self.locations["users"][user_id] = target_province
        self.save_locations()

        # จัดการเรื่อง Role ต่างประเทศ (เช็คและลบถ้ามี)
        abroad_role_id = os.getenv('ABROAD_ROLE_ID')
        if abroad_role_id:
            try:
                role_id = int(abroad_role_id)
                role = interaction.guild.get_role(role_id)
                if role and role in interaction.user.roles:
                    await interaction.user.remove_roles(role)
            except:
                pass

        self.traveling_users.remove(user_id)
        await interaction.followup.send(f"📍 คุณเดินทางมาถึง **{target_province}** โดย**{vehicle}** แล้ว! (ใช้เวลาเดินทาง {time_text})")
        await self._update_population_dashboard()

    @app_commands.command(name="province", description="ดูข้อมูลจังหวัดและคนที่อยู่ที่นั่น")
    @app_commands.describe(province="ชื่อจังหวัด")
    async def province_info(self, interaction: discord.Interaction, province: str):
        target_province = None
        for key in self.provinces.keys():
             if province.lower() == key.lower():
                target_province = key
                break
        
        if not target_province:
             await interaction.response.send_message(f"<:w_:1459388961943457934> ไม่พบจังหวัด: {province}", ephemeral=True)
             return

        data = self.provinces[target_province]
        
        users_here = []
        for uid, loc in self.locations["users"].items(): # Corrected to access "users" key
            if loc == target_province:
                users_here.append(uid)
        
        user_list_text = ", ".join([f"<@{uid}>" for uid in users_here]) if users_here else "ไม่มีใครอยู่เลย..."

        embed = discord.Embed(title=f"📍 {target_province}", color=discord.Color.green())
        if "image" in data and data["image"]:
            embed.set_image(url=data["image"])
        
        embed.add_field(name=f"👥 ประชากร ({len(users_here)} คน)", value=user_list_text, inline=False)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="whereami", description="เช็คว่าตอนนี้เราอยู่ที่ไหน")
    async def whereami(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)
        current_loc = self.locations["users"].get(user_id)

        if current_loc and current_loc in self.provinces:
            await interaction.response.send_message(f"📍 ตอนนี้คุณอยู่ที่: **{current_loc}**", ephemeral=True)
        else:
            await interaction.response.send_message("❓ คุณยังไม่ได้เดินทางไปไหนเลย ลองใช้ `/travel` ดูสิ!", ephemeral=True)

    @app_commands.command(name="setup_address", description="[Admin] ตั้งค่าช่องสำหรับแสดงตารางประชากร")
    @app_commands.default_permissions(administrator=True)
    async def setup_address(self, interaction: discord.Interaction, channel: discord.TextChannel):
        # ลบข้อความเก่าถ้ามี
        old_dash = self.locations.get("dashboard")
        if old_dash:
            try:
                # ลองดึง Channel จาก Cache ก่อน ถ้าไม่มีค่อย Fetch
                old_channel = self.bot.get_channel(old_dash["channel_id"]) or await self.bot.fetch_channel(old_dash["channel_id"])
                if old_channel:
                    old_msg = await old_channel.fetch_message(old_dash["message_id"])
                    await old_msg.delete()
            except:
                # ถ้าลบไม่ได้ (เช่น ข้อความถูกลบไปแล้ว) ก็ให้ข้ามไป
                pass

        embed = discord.Embed(title="📊 ตารางบันทึกประชากร (77 จังหวัด)", color=discord.Color.blue())
        embed.description = "⌛ กำลังเรียลไทม์ข้อมูล..."
        
        msg = await channel.send(embed=embed)
        
        self.locations["dashboard"] = {
            "channel_id": channel.id,
            "message_id": msg.id
        }
        self.save_locations()
        
        await self._update_population_dashboard()
        await interaction.response.send_message(f"<:c_:1459387176516190312> ตั้งค่าตารางประชากรที่ช่อง {channel.mention} เรียบร้อยแล้ว", ephemeral=True)

    async def _update_population_dashboard(self):
        dash = self.locations.get("dashboard")
        if not dash: return

        channel = self.bot.get_channel(dash["channel_id"])
        if not channel: return

        try:
            msg = await channel.fetch_message(dash["message_id"])
        except:
            return

        # นับประชากรและเก็บรายชื่อ
        pop_count = {}
        province_users = {}
        for uid, loc in self.locations["users"].items():
            pop_count[loc] = pop_count.get(loc, 0) + 1
            if loc not in province_users:
                province_users[loc] = []
            province_users[loc].append(uid)

        # เตรียมตาราง (เรียงตามคนเยอะไปน้อย)
        sorted_provinces = sorted(pop_count.keys(), key=lambda p: pop_count[p], reverse=True)
        
        if not sorted_provinces:
            description = "ขณะนี้ยังไม่มีชาวเมืองในจังหวัดใดเลย..."
        else:
            description = ""
            for p in sorted_provinces:
                pop = pop_count[p]
                users = province_users[p]
                
                # ทำ mention 3 คนแรก
                mentions = [f"<@{uid}>" for uid in users[:3]]
                mention_text = ", ".join(mentions)
                
                if len(users) > 3:
                    mention_text += " และคนอื่นๆ..."
                
                # เปลี่ยนไอคอนถ้าเป็นต่างประเทศ
                icon = "🌍" if p.startswith("ต่างประเทศ") else "📍"
                description += f"{icon} **{p}**: `{pop}` คน ({mention_text})\n"
        
        embed = discord.Embed(title="📊 ตารางบันทึกประชากร (Real-time)", color=discord.Color.blue())
        embed.description = description
        embed.timestamp = discord.utils.utcnow()
        embed.set_footer(text="อัปเดตล่าสุด")
        
        await msg.edit(embed=embed)

    # Autocomplete for province names
    @travel.autocomplete('province')
    @province_info.autocomplete('province')
    async def province_autocomplete(self, interaction: discord.Interaction, current: str):
        choices = []
        # เพิ่มตัวเลือกต่างประเทศ
        if "ต่างประเทศ".startswith(current) or current.lower() in "abroad":
            choices.append(app_commands.Choice(name="✈️ ต่างประเทศ", value="ต่างประเทศ"))

        for key in self.provinces.keys():
            if current.lower() in key.lower():
                 choices.append(app_commands.Choice(name=key, value=key))
        return choices[:25]

    # Error handler for cooldowns
    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CommandOnCooldown):
            seconds = round(error.retry_after)
            await interaction.response.send_message(
                f"⏳ ใจเย็นๆ ครับ! คุณเพิ่งเดินทางไปเอง ต้องรออีก **{seconds} วินาที** ถึงจะเดินทางได้อีกครั้ง",
                ephemeral=True
            )
        else:
            # Re-raise other errors
            raise error

async def setup(bot):
    await bot.add_cog(ThailandMap(bot))
