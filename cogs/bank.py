import discord
from discord.ext import commands, tasks
from discord import app_commands, ui
import json
import os
import time

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

        if eco_cog:
            embed = discord.Embed(title="🏦 ฝากเงินเข้าธนาคารพาณิชย์", color=discord.Color.green())
            embed.add_field(name="ผู้ทำรายการ", value=f"{interaction.user.mention} ({interaction.user.id})", inline=False)
            embed.add_field(name="สาขาธนาคาร", value=f"{self.bank_name}", inline=False)
            embed.add_field(name="จำนวนเงิน", value=f"+ {amt:,} บาท", inline=False)
            await eco_cog.log_transaction(embed)

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

        if eco_cog:
            embed = discord.Embed(title="📤 ถอนเงินจากธนาคารพาณิชย์", color=discord.Color.orange())
            embed.add_field(name="ผู้ทำรายการ", value=f"{interaction.user.mention} ({interaction.user.id})", inline=False)
            embed.add_field(name="สาขาธนาคาร", value=f"{self.bank_name}", inline=False)
            embed.add_field(name="จำนวนเงิน", value=f"- {amt:,} บาท", inline=False)
            await eco_cog.log_transaction(embed)

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

        if eco_cog:
            embed = discord.Embed(title="💸 กู้ยอดเงินคงคลังธนาคาร", color=discord.Color.red())
            embed.add_field(name="ผู้ขอกู้", value=f"{interaction.user.mention} ({interaction.user.id})", inline=False)
            embed.add_field(name="สาขาธนาคาร", value=f"{self.bank_name}", inline=False)
            embed.add_field(name="ยอดเงินขอกู้", value=f"{amt:,} บาท", inline=False)
            embed.add_field(name="ภาระหนี้สินรวม", value=f"{current_loan + amt:,} บาท", inline=False)
            await eco_cog.log_transaction(embed)

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

        if eco_cog:
            embed = discord.Embed(title="💳 ชำระหนี้ธนาคารย่อย", color=discord.Color.blue())
            embed.add_field(name="ผู้ชำระหนี้", value=f"{interaction.user.mention} ({interaction.user.id})", inline=False)
            embed.add_field(name="สาขาธนาคาร", value=f"{self.bank_name}", inline=False)
            embed.add_field(name="ยอดเงินชำระ", value=f"{amt:,} บาท", inline=False)
            embed.add_field(name="ยอดหนี้คงเหลือ", value=f"{current_loan - amt:,} บาท", inline=False)
            await eco_cog.log_transaction(embed)

# --- Management UI (setting_bank) ---

class CreateBankModal(ui.Modal, title="สร้างธนาคารใหม่"):
    bank_name = ui.TextInput(label="ชื่อธนาคาร", placeholder="ตัวอย่าง: กสิกรไทย", required=True)
    deposit_rate = ui.TextInput(label="อัตราดอกเบี้ยเงินฝาก (%)", placeholder="ตัวอย่าง: 3.5", required=True)
    loan_rate = ui.TextInput(label="อัตราดอกเบี้ยเงินกู้ (%)", placeholder="ตัวอย่าง: 5.0", required=True)
    description = ui.TextInput(label="ข้อความอธิบาย (ไม่บังคับ)", placeholder="สโลแกนหรือข้อมูลเพิ่มเติม", required=False, style=discord.TextStyle.paragraph)

    def __init__(self, cog):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        name = self.bank_name.value
        try:
            dep_rate = float(self.deposit_rate.value)
            lo_rate = float(self.loan_rate.value)
        except ValueError:
            return await interaction.response.send_message("❌ อัตราดอกเบี้ยต้องเป็นตัวเลขเท่านั้น", ephemeral=True)

        if name in self.cog.data["sub_banks"]:
            return await interaction.response.send_message(f"❌ มีธนาคารชื่อ {name} อยู่ในระบบแล้ว", ephemeral=True)

        self.cog.data["sub_banks"][name] = {
            "name": name,
            "owner_id": interaction.user.id,
            "deposit_rate": dep_rate,
            "loan_rate": lo_rate,
            "description": self.description.value or "",
            "accounts": {},
            "loans": {},
            "dashboard": {"channel_id": None, "msg_info": None, "msg_users": None, "msg_menu": None}
        }
        self.cog.save_data()
        await interaction.response.send_message(f"✅ สร้างธนาคาร **{name}** เรียบร้อยแล้ว\n*(อย่าลืมใช้คำสั่ง `/setup_minbank` เพื่อเสกบอร์ดธนาคารลงแชท)*", ephemeral=True)


