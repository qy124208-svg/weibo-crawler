# -*- coding: utf-8 -*-
"""对比 type=1(综合) vs type=61(微博) 的有效帖子返回量"""
import requests, time
from weibo_city_crawl import _browser_headers, load_cookie

cookie = load_cookie(mobile=True)

def search(containerid, pages=5):
    total_posts = 0
    total_cards = 0
    for page in range(1, pages + 1):
        h = _browser_headers(mobile=True, cookie=cookie)
        h['Cookie'] = cookie
        h['X-Requested-With'] = 'XMLHttpRequest'
        r = requests.get('https://m.weibo.cn/api/container/getIndex',
                         headers=h,
                         params={'containerid': containerid, 'page_type': 'searchall', 'page': page},
                         timeout=10)
        try:
            d = r.json()
        except Exception as e:
            print(f'  page {page}: 解析失败 {e}')
            break
        cards = d.get('data', {}).get('cards', [])
        posts = [c for c in cards if c.get('card_type') == 9]
        total_posts += len(posts)
        total_cards += len(cards)
        print(f'  page {page}: 总卡={len(cards)} 帖子卡={len(posts)}')
        if not cards:
            break
        time.sleep(1)
    return total_posts, total_cards

for kw in ['穷游', '大学生穷游']:
    print(f'\n===== 关键词 [{kw}] type=1 综合 =====')
    p1, c1 = search('100103type=1&q=%s' % kw)
    print(f'  >> 合计: 帖子={p1} 总卡={c1}')
    print(f'===== 关键词 [{kw}] type=61 微博 =====')
    p61, c61 = search('100103type=61&q=%s' % kw)
    print(f'  >> 合计: 帖子={p61} 总卡={c61}')
    time.sleep(2)
