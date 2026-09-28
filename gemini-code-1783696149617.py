import os
import sqlite3
import asyncio
import struct
import zlib
from io import BytesIO
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

    # NUEVO: replays .hbr2 guardados dentro de la propia base de datos
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS replays (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            partido_id INTEGER NOT NULL,
            nombre_archivo TEXT NOT NULL,
            version INTEGER,
            frames INTEGER,
            datos BLOB NOT NULL,
            FOREIGN KEY (partido_id) REFERENCES partidos(id)
        )
    ''')

    conn.commit()
    conn.close()


init_db()

# ==========================================
# --- 2. SERVIDOR WEB (KEEP ALIVE 24/7) ----
# ==========================================
app = Flask('')


@app.route('/')
def home():
    return "Bot de Liga Haxball activo 24/7"


def run_web():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)


def keep_alive():
    t = Thread(target=run_web)
    t.daemon = True
    t.start()


# ==========================================
# --- 3. CONFIGURACIÓN Y CONSTANTES --------
# ==========================================
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

ID_CANAL_PARTNERS = 1538933871457075230
ID_FUNDADOR = 1538383718459252786
ID_CO_OWNER = 1538390799299911766
ID_ADMINISTRADOR = 1538389985336762448
ID_ROL_PARTNER = 1538933503641780265

REPLAY_MAX_BYTES = 10 * 1024 * 1024  # 10 MB por replay


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


def puede_cerrar_ticket(interaction: discord.Interaction) -> bool:
    """El dueño del ticket (ID guardado en el topic del canal) o el staff."""
    user = interaction.user
    perms = user.guild_permissions
    if perms.administrator or perms.manage_channels:
        return True
    if any(r.id in (ID_FUNDADOR, ID_CO_OWNER, ID_ADMINISTRADOR) for r in user.roles):
        return True
    return interaction.channel.topic == str(user.id)


async def cerrar_ticket_comun(interaction: discord.Interaction):
    if not puede_cerrar_ticket(interaction):
        await interaction.response.send_message(
            "❌ Solo el dueño del ticket o el staff pueden cerrarlo.", ephemeral=True
        )
        return
    await interaction.response.send_message("🔒 Cerrando ticket en 5 segundos...", ephemeral=True)
    await asyncio.sleep(5)
    await seguro_borrar_canal(interaction.channel)


# ==========================================
# --- 3B. LECTURA DE REPLAYS (.hbr2) -------
# ==========================================
def analizar_replay(data: bytes):
    """
    Valida un replay .hbr2 y devuelve (version, frames, segundos).
    Formato: 'HBR2' + version (uint32) + frames (uint32) + datos comprimidos (deflate).
    Lanza ValueError si el archivo no es un replay válido.
    """
    if len(data) < 12 or data[:4] != b'HBR2':
        raise ValueError("No es un replay .hbr2 válido de HaxBall.")
    version, frames = struct.unpack('>II', data[4:12])
    try:
        # Se descomprime (con tope de tamaño) solo para comprobar que no está corrupto
        zlib.decompressobj(-15).decompress(data[12:], 64 * 1024 * 1024)
    except zlib.error:
        raise ValueError("El replay está corrupto o incompleto.")
    return version, frames, frames / 60  # HaxBall corre a 60 ticks por segundo


def formato_duracion(segundos: float) -> str:
    total = int(segundos)
    return f"{total // 60}:{total % 60:02d}"


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
        await interaction.response.send_message(
            f"✅ **Plantilla recibida correctamente.**\n"
            f"La propuesta de **{self.nombre_comunidad.value}** ha sido procesada.",
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

    @discord.ui.button(label="🔔 Llamar al Staff", style=discord.ButtonStyle.primary, custom_id="btn_llamar_staff_alianza")
    async def llamar_staff(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            f"🔔 <@&{ID_FUNDADOR}> <@&{ID_CO_OWNER}> <@&{ID_ADMINISTRADOR}>, el usuario {interaction.user.mention} requiere atención.",
            ephemeral=False
        )

    @discord.ui.button(label="🔒 Cerrar Ticket", style=discord.ButtonStyle.danger, custom_id="btn_cerrar_ticket_alianza")
    async def cerrar_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await cerrar_ticket_comun(interaction)


class PostulacionSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Administrador", description="Postularte para Admin de la liga", emoji="🛡️", value="admin"),
            discord.SelectOption(label="Diseñador Gráfico", description="Postularte para hacer banners/creativos", emoji="🎨", value="disenador"),
            discord.SelectOption(label="Moderador / Periodista", description="Postularte para moderar o redactar", emoji="📰", value="moderador"),
        ]
        super().__init__(placeholder="Selecciona el cargo...", min_values=1, max_values=1, options=options, custom_id="select_postulacion_cargo")

    async def callback(self, interaction: discord.Interaction):
        cargo = self.values[0]
        preguntas = {
            "admin": "🛡️ **POSTULACIÓN A ADMINISTRADOR**\n1. ¿Edad y país?\n2. ¿Experiencia previa?\n3. ¿Tiempo disponible diario?",
            "disenador": "🎨 **POSTULACIÓN A DISEÑADOR**\n1. Adjunta 2 o 3 trabajos previos.\n2. ¿Qué programas usas?\n3. ¿Disponibilidad de entregas?",
            "moderador": "📰 **POSTULACIÓN A MODERADOR / PERIODISTA**\n1. ¿Moderación o Redacción?\n2. ¿Horarios activo?\n3. ¿Cómo manejas un conflicto?"
        }
        await interaction.response.send_message(f"🤖 **Preguntas para {cargo.capitalize()}:**\n\n{preguntas[cargo]}", ephemeral=True)


class PostulacionTicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(PostulacionSelect())

    @discord.ui.button(label="🔒 Cerrar Ticket", style=discord.ButtonStyle.danger, custom_id="btn_cerrar_postulacion", row=1)
    async def cerrar_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await cerrar_ticket_comun(interaction)


class ReporteTicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🔔 Re-notificar al Staff", style=discord.ButtonStyle.secondary, custom_id="btn_re_llamar_staff")
    async def re_llamar_staff(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            f"⚠️ **Atención Staff:** <@&{ID_FUNDADOR}> <@&{ID_CO_OWNER}> <@&{ID_ADMINISTRADOR}>, el usuario {interaction.user.mention} solicita asistencia.",
            ephemeral=False
        )

    @discord.ui.button(label="🔒 Cerrar Ticket", style=discord.ButtonStyle.danger, custom_id="btn_cerrar_reporte")
    async def cerrar_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await cerrar_ticket_comun(interaction)


class OtroTicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🔔 Llamar al Staff", style=discord.ButtonStyle.primary, custom_id="btn_llamar_staff_otro")
    async def llamar_staff(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            f"🔔 <@&{ID_FUNDADOR}> <@&{ID_CO_OWNER}> <@&{ID_ADMINISTRADOR}>, el usuario {interaction.user.mention} requiere asistencia.",
            ephemeral=False
        )

    @discord.ui.button(label="🔒 Cerrar Ticket", style=discord.ButtonStyle.danger, custom_id="btn_cerrar_otro")
    async def cerrar_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await cerrar_ticket_comun(interaction)


class TicketSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Alianzas", description="Abrir ticket para alianzas", emoji="🤝", value="alianza"),
            discord.SelectOption(label="Reportes", description="Abrir ticket para reportes", emoji="❗", value="reporte"),
            discord.SelectOption(label="Postulaciones", description="Abrir ticket para postularte", emoji="🧑‍💼", value="postulacion"),
            discord.SelectOption(label="Otro", description="Consulta general u otros temas", emoji="❓", value="otro"),
        ]
        super().__init__(
            placeholder="Selecciona la opción que necesitas...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="ticket_main_select_v14"
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

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

        # El ID del dueño se guarda en el topic para validar quién puede cerrar el ticket
        ticket_channel = await guild.create_text_channel(
            name=channel_name,
            category=target_category,
            overwrites=overwrites,
            topic=str(user.id)
        )

        if categoria_tipo == "alianza":
            await ticket_channel.send(
                content=f"👋 ¡Hola {user.mention}! Pulsa el botón verde para llenar la plantilla de alianza.",
                view=AlianzaTicketView()
            )

        elif categoria_tipo == "reporte":
            menciones_staff = f"<@&{ID_FUNDADOR}> <@&{ID_CO_OWNER}> <@&{ID_ADMINISTRADOR}>"
            embed_reporte = discord.Embed(
                title="❗ SISTEMA DE REPORTES",
                description=f"¡Hola {user.mention}!\nEscribe los detalles de tu reporte en este chat.",
                color=discord.Color.red()
            )
            await ticket_channel.send(content=menciones_staff, embed=embed_reporte, view=ReporteTicketView())

        elif categoria_tipo == "postulacion":
            embed_postulacion = discord.Embed(
                title="🧑‍💼 POSTULACIONES VANTA LEAGUE",
                description=f"¡Bienvenido {user.mention}!\nSelecciona el puesto abajo.",
                color=discord.Color.blue()
            )
            await ticket_channel.send(embed=embed_postulacion, view=PostulacionTicketView())

        else:
            embed_otro = discord.Embed(
                title="❓ ATENCIÓN GENERAL Y SOPORTE",
                description=f"¡Hola {user.mention}!\nEscribe tu duda en este chat.",
                color=discord.Color.green()
            )
            await ticket_channel.send(embed=embed_otro, view=OtroTicketView())

        await interaction.followup.send(f"✅ Ticket creado correctamente: {ticket_channel.mention}", ephemeral=True)


class MainTicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(TicketSelect())


# ==========================================
# --- 5. MÓDULO DE TRASPASOS CON FIRMAS ----
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
            description=f"Proceso de transferencia para {self.jugador.mention}.",
            color=discord.Color.orange()
        )
        embed.add_field(name="Origen", value=orig_val, inline=True)
        embed.add_field(name="Destino", value=self.eq_destino_nombre, inline=True)
        embed.add_field(name="Firma DT Origen", value=f_orig_str, inline=True)
        embed.add_field(name="Firma DT Destino", value=f_dest_str, inline=True)
        return embed

    @discord.ui.button(label="✍️ Firmar (DT Origen)", style=discord.ButtonStyle.secondary, custom_id="firma_dt_origen")
    async def firmar_origen(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.dt_origen_id:
            await interaction.response.send_message("❌ Solo el DT de origen puede firmar.", ephemeral=True)
            return

        self.firma_origen = True
        button.disabled = True
        button.style = discord.ButtonStyle.success
        button.label = "✍️ Firmado (Origen)"

        await interaction.response.edit_message(embed=self.generar_embed(), view=self)
        await self.comprobar_completado(interaction)

    @discord.ui.button(label="✍️ Firmar (DT Destino)", style=discord.ButtonStyle.primary, custom_id="firma_dt_destino")
    async def firmar_destino(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.dt_destino_id:
            await interaction.response.send_message("❌ Solo el DT de destino puede firmar.", ephemeral=True)
            return

        self.firma_destino = True
        button.disabled = True
        button.style = discord.ButtonStyle.success
        button.label = "✍️ Firmado (Destino)"

        await interaction.response.edit_message(embed=self.generar_embed(), view=self)
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

            for child in self.children:
                child.disabled = True

            try:
                await interaction.message.edit(embed=embed_final, view=self)
            except discord.HTTPException:
                pass


# ==========================================
# --- 6. MÓDULO MUSEO / VITRINA ------------
# ==========================================
class MuseoSelect(discord.ui.Select):
    def __init__(self, equipos):
        options = [discord.SelectOption(label=eq[1], value=str(eq[0]), emoji="🏛️") for eq in equipos]
        super().__init__(placeholder="Selecciona un equipo...", options=options)

    async def callback(self, interaction: discord.Interaction):
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
            await interaction.response.send_message(f"🏛️ La vitrina de **{eq_nombre}** aún está vacía.", ephemeral=True)
            return

        embed = discord.Embed(title=f"🏛️ Vitrina Histórica: {eq_nombre}", color=discord.Color.gold())
        for it in items:
            embed.add_field(name=f"🏆 {it[1]}", value=f"Temporada: {it[3] or 'N/A'}\n{it[4] or ''}", inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=True)


class MuseoGroup(app_commands.Group):
    def __init__(self):
        super().__init__(name="museo", description="Gestión del museo y vitrinas")

    @app_commands.command(name="add_titulo", description="Añade un título a la vitrina de un equipo")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.autocomplete(equipo=equipo_autocomplete)
    async def add_titulo(self, interaction: discord.Interaction, equipo: str, titulo: str, temporada: str = None, detalles: str = None):
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM equipos WHERE nombre = ?", (equipo,))
        eq = cursor.fetchone()

        if not eq:
            await interaction.response.send_message(f"❌ El equipo **{equipo}** no existe.", ephemeral=True)
            conn.close()
            return

        cursor.execute(
            "INSERT INTO museo_titulos (equipo_id, tipo, nombre, temporada, detalles) VALUES (?, 'titulo', ?, ?, ?)",
            (eq[0], titulo, temporada, detalles)
        )
        conn.commit()
        conn.close()

        await interaction.response.send_message(f"🏆 Se añadió el título **{titulo}** a la vitrina de **{equipo}**.")

    @app_commands.command(name="ver", description="Abre el menú para ver trofeos")
    async def ver(self, interaction: discord.Interaction):
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT id, nombre FROM equipos")
        equipos = cursor.fetchall()
        conn.close()

        if not equipos:
            await interaction.response.send_message("No hay equipos registrados.", ephemeral=True)
            return

        view = discord.ui.View()
        view.add_item(MuseoSelect(equipos))
        await interaction.response.send_message("🏛️ Elige un equipo:", view=view, ephemeral=True)


bot.tree.add_command(MuseoGroup())


# ==========================================
# --- 7. MÓDULO DE TEMPORADAS --------------
# ==========================================
class SeasonGroup(app_commands.Group):
    def __init__(self):
        super().__init__(name="season", description="Gestión de temporadas")

    @app_commands.command(name="create", description="Crea una nueva temporada")
    @app_commands.checks.has_permissions(administrator=True)
    async def season_create(self, interaction: discord.Interaction, nombre: str):
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        try:
            cursor.execute("INSERT INTO temporadas (nombre, estado) VALUES (?, 'inscripcion')", (nombre,))
            conn.commit()
            await interaction.response.send_message(f"🏆 Temporada **{nombre}** creada.")
        except sqlite3.IntegrityError:
            await interaction.response.send_message(f"❌ La temporada **{nombre}** ya existe.", ephemeral=True)
        finally:
            conn.close()

    @app_commands.command(name="start", description="Activa la temporada")
    @app_commands.checks.has_permissions(administrator=True)
    async def season_start(self, interaction: discord.Interaction, nombre: str):
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("UPDATE temporadas SET estado = 'en_curso' WHERE nombre = ?", (nombre,))
        conn.commit()
        conn.close()

        await interaction.response.send_message(f"🚀 La temporada **{nombre}** ha sido activada.")


bot.tree.add_command(SeasonGroup())


# ==========================================
# --- 8. MÓDULO DE LIGA, PARTIDOS Y STATS --
# ==========================================
class LigaGroup(app_commands.Group):
    def __init__(self):
        super().__init__(name="liga", description="Comandos operativos de la liga y partidos")

    @app_commands.command(name="registrar_partido", description="Registra el marcador de un partido jugado (con replay opcional)")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.autocomplete(local=equipo_autocomplete, visitante=equipo_autocomplete)
    @app_commands.describe(
        replay="Link del replay (opcional)",
        replay_archivo="Archivo .hbr2 del replay (opcional, se guarda y se valida)"
    )
    async def registrar_partido(
        self,
        interaction: discord.Interaction,
        temporada: str,
        jornada: int,
        local: str,
        visitante: str,
        goles_local: int,
        goles_visitante: int,
        replay: str = None,
        replay_archivo: discord.Attachment = None
    ):
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()

        cursor.execute("SELECT id FROM temporadas WHERE nombre = ?", (temporada,))
        temp = cursor.fetchone()
        if not temp:
            await interaction.response.send_message(f"❌ La temporada **{temporada}** no existe.", ephemeral=True)
            conn.close()
            return
        temp_id = temp[0]

        cursor.execute("SELECT id FROM equipos WHERE nombre = ?", (local,))
        eq_l = cursor.fetchone()
        cursor.execute("SELECT id FROM equipos WHERE nombre = ?", (visitante,))
        eq_v = cursor.fetchone()

        if not eq_l or not eq_v:
            await interaction.response.send_message("❌ Uno de los equipos no está registrado.", ephemeral=True)
            conn.close()
            return

        # --- Lectura y validación del replay ANTES de guardar nada ---
        datos_replay = None
        info_replay = None
        respondido_con_defer = False

        if replay_archivo is not None:
            nombre = replay_archivo.filename.lower()
            if not (nombre.endswith('.hbr2') or nombre.endswith('.hbr')):
                await interaction.response.send_message("❌ El archivo debe ser un replay `.hbr2` de HaxBall.", ephemeral=True)
                conn.close()
                return
            if replay_archivo.size > REPLAY_MAX_BYTES:
                await interaction.response.send_message("❌ El replay pesa más de 10 MB.", ephemeral=True)
                conn.close()
                return

            await interaction.response.defer()
            respondido_con_defer = True
            datos_replay = await replay_archivo.read()
            try:
                info_replay = analizar_replay(datos_replay)
            except ValueError as e:
                await interaction.followup.send(f"❌ {e}", ephemeral=True)
                conn.close()
                return

        cursor.execute(
            "INSERT INTO partidos (temporada_id, jornada, equipo_local_id, equipo_visitante_id, goles_local, goles_visitante, jugado, replay_url) VALUES (?, ?, ?, ?, ?, ?, 1, ?)",
            (temp_id, jornada, eq_l[0], eq_v[0], goles_local, goles_visitante, replay)
        )
        partido_id = cursor.lastrowid

        texto_replay = ""
        if datos_replay is not None:
            version, frames, segundos = info_replay
            cursor.execute(
                "INSERT INTO replays (partido_id, nombre_archivo, version, frames, datos) VALUES (?, ?, ?, ?, ?)",
                (partido_id, replay_archivo.filename, version, frames, datos_replay)
            )
            texto_replay = f"\n🎬 Replay guardado (duración: **{formato_duracion(segundos)}**). Descárgalo con `/liga replay {partido_id}`."
        elif replay:
            texto_replay = f"\n🎬 Replay: {replay}"

        conn.commit()
        conn.close()

        mensaje = (
            f"⚽ Partido registrado (ID **{partido_id}**): **{local} {goles_local} - {goles_visitante} {visitante}** "
            f"(Jornada {jornada}).{texto_replay}\n"
            f"👉 Añade goleadores con `/liga anotar partido_id:{partido_id}`."
        )
        if respondido_con_defer:
            await interaction.followup.send(mensaje)
        else:
            await interaction.response.send_message(mensaje)

    @app_commands.command(name="replay", description="Descarga el replay guardado de un partido")
    async def replay(self, interaction: discord.Interaction, partido_id: int):
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT nombre_archivo, datos FROM replays WHERE partido_id = ? ORDER BY id DESC LIMIT 1",
            (partido_id,)
        )
        row = cursor.fetchone()
        conn.close()

        if not row:
            await interaction.response.send_message(f"❌ El partido **{partido_id}** no tiene un replay guardado.", ephemeral=True)
            return

        archivo = discord.File(BytesIO(row[1]), filename=row[0])
        await interaction.response.send_message(f"🎬 Replay del partido **{partido_id}**:", file=archivo)

    @app_commands.command(name="anotar", description="Registra goles, asistencias y MVP de un jugador en un partido")
    @app_commands.checks.has_permissions(administrator=True)
    async def anotar(
        self,
        interaction: discord.Interaction,
        partido_id: int,
        miembro: discord.Member,
        goles: int = 0,
        asistencias: int = 0,
        mvp: bool = False
    ):
        if goles < 0 or asistencias < 0:
            await interaction.response.send_message("❌ Los valores no pueden ser negativos.", ephemeral=True)
            return

        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()

        cursor.execute("SELECT 1 FROM partidos WHERE id = ?", (partido_id,))
        if not cursor.fetchone():
            await interaction.response.send_message(f"❌ El partido **{partido_id}** no existe.", ephemeral=True)
            conn.close()
            return

        cursor.execute(
            "SELECT 1 FROM goles_partido WHERE partido_id = ? AND jugador_id = ?",
            (partido_id, miembro.id)
        )
        ya_registrado = cursor.fetchone() is not None

        cursor.execute(
            "INSERT INTO jugadores (discord_id) VALUES (?) ON CONFLICT(discord_id) DO NOTHING",
            (miembro.id,)
        )

        filas = []
        if goles:
            filas.append(('gol', goles))
        if asistencias:
            filas.append(('asistencia', asistencias))
        if mvp:
            filas.append(('mvp', 1))
        if not filas and not ya_registrado:
            filas.append(('participacion', 0))

        for tipo, cantidad in filas:
            cursor.execute(
                "INSERT INTO goles_partido (partido_id, jugador_id, tipo, cantidad) VALUES (?, ?, ?, ?)",
                (partido_id, miembro.id, tipo, cantidad)
            )

        # partidos_jugados solo suma la primera vez que el jugador aparece en ese partido
        cursor.execute(
            "UPDATE jugadores SET goles = goles + ?, asistencias = asistencias + ?, mvps = mvps + ?, partidos_jugados = partidos_jugados + ? WHERE discord_id = ?",
            (goles, asistencias, 1 if mvp else 0, 0 if ya_registrado else 1, miembro.id)
        )
        conn.commit()
        conn.close()

        extra = " ⭐ MVP" if mvp else ""
        await interaction.response.send_message(
            f"✅ {miembro.mention} en el partido **{partido_id}**: ⚽ {goles} gol(es), 🅰️ {asistencias} asistencia(s){extra}."
        )

    @app_commands.command(name="stats", description="Muestra las estadísticas de un jugador")
    async def stats(self, interaction: discord.Interaction, miembro: discord.Member):
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT equipo_id, goles, asistencias, mvps, partidos_jugados FROM jugadores WHERE discord_id = ?", (miembro.id,))
        row = cursor.fetchone()

        eq_nombre = "Agente Libre"
        if row and row[0]:
            cursor.execute("SELECT nombre FROM equipos WHERE id = ?", (row[0],))
            eq_row = cursor.fetchone()
            if eq_row:
                eq_nombre = eq_row[0]

        conn.close()

        if not row:
            await interaction.response.send_message(f"📊 {miembro.mention} aún no registra estadísticas en la liga.", ephemeral=True)
            return

        embed = discord.Embed(title=f"📊 Estadísticas de {miembro.display_name}", color=discord.Color.blue())
        embed.add_field(name="Equipo", value=eq_nombre, inline=False)
        embed.add_field(name="Goles", value=str(row[1]), inline=True)
        embed.add_field(name="Asistencias", value=str(row[2]), inline=True)
        embed.add_field(name="MVPs", value=str(row[3]), inline=True)
        embed.add_field(name="Partidos Jugados", value=str(row[4]), inline=True)

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="sancion", description="Aplica una sanción a un jugador")
    @app_commands.checks.has_permissions(administrator=True)
    async def sancion(self, interaction: discord.Interaction, miembro: discord.Member, tipo: str, partidos: int, motivo: str):
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO jugadores (discord_id) VALUES (?) ON CONFLICT(discord_id) DO NOTHING",
            (miembro.id,)
        )
        cursor.execute(
            "INSERT INTO sanciones (jugador_id, tipo, partidos_suspension, motivo, activa) VALUES (?, ?, ?, ?, 1)",
            (miembro.id, tipo, partidos, motivo)
        )
        conn.commit()
        conn.close()

        await interaction.response.send_message(f"⚖️ Sanción aplicada a {miembro.mention}: **{tipo}** ({partidos} partidos). Motivo: {motivo}")


bot.tree.add_command(LigaGroup())


# ==========================================
# --- 9. COMANDOS DE SETUP Y EVENTOS -------
# ==========================================
@bot.tree.command(name="setup_tickets", description="Despliega el panel de tickets")
@app_commands.default_permissions(administrator=True)
async def setup_tickets(interaction: discord.Interaction):
    await interaction.response.send_message("✅ Panel desplegado con éxito.", ephemeral=True)

    embed = discord.Embed(
        title="🎫 Centro de Atención y Tickets",
        description=(
            "📢 **HORARIO DE ATENCIÓN DE TICKETS**\n\n"
            "Les informamos que el horario oficial de atención de tickets será el siguiente:\n\n"
            "🇨🇴 **Colombia:** 2:00 PM - 9:00 PM\n"
            "🇻🇪 **Venezuela:** 3:00 PM - 10:00 PM\n"
            "🇨🇱 **Chile:** 4:00 PM - 11:00 PM\n"
            "🇦🇷 **Argentina:** 4:00 PM - 11:00 PM\n"
            "🇺🇾 **Uruguay:** 4:00 PM - 11:00 PM\n\n"
            "⚠️ Los tickets abiertos fuera de este horario podrán ser atendidos al día siguiente, dependiendo de la disponibilidad del Staff.\n\n"
            "Agradecemos su comprensión y colaboración. 🏆⚽"
        ),
        color=discord.Color.dark_theme()
    )
    await interaction.channel.send(embed=embed, view=MainTicketView())


@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        msg = "❌ No tienes permisos para usar este comando."
    else:
        msg = "❌ Ocurrió un error ejecutando el comando."
        print(f"Error en comando: {error}")
    if interaction.response.is_done():
        await interaction.followup.send(msg, ephemeral=True)
    else:
        await interaction.response.send_message(msg, ephemeral=True)


@bot.event
async def on_ready():
    print("==========================================")
    print(f"🤖 Bot activo como: {bot.user.name}")
    print("==========================================")

    bot.add_view(MainTicketView())
    bot.add_view(AlianzaTicketView())
    bot.add_view(PostulacionTicketView())
    bot.add_view(ReporteTicketView())
    bot.add_view(OtroTicketView())

    try:
        synced = await bot.tree.sync()
        print(f"🔄 Sincronizados {len(synced)} comandos de barra.")
    except Exception as e:
        print(f"❌ Error al sincronizar: {e}")


keep_alive()

TOKEN = os.environ.get("DISCORD_TOKEN")
if TOKEN:
    bot.run(TOKEN)
