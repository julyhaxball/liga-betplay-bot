import discord
from discord import app_commands
from discord.ext import commands
import os, asyncio, datetime, aiosqlite
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

TOKEN = os.getenv("DISCORD_TOKEN", "TU_TOKEN_AQUI")
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

def es_admin(i): return i.user.guild_permissions.administrator or any(r.name==ADMIN_ROL for r in i.user.roles)
def embed_ok(t,d=""): return discord.Embed(title=t,description=d,color=COLOR_OK)
def embed_error(d): return discord.Embed(title="❌ Error",description=d,color=COLOR_ERROR)
def embed_info(t,d=""): return discord.Embed(title=t,description=d,color=COLOR_INFO)
def fmt(m): return f"${m:,}".replace(",",".")

async def get_equipo_dt_o_sub(discord_id):
    e = await get_equipo_by_discord(discord_id)
    if e: return e, True
    e = await get_equipo_by_sub_dt(discord_id)
    if e: return e, False
    return None, False

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
    except: pass
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
        # Buscar guild del bot
        guild = bot.guilds[0] if bot.guilds else None
        if guild:
            member = guild.get_member(interaction.user.id)
            if member:
                # Asignar rol del equipo
                if self.equipo["rol_id"]:
                    try:
                        rol = guild.get_role(int(self.equipo["rol_id"]))
                        if rol: await member.add_roles(rol)
                    except: pass
                # Quitar rol agente libre
                try:
                    rol_libre = discord.utils.get(guild.roles, name="👤 | Agente Libre")
                    if rol_libre and rol_libre in member.roles:
                        await member.remove_roles(rol_libre)
                except: pass
        emb = embed_ok("✅ ¡Contrato aceptado!", f"Bienvenido a **{self.equipo['nombre']}**, **{self.nombre}**!\nDorsal: #{self.dorsal} · {self.posicion}\n💰 Sueldo semanal: **{fmt(self.sueldo)}**")
        self.stop()
        for item in self.children: item.disabled = True
        await interaction.response.edit_message(embed=emb, view=self)
        # Publicar en #fichajes
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
        # Notificar al DT
        guild = bot.guilds[0] if bot.guilds else None
        if guild and self.equipo["discord_id"]:
            try:
                dt = guild.get_member(int(self.equipo["discord_id"]))
                if dt:
                    await dt.send(embed=embed_error(f"**{self.nombre}** rechazó tu oferta de contrato."))
            except: pass

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
    if any(j["dorsal"]==dorsal for j in plantilla):
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
    except:
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
    # Quitar rol del equipo al jugador
    if equipo["rol_id"] and jugador["discord_id"]:
        try:
            member = interaction.guild.get_member(int(jugador["discord_id"])) if jugador["discord_id"] else None
            rol = interaction.guild.get_role(int(equipo["rol_id"]))
            if member and rol:
                await member.remove_roles(rol)
        except: pass
    emb = embed_ok("🔓 Jugador liberado", f"**{nombre}** ahora está en el mercado libre.")
    await interaction.response.send_message(embed=emb)

