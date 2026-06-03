import discord
from discord import app_commands
from discord.ext import commands
import os
from database import (
    init_db, get_equipo_by_discord, crear_equipo, get_todos_equipos,
    inscribir_jugador, get_plantilla, get_jugadores_libres, get_jugador_by_nombre,
    fichar_jugador, liberar_jugador, get_equipo_by_nombre, get_equipo_by_id,
    get_equipo_by_rol, crear_partido, get_fixture, cargar_resultado,
    generar_fixture_automatico, crear_oferta, get_oferta, get_ofertas_pendientes,
    aceptar_oferta, rechazar_oferta, get_jugador_by_id
)

TOKEN = os.getenv("DISCORD_TOKEN", "TU_TOKEN_AQUI")
ADMIN_ROL = "Admin"

COLOR_OK       = 0x1D9E75
COLOR_ERROR    = 0xD85A30
COLOR_INFO     = 0x378ADD
COLOR_AMARILLO = 0xEF9F27

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

def es_admin(interaction: discord.Interaction) -> bool:
    if interaction.user.guild_permissions.administrator:
        return True
    return any(r.name == ADMIN_ROL for r in interaction.user.roles)

def embed_ok(titulo, descripcion=""):
    return discord.Embed(title=titulo, description=descripcion, color=COLOR_OK)

def embed_error(descripcion):
    return discord.Embed(title="❌ Error", description=descripcion, color=COLOR_ERROR)

def embed_info(titulo, descripcion=""):
    return discord.Embed(title=titulo, description=descripcion, color=COLOR_INFO)

def fmt_dinero(monto: int) -> str:
    return f"${monto:,}".replace(",", ".")

# ══════════════════════════════════════════════════════════════
#  EQUIPOS
# ══════════════════════════════════════════════════════════════

@tree.command(name="registrar", description="Regístrate como DT eligiendo el rol de tu equipo")
@app_commands.describe(rol="El rol de tu equipo en el servidor")
async def registrar(interaction: discord.Interaction, rol: discord.Role):
    existente = await get_equipo_by_discord(str(interaction.user.id))
    if existente:
        await interaction.response.send_message(
            embed=embed_error(f"Ya tienes un equipo registrado: **{existente['nombre']}**"), ephemeral=True)
        return
    por_rol = await get_equipo_by_rol(str(rol.id))
    if por_rol:
        await interaction.response.send_message(
            embed=embed_error(f"El rol **{rol.name}** ya está registrado por otro DT."), ephemeral=True)
        return
    await crear_equipo(str(interaction.user.id), rol.name, interaction.user.display_name, str(rol.id))
    if rol not in interaction.user.roles:
        try:
            await interaction.user.add_roles(rol)
        except:
            pass
    emb = embed_ok(
        "⚽ ¡Equipo registrado!",
        f"**{rol.name}** ha sido inscrito en la liga.\n"
        f"DT: {interaction.user.mention} {rol.mention}\n"
        f"💰 Presupuesto inicial: **{fmt_dinero(50_000_000)}**\n\n"
        f"Añade jugadores con `/inscribir_jugador`."
    )
    await interaction.response.send_message(embed=emb)


