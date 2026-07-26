#!/usr/bin/env python3
"""Statik blog üretici.

Soro API'sinden yazı listesini ve içerikleri çeker, /blog/ altına tamamen
statik, indekslenebilir HTML sayfalar üretir ve sitemap.xml'i yeniden yazar.
Soro panelinden yeni yazı yayınlandığında bu script'i tekrar çalıştırmak
yeterlidir (GitHub Action bunu günlük yapar):

    python3 tools/build-blog.py
"""
import json
import html as htmlmod
import os
import re
import sys
import urllib.request
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = "https://newslearner.com"
TOKEN = "a4b15ddd-bcef-4fae-88b7-d9ce5ebb8a2b"
API = "https://app.trysoro.com"
APP_URL = "https://apps.apple.com/us/app/newslearner-learn-languages/id6757966210"

# Sitemap'teki statik sayfalar: (path, lastmod). Blog sayfaları otomatik eklenir.
STATIC_PAGES = [
    ("/", "2026-07-26"),
    ("/blog/", None),  # None -> en yeni yazının tarihi
    ("/privacy.html", "2026-03-12"),
    ("/terms.html", "2026-03-12"),
    ("/data-deletion.html", "2026-07-16"),
]


def _ssl_context():
    import ssl
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


_CTX = _ssl_context()


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "newslearner-blog-build/1.0"})
    with urllib.request.urlopen(req, timeout=30, context=_CTX) as r:
        return r.read()


def get_articles():
    js = fetch(f"{API}/api/embed/{TOKEN}?theme=dark").decode("utf-8")
    m = re.search(r"var SORO_ARTICLES = (\[.*?\]);\n", js, re.S)
    if not m:
        raise SystemExit("SORO_ARTICLES embed script'inde bulunamadı")
    articles = json.loads(m.group(1))
    for a in articles:
        # slug dosya yolu kurmakta kullanılıyor — dış veriyi doğrulamadan kullanma
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,120}", a.get("slug") or ""):
            raise SystemExit(f"Geçersiz slug, build durduruldu: {a.get('slug')!r}")
        if not a.get("content"):
            data = json.loads(fetch(f"{API}/api/embed/{TOKEN}/article/{a['id']}"))
            a["content"] = data["content"]
    articles.sort(key=lambda a: a["isoDate"], reverse=True)
    return articles


def esc(s):
    return htmlmod.escape(s or "", quote=True)


def reading_minutes(content):
    words = len(re.sub(r"<[^>]+>", " ", content).split())
    return max(1, round(words / 200))


def cover_path(a):
    return f"blog/{a['slug']}/cover.webp"


def download_covers(articles):
    for a in articles:
        if not a.get("image"):
            a["cover"] = None
            continue
        dest = os.path.join(ROOT, cover_path(a))
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        if not os.path.exists(dest):
            open(dest, "wb").write(fetch(a["image"]))
        a["cover"] = "/" + cover_path(a)
        try:
            from PIL import Image
            with Image.open(dest) as im:
                a["cover_w"], a["cover_h"] = im.size
        except Exception:
            a["cover_w"] = a["cover_h"] = None


NAV = f"""<nav>
  <div class="wrap">
    <a class="brand" href="/"><img src="/favicon.png" alt="" width="34" height="34">NewsLearner</a>
    <div class="navlinks">
      <a href="/#how">How it works</a>
      <a href="/#inside">Inside the app</a>
      <a href="/#faq">FAQ</a>
      <a href="/blog/" style="color:var(--cream)">Blog</a>
      <a class="btn" href="{APP_URL}" target="_blank" rel="noopener">Get the app</a>
    </div>
  </div>
</nav>"""

FOOTER = """<footer>
  <div class="wrap">
    <a class="brand" href="/" style="color:var(--cream)"><img src="/favicon.png" alt="" width="28" height="28" style="border-radius:8px">NewsLearner</a>
    <div class="foot-links">
      <a href="/blog/">Blog</a>
      <a href="/privacy.html">Privacy</a>
      <a href="/terms.html">Terms</a>
      <a href="mailto:support@newslearner.com">support@newslearner.com</a>
    </div>
  </div>
</footer>"""


