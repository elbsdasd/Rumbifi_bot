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
from datetime import datetime, date # Importar date

import config
from utils import database as db_utils
from . import common_handlers
# La importación de start_access.send_main_menu_message se hará a través de common_handlers.cancel_conversation...

logger = logging.getLogger(__name__)

# Estados de la conversación para el flujo de AÑADIR ítems de planificación
(
    STATE_PLAN_GET_TYPE_DESCRIPTION, # Esperando descripción después de elegir tipo
    STATE_PLAN_GET_OBJECTIVE_REMINDER # Esperando hora de recordatorio SOLO para el objetivo
) = range(30, 32) # Nuevo rango para evitar colisiones

# Estados para el flujo de VER Y MARCAR tareas
(
    STATE_PLAN_VIEW_MODE # Estado activo mientras se muestra la lista de tareas para marcar
) = range(32, 33)


# Claves para context.user_data
UD_PLAN_CURRENT_ITEM_TYPE = 'plan_current_item_type' # 'objective', 'important', 'secondary'
UD_PLAN_TEMP_DESCRIPTION_LIST = 'plan_temp_description_list' # Lista de textos para imp/sec
UD_PLAN_CLEANUP_KEYS_ADD_FLOW = [UD_PLAN_CURRENT_ITEM_TYPE, UD_PLAN_TEMP_DESCRIPTION_LIST]


