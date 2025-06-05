# handlers/start_access.py

import logging
from telegram import Update, ParseMode, InlineKeyboardMarkup
from telegram.ext import CallbackContext # No necesitamos ConversationHandler aquí directamente

import config
from utils import database as db_utils
from . import common_handlers # Para el teclado del menú

logger = logging.getLogger(__name__)

WELCOME_MESSAGES = [
    "¡Hola! 👋 Soy Rumbify, tu mejor amigo que te ayudará a organizar tu día a día 📅 y tomar el control de tu vida ✨.",
    "A partir de hoy, tú liderarás el rumbo de tu historia 🚀.",
    "Te acompañaré paso a paso para que seas más productiv@ 💪, disciplinad@ y sobre todo, ¡constante! 🎯",
    "Con esfuerzo y perseverancia, ¡vamos a alcanzar tus sueños! 🌟"
]
VIDEO_PATH = "assets/Video_1.mp4" # Ruta relativa desde la raíz del proyecto

def send_main_menu_message(context: CallbackContext, user_id: int, message_text: str = "Aquí tienes el menú principal de Rumbify:", original_update: Update = None):
    """
    Envía el mensaje con el menú principal.
    Si original_update y su query existen, intenta editar. Sino, envía nuevo.
    """
    keyboard = common_handlers.get_main_menu_keyboard()
    
    should_edit = False
    if original_update and original_update.callback_query and original_update.callback_query.message:
        should_edit = True
    
    try:
        if should_edit:
            original_update.callback_query.edit_message_text(text=message_text, reply_markup=keyboard, parse_mode='Markdown')
        else:
            context.bot.send_message(chat_id=user_id, text=message_text, reply_markup=keyboard, parse_mode='Markdown')
    except Exception as e:
        logger.warning(f"Error enviando/editando menú principal para {user_id} (edit={should_edit}): {e}. Enviando como nuevo mensaje si no se editó.")
        if not should_edit or (should_edit and "message is not modified" not in str(e).lower()): # Evitar reenviar si el error fue "not modified"
            try:
                context.bot.send_message(chat_id=user_id, text=message_text, reply_markup=keyboard, parse_mode='Markdown')
            except Exception as e2:
                logger.error(f"Fallo crítico enviando menú principal a {user_id}: {e2}")


def start_command(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    user_id = user.id
    logger.info(f"Usuario {user_id} ({user.username or user.first_name}) inició /start (Render Full Review).")

    has_access, access_message = db_utils.check_user_access(user_id)
    if not has_access:
        update.message.reply_text(access_message)
        return

    for msg in WELCOME_MESSAGES:
        update.message.reply_text(msg)

    try:
        with open(VIDEO_PATH, 'rb') as video_file:
            context.bot.send_video(chat_id=user_id, video=video_file, caption="🎬 ¡Prepárate para tomar el control!")
    except FileNotFoundError:
        logger.warning(f"Video no encontrado en {VIDEO_PATH}. No se envió video a {user_id}.")
        update.message.reply_text("ℹ️ (Video de introducción no disponible en este momento)")
    except Exception as e:
        logger.error(f"Error enviando video a {user_id}: {e}")
        update.message.reply_text("⚠️ Hubo un problema al intentar mostrar el video de introducción.")

    send_main_menu_message(context, user_id, original_update=update) # Pasar update para posible edición

def main_menu_command(update: Update, context: CallbackContext) -> None:
    """Comando /menu para mostrar el menú principal del bot."""
    user_id = update.effective_user.id
    has_access, access_message = db_utils.check_user_access(user_id)
    if not has_access:
        update.message.reply_text(access_message)
        return
    send_main_menu_message(context, user_id, message_text="Volviendo al menú principal:", original_update=update)

def main_menu_button_handler(update: Update, context: CallbackContext) -> None:
    """Maneja el botón de callback para ir al menú principal del bot (config.CB_MAIN_MENU)."""
    query = update.callback_query
    query.answer() # Siempre contesta al callback
    user_id = query.from_user.id
    
    has_access, access_message = db_utils.check_user_access(user_id)
    if not has_access:
        try: 
            query.edit_message_text(text=access_message) 
        except Exception: 
            context.bot.send_message(chat_id=user_id, text=access_message)
        return
        
    send_main_menu_message(context, user_id, original_update=update) # Pasar update para editar

# --- Comandos de Administrador (sin cambios en su lógica interna) ---
def admin_add_user_command(update: Update, context: CallbackContext) -> None:
    # (Código idéntico a la versión anterior de Render)
    admin_id = update.effective_user.id
    if admin_id != config.ADMIN_USER_ID:
        update.message.reply_text("🚫 No tienes permiso para usar este comando."); return
    if not context.args:
        update.message.reply_text("Uso: /admin_adduser <ID_del_usuario_de_Telegram>"); return
    try:
        target_user_id = int(context.args[0])
        if db_utils.add_permanent_access(target_user_id):
            update.message.reply_text(f"✅ Acceso permanente otorgado al usuario ID: {target_user_id}.")
            try:
                context.bot.send_message(chat_id=target_user_id, text="🎉 ¡Felicidades! Has recibido acceso completo y permanente a Rumbify.")
            except Exception as e: logger.warning(f"No se pudo notificar al usuario {target_user_id} sobre el acceso: {e}")
        # else: # add_permanent_access ahora siempre retorna True si no hay excepción
            # update.message.reply_text(f"Acceso otorgado o ya existente para {target_user_id}.")
    except ValueError: update.message.reply_text("El ID del usuario debe ser un número.")
    except Exception as e: logger.error(f"Error en admin_adduser: {e}"); update.message.reply_text("Ocurrió un error.")

def admin_remove_user_command(update: Update, context: CallbackContext) -> None:
    # (Código idéntico a la versión anterior de Render)
    admin_id = update.effective_user.id
    if admin_id != config.ADMIN_USER_ID:
        update.message.reply_text("🚫 No tienes permiso para usar este comando."); return
    if not context.args:
        update.message.reply_text("Uso: /admin_removeuser <ID_del_usuario_de_Telegram>"); return
    try:
        target_user_id = int(context.args[0])
        if db_utils.remove_permanent_access(target_user_id):
            update.message.reply_text(f"✅ Acceso permanente revocado para el usuario ID: {target_user_id}.")
            try:
                context.bot.send_message(chat_id=target_user_id, text="ℹ️ Tu acceso permanente a Rumbify ha sido revocado.")
            except Exception as e: logger.warning(f"No se pudo notificar al usuario {target_user_id} sobre la revocación: {e}")
        else: update.message.reply_text(f"⚠️ No se pudo revocar acceso a {target_user_id} (quizás no existía).")
    except ValueError: update.message.reply_text("El ID del usuario debe ser un número.")
    except Exception as e: logger.error(f"Error en admin_removeuser: {e}"); update.message.reply_text("Ocurrió un error.")

def get_my_id_command(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_user.id
    update.message.reply_text(f"Tu ID de Telegram es: `{user_id}`", parse_mode=ParseMode.MARKDOWN_V2)