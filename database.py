import aiosqlite
import datetime

DB_PATH = "liga.db"
PRESUPUESTO_INICIAL = 50_000_000

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS equipos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                discord_id TEXT UNIQUE NOT NULL,
                nombre TEXT UNIQUE NOT NULL,
                dt_nombre TEXT NOT NULL,
                rol_id TEXT,
                presupuesto INTEGER DEFAULT 50000000,
                puntos INTEGER DEFAULT 0,
                pj INTEGER DEFAULT 0,
                pg INTEGER DEFAULT 0,
                pe INTEGER DEFAULT 0,
                pp INTEGER DEFAULT 0,
                gf INTEGER DEFAULT 0,
                gc INTEGER DEFAULT 0,
                creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS jugadores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT NOT NULL,
                posicion TEXT NOT NULL,
                equipo_id INTEGER,
                dorsal INTEGER,
                libre INTEGER DEFAULT 0,
                sueldo INTEGER DEFAULT 0,
                valor INTEGER DEFAULT 0,
                contrato_inicio TEXT DEFAULT NULL,
                pagos_realizados INTEGER DEFAULT 0,
                discord_id TEXT DEFAULT NULL,
                FOREIGN KEY (equipo_id) REFERENCES equipos(id)
            );
            CREATE TABLE IF NOT EXISTS partidos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                jornada INTEGER NOT NULL,
                local_id INTEGER NOT NULL,
                visitante_id INTEGER NOT NULL,
                goles_local INTEGER DEFAULT NULL,
                goles_visitante INTEGER DEFAULT NULL,
                jugado INTEGER DEFAULT 0,
                FOREIGN KEY (local_id) REFERENCES equipos(id),
                FOREIGN KEY (visitante_id) REFERENCES equipos(id)
            );
            CREATE TABLE IF NOT EXISTS ofertas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                jugador_id INTEGER NOT NULL,
                equipo_comprador_id INTEGER NOT NULL,
                equipo_vendedor_id INTEGER NOT NULL,
                monto INTEGER NOT NULL,
                estado TEXT DEFAULT 'pendiente',
                creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (jugador_id) REFERENCES jugadores(id),
                FOREIGN KEY (equipo_comprador_id) REFERENCES equipos(id),
                FOREIGN KEY (equipo_vendedor_id) REFERENCES equipos(id)
            );
            CREATE TABLE IF NOT EXISTS sub_dts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                equipo_id INTEGER NOT NULL,
                discord_id TEXT NOT NULL,
                UNIQUE(equipo_id, discord_id),
                FOREIGN KEY (equipo_id) REFERENCES equipos(id)
            );
        """)
        await db.commit()
        # Migraciones para bases existentes
        for col, tipo, default in [
            ("rol_id", "TEXT", "NULL"),
            ("presupuesto", "INTEGER", str(PRESUPUESTO_INICIAL)),
            ("sueldo", "INTEGER", "0"),
            ("valor", "INTEGER", "0"),
            ("contrato_inicio", "TEXT", "NULL"),
            ("pagos_realizados", "INTEGER", "0"),
            ("discord_id", "TEXT", "NULL"),
        ]:
            try:
                tbl = "equipos" if col in ("rol_id", "presupuesto") else "jugadores"
                await db.execute(f"ALTER TABLE {tbl} ADD COLUMN {col} {tipo} DEFAULT {default}")
                await db.commit()
            except:
                pass

async def get_equipo_by_discord(discord_id):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM equipos WHERE discord_id=?", (discord_id,)) as cur:
            return await cur.fetchone()

async def get_equipo_by_id(equipo_id):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM equipos WHERE id=?", (equipo_id,)) as cur:
            return await cur.fetchone()

async def get_equipo_by_nombre(nombre):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM equipos WHERE LOWER(nombre)=LOWER(?)", (nombre,)) as cur:
            return await cur.fetchone()

async def get_equipo_by_rol(rol_id):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM equipos WHERE rol_id=?", (rol_id,)) as cur:
            return await cur.fetchone()

async def crear_equipo(discord_id, nombre, dt_nombre, rol_id=None):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO equipos (discord_id, nombre, dt_nombre, rol_id, presupuesto) VALUES (?,?,?,?,?)",
            (discord_id, nombre, dt_nombre, rol_id, PRESUPUESTO_INICIAL)
        )
        await db.commit()

async def get_todos_equipos():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM equipos ORDER BY puntos DESC, (gf-gc) DESC, gf DESC") as cur:
            return await cur.fetchall()

async def get_roles_equipos():
    """Retorna lista de rol_ids de todos los equipos registrados."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT rol_id FROM equipos WHERE rol_id IS NOT NULL") as cur:
            rows = await cur.fetchall()
            return [r["rol_id"] for r in rows]

