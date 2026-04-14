#!/usr/bin/env python3
"""
MCP CTF Platform Server — CTF platformlarına (CTFd, HackTheBox, TryHackMe) 
API erişimi sağlayan MCP server.

Desteklenen platformlar:
- CTFd (self-hosted veya third-party)
- HackTheBox API
- TryHackMe API

Kullanım:
    python server.py
"""

import os
import json
import requests
from typing import Optional
from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    "ctf-platform",
    description="CTF platform API entegrasyonu — challenge yönetimi ve flag submission"
)

# ============================================================
# YAPILANDIRMA
# ============================================================

# Ortam değişkenlerinden platform bilgileri
CTFD_URL = os.environ.get("CTFD_URL", "")
CTFD_TOKEN = os.environ.get("CTFD_TOKEN", "")
HTB_TOKEN = os.environ.get("HTB_TOKEN", "")
THM_TOKEN = os.environ.get("THM_TOKEN", "")

def get_headers(platform: str) -> dict:
    """Platform için auth headerlerini döndür."""
    if platform == "ctfd":
        return {
            "Authorization": f"Token {CTFD_TOKEN}",
            "Content-Type": "application/json"
        }
    elif platform == "htb":
        return {
            "Authorization": f"Bearer {HTB_TOKEN}",
            "Content-Type": "application/json"
        }
    elif platform == "thm":
        return {
            "Authorization": f"Bearer {THM_TOKEN}",
            "Content-Type": "application/json"
        }
    return {}

# ============================================================
# CTFd ARAÇLARI
# ============================================================

