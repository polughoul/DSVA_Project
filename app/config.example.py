"""Vzor lokální konfigurace.

Zkopírujte soubor do ``app/config_local.py`` a upravte hodnoty
pro svou instalaci. Proměnné definované zde přepíší nastavení
vygenerovaná v ``app/config.py``.
"""

# Identifikátor uzlu v kruhu (používá se i pro výběr portu)
NODE_ID = 1

# HTTP adresa REST API tohoto uzlu
HOST = "http://192.168.56.103:8000"

# Port REST API
PORT = 8000

# Port socket serveru (standardně 9000 + NODE_ID)
SOCKET_PORT = 9001

# Adresa log agregátoru (ponechte None, pokud se nemá připojovat)
LOG_AGGREGATOR_HOST = "192.168.56.103"
LOG_AGGREGATOR_PORT = 9020

# Volitelně lze nastavit zpoždění odesílání zpráv
MESSAGE_DELAY = 0.0
