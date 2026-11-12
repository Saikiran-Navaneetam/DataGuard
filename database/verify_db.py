
from database.connection import get_connection

connection = get_connection()

tables = connection.execute("""
    SELECT name
    FROM sqlite_master
    WHERE type = 'table'
    AND name NOT LIKE 'sqlite_%'
    ORDER BY name
""").fetchall()

print("\nDATA GUARD DATABASE VERIFICATION")
print("-" * 40)

for table in tables:
    print(f"[OK] {table['name']}")

print("-" * 40)
print(f"Total tables created: {len(tables)}")

connection.close()
