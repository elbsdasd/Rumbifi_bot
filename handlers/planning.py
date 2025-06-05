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
# from .start_access import send_main_menu # Se usará a través de common_handlers.cancel_conversation...

logger = logging.getLogger(__name__)

# Estados de la conversación (se mantienen)
(
    STATE_PLAN_ACTION_SELECT,
    STATE_PLAN_GET_DESCRIPTION,
    STATE_PLAN_GET_REMINDER_TIME,
    STATE_PLAN_VIEW_DAILY_TASKS 
) = range(4) 

# Claves para context.user_data (se mantienen)
UD_PLAN_CURRENT_TYPE = 'plan_current_type'
UD_PLAN_TEMP_DESCRIPTION = 'plan_temp_description'
UD_PLAN_TEMP_REMINDER_TIME = 'plan_temp_reminder_time'
UD_PLAN_IMPORTANT_TASKS_COLLECTED = 'plan_important_tasks_collected'
UD_PLAN_SECONDARY_TASKS_COLLECTED = 'plan_secondary_tasks_collected'
UD_PLAN_CLEANUP_KEYS = [UD_PLAN_CURRENT_TYPE, UD_PLAN_TEMP_DESCRIPTION, UD_PLAN_TEMP_REMINDER_TIME,
                        UD_PLAN_IMPORTANT_TASKS_COLLECTED, UD_PLAN_SECONDARY_TASKS_COLLECTED]


