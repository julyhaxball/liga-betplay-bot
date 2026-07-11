import os
import io
import discord
from discord.ext import commands
from discord import app_commands
import aiosqlite
import asyncio
import re as _re

# Importaciones del módulo local database.py
from database import (
    init_db, get_equipo_by_discord, crear_equipo, get_todos_equipos,
    inscribir_jugador, get_plantilla, get_jugadores_libres, get_jugador_by_nombre,
    fichar_jugador, liberar_jugador, get_equipo_by_nombre, get_equipo_by_id,
    get_equipo_by_rol, crear_partido, get_fixture, cargar_resultado,
    generar_fixture_automatico, crear_oferta, get_oferta, get_ofertas_pendientes,
    aceptar_oferta, rechazar_oferta, get_jugador_by_id,
    agregar_sub_dt, quitar_sub_dt, get_equipo_by_sub_dt, get_sub_dts,
    activar_contrato, get_todos_jugadores_con_sueldo, incrementar_pago,
    dar_presupuesto_mensual, get_roles_equipos, DB_PATH
)

TOKEN = os.getenv("DISCORD_TOKEN", "MTUwODYyMTYzMjI4Mzg2OTI1NQ.GcNQYR.QE_FlSK32o4pkVlDUWqEgeEeHotMstuqAHYXs4")
ADMIN_ROL = "Admin"

COLOR_OK      = 0x1D9E75
COLOR_ERROR   = 0xD85A30
COLOR_INFO    = 0x378ADD
COLOR_AMARILLO = 0xEF9F27

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.presences = True  
bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

def es_admin(i): 
    return i.user.guild_permissions.administrator or any(r.name == ADMIN_ROL for r in i.user.roles)

def embed_ok(t, d=""): 
    return discord.Embed(title=t, description=d, color=COLOR_OK)

def embed_error(d): 
    return discord.Embed(title="❌ Error", description=d, color=COLOR_ERROR)

def embed_info(t, d=""): 
    return discord.Embed(title=t, description=d, color=COLOR_INFO)

def fmt(m): 
    return f"${m:,}".replace(",", ".")

async def get_equipo_dt_o_sub(discord_id):
    e = await get_equipo_by_discord(discord_id)
    if e: return e, True
    e = await get_equipo_by_sub_dt(discord_id)
    if e: return e, False
    return None, False

# ══════════════════════════════════════════════════════════════
#  SISTEMA DE CARPETAS Y PREMIOS (ACTUALIZADO)
# ══════════════════════════════════════════════════════════════

# Mapeo de carpetas con sus respectivos IDs de canales para cada premio
CARPETAS_PREMIOS = {
    "first_season": {
        "nombre_carpeta": "🌱 First Season",
        "golden_boot": 1503892522634842283,
        "playmaker": 1518398329187209246,
        "x5": 1503893154053488700,
        "winner_team": 1503893743747469362,
        "puskas": 1516557926267879444
    },
    "second_season": {
        "nombre_carpeta": "🔥 Second Season",
        "golden_boot": 1503892522634842283,  # Reemplazar con IDs reales si cambian por temporada
        "playmaker": 1518398329187209246,
        "x5": 1503893154053488700,
        "winner_team": 1503893743747469362,
        "puskas": 1516557926267879444
    },
    "playoffs": {
        "nombre_carpeta": "🏆 Playoffs",
        "golden_boot": 1503892522634842283,  # Reemplazar con IDs reales si cambian para Playoffs
        "playmaker": 1518398329187209246,
        "x5": 1503893154053488700,
        "winner_team": 1503893743747469362,
        "puskas": 1516557926267879444
    }
}

