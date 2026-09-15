"""CDP模式刷新cookie - 连接已运行的Chrome获取未封cookie"""
import os, json, time
os.environ['PW_EXPERIMENTAL_SERVICE_WORKER_NETWORK_EVENTS'] = '1'

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print('请先安装: python -m pip install playwright')
    exit(1)

COOKIE_PC = os.path.join(os.path.dirname(__file__), 'cookie.txt')
COOKIE_MOBILE = os.path.join(os.path.dirname(__file__), 'cookie_mobile.txt')

print('=== CDP Cookie刷新 ===')
print('连接到已运行的Chrome...')

with sync_playwright() as p:
    try:
        browser = p.chromium.connect_over_cdp('http://localhost:9222')
    except:
        print('❌ 无法连接Chrome，请先运行:')
        print('   start chrome --remote-debugging-port=9222')
        exit(1)

    contexts = browser.contexts
    if not contexts:
        print('❌ 无浏览器上下文')
        exit(1)

    ctx = contexts[0]

    # PC端cookie
    pc_cookies = ctx.cookies('https://weibo.com')
    pc_parts = []
    key_fields = ['SUB', 'SUBP', 'SCF', 'XSRF-TOKEN', 'SSOLoginState', 'ALF', 'MLOGIN', '_T_WM', 'WBPSESS']
    for c in pc_cookies:
        if c['name'] in key_fields and c['value']:
            pc_parts.append(f"{c['name']}={c['value']}")
    with open(COOKIE_PC, 'w', encoding='utf-8') as f:
        f.write('; '.join(pc_parts))
    print(f'cookie.txt: {len(pc_parts)}字段')

    # 移动端cookie
    mobile_cookies = ctx.cookies('https://m.weibo.cn')
    mobile_parts = []
    for c in mobile_cookies:
        if c['name'] in key_fields and c['value']:
            mobile_parts.append(f"{c['name']}={c['value']}")
    with open(COOKIE_MOBILE, 'w', encoding='utf-8') as f:
        f.write('; '.join(mobile_parts))
    print(f'cookie_mobile.txt: {len(mobile_parts)}字段')

    browser.close()

print('✅ Cookie刷新完成')