# --- MENÚ PRINCIPAL DE PLANIFICACIÓN ---
def planning_menu(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    user_id = query.from_user.id if query else update.effective_user.id


    has_access, access_message = db_utils.check_user_access(user_id)
    if not has_access:
        if query:
            query.answer()
            query.edit_message_text(text=access_message)
        else: # Si se llama sin query (ej. después de cancelar una conversación)
            context.bot.send_message(chat_id=user_id, text=access_message)
        return ConversationHandler.END

    keyboard = [
        [InlineKeyboardButton("🎯 Establecer Objetivo Principal", callback_data=config.CB_PLAN_SET_OBJECTIVE)],
        [InlineKeyboardButton("⭐ Definir Tareas Importantes (hasta 3)", callback_data=config.CB_PLAN_SET_IMPORTANT)],
        [InlineKeyboardButton("📝 Listar Tareas Secundarias", callback_data=config.CB_PLAN_SET_SECONDARY)],
        [InlineKeyboardButton("📋 Ver Plan del Día y Marcar Avance", callback_data=config.CB_PLAN_VIEW_DAY)],
        [common_handlers.get_main_menu_button()]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    message_text = (
        "🗓️ *Planificar Mi Día*\n\n"
        "Te presento el método 1-3-5: cada día anota:\n"
        "1️⃣ Objetivo Principal\n"
        "3️⃣ Tareas Importantes\n"
        "5️⃣ (o más) Tareas Secundarias\n\n"
        "Elige una opción:"
    )
    
    if query:
        query.answer()
        query.edit_message_text(text=message_text, reply_markup=reply_markup, parse_mode='Markdown')
    else: 
        context.bot.send_message(chat_id=user_id, text=message_text, reply_markup=reply_markup, parse_mode='Markdown')
        
    return STATE_PLAN_ACTION_SELECT


# --- INICIO DE FLUJO PARA REGISTRAR ITEMS ---
def start_item_registration(update: Update, context: CallbackContext, item_type: str) -> int:
    query = update.callback_query
    query.answer()
    
    context.user_data[UD_PLAN_CURRENT_TYPE] = item_type
    context.user_data[UD_PLAN_TEMP_DESCRIPTION] = None # Reiniciar por si acaso
    context.user_data[UD_PLAN_TEMP_REMINDER_TIME] = None # Reiniciar

    # Limpiar listas de tareas recolectadas si se inicia un nuevo tipo
    if UD_PLAN_IMPORTANT_TASKS_COLLECTED in context.user_data:
        del context.user_data[UD_PLAN_IMPORTANT_TASKS_COLLECTED]
    if UD_PLAN_SECONDARY_TASKS_COLLECTED in context.user_data:
        del context.user_data[UD_PLAN_SECONDARY_TASKS_COLLECTED]


    if item_type == 'important':
        context.user_data[UD_PLAN_IMPORTANT_TASKS_COLLECTED] = []
        prompt_text = "⭐ Tareas Importantes (máx. 3):\n\nEnvía la primera tarea importante del día. Puedes añadir hasta 3. Escribe /doneplanning cuando termines, o /cancelplanning para salir."
    elif item_type == 'secondary':
        context.user_data[UD_PLAN_SECONDARY_TASKS_COLLECTED] = []
        prompt_text = "📝 Tareas Secundarias:\n\nEnvía tu primera tarea secundaria. Puedes añadir varias. Escribe /doneplanning cuando termines, o /cancelplanning para salir."
    else: # objective
        prompt_text = f"🎯 Objetivo Principal del Día:\n\nEscribe tu objetivo principal para hoy.\n\nEscribe /cancelplanning para salir."

    query.edit_message_text(text=prompt_text)
    return STATE_PLAN_GET_DESCRIPTION


def plan_set_objective_cb(update: Update, context: CallbackContext) -> int:
    return start_item_registration(update, context, 'objective')

def plan_set_important_cb(update: Update, context: CallbackContext) -> int:
    return start_item_registration(update, context, 'important')

def plan_set_secondary_cb(update: Update, context: CallbackContext) -> int:
    return start_item_registration(update, context, 'secondary')


# --- OBTENER DESCRIPCIÓN DE LA TAREA ---
def get_task_description(update: Update, context: CallbackContext) -> int:
    user_text = update.message.text
    item_type = context.user_data.get(UD_PLAN_CURRENT_TYPE)

    if item_type == 'objective':
        context.user_data[UD_PLAN_TEMP_DESCRIPTION] = user_text
        update.message.reply_text(config.MSG_TIME_FORMAT_PROMPT)
        return STATE_PLAN_GET_REMINDER_TIME
    
    elif item_type == 'important':
        collected_tasks = context.user_data.get(UD_PLAN_IMPORTANT_TASKS_COLLECTED, [])
        if len(collected_tasks) < 3:
            collected_tasks.append({"text": user_text, "reminder_time": None}) 
            context.user_data[UD_PLAN_IMPORTANT_TASKS_COLLECTED] = collected_tasks
            if len(collected_tasks) < 3:
                update.message.reply_text(f"✅ Tarea importante '{user_text[:30]}...' añadida ({len(collected_tasks)}/3). Envía la siguiente, o escribe /doneplanning.")
                return STATE_PLAN_GET_DESCRIPTION 
            else:
                update.message.reply_text(f"✅ Has añadido 3 tareas importantes. Escribe /doneplanning para guardarlas.")
                return STATE_PLAN_GET_DESCRIPTION 
        else:
            update.message.reply_text("Ya has añadido el máximo de 3 tareas importantes. Escribe /doneplanning para guardarlas.")
            return STATE_PLAN_GET_DESCRIPTION

    elif item_type == 'secondary':
        collected_tasks = context.user_data.get(UD_PLAN_SECONDARY_TASKS_COLLECTED, [])
        collected_tasks.append({"text": user_text, "reminder_time": None})
        context.user_data[UD_PLAN_SECONDARY_TASKS_COLLECTED] = collected_tasks
        update.message.reply_text(f"✅ Tarea secundaria '{user_text[:30]}...' añadida. Envía otra, o escribe /doneplanning.")
        return STATE_PLAN_GET_DESCRIPTION
        
    # Fallback si item_type es desconocido (no debería pasar)
    logger.error(f"Tipo de ítem desconocido en get_task_description: {item_type}")
    return common_handlers.cancel_conversation_to_main_menu(update, context, UD_PLAN_CLEANUP_KEYS)


# --- OBTENER HORA DEL RECORDATORIO (Para Objetivo Principal) ---
def get_reminder_time(update: Update, context: CallbackContext) -> int:
    user_text = update.message.text.lower()
    item_type = context.user_data.get(UD_PLAN_CURRENT_TYPE)
    
    if item_type != 'objective': # Esta función es solo para el objetivo principal
        logger.warning("get_reminder_time llamado incorrectamente para tipo no objetivo.")
        return common_handlers.cancel_conversation_to_main_menu(update, context, UD_PLAN_CLEANUP_KEYS)

    if user_text == 'no':
        context.user_data[UD_PLAN_TEMP_REMINDER_TIME] = None
        update.message.reply_text("Entendido, sin recordatorio para el objetivo.")
    else:
        try:
            datetime.strptime(user_text, "%H:%M") # Validar formato
            context.user_data[UD_PLAN_TEMP_REMINDER_TIME] = user_text
            update.message.reply_text(f"Recordatorio para el objetivo programado a las {user_text}.")
        except ValueError:
            update.message.reply_text(config.MSG_TIME_FORMAT_ERROR + "\nIntenta de nuevo o escribe 'no'.")
            return STATE_PLAN_GET_REMINDER_TIME 

    description = context.user_data.get(UD_PLAN_TEMP_DESCRIPTION)
    reminder = context.user_data.get(UD_PLAN_TEMP_REMINDER_TIME)
    if description:
        db_utils.save_planning_item( # Ahora interactúa con PostgreSQL
            user_id=update.effective_user.id,
            item_type='objective',
            text=description,
            reminder_time=reminder
        )
        update.message.reply_text("🎯 ¡Objetivo principal guardado!")
    else:
        update.message.reply_text("⚠️ Hubo un error, no se encontró la descripción del objetivo.")
    
    return common_handlers.cancel_conversation_to_main_menu(update, context, UD_PLAN_CLEANUP_KEYS)


# --- FINALIZAR REGISTRO DE TAREAS (IMPORTANTES/SECUNDARIAS) ---
def done_planning_tasks(update: Update, context: CallbackContext) -> int:
    user_id = update.effective_user.id
    item_type = context.user_data.get(UD_PLAN_CURRENT_TYPE)
    
    tasks_to_save_data = []
    if item_type == 'important':
        tasks_to_save_data = context.user_data.get(UD_PLAN_IMPORTANT_TASKS_COLLECTED, [])
    elif item_type == 'secondary':
        tasks_to_save_data = context.user_data.get(UD_PLAN_SECONDARY_TASKS_COLLECTED, [])

    if not tasks_to_save_data:
        update.message.reply_text("No has añadido ninguna tarea para guardar. Escribe /cancelplanning para volver.")
        return STATE_PLAN_GET_DESCRIPTION # Quedarse en el estado de descripción
    else:
        count = 0
        for task_entry in tasks_to_save_data:
            db_utils.save_planning_item(
                user_id=user_id,
                item_type=item_type,
                text=task_entry["text"],
                reminder_time=task_entry.get("reminder_time") # Por ahora, siempre None para estas
            )
            count += 1
        update.message.reply_text(f"✅ ¡{count} tarea(s) '{item_type}' han sido guardadas!")

    return common_handlers.cancel_conversation_to_main_menu(update, context, UD_PLAN_CLEANUP_KEYS)


# --- VER Y MARCAR TAREAS DEL DÍA ---
def view_daily_plan_cb(update: Update, context: CallbackContext) -> int: # Puede ser un estado o un callback simple
    query = update.callback_query
    user_id = query.from_user.id if query else update.effective_user.id
    
    if query: query.answer()

    today_lima_date_obj = datetime.now(db_utils.LIMA_TZ).date() # Usar objeto date
    items = db_utils.get_daily_planning_items(user_id, today_lima_date_obj) # Espera objeto date

    message_text = "📋 *Tu Plan para Hoy:* \n\n"
    keyboard_markup_rows = []

    if not items:
        message_text += "No tienes nada planeado para hoy. ¡Añade algunas tareas desde el menú de planificación!"
    else:
        item_categories = {"objective": "🎯 Objetivo:", "important": "⭐ Importantes:", "secondary": "📝 Secundarias:"}
        categorized_items = {"objective": [], "important": [], "secondary": []}
        for item_dictrow in items: # item_dictrow es un DictRow de psycopg2
            item = dict(item_dictrow) # Convertir a dict normal para acceso más fácil
            if item.get("type") in categorized_items:
                categorized_items[item.get("type")].append(item)

        for category_key, category_title in item_categories.items():
            if categorized_items[category_key]:
                message_text += f"*{category_title}*\n"
                for item in categorized_items[category_key]:
                    status_emoji = "⏳" 
                    if item.get("marked_at"): 
                        status_emoji = "✅" if item.get("completed") else "❌"
                    
                    reminder_str = ""
                    if item.get("reminder_time"): # reminder_time es un objeto datetime.time
                        reminder_str = f" ({item['reminder_time'].strftime('%H:%M')})"

                    message_text += f"{status_emoji} {item['text']}{reminder_str}\n"
                    
                    if item.get("completed") is None: # Solo mostrar botones si 'completed' es NULL (no marcado)
                                                    # 'completed' es True, False, o None
                        # La 'key' ahora es 'item_id' (entero) de la tabla planning_items
                        item_id = item['key'] 
                        cb_done = f"{config.CB_TASK_DONE_PREFIX}planning_{item_id}"
                        cb_not_done = f"{config.CB_TASK_NOT_DONE_PREFIX}planning_{item_id}"
                        
                        task_short_text = item['text'][:15] + ('...' if len(item['text']) > 15 else '')
                        buttons_row = [
                            InlineKeyboardButton(f"✅ Hecho '{task_short_text}'", callback_data=cb_done),
                            InlineKeyboardButton(f"❌ No '{task_short_text}'", callback_data=cb_not_done)
                        ]
                        keyboard_markup_rows.append(buttons_row)
                message_text += "\n"
            
    keyboard_markup_rows.append([common_handlers.get_back_button(config.CB_PLAN_MAIN_MENU, "⬅️ Volver a Planificación")])
    reply_markup = InlineKeyboardMarkup(keyboard_markup_rows)
    
    if query:
        try:
            query.edit_message_text(text=message_text, reply_markup=reply_markup, parse_mode='Markdown')
        except Exception as e: # Si el mensaje es el mismo, puede fallar. Enviar nuevo.
            logger.warning(f"Error editando vista de plan diario, enviando nuevo: {e}")
            context.bot.send_message(chat_id=user_id, text=message_text, reply_markup=reply_markup, parse_mode='Markdown')
    else: # Llamado sin query
        context.bot.send_message(chat_id=user_id, text=message_text, reply_markup=reply_markup, parse_mode='Markdown')
        
    return STATE_PLAN_VIEW_DAILY_TASKS # Mantenerse en este estado para los callbacks de marcado


def mark_task_cb(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    query.answer()

    callback_data = query.data
    try:
        # Formato: CB_TASK_DONE_PREFIX + "planning_" + item_id (entero)
        parts = callback_data.split('_') # task_done_planning_123
        action_type = parts[0] + "_" + parts[1] # task_done o task_notdone
        # db_name_part = parts[2] # "planning"
        item_id = int(parts[3]) # El ID del ítem es un entero

        completed_status = (action_type == config.CB_TASK_DONE_PREFIX[:-1]) # Comparar con "task_done"
        
        db_utils.update_planning_item_status(item_id, completed_status) # Usa item_id
        
        # query.message.reply_text(f"Tarea marcada como {'✅ completada' if completed_status else '❌ no completada'}.")
        # No enviar mensaje nuevo, refrescar la lista directamente.
        
        # Para refrescar, volvemos a llamar la función que muestra la lista.
        # Necesitamos pasar 'update' y 'context' correctamente.
        # view_daily_plan_cb espera una query para editar, aquí tenemos una.
        return view_daily_plan_cb(update, context)

    except (IndexError, ValueError) as e:
        logger.error(f"Error parseando callback_data para marcar tarea: {e}, data: {callback_data}")
        query.message.reply_text("⚠️ Error al procesar la acción.")
    except Exception as e:
        logger.error(f"Error general marcando tarea: {e}, data: {callback_data}")
        query.message.reply_text("⚠️ Error inesperado al marcar la tarea.")
        
    return STATE_PLAN_VIEW_DAILY_TASKS # Quedarse en la vista o ir a un estado de error/menú


# --- CANCELACIÓN ---
def cancel_planning_flow_command(update: Update, context: CallbackContext) -> int:
    """Comando /cancelplanning para salir del flujo."""
    return common_handlers.cancel_conversation_to_main_menu(update, context, UD_PLAN_CLEANUP_KEYS)

# --- CONVERSATION HANDLER ---
def get_planning_conversation_handler() -> ConversationHandler:
    # Flujo para AÑADIR ítems (objetivo, importantes, secundarios)
    add_item_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(plan_set_objective_cb, pattern=f"^{config.CB_PLAN_SET_OBJECTIVE}$"),
            CallbackQueryHandler(plan_set_important_cb, pattern=f"^{config.CB_PLAN_SET_IMPORTANT}$"),
            CallbackQueryHandler(plan_set_secondary_cb, pattern=f"^{config.CB_PLAN_SET_SECONDARY}$"),
        ],
        states={
            STATE_PLAN_GET_DESCRIPTION: [
                MessageHandler(Filters.text & ~Filters.command, get_task_description),
                CommandHandler("doneplanning", done_planning_tasks),
            ],
            STATE_PLAN_GET_REMINDER_TIME: [ # Solo para el objetivo
                MessageHandler(Filters.text & ~Filters.command, get_reminder_time)
            ],
        },
        fallbacks=[ CommandHandler("cancelplanning", cancel_planning_flow_command) ],
        map_to_parent={ ConversationHandler.END: STATE_PLAN_ACTION_SELECT } # Volver al menú de planificación
    )

    # Flujo para VER Y MARCAR tareas (es un estado simple que espera callbacks)
    # Esto podría ser un ConversationHandler anidado o manejarse como estados de un handler más grande.
    # Por simplicidad, hacemos un handler separado para ver/marcar que no es parte de la conversación de "añadir".
    # No, view_daily_plan_cb es mejor como un callback que entra a un estado donde se esperan los botones de marcar.
    # O, como está ahora, view_daily_plan_cb es un callback, y mark_task_cb es otro callback.
    # Para que el refresco funcione, view_daily_plan_cb debe poder ser llamado por mark_task_cb.
    
    # Considerar que el menú de planificación (planning_menu) es el "estado" principal de esta sección.
    # Los ConversationHandlers son para flujos específicos DENTRO de esta sección.
    # Si usamos STATE_PLAN_ACTION_SELECT como "estado de reposo" del menú de planificación:
    
    main_planning_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(planning_menu, pattern=f"^{config.CB_PLAN_MAIN_MENU}$"), # Desde menú principal del bot
            CallbackQueryHandler(view_daily_plan_cb, pattern=f"^{config.CB_PLAN_VIEW_DAY}$") 
        ],
        states={
            STATE_PLAN_ACTION_SELECT: [ # Estado del menú de planificación
                # Los entry_points del add_item_handler se activarán desde aquí
                add_item_handler, # Anidar el ConversationHandler para añadir ítems
                CallbackQueryHandler(view_daily_plan_cb, pattern=f"^{config.CB_PLAN_VIEW_DAY}$") 
            ],
            STATE_PLAN_VIEW_DAILY_TASKS: [ # Estado cuando se está viendo la lista de tareas
                CallbackQueryHandler(mark_task_cb, pattern=f"^{config.CB_TASK_DONE_PREFIX}planning_"),
                CallbackQueryHandler(mark_task_cb, pattern=f"^{config.CB_TASK_NOT_DONE_PREFIX}planning_"),
                CallbackQueryHandler(planning_menu, pattern=f"^{config.CB_PLAN_MAIN_MENU}$") # Volver al menú de planif.
            ]
        },
        fallbacks=[
            CallbackQueryHandler(planning_menu, pattern=f"^{config.CB_PLAN_MAIN_MENU}$"), # Botón "Volver a Planificación"
            CommandHandler("cancel", common_handlers.cancel_conversation_to_main_menu) # Un /cancel global
        ],
        # allow_reentry=True # Importante si se vuelve al mismo menú
    )
    # Esta estructura de ConversationHandler anidado o múltiple puede ser compleja.
    # Simplificación: No usar un ConversationHandler global para la sección de planificación,
    # sino ConversationHandlers para flujos específicos (como añadir tarea) y callbacks directos.
    # La estructura actual en register_handlers es más simple:
    # 1. Un ConvHandler para "añadir" (objetivo, imp, sec).
    # 2. Callbacks directos para "ver" y "marcar".
    # Esto es lo que se implementa en register_handlers.

    return add_item_handler # Solo el handler para añadir tareas


