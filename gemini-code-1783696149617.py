import discord
from discord import app_commands
from discord.ext import commands, tasks
import os
import asyncio
import datetime
import aiosqlite
import io
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
#  SISTEMA DE PREMIOS Y CLIPS RECIENTES (FILTRADO POR ROLES EXÁCTOS)
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
        self.temporada = temporada  # "first_season" o "playoffs"
        options = [
            discord.SelectOption(label="⚽ Golden Boot", value="golden_boot", description="Ver los goles del máximo artillero"),
            discord.SelectOption(label="👟 Playmaker Award", value="playmaker", description="Ver las mejores asistencias de la liga"),
            discord.SelectOption(label="⭐ Quinteto Ideal (x5)", value="x5", description="Ver clips del quinteto ideal de la jornada"),
            discord.SelectOption(label="👑 Winner Team", value="winner_team", description="Ver las jugadas del equipo campeón"),
            discord.SelectOption(label="🎯 Premio Puskas", value="puskas", description="Ver las obras de arte nominadas al mejor gol")
        ]
        super().__init__(
            placeholder="Elige una categoría de premio para ver clips...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="categoria_premios_select_v2"
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=False)
        categoria = self.values[0]
        canal_id = CANALES_PREMIOS.get(categoria)
        
        canal = interaction.guild.get_channel(canal_id)
        if not canal:
            await interaction.followup.send("❌ El canal asignado para este premio no se encuentra disponible.", ephemeral=False)
            return

        ultimo_clip = None
        
        async for mensaje in canal.history(limit=100):
            if mensaje.attachments or "http" in mensaje.content:
                miembro = interaction.guild.get_member(mensaje.author.id)
                if not miembro:
                    if self.temporada == "playoffs":
                        ultimo_clip = mensaje
                        break
                    continue

                tiene_rol_first_season = any("First Season" in r.name for r in miembro.roles)
                tiene_rol_playoffs = any("PlayOffs" in r.name or "Playoffs" in r.name for r in miembro.roles)
                
                if not tiene_rol_first_season and not tiene_rol_playoffs:
                    if self.temporada == "playoffs":
                        ultimo_clip = mensaje
                        break
                    continue

                if self.temporada == "playoffs" and tiene_rol_playoffs:
                    ultimo_clip = mensaje
                    break
                elif self.temporada == "first_season" and tiene_rol_first_season:
                    ultimo_clip = mensaje
                    break

        if not ultimo_clip:
            temp_name = "Playoffs" if self.temporada == "playoffs" else "First Season"
            await interaction.followup.send(f"📂 No se encontraron clips recientes en {canal.mention} que pertenezcan a la carpeta **{temp_name}**.", ephemeral=False)
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

        temp_label = "Playoffs" if self.temporada == "playoffs" else "First Season"
        contenido = f"🎬 **[{temp_label}] Aporte destacado en** {canal.mention} (por {ultimo_clip.author.mention}):\n"
        if ultimo_clip.content:
            contenido += f"\n{ultimo_clip.content}"

        if files:
            await interaction.followup.send(content=contenido, files=files, ephemeral=False)
        else:
            await interaction.followup.send(content=contenido, ephemeral=False)

class TemporadaPremiosSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="📁 First Season", value="first_season", description="Ver clips de la Temporada Regular", emoji="📝"),
            discord.SelectOption(label="📁 Playoffs", value="playoffs", description="Ver clips de las Eliminatorias Directas", emoji="🔥")
        ]
        super().__init__(
            placeholder="Selecciona una carpeta / temporada...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="temporada_premios_select_v2"
        )

    async def callback(self, interaction: discord.Interaction):
        temporada_elegida = self.values[0]
        temp_label = "First Season" if temporada_elegida == "first_season" else "Playoffs"
        
        nueva_vista = discord.ui.View(timeout=None)
        nueva_vista.add_item(CategoriaPremiosSelect(temporada_elegida))
        
        emb_actualizado = discord.Embed(
            title="🏆 Galería de Carpetas y Premios Especiales",
            description=f"Has abierto la carpeta: **{temp_label}**.\nEl bot clasificará los clips buscando los roles específicos en los autores.\n\nSelecciona la categoría abajo:",
            color=0x378ADD
        )
        await interaction.response.edit_message(embed=emb_actualizado, view=nueva_vista)

class PremiosView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(TemporadaPremiosSelect())