async def inscribir_jugador(nombre, posicion, equipo_id, dorsal, discord_id=None):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO jugadores (nombre, posicion, equipo_id, dorsal, discord_id) VALUES (?,?,?,?,?)",
            (nombre, posicion, equipo_id, dorsal, discord_id)
        )
        await db.commit()

async def get_plantilla(equipo_id):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM jugadores WHERE equipo_id=? ORDER BY dorsal", (equipo_id,)) as cur:
            return await cur.fetchall()

async def get_jugadores_libres():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM jugadores WHERE libre=1 OR equipo_id IS NULL") as cur:
            return await cur.fetchall()

async def get_jugador_by_nombre(nombre):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM jugadores WHERE LOWER(nombre)=LOWER(?)", (nombre,)) as cur:
            return await cur.fetchone()

async def get_jugador_by_id(jugador_id):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM jugadores WHERE id=?", (jugador_id,)) as cur:
            return await cur.fetchone()

async def fichar_jugador(jugador_id, nuevo_equipo_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE jugadores SET equipo_id=?, libre=0 WHERE id=?", (nuevo_equipo_id, jugador_id))
        await db.commit()

async def liberar_jugador(jugador_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE jugadores SET equipo_id=NULL, libre=1, sueldo=0, contrato_inicio=NULL WHERE id=?", (jugador_id,))
        await db.commit()

async def crear_partido(jornada, local_id, visitante_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT INTO partidos (jornada, local_id, visitante_id) VALUES (?,?,?)", (jornada, local_id, visitante_id))
        await db.commit()

async def get_fixture(jornada=None):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        if jornada:
            async with db.execute(
                "SELECT p.*,el.nombre as local_nombre,ev.nombre as visitante_nombre FROM partidos p JOIN equipos el ON p.local_id=el.id JOIN equipos ev ON p.visitante_id=ev.id WHERE p.jornada=? ORDER BY p.id", (jornada,)
            ) as cur:
                return await cur.fetchall()
        else:
            async with db.execute(
                "SELECT p.*,el.nombre as local_nombre,ev.nombre as visitante_nombre FROM partidos p JOIN equipos el ON p.local_id=el.id JOIN equipos ev ON p.visitante_id=ev.id WHERE p.jugado=0 ORDER BY p.jornada,p.id LIMIT 20"
            ) as cur:
                return await cur.fetchall()

async def cargar_resultado(partido_id, goles_local, goles_visitante):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM partidos WHERE id=?", (partido_id,)) as cur:
            partido = await cur.fetchone()
        if not partido:
            return False
        await db.execute("UPDATE partidos SET goles_local=?,goles_visitante=?,jugado=1 WHERE id=?", (goles_local, goles_visitante, partido_id))
        def stats(gf, gc):
            if gf>gc: return 3,1,0,0
            elif gf==gc: return 1,0,1,0
            else: return 0,0,0,1
        pts_l,pg_l,pe_l,pp_l = stats(goles_local, goles_visitante)
        pts_v,pg_v,pe_v,pp_v = stats(goles_visitante, goles_local)
        await db.execute("UPDATE equipos SET puntos=puntos+?,pj=pj+1,pg=pg+?,pe=pe+?,pp=pp+?,gf=gf+?,gc=gc+? WHERE id=?",
            (pts_l,pg_l,pe_l,pp_l,goles_local,goles_visitante,partido["local_id"]))
        await db.execute("UPDATE equipos SET puntos=puntos+?,pj=pj+1,pg=pg+?,pe=pe+?,pp=pp+?,gf=gf+?,gc=gc+? WHERE id=?",
            (pts_v,pg_v,pe_v,pp_v,goles_visitante,goles_local,partido["visitante_id"]))
        await db.commit()
        return True

async def generar_fixture_automatico():
    equipos = await get_todos_equipos()
    if len(equipos) < 2:
        return 0
    ids = [e["id"] for e in equipos]
    if len(ids) % 2 != 0:
        ids.append(None)
    n = len(ids)
    jornada = 1
    total = 0
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM partidos")
        await db.commit()
    for vuelta in range(2):
        ronda_ids = ids[:]
        for ronda in range(n-1):
            mitad = n//2
            for i in range(mitad):
                local = ronda_ids[i]
                visitante = ronda_ids[n-1-i]
                if local is not None and visitante is not None:
                    if vuelta == 1:
                        local, visitante = visitante, local
                    await crear_partido(jornada, local, visitante)
                    total += 1
            ronda_ids = [ronda_ids[0]] + [ronda_ids[-1]] + ronda_ids[1:-1]
            jornada += 1
    return total

# ── Ofertas ───────────────────────────────────────────────────
async def crear_oferta(jugador_id, equipo_comprador_id, equipo_vendedor_id, monto):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO ofertas (jugador_id,equipo_comprador_id,equipo_vendedor_id,monto) VALUES (?,?,?,?)",
            (jugador_id, equipo_comprador_id, equipo_vendedor_id, monto)
        )
        await db.commit()
        async with db.execute("SELECT last_insert_rowid()") as cur:
            return (await cur.fetchone())[0]

async def get_oferta(oferta_id):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM ofertas WHERE id=?", (oferta_id,)) as cur:
            return await cur.fetchone()

async def get_ofertas_pendientes(equipo_id):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM ofertas WHERE equipo_vendedor_id=? AND estado='pendiente' ORDER BY creado_en DESC", (equipo_id,)
        ) as cur:
            return await cur.fetchall()

async def aceptar_oferta(oferta_id):
    oferta = await get_oferta(oferta_id)
    if not oferta or oferta["estado"] != "pendiente":
        return False
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE jugadores SET equipo_id=?,libre=0,valor=? WHERE id=?",
            (oferta["equipo_comprador_id"], oferta["monto"], oferta["jugador_id"]))
        await db.execute("UPDATE equipos SET presupuesto=presupuesto-? WHERE id=?",
            (oferta["monto"], oferta["equipo_comprador_id"]))
        await db.execute("UPDATE equipos SET presupuesto=presupuesto+? WHERE id=?",
            (oferta["monto"], oferta["equipo_vendedor_id"]))
        await db.execute("UPDATE ofertas SET estado='aceptada' WHERE id=?", (oferta_id,))
        await db.execute("UPDATE ofertas SET estado='cancelada' WHERE jugador_id=? AND id!=? AND estado='pendiente'",
            (oferta["jugador_id"], oferta_id))
        await db.commit()
    return True

