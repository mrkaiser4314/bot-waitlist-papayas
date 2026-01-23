import discord
from discord import app_commands
from discord.ext import commands, tasks
import json
import os
from datetime import datetime, timedelta
import asyncio

import requests
import zipfile
import io

# Importar módulo de base de datos PostgreSQL
try:
    import database
    POSTGRESQL_AVAILABLE = True
    print("✅ Módulo PostgreSQL importado")
except ImportError:
    POSTGRESQL_AVAILABLE = False
    print("⚠️ PostgreSQL no disponible, usando solo memoria")

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix='/', intents=intents)

# IDs de roles por tier
TIER_ROLES = {
    'LT5': 1459287994119753748,
    'HT5': 1459288022792278097,
    'LT4': 1459288127691554967,
    'HT4': 1459288051254694126,
    'LT3': 1459288151796486301,
    'HT3': 1459288170985160704,
    'LT2': 1459288188802826382,
    'HT2': 1459288204531466332,
    'LT1': 1459288232306151566,
    'HT1': 1459288252606447831
}

TESTER_ROLE_ID = 1459287018746941615

TIER_POINTS = {
    'LT5': 1, 'HT5': 2,
    'LT4': 3, 'HT4': 4,
    'LT3': 5, 'HT3': 6,
    'LT2': 7, 'HT2': 8,
    'LT1': 9, 'HT1': 10
}

GAME_MODES = ['Mace', 'Sword', 'UHC', 'Crystal', 'NethOP', 'SMP', 'Axe', 'Dpot']

MODE_EMOJIS = {
    'Mace': '🔨',
    'Sword': '⚔️',
    'UHC': '❤️',
    'Crystal': '💎',
    'NethOP': '🧪',
    'SMP': '🪓',
    'Axe': '🪓',
    'Dpot': '🧪'
}

DATA_FILE = '/data/waitlist_data.json' if os.path.exists('/data') else 'waitlist_data.json'
COOLDOWN_DAYS = 10
MAX_QUEUE_SIZE = 20

def create_initial_data():
    return {
        'waitlists': {mode: {'active': False, 'queue': [], 'testers': []} for mode in GAME_MODES},
        'jugadores': {},
        'resultados': [],
        'castigos': [],
        'tickets': {},
        'cooldowns': {},
        'bans_temporales': {},
        'panel_messages': {},
        'config': {
            'ticket_category_id': None,
            'ticket_logs_channel_id': 1459298622930813121,  # Canal para logs de tickets
            'resultado_channel_id': 1459289305414635560      # Canal para resultados
        }
    }

def load_data():
    if not os.path.exists(DATA_FILE):
        print(f"⚠️ {DATA_FILE} no existe, creando nuevo...")
        initial_data = create_initial_data()
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(initial_data, f, indent=2, ensure_ascii=False)
        print(f"✅ {DATA_FILE} creado exitosamente")
        return initial_data
    
    try:
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            if 'waitlists' not in data:
                data['waitlists'] = {mode: {'active': False, 'queue': [], 'testers': []} for mode in GAME_MODES}
            if 'jugadores' not in data:
                data['jugadores'] = {}
            if 'cooldowns' not in data:
                data['cooldowns'] = {}
            if 'bans_temporales' not in data:
                data['bans_temporales'] = {}
            if 'resultados' not in data:
                data['resultados'] = []
            if 'castigos' not in data:
                data['castigos'] = []
            if 'tickets' not in data:
                data['tickets'] = {}
            if 'panel_messages' not in data:
                data['panel_messages'] = {}
            if 'config' not in data:
                data['config'] = {
                    'ticket_category_id': None,
                    'ticket_logs_channel_id': 1459298622930813121,
                    'resultado_channel_id': 1459289305414635560
                }
            # Migrar log_channel_id antiguo a ticket_logs_channel_id
            if 'log_channel_id' in data['config'] and 'ticket_logs_channel_id' not in data['config']:
                data['config']['ticket_logs_channel_id'] = data['config']['log_channel_id']
            # Agregar resultado_channel_id si no existe
            if 'resultado_channel_id' not in data['config']:
                data['config']['resultado_channel_id'] = 1459289305414635560
            return data
    except Exception as e:
        print(f"❌ Error cargando {DATA_FILE}: {e}")
        initial_data = create_initial_data()
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(initial_data, f, indent=2, ensure_ascii=False)
        return initial_data

def save_data():
    try:
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"❌ Error guardando datos: {e}")

data = load_data()


# === TICKET MESSAGE LOGGER ===
ticket_logs = {}  # {channel_id: [messages]}

@bot.event
async def on_ready():
    print('=' * 50)
    print(f'✅ Bot conectado como {bot.user}')
    print(f'📁 Archivo de datos: {DATA_FILE}')
    
    # Inicializar PostgreSQL
    if POSTGRESQL_AVAILABLE:
        print('🔧 Inicializando PostgreSQL...')
        if database.init_database():
            print('✅ PostgreSQL inicializado correctamente')
            # Cargar datos existentes a memoria
            resultados_db = database.get_all_resultados()
            if resultados_db:
                print(f'📊 Cargados {len(resultados_db)} resultados desde PostgreSQL')
        else:
            print('⚠️ PostgreSQL no pudo inicializarse, usando solo memoria')
    
    print(f'👥 Jugadores: {len(data.get("jugadores", {}))}')
    print(f'⏰ Cooldowns activos: {len(data.get("cooldowns", {}))}')
    print(f'⛔ Bans temporales: {len(data.get("bans_temporales", {}))}')
    print('=' * 50)
    
    # Iniciar tareas periódicas
    check_cooldowns.start()
    check_temp_bans.start()
    
    try:
        # Sincronización global (puede tardar hasta 1 hora)
        synced = await bot.tree.sync()
        print(f'🔄 Sincronizados {len(synced)} comandos globalmente')
        
        # Si quieres sincronización instantánea en tu servidor específico:
        # Descomenta las siguientes 3 líneas y pon tu SERVER_ID
        # SERVER_ID = 1234567890  # Reemplaza con el ID de tu servidor
        # await bot.tree.sync(guild=discord.Object(id=SERVER_ID))
        # print(f'⚡ Sincronización instantánea en servidor {SERVER_ID}')
    except Exception as e:
        print(f'❌ Error al sincronizar: {e}')

@bot.event
async def on_message(message):
    """Log messages in tickets"""
    if message.channel.id in ticket_logs:
        ticket_logs[message.channel.id].append({
            'author': str(message.author),
            'content': message.content,
            'timestamp': message.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            'attachments': [att.url for att in message.attachments]
        })
    
    await bot.process_commands(message)

@bot.event
async def on_thread_create(thread):
    """Cuando se crea un ticket, empieza a logear"""
    if thread.parent and "ticket" in thread.name.lower():
        ticket_logs[thread.id] = []
        print(f"📝 Iniciando log para ticket: {thread.name}")

@bot.event
async def on_thread_delete(thread):
    """Cuando se cierra un ticket, genera log .zip"""
    
    if thread.id in ticket_logs:
        # Crear archivo .txt con los mensajes
        log_content = f"TICKET LOG - {thread.name}\n"
        log_content += f"Creado: {thread.created_at}\n"
        log_content += f"Cerrado: {datetime.now()}\n"
        log_content += "=" * 50 + "\n\n"
        
        for msg in ticket_logs[thread.id]:
            log_content += f"[{msg['timestamp']}] {msg['author']}:\n"
            log_content += f"{msg['content']}\n"
            if msg['attachments']:
                log_content += f"Adjuntos: {', '.join(msg['attachments'])}\n"
            log_content += "\n"
        
        # Crear .zip
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            zip_file.writestr(f"{thread.name}.txt", log_content)
        
        zip_buffer.seek(0)
        
        # Enviar a canal de TICKET logs
        ticket_logs_channel_id = data.get('config', {}).get('ticket_logs_channel_id', 1459298622930813121)
        logs_channel = bot.get_channel(ticket_logs_channel_id)
        
        if logs_channel:
            await logs_channel.send(
                content=f"📁 Log del ticket **{thread.name}**",
                file=discord.File(zip_buffer, filename=f"{thread.name}_log.zip")
            )
        
        # Limpiar del dict
        del ticket_logs[thread.id]

