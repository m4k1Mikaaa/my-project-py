import sqlite3
import bcrypt
import base64
from cryptography.fernet import Fernet
import os
import mysql.connector
import psycopg2
import logging
from datetime import datetime, timedelta
from app_config import app_config, AppConfig
import json
from PyQt6.QtCore import QObject, pyqtSignal

logger = logging.getLogger(__name__)

class DBMgmtSignals(QObject): # sourcery skip: snake-case-functions
    item_status_changed = pyqtSignal(int, str) # item_id, new_status
    payment_status_updated = pyqtSignal(int) # user_id
    data_changed = pyqtSignal(str) # table_name (e.g., 'items', 'users')
    server_encryption_key_missing = pyqtSignal()

db_signals = DBMgmtSignals()

class DBManagement:
    def __init__(self):
        self.conn = None
        self.cursor = None
        self.paramstyle = '?' # Default to SQLite's parameter style

    def initialize_connections(self):
        """
        Establishes both local and (if enabled) remote database connections
        at application startup. This prevents connection delays later on.
        """
        # Always re-initialize the local SQLite instance on the manager itself.
        # This will attempt to connect to the local DB. If it doesn't exist,
        # get_instance_for_mode will handle its creation later.
        try:
            _get_and_cache_instance(is_remote=False, force_reconnect=True)
        except Exception as e:
            logger.error(f"Initial local DB connection failed: {e}", exc_info=True)

        # Initialize remote connection if enabled in config
        use_server_db = app_config.get('DATABASE', 'enabled', fallback='False').lower() == 'true'
        if use_server_db:
            try:
                _get_and_cache_instance(is_remote=True, force_reconnect=True)
            except Exception as e:
                logger.warning(f"Initial remote DB connection failed: {e}")
                # Don't re-raise here; allow the app to start in a degraded state.
                # The error will be handled when a remote connection is requested.

    def get_active_instance(self) -> 'DBManagement':
        """
        Returns the currently active database instance based on the global config.
        """
        use_server_db = app_config.get('DATABASE', 'enabled', fallback='False').lower() == 'true'
        if use_server_db:
            return get_db_instance(is_remote=True)
        return get_db_instance(is_remote=False)

    def create_and_initialize_local_db(self):
        """
        Explicitly creates and initializes the local SQLite database file and tables.
        This is called from the settings dialog when a new DB path is specified.
        Returns the newly created instance.
        """
        try:
            # Force a reconnection for the local instance.
            return _get_and_cache_instance(is_remote=False, force_reconnect=True)
        except Exception as e:
            logger.error(f"Error during explicit local DB creation: {e}", exc_info=True)
            return None

    def close_all_connections(self):
        """Closes all globally managed database connections."""
        global _local_instance, _remote_instance
        if _local_instance:
            _local_instance.close_connection()
        if _remote_instance:
            _remote_instance.close_connection()
        logger.info("All managed database connections closed.")

    def _setup_cursor_and_paramstyle(self):
        """Sets up the cursor and paramstyle based on the connection type."""
        if isinstance(self.conn, sqlite3.Connection):
            self.conn.row_factory = self._dict_factory
            self.cursor = self.conn.cursor()
            self.paramstyle = '?'
        elif hasattr(self.conn, 'cursor'): # For psycopg2
            from psycopg2.extras import DictCursor
            self.cursor = self.conn.cursor(cursor_factory=DictCursor)
            self.paramstyle = '%s'
        else:
            raise TypeError("Unsupported database connection type.")

    def _connect_local(self):
        """Connect to the local SQLite database."""
        from app_config import APP_ROOT
        default_path = os.path.join(APP_ROOT, 'local_mika_rental.db')
        db_path = app_config.get('LOCAL_DATABASE', 'path', fallback=default_path)

        # if not os.path.exists(db_path):
        #     raise FileNotFoundError(f"Local database file not found at: {db_path}")
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = self._dict_factory
        self.cursor = self.conn.cursor()
        self._setup_cursor_and_paramstyle()
        self.paramstyle = '?'
        logger.info("Connected to local SQLite database at %s", db_path)

    def _connect_remote(self, config_object=None):
        """Connect to the remote database based on config."""
        # Use the passed config_object for testing, otherwise fall back to the global app_config.
        config_to_use = config_object if config_object else app_config
        # Since we only support PostgreSQL now, we connect directly.
        try:
            # --- FIX: Check for password before attempting to connect ---
            password = config_to_use.get('DATABASE', 'password')
            if not password:
                raise ConnectionError("กรุณาตั้งรหัสผ่านสำหรับฐานข้อมูลเซิร์ฟเวอร์ในหน้าตั้งค่า")

            self.conn = psycopg2.connect(
                host=config_to_use.get('DATABASE', 'host', '').strip(),
                port=config_to_use.getint('DATABASE', 'port'),
                dbname=config_to_use.get('DATABASE', 'database', '').strip(),
                user=config_to_use.get('DATABASE', 'user', '').strip(),
                password=password
            )
            from psycopg2.extras import DictCursor
            self.cursor = self.conn.cursor(cursor_factory=DictCursor)
            self.paramstyle = '%s'
            logger.info("Successfully connected to remote PostgreSQL database.")
            # --- NEW: Run remote schema migration after successful connection ---
            self._migrate_remote_schema()
        except psycopg2.OperationalError as e:
            # Catch specific connection errors (wrong host, port, dbname, user, password)
            # and re-raise them as a more generic ConnectionError with a user-friendly message.
            logger.error(f"Remote DB connection failed (OperationalError): {e}", exc_info=True)
            raise ConnectionError(f"ไม่สามารถเชื่อมต่อฐานข้อมูลเซิร์ฟเวอร์ได้:\n{e}")
        except Exception as e:
            logger.error(f"An unexpected error occurred during remote DB connection: {e}", exc_info=True)
            raise ConnectionError(f"เกิดข้อผิดพลาดที่ไม่คาดคิดในการเชื่อมต่อฐานข้อมูล:\n{e}")

    def _migrate_remote_schema(self):
        """
        Checks for and applies necessary schema migrations to the remote PostgreSQL database.
        This ensures backward compatibility with older database schemas.
        """
        if not self.cursor or not self.conn:
            return
        try:
            # --- Migration for payment system in 'rental_history' table ---
            self.cursor.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_schema = 'public' AND table_name = 'rental_history'
            """)
            history_columns = [row['column_name'] for row in self.cursor.fetchall()]
            history_migrations = {
                'amount_due': "ALTER TABLE rental_history ADD COLUMN amount_due NUMERIC(10, 2)",
                'payment_status': "ALTER TABLE rental_history ADD COLUMN payment_status VARCHAR(20)",
                'payment_date': "ALTER TABLE rental_history ADD COLUMN payment_date TIMESTAMP",
                'transaction_ref': "ALTER TABLE rental_history ADD COLUMN transaction_ref VARCHAR(255)",
                'slip_sender': "ALTER TABLE rental_history ADD COLUMN slip_sender VARCHAR(255)",
                'slip_receiver': "ALTER TABLE rental_history ADD COLUMN slip_receiver VARCHAR(255)",
                'slip_transacted_at': "ALTER TABLE rental_history ADD COLUMN slip_transacted_at TIMESTAMP",
                'slip_data_json': "ALTER TABLE rental_history ADD COLUMN slip_data_json TEXT"
            }
            for col, sql in history_migrations.items():
                if col not in history_columns:
                    self.cursor.execute(sql)
            # --- Migration for new pricing model in 'items' table ---
            self.cursor.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_schema = 'public' AND table_name = 'items'
            """)
            item_columns = [row['column_name'] for row in self.cursor.fetchall()]

            migrations = {
                'price_model': "ALTER TABLE items ADD COLUMN price_model VARCHAR(50) DEFAULT 'per_minute'",
                'fixed_fee': "ALTER TABLE items ADD COLUMN fixed_fee NUMERIC(10, 2) DEFAULT 0.0",
                'grace_period_minutes': "ALTER TABLE items ADD COLUMN grace_period_minutes INTEGER DEFAULT 0",
                'minimum_charge': "ALTER TABLE items ADD COLUMN minimum_charge NUMERIC(10, 2) DEFAULT 0.0"
            }

            for col, sql in migrations.items():
                if col not in item_columns:
                    self.cursor.execute(sql)
            self.conn.commit()
        except psycopg2.Error as e:
            logger.error(f"Failed to migrate remote schema: {e}", exc_info=True)
            self.conn.rollback()

    def close_connection(self):
        """Closes the database connection if it's open."""
        if self.conn:
            self.conn.close()
            self.conn = None
            self.cursor = None

    def _dict_factory(self, cursor, row):
        """A factory to return query results as dictionaries for SQLite."""
        d = {}
        for idx, col in enumerate(cursor.description):
            d[col[0]] = row[idx]
        return d

    def _create_local_tables(self):
        """Create tables in the local SQLite database if they don't exist."""
        if not self.cursor: return
        # Users table
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                first_name TEXT,
                last_name TEXT,
                email TEXT UNIQUE,
                phone TEXT,
                location TEXT,
                avatar_path BLOB,
                role TEXT NOT NULL DEFAULT 'user'
            )
        ''')

        # --- Migration for user roles ---
        self.cursor.execute("PRAGMA table_info(users)")
        user_columns = [info['name'] for info in self.cursor.fetchall()]
        if 'role' not in user_columns:
            self.cursor.execute("ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'user'")

        # System settings table (for server mode)
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS system_settings (
                setting_key TEXT PRIMARY KEY NOT NULL,
                setting_value BLOB
            )
        ''')

        # Items table
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                brand TEXT,
                description TEXT,
                status TEXT NOT NULL DEFAULT 'available',
                image_path BLOB,
                current_renter_id INTEGER,
                price_per_minute REAL DEFAULT 0.0, -- Updated from price_per_day
                price_unit TEXT DEFAULT 'ต่อวัน',
                renter_username TEXT,
                rent_date DATETIME,
                FOREIGN KEY(current_renter_id) REFERENCES users(id)
            )
        ''')
        # Rental history table
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS rental_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                rent_date DATETIME NOT NULL,
                return_date DATETIME,
                initiator TEXT,
                FOREIGN KEY(item_id) REFERENCES items(id),
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
        ''')

        # --- Simple Schema Migration for Payment System ---
        # Checks if payment columns exist and adds them if they don't.
        # This ensures backward compatibility with older database files.
        self.cursor.execute("PRAGMA table_info(rental_history)")
        columns = [info['name'] for info in self.cursor.fetchall()]
        
        if 'amount_due' not in columns:
            self.cursor.execute("ALTER TABLE rental_history ADD COLUMN amount_due REAL")
        if 'payment_status' not in columns:
            self.cursor.execute("ALTER TABLE rental_history ADD COLUMN payment_status TEXT")
        if 'payment_date' not in columns:
            self.cursor.execute("ALTER TABLE rental_history ADD COLUMN payment_date DATETIME")
        if 'transaction_ref' not in columns:
            self.cursor.execute("ALTER TABLE rental_history ADD COLUMN transaction_ref TEXT")
        if 'slip_sender' not in columns:
            self.cursor.execute("ALTER TABLE rental_history ADD COLUMN slip_sender TEXT")
        if 'slip_receiver' not in columns:
            self.cursor.execute("ALTER TABLE rental_history ADD COLUMN slip_receiver TEXT")
        if 'slip_transacted_at' not in columns:
            self.cursor.execute("ALTER TABLE rental_history ADD COLUMN slip_transacted_at DATETIME")
        if 'slip_data_json' not in columns:
            self.cursor.execute("ALTER TABLE rental_history ADD COLUMN slip_data_json TEXT")

        # --- Migration for new pricing model ---
        self.cursor.execute("PRAGMA table_info(items)")
        item_columns = [info['name'] for info in self.cursor.fetchall()]
        if 'price_model' not in item_columns:
            self.cursor.execute("ALTER TABLE items ADD COLUMN price_model TEXT DEFAULT 'per_minute'")
        if 'fixed_fee' not in item_columns:
            self.cursor.execute("ALTER TABLE items ADD COLUMN fixed_fee REAL DEFAULT 0.0")
        if 'grace_period_minutes' not in item_columns:
            self.cursor.execute("ALTER TABLE items ADD COLUMN grace_period_minutes INTEGER DEFAULT 0")
        if 'minimum_charge' not in item_columns:
            self.cursor.execute("ALTER TABLE items ADD COLUMN minimum_charge REAL DEFAULT 0.0")
        
        self.conn.commit()

    def create_remote_tables(self):
        """
        Creates tables in the remote database (PostgreSQL/MySQL) if they don't exist.
        This should be called manually by an admin after the initial connection.
        """
        if not self.cursor or not self.conn:
            raise ConnectionError("Cannot create remote tables: No active database connection.")

        # --- Table Creation SQL Statements (Dialect-Specific) ---
        # PostgreSQL-specific statements
        table_statements = [
            """
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    username VARCHAR(80) UNIQUE NOT NULL,
                    password TEXT NOT NULL,
                    first_name VARCHAR(100),
                    last_name VARCHAR(100),
                    email VARCHAR(120) UNIQUE,
                    phone VARCHAR(20),
                    location TEXT,
                    avatar_path BYTEA, role VARCHAR(20) NOT NULL DEFAULT 'user'
                );
            """,
            """
                CREATE TABLE IF NOT EXISTS items (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(255) NOT NULL,
                    brand VARCHAR(100),
                    description TEXT,
                    status VARCHAR(50) NOT NULL DEFAULT 'available',
                    image_path BYTEA,
                    current_renter_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                    price_per_minute NUMERIC(10, 4) DEFAULT 0.0,
                    price_unit VARCHAR(20) DEFAULT 'ต่อวัน',
                    price_model VARCHAR(50) DEFAULT 'per_minute',
                    fixed_fee NUMERIC(10, 2) DEFAULT 0.0,
                    grace_period_minutes INTEGER DEFAULT 0,
                    minimum_charge NUMERIC(10, 2) DEFAULT 0.0,
                    renter_username VARCHAR(80),
                    rent_date TIMESTAMP
                );
            """,
            """
                CREATE TABLE IF NOT EXISTS rental_history (
                    id SERIAL PRIMARY KEY,
                    item_id INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    rent_date TIMESTAMP NOT NULL,
                    return_date TIMESTAMP,
                    initiator VARCHAR(50),
                    amount_due NUMERIC(10, 2),
                    payment_status VARCHAR(20),
                    payment_date TIMESTAMP,
                    transaction_ref VARCHAR(255),
                    slip_sender VARCHAR(255),
                    slip_receiver VARCHAR(255),
                    slip_transacted_at TIMESTAMP,
                    slip_data_json TEXT
                );
            """,
            """
                CREATE TABLE IF NOT EXISTS system_settings (
                    setting_key VARCHAR(255) PRIMARY KEY NOT NULL,
                    setting_value BYTEA
                );
            """
        ]

        try:
            for statement in table_statements:
                self.cursor.execute(statement)
            self.conn.commit()
        except psycopg2.Error as e:
            # If an error occurs (e.g., table already exists in a transaction), rollback.
            # This is crucial for PostgreSQL to allow further commands on the connection.
            self.conn.rollback()
            # Re-try the operation after rollback, as the connection is now clean.
            # This handles the case where the connection was in an aborted state before this was called.
            # Also, generate and store the server's master encryption key.
            for statement in table_statements:
                self.cursor.execute(statement)
            self.conn.commit()
        
        # After creating tables, ensure the master encryption key exists.
        self.cursor.execute("SELECT setting_value FROM system_settings WHERE setting_key = 'SYSTEM.encryption_key'")
        if self.cursor.fetchone() is None:
            print("Server encryption key not found. Generating a new one...")
            # Generate a new, strong, random key for the server.
            new_server_key = Fernet.generate_key()
            # Store it in plaintext (as bytes) because it's the key to everything else.
            # We use BYTEA which is suitable for this.
            sql = "INSERT INTO system_settings (setting_key, setting_value) VALUES (%s, %s)"
            self.cursor.execute(sql, ('SYSTEM.encryption_key', new_server_key))
            self.conn.commit()
            print("New server encryption key has been generated and stored.")

    @staticmethod
    def static_hash_password(password):
        """A static version of _hash_password that can be used without an instance."""
        return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())

    def _hash_password(self, password):
        return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())

    def _check_password(self, password, hashed_password):
        if not password or not hashed_password:
            return False
        # Ensure both password and hashed_password are bytes
        encoded_password = password.encode('utf-8')

        # If the hashed password from the DB is a hex string, convert it back to bytes.
        if isinstance(hashed_password, str):
            try:
                hashed_password = bytes.fromhex(hashed_password)
            except (ValueError, TypeError):
                hashed_password = hashed_password.encode('utf-8') # Fallback for old format
        return bcrypt.checkpw(encoded_password, hashed_password)

    # --- System Settings Management ---
    def get_system_setting(self, key: str, decrypt: bool = True) -> str | bytes | None:
        """Retrieves and decrypts a setting from the system_settings table."""
        if not self.cursor:
            return None
        sql = f"SELECT setting_value FROM system_settings WHERE setting_key = {self.paramstyle}"
        try:
            self.cursor.execute(sql, (key,))
            result = self.cursor.fetchone()
            if result and result['setting_value']:
                # psycopg2 returns BYTEA as a memoryview, which must be converted to bytes
                # for the cryptography library to use it.
                value_bytes = bytes(result['setting_value'])

                if not decrypt:
                    return value_bytes

                server_fernet = _get_server_fernet(self)
                if server_fernet:
                    return server_fernet.decrypt(value_bytes).decode('utf-8')
                return None # Or raise an error if key is essential

            return None
        except (psycopg2.Error, Exception) as e:
            logger.error(f"Error getting system setting '{key}': {e}", exc_info=True)
            self.conn.rollback() # CRITICAL: Rollback the failed transaction
            return None

    def get(self, section, key, fallback=None):
        """
        Provides a 'get' method to conform to the config_source interface,
        allowing this class to act as a configuration provider.
        It delegates the call to the internal get_system_setting method.
        """
        # In server mode, we primarily look for settings in the server database.
        # If a setting is not found in the server DB, we return the provided fallback.
        # We do NOT fall back to the local app_config for server-specific settings.
        server_value = self.get_system_setting(f"{section.upper()}.{key.lower()}")
        if server_value is not None:
            return server_value
        return fallback

    def getint(self, section, key, fallback=None):
        """
        Provides a 'getint' method for the config_source interface.
        """
        value = self.get(section, key, fallback=None)
        if value is not None:
            try:
                return int(value)
            except (ValueError, TypeError):
                return fallback
        return fallback

    def set_system_setting(self, key: str, value: str) -> tuple[bool, str]:
        """Encrypts and saves a setting to the system_settings table."""
        if not self.cursor or not self.conn:
            return False, "No active database connection."
        try:
            server_fernet = _get_server_fernet(self)
            if not server_fernet:
                raise ConnectionError("Cannot save setting: Server encryption key is missing.")
            encrypted_value = server_fernet.encrypt(str(value).encode('utf-8'))
            # Use INSERT OR REPLACE for simplicity (UPSERT)
            if isinstance(self.conn, sqlite3.Connection): # SQLite
                sql = "INSERT OR REPLACE INTO system_settings (setting_key, setting_value) VALUES (?, ?)"
            else: # PostgreSQL
                sql = "INSERT INTO system_settings (setting_key, setting_value) VALUES (%s, %s) ON CONFLICT (setting_key) DO UPDATE SET setting_value = EXCLUDED.setting_value;"
            self.cursor.execute(sql, (key, encrypted_value))
            self.conn.commit()
            return True, "Setting saved successfully."
        except Exception as e:
            if self.conn: self.conn.rollback()
            logger.error(f"Failed to save setting '{key}': {e}", exc_info=True)
            return False, f"Failed to save setting '{key}': {e}"

    def verify_user_local(self, username, password):
        """
        Verifies a user's credentials against the local SQLite database,
        including account lockout logic based on app_config.ini settings.
        """
        sql = f"SELECT * FROM users WHERE username = {self.paramstyle}"
        self.cursor.execute(sql, (username,))
        user = self.cursor.fetchone()

        # --- FIX: Handle case where username does not exist ---
        if not user:
            return None, "ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง"

        if self._check_password(password, user['password']):
            return user, None
        return None, "ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง"

    # --- User Management ---
    def create_user(self, username, password, first_name, last_name, email, phone, location, avatar_data=None):
        hashed_password = self._hash_password(password)
        try:
            # Determine the correct paramstyle for the query.
            # self.paramstyle is correctly set during connection (_setup_cursor_and_paramstyle).
            # The issue was that the instance being used might have been the wrong one.
            # By ensuring the correct instance is used (via db_manager.get_active_instance), this should now work.
            # Let's make it more robust by re-checking.
            param = '?' if isinstance(self.conn, sqlite3.Connection) else '%s'
            sql = f"INSERT INTO users (username, password, first_name, last_name, email, phone, location, avatar_path) VALUES ({param}, {param}, {param}, {param}, {param}, {param}, {param}, {param})"
            
            # Convert the bytes hash to a hex string for consistent storage across all DB types.
            # This matches the logic in create_admin_user and is required for _check_password to work correctly.
            hex_hashed_password = hashed_password.hex()

            self.cursor.execute(
                sql,
                (username, hex_hashed_password, first_name, last_name, email, phone, location, avatar_data)
            )
            self.conn.commit()
            return True, "User created successfully."
        except sqlite3.IntegrityError as e:
            return False, f"Username or email already exists: {e}"

    def create_admin_user(self, username, password):
        """Creates a user with the 'admin' role if they don't already exist."""
        hashed_password = self._hash_password(password)
        hex_hashed_password = hashed_password.hex()
        try:
            # --- New Robust Logic ---
            # This logic now ensures that a default admin is only created if the Super Admin (ID=1) does not exist.
            # This prevents overwriting the super admin's custom settings.
            self.cursor.execute(f"SELECT id FROM users WHERE id = {self.paramstyle}", (1,))
            if self.cursor.fetchone():
                return True, "Super Admin (ID: 1) already exists. No action taken."

            if isinstance(self.conn, sqlite3.Connection):
                sql = "INSERT INTO users (id, username, password, role) VALUES (1, ?, ?, 'admin')"
            else: # PostgreSQL
                sql = "INSERT INTO users (id, username, password, role) VALUES (1, %s, %s, 'admin')"
            self.cursor.execute(sql, (username, hex_hashed_password))
            
            self.conn.commit()
            return True, "Admin user created successfully."
        except Exception as e:
            logger.error(f"Failed to create admin user: {e}", exc_info=True)
            if self.conn:
                self.conn.rollback()
            return False, str(e)

    def verify_user(self, username, password):
        """
        Verifies a user's credentials against the database, including account lockout logic.
        This is the single, secure entry point for all user/admin logins.
        """
        sql = f"SELECT * FROM users WHERE username = {self.paramstyle}"
        try:
            self.cursor.execute(sql, (username,))
            user = self.cursor.fetchone()
        except psycopg2.Error as e:
            logger.error(f"Error during user verification (PostgreSQL): {e}", exc_info=True)
            self.conn.rollback()
            return None, "Database query error."

        # --- FIX: Handle case where username does not exist ---
        if not user:
            return None, "ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง"

        # --- Security Enhancement: Timing-attack resistant password check ---
        if self._check_password(password, user['password']):
            # Password is correct, now check role
            if user.get('role') in ['admin', 'super_admin']:
                return user, None # Success
            else:
                return None, "คุณไม่มีสิทธิ์ในการเข้าถึงส่วนของผู้ดูแลระบบ"
        return None, "ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง" # Password is wrong

    def username_exists(self, username, user_id_to_exclude=None):
        if not self.cursor:
            return False
        if user_id_to_exclude:
            sql = f"SELECT id FROM users WHERE username = {self.paramstyle} AND id != {self.paramstyle}"
            self.cursor.execute(sql, (username, user_id_to_exclude))
        else:
            sql = f"SELECT id FROM users WHERE username = {self.paramstyle}"
            try:
                self.cursor.execute(sql, (username,))
                return self.cursor.fetchone() is not None
            except psycopg2.Error:
                self.conn.rollback()
                return False

    def email_exists(self, email, user_id_to_exclude=None):
        if not self.cursor:
            return False
        if user_id_to_exclude:
            sql = f"SELECT id FROM users WHERE email = {self.paramstyle} AND id != {self.paramstyle}"
            self.cursor.execute(sql, (email, user_id_to_exclude))
        else:
            sql = f"SELECT id FROM users WHERE email = {self.paramstyle}"
            try:
                self.cursor.execute(sql, (email,))
                return self.cursor.fetchone() is not None
            except psycopg2.Error:
                self.conn.rollback()
                return False

    def update_user(self, user_id: int, **kwargs):
        """
        Updates a user's profile information.
        Accepts keyword arguments for the fields to be updated.
        Empty strings for optional fields will be ignored.
        """
        if not self.cursor:
            return

        update_fields = []
        params = []
        # --- FIX: Correctly handle integer 0 as a valid value to update ---
        for key, value in kwargs.items():
            # --- FIX: Allow setting fields to NULL by passing None ---
            # Only skip if the key is not 'account_locked_until' and the value is None.
            if value is not None or key == 'account_locked_until':
                if key == 'password' and value:
                    value = self._hash_password(value).hex() # Hash non-empty passwords
                update_fields.append(f"{key} = {self.paramstyle}")
                params.append(value)

        if not update_fields: return # Nothing to update
        sql = f"UPDATE users SET {', '.join(update_fields)} WHERE id = {self.paramstyle}"
        params.append(user_id)
        try:
            self.cursor.execute(sql, tuple(params))
            self.conn.commit()
            db_signals.data_changed.emit('users')
        except Exception as e:
            logger.error(f"Failed to update user {user_id}: {e}", exc_info=True)
            if self.conn: self.conn.rollback()
            raise # Re-raise the exception after rolling back

    def update_super_admin(self, new_username: str, new_password: str | None, email: str, first_name: str, last_name: str, phone: str, location: str, avatar_data: bytes | None):
        """
        Specifically updates or creates (UPSERT) the user with ID 1.
        """
        if not self.cursor:
            return

        # Use a list of tuples to maintain order for parameter substitution
        params = [
            ('username', new_username),
            ('email', email),
            ('first_name', first_name),
            ('last_name', last_name),
            ('phone', phone),
            ('location', location),
        ]

        if new_password:
            params.append(('password', self._hash_password(new_password).hex()))
        
        if avatar_data:
            params.append(('avatar_path', avatar_data))

        columns = ', '.join([p[0] for p in params])
        values = tuple([p[1] for p in params])

        if isinstance(self.conn, sqlite3.Connection):
            # --- UPSERT Logic for SQLite ---
            placeholders = ', '.join(['?'] * len(params))
            update_set = ', '.join([f"{col} = excluded.{col}" for col, val in params])
            sql = f"""
                INSERT INTO users (id, {columns}, role)
                VALUES (1, {placeholders}, 'admin')
                ON CONFLICT(id) DO UPDATE SET {update_set};
            """
            self.cursor.execute(sql, values)
        else: # PostgreSQL
            # --- UPSERT Logic for PostgreSQL ---
            placeholders = ', '.join(['%s'] * len(params))
            update_set = ', '.join([f"{col} = EXCLUDED.{col}" for col, val in params])
            sql = f"""
                INSERT INTO users (id, {columns}, role)
                VALUES (1, {placeholders}, 'admin')
                ON CONFLICT (id) DO UPDATE SET {update_set};
            """
            self.cursor.execute(sql, values)

        self.conn.commit()

    def get_user_by_id(self, user_id):
        """Fetches a user's complete data by their ID."""
        if not self.cursor:
            return None
        try:
            sql = f"SELECT * FROM users WHERE id = {self.paramstyle}"
            self.cursor.execute(sql, (user_id,))
            return self.cursor.fetchone()
        except psycopg2.Error:
            self.conn.rollback()
            return None

    def update_user_role(self, user_id: int, new_role: str):
        """Updates the role for a specific user."""
        if not self.cursor or new_role not in ['admin', 'user']:
            return
        sql = f"UPDATE users SET role = {self.paramstyle} WHERE id = {self.paramstyle}"
        self.cursor.execute(sql, (new_role, user_id))
        self.conn.commit()

    def get_all_users(self):
        """Fetches all users from the database."""
        if not self.cursor:
            return []
        sql = "SELECT id, username, first_name, last_name, email, phone, role FROM users ORDER BY username"
        try:
            self.cursor.execute(sql)
            return self.cursor.fetchall()
        except psycopg2.Error:
            self.conn.rollback()
            return []

    def get_admin_user_count(self) -> int:
        """Counts the number of users with the 'admin' role."""
        if not self.cursor:
            return 0
        try:
            self.cursor.execute("SELECT COUNT(*) as count FROM users WHERE role = 'admin'")
            result = self.cursor.fetchone()
            return result['count'] if result else 0
        except psycopg2.Error:
            self.conn.rollback()
            return 0 # Assume 0 on error

    def get_all_users_for_management(self, is_remote: bool):
        """
        Fetches all users for the user management dialog.
        If in remote mode, it filters out the Super Admin (ID=1).
        """
        all_users = self.get_all_users()
        if is_remote:
            return [user for user in all_users if user.get('id') != 1]
        return all_users

    def delete_user(self, user_id):
        """Deletes a user from the database."""
        if not self.cursor:
            return False
        try:
            sql = f"DELETE FROM users WHERE id={self.paramstyle}"
            self.cursor.execute(sql, (user_id,))
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False # Cannot delete user if they have rental history

    # --- Item Management ---
    def get_all_items(self, sort_by='name', sort_order='ASC'):
        if not self.conn or not self.cursor:
            raise ConnectionError("No active database connection.")

        """Fetches all items with dynamic sorting."""
        # Whitelist columns to prevent SQL injection
        allowed_sort_columns = {
            'name': 'name',
            'status': 'status',
            'rent_date': 'rent_date',
            'id': 'id',
            'fixed_fee': 'fixed_fee',
            'price_per_minute': 'price_per_minute'
        }
        # Whitelist sort orders
        allowed_sort_orders = ['ASC', 'DESC']

        sort_column = allowed_sort_columns.get(sort_by, 'name')
        order = sort_order.upper() if sort_order.upper() in allowed_sort_orders else 'ASC'

        # Special handling for rent_date to put NULLs last when sorting descending
        order_clause = f"ORDER BY CASE WHEN {sort_column} IS NULL THEN 1 ELSE 0 END, {sort_column} {order}"

        try:
            self.cursor.execute(f"SELECT * FROM items {order_clause}")
            return self.cursor.fetchall()
        except psycopg2.Error as e:
            logger.error(f"Error in get_all_items (PostgreSQL): {e}", exc_info=True)
            self.conn.rollback()
            return [] # Return an empty list to prevent UI crashes

    def get_item_by_id(self, item_id):
        if not self.cursor:
            return None
        sql = f"SELECT * FROM items WHERE id = {self.paramstyle}"
        try:
            self.cursor.execute(sql, (item_id,)) # type: ignore
            item_data_row = self.cursor.fetchone()

            if item_data_row:
                # --- NEW: Fetch the latest renter from rental_history ---
                # Convert the row object to a mutable dictionary
                item_data = dict(item_data_row)
                history_sql = f"""
                    SELECT u.username
                    FROM rental_history h
                    JOIN users u ON h.user_id = u.id
                    WHERE h.item_id = {self.paramstyle}
                    ORDER BY h.rent_date DESC
                    LIMIT 1
                """
                self.cursor.execute(history_sql, (item_id,))
                latest_renter_record = self.cursor.fetchone()
                item_data['latest_renter'] = latest_renter_record['username'] if latest_renter_record else None

            return item_data
        except psycopg2.Error:
            self.conn.rollback()
            return None

    def add_item(self, name, description, image_data, brand, price_per_minute: float, price_unit: str, price_model: str, fixed_fee: float, grace_period_minutes: int, minimum_charge: float):
        if not self.cursor:
            return
        sql = f"INSERT INTO items (name, description, image_path, brand, price_per_minute, price_unit, price_model, fixed_fee, grace_period_minutes, minimum_charge) VALUES ({self.paramstyle}, {self.paramstyle}, {self.paramstyle}, {self.paramstyle}, {self.paramstyle}, {self.paramstyle}, {self.paramstyle}, {self.paramstyle}, {self.paramstyle}, {self.paramstyle})"
        self.cursor.execute(
            sql,
            (name, description, image_data, brand, price_per_minute, price_unit, price_model, fixed_fee, grace_period_minutes, minimum_charge)
        )
        self.conn.commit()
        db_signals.data_changed.emit('items')

    def update_item(self, item_id, name, description, image_data, brand, status, price_per_minute: float, price_unit: str, price_model: str, fixed_fee: float, grace_period_minutes: int, minimum_charge: float):
        if not self.cursor:
            return
        sql = f"""UPDATE items SET 
                  name={self.paramstyle}, description={self.paramstyle}, image_path={self.paramstyle}, brand={self.paramstyle}, status={self.paramstyle}, 
                  price_per_minute={self.paramstyle}, price_unit={self.paramstyle}, price_model={self.paramstyle}, fixed_fee={self.paramstyle}, grace_period_minutes={self.paramstyle},
                  minimum_charge={self.paramstyle}
                  WHERE id={self.paramstyle}"""
        self.cursor.execute(
            sql,
            (name, description, image_data, brand, status, price_per_minute, price_unit, price_model, fixed_fee, grace_period_minutes, minimum_charge, item_id)
        )
        self.conn.commit()
        db_signals.data_changed.emit('items')

    def delete_item(self, item_id):
        if not self.cursor:
            return
        sql = f"DELETE FROM items WHERE id={self.paramstyle}"
        self.cursor.execute(sql, (item_id,))
        self.conn.commit()
        db_signals.data_changed.emit('items')

    # --- Rental Management ---
    def rent_item(self, item_id, user_id):
        if not self.cursor:
            return
        sql_select = f"SELECT username FROM users WHERE id = {self.paramstyle}"
        self.cursor.execute(sql_select, (user_id,))
        user = self.cursor.fetchone()
        if not user: return

        now_utc = datetime.utcnow()
        sql_update = f"UPDATE items SET status='rented', current_renter_id={self.paramstyle}, renter_username={self.paramstyle}, rent_date={self.paramstyle} WHERE id={self.paramstyle}"
        self.cursor.execute(
            sql_update,
            (user_id, user['username'], now_utc, item_id)
        )
        sql_insert = f"INSERT INTO rental_history (item_id, user_id, rent_date) VALUES ({self.paramstyle}, {self.paramstyle}, {self.paramstyle})"
        self.cursor.execute(
            sql_insert,
            (item_id, user_id, now_utc)
        )
        self.conn.commit()
        db_signals.data_changed.emit('items')

    def return_item(self, item_id: int, amount_due: float, transaction_ref: str | None, slip_data: dict | None, initiator: str = 'user') -> int:
        if not self.cursor:
            return

        # --- NEW: Check if auto-confirm return is enabled ---
        # Determine the correct config source. For remote mode, use self.get(). For local mode, use app_config.get().
        is_remote_db = hasattr(self.conn, 'get_backend_pid')
        if is_remote_db:
            auto_confirm = self.get('WORKFLOW', 'auto_confirm_return', fallback='False').lower() == 'true'
        else: # Local mode (SQLite)
            auto_confirm = app_config.get('WORKFLOW', 'auto_confirm_return', fallback='False').lower() == 'true'

        if auto_confirm:
            # If auto-confirm is on, set status to 'available' and clear renter info immediately.
            final_status = 'available'
            sql_update_item = f"UPDATE items SET status='available', current_renter_id=NULL, renter_username=NULL, rent_date=NULL WHERE id={self.paramstyle}"
        else:
            # Otherwise, use the existing 'pending_return' workflow.
            final_status = 'pending_return'
            sql_update_item = f"UPDATE items SET status='pending_return' WHERE id={self.paramstyle}"

        self.cursor.execute(sql_update_item, (item_id,))

        # Extract data from slip_data if available
        slip_sender = None
        slip_receiver = None
        slip_transacted_at = None
        # Updated data extraction based on new API response structure
        if slip_data:
            slip_sender = slip_data.get('sender', {}).get('account', {}).get('name')
            slip_receiver = slip_data.get('receiver', {}).get('account', {}).get('name')
            # The key is now 'dateTime' but handler renames it to 'transactedAt' for compatibility
            transacted_at_str = slip_data.get('transactedAt')
            if transacted_at_str:
                slip_transacted_at = datetime.fromisoformat(transacted_at_str.replace("Z", "+00:00")).strftime('%Y-%m-%d %H:%M:%S')

        now_utc = datetime.utcnow()
        sql_update_history = f"UPDATE rental_history SET return_date={self.paramstyle}, initiator={self.paramstyle}, amount_due={self.paramstyle}, payment_status={self.paramstyle}, transaction_ref={self.paramstyle}, slip_sender={self.paramstyle}, slip_receiver={self.paramstyle}, slip_transacted_at={self.paramstyle} WHERE item_id={self.paramstyle} AND return_date IS NULL"
        self.cursor.execute(
            sql_update_history,
            (now_utc, initiator, amount_due, 'pending' if amount_due > 0 else 'paid', transaction_ref, slip_sender, slip_receiver, slip_transacted_at, item_id)
        )
        self.conn.commit()

        # Get the ID of the just-updated history record
        # This is more reliable than assuming the last inserted ID.
        self.cursor.execute(f"SELECT id FROM rental_history WHERE item_id = {self.paramstyle} AND return_date = {self.paramstyle}", (item_id, now_utc))
        history_id_result = self.cursor.fetchone()
        history_id = history_id_result['id'] if history_id_result else -1

        db_signals.data_changed.emit('items')
        return history_id

    def confirm_return(self, item_id: int):
        """Admin confirms the physical return of an item."""
        if not self.cursor:
            return
        # Now, set the item as truly available
        sql = f"UPDATE items SET status='available', current_renter_id=NULL, renter_username=NULL, rent_date=NULL WHERE id={self.paramstyle}"
        self.cursor.execute(sql, (item_id,))
        self.conn.commit()
        db_signals.data_changed.emit('items')

    def get_rental_history_for_item(self, item_id):
        if not self.cursor:
            return []
        sql = f"""
            SELECT h.rent_date, h.return_date, u.username
            FROM rental_history h
            JOIN users u ON h.user_id = u.id
            WHERE h.item_id = {self.paramstyle}
            ORDER BY h.rent_date DESC
        """
        try:
            self.cursor.execute(sql, (item_id,))
            return self.cursor.fetchall()
        except psycopg2.Error:
            self.conn.rollback()
            return []

    def has_rented_items(self, user_id: int) -> bool:
        """Checks if a user has any items currently rented."""
        if not self.cursor:
            return False
        sql = f"SELECT 1 FROM items WHERE current_renter_id = {self.paramstyle} AND status = 'rented' LIMIT 1"
        try:
            self.cursor.execute(sql, (user_id,))
            return self.cursor.fetchone() is not None
        except psycopg2.Error:
            self.conn.rollback()
            return False

    def get_rented_items_by_user(self, user_id: int) -> list:
        """Fetches all items currently rented by a specific user."""
        if not self.cursor:
            return []
        sql = f"SELECT * FROM items WHERE current_renter_id = {self.paramstyle} AND status = 'rented' ORDER BY rent_date ASC"
        try:
            self.cursor.execute(sql, (user_id,))
            return self.cursor.fetchall()
        except psycopg2.Error:
            self.conn.rollback()
            return []

    def get_items_by_status(self, status: str, get_all_columns: bool = False, sort_by: str = 'name', sort_order: str = 'ASC') -> list:
        """Fetches all items with a specific status with sorting."""
        if not self.cursor:
            return []
        
        # Whitelist columns to prevent SQL injection
        allowed_sort_columns = {
            'name': 'name',
            'status': 'status',
            'rent_date': 'rent_date',
            'id': 'id',
            'fixed_fee': 'fixed_fee',
            'price_per_minute': 'price_per_minute'
        }
        # Whitelist sort orders
        allowed_sort_orders = ['ASC', 'DESC']

        sort_column = allowed_sort_columns.get(sort_by, 'name')
        order = sort_order.upper() if sort_order.upper() in allowed_sort_orders else 'ASC'

        # Special handling for rent_date to put NULLs last when sorting descending
        order_clause = f"ORDER BY CASE WHEN {sort_column} IS NULL THEN 1 ELSE 0 END, {sort_column} {order}"

        if get_all_columns:
            columns = "*"
        else:
            columns = "id, name"
        sql = f"SELECT {columns} FROM items WHERE status = {self.paramstyle} {order_clause}"
        try:
            self.cursor.execute(sql, (status,))
            return self.cursor.fetchall()
        except psycopg2.Error:
            self.conn.rollback()
            return []

    def get_payment_history_for_user(self, user_id):
        """Fetches all rental history records that have an amount due for a user."""
        if not self.cursor:
            return []
        sql = f"""
            SELECT h.id, h.rent_date, h.return_date, h.amount_due, h.payment_status, h.transaction_ref, i.name as item_name
            FROM rental_history h
            JOIN items i ON h.item_id = i.id
            WHERE h.user_id = {self.paramstyle} AND h.amount_due IS NOT NULL
            ORDER BY h.return_date DESC
        """
        try:
            self.cursor.execute(sql, (user_id,))
            return self.cursor.fetchall()
        except psycopg2.Error:
            self.conn.rollback()
            return []

    def has_pending_payments(self, user_id):
        """Checks if a user has any pending payments."""
        if not self.cursor:
            return False
        sql = f"SELECT 1 FROM rental_history WHERE user_id = {self.paramstyle} AND payment_status = 'pending' LIMIT 1"
        try:
            self.cursor.execute(sql, (user_id,))
            return self.cursor.fetchone() is not None
        except psycopg2.Error:
            self.conn.rollback()
            return False

    def get_all_pending_records(self):
        """Fetches all rental history records with a 'pending' status, joined with item and user info."""
        if not self.cursor:
            return []
        sql = """
            SELECT h.id, h.transaction_ref, h.amount_due, i.name as item_name, u.username
            FROM rental_history h
            JOIN items i ON h.item_id = i.id
            JOIN users u ON h.user_id = u.id
            WHERE h.payment_status = 'pending'
            ORDER BY h.return_date DESC
        """
        try:
            self.cursor.execute(sql)
            return self.cursor.fetchall()
        except psycopg2.Error:
            self.conn.rollback()
            return []

    def get_history_record_by_id(self, history_id: int):
        """Fetches a single rental history record by its ID."""
        if not self.cursor:
            return None
        try:
            sql = f"SELECT * FROM rental_history WHERE id = {self.paramstyle}"
            self.cursor.execute(sql, (history_id,))
            return self.cursor.fetchone()
        except psycopg2.Error:
            self.conn.rollback()
            return None

    def get_history_record_by_transaction_ref(self, transaction_ref: str):
        """Fetches a single rental history record by its transaction reference."""
        if not self.cursor:
            return None
        try:
            sql = f"SELECT * FROM rental_history WHERE transaction_ref = {self.paramstyle}"
            self.cursor.execute(sql, (transaction_ref,))
            return self.cursor.fetchone()
        except psycopg2.Error:
            self.conn.rollback()
            return None

    def update_payment_status(self, history_id, new_status, slip_data: dict | None = None, db_instance_for_email=None):
        """Updates the payment status of a specific history record."""
        if not self.cursor:
            return
        now_utc = datetime.utcnow() if new_status == 'paid' else None
        
        # Prepare base update
        update_parts = [f"payment_status={self.paramstyle}", f"payment_date={self.paramstyle}"] # type: ignore
        params = [new_status, now_utc]
        slip_data_json = None

        # If slip_data is provided, add its fields to the update
        if slip_data:
            slip_data_json = json.dumps(slip_data) # Convert dict to JSON string
            # Handle inconsistent sender key from API ('sender', 'seender', 'sendeer')
            sender_info = slip_data.get('sender') or slip_data.get('seender') or slip_data.get('sendeer') or {}
            sender_name = sender_info.get('account', {}).get('name')

            receiver_name = slip_data.get('receiver', {}).get('account', {}).get('name')
            transacted_at = slip_data.get('transactedAt')
            update_parts.extend([f"slip_sender={self.paramstyle}", f"slip_receiver={self.paramstyle}", f"slip_transacted_at={self.paramstyle}", f"slip_data_json={self.paramstyle}"])
            params.extend([sender_name, receiver_name, transacted_at, slip_data_json])

        sql = f"UPDATE rental_history SET {', '.join(update_parts)} WHERE id={self.paramstyle}"
        params.append(history_id)
        self.cursor.execute(sql, tuple(params))
        self.conn.commit()

        # --- Trigger automatic receipt email on successful payment ---
        # Pass the current db_instance and a fresh config instance to the email handler
        if new_status == 'paid':
            from app_payment.payment_handler import PaymentHandler
            # Emit a signal that a user's payment status has changed.
            # This is useful for UI elements that show pending payment indicators.
            db_signals.payment_status_updated.emit(self.get_history_record_by_id(history_id)['user_id'])
            # Also emit a generic data changed signal for the 'users' table,
            # as their payment status is a derived property. This helps refresh the UserManagementDialog.
            db_signals.data_changed.emit('users')
            db_signals.payment_status_updated.emit(self.get_history_record_by_id(history_id)['user_id'])
            # Use the provided db_instance for the email handler to ensure it uses the correct
            # connection, especially when called from a background thread like a webhook.
            db_for_email = db_instance_for_email if db_instance_for_email else self
            email_handler = PaymentHandler(db_instance=db_for_email)
            email_handler.send_receipt_email(history_id)
        
    def get_item_status_summary(self):
        """Counts items for each status and returns a dictionary."""
        if not self.cursor:
            return {}
        
        sql = "SELECT status, COUNT(*) as count FROM items GROUP BY status"
        try:
            self.cursor.execute(sql)
            results = self.cursor.fetchall()
            summary = {row['status']: row['count'] for row in results}
            return summary
        except psycopg2.Error as e: # Catch PostgreSQL specific errors
            logger.error(f"Error getting item status summary (PostgreSQL): {e}", exc_info=True)
            self.conn.rollback() # CRITICAL: Rollback the failed transaction
            return {}
        except Exception as e:
            logger.error(f"Error getting item status summary: {e}", exc_info=True)
            return {}

    def get_income_summary(self, start_date: str | None = None, end_date: str | None = None) -> dict:
        """
        Calculates income summary statistics for a given date range.
        Dates should be in 'YYYY-MM-DD' format.
        """
        if not self.cursor:
            return {}

        summary = {
            'total_paid': 0.0,
            'total_pending': 0.0,
            'total_waived': 0.0,
            'total_cash': 0.0,
            'total_transfer': 0.0,
        }

        # Base WHERE clause for date filtering
        where_clauses = []
        params = []
        if start_date:
            where_clauses.append(f"DATE(return_date) >= {self.paramstyle}")
            params.append(start_date)
        if end_date:
            where_clauses.append(f"DATE(return_date) <= {self.paramstyle}")
            params.append(end_date)
        
        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

        # --- FIX: Correctly build WHERE clauses ---
        queries = {
            'total_paid': f"SELECT SUM(amount_due) as total FROM rental_history {where_sql} {'AND' if where_sql else 'WHERE'} payment_status = 'paid'",
            'total_pending': f"SELECT SUM(amount_due) as total FROM rental_history {where_sql} {'AND' if where_sql else 'WHERE'} payment_status = 'pending'",
            'total_waived': f"SELECT SUM(amount_due) as total FROM rental_history {where_sql} {'AND' if where_sql else 'WHERE'} payment_status = 'waived'",
            'total_cash': f"SELECT SUM(amount_due) as total FROM rental_history {where_sql} {'AND' if where_sql else 'WHERE'} payment_status = 'paid' AND slip_data_json IS NULL AND transaction_ref IS NULL",
            'total_transfer': f"SELECT SUM(amount_due) as total FROM rental_history {where_sql} {'AND' if where_sql else 'WHERE'} payment_status = 'paid' AND (slip_data_json IS NOT NULL OR transaction_ref IS NOT NULL)",
        }

        try:
            for key, sql in queries.items():
                self.cursor.execute(sql, tuple(params))
                result = self.cursor.fetchone()
                summary[key] = float(result['total']) if result and result['total'] is not None else 0.0
            return summary
        except Exception as e:
            logger.error(f"Error getting income summary: {e}", exc_info=True)
            if self.conn: self.conn.rollback()
            return {}

    def get_all_payment_history_paginated(self, page: int, items_per_page: int, search_text: str | None = None, start_date: str | None = None, end_date: str | None = None, status_filter: str | None = None, sort_by: str = 'return_date', sort_order: str = 'DESC') -> tuple[list, int]:
        """Fetches all payment history records with pagination, search, and date filtering."""
        if not self.cursor:
            return [], 0

        where_clauses = ["h.amount_due IS NOT NULL"]
        params = []

        if search_text:
            search_pattern = f"%{search_text}%"
            where_clauses.append(f"(i.name LIKE {self.paramstyle} OR u.username LIKE {self.paramstyle} OR h.transaction_ref LIKE {self.paramstyle})")
            params.extend([search_pattern, search_pattern, search_pattern])
        if start_date:
            # --- FIX: Use dialect-specific date casting ---
            if isinstance(self.conn, sqlite3.Connection):
                where_clauses.append(f"DATE(h.return_date) >= {self.paramstyle}")
            else: # PostgreSQL
                where_clauses.append(f"h.return_date::date >= {self.paramstyle}")
            params.append(start_date)
        if end_date:
            if isinstance(self.conn, sqlite3.Connection):
                where_clauses.append(f"DATE(h.return_date) <= {self.paramstyle}")
            else: # PostgreSQL
                where_clauses.append(f"h.return_date::date <= {self.paramstyle}")
            params.append(end_date)
        if status_filter:
            if status_filter == 'transfer':
                where_clauses.append("(h.transaction_ref IS NOT NULL OR h.slip_data_json IS NOT NULL)")
            elif status_filter == 'cash':
                where_clauses.append("(h.transaction_ref IS NULL AND h.slip_data_json IS NULL)")
            else:
                where_clauses.append(f"h.payment_status = {self.paramstyle}")
                params.append(status_filter)

        allowed_sort_columns = {'return_date': 'h.return_date', 'amount_due': 'h.amount_due'}
        order_by_column = allowed_sort_columns.get(sort_by, 'h.return_date')

        where_sql = f"WHERE {' AND '.join(where_clauses)}"

        # Get total count
        count_sql = f"SELECT COUNT(h.id) as total_count FROM rental_history h JOIN items i ON h.item_id = i.id JOIN users u ON h.user_id = u.id {where_sql}"
        self.cursor.execute(count_sql, tuple(params))
        count_result = self.cursor.fetchone()
        # FIX: Access by column name 'total_count'
        total_count = count_result['total_count'] if count_result and count_result['total_count'] is not None else 0

        # Get paginated data
        offset = (page - 1) * items_per_page
        data_sql = f"""
            SELECT h.id, h.return_date, h.amount_due, h.payment_status, h.transaction_ref, i.name as item_name, u.username
            FROM rental_history h
            JOIN items i ON h.item_id = i.id
            JOIN users u ON h.user_id = u.id
            {where_sql}
            ORDER BY {order_by_column} {sort_order}
            LIMIT {self.paramstyle} OFFSET {self.paramstyle}
        """
        params.extend([items_per_page, offset])
        self.cursor.execute(data_sql, tuple(params))
        records = self.cursor.fetchall()

        return records, total_count

    def get_total_income(self) -> float:
        """Calculates the sum of all 'paid' transactions."""
        if not self.cursor:
            return 0.0
        
        sql = "SELECT SUM(amount_due) as total FROM rental_history WHERE payment_status = 'paid'"
        try:
            self.cursor.execute(sql)
            result = self.cursor.fetchone()
            return float(result['total']) if result and result['total'] is not None else 0.0
        except Exception as e:
            logger.error(f"Error getting total income: {e}", exc_info=True)
            if self.conn: self.conn.rollback()
            return 0.0

    def get_current_month_income(self) -> float:
        """Calculates the sum of 'paid' transactions for the current month."""
        if not self.cursor:
            return 0.0

        # Dialect-specific SQL for getting the current month
        if isinstance(self.conn, sqlite3.Connection): # SQLite
            # We need to adjust for the local timezone offset to get the correct month
            offset_hours = app_config.getint('TIME', 'utc_offset_hours', fallback=7)
            sql = f"SELECT SUM(amount_due) as total FROM rental_history WHERE payment_status = 'paid' AND strftime('%Y-%m', payment_date, '{offset_hours} hours') = strftime('%Y-%m', 'now', 'localtime')"
        else: # PostgreSQL
            # PostgreSQL's NOW() is timezone-aware, so this is simpler
            sql = "SELECT SUM(amount_due) as total FROM rental_history WHERE payment_status = 'paid' AND to_char(payment_date, 'YYYY-MM') = to_char(NOW(), 'YYYY-MM')"

        try:
            self.cursor.execute(sql)
            result = self.cursor.fetchone()
            return float(result['total']) if result and result['total'] is not None else 0.0
        except Exception as e:
            logger.error(f"Error getting current month income: {e}", exc_info=True)
            if self.conn: self.conn.rollback()
            return 0.0