@tree.command(name="mi_equipo", description="Muestra la información y plantilla de tu equipo")
async def mi_equipo(interaction: discord.Interaction):
    equipo = await get_equipo_by_discord(str(interaction.user.id))
    if not equipo:
        await interaction.response.send_message(embed=embed_error("No tienes equipo. Usa `/registrar`."), ephemeral=True)
        return
    jugadores = await get_plantilla(equipo["id"])
    emb = embed_info(f"🏟️ {equipo['nombre']}", f"DT: **{equipo['dt_nombre']}**")
    emb.add_field(name="💰 Presupuesto", value=fmt_dinero(equipo["presupuesto"]), inline=False)
    stats = (
        f"**PJ:** {equipo['pj']} | **PG:** {equipo['pg']} | **PE:** {equipo['pe']} | **PP:** {equipo['pp']}\n"
        f"**GF:** {equipo['gf']} | **GC:** {equipo['gc']} | **DG:** {equipo['gf'] - equipo['gc']} | **Pts:** {equipo['puntos']}"
    )
    emb.add_field(name="📊 Estadísticas", value=stats, inline=False)
    if jugadores:
        por_pos = {}
        for j in jugadores:
            por_pos.setdefault(j["posicion"], []).append(f"`{j['dorsal']}` {j['nombre']}")
        for pos, lista in por_pos.items():
            emb.add_field(name=pos, value="\n".join(lista), inline=True)
    else:
        emb.add_field(name="Plantilla", value="Sin jugadores. Usa `/inscribir_jugador`.", inline=False)
    await interaction.response.send_message(embed=emb)


@tree.command(name="ver_equipo", description="Ver el equipo de otro DT")
@app_commands.describe(nombre="Nombre del equipo a consultar")
async def ver_equipo(interaction: discord.Interaction, nombre: str):
    equipo = await get_equipo_by_nombre(nombre)
    if not equipo:
        await interaction.response.send_message(embed=embed_error(f"No existe el equipo **{nombre}**."), ephemeral=True)
        return
    jugadores = await get_plantilla(equipo["id"])
    emb = embed_info(f"🏟️ {equipo['nombre']}", f"DT: **{equipo['dt_nombre']}**")
    stats = (
        f"**Pts:** {equipo['puntos']} | **PJ:** {equipo['pj']} | **PG:** {equipo['pg']} | **PE:** {equipo['pe']} | **PP:** {equipo['pp']}\n"
        f"**GF:** {equipo['gf']} | **GC:** {equipo['gc']} | **DG:** {equipo['gf'] - equipo['gc']}"
    )
    emb.add_field(name="📊 Estadísticas", value=stats, inline=False)
    if jugadores:
        por_pos = {}
        for j in jugadores:
            por_pos.setdefault(j["posicion"], []).append(f"`{j['dorsal']}` {j['nombre']}")
        for pos, lista in por_pos.items():
            emb.add_field(name=pos, value="\n".join(lista), inline=True)
    else:
        emb.add_field(name="Plantilla", value="Sin jugadores aún.", inline=False)
    await interaction.response.send_message(embed=emb)


# ══════════════════════════════════════════════════════════════
#  JUGADORES
# ══════════════════════════════════════════════════════════════

@tree.command(name="inscribir_jugador", description="Añade un jugador a tu plantilla")
@app_commands.describe(nombre="Nombre completo del jugador", posicion="Posición del jugador", dorsal="Número de camiseta")
@app_commands.choices(posicion=[
    app_commands.Choice(name="Portero (POR)", value="POR"),
    app_commands.Choice(name="Defensa (DEF)", value="DEF"),
    app_commands.Choice(name="Mediocampista (MED)", value="MED"),
    app_commands.Choice(name="Delantero (DEL)", value="DEL"),
])
async def inscribir_jugador_cmd(interaction: discord.Interaction, nombre: str, posicion: str, dorsal: int):
    equipo = await get_equipo_by_discord(str(interaction.user.id))
    if not equipo:
        await interaction.response.send_message(embed=embed_error("No tienes equipo. Usa `/registrar` primero."), ephemeral=True)
        return
    plantilla = await get_plantilla(equipo["id"])
    if any(j["dorsal"] == dorsal for j in plantilla):
        await interaction.response.send_message(embed=embed_error(f"El dorsal **{dorsal}** ya está ocupado."), ephemeral=True)
        return
    if len(plantilla) >= 25:
        await interaction.response.send_message(embed=embed_error("Ya tienes 25 jugadores. Libera alguno primero."), ephemeral=True)
        return
    await inscribir_jugador(nombre, posicion, equipo["id"], dorsal)
    emb = embed_ok("✅ Jugador inscrito", f"**{nombre}** ({posicion}) · Dorsal #{dorsal}\nEquipo: {equipo['nombre']}")
    await interaction.response.send_message(embed=emb)


