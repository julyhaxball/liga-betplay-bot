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

# IDs CONFIGURABLES DE TU SERVIDOR
ID_CANAL_PARTNERS = 123456789012345678  # 👈 Reemplaza con la ID de tu canal público de alianzas
ID_FUNDADOR = 1538383718459252786
ID_CO_OWNER = 1538390799299911766
ID_ADMINISTRADOR = 1538389985336762448
ID_ROL_PARTNER = 1538390251414757396

# AUTOCOMPLETADO GLOBAL DE EQUIPOS
async def equipo_autocomplete(interaction: discord.Interaction, current: str):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT nombre FROM equipos WHERE nombre LIKE ? LIMIT 25", (f"%{current}%",))
    equipos = cursor.fetchall()
    conn.close()
    return [app_commands.Choice(name=eq[0], value=eq[0]) for eq in equipos]

# Funciones aux para cerrar canales de forma segura
async def seguro_borrar_canal(channel):
    if channel:
        try:
            await channel.delete()
        except (discord.NotFound, discord.HTTPException):
            pass

# ==========================================
# --- 4. MODALES Y VISTAS DE TICKETS -------
# ==========================================

# 📝 Modal para ingresar plantilla de Alianza
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
            await interaction.response.defer()
        except Exception:
            pass

        await interaction.followup.send(
            f"✅ **Plantilla recibida correctamente.**\n"
            f"La propuesta de **{self.nombre_comunidad.value}** ha sido procesada y publicada en el canal de alianzas."
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


# 🤝 Vista de botones dentro del ticket de Alianza
class AlianzaTicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="📝 Rellenar Plantilla de Alianza", style=discord.ButtonStyle.success, custom_id="btn_abrir_modal_alianza")
    async def abrir_modal(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AlianzaModal())

    @discord.ui.button(label="🔔 Llamar al Staff", style=discord.ButtonStyle.secondary, custom_id="btn_llamar_staff_alianza")
    async def llamar_staff(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await interaction.response.send_message(
                f"🔔 <@&{ID_FUNDADOR}> <@&{ID_CO_OWNER}> <@&{ID_ADMINISTRADOR}>, el usuario {interaction.user.mention} requiere atención.",
                ephemeral=False
            )
        except Exception:
            pass

    @discord.ui.button(label="🔒 Cerrar Ticket", style=discord.ButtonStyle.danger, custom_id="btn_cerrar_ticket_alianza")
    async def cerrar_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await interaction.response.send_message("🔒 Cerrando ticket en 5 segundos...")
        except Exception:
            pass
        await asyncio.sleep(5)
        await seguro_borrar_canal(interaction.channel)


# 🧑‍💼 Menú Desplegable (Select) para Postulaciones
class PostulacionSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Administrador", description="Postularte para Admin de la liga", emoji="🛡️", value="admin"),
            discord.SelectOption(label="Diseñador Gráfico", description="Postularte para hacer banners/creativos", emoji="🎨", value="disenador"),
            discord.SelectOption(label="Moderador / Periodista", description="Postularte para moderar o redactar", emoji="📰", value="moderador"),
        ]
        super().__init__(placeholder="Selecciona el cargo al que deseas postularte...", min_values=1, max_values=1, custom_id="select_postulacion_cargo")

    async def callback(self, interaction: discord.Interaction):
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
            await interaction.response.send_message(f"🤖 **Preguntas para {cargo.capitalize()}:**\n\n{preguntas[cargo]}")
        except Exception:
            pass


class PostulacionTicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(PostulacionSelect())

    @discord.ui.button(label="🔒 Cerrar Ticket", style=discord.ButtonStyle.danger, custom_id="btn_cerrar_postulacion", row=1)
    async def cerrar_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await interaction.response.send_message("🔒 Cerrando ticket en 5 segundos...")
        except Exception:
            pass
        await asyncio.sleep(5)
        await seguro_borrar_canal(interaction.channel)


