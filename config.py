# config.py

import os
from dotenv import load_dotenv

load_dotenv()

# --- BOT TOKEN ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "TU_NUEVO_TOKEN_AQUI_SI_NO_USAS_ENV") # Placeholder para tu nuevo token

# --- DATABASE URL (Provided by Render) ---
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://user:password@host:port/dbname_placeholder")

# --- ADMIN USER ID ---
ADMIN_USER_ID = int(os.getenv("ADMIN_USER_ID", "0"))

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

# --- NOMBRES DE BOTONES (CALLBACK DATA STRINGS) ---
# (Se mantienen las definiciones de la última revisión completa, ya que eran consistentes)

# Menús Principales y Navegación General
CB_MAIN_MENU = "main_menu_cb"

# Planificación
CB_PLAN_MAIN_MENU = "planning_menu_entry_cb"
CB_PLAN_SET_OBJECTIVE = "plan_set_objective_action_cb"
CB_PLAN_SET_IMPORTANT = "plan_set_important_action_cb"
CB_PLAN_SET_SECONDARY = "plan_set_secondary_action_cb"
CB_PLAN_VIEW_DAY = "plan_view_day_action_cb"

# Bienestar Físico y Mental
CB_WB_MAIN_MENU = "wellbeing_menu_entry_cb"
CB_WB_REG_EXERCISE = "wb_reg_exercise_action_cb"
CB_WB_REG_DIET = "wb_reg_diet_main_action_cb"
CB_WB_VIEW_ROUTINE = "wb_view_routine_action_cb"
CB_WB_VIEW_DIET = "wb_view_diet_action_cb"
CB_WB_REG_EXTRAS = "wb_reg_diet_extras_action_cb"

# Finanzas
CB_FIN_MAIN_MENU = "finance_menu_entry_cb"
CB_FIN_REG_INCOME_MENU = "fin_reg_income_submenu_cb"
CB_FIN_REG_EXPENSE_MENU = "fin_reg_expense_submenu_cb"
CB_FIN_REG_SAVINGS_ACTION = "fin_reg_savings_action_cb"
CB_FIN_VIEW_SUMMARY = "fin_view_summary_action_cb"
CB_FIN_REG_FIXED_INCOME_START = "fin_reg_fixed_income_start_cb"
CB_FIN_REG_VAR_INCOME_START = "fin_reg_var_income_start_cb"
CB_FIN_REG_FIXED_EXPENSE_START = "fin_reg_fixed_expense_start_cb"
CB_FIN_REG_VAR_EXPENSE_START = "fin_reg_var_expense_start_cb"

# Progreso / Gráficas
CB_PROG_MAIN_MENU = "progress_menu_entry_cb"
CB_PROG_GRAPH_DISCIPLINE = "prog_graph_discipline_action_cb"
CB_PROG_GRAPH_FINANCE = "prog_graph_finance_action_cb"
CB_PROG_GRAPH_WELLBEING = "prog_graph_wellbeing_action_cb"

# Callbacks para Marcar Tareas/Items (prefijos)
CB_TASK_DONE_PREFIX = "task_done_"
CB_TASK_NOT_DONE_PREFIX = "task_notdone_"

# --- VALIDACIÓN DE CONFIGURACIONES CRÍTICAS ---
if not TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN == "TU_NUEVO_TOKEN_AQUI_SI_NO_USAS_ENV":
    raise ValueError("CRÍTICO: TELEGRAM_BOT_TOKEN no está configurado en las variables de entorno.")
if not DATABASE_URL or DATABASE_URL == "postgresql://user:password@host:port/dbname_placeholder":
    print("ADVERTENCIA: DATABASE_URL no está configurada o usa el valor placeholder.")
if ADMIN_USER_ID == 0:
    print("ADVERTENCIA: ADMIN_USER_ID no está configurado como una variable de entorno válida.")