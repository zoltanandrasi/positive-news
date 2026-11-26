# Pozitív hírek

Saját üzemeltetésű hírgyűjtő oldal, amely magyar hírportálok RSS-csatornáiból
összegyűjti a pozitív és semleges híreket, és rovatokba rendezve, címmel és
leaddel jeleníti meg őket. Mesterséges intelligencia és külső szolgáltatás
nélkül működik, egyetlen Docker konténerben, Synology NAS-on is.

## Hogyan működik

1. Beállítható időközönként (alapból 2 óránként) letölti a `config/feeds.yaml`-ban
   megadott RSS-csatornákat.
2. A címből és a leadből kulcsszavak alapján kiszűri a negatív híreket
   (`config/filters.yaml`).
3. A híreket rovatba sorolja: a rovatonkénti feedek rögzített rovatba mennek, a
   vegyes feedeknél a cikk webcíme és RSS-címkéi döntenek.
4. SQLite adatbázisba menti őket (ismétlődések nélkül), a régieket törli.
5. A weboldal címlapot, rovatoldalakat és egy `/allapot` oldalt mutat (források
   állapota és a kiszűrt hírek listája az okkal együtt).

## Telepítés Synology NAS-ra (Container Manager)

### 1. A Docker image elérhetővé tétele (egyszer kell)

Minden `main` ágra kerülő változás után a GitHub Actions automatikusan elkészíti az
image-et: `ghcr.io/zoltanandrasi/positive-news:latest`.

Mivel a repó privát, az image is privát lesz. A legegyszerűbb, ha az image-et
nyilvánossá teszed (a kód nem tartalmaz titkot):

1. GitHub → a profilod → **Packages** → `positive-news`
2. **Package settings** → lent **Change visibility** → **Public**

### 2. Projekt létrehozása a NAS-on

1. **File Station**: hozz létre egy mappát, pl. `docker/positive-news`.
2. **Container Manager → Projekt → Létrehozás**
   - Projekt neve: `positive-news`
   - Elérési út: a fenti mappa
   - Forrás: **docker-compose.yml létrehozása**, és másold be a repó
     [`docker-compose.yml`](docker-compose.yml) fájljának tartalmát.
3. **Tovább → Kész**. A Container Manager letölti az image-et és elindítja.
4. Nyisd meg: `http://<NAS-IP>:8080`

Az első frissítés néhány másodperccel az indulás után lefut.

### 3. Frissítés új verzióra

Container Manager → **Kép (Image)** fül: ha a `positive-news` image mellett
„Frissítés elérhető” jelzés van, kattints rá, és a konténer az új verzióval indul újra.
Ha nincs ilyen jelzés: Projekt → `positive-news` → **Művelet → Leállítás**, majd
**Művelet → Build** (újra letölti a `latest` image-et), végül **Indítás**.

## Beállítások

A `docker-compose.yml` környezeti változói:

| Változó | Alapérték | Jelentés |
|---|---|---|
| `REFRESH_INTERVAL_HOURS` | `2` | Frissítés gyakorisága órában (tört is lehet, pl. `0.5`) |
| `RETENTION_DAYS` | `14` | Ennyi napnál régebbi hírek törlődnek |
| `LEAD_MAX_CHARS` | `320` | A lead maximális hossza |
| `SITE_TITLE` | `Jó Hírek` | Az oldal neve |
| `TZ` | `Europe/Budapest` | Időzóna |

Módosítás után a projektet újra kell indítani.

### Források és szűrők

Első induláskor a projekt mappájában létrejön a `config/feeds.yaml` és a
`config/filters.yaml`. Ezeket File Station-ből (vagy a Text Editor csomaggal)
szerkesztheted; a változás a következő frissítéskor lép életbe.

- **Új forrás:** add hozzá a `feeds:` listához névvel, URL-lel és rovattal.
- **Hibás forrás:** az `/allapot` oldalon pirossal látszik; javítsd az URL-t, vagy
  tedd mellé: `enabled: false`.
- **Túl sok vagy túl kevés kiszűrt hír:** az `/allapot` oldal alján látod, mi miért
  esett ki; ehhez igazítsd a `filters.yaml` listáit.

## Fejlesztés

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
pytest

# helyi futtatás
DATA_DIR=./data CONFIG_DIR=./config uvicorn app.main:create_app --factory --reload
# egyszeri frissítés kézzel
DATA_DIR=./data CONFIG_DIR=./config python -m app.fetcher
```
