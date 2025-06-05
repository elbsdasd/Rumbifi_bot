import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import CallbackContext, CallbackQueryHandler
from datetime import datetime, date # Importar date
import io 

import config
from utils import database as db_utils # Interactúa con PostgreSQL
from utils import graphics as graphics_utils 
from . import common_handlers

logger = logging.getLogger(__name__)

# No se usa ConversationHandler aquí.

# --- MENÚ PRINCIPAL DE PROGRESO ---
def progress_menu(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    user_id = query.from_user.id if query else update.effective_user.id

    has_access, access_message = db_utils.check_user_access(user_id)
    if not has_access:
        if query:
            query.answer()
            query.edit_message_text(text=access_message)
        else:
            context.bot.send_message(chat_id=user_id, text=access_message)
        return

    keyboard = [
        [InlineKeyboardButton("🎯 Gráfica de Disciplina Diaria", callback_data=config.CB_PROG_GRAPH_DISCIPLINE)],
        [InlineKeyboardButton("💹 Gráfica Financiera Mensual", callback_data=config.CB_PROG_GRAPH_FINANCE)],
        [InlineKeyboardButton("💪 Gráfica de Bienestar Físico Diario", callback_data=config.CB_PROG_GRAPH_WELLBEING)],
        [common_handlers.get_main_menu_button()]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    message_text = "📊 *Ver Mi Progreso*\n\nVisualiza tus avances y mantén la motivación. Elige una gráfica:"
    
    if query:
        query.answer()
        query.edit_message_text(text=message_text, reply_markup=reply_markup, parse_mode='Markdown')
    else: 
        context.bot.send_message(chat_id=user_id, text=message_text, reply_markup=reply_markup, parse_mode='Markdown')


# --- GENERACIÓN Y ENVÍO DE GRÁFICAS ---
def send_chart(update: Update, context: CallbackContext, chart_image_buffer: io.BytesIO, caption: str):
    query = update.callback_query # Asumimos que siempre se llama desde un callback
    user_id = query.from_user.id

    # Crear un botón para volver al menú de progreso
    back_button_keyboard = InlineKeyboardMarkup([[
        common_handlers.get_back_button(config.CB_PROG_MAIN_MENU, "⬅️ Volver a Gráficas")
    ]])

    if chart_image_buffer:
        # Enviar la foto. No se puede editar un mensaje de texto para convertirlo en foto.
        # Así que siempre enviamos un nuevo mensaje con la foto.
        try:
            context.bot.send_photo(
                chat_id=user_id,
                photo=chart_image_buffer,
                caption=caption,
                reply_markup=back_button_keyboard
            )
            # Opcional: Borrar el mensaje del menú de gráficas para evitar clutter,
            # o editarlo a un mensaje simple si no se envió foto.
            if query.message:
                 query.edit_message_text(text=f"Aquí tienes tu gráfica de: {caption.split(':')[0]}") # Editar mensaje original a algo simple
        except Exception as e:
            logger.error(f"Error enviando foto de gráfica: {e}")
            context.bot.send_message(chat_id=user_id, text="Hubo un error al generar tu gráfica. Intenta más tarde.", reply_markup=back_button_keyboard)

    else:
        # Si no hay buffer (no hay datos), editar el mensaje actual o enviar uno nuevo.
        no_data_message = f"No hay suficientes datos para generar la '{caption.split(':')[0]}'. ¡Sigue registrando tu progreso!"
        if query.message:
            query.edit_message_text(text=no_data_message, reply_markup=back_button_keyboard)
        else:
            context.bot.send_message(chat_id=user_id, text=no_data_message, reply_markup=back_button_keyboard)


def show_discipline_chart_cb(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    user_id = query.from_user.id
    query.answer("Generando gráfica de disciplina...") 

    today_lima_date_obj = datetime.now(db_utils.LIMA_TZ).date() # Usar objeto date
    planning_items_dictrows = db_utils.get_daily_planning_items(user_id, today_lima_date_obj)
    
    completed_tasks = 0
    not_done_tasks = 0
    
    for item_dr in planning_items_dictrows:
        item = dict(item_dr) # Convertir a dict
        if item.get("marked_at"): 
            if item.get("completed") is True: # PostgreSQL puede devolver True/False/None
                completed_tasks += 1
            elif item.get("completed") is False:
                not_done_tasks += 1
                
    chart_buffer = graphics_utils.get_discipline_chart_image(completed_tasks, not_done_tasks)
    send_chart(update, context, chart_buffer, "🎯 Tu Disciplina Diaria (Tareas Marcadas)")


def show_finance_chart_cb(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    user_id = query.from_user.id
    query.answer("Generando gráfica financiera...")

    now_lima = datetime.now(db_utils.LIMA_TZ)
    current_month_str = now_lima.strftime("%Y-%m")

    inc_fixed = sum(float(t['amount']) for t in db_utils.get_finance_transactions(user_id, month_str=current_month_str, trans_type='income_fixed'))
    inc_var = sum(float(t['amount']) for t in db_utils.get_finance_transactions(user_id, month_str=current_month_str, trans_type='income_variable'))
    total_income_month = inc_fixed + inc_var
    
    total_savings_month = sum(float(t['amount']) for t in db_utils.get_finance_transactions(user_id, month_str=current_month_str, trans_type='savings'))
    
    exp_fixed_month = sum(float(t['amount']) for t in db_utils.get_finance_transactions(user_id, month_str=current_month_str, trans_type='expense_fixed'))
    exp_var_month = sum(float(t['amount']) for t in db_utils.get_finance_transactions(user_id, month_str=current_month_str, trans_type='expense_variable'))

    chart_buffer = graphics_utils.get_finance_chart_image(
        income_extra=inc_var, 
        expenses_variable=exp_var_month,
        savings=total_savings_month,
        expenses_fixed=exp_fixed_month,
        income_total_bruto=total_income_month
    )
    send_chart(update, context, chart_buffer, "💹 Tu Distribución Financiera Mensual")


def show_wellbeing_chart_cb(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    user_id = query.from_user.id
    query.answer("Generando gráficas de bienestar...")

    today_lima_date_obj = datetime.now(db_utils.LIMA_TZ).date()

    # Gráfica de Ejercicio
    exercise_doc_and_items = db_utils.get_daily_wellbeing_doc_and_items(user_id, 'exercise', today_lima_date_obj)
    completed_exercises = 0
    not_done_exercises = 0
    if exercise_doc_and_items and exercise_doc_and_items.get("items"):
        for item_data_dr in exercise_doc_and_items["items"]:
            item_data = dict(item_data_dr)
            if item_data.get("marked_at"):
                if item_data.get("completed") is True:
                    completed_exercises += 1
                elif item_data.get("completed") is False:
                    not_done_exercises += 1
    
    exercise_chart_buffer = graphics_utils.get_wellbeing_exercise_chart_image(completed_exercises, not_done_exercises)
    send_chart(update, context, exercise_chart_buffer, "💪 Tu Progreso en Ejercicio Diario")

    # Gráfica de Dieta
    diet_main_doc_and_items = db_utils.get_daily_wellbeing_doc_and_items(user_id, 'diet_main', today_lima_date_obj)
    diet_extra_doc_and_items = db_utils.get_daily_wellbeing_doc_and_items(user_id, 'diet_extra', today_lima_date_obj)

    diet_fulfilled = 0
    diet_not_fulfilled = 0
    if diet_main_doc_and_items and diet_main_doc_and_items.get("items"):
        for item_data_dr in diet_main_doc_and_items["items"]:
            item_data = dict(item_data_dr)
            if item_data.get("marked_at"):
                if item_data.get("completed") is True:
                    diet_fulfilled += 1
                elif item_data.get("completed") is False:
                    diet_not_fulfilled += 1
    
    extra_meals_count = 0
    if diet_extra_doc_and_items and diet_extra_doc_and_items.get("items"):
        extra_meals_count = len(diet_extra_doc_and_items["items"])

    diet_chart_buffer = graphics_utils.get_wellbeing_diet_chart_image(diet_fulfilled, diet_not_fulfilled, extra_meals_count)
    send_chart(update, context, diet_chart_buffer, "🍎 Tu Progreso en Alimentación Diaria")


# --- REGISTRO DE HANDLERS ---
def register_handlers(dp) -> None:
    dp.add_handler(CallbackQueryHandler(show_discipline_chart_cb, pattern=f"^{config.CB_PROG_GRAPH_DISCIPLINE}$"))
    dp.add_handler(CallbackQueryHandler(show_finance_chart_cb, pattern=f"^{config.CB_PROG_GRAPH_FINANCE}$"))
    dp.add_handler(CallbackQueryHandler(show_wellbeing_chart_cb, pattern=f"^{config.CB_PROG_GRAPH_WELLBEING}$"))
    # El handler para CB_PROG_MAIN_MENU (progress_menu) se registra en main.py