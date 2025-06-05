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

# Estados de la conversación para Bienestar
(
    STATE_WB_MENU_ACTION,      # Estado del menú principal de bienestar, esperando acción
    STATE_WB_GET_ITEMS_INPUT,  # Esperando descripciones de ejercicios o comidas
    STATE_WB_VIEW_ITEMS_MODE   # Viendo la lista y esperando callbacks de marcado o registrar extras
) = range(40, 43) # Nuevo rango para estados

# Claves para context.user_data
UD_WB_CURRENT_ITEM_TYPE = 'wb_current_item_type' # 'exercise', 'diet_main', 'diet_extra'
UD_WB_TEMP_COLLECTED_ITEMS = 'wb_temp_collected_items'
UD_WB_CLEANUP_KEYS_ADD_FLOW = [UD_WB_CURRENT_ITEM_TYPE, UD_WB_TEMP_COLLECTED_ITEMS]


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
        [InlineKeyboardButton("👀 Ver Mi Rutina y Marcar", callback_data=config.CB_WB_VIEW_ROUTINE)],
        [InlineKeyboardButton("📖 Ver Mi Dieta y Marcar", callback_data=config.CB_WB_VIEW_DIET)],
        [common_handlers.get_back_to_main_menu_button()]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    message_text = "💪 *Bienestar Físico y Mental*\n\nElige una opción:"
    
    if query:
        query.answer()
        query.edit_message_text(text=message_text, reply_markup=reply_markup, parse_mode='Markdown')
    else: 
        context.bot.send_message(chat_id=user_id, text=message_text, reply_markup=reply_markup, parse_mode='Markdown')
    return STATE_WB_MENU_ACTION


# --- FLUJO: AÑADIR ITEMS DE BIENESTAR ---
def start_add_wb_item_flow(update: Update, context: CallbackContext, item_type: str) -> int:
    query = update.callback_query
    if query: query.answer()
    
    context.user_data[UD_WB_CURRENT_ITEM_TYPE] = item_type
    context.user_data[UD_WB_TEMP_COLLECTED_ITEMS] = []

    prompt_map = {
        'exercise': "🤸 Ejercicios del Día:\n\nEnvía cada ejercicio (ej. 'Planchas 3x15').\nEscribe /donewellbeing al terminar, o /cancelwellbeing.",
        'diet_main': "🍎 Comidas Principales:\n\nRegistra desayuno, almuerzo, cena.\nEnvía cada comida. Escribe /donewellbeing al terminar, o /cancelwellbeing.",
        'diet_extra': "🍪 Antojos/Extras:\n\nRegistra cualquier comida extra.\nEnvía cada una. Escribe /donewellbeing al terminar, o /cancelwellbeing."
    }
    prompt_text = prompt_map.get(item_type)

    if query and query.message: query.edit_message_text(text=prompt_text)
    else: context.bot.send_message(chat_id=update.effective_chat.id, text=prompt_text)
    return STATE_WB_GET_ITEMS_INPUT

# Callbacks para los botones de añadir
def cb_wb_reg_exercise(update: Update, context: CallbackContext) -> int:
    return start_add_wb_item_flow(update, context, 'exercise')
def cb_wb_reg_diet_main(update: Update, context: CallbackContext) -> int:
    return start_add_wb_item_flow(update, context, 'diet_main')
def cb_wb_reg_diet_extra(update: Update, context: CallbackContext) -> int: # Llamado desde "Ver Dieta"
    # Este es un entry point a la conversación de añadir, pero desde la vista de dieta.
    # Debe enviar un nuevo mensaje, no editar.
    context.user_data[UD_WB_CURRENT_ITEM_TYPE] = 'diet_extra'
    context.user_data[UD_WB_TEMP_COLLECTED_ITEMS] = []
    prompt_text = "🍪 Antojos/Extras:\n\nRegistra cualquier comida extra.\nEnvía cada una. Escribe /donewellbeing al terminar, o /cancelwellbeing."
    if update.callback_query: update.callback_query.answer() # Contestar al callback
    context.bot.send_message(chat_id=update.effective_chat.id, text=prompt_text)
    return STATE_WB_GET_ITEMS_INPUT


def get_wb_item_input(update: Update, context: CallbackContext) -> int:
    user_text = update.message.text
    collected_items = context.user_data.get(UD_WB_TEMP_COLLECTED_ITEMS, [])
    collected_items.append(user_text)
    context.user_data[UD_WB_TEMP_COLLECTED_ITEMS] = collected_items
    
    item_type = context.user_data.get(UD_WB_CURRENT_ITEM_TYPE)
    type_map = {'exercise': 'ejercicio', 'diet_main': 'comida principal', 'diet_extra': 'comida extra'}
    friendly_type = type_map.get(item_type, "ítem")
    update.message.reply_text(f"✅ '{user_text[:30]}...' añadido como {friendly_type}. Envía otro, o /donewellbeing.")
    return STATE_WB_GET_ITEMS_INPUT

