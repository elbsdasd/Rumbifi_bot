# main.py

import logging
import threading
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler, MessageHandler, Filters, ConversationHandler

import config
from utils import database as db_utils
from utils import notifications as notification_utils
# from utils import graphics as graphics_utils # No se usa directamente aquí

from handlers import start_access
from handlers import planning
from handlers import wellbeing
from handlers import finance
from handlers import progress
# common_handlers es importado por los otros módulos de handlers

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO # Cambiar a DEBUG para más detalle si es necesario
)
logger = logging.getLogger(__name__)

def main() -> None:
    """Inicia el bot."""
    
    try:
        db_utils.initialize_database()
        logger.info("Base de datos inicializada (tablas creadas si no existían).")
    except Exception as e:
        logger.critical(f"CRÍTICO: No se pudo inicializar la base de datos: {e}")
        logger.critical("El bot no puede continuar sin conexión a la base de datos o con tablas faltantes.")
        return 

    updater = Updater(config.TELEGRAM_BOT_TOKEN, use_context=True)
    dp = updater.dispatcher

    # --- Handlers Generales y de Acceso ---
    # start_command ahora manejará el saludo combinado y el video opcional
    dp.add_handler(CommandHandler("start", start_access.start_command_handler)) # Renombrado para claridad
    dp.add_handler(CommandHandler("menu", start_access.main_menu_command_handler)) # Renombrado
    dp.add_handler(CommandHandler("admin_adduser", start_access.admin_add_user_command))
    dp.add_handler(CommandHandler("admin_removeuser", start_access.admin_remove_user_command))
    dp.add_handler(CommandHandler("get_my_id", start_access.get_my_id_command))

    # --- Handlers de CallbackQuery para NAVEGACIÓN PRINCIPAL ---
    # Botón para mostrar el menú principal del bot (desde cualquier lugar donde se ponga este botón)
    dp.add_handler(CallbackQueryHandler(start_access.main_menu_button_handler, pattern=f"^{config.CB_MAIN_MENU}$"))
    
    # Botones que abren los menús de cada sección principal
    # Estos llaman a las funciones de menú de cada módulo, que son los entry_points de sus ConvHandlers
    dp.add_handler(CallbackQueryHandler(planning.planning_menu, pattern=f"^{config.CB_PLAN_MAIN_MENU}$"))
    dp.add_handler(CallbackQueryHandler(wellbeing.wellbeing_menu, pattern=f"^{config.CB_WB_MAIN_MENU}$"))
    dp.add_handler(CallbackQueryHandler(finance.finance_menu, pattern=f"^{config.CB_FIN_MAIN_MENU}$"))
    dp.add_handler(CallbackQueryHandler(progress.progress_menu, pattern=f"^{config.CB_PROG_MAIN_MENU}$"))

    # --- Registro de Handlers específicos de cada módulo ---
    planning.register_handlers(dp)
    wellbeing.register_handlers(dp)
    finance.register_handlers(dp)
    progress.register_handlers(dp)
    
    # Iniciar el scheduler de notificaciones
    notification_utils.start_notification_scheduler(updater.bot)
    logger.info("Notification scheduler startup initiated.")

    logger.info("Starting Rumbify Bot (Render Final Review)...")
    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()