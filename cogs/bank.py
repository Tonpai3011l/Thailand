import discord
from discord.ext import commands
from discord import app_commands, ui
import json
import os

BANK_DB_FILE = "json/bank_data.json"

# --- Central Bank (Budget) Modals ---

class BudgetWithdrawModal(ui.Modal, title="เบิกงบประมาณ (รัฐบาล)"):
    amount = ui.TextInput(label="จำนวนเงิน", placeholder="ระบุจำนวนเงินที่ต้องการเบิก...", required=True)
    
    def __init__(self, cog):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        try:
            amt = int(self.amount.value)
            if amt <= 0: raise ValueError
        except ValueError:
            return await interaction.response.send_message("❌ จำนวนเงินไม่ถูกต้อง", ephemeral=True)
            
        eco_cog = self.cog.bot.get_cog('Economy')
        if not eco_cog: return await interaction.response.send_message("❌ ระบบ Economy ไม่พร้อม", ephemeral=True)
        
        system_bal = eco_cog.get_balance("system_bank")
        if system_bal['bank'] < amt:
            return await interaction.response.send_message("❌ เงินคงคลัง (System Bank) มีไม่พอให้เบิก!", ephemeral=True)
            
        eco_cog.update_balance("system_bank", -amt, "bank")
        eco_cog.update_balance(str(interaction.user.id), amt, "wallet")
        
        await self.cog._update_central_dashboard()
        await interaction.response.send_message(f"✅ เบิกงบประมาณ **{amt:,}** บาท เข้ากระเป๋าของคุณเรียบร้อยแล้ว", ephemeral=True)

class BudgetDepositModal(ui.Modal, title="นำส่งเงินเข้าคลัง (รัฐบาล)"):
    amount = ui.TextInput(label="จำนวนเงิน", placeholder="ระบุจำนวนเงินที่ต้องการนำส่ง...", required=True)
    
    def __init__(self, cog):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        try:
            amt = int(self.amount.value)
            if amt <= 0: raise ValueError
        except ValueError:
            return await interaction.response.send_message("❌ จำนวนเงินไม่ถูกต้อง", ephemeral=True)
            
        eco_cog = self.cog.bot.get_cog('Economy')
        user_id = str(interaction.user.id)
        bal = eco_cog.get_balance(user_id)
        
        if bal['wallet'] < amt:
            return await interaction.response.send_message("❌ เงินในกระเป๋าของคุณไม่พอส่งเข้าคลัง!", ephemeral=True)
            
        eco_cog.update_balance(user_id, -amt, "wallet")
        eco_cog.update_balance("system_bank", amt, "bank")
        
        await self.cog._update_central_dashboard()
        await interaction.response.send_message(f"✅ นำส่งเงินงบประมาณ **{amt:,}** บาท เข้าคลังเรียบร้อยแล้ว", ephemeral=True)


# --- Sub-Bank Modals ---

class SubBankDepositModal(ui.Modal):
    amount = ui.TextInput(label="จำนวนเงิน", placeholder="ระบุจำนวนเงินที่ต้องการฝาก...", required=True)
    
    def __init__(self, cog, bank_name):
        super().__init__(title=f"ฝากเงิน: {bank_name}")
        self.cog = cog
        self.bank_name = bank_name

    async def on_submit(self, interaction: discord.Interaction):
        try:
            amt = int(self.amount.value)
            if amt <= 0: raise ValueError
        except ValueError:
            return await interaction.response.send_message("❌ จำนวนเงินไม่ถูกต้อง", ephemeral=True)
            
        eco_cog = self.cog.bot.get_cog('Economy')
        user_id = str(interaction.user.id)
        bal = eco_cog.get_balance(user_id)
        
        if bal['wallet'] < amt:
            return await interaction.response.send_message("❌ เงินในกระเป๋าไม่พอ!", ephemeral=True)
            
        eco_cog.update_balance(user_id, -amt, "wallet")
        self.cog.add_subbank_balance(self.bank_name, user_id, amt)
        
        await self.cog._update_subbank_dashboard(self.bank_name)
        await interaction.response.send_message(f"✅ ฝากเงิน **{amt:,}** บาท เข้าธนาคาร {self.bank_name} เรียบร้อย", ephemeral=True)

