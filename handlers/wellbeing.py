# handlers/wellbeing.py

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
from datetime import datetime, date

import config
from utils import database as db_utils
from . import common_handlers

logger = logging.getLogger(__name__)

# Estados de la conversación para TODA la sección de Bienestar
(
    STATE_WB_MENU_ACTION,        # 0: Menú principal de bienestar, esperando selección
    STATE_WB_ADD_GET_ITEMS_INPUT, # 1: Esperando descripciones de ejercicios o comidas para añadir
    STATE_WB_VIEW_AND_MARK_MODE  # 2: Viendo la lista (rutina/dieta), esperando acción de marcar o registrar extras
) = range(40, 43) 

# Claves para context.user_data
UD_WB_CURRENT_ITEM_TYPE = 'wb_current_item_type' # 'exercise', 'diet_main', 'diet_extra'
UD_WB_TEMP_COLLECTED_ITEMS = 'wb_temp_collected_items'
UD_WB_CURRENT_VIEW_TYPE = 'wb_current_view_type' # Para saber qué vista refrescar ('exercise' o 'diet_main')
UD_WB_CLEANUP_KEYS = [UD_WB_CURRENT_ITEM_TYPE, UD_WB_TEMP_COLLECTED_ITEMS, UD_WB_CURRENT_VIEW_TYPE]