# 1. Menú Desplegable de Premios (Se activa DESPUÉS de elegir carpeta)
class PremiosSelect(discord.ui.Select):
    def __init__(self, carpeta_id):
        self.carpeta_id = carpeta_id
        options = [
            discord.SelectOption(label="⚽ Golden Boot", value="golden_boot", description="Ver los goles del máximo artillero"),
            discord.SelectOption(label="👟 Playmaker Award", value="playmaker", description="Ver las mejores asistencias de la liga"),
            discord.SelectOption(label="⭐ Quinteto Ideal (x5)", value="x5", description="Ver clips del quinteto ideal de la jornada"),
            discord.SelectOption(label="👑 Winner Team", value="winner_team", description="Ver las jugadas del equipo campeón"),
            discord.SelectOption(label="🎯 Premio Puskas", value="puskas", description="Ver las obras de arte nominadas al mejor gol")
        ]
        super().__init__(
            placeholder="Elige una categoría de premio...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="premios_select_clips"
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        categoria = self.values[0]
        
        # Obtener los canales de la carpeta seleccionada anteriormente
        canales = CARPETAS_PREMIOS.get(self.carpeta_id)
        canal_id = canales.get(categoria) if canales else None
        
        canal = interaction.guild.get_channel(canal_id)
        if not canal:
            await interaction.followup.send("❌ El canal asignado para este premio no se encuentra o el bot no tiene acceso.", ephemeral=True)
            return

        ultimo_clip = None
        async for mensaje in canal.history(limit=50):
            if mensaje.attachments or "http" in mensaje.content:
                ultimo_clip = mensaje
                break

        if not ultimo_clip:
            await interaction.followup.send(f"📂 No se encontraron clips recientes en el canal {canal.mention}.", ephemeral=True)
            return

        files = []
        for att in ultimo_clip.attachments:
            try:
                fp = io.BytesIO()
                await att.save(fp)
                fp.seek(0)
                files.append(discord.File(fp, filename=att.filename))
            except Exception:
                pass

        nombre_carpeta = canales["nombre_carpeta"]
        contenido = f"🎬 **Último aporte destacado en** {canal.mention} (`{nombre_carpeta}`) (por {ultimo_clip.author.mention}):\n"
        if ultimo_clip.content:
            contenido += f"\n{ultimo_clip.content}"

        if files:
            await interaction.followup.send(content=contenido, files=files, ephemeral=True)
        else:
            await interaction.followup.send(content=contenido, ephemeral=True)

# 2. Menú Desplegable Inicial para seleccionar la "Carpeta"
class CarpetasSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="🌱 First Season", value="first_season", description="Clips de la Primera Temporada"),
            discord.SelectOption(label="🔥 Second Season", value="second_season", description="Clips de la Segunda Temporada"),
            discord.SelectOption(label="🏆 Playoffs", value="playoffs", description="Clips de las fases eliminatorias")
        ]
        super().__init__(
            placeholder="📁 Selecciona una carpeta / temporada...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="carpetas_select"
        )

    async def callback(self, interaction: discord.Interaction):
        carpeta_seleccionada = self.values[0]
        nombre_carpeta = CARPETAS_PREMIOS[carpeta_seleccionada]["nombre_carpeta"]
        
        # Creamos una nueva vista que contenga el menú de premios filtrado por esta carpeta
        view_premios = discord.ui.View(timeout=None)
        view_premios.add_item(PremiosSelect(carpeta_id=carpeta_seleccionada))
        
        emb = embed_info(
            f"📁 Carpeta: {nombre_carpeta}", 
            "Ahora selecciona la categoría de premios de la que deseas extraer el clip reciente."
        )
        
        # Editamos el mensaje actual para mostrar el segundo paso
        await interaction.response.edit_message(embed=emb, view=view_premios)

class CarpetasView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(CarpetasSelect())

@tree.command(name="premios", description="Muestra las carpetas de temporadas y premios de la liga")
async def premios(interaction: discord.Interaction):
    emb = embed_info(
        "🏆 Galería de Carpetas y Premios Especiales", 
        "Selecciona primero una **carpeta o temporada** en el menú desplegable de abajo para ver sus categorías."
    )
    await interaction.response.send_message(embed=emb, view=CarpetasView(), ephemeral=True)