@tree.command(name="premios", description="Muestra el menú para consultar los mejores clips filtrados por temporadas")
async def premios(interaction: discord.Interaction):
    emb = embed_info(
        "🏆 Galería de Carpetas y Premios Especiales", 
        "Selecciona primero una **carpeta o temporada** en el menú desplegable de abajo para ver sus categorías correspondientes."
    )
    await interaction.response.send_message(embed=emb, view=PremiosView(), ephemeral=False)

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
    if rol_libre and rol_libre.members:
        agentes = [m.display_name for m in rol_libre.members if not m.bot]
        if agentes:
            chunk = agentes[:25]
            emb.add_field(name=f"👥 Agentes libres ({len(agentes)})", value="\n".join(f"• {n}" for n in chunk), inline=False)
            if len(agentes) > 25:
                emb.set_footer(text=f"... y {len(agentes)-25} más")

    if not libres_bd and (not rol_libre or not [m for m in rol_libre.members if not m.bot]):
        emb.description = "No hay jugadores disponibles."

    await interaction.response.send_message(embed=emb)

# ══════════════════════════════════════════════════════════════
#  FICHAJES CON DINERO
# ══════════════════════════════════════════════════════════════

@tree.command(name="ofertar", description="Haz una oferta económica por un jugador rival")
@app_commands.describe(equipo_rival="Rol del equipo rival", jugador="Nombre del jugador", monto="Cantidad en dólares")
async def ofertar(interaction: discord.Interaction, equipo_rival: discord.Role, jugador: str, monto: int):
    equipo_comprador, _ = await get_equipo_dt_o_sub(str(interaction.user.id))
    if not equipo_comprador:
        await interaction.response.send_message(embed=embed_error("No tienes equipo."), ephemeral=True); return
    if monto <= 0:
        await interaction.response.send_message(embed=embed_error("El monto debe ser mayor a $0."), ephemeral=True); return
    if equipo_comprador["presupuesto"] < monto:
        await interaction.response.send_message(embed=embed_error(f"No tienes suficiente presupuesto.\nDisponible: **{fmt(equipo_comprador['presupuesto'])}**"), ephemeral=True); return
    equipo_vendedor = await get_equipo_by_rol(str(equipo_rival.id))
    if not equipo_vendedor:
        await interaction.response.send_message(embed=embed_error(f"**{equipo_rival.name}** no está en la liga."), ephemeral=True); return
    if equipo_comprador["id"] == equipo_vendedor["id"]:
        await interaction.response.send_message(embed=embed_error("No puedes hacerte una oferta a ti mismo."), ephemeral=True); return
    jug = await get_jugador_by_nombre(jugador)
    if not jug or jug["equipo_id"] != equipo_vendedor["id"]:
        await interaction.response.send_message(embed=embed_error(f"**{equipo_rival.name}** no tiene a **{jugador}**."), ephemeral=True); return
    oferta_id = await crear_oferta(jug["id"], equipo_comprador["id"], equipo_vendedor["id"], monto)
    emb = embed_ok("💸 Oferta enviada", f"**{equipo_comprador['nombre']}** ofrece **{fmt(monto)}** por **{jugador}** ({jug['posicion']})\nAl equipo: **{equipo_vendedor['nombre']}**\nID: `{oferta_id}`")
    await interaction.response.send_message(emb)
    dt_rival = interaction.guild.get_member(int(equipo_vendedor["discord_id"])) if equipo_vendedor["discord_id"] else None
    if dt_rival:
        try:
            notif = discord.Embed(title="📨 ¡Tienes una oferta!", description=f"**{equipo_comprador['nombre']}** ofrece **{fmt(monto)}** por **{jugador}** ({jug['posicion']})\n\nUsa `/mis_ofertas` para verla.", color=COLOR_AMARILLO)
            await dt_rival.send(embed=notif)
        except Exception: pass

@tree.command(name="mis_ofertas", description="Ver las ofertas pendientes para tu equipo")
async def mis_ofertas(interaction: discord.Interaction):
    equipo = await get_equipo_by_discord(str(interaction.user.id))
    if not equipo:
        await interaction.response.send_message(embed=embed_error("No tienes equipo."), ephemeral=True); return
    ofertas = await get_ofertas_pendientes(equipo["id"])
    if not ofertas:
        await interaction.response.send_message(embed=embed_info("📨 Ofertas pendientes", "No tienes ofertas pendientes."), ephemeral=True); return
    emb = embed_info("📨 Ofertas pendientes", f"Tienes **{len(ofertas)}** oferta(s):")
    for o in ofertas:
        jug = await get_jugador_by_id(o["jugador_id"])
        eq = await get_equipo_by_id(o["equipo_comprador_id"])
        emb.add_field(name=f"Oferta ID: {o['id']}", value=f"**{eq['nombre']}** ofrece **{fmt(o['monto'])}** por **{jug['nombre']}** ({jug['posicion']})\n✅ `/aceptar_oferta id:{o['id']}` · ❌ `/rechazar_oferta id:{o['id']}`", inline=False)
    await interaction.response.send_message(embed=emb, ephemeral=True)

