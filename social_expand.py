"""
Playwright社交扩散 - 从昵称不含城市的用户中捞出同城用户
独立运行，不依赖主爬虫
"""
import asyncio, csv, os, json, re, time, platform
from playwright.async_api import async_playwright

USER_DATA = os.path.join(os.path.dirname(__file__), 'chrome_weibo_profile')
INPUT_CSV = os.path.join(os.path.dirname(__file__), 'weibo_one_spider-main', 'output')
OUTPUT = os.path.join(os.path.dirname(__file__), 'social_expand_result.csv')


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

PROVINCE_MAP = {'南京': '32', '杭州': '33', '青岛': '37', '郑州': '41'}


async def get_following(page, uid, max_pages=5):
    """用Playwright加载关注页，提取关注用户"""
    all_users = []
    for pg in range(1, max_pages + 1):
        url = f'https://weibo.com/ajax/friendships/friends?uid={uid}&page={pg}'
        try:
            resp = await page.request.get(url, headers={
                'X-Requested-With': 'XMLHttpRequest',
                'Accept': 'application/json',
                'Referer': f'https://weibo.com/u/{uid}',
            })
            if resp.status != 200:
                break
            data = await resp.json()
            users = data.get('users', [])
            if not users:
                break
            all_users.extend(users)
            await asyncio.sleep(0.5)
        except:
            break
    return all_users


async def main():
    # 找最新的用户CSV
    csv_files = []
    for f in os.listdir(INPUT_CSV):
        if f.startswith('城市用户信息') and f.endswith('.csv'):
            csv_files.append(os.path.join(INPUT_CSV, f))
    if not csv_files:
        print('未找到用户CSV')
        return
    latest = max(csv_files, key=os.path.getmtime)
    print(f'输入: {latest}')

    # 读取已确认用户
    with open(latest, 'r', encoding='utf-8-sig') as f:
        users = list(csv.DictReader(f))
    print(f'种子用户: {len(users)}')

    # 检测城市
    city = None
    for u in users:
        loc = u.get('所在地', '')
        for c in PROVINCE_MAP:
            if c in loc:
                city = c
                break
        if city:
            break
    if not city:
        city = '南京'
    prov_code = PROVINCE_MAP.get(city, '32')
    print(f'目标城市: {city} (省份代码: {prov_code})')

    async with async_playwright() as p:
        ctx = await p.chromium.launch_persistent_context(
            user_data_dir=USER_DATA,
            headless=True,
            **({'channel': 'chrome'} if _find_system_chrome() else {}),
            viewport={'width': 1280, 'height': 800},
        )
        page = await ctx.new_page()
        await page.goto('https://weibo.com', wait_until='domcontentloaded')
        await asyncio.sleep(2)

        all_new = {}
        for i, u in enumerate(users[:30]):  # 用前30个种子
            uid = u['uid']
            print(f'[{i+1}/30] {u.get("昵称", uid)}')

            following = await get_following(page, uid, max_pages=5)
            matched = [x for x in following
                       if x.get('province', '') == prov_code
                       and city in x.get('location', '')]

            for x in matched:
                nid = str(x['id'])
                if nid not in all_new:
                    all_new[nid] = {
                        'uid': nid,
                        '昵称': x.get('screen_name', ''),
                        '所在地': x.get('location', ''),
                        '简介': x.get('description', ''),
                    }
            print(f'  {len(following)}关注 → 同城{len(matched)} → 累计新增{len(all_new)}')
            await asyncio.sleep(1)

        await ctx.close()

    if all_new:
        with open(OUTPUT, 'w', newline='', encoding='utf-8-sig') as f:
            w = csv.DictWriter(f, fieldnames=['uid', '昵称', '所在地', '简介'])
            w.writeheader()
            w.writerows(all_new.values())
        print(f'\n✅ 新增{len(all_new)}个{ city}用户 → {OUTPUT}')
    else:
        print('\n❌ 未发现新用户 - API仍然不通')


if __name__ == '__main__':
    asyncio.run(main())
