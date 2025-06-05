import logging
import threading
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler, MessageHandler, Filters, ConversationHandler

# Módulos de configuración y utilidades
import config
# utils.database se importará como db_utils, pero su contenido interno cambiará
from utils import database as db_utils # <-- Este módulo será diferente
from utils import notifications as notification_utils
from utils import graphics as graphics_utils


# Módulos de Handlers (estos no cambian su lógica interna significativamente)
from handlers import start_access
from handlers import planning
from handlers import wellbeing
from handlers import finance
from handlers import progress
from handlers import common_handlers

# Configurar logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO # Cambiar a logging.DEBUG para más detalles durante el desarrollo
)
logger = logging.getLogger(__name__)

def main() -> None:
    """Inicia el bot."""
    
    # Es buena práctica inicializar la base de datos al inicio si es necesario
    # (crear tablas si no existen).
    try:
        db_utils.initialize_database() # Nueva función que añadiremos a database.py
        logger.info("Base de datos inicializada (tablas creadas si no existían).")
    except Exception as e:
        logger.error(f"CRÍTICO: No se pudo inicializar la base de datos: {e}")
        logger.error("El bot no puede continuar sin conexión a la base de datos o con tablas faltantes.")
        return # Detener el bot si la BD no se puede inicializar


    updater = Updater(config.TELEGRAM_BOT_TOKEN, use_context=True)
    dp = updater.dispatcher

    # --- Handlers Generales y de Acceso (sin cambios aquí) ---
    dp.add_handler(CommandHandler("start", start_access.start_command))
    dp.add_handler(CommandHandler("menu", start_access.main_menu_command))
    dp.add_handler(CommandHandler("admin_adduser", start_access.admin_add_user_command))
    dp.add_handler(CommandHandler("admin_removeuser", start_access.admin_remove_user_command))
    dp.add_handler(CommandHandler("get_my_id", start_access.get_my_id_command))

    # --- Handlers de CallbackQuery para Menús Principales (sin cambios aquí) ---
    dp.add_handler(CallbackQueryHandler(start_access.main_menu_button, pattern=f"^{config.CB_MAIN_MENU}$"))
    dp.add_handler(CallbackQueryHandler(planning.planning_menu, pattern=f"^{config.CB_PLAN_MAIN_MENU}$"))
    dp.add_handler(CallbackQueryHandler(wellbeing.wellbeing_menu, pattern=f"^{config.CB_WB_MAIN_MENU}$"))
    dp.add_handler(CallbackQueryHandler(finance.finance_menu, pattern=f"^{config.CB_FIN_MAIN_MENU}$"))
    dp.add_handler(CallbackQueryHandler(progress.progress_menu, pattern=f"^{config.CB_PROG_MAIN_MENU}$"))

    # --- Registro de Handlers de cada módulo (sin cambios aquí) ---
    planning.register_handlers(dp)
    wellbeing.register_handlers(dp)
    finance.register_handlers(dp)
    progress.register_handlers(dp)
    # common_handlers.register_handlers(dp) # Si tuviera callbacks globales

    # Iniciar el scheduler de notificaciones (sin cambios aquí)
    # El hilo se crea dentro de start_notification_scheduler
    notification_utils.start_notification_scheduler(updater.bot)
    logger.info("Notification scheduler startup initiated.")

    logger.info("Starting Rumbify Bot (Render version)...")
    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()