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
) = range(30, 34)

# Claves para context.user_data
UD_PLAN_CURRENT_ITEM_TYPE = 'plan_current_item_type'
UD_PLAN_TEMP_DESCRIPTION_LIST = 'plan_temp_description_list'
UD_PLAN_CLEANUP_KEYS = [UD_PLAN_CURRENT_ITEM_TYPE, UD_PLAN_TEMP_DESCRIPTION_LIST]


# --- FUNCIÓN DE MENÚ DE PLANIFICACIÓN (Entry Point Principal de la Sección) ---
def planning_menu(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    user_id = query.from_user.id if query else update.effective_user.id

    has_access, access_message = db_utils.check_user_access(user_id)
    if not has_access:
        if query: query.answer(); query.edit_message_text(text=access_message)
        else: context.bot.send_message(chat_id=user_id, text=access_message)
        return ConversationHandler.END

    keyboard = [
        [InlineKeyboardButton("🎯 Objetivo Principal del Día", callback_data=config.CB_PLAN_SET_OBJECTIVE)],
        [InlineKeyboardButton("⭐ Tareas Importantes (Máx. 3)", callback_data=config.CB_PLAN_SET_IMPORTANT)],
        [InlineKeyboardButton("📝 Tareas Secundarias (Recomendado 5+)", callback_data=config.CB_PLAN_SET_SECONDARY)],
        [InlineKeyboardButton("📋 Ver Plan del Día y Marcar Avance", callback_data=config.CB_PLAN_VIEW_DAY)],
        [common_handlers.get_back_to_main_menu_button()] # Botón para volver al menú principal del BOT
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    message_text = (
        "🗓️ *Planificar Mi Día - Método 1-3-5*\n\n"
        "Este método te ayuda a priorizar y enfocarte. Cada día define:\n"
        "1️⃣ Un **Objetivo Principal:** Tu tarea más crucial que debe completarse.\n"
        "3️⃣ Tres **Tareas Importantes:** Tareas significativas que te acercan a tus metas.\n"
        "5️⃣ Cinco (o más) **Tareas Secundarias:** Tareas más pequeñas o menos urgentes.\n\n"
        "¡Así evitamos la sobrecarga y fomentamos disciplina y constancia! Elige una opción para empezar:"
    )
    
    if query:
        query.answer()
        query.edit_message_text(text=message_text, reply_markup=reply_markup, parse_mode='Markdown')
    else: 
        context.bot.send_message(chat_id=user_id, text=message_text, reply_markup=reply_markup, parse_mode='Markdown')
        
    return STATE_PLAN_MENU_ACTION


# --- INICIO FLUJO: AÑADIR ITEMS ---
def start_add_item_flow(update: Update, context: CallbackContext, item_type: str) -> int:
    query = update.callback_query
    if query: query.answer()
    
    context.user_data[UD_PLAN_CURRENT_ITEM_TYPE] = item_type
    context.user_data[UD_PLAN_TEMP_DESCRIPTION_LIST] = [] 

    prompt_map = {
        'objective': "🎯 *Objetivo Principal del Día:*\n\nEscribe tu objetivo más importante para hoy (ej. 'Terminar informe de ventas').\n\nPuedes escribir /cancelplanning para volver al menú de planificación.",
        'important': "⭐ *Tareas Importantes (Máx. 3):*\n\nEnvía la descripción de tu primera tarea importante (ej. 'Preparar presentación para cliente X'). Puedes añadir hasta 3.\nEscribe /doneplanning cuando hayas añadido todas tus tareas importantes, o /cancelplanning para volver.",
        'secondary': "📝 *Tareas Secundarias:*\n\nEnvía la descripción de tu primera tarea secundaria (ej. 'Comprar leche y pan'). Puedes añadir varias.\nEscribe /doneplanning cuando hayas añadido todas tus tareas secundarias, o /cancelplanning para volver."
    }
    prompt_text = prompt_map.get(item_type)

    target_chat_id = query.message.chat_id if query and query.message else update.effective_chat.id
    if query and query.message: query.edit_message_text(text=prompt_text, parse_mode='Markdown')
    else: context.bot.send_message(chat_id=target_chat_id, text=prompt_text, parse_mode='Markdown')
    return STATE_PLAN_ADD_GET_DESCRIPTION

# Callbacks para los botones de añadir
def cb_plan_set_objective_action(update: Update, context: CallbackContext) -> int:
    return start_add_item_flow(update, context, 'objective')
def cb_plan_set_important_action(update: Update, context: CallbackContext) -> int:
    return start_add_item_flow(update, context, 'important')
def cb_plan_set_secondary_action(update: Update, context: CallbackContext) -> int:
    return start_add_item_flow(update, context, 'secondary')

def get_item_description_input(update: Update, context: CallbackContext) -> int:
    user_text = update.message.text.strip()
    if not user_text: # Ignorar mensajes vacíos
        update.message.reply_text("La descripción no puede estar vacía. Intenta de nuevo o usa /cancelplanning.")
        return STATE_PLAN_ADD_GET_DESCRIPTION

    item_type = context.user_data.get(UD_PLAN_CURRENT_ITEM_TYPE)
    
    if item_type == 'objective':
        context.user_data[UD_PLAN_TEMP_DESCRIPTION_LIST] = [user_text]
        update.message.reply_text(config.MSG_TIME_FORMAT_PROMPT, parse_mode='Markdown')
        return STATE_PLAN_ADD_GET_OBJECTIVE_REMINDER
    
    elif item_type in ['important', 'secondary']:
        collected_list = context.user_data.get(UD_PLAN_TEMP_DESCRIPTION_LIST, [])
        if item_type == 'important' and len(collected_list) >= 3:
            update.message.reply_text("Ya has añadido el máximo de 3 tareas importantes. Escribe /doneplanning para guardarlas o /cancelplanning.")
            return STATE_PLAN_ADD_GET_DESCRIPTION 
        collected_list.append(user_text)
        context.user_data[UD_PLAN_TEMP_DESCRIPTION_LIST] = collected_list
        count_msg = f"({len(collected_list)}/3)" if item_type == 'important' else f"({len(collected_list)} añadidas)"
        update.message.reply_text(f"✅ Tarea '{user_text[:30]}...' añadida {count_msg}. Envía otra, o /doneplanning para guardar todo. /cancelplanning para volver.")
        return STATE_PLAN_ADD_GET_DESCRIPTION
        
    logger.error(f"Tipo de ítem desconocido en get_item_description_input: {item_type}")
    return cancel_planning_subflow(update, context)

def get_objective_reminder_input(update: Update, context: CallbackContext) -> int:
    user_text = update.message.text.lower().strip()
    item_type = context.user_data.get(UD_PLAN_CURRENT_ITEM_TYPE)
    user_id = update.effective_user.id

    if item_type != 'objective': return cancel_planning_subflow(update, context)

    reminder_time_to_save = None
    if user_text == 'no': update.message.reply_text("Entendido, sin recordatorio para el objetivo.")
    else:
        try:
            datetime.strptime(user_text, "%H:%M"); reminder_time_to_save = user_text
            update.message.reply_text(f"Recordatorio para el objetivo programado a las {user_text}.")
        except ValueError:
            update.message.reply_text(config.MSG_TIME_FORMAT_ERROR + "\nIntenta de nuevo, escribe 'no', o /cancelplanning.")
            return STATE_PLAN_ADD_GET_OBJECTIVE_REMINDER 

    description_list = context.user_data.get(UD_PLAN_TEMP_DESCRIPTION_LIST)
    if description_list and description_list[0]:
        db_utils.save_planning_item(user_id, 'objective', description_list[0], reminder_time_to_save)
        update.message.reply_text("🎯 ¡Objetivo principal guardado!")
    else: update.message.reply_text("⚠️ Error guardando objetivo. No se encontró descripción.")
    return cancel_planning_subflow(update, context)

def done_adding_planning_items_command(update: Update, context: CallbackContext) -> int: # /doneplanning
    user_id = update.effective_user.id
    item_type = context.user_data.get(UD_PLAN_CURRENT_ITEM_TYPE)
    descriptions_list = context.user_data.get(UD_PLAN_TEMP_DESCRIPTION_LIST, [])

    if not descriptions_list:
        update.message.reply_text("No has añadido ninguna tarea. Envía una tarea o escribe /cancelplanning para volver.")
        return STATE_PLAN_ADD_GET_DESCRIPTION 
    else:
        for desc_text in descriptions_list:
            db_utils.save_planning_item(user_id, item_type, desc_text, None) # Reminder None para tareas imp/sec por ahora
        update.message.reply_text(f"✅ ¡{len(descriptions_list)} tarea(s) '{item_type}' han sido guardadas!")
    return cancel_planning_subflow(update, context)

def cancel_planning_subflow(update: Update, context: CallbackContext) -> int: # /cancelplanning
    for key in UD_PLAN_CLEANUP_KEYS:
        if key in context.user_data: del context.user_data[key]
    if update.message: update.message.reply_text("Proceso de añadir tarea cancelado.")
    elif update.callback_query: update.callback_query.answer("Cancelado.") # Si se llamara desde un botón
    return planning_menu(update, context) # Vuelve al menú de planificación


# --- FLUJO: VER Y MARCAR TAREAS ---
def view_daily_plan_action_cb(update: Update, context: CallbackContext) -> int:
    # (La lógica interna de esta función se mantiene igual que la última versión estable para Render)
    # ... (copia el contenido de view_daily_plan_action_cb de la respuesta anterior) ...
    # Solo asegúrate de que los callback_data para los botones usen config.CB_TASK_DONE_PREFIX, etc.
    # y que el botón de volver use config.CB_PLAN_MAIN_MENU
    query = update.callback_query
    user_id = query.from_user.id
    if query: query.answer()

    today_lima_date_obj = datetime.now(db_utils.LIMA_TZ).date()
    items_dictrows = db_utils.get_daily_planning_items(user_id, today_lima_date_obj)
    message_text = "📋 *Tu Plan para Hoy:* \n\n"
    keyboard_markup_rows = []

    if not items_dictrows:
        message_text += "No tienes nada planeado para hoy.\nPuedes añadir tareas desde el menú de planificación."
    else:
        item_categories = {"objective": "🎯 Objetivo:", "important": "⭐ Importantes:", "secondary": "📝 Secundarias:"}
        categorized_items = {"objective": [], "important": [], "secondary": []}
        for item_dr in items_dictrows:
            item = dict(item_dr)
            # Asegurar que item_type exista y sea válido
            item_type = item.get("type")
            if item_type in categorized_items:
                categorized_items[item_type].append(item)
            else:
                logger.warning(f"Item con tipo desconocido o faltante encontrado: {item}")


        for category_key, category_title in item_categories.items():
            if categorized_items[category_key]:
                message_text += f"*{category_title}*\n"
                for item in categorized_items[category_key]:
                    status_emoji = "⏳" 
                    if item.get("completed") is True: status_emoji = "✅"
                    elif item.get("completed") is False: status_emoji = "❌"
                    
                    reminder_str = ""
                    if item.get("reminder_time"): 
                        reminder_str = f" ({item['reminder_time'].strftime('%H:%M')})"
                    message_text += f"{status_emoji} {item['text']}{reminder_str}\n"
                    
                    if item.get("completed") is None: 
                        item_id = item['key'] 
                        cb_done = f"{config.CB_TASK_DONE_PREFIX}planning_{item_id}"
                        cb_not_done = f"{config.CB_TASK_NOT_DONE_PREFIX}planning_{item_id}"
                        task_short = item['text'][:15] + ('…' if len(item['text']) > 15 else '')
                        buttons_row = [
                            InlineKeyboardButton(f"✅ '{task_short}'", callback_data=cb_done),
                            InlineKeyboardButton(f"❌ '{task_short}'", callback_data=cb_not_done)
                        ]
                        keyboard_markup_rows.append(buttons_row)
                message_text += "\n"
            
    # Botón para volver al menú de planificación (CB_PLAN_MAIN_MENU)
    keyboard_markup_rows.append([common_handlers.get_back_button(config.CB_PLAN_MAIN_MENU, "⬅️ A Planificación")])
    reply_markup = InlineKeyboardMarkup(keyboard_markup_rows)
    
    target_chat_id = query.message.chat_id if query and query.message else user_id
    if query and query.message:
        try: query.edit_message_text(text=message_text, reply_markup=reply_markup, parse_mode='Markdown')
        except Exception as e: 
            logger.warning(f"Error editando vista plan (planning), enviando nuevo: {e}")
            context.bot.send_message(chat_id=target_chat_id, text=message_text, reply_markup=reply_markup, parse_mode='Markdown')
    else: context.bot.send_message(chat_id=target_chat_id, text=message_text, reply_markup=reply_markup, parse_mode='Markdown')
    return STATE_PLAN_VIEW_AND_MARK_MODE

def mark_planning_task_cb(update: Update, context: CallbackContext) -> int:
    # (Lógica idéntica a la última versión estable para Render)
    # ... (copia el contenido de mark_planning_task_cb de la respuesta anterior) ...
    query = update.callback_query; query.answer()
    try:
        parts = query.data.split('_'); item_id = int(parts[3])
        completed_status = (parts[0]+"_"+parts[1] == config.CB_TASK_DONE_PREFIX[:-1]) # Compara con "task_done"
        db_utils.update_planning_item_status(item_id, completed_status)
        return view_daily_plan_action_cb(update, context) 
    except (IndexError, ValueError) as e:
        logger.error(f"Error parseando callback_data para marcar tarea planning: {e}, data: {query.data}")
        if query.message: query.message.reply_text("⚠️ Error al procesar.")
    except Exception as e:
        logger.error(f"Error general marcando tarea planning: {e}, data: {query.data}")
        if query.message: query.message.reply_text("⚠️ Error inesperado.")
    return STATE_PLAN_VIEW_AND_MARK_MODE


# --- REGISTRO DE HANDLERS ---
def register_handlers(dp) -> None:
    planning_conv_handler = ConversationHandler(
        entry_points=[
            # El CB_PLAN_MAIN_MENU es el entry point desde main.py, que llama a planning_menu
            # y devuelve STATE_PLAN_MENU_ACTION.
            CallbackQueryHandler(planning_menu, pattern=f"^{config.CB_PLAN_MAIN_MENU}$")
            ],
        states={
            STATE_PLAN_MENU_ACTION: [ 
                CallbackQueryHandler(cb_plan_set_objective_action, pattern=f"^{config.CB_PLAN_SET_OBJECTIVE}$"),
                CallbackQueryHandler(cb_plan_set_important_action, pattern=f"^{config.CB_PLAN_SET_IMPORTANT}$"),
                CallbackQueryHandler(cb_plan_set_secondary_action, pattern=f"^{config.CB_PLAN_SET_SECONDARY}$"),
                CallbackQueryHandler(view_daily_plan_action_cb, pattern=f"^{config.CB_PLAN_VIEW_DAY}$"),
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
                # El botón "Volver a Planificación" desde la vista de tareas ahora usa CB_PLAN_MAIN_MENU
                # y es manejado por el entry_point del ConversationHandler.
                CallbackQueryHandler(planning_menu, pattern=f"^{config.CB_PLAN_MAIN_MENU}$")
            ]
        },
        fallbacks=[
            CommandHandler("cancelplanning", cancel_planning_subflow), 
            # Un /cancel global que te saque de toda la sección de planificación
            CommandHandler("cancel", lambda u,c: common_handlers.cancel_conversation_and_show_main_menu(u,c, UD_PLAN_CLEANUP_KEYS)),
            # Botón para volver al menú principal del BOT (CB_MAIN_MENU)
            CallbackQueryHandler(lambda u,c: common_handlers.cancel_conversation_and_show_main_menu(u,c, UD_PLAN_CLEANUP_KEYS), pattern=f"^{config.CB_MAIN_MENU}$")
            ],
        allow_reentry=True 
    )
    dp.add_handler(planning_conv_handler)