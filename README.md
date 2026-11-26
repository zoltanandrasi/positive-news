# Positive News

A self-hosted news aggregator that collects positive and neutral news from the
RSS feeds of Hungarian news sites and shows them by category, with title and
lead. The news and the website text are in Hungarian. It needs no AI and no
external service, and runs in a single Docker container, including on a
Synology NAS.

## How it works

1. At a configurable interval (every 2 hours by default) it downloads the RSS
   feeds listed in `config/feeds.yaml`.
2. It hides negative news based on keywords in the title and lead
   (`config/filters.yaml`).
3. It assigns each article to a category: single-section feeds go to a fixed
   category, and for mixed feeds the article URL and RSS tags decide.
4. It stores articles in SQLite without duplicates and deletes old ones.
5. The website has a home page, category pages and a `/status` page (feed health
   and the list of blocked articles with the reason).

## Installing on a Synology NAS (Container Manager)

### 1. Make the Docker image available (once)

Every change merged to `main` triggers GitHub Actions, which builds the image
`ghcr.io/zoltanandrasi/positive-news:latest`.

Because the repository is private, the image is private too. The simplest option
is to make the image public (the code contains no secrets):

1. GitHub → your profile → **Packages** → `positive-news`
2. **Package settings** → at the bottom **Change visibility** → **Public**

### 2. Create the project on the NAS

1. **File Station**: create a folder, e.g. `docker/positive-news`, and inside it two
   empty subfolders: `config` and `data`. Synology does not create missing
   bind-mount folders, so without them the project fails to start with
   "Bind mount failed: ... does not exist". Leave both empty.
2. **Container Manager → Project → Create**
   - Project name: `positive-news`
   - Path: the folder above
   - Source: **Create docker-compose.yml**, and paste the contents of
     [`docker-compose.yml`](docker-compose.yml) from this repository.
3. **Next → Done**. Container Manager pulls the image and starts it.
4. Open `http://<NAS-IP>:8080`

The first refresh runs a few seconds after startup.

If every feed on the `/status` page shows `Temporary failure in name resolution`,
the container cannot resolve host names. The compose file already sets public DNS
servers (`dns:` with 1.1.1.1 and 8.8.8.8) to avoid this. If it still happens,
check that the DSM firewall (Control Panel → Security → Firewall) allows traffic
from the Docker networks, and that the NAS itself has a working DNS server under
Control Panel → Network → General.

### 3. Updates

Updates are automatic. The compose file includes Watchtower, which checks GitHub
every hour and restarts `positive-news` when a new image is available (it only
touches containers with the `com.centurylinklabs.watchtower.enable` label). The
`/status` page shows the running version.

To update right away: Project → `positive-news` → **Action → Build**
(`pull_policy: always` makes it download the newest image).

## Settings

Environment variables in `docker-compose.yml`:

| Variable | Default | Meaning |
|---|---|---|
| `REFRESH_INTERVAL_HOURS` | `2` | Refresh interval in hours (fractions allowed, e.g. `0.5`) |
| `RETENTION_DAYS` | `14` | Articles older than this are deleted |
| `LEAD_MAX_CHARS` | `320` | Maximum lead length |
| `SITE_TITLE` | `Jó Hírek` | Site name shown in the header |
| `UI_LANGUAGE` | `hu` | Website text language: `hu` or `en` (the news itself is always Hungarian) |
| `TZ` | `Europe/Budapest` | Time zone |

Restart the project after changing them.

### Feeds and filters

The app uses its built-in feed list and filter list, and they are updated
automatically with every new version. On each start, up-to-date copies are
written to the `config` folder as `feeds.example.yaml` and `filters.example.yaml`.

To customize, copy `feeds.example.yaml` to `feeds.yaml` (or
`filters.example.yaml` to `filters.yaml`) in File Station and edit it. Your file
then replaces the built-in one, and changes apply from the next refresh. Delete it
to go back to the built-in list. The `/status` page shows which one is in use.

- **New feed:** add it to the `feeds:` list with a name, URL and category.
- **Broken feed:** it shows in red on the `/status` page; fix the URL or add
  `enabled: false`.
- **Too many or too few blocked articles:** the bottom of the `/status` page shows
  what was blocked and why; adjust the lists in `filters.yaml`. The filter terms
  are Hungarian because the articles are, and each has its English meaning in a
  comment.

Earlier versions copied the lists into `config` on first start. An unedited copy
like that is renamed to `*.yaml.old` automatically so the built-in list is used.

## Development

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
pytest

# run locally
DATA_DIR=./data CONFIG_DIR=./config uvicorn app.main:create_app --factory --reload
# run one refresh by hand
DATA_DIR=./data CONFIG_DIR=./config python -m app.fetcher
```

Website text lives in `app/i18n.py`.
