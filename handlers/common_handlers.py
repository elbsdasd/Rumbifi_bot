# handlers/common_handlers.py

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackContext, ConversationHandler

import config
from utils import database as db_utils # Para check_user_access en la cancelación

# --- TECLADOS COMUNES ---
def get_main_menu_keyboard() -> InlineKeyboardMarkup:
    """Devuelve el teclado del menú principal del bot."""
    keyboard = [
        [InlineKeyboardButton("🗓️ Planificar Mi Día", callback_data=config.CB_PLAN_MAIN_MENU)],
        [InlineKeyboardButton("💪 Bienestar Físico y Mental", callback_data=config.CB_WB_MAIN_MENU)],
        [InlineKeyboardButton("💰 Mis Finanzas", callback_data=config.CB_FIN_MAIN_MENU)],
        [InlineKeyboardButton("📊 Ver Mi Progreso", callback_data=config.CB_PROG_MAIN_MENU)],
    ]
    return InlineKeyboardMarkup(keyboard)

def get_back_to_main_menu_button(text: str = "⬅️ Volver al Menú Principal") -> InlineKeyboardButton:
    """Devuelve un botón para volver al menú principal del bot (CB_MAIN_MENU)."""
    return InlineKeyboardButton(text, callback_data=config.CB_MAIN_MENU)

def get_back_button(callback_data_target: str, text: str = "⬅️ Volver") -> InlineKeyboardButton:
    """Devuelve un botón de 'Volver' genérico que apunta a un callback_data específico."""
    return InlineKeyboardButton(text, callback_data=callback_data_target)


# --- FUNCIONES DE UTILIDAD PARA HANDLERS ---
def clear_conversation_user_data(context: CallbackContext, specific_keys: list = None):
    """Limpia claves de user_data relacionadas con conversaciones."""
    keys_to_clear = ['plan_current_item_type', 'plan_temp_description_list',
                     'wb_current_item_type', 'wb_temp_collected_items',
                     'fin_current_transaction_type'] # Añadir más si es necesario
    if specific_keys:
        keys_to_clear.extend(specific_keys)
    
    for key in keys_to_clear:
        if key in context.user_data:
            del context.user_data[key]

def cancel_conversation_and_show_main_menu(update: Update, context: CallbackContext, cleanup_keys: list = None) -> int:
    """
    Cancela una conversación, limpia user_data y muestra el menú principal del bot.
    """
    user = update.effective_user
    cancel_message_text = f"Operación cancelada, {user.first_name}."
    
    clear_conversation_user_data(context, cleanup_keys) # Limpiar user_data

    if update.message: # Si se canceló por comando /cancel o similar
        update.message.reply_text(cancel_message_text)
    elif update.callback_query: # Si se canceló por un botón de "cancelar" (si existiera)
        try:
            update.callback_query.answer("Operación cancelada.")
        except Exception: pass

    # Enviar el menú principal del bot. Necesitamos la función de start_access.
    # Para evitar importación circular, el handler que llama a esto debe asegurarse
    # de que el ConversationHandler termine y se pueda volver al menú.
    # O, como hacemos aquí, tener una forma de llamarlo.
    from .start_access import send_bot_main_menu # Renombrada y adaptada
    
    has_access, _ = db_utils.check_user_access(user.id)
    if has_access:
        # Enviar como nuevo mensaje para evitar problemas con edit_message_text
        send_bot_main_menu(context, user.id, message_text="Aquí tienes el menú principal:")
    else:
        # Si no tiene acceso, el check_user_access ya debería haber manejado el mensaje.
        # Si fue un callback, enviar un simple mensaje de cancelación si el de no acceso no se envió.
        if update.callback_query and update.callback_query.message:
             context.bot.send_message(chat_id=user.id, text=cancel_message_text + " Acceso restringido.")
        # El mensaje de "no acceso" debería ser la respuesta principal.
            
    return ConversationHandler.END