@tasks.loop(hours=1)
async def check_cooldowns():
    """Limpia cooldowns expirados por modalidad"""
    now = datetime.now()
    users_to_update = []
    
    for user_id, modes_data in data.get('cooldowns', {}).items():
        if not isinstance(modes_data, dict):
            # Migrar formato antiguo
            users_to_update.append(user_id)
            continue
            
        modes_to_remove = []
        
        for mode, cooldown_data in modes_data.items():
            try:
                end_date = datetime.fromisoformat(cooldown_data['end_date'])
                
                if now >= end_date:
                    modes_to_remove.append(mode)
                    
                    # Notificar que puede testearse en esa modalidad
                    try:
                        user = await bot.fetch_user(int(user_id))
                        if user:
                            embed = discord.Embed(
                                title=f"✅ Cooldown Terminado - {mode}",
                                description=f"Ya puedes testearte de nuevo en **{mode}**",
                                color=discord.Color.green()
                            )
                            await user.send(embed=embed)
                    except:
                        pass
            except:
                modes_to_remove.append(mode)
        
        # Remover modalidades con cooldown expirado
        for mode in modes_to_remove:
            del data['cooldowns'][user_id][mode]
        
        # Si ya no tiene cooldowns en ninguna modalidad, remover usuario
        if not data['cooldowns'][user_id]:
            users_to_update.append(user_id)
    
    for user_id in users_to_update:
        if user_id in data.get('cooldowns', {}):
            del data['cooldowns'][user_id]
    
    if users_to_update or any(modes_data for modes_data in data.get('cooldowns', {}).values()):
        save_data()

def check_user_cooldown(user_id: str, mode: str):
    """Verifica si un usuario tiene cooldown en una modalidad específica"""
    if user_id not in data.get('cooldowns', {}):
        return False, None
    
    # Migrar formato antiguo (cooldown global)
    if 'end_date' in data['cooldowns'][user_id]:
        # Formato antiguo, aplicar a todas las modalidades
        old_data = data['cooldowns'][user_id]
        data['cooldowns'][user_id] = {}
        for game_mode in GAME_MODES:
            data['cooldowns'][user_id][game_mode] = old_data
        save_data()
    
    if mode not in data['cooldowns'][user_id]:
        return False, None
    
    cooldown_data = data['cooldowns'][user_id][mode]
    end_date = datetime.fromisoformat(cooldown_data['end_date'])
    
    if datetime.now() >= end_date:
        del data['cooldowns'][user_id][mode]
        if not data['cooldowns'][user_id]:
            del data['cooldowns'][user_id]
        save_data()
        return False, None
    
    return True, end_date

def add_cooldown(user_id: str, mode: str):
    """Agrega cooldown para una modalidad específica"""
    end_date = datetime.now() + timedelta(days=COOLDOWN_DAYS)
    
    if user_id not in data['cooldowns']:
        data['cooldowns'][user_id] = {}
    
    data['cooldowns'][user_id][mode] = {
        'start_date': datetime.now().isoformat(),
        'end_date': end_date.isoformat()
    }
    save_data()
    return end_date

class TicketCloseView(discord.ui.View):
    def __init__(self, player_id: int):
        super().__init__(timeout=None)
        self.player_id = player_id
    
    @discord.ui.button(label="Cerrar Ticket", style=discord.ButtonStyle.red, emoji="🔒")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        is_tester = any(role.id == TESTER_ROLE_ID for role in interaction.user.roles)
        is_player = interaction.user.id == self.player_id
        
        if not (is_tester or is_player):
            await interaction.response.send_message("❌ Solo el tester o el jugador pueden cerrar el ticket", ephemeral=True)
            return
        
        # Enviar log al canal de TICKET logs antes de cerrar
        try:
            ticket_logs_channel_id = data['config'].get('ticket_logs_channel_id', 1459298622930813121)
            log_channel = interaction.guild.get_channel(ticket_logs_channel_id)
            
            if log_channel:
                # Obtener información del ticket
                ticket_id = str(interaction.channel.id)
                ticket_info = data['tickets'].get(ticket_id, {})
                
                # Crear embed de log
                log_embed = discord.Embed(
                    title="🔒 Ticket Cerrado",
                    description=f"**Canal:** {interaction.channel.mention} (`{interaction.channel.name}`)",
                    color=discord.Color.red(),
                    timestamp=datetime.now()
                )
                
                if ticket_info:
                    jugador = interaction.guild.get_member(int(ticket_info.get('jugador_id', 0)))
                    tester = interaction.guild.get_member(int(ticket_info.get('tester_id', 0)))
                    
                    log_embed.add_field(
                        name="👤 Jugador",
                        value=jugador.mention if jugador else "Desconocido",
                        inline=True
                    )
                    log_embed.add_field(
                        name="👨‍🏫 Tester",
                        value=tester.mention if tester else "Desconocido",
                        inline=True
                    )
                    log_embed.add_field(
                        name="🎮 Modalidad",
                        value=ticket_info.get('modalidad', 'N/A'),
                        inline=True
                    )
                    log_embed.add_field(
                        name="📅 Creado",
                        value=f"<t:{int(datetime.fromisoformat(ticket_info['fecha']).timestamp())}:R>",
                        inline=True
                    )
                
                log_embed.add_field(
                    name="🔒 Cerrado por",
                    value=interaction.user.mention,
                    inline=True
                )
                
                await log_channel.send(embed=log_embed)
                
                # Limpiar ticket de la data
                if ticket_id in data['tickets']:
                    del data['tickets'][ticket_id]
                    save_data()
        except Exception as e:
            print(f"❌ Error enviando log de ticket: {e}")
        
        await interaction.response.send_message(f"🔒 Ticket cerrado por {interaction.user.mention}")
        await asyncio.sleep(2)
        
        try:
            await interaction.channel.delete()
        except:
            pass

