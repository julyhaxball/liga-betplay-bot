import os
import json
import sqlite3
import datetime
import asyncio
import re
from threading import Thread
from flask import Flask

import discord
from discord.ext import commands
from discord import app_commands

# --- BASE DE DATOS Y ESTRUCTURA ---
DB_NAME = "liga_haxball.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # Temporadas
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS temporadas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL UNIQUE,
            estado TEXT NOT NULL DEFAULT 'inscripcion',
            fecha_inicio TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Equipos
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
    
    # Jugadores
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
    
    # Partidos / Fixture
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
    
    # Registro de Goles / Estadísticas por Partido
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
    
    # Sanciones
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

    # Traspasos
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

    # Museo / Vitrina de Trofeos
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


# --- SERVIDOR WEB (KEEP ALIVE RENDER) ---
app = Flask('')

@app.route('/')
def home():
    return "Bot de Liga Haxball activo 24/7"

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run_web)
    t.start()

init_db()

# --- CONFIGURACIÓN DEL BOT ---
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)


# --- AUTOCOMPLETADO GLOBAL ---
async def equipo_autocomplete(interaction: discord.Interaction, current: str):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT nombre FROM equipos WHERE nombre LIKE ? LIMIT 25", (f"%{current}%",))
    equipos = cursor.fetchall()
    conn.close()
    return [app_commands.Choice(name=eq[0], value=eq[0]) for eq in equipos]


# --- VISTA INTERACTIVA DENTRO DEL TICKET ---
class TicketInteractiveView(discord.ui.View):
    def __init__(self, categoria_tipo: str = "otro"):
        super().__init__(timeout=None)
        self.categoria_tipo = categoria_tipo

    @discord.ui.button(label="📌 Ver información / FAQ", style=discord.ButtonStyle.primary, custom_id="btn_faq_ticket")
    async def ver_faq(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        respuestas = {
            "alianza": "🤝 **Requisitos de Alianza:**\n- Contar con al menos 100 miembros activos.\n- Servidor organizado de Haxball o eSports.\n- Para concretar, presiona **Llamar al Staff** y déjanos el enlace de tu servidor.",
            "reporte": "❗ **Para realizar un reporte:**\n- Adjunta captura de pantalla o video de la infracción.\n- Indica el nombre/ID del usuario reportado y la regla incumplida.",
            "postulacion": "🧑‍💼 **Postulaciones abiertas:**\n- Para Admin / Periodista / Creador de contenido.\n- Deja tus datos: Edad, experiencia previa y disponibilidad de tiempo.",
            "otro": "❓ **Consulta general:**\n- Por favor escribe tu duda detalladamente aquí en el canal."
        }
        info = respuestas.get(self.categoria_tipo, "Escribe tu duda detalladamente en este canal.")
        await interaction.followup.send(f"ℹ️ **Información Automática:**\n\n{info}", ephemeral=True)

    @discord.ui.button(label="🔔 Llamar al Staff", style=discord.ButtonStyle.danger, custom_id="btn_llamar_staff")
    async def llamar_staff(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        ID_ADMINISTRADOR = 1538389985336762448
        await interaction.followup.send(f"🔔 <@&{ID_ADMINISTRADOR}>, el usuario {interaction.user.mention} solicita asistencia de un administrador.")

    @discord.ui.button(label="✅ Duda Resuelta (Cerrar)", style=discord.ButtonStyle.success, custom_id="btn_duda_resuelta")
    async def duda_resuelta(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await interaction.followup.send("✅ ¡Nos alegra haberte ayudado! Este ticket se cerrará y eliminará en 5 segundos...")
        await asyncio.sleep(5)
        await interaction.channel.delete()


# --- PANEL INICIAL Y SELECTOR DE TICKETS ---
class TicketSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Alianzas", description="Hacer una alianza con nosotros", emoji="🤝", value="alianza"),
            discord.SelectOption(label="Reportes", description="Reportar algo que no sea apto", emoji="❗", value="reporte"),
            discord.SelectOption(label="Postulaciones", description="Postularse para ser admin, periodista, etc.", emoji="🧑‍💼", value="postulacion"),
            discord.SelectOption(label="Otro", description="Algo distinto al resto", emoji="❓", value="otro"),
        ]
        super().__init__(
            placeholder="Selecciona el tipo de ticket que deseas abrir...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="ticket_select_menu_v4"
        )

    async def callback(self, interaction: discord.Interaction):
        # Evitar timeout diferyendo inmediatamente
        await interaction.response.defer(ephemeral=True)

        categoria_tipo = self.values[0]
        guild = interaction.guild
        user = interaction.user

        channel_name = f"ticket-{categoria_tipo}-{user.name.lower()}"
        
        existing_channel = discord.utils.get(guild.channels, name=channel_name)
        if existing_channel:
            await interaction.followup.send(f"❌ Ya tienes un ticket abierto en {existing_channel.mention}", ephemeral=True)
            return

        ID_ADMINISTRADOR = 1538389985336762448
        rol_admin = guild.get_role(ID_ADMINISTRADOR)

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False, view_channel=False),
            user: discord.PermissionOverwrite(read_messages=True, send_messages=True, attach_files=True, view_channel=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True, view_channel=True, embed_links=True)
        }

        if rol_admin:
            overwrites[rol_admin] = discord.PermissionOverwrite(read_messages=True, send_messages=True, view_channel=True)

        target_category = interaction.channel.category
        if not target_category:
            target_category = discord.utils.get(guild.categories, name="📁 TICKETS")
            if not target_category:
                target_category = await guild.create_category("📁 TICKETS")

        try:
            ticket_channel = await guild.create_text_channel(
                name=channel_name,
                category=target_category,
                overwrites=overwrites
            )

            embed = discord.Embed(
                title=f"🎫 Ticket de {categoria_tipo.capitalize()}",
                description=f"Hola {user.mention}.\n\nUsa los botones interactivos de abajo para consultar información rápida, solicitar la ayuda del Staff o cerrar la consulta si tu duda queda resuelta.",
                color=discord.Color.blue()
            )

            await ticket_channel.send(content=f"{user.mention}", embed=embed, view=TicketInteractiveView(categoria_tipo))
            await interaction.followup.send(f"✅ Ticket creado correctamente: {ticket_channel.mention}", ephemeral=True)

        except Exception as e:
            await interaction.followup.send(f"❌ Error al crear el ticket: {e}", ephemeral=True)


