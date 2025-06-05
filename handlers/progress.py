# handlers/progress.py

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import CallbackContext, CallbackQueryHandler
from datetime import datetime, date # Importar date
import io 

import config
from utils import database as db_utils
from utils import graphics as graphics_utils
from . import common_handlers

logger = logging.getLogger(__name__)

# --- MENÚ PRINCIPAL DE PROGRESO (Entry Point) ---
def progress_menu(update: Update, context: CallbackContext) -> None:
    """Muestra el menú de la sección 'Ver Mi Progreso'."""
    query = update.callback_query
    user_id = query.from_user.id if query else update.effective_user.id

    has_access, access_message = db_utils.check_user_access(user_id)
    if not has_access:
        if query: query.answer(); query.edit_message_text(text=access_message)
        else: context.bot.send_message(chat_id=user_id, text=access_message)
        return

    keyboard = [
        [InlineKeyboardButton("🎯 Gráfica de Disciplina Diaria", callback_data=config.CB_PROG_GRAPH_DISCIPLINE)],
        [InlineKeyboardButton("💹 Gráfica Financiera Mensual", callback_data=config.CB_PROG_GRAPH_FINANCE)],
        [InlineKeyboardButton("💪 Gráfica de Bienestar Físico Diario", callback_data=config.CB_PROG_GRAPH_WELLBEING)],
        [common_handlers.get_back_to_main_menu_button()] # Botón para volver al menú principal del bot
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    message_text = "📊 *Ver Mi Progreso*\n\nVisualiza tus avances. Elige una gráfica:"
    
    if query:
        query.answer()
        query.edit_message_text(text=message_text, reply_markup=reply_markup, parse_mode='Markdown')
    else: 
        context.bot.send_message(chat_id=user_id, text=message_text, reply_markup=reply_markup, parse_mode='Markdown')
    # No se retorna un estado de conversación aquí, ya que son callbacks directos.

# --- GENERACIÓN Y ENVÍO DE GRÁFICAS ---
def send_generated_chart(update: Update, context: CallbackContext, chart_image_buffer: io.BytesIO, caption_title: str):
    """Envía la imagen de la gráfica generada o un mensaje de 'sin datos'."""
    query = update.callback_query # Se asume que esta función es llamada desde un CallbackQuery
    user_id = query.from_user.id

    # Botón para volver al menú de progreso
    back_to_progress_menu_button = InlineKeyboardMarkup([[
        common_handlers.get_back_button(config.CB_PROG_MAIN_MENU, "⬅️ Volver a Gráficas")
    ]])

    if chart_image_buffer:
        try:
            context.bot.send_photo(
                chat_id=user_id,
                photo=chart_image_buffer, # El buffer ya está rebobinado desde graphics_utils
                caption=caption_title,
                reply_markup=back_to_progress_menu_button
            )
            # Opcional: Editar el mensaje original del menú de gráficas
            if query.message:
                 query.edit_message_text(text=f"Aquí tienes tu: {caption_title.split(':')[0]}") # Mensaje simple
        except Exception as e:
            logger.error(f"Error enviando foto de gráfica '{caption_title}': {e}")
            context.bot.send_message(chat_id=user_id, text="Hubo un error al generar tu gráfica. Intenta más tarde.", reply_markup=back_to_progress_menu_button)
    else:
        no_data_msg = f"No hay suficientes datos para generar la '{caption_title}'. ¡Sigue registrando tu progreso!"
        if query.message:
            query.edit_message_text(text=no_data_msg, reply_markup=back_to_progress_menu_button)
        else: # No debería pasar si se llama desde un callback de botón
            context.bot.send_message(chat_id=user_id, text=no_data_msg, reply_markup=back_to_progress_menu_button)

def cb_show_discipline_chart(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    user_id = query.from_user.id
    query.answer("Generando gráfica de disciplina...") 

    today_date_obj = datetime.now(db_utils.LIMA_TZ).date()
    planning_items_dr = db_utils.get_daily_planning_items(user_id, today_date_obj)
    
    completed = sum(1 for item_dr in planning_items_dr if dict(item_dr).get("marked_at") and dict(item_dr).get("completed") is True)
    not_done = sum(1 for item_dr in planning_items_dr if dict(item_dr).get("marked_at") and dict(item_dr).get("completed") is False)
                
    chart_buffer = graphics_utils.get_discipline_chart_image(completed, not_done)
    send_generated_chart(update, context, chart_buffer, "🎯 Disciplina Diaria (Tareas Marcadas)")

def cb_show_finance_chart(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    user_id = query.from_user.id
    query.answer("Generando gráfica financiera...")

    now_lima = datetime.now(db_utils.LIMA_TZ)
    current_month_str = now_lima.strftime("%Y-%m")

    inc_fixed = sum(float(dict(t)['amount']) for t in db_utils.get_finance_transactions(user_id, month_str=current_month_str, trans_type='income_fixed'))
    inc_var = sum(float(dict(t)['amount']) for t in db_utils.get_finance_transactions(user_id, month_str=current_month_str, trans_type='income_variable'))
    total_income = inc_fixed + inc_var
    savings = sum(float(dict(t)['amount']) for t in db_utils.get_finance_transactions(user_id, month_str=current_month_str, trans_type='savings'))
    exp_fixed = sum(float(dict(t)['amount']) for t in db_utils.get_finance_transactions(user_id, month_str=current_month_str, trans_type='expense_fixed'))
    exp_var = sum(float(dict(t)['amount']) for t in db_utils.get_finance_transactions(user_id, month_str=current_month_str, trans_type='expense_variable'))

    chart_buffer = graphics_utils.get_finance_chart_image(
        income_extra=inc_var, expenses_variable=exp_var,
        savings=savings, expenses_fixed=exp_fixed, income_total_bruto=total_income
    )
    send_generated_chart(update, context, chart_buffer, "💹 Distribución Financiera Mensual")

def cb_show_wellbeing_chart(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    user_id = query.from_user.id
    query.answer("Generando gráficas de bienestar...")
    today_date_obj = datetime.now(db_utils.LIMA_TZ).date()

    # Ejercicio
    ex_doc = db_utils.get_daily_wellbeing_doc_and_sub_items(user_id, 'exercise', today_date_obj)
    comp_ex = sum(1 for item_dr in ex_doc["items"] if dict(item_dr).get("marked_at") and dict(item_dr).get("completed") is True) if ex_doc else 0
    not_comp_ex = sum(1 for item_dr in ex_doc["items"] if dict(item_dr).get("marked_at") and dict(item_dr).get("completed") is False) if ex_doc else 0
    ex_chart_buffer = graphics_utils.get_wellbeing_exercise_chart_image(comp_ex, not_comp_ex)
    send_generated_chart(update, context, ex_chart_buffer, "💪 Progreso en Ejercicio Diario")

    # Dieta
    diet_main_doc = db_utils.get_daily_wellbeing_doc_and_sub_items(user_id, 'diet_main', today_date_obj)
    diet_extra_doc = db_utils.get_daily_wellbeing_doc_and_sub_items(user_id, 'diet_extra', today_date_obj)
    
    fulfilled_diet = sum(1 for item_dr in diet_main_doc["items"] if dict(item_dr).get("marked_at") and dict(item_dr).get("completed") is True) if diet_main_doc else 0
    not_fulfilled_diet = sum(1 for item_dr in diet_main_doc["items"] if dict(item_dr).get("marked_at") and dict(item_dr).get("completed") is False) if diet_main_doc else 0
    extras_count = len(diet_extra_doc["items"]) if diet_extra_doc and diet_extra_doc.get("items") else 0
    
    diet_chart_buffer = graphics_utils.get_wellbeing_diet_chart_image(fulfilled_diet, not_fulfilled_diet, extras_count)
    send_generated_chart(update, context, diet_chart_buffer, "🍎 Progreso en Alimentación Diaria")

# --- REGISTRO DE HANDLERS ---
def register_handlers(dp) -> None:
    dp.add_handler(CallbackQueryHandler(cb_show_discipline_chart, pattern=f"^{config.CB_PROG_GRAPH_DISCIPLINE}$"))
    dp.add_handler(CallbackQueryHandler(cb_show_finance_chart, pattern=f"^{config.CB_PROG_GRAPH_FINANCE}$"))
    dp.add_handler(CallbackQueryHandler(cb_show_wellbeing_chart, pattern=f"^{config.CB_PROG_GRAPH_WELLBEING}$"))
    # El handler para config.CB_PROG_MAIN_MENU (que llama a progress_menu) se registra en main.py