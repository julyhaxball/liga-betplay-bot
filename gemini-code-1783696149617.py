import discord
from discord import app_commands
from discord.ext import commands
import os
import subprocess
import json
import io
import aiosqlite

# ══════════════════════════════════════════════════════════════
#  CONFIGURACIÓN INICIAL
# ══════════════════════════════════════════════════════════════

TOKEN = os.getenv("DISCORD_TOKEN", "TU_TOKEN_AQUI")
DB_PATH = "liga_haxball.db"

COLOR_OK = 0x1D9E75
COLOR_ERROR = 0xD85A30
COLOR_INFO = 0x378ADD

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

def embed_ok(t, d=""): return discord.Embed(title=t, description=d, color=COLOR_OK)
def embed_error(d): return discord.Embed(title="❌ Error", description=d, color=COLOR_ERROR)
def embed_info(t, d=""): return discord.Embed(title=t, description=d, color=COLOR_INFO)

# ══════════════════════════════════════════════════════════════
#  BASE DE DATOS - INICIALIZACIÓN
# ══════════════════════════════════════════════════════════════

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        # Tabla de Equipos
        await db.execute("""
            CREATE TABLE IF NOT EXISTS equipos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT UNIQUE,
                dt_id TEXT,
                rol_id TEXT,
                logo_url TEXT,
                puntos INTEGER DEFAULT 0,
                pj INTEGER DEFAULT 0,
                pg INTEGER DEFAULT 0,
                pe INTEGER DEFAULT 0,
                pp INTEGER DEFAULT 0,
                gf INTEGER DEFAULT 0,
                gc INTEGER DEFAULT 0
            )
        """)
        # Tabla de Jugadores
        await db.execute("""
            CREATE TABLE IF NOT EXISTS jugadores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT,
                discord_id TEXT,
                equipo_id INTEGER,
                goles INTEGER DEFAULT 0,
                FOREIGN KEY(equipo_id) REFERENCES equipos(id)
            )
        """)
        # Tabla de Fixture
        await db.execute("""
            CREATE TABLE IF NOT EXISTS fixture (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha_num INTEGER,
                equipo_local TEXT,
                equipo_visitante TEXT,
                estado TEXT DEFAULT 'Pendiente'
            )
        """)
        # Tabla de Sanciones
        await db.execute("""
            CREATE TABLE IF NOT EXISTS sanciones (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                jugador_id TEXT,
                nombre_jugador TEXT,
                motivo TEXT,
                tipo TEXT,
                partidos_suspension INTEGER DEFAULT 1
            )
        """)
        await db.commit()

@bot.event
async def on_ready():
    await init_db()
    try:
        await tree.sync()
    except Exception as e:
        print(f"Error sincronizando comandos: {e}")
    print(f"🤖 Bot encendido correctamente como {bot.user}")

# Función para sugerir nombres de equipos al escribir comandos
async def equipo_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT nombre FROM equipos WHERE nombre LIKE ? LIMIT 25", (f"%{current}%",)) as cursor:
            filas = await cursor.fetchall()
            return [app_commands.Choice(name=row[0], value=row[0]) for row in filas]

# ══════════════════════════════════════════════════════════════
#  SISTEMA DE EQUIPOS Y FICHAJES
# ══════════════════════════════════════════════════════════════