# ❗ Vista para Reportes (Corregido: style=discord.ButtonStyle.secondary para evitar el fallo de Style.warning)
class ReporteTicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🔔 Re-notificar al Staff", style=discord.ButtonStyle.secondary, custom_id="btn_re_llamar_staff")
    async def re_llamar_staff(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await interaction.response.send_message(
                f"⚠️ **Atención Staff:** <@&{ID_FUNDADOR}> <@&{ID_CO_OWNER}> <@&{ID_ADMINISTRADOR}>, el usuario {interaction.user.mention} solicita asistencia inmediata.",
                ephemeral=False
            )
        except Exception:
            pass

    @discord.ui.button(label="🔒 Cerrar Ticket", style=discord.ButtonStyle.danger, custom_id="btn_cerrar_reporte")
    async def cerrar_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await interaction.response.send_message("🔒 Cerrando ticket en 5 segundos...")
        except Exception:
            pass
        await asyncio.sleep(5)
        await seguro_borrar_canal(interaction.channel)


# 🎫 Menú Desplegable Principal del Panel de Tickets
class TicketSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Alianzas", description="Abrir ticket para alianzas", emoji="🤝", value="alianza"),
            discord.SelectOption(label="Reportes", description="Abrir ticket para reportes", emoji="❗", value="reporte"),
            discord.SelectOption(label="Postulaciones", description="Abrir ticket para postularte", emoji="🧑‍💼", value="postulacion"),
            discord.SelectOption(label="Otro", description="Consulta general u otros temas", emoji="❓", value="otro"),
        ]
        super().__init__(placeholder="Selecciona la opción que necesitas...", min_values=1, max_values=1, custom_id="ticket_main_select_v9")

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

        # 🤝 ALIANZAS
        if categoria_tipo == "alianza":
            plantilla_vanta = (
                "╔════════════════════════════════════════════╗ V A N T A  L E A G U E \n"
                "╚════════════════════════════════════════════╝\n"
                "         COMPETITION HAS NO LIMITS \n"
                "◢━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━◣\n\n"
                "       INSCRIPCIONES ABIERTAS \n"
                "         NUEVA LIGA DE HAXBALL\n\n"
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
                "       「 NO VENIMOS A SER UNA MÁS 」\n\n"
                "              VENIMOS A HACER HISTORIA.\n"
                "◢◤◢◤◢◤◢◤◢◤◢◤◢◤◢◤◢◤◢◤\n"
                "https://discord.gg/6tJcG5qqvf"
            )

            await ticket_channel.send(content=plantilla_vanta)
            await ticket_channel.send(
                content=f"👋 ¡Hola {user.mention}! Arriba tienes nuestra plantilla oficial.\n"
                        "Haz clic en el botón verde **'Rellenar Plantilla de Alianza'** para ingresar los datos de tu comunidad en el formulario interactivo.",
                view=AlianzaTicketView()
            )

        # ❗ REPORTES
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

        # 🧑‍💼 POSTULACIONES
        elif categoria_tipo == "postulacion":
            await ticket_channel.send(
                content=f"👋 ¡Hola {user.mention}! Selecciona en el menú desplegable el puesto al que deseas postularte:",
                view=PostulacionTicketView()
            )

        # ❓ OTRO
        else:
            await ticket_channel.send(
                content=f"👋 ¡Hola {user.mention}! Por favor, describe tu consulta detalladamente en este canal."
            )

        await interaction.followup.send(f"✅ Ticket creado correctamente: {ticket_channel.mention}", ephemeral=True)


class TicketLaunchView(discord.ui.View):
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
        try: await interaction.response.defer()
        except Exception: pass

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
        try: await interaction.response.defer()
        except Exception: pass

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
        try: await interaction.response.defer(ephemeral=True)
        except Exception: pass

        equipo_id = int(self.values[0])

        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT nombre FROM equipos WHERE id = ?", (equipo_id,))
        eq_nombre = cursor.fetchone()[0]

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
        try: await interaction.response.defer()
        except Exception: pass

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
        try: await interaction.response.defer(ephemeral=True)
        except Exception: pass

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
        try: await interaction.response.defer()
        except Exception: pass

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
    async def season_start(self, interaction: discord.Interaction):
        try: await interaction.response.defer()
        except Exception: pass

        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT id, nombre FROM temporadas WHERE estado = 'inscripcion' ORDER BY id DESC LIMIT 1")
        temp = cursor.fetchone()
        
        if not temp:
            await interaction.followup.send("❌ No hay ninguna temporada en 'inscripcion' para iniciar.", ephemeral=True)
            conn.close()
            return

        cursor.execute("UPDATE temporadas SET estado = 'cerrada' WHERE estado = 'activa'")
        cursor.execute("UPDATE temporadas SET estado = 'activa' WHERE id = ?", (temp[0],))
        conn.commit()
        conn.close()

        await interaction.followup.send(f"🚀 ¡Temporada **{temp[1]}** officially ACTIVA!")

