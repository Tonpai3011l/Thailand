import discord
from discord.ext import commands, tasks
from discord import app_commands
import random

class CitizenAPI:
    """Simulates the state of the citizenry."""
    def __init__(self):
        self.approval_rating = 50.0  # Percentage
        self.mood = "Neutral"

    def update_approval(self):
        """Randomly fluctuate approval rating."""
        change = random.uniform(-5.0, 5.0)
        self.approval_rating = max(0.0, min(100.0, self.approval_rating + change))
        self.update_mood()

    def update_mood(self):
        if self.approval_rating > 80:
            self.mood = "มีความสุขสุดๆ 😄"
        elif self.approval_rating > 50:
            self.mood = "เฉยๆ ก็งั้นๆ 😐"
        elif self.approval_rating > 30:
            self.mood = "ไม่พอใจตั้วแต่น้อย 😠"
        else:
            self.mood = "โกรธจัด อยากจะเดินขบวน! 🤬"

    def get_status(self):
        return {
            "approval": round(self.approval_rating, 2),
            "mood": self.mood
        }

class Politics(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.citizen_simulation = CitizenAPI()
        
        # Problems list
        self.problems = [
            "น้ำท่วมกรุงเทพฯ (อีกแล้ว)! 🌊",
            "นายกฯ หลับกลางสภา! 😴",
            "รถไฟฟ้าเสีย รอนานเป็นชั่วโมง! 🚆",
            "พบทุจริตโครงการใหญ่ หมื่นล้านหายวับ! 💰",
            "ฝุ่น PM 2.5 พุ่งปรี๊ด มองไม่เห็นตึก! 😷",
            "ราคาผักชีแพงหูฉี่! 🥦",
            "เน็ตล่มทั่วประเทศ ทำงานไม่ได้! 🌐"
        ]

    # Background task to generate problems periodically
    # (Commented out for now to avoid spam, can be enabled if user wants automatic events)
    # @tasks.loop(hours=1)
    # async def generate_problem_task(self):
    #     pass

    @app_commands.command(name="poll", description="เช็คเรตติ้งความนิยมของรัฐบาล")
    async def poll(self, interaction: discord.Interaction):
        self.citizen_simulation.update_approval()
        status = self.citizen_simulation.get_status()
        
        embed = discord.Embed(title="📊 ผลสำรวจประชามติ", color=discord.Color.blue())
        embed.add_field(name="คะแนนความนิยม", value=f"{status['approval']}%", inline=False)
        embed.add_field(name="อารมณ์ประชาชน", value=status['mood'], inline=False)
        
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="crisis", description="จำลองสถานการณ์ปั่นป่วนในประเทศ")
    async def crisis(self, interaction: discord.Interaction):
        problem = random.choice(self.problems)
        
        # Simulate approval drop
        self.citizen_simulation.approval_rating -= random.uniform(5, 15)
        self.citizen_simulation.update_mood()
        
        embed = discord.Embed(title="🚨 ข่าวด่วน! 🚨", description=f"**{problem}**", color=discord.Color.red())
        embed.add_field(name="ผลกระทบ", value="คะแนนความนิยมร่วงกราวรูด!", inline=False)
        
        await interaction.response.send_message(embed=embed)

async def setup(bot):
    await bot.add_cog(Politics(bot))
