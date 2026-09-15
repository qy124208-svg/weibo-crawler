"""从已登录的Chrome读取全部weibo cookie"""
import os, json, sqlite3, shutil

# 复制cookie数据库
src = os.path.join(os.environ['LOCALAPPDATA'],
    r'Google\Chrome\User Data\Default\Network\Cookies')
dst = os.path.join(os.environ['TEMP'], 'chrome_cookies.db')
shutil.copy2(src, dst)

db = sqlite3.connect(dst)
key_fields = ['SUB', 'SUBP', 'SCF', 'XSRF-TOKEN', 'SSOLoginState', 'MLOGIN', '_T_WM', 'ALF', 'WBPSESS', 'M_WEIBOCN_PARAMS']

# 读weibo.com和m.weibo.cn的cookie
for domain in ['%weibo.com%', '%weibo.cn%']:
    print(f'=== {domain} ===')
    parts = []
    for name in key_fields:
        for row in db.execute(
            "SELECT name, value FROM cookies WHERE host_key LIKE ? AND name = ? AND value != ''",
            (domain, name)):
            parts.append(f'{row[0]}={row[1]}')
    if parts:
        print('; '.join(parts))
    else:
        print('(无)')
    print()

db.close()
