import os
import sqlite3

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
DB_PATH = os.path.join(PROJECT_ROOT, "rfp.db")
SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "schema.sql")


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    with open(SCHEMA_PATH) as f:
        schema = f.read()
    conn = get_connection()
    conn.executescript(schema)
    conn.commit()
    conn.close()


def insert_dish(name, category, description):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT OR IGNORE INTO dishes (name, category, description) VALUES (?, ?, ?)",
        (name, category, description),
    )
    conn.commit()
    cur.execute("SELECT id FROM dishes WHERE name = ?", (name,))
    row = cur.fetchone()
    conn.close()
    return row["id"] if row else None


def insert_ingredient(name):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("INSERT OR IGNORE INTO ingredients (name) VALUES (?)", (name,))
    conn.commit()
    cur.execute("SELECT id FROM ingredients WHERE name = ?", (name,))
    row = cur.fetchone()
    conn.close()
    return row["id"] if row else None


def insert_dish_ingredient(dish_id, ingredient_id, quantity, unit, notes):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO dish_ingredients (dish_id, ingredient_id, quantity, unit, notes)
           VALUES (?, ?, ?, ?, ?)""",
        (dish_id, ingredient_id, quantity, unit, notes),
    )
    conn.commit()
    conn.close()


def get_all_dishes():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM dishes ORDER BY category, name")
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_dish_ingredients(dish_id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """SELECT i.name, di.quantity, di.unit, di.notes
           FROM dish_ingredients di
           JOIN ingredients i ON di.ingredient_id = i.id
           WHERE di.dish_id = ?""",
        (dish_id,),
    )
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def insert_ingredient_pricing(
    ingredient_id, commodity, price_per_lb, original_price, original_unit,
    market, report_title, report_date, no_data_reason
):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO ingredient_pricing
           (ingredient_id, commodity, price_per_lb, original_price, original_unit,
            market, report_title, report_date, no_data_reason)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (ingredient_id, commodity, price_per_lb, original_price, original_unit,
         market, report_title, report_date, no_data_reason),
    )
    conn.commit()
    conn.close()


def get_all_ingredient_pricing():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """SELECT i.name, ip.commodity, ip.price_per_lb, ip.original_price,
                  ip.original_unit, ip.market, ip.report_date, ip.no_data_reason
           FROM ingredient_pricing ip
           JOIN ingredients i ON ip.ingredient_id = i.id
           ORDER BY i.name"""
    )
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def clear_ingredient_pricing():
    conn = get_connection()
    conn.execute("DELETE FROM ingredient_pricing")
    conn.commit()
    conn.close()


def pricing_already_fetched():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) as cnt FROM ingredient_pricing")
    row = cur.fetchone()
    conn.close()
    return row["cnt"] > 0


def insert_rfp_email(distributor_id, to_email, subject, body, status, sent_at):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO rfp_emails (distributor_id, to_email, subject, body, status, sent_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (distributor_id, to_email, subject, body, status, sent_at),
    )
    row_id = cur.lastrowid
    conn.commit()
    conn.close()
    return row_id


def update_rfp_email_status(email_id, status, sent_at=None):
    conn = get_connection()
    conn.execute(
        "UPDATE rfp_emails SET status = ?, sent_at = ? WHERE id = ?",
        (status, sent_at, email_id),
    )
    conn.commit()
    conn.close()


def get_ingredients_with_categories():
    """
    Returns all ingredients joined with their USDA category.
    Category is derived from report_title (e.g. 'USDA AMS Report 2307 — Vegetables' → 'vegetables').
    Ingredients with no pricing data default to category 'none'.
    """
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """SELECT i.id, i.name, ip.report_title, ip.commodity
           FROM ingredients i
           LEFT JOIN ingredient_pricing ip ON ip.ingredient_id = i.id
           ORDER BY i.name"""
    )
    rows = cur.fetchall()
    conn.close()
    result = []
    for r in rows:
        row = dict(r)
        if row.get("report_title"):
            parts = row["report_title"].split(" — ")
            row["category"] = parts[-1].lower() if len(parts) >= 2 else "none"
        else:
            row["category"] = "none"
        result.append(row)
    return result


def get_all_rfp_emails():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """SELECT r.id, d.name as distributor_name, r.to_email, r.subject,
                  r.status, r.sent_at
           FROM rfp_emails r
           JOIN distributors d ON r.distributor_id = d.id
           ORDER BY r.sent_at DESC"""
    )
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def clear_rfp_emails():
    conn = get_connection()
    conn.execute("DELETE FROM rfp_emails")
    conn.commit()
    conn.close()


def insert_distributor(name, specialty, address, city, state, phone, email, website, notes):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """INSERT OR IGNORE INTO distributors
           (name, specialty, address, city, state, phone, email, website, notes)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (name, specialty, address, city, state, phone, email, website, notes),
    )
    conn.commit()
    conn.close()


def get_all_distributors():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM distributors ORDER BY name")
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def clear_distributors():
    conn = get_connection()
    conn.execute("DELETE FROM rfp_emails")   # clear dependent records first
    conn.execute("DELETE FROM distributors")
    conn.commit()
    conn.close()


def get_all_ingredients():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM ingredients ORDER BY name")
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]
