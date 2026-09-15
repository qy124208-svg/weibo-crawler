"""
2015微博批量采集 — 使用Playwright在真实浏览器中调API
参照 JMeowKit/八爪鱼 架构：CDP控制浏览器 → cookie/TLS全部原生
用法: python collect_2015_browser.py --city 南京 --batch-size 200
"""

import asyncio, json, os, sys, csv, re, time, random, argparse, platform
from datetime import datetime


def _find_system_chrome():
    """检测系统Chrome，没有则用Playwright自带Chromium"""
    paths = []
    if platform.system() == 'Windows':
        paths = [
            os.path.join(os.environ.get('ProgramFiles', 'C:\\Program Files'),
                        'Google\\Chrome\\Application\\chrome.exe'),
            os.path.join(os.environ.get('ProgramFiles(x86)', 'C:\\Program Files (x86)'),
                        'Google\\Chrome\\Application\\chrome.exe'),
        ]
    elif platform.system() == 'Darwin':
        paths = ['/Applications/Google Chrome.app/Contents/MacOS/Google Chrome']
    else:
        paths = ['/usr/bin/google-chrome']
    for p in paths:
        if os.path.exists(p): return True
    return False


def parse_time(s):
    if not s: return None
    try: return datetime.strptime(s.strip(), '%a %b %d %H:%M:%S %z %Y').replace(tzinfo=None)
    except:
        try: return datetime.strptime(s.strip(), '%Y-%m-%d %H:%M:%S')
        except: return None


