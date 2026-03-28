import discord
from discord.ext import commands
from discord import app_commands, ui
import json
import os
import re

DB_FILE = "json/lottery_data.json"

class LotteryModal(ui.Modal):
    def __init__(self, cog, bet_type):
        type_str = "เลขท้าย 2 ตัว" if bet_type == "last_2" else "เลขท้าย 3 ตัว"
        super().__init__(title=f"ระบุตัวเลข: ลุ้น{type_str}")
        self.cog = cog
        self.bet_type = bet_type
        
        self.number_input = ui.TextInput(
            label="เลข 6 หลัก (เช่น 012345)",
            placeholder="กรอกเลข 6 หลัก...",
            required=True,
            min_length=6,
            max_length=6
        )
        self.add_item(self.number_input)

    async def on_submit(self, interaction: discord.Interaction):
        num_str = self.number_input.value
        if not re.fullmatch(r'\d{6}', num_str):
            await interaction.response.send_message("❌ กรุณาระบุเป็นตัวเลข 6 หลักให้ถูกต้อง (0-9 เท่านั้น)", ephemeral=True)
            return
            
        # Check economy
        economy_cog = self.cog.bot.get_cog('Economy')
        if not economy_cog:
            await interaction.response.send_message("❌ ระบบกระเป๋าเงินมีปัญหา ลองเรียกแอดมินมาดูที", ephemeral=True)
            return
            
        user_id = str(interaction.user.id)
        bal = economy_cog.get_balance(user_id)
        ticket_price = 80
        
        if bal['wallet'] < ticket_price:
            await interaction.response.send_message(f"❌ เงินในกระเป๋าไม่พอ! (ต้องการ {ticket_price} บาท)", ephemeral=True)
            return
            
        economy_cog.update_balance(user_id, -ticket_price, "wallet")
        
        # Save ticket
        if user_id not in self.cog.data["tickets"]:
            self.cog.data["tickets"][user_id] = []
            
        self.cog.data["tickets"][user_id].append({
            "number": num_str,
            "type": self.bet_type,
            "claimed": False
        })
        self.cog.save_data()
        
        type_display = "2 ตัวท้าย" if self.bet_type == "last_2" else "3 ตัวท้าย"
        await interaction.response.send_message(f"✅ ซื้อสลาก **{num_str}** แบบลุ้น **{type_display}** เรียบร้อยแล้ว!\n*(หักเงินจาก Wallet {ticket_price} บาท)*", ephemeral=True)