# ══════════════════════════════════════════════════════════════
#  EQUIPOS
# ══════════════════════════════════════════════════════════════

@tree.command(name="registrar", description="Regístrate como DT eligiendo el rol de tu equipo")
@app_commands.describe(rol="El rol de tu equipo en el servidor")
async def registrar(interaction: discord.Interaction, rol: discord.Role):
    if await get_equipo_by_discord(str(interaction.user.id)):
        await interaction.response.send_message(embed=embed_error("Ya tienes equipo registrado."), ephemeral=True); return
    if await get_equipo_by_rol(str(rol.id)):
        await interaction.response.send_message(embed=embed_error(f"**{rol.name}** ya está registrado."), ephemeral=True); return
    await crear_equipo(str(interaction.user.id), rol.name, interaction.user.display_name, str(rol.id))
    try: await interaction.user.add_roles(rol)
    except Exception: pass
    emb = embed_ok("⚽ ¡Equipo registrado!", f"**{rol.name}** inscrito en la liga.\nDT: {interaction.user.mention} {rol.mention}\n💰 Presupuesto: **{fmt(50_000_000)}**\n\nUsa `/inscribir_jugador` para añadir jugadores.")
    await interaction.response.send_message(embed=emb)

@tree.command(name="mi_equipo", description="Muestra tu equipo, plantilla, sueldos y valores")
async def mi_equipo(interaction: discord.Interaction):
    equipo = await get_equipo_by_discord(str(interaction.user.id))
    if not equipo:
        await interaction.response.send_message(embed=embed_error("No tienes equipo. Usa `/registrar`."), ephemeral=True); return
    jugadores = await get_plantilla(equipo["id"])
    emb = embed_info(f"🏟️ {equipo['nombre']}", f"DT: **{equipo['dt_nombre']}**")
    gasto = sum((j["sueldo"] or 0) for j in jugadores)
    valor_total = sum((j["valor"] or 0) for j in jugadores)
    emb.add_field(name="💰 Presupuesto", value=fmt(equipo["presupuesto"]), inline=True)
    emb.add_field(name="💸 Gasto semanal", value=fmt(gasto), inline=True)
    emb.add_field(name="📈 Valor plantilla", value=fmt(valor_total), inline=True)
    stats = (f"**PJ:** {equipo['pj']} | **PG:** {equipo['pg']} | **PE:** {equipo['pe']} | **PP:** {equipo['pp']}\n"
             f"**GF:** {equipo['gf']} | **GC:** {equipo['gc']} | **DG:** {equipo['gf']-equipo['gc']} | **Pts:** {equipo['puntos']}")
    emb.add_field(name="📊 Estadísticas", value=stats, inline=False)
    if jugadores:
        por_pos = {}
        for j in jugadores:
            s = fmt(j["sueldo"]) if j["sueldo"] else "—"
            v = fmt(j["valor"]) if j["valor"] else "Libre"
            por_pos.setdefault(j["posicion"],[]).append(f"`{j['dorsal']}` **{j['nombre']}** · Sueldo: {s} · Valor: {v}")
        for pos, lista in por_pos.items():
            emb.add_field(name=pos, value="\n".join(lista), inline=False)
    else:
        emb.add_field(name="Plantilla", value="Sin jugadores. Usa `/inscribir_jugador`.", inline=False)
    await interaction.response.send_message(embed=emb)

