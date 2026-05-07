#!/usr/bin/env python3
"""
microCMS ブログ記事 半自動生成ツール

使い方:
  python blog_generator.py                          # 新規生成 → 確認 → push
  python blog_generator.py drafts/20260507-xxx.json # 既存下書きをpushする
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

# ── 依存パッケージチェック ─────────────────────────────────────
for _pkg, _install in [("anthropic", "anthropic"), ("requests", "requests")]:
    try:
        __import__(_pkg)
    except ImportError:
        print(f"\n[ERROR] '{_pkg}' が未インストールです")
        print(f"  pip install {_install}\n")
        sys.exit(1)

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv なしでも環境変数から読める

import anthropic
import requests

# ── 設定 ──────────────────────────────────────────────────────
ANTHROPIC_KEY      = os.getenv("ANTHROPIC_API_KEY", "")
MICROCMS_SERVICE   = os.getenv("MICROCMS_SERVICE_DOMAIN", "9d1xfgkz89")
MICROCMS_WRITE_KEY = os.getenv("MICROCMS_WRITE_API_KEY", "")
MICROCMS_ENDPOINT  = os.getenv("MICROCMS_ENDPOINT", "blogs")
CLAUDE_MODEL       = os.getenv("CLAUDE_MODEL", "claude-opus-4-7")

MICROCMS_URL = f"https://{MICROCMS_SERVICE}.microcms.io/api/v1/{MICROCMS_ENDPOINT}"
DRAFTS_DIR   = Path(__file__).parent / "drafts"
DRAFTS_DIR.mkdir(exist_ok=True)

SEP = "─" * 60

# ── AI生成プロンプト ───────────────────────────────────────────
SYSTEM_PROMPT = (
    "あなたはSEO・AI集客専門の日本語Webライターです。"
    "HP制作会社「AI集客ドットコム」(https://hp.ai-marketing-japan.jp) のブログ向けに"
    "SEO/AIO/LLMO/AEO対応の記事を生成します。"
    "読者はSEO・MEO・AI集客を活用したい中小企業オーナーや担当者です。"
)

def build_prompt(theme: str) -> str:
    return f"""以下のテーマでブログ記事を生成してください。

テーマ: {theme}

