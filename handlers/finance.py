# handlers/finance.py

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

# Estados de la conversación para Finanzas
(
    STATE_FIN_MENU_ACTION,        # 0: Menú principal de finanzas, esperando selección.
    STATE_FIN_SUBMENU_TYPE_SELECT, # 1: Submenú de Ingresos o Gastos, esperando selección de tipo específico.
    STATE_FIN_GET_AMOUNT_INPUT    # 2: Esperando monto numérico para una transacción.
) = range(50, 53)

# Claves para context.user_data
UD_FIN_CURRENT_TRANSACTION_TYPE = 'fin_current_transaction_type'
UD_FIN_CLEANUP_KEYS = [UD_FIN_CURRENT_TRANSACTION_TYPE]


# --- MENÚ PRINCIPAL DE FINANZAS (Entry Point) ---
def finance_menu(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    user_id = query.from_user.id if query else update.effective_user.id

    has_access, access_message = db_utils.check_user_access(user_id)
    if not has_access:
        if query: query.answer(); query.edit_message_text(text=access_message)
        else: context.bot.send_message(chat_id=user_id, text=access_message)
        return ConversationHandler.END

    keyboard = [
        [InlineKeyboardButton("➕ Registrar Ingresos Mensuales", callback_data=config.CB_FIN_REG_INCOME_MENU)],
        [InlineKeyboardButton("➖ Registrar Gastos Diarios", callback_data=config.CB_FIN_REG_EXPENSE_MENU)],
        [InlineKeyboardButton("🏦 Registrar Ahorros Mensuales", callback_data=config.CB_FIN_REG_SAVINGS_ACTION)], # Inicia flujo de monto
        [InlineKeyboardButton("📊 Ver Resumen Financiero", callback_data=config.CB_FIN_VIEW_SUMMARY)],
        [common_handlers.get_back_to_main_menu_button()]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    message_text = (
        "💰 *Mis Finanzas*\n\n"
        "Lleva un control de tus ingresos, gastos y ahorros para alcanzar tus metas financieras.\n"
        "Elige una opción:"
    )
    
    if query:
        query.answer()
        query.edit_message_text(text=message_text, reply_markup=reply_markup, parse_mode='Markdown')
    else: 
        context.bot.send_message(chat_id=user_id, text=message_text, reply_markup=reply_markup, parse_mode='Markdown')
    return STATE_FIN_MENU_ACTION


# --- SUB-MENÚS PARA INGRESOS Y GASTOS ---
def cb_fin_show_income_submenu(update: Update, context: CallbackContext) -> int:
    query = update.callback_query; query.answer()
    keyboard = [
        [InlineKeyboardButton("💵 Ingreso Fijo Mensual", callback_data=config.CB_FIN_REG_FIXED_INCOME_START)],
        [InlineKeyboardButton("📈 Ingreso Extra/Variable Mensual", callback_data=config.CB_FIN_REG_VAR_INCOME_START)],
        [common_handlers.get_back_button(config.CB_FIN_MAIN_MENU, "⬅️ A Finanzas")]
    ]
    query.edit_message_text(text="➕ *Registrar Ingresos Mensuales:*\nSelecciona el tipo de ingreso:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    return STATE_FIN_SUBMENU_TYPE_SELECT

def cb_fin_show_expense_submenu(update: Update, context: CallbackContext) -> int:
    query = update.callback_query; query.answer()
    keyboard = [
        [InlineKeyboardButton("🧾 Gasto Fijo Diario", callback_data=config.CB_FIN_REG_FIXED_EXPENSE_START)],
        [InlineKeyboardButton("🛍️ Gasto Variable Diario", callback_data=config.CB_FIN_REG_VAR_EXPENSE_START)],
        [common_handlers.get_back_button(config.CB_FIN_MAIN_MENU, "⬅️ A Finanzas")]
    ]
    query.edit_message_text(text="➖ *Registrar Gastos Diarios:*\nSelecciona el tipo de gasto:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    return STATE_FIN_SUBMENU_TYPE_SELECT


# --- INICIO DE REGISTRO DE TRANSACCIÓN (Petición de Monto) ---
def start_amount_input_flow(update: Update, context: CallbackContext, transaction_type: str) -> int:
    query = update.callback_query
    if query: query.answer()
    context.user_data[UD_FIN_CURRENT_TRANSACTION_TYPE] = transaction_type
    
    prompt_map = {
        'income_fixed': "💵 Ingreso Fijo Mensual:\nEnvía el monto total.",
        'income_variable': "📈 Ingreso Variable Mensual:\nEnvía el monto.",
        'expense_fixed': "🧾 Gasto Fijo Diario:\nEnvía el monto del gasto.",
        'expense_variable': "🛍️ Gasto Variable Diario:\nEnvía el monto del gasto.",
        'savings': "🏦 Ahorro Mensual:\nEnvía el monto a ahorrar."
    }
    prompt = prompt_map.get(transaction_type, "Envía el monto:") + "\n\nO /cancelfinance para volver al menú de finanzas."
    
    target_chat_id = query.message.chat_id if query and query.message else update.effective_chat.id
    if query and query.message: query.edit_message_text(text=prompt)
    else: context.bot.send_message(chat_id=target_chat_id, text=prompt)
    return STATE_FIN_GET_AMOUNT_INPUT

# Callbacks que inician la petición de monto
def cb_fin_reg_fixed_income_start_action(update: Update, context: CallbackContext): return start_amount_input_flow(update, context, 'income_fixed')
def cb_fin_reg_var_income_start_action(update: Update, context: CallbackContext): return start_amount_input_flow(update, context, 'income_variable')
def cb_fin_reg_fixed_expense_start_action(update: Update, context: CallbackContext): return start_amount_input_flow(update, context, 'expense_fixed')
def cb_fin_reg_var_expense_start_action(update: Update, context: CallbackContext): return start_amount_input_flow(update, context, 'expense_variable')
def cb_fin_reg_savings_direct_action(update: Update, context: CallbackContext): return start_amount_input_flow(update, context, 'savings')


# --- OBTENER Y GUARDAR MONTO ---
def get_transaction_amount_input(update: Update, context: CallbackContext) -> int:
    user_text = update.message.text.strip()
    trans_type = context.user_data.get(UD_FIN_CURRENT_TRANSACTION_TYPE)
    user_id = update.effective_user.id

    try:
        amount = float(user_text)
        if amount <= 0:
            update.message.reply_text("⚠️ El monto debe ser positivo. Intenta de nuevo o /cancelfinance.")
            return STATE_FIN_GET_AMOUNT_INPUT
        
        date_obj = datetime.now(db_utils.LIMA_TZ).date()
        db_utils.save_finance_transaction(user_id, trans_type, amount, date_obj=date_obj)
        
        type_map = {'income_fixed': "Ingreso fijo", 'income_variable': "Ingreso variable",
                    'expense_fixed': "Gasto fijo", 'expense_variable': "Gasto variable", 'savings': "Ahorro"}
        update.message.reply_text(f"✅ {type_map.get(trans_type, 'Monto').capitalize()} de S/. {amount:.2f} guardado.")
        return cancel_finance_subflow(update, context) # Vuelve al menú de finanzas
    except ValueError:
        update.message.reply_text(config.MSG_REQUIRE_NUMBER + " Intenta de nuevo o /cancelfinance.")
        return STATE_FIN_GET_AMOUNT_INPUT

# --- VER RESUMEN FINANCIERO ---
def cb_fin_view_summary_action(update: Update, context: CallbackContext) -> int: # Renombrado
    # (Lógica interna idéntica a la última versión estable para Render)
    # ... (copia el contenido de view_finance_summary_cb de la respuesta anterior) ...
    # Solo asegurar que el botón de volver use config.CB_FIN_MAIN_MENU
    query = update.callback_query; user_id = query.from_user.id; query.answer()
    now = datetime.now(db_utils.LIMA_TZ); month_s = now.strftime("%Y-%m"); day_o = now.date()

    inc_f = sum(float(dict(t)['amount']) for t in db_utils.get_finance_transactions(user_id, month_s, trans_type='income_fixed'))
    inc_v = sum(float(dict(t)['amount']) for t in db_utils.get_finance_transactions(user_id, month_s, trans_type='income_variable'))
    total_inc = inc_f + inc_v
    total_sav = sum(float(dict(t)['amount']) for t in db_utils.get_finance_transactions(user_id, month_s, trans_type='savings'))
    
    all_exp_dr = db_utils.get_finance_transactions(user_id, month_s, trans_type='expense_fixed') + \
                 db_utils.get_finance_transactions(user_id, month_s, trans_type='expense_variable')
    total_exp_month = sum(float(dict(t)['amount']) for t in all_exp_dr if dict(t)['transaction_date'] <= day_o)
            
    exp_today_f = sum(float(dict(t)['amount']) for t in db_utils.get_finance_transactions(user_id, day_obj=day_o, trans_type='expense_fixed'))
    exp_today_v = sum(float(dict(t)['amount']) for t in db_utils.get_finance_transactions(user_id, day_obj=day_o, trans_type='expense_variable'))
    total_exp_today = exp_today_f + exp_today_v
    balance = (total_inc - total_sav) - total_exp_month

    summary = f"📊 *Resumen Financiero ({now.strftime('%B %Y')})*\n\n"
    summary += f"💵 Ingresos Mes: S/. {total_inc:.2f} (Fijos: {inc_f:.2f}, Variables: {inc_v:.2f})\n"
    summary += f"🏦 Ahorros Mes: S/. {total_sav:.2f}\n"
    summary += f"🧾 Gastos: Hoy S/. {total_exp_today:.2f} | Mes (hasta hoy) S/. {total_exp_month:.2f}\n\n"
    summary += f"💰 Saldo Estimado Mes: S/. {balance:.2f}\n\n_Registra gastos diarios._"

    kbd = [[common_handlers.get_back_button(config.CB_FIN_MAIN_MENU, "⬅️ A Finanzas")]]
    query.edit_message_text(text=summary, reply_markup=InlineKeyboardMarkup(kbd), parse_mode='Markdown')
    return STATE_FIN_MENU_ACTION


# --- CANCELACIÓN ---
def cancel_finance_subflow(update: Update, context: CallbackContext) -> int: # /cancelfinance
    """Cancela el subflujo actual y vuelve al menú de finanzas."""
    for key in UD_FIN_CLEANUP_KEYS:
        if key in context.user_data: del context.user_data[key]
    if update.message: update.message.reply_text("Subproceso cancelado.")
    elif update.callback_query: update.callback_query.answer("Cancelado.")
    return finance_menu(update, context) # Vuelve al menú de finanzas

# --- REGISTRO DE HANDLERS ---
def register_handlers(dp) -> None:
    finance_conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(finance_menu, pattern=f"^{config.CB_FIN_MAIN_MENU}$")],
        states={
            STATE_FIN_MENU_ACTION: [ 
                CallbackQueryHandler(cb_fin_show_income_submenu, pattern=f"^{config.CB_FIN_REG_INCOME_MENU}$"),
                CallbackQueryHandler(cb_fin_show_expense_submenu, pattern=f"^{config.CB_FIN_REG_EXPENSE_MENU}$"),
                CallbackQueryHandler(cb_fin_reg_savings_direct_action, pattern=f"^{config.CB_FIN_REG_SAVINGS_ACTION}$"),
                CallbackQueryHandler(cb_fin_view_summary_action, pattern=f"^{config.CB_FIN_VIEW_SUMMARY}$"),
            ],
            STATE_FIN_SUBMENU_TYPE_SELECT: [ 
                CallbackQueryHandler(cb_fin_reg_fixed_income_start_action, pattern=f"^{config.CB_FIN_REG_FIXED_INCOME_START}$"),
                CallbackQueryHandler(cb_fin_reg_var_income_start_action, pattern=f"^{config.CB_FIN_REG_VAR_INCOME_START}$"),
                CallbackQueryHandler(cb_fin_reg_fixed_expense_start_action, pattern=f"^{config.CB_FIN_REG_FIXED_EXPENSE_START}$"),
                CallbackQueryHandler(cb_fin_reg_var_expense_start_action, pattern=f"^{config.CB_FIN_REG_VAR_EXPENSE_START}$"),
                CallbackQueryHandler(finance_menu, pattern=f"^{config.CB_FIN_MAIN_MENU}$"), # "Volver a Finanzas" desde submenú
            ],
            STATE_FIN_GET_AMOUNT_INPUT: [ 
                MessageHandler(Filters.text & ~Filters.command, get_transaction_amount_input),
            ],
        },
        fallbacks=[
            CommandHandler("cancelfinance", cancel_finance_subflow),
            CommandHandler("cancel", lambda u,c: common_handlers.cancel_conversation_and_show_main_menu(u,c, UD_FIN_CLEANUP_KEYS)),
            CallbackQueryHandler(lambda u,c: common_handlers.cancel_conversation_and_show_main_menu(u,c, UD_FIN_CLEANUP_KEYS), pattern=f"^{config.CB_MAIN_MENU}$")
            ],
        allow_reentry=True
    )
    dp.add_handler(finance_conv_handler)