class WaitlistView(discord.ui.View):
    def __init__(self, modo: str):
        super().__init__(timeout=None)
        self.modo = modo
    
    @discord.ui.button(label="Join", style=discord.ButtonStyle.green, emoji="✅", custom_id="join")
    async def join_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.modo not in data['waitlists']:
            data['waitlists'][self.modo] = {'active': False, 'queue': [], 'testers': []}
        
        waitlist = data['waitlists'][self.modo]
        
        if not waitlist['active']:
            await interaction.response.send_message("❌ La waitlist está cerrada", ephemeral=True)
            return
        
        user_id = str(interaction.user.id)
        
        # Verificar cooldown para esta modalidad específica
        has_cooldown, end_date = check_user_cooldown(user_id, self.modo)
        if has_cooldown:
            time_left = end_date - datetime.now()
            days_left = time_left.days
            hours_left = time_left.seconds // 3600
            
            embed = discord.Embed(
                title=f"⏰ Cooldown Activo en {self.modo}",
                description=f"No puedes testearte en **{self.modo}** aún\n\n✨ Puedes testearte en otras modalidades",
                color=discord.Color.orange()
            )
            embed.add_field(name="Tiempo restante", value=f"**{days_left} días y {hours_left} horas**")
            embed.add_field(name="Disponible", value=f"<t:{int(end_date.timestamp())}:R>")
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        if user_id in waitlist['queue']:
            await interaction.response.send_message("⚠️ Ya estás en la cola", ephemeral=True)
            return
        
        if len(waitlist['queue']) >= MAX_QUEUE_SIZE:
            await interaction.response.send_message(f"⚠️ La cola está llena (máximo {MAX_QUEUE_SIZE} jugadores)", ephemeral=True)
            return
        
        waitlist['queue'].append(user_id)
        save_data()
        
        position = len(waitlist['queue'])
        await interaction.response.send_message(
            f"✅ Te has unido a la waitlist de **{self.modo}**\nPosición: **#{position}**",
            ephemeral=True
        )
        await self.update_panel(interaction)
    
    @discord.ui.button(label="Leave", style=discord.ButtonStyle.red, emoji="❌", custom_id="leave")
    async def leave_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        waitlist = data['waitlists'].get(self.modo, {'queue': []})
        user_id = str(interaction.user.id)
        
        if user_id not in waitlist['queue']:
            await interaction.response.send_message("⚠️ No estás en la cola", ephemeral=True)
            return
        
        waitlist['queue'].remove(user_id)
        save_data()
        
        await interaction.response.send_message(f"✅ Has salido de la waitlist de **{self.modo}**", ephemeral=True)
        await self.update_panel(interaction)
    
    @discord.ui.button(label="Tester", style=discord.ButtonStyle.blurple, emoji="👨‍🏫", custom_id="tester")
    async def tester_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not any(role.id == TESTER_ROLE_ID for role in interaction.user.roles):
            await interaction.response.send_message("❌ Solo los testers pueden usar este botón", ephemeral=True)
            return
        
        if self.modo not in data['waitlists']:
            data['waitlists'][self.modo] = {'active': False, 'queue': [], 'testers': []}
        
        waitlist = data['waitlists'][self.modo]
        user_id = str(interaction.user.id)
        
        if user_id in waitlist.get('testers', []):
            waitlist['testers'].remove(user_id)
            save_data()
            await interaction.response.send_message(f"✅ Has dejado de testear **{self.modo}**", ephemeral=True)
        else:
            if 'testers' not in waitlist:
                waitlist['testers'] = []
            waitlist['testers'].append(user_id)
            save_data()
            await interaction.response.send_message(f"✅ Ahora estás testeando **{self.modo}**", ephemeral=True)
        
        await self.update_panel(interaction)
    
    @discord.ui.button(label="Next", style=discord.ButtonStyle.gray, emoji="⏭️", custom_id="next")
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not any(role.id == TESTER_ROLE_ID for role in interaction.user.roles):
            await interaction.response.send_message("❌ Solo los testers pueden usar este botón", ephemeral=True)
            return
        
        waitlist = data['waitlists'].get(self.modo, {'queue': [], 'testers': []})
        
        if not waitlist['queue']:
            await interaction.response.send_message("⚠️ No hay jugadores en cola", ephemeral=True)
            return
        
        tester_id = str(interaction.user.id)
        if tester_id not in waitlist.get('testers', []):
            await interaction.response.send_message("❌ Debes presionar el botón **Tester** primero", ephemeral=True)
            return
        
        next_user_id = waitlist['queue'].pop(0)
        save_data()
        
        try:
            next_user = await bot.fetch_user(int(next_user_id))
            guild = interaction.guild
            category_id = data['config'].get('ticket_category_id')
            
            try:
                dm_embed = discord.Embed(
                    title=f"🎮 ¡Es tu turno para el test de {self.modo}!",
                    description=f"El tester **{interaction.user.name}** te ha llamado para tu test.",
                    color=discord.Color.blue()
                )
                dm_embed.add_field(name="Modalidad", value=f"{MODE_EMOJIS.get(self.modo, '🎮')} {self.modo}")
                await next_user.send(embed=dm_embed)
            except:
                pass
            
            if category_id:
                category = guild.get_channel(category_id)
                if category:
                    ticket_name = f"test-{next_user.name}-{self.modo.lower()}".replace(" ", "-")[:50]
                    
                    overwrites = {
                        guild.default_role: discord.PermissionOverwrite(read_messages=False),
                        next_user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
                        interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
                        guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
                    }
                    
                    ticket_channel = await category.create_text_channel(
                        name=ticket_name,
                        overwrites=overwrites
                    )
                    
                    ticket_embed = discord.Embed(
                        title=f"🎫 Test de {self.modo}",
                        description=f"**Jugador:** {next_user.mention}\n**Tester:** {interaction.user.mention}",
                        color=discord.Color.blue()
                    )
                    
                    form_embed = discord.Embed(
                        title="📋 Información Requerida",
                        description=f"{next_user.mention} Por favor proporciona:",
                        color=discord.Color.gold()
                    )
                    form_embed.add_field(name="Nick MC:", value="`Tu nick de Minecraft`", inline=False)
                    form_embed.add_field(name="Región:", value="`Tu región (NA/EU/SA/etc)`", inline=False)
                    form_embed.add_field(name="Server:", value="`Servidor donde juegas`", inline=False)
                    form_embed.add_field(name="Premium:", value="`Sí/No`", inline=False)
                    # Auto-close desactivado - solo botón manual
                    
                    view = TicketCloseView(next_user.id)
                    
                    await ticket_channel.send(embed=ticket_embed)
                    await ticket_channel.send(embed=form_embed, view=view)
                    
                    # Auto-close desactivado por petición del usuario
                    # asyncio.create_task(auto_close_ticket(ticket_channel, 300))
                    
                    ticket_id = str(ticket_channel.id)
                    data['tickets'][ticket_id] = {
                        'jugador_id': next_user_id,
                        'tester_id': tester_id,
                        'modalidad': self.modo,
                        'fecha': datetime.now().isoformat()
                    }
                    save_data()
                    
                    await interaction.response.send_message(
                        f"✅ Ticket creado: {ticket_channel.mention}\n📩 DM enviado a {next_user.mention}",
                        ephemeral=True
                    )
                else:
                    await interaction.response.send_message("⚠️ Categoría no encontrada", ephemeral=True)
            else:
                await interaction.response.send_message(
                    f"⚠️ Configura la categoría con `/configurar-tickets`",
                    ephemeral=True
                )
        except Exception as e:
            print(f"Error: {e}")
            await interaction.response.send_message(f"❌ Error al procesar", ephemeral=True)
        
        await self.update_panel(interaction)
    
    @discord.ui.button(label="Open/Close", style=discord.ButtonStyle.secondary, emoji="🔄", custom_id="toggle", row=1)
    async def toggle_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not any(role.id == TESTER_ROLE_ID for role in interaction.user.roles):
            await interaction.response.send_message("❌ Solo los testers pueden abrir/cerrar la waitlist", ephemeral=True)
            return
        
        if self.modo not in data['waitlists']:
            data['waitlists'][self.modo] = {'active': False, 'queue': [], 'testers': []}
        
        waitlist = data['waitlists'][self.modo]
        waitlist['active'] = not waitlist['active']
        save_data()
        
        status = "🟢 Abierta" if waitlist['active'] else "🔴 Cerrada"
        await interaction.response.send_message(f"✅ Waitlist de **{self.modo}**: {status}", ephemeral=True)
        await self.update_panel(interaction)
    
    async def update_panel(self, interaction: discord.Interaction):
        waitlist = data['waitlists'].get(self.modo, {'active': False, 'queue': [], 'testers': []})
        
        testers = waitlist.get('testers', [])
        queue = waitlist['queue']
        
        # Si no hay testers activos
        if not testers:
            embed = discord.Embed(
                title=f"{MODE_EMOJIS.get(self.modo, '🎮')} Queue Cerrada Temporalmente",
                description="**No hay testers disponibles, la cola se encuentra cerrada.**",
                color=discord.Color.red(),
                timestamp=datetime.now()
            )
            embed.set_footer(text=f"Papayas tierlist - {self.modo}")
        else:
            # Formato vertical con testers y jugadores
            color = discord.Color.green() if waitlist['active'] else discord.Color.red()
            
            # Obtener menciones de testers
            tester_mentions = []
            for t_id in testers:
                try:
                    user = await bot.fetch_user(int(t_id))
                    tester_mentions.append(f"@{user.name}")
                except:
                    pass
            
            testers_text = " ".join(tester_mentions) if tester_mentions else "Ninguno"
            
            embed = discord.Embed(
                title=f"{MODE_EMOJIS.get(self.modo, '🎮')} Waitlist de {self.modo}",
                color=color,
                timestamp=datetime.now()
            )
            
            embed.add_field(
                name="**Testers en turno:**",
                value=testers_text,
                inline=False
            )
            
            # Lista de espera
            if queue:
                queue_text = ""
                for idx, player_id in enumerate(queue, 1):
                    try:
                        user = await bot.fetch_user(int(player_id))
                        # Calcular tiempo en cola (simplificado)
                        queue_text += f"{idx}. @{user.name}\n"
                    except:
                        queue_text += f"{idx}. Usuario desconocido\n"
                
                embed.add_field(
                    name="**Lista de espera:**",
                    value=queue_text if queue_text else "Vacía",
                    inline=False
                )
            else:
                embed.add_field(
                    name="**Lista de espera:**",
                    value="Vacía",
                    inline=False
                )
            
            embed.set_footer(text=f"Papayas tierlist - {self.modo} | Máximo {MAX_QUEUE_SIZE} jugadores")
        
        try:
            await interaction.message.edit(embed=embed)
        except:
            pass

async def auto_close_ticket(channel, delay):
    await asyncio.sleep(delay)
    try:
        await channel.send("⏰ Ticket cerrado automáticamente por inactividad (5 minutos)")
        await asyncio.sleep(3)
        await channel.delete()
    except:
        pass