# --- Global Instance Management ---

_local_instance: DBManagement | None = None
_remote_instance: DBManagement | None = None
_server_fernet: Fernet | None = None # Cache for the server-side fernet instance

def _get_server_fernet(db_instance: DBManagement) -> Fernet | None:
    """Fetches the server's master encryption key and returns a Fernet instance."""
    global _server_fernet
    if _server_fernet:
        return _server_fernet
    
    # Fetch the raw key bytes directly, avoiding recursive call to get_system_setting
    if not db_instance.cursor: return None
    sql = f"SELECT setting_value FROM system_settings WHERE setting_key = {db_instance.paramstyle}"
    db_instance.cursor.execute(sql, ('SYSTEM.encryption_key',))
    result = db_instance.cursor.fetchone()
    key_bytes = result['setting_value'] if result else None
    logger.debug(f"Fetched server master key. Key is present: {key_bytes is not None}")
    if key_bytes:
        _server_fernet = Fernet(key_bytes)
        return _server_fernet
    return None

def _get_and_cache_instance(is_remote: bool, force_reconnect: bool = False) -> DBManagement:
    """Internal factory function to create and cache DB instances."""
    global _local_instance, _remote_instance

    if is_remote:
        if force_reconnect and _remote_instance:
            _remote_instance.close_connection()
            _remote_instance = None
            logger.info("Forcing reconnection for remote instance.")
        if not _remote_instance:
            logger.info("Remote instance not found, creating a new one.")
            _remote_instance = DBManagement()
            _remote_instance._connect_remote()
        return _remote_instance
    else: # Local
        if force_reconnect and _local_instance:
            _local_instance.close_connection()
            _local_instance = None
            logger.info("Forcing reconnection for local instance.")
        if not _local_instance:
            logger.info("Local instance not found, creating a new one.")
            _local_instance = DBManagement()
            _local_instance._connect_local()
            _local_instance._create_local_tables()
        return _local_instance

def initialize_databases():
    """
    Global function to initialize database connections at startup.
    This is called once from main.py.
    """
    logger.info("Initializing database connections...")
    db_manager.initialize_connections()

def get_db_instance(is_remote: bool = False) -> DBManagement:
    """
    Global function to get the active DBManagement instance for a specific mode,
    This is the primary way other modules should get a database connection.
    """
    logger.debug(f"Requesting DB instance. is_remote={is_remote}")
    return _get_and_cache_instance(is_remote)

# The global db_manager is now primarily for orchestrating startup and shutdown.
# Other modules should prefer get_db_instance().
db_manager = DBManagement()