async def rechazar_oferta(oferta_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE ofertas SET estado='rechazada' WHERE id=?", (oferta_id,))
        await db.commit()

# ── Sub DTs ───────────────────────────────────────────────────
async def agregar_sub_dt(equipo_id, discord_id):
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute("INSERT INTO sub_dts (equipo_id,discord_id) VALUES (?,?)", (equipo_id, discord_id))
            await db.commit()
            return True
        except:
            return False

async def quitar_sub_dt(equipo_id, discord_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM sub_dts WHERE equipo_id=? AND discord_id=?", (equipo_id, discord_id))
        await db.commit()

async def get_equipo_by_sub_dt(discord_id):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT e.* FROM equipos e JOIN sub_dts s ON e.id=s.equipo_id WHERE s.discord_id=?", (discord_id,)
        ) as cur:
            return await cur.fetchone()

async def get_sub_dts(equipo_id):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM sub_dts WHERE equipo_id=?", (equipo_id,)) as cur:
            return await cur.fetchall()

# ── Contratos y sueldos ───────────────────────────────────────
async def activar_contrato(jugador_id, sueldo):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE jugadores SET sueldo=?,contrato_inicio=datetime('now'),pagos_realizados=0 WHERE id=?",
            (sueldo, jugador_id)
        )
        await db.commit()

async def get_todos_jugadores_con_sueldo():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT j.*,e.discord_id as dt_discord_id FROM jugadores j JOIN equipos e ON j.equipo_id=e.id WHERE j.sueldo>0 AND j.contrato_inicio IS NOT NULL"
        ) as cur:
            return await cur.fetchall()

async def incrementar_pago(jugador_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE jugadores SET pagos_realizados=pagos_realizados+1 WHERE id=?", (jugador_id,))
        await db.commit()

async def dar_presupuesto_mensual():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE equipos SET presupuesto=presupuesto+50000000")
        await db.commit()