def head(title, description, canonical, og_type="website", og_image=f"{SITE}/og-image.png", extra=""):
    return f"""<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="{esc(description)}">
<link rel="canonical" href="{canonical}">
<meta name="theme-color" content="#0A0E2A">
<meta property="og:site_name" content="NewsLearner">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(description)}">
<meta property="og:type" content="{og_type}">
<meta property="og:url" content="{canonical}">
<meta property="og:image" content="{og_image}">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{esc(title)}">
<meta name="twitter:description" content="{esc(description)}">
<meta name="twitter:image" content="{og_image}">
<link rel="icon" type="image/png" href="/favicon.png">
<link rel="apple-touch-icon" href="/apple-touch-icon.png">
<link rel="preload" href="/assets/fonts/jakarta-400.woff2" as="font" type="font/woff2" crossorigin>
<link rel="preload" href="/assets/fonts/jakarta-800.woff2" as="font" type="font/woff2" crossorigin>
<link rel="stylesheet" href="/blog/blog.css">
<link rel="alternate" type="application/rss+xml" title="NewsLearner Blog" href="/blog/feed.xml">
{extra}"""


def card(a):
    img = ""
    if a["cover"]:
        dims = f' width="{a["cover_w"]}" height="{a["cover_h"]}"' if a.get("cover_w") else ""
        # kart linkinin içinde başlık zaten var — alt boş kalmalı (çift okuma olmasın)
        img = f'<img src="{a["cover"]}" alt=""{dims} loading="lazy">'
    return f"""    <a class="card" href="/blog/{a['slug']}/">
      {img}
      <div class="card-body">
        <h2>{esc(a['title'])}</h2>
        <p>{esc(a['excerpt'])}</p>
        <time datetime="{a['isoDate'][:10]}">{esc(a['date'])}</time>
      </div>
    </a>"""


PER_PAGE = 24  # bu eşiğe kadar tek sayfa; aşılınca /blog/page/2/ ... otomatik açılır


def build_index(articles):
    import shutil
    pages = [articles[i:i + PER_PAGE] for i in range(0, len(articles), PER_PAGE)] or [[]]
    # eski sayfalama dizinlerini temizle (yazı sayısı azalırsa artık sayfa kalmasın)
    pagedir = os.path.join(ROOT, "blog", "page")
    if os.path.isdir(pagedir):
        shutil.rmtree(pagedir)
    for n, chunk in enumerate(pages, 1):
        build_index_page(n, chunk, len(pages))


def build_index_page(n, articles, total):
    cards = "\n".join(card(a) for a in articles)
    canonical = f"{SITE}/blog/" if n == 1 else f"{SITE}/blog/page/{n}/"
    title = ("Blog — NewsLearner | Language Learning with Real News" if n == 1
             else f"Blog — Page {n} — NewsLearner")
    items = ",\n    ".join(
        f'{{"@type":"ListItem","position":{i+1},"url":"{SITE}/blog/{a["slug"]}/"}}'
        for i, a in enumerate(articles)
    )
    ld = f"""<script type="application/ld+json">
{{
  "@context": "https://schema.org",
  "@type": "Blog",
  "name": "NewsLearner Blog",
  "description": "Guides on learning languages by reading real news.",
  "url": "{canonical}",
  "publisher": {{"@type": "Organization", "name": "NewsLearner", "url": "{SITE}/", "logo": "{SITE}/apple-touch-icon.png"}},
  "blogPost": [
    {items}
  ]
}}
</script>"""
    pager = ""
    if total > 1:
        newer = "" if n == 1 else f'<a class="pager-link" href="{"/blog/" if n == 2 else f"/blog/page/{n-1}/"}">&larr; Newer posts</a>'
        older = "" if n == total else f'<a class="pager-link" href="/blog/page/{n+1}/">Older posts &rarr;</a>'
        pager = f"""    <nav class="pager" aria-label="Blog pages">
      {newer}
      <span class="pager-info">Page {n} of {total}</span>
      {older}
    </nav>"""
    redirect = ("""<script>(function(){var p=new URLSearchParams(location.search).get('post');"""
                """if(p&&/^[a-z0-9-]+$/.test(p))location.replace('/blog/'+p+'/');})();</script>"""
                if n == 1 else "")
    page = f"""<!doctype html>
<html lang="en">
<head>
{head(title,
      "Guides and ideas on learning languages by reading real news: methods, CEFR levels, vocabulary science, and language-specific tips from the NewsLearner team.",
      canonical, extra=ld)}
</head>
<body>
{redirect}
{NAV}
<header class="head">
  <div class="wrap">
    <span class="eyebrow">NewsLearner Blog</span>
    <h1>Learning a language, one headline at a time.</h1>
    <p class="lede">Guides and ideas on learning languages through real news — methods that work, CEFR levels explained, and the science of making vocabulary stick.</p>
  </div>
</header>
<main class="blogbox">
  <div class="wrap">
    <div class="cards">
{cards}
    </div>
{pager}
  </div>
</main>
{FOOTER}
</body>
</html>
"""
    out = (os.path.join(ROOT, "blog", "index.html") if n == 1
           else os.path.join(ROOT, "blog", "page", str(n), "index.html"))
    os.makedirs(os.path.dirname(out), exist_ok=True)
    open(out, "w", encoding="utf-8").write(page)


