# Target: Widget Shop (local dev server)

A two-page development site, used as the worked example and as a fast regression fixture.
It runs on this machine's loopback, so `scripts/site-bridge.sh` is exercised too.

Recreate the site it describes with:

```bash
mkdir -p /tmp/devsite && cd /tmp/devsite
cat > index.html <<'HTML'
<!doctype html><html><head><title>Widget Shop</title></head>
<body><main role="main">
<h1>Widget Shop</h1>
<p>A local development server, standing in for something you are building.</p>
<ul><li><a href="/catalogue.html">Catalogue</a></li></ul>
</main></body></html>
HTML
cat > catalogue.html <<'HTML'
<!doctype html><html><head><title>Catalogue</title></head>
<body><main role="main">
<h1>Catalogue</h1>
<h2>Sprockets</h2><p>Six sizes, all metric.</p>
<h2>Grommets</h2><p>Rubber and nitrile.</p>
<form><label>Search<input name="q" placeholder="sprocket"></label><button>Search</button></form>
</main></body></html>
HTML
python3 -m http.server 3000 --bind 127.0.0.1
```

## Scope

Build the catalogue as a native list with the two product categories and their
descriptions, and the search field from the catalogue page. No networking — bundle the
content locally.

Neutral styling; there is no brand to reproduce.