@tree.command(name="inscribir_equipo", description="Inscribe tu equipo y crea el rol en Discord automáticamente")
@app_commands.describe(nombre="Nombre oficial de tu equipo", logo_url="Enlace directo a la imagen del logo")
async def inscribir_equipo(interaction: discord.Interaction, nombre: str, logo_url: str):
    await interaction.response.defer()

    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT id FROM equipos WHERE dt_id = ?", (str(interaction.user.id),)) as cursor:
            if await cursor.fetchone():
                await interaction.followup.send(embed=embed_error("Ya tienes un equipo inscrito como DT."), ephemeral=True)
                return

        try:
            nuevo_rol = await interaction.guild.create_role(
                name=nombre,
                mentionable=True,
                reason=f"Rol de equipo creado por {interaction.user.display_name}"
            )
            await interaction.user.add_roles(nuevo_rol)
        except Exception as e:
            await interaction.followup.send(embed=embed_error(f"No se pudo crear el rol en Discord: {e}"), ephemeral=True)
            return

        try:
            await db.execute(
                "INSERT INTO equipos (nombre, dt_id, rol_id, logo_url) VALUES (?, ?, ?, ?)",
                (nombre, str(interaction.user.id), str(nuevo_rol.id), logo_url)
            )
            await db.commit()
        except Exception:
            await nuevo_rol.delete()
            await interaction.followup.send(embed=embed_error("Ya existe un equipo con ese nombre."), ephemeral=True)
            return

    emb = embed_ok("🛡️ ¡Equipo Inscrito Exitosamente!", f"**Equipo:** {nombre}\n**DT:** {interaction.user.mention}\n**Rol Creado:** {nuevo_rol.mention}")
    emb.set_thumbnail(url=logo_url)
    await interaction.followup.send(embed=emb)

@tree.command(name="fichar_jugador", description="Ficha a un usuario para tu plantilla")
@app_commands.describe(usuario="Jugador de Discord a fichar")
async def fichar_jugador(interaction: discord.Interaction, usuario: discord.Member):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM equipos WHERE dt_id = ?", (str(interaction.user.id),)) as cursor:
            equipo = await cursor.fetchone()
        
        if not equipo:
            await interaction.response.send_message(embed=embed_error("No eres DT de ningún equipo registrado."), ephemeral=True)
            return

        async with db.execute("SELECT * FROM jugadores WHERE discord_id = ?", (str(usuario.id),)) as cursor:
            jugador = await cursor.fetchone()

        if jugador and jugador["equipo_id"]:
            await interaction.response.send_message(embed=embed_error(f"**{usuario.display_name}** ya pertenece a otro equipo."), ephemeral=True)
            return

        if jugador:
            await db.execute("UPDATE jugadores SET equipo_id = ? WHERE discord_id = ?", (equipo["id"], str(usuario.id)))
        else:
            await db.execute("INSERT INTO jugadores (nombre, discord_id, equipo_id) VALUES (?, ?, ?)", (usuario.display_name, str(usuario.id), equipo["id"]))
        
        await db.commit()

    if equipo["rol_id"]:
        try:
            rol = interaction.guild.get_role(int(equipo["rol_id"]))
            if rol: await usuario.add_roles(rol)
        except Exception: pass

    emb = embed_ok("🤝 ¡Fichaje Oficial!", f"**{usuario.mention}** ahora es nuevo jugador de **{equipo['nombre']}**.")
    if equipo["logo_url"]: emb.set_thumbnail(url=equipo["logo_url"])
    await interaction.response.send_message(embed=emb)

# ══════════════════════════════════════════════════════════════
#  REPLAYS, RESULTADOS Y TABLA AUTOMÁTICA
# ══════════════════════════════════════════════════════════════