class SubBankWithdrawModal(ui.Modal):
    amount = ui.TextInput(label="จำนวนเงิน", placeholder="ระบุจำนวนเงินที่ต้องการถอน...", required=True)
    
    def __init__(self, cog, bank_name):
        super().__init__(title=f"ถอนเงิน: {bank_name}")
        self.cog = cog
        self.bank_name = bank_name

    async def on_submit(self, interaction: discord.Interaction):
        try:
            amt = int(self.amount.value)
            if amt <= 0: raise ValueError
        except ValueError:
            return await interaction.response.send_message("❌ จำนวนเงินไม่ถูกต้อง", ephemeral=True)
            
        eco_cog = self.cog.bot.get_cog('Economy')
        user_id = str(interaction.user.id)
        
        sub_bal = self.cog.get_subbank_balance(self.bank_name, user_id)
        if sub_bal < amt:
            return await interaction.response.send_message("❌ เงินฝากในบัญชีนี้ไม่พอ!", ephemeral=True)
            
        self.cog.add_subbank_balance(self.bank_name, user_id, -amt)
        eco_cog.update_balance(user_id, amt, "wallet")
        
        await self.cog._update_subbank_dashboard(self.bank_name)
        await interaction.response.send_message(f"✅ ถอนเงิน **{amt:,}** บาท เรียบร้อยแล้ว", ephemeral=True)

class SubBankLoanModal(ui.Modal):
    amount = ui.TextInput(label="จำนวนเงิน", placeholder="ระบุจำนวนเงินที่ต้องการกู้...", required=True)
    
    def __init__(self, cog, bank_name):
        super().__init__(title=f"ขอกู้เงิน: {bank_name}")
        self.cog = cog
        self.bank_name = bank_name

    async def on_submit(self, interaction: discord.Interaction):
        try:
            amt = int(self.amount.value)
            if amt <= 0: raise ValueError
        except ValueError:
            return await interaction.response.send_message("❌ จำนวนเงินไม่ถูกต้อง", ephemeral=True)
            
        eco_cog = self.cog.bot.get_cog('Economy')
        user_id = str(interaction.user.id)
        
        bank_data = self.cog.data["sub_banks"][self.bank_name]
        if "loans" not in bank_data:
            bank_data["loans"] = {}
            
        current_loan = bank_data["loans"].get(user_id, 0)
        bank_data["loans"][user_id] = current_loan + amt
        self.cog.save_data()
        
        eco_cog.update_balance(user_id, amt, "wallet")
        
        await interaction.response.send_message(f"✅ อนุมัติเงินกู้ **{amt:,}** บาท โอนเข้ากระเป๋าเรียบร้อยแล้ว\n*(ยอดหนี้รวมของคุณที่นี่: {current_loan + amt:,} บาท)*", ephemeral=True)

