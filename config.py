# config.py

import os
from dotenv import load_dotenv

# Cargar variables de entorno desde un archivo .env (para desarrollo local)
# En Render, estas se configuran en el dashboard del servicio.
load_dotenv()

# --- BOT TOKEN ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "TU_BOT_TOKEN_AQUI_SI_NO_USAS_ENV")

# --- DATABASE URL (Provided by Render) ---
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://user:password@host:port/dbname_placeholder") # Placeholder

# --- ADMIN USER ID ---
# Tu ID de usuario de Telegram para comandos de administrador.
ADMIN_USER_ID = int(os.getenv("ADMIN_USER_ID", "0")) # Reemplaza 0 con tu ID real o configúralo en .env

# --- MENSAJES COMUNES ---
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

# --- ESTADOS DE CONVERSACIÓN GENERALES (si los usas globalmente) ---
# Los estados específicos de cada flujo se definen mejor en sus respectivos módulos de handlers.
# STATE_WAITING_FOR_TIME = 1 # Ejemplo, pero no se usa globalmente así
# STATE_WAITING_FOR_DESCRIPTION = 2 # Ejemplo

# --- NOMBRES DE BOTONES (CALLBACK DATA STRINGS) ---

# Menús Principales y Navegación General
CB_MAIN_MENU = "main_menu" # Para volver al menú principal del bot
CB_GO_BACK_PREFIX = "go_back_" # Prefijo para botones de "volver" dinámicos

# Planificación
CB_PLAN_MAIN_MENU = "plan_main_menu_cb"         # Botón "Planificar Mi Día" del menú principal
CB_PLAN_SET_OBJECTIVE = "plan_set_objective_cb"
CB_PLAN_SET_IMPORTANT = "plan_set_important_cb"
CB_PLAN_SET_SECONDARY = "plan_set_secondary_cb"
CB_PLAN_VIEW_DAY = "plan_view_day_cb"
# Los prefijos para guardar se usan internamente en los handlers, no necesitan ser constantes globales
# CB_PLAN_SAVE_OBJECTIVE_PREFIX = "plan_save_obj_"
# CB_PLAN_SAVE_IMPORTANT_PREFIX = "plan_save_imp_"
# CB_PLAN_SAVE_SECONDARY_PREFIX = "plan_save_sec_"

# Bienestar Físico y Mental
CB_WB_MAIN_MENU = "wb_main_menu_cb"             # Botón "Bienestar Físico y Mental" del menú principal
CB_WB_REG_EXERCISE = "wb_reg_exercise_cb"
CB_WB_REG_DIET = "wb_reg_diet_main_cb"          # Registrar comidas principales
CB_WB_VIEW_ROUTINE = "wb_view_routine_cb"
CB_WB_VIEW_DIET = "wb_view_diet_cb"
CB_WB_REG_EXTRAS = "wb_reg_diet_extras_cb"      # Registrar antojos/extras desde "Ver Dieta"
# Los prefijos para guardar se usan internamente

# Finanzas
CB_FIN_MAIN_MENU = "fin_main_menu_cb"           # Botón "Mis Finanzas" del menú principal
CB_FIN_REG_INCOME = "fin_reg_income_menu_cb"    # Botón para ir al submenú de registrar ingresos
CB_FIN_REG_EXPENSE = "fin_reg_expense_menu_cb"  # Botón para ir al submenú de registrar gastos
CB_FIN_REG_SAVINGS = "fin_reg_savings_cb"       # Botón para registrar ahorros directamente
CB_FIN_VIEW_SUMMARY = "fin_view_summary_cb"
# Sub-tipos de transacciones (para iniciar el flujo de pedir monto)
CB_FIN_REG_FIXED_INCOME = "fin_reg_fixed_income_amount_cb"
CB_FIN_REG_VAR_INCOME = "fin_reg_var_income_amount_cb"
CB_FIN_REG_FIXED_EXPENSE = "fin_reg_fixed_expense_amount_cb"
CB_FIN_REG_VAR_EXPENSE = "fin_reg_var_expense_amount_cb"
# Los prefijos para guardar se usan internamente

# Progreso / Gráficas
CB_PROG_MAIN_MENU = "prog_main_menu_cb"         # Botón "Ver Mi Progreso" del menú principal
CB_PROG_GRAPH_DISCIPLINE = "prog_graph_discipline_cb"
CB_PROG_GRAPH_FINANCE = "prog_graph_finance_cb"
CB_PROG_GRAPH_WELLBEING = "prog_graph_wellbeing_cb"

# Callbacks para Marcar Tareas/Items (prefijos, el resto es dinámico)
CB_TASK_DONE_PREFIX = "task_done_"      # task_done_{seccion}_{item_id_o_sub_item_id}
CB_TASK_NOT_DONE_PREFIX = "task_notdone_" # task_notdone_{seccion}_{item_id_o_sub_item_id}
# Ejemplo de uso dinámico en el código: f"{CB_TASK_DONE_PREFIX}planning_{item_id}"
# Ejemplo de uso dinámico en el código: f"{CB_TASK_DONE_PREFIX}wb_exercise_{sub_item_id}"


# --- VALIDACIÓN DE CONFIGURACIONES CRÍTICAS ---
if not TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN == "TU_BOT_TOKEN_AQUI_SI_NO_USAS_ENV":
    raise ValueError("CRÍTICO: TELEGRAM_BOT_TOKEN no está configurado en las variables de entorno.")

if not DATABASE_URL or DATABASE_URL == "postgresql://user:password@host:port/dbname_placeholder":
    # Esta advertencia es más para desarrollo local. En Render, si no está, fallará al conectar.
    print("ADVERTENCIA: DATABASE_URL no está configurada o usa el valor placeholder. "
          "Asegúrate de que esté correctamente establecida en el entorno de Render "
          "o en tu archivo .env para desarrollo local con PostgreSQL.")

if ADMIN_USER_ID == 0:
    print("ADVERTENCIA: ADMIN_USER_ID no está configurado como una variable de entorno válida. "
          "Los comandos de administrador no funcionarán correctamente.")