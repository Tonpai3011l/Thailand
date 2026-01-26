import discord
from discord.ext import commands
from discord import app_commands
import aiohttp
import json
import os

class RobloxVerifyModal(discord.ui.Modal, title="ยืนยันตัวตน"):
    username = discord.ui.TextInput(
        label="ชื่อใน Roblox",
        placeholder="ตัวอย่าง: tonpai3011l (กรุณาใช้ Username)",
        min_length=3,
        max_length=20,
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        username_val = self.username.value
        
        # แสดงสถานะกำลังตรวจสอบ
        await interaction.response.defer(ephemeral=True)
        
        try:
            # ใช้ POST endpoint เพื่อความแม่นยำและรองรับข้อมูลแบบ array (data)
            url = "https://users.roblox.com/v1/usernames/users"
            payload = {
                "usernames": [username_val],
                "excludeBannedUsers": False
            }
            headers = {
                "Content-Type": "application/json",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        # ตรวจสอบว่ามีข้อมูลใน data list หรือไม่
                        if "data" in data and len(data["data"]) > 0:
                            roblox_user = data["data"][0]
                            actual_name = roblox_user["name"] # หรือใช้ roblox_user.get("name")
                            
                            # ตรวจสอบว่าสามารถเปลี่ยนชื่อได้ไหม (ต้องเป็นเจ้าของเซิร์ฟเวอร์หรือมีสิทธิ์สูงกว่าบอท)
                            try:
                                await interaction.user.edit(nick=actual_name)
                                nickname_msg = f"เปลี่ยนชื่อเป็น **{actual_name}** เรียบร้อยแล้วครับ"
                            except discord.Forbidden:
                                nickname_msg = f"บอทไม่มีสิทธิ์เปลี่ยนชื่อของคุณ (ชื่อจริงคือ **{actual_name}**)"

                            # มอบ Role จาก .env
                            role_id = os.getenv('VERIFIED_ROLE_ID')
                            role_status = ""
                            if role_id:
                                try:
                                    role = interaction.guild.get_role(int(role_id))
                                    if role:
                                        await interaction.user.add_roles(role)
                                        role_status = f" และมอบยศ **{role.name}** ให้แล้วครับ"
                                    else:
                                        role_status = " (ไม่พบยศที่กำหนดในระบบ)"
                                except Exception as e:
                                    print(f"Error adding role: {e}")
                                    role_status = " (เกิดข้อผิดพลาดในการมอบยศ)"
                            
                            await interaction.followup.send(
                                f"✅ ยืนยันตัวตนสำเร็จ! {nickname_msg}{role_status}",
                                ephemeral=True
                            )
                        else:
                            await interaction.followup.send(
                                f"❌ ไม่พบชื่อผู้ใช้ **{username_val}** ในระบบ Roblox ครับ กรุณาตรวจสอบตัวสะกดและลองใหม่อีกครั้ง",
                                ephemeral=True
                            )
                    else:
                        status = response.status
                        await interaction.followup.send(
                            f"❌ เกิดข้อผิดพลาดในการเชื่อมต่อกับ Roblox API (Code: {status}) กรุณาลองใหม่ภายหลัง",
                            ephemeral=True
                        )
        except Exception as e:
            print(f"Error in Roblox verification: {e}")
            await interaction.followup.send(
                "❌ เกิดข้อผิดพลาดไม่คาดคิดภายในระบบ กรุณาติดต่อแอดมิน",
                ephemeral=True
            )

class RobloxVerifyView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None) # Persistent view

    @discord.ui.button(label="📝 ยืนยันตัวตน", style=discord.ButtonStyle.primary, custom_id="roblox_verify_button")
    async def verify_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(RobloxVerifyModal())

class VerificationCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="setup_verify", description="[Admin] ตั้งค่าปุ่มยืนยันตัวตน Roblox ในห้องที่กำหนด")
    @app_commands.describe(channel="ห้องที่ต้องการส่งปุ่มยืนยันตัวตน")
    @app_commands.default_permissions(administrator=True)
    async def setup_verify(self, interaction: discord.Interaction, channel: discord.TextChannel):
        embed = discord.Embed(
            title="<:sheild:1459451942819467388> ระบบยืนยันตัวตน Roblox",
            description=(
                "กรุณากดปุ่มด้านล่างเพื่อทำการยืนยันตัวตนและซิงค์ชื่อจากในเกม\n\n"
                "**ขั้นตอน:**\n"
                "1. กดปุ่ม 'ยืนยันตัวตน'\n"
                "2. กรอกชื่อผู้ใช้ Roblox ของคุณ\n"
                "3. บอทจะทำการตรวจสอบและเปลี่ยนชื่อในดิสคอร์ดให้โดยอัตโนมัติ"
            ),
            color=discord.Color.blurple()
        )
        embed.set_footer(text="powered by tonpai3011l • Roblox Verification")
        
        await channel.send(embed=embed, view=RobloxVerifyView())
        await interaction.response.send_message(f"✅ ตั้งค่าระบบยืนยันตัวตนที่ห้อง {channel.mention} เรียบร้อยแล้ว", ephemeral=True)

async def setup(bot):
    await bot.add_cog(VerificationCog(bot))