@tree.command(name="fichar", description="Ficha un jugador libre del mercado")
@app_commands.describe(nombre="Nombre del jugador", dorsal="Dorsal que le asignarás")
async def fichar_cmd(interaction: discord.Interaction, nombre: str, dorsal: int):
    equipo, _ = await get_equipo_dt_o_sub(str(interaction.user.id))
    if not equipo:
        await interaction.response.send_message(embed=embed_error("No tienes equipo."), ephemeral=True); return
    jugador = await get_jugador_by_nombre(nombre)
    if not jugador or (jugador["equipo_id"] is not None and jugador["libre"]==0):
        await interaction.response.send_message(embed=embed_error(f"**{nombre}** no está en el mercado."), ephemeral=True); return
    plantilla = await get_plantilla(equipo["id"])
    if any(j["dorsal"]==dorsal for j in plantilla):
        await interaction.response.send_message(embed=embed_error(f"El dorsal **{dorsal}** ya está ocupado."), ephemeral=True); return
    await fichar_jugador(jugador["id"], equipo["id"])
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE jugadores SET dorsal=? WHERE id=?", (dorsal, jugador["id"]))
        await db.commit()

    # Asignar rol del equipo y quitar agente libre
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
        except: pass

    emb = embed_ok("🤝 ¡Fichaje completado!", f"**{nombre}** ({jugador['posicion']}) llega a **{equipo['nombre']}** con el dorsal #{dorsal}.")
    await interaction.response.send_message(embed=emb)

    # Publicar en canal fichajes
    canal_fich = discord.utils.get(interaction.guild.text_channels, name="✅・fichajes")
    if canal_fich:
        pos = jugador["posicion"]
        eq_nom = equipo["nombre"]
        emb_f = embed_ok("✅ Nuevo fichaje", f"**{nombre}** ({pos}) · Dorsal #{dorsal}\nEquipo: **{eq_nom}**")
        await canal_fich.send(embed=emb_f)

@tree.command(name="mercado", description="Muestra los jugadores libres disponibles")
async def mercado(interaction: discord.Interaction):
    emb = embed_info("🏪 Mercado libre")

    # Jugadores registrados en BD sin equipo
    libres_bd = await get_jugadores_libres()
    if libres_bd:
        por_pos = {}
        for j in libres_bd:
            por_pos.setdefault(j["posicion"],[]).append(f"• {j['nombre']}")
        for pos, lista in por_pos.items():
            emb.add_field(name=f"Registrados — {pos}", value="\n".join(lista[:8]), inline=True)

    # Solo miembros con rol "agente libre"
    rol_libre = discord.utils.get(interaction.guild.roles, name="👤 | Agente Libre")
    if rol_libre and rol_libre.members:
        agentes = [m.display_name for m in rol_libre.members if not m.bot]
        if agentes:
            chunk = agentes[:25]
            emb.add_field(
                name=f"👥 Agentes libres ({len(agentes)})",
                value="\n".join(f"• {n}" for n in chunk),
                inline=False
            )
            if len(agentes) > 25:
                emb.set_footer(text=f"... y {len(agentes)-25} más")

    if not libres_bd and (not rol_libre or not [m for m in rol_libre.members if not m.bot]):
        emb.description = "No hay jugadores disponibles."

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
    await interaction.response.send_message(embed=emb)
    dt_rival = interaction.guild.get_member(int(equipo_vendedor["discord_id"])) if equipo_vendedor["discord_id"] else None
    if dt_rival:
        try:
            notif = discord.Embed(title="📨 ¡Tienes una oferta!",
                description=f"**{equipo_comprador['nombre']}** ofrece **{fmt(monto)}** por **{jugador}** ({jug['posicion']})\n\nUsa `/mis_ofertas` para verla.",
                color=COLOR_AMARILLO)
            await dt_rival.send(embed=notif)
        except: pass

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
        emb.add_field(name=f"Oferta ID: {o['id']}",
            value=f"**{eq['nombre']}** ofrece **{fmt(o['monto'])}** por **{jug['nombre']}** ({jug['posicion']})\n✅ `/aceptar_oferta id:{o['id']}` · ❌ `/rechazar_oferta id:{o['id']}`",
            inline=False)
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
    # Cambiar rol del jugador
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
        except: pass
    # Generar imagen de fichaje
    try:
        from generar_imagen import generar_fichaje
        buf = generar_fichaje(jug["nombre"], jug["posicion"], jug["dorsal"] or 0, eq_v["nombre"], eq_c["nombre"], oferta["monto"])
        file = discord.File(buf, filename="fichaje.png")
        emb = embed_ok("✅ ¡Transferencia completada!", f"**{jug['nombre']}** → **{eq_c['nombre']}**\n💰 **{fmt(oferta['monto'])}**")
        emb.set_image(url="attachment://fichaje.png")
        await interaction.response.send_message(embed=emb, file=file)

        # Publicar en canal #fichajes
        if interaction.guild:
            canal_fichajes = discord.utils.get(interaction.guild.text_channels, name="✅・fichajes")
            if canal_fichajes:
                from generar_imagen import generar_fichaje as gf2
                buf2 = gf2(jug["nombre"], jug["posicion"], jug["dorsal"] or 0, eq_v["nombre"], eq_c["nombre"], oferta["monto"])
                file2 = discord.File(buf2, filename="fichaje.png")
                emb2 = embed_ok("⚽ ¡Fichaje oficial!", f"**{jug['nombre']}** ({jug['posicion']}) se une a **{eq_c['nombre']}**\n💰 Traspaso: **{fmt(oferta['monto'])}**")
                emb2.set_image(url="attachment://fichaje.png")
                await canal_fichajes.send(embed=emb2, file=file2)
    except Exception as e:
        emb = embed_ok("✅ ¡Transferencia completada!", f"**{jug['nombre']}** → **{eq_c['nombre']}**\n💰 **{fmt(oferta['monto'])}**")
        await interaction.response.send_message(embed=emb)
        # Publicar en #fichajes sin imagen
        if interaction.guild:
            canal_fichajes = discord.utils.get(interaction.guild.text_channels, name="✅・fichajes")
            if canal_fichajes:
                emb2 = embed_ok("⚽ ¡Fichaje oficial!", f"**{jug['nombre']}** ({jug['posicion']}) se une a **{eq_c['nombre']}**\n💰 Traspaso: **{fmt(oferta['monto'])}**")
                await canal_fichajes.send(embed=emb2)
    dt_c = interaction.guild.get_member(int(eq_c["discord_id"])) if eq_c["discord_id"] else None
    if dt_c:
        try:
            await dt_c.send(embed=embed_ok("🎉 ¡Oferta aceptada!", f"**{eq_v['nombre']}** aceptó tu oferta.\n**{jug['nombre']}** ya es tuyo."))
        except: pass

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
        except: pass

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
    await interaction.response.send_message(embed=emb)