@tree.command(name="replay", description="Procesa un partido .hbr2 y actualiza la liga")
@app_commands.describe(archivo="Archivo .hbr2", equipo_local="Equipo Local (Rojo)", equipo_visitante="Equipo Visitante (Azul)")
@app_commands.autocomplete(equipo_local=equipo_autocomplete, equipo_visitante=equipo_autocomplete)
async def replay(interaction: discord.Interaction, archivo: discord.Attachment, equipo_local: str, equipo_visitante: str):
    await interaction.response.defer()

    if not archivo.filename.endswith(".hbr2"):
        await interaction.followup.send("❌ El archivo debe ser de extensión **.hbr2**", ephemeral=True)
        return

    if equipo_local == equipo_visitante:
        await interaction.followup.send("❌ El equipo local y el visitante no pueden ser el mismo.", ephemeral=True)
        return

    path_temp = f"temp_{archivo.filename}"
    await archivo.save(path_temp)

    try:
        proceso = subprocess.run(["node", "parse_replay.js", path_temp], capture_output=True, text=True)
        datos = json.loads(proceso.stdout)

        if "error" in datos:
            await interaction.followup.send(f"❌ Error leyendo el replay: {datos['error']}")
            return

        g_red, g_blue = datos["redScore"], datos["blueScore"]

        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM equipos WHERE nombre = ?", (equipo_local,)) as c: eq_loc = await c.fetchone()
            async with db.execute("SELECT * FROM equipos WHERE nombre = ?", (equipo_visitante,)) as c: eq_vis = await c.fetchone()

            if not eq_loc or not eq_vis:
                await interaction.followup.send(embed=embed_error("Uno o ambos equipos no están registrados en la base de datos."))
                return

            pts_loc, pts_vis = 0, 0
            pg_loc, pe_loc, pp_loc = 0, 0, 0
            pg_vis, pe_vis, pp_vis = 0, 0, 0

            if g_red > g_blue:
                pts_loc, pg_loc, pp_vis = 3, 1, 1
            elif g_blue > g_red:
                pts_vis, pg_vis, pp_loc = 3, 1, 1
            else:
                pts_loc, pts_vis = 1, 1
                pe_loc, pe_vis = 1, 1

            # Actualizar Local
            await db.execute("""
                UPDATE equipos SET 
                puntos = puntos + ?, pj = pj + 1, pg = pg + ?, pe = pe + ?, pp = pp + ?, gf = gf + ?, gc = gc + ?
                WHERE nombre = ?
            """, (pts_loc, pg_loc, pe_loc, pp_loc, g_red, g_blue, equipo_local))

            # Actualizar Visitante
            await db.execute("""
                UPDATE equipos SET 
                puntos = puntos + ?, pj = pj + 1, pg = pg + ?, pe = pe + ?, pp = pp + ?, gf = gf + ?, gc = gc + ?
                WHERE nombre = ?
            """, (pts_vis, pg_vis, pe_vis, pp_vis, g_blue, g_red, equipo_visitante))

            # Registrar goles de jugadores
            for g in datos["goals"]:
                nombre_j = g['player']
                await db.execute("""
                    INSERT INTO jugadores (nombre, goles) VALUES (?, 1)
                    ON CONFLICT(discord_id) DO UPDATE SET goles = goles + 1
                """, (nombre_j,))

            # Marcar partido como jugado en el fixture si existía
            await db.execute("""
                UPDATE fixture SET estado = 'Finalizado' 
                WHERE (equipo_local = ? AND equipo_visitante = ?) AND estado = 'Pendiente'
            """, (equipo_local, equipo_visitante))

            await db.commit()

            # --- VERIFICACIÓN DE JORNADA COMPLETA ---
            async with db.execute("SELECT MIN(pj), MAX(pj), COUNT(DISTINCT pj) FROM equipos") as c:
                row = await c.fetchone()
                min_pj, max_pj, distinct_pj = row[0], row[1], row[2]

            # Si todos jugaron la misma cantidad de partidos y ya han jugado al menos 1
            if distinct_pj == 1 and min_pj > 0:
                canal_tabla = discord.utils.get(interaction.guild.text_channels, name="tabla")
                if canal_tabla:
                    async with db.execute("SELECT * FROM equipos ORDER BY puntos DESC, (gf - gc) DESC, gf DESC") as cursor:
                        equipos_tabla = await cursor.fetchall()

                    desc_t = ""
                    for idx, eq in enumerate(equipos_tabla, 1):
                        dg = eq["gf"] - eq["gc"]
                        desc_t += f"**{idx}. {eq['nombre']}** — `{eq['puntos']} pts` | PJ: {eq['pj']} | PG: {eq['pg']} | PE: {eq['pe']} | PP: {eq['pp']} | DG: {dg}\n"

                    emb_tabla = embed_info(f"📊 Tabla de Posiciones Oficial — Jornada {min_pj} Concluida", desc_t)
                    await canal_tabla.send(embed=emb_tabla)

        # Respuesta Embed del Replay
        emb = embed_ok("⚽ Partido Procesado y Registrado", f"**{equipo_local}** `{g_red}` - `{g_blue}` **{equipo_visitante}**")
        
        texto_goles = ""
        for g in datos["goals"]:
            m = f"{g['time'] // 60}:{g['time'] % 60:02d}"
            eq_nom = equipo_local if g['team'] == 'red' else equipo_visitante
            texto_goles += f"⚽ **{g['player']}** ({eq_nom}) - Min {m}\n"

        emb.add_field(name="🎯 Anotaciones", value=texto_goles if texto_goles else "Partido sin goles.", inline=False)
        await interaction.followup.send(embed=emb)

    except Exception as e:
        await interaction.followup.send(f"❌ Ocurrió un error al procesar el archivo: {e}")
    finally:
        if os.path.exists(path_temp): os.remove(path_temp)

