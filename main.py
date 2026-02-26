"""
MAIN - Ejecuta Bot Discord + API Flask simultáneamente
Este archivo arranca ambos servicios en el mismo proceso
"""

import os
import threading
import time

# ============================================
# CONFIGURACIÓN
# ============================================

PORT = int(os.getenv('PORT', 10000))

# ============================================
# FUNCIÓN PARA CORRER API
# ============================================

def run_api():
    """Corre Flask API en thread separado"""
    print(f"🌐 Iniciando API en puerto {PORT}...")
    from api import app as flask_app
    flask_app.run(host='0.0.0.0', port=PORT, debug=False, use_reloader=False)

# ============================================
# FUNCIÓN PARA CORRER BOT
# ============================================

def run_bot():
    """Corre Discord Bot"""
    print("🤖 Iniciando Discord Bot...")
    import discord_waitlist_bot

# ============================================
# MAIN - INICIAR AMBOS SERVICIOS
# ============================================

if __name__ == '__main__':
    print("=" * 50)
    print("🚀 PAPAYAS TIERLIST - BOT + API")
    print("=" * 50)
    
    # Verificar variables de entorno
    if not os.getenv('DISCORD_TOKEN'):
        print("❌ Error: DISCORD_TOKEN no configurado")
        exit(1)
    
    if not os.getenv('DATABASE_URL'):
        print("❌ Error: DATABASE_URL no configurado")
        exit(1)
    
    print("✅ Variables de entorno OK")
    
    # Iniciar API en thread separado (daemon)
    api_thread = threading.Thread(target=run_api, daemon=True, name="API-Thread")
    api_thread.start()
    
    # Esperar un poco para que API inicie
    time.sleep(2)
    print("✅ API iniciada en background")
    
    # Iniciar bot en el main thread (bloqueante)
    print("🎮 Iniciando bot Discord (esto mantiene el proceso activo)...")
    run_bot()