@bot.tree.command(name="crear-waitlist", description="Crea panel de waitlist para una modalidad")
@app_commands.describe(modo="Modalidad del waitlist")
@app_commands.choices(modo=[
    app_commands.Choice(name="🔨 Mace", value="Mace"),
    app_commands.Choice(name="⚔️ Sword", value="Sword"),
    app_commands.Choice(name="❤️ UHC", value="UHC"),
    app_commands.Choice(name="💎 Crystal", value="Crystal"),
    app_commands.Choice(name="🧪 NethOP", value="NethOP"),
    app_commands.Choice(name="🪓 SMP", value="SMP"),
    app_commands.Choice(name="🪓 Axe", value="Axe"),
    app_commands.Choice(name="🧪 Dpot", value="Dpot"),
])
@app_commands.checks.has_permissions(administrator=True)
async def crear_waitlist(interaction: discord.Interaction, modo: str):
    embed = discord.Embed(
        title=f"{MODE_EMOJIS.get(modo, '🎮')} Queue Cerrada Temporalmente",
        description="**No hay testers disponibles, la cola se encuentra cerrada.**",
        color=discord.Color.red(),
        timestamp=datetime.now()
    )
    embed.set_footer(text=f"Papayas tierlist - {modo}")
    
    view = WaitlistView(modo)
    message = await interaction.channel.send(embed=embed, view=view)
    
    if 'panel_messages' not in data:
        data['panel_messages'] = {}
    data['panel_messages'][modo] = message.id
    save_data()
    
    await interaction.response.send_message(f"✅ Panel de waitlist para **{modo}** creado", ephemeral=True)

@bot.tree.command(name="configurar-tickets", description="Configura la categoría para crear tickets")
@app_commands.describe(categoria="Categoría donde se crearán los tickets")
@app_commands.checks.has_permissions(administrator=True)
async def configurar_tickets(interaction: discord.Interaction, categoria: discord.CategoryChannel):
    data['config']['ticket_category_id'] = categoria.id
    save_data()
    await interaction.response.send_message(f"✅ Categoría de tickets configurada: {categoria.name}", ephemeral=True)

@bot.tree.command(name="resultado", description="Publica resultado de test (tiers bajos)")
@app_commands.describe(
    nick_mc="Nick de Minecraft del jugador",
    jugador_discord="Usuario de Discord",
    modo="Modalidad del test",
    tier_antiguo="Tier anterior",
    tier_nuevo="Tier nuevo",
    es_premium="¿Cuenta premium?"
)
@app_commands.choices(modo=[
    app_commands.Choice(name="🔨 Mace", value="Mace"),
    app_commands.Choice(name="⚔️ Sword", value="Sword"),
    app_commands.Choice(name="❤️ UHC", value="UHC"),
    app_commands.Choice(name="💎 Crystal", value="Crystal"),
    app_commands.Choice(name="🧪 NethOP", value="NethOP"),
    app_commands.Choice(name="🪓 SMP", value="SMP"),
    app_commands.Choice(name="🪓 Axe", value="Axe"),
    app_commands.Choice(name="🧪 Dpot", value="Dpot"),
])
@app_commands.choices(tier_antiguo=[
    app_commands.Choice(name="Sin Tier", value="Sin Tier"),
    app_commands.Choice(name="LT5", value="LT5"),
    app_commands.Choice(name="HT5", value="HT5"),
    app_commands.Choice(name="LT4", value="LT4"),
    app_commands.Choice(name="HT4", value="HT4"),
    app_commands.Choice(name="LT3", value="LT3"),
])
@app_commands.choices(tier_nuevo=[
    app_commands.Choice(name="LT5", value="LT5"),
    app_commands.Choice(name="HT5", value="HT5"),
    app_commands.Choice(name="LT4", value="LT4"),
    app_commands.Choice(name="HT4", value="HT4"),
    app_commands.Choice(name="LT3", value="LT3"),
])
@app_commands.choices(es_premium=[
    app_commands.Choice(name="Sí", value="si"),
    app_commands.Choice(name="No", value="no"),
])
async def resultado(
    interaction: discord.Interaction,
    nick_mc: str,
    jugador_discord: discord.User,
    modo: str,
    tier_antiguo: str,
    tier_nuevo: str,
    es_premium: str
):
    if not any(role.id == TESTER_ROLE_ID for role in interaction.user.roles):
        await interaction.response.send_message("❌ Solo los testers pueden usar este comando", ephemeral=True)
        return
    
    await publicar_resultado(interaction, nick_mc, jugador_discord, interaction.user, modo, tier_antiguo, tier_nuevo, es_premium)

@bot.tree.command(name="resultadohightier", description="Publica resultado de test (todos los tiers)")
@app_commands.describe(
    nick_mc="Nick de Minecraft del jugador",
    jugador_discord="Usuario de Discord",
    modo="Modalidad del test",
    tier_antiguo="Tier anterior",
    tier_nuevo="Tier nuevo",
    es_premium="¿Cuenta premium?"
)
@app_commands.choices(modo=[
    app_commands.Choice(name="🔨 Mace", value="Mace"),
    app_commands.Choice(name="⚔️ Sword", value="Sword"),
    app_commands.Choice(name="❤️ UHC", value="UHC"),
    app_commands.Choice(name="💎 Crystal", value="Crystal"),
    app_commands.Choice(name="🧪 NethOP", value="NethOP"),
    app_commands.Choice(name="🪓 SMP", value="SMP"),
    app_commands.Choice(name="🪓 Axe", value="Axe"),
    app_commands.Choice(name="🧪 Dpot", value="Dpot"),
])
@app_commands.choices(tier_antiguo=[
    app_commands.Choice(name="Sin Tier", value="Sin Tier"),
    app_commands.Choice(name="LT5", value="LT5"),
    app_commands.Choice(name="HT5", value="HT5"),
    app_commands.Choice(name="LT4", value="LT4"),
    app_commands.Choice(name="HT4", value="HT4"),
    app_commands.Choice(name="LT3", value="LT3"),
    app_commands.Choice(name="HT3", value="HT3"),
    app_commands.Choice(name="LT2", value="LT2"),
    app_commands.Choice(name="HT2", value="HT2"),
    app_commands.Choice(name="LT1", value="LT1"),
    app_commands.Choice(name="HT1", value="HT1"),
])
@app_commands.choices(tier_nuevo=[
    app_commands.Choice(name="LT5", value="LT5"),
    app_commands.Choice(name="HT5", value="HT5"),
    app_commands.Choice(name="LT4", value="LT4"),
    app_commands.Choice(name="HT4", value="HT4"),
    app_commands.Choice(name="LT3", value="LT3"),
    app_commands.Choice(name="HT3", value="HT3"),
    app_commands.Choice(name="LT2", value="LT2"),
    app_commands.Choice(name="HT2", value="HT2"),
    app_commands.Choice(name="LT1", value="LT1"),
    app_commands.Choice(name="HT1", value="HT1"),
])
@app_commands.choices(es_premium=[
    app_commands.Choice(name="Sí", value="si"),
    app_commands.Choice(name="No", value="no"),
])
async def resultadohightier(
    interaction: discord.Interaction,
    nick_mc: str,
    jugador_discord: discord.User,
    modo: str,
    tier_antiguo: str,
    tier_nuevo: str,
    es_premium: str
):
    if not any(role.id == TESTER_ROLE_ID for role in interaction.user.roles):
        await interaction.response.send_message("❌ Solo los testers pueden usar este comando", ephemeral=True)
        return
    
    await publicar_resultado(interaction, nick_mc, jugador_discord, interaction.user, modo, tier_antiguo, tier_nuevo, es_premium)

