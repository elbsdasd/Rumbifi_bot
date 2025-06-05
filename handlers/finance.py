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
    STATE_FIN_MENU_ACTION,      # Menú principal de finanzas, esperando selección de acción
    STATE_FIN_SUBMENU_ACTION,   # Submenú de Ingresos o Gastos, esperando selección de tipo
    STATE_FIN_GET_AMOUNT_INPUT  # Esperando monto numérico para una transacción
) = range(50, 53) # Nuevo rango para estados

# Claves para context.user_data
UD_FIN_CURRENT_TRANSACTION_TYPE = 'fin_current_transaction_type' # 'income_fixed', 'expense_variable', etc.
UD_FIN_CLEANUP_KEYS_ADD_FLOW = [UD_FIN_CURRENT_TRANSACTION_TYPE]


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
        [InlineKeyboardButton("🏦 Registrar Ahorros Mensuales", callback_data=config.CB_FIN_REG_SAVINGS_ACTION)],
        [InlineKeyboardButton("📊 Ver Resumen Financiero", callback_data=config.CB_FIN_VIEW_SUMMARY)],
        [common_handlers.get_back_to_main_menu_button()]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    message_text = "💰 *Mis Finanzas*\n\nGestiona tus ingresos, gastos y ahorros:"
    
    if query:
        query.answer()
        query.edit_message_text(text=message_text, reply_markup=reply_markup, parse_mode='Markdown')
    else: 
        context.bot.send_message(chat_id=user_id, text=message_text, reply_markup=reply_markup, parse_mode='Markdown')
    return STATE_FIN_MENU_ACTION


