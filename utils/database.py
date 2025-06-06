# utils/database.py

import psycopg2
import psycopg2.extras 
import config # Para DATABASE_URL
from datetime import datetime, timedelta, date, time as time_obj
import pytz # Para manejo de zonas horarias
import logging

logger = logging.getLogger(__name__)

# Definir LIMA_TZ aquí para que esté disponible en todo el módulo
LIMA_TZ = pytz.timezone('America/Lima')

# --- MANEJO DE CONEXIÓN ---
def get_db_connection():
    """Establece y devuelve una conexión a la base de datos PostgreSQL."""
    try:
        conn = psycopg2.connect(config.DATABASE_URL)
        return conn
    except psycopg2.Error as e:
        logger.error(f"Error al conectar a PostgreSQL: {e}")
        raise 

# --- INICIALIZACIÓN DE LA BASE DE DATOS ---
def initialize_database():
    """Crea las tablas necesarias si no existen."""
    commands = (
        """
        CREATE TABLE IF NOT EXISTS rumbify_users (
            user_id BIGINT PRIMARY KEY,
            trial_start_date TIMESTAMPTZ,
            trial_active BOOLEAN DEFAULT TRUE,
            has_permanent_access BOOLEAN DEFAULT FALSE,
            last_seen TIMESTAMPTZ
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS planning_items (
            item_id SERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            item_date DATE NOT NULL,
            item_type VARCHAR(20) NOT NULL, 
            text TEXT NOT NULL,
            reminder_time TIME, 
            completed BOOLEAN, 
            marked_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
            notification_sent BOOLEAN DEFAULT FALSE
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS wellbeing_docs (
            doc_id SERIAL PRIMARY KEY, 
            user_id BIGINT NOT NULL,
            item_date DATE NOT NULL,
            item_type VARCHAR(20) NOT NULL, 
            created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ,
            UNIQUE(user_id, item_date, item_type)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS wellbeing_sub_items (
            sub_item_id SERIAL PRIMARY KEY,
            doc_id INTEGER REFERENCES wellbeing_docs(doc_id) ON DELETE CASCADE,
            text TEXT NOT NULL,
            completed BOOLEAN DEFAULT FALSE,
            marked_at TIMESTAMPTZ
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS finance_transactions (
            transaction_id SERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            transaction_type VARCHAR(30) NOT NULL, 
            amount NUMERIC(12, 2) NOT NULL,
            description TEXT,
            transaction_date DATE NOT NULL, 
            transaction_month VARCHAR(7) NOT NULL, 
            created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        for command in commands:
            cur.execute(command)
        cur.close()
        conn.commit()
    except psycopg2.Error as e:
        logger.error(f"Error creando tablas: {e}")
        if conn: conn.rollback()
        raise 
    finally:
        if conn: conn.close()

# --- FUNCIONES DE USUARIO ---
def get_user_data(user_id: int):
    # (Código idéntico a la última versión estable para Render)
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute("SELECT * FROM rumbify_users WHERE user_id = %s", (user_id,))
    user_data = cur.fetchone()
    cur.close(); conn.close()
    return user_data

def create_or_update_user(user_id: int, data: dict):
    # (Código idéntico a la última versión estable para Render)
    conn = get_db_connection()
    cur = conn.cursor()
    sql = """
        INSERT INTO rumbify_users (user_id, trial_start_date, trial_active, has_permanent_access, last_seen)
        VALUES (%(user_id)s, %(trial_start_date)s, %(trial_active)s, %(has_permanent_access)s, %(last_seen)s)
        ON CONFLICT (user_id) DO UPDATE SET
            trial_start_date = EXCLUDED.trial_start_date, trial_active = EXCLUDED.trial_active,
            has_permanent_access = EXCLUDED.has_permanent_access, last_seen = EXCLUDED.last_seen;
    """
    params = {'user_id': user_id, 'trial_start_date': data.get('trial_start_date'),
              'trial_active': data.get('trial_active', True), 
              'has_permanent_access': data.get('has_permanent_access', False),
              'last_seen': data.get('last_seen')}
    try:
        cur.execute(sql, params); conn.commit()
    except psycopg2.Error as e: logger.error(f"Error en C_O_U_user para {user_id}: {e}"); conn.rollback()
    finally: cur.close(); conn.close()

def add_permanent_access(user_id: int):
    # (Lógica idéntica)
    user_data = get_user_data(user_id)
    now_lima_iso = datetime.now(LIMA_TZ).isoformat()
    data_to_save = {"trial_start_date": user_data['trial_start_date'] if user_data else None,
                    "trial_active": False, "has_permanent_access": True, "last_seen": now_lima_iso}
    create_or_update_user(user_id, data_to_save)
    return True

def remove_permanent_access(user_id: int):
    # (Lógica idéntica)
    user_data = get_user_data(user_id)
    if user_data:
        update_data = dict(user_data); update_data["has_permanent_access"] = False
        update_data["last_seen"] = datetime.now(LIMA_TZ).isoformat()
        create_or_update_user(user_id, update_data)
        return True
    return False

def check_user_access(user_id: int) -> tuple[bool, str]:
    # (Lógica idéntica, manejo de timestamps con zona horaria)
    user_data = get_user_data(user_id)
    current_time_lima = datetime.now(LIMA_TZ)

    if not user_data:
        trial_start_iso = current_time_lima.isoformat()
        new_user_data = {"trial_start_date": trial_start_iso, "trial_active": True,
                         "has_permanent_access": False, "last_seen": trial_start_iso}
        create_or_update_user(user_id, new_user_data)
        return True, "Trial started"

    update_last_seen_data = dict(user_data) # Crear una copia para modificar
    update_last_seen_data["last_seen"] = current_time_lima.isoformat()
    create_or_update_user(user_id, update_last_seen_data)
    
    if user_data.get("has_permanent_access"): return True, "Permanent access"
    if user_data.get("trial_active") and user_data.get("trial_start_date"):
        trial_start_date_db = user_data["trial_start_date"] # Es TIMESTAMPTZ de PG, Python lo lee como datetime con tz
        # trial_start_date_lima = trial_start_date_db.astimezone(LIMA_TZ) # No es necesario si ya está en UTC y current_time_lima también tiene TZ
        if current_time_lima < trial_start_date_db + timedelta(days=3): # Comparación directa de datetimes con zona horaria
            return True, "Trial active"
        else:
            expired_data = dict(user_data); expired_data["trial_active"] = False
            create_or_update_user(user_id, expired_data)
            return False, config.MSG_CONTACT_FOR_FULL_ACCESS
    return False, config.MSG_CONTACT_FOR_FULL_ACCESS

# --- FUNCIONES DE PLANIFICACIÓN (Prácticamente idénticas a la última versión de Render) ---
def save_planning_item(user_id: int, item_type: str, text: str, reminder_time: str = None):
    # (Lógica idéntica)
    conn = get_db_connection(); cur = conn.cursor(); today_date = datetime.now(LIMA_TZ).date()
    rt_obj = None
    if reminder_time:
        try: rt_obj = datetime.strptime(reminder_time, "%H:%M").time()
        except ValueError: logger.warning(f"Formato reminder_time inválido '{reminder_time}'")
    sql = "INSERT INTO planning_items (user_id, item_date, item_type, text, reminder_time, completed, notification_sent) VALUES (%s, %s, %s, %s, %s, NULL, %s) RETURNING item_id;"
    try:
        cur.execute(sql, (user_id, today_date, item_type, text, rt_obj, False if rt_obj else None)); item_id = cur.fetchone()[0]; conn.commit(); return item_id
    except psycopg2.Error as e: logger.error(f"Error save_planning_item: {e}"); conn.rollback(); return None
    finally: cur.close(); conn.close()

def get_daily_planning_items(user_id: int, date_obj: date): # Espera objeto date
    # (Lógica idéntica)
    conn = get_db_connection(); cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    sql = "SELECT item_id AS key, item_type AS type, text, reminder_time, completed, marked_at FROM planning_items WHERE user_id = %s AND item_date = %s ORDER BY created_at"
    cur.execute(sql, (user_id, date_obj)); items = cur.fetchall(); cur.close(); conn.close(); return items

def update_planning_item_status(item_id: int, completed_status: bool): # Renombrado completed_status
    # (Lógica idéntica)
    conn = get_db_connection(); cur = conn.cursor()
    sql = "UPDATE planning_items SET completed = %s, marked_at = %s WHERE item_id = %s"
    try: cur.execute(sql, (completed_status, datetime.now(LIMA_TZ), item_id)); conn.commit()
    except psycopg2.Error as e: logger.error(f"Error update_planning_item_status ({item_id}): {e}"); conn.rollback()
    finally: cur.close(); conn.close()

def get_pending_reminders():
    # (Lógica idéntica)
    conn = get_db_connection(); cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    today_date = datetime.now(LIMA_TZ).date()
    sql = "SELECT item_id AS key, user_id, text, reminder_time FROM planning_items WHERE item_date = %s AND reminder_time IS NOT NULL AND notification_sent = FALSE"
    cur.execute(sql, (today_date,)); items = cur.fetchall(); cur.close(); conn.close(); return items

def mark_reminder_sent(item_id: int):
    # (Lógica idéntica)
    conn = get_db_connection(); cur = conn.cursor()
    sql = "UPDATE planning_items SET notification_sent = TRUE WHERE item_id = %s"
    try: cur.execute(sql, (item_id,)); conn.commit()
    except psycopg2.Error as e: logger.error(f"Error mark_reminder_sent ({item_id}): {e}"); conn.rollback()
    finally: cur.close(); conn.close()

def cleanup_old_unmarked_tasks():
    # (Lógica idéntica)
    conn = get_db_connection(); cur = conn.cursor()
    cutoff = datetime.now(LIMA_TZ) - timedelta(days=1)
    sql = "DELETE FROM planning_items WHERE completed IS NULL AND created_at < %s"
    try:
        cur.execute(sql, (cutoff,)); deleted = cur.rowcount; conn.commit()
        if deleted > 0: logger.info(f"Limpieza: {deleted} tareas planeadas antiguas no marcadas eliminadas.")
    except psycopg2.Error as e: logger.error(f"Error cleanup_old_unmarked_tasks: {e}"); conn.rollback()
    finally: cur.close(); conn.close()

# --- FUNCIONES DE BIENESTAR (Prácticamente idénticas) ---
def save_wellbeing_items_list(user_id: int, item_type: str, data_list: list, date_obj: date = None):
    # (Lógica idéntica)
    if date_obj is None: date_obj = datetime.now(LIMA_TZ).date()
    conn = get_db_connection(); cur = conn.cursor(); doc_id = None
    try:
        cur.execute("INSERT INTO wellbeing_docs (user_id, item_date, item_type, updated_at) VALUES (%s, %s, %s, %s) ON CONFLICT (user_id, item_date, item_type) DO UPDATE SET updated_at = EXCLUDED.updated_at RETURNING doc_id", (user_id, date_obj, item_type, datetime.now(LIMA_TZ))); doc_id = cur.fetchone()[0]
        cur.execute("DELETE FROM wellbeing_sub_items WHERE doc_id = %s", (doc_id,))
        if doc_id and data_list:
            sub_items_sql = "INSERT INTO wellbeing_sub_items (doc_id, text) VALUES (%s, %s)"
            cur.executemany(sub_items_sql, [(doc_id, text) for text in data_list])
        conn.commit(); return doc_id
    except psycopg2.Error as e: logger.error(f"Error save_wellbeing_items_list (type: {item_type}): {e}"); if conn: conn.rollback(); return None
    finally:
        if conn: cur.close(); conn.close()

def get_daily_wellbeing_doc_and_sub_items(user_id: int, item_type: str, date_obj: date = None):
    # (Lógica idéntica, 'key' para sub_items es sub_item_id)
    if date_obj is None: date_obj = datetime.now(LIMA_TZ).date()
    conn = get_db_connection(); cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor); doc_id = None
    try:
        cur.execute("SELECT doc_id FROM wellbeing_docs WHERE user_id = %s AND item_date = %s AND item_type = %s", (user_id, date_obj, item_type)); doc_row = cur.fetchone()
        if not doc_row: return None
        doc_id = doc_row['doc_id']
        cur.execute("SELECT sub_item_id AS key, text, completed, marked_at FROM wellbeing_sub_items WHERE doc_id = %s ORDER BY sub_item_id", (doc_id,)); sub_items = cur.fetchall()
        return {"key": doc_id, "items": sub_items, "type": item_type, "date": date_obj}
    except psycopg2.Error as e: logger.error(f"Error get_daily_wellbeing_doc_and_sub_items: {e}"); return None
    finally:
        if conn: cur.close(); conn.close()

def update_wellbeing_sub_item_status(sub_item_id: int, completed_status: bool): # Renombrado completed_status
    # (Lógica idéntica)
    conn = get_db_connection(); cur = conn.cursor()
    sql = "UPDATE wellbeing_sub_items SET completed = %s, marked_at = %s WHERE sub_item_id = %s"
    try: cur.execute(sql, (completed_status, datetime.now(LIMA_TZ), sub_item_id)); conn.commit()
    except psycopg2.Error as e: logger.error(f"Error update_wellbeing_sub_item_status ({sub_item_id}): {e}"); conn.rollback()
    finally:
        if conn: cur.close(); conn.close()

# --- FUNCIONES DE FINANZAS (Prácticamente idénticas) ---
def save_finance_transaction(user_id: int, trans_type: str, amount: float, description: str = None, date_obj: date = None):
    # (Lógica idéntica)
    if date_obj is None: date_obj = datetime.now(LIMA_TZ).date()
    month_str = date_obj.strftime("%Y-%m"); conn = get_db_connection(); cur = conn.cursor()
    sql = "INSERT INTO finance_transactions (user_id, transaction_type, amount, description, transaction_date, transaction_month) VALUES (%s, %s, %s, %s, %s, %s) RETURNING transaction_id;"
    try:
        cur.execute(sql, (user_id, trans_type, amount, description, date_obj, month_str)); trans_id = cur.fetchone()[0]; conn.commit(); return trans_id
    except psycopg2.Error as e: logger.error(f"Error save_finance_transaction: {e}"); conn.rollback(); return None
    finally:
        if conn: cur.close(); conn.close()

def get_finance_transactions(user_id: int, month_str: str = None, day_obj: date = None, trans_type: str = None):
    # (Lógica idéntica)
    conn = get_db_connection(); cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    conditions = ["user_id = %(user_id)s"]; params = {'user_id': user_id}
    if month_str: conditions.append("transaction_month = %(month_str)s"); params['month_str'] = month_str
    if day_obj: conditions.append("transaction_date = %(day_obj)s"); params['day_obj'] = day_obj
    if trans_type: conditions.append("transaction_type = %(trans_type)s"); params['trans_type'] = trans_type
    sql = f"SELECT * FROM finance_transactions WHERE {' AND '.join(conditions)} ORDER BY created_at"
    try: cur.execute(sql, params); items = cur.fetchall(); return items
    except psycopg2.Error as e: logger.error(f"Error get_finance_transactions: {e}"); return []
    finally:
        if conn: cur.close(); conn.close()