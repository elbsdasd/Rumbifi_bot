import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    CallbackContext,
    ConversationHandler,
    CallbackQueryHandler,
    MessageHandler,
    Filters,
    CommandHandler
)
from datetime import datetime, date # Importar date

import config
from utils import database as db_utils # Interactúa con PostgreSQL
from . import common_handlers

logger = logging.getLogger(__name__)

# Estados de la conversación para Bienestar
(
    STATE_WB_ACTION_SELECT,     # Menú principal de bienestar
    STATE_WB_GET_ITEMS,         # Esperando descripciones de ejercicios o comidas
    STATE_WB_VIEW_ITEMS         # Viendo la lista y esperando callbacks de marcado
) = range(10, 13) # Rango diferente para evitar colisiones

# Claves para context.user_data
UD_WB_CURRENT_TYPE = 'wb_current_type' # 'exercise', 'diet_main', 'diet_extra'
UD_WB_TEMP_ITEMS_COLLECTED = 'wb_temp_items_collected'
UD_WB_CLEANUP_KEYS = [UD_WB_CURRENT_TYPE, UD_WB_TEMP_ITEMS_COLLECTED]


# --- MENÚ PRINCIPAL DE BIENESTAR ---
def wellbeing_menu(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    user_id = query.from_user.id if query else update.effective_user.id

    has_access, access_message = db_utils.check_user_access(user_id)
    if not has_access:
        if query:
            query.answer()
            query.edit_message_text(text=access_message)
        else:
            context.bot.send_message(chat_id=user_id, text=access_message)
        return ConversationHandler.END

    keyboard = [
        [InlineKeyboardButton("🤸 Registrar Rutina de Ejercicios", callback_data=config.CB_WB_REG_EXERCISE)],
        [InlineKeyboardButton("🍎 Registrar Plan de Alimentación Diario", callback_data=config.CB_WB_REG_DIET)], # Diet Main
        [InlineKeyboardButton("👀 Ver Mi Rutina y Marcar Avance", callback_data=config.CB_WB_VIEW_ROUTINE)],
        [InlineKeyboardButton("📖 Ver Mi Dieta y Marcar Avance", callback_data=config.CB_WB_VIEW_DIET)],
        [common_handlers.get_main_menu_button()]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    message_text = (
        "💪 *Bienestar Físico y Mental*\n\n"
        "Un físico fuerte refleja una mente fuerte. ¡Cuidemos ambos! Elige una opción:"
    )
    
    if query:
        query.answer()
        query.edit_message_text(text=message_text, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        context.bot.send_message(chat_id=user_id, text=message_text, reply_markup=reply_markup, parse_mode='Markdown')
        
    return STATE_WB_ACTION_SELECT


# --- INICIO DE FLUJO PARA REGISTRAR ITEMS (EJERCICIOS/DIETA) ---
def start_wb_item_registration(update: Update, context: CallbackContext, item_type: str) -> int:
    query = update.callback_query
    if query: query.answer() # Puede ser llamado sin query si es un reingreso al estado
    
    context.user_data[UD_WB_CURRENT_TYPE] = item_type
    context.user_data[UD_WB_TEMP_ITEMS_COLLECTED] = [] # Reiniciar lista

    prompt_map = {
        'exercise': "🤸 Ejercicios del Día:\n\nEnvía cada ejercicio (ej. 'Planchas 3x15').\nEscribe /donewellbeing al terminar, o /cancelwellbeing.",
        'diet_main': "🍎 Comidas Principales:\n\nRegistra tu desayuno, almuerzo y cena.\nEnvía cada comida. Escribe /donewellbeing al terminar, o /cancelwellbeing.",
        'diet_extra': "🍪 Antojos / Comidas Extra:\n\nRegistra cualquier antojo.\nEnvía cada uno. Escribe /donewellbeing al terminar, o /cancelwellbeing."
    }
    prompt_text = prompt_map.get(item_type, "Registra tus ítems:")

    if query: # Si se llamó desde un botón
        query.edit_message_text(text=prompt_text)
    else: # Si se reingresó al estado (ej. después de un error) o llamado internamente
        context.bot.send_message(chat_id=update.effective_chat.id, text=prompt_text)
        
    return STATE_WB_GET_ITEMS

# Callbacks para los botones del menú de bienestar
def wb_reg_exercise_cb(update: Update, context: CallbackContext) -> int:
    return start_wb_item_registration(update, context, 'exercise')

def wb_reg_diet_main_cb(update: Update, context: CallbackContext) -> int:
    return start_wb_item_registration(update, context, 'diet_main')

def wb_reg_diet_extra_cb(update: Update, context: CallbackContext) -> int: # Llamado desde "Ver Dieta"
    # No hay query.edit_message_text aquí, se envía un nuevo mensaje
    return start_wb_item_registration(update, context, 'diet_extra')


# --- OBTENER DESCRIPCIÓN DE ITEMS (EJERCICIOS/COMIDAS) ---
def get_wb_item_description(update: Update, context: CallbackContext) -> int:
    user_text = update.message.text
    item_type = context.user_data.get(UD_WB_CURRENT_TYPE)
    
    collected_items = context.user_data.get(UD_WB_TEMP_ITEMS_COLLECTED, [])
    collected_items.append(user_text) 
    context.user_data[UD_WB_TEMP_ITEMS_COLLECTED] = collected_items
    
    type_map = {'exercise': 'ejercicio', 'diet_main': 'comida principal', 'diet_extra': 'comida extra'}
    friendly_type = type_map.get(item_type, "ítem")

    update.message.reply_text(f"✅ '{user_text[:30]}...' añadido como {friendly_type}. Envía otro, o /donewellbeing para guardar.")
    return STATE_WB_GET_ITEMS # Mantenerse en este estado


# --- FINALIZAR REGISTRO DE ITEMS DE BIENESTAR ---
def done_wellbeing_items(update: Update, context: CallbackContext) -> int:
    user_id = update.effective_user.id
    item_type = context.user_data.get(UD_WB_CURRENT_TYPE)
    collected_items = context.user_data.get(UD_WB_TEMP_ITEMS_COLLECTED, [])

    if not collected_items:
        update.message.reply_text("No has añadido ningún ítem. Escribe /cancelwellbeing para volver.")
        return STATE_WB_GET_ITEMS # Quedarse esperando ítems
    else:
        today_lima_date_obj = datetime.now(db_utils.LIMA_TZ).date()
        db_utils.save_wellbeing_item( # db_utils ahora usa PostgreSQL
            user_id=user_id,
            item_type=item_type, 
            data_list=collected_items,
            date_obj=today_lima_date_obj
        )
        type_map_plural = {'exercise': 'ejercicios', 'diet_main': 'comidas principales', 'diet_extra': 'comidas extra'}
        friendly_type_plural = type_map_plural.get(item_type, "ítems")
        update.message.reply_text(f"✅ ¡Tus {friendly_type_plural} han sido guardados!")

    return common_handlers.cancel_conversation_to_main_menu(update, context, UD_WB_CLEANUP_KEYS)


# --- VER Y MARCAR ITEMS DE BIENESTAR ---
def view_wellbeing_items_shared_logic(update: Update, context: CallbackContext, view_type: str) -> int:
    """Lógica compartida para mostrar rutina o dieta."""
    query = update.callback_query
    user_id = query.from_user.id if query else update.effective_user.id
    
    if query: query.answer()

    today_lima_date_obj = datetime.now(db_utils.LIMA_TZ).date()
    # doc_and_items ahora tiene: {"key": doc_id, "items": [sub_items_list], "type": ..., "date": ...}
    doc_and_items = db_utils.get_daily_wellbeing_doc_and_items(user_id, view_type, today_lima_date_obj)

    title_map = {'exercise': '🤸 Tu Rutina de Hoy:', 'diet_main': '🍎 Tu Dieta de Hoy:'}
    message_text = f"*{title_map.get(view_type, 'Tus Items:')}*\n\n"
    keyboard_markup_rows = []

    if not doc_and_items or not doc_and_items.get("items"):
        message_text += "No has registrado nada para hoy."
    else:
        # doc_id = doc_and_items['key'] # No necesitamos doc_id para construir el callback, usamos sub_item_id
        sub_items_list = doc_and_items.get("items", [])

        for item_data_dictrow in sub_items_list: # item_data_dictrow es un DictRow
            item_data = dict(item_data_dictrow) # Convertir a dict
            status_emoji = "⏳" 
            if item_data.get("marked_at"):
                status_emoji = "✅" if item_data.get("completed") else "❌"
            
            message_text += f"{status_emoji} {item_data['text']}\n"
            
            if item_data.get("completed") is False or item_data.get("completed") is None: # Solo si no completado o no marcado
                sub_item_id = item_data['key'] # 'key' ahora es 'sub_item_id'
                cb_done = f"{config.CB_TASK_DONE_PREFIX}wb_{view_type}_{sub_item_id}"
                cb_not_done = f"{config.CB_TASK_NOT_DONE_PREFIX}wb_{view_type}_{sub_item_id}"
                
                item_short_text = item_data['text'][:15] + ('...' if len(item_data['text']) > 15 else '')
                buttons_row = [
                    InlineKeyboardButton(f"✅ Hecho '{item_short_text}'", callback_data=cb_done),
                    InlineKeyboardButton(f"❌ No '{item_short_text}'", callback_data=cb_not_done)
                ]
                keyboard_markup_rows.append(buttons_row)
        message_text += "\n"

    if view_type == 'diet_main':
        keyboard_markup_rows.append([InlineKeyboardButton("🍪 Registrar Antojos / Extras", callback_data=config.CB_WB_REG_EXTRAS)])
    
    keyboard_markup_rows.append([common_handlers.get_back_button(config.CB_WB_MAIN_MENU, "⬅️ Volver a Bienestar")])
    reply_markup = InlineKeyboardMarkup(keyboard_markup_rows)
    
    if query:
        try:
            query.edit_message_text(text=message_text, reply_markup=reply_markup, parse_mode='Markdown')
        except Exception as e:
            logger.warning(f"Error editando vista de bienestar, enviando nuevo: {e}")
            context.bot.send_message(chat_id=user_id, text=message_text, reply_markup=reply_markup, parse_mode='Markdown')
    else:
         context.bot.send_message(chat_id=user_id, text=message_text, reply_markup=reply_markup, parse_mode='Markdown')
        
    return STATE_WB_VIEW_ITEMS # Estado para esperar callbacks de marcado o registrar extras

# Callbacks para ver rutina y dieta
def wb_view_routine_cb(update: Update, context: CallbackContext) -> int:
    return view_wellbeing_items_shared_logic(update, context, 'exercise')

def wb_view_diet_cb(update: Update, context: CallbackContext) -> int:
    return view_wellbeing_items_shared_logic(update, context, 'diet_main')


def mark_wb_item_cb(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    query.answer()
    callback_data = query.data
    
    try:
        # Formato: CB_TASK_DONE_PREFIX + "wb_" + view_type + _ + sub_item_id
        parts = callback_data.split('_') # task_done_wb_exercise_123
        action_type = parts[0] + "_" + parts[1] # task_done_wb
        view_type_from_cb = parts[2] # 'exercise' o 'diet_main'
        sub_item_id = int(parts[3])

        completed_status = (action_type == config.CB_TASK_DONE_PREFIX[:-1] + "wb") # "task_donewb"
        
        db_utils.update_wellbeing_sub_item_status(sub_item_id, completed_status) # Usa sub_item_id
        
        # Refrescar la vista
        return view_wellbeing_items_shared_logic(update, context, view_type_from_cb)

    except (IndexError, ValueError) as e:
        logger.error(f"Error parseando callback_data para marcar wb_item: {e}, data: {callback_data}")
        query.message.reply_text("⚠️ Error al procesar la acción.")
    except Exception as e:
        logger.error(f"Error general marcando wb_item: {e}, data: {callback_data}")
        query.message.reply_text("⚠️ Error inesperado al marcar el ítem.")
        
    return STATE_WB_VIEW_ITEMS # Quedarse en la vista


# --- CANCELACIÓN ---
def cancel_wellbeing_flow_command(update: Update, context: CallbackContext) -> int:
    return common_handlers.cancel_conversation_to_main_menu(update, context, UD_WB_CLEANUP_KEYS)


# --- CONVERSATION HANDLER ---
def get_wellbeing_conversation_handler() -> ConversationHandler:
    # Handler para AÑADIR ítems (ejercicios, comidas principales, comidas extra)
    add_wb_item_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(wb_reg_exercise_cb, pattern=f"^{config.CB_WB_REG_EXERCISE}$"),
            CallbackQueryHandler(wb_reg_diet_main_cb, pattern=f"^{config.CB_WB_REG_DIET}$"),
            CallbackQueryHandler(wb_reg_diet_extra_cb, pattern=f"^{config.CB_WB_REG_EXTRAS}$"), # Desde "Ver Dieta"
        ],
        states={
            STATE_WB_GET_ITEMS: [MessageHandler(Filters.text & ~Filters.command, get_wb_item_description)],
        },
        fallbacks=[
            CommandHandler("donewellbeing", done_wellbeing_items),
            CommandHandler("cancelwellbeing", cancel_wellbeing_flow_command),
        ],
        map_to_parent={ConversationHandler.END: STATE_WB_ACTION_SELECT } # Volver al menú de bienestar
    )
    
    # Handler para la sección de VER y MARCAR ítems
    view_mark_wb_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(wb_view_routine_cb, pattern=f"^{config.CB_WB_VIEW_ROUTINE}$"),
            CallbackQueryHandler(wb_view_diet_cb, pattern=f"^{config.CB_WB_VIEW_DIET}$"),
        ],
        states={
            STATE_WB_VIEW_ITEMS: [ # Esperando callbacks de marcar o el botón de registrar extras
                CallbackQueryHandler(mark_wb_item_cb, pattern=f"^{config.CB_TASK_DONE_PREFIX}wb_"),
                CallbackQueryHandler(mark_wb_item_cb, pattern=f"^{config.CB_TASK_NOT_DONE_PREFIX}wb_"),
                # El botón de "Registrar Extras" (CB_WB_REG_EXTRAS) ahora es un entry point 
                # al add_wb_item_handler, por lo que no necesita estar aquí explícitamente si
                # el add_wb_item_handler está anidado o es el siguiente en la cadena.
                # Si no está anidado, necesitamos una forma de transitar.
                # Para simplificar, asumimos que CB_WB_REG_EXTRAS inicia una nueva instancia de add_wb_item_handler.
                CallbackQueryHandler(wellbeing_menu, pattern=f"^{config.CB_WB_MAIN_MENU}$"), # Volver al menú de bienestar
            ]
        },
        fallbacks=[
            CommandHandler("cancelwellbeing", cancel_wellbeing_flow_command),
            CallbackQueryHandler(wellbeing_menu, pattern=f"^{config.CB_WB_MAIN_MENU}$") # Botón volver
            ],
         map_to_parent={ConversationHandler.END: -1 } # Fin de este flujo, no afecta otros.
    )


    return [add_wb_item_handler, view_mark_wb_handler] # Devolver una lista de handlers


def register_handlers(dp) -> None:
    handlers_list = get_wellbeing_conversation_handler()
    for handler in handlers_list:
        dp.add_handler(handler)
    
    # El CallbackQueryHandler para el menú de bienestar (CB_WB_MAIN_MENU)
    # se registra en main.py, y llama a wellbeing.wellbeing_menu.
    # wellbeing_menu sirve como entry point para los ConversationHandlers definidos aquí.