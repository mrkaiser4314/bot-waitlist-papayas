import os
import threading
from api import app
from discord_waitlist_bot import run_bot
from database import init_db

print("="*50)
print("🚀 PAPAYAS TIERLIST - BOT + API")
print("="*50)

# ==========================
# VALIDAR VARIABLES
# ==========================
if not os.getenv("DATABASE_URL"):
    print("❌ Error: DATABASE_URL no configurado")
    exit(1)

if not os.getenv("DISCORD_TOKEN"):
    print("❌ Error: DISCORD_TOKEN no configurado")
    exit(1)

print("✅ Variables de entorno OK")

# ==========================
# INICIALIZAR DB
# ==========================
print("🗄 Inicializando base de datos...")
init_db()
print("✅ Base de datos lista")

# ==========================
# INICIAR API EN THREAD
# ==========================
def run_api():
    port = int(os.environ.get("PORT", 10000))
    print(f"🌐 Iniciando API en puerto {port}...")
    app.run(host="0.0.0.0", port=port)

api_thread = threading.Thread(target=run_api)
api_thread.daemon = True
api_thread.start()

print("✅ API iniciada en background")

# ==========================
# INICIAR BOT (HILO PRINCIPAL)
# ==========================
print("🎮 Iniciando bot Discord...")
run_bot()
