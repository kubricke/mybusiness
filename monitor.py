import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright

URL = os.environ.get("CALENDAR_URL", "")  # il link e' nei GitHub Secrets, non nel codice
MESI = 5  # mese attuale + 4 successivi
STATE = Path("state.json")

# Freccia "avanti": cerco il bottone che contiene l'icona (path SVG) della freccia destra
NEXT = ':is(button,[role=button]):has(path[d^="M10 6L8.59"])'

# Tutti i giorni del calendario a sinistra: ogni giorno e' un bottone con data-grid-cell
GIORNI_JS = """() => [...document.querySelectorAll('button[data-grid-cell="true"]')]
  .map(b => ({label: b.getAttribute('aria-label') || '', disabled: b.disabled}))"""


def invia_telegram(testo):
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    data = urllib.parse.urlencode({"chat_id": chat_id, "text": testo}).encode()
    urllib.request.urlopen(f"https://api.telegram.org/bot{token}/sendMessage", data, timeout=30)


def giorni_disponibili():
    """Restituisce (totale giorni letti, lista dei giorni con disponibilita')."""
    totale, liberi = 0, []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_context(locale="en-US").new_page()
        page.goto(URL, wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(3000)
        for mese in range(MESI):
            for g in page.evaluate(GIORNI_JS):
                totale += 1
                # giorno senza slot: aria-label tipo "15, Thursday, no available times"
                if "no available times" not in g["label"].lower() and not g["disabled"]:
                    liberi.append(f"{mese}|{g['label']}")
            if mese == MESI - 1:
                break
            nxt = page.locator(NEXT)
            if nxt.count() == 0:
                print("Freccia avanti non trovata, mi fermo qui.")
                break
            nxt.first.click()
            page.wait_for_timeout(1500)
        browser.close()
    return totale, sorted(set(liberi))


def main():
    if os.environ.get("TEST_NOTIFICA") == "1":  # solo per provare Telegram
        invia_telegram("✅ Test: le notifiche Telegram funzionano.")
        print("Messaggio di test inviato.")
        return

    if not URL:
        print("Manca il secret CALENDAR_URL.")
        sys.exit(1)

    totale, liberi = giorni_disponibili()
    print(f"Giorni letti: {totale} - con disponibilita': {len(liberi)}")
    for x in liberi:
        print("  libero:", x)

    if totale == 0:  # pagina non caricata: evita falsi allarmi
        print("Nessun giorno letto: pagina non caricata o struttura cambiata.")
        sys.exit(1)

    precedenti = set(json.loads(STATE.read_text())) if STATE.exists() else set()
    nuovi = set(liberi) - precedenti

    if nuovi:
        invia_telegram("🚨 Attenzione: trovata nuova disponibilità sul calendario nei prossimi mesi!")
        print("Nuova disponibilita' rilevata, notifica inviata.")
    else:
        print("Nessuna novita'.")

    STATE.write_text(json.dumps(liberi))


if __name__ == "__main__":
    main()