@tree.command(name="liberar_jugador", description="Libera un jugador de tu plantilla al mercado libre")
@app_commands.describe(nombre="Nombre del jugador a liberar")
async def liberar_jugador_cmd(interaction: discord.Interaction, nombre: str):
    equipo = await get_equipo_by_discord(str(interaction.user.id))
    if not equipo:
        await interaction.response.send_message(embed=embed_error("No tienes equipo."), ephemeral=True)
        return
    jugador = await get_jugador_by_nombre(nombre)
    if not jugador or jugador["equipo_id"] != equipo["id"]:
        await interaction.response.send_message(embed=embed_error(f"No tienes ningún jugador llamado **{nombre}**."), ephemeral=True)
        return
    await liberar_jugador(jugador["id"])
    emb = embed_ok("🔓 Jugador liberado", f"**{nombre}** ahora está en el mercado libre.")
    await interaction.response.send_message(embed=emb)


@tree.command(name="fichar", description="Ficha un jugador libre del mercado")
@app_commands.describe(nombre="Nombre del jugador a fichar", dorsal="Dorsal que le asignarás")
async def fichar_cmd(interaction: discord.Interaction, nombre: str, dorsal: int):
    equipo = await get_equipo_by_discord(str(interaction.user.id))
    if not equipo:
        await interaction.response.send_message(embed=embed_error("No tienes equipo."), ephemeral=True)
        return
    jugador = await get_jugador_by_nombre(nombre)
    if not jugador or (jugador["equipo_id"] is not None and jugador["libre"] == 0):
        await interaction.response.send_message(embed=embed_error(f"**{nombre}** no está en el mercado libre."), ephemeral=True)
        return
    plantilla = await get_plantilla(equipo["id"])
    if any(j["dorsal"] == dorsal for j in plantilla):
        await interaction.response.send_message(embed=embed_error(f"El dorsal **{dorsal}** ya está ocupado."), ephemeral=True)
        return
    await fichar_jugador(jugador["id"], equipo["id"])
    import aiosqlite
    from database import DB_PATH
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE jugadores SET dorsal=? WHERE id=?", (dorsal, jugador["id"]))
        await db.commit()
    emb = embed_ok("🤝 ¡Fichaje completado!", f"**{nombre}** ({jugador['posicion']}) llega a **{equipo['nombre']}** con el dorsal #{dorsal}.")
    await interaction.response.send_message(embed=emb)


@tree.command(name="mercado", description="Muestra los jugadores libres disponibles para fichar")
async def mercado(interaction: discord.Interaction):
    libres = await get_jugadores_libres()
    if not libres:
        await interaction.response.send_message(embed=embed_info("🏪 Mercado libre", "No hay jugadores disponibles."), ephemeral=True)
        return
    emb = embed_info("🏪 Mercado libre", f"**{len(libres)}** jugadores disponibles")
    por_pos = {}
    for j in libres:
        por_pos.setdefault(j["posicion"], []).append(f"• {j['nombre']}")
    for pos, lista in por_pos.items():
        emb.add_field(name=pos, value="\n".join(lista[:10]), inline=True)
    await interaction.response.send_message(embed=emb)


# ══════════════════════════════════════════════════════════════
#  FICHAJES CON DINERO
# ══════════════════════════════════════════════════════════════

