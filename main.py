for i, e in enumerate(equipos, 1):
        dg = e["gf"] - e["gc"]
        lines.append(f"{i:<3} {e['nombre'][:20]:<20} {e['pj']:>3} {e['pg']:>3} {e['pe']:>3} {e['pp']:>3} {e['gf']:>3} {e['gc']:>3} {dg:>+4} {e['puntos']:>4}")
    lines.append("```")
    emb.description = "\n".join(lines)
    await interaction.response.send_message(embed=emb)

@tree.command(name="fixture", description="Ver fixture de una jornada o próximos partidos")
async def fixture(interaction: discord.Interaction, jornada: int = None):
    partidos = await get_fixture(jornada)
    if not partidos:
        await interaction.response.send_message(embed=embed_info("📅 Fixture", "No hay partidos pendientes.")); return
    emb = embed_info("📅 Fixture de la Liga")
    jornadas = {}
    for p in partidos: jornadas.setdefault(p["jornada"], []).append(p)
    for j, lista in sorted(jornadas.items()):
        lines = []
        for p in lista:
            if p["jugado"]: lines.append(f"**{p['local_nombre']}** {p['goles_local']} – {p['goles_visitante']} **{p['visitante_nombre']}**")
            else: lines.append(f"{p['local_nombre']} vs {p['visitante_nombre']} *(ID: {p['id']})*")
        emb.add_field(name=f"Jornada {j}", value="\n".join(lines), inline=False)
    await interaction.response.send_message(emb)

# ══════════════════════════════════════════════════════════════
#  ADMINISTRACIÓN
# ══════════════════════════════════════════════════════════════

@tree.command(name="resultado", description="[Admin] Carga el resultado de un partido")
async def resultado(interaction: discord.Interaction, partido_id: int, goles_local: int, goles_visitante: int):
    if not es_admin(interaction):
        await interaction.response.send_message(embed=embed_error("Solo admins."), ephemeral=True); return
    await cargar_resultado(partido_id, goles_local, goles_visitante)
    await interaction.response.send_message(embed=embed_ok("⚽ Resultado guardado", "El partido y la tabla han sido actualizados con éxito."))

@tree.command(name="generar_fixture", description="[Admin] Genera el fixture completo")
async def generar_fixture(interaction: discord.Interaction):
    if not es_admin(interaction):
        await interaction.response.send_message(embed=embed_error("Solo admins."), ephemeral=True); return
    await interaction.response.defer()
    total = await generar_fixture_automatico()
    await interaction.followup.send(embed=embed_ok("📅 Fixture generado", f"Se crearon {total} partidos en total."))

@tree.command(name="agregar_jugador_libre", description="[Admin] Agrega un jugador al mercado como libre")
async def agregar_jugador_libre_cmd(interaction: discord.Interaction, nombre: str, posicion: str, discord_id: discord.Member = None):
    if not es_admin(interaction):
        await interaction.response.send_message(embed=embed_error("Solo admins."), ephemeral=True); return
    disc_id_str = str(discord_id.id) if discord_id else None
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT INTO jugadores (nombre, posicion, libre, sueldo, valor, discord_id) VALUES (?, ?, 1, 0, 0, ?)", (nombre, posicion, disc_id_str))
        await db.commit()
    await interaction.response.send_message(embed=embed_ok("👤 Jugador libre añadido", f"**{nombre}** listo en la tienda."))

if __name__ == "__main__":
    bot.run(TOKEN)