class LotteryTypeView(ui.View):
    def __init__(self, cog):
        super().__init__(timeout=120)
        self.cog = cog

    @ui.button(label="ลุ้นเลขท้าย 2 ตัว (80 บาท)", style=discord.ButtonStyle.primary, row=0)
    async def btn_last2(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(LotteryModal(self.cog, "last_2"))

    @ui.button(label="ลุ้นเลขท้าย 3 ตัว (80 บาท)", style=discord.ButtonStyle.primary, row=0)
    async def btn_last3(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(LotteryModal(self.cog, "last_3"))

class LotteryMainView(ui.View):
    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog
        
        status = self.cog.data.get("status", "open")
        buy_btn = [x for x in self.children if getattr(x, "custom_id", None) == "lottery_buy_btn"][0]
        
        if status == "open":
            buy_btn.disabled = False
            buy_btn.emoji = "🛒"
            buy_btn.label = " ซื้อสลาก"
        else:
            buy_btn.disabled = True
            buy_btn.label = "ปิดรับซื้อแล้ว"

    @ui.button(emoji="🛒", label=" ซื้อสลาก", style=discord.ButtonStyle.success, custom_id="lottery_buy_btn")
    async def buy_button(self, interaction: discord.Interaction, button: ui.Button):
        embed = discord.Embed(title="🎫 เลือกประเภทสลาก", description="สลากทุกใบราคา 80 บาท\nโดยคุณจะได้ระบุตัวเลข 6 หลักด้วยตัวเองทั้งหมด!", color=discord.Color.blue())
        await interaction.response.send_message(embed=embed, view=LotteryTypeView(self.cog), ephemeral=True)

    @ui.button(emoji="📋", label=" สลากของฉัน", style=discord.ButtonStyle.secondary, custom_id="lottery_my_tickets_btn")
    async def inventory_button(self, interaction: discord.Interaction, button: ui.Button):
        user_id = str(interaction.user.id)
        tickets = self.cog.data["tickets"].get(user_id, [])
        unclaimed = [t for t in tickets if not t["claimed"]]
        
        if not unclaimed:
            await interaction.response.send_message("คุณยังไม่มีสลากที่รอตรวจผลเลย (หรือสลากทั้งหมดของคุณตรวจรับเงินไปหมดแล้ว)", ephemeral=True)
            return
            
        txt = ""
        for i, t in enumerate(unclaimed, 1):
            t_str = "ลุ้น 2 ตัวท้าย" if t["type"] == "last_2" else "ลุ้น 3 ตัวท้าย"
            txt += f"{i}. **{t['number']}** ({t_str})\n"
            
        embed = discord.Embed(title="🎟️ สลากที่คุณถือครองอยู่", description=txt, color=discord.Color.purple())
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @ui.button(emoji="🔍", label=" ตรวจสลาก", style=discord.ButtonStyle.primary, custom_id="lottery_check_btn")
    async def check_button(self, interaction: discord.Interaction, button: ui.Button):
        prizes = self.cog.data.get("prizes", {})
        if not prizes.get("first") and not prizes.get("last_3") and not prizes.get("last_2"):
            await interaction.response.send_message("งวดนี้ยังไม่ได้ประกาศผลรางวัลครับ รอสักครู่นะฮะ!", ephemeral=True)
            return
            
        user_id = str(interaction.user.id)
        tickets = self.cog.data["tickets"].get(user_id, [])
        unclaimed_idx = [i for i, t in enumerate(tickets) if not t["claimed"]]
        
        if not unclaimed_idx:
            await interaction.response.send_message("คุณไม่มีสลากให้ตรวจเลย หรือสลากของคุณตรวจรับไปหมดแล้ว", ephemeral=True)
            return

        total_won = 0
        result_txt = ""
        economy_cog = self.cog.bot.get_cog('Economy')
        
        prize_1st = prizes.get("first", "")
        prize_last3 = prizes.get("last_3", "")
        prize_last2 = prizes.get("last_2", "")
        
        has_win = False
        
        for idx in unclaimed_idx:
            t = tickets[idx]
            num = t["number"]
            b_type = t["type"]
            t["claimed"] = True # Mark as claimed permanently
            
            won_amt = 0
            win_msg = ""
            
            # Special Prize checking (matching all 6 digits exactly)
            if prize_1st and num == prize_1st:
                won_amt = 6000000
                win_msg = "🎉 **รางวัลพิเศษ (ตรง 6 หลัก!!)**"
            else:
                # Normal check based on bet type
                if b_type == "last_2" and prize_last2 and num[-2:] == prize_last2:
                    won_amt = 2000
                    win_msg = "✅ **เลขท้าย 2 ตัว**"
                elif b_type == "last_3" and prize_last3 and num[-3:] == prize_last3:
                    won_amt = 4000
                    win_msg = "✅ **เลขท้าย 3 ตัว**"
                    
            if won_amt > 0:
                total_won += won_amt
                result_txt += f"สลาก **{num}**: {win_msg} (รับกำไร {won_amt:,} บาท)\n"
                has_win = True
            else:
                result_txt += f"สลาก **{num}**: ❌ ไม่ถูกรางวัล\n"
                
        self.cog.save_data()
        
        if total_won > 0 and economy_cog:
            economy_cog.update_balance(user_id, total_won, "bank")
            result_txt += f"\n💰 เงินรางวัลรวม **{total_won:,}** บาท โอนเข้าบัญชีธนาคารเรียบร้อยแล้ว!"
        
        embed = discord.Embed(
            title="✨ ผลการตรวจสลากของคุณ", 
            description=result_txt, 
            color=discord.Color.gold() if has_win else discord.Color.red()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


class Lottery(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.load_data()

    def load_data(self):
        if not os.path.exists(DB_FILE):
            self.data = {
                "prizes": {"first": None, "last_3": None, "last_2": None},
                "tickets": {},
                "dashboard": None,
                "status": "open"
            }
            self.save_data()
        else:
            with open(DB_FILE, "r") as f:
                self.data = json.load(f)
                
    def save_data(self):
        # Create folder if not exists just to be safe
        os.makedirs(os.path.dirname(DB_FILE), exist_ok=True)
        with open(DB_FILE, "w") as f:
            json.dump(self.data, f, indent=4)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # ข้ามข้อความของบอท หรือข้อความส่วนตัว (DM)
        if message.author.bot or isinstance(message.channel, discord.DMChannel):
            return

        dashboard = self.data.get("dashboard")
        if dashboard and dashboard.get("channel_id") == message.channel.id:
            try:
                await message.delete()
            except (discord.Forbidden, discord.NotFound, discord.HTTPException):
                pass

    async def _update_dashboard(self):
        if not self.data.get("dashboard"):
            return
            
        channel = self.bot.get_channel(self.data["dashboard"]["channel_id"])
        if not channel: return
        try:
            msg = await channel.fetch_message(self.data["dashboard"]["message_id"])
            status_text = "🟢 เปิดรับแทง" if self.data["status"] == "open" else "🔴 ปิดรับแทง (รอผลรางวัล)"
            
            prizes_str = ""
            if self.data["prizes"]["first"]:
                p = self.data["prizes"]
                prizes_str = f"\n\n🏆 **ผลรางวัลงวดล่าสุด**\n- รางวัลพิเศษ: **{p['first']}**\n- เลขท้าย 3 ตัว: **{p['last_3']}**\n- เลขท้าย 2 ตัว: **{p['last_2']}**"

            embed = discord.Embed(
                title="🎰 สลากกินแบ่งกินรัฐบาลไทย", 
                description=f"สถานะตลาด: **{status_text}**\nสลากราคาใบละ **80 บาท**\n\n📌 **กติกาการจ่ายรางวัล:**\n- แบบลุ้น 2 ตัวท้าย ถูกรับ 2,000 บาท\n- แบบลุ้น 3 ตัวท้าย ถูกรับ 4,000 บาท\n- 🌟 **รางวัลพิเศษ:** ถ้าเลขที่ซื้อ 6 ตัวตรงกับรางวัลพิเศษเป๊ะๆ รับ 6,000,000 บาท ทันที! (ไม่ว่าจะลุ้นแบบไหน){prizes_str}", 
                color=discord.Color.blue()
            )
            embed.set_thumbnail(url="https://cdn-icons-png.flaticon.com/512/3233/3233816.png") # Example lottery ticket icon
            await msg.edit(embed=embed, view=LotteryMainView(self))
        except:
            pass

    @app_commands.command(name="setup_lottery", description="[Admin] ตั้งค่าบอร์ดขายสลากกินแบ่ง")
    @app_commands.default_permissions(administrator=True)
    async def setup_lottery(self, interaction: discord.Interaction):
        # Clean old message if it exists
        if self.data.get("dashboard"):
            try:
                old_channel = self.bot.get_channel(self.data["dashboard"]["channel_id"])
                if old_channel:
                    old_msg = await old_channel.fetch_message(self.data["dashboard"]["message_id"])
                    await old_msg.delete()
            except:
                pass
                
        embed = discord.Embed(title="กำลังโหลดระบบสลาก...", color=discord.Color.blue())
        msg = await interaction.channel.send(embed=embed)
        self.data["dashboard"] = {"channel_id": interaction.channel.id, "message_id": msg.id}
        self.save_data()
        await self._update_dashboard()
        await interaction.response.send_message("✅ สร้างบอร์ดขายลอตเตอรี่สำเร็จ", ephemeral=True)

    @app_commands.command(name="lottery_status", description="[Admin] เปิด/ปิด การซื้อสลาก")
    @app_commands.default_permissions(administrator=True)
    @app_commands.choices(mode=[
        app_commands.Choice(name="Open (เปิดรับแทง)", value="open"),
        app_commands.Choice(name="Close (ปิดรอผล)", value="close")
    ])
    async def lottery_status(self, interaction: discord.Interaction, mode: app_commands.Choice[str]):
        self.data["status"] = mode.value
        self.save_data()
        await self._update_dashboard()
        await interaction.response.send_message(f"✅ ปรับสถานะเป็นชือ {mode.name} แล้ว", ephemeral=True)

    @app_commands.command(name="set_lottery_prize", description="[Admin] ตั้งค่าผลรางวัลสลาก")
    @app_commands.default_permissions(administrator=True)
    async def set_lottery_prize(self, interaction: discord.Interaction, first: str, last_3: str, last_2: str):
        if not re.fullmatch(r'\d{6}', first) or not re.fullmatch(r'\d{3}', last_3) or not re.fullmatch(r'\d{2}', last_2):
            await interaction.response.send_message("❌ กรุณาตรวจสอบตัวเลข\n- ชุดที่ 1 (first) = 6 หลัก\n- ชุดที่ 2 (last_3) = 3 หลัก\n- ชุดที่ 3 (last_2) = 2 หลัก", ephemeral=True)
            return
            
        self.data["prizes"] = {
            "first": first,
            "last_3": last_3,
            "last_2": last_2
        }
        self.save_data()
        await self._update_dashboard() # Update dashboard to show winning numbers
        await interaction.response.send_message(f"✅ บันทึกผลรางวัลงวดนี้แล้ว:\n- รางวัลพิเศษ (6 ตัว): {first}\n- เลขท้าย 3 ตัว: {last_3}\n- เลขท้าย 2 ตัว: {last_2}\n*(ผู้เล่นสามารถกดตรวจสลากได้เลยที่หน้าบอร์ด)*", ephemeral=True)

    @app_commands.command(name="draw_lottery", description="[Admin] สุ่มออกรางวัลสลากกินแบ่งอัตโนมัติ (ปิดรับแทงทันที)")
    async def draw_lottery(self, interaction: discord.Interaction):
        gov_role_id = os.getenv('GOV_ROLE_ID')
        if gov_role_id and gov_role_id.isdigit():
            has_gov_role = any(role.id == int(gov_role_id) for role in interaction.user.roles)
        else:
            has_gov_role = any(role.name == "[ 𝐆𝐨𝐯𝐞𝐫𝐧𝐦𝐞𝐧𝐭 | รัฐบาล ]" for role in interaction.user.roles)
            
        if not has_gov_role and not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ คุณไม่มีสิทธิ์ใช้คำสั่งนี้ (ต้องมี Role ID ที่กำหนด หรือเป็นผู้ดูแลระบบ)", ephemeral=True)
            return
            
        import random
        first = f"{random.randint(0, 999999):06d}"
        last_3 = f"{random.randint(0, 999):03d}"
        last_2 = f"{random.randint(0, 99):02d}"
        
        self.data["prizes"] = {
            "first": first,
            "last_3": last_3,
            "last_2": last_2
        }
        self.data["status"] = "close" # ปิดรับแทงอัตโนมัติ
        self.save_data()
        await self._update_dashboard()
        
        await interaction.response.send_message(f"🎉 **สุ่มออกรางวัลเรียบร้อยแล้ว!** (และปิดรับแทงอัตโนมัติ)\n- รางวัลพิเศษ: **{first}**\n- เลขท้าย 3 ตัว: **{last_3}**\n- เลขท้าย 2 ตัว: **{last_2}**", ephemeral=False)

    @app_commands.command(name="clear_lottery", description="[Admin] ล้างสลากและผลทั้งหมด เพื่อเริ่มงวดใหม่")
    @app_commands.default_permissions(administrator=True)
    async def clear_lottery(self, interaction: discord.Interaction):
        self.data["tickets"] = {}
        self.data["prizes"] = {"first": None, "last_3": None, "last_2": None}
        self.data["status"] = "open" # เปิดรับแทงอัตโนมัติ
        self.save_data()
        await self._update_dashboard()
        await interaction.response.send_message("✅ ล้างข้อมูลสลากและรางวัลออกเรียบร้อย พร้อมเปิดรับซื้องวดใหม่แล้ว!", ephemeral=True)

async def setup(bot):
    await bot.add_cog(Lottery(bot))