async def collect_batch(city, uids, output_dir):
    """用Playwright在真实浏览器中批量采集2015微博"""
    profile_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'chrome_weibo_profile')
    posts_file = os.path.join(output_dir, f'{city}_2015微博.csv')
    state_file = os.path.join(output_dir, 'state.json')

    # 读取已采集列表
    collected = set()
    existing_ids = set()
    if os.path.exists(state_file):
        with open(state_file, encoding='utf-8') as f:
            state = json.load(f)
            collected = set(state.get('collected', {}).get(city, []))
    if os.path.exists(posts_file):
        with open(posts_file, encoding='utf-8-sig') as f:
            for row in csv.DictReader(f):
                pid = row.get('微博id', '')
                if pid: existing_ids.add(pid)

    # 手机UA池
    ua_pool = [
        'Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1',
        'Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1',
        'Mozilla/5.0 (Linux; Android 14; Pixel 8 Pro) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.6261.119 Mobile Safari/537.36',
        'Mozilla/5.0 (Linux; Android 13; SM-S9080) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.6099.144 Mobile Safari/537.36',
    ]

    total_posts = 0
    processed = 0

    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        # 持久化浏览器上下文——复用chrome_weibo_profile的登录态
        ctx = await p.chromium.launch_persistent_context(
            user_data_dir=profile_dir,
            headless=True,
            **({'channel': 'chrome'} if _find_system_chrome() else {}),
            viewport={'width': 390, 'height': 844},
            user_agent=random.choice(ua_pool),
            locale='zh-CN',
            timezone_id='Asia/Shanghai',
        )

        page = await ctx.new_page()

        # 预热：先打开m.weibo.cn首页
        try:
            await page.goto('https://m.weibo.cn/', wait_until='domcontentloaded', timeout=30000)
            await asyncio.sleep(2)
        except:
            pass

        for i, uid in enumerate(uids):
            if uid in collected:
                continue

            try:
                # 先打开用户主页（模拟真人行为）
                try:
                    await page.goto(f'https://m.weibo.cn/profile/{uid}',
                                   wait_until='domcontentloaded', timeout=15000)
                    await asyncio.sleep(1 + random.uniform(0, 1.5))
                except:
                    pass

                user_posts = []
                user_name = ''

                for pg in range(1, 500):
                    try:
                        # 在浏览器内通过fetch调用API——cookie/TLS/headers全部原生
                        result = await page.evaluate('''
                            async ([uid, pageNum]) => {
                                const resp = await fetch(
                                    `https://m.weibo.cn/api/container/getIndex?type=uid&value=${uid}&containerid=107603${uid}&page=${pageNum}`,
                                    { credentials: 'include' }
                                );
                                return await resp.json();
                            }
                        ''', [uid, pg])

                        ok_val = result.get('ok')
                        if ok_val != 1:
                            if ok_val == -100:
                                print(f'  [!] uid={uid} cookie过期(ok=-100)，需重新登录')
                            break

                        cards = result.get('data', {}).get('cards', [])
                        if not cards:
                            collected.add(uid)
                            break

                        # 第一页获取用户名
                        if pg == 1 and cards:
                            user_name = cards[0].get('mblog', {}).get('user', {}).get('screen_name', '')

                        pre_2015 = False
                        for card in cards:
                            mblog = card.get('mblog')
                            if not mblog: continue
                            dt = parse_time(mblog.get('created_at', ''))
                            if dt is None: continue
                            if dt.year < 2015:
                                pre_2015 = True
                                break
                            if dt.year != 2015: continue

                            txt = mblog.get('text_raw', '') or re.sub(r'<[^>]+>', '', mblog.get('text', ''))
                            if mblog.get('retweeted_status'):
                                rt = mblog['retweeted_status']
                                rt_user = rt.get('user', {}).get('screen_name', '')
                                rt_txt = rt.get('text_raw', '') or re.sub(r'<[^>]+>', '', rt.get('text', ''))
                                user_comment = txt.strip()
                                if user_comment in ('转发微博', ''):
                                    txt = '//@%s: %s' % (rt_user, rt_txt.strip())
                                else:
                                    txt = '%s //@%s: %s' % (user_comment, rt_user, rt_txt.strip())

                            pid = str(mblog.get('id', ''))
                            if pid in existing_ids:
                                continue
                            existing_ids.add(pid)

                            user_posts.append({
                                'uid': str(uid), '用户昵称': user_name,
                                '微博id': pid,
                                '微博链接': f'https://weibo.com/{uid}/{pid}',
                                '发布时间': dt.strftime('%Y-%m-%d %H:%M:%S'),
                                '微博内容': txt.strip(),
                                '转发数': mblog.get('reposts_count', 0),
                                '评论数': mblog.get('comments_count', 0),
                                '点赞数': mblog.get('attitudes_count', 0),
                                '发布于': mblog.get('source', ''),
                                '话题标签': ';'.join(re.findall(r'#([^#]+)#', txt)),
                            })

                        if pre_2015:
                            collected.add(uid)
                            break

                        await asyncio.sleep(1.5 + random.uniform(0.3, 1.0))
                    except Exception as e:
                        print(f'  [E] uid={uid} pg={pg}: {str(e)[:60]}')
                        break

                # 有帖子或API成功访问 → 标记已采集
                if user_posts or pg > 1:
                    collected.add(uid)

                # 实时写入CSV
                if user_posts:
                    fields = ['uid', '用户昵称', '微博id', '微博链接', '发布时间',
                              '微博内容', '转发数', '评论数', '点赞数', '发布于', '话题标签']
                    file_exists = os.path.exists(posts_file) and os.path.getsize(posts_file) > 0
                    with open(posts_file, 'a+', newline='', encoding='utf-8-sig') as f:
                        w = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
                        if not file_exists: w.writeheader()
                        w.writerows(user_posts)
                    total_posts += len(user_posts)

                processed += 1
                print(f'[{processed}/{len(uids)}] {user_name or uid} -> {len(user_posts)}帖 (累计{total_posts})')

                # 每20个用户保存state
                if processed % 20 == 0:
                    if os.path.exists(state_file):
                        with open(state_file, encoding='utf-8') as f:
                            state = json.load(f)
                    else:
                        state = {'collected': {}}
                    state['collected'][city] = list(collected)
                    with open(state_file, 'w', encoding='utf-8') as f:
                        json.dump(state, f, ensure_ascii=False)

                # 每100个用户休息10-20秒
                if processed % 100 == 0:
                    rest = 10 + random.uniform(0, 10)
                    print(f'[休息] 已处理{processed}个，暂停{rest:.0f}秒...')
                    await asyncio.sleep(rest)

            except Exception as e:
                print(f'[E] uid={uid}: {str(e)[:80]}')
                continue

        await ctx.close()

    # 最终保存
    if os.path.exists(state_file):
        with open(state_file, encoding='utf-8') as f:
            state = json.load(f)
    else:
        state = {'collected': {}}
    state['collected'][city] = list(collected)
    with open(state_file, 'w', encoding='utf-8') as f:
        json.dump(state, f, ensure_ascii=False)

    print(f'\n=== {city} 完成: {total_posts}条微博 ===')
    return total_posts


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--city', required=True)
    parser.add_argument('--uids', required=True, help='逗号分隔的UID列表')
    parser.add_argument('--output', default='city_output')
    args = parser.parse_args()

    uids = [u.strip() for u in args.uids.split(',') if u.strip()]
    asyncio.run(collect_batch(args.city, uids, args.output))