bot.tree.add_command(SeasonGroup())

# ==========================================
# --- 8. COMANDOS DE LIGA & ADMINISTRACIÓN -
# ==========================================
@bot.tree.command(name="inscribir_equipo", description="Inscribe un equipo y crea su rol en el servidor.")
@app_commands.checks.has_permissions(administrator=True)
async def inscribir_equipo(interaction: discord.Interaction, nombre_equipo: str, dt: discord.Member):
    try: await interaction.response.defer()
    except Exception: pass

    guild = interaction.guild
    rol = await guild.create_role(name=nombre_equipo, reason="Rol oficial de equipo Haxball")
    await dt.add_roles(rol)

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO equipos (nombre, dt_id, rol_id) VALUES (?, ?, ?)", (nombre_equipo, dt.id, rol.id))
        conn.commit()
        await interaction.followup.send(f"✅ Equipo **{nombre_equipo}** registrado. Rol asignado a {dt.mention}.")
    except sqlite3.IntegrityError:
        await interaction.followup.send(f"❌ El equipo **{nombre_equipo}** ya existe.", ephemeral=True)
    finally:
        conn.close()

@bot.tree.command(name="borrar_equipo", description="Elimina un equipo y limpia todos sus registros.")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.autocomplete(nombre_equipo=equipo_autocomplete)
async def borrar_equipo(interaction: discord.Interaction, nombre_equipo: str):
    try: await interaction.response.defer()
    except Exception: pass

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT id, rol_id FROM equipos WHERE nombre = ?", (nombre_equipo,))
    equipo = cursor.fetchone()

    if not equipo:
        await interaction.followup.send(f"❌ El equipo **{nombre_equipo}** no existe.", ephemeral=True)
        conn.close()
        return

    equipo_id, rol_id = equipo
    rol = interaction.guild.get_role(rol_id)
    if rol:
        try: await rol.delete(reason="Equipo borrado por administrador")
        except discord.HTTPException: pass

    cursor.execute("UPDATE jugadores SET equipo_id = NULL WHERE equipo_id = ?", (equipo_id,))
    cursor.execute("DELETE FROM partidos WHERE equipo_local_id = ? OR equipo_visitante_id = ?", (equipo_id, equipo_id))
    cursor.execute("DELETE FROM museo_titulos WHERE equipo_id = ?", (equipo_id,))
    cursor.execute("DELETE FROM equipos WHERE id = ?", (equipo_id,))

    conn.commit()
    conn.close()

    await interaction.followup.send(f"🗑️ Equipo **{nombre_equipo}** borrado correctamente.")

@bot.tree.command(name="crear_partido", description="Registra un partido en el fixture de la temporada activa.")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.autocomplete(local=equipo_autocomplete, visitante=equipo_autocomplete)
async def crear_partido(interaction: discord.Interaction, local: str, visitante: str, jornada: int = 1):
    try: await interaction.response.defer()
    except Exception: pass

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM temporadas WHERE estado = 'activa' LIMIT 1")
    temp = cursor.fetchone()
    if not temp:
        await interaction.followup.send("❌ No hay ninguna temporada activa actualmente.", ephemeral=True)
        conn.close()
        return

    cursor.execute("SELECT id FROM equipos WHERE nombre = ?", (local,))
    eq_loc = cursor.fetchone()
    cursor.execute("SELECT id FROM equipos WHERE nombre = ?", (visitante,))
    eq_vis = cursor.fetchone()

    if not eq_loc or not eq_vis:
        await interaction.followup.send("❌ Uno o ambos equipos no se encuentran registrados.", ephemeral=True)
        conn.close()
        return

    cursor.execute(
        "INSERT INTO partidos (temporada_id, jornada, equipo_local_id, equipo_visitante_id) VALUES (?, ?, ?, ?)",
        (temp[0], jornada, eq_loc[0], eq_vis[0])
    )
    conn.commit()
    conn.close()

    await interaction.followup.send(f"⚽ Partido registrado (Jornada {jornada}): **{local}** vs **{visitante}**.")