@tree.command(name="aceptar_oferta", description="Acepta una oferta de fichaje")
@app_commands.describe(id="ID de la oferta")
async def aceptar_oferta_cmd(interaction: discord.Interaction, id: int):
    equipo = await get_equipo_by_discord(str(interaction.user.id))
    if not equipo:
        await interaction.response.send_message(embed=embed_error("No tienes equipo."), ephemeral=True); return
    oferta = await get_oferta(id)
    if not oferta or oferta["equipo_vendedor_id"] != equipo["id"] or oferta["estado"] != "pendiente":
        await interaction.response.send_message(embed=embed_error("Oferta no válida o ya respondida."), ephemeral=True); return
    await aceptar_oferta(id)
    jug = await get_jugador_by_id(oferta["jugador_id"])
    eq_c = await get_equipo_by_id(oferta["equipo_comprador_id"])
    eq_v = await get_equipo_by_id(oferta["equipo_vendedor_id"])
    
    if jug["discord_id"]:
        try:
            member = interaction.guild.get_member(int(jug["discord_id"])) if jug["discord_id"] else None
            if member:
                if eq_v["rol_id"]:
                    rol_v = interaction.guild.get_role(int(eq_v["rol_id"])) if eq_v["rol_id"] else None
                    if rol_v: await member.remove_roles(rol_v)
                if eq_c["rol_id"]:
                    rol_c = interaction.guild.get_role(int(eq_c["rol_id"])) if eq_c["rol_id"] else None
                    if rol_c: await member.add_roles(rol_c)
        except Exception: pass
        
    try:
        from generar_imagen import generar_fichaje
        buf = generar_fichaje(jug["nombre"], jug["posicion"], jug["dorsal"] or 0, eq_v["nombre"], eq_c["nombre"], oferta["monto"])
        file = discord.File(buf, filename="fichaje.png")
        emb = embed_ok("✅ ¡Transferencia completada!", f"**{jug['nombre']}** → **{eq_c['nombre']}**\n💰 **{fmt(oferta['monto'])}**")
        emb.set_image(url="attachment://fichaje.png")
        await interaction.response.send_message(embed=emb, file=file)

        if interaction.guild:
            canal_fichajes = discord.utils.get(interaction.guild.text_channels, name="✅・fichajes")
            if canal_fichajes:
                from generar_imagen import generar_fichaje as gf2
                buf2 = gf2(jug["nombre"], jug["posicion"], jug["dorsal"] or 0, eq_v["nombre"], eq_c["nombre"], oferta["monto"])
                file2 = discord.File(buf2, filename="fichaje.png")
                emb2 = embed_ok("⚽ ¡Fichaje oficial!", f"**{jug['nombre']}** ({jug['posicion']}) se une a **{eq_c['nombre']}**\n💰 Traspaso: **{fmt(oferta['monto'])}**")
                emb2.set_image(url="attachment://fichaje.png")
                await canal_fichajes.send(embed=emb2, file=file2)
    except Exception:
        emb = embed_ok("✅ ¡Transferencia completada!", f"**{jug['nombre']}** → **{eq_c['nombre']}**\n💰 **{fmt(oferta['monto'])}**")
        await interaction.response.send_message(embed=emb)
        if interaction.guild:
            canal_fichajes = discord.utils.get(interaction.guild.text_channels, name="✅・fichajes")
            if canal_fichajes:
                emb2 = embed_ok("⚽ ¡Fichaje oficial!", f"**{jug['nombre']}** ({jug['posicion']}) se une a **{eq_c['nombre']}**\n💰 Traspaso: **{fmt(oferta['monto'])}**")
                await canal_fichajes.send(embed=emb2)
                
    dt_c = interaction.guild.get_member(int(eq_c["discord_id"])) if eq_c["discord_id"] else None
    if dt_c:
        try: await dt_c.send(embed=embed_ok("🎉 ¡Oferta aceptada!", f"**{eq_v['nombre']}** aceptó tu oferta.\n**{jug['nombre']}** ya es tuyo."))
        except Exception: pass

