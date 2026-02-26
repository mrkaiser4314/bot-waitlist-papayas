"""
MAIN - Ejecuta Bot Discord + API Flask simultáneamente
Compatible con discord_waitlist_bot.py existente
"""

import os
import threading
import time

print("="*50)
print("🚀 PAPAYAS TIERLIST - BOT + API")
print("="*50)

# ============================================
# VALIDAR VARIABLES DE ENTORNO
# ============================================

if not os.getenv('DISCORD_TOKEN'):
    print("❌ Error: DISCORD_TOKEN no configurado")
    exit(1)

if not os.getenv('DATABASE_URL'):
    print("❌ Error: DATABASE_URL no configurado")
    exit(1)

print("✅ Variables de entorno OK\n")

# ============================================
# FUNCIÓN PARA CORRER API
# ============================================

def run_api():
    """Corre Flask API en thread separado"""
    port = int(os.getenv('PORT', 10000))
    print(f"🌐 Iniciando API en puerto {port}...")
    
    from api import app
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

# ============================================
# FUNCIÓN PARA CORRER BOT
# ============================================

def run_bot():
    """Corre Discord Bot importando el módulo completo"""
    print("🤖 Iniciando Discord Bot...")
    
    # Importar el bot (esto ejecuta todo el código del módulo)
    # El bot se ejecutará automáticamente porque tiene bot.run() al final
    import discord_waitlist_bot

# ============================================
# MAIN - INICIAR AMBOS SERVICIOS
# ============================================

if __name__ == '__main__':
    try:
        # Iniciar API en thread separado (daemon=True para que muera con el programa)
        print("📡 Lanzando API en background...\n")
        api_thread = threading.Thread(target=run_api, daemon=True, name="API-Thread")
        api_thread.start()
        
        # Esperar un poco para que API inicie
        time.sleep(3)
        print("✅ API iniciada correctamente\n")
        
        # Iniciar bot en el main thread (esto bloquea y mantiene el proceso vivo)
        print("🎮 Iniciando Discord Bot (esto mantiene el proceso activo)...\n")
        run_bot()
        
    except KeyboardInterrupt:
        print("\n\n🛑 Apagando servicios...")
        exit(0)
    except Exception as e:
        print(f"\n❌ Error fatal: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