@tree.command(name="ver_equipo", description="Ver el equipo de otro DT")
@app_commands.describe(nombre="Nombre del equipo")
async def ver_equipo(interaction: discord.Interaction, nombre: str):
    equipo = await get_equipo_by_nombre(nombre)
    if not equipo:
        await interaction.response.send_message(embed=embed_error(f"No existe **{nombre}**."), ephemeral=True); return
    jugadores = await get_plantilla(equipo["id"])
    emb = embed_info(f"🏟️ {equipo['nombre']}", f"DT: **{equipo['dt_nombre']}**")
    stats = (f"**Pts:** {equipo['puntos']} | **PJ:** {equipo['pj']} | **PG:** {equipo['pg']} | **PE:** {equipo['pe']} | **PP:** {equipo['pp']}\n"
             f"**GF:** {equipo['gf']} | **GC:** {equipo['gc']} | **DG:** {equipo['gf']-equipo['gc']}")
    emb.add_field(name="📊 Estadísticas", value=stats, inline=False)
    if jugadores:
        por_pos = {}
        for j in jugadores:
            por_pos.setdefault(j["posicion"],[]).append(f"`{j['dorsal']}` {j['nombre']}")
        for pos, lista in por_pos.items():
            emb.add_field(name=pos, value="\n".join(lista), inline=True)
    else:
        emb.add_field(name="Plantilla", value="Sin jugadores.", inline=False)
    await interaction.response.send_message(embed=emb)

# ══════════════════════════════════════════════════════════════
#  JUGADORES Y CONTRATOS
# ══════════════════════════════════════════════════════════════

class ContratoView(discord.ui.View):
    def __init__(self, jugador_id, equipo, nombre, posicion, dorsal, sueldo, rol):
        super().__init__(timeout=86400)
        self.jugador_id = jugador_id
        self.equipo = equipo
        self.nombre = nombre
        self.posicion = posicion
        self.dorsal = dorsal
        self.sueldo = sueldo
        self.rol = rol

    @discord.ui.button(label="✅ Aceptar contrato", style=discord.ButtonStyle.success)
    async def aceptar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await activar_contrato(self.jugador_id, self.sueldo)
        guild = interaction.guild
        if guild:
            member = guild.get_member(interaction.user.id)
            if member:
                if self.equipo["rol_id"]:
                    try:
                        rol = guild.get_role(int(self.equipo["rol_id"]))
                        if rol: await member.add_roles(rol)
                    except Exception: pass
                try:
                    rol_libre = discord.utils.get(guild.roles, name="👤 | Agente Libre")
                    if rol_libre and rol_libre in member.roles:
                        await member.remove_roles(rol_libre)
                except Exception: pass
        emb = embed_ok("✅ ¡Contrato aceptado!", f"Bienvenido a **{self.equipo['nombre']}**, **{self.nombre}**!\nDorsal: #{self.dorsal} · {self.posicion}\n💰 Sueldo semanal: **{fmt(self.sueldo)}**")
        self.stop()
        for item in self.children: item.disabled = True
        await interaction.response.edit_message(embed=emb, view=self)
        if guild:
            canal_fichajes = discord.utils.get(guild.text_channels, name="✅・fichajes")
            if canal_fichajes:
                emb_pub = embed_ok(
                    "📋 Nuevo jugador inscrito",
                    f"**{self.nombre}** ({self.posicion}) · Dorsal #{self.dorsal}\n"
                    f"Se une a **{self.equipo['nombre']}**\n"
                    f"💰 Sueldo semanal: **{fmt(self.sueldo)}**"
                )
                await canal_fichajes.send(embed=emb_pub)

    @discord.ui.button(label="❌ Rechazar contrato", style=discord.ButtonStyle.danger)
    async def rechazar(self, interaction: discord.Interaction, button: discord.ui.Button):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("DELETE FROM jugadores WHERE id=?", (self.jugador_id,))
            await db.commit()
        emb = embed_error(f"**{self.nombre}** rechazó el contrato con **{self.equipo['nombre']}**.")
        self.stop()
        for item in self.children: item.disabled = True
        await interaction.response.edit_message(embed=emb, view=self)
        guild = interaction.guild
        if guild and self.equipo["discord_id"]:
            try:
                dt = guild.get_member(int(self.equipo["discord_id"]))
                if dt:
                    await dt.send(embed=embed_error(f"**{self.nombre}** rechazó tu oferta de contrato."))
            except Exception: pass