# --- SUB-MENÚS PARA INGRESOS Y GASTOS ---
def cb_fin_reg_income_menu(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    query.answer()
    keyboard = [
        [InlineKeyboardButton("💵 Ingreso Fijo Mensual", callback_data=config.CB_FIN_REG_FIXED_INCOME_START)],
        [InlineKeyboardButton("📈 Ingreso Extra/Variable Mensual", callback_data=config.CB_FIN_REG_VAR_INCOME_START)],
        [common_handlers.get_back_button(config.CB_FIN_MAIN_MENU, "⬅️ Volver a Finanzas")] # Vuelve al menú de finanzas
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    query.edit_message_text(text="➕ Selecciona el tipo de ingreso mensual:", reply_markup=reply_markup)
    return STATE_FIN_SUBMENU_ACTION

def cb_fin_reg_expense_menu(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    query.answer()
    keyboard = [
        [InlineKeyboardButton("🧾 Gasto Fijo Diario", callback_data=config.CB_FIN_REG_FIXED_EXPENSE_START)],
        [InlineKeyboardButton("🛍️ Gasto Variable Diario", callback_data=config.CB_FIN_REG_VAR_EXPENSE_START)],
        [common_handlers.get_back_button(config.CB_FIN_MAIN_MENU, "⬅️ Volver a Finanzas")] # Vuelve al menú de finanzas
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    query.edit_message_text(text="➖ Selecciona el tipo de gasto diario:", reply_markup=reply_markup)
    return STATE_FIN_SUBMENU_ACTION


# --- INICIO DE REGISTRO DE TRANSACCIÓN (Petición de Monto) ---
def start_transaction_amount_input(update: Update, context: CallbackContext, transaction_type: str) -> int:
    query = update.callback_query
    if query: query.answer()
    
    context.user_data[UD_FIN_CURRENT_TRANSACTION_TYPE] = transaction_type
    
    prompt_map = {
        'income_fixed': "💵 Ingreso Fijo Mensual:\nEnvía el monto total.",
        'income_variable': "📈 Ingreso Extra/Variable Mensual:\nEnvía el monto.",
        'expense_fixed': "🧾 Gasto Fijo Diario:\nEnvía el monto del gasto.",
        'expense_variable': "🛍️ Gasto Variable Diario:\nEnvía el monto del gasto.",
        'savings': "🏦 Ahorro Mensual:\nEnvía el monto a ahorrar este mes."
    }
    prompt_text = prompt_map.get(transaction_type, "Envía el monto:") + "\n\nEscribe /cancelfinance para salir."
    
    if query and query.message: query.edit_message_text(text=prompt_text)
    else: context.bot.send_message(chat_id=update.effective_chat.id, text=prompt_text)
    return STATE_FIN_GET_AMOUNT_INPUT

# Callbacks que inician la petición de monto
def cb_fin_reg_fixed_income_start(update: Update, context: CallbackContext) -> int:
    return start_transaction_amount_input(update, context, 'income_fixed')
def cb_fin_reg_var_income_start(update: Update, context: CallbackContext) -> int:
    return start_transaction_amount_input(update, context, 'income_variable')
def cb_fin_reg_fixed_expense_start(update: Update, context: CallbackContext) -> int:
    return start_transaction_amount_input(update, context, 'expense_fixed')
def cb_fin_reg_var_expense_start(update: Update, context: CallbackContext) -> int:
    return start_transaction_amount_input(update, context, 'expense_variable')
def cb_fin_reg_savings_action(update: Update, context: CallbackContext) -> int: # Directo desde menú de finanzas
    return start_transaction_amount_input(update, context, 'savings')


# --- OBTENER Y GUARDAR MONTO DE LA TRANSACCIÓN ---
def get_transaction_amount_input(update: Update, context: CallbackContext) -> int:
    user_text = update.message.text
    transaction_type = context.user_data.get(UD_FIN_CURRENT_TRANSACTION_TYPE)
    user_id = update.effective_user.id

    try:
        amount = float(user_text)
        if amount <= 0:
            update.message.reply_text("⚠️ El monto debe ser positivo. Intenta de nuevo o /cancelfinance.")
            return STATE_FIN_GET_AMOUNT_INPUT
        
        transaction_date_obj = datetime.now(db_utils.LIMA_TZ).date()
        db_utils.save_finance_transaction(
            user_id=user_id, trans_type=transaction_type,
            amount=amount, date_obj=transaction_date_obj
        )
        
        type_map = {'income_fixed': "Ingreso fijo", 'income_variable': "Ingreso variable",
                    'expense_fixed': "Gasto fijo", 'expense_variable': "Gasto variable", 'savings': "Ahorro"}
        update.message.reply_text(f"✅ {type_map.get(transaction_type, 'Monto').capitalize()} de S/. {amount:.2f} guardado.")
        
        # Limpiar user_data y volver al menú de finanzas
        for key in UD_FIN_CLEANUP_KEYS_ADD_FLOW:
            if key in context.user_data: del context.user_data[key]
        finance_menu(update, context) # Mostrar menú de finanzas como nuevo mensaje
        return ConversationHandler.END

    except ValueError:
        update.message.reply_text(config.MSG_REQUIRE_NUMBER + " Intenta de nuevo o /cancelfinance.")
        return STATE_FIN_GET_AMOUNT_INPUT


# --- VER RESUMEN FINANCIERO ---
def cb_fin_view_summary(update: Update, context: CallbackContext) -> int: # Renombrado con _cb
    query = update.callback_query
    user_id = query.from_user.id
    query.answer()

    now_lima = datetime.now(db_utils.LIMA_TZ)
    current_month_str = now_lima.strftime("%Y-%m")
    current_day_obj = now_lima.date()

    inc_fixed = sum(float(t['amount']) for t in db_utils.get_finance_transactions(user_id, month_str=current_month_str, trans_type='income_fixed'))
    inc_var = sum(float(t['amount']) for t in db_utils.get_finance_transactions(user_id, month_str=current_month_str, trans_type='income_variable'))
    total_income_month = inc_fixed + inc_var
    total_savings_month = sum(float(t['amount']) for t in db_utils.get_finance_transactions(user_id, month_str=current_month_str, trans_type='savings'))
    
    all_month_expenses_dr = db_utils.get_finance_transactions(user_id, month_str=current_month_str, trans_type='expense_fixed') + \
                            db_utils.get_finance_transactions(user_id, month_str=current_month_str, trans_type='expense_variable')
    total_expenses_month_to_date = sum(float(dict(t)['amount']) for t in all_month_expenses_dr if dict(t)['transaction_date'] <= current_day_obj)
            
    exp_today_fixed = sum(float(t['amount']) for t in db_utils.get_finance_transactions(user_id, day_obj=current_day_obj, trans_type='expense_fixed'))
    exp_today_var = sum(float(t['amount']) for t in db_utils.get_finance_transactions(user_id, day_obj=current_day_obj, trans_type='expense_variable'))
    total_expenses_today = exp_today_fixed + exp_today_var
    balance_month = (total_income_month - total_savings_month) - total_expenses_month_to_date

    summary = f"📊 *Resumen Financiero ({now_lima.strftime('%B %Y')})*\n\n"
    summary += f"💵 *Ingresos Mes:*\n  Fijos: S/. {inc_fixed:.2f}\n  Variables: S/. {inc_var:.2f}\n  ▪️ *Total:* S/. {total_income_month:.2f}\n\n"
    summary += f"🏦 *Ahorros Mes:*\n  ▪️ *Total:* S/. {total_savings_month:.2f}\n\n"
    summary += f"🧾 *Gastos:*\n  Hoy: S/. {total_expenses_today:.2f}\n  ▪️ *Mes (hasta hoy):* S/. {total_expenses_month_to_date:.2f}\n\n"
    summary += f"💰 *Saldo Estimado Mes:*\n  ▪️ *Saldo:* S/. {balance_month:.2f}\n\n"
    summary += "_Recuerda registrar gastos diarios._"

    keyboard = [[common_handlers.get_back_button(config.CB_FIN_MAIN_MENU, "⬅️ Volver a Finanzas")]]
    query.edit_message_text(text=summary, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    return STATE_FIN_MENU_ACTION # Volver al estado del menú de finanzas


# --- CANCELACIÓN ---
def cancel_finance_flow_command(update: Update, context: CallbackContext) -> int:
    return common_handlers.cancel_conversation_to_main_menu(update, context, UD_FIN_CLEANUP_KEYS_ADD_FLOW)


# --- REGISTRO DE HANDLERS ---
def register_handlers(dp) -> None:
    # ConversationHandler principal para toda la sección de finanzas
    finance_section_conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(finance_menu, pattern=f"^{config.CB_FIN_MAIN_MENU}$")],
        states={
            STATE_FIN_MENU_ACTION: [ # En el menú de finanzas, esperando acción
                CallbackQueryHandler(cb_fin_reg_income_menu, pattern=f"^{config.CB_FIN_REG_INCOME_MENU}$"),
                CallbackQueryHandler(cb_fin_reg_expense_menu, pattern=f"^{config.CB_FIN_REG_EXPENSE_MENU}$"),
                CallbackQueryHandler(cb_fin_reg_savings_action, pattern=f"^{config.CB_FIN_REG_SAVINGS_ACTION}$"), # Inicia sub-flujo
                CallbackQueryHandler(cb_fin_view_summary, pattern=f"^{config.CB_FIN_VIEW_SUMMARY}$"),
            ],
            STATE_FIN_SUBMENU_ACTION: [ # En submenú de ingresos o gastos, esperando tipo
                CallbackQueryHandler(cb_fin_reg_fixed_income_start, pattern=f"^{config.CB_FIN_REG_FIXED_INCOME_START}$"),
                CallbackQueryHandler(cb_fin_reg_var_income_start, pattern=f"^{config.CB_FIN_REG_VAR_INCOME_START}$"),
                CallbackQueryHandler(cb_fin_reg_fixed_expense_start, pattern=f"^{config.CB_FIN_REG_FIXED_EXPENSE_START}$"),
                CallbackQueryHandler(cb_fin_reg_var_expense_start, pattern=f"^{config.CB_FIN_REG_VAR_EXPENSE_START}$"),
                CallbackQueryHandler(finance_menu, pattern=f"^{config.CB_FIN_MAIN_MENU}$"), # Botón "Volver a Finanzas"
            ],
            STATE_FIN_GET_AMOUNT_INPUT: [ # Esperando el monto
                MessageHandler(Filters.text & ~Filters.command, get_transaction_amount_input),
            ],
        },
        fallbacks=[
            CommandHandler("cancelfinance", cancel_finance_flow_command),
            CallbackQueryHandler(common_handlers.cancel_conversation_to_main_menu, pattern=f"^{config.CB_MAIN_MENU}$") # Botón de volver al menú principal del bot
            ],
        allow_reentry=True # Permite reingresar a los estados, ej. al menú de finanzas
    )
    dp.add_handler(finance_section_conv_handler)