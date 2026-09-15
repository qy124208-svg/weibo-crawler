"""
Playwright真浏览器登录微博 → 提取cookie → 保存供爬虫使用
自动检测：优先使用系统Chrome（已有profile可复用），没有则用Playwright自带Chromium
"""
import asyncio, os, sys
from playwright.async_api import async_playwright

COOKIE_PC = os.path.join(os.path.dirname(__file__), 'cookie.txt')
COOKIE_MOBILE = os.path.join(os.path.dirname(__file__), 'cookie_mobile.txt')
USER_DATA = os.path.join(os.path.dirname(__file__), 'chrome_weibo_profile')


def _find_system_chrome():
    """检测系统是否安装了Chrome，返回可执行路径或None"""
    import platform
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
    else:  # Linux
        paths = ['/usr/bin/google-chrome', '/usr/bin/google-chrome-stable',
                 '/opt/google/chrome/chrome']

    for p in paths:
        if os.path.exists(p):
            return p
    return None


async def login_and_save():
    print('=== 微博 Playwright 登录 ===')
    print('1. 打开浏览器 → m.weibo.cn')
    print('2. 请扫码登录（如已登录自动跳过）')
    print('3. 登录成功后自动提取cookie保存\n')

    system_chrome = _find_system_chrome()
    if system_chrome:
        print(f'[检测] 系统Chrome: {system_chrome}')
        print(f'[策略] 使用系统Chrome（稳定，可复用已有登录状态）')
        use_channel = True
    else:
        print('[检测] 未找到系统Chrome，使用Playwright自带Chromium')
        print('[提示] 如果扫码页面加载异常，请安装Chrome后重试')
        use_channel = False

    async with async_playwright() as p:
        # 持久化浏览器配置，登录一次后不用重复登
        launch_args = {
            'user_data_dir': USER_DATA,
            'headless': False,
            'viewport': {'width': 1280, 'height': 800},
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            # 绕过 Windows 系统代理（本机代理软件导致 net::ERR_PROXY_CONNECTION_FAILED）
            'args': ['--no-proxy-server'],
        }
        if use_channel:
            launch_args['channel'] = 'chrome'

        ctx = await p.chromium.launch_persistent_context(**launch_args)

        page = await ctx.new_page()

        # Step 1: 打开 weibo.com
        print('[1/4] 打开 weibo.com...（如长时间白屏请等待）')
        try:
            await page.goto('https://weibo.com', wait_until='domcontentloaded', timeout=60000)
        except:
            print('weibo.com加载慢，继续...')
        await asyncio.sleep(2)

        # Step 2: 直接打开移动端扫码登录页（二维码直接显示，无需找登录按钮）
        print('[2/4] 打开微博扫码登录页...')
        await page.goto(
            'https://passport.weibo.cn/signin/login?entry=mweibo&res=wel&wm=3349&r=https%3A%2F%2Fm.weibo.cn%2F',
            wait_until='domcontentloaded', timeout=60000)
        print('       请在页面扫码登录...')

        for _ in range(120):
            cookies = await ctx.cookies('https://m.weibo.cn')
            has_sub = any(c['name'] == 'SUB' and len(c['value']) > 10 for c in cookies)
            has_mlogin = any(c['name'] == 'MLOGIN' and c['value'] == '1' for c in cookies)
            if has_sub and has_mlogin:
                print('       登录成功(MLOGIN=1)！')
                break
            await asyncio.sleep(2)
        else:
            print('       超时，请重试')
            await ctx.close()
            return False

        # Step 3: 顺便刷新m.weibo.cn的cookie
        print('[3/4] 刷新 m.weibo.cn session...')
        try:
            await page.goto('https://m.weibo.cn', wait_until='domcontentloaded', timeout=30000)
            await asyncio.sleep(3)
        except Exception as e:
            print(f'       m.weibo.cn访问失败({e})，跳过')

        # Step 4: 提取并保存cookie
        print('[4/4] 提取cookie...')

        # PC端 cookie (weibo.com)
        pc_cookies = await ctx.cookies('https://weibo.com')
        pc_parts = []
        key_fields = ['SUB', 'SUBP', 'SCF', 'XSRF-TOKEN', 'SSOLoginState',
                       'ALF', 'MLOGIN', '_T_WM', 'WBPSESS']
        for c in pc_cookies:
            if c['name'] in key_fields and c['value']:
                pc_parts.append(f"{c['name']}={c['value']}")
        with open(COOKIE_PC, 'w', encoding='utf-8') as f:
            f.write('; '.join(pc_parts))
        print(f'   cookie.txt: {len(pc_parts)}个字段')

        # 移动端 cookie (m.weibo.cn)
        mobile_cookies = await ctx.cookies('https://m.weibo.cn')
        mobile_parts = []
        for c in mobile_cookies:
            if c['name'] in key_fields and c['value']:
                mobile_parts.append(f"{c['name']}={c['value']}")
        with open(COOKIE_MOBILE, 'w', encoding='utf-8') as f:
            f.write('; '.join(mobile_parts))
        print(f'   cookie_mobile.txt: {len(mobile_parts)}个字段')

        await ctx.close()

    print('\n[OK] Cookie保存完成!')
    print(f'   {COOKIE_PC}')
    print(f'   {COOKIE_MOBILE}')
    return True


def refresh_cookies():
    """同步入口——供爬虫调用刷新cookie"""
    return asyncio.run(login_and_save())


if __name__ == '__main__':
    refresh_cookies()