async def publicar_resultado(
    interaction: discord.Interaction,
    nick_mc: str,
    jugador_discord: discord.User,
    tester_discord: discord.User,
    modo: str,
    tier_antiguo: str,
    tier_nuevo: str,
    es_premium: str
):
    tier_colors = {
        "HT1": discord.Color.red(), "LT1": discord.Color.orange(),
        "HT2": discord.Color.gold(), "LT2": discord.Color.yellow(),
        "HT3": discord.Color.green(), "LT3": discord.Color.teal(),
        "HT4": discord.Color.blue(), "LT4": discord.Color.purple(),
        "HT5": discord.Color.magenta(), "LT5": discord.Color.dark_purple(),
    }
    
    embed_color = tier_colors.get(tier_nuevo, discord.Color.blue())
    
    if tier_antiguo == "Sin Tier":
        tier_emoji = "🆕"
    else:
        old_value = TIER_POINTS.get(tier_antiguo, 0)
        new_value = TIER_POINTS.get(tier_nuevo, 0)
        tier_emoji = "📈" if new_value > old_value else ("📉" if new_value < old_value else "➡️")
    
    jugador_id = str(jugador_discord.id)
    if jugador_id not in data['jugadores']:
        data['jugadores'][jugador_id] = {
            'nick_mc': nick_mc,
            'discord_name': str(jugador_discord),
            'puntos_por_modalidad': {},
            'tier_por_modalidad': {},
            'puntos_totales': 0,
            'es_premium': es_premium
        }
    
    puntos_tier = TIER_POINTS.get(tier_nuevo, 0)
    
    if modo not in data['jugadores'][jugador_id]['puntos_por_modalidad']:
        data['jugadores'][jugador_id]['puntos_por_modalidad'][modo] = []
    
    # Guardar tier exacto por modalidad
    if 'tier_por_modalidad' not in data['jugadores'][jugador_id]:
        data['jugadores'][jugador_id]['tier_por_modalidad'] = {}
    
    data['jugadores'][jugador_id]['puntos_por_modalidad'][modo].append(puntos_tier)
    data['jugadores'][jugador_id]['tier_por_modalidad'][modo] = tier_nuevo  # Guardar tier exacto
    
    puntos_totales = sum(
        sum(puntos) 
        for puntos in data['jugadores'][jugador_id]['puntos_por_modalidad'].values()
    )
    data['jugadores'][jugador_id]['puntos_totales'] = puntos_totales
    data['jugadores'][jugador_id]['nick_mc'] = nick_mc
    data['jugadores'][jugador_id]['discord_name'] = str(jugador_discord)
    data['jugadores'][jugador_id]['es_premium'] = es_premium
    
    embed = discord.Embed(
        title=f"{tier_emoji} RESULTADO DE TEST - {modo.upper()}",
        description=f"**Jugador:** {jugador_discord.mention}",
        color=embed_color,
        timestamp=datetime.now()
    )
    
    embed.add_field(name="👤 Nick MC", value=f"`{nick_mc}`", inline=True)
    embed.add_field(name="🎮 Modalidad", value=f"{MODE_EMOJIS.get(modo, '🎮')} {modo}", inline=True)
    embed.add_field(name="💎 Premium", value="✅ Sí" if es_premium == "si" else "❌ No", inline=True)
    embed.add_field(name="👨‍🏫 Tester", value=tester_discord.mention, inline=False)
    embed.add_field(name="📊 Tier Anterior", value=f"**{tier_antiguo}**", inline=True)
    embed.add_field(name="🏆 Tier Nuevo", value=f"**{tier_nuevo}**", inline=True)
    embed.add_field(name="⭐ Puntos Obtenidos", value=f"**+{puntos_tier} pts**", inline=True)
    embed.add_field(name="📈 Puntos Totales", value=f"**{puntos_totales} pts**", inline=False)
    
    # Skins mejoradas
    if es_premium == "si":
        # Intento 1: NameMC (mejor calidad)
        skin_url = f"https://mc-heads.net/body/{nick_mc}"
        embed.set_thumbnail(url=skin_url)
    else:
        # No premium: Steve
        embed.set_thumbnail(url="https://mc-heads.net/body/Steve")
    
    # SIN FOOTER
    
    data['resultados'].append({
        'nick_mc': nick_mc,
        'jugador_id': str(jugador_discord.id),
        'jugador_name': str(jugador_discord),
        'tester_id': str(tester_discord.id),
        'tester_name': str(tester_discord),
        'modalidad': modo,
        'tier_antiguo': tier_antiguo,
        'tier_nuevo': tier_nuevo,
        'puntos_obtenidos': puntos_tier,
        'puntos_totales': puntos_totales,
        'fecha': datetime.now().isoformat()
    })
    
    # Guardar también en PostgreSQL
    if POSTGRESQL_AVAILABLE:
        resultado_obj = {
            'nick_mc': nick_mc,
            'jugador_id': str(jugador_discord.id),
            'jugador_name': str(jugador_discord),
            'tester_id': str(tester_discord.id),
            'tester_name': str(tester_discord),
            'modalidad': modo,
            'tier_antiguo': tier_antiguo,
            'tier_nuevo': tier_nuevo,
            'puntos_obtenidos': puntos_tier,
            'puntos_totales': puntos_totales,
            'fecha': datetime.now().isoformat()
        }
        if database.add_resultado(resultado_obj):
            print(f"✅ Resultado guardado en PostgreSQL")
        else:
            print(f"⚠️ No se pudo guardar en PostgreSQL (usando solo memoria)")
    
    end_date = add_cooldown(jugador_id, modo)
    save_data()
    
    # Enviar al canal de RESULTADOS con reacciones
    resultado_channel_id = data.get('config', {}).get('resultado_channel_id', 1459289305414635560)
    resultado_channel = interaction.guild.get_channel(resultado_channel_id)
    
    if resultado_channel:
        # Enviar embed al canal de resultados
        resultado_message = await resultado_channel.send(embed=embed)
        
        # Agregar reacciones automáticas
        try:
            await resultado_message.add_reaction('👑')
            await resultado_message.add_reaction('😊')
            await resultado_message.add_reaction('🙏')
            await resultado_message.add_reaction('😂')
            await resultado_message.add_reaction('💀')
            print("✅ Reacciones agregadas al resultado")
        except Exception as e:
            print(f"❌ Error agregando reacciones: {e}")
    
    # Responder a la interacción
    await interaction.response.send_message(
        f"✅ Resultado publicado para {jugador_discord.mention} en {resultado_channel.mention}",
        ephemeral=True
    )
    
    # ASIGNAR ROL AUTOMÁTICAMENTE - ARREGLADO
    try:
        guild = interaction.guild
        member = guild.get_member(jugador_discord.id)
        
        if member:
            print(f"🔍 Asignando rol a {member.name}")
            
            # REMOVER TODOS LOS ROLES DE TIER
            for tier_name, role_id in TIER_ROLES.items():
                role = guild.get_role(role_id)
                if role and role in member.roles:
                    await member.remove_roles(role)
                    print(f"✅ Removido rol: {tier_name}")
            
            # ASIGNAR NUEVO ROL
            nuevo_role_id = TIER_ROLES.get(tier_nuevo)
            if nuevo_role_id:
                nuevo_role = guild.get_role(nuevo_role_id)
                if nuevo_role:
                    await member.add_roles(nuevo_role)
                    print(f"✅ Asignado rol: {tier_nuevo}")
                else:
                    print(f"❌ Rol {tier_nuevo} no encontrado en el servidor")
            else:
                print(f"❌ ID de rol para {tier_nuevo} no existe en TIER_ROLES")
    except Exception as e:
        print(f"❌ Error asignando rol: {e}")
        import traceback
        traceback.print_exc()
    
    # DM de cooldown
    try:
        cooldown_embed = discord.Embed(
            title=f"✅ ¡Gracias por testearte en {modo}!",
            description=f"Para volver a testearte en **{modo}** tendrás que esperar **{COOLDOWN_DAYS} días**\n\n✨ Puedes testearte en otras modalidades sin esperar",
            color=discord.Color.blue()
        )
        cooldown_embed.add_field(
            name=f"🎮 Modalidad",
            value=f"{MODE_EMOJIS.get(modo, '🎮')} {modo}",
            inline=True
        )
        cooldown_embed.add_field(
            name="📅 Disponible de nuevo",
            value=f"<t:{int(end_date.timestamp())}:F>",
            inline=False
        )
        cooldown_embed.add_field(
            name="⏰ Tiempo restante",
            value=f"<t:{int(end_date.timestamp())}:R>",
            inline=False
        )
        await jugador_discord.send(embed=cooldown_embed)
    except:
        pass

