import discord
from discord.ext import commands
from discord import app_commands, ui
import json
import os

DB_FILE = "json/crypto_data.json"

class TradeQuantityModal(ui.Modal):
    amount = ui.TextInput(label="จำนวนที่ต้องการ", placeholder="ใส่ตัวเลข...", required=True)
    
    def __init__(self, cog, symbol, action_type, parent_view):
        title_action = "ซื้อ" if action_type == 'buy' else "ขาย"
        super().__init__(title=f"{title_action} หุ้น {symbol}")
        self.cog = cog
        self.symbol = symbol
        self.action_type = action_type
        self.parent_view = parent_view

    async def on_submit(self, interaction: discord.Interaction):
        try:
            qty = float(self.amount.value)
            if qty <= 0:
                await interaction.response.send_message("<:w_:1459388961943457934> จำนวนต้องมากกว่า 0", ephemeral=True)
                return
            
            # ปรับเป็นเลขจำนวนเต็มถ้าเป็นไปได้ เพื่อความสวยงาม
            if qty.is_integer():
                qty = int(qty)
                
            await self.parent_view.update_quantity(interaction, qty)
        except ValueError:
             await interaction.response.send_message("<:w_:1459388961943457934> กรุณาใส่ตัวเลขที่ถูกต้อง", ephemeral=True)

