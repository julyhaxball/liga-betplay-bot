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
    responder_oferta, ejecutar_intercambio, get_jugador_by_id
)

TOKEN = os.getenv("DISCORD_TOKEN", "MTUwODYyMTYzMjI4Mzg2OTI1NQ.GVjqKr.hcv0ynVgxIgPcuVgQHgBWyD7CGOieU__62oW-s")
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

# ══════════════════════════════════════════════════════════════
#  EQUIPOS
# ══════════════════════════════════════════════════════════════

@tree.command(name="registrar", description="Regístrate como DT eligiendo el rol de tu equipo")
@app_commands.describe(rol="El rol de tu equipo en el servidor")
async def registrar(interaction: discord.Interaction, rol: discord.Role):
    existente = await get_equipo_by_discord(str(interaction.user.id))
    if existente:
        await interaction.response.send_message(
            embed=embed_error(f"Ya tienes un equipo registrado: **{existente['nombre']}**"),
            ephemeral=True
        )
        return

    por_rol = await get_equipo_by_rol(str(rol.id))
    if por_rol:
        await interaction.response.send_message(
            embed=embed_error(f"El rol **{rol.name}** ya está registrado por otro DT."),
            ephemeral=True
        )
        return

    await crear_equipo(
        str(interaction.user.id),
        rol.name,
        interaction.user.display_name,
        str(rol.id)
    )

    # Asignar el rol al DT si no lo tiene
    if rol not in interaction.user.roles:
        try:
            await interaction.user.add_roles(rol)
        except:
            pass

    emb = embed_ok(
        "⚽ ¡Equipo registrado!",
        f"**{rol.name}** ha sido inscrito en la liga.\n"
        f"DT: {interaction.user.mention} {rol.mention}\n\n"
        f"Ahora puedes añadir jugadores con `/inscribir_jugador`."
    )
    await interaction.response.send_message(embed=emb)


@tree.command(name="mi_equipo", description="Muestra la información y plantilla de tu equipo")
async def mi_equipo(interaction: discord.Interaction):
    equipo = await get_equipo_by_discord(str(interaction.user.id))
    if not equipo:
        await interaction.response.send_message(
            embed=embed_error("No tienes ningún equipo registrado. Usa `/registrar`."),
            ephemeral=True
        )
        return
    jugadores = await get_plantilla(equipo["id"])
    emb = embed_info(f"🏟️ {equipo['nombre']}", f"DT: **{equipo['dt_nombre']}**")
    stats = (
        f"**PJ:** {equipo['pj']} | **PG:** {equipo['pg']} | "
        f"**PE:** {equipo['pe']} | **PP:** {equipo['pp']}\n"
        f"**GF:** {equipo['gf']} | **GC:** {equipo['gc']} | "
        f"**DG:** {equipo['gf'] - equipo['gc']} | **Pts:** {equipo['puntos']}"
    )
    emb.add_field(name="Estadísticas", value=stats, inline=False)
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
        await interaction.response.send_message(
            embed=embed_error(f"No existe ningún equipo llamado **{nombre}**."),
            ephemeral=True
        )
        return
    jugadores = await get_plantilla(equipo["id"])
    emb = embed_info(f"🏟️ {equipo['nombre']}", f"DT: **{equipo['dt_nombre']}**")
    stats = (
        f"**Pts:** {equipo['puntos']} | **PJ:** {equipo['pj']} | "
        f"**PG:** {equipo['pg']} | **PE:** {equipo['pe']} | **PP:** {equipo['pp']}\n"
        f"**GF:** {equipo['gf']} | **GC:** {equipo['gc']} | **DG:** {equipo['gf'] - equipo['gc']}"
    )
    emb.add_field(name="Estadísticas", value=stats, inline=False)
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
        await interaction.response.send_message(embed=embed_error(f"**{nombre}** no está disponible en el mercado libre."), ephemeral=True)
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
#  COMERCIOS
# ══════════════════════════════════════════════════════════════