@bot.tree.command(name="banchiterlist", description="Banea a un jugador de la chiterlist")
@app_commands.describe(
    nick_mc="Nick de Minecraft",
    jugador_discord="Usuario de Discord",
    motivo="Motivo del ban",
    evidencia="Link a video o captura de evidencia",
    es_premium="¿Cuenta premium?"
)
@app_commands.choices(motivo=[
    app_commands.Choice(name="Chiter", value="chiter"),
    app_commands.Choice(name="Alt", value="alt"),
])
@app_commands.choices(es_premium=[
    app_commands.Choice(name="Sí", value="si"),
    app_commands.Choice(name="No", value="no"),
])
@app_commands.checks.has_permissions(manage_roles=True)
async def banchiterlist(
    interaction: discord.Interaction,
    nick_mc: str,
    jugador_discord: discord.User,
    motivo: str,
    evidencia: str,
    es_premium: str
):
    # Calcular finalización según motivo
    if motivo == "chiter":
        finalizacion_text = "Permanente"
        finalizacion_date = None  # Nunca expira
        dias = None
    else:  # alt
        finalizacion_date = datetime.now() + timedelta(days=30)
        finalizacion_text = f"30 días (<t:{int(finalizacion_date.timestamp())}:F>)"
        dias = 30
    
    # Color según motivo
    embed_color = discord.Color.dark_red() if motivo == "chiter" else discord.Color.orange()
    
    embed = discord.Embed(
        title="⚠️ JUGADOR BANEADO DE LA CHITERLIST",
        description=f"**{nick_mc} - {jugador_discord.mention} HA SIDO BANEADO**",
        color=embed_color,
        timestamp=datetime.now()
    )
    
    embed.add_field(name="👤 Nick MC", value=f"`{nick_mc}`", inline=True)
    embed.add_field(name="📋 Motivo", value=f"**{motivo.upper()}**", inline=True)
    embed.add_field(name="⏰ Duración", value=finalizacion_text, inline=True)
    embed.add_field(name="📸 Evidencia", value=f"[Ver evidencia]({evidencia})", inline=False)
    embed.add_field(name="👮 Staff", value=interaction.user.mention, inline=False)
    
    # Agregar skin
    if es_premium == "si":
        skin_url = f"https://mc-heads.net/avatar/{nick_mc}/100"
        embed.set_thumbnail(url=skin_url)
    else:
        embed.set_thumbnail(url="https://mc-heads.net/avatar/Steve/100")
    
    # Guardar ban
    ban_data = {
        'nick_mc': nick_mc,
        'jugador_id': str(jugador_discord.id),
        'motivo': motivo,
        'evidencia': evidencia,
        'finalizacion_text': finalizacion_text,
        'finalizacion_date': finalizacion_date.isoformat() if finalizacion_date else None,
        'permanente': motivo == "chiter",
        'staff_id': str(interaction.user.id),
        'fecha': datetime.now().isoformat()
    }
    
    data['castigos'].append(ban_data)
    
    # Si es ban temporal (Alt), agregar a sistema de auto-unban
    if motivo == "alt" and finalizacion_date:
        if 'bans_temporales' not in data:
            data['bans_temporales'] = {}
        
        data['bans_temporales'][str(jugador_discord.id)] = {
            'nick_mc': nick_mc,
            'end_date': finalizacion_date.isoformat(),
            'motivo': motivo
        }
    
    save_data()
    
    await interaction.response.send_message(embed=embed)
    
    # Remover todos los roles de tier
    try:
        guild = interaction.guild
        member = guild.get_member(jugador_discord.id)
        if member:
            for tier_role_id in TIER_ROLES.values():
                role = guild.get_role(tier_role_id)
                if role and role in member.roles:
                    await member.remove_roles(role)
            print(f"✅ Removidos roles de tier por ban: {motivo}")
    except Exception as e:
        print(f"Error removiendo roles: {e}")
    
    # Enviar DM al jugador
    try:
        if motivo == "chiter":
            dm_embed = discord.Embed(
                title="⛔ Has sido baneado permanentemente de Papayas tierlist",
                description="**Tu acceso a la chiterlist ha sido revocado permanentemente**",
                color=discord.Color.dark_red()
            )
            dm_embed.add_field(name="📋 Motivo", value="**CHITER**", inline=False)
            dm_embed.add_field(name="⏰ Duración", value="**PERMANENTE**", inline=False)
            dm_embed.add_field(name="📸 Evidencia", value=f"[Ver evidencia]({evidencia})", inline=False)
            dm_embed.add_field(
                name="ℹ️ Información",
                value="Este ban no expira. Si crees que es un error, contacta con el staff.",
                inline=False
            )
        else:  # alt
            dm_embed = discord.Embed(
                title="⚠️ Has sido baneado temporalmente de Papayas tierlist",
                description="**Has sido baneado por uso de cuenta alternativa**",
                color=discord.Color.orange()
            )
            dm_embed.add_field(name="📋 Motivo", value="**ALT (Cuenta alternativa)**", inline=False)
            dm_embed.add_field(name="⏰ Duración", value=f"**30 días**", inline=False)
            dm_embed.add_field(
                name="📅 Finaliza",
                value=f"<t:{int(finalizacion_date.timestamp())}:F>",
                inline=False
            )
            dm_embed.add_field(
                name="⏱️ Tiempo restante",
                value=f"<t:{int(finalizacion_date.timestamp())}:R>",
                inline=False
            )
            dm_embed.add_field(name="📸 Evidencia", value=f"[Ver evidencia]({evidencia})", inline=False)
            dm_embed.add_field(
                name="ℹ️ Información",
                value="El ban se quitará automáticamente después de 30 días.",
                inline=False
            )
        
        await jugador_discord.send(embed=dm_embed)
        print(f"✅ DM de ban enviado a {jugador_discord.name}")
    except Exception as e:
        print(f"❌ No se pudo enviar DM: {e}")

@tasks.loop(hours=1)
async def check_temp_bans():
    """Verifica bans temporales cada hora y los quita automáticamente"""
    now = datetime.now()
    bans_to_remove = []
    
    if 'bans_temporales' not in data:
        return
    
    for user_id, ban_data in data.get('bans_temporales', {}).items():
        try:
            end_date = datetime.fromisoformat(ban_data['end_date'])
            
            if now >= end_date:
                # Ban expirado - notificar al jugador
                user = await bot.fetch_user(int(user_id))
                if user:
                    try:
                        unban_embed = discord.Embed(
                            title="✅ Tu ban ha expirado",
                            description="Ya puedes volver a testearte en Papayas tierlist",
                            color=discord.Color.green()
                        )
                        unban_embed.add_field(
                            name="ℹ️ Información",
                            value=f"Tu ban de 30 días por uso de alt ha finalizado.\nYa puedes unirte a las waitlists normalmente.",
                            inline=False
                        )
                        await user.send(embed=unban_embed)
                        print(f"✅ Ban temporal expirado para {user.name}")
                    except:
                        pass
                
                bans_to_remove.append(user_id)
        except:
            bans_to_remove.append(user_id)
    
    # Remover bans expirados
    for user_id in bans_to_remove:
        if user_id in data.get('bans_temporales', {}):
            del data['bans_temporales'][user_id]
    
    if bans_to_remove:
        save_data()
        print(f"🔄 Removidos {len(bans_to_remove)} bans temporales expirados")

