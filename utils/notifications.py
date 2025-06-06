# utils/notifications.py
# (Este código es el mismo que el del Mensaje 3 de X (Revisión Completa para Render)
# que te di antes, ya que su lógica no cambia fundamentalmente).

import time
import threading
from datetime import datetime # No renombres time aquí, datetime.time es diferente
import logging

from telegram import Bot

from . import database as db_utils

logger = logging.getLogger(__name__)

_bot_instance: Bot = None # Variable global para la instancia del bot

def check_and_send_reminders():
    if _bot_instance is None:
        logger.warning("Instancia del bot no establecida para el programador de notificaciones.")
        return

    try:
        pending_items_from_db = db_utils.get_pending_reminders()
        now_lima = datetime.now(db_utils.LIMA_TZ)

        for item_dictrow in pending_items_from_db:
            item = dict(item_dictrow) # Convertir DictRow a dict
            user_id_str = item.get("user_id") # user_id es BIGINT en BD, psycopg2 lo da como int o str
            item_id = item.get("key") # 'key' es el alias de item_id
            reminder_time_obj_db = item.get("reminder_time") # Objeto datetime.time de la BD
            task_text = item.get("text", "Tu tarea programada")

            if not all([user_id_str, item_id, reminder_time_obj_db]):
                logger.warning(f"Datos incompletos para el recordatorio (item_id: {item_id}): {item}")
                continue
            
            try:
                user_id = int(user_id_str) # Convertir a int si es necesario
                reminder_datetime_lima = now_lima.replace(
                    hour=reminder_time_obj_db.hour, 
                    minute=reminder_time_obj_db.minute, 
                    second=0, 
                    microsecond=0
                )
            except (AttributeError, ValueError) as e: 
                logger.error(f"Error procesando datos del recordatorio (item_id {item_id}): {e}")
                continue

            time_difference_minutes = (now_lima - reminder_datetime_lima).total_seconds() / 60

            if -1 < time_difference_minutes < 5: # Margen para el scheduler
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
        logger.error(f"Error crítico en check_and_send_reminders: {e}")

def notification_scheduler_loop():
    logger.info("Notification scheduler loop_thread started (Render Final Review).")
    while True:
        check_and_send_reminders()
        try:
            db_utils.cleanup_old_unmarked_tasks() # Limpieza de tareas de planificación
            # Podríamos añadir limpieza para wellbeing_docs/sub_items si es necesario
        except Exception as e:
            logger.error(f"Error durante la tarea de limpieza periódica: {e}")
        time.sleep(60) # Revisar cada minuto

def start_notification_scheduler(bot: Bot):
    global _bot_instance
    _bot_instance = bot
    scheduler_thread = threading.Thread(target=notification_scheduler_loop, daemon=True)
    scheduler_thread.start()
    logger.info("Notification scheduler thread initiated from notifications.py (Render Final Review).")