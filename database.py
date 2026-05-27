import aiosqlite
import os

DB_PATH = "liga.db"

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS equipos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                discord_id TEXT UNIQUE NOT NULL,
                nombre TEXT UNIQUE NOT NULL,
                dt_nombre TEXT NOT NULL,
                rol_id TEXT,
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
                jugador_origen_id INTEGER NOT NULL,
                jugador_destino_id INTEGER NOT NULL,
                equipo_origen_id INTEGER NOT NULL,
                equipo_destino_id INTEGER NOT NULL,
                estado TEXT DEFAULT 'pendiente',
                creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (jugador_origen_id) REFERENCES jugadores(id),
                FOREIGN KEY (jugador_destino_id) REFERENCES jugadores(id),
                FOREIGN KEY (equipo_origen_id) REFERENCES equipos(id),
                FOREIGN KEY (equipo_destino_id) REFERENCES equipos(id)
            );
        """)
        # Agregar columna rol_id si no existe (para bases de datos ya creadas)
        try:
            await db.execute("ALTER TABLE equipos ADD COLUMN rol_id TEXT")
            await db.commit()
        except:
            pass

async def get_equipo_by_discord(discord_id: str):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM equipos WHERE discord_id = ?", (discord_id,)) as cur:
            return await cur.fetchone()

async def get_equipo_by_id(equipo_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM equipos WHERE id = ?", (equipo_id,)) as cur:
            return await cur.fetchone()

async def get_equipo_by_nombre(nombre: str):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM equipos WHERE LOWER(nombre) = LOWER(?)", (nombre,)) as cur:
            return await cur.fetchone()

async def get_equipo_by_rol(rol_id: str):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM equipos WHERE rol_id = ?", (rol_id,)) as cur:
            return await cur.fetchone()

async def crear_equipo(discord_id: str, nombre: str, dt_nombre: str, rol_id: str = None):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO equipos (discord_id, nombre, dt_nombre, rol_id) VALUES (?, ?, ?, ?)",
            (discord_id, nombre, dt_nombre, rol_id)
        )
        await db.commit()

async def get_todos_equipos():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM equipos ORDER BY puntos DESC, (gf - gc) DESC, gf DESC") as cur:
            return await cur.fetchall()

async def inscribir_jugador(nombre: str, posicion: str, equipo_id: int, dorsal: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO jugadores (nombre, posicion, equipo_id, dorsal) VALUES (?, ?, ?, ?)",
            (nombre, posicion, equipo_id, dorsal)
        )
        await db.commit()

async def get_plantilla(equipo_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM jugadores WHERE equipo_id = ? ORDER BY dorsal", (equipo_id,)) as cur:
            return await cur.fetchall()

async def get_jugadores_libres():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM jugadores WHERE libre = 1 OR equipo_id IS NULL") as cur:
            return await cur.fetchall()

async def get_jugador_by_nombre(nombre: str):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM jugadores WHERE LOWER(nombre) = LOWER(?)", (nombre,)) as cur:
            return await cur.fetchone()

async def get_jugador_by_id(jugador_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM jugadores WHERE id = ?", (jugador_id,)) as cur:
            return await cur.fetchone()

async def fichar_jugador(jugador_id: int, nuevo_equipo_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE jugadores SET equipo_id = ?, libre = 0 WHERE id = ?", (nuevo_equipo_id, jugador_id))
        await db.commit()

async def liberar_jugador(jugador_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE jugadores SET equipo_id = NULL, libre = 1 WHERE id = ?", (jugador_id,))
        await db.commit()

async def crear_partido(jornada: int, local_id: int, visitante_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT INTO partidos (jornada, local_id, visitante_id) VALUES (?, ?, ?)", (jornada, local_id, visitante_id))
        await db.commit()

async def get_fixture(jornada: int = None):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        if jornada:
            async with db.execute(
                """SELECT p.*, el.nombre as local_nombre, ev.nombre as visitante_nombre
                   FROM partidos p JOIN equipos el ON p.local_id = el.id
                   JOIN equipos ev ON p.visitante_id = ev.id
                   WHERE p.jornada = ? ORDER BY p.id""", (jornada,)
            ) as cur:
                return await cur.fetchall()
        else:
            async with db.execute(
                """SELECT p.*, el.nombre as local_nombre, ev.nombre as visitante_nombre
                   FROM partidos p JOIN equipos el ON p.local_id = el.id
                   JOIN equipos ev ON p.visitante_id = ev.id
                   WHERE p.jugado = 0 ORDER BY p.jornada, p.id LIMIT 20"""
            ) as cur:
                return await cur.fetchall()

async def cargar_resultado(partido_id: int, goles_local: int, goles_visitante: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM partidos WHERE id = ?", (partido_id,)) as cur:
            partido = await cur.fetchone()
        if not partido:
            return False
        await db.execute("UPDATE partidos SET goles_local=?, goles_visitante=?, jugado=1 WHERE id=?", (goles_local, goles_visitante, partido_id))
        def stats(gf, gc):
            if gf > gc: return 3, 1, 0, 0
            elif gf == gc: return 1, 0, 1, 0
            else: return 0, 0, 0, 1
        pts_l, pg_l, pe_l, pp_l = stats(goles_local, goles_visitante)
        pts_v, pg_v, pe_v, pp_v = stats(goles_visitante, goles_local)
        await db.execute("UPDATE equipos SET puntos=puntos+?, pj=pj+1, pg=pg+?, pe=pe+?, pp=pp+?, gf=gf+?, gc=gc+? WHERE id=?",
            (pts_l, pg_l, pe_l, pp_l, goles_local, goles_visitante, partido["local_id"]))
        await db.execute("UPDATE equipos SET puntos=puntos+?, pj=pj+1, pg=pg+?, pe=pe+?, pp=pp+?, gf=gf+?, gc=gc+? WHERE id=?",
            (pts_v, pg_v, pe_v, pp_v, goles_visitante, goles_local, partido["visitante_id"]))
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
        for ronda in range(n - 1):
            mitad = n // 2
            for i in range(mitad):
                local = ronda_ids[i]
                visitante = ronda_ids[n - 1 - i]
                if local is not None and visitante is not None:
                    if vuelta == 1:
                        local, visitante = visitante, local
                    await crear_partido(jornada, local, visitante)
                    total += 1
            ronda_ids = [ronda_ids[0]] + [ronda_ids[-1]] + ronda_ids[1:-1]
            jornada += 1
    return total

# ── Comercios ─────────────────────────────────────────────────

async def crear_oferta(jugador_origen_id: int, jugador_destino_id: int, equipo_origen_id: int, equipo_destino_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO ofertas (jugador_origen_id, jugador_destino_id, equipo_origen_id, equipo_destino_id) VALUES (?, ?, ?, ?)",
            (jugador_origen_id, jugador_destino_id, equipo_origen_id, equipo_destino_id)
        )
        await db.commit()
        async with db.execute("SELECT last_insert_rowid()") as cur:
            row = await cur.fetchone()
            return row[0]

async def get_oferta(oferta_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM ofertas WHERE id = ?", (oferta_id,)) as cur:
            return await cur.fetchone()

async def get_ofertas_pendientes(equipo_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM ofertas WHERE equipo_destino_id = ? AND estado = 'pendiente'", (equipo_id,)
        ) as cur:
            return await cur.fetchall()

async def responder_oferta(oferta_id: int, aceptar: bool):
    estado = 'aceptada' if aceptar else 'rechazada'
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE ofertas SET estado = ? WHERE id = ?", (estado, oferta_id))
        await db.commit()

async def ejecutar_intercambio(oferta_id: int):
    oferta = await get_oferta(oferta_id)
    if not oferta:
        return False
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE jugadores SET equipo_id = ? WHERE id = ?", (oferta["equipo_destino_id"], oferta["jugador_origen_id"]))
        await db.execute("UPDATE jugadores SET equipo_id = ? WHERE id = ?", (oferta["equipo_origen_id"], oferta["jugador_destino_id"]))
        await db.commit()
    return True