@tree.command(name="ofertar", description="Haz una oferta económica por un jugador de otro equipo")
@app_commands.describe(
    equipo_rival="Rol del equipo rival",
    jugador="Nombre del jugador que quieres fichar",
    monto="Cantidad en dólares que ofreces (ej: 5000000)"
)
async def ofertar(interaction: discord.Interaction, equipo_rival: discord.Role, jugador: str, monto: int):
    equipo_comprador = await get_equipo_by_discord(str(interaction.user.id))
    if not equipo_comprador:
        await interaction.response.send_message(embed=embed_error("No tienes equipo registrado."), ephemeral=True)
        return

    if monto <= 0:
        await interaction.response.send_message(embed=embed_error("El monto debe ser mayor a $0."), ephemeral=True)
        return

    if equipo_comprador["presupuesto"] < monto:
        await interaction.response.send_message(
            embed=embed_error(f"No tienes suficiente presupuesto.\nDisponible: **{fmt_dinero(equipo_comprador['presupuesto'])}**"),
            ephemeral=True
        )
        return

    equipo_vendedor = await get_equipo_by_rol(str(equipo_rival.id))
    if not equipo_vendedor:
        await interaction.response.send_message(embed=embed_error(f"**{equipo_rival.name}** no está registrado en la liga."), ephemeral=True)
        return

    if equipo_comprador["id"] == equipo_vendedor["id"]:
        await interaction.response.send_message(embed=embed_error("No puedes hacerte una oferta a ti mismo."), ephemeral=True)
        return

    jug = await get_jugador_by_nombre(jugador)
    if not jug or jug["equipo_id"] != equipo_vendedor["id"]:
        await interaction.response.send_message(
            embed=embed_error(f"**{equipo_rival.name}** no tiene ningún jugador llamado **{jugador}**."),
            ephemeral=True
        )
        return

    oferta_id = await crear_oferta(jug["id"], equipo_comprador["id"], equipo_vendedor["id"], monto)

    emb = embed_ok(
        "💸 Oferta enviada",
        f"**{equipo_comprador['nombre']}** ofrece **{fmt_dinero(monto)}** por **{jugador}** ({jug['posicion']})\n"
        f"Al equipo: **{equipo_vendedor['nombre']}**\n\n"
        f"ID de la oferta: `{oferta_id}`"
    )
    await interaction.response.send_message(embed=emb)

    # Notificar al DT rival por DM
    dt_rival = interaction.guild.get_member(int(equipo_vendedor["discord_id"]))
    if dt_rival:
        try:
            notif = discord.Embed(
                title="📨 ¡Tienes una oferta de fichaje!",
                description=(
                    f"**{equipo_comprador['nombre']}** ofrece **{fmt_dinero(monto)}** por tu jugador **{jugador}** ({jug['posicion']})\n\n"
                    f"Usa `/mis_ofertas` para verla y `/aceptar_oferta id: {oferta_id}` para aceptar\n"
                    f"o `/rechazar_oferta id: {oferta_id}` para rechazar."
                ),
                color=COLOR_AMARILLO
            )
            await dt_rival.send(embed=notif)
        except:
            pass


@tree.command(name="mis_ofertas", description="Ver las ofertas de fichaje pendientes para tu equipo")
async def mis_ofertas(interaction: discord.Interaction):
    equipo = await get_equipo_by_discord(str(interaction.user.id))
    if not equipo:
        await interaction.response.send_message(embed=embed_error("No tienes equipo."), ephemeral=True)
        return
    ofertas = await get_ofertas_pendientes(equipo["id"])
    if not ofertas:
        await interaction.response.send_message(embed=embed_info("📨 Ofertas pendientes", "No tienes ofertas pendientes."), ephemeral=True)
        return
    emb = embed_info("📨 Ofertas pendientes", f"Tienes **{len(ofertas)}** oferta(s):")
    for o in ofertas:
        jug = await get_jugador_by_id(o["jugador_id"])
        eq_comprador = await get_equipo_by_id(o["equipo_comprador_id"])
        emb.add_field(
            name=f"Oferta ID: {o['id']}",
            value=(
                f"**{eq_comprador['nombre']}** ofrece **{fmt_dinero(o['monto'])}**\n"
                f"por tu jugador **{jug['nombre']}** ({jug['posicion']})\n"
                f"✅ `/aceptar_oferta id: {o['id']}` · ❌ `/rechazar_oferta id: {o['id']}`"
            ),
            inline=False
        )
    await interaction.response.send_message(embed=emb, ephemeral=True)