@tree.command(name="inscribir_jugador", description="Propone contrato a un jugador")
@app_commands.describe(jugador="Usuario de Discord del jugador", posicion="Posición", dorsal="Número de camiseta", sueldo="Sueldo semanal en dólares")
@app_commands.choices(posicion=[
    app_commands.Choice(name="Portero (POR)", value="POR"),
    app_commands.Choice(name="Defensa (DEF)", value="DEF"),
    app_commands.Choice(name="Mediocampista (MED)", value="MED"),
    app_commands.Choice(name="Delantero (DEL)", value="DEL"),
])
async def inscribir_jugador_cmd(interaction: discord.Interaction, jugador: discord.Member, posicion: str, dorsal: int, sueldo: int):
    equipo, _ = await get_equipo_dt_o_sub(str(interaction.user.id))
    if not equipo:
        await interaction.response.send_message(embed=embed_error("No tienes equipo."), ephemeral=True); return
    if sueldo < 0:
        await interaction.response.send_message(embed=embed_error("El sueldo no puede ser negativo."), ephemeral=True); return
    plantilla = await get_plantilla(equipo["id"])
    if any(j["dorsal"] == dorsal for j in plantilla):
        await interaction.response.send_message(embed=embed_error(f"El dorsal **{dorsal}** ya está ocupado."), ephemeral=True); return
    if len(plantilla) >= 25:
        await interaction.response.send_message(embed=embed_error("Ya tienes 25 jugadores."), ephemeral=True); return
    await inscribir_jugador(jugador.display_name, posicion, equipo["id"], dorsal, str(jugador.id))
    jug = await get_jugador_by_nombre(jugador.display_name)
    rol = interaction.guild.get_role(int(equipo["rol_id"])) if equipo["rol_id"] else None
    emb_oferta = discord.Embed(
        title="📋 Oferta de contrato",
        description=(f"**{equipo['nombre']}** te ofrece un contrato:\n\n"
                     f"👕 Dorsal: **#{dorsal}**\n🏃 Posición: **{posicion}**\n💰 Sueldo semanal: **{fmt(sueldo)}**\n\n¿Aceptas?"),
        color=COLOR_AMARILLO
    )
    view = ContratoView(jug["id"], equipo, jugador.display_name, posicion, dorsal, sueldo, rol)
    try:
        await jugador.send(embed=emb_oferta, view=view)
        await interaction.response.send_message(embed=embed_info("📨 Oferta enviada", f"Se envió la oferta a {jugador.mention}. Espera su respuesta."), ephemeral=True)
    except Exception:
        await interaction.response.send_message(embed=emb_oferta, view=view)

@tree.command(name="liberar_jugador", description="Libera un jugador al mercado libre")
@app_commands.describe(nombre="Nombre del jugador")
async def liberar_jugador_cmd(interaction: discord.Interaction, nombre: str):
    equipo, _ = await get_equipo_dt_o_sub(str(interaction.user.id))
    if not equipo:
        await interaction.response.send_message(embed=embed_error("No tienes equipo."), ephemeral=True); return
    jugador = await get_jugador_by_nombre(nombre)
    if not jugador or jugador["equipo_id"] != equipo["id"]:
        await interaction.response.send_message(embed=embed_error(f"No tienes ningún jugador llamado **{nombre}**."), ephemeral=True); return
    await liberar_jugador(jugador["id"])
    if equipo["rol_id"] and jugador["discord_id"]:
        try:
            member = interaction.guild.get_member(int(jugador["discord_id"])) if jugador["discord_id"] else None
            rol = interaction.guild.get_role(int(equipo["rol_id"]))
            if member and rol:
                await member.remove_roles(rol)
        except Exception: pass
    emb = embed_ok("🔓 Jugador liberado", f"**{nombre}** ahora está en el mercado libre.")
    await interaction.response.send_message(embed=emb)

