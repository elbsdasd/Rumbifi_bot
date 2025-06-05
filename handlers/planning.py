    # handlers/planning.py

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

# Estados de la conversación para TODA la sección de Planificación
(
    STATE_PLAN_MENU_ACTION,             # 0: Menú principal de planificación, esperando selección
    STATE_PLAN_ADD_GET_DESCRIPTION,     # 1: Esperando descripción para añadir (objetivo, imp, sec)
    STATE_PLAN_ADD_GET_OBJECTIVE_REMINDER, # 2: Esperando recordatorio para el objetivo
    STATE_PLAN_VIEW_AND_MARK_MODE       # 3: Viendo la lista de tareas, esperando acción de marcar o volver
) = range(30, 34) # Usar un rango que no colisione con otros handlers

# Claves para context.user_data
UD_PLAN_CURRENT_ITEM_TYPE = 'plan_current_item_type'
UD_PLAN_TEMP_DESCRIPTION_LIST = 'plan_temp_description_list'
UD_PLAN_CLEANUP_KEYS = [UD_PLAN_CURRENT_ITEM_TYPE, UD_PLAN_TEMP_DESCRIPTION_LIST]


# --- FUNCIÓN DE MENÚ DE PLANIFICACIÓN (ENTRY POINT PRINCIPAL DE LA SECCIÓN) ---
def planning_menu(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    user_id = query.from_user.id if query else update.effective_user.id

    # Verificar acceso (aunque el handler de main.py ya debería haberlo hecho para CB_PLAN_MAIN_MENU)
    # Es bueno tenerlo por si se entra a este estado de otra forma.
    has_access, access_message = db_utils.check_user_access(user_id)
    if not has_access:
        if query: query.answer(); query.edit_message_text(text=access_message)
        else: context.bot.send_message(chat_id=user_id, text=access_message)
        return ConversationHandler.END

    keyboard = [
        [InlineKeyboardButton("🎯 Objetivo Principal", callback_data=config.CB_PLAN_SET_OBJECTIVE)],
        [InlineKeyboardButton("⭐ Tareas Importantes (3)", callback_data=config.CB_PLAN_SET_IMPORTANT)],
        [InlineKeyboardButton("📝 Tareas Secundarias", callback_data=config.CB_PLAN_SET_SECONDARY)],
        [InlineKeyboardButton("📋 Ver Plan del Día y Marcar", callback_data=config.CB_PLAN_VIEW_DAY)],
        [common_handlers.get_back_to_main_menu_button()] # Botón para volver al menú principal del BOT
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    message_text = "🗓️ *Planificar Mi Día*\n\nMétodo 1-3-5. Elige una opción:"
    
    if query:
        query.answer()
        query.edit_message_text(text=message_text, reply_markup=reply_markup, parse_mode='Markdown')
    else: 
        context.bot.send_message(chat_id=user_id, text=message_text, reply_markup=reply_markup, parse_mode='Markdown')
        
    return STATE_PLAN_MENU_ACTION # Estado donde se espera una acción del menú de planificación


# --- INICIO FLUJO: AÑADIR ITEMS ---
def start_add_item_flow(update: Update, context: CallbackContext, item_type: str) -> int:
    query = update.callback_query
    if query: query.answer()
    
    context.user_data[UD_PLAN_CURRENT_ITEM_TYPE] = item_type
    context.user_data[UD_PLAN_TEMP_DESCRIPTION_LIST] = [] 

    prompt_map = {
        'objective': "🎯 Objetivo Principal:\nEscribe tu objetivo. (/cancelplanning para volver al menú de planificación)",
        'important': "⭐ Tareas Importantes (máx. 3):\nEnvía la 1ra tarea. /doneplanning al terminar, /cancelplanning para volver.",
        'secondary': "📝 Tareas Secundarias:\nEnvía la 1ra tarea. /doneplanning al terminar, /cancelplanning para volver."
    }
    prompt_text = prompt_map.get(item_type)

    if query and query.message: query.edit_message_text(text=prompt_text)
    else: context.bot.send_message(chat_id=update.effective_chat.id, text=prompt_text)
    return STATE_PLAN_ADD_GET_DESCRIPTION

# Callbacks para los botones de añadir (desde STATE_PLAN_MENU_ACTION)
def cb_plan_set_objective_action(update: Update, context: CallbackContext) -> int:
    return start_add_item_flow(update, context, 'objective')
def cb_plan_set_important_action(update: Update, context: CallbackContext) -> int:
    return start_add_item_flow(update, context, 'important')
def cb_plan_set_secondary_action(update: Update, context: CallbackContext) -> int:
    return start_add_item_flow(update, context, 'secondary')

def get_item_description_input(update: Update, context: CallbackContext) -> int:
    user_text = update.message.text
    item_type = context.user_data.get(UD_PLAN_CURRENT_ITEM_TYPE)
    
    if item_type == 'objective':
        context.user_data[UD_PLAN_TEMP_DESCRIPTION_LIST] = [user_text]
        update.message.reply_text(config.MSG_TIME_FORMAT_PROMPT)
        return STATE_PLAN_ADD_GET_OBJECTIVE_REMINDER
    
    elif item_type in ['important', 'secondary']:
        collected_list = context.user_data.get(UD_PLAN_TEMP_DESCRIPTION_LIST, [])
        if item_type == 'important' and len(collected_list) >= 3:
            update.message.reply_text("Máximo 3 tareas importantes. /doneplanning para guardar.")
            return STATE_PLAN_ADD_GET_DESCRIPTION
        collected_list.append(user_text)
        context.user_data[UD_PLAN_TEMP_DESCRIPTION_LIST] = collected_list
        count_msg = f"({len(collected_list)}/3)" if item_type == 'important' else ""
        update.message.reply_text(f"✅ Tarea '{user_text[:30]}...' añadida {count_msg}. Envía otra, o /doneplanning.")
        return STATE_PLAN_ADD_GET_DESCRIPTION
        
    logger.error(f"Tipo ítem desconocido: {item_type}")
    return cancel_planning_subflow(update, context) # Volver al menú de planificación

def get_objective_reminder_input(update: Update, context: CallbackContext) -> int:
    user_text = update.message.text.lower()
    item_type = context.user_data.get(UD_PLAN_CURRENT_ITEM_TYPE)
    user_id = update.effective_user.id

    if item_type != 'objective': return cancel_planning_subflow(update, context)

    reminder_time_to_save = None
    if user_text == 'no': update.message.reply_text("OK, sin recordatorio.")
    else:
        try:
            datetime.strptime(user_text, "%H:%M"); reminder_time_to_save = user_text
            update.message.reply_text(f"Recordatorio para objetivo: {user_text}.")
        except ValueError:
            update.message.reply_text(config.MSG_TIME_FORMAT_ERROR + "\nIntenta de nuevo o 'no'.")
            return STATE_PLAN_ADD_GET_OBJECTIVE_REMINDER 

    desc_list = context.user_data.get(UD_PLAN_TEMP_DESCRIPTION_LIST)
    if desc_list and desc_list[0]:
        db_utils.save_planning_item(user_id, 'objective', desc_list[0], reminder_time_to_save)
        update.message.reply_text("🎯 ¡Objetivo principal guardado!")
    else: update.message.reply_text("⚠️ Error guardando objetivo.")
    return cancel_planning_subflow(update, context) # Vuelve al menú de planificación

def done_adding_planning_items_command(update: Update, context: CallbackContext) -> int: # /doneplanning
    user_id = update.effective_user.id
    item_type = context.user_data.get(UD_PLAN_CURRENT_ITEM_TYPE)
    desc_list = context.user_data.get(UD_PLAN_TEMP_DESCRIPTION_LIST, [])

    if not desc_list:
        update.message.reply_text("No añadiste tareas. /cancelplanning para volver.")
        return STATE_PLAN_ADD_GET_DESCRIPTION 
    else:
        for desc in desc_list:
            db_utils.save_planning_item(user_id, item_type, desc, None)
        update.message.reply_text(f"✅ ¡{len(desc_list)} tarea(s) '{item_type}' guardadas!")
    return cancel_planning_subflow(update, context) # Vuelve al menú de planificación

def cancel_planning_subflow(update: Update, context: CallbackContext) -> int: # /cancelplanning
    """Cancela el subflujo de añadir y vuelve al menú de planificación."""
    for key in UD_PLAN_CLEANUP_KEYS:
        if key in context.user_data: del context.user_data[key]
    if update.message: update.message.reply_text("Subproceso cancelado.")
    # Mostrar menú de planificación
    return planning_menu(update, context)


# --- FLUJO: VER Y MARCAR TAREAS ---
def view_daily_plan_action_cb(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    user_id = query.from_user.id
    if query: query.answer()

    today_date_obj = datetime.now(db_utils.LIMA_TZ).date()
    items_dr = db_utils.get_daily_planning_items(user_id, today_date_obj)
    message_text = "📋 *Tu Plan para Hoy:* \n\n"
    keyboard_rows = []

    if not items_dr: message_text += "No tienes nada planeado para hoy."
    else:
        cats = {"objective": "🎯 Objetivo:", "important": "⭐ Importantes:", "secondary": "📝 Secundarias:"}
        cat_items = {k: [] for k in cats}
        for item_dictrow in items_dr: item = dict(item_dictrow); cat_items[item.get("type", "")].append(item)

        for cat_key, cat_title in cats.items():
            if cat_items[cat_key]:
                message_text += f"*{cat_title}*\n"
                for item in cat_items[cat_key]:
                    se = "⏳"; rts = ""
                    if item.get("completed") is True: se = "✅"
                    elif item.get("completed") is False: se = "❌"
                    if item.get("reminder_time"): rts = f" ({item['reminder_time'].strftime('%H:%M')})"
                    message_text += f"{se} {item['text']}{rts}\n"
                    if item.get("completed") is None:
                        iid = item['key']; cb_d = f"{config.CB_TASK_DONE_PREFIX}planning_{iid}"; cb_nd = f"{config.CB_TASK_NOT_DONE_PREFIX}planning_{iid}"
                        ts = item['text'][:15] + ('…' if len(item['text']) > 15 else '')
                        keyboard_rows.append([InlineKeyboardButton(f"✅ '{ts}'", callback_data=cb_d), InlineKeyboardButton(f"❌ '{ts}'", callback_data=cb_nd)])
                message_text += "\n"
            
    keyboard_rows.append([common_handlers.get_back_button(config.CB_PLAN_MAIN_MENU, "⬅️ A Planificación")])
    reply_markup = InlineKeyboardMarkup(keyboard_rows)
    
    if query and query.message:
        try: query.edit_message_text(text=message_text, reply_markup=reply_markup, parse_mode='Markdown')
        except Exception as e: context.bot.send_message(chat_id=user_id,text=message_text, reply_markup=reply_markup, parse_mode='Markdown')
    else: context.bot.send_message(chat_id=user_id, text=message_text, reply_markup=reply_markup, parse_mode='Markdown')
    return STATE_PLAN_VIEW_AND_MARK_MODE

def mark_planning_task_cb(update: Update, context: CallbackContext) -> int:
    query = update.callback_query; query.answer()
    try:
        parts = query.data.split('_'); item_id = int(parts[3])
        completed = (parts[0]+"_"+parts[1] == config.CB_TASK_DONE_PREFIX[:-1])
        db_utils.update_planning_item_status(item_id, completed)
        return view_daily_plan_action_cb(update, context) # Refrescar
    except Exception as e:
        logger.error(f"Error marcando tarea planning: {e}, data: {query.data}")
        if query.message: query.message.reply_text("⚠️ Error al marcar.")
    return STATE_PLAN_VIEW_AND_MARK_MODE


# --- REGISTRO DE HANDLERS ---
def register_handlers(dp) -> None:
    planning_conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(planning_menu, pattern=f"^{config.CB_PLAN_MAIN_MENU}$")],
        states={
            STATE_PLAN_MENU_ACTION: [ # Desde el menú de planificación, podemos...
                CallbackQueryHandler(cb_plan_set_objective_action, pattern=f"^{config.CB_PLAN_SET_OBJECTIVE}$"),
                CallbackQueryHandler(cb_plan_set_important_action, pattern=f"^{config.CB_PLAN_SET_IMPORTANT}$"),
                CallbackQueryHandler(cb_plan_set_secondary_action, pattern=f"^{config.CB_PLAN_SET_SECONDARY}$"),
                CallbackQueryHandler(view_daily_plan_action_cb, pattern=f"^{config.CB_PLAN_VIEW_DAY}$"),
                # Botón "Volver al Menú Principal del Bot" (CB_MAIN_MENU) es manejado por main.py
            ],
            STATE_PLAN_ADD_GET_DESCRIPTION: [
                MessageHandler(Filters.text & ~Filters.command, get_item_description_input),
                CommandHandler("doneplanning", done_adding_planning_items_command),
            ],
            STATE_PLAN_ADD_GET_OBJECTIVE_REMINDER: [
                MessageHandler(Filters.text & ~Filters.command, get_objective_reminder_input)
            ],
            STATE_PLAN_VIEW_AND_MARK_MODE: [
                CallbackQueryHandler(mark_planning_task_cb, pattern=f"^{config.CB_TASK_DONE_PREFIX}planning_"),
                CallbackQueryHandler(mark_planning_task_cb, pattern=f"^{config.CB_TASK_NOT_DONE_PREFIX}planning_"),
                # Botón "Volver a Planificación" (CB_PLAN_MAIN_MENU) te lleva de nuevo a planning_menu
                CallbackQueryHandler(planning_menu, pattern=f"^{config.CB_PLAN_MAIN_MENU}$")
            ]
        },
        fallbacks=[
            CommandHandler("cancelplanning", cancel_planning_subflow), # Cancela subflujos al menú de planificación
            # Un /cancel global que te saque de toda la sección de planificación
            CommandHandler("cancel", lambda u,c: common_handlers.cancel_conversation_to_main_menu(u,c, UD_PLAN_CLEANUP_KEYS)),
            # Botón para volver al menú principal del BOT (CB_MAIN_MENU) desde cualquier estado profundo.
            # Este es manejado por el handler global en main.py, que terminará esta conversación.
        ],
        allow_reentry=True # Permite reingresar a los estados del menú
    )
    dp.add_handler(planning_conv_handler)