import os
import json
import sqlite3
import datetime
import asyncio
import io
from threading import Thread
from flask import Flask

import discord
from discord import app_commands
from discord.ext import commands
from PIL import Image, ImageDraw, ImageFont

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
            elo INTEGER DEFAULT 1000,
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
            elo INTEGER DEFAULT 1000,
            valor_mercado INTEGER DEFAULT 10,
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
ID_CANAL_FICHAJES = 1538963728043741346
ID_CANAL_BAJAS = 1538964371722600498
ID_CANAL_RESULTADOS = 1538935950288093235
ID_ROL_RESULTADOS = 1539028557420957866

async def equipo_autocomplete(interaction: discord.Interaction, current: str):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT nombre FROM equipos WHERE nombre LIKE ? LIMIT 25", (f"%{current}%",))
    equipos = cursor.fetchall()
    conn.close()
    return [app_commands.Choice(name=eq[0], value=eq[0]) for eq in equipos]

async def temporada_autocomplete(interaction: discord.Interaction, current: str):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT nombre FROM temporadas WHERE nombre LIKE ? LIMIT 25", (f"%{current}%",))
    temps = cursor.fetchall()
    conn.close()
    return [app_commands.Choice(name=t[0], value=t[0]) for t in temps]

async def seguro_borrar_canal(channel):
    if channel:
        try:
            await channel.delete()
        except (discord.NotFound, discord.HTTPException):
            pass