# ══════════════════════════════════════════════════════════════
#  LIGA
# ══════════════════════════════════════════════════════════════

@tree.command(name="tabla", description="Tabla de posiciones")
async def tabla(interaction: discord.Interaction):
    equipos = await get_todos_equipos()
    if not equipos:
        await interaction.response.send_message(embed=embed_info("📊 Tabla", "No hay equipos registrados.")); return
    emb = embed_info("📊 Tabla de posiciones")
    lines = ["```", f"{'#':<3} {'Equipo':<20} {'PJ':>3} {'PG':>3} {'PE':>3} {'PP':>3} {'GF':>3} {'GC':>3} {'DG':>4} {'Pts':>4}", "─"*58]
    for i,e in enumerate(equipos,1):
        dg = e["gf"]-e["gc"]
        lines.append(f"{i:<3} {e['nombre'][:20]:<20} {e['pj']:>3} {e['pg']:>3} {e['pe']:>3} {e['pp']:>3} {e['gf']:>3} {e['gc']:>3} {dg:>+4} {e['puntos']:>4}")
    lines.append("```")
    emb.description = "\n".join(lines)
    await interaction.response.send_message(embed=emb)

@tree.command(name="fixture", description="Ver fixture de una jornada o próximos partidos")
@app_commands.describe(jornada="Número de jornada (opcional)")
async def fixture(interaction: discord.Interaction, jornada: int = None):
    partidos = await get_fixture(jornada)
    if not partidos:
        await interaction.response.send_message(embed=embed_info("📅 Fixture", f"No hay partidos{'en jornada '+str(jornada) if jornada else ' pendientes'}.")); return
    emb = embed_info(f"📅 {'Jornada '+str(jornada) if jornada else 'Próximos partidos'}")
    jornadas = {}
    for p in partidos:
        jornadas.setdefault(p["jornada"],[]).append(p)
    for j, lista in sorted(jornadas.items()):
        lines = []
        for p in lista:
            if p["jugado"]: lines.append(f"**{p['local_nombre']}** {p['goles_local']} – {p['goles_visitante']} **{p['visitante_nombre']}**")
            else: lines.append(f"{p['local_nombre']}  vs  {p['visitante_nombre']}  *(ID: {p['id']})*")
        emb.add_field(name=f"Jornada {j}", value="\n".join(lines), inline=False)
    await interaction.response.send_message(embed=emb)

