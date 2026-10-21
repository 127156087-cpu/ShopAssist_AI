"""SQLite business database: schema, seed data and small query helpers."""
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

from src.shopassist import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS customers (customer_id TEXT PRIMARY KEY, name TEXT NOT NULL, email TEXT);
CREATE TABLE IF NOT EXISTS orders (
  order_id TEXT PRIMARY KEY, customer_id TEXT NOT NULL REFERENCES customers(customer_id),
  product_name TEXT, amount REAL, order_status TEXT, tracking_status TEXT,
  delivery_date TEXT, estimated_delivery TEXT);
CREATE TABLE IF NOT EXISTS policies (
  category TEXT PRIMARY KEY, rule_description TEXT, return_window_days INTEGER, approval_required INTEGER);
CREATE TABLE IF NOT EXISTS tickets (
  ticket_id TEXT PRIMARY KEY, customer_id TEXT NOT NULL, order_id TEXT NOT NULL, thread_id TEXT NOT NULL,
  category TEXT, priority TEXT, description TEXT, requested_action TEXT, findings TEXT,
  status TEXT NOT NULL, resolution TEXT, created_at TEXT, updated_at TEXT);
CREATE TABLE IF NOT EXISTS actions (   -- idempotency: one row per (ticket, action)
  action_id TEXT PRIMARY KEY, ticket_id TEXT, type TEXT, status TEXT, result TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS events (    -- kind='audit' = ticket timeline, kind='workflow' = live monitor
  id INTEGER PRIMARY KEY AUTOINCREMENT, thread_id TEXT, ticket_id TEXT, kind TEXT,
  node TEXT, status TEXT, message TEXT, created_at TEXT);
"""


def _connect():
    Path(config.DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(config.DB_PATH, timeout=10)
    connection.row_factory = sqlite3.Row
    return connection


def query(sql: str, args=(), one: bool = False):
    connection = _connect()
    try:
        rows = [dict(row) for row in connection.execute(sql, args).fetchall()]
    finally:
        connection.close()
    return (rows[0] if rows else None) if one else rows


def run(sql: str, args=()):
    connection = _connect()
    try:
        with connection:
            return connection.execute(sql, args).lastrowid
    finally:
        connection.close()


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def log_event(thread_id, ticket_id, node, status, message="", kind="workflow") -> None:
    #placeholders to prevent injection attacks
    run("INSERT INTO events (thread_id, ticket_id, kind, node, status, message, created_at) VALUES (?,?,?,?,?,?,?)",
        (thread_id, ticket_id, kind, node, status, message, now()))


def init_db() -> None:
    """Create the tables and, on first run, the demo customers, orders and policies."""
    connection = _connect()
    connection.executescript(SCHEMA)
    connection.commit()
    connection.close()
    if query("SELECT 1 FROM customers LIMIT 1"):
        return

    day = lambda offset: (date.today() + timedelta(days=offset)).isoformat()
    run("INSERT INTO customers VALUES ('C101','Asha','asha@example.com')")
    run("INSERT INTO customers VALUES ('C102','Ravi','ravi@example.com')")

    orders = [  # id, customer, product, amount, status, tracking, delivered, estimated
        ("ORD1024", "C101", "Wireless Headphones", 2499, "DELIVERED", "Delivered", day(-5), None),   # refund-eligible
        ("ORD1025", "C101", "Smart Watch", 8999, "DELIVERED", "Delivered", day(-60), None),           # outside every window
        ("ORD1026", "C101", "Backpack", 1299, "SHIPPED", "In transit", None, day(2)),                 # too late to cancel
        ("ORD1027", "C102", "Running Shoes", 3499, "PLACED", "Order confirmed", None, day(5)),        # can be cancelled
        ("ORD1028", "C102", "Desk Lamp", 1799, "CANCELLED", "Cancelled", None, None),
    ]
    for order in orders:
        run("INSERT INTO orders VALUES (?,?,?,?,?,?,?,?)", order)

    policies = [  # category, description, window in days, approval required
        ("refund", "Refunds are available within 30 days of delivery. Support approval is required.", 30, 1),
        ("return", "Items can be returned within 15 days of delivery. Support approval is required.", 15, 1),
        ("replacement", "Replacements for damaged or defective items are available within 30 days of delivery. Support approval is required.", 30, 1),
        ("cancellation", "Orders can be cancelled before they ship. Cancellations are approved automatically.", 0, 0),
    ]
    for policy in policies:
        run("INSERT INTO policies VALUES (?,?,?,?)", policy)


def reset_db() -> None:
    """Delete the database and rebuild it from the seed data (used by the evaluation)."""
    Path(config.DB_PATH).unlink(missing_ok=True)
    init_db()