@tree.command(name="aceptar_oferta", description="Acepta una oferta de fichaje")
@app_commands.describe(id="ID de la oferta")
async def aceptar_oferta_cmd(interaction: discord.Interaction, id: int):
    equipo = await get_equipo_by_discord(str(interaction.user.id))
    if not equipo:
        await interaction.response.send_message(embed=embed_error("No tienes equipo."), ephemeral=True)
        return
    oferta = await get_oferta(id)
    if not oferta or oferta["equipo_vendedor_id"] != equipo["id"]:
        await interaction.response.send_message(embed=embed_error("Esta oferta no existe o no es para tu equipo."), ephemeral=True)
        return
    if oferta["estado"] != "pendiente":
        await interaction.response.send_message(embed=embed_error("Esta oferta ya fue respondida."), ephemeral=True)
        return
    ok = await aceptar_oferta(id)
    if not ok:
        await interaction.response.send_message(embed=embed_error("No se pudo completar la transferencia."), ephemeral=True)
        return
    jug = await get_jugador_by_id(oferta["jugador_id"])
    eq_comprador = await get_equipo_by_id(oferta["equipo_comprador_id"])
    eq_vendedor = await get_equipo_by_id(oferta["equipo_vendedor_id"])
    emb = embed_ok(
        "✅ ¡Transferencia completada!",
        f"**{jug['nombre']}** ({jug['posicion']}) ha sido transferido a **{eq_comprador['nombre']}**\n"
        f"💰 **{eq_vendedor['nombre']}** recibe: **{fmt_dinero(oferta['monto'])}**\n"
        f"💸 **{eq_comprador['nombre']}** paga: **{fmt_dinero(oferta['monto'])}**\n\n"
        f"Presupuesto restante de {eq_vendedor['nombre']}: **{fmt_dinero(eq_vendedor['presupuesto'] + oferta['monto'])}**"
    )
    await interaction.response.send_message(embed=emb)

    # Notificar al comprador
    dt_comprador = interaction.guild.get_member(int(eq_comprador["discord_id"]))
    if dt_comprador:
        try:
            notif = embed_ok(
                "🎉 ¡Oferta aceptada!",
                f"**{eq_vendedor['nombre']}** aceptó tu oferta de **{fmt_dinero(oferta['monto'])}**\n"
                f"**{jug['nombre']}** ya es parte de tu equipo."
            )
            await dt_comprador.send(embed=notif)
        except:
            pass


@tree.command(name="rechazar_oferta", description="Rechaza una oferta de fichaje")
@app_commands.describe(id="ID de la oferta")
async def rechazar_oferta_cmd(interaction: discord.Interaction, id: int):
    equipo = await get_equipo_by_discord(str(interaction.user.id))
    if not equipo:
        await interaction.response.send_message(embed=embed_error("No tienes equipo."), ephemeral=True)
        return
    oferta = await get_oferta(id)
    if not oferta or oferta["equipo_vendedor_id"] != equipo["id"]:
        await interaction.response.send_message(embed=embed_error("Esta oferta no existe o no es para tu equipo."), ephemeral=True)
        return
    if oferta["estado"] != "pendiente":
        await interaction.response.send_message(embed=embed_error("Esta oferta ya fue respondida."), ephemeral=True)
        return
    await rechazar_oferta(id)
    jug = await get_jugador_by_id(oferta["jugador_id"])
    eq_comprador = await get_equipo_by_id(oferta["equipo_comprador_id"])
    emb = embed_error(f"Oferta de **{eq_comprador['nombre']}** por **{jug['nombre']}** rechazada.")
    await interaction.response.send_message(embed=emb)

    # Notificar al comprador
    dt_comprador = interaction.guild.get_member(int(eq_comprador["discord_id"]))
    if dt_comprador:
        try:
            notif = discord.Embed(
                title="❌ Oferta rechazada",
                description=f"**{equipo['nombre']}** rechazó tu oferta de **{fmt_dinero(oferta['monto'])}** por **{jug['nombre']}**.",
                color=COLOR_ERROR
            )
            await dt_comprador.send(embed=notif)
        except:
            pass


