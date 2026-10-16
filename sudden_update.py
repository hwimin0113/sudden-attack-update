import os
import re
import json
import time
import requests
from bs4 import BeautifulSoup

BASE = "https://sa.nexon.com"
LIST_URL = BASE + "/news/update/list.aspx"
WEBHOOK = os.environ["DISCORD_WEBHOOK_URL"]
STATE_FILE = "last_update.json"

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0 Safari/537.36",
    "Accept-Language": "ko-KR,ko;q=0.9"
})


def fetch(url):
    for attempt in range(3):
        try:
            response = session.get(url, timeout=25)
            response.raise_for_status()
            response.encoding = response.apparent_encoding
            return response.text
        except requests.RequestException as exc:
            print(f"접속 실패 {attempt + 1}/3: {exc}")
            if attempt < 2:
                time.sleep(5 * (attempt + 1))
    raise RuntimeError("홈페이지 접근 실패")


def get_latest():
    soup = BeautifulSoup(fetch(LIST_URL), "html.parser")

    candidates = []
    for a in soup.select('a[href*="view.aspx"]'):
        href = a.get("href", "")
        match = re.search(r"n4ArticleSN=(\d+)", href, re.I)
        title = a.get_text(" ", strip=True)

        if match and title:
            candidates.append((int(match.group(1)), title))

    if not candidates:
        raise RuntimeError("업데이트 목록 파싱 실패")

    article_id, title = max(candidates, key=lambda x: x[0])
    return article_id, title


def get_summary(article_id):
    url = (
        BASE + "/news/update/view.aspx"
        f"?n4ArticleSN={article_id}&n4ArticleCategorySN=0"
    )

    soup = BeautifulSoup(fetch(url), "html.parser")

    # 공식 업데이트 항목은 ▣ 기호로 구분됨
    lines = [
        " ".join(line.split())
        for line in soup.get_text("\n").splitlines()
    ]

    items = []
    seen = set()

    for line in lines:
        if not line.startswith("▣"):
            continue

        item = line.lstrip("▣").strip()
        item = re.sub(r"\[더보기\]|\[숨기기\]", "", item).strip()

        if not item or item in seen:
            continue

        seen.add(item)
        items.append(item)

    if not items:
        raise RuntimeError("업데이트 본문 추출 실패")

    # 주요 항목을 최대 10개까지 요약
    summary = "\n".join(
        f"• {item[:160]}" for item in items[:10]
    )

    if len(items) > 10:
        summary += f"\n\n외 {len(items) - 10}개 항목"

    return summary, url


def send_discord(title, summary, url):
    payload = {
        "username": "서든어택 업데이트",
        "allowed_mentions": {"parse": []},
        "embeds": [{
            "title": title[:256],
            "url": url,
            "description": summary[:4000],
            "color": 3447003,
            "footer": {
                "text": "서든어택 공식 업데이트 자동 알림"
            }
        }]
    }

    response = requests.post(
        WEBHOOK + ("&" if "?" in WEBHOOK else "?") + "wait=true",
        json=payload,
        timeout=25
    )
    response.raise_for_status()


def main():
    article_id, title = get_latest()

    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, encoding="utf-8") as f:
            state = json.load(f)
        last_id = int(state["article_id"])
    else:
        # 첫 실행은 기준점만 저장
        # 기존 업데이트를 새 공지로 전송하지 않음
        last_id = article_id

    if article_id > last_id:
        summary, url = get_summary(article_id)
        send_discord(title, summary, url)
        print(f"전송 완료: {title}")
    else:
        print("새 업데이트 없음")

    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(
            {"article_id": article_id},
            f,
            ensure_ascii=False,
            indent=2
        )


if __name__ == "__main__":
    main()