def done_adding_wb_items(update: Update, context: CallbackContext) -> int:
    user_id = update.effective_user.id
    item_type = context.user_data.get(UD_WB_CURRENT_ITEM_TYPE)
    collected_items = context.user_data.get(UD_WB_TEMP_COLLECTED_ITEMS, [])

    if not collected_items:
        update.message.reply_text("No has añadido ítems. Escribe /cancelwellbeing para volver.")
        return STATE_WB_GET_ITEMS_INPUT
    else:
        today_date_obj = datetime.now(db_utils.LIMA_TZ).date()
        db_utils.save_wellbeing_items_list( # Nueva función de db_utils
            user_id=user_id, item_type=item_type, 
            data_list=collected_items, date_obj=today_date_obj
        )
        type_map_plural = {'exercise': 'ejercicios', 'diet_main': 'comidas principales', 'diet_extra': 'comidas extra'}
        update.message.reply_text(f"✅ ¡Tus {type_map_plural.get(item_type, 'ítems')} han sido guardados!")

    # Limpiar user_data y volver al menú de bienestar
    for key_to_clear in UD_WB_CLEANUP_KEYS_ADD_FLOW:
        if key_to_clear in context.user_data: del context.user_data[key_to_clear]
    
    # Enviar menú de bienestar como nuevo mensaje
    wellbeing_menu(update, context) # Llamar a la función del menú
    return ConversationHandler.END


# --- FLUJO: VER Y MARCAR ITEMS DE BIENESTAR ---
def view_wb_items_action_cb(update: Update, context: CallbackContext, view_type: str) -> int:
    query = update.callback_query
    user_id = query.from_user.id
    if query: query.answer()

    today_date_obj = datetime.now(db_utils.LIMA_TZ).date()
    # doc_and_items: {"key": doc_id, "items": [sub_items_list], ...}
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
            status_emoji = "⏳"
            if item.get("marked_at"):
                status_emoji = "✅" if item.get("completed") else "❌"
            message_text += f"{status_emoji} {item['text']}\n"
            
            if item.get("completed") is False or item.get("completed") is None:
                sub_item_id = item['key'] # 'key' es el alias de sub_item_id
                cb_done = f"{config.CB_TASK_DONE_PREFIX}wb_{view_type}_{sub_item_id}"
                cb_not_done = f"{config.CB_TASK_NOT_DONE_PREFIX}wb_{view_type}_{sub_item_id}"
                item_short = item['text'][:15] + ('…' if len(item['text']) > 15 else '')
                buttons_row = [
                    InlineKeyboardButton(f"✅ Hecho '{item_short}'", callback_data=cb_done),
                    InlineKeyboardButton(f"❌ No '{item_short}'", callback_data=cb_not_done)
                ]
                keyboard_rows.append(buttons_row)
        message_text += "\n"

    if view_type == 'diet_main':
        keyboard_rows.append([InlineKeyboardButton("🍪 Registrar Antojos/Extras", callback_data=config.CB_WB_REG_EXTRAS)])
    
    keyboard_rows.append([common_handlers.get_back_button(config.CB_WB_MAIN_MENU, "⬅️ Volver a Bienestar")])
    reply_markup = InlineKeyboardMarkup(keyboard_rows)
    
    if query and query.message:
        try:
            query.edit_message_text(text=message_text, reply_markup=reply_markup, parse_mode='Markdown')
        except Exception as e:
            logger.warning(f"Error editando vista de bienestar (wellbeing), enviando nuevo: {e}")
            context.bot.send_message(chat_id=user_id, text=message_text, reply_markup=reply_markup, parse_mode='Markdown')
    else:
         context.bot.send_message(chat_id=user_id, text=message_text, reply_markup=reply_markup, parse_mode='Markdown')
    return STATE_WB_VIEW_ITEMS_MODE

# Callbacks para los botones de ver
def cb_wb_view_routine(update: Update, context: CallbackContext) -> int:
    return view_wb_items_action_cb(update, context, 'exercise')
def cb_wb_view_diet(update: Update, context: CallbackContext) -> int:
    return view_wb_items_action_cb(update, context, 'diet_main')

