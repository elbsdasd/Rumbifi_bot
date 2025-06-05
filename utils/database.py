import psycopg2
import psycopg2.extras # Para dict cursor
import config
from datetime import datetime, timedelta, date
import pytz
import logging
import time

logger = logging.getLogger(__name__)

LIMA_TZ = pytz.timezone('America/Lima')

# --- MANEJO DE CONEXIÓN ---
def get_db_connection():
    """Establece y devuelve una conexión a la base de datos PostgreSQL."""
    try:
        conn = psycopg2.connect(config.DATABASE_URL)
        return conn
    except psycopg2.Error as e:
        logger.error(f"Error al conectar a PostgreSQL: {e}")
        # En un caso real, podríamos reintentar o manejar esto de forma más robusta.
        # Por ahora, si no podemos conectar, muchas funciones fallarán.
        raise # Relanzar la excepción para que se maneje más arriba si es necesario.

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
            item_type VARCHAR(20) NOT NULL, -- 'objective', 'important', 'secondary'
            text TEXT NOT NULL,
            reminder_time TIME, -- Solo HH:MM
            completed BOOLEAN, -- True, False, o NULL si no marcado
            marked_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
            notification_sent BOOLEAN DEFAULT FALSE
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS wellbeing_items (
            doc_id SERIAL PRIMARY KEY, -- Un ID para el documento/día
            user_id BIGINT NOT NULL,
            item_date DATE NOT NULL,
            item_type VARCHAR(20) NOT NULL, -- 'exercise', 'diet_main', 'diet_extra'
            created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS wellbeing_sub_items (
            sub_item_id SERIAL PRIMARY KEY,
            doc_id INTEGER REFERENCES wellbeing_items(doc_id) ON DELETE CASCADE,
            text TEXT NOT NULL,
            completed BOOLEAN DEFAULT FALSE,
            marked_at TIMESTAMPTZ
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS finance_transactions (
            transaction_id SERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            transaction_type VARCHAR(30) NOT NULL, -- 'income_fixed', etc.
            amount NUMERIC(12, 2) NOT NULL,
            description TEXT,
            transaction_date DATE NOT NULL, -- Día de la transacción
            transaction_month VARCHAR(7) NOT NULL, -- Mes en formato YYYY-MM
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
        if conn:
            conn.rollback() # Revertir si algo falló
        raise # Relanzar para que main.py sepa que falló
    finally:
        if conn:
            conn.close()

# --- FUNCIONES DE USUARIO (Adaptadas para PostgreSQL) ---
def get_user_data(user_id: int):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute("SELECT * FROM rumbify_users WHERE user_id = %s", (user_id,))
    user_data = cur.fetchone()
    cur.close()
    conn.close()
    return user_data # Retorna un DictRow o None

def create_or_update_user(user_id: int, data: dict):
    conn = get_db_connection()
    cur = conn.cursor()
    # Usar INSERT ... ON CONFLICT para actualizar si ya existe (UPSERT)
    # Asegurarse de que las claves en 'data' coincidan con las columnas
    sql = """
        INSERT INTO rumbify_users (user_id, trial_start_date, trial_active, has_permanent_access, last_seen)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (user_id) DO UPDATE SET
            trial_start_date = EXCLUDED.trial_start_date,
            trial_active = EXCLUDED.trial_active,
            has_permanent_access = EXCLUDED.has_permanent_access,
            last_seen = EXCLUDED.last_seen;
    """
    try:
        cur.execute(sql, (
            user_id,
            data.get('trial_start_date'),
            data.get('trial_active', True),
            data.get('has_permanent_access', False),
            data.get('last_seen')
        ))
        conn.commit()
    except psycopg2.Error as e:
        logger.error(f"Error en create_or_update_user: {e}")
        conn.rollback()
    finally:
        cur.close()
        conn.close()

def add_permanent_access(user_id: int):
    user_data = get_user_data(user_id) # Obtiene datos existentes o None
    now_lima_iso = datetime.now(LIMA_TZ).isoformat()
    
    if not user_data: # Si el usuario no existe, crearlo con acceso permanente
        new_data = {
            "trial_start_date": None, # No necesita prueba
            "trial_active": False,
            "has_permanent_access": True,
            "last_seen": now_lima_iso
        }
        create_or_update_user(user_id, new_data)
    else: # Si existe, actualizar
        update_data = {
            "trial_start_date": user_data['trial_start_date'], # Mantener si existía
            "trial_active": False, # Desactivar prueba
            "has_permanent_access": True,
            "last_seen": now_lima_iso # Actualizar last_seen
        }
        create_or_update_user(user_id, update_data)
    return True


def remove_permanent_access(user_id: int):
    user_data = get_user_data(user_id)
    if user_data:
        update_data = dict(user_data) # Convertir DictRow a dict normal
        update_data["has_permanent_access"] = False
        update_data["last_seen"] = datetime.now(LIMA_TZ).isoformat()
        create_or_update_user(user_id, update_data)
        return True
    return False

def check_user_access(user_id: int) -> tuple[bool, str]:
    user_data = get_user_data(user_id)
    current_time_lima = datetime.now(LIMA_TZ)

    if not user_data:
        trial_start_iso = current_time_lima.isoformat()
        new_user_data = {
            "trial_start_date": trial_start_iso,
            "trial_active": True,
            "has_permanent_access": False,
            "last_seen": trial_start_iso
        }
        create_or_update_user(user_id, new_user_data)
        return True, "Trial started"

    # Actualizar last_seen
    # Hacemos una copia para no modificar el DictRow directamente si no es necesario
    update_data_for_last_seen = dict(user_data)
    update_data_for_last_seen["last_seen"] = current_time_lima.isoformat()
    create_or_update_user(user_id, update_data_for_last_seen)
    
    # Re-obtener por si acaso, o usar los datos ya obtenidos pero siendo cuidadosos
    # user_data = get_user_data(user_id) # Opcional, para asegurar datos frescos tras el update

    if user_data.get("has_permanent_access", False):
        return True, "Permanent access"

    if user_data.get("trial_active", False) and user_data.get("trial_start_date"):
        trial_start_date_db = user_data["trial_start_date"]
        # Asegurarse de que trial_start_date_db es un objeto datetime con zona horaria
        if isinstance(trial_start_date_db, str):
             trial_start_date_dt = datetime.fromisoformat(trial_start_date_db)
        elif isinstance(trial_start_date_db, datetime):
            trial_start_date_dt = trial_start_date_db
        else: # Si es otro tipo, error
            logger.error(f"Formato de trial_start_date inesperado para user {user_id}: {trial_start_date_db}")
            # Invalidar prueba
            err_update_data = dict(user_data)
            err_update_data["trial_active"] = False
            create_or_update_user(user_id, err_update_data)
            return False, config.MSG_CONTACT_FOR_FULL_ACCESS

        # Si no tiene zona horaria, asumir que es LIMA o UTC y localizar
        if trial_start_date_dt.tzinfo is None:
            trial_start_date_dt = LIMA_TZ.localize(trial_start_date_dt) # O si está en UTC: pytz.utc.localize(trial_start_date_dt).astimezone(LIMA_TZ)
        else: # Si tiene, convertirla a LIMA por si acaso
            trial_start_date_dt = trial_start_date_dt.astimezone(LIMA_TZ)

        if current_time_lima < trial_start_date_dt + timedelta(days=3):
            return True, "Trial active"
        else:
            expired_trial_data = dict(user_data)
            expired_trial_data["trial_active"] = False
            create_or_update_user(user_id, expired_trial_data)
            return False, config.MSG_CONTACT_FOR_FULL_ACCESS
            
    return False, config.MSG_CONTACT_FOR_FULL_ACCESS

# --- FUNCIONES DE PLANIFICACIÓN (PostgreSQL) ---
def save_planning_item(user_id: int, item_type: str, text: str, reminder_time: str = None):
    conn = get_db_connection()
    cur = conn.cursor()
    today_lima_date = datetime.now(LIMA_TZ).date() # Solo la fecha
    
    # Convertir reminder_time "HH:MM" a objeto time de Python si existe
    reminder_time_obj = None
    if reminder_time:
        try:
            reminder_time_obj = datetime.strptime(reminder_time, "%H:%M").time()
        except ValueError:
            logger.warning(f"Formato de reminder_time inválido '{reminder_time}', se guardará como NULL.")
            reminder_time_obj = None
            
    sql = """
        INSERT INTO planning_items (user_id, item_date, item_type, text, reminder_time, completed, notification_sent)
        VALUES (%s, %s, %s, %s, %s, NULL, %s) RETURNING item_id; 
    """ # completed es NULL inicialmente
    try:
        cur.execute(sql, (
            user_id, today_lima_date, item_type, text, reminder_time_obj,
            False if reminder_time_obj else None # notification_sent
        ))
        item_id = cur.fetchone()[0]
        conn.commit()
        return item_id # Retornar el ID del nuevo ítem
    except psycopg2.Error as e:
        logger.error(f"Error guardando planning_item: {e}")
        conn.rollback()
        return None
    finally:
        cur.close()
        conn.close()

def get_daily_planning_items(user_id: int, date_obj: date): # date_obj es un objeto date
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    # Añadir item_id a la selección para usarlo como key
    sql = "SELECT item_id AS key, user_id, item_date AS date, item_type AS type, text, reminder_time, completed, marked_at, created_at, notification_sent FROM planning_items WHERE user_id = %s AND item_date = %s ORDER BY created_at"
    cur.execute(sql, (user_id, date_obj))
    items = cur.fetchall()
    cur.close()
    conn.close()
    return items # Lista de DictRow

def update_planning_item_status(item_id: int, completed: bool):
    conn = get_db_connection()
    cur = conn.cursor()
    sql = "UPDATE planning_items SET completed = %s, marked_at = %s WHERE item_id = %s"
    try:
        cur.execute(sql, (completed, datetime.now(LIMA_TZ), item_id))
        conn.commit()
    except psycopg2.Error as e:
        logger.error(f"Error actualizando planning_item_status: {e}")
        conn.rollback()
    finally:
        cur.close()
        conn.close()

def get_pending_reminders():
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    today_lima_date = datetime.now(LIMA_TZ).date()
    # Obtener item_id como 'key'
    sql = """
        SELECT item_id AS key, user_id, text, reminder_time 
        FROM planning_items 
        WHERE item_date = %s AND reminder_time IS NOT NULL AND notification_sent = FALSE
    """
    cur.execute(sql, (today_lima_date,))
    items = cur.fetchall()
    cur.close()
    conn.close()
    return items

def mark_reminder_sent(item_id: int):
    conn = get_db_connection()
    cur = conn.cursor()
    sql = "UPDATE planning_items SET notification_sent = TRUE WHERE item_id = %s"
    try:
        cur.execute(sql, (item_id,))
        conn.commit()
    except psycopg2.Error as e:
        logger.error(f"Error marcando reminder_sent: {e}")
        conn.rollback()
    finally:
        cur.close()
        conn.close()

def cleanup_old_unmarked_tasks():
    """Elimina tareas de planificación no marcadas (completed IS NULL) con más de 24h."""
    conn = get_db_connection()
    cur = conn.cursor()
    cutoff_time = datetime.now(LIMA_TZ) - timedelta(days=1)
    # Eliminar donde 'completed' es NULL y 'created_at' es más antiguo que el cutoff
    sql = "DELETE FROM planning_items WHERE completed IS NULL AND created_at < %s"
    try:
        cur.execute(sql, (cutoff_time,))
        deleted_count = cur.rowcount
        conn.commit()
        if deleted_count > 0:
            logger.info(f"Limpieza: {deleted_count} tareas antiguas no marcadas eliminadas.")
    except psycopg2.Error as e:
        logger.error(f"Error en cleanup_old_unmarked_tasks: {e}")
        conn.rollback()
    finally:
        cur.close()
        conn.close()


# --- FUNCIONES DE BIENESTAR (PostgreSQL) ---
# wellbeing_items: user_id, item_date, item_type -> doc_id
# wellbeing_sub_items: doc_id (FK), text, completed, marked_at

def save_wellbeing_item(user_id: int, item_type: str, data_list: list, date_obj: date = None):
    """Guarda ítems de bienestar. Crea un 'documento' y luego los sub-ítems."""
    if date_obj is None:
        date_obj = datetime.now(LIMA_TZ).date()
    
    conn = get_db_connection()
    cur = conn.cursor()
    doc_id = None
    try:
        # 1. Crear o encontrar el wellbeing_items (documento)
        cur.execute(
            "SELECT doc_id FROM wellbeing_items WHERE user_id = %s AND item_date = %s AND item_type = %s",
            (user_id, date_obj, item_type)
        )
        existing_doc = cur.fetchone()
        if existing_doc:
            doc_id = existing_doc[0]
            # Opcional: podrías querer borrar sub-items antiguos si esto es un reemplazo total
            cur.execute("DELETE FROM wellbeing_sub_items WHERE doc_id = %s", (doc_id,))
            cur.execute("UPDATE wellbeing_items SET updated_at = %s WHERE doc_id = %s", (datetime.now(LIMA_TZ), doc_id))
        else:
            cur.execute(
                "INSERT INTO wellbeing_items (user_id, item_date, item_type, updated_at) VALUES (%s, %s, %s, %s) RETURNING doc_id",
                (user_id, date_obj, item_type, datetime.now(LIMA_TZ))
            )
            doc_id = cur.fetchone()[0]

        # 2. Insertar los sub-ítems
        if doc_id and data_list:
            sub_item_sql = "INSERT INTO wellbeing_sub_items (doc_id, text) VALUES (%s, %s)"
            # Convertir data_list a tuplas para executemany
            sub_items_to_insert = [(doc_id, text_item) for text_item in data_list]
            cur.executemany(sub_item_sql, sub_items_to_insert)
        
        conn.commit()
        return doc_id # Retorna el ID del documento principal
        
    except psycopg2.Error as e:
        logger.error(f"Error guardando wellbeing_item: {e}")
        conn.rollback()
        return None
    finally:
        cur.close()
        conn.close()

def get_daily_wellbeing_doc_and_items(user_id: int, item_type: str, date_obj: date = None):
    """Obtiene el documento de bienestar y sus sub-ítems."""
    if date_obj is None:
        date_obj = datetime.now(LIMA_TZ).date()
    
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    
    # Obtener el doc_id primero
    cur.execute(
        "SELECT doc_id FROM wellbeing_items WHERE user_id = %s AND item_date = %s AND item_type = %s",
        (user_id, date_obj, item_type)
    )
    doc_row = cur.fetchone()
    if not doc_row:
        cur.close()
        conn.close()
        return None # No existe el documento para este día/tipo

    doc_id = doc_row['doc_id']
    
    # Obtener sub-ítems
    cur.execute(
        "SELECT sub_item_id AS key, text, completed, marked_at FROM wellbeing_sub_items WHERE doc_id = %s ORDER BY sub_item_id",
        (doc_id,)
    )
    sub_items = cur.fetchall()
    
    cur.close()
    conn.close()
    
    # Devolver en un formato similar al de Deta para compatibilidad con handlers
    return {"key": doc_id, "items": sub_items, "type": item_type, "date": date_obj}


def update_wellbeing_sub_item_status(sub_item_id: int, completed: bool):
    conn = get_db_connection()
    cur = conn.cursor()
    sql = "UPDATE wellbeing_sub_items SET completed = %s, marked_at = %s WHERE sub_item_id = %s"
    try:
        cur.execute(sql, (completed, datetime.now(LIMA_TZ), sub_item_id))
        conn.commit()
    except psycopg2.Error as e:
        logger.error(f"Error actualizando wellbeing_sub_item_status: {e}")
        conn.rollback()
    finally:
        cur.close()
        conn.close()


# --- FUNCIONES DE FINANZAS (PostgreSQL) ---
def save_finance_transaction(user_id: int, trans_type: str, amount: float, description: str = None, date_obj: date = None):
    if date_obj is None:
        date_obj = datetime.now(LIMA_TZ).date()
    
    month_str = date_obj.strftime("%Y-%m")
    conn = get_db_connection()
    cur = conn.cursor()
    sql = """
        INSERT INTO finance_transactions (user_id, transaction_type, amount, description, transaction_date, transaction_month)
        VALUES (%s, %s, %s, %s, %s, %s) RETURNING transaction_id;
    """
    try:
        cur.execute(sql, (user_id, trans_type, amount, description, date_obj, month_str))
        trans_id = cur.fetchone()[0]
        conn.commit()
        return trans_id
    except psycopg2.Error as e:
        logger.error(f"Error guardando finance_transaction: {e}")
        conn.rollback()
        return None
    finally:
        cur.close()
        conn.close()

def get_finance_transactions(user_id: int, month_str: str = None, day_obj: date = None, trans_type: str = None):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    
    conditions = ["user_id = %(user_id)s"]
    params = {'user_id': user_id}

    if month_str:
        conditions.append("transaction_month = %(month_str)s")
        params['month_str'] = month_str
    if day_obj:
        conditions.append("transaction_date = %(day_obj)s")
        params['day_obj'] = day_obj
    if trans_type:
        conditions.append("transaction_type = %(trans_type)s")
        params['trans_type'] = trans_type
        
    sql = f"SELECT * FROM finance_transactions WHERE {' AND '.join(conditions)} ORDER BY created_at"
    
    cur.execute(sql, params)
    items = cur.fetchall()
    cur.close()
    conn.close()
    return items