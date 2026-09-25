import os
import json
import sqlite3
import datetime
import asyncio
import io
import urllib.request
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
            sub_dt_id INTEGER,
            FOREIGN KEY (temporada_id) REFERENCES temporadas(id)
        )
    ''')
    
    # Migraciones para bases de datos ya existentes
    for columna, tipo in [("sub_dt_id", "INTEGER"), ("escudo_url", "TEXT")]:
        try:
            cursor.execute(f"ALTER TABLE equipos ADD COLUMN {columna} {tipo}")
        except sqlite3.OperationalError:
            pass  # la columna ya existe

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
ID_ROL_PARTNER = 1538933503641780265
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

def descargar_escudo(url, size=(110, 110)):
    if not url:
        return None
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=6) as resp:
            data = resp.read()
        escudo = Image.open(io.BytesIO(data)).convert("RGBA").resize(size)

        mascara = Image.new("L", size, 0)
        ImageDraw.Draw(mascara).ellipse([0, 0, size[0], size[1]], fill=255)
        circular = Image.new("RGBA", size, (0, 0, 0, 0))
        circular.paste(escudo, (0, 0), mascara)
        return circular
    except Exception:
        return None

def generar_tarjeta_fichaje(nombre_jugador, equipo_origen, equipo_destino, valor, escudo_origen_url=None, escudo_destino_url=None):
    img = Image.new("RGB", (800, 500), color=(15, 12, 25))
    draw = ImageDraw.Draw(img)

    draw.rectangle([20, 20, 780, 480], outline=(142, 68, 173), width=4)
    draw.rectangle([30, 30, 770, 470], outline=(40, 30, 60), width=2)
    draw.rectangle([30, 30, 770, 100], fill=(25, 18, 42))

    try:
        font_titulo = ImageFont.truetype("arial.ttf", 34)
        font_sub = ImageFont.truetype("arial.ttf", 22)
        font_chico = ImageFont.truetype("arial.ttf", 18)
    except IOError:
        font_titulo = font_sub = font_chico = ImageFont.load_default()

    draw.text((45, 45), "⚡ FICHAJE OFICIAL - VANTA LEAGUE ⚡", fill=(220, 198, 255), font=font_titulo)

    escudo_o = descargar_escudo(escudo_origen_url)
    cx_o, cy_o = 110, 250
    if escudo_o:
        img.paste(escudo_o, (cx_o - 55, cy_o - 55), escudo_o)
    else:
        draw.ellipse([cx_o - 55, cy_o - 55, cx_o + 55, cy_o + 55], fill=(45, 25, 75), outline=(150, 80, 200), width=3)
    draw.text((cx_o - 45, cy_o + 65), "🔴 VENDE", fill=(230, 100, 100), font=font_chico)
    draw.text((cx_o - 90, cy_o + 95), equipo_origen[:18], fill=(200, 200, 200), font=font_chico)

    escudo_d = descargar_escudo(escudo_destino_url)
    cx_d, cy_d = 690, 250
    if escudo_d:
        img.paste(escudo_d, (cx_d - 55, cy_d - 55), escudo_d)
    else:
        draw.ellipse([cx_d - 55, cy_d - 55, cx_d + 55, cy_d + 55], fill=(45, 25, 75), outline=(150, 80, 200), width=3)
    draw.text((cx_d - 55, cy_d + 65), "🟢 COMPRA", fill=(120, 220, 120), font=font_chico)
    draw.text((cx_d - 90, cy_d + 95), equipo_destino[:18], fill=(220, 198, 255), font=font_chico)

    draw.ellipse([365, 210, 435, 280], fill=(45, 25, 75), outline=(170, 100, 255), width=3)
    draw.text((383, 228), "⚽", font=font_sub)

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
        await interaction.response.send_message("✅ Propuesta procesada correctamente.", ephemeral=True)
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
    def __init__(self, jugador, eq_origen_nombre, eq_destino_nombre, dt_origen_id, dt_destino_id, eq_origen_id, eq_destino_id, rol_origen_id, rol_destino_id, escudo_origen_url=None, escudo_destino_url=None):
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
        self.escudo_origen_url = escudo_origen_url
        self.escudo_destino_url = escudo_destino_url

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
        if self.escudo_destino_url:
            embed.set_thumbnail(url=self.escudo_destino_url)
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
            cursor.execute("INSERT INTO jugadores (discord_id, equipo_id) VALUES (?, ?) ON CONFLICT(discord_id) DO UPDATE SET equipo_id = ?", (self.jugador.id, self.eq_destino_id, self.eq_destino_id))
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

            cursor.execute("INSERT INTO historial_traspasos (jugador_id, origen_id, destino_id) VALUES (?, ?, ?)", (self.jugador.id, self.eq_origen_id, self.eq_destino_id))
            conn.commit()
            conn.close()

            img_buffer = await interaction.client.loop.run_in_executor(
                None,
                generar_tarjeta_fichaje,
                self.jugador.display_name,
                self.eq_origen_nombre or "Agente Libre",
                self.eq_destino_nombre,
                valor,
                self.escudo_origen_url,
                self.escudo_destino_url,
            )
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
# --- 6. MÓDULOS: EQUIPOS, TRASPASOS -------
# ==========================================
class EquipoGroup(app_commands.Group):
    def __init__(self):
        super().__init__(name="equipo", description="Gestión de equipos de la liga")

    @app_commands.command(name="crear", description="Registra un nuevo equipo en la temporada activa")
    @app_commands.checks.has_permissions(administrator=True)
    async def crear(self, interaction: discord.Interaction, nombre: str, dt: discord.Member, rol: discord.Role, escudo: discord.Attachment = None):
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM temporadas WHERE estado = 'activa' ORDER BY id DESC LIMIT 1")
        temp = cursor.fetchone()
        temp_id = temp[0] if temp else None
        escudo_url = escudo.url if escudo else None
        try:
            cursor.execute("INSERT INTO equipos (nombre, dt_id, rol_id, temporada_id, escudo_url) VALUES (?, ?, ?, ?, ?)", (nombre, dt.id, rol.id, temp_id, escudo_url))
            conn.commit()
            await interaction.response.send_message(f"✅ Equipo **{nombre}** creado con DT {dt.mention}.")
        except sqlite3.IntegrityError:
            await interaction.response.send_message("❌ Ya existe un equipo con ese nombre.", ephemeral=True)
        finally:
            conn.close()

    @app_commands.command(name="escudo", description="Sube o cambia el escudo de tu equipo")
    @app_commands.autocomplete(equipo=equipo_autocomplete)
    async def escudo_cmd(self, interaction: discord.Interaction, equipo: str, imagen: discord.Attachment):
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT id, dt_id FROM equipos WHERE nombre = ?", (equipo,))
        eq = cursor.fetchone()
        if not eq:
            await interaction.response.send_message("❌ Equipo no encontrado.", ephemeral=True)
            conn.close()
            return
        eq_id, dt_id = eq

        es_admin = interaction.user.guild_permissions.administrator
        if not (es_admin or interaction.user.id == dt_id):
            await interaction.response.send_message("❌ Solo el DT titular de ese equipo puede cambiar el escudo.", ephemeral=True)
            conn.close()
            return

        cursor.execute("UPDATE equipos SET escudo_url = ? WHERE id = ?", (imagen.url, eq_id))
        conn.commit()
        conn.close()

        embed = discord.Embed(title=f"🛡️ Escudo actualizado — {equipo}", color=discord.Color.purple())
        embed.set_thumbnail(url=imagen.url)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="listar", description="Lista los equipos registrados")
    async def listar(self, interaction: discord.Interaction):
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT nombre, elo, escudo_url FROM equipos ORDER BY elo DESC")
        equipos = cursor.fetchall()
        conn.close()
        if not equipos:
            await interaction.response.send_message("No hay equipos registrados aún.", ephemeral=True)
            return
        desc = "\n".join([f"**{i+1}.** {eq[0]} — ELO `{eq[1]}`" for i, eq in enumerate(equipos)])
        embed = discord.Embed(title="📋 Equipos Registrados", description=desc, color=discord.Color.purple())
        if equipos[0][2]:
            embed.set_thumbnail(url=equipos[0][2])
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="sub_dt", description="Asigna o cambia el sub DT de tu equipo")
    @app_commands.autocomplete(equipo=equipo_autocomplete)
    async def sub_dt(self, interaction: discord.Interaction, equipo: str, sub_dt: discord.Member):
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT id, dt_id FROM equipos WHERE nombre = ?", (equipo,))
        eq = cursor.fetchone()
        if not eq:
            await interaction.response.send_message("❌ Equipo no encontrado.", ephemeral=True)
            conn.close()
            return
        eq_id, dt_id = eq

        es_admin = interaction.user.guild_permissions.administrator
        if not (es_admin or interaction.user.id == dt_id):
            await interaction.response.send_message("❌ Solo el DT titular de ese equipo puede asignar un sub DT.", ephemeral=True)
            conn.close()
            return

        cursor.execute("UPDATE equipos SET sub_dt_id = ? WHERE id = ?", (sub_dt.id, eq_id))
        conn.commit()
        conn.close()
        await interaction.response.send_message(f"✅ {sub_dt.mention} ahora es sub DT de **{equipo}** y puede inscribir jugadores en la plantilla.")

bot.tree.add_command(EquipoGroup())

class TraspasoGroup(app_commands.Group):
    def __init__(self):
        super().__init__(name="traspaso", description="Gestión del mercado de fichajes")

    @app_commands.command(name="iniciar", description="Inicia un traspaso con panel de doble firma")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.autocomplete(equipo_destino=equipo_autocomplete)
    async def iniciar(self, interaction: discord.Interaction, jugador: discord.Member, equipo_destino: str):
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()

        cursor.execute("SELECT id, nombre, dt_id, rol_id, escudo_url FROM equipos WHERE nombre = ?", (equipo_destino,))
        eq_dest = cursor.fetchone()
        if not eq_dest:
            await interaction.response.send_message("❌ Equipo destino no encontrado.", ephemeral=True)
            conn.close()
            return
        eq_destino_id, eq_destino_nombre, dt_destino_id, rol_destino_id, escudo_destino_url = eq_dest

        cursor.execute("SELECT equipo_id FROM jugadores WHERE discord_id = ?", (jugador.id,))
        row = cursor.fetchone()
        eq_origen_id = row[0] if row else None

        eq_origen_nombre, dt_origen_id, rol_origen_id, escudo_origen_url = None, None, None, None
        if eq_origen_id:
            cursor.execute("SELECT nombre, dt_id, rol_id, escudo_url FROM equipos WHERE id = ?", (eq_origen_id,))
            eq_o = cursor.fetchone()
            if eq_o:
                eq_origen_nombre, dt_origen_id, rol_origen_id, escudo_origen_url = eq_o

        conn.close()

        if eq_origen_id == eq_destino_id:
            await interaction.response.send_message("❌ El jugador ya pertenece a ese equipo.", ephemeral=True)
            return

        view = TraspasoFirmasView(jugador, eq_origen_nombre, eq_destino_nombre, dt_origen_id, dt_destino_id, eq_origen_id, eq_destino_id, rol_origen_id, rol_destino_id, escudo_origen_url, escudo_destino_url)
        await interaction.response.send_message(embed=view.generar_embed(), view=view)

bot.tree.add_command(TraspasoGroup())


# ==========================================
# --- 7. MÓDULOS: MUSEO, TEMPORADAS Y LIGA ---
# ==========================================
class MuseoSelect(discord.ui.Select):
    def __init__(self, equipos):
        options = [discord.SelectOption(label=eq[1], value=str(eq[0]), emoji="🏛️") for eq in equipos]
        super().__init__(placeholder="Selecciona un equipo...", options=options)

    async def callback(self, interaction: discord.Interaction):
        equipo_id = int(self.values[0])
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT nombre, escudo_url FROM equipos WHERE id = ?", (equipo_id,))
        eq_row = cursor.fetchone()
        eq_nombre = eq_row[0] if eq_row else "Equipo"
        escudo_url = eq_row[1] if eq_row else None
        cursor.execute("SELECT tipo, nombre, temporada, detalles FROM museo_titulos WHERE equipo_id = ?", (equipo_id,))
        items = cursor.fetchall()
        conn.close()

        if not items:
            await interaction.response.send_message(f"🏛️ La vitrina de **{eq_nombre}** está vacía.", ephemeral=True)
            return

        embed = discord.Embed(title=f"🏛️ Vitrina de {eq_nombre}", color=discord.Color.purple())
        if escudo_url:
            embed.set_thumbnail(url=escudo_url)
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
            await interaction.response.send_message("❌ Equipo no encontrado.", ephemeral=True)
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
            await interaction.response.send_message("❌ Ya existe una temporada con ese nombre.", ephemeral=True)
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
            await interaction.response.send_message("❌ La temporada no existe.", ephemeral=True)
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
            await interaction.response.send_message("❌ La temporada no existe.", ephemeral=True)
            conn.close()
            return
        cursor.execute("DELETE FROM temporadas WHERE id = ?", (temp[0],))
        conn.commit()
        conn.close()
        await interaction.response.send_message(f"🗑️ Temporada **{nombre}** eliminada correctamente.")

bot.tree.add_command(SeasonGroup())

# ==========================================
# --- 8. INICIO DEL BOT --------------------
# ==========================================
@bot.event
async def on_ready():
    keep_alive()
    try:
        synced = await bot.tree.sync()
        print(f"🤖 Bot conectado como {bot.user} (Sincronizados {len(synced)} comandos)")
    except Exception as e:
        print(f"Error sincronizando comandos: {e}")

if __name__ == "__main__":
    TOKEN = os.environ.get("DISCORD_TOKEN")
    if TOKEN:
        bot.run(TOKEN)
    else:
        print("❌ Error: No se encontró la variable de entorno DISCORD_TOKEN.")