# ══════════════════════════════════════════════════════════════
#  ADMIN
# ══════════════════════════════════════════════════════════════

@tree.command(name="resultado", description="[Admin] Carga el resultado de un partido")
@app_commands.describe(partido_id="ID del partido", goles_local="Goles local", goles_visitante="Goles visitante")
async def resultado(interaction: discord.Interaction, partido_id: int, goles_local: int, goles_visitante: int):
    if not es_admin(interaction):
        await interaction.response.send_message(embed=embed_error("Solo admins."), ephemeral=True); return
    ok = await cargar_resultado(partido_id, goles_local, goles_visitante)
    if not ok:
        await interaction.response.send_message(embed=embed_error(f"No encontré el partido **{partido_id}**."), ephemeral=True); return
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT p.*,el.nombre as ln,ev.nombre as vn FROM partidos p JOIN equipos el ON p.local_id=el.id JOIN equipos ev ON p.visitante_id=ev.id WHERE p.id=?", (partido_id,)) as cur:
            p = await cur.fetchone()
    await interaction.response.send_message(embed=embed_ok("⚽ Resultado cargado", f"**{p['ln']}** {goles_local} – {goles_visitante} **{p['vn']}**\nJornada {p['jornada']}"))

@tree.command(name="generar_fixture", description="[Admin] Genera el fixture completo")
async def generar_fixture(interaction: discord.Interaction):
    if not es_admin(interaction):
        await interaction.response.send_message(embed=embed_error("Solo admins."), ephemeral=True); return
    await interaction.response.defer()
    total = await generar_fixture_automatico()
    if total == 0:
        await interaction.followup.send(embed=embed_error("Necesitas al menos 2 equipos.")); return
    equipos = await get_todos_equipos()
    await interaction.followup.send(embed=embed_ok("📅 Fixture generado", f"**{total} partidos** para **{len(equipos)} equipos**.\nUsa `/fixture` para verlo."))

@tree.command(name="agregar_jugador_libre", description="[Admin] Agrega un jugador al mercado libre")
@app_commands.describe(nombre="Nombre del jugador", posicion="Posición")
@app_commands.choices(posicion=[
    app_commands.Choice(name="Portero (POR)", value="POR"),
    app_commands.Choice(name="Defensa (DEF)", value="DEF"),
    app_commands.Choice(name="Mediocampista (MED)", value="MED"),
    app_commands.Choice(name="Delantero (DEL)", value="DEL"),
])
async def agregar_jugador_libre(interaction: discord.Interaction, nombre: str, posicion: str):
    if not es_admin(interaction):
        await interaction.response.send_message(embed=embed_error("Solo admins."), ephemeral=True); return
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT INTO jugadores (nombre,posicion,libre,dorsal) VALUES (?,?,1,0)", (nombre,posicion))
        await db.commit()
    await interaction.response.send_message(embed=embed_ok("✅ Jugador añadido", f"**{nombre}** ({posicion}) disponible en el mercado."))

