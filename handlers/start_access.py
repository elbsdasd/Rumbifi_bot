import logging
from telegram import Update, ParseMode, InlineKeyboardMarkup
from telegram.ext import CallbackContext, ConversationHandler # Para ConversationHandler.END si se usa en cancel

import config
from utils import database as db_utils # Interactúa con la nueva DB
from . import common_handlers # Para el teclado del menú

logger = logging.getLogger(__name__)

WELCOME_MESSAGES = [
    "¡Hola! 👋 Soy Rumbify, tu mejor amigo que te ayudará a organizar tu día a día 📅 y tomar el control de tu vida ✨.",
    "A partir de hoy, tú liderarás el rumbo de tu historia 🚀.",
    "Te acompañaré paso a paso para que seas más productiv@ 💪, disciplinad@ y sobre todo, ¡constante! 🎯",
    "Con esfuerzo y perseverancia, ¡vamos a alcanzar tus sueños! 🌟"
]
VIDEO_PATH = "assets/Video_1.mp4"

def send_main_menu(update: Update, context: CallbackContext, user_id: int, message_text: str = "Aquí tienes el menú principal de Rumbify:", edit_message: bool = False):
    """Envía o edita el mensaje con el menú principal."""
    keyboard = common_handlers.get_main_menu_keyboard()
    
    target_chat_id = user_id # El ID del usuario al que se enviará el mensaje

    # Determinar si se debe editar o enviar un nuevo mensaje
    should_edit = edit_message and update.callback_query and update.callback_query.message
    
    try:
        if should_edit:
            update.callback_query.edit_message_text(text=message_text, reply_markup=keyboard)
        elif update.message: # Si es un comando o mensaje de texto
            update.message.reply_text(message_text, reply_markup=keyboard)
        elif update.callback_query: # Si es un callback pero no se va a editar (ej. después de una acción)
            context.bot.send_message(chat_id=target_chat_id, text=message_text, reply_markup=keyboard)
        else: # Fallback si no hay update.message ni update.callback_query (ej. llamado internamente después de cancelar)
            context.bot.send_message(chat_id=target_chat_id, text=message_text, reply_markup=keyboard)
    except Exception as e:
        logger.warning(f"Error enviando/editando menú principal para {target_chat_id} (edit={should_edit}): {e}. Enviando como nuevo mensaje.")
        # Fallback a enviar un nuevo mensaje si la edición falla
        try:
            context.bot.send_message(chat_id=target_chat_id, text=message_text, reply_markup=keyboard)
        except Exception as e2:
            logger.error(f"Fallo crítico enviando menú principal a {target_chat_id}: {e2}")


def start_command(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    user_id = user.id
    logger.info(f"Usuario {user_id} ({user.username or user.first_name}) inició /start (Render version).")

    has_access, access_message = db_utils.check_user_access(user_id) # db_utils ahora usa PostgreSQL
    if not has_access:
        update.message.reply_text(access_message)
        return

    for msg in WELCOME_MESSAGES:
        update.message.reply_text(msg)

    try:
        with open(VIDEO_PATH, 'rb') as video_file:
            context.bot.send_video(chat_id=user_id, video=video_file, caption="🎬 ¡Prepárate para tomar el control!")
        logger.info(f"Video enviado a {user_id}")
    except FileNotFoundError:
        logger.warning(f"Video no encontrado en {VIDEO_PATH}. No se envió video a {user_id}.")
        update.message.reply_text("ℹ️ (Video de introducción no disponible en este momento)")
    except Exception as e:
        logger.error(f"Error enviando video a {user_id}: {e}")
        update.message.reply_text("⚠️ Hubo un problema al intentar mostrar el video de introducción.")

    send_main_menu(update, context, user_id)

def main_menu_command(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_user.id
    has_access, access_message = db_utils.check_user_access(user_id)
    if not has_access:
        update.message.reply_text(access_message)
        return
    send_main_menu(update, context, user_id, "Volviendo al menú principal:")

def main_menu_button(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    query.answer()
    user_id = query.from_user.id
    
    has_access, access_message = db_utils.check_user_access(user_id)
    if not has_access:
        try: # Intentar editar si es posible
            query.edit_message_text(text=access_message) 
        except Exception: # Si no, enviar nuevo
            context.bot.send_message(chat_id=user_id, text=access_message)
        return
        
    send_main_menu(update, context, user_id, edit_message=True)


def admin_add_user_command(update: Update, context: CallbackContext) -> None:
    admin_id = update.effective_user.id
    if admin_id != config.ADMIN_USER_ID:
        update.message.reply_text("🚫 No tienes permiso para usar este comando.")
        return

    if not context.args:
        update.message.reply_text("Uso: /admin_adduser <ID_del_usuario_de_Telegram>")
        return

    try:
        target_user_id = int(context.args[0])
        if db_utils.add_permanent_access(target_user_id): # db_utils ahora usa PostgreSQL
            update.message.reply_text(f"✅ Acceso permanente otorgado al usuario ID: {target_user_id}.")
            try:
                context.bot.send_message(
                    chat_id=target_user_id,
                    text="🎉 ¡Felicidades! Has recibido acceso completo y permanente a Rumbify."
                )
            except Exception as e:
                logger.warning(f"No se pudo notificar al usuario {target_user_id} sobre el acceso: {e}")
        else: # add_permanent_access ahora siempre retorna True si no hay excepción
            update.message.reply_text(f"Acceso otorgado o ya existente para {target_user_id}.")
    except ValueError:
        update.message.reply_text("El ID del usuario debe ser un número.")
    except Exception as e:
        logger.error(f"Error en admin_adduser: {e}")
        update.message.reply_text("Ocurrió un error procesando el comando.")


def admin_remove_user_command(update: Update, context: CallbackContext) -> None:
    admin_id = update.effective_user.id
    if admin_id != config.ADMIN_USER_ID:
        update.message.reply_text("🚫 No tienes permiso para usar este comando.")
        return

    if not context.args:
        update.message.reply_text("Uso: /admin_removeuser <ID_del_usuario_de_Telegram>")
        return

    try:
        target_user_id = int(context.args[0])
        if db_utils.remove_permanent_access(target_user_id): # db_utils ahora usa PostgreSQL
            update.message.reply_text(f"✅ Acceso permanente revocado para el usuario ID: {target_user_id}.")
            try:
                context.bot.send_message(
                    chat_id=target_user_id,
                    text="ℹ️ Tu acceso permanente a Rumbify ha sido revocado por un administrador."
                )
            except Exception as e:
                logger.warning(f"No se pudo notificar al usuario {target_user_id} sobre la revocación: {e}")
        else:
            update.message.reply_text(f"⚠️ No se pudo revocar acceso a {target_user_id} (quizás el usuario no existía).")
    except ValueError:
        update.message.reply_text("El ID del usuario debe ser un número.")
    except Exception as e:
        logger.error(f"Error en admin_removeuser: {e}")
        update.message.reply_text("Ocurrió un error procesando el comando.")

def get_my_id_command(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_user.id
    update.message.reply_text(f"Tu ID de Telegram es: `{user_id}`", parse_mode=ParseMode.MARKDOWN_V2)