class SubBankPayLoanModal(ui.Modal):
    amount = ui.TextInput(label="จำนวนเงิน", placeholder="ระบุจำนวนเงินที่ต้องการชำระ...", required=True)
    
    def __init__(self, cog, bank_name):
        super().__init__(title=f"ชำระหนี้: {bank_name}")
        self.cog = cog
        self.bank_name = bank_name

    async def on_submit(self, interaction: discord.Interaction):
        try:
            amt = int(self.amount.value)
            if amt <= 0: raise ValueError
        except ValueError:
            return await interaction.response.send_message("❌ จำนวนเงินไม่ถูกต้อง", ephemeral=True)
            
        eco_cog = self.cog.bot.get_cog('Economy')
        user_id = str(interaction.user.id)
        
        bank_data = self.cog.data["sub_banks"][self.bank_name]
        current_loan = bank_data.get("loans", {}).get(user_id, 0)
        
        if current_loan <= 0:
            return await interaction.response.send_message("❌ คุณไม่ได้มีหนี้ค้างชำระที่ธนาคารนี้", ephemeral=True)
            
        if amt > current_loan:
            amt = current_loan
            
        bal = eco_cog.get_balance(user_id)
        if bal['wallet'] < amt:
            return await interaction.response.send_message("❌ เงินในกระเป๋าไม่พอชำระหนี้!", ephemeral=True)
            
        eco_cog.update_balance(user_id, -amt, "wallet")
        bank_data["loans"][user_id] -= amt
        if bank_data["loans"][user_id] <= 0:
            del bank_data["loans"][user_id]
        
        self.cog.save_data()
        await interaction.response.send_message(f"✅ ชำระหนี้ **{amt:,}** บาท เรียบร้อยแล้ว (ยอดหนี้คงเหลือ {current_loan - amt:,} บาท)", ephemeral=True)

# --- Views ---

class CentralBankView(ui.View):
    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog

    async def check_gov_role(self, interaction: discord.Interaction) -> bool:
        if interaction.user.guild_permissions.administrator: return True
        gov_role_id = os.getenv('GOV_ROLE_ID')
        if gov_role_id and gov_role_id.isdigit():
            return any(r.id == int(gov_role_id) for r in interaction.user.roles)
        return any(r.name == "รัฐบาล" for r in interaction.user.roles)

    @ui.button(label="เบิกงบประมาณ", style=discord.ButtonStyle.danger, emoji="💸", custom_id="cbank_withdraw_budget")
    async def btn_withdraw_budget(self, interaction: discord.Interaction, button: ui.Button):
        if not await self.check_gov_role(interaction):
            return await interaction.response.send_message("❌ เฉพาะรัฐบาลและผู้ดูแลระบบเท่านั้นที่สามารถเบิกงบได้", ephemeral=True)
        await interaction.response.send_modal(BudgetWithdrawModal(self.cog))

    @ui.button(label="นำส่งเงินสำรอง", style=discord.ButtonStyle.success, emoji="📥", custom_id="cbank_deposit_budget")
    async def btn_deposit_budget(self, interaction: discord.Interaction, button: ui.Button):
        if not await self.check_gov_role(interaction):
            return await interaction.response.send_message("❌ เฉพาะรัฐบาลและผู้ดูแลระบบเท่านั้นที่ทำรายการนี้ได้", ephemeral=True)
        await interaction.response.send_modal(BudgetDepositModal(self.cog))

