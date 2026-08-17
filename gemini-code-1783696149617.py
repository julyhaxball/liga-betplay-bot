import os
import discord
from discord.ext import commands
from discord import app_commands
from flask import Flask
from threading import Thread

# --- SERVIDOR WEB PARA RENDER (KEEP ALIVE) ---
app = Flask('')

@app.route('/')
def home():
    return "Bot de Discord activo 24/7"

def run_web():
    app.run(host='0.0.0.0', port=10000)

def keep_alive():
    t = Thread(target=run_web)
    t.start()


# --- CONFIGURACIÓN DEL BOT ---
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)


# --- VISTAS PERSISTENTES PARA TICKETS ---
class TicketSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Alianzas", description="Hacer una alianza con nosotros", emoji="🤝", value="alianza"),
            discord.SelectOption(label="Reportes", description="Reportar algo que no sea apto", emoji="❗", value="reporte"),
            discord.SelectOption(label="Postulaciones", description="Postularse para ser admin, periodista, etc.", emoji="🧑‍💼", value="postulacion"),
            discord.SelectOption(label="Otro", description="Algo distinto al resto", emoji="❓", value="otro"),
        ]
        super().__init__(placeholder="Selecciona el tipo de ticket que deseas abrir...", min_values=1, max_values=1, custom_id="ticket_select_menu")

    async def callback(self, interaction: discord.Interaction):
        categoria = self.values[0]
        guild = interaction.guild
        user = interaction.user

        # Crear canal privado para el ticket
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True)
        }

        nombre_canal = f"ticket-{categoria}-{user.name}".lower()
        ticket_channel = await guild.create_text_channel(name=nombre_canal, overwrites=overwrites)

        embed = discord.Embed(
            title=f"🎫 Ticket de {categoria.capitalize()} - {user.name}",
            description="Un miembro del Staff te atenderá pronto. Explica tu consulta o motivo aquí.",
            color=discord.Color.blue()
        )

        await ticket_channel.send(content=f"{user.mention}", embed=embed, view=TicketCloseView())
        await interaction.response.send_message(f"✅ Ticket creado correctamente: {ticket_channel.mention}", ephemeral=True)


class TicketLaunchView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(TicketSelect())


class TicketCloseView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Cerrar Ticket", style=discord.ButtonStyle.danger, custom_id="close_ticket_btn", emoji="🔒")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("🔒 Cerrando este ticket en 5 segundos...")
        await discord.utils.sleep_until(discord.utils.utcnow() + datetime.timedelta(seconds=5))
        await interaction.channel.delete()


# --- EVENTO ON_READY ---
@bot.event
async def on_ready():
    # Registrar vistas persistentes para que sigan funcionando tras reinicios
    bot.add_view(TicketLaunchView())
    bot.add_view(TicketCloseView())

    # Forzar el estado Online visible en Discord
    await bot.change_presence(
        status=discord.Status.online,
        activity=discord.Game(name="Liga Haxball | /ticket_panel")
    )

    try:
        synced = await bot.tree.sync()
        print(f"✅ Comandos sincronizados: {len(synced)}")
    except Exception as e:
        print(f"Error al sincronizar comandos: {e}")

    print(f"🤖 Bot encendido correctamente como {bot.user}")


# --- COMANDO SLASH DE PANEL DE TICKETS ---
@bot.tree.command(name="ticket_panel", description="Publica el panel con menú desplegable para abrir tickets (Admin).")
@app_commands.checks.has_permissions(administrator=True)
async def ticket_panel(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    # IDs de los roles
    ID_FUNDADOR = 1538383718459252786
    ID_CO_OWNER = 1538390799299911766
    ID_ADMINISTRADOR = 1538389985336762448
    ID_MODERADOR = 1538390251414757396

    menciones_roles = f"<@&{ID_FUNDADOR}> <@&{ID_CO_OWNER}> <@&{ID_ADMINISTRADOR}> <@&{ID_MODERADOR}>"

    mensaje_descripcion = (
        "📢 **HORARIO DE ATENCIÓN DE TICKETS**\n\n"
        "Les informamos que el horario oficial de atención de tickets será el siguiente:\n\n"
        "🇨🇴 **Colombia:** 2:00 PM - 9:00 PM\n"
        "🇻🇪 **Venezuela:** 3:00 PM - 10:00 PM\n"
        "🇨🇱 **Chile:** 4:00 PM - 11:00 PM\n"
        "🇦🇷 **Argentina:** 4:00 PM - 11:00 PM\n"
        "🇺🇾 **Uruguay:** 4:00 PM - 11:00 PM\n\n"
        "⚠️ Los tickets abiertos fuera de este horario podrán ser atendidos al día siguiente, dependiendo de la disponibilidad del Staff.\n\n"
        "Agradecemos su comprensión y colaboración. 🏆⚽\n\n"
        "[🤝] **ALIANZAS**\nHacer una alianza con nosotros\n\n"
        "[❗] **REPORTES**\nReportar algo que no sea apto\n\n"
        "[🧑‍💼] **POSTULACIONES**\nPostularse para ser admin, periodista, programador, etc.\n\n"
        "[❓] **OTRO**\nAlgo distinto al resto"
    )

    embed = discord.Embed(
        title="🎫 Centro de Atención y Tickets",
        description=mensaje_descripcion,
        color=discord.Color.gold()
    )
    embed.set_footer(text="Selecciona una opción del menú de abajo para abrir un ticket.")

    await interaction.channel.send(content=menciones_roles, embed=embed, view=TicketLaunchView())
    await interaction.followup.send("✅ Panel publicado correctamente notificando a los roles.", ephemeral=True)


# --- EJECUCIÓN ---
keep_alive()
TOKEN = os.getenv("DISCORD_TOKEN")  # Asegúrate de tener la variable de entorno en Render
bot.run(TOKEN)