# --- MENÚ PRINCIPAL DE BIENESTAR (Entry Point) ---
def wellbeing_menu(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    user_id = query.from_user.id if query else update.effective_user.id

    has_access, access_message = db_utils.check_user_access(user_id)
    if not has_access:
        if query: query.answer(); query.edit_message_text(text=access_message)
        else: context.bot.send_message(chat_id=user_id, text=access_message)
        return ConversationHandler.END

    keyboard = [
        [InlineKeyboardButton("🤸 Registrar Rutina de Ejercicios", callback_data=config.CB_WB_REG_EXERCISE)],
        [InlineKeyboardButton("🍎 Registrar Comidas Principales", callback_data=config.CB_WB_REG_DIET)],
        [InlineKeyboardButton("👀 Ver Rutina y Marcar", callback_data=config.CB_WB_VIEW_ROUTINE)],
        [InlineKeyboardButton("📖 Ver Dieta y Marcar", callback_data=config.CB_WB_VIEW_DIET)],
        [common_handlers.get_back_to_main_menu_button()]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    message_text = (
        "💪 *Bienestar Físico y Mental*\n\n"
        "Un cuerpo sano y una mente clara son fundamentales. Aquí puedes llevar un registro de tus hábitos saludables.\n"
        "Elige una opción:"
    )
    
    if query:
        query.answer()
        query.edit_message_text(text=message_text, reply_markup=reply_markup, parse_mode='Markdown')
    else: 
        context.bot.send_message(chat_id=user_id, text=message_text, reply_markup=reply_markup, parse_mode='Markdown')
    return STATE_WB_MENU_ACTION


# --- INICIO FLUJO: AÑADIR ITEMS DE BIENESTAR ---
def start_add_wb_item_flow(update: Update, context: CallbackContext, item_type: str) -> int:
    query = update.callback_query
    if query: query.answer()
    
    context.user_data[UD_WB_CURRENT_ITEM_TYPE] = item_type
    context.user_data[UD_WB_TEMP_COLLECTED_ITEMS] = []

    prompt_map = {
        'exercise': "🤸 *Registrar Ejercicios del Día:*\n\nEnvía cada ejercicio o serie que realizarás (ej. 'Correr 30 min', 'Sentadillas 3x12').\nEscribe /donewellbeing cuando termines, o /cancelwellbeing para volver.",
        'diet_main': "🍎 *Registrar Comidas Principales:*\n\nRegistra tu desayuno, almuerzo y cena (ej. 'Desayuno: Avena con frutas y nueces').\nEnvía cada comida por separado. Escribe /donewellbeing al terminar, o /cancelwellbeing para volver.",
        'diet_extra': "🍪 *Registrar Antojos / Comidas Extra:*\n\n¿Tuviste algún antojo o comida fuera de tu plan principal? Regístralo aquí (ej. 'Galleta de chocolate', 'Puñado de almendras').\nEnvía cada uno. Escribe /donewellbeing al terminar, o /cancelwellbeing para volver."
    }
    prompt_text = prompt_map.get(item_type)

    target_chat_id = query.message.chat_id if query and query.message else update.effective_chat.id
    if query and query.message: query.edit_message_text(text=prompt_text, parse_mode='Markdown')
    else: context.bot.send_message(chat_id=target_chat_id, text=prompt_text, parse_mode='Markdown')
    return STATE_WB_ADD_GET_ITEMS_INPUT

# Callbacks para los botones de añadir (desde STATE_WB_MENU_ACTION o STATE_WB_VIEW_AND_MARK_MODE)
def cb_wb_reg_exercise_action(update: Update, context: CallbackContext) -> int:
    return start_add_wb_item_flow(update, context, 'exercise')
def cb_wb_reg_diet_main_action(update: Update, context: CallbackContext) -> int:
    return start_add_wb_item_flow(update, context, 'diet_main')
def cb_wb_reg_diet_extra_action(update: Update, context: CallbackContext) -> int: # Desde "Ver Dieta"
    return start_add_wb_item_flow(update, context, 'diet_extra')


def get_wb_item_input(update: Update, context: CallbackContext) -> int:
    user_text = update.message.text.strip()
    if not user_text:
        update.message.reply_text("La descripción no puede estar vacía. Intenta de nuevo o usa /cancelwellbeing.")
        return STATE_WB_ADD_GET_ITEMS_INPUT
        
    collected_items = context.user_data.get(UD_WB_TEMP_COLLECTED_ITEMS, [])
    collected_items.append(user_text)
    context.user_data[UD_WB_TEMP_COLLECTED_ITEMS] = collected_items
    
    item_type = context.user_data.get(UD_WB_CURRENT_ITEM_TYPE)
    type_map = {'exercise': 'ejercicio', 'diet_main': 'comida principal', 'diet_extra': 'comida extra'}
    friendly_type = type_map.get(item_type, "ítem")
    update.message.reply_text(f"✅ '{user_text[:30]}...' añadido como {friendly_type}. Envía otro, o /donewellbeing para guardar.")
    return STATE_WB_ADD_GET_ITEMS_INPUT

def done_adding_wb_items_command(update: Update, context: CallbackContext) -> int: # /donewellbeing
    user_id = update.effective_user.id
    item_type = context.user_data.get(UD_WB_CURRENT_ITEM_TYPE)
    collected_items = context.user_data.get(UD_WB_TEMP_COLLECTED_ITEMS, [])

    if not collected_items:
        update.message.reply_text("No has añadido ítems. Escribe /cancelwellbeing para volver.")
        return STATE_WB_ADD_GET_ITEMS_INPUT
    else:
        today_date_obj = datetime.now(db_utils.LIMA_TZ).date()
        db_utils.save_wellbeing_items_list(user_id, item_type, collected_items, today_date_obj)
        type_map_plural = {'exercise': 'ejercicios', 'diet_main': 'comidas principales', 'diet_extra': 'comidas extra'}
        update.message.reply_text(f"✅ ¡Tus {type_map_plural.get(item_type, 'ítems')} han sido guardados!")

    return cancel_wellbeing_subflow(update, context) # Vuelve al menú de bienestar

def cancel_wellbeing_subflow(update: Update, context: CallbackContext) -> int: # /cancelwellbeing
    """Cancela el subflujo de añadir y vuelve al menú de bienestar."""
    for key in UD_WB_CLEANUP_KEYS: # Limpia solo las claves de este flujo
        if key in context.user_data: del context.user_data[key]
    if update.message: update.message.reply_text("Subproceso cancelado.")
    elif update.callback_query: update.callback_query.answer("Cancelado.")
    return wellbeing_menu(update, context) # Vuelve al menú de bienestar


# --- FLUJO: VER Y MARCAR ITEMS DE BIENESTAR ---
def view_wb_items_action_cb(update: Update, context: CallbackContext, view_type: str) -> int:
    query = update.callback_query
    user_id = query.from_user.id
    if query: query.answer()

    context.user_data[UD_WB_CURRENT_VIEW_TYPE] = view_type # Guardar para el refresco
    today_date_obj = datetime.now(db_utils.LIMA_TZ).date()
    doc_and_items = db_utils.get_daily_wellbeing_doc_and_sub_items(user_id, view_type, today_date_obj)

    title_map = {'exercise': '🤸 Tu Rutina de Hoy:', 'diet_main': '🍎 Tu Dieta de Hoy:'}
    message_text = f"*{title_map.get(view_type, 'Tus Items:')}*\n\n"
    keyboard_rows = []

    if not doc_and_items or not doc_and_items.get("items"):
        message_text += "No has registrado nada para hoy."
    else:
        sub_items_list = doc_and_items.get("items", [])
        for item_dr in sub_items_list:
            item = dict(item_dr)
            status = "⏳"
            if item.get("completed") is True: status = "✅"
            elif item.get("completed") is False: status = "❌"
            message_text += f"{status} {item['text']}\n"
            if item.get("completed") is None or item.get("completed") is False : # Mostrar si no completado o no marcado
                sub_id = item['key']; cb_d = f"{config.CB_TASK_DONE_PREFIX}wb_{view_type}_{sub_id}"; cb_nd = f"{config.CB_TASK_NOT_DONE_PREFIX}wb_{view_type}_{sub_id}"
                txt_s = item['text'][:15] + ('…'if len(item['text'])>15 else '')
                keyboard_rows.append([InlineKeyboardButton(f"✅ '{txt_s}'", cb_d), InlineKeyboardButton(f"❌ '{txt_s}'", cb_nd)])
        message_text += "\n"

    if view_type == 'diet_main': # Solo en la vista de dieta principal
        keyboard_rows.append([InlineKeyboardButton("🍪 Registrar Antojos/Extras", callback_data=config.CB_WB_REG_EXTRAS)])
    keyboard_rows.append([common_handlers.get_back_button(config.CB_WB_MAIN_MENU, "⬅️ A Bienestar")])
    
    reply_markup = InlineKeyboardMarkup(keyboard_rows)
    if query.message: query.edit_message_text(text=message_text, reply_markup=reply_markup, parse_mode='Markdown')
    else: context.bot.send_message(chat_id=user_id, text=message_text, reply_markup=reply_markup, parse_mode='Markdown')
    return STATE_WB_VIEW_AND_MARK_MODE

# Callbacks para los botones de ver
def cb_wb_view_routine_action(update: Update, context: CallbackContext) -> int:
    return view_wb_items_action_cb(update, context, 'exercise')
def cb_wb_view_diet_action(update: Update, context: CallbackContext) -> int:
    return view_wb_items_action_cb(update, context, 'diet_main')

def mark_wb_sub_item_cb(update: Update, context: CallbackContext) -> int:
    query = update.callback_query; query.answer()
    try:
        parts = query.data.split('_'); view_type = parts[2]; sub_item_id = int(parts[3])
        completed = (parts[0]+"_"+parts[1] == config.CB_TASK_DONE_PREFIX[:-1] + "wb")
        db_utils.update_wellbeing_sub_item_status(sub_item_id, completed)
        return view_wb_items_action_cb(update, context, view_type) # Refrescar
    except Exception as e:
        logger.error(f"Error marcando sub-ítem bienestar: {e}, data: {query.data}")
        if query.message: query.message.reply_text("⚠️ Error al marcar.")
    return STATE_WB_VIEW_AND_MARK_MODE


# --- REGISTRO DE HANDLERS ---
def register_handlers(dp) -> None:
    wb_conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(wellbeing_menu, pattern=f"^{config.CB_WB_MAIN_MENU}$")],
        states={
            STATE_WB_MENU_ACTION: [
                CallbackQueryHandler(cb_wb_reg_exercise_action, pattern=f"^{config.CB_WB_REG_EXERCISE}$"),
                CallbackQueryHandler(cb_wb_reg_diet_main_action, pattern=f"^{config.CB_WB_REG_DIET}$"),
                CallbackQueryHandler(cb_wb_view_routine_action, pattern=f"^{config.CB_WB_VIEW_ROUTINE}$"),
                CallbackQueryHandler(cb_wb_view_diet_action, pattern=f"^{config.CB_WB_VIEW_DIET}$"),
            ],
            STATE_WB_ADD_GET_ITEMS_INPUT: [ # Estado para añadir cualquier tipo de item de bienestar
                MessageHandler(Filters.text & ~Filters.command, get_wb_item_input),
                CommandHandler("donewellbeing", done_adding_wb_items_command),
            ],
            STATE_WB_VIEW_AND_MARK_MODE: [ # Estado para ver ítems y poder marcarlos o añadir extras
                CallbackQueryHandler(mark_wb_sub_item_cb, pattern=f"^{config.CB_TASK_DONE_PREFIX}wb_"),
                CallbackQueryHandler(mark_wb_sub_item_cb, pattern=f"^{config.CB_TASK_NOT_DONE_PREFIX}wb_"),
                CallbackQueryHandler(cb_wb_reg_diet_extra_action, pattern=f"^{config.CB_WB_REG_EXTRAS}$"), # Transiciona a añadir extras
                CallbackQueryHandler(wellbeing_menu, pattern=f"^{config.CB_WB_MAIN_MENU}$") # Botón "Volver a Bienestar"
            ]
        },
        fallbacks=[
            CommandHandler("cancelwellbeing", cancel_wellbeing_subflow),
            CommandHandler("cancel", lambda u,c: common_handlers.cancel_conversation_and_show_main_menu(u,c, UD_WB_CLEANUP_KEYS)),
            CallbackQueryHandler(lambda u,c: common_handlers.cancel_conversation_and_show_main_menu(u,c, UD_WB_CLEANUP_KEYS), pattern=f"^{config.CB_MAIN_MENU}$")
        ],
        allow_reentry=True
    )
    dp.add_handler(wb_conv_handler)