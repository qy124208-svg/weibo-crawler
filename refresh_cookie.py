"""独立Playwright cookie刷新 — subprocess调用，不和GUI冲突
自动检测：优先使用系统Chrome，没有则用Playwright自带Chromium"""
import time, os, sys, platform
from playwright.sync_api import sync_playwright

profile = os.path.join(os.path.dirname(__file__), 'chrome_weibo_profile')
keys = ['SUB', 'SUBP', 'SCF', 'XSRF-TOKEN', 'SSOLoginState', 'ALF', 'MLOGIN', '_T_WM', 'WBPSESS']


def _find_system_chrome():
    """检测系统是否安装了Chrome"""
    paths = []
    if platform.system() == 'Windows':
        paths = [
            os.path.join(os.environ.get('ProgramFiles', 'C:\\Program Files'),
                        'Google\\Chrome\\Application\\chrome.exe'),
            os.path.join(os.environ.get('ProgramFiles(x86)', 'C:\\Program Files (x86)'),
                        'Google\\Chrome\\Application\\chrome.exe'),
            os.path.join(os.environ.get('LOCALAPPDATA', ''),
                        'Google\\Chrome\\Application\\chrome.exe'),
        ]
    elif platform.system() == 'Darwin':
        paths = ['/Applications/Google Chrome.app/Contents/MacOS/Google Chrome']
    else:
        paths = ['/usr/bin/google-chrome', '/usr/bin/google-chrome-stable']

    for p in paths:
        if os.path.exists(p):
            return p
    return None


with sync_playwright() as p:
    use_channel = _find_system_chrome() is not None
    launch_args = {
        'user_data_dir': profile,
        'headless': False,
        'args': ['--window-position=-2000,-2000'],
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    }
    if use_channel:
        launch_args['channel'] = 'chrome'

    ctx = p.chromium.launch_persistent_context(**launch_args)
    page = ctx.new_page()
    # 先上weibo.com，再跳m.weibo.cn（模拟真实浏览）
    page.goto('https://weibo.com', timeout=30000, wait_until='domcontentloaded')
    time.sleep(2)
    page.goto('https://m.weibo.cn', timeout=30000, wait_until='domcontentloaded')
    time.sleep(3)
    # 刷新几次
    for _ in range(2):
        try: page.goto('https://m.weibo.cn/api/container/getIndex?type=uid&value=0', timeout=15000)
        except: pass
        time.sleep(2)

    pc = [f'{c["name"]}={c["value"]}' for c in ctx.cookies('https://weibo.com') if c['name'] in keys and c['value']]
    with open(os.path.join(os.path.dirname(__file__), 'cookie.txt'), 'w', encoding='utf-8') as f:
        f.write('; '.join(pc))

    mb = [f'{c["name"]}={c["value"]}' for c in ctx.cookies('https://m.weibo.cn') if c['name'] in keys and c['value']]
    with open(os.path.join(os.path.dirname(__file__), 'cookie_mobile.txt'), 'w', encoding='utf-8') as f:
        f.write('; '.join(mb))

    ctx.close()
    print(f'OK pc={len(pc)} mobile={len(mb)}')
