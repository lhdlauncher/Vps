# bot.py
import discord
from discord.ext import commands
import asyncio
import subprocess
import json
from datetime import datetime, timedelta
import shlex
import logging
import shutil
import os
from typing import Optional, List, Dict, Any
import sqlite3
import random
import traceback
import aiohttp
import time

# ============ CONFIGURATION - EASY TO SET ============

# Discord Bot Settings
DISCORD_TOKEN = 'MTQ0MTc0NDE0OTQ3NjAxNjIyOA.GZad47.x9aX3BjcBANjSTk-nUAmYnprAtJ8PIDLG6yr9w'  # Your bot token here
BOT_NAME = 'StrengthCloud'  # Bot name
PREFIX = '.'  # Command prefix
MAIN_ADMIN_ID = '1251119503492775956'  # Main admin Discord ID
VPS_USER_ROLE_ID = ''  # Role ID for VPS users (leave empty to auto-create)
DEFAULT_STORAGE_POOL = 'default'  # LXC storage pool name
YOUR_SERVER_IP = ''  # Your server IP for port forwarding

# Thumbnail URL (icon in top right and footer)
THUMBNAIL_URL = "" # SET HERE THUMBNAIL 

# Free VPS Plans based on invites/boosts
FREE_VPS_PLANS = {
    'invites': [
        {'name': ' Free Tier I', 'invites': 10, 'ram': 4, 'cpu': 1, 'disk': 20, 'emoji': '🥉'},
        {'name': ' Free Tier II', 'invites': 14, 'ram': 8, 'cpu': 2, 'disk': 50, 'emoji': '🥈'},
        {'name': ' Free Tier III', 'invites': 16, 'ram': 12, 'cpu': 2, 'disk': 60, 'emoji': '🥇'},
        {'name': ' Free Tier IV', 'invites': 22, 'ram': 16, 'cpu': 2, 'disk': 80, 'emoji': '🏆'},
        {'name': ' Free Tier V', 'invites': 32, 'ram': 24, 'cpu': 4, 'disk': 100, 'emoji': '💎'},
        {'name': ' Free Tier VI', 'invites': 40, 'ram': 32, 'cpu': 6, 'disk': 150, 'emoji': '👑'}
    ],
    'boosts': [
        {'name': ' Boost Tier I', 'boosts': 1, 'ram': 6, 'cpu': 1, 'disk': 30, 'emoji': '⭐'},
        {'name': ' Boost Tier II', 'boosts': 2, 'ram': 12, 'cpu': 2, 'disk': 60, 'emoji': '🌟🌟'},
        {'name': ' Boost Tier III', 'boosts': 3, 'ram': 18, 'cpu': 3, 'disk': 90, 'emoji': '🌟🌟🌟'},
        {'name': ' Boost Tier IV', 'boosts': 4, 'ram': 24, 'cpu': 4, 'disk': 120, 'emoji': '⚡'},
        {'name': ' Boost Tier V', 'boosts': 5, 'ram': 32, 'cpu': 5, 'disk': 150, 'emoji': '🔥'}
    ]
}

# OS Options for VPS Creation and Reinstall - Modern with emojis
OS_OPTIONS = [
    {"label": " Ubuntu 20.04 LTS", "value": "ubuntu:20.04", "emoji": "🐧", "description": "Focal Fossa - Stable LTS"},
    {"label": " Ubuntu 22.04 LTS", "value": "ubuntu:22.04", "emoji": "🐧", "description": "Jammy Jellyfish - Current LTS"},
    {"label": " Ubuntu 24.04 LTS", "value": "ubuntu:24.04", "emoji": "🐧", "description": "Noble Numbat - Latest LTS"},
    {"label": " Debian 11", "value": "images:debian/11", "emoji": "🔴", "description": "Bullseye - Old Stable"},
    {"label": " Debian 12", "value": "images:debian/12", "emoji": "🔴", "description": "Bookworm - Current Stable"},
    {"label": " Rocky Linux 9", "value": "images:rockylinux/9", "emoji": "🦊", "description": "Enterprise Linux"},
    {"label": " AlmaLinux 9", "value": "images:almalinux/9", "emoji": "🦊", "description": "RHEL Compatible"},
    {"label": " Fedora 39", "value": "images:fedora/39", "emoji": "🪅", "description": "Latest Fedora"},
]

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(f'{BOT_NAME.lower()}_vps_bot')

# Check if lxc command is available
if not shutil.which("lxc"):
    logger.error("LXC command not found. Please ensure LXC is installed.")
    raise SystemExit("LXC command not found. Please ensure LXC is installed.")

# ============ DATABASE SETUP ============

def get_db():
    conn = sqlite3.connect('vps.db')
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cur = conn.cursor()
    
    # Admins table
    cur.execute('''CREATE TABLE IF NOT EXISTS admins (
        user_id TEXT PRIMARY KEY
    )''')
    cur.execute('INSERT OR IGNORE INTO admins (user_id) VALUES (?)', (str(MAIN_ADMIN_ID),))
    
    # VPS table with purge_protected column
    cur.execute('''CREATE TABLE IF NOT EXISTS vps (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        container_name TEXT UNIQUE NOT NULL,
        plan_name TEXT DEFAULT 'Custom',
        ram TEXT NOT NULL,
        cpu TEXT NOT NULL,
        storage TEXT NOT NULL,
        config TEXT NOT NULL,
        os_version TEXT DEFAULT 'ubuntu:22.04',
        status TEXT DEFAULT 'stopped',
        suspended INTEGER DEFAULT 0,
        whitelisted INTEGER DEFAULT 0,
        purge_protected INTEGER DEFAULT 0,
        suspended_reason TEXT DEFAULT '',
        created_at TEXT NOT NULL,
        shared_with TEXT DEFAULT '[]',
        suspension_history TEXT DEFAULT '[]'
    )''')
    
    # Ensure columns exist
    cur.execute('PRAGMA table_info(vps)')
    info = cur.fetchall()
    columns = [col[1] for col in info]
    if 'os_version' not in columns:
        cur.execute("ALTER TABLE vps ADD COLUMN os_version TEXT DEFAULT 'ubuntu:22.04'")
    if 'plan_name' not in columns:
        cur.execute("ALTER TABLE vps ADD COLUMN plan_name TEXT DEFAULT 'Custom'")
    if 'suspended_reason' not in columns:
        cur.execute("ALTER TABLE vps ADD COLUMN suspended_reason TEXT DEFAULT ''")
    if 'purge_protected' not in columns:
        cur.execute("ALTER TABLE vps ADD COLUMN purge_protected INTEGER DEFAULT 0")
    
    # User stats for free VPS
    cur.execute('''CREATE TABLE IF NOT EXISTS user_stats (
        user_id TEXT PRIMARY KEY,
        invites INTEGER DEFAULT 0,
        boosts INTEGER DEFAULT 0,
        claimed_vps_count INTEGER DEFAULT 0,
        last_updated TEXT
    )''')
    
    # Settings table
    cur.execute('''CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    )''')
    
    # Port allocations table
    cur.execute('''CREATE TABLE IF NOT EXISTS port_allocations (
        user_id TEXT PRIMARY KEY,
        allocated_ports INTEGER DEFAULT 0
    )''')
    
    # Port forwards table
    cur.execute('''CREATE TABLE IF NOT EXISTS port_forwards (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        vps_container TEXT NOT NULL,
        vps_port INTEGER NOT NULL,
        host_port INTEGER NOT NULL,
        created_at TEXT NOT NULL
    )''')
    
    # Suspension logs table
    cur.execute('''CREATE TABLE IF NOT EXISTS suspension_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        container_name TEXT NOT NULL,
        user_id TEXT NOT NULL,
        action TEXT NOT NULL,
        reason TEXT,
        admin_id TEXT,
        created_at TEXT NOT NULL
    )''')
    
    # Purge protection logs table
    cur.execute('''CREATE TABLE IF NOT EXISTS purge_protection_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        container_name TEXT NOT NULL,
        user_id TEXT NOT NULL,
        action TEXT NOT NULL,
        admin_id TEXT,
        created_at TEXT NOT NULL
    )''')
    
    # Initialize settings
    settings_init = [
        ('cpu_threshold', '90'),
        ('ram_threshold', '90'),
        ('maintenance_mode', 'false'),
        ('maintenance_started_by', ''),
        ('maintenance_started_at', ''),
        ('bot_version', '4.1.0'),
        ('bot_status', 'online'),
        ('bot_activity', 'watching'),
        ('bot_activity_name', f'{BOT_NAME} VPS Manager')
    ]
    for key, value in settings_init:
        cur.execute('INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)', (key, value))
    
    conn.commit()
    conn.close()

def get_setting(key: str, default: Any = None):
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT value FROM settings WHERE key = ?', (key,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else default

def set_setting(key: str, value: str):
    conn = get_db()
    cur = conn.cursor()
    cur.execute('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', (key, value))
    conn.commit()
    conn.close()

def get_vps_data() -> Dict[str, List[Dict[str, Any]]]:
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT * FROM vps')
    rows = cur.fetchall()
    conn.close()
    data = {}
    for row in rows:
        user_id = row['user_id']
        if user_id not in data:
            data[user_id] = []
        vps = dict(row)
        vps['shared_with'] = json.loads(vps['shared_with'])
        vps['suspension_history'] = json.loads(vps['suspension_history'])
        vps['suspended'] = bool(vps['suspended'])
        vps['whitelisted'] = bool(vps['whitelisted'])
        vps['purge_protected'] = bool(vps.get('purge_protected', 0))
        vps['os_version'] = vps.get('os_version', 'ubuntu:22.04')
        vps['plan_name'] = vps.get('plan_name', 'Custom')
        data[user_id].append(vps)
    return data

def get_admins() -> List[str]:
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT user_id FROM admins')
    rows = cur.fetchall()
    conn.close()
    return [row['user_id'] for row in rows]

