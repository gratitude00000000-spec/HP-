// Netlify Edge Function: /blog/:slug のリクエストをインターセプトし
// microCMS から記事を取得してSEOメタタグをHTMLソースに直接書き込む

const MICROCMS_SERVICE = '9d1xfgkz89';
const MICROCMS_KEY     = 'YRr0JUxPTTGZp9VI6weBvUAeIZqqvbLIRf1m';
const BLOG_ENDPOINT    = 'blogs';
const BASE_URL         = 'https://hp.ai-marketing-japan.jp';

// カテゴリID → カテゴリページURL用スラッグ（article.html と同期）
const CATEGORY_SLUGS = {
  '9u_-4ryk-k9':  'ai-marketing',
  '82v_qeo_bf':   'website',
  'wbmzxggcg4o9': 'meo',
  'ggfrebaqv':    'marketing',
};

function esc(s) {
  return (s || '').replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function stripHtml(s) {
  return (s || '').replace(/<[^>]+>/g, '').replace(/\s+/g, ' ').trim();
}

// 10文字以上かつ日本語を含む場合のみ有効な説明文とみなす
function isValidDesc(s) {
  if (!s) return false;
  const t = s.trim();
  return t.length >= 10 && /[぀-鿿]/.test(t);
}

async function fetchArticle(slug) {
  const headers = { 'X-MICROCMS-API-KEY': MICROCMS_KEY };
  const base = `https://${MICROCMS_SERVICE}.microcms.io/api/v1/${BLOG_ENDPOINT}`;

  // 1. content IDで直接取得
  const r1 = await fetch(`${base}/${encodeURIComponent(slug)}`, { headers });
  if (r1.ok) return r1.json();
  if (r1.status !== 404) return null;

  // 2. seotitle.slug → content ID をリスト取得で解決
  const r2 = await fetch(`${base}?limit=100&fields=id,seotitle`, { headers });
  if (!r2.ok) return null;
  const data = await r2.json();
  const found = data.contents.find(a => a.seotitle && a.seotitle.slug === slug);
  if (!found) return null;

  // 3. 解決したIDで記事本体を取得
  const r3 = await fetch(`${base}/${found.id}`, { headers });
  return r3.ok ? r3.json() : null;
}

export default async function handler(request, context) {
  const url  = new URL(request.url);
  const parts = url.pathname.split('/').filter(Boolean);
  const slug  = parts[1];

  // 静的ファイル（.html 等）はスキップ
  if (!slug || slug.includes('.')) return context.next();

  let article = null;
  try {
    article = await fetchArticle(slug);
  } catch (_) {
    // microCMS が応答しない場合はフォールバック（JS側で処理）
    return context.next();
  }

  // 記事が見つからない場合もフォールバック（JS側で404表示）
  if (!article) return context.next();

  // article.html を取得
  const response = await context.next();
  if (!response.ok) return response;

  const html = await response.text();

  // ── SEO値の計算 ──
  const seo         = article.seotitle || {};
  const articleSlug = seo.slug || article.id;
  const canonical   = `${BASE_URL}/blog/${articleSlug}`;

  const pageTitle = seo.seoTitle
    ? `${seo.seoTitle}｜AI集客ドットコム ブログ`
    : `${article.title}｜AI集客ドットコム ブログ`;

  const metaDesc = seo.metaDescription
    || article.description || article.excerpt || article.summary
    || (article.content ? stripHtml(article.content).slice(0, 120) + '…' : '');

  const ogDesc = (isValidDesc(seo.ogpDescription) ? seo.ogpDescription : null)
    || seo.metaDescription
    || metaDesc;

  const ogImg = (seo.ogpImage && seo.ogpImage.url)
    ? seo.ogpImage.url
    : (article.eyecatch ? article.eyecatch.url : `${BASE_URL}/ogp_hp_.jpg`);

  const ogTitle = seo.seoTitle || article.title;

  // ── HTMLのheadタグを書き換え ──
  let modified = html
    // title
    .replace(/<title>[^<]*<\/title>/, `<title>${esc(pageTitle)}</title>`)
    // meta description
    .replace(
      /<meta name="description"[^>]*\/>/,
      `<meta name="description" content="${esc(metaDesc)}" />`
    )
    // canonical
    .replace(
      /<link rel="canonical"[^>]*>/,
      `<link rel="canonical" id="canonicalTag" href="${esc(canonical)}" />`
    )
    // og:title
    .replace(/(<meta id="ogTitle"[^>]*content=")[^"]*(")/,    `$1${esc(ogTitle)}$2`)
    // og:description
    .replace(/(<meta id="ogDesc"[^>]*content=")[^"]*(")/,     `$1${esc(ogDesc)}$2`)
    // og:url
    .replace(/(<meta id="ogUrl"[^>]*content=")[^"]*(")/,      `$1${esc(canonical)}$2`)
    // og:image
    .replace(/(<meta id="ogImage"[^>]*content=")[^"]*(")/,    `$1${esc(ogImg)}$2`)
    // twitter:title
    .replace(/(<meta id="twitterTitle"[^>]*content=")[^"]*(")/,  `$1${esc(ogTitle)}$2`)
    // twitter:description
    .replace(/(<meta id="twitterDesc"[^>]*content=")[^"]*(")/,   `$1${esc(ogDesc)}$2`)
    // twitter:image
    .replace(/(<meta id="twitterImage"[^>]*content=")[^"]*(")/,  `$1${esc(ogImg)}$2`);

  // keywords（入力がある場合のみ追加）
  if (seo.keywords) {
    modified = modified.replace(
      '</head>',
      `  <meta name="keywords" content="${esc(seo.keywords)}" />\n</head>`
    );
  }

  // ── BreadcrumbList JSON-LD ──
  const catObj  = (article.category && typeof article.category === 'object') ? article.category : null;
  const catName = catObj ? (catObj.name || '') : '';
  const catId   = catObj ? (catObj.id   || '') : '';
  const catSlug = CATEGORY_SLUGS[catId] || '';

  const bcItems = (catName && catSlug) ? [
    { position: 1, name: 'HOME',    item: `${BASE_URL}/` },
    { position: 2, name: catName,   item: `${BASE_URL}/category/${catSlug}` },
    { position: 3, name: article.title, item: canonical },
  ] : [
    { position: 1, name: 'HOME',    item: `${BASE_URL}/` },
    { position: 2, name: 'ブログ',   item: `${BASE_URL}/blog` },
    { position: 3, name: article.title, item: canonical },
  ];

  const breadcrumbLd = JSON.stringify({
    '@context': 'https://schema.org',
    '@type': 'BreadcrumbList',
    itemListElement: bcItems.map(it => ({ '@type': 'ListItem', ...it })),
  });

  modified = modified.replace(
    '</head>',
    `  <script type="application/ld+json">${breadcrumbLd}</script>\n</head>`
  );

  return new Response(modified, {
    status: 200,
    headers: { 'content-type': 'text/html; charset=UTF-8' },
  });
}

export const config = { path: '/blog/:slug' };
