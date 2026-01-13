# Distribuovaný systém

Distribuovaný systém simulující Chang–Roberts volby v kruhové topologii. Každý uzel kombinuje REST API (řídicí rovina) a TCP sockety (datová rovina) a sdílí logy přes centrální agregátor.

## Architektura systému
- REST API (FastAPI) zajišťuje administraci: join/leave, startElection, kill/revive, setDelay, práci se sdílenou proměnnou a health dotazy.
- TCP socket server předává zprávy algoritmu (ELECTION, LEADER, GET_VAR, SET_VAR) sousedům v kruhu.
- Logování probíhá lokálně i do centrálního agregátoru pomocí Python logging handleru.
- Skript `demo.sh` orchestruje scénáře: budování kruhu, volby, selhání, obnovení topologie a práci se sdílenou proměnnou.

## Požadavky
- Python 3.11 nebo novější.
- `pip` pro instalaci závislostí.
- Volitelně GNU `bash` pro spouštění skriptů.

## Instalace
1. (Volitelné) vytvořte virtuální prostředí: `python -m venv .venv && source .venv/bin/activate`.
2. Nainstalujte závislosti: `pip install -r requirements.txt`.
3. Zkopírujte konfigurační šablonu: `cp app/config.example.py app/config_local.py`.

## Konfigurace uzlu
Každý uzel čte nastavení z proměnných prostředí. `app/config_local.py` může tyto hodnoty přepsat pro lokální nasazení (soubor není verzován).

| Proměnná             | Význam                                        | Výchozí hodnota                                          |
|----------------------|-----------------------------------------------|----------------------------------------------------------|
| `NODE_ID`            | Jedinečné ID uzlu                             | `1`                                                      |
| `PORT`               | REST port                                     | `8000`                                                   |
| `HOST`               | Adresa REST API včetně schématu               | `http://127.0.0.1:{PORT}`                                |
| `SOCKET_PORT`        | TCP port pro socket server                     | `9000 + NODE_ID`                                         |
| `LOG_AGGREGATOR_HOST`| Adresa centrálního log agregátoru (volitelné) | žádná (logování pouze lokálně)                           |
| `LOG_AGGREGATOR_PORT`| Port agregátoru                               | `9020` pokud je nastaven host                            |
| `MESSAGE_DELAY`      | Umělá latence při odesílání REST požadavků    | `0.0` (sekundy)                                          |

`app/config.example.py` obsahuje komentovanou ukázku. Pro každý stroj lze nastavit vlastní `config_local.py`, např.:

```python
NODE_ID = 3
HOST = "http://192.168.56.105:8000"
SOCKET_PORT = 9003
LOG_AGGREGATOR_HOST = "192.168.56.103"
LOG_AGGREGATOR_PORT = 9020
```

## Spuštění log agregátoru
Na stroji, který sbírá logy, spusťte:

```bash
python log_aggregator.py --host 0.0.0.0 --port 9020 --output logs/aggregated.log
```

Ostatní uzly se k agregátoru připojí, pokud mají nastaveny `LOG_AGGREGATOR_HOST` a `LOG_AGGREGATOR_PORT`.

## Spuštění uzlu
1. Ujistěte se, že konfigurace odpovídá konkrétnímu uzlu (proměnné prostředí nebo `config_local.py`).
2. Spusťte server: `./run.sh`. Skript startuje FastAPI aplikaci i socket server (`uvicorn app.main:app`).
3. V logu se objeví informace `Node starting...` a `socket_server listening...` s nastavenými porty.

## Demo scénář (`demo.sh`)
Skript automatizuje scénář pro pět uzlů. Pokud necháte výchozí lokální nastavení, není nutné nic exportovat. Pro více strojů můžete zadat konkrétní adresy přes proměnné prostředí:

```bash
export NODE1_HOST=http://192.168.56.103:8000
export NODE2_HOST=http://192.168.56.104:8000
export NODE3_HOST=http://192.168.56.105:8000
export NODE4_HOST=http://192.168.56.106:8000
export NODE5_HOST=http://192.168.56.107:8000

export NODE1_SOCKET_PORT=9001
export NODE2_SOCKET_PORT=9002
export NODE3_SOCKET_PORT=9003
export NODE4_SOCKET_PORT=9004
export NODE5_SOCKET_PORT=9005
```

Spuštění: `./demo.sh`. Skript krok za krokem:
- vytvoří kruh (uzly 1–4), provede základní volbu a nastaví sdílenou proměnnou,
- připojí uzel 5, zapne umělá zpoždění a spustí souběžné volby,
- simuluje výpadek vůdce, obnovu a ověření stavu,
- postupně odebírá uzly až na jediný a znovu je přidává,
- uzavírá scénář finální aktualizací sdílené proměnné a resetem zpoždění.

Výstup sledujte v `logs/aggregated.log` nebo na konzoli agregátoru.

## REST API (curl příklady)
V příkladech nahraďte `<HOST>` adresou cílového uzlu (např. `http://192.168.56.103:8000`).

### Stav uzlu
```bash
curl -s <HOST>/health
```
Vrací `status`, `leader_id`, sousedy a aktuální zpoždění.

### Připojení nového uzlu
```bash
curl -s -X POST <HOST>/join \
	-H "Content-Type: application/json" \
	-d '{"node_id": 3, "host": "http://192.168.56.105:8000", "socket_port": 9003}'
```
Uzlu `<HOST>` sdělí, aby vložil uzel s ID 3 mezi sebe a svého následníka.

### Opustit kruh
```bash
curl -s -X POST <HOST>/leave
```
Uzel informuje sousedy, aby se propojili, a vynuluje vlastní topologii.

### Start voleb
```bash
curl -s -X POST <HOST>/startElection
```
Spustí Chang–Roberts volby, pokud má uzel alespoň jednoho souseda.

### Kill / Revive
```bash
curl -s -X POST <HOST>/kill
curl -s -X POST <HOST>/revive
```
`kill` simuluje výpadek (uzel neobsluhuje REST, ale socket zprávy pouze přeposílí). `revive` vrátí uzel do aktivního stavu.

### Nastavení umělého zpoždění
```bash
curl -s -X POST <HOST>/setDelay \
	-H "Content-Type: application/json" \
	-d '{"delay": 2.5}'
```
Zpoždění se aplikuje před každým odchozím REST voláním tohoto uzlu.

### Sdílená proměnná
```bash
# Zápis (pouze vůdce obsluhuje lokálně)
curl -s -X POST <HOST>/variable \
	-H "Content-Type: application/json" \
	-d '{"value": 123}'

# Čtení
curl -s <HOST>/variable
```
Nevůdcovské uzly požadavek přepošlou přes socket aktuálnímu vůdci. Při selhání vůdce REST vrstva spustí nové volby a vrátí informaci o restartu.

## Logování
- Lokální logy jsou zapisovány na standardní výstup a do souboru (pokud je nakonfigurován). Soubor `logs/aggregated.log` je ignorován v git.
- Centrální agregátor vypisuje logy všech uzlů – včetně health snapshotů, voleb a operací se sdílenou proměnnou.

## Tipy k nasazení
- Každý uzel spusťte na samostatném stroji/VM se správně nastaveným `NODE_ID`, `HOST` a `SOCKET_PORT`.
- Ujistěte se, že firewall povoluje REST i socket porty (default 8000 + 900X).
- Před hromadným scénářem zkontrolujte, že agregátor běží a logy se zaznamenávají.