def actualizar_valor_mercado(cursor, jugador_id):
    cursor.execute("SELECT goles, asistencias, mvps, partidos_jugados, elo FROM jugadores WHERE discord_id = ?", (jugador_id,))
    row = cursor.fetchone()
    if row:
        goles, asis, mvps, pj, elo = row
        nuevo_valor = 5 + (goles * 4) + (asis * 2) + (mvps * 6) + (max(0, (elo - 1000)) // 10)
        cursor.execute("UPDATE jugadores SET valor_mercado = ? WHERE discord_id = ?", (max(5, nuevo_valor), jugador_id))

def generar_tarjeta_fichaje(nombre_jugador, equipo_origen, equipo_destino, valor):
    img = Image.new("RGB", (800, 500), color=(15, 12, 25))
    draw = ImageDraw.Draw(img)
    
    draw.rectangle([20, 20, 780, 480], outline=(142, 68, 173), width=4)
    draw.rectangle([30, 30, 770, 470], outline=(40, 30, 60), width=2)
    draw.rectangle([30, 30, 770, 100], fill=(25, 18, 42))
    
    try:
        font_titulo = ImageFont.truetype("arial.ttf", 34)
        font_sub = ImageFont.truetype("arial.ttf", 22)
        font_grande = ImageFont.truetype("arial.ttf", 40)
    except IOError:
        font_titulo = font_sub = font_grande = ImageFont.load_default()

    draw.text((45, 45), "⚡ FICHAJE OFICIAL - VANTA LEAGUE ⚡", fill=(220, 198, 255), font=font_titulo)
    draw.text((50, 135), f"De: {equipo_origen}", fill=(180, 180, 180), font=font_sub)
    draw.text((50, 175), f"A: {equipo_destino}", fill=(170, 100, 255), font=font_sub)
    
    draw.ellipse([320, 210, 480, 370], fill=(45, 25, 75), outline=(170, 100, 255), width=3)
    draw.text((370, 260), "⚽", font=font_grande)

    draw.text((50, 390), f"JUGADOR: {nombre_jugador.upper()}", fill=(255, 255, 255), font=font_titulo)
    draw.text((50, 435), f"VALOR EN MERCADO: €{valor}M", fill=(170, 100, 255), font=font_sub)

    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer


# ==========================================
# --- 4. MODALES Y VISTAS DE TICKETS -------
# ==========================================
class AlianzaModal(discord.ui.Modal, title="📝 Formulario de Alianza"):
    nombre_comunidad = discord.ui.TextInput(label="Nombre de tu Comunidad/Liga", placeholder="Ej. Liga Sombra Haxball", required=True)
    miembros = discord.ui.TextInput(label="Cantidad aproximada de miembros", placeholder="Ej. 250 miembros", required=True)
    invitacion = discord.ui.TextInput(label="Link de Invitación a tu Discord", placeholder="https://discord.gg/ejemplo", required=True)
    propuesta = discord.ui.TextInput(label="Detalles / Tipo de Alianza", style=discord.TextStyle.paragraph, placeholder="Ej. Ping x Ping...", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.send_message(f"✅ Propuesta procesada correctamente.", ephemeral=True)
        canal_partners = interaction.guild.get_channel(ID_CANAL_PARTNERS)
        if canal_partners:
            embed = discord.Embed(title=f"🤝 ¡NUEVA ALIANZA! - {self.nombre_comunidad.value}", description=f"👥 **Miembros:** {self.miembros.value}\n🔗 **Servidor:** {self.invitacion.value}\n\n📜 **Propuesta:**\n{self.propuesta.value}\n\n👤 **Representante:** {interaction.user.mention}", color=discord.Color.purple())
            await canal_partners.send(content=f"<@&{ID_ROL_PARTNER}>", embed=embed)

class AlianzaTicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
    @discord.ui.button(label="📝 Rellenar Plantilla", style=discord.ButtonStyle.success, custom_id="btn_modal_alianza")
    async def abrir_modal(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AlianzaModal())
    @discord.ui.button(label="🔒 Cerrar Ticket", style=discord.ButtonStyle.danger, custom_id="btn_cerrar_alianza")
    async def cerrar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("🔒 Cerrando...", ephemeral=True)
        await asyncio.sleep(3)
        await seguro_borrar_canal(interaction.channel)

class TicketSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Alianzas", description="Abrir ticket para alianzas", emoji="🤝", value="alianza"),
            discord.SelectOption(label="Reportes", description="Reportar un problema", emoji="❗", value="reporte"),
            discord.SelectOption(label="Postulaciones", description="Postularte al staff", emoji="🧑‍💼", value="postulacion"),
            discord.SelectOption(label="Otro", description="Soporte general", emoji="❓", value="otro"),
        ]
        super().__init__(placeholder="Selecciona una categoría...", options=options, custom_id="ticket_main_select")

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        tipo = self.values[0]
        guild = interaction.guild
        user = interaction.user
        channel_name = f"ticket-{tipo}-{user.name.lower()}"

        existing = discord.utils.get(guild.channels, name=channel_name)
        if existing:
            await interaction.followup.send(f"❌ Ya tienes un ticket abierto: {existing.mention}", ephemeral=True)
            return

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            user: discord.PermissionOverwrite(view_channel=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True)
        }
        category = interaction.channel.category or discord.utils.get(guild.categories, name="📁 TICKETS") or await guild.create_category("📁 TICKETS")
        ticket_channel = await guild.create_text_channel(name=channel_name, category=category, overwrites=overwrites)

        if tipo == "alianza":
            await ticket_channel.send(content=f"👋 ¡Hola {user.mention}!", view=AlianzaTicketView())
        else:
            await ticket_channel.send(content=f"👋 ¡Hola {user.mention}! Un miembro del staff te atenderá pronto.")
        
        await interaction.followup.send(f"✅ Ticket creado: {ticket_channel.mention}", ephemeral=True)

class MainTicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(TicketSelect())