def build_post(a, articles):
    title = f"{a['title']} — NewsLearner Blog"
    canonical = f"{SITE}/blog/{a['slug']}/"
    og_image = f"{SITE}{a['cover']}" if a["cover"] else f"{SITE}/og-image.png"
    mins = reading_minutes(a["content"])
    ld = f"""<script type="application/ld+json">
{{
  "@context": "https://schema.org",
  "@type": "BlogPosting",
  "headline": {json.dumps(a['title'])},
  "description": {json.dumps(a['excerpt'])},
  "image": "{og_image}",
  "datePublished": "{a['isoDate']}",
  "dateModified": "{a['isoDate']}",
  "mainEntityOfPage": "{canonical}",
  "author": {{"@type": "Organization", "name": "NewsLearner", "url": "{SITE}/"}},
  "publisher": {{"@type": "Organization", "name": "NewsLearner", "url": "{SITE}/", "logo": {{"@type": "ImageObject", "url": "{SITE}/apple-touch-icon.png"}}}}
}}
</script>
<script type="application/ld+json">
{{
  "@context": "https://schema.org",
  "@type": "BreadcrumbList",
  "itemListElement": [
    {{"@type": "ListItem", "position": 1, "name": "Home", "item": "{SITE}/"}},
    {{"@type": "ListItem", "position": 2, "name": "Blog", "item": "{SITE}/blog/"}},
    {{"@type": "ListItem", "position": 3, "name": {json.dumps(a['title'])}, "item": "{canonical}"}}
  ]
}}
</script>"""
    others = [o for o in articles if o["slug"] != a["slug"]][:3]
    more = ""
    if others:
        more_cards = "\n".join(card(o) for o in others)
        more = f"""<section class="more">
  <div class="wrap">
    <h2 class="more-title">More from the blog</h2>
    <div class="cards">
{more_cards}
    </div>
  </div>
</section>"""
    cover = ""
    if a["cover"]:
        dims = f' width="{a["cover_w"]}" height="{a["cover_h"]}"' if a.get("cover_w") else ""
        cover = f'<img class="cover" src="{a["cover"]}" alt="{esc(a["title"])}"{dims} fetchpriority="high">'
    meta_extra = (f'<meta property="article:published_time" content="{a["isoDate"]}">\n' + ld)
    page = f"""<!doctype html>
<html lang="en">
<head>
{head(title, a['excerpt'], canonical, og_type="article", og_image=og_image, extra=meta_extra)}
</head>
<body>
{NAV}
<main class="postbox">
  <article class="wrap article">
    <p class="crumbs"><a href="/">Home</a> · <a href="/blog/">Blog</a></p>
    <span class="eyebrow">NewsLearner Blog</span>
    <h1>{esc(a['title'])}</h1>
    <p class="postmeta"><time datetime="{a['isoDate'][:10]}">{esc(a['date'])}</time> · {mins} min read</p>
    {cover}
    <div class="content">
{a['content']}
    </div>
    <aside class="cta">
      <h2>Put it into practice</h2>
      <p>NewsLearner turns today's real headlines into reading practice at your level — tap any word to save it, then review until it sticks. Free on iOS, in seven languages.</p>
      <a class="btn" href="{APP_URL}" target="_blank" rel="noopener">Get NewsLearner for iOS</a>
    </aside>
  </article>
</main>
{more}
{FOOTER}
</body>
</html>
"""
    out = os.path.join(ROOT, "blog", a["slug"], "index.html")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    open(out, "w", encoding="utf-8").write(page)