@tree.command(name="ofrecer_cambio", description="Ofrece un intercambio de jugadores a otro equipo")
@app_commands.describe(
    mi_jugador="Nombre del jugador tuyo que ofreces",
    equipo_rival="Rol del equipo rival",
    su_jugador="Nombre del jugador rival que quieres"
)
async def ofrecer_cambio(interaction: discord.Interaction, mi_jugador: str, equipo_rival: discord.Role, su_jugador: str):
    equipo_origen = await get_equipo_by_discord(str(interaction.user.id))
    if not equipo_origen:
        await interaction.response.send_message(embed=embed_error("No tienes equipo registrado."), ephemeral=True)
        return

    equipo_destino = await get_equipo_by_rol(str(equipo_rival.id))
    if not equipo_destino:
        await interaction.response.send_message(embed=embed_error(f"El equipo **{equipo_rival.name}** no está registrado en la liga."), ephemeral=True)
        return

    if equipo_origen["id"] == equipo_destino["id"]:
        await interaction.response.send_message(embed=embed_error("No puedes hacerte un comercio a ti mismo."), ephemeral=True)
        return

    jug_origen = await get_jugador_by_nombre(mi_jugador)
    if not jug_origen or jug_origen["equipo_id"] != equipo_origen["id"]:
        await interaction.response.send_message(embed=embed_error(f"No tienes ningún jugador llamado **{mi_jugador}**."), ephemeral=True)
        return

    jug_destino = await get_jugador_by_nombre(su_jugador)
    if not jug_destino or jug_destino["equipo_id"] != equipo_destino["id"]:
        await interaction.response.send_message(embed=embed_error(f"**{equipo_rival.name}** no tiene ningún jugador llamado **{su_jugador}**."), ephemeral=True)
        return

    oferta_id = await crear_oferta(jug_origen["id"], jug_destino["id"], equipo_origen["id"], equipo_destino["id"])

    emb = embed_info(
        "🔄 Propuesta de intercambio enviada",
        f"**{equipo_origen['nombre']}** ofrece **{mi_jugador}** ({jug_origen['posicion']})\n"
        f"a cambio de **{su_jugador}** ({jug_destino['posicion']}) de **{equipo_destino['nombre']}**\n\n"
        f"El DT rival puede aceptar o rechazar con `/responder_cambio id: {oferta_id}`"
    )
    await interaction.response.send_message(embed=emb)

    # Notificar al DT rival si está en el servidor
    dt_rival = interaction.guild.get_member(int(equipo_destino["discord_id"]))
    if dt_rival:
        try:
            notif = embed_info(
                "📨 Tienes una propuesta de intercambio",
                f"**{equipo_origen['nombre']}** te ofrece **{mi_jugador}** ({jug_origen['posicion']})\n"
                f"a cambio de tu jugador **{su_jugador}** ({jug_destino['posicion']})\n\n"
                f"Usa `/responder_cambio id: {oferta_id} aceptar: Sí` para aceptar\n"
                f"o `/responder_cambio id: {oferta_id} aceptar: No` para rechazar"
            )
            await dt_rival.send(embed=notif)
        except:
            pass


