"""Python自动启动Chrome CDP → 提取cookie
⚠ 仅Windows可用 | 需要: pip install websocket-client"""
import subprocess, time, os, json
import requests

# 1. 杀Chrome
print('[1/5] 关闭现有Chrome...')
subprocess.run('taskkill /F /IM chrome.exe 2>nul', shell=True)
time.sleep(2)

# 2. 启动Chrome debug模式
print('[2/5] 启动Chrome debug模式...')
chrome_paths = [
    r'C:\Program Files\Google\Chrome\Application\chrome.exe',
    r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe',
    os.path.expandvars(r'%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe'),
]
chrome = None
for p in chrome_paths:
    if os.path.exists(p):
        chrome = p
        break

if not chrome:
    print('找不到Chrome，请手动输入路径：')
    chrome = input().strip()

# 用cmd启动确保debug端口生效
cmd = f'start "" "{chrome}" --remote-debugging-port=9222 --no-first-run https://m.weibo.cn'
subprocess.run(cmd, shell=True)
time.sleep(3)

# 3. 等用户登录
print('[3/5] Chrome已打开，请在Chrome中登录 m.weibo.cn')
print('       登录完成后按回车继续...')
input()

# 4. 连接CDP获取cookie（重试最多10次）
print('[4/5] 连接CDP提取cookie...')
ws_url = None
for attempt in range(10):
    time.sleep(2)
    try:
        r = requests.get('http://localhost:9222/json', timeout=5)
        pages = r.json()
        ws_url = pages[0]['webSocketDebuggerUrl']
        break
    except:
        print(f'       等待Chrome启动 ({attempt+1}/10)...')
if not ws_url:
    print('❌ CDP连接失败')
    exit(1)

import websocket
ws = websocket.create_connection(ws_url)
ws.send(json.dumps({'id': 1, 'method': 'Runtime.evaluate',
                     'params': {'expression': 'document.cookie'}}))
resp = ''
while True:
    data = json.loads(ws.recv())
    if 'result' in data and 'result' in data['result']:
        resp = data['result']['result'].get('value', '')
        break
ws.close()

# 5. 保存
print('[5/5] 保存cookie...')
key_fields = ['SUB', 'SUBP', 'SCF', 'XSRF-TOKEN', 'SSOLoginState',
              'ALF', 'MLOGIN', '_T_WM', 'WBPSESS']
cookies = {}
for item in resp.split(';'):
    item = item.strip()
    if '=' in item:
        k, v = item.split('=', 1)
        if k.strip() in key_fields:
            cookies[k.strip()] = v.strip()

base = os.path.dirname(__file__)
parts = [f'{k}={v}' for k, v in cookies.items()]
cookie_str = '; '.join(parts)

with open(os.path.join(base, 'cookie.txt'), 'w', encoding='utf-8') as f:
    f.write(cookie_str)
with open(os.path.join(base, 'cookie_mobile.txt'), 'w', encoding='utf-8') as f:
    f.write(cookie_str)
print(f'✅ {len(cookies)}个cookie已保存')
print(f'   SUB: {cookies.get("SUB","无")[:30]}...')
