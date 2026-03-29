import discord
from discord.ext import commands
from discord import app_commands
import json
import os
import random

DB_FILE = "json/economy_data.json"

class Economy(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.load_data() # โหลดข้อมูลเมื่อเริ่มบอท

    # ฟังก์ชันโหลดข้อมูลผู้ใช้จากไฟล์ JSON
    def load_data(self):
        if not os.path.exists(DB_FILE):
            # ถ้าไม่มีไฟล์ ให้สร้างข้อมูลเก็บเงินเริ่มต้นสำหรับบอท (System)
            self.users = {"system_bank": {"wallet": 1000000000, "bank": 1000000000}} 
            self.save_data()
        else:
            with open(DB_FILE, "r") as f:
                self.users = json.load(f)
            # Migration check
            migrated = False
            for user_id, value in self.users.items():
                if isinstance(value, int):
                    self.users[user_id] = {"wallet": value, "bank": 0}
                    migrated = True
            if migrated:
                self.save_data()

    # ฟังก์ชันบันทึกข้อมูลลงไฟล์ JSON
    def save_data(self):
        with open(DB_FILE, "w") as f:
            json.dump(self.users, f, indent=4)

    def get_balance(self, user_id):
        user_id = str(user_id)
        if user_id not in self.users:
            self.users[user_id] = {"wallet": 0, "bank": 0}
            self.save_data()
        return self.users[user_id]

    def update_balance(self, user_id, amount, type="wallet"):
        user_id = str(user_id)
        self.get_balance(user_id) # Ensure user exists
        self.users[user_id][type] += amount
        self.save_data()

    async def log_transaction(self, embed: discord.Embed):
        channel = self.bot.get_channel(1487603625290371325)
        if channel:
            try:
                await channel.send(embed=embed)
            except: pass

    @app_commands.command(name="balance", description="เช็คยอดเงินในกระเป๋าและธนาคาร")
    async def balance(self, interaction: discord.Interaction, member: discord.Member = None):
        target = member or interaction.user
        bal = self.get_balance(target.id)
        embed = discord.Embed(title=f"💸 ทรัพย์สินของ {target.display_name}", color=discord.Color.blue())
        embed.add_field(name="💵 กระเป๋าตังค์", value=f"{bal['wallet']:,} บาท", inline=True)
        embed.add_field(name="<:__:1459385992040546559> ธนาคาร", value=f"{bal['bank']:,} บาท", inline=True)
        embed.add_field(name="💰 รวมทั้งหมด", value=f"{bal['wallet'] + bal['bank']:,} บาท", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="deposit", description="ฝากเงินเข้าธนาคาร")
    async def deposit(self, interaction: discord.Interaction, amount: int):
        bal = self.get_balance(interaction.user.id)
        if amount <= 0:
            await interaction.response.send_message("<:w_:1459388961943457934> จำนวนเงินต้องมากกว่า 0!", ephemeral=True)
            return
        if bal['wallet'] < amount:
            await interaction.response.send_message("<:w_:1459388961943457934> เงินในกระเป๋าไม่พอ!", ephemeral=True)
            return

        self.update_balance(interaction.user.id, -amount, "wallet")
        self.update_balance(interaction.user.id, amount, "bank")
        
        await interaction.response.send_message(f"🏦 ฝากเงิน **{amount:,} บาท** เข้าธนาคารเรียบร้อยแล้ว")
        
        embed = discord.Embed(title="🏦 ทำรายการฝากเงิน", color=discord.Color.green())
        embed.add_field(name="ผู้ทำรายการ", value=f"{interaction.user.mention} ({interaction.user.id})", inline=False)
        embed.add_field(name="จำนวนเงิน", value=f"+ {amount:,} บาท", inline=False)
        await self.log_transaction(embed)

    @app_commands.command(name="withdraw", description="ถอนเงินจากธนาคาร")
    async def withdraw(self, interaction: discord.Interaction, amount: int):
        bal = self.get_balance(interaction.user.id)
        if amount <= 0:
            await interaction.response.send_message("<:w_:1459388961943457934> จำนวนเงินต้องมากกว่า 0!", ephemeral=True)
            return
        if bal['bank'] < amount:
            await interaction.response.send_message("<:w_:1459388961943457934> เงินในธนาคารไม่พอ!", ephemeral=True)
            return

        self.update_balance(interaction.user.id, -amount, "bank")
        self.update_balance(interaction.user.id, amount, "wallet")
        
        await interaction.response.send_message(f"💸 ถอนเงิน **{amount:,} บาท** ออกจากธนาคารเรียบร้อยแล้ว")

        embed = discord.Embed(title="📤 ทำรายการถอนเงิน", color=discord.Color.orange())
        embed.add_field(name="ผู้ทำรายการ", value=f"{interaction.user.mention} ({interaction.user.id})", inline=False)
        embed.add_field(name="จำนวนเงิน", value=f"- {amount:,} บาท", inline=False)
        await self.log_transaction(embed)

    @app_commands.command(name="work", description="ทำงานเพื่อชาติ (และปากท้อง)")
    async def work(self, interaction: discord.Interaction):
        earnings = random.randint(100, 500)
        self.update_balance(interaction.user.id, earnings, "wallet")
        
        reasons = [
            "ช่วยสร้างถนน (แต่ยังไม่เสร็จ)",
            "ขายหมูปิ้งหน้าปากซอย",
            "ซ่อมสายไฟที่พันกันอีรุงตุงนัง",
            "สอนเด็กอนุบาลร้องเพลงชาติ",
            "ขับวินมอไซค์ส่งคน",
            "เก็บขวดขาย",
            "รับจ้างต่อคิวซื้อของ"
        ]
        reason = random.choice(reasons)
        
        await interaction.response.send_message(f"🔨 คุณออกไป **{reason}** ได้เงินค่าแรงมา **{earnings} บาท**!")


    @app_commands.command(name="transfer", description="โอนเงินให้ประชาชนท่านอื่น")
    async def transfer(self, interaction: discord.Interaction, recipient: discord.Member, amount: int):
        if amount <= 0:
            await interaction.response.send_message("<:w_:1459388961943457934> จำนวนเงินต้องมากกว่า 0!", ephemeral=True)
            return
            
        sender_bal = self.get_balance(interaction.user.id)
        if sender_bal['wallet'] < amount:
            await interaction.response.send_message("<:w_:1459388961943457934> เงินในกระเป๋าไม่พอ!", ephemeral=True)
            return

        self.update_balance(interaction.user.id, -amount, "wallet")
        self.update_balance(recipient.id, amount, "wallet")
        
        await interaction.response.send_message(f"<:c_:1459387176516190312> โอนเงิน **{amount:,} บาท** ให้กับ {recipient.mention} เรียบร้อยแล้ว!")

        embed = discord.Embed(title="🔄 โอนเงิน", color=discord.Color.blue())
        embed.add_field(name="ผู้โอน", value=f"{interaction.user.mention} ({interaction.user.id})", inline=False)
        embed.add_field(name="ผู้รับ", value=f"{recipient.mention} ({recipient.id})", inline=False)
        embed.add_field(name="จำนวนเงิน", value=f"{amount:,} บาท", inline=False)
        await self.log_transaction(embed)

    @app_commands.command(name="give_money", description="มอบเงินให้ประชาชนด้วยความเสน่หา")
    async def give_money(self, interaction: discord.Interaction, member: discord.Member, amount: int):
        if amount <= 0:
            await interaction.response.send_message("<:w_:1459388961943457934> จำนวนเงินต้องมากกว่า 0!", ephemeral=True)
            return
            
        sender_bal = self.get_balance(interaction.user.id)
        if sender_bal['wallet'] < amount:
            await interaction.response.send_message("<:w_:1459388961943457934> เงินในกระเป๋าไม่พอ!", ephemeral=True)
            return

        self.update_balance(interaction.user.id, -amount, "wallet")
        self.update_balance(member.id, amount, "wallet")
        
        await interaction.response.send_message(f"💸 คุณได้มอบเงิน **{amount:,} บาท** ให้กับ {member.mention}! ช่างใจบุญจริงๆ 🙏")

        embed = discord.Embed(title="🎁 ให้เงินโดยเสน่หา", color=discord.Color.purple())
        embed.add_field(name="ผู้ให้", value=f"{interaction.user.mention} ({interaction.user.id})", inline=False)
        embed.add_field(name="ผู้รับ", value=f"{member.mention} ({member.id})", inline=False)
        embed.add_field(name="จำนวนเงิน", value=f"{amount:,} บาท", inline=False)
        await self.log_transaction(embed)

    @app_commands.command(name="add_money", description="[Admin] เสกเงินเข้าระบบให้ประชาชน (Mention)")
    @app_commands.default_permissions(administrator=True)
    async def add_money(self, interaction: discord.Interaction, mentions: str, amount: int):
        if amount <= 0:
            await interaction.response.send_message("<:w_:1459388961943457934> จำนวนเงินต้องมากกว่า 0!", ephemeral=True)
            return

        import re
        user_ids = re.findall(r'<@!?(\d+)>', mentions)
        
        if not user_ids:
            await interaction.response.send_message("<:w_:1459388961943457934> ไม่พบการ Mention ผู้ใช้!", ephemeral=True)
            return

        processed_users = []
        for user_id in set(user_ids):
            self.update_balance(user_id, amount, "wallet")
            processed_users.append(f"<@{user_id}>")
        
        embed = discord.Embed(title="💸 เสกเงินเข้าระบบสำเร็จ", color=discord.Color.gold())
        embed.add_field(name="ผู้ได้รับเงิน", value=", ".join(processed_users), inline=False)
        embed.add_field(name="ได้รับคนละ", value=f"{amount:,} บาท", inline=False)
        embed.add_field(name="รวมทั้งหมด", value=f"{amount * len(processed_users):,} บาท", inline=False)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

        log_embed = discord.Embed(title="⚠️ เสกเงินเข้าระบบ (Admin)", color=discord.Color.red())
        log_embed.add_field(name="แอดมินผู้พิมพ์คำสั่ง", value=f"{interaction.user.mention} ({interaction.user.id})", inline=False)
        log_embed.add_field(name="ผู้ได้รับเงิน", value=", ".join(processed_users), inline=False)
        log_embed.add_field(name="จำนวนเงิน", value=f"{amount:,} บาท ต่อคน", inline=False)
        await self.log_transaction(log_embed)

async def setup(bot):
    await bot.add_cog(Economy(bot))
