# auth.py -- SQLite-based authentication with salted password hashing
"""
User authentication and registration service for AgriCare.
Uses SQLite for persistent storage and bcrypt (with hashlib fallback) for salted password hashing.
"""

import os
import sqlite3
import hashlib
from datetime import datetime
from typing import Tuple, Optional

try:
    import bcrypt
    HAS_BCRYPT = True
except ImportError:
    HAS_BCRYPT = False

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "users.db")


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Initialize the SQLite database and create users table if not exists."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                phone TEXT,
                created_at TEXT NOT NULL
            )
        """)
        conn.commit()

        # Seed default admin user if not present (allows existing tests/admin to work)
        cursor.execute("SELECT id FROM users WHERE username = ?", ("admin",))
        if cursor.fetchone() is None:
            admin_hash = hash_password("admin123")
            cursor.execute(
                "INSERT INTO users (username, password_hash, phone, created_at) VALUES (?, ?, ?, ?)",
                ("admin", admin_hash, "9999999999", datetime.now().isoformat())
            )
            conn.commit()


def hash_password(password: str) -> str:
    """Hash password using bcrypt or SHA-256 with salt."""
    if HAS_BCRYPT:
        salt = bcrypt.gensalt()
        return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")
    else:
        salt = "agricare_maharashtra_salt_"
        return "sha256$" + hashlib.sha256((salt + password).encode("utf-8")).hexdigest()


def verify_password(password: str, hashed: str) -> bool:
    """Verify plain password against stored hash."""
    if not hashed:
        return False
    if hashed.startswith("sha256$"):
        salt = "agricare_maharashtra_salt_"
        expected = "sha256$" + hashlib.sha256((salt + password).encode("utf-8")).hexdigest()
        return hashed == expected
    if HAS_BCRYPT:
        try:
            return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
        except Exception:
            return False
    return False


def register_user(username: str, password: str, phone: str = "") -> Tuple[bool, str]:
    """
    Register a new user account.
    Returns (success, message).
    """
    username = username.strip()
    password = password.strip()
    phone = phone.strip()

    if len(username) < 3:
        return False, "Username must be at least 3 characters."
    if len(password) < 4:
        return False, "Password must be at least 4 characters."

    pwd_hash = hash_password(password)

    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO users (username, password_hash, phone, created_at) VALUES (?, ?, ?, ?)",
                (username, pwd_hash, phone, datetime.now().isoformat())
            )
            conn.commit()
            return True, "Registration successful! You can now log in."
    except sqlite3.IntegrityError:
        return False, "Username or phone already registered."
    except Exception as e:
        return False, f"Registration failed: {str(e)}"


def authenticate_user(username: str, password: str) -> bool:
    """Authenticate username and password against SQLite database."""
    username = username.strip()
    password = password.strip()

    if not username or not password:
        return False

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT password_hash FROM users WHERE username = ?", (username,))
        row = cursor.fetchone()
        if row:
            return verify_password(password, row["password_hash"])
        return False


# Auto-initialize database on module import
init_db()