# --- MENÚ PRINCIPAL DE PLANIFICACIÓN (Entry point para handlers de esta sección) ---
def planning_menu(update: Update, context: CallbackContext) -> int:
    """
    Muestra el menú de la sección 'Planificar Mi Día'.
    Este es el entry point principal para los ConversationHandlers de planificación.
    """
    query = update.callback_query
    user_id = query.from_user.id if query else update.effective_user.id

    has_access, access_message = db_utils.check_user_access(user_id)
    if not has_access:
        # Esta función es un entry point a un ConversationHandler,
        # si no hay acceso, no deberíamos entrar en la conversación.
        # El handler de main.py que llama a esto es un CallbackQueryHandler simple.
        # Así que podemos editar/enviar mensaje y NO retornar un estado de conversación.
        if query:
            query.answer()
            query.edit_message_text(text=access_message)
        else: # No debería ocurrir si se accede por botón
            context.bot.send_message(chat_id=user_id, text=access_message)
        return ConversationHandler.END # Terminar cualquier conversación potencial

    keyboard = [
        [InlineKeyboardButton("🎯 Objetivo Principal", callback_data=config.CB_PLAN_SET_OBJECTIVE)],
        [InlineKeyboardButton("⭐ Tareas Importantes (hasta 3)", callback_data=config.CB_PLAN_SET_IMPORTANT)],
        [InlineKeyboardButton("📝 Tareas Secundarias", callback_data=config.CB_PLAN_SET_SECONDARY)],
        [InlineKeyboardButton("📋 Ver Plan del Día y Marcar", callback_data=config.CB_PLAN_VIEW_DAY)],
        [common_handlers.get_back_to_main_menu_button()]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    message_text = (
        "🗓️ *Planificar Mi Día*\n\n"
        "Método 1-3-5: 1 Objetivo, 3 Tareas Imp., 5+ Tareas Sec.\n"
        "Elige una opción:"
    )
    
    if query:
        query.answer()
        query.edit_message_text(text=message_text, reply_markup=reply_markup, parse_mode='Markdown')
    else: 
        context.bot.send_message(chat_id=user_id, text=message_text, reply_markup=reply_markup, parse_mode='Markdown')
        
    return ConversationHandler. आगे # Placeholder, el estado real lo determinará el handler que lo use


# --- FLUJO: AÑADIR ITEMS DE PLANIFICACIÓN ---
def start_add_item_flow(update: Update, context: CallbackContext, item_type: str) -> int:
    """Inicia el flujo para añadir un tipo de ítem (objetivo, importante, secundario)."""
    query = update.callback_query
    if query: query.answer()
    
    context.user_data[UD_PLAN_CURRENT_ITEM_TYPE] = item_type
    context.user_data[UD_PLAN_TEMP_DESCRIPTION_LIST] = [] # Para recolectar descripciones

    prompt_map = {
        'objective': "🎯 Objetivo Principal del Día:\n\nEscribe tu objetivo. (/cancelplanning para salir)",
        'important': "⭐ Tareas Importantes (máx. 3):\n\nEnvía la primera tarea. Puedes añadir hasta 3. Escribe /doneplanning al terminar, o /cancelplanning.",
        'secondary': "📝 Tareas Secundarias:\n\nEnvía tu primera tarea secundaria. Puedes añadir varias. Escribe /doneplanning al terminar, o /cancelplanning."
    }
    prompt_text = prompt_map.get(item_type)

    if query and query.message:
        query.edit_message_text(text=prompt_text)
    else: # Si no hay query o message (ej. reentrada a estado)
        context.bot.send_message(chat_id=update.effective_chat.id, text=prompt_text)
        
    return STATE_PLAN_GET_TYPE_DESCRIPTION

# Callbacks para los botones de añadir
def cb_plan_set_objective(update: Update, context: CallbackContext) -> int:
    return start_add_item_flow(update, context, 'objective')
def cb_plan_set_important(update: Update, context: CallbackContext) -> int:
    return start_add_item_flow(update, context, 'important')
def cb_plan_set_secondary(update: Update, context: CallbackContext) -> int:
    return start_add_item_flow(update, context, 'secondary')

def get_item_description_input(update: Update, context: CallbackContext) -> int:
    """Recibe la descripción de la tarea/objetivo."""
    user_text = update.message.text
    item_type = context.user_data.get(UD_PLAN_CURRENT_ITEM_TYPE)
    
    if item_type == 'objective':
        # Para el objetivo, solo tomamos una descripción y luego pedimos recordatorio
        context.user_data[UD_PLAN_TEMP_DESCRIPTION_LIST] = [user_text] # Guardar como lista de 1
        update.message.reply_text(config.MSG_TIME_FORMAT_PROMPT)
        return STATE_PLAN_GET_OBJECTIVE_REMINDER
    
    elif item_type in ['important', 'secondary']:
        collected_list = context.user_data.get(UD_PLAN_TEMP_DESCRIPTION_LIST, [])
        
        if item_type == 'important' and len(collected_list) >= 3:
            update.message.reply_text("Ya has añadido 3 tareas importantes. Escribe /doneplanning para guardarlas.")
            return STATE_PLAN_GET_TYPE_DESCRIPTION # Seguir en este estado esperando /doneplanning

        collected_list.append(user_text)
        context.user_data[UD_PLAN_TEMP_DESCRIPTION_LIST] = collected_list
        
        count_msg = f"({len(collected_list)}/3)" if item_type == 'important' else ""
        update.message.reply_text(f"✅ Tarea '{user_text[:30]}...' añadida {count_msg}. Envía otra, o /doneplanning para guardar.")
        return STATE_PLAN_GET_TYPE_DESCRIPTION # Seguir esperando descripciones o /doneplanning
        
    logger.error(f"Tipo de ítem desconocido en get_item_description_input: {item_type}")
    return common_handlers.cancel_conversation_to_main_menu(update, context, UD_PLAN_CLEANUP_KEYS_ADD_FLOW)

def get_objective_reminder_input(update: Update, context: CallbackContext) -> int:
    """Recibe la hora del recordatorio para el Objetivo Principal."""
    user_text = update.message.text.lower()
    item_type = context.user_data.get(UD_PLAN_CURRENT_ITEM_TYPE)
    user_id = update.effective_user.id

    if item_type != 'objective':
        logger.warning("get_objective_reminder_input llamado para tipo no objetivo.")
        return common_handlers.cancel_conversation_to_main_menu(update, context, UD_PLAN_CLEANUP_KEYS_ADD_FLOW)

    reminder_time_to_save = None
    if user_text == 'no':
        update.message.reply_text("Entendido, sin recordatorio para el objetivo.")
    else:
        try:
            datetime.strptime(user_text, "%H:%M") # Validar formato
            reminder_time_to_save = user_text
            update.message.reply_text(f"Recordatorio para el objetivo programado a las {user_text}.")
        except ValueError:
            update.message.reply_text(config.MSG_TIME_FORMAT_ERROR + "\nIntenta de nuevo o escribe 'no'.")
            return STATE_PLAN_GET_OBJECTIVE_REMINDER 

    description_list = context.user_data.get(UD_PLAN_TEMP_DESCRIPTION_LIST)
    if description_list and description_list[0]:
        db_utils.save_planning_item(
            user_id=user_id, item_type='objective',
            text=description_list[0], reminder_time=reminder_time_to_save
        )
        update.message.reply_text("🎯 ¡Objetivo principal guardado!")
    else:
        update.message.reply_text("⚠️ Hubo un error, no se encontró la descripción del objetivo.")
    
    return common_handlers.cancel_conversation_to_main_menu(update, context, UD_PLAN_CLEANUP_KEYS_ADD_FLOW)

def done_adding_planning_items(update: Update, context: CallbackContext) -> int:
    """Comando /doneplanning: Guarda las tareas importantes o secundarias recolectadas."""
    user_id = update.effective_user.id
    item_type = context.user_data.get(UD_PLAN_CURRENT_ITEM_TYPE)
    descriptions_list = context.user_data.get(UD_PLAN_TEMP_DESCRIPTION_LIST, [])

    if not descriptions_list:
        update.message.reply_text("No has añadido ninguna tarea. Escribe /cancelplanning para volver.")
        return STATE_PLAN_GET_TYPE_DESCRIPTION 
    else:
        count = 0
        for desc_text in descriptions_list:
            # Por ahora, las tareas importantes/secundarias se guardan sin recordatorio individual.
            db_utils.save_planning_item(user_id=user_id, item_type=item_type, text=desc_text, reminder_time=None)
            count += 1
        update.message.reply_text(f"✅ ¡{count} tarea(s) '{item_type}' han sido guardadas!")

    return common_handlers.cancel_conversation_to_main_menu(update, context, UD_PLAN_CLEANUP_KEYS_ADD_FLOW)

def cancel_add_planning_flow(update: Update, context: CallbackContext) -> int:
    """Comando /cancelplanning para salir del flujo de añadir."""
    return common_handlers.cancel_conversation_to_main_menu(update, context, UD_PLAN_CLEANUP_KEYS_ADD_FLOW)

# --- FLUJO: VER Y MARCAR TAREAS DEL DÍA ---
def view_daily_plan_action_cb(update: Update, context: CallbackContext) -> int:
    """Muestra el plan del día y permite marcar tareas."""
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
            if item.get("type") in categorized_items:
                categorized_items[item.get("type")].append(item)

        for category_key, category_title in item_categories.items():
            if categorized_items[category_key]:
                message_text += f"*{category_title}*\n"
                for item in categorized_items[category_key]:
                    status_emoji = "⏳" 
                    if item.get("completed") is True: status_emoji = "✅"
                    elif item.get("completed") is False: status_emoji = "❌"
                    
                    reminder_str = ""
                    if item.get("reminder_time"): # Es un objeto datetime.time
                        reminder_str = f" ({item['reminder_time'].strftime('%H:%M')})"
                    message_text += f"{status_emoji} {item['text']}{reminder_str}\n"
                    
                    if item.get("completed") is None: # Solo mostrar botones si aún no se ha marcado
                        item_id = item['key'] # 'key' es el alias de item_id (entero)
                        cb_done = f"{config.CB_TASK_DONE_PREFIX}planning_{item_id}"
                        cb_not_done = f"{config.CB_TASK_NOT_DONE_PREFIX}planning_{item_id}"
                        task_short = item['text'][:15] + ('…' if len(item['text']) > 15 else '')
                        buttons_row = [
                            InlineKeyboardButton(f"✅ Hecho '{task_short}'", callback_data=cb_done),
                            InlineKeyboardButton(f"❌ No '{task_short}'", callback_data=cb_not_done)
                        ]
                        keyboard_markup_rows.append(buttons_row)
                message_text += "\n"
            
    keyboard_markup_rows.append([common_handlers.get_back_button(config.CB_PLAN_MAIN_MENU, "⬅️ Volver a Planificación")])
    reply_markup = InlineKeyboardMarkup(keyboard_markup_rows)
    
    if query and query.message:
        try:
            query.edit_message_text(text=message_text, reply_markup=reply_markup, parse_mode='Markdown')
        except Exception as e:
            logger.warning(f"Error editando vista de plan diario (planning), enviando nuevo: {e}")
            context.bot.send_message(chat_id=user_id, text=message_text, reply_markup=reply_markup, parse_mode='Markdown')
    else: # No debería ocurrir si se accede por botón
         context.bot.send_message(chat_id=user_id, text=message_text, reply_markup=reply_markup, parse_mode='Markdown')
        
    return STATE_PLAN_VIEW_MODE

def mark_planning_task_cb(update: Update, context: CallbackContext) -> int:
    """Callback para marcar una tarea de planificación como hecha o no hecha."""
    query = update.callback_query
    query.answer()
    callback_data = query.data
    try:
        parts = callback_data.split('_')
        action_prefix_part = parts[0] + "_" + parts[1] # "task_done" o "task_notdone"
        # section_part = parts[2] # "planning"
        item_id = int(parts[3]) # El ID del ítem
        completed_status = (action_prefix_part == config.CB_TASK_DONE_PREFIX[:-1]) # Compara con "task_done"
        db_utils.update_planning_item_status(item_id, completed_status)
        # Refrescar la vista
        return view_daily_plan_action_cb(update, context)
    except (IndexError, ValueError) as e:
        logger.error(f"Error parseando callback_data para marcar tarea de planning: {e}, data: {callback_data}")
        query.message.reply_text("⚠️ Error al procesar la acción.")
    except Exception as e:
        logger.error(f"Error general marcando tarea de planning: {e}, data: {callback_data}")
        query.message.reply_text("⚠️ Error inesperado al marcar la tarea.")
    return STATE_PLAN_VIEW_MODE # Quedarse en la vista o ir a un estado de error/menú

def back_to_planning_menu_from_view(update: Update, context: CallbackContext) -> int:
    """Vuelve al menú de planificación desde la vista de tareas."""
    # Esta función es llamada por un CallbackQueryHandler con pattern CB_PLAN_MAIN_MENU
    # cuando se está en el estado STATE_PLAN_VIEW_MODE.
    # Llama a planning_menu para reconstruir el menú.
    return planning_menu(update, context)


# --- REGISTRO DE HANDLERS ---
def register_handlers(dp) -> None:
    # ConversationHandler para AÑADIR ítems (objetivo, importantes, secundarios)
    add_item_conv_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(cb_plan_set_objective, pattern=f"^{config.CB_PLAN_SET_OBJECTIVE}$"),
            CallbackQueryHandler(cb_plan_set_important, pattern=f"^{config.CB_PLAN_SET_IMPORTANT}$"),
            CallbackQueryHandler(cb_plan_set_secondary, pattern=f"^{config.CB_PLAN_SET_SECONDARY}$"),
        ],
        states={
            STATE_PLAN_GET_TYPE_DESCRIPTION: [
                MessageHandler(Filters.text & ~Filters.command, get_item_description_input),
                CommandHandler("doneplanning", done_adding_planning_items),
            ],
            STATE_PLAN_GET_OBJECTIVE_REMINDER: [
                MessageHandler(Filters.text & ~Filters.command, get_objective_reminder_input)
            ],
        },
        fallbacks=[CommandHandler("cancelplanning", cancel_add_planning_flow)],
        # Cuando este ConvHandler termina, queremos volver al menú de planificación.
        # Esto se maneja llamando a common_handlers.cancel_conversation_to_main_menu,
        # que a su vez llama a start_access.send_main_menu_message.
        # O, idealmente, el estado de "reposo" del menú de planificación sería un estado del ConversationHandler principal.
        # Por ahora, la cancelación lleva al menú principal del bot.
        # Si queremos volver al menú de planificación:
        map_to_parent={ConversationHandler.END: ConversationHandler.END} # O un estado específico si está anidado
                                                                       # Si no está anidado, simplemente termina.
                                                                       # La función de cancelación se encarga de mostrar el menú.
    )
    dp.add_handler(add_item_conv_handler)

    # ConversationHandler para VER y MARCAR tareas
    view_mark_conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(view_daily_plan_action_cb, pattern=f"^{config.CB_PLAN_VIEW_DAY}$")],
        states={
            STATE_PLAN_VIEW_MODE: [
                CallbackQueryHandler(mark_planning_task_cb, pattern=f"^{config.CB_TASK_DONE_PREFIX}planning_"),
                CallbackQueryHandler(mark_planning_task_cb, pattern=f"^{config.CB_TASK_NOT_DONE_PREFIX}planning_"),
                # Botón "Volver a Planificación" desde la vista de tareas:
                CallbackQueryHandler(planning_menu, pattern=f"^{config.CB_PLAN_MAIN_MENU}$")
            ]
        },
        fallbacks=[CommandHandler("cancelplanning", cancel_add_planning_flow)], # Usar el mismo cancel
        map_to_parent={ConversationHandler.END: ConversationHandler.END }
    )
    dp.add_handler(view_mark_conv_handler)

    # El handler para el botón CB_PLAN_MAIN_MENU (que llama a planning.planning_menu)
    # se registra en main.py y actúa como el entry point general para esta sección.