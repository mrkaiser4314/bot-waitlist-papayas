"""
API para Papayas Tierlist
Compatible con Render + Vercel (CORS arreglado)
"""

from flask import Flask, jsonify
from flask_cors import CORS
import os
import psycopg2

app = Flask(__name__)

# ✅ CORS CONFIGURADO PARA VERCEL
CORS(
    app,
    resources={r"/*": {"origins": "https://papaya-website-eight.vercel.app"}},
    supports_credentials=True
)

# 🔥 Forzar headers CORS (extra seguridad)
@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', 'https://papaya-website-eight.vercel.app')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,POST,OPTIONS')
    return response


# ===============================
# DATABASE
# ===============================

def get_db_connection():
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        return None
    try:
        return psycopg2.connect(
            database_url,
            sslmode="require"
        )
    except Exception as e:
        print("DB Error:", e)
        return None


# ===============================
# ROUTES
# ===============================

@app.route("/")
def home():
    return jsonify({
        "status": "online",
        "message": "Papayas Tierlist API",
    })


@app.route("/health")
def health():
    conn = get_db_connection()
    if not conn:
        return jsonify({"status": "error", "database": "disconnected"}), 500

    try:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM resultados")
        count = cur.fetchone()[0]
        conn.close()
        return jsonify({"status": "ok", "total_tests": count})
    except:
        conn.close()
        return jsonify({"status": "error"}), 500


@app.route("/api/rankings/<mode>")
def get_rankings(mode):

    conn = get_db_connection()
    if not conn:
        return jsonify({"mode": mode, "players": [], "total_players": 0})

    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT discord_id, nick_mc, discord_name,
                   tier_por_modalidad, puntos_por_modalidad,
                   puntos_totales, es_premium
            FROM jugadores
            ORDER BY puntos_totales DESC
        """)

        rows = cur.fetchall()
        players_list = []

        for row in rows:
            did, nick, dname, tiers_json, puntos_json, ptotal, premium = row

            mods = {}
            if tiers_json:
                for m, t in tiers_json.items():
                    p = puntos_json.get(m, 0) if puntos_json else 0
                    mods[m] = {
                        "tier": t,
                        "tier_display": t,
                        "puntos": p
                    }

            if mode != "overall" and mode not in mods:
                continue

            sort_points = ptotal if mode == "overall" else mods.get(mode, {}).get("puntos", 0)

            players_list.append({
                "id": did,
                "name": nick or dname,
                "points": ptotal or 0,
                "mode_points": sort_points,
                "es_premium": "si" if premium == "si" else "no",
                "modalidades": mods
            })

        if mode != "overall":
            players_list.sort(key=lambda x: x["mode_points"], reverse=True)

        conn.close()

        return jsonify({
            "mode": mode,
            "players": players_list,
            "total_players": len(players_list)
        })

    except Exception as e:
        conn.close()
        return jsonify({
            "mode": mode,
            "players": [],
            "total_players": 0,
            "error": str(e)
        }), 500


@app.route("/api/player/<discord_id>")
def get_player(discord_id):

    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "Database error"}), 500

    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT discord_id, nick_mc, discord_name,
                   tier_por_modalidad, puntos_por_modalidad,
                   puntos_totales, es_premium
            FROM jugadores
            WHERE discord_id = %s
        """, (discord_id,))

        row = cur.fetchone()
        if not row:
            conn.close()
            return jsonify({"error": "Player not found"}), 404

        did, nick, dname, tiers_json, puntos_json, ptotal, premium = row

        cur.execute("SELECT COUNT(*) + 1 FROM jugadores WHERE puntos_totales > %s", (ptotal,))
        pos = cur.fetchone()[0]

        tiers_dict = {}
        if tiers_json:
            for m, t in tiers_json.items():
                p = puntos_json.get(m, 0) if puntos_json else 0
                tiers_dict[m] = {"tier": t, "puntos": p}

        conn.close()

        return jsonify({
            "id": did,
            "nick": nick,
            "discord_name": dname,
            "position": pos,
            "total_points": ptotal or 0,
            "tiers": tiers_dict,
            "es_premium": premium
        })

    except Exception as e:
        conn.close()
        return jsonify({"error": str(e)}), 500


@app.route("/api/stats")
def get_stats():

    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "Database error"}), 500

    try:
        cur = conn.cursor()

        cur.execute("SELECT COUNT(*) FROM resultados")
        total_tests = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM jugadores")
        total_players = cur.fetchone()[0]

        conn.close()

        return jsonify({
            "total_tests": total_tests,
            "total_players": total_players
        })

    except Exception as e:
        conn.close()
        return jsonify({"error": str(e)}), 500
