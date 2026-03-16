# update_admin.py
import sqlite3

# Conectar ao banco
conn = sqlite3.connect('autoanalytics.db')
cursor = conn.cursor()

# Atualizar para admin
cursor.execute("UPDATE users SET is_admin = 1 WHERE email = 'joaoguilherme192561@gmail.com'")
conn.commit()

# Verificar
cursor.execute("SELECT email, is_admin FROM users WHERE email = 'joaoguilherme192561@gmail.com'")
resultado = cursor.fetchone()
print(f"Email: {resultado[0]}, is_admin: {resultado[1]}")

conn.close()