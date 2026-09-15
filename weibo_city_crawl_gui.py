"""微博城市用户采集 — 三功能独立控制"""
import tkinter as tk
from tkinter import ttk, messagebox
import threading, subprocess, os, json, requests, time, random, re
from weibo_city_crawl import WeiboCityCrawl, CITIES, load_cookie


class App:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title('微博城市用户采集 v4.2')
        self.root.geometry('750x720')
        self.root.minsize(700, 640)
        self.crawler = None
        self.running = False
        self.auto_health = tk.BooleanVar(value=True)

        # == 设置 ==
        f1 = ttk.LabelFrame(self.root, text='采集设置', padding=10)
        f1.pack(fill='x', padx=10, pady=5)

        ttk.Label(f1, text='目标城市:', font=('微软', 10)).grid(row=0, column=0, sticky='w')
        cf = ttk.Frame(f1)
        cf.grid(row=0, column=1, columnspan=3, sticky='w', padx=5)
        self.city_vars = {}
        for c in CITIES:
            v = tk.BooleanVar(value=True)
            self.city_vars[c] = v
            ttk.Checkbutton(cf, text=c, variable=v).pack(side='left', padx=5)

        ttk.Label(f1, text='每城目标:', font=('微软', 10)).grid(row=1, column=0, sticky='w', pady=3)
        self.target_entry = ttk.Entry(f1, width=10, font=('微软', 10))
        self.target_entry.grid(row=1, column=1, sticky='w', padx=5, pady=3)
        self.target_entry.insert(0, '10000')

        ttk.Label(f1, text='请求间隔(秒):', font=('微软', 10)).grid(row=1, column=2, sticky='w', pady=3)
        self.wait_entry = ttk.Entry(f1, width=6, font=('微软', 10))
        self.wait_entry.grid(row=1, column=3, sticky='w', padx=5, pady=3)
        self.wait_entry.insert(0, '2')

        ttk.Label(f1, text='搜索线程:', font=('微软', 10)).grid(row=1, column=4, sticky='w', pady=3, padx=(15,0))
        self.workers_entry = ttk.Entry(f1, width=4, font=('微软', 10))
        self.workers_entry.grid(row=1, column=5, sticky='w', padx=5, pady=3)
        self.workers_entry.insert(0, '5')

        # Cookie状态行
        bf0 = ttk.Frame(f1)
        bf0.grid(row=2, column=0, columnspan=4, pady=5)
        self.btn_cookie = ttk.Button(bf0, text='🔄 刷新Cookie', command=self.refresh_cookie, width=12)
        self.btn_cookie.pack(side='left', padx=5)
        self.cookie_status = ttk.Label(bf0, text='', font=('微软', 9), foreground='gray')
        self.cookie_status.pack(side='left', padx=10)
        ttk.Checkbutton(bf0, text='自动健康检查(每15分钟)', variable=self.auto_health).pack(side='left', padx=10)
        self.check_cookie()
        self._start_health_thread()

        # == 全局控制（暂停/恢复/停止）==
        f_ctrl = ttk.Frame(self.root)
        f_ctrl.pack(fill='x', padx=10, pady=3)
        ttk.Label(f_ctrl, text='全局控制:', font=('微软', 9, 'bold')).pack(side='left', padx=5)
        self.btn_pause = ttk.Button(f_ctrl, text='⏸ 暂停', command=self.do_pause, width=8, state='disabled')
        self.btn_pause.pack(side='left', padx=3)
        self.btn_resume = ttk.Button(f_ctrl, text='▶ 恢复', command=self.do_resume, width=8, state='disabled')
        self.btn_resume.pack(side='left', padx=3)
        self.btn_stop_all = ttk.Button(f_ctrl, text='■ 全部停止', command=self.stop_all, width=10, state='disabled')
        self.btn_stop_all.pack(side='left', padx=3)
        self.pause_status = ttk.Label(f_ctrl, text='', font=('微软', 9), foreground='gray')
        self.pause_status.pack(side='left', padx=10)

        # == 三个功能按钮 ==
        f2 = ttk.LabelFrame(self.root, text='功能模块', padding=10)
        f2.pack(fill='x', padx=10, pady=5)

        # 模块1: 关键词搜索+验证
        m1 = ttk.Frame(f2)
        m1.pack(fill='x', pady=3)
        ttk.Label(m1, text='① 搜索+验证', font=('微软', 11, 'bold')).pack(side='left', padx=5)
        ttk.Label(m1, text='关键词搜索用户 → API验证所在地 (14字段用户CSV)', font=('微软', 9), foreground='gray').pack(side='left', padx=5)
        self.btn_search = ttk.Button(m1, text='▶ 开始', command=self.start_search, width=8)
        self.btn_search.pack(side='right', padx=5)
        self.btn_s1_stop = ttk.Button(m1, text='■', command=self.stop_all, width=3, state='disabled')
        self.btn_s1_stop.pack(side='right')

        # 模块2: 社交扩散
        m2 = ttk.Frame(f2)
        m2.pack(fill='x', pady=3)
        ttk.Label(m2, text='② 社交扩散', font=('微软', 11, 'bold')).pack(side='left', padx=5)
        ttk.Label(m2, text='从关注列表扩展同城用户 (需先有种子用户)', font=('微软', 9), foreground='gray').pack(side='left', padx=5)
        self.btn_expand = ttk.Button(m2, text='▶ 开始', command=self.start_expand, width=8)
        self.btn_expand.pack(side='right', padx=5)
        self.btn_s2_stop = ttk.Button(m2, text='■', command=self.stop_all, width=3, state='disabled')
        self.btn_s2_stop.pack(side='right')

        # 模块3: 2015微博采集
        m3 = ttk.Frame(f2)
        m3.pack(fill='x', pady=3)
        ttk.Label(m3, text='③ 2015微博采集', font=('微软', 11, 'bold')).pack(side='left', padx=5)
        ttk.Label(m3, text='对已确认用户采集2015年微博 (11字段微博CSV)', font=('微软', 9), foreground='gray').pack(side='left', padx=5)
        self.btn_collect = ttk.Button(m3, text='▶ 开始', command=self.start_collect, width=8)
        self.btn_collect.pack(side='right', padx=5)
        self.btn_s3_stop = ttk.Button(m3, text='■', command=self.stop_all, width=3, state='disabled')
        self.btn_s3_stop.pack(side='right')

        # == 模块④: 关键词/话题搜帖子（滚雪球）==
        f_post = ttk.LabelFrame(self.root, text='④ 帖子采集（关键词 → 话题滚雪球）', padding=10)
        f_post.pack(fill='x', padx=10, pady=5)

        prow1 = ttk.Frame(f_post)
        prow1.pack(fill='x', pady=2)
        ttk.Label(prow1, text='关键词/话题:', font=('微软', 10)).pack(side='left', anchor='n')
        ttk.Label(prow1, text='一行一个，支持 #话题#', font=('微软', 8), foreground='gray').pack(side='left', padx=5, anchor='n')
        self.kw_text = tk.Text(prow1, height=12, font=('微软', 10))
        self.kw_text.pack(side='left', fill='x', expand=True, padx=5)
        self.kw_text.insert('1.0', '大学生穷游\n穷游\n穷游攻略\n学生党穷游\n穷游省钱\n穷游路线\n毕业旅行\n毕业穷游\ngap year\n义工旅行\n独自旅行\n一个人旅行\n闺蜜旅行\n宿舍旅行\n说走就走\n暑假旅行\n西藏穷游\n新疆穷游\n云南穷游\n川西穷游\n青海穷游\n甘肃穷游\n大理穷游\n丽江穷游\n拉萨穷游\n香格里拉穷游\n贵州穷游\n西北大环线\n西安穷游\n成都穷游\n重庆穷游\n北京穷游\n上海穷游\n杭州穷游\n苏州穷游\n南京穷游\n长沙穷游\n武汉穷游\n桂林穷游\n张家界穷游\n三亚穷游\n厦门穷游\n青岛穷游\n大连穷游\n北海穷游\n海南穷游\n火车硬座\n绿皮火车\n拼车旅行\n顺风车旅行\n骑行穷游\n骑行川藏线\n徒步旅行\n搭车旅行\n青旅\n青年旅舍\n沙发客\n民宿穷游\n露营旅行\n穷游住宿\n学生证优惠\n学生证半价\n免费景点\n低价机票\n特价机票\n穷游交通\n穷游吃饭\n预算旅行\n穷游搭子\n旅游搭子\n拼车拼房\n结伴旅行\n找旅伴\n搭子旅游\n#穷游#\n#旅行#\n#大学生旅游#\n#毕业旅行#\n#说走就走的旅行#\n#青旅#')

        prow2 = ttk.Frame(f_post)
        prow2.pack(fill='x', pady=3)
        ttk.Label(prow2, text='目标帖子:', font=('微软', 10)).pack(side='left')
        self.post_target_entry = ttk.Entry(prow2, width=8, font=('微软', 10))
        self.post_target_entry.pack(side='left', padx=5)
        self.post_target_entry.insert(0, '10000')
        ttk.Label(prow2, text='每词页数:', font=('微软', 10)).pack(side='left', padx=(15, 0))
        self.post_pages_entry = ttk.Entry(prow2, width=5, font=('微软', 10))
        self.post_pages_entry.pack(side='left', padx=5)
        self.post_pages_entry.insert(0, '30')
        self.post_progress = ttk.Label(prow2, text='', font=('微软', 9), foreground='gray')
        self.post_progress.pack(side='right', padx=10)
        self.btn_post_stop = ttk.Button(prow2, text='■', command=self.stop_all, width=3, state='disabled')
        self.btn_post_stop.pack(side='right')
        self.btn_post = ttk.Button(prow2, text='▶ 开始采集帖子', command=self.start_post_collect, width=14)
        self.btn_post.pack(side='right', padx=5)

        # == 进度 ==
        f3 = ttk.LabelFrame(self.root, text='采集进度', padding=10)
        f3.pack(fill='x', padx=10, pady=5)
        self.progress = {}
        for i, c in enumerate(CITIES):
            ttk.Label(f3, text=f'{c}:', font=('微软', 10, 'bold')).grid(row=i, column=0, sticky='w')
            lbl = ttk.Label(f3, text='待开始', font=('微软', 10), foreground='gray')
            lbl.grid(row=i, column=1, sticky='w', padx=5)
            self.progress[c] = lbl

        # == 日志 ==
        f4 = ttk.LabelFrame(self.root, text='运行日志', padding=5)
        f4.pack(expand=True, fill='both', padx=10, pady=5)
        self.log = tk.Text(f4, height=14, font=('Consolas', 9), wrap='word')
        self.log.pack(side='left', expand=True, fill='both')
        sb = ttk.Scrollbar(f4, command=self.log.yview)
        sb.pack(side='right', fill='y')
        self.log.configure(yscrollcommand=sb.set)

        tk.Label(self.root, text='微博城市用户采集 v4.2 | 14字段用户 + 11字段微博 | weibo.com',
                 font=('仿宋', 9), fg='gray').pack(side='bottom', pady=3)

    # == 日志 & 进度 ==
    def writelog(self, msg):
        t = time.strftime('%H:%M:%S')
        self.root.after(0, lambda: self.log.insert('end', f'[{t}] {msg}\n'))
        self.root.after(0, lambda: self.log.see('end'))

    def update_progress(self, city, users, posts):
        def _do():
            if posts > 0:
                self.progress[city].config(text=f'已发现{users}人 | 已采集{posts}条2015微博', foreground='green')
            elif users > 0:
                self.progress[city].config(text=f'已发现{users}人', foreground='blue')
            else:
                self.progress[city].config(text='采集中...', foreground='orange')
        self.root.after(0, _do)

    # == Cookie ==
    def check_cookie(self):
        try:
            for p in ['cookie.txt', '../cookie.txt']:
                if os.path.exists(p):
                    with open(p, encoding='utf-8') as f:
                        c = f.read().strip()
                    h = {'User-Agent': 'Mozilla/5.0', 'Cookie': c,
                         'X-Requested-With': 'XMLHttpRequest', 'Accept': 'application/json',
                         'Referer': 'https://weibo.com/'}
                    r = requests.get('https://weibo.com/ajax/profile/info?uid=0', headers=h, timeout=10)
                    if r.json().get('ok') == 1:
                        self.cookie_status.config(text='✅ Cookie有效', foreground='green')
                        return
            self.cookie_status.config(text='❌ Cookie过期', foreground='red')
        except:
            self.cookie_status.config(text='⚠ 检测失败', foreground='orange')

    def refresh_cookie(self):
        self.writelog('刷新Cookie...')
        script = os.path.join(os.path.dirname(__file__), 'refresh_cookie.py')
        if not os.path.exists(script):
            self.writelog('找不到refresh_cookie.py')
            return
        try:
            r = subprocess.run(['python', script], capture_output=True, text=True, timeout=60)
            self.writelog(f'结果: {r.stdout.strip()}')
            self.check_cookie()
        except Exception as e:
            self.writelog(f'失败: {e}')

    def _start_health_thread(self):
        """后台线程：每15分钟自动检测cookie健康"""
        def health_loop():
            while True:
                time.sleep(900)  # 15分钟（v4.3提速）
                if not self.auto_health.get():
                    continue
                if self.crawler and self.crawler.running:
                    try:
                        # 只重载cookie文件，不调playwright
                        self.crawler.mobile_cookie = load_cookie(mobile=True)
                        self.crawler.cookie = load_cookie()
                        self.root.after(0, self.check_cookie)
                        self.writelog('[自动] Cookie已重载')
                    except Exception as e:
                        self.writelog(f'[自动] 健康检查异常: {e}')
        t = threading.Thread(target=health_loop, daemon=True)
        t.start()

    # == 暂停/恢复 ==
    def do_pause(self):
        if self.crawler:
            self.crawler.pause()
            # 暂停时自动存盘
            try:
                for city in self.crawler.cities:
                    self.crawler.save_users(city)
                self.crawler._save()
            except: pass
            self._sync_button_state()

    def do_resume(self):
        if self.crawler:
            self.crawler.resume()
            self._sync_button_state()

    def _sync_button_state(self):
        """根据crawler.paused状态同步按钮（kernel回调也会触发）"""
        if self.crawler and self.crawler.paused:
            self.btn_pause.config(state='disabled')
            self.btn_resume.config(state='normal')
            self.pause_status.config(text='⏸ 已暂停 — 点击"▶ 恢复"继续', foreground='orange')
        else:
            self.btn_resume.config(state='disabled')
            self.btn_pause.config(state='normal')
            self.pause_status.config(text='▶ 运行中', foreground='green')

    # == 线程管理 ==
    def _get_crawler(self, cities, target, wait, workers=5):
        c = WeiboCityCrawl(target=target)
        c.wait = wait
        c.search_workers = workers
        c.cities = cities
        c.running = True
        orig = c._log

        def gui_log(msg):
            self.writelog(msg)
            orig(msg)
        c._log = gui_log
        # 注册pause回调：内核触发暂停时（如验证码），通知GUI启用恢复按钮
        c._on_pause_cb = lambda: self.root.after(0, self._sync_button_state)
        return c

    _phase_lock = threading.Lock()

    def _run_phase(self, phase_name, cities, target, wait, func, enable_btns, disable_btns):
        """统一执行入口（防双击）"""
        if not self._phase_lock.acquire(blocking=False):
            messagebox.showwarning('提示', '有任务正在启动，请稍候')
            return
        try:
            if self.running:
                messagebox.showwarning('提示', '有任务正在运行，请先停止')
                return
            self.running = True
        except:
            self._phase_lock.release()
            raise
        self.btn_pause.config(state='normal')
        self.btn_resume.config(state='disabled')
        self.btn_stop_all.config(state='normal')
        self.pause_status.config(text='▶ 运行中', foreground='green')
        for b in enable_btns:
            b.config(state='normal')
        for b in disable_btns:
            b.config(state='disabled')

        def run():
            try:
                func()
            except Exception as e:
                self.writelog(f'[异常] {e}')
            finally:
                self.running = False
                self._phase_lock.release()
                self.root.after(0, lambda: self._reset_btns())

        threading.Thread(target=run, daemon=True).start()

    def _reset_btns(self):
        self.btn_search.config(state='normal')
        self.btn_expand.config(state='normal')
        self.btn_collect.config(state='normal')
        self.btn_s1_stop.config(state='disabled')
        self.btn_s2_stop.config(state='disabled')
        self.btn_s3_stop.config(state='disabled')
        self.btn_post.config(state='normal')
        self.btn_post_stop.config(state='disabled')
        self.btn_pause.config(state='disabled')
        self.btn_resume.config(state='disabled')
        self.btn_stop_all.config(state='disabled')
        self.pause_status.config(text='')

    def stop_all(self):
        if self.crawler:
            self.crawler.running = False
            # 强制存盘，防止数据丢失
            try:
                for city in self.crawler.cities:
                    self.crawler.save_users(city)
                self.crawler._save()
                self.writelog('[已保存进度]')
            except:
                pass
        self.running = False
        self.writelog('[停止]')
        self._reset_btns()

    # == 模块1: 关键词搜索+验证 ==
    def start_search(self):
        cities = [c for c in CITIES if self.city_vars[c].get()]
        if not cities: messagebox.showwarning('', '至少选一个城市'); return
        try: target = int(self.target_entry.get())
        except: messagebox.showwarning('', '目标数为整数'); return
        try: wait = float(self.wait_entry.get())
        except: wait = 2
        try: workers = int(self.workers_entry.get())
        except: workers = 5

        self.writelog('=== 模块1: 关键词搜索+验证 (14字段) ===')
        crawler = self._get_crawler(cities, target, wait, workers)
        self.crawler = crawler

        def do():
            for city in cities:
                if not crawler.running: break
                self.writelog(f'\n--- {city} ---')
                crawler._load()
                crawler._cookie_health_check()
                cur = len(crawler.confirmed[city])
                self.writelog(f'已有: {cur}人')
                self.update_progress(city, cur, 0)
                rnd = 0
                stale = 0
                while crawler.running and len(crawler.confirmed[city]) < target:
                    while crawler.paused: time.sleep(0.5)
                    rnd += 1
                    b4 = len(crawler.confirmed[city])
                    self.writelog(f'第{rnd}轮...')
                    new = crawler.search(city) - set(crawler.confirmed[city].keys()) - crawler.tried
                    self.writelog(f'新品: {len(new)}')
                    if new:
                        v = crawler.verify_batch(city, list(new))
                        self.writelog(f'通过: {v}')
                        crawler.save_users(city)
                    cur = len(crawler.confirmed[city])
                    self.update_progress(city, cur, 0)
                    crawler._save()
                    if cur <= b4:
                        stale += 1
                        if stale >= 3: break
                    else: stale = 0
                crawler.save_users(city)
                self.writelog(f'{city} 完成: {cur}人')

        self._run_phase('search', cities, target, wait, do,
                        [self.btn_s1_stop], [self.btn_search, self.btn_expand, self.btn_collect])

    # == 模块2: 社交扩散 ==
    def start_expand(self):
        cities = [c for c in CITIES if self.city_vars[c].get()]
        if not cities: messagebox.showwarning('', '至少选一个城市'); return
        try: target = int(self.target_entry.get())
        except: messagebox.showwarning('', '目标数为整数'); return
        try: wait = float(self.wait_entry.get())
        except: wait = 2

        self.writelog('=== 模块2: 社交扩散 (14字段) ===')
        crawler = self._get_crawler(cities, target, wait)
        self.crawler = crawler

        def do():
            # 社交扩散已改用PC关注API，不需要移动cookie
            for city in cities:
                if not crawler.running: break
                crawler._load()
                crawler._cookie_health_check()
                cur = len(crawler.confirmed[city])
                self.writelog(f'{city}: 种子{cur}人')
                self.update_progress(city, cur, 0)
                if cur == 0:
                    self.writelog(f'{city}: 无种子用户，跳过')
                    continue
                st = 0
                stale = 0
                while crawler.running and len(crawler.confirmed[city]) < target:
                    while crawler.paused: time.sleep(0.5)
                    st += 1
                    b4 = len(crawler.confirmed[city])
                    self.writelog(f'第{st}轮(已扩散{len(crawler._expanded_seeds)}种子)...')
                    new = crawler.expand(city)
                    if not new and len(crawler._expanded_seeds) >= len(crawler.confirmed[city]):
                        self.writelog('所有种子已扩散完毕')
                        break
                    for nid, info in new.items():
                        if nid not in crawler.confirmed[city]:
                            crawler.confirmed[city][nid] = info
                            crawler.tried.add(nid)
                    crawler.save_users(city)
                    cur = len(crawler.confirmed[city])
                    self.writelog(f'新增: {cur-b4}, 累计: {cur}')
                    self.update_progress(city, cur, 0)
                    crawler._save()
                    if cur <= b4:
                        stale += 1
                        if stale >= 10: break
                    else:
                        stale = 0
                    # 高-100率时额外冷却2分钟（可中断）
                    if getattr(crawler, '_need_cooldown', False):
                        self.writelog('[冷却] 高-100率，暂停2分钟让Cookie恢复...')
                        for _ in range(24):
                            if not crawler.running: break
                            while crawler.paused: time.sleep(0.5)
                            time.sleep(5)
                    time.sleep(wait)

        self._run_phase('expand', cities, target, wait, do,
                        [self.btn_s2_stop], [self.btn_search, self.btn_expand, self.btn_collect])

    # == 模块3: 2015微博采集 ==
    def start_collect(self):
        cities = [c for c in CITIES if self.city_vars[c].get()]
        if not cities: messagebox.showwarning('', '至少选一个城市'); return
        try: target = int(self.target_entry.get())
        except: messagebox.showwarning('', '目标数为整数'); return
        try: wait = float(self.wait_entry.get())
        except: wait = 2

        self.writelog('=== 模块3: 2015微博采集 (11字段) ===')
        crawler = self._get_crawler(cities, target, wait)
        self.crawler = crawler

        def do():
            import concurrent.futures
            # 重载cookie + 预热session（纯requests，不碰Playwright）
            crawler._pw_init()

            for city in cities:
                if not crawler.running: break
                crawler._load()
                conf = list(crawler.confirmed[city].items())
                coll = crawler.collected[city]
                todo = [(u, i) for u, i in conf if u not in coll]
                random.shuffle(todo)
                self.writelog(f'{city}: 总{len(conf)} 已采{len(coll)} 待采{len(todo)}(乱序)')
                self.update_progress(city, len(conf), 0)
                tp = [0]  # 用list包装以便在闭包中修改
                done = [0]
                total = len(todo)
                lock = threading.Lock()

                def collect_one(uid_info):
                    uid, info = uid_info
                    if not crawler.running: return
                    while crawler.paused: time.sleep(0.3)
                    name = info.get('昵称', uid)
                    try:
                        result = crawler.collect_2015(uid)
                        posts, api_ok = result if isinstance(result, tuple) else (result, False)
                    except Exception as e:
                        self.writelog(f'[异常] {name}: {str(e)[:80]}')
                        posts, api_ok = [], False

                    with lock:
                        done[0] += 1
                        if len(posts) >= 12:
                            tp[0] += len(posts)
                            self.writelog(f'[{done[0]}/{total}] {name} -> {len(posts)}条 (累计{tp[0]})')
                        else:
                            self.writelog(f'[{done[0]}/{total}] {name} -> {len(posts)}条 <12跳过 (累计{tp[0]})')
                        if posts or api_ok: crawler.collected[city].add(uid)
                        self.update_progress(city, len(conf), tp[0])
                        need_save = (done[0] % 10 == 0)
                        need_rest = (done[0] % 50 == 0)

                    # 锁外执行：避免锁内I/O阻塞其他线程
                    if len(posts) >= 12:
                        crawler.save_posts(posts, city)
                    if need_save:
                        crawler._save()
                    if need_rest:
                        rest = random.randint(3, 5)
                        self.writelog(f'[休息] 已处理{done[0]}个，暂停{rest}s...')
                        for _ in range(rest):
                            if not crawler.running: break
                            while crawler.paused: time.sleep(0.3)
                            time.sleep(1)

                # 多线程并行采集
                with concurrent.futures.ThreadPoolExecutor(max_workers=crawler.collect_workers) as ex:
                    futures = {}
                    for uid_info in todo:
                        if not crawler.running: break
                        f = ex.submit(collect_one, uid_info)
                        futures[f] = uid_info[0]
                        time.sleep(0.05)
                    for f in concurrent.futures.as_completed(futures):
                        if not crawler.running: break
                        try:
                            f.result(timeout=300)
                        except Exception as e:
                            self.writelog(f'[线程异常] {str(e)[:100]}')

                crawler._save()
                self.writelog(f'{city} 完成: {tp[0]}条')

        self._run_phase('collect', cities, target, wait, do,
                        [self.btn_s3_stop], [self.btn_search, self.btn_expand, self.btn_collect])

    # == 模块④: 帖子采集 ==
    def _get_post_collector(self, target, kws, pages):
        from weibo_city_crawl import WeiboPostCollector
        c = WeiboPostCollector(target_posts=target, seed_keywords=kws, max_pages=pages,
                               grab_comments=True, max_comments_per_post=30)
        c.running = True
        orig = c._log

        def gui_log(msg):
            self.writelog(msg)
            orig(msg)
            m = re.search(r'累计帖 (\d+) 评论 (\d+)', msg)
            if m:
                self.root.after(0, lambda: self.post_progress.config(
                    text=f'帖子 {m.group(1)} / 评论 {m.group(2)}', foreground='blue'))
        c._log = gui_log
        c._on_pause_cb = lambda: self.root.after(0, self._sync_button_state)
        return c

    def start_post_collect(self):
        kws = [l.strip() for l in self.kw_text.get('1.0', 'end').splitlines() if l.strip()]
        if not kws:
            messagebox.showwarning('', '至少填一个关键词'); return
        try:
            target = int(self.post_target_entry.get())
        except:
            messagebox.showwarning('', '目标帖子数为整数'); return
        try:
            pages = int(self.post_pages_entry.get())
        except:
            pages = 30

        self.writelog('=== 模块④: 关键词/话题搜帖子（滚雪球）===')
        crawler = self._get_post_collector(target, kws, pages)
        self.crawler = crawler

        def do():
            crawler.collect()
            self.root.after(0, lambda: self.post_progress.config(
                text=f'完成：帖子 {len(crawler.seen_mids)} / 评论 {crawler.total_comments}', foreground='green'))

        self._run_phase('post', [], target, 2, do,
                        [self.btn_post_stop],
                        [self.btn_post, self.btn_search, self.btn_expand, self.btn_collect])

    def run(self):
        self.root.mainloop()


if __name__ == '__main__':
    App().run()