@tree.command(name="eliminar_mi_equipo", description="Elimina tu propio equipo de la liga")
async def eliminar_mi_equipo(interaction: discord.Interaction):
    equipo = await get_equipo_by_discord(str(interaction.user.id))
    if not equipo:
        await interaction.response.send_message(embed=embed_error("No tienes equipo."), ephemeral=True); return
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM jugadores WHERE equipo_id=?", (equipo["id"],))
        try:
            await db.execute("DELETE FROM ofertas WHERE equipo_comprador_id=? OR equipo_vendedor_id=?", (equipo["id"],equipo["id"]))
        except:
            pass
        await db.execute("DELETE FROM sub_dts WHERE equipo_id=?", (equipo["id"],))
        await db.execute("DELETE FROM equipos WHERE id=?", (equipo["id"],))
        await db.commit()
    await interaction.response.send_message(embed=embed_ok("🗑️ Equipo eliminado", f"**{equipo['nombre']}** ha sido eliminado. Puedes volver a registrarte con `/registrar`."))

@tree.command(name="resetear_equipo", description="[Admin] Elimina un equipo de la liga")
@app_commands.describe(rol="Rol del equipo a eliminar")
async def resetear_equipo(interaction: discord.Interaction, rol: discord.Role):
    if not es_admin(interaction):
        await interaction.response.send_message(embed=embed_error("Solo admins."), ephemeral=True); return
    equipo = await get_equipo_by_rol(str(rol.id))
    if not equipo:
        await interaction.response.send_message(embed=embed_error(f"No existe equipo con rol {rol.mention}."), ephemeral=True); return
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM jugadores WHERE equipo_id=?", (equipo["id"],))
        try:
            await db.execute("DELETE FROM ofertas WHERE equipo_comprador_id=? OR equipo_vendedor_id=?", (equipo["id"],equipo["id"]))
        except:
            pass
        await db.execute("DELETE FROM sub_dts WHERE equipo_id=?", (equipo["id"],))
        await db.execute("DELETE FROM equipos WHERE id=?", (equipo["id"],))
        await db.commit()
    await interaction.response.send_message(embed=embed_ok("🗑️ Equipo eliminado", f"**{equipo['nombre']}** eliminado. El DT puede volver a registrarse."))

@tree.command(name="resetear_liga", description="[Admin] Borra todos los datos y reinicia la liga")
async def resetear_liga(interaction: discord.Interaction):
    if not es_admin(interaction):
        await interaction.response.send_message(embed=embed_error("Solo admins."), ephemeral=True); return
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("DELETE FROM partidos; DELETE FROM jugadores; DELETE FROM equipos; DELETE FROM ofertas; DELETE FROM sub_dts;")
        await db.commit()
    await interaction.response.send_message(embed=embed_ok("🔄 Liga reseteada", "Todos los datos borrados. ¡Nueva temporada!"))

@tree.command(name="ayuda", description="Lista todos los comandos")
async def ayuda(interaction: discord.Interaction):
    emb = discord.Embed(title="📖 Comandos del bot de liga", color=COLOR_INFO)
    emb.add_field(name="⚽ Equipos", value="`/registrar` `/mi_equipo` `/ver_equipo` `/tabla` `/fixture`", inline=False)
    emb.add_field(name="👥 Sub DT", value="`/agregar_sub_dt` `/quitar_sub_dt`", inline=False)
    emb.add_field(name="🤝 Jugadores", value="`/inscribir_jugador` `/liberar_jugador` `/fichar` `/mercado`", inline=False)
    emb.add_field(name="💸 Fichajes con dinero", value="`/ofertar` `/mis_ofertas` `/aceptar_oferta` `/rechazar_oferta`", inline=False)
    emb.add_field(name="🗑️ Gestión", value="`/eliminar_mi_equipo` (DT) · `/resetear_equipo` (Admin)", inline=False)
    emb.add_field(name="🔧 Admin", value="`/resultado` `/generar_fixture` `/agregar_jugador_libre` `/resetear_liga`", inline=False)
    await interaction.response.send_message(embed=emb, ephemeral=True)

