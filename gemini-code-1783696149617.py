import os
import json
import sqlite3
import datetime
import asyncio
import subprocess
import shutil
from threading import Thread
from flask import Flask

import discord
from discord.ext import commands
from discord import app_commands

# --- CONFIGURACIÓN E INICIALIZACIÓN DE LA BASE DE DATOS ---
DB_NAME = "liga_haxball.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # Tabla de Temporadas
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS temporadas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL UNIQUE,
            estado TEXT NOT NULL DEFAULT 'inscripcion',
            fecha_inicio TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Tabla de Equipos
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
    
    # Tabla de Jugadores
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS jugadores (
            discord_id INTEGER PRIMARY KEY,
            equipo_id INTEGER,
            goles INTEGER DEFAULT 0,
            asistencias INTEGER DEFAULT 0,
            FOREIGN KEY (equipo_id) REFERENCES equipos(id)
        )
    ''')
    
    # Tabla de Partidos
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS partidos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            temporada_id INTEGER NOT NULL,
            equipo_local_id INTEGER NOT NULL,
            equipo_visitante_id INTEGER NOT NULL,
            goles_local INTEGER DEFAULT 0,
            goles_visitante INTEGER DEFAULT 0,
            jugado INTEGER DEFAULT 0,
            FOREIGN KEY (temporada_id) REFERENCES temporadas(id),
            FOREIGN KEY (equipo_local_id) REFERENCES equipos(id),
            FOREIGN KEY (equipo_visitante_id) REFERENCES equipos(id)
        )
    ''')
    
    # Tabla de Goles por Partido
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS goles_partido (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            partido_id INTEGER NOT NULL,
            jugador_id INTEGER NOT NULL,
            cantidad INTEGER DEFAULT 1,
            FOREIGN KEY (partido_id) REFERENCES partidos(id),
            FOREIGN KEY (jugador_id) REFERENCES jugadores(discord_id)
        )
    ''')
    
    # Tabla de Sanciones
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sanciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            jugador_id INTEGER NOT NULL,
            tipo TEXT NOT NULL,
            partidos_suspension INTEGER DEFAULT 0,
            motivo TEXT,
            FOREIGN KEY (jugador_id) REFERENCES jugadores(discord_id)
        )
    ''')

    # Tabla de Historial de Traspasos (NUEVO)
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

    # Tabla del Museo de Títulos y Reconocimientos (NUEVO)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS museo_titulos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            equipo_id INTEGER NOT NULL,
            tipo TEXT NOT NULL, -- 'titulo' o 'reconocimiento'
            nombre TEXT NOT NULL,
            temporada TEXT,
            detalles TEXT,
            FOREIGN KEY (equipo_id) REFERENCES equipos(id)
        )
    ''')
    
    conn.commit()
    conn.close()


# --- SERVIDOR WEB PARA RENDER (KEEP ALIVE) ---
app = Flask('')

@app.route('/')
def home():
    return "Bot de Discord activo 24/7"

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


# --- VISTAS PERSISTENTES DE TICKETS ---
class TicketCloseView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🔒 Cerrar Ticket", style=discord.ButtonStyle.danger, custom_id="close_ticket_btn")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("🔒 Este ticket se cerrará y eliminará en 5 segundos...", ephemeral=False)
        await asyncio.sleep(5)
        await interaction.channel.delete()


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
            custom_id="ticket_select_menu"
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        categoria = self.values[0]
        guild = interaction.guild
        user = interaction.user

        channel_name = f"ticket-{categoria}-{user.name.lower()}"
        existing_channel = discord.utils.get(guild.channels, name=channel_name)
        if existing_channel:
            await interaction.followup.send(f"❌ Ya tienes un ticket abierto de este tipo en {existing_channel.mention}", ephemeral=True)
            return

        ID_ADMINISTRADOR = 1538389985336762448
        rol_admin = guild.get_role(ID_ADMINISTRADOR)

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            user: discord.PermissionOverwrite(read_messages=True, send_messages=True, attach_files=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True)
        }

        if rol_admin:
            overwrites[rol_admin] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

        category = interaction.channel.category
        ticket_channel = await guild.create_text_channel(
            name=channel_name,
            category=category,
            overwrites=overwrites
        )

        embed = discord.Embed(
            title=f"🎫 Ticket de {categoria.capitalize()} - {user.name}",
            description="Un miembro del Staff te atenderá pronto. Explica tu consulta o motivo aquí abajo.",
            color=discord.Color.blue()
        )

        await ticket_channel.send(content=f"{user.mention}", embed=embed, view=TicketCloseView())
        await interaction.followup.send(f"✅ Ticket creado correctamente: {ticket_channel.mention}", ephemeral=True)


class TicketLaunchView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(TicketSelect())


# --- VISTAS INTERACTIVAS (FIXTURE & PREMIOS) ---
class FixtureSelect(discord.ui.Select):
    def __init__(self, equipos):
        options = [discord.SelectOption(label=eq[1], value=str(eq[0])) for eq in equipos]
        super().__init__(placeholder="Elige un equipo para ver sus partidos...", options=options)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        equipo_id = int(self.values[0])
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        
        cursor.execute("SELECT nombre FROM equipos WHERE id = ?", (equipo_id,))
        equipo_nombre = cursor.fetchone()[0]

        cursor.execute('''
            SELECT e1.nombre, e2.nombre, p.goles_local, p.goles_visitante, p.jugado
            FROM partidos p
            JOIN equipos e1 ON p.equipo_local_id = e1.id
            JOIN equipos e2 ON p.equipo_visitante_id = e2.id
            WHERE p.equipo_local_id = ? OR p.equipo_visitante_id = ?
        ''', (equipo_id, equipo_id))
        
        partidos = cursor.fetchall()
        conn.close()

        if not partidos:
            await interaction.followup.send(f"No hay partidos registrados para {equipo_nombre}.", ephemeral=True)
            return

        embed = discord.Embed(title=f"📅 Fixture: {equipo_nombre}", color=discord.Color.blue())
        for local, visitante, g_loc, g_vis, jugado in partidos:
            estado = f"✅ {g_loc} - {g_vis}" if jugado else "⏳ Pendiente"
            embed.add_field(name=f"{local} vs {visitante}", value=f"Estado: {estado}", inline=False)

        await interaction.followup.send(embed=embed, ephemeral=True)


class FixtureView(discord.ui.View):
    def __init__(self, equipos):
        super().__init__()
        self.add_item(FixtureSelect(equipos))


# --- VISTAS INTERACTIVAS (TRASPASOS Y MUSEO) ---
class TraspasoFirmasView(discord.ui.View):
    def __init__(self, jugador, eq_origen_nombre, eq_destino_nombre, dt_origen_id, dt_destino_id, eq_origen_id, eq_destino_id, rol_origen_id, rol_destino_id):
        super().__init__(timeout=86400) # 24 horas
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
        f_orig_str = "✅ Firmado" if self.firma_origen else "⏳ Pendiente de firma"
        f_dest_str = "✅ Firmado" if self.firma_destino else "⏳ Pendiente de firma"
        
        orig_val = self.eq_origen_nombre if self.eq_origen_nombre else "Libre / Sin Equipo"

        embed = discord.Embed(
            title="📝 Solicitud Formal de Traspaso",
            description=f"Se ha iniciado el proceso de transferencia para el jugador {self.jugador.mention}.",
            color=discord.Color.orange()
        )
        embed.add_field(name="Origen", value=orig_val, inline=True)
        embed.add_field(name="Destino", value=self.eq_destino_nombre, inline=True)
        embed.add_field(name="\u200b", value="\u200b", inline=False)
        embed.add_field(name=f"Firma DT Origen", value=f_orig_str, inline=True)
        embed.add_field(name=f"Firma DT Destino", value=f_dest_str, inline=True)
        embed.set_footer(text="Ambos DTs deben autorizar presionando sus respectivos botones.")
        return embed

    @discord.ui.button(label="✍️ Firmar (DT Origen)", style=discord.ButtonStyle.secondary, custom_id="firma_dt_origen")
    async def firmar_origen(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.dt_origen_id:
            await interaction.response.send_message("❌ El jugador no tenía equipo previo, no requiere esta firma.", ephemeral=True)
            return

        if interaction.user.id != self.dt_origen_id:
            await interaction.response.send_message("❌ Solo el DT del equipo de origen puede presionar este botón.", ephemeral=True)
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
            await interaction.response.send_message("❌ Solo el DT del equipo de destino puede presionar este botón.", ephemeral=True)
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
            
            # Quitar rol de origen si aplica
            if self.rol_origen_id:
                rol_old = guild.get_role(self.rol_origen_id)
                if rol_old and rol_old in self.jugador.roles:
                    await self.jugador.remove_roles(rol_old)

            # Asignar rol de destino
            if self.rol_destino_id:
                rol_new = guild.get_role(self.rol_destino_id)
                if rol_new:
                    await self.jugador.add_roles(rol_new)

            # Actualizar Base de Datos
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
            embed_final.description = f"El traspaso de {self.jugador.mention} a **{self.eq_destino_nombre}** ha sido completado y registrado exitosamente."

            for child in self.children:
                child.disabled = True

            await interaction.message.edit(embed=embed_final, view=self)


class MuseoSelect(discord.ui.Select):
    def __init__(self, equipos):
        options = [discord.SelectOption(label=eq[1], value=str(eq[0]), emoji="🏛️") for eq in equipos]
        super().__init__(placeholder="Selecciona un equipo para ver su vitrina...", options=options)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        equipo_id = int(self.values[0])

        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT nombre FROM equipos WHERE id = ?", (equipo_id,))
        eq_nombre = cursor.fetchone()[0]

        cursor.execute("SELECT tipo, nombre, temporada, detalles FROM museo_titulos WHERE equipo_id = ?", (equipo_id,))
        items = cursor.fetchall()
        conn.close()

        if not items:
            await interaction.followup.send(f"🏛️ La vitrina de **{eq_nombre}** está vacía por el momento.", ephemeral=True)
            return

        embed = discord.Embed(title=f"🏛️ Vitrina de Trofeos: {eq_nombre}", color=discord.Color.gold())
        
        titulos = [it for it in items if it[0] == 'titulo']
        reconocimientos = [it for it in items if it[0] == 'reconocimiento']

        if titulos:
            txt = ""
            for t in titulos:
                temp_str = f" ({t[2]})" if t[2] else ""
                det_str = f" - *{t[3]}*" if t[3] else ""
                txt += f"🏆 **{t[1]}**{temp_str}{det_str}\n"
            embed.add_field(name="🏆 Títulos Oficiales", value=txt, inline=False)

        if reconocimientos:
            txt = ""
            for r in reconocimientos:
                temp_str = f" ({r[2]})" if r[2] else ""
                det_str = f" - *{r[3]}*" if r[3] else ""
                txt += f"🎖️ **{r[1]}**{temp_str}{det_str}\n"
            embed.add_field(name="🎖️ Menciones y Reconocimientos", value=txt, inline=False)

        await interaction.followup.send(embed=embed, ephemeral=True)


class MuseoView(discord.ui.View):
    def __init__(self, equipos):
        super().__init__()
        self.add_item(MuseoSelect(equipos))


# --- EVENTOS PRINCIPALES ---
@bot.event
async def on_ready():
    bot.add_view(TicketLaunchView())
    bot.add_view(TicketCloseView())

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


# --- GRUPO DE COMANDOS DE TEMPORADA ---
class SeasonGroup(app_commands.Group):
    def __init__(self):
        super().__init__(name="season", description="Gestión de temporadas de la liga")

    @app_commands.command(name="create", description="Crea una nueva temporada")
    @app_commands.checks.has_permissions(administrator=True)
    async def season_create(self, interaction: discord.Interaction, nombre: str):
        await interaction.response.defer()
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        try:
            cursor.execute("INSERT INTO temporadas (nombre, estado) VALUES (?, 'inscripcion')", (nombre,))
            conn.commit()
            await interaction.followup.send(f"🏆 Temporada **{nombre}** creada exitosamente en fase de inscripción.")
        except sqlite3.IntegrityError:
            await interaction.followup.send(f"❌ Ya existe una temporada llamada **{nombre}**.", ephemeral=True)
        finally:
            conn.close()

    @app_commands.command(name="start", description="Inicia oficialmente la temporada activa")
    @app_commands.checks.has_permissions(administrator=True)
    async def season_start(self, interaction: discord.Interaction):
        await interaction.response.defer()
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT id, nombre FROM temporadas WHERE estado = 'inscripcion' ORDER BY id DESC LIMIT 1")
        temp = cursor.fetchone()
        
        if not temp:
            await interaction.followup.send("❌ No hay ninguna temporada en fase de inscripción para iniciar.", ephemeral=True)
            conn.close()
            return

        cursor.execute("UPDATE temporadas SET estado = 'cerrada' WHERE estado = 'activa'")
        cursor.execute("UPDATE temporadas SET estado = 'activa' WHERE id = ?", (temp[0],))
        conn.commit()
        conn.close()

        await interaction.followup.send(f"🚀 ¡La temporada **{temp[1]}** ha iniciado oficialmente! Ahora se pueden subir replays.")

    @app_commands.command(name="close", description="Cierra la temporada activa")
    @app_commands.checks.has_permissions(administrator=True)
    async def season_close(self, interaction: discord.Interaction):
        await interaction.response.defer()
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT id, nombre FROM temporadas WHERE estado = 'activa'")
        temp = cursor.fetchone()

        if not temp:
            await interaction.followup.send("❌ No hay ninguna temporada activa para cerrar.", ephemeral=True)
            conn.close()
            return

        cursor.execute("UPDATE temporadas SET estado = 'cerrada' WHERE id = ?", (temp[0],))
        conn.commit()
        conn.close()

        await interaction.followup.send(f"🔒 La temporada **{temp[1]}** ha sido cerrada oficialmente.")

    @app_commands.command(name="info", description="Muestra información de la temporada actual")
    async def season_info(self, interaction: discord.Interaction):
        await interaction.response.defer()
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT nombre, estado FROM temporadas ORDER BY id DESC LIMIT 1")
        temp = cursor.fetchone()
        conn.close()

        if not temp:
            await interaction.followup.send("ℹ️ No hay temporadas registradas aún.", ephemeral=True)
        else:
            await interaction.followup.send(f"ℹ️ Temporada actual: **{temp[0]}** | Estado: `{temp[1].upper()}`")

    @app_commands.command(name="list", description="Lista todas las temporadas")
    async def season_list(self, interaction: discord.Interaction):
        await interaction.response.defer()
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT id, nombre, estado FROM temporadas ORDER BY id DESC")
        temporadas = cursor.fetchall()
        conn.close()

        if not temporadas:
            await interaction.followup.send("ℹ️ No hay temporadas en la base de datos.", ephemeral=True)
            return

        embed = discord.Embed(title="📜 Historial de Temporadas", color=discord.Color.blue())
        for t_id, nombre, estado in temporadas:
            embed.add_field(name=f"#{t_id} {nombre}", value=f"Estado: `{estado}`", inline=False)

        await interaction.followup.send(embed=embed)

bot.tree.add_command(SeasonGroup())


# --- GRUPO DE COMANDOS DEL MUSEO ---
class MuseoGroup(app_commands.Group):
    def __init__(self):
        super().__init__(name="museo", description="Módulo de museo, vitrinas y trofeos de equipos")

    async def equipo_autocomplete(self, interaction: discord.Interaction, current: str):
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT nombre FROM equipos WHERE nombre LIKE ? LIMIT 25", (f"%{current}%",))
        equipos = cursor.fetchall()
        conn.close()
        return [app_commands.Choice(name=eq[0], value=eq[0]) for eq in equipos]

    @app_commands.command(name="add_titulo", description="Añade un título oficial a la vitrina de un equipo (Admin).")
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

        await interaction.followup.send(f"🏆 Se ha añadido el título **{titulo}** a la vitrina de **{equipo}**.")

    @app_commands.command(name="add_reconocimiento", description="Añade una mención o reconocimiento a un equipo (Admin).")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.autocomplete(equipo=equipo_autocomplete)
    async def add_reconocimiento(self, interaction: discord.Interaction, equipo: str, reconocimiento: str, temporada: str = None, detalles: str = None):
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
            "INSERT INTO museo_titulos (equipo_id, tipo, nombre, temporada, detalles) VALUES (?, 'reconocimiento', ?, ?, ?)",
            (eq[0], reconocimiento, temporada, detalles)
        )
        conn.commit()
        conn.close()

        await interaction.followup.send(f"🎖️ Se ha añadido el reconocimiento **{reconocimiento}** a **{equipo}**.")

    @app_commands.command(name="ver", description="Abre el menú interactivo para consultar las vitrinas de los equipos.")
    async def ver(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT id, nombre FROM equipos")
        equipos = cursor.fetchall()
        conn.close()

        if not equipos:
            await interaction.followup.send("No hay equipos registrados en el sistema.", ephemeral=True)
            return

        await interaction.followup.send("🏛️ Selecciona un equipo para consultar su vitrina:", view=MuseoView(equipos), ephemeral=True)

bot.tree.add_command(MuseoGroup())


# --- RESTO DE COMANDOS DE LA LIGA Y TRASPASOS ---
@bot.tree.command(name="inscribir_equipo", description="Inscribe un equipo y crea su rol en Discord.")
@app_commands.checks.has_permissions(administrator=True)
async def inscribir_equipo(interaction: discord.Interaction, nombre_equipo: str, dt: discord.Member):
    await interaction.response.defer()
    guild = interaction.guild
    rol = await guild.create_role(name=nombre_equipo, reason="Rol para equipo de Haxball")
    await dt.add_roles(rol)

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO equipos (nombre, dt_id, rol_id) VALUES (?, ?, ?)", (nombre_equipo, dt.id, rol.id))
        conn.commit()
        await interaction.followup.send(f"✅ Equipo **{nombre_equipo}** inscrito correctamente. Rol creado y asignado a {dt.mention}.")
    except sqlite3.IntegrityError:
        await interaction.followup.send(f"❌ El equipo **{nombre_equipo}** ya existe.", ephemeral=True)
    finally:
        conn.close()

async def equipo_autocomplete(interaction: discord.Interaction, current: str):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT nombre FROM equipos WHERE nombre LIKE ? LIMIT 25", (f"%{current}%",))
    equipos = cursor.fetchall()
    conn.close()
    return [app_commands.Choice(name=eq[0], value=eq[0]) for eq in equipos]

@bot.tree.command(name="fichar", description="Inicia una solicitud formal de traspaso con firmas interactivas.")
@app_commands.autocomplete(equipo_destino=equipo_autocomplete)
async def fichar(interaction: discord.Interaction, jugador: discord.Member, equipo_destino: str):
    await interaction.response.defer()
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    # Obtener Equipo Destino
    cursor.execute("SELECT id, dt_id, rol_id FROM equipos WHERE nombre = ?", (equipo_destino,))
    eq_dest = cursor.fetchone()

    if not eq_dest:
        await interaction.followup.send(f"❌ El equipo de destino **{equipo_destino}** no existe.", ephemeral=True)
        conn.close()
        return

    eq_dest_id, dt_dest_id, rol_dest_id = eq_dest

    # Comprobar Equipo Actual del Jugador
    cursor.execute('''
        SELECT e.id, e.nombre, e.dt_id, e.rol_id 
        FROM jugadores j
        JOIN equipos e ON j.equipo_id = e.id
        WHERE j.discord_id = ?
    ''', (jugador.id,))
    eq_orig = cursor.fetchone()
    conn.close()

    eq_orig_id = eq_orig[0] if eq_orig else None
    eq_orig_nombre = eq_orig[1] if eq_orig else None
    dt_orig_id = eq_orig[2] if eq_orig else None
    rol_orig_id = eq_orig[3] if eq_orig else None

    if eq_orig_id == eq_dest_id:
        await interaction.followup.send(f"❌ {jugador.mention} ya pertenece a **{equipo_destino}**.", ephemeral=True)
        return

    view = TraspasoFirmasView(
        jugador=jugador,
        eq_origen_nombre=eq_orig_nombre,
        eq_destino_nombre=equipo_destino,
        dt_origen_id=dt_orig_id,
        dt_destino_id=dt_dest_id,
        eq_origen_id=eq_orig_id,
        eq_destino_id=eq_dest_id,
        rol_origen_id=rol_orig_id,
        rol_destino_id=rol_dest_id
    )

    await interaction.followup.send(embed=view.generar_embed(), view=view)

@bot.tree.command(name="fichar_jugador", description="Fichaje directo por administración (sin requerir firmas).")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.autocomplete(nombre_equipo=equipo_autocomplete)
async def fichar_jugador(interaction: discord.Interaction, jugador: discord.Member, nombre_equipo: str):
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
    cursor.execute("INSERT INTO jugadores (discord_id, equipo_id) VALUES (?, ?) ON CONFLICT(discord_id) DO UPDATE SET equipo_id = ?", 
                   (jugador.id, equipo_id, equipo_id))
    conn.commit()
    conn.close()

    rol = interaction.guild.get_role(rol_id)
    if rol:
        await jugador.add_roles(rol)

    await interaction.followup.send(f"📝 {jugador.mention} ha sido fichado por **{nombre_equipo}** por un administrador.")

@bot.tree.command(name="replay", description="Procesa un archivo .hbr2 para registrar el partido.")
@app_commands.autocomplete(local=equipo_autocomplete, visitante=equipo_autocomplete)
async def replay(interaction: discord.Interaction, archivo: discord.Attachment, local: str, visitante: str):
    await interaction.response.defer()
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM temporadas WHERE estado = 'activa'")
    temp_activa = cursor.fetchone()

    if not temp_activa:
        await interaction.followup.send("❌ No hay ninguna temporada activa para registrar partidos.", ephemeral=True)
        conn.close()
        return

    temporada_id = temp_activa[0]

    if not archivo.filename.endswith(".hbr2"):
        await interaction.followup.send("❌ El archivo debe ser formato `.hbr2`.", ephemeral=True)
        conn.close()
        return

    file_path = f"temp_{archivo.filename}"
    await archivo.save(file_path)

    try:
        node_path = shutil.which("node") or "node"
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: subprocess.run([node_path, "parse_replay.js", file_path], capture_output=True, text=True, check=True)
        )
        data = json.loads(result.stdout)
        os.remove(file_path)
    except Exception as e:
        if os.path.exists(file_path):
            os.remove(file_path)
        await interaction.followup.send(f"❌ Error al procesar el replay con Node.js: {e}")
        conn.close()
        return

    score = data.get("score", {})
    goals = data.get("goals", [])
    g_local = score.get("red", 0)
    g_vis = score.get("blue", 0)

    cursor.execute("SELECT id FROM equipos WHERE nombre = ?", (local,))
    eq_loc = cursor.fetchone()
    cursor.execute("SELECT id FROM equipos WHERE nombre = ?", (visitante,))
    eq_vis = cursor.fetchone()

    if not eq_loc or not eq_vis:
        await interaction.followup.send("❌ Uno de los equipos no está registrado.")
        conn.close()
        return

    cursor.execute('''
        INSERT INTO partidos (temporada_id, equipo_local_id, equipo_visitante_id, goles_local, goles_visitante, jugado)
        VALUES (?, ?, ?, ?, ?, 1)
    ''', (temporada_id, eq_loc[0], eq_vis[0], g_local, g_vis))
    partido_id = cursor.lastrowid

    for g in goals:
        player_name = g.get("scorer")
        cursor.execute("SELECT discord_id FROM jugadores WHERE discord_id = ?", (player_name,))
        p = cursor.fetchone()
        if p:
            cursor.execute("INSERT INTO goles_partido (partido_id, jugador_id, cantidad) VALUES (?, ?, 1)", (partido_id, p[0]))
            cursor.execute("UPDATE jugadores SET goles = goles + 1 WHERE discord_id = ?", (p[0],))

    conn.commit()

    cursor.execute("SELECT COUNT(DISTINCT id) FROM equipos")
    total_equipos = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM partidos WHERE jugado = 1 AND temporada_id = ?", (temporada_id,))
    total_partidos = cursor.fetchone()[0]

    fin_jornada = False
    if total_equipos > 0 and (total_partidos % (total_equipos // 2)) == 0:
        fin_jornada = True

    conn.close()

    embed = discord.Embed(title="⚽ Partido Registrado", color=discord.Color.green())
    embed.add_field(name="Resultado", value=f"**{local}** {g_local} - {g_vis} **{visitante}**", inline=False)
    embed.add_field(name="Goles Detectados", value=str(len(goals)), inline=False)

    await interaction.followup.send(embed=embed)

    if fin_jornada:
        canal_tabla = discord.utils.get(interaction.guild.text_channels, name="tabla")
        if canal_tabla:
            await canal_tabla.send("📢 **¡Ha finalizado la jornada! La tabla de posiciones se ha actualizado automáticamente.**")

@bot.tree.command(name="tabla", description="Muestra la tabla de posiciones.")
async def tabla(interaction: discord.Interaction):
    await interaction.response.defer()
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT id, nombre FROM equipos")
    equipos = cursor.fetchall()

    stats = {eq[0]: {"nombre": eq[1], "pj": 0, "pg": 0, "pe": 0, "pp": 0, "gf": 0, "gc": 0, "pts": 0} for eq in equipos}

    cursor.execute("SELECT equipo_local_id, equipo_visitante_id, goles_local, goles_visitante FROM partidos WHERE jugado = 1")
    partidos = cursor.fetchall()
    conn.close()

    for loc_id, vis_id, g_loc, g_vis in partidos:
        if loc_id in stats and vis_id in stats:
            stats[loc_id]["pj"] += 1
            stats[vis_id]["pj"] += 1
            stats[loc_id]["gf"] += g_loc
            stats[loc_id]["gc"] += g_vis
            stats[vis_id]["gf"] += g_vis
            stats[vis_id]["gc"] += g_loc

            if g_loc > g_vis:
                stats[loc_id]["pg"] += 1
                stats[loc_id]["pts"] += 3
                stats[vis_id]["pp"] += 1
            elif g_vis > g_loc:
                stats[vis_id]["pg"] += 1
                stats[vis_id]["pts"] += 3
                stats[loc_id]["pp"] += 1
            else:
                stats[loc_id]["pe"] += 1
                stats[loc_id]["pts"] += 1
                stats[vis_id]["pe"] += 1
                stats[vis_id]["pts"] += 1

    tabla_ordenada = sorted(stats.values(), key=lambda x: (x["pts"], x["gf"] - x["gc"], x["gf"]), reverse=True)

    embed = discord.Embed(title="🏆 Tabla de Posiciones", color=discord.Color.gold())
    descripcion = "```\nPos | Equipo            | PJ | PG | PE | PP | DG | PTS\n"
    descripcion += "-" * 50 + "\n"

    for i, eq in enumerate(tabla_ordenada, 1):
        dg = eq["gf"] - eq["gc"]
        descripcion += f"{i:<3} | {eq['nombre']:<16} | {eq['pj']:<2} | {eq['pg']:<2} | {eq['pe']:<2} | {eq['pp']:<2} | {dg:<2} | {eq['pts']:<3}\n"

    descripcion += "```"
    embed.description = descripcion
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="goleadores", description="Muestra el top 10 de goleadores de la liga.")
async def goleadores(interaction: discord.Interaction):
    await interaction.response.defer()
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT discord_id, goles FROM jugadores WHERE goles > 0 ORDER BY goles DESC LIMIT 10")
    top = cursor.fetchall()
    conn.close()

    if not top:
        await interaction.followup.send("Aún no hay goles registrados.", ephemeral=True)
        return

    embed = discord.Embed(title="🥇 Tabla de Goleadores", color=discord.Color.dark_gold())
    medallas = ["🥇", "🥈", "🥉"]

    for i, (p_id, goles) in enumerate(top, 1):
        prefix = medallas[i-1] if i <= 3 else f"#{i}"
        user = interaction.guild.get_member(p_id)
        nombre = user.mention if user else f"Jugador ID: {p_id}"
        embed.add_field(name=f"{prefix} {goles} Goles", value=nombre, inline=False)

    await interaction.followup.send(embed=embed)

@bot.tree.command(name="crear_partido", description="Programa un partido de la liga.")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.autocomplete(local=equipo_autocomplete, visitante=equipo_autocomplete)
async def crear_partido(interaction: discord.Interaction, local: str, visitante: str):
    await interaction.response.defer()
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM temporadas WHERE estado = 'activa'")
    temp_activa = cursor.fetchone()

    if not temp_activa:
        await interaction.followup.send("❌ No hay una temporada activa.", ephemeral=True)
        conn.close()
        return

    cursor.execute("SELECT id FROM equipos WHERE nombre = ?", (local,))
    eq_loc = cursor.fetchone()
    cursor.execute("SELECT id FROM equipos WHERE nombre = ?", (visitante,))
    eq_vis = cursor.fetchone()

    if not eq_loc or not eq_vis:
        await interaction.followup.send("❌ Uno de los equipos no existe.", ephemeral=True)
        conn.close()
        return

    cursor.execute("INSERT INTO partidos (temporada_id, equipo_local_id, equipo_visitante_id) VALUES (?, ?, ?)", 
                   (temp_activa[0], eq_loc[0], eq_vis[0]))
    conn.commit()
    conn.close()

    await interaction.followup.send(f"📅 Partido programado: **{local} vs {visitante}**")

@bot.tree.command(name="fixture", description="Consulta el fixture por equipo.")
async def fixture(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT id, nombre FROM equipos")
    equipos = cursor.fetchall()
    conn.close()

    if not equipos:
        await interaction.followup.send("No hay equipos registrados.", ephemeral=True)
        return

    await interaction.followup.send("Selecciona tu equipo para ver sus partidos:", view=FixtureView(equipos), ephemeral=True)

@bot.tree.command(name="sancionar", description="Aplica una sanción a un jugador.")
@app_commands.checks.has_permissions(administrator=True)
async def sancionar(interaction: discord.Interaction, jugador: discord.Member, tipo: str, suspension_partidos: int = 0, motivo: str = "Sin especificar"):
    await interaction.response.defer()
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO sanciones (jugador_id, tipo, partidos_suspension, motivo) VALUES (?, ?, ?, ?)",
                   (jugador.id, tipo, suspension_partidos, motivo))
    conn.commit()
    conn.close()

    await interaction.followup.send(f"🚨 {jugador.mention} ha sido sancionado con **{tipo}**. Suspensión: {suspension_partidos} partido(s). Motivo: {motivo}")

@bot.tree.command(name="sancionados", description="Muestra la lista de jugadores suspendidos.")
async def sancionados(interaction: discord.Interaction):
    await interaction.response.defer()
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT jugador_id, tipo, partidos_suspension, motivo FROM sanciones WHERE partidos_suspension > 0")
    lista = cursor.fetchall()
    conn.close()

    if not lista:
        await interaction.followup.send("✅ No hay jugadores suspendidos actualmente.", ephemeral=True)
        return

    embed = discord.Embed(title="🚨 Jugadores Sancionados", color=discord.Color.red())
    for j_id, tipo, partidos, motivo in lista:
        user = interaction.guild.get_member(j_id)
        nombre = user.mention if user else f"Jugador ID: {j_id}"
        embed.add_field(
            name=f"Sanción: {tipo}",
            value=f"Jugador: {nombre}\nPartidos restantes: **{partidos}**\nMotivo: *{motivo}*",
            inline=False
        )

    await interaction.followup.send(embed=embed)


# --- INICIO DEL BOT Y SERVIDOR WEB ---
keep_alive()
TOKEN = os.getenv("DISCORD_TOKEN")
bot.run(TOKEN)