# ══════════════════════════════════════════════════════════════
#  LIGA
# ══════════════════════════════════════════════════════════════

@tree.command(name="tabla", description="Muestra la tabla de posiciones de la liga")
async def tabla(interaction: discord.Interaction):
    equipos = await get_todos_equipos()
    if not equipos:
        await interaction.response.send_message(embed=embed_info("📊 Tabla de posiciones", "Aún no hay equipos registrados."))
        return
    emb = embed_info("📊 Tabla de posiciones")
    lineas = ["```"]
    lineas.append(f"{'#':<3} {'Equipo':<20} {'PJ':>3} {'PG':>3} {'PE':>3} {'PP':>3} {'GF':>3} {'GC':>3} {'DG':>4} {'Pts':>4}")
    lineas.append("─" * 58)
    for i, e in enumerate(equipos, 1):
        dg = e["gf"] - e["gc"]
        lineas.append(f"{i:<3} {e['nombre'][:20]:<20} {e['pj']:>3} {e['pg']:>3} {e['pe']:>3} {e['pp']:>3} {e['gf']:>3} {e['gc']:>3} {dg:>+4} {e['puntos']:>4}")
    lineas.append("```")
    emb.description = "\n".join(lineas)
    await interaction.response.send_message(embed=emb)


@tree.command(name="fixture", description="Muestra el fixture de una jornada o los próximos partidos")
@app_commands.describe(jornada="Número de jornada (opcional)")
async def fixture(interaction: discord.Interaction, jornada: int = None):
    partidos = await get_fixture(jornada)
    if not partidos:
        msg = f"No hay partidos en la jornada {jornada}." if jornada else "No hay partidos pendientes."
        await interaction.response.send_message(embed=embed_info("📅 Fixture", msg))
        return
    titulo = f"📅 Jornada {jornada}" if jornada else "📅 Próximos partidos"
    emb = embed_info(titulo)
    jornadas = {}
    for p in partidos:
        jornadas.setdefault(p["jornada"], []).append(p)
    for j, lista in sorted(jornadas.items()):
        lineas = []
        for p in lista:
            if p["jugado"]:
                lineas.append(f"**{p['local_nombre']}** {p['goles_local']} – {p['goles_visitante']} **{p['visitante_nombre']}**")
            else:
                lineas.append(f"{p['local_nombre']}  vs  {p['visitante_nombre']}  *(ID: {p['id']})*")
        emb.add_field(name=f"Jornada {j}", value="\n".join(lineas), inline=False)
    await interaction.response.send_message(embed=emb)


# ══════════════════════════════════════════════════════════════
#  ADMIN
# ══════════════════════════════════════════════════════════════