@mcp.tool()
def ctfd_list_challenges(
    ctfd_url: str = "",
    token: str = ""
) -> str:
    """
    CTFd platformunda challenge'ları listele.
    
    Args:
        ctfd_url: CTFd URL'si (ör: https://ctf.example.com)
        token: CTFd API token
    """
    url = ctfd_url or CTFD_URL
    auth_token = token or CTFD_TOKEN
    
    if not url:
        return "HATA: CTFd URL belirtilmedi. ctfd_url parametresi veya CTFD_URL env var gerekli."
    
    try:
        headers = {"Authorization": f"Token {auth_token}", "Content-Type": "application/json"}
        response = requests.get(f"{url.rstrip('/')}/api/v1/challenges", headers=headers, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        if data.get("success"):
            challenges = data.get("data", [])
            output = f"Toplam {len(challenges)} challenge bulundu:\n\n"
            for c in challenges:
                solved = "✅" if c.get("solved_by_me") else "⬜"
                output += f"{solved} [{c.get('category', 'N/A')}] {c.get('name')} — {c.get('value', 0)} puan\n"
            return output
        else:
            return f"API hatası: {data}"
    except Exception as e:
        return f"HATA: {str(e)}"


@mcp.tool()
def ctfd_get_challenge(
    challenge_id: int,
    ctfd_url: str = "",
    token: str = ""
) -> str:
    """
    CTFd'de belirli bir challenge'ın detaylarını getir.
    
    Args:
        challenge_id: Challenge ID
        ctfd_url: CTFd URL'si
        token: CTFd API token
    """
    url = ctfd_url or CTFD_URL
    auth_token = token or CTFD_TOKEN
    
    if not url:
        return "HATA: CTFd URL belirtilmedi."
    
    try:
        headers = {"Authorization": f"Token {auth_token}", "Content-Type": "application/json"}
        response = requests.get(
            f"{url.rstrip('/')}/api/v1/challenges/{challenge_id}",
            headers=headers, timeout=30
        )
        response.raise_for_status()
        data = response.json()
        
        if data.get("success"):
            c = data.get("data", {})
            output = f"""
Challenge: {c.get('name')}
Kategori: {c.get('category')}
Puan: {c.get('value')}
Çözülme sayısı: {c.get('solves', 0)}
Açıklama: {c.get('description')}

Dosyalar: {json.dumps(c.get('files', []), indent=2)}
Tags: {c.get('tags', [])}
Hints: {c.get('hints', [])}
"""
            return output
        else:
            return f"API hatası: {data}"
    except Exception as e:
        return f"HATA: {str(e)}"


@mcp.tool()
def ctfd_submit_flag(
    challenge_id: int,
    flag: str,
    ctfd_url: str = "",
    token: str = ""
) -> str:
    """
    CTFd'de flag gönder.
    
    Args:
        challenge_id: Challenge ID
        flag: Gönderilecek flag
        ctfd_url: CTFd URL'si
        token: CTFd API token
    """
    url = ctfd_url or CTFD_URL
    auth_token = token or CTFD_TOKEN
    
    if not url:
        return "HATA: CTFd URL belirtilmedi."
    
    try:
        headers = {"Authorization": f"Token {auth_token}", "Content-Type": "application/json"}
        response = requests.post(
            f"{url.rstrip('/')}/api/v1/challenges/attempt",
            headers=headers,
            json={"challenge_id": challenge_id, "submission": flag},
            timeout=30
        )
        response.raise_for_status()
        data = response.json()
        
        if data.get("success"):
            status = data.get("data", {}).get("status", "")
            if status == "correct":
                return f"🎉 DOĞRU FLAG! Challenge çözüldü!"
            elif status == "already_solved":
                return f"✅ Bu challenge zaten çözülmüş."
            else:
                return f"❌ Yanlış flag: {flag}"
        else:
            return f"API hatası: {data}"
    except Exception as e:
        return f"HATA: {str(e)}"


@mcp.tool()
def ctfd_download_files(
    challenge_id: int,
    output_dir: str = "./challenge_files",
    ctfd_url: str = "",
    token: str = ""
) -> str:
    """
    CTFd'den challenge dosyalarını indir.
    
    Args:
        challenge_id: Challenge ID
        output_dir: İndirme dizini
        ctfd_url: CTFd URL'si
        token: CTFd API token
    """
    url = ctfd_url or CTFD_URL
    auth_token = token or CTFD_TOKEN
    
    if not url:
        return "HATA: CTFd URL belirtilmedi."
    
    try:
        headers = {"Authorization": f"Token {auth_token}", "Content-Type": "application/json"}
        
        # Challenge bilgisini al
        response = requests.get(
            f"{url.rstrip('/')}/api/v1/challenges/{challenge_id}",
            headers=headers, timeout=30
        )
        response.raise_for_status()
        data = response.json()
        
        files = data.get("data", {}).get("files", [])
        if not files:
            return "Bu challenge'da dosya bulunmuyor."
        
        os.makedirs(output_dir, exist_ok=True)
        downloaded = []
        
        for file_url in files:
            if not file_url.startswith("http"):
                file_url = f"{url.rstrip('/')}{file_url}"
            
            filename = file_url.split("/")[-1].split("?")[0]
            filepath = os.path.join(output_dir, filename)
            
            r = requests.get(file_url, headers=headers, timeout=60)
            with open(filepath, "wb") as f:
                f.write(r.content)
            downloaded.append(filepath)
        
        return f"İndirilen dosyalar:\n" + "\n".join(f"  - {f}" for f in downloaded)
    except Exception as e:
        return f"HATA: {str(e)}"

# ============================================================
# HACKTHEBOX ARAÇLARI
# ============================================================

@mcp.tool()
def htb_list_machines(
    token: str = "",
    retired: bool = False
) -> str:
    """
    HackTheBox'ta makine listesi al.
    
    Args:
        token: HTB API token
        retired: Emekli makineleri dahil et
    """
    auth_token = token or HTB_TOKEN
    if not auth_token:
        return "HATA: HTB_TOKEN belirtilmedi."
    
    try:
        headers = {"Authorization": f"Bearer {auth_token}"}
        endpoint = "https://labs.hackthebox.com/api/v4/machine/list"
        if retired:
            endpoint = "https://labs.hackthebox.com/api/v4/machine/list/retired"
        
        response = requests.get(endpoint, headers=headers, timeout=30)
        response.raise_for_status()
        machines = response.json().get("data", [])
        
        output = f"Toplam {len(machines)} makine:\n\n"
        for m in machines[:30]:
            diff = m.get("difficultyText", "?")
            os_type = m.get("os", "?")
            name = m.get("name", "?")
            output += f"  [{os_type}] {name} — {diff}\n"
        
        return output
    except Exception as e:
        return f"HATA: {str(e)}"


@mcp.tool()
def htb_submit_flag(
    machine_id: int,
    flag: str,
    difficulty: int = 50,
    token: str = ""
) -> str:
    """
    HackTheBox'ta flag gönder.
    
    Args:
        machine_id: Makine ID
        flag: Flag
        difficulty: Zorluk puanı (1-100)
        token: HTB API token
    """
    auth_token = token or HTB_TOKEN
    if not auth_token:
        return "HATA: HTB_TOKEN belirtilmedi."
    
    try:
        headers = {
            "Authorization": f"Bearer {auth_token}",
            "Content-Type": "application/json"
        }
        response = requests.post(
            "https://labs.hackthebox.com/api/v4/flag/own",
            headers=headers,
            json={"id": machine_id, "flag": flag, "difficulty": difficulty},
            timeout=30
        )
        response.raise_for_status()
        data = response.json()
        
        if data.get("success"):
            return f"🎉 FLAG DOĞRU! Makine pwned!"
        else:
            return f"❌ Yanlış flag veya makine."
    except Exception as e:
        return f"HATA: {str(e)}"

# ============================================================
# GENEL CTF YARDIMCI ARAÇLAR
# ============================================================

@mcp.tool()
def ctf_decode(
    text: str,
    encoding: str = "auto"
) -> str:
    """
    Metni çeşitli encoding'lerden decode et.
    
    Args:
        text: Decode edilecek metin
        encoding: 'auto', 'base64', 'base32', 'hex', 'rot13', 'url', 'binary', 'decimal'
    """
    import base64
    import codecs
    import urllib.parse
    
    results = []
    
    if encoding == "auto" or encoding == "base64":
        try:
            decoded = base64.b64decode(text).decode('utf-8', errors='replace')
            results.append(f"Base64: {decoded}")
        except:
            if encoding == "base64":
                results.append("Base64 decode başarısız")
    
    if encoding == "auto" or encoding == "base32":
        try:
            decoded = base64.b32decode(text).decode('utf-8', errors='replace')
            results.append(f"Base32: {decoded}")
        except:
            if encoding == "base32":
                results.append("Base32 decode başarısız")
    
    if encoding == "auto" or encoding == "hex":
        try:
            decoded = bytes.fromhex(text.replace(" ", "").replace("0x", "")).decode('utf-8', errors='replace')
            results.append(f"Hex: {decoded}")
        except:
            if encoding == "hex":
                results.append("Hex decode başarısız")
    
    if encoding == "auto" or encoding == "rot13":
        decoded = codecs.decode(text, 'rot_13')
        results.append(f"ROT13: {decoded}")
    
    if encoding == "auto" or encoding == "url":
        try:
            decoded = urllib.parse.unquote(text)
            if decoded != text:
                results.append(f"URL: {decoded}")
        except:
            pass
    
    if encoding == "auto" or encoding == "binary":
        try:
            bits = text.replace(" ", "")
            if all(c in '01' for c in bits) and len(bits) % 8 == 0:
                decoded = ''.join(chr(int(bits[i:i+8], 2)) for i in range(0, len(bits), 8))
                results.append(f"Binary: {decoded}")
        except:
            pass
    
    if encoding == "auto" or encoding == "decimal":
        try:
            nums = text.split()
            if all(n.isdigit() and int(n) < 128 for n in nums):
                decoded = ''.join(chr(int(n)) for n in nums)
                results.append(f"Decimal: {decoded}")
        except:
            pass
    
    return "\n".join(results) if results else "Decode edilemedi"


@mcp.tool()
def ctf_hash_identify(hash_value: str) -> str:
    """
    Hash tipini tanımla.
    
    Args:
        hash_value: Hash değeri
    """
    length = len(hash_value)
    
    identifications = []
    
    if length == 32:
        identifications.extend(["MD5", "NTLM", "MD4"])
    elif length == 40:
        identifications.extend(["SHA-1", "MySQL5"])
    elif length == 56:
        identifications.append("SHA-224")
    elif length == 64:
        identifications.extend(["SHA-256", "Keccak-256"])
    elif length == 96:
        identifications.append("SHA-384")
    elif length == 128:
        identifications.extend(["SHA-512", "Whirlpool"])
    elif hash_value.startswith("$1$"):
        identifications.append("MD5crypt")
    elif hash_value.startswith("$2"):
        identifications.append("bcrypt")
    elif hash_value.startswith("$5$"):
        identifications.append("SHA-256crypt")
    elif hash_value.startswith("$6$"):
        identifications.append("SHA-512crypt")
    elif hash_value.startswith("$apr1$"):
        identifications.append("Apache MD5")
    elif ":" in hash_value and length > 32:
        identifications.append("Muhtemelen Hash:Salt formatı")
    
    if identifications:
        return f"Hash: {hash_value}\nUzunluk: {length}\nOlası tipler:\n" + "\n".join(f"  - {h}" for h in identifications)
    else:
        return f"Hash: {hash_value}\nUzunluk: {length}\nTip tanımlanamadı. hashid veya hash-identifier aracını deneyin."


# ============================================================
# SERVER BAŞLAT
# ============================================================

if __name__ == "__main__":
    mcp.run(transport="stdio")
