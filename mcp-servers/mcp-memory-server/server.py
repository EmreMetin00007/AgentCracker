#!/usr/bin/env python3
"""
MCP Memory Server — HackerAgent için kalıcı, ilişkisel ajan hafızası.
SQLite kullanarak hedefleri, zafiyetleri, credential'ları ve endpoint'leri kaydeder.
Session kapansa bile verilerin saklanmasını sağlar (Phase C).

Kullanım:
    python server.py
"""

import sqlite3
import os
import json
from datetime import datetime
from mcp.server.fastmcp import FastMCP

# Veritabanı dosya yolu (kalıcı olması için kullanıcı dizinini kullan)
DB_PATH = os.path.expanduser("~/.claude/agent_memory.db")

# Server oluştur
mcp = FastMCP(
    "memory-server",
    description="HackerAgent Kalıcı Hafızası - Hedefler, Zafiyetler ve Kimlik Bilgileri veritabanı"
)

def init_db():
    """Veritabanı tablolarını oluşturur."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Zafiyetler (Findings)
    c.execute('''
        CREATE TABLE IF NOT EXISTS findings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            target TEXT NOT NULL,
            type TEXT NOT NULL,
            severity TEXT NOT NULL,
            description TEXT,
            payload TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Kimlik Bilgileri (Credentials)
    c.execute('''
        CREATE TABLE IF NOT EXISTS credentials (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            target TEXT NOT NULL,
            service TEXT NOT NULL,
            username TEXT NOT NULL,
            password TEXT NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Servisler / Portlar (Endpoints)
    c.execute('''
        CREATE TABLE IF NOT EXISTS endpoints (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            target TEXT NOT NULL,
            url_or_port TEXT NOT NULL,
            protocol TEXT,
            state TEXT,
            technologies TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()

# Başlangıçta veritabanını hazırla
init_db()

@mcp.tool()
def store_finding(
    target: str,
    type: str,
    severity: str,
    description: str,
    payload: str = ""
) -> str:
    """Hafızaya yeni bir zafiyet/bulgu (finding) kaydet."""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute(
            "INSERT INTO findings (target, type, severity, description, payload) VALUES (?, ?, ?, ?, ?)",
            (target, type, severity, description, payload)
        )
        conn.commit()
        finding_id = c.lastrowid
        conn.close()
        return f"Bulgu başarıyla kaydedildi. Öğe ID: {finding_id}"
    except Exception as e:
        return f"HATA: Bulgu kaydedilemedi: {str(e)}"

@mcp.tool()
def store_credential(
    target: str,
    service: str,
    username: str,
    password: str
) -> str:
    """Hafızaya ele geçirilmiş kimlik bilgisi (credential) kaydet."""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute(
            "INSERT INTO credentials (target, service, username, password) VALUES (?, ?, ?, ?)",
            (target, service, username, password)
        )
        conn.commit()
        cred_id = c.lastrowid
        conn.close()
        return f"Kimlik bilgisi başarıyla hafızaya yazıldı. ID: {cred_id}"
    except Exception as e:
        return f"HATA: Kimlik bilgisi kaydedilemedi: {str(e)}"

@mcp.tool()
def store_endpoint(
    target: str,
    url_or_port: str,
    protocol: str = "http",
    state: str = "open",
    technologies: str = ""
) -> str:
    """Hafızaya yeni keşfedilmiş bir port, servis veya URL endpoint kaydet."""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        # Check if already exists to avoid massive duplicates
        c.execute("SELECT id FROM endpoints WHERE target=? AND url_or_port=?", (target, url_or_port))
        if c.fetchone():
            return f"Endpoint ({url_or_port}) zaten hafızada mevcut, güncellenmedi."
            
        c.execute(
            "INSERT INTO endpoints (target, url_or_port, protocol, state, technologies) VALUES (?, ?, ?, ?, ?)",
            (target, url_or_port, protocol, state, technologies)
        )
        conn.commit()
        ep_id = c.lastrowid
        conn.close()
        return f"Endpoint başarıyla kaydedildi. ID: {ep_id}"
    except Exception as e:
        return f"HATA: Endpoint kaydedilemedi: {str(e)}"

@mcp.tool()
def get_target_memory(
    target: str
) -> str:
    """
    Belirtilen hedefle ilgili HAFIZADA olan tüm bulguları, credential'ları ve
    endpoint'leri tek bir JSON dökümü olarak getirir.
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        
        result = {"target": target, "findings": [], "credentials": [], "endpoints": []}
        
        for row in c.execute("SELECT * FROM findings WHERE target LIKE ?", (f"%{target}%",)):
            result["findings"].append(dict(row))
            
        for row in c.execute("SELECT * FROM credentials WHERE target LIKE ?", (f"%{target}%",)):
            result["credentials"].append(dict(row))
            
        for row in c.execute("SELECT * FROM endpoints WHERE target LIKE ?", (f"%{target}%",)):
            result["endpoints"].append(dict(row))
            
        conn.close()
        
        if not any([result["findings"], result["credentials"], result["endpoints"]]):
            return f"Hedef '{target}' için hafızada herhangi bir veri bulunamadı."
            
        return json.dumps(result, indent=2)
    except Exception as e:
        return f"HATA: Hafıza okunamadı: {str(e)}"

@mcp.tool()
def drop_target_memory(
    target: str
) -> str:
    """Belirtilen hedefle ilgili tüm kayıtları hafızadan tamamen siler (Sıfırla)."""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("DELETE FROM findings WHERE target LIKE ?", (f"%{target}%",))
        c.execute("DELETE FROM credentials WHERE target LIKE ?", (f"%{target}%",))
        c.execute("DELETE FROM endpoints WHERE target LIKE ?", (f"%{target}%",))
        conn.commit()
        conn.close()
        return f"'{target}' hedefi ile ilgili tüm hafıza verisi TEMİZLENDİ."
    except Exception as e:
        return f"HATA: Hafıza silinemedi: {str(e)}"

if __name__ == "__main__":
    mcp.run()