def save_vps_data():
    conn = get_db()
    cur = conn.cursor()
    for user_id, vps_list in vps_data.items():
        for vps in vps_list:
            shared_json = json.dumps(vps['shared_with'])
            history_json = json.dumps(vps['suspension_history'])
            suspended_int = 1 if vps['suspended'] else 0
            whitelisted_int = 1 if vps.get('whitelisted', False) else 0
            purge_protected_int = 1 if vps.get('purge_protected', False) else 0
            os_ver = vps.get('os_version', 'ubuntu:22.04')
            plan_name = vps.get('plan_name', 'Custom')
            created_at = vps.get('created_at', datetime.now().isoformat())
            suspended_reason = vps.get('suspended_reason', '')
            
            if 'id' not in vps or vps['id'] is None:
                cur.execute('''INSERT INTO vps (user_id, container_name, plan_name, ram, cpu, storage, config, os_version, status, suspended, whitelisted, purge_protected, suspended_reason, created_at, shared_with, suspension_history)
                               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                            (user_id, vps['container_name'], plan_name, vps['ram'], vps['cpu'], vps['storage'], vps['config'],
                             os_ver, vps['status'], suspended_int, whitelisted_int, purge_protected_int, suspended_reason,
                             created_at, shared_json, history_json))
                vps['id'] = cur.lastrowid
            else:
                cur.execute('''UPDATE vps SET user_id = ?, plan_name = ?, ram = ?, cpu = ?, storage = ?, config = ?, os_version = ?, status = ?, suspended = ?, whitelisted = ?, purge_protected = ?, suspended_reason = ?, shared_with = ?, suspension_history = ?
                               WHERE id = ?''',
                            (user_id, plan_name, vps['ram'], vps['cpu'], vps['storage'], vps['config'],
                             os_ver, vps['status'], suspended_int, whitelisted_int, purge_protected_int, suspended_reason,
                             shared_json, history_json, vps['id']))
    conn.commit()
    conn.close()

def save_admin_data():
    conn = get_db()
    cur = conn.cursor()
    cur.execute('DELETE FROM admins')
    for admin_id in admin_data['admins']:
        cur.execute('INSERT INTO admins (user_id) VALUES (?)', (admin_id,))
    conn.commit()
    conn.close()

def log_suspension(container_name: str, user_id: str, action: str, reason: str = "", admin_id: str = ""):
    conn = get_db()
    cur = conn.cursor()
    cur.execute('''INSERT INTO suspension_logs (container_name, user_id, action, reason, admin_id, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)''',
                (container_name, user_id, action, reason, admin_id, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def log_purge_protection(container_name: str, user_id: str, action: str, admin_id: str = ""):
    conn = get_db()
    cur = conn.cursor()
    cur.execute('''INSERT INTO purge_protection_logs (container_name, user_id, action, admin_id, created_at)
                   VALUES (?, ?, ?, ?, ?)''',
                (container_name, user_id, action, admin_id, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def get_suspension_logs(container_name: str = None) -> List[Dict]:
    conn = get_db()
    cur = conn.cursor()
    if container_name:
        cur.execute('SELECT * FROM suspension_logs WHERE container_name = ? ORDER BY created_at DESC', (container_name,))
    else:
        cur.execute('SELECT * FROM suspension_logs ORDER BY created_at DESC LIMIT 50')
    rows = cur.fetchall()
    conn.close()
    return [dict(row) for row in rows]

# User stats functions
def get_user_stats(user_id: str) -> Dict[str, Any]:
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT * FROM user_stats WHERE user_id = ?', (user_id,))
    row = cur.fetchone()
    conn.close()
    if row:
        return dict(row)
    return {'user_id': user_id, 'invites': 0, 'boosts': 0, 'claimed_vps_count': 0, 'last_updated': None}

def update_user_stats(user_id: str, invites: int = 0, boosts: int = 0, claimed_vps_count: int = 0):
    conn = get_db()
    cur = conn.cursor()
    
    cur.execute('''INSERT OR REPLACE INTO user_stats 
                   (user_id, invites, boosts, claimed_vps_count, last_updated) 
                   VALUES (?, COALESCE((SELECT invites FROM user_stats WHERE user_id = ?), 0) + ?, 
                           COALESCE((SELECT boosts FROM user_stats WHERE user_id = ?), 0) + ?,
                           COALESCE((SELECT claimed_vps_count FROM user_stats WHERE user_id = ?), 0) + ?,
                           ?)''',
                (user_id, user_id, invites, user_id, boosts, user_id, claimed_vps_count, datetime.now().isoformat()))
    
    conn.commit()
    conn.close()

# Port forwarding functions
def get_user_allocation(user_id: str) -> int:
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT allocated_ports FROM port_allocations WHERE user_id = ?', (user_id,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else 0

def get_user_used_ports(user_id: str) -> int:
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT COUNT(*) FROM port_forwards WHERE user_id = ?', (user_id,))
    row = cur.fetchone()
    conn.close()
    return row[0]

def allocate_ports(user_id: str, amount: int):
    conn = get_db()
    cur = conn.cursor()
    cur.execute('INSERT OR REPLACE INTO port_allocations (user_id, allocated_ports) VALUES (?, COALESCE((SELECT allocated_ports FROM port_allocations WHERE user_id = ?), 0) + ?)', (user_id, user_id, amount))
    conn.commit()
    conn.close()

def deallocate_ports(user_id: str, amount: int):
    conn = get_db()
    cur = conn.cursor()
    cur.execute('UPDATE port_allocations SET allocated_ports = GREATEST(0, allocated_ports - ?) WHERE user_id = ?', (amount, user_id))
    conn.commit()
    conn.close()

def get_available_host_port() -> Optional[int]:
    used_ports = set()
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT host_port FROM port_forwards')
    for row in cur.fetchall():
        used_ports.add(row[0])
    conn.close()
    for _ in range(100):
        port = random.randint(20000, 50000)
        if port not in used_ports:
            return port
    return None

async def create_port_forward(user_id: str, container: str, vps_port: int) -> Optional[int]:
    host_port = get_available_host_port()
    if not host_port:
        return None
    try:
        await execute_lxc(f"lxc config device add {container} tcp_proxy_{host_port} proxy listen=tcp:0.0.0.0:{host_port} connect=tcp:127.0.0.1:{vps_port}")
        await execute_lxc(f"lxc config device add {container} udp_proxy_{host_port} proxy listen=udp:0.0.0.0:{host_port} connect=udp:127.0.0.1:{vps_port}")
        conn = get_db()
        cur = conn.cursor()
        cur.execute('INSERT INTO port_forwards (user_id, vps_container, vps_port, host_port, created_at) VALUES (?, ?, ?, ?, ?)',
                    (user_id, container, vps_port, host_port, datetime.now().isoformat()))
        conn.commit()
        conn.close()
        return host_port
    except Exception as e:
        logger.error(f"Failed to create port forward: {e}")
        return None

async def remove_port_forward(forward_id: int, is_admin: bool = False) -> tuple[bool, Optional[str]]:
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT user_id, vps_container, host_port FROM port_forwards WHERE id = ?', (forward_id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        return False, None
    user_id, container, host_port = row
    try:
        await execute_lxc(f"lxc config device remove {container} tcp_proxy_{host_port}")
        await execute_lxc(f"lxc config device remove {container} udp_proxy_{host_port}")
        cur.execute('DELETE FROM port_forwards WHERE id = ?', (forward_id,))
        conn.commit()
        conn.close()
        return True, user_id
    except Exception as e:
        logger.error(f"Failed to remove port forward {forward_id}: {e}")
        conn.close()
        return False, None

def get_user_forwards(user_id: str) -> List[Dict]:
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT * FROM port_forwards WHERE user_id = ? ORDER BY created_at DESC', (user_id,))
    rows = cur.fetchall()
    conn.close()
    return [dict(row) for row in rows]

# Initialize database
init_db()

# Load data at startup
vps_data = get_vps_data()
admin_data = {'admins': get_admins()}

# Global settings from DB
CPU_THRESHOLD = int(get_setting('cpu_threshold', 90))
RAM_THRESHOLD = int(get_setting('ram_threshold', 90))
MAINTENANCE_MODE = get_setting('maintenance_mode', 'false').lower() == 'true'
MAINTENANCE_STARTED_BY = get_setting('maintenance_started_by', '')
MAINTENANCE_STARTED_AT = get_setting('maintenance_started_at', '')
BOT_STATUS = get_setting('bot_status', 'online')
BOT_ACTIVITY = get_setting('bot_activity', 'watching')
BOT_ACTIVITY_NAME = get_setting('bot_activity_name', f'{BOT_NAME} VPS Manager')

# Bot setup
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix=PREFIX, intents=intents, help_command=None)

# Dictionary to track active help menus to prevent duplicates
active_help_menus = {}

# Helper function to truncate text
def truncate_text(text, max_length=1024):
    if not text:
        return text
    if len(text) <= max_length:
        return text
    return text[:max_length-3] + "..."

# ============ EASY EMBED CREATION FUNCTIONS ============

def create_embed(title, description="", color=0x1a1a1a):
    """Create a styled embed with thumbnail and footer icon"""
    embed = discord.Embed(
        title=truncate_text(f"⭐ {BOT_NAME} - {title}", 256),
        description=truncate_text(description, 4096),
        color=color
    )
    
    # Set thumbnail if URL is provided
    if THUMBNAIL_URL:
        embed.set_thumbnail(url=THUMBNAIL_URL)
    
    # Set footer with timestamp and icon
    embed.set_footer(
        text=f"{BOT_NAME} VPS Manager • {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        icon_url=THUMBNAIL_URL
    )
    
    return embed

def add_field(embed, name, value, inline=False):
    """Add a styled field to an embed"""
    embed.add_field(
        name=truncate_text(f"▸ {name}", 256),
        value=truncate_text(value, 1024),
        inline=inline
    )
    return embed

def create_success_embed(title, description=""):
    """Create a success embed (green)"""
    return create_embed(title, description, color=0x00ff88)

def create_error_embed(title, description=""):
    """Create an error embed (red)"""
    return create_embed(title, description, color=0xff3366)

def create_info_embed(title, description=""):
    """Create an info embed (blue)"""
    return create_embed(title, description, color=0x00ccff)

def create_warning_embed(title, description=""):
    """Create a warning embed (yellow/orange)"""
    return create_embed(title, description, color=0xffaa00)

def create_no_vps_embed():
    """Create the No VPS Found embed"""
    embed = discord.Embed(
        title=f"⭐ {BOT_NAME} - No VPS Found",
        description="You don't have any VPS. Contact an admin to create one.",
        color=0xff3366
    )
    
    quick_actions = f"• `{PREFIX}manage` - Manage VPS\n"
    quick_actions += "• Contact admin for VPS creation"
    
    embed.add_field(
        name="▸ Quick Actions",
        value=quick_actions,
        inline=False
    )
    
    # Set thumbnail if URL is provided
    if THUMBNAIL_URL:
        embed.set_thumbnail(url=THUMBNAIL_URL)
    
    # Set footer with timestamp and icon
    embed.set_footer(
        text=f"{BOT_NAME} VPS Manager • {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        icon_url=THUMBNAIL_URL
    )
    
    return embed

def create_ping_embed(ws_latency, db_latency):
    """Create the ping embed"""
    embed = discord.Embed(
        title="📊 System Latency Report",
        color=0x00ccff
    )
    
    # Websocket and Database latency
    latency_info = f"**Websocket**\n`{ws_latency:.2f}ms`"
    db_info = f"**Database**\n`{db_latency:.2f}ms`"
    
    embed.add_field(name="⌯⌲ Connection", value=latency_info, inline=True)
    embed.add_field(name="⌯⌲ Database", value=db_info, inline=True)
    
    # Status
    status = "🟢 All systems normal" if ws_latency < 100 else "🟡 Elevated latency" if ws_latency < 200 else "🔴 High latency"
    embed.add_field(name="⌯⌲ Status", value=status, inline=False)
    
    # Set thumbnail if URL is provided
    if THUMBNAIL_URL:
        embed.set_thumbnail(url=THUMBNAIL_URL)
    
    # Set footer with timestamp and icon
    embed.set_footer(
        text=f"{BOT_NAME} VPS Manager • {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        icon_url=THUMBNAIL_URL
    )
    
    return embed

# ============ MAINTENANCE MODE CHECK ============

async def maintenance_check(ctx):
    global MAINTENANCE_MODE, MAINTENANCE_STARTED_BY, MAINTENANCE_STARTED_AT
    
    if MAINTENANCE_MODE:
        user_id = str(ctx.author.id)
        if user_id == str(MAIN_ADMIN_ID) or user_id in admin_data.get("admins", []):
            return True
        
        try:
            started_by_user = await bot.fetch_user(int(MAINTENANCE_STARTED_BY)) if MAINTENANCE_STARTED_BY else None
            started_by_mention = started_by_user.mention if started_by_user else "Unknown"
        except:
            started_by_mention = "Unknown"
        
        try:
            started_at = datetime.fromisoformat(MAINTENANCE_STARTED_AT).strftime('%Y-%m-%d %H:%M:%S') if MAINTENANCE_STARTED_AT else "Unknown"
        except:
            started_at = "Unknown"
        
        embed = create_warning_embed(
            "Maintenance Mode Active",
            "The bot is currently under maintenance. Only administrators can use commands at this time."
        )
        add_field(embed, "Started By", started_by_mention, True)
        add_field(embed, "Status", "Commands disabled for non-admins", True)
        add_field(embed, "Started At", started_at, False)
        
        await ctx.send(embed=embed)
        return False
    return True

# ============ ADMIN CHECKS ============

def is_admin():
    async def predicate(ctx):
        if not await maintenance_check(ctx):
            return False
        
        user_id = str(ctx.author.id)
        if user_id == str(MAIN_ADMIN_ID) or user_id in admin_data.get("admins", []):
            return True
        raise commands.CheckFailure("You need admin permissions to use this command.")
    return commands.check(predicate)

def is_main_admin():
    async def predicate(ctx):
        if not await maintenance_check(ctx):
            return False
        
        if str(ctx.author.id) == str(MAIN_ADMIN_ID):
            return True
        raise commands.CheckFailure("Only the main admin can use this command.")
    return commands.check(predicate)

# ============ LXC COMMAND EXECUTION ============

async def execute_lxc(command, timeout=120):
    try:
        cmd = shlex.split(command)
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            raise asyncio.TimeoutError(f"Command timed out after {timeout} seconds")
        if proc.returncode != 0:
            error = stderr.decode().strip() if stderr else "Command failed with no error output"
            raise Exception(error)
        return stdout.decode().strip() if stdout else True
    except asyncio.TimeoutError as te:
        logger.error(f"LXC command timed out: {command} - {str(te)}")
        raise
    except Exception as e:
        logger.error(f"LXC Error: {command} - {str(e)}")
        raise

# ============ LXC CONFIGURATION ============

async def apply_lxc_config(container_name):
    try:
        await execute_lxc(f"lxc config set {container_name} security.nesting true")
        await execute_lxc(f"lxc config set {container_name} security.privileged true")
        await execute_lxc(f"lxc config set {container_name} security.syscalls.intercept.mknod true")
        await execute_lxc(f"lxc config set {container_name} security.syscalls.intercept.setxattr true")
        
        try:
            await execute_lxc(f"lxc config device add {container_name} fuse unix-char path=/dev/fuse")
        except Exception as e:
            if "already exists" not in str(e).lower():
                raise
        
        await execute_lxc(f"lxc config set {container_name} linux.kernel_modules overlay,loop,nf_nat,ip_tables,ip6_tables,netlink_diag,br_netfilter")
        
        raw_lxc_config = """
lxc.apparmor.profile = unconfined
lxc.cgroup.devices.allow = a
lxc.cap.drop =
lxc.mount.auto = proc:rw sys:rw cgroup:rw
"""
        await execute_lxc(f"lxc config set {container_name} raw.lxc '{raw_lxc_config}'")
        
        logger.info(f"Applied LXC config to {container_name}")
    except Exception as e:
        logger.error(f"Failed to apply LXC config to {container_name}: {e}")

async def apply_internal_permissions(container_name):
    try:
        await asyncio.sleep(5)
        
        commands = [
            "mkdir -p /etc/sysctl.d/",
            "echo 'net.ipv4.ip_unprivileged_port_start=0' > /etc/sysctl.d/99-custom.conf",
            "echo 'net.ipv4.ping_group_range=0 2147483647' >> /etc/sysctl.d/99-custom.conf",
            "echo 'fs.inotify.max_user_watches=524288' >> /etc/sysctl.d/99-custom.conf",
            "sysctl -p /etc/sysctl.d/99-custom.conf || true"
        ]
        
        for cmd in commands:
            try:
                await execute_lxc(f"lxc exec {container_name} -- bash -c \"{cmd}\"")
            except Exception:
                continue
        
        logger.info(f"Applied internal permissions to {container_name}")
    except Exception as e:
        logger.error(f"Failed to apply internal permissions to {container_name}: {e}")

# ============ VPS USER ROLE ============

async def get_or_create_vps_role(guild):
    global VPS_USER_ROLE_ID
    if VPS_USER_ROLE_ID:
        try:
            role = guild.get_role(int(VPS_USER_ROLE_ID))
            if role:
                return role
        except:
            pass
    
    role = discord.utils.get(guild.roles, name=f"{BOT_NAME} VPS User")
    if role:
        VPS_USER_ROLE_ID = str(role.id)
        return role
    try:
        role = await guild.create_role(
            name=f"{BOT_NAME} VPS User",
            color=discord.Color.dark_purple(),
            reason=f"{BOT_NAME} VPS User role for bot management",
            permissions=discord.Permissions.none()
        )
        VPS_USER_ROLE_ID = str(role.id)
        logger.info(f"Created {BOT_NAME} VPS User role: {role.name} (ID: {role.id})")
        return role
    except Exception as e:
        logger.error(f"Failed to create {BOT_NAME} VPS User role: {e}")
        return None

# ============ CONTAINER STATS FUNCTIONS ============

async def get_container_status(container_name):
    try:
        proc = await asyncio.create_subprocess_exec(
            "lxc", "info", container_name,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await proc.communicate()
        output = stdout.decode()
        for line in output.splitlines():
            if line.startswith("Status: "):
                return line.split(": ", 1)[1].strip().lower()
        return "unknown"
    except Exception:
        return "unknown"

async def get_container_cpu(container_name):
    try:
        proc = await asyncio.create_subprocess_exec(
            "lxc", "exec", container_name, "--", "top", "-bn1",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await proc.communicate()
        output = stdout.decode()
        for line in output.splitlines():
            if '%Cpu(s):' in line:
                parts = line.split()
                us = float(parts[1])
                sy = float(parts[3])
                ni = float(parts[5])
                id_ = float(parts[7])
                wa = float(parts[9])
                hi = float(parts[11])
                si = float(parts[13])
                st = float(parts[15])
                usage = us + sy + ni + wa + hi + si + st
                return f"{usage:.1f}%"
        return "0.0%"
    except Exception:
        return "N/A"

async def get_container_memory(container_name):
    try:
        proc = await asyncio.create_subprocess_exec(
            "lxc", "exec", container_name, "--", "free", "-m",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await proc.communicate()
        lines = stdout.decode().splitlines()
        if len(lines) > 1:
            parts = lines[1].split()
            total = int(parts[1])
            used = int(parts[2])
            usage_pct = (used / total * 100) if total > 0 else 0
            return f"{used}/{total} MB ({usage_pct:.1f}%)"
        return "Unknown"
    except Exception:
        return "N/A"

async def get_container_disk(container_name):
    try:
        proc = await asyncio.create_subprocess_exec(
            "lxc", "exec", container_name, "--", "df", "-h", "/",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await proc.communicate()
        lines = stdout.decode().splitlines()
        for line in lines:
            if '/dev/' in line and ' /' in line:
                parts = line.split()
                if len(parts) >= 5:
                    used = parts[2]
                    size = parts[1]
                    perc = parts[4]
                    return f"{used}/{size} ({perc})"
        return "Unknown"
    except Exception:
        return "N/A"

async def get_container_uptime(container_name):
    try:
        proc = await asyncio.create_subprocess_exec(
            "lxc", "exec", container_name, "--", "uptime",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await proc.communicate()
        uptime_str = stdout.decode().strip()
        if ',' in uptime_str:
            uptime_parts = uptime_str.split('up ')[1].split(',')[0]
            return uptime_parts.strip()
        return uptime_str
    except Exception:
        return "Unknown"

async def get_container_logs(container_name, lines=50):
    try:
        proc = await asyncio.create_subprocess_exec(
            "lxc", "exec", container_name, "--", "journalctl", "-n", str(lines), "--no-pager",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await proc.communicate()
        return stdout.decode().strip() if stdout else "No logs available"
    except Exception:
        return "Unable to fetch logs"

def get_uptime():
    try:
        result = subprocess.run(['uptime'], capture_output=True, text=True)
        return result.stdout.strip()
    except Exception:
        return "Unknown"

# ============ BOT EVENTS ============

@bot.event
async def on_ready():
    logger.info(f'{bot.user} has connected to Discord!')
    
    if MAINTENANCE_MODE:
        await bot.change_presence(status=discord.Status.idle, activity=discord.Game(name="🔧 Maintenance Mode"))
    else:
        activity_types = {
            'playing': discord.ActivityType.playing,
            'watching': discord.ActivityType.watching,
            'listening': discord.ActivityType.listening,
        }
        
        status_types = {
            'online': discord.Status.online,
            'idle': discord.Status.idle,
            'dnd': discord.Status.dnd,
        }
        
        activity_type = activity_types.get(BOT_ACTIVITY, discord.ActivityType.watching)
        status = status_types.get(BOT_STATUS, discord.Status.online)
        
        await bot.change_presence(
            status=status,
            activity=discord.Activity(type=activity_type, name=BOT_ACTIVITY_NAME)
        )
    
    logger.info(f"{BOT_NAME} Bot is ready!")

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(embed=create_error_embed("Missing Argument", f"Please check command usage with `{PREFIX}help`."))
    elif isinstance(error, commands.BadArgument):
        await ctx.send(embed=create_error_embed("Invalid Argument", "Please check your input and try again."))
    elif isinstance(error, commands.CheckFailure):
        error_msg = str(error) if str(error) else "You need admin permissions for this command."
        await ctx.send(embed=create_error_embed("Access Denied", error_msg))
    elif isinstance(error, commands.CommandOnCooldown):
        await ctx.send(embed=create_warning_embed("Command on Cooldown", f"Please wait {error.retry_after:.2f} seconds before using this command again."))
    else:
        logger.error(f"Command error: {error}")
        await ctx.send(embed=create_error_embed("System Error", "An unexpected error occurred."))

# ============ USER COMMANDS ============

@bot.command(name='ping')
@commands.cooldown(1, 3, commands.BucketType.user)
async def ping(ctx):
    """Check bot latency with detailed report"""
    if not await maintenance_check(ctx):
        return
    
    # Measure websocket latency
    ws_latency = bot.latency * 1000
    
    # Measure database latency
    start_time = time.time()
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT 1')
    cur.fetchone()
    conn.close()
    db_latency = (time.time() - start_time) * 1000
    
    embed = create_ping_embed(ws_latency, db_latency)
    await ctx.send(embed=embed)

@bot.command(name='uptime')
@commands.cooldown(1, 5, commands.BucketType.user)
async def uptime(ctx):
    """Show host uptime"""
    if not await maintenance_check(ctx):
        return
    
    up = get_uptime()
    embed = create_info_embed("Host Uptime", f"```\n{up}\n```")
    await ctx.send(embed=embed)

@bot.command(name='plans')
@commands.cooldown(1, 5, commands.BucketType.user)
async def show_plans(ctx):
    """View free VPS plans with emojis"""
    if not await maintenance_check(ctx):
        return
    
    embed = discord.Embed(
        title=f"⭐ {BOT_NAME} - Free VPS Plans",
        description="───────────────\nEarn FREE VPS plans by invites or server boosts",
        color=0xffaa00
    )
    
    # Invite-based plans with emojis
    invite_text = ""
    for i, plan in enumerate(FREE_VPS_PLANS['invites'], 1):
        invite_text += f"**{plan['emoji']} {plan['name']}**\n"
        invite_text += f"  • RAM: {plan['ram']} GB\n"
        invite_text += f"  • CPU: {plan['cpu']} Cores\n"
        invite_text += f"  • Storage: {plan['disk']} GB\n"
        invite_text += f"  • Requires: {plan['invites']} Invites\n\n"
    
    embed.add_field(name="📨 Invite Rewards", value=invite_text, inline=True)
    
    # Boost-based plans with emojis
    boost_text = ""
    for i, plan in enumerate(FREE_VPS_PLANS['boosts'], 1):
        boost_text += f"**{plan['emoji']} {plan['name']}**\n"
        boost_text += f"  • RAM: {plan['ram']} GB\n"
        boost_text += f"  • CPU: {plan['cpu']} Cores\n"
        boost_text += f"  • Storage: {plan['disk']} GB\n"
        boost_text += f"  • Requires: {plan['boosts']} Boost{'s' if plan['boosts'] > 1 else ''}\n\n"
    
    embed.add_field(name="🚀 Boost Rewards", value=boost_text, inline=True)
    
    embed.add_field(name="───────────────", 
                   value=f"📌 **How to Claim:**\n"
                         f"• `.claimfree inv <1-6>` - Claim invite VPS\n"
                         f"• `.claimfree boost <1-5>` - Claim boost VPS\n"
                         f"• Check your stats with `.stats`", 
                   inline=False)
    
    # Set thumbnail if URL is provided
    if THUMBNAIL_URL:
        embed.set_thumbnail(url=THUMBNAIL_URL)
    
    # Set footer with timestamp and icon
    embed.set_footer(
        text=f"{BOT_NAME} VPS Manager • {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        icon_url=THUMBNAIL_URL
    )
    
    await ctx.send(embed=embed)

@bot.command(name='freeplans')
@commands.cooldown(1, 5, commands.BucketType.user)
async def free_plans(ctx):
    """Free Plans List"""
    if not await maintenance_check(ctx):
        return
    await show_plans(ctx)

@bot.command(name='stats')
@commands.cooldown(1, 5, commands.BucketType.user)
async def user_stats(ctx):
    """View your invite and boost stats"""
    if not await maintenance_check(ctx):
        return
    
    user_id = str(ctx.author.id)
    stats = get_user_stats(user_id)
    
    embed = create_info_embed(f"📊 {ctx.author.name}'s Stats", f"Your current statistics")
    
    add_field(embed, "📨 Invites", str(stats.get('invites', 0)), True)
    add_field(embed, "🚀 Boosts", str(stats.get('boosts', 0)), True)
    add_field(embed, "🖥️ VPS Owned", str(len(vps_data.get(user_id, []))), True)
    add_field(embed, "🎁 Claimed VPS", str(stats.get('claimed_vps_count', 0)), True)
    
    await ctx.send(embed=embed)

@bot.command(name='claimfree')
@commands.cooldown(1, 30, commands.BucketType.user)
async def claim_free_vps(ctx, reward_type: str = None, plan_number: int = None):
    """Claim a free VPS based on invites or boosts
    Usage: 
    .claimfree inv <1-6> - Claim invite-based VPS
    .claimfree boost <1-5> - Claim boost-based VPS
    """
    if not await maintenance_check(ctx):
        return
    
    if not reward_type or not plan_number:
        embed = create_error_embed("Invalid Usage", 
            f"**Usage:**\n"
            f"• `.claimfree inv <1-6>` - Claim invite VPS\n"
            f"• `.claimfree boost <1-5>` - Claim boost VPS\n\n"
            f"Use `.plans` to see available plans.")
        await ctx.send(embed=embed)
        return
    
    user_id = str(ctx.author.id)
    stats = get_user_stats(user_id)
    
    # Check if user already has a VPS
    if user_id in vps_data and len(vps_data[user_id]) > 0:
        embed = create_error_embed("VPS Already Exists", 
            "You already have a VPS. Each user can only claim one free VPS.\n"
            "Contact an admin if you need additional VPS.")
        await ctx.send(embed=embed)
        return
    
    # Determine reward type
    reward_type = reward_type.lower()
    plan_category = None
    
    if reward_type in ['inv', 'invite', 'invites']:
        plan_category = 'invites'
        max_plans = len(FREE_VPS_PLANS['invites'])
        plan_type_name = "invite"
    elif reward_type in ['boost', 'boosts']:
        plan_category = 'boosts'
        max_plans = len(FREE_VPS_PLANS['boosts'])
        plan_type_name = "boost"
    else:
        embed = create_error_embed("Invalid Reward Type", 
            "Reward type must be: `inv` (invites) or `boost` (boosts)")
        await ctx.send(embed=embed)
        return
    
    # Check plan number
    if plan_number < 1 or plan_number > max_plans:
        embed = create_error_embed("Invalid Plan Number", 
            f"Plan number must be between 1 and {max_plans} for {plan_type_name} plans.\n"
            f"Use `.plans` to see available plans.")
        await ctx.send(embed=embed)
        return
    
    # Get the selected plan
    selected_plan = FREE_VPS_PLANS[plan_category][plan_number - 1]
    
    # Check if user meets requirements
    required = selected_plan.get(plan_category[:-1])  # removes 's' from end
    current = stats.get(plan_category, 0)
    
    if current < required:
        embed = create_error_embed("Insufficient Requirements", 
            f"You need **{required} {plan_type_name}{'s' if required > 1 else ''}** to claim **{selected_plan['name']}**.\n"
            f"You currently have: **{current} {plan_type_name}{'s' if current > 1 else ''}**\n\n"
            f"**How to earn more {plan_type_name}s:**\n"
            f"• Invites: Invite users to the server\n"
            f"• Boosts: Boost the server with Nitro")
        await ctx.send(embed=embed)
        return
    
    # Create OS selection view
    embed = create_info_embed("VPS Creation", 
        f"Claiming **{selected_plan['name']}** for {ctx.author.mention}\n"
        f"**RAM:** {selected_plan['ram']}GB\n"
        f"**CPU:** {selected_plan['cpu']} Cores\n"
        f"**Disk:** {selected_plan['disk']}GB\n"
        f"**Cost:** {required} {plan_type_name}{'s' if required > 1 else ''}\n\n"
        f"Select an OS below.")
    
    view = ClaimOSSelectView(selected_plan, plan_category, required, ctx)
    await ctx.send(embed=embed, view=view)

class ClaimOSSelectView(discord.ui.View):
    def __init__(self, plan, plan_category, required, ctx):
        super().__init__(timeout=300)
        self.plan = plan
        self.plan_category = plan_category
        self.required = required
        self.ctx = ctx
        self.selected_os = None
        
        options = []
        for o in OS_OPTIONS:
            emoji = o.get('emoji', '🐧')
            options.append(discord.SelectOption(label=o["label"], value=o["value"], emoji=emoji, description=o.get("description", "")))
        
        self.select = discord.ui.Select(
            placeholder="Select an OS for the VPS",
            options=options
        )
        self.select.callback = self.select_os
        self.add_item(self.select)
        self.add_item(discord.ui.Button(label="❌ Cancel", style=discord.ButtonStyle.danger, custom_id="cancel", row=1))
    
    async def select_os(self, interaction: discord.Interaction):
        if str(interaction.user.id) != str(self.ctx.author.id):
            await interaction.response.send_message(embed=create_error_embed("Access Denied", "Only the command author can select."), ephemeral=True)
            return
        
        self.selected_os = self.select.values[0]
        await interaction.response.defer()
        
        confirm_view = discord.ui.View()
        confirm_button = discord.ui.Button(label="✅ Confirm", style=discord.ButtonStyle.success, custom_id="confirm")
        cancel_button = discord.ui.Button(label="❌ Cancel", style=discord.ButtonStyle.danger, custom_id="cancel")
        
        async def confirm_callback(confirm_interaction):
            await self.create_vps(confirm_interaction)
        
        async def cancel_callback(cancel_interaction):
            await cancel_interaction.response.edit_message(embed=create_info_embed("Cancelled", "VPS creation cancelled."), view=None)
        
        confirm_button.callback = confirm_callback
        cancel_button.callback = cancel_callback
        
        confirm_view.add_item(confirm_button)
        confirm_view.add_item(cancel_button)
        
        embed = create_info_embed("Confirm VPS Creation", 
            f"**User:** {self.ctx.author.mention}\n"
            f"**Plan:** {self.plan['name']}\n"
            f"**OS:** {self.selected_os}\n"
            f"**RAM:** {self.plan['ram']}GB\n"
            f"**CPU:** {self.plan['cpu']} Cores\n"
            f"**Disk:** {self.plan['disk']}GB\n"
            f"**Cost:** {self.required} {self.plan_category[:-1]}{'s' if self.required > 1 else ''}\n\n"
            f"Please confirm to proceed.")
        
        await interaction.edit_original_response(embed=embed, view=confirm_view)
    
    async def create_vps(self, interaction: discord.Interaction):
        await interaction.response.defer()
        
        creating_embed = create_info_embed("Creating VPS", f"Deploying {self.selected_os} VPS for {self.ctx.author.mention}...")
        await interaction.edit_original_response(embed=creating_embed, view=None)
        
        user_id = str(self.ctx.author.id)
        if user_id not in vps_data:
            vps_data[user_id] = []
        
        vps_count = len(vps_data[user_id]) + 1
        container_name = f"{BOT_NAME.lower()}-vps-{user_id}-{vps_count}"
        ram_mb = self.plan['ram'] * 1024
        
        try:
            # Create the VPS
            await execute_lxc(f"lxc init {self.selected_os} {container_name} -s {DEFAULT_STORAGE_POOL}")
            await execute_lxc(f"lxc config set {container_name} limits.memory {ram_mb}MB")
            await execute_lxc(f"lxc config set {container_name} limits.cpu {self.plan['cpu']}")
            await execute_lxc(f"lxc config device set {container_name} root size={self.plan['disk']}GB")
            await apply_lxc_config(container_name)
            await execute_lxc(f"lxc start {container_name}")
            await apply_internal_permissions(container_name)
            
            # Deduct the cost
            update_amount = -self.required
            if self.plan_category == 'invites':
                update_user_stats(user_id, invites=update_amount)
            else:  # boosts
                update_user_stats(user_id, boosts=update_amount)
            
            # Update claimed VPS count
            update_user_stats(user_id, claimed_vps_count=1)
            
            # Save VPS info
            config_str = f"{self.plan['ram']}GB RAM / {self.plan['cpu']} CPU / {self.plan['disk']}GB Disk"
            vps_info = {
                "container_name": container_name,
                "plan_name": self.plan['name'],
                "ram": f"{self.plan['ram']}GB",
                "cpu": str(self.plan['cpu']),
                "storage": f"{self.plan['disk']}GB",
                "config": config_str,
                "os_version": self.selected_os,
                "status": "running",
                "suspended": False,
                "whitelisted": False,
                "purge_protected": False,
                "suspended_reason": "",
                "suspension_history": [],
                "created_at": datetime.now().isoformat(),
                "shared_with": [],
                "id": None
            }
            vps_data[user_id].append(vps_info)
            save_vps_data()
            
            # Assign VPS role
            if self.ctx.guild:
                vps_role = await get_or_create_vps_role(self.ctx.guild)
                if vps_role:
                    try:
                        await self.ctx.author.add_roles(vps_role, reason=f"{BOT_NAME} VPS ownership granted")
                    except discord.Forbidden:
                        logger.warning(f"Failed to assign VPS role to {self.ctx.author.name}")
            
            # Send success embed
            success_embed = create_success_embed("VPS Created Successfully")
            add_field(success_embed, "Owner", self.ctx.author.mention, True)
            add_field(success_embed, "Plan", self.plan['name'], True)
            add_field(success_embed, "Container", f"`{container_name}`", True)
            add_field(success_embed, "Resources", f"**RAM:** {self.plan['ram']}GB\n**CPU:** {self.plan['cpu']} Cores\n**Storage:** {self.plan['disk']}GB", False)
            add_field(success_embed, "OS", self.selected_os, True)
            
            await interaction.followup.send(embed=success_embed)
            
            # Send DM to user
            try:
                dm_embed = create_success_embed("VPS Created!", f"Your VPS has been successfully created!")
                vps_details = f"**Plan:** {self.plan['name']}\n"
                vps_details += f"**Container Name:** `{container_name}`\n"
                vps_details += f"**Configuration:** {config_str}\n"
                vps_details += f"**Status:** Running\n"
                vps_details += f"**OS:** {self.selected_os}\n"
                vps_details += f"**Created:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                
                add_field(dm_embed, "VPS Details", vps_details, False)
                add_field(dm_embed, "Management", 
                         f"• Use `{PREFIX}manage` to start/stop your VPS\n• Use `{PREFIX}manage` → SSH for terminal access\n• Use `{PREFIX}ports` for port forwarding", 
                         False)
                
                await self.ctx.author.send(embed=dm_embed)
            except:
                pass  # User has DMs disabled
        
        except Exception as e:
            error_embed = create_error_embed("Creation Failed", f"Error: {str(e)}")
            await interaction.followup.send(embed=error_embed)

@bot.command(name='myvps')
@commands.cooldown(1, 5, commands.BucketType.user)
async def my_vps(ctx):
    """List your VPS"""
    if not await maintenance_check(ctx):
        return
    
    user_id = str(ctx.author.id)
    vps_list = vps_data.get(user_id, [])
    
    if not vps_list:
        await ctx.send(embed=create_no_vps_embed())
        return
    
    embed = create_info_embed("My VPS", f"You have `{len(vps_list)}` VPS")
    
    for i, vps in enumerate(vps_list, 1):
        status = vps.get('status', 'unknown').upper()
        if vps.get('suspended', False):
            status += " (SUSPENDED)"
        
        status_emoji = "🟢" if vps.get('status') == 'running' else "🔴" if vps.get('status') == 'stopped' else "🟡"
        
        vps_info = f"{status_emoji} **VPS #{i}:** `{vps['container_name']}`\n"
        vps_info += f"• **Status:** {status}\n"
        vps_info += f"• **Plan:** {vps.get('plan_name', 'Custom')}\n"
        vps_info += f"• **Resources:** {vps.get('config', 'Custom')}\n"
        
        embed.add_field(name="", value=vps_info, inline=False)
    
    add_field(embed, "Management", f"Use `{PREFIX}manage` to control your VPS\nUse `{PREFIX}list` for detailed information", False)
    await ctx.send(embed=embed)

@bot.command(name='list')
@commands.cooldown(1, 5, commands.BucketType.user)
async def list_user_vps(ctx):
    """Detailed VPS list"""
    if not await maintenance_check(ctx):
        return
    
    user_id = str(ctx.author.id)
    vps_list = vps_data.get(user_id, [])
    
    if not vps_list:
        await ctx.send(embed=create_no_vps_embed())
        return
    
    embed = create_info_embed("Your VPS List", f"Showing `{len(vps_list)}` VPS for {ctx.author.mention}")
    
    for i, vps in enumerate(vps_list, 1):
        container_name = vps['container_name']
        
        status = await get_container_status(container_name)
        cpu_usage = await get_container_cpu(container_name)
        memory_usage = await get_container_memory(container_name)
        disk_usage = await get_container_disk(container_name)
        uptime_info = await get_container_uptime(container_name)
        
        status_emoji = "🟢" if status == 'running' else "🔴" if status == 'stopped' else "🟡"
        suspended_text = " (SUSPENDED)" if vps.get('suspended', False) else ""
        purge_text = " 🛡️ PROTECTED" if vps.get('purge_protected', False) else ""
        
        vps_info = f"**#{i} | {status_emoji} {status.upper()}{suspended_text}{purge_text}**\n"
        vps_info += f"**Container:** `{container_name}`\n"
        vps_info += f"**Plan:** {vps.get('plan_name', 'Custom')}\n"
        vps_info += f"**Resources:** {vps['ram']} RAM | {vps['cpu']} CPU | {vps['storage']} Storage\n"
        vps_info += f"**OS:** {vps.get('os_version', 'ubuntu:22.04')}\n"
        vps_info += f"**Uptime:** {uptime_info}\n"
        vps_info += f"**CPU Usage:** {cpu_usage}\n"
        vps_info += f"**Memory:** {memory_usage}\n"
        vps_info += f"**Disk:** {disk_usage}\n"
        vps_info += f"**Created:** {vps.get('created_at', 'Unknown')[:10]}\n"
        
        embed.add_field(name=f"VPS #{i}", value=vps_info, inline=False)
    
    await ctx.send(embed=embed)

# ============ MODERN REINSTALL BUTTON WITH OS SELECTION ============

class ReinstallOSView(discord.ui.View):
    """Modern OS selection view for reinstall with descriptions and emojis"""
    def __init__(self, ctx, container_name, owner_id, actual_idx, vps_data_entry, parent_view):
        super().__init__(timeout=300)
        self.ctx = ctx
        self.container_name = container_name
        self.owner_id = owner_id
        self.actual_idx = actual_idx
        self.vps_data_entry = vps_data_entry
        self.parent_view = parent_view
        self.message = None
        
        # Get current OS for display
        self.current_os = vps_data_entry.get('os_version', 'ubuntu:22.04')
        
        # Create OS selection dropdown with modern styling
        options = []
        for o in OS_OPTIONS:
            emoji = o.get('emoji', '🐧')
            description = o.get('description', '')
            options.append(discord.SelectOption(
                label=o["label"], 
                value=o["value"], 
                emoji=emoji,
                description=description
            ))
        
        self.select = discord.ui.Select(
            placeholder="🎯 Select a new operating system",
            options=options,
            min_values=1,
            max_values=1
        )
        self.select.callback = self.select_callback
        self.add_item(self.select)
        
        # Add cancel button
        cancel_button = discord.ui.Button(label="❌ Cancel", style=discord.ButtonStyle.secondary, row=1)
        cancel_button.callback = self.cancel_callback
        self.add_item(cancel_button)
    
    async def select_callback(self, interaction: discord.Interaction):
        if str(interaction.user.id) != str(self.ctx.author.id):
            await interaction.response.send_message(embed=create_error_embed("Access Denied", "Only the command author can select."), ephemeral=True)
            return
        
        selected_os = self.select.values[0]
        
        # Find the selected OS details
        selected_os_data = next((o for o in OS_OPTIONS if o["value"] == selected_os), None)
        os_display = selected_os_data["label"] if selected_os_data else selected_os
        
        # Create confirmation embed
        embed = discord.Embed(
            title="⚠️ Confirm Reinstall",
            description=f"Are you sure you want to reinstall **{self.container_name}**?",
            color=0xffaa00
        )
        
        # Set thumbnail if URL is provided
        if THUMBNAIL_URL:
            embed.set_thumbnail(url=THUMBNAIL_URL)
        
        # Set footer with timestamp and icon
        embed.set_footer(
            text=f"{BOT_NAME} VPS Manager • {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            icon_url=THUMBNAIL_URL
        )
        
        details = f"**Container:** `{self.container_name}`\n"
        details += f"**New OS:** {os_display}\n"
        details += f"**Current OS:** {self.current_os}\n\n"
        details += "⚠️ **WARNING:** This will erase ALL data on this VPS!\n"
        details += "This action cannot be undone."
        
        embed.add_field(name="📋 Reinstall Details", value=details, inline=False)
        
        # Create confirmation buttons
        view = discord.ui.View()
        confirm_button = discord.ui.Button(label="✅ Confirm Reinstall", style=discord.ButtonStyle.danger)
        cancel_button = discord.ui.Button(label="❌ Cancel", style=discord.ButtonStyle.secondary)
        
        async def confirm_callback(confirm_interaction):
            await self.perform_reinstall(confirm_interaction, selected_os)
        
        async def cancel_callback(cancel_interaction):
            await cancel_interaction.response.edit_message(
                embed=create_info_embed("Cancelled", "Reinstall operation cancelled."),
                view=None
            )
        
        confirm_button.callback = confirm_callback
        cancel_button.callback = cancel_callback
        
        view.add_item(confirm_button)
        view.add_item(cancel_button)
        
        await interaction.response.edit_message(embed=embed, view=view)
    
    async def perform_reinstall(self, interaction: discord.Interaction, selected_os):
        await interaction.response.defer()
        
        # Update message to show progress
        progress_embed = create_info_embed(
            "Reinstalling VPS", 
            f"Please wait while we reinstall **{self.container_name}** with **{selected_os}**...\n\n"
            f"⏳ **Step 1/4:** Stopping container..."
        )
        await interaction.edit_original_response(embed=progress_embed, view=None)
        
        try:
            # Get resource values from VPS
            ram_gb = int(self.vps_data_entry['ram'].replace('GB', ''))
            cpu = int(self.vps_data_entry['cpu'])
            storage_gb = int(self.vps_data_entry['storage'].replace('GB', ''))
            ram_mb = ram_gb * 1024
            
            # Step 1: Stop and delete the container
            progress_embed.description = f"⏳ **Step 2/4:** Removing old container..."
            await interaction.edit_original_response(embed=progress_embed)
            
            try:
                await execute_lxc(f"lxc stop {self.container_name} --force", timeout=60)
            except:
                pass  # Container might not be running
            
            await execute_lxc(f"lxc delete {self.container_name} --force", timeout=60)
            
            # Step 2: Create new container with selected OS
            progress_embed.description = f"⏳ **Step 3/4:** Creating new container with {selected_os}..."
            await interaction.edit_original_response(embed=progress_embed)
            
            await execute_lxc(f"lxc init {selected_os} {self.container_name} -s {DEFAULT_STORAGE_POOL}")
            await execute_lxc(f"lxc config set {self.container_name} limits.memory {ram_mb}MB")
            await execute_lxc(f"lxc config set {self.container_name} limits.cpu {cpu}")
            await execute_lxc(f"lxc config device set {self.container_name} root size={storage_gb}GB")
            await apply_lxc_config(self.container_name)
            
            # Step 3: Start and configure
            progress_embed.description = f"⏳ **Step 4/4:** Starting and configuring VPS..."
            await interaction.edit_original_response(embed=progress_embed)
            
            await execute_lxc(f"lxc start {self.container_name}")
            await apply_internal_permissions(self.container_name)
            
            # Update VPS data
            target_vps = vps_data[self.owner_id][self.actual_idx]
            target_vps["os_version"] = selected_os
            target_vps["status"] = "running"
            target_vps["suspended"] = False
            target_vps["created_at"] = datetime.now().isoformat()
            config_str = f"{ram_gb}GB RAM / {cpu} CPU / {storage_gb}GB Disk"
            target_vps["config"] = config_str
            save_vps_data()
            
            # Success embed
            success_embed = discord.Embed(
                title="✅ Reinstall Complete",
                description=f"VPS **{self.container_name}** has been successfully reinstalled!",
                color=0x00ff88
            )
            
            # Set thumbnail if URL is provided
            if THUMBNAIL_URL:
                success_embed.set_thumbnail(url=THUMBNAIL_URL)
            
            # Set footer with timestamp and icon
            success_embed.set_footer(
                text=f"{BOT_NAME} VPS Manager • {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                icon_url=THUMBNAIL_URL
            )
            
            # Find OS display name
            os_display = selected_os
            for o in OS_OPTIONS:
                if o["value"] == selected_os:
                    os_display = o["label"]
                    break
            
            details = f"**Container:** `{self.container_name}`\n"
            details += f"**New OS:** {os_display}\n"
            details += f"**Resources:** {ram_gb}GB RAM / {cpu} CPU / {storage_gb}GB Disk"
            
            success_embed.add_field(name="📋 New Configuration", value=details, inline=False)
            success_embed.add_field(name="✨ Features", 
                                  value="• Nesting, Privileged, FUSE\n• Docker-ready with kernel modules\n• Unprivileged ports from 0", 
                                  inline=False)
            
            await interaction.edit_original_response(embed=success_embed)
            
            # Refresh the parent view
            if self.parent_view and self.parent_view.selected_index is not None:
                new_embed = await self.parent_view.create_vps_embed(self.parent_view.selected_index)
                await self.parent_view.message.edit(embed=new_embed, view=self.parent_view)
            
        except Exception as e:
            error_embed = create_error_embed("Reinstall Failed", f"Error: {str(e)}")
            await interaction.edit_original_response(embed=error_embed)
    
    async def cancel_callback(self, interaction: discord.Interaction):
        if str(interaction.user.id) != str(self.ctx.author.id):
            await interaction.response.send_message(embed=create_error_embed("Access Denied", "Only the command author can cancel."), ephemeral=True)
            return
        
        await interaction.response.edit_message(
            embed=create_info_embed("Cancelled", "Reinstall operation cancelled."),
            view=None
        )
        
        # Refresh the parent view
        if self.parent_view and self.parent_view.selected_index is not None:
            new_embed = await self.parent_view.create_vps_embed(self.parent_view.selected_index)
            await self.parent_view.message.edit(embed=new_embed, view=self.parent_view)

# ============ VPS MANAGEMENT COMMANDS ============

class ManageView(discord.ui.View):
    def __init__(self, user_id, vps_list, is_shared=False, owner_id=None, is_admin=False, actual_index: Optional[int] = None):
        super().__init__(timeout=300)
        self.user_id = user_id
        self.vps_list = vps_list[:]
        self.selected_index = 0 if vps_list else None
        self.is_shared = is_shared
        self.owner_id = owner_id or user_id
        self.is_admin = is_admin
        self.actual_index = actual_index
        self.indices = list(range(len(vps_list)))
        self.message = None  # Will be set when message is sent
        
        if self.is_shared and self.actual_index is None:
            raise ValueError("actual_index required for shared views")
        
        if len(vps_list) > 1:
            options = [
                discord.SelectOption(
                    label=f"VPS {i+1} ({v.get('plan_name', 'Custom')})",
                    description=f"Status: {v.get('status', 'unknown')}",
                    value=str(i)
                ) for i, v in enumerate(vps_list)
            ]
            self.select = discord.ui.Select(placeholder="Select a VPS to manage", options=options)
            self.select.callback = self.select_vps
            self.add_item(self.select)
        else:
            self.add_action_buttons()
    
    async def create_vps_embed(self, index):
        vps = self.vps_list[index]
        status = vps.get('status', 'unknown')
        suspended = vps.get('suspended', False)
        whitelisted = vps.get('whitelisted', False)
        purge_protected = vps.get('purge_protected', False)
        status_color = 0x00ff88 if status == 'running' and not suspended else 0xffaa00 if suspended else 0xff3366
        container_name = vps['container_name']
        
        lxc_status = await get_container_status(container_name)
        cpu_usage = await get_container_cpu(container_name)
        memory_usage = await get_container_memory(container_name)
        disk_usage = await get_container_disk(container_name)
        uptime = await get_container_uptime(container_name)
        
        status_text = f"{lxc_status.upper()}"
        if suspended:
            status_text += " (SUSPENDED)"
        if whitelisted:
            status_text += " (WHITELISTED)"
        
        purge_text = "🟢 Enabled" if purge_protected else "🔴 Disabled"
        
        owner_text = ""
        if self.is_admin and self.owner_id != self.user_id:
            try:
                owner_user = await bot.fetch_user(int(self.owner_id))
                owner_text = f"\n**Owner:** {owner_user.mention}"
            except:
                owner_text = f"\n**Owner ID:** {self.owner_id}"
        
        embed = discord.Embed(
            title=f"🖥️ VPS Management",
            description=f"Managing VPS #{index + 1}: `{container_name}`{owner_text}",
            color=status_color
        )
        
        # Set thumbnail if URL is provided
        if THUMBNAIL_URL:
            embed.set_thumbnail(url=THUMBNAIL_URL)
        
        # Set footer with timestamp and icon
        embed.set_footer(
            text=f"{BOT_NAME} VPS Manager • {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            icon_url=THUMBNAIL_URL
        )
        
        # Find OS display name
        os_display = vps.get('os_version', 'ubuntu:22.04')
        for o in OS_OPTIONS:
            if o["value"] == os_display:
                os_display = o["label"]
                break
        
        resource_info = f"**Plan:** {vps.get('plan_name', 'Custom')}\n"
        resource_info += f"**Status:** {status_text}\n"
        resource_info += f"**RAM:** {vps['ram']}\n"
        resource_info += f"**CPU:** {vps['cpu']} Cores\n"
        resource_info += f"**Storage:** {vps['storage']}\n"
        resource_info += f"**OS:** {os_display}\n"
        resource_info += f"**Uptime:** {uptime}\n"
        resource_info += f"**Purge Protection:** {purge_text}"
        
        embed.add_field(name="⌯⌲ Resources", value=resource_info, inline=False)
        
        if suspended:
            embed.add_field(name="⌯⌲ Suspended", value="This VPS is suspended. Contact an admin to unsuspend.", inline=False)
        if whitelisted:
            embed.add_field(name="⌯⌲ Whitelisted", value="This VPS is exempt from auto-suspension.", inline=False)
        if purge_protected:
            embed.add_field(name="⌯⌲ Purge Protected", value="This VPS is protected from `.purge-vm-all` command.", inline=False)
        
        live_stats = f"**CPU Usage:** {cpu_usage}\n**Memory:** {memory_usage}\n**Disk:** {disk_usage}"
        embed.add_field(name="⌯⌲ Live Usage", value=live_stats, inline=False)
        embed.add_field(name="⌯⌲ Controls", value="Use the buttons below to manage your VPS", inline=False)
        
        return embed
    
    def add_action_buttons(self):
        # Modern button styling with emojis
        if not self.is_shared and not self.is_admin:
            reinstall_button = discord.ui.Button(label="Reinstall", style=discord.ButtonStyle.danger, emoji="🔄")
            reinstall_button.callback = lambda inter: self.action_callback(inter, 'reinstall')
            self.add_item(reinstall_button)
        
        start_button = discord.ui.Button(label="Start", style=discord.ButtonStyle.success, emoji="▶️")
        start_button.callback = lambda inter: self.action_callback(inter, 'start')
        
        stop_button = discord.ui.Button(label="Stop", style=discord.ButtonStyle.secondary, emoji="⏹️")
        stop_button.callback = lambda inter: self.action_callback(inter, 'stop')
        
        ssh_button = discord.ui.Button(label="SSH", style=discord.ButtonStyle.primary, emoji="🔑")
        ssh_button.callback = lambda inter: self.action_callback(inter, 'ssh')
        
        stats_button = discord.ui.Button(label="Stats", style=discord.ButtonStyle.secondary, emoji="📊")
        stats_button.callback = lambda inter: self.action_callback(inter, 'stats')
        
        self.add_item(start_button)
        self.add_item(stop_button)
        self.add_item(ssh_button)
        self.add_item(stats_button)
    
    async def select_vps(self, interaction: discord.Interaction):
        if str(interaction.user.id) != self.user_id and not self.is_admin:
            await interaction.response.send_message(embed=create_error_embed("Access Denied", "This is not your VPS!"), ephemeral=True)
            return
        
        self.selected_index = int(self.select.values[0])
        new_embed = await self.create_vps_embed(self.selected_index)
        self.clear_items()
        self.add_action_buttons()
        await interaction.response.edit_message(embed=new_embed, view=self)
        self.message = await interaction.original_response()
    
    async def action_callback(self, interaction: discord.Interaction, action: str):
        if str(interaction.user.id) != self.user_id and not self.is_admin:
            await interaction.response.send_message(embed=create_error_embed("Access Denied", "This is not your VPS!"), ephemeral=True)
            return
        
        if self.selected_index is None and len(self.vps_list) == 1:
            self.selected_index = 0
        
        if self.selected_index is None:
            await interaction.response.send_message(embed=create_error_embed("No VPS Selected", "Please select a VPS first."), ephemeral=True)
            return
        
        actual_idx = self.actual_index if self.is_shared else self.indices[self.selected_index]
        target_vps = vps_data[self.owner_id][actual_idx]
        suspended = target_vps.get('suspended', False)
        
        if suspended and not self.is_admin and action not in ['stats']:
            await interaction.response.send_message(embed=create_error_embed("Access Denied", "This VPS is suspended. Contact an admin to unsuspend."), ephemeral=True)
            return
        
        container_name = target_vps["container_name"]
        
        if action == 'stats':
            status = await get_container_status(container_name)
            cpu_usage = await get_container_cpu(container_name)
            memory_usage = await get_container_memory(container_name)
            disk_usage = await get_container_disk(container_name)
            uptime = await get_container_uptime(container_name)
            
            stats_embed = create_info_embed("Live Statistics", f"Real-time stats for `{container_name}`")
            add_field(stats_embed, "Status", f"`{status.upper()}`", True)
            add_field(stats_embed, "CPU", cpu_usage, True)
            add_field(stats_embed, "Memory", memory_usage, True)
            add_field(stats_embed, "Disk", disk_usage, True)
            add_field(stats_embed, "Uptime", uptime, True)
            
            await interaction.response.send_message(embed=stats_embed, ephemeral=True)
            return
        
        # Handle reinstall action with modern OS selection
        if action == 'reinstall':
            if self.is_shared or self.is_admin:
                await interaction.response.send_message(embed=create_error_embed("Access Denied", "Only the VPS owner can reinstall!"), ephemeral=True)
                return
            
            if suspended:
                await interaction.response.send_message(embed=create_error_embed("Cannot Reinstall", "Unsuspend the VPS first."), ephemeral=True)
                return
            
            # Create modern OS selection view
            os_view = ReinstallOSView(
                ctx=self.ctx if hasattr(self, 'ctx') else interaction,
                container_name=container_name,
                owner_id=self.owner_id,
                actual_idx=actual_idx,
                vps_data_entry=target_vps,
                parent_view=self
            )
            
            # Get current OS display name
            current_os_display = target_vps.get('os_version', 'ubuntu:22.04')
            for o in OS_OPTIONS:
                if o["value"] == current_os_display:
                    current_os_display = o["label"]
                    break
            
            embed = discord.Embed(
                title="🔄 Reinstall VPS",
                description=f"Choose a new operating system for **{container_name}**",
                color=0xffaa00
            )
            
            # Set thumbnail if URL is provided
            if THUMBNAIL_URL:
                embed.set_thumbnail(url=THUMBNAIL_URL)
            
            # Set footer with timestamp and icon
            embed.set_footer(
                text=f"{BOT_NAME} VPS Manager • {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                icon_url=THUMBNAIL_URL
            )
            
            embed.add_field(name="📋 Current Configuration", 
                          value=f"**Container:** `{container_name}`\n**Current OS:** {current_os_display}", 
                          inline=False)
            embed.add_field(name="⚠️ Warning", 
                          value="This will erase ALL data on this VPS. Make sure to backup important files first.", 
                          inline=False)
            
            await interaction.response.send_message(embed=embed, view=os_view, ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True)
        
        if action == 'start':
            try:
                await execute_lxc(f"lxc start {container_name}")
                target_vps["status"] = "running"
                target_vps["suspended"] = False
                save_vps_data()
                await apply_internal_permissions(container_name)
                await interaction.followup.send(embed=create_success_embed("VPS Started", f"VPS `{container_name}` is now running!"), ephemeral=True)
            except Exception as e:
                await interaction.followup.send(embed=create_error_embed("Start Failed", str(e)), ephemeral=True)
        
        elif action == 'stop':
            try:
                await execute_lxc(f"lxc stop {container_name}", timeout=120)
                target_vps["status"] = "stopped"
                save_vps_data()
                await interaction.followup.send(embed=create_success_embed("VPS Stopped", f"VPS `{container_name}` has been stopped!"), ephemeral=True)
            except Exception as e:
                await interaction.followup.send(embed=create_error_embed("Stop Failed", str(e)), ephemeral=True)
        
        elif action == 'ssh':
            if suspended:
                await interaction.followup.send(embed=create_error_embed("Access Denied", "Cannot access suspended VPS."), ephemeral=True)
                return
            
            await interaction.followup.send(embed=create_info_embed("SSH Access", "Generating SSH connection..."), ephemeral=True)
            
            try:
                check_proc = await asyncio.create_subprocess_exec(
                    "lxc", "exec", container_name, "--", "which", "tmate",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await check_proc.communicate()
                
                if check_proc.returncode != 0:
                    await interaction.followup.send(embed=create_info_embed("Installing SSH", "Installing tmate..."), ephemeral=True)
                    await execute_lxc(f"lxc exec {container_name} -- apt-get update -y")
                    await execute_lxc(f"lxc exec {container_name} -- apt-get install tmate -y")
                    await interaction.followup.send(embed=create_success_embed("Installed", "SSH service installed!"), ephemeral=True)
                
                session_name = f"{BOT_NAME.lower()}-session-{datetime.now().strftime('%Y%m%d%H%M%S')}"
                await execute_lxc(f"lxc exec {container_name} -- tmate -S /tmp/{session_name}.sock new-session -d")
                await asyncio.sleep(3)
                
                ssh_proc = await asyncio.create_subprocess_exec(
                    "lxc", "exec", container_name, "--", "tmate", "-S", f"/tmp/{session_name}.sock", "display", "-p", "#{tmate_ssh}",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await ssh_proc.communicate()
                ssh_url = stdout.decode().strip() if stdout else None
                
                if ssh_url:
                    try:
                        ssh_embed = create_info_embed("🔑 SSH Access", f"SSH connection for VPS `{container_name}`:")
                        add_field(ssh_embed, "Command", f"```{ssh_url}```", False)
                        add_field(ssh_embed, "Security", "This link is temporary. Do not share it.", False)
                        
                        await interaction.user.send(embed=ssh_embed)
                        await interaction.followup.send(embed=create_success_embed("SSH Sent", f"Check your DMs for SSH link!"), ephemeral=True)
                    except discord.Forbidden:
                        await interaction.followup.send(embed=create_error_embed("DM Failed", "Enable DMs to receive SSH link!"), ephemeral=True)
                else:
                    error_msg = stderr.decode().strip() if stderr else "Unknown error"
                    await interaction.followup.send(embed=create_error_embed("SSH Failed", error_msg), ephemeral=True)
            
            except Exception as e:
                await interaction.followup.send(embed=create_error_embed("SSH Error", str(e)), ephemeral=True)
        
        if self.selected_index is not None:
            new_embed = await self.create_vps_embed(self.selected_index)
            await interaction.edit_original_response(embed=new_embed, view=self)
            self.message = await interaction.original_response()

@bot.command(name='manage')
@commands.cooldown(1, 5, commands.BucketType.user)
async def manage_vps(ctx, user: discord.Member = None):
    """Manage your VPS with modern controls"""
    if not await maintenance_check(ctx):
        return
    
    if user:
        user_id_check = str(ctx.author.id)
        if user_id_check != str(MAIN_ADMIN_ID) and user_id_check not in admin_data.get("admins", []):
            await ctx.send(embed=create_error_embed("Access Denied", "Only admins can manage other users' VPS."))
            return
        
        user_id = str(user.id)
        vps_list = vps_data.get(user_id, [])
        if not vps_list:
            embed = create_no_vps_embed()
            embed.title = f"⭐ {BOT_NAME} - No VPS Found"
            embed.description = f"{user.mention} doesn't have any VPS."
            await ctx.send(embed=embed)
            return
        
        view = ManageView(str(ctx.author.id), vps_list, is_admin=True, owner_id=user_id)
        embed = await view.create_vps_embed(0)
        msg = await ctx.send(embed=embed, view=view)
        view.message = msg
    
    else:
        user_id = str(ctx.author.id)
        vps_list = vps_data.get(user_id, [])
        
        if not vps_list:
            await ctx.send(embed=create_no_vps_embed())
            return
        
        view = ManageView(user_id, vps_list)
        embed = await view.create_vps_embed(0)
        msg = await ctx.send(embed=embed, view=view)
        view.message = msg
        view.ctx = ctx  # Store ctx for later use

# ============ SHARE COMMANDS ============

@bot.command(name='share-user')
@commands.cooldown(1, 3, commands.BucketType.user)
async def share_user(ctx, shared_user: discord.Member, vps_number: int):
    """Share VPS access with another user"""
    if not await maintenance_check(ctx):
        return
    
    user_id = str(ctx.author.id)
    shared_user_id = str(shared_user.id)
    
    if user_id not in vps_data or vps_number < 1 or vps_number > len(vps_data[user_id]):
        await ctx.send(embed=create_error_embed("Invalid VPS", "Invalid VPS number or you don't have a VPS."))
        return
    
    vps = vps_data[user_id][vps_number - 1]
    if "shared_with" not in vps:
        vps["shared_with"] = []
    
    if shared_user_id in vps["shared_with"]:
        await ctx.send(embed=create_error_embed("Already Shared", f"{shared_user.mention} already has access to this VPS!"))
        return
    
    vps["shared_with"].append(shared_user_id)
    save_vps_data()
    
    embed = create_success_embed("VPS Shared", f"VPS #{vps_number} shared with {shared_user.mention}!")
    await ctx.send(embed=embed)

@bot.command(name='share-ruser')
@commands.cooldown(1, 3, commands.BucketType.user)
async def revoke_share(ctx, shared_user: discord.Member, vps_number: int):
    """Revoke VPS access from another user"""
    if not await maintenance_check(ctx):
        return
    
    user_id = str(ctx.author.id)
    shared_user_id = str(shared_user.id)
    
    if user_id not in vps_data or vps_number < 1 or vps_number > len(vps_data[user_id]):
        await ctx.send(embed=create_error_embed("Invalid VPS", "Invalid VPS number or you don't have a VPS."))
        return
    
    vps = vps_data[user_id][vps_number - 1]
    if "shared_with" not in vps:
        vps["shared_with"] = []
    
    if shared_user_id not in vps["shared_with"]:
        await ctx.send(embed=create_error_embed("Not Shared", f"{shared_user.mention} doesn't have access to this VPS!"))
        return
    
    vps["shared_with"].remove(shared_user_id)
    save_vps_data()
    
    embed = create_success_embed("Access Revoked", f"Access to VPS #{vps_number} revoked from {shared_user.mention}!")
    await ctx.send(embed=embed)

@bot.command(name='manage-shared')
@commands.cooldown(1, 3, commands.BucketType.user)
async def manage_shared_vps(ctx, owner: discord.Member, vps_number: int):
    """Manage a VPS that has been shared with you"""
    if not await maintenance_check(ctx):
        return
    
    owner_id = str(owner.id)
    user_id = str(ctx.author.id)
    
    if owner_id not in vps_data or vps_number < 1 or vps_number > len(vps_data[owner_id]):
        await ctx.send(embed=create_error_embed("Invalid VPS", "Invalid VPS number or owner doesn't have a VPS."))
        return
    
    vps = vps_data[owner_id][vps_number - 1]
    if user_id not in vps.get("shared_with", []):
        await ctx.send(embed=create_error_embed("Access Denied", "You do not have access to this VPS."))
        return
    
    view = ManageView(user_id, [vps], is_shared=True, owner_id=owner_id, actual_index=vps_number - 1)
    embed = await view.create_vps_embed(0)
    msg = await ctx.send(embed=embed, view=view)
    view.message = msg
    view.ctx = ctx

# ============ ADMIN INFO COMMANDS ============

@bot.command(name='vpsinfo')
@is_admin()
@commands.cooldown(1, 3, commands.BucketType.user)
async def vps_info(ctx, container_name: str):
    """VPS information"""
    if not container_name:
        await ctx.send(embed=create_error_embed("Usage", f"Usage: {PREFIX}vpsinfo <container_name>"))
        return
    
    found_vps = None
    found_user = None
    user_id = None
    
    for uid, vps_list in vps_data.items():
        for vps in vps_list:
            if vps['container_name'] == container_name:
                found_vps = vps
                user_id = uid
                try:
                    found_user = await bot.fetch_user(int(uid))
                except:
                    found_user = None
                break
        if found_vps:
            break
    
    if not found_vps:
        await ctx.send(embed=create_error_embed("VPS Not Found", f"No VPS found with container name: `{container_name}`"))
        return
    
    status = await get_container_status(container_name)
    cpu = await get_container_cpu(container_name)
    memory = await get_container_memory(container_name)
    disk = await get_container_disk(container_name)
    uptime = await get_container_uptime(container_name)
    
    # Find OS display name
    os_display = found_vps.get('os_version', 'ubuntu:22.04')
    for o in OS_OPTIONS:
        if o["value"] == os_display:
            os_display = o["label"]
            break
    
    embed = discord.Embed(
        title=f"⭐ VPS Information - {container_name}",
        description=f"Details for VPS",
        color=0x1a1a1a
    )
    
    # Set thumbnail if URL is provided
    if THUMBNAIL_URL:
        embed.set_thumbnail(url=THUMBNAIL_URL)
    
    # Set footer with timestamp and icon
    embed.set_footer(
        text=f"{BOT_NAME} VPS Manager • {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        icon_url=THUMBNAIL_URL
    )
    
    embed.add_field(name="**Owner**", value=found_user.mention if found_user else f"ID: {user_id}", inline=True)
    embed.add_field(name="**Status**", value=status.upper(), inline=True)
    embed.add_field(name="**Plan**", value=found_vps.get('plan_name', 'Custom'), inline=True)
    embed.add_field(name="**Purge Protected**", value="✅ Yes" if found_vps.get('purge_protected', False) else "❌ No", inline=True)
    
    resources = f"**RAM:** {found_vps['ram']}\n"
    resources += f"**CPU:** {found_vps['cpu']} Cores\n"
    resources += f"**Storage:** {found_vps['storage']}\n"
    resources += f"**OS:** {os_display}"
    embed.add_field(name="**Allocated Resources**", value=resources, inline=False)
    
    live_stats = f"**CPU Usage:** {cpu}\n"
    live_stats += f"**Memory:** {memory}\n"
    live_stats += f"**Disk:** {disk}\n"
    live_stats += f"**Uptime:** {uptime}"
    embed.add_field(name="**Live Statistics**", value=live_stats, inline=False)
    
    if found_vps.get('suspended', False):
        embed.add_field(name="**Suspended**", value=f"Reason: {found_vps.get('suspended_reason', 'No reason')}", inline=False)
    
    if found_vps.get('whitelisted', False):
        embed.add_field(name="**Whitelisted**", value="Exempt from auto-suspension", inline=False)
    
    created = found_vps.get('created_at', 'Unknown')[:19].replace('T', ' ')
    embed.add_field(name="**Created**", value=created, inline=False)
    
    await ctx.send(embed=embed)

@bot.command(name='vps-stats')
@is_admin()
@commands.cooldown(1, 3, commands.BucketType.user)
async def vps_stats(ctx, container_name: str):
    """VPS stats"""
    cpu = await get_container_cpu(container_name)
    memory = await get_container_memory(container_name)
    disk = await get_container_disk(container_name)
    uptime = await get_container_uptime(container_name)
    
    embed = create_info_embed(f"VPS Stats - {container_name}", 
        f"**CPU Usage:** {cpu}\n**Memory:** {memory}\n**Disk:** {disk}\n**Uptime:** {uptime}")
    await ctx.send(embed=embed)

@bot.command(name='restart-vps')
@is_admin()
@commands.cooldown(1, 10, commands.BucketType.user)
async def restart_vps(ctx, container_name: str):
    """Restart VPS"""
    await ctx.send(embed=create_info_embed("Restarting VPS", f"Restarting VPS `{container_name}`..."))
    
    try:
        await execute_lxc(f"lxc restart {container_name}")
        
        for user_id, vps_list in vps_data.items():
            for vps in vps_list:
                if vps['container_name'] == container_name:
                    vps['status'] = 'running'
                    vps['suspended'] = False
                    save_vps_data()
                    break
        
        await apply_internal_permissions(container_name)
        
        embed = create_success_embed("VPS Restarted", f"VPS `{container_name}` has been restarted successfully!")
        await ctx.send(embed=embed)
    
    except Exception as e:
        await ctx.send(embed=create_error_embed("Restart Failed", f"Error: {str(e)}"))

@bot.command(name='clone-vps')
@is_admin()
@commands.cooldown(1, 30, commands.BucketType.user)
async def clone_vps(ctx, container_name: str, new_name: str = None):
    """Clone VPS"""
    if not new_name:
        new_name = f"{container_name}-clone-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    
    await ctx.send(embed=create_info_embed("Cloning VPS", f"Cloning `{container_name}` to `{new_name}`..."))
    
    try:
        await execute_lxc(f"lxc copy {container_name} {new_name}")
        embed = create_success_embed("VPS Cloned", f"VPS `{container_name}` cloned to `{new_name}`")
        await ctx.send(embed=embed)
    except Exception as e:
        await ctx.send(embed=create_error_embed("Clone Failed", f"Error: {str(e)}"))

@bot.command(name='snapshot')
@is_admin()
@commands.cooldown(1, 30, commands.BucketType.user)
async def create_snapshot(ctx, container_name: str, snap_name: str = None):
    """Create snapshot"""
    if not snap_name:
        snap_name = f"snap-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    
    await ctx.send(embed=create_info_embed("Creating Snapshot", f"Creating snapshot `{snap_name}` for `{container_name}`..."))
    
    try:
        await execute_lxc(f"lxc snapshot {container_name} {snap_name}")
        embed = create_success_embed("Snapshot Created", f"Snapshot `{snap_name}` created for `{container_name}`")
        await ctx.send(embed=embed)
    except Exception as e:
        await ctx.send(embed=create_error_embed("Snapshot Failed", f"Error: {str(e)}"))

@bot.command(name='restore-backup')
@is_admin()
@commands.cooldown(1, 30, commands.BucketType.user)
async def restore_backup(ctx, container_name: str, snap_name: str):
    """Restore VPS Data"""
    await ctx.send(embed=create_info_embed("Restoring Backup", f"Restoring `{container_name}` from snapshot `{snap_name}`..."))
    
    try:
        await execute_lxc(f"lxc restore {container_name} {snap_name}")
        embed = create_success_embed("Backup Restored", f"VPS `{container_name}` restored from snapshot `{snap_name}`")
        await ctx.send(embed=embed)
    except Exception as e:
        await ctx.send(embed=create_error_embed("Restore Failed", f"Error: {str(e)}"))

# ============ BOT SYSTEM COMMANDS ============

@bot.command(name='addinv')
@is_admin()
@commands.cooldown(1, 2, commands.BucketType.user)
async def add_invites(ctx, user: discord.Member, amount: int):
    """Add invites to user"""
    if amount <= 0:
        await ctx.send(embed=create_error_embed("Invalid Amount", "Amount must be positive."))
        return
    
    update_user_stats(str(user.id), invites=amount)
    stats = get_user_stats(str(user.id))
    
    embed = create_success_embed("Invites Added", f"Added **{amount}** invites to {user.mention}")
    add_field(embed, "Current Stats", 
              f"**Total Invites:** {stats['invites']}\n**Boosts:** {stats['boosts']}", 
              False)
    await ctx.send(embed=embed)

@bot.command(name='removeinv')
@is_admin()
@commands.cooldown(1, 2, commands.BucketType.user)
async def remove_invites(ctx, user: discord.Member, amount: int):
    """Remove invites from user"""
    if amount <= 0:
        await ctx.send(embed=create_error_embed("Invalid Amount", "Amount must be positive."))
        return
    
    stats = get_user_stats(str(user.id))
    if stats['invites'] < amount:
        amount = stats['invites']
    
    update_user_stats(str(user.id), invites=-amount)
    new_stats = get_user_stats(str(user.id))
    
    embed = create_success_embed("Invites Removed", f"Removed **{amount}** invites from {user.mention}")
    add_field(embed, "Current Stats", 
              f"**Total Invites:** {new_stats['invites']}\n**Boosts:** {new_stats['boosts']}", 
              False)
    await ctx.send(embed=embed)

@bot.command(name='addboost')
@is_admin()
@commands.cooldown(1, 2, commands.BucketType.user)
async def add_boosts(ctx, user: discord.Member, amount: int):
    """Add boosts to user"""
    if amount <= 0:
        await ctx.send(embed=create_error_embed("Invalid Amount", "Amount must be positive."))
        return
    
    update_user_stats(str(user.id), boosts=amount)
    stats = get_user_stats(str(user.id))
    
    embed = create_success_embed("Boosts Added", f"Added **{amount}** boosts to {user.mention}")
    add_field(embed, "Current Stats", 
              f"**Invites:** {stats['invites']}\n**Total Boosts:** {stats['boosts']}", 
              False)
    await ctx.send(embed=embed)

@bot.command(name='removeboost')
@is_admin()
@commands.cooldown(1, 2, commands.BucketType.user)
async def remove_boosts(ctx, user: discord.Member, amount: int):
    """Remove boosts from user"""
    if amount <= 0:
        await ctx.send(embed=create_error_embed("Invalid Amount", "Amount must be positive."))
        return
    
    stats = get_user_stats(str(user.id))
    if stats['boosts'] < amount:
        amount = stats['boosts']
    
    update_user_stats(str(user.id), boosts=-amount)
    new_stats = get_user_stats(str(user.id))
    
    embed = create_success_embed("Boosts Removed", f"Removed **{amount}** boosts from {user.mention}")
    add_field(embed, "Current Stats", 
              f"**Invites:** {new_stats['invites']}\n**Total Boosts:** {new_stats['boosts']}", 
              False)
    await ctx.send(embed=embed)

@bot.command(name='user-stats')
@is_admin()
@commands.cooldown(1, 2, commands.BucketType.user)
async def user_stats_cmd(ctx, user: discord.Member):
    """View user stats"""
    stats = get_user_stats(str(user.id))
    
    embed = create_info_embed(f"User Stats - {user.name}", f"Statistics for {user.mention}")
    add_field(embed, "📨 Invites", str(stats['invites']), True)
    add_field(embed, "🚀 Boosts", str(stats['boosts']), True)
    add_field(embed, "🖥️ VPS Owned", str(len(vps_data.get(str(user.id), []))), True)
    add_field(embed, "🎁 Claimed VPS", str(stats.get('claimed_vps_count', 0)), True)
    
    await ctx.send(embed=embed)

# ============ PURGE PROTECTION COMMANDS ============

@bot.command(name='purge-prot')
@is_main_admin()
@commands.cooldown(1, 3, commands.BucketType.user)
async def purge_protect(ctx, user: discord.Member, vps_number: int = None):
    """Protect a user's VPS from .purge-vm-all command
    Usage: .purge-prot @user <vps_number> - Protect specific VPS
           .purge-prot @user - Protect all VPS of that user
    """
    user_id = str(user.id)
    
    if user_id not in vps_data or not vps_data[user_id]:
        await ctx.send(embed=create_error_embed("No VPS Found", f"{user.mention} doesn't have any VPS."))
        return
    
    protected_count = 0
    
    if vps_number is None:
        # Protect all VPS of the user
        for vps in vps_data[user_id]:
            if not vps.get('purge_protected', False):
                vps['purge_protected'] = True
                log_purge_protection(vps['container_name'], user_id, 'protect', str(ctx.author.id))
                protected_count += 1
        
        save_vps_data()
        
        if protected_count == 0:
            embed = create_info_embed("Already Protected", f"All VPS of {user.mention} are already purge protected.")
        else:
            embed = create_success_embed("Purge Protection Enabled", 
                f"Protected **{protected_count}** VPS of {user.mention} from `.purge-vm-all`.")
        
        await ctx.send(embed=embed)
    
    else:
        # Protect specific VPS
        if vps_number < 1 or vps_number > len(vps_data[user_id]):
            await ctx.send(embed=create_error_embed("Invalid VPS Number", 
                f"VPS number must be between 1 and {len(vps_data[user_id])}."))
            return
        
        vps = vps_data[user_id][vps_number - 1]
        
        if vps.get('purge_protected', False):
            embed = create_info_embed("Already Protected", 
                f"VPS #{vps_number} of {user.mention} is already purge protected.")
        else:
            vps['purge_protected'] = True
            save_vps_data()
            log_purge_protection(vps['container_name'], user_id, 'protect', str(ctx.author.id))
            
            embed = create_success_embed("Purge Protection Enabled", 
                f"VPS #{vps_number} (`{vps['container_name']}`) of {user.mention} is now protected from `.purge-vm-all`.")
        
        await ctx.send(embed=embed)

@bot.command(name='purge-remove-prot')
@is_main_admin()
@commands.cooldown(1, 3, commands.BucketType.user)
async def purge_remove_protect(ctx, user: discord.Member, vps_number: int = None):
    """Remove purge protection from a user's VPS
    Usage: .purge-remove-prot @user <vps_number> - Remove protection from specific VPS
           .purge-remove-prot @user - Remove protection from all VPS of that user
    """
    user_id = str(user.id)
    
    if user_id not in vps_data or not vps_data[user_id]:
        await ctx.send(embed=create_error_embed("No VPS Found", f"{user.mention} doesn't have any VPS."))
        return
    
    unprotected_count = 0
    
    if vps_number is None:
        # Remove protection from all VPS of the user
        for vps in vps_data[user_id]:
            if vps.get('purge_protected', False):
                vps['purge_protected'] = False
                log_purge_protection(vps['container_name'], user_id, 'remove_protect', str(ctx.author.id))
                unprotected_count += 1
        
        save_vps_data()
        
        if unprotected_count == 0:
            embed = create_info_embed("No Protection Found", f"No purge protected VPS found for {user.mention}.")
        else:
            embed = create_success_embed("Purge Protection Removed", 
                f"Removed protection from **{unprotected_count}** VPS of {user.mention}.")
        
        await ctx.send(embed=embed)
    
    else:
        # Remove protection from specific VPS
        if vps_number < 1 or vps_number > len(vps_data[user_id]):
            await ctx.send(embed=create_error_embed("Invalid VPS Number", 
                f"VPS number must be between 1 and {len(vps_data[user_id])}."))
            return
        
        vps = vps_data[user_id][vps_number - 1]
        
        if not vps.get('purge_protected', False):
            embed = create_info_embed("Not Protected", 
                f"VPS #{vps_number} of {user.mention} is not purge protected.")
        else:
            vps['purge_protected'] = False
            save_vps_data()
            log_purge_protection(vps['container_name'], user_id, 'remove_protect', str(ctx.author.id))
            
            embed = create_success_embed("Purge Protection Removed", 
                f"VPS #{vps_number} (`{vps['container_name']}`) of {user.mention} is no longer protected from `.purge-vm-all`.")
        
        await ctx.send(embed=embed)

@bot.command(name='purge-list-protected')
@is_main_admin()
@commands.cooldown(1, 3, commands.BucketType.user)
async def purge_list_protected(ctx):
    """List all purge protected VPS"""
    
    protected_vps = []
    
    for user_id, vps_list in vps_data.items():
        for vps in vps_list:
            if vps.get('purge_protected', False):
                try:
                    user = await bot.fetch_user(int(user_id))
                    username = user.name
                except:
                    username = f"Unknown User ({user_id})"
                
                protected_vps.append(f"• **{username}** - `{vps['container_name']}` ({vps.get('plan_name', 'Custom')})")
    
    if not protected_vps:
        embed = create_info_embed("Purge Protected VPS", "No purge protected VPS found.")
    else:
        embed = create_info_embed("Purge Protected VPS", f"Found **{len(protected_vps)}** protected VPS")
        
        # Split into multiple fields if too many
        chunks = [protected_vps[i:i+10] for i in range(0, len(protected_vps), 10)]
        for i, chunk in enumerate(chunks):
            add_field(embed, f"Protected VPS {i+1}", "\n".join(chunk), False)
    
    await ctx.send(embed=embed)

# ============ UPDATED ADMIN COMMANDS - SERVER STATS ============

@bot.command(name='serverstats')
@is_admin()
@commands.cooldown(1, 5, commands.BucketType.user)
async def server_stats(ctx):
    """Server statistics - Shows detailed server overview"""
    
    total_users = len(vps_data)
    total_admins = len(admin_data.get("admins", [])) + 1  # +1 for main admin
    
    total_vps = 0
    running_vps = 0
    suspended_vps = 0
    whitelisted_vps = 0
    stopped_vps = 0
    
    total_ram = 0
    total_cpu = 0
    total_storage = 0
    
    for user_id, vps_list in vps_data.items():
        for vps in vps_list:
            total_vps += 1
            
            # Parse resources (remove 'GB' and convert to int)
            try:
                ram_value = int(vps['ram'].replace('GB', '').strip())
                total_ram += ram_value
            except:
                pass
                
            try:
                cpu_value = int(vps['cpu'])
                total_cpu += cpu_value
            except:
                pass
                
            try:
                storage_value = int(vps['storage'].replace('GB', '').strip())
                total_storage += storage_value
            except:
                pass
            
            # Count status
            if vps.get('status') == 'running':
                running_vps += 1
            else:
                stopped_vps += 1
                
            if vps.get('suspended', False):
                suspended_vps += 1
            if vps.get('whitelisted', False):
                whitelisted_vps += 1
    
    # Port statistics
    total_port_allocation = 0
    total_port_used = 0
    
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT SUM(allocated_ports) FROM port_allocations')
    result = cur.fetchone()
    if result and result[0]:
        total_port_allocation = result[0]
    
    cur.execute('SELECT COUNT(*) FROM port_forwards')
    result = cur.fetchone()
    if result and result[0]:
        total_port_used = result[0]
    conn.close()
    
    # Create the embed
    embed = discord.Embed(
        title=f"⭐ {BOT_NAME} - Server Statistics",
        description="## Current server overview",
        color=0x00ccff
    )
    
    # Set thumbnail if URL is provided
    if THUMBNAIL_URL:
        embed.set_thumbnail(url=THUMBNAIL_URL)
    
    # Set footer with timestamp and icon
    embed.set_footer(
        text=f"{BOT_NAME} VPS Manager • {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        icon_url=THUMBNAIL_URL
    )
    
    # Users section
    users_text = f"- **Total Users:** {total_users}\n- **Total Admins:** {total_admins}"
    embed.add_field(name="**Users**", value=users_text, inline=False)
    
    # VPS section
    vps_text = f"- **Total VPS:** {total_vps}\n- **Running:** {running_vps}\n- **Suspended:** {suspended_vps}\n- **Whitelisted:** {whitelisted_vps}\n- **Stopped:** {stopped_vps}"
    embed.add_field(name="**VPS**", value=vps_text, inline=False)
    
    # Resources section
    resources_text = f"- **Total RAM:** {total_ram}GB\n- **Total CPU:** {total_cpu} cores\n- **Total Storage:** {total_storage}GB"
    embed.add_field(name="**Resources**", value=resources_text, inline=False)
    
    # Ports section
    ports_text = f"- **Allocated:** {total_port_allocation}\n- **In Use:** {total_port_used}"
    embed.add_field(name="**Ports**", value=ports_text, inline=False)
    
    await ctx.send(embed=embed)

# ============ UPDATED ADMIN COMMANDS - LIST ALL VPS ============

@bot.command(name='list-all')
@is_admin()
@commands.cooldown(1, 5, commands.BucketType.user)
async def list_all_vps(ctx):
    """List all VPS with detailed user and VPS information"""
    
    total_users = len(vps_data)
    total_vps = 0
    running_vps = 0
    stopped_vps = 0
    suspended_vps = 0
    whitelisted_vps = 0
    
    for user_id, vps_list in vps_data.items():
        for vps in vps_list:
            total_vps += 1
            if vps.get('status') == 'running':
                running_vps += 1
            else:
                stopped_vps += 1
            if vps.get('suspended', False):
                suspended_vps += 1
            if vps.get('whitelisted', False):
                whitelisted_vps += 1
    
    # First embed - System Overview
    embed1 = discord.Embed(
        title=f"⭐ {BOT_NAME} - All VPS Information",
        description="Complete overview of all VPS deployments and user statistics",
        color=0x00ccff
    )
    
    # Set thumbnail if URL is provided
    if THUMBNAIL_URL:
        embed1.set_thumbnail(url=THUMBNAIL_URL)
    
    # Set footer with timestamp and icon
    embed1.set_footer(
        text=f"{BOT_NAME} VPS Manager • {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        icon_url=THUMBNAIL_URL
    )
    
    system_text = f"- **Total Users:** {total_users}\n- **Total VPS:** {total_vps}\n- **Running:** {running_vps}\n- **Stopped:** {stopped_vps}\n- **Suspended:** {suspended_vps}\n- **Whitelisted:** {whitelisted_vps}"
    embed1.add_field(name="**System Overview**", value=system_text, inline=False)
    
    await ctx.send(embed=embed1)
    
    # Second embed - User Summary
    embed2 = discord.Embed(
        title=f"⭐ {BOT_NAME} - User Summary",
        description="Summary of all users and their VPS",
        color=0x00ccff
    )
    
    # Set thumbnail if URL is provided
    if THUMBNAIL_URL:
        embed2.set_thumbnail(url=THUMBNAIL_URL)
    
    # Set footer with timestamp and icon
    embed2.set_footer(
        text=f"{BOT_NAME} VPS Manager • {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        icon_url=THUMBNAIL_URL
    )
    
    user_summaries = []
    for user_id, vps_list in vps_data.items():
        try:
            user = await bot.fetch_user(int(user_id))
            username = f"{user.name} (@{user.name})"
        except:
            username = f"Unknown User ({user_id})"
        
        user_vps_count = len(vps_list)
        user_running = sum(1 for v in vps_list if v.get('status') == 'running')
        user_suspended = sum(1 for v in vps_list if v.get('suspended', False))
        user_whitelisted = sum(1 for v in vps_list if v.get('whitelisted', False))
        
        user_summaries.append(f"- **{username}** - {user_vps_count} VPS ({user_running} running, {user_suspended} suspended, {user_whitelisted} whitelisted)")
    
    # Split into multiple fields if too many users
    chunk_size = 8
    for i in range(0, len(user_summaries), chunk_size):
        chunk = user_summaries[i:i+chunk_size]
        embed2.add_field(name=f"**Users (Part {i//chunk_size + 1})**" if len(user_summaries) > chunk_size else "**Users**", 
                        value="\n".join(chunk), 
                        inline=False)
    
    await ctx.send(embed=embed2)
    
    # Third embed - VPS Details
    embed3 = discord.Embed(
        title=f"⭐ {BOT_NAME} - VPS Details",
        description="List of all VPS deployments",
        color=0x00ccff
    )
    
    # Set thumbnail if URL is provided
    if THUMBNAIL_URL:
        embed3.set_thumbnail(url=THUMBNAIL_URL)
    
    # Set footer with timestamp and icon
    embed3.set_footer(
        text=f"{BOT_NAME} VPS Manager • {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        icon_url=THUMBNAIL_URL
    )
    
    vps_details = []
    for user_id, vps_list in vps_data.items():
        try:
            user = await bot.fetch_user(int(user_id))
            username = user.name
        except:
            username = f"Unknown-User"
        
        # Find OS display name
        for vps in vps_list:
            container_name = vps['container_name']
            config = vps.get('config', f"{vps['ram']} RAM / {vps['cpu']} CPU / {vps['storage']} Disk")
            status = vps.get('status', 'unknown').upper()
            
            vps_details.append(f"- **{username}** - VPS: `{container_name}` - {config} - {status}")
    
    # Split into multiple fields if too many VPS
    chunk_size = 8
    for i in range(0, len(vps_details), chunk_size):
        chunk = vps_details[i:i+chunk_size]
        embed3.add_field(name=f"**VPS List (Part {i//chunk_size + 1})**" if len(vps_details) > chunk_size else "**VPS List**", 
                        value="\n".join(chunk), 
                        inline=False)
    
    await ctx.send(embed=embed3)

# ============ OTHER ADMIN COMMANDS ============

@bot.command(name='admin-add')
@is_main_admin()
@commands.cooldown(1, 3, commands.BucketType.user)
async def admin_add(ctx, user: discord.Member):
    """Add admin"""
    user_id = str(user.id)
    
    if user_id == str(MAIN_ADMIN_ID):
        await ctx.send(embed=create_error_embed("Already Admin", "This user is already the main admin!"))
        return
    
    if user_id in admin_data.get("admins", []):
        await ctx.send(embed=create_error_embed("Already Admin", f"{user.mention} is already an admin!"))
        return
    
    admin_data["admins"].append(user_id)
    save_admin_data()
    
    embed = create_success_embed("Admin Added", f"{user.mention} has been added as an admin!")
    await ctx.send(embed=embed)

@bot.command(name='admin-remove')
@is_main_admin()
@commands.cooldown(1, 3, commands.BucketType.user)
async def admin_remove(ctx, user: discord.Member):
    """Remove admin"""
    user_id = str(user.id)
    
    if user_id == str(MAIN_ADMIN_ID):
        await ctx.send(embed=create_error_embed("Cannot Remove", "You cannot remove the main admin!"))
        return
    
    if user_id not in admin_data.get("admins", []):
        await ctx.send(embed=create_error_embed("Not Admin", f"{user.mention} is not an admin!"))
        return
    
    admin_data["admins"].remove(user_id)
    save_admin_data()
    
    embed = create_success_embed("Admin Removed", f"{user.mention} has been removed as an admin!")
    await ctx.send(embed=embed)

@bot.command(name='admin-list')
@is_main_admin()
@commands.cooldown(1, 3, commands.BucketType.user)
async def admin_list(ctx):
    """List admins"""
    embed = create_info_embed("Admin List", "Current administrators of the system")
    
    try:
        main_admin = await bot.fetch_user(int(MAIN_ADMIN_ID))
        add_field(embed, "👑 Main Admin", main_admin.mention, False)
    except:
        add_field(embed, "👑 Main Admin", f"User ID: {MAIN_ADMIN_ID}", False)
    
    if admin_data['admins']:
        admin_text = []
        for admin_id in admin_data['admins']:
            try:
                admin_user = await bot.fetch_user(int(admin_id))
                admin_text.append(f"• {admin_user.mention}")
            except:
                admin_text.append(f"• User ID: {admin_id}")
        
        add_field(embed, "🛡️ Admins", "\n".join(admin_text), False)
    else:
        add_field(embed, "🛡️ Admins", "No additional admins", False)
    
    await ctx.send(embed=embed)

@bot.command(name='create')
@is_admin()
@commands.cooldown(1, 10, commands.BucketType.user)
async def create_vps(ctx, ram: int, cpu: int, disk: int, user: discord.Member):
    """Create VPS with OS selection"""
    if ram <= 0 or cpu <= 0 or disk <= 0:
        await ctx.send(embed=create_error_embed("Invalid Specs", "RAM, CPU, and Disk must be positive integers."))
        return
    
    embed = create_info_embed("VPS Creation", 
        f"Creating VPS for {user.mention}\n"
        f"**RAM:** {ram}GB\n"
        f"**CPU:** {cpu} Cores\n"
        f"**Disk:** {disk}GB\n\n"
        f"Select OS below.")
    
    view = AdminOSSelectView(ram, cpu, disk, user, ctx)
    await ctx.send(embed=embed, view=view)

class AdminOSSelectView(discord.ui.View):
    def __init__(self, ram: int, cpu: int, disk: int, user: discord.Member, ctx):
        super().__init__(timeout=300)
        self.ram = ram
        self.cpu = cpu
        self.disk = disk
        self.user = user
        self.ctx = ctx
        self.selected_os = None
        
        options = []
        for o in OS_OPTIONS:
            emoji = o.get('emoji', '🐧')
            description = o.get('description', '')
            options.append(discord.SelectOption(
                label=o["label"], 
                value=o["value"], 
                emoji=emoji,
                description=description
            ))
        
        self.select = discord.ui.Select(
            placeholder="Select an OS for the VPS",
            options=options
        )
        self.select.callback = self.select_os
        self.add_item(self.select)
        self.add_item(discord.ui.Button(label="❌ Cancel", style=discord.ButtonStyle.danger, custom_id="cancel", row=1))
    
    async def select_os(self, interaction: discord.Interaction):
        if str(interaction.user.id) != str(self.ctx.author.id):
            await interaction.response.send_message(embed=create_error_embed("Access Denied", "Only the command author can select."), ephemeral=True)
            return
        
        self.selected_os = self.select.values[0]
        await interaction.response.defer()
        
        confirm_view = discord.ui.View()
        confirm_button = discord.ui.Button(label="✅ Confirm", style=discord.ButtonStyle.success, custom_id="confirm")
        cancel_button = discord.ui.Button(label="❌ Cancel", style=discord.ButtonStyle.danger, custom_id="cancel")
        
        async def confirm_callback(confirm_interaction):
            await self.create_vps(confirm_interaction)
        
        async def cancel_callback(cancel_interaction):
            await cancel_interaction.response.edit_message(embed=create_info_embed("Cancelled", "VPS creation cancelled."), view=None)
        
        confirm_button.callback = confirm_callback
        cancel_button.callback = cancel_callback
        
        confirm_view.add_item(confirm_button)
        confirm_view.add_item(cancel_button)
        
        embed = create_info_embed("Confirm VPS Creation", 
            f"**User:** {self.user.mention}\n"
            f"**OS:** {self.selected_os}\n"
            f"**RAM:** {self.ram}GB\n"
            f"**CPU:** {self.cpu} Cores\n"
            f"**Disk:** {self.disk}GB\n\n"
            f"Please confirm to proceed.")
        
        await interaction.edit_original_response(embed=embed, view=confirm_view)
    
    async def create_vps(self, interaction: discord.Interaction):
        await interaction.response.defer()
        
        creating_embed = create_info_embed("Creating VPS", f"Deploying {self.selected_os} VPS for {self.user.mention}...")
        await interaction.edit_original_response(embed=creating_embed, view=None)
        
        user_id = str(self.user.id)
        if user_id not in vps_data:
            vps_data[user_id] = []
        
        vps_count = len(vps_data[user_id]) + 1
        container_name = f"{BOT_NAME.lower()}-vps-{user_id}-{vps_count}"
        ram_mb = self.ram * 1024
        
        try:
            await execute_lxc(f"lxc init {self.selected_os} {container_name} -s {DEFAULT_STORAGE_POOL}")
            await execute_lxc(f"lxc config set {container_name} limits.memory {ram_mb}MB")
            await execute_lxc(f"lxc config set {container_name} limits.cpu {self.cpu}")
            await execute_lxc(f"lxc config device set {container_name} root size={self.disk}GB")
            await apply_lxc_config(container_name)
            await execute_lxc(f"lxc start {container_name}")
            await apply_internal_permissions(container_name)
            
            config_str = f"{self.ram}GB RAM / {self.cpu} CPU / {self.disk}GB Disk"
            vps_info = {
                "container_name": container_name,
                "plan_name": "Custom",
                "ram": f"{self.ram}GB",
                "cpu": str(self.cpu),
                "storage": f"{self.disk}GB",
                "config": config_str,
                "os_version": self.selected_os,
                "status": "running",
                "suspended": False,
                "whitelisted": False,
                "purge_protected": False,
                "suspended_reason": "",
                "suspension_history": [],
                "created_at": datetime.now().isoformat(),
                "shared_with": [],
                "id": None
            }
            vps_data[user_id].append(vps_info)
            save_vps_data()
            
            if self.ctx.guild:
                vps_role = await get_or_create_vps_role(self.ctx.guild)
                if vps_role:
                    try:
                        await self.user.add_roles(vps_role, reason=f"{BOT_NAME} VPS ownership granted")
                    except discord.Forbidden:
                        logger.warning(f"Failed to assign VPS role to {self.user.name}")
            
            success_embed = create_success_embed("VPS Created Successfully")
            add_field(success_embed, "Owner", self.user.mention, True)
            add_field(success_embed, "VPS ID", f"#{vps_count}", True)
            add_field(success_embed, "Container", f"`{container_name}`", True)
            add_field(success_embed, "Resources", f"**RAM:** {self.ram}GB\n**CPU:** {self.cpu} Cores\n**Storage:** {self.disk}GB", False)
            add_field(success_embed, "OS", self.selected_os, True)
            
            await interaction.followup.send(embed=success_embed)
            
            try:
                dm_embed = create_success_embed("VPS Created!", f"Your VPS has been successfully deployed by an admin!")
                created_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                vps_details = f"**VPS ID:** #{vps_count}\n"
                vps_details += f"**Container Name:** `{container_name}`\n"
                vps_details += f"**Configuration:** {config_str}\n"
                vps_details += f"**Status:** Running\n"
                vps_details += f"**OS:** {self.selected_os}\n"
                vps_details += f"**Created:** {created_time}"
                
                add_field(dm_embed, "VPS Details", vps_details, False)
                add_field(dm_embed, "Management", 
                         f"• Use `{PREFIX}manage` to start/stop your VPS\n• Use `{PREFIX}manage` → SSH for terminal access\n• Contact admin for upgrades or issues", 
                         False)
                
                await self.user.send(embed=dm_embed)
            except discord.Forbidden:
                await self.ctx.send(embed=create_info_embed("Notification Failed", f"Couldn't send DM to {self.user.mention}. Please ensure DMs are enabled."))
            except Exception as e:
                logger.error(f"Failed to send DM to {self.user.id}: {e}")
        
        except Exception as e:
            error_embed = create_error_embed("Creation Failed", f"Error: {str(e)}")
            await interaction.followup.send(embed=error_embed)

# ============ DELETE-VPS COMMAND WITH CONFIRMATION ============

class DeleteVPSView(discord.ui.View):
    def __init__(self, ctx, user, vps_number, vps_data_entry, container_name, reason):
        super().__init__(timeout=60)
        self.ctx = ctx
        self.user = user
        self.vps_number = vps_number
        self.vps_data_entry = vps_data_entry
        self.container_name = container_name
        self.reason = reason
        self.message = None
    
    async def on_timeout(self):
        if self.message:
            embed = create_info_embed("⏰ Timeout", "VPS deletion cancelled due to timeout.")
            await self.message.edit(embed=embed, view=None)
    
    @discord.ui.button(label="✅ Confirm Delete", style=discord.ButtonStyle.danger, emoji="⚠️")
    async def confirm_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message(embed=create_error_embed("Access Denied", "Only the command author can confirm this action."), ephemeral=True)
            return
        
        await interaction.response.defer()
        
        # Delete the VPS container
        try:
            await execute_lxc(f"lxc delete {self.container_name} --force")
            
            # Remove from database
            user_id = str(self.user.id)
            
            # Delete port forwards for this container
            conn = get_db()
            cur = conn.cursor()
            cur.execute('DELETE FROM port_forwards WHERE vps_container = ?', (self.container_name,))
            conn.commit()
            conn.close()
            
            # Remove from vps_data
            if user_id in vps_data:
                vps_data[user_id] = [v for v in vps_data[user_id] if v['container_name'] != self.container_name]
                if not vps_data[user_id]:
                    del vps_data[user_id]
                    
                    # Remove VPS role if user has no more VPS
                    if self.ctx.guild:
                        vps_role = await get_or_create_vps_role(self.ctx.guild)
                        if vps_role and vps_role in self.user.roles:
                            try:
                                await self.user.remove_roles(vps_role, reason="No VPS ownership")
                            except discord.Forbidden:
                                logger.warning(f"Failed to remove VPS role from {self.user.name}")
            
            # Save changes
            save_vps_data()
            
            # Log the deletion
            log_suspension(self.container_name, user_id, 'delete', self.reason, str(self.ctx.author.id))
            
            # Send success embed
            embed = create_success_embed("VPS Deleted Successfully")
            add_field(embed, "Owner", self.user.mention, True)
            add_field(embed, "VPS Number", f"#{self.vps_number}", True)
            add_field(embed, "Container", f"`{self.container_name}`", True)
            add_field(embed, "Reason", self.reason, False)
            
            await interaction.followup.send(embed=embed)
            
            # Notify user via DM
            try:
                dm_embed = create_warning_embed("VPS Deleted", f"Your VPS has been deleted by an admin.")
                add_field(dm_embed, "Container", f"`{self.container_name}`", True)
                add_field(dm_embed, "Reason", self.reason, False)
                add_field(dm_embed, "Deleted By", self.ctx.author.mention, False)
                
                await self.user.send(embed=dm_embed)
            except:
                pass  # User has DMs disabled
            
            # Disable all buttons
            for item in self.children:
                item.disabled = True
            await interaction.edit_original_response(view=self)
            
        except Exception as e:
            await interaction.followup.send(embed=create_error_embed("Deletion Failed", f"Error: {str(e)}"))
    
    @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.secondary)
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message(embed=create_error_embed("Access Denied", "Only the command author can cancel this action."), ephemeral=True)
            return
        
        embed = create_info_embed("Operation Cancelled", "VPS deletion has been cancelled.")
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(embed=embed, view=self)

@bot.command(name='delete-vps')
@is_admin()
@commands.cooldown(1, 10, commands.BucketType.user)
async def delete_vps(ctx, user: discord.Member, vps_number: int, *, reason: str = "No reason provided"):
    """Delete user's VPS with confirmation"""
    user_id = str(user.id)
    
    # Check if user has VPS
    if user_id not in vps_data:
        await ctx.send(embed=create_error_embed("No VPS Found", f"{user.mention} doesn't have any VPS."))
        return
    
    # Check if VPS number is valid
    if vps_number < 1 or vps_number > len(vps_data[user_id]):
        await ctx.send(embed=create_error_embed("Invalid VPS Number", 
            f"VPS number must be between 1 and {len(vps_data[user_id])}.\nUse `{PREFIX}userinfo {user.mention}` to see their VPS."))
        return
    
    # Get VPS information
    vps = vps_data[user_id][vps_number - 1]
    container_name = vps["container_name"]
    
    # Find OS display name
    os_display = vps.get('os_version', 'ubuntu:22.04')
    for o in OS_OPTIONS:
        if o["value"] == os_display:
            os_display = o["label"]
            break
    
    # Create confirmation embed
    embed = discord.Embed(
        title="⚠️ Confirm VPS Deletion",
        description=f"Are you sure you want to delete this VPS?",
        color=0xffaa00
    )
    
    # Set thumbnail if URL is provided
    if THUMBNAIL_URL:
        embed.set_thumbnail(url=THUMBNAIL_URL)
    
    # Set footer with timestamp and icon
    embed.set_footer(
        text=f"{BOT_NAME} VPS Manager • {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        icon_url=THUMBNAIL_URL
    )
    
    # VPS details
    vps_details = f"**Owner:** {user.mention}\n"
    vps_details += f"**VPS #{vps_number}:** `{container_name}`\n"
    vps_details += f"**Plan:** {vps.get('plan_name', 'Custom')}\n"
    vps_details += f"**Resources:** {vps['ram']} RAM | {vps['cpu']} CPU | {vps['storage']} Storage\n"
    vps_details += f"**OS:** {os_display}\n"
    vps_details += f"**Status:** {vps.get('status', 'unknown').upper()}\n"
    vps_details += f"**Purge Protected:** {'✅ Yes' if vps.get('purge_protected', False) else '❌ No'}\n"
    vps_details += f"**Created:** {vps.get('created_at', 'Unknown')[:10]}\n"
    vps_details += f"**Reason:** {reason}"
    
    add_field(embed, "VPS Details", vps_details, False)
    add_field(embed, "⚠️ Warning", "This action is **permanent** and cannot be undone!\nAll data on this VPS will be lost.", False)
    
    # Create view with confirmation buttons
    view = DeleteVPSView(ctx, user, vps_number, vps, container_name, reason)
    
    # Send the confirmation message
    msg = await ctx.send(embed=embed, view=view)
    view.message = msg

# ============ PURGE ALL VMS COMMAND (1 BY 1 DELETION) ============

class PurgeAllVMSView(discord.ui.View):
    def __init__(self, ctx):
        super().__init__(timeout=60)
        self.ctx = ctx
        self.message = None
        self.is_running = False
    
    async def on_timeout(self):
        if self.message and not self.is_running:
            embed = create_info_embed("⏰ Timeout", "Purge operation cancelled due to timeout.")
            await self.message.edit(embed=embed, view=None)
    
    @discord.ui.button(label="✅ Confirm Purge All", style=discord.ButtonStyle.danger, emoji="⚠️")
    async def confirm_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message(embed=create_error_embed("Access Denied", "Only the command author can confirm this action."), ephemeral=True)
            return
        
        self.is_running = True
        button.disabled = True
        self.children[1].disabled = True  # Disable cancel button
        await interaction.response.edit_message(view=self)
        
        # Count only non-protected VPS
        total_vps = 0
        protected_vps = 0
        for user_id, vps_list in vps_data.items():
            for vps in vps_list:
                if vps.get('purge_protected', False):
                    protected_vps += 1
                else:
                    total_vps += 1
        
        if total_vps == 0:
            if protected_vps > 0:
                embed = create_info_embed("All VPS Protected", 
                    f"Found **{protected_vps}** protected VPS but no unprotected VPS to purge.\n"
                    f"Use `.purge-list-protected` to see protected VPS.")
            else:
                embed = create_info_embed("No VPS Found", "There are no VPS to purge.")
            await interaction.followup.send(embed=embed)
            return
        
        # Create progress embed
        progress_embed = discord.Embed(
            title="🧹 Purging Unprotected VPS",
            description=f"Starting purge of {total_vps} unprotected VPS...\n"
                       f"({protected_vps} protected VPS will be skipped)\n"
                       f"This will delete **1 VPS every 3 seconds** to prevent high server load.",
            color=0xffaa00
        )
        
        # Set thumbnail if URL is provided
        if THUMBNAIL_URL:
            progress_embed.set_thumbnail(url=THUMBNAIL_URL)
        
        # Set footer with timestamp and icon
        progress_embed.set_footer(
            text=f"{BOT_NAME} VPS Manager • {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            icon_url=THUMBNAIL_URL
        )
        
        add_field(progress_embed, "Status", "🟡 Initializing...", False)
        add_field(progress_embed, "Progress", f"0/{total_vps} (0%)", False)
        add_field(progress_embed, "Protected VPS", f"🛡️ {protected_vps} VPS skipped", False)
        
        progress_msg = await interaction.followup.send(embed=progress_embed)
        
        deleted_count = 0
        skipped_count = 0
        failed_count = 0
        users_affected = set()
        
        # Create a list of all unprotected VPS to delete
        all_vps = []
        for user_id, vps_list in list(vps_data.items()):
            for vps in vps_list[:]:  # Use a copy of the list
                if not vps.get('purge_protected', False):
                    all_vps.append((user_id, vps))
                else:
                    skipped_count += 1
        
        total_to_delete = len(all_vps)
        
        # Delete VPS one by one with delay
        for i, (user_id, vps) in enumerate(all_vps, 1):
            container_name = vps['container_name']
            
            try:
                # Delete port forwards first
                conn = get_db()
                cur = conn.cursor()
                cur.execute('DELETE FROM port_forwards WHERE vps_container = ?', (container_name,))
                conn.commit()
                conn.close()
                
                # Delete the container
                await execute_lxc(f"lxc delete {container_name} --force", timeout=60)
                
                # Remove from vps_data
                if user_id in vps_data:
                    vps_data[user_id] = [v for v in vps_data[user_id] if v['container_name'] != container_name]
                    if not vps_data[user_id]:
                        del vps_data[user_id]
                
                # Log the deletion
                log_suspension(container_name, user_id, 'purge_all', f"Purged by {self.ctx.author.name}", str(self.ctx.author.id))
                
                deleted_count += 1
                users_affected.add(user_id)
                
                # Update progress every 5 deletions or at the end
                if i % 5 == 0 or i == total_to_delete:
                    percentage = int((i / total_to_delete) * 100) if total_to_delete > 0 else 100
                    progress_embed = discord.Embed(
                        title="🧹 Purging Unprotected VPS",
                        description=f"Progress: {i}/{total_to_delete} VPS processed",
                        color=0xffaa00
                    )
                    
                    # Set thumbnail if URL is provided
                    if THUMBNAIL_URL:
                        progress_embed.set_thumbnail(url=THUMBNAIL_URL)
                    
                    # Set footer with timestamp and icon
                    progress_embed.set_footer(
                        text=f"{BOT_NAME} VPS Manager • {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                        icon_url=THUMBNAIL_URL
                    )
                    
                    status_text = f"✅ Deleted: {deleted_count}\n"
                    status_text += f"🛡️ Skipped (Protected): {skipped_count}\n"
                    status_text += f"❌ Failed: {failed_count}\n"
                    status_text += f"👥 Users Affected: {len(users_affected)}"
                    
                    add_field(progress_embed, "Status", status_text, False)
                    add_field(progress_embed, "Progress Bar", self.create_progress_bar(percentage), False)
                    add_field(progress_embed, "Protected VPS", f"🛡️ {protected_vps} VPS remain protected", False)
                    
                    await progress_msg.edit(embed=progress_embed)
                
                # Save data periodically
                if i % 10 == 0:
                    save_vps_data()
                
                # Wait 3 seconds before next deletion to prevent high load
                await asyncio.sleep(3)
                
            except Exception as e:
                logger.error(f"Failed to delete VPS {container_name}: {e}")
                failed_count += 1
                
                # Still wait even on failure
                await asyncio.sleep(3)
        
        # Final save
        save_vps_data()
        
        # Send completion embed
        final_embed = discord.Embed(
            title="✅ Purge Complete",
            description=f"Successfully purged {deleted_count} unprotected VPS",
            color=0x00ff88
        )
        
        # Set thumbnail if URL is provided
        if THUMBNAIL_URL:
            final_embed.set_thumbnail(url=THUMBNAIL_URL)
        
        # Set footer with timestamp and icon
        final_embed.set_footer(
            text=f"{BOT_NAME} VPS Manager • {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            icon_url=THUMBNAIL_URL
        )
        
        summary = f"**Total Unprotected VPS:** {total_to_delete}\n"
        summary += f"**Successfully Deleted:** {deleted_count}\n"
        summary += f"**Failed Deletions:** {failed_count}\n"
        summary += f"**Protected VPS (Skipped):** {skipped_count}\n"
        summary += f"**Users Affected:** {len(users_affected)}"
        
        add_field(final_embed, "Summary", summary, False)
        
        if skipped_count > 0:
            add_field(final_embed, "Note", f"🛡️ {skipped_count} protected VPS were skipped. Use `.purge-list-protected` to see them.", False)
        
        await progress_msg.edit(embed=final_embed)
        
        # Disable all buttons in original message
        for item in self.children:
            item.disabled = True
        await interaction.edit_original_response(view=self)
    
    def create_progress_bar(self, percentage, length=20):
        """Create a text progress bar"""
        filled = int(length * percentage / 100)
        bar = "█" * filled + "░" * (length - filled)
        return f"`[{bar}] {percentage}%`"
    
    @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.secondary)
    async def cancel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message(embed=create_error_embed("Access Denied", "Only the command author can cancel this action."), ephemeral=True)
            return
        
        embed = create_info_embed("Operation Cancelled", "Purge all VPS operation has been cancelled.")
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(embed=embed, view=self)

@bot.command(name='purge-vm-all')
@is_main_admin()
@commands.cooldown(1, 300, commands.BucketType.user)  # 5 minute cooldown
async def purge_all_vms(ctx):
    """Purge ALL unprotected VPS from the bot (1 by 1 deletion to prevent high load)"""
    
    total_vps = 0
    protected_vps = 0
    
    for user_id, vps_list in vps_data.items():
        for vps in vps_list:
            if vps.get('purge_protected', False):
                protected_vps += 1
            else:
                total_vps += 1
    
    if total_vps == 0:
        if protected_vps > 0:
            embed = create_info_embed("All VPS Protected", 
                f"Found **{protected_vps}** protected VPS but no unprotected VPS to purge.\n"
                f"Use `.purge-list-protected` to see protected VPS.")
        else:
            embed = create_info_embed("No VPS Found", "There are no VPS to purge.")
        await ctx.send(embed=embed)
        return
    
    # Calculate estimated time
    estimated_time = total_vps * 3  # 3 seconds per VPS
    estimated_minutes = estimated_time // 60
    estimated_seconds = estimated_time % 60
    
    # Create confirmation embed
    embed = discord.Embed(
        title="⚠️⚠️⚠️ PURGE ALL UNPROTECTED VPS ⚠️⚠️⚠️",
        description=f"This will delete **ALL {total_vps} UNPROTECTED VPS** from the system!\n"
                   f"**{protected_vps} protected VPS will be skipped.**",
        color=0xff0000
    )
    
    # Set thumbnail if URL is provided
    if THUMBNAIL_URL:
        embed.set_thumbnail(url=THUMBNAIL_URL)
    
    # Set footer with timestamp and icon
    embed.set_footer(
        text=f"{BOT_NAME} VPS Manager • {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        icon_url=THUMBNAIL_URL
    )
    
    warning = f"**Unprotected VPS to delete:** {total_vps}\n"
    warning += f"**Protected VPS (skipped):** {protected_vps}\n"
    warning += f"**Deletion speed:** 1 VPS every 3 seconds\n"
    warning += f"**Estimated time:** {estimated_minutes} minutes and {estimated_seconds} seconds\n\n"
    warning += "**⚠️ THIS ACTION CANNOT BE UNDONE!**\n"
    warning += "• All unprotected VPS containers will be permanently deleted\n"
    warning += "• All port forwards will be removed\n"
    warning += "• All user data for deleted VPS will be cleared\n"
    warning += "• Protected VPS will remain untouched\n\n"
    warning += "Type `.confirm-purge-all` to proceed with this destructive action."
    
    add_field(embed, "Warning", warning, False)
    
    await ctx.send(embed=embed)

@bot.command(name='confirm-purge-all')
@is_main_admin()
@commands.cooldown(1, 300, commands.BucketType.user)
async def confirm_purge_all(ctx):
    """Confirm and execute purge all unprotected VPS"""
    
    total_vps = 0
    protected_vps = 0
    
    for user_id, vps_list in vps_data.items():
        for vps in vps_list:
            if vps.get('purge_protected', False):
                protected_vps += 1
            else:
                total_vps += 1
    
    if total_vps == 0:
        if protected_vps > 0:
            embed = create_info_embed("All VPS Protected", 
                f"Found **{protected_vps}** protected VPS but no unprotected VPS to purge.\n"
                f"Use `.purge-list-protected` to see protected VPS.")
        else:
            embed = create_info_embed("No VPS Found", "There are no VPS to purge.")
        await ctx.send(embed=embed)
        return
    
    # Calculate estimated time
    estimated_time = total_vps * 3
    estimated_minutes = estimated_time // 60
    estimated_seconds = estimated_time % 60
    
    # Create final confirmation with buttons
    embed = discord.Embed(
        title="⚠️ FINAL CONFIRMATION - PURGE ALL UNPROTECTED VPS",
        description=f"You are about to delete **{total_vps} unprotected VPS**",
        color=0xff0000
    )
    
    # Set thumbnail if URL is provided
    if THUMBNAIL_URL:
        embed.set_thumbnail(url=THUMBNAIL_URL)
    
    # Set footer with timestamp and icon
    embed.set_footer(
        text=f"{BOT_NAME} VPS Manager • {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        icon_url=THUMBNAIL_URL
    )
    
    details = f"**Unprotected VPS to delete:** {total_vps}\n"
    details += f"**Protected VPS (skipped):** {protected_vps}\n"
    details += f"**Estimated time:** {estimated_minutes} minutes and {estimated_seconds} seconds\n"
    details += f"**Deletion rate:** 1 VPS every 3 seconds\n\n"
    details += "This operation will:\n"
    details += "• Delete all unprotected VPS containers\n"
    details += "• Remove all port forwards\n"
    details += "• Clear user data for deleted VPS\n"
    details += "• Protected VPS will remain untouched\n\n"
    details += "**Are you absolutely sure?**"
    
    add_field(embed, "Details", details, False)
    
    view = PurgeAllVMSView(ctx)
    msg = await ctx.send(embed=embed, view=view)
    view.message = msg

# ============ ADDITIONAL ADMIN COMMANDS ============

@bot.command(name='add-resources')
@is_admin()
@commands.cooldown(1, 10, commands.BucketType.user)
async def add_resources(ctx, container_name: str, ram: int = None, cpu: int = None, disk: int = None):
    """Add resources to VPS"""
    if ram is None and cpu is None and disk is None:
        await ctx.send(embed=create_error_embed("Missing Parameters", "Please specify at least one resource to add"))
        return
    
    found_vps = None
    user_id = None
    vps_index = None
    
    for uid, vps_list in vps_data.items():
        for i, vps in enumerate(vps_list):
            if vps['container_name'] == container_name:
                found_vps = vps
                user_id = uid
                vps_index = i
                break
        if found_vps:
            break
    
    if not found_vps:
        await ctx.send(embed=create_error_embed("VPS Not Found", f"No VPS found with ID: `{container_name}`"))
        return
    
    was_running = found_vps.get('status') == 'running' and not found_vps.get('suspended', False)
    disk_changed = disk is not None
    
    if was_running:
        await ctx.send(embed=create_info_embed("Stopping VPS", f"Stopping VPS `{container_name}` to apply resource changes..."))
        try:
            await execute_lxc(f"lxc stop {container_name}")
            found_vps['status'] = 'stopped'
            save_vps_data()
        except Exception as e:
            await ctx.send(embed=create_error_embed("Stop Failed", f"Error stopping VPS: {str(e)}"))
            return
    
    changes = []
    try:
        current_ram_gb = int(found_vps['ram'].replace('GB', ''))
        current_cpu = int(found_vps['cpu'])
        current_disk_gb = int(found_vps['storage'].replace('GB', ''))
        
        new_ram_gb = current_ram_gb
        new_cpu = current_cpu
        new_disk_gb = current_disk_gb
        
        if ram is not None and ram > 0:
            new_ram_gb += ram
            ram_mb = new_ram_gb * 1024
            await execute_lxc(f"lxc config set {container_name} limits.memory {ram_mb}MB")
            changes.append(f"RAM: +{ram}GB (New total: {new_ram_gb}GB)")
        
        if cpu is not None and cpu > 0:
            new_cpu += cpu
            await execute_lxc(f"lxc config set {container_name} limits.cpu {new_cpu}")
            changes.append(f"CPU: +{cpu} cores (New total: {new_cpu} cores)")
        
        if disk is not None and disk > 0:
            new_disk_gb += disk
            await execute_lxc(f"lxc config device set {container_name} root size={new_disk_gb}GB")
            changes.append(f"Disk: +{disk}GB (New total: {new_disk_gb}GB)")
        
        found_vps['ram'] = f"{new_ram_gb}GB"
        found_vps['cpu'] = str(new_cpu)
        found_vps['storage'] = f"{new_disk_gb}GB"
        found_vps['config'] = f"{new_ram_gb}GB RAM / {new_cpu} CPU / {new_disk_gb}GB Disk"
        vps_data[user_id][vps_index] = found_vps
        save_vps_data()
        
        if was_running:
            await execute_lxc(f"lxc start {container_name}")
            found_vps['status'] = 'running'
            save_vps_data()
            await apply_internal_permissions(container_name)
        
        embed = create_success_embed("Resources Added", f"Successfully added resources to VPS `{container_name}`")
        add_field(embed, "Changes Applied", "\n".join(changes), False)
        if disk_changed:
            add_field(embed, "Disk Note", "Run `sudo resize2fs /` inside the VPS to expand the filesystem.", False)
        
        await ctx.send(embed=embed)
    
    except Exception as e:
        await ctx.send(embed=create_error_embed("Resource Addition Failed", f"Error: {str(e)}"))

@bot.command(name='resize-vps')
@is_admin()
@commands.cooldown(1, 10, commands.BucketType.user)
async def resize_vps(ctx, container_name: str, ram: int = None, cpu: int = None, disk: int = None):
    """Resize VPS resources"""
    await add_resources(ctx, container_name, ram, cpu, disk)

@bot.command(name='suspend-vps')
@is_admin()
@commands.cooldown(1, 5, commands.BucketType.user)
async def suspend_vps(ctx, container_name: str, *, reason: str = "Admin action"):
    """Suspend VPS"""
    found = False
    for uid, lst in vps_data.items():
        for vps in lst:
            if vps['container_name'] == container_name:
                if vps.get('status') != 'running':
                    await ctx.send(embed=create_error_embed("Cannot Suspend", "VPS must be running to suspend."))
                    return
                try:
                    await execute_lxc(f"lxc stop {container_name}")
                    vps['status'] = 'stopped'
                    vps['suspended'] = True
                    vps['suspended_reason'] = reason
                    if 'suspension_history' not in vps:
                        vps['suspension_history'] = []
                    vps['suspension_history'].append({
                        'time': datetime.now().isoformat(),
                        'reason': reason,
                        'by': f"{ctx.author.name}"
                    })
                    save_vps_data()
                    log_suspension(container_name, uid, 'suspend', reason, str(ctx.author.id))
                except Exception as e:
                    await ctx.send(embed=create_error_embed("Suspend Failed", str(e)))
                    return
                
                embed = create_warning_embed("VPS Suspended", f"VPS `{container_name}` suspended.")
                add_field(embed, "Reason", reason, False)
                await ctx.send(embed=embed)
                found = True
                break
        if found:
            break
    
    if not found:
        await ctx.send(embed=create_error_embed("Not Found", f"VPS `{container_name}` not found."))

@bot.command(name='unsuspend-vps')
@is_admin()
@commands.cooldown(1, 5, commands.BucketType.user)
async def unsuspend_vps(ctx, container_name: str):
    """Unsuspend VPS"""
    found = False
    for uid, lst in vps_data.items():
        for vps in lst:
            if vps['container_name'] == container_name:
                if not vps.get('suspended', False):
                    await ctx.send(embed=create_error_embed("Not Suspended", "VPS is not suspended."))
                    return
                try:
                    vps['suspended'] = False
                    vps['suspended_reason'] = ''
                    vps['status'] = 'running'
                    await execute_lxc(f"lxc start {container_name}")
                    await apply_internal_permissions(container_name)
                    save_vps_data()
                    log_suspension(container_name, uid, 'unsuspend', '', str(ctx.author.id))
                    
                    embed = create_success_embed("VPS Unsuspended", f"VPS `{container_name}` unsuspended and started.")
                    await ctx.send(embed=embed)
                    found = True
                except Exception as e:
                    await ctx.send(embed=create_error_embed("Start Failed", str(e)))
                break
        if found:
            break
    
    if not found:
        await ctx.send(embed=create_error_embed("Not Found", f"VPS `{container_name}` not found."))

@bot.command(name='suspension-logs')
@is_admin()
@commands.cooldown(1, 3, commands.BucketType.user)
async def suspension_logs(ctx, container_name: str = None):
    """View suspension logs"""
    logs = get_suspension_logs(container_name)
    
    if not logs:
        await ctx.send(embed=create_info_embed("Suspension Logs", "No logs found."))
        return
    
    log_text = ""
    for log in logs[:10]:
        log_text += f"**{log['action']}** - {log['container_name']}\n"
        log_text += f"Time: {log['created_at'][:19]}\n"
        if log['reason']:
            log_text += f"Reason: {log['reason']}\n"
        log_text += "\n"
    
    embed = create_info_embed("Suspension Logs", log_text)
    await ctx.send(embed=embed)

@bot.command(name='whitelist-vps')
@is_admin()
@commands.cooldown(1, 3, commands.BucketType.user)
async def whitelist_vps(ctx, container_name: str, action: str):
    """Whitelist VPS from auto-suspend"""
    action = action.lower()
    if action not in ['add', 'remove']:
        await ctx.send(embed=create_error_embed("Invalid Action", "Use `add` or `remove`."))
        return
    
    found = False
    for user_id, vps_list in vps_data.items():
        for vps in vps_list:
            if vps['container_name'] == container_name:
                if action == 'add':
                    vps['whitelisted'] = True
                    msg = "added to whitelist (exempt from auto-suspension)"
                else:
                    vps['whitelisted'] = False
                    msg = "removed from whitelist"
                save_vps_data()
                
                embed = create_success_embed("Whitelist Updated", f"VPS `{container_name}` {msg}.")
                await ctx.send(embed=embed)
                found = True
                break
        if found:
            break
    
    if not found:
        await ctx.send(embed=create_error_embed("Not Found", f"VPS `{container_name}` not found."))

@bot.command(name='userinfo')
@is_admin()
@commands.cooldown(1, 3, commands.BucketType.user)
async def user_info(ctx, user: discord.Member):
    """User information with VPS numbers"""
    user_id = str(user.id)
    vps_list = vps_data.get(user_id, [])
    stats = get_user_stats(user_id)
    
    embed = discord.Embed(
        title=f"User Information - {user.name}",
        description=f"Detailed information for {user.mention}",
        color=0x1a1a1a
    )
    
    # Set thumbnail if URL is provided
    if THUMBNAIL_URL:
        embed.set_thumbnail(url=THUMBNAIL_URL)
    
    # Set footer with timestamp and icon
    embed.set_footer(
        text=f"{BOT_NAME} VPS Manager • {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        icon_url=THUMBNAIL_URL
    )
    
    user_details = f"**Name:** {user.name}\n"
    user_details += f"**ID:** {user.id}\n"
    user_details += f"**Joined:** {user.joined_at.strftime('%Y-%m-%d %H:%M:%S') if user.joined_at else 'Unknown'}"
    
    add_field(embed, "User Details", user_details, False)
    
    # Stats
    stats_info = f"**📨 Invites:** {stats.get('invites', 0)}\n"
    stats_info += f"**🚀 Boosts:** {stats.get('boosts', 0)}\n"
    add_field(embed, "User Stats", stats_info, True)
    
    if vps_list:
        vps_info = []
        for i, vps in enumerate(vps_list, 1):
            status_emoji = "🟢" if vps.get('status') == 'running' and not vps.get('suspended', False) else "🟡" if vps.get('suspended', False) else "🔴"
            status_text = vps.get('status', 'unknown').upper()
            if vps.get('suspended', False):
                status_text += " (SUSPENDED)"
            purge_text = " 🛡️" if vps.get('purge_protected', False) else ""
            vps_info.append(f"{status_emoji} **VPS #{i}:** `{vps['container_name']}` - {status_text}{purge_text}")
        
        add_field(embed, f"VPS List ({len(vps_list)})", "\n".join(vps_info), False)
        add_field(embed, "Delete Command", f"`{PREFIX}delete-vps {user.mention} <1-{len(vps_list)}> [reason]`", False)
        add_field(embed, "Purge Protection", f"Use `{PREFIX}purge-prot {user.mention} <num>` to protect", False)
    else:
        add_field(embed, "VPS Information", "**No VPS owned**", False)
    
    # Port quota
    port_quota = get_user_allocation(user_id)
    port_used = get_user_used_ports(user_id)
    add_field(embed, "Port Quota", f"Allocated: {port_quota}, Used: {port_used}", False)
    
    # Admin status
    is_admin_user = user_id == str(MAIN_ADMIN_ID) or user_id in admin_data.get("admins", [])
    add_field(embed, "Admin Status", f"**{'Yes' if is_admin_user else 'No'}**", False)
    
    await ctx.send(embed=embed)

# ============ OTHER COMMANDS ============

@bot.command(name='exec')
@is_admin()
@commands.cooldown(1, 5, commands.BucketType.user)
async def execute_command(ctx, container_name: str, *, command: str):
    """Execute command in VPS"""
    await ctx.send(embed=create_info_embed("Executing Command", f"Running command in VPS `{container_name}`..."))
    
    try:
        proc = await asyncio.create_subprocess_exec(
            "lxc", "exec", container_name, "--", "bash", "-c", command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        output = stdout.decode() if stdout else "No output"
        error = stderr.decode() if stderr else ""
        
        embed = discord.Embed(
            title=f"Command Output - {container_name}",
            description=f"Command: `{command}`",
            color=0x1a1a1a
        )
        
        # Set thumbnail if URL is provided
        if THUMBNAIL_URL:
            embed.set_thumbnail(url=THUMBNAIL_URL)
        
        # Set footer with timestamp and icon
        embed.set_footer(
            text=f"{BOT_NAME} VPS Manager • {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            icon_url=THUMBNAIL_URL
        )
        
        if output.strip():
            if len(output) > 1000:
                output = output[:1000] + "\n... (truncated)"
            embed.add_field(name="⌯⌲ Output", value=f"```\n{output}\n```", inline=False)
        
        if error.strip():
            if len(error) > 1000:
                error = error[:1000] + "\n... (truncated)"
            embed.add_field(name="⌯⌲ Error", value=f"```\n{error}\n```", inline=False)
        
        await ctx.send(embed=embed)
    
    except Exception as e:
        await ctx.send(embed=create_error_embed("Execution Failed", f"Error: {str(e)}"))

@bot.command(name='stop-vps-all')
@is_admin()
@commands.cooldown(1, 30, commands.BucketType.user)
async def stop_all_vps(ctx):
    """Stop all VPS"""
    embed = discord.Embed(
        title="⚠️ Stopping All VPS",
        description="This will stop ALL running VPS on the server.\n\nThis action cannot be undone. Continue?",
        color=0xffaa00
    )
    
    # Set thumbnail if URL is provided
    if THUMBNAIL_URL:
        embed.set_thumbnail(url=THUMBNAIL_URL)
    
    # Set footer with timestamp and icon
    embed.set_footer(
        text=f"{BOT_NAME} VPS Manager • {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        icon_url=THUMBNAIL_URL
    )
    
    class ConfirmView(discord.ui.View):
        def __init__(self):
            super().__init__(timeout=60)
        
        @discord.ui.button(label="Stop All VPS", style=discord.ButtonStyle.danger)
        async def confirm(self, interaction: discord.Interaction, item: discord.ui.Button):
            await interaction.response.defer()
            try:
                await execute_lxc("lxc stop --all --force")
                
                stopped_count = 0
                for user_id, vps_list in vps_data.items():
                    for vps in vps_list:
                        if vps.get('status') == 'running':
                            vps['status'] = 'stopped'
                            stopped_count += 1
                
                save_vps_data()
                embed = create_success_embed("All VPS Stopped", f"Successfully stopped {stopped_count} VPS")
                await interaction.followup.send(embed=embed)
            except Exception as e:
                embed = create_error_embed("Stop Failed", str(e))
                await interaction.followup.send(embed=embed)
        
        @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
        async def cancel(self, interaction: discord.Interaction, item: discord.ui.Button):
            embed = create_info_embed("Operation Cancelled", "The stop all VPS operation has been cancelled.")
            await interaction.response.edit_message(embed=embed, view=None)
    
    await ctx.send(embed=embed, view=ConfirmView())

@bot.command(name='migrate-vps')
@is_admin()
@commands.cooldown(1, 30, commands.BucketType.user)
async def migrate_vps(ctx, container_name: str, pool: str):
    """Migrate VPS to another storage pool"""
    await ctx.send(embed=create_info_embed("Migrating VPS", f"Migrating `{container_name}` to pool `{pool}`..."))
    
    try:
        await execute_lxc(f"lxc move {container_name} -s {pool}")
        embed = create_success_embed("VPS Migrated", f"VPS `{container_name}` migrated to pool `{pool}`")
        await ctx.send(embed=embed)
    except Exception as e:
        await ctx.send(embed=create_error_embed("Migration Failed", f"Error: {str(e)}"))

@bot.command(name='vps-network')
@is_admin()
@commands.cooldown(1, 5, commands.BucketType.user)
async def vps_network(ctx, container_name: str, action: str, value: str = None):
    """Network management for VPS"""
    actions = ['list', 'limit', 'add', 'remove']
    
    if action not in actions:
        await ctx.send(embed=create_error_embed("Invalid Action", f"Use: {', '.join(actions)}"))
        return
    
    try:
        if action == 'list':
            proc = await asyncio.create_subprocess_exec(
                "lxc", "exec", container_name, "--", "ip", "addr",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()
            if proc.returncode == 0:
                output = stdout.decode()
                if len(output) > 1900:
                    output = output[:1900] + "..."
                embed = create_info_embed(f"Network - {container_name}", f"```\n{output}\n```")
            else:
                embed = create_error_embed("Error", f"Failed to list network interfaces")
        elif action == 'limit' and value:
            await execute_lxc(f"lxc config device set {container_name} eth0 limits.egress {value}")
            await execute_lxc(f"lxc config device set {container_name} eth0 limits.ingress {value}")
            embed = create_success_embed("Network Limit Set", f"Set network limit to {value} for `{container_name}`")
        else:
            embed = create_error_embed("Invalid Command", "Usage: .vps-network <container> <list|limit> [value]")
        
        await ctx.send(embed=embed)
    except Exception as e:
        await ctx.send(embed=create_error_embed("Network Operation Failed", str(e)))

@bot.command(name='apply-permissions')
@is_admin()
@commands.cooldown(1, 10, commands.BucketType.user)
async def apply_permissions(ctx, container_name: str):
    """Apply Docker-ready permissions to VPS"""
    await ctx.send(embed=create_info_embed("Applying Permissions", f"Applying Docker-ready permissions to `{container_name}`..."))
    
    try:
        await apply_lxc_config(container_name)
        await apply_internal_permissions(container_name)
        embed = create_success_embed("Permissions Applied", f"Docker-ready permissions applied to `{container_name}`")
        await ctx.send(embed=embed)
    except Exception as e:
        await ctx.send(embed=create_error_embed("Failed", f"Error: {str(e)}"))

# ============ SYSTEM COMMANDS ============

@bot.command(name='thresholds')
@is_admin()
@commands.cooldown(1, 3, commands.BucketType.user)
async def thresholds(ctx):
    """Show current resource thresholds"""
    embed = create_info_embed("Resource Thresholds", f"**CPU:** {CPU_THRESHOLD}%\n**RAM:** {RAM_THRESHOLD}%")
    await ctx.send(embed=embed)

@bot.command(name='set-threshold')
@is_admin()
@commands.cooldown(1, 5, commands.BucketType.user)
async def set_threshold(ctx, cpu: int, ram: int):
    """Set resource thresholds"""
    global CPU_THRESHOLD, RAM_THRESHOLD
    
    if cpu < 0 or ram < 0:
        await ctx.send(embed=create_error_embed("Invalid Thresholds", "Thresholds must be non-negative."))
        return
    
    CPU_THRESHOLD = cpu
    RAM_THRESHOLD = ram
    set_setting('cpu_threshold', str(cpu))
    set_setting('ram_threshold', str(ram))
    
    embed = create_success_embed("Thresholds Updated", f"**CPU:** {cpu}%\n**RAM:** {ram}%")
    await ctx.send(embed=embed)

@bot.command(name='lxc-list')
@is_admin()
@commands.cooldown(1, 5, commands.BucketType.user)
async def lxc_list(ctx):
    """List all LXC containers"""
    try:
        result = await execute_lxc("lxc list")
        embed = create_info_embed("LXC Containers List", f"```\n{result}\n```")
        await ctx.send(embed=embed)
    except Exception as e:
        await ctx.send(embed=create_error_embed("Error", str(e)))

@bot.command(name='set-status')
@is_admin()
@commands.cooldown(1, 5, commands.BucketType.user)
async def set_status(ctx, activity_type: str, *, name: str):
    """Set bot status"""
    types = {
        'playing': discord.ActivityType.playing,
        'watching': discord.ActivityType.watching,
        'listening': discord.ActivityType.listening,
    }
    
    if activity_type.lower() not in types:
        await ctx.send(embed=create_error_embed("Invalid Type", "Valid types: playing, watching, listening"))
        return
    
    await bot.change_presence(activity=discord.Activity(type=types[activity_type.lower()], name=name))
    set_setting('bot_activity', activity_type.lower())
    set_setting('bot_activity_name', name)
    
    embed = create_success_embed("Status Updated", f"Set to {activity_type}: {name}")
    await ctx.send(embed=embed)

@bot.command(name='change-mode')
@is_main_admin()
@commands.cooldown(1, 5, commands.BucketType.user)
async def change_mode(ctx, mode: str):
    """Change bot mode"""
    modes = {
        'online': discord.Status.online,
        'idle': discord.Status.idle,
        'dnd': discord.Status.dnd,
    }
    
    if mode.lower() not in modes:
        await ctx.send(embed=create_error_embed("Invalid Mode", "Valid modes: online, idle, dnd"))
        return
    
    await bot.change_presence(status=modes[mode.lower()])
    set_setting('bot_status', mode.lower())
    
    embed = create_success_embed("Mode Changed", f"Bot mode set to {mode}")
    await ctx.send(embed=embed)

@bot.command(name='maintenance')
@is_main_admin()
@commands.cooldown(1, 5, commands.BucketType.user)
async def maintenance_mode(ctx, mode: str):
    """Toggle maintenance mode"""
    global MAINTENANCE_MODE, MAINTENANCE_STARTED_BY, MAINTENANCE_STARTED_AT
    
    mode = mode.lower()
    if mode not in ['on', 'off']:
        await ctx.send(embed=create_error_embed("Invalid Mode", "Please use `on` or `off`."))
        return
    
    if mode == 'on':
        MAINTENANCE_MODE = True
        MAINTENANCE_STARTED_BY = str(ctx.author.id)
        MAINTENANCE_STARTED_AT = datetime.now().isoformat()
        
        set_setting('maintenance_mode', 'true')
        set_setting('maintenance_started_by', str(ctx.author.id))
        set_setting('maintenance_started_at', MAINTENANCE_STARTED_AT)
        
        await bot.change_presence(status=discord.Status.idle, activity=discord.Game(name="🔧 Maintenance Mode"))
        
        embed = create_warning_embed("Maintenance Mode Active", "The bot is now in maintenance mode. Only administrators can use commands.")
        add_field(embed, "Started By", ctx.author.mention, True)
        add_field(embed, "Status", "Commands disabled for non-admins", True)
        
    else:
        MAINTENANCE_MODE = False
        MAINTENANCE_STARTED_BY = ''
        MAINTENANCE_STARTED_AT = ''
        
        set_setting('maintenance_mode', 'false')
        set_setting('maintenance_started_by', '')
        set_setting('maintenance_started_at', '')
        
        activity_types = {
            'playing': discord.ActivityType.playing,
            'watching': discord.ActivityType.watching,
            'listening': discord.ActivityType.listening,
        }
        activity_type = activity_types.get(BOT_ACTIVITY, discord.ActivityType.watching)
        status_types = {
            'online': discord.Status.online,
            'idle': discord.Status.idle,
            'dnd': discord.Status.dnd,
        }
        status = status_types.get(BOT_STATUS, discord.Status.online)
        
        await bot.change_presence(status=status, activity=discord.Activity(type=activity_type, name=BOT_ACTIVITY_NAME))
        
        embed = create_success_embed("Maintenance Mode Deactivated", "All commands are now available.")
    
    await ctx.send(embed=embed)

@bot.command(name='purge-data')
@is_main_admin()
@commands.cooldown(1, 60, commands.BucketType.user)
async def purge_data(ctx, user: discord.Member):
    """Purge all data for a user"""
    user_id = str(user.id)
    
    if user_id not in vps_data:
        await ctx.send(embed=create_error_embed("No Data", f"{user.mention} has no VPS data."))
        return
    
    embed = discord.Embed(
        title="⚠️ Purge Data",
        description=f"This will permanently delete ALL VPS data for {user.mention}.\n"
                    f"This action CANNOT be undone!\n\n"
                    f"**VPS Count:** {len(vps_data[user_id])}\n\n"
                    f"Type `{PREFIX}confirm-purge {user.id}` to proceed.",
        color=0xffaa00
    )
    
    # Set thumbnail if URL is provided
    if THUMBNAIL_URL:
        embed.set_thumbnail(url=THUMBNAIL_URL)
    
    # Set footer with timestamp and icon
    embed.set_footer(
        text=f"{BOT_NAME} VPS Manager • {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        icon_url=THUMBNAIL_URL
    )
    
    await ctx.send(embed=embed)

@bot.command(name='confirm-purge')
@is_main_admin()
@commands.cooldown(1, 60, commands.BucketType.user)
async def confirm_purge(ctx, user_id: str):
    """Confirm purge of user data"""
    try:
        user = await bot.fetch_user(int(user_id))
    except:
        user = None
    
    if user_id not in vps_data:
        await ctx.send(embed=create_error_embed("No Data", f"User ID {user_id} has no VPS data."))
        return
    
    deleted_count = 0
    for vps in vps_data[user_id][:]:
        try:
            # Delete port forwards first
            conn = get_db()
            cur = conn.cursor()
            cur.execute('DELETE FROM port_forwards WHERE vps_container = ?', (vps['container_name'],))
            conn.commit()
            conn.close()
            
            await execute_lxc(f"lxc delete {vps['container_name']} --force")
            deleted_count += 1
            await asyncio.sleep(1)  # Small delay to prevent overload
        except Exception as e:
            logger.error(f"Failed to delete {vps['container_name']}: {e}")
    
    del vps_data[user_id]
    save_vps_data()
    
    embed = create_success_embed("Data Purged", 
        f"Successfully purged data for {user.mention if user else f'User {user_id}'}\n"
        f"Deleted {deleted_count} VPS containers.")
    await ctx.send(embed=embed)

# ============ PORT FORWARDING COMMANDS ============

@bot.command(name='ports')
@commands.cooldown(1, 2, commands.BucketType.user)
async def ports_command(ctx, subcmd: str = None, *args):
    """Manage port forwarding"""
    if not await maintenance_check(ctx):
        return
    
    user_id = str(ctx.author.id)
    allocated = get_user_allocation(user_id)
    used = get_user_used_ports(user_id)
    available = allocated - used
    
    if subcmd is None:
        embed = create_info_embed("Port Forwarding Help", f"**Your Quota:** Allocated: {allocated}, Used: {used}, Available: {available}")
        add_field(embed, "Commands", 
                 f"{PREFIX}ports add <vps_num> <vps_port>\n{PREFIX}ports list\n{PREFIX}ports remove <id>", 
                 False)
        await ctx.send(embed=embed)
        return
    
    if subcmd == 'add':
        if len(args) < 2:
            await ctx.send(embed=create_error_embed("Usage", f"Usage: {PREFIX}ports add <vps_number> <vps_port>"))
            return
        
        try:
            vps_num = int(args[0])
            vps_port = int(args[1])
            if vps_port < 1 or vps_port > 65535:
                raise ValueError
        except ValueError:
            await ctx.send(embed=create_error_embed("Invalid Input", "VPS number and port must be positive integers (port: 1-65535)."))
            return
        
        vps_list = vps_data.get(user_id, [])
        if not vps_list:
            await ctx.send(embed=create_no_vps_embed())
            return
        
        if vps_num < 1 or vps_num > len(vps_list):
            await ctx.send(embed=create_error_embed("Invalid VPS", f"Invalid VPS number (1-{len(vps_list)}). Use {PREFIX}myvps to list."))
            return
        
        vps = vps_list[vps_num - 1]
        container = vps['container_name']
        
        if used >= allocated:
            await ctx.send(embed=create_error_embed("Quota Exceeded", f"No available slots. Allocated: {allocated}, Used: {used}. Contact admin for more."))
            return
        
        host_port = await create_port_forward(user_id, container, vps_port)
        if host_port:
            embed = create_success_embed("Port Forward Created", 
                f"VPS #{vps_num} port {vps_port} (TCP/UDP) forwarded to host port {host_port}.")
            add_field(embed, "Access", f"External: {YOUR_SERVER_IP}:{host_port} → VPS:{vps_port} (TCP & UDP)", False)
            add_field(embed, "Quota Update", f"Used: {used + 1}/{allocated}", False)
            await ctx.send(embed=embed)
        else:
            await ctx.send(embed=create_error_embed("Failed", "Could not assign host port. Try again later."))
    
    elif subcmd == 'list':
        forwards = get_user_forwards(user_id)
        embed = create_info_embed("Your Port Forwards", f"**Quota:** Allocated: {allocated}, Used: {used}, Available: {available}")
        
        if not forwards:
            add_field(embed, "Forwards", "No active port forwards.", False)
        else:
            text = []
            for f in forwards:
                vps_num = next((i+1 for i, v in enumerate(vps_data.get(user_id, [])) if v['container_name'] == f['vps_container']), 'Unknown')
                created = datetime.fromisoformat(f['created_at']).strftime('%Y-%m-%d %H:%M')
                text.append(f"**ID {f['id']}** - VPS #{vps_num}: {f['vps_port']} (TCP/UDP) → {f['host_port']} (Created: {created})")
            
            add_field(embed, "Active Forwards", "\n".join(text[:10]), False)
            if len(forwards) > 10:
                add_field(embed, "Note", f"Showing 10 of {len(forwards)}. Remove unused with {PREFIX}ports remove <id>.", False)
        
        await ctx.send(embed=embed)
    
    elif subcmd == 'remove':
        if len(args) < 1:
            await ctx.send(embed=create_error_embed("Usage", f"Usage: {PREFIX}ports remove <forward_id>"))
            return
        
        try:
            fid = int(args[0])
        except ValueError:
            await ctx.send(embed=create_error_embed("Invalid ID", "Forward ID must be an integer."))
            return
        
        success, _ = await remove_port_forward(fid)
        if success:
            embed = create_success_embed("Removed", f"Port forward {fid} removed (TCP & UDP).")
            add_field(embed, "Quota Update", f"Used: {used - 1}/{allocated}", False)
            await ctx.send(embed=embed)
        else:
            await ctx.send(embed=create_error_embed("Not Found", "Forward ID not found. Use .ports list."))
    
    else:
        await ctx.send(embed=create_error_embed("Invalid Subcommand", f"Use: add <vps_num> <port>, list, remove <id>"))

@bot.command(name='ports-add-user')
@is_admin()
@commands.cooldown(1, 3, commands.BucketType.user)
async def ports_add_user(ctx, amount: int, user: discord.Member):
    """Allocate port slots to a user"""
    if amount <= 0:
        await ctx.send(embed=create_error_embed("Invalid Amount", "Amount must be a positive integer."))
        return
    
    user_id = str(user.id)
    allocate_ports(user_id, amount)
    
    embed = create_success_embed("Ports Allocated", f"Allocated {amount} port slots to {user.mention}.")
    add_field(embed, "Quota", f"Total: {get_user_allocation(user_id)} slots", False)
    await ctx.send(embed=embed)
    
    try:
        dm_embed = create_info_embed("Port Slots Allocated", 
            f"You have been granted {amount} additional port forwarding slots by an admin.\nUse `{PREFIX}ports list` to view your quota and active forwards.")
        await user.send(embed=dm_embed)
    except discord.Forbidden:
        await ctx.send(embed=create_info_embed("DM Failed", f"Could not notify {user.mention} via DM."))

@bot.command(name='ports-remove-user')
@is_admin()
@commands.cooldown(1, 3, commands.BucketType.user)
async def ports_remove_user(ctx, amount: int, user: discord.Member):
    """Deallocate port slots from a user"""
    if amount <= 0:
        await ctx.send(embed=create_error_embed("Invalid Amount", "Amount must be a positive integer."))
        return
    
    user_id = str(user.id)
    current = get_user_allocation(user_id)
    if amount > current:
        amount = current
    
    deallocate_ports(user_id, amount)
    remaining = get_user_allocation(user_id)
    
    embed = create_success_embed("Ports Deallocated", f"Removed {amount} port slots from {user.mention}.")
    add_field(embed, "Remaining Quota", f"{remaining} slots", False)
    await ctx.send(embed=embed)
    
    try:
        dm_embed = create_warning_embed("Port Slots Reduced", 
            f"Your port forwarding quota has been reduced by {amount} slots by an admin.\nRemaining: {remaining} slots.")
        await user.send(embed=dm_embed)
    except discord.Forbidden:
        await ctx.send(embed=create_info_embed("DM Failed", f"Could not notify {user.mention} via DM."))

@bot.command(name='ports-revoke')
@is_admin()
@commands.cooldown(1, 3, commands.BucketType.user)
async def ports_revoke(ctx, forward_id: int):
    """Revoke a port forward"""
    success, user_id = await remove_port_forward(forward_id, is_admin=True)
    if success and user_id:
        try:
            user = await bot.fetch_user(int(user_id))
            dm_embed = create_warning_embed("Port Forward Revoked", 
                f"One of your port forwards (ID: {forward_id}) has been revoked by an admin.")
            await user.send(embed=dm_embed)
        except:
            pass
        embed = create_success_embed("Revoked", f"Port forward ID {forward_id} revoked.")
        await ctx.send(embed=embed)
    else:
        await ctx.send(embed=create_error_embed("Failed", "Port forward ID not found or removal failed."))

# ============ HELP SYSTEM ============

class HelpView(discord.ui.View):
    def __init__(self, ctx):
        super().__init__(timeout=300)
        self.ctx = ctx
        self.current_category = "user"
        self.message = None
        
        self.select = discord.ui.Select(
            placeholder="Select a category...",
            options=[
                discord.SelectOption(label="👤 User Commands", value="user", description="Basic commands for all users"),
                discord.SelectOption(label="🖥️ VPS Management", value="vps", description="Manage your VPS containers"),
                discord.SelectOption(label="🔌 Port Forwarding", value="ports", description="Manage port forwards"),
                discord.SelectOption(label="🤖 Bot System Commands", value="bot_system", description="Bot economy and stats"),
                discord.SelectOption(label="⚙️ System Commands", value="system", description="Bot and system commands"),
                discord.SelectOption(label="🛡️ Admin Commands", value="admin", description="Administrator commands"),
                discord.SelectOption(label="👑 Main Admin Commands", value="main_admin", description="Main administrator commands"),
            ]
        )
        self.select.callback = self.select_callback
        self.add_item(self.select)
        
        self.update_embed()
    
    async def select_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("This help menu is not for you!", ephemeral=True)
            return
        
        self.current_category = interaction.data["values"][0]
        self.update_embed()
        await interaction.response.edit_message(embed=self.embed, view=self)
    
    def update_embed(self):
        colors = {
            "user": 0x3498db,
            "vps": 0x2ecc71,
            "ports": 0xe74c3c,
            "bot_system": 0x9b59b6,
            "system": 0xf39c12,
            "admin": 0xe67e22,
            "main_admin": 0xf1c40f
        }
        
        color = colors.get(self.current_category, 0x5865F2)
        
        if self.current_category == "user":
            embed = discord.Embed(
                title=f"📚 {BOT_NAME} Help - 👤 User Commands",
                description="Basic commands available to all users",
                color=color
            )
            commands = [
                f"**`{PREFIX}ping`** - Check bot latency with detailed report",
                f"**`{PREFIX}uptime`** - Show host uptime",
                f"**`{PREFIX}plans`** - View free VPS plans with emojis",
                f"**`{PREFIX}freeplans`** - Free plans list",
                f"**`{PREFIX}stats`** - View your invite/boost stats",
                f"**`{PREFIX}myvps`** - List your VPS",
                f"**`{PREFIX}list`** - Detailed VPS list",
                f"**`{PREFIX}manage`** - Manage your VPS (with modern reinstall)",
                f"**`{PREFIX}claimfree inv <1-6>`** - Claim invite VPS",
                f"**`{PREFIX}claimfree boost <1-5>`** - Claim boost VPS",
                f"**`{PREFIX}share-user @user <vps_number>`** - Share VPS access",
                f"**`{PREFIX}share-ruser @user <vps_number>`** - Revoke VPS access",
                f"**`{PREFIX}manage-shared @owner <vps_number>`** - Manage shared VPS"
            ]
            total = 13
            
        elif self.current_category == "vps":
            embed = discord.Embed(
                title=f"📚 {BOT_NAME} Help - 🖥️ VPS Management",
                description="Commands for managing your VPS",
                color=color
            )
            commands = [
                f"**`{PREFIX}myvps`** - List your VPS",
                f"**`{PREFIX}list`** - Detailed VPS list",
                f"**`{PREFIX}manage`** - Manage your VPS (with modern reinstall)",
                f"**`{PREFIX}manage @user`** - Manage another user's VPS (Admin)",
                f"**`{PREFIX}vpsinfo [container]`** - VPS information (Admin)",
                f"**`{PREFIX}vps-stats <container>`** - VPS stats (Admin)",
                f"**`{PREFIX}restart-vps <container>`** - Restart VPS (Admin)",
                f"**`{PREFIX}clone-vps <container> [new_name]`** - Clone VPS (Admin)",
                f"**`{PREFIX}snapshot <container> [snap_name]`** - Create snapshot (Admin)",
                f"**`{PREFIX}restore-backup <container> <snap_name>`** - Restore VPS (Admin)"
            ]
            total = 10
            
        elif self.current_category == "ports":
            embed = discord.Embed(
                title=f"📚 {BOT_NAME} Help - 🔌 Port Forwarding",
                description="Manage port forwarding for your VPS",
                color=color
            )
            commands = [
                f"**`{PREFIX}ports`** - Port forwarding help",
                f"**`{PREFIX}ports add <vps_num> <port>`** - Add port forward",
                f"**`{PREFIX}ports list`** - List your port forwards",
                f"**`{PREFIX}ports remove <id>`** - Remove port forward",
                f"**`{PREFIX}ports-add-user <amount> @user`** - Allocate ports (Admin)",
                f"**`{PREFIX}ports-remove-user <amount> @user`** - Deallocate ports (Admin)",
                f"**`{PREFIX}ports-revoke <id>`** - Revoke port forward (Admin)"
            ]
            total = 7
            
        elif self.current_category == "bot_system":
            embed = discord.Embed(
                title=f"📚 {BOT_NAME} Help - 🤖 Bot System Commands",
                description="Bot economy and statistics commands",
                color=color
            )
            commands = [
                f"**`{PREFIX}plans`** - View free VPS plans",
                f"**`{PREFIX}stats`** - View your invite/boost stats",
                f"**`{PREFIX}addinv @user <amount>`** - Add invites (Admin)",
                f"**`{PREFIX}removeinv @user <amount>`** - Remove invites (Admin)",
                f"**`{PREFIX}addboost @user <amount>`** - Add boosts (Admin)",
                f"**`{PREFIX}removeboost @user <amount>`** - Remove boosts (Admin)",
                f"**`{PREFIX}user-stats @user`** - View user stats (Admin)"
            ]
            total = 7
            
        elif self.current_category == "system":
            embed = discord.Embed(
                title=f"📚 {BOT_NAME} Help - ⚙️ System Commands",
                description="Bot and system management commands",
                color=color
            )
            commands = [
                f"**`{PREFIX}ping`** - Check bot latency with detailed report",
                f"**`{PREFIX}uptime`** - Show host uptime",
                f"**`{PREFIX}serverstats`** - Server statistics (Admin)",
                f"**`{PREFIX}thresholds`** - View resource thresholds",
                f"**`{PREFIX}set-threshold <cpu> <ram>`** - Set thresholds (Admin)",
                f"**`{PREFIX}set-status <type> <name>`** - Set bot status (Admin)",
                f"**`{PREFIX}change-mode <mode>`** - Change bot mode (Main Admin)",
                f"**`{PREFIX}maintenance <on/off>`** - Maintenance mode (Main Admin)",
                f"**`{PREFIX}lxc-list`** - List all LXC containers (Admin)"
            ]
            total = 9
            
        elif self.current_category == "admin":
            embed = discord.Embed(
                title=f"📚 {BOT_NAME} Help - 🛡️ Admin Commands",
                description="Commands for server administrators",
                color=color
            )
            commands = [
                f"**`{PREFIX}create <ram> <cpu> <disk> @user`** - Create VPS",
                f"**`{PREFIX}delete-vps @user <vps_number> [reason]`** - Delete VPS (with confirmation)",
                f"**`{PREFIX}add-resources <container> [ram] [cpu] [disk]`** - Add resources",
                f"**`{PREFIX}resize-vps <container> [ram] [cpu] [disk]`** - Resize VPS",
                f"**`{PREFIX}suspend-vps <container> [reason]`** - Suspend VPS",
                f"**`{PREFIX}unsuspend-vps <container>`** - Unsuspend VPS",
                f"**`{PREFIX}suspension-logs [container]`** - View suspension logs",
                f"**`{PREFIX}whitelist-vps <container> <add|remove>`** - Whitelist VPS",
                f"**`{PREFIX}userinfo @user`** - User information",
                f"**`{PREFIX}list-all`** - List all VPS (detailed)",
                f"**`{PREFIX}exec <container> <command>`** - Execute command",
                f"**`{PREFIX}stop-vps-all`** - Stop all VPS",
                f"**`{PREFIX}restart-vps <container>`** - Restart VPS",
                f"**`{PREFIX}clone-vps <container> [new_name]`** - Clone VPS",
                f"**`{PREFIX}snapshot <container> [snap_name]`** - Create snapshot",
                f"**`{PREFIX}restore-backup <container> <snap_name>`** - Restore backup",
                f"**`{PREFIX}vpsinfo [container]`** - VPS information",
                f"**`{PREFIX}vps-stats <container>`** - VPS stats",
                f"**`{PREFIX}apply-permissions <container>`** - Apply Docker permissions"
            ]
            total = 19
            
        elif self.current_category == "main_admin":
            embed = discord.Embed(
                title=f"📚 {BOT_NAME} Help - 👑 Main Admin Commands",
                description="Commands for the main administrator only",
                color=color
            )
            commands = [
                f"**`{PREFIX}admin-add @user`** - Add admin",
                f"**`{PREFIX}admin-remove @user`** - Remove admin",
                f"**`{PREFIX}admin-list`** - List admins",
                f"**`{PREFIX}maintenance <on/off>`** - Maintenance mode",
                f"**`{PREFIX}set-status <type> <name>`** - Set bot status",
                f"**`{PREFIX}change-mode <mode>`** - Change bot mode",
                f"**`{PREFIX}purge-data @user`** - Purge user data",
                f"**`{PREFIX}confirm-purge <user_id>`** - Confirm purge",
                f"**`{PREFIX}purge-prot @user [vps_num]`** - Protect VPS from purge",
                f"**`{PREFIX}purge-remove-prot @user [vps_num]`** - Remove purge protection",
                f"**`{PREFIX}purge-list-protected`** - List protected VPS",
                f"**`{PREFIX}purge-vm-all`** - Purge ALL unprotected VPS (1 by 1)",
                f"**`{PREFIX}confirm-purge-all`** - Confirm purge all unprotected VPS"
            ]
            total = 13
            
        else:
            embed = discord.Embed(
                title=f"📚 {BOT_NAME} Help",
                description="Select a category from the dropdown",
                color=color
            )
            commands = []
            total = 0
        
        # Set thumbnail if URL is provided
        if THUMBNAIL_URL:
            embed.set_thumbnail(url=THUMBNAIL_URL)
        
        # Set footer with timestamp and icon
        embed.set_footer(
            text=f"{BOT_NAME} VPS Manager • {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            icon_url=THUMBNAIL_URL
        )
        
        embed.add_field(name="⌯⌲ Commands", value="\n".join(commands) if commands else "No commands available", inline=False)
        embed.add_field(name="⌯⌲ Navigation", 
                       value=f"• Use dropdown to switch categories\n• Total commands: {total}\n• Prefix: `{PREFIX}`", 
                       inline=False)
        
        self.embed = embed

@bot.command(name='help')
@commands.cooldown(1, 3, commands.BucketType.user)
async def help_command(ctx):
    """Show interactive help menu"""
    if not await maintenance_check(ctx):
        return
    
    # Check if user already has an active help menu
    user_id = ctx.author.id
    if user_id in active_help_menus:
        try:
            await active_help_menus[user_id].delete()
        except:
            pass
        del active_help_menus[user_id]
    
    view = HelpView(ctx)
    msg = await ctx.send(embed=view.embed, view=view)
    active_help_menus[user_id] = msg
    
    # Remove from dict when menu expires
    async def remove_from_dict():
        await asyncio.sleep(300)
        if user_id in active_help_menus:
            del active_help_menus[user_id]
    
    asyncio.create_task(remove_from_dict())

@bot.command(name='commands')
@commands.cooldown(1, 3, commands.BucketType.user)
async def commands_alias(ctx):
    """Alias for help command"""
    await help_command(ctx)

# ============ TYPO HANDLING ============

@bot.command(name='mangage')
async def manage_typo(ctx):
    """Handle typo for manage command"""
    embed = create_info_embed("Command Correction", f"Did you mean `{PREFIX}manage`? Use the correct command.")
    await ctx.send(embed=embed)

# ============ RUN THE BOT ============

if __name__ == "__main__":
    if DISCORD_TOKEN:
        bot.run(DISCORD_TOKEN)
    else:
        logger.error("No Discord token found. Please set DISCORD_TOKEN in the configuration.")