【出力指示】
JSON **のみ** を返してください。前置き・説明・コードブロック記号(```)は不要です。

{{
  "title":           "記事タイトル（読者がクリックしたくなる表現）",
  "seoTitle":        "SEOタイトル（32〜45文字・重要KWを前半に配置）",
  "metaDescription": "メタディスクリプション（120〜160文字・結論ファースト・行動喚起含む）",
  "ogpDescription":  "OGP説明文（50〜100文字・SNSシェア向けに短く自然に）",
  "slug":            "english-url-slug-3-to-5-words",
  "keywords":        "KW1, KW2, KW3, KW4, KW5",
  "content":         "<p>本文HTML全文</p>"
}}

【本文（content）ルール】
・冒頭<p>に記事の結論・要点（結論ファースト）
・<h2>見出し: 3〜5個（主要KWを含める）
・各<h2>の下に<h3>: 1〜2個
・<h2>よくある質問</h2> セクション: 3〜5問（<h3>質問 → <p>回答）
・<ul><li> / <ol><li> を積極活用
・本文は2500〜4000文字相当（HTMLタグ込み）
・末尾に <h2>この記事のまとめ</h2> セクションを追加
・SEO / AIO / LLMO / AEO（AIエンジン最適化）を意識した自然な文体
・不自然なKW詰め込み禁止 / スパム的表現・誇大広告禁止
・slugは英語小文字・ハイフン区切り・3〜5単語（公開後変更しない前提）"""


# ── コンテンツ生成 ─────────────────────────────────────────────
def generate(theme: str) -> dict:
    if not ANTHROPIC_KEY:
        print("[ERROR] ANTHROPIC_API_KEY が未設定です。.env を確認してください。")
        sys.exit(1)

    print(f"\n  Claude ({CLAUDE_MODEL}) で記事を生成中… (30秒〜1分かかります)")

    client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
    msg = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=8192,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": build_prompt(theme)}],
    )

    raw = msg.content[0].text.strip()

    # ```json ... ``` で包まれていた場合の対応
    m = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", raw)
    if m:
        raw = m.group(1).strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"\n[ERROR] JSON解析に失敗しました: {e}")
        print("── AI出力（先頭500文字）──")
        print(raw[:500])
        sys.exit(1)


# ── プレビュー表示 ─────────────────────────────────────────────
def show_preview(data: dict, images: dict | None = None) -> None:
    content_text = re.sub(r"<[^>]+>", "", data.get("content", "")).replace("\n", " ").strip()
    preview_text = content_text[:250] + ("…" if len(content_text) > 250 else "")

    seo_len  = len(data.get("seoTitle", ""))
    meta_len = len(data.get("metaDescription", ""))
    ogp_len  = len(data.get("ogpDescription", ""))

    def warn(ok: bool, msg: str) -> str:
        return "" if ok else f"  ⚠ {msg}"

    print(f"\n{SEP}")
    print("【 生成結果プレビュー 】")
    print(SEP)
    print(f"📝 記事タイトル:\n   {data.get('title', '')}\n")
    print(f"🏷  SEOタイトル ({seo_len}文字){warn(32 <= seo_len <= 45, '推奨は32〜45文字')}:")
    print(f"   {data.get('seoTitle', '')}\n")
    print(f"📋 メタディスクリプション ({meta_len}文字){warn(120 <= meta_len <= 160, '推奨は120〜160文字')}:")
    print(f"   {data.get('metaDescription', '')}\n")
    print(f"📣 OGP説明文 ({ogp_len}文字):")
    print(f"   {data.get('ogpDescription', '')}\n")
    print(f"🔗 スラッグ:    {data.get('slug', '')}")
    print(f"🔑 キーワード:  {data.get('keywords', '')}\n")
    if images:
        print(f"🖼  アイキャッチ: {images.get('eyecatch') or '(未設定)'}")
        print(f"🖼  OGP画像:     {images.get('ogpImage') or '(未設定)'}\n")
    print(f"📄 本文プレビュー（冒頭250文字）:")
    print(f"   {preview_text}")
    print(SEP)


# ── microCMS ペイロード組み立て ────────────────────────────────
def build_payload(data: dict, images: dict) -> dict:
    seotitle: dict = {
        "fieldId": "SEO",
        "seoTitle":        data.get("seoTitle", ""),
        "metaDescription": data.get("metaDescription", ""),
        "slug":            data.get("slug", ""),
        "ogpDescription":  data.get("ogpDescription", ""),
        "keywords":        data.get("keywords", ""),
    }
    if images.get("ogpImage"):
        seotitle["ogpImage"] = {"url": images["ogpImage"]}

    payload: dict = {
        "title":    data["title"],
        "content":  data["content"],
        "seotitle": seotitle,
    }
    if images.get("eyecatch"):
        payload["eyecatch"] = {"url": images["eyecatch"]}

    return payload


# ── microCMS 下書き保存 ────────────────────────────────────────
def push_draft(payload: dict) -> None:
    if not MICROCMS_WRITE_KEY:
        print("\n[ERROR] MICROCMS_WRITE_API_KEY が未設定です。")
        print("  microCMS管理画面 → APIキー → 書き込み権限のあるキーを作成して .env に設定してください。")
        sys.exit(1)

    print("\n  microCMS に下書き保存中…")

    try:
        res = requests.post(
            MICROCMS_URL,
            json=payload,
            headers={
                "X-MICROCMS-API-KEY": MICROCMS_WRITE_KEY,
                "Content-Type": "application/json",
            },
            timeout=20,
        )
        res.raise_for_status()
        content_id = res.json().get("id", "(不明)")
        print(f"\n✅ 下書き保存完了！")
        print(f"   コンテンツID: {content_id}")
        print(f"   管理画面で確認・編集後に公開してください。")
        print(f"   → https://{MICROCMS_SERVICE}.microcms.io/")
    except requests.HTTPError as e:
        status = e.response.status_code
        body   = e.response.text[:400]
        print(f"\n[ERROR] microCMS API エラー (HTTP {status})")
        if status == 401:
            print("  APIキーの権限を確認してください（POST権限が必要です）。")
        print(f"  レスポンス: {body}")
        sys.exit(1)
    except requests.RequestException as e:
        print(f"\n[ERROR] 通信エラー: {e}")
        sys.exit(1)


# ── メイン ────────────────────────────────────────────────────
def main() -> None:
    parser = argparse.ArgumentParser(
        description="microCMS ブログ記事 半自動生成ツール",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "例:\n"
            "  python blog_generator.py\n"
            "  python blog_generator.py drafts/20260507-seo-basics.json"
        ),
    )
    parser.add_argument(
        "draft_file", nargs="?",
        help="既存の下書きJSONファイルをpushする場合に指定"
    )
    args = parser.parse_args()

    print("\n" + "=" * 60)
    print("  microCMS ブログ記事 半自動生成ツール")
    print("=" * 60)

    # ── モード分岐 ──────────────────────────────────────────────
    if args.draft_file:
        # 既存下書きpushモード
        path = Path(args.draft_file)
        if not path.exists():
            print(f"\n[ERROR] ファイルが見つかりません: {path}")
            sys.exit(1)
        with open(path, encoding="utf-8") as f:
            draft = json.load(f)
        data   = draft["generated"]
        images = draft.get("images", {})
        print(f"\n💾 下書きファイル: {path}")
        print(f"   テーマ: {draft.get('theme', '(不明)')}")
        show_preview(data, images)

    else:
        # 新規生成モード
        theme = input("\nテーマを入力してください: ").strip()
        if not theme:
            print("[ERROR] テーマが入力されていません")
            sys.exit(1)

        data = generate(theme)
        show_preview(data)

        # 画像URL入力
        print("\n【 画像設定（任意） 】")
        print("microCMSメディアライブラリにアップロード済みの画像URLを入力。")
        print("スキップする場合はそのままEnterを押してください。")
        eyecatch_url  = input("\nアイキャッチ画像URL: ").strip()
        ogp_image_url = input("OGP画像URL:         ").strip()
        images = {"eyecatch": eyecatch_url, "ogpImage": ogp_image_url}

        # 下書きJSONを保存
        slug       = re.sub(r"[^a-z0-9\-]", "", data.get("slug", "draft").lower())
        timestamp  = datetime.now().strftime("%Y%m%d-%H%M%S")
        draft_path = DRAFTS_DIR / f"{timestamp}-{slug}.json"
        with open(draft_path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "theme":     theme,
                    "generated": data,
                    "images":    images,
                    "createdAt": datetime.now().isoformat(),
                },
                f, ensure_ascii=False, indent=2,
            )
        print(f"\n💾 下書き保存: {draft_path}")
        print("   JSONを直接編集して内容を調整することもできます。")
        print(f"   再pushコマンド: python blog_generator.py {draft_path}")

    # ── Push確認 ────────────────────────────────────────────────
    payload = build_payload(data, images)

    print(f"\n{SEP}")
    print("microCMS に下書き保存しますか？（公開はされません）")
    print("  「push」と入力 → 保存実行")
    print("  それ以外       → 中止")
    print(SEP)

    answer = input("\n> ").strip().lower()
    if answer == "push":
        push_draft(payload)
    else:
        print("\n⏸  中止しました。")
        if not args.draft_file:
            print(f"   下書きJSONは保存済みです: {draft_path}")
            print(f"   後でpushするには: python blog_generator.py {draft_path}")


if __name__ == "__main__":
    main()