class SubBankView(ui.View):
    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog

    def get_bank_name_from_msg(self, message_id):
        # ปุ่มอยู่ล่างสุด (msg_users)
        for b_name, b_data in self.cog.data["sub_banks"].items():
            if b_data.get("dashboard", {}).get("msg_users") == message_id:
                return b_name
        return None

    @ui.button(label="เปิดบัญชี", style=discord.ButtonStyle.success, emoji="📝", custom_id="sbank_open", row=0)
    async def btn_open(self, interaction: discord.Interaction, button: ui.Button):
        bank_name = self.get_bank_name_from_msg(interaction.message.id)
        if not bank_name: return await interaction.response.send_message("❌ ข้อผิดพลาด: ไม่พบข้อมูลธนาคารสำหรับข้อความนี้", ephemeral=True)
        
        user_id = str(interaction.user.id)
        bank_data = self.cog.data["sub_banks"][bank_name]
        if user_id in bank_data["accounts"]:
            return await interaction.response.send_message("❌ คุณมีบัญชีกับธนาคารนี้อยู่แล้ว", ephemeral=True)
            
        bank_data["accounts"][user_id] = {"balance": 0}
        self.cog.save_data()
        await self.cog._update_subbank_dashboard(bank_name)
        await interaction.response.send_message(f"✅ เปิดบัญชีกับธนาคาร **{bank_name}** เรียบร้อยแล้ว", ephemeral=True)

    @ui.button(label="ฝากเงิน", style=discord.ButtonStyle.primary, emoji="📥", custom_id="sbank_deposit", row=0)
    async def btn_deposit(self, interaction: discord.Interaction, button: ui.Button):
        bank_name = self.get_bank_name_from_msg(interaction.message.id)
        if not bank_name: return await interaction.response.send_message("❌ ข้อผิดพลาด: ไม่พบข้อมูลธนาคาร", ephemeral=True)
        
        user_id = str(interaction.user.id)
        if user_id not in self.cog.data["sub_banks"][bank_name]["accounts"]:
            return await interaction.response.send_message("❌ คุณยังไม่มีบัญชีกับธนาคารนี้ กรุณากดเปิดบัญชีก่อนครับ", ephemeral=True)
            
        await interaction.response.send_modal(SubBankDepositModal(self.cog, bank_name))

    @ui.button(label="ถอนเงิน", style=discord.ButtonStyle.secondary, emoji="📤", custom_id="sbank_withdraw", row=0)
    async def btn_withdraw(self, interaction: discord.Interaction, button: ui.Button):
        bank_name = self.get_bank_name_from_msg(interaction.message.id)
        if not bank_name: return await interaction.response.send_message("❌ ข้อผิดพลาด: ไม่พบข้อมูลธนาคาร", ephemeral=True)
        
        user_id = str(interaction.user.id)
        if user_id not in self.cog.data["sub_banks"][bank_name]["accounts"]:
            return await interaction.response.send_message("❌ คุณยังไม่มีบัญชีกับธนาคารนี้", ephemeral=True)
            
        await interaction.response.send_modal(SubBankWithdrawModal(self.cog, bank_name))

    @ui.button(label="ขอกู้เงิน", style=discord.ButtonStyle.danger, emoji="💸", custom_id="sbank_loan", row=1)
    async def btn_loan(self, interaction: discord.Interaction, button: ui.Button):
        bank_name = self.get_bank_name_from_msg(interaction.message.id)
        if not bank_name: return await interaction.response.send_message("❌ ข้อผิดพลาด: ไม่พบข้อมูลธนาคาร", ephemeral=True)
        
        user_id = str(interaction.user.id)
        if user_id not in self.cog.data["sub_banks"][bank_name]["accounts"]:
            return await interaction.response.send_message("❌ คุณต้องเปิดบัญชีก่อน จึงจะสามารถทำธุรกรรมกู้เงินได้", ephemeral=True)
            
        await interaction.response.send_modal(SubBankLoanModal(self.cog, bank_name))

    @ui.button(label="ชำระหนี้", style=discord.ButtonStyle.secondary, emoji="💳", custom_id="sbank_payloan", row=1)
    async def btn_payloan(self, interaction: discord.Interaction, button: ui.Button):
        bank_name = self.get_bank_name_from_msg(interaction.message.id)
        if not bank_name: return await interaction.response.send_message("❌ ข้อผิดพลาด: ไม่พบข้อมูลธนาคาร", ephemeral=True)
        
        user_id = str(interaction.user.id)
        if user_id not in self.cog.data["sub_banks"][bank_name]["accounts"]:
            return await interaction.response.send_message("❌ คุณยังไม่มีบัญชีที่นี่", ephemeral=True)
            
        await interaction.response.send_modal(SubBankPayLoanModal(self.cog, bank_name))


