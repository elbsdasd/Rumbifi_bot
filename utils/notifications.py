import time
import threading
from datetime import datetime, time as time_obj # Renombrar time para evitar conflicto con el módulo time
import logging

from telegram import Bot

from . import database as db_utils # Sigue usando el mismo alias
import config # Ya no es necesario para LIMA_TZ, está en db_utils

logger = logging.getLogger(__name__)

_bot_instance: Bot = None

def check_and_send_reminders():
    if _bot_instance is None:
        logger.warning("Instancia del bot no establecida para el programador de notificaciones.")
        return

    try:
        pending_items_from_db = db_utils.get_pending_reminders() # db_utils ahora usa PostgreSQL
        now_lima = datetime.now(db_utils.LIMA_TZ)
        # current_time_str_lima = now_lima.strftime("%H:%M") # No se usa directamente

        for item in pending_items_from_db: # item es ahora un DictRow de psycopg2
            user_id = item.get("user_id")
            # La 'key' ahora es 'item_id' de la tabla planning_items
            item_key_or_id = item.get("key") # Esto debería ser el item_id
            
            # reminder_time de la BD es un objeto datetime.time
            reminder_time_obj_db = item.get("reminder_time") 
            task_text = item.get("text", "Tu tarea programada")

            if not user_id or not item_key_or_id or not reminder_time_obj_db:
                logger.warning(f"Datos incompletos para el recordatorio: {item}")
                continue
            
            # Convertir la hora del recordatorio (objeto time) a un objeto datetime para hoy
            try:
                # reminder_time_obj_db ya es un objeto time
                reminder_datetime_lima = now_lima.replace(
                    hour=reminder_time_obj_db.hour, 
                    minute=reminder_time_obj_db.minute, 
                    second=0, 
                    microsecond=0
                )
            except AttributeError: # Si reminder_time_obj_db no es un objeto time (ej. None)
                logger.error(f"reminder_time no es un objeto time válido para item {item_key_or_id}")
                continue


            time_difference_minutes = (now_lima - reminder_datetime_lima).total_seconds() / 60

            if -1 < time_difference_minutes < 5: 
                try:
                    logger.info(f"Enviando recordatorio a {user_id} para la tarea: {task_text}")
                    _bot_instance.send_message(
                        chat_id=user_id,
                        text=f"🔔 ¡Recordatorio Rumbify! 🔔\n\nEs hora de: {task_text}"
                    )
                    # Usar el item_id para marcar como enviado
                    db_utils.mark_reminder_sent(item_key_or_id) 
                    logger.info(f"Recordatorio para item_id {item_key_or_id} enviado y marcado.")
                except Exception as e:
                    logger.error(f"Error enviando recordatorio para item_id {item_key_or_id} a {user_id}: {e}")
            # else:
                # logger.debug(f"Recordatorio para item_id {item_key_or_id} no es para ahora. Hora actual: {now_lima.strftime('%H:%M')}, Hora recordatorio: {reminder_time_obj_db.strftime('%H:%M')}")

    except Exception as e:
        logger.error(f"Error en check_and_send_reminders: {e}")


def notification_scheduler_loop():
    logger.info("Notification scheduler loop_thread started (Render version).")
    while True:
        check_and_send_reminders()
        
        # También ejecutar la limpieza de tareas viejas periódicamente
        try:
            # logger.debug("Ejecutando limpieza de tareas antiguas no marcadas...")
            db_utils.cleanup_old_unmarked_tasks() # Esta función ahora usa SQL
        except Exception as e:
            logger.error(f"Error durante cleanup_old_unmarked_tasks: {e}")
            
        time.sleep(60)


def start_notification_scheduler(bot: Bot):
    global _bot_instance
    _bot_instance = bot
    
    scheduler_thread = threading.Thread(target=notification_scheduler_loop, daemon=True)
    scheduler_thread.start()
    logger.info("Notification scheduler thread initiated from notifications.py (Render version).")