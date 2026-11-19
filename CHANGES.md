# Site polish changes (Nov 2026)

## Added
- Per-page meta descriptions, canonical tags, Open Graph / Twitter tags (`backend/seo.py` + `base.html`)
- Share image `static/images/og-share.jpg` (1200x630)
- `/robots.txt`, `/sitemap.xml`, `/llms.txt` (generated from `backend/seo.py`)
- Breadcrumbs (visible + BreadcrumbList JSON-LD), WebSite JSON-LD
- Custom 404 page with useful links (noindex); 403/405 handled too
- `/privacy` page, linked in footer
- Skip-to-content link, `id="main-content"`
- Optional Google Analytics: set `GA_MEASUREMENT_ID` (off by default)
- `SITE_URL` env var for canonical URLs / sitemap behind your custom domain

## Fixed / improved
- Home page title now descriptive; every page has a unique title
- Footer copyright year is dynamic
- Cache headers on static files (30d images/vendor/video, 1d CSS/JS); gzip via flask-compress
- Security headers (nosniff, referrer policy, frame options)
- Home hero image preloaded (LCP); About video gets poster + `preload=metadata`
- About page images lazy-loaded with dimensions; "placeholder logo" alt text fixed
- Mobile overflow guards (media max-width, scrollable comparison table)
- `gunicorn` was in the Procfile but missing from requirements.txt - added

## Not done (needs your input or doesn't apply)
- Custom domain, real photos, case studies, FAQ, response-time promise, sticky CTA, thank-you page,
  local-business schema: this is a data portal, not a service business
- Vite/React titles and production source maps: project is Flask/Jinja, none exist
- Font Awesome/Bootstrap are still CDN-loaded (self-hosting needs a network-enabled build)
