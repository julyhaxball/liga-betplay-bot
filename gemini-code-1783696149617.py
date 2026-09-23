import os
import json
import sqlite3
import datetime
import asyncio
import re
from threading import Thread
from flask import Flask

import discord
from discord import app_commands
from discord.ext import commands

# ==========================================
# --- 1. CONFIGURACIÓN Y BASE DE DATOS -----
# ==========================================
DB_NAME = "liga_haxball.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS temporadas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL UNIQUE,
            estado TEXT NOT NULL DEFAULT 'inscripcion',
            fecha_inicio TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS equipos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL UNIQUE,
            dt_id INTEGER NOT NULL,
            rol_id INTEGER NOT NULL,
            temporada_id INTEGER,
            FOREIGN KEY (temporada_id) REFERENCES temporadas(id)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS jugadores (
            discord_id INTEGER PRIMARY KEY,
            equipo_id INTEGER,
            goles INTEGER DEFAULT 0,
            asistencias INTEGER DEFAULT 0,
            mvps INTEGER DEFAULT 0,
            partidos_jugados INTEGER DEFAULT 0,
            FOREIGN KEY (equipo_id) REFERENCES equipos(id)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS partidos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            temporada_id INTEGER NOT NULL,
            jornada INTEGER DEFAULT 1,
            equipo_local_id INTEGER NOT NULL,
            equipo_visitante_id INTEGER NOT NULL,
            goles_local INTEGER DEFAULT 0,
            goles_visitante INTEGER DEFAULT 0,
            jugado INTEGER DEFAULT 0,
            replay_url TEXT,
            FOREIGN KEY (temporada_id) REFERENCES temporadas(id),
            FOREIGN KEY (equipo_local_id) REFERENCES equipos(id),
            FOREIGN KEY (equipo_visitante_id) REFERENCES equipos(id)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS goles_partido (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            partido_id INTEGER NOT NULL,
            jugador_id INTEGER NOT NULL,
            tipo TEXT DEFAULT 'gol',
            cantidad INTEGER DEFAULT 1,
            FOREIGN KEY (partido_id) REFERENCES partidos(id),
            FOREIGN KEY (jugador_id) REFERENCES jugadores(discord_id)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sanciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            jugador_id INTEGER NOT NULL,
            tipo TEXT NOT NULL,
            partidos_suspension INTEGER DEFAULT 0,
            motivo TEXT,
            activa INTEGER DEFAULT 1,
            FOREIGN KEY (jugador_id) REFERENCES jugadores(discord_id)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS historial_traspasos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            jugador_id INTEGER NOT NULL,
            origen_id INTEGER,
            destino_id INTEGER NOT NULL,
            fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (jugador_id) REFERENCES jugadores(discord_id),
            FOREIGN KEY (origen_id) REFERENCES equipos(id),
            FOREIGN KEY (destino_id) REFERENCES equipos(id)
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS museo_titulos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            equipo_id INTEGER NOT NULL,
            tipo TEXT NOT NULL,
            nombre TEXT NOT NULL,
            jugador_id INTEGER,
            temporada TEXT,
            detalles TEXT,
            FOREIGN KEY (equipo_id) REFERENCES equipos(id)
        )
    ''')
    
    conn.commit()
    conn.close()

init_db()

# ==========================================
# --- 2. SERVIDOR WEB (KEEP ALIVE) --------
# ==========================================
app = Flask('')

@app.route('/')
def home():
    return "Bot de Liga Haxball (Vanta League) activo 24/7"

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run_web)
    t.start()

# ==========================================
# --- 3. CONFIGURACIÓN Y CONSTANTES --------
# ==========================================
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

ID_CANAL_PARTNERS = 123456789012345678  # Reemplaza con la ID de tu canal público de alianzas
ID_FUNDADOR = 1538383718459252786
ID_CO_OWNER = 1538390799299911766
ID_ADMINISTRADOR = 1538389985336762448
ID_ROL_PARTNER = 1538390251414757396

async def equipo_autocomplete(interaction: discord.Interaction, current: str):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT nombre FROM equipos WHERE nombre LIKE ? LIMIT 25", (f"%{current}%",))
    equipos = cursor.fetchall()
    conn.close()
    return [app_commands.Choice(name=eq[0], value=eq[0]) for eq in equipos]

async def seguro_borrar_canal(channel):
    if channel:
        try:
            await channel.delete()
        except (discord.NotFound, discord.HTTPException):
            pass

# ==========================================
# --- 4. MODALES Y VISTAS DE TICKETS -------
# ==========================================

class AlianzaModal(discord.ui.Modal, title="📝 Formulario de Alianza"):
    nombre_comunidad = discord.ui.TextInput(
        label="Nombre de tu Comunidad/Liga",
        placeholder="Ej. Liga Sombra Haxball",
        required=True
    )
    miembros = discord.ui.TextInput(
        label="Cantidad aproximada de miembros",
        placeholder="Ej. 250 miembros",
        required=True
    )
    invitacion = discord.ui.TextInput(
        label="Link de Invitación a tu Discord",
        placeholder="https://discord.gg/ejemplo",
        required=True
    )
    propuesta = discord.ui.TextInput(
        label="Detalles / Tipo de Alianza",
        style=discord.TextStyle.paragraph,
        placeholder="Ej. Ping x Ping en canal oficial, Banner rotatorio, etc.",
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            if not interaction.response.is_done():
                await interaction.response.defer(ephemeral=True)
        except Exception:
            pass

        await interaction.followup.send(
            f"✅ **Plantilla recibida correctamente.**\n"
            f"La propuesta de **{self.nombre_comunidad.value}** ha sido procesada y publicada en el canal de alianzas.",
            ephemeral=True
        )

        canal_partners = interaction.guild.get_channel(ID_CANAL_PARTNERS)
        if canal_partners:
            embed_alianza = discord.Embed(
                title=f"🤝 ¡NUEVA ALIANZA CONFIRMADA! - {self.nombre_comunidad.value}",
                description=(
                    f"👥 **Miembros:** {self.miembros.value}\n"
                    f"🔗 **Servidor:** {self.invitacion.value}\n\n"
                    f"📜 **Propuesta:**\n{self.propuesta.value}\n\n"
                    f"👤 **Representante:** {interaction.user.mention}"
                ),
                color=discord.Color.purple()
            )
            await canal_partners.send(content=f"<@&{ID_ROL_PARTNER}>", embed=embed_alianza)


class AlianzaTicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="📝 Rellenar Plantilla de Alianza", style=discord.ButtonStyle.success, custom_id="btn_abrir_modal_alianza")
    async def abrir_modal(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AlianzaModal())

    @discord.ui.button(label="🔔 Llamar al Staff", style=discord.ButtonStyle.secondary, custom_id="btn_llamar_staff_alianza")
    async def llamar_staff(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            if not interaction.response.is_done():
                await interaction.response.defer()
            await interaction.followup.send(
                f"🔔 <@&{ID_FUNDADOR}> <@&{ID_CO_OWNER}> <@&{ID_ADMINISTRADOR}>, el usuario {interaction.user.mention} requiere atención."
            )
        except Exception:
            pass

    @discord.ui.button(label="🔒 Cerrar Ticket", style=discord.ButtonStyle.danger, custom_id="btn_cerrar_ticket_alianza")
    async def cerrar_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            if not interaction.response.is_done():
                await interaction.response.defer()
            await interaction.followup.send("🔒 Cerrando ticket en 5 segundos...")
        except Exception:
            pass
        await asyncio.sleep(5)
        await seguro_borrar_canal(interaction.channel)


class PostulacionSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Administrador", description="Postularte para Admin de la liga", emoji="🛡️", value="admin"),
            discord.SelectOption(label="Diseñador Gráfico", description="Postularte para hacer banners/creativos", emoji="🎨", value="disenador"),
            discord.SelectOption(label="Moderador / Periodista", description="Postularte para moderar o redactar", emoji="📰", value="moderador"),
        ]
        super().__init__(placeholder="Selecciona el cargo al que deseas postularte...", min_values=1, max_values=1, custom_id="select_postulacion_cargo")

    async def callback(self, interaction: discord.Interaction):
        try:
            if not interaction.response.is_done():
                await interaction.response.defer()
        except Exception:
            pass

        cargo = self.values[0]
        preguntas = {
            "admin": (
                "🛡️ **POSTULACIÓN A ADMINISTRADOR**\n"
                "Responde lo siguiente en este chat:\n"
                "1. ¿Qué edad tienes y de qué país eres?\n"
                "2. ¿Tienes experiencia previa administrando ligas de Haxball?\n"
                "3. ¿Cuánto tiempo diario puedes dedicar a la liga?"
            ),
            "disenador": (
                "🎨 **POSTULACIÓN A DISEÑADOR**\n"
                "Responde lo siguiente en este chat:\n"
                "1. Adjunta 2 o 3 trabajos/banners previos realizados por ti.\n"
                "2. ¿Qué programas manejas (Photoshop, Canva, Illustrator, etc.)?\n"
                "3. ¿Tienes disponibilidad para entregas rápidas de fechas/tablas?"
            ),
            "moderador": (
                "📰 **POSTULACIÓN A MODERADOR / PERIODISTA**\n"
                "Responde lo siguiente en este chat:\n"
                "1. ¿Qué función prefieres: Moderación de chat o Redacción de noticias/resúmenes?\n"
                "2. ¿En qué horarios estás más activo en Discord?\n"
                "3. ¿Cómo reaccionas ante un conflicto en el chat?"
            )
        }

        try:
            await interaction.followup.send(f"🤖 **Preguntas para {cargo.capitalize()}:**\n\n{preguntas[cargo]}")
        except Exception:
            pass


class PostulacionTicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(PostulacionSelect())

    @discord.ui.button(label="🔒 Cerrar Ticket", style=discord.ButtonStyle.danger, custom_id="btn_cerrar_postulacion", row=1)
    async def cerrar_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            if not interaction.response.is_done():
                await interaction.response.defer()
            await interaction.followup.send("🔒 Cerrando ticket en 5 segundos...")
        except Exception:
            pass
        await asyncio.sleep(5)
        await seguro_borrar_canal(interaction.channel)


class ReporteTicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🔔 Re-notificar al Staff", style=discord.ButtonStyle.secondary, custom_id="btn_re_llamar_staff")
    async def re_llamar_staff(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            if not interaction.response.is_done():
                await interaction.response.defer()
            await interaction.followup.send(
                f"⚠️ **Atención Staff:** <@&{ID_FUNDADOR}> <@&{ID_CO_OWNER}> <@&{ID_ADMINISTRADOR}>, el usuario {interaction.user.mention} solicita asistencia inmediata."
            )
        except Exception:
            pass

    @discord.ui.button(label="🔒 Cerrar Ticket", style=discord.ButtonStyle.danger, custom_id="btn_cerrar_reporte")
    async def cerrar_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            if not interaction.response.is_done():
                await interaction.response.defer()
            await interaction.followup.send("🔒 Cerrando ticket en 5 segundos...")
        except Exception:
            pass
        await asyncio.sleep(5)
        await seguro_borrar_canal(interaction.channel)


class OtroTicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🔔 Llamar al Staff", style=discord.ButtonStyle.secondary, custom_id="btn_llamar_staff_otro")
    async def llamar_staff(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            if not interaction.response.is_done():
                await interaction.response.defer()
            await interaction.followup.send(
                f"🔔 <@&{ID_FUNDADOR}> <@&{ID_CO_OWNER}> <@&{ID_ADMINISTRADOR}>, el usuario {interaction.user.mention} requiere asistencia."
            )
        except Exception:
            pass

    @discord.ui.button(label="🔒 Cerrar Ticket", style=discord.ButtonStyle.danger, custom_id="btn_cerrar_otro")
    async def cerrar_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            if not interaction.response.is_done():
                await interaction.response.defer()
            await interaction.followup.send("🔒 Cerrando ticket en 5 segundos...")
        except Exception:
            pass
        await asyncio.sleep(5)
        await seguro_borrar_canal(interaction.channel)


class TicketSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Alianzas", description="Abrir ticket para alianzas", emoji="🤝", value="alianza"),
            discord.SelectOption(label="Reportes", description="Abrir ticket para reportes", emoji="❗", value="reporte"),
            discord.SelectOption(label="Postulaciones", description="Abrir ticket para postularte", emoji="🧑‍💼", value="postulacion"),
            discord.SelectOption(label="Otro", description="Consulta general u otros temas", emoji="❓", value="otro"),
        ]
        super().__init__(placeholder="Selecciona la opción que necesitas...", min_values=1, max_values=1, custom_id="ticket_main_select_v11")

    async def callback(self, interaction: discord.Interaction):
        try:
            if not interaction.response.is_done():
                await interaction.response.defer(ephemeral=True)
        except Exception:
            return

        categoria_tipo = self.values[0]
        guild = interaction.guild
        user = interaction.user
        channel_name = f"ticket-{categoria_tipo}-{user.name.lower()}"

        existing_channel = discord.utils.get(guild.channels, name=channel_name)
        if existing_channel:
            await interaction.followup.send(f"❌ Ya tienes un ticket abierto en {existing_channel.mention}", ephemeral=True)
            return

        rol_fundador = guild.get_role(ID_FUNDADOR)
        rol_co_owner = guild.get_role(ID_CO_OWNER)
        rol_admin = guild.get_role(ID_ADMINISTRADOR)

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False, view_channel=False),
            user: discord.PermissionOverwrite(read_messages=True, send_messages=True, attach_files=True, view_channel=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True, view_channel=True)
        }

        if rol_fundador: overwrites[rol_fundador] = discord.PermissionOverwrite(read_messages=True, send_messages=True, view_channel=True)
        if rol_co_owner: overwrites[rol_co_owner] = discord.PermissionOverwrite(read_messages=True, send_messages=True, view_channel=True)
        if rol_admin: overwrites[rol_admin] = discord.PermissionOverwrite(read_messages=True, send_messages=True, view_channel=True)

        target_category = interaction.channel.category or discord.utils.get(guild.categories, name="📁 TICKETS")
        if not target_category:
            target_category = await guild.create_category("📁 TICKETS")

        ticket_channel = await guild.create_text_channel(name=channel_name, category=target_category, overwrites=overwrites)

        if categoria_tipo == "alianza":
            plantilla_vanta = (
                "╔════════════════════════════════════════════╗ V A N T A  L E A G U E \n"
                "╚════════════════════════════════════════════╝\n"
                "          COMPETITION HAS NO LIMITS \n"
                "◢━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━◣\n\n"
                "        INSCRIPCIONES ABIERTAS \n"
                "          NUEVA LIGA DE HAXBALL\n\n"
                "    HAXBALL • X5\n"
                "    COMPETENCIA INTERNACIONAL\n"
                "    PRIMERA TEMPORADA (SEASON 1)\n"
                "◥━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━◤\n"
                "╭──────────────  ──────────────╮\n\n"
                "     UNA NUEVA ERA COMIENZA\n"
                "     INICIA LA COPA / TEMPORADA 1\n"
                "     REGISTRA A TU EQUIPO YA\n"
                "     COMUNIDAD INTERNACIONAL\n"
                "╰────────────────────────────────╯\n"
                "◢━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━◣\n\n"
                "     INSCRIBE A TU EQUIPO AHORA\n"
                "Buscamos a los mejores clubes y DTs que quieran demostrar su nivel en la cancha "
                "y escribir su nombre en la historia de Vanta. Mínimo 10 - Máximo 20 Jugadores Formato Oficial X5 Torneo Altamente Competitivo\n"
                "◥━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━◤\n"
                "╭────────────── ✦ ──────────────╮\n\n"
                "    ¿POR QUÉ INSCRIBIRTE EN VANTA? Competición organizada y seria Tabla de posiciones y goleadores Cobertura y transmisiones Difusión de tu club Respeto y fair play\n"
                "╰────────────────────────────────╯\n"
                "◢━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━◣\n\n"
                "     EL TERRENO DE JUEGO ESTÁ LISTO\n\n"
                "   ¿TIENES LO NECESARIO PARA DOMINAR?\n\n"
                "    INSCRÍBETE • COMPITE • SÉ EL CAMPEÓN \n"
                "◥━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━◤ ENLACE DEL SERVIDOR DE DISCORD\n"
                "[PONE AQUÍ TU INVITACIÓN DE DISCORD]\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "        「 NO VENIMOS A SER UNA MÁS 」\n\n"
                "               VENIMOS A HACER HISTORIA.\n"
                "◢◤◢◤◢◤◢◤◢◤◢◤◢◤◢◤◢◤◢◤\n"
                "https://discord.gg/6tJcG5qqvf"
            )

            await ticket_channel.send(content=plantilla_vanta)
            await ticket_channel.send(
                content=f"👋 ¡Hola {user.mention}! Arriba tienes nuestra plantilla oficial.\n"
                        "Haz clic en el botón verde **'Rellenar Plantilla de Alianza'** para ingresar los datos de tu comunidad en el formulario interactivo.",
                view=AlianzaTicketView()
            )

        elif categoria_tipo == "reporte":
            menciones_staff = f"<@&{ID_FUNDADOR}> <@&{ID_CO_OWNER}> <@&{ID_ADMINISTRADOR}>"
            embed_reporte = discord.Embed(
                title="❗ SISTEMA DE REPORTES",
                description=(
                    f"¡Hola {user.mention}!\n\n"
                    "Por favor, redacta los detalles de tu reporte en este chat con la siguiente plantilla:\n"
                    "• **Usuario / Equipo reportado:**\n"
                    "• **Infracción cometida:**\n"
                    "• **Pruebas (Capturas / Link del Replay):**\n\n"
                    "🚨 **El Staff ha sido notificado automáticamente y acudirá en breve.**"
                ),
                color=discord.Color.red()
            )
            await ticket_channel.send(content=menciones_staff, embed=embed_reporte, view=ReporteTicketView())

        elif categoria_tipo == "postulacion":
            embed_postulacion = discord.Embed(
                title="🧑‍💼 POSTULACIONES VANTA LEAGUE",
                description=(
                    f"¡Bienvenido {user.mention}!\n\n"
                    "Por favor, selecciona en el menú desplegable de abajo el puesto al que te gustaría postularte."
                ),
                color=discord.Color.blue()
            )
            await ticket_channel.send(embed=embed_postulacion, view=PostulacionTicketView())

        else:
            embed_otro = discord.Embed(
                title="❓ ATENCIÓN GENERAL Y SOPORTE",
                description=(
                    f"¡Hola {user.mention}!\n\n"
                    "Describe detalladamente tu consulta o problema en este canal. Un miembro del equipo administrativo te responderá pronto."
                ),
                color=discord.Color.green()
            )
            await ticket_channel.send(embed=embed_otro, view=OtroTicketView())

        await interaction.followup.send(f"✅ Ticket creado correctamente: {ticket_channel.mention}", ephemeral=True)


class MainTicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(TicketSelect())


# ==========================================
# --- 5. MÓDULO DE TRASPASOS INTERACTIVOS --
# ==========================================
class TraspasoFirmasView(discord.ui.View):
    def __init__(self, jugador, eq_origen_nombre, eq_destino_nombre, dt_origen_id, dt_destino_id, eq_origen_id, eq_destino_id, rol_origen_id, rol_destino_id):
        super().__init__(timeout=86400)
        self.jugador = jugador
        self.eq_origen_nombre = eq_origen_nombre
        self.eq_destino_nombre = eq_destino_nombre
        self.dt_origen_id = dt_origen_id
        self.dt_destino_id = dt_destino_id
        self.eq_origen_id = eq_origen_id
        self.eq_destino_id = eq_destino_id
        self.rol_origen_id = rol_origen_id
        self.rol_destino_id = rol_destino_id

        self.firma_origen = False if dt_origen_id else True
        self.firma_destino = False

        if not dt_origen_id:
            for item in self.children:
                if item.custom_id == "firma_dt_origen":
                    item.disabled = True
                    item.label = "✍️ No requerido (Agente Libre)"

    def generar_embed(self):
        f_orig_str = "✅ Firmado / No Requerido" if self.firma_origen else "⏳ Pendiente de firma"
        f_dest_str = "✅ Firmado" if self.firma_destino else "⏳ Pendiente de firma"
        orig_val = self.eq_origen_nombre if self.eq_origen_nombre else "Agente Libre"

        embed = discord.Embed(
            title="📝 Solicitud Formal de Traspaso",
            description=f"Se ha iniciado el proceso de transferencia para {self.jugador.mention}.",
            color=discord.Color.orange()
        )
        embed.add_field(name="Origen", value=orig_val, inline=True)
        embed.add_field(name="Destino", value=self.eq_destino_nombre, inline=True)
        embed.add_field(name="\u200b", value="\u200b", inline=False)
        embed.add_field(name="Firma DT Origen", value=f_orig_str, inline=True)
        embed.add_field(name="Firma DT Destino", value=f_dest_str, inline=True)
        embed.set_footer(text="Ambos DTs autorizados deben confirmar mediante los botones.")
        return embed

    @discord.ui.button(label="✍️ Firmar (DT Origen)", style=discord.ButtonStyle.secondary, custom_id="firma_dt_origen")
    async def firmar_origen(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            if not interaction.response.is_done():
                await interaction.response.defer()
        except Exception:
            pass

        if not self.dt_origen_id:
            await interaction.followup.send("❌ El jugador no tenía equipo previo.", ephemeral=True)
            return

        if interaction.user.id != self.dt_origen_id:
            await interaction.followup.send("❌ Solo el DT de origen puede firmar.", ephemeral=True)
            return

        self.firma_origen = True
        button.disabled = True
        button.style = discord.ButtonStyle.success
        button.label = "✍️ Firmado (Origen)"

        await interaction.message.edit(embed=self.generar_embed(), view=self)
        await self.comprobar_completado(interaction)

    @discord.ui.button(label="✍️ Firmar (DT Destino)", style=discord.ButtonStyle.primary, custom_id="firma_dt_destino")
    async def firmar_destino(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            if not interaction.response.is_done():
                await interaction.response.defer()
        except Exception:
            pass

        if interaction.user.id != self.dt_destino_id:
            await interaction.followup.send("❌ Solo el DT de destino puede firmar.", ephemeral=True)
            return

        self.firma_destino = True
        button.disabled = True
        button.style = discord.ButtonStyle.success
        button.label = "✍️ Firmado (Destino)"

        await interaction.message.edit(embed=self.generar_embed(), view=self)
        await self.comprobar_completado(interaction)

    async def comprobar_completado(self, interaction: discord.Interaction):
        if self.firma_origen and self.firma_destino:
            guild = interaction.guild
            
            if self.rol_origen_id:
                rol_old = guild.get_role(self.rol_origen_id)
                if rol_old and rol_old in self.jugador.roles:
                    await self.jugador.remove_roles(rol_old)

            if self.rol_destino_id:
                rol_new = guild.get_role(self.rol_destino_id)
                if rol_new:
                    await self.jugador.add_roles(rol_new)

            conn = sqlite3.connect(DB_NAME)
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO jugadores (discord_id, equipo_id) VALUES (?, ?) ON CONFLICT(discord_id) DO UPDATE SET equipo_id = ?",
                (self.jugador.id, self.eq_destino_id, self.eq_destino_id)
            )
            cursor.execute(
                "INSERT INTO historial_traspasos (jugador_id, origen_id, destino_id) VALUES (?, ?, ?)",
                (self.jugador.id, self.eq_origen_id, self.eq_destino_id)
            )
            conn.commit()
            conn.close()

            embed_final = self.generar_embed()
            embed_final.title = "✅ ¡Traspaso Oficializado!"
            embed_final.color = discord.Color.green()
            embed_final.description = f"El fichaje de {self.jugador.mention} por **{self.eq_destino_nombre}** se ha completado."

            for child in self.children:
                child.disabled = True

            await interaction.message.edit(embed=embed_final, view=self)


# ==========================================
# --- 6. MÓDULO MUSEO / VITRINA DE TROFEOS -
# ==========================================
class MuseoSelect(discord.ui.Select):
    def __init__(self, equipos):
        options = [discord.SelectOption(label=eq[1], value=str(eq[0]), emoji="🏛️") for eq in equipos]
        super().__init__(placeholder="Selecciona un equipo para consultar su vitrina...", options=options)

    async def callback(self, interaction: discord.Interaction):
        try:
            if not interaction.response.is_done():
                await interaction.response.defer(ephemeral=True)
        except Exception:
            pass

        equipo_id = int(self.values[0])

        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT nombre FROM equipos WHERE id = ?", (equipo_id,))
        eq_row = cursor.fetchone()
        eq_nombre = eq_row[0] if eq_row else "Equipo Desconocido"

        cursor.execute("SELECT tipo, nombre, jugador_id, temporada, detalles FROM museo_titulos WHERE equipo_id = ?", (equipo_id,))
        items = cursor.fetchall()
        conn.close()

        if not items:
            await interaction.followup.send(f"🏛️ La vitrina de **{eq_nombre}** aún no contiene registros.", ephemeral=True)
            return

        embed = discord.Embed(title=f"🏛️ Vitrina Histórica: {eq_nombre}", color=discord.Color.gold())
        
        titulos = [it for it in items if it[0] == 'titulo']
        goleadores = [it for it in items if it[0] in ['goleador', 'asistencia', 'mvp']]
        reconocimientos = [it for it in items if it[0] == 'reconocimiento']

        if titulos:
            txt = ""
            for t in titulos:
                temp_str = f" ({t[3]})" if t[3] else ""
                det_str = f" - *{t[4]}*" if t[4] else ""
                txt += f"🏆 **{t[1]}**{temp_str}{det_str}\n"
            embed.add_field(name="🏆 Títulos Oficiales", value=txt, inline=False)

        if goleadores:
            txt = ""
            for g in goleadores:
                jugador_user = interaction.guild.get_member(g[2]) if g[2] else None
                jugador_str = jugador_user.mention if jugador_user else "Jugador Desconocido"
                temp_str = f" ({g[3]})" if g[3] else ""
                det_str = f" - *{g[4]}*" if g[4] else ""
                emoji = "⚽" if g[0] == 'goleador' else ("👟" if g[0] == 'asistencia' else "⭐")
                txt += f"{emoji} **{g[1]}**: {jugador_str}{temp_str}{det_str}\n"
            embed.add_field(name="🥇 Distinciones Individuales", value=txt, inline=False)

        if reconocimientos:
            txt = ""
            for r in reconocimientos:
                temp_str = f" ({r[3]})" if r[3] else ""
                det_str = f" - *{r[4]}*" if r[4] else ""
                txt += f"🎖️ **{r[1]}**{temp_str}{det_str}\n"
            embed.add_field(name="🎖️ Reconocimientos Mención Honorífica", value=txt, inline=False)

        await interaction.followup.send(embed=embed, ephemeral=True)


class MuseoGroup(app_commands.Group):
    def __init__(self):
        super().__init__(name="museo", description="Gestión del museo y vitrinas")

    @app_commands.command(name="add_titulo", description="Añade un título a la vitrina de un equipo.")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.autocomplete(equipo=equipo_autocomplete)
    async def add_titulo(self, interaction: discord.Interaction, equipo: str, titulo: str, temporada: str = None, detalles: str = None):
        try:
            if not interaction.response.is_done():
                await interaction.response.defer()
        except Exception:
            pass

        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM equipos WHERE nombre = ?", (equipo,))
        eq = cursor.fetchone()

        if not eq:
            await interaction.followup.send(f"❌ El equipo **{equipo}** no existe.", ephemeral=True)
            conn.close()
            return

        cursor.execute(
            "INSERT INTO museo_titulos (equipo_id, tipo, nombre, temporada, detalles) VALUES (?, 'titulo', ?, ?, ?)",
            (eq[0], titulo, temporada, detalles)
        )
        conn.commit()
        conn.close()

        await interaction.followup.send(f"🏆 Se añadió el título **{titulo}** a la vitrina de **{equipo}**.")

    @app_commands.command(name="ver", description="Abre el menú interactivo para ver trofeos.")
    async def ver(self, interaction: discord.Interaction):
        try:
            if not interaction.response.is_done():
                await interaction.response.defer(ephemeral=True)
        except Exception:
            pass

        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT id, nombre FROM equipos")
        equipos = cursor.fetchall()
        conn.close()

        if not equipos:
            await interaction.followup.send("No hay equipos registrados.", ephemeral=True)
            return

        view = discord.ui.View()
        view.add_item(MuseoSelect(equipos))
        await interaction.followup.send("🏛️ Elige un equipo para consultar su vitrina:", view=view, ephemeral=True)

bot.tree.add_command(MuseoGroup())

# ==========================================
# --- 7. MÓDULO DE TEMPORADAS --------------
# ==========================================
class SeasonGroup(app_commands.Group):
    def __init__(self):
        super().__init__(name="season", description="Módulo de gestión de temporadas")

    @app_commands.command(name="create", description="Crea una nueva temporada")
    @app_commands.checks.has_permissions(administrator=True)
    async def season_create(self, interaction: discord.Interaction, nombre: str):
        try:
            if not interaction.response.is_done():
                await interaction.response.defer()
        except Exception:
            pass

        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        try:
            cursor.execute("INSERT INTO temporadas (nombre, estado) VALUES (?, 'inscripcion')", (nombre,))
            conn.commit()
            await interaction.followup.send(f"🏆 Temporada **{nombre}** creada exitosamente.")
        except sqlite3.IntegrityError:
            await interaction.followup.send(f"❌ La temporada **{nombre}** ya existe.", ephemeral=True)
        finally:
            conn.close()

    @app_commands.command(name="start", description="Activa la temporada más reciente")
    @app_commands.checks.has_permissions(administrator=True)
    async def season_start(self, interaction: discord.Interaction, nombre: str):
        try:
            if not interaction.response.is_done():
                await interaction.response.defer()
        except Exception:
            pass

        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM temporadas WHERE nombre = ?", (nombre,))
        row = cursor.fetchone()
        
        if not row:
            await interaction.followup.send(f"❌ No se encontró la temporada **{nombre}**.", ephemeral=True)
            conn.close()
            return

        cursor.execute("UPDATE temporadas SET estado = 'en_curso' WHERE id = ?", (row[0],))
        conn.commit()
        conn.close()

        await interaction.followup.send(f"🚀 La temporada **{nombre}** ha sido activada oficialmente.")

bot.tree.add_command(SeasonGroup())

# ==========================================
# --- 8. COMANDOS DE SETUP Y EVENTOS -------
# ==========================================
@bot.tree.command(name="setup_tickets", description="Despliega el panel interactivo de tickets en el canal actual")
@app_commands.default_permissions(administrator=True)
async def setup_tickets(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🎫 CENTRO DE ATENCIÓN Y SOPORTE - VANTA LEAGUE",
        description=(
            "¡Bienvenido al centro de soporte oficial de **Vanta League**!\n\n"
            "Selecciona una opción en el menú desplegable de abajo según tu requerimiento:\n\n"
            "🤝 **Alianzas:** Realiza una propuesta de asociación o partnership.\n"
            "❗ **Reportes:** Notifica conductas inapropiadas o faltas al reglamento.\n"
            "🧑‍💼 **Postulaciones:** Formulario de ingreso para Staff, Diseñadores, etc.\n"
            "❓ **Otro:** Dudas generales, soporte de cuenta o consultas directas.\n\n"
            "📌 *Al seleccionar una opción se creará un canal privado de atención.*"
        ),
        color=discord.Color.dark_theme()
    )
    embed.set_footer(text="Vanta League • Competition Has No Limits")
    await interaction.channel.send(embed=embed, view=MainTicketView())
    await interaction.response.send_message("✅ Panel de tickets desplegado exitosamente.", ephemeral=True)

@bot.event
async def on_ready():
    print("==========================================")
    print(f"🤖 Bot iniciado con éxito como: {bot.user.name}")
    print(f"🆔 Bot ID: {bot.user.id}")
    print("==========================================")
    
    bot.add_view(MainTicketView())
    bot.add_view(AlianzaTicketView())
    bot.add_view(PostulacionTicketView())
    bot.add_view(ReporteTicketView())
    bot.add_view(OtroTicketView())

    try:
        synced = await bot.tree.sync()
        print(f"🔄 Se han sincronizado {len(synced)} comandos de barra (Slash Commands).")
    except Exception as e:
        print(f"❌ Error sincronizando comandos: {e}")

keep_alive()

TOKEN = os.environ.get("DISCORD_TOKEN")
if TOKEN:
    bot.run(TOKEN)
else:
    print("❌ ERROR CRÍTICO: La variable de entorno 'DISCORD_TOKEN' no está configurada.")
