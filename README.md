# ⚽ Bot de Liga para Discord

Bot completo para gestionar una liga de fútbol en Discord: fichajes, plantillas, tabla de posiciones, fixture y resultados.

---

## 🚀 Instalación rápida

### 1. Requisitos
- Python 3.10 o superior
- Una cuenta en [discord.com/developers](https://discord.com/developers)

### 2. Instalar dependencias
```bash
pip install -r requirements.txt
```

### 3. Crear el bot en Discord
1. Ve a [discord.com/developers/applications](https://discord.com/developers/applications)
2. Clic en **New Application** → dale un nombre
3. Ve a **Bot** → clic en **Reset Token** → copia el token
4. En **Bot**, activa: `MESSAGE CONTENT INTENT`, `SERVER MEMBERS INTENT`
5. Ve a **OAuth2 → URL Generator**:
   - Scopes: `bot`, `applications.commands`
   - Bot Permissions: `Send Messages`, `Embed Links`, `Use Slash Commands`
6. Copia la URL generada y úsala para invitar el bot a tu servidor

### 4. Configurar el token
Edita `bot.py` y reemplaza:
```python
TOKEN = "TU_TOKEN_AQUI"
```
con tu token real. O mejor, usa una variable de entorno:
```bash
export DISCORD_TOKEN="tu_token_aqui"
```

### 5. Ejecutar
```bash
python bot.py
```

La primera vez que corra, el bot sincronizará los slash commands (puede tardar hasta 1 minuto en aparecer en Discord).

---

## 📋 Comandos disponibles

### Para DTs (todos los usuarios)
| Comando | Descripción |
|---|---|
| `/registrar` | Registrarse como DT e inscribir el equipo |
| `/mi_equipo` | Ver tu equipo, plantilla y estadísticas |
| `/ver_equipo` | Ver el equipo de otro DT |
| `/inscribir_jugador` | Añadir un jugador a tu plantilla |
| `/liberar_jugador` | Liberar un jugador al mercado libre |
| `/fichar` | Fichar un jugador del mercado libre |
| `/mercado` | Ver jugadores libres disponibles |
| `/tabla` | Tabla de posiciones de la liga |
| `/fixture` | Ver el fixture (todos o por jornada) |
| `/ayuda` | Lista de todos los comandos |

### Para Admins
| Comando | Descripción |
|---|---|
| `/resultado` | Cargar el resultado de un partido |
| `/generar_fixture` | Generar fixture de ida y vuelta automáticamente |
| `/agregar_jugador_libre` | Añadir un jugador al mercado libre |
| `/resetear_liga` | Reiniciar toda la liga (borra todos los datos) |

---

## 🏗️ Estructura del proyecto
```
liga_bot/
├── bot.py          # Bot principal con todos los comandos
├── database.py     # Base de datos SQLite y todas las consultas
├── requirements.txt
├── README.md
└── liga.db         # Se crea automáticamente al ejecutar
```

---

## ⚙️ Personalización

En `bot.py` puedes cambiar:
```python
ADMIN_ROL = "Admin"  # Nombre del rol de admin en tu servidor
```
Los admins también incluyen a cualquier usuario con permisos de Administrador del servidor.

---

## 💡 Flujo típico de uso

1. Admin invita el bot y ejecuta `/generar_fixture` (después de que se registren los DTs)
2. Cada DT usa `/registrar nombre_equipo`
3. Cada DT añade sus jugadores con `/inscribir_jugador`
4. El admin usa `/generar_fixture` para crear el calendario
5. Después de cada partido, el admin carga el resultado con `/resultado`
6. Los DTs pueden fichar jugadores del mercado con `/fichar`
7. Todos pueden ver la tabla con `/tabla` y el fixture con `/fixture`

---

## 🐛 Problemas frecuentes

**Los comandos no aparecen en Discord:**
El sync puede tardar hasta 1 hora en servidores nuevos. Para forzarlo,
puedes añadir `guild=discord.Object(id=TU_GUILD_ID)` al `tree.sync()` durante desarrollo.

**Error de permisos:**
Asegúrate de haber activado todos los intents en el panel de desarrolladores.
