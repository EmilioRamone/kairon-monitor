"""
KAIRON USADOS MONITOR — versión cloud (GitHub Actions)
=======================================================
Corre una sola vez: lee estado, compara, notifica y guarda.
El scheduling (cada 15 min) lo maneja GitHub Actions.

Secrets requeridos en el repo de GitHub:
    TELEGRAM_TOKEN
    TELEGRAM_CHAT_ID
"""

import requests
import json
import os
import logging
from datetime import datetime
from bs4 import BeautifulSoup
from pathlib import Path

URL       = "https://www.kaironmusic.com.ar/usados/con-stock/"
ESTADO_DB = "kairon_estado.json"

TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(message)s",
    datefmt="%d/%m %H:%M",
)
log = logging.getLogger(__name__)


def obtener_productos() -> dict:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0 Safari/537.36"
        )
    }
    try:
        resp = requests.get(URL, headers=headers, timeout=20)
        resp.raise_for_status()
    except requests.RequestException as e:
        log.error(f"Error al acceder a Kairon: {e}")
        return {}

    soup = BeautifulSoup(resp.text, "html.parser")
    productos = {}

    items = soup.select("li.js-item-product, li[class*='item-product']")

    if not items:
        for a in soup.select("a[href*='/productos/']"):
            nombre = a.get_text(strip=True)
            if nombre and "*USADO*" in nombre.upper():
                url_prod = a.get("href", "")
                if not url_prod.startswith("http"):
                    url_prod = "https://www.kaironmusic.com.ar" + url_prod
                productos[nombre] = {"url": url_prod, "precio": ""}
        return productos

    for item in items:
        nombre_tag = (
            item.select_one(".item-name")
            or item.select_one("[class*='item-name']")
            or item.select_one("h2")
            or item.select_one("h3")
        )
        if not nombre_tag:
            continue
        nombre = nombre_tag.get_text(strip=True)
        if not nombre:
            continue

        link = item.select_one("a[href*='/productos/']")
        url_prod = ""
        if link:
            url_prod = link.get("href", "")
            if not url_prod.startswith("http"):
                url_prod = "https://www.kaironmusic.com.ar" + url_prod

        precio_tag = (
            item.select_one(".item-price")
            or item.select_one("[class*='price']")
        )
        precio = precio_tag.get_text(strip=True) if precio_tag else ""

        productos[nombre] = {"url": url_prod, "precio": precio}

    return productos


def cargar_estado() -> dict:
    p = Path(ESTADO_DB)
    if p.exists():
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    return {}


def guardar_estado(productos: dict):
    with open(ESTADO_DB, "w", encoding="utf-8") as f:
        json.dump(productos, f, ensure_ascii=False, indent=2)


def telegram(msg: str):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        log.warning("Secrets de Telegram no configurados.")
        return
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "HTML"},
            timeout=10,
        )
        resp.raise_for_status()
        log.info("✅ Telegram enviado")
    except Exception as e:
        log.error(f"❌ Error Telegram: {e}")


def comparar_y_notificar(anteriores: dict, actuales: dict):
    nuevos    = set(actuales) - set(anteriores)
    removidos = set(anteriores) - set(actuales)

    if not nuevos and not removidos:
        log.info("Sin cambios.")
        return

    ahora  = datetime.now().strftime("%d/%m/%Y %H:%M")
    lineas = [f"🎸 <b>Kairon Usados — {ahora}</b>\n"]

    if nuevos:
        lineas.append("🆕 <b>Productos nuevos:</b>")
        for n in sorted(nuevos):
            p = actuales[n]
            precio  = f" — {p['precio']}" if p["precio"] else ""
            url_str = f"\n   <a href='{p['url']}'>{p['url']}</a>" if p["url"] else ""
            lineas.append(f"• {n}{precio}{url_str}")

    if removidos:
        lineas.append("\n🗑️ <b>Productos removidos / vendidos:</b>")
        for n in sorted(removidos):
            lineas.append(f"• {n}")

    telegram("\n".join(lineas))


def main():
    log.info(f"🔍 Chequeando {URL}")
    anteriores = cargar_estado()
    actuales   = obtener_productos()

    if not actuales:
        log.warning("Fetch vacío — sin modificar estado.")
        return

    log.info(f"📋 {len(actuales)} productos en página")

    if not anteriores:
        log.info("Primera ejecución — registrando estado inicial.")
        guardar_estado(actuales)
        return

    comparar_y_notificar(anteriores, actuales)
    guardar_estado(actuales)


if __name__ == "__main__":
    main()