class BankSettingView(ui.View):
    def __init__(self, cog):
        super().__init__(timeout=180)
        self.cog = cog

    @ui.select(
        placeholder="เลือกรายการที่ต้องการจัดการ...",
        options=[
            discord.SelectOption(label="สร้างธนาคาร (Create Bank)", description="เปิดธนาคารพาณิชย์สาขาใหม่", value="create", emoji="🏗️"),
            discord.SelectOption(label="แก้ไขธนาคาร (Edit Bank)", description="แก้ไขชื่อ, ดอกเบี้ย, หรือระงับบัญชีโอนย้ายเจ้าของ", value="edit", emoji="✏️"),
            discord.SelectOption(label="ลบธนาคาร (Delete Bank)", description="ยกเลิกกิจการ (ดึงเงินคืนให้ลูกค้าทั้งหมดออโต้)", value="delete", emoji="🗑️")
        ]
    )
    async def select_callback(self, interaction: discord.Interaction, select: discord.ui.Select):
        val = select.values[0]
        if val == "create":
            await interaction.response.send_modal(CreateBankModal(self.cog))
        elif val == "edit":
            await interaction.response.send_message("🚧 เลือกระบบธนาคารของคุณ...", view=SelectBankToEditView(self.cog, "edit"), ephemeral=True)
        elif val == "delete":
            await interaction.response.send_message("🚧 เลือกระบบธนาคารที่ต้องการลบกวาดล้าง...", view=SelectBankToEditView(self.cog, "delete"), ephemeral=True)


class SelectBankToEditView(ui.View):
    def __init__(self, cog, action_type):
        super().__init__(timeout=180)
        self.cog = cog
        self.action_type = action_type
        self.add_bank_select()

    def add_bank_select(self):
        options = []
        if not self.cog.data["sub_banks"]:
            options.append(discord.SelectOption(label="ไม่มีธนาคารในระบบ", value="none"))
        else:
            for b_name in self.cog.data["sub_banks"].keys():
                options.append(discord.SelectOption(label=f"ธนาคาร {b_name}", value=b_name))
        
        select = ui.Select(placeholder="เลือกธนาคาร...", options=options[:25])
        select.callback = self.select_callback
        self.add_item(select)

    async def select_callback(self, interaction: discord.Interaction):
        select = self.children[0]
        b_name = select.values[0]
        if b_name == "none":
            return await interaction.response.send_message("❌ ยังไม่มีธนาคาร", ephemeral=True)

        bank_data = self.cog.data["sub_banks"][b_name]
        is_admin = interaction.user.guild_permissions.administrator
        is_owner = (bank_data.get("owner_id") == interaction.user.id)
        
        if not (is_admin or is_owner):
            return await interaction.response.send_message("❌ คุณไม่ใช่เจ้าของธนาคารนี้", ephemeral=True)

        if self.action_type == "delete":
            await interaction.response.send_message(
                f"⚠️ คุณต้องการลบธนาคาร **{b_name}** ทิ้งใช่หรือไม่?\n*(เงินของผู้ฝากจะถูกโอนคืนอัตโนมัติ)*",
                view=ConfirmDeleteBankView(self.cog, b_name), ephemeral=True
            )
        else:
            await interaction.response.send_message(f"✏️ เลือกการตั้งค่าธนาคาร **{b_name}**:", view=EditBankOptionView(self.cog, b_name), ephemeral=True)


