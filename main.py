"""
MAIN - Ejecuta Bot Discord + API Flask simultáneamente
Optimizado para Render
"""

import os
import threading
import time
from database import init_database

PORT = int(os.getenv("PORT", 10000))


def run_api():
    """Corre Flask API en thread separado"""
    print(f"🌐 Iniciando API en puerto {PORT}...")
    from api import app as flask_app
    flask_app.run(
        host="0.0.0.0",
        port=PORT,
        debug=False,
        use_reloader=False
    )


def run_bot():
    """Corre Discord Bot"""
    print("🤖 Iniciando Discord Bot...")
    import discord_waitlist_bot  # esto lo deja bloqueante


if __name__ == "__main__":
    print("=" * 50)
    print("🚀 PAPAYAS TIERLIST - BOT + API")
    print("=" * 50)

    # Verificar variables obligatorias
    if not os.getenv("DISCORD_TOKEN"):
        print("❌ Error: DISCORD_TOKEN no configurado")
        exit(1)

    if not os.getenv("DATABASE_URL"):
        print("❌ Error: DATABASE_URL no configurado")
        exit(1)

    print("✅ Variables de entorno OK")

    # Inicializar base de datos
    print("🗄 Inicializando base de datos...")
    if not init_database():
        print("❌ No se pudo inicializar la base de datos")
        exit(1)

    print("✅ Base de datos lista")

    # Iniciar API en background
    api_thread = threading.Thread(target=run_api, daemon=True)
    api_thread.start()

    time.sleep(2)
    print("✅ API iniciada en background")

    # Iniciar bot (mantiene vivo el proceso)
    print("🎮 Iniciando bot Discord...")
    run_bot()
