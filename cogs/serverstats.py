import discord
from discord.ext import commands, tasks
from discord import app_commands
import json
import os
import asyncio
import time

STATS_FILE = "json/server_stats.json"

class ServerStats(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.load_data()
        self._last_update_time = {} # {guild_id: timestamp}
        self.update_stats_loop.start()

    def cog_unload(self):
        self.update_stats_loop.cancel()

    def load_data(self):
        if not os.path.exists(STATS_FILE):
            self.stats = {}
            self.save_data()
        else:
            with open(STATS_FILE, "r", encoding='utf-8') as f:
                self.stats = json.load(f)

    def save_data(self):
        if not os.path.exists('json'):
            os.makedirs('json')
        with open(STATS_FILE, "w", encoding='utf-8') as f:
            json.dump(self.stats, f, indent=4)

    async def _update_guild_stats(self, guild_id_str):
        guild = self.bot.get_guild(int(guild_id_str))
        if not guild: return
        
        data = self.stats.get(guild_id_str)
        if not data: return

        # คำนวณ (ไม่นับบอท)
        total_humans = sum(1 for m in guild.members if not m.bot)
        online = sum(1 for m in guild.members if not m.bot and m.status == discord.Status.online)
        idle = sum(1 for m in guild.members if not m.bot and m.status == discord.Status.idle)
        dnd = sum(1 for m in guild.members if not m.bot and m.status == discord.Status.dnd)
        offline = total_humans - (online + idle + dnd)
        
        total_all = guild.member_count

        new_names = {
            "ch_total": f"Members: {total_all}",
            "ch_status": f"✅ {online} 🌙 {idle+dnd} ❌ {offline}"
        }

        any_updated = False
        for key, name in new_names.items():
            ch_id = data.get(key)
            if ch_id:
                channel = guild.get_channel(ch_id)
                if channel and channel.name != name:
                    try:
                        await channel.edit(name=name)
                        any_updated = True
                        await asyncio.sleep(1) 
                    except Exception as e:
                        print(f"Failed to update {key} on {guild_id_str}: {e}")
        
        if any_updated:
            self._last_update_time[guild_id_str] = time.time()

    async def _queue_update(self, guild):
        if not guild: return
        gid = str(guild.id)
        if gid not in self.stats: return

        now = time.time()
        last = self._last_update_time.get(gid, 0)
        
        # กฎ Discord: ห้ามเปลี่ยนชื่อช่องเกิน 2 ครั้งใน 10 นาที (ปลอดภัยที่ 6 นาที)
        if now - last > 360:
            await self._update_guild_stats(gid)

    @commands.Cog.listener()
    async def on_member_join(self, member):
        await self._queue_update(member.guild)

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        await self._queue_update(member.guild)

    @commands.Cog.listener()
    async def on_presence_update(self, before, after):
        # อัปเดตเมื่อสถานะเปลี่ยนเท่านั้น (เช่น Online -> Idle)
        if before.status != after.status:
            await self._queue_update(after.guild)

    @app_commands.command(name="setup_stats", description="สร้างห้องแสดงสถิติเซิร์ฟเวอร์ (Admin Only)")
    @app_commands.default_permissions(administrator=True)
    async def setup_stats(self, interaction: discord.Interaction):
        guild = interaction.guild
        await interaction.response.send_message("⏳ กำลังเริ่มตั้งค่า Server Stats...", ephemeral=True)

        try:
            # ลบข้อมูลเก่า
            old_data = self.stats.get(str(guild.id))
            if old_data:
                category = guild.get_channel(old_data.get("category_id"))
                if category:
                    for channel in category.channels:
                        try: await channel.delete()
                        except: pass
                    try: await category.delete()
                    except: pass

            overwrites = {guild.default_role: discord.PermissionOverwrite(connect=False)}
            category = await guild.create_category("📊 Server Stats", overwrites=overwrites)

            # สร้าง
            total_all = guild.member_count
            ch_total = await guild.create_voice_channel(f"Members: {total_all}", category=category)
            ch_status = await guild.create_voice_channel("⌛ กำลังโหลดสถิติ...", category=category)
            
            self.stats[str(guild.id)] = {
                "category_id": category.id,
                "ch_total": ch_total.id,
                "ch_status": ch_status.id
            }
            self.save_data()

            # อัปเดตทันทีครั้งแรก
            await self._update_guild_stats(str(guild.id))
            await interaction.followup.send("✅ ตั้งค่า Server Stats เรียบร้อยแล้ว! บอทจะอัปเดตสถานะทันทีที่มีการเปลี่ยนแปลง (จำกัดความเร็วตามกฎ Discord)")

        except Exception as e:
            await interaction.followup.send(f"❌ เกิดข้อผิดพลาด: {e}")

    @tasks.loop(minutes=6)
    async def update_stats_loop(self):
        await self.bot.wait_until_ready()
        for guild_id in list(self.stats.keys()):
            await self._update_guild_stats(guild_id)


async def setup(bot):
    await bot.add_cog(ServerStats(bot))