class TicketLaunchView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(TicketSelect())


# --- TRASPASOS E INTERACCIONES ---
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
        embed.set_footer(text="Ambos DTs autorizados deben confirmar con los botones correspondientes.")
        return embed

    @discord.ui.button(label="✍️ Firmar (DT Origen)", style=discord.ButtonStyle.secondary, custom_id="firma_dt_origen")
    async def firmar_origen(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
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
        await interaction.response.defer()
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


# --- MUSEO / VITRINA DE TROFEOS ---
class MuseoSelect(discord.ui.Select):
    def __init__(self, equipos):
        options = [discord.SelectOption(label=eq[1], value=str(eq[0]), emoji="🏛️") for eq in equipos]
        super().__init__(placeholder="Selecciona un equipo para consultar su vitrina...", options=options)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
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
        await interaction.response.defer()
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
        await interaction.response.defer(ephemeral=True)
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


# --- GRUPO DE TEMPORADAS ---
class SeasonGroup(app_commands.Group):
    def __init__(self):
        super().__init__(name="season", description="Módulo de gestión de temporadas")

    @app_commands.command(name="create", description="Crea una nueva temporada")
    @app_commands.checks.has_permissions(administrator=True)
    async def season_create(self, interaction: discord.Interaction, nombre: str):
        await interaction.response.defer()
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
        await interaction.response.defer()
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

        await interaction.followup.send(f"🚀 ¡Temporada **{temp[1]}** oficialmente ACTIVA!")

bot.tree.add_command(SeasonGroup())


# --- GESTIÓN DE EQUIPOS Y FIXTURE ---
@bot.tree.command(name="inscribir_equipo", description="Inscribe un equipo y crea su rol en el servidor.")
@app_commands.checks.has_permissions(administrator=True)
async def inscribir_equipo(interaction: discord.Interaction, nombre_equipo: str, dt: discord.Member):
    await interaction.response.defer()
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
    await interaction.response.defer()
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
        try:
            await rol.delete(reason="Equipo borrado por administrador")
        except discord.HTTPException:
            pass

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
    await interaction.response.defer()
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


# --- ESTADÍSTICAS Y REPLAYS ---
@bot.tree.command(name="subir_replay", description="Carga el resultado y estadísticas de un partido mediante replay.")
@app_commands.autocomplete(local=equipo_autocomplete, visitante=equipo_autocomplete)
async def subir_replay(interaction: discord.Interaction, local: str, visitante: str, goles_local: int, goles_visitante: int, mvp: discord.Member, replay_url: str = None):
    await interaction.response.defer()
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
    await interaction.response.defer()
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


# --- SANCIONES Y PERFIL ---
@bot.tree.command(name="sancionar", description="Aplica una sanción a un jugador (Admin).")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.choices(tipo=[
    app_commands.Choice(name="Tarjeta Amarilla 🟨", value="amarilla"),
    app_commands.Choice(name="Tarjeta Roja 🟥", value="roja"),
    app_commands.Choice(name="Suspensión por Partidos 🚫", value="suspension")
])
async def sancionar(interaction: discord.Interaction, jugador: discord.Member, tipo: str, partidos_suspension: int = 0, motivo: str = "Sin motivo especificado"):
    await interaction.response.defer()
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
    await interaction.response.defer()
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


# --- COMANDOS TRASPASOS & PANEL DE TICKETS ---
@bot.tree.command(name="traspaso", description="Inicia un traspaso formal con firmas requeridas de DTs.")
@app_commands.autocomplete(equipo_destino=equipo_autocomplete)
async def traspaso(interaction: discord.Interaction, jugador: discord.Member, equipo_destino: str):
    await interaction.response.defer()

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
    await interaction.response.defer(ephemeral=True)
    menciones_roles = "<@&1538383718459252786> <@&1538390799299911766> <@&1538389985336762448> <@&1538390251414757396>"

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


# --- EVENTOS DE INICIO ---
@bot.event
async def on_ready():
    bot.add_view(TicketLaunchView())
    bot.add_view(TicketInteractiveView())

    await bot.change_presence(
        status=discord.Status.online,
        activity=discord.Game(name="Liga Haxball | /tabla")
    )

    try:
        synced = await bot.tree.sync()
        print(f"✅ {len(synced)} Comandos sincronizados correctamente.")
    except Exception as e:
        print(f"Error en la sincronización: {e}")

    print(f"🤖 Bot encendido como {bot.user}")


# --- EJECUCIÓN GENERAL ---
if __name__ == "__main__":
    keep_alive()
    TOKEN = os.environ.get("DISCORD_TOKEN")
    if TOKEN:
        bot.run(TOKEN)
    else:
        print("❌ Error: Asigna la variable de entorno 'DISCORD_TOKEN'.")