@bot.tree.command(name="ver-bans", description="Ver todos los bans activos")
@app_commands.checks.has_permissions(manage_roles=True)
async def ver_bans(interaction: discord.Interaction):
    """Muestra todos los bans activos (permanentes y temporales)"""
    
    bans_permanentes = [b for b in data.get('castigos', []) if b.get('permanente', False)]
    bans_temporales = data.get('bans_temporales', {})
    
    embed = discord.Embed(
        title="📋 Bans Activos en Chiterlist",
        color=discord.Color.red(),
        timestamp=datetime.now()
    )
    
    # Bans permanentes
    if bans_permanentes:
        perm_text = ""
        for ban in bans_permanentes[-5:]:  # Últimos 5
            perm_text += f"👤 **{ban['nick_mc']}** - CHITER (Permanente)\n"
        embed.add_field(name="⛔ Bans Permanentes", value=perm_text or "Ninguno", inline=False)
    else:
        embed.add_field(name="⛔ Bans Permanentes", value="Ninguno", inline=False)
    
    # Bans temporales
    if bans_temporales:
        temp_text = ""
        for user_id, ban in list(bans_temporales.items())[:5]:
            try:
                end_date = datetime.fromisoformat(ban['end_date'])
                time_left = end_date - datetime.now()
                days_left = time_left.days
                temp_text += f"👤 **{ban['nick_mc']}** - ALT ({days_left} días restantes)\n"
            except:
                pass
        embed.add_field(name="⏰ Bans Temporales (30 días)", value=temp_text or "Ninguno", inline=False)
    else:
        embed.add_field(name="⏰ Bans Temporales (30 días)", value="Ninguno", inline=False)
    
    embed.set_footer(text=f"Total permanentes: {len(bans_permanentes)} | Total temporales: {len(bans_temporales)}")
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="toptester", description="Ver el tester del mes con más tests completados")
async def toptester(interaction: discord.Interaction):
    """Muestra el tester del mes que ha completado más tests"""
    
    # Intentar obtener de PostgreSQL primero
    tester_counts = {}
    if POSTGRESQL_AVAILABLE:
        tester_counts = database.get_tester_stats()
        if tester_counts:
            print("📊 Datos obtenidos de PostgreSQL")
    
    # Si PostgreSQL no está disponible o no tiene datos, usar memoria
    if not tester_counts:
        print("📊 Usando datos de memoria")
        for resultado in data.get('resultados', []):
            tester_id = resultado.get('tester_id')
            tester_name = resultado.get('tester_name', 'Unknown')
            
            if tester_id:
                if tester_id not in tester_counts:
                    tester_counts[tester_id] = {
                        'name': tester_name,
                        'count': 0
                    }
                tester_counts[tester_id]['count'] += 1
    
    # Encontrar el tester con más tests
    if not tester_counts:
        embed = discord.Embed(
            title="🏆 Top Tester",
            description="No hay tests registrados aún",
            color=discord.Color.blue(),
            timestamp=datetime.now()
        )
        await interaction.response.send_message(embed=embed)
        return
    
    # Ordenar testers por cantidad de tests
    sorted_testers = sorted(tester_counts.items(), key=lambda x: x[1]['count'], reverse=True)
    
    # Top tester
    top_tester_id = sorted_testers[0][0]
    top_tester_data = sorted_testers[0][1]
    
    # Obtener usuario de Discord
    try:
        top_user = await bot.fetch_user(int(top_tester_id))
        tester_mention = top_user.mention
        tester_avatar = top_user.display_avatar.url
    except:
        tester_mention = top_tester_data['name']
        tester_avatar = None
    
    # Crear embed
    embed = discord.Embed(
        title="🏆 TESTER DEL MES",
        color=discord.Color.gold(),
        timestamp=datetime.now()
    )
    
    embed.add_field(
        name="👤 Top Tester",
        value=tester_mention,
        inline=True
    )
    
    embed.add_field(
        name="📊 Tests completados",
        value=f"**{top_tester_data['count']} tests**",
        inline=True
    )
    
    if tester_avatar:
        embed.set_thumbnail(url=tester_avatar)
    
    # Top 5 testers
    if len(sorted_testers) > 1:
        top5_text = ""
        for i, (tid, tdata) in enumerate(sorted_testers[:5], 1):
            try:
                user = await bot.fetch_user(int(tid))
                top5_text += f"{i}. {user.mention} - {tdata['count']} tests\n"
            except:
                top5_text += f"{i}. {tdata['name']} - {tdata['count']} tests\n"
        
        embed.add_field(
            name="📋 Top 5 Testers",
            value=top5_text,
            inline=False
        )
    
    # Footer indica origen de datos
    footer_text = "Papayas tierlist"
    if POSTGRESQL_AVAILABLE:
        footer_text += " - Datos desde PostgreSQL"
    embed.set_footer(text=footer_text)
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="test", description="Verifica que el bot esté funcionando")
async def test(interaction: discord.Interaction):
    await interaction.response.send_message("✅ ¡Bot funcionando correctamente!")

@bot.tree.command(name="sacatester", description="Remueve un tester de la tabla de resultados")
@app_commands.describe(
    tester="Usuario de Discord del tester a remover"
)
@app_commands.checks.has_permissions(manage_roles=True)
async def sacatester(interaction: discord.Interaction, tester: discord.User):
    """Remueve todos los tests realizados por un tester específico"""
    
    tester_id = str(tester.id)
    
    # Contar tests del tester ANTES de remover
    tests_count = 0
    for resultado in data.get('resultados', []):
        if resultado.get('tester_id') == tester_id:
            tests_count += 1
    
    if tests_count == 0:
        await interaction.response.send_message(
            f"❌ {tester.mention} no tiene tests registrados",
            ephemeral=True
        )
        return
    
    # Confirmar acción
    embed_confirm = discord.Embed(
        title="⚠️ Confirmar Remoción de Tester",
        description=f"¿Estás seguro de remover a **{tester.mention}** de la tabla de testers?",
        color=discord.Color.orange()
    )
    embed_confirm.add_field(
        name="📊 Tests a remover",
        value=f"**{tests_count} tests**",
        inline=True
    )
    embed_confirm.add_field(
        name="⚠️ Advertencia",
        value="Esta acción NO afecta los tiers de los jugadores, solo remueve al tester de las estadísticas",
        inline=False
    )
    
    await interaction.response.send_message(
        embed=embed_confirm,
        ephemeral=True
    )
    
    # Esperar confirmación (simplificado - remover inmediatamente por ahora)
    # En producción, podrías agregar botones de confirmación
    
    # Remover tests del tester
    resultados_originales = len(data.get('resultados', []))
    data['resultados'] = [
        resultado for resultado in data.get('resultados', [])
        if resultado.get('tester_id') != tester_id
    ]
    resultados_nuevos = len(data['resultados'])
    tests_removidos = resultados_originales - resultados_nuevos
    
    save_data()
    
    # Eliminar también de PostgreSQL
    if POSTGRESQL_AVAILABLE:
        deleted_db = database.delete_tester_resultados(tester_id)
        print(f"✅ Eliminados {deleted_db} resultados de PostgreSQL")
    
    # Embed de confirmación
    embed_success = discord.Embed(
        title="✅ Tester Removido",
        description=f"Se removió a **{tester.mention}** de la tabla de testers",
        color=discord.Color.green()
    )
    embed_success.add_field(
        name="📊 Tests removidos",
        value=f"**{tests_removidos} tests**",
        inline=True
    )
    embed_success.add_field(
        name="📋 Resultados totales",
        value=f"**{resultados_nuevos} restantes**",
        inline=True
    )
    embed_success.set_footer(text=f"Removido por: {interaction.user}")
    
    # Enviar a canal de logs
    resultado_channel_id = data.get('config', {}).get('resultado_channel_id', 1459289305414635560)
    resultado_channel = interaction.guild.get_channel(resultado_channel_id)
    
    if resultado_channel:
        await resultado_channel.send(embed=embed_success)
    
    # Responder al admin (actualizar mensaje anterior)
    await interaction.edit_original_response(embed=embed_success)
    
    print(f"✅ Tester removido: {tester.name} ({tests_removidos} tests)")

@bot.tree.command(name="añadetesteratoptester", description="Añade tests a un tester en la tabla")
@app_commands.describe(
    tester="Usuario de Discord del tester",
    cantidad="Cantidad de tests a añadir"
)
@app_commands.checks.has_permissions(manage_roles=True)
async def añadetesteratoptester(interaction: discord.Interaction, tester: discord.User, cantidad: int):
    """Añade tests falsos a un tester para reconstruir la tabla de /toptester"""
    
    if cantidad <= 0:
        await interaction.response.send_message(
            "❌ La cantidad debe ser mayor a 0",
            ephemeral=True
        )
        return
    
    if cantidad > 1000:
        await interaction.response.send_message(
            "❌ La cantidad no puede ser mayor a 1000 (para evitar errores)",
            ephemeral=True
        )
        return
    
    tester_id = str(tester.id)
    tester_name = str(tester)
    
    # Crear tests falsos
    tests_creados = 0
    for i in range(cantidad):
        # Crear resultado falso con jugador genérico
        fake_resultado = {
            'jugador_id': f'fake_player_{i}_{tester_id}',
            'jugador_name': f'FakePlayer{i}',
            'nick_mc': f'FakePlayer{i}',
            'tester_id': tester_id,
            'tester_name': tester_name,
            'modalidad': 'Sword',  # Modalidad por defecto
            'tier_antiguo': 'Sin Tier',
            'tier_nuevo': 'LT4',
            'puntos_obtenidos': 100,
            'puntos_totales': 100,
            'fecha': datetime.now().isoformat()
        }
        
        data['resultados'].append(fake_resultado)
        
        # Guardar también en PostgreSQL
        if POSTGRESQL_AVAILABLE:
            database.add_resultado(fake_resultado)
        
        tests_creados += 1
    
    save_data()
    print(f"✅ {tests_creados} tests añadidos al tester {tester_name}")
    
    # Embed de confirmación
    embed_success = discord.Embed(
        title="✅ Tests Añadidos",
        description=f"Se añadieron **{tests_creados} tests** a **{tester.mention}**",
        color=discord.Color.green()
    )
    embed_success.add_field(
        name="👨‍🏫 Tester",
        value=tester.mention,
        inline=True
    )
    embed_success.add_field(
        name="📊 Tests añadidos",
        value=f"**{tests_creados} tests**",
        inline=True
    )
    embed_success.add_field(
        name="📋 Total resultados",
        value=f"**{len(data['resultados'])} tests**",
        inline=False
    )
    embed_success.add_field(
        name="ℹ️ Nota",
        value="Estos son tests falsos para restaurar la tabla de /toptester. No afectan los tiers de jugadores reales.",
        inline=False
    )
    embed_success.set_footer(text=f"Añadido por: {interaction.user}")
    
    await interaction.response.send_message(embed=embed_success, ephemeral=True)
    
    # Enviar a canal de logs
    resultado_channel_id = data.get('config', {}).get('resultado_channel_id', 1459289305414635560)
    resultado_channel = interaction.guild.get_channel(resultado_channel_id)
    
    if resultado_channel:
        log_embed = discord.Embed(
            title="📊 Tests Añadidos a Tester",
            description=f"**{tester.mention}** recibió **{tests_creados} tests** en /toptester",
            color=discord.Color.blue()
        )
        log_embed.set_footer(text=f"Por: {interaction.user}")
        await resultado_channel.send(embed=log_embed)
    
    print(f"✅ Tests añadidos: {tester.name} (+{tests_creados} tests)")

