import discord
from discord.ext import commands
from discord import app_commands
import json
import os

ROLE_SETTINGS_FILE = 'json/role_settings.json'

def load_role_settings():
    if not os.path.exists('json'):
        os.makedirs('json')
    if os.path.exists(ROLE_SETTINGS_FILE):
        with open(ROLE_SETTINGS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

def save_role_settings(settings):
    with open(ROLE_SETTINGS_FILE, 'w', encoding='utf-8') as f:
        json.dump(settings, f, indent=4, ensure_ascii=False)

class RoleButton(discord.ui.Button):
    def __init__(self, emoji, role_id):
        super().__init__(
            emoji=emoji,
            style=discord.ButtonStyle.secondary,
            custom_id=f"role_giver_{role_id}"
        )
        self.role_id = role_id

    async def callback(self, interaction: discord.Interaction):
        role = interaction.guild.get_role(self.role_id)
        if not role:
            return await interaction.response.send_message("❌ ไม่พบยศนี้ในระบบ", ephemeral=True)

        # Logic สำหรับ Mutual Exclusion (เพศ)
        male_id = os.getenv('MALE_ROLE_ID')
        female_id = os.getenv('FEMALE_ROLE_ID')
        
        extra_msg = ""
        if str(self.role_id) == male_id:
            # ถ้าเลือกชาย ให้เช็คและลบหญิง
            female_role = interaction.guild.get_role(int(female_id)) if female_id and female_id != '0' else None
            if female_role and female_role in interaction.user.roles:
                await interaction.user.remove_roles(female_role)
                extra_msg = f" (และนำยศ **{female_role.name}** ออกให้แล้ว)"
        elif str(self.role_id) == female_id:
            # ถ้าเลือกหญิง ให้เช็คและลบชาย
            male_role = interaction.guild.get_role(int(male_id)) if male_id and male_id != '0' else None
            if male_role and male_role in interaction.user.roles:
                await interaction.user.remove_roles(male_role)
                extra_msg = f" (และนำยศ **{male_role.name}** ออกให้แล้ว)"

        if role in interaction.user.roles:
            await interaction.user.remove_roles(role)
            await interaction.response.send_message(f"✅ นำยศ **{role.name}** ออกแล้ว", ephemeral=True)
        else:
            await interaction.user.add_roles(role)
            await interaction.response.send_message(f"✅ เพิ่มยศ **{role.name}** ให้แล้ว{extra_msg}", ephemeral=True)

class PersistentRoleGiverView(discord.ui.View):
    def __init__(self, settings):
        super().__init__(timeout=None)
        for item in settings:
            self.add_item(RoleButton(emoji=item['emoji'], role_id=item['role_id']))

class AddRoleModal(discord.ui.Modal, title="เพิ่มยศในรายการ"):
    emoji = discord.ui.TextInput(label="อีโมจิ (Emoji)", placeholder="เช่น 🎫, 🎮, ❤️", required=True)
    
    def __init__(self, role: discord.Role):
        super().__init__()
        self.role = role

    async def on_submit(self, interaction: discord.Interaction):
        settings = load_role_settings()
        
        # Check if emoji or role already exists
        if any(s['emoji'] == self.emoji.value for s in settings):
            return await interaction.response.send_message("❌ อีโมจินี้ถูกใช้งานไปแล้ว", ephemeral=True)
        
        settings.append({
            "emoji": self.emoji.value,
            "role_id": self.role.id,
            "role_name": self.role.name
        })
        save_role_settings(settings)
        
        await interaction.response.send_message(f"✅ บันทึกการตั้งค่า ยศ **{self.role.name}** คู่กับอีโมจิ {self.emoji.value} เรียบร้อยแล้ว", ephemeral=True)

class RoleSettingsView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)

    @discord.ui.select(
        placeholder="เลือกการจัดการ...",
        options=[
            discord.SelectOption(label="เพิ่มการตั้งค่า", description="เพิ่มคู่ Emoji และ Role", value="add", emoji="➕"),
            discord.SelectOption(label="ลบการตั้งค่า", description="ลบคู่ Emoji และ Role ออกจากระบบ", value="remove", emoji="➖")
        ]
    )
    async def select_callback(self, interaction: discord.Interaction, select: discord.ui.Select):
        if select.values[0] == "add":
            # Show role selection first
            await interaction.response.send_message("กรุณาระบุยศที่ต้องการเพิ่ม (เลือกจากรายการด้านล่าง)", view=discord.ui.View().add_item(RoleSelect()), ephemeral=True)
        else:
            settings = load_role_settings()
            if not settings:
                return await interaction.response.send_message("❌ ยังไม่มีการตั้งค่าใดๆ", ephemeral=True)
            
            view = discord.ui.View().add_item(RemoveRoleSelect(settings))
            await interaction.response.send_message("เลือกรายการที่ต้องการลบทิ้ง:", view=view, ephemeral=True)

class RoleSelect(discord.ui.RoleSelect):
    def __init__(self):
        super().__init__(placeholder="เลือก Role...", min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction):
        role = self.values[0]
        await interaction.response.send_modal(AddRoleModal(role))

class RemoveRoleSelect(discord.ui.Select):
    def __init__(self, settings):
        options = [
            discord.SelectOption(label=f"{s['role_name']}", value=str(s['role_id']), emoji=s['emoji'])
            for s in settings
        ]
        super().__init__(placeholder="เลือกรายการที่จะลบ...", options=options)

    async def callback(self, interaction: discord.Interaction):
        settings = load_role_settings()
        new_settings = [s for s in settings if str(s['role_id']) != self.values[0]]
        save_role_settings(new_settings)
        await interaction.response.send_message("✅ ลบรายการเรียบร้อยแล้ว", ephemeral=True)

class RolesCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="set_rolegiver", description="[Admin] ตั้งค่า Emoji และ Role สำหรับระบรับยศ")
    @app_commands.default_permissions(administrator=True)
    async def set_rolegiver(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="⚙️ ตั้งค่าระบบรับยศ (Role Giver)",
            description="คุณสามารถ เพิ่ม หรือ ลบ คู่ Emoji และ Role ได้จากเมนูด้านล่างนี้ครับ",
            color=discord.Color.blurple()
        )
        await interaction.response.send_message(embed=embed, view=RoleSettingsView(), ephemeral=True)

    @app_commands.command(name="setup_rolegiver", description="[Admin] ส่งกล่องรับยศไปยังห้องที่กำหนด")
    @app_commands.describe(channel="ห้องที่ต้องการให้บอทส่งกล่องรับยศ")
    @app_commands.default_permissions(administrator=True)
    async def setup_rolegiver(self, interaction: discord.Interaction, channel: discord.TextChannel):
        settings = load_role_settings()
        if not settings:
            return await interaction.response.send_message("❌ ยังไม่มีการตั้งค่าใดๆ กรุณาใช้ `/set_rolegiver` ก่อนครับ", ephemeral=True)

        embed = discord.Embed(
            title="🎫 เลือกรับ Role ที่คุณต้องการ",
            description="กดปุ่มด้านล่างเพื่อ รับ หรือ คืน ยศตามที่คุณต้องการได้เลยครับ!",
            color=discord.Color.blurple()
        )
        embed.set_footer(text="Thailand System • Role Giver Service")
        
        await channel.send(embed=embed, view=PersistentRoleGiverView(settings))
        await interaction.response.send_message(f"✅ ส่งกล่องรับยศที่ห้อง {channel.mention} เรียบร้อยแล้ว", ephemeral=True)

async def setup(bot):
    await bot.add_cog(RolesCog(bot))