# ==========================================
# --- 5. TRASPASOS CON DOBLE FIRMA ----------
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

    def generar_embed(self):
        f_orig = "✅ Firmado" if self.firma_origen else "⏳ Pendiente"
        f_dest = "✅ Firmado" if self.firma_destino else "⏳ Pendiente"
        embed = discord.Embed(title="📝 Solicitud de Traspaso", color=discord.Color.purple())
        embed.add_field(name="Origen", value=self.eq_origen_nombre or "Agente Libre", inline=True)
        embed.add_field(name="Destino", value=self.eq_destino_nombre, inline=True)
        embed.add_field(name="Firma Origen", value=f_orig, inline=True)
        embed.add_field(name="Firma Destino", value=f_dest, inline=True)
        return embed

    @discord.ui.button(label="✍️ Firmar (Origen)", style=discord.ButtonStyle.secondary, custom_id="f_orig")
    async def firmar_origen(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        if interaction.user.id != self.dt_origen_id:
            await interaction.followup.send("❌ Solo el DT de origen puede firmar.", ephemeral=True)
            return
        self.firma_origen = True
        button.disabled = True
        await interaction.message.edit(embed=self.generar_embed(), view=self)
        await self.comprobar_completado(interaction)

    @discord.ui.button(label="✍️ Firmar (Destino)", style=discord.ButtonStyle.primary, custom_id="f_dest")
    async def firmar_destino(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        if interaction.user.id != self.dt_destino_id:
            await interaction.followup.send("❌ Solo el DT de destino puede firmar.", ephemeral=True)
            return
        self.firma_destino = True
        button.disabled = True
        await interaction.message.edit(embed=self.generar_embed(), view=self)
        await self.comprobar_completado(interaction)

    async def comprobar_completado(self, interaction: discord.Interaction):
        if self.firma_origen and self.firma_destino:
            guild = interaction.guild

            conn = sqlite3.connect(DB_NAME)
            cursor = conn.cursor()
            actualizar_valor_mercado(cursor, self.jugador.id)
            cursor.execute("SELECT valor_mercado FROM jugadores WHERE discord_id = ?", (self.jugador.id,))
            row = cursor.fetchone()
            valor = row[0] if row else 10

            if self.rol_origen_id:
                r_old = guild.get_role(self.rol_origen_id)
                if r_old and r_old in self.jugador.roles:
                    await self.jugador.remove_roles(r_old)
            if self.rol_destino_id:
                r_new = guild.get_role(self.rol_destino_id)
                if r_new:
                    await self.jugador.add_roles(r_new)

            cursor.execute("INSERT INTO jugadores (discord_id, equipo_id) VALUES (?, ?) ON CONFLICT(discord_id) DO UPDATE SET equipo_id = ?", (self.jugador.id, self.eq_destino_id, self.eq_destino_id))
            cursor.execute("INSERT INTO historial_traspasos (jugador_id, origen_id, destino_id) VALUES (?, ?, ?)", (self.jugador.id, self.eq_origen_id, self.eq_destino_id))
            conn.commit()
            conn.close()

            img_buffer = generar_tarjeta_fichaje(self.jugador.display_name, self.eq_origen_nombre or "Agente Libre", self.eq_destino_nombre, valor)
            file = discord.File(img_buffer, filename="fichaje.png")

            canal_fichajes = guild.get_channel(ID_CANAL_FICHAJES)
            if canal_fichajes:
                await canal_fichajes.send(content=f"🚨 **¡NUEVO FICHAJE OFICIAL!** {self.jugador.mention}", file=file)

            if self.eq_origen_nombre:
                canal_bajas = guild.get_channel(ID_CANAL_BAJAS)
                if canal_bajas:
                    await canal_bajas.send(content=f"⚠️ **BAJA CONFIRMADA:** {self.jugador.mention} deja las filas de **{self.eq_origen_nombre}** rumbo a **{self.eq_destino_nombre}**.")

            for child in self.children:
                child.disabled = True
            await interaction.message.edit(content="✅ **¡Traspaso Oficializado con Éxito!**", embed=self.generar_embed(), view=self)


# ==========================================
# --- 6. MÓDULOS: MUSEO, TEMPORADAS Y LIGA ---
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
        eq_nombre = eq_row[0] if eq_row else "Equipo"
        cursor.execute("SELECT tipo, nombre, temporada, detalles FROM museo_titulos WHERE equipo_id = ?", (equipo_id,))
        items = cursor.fetchall()
        conn.close()

        if not items:
            await interaction.response.send_message(f"🏛️ La vitrina de **{eq_nombre}** está vacía.", ephemeral=True)
            return

        embed = discord.Embed(title=f"🏛️ Vitrina de {eq_nombre}", color=discord.Color.purple())
        for it in items:
            embed.add_field(name=f"🏆 {it[1]}", value=f"Temporada: {it[2] or 'N/A'}\n{it[3] or ''}", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

class MuseoGroup(app_commands.Group):
    def __init__(self):
        super().__init__(name="museo", description="Gestión del museo")

    @app_commands.command(name="add_titulo", description="Añade un título a la vitrina")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.autocomplete(equipo=equipo_autocomplete)
    async def add_titulo(self, interaction: discord.Interaction, equipo: str, titulo: str, temporada: str = None, detalles: str = None):
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM equipos WHERE nombre = ?", (equipo,))
        eq = cursor.fetchone()
        if not eq:
            await interaction.response.send_message(f"❌ Equipo no encontrado.", ephemeral=True)
            conn.close()
            return
        cursor.execute("INSERT INTO museo_titulos (equipo_id, tipo, nombre, temporada, detalles) VALUES (?, 'titulo', ?, ?, ?)", (eq[0], titulo, temporada, detalles))
        conn.commit()
        conn.close()
        await interaction.response.send_message(f"🏆 Título añadido a **{equipo}**.")

    @app_commands.command(name="ver", description="Muestra la vitrina de un equipo")
    async def ver(self, interaction: discord.Interaction):
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT id, nombre FROM equipos")
        equipos = cursor.fetchall()
        conn.close()
        if not equipos:
            await interaction.response.send_message("No hay equipos.", ephemeral=True)
            return
        view = discord.ui.View()
        view.add_item(MuseoSelect(equipos))
        await interaction.response.send_message("🏛️ Elige un equipo:", view=view, ephemeral=True)

bot.tree.add_command(MuseoGroup())

class SeasonGroup(app_commands.Group):
    def __init__(self):
        super().__init__(name="season", description="Gestión completa de temporadas")

    @app_commands.command(name="create", description="Crea una temporada en fase de inscripción")
    @app_commands.checks.has_permissions(administrator=True)
    async def season_create(self, interaction: discord.Interaction, nombre: str):
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        try:
            cursor.execute("INSERT INTO temporadas (nombre, estado) VALUES (?, 'inscripcion')", (nombre,))
            conn.commit()
            await interaction.response.send_message(f"🏆 Temporada **{nombre}** creada con éxito (Estado: Inscripción).")
        except sqlite3.IntegrityError:
            await interaction.response.send_message(f"❌ Ya existe una temporada con ese nombre.", ephemeral=True)
        finally:
            conn.close()

    @app_commands.command(name="start", description="Inicia una temporada existente (cambia estado a activa)")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.autocomplete(nombre=temporada_autocomplete)
    async def season_start(self, interaction: discord.Interaction, nombre: str):
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM temporadas WHERE nombre = ?", (nombre,))
        temp = cursor.fetchone()
        if not temp:
            await interaction.response.send_message(f"❌ La temporada no existe.", ephemeral=True)
            conn.close()
            return
        cursor.execute("UPDATE temporadas SET estado = 'activa' WHERE id = ?", (temp[0],))
        conn.commit()
        conn.close()
        await interaction.response.send_message(f"🚀 ¡La temporada **{nombre}** ha dado inicio oficialmente!")

    @app_commands.command(name="delete", description="Elimina una temporada existente")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.autocomplete(nombre=temporada_autocomplete)
    async def season_delete(self, interaction: discord.Interaction, nombre: str):
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM temporadas WHERE nombre = ?", (nombre,))
        temp = cursor.fetchone()
        if not temp:
            await interaction.response.send_message(f"❌ La temporada no existe.", ephemeral=True)
            conn.close()
            return
        cursor.execute("DELETE FROM temporadas WHERE id = ?", (temp[0],))
        conn.commit()
        conn.close()
        await interaction.response.send_message(f"🗑️ Temporada **{nombre}** eliminada correctamente.")

bot.tree.add_command(SeasonGroup())

class LigaGroup(app_commands.Group):
    def __init__(self):
        super().__init__(name="liga", description="Comandos operativos de la liga y partidos")

    @app_commands.command(name="registrar_partido", description="Registra partido, ELO, stats, replay y publica en resultados")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.autocomplete(local=equipo_autocomplete, visitante=equipo_autocomplete)
    async def registrar_partido(self, interaction: discord.Interaction, temporada: str, jornada: int, local: str, visitante: str, goles_local: int, goles_visitante: int, replay_url: str = None):
        await interaction.response.defer(ephemeral=False)
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()

        cursor.execute("SELECT id FROM temporadas WHERE nombre = ?", (temporada,))
        temp = cursor.fetchone()
        if not temp:
            await interaction.followup.send(f"❌ Temporada no encontrada.", ephemeral=True)
            conn.close()
            return
        temp_id = temp[0]

        cursor.execute("SELECT id, elo FROM equipos WHERE nombre = ?", (local,))
        eq_l = cursor.fetchone()
        cursor.execute("SELECT id, elo FROM equipos WHERE nombre = ?", (visitante,))
        eq_v = cursor.fetchone()

        if not eq_l or not eq_v:
            await interaction.followup.send("❌ Equipos no encontrados en la base de datos.", ephemeral=True)
            conn.close()
            return

        # Cálculo ELO
        k = 32
        elo_l, elo_v = eq_l[1], eq_v[1]
        score_l = 1.0 if goles_local > goles_visitante else (0.5 if goles_local == goles_visitante else 0.0)
        exp_l = 1 / (1 + 10 ** ((elo_v - elo_l) / 400))
        new_elo_l = int(elo_l + k * (score_l - exp_l))
        new_elo_v = int(elo_v + k * ((1 - score_l) - (1 - exp_l)))

        cursor.execute("UPDATE equipos SET elo = ? WHERE id = ?", (new_elo_l, eq_l[0]))
        cursor.execute("UPDATE equipos SET elo = ? WHERE id = ?", (new_elo_v, eq_v[0]))
        cursor.execute("INSERT INTO partidos (temporada_id, jornada, equipo_local_id, equipo_visitante_id, goles_local, goles_visitante, jugado, replay_url) VALUES (?, ?, ?, ?, ?, ?, 1, ?)", (temp_id, jornada, eq_l[0], eq_v[0], goles_local, goles_visitante, replay_url))
        
        conn.commit()
        conn.close()

        # Respuesta de confirmación en el chat actual
        await interaction.followup.send(f"✅ Partido registrado correctamente para la jornada {jornada} de **{temporada}**.")

        # Envío del resultado formateado al canal de resultados específico
        guild = interaction.guild
        canal_resultados = guild.get_channel(ID_CANAL_RESULTADOS)
        if canal_resultados:
            embed = discord.Embed(
                title=f"⚽ RESULTADO OFICIAL - JORNADA {jornada}",
                description=f"🏆 **Temporada:** {temporada}\n\n**{local}** `{goles_local} - {goles_visitante}` **{visitante}**",
                color=discord.Color.purple()
            )
            embed.add_field(name="📊 Actualización de ELO", value=f"• **{local}:** `{elo_l}` ➔ `{new_elo_l}`\n• **{visitante}:** `{elo_v}` ➔ `{new_elo_v}`", inline=False)
            if replay_url:
                embed.add_field(name="🎬 Enlace de Replay", value=f"[Ver Replay]({replay_url})", inline=False)
            
            await canal_resultados.send(content=f"<@&{ID_ROL_RESULTADOS}>", embed=embed)

    @app_commands.command(name="stats", description="Muestra estadísticas, ELO y valor de mercado de un jugador")
    async def stats(self, interaction: discord.Interaction, miembro: discord.Member):
        await interaction.response.defer(ephemeral=True)
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        actualizar_valor_mercado(cursor, miembro.id)
        conn.commit()
        
        cursor.execute("SELECT equipo_id, goles, asistencias, mvps, partidos_jugados, elo, valor_mercado FROM jugadores WHERE discord_id = ?", (miembro.id,))
        row = cursor.fetchone()
        conn.close()

        if not row:
            await interaction.followup.send(f"📊 {miembro.mention} no registra datos aún.", ephemeral=True)
            return

        embed = discord.Embed(title=f"📊 Estadísticas de {miembro.display_name}", color=discord.Color.purple())
        embed.add_field(name="Goles", value=str(row[1]), inline=True)
        embed.add_field(name="Asistencias", value=str(row[2]), inline=True)
        embed.add_field(name="MVPs", value=str(row[3]), inline=True)
        embed.add_field(name="Partidos Jugados", value=str(row[4]), inline=True)
        embed.add_field(name="ELO Personal", value=str(row[5]), inline=True)
        embed.add_field(name="💰 Valor de Mercado", value=f"€{row[6]}M", inline=True)

        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="sancion", description="Aplica una sanción a un jugador")
    @app_commands.checks.has_permissions(administrator=True)
    async def sancion(self, interaction: discord.Interaction, miembro: discord.Member, tipo: str, partidos: int, motivo: str):
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO jugadores (discord_id) VALUES (?) ON CONFLICT(discord_id) DO NOTHING", (miembro.id,))
        cursor.execute("INSERT INTO sanciones (jugador_id, tipo, partidos_suspension, motivo, activa) VALUES (?, ?, ?, ?, 1)", (miembro.id, tipo, partidos, motivo))
        conn.commit()
        conn.close()
        await interaction.response.send_message(f"⚖️ Sanción aplicada a {miembro.mention}: **{tipo}** ({partidos} partidos). Motivo: {motivo}")

bot.tree.add_command(LigaGroup())


# ==========================================
# --- 7. EVENTOS Y SETUP DEL BOT -----------
# ==========================================
@bot.tree.command(name="setup_tickets", description="Despliega el panel de tickets")
@app_commands.default_permissions(administrator=True)
async def setup_tickets(interaction: discord.Interaction):
    await interaction.response.send_message("✅ Panel desplegado.", ephemeral=True)
    embed = discord.Embed(
        title="🎫 Centro de Atención y Tickets",
        description=(
            "📢 **HORARIO DE ATENCIÓN DE TICKETS**\n\n"
            "🇨🇴 **Colombia:** 2:00 PM - 9:00 PM\n"
            "🇻🇪 **Venezuela:** 3:00 PM - 10:00 PM\n"
            "🇨🇱 **Chile:** 4:00 PM - 11:00 PM\n"
            "🇦🇷 **Argentina:** 4:00 PM - 11:00 PM\n"
            "🇺🇾 **Uruguay:** 4:00 PM - 11:00 PM\n\n"
            "⚠️ Los tickets abiertos fuera de este horario podrán ser atendidos al día siguiente, dependiendo de la disponibilidad del Staff."
        ),
        color=discord.Color.purple()
    )
    await interaction.channel.send(embed=embed, view=MainTicketView())

@bot.event
async def on_ready():
    print(f"🤖 Bot conectado como: {bot.user.name}")
    bot.add_view(MainTicketView())
    bot.add_view(AlianzaTicketView())
    try:
        synced = await bot.tree.sync()
        print(f"🔄 Sincronizados {len(synced)} comandos.")
    except Exception as e:
        print(f"❌ Error: {e}")

keep_alive()
TOKEN = os.environ.get("DISCORD_TOKEN")
if TOKEN:
    bot.run(TOKEN)
