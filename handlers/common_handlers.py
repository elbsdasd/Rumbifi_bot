from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackContext, ConversationHandler # Importar ConversationHandler
import config

# --- TECLADOS COMUNES ---
def get_main_menu_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("🗓️ Planificar Mi Día", callback_data=config.CB_PLAN_MAIN_MENU)],
        [InlineKeyboardButton("💪 Bienestar Físico y Mental", callback_data=config.CB_WB_MAIN_MENU)],
        [InlineKeyboardButton("💰 Mis Finanzas", callback_data=config.CB_FIN_MAIN_MENU)],
        [InlineKeyboardButton("📊 Ver Mi Progreso", callback_data=config.CB_PROG_MAIN_MENU)],
    ]
    return InlineKeyboardMarkup(keyboard)

def get_back_to_main_menu_button() -> InlineKeyboardButton:
    return InlineKeyboardButton("⬅️ Volver al Menú Principal", callback_data=config.CB_MAIN_MENU)

def get_back_button(callback_data_target: str, text: str = "⬅️ Volver") -> InlineKeyboardButton:
    return InlineKeyboardButton(text, callback_data=callback_data_target)


# --- FUNCIONES DE UTILIDAD PARA HANDLERS ---
def cancel_conversation_to_main_menu(update: Update, context: CallbackContext, flow_specific_cleanup_keys: list = None) -> int:
    """
    Función genérica para cancelar una conversación y volver al menú principal.
    Limpia claves específicas del flujo en user_data.
    """
    user = update.effective_user
    cancel_message = f"Operación cancelada, {user.first_name}. Volviendo al menú principal."

    if update.message:
        update.message.reply_text(cancel_message)
    elif update.callback_query:
        try:
            update.callback_query.answer("Operación cancelada.")
            # Es mejor enviar un nuevo mensaje para el menú que editar,
            # ya que el mensaje original podría no ser adecuado para el menú.
            # update.callback_query.edit_message_text(text=cancel_message) # Evitar esto
        except Exception:
            pass # No importa si falla el answer o edit

    # Limpiar datos de contexto específicos del flujo
    if flow_specific_cleanup_keys:
        for key in flow_specific_cleanup_keys:
            if key in context.user_data:
                del context.user_data[key]
    
    # También limpiar claves genéricas si existen
    generic_keys_to_clear = ['current_flow_data', 'temp_messages']
    for key in generic_keys_to_clear:
        if key in context.user_data:
            del context.user_data[key]
            
    # Enviar menú principal después de cancelar
    # Necesitamos importar la función send_main_menu de start_access.py
    # Esto puede crear una dependencia circular si no se maneja con cuidado.
    # Una mejor práctica es que main.py maneje el envío del menú principal
    # o que esta función devuelva un estado especial que main.py interprete.
    # Por ahora, para simplificar, asumimos que se puede llamar a una función que envíe el menú.
    # O que simplemente terminamos la conversación y el usuario usa /menu o /start.

    # Para evitar la importación circular directa aquí, es mejor que el ConversationHandler
    # que usa esta función, en su `fallbacks` o después de que esta función retorne END,
    # llame a la función que muestra el menú principal.
    # Por ahora, esta función solo se encarga de la limpieza y el mensaje de cancelación.
    # El retorno de ConversationHandler.END es lo principal.
    
    # El handler que llama a esta función se encargará de redirigir al menú
    # por ejemplo, haciendo que el ConversationHandler termine y el usuario
    # vuelva a usar /menu, o el ConversationHandler padre tome el control.
    
    # Enviar menú principal como nuevo mensaje
    from .start_access import send_main_menu # Importación tardía
    # Verificar si el usuario tiene acceso antes de mostrar el menú
    has_access, _ = db_utils.check_user_access(user.id)
    if has_access:
        send_main_menu(update, context, user_id=user.id, message_text="Operación cancelada. Aquí tienes el menú principal:")
    else:
        # Si no tiene acceso, no mostrar menú, el check_user_access ya habrá enviado un mensaje.
        # O enviar un mensaje genérico si es necesario.
        if update.callback_query:
             context.bot.send_message(chat_id=user.id, text="Operación cancelada.")
        # El mensaje de no acceso ya se debería haber manejado por check_user_access.
        
    return ConversationHandler.END