class Bank(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.load_data()

    def load_data(self):
        if not os.path.exists(BANK_DB_FILE):
            self.data = {
                "central": {
                    "rates": {
                        "deposit": 0,
                        "loan": 0
                    },
                    "dashboard": {"channel_id": None, "message_id": None},
                    "loans": {}
                },
                "sub_banks": {}
            }
            self.save_data()
        else:
            with open(BANK_DB_FILE, "r", encoding="utf-8") as f:
                self.data = json.load(f)

    def save_data(self):
        os.makedirs(os.path.dirname(BANK_DB_FILE), exist_ok=True)
        with open(BANK_DB_FILE, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=4, ensure_ascii=False)

    def get_subbank_balance(self, bank_name, user_id):
        return self.data["sub_banks"].get(bank_name, {}).get("accounts", {}).get(user_id, {}).get("balance", 0)

    def add_subbank_balance(self, bank_name, user_id, amount):
        if bank_name in self.data["sub_banks"] and user_id in self.data["sub_banks"][bank_name]["accounts"]:
            self.data["sub_banks"][bank_name]["accounts"][user_id]["balance"] += amount
            self.save_data()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or isinstance(message.channel, discord.DMChannel):
            return

        c_dash = self.data["central"].get("dashboard")
        is_dashboard = False
        
        if c_dash and c_dash.get("channel_id") == message.channel.id:
            is_dashboard = True
            
        for bank_name, b_data in self.data["sub_banks"].items():
            s_dash = b_data.get("dashboard")
            if s_dash and s_dash.get("channel_id") == message.channel.id:
                is_dashboard = True
                
        if is_dashboard:
            try:
                await message.delete()
            except (discord.Forbidden, discord.NotFound, discord.HTTPException):
                pass

    @app_commands.command(name="setup_bank", description="[Admin] สร้างบอร์ดธนาคารกลางประเทศไทย (สำหรับเบิกงบ)")
    @app_commands.default_permissions(administrator=True)
    async def setup_bank(self, interaction: discord.Interaction):
        old_dash = self.data["central"].get("dashboard")
        if old_dash and old_dash.get("message_id"):
            try:
                old_ch = self.bot.get_channel(old_dash["channel_id"])
                if old_ch:
                    old_msg = await old_ch.fetch_message(old_dash["message_id"])
                    await old_msg.delete()
            except: pass

        embed = discord.Embed(title="กำลังสร้างระบบธนาคาร...", color=discord.Color.blue())
        msg = await interaction.channel.send(embed=embed)
        self.data["central"]["dashboard"] = {"channel_id": interaction.channel.id, "message_id": msg.id}
        self.save_data()
        
        await self._update_central_dashboard()
        await interaction.response.send_message("✅ สร้างบอร์ดธนาคารกลางเสร็จสิ้นแล้ว", ephemeral=True)

    @app_commands.command(name="setup_minbank", description="[Admin] สร้างบอร์ดธนาคารพาณิชย์ (ธนาคารย่อย)")
    @app_commands.describe(bank_name="ชื่อธนาคารย่อย", deposit_rate="อัตราดอกเบี้ยเงินฝาก (%)", loan_rate="อัตราดอกเบี้ยเงินกู้ (%)")
    @app_commands.default_permissions(administrator=True)
    async def setup_minbank(self, interaction: discord.Interaction, bank_name: str, deposit_rate: float, loan_rate: float = 5.0):
        if bank_name not in self.data["sub_banks"]:
            self.data["sub_banks"][bank_name] = {
                "name": bank_name,
                "deposit_rate": deposit_rate,
                "loan_rate": loan_rate,
                "accounts": {},
                "loans": {},
                "dashboard": {"channel_id": None, "msg_info": None, "msg_users": None}
            }
        else:
            self.data["sub_banks"][bank_name]["deposit_rate"] = deposit_rate
            self.data["sub_banks"][bank_name]["loan_rate"] = loan_rate

        old_dash = self.data["sub_banks"][bank_name].get("dashboard")
        if old_dash and old_dash.get("msg_info"):
            try:
                old_ch = self.bot.get_channel(old_dash["channel_id"])
                if old_ch:
                    await (await old_ch.fetch_message(old_dash["msg_info"])).delete()
                    await (await old_ch.fetch_message(old_dash["msg_users"])).delete()
            except: pass

        embed1 = discord.Embed(title=f"🏦 ธนาคาร {bank_name} - โหลด...", color=discord.Color.blue())
        embed2 = discord.Embed(title="โหลดรายชื่อ...", color=discord.Color.light_embed())
        
        msg1 = await interaction.channel.send(embed=embed1)
        msg2 = await interaction.channel.send(embed=embed2)
        
        self.data["sub_banks"][bank_name]["dashboard"] = {
            "channel_id": interaction.channel.id, 
            "msg_info": msg1.id,
            "msg_users": msg2.id
        }
        self.save_data()
        
        await self._update_subbank_dashboard(bank_name)
        await interaction.response.send_message(f"✅ สร้างบอร์ดธนาคารพาณิชย์ {bank_name} สำเร็จ", ephemeral=True)

    async def _update_central_dashboard(self):
        dash = self.data["central"].get("dashboard")
        if not dash or not dash.get("message_id"): return
        
        try:
            channel = self.bot.get_channel(dash["channel_id"])
            if not channel: return
            msg = await channel.fetch_message(dash["message_id"])
            
            eco_cog = self.bot.get_cog('Economy')
            if eco_cog:
                total_money = 0
                for uid, bal in eco_cog.users.items():
                    if uid != "system_bank":
                        total_money += bal.get("wallet", 0) + bal.get("bank", 0)
                system_bal = eco_cog.get_balance("system_bank")['bank']
            else:
                total_money = 0
                system_bal = 0
                
            embed = discord.Embed(title="🏛️ ธนาคารกลางแห่งประเทศไทย (Central Bank)", description="ดูแลปกป้องความมั่นคงทางการเงินให้แก่ราษฎร ใช้สำหรับเบิกจ่ายงบประมาณแผ่นดินเท่านั้น", color=discord.Color.brand_green())
            embed.add_field(name="💰 เงินทุนหมุนเวียนในประเทศ", value=f"**{total_money:,}** บาท", inline=False)
            embed.add_field(name="🏦 เงินคงคลัง (System Bank)", value=f"**{system_bal:,}** บาท", inline=False)
            embed.set_thumbnail(url="https://cdn-icons-png.flaticon.com/512/2830/2830284.png")
            
            await msg.edit(embed=embed, view=CentralBankView(self))
        except:
            pass

    async def _update_subbank_dashboard(self, bank_name):
        bank_data = self.data["sub_banks"].get(bank_name)
        if not bank_data: return
        
        dash = bank_data.get("dashboard")
        if not dash or not dash.get("msg_info"): return
        
        try:
            channel = self.bot.get_channel(dash["channel_id"])
            if not channel: return
            
            msg1 = await channel.fetch_message(dash["msg_info"])
            msg2 = await channel.fetch_message(dash["msg_users"])
            
            embed1 = discord.Embed(title=f"🏦 ธนาคารพาณิชย์ {bank_name}", description="ผลตอบแทนมั่นคง บริการดุจญาติมิตร", color=discord.Color.blue())
            embed1.add_field(name="📈 อัตราดอกเบี้ยเงินฝากสูงสุด", value=f"**{bank_data['deposit_rate']}%** ต่อรอบ", inline=False)
            embed1.set_thumbnail(url="https://cdn-icons-png.flaticon.com/512/2830/2830284.png")
            
            users_txt = ""
            # Sort by balance descending
            sorted_accounts = sorted(bank_data["accounts"].items(), key=lambda x: x[1]['balance'], reverse=True)
            for uid, acc in sorted_accounts:
                bal = acc.get("balance", 0)
                users_txt += f"🔹 <@{uid}>: **{bal:,}** บาท\n"
            if not users_txt:
                users_txt = "ยังไม่มีผู้เปิดบัญชี"
                
            embed2 = discord.Embed(title="👥 รายชื่อผู้ถือบัญชี (สมุดบัญชีเงินฝาก)", description=users_txt, color=discord.Color.dark_blue())
            
            await msg1.edit(embed=embed1, view=SubBankView(self))
            await msg2.edit(embed=embed2)
            
        except Exception as e:
            print(f"Error updating subbank: {e}")

async def setup(bot):
    await bot.add_cog(Bank(bot))
