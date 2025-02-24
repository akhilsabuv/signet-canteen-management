import pyodbc

conn_str = (
    "DRIVER={ODBC Driver 17 for SQL Server};"
    "SERVER=localhost,1433;"
    "DATABASE=signet_log;"
    "UID=akhil;"
    "PWD=Asv123456"
)

try:
    conn = pyodbc.connect(conn_str, timeout=5)
    print("Connection successful!")
    conn.close()
except Exception as e:
    print("Connection error:", e)