@tree.command(name="fichar", description="Ficha un jugador libre del mercado")
@app_commands.describe(nombre="Nombre del jugador", dorsal="Dorsal que le asignarás")
async def fichar_cmd(interaction: discord.Interaction, nombre: str, dorsal: int):
    equipo, _ = await get_equipo_dt_o_sub(str(interaction.user.id))
    if not equipo:
        await interaction.response.send_message(embed=embed_error("No tienes equipo."), ephemeral=True); return
    jugador = await get_jugador_by_nombre(nombre)
    if not jugador or (jugador["equipo_id"] is not None and jugador["libre"] == 0):
        await interaction.response.send_message(embed=embed_error(f"**{nombre}** no está en el mercado."), ephemeral=True); return
    plantilla = await get_plantilla(equipo["id"])
    if any(j["dorsal"] == dorsal for j in plantilla):
        await interaction.response.send_message(embed=embed_error(f"El dorsal **{dorsal}** ya está ocupado."), ephemeral=True); return
    await fichar_jugador(jugador["id"], equipo["id"])
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE jugadores SET dorsal=? WHERE id=?", (dorsal, jugador["id"]))
        await db.commit()

    if jugador["discord_id"]:
        try:
            member = interaction.guild.get_member(int(jugador["discord_id"])) if jugador["discord_id"] else None
            if member:
                if equipo["rol_id"]:
                    rol_equipo = interaction.guild.get_role(int(equipo["rol_id"])) if equipo["rol_id"] else None
                    if rol_equipo:
                        await member.add_roles(rol_equipo)
                rol_libre = discord.utils.get(interaction.guild.roles, name="👤 | Agente Libre")
                if rol_libre and rol_libre in member.roles:
                    await member.remove_roles(rol_libre)
        except Exception: pass

    emb = embed_ok("🤝 ¡Fichaje completado!", f"**{nombre}** ({jugador['posicion']}) llega a **{equipo['nombre']}** con el dorsal #{dorsal}.")
    await interaction.response.send_message(embed=emb)

    canal_fich = discord.utils.get(interaction.guild.text_channels, name="✅・fichajes")
    if canal_fich:
        pos = jugador["posicion"]
        eq_nom = equipo["nombre"]
        emb_f = embed_ok("✅ Nuevo fichaje", f"**{nombre}** ({pos}) · Dorsal #{dorsal}\nEquipo: **{eq_nom}**")
        await canal_fich.send(embed=emb_f)

@tree.command(name="mercado", description="Muestra los jugadores libres disponibles")
async def mercado(interaction: discord.Interaction):
    emb = embed_info("🏪 Mercado libre")
    libres_bd = await get_jugadores_libres()
    if libres_bd:
        por_pos = {}
        for j in libres_bd:
            por_pos.setdefault(j["posicion"],[]).append(f"• {j['nombre']}")
        for pos, lista in por_pos.items():
            emb.add_field(name=f"Registrados — {pos}", value="\n".join(lista[:8]), inline=True)

    rol_libre = discord.utils.get(interaction.guild.roles, name="👤 | Agente Libre")
    await interaction.response.send_message(embed=emb)

# ══════════════════════════════════════════════════════════════
#  ARRANQUE SEGURO CON REGISTRO DE ERRORES (AL FINAL DEL ARCHIVO)
# ══════════════════════════════════════════════════════════════

async def main():
    try:
        await init_db()
        print("✅ Base de datos inicializada correctamente.")
        await bot.start(TOKEN)
    except Exception as e:
        import traceback
        error_completo = traceback.format_exc()
        print(f"❌ ERROR CRÍTICO AL INICIAR:\n{error_completo}")
        with open("error_bot.txt", "w", encoding="utf-8") as f:
            f.write(error_completo)

if __name__ == "__main__":
    asyncio.run(main())