class ConfirmDeleteBankView(ui.View):
    def __init__(self, cog, bank_name):
        super().__init__(timeout=60)
        self.cog = cog
        self.bank_name = bank_name

    @ui.button(label="ยืนยันการลบ", style=discord.ButtonStyle.danger)
    async def btn_confirm(self, interaction: discord.Interaction, button: ui.Button):
        bank_data = self.cog.data["sub_banks"][self.bank_name]
        eco_cog = self.cog.bot.get_cog('Economy')
        
        refund_amount = 0
        refund_count = 0
        
        if eco_cog:
            for uid, acc in bank_data.get("accounts", {}).items():
                bal = acc.get("balance", 0)
                if bal > 0:
                    eco_cog.update_balance(uid, bal, "wallet")
                    refund_amount += bal
                    refund_count += 1
        
        dash = bank_data.get("dashboard")
        if dash and dash.get("channel_id"):
            try:
                ch = self.cog.bot.get_channel(dash["channel_id"])
                if ch:
                    for k in ["msg_info", "msg_users", "msg_menu"]:
                        if dash.get(k):
                            msg = await ch.fetch_message(dash[k])
                            await msg.delete()
            except Exception: pass

        del self.cog.data["sub_banks"][self.bank_name]
        self.cog.save_data()
        
        await interaction.response.send_message(f"✅ ลบธนาคาร **{self.bank_name}** เรียบร้อยแล้ว!\n(โอนเงินคืน {refund_count} บัญชี รวมมูลค่า {refund_amount:,} บาท)", ephemeral=True)

    @ui.button(label="ยกเลิก", style=discord.ButtonStyle.secondary)
    async def btn_cancel(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_message("✅ ยกเลิกการลบธนาคาร", ephemeral=True)

class EditBankOptionView(ui.View):
    def __init__(self, cog, bank_name):
        super().__init__(timeout=180)
        self.cog = cog
        self.bank_name = bank_name
        
    @ui.select(
        placeholder="เลือกสิ่งที่ต้องการแก้ไข...",
        options=[
            discord.SelectOption(label="เปลี่ยนชื่อธนาคาร", value="edit_name"),
            discord.SelectOption(label="แก้ไขรูปหน้าปก (Thumbnail)", value="edit_thumb", description="ใส่ URL ของรูปภาพโลโก้ธนาคาร"),
            discord.SelectOption(label="แก้ไขดอกเบี้ย (ฝาก/กู้)", value="edit_rate"),
            discord.SelectOption(label="แก้ไขข้อความอธิบาย", value="edit_desc"),
            discord.SelectOption(label="ระงับ/ลบบัญชีลูกหนี้ (Suspend)", value="suspend", description="บังคับคืนเงินเข้ากระเป๋าและลบบัญชีที่เปิดไว้"),
            discord.SelectOption(label="เปลี่ยนเจ้าของธนาคาร", value="change_owner")
        ]
    )
    async def opt_select(self, interaction: discord.Interaction, select: ui.Select):
        val = select.values[0]
        if val == "edit_name":
            await interaction.response.send_modal(EditNameModal(self.cog, self.bank_name))
        elif val == "edit_thumb":
            await interaction.response.send_modal(EditThumbModal(self.cog, self.bank_name))
        elif val == "edit_rate":
            await interaction.response.send_modal(EditRateModal(self.cog, self.bank_name))
        elif val == "edit_desc":
            await interaction.response.send_modal(EditDescModal(self.cog, self.bank_name))
        elif val == "change_owner":
            await interaction.response.send_message("👤 เลือกเจ้าของใหม่ที่เมนูด้านล่างนี้:", view=ChangeOwnerView(self.cog, self.bank_name), ephemeral=True)
        elif val == "suspend":
            await interaction.response.send_message("🚫 เลือกลูกค้าที่คุณต้องการระงับบัญชี (ลบบัญชีเพื่อโอนคืน):", view=SuspendUserSelectView(self.cog, self.bank_name), ephemeral=True)


class EditNameModal(ui.Modal):
    new_name = ui.TextInput(label="ชื่อธนาคารใหม่", required=True)
    def __init__(self, cog, old_name):
        super().__init__(title="แก้ชื่อธนาคาร")
        self.cog = cog
        self.old_name = old_name
    async def on_submit(self, interaction: discord.Interaction):
        nname = self.new_name.value
        if nname in self.cog.data["sub_banks"]:
            return await interaction.response.send_message("❌ ชื่อนี้มีอยู่แล้ว", ephemeral=True)
            
        bd = self.cog.data["sub_banks"][self.old_name]
        bd["name"] = nname
        self.cog.data["sub_banks"][nname] = bd
        del self.cog.data["sub_banks"][self.old_name]
        self.cog.save_data()
        
        await self.cog._update_subbank_dashboard(nname)
        await interaction.response.send_message(f"✅ เปลี่ยนชื่อเป็น **{nname}** แล้ว", ephemeral=True)

class EditRateModal(ui.Modal):
    dep_rate = ui.TextInput(label="ดอกเบี้ยเงินฝาก (%)", required=True)
    lo_rate = ui.TextInput(label="ดอกเบี้ยเงินกู้ (%)", required=True)
    def __init__(self, cog, b_name):
        super().__init__(title="แก้ไขดอกเบี้ย")
        self.cog = cog
        self.b_name = b_name
        bd = cog.data["sub_banks"][b_name]
        self.dep_rate.default = str(bd.get("deposit_rate", 0))
        self.lo_rate.default = str(bd.get("loan_rate", 0))
    async def on_submit(self, interaction: discord.Interaction):
        try:
            d = float(self.dep_rate.value)
            l = float(self.lo_rate.value)
        except: return await interaction.response.send_message("❌ ต้องเป็นเลข", ephemeral=True)
        self.cog.data["sub_banks"][self.b_name]["deposit_rate"] = d
        self.cog.data["sub_banks"][self.b_name]["loan_rate"] = l
        self.cog.save_data()
        await self.cog._update_subbank_dashboard(self.b_name)
        await interaction.response.send_message(f"✅ แก้ไขดอกเบี้ยแล้ว", ephemeral=True)

class EditDescModal(ui.Modal):
    desc = ui.TextInput(label="ข้อความอธิบาย", style=discord.TextStyle.paragraph, required=False)
    def __init__(self, cog, b_name):
        super().__init__(title="แก้ไขคำอธิบาย")
        self.cog = cog
        self.b_name = b_name
        self.desc.default = cog.data["sub_banks"][b_name].get("description", "")
    async def on_submit(self, interaction: discord.Interaction):
        self.cog.data["sub_banks"][self.b_name]["description"] = self.desc.value
        self.cog.save_data()
        await self.cog._update_subbank_dashboard(self.b_name)
        await interaction.response.send_message(f"✅ แก้ไขคำอธิบายแล้ว", ephemeral=True)

class EditThumbModal(ui.Modal):
    thumb_url = ui.TextInput(label="URL ของรูปภาพ", placeholder="ขึ้นต้นด้วย http:// หรือ https://", required=True)
    def __init__(self, cog, b_name):
        super().__init__(title="แก้ไขรูปภาพหน้าปก")
        self.cog = cog
        self.b_name = b_name
        self.thumb_url.default = cog.data["sub_banks"][b_name].get("thumbnail", "https://cdn-icons-png.flaticon.com/512/2830/2830284.png")
    async def on_submit(self, interaction: discord.Interaction):
        url = self.thumb_url.value
        if not url.startswith("http"):
            return await interaction.response.send_message("❌ ต้องเป็นลิงก์ URL ที่ขึ้นต้นด้วย http หรือ https", ephemeral=True)
            
        self.cog.data["sub_banks"][self.b_name]["thumbnail"] = url
        self.cog.save_data()
        await self.cog._update_subbank_dashboard(self.b_name)
        await interaction.response.send_message(f"✅ บันทึกรูปภาพหน้าปกเรียบร้อย", ephemeral=True)

class ChangeOwnerView(ui.View):
    def __init__(self, cog, b_name):
        super().__init__(timeout=60)
        self.cog = cog
        self.b_name = b_name
    
    @ui.select(cls=ui.UserSelect, placeholder="เลือกผู้ใช้งานที่จะให้เป็นเจ้าของ...")
    async def u_select(self, interaction: discord.Interaction, select: ui.UserSelect):
        n_owner = select.values[0]
        self.cog.data["sub_banks"][self.b_name]["owner_id"] = n_owner.id
        self.cog.save_data()
        await interaction.response.send_message(f"✅ โอนธนาคาร **{self.b_name}** ให้ {n_owner.mention} เป็นเจ้าของเรียบร้อย!", ephemeral=True)

class SuspendUserSelectView(ui.View):
    def __init__(self, cog, b_name):
        super().__init__(timeout=60)
        self.cog = cog
        self.b_name = b_name
        self.setup_options()
        
    def setup_options(self):
        opts = []
        accs = self.cog.data["sub_banks"][self.b_name].get("accounts", {})
        for uid, acc in list(accs.items())[:25]:
            bal = acc.get('balance', 0)
            loan = self.cog.data["sub_banks"][self.b_name].get("loans", {}).get(uid, 0)
            opts.append(discord.SelectOption(label=f"ID: {uid}", description=f"ฝาก: {bal} | หนี้: {loan}", value=uid))
            
        if not opts:
            opts = [discord.SelectOption(label="ไม่มีลูกค้าให้แบน", value="none")]
            
        sel = ui.Select(placeholder="เลือกลูกค้าที่จะระงับบัญชีโอนคืน...", options=opts)
        sel.callback = self.on_suspend
        self.add_item(sel)
        
    async def on_suspend(self, interaction: discord.Interaction):
        uid = self.children[0].values[0]
        if uid == "none": return await interaction.response.send_message("❌ ยกเลิก", ephemeral=True)
        
        bd = self.cog.data["sub_banks"][self.b_name]
        bal = bd["accounts"].get(uid, {}).get("balance", 0)
        if bal > 0:
            eco = self.cog.bot.get_cog('Economy')
            if eco: eco.update_balance(uid, bal, "wallet")
            
        if uid in bd["accounts"]:
            del bd["accounts"][uid]
        if uid in bd.get("loans", {}):
            del bd["loans"][uid]
            
        self.cog.save_data()
        await self.cog._update_subbank_dashboard(self.b_name)
        await interaction.response.send_message(f"✅ ระงับบัญชีของ User ID {uid} และโอนเงินคืน {bal:,} บาท ให้เขาแล้ว", ephemeral=True)

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
            dash = b_data.get("dashboard", {})
            if dash.get("msg_users") == message_id or dash.get("msg_info") == message_id or dash.get("msg_menu") == message_id:
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

        if hasattr(self.cog, 'bot'):
            eco = self.cog.bot.get_cog('Economy')
            if eco:
                embed = discord.Embed(title="📝 เปิดบัญชีใหม่", color=discord.Color.green())
                embed.add_field(name="ผู้ทำรายการ", value=f"{interaction.user.mention} ({interaction.user.id})", inline=False)
                embed.add_field(name="สาขาธนาคาร", value=f"{bank_name}", inline=False)
                await eco.log_transaction(embed)

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
        self.interest_loop.start()

    def cog_unload(self):
        self.interest_loop.cancel()

    @tasks.loop(minutes=30)
    async def interest_loop(self):
        next_run = self.data["central"].get("next_interest_run", 0)
        now = time.time()
        
        # ถ้าพ้น 7 วัน (หรือเป็น 0 ค่าเริ่มต้น)
        if now >= next_run:
            await self._process_interest()

    @interest_loop.before_loop
    async def before_interest_loop(self):
        await self.bot.wait_until_ready()

    async def _process_interest(self):
        for bank_name, b_data in self.data["sub_banks"].items():
            dep_rate = b_data.get("deposit_rate", 0)
            loan_rate = b_data.get("loan_rate", 0)
            
            # ดอกเบี้ยเงินฝาก (ทบเข้าสมุดบัญชี)
            if dep_rate > 0:
                for uid, acc in b_data.get("accounts", {}).items():
                    bal = acc.get("balance", 0)
                    if bal > 0:
                        interest = int(bal * (dep_rate / 100.0))
                        acc["balance"] += interest
                        
            # ดอกเบี้ยเงินกู้ (ทบเข้ายอดหนี้คงเหลือ)
            if loan_rate > 0:
                loans = b_data.get("loans", {})
                for uid, loan in loans.items():
                    if loan > 0:
                        l_interest = int(loan * (loan_rate / 100.0))
                        loans[uid] += l_interest
            
            # อัปเดตบอร์ดตามปกติ
            try:
                await self._update_subbank_dashboard(bank_name)
            except Exception as e:
                print(f"Auto-update error {bank_name}: {e}")

        # เซ็ตเวลาแจกจ่ายรอบหน้าคือ 7 วัน (7 x 24 x 60 x 60 วินาที) นับจากวินาทีนี้
        self.data["central"]["next_interest_run"] = time.time() + (7 * 24 * 60 * 60)
        self.save_data()

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
        await interaction.response.defer(ephemeral=True)
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
        await interaction.followup.send("✅ สร้างบอร์ดธนาคารกลางเสร็จสิ้นแล้ว", ephemeral=True)

    async def bank_name_autocomplete(self, interaction: discord.Interaction, current: str):
        banks = list(self.data.get("sub_banks", {}).keys())
        filtered = [bank for bank in banks if current.lower() in bank.lower()]
        return [app_commands.Choice(name=bank, value=bank) for bank in filtered[:25]]

    @app_commands.command(name="setup_minbank", description="[Admin/Owner] เสกบอร์ดธนาคารพาณิชย์ลงในแชทนี้")
    @app_commands.describe(bank_name="ชื่อธนาคารย่อยที่มีอยู่ในระบบแล้ว")
    @app_commands.autocomplete(bank_name=bank_name_autocomplete)
    async def setup_minbank(self, interaction: discord.Interaction, bank_name: str):
        await interaction.response.defer(ephemeral=True)
        
        if bank_name not in self.data["sub_banks"]:
            return await interaction.followup.send(f"❌ ไม่พบธนาคาร **{bank_name}** ในระบบ! กรุณาสร้างด้วยคำสั่ง `/setting_bank` ก่อน", ephemeral=True)
            
        bank_data = self.data["sub_banks"][bank_name]
        is_admin = interaction.user.guild_permissions.administrator
        is_owner = (bank_data.get("owner_id") == interaction.user.id)
        
        if not (is_admin or is_owner):
            return await interaction.followup.send(f"❌ คุณไม่ใช่เจ้าของธนาคาร **{bank_name}** และไม่มีสิทธิ์สั่งงานนี้", ephemeral=True)

        old_dash = self.data["sub_banks"][bank_name].get("dashboard")
        if old_dash and old_dash.get("msg_info"):
            try:
                old_ch = self.bot.get_channel(old_dash["channel_id"])
                if old_ch:
                    await (await old_ch.fetch_message(old_dash["msg_info"])).delete()
                    if old_dash.get("msg_users"):
                        await (await old_ch.fetch_message(old_dash["msg_users"])).delete()
                    if old_dash.get("msg_menu"):
                        await (await old_ch.fetch_message(old_dash["msg_menu"])).delete()
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
        await interaction.followup.send(f"✅ สร้างบอร์ดธนาคารพาณิชย์ {bank_name} สำเร็จ", ephemeral=True)

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
            embed.add_field(name="<:__:1459385992040546559> เงินคงคลัง (System Bank)", value=f"**{system_bal:,}** บาท", inline=False)
            embed.set_thumbnail(url="")
            
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
            
            deposit_r = bank_data.get("deposit_rate", 0)
            loan_r = bank_data.get("loan_rate", 0)
            
            desc = bank_data.get("description", "")
            if not desc:
                desc = "ผลตอบแทนมั่นคง บริการดุจญาติมิตร"
            
            embed1 = discord.Embed(title=f"<:__:1459385992040546559> ธนาคารพาณิชย์ {bank_name}", description=desc, color=discord.Color.blue())
            embed1.add_field(name="📈 อัตราดอกเบี้ยเงินฝาก", value=f"**{deposit_r}%** ต่อรอบ", inline=True)
            embed1.add_field(name="📉 อัตราดอกเบี้ยเงินกู้", value=f"**{loan_r}%** ต่อรอบ", inline=True)
            
            thumb = bank_data.get("thumbnail", "https://cdn-icons-png.flaticon.com/512/2830/2830284.png")
            embed1.set_thumbnail(url=thumb)
            
            users_txt = ""
            # Sort by balance descending
            sorted_accounts = sorted(bank_data.get("accounts", {}).items(), key=lambda x: x[1]['balance'], reverse=True)
            for uid, acc in sorted_accounts:
                bal = acc.get("balance", 0)
                loan = bank_data.get("loans", {}).get(uid, 0)
                
                info = f"🔹 <@{uid}>: ฝาก **{bal:,}**"
                if loan > 0:
                    info += f" | หนี้ **{loan:,}**"
                users_txt += info + "\n"
                
            if not users_txt:
                users_txt = "ยังไม่มีผู้เปิดบัญชี"
                
            embed2 = discord.Embed(title="👥 รายชื่อผู้ถือบัญชี (สมุดบัญชีเงินฝาก)", description=users_txt, color=discord.Color.dark_blue())
            
            await msg1.edit(embed=embed1, view=None)
            await msg2.edit(embed=embed2, view=SubBankView(self))
            
        except Exception as e:
            print(f"Error updating subbank: {e}")

    @app_commands.command(name="setting_bank", description="[Bank Officer/Admin] จัดการธนาคาร (สร้าง/แก้ไข/ลบ)")
    async def setting_bank(self, interaction: discord.Interaction):
        # Check permissions: Admin or has "เจ้าหน้าที่ธนาคาร" role
        has_perm = interaction.user.guild_permissions.administrator
        if not has_perm:
            has_perm = any(role.name == "𝐁𝐚𝐧𝐤 𝐄𝐱𝐞𝐜𝐮𝐭𝐢𝐯𝐞𝐬 | เจ้าหน้าที่ธนาคาร" for role in interaction.user.roles)
            
        if not has_perm:
            return await interaction.response.send_message("❌ คุณไม่มีสิทธิ์ใช้งานคำสั่งนี้ (ต้องเป็นแอดมินหรือ 'เจ้าหน้าที่ธนาคาร')", ephemeral=True)
            
        embed = discord.Embed(
            title="⚙️ ระบบจัดการธนาคารพาณิชย์",
            description="เลือกระบบที่คุณต้องการจัดการจากเมนูด้านล่างนี้ครับ",
            color=discord.Color.dark_theme()
        )
        # We will add BankSettingView() next
        await interaction.response.send_message(embed=embed, view=BankSettingView(self), ephemeral=True)

    @app_commands.command(name="dev_force_interest", description="[Admin/Dev] แจกดอกเบี้ยเดี๋ยวนี้ (เร่งเวลาล่วงหน้า 7 วัน)")
    @app_commands.default_permissions(administrator=True)
    async def dev_force_interest(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await self._process_interest()
        await interaction.followup.send("✅ แจกดอกเบี้ยสำเร็จ! ยอดเงินฝากและยอดหนี้ของทุกคนถูกบวกทบขึ้นตาม % เรียบร้อย", ephemeral=True)

async def setup(bot):
    await bot.add_cog(Bank(bot))
