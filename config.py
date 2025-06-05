import os
from dotenv import load_dotenv

load_dotenv()

# --- BOT TOKEN ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "TU_BOT_TOKEN_AQUI_SI_NO_USAS_ENV")

# --- DATABASE URL (Provided by Render) ---
# Para desarrollo local, puedes configurar una DB PostgreSQL local y poner su URL aquí
# o en el .env. En Render, esta variable se establece automáticamente.
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://user:password@host:port/dbname")

# --- ADMIN USER ID ---
ADMIN_USER_ID = int(os.getenv("ADMIN_USER_ID", "0"))

# --- NOMBRES DE TABLAS EN POSTGRESQL (opcional, podemos usar nombres por defecto) ---
# No son tan críticos como los nombres de Base en Deta, pero pueden ayudar a organizar.

# --- MENSAJES COMUNES (igual que antes) ---
MSG_ACCESS_DENIED = "🚫 No tienes permiso para usar esta función o tu prueba ha expirado."
MSG_CONTACT_FOR_FULL_ACCESS = (
    "Tu periodo de prueba ha finalizado. Si Rumbify te ha sido útil y deseas seguir usándolo, "
    "por favor comunícate al +51 923544221 para obtener acceso completo."
)
MSG_REQUIRE_NUMBER = "🔢 Por favor, ingresa un valor numérico."
MSG_TIME_FORMAT_PROMPT = (
    "⏰ ¿A qué hora quieres un recordatorio para esta tarea? \n"
    "Envía la hora en formato HH:MM (ej. 09:30) o escribe 'no' si no necesitas recordatorio."
)
MSG_TIME_FORMAT_ERROR = "⚠️ Formato de hora incorrecto. Por favor, usa HH:MM (ej. 14:00) o escribe 'no'."

# --- ESTADOS DE CONVERSACIÓN (igual que antes) ---
STATE_WAITING_FOR_TIME = 1
STATE_WAITING_FOR_DESCRIPTION = 2

# --- NOMBRES DE BOTONES (Callbacks) (igual que antes) ---
# Planificación
CB_PLAN_MAIN_MENU = "plan_main"
CB_PLAN_SET_OBJECTIVE = "plan_set_obj"
# ... (todos los demás callbacks de config.py se mantienen igual) ...
CB_MAIN_MENU = "main_menu"
CB_GO_BACK_PREFIX = "go_back_"


# Validar que las variables críticas estén presentes
if not TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN == "TU_BOT_TOKEN_AQUI_SI_NO_USAS_ENV":
    raise ValueError("Error: TELEGRAM_BOT_TOKEN no está configurado.")
if not DATABASE_URL or DATABASE_URL == "postgresql://user:password@host:port/dbname":
    # En producción en Render, esta variable la provee Render.
    # En local, necesitas configurarla si vas a usar una DB PostgreSQL.
    # Si en local no usas DB, podrías comentar esta excepción temporalmente.
    print("Advertencia: DATABASE_URL no está configurada o usa el valor por defecto. "
          "Asegúrate de que esté configurada en Render o para desarrollo local con PostgreSQL.")
if ADMIN_USER_ID == 0:
    print("Advertencia: ADMIN_USER_ID no está configurado. Los comandos de administrador no funcionarán correctamente.")