def register_handlers(dp) -> None:
    """Registra todos los handlers para la sección de planificación."""
    # Handler para el flujo de añadir tareas (objetivo, importantes, secundarias)
    dp.add_handler(get_planning_conversation_handler())
    
    # Handler para el botón "Ver Plan del Día" y los botones de marcar tareas
    # (estos no necesitan ser parte de la misma conversación que "añadir tarea")
    # O podrían ser un ConversationHandler separado si la vista de tareas se vuelve más interactiva.
    # Por ahora, view_daily_plan_cb es un simple callback.
    # Y mark_task_cb es un callback que refresca llamando a view_daily_plan_cb.
    # Esto requiere que view_daily_plan_cb pueda manejar ser llamado después de un query.answer()
    # y que pueda editar el mensaje de la query original.
    
    # Este ConversationHandler es para el estado de "ver y marcar tareas"
    view_mark_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(view_daily_plan_cb, pattern=f"^{config.CB_PLAN_VIEW_DAY}$")],
        states={
            STATE_PLAN_VIEW_DAILY_TASKS: [ # Esperando callbacks de marcar o volver
                CallbackQueryHandler(mark_task_cb, pattern=f"^{config.CB_TASK_DONE_PREFIX}planning_"),
                CallbackQueryHandler(mark_task_cb, pattern=f"^{config.CB_TASK_NOT_DONE_PREFIX}planning_"),
                CallbackQueryHandler(planning_menu, pattern=f"^{config.CB_PLAN_MAIN_MENU}$"), # Volver al menú de planificación
            ]
        },
        fallbacks=[
            CallbackQueryHandler(planning_menu, pattern=f"^{config.CB_PLAN_MAIN_MENU}$"),
            CommandHandler("cancel", lambda u,c: common_handlers.cancel_conversation_to_main_menu(u,c, UD_PLAN_CLEANUP_KEYS))
            ],
        map_to_parent={ConversationHandler.END: -1} # -1 para que no afecte a otro handler si no es anidado
                                                    # O un estado global si es anidado.
    )
    dp.add_handler(view_mark_handler)

    # El handler para el menú de planificación principal (CB_PLAN_MAIN_MENU)
    # se registra en main.py, y llama a planning.planning_menu.
    # planning_menu entonces se convierte en un entry point para los ConversationHandlers de arriba.