def mark_wb_sub_item_cb(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    query.answer()
    callback_data = query.data
    try:
        parts = callback_data.split('_')
        action_prefix_part = parts[0] + "_" + parts[1] 
        view_type_from_cb = parts[2]
        sub_item_id = int(parts[3])
        completed_status = (action_prefix_part == config.CB_TASK_DONE_PREFIX[:-1] + "wb")
        db_utils.update_wellbeing_sub_item_status(sub_item_id, completed_status)
        return view_wb_items_action_cb(update, context, view_type_from_cb) # Refrescar
    except Exception as e:
        logger.error(f"Error marcando sub-ítem de bienestar: {e}, data: {callback_data}")
        query.message.reply_text("⚠️ Error al procesar la acción.")
    return STATE_WB_VIEW_ITEMS_MODE

def cancel_wellbeing_flow_command(update: Update, context: CallbackContext) -> int:
    return common_handlers.cancel_conversation_to_main_menu(update, context, UD_WB_CLEANUP_KEYS_ADD_FLOW)

# --- REGISTRO DE HANDLERS ---
def register_handlers(dp) -> None:
    # ConvHandler para AÑADIR ítems (ejercicios, comidas principales, comidas extra)
    add_wb_item_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(cb_wb_reg_exercise, pattern=f"^{config.CB_WB_REG_EXERCISE}$"),
            CallbackQueryHandler(cb_wb_reg_diet_main, pattern=f"^{config.CB_WB_REG_DIET}$"),
            # CB_WB_REG_EXTRAS es un entry point especial desde la vista de dieta
            CallbackQueryHandler(cb_wb_reg_diet_extra, pattern=f"^{config.CB_WB_REG_EXTRAS}$"),
        ],
        states={
            STATE_WB_GET_ITEMS_INPUT: [MessageHandler(Filters.text & ~Filters.command, get_wb_item_input)],
        },
        fallbacks=[
            CommandHandler("donewellbeing", done_adding_wb_items),
            CommandHandler("cancelwellbeing", cancel_wellbeing_flow_command),
        ],
        map_to_parent={ConversationHandler.END: STATE_WB_MENU_ACTION} # Volver al menú de bienestar
    )

    # ConvHandler para la sección de VER y MARCAR ítems, y desde donde se puede ir a AÑADIR extras
    view_mark_wb_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(cb_wb_view_routine, pattern=f"^{config.CB_WB_VIEW_ROUTINE}$"),
            CallbackQueryHandler(cb_wb_view_diet, pattern=f"^{config.CB_WB_VIEW_DIET}$"),
        ],
        states={
            STATE_WB_VIEW_ITEMS_MODE: [
                CallbackQueryHandler(mark_wb_sub_item_cb, pattern=f"^{config.CB_TASK_DONE_PREFIX}wb_"),
                CallbackQueryHandler(mark_wb_sub_item_cb, pattern=f"^{config.CB_TASK_NOT_DONE_PREFIX}wb_"),
                # El callback para CB_WB_REG_EXTRAS es un entry_point de add_wb_item_conv
                # Si add_wb_item_conv está anidado, esto funcionaría.
                # Si no, necesitamos una forma de que este handler termine y el otro comience.
                # Una forma es que cb_wb_reg_diet_extra sea un entry point al OTRO conv handler.
                # Lo hemos hecho así: CB_WB_REG_EXTRAS es un entry point de add_wb_item_conv.
                CallbackQueryHandler(wellbeing_menu, pattern=f"^{config.CB_WB_MAIN_MENU}$") # Volver al menú de bienestar
            ]
        },
        fallbacks=[CommandHandler("cancelwellbeing", cancel_wellbeing_flow_command)],
        map_to_parent={ConversationHandler.END: STATE_WB_MENU_ACTION} # Volver al menú de bienestar
    )
    
    # El ConversationHandler principal para toda la sección de bienestar
    # El menú de bienestar es el estado de "reposo"
    wb_section_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(wellbeing_menu, pattern=f"^{config.CB_WB_MAIN_MENU}$")],
        states={
            STATE_WB_MENU_ACTION: [ # Desde el menú de bienestar, podemos ir a...
                add_wb_item_conv,    # ...el flujo de añadir
                view_mark_wb_conv,   # ...el flujo de ver/marcar
            ],
            # Los estados internos de add_wb_item_conv y view_mark_wb_conv se manejan dentro de ellos.
        },
        fallbacks=[
            CommandHandler("cancel", lambda u,c: common_handlers.cancel_conversation_to_main_menu(u,c,UD_WB_CLEANUP_KEYS_ADD_FLOW)),
            CallbackQueryHandler(common_handlers.cancel_conversation_to_main_menu, pattern=f"^{config.CB_MAIN_MENU}$") # Si el botón de volver al menú principal del bot está aquí
            ],
        allow_reentry=True # Permitir reingresar al menú de bienestar
    )
    dp.add_handler(wb_section_handler)