@tree.command(name="rechazar_oferta", description="Rechaza una oferta de fichaje")
@app_commands.describe(id="ID de la oferta")
async def rechazar_oferta_cmd(interaction: discord.Interaction, id: int):
    equipo = await get_equipo_by_discord(str(interaction.user.id))
    if not equipo:
        await interaction.response.send_message(embed=embed_error("No tienes equipo."), ephemeral=True); return
    oferta = await get_oferta(id)
    if not oferta or oferta["equipo_vendedor_id"] != equipo["id"] or oferta["estado"] != "pendiente":
        await interaction.response.send_message(embed=embed_error("Oferta no válida o ya respondida."), ephemeral=True); return
    await rechazar_oferta(id)
    jug = await get_jugador_by_id(oferta["jugador_id"])
    eq_c = await get_equipo_by_id(oferta["equipo_comprador_id"])
    await interaction.response.send_message(embed=embed_error(f"Oferta de **{eq_c['nombre']}** por **{jug['nombre']}** rechazada."))
    dt_c = interaction.guild.get_member(int(eq_c["discord_id"])) if eq_c["discord_id"] else None
    if dt_c:
        try: await dt_c.send(embed=discord.Embed(title="❌ Oferta rechazada", description=f"**{equipo['nombre']}** rechazó tu oferta por **{jug['nombre']}**.", color=COLOR_ERROR))
        except Exception: pass

# ══════════════════════════════════════════════════════════════
#  SUB DTS
# ══════════════════════════════════════════════════════════════

@tree.command(name="agregar_sub_dt", description="Agrega un sub DT a tu equipo")
@app_commands.describe(usuario="Usuario que será sub DT")
async def agregar_sub_dt_cmd(interaction: discord.Interaction, usuario: discord.Member):
    equipo = await get_equipo_by_discord(str(interaction.user.id))
    if not equipo:
        await interaction.response.send_message(embed=embed_error("Solo el DT principal puede agregar sub DTs."), ephemeral=True); return
    if usuario.id == interaction.user.id:
        await interaction.response.send_message(embed=embed_error("No puedes agregarte a ti mismo."), ephemeral=True); return
    otro = await get_equipo_by_discord(str(usuario.id))
    if otro:
        await interaction.response.send_message(embed=embed_error(f"**{usuario.display_name}** ya es DT de **{otro['nombre']}**."), ephemeral=True); return
    subs = await get_sub_dts(equipo["id"])
    if len(subs) >= 2:
        await interaction.response.send_message(embed=embed_error("Ya tienes 2 sub DTs, ese es el máximo."), ephemeral=True); return
    ok = await agregar_sub_dt(equipo["id"], str(usuario.id))
    if not ok:
        await interaction.response.send_message(embed=embed_error(f"**{usuario.display_name}** ya es sub DT."), ephemeral=True); return
    emb = embed_ok("👥 Sub DT agregado", f"**{usuario.display_name}** ahora es sub DT de **{equipo['nombre']}**.\nPuede fichar, inscribir y liberar jugadores.")
    await interaction.response.send_message(embed=emb)

@tree.command(name="quitar_sub_dt", description="Quita un sub DT de tu equipo")
@app_commands.describe(usuario="Sub DT a quitar")
async def quitar_sub_dt_cmd(interaction: discord.Interaction, usuario: discord.Member):
    equipo = await get_equipo_by_discord(str(interaction.user.id))
    if not equipo:
        await interaction.response.send_message(embed=embed_error("Solo el DT principal puede quitar sub DTs."), ephemeral=True); return
    await quitar_sub_dt(equipo["id"], str(usuario.id))
    emb = embed_ok("👥 Sub DT eliminado", f"**{usuario.display_name}** ya no es sub DT de **{equipo['nombre']}**.")
    await interaction.response.send_message(emb)

# ══════════════════════════════════════════════════════════════
#  LIGA
# ══════════════════════════════════════════════════════════════

@tree.command(name="tabla", description="Tabla de posiciones")
async def tabla(interaction: discord.Interaction):
    equipos = await get_todos_equipos()
    if not equipos:
        await interaction.response.send_message(embed=embed_info("📊 Tabla", "No hay equipos registrados.")); return
    emb = embed_info("📊 Tabla de posiciones")

    equipos.sort(key=lambda x: (x.get('puntos', 0), x.get('dg', 0)), reverse=True)
    
    descripcion = ""
    for i, eq in enumerate(equipos, 1):
        descripcion += f"**{i}. {eq['nombre']}** - {eq.get('puntos', 0)} pts (PJ: {eq.get('pj', 0)} | DG: {eq.get('dg', 0)})\n"
        
    emb.description = descripcion
    await interaction.response.send_message(embed=emb)

if __name__ == "__main__":
    if not bot.is_ready():
        bot.run(TOKEN)