@tree.command(name="resultado", description="[Admin] Carga el resultado de un partido")
@app_commands.describe(partido_id="ID del partido", goles_local="Goles del local", goles_visitante="Goles del visitante")
async def resultado(interaction: discord.Interaction, partido_id: int, goles_local: int, goles_visitante: int):
    if not es_admin(interaction):
        await interaction.response.send_message(embed=embed_error("Solo los admins pueden cargar resultados."), ephemeral=True)
        return
    ok = await cargar_resultado(partido_id, goles_local, goles_visitante)
    if not ok:
        await interaction.response.send_message(embed=embed_error(f"No encontré el partido con ID **{partido_id}**."), ephemeral=True)
        return
    import aiosqlite
    from database import DB_PATH
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT p.*, el.nombre as ln, ev.nombre as vn FROM partidos p JOIN equipos el ON p.local_id = el.id JOIN equipos ev ON p.visitante_id = ev.id WHERE p.id = ?", (partido_id,)
        ) as cur:
            p = await cur.fetchone()
    emb = embed_ok("⚽ Resultado cargado", f"**{p['ln']}** {goles_local} – {goles_visitante} **{p['vn']}**\nJornada {p['jornada']}")
    await interaction.response.send_message(embed=emb)


@tree.command(name="generar_fixture", description="[Admin] Genera el fixture completo de ida y vuelta")
async def generar_fixture(interaction: discord.Interaction):
    if not es_admin(interaction):
        await interaction.response.send_message(embed=embed_error("Solo los admins pueden generar el fixture."), ephemeral=True)
        return
    await interaction.response.defer()
    total = await generar_fixture_automatico()
    if total == 0:
        await interaction.followup.send(embed=embed_error("Necesitas al menos 2 equipos registrados."))
        return
    equipos = await get_todos_equipos()
    emb = embed_ok("📅 Fixture generado", f"Se crearon **{total} partidos** para **{len(equipos)} equipos**.\nUsa `/fixture` para verlo.")
    await interaction.followup.send(embed=emb)


@tree.command(name="agregar_jugador_libre", description="[Admin] Agrega un jugador al mercado libre")
@app_commands.describe(nombre="Nombre del jugador", posicion="Posición del jugador")
@app_commands.choices(posicion=[
    app_commands.Choice(name="Portero (POR)", value="POR"),
    app_commands.Choice(name="Defensa (DEF)", value="DEF"),
    app_commands.Choice(name="Mediocampista (MED)", value="MED"),
    app_commands.Choice(name="Delantero (DEL)", value="DEL"),
])
async def agregar_jugador_libre(interaction: discord.Interaction, nombre: str, posicion: str):
    if not es_admin(interaction):
        await interaction.response.send_message(embed=embed_error("Solo los admins pueden hacer esto."), ephemeral=True)
        return
    import aiosqlite
    from database import DB_PATH
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT INTO jugadores (nombre, posicion, libre, dorsal) VALUES (?, ?, 1, 0)", (nombre, posicion))
        await db.commit()
    emb = embed_ok("✅ Jugador añadido al mercado", f"**{nombre}** ({posicion}) ya está disponible.")
    await interaction.response.send_message(embed=emb)


@tree.command(name="eliminar_mi_equipo", description="Elimina tu propio equipo y plantilla de la liga")
async def eliminar_mi_equipo(interaction: discord.Interaction):
    equipo = await get_equipo_by_discord(str(interaction.user.id))
    if not equipo:
        await interaction.response.send_message(embed=embed_error("No tienes ningún equipo registrado."), ephemeral=True)
        return
    import aiosqlite
    from database import DB_PATH
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM jugadores WHERE equipo_id = ?", (equipo["id"],))
        await db.execute("DELETE FROM ofertas WHERE equipo_comprador_id = ? OR equipo_vendedor_id = ?", (equipo["id"], equipo["id"]))
        await db.execute("DELETE FROM equipos WHERE id = ?", (equipo["id"],))
        await db.commit()
    emb = embed_ok("🗑️ Equipo eliminado", f"Tu equipo **{equipo['nombre']}** y su plantilla han sido eliminados.\nPuedes volver a registrarte con `/registrar`.")
    await interaction.response.send_message(embed=emb)


