"""
Módulo de base de datos PostgreSQL para Papayas Tierlist
Guarda resultados en PostgreSQL para persistencia permanente
"""

import psycopg2
import os
import json
from datetime import datetime

def get_db_connection():
    """Obtiene conexión a PostgreSQL usando DATABASE_URL de Railway"""
    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        print("❌ No se encontró DATABASE_URL")
        return None
    
    try:
        conn = psycopg2.connect(database_url)
        return conn
    except Exception as e:
        print(f"❌ Error conectando a PostgreSQL: {e}")
        return None

def init_database():
    """Inicializa las tablas de la base de datos"""
    conn = get_db_connection()
    if not conn:
        return False
    
    try:
        cur = conn.cursor()
        
        # Tabla de resultados (lo MÁS IMPORTANTE)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS resultados (
                id SERIAL PRIMARY KEY,
                nick_mc VARCHAR(100),
                jugador_id VARCHAR(50) NOT NULL,
                jugador_name VARCHAR(100),
                tester_id VARCHAR(50) NOT NULL,
                tester_name VARCHAR(100),
                modalidad VARCHAR(50),
                tier_antiguo VARCHAR(10),
                tier_nuevo VARCHAR(10),
                puntos_obtenidos INTEGER,
                puntos_totales INTEGER,
                fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Tabla de jugadores
        cur.execute("""
            CREATE TABLE IF NOT EXISTS jugadores (
                discord_id VARCHAR(50) PRIMARY KEY,
                nick_mc VARCHAR(100),
                discord_name VARCHAR(100),
                tier_por_modalidad JSONB,
                puntos_por_modalidad JSONB,
                puntos_totales INTEGER DEFAULT 0,
                es_premium VARCHAR(10)
            )
        """)
        
        # Tabla de cooldowns
        cur.execute("""
            CREATE TABLE IF NOT EXISTS cooldowns (
                id SERIAL PRIMARY KEY,
                jugador_id VARCHAR(50) NOT NULL,
                modalidad VARCHAR(50) NOT NULL,
                start_date TIMESTAMP,
                end_date TIMESTAMP,
                UNIQUE(jugador_id, modalidad)
            )
        """)
        
        conn.commit()
        print("✅ Base de datos inicializada correctamente")
        return True
        
    except Exception as e:
        print(f"❌ Error inicializando base de datos: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

def add_resultado(resultado_data):
    """Añade un resultado a la base de datos"""
    conn = get_db_connection()
    if not conn:
        return False
    
    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO resultados 
            (nick_mc, jugador_id, jugador_name, tester_id, tester_name, 
             modalidad, tier_antiguo, tier_nuevo, puntos_obtenidos, puntos_totales, fecha)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            resultado_data['nick_mc'],
            resultado_data['jugador_id'],
            resultado_data['jugador_name'],
            resultado_data['tester_id'],
            resultado_data['tester_name'],
            resultado_data['modalidad'],
            resultado_data['tier_antiguo'],
            resultado_data['tier_nuevo'],
            resultado_data['puntos_obtenidos'],
            resultado_data['puntos_totales'],
            datetime.fromisoformat(resultado_data['fecha']) if 'fecha' in resultado_data else datetime.now()
        ))
        conn.commit()
        return True
    except Exception as e:
        print(f"❌ Error añadiendo resultado: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

def get_all_resultados():
    """Obtiene todos los resultados"""
    conn = get_db_connection()
    if not conn:
        return []
    
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT nick_mc, jugador_id, jugador_name, tester_id, tester_name,
                   modalidad, tier_antiguo, tier_nuevo, puntos_obtenidos, 
                   puntos_totales, fecha
            FROM resultados
            ORDER BY fecha DESC
        """)
        
        rows = cur.fetchall()
        resultados = []
        for row in rows:
            resultados.append({
                'nick_mc': row[0],
                'jugador_id': row[1],
                'jugador_name': row[2],
                'tester_id': row[3],
                'tester_name': row[4],
                'modalidad': row[5],
                'tier_antiguo': row[6],
                'tier_nuevo': row[7],
                'puntos_obtenidos': row[8],
                'puntos_totales': row[9],
                'fecha': row[10].isoformat() if row[10] else None
            })
        
        return resultados
    except Exception as e:
        print(f"❌ Error obteniendo resultados: {e}")
        return []
    finally:
        conn.close()

def delete_tester_resultados(tester_id):
    """Elimina todos los resultados de un tester"""
    conn = get_db_connection()
    if not conn:
        return 0
    
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM resultados WHERE tester_id = %s", (tester_id,))
        deleted = cur.rowcount
        conn.commit()
        return deleted
    except Exception as e:
        print(f"❌ Error eliminando resultados: {e}")
        conn.rollback()
        return 0
    finally:
        conn.close()

def get_tester_stats():
    """Obtiene estadísticas de testers para /toptester"""
    conn = get_db_connection()
    if not conn:
        return {}
    
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT tester_id, tester_name, COUNT(*) as tests
            FROM resultados
            GROUP BY tester_id, tester_name
            ORDER BY tests DESC
        """)
        
        rows = cur.fetchall()
        stats = {}
        for row in rows:
            stats[row[0]] = {
                'name': row[1],
                'count': row[2]
            }
        
        return stats
    except Exception as e:
        print(f"❌ Error obteniendo stats: {e}")
        return {}
    finally:
        conn.close()
