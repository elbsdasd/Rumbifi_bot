# utils/notifications.py
# (Este código es el mismo que el del Mensaje 3 de X (Render) de la tanda anterior,
#  ya que los cambios en database.py no deberían afectar su lógica principal
#  siempre que get_pending_reminders y mark_reminder_sent sigan funcionando
#  con item_id como 'key')

import time
import threading
from datetime import datetime # No renombres time aquí, datetime.time es diferente
import logging

from telegram import Bot

from . import database as db_utils
# config no se usa aquí directamente

logger = logging.getLogger(__name__)

_bot_instance: Bot = None

def check_and_send_reminders():
    if _bot_instance is None:
        logger.warning("Instancia del bot no establecida para el programador de notificaciones.")
        return

    try:
        pending_items_from_db = db_utils.get_pending_reminders()
        now_lima = datetime.now(db_utils.LIMA_TZ)

        for item_dictrow in pending_items_from_db:
            item = dict(item_dictrow) # Convertir a dict
            user_id = item.get("user_id")
            item_id = item.get("key") # 'key' es el alias de item_id
            reminder_time_obj_db = item.get("reminder_time") # Objeto datetime.time de la BD
            task_text = item.get("text", "Tu tarea programada")

            if not all([user_id, item_id, reminder_time_obj_db]):
                logger.warning(f"Datos incompletos para el recordatorio: {item}")
                continue
            
            try:
                reminder_datetime_lima = now_lima.replace(
                    hour=reminder_time_obj_db.hour, 
                    minute=reminder_time_obj_db.minute, 
                    second=0, 
                    microsecond=0
                )
            except AttributeError: 
                logger.error(f"reminder_time no es un objeto time válido para item_id {item_id}")
                continue

            time_difference_minutes = (now_lima - reminder_datetime_lima).total_seconds() / 60

            if -1 < time_difference_minutes < 5: 
                try:
                    logger.info(f"Enviando recordatorio a {user_id} para tarea ID {item_id}: {task_text}")
                    _bot_instance.send_message(
                        chat_id=user_id,
                        text=f"🔔 ¡Recordatorio Rumbify! 🔔\n\nEs hora de: {task_text}"
                    )
                    db_utils.mark_reminder_sent(item_id) 
                    logger.info(f"Recordatorio para item_id {item_id} enviado y marcado.")
                except Exception as e:
                    logger.error(f"Error enviando recordatorio para item_id {item_id} a {user_id}: {e}")
    except Exception as e:
        logger.error(f"Error en check_and_send_reminders: {e}")

def notification_scheduler_loop():
    logger.info("Notification scheduler loop_thread started (Render version - Full Review).")
    while True:
        check_and_send_reminders()
        try:
            db_utils.cleanup_old_unmarked_tasks()
        except Exception as e:
            logger.error(f"Error durante cleanup_old_unmarked_tasks: {e}")
        time.sleep(60)

def start_notification_scheduler(bot: Bot):
    global _bot_instance
    _bot_instance = bot
    scheduler_thread = threading.Thread(target=notification_scheduler_loop, daemon=True)
    scheduler_thread.start()
    logger.info("Notification scheduler thread initiated from notifications.py (Render version - Full Review).")