@tree.command(name="tabla", description="Muestra la tabla de posiciones en tiempo real")
async def tabla(interaction: discord.Interaction):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM equipos ORDER BY puntos DESC, (gf - gc) DESC, gf DESC") as cursor:
            equipos = await cursor.fetchall()

    if not equipos:
        await interaction.response.send_message(embed=embed_info("📊 Tabla de Posiciones", "No hay equipos registrados aún."))
        return

    desc = ""
    for idx, eq in enumerate(equipos, 1):
        dg = eq["gf"] - eq["gc"]
        desc += f"**{idx}. {eq['nombre']}** — `{eq['puntos']} pts` | PJ: {eq['pj']} | PG: {eq['pg']} | PE: {eq['pe']} | PP: {eq['pp']} | DG: {dg}\n"

    emb = embed_info("📊 Tabla de Posiciones Oficial", desc)
    await interaction.response.send_message(embed=emb)

@tree.command(name="goleadores", description="Muestra el ranking de goleadores")
async def goleadores(interaction: discord.Interaction):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM jugadores WHERE goles > 0 ORDER BY goles DESC LIMIT 10") as cursor:
            jugadores = await cursor.fetchall()

    if not jugadores:
        await interaction.response.send_message(embed=embed_info("👟 Tabla de Goleadores", "Aún no hay goles registrados."))
        return

    desc = ""
    medallas = ["🥇", "🥈", "🥉"]
    for idx, j in enumerate(jugadores):
        prefix = medallas[idx] if idx < 3 else f"**{idx+1}.**"
        desc += f"{prefix} **{j['nombre']}** — `{j['goles']} goles`\n"

    emb = embed_info("👟 Top 10 Goleadores", desc)
    await interaction.response.send_message(embed=emb)

# ══════════════════════════════════════════════════════════════
#  SISTEMA DE FIXTURE
# ══════════════════════════════════════════════════════════════

@tree.command(name="crear_partido", description="Admin: Programa un partido en el fixture")
@app_commands.describe(fecha_num="Número de jornada", equipo_local="Equipo Local", equipo_visitante="Equipo Visitante")
@app_commands.autocomplete(equipo_local=equipo_autocomplete, equipo_visitante=equipo_autocomplete)
async def crear_partido(interaction: discord.Interaction, fecha_num: int, equipo_local: str, equipo_visitante: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO fixture (fecha_num, equipo_local, equipo_visitante) VALUES (?, ?, ?)",
            (fecha_num, equipo_local, equipo_visitante)
        )
        await db.commit()

    emb = embed_ok("📅 Partido Programado", f"**Jornada {fecha_num}:** {equipo_local} 🆚 {equipo_visitante}\n**Estado:** Pendiente")
    await interaction.response.send_message(embed=emb)