@tree.command(name="responder_cambio", description="Acepta o rechaza una propuesta de intercambio")
@app_commands.describe(id="ID de la propuesta", aceptar="¿Aceptas el intercambio?")
@app_commands.choices(aceptar=[
    app_commands.Choice(name="Sí, acepto", value="si"),
    app_commands.Choice(name="No, rechazo", value="no"),
])
async def responder_cambio(interaction: discord.Interaction, id: int, aceptar: str):
    equipo = await get_equipo_by_discord(str(interaction.user.id))
    if not equipo:
        await interaction.response.send_message(embed=embed_error("No tienes equipo registrado."), ephemeral=True)
        return

    oferta = await get_oferta(id)
    if not oferta:
        await interaction.response.send_message(embed=embed_error(f"No existe ninguna propuesta con ID **{id}**."), ephemeral=True)
        return

    if oferta["equipo_destino_id"] != equipo["id"]:
        await interaction.response.send_message(embed=embed_error("Esta propuesta no es para tu equipo."), ephemeral=True)
        return

    if oferta["estado"] != "pendiente":
        await interaction.response.send_message(embed=embed_error("Esta propuesta ya fue respondida."), ephemeral=True)
        return

    if aceptar == "si":
        await responder_oferta(id, True)
        await ejecutar_intercambio(id)

        jug_origen = await get_jugador_by_id(oferta["jugador_origen_id"])
        jug_destino = await get_jugador_by_id(oferta["jugador_destino_id"])
        equipo_origen = await get_equipo_by_id(oferta["equipo_origen_id"])

        emb = embed_ok(
            "✅ ¡Intercambio completado!",
            f"**{jug_origen['nombre']}** → **{equipo['nombre']}**\n"
            f"**{jug_destino['nombre']}** → **{equipo_origen['nombre']}**"
        )
        await interaction.response.send_message(embed=emb)
    else:
        await responder_oferta(id, False)
        equipo_origen = await get_equipo_by_id(oferta["equipo_origen_id"])
        emb = embed_error(f"Propuesta de **{equipo_origen['nombre']}** rechazada.")
        await interaction.response.send_message(embed=emb)


@tree.command(name="mis_ofertas", description="Ver las propuestas de intercambio pendientes para tu equipo")
async def mis_ofertas(interaction: discord.Interaction):
    equipo = await get_equipo_by_discord(str(interaction.user.id))
    if not equipo:
        await interaction.response.send_message(embed=embed_error("No tienes equipo."), ephemeral=True)
        return

    ofertas = await get_ofertas_pendientes(equipo["id"])
    if not ofertas:
        await interaction.response.send_message(embed=embed_info("📨 Propuestas pendientes", "No tienes propuestas pendientes."), ephemeral=True)
        return

    emb = embed_info("📨 Propuestas pendientes", f"Tienes **{len(ofertas)}** propuesta(s):")
    for o in ofertas:
        jug_origen = await get_jugador_by_id(o["jugador_origen_id"])
        jug_destino = await get_jugador_by_id(o["jugador_destino_id"])
        eq_origen = await get_equipo_by_id(o["equipo_origen_id"])
        emb.add_field(
            name=f"Propuesta ID: {o['id']}",
            value=f"**{eq_origen['nombre']}** te ofrece **{jug_origen['nombre']}** ({jug_origen['posicion']})\n"
                  f"a cambio de tu jugador **{jug_destino['nombre']}** ({jug_destino['posicion']})\n"
                  f"Usa `/responder_cambio id: {o['id']}`",
            inline=False
        )
    await interaction.response.send_message(embed=emb, ephemeral=True)


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
    emb = embed_ok("✅ Jugador añadido al mercado", f"**{nombre}** ({posicion}) ya está disponible para fichar.")
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
        "`/mi_equipo` — Ver tu equipo y plantilla\n"
        "`/ver_equipo` — Ver el equipo de otro DT\n"
        "`/tabla` — Tabla de posiciones\n"
        "`/fixture` — Ver el fixture"
    ), inline=False)
    emb.add_field(name="🤝 Jugadores y fichajes", value=(
        "`/inscribir_jugador` — Añadir jugador a tu plantilla\n"
        "`/liberar_jugador` — Liberar jugador al mercado\n"
        "`/fichar` — Fichar jugador del mercado libre\n"
        "`/mercado` — Ver jugadores libres disponibles"
    ), inline=False)
    emb.add_field(name="🔄 Comercios", value=(
        "`/ofrecer_cambio` — Proponer intercambio de jugadores\n"
        "`/responder_cambio` — Aceptar o rechazar una propuesta\n"
        "`/mis_ofertas` — Ver propuestas pendientes"
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