@tree.command(name="resetear_equipo", description="[Admin] Elimina un equipo y su plantilla de la liga")
@app_commands.describe(rol="Rol del equipo a eliminar")
async def resetear_equipo(interaction: discord.Interaction, rol: discord.Role):
    if not es_admin(interaction):
        await interaction.response.send_message(embed=embed_error("Solo los admins pueden hacer esto."), ephemeral=True)
        return
    equipo = await get_equipo_by_rol(str(rol.id))
    if not equipo:
        await interaction.response.send_message(embed=embed_error(f"No existe ningún equipo con el rol {rol.mention}."), ephemeral=True)
        return
    import aiosqlite
    from database import DB_PATH
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM jugadores WHERE equipo_id = ?", (equipo["id"],))
        await db.execute("DELETE FROM ofertas WHERE equipo_comprador_id = ? OR equipo_vendedor_id = ?", (equipo["id"], equipo["id"]))
        await db.execute("DELETE FROM equipos WHERE id = ?", (equipo["id"],))
        await db.commit()
    emb = embed_ok("🗑️ Equipo eliminado", f"El equipo **{equipo['nombre']}** y su plantilla han sido eliminados.\nEl DT puede volver a registrarse con `/registrar`.")
    await interaction.response.send_message(embed=emb)


@tree.command(name="resetear_liga", description="[Admin] Borra todos los datos y reinicia la liga")
async def resetear_liga(interaction: discord.Interaction):
    if not es_admin(interaction):
        await interaction.response.send_message(embed=embed_error("Solo los admins pueden hacer esto."), ephemeral=True)
        return
    import aiosqlite
    from database import DB_PATH
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("DELETE FROM partidos; DELETE FROM jugadores; DELETE FROM equipos; DELETE FROM ofertas;")
        await db.commit()
    await interaction.response.send_message(embed=embed_ok("🔄 Liga reseteada", "Todos los datos han sido borrados. ¡Nueva temporada!"))


@tree.command(name="ayuda", description="Lista todos los comandos disponibles")
async def ayuda(interaction: discord.Interaction):
    emb = discord.Embed(title="📖 Comandos del bot de liga", color=COLOR_INFO)
    emb.add_field(name="⚽ Equipos", value=(
        "`/registrar` — Registrate como DT eligiendo tu rol\n"
        "`/mi_equipo` — Ver tu equipo, plantilla y presupuesto\n"
        "`/ver_equipo` — Ver el equipo de otro DT\n"
        "`/tabla` — Tabla de posiciones\n"
        "`/fixture` — Ver el fixture"
    ), inline=False)
    emb.add_field(name="🤝 Jugadores", value=(
        "`/inscribir_jugador` — Añadir jugador a tu plantilla\n"
        "`/liberar_jugador` — Liberar jugador al mercado\n"
        "`/fichar` — Fichar jugador del mercado libre\n"
        "`/mercado` — Ver jugadores libres disponibles"
    ), inline=False)
    emb.add_field(name="💸 Fichajes con dinero", value=(
        "`/ofertar` — Hacer una oferta por un jugador del rival\n"
        "`/mis_ofertas` — Ver ofertas pendientes recibidas\n"
        "`/aceptar_oferta` — Aceptar una oferta\n"
        "`/rechazar_oferta` — Rechazar una oferta"
    ), inline=False)
    emb.add_field(name="🔧 Admin", value=(
        "`/resultado` — Cargar resultado de un partido\n"
        "`/generar_fixture` — Generar fixture completo\n"
        "`/agregar_jugador_libre` — Añadir jugador al mercado\n"
        "`/resetear_liga` — Reiniciar toda la liga"
    ), inline=False)
    await interaction.response.send_message(embed=emb, ephemeral=True)


@bot.event
async def on_ready():
    await init_db()
    await tree.sync()
    print(f"✅ Bot conectado como {bot.user} | {len(bot.guilds)} servidor(es)")
    await bot.change_presence(activity=discord.Game(name="⚽ Liga activa | /ayuda"))

@bot.event
async def on_command_error(ctx, error):
    pass

if __name__ == "__main__":
    bot.run(TOKEN)