# ══════════════════════════════════════════════════════════════
#  SCHEDULERS
# ══════════════════════════════════════════════════════════════

async def scheduler_sueldos():
    await bot.wait_until_ready()
    while not bot.is_closed():
        try:
            jugadores = await get_todos_jugadores_con_sueldo()
            ahora = datetime.datetime.utcnow()
            for j in jugadores:
                if not j["contrato_inicio"]: continue
                inicio = datetime.datetime.fromisoformat(j["contrato_inicio"])
                dias = (ahora - inicio).days
                semanas_esperadas = dias // 7
                if semanas_esperadas > (j["pagos_realizados"] or 0):
                    async with aiosqlite.connect(DB_PATH) as db:
                        await db.execute("UPDATE equipos SET presupuesto=presupuesto-? WHERE id=?", (j["sueldo"], j["equipo_id"]))
                        await db.commit()
                    await incrementar_pago(j["id"])
        except Exception as e:
            print(f"Error scheduler sueldos: {e}")
        await asyncio.sleep(3600)

async def scheduler_presupuesto_mensual():
    await bot.wait_until_ready()
    while not bot.is_closed():
        await asyncio.sleep(30*24*3600)
        try:
            await dar_presupuesto_mensual()
            print("✅ $50M entregados a todos los equipos")
        except Exception as e:
            print(f"Error scheduler presupuesto: {e}")


# ══════════════════════════════════════════════════════════════
#  SISTEMA DE TICKETS
# ══════════════════════════════════════════════════════════════

STAFF_ROLES = ["🎶 | Moderador", "Fundador", "👮‍♂️ | Equipo Staff", "🍉 | Administrador", "👑 | Owner"]

TICKET_TIPOS = {
    "alianza": ("🤝", "ALIANZAS", "Hacer una alianza con nosotros"),
    "reporte": ("❗", "REPORTES", "Reportar algo que no sea apto"),
    "postulacion": ("👥", "POSTULACIONES", "Postularse para un cargo"),
    "inscribir": ("📋", "INSCRIBIR EQUIPO", "Inscribir tu equipo en la liga"),
    "otro": ("❓", "OTRO", "Cualquier otra consulta"),
}

class TicketSelect(discord.ui.Select):
    def __init__(self):
        super().__init__(
            placeholder="Selecciona el tipo de ticket...",
            custom_id="ticket_select",
            min_values=1,
            max_values=1,
            options=[
            discord.SelectOption(label="ALIANZAS", value="alianza", emoji="🤝", description="Hacer una alianza con nosotros"),
            discord.SelectOption(label="REPORTES", value="reporte", emoji="❗", description="Reportar algo que no sea apto"),
            discord.SelectOption(label="POSTULACIONES", value="postulacion", emoji="👥", description="Postularse para un cargo"),
            discord.SelectOption(label="INSCRIBIR EQUIPO", value="inscribir", emoji="📋", description="Inscribir tu equipo en la liga"),
            discord.SelectOption(label="OTRO", value="otro", emoji="❓", description="Cualquier otra consulta"),
        ])

    async def callback(self, interaction: discord.Interaction):
        tipo = self.values[0]
        emoji, nombre, desc = TICKET_TIPOS[tipo]
        guild = interaction.guild
        user = interaction.user

        await interaction.response.defer(ephemeral=True)
        
        # Nombre seguro para el canal (solo letras, números y guiones)
        import re as _re
        safe_name = _re.sub(r'[^a-z0-9]', '-', user.display_name.lower())[:20].strip('-') or f"user-{user.id}"
        canal_name = f"ticket-{safe_name}"

        # Verificar si ya tiene un ticket abierto
        canal_existente = discord.utils.get(guild.text_channels, name=canal_name)
        if canal_existente:
            await interaction.followup.send(
                f"Ya tienes un ticket abierto en {canal_existente.mention}.", ephemeral=True
            )
            return

        # Permisos del canal
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True),
        }
        # Agregar permisos a los roles de staff
        for rol_nombre in STAFF_ROLES:
            rol = discord.utils.get(guild.roles, name=rol_nombre)
            if rol:
                overwrites[rol] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

        # Buscar o crear categoría Tickets
        categoria = discord.utils.get(guild.categories, name="TICKETS")
        if not categoria:
            try:
                categoria = await guild.create_category("TICKETS")
            except:
                categoria = None

        try:
            canal = await guild.create_text_channel(
                name=canal_name,
                category=categoria,
                overwrites=overwrites
            )
        except Exception as e:
            await interaction.followup.send(f"No pude crear el canal del ticket. Verifica los permisos del bot.", ephemeral=True)
            return

        # Mensaje en el canal del ticket
        staff_mentions = []
        for rol_nombre in STAFF_ROLES:
            rol = discord.utils.get(guild.roles, name=rol_nombre)
            if rol:
                staff_mentions.append(rol.mention)

        emb = discord.Embed(
            title=f"{emoji} Ticket — {nombre}",
            description=(
                f"**Usuario:** {user.mention}\n"
                f"**Tipo:** {nombre}\n"
                f"**Descripción:** {desc}\n\n"
                f"El staff te atenderá en breve. Para cerrar el ticket usa el botón de abajo."
            ),
            color=COLOR_AMARILLO
        )
        emb.set_footer(text=f"Ticket abierto por {user.display_name}")

        view = CerrarTicketView()
        msg = await canal.send(
            content=" ".join(staff_mentions) + f" | {user.mention}",
            embed=emb,
            view=view
        )
        await msg.pin()

        await interaction.followup.send(
            f"✅ Tu ticket fue creado en {canal.mention}", ephemeral=True
        )


class CerrarTicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🔒 Cerrar ticket", style=discord.ButtonStyle.danger, custom_id="cerrar_ticket")
    async def cerrar(self, interaction: discord.Interaction, button: discord.ui.Button):
        es_staff = any(r.name in STAFF_ROLES for r in interaction.user.roles)
        if not es_staff and not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("Solo el staff puede cerrar tickets.", ephemeral=True)
            return
        await interaction.response.send_message("🔒 Cerrando ticket en 3 segundos...")
        await asyncio.sleep(3)
        await interaction.channel.delete()


class TicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(TicketSelect())

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return True


@tree.command(name="setup_tickets", description="[Admin] Envía el panel de tickets en este canal")
async def setup_tickets(interaction: discord.Interaction):
    if not es_admin(interaction):
        await interaction.response.send_message(embed=embed_error("Solo admins."), ephemeral=True)
        return
    emb = discord.Embed(
        title="🎫 Help & Support",
        description=(
            "Reclama un ticket según lo que deseas\n\n"
            "🤝 **ALIANZAS** — Hacer una alianza con nosotros\n"
            "❗ **REPORTES** — Reportar algo que no sea apto\n"
            "👥 **POSTULACIONES** — Postularse para un cargo\n"
            "📋 **INSCRIBIR EQUIPO** — Inscribir tu equipo en la liga\n"
            "❓ **OTRO** — Cualquier otra consulta"
        ),
        color=COLOR_AMARILLO
    )
    await interaction.channel.send(embed=emb, view=TicketView())
    await interaction.response.send_message("✅ Panel de tickets enviado.", ephemeral=True)

@bot.event
async def on_ready():
    await init_db()
    await tree.sync()
    print(f"✅ Bot conectado como {bot.user} | {len(bot.guilds)} servidor(es)")
    await bot.change_presence(activity=discord.Game(name="⚽ Liga activa | /ayuda"))
    asyncio.ensure_future(scheduler_sueldos())
    asyncio.ensure_future(scheduler_presupuesto_mensual())

@bot.event
async def on_command_error(ctx, error):
    pass

if __name__ == "__main__":
    bot.run(TOKEN)
