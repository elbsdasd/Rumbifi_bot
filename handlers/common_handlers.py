# handlers/common_handlers.py

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackContext, ConversationHandler

import config
# Import db_utils aquí si cancel_conversation_to_main_menu lo necesita directamente para check_user_access
from utils import database as db_utils # Necesario para el check_user_access en la función de cancelar

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
    """Devuelve un botón para volver al menú principal del bot."""
    return InlineKeyboardButton(text, callback_data=config.CB_MAIN_MENU) # CB_MAIN_MENU es para el menú del bot

def get_back_button(callback_data_target: str, text: str = "⬅️ Volver") -> InlineKeyboardButton:
    """Devuelve un botón de 'Volver' genérico que apunta a un callback_data específico."""
    return InlineKeyboardButton(text, callback_data=callback_data_target)


# --- FUNCIONES DE UTILIDAD PARA HANDLERS ---
def cancel_conversation_to_main_menu(update: Update, context: CallbackContext, flow_specific_cleanup_keys: list = None) -> int:
    """
    Función genérica para cancelar una conversación y volver al menú principal del bot.
    Limpia claves específicas del flujo en user_data.
    """
    user = update.effective_user
    cancel_message_text = f"Operación cancelada, {user.first_name}."
    
    # Limpiar datos de contexto específicos del flujo
    if flow_specific_cleanup_keys:
        for key in flow_specific_cleanup_keys:
            if key in context.user_data:
                del context.user_data[key]
    
    # Limpiar claves genéricas de conversación si existen
    generic_conv_keys = ['current_flow_data', 'temp_messages', 
                         'plan_current_type', 'plan_temp_description', 'plan_temp_reminder_time', 
                         'plan_important_tasks_collected', 'plan_secondary_tasks_collected',
                         'wb_current_type', 'wb_temp_items_collected',
                         'fin_current_trans_type', 'fin_temp_amount']
    for key in generic_conv_keys:
        if key in context.user_data:
            del context.user_data[key]

    # Informar al usuario y enviar menú principal
    if update.message: # Si se canceló por comando
        update.message.reply_text(cancel_message_text)
    elif update.callback_query: # Si se canceló por botón (aunque no hay uno genérico de cancelar con callback)
        try:
            update.callback_query.answer("Operación cancelada.")
            # Enviar nuevo mensaje en lugar de editar para el menú
        except Exception: pass # Ignorar si el answer falla

    # Reutilizar la función send_main_menu de start_access para mostrar el menú
    # Esto requiere una importación tardía o pasar la función como argumento para evitar circularidad.
    # La mejor forma es que el ConversationHandler que usa esto simplemente termine (return ConversationHandler.END)
    # y que el usuario use /menu o que un handler de nivel superior (si existe) tome el control.
    # O, si esta función es el fallback de un ConvHandler, el ConvHandler puede tener un entry_point
    # que sea el menú principal.

    # Por ahora, enviaremos el menú desde aquí después de cancelar.
    from .start_access import send_main_menu_message # Renombrar para claridad
    
    has_access, _ = db_utils.check_user_access(user.id)
    if has_access:
        send_main_menu_message(context, user.id, message_text="Operación cancelada. Aquí tienes el menú principal:")
    else:
        # Si no tiene acceso, el check_user_access ya habrá enviado un mensaje.
        # O enviar un mensaje genérico de cancelación si es necesario.
        if update.message is None and update.callback_query: # Si fue callback, pero no tiene acceso
             context.bot.send_message(chat_id=user.id, text=cancel_message_text + " Acceso restringido.")
        # (El mensaje de no acceso ya debería manejarse de forma centralizada por check_user_access)
            
    return ConversationHandler.END