@bot.tree.command(name="subir_replay", description="Carga el resultado y estadísticas de un partido mediante replay.")
@app_commands.autocomplete(local=equipo_autocomplete, visitante=equipo_autocomplete)
async def subir_replay(interaction: discord.Interaction, local: str, visitante: str, goles_local: int, goles_visitante: int, mvp: discord.Member, replay_url: str = None):
    try: await interaction.response.defer()
    except Exception: pass

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute('''
        SELECT p.id FROM partidos p
        JOIN equipos e1 ON p.equipo_local_id = e1.id
        JOIN equipos e2 ON p.equipo_visitante_id = e2.id
        WHERE e1.nombre = ? AND e2.nombre = ? AND p.jugado = 0
        LIMIT 1
    ''', (local, visitante))
    partido = cursor.fetchone()

    if not partido:
        await interaction.followup.send("❌ No se encontró un partido pendiente entre esos dos equipos.", ephemeral=True)
        conn.close()
        return

    partido_id = partido[0]

    cursor.execute(
        "UPDATE partidos SET goles_local = ?, goles_visitante = ?, jugado = 1, replay_url = ? WHERE id = ?",
        (goles_local, goles_visitante, replay_url, partido_id)
    )

    cursor.execute(
        "INSERT INTO jugadores (discord_id, mvps, partidos_jugados) VALUES (?, 1, 1) ON CONFLICT(discord_id) DO UPDATE SET mvps = mvps + 1, partidos_jugados = partidos_jugados + 1",
        (mvp.id,)
    )

    conn.commit()
    conn.close()

    embed = discord.Embed(title="📊 Partido Finalizado y Cargado", color=discord.Color.green())
    embed.add_field(name="Resultado", value=f"**{local}** {goles_local} - {goles_visitante} **{visitante}**", inline=False)
    embed.add_field(name="⭐ MVP", value=mvp.mention, inline=True)
    if replay_url:
        embed.add_field(name="📹 Replay", value=f"[Ver Grabación]({replay_url})", inline=True)

    await interaction.followup.send(embed=embed)

@bot.tree.command(name="tabla", description="Muestra la tabla de posiciones de la temporada activa.")
async def tabla(interaction: discord.Interaction):
    try: await interaction.response.defer()
    except Exception: pass

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute("SELECT id, nombre FROM temporadas WHERE estado = 'activa' LIMIT 1")
    temp = cursor.fetchone()

    if not temp:
        await interaction.followup.send("❌ No hay temporadas activas en este momento.", ephemeral=True)
        conn.close()
        return

    cursor.execute("SELECT id, nombre FROM equipos")
    equipos = cursor.fetchall()

    tabla_datos = []
    for eq_id, eq_nombre in equipos:
        cursor.execute('''
            SELECT 
                SUM(CASE WHEN (equipo_local_id = ? AND goles_local > goles_visitante) OR (equipo_visitante_id = ? AND goles_visitante > goles_local) THEN 3
                         WHEN (goles_local = goles_visitante) THEN 1 ELSE 0 END) as pts,
                COUNT(*) as pj,
                SUM(CASE WHEN (equipo_local_id = ? AND goles_local > goles_visitante) OR (equipo_visitante_id = ? AND goles_visitante > goles_local) THEN 1 ELSE 0 END) as pg,
                SUM(CASE WHEN goles_local = goles_visitante THEN 1 ELSE 0 END) as pe,
                SUM(CASE WHEN (equipo_local_id = ? AND goles_local < goles_visitante) OR (equipo_visitante_id = ? AND goles_visitante < goles_local) THEN 1 ELSE 0 END) as pp,
                SUM(CASE WHEN equipo_local_id = ? THEN goles_local ELSE goles_visitante END) as gf,
                SUM(CASE WHEN equipo_local_id = ? THEN goles_visitante ELSE goles_local END) as gc
            FROM partidos
            WHERE (equipo_local_id = ? OR equipo_visitante_id = ?) AND jugado = 1
        ''', (eq_id, eq_id, eq_id, eq_id, eq_id, eq_id, eq_id, eq_id, eq_id, eq_id))
        
        res = cursor.fetchone()
        pts = res[0] or 0
        pj = res[1] or 0
        pg = res[2] or 0
        pe = res[3] or 0
        pp = res[4] or 0
        gf = res[5] or 0
        gc = res[6] or 0
        dg = gf - gc

        tabla_datos.append({
            "nombre": eq_nombre,
            "pts": pts, "pj": pj, "pg": pg, "pe": pe, "pp": pp, "gf": gf, "gc": gc, "dg": dg
        })

    conn.close()
    tabla_datos.sort(key=lambda x: (x["pts"], x["dg"], x["gf"]), reverse=True)

    embed = discord.Embed(title=f"🏆 Tabla de Posiciones: {temp[1]}", color=discord.Color.gold())
    encabezado = "`Pos | Equipo          | PTS | PJ | PG | PE | PP | DG`"
    lineas = []
    for idx, t in enumerate(tabla_datos, 1):
        lineas.append(f"`{idx:<3}| {t['nombre']:<16} | {t['pts']:<3} | {t['pj']:<2} | {t['pg']:<2} | {t['pe']:<2} | {t['pp']:<2} | {t['dg']:<3}`")

    embed.description = f"{encabezado}\n" + "\n".join(lineas) if lineas else "No se han disputado partidos todavía."
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="sancionar", description="Aplica una sanción a un jugador (Admin).")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.choices(tipo=[
    app_commands.Choice(name="Tarjeta Amarilla 🟨", value="amarilla"),
    app_commands.Choice(name="Tarjeta Roja 🟥", value="roja"),
    app_commands.Choice(name="Suspensión por Partidos 🚫", value="suspension")
])
async def sancionar(interaction: discord.Interaction, jugador: discord.Member, tipo: str, partidos_suspension: int = 0, motivo: str = "Sin motivo especificado"):
    try: await interaction.response.defer()
    except Exception: pass

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO sanciones (jugador_id, tipo, partidos_suspension, motivo) VALUES (?, ?, ?, ?)",
        (jugador.id, tipo, partidos_suspension, motivo)
    )
    conn.commit()
    conn.close()

    embed = discord.Embed(title="⚠️ Sanción Disciplinaria Registrada", color=discord.Color.red())
    embed.add_field(name="Jugador", value=jugador.mention, inline=True)
    embed.add_field(name="Tipo de Sanción", value=tipo.capitalize(), inline=True)
    if partidos_suspension > 0:
        embed.add_field(name="Partidos de Suspensión", value=str(partidos_suspension), inline=True)
    embed.add_field(name="Motivo", value=motivo, inline=False)

    await interaction.followup.send(embed=embed)