class EquiposFixtureSelect(discord.ui.Select):
    def __init__(self, lista_equipos):
        options = [discord.SelectOption(label=eq, value=eq, emoji="🛡️") for eq in lista_equipos[:25]]
        super().__init__(placeholder="Selecciona un equipo para ver sus partidos...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        equipo_sel = self.values[0]

        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("""
                SELECT * FROM fixture 
                WHERE (equipo_local = ? OR equipo_visitante = ?) AND estado = 'Pendiente'
                ORDER BY fecha_num ASC
            """, (equipo_sel, equipo_sel)) as cursor:
                partidos = await cursor.fetchall()

        if not partidos:
            await interaction.followup.send(embed=embed_info(f"📅 Fixture de {equipo_sel}", "¡No tiene partidos pendientes!"))
            return

        desc = ""
        for p in partidos:
            desc += f"📌 **Jornada {p['fecha_num']}:** {p['equipo_local']} 🆚 {p['equipo_visitante']}\n"

        emb = embed_info(f"📅 Partidos Pendientes — {equipo_sel}", desc)
        await interaction.followup.send(embed=emb)

class FixtureView(discord.ui.View):
    def __init__(self, lista_equipos):
        super().__init__(timeout=None)
        self.add_item(EquiposFixtureSelect(lista_equipos))

@tree.command(name="fixture", description="Consulta los partidos pendientes de un equipo")
async def fixture(interaction: discord.Interaction):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT nombre FROM equipos") as cursor:
            filas = await cursor.fetchall()
            lista_equipos = [row[0] for row in filas]

    if not lista_equipos:
        await interaction.response.send_message(embed=embed_info("📅 Fixture", "No hay equipos registrados en la liga."))
        return

    emb = embed_info("📅 Consulta de Fixture", "Selecciona un equipo del menú desplegable para ver sus partidos pendientes:")
    await interaction.response.send_message(embed=emb, view=FixtureView(lista_equipos))

# ══════════════════════════════════════════════════════════════
#  SISTEMA DE SANCTIONES Y TARJETAS
# ══════════════════════════════════════════════════════════════

@tree.command(name="sancionar", description="Admin: Sanciona a un jugador o le aplica tarjeta")
@app_commands.describe(usuario="Jugador a sancionar", tipo="Tipo de sanción", partidos="Partidos de suspensión", motivo="Razón de la sanción")
@app_commands.choices(tipo=[
    app_commands.Choice(name="🟨 Tarjeta Amarilla", value="Amarilla"),
    app_commands.Choice(name="🟥 Tarjeta Roja", value="Roja"),
    app_commands.Choice(name="🚫 Sanción Administrativa", value="Sancion")
])
async def sancionar(interaction: discord.Interaction, usuario: discord.Member, tipo: str, partidos: int, motivo: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO sanciones (jugador_id, nombre_jugador, motivo, tipo, partidos_suspension) VALUES (?, ?, ?, ?, ?)",
            (str(usuario.id), usuario.display_name, motivo, tipo, partidos)
        )
        await db.commit()

    iconos = {"Amarilla": "🟨", "Roja": "🟥", "Sancion": "🚫"}
    emb = embed_error(f"{iconos.get(tipo, '⚠️')} **Sanción Aplicada a {usuario.mention}**\n\n**Tipo:** {tipo}\n**Partidos suspendido:** {partidos}\n**Motivo:** {motivo}")
    await interaction.response.send_message(embed=emb)

@tree.command(name="sancionados", description="Muestra la lista de jugadores suspendidos en la liga")
async def sancionados(interaction: discord.Interaction):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM sanciones WHERE partidos_suspension > 0") as cursor:
            lista = await cursor.fetchall()

    if not lista:
        await interaction.response.send_message(embed=embed_info("🛡️ Sanciones", "No hay jugadores suspendidos en este momento."))
        return

    desc = ""
    for s in lista:
        desc += f"👤 **{s['nombre_jugador']}** — `{s['tipo']}` | Suspendido: **{s['partidos_suspension']} partido(s)**\n*Motivo:* {s['motivo']}\n\n"

    emb = embed_info("🚨 Lista de Jugadores Sancionados", desc)
    await interaction.response.send_message(embed=emb)

# ══════════════════════════════════════════════════════════════
#  GALERÍA DE PREMIOS
# ══════════════════════════════════════════════════════════════

CANALES_PREMIOS = {
    "golden_boot": 1503892522634842283,
    "playmaker": 1518398329187209246,
    "x5": 1503893154053488700,
    "winner_team": 1503893743747469362,
    "puskas": 1516557926267879444
}

class CategoriaPremiosSelect(discord.ui.Select):
    def __init__(self, temporada):
        self.temporada = temporada
        options = [
            discord.SelectOption(label="⚽ Golden Boot", value="golden_boot"),
            discord.SelectOption(label="👟 Playmaker Award", value="playmaker"),
            discord.SelectOption(label="⭐ Quinteto Ideal (x5)", value="x5"),
            discord.SelectOption(label="👑 Winner Team", value="winner_team"),
            discord.SelectOption(label="🎯 Premio Puskas", value="puskas")
        ]
        super().__init__(placeholder="Elige una categoría de premio...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        canal_id = CANALES_PREMIOS.get(self.values[0])
        canal = interaction.guild.get_channel(canal_id)
        if not canal:
            await interaction.followup.send("❌ Canal no encontrado.", ephemeral=True)
            return

        ultimo_clip = None
        async for mensaje in canal.history(limit=100):
            if mensaje.attachments or "http" in mensaje.content:
                miembro = interaction.guild.get_member(mensaje.author.id)
                if not miembro: continue
                
                tiene_first = any("First Season" in r.name for r in miembro.roles)
                tiene_playoffs = any("PlayOffs" in r.name or "Playoffs" in r.name for r in miembro.roles)

                if self.temporada == "playoffs" and (tiene_playoffs or (not tiene_first and not tiene_playoffs)):
                    ultimo_clip = mensaje
                    break
                elif self.temporada == "first_season" and tiene_first:
                    ultimo_clip = mensaje
                    break

        if not ultimo_clip:
            await interaction.followup.send("📂 No se encontraron clips recientes en esta categoría.", ephemeral=True)
            return

        files = []
        for att in ultimo_clip.attachments:
            try:
                fp = io.BytesIO()
                await att.save(fp)
                fp.seek(0)
                files.append(discord.File(fp, filename=att.filename))
            except Exception: pass

        contenido = f"🎬 **Aporte destacado en** {canal.mention} (por {ultimo_clip.author.mention}):\n{ultimo_clip.content}"
        await interaction.followup.send(content=contenido, files=files if files else None)

class TemporadaPremiosSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="📁 First Season", value="first_season", emoji="📝"),
            discord.SelectOption(label="📁 Playoffs", value="playoffs", emoji="🔥")
        ]
        super().__init__(placeholder="Selecciona una temporada...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        nueva_vista = discord.ui.View(timeout=None)
        nueva_vista.add_item(CategoriaPremiosSelect(self.values[0]))
        emb = embed_info("🏆 Galería de Premios", f"Carpeta seleccionada: **{self.values[0].replace('_', ' ').title()}**.\nElige una categoría abajo:")
        await interaction.response.edit_message(embed=emb, view=nueva_vista)

class PremiosView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(TemporadaPremiosSelect())

@tree.command(name="premios", description="Consulta los mejores clips guardados por temporadas")
async def premios(interaction: discord.Interaction):
    emb = embed_info("🏆 Galería de Carpetas y Premios", "Selecciona una carpeta o temporada abajo para ver los clips.")
    await interaction.response.send_message(embed=emb, view=PremiosView())

if __name__ == "__main__":
    bot.run(TOKEN)