class TradeProcessView(ui.View):
    def __init__(self, cog):
        super().__init__(timeout=300)
        self.cog = cog
        self.symbol = None
        self.action_type = None
        self.quantity = None

        # ตั้งค่าเลือกหุ้น
        market = self.cog.data.get("market", {})
        options = [discord.SelectOption(label=s, value=s, description=f"ราคา: {d['price']:,} บาท") for s, d in market.items()]
        
        if not options:
            options = [discord.SelectOption(label="ไม่มีหุ้นในตลาด", value="none")]
        
        self.stock_select = ui.Select(placeholder="เลือกหุ้นที่ต้องการ...", options=options, row=0)
        self.stock_select.callback = self.stock_callback
        self.add_item(self.stock_select)

        # เลือกประเภทการเทรด
        self.type_select = ui.Select(placeholder="เลือกประเภท (ซื้อ/ขาย)...", options=[
            discord.SelectOption(label="ซื้อ (Buy)", value="buy", emoji="📥"),
            discord.SelectOption(label="ขาย (Sell)", value="sell", emoji="📤")
        ], row=1)
        self.type_select.callback = self.type_callback
        self.add_item(self.type_select)

    def create_embed(self):
        sym_txt = f"**{self.symbol}**" if self.symbol else "ยังไม่ได้เลือก"
        type_txt = "**ซื้อ**" if self.action_type == 'buy' else "**ขาย**" if self.action_type == 'sell' else "ยังไม่ได้เลือก"
        qty_txt = f"**{self.quantity:,}**" if self.quantity is not None else "ยังไม่ได้ระบุ"
        
        price_txt = ""
        total_txt = ""
        if self.symbol:
            price = self.cog.data["market"][self.symbol]["price"]
            price_str = f"{int(price):,}" if isinstance(price, int) or price.is_integer() else f"{price:,.2f}"
            price_txt = f"\n**ราคาปัจจุบัน:** {price_str} บาท"
            
            if self.quantity:
                total = price * self.quantity
                total_str = f"{int(total):,}" if isinstance(total, int) or total.is_integer() else f"{total:,.2f}"
                total_txt = f"\n**รวมมูลค่า:** {total_str} บาท"

        embed = discord.Embed(title="🛒 พื้นที่ทำรายการซื้อขาย", color=discord.Color.blue())
        embed.description = f"📌 **หุ้น:** {sym_txt}{price_txt}\n⚡ **ประเภท:** {type_txt}\n🔢 **จำนวน:** {qty_txt}{total_txt}"
        embed.set_footer(text="เลือกข้อมูลให้ครบเพื่อเปิดใช้งานปุ่มยืนยัน")
        return embed

    async def update_view(self, interaction: discord.Interaction):
        # ตรวจสอบว่ากรอกครบหรือยัง
        if self.symbol and self.action_type and self.quantity is not None:
            self.confirm_button.disabled = False
        else:
            self.confirm_button.disabled = True
            
        await interaction.response.edit_message(embed=self.create_embed(), view=self)

    async def stock_callback(self, interaction: discord.Interaction):
        val = self.stock_select.values[0]
        if val == "none": return
        self.symbol = val
        await self.update_view(interaction)

    async def type_callback(self, interaction: discord.Interaction):
        self.action_type = self.type_select.values[0]
        await self.update_view(interaction)

    @ui.button(label="ระบุจำนวน", style=discord.ButtonStyle.primary, row=2)
    async def qty_button(self, interaction: discord.Interaction, button: ui.Button):
        if not self.symbol or not self.action_type:
            await interaction.response.send_message("<:w_:1459388961943457934> กรุณาเลือกหุ้นและประเภทก่อนระบุจำนวน", ephemeral=True)
            return
        await interaction.response.send_modal(TradeQuantityModal(self.cog, self.symbol, self.action_type, self))

    async def update_quantity(self, interaction: discord.Interaction, qty):
        self.quantity = qty
        await self.update_view(interaction)

    @ui.button(label="ยืนยันรายการ", emoji="<:c_:1459387176516190312>", style=discord.ButtonStyle.success, disabled=True, row=3)
    async def confirm_button(self, interaction: discord.Interaction, button: ui.Button):
        # ดำเนินการเทรด P2P (คัดลอก Logic เดิมมาปรับใช้)
        market_data = self.cog.get_market_price(self.symbol)
        current_price = market_data['price']
        total_cost = current_price * self.quantity
        
        economy_cog = self.cog.bot.get_cog('Economy')
        user_id = str(interaction.user.id)
        owner_id = market_data.get('owner_id')
        owner_id_str = str(owner_id) if owner_id else None
        
        cost_str = f"{int(total_cost):,}" if isinstance(total_cost, int) or total_cost.is_integer() else f"{total_cost:,.2f}"
        qty_str = f"{int(self.quantity):,}" if isinstance(self.quantity, int) or self.quantity.is_integer() else f"{self.quantity:,}"

        if self.action_type == 'buy':
            bal = economy_cog.get_balance(user_id)
            if bal['wallet'] < total_cost:
                 await interaction.response.send_message(f"<:w_:1459388961943457934> เงินไม่พอ! (ต้องการ {cost_str} บาท)", ephemeral=True)
                 return
            
            economy_cog.update_balance(user_id, -total_cost, "wallet")
            if owner_id_str and owner_id_str != user_id:
                economy_cog.update_balance(owner_id_str, total_cost, "bank")
                owner_msg = f" (เงินโอนเข้าธนาคารเจ้าของหุ้น)"
            else:
                owner_msg = ""
            self.cog.update_portfolio(user_id, self.symbol, self.quantity)
            await interaction.response.edit_message(content=f"<:c_:1459387176516190312> ซื้อ **{self.symbol}** {qty_str} หน่วย เรียบร้อยแล้ว!{owner_msg}", embed=None, view=None)

            if hasattr(economy_cog, 'log_transaction'):
                log_emb = discord.Embed(title="📈 ซื้อหุ้น (Crypto)", color=discord.Color.green())
                log_emb.add_field(name="ผู้ซื้อ", value=f"{interaction.user.mention} ({interaction.user.id})", inline=False)
                log_emb.add_field(name="ชื่อหุ้น", value=f"{self.symbol}", inline=True)
                log_emb.add_field(name="จำนวน", value=f"{qty_str} หน่วย", inline=True)
                log_emb.add_field(name="ราคารวม", value=f"{cost_str} บาท", inline=True)
                await economy_cog.log_transaction(log_emb)

        elif self.action_type == 'sell':
            current_qty = self.cog.get_portfolio(user_id).get(self.symbol, 0)
            if current_qty < self.quantity:
                await interaction.response.send_message(f"<:w_:1459388961943457934> มีหุ้นไม่พอขาย!", ephemeral=True)
                return

            if owner_id_str and owner_id_str != user_id:
                owner_bal = economy_cog.get_balance(owner_id_str)
                if owner_bal['bank'] < total_cost:
                    await interaction.response.send_message(f"<:w_:1459388961943457934> เจ้าของหุ้นมีเงินไม่พอจ่ายคืน!", ephemeral=True)
                    return
                economy_cog.update_balance(owner_id_str, -total_cost, "bank")
                owner_msg = f" (หักจากธนาคารเจ้าของหุ้น)"
            else:
                owner_msg = ""

            economy_cog.update_balance(user_id, total_cost, "wallet")
            self.cog.update_portfolio(user_id, self.symbol, -self.quantity)
            await interaction.response.edit_message(content=f"<:c_:1459387176516190312> ขาย **{self.symbol}** {qty_str} หน่วย เรียบร้อยแล้ว!{owner_msg}", embed=None, view=None)

            if hasattr(economy_cog, 'log_transaction'):
                log_emb = discord.Embed(title="📉 ขายหุ้น (Crypto)", color=discord.Color.red())
                log_emb.add_field(name="ผู้ขาย", value=f"{interaction.user.mention} ({interaction.user.id})", inline=False)
                log_emb.add_field(name="ชื่อหุ้น", value=f"{self.symbol}", inline=True)
                log_emb.add_field(name="จำนวน", value=f"{qty_str} หน่วย", inline=True)
                log_emb.add_field(name="ได้เงินรวม", value=f"{cost_str} บาท", inline=True)
                await economy_cog.log_transaction(log_emb)

    @ui.button(label="ยกเลิก", emoji="<:w_:1459388961943457934>", style=discord.ButtonStyle.danger, row=3)
    async def cancel_button(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.edit_message(content="<:w_:1459388961943457934> ยกเลิกรายการแล้ว", embed=None, view=None)

class StockModal(ui.Modal):
    def __init__(self, title, symbol_default="", price_default="", action="add"):
        super().__init__(title=title)
        self.action = action
        self.symbol_input = ui.TextInput(label="ชื่อหุ้น (Symbol)", placeholder="เช่น PTT, BTC...", default=symbol_default, required=True if action == "add" else False)
        self.price_input = ui.TextInput(label="ราคาเริ่มต้น", placeholder="ใส่ตัวเลข...", default=str(price_default), required=True)
        
        if action == "add":
            self.add_item(self.symbol_input)
        self.add_item(self.price_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            price = float(self.price_input.value)
            if price < 0: raise ValueError
        except ValueError:
            await interaction.response.send_message("<:w_:1459388961943457934> กรุณาใส่ราคาที่ถูกต้อง (ตัวเลขมากกว่าหรือเท่ากับ 0)", ephemeral=True)
            return
        
        symbol = self.symbol_input.value.upper() if self.action == "add" else None
        self.interaction_result = (symbol, price)
        self.stop()
        await interaction.response.defer()

class StockManageView(ui.View):
    def __init__(self, cog, user):
        super().__init__(timeout=300)
        self.cog = cog
        self.user = user
        self.temp_symbol = None
        self.temp_price = None

    def create_initial_embed(self):
        embed = discord.Embed(title="⚙️ จัดการระบบหุ้น", description="กรุณาเลือกสิ่งที่ต้องการทำจากเมนูด้านล่าง", color=discord.Color.blue())
        embed.set_footer(text=f"ร้องขอโดย: {self.user.display_name}")
        return embed

    @ui.select(placeholder="เลือกการทำงาน...", options=[
        discord.SelectOption(label="เพิ่มหุ้นใหม่", value="add", emoji="➕", description="สร้างหุ้นตัวใหม่เข้าตลาด"),
        discord.SelectOption(label="แก้ไขราคาหุ้น", value="edit", emoji="📝", description="เปลี่ยนราคาหุ้นที่เป็นเจ้าของ"),
        discord.SelectOption(label="โอนกรรมสิทธิ์", value="transfer", emoji="🤝", description="โอนเจ้าของหุ้นให้คนอื่น"),
        discord.SelectOption(label="ลบหุ้นออก", value="delete", emoji="🗑️", description="ลบหุ้นออกจากตลาด")
    ])
    async def action_select(self, interaction: discord.Interaction, select: ui.Select):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("<:w_:1459388961943457934> นี่ไม่ใช่เมนูของคุณ!", ephemeral=True)
            return

        val = select.values[0]
        if val == "add":
            await self.show_add_menu(interaction)
        elif val == "edit":
            await self.show_edit_menu(interaction)
        elif val == "delete":
            await self.show_delete_menu(interaction)
        elif val == "transfer":
            await self.show_transfer_menu(interaction)

    async def show_add_menu(self, interaction: discord.Interaction):
        self.temp_symbol = None
        self.temp_price = None

        def update_embed():
            embed = discord.Embed(title="➕ เพิ่มหุ้นใหม่", description="กรุณาเลือกตั้งค่าชื่อและราคาทีละอย่างให้ครบ", color=discord.Color.green())
            sym_display = self.temp_symbol if self.temp_symbol else "ยังไม่ได้ตั้งค่า"
            pri_display = f"{self.temp_price:,}" if self.temp_price is not None else "ยังไม่ได้ตั้งค่า"
            embed.add_field(name="ชื่อหุ้น (Symbol)", value=sym_display, inline=True)
            embed.add_field(name="ราคาเริ่มต้น", value=pri_display, inline=True)
            return embed

        view = ui.View(timeout=180)
        
        select = ui.Select(placeholder="เลือกสิ่งที่ต้องการตั้งค่า...", options=[
            discord.SelectOption(label="ตั้งชื่อหุ้น (Symbol)", value="set_sym", emoji="🔤"),
            discord.SelectOption(label="ตั้งราคาหุ้น", value="set_price", emoji="💰")
        ])

        confirm_btn = ui.Button(label="ยืนยันการเพิ่มหุ้น", style=discord.ButtonStyle.success, disabled=True)
        
        async def select_callback(inter):
            if inter.user.id != self.user.id:
                await inter.response.send_message("<:w_:1459388961943457934> นี่ไม่ใช่เมนูของคุณ!", ephemeral=True)
                return

            val = select.values[0]
            if val == "set_sym":
                modal = ui.Modal(title="ตั้งชื่อหุ้น")
                sym_input = ui.TextInput(label="ชื่อหุ้น (Symbol)", placeholder="เช่น PTT, BTC...", required=True, min_length=1, max_length=10)
                modal.add_item(sym_input)
                
                async def modal_submit(m_inter):
                    self.temp_symbol = sym_input.value.upper()
                    if self.temp_symbol and self.temp_price is not None:
                        confirm_btn.disabled = False
                    await m_inter.response.edit_message(embed=update_embed(), view=view)
                
                modal.on_submit = modal_submit
                await inter.response.send_modal(modal)

            elif val == "set_price":
                modal = ui.Modal(title="ตั้งราคาหุ้น")
                price_input = ui.TextInput(label="ราคาเริ่มต้น", placeholder="ใส่ตัวเลข...", required=True)
                modal.add_item(price_input)
                
                async def modal_submit(m_inter):
                    try:
                        price = float(price_input.value)
                        if price < 0: raise ValueError
                        self.temp_price = price
                        if self.temp_symbol and self.temp_price is not None:
                            confirm_btn.disabled = False
                        await m_inter.response.edit_message(embed=update_embed(), view=view)
                    except ValueError:
                        await m_inter.response.send_message("<:w_:1459388961943457934> กรุณาใส่ราคาที่ถูกต้อง (ตัวเลขมากกว่าหรือเท่ากับ 0)", ephemeral=True)
                
                modal.on_submit = modal_submit
                await inter.response.send_modal(modal)

        async def confirm_add(inter):
            if inter.user.id != self.user.id:
                await inter.response.send_message("<:w_:1459388961943457934> นี่ไม่ใช่เมนูของคุณ!", ephemeral=True)
                return
            
            self.cog.data["market"][self.temp_symbol] = {"price": self.temp_price, "owner_id": inter.user.id}
            self.cog.save_data()
            await self.cog._update_dashboard_message()
            await inter.response.edit_message(content=f"<:c_:1459387176516190312> เพิ่มหุ้น **{self.temp_symbol}** สำเร็จ!", embed=None, view=None)

        select.callback = select_callback
        confirm_btn.callback = confirm_add
        
        cancel_btn = ui.Button(label="ยกเลิก", style=discord.ButtonStyle.secondary)
        cancel_btn.callback = lambda i: i.response.edit_message(embed=self.create_initial_embed(), view=self)

        view.add_item(select)
        view.add_item(confirm_btn)
        view.add_item(cancel_btn)
        
        await interaction.response.edit_message(embed=update_embed(), view=view)

    async def show_edit_menu(self, interaction: discord.Interaction):
        # กรองเอาเฉพาะหุ้นที่ตัวเองเป็นเจ้าของ
        owned_stocks = {s: d for s, d in self.cog.data["market"].items() if d.get("owner_id") == interaction.user.id or interaction.user.guild_permissions.administrator}
        
        if not owned_stocks:
            await interaction.response.send_message("<:w_:1459388961943457934> คุณไม่ได้เป็นเจ้าของหุ้นตัวใดเลย!", ephemeral=True)
            return

        embed = discord.Embed(title="📝 แก้ไขราคาหุ้น", description="เลือกหุ้นที่คุณเป็นเจ้าของเพื่อเปลี่ยนราคา", color=discord.Color.orange())
        
        view = ui.View(timeout=180)
        options = [discord.SelectOption(label=s, value=s) for s in owned_stocks.keys()]
        
        select = ui.Select(placeholder="เลือกหุ้น...", options=options)
        
        async def select_to_edit(inter):
            sym = select.values[0]
            current_price = owned_stocks[sym]['price']
            modal = StockModal(f"แก้ไขราคา {sym}", price_default=current_price, action="edit")
            await inter.response.send_modal(modal)
            await modal.wait()
            if hasattr(modal, "interaction_result"):
                _, new_price = modal.interaction_result
                new_embed = discord.Embed(title="📝 ยืนยันการเปลี่ยนราคา", color=discord.Color.orange())
                new_embed.add_field(name="หุ้น", value=sym)
                new_embed.add_field(name="ราคาเดิม", value=f"{current_price:,}")
                new_embed.add_field(name="ราคาใหม่", value=f"{new_price:,}")
                
                final_view = ui.View()
                async def confirm_edit(i):
                    self.cog.data["market"][sym]["price"] = new_price
                    self.cog.save_data()
                    await self.cog._update_dashboard_message()
                    await i.response.edit_message(content=f"<:c_:1459387176516190312> เปลี่ยนราคา **{sym}** เป็น **{new_price:,}** เรียบร้อย!", embed=None, view=None)

                c_btn = ui.Button(label="ยืนยัน", style=discord.ButtonStyle.success)
                c_btn.callback = confirm_edit
                can_btn = ui.Button(label="ยกเลิก", style=discord.ButtonStyle.secondary)
                can_btn.callback = lambda i: i.response.edit_message(embed=self.create_initial_embed(), view=self)
                final_view.add_item(c_btn)
                final_view.add_item(can_btn)
                await inter.followup.edit_message(message_id=interaction.message.id, embed=new_embed, view=final_view)

        select.callback = select_to_edit
        view.add_item(select)
        
        cancel_btn = ui.Button(label="ยกเลิก", style=discord.ButtonStyle.secondary)
        cancel_btn.callback = lambda i: i.response.edit_message(embed=self.create_initial_embed(), view=self)
        view.add_item(cancel_btn)

        await interaction.response.edit_message(embed=embed, view=view)

    async def show_delete_menu(self, interaction: discord.Interaction):
        owned_stocks = {s: d for s, d in self.cog.data["market"].items() if d.get("owner_id") == interaction.user.id or interaction.user.guild_permissions.administrator}
        
        if not owned_stocks:
            await interaction.response.send_message("<:w_:1459388961943457934> คุณไม่ได้เป็นเจ้าของหุ้นตัวใดเลย!", ephemeral=True)
            return

        embed = discord.Embed(title="🗑️ ลบหุ้นออก", description="เลือกหุ้นที่ต้องการลบออกจากระบบ", color=discord.Color.red())
        
        view = ui.View(timeout=180)
        options = [discord.SelectOption(label=s, value=s) for s in owned_stocks.keys()]
        
        select = ui.Select(placeholder="เลือกหุ้นที่ต้องการลบ...", options=options)
        
        async def select_to_delete(inter):
            sym = select.values[0]
            new_embed = discord.Embed(title="⚠️ ยืนยันการลบหุ้น", description=f"คุณแน่ใจหรือไม่ที่จะลบหุ้น **{sym}** ออกจากตลาด?\n*การลบนี้จะไม่รวมถึงการยึดหุ้นที่ผู้เล่นถือครองอยู่*", color=discord.Color.red())
            
            final_view = ui.View()
            async def confirm_del(i):
                if sym in self.cog.data["market"]:
                    del self.cog.data["market"][sym]
                    self.cog.save_data()
                    await self.cog._update_dashboard_message()
                    await i.response.edit_message(content=f"<:c_:1459387176516190312> ลบหุ้น **{sym}** ออกจากตลาดแล้ว", embed=None, view=None)

            c_btn = ui.Button(label="ยืนยันการลบ", style=discord.ButtonStyle.danger)
            c_btn.callback = confirm_del
            can_btn = ui.Button(label="ยกเลิก", style=discord.ButtonStyle.secondary)
            can_btn.callback = lambda i: i.response.edit_message(embed=self.create_initial_embed(), view=self)
            
            final_view.add_item(c_btn)
            final_view.add_item(can_btn)
            await inter.response.edit_message(embed=new_embed, view=final_view)

        select.callback = select_to_delete
        view.add_item(select)
        
        cancel_btn = ui.Button(label="ยกเลิก", style=discord.ButtonStyle.secondary)
        cancel_btn.callback = lambda i: i.response.edit_message(embed=self.create_initial_embed(), view=self)
        view.add_item(cancel_btn)

        await interaction.response.edit_message(embed=embed, view=view)

    async def show_transfer_menu(self, interaction: discord.Interaction):
        owned_stocks = {s: d for s, d in self.cog.data["market"].items() if d.get("owner_id") == interaction.user.id or interaction.user.guild_permissions.administrator}
        
        if not owned_stocks:
            await interaction.response.send_message("<:w_:1459388961943457934> คุณไม่ได้เป็นเจ้าของหุ้นตัวใดเลย!", ephemeral=True)
            return

        embed = discord.Embed(title="🤝 โอนกรรมสิทธิ์หุ้น", description="กรุณาเลือกหุ้นจากเมนูด้านบน และเลือกผู้รับโอนจากเมนูด้านล่าง แล้วกดยืนยัน", color=discord.Color.purple())
        
        view = ui.View(timeout=180)
        stock_options = [discord.SelectOption(label=s, value=s) for s in owned_stocks.keys()]
        
        stock_select = ui.Select(placeholder="1. เลือกหุ้นที่ต้องการโอน...", options=stock_options, row=0)
        user_select = ui.UserSelect(placeholder="2. เลือกผู้รับโอน...", row=1)
        
        async def defer_callback(inter):
            await inter.response.defer()
            
        stock_select.callback = defer_callback
        user_select.callback = defer_callback
        
        confirm_btn = ui.Button(label="ยืนยันการโอน", style=discord.ButtonStyle.success, row=2)
        cancel_btn = ui.Button(label="ยกเลิก", style=discord.ButtonStyle.secondary, row=2)
        
        async def confirm_callback(inter):
            if inter.user.id != self.user.id:
                await inter.response.send_message("<:w_:1459388961943457934> นี่ไม่ใช่เมนูของคุณ!", ephemeral=True)
                return
                
            if not stock_select.values:
                await inter.response.send_message("<:w_:1459388961943457934> กรุณาเลือกหุ้นที่ต้องการโอน!", ephemeral=True)
                return
            if not user_select.values:
                await inter.response.send_message("<:w_:1459388961943457934> กรุณาเลือกผู้รับโอน!", ephemeral=True)
                return
                
            selected_stock = stock_select.values[0]
            target_user = user_select.values[0]
            
            if target_user.bot:
                await inter.response.send_message("<:w_:1459388961943457934> ไม่สามารถโอนให้บอทได้!", ephemeral=True)
                return
                
            self.cog.data["market"][selected_stock]["owner_id"] = target_user.id
            self.cog.save_data()
            await self.cog._update_dashboard_message()
            
            await inter.response.edit_message(content=f"<:c_:1459387176516190312> โอนหุ้น **{selected_stock}** ให้กับ {target_user.mention} สำเร็จ!", embed=None, view=None)

        confirm_btn.callback = confirm_callback
        cancel_btn.callback = lambda i: i.response.edit_message(embed=self.create_initial_embed(), view=self)
        
        view.add_item(stock_select)
        view.add_item(user_select)
        view.add_item(confirm_btn)
        view.add_item(cancel_btn)
        
        await interaction.response.edit_message(embed=embed, view=view)

class CryptoView(ui.View):
    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog
        
        status = self.cog.data.get("status", "open")
        trade_btn = [x for x in self.children if x.custom_id == "crypto_trade_btn"][0]
        
        if status == "open":
            trade_btn.style = discord.ButtonStyle.success
            trade_btn.label = "เข้าสู่พื้นที่ซื้อขาย"
            trade_btn.disabled = False
        else:
            trade_btn.style = discord.ButtonStyle.danger
            trade_btn.label = "ตลาดปิดทำการ"
            trade_btn.disabled = True

        market_len = len(self.cog.data.get("market", {}))
        max_page = max(0, (market_len - 1) // 10)
        current_page = self.cog.data.get("dashboard", {}).get("page", 0)
        
        prev_btn = [x for x in self.children if getattr(x, "custom_id", None) == "crypto_prev_btn"]
        next_btn = [x for x in self.children if getattr(x, "custom_id", None) == "crypto_next_btn"]
        
        if prev_btn and next_btn:
            if market_len <= 10:
                self.remove_item(prev_btn[0])
                self.remove_item(next_btn[0])
            else:
                prev_btn[0].disabled = (current_page == 0)
                next_btn[0].disabled = (current_page >= max_page)

    @ui.button(emoji="🛒", label="เข้าสู่พื้นที่ซื้อขาย", style=discord.ButtonStyle.success, custom_id="crypto_trade_btn", row=0)
    async def trade_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(title="🛒 เตรียมทำรายการซื้อขาย", description="กรุณาเลือกข้อมูลด่านล่างให้ครบถ้วน", color=discord.Color.blue())
        await interaction.response.send_message(embed=embed, view=TradeProcessView(self.cog), ephemeral=True)

    @ui.button(emoji="💸", label="ตรวจดูกระเป๋าหุ้น", style=discord.ButtonStyle.primary, custom_id="crypto_portfolio_btn", row=0)
    async def portfolio_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_id = interaction.user.id
        portfolio = self.cog.get_portfolio(user_id)
        market = self.cog.data.get("market", {})
        
        txt_portfolio = ""
        total_val = 0
        
        if portfolio:
            for symbol, qty in portfolio.items():
                if qty > 0:
                    data = market.get(symbol, {"price": 0})
                    price = data.get('price', 0)
                    val = price * qty
                    total_val += val
                    
                    if isinstance(val, int) or (isinstance(val, float) and val.is_integer()):
                        val_str = f"{int(val):,}"
                    else:
                        val_str = f"{val:,.2f}"
                        
                    txt_portfolio += f"🔹 **{symbol}**: {qty} หน่วย (มูลค่า {val_str} บาท)\n"
        
        if not txt_portfolio:
            txt_portfolio = "ว่างเปล่า...\n"

        owned_stocks = [sym for sym, data in market.items() if data.get('owner_id') == user_id]
        
        txt_owned = ""
        if owned_stocks:
            txt_owned = "\n👑 **หุ้นที่คุณเป็นเจ้าของ (เปิดขายในตลาด):**\n"
            for sym in owned_stocks:
                txt_owned += f"- **{sym}**\n"
            
        embed = discord.Embed(title=f"📊 พอร์ตการลงทุนของ {interaction.user.display_name}", color=discord.Color.blue())
        embed.description = f"💼 **หุ้นที่ถือครอง:**\n{txt_portfolio}{txt_owned}"
        
        total_str = f"{int(total_val):,}" if isinstance(total_val, int) or (isinstance(total_val, float) and total_val.is_integer()) else f"{total_val:,.2f}"
        embed.set_footer(text=f"มูลค่าหุ้นที่ถือครองรวม: {total_str} บาท")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @ui.button(label="ก่อนหน้า", emoji="⬅️", style=discord.ButtonStyle.secondary, custom_id="crypto_prev_btn", row=1)
    async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        dashboard = self.cog.data.get("dashboard", {})
        if dashboard.get("page", 0) > 0:
            dashboard["page"] -= 1
            self.cog.save_data()
            await interaction.response.defer()
            await self.cog._update_dashboard_message()
        else:
            await interaction.response.send_message("นี่คือหน้าแรกแล้ว!", ephemeral=True)

    @ui.button(label="ถัดไป", emoji="➡️", style=discord.ButtonStyle.secondary, custom_id="crypto_next_btn", row=1)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        market_len = len(self.cog.data.get("market", {}))
        max_page = max(0, (market_len - 1) // 10)
        dashboard = self.cog.data.get("dashboard", {})
        if dashboard.get("page", 0) < max_page:
            dashboard["page"] = dashboard.get("page", 0) + 1
            self.cog.save_data()
            await interaction.response.defer()
            await self.cog._update_dashboard_message()
        else:
            await interaction.response.send_message("นี่คือหน้าสุดท้ายแล้ว!", ephemeral=True)

class Crypto(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.load_data()

    def load_data(self):
        if not os.path.exists(DB_FILE):
            self.data = {"market": {}, "portfolios": {}, "status": "open", "admins": {"users": [], "roles": []}}
            self.save_data()
        else:
            with open(DB_FILE, "r") as f:
                self.data = json.load(f)

        # การย้ายข้อมูล (Migration) สำหรับโครงสร้างใหม่
        migrated = False
        market = self.data.get("market", {})
        for sym, val in market.items():
            if not isinstance(val, dict):
                # หากยังเป็นเลขตัวเดียว ให้เปลี่ยนเป็น dict และตั้งบอทเป็นเจ้าของชั่วคราว (หรือแอดมินคนแรกถ้ามี)
                owner = self.data["admins"]["users"][0] if self.data["admins"]["users"] else None
                market[sym] = {"price": val, "owner_id": owner}
                migrated = True
        
        if migrated:
            self.save_data()

        if "dashboard" not in self.data:
            self.data["dashboard"] = None
        
        if "status" not in self.data:
            self.data["status"] = "open"

        if "admins" not in self.data:
            self.data["admins"] = {"users": [], "roles": []}

    def save_data(self):
        with open(DB_FILE, "w") as f:
            json.dump(self.data, f, indent=4)

    def get_market_price(self, symbol):
        return self.data["market"].get(symbol)

    def get_portfolio(self, user_id):
        return self.data["portfolios"].get(str(user_id), {})

    def update_portfolio(self, user_id, symbol, qty):
        user_id = str(user_id)
        if user_id not in self.data["portfolios"]:
            self.data["portfolios"][user_id] = {}
        
        if symbol not in self.data["portfolios"][user_id]:
            self.data["portfolios"][user_id][symbol] = 0
            
        self.data["portfolios"][user_id][symbol] += qty
        self.save_data()

    async def _update_dashboard_message(self):
        if not self.data.get("dashboard"):
            return False

        channel_id = self.data["dashboard"]["channel_id"]
        message_id = self.data["dashboard"]["message_id"]
        current_page = self.data["dashboard"].get("page", 0)
        
        channel = self.bot.get_channel(channel_id)
        if not channel:
            return False

        try:
            msg = await channel.fetch_message(message_id)
        except discord.NotFound:
            return False

        items = list(self.data["market"].items())
        market_len = len(items)
        max_page = max(0, (market_len - 1) // 10)
        
        if current_page > max_page:
            current_page = max_page
            self.data["dashboard"]["page"] = current_page
            
        start_idx = current_page * 10
        end_idx = start_idx + 10
        page_items = items[start_idx:end_idx]

        market_txt = "รายการหุ้นที่มีขายในตลาด:\n" if page_items else "ไม่มีหุ้นในตลาด\n"
        for sym, data in page_items:
            price = data['price']
            if isinstance(price, int) or (isinstance(price, float) and price.is_integer()):
                price_str = f"{int(price):,}"
            else:
                price_str = f"{price:,.2f}"
            
            owner_mention = f"<@{data['owner_id']}>" if data.get('owner_id') else "ส่วนกลาง"
            market_txt += f"🔹 **{sym}**: {price_str} บาท (เจ้าของ: {owner_mention})\n"
            
        status = self.data.get("status", "open")
        title_status = "(**Status:** Open 🟢)" if status == "open" else "(**Status:** Closed 🔴)"
        color = discord.Color.green() if status == "open" else discord.Color.red()
        
        embed = discord.Embed(title=f"📈 ตลาดหลักทรัพย์แห่งประเทศไทย {title_status}", description=market_txt, color=color)
        
        if market_len > 10:
            embed.set_footer(text=f"หน้า {current_page + 1}/{max_page + 1} | กดปุ่มด้านล่างเพื่อทำการซื้อขาย")
        else:
            embed.set_footer(text="กดปุ่มด้านล่างเพื่อทำการซื้อขาย")
        
        try:
            await msg.edit(embed=embed, view=CryptoView(self))
            return True
        except Exception:
            return False

    def check_crypto_permission(self, interaction: discord.Interaction) -> bool:
        # Check for Administrator permission
        if interaction.user.guild_permissions.administrator:
            return True
        
        # Check if user is in authorized users list
        if interaction.user.id in self.data["admins"].get("users", []):
            return True
            
        # Check if user has any authorized roles
        user_roles = [role.id for role in interaction.user.roles]
        authorized_roles = self.data["admins"].get("roles", [])
        if any(role_id in authorized_roles for role_id in user_roles):
            return True
            
        return False

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


    @app_commands.command(name="admin_crypto", description="[Admin] จัดการผู้มีสิทธิ์ดูแลระบบหุ้น")
    @app_commands.default_permissions(administrator=True)
    @app_commands.choices(action=[
        app_commands.Choice(name="Add (เพิ่มสิทธิ์)", value="add"),
        app_commands.Choice(name="Remove (ลบสิทธิ์)", value="remove"),
        app_commands.Choice(name="List (ดูรายชื่อ)", value="list")
    ])
    async def admin_crypto(self, interaction: discord.Interaction, action: app_commands.Choice[str], target: discord.User = None, role_target: discord.Role = None):
        action_val = action.value
        
        if action_val == "list":
            users = [f"<@{uid}>" for uid in self.data["admins"].get("users", [])]
            roles = [f"<@&{rid}>" for rid in self.data["admins"].get("roles", [])]
            
            embed = discord.Embed(title="<:sheild:1459451942819467388> Crypto Administrators", color=discord.Color.blurple())
            embed.add_field(name="Authorized Users", value="\n".join(users) if users else "None", inline=False)
            embed.add_field(name="Authorized Roles", value="\n".join(roles) if roles else "None", inline=False)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        # For Add/Remove, target must be provided
        if not target and not role_target:
             await interaction.response.send_message("<:w_:1459388961943457934> กรุณาระบุ Target (User หรือ Role) ที่ต้องการจัดการ", ephemeral=True)
             return

        if action_val == "add":
            if target:
                if target.id not in self.data["admins"]["users"]:
                    self.data["admins"]["users"].append(target.id)
                    self.save_data()
                    await interaction.response.send_message(f"<:c_:1459387176516190312> เพิ่มสิทธิ์ให้ {target.mention} เรียบร้อยแล้ว", ephemeral=True)
                else:
                    await interaction.response.send_message(f"⚠️ {target.mention} มีสิทธิ์อยู่แล้ว", ephemeral=True)
            
            if role_target:
                if role_target.id not in self.data["admins"]["roles"]:
                    self.data["admins"]["roles"].append(role_target.id)
                    self.save_data()
                    await interaction.response.send_message(f"<:c_:1459387176516190312> เพิ่มสิทธิ์ให้ role {role_target.mention} เรียบร้อยแล้ว", ephemeral=True)
                else:
                    await interaction.response.send_message(f"⚠️ Role {role_target.mention} มีสิทธิ์อยู่แล้ว", ephemeral=True)

        elif action_val == "remove":
            if target:
                if target.id in self.data["admins"]["users"]:
                    self.data["admins"]["users"].remove(target.id)
                    self.save_data()
                    await interaction.response.send_message(f"<:c_:1459387176516190312> ลบสิทธิ์ของ {target.mention} เรียบร้อยแล้ว", ephemeral=True)
                else:
                    await interaction.response.send_message(f"⚠️ {target.mention} ไม่มีสิทธิ์ในระบบนี้", ephemeral=True)
            
            if role_target:
                if role_target.id in self.data["admins"]["roles"]:
                    self.data["admins"]["roles"].remove(role_target.id)
                    self.save_data()
                    await interaction.response.send_message(f"<:c_:1459387176516190312> ลบสิทธิ์ของ role {role_target.mention} เรียบร้อยแล้ว", ephemeral=True)
                else:
                    await interaction.response.send_message(f"⚠️ Role {role_target.mention} ไม่มีสิทธิ์ในระบบนี้", ephemeral=True)

    @app_commands.command(name="set_crypto", description="[Admin/Owner] จัดการตลาดหุ้นผ่านเมนูโต้ตอบ")
    async def set_crypto(self, interaction: discord.Interaction):
        # แอดมินหรือผู้ที่ได้รับสิทธิ์สามารถใช้งานเมนูหลักได้
        if not self.check_crypto_permission(interaction):
            await interaction.response.send_message("<:w_:1459388961943457934> คุณไม่มีสิทธิ์ในการจัดการระบบหุ้นส่วนกลาง", ephemeral=True)
            return

        view = StockManageView(self, interaction.user)
        await interaction.response.send_message(embed=view.create_initial_embed(), view=view, ephemeral=True)

    @app_commands.command(name="set_crypto_perm", description="[Admin] เปิด/ปิด ตลาดหุ้น (open/close)")
    async def set_crypto_perm(self, interaction: discord.Interaction, mode: str):
        if not self.check_crypto_permission(interaction):
            await interaction.response.send_message("<:w_:1459388961943457934> คุณไม่มีสิทธิ์ในการใช้คำสั่งนี้", ephemeral=True)
            return

        mode = mode.lower()
        if mode not in ["open", "close"]:
            await interaction.response.send_message("<:w_:1459388961943457934> กรุณาระบุ `open` หรือ `close` เท่านั้น", ephemeral=True)
            return

        self.data["status"] = "open" if mode == "open" else "closed"
        self.save_data()
        
        await self._update_dashboard_message()
        
        status_text = "เปิดตลาด 🟢" if mode == "open" else "ปิดตลาด 🔴"
        await interaction.response.send_message(f"<:c_:1459387176516190312> ทำการ **{status_text}** เรียบร้อยแล้ว", ephemeral=True)

    @app_commands.command(name="setup_crypto", description="[Admin] สร้างบอร์ดซื้อขายหุ้น")
    async def setup_crypto(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        if not self.check_crypto_permission(interaction):
            await interaction.followup.send("<:w_:1459388961943457934> คุณไม่มีสิทธิ์ในการใช้คำสั่งนี้", ephemeral=True)
            return

        # ลบข้อความเก่าถ้ามี
        old_dash = self.data.get("dashboard")
        if old_dash:
            try:
                old_channel = self.bot.get_channel(old_dash["channel_id"])
                if old_channel:
                    old_msg = await old_channel.fetch_message(old_dash["message_id"])
                    await old_msg.delete()
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                pass # ข้ามถ้าไม่เจอหรือไม่มีสิทธิ์ลบ

        if "dashboard" not in self.data or not isinstance(self.data["dashboard"], dict):
            self.data["dashboard"] = {}
            
        embed = discord.Embed(title="กำลังสร้างกระดานตลาดหุ้น...", color=discord.Color.blue())
        msg = await interaction.channel.send(embed=embed)
        
        self.data["dashboard"]["channel_id"] = interaction.channel.id
        self.data["dashboard"]["message_id"] = msg.id
        self.data["dashboard"]["page"] = 0
        self.save_data()
        
        await self._update_dashboard_message()
        await interaction.followup.send("<:c_:1459387176516190312> สร้างบอร์ดใหม่เรียบร้อยแล้ว (ลบอันเก่าทิ้งแล้ว)", ephemeral=True)

    @app_commands.command(name="update_crypto", description="[Admin] อัพเดทราคาหน้าบอร์ดซื้อขาย")
    async def update_crypto(self, interaction: discord.Interaction):
        if not self.check_crypto_permission(interaction):
            await interaction.response.send_message("<:w_:1459388961943457934> คุณไม่มีสิทธิ์ในการใช้คำสั่งนี้", ephemeral=True)
            return
            
        success = await self._update_dashboard_message()
        if success:
            await interaction.response.send_message("<:c_:1459387176516190312> อัพเดทบอร์ดเรียบร้อยแล้ว", ephemeral=True)
        else:
            await interaction.response.send_message("<:w_:1459388961943457934> ไม่สามารถอัพเดทบอร์ดได้ (อาจเพราะไม่พบบอร์ดเดิม)", ephemeral=True)


    @app_commands.command(name="view_crypto", description="ดูรายการหุ้น/คริปโตทั้งหมดในตลาด")
    async def view_crypto(self, interaction: discord.Interaction):
        if not self.data["market"]:
            await interaction.response.send_message("<:w_:1459388961943457934> ยังไม่มีหุ้นในตลาดเลย!", ephemeral=True)
            return

        market_txt = "รายการหุ้นที่มีขายในตลาด:\n"
        for sym, data in self.data["market"].items():
            price = data['price']
            if isinstance(price, int) or price.is_integer():
                price_str = f"{int(price):,}"
            else:
                price_str = f"{price:,.2f}"
            market_txt += f"🔹 **{sym}**: {price_str} บาท\n"
            
        embed = discord.Embed(title="📈 ตลาดหุ้น/คริปโต (Real-time)", description=market_txt, color=discord.Color.blue())
        await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot):
    await bot.add_cog(Crypto(bot))

