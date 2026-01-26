import discord
import os
import asyncio
from discord.ext import commands
from dotenv import load_dotenv

# โหลดค่าตัวแปรจากไฟล์ .env
load_dotenv()

# การตั้งค่าบอท
TOKEN = os.getenv('DISCORD_TOKEN')
INTENTS = discord.Intents.default()
INTENTS.message_content = True # เปิดใช้งาน Intent สำหรับอ่านข้อความ
INTENTS.presences = True # เปิดใช้งานการดูสถานะ (Online/Idle/DND)
INTENTS.members = True # เปิดใช้งานการดูรายชื่อสมาชิกทั้งหมด

from cogs.verification import RobloxVerifyView
from cogs.roles import PersistentRoleGiverView, load_role_settings

class ThaiBot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix='!',
            intents=INTENTS,
            help_command=None
        )

    async def setup_hook(self):
        # โหลดส่วนเสริม (Cogs) จากโฟลเดอร์ cogs
        for filename in os.listdir('./cogs'):
            if filename.endswith('.py'):
                await self.load_extension(f'cogs.{filename[:-3]}')
        
        # ซิงค์คำสั่ง Slash Command ไปยัง Discord
        try:
            synced = await self.tree.sync()
            print(f"เชื่อมต่อคำสั่งแล้ว {len(synced)} คำสั่ง")
        except Exception as e:
            print(f"เกิดข้อผิดพลาดในการซิงค์คำสั่ง: {e}")

    async def on_ready(self):
        # ลงทะเบียน View ถาวรเพื่อให้ปุ่มทำงานหลังบอทรีสตาร์ท
        self.add_view(RobloxVerifyView())
        
        # ลงทะเบียน View รับยศ (ต้องโหลดข้อมูลจาก JSON มาสร้างปุ่ม)
        role_settings = load_role_settings()
        self.add_view(PersistentRoleGiverView(role_settings))
        
        print(f'ล็อกอินในชื่อ {self.user} (ID: {self.user.id})')
        print('-----------------------')

bot = ThaiBot()

if __name__ == '__main__':
    if not TOKEN:
        print("ข้อผิดพลาด: ไม่พบ DISCORD_TOKEN ในไฟล์ .env")
    else:
        bot.run(TOKEN)
