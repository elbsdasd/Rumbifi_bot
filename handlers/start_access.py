# handlers/start_access.py

import logging
from telegram import Update, ParseMode, InlineKeyboardMarkup
from telegram.ext import CallbackContext # No se usa ConversationHandler directamente aquí

import config
from utils import database as db_utils
from . import common_handlers # Para el teclado del menú

logger = logging.getLogger(__name__)

# Saludo inicial combinado
COMBINED_WELCOME_MESSAGE = (
    "¡Hola! 👋 Soy Rumbify, tu mejor amigo que te ayudará a organizar tu día a día 📅 y tomar el control de tu vida ✨.\n\n"
    "A partir de hoy, tú liderarás el rumbo de tu historia 🚀.\n\n"
    "Te acompañaré paso a paso para que seas más productiv@ 💪, disciplinad@ y sobre todo, ¡constante! 🎯\n\n"
    "Con esfuerzo y perseverancia, ¡vamos a alcanzar tus sueños! 🌟"
)
VIDEO_PATH = "assets/Video_1.mp4" 

def send_bot_main_menu(context: CallbackContext, user_id: int, message_text: str = None, original_update: Update = None):
    """
    Envía el mensaje con el menú principal del bot.
    Intenta editar si original_update.callback_query existe, sino envía nuevo mensaje.
    """
    if message_text is None:
        message_text = "🤖 Menú Principal de Rumbify. ¿Qué deseas hacer?"
        
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
        logger.warning(f"Error enviando/editando menú principal del bot para {user_id} (edit={should_edit}): {e}.")
        # Fallback a enviar un nuevo mensaje si la edición falla por razones que no sean "message is not modified"
        if not should_edit or (should_edit and "message is not modified" not in str(e).lower()):
            try:
                context.bot.send_message(chat_id=user_id, text=message_text, reply_markup=keyboard, parse_mode='Markdown')
            except Exception as e2:
                logger.error(f"Fallo crítico enviando menú principal del bot a {user_id}: {e2}")

def start_command_handler(update: Update, context: CallbackContext) -> None:
    """Maneja el comando /start."""
    user = update.effective_user
    user_id = user.id
    logger.info(f"Usuario {user_id} ({user.username or user.first_name}) inició /start (Render Final Review).")

    has_access, access_message = db_utils.check_user_access(user_id)
    if not has_access:
        update.message.reply_text(access_message)
        return

    # Enviar saludo combinado
    update.message.reply_text(COMBINED_WELCOME_MESSAGE)

    # Intentar enviar el video silenciosamente si existe
    try:
        with open(VIDEO_PATH, 'rb') as video_file:
            context.bot.send_video(chat_id=user_id, video=video_file, caption="🎬 ¡Prepárate!") 
            # No enviar mensaje si no se encuentra, simplemente no se envía el video.
    except FileNotFoundError:
        logger.warning(f"Video no encontrado en {VIDEO_PATH}. No se enviará video a {user_id}.")
    except Exception as e: # Otros errores al enviar el video
        logger.error(f"Error enviando video a {user_id}: {e}")
        # No enviar mensaje de error al usuario por el video, para mantenerlo silencioso.

    # Enviar menú principal del bot
    send_bot_main_menu(context, user_id, original_update=update)

def main_menu_command_handler(update: Update, context: CallbackContext) -> None:
    """Comando /menu para mostrar el menú principal del bot."""
    user_id = update.effective_user.id
    has_access, access_message = db_utils.check_user_access(user_id)
    if not has_access:
        update.message.reply_text(access_message)
        return
    send_bot_main_menu(context, user_id, message_text="Volviendo al menú principal:", original_update=update)

def main_menu_button_handler(update: Update, context: CallbackContext) -> None:
    """Maneja el botón de callback para ir al menú principal del bot (config.CB_MAIN_MENU)."""
    query = update.callback_query
    query.answer() 
    user_id = query.from_user.id
    
    has_access, access_message = db_utils.check_user_access(user_id)
    if not has_access:
        try: query.edit_message_text(text=access_message) 
        except Exception: context.bot.send_message(chat_id=user_id, text=access_message)
        return
        
    send_bot_main_menu(context, user_id, original_update=update) # Pasar update para que pueda intentar editar

# --- Comandos de Administrador (sin cambios en su lógica interna) ---
def admin_add_user_command(update: Update, context: CallbackContext) -> None:
    # (Código idéntico a la última versión estable para Render)
    admin_id = update.effective_user.id
    if admin_id != config.ADMIN_USER_ID: update.message.reply_text("🚫 Permiso denegado."); return
    if not context.args: update.message.reply_text("Uso: /admin_adduser <ID_usuario>"); return
    try:
        target_user_id = int(context.args[0])
        if db_utils.add_permanent_access(target_user_id):
            update.message.reply_text(f"✅ Acceso permanente otorgado a ID: {target_user_id}.")
            try: context.bot.send_message(chat_id=target_user_id, text="🎉 ¡Felicidades! Tienes acceso completo y permanente a Rumbify.")
            except Exception as e: logger.warning(f"No se pudo notificar a {target_user_id} (acceso): {e}")
    except ValueError: update.message.reply_text("ID debe ser numérico.")
    except Exception as e: logger.error(f"Error admin_adduser: {e}"); update.message.reply_text("Ocurrió un error.")

def admin_remove_user_command(update: Update, context: CallbackContext) -> None:
    # (Código idéntico a la última versión estable para Render)
    admin_id = update.effective_user.id
    if admin_id != config.ADMIN_USER_ID: update.message.reply_text("🚫 Permiso denegado."); return
    if not context.args: update.message.reply_text("Uso: /admin_removeuser <ID_usuario>"); return
    try:
        target_user_id = int(context.args[0])
        if db_utils.remove_permanent_access(target_user_id):
            update.message.reply_text(f"✅ Acceso permanente revocado para ID: {target_user_id}.")
            try: context.bot.send_message(chat_id=target_user_id, text="ℹ️ Tu acceso permanente a Rumbify ha sido revocado.")
            except Exception as e: logger.warning(f"No se pudo notificar a {target_user_id} (revocación): {e}")
        else: update.message.reply_text(f"⚠️ No se pudo revocar acceso a {target_user_id} (¿no existía?).")
    except ValueError: update.message.reply_text("ID debe ser numérico.")
    except Exception as e: logger.error(f"Error admin_removeuser: {e}"); update.message.reply_text("Ocurrió un error.")

def get_my_id_command(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_user.id
    update.message.reply_text(f"Tu ID de Telegram es: `{user_id}`", parse_mode=ParseMode.MARKDOWN_V2)