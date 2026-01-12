# Distribuovaný Node Demo

## Příprava prostředí
- Nainstalujte Python 3.11+ a nástroj `pip`.
- Vytvořte virtuální prostředí (volitelné) a nainstalujte závislosti příkazem `pip install -r requirements.txt`.
- Zkopírujte šablonu konfigurace: `cp app/config.example.py app/config_local.py` a podle potřeby nastavte hodnoty `NODE_ID`, `HOST`, `SOCKET_PORT`, `LOG_AGGREGATOR_*`.
- Alternativně nastavte přímo proměnné prostředí: `NODE_ID`, `PORT`, `HOST`, `SOCKET_PORT`, `LOG_AGGREGATOR_HOST`, `LOG_AGGREGATOR_PORT`, `MESSAGE_DELAY`.

## Spuštění log agregátoru
- Na uzlu, který sbírá logy, spusťte `python log_aggregator.py --host 0.0.0.0 --port 9020 --output logs/aggregated.log`.
- Ostatní uzly se připojí automaticky, pokud mají v konfiguraci adresu agregátoru.

## Start uzlu
- Exportujte parametry uzlu (`NODE_ID`, `HOST`, `PORT`, `SOCKET_PORT`, případně zpoždění zpráv).
- Spusťte `./run.sh`, který nastartuje FastAPI a socketový server.

## Ukázkový scénář
- Připravte proměnné prostředí pro skript: `NODE_COUNT`, `NODE_API_BASE_HOST`, `NODE_API_BASE_PORT`, `NODE_API_PORT_STEP`, `NODE_SOCKET_BASE_PORT`, `NODE_SOCKET_PORT_STEP`, případně konkrétní `NODE{i}_HOST` / `NODE{i}_SOCKET_PORT`.
- Spusťte `./demo.sh` a sledujte automatické prověření: vytvoření kruhu, volby lídra, simulované zpoždění, operace kill/revive, leave/join a práci se sdílenou proměnnou.

## Užitečné REST endpointy
- `/health` — stav uzlu a jeho sousedů.
- `/startElection`, `/leader`, `/kill`, `/revive`, `/leave` — řízení životního cyklu a voleb.
- `/variable` (GET/POST) — čtení nebo zápis sdílené proměnné.