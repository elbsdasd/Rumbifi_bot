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

logger = logging.getLogger(__name__)

# Estados de la conversación para Finanzas
(
    STATE_FIN_ACTION_SELECT,    # Menú principal de finanzas
    STATE_FIN_GET_AMOUNT,       # Esperando monto numérico
    # STATE_FIN_GET_DESCRIPTION # No lo usaremos por ahora para simplificar
) = range(20, 22) # Rango diferente

# Claves para context.user_data
UD_FIN_CURRENT_TRANS_TYPE = 'fin_current_trans_type' 
UD_FIN_TEMP_AMOUNT = 'fin_temp_amount' # No se usa si guardamos directo
UD_FIN_CLEANUP_KEYS = [UD_FIN_CURRENT_TRANS_TYPE, UD_FIN_TEMP_AMOUNT]


# --- MENÚ PRINCIPAL DE FINANZAS ---
def finance_menu(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    user_id = query.from_user.id if query else update.effective_user.id

    has_access, access_message = db_utils.check_user_access(user_id)
    if not has_access:
        if query:
            query.answer()
            query.edit_message_text(text=access_message)
        else:
            context.bot.send_message(chat_id=user_id, text=access_message)
        return ConversationHandler.END

    keyboard = [
        [InlineKeyboardButton("➕ Registrar Ingresos Mensuales", callback_data=config.CB_FIN_REG_INCOME)],
        [InlineKeyboardButton("➖ Registrar Gastos Diarios", callback_data=config.CB_FIN_REG_EXPENSE)],
        [InlineKeyboardButton("🏦 Registrar Ahorros Mensuales", callback_data=config.CB_FIN_REG_SAVINGS)],
        [InlineKeyboardButton("📊 Ver Resumen Financiero", callback_data=config.CB_FIN_VIEW_SUMMARY)],
        [common_handlers.get_main_menu_button()]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    message_text = "💰 *Mis Finanzas*\n\nGestiona tus ingresos, gastos y ahorros. Elige una opción:"
    
    if query:
        query.answer()
        query.edit_message_text(text=message_text, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        context.bot.send_message(chat_id=user_id, text=message_text, reply_markup=reply_markup, parse_mode='Markdown')
        
    return STATE_FIN_ACTION_SELECT


# --- SUB-MENÚS PARA INGRESOS Y GASTOS ---
def finance_reg_income_menu_cb(update: Update, context: CallbackContext) -> int: # Renombrado con _cb
    query = update.callback_query
    query.answer()
    keyboard = [
        [InlineKeyboardButton("💵 Ingreso Fijo Mensual", callback_data=config.CB_FIN_REG_FIXED_INCOME)],
        [InlineKeyboardButton("📈 Ingreso Extra/Variable Mensual", callback_data=config.CB_FIN_REG_VAR_INCOME)],
        [common_handlers.get_back_button(config.CB_FIN_MAIN_MENU, "⬅️ Volver a Finanzas")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    query.edit_message_text(text="➕ Selecciona el tipo de ingreso mensual a registrar:", reply_markup=reply_markup)
    return STATE_FIN_ACTION_SELECT 

def finance_reg_expense_menu_cb(update: Update, context: CallbackContext) -> int: # Renombrado con _cb
    query = update.callback_query
    query.answer()
    keyboard = [
        [InlineKeyboardButton("🧾 Gasto Fijo Diario", callback_data=config.CB_FIN_REG_FIXED_EXPENSE)],
        [InlineKeyboardButton("🛍️ Gasto Variable Diario", callback_data=config.CB_FIN_REG_VAR_EXPENSE)],
        [common_handlers.get_back_button(config.CB_FIN_MAIN_MENU, "⬅️ Volver a Finanzas")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    query.edit_message_text(text="➖ Selecciona el tipo de gasto diario a registrar:", reply_markup=reply_markup)
    return STATE_FIN_ACTION_SELECT


# --- INICIO DE REGISTRO DE TRANSACCIÓN (DESPUÉS DE SELECCIONAR TIPO) ---
def start_transaction_registration(update: Update, context: CallbackContext, transaction_type: str) -> int:
    query = update.callback_query
    if query: query.answer()
    
    context.user_data[UD_FIN_CURRENT_TRANS_TYPE] = transaction_type
    
    type_map_prompt = {
        'income_fixed': "💵 Ingreso Fijo Mensual: \nPor favor, envía el monto total.",
        'income_variable': "📈 Ingreso Extra/Variable Mensual: \nEnvía el monto.",
        'expense_fixed': "🧾 Gasto Fijo Diario: \nEnvía el monto del gasto.",
        'expense_variable': "🛍️ Gasto Variable Diario: \nEnvía el monto del gasto.",
        'savings': "🏦 Ahorro Mensual: \nEnvía el monto que deseas ahorrar este mes."
    }
    prompt_text = type_map_prompt.get(transaction_type, "Por favor, envía el monto:")
    prompt_text += "\n\nEscribe /cancelfinance para salir."
    
    # Si se llamó desde un botón (query existe), editar mensaje. Sino, enviar nuevo.
    if query and query.message:
        query.edit_message_text(text=prompt_text)
    else:
        context.bot.send_message(chat_id=update.effective_chat.id, text=prompt_text)
        
    return STATE_FIN_GET_AMOUNT

# Callbacks para cada tipo de transacción
def fin_reg_fixed_income_cb(update: Update, context: CallbackContext) -> int:
    return start_transaction_registration(update, context, 'income_fixed')
def fin_reg_var_income_cb(update: Update, context: CallbackContext) -> int:
    return start_transaction_registration(update, context, 'income_variable')
def fin_reg_fixed_expense_cb(update: Update, context: CallbackContext) -> int:
    return start_transaction_registration(update, context, 'expense_fixed')
def fin_reg_var_expense_cb(update: Update, context: CallbackContext) -> int:
    return start_transaction_registration(update, context, 'expense_variable')
def fin_reg_savings_cb(update: Update, context: CallbackContext) -> int: # Llamado directamente desde el menú de finanzas
    return start_transaction_registration(update, context, 'savings')


# --- OBTENER MONTO DE LA TRANSACCIÓN ---
def get_transaction_amount(update: Update, context: CallbackContext) -> int:
    user_text = update.message.text
    transaction_type = context.user_data.get(UD_FIN_CURRENT_TRANS_TYPE)
    user_id = update.effective_user.id

    try:
        amount = float(user_text)
        if amount <= 0: # Los montos deben ser positivos
            update.message.reply_text("⚠️ El monto debe ser un valor positivo. Por favor, intenta de nuevo.")
            return STATE_FIN_GET_AMOUNT
        
        # Determinar la fecha de la transacción
        # Ingresos y Ahorros son mensuales, pero se registran en una fecha. Usamos hoy.
        # Gastos son diarios.
        transaction_date_obj = datetime.now(db_utils.LIMA_TZ).date()
        
        db_utils.save_finance_transaction(
            user_id=user_id,
            trans_type=transaction_type,
            amount=amount,
            date_obj=transaction_date_obj # Pasamos el objeto date
        )
        
        type_map_feedback = {
            'income_fixed': "Ingreso fijo mensual", 'income_variable': "Ingreso extra/variable mensual",
            'expense_fixed': "Gasto fijo diario", 'expense_variable': "Gasto variable diario",
            'savings': "Ahorro mensual"
        }
        friendly_type = type_map_feedback.get(transaction_type, "Monto")
        update.message.reply_text(f"✅ {friendly_type} de S/. {amount:.2f} guardado exitosamente.")

        return common_handlers.cancel_conversation_to_main_menu(update, context, UD_FIN_CLEANUP_KEYS)

    except ValueError:
        update.message.reply_text(config.MSG_REQUIRE_NUMBER + " Intenta de nuevo o escribe /cancelfinance.")
        return STATE_FIN_GET_AMOUNT


# --- VER RESUMEN FINANCIERO ---
def view_finance_summary_cb(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    user_id = query.from_user.id
    query.answer()

    now_lima = datetime.now(db_utils.LIMA_TZ)
    current_month_str = now_lima.strftime("%Y-%m")
    current_day_obj = now_lima.date() # Objeto date

    # Obtener Ingresos Mensuales
    inc_fixed = sum(t['amount'] for t in db_utils.get_finance_transactions(user_id, month_str=current_month_str, trans_type='income_fixed'))
    inc_var = sum(t['amount'] for t in db_utils.get_finance_transactions(user_id, month_str=current_month_str, trans_type='income_variable'))
    total_income_month = inc_fixed + inc_var

    total_savings_month = sum(t['amount'] for t in db_utils.get_finance_transactions(user_id, month_str=current_month_str, trans_type='savings'))

    # Gastos Mensuales (acumulados hasta hoy en el mes actual)
    all_month_expenses = db_utils.get_finance_transactions(user_id, month_str=current_month_str, trans_type='expense_fixed') + \
                         db_utils.get_finance_transactions(user_id, month_str=current_month_str, trans_type='expense_variable')
    
    total_expenses_month_to_date = 0
    for t_dictrow in all_month_expenses:
        t = dict(t_dictrow) # Convertir DictRow a dict
        # transaction_date en la BD es un objeto date
        if t['transaction_date'] <= current_day_obj: # Comparar objetos date
            total_expenses_month_to_date += t['amount']
            
    # Gastos del Día de Hoy
    exp_today_fixed = sum(t['amount'] for t in db_utils.get_finance_transactions(user_id, day_obj=current_day_obj, trans_type='expense_fixed'))
    exp_today_var = sum(t['amount'] for t in db_utils.get_finance_transactions(user_id, day_obj=current_day_obj, trans_type='expense_variable'))
    total_expenses_today = exp_today_fixed + exp_today_var

    balance_month = (total_income_month - total_savings_month) - total_expenses_month_to_date

    summary_text = f"📊 *Resumen Financiero para {now_lima.strftime('%B %Y')}*\n\n"
    summary_text += f"💵 *Ingresos del Mes:*\n"
    summary_text += f"  ▫️ Fijos: S/. {inc_fixed:.2f}\n"
    summary_text += f"  ▫️ Variables: S/. {inc_var:.2f}\n"
    summary_text += f"  ▪️ *Total:* S/. {total_income_month:.2f}\n\n"
    summary_text += f"🏦 *Ahorros del Mes:*\n  ▪️ *Total:* S/. {total_savings_month:.2f}\n\n"
    summary_text += f"🧾 *Gastos:*\n"
    summary_text += f"  ▫️ Hoy: S/. {total_expenses_today:.2f}\n"
    summary_text += f"  ▪️ *Mes (hasta hoy):* S/. {total_expenses_month_to_date:.2f}\n\n"
    summary_text += f"💰 *Saldo Estimado del Mes:*\n  ▪️ *Saldo:* S/. {balance_month:.2f}\n\n"
    summary_text += "_Registra gastos diarios para mantener el resumen actualizado._"

    keyboard = [[common_handlers.get_back_button(config.CB_FIN_MAIN_MENU, "⬅️ Volver a Finanzas")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    query.edit_message_text(text=summary_text, reply_markup=reply_markup, parse_mode='Markdown')
    return STATE_FIN_ACTION_SELECT


# --- CANCELACIÓN ---
def cancel_finance_flow_command(update: Update, context: CallbackContext) -> int:
    return common_handlers.cancel_conversation_to_main_menu(update, context, UD_FIN_CLEANUP_KEYS)


# --- CONVERSATION HANDLER ---
def get_finance_conversation_handler() -> ConversationHandler:
    conv_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(fin_reg_fixed_income_cb, pattern=f"^{config.CB_FIN_REG_FIXED_INCOME}$"),
            CallbackQueryHandler(fin_reg_var_income_cb, pattern=f"^{config.CB_FIN_REG_VAR_INCOME}$"),
            CallbackQueryHandler(fin_reg_fixed_expense_cb, pattern=f"^{config.CB_FIN_REG_FIXED_EXPENSE}$"),
            CallbackQueryHandler(fin_reg_var_expense_cb, pattern=f"^{config.CB_FIN_REG_VAR_EXPENSE}$"),
            CallbackQueryHandler(fin_reg_savings_cb, pattern=f"^{config.CB_FIN_REG_SAVINGS}$"),
        ],
        states={
            STATE_FIN_GET_AMOUNT: [MessageHandler(Filters.text & ~Filters.command, get_transaction_amount)],
        },
        fallbacks=[ CommandHandler("cancelfinance", cancel_finance_flow_command) ],
        map_to_parent={ConversationHandler.END: STATE_FIN_ACTION_SELECT} # Volver al menú de finanzas
    )
    return conv_handler

def register_handlers(dp) -> None:
    # Handler para el flujo de añadir transacciones
    dp.add_handler(get_finance_conversation_handler())
    
    # Callbacks para los sub-menús de ingresos/gastos y para ver resumen
    # Estos ahora son los entry_points del ConversationHandler principal de finanzas
    # O pueden ser parte de un ConversationHandler más grande que englobe toda la sección.
    # La estructura actual es:
    # 1. CB_FIN_MAIN_MENU (en main.py) -> finance_menu (estado STATE_FIN_ACTION_SELECT)
    # 2. Desde finance_menu (botones):
    #    - CB_FIN_REG_INCOME -> finance_reg_income_menu_cb (sigue en STATE_FIN_ACTION_SELECT)
    #    - CB_FIN_REG_EXPENSE -> finance_reg_expense_menu_cb (sigue en STATE_FIN_ACTION_SELECT)
    #    - CB_FIN_REG_SAVINGS -> fin_reg_savings_cb (entry_point a ConversationHandler para pedir monto)
    #    - CB_FIN_VIEW_SUMMARY -> view_finance_summary_cb (sigue en STATE_FIN_ACTION_SELECT)
    # 3. Desde sub-menús de ingreso/gasto:
    #    - CB_FIN_REG_FIXED_INCOME, etc. -> son entry_points al ConversationHandler para pedir monto.

    # Es más simple si finance_menu es el entry point a un ConvHandler que maneja todos los estados.
    main_finance_conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(finance_menu, pattern=f"^{config.CB_FIN_MAIN_MENU}$")],
        states={
            STATE_FIN_ACTION_SELECT: [ # Estado del menú de finanzas, esperando selección
                CallbackQueryHandler(finance_reg_income_menu_cb, pattern=f"^{config.CB_FIN_REG_INCOME}$"),
                CallbackQueryHandler(finance_reg_expense_menu_cb, pattern=f"^{config.CB_FIN_REG_EXPENSE}$"),
                # Los siguientes inician el sub-flujo de pedir monto
                get_finance_conversation_handler(), # Anidar el handler de pedir monto
                CallbackQueryHandler(view_finance_summary_cb, pattern=f"^{config.CB_FIN_VIEW_SUMMARY}$"),
            ],
            # El estado de pedir monto (STATE_FIN_GET_AMOUNT) está dentro del handler anidado.
        },
        fallbacks=[
             CallbackQueryHandler(finance_menu, pattern=f"^{config.CB_FIN_MAIN_MENU}$"), # Para el botón "Volver a Finanzas"
             CommandHandler("cancel", lambda u,c: common_handlers.cancel_conversation_to_main_menu(u,c,UD_FIN_CLEANUP_KEYS))
        ],
        # allow_reentry=True
    )
    dp.add_handler(main_finance_conv_handler)