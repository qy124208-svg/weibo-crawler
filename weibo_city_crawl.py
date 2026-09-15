"""
微博城市用户采集 — 满足三需求:
(1) 所在地=南京/杭州/青岛/郑州
(2) 2015年微博
(3) 10000用户/城

用法: python weibo_city_crawl.py
"""
import time, random, datetime, os, re, json, csv, threading, concurrent.futures, subprocess, webbrowser, atexit, signal
import requests
from collections import Counter
from bs4 import BeautifulSoup

# ===== 反反爬：UA池 + 真实浏览器请求头 =====
_UA_POOL_MOBILE = [
    'Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1',
    'Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1',
    'Mozilla/5.0 (iPhone; CPU iPhone OS 17_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/120.0.6099.119 Mobile/15E148 Safari/604.1',
    'Mozilla/5.0 (Linux; Android 14; Pixel 8 Pro) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.6261.119 Mobile Safari/537.36',
    'Mozilla/5.0 (Linux; Android 13; SM-S9080) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.6099.144 Mobile Safari/537.36',
    'Mozilla/5.0 (Linux; Android 14; V2334A) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.6167.178 Mobile Safari/537.36',
]
_UA_POOL_PC = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 14.4; rv:124.0) Gecko/20100101 Firefox/124.0',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0',
]

def _random_ua(mobile=False):
    pool = _UA_POOL_MOBILE if mobile else _UA_POOL_PC
    return random.choice(pool)

def _extract_xsrf(cookie_str):
    """从cookie字符串中提取XSRF-TOKEN"""
    if not cookie_str: return ''
    for part in cookie_str.replace('; ', ';').split(';'):
        if '=' in part:
            k, v = part.split('=', 1)
            if k.strip() == 'XSRF-TOKEN':
                return v.strip()
    return ''

def _browser_headers(mobile=False, cookie=''):
    """返回模拟真实浏览器的请求头（含随机UA + XSRF-TOKEN + Origin + Sec-CH-UA）"""
    ua = _random_ua(mobile)
    is_android = 'Android' in ua
    headers = {
        'User-Agent': ua,
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': random.choice(['zh-CN,zh;q=0.9,en;q=0.8', 'zh-CN,zh;q=0.9', 'zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7']),
        'Accept-Encoding': 'gzip, deflate, br',
        'Cache-Control': 'no-cache',
        'Pragma': 'no-cache',
        'DNT': '1',
        'Connection': 'keep-alive',
        'Sec-Fetch-Dest': 'empty',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Site': 'same-origin',
        'Sec-Ch-Ua': '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
        'Sec-Ch-Ua-Mobile': '?1' if is_android else '?0',
        'Sec-Ch-Ua-Platform': '"Android"' if is_android else '"Windows"',
    }
    if mobile:
        headers['Referer'] = 'https://m.weibo.cn/'
        headers['Origin'] = 'https://m.weibo.cn'
    else:
        headers['Referer'] = 'https://weibo.com/'
        headers['Origin'] = 'https://weibo.com'
    # XSRF-TOKEN：微博很多API需要这个头
    xsrf = _extract_xsrf(cookie) if cookie else ''
    if xsrf:
        headers['X-XSRF-TOKEN'] = xsrf
    return headers

def _warm_session(mobile_cookie):
    """预热：先访问一次首页，模拟真人打开浏览器的行为"""
    try:
        h = _browser_headers(mobile=True, cookie=mobile_cookie)
        h['Accept'] = 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
        h['Sec-Fetch-Dest'] = 'document'
        h['Sec-Fetch-Mode'] = 'navigate'
        requests.get('https://m.weibo.cn/', headers=h, timeout=15, allow_redirects=True)
        time.sleep(random.uniform(0.5, 1.5))
    except:
        pass

def _visit_profile(uid, mobile_cookie):
    """采集前先访问用户主页——模拟真人点进用户资料再翻帖子"""
    try:
        h = _browser_headers(mobile=True, cookie=mobile_cookie)
        h['Accept'] = 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
        h['Sec-Fetch-Dest'] = 'document'
        h['Sec-Fetch-Mode'] = 'navigate'
        h['Referer'] = 'https://m.weibo.cn/'
        requests.get(f'https://m.weibo.cn/profile/{uid}', headers=h, timeout=15, allow_redirects=True)
        time.sleep(random.uniform(1.0, 2.5))  # 模拟浏览资料
    except:
        pass

def _human_jitter(base_wait):
    """在基础等待时间上添加人类行为抖动（±50%）"""
    return base_wait * (0.5 + random.random())

def _human_break():
    """偶尔模拟人类长时间停留（10%概率，5-15秒）"""
    if random.random() < 0.1:
        time.sleep(5 + random.uniform(0, 10))

CITIES = ['南京', '杭州', '青岛', '郑州']

KEYWORDS = {
    '南京': ['南京','江苏','鼓楼区','江宁区','秦淮区','建邺区','栖霞区',
           '南京大学','东南大学','南航','南理工','夫子庙','玄武湖','新街口','紫金山'],
    '杭州': ['杭州','浙江','西湖区','滨江区','余杭区','萧山区',
           '浙江大学','浙大','中国美院','西湖','钱塘江','武林广场','灵隐寺'],
    '青岛': ['青岛','山东','市南区','市北区','崂山区','黄岛区',
           '中国海洋大学','青岛大学','山科大','栈桥','五四广场','崂山','八大关'],
    '郑州': ['郑州','河南','金水区','二七区','中原区','管城区',
           '郑州大学','河南大学','郑大','二七塔','如意湖','少林寺','郑东新区'],
}

def load_cookie(mobile=False):
    names = ['cookie_mobile.txt', 'cookie.txt'] if mobile else ['cookie.txt', 'cookie_mobile.txt']
    for n in names:
        for p in [n, os.path.join('..', n)]:
            if os.path.exists(p):
                with open(p, encoding='utf-8') as f:
                    return f.read().strip()
    return ''

def parse_time(s):
    if not s: return None
    s = str(s).strip()
    now = datetime.datetime.now()

    # 1. 标准微博格式: "Fri Jun 30 10:00:00 +0800 2023"
    try: return datetime.datetime.strptime(s, '%a %b %d %H:%M:%S %z %Y').replace(tzinfo=None)
    except: pass
    # 2. ISO格式: "2023-06-30 10:00:00"
    try: return datetime.datetime.strptime(s, '%Y-%m-%d %H:%M:%S')
    except: pass
    # 3. 中文带年份: "2023年06月30日 10:30" 或 "2015年03月15日"
    try:
        m = re.match(r'(\d{4})年(\d{1,2})月(\d{1,2})日\s*(\d{1,2}):(\d{2})', s)
        if m:
            return datetime.datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)),
                                     int(m.group(4)), int(m.group(5)))
    except: pass
    # 4. "刚刚" / "X分钟前" / "X小时前" → 返回当前时间（近期帖，年份≠2015就够了）
    if s in ('刚刚',) or '分钟前' in s or '小时前' in s:
        return now
    # 5. "昨天 HH:MM" → 昨天
    try:
        m = re.match(r'昨天\s*(\d{1,2}):(\d{2})', s)
        if m:
            d = now - datetime.timedelta(days=1)
            return datetime.datetime(d.year, d.month, d.day, int(m.group(1)), int(m.group(2)))
    except: pass
    # 6. "MM月DD日 HH:MM" → 今年
    try:
        m = re.match(r'(\d{1,2})月(\d{1,2})日\s*(\d{1,2}):(\d{2})', s)
        if m:
            return datetime.datetime(now.year, int(m.group(1)), int(m.group(2)),
                                     int(m.group(3)), int(m.group(4)))
    except: pass
    # 7. ISO date only: "2023-06-30"
    try: return datetime.datetime.strptime(s, '%Y-%m-%d')
    except: pass
    # 8. 正则兜底：提取4位年份
    try:
        m = re.search(r'(\d{4})', s)
        if m:
            return datetime.datetime(int(m.group(1)), 1, 1)
    except: pass
    return None

class WeiboCityCrawl:
    def __init__(self, target=10000):
        self.target = target
        self.wait = 2
        self.search_workers = 10  # 搜索线程数（GUI可配）
        self.running = True
        self.paused = False
        self.cities = CITIES
        self.cookie = load_cookie()
        self.mobile_cookie = load_cookie(mobile=True)
        self._log(f'Cookie: PC={bool(self.cookie)} 移动={bool(self.mobile_cookie)}')
        self.confirmed = {c: {} for c in CITIES}
        self.collected = {c: set() for c in CITIES}
        self.tried = set()
        self.lock = threading.Lock()
        self._api_lock = threading.Lock()  # API互斥锁，多线程时防并发请求
        self._expanded_seeds = set()  # 已扩散过的种子UID，避免重复
        self._session = requests.Session()  # 持久化Session（连接复用+Cookie管理）
        self._session.trust_env = False     # 忽略系统代理，避免连接干扰
        self._session.headers.update(_browser_headers(mobile=False))
        self.output = 'city_output'
        os.makedirs(self.output, exist_ok=True)
        self._last_cookie_refresh = 0
        self._cookie_refresh_lock = threading.Lock()  # 防并发刷新
        self.chrome_dir = 'chrome_weibo_profile'  # Chrome持久化profile目录（验证码用）
        self._on_pause_cb = None      # GUI注册的回调，验证码暂停时通知GUI启用恢复按钮
        self._api_delay = 0.5       # 自适应延迟初始值（参照B站爬虫的_adaptive_sleep模式）
        self._api_delay_min = 0.3   # 正常时最低间隔
        self._api_delay_max = 8.0   # 被限速时最高间隔
        self.collect_workers = 1      # 采集并发线程（单线程最稳最快）
        self._load()
        # 注册优雅退出：Ctrl+C或进程终止时自动存盘
        atexit.register(self._emergency_save)
        signal.signal(signal.SIGINT, lambda s, f: self._emergency_save() or os._exit(0))
        signal.signal(signal.SIGTERM, lambda s, f: self._emergency_save() or os._exit(0))

    def _log(self, msg):
        t = datetime.datetime.now().strftime('%H:%M:%S')
        print(f'[{t}] {msg}')

    def _adaptive_sleep(self, was_rate_limited=False):
        """参照B站爬虫的自适应延迟：正常时加速，被限时减速"""
        if was_rate_limited:
            self._api_delay = min(self._api_delay * 2, self._api_delay_max)
        else:
            self._api_delay = max(self._api_delay * 0.9, self._api_delay_min)
        time.sleep(self._api_delay)

    def _save(self):
        p = {'confirmed': {c: {uid: info for uid, info in self.confirmed[c].items()} for c in CITIES},
             'collected': {c: list(self.collected[c]) for c in CITIES},
             'tried': list(self.tried),
             'expanded_seeds': list(self._expanded_seeds)}
        path = os.path.join(self.output, 'state.json')
        tmp = path + '.tmp'
        with self.lock:
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(p, f, ensure_ascii=False)
            os.replace(tmp, path)  # 原子替换，崩溃不丢数据

    def _load(self):
        f = os.path.join(self.output, 'state.json')
        if not os.path.exists(f): return
        with open(f, encoding='utf-8') as fh:
            p = json.load(fh)
        # 合并而非替换——防止内存中有未存盘的tried被清空
        self.tried.update(p.get('tried', []))
        self._expanded_seeds.update(p.get('expanded_seeds', []))
        for c in CITIES:
            self.collected[c] = set(p.get('collected', {}).get(c, []))
            confirmed_data = p.get('confirmed', {}).get(c, {})
            if isinstance(confirmed_data, list):
                # 旧格式：UID列表 → 占位dict
                for uid in confirmed_data:
                    if uid not in self.confirmed[c]:
                        self.confirmed[c][uid] = {'uid': uid, '昵称': '', '所在地': c}
            else:
                # 新格式：{uid: {完整14字段}}
                for uid, info in confirmed_data.items():
                    if uid not in self.confirmed[c]:
                        self.confirmed[c][uid] = info
        self._log(f'恢复: {sum(len(v) for v in self.confirmed.values())}用户, tried={len(self.tried)}')

    def _emergency_save(self):
        """紧急存盘：Ctrl+C或进程终止时调用"""
        try:
            for city in self.cities:
                self.save_users(city)
            self._save()
            print('[紧急存盘] 数据已保存')
        except:
            pass

    # ===== 暂停/恢复 =====
    def pause(self):
        self.paused = True
        self._log('[暂停]')
        if self._on_pause_cb:
            try: self._on_pause_cb()
            except: pass

    def resume(self):
        self.paused = False
        self._log('[恢复]')
        if self._on_pause_cb:
            try: self._on_pause_cb()
            except: pass

    # ===== Cookie健康检查 =====
    def _auto_refresh_cookies(self):
        """调用独立Playwright脚本刷新cookie（加锁防并发，10秒内不重复刷）"""
        # 60秒内刚刷过就跳过
        if time.time() - self._last_cookie_refresh < 60:
            self._log('[Cookie] 刚刷新过，跳过')
            return
        # 抢锁，抢不到说明别的线程在刷新，直接等它完成
        if not self._cookie_refresh_lock.acquire(blocking=False):
            self._log('[Cookie] 其他线程正在刷新，等待...')
            self._cookie_refresh_lock.acquire(blocking=True, timeout=30)
            self._cookie_refresh_lock.release()
            return

        try:
            script = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'playwright_login.py')
            if not os.path.exists(script):
                self._log('[!] playwright_login.py 不存在')
                return
            self._log('[Cookie] 正在调用Playwright登录...')
            result = subprocess.run(['python', script], timeout=180,
                                    cwd=os.path.dirname(script),
                                    capture_output=True, text=True)
            if result.returncode != 0:
                self._log(f'[!] Playwright登录失败(exit={result.returncode})')
                if result.stderr.strip():
                    self._log(f'[!] stderr: {result.stderr.strip()[:200]}')
                return
            out = result.stdout
            if 'Cookie保存完成' in out:
                self._log('[Cookie] Playwright登录成功')
                self.cookie = load_cookie()
                self.mobile_cookie = load_cookie(mobile=True)
                self._last_cookie_refresh = time.time()
            else:
                self._log(f'[!] Playwright输出异常: {out.strip()[-100:]}')
        except subprocess.TimeoutExpired:
            self._log('[!] Playwright登录超时(180s)')
        except Exception as e:
            self._log(f'[!] Playwright调用异常: {e}')
        finally:
            self._cookie_refresh_lock.release()
            return

    def _check_mobile_cookie(self):
        """快速检测移动端cookie是否有效（MLOGIN=1），遇到验证码自动打开浏览器"""
        for attempt in range(2):
            try:
                r = requests.get(
                    'https://m.weibo.cn/api/container/getIndex?type=uid&value=0&containerid=1076030&page=1',
                    headers={'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_5 like Mac OS X) AppleWebKit/605.1.15',
                             'X-Requested-With': 'XMLHttpRequest', 'Accept': 'application/json',
                             'Referer': 'https://m.weibo.cn/', 'Cookie': self.mobile_cookie}, timeout=10)
                d = r.json()
                ok = d.get('ok', 0)
                if ok == 1: return True
                captcha_url = d.get('url', '')
                if 'captcha' in captcha_url and attempt == 0:
                    self._log('[验证码] 正在用Chrome(带cookie)打开验证页面...')
                    try:
                        subprocess.Popen([
                            r'C:\Program Files\Google\Chrome\Application\chrome.exe',
                            '--user-data-dir=' + os.path.abspath(self.chrome_dir),
                            captcha_url
                        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    except:
                        self._log('[验证码] 请手动打开: https://m.weibo.cn/')
                    # 等待用户完成验证（最多等60秒，每5秒重试一次）
                    for _ in range(12):
                        time.sleep(5)
                        try:
                            r2 = requests.get(
                                'https://m.weibo.cn/api/container/getIndex?type=uid&value=0&containerid=1076030&page=1',
                                headers={'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_5 like Mac OS X) AppleWebKit/605.1.15',
                                         'X-Requested-With': 'XMLHttpRequest', 'Accept': 'application/json',
                                         'Referer': 'https://m.weibo.cn/', 'Cookie': self.mobile_cookie}, timeout=10)
                            if r2.json().get('ok') == 1:
                                self._log('[验证码] 验证完成！Cookie已恢复')
                                return True
                        except: pass
                    self._log('[验证码] 等待超时，请手动运行 playwright_login.py 后重启')
                    return False
                elif 'captcha' in captcha_url:
                    self._log('[验证码] 验证失败，请运行: python playwright_login.py')
                    return False
                else:
                    self._log('[!] 移动Cookie无效 (ok=%s)，需要MLOGIN=1' % ok)
                    return False
            except Exception as e:
                self._log('[!] 移动Cookie检测异常: %s' % str(e)[:40])
            time.sleep(3)
        return False

    def _cookie_health_check(self):
        """每20分钟重读cookie文件，失效时自动刷新并提示"""
        now = time.time()
        if now - self._last_cookie_refresh < 1200:
            # 20分钟内：快检PC cookie
            try:
                r = requests.get('https://weibo.com/ajax/profile/info?uid=0',
                                 headers={'User-Agent': 'Mozilla/5.0', 'Cookie': self.cookie,
                                          'X-Requested-With': 'XMLHttpRequest', 'Accept': 'application/json',
                                          'Referer': 'https://weibo.com/'}, timeout=5)
                if r.json().get('ok') == 1: return
            except: pass
        self._auto_refresh_cookies()
        # 验证PC cookie
        pc_ok = False
        try:
            r = requests.get('https://weibo.com/ajax/profile/info?uid=0',
                             headers={'User-Agent': 'Mozilla/5.0', 'Cookie': self.cookie,
                                      'X-Requested-With': 'XMLHttpRequest', 'Accept': 'application/json',
                                      'Referer': 'https://weibo.com/'}, timeout=10)
            pc_ok = r.json().get('ok') == 1
        except: pass
        if not pc_ok:
            self._log('[!] PC Cookie失效，请运行: python playwright_login.py')
        # 验证移动cookie
        if not self._check_mobile_cookie():
            self._log('[!] 移动Cookie失效，请运行: python playwright_login.py (需扫码登录m.weibo.cn)')

    def _api(self, url, params=None, mobile=False):
        cookie = self.mobile_cookie if mobile else self.cookie
        api_lock = getattr(self, '_api_lock', None)
        for attempt in range(2):
            while self.paused: time.sleep(0.5)
            if api_lock:
                with api_lock:
                    self._adaptive_sleep()  # 锁内自适应错开
            h = _browser_headers(mobile, cookie=cookie)
            h['Cookie'] = cookie
            h['X-Requested-With'] = 'XMLHttpRequest'
            try:
                r = requests.get(url, headers=h, params=params, timeout=10)
                if r.status_code == 200:
                    d = r.json()
                    ok_val = d.get('ok')
                    if ok_val == 1:
                        self._adaptive_sleep(was_rate_limited=False)  # 成功，逐步加速
                        return d
                    elif ok_val == 0:
                        return None  # 无更多内容，正常结束
                    elif ok_val == -100 and mobile:
                        # Cookie过期，刷新后重试
                        self._log('[!] API ok=-100，触发cookie刷新...')
                        self._auto_refresh_cookies()
                        cookie = self.mobile_cookie
                        self._adaptive_sleep(was_rate_limited=True)
                        continue
                    else:
                        captcha_url = d.get('url', '')
                        if 'captcha' in captcha_url and mobile:
                            self._log('[验证码] API触发验证码，用Chrome(带cookie)打开...')
                            try:
                                subprocess.Popen([
                                    r'C:\Program Files\Google\Chrome\Application\chrome.exe',
                                    '--user-data-dir=' + os.path.abspath(self.chrome_dir),
                                    captcha_url
                                ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                            except:
                                self._log('[验证码] 请手动打开: https://m.weibo.cn/')
                            self._log('[验证码] 请在Chrome中完成验证，爬虫将暂停60秒等待...')
                            time.sleep(60)
                            self._auto_refresh_cookies()
                            cookie = self.mobile_cookie
                        else:
                            self._log('API ok=%s %s' % (ok_val, url[:60]))
                        self._adaptive_sleep(was_rate_limited=True)
                        return None
                elif r.status_code == 429:
                    self._log('HTTP429 限流，自适应退避...')
                    self._adaptive_sleep(was_rate_limited=True)
                elif r.status_code == 418:
                    self._log('HTTP418 WAF拦截，等待90s...')
                    time.sleep(90)
                    self._adaptive_sleep(was_rate_limited=True)
                elif r.status_code == 403:
                    self._log('HTTP403 禁止访问，等待60s...')
                    time.sleep(60)
                    self._adaptive_sleep(was_rate_limited=True)
                elif r.status_code in (500, 502, 503):
                    self._log('HTTP%s 服务器错误，稍后重试...' % r.status_code)
                    self._adaptive_sleep(was_rate_limited=True)
                elif r.status_code == 400:
                    continue
                else:
                    self._log('HTTP%s %s' % (r.status_code, url[:60]))
                    self._adaptive_sleep(was_rate_limited=True)
            except Exception as e:
                err_str = str(e)
                if 'Connection' in err_str or 'RemoteDisconnected' in err_str:
                    self._log('IP限流，自适应冷却...')
                    self._adaptive_sleep(was_rate_limited=True)
                else:
                    self._log('网络:%s' % err_str[:40])
                    self._adaptive_sleep(was_rate_limited=True)
        return None

    # ===== 搜索 =====
    def _search_api(self, kw, max_page=10):
        """备用搜索：使用weibo.com AJAX用户搜索API（比老版s.weibo.com更稳定）"""
        uids = set()
        for page in range(1, max_page + 1):
            if not self.running: break
            while self.paused: time.sleep(0.5)
            try:
                with self._api_lock:
                    time.sleep(random.uniform(0.5, 1.0))
                    r = requests.get(
                        'https://weibo.com/ajax/search/users',
                        params={'q': kw, 'page': page},
                        headers=_browser_headers(mobile=False, cookie=self.cookie),
                        timeout=10)
                if r.status_code == 429:
                    time.sleep(30)
                    continue
                if r.status_code != 200:
                    break
                d = r.json()
                if d.get('ok') != 1:
                    break
                users = d.get('data', {}).get('user_list', []) or d.get('data', {}).get('users', [])
                if not users:
                    break
                for u in users:
                    uid = str(u.get('id', u.get('idstr', '')))
                    if uid.isdigit():
                        uids.add(uid)
            except:
                break
        return uids

    def search(self, city):
        found = set()
        kws = KEYWORDS.get(city, [city])

        def search_one(kw):
            f = set()
            stale = 0
            for page in range(1, 20):
                if not self.running: break
                while self.paused: time.sleep(0.5)
                try:
                    sh = _browser_headers(mobile=False, cookie=self.cookie)
                    sh['Cookie'] = self.cookie
                    with self._api_lock:
                        time.sleep(random.uniform(0.3, 0.8))
                        r = requests.get(f'https://s.weibo.com/user?q={kw}&page={page}', headers=sh, timeout=10)
                    if r.status_code == 429: time.sleep(30); continue
                    if r.status_code != 200: break
                except: break
                soup = BeautifulSoup(r.text, 'lxml')
                cards = soup.find_all('div', class_='card')
                if not cards: break
                b4 = len(f)
                for card in cards:
                    for a in card.find_all('a', href=True):
                        if '/u/' in a['href']:
                            uid = a['href'].split('/u/')[-1].split('?')[0]
                            if uid.isdigit(): f.add(uid)
                if len(f) == b4: stale += 1
                else: stale = 0
                if stale >= 2: break
                time.sleep(self.wait + random.uniform(0, 0.3))
            # 老版搜索页结果太少 → 尝试AJAX搜索API兜底
            if len(f) < 5:
                self._log(f'  老版搜索"{kw}"仅{len(f)}结果，尝试API兜底...')
                try:
                    api_uids = self._search_api(kw, max_page=10)
                    f.update(api_uids)
                    self._log(f'  API兜底"{kw}"新增{len(api_uids)}结果')
                except Exception as e:
                    self._log(f'  API兜底失败: {e}')
            return f

        self._log(f'搜索 {len(kws)}关键词 {self.search_workers}线...')
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.search_workers) as ex:
            for future in concurrent.futures.as_completed(
                    {ex.submit(search_one, kw): kw for kw in kws}):
                try: found.update(future.result())
                except: pass
        self._log(f'搜索完成: {len(found)}候选')
        self._save()  # 搜索成果存盘
        return found

    # ===== 验证（14字段完整版）=====
    def verify_one(self, uid, city):
        # 加锁检查+标记tried，消除竞态条件
        with self.lock:
            if uid in self.tried: return None
            self.tried.add(uid)
        try:
            d = self._api('https://weibo.com/ajax/profile/info', {'uid': uid})
            if d is None or d.get('ok') != 1: return None
            u = d.get('data', {}).get('user')
            if not u: return None
            loc = u.get('location', '')
            if city not in loc: return None
            sc, fc, fr = u.get('statuses_count', 0), u.get('followers_count', 0), u.get('friends_count', 0)
            if sc == 0 or (fc == 0 and fr == 0): return None
            return {
                'uid': str(uid), '昵称': u.get('screen_name', ''),
                '性别': u.get('gender', '未知'), '所在地': loc, 'IP属地': u.get('ip_location', ''),
                '认证类型': '认证' if u.get('verified') else '未认证',
                '认证信息': u.get('verified_reason', ''), '简介': u.get('description', ''),
                '粉丝数': fc, '关注数': fr, '微博数': sc,
                '注册时间': u.get('created_at', ''), '用户主页链接': f'https://weibo.com/u/{uid}',
                '质量标记': 'high' if city in u.get('description', '') else 'normal',
            }
        except Exception:
            return None

    def verify_batch(self, city, uids):
        ok = 0
        total = len(uids)
        # 偶尔混入无关请求破坏模式（5%概率）
        if random.random() < 0.05:
            try:
                requests.get('https://weibo.com/ajax/sidebar/remind',
                             headers=_browser_headers(mobile=False, cookie=self.cookie), timeout=5)
            except: pass
        # 打乱UID顺序——不要总是按搜索结果顺序验证
        shuffled = list(uids)
        random.shuffle(shuffled)
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
            futures = {ex.submit(self.verify_one, uid, city): uid for uid in shuffled}
            for i, future in enumerate(concurrent.futures.as_completed(futures)):
                try: info = future.result(timeout=15)
                except: info = None
                if info:
                    self.confirmed[city][futures[future]] = info
                    ok += 1
                # 每20个微停0.8-2秒
                if (i + 1) % 20 == 0:
                    time.sleep(random.uniform(0.8, 2))
                if (i + 1) % 50 == 0:
                    self._log(f'  验证 {i+1}/{total} 通过{ok} 累计{len(self.confirmed[city])}')
                    self.save_users(city)
                    self._save()
                # 每150人长停4-8秒
                if (i + 1) % 150 == 0:
                    pause = random.uniform(4, 8)
                    self._log(f'  已验{i+1}人，休息{pause:.0f}秒...')
                    time.sleep(pause)
        return ok

    # ===== 社交扩散（14字段完整版）=====
    def expand(self, city):
        """从关注列表扩展同城用户 — 使用PC端API（免验证码）"""
        candidates = {}
        all_confirmed = list(self.confirmed[city].keys())
        fresh = [u for u in all_confirmed if u not in self._expanded_seeds]
        random.shuffle(fresh)
        seeds = fresh[:10]  # 随机选10个种子，公平覆盖
        if not seeds:
            self._log('扩散: 所有种子已用完，无新种子可扩散')
            return candidates
        ph_base = _browser_headers(mobile=False, cookie=self.cookie)
        ph_base['Cookie'] = self.cookie
        ph_base['X-Requested-With'] = 'XMLHttpRequest'
        self._log(f'扩散 {len(seeds)}种子(PC关注API)...')

        def do_seed(uid):
            local = {}
            total_found = 0
            rate_limits = [0]  # 用list包装以便在闭包中修改
            for pg in range(1, 4):  # 翻3页关注列表
                while self.paused: time.sleep(0.5)
                for retry in range(2):
                    try:
                        with self._api_lock:
                            time.sleep(random.uniform(0.3, 0.8))
                            r = requests.get(
                                f'https://weibo.com/ajax/friendships/friends?uid={uid}&page={pg}',
                                headers=ph_base, timeout=10)
                        if r.status_code == 429:
                            rate_limits[0] += 1
                            wait = 60 * (retry + 1)
                            self._log(f'扩散 HTTP429 冷却{wait}s...')
                            time.sleep(wait)
                            continue
                        if r.status_code == 403:
                            time.sleep(30)
                            continue
                        if r.status_code != 200:
                            break
                        d = r.json()
                        if d.get('ok') != 1:
                            break
                        users = d.get('users', [])
                        if not users:
                            break
                        break  # 成功，跳出retry循环
                    except:
                        time.sleep(3 * (retry + 1))
                        continue
                else:
                    break  # retry耗尽，翻下一页
                try:
                    for u in users:
                        fid = str(u.get('id', ''))
                        if not fid or fid in self.tried or fid in local: continue
                        loc = u.get('location', '')
                        if city in loc:
                            local[fid] = {
                                'uid': fid, '昵称': u.get('screen_name', ''),
                                '性别': u.get('gender', '未知'), '所在地': loc, 'IP属地': u.get('ip_location', ''),
                                '认证类型': '认证' if u.get('verified') else '未认证',
                                '认证信息': u.get('verified_reason', ''), '简介': u.get('description', ''),
                                '粉丝数': u.get('followers_count', 0), '关注数': u.get('friends_count', 0),
                                '微博数': u.get('statuses_count', 0),
                                '注册时间': u.get('created_at', ''), '用户主页链接': f'https://weibo.com/u/{fid}',
                                '质量标记': 'high' if city in u.get('description', '') else 'normal',
                            }
                        with self.lock: self.tried.add(fid)
                    total_found += len(users)
                except: break
                time.sleep(random.uniform(0.3, 0.6))
            return (local, total_found, rate_limits[0])

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as ex:
            futures = {ex.submit(do_seed, uid): uid for uid in seeds}
            total_found = 0
            total_rate_limits = 0
            failed_seeds = set()
            for future in concurrent.futures.as_completed(futures):
                uid = futures[future]
                try:
                    result = future.result(timeout=120)
                    if isinstance(result, tuple) and len(result) == 3:
                        local_dict, found, rl = result
                        total_rate_limits += rl
                    elif isinstance(result, tuple):
                        local_dict, found = result
                    else:
                        local_dict, found = result, 0
                    candidates.update(local_dict)
                    total_found += found
                    if found > 0:
                        with self.lock: self._expanded_seeds.add(uid)  # API成功：标记已扩散
                    else:
                        failed_seeds.add(uid)  # 0关注=可能网络问题，不标记
                except:
                    failed_seeds.add(uid)  # 异常=网络问题，不标记
        if failed_seeds:
            self._log(f'扩散 {len(seeds)}种子 -> 关注{total_found}人 -> 同城{len(candidates)}人 ({len(failed_seeds)}种子0关注/失败，下轮重试)')
        else:
            self._log(f'扩散 {len(seeds)}种子 -> 关注{total_found}人 -> 同城{len(candidates)}人 (累计已扩散{len(self._expanded_seeds)}种子)')
        # 429超过阈值时触发冷却
        self._need_cooldown = total_rate_limits >= 3
        return candidates

    # ===== 2015微博采集（纯requests，零Playwright）=====
    def _pw_init(self):
        """启动采集：只重载cookie文件 + requests预热，不碰Playwright"""
        self._log('[采集] 重载cookie + 预热...')
        # 直接从文件重载cookie（不调Playwright）
        self.mobile_cookie = load_cookie(mobile=True)
        self.cookie = load_cookie()
        # 用requests预热session
        try:
            requests.get('https://m.weibo.cn/', headers={
                'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15',
                'Cookie': self.mobile_cookie}, timeout=10)
        except: pass
        self._log('[采集] 就绪')

    def _pw_request(self, url):
        """纯requests请求——不调playwright，保持session纯净。
        验证码处理：绝不启动Playwright（会重置白名单），只用系统浏览器+文件重载cookie"""
        if not self.mobile_cookie:
            self._log("  [API] mobile_cookie为空!")
            return None
        h = {
            'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15',
            'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest',
            'Referer': 'https://m.weibo.cn/', 'Cookie': self.mobile_cookie,
        }
        base_delay = 2.0  # 每线程基础延迟2.0s（单线程已验证安全）
        for attempt in range(3):
            try:
                # 每线程 2.0-3.0s 间隔，3线程自然错开 → 总吞吐 ~1.0-1.5 req/s
                delay = base_delay + random.uniform(0, 1.0)
                time.sleep(delay)
                while self.paused:
                    time.sleep(0.3)
                r = requests.get(url, headers=h, timeout=12)
                d = r.json()
                if d.get('ok') == 1:
                    return d
                if d.get('ok') == -100:
                    captcha_url = d.get('url', '')
                    if captcha_url and 'captcha' in captcha_url and attempt < 2:
                        self._log('********************************')
                        self._log('*** [验证码] 请完成验证! ***')
                        self._log('*** 正在用Chrome(带cookie)打开验证页面...')
                        self._log('*** 如果Chrome没自动打开，手动访问: https://m.weibo.cn/')
                        self._log('*** 完成滑块后点击GUI"▶ 恢复"继续 ***')
                        self._log('********************************')
                        # 用持久化Chrome profile打开——自带cookie，验证码页面不会再"请求非法"
                        try:
                            subprocess.Popen([
                                r'C:\Program Files\Google\Chrome\Application\chrome.exe',
                                '--user-data-dir=' + os.path.abspath(self.chrome_dir),
                                captcha_url
                            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        except:
                            self._log('[验证码] Chrome启动失败，请手动打开m.weibo.cn完成验证')
                        # 暂停等用户手动完成验证码（用pause()触发GUI回调）
                        self.pause()
                        waited = 0
                        while self.paused and self.running:
                            time.sleep(1); waited += 1
                            if waited > 180:
                                self.resume()
                                self._log('[验证码] 超时，自动恢复...')
                                break
                        # 无论超时与否，都重载cookie + 降速
                        self.mobile_cookie = load_cookie(mobile=True)
                        h['Cookie'] = self.mobile_cookie
                        base_delay = 4.0
                        if waited <= 180:
                            self._log('[验证码] 已恢复，cookie已重载')
                        else:
                            self._log('[验证码] 超时，cookie已重载继续')
                    else:
                        # 纯限流，等久一点
                        self._log('[限流] 等待90s...')
                        for _ in range(90):
                            if not self.running: break
                            while self.paused: time.sleep(0.5)
                            time.sleep(1)
                        self.mobile_cookie = load_cookie(mobile=True)
                        h['Cookie'] = self.mobile_cookie
                        base_delay = 3.0
                    continue
                # ok=0: 无数据（隐私账号/页码越界/无可见帖），返回空数据不重试
                # 其他非1/-100: 诊断日志后返回None
                if d.get('ok') == 0:
                    return {"ok": 0, "data": {"cards": []}}
                self._log("  [API] ok=%s http=%d uid=%s" % (d.get('ok'), r.status_code, url.split('=')[-1].split('&')[0]))
                return None
            except Exception as e:
                err_full = str(e)
                # 诊断：区分连接层错误 vs HTTP层错误
                if 'Connection' in type(e).__name__ or 'ConnectTimeout' in type(e).__name__ or 'ConnectionError' in type(e).__name__:
                    err_type = '连接'
                elif 'Timeout' in type(e).__name__:
                    err_type = '超时'
                elif 'SSL' in type(e).__name__ or 'SSLError' in type(e).__name__:
                    err_type = 'SSL'
                else:
                    err_type = type(e).__name__
                if attempt < 2:
                    self._log("  [API] 异常重试(%s): %s" % (err_type, err_full[:120]))
                    time.sleep(5)
                    base_delay = 3.0
                else:
                    self._log("  [API] 异常放弃(%s): %s" % (err_type, err_full[:120]))
                    return None
        return None

    def collect_2015(self, uid):
        """采集用户2015年微博 — 从最新向最旧翻，二分段跳转定位。
        核心优化：last_year=0时不做二分(浪费API)，ratio估算+限30页扫描"""
        posts, name, api_ok = [], "", False

        def fetch_page(p):
            return self._pw_request(
                "https://m.weibo.cn/api/container/getIndex?type=uid&value=" + uid + "&containerid=107603" + uid + "&page=" + str(p)
            )

        # 方案1: 注册时间预过滤 — 2016后注册的不可能有2015帖，零API跳过
        for c in self.cities:
            info = self.confirmed.get(c, {}).get(uid)
            if info:
                reg_str = info.get("注册时间", "")
                if reg_str:
                    reg_year = 0
                    rt = parse_time(reg_str)
                    reg_year = rt.year if rt else 0
                    if reg_year == 0:
                        m = re.search(r'(\d{4})', str(reg_str))
                        if m: reg_year = int(m.group(1))
                    if reg_year > 2015:
                        self._log("  注册%d年 → 跳过" % reg_year)
                        return ([], True)  # 2016后注册，标记完成
                name = info.get("昵称", "")
                break

        # Step 1: 取第1页
        d1 = fetch_page(1)
        if d1 is None:
            self._log("  API失败 → 跳过")
            return ([], False)
        cards1 = d1.get("data", {}).get("cards", [])
        total = d1.get("data", {}).get("cardlistInfo", {}).get("total", 0)
        if not cards1:
            self._log("  无可见帖子(total=%d) → 跳过" % total)
            return ([], True if total == 0 else False)

        name = cards1[0].get("mblog", {}).get("user", {}).get("screen_name", "")
        if not name:
            for c in self.cities:
                if uid in self.confirmed.get(c, {}):
                    name = self.confirmed[c][uid].get("昵称", "")
                    break

        first_dt = cards1[0].get("mblog", {}).get("created_at", "")
        first_parsed = parse_time(first_dt)
        first_year = first_parsed.year if first_parsed else 0
        last_page = max(1, total // 10 + 1)
        self._log("  total=%d 最新=%d" % (total, first_year))

        # 方案5: 最新帖在2015之前 → 全站帖子≤2014，绝无2015帖，零风险跳过
        if first_year > 0 and first_year < 2015:
            self._log("  最新%d年 → 无2015帖" % first_year)
            return ([], True)

        # 方案2: 小profile(<100帖) → 不跳页不二分，直扫
        if total < 100:
            posts = self._scan_posts(uid, name, 1, min(11, last_page + 1))
            return (posts, bool(posts))

        # 方案4: first_year>2020且total<500 → 快速末页确认，不做二分
        quick_last = None  # 存末页结果，Step2复用以避免重复请求
        if first_year > 2020 and total < 500 and last_page > 1:
            self._log("  快速末页确认...")
            d_last = fetch_page(last_page)
            if d_last:
                cards_last = d_last.get("data", {}).get("cards", [])
                if cards_last:
                    last_year = self._try_parse_year(cards_last, -1)
                    if last_year > 2015:
                        return ([], True)
                    quick_last = (d_last, cards_last, last_year)  # 保存供Step2复用

        # Step 2: 快速判定是否有2015
        is_reliable = True

        if first_year <= 2015 and first_year > 0:
            start_page = 1
            is_reliable = True
        elif first_year <= 0:
            is_reliable = False
            lookback = max(30, last_page // 2)
            self._log("  日期未知，跳p%d推测..." % last_page)
            d_last = fetch_page(last_page)
            if d_last is None:
                return ([], False)
            cards_last = d_last.get("data", {}).get("cards", [])
            if cards_last:
                last_year = self._try_parse_year(cards_last, -1)
                if last_year > 2015:
                    return ([], True)
                if last_year > 0 and last_year <= 2015:
                    start_page = max(1, last_page - max(20, min(last_page // 5, 100)))
                    is_reliable = True
                else:
                    start_page = max(1, last_page - lookback)
                    self._log("  年份未知，从p%d开始(回看%d页)" % (start_page, lookback))
            else:
                start_page = max(1, last_page - lookback)
        else:
            lookback = max(30, last_page // 2)
            # 方案4已取末页 → 复用，不重复请求
            if quick_last and quick_last[2] > 0:
                d_last, cards_last, last_year = quick_last
                self._log("  最早年份=%d(复用)" % last_year)
            else:
                self._log("  跳p%d看最早年份..." % last_page)
                d_last = fetch_page(last_page)
                if d_last is None:
                    return ([], False)
                cards_last = d_last.get("data", {}).get("cards", [])
                if not cards_last:
                    start_page = max(1, last_page - lookback)
                    is_reliable = False
                    self._log("  末页无数据，从p%d开始(回看%d页)" % (start_page, lookback))
                    cards_last = None  # 标记已处理
                last_year = self._try_parse_year(cards_last, -1) if cards_last else 0
                self._log("  最早年份=%d" % last_year)
            if cards_last is not None and last_year > 0:
                if last_year > 2015:
                    return ([], True)
                if last_year == 2015:
                    start_page = max(1, last_page - max(20, min(last_page // 5, 100)))
                    is_reliable = True
                else:
                    start_page, is_reliable = self._binary_search_2015(uid, fetch_page, 1, last_page)
            elif cards_last is not None:
                # last_year == 0: 解析失败
                is_reliable = False
                span = max(1, first_year - 2010)
                linear_ratio = (first_year - 2015) / span
                ratio = linear_ratio ** 0.4
                start_page = int(last_page * ratio)
                start_page = max(1, min(last_page, start_page - 10))
                self._log("  末页日期未知，非线性估算p%d" % start_page)

        # Step 3: 扫描2015微博
        # 年均发帖量判断：日均>5条持续多年 → 营销号，缩减扫描
        cap = 150
        for c in self.cities:
            info = self.confirmed.get(c, {}).get(uid)
            if info:
                sc = int(info.get('微博数', 0) or 0) or total  # total兜底: 确认信息可能缺微博数
                reg_str = info.get('注册时间', '')
                if sc > 0 and reg_str:
                    rt = parse_time(reg_str)
                    if rt:
                        age = max(0.5, (datetime.datetime.now() - rt).days / 365.0)
                        ppy = sc / age
                        if ppy > 365:        # 日均>1条 → 不可能持续10+年，跳过
                            self._log("  日均%.1f条(ppy=%d) → 跳过" % (ppy / 365, int(ppy)))
                            return ([], True)
                        if ppy > 3000:       # 日均8条+(兜底)
                            cap = 20
                        elif ppy > 1500:      # 日均4条+(兜底)
                            cap = 60
                break
        # 可靠→cap页；不可靠→total的一半，下限50
        if is_reliable:
            scan_limit = min(cap, last_page)
        else:
            scan_limit = min(max(30, last_page // 3), cap)
        max_scan = min(last_page + 1, start_page + scan_limit)
        self._log("  从p%d开始扫描(限%d页%s)..." % (start_page, scan_limit, '' if is_reliable else ', 保守'))

        date_skip_count = 0   # 统计日期解析失败的帖子数
        fail_streak = 0       # 连续fetch失败计数
        scanned_pages = 0     # 已扫页数
        earliest_seen = 9999  # 保守扫描时跟踪最早年份，用于提前中断
        for page in range(start_page, max_scan):
            while self.paused: time.sleep(0.5)
            if not self.running: break

            d = fetch_page(page)
            if d is None:
                fail_streak += 1
                if fail_streak >= 3:
                    self._log("  连续%d页请求失败，中断扫描" % fail_streak)
                    break
                continue
            fail_streak = 0  # 成功则重置
            scanned_pages += 1
            # 长扫描进度提示：每20页报一次
            if scanned_pages % 20 == 0:
                self._log("  扫描中... p%d/%d (已找到%d条)" % (page, max_scan-1, len(posts)))
            cards = d.get("data", {}).get("cards", [])
            if not cards:
                continue

            pre_2015 = False
            for card in cards:
                mblog = card.get("mblog")
                if not mblog: continue
                dt = parse_time(mblog.get("created_at", ""))
                if dt is None:
                    date_skip_count += 1
                    continue
                if dt.year < earliest_seen:
                    earliest_seen = dt.year
                if dt.year < 2015:
                    pre_2015 = True
                    continue
                if dt.year != 2015: continue
                txt = mblog.get("text_raw", "") or re.sub(r"<[^>]+>", "", mblog.get("text", ""))
                if mblog.get("retweeted_status"):
                    rt = mblog["retweeted_status"]
                    rt_user = (rt.get("user") or {}).get("screen_name", "")
                    rt_txt = rt.get("text_raw", "") or re.sub(r"<[^>]+>", "", rt.get("text", ""))
                    user_comment = txt.strip()
                    if user_comment in ("转发微博", ""):
                        txt = "//@%s: %s" % (rt_user, rt_txt.strip())
                    else:
                        txt = "%s //@%s: %s" % (user_comment, rt_user, rt_txt.strip())
                posts.append({
                    "uid": str(uid), "用户昵称": name,
                    "微博id": str(mblog.get("id", "")),
                    "微博链接": "https://weibo.com/" + str(uid) + "/" + str(mblog.get("id", "")),
                    "发布时间": dt.strftime("%Y-%m-%d %H:%M:%S"),
                    "微博内容": txt.strip(),
                    "转发数": mblog.get("reposts_count", 0),
                    "评论数": mblog.get("comments_count", 0),
                    "点赞数": mblog.get("attitudes_count", 0),
                    "发布于": mblog.get("source", ""),
                    "话题标签": ";".join(re.findall(r"#([^#]+)#", txt)),
                })
            if pre_2015:
                api_ok = True
                break
            # 保守扫描提前中断：25页后仍未触达2015 → 估算偏差太大，放弃
            if not is_reliable and scanned_pages >= 25 and earliest_seen > 2015:
                self._log("  已扫%d页仍未见2015(最早%d)，提前中断" % (scanned_pages, earliest_seen))
                break

        if date_skip_count > 0:
            self._log("  ⚠ %d条帖日期解析失败被跳过" % date_skip_count)
        if posts and not api_ok:
            api_ok = True
        return (posts, api_ok)

    def _scan_posts(self, uid, name, start_page, end_page):
        """扫描页范围内提取2015微博（小profile共用）"""
        posts = []
        for page in range(start_page, end_page):
            while self.paused: time.sleep(0.5)
            if not self.running: break
            d = self._pw_request(
                "https://m.weibo.cn/api/container/getIndex?type=uid&value=" + uid + "&containerid=107603" + uid + "&page=" + str(page)
            )
            if d is None: continue
            cards = d.get("data", {}).get("cards", [])
            for card in cards:
                mblog = card.get("mblog")
                if not mblog: continue
                dt = parse_time(mblog.get("created_at", ""))
                if dt is None or dt.year != 2015: continue
                txt = mblog.get("text_raw", "") or re.sub(r"<[^>]+>", "", mblog.get("text", ""))
                if mblog.get("retweeted_status"):
                    rt = mblog["retweeted_status"]
                    rt_user = (rt.get("user") or {}).get("screen_name", "")
                    rt_txt = rt.get("text_raw", "") or re.sub(r"<[^>]+>", "", rt.get("text", ""))
                    user_comment = txt.strip()
                    if user_comment in ("转发微博", ""):
                        txt = "//@%s: %s" % (rt_user, rt_txt.strip())
                    else:
                        txt = "%s //@%s: %s" % (user_comment, rt_user, rt_txt.strip())
                posts.append({
                    "uid": str(uid), "用户昵称": name,
                    "微博id": str(mblog.get("id", "")),
                    "微博链接": "https://weibo.com/" + str(uid) + "/" + str(mblog.get("id", "")),
                    "发布时间": dt.strftime("%Y-%m-%d %H:%M:%S"),
                    "微博内容": txt.strip(),
                    "转发数": mblog.get("reposts_count", 0),
                    "评论数": mblog.get("comments_count", 0),
                    "点赞数": mblog.get("attitudes_count", 0),
                    "发布于": mblog.get("source", ""),
                    "话题标签": ";".join(re.findall(r"#([^#]+)#", txt)),
                })
        return posts

    def _try_parse_year(self, cards, idx):
        """从卡片列表中提取年份（辅助方法）"""
        try:
            card = cards[idx]
            dt_str = card.get("mblog", {}).get("created_at", "")
            parsed = parse_time(dt_str)
            return parsed.year if parsed else 0
        except:
            return 0

    def _binary_search_2015(self, uid, fetch_page, lo, hi):
        """二分定位2015所在页。返回 (start_page, converged)。
        converged=True 表示找到2015边界，起点可靠可用150页扫描"""
        for _ in range(10):
            mid = (lo + hi) // 2
            if mid <= lo or mid >= hi:
                return (max(1, lo), False)  # 范围耗尽，未收敛
            dm = fetch_page(mid)
            if dm is None:
                hi = mid
                continue
            cm = dm.get("data", {}).get("cards", [])
            if not cm:
                hi = mid
                continue
            fy = parse_time(cm[0].get("mblog", {}).get("created_at", ""))
            ly = parse_time(cm[-1].get("mblog", {}).get("created_at", ""))
            fy = fy.year if fy else 0
            ly = ly.year if ly else 0
            # 日期解析全部失败 → 在更深的位置继续找
            if fy == 0 and ly == 0:
                lo = mid
                continue
            if ly > 2015:
                lo = mid
            elif fy < 2015:
                hi = mid
            else:
                return (mid, True)  # 成功定位2015所在页！
        return (max(1, lo), False)  # 6轮耗尽，未收敛

    def save_users(self, city):
        users = list(self.confirmed[city].values())
        if not users: return
        f = os.path.join(self.output, f'{city}_用户.csv')
        fields = ['uid', '昵称', '性别', '所在地', 'IP属地', '认证类型', '认证信息',
                  '简介', '粉丝数', '关注数', '微博数', '注册时间', '用户主页链接', '质量标记']
        with open(f, 'w', newline='', encoding='utf-8-sig') as fh:
            w = csv.DictWriter(fh, fieldnames=fields, extrasaction='ignore')
            w.writeheader(); w.writerows(users)

    def save_posts(self, posts, city):
        if not posts: return
        f = os.path.join(self.output, f'{city}_2015微博.csv')
        fields = ['uid', '用户昵称', '微博id', '微博链接', '发布时间',
                  '微博内容', '转发数', '评论数', '点赞数', '发布于', '话题标签']
        with self.lock:
            # 锁内读取已有微博id去重 + 写入，防止并发重复
            existing_ids = set()
            try:
                if os.path.exists(f) and os.path.getsize(f) > 0:
                    with open(f, 'r', encoding='utf-8-sig') as fh:
                        reader = csv.DictReader(fh)
                        for row in reader:
                            pid = row.get('微博id', '')
                            if pid: existing_ids.add(pid)
            except: pass
            new_posts = [p for p in posts if p.get('微博id', '') not in existing_ids]
            if not new_posts: return
            ex = os.path.exists(f) and os.path.getsize(f) > 0
            with open(f, 'a+', newline='', encoding='utf-8-sig') as fh:
                w = csv.DictWriter(fh, fieldnames=fields, extrasaction='ignore')
                if not ex: w.writeheader()
                w.writerows(new_posts)

        # ===== 完整流程 =====
    def run_city(self, city):
        self._log(f'\n========== {city} ==========')
        self._cookie_health_check()
        cur = len(self.confirmed[city])
        self._log(f'已确认: {cur}/{self.target}')

        rnd = 0
        stale = 0
        while self.running and cur < self.target:
            while self.paused: time.sleep(0.5)
            rnd += 1
            self._log(f'--- 第{rnd}轮 ---')
            b4 = cur

            new = self.search(city) - set(self.confirmed[city].keys()) - self.tried
            self._log(f'新品: {len(new)}')
            if new:
                v = self.verify_batch(city, list(new))
                self._log(f'通过: {v}')
                self.save_users(city)

            self._cookie_health_check()

            # 社交扩散
            if self.running and len(self.confirmed[city]) < self.target:
                new_users = self.expand(city)
                for nid, info in new_users.items():
                    if nid not in self.confirmed[city]:
                        self.confirmed[city][nid] = info
                        with self.lock: self.tried.add(nid)
                self.save_users(city)

            # 高限流率时额外冷却2分钟（可中断）
            if getattr(self, '_need_cooldown', False):
                self._log('[冷却] 高限流率，暂停2分钟让Cookie恢复...')
                for _ in range(24):
                    if not self.running: break
                    while self.paused: time.sleep(0.5)
                    time.sleep(5)
                self._need_cooldown = False

            cur = len(self.confirmed[city])
            if cur <= b4:
                stale += 1
                if stale >= 3: break
            else: stale = 0
            self._save()

        self.save_users(city)
        self._log(f'{city} 完成: {cur}人')

        # 采集2015微博 — 多线程并行提速
        self._log(f'\n--- {city} 2015微博采集 ({self.collect_workers}线程) ---')
        uids = [u for u in self.confirmed[city] if u not in self.collected[city]]
        random.shuffle(uids)
        self._log(f'{city}: 总{len(self.confirmed[city])} 已采{len(self.collected[city])} 待采{len(uids)}(乱序)')

        # 重载cookie + 预热session
        self._pw_init()

        total = [0]        # list包装，线程间共享
        processed = [0]
        conn_fail = [0]    # 连续API失败计数
        total_count = len(uids)
        collect_lock = threading.Lock()

        def _collect_one(uid, idx):
            """单用户采集worker（线程安全）"""
            if not self.running:
                return
            while self.paused:
                time.sleep(0.3)

            name = self.confirmed[city][uid].get('昵称', uid)
            try:
                result = self.collect_2015(uid)
                posts, api_ok = result if isinstance(result, tuple) else (result, False)
            except Exception as e:
                self._log(f'  [异常] {name}: {str(e)[:80]}')
                posts, api_ok = [], False

            with collect_lock:
                processed[0] += 1
                # 连续失败追踪
                if not api_ok and not posts:
                    conn_fail[0] += 1
                else:
                    conn_fail[0] = 0

                if len(posts) >= 12:
                    total[0] += len(posts)
                    self._log(f'[{processed[0]}/{total_count}] {name} -> {len(posts)}条 (累计{total[0]})')
                else:
                    self._log(f'[{processed[0]}/{total_count}] {name} -> {len(posts)}条 <12跳过 (累计{total[0]})')

                if posts or api_ok:
                    self.collected[city].add(uid)

                # 每20个存盘（在锁外做I/O）
                need_save = (processed[0] % 20 == 0)
                # 每50个短歇（在锁外sleep）
                need_rest = (processed[0] % 50 == 0)
                # 连续失败保护
                need_pause = conn_fail[0] >= 5

            # 锁外操作：存盘、休息、暂停
            if len(posts) >= 12:
                self.save_posts(posts, city)
            if need_save:
                self._save()
            if need_pause:
                self._log('⚠ 连续5个用户API连接失败！自动暂停...')
                self.pause()
                with collect_lock:
                    conn_fail[0] = 0
                while self.paused and self.running:
                    time.sleep(1)
                self._log('[恢复] 重载cookie + 预热...')
                self._pw_init()
                self._log('[恢复] 继续采集')
            if need_rest:
                rest = random.randint(3, 5)
                for _ in range(rest):
                    if not self.running:
                        break
                    while self.paused:
                        time.sleep(0.3)
                    time.sleep(1)

        with concurrent.futures.ThreadPoolExecutor(max_workers=self.collect_workers) as ex:
            futures = {}
            for i, uid in enumerate(uids):
                if not self.running:
                    break
                f = ex.submit(_collect_one, uid, i)
                futures[f] = uid
                time.sleep(0.05)  # 提交间隙，避免瞬间冲击

            for f in concurrent.futures.as_completed(futures):
                if not self.running:
                    break
                try:
                    f.result(timeout=300)
                except Exception as e:
                    self._log(f'[线程异常] {str(e)[:100]}')

        self._save()
        self._log(f'{city} 微博完成: {total[0]}条')

    def run(self):
        self._log(f'微博城市采集 | {CITIES} | 目标{self.target}/城')
        for city in CITIES:
            self.run_city(city)
        self._log('全部完成!')


class WeiboPostCollector(WeiboCityCrawl):
    """关键词/话题 帖子采集（滚雪球），复用 WeiboCityCrawl 的 _api 请求层。

    策略：种子关键词 → 搜帖子 → 提取 #话题# → 高频话题继续滚雪球 → 直到帖子数达标。
    帖子为主（目标 N 条），评论附带抓取（不设硬目标）。
    搜索词支持普通关键词（如"大学生穷游"）和话题标签（如"#大学生穷游#"），同一接口。
    """
    POST_FIELDS = ['搜索词', '微博id', '用户昵称', '发布时间', '微博内容',
                   '转发数', '评论数', '点赞数', '发布于', '话题标签', '微博链接']
    COMMENT_FIELDS = ['搜索词', '微博id', '评论id', '评论者昵称', '评论内容',
                      '评论时间', '评论点赞数', '评论来源']

    def __init__(self, target_posts=10000, seed_keywords=None, max_pages=30,
                 grab_comments=True, max_comments_per_post=30, output_dir='post_output',
                 snowball=True):
        super().__init__(target=target_posts)
        self.target_posts = target_posts
        self.seed_keywords = seed_keywords or []
        self.max_pages = max_pages
        self.grab_comments = grab_comments
        self.max_comments_per_post = max_comments_per_post
        self.output = output_dir
        self.snowball = snowball
        os.makedirs(self.output, exist_ok=True)
        self.seen_mids = set()               # 已抓帖子 id（去重 + 计数 + 断点续传）
        self.topics_counter = Counter()      # 话题 -> 出现次数
        self.used_queries = set()            # 已用过的搜索词
        self.total_comments = 0
        self._post_path = os.path.join(self.output, '帖子.csv')
        self._comment_path = os.path.join(self.output, '评论.csv')
        # 用独立文件名，避免与父类 WeiboCityCrawl 的 _save()（atexit 紧急存盘写 state.json）冲突
        self._state_path = os.path.join(self.output, 'post_state.json')
        self._load_state()

    # ---------- 文本工具 ----------
    @staticmethod
    def _strip_html(s):
        if not s:
            return ''
        s = str(s)
        s = re.sub(r'<br\s*/?>', '\n', s)
        s = re.sub(r'<[^>]+>', '', s)
        s = s.replace('&nbsp;', ' ').replace('&amp;', '&')
        s = s.replace('&lt;', '<').replace('&gt;', '>')
        s = s.replace('&quot;', '"').replace('&#39;', "'").replace('&apos;', "'")
        return s.strip()

    @staticmethod
    def _extract_topics(text):
        if not text:
            return []
        return re.findall(r'#([^#\s]{1,30})#', text)

    # ---------- 搜索帖子 ----------
    def search_posts(self, query):
        """按关键词/话题搜索帖子（m.weibo.cn getIndex，containerid=100103type=61 微博专用子标签）。
        query 可以是普通关键词，或 #话题# 格式。"""
        posts = []
        for page in range(1, self.max_pages + 1):
            if not self.running:
                break
            d = self._api(
                'https://m.weibo.cn/api/container/getIndex',
                {'containerid': '100103type=61&q=%s' % query,
                 'page_type': 'searchall',
                 'page': page},
                mobile=True)
            if d is None:
                break
            cards = d.get('data', {}).get('cards', [])
            if not cards:
                break
            got = 0
            for card in cards:
                if card.get('card_type') != 9:   # 只取帖子卡片，过滤话题/用户卡
                    continue
                mblog = card.get('mblog') or {}
                if mblog.get('id'):
                    posts.append(mblog)
                    got += 1
            if got == 0:
                break
            if page % 5 == 0:
                self._log(f'    [{query}] 已翻 {page} 页，累计 {len(posts)} 帖')
        return posts

    # ---------- 抓评论（附带） ----------
    def get_comments(self, mid):
        """hotflow 登录态抓评论，最多 max_comments_per_post 条"""
        result = []
        max_id = 0
        while len(result) < self.max_comments_per_post:
            d = self._api(
                'https://m.weibo.cn/comments/hotflow',
                {'id': mid, 'mid': mid, 'max_id_type': 0,
                 **({'max_id': max_id} if max_id > 0 else {})},
                mobile=True)
            if d is None:
                break
            data = d.get('data') or {}
            comments = data.get('data') or []
            if not comments:
                break
            result.extend(comments)
            max_id = data.get('max_id') or 0
            if max_id == 0:
                break
        return result[:self.max_comments_per_post]

    # ---------- 状态存取 ----------
    def _save_state(self):
        p = {'seen_mids': list(self.seen_mids),
             'topics_counter': dict(self.topics_counter),
             'used_queries': list(self.used_queries),
             'total_comments': self.total_comments}
        tmp = self._state_path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(p, f, ensure_ascii=False)
        os.replace(tmp, self._state_path)

    def _load_state(self):
        if not os.path.exists(self._state_path):
            return
        try:
            with open(self._state_path, encoding='utf-8') as f:
                p = json.load(f)
            self.seen_mids = set(p.get('seen_mids', []))
            self.topics_counter = Counter(p.get('topics_counter', {}))
            self.used_queries = set(p.get('used_queries', []))
            self.total_comments = p.get('total_comments', 0)
            self._log(f'恢复状态：已抓 {len(self.seen_mids)} 帖，评论 {self.total_comments}，话题 {len(self.topics_counter)}')
        except Exception as e:
            self._log(f'状态恢复失败: {e}')

    # ---------- CSV 导出 ----------
    def _save_posts(self, rows):
        if not rows:
            return
        ex = os.path.exists(self._post_path) and os.path.getsize(self._post_path) > 0
        with open(self._post_path, 'a+', newline='', encoding='utf-8-sig') as fh:
            w = csv.DictWriter(fh, fieldnames=self.POST_FIELDS, extrasaction='ignore')
            if not ex:
                w.writeheader()
            w.writerows(rows)

    def _save_comments(self, query, mid, comments):
        rows = []
        for c in comments:
            text = c.get('text_raw') or self._strip_html(c.get('text', ''))
            if not text:
                continue
            user = c.get('user') or {}
            rows.append({
                '搜索词': query,
                '微博id': mid,
                '评论id': c.get('id', ''),
                '评论者昵称': user.get('screen_name', ''),
                '评论内容': text,
                '评论时间': c.get('created_at', ''),
                '评论点赞数': c.get('like_count', 0),
                '评论来源': self._strip_html(c.get('source', '')),
            })
        if not rows:
            return
        ex = os.path.exists(self._comment_path) and os.path.getsize(self._comment_path) > 0
        with open(self._comment_path, 'a+', newline='', encoding='utf-8-sig') as fh:
            w = csv.DictWriter(fh, fieldnames=self.COMMENT_FIELDS, extrasaction='ignore')
            if not ex:
                w.writeheader()
            w.writerows(rows)

    # ---------- 滚雪球主循环 ----------
    def collect(self):
        queue = list(self.seed_keywords)
        self._log(f'目标帖子 {self.target_posts}，种子词 {len(queue)} 组')
        while len(self.seen_mids) < self.target_posts and self.running:
            while self.paused:
                time.sleep(0.5)
            if not queue:
                if not self.snowball:
                    self._log('种子词耗尽，停止（滚雪球已关闭）')
                    break
                # 从话题池补充高频未用话题（滚雪球核心）
                new_tags = [t for t, _ in self.topics_counter.most_common(150)
                            if t not in self.used_queries]
                if not new_tags:
                    self._log('话题池已耗尽，停止')
                    break
                queue = new_tags[:20]
                self._log(f'话题池补充 {len(queue)} 个新话题')
            query = queue.pop(0)
            if query in self.used_queries:
                continue
            self.used_queries.add(query)
            self._log(f'>>> 搜索 [{query}]（第 {len(self.used_queries)} 组）...')

            posts = self.search_posts(query)
            new_rows, new_comments = [], 0
            for p in posts:
                if not self.running:
                    break
                mid = str(p.get('id', ''))
                if not mid or mid in self.seen_mids:
                    continue
                self.seen_mids.add(mid)
                text = self._strip_html(p.get('text', ''))
                topics = self._extract_topics(text)
                for t in topics:
                    self.topics_counter[t] += 1
                user = p.get('user') or {}
                new_rows.append({
                    '搜索词': query,
                    '微博id': mid,
                    '用户昵称': user.get('screen_name', ''),
                    '发布时间': p.get('created_at', ''),
                    '微博内容': text,
                    '转发数': p.get('reposts_count', 0),
                    '评论数': p.get('comments_count', 0),
                    '点赞数': p.get('attitudes_count', 0),
                    '发布于': self._strip_html(p.get('source', '')),
                    '话题标签': ','.join(topics),
                    '微博链接': 'https://m.weibo.cn/detail/%s' % mid,
                })
                # 附带抓评论
                if self.grab_comments and (p.get('comments_count') or 0) > 0:
                    comments = self.get_comments(mid)
                    if comments:
                        self._save_comments(query, mid, comments)
                        new_comments += len(comments)
                        self.total_comments += len(comments)
                if len(self.seen_mids) >= self.target_posts:
                    break

            if new_rows:
                self._save_posts(new_rows)
            self._save_state()
            self._log(f'[{query}] 新增 {len(new_rows)} 帖 + {new_comments} 评论 | '
                      f'累计帖 {len(self.seen_mids)} 评论 {self.total_comments} 话题 {len(self.topics_counter)}')

        self._log(f'== 完成：帖子 {len(self.seen_mids)}，评论 {self.total_comments} ==')
        self._log(f'帖子文件: {self._post_path}')
        self._log(f'评论文件: {self._comment_path}')


if __name__ == '__main__':
    # 默认城市采集；帖子采集请用 GUI 模块④ 或手动：
    #   WeiboPostCollector(target_posts=10000, seed_keywords=['大学生穷游','穷游','青旅']).collect()
    WeiboCityCrawl(target=10000).run()