@bot.tree.command(name="mi_perfil", description="Muestra la ficha y estadísticas del jugador.")
async def mi_perfil(interaction: discord.Interaction, usuario: discord.Member = None):
    try: await interaction.response.defer()
    except Exception: pass

    target = usuario or interaction.user

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT e.nombre, j.goles, j.asistencias, j.mvps, j.partidos_jugados 
        FROM jugadores j
        LEFT JOIN equipos e ON j.equipo_id = e.id
        WHERE j.discord_id = ?
    ''', (target.id,))
    data = cursor.fetchone()
    conn.close()

    equipo_nombre = data[0] if data and data[0] else "Agente Libre / Sin Equipo"
    goles = data[1] if data else 0
    asistencias = data[2] if data else 0
    mvps = data[3] if data else 0
    pj = data[4] if data else 0

    embed = discord.Embed(title=f"👤 Perfil Oficial: {target.display_name}", color=discord.Color.blue())
    embed.set_thumbnail(url=target.display_avatar.url)
    embed.add_field(name="Equipo", value=equipo_nombre, inline=False)
    embed.add_field(name="Partidos Jugados", value=str(pj), inline=True)
    embed.add_field(name="Goles ⚽", value=str(goles), inline=True)
    embed.add_field(name="Asistencias 👟", value=str(asistencias), inline=True)
    embed.add_field(name="MVPs ⭐", value=str(mvps), inline=True)

    await interaction.followup.send(embed=embed)

@bot.tree.command(name="traspaso", description="Inicia un traspaso formal con firmas requeridas de DTs.")
@app_commands.autocomplete(equipo_destino=equipo_autocomplete)
async def traspaso(interaction: discord.Interaction, jugador: discord.Member, equipo_destino: str):
    try: await interaction.response.defer()
    except Exception: pass

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute("SELECT id, dt_id, rol_id FROM equipos WHERE nombre = ?", (equipo_destino,))
    eq_destino = cursor.fetchone()

    if not eq_destino:
        await interaction.followup.send(f"❌ El equipo **{equipo_destino}** no existe.", ephemeral=True)
        conn.close()
        return

    eq_destino_id, dt_destino_id, rol_destino_id = eq_destino

    cursor.execute('''
        SELECT e.id, e.nombre, e.dt_id, e.rol_id 
        FROM jugadores j
        JOIN equipos e ON j.equipo_id = e.id
        WHERE j.discord_id = ?
    ''', (jugador.id,))
    eq_origen = cursor.fetchone()
    conn.close()

    if eq_origen:
        eq_origen_id, eq_origen_nombre, dt_origen_id, rol_origen_id = eq_origen
    else:
        eq_origen_id, eq_origen_nombre, dt_origen_id, rol_origen_id = None, None, None, None

    if eq_origen_id == eq_destino_id:
        await interaction.followup.send(f"❌ {jugador.mention} ya pertenece a **{equipo_destino}**.", ephemeral=True)
        return

    vista = TraspasoFirmasView(
        jugador=jugador,
        eq_origen_nombre=eq_origen_nombre,
        eq_destino_nombre=equipo_destino,
        dt_origen_id=dt_origen_id,
        dt_destino_id=dt_destino_id,
        eq_origen_id=eq_origen_id,
        eq_destino_id=eq_destino_id,
        rol_origen_id=rol_origen_id,
        rol_destino_id=rol_destino_id
    )

    await interaction.followup.send(embed=vista.generar_embed(), view=vista)

@bot.tree.command(name="ticket_panel", description="Publica el panel con menú de atención por ticket.")
@app_commands.checks.has_permissions(administrator=True)
async def ticket_panel(interaction: discord.Interaction):
    try: await interaction.response.defer(ephemeral=True)
    except Exception: pass

    menciones_roles = f"<@&{ID_FUNDADOR}> <@&{ID_CO_OWNER}> <@&{ID_ADMINISTRADOR}> <@&{ID_ROL_PARTNER}>"

    mensaje_descripcion = (
        "📢 **HORARIO DE ATENCIÓN DE TICKETS**\n\n"
        "🇨🇴 **Colombia:** 2:00 PM - 9:00 PM\n"
        "🇻🇪 **Venezuela:** 3:00 PM - 10:00 PM\n"
        "🇨🇱 **Chile:** 4:00 PM - 11:00 PM\n"
        "🇦🇷 **Argentina:** 4:00 PM - 11:00 PM\n"
        "🇺🇾 **Uruguay:** 4:00 PM - 11:00 PM\n\n"
        "⚠️ Los tickets fuera de este rango se responderán al siguiente día de disponibilidad.\n\n"
        "[🤝] **ALIANZAS** | [❗] **REPORTES** | [🧑‍💼] **POSTULACIONES** | [❓] **OTRO**"
    )

    embed = discord.Embed(title="🎫 Centro de Atención y Tickets", description=mensaje_descripcion, color=discord.Color.gold())
    await interaction.channel.send(content=menciones_roles, embed=embed, view=TicketLaunchView())
    await interaction.followup.send("✅ Panel publicado correctamente.", ephemeral=True)

# ==========================================
# --- 9. EVENTOS Y ARRANQUE DEL BOT --------
# ==========================================
@bot.event
async def on_ready():
    bot.add_view(TicketLaunchView())
    bot.add_view(AlianzaTicketView())
    bot.add_view(PostulacionTicketView())
    bot.add_view(ReporteTicketView())

    await bot.change_presence(
        status=discord.Status.online,
        activity=discord.Game(name="Vanta League | /tabla")
    )

    try:
        synced = await bot.tree.sync()
        print(f"✅ {len(synced)} Comandos sincronizados correctamente.")
    except Exception as e:
        print(f"Error en la sincronización: {e}")

    print(f"🤖 Bot encendido correctamente como {bot.user}")

if __name__ == "__main__":
    keep_alive()
    TOKEN = os.environ.get("DISCORD_TOKEN")
    if TOKEN:
        bot.run(TOKEN)
    else:
        print("❌ Error: Falta asignar la variable de entorno 'DISCORD_TOKEN'.")