@bot.tree.command(name="ver-cooldowns", description="Ver todos los cooldowns activos")
@app_commands.checks.has_permissions(manage_roles=True)
async def ver_cooldowns(interaction: discord.Interaction):
    cooldowns = data.get('cooldowns', {})
    
    if not cooldowns:
        await interaction.response.send_message("✅ No hay cooldowns activos", ephemeral=True)
        return
    
    embed = discord.Embed(
        title="⏰ Cooldowns Activos por Modalidad",
        description=f"Total: {len(cooldowns)} jugadores",
        color=discord.Color.orange()
    )
    
    count = 0
    for user_id, modes_data in list(cooldowns.items()):
        if count >= 10:
            break
            
        try:
            user = await bot.fetch_user(int(user_id))
            
            # Si es formato antiguo (solo tiene end_date), mostrar como antes
            if isinstance(modes_data, dict) and 'end_date' in modes_data:
                end_date = datetime.fromisoformat(modes_data['end_date'])
                time_left = end_date - datetime.now()
                days = time_left.days
                embed.add_field(
                    name=f"👤 {user.name}",
                    value=f"Todas las modalidades\nFinaliza: <t:{int(end_date.timestamp())}:R> ({days} días)",
                    inline=False
                )
            else:
                # Formato nuevo (por modalidad)
                modes_text = ""
                for mode, cooldown_data in modes_data.items():
                    end_date = datetime.fromisoformat(cooldown_data['end_date'])
                    modes_text += f"{MODE_EMOJIS.get(mode, '🎮')} {mode}: <t:{int(end_date.timestamp())}:R>\n"
                
                if modes_text:
                    embed.add_field(
                        name=f"👤 {user.name}",
                        value=modes_text.strip(),
                        inline=False
                    )
            
            count += 1
        except Exception as e:
            print(f"Error mostrando cooldown de {user_id}: {e}")
            pass
    
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="cooldowndesactivar", description="Quita el cooldown de un jugador")
@app_commands.describe(
    jugador="Usuario de Discord al que quitar el cooldown",
    modo="Modalidad específica (opcional - si no se especifica, quita de todas)"
)
@app_commands.choices(modo=[
    app_commands.Choice(name="Todas las modalidades", value="all"),
    app_commands.Choice(name="🔨 Mace", value="Mace"),
    app_commands.Choice(name="⚔️ Sword", value="Sword"),
    app_commands.Choice(name="❤️ UHC", value="UHC"),
    app_commands.Choice(name="💎 Crystal", value="Crystal"),
    app_commands.Choice(name="🧪 NethOP", value="NethOP"),
    app_commands.Choice(name="🪓 SMP", value="SMP"),
    app_commands.Choice(name="🪓 Axe", value="Axe"),
    app_commands.Choice(name="🧪 Dpot", value="Dpot"),
])
@app_commands.checks.has_permissions(manage_roles=True)
async def cooldowndesactivar(
    interaction: discord.Interaction,
    jugador: discord.User,
    modo: str = "all"
):
    """Quita el cooldown de un jugador en una o todas las modalidades"""
    
    jugador_id = str(jugador.id)
    
    if jugador_id not in data.get('cooldowns', {}):
        await interaction.response.send_message(
            f"❌ {jugador.mention} no tiene ningún cooldown activo",
            ephemeral=True
        )
        return
    
    if modo == "all":
        # Quitar cooldown de todas las modalidades
        del data['cooldowns'][jugador_id]
        save_data()
        
        embed = discord.Embed(
            title="✅ Cooldown Eliminado",
            description=f"Se eliminó el cooldown de **{jugador.mention}** en **todas las modalidades**",
            color=discord.Color.green()
        )
        embed.add_field(name="👤 Jugador", value=jugador.mention, inline=True)
        embed.add_field(name="🎮 Modalidades", value="Todas", inline=True)
        embed.set_footer(text=f"Por: {interaction.user}")
        
        await interaction.response.send_message(embed=embed)
        
        # Notificar al jugador
        try:
            dm_embed = discord.Embed(
                title="✅ Cooldown Eliminado",
                description="Un administrador eliminó tu cooldown. Ya puedes testearte en todas las modalidades.",
                color=discord.Color.green()
            )
            await jugador.send(embed=dm_embed)
        except:
            pass
    else:
        # Quitar cooldown de modalidad específica
        if isinstance(data['cooldowns'][jugador_id], dict) and 'end_date' in data['cooldowns'][jugador_id]:
            # Formato antiguo, convertir primero
            old_data = data['cooldowns'][jugador_id]
            data['cooldowns'][jugador_id] = {}
            for game_mode in GAME_MODES:
                data['cooldowns'][jugador_id][game_mode] = old_data
        
        if modo not in data['cooldowns'][jugador_id]:
            await interaction.response.send_message(
                f"❌ {jugador.mention} no tiene cooldown activo en **{modo}**",
                ephemeral=True
            )
            return
        
        del data['cooldowns'][jugador_id][modo]
        
        # Si ya no tiene cooldowns en ninguna modalidad, eliminar jugador
        if not data['cooldowns'][jugador_id]:
            del data['cooldowns'][jugador_id]
        
        save_data()
        
        embed = discord.Embed(
            title="✅ Cooldown Eliminado",
            description=f"Se eliminó el cooldown de **{jugador.mention}** en **{modo}**",
            color=discord.Color.green()
        )
        embed.add_field(name="👤 Jugador", value=jugador.mention, inline=True)
        embed.add_field(name="🎮 Modalidad", value=f"{MODE_EMOJIS.get(modo, '🎮')} {modo}", inline=True)
        embed.set_footer(text=f"Por: {interaction.user}")
        
        await interaction.response.send_message(embed=embed)
        
        # Notificar al jugador
        try:
            dm_embed = discord.Embed(
                title=f"✅ Cooldown Eliminado - {modo}",
                description=f"Un administrador eliminó tu cooldown en **{modo}**. Ya puedes testearte en esta modalidad.",
                color=discord.Color.green()
            )
            await jugador.send(embed=dm_embed)
        except:
            pass



# === COMANDO: /mensaje ===
@bot.tree.command(name="mensaje", description="Envía un mensaje desde el bot")
@app_commands.describe(
    canal="Canal donde enviar el mensaje",
    mensaje="Contenido del mensaje"
)
@app_commands.checks.has_permissions(administrator=True)
async def send_message(interaction: discord.Interaction, canal: discord.TextChannel, mensaje: str):
    """Envía mensaje desde el bot"""
    
    try:
        await canal.send(mensaje)
        await interaction.response.send_message(
            f"✅ Mensaje enviado a {canal.mention}",
            ephemeral=True
        )
    except Exception as e:
        await interaction.response.send_message(
            f"❌ Error: {e}",
            ephemeral=True
        )

if __name__ == "__main__":
    TOKEN = os.getenv('DISCORD_TOKEN')
    if not TOKEN:
        print("ERROR: No se encontró DISCORD_TOKEN en las variables de entorno")
        exit(1)
    bot.run(TOKEN)