def build_sitemap(articles, orphans=()):
    newest = articles[0]["isoDate"][:10] if articles else date.today().isoformat()
    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for path, lastmod in STATIC_PAGES:
        lm = lastmod or newest
        lines.append(f"  <url><loc>{SITE}{path}</loc><lastmod>{lm}</lastmod></url>")
    for a in articles:
        lines.append(f"  <url><loc>{SITE}/blog/{a['slug']}/</loc><lastmod>{a['isoDate'][:10]}</lastmod></url>")
    # Soro listesinden düşmüş ama sitede tutulan yazılar da sitemap'te kalsın
    for slug in orphans:
        lines.append(f"  <url><loc>{SITE}/blog/{slug}/</loc></url>")
    lines.append("</urlset>")
    open(os.path.join(ROOT, "sitemap.xml"), "w", encoding="utf-8").write("\n".join(lines) + "\n")


def build_feed(articles):
    """RSS 2.0 beslemesi — okuyucular, dizinler ve AI tarayıcıları için."""
    from datetime import datetime

    def rfc822(iso):
        return datetime.fromisoformat(iso).strftime("%a, %d %b %Y %H:%M:%S %z")

    items = []
    for a in articles[:20]:
        items.append(f"""    <item>
      <title>{esc(a['title'])}</title>
      <link>{SITE}/blog/{a['slug']}/</link>
      <guid isPermaLink="true">{SITE}/blog/{a['slug']}/</guid>
      <pubDate>{rfc822(a['isoDate'])}</pubDate>
      <description>{esc(a['excerpt'])}</description>
    </item>""")
    feed = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>NewsLearner Blog</title>
    <link>{SITE}/blog/</link>
    <atom:link href="{SITE}/blog/feed.xml" rel="self" type="application/rss+xml"/>
    <description>Guides on learning languages by reading real news.</description>
    <language>en</language>
{chr(10).join(items)}
  </channel>
</rss>
"""
    open(os.path.join(ROOT, "blog", "feed.xml"), "w", encoding="utf-8").write(feed)


def report_orphans(articles):
    """Soro listesinde artık olmayan yazıları BİLDİR — asla silme.

    Otomatik silme bilinçli olarak kapalı: yayınlanmış her yazı kalıcı bir
    varlıktır. Bir yazıyı gerçekten kaldırmak isterseniz blog/<yazı>/ dizinini
    elle silin; sitemap bir sonraki senkronda kendiliğinden güncellenir.
    """
    keep = {a["slug"] for a in articles} | {"page"}
    blogdir = os.path.join(ROOT, "blog")
    orphans = [n for n in os.listdir(blogdir)
               if os.path.isdir(os.path.join(blogdir, n)) and n not in keep]
    for name in orphans:
        print(f"  NOT: blog/{name}/ Soro listesinde yok — sitede tutuluyor"
              f" (otomatik silme kapalı)")
    return orphans


def existing_post_count():
    blogdir = os.path.join(ROOT, "blog")
    return sum(1 for n in os.listdir(blogdir)
               if os.path.isdir(os.path.join(blogdir, n)) and n != "page")


def main():
    articles = get_articles()
    # Sigorta: API boş/eksik liste döndürürse mevcut siteyi boşaltma
    if not articles and existing_post_count() > 0:
        raise SystemExit("API boş liste döndürdü ama sitede yazılar var — "
                         "muhtemel API arızası, build durduruldu.")
    print(f"{len(articles)} yazı bulundu")
    download_covers(articles)
    orphans = report_orphans(articles)
    build_index(articles)
    for a in articles:
        build_post(a, articles)
        print(f"  blog/{a['slug']}/")
    build_sitemap(articles, orphans)
    build_feed(articles)
    print("sitemap.xml + feed.xml güncellendi")


if __name__ == "__main__":
    sys.exit(main())
