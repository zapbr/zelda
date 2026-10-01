# Zelda Concert RSS Monitor

Creates a personal RSS feed from the official:
https://zelda.gameconcerts.com/

The workflow checks the site hourly and publishes `feed.xml` through GitHub Pages.

## Setup

1. Create a public GitHub repository named `zelda-rss` (or another name).
2. Upload all files from this project.
3. Go to **Settings → Pages**.
4. Under **Build and deployment**, choose **Deploy from a branch**.
5. Select branch `main` and folder `/ (root)`.
6. Save.
7. Go to **Actions → Update Zelda concert RSS → Run workflow** once manually.
8. Your feed will be:

   https://YOUR-USERNAME.github.io/zelda-rss/feed.xml

Replace `YOUR-USERNAME` and `zelda-rss` with your GitHub username and repository name.

## Important

The scraper intentionally fails if it extracts zero concerts. This prevents a redesign of the source site from silently replacing a valid feed with an empty one.

The source currently exposes individual concerts with country, city, date, time, orchestra and venue. It also exposes states such as "sold out" and future sale information.

If the site changes its HTML structure, adjust `extract_events()` in `scraper.py`.

## Local test

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python scraper.py
```

Windows PowerShell:

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python scraper.py
```
