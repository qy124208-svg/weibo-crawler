"""
微博关键词搜索 + 评论采集 — 满足暑假作业第6章文本挖掘需求：
(1) 关键词搜索微博帖子（含长文正文展开）
(2) 抓取每条帖子的评论
(3) 目标 200-300 条评论，够了自动停

用法: python weibo_search_comments.py
      可选传关键词: python weibo_search_comments.py "穷游拼车,青旅安全吗,学生穷游"

复用 weibo_city_crawl.py 的 cookie / 请求头 / 时间解析，不修改核心引擎。
"""
import time, random, os, re, json, csv, sys
import requests

# 复用核心工具函数（模块级无副作用，安全）
from weibo_city_crawl import load_cookie, _browser_headers, parse_time, _extract_xsrf

# ==================== 配置区 ====================
# 默认关键词（暑假作业 6 组）。若命令行传了参数，则用命令行关键词覆盖。
KEYWORDS = ["大学生穷游", "穷游搭子", "拼车拼房", "学生证优惠", "穷游攻略", "AI做攻略"]

MAX_NOTES_PER_KEYWORD = 30    # 每组关键词搜多少条帖子
MAX_COMMENTS_PER_NOTE = 50    # 每条帖子最多抓多少条评论
TARGET_COMMENTS = 250         # 目标评论总数（200-300 之间）
REQUEST_DELAY_MIN = 1.0       # 请求间隔下限（秒）
REQUEST_DELAY_MAX = 6.0       # 请求间隔上限（秒）
OUTPUT_DIR = "search_output"  # 输出目录
# ================================================


def _strip_html(s):
    """清洗微博返回的 HTML 文本为纯文本：<br>→换行，去掉其余标签，还原实体"""
    if not s:
        return ""
    s = str(s)
    s = re.sub(r'<br\s*/?>', '\n', s)                     # 换行
    s = re.sub(r'<[^>]+>', '', s)                          # 去掉所有标签
    s = s.replace('&nbsp;', ' ').replace('&amp;', '&')     # 实体还原
    s = s.replace('&lt;', '<').replace('&gt;', '>')
    s = s.replace('&quot;', '"').replace('&#39;', "'").replace('&apos;', "'")
    return s.strip()


def _extract_topics(text):
    """从纯文本中提取 #话题# 标签"""
    if not text:
        return ""
    topics = re.findall(r'#([^#\s]+)#', text)
    return ",".join(topics) if topics else ""


class WeiboSearchComments:
    def __init__(self, keywords):
        self.keywords = keywords
        self.mobile_cookie = load_cookie(mobile=True)
        self.session = requests.Session()
        self.session.trust_env = False  # 忽略系统代理，避免连接干扰
        self._delay = REQUEST_DELAY_MIN
        self._posts_done = set()        # 已处理帖子 id（去重 + 断点续传）
        self._total_comments = 0
        self.output = OUTPUT_DIR
        os.makedirs(self.output, exist_ok=True)
        self._post_path = os.path.join(self.output, "帖子.csv")
        self._comment_path = os.path.join(self.output, "评论.csv")
        self._state_path = os.path.join(self.output, "state.json")
        self._load_state()
        self._log("移动Cookie: %s" % ("有" if self.mobile_cookie else "无（请先跑 playwright_login.py）"))

    # ---------- 基础 ----------
    def _log(self, msg):
        t = time.strftime("%H:%M:%S")
        print(f"[{t}] {msg}")

    def _adaptive_sleep(self, was_rate_limited=False):
        """正常逐步加速，被限逐步减速"""
        if was_rate_limited:
            self._delay = min(self._delay * 2, REQUEST_DELAY_MAX)
        else:
            self._delay = max(self._delay * 0.9, REQUEST_DELAY_MIN)
        time.sleep(self._delay)

    def _api_get(self, url, params=None, referer=None):
        """移动端请求层：cookie + 真实请求头 + 自适应延迟 + 限流处理"""
        for _ in range(2):
            h = _browser_headers(mobile=True, cookie=self.mobile_cookie)
            h["Cookie"] = self.mobile_cookie
            h["X-Requested-With"] = "XMLHttpRequest"
            if referer:
                h["Referer"] = referer
            try:
                r = self.session.get(url, headers=h, params=params, timeout=15)
                if r.status_code == 200:
                    d = r.json()
                    ok_val = d.get("ok")
                    if ok_val == 1:
                        self._adaptive_sleep(was_rate_limited=False)
                        return d
                    elif ok_val == 0:
                        return None
                    elif ok_val == -100:
                        self._log("[!] Cookie 失效(ok=-100)，请运行: python playwright_login.py 后重启")
                        return None
                    else:
                        cap = d.get("url", "")
                        if "captcha" in cap:
                            self._log("[验证码] 触发验证码，请手动打开 https://m.weibo.cn/ 完成滑块后重启")
                            return None
                        self._log("API ok=%s %s" % (ok_val, url[:50]))
                        self._adaptive_sleep(was_rate_limited=True)
                        return None
                elif r.status_code == 429:
                    self._log("HTTP429 限流，退避...")
                    self._adaptive_sleep(was_rate_limited=True)
                elif r.status_code in (418, 403):
                    self._log("HTTP%s 拦截，等待 60s..." % r.status_code)
                    time.sleep(60)
                    self._adaptive_sleep(was_rate_limited=True)
                elif r.status_code in (500, 502, 503):
                    self._log("HTTP%s 服务器错误，重试..." % r.status_code)
                    self._adaptive_sleep(was_rate_limited=True)
                else:
                    self._log("HTTP%s %s" % (r.status_code, url[:50]))
                    self._adaptive_sleep(was_rate_limited=True)
            except Exception as e:
                self._log("网络异常: %s" % str(e)[:50])
                self._adaptive_sleep(was_rate_limited=True)
        return None

    # ---------- 搜索帖子 ----------
    def search_posts(self, keyword, max_notes):
        """按关键词搜索微博帖子（m.weibo.cn getIndex，containerid=100103type=1）"""
        posts = []
        page = 1
        while len(posts) < max_notes and page <= 50:
            d = self._api_get(
                "https://m.weibo.cn/api/container/getIndex",
                params={
                    "containerid": "100103type=1&q=%s" % keyword,
                    "page_type": "searchall",
                    "page": page,
                },
                referer="https://m.weibo.cn/",
            )
            if d is None:
                break
            cards = d.get("data", {}).get("cards", [])
            if not cards:
                break
            got = 0
            for card in cards:
                if card.get("card_type") != 9:   # 只取帖子卡片，过滤话题/用户卡
                    continue
                mblog = card.get("mblog") or {}
                mid = mblog.get("id")
                if not mid:
                    continue
                posts.append(mblog)
                got += 1
            if got == 0:
                break
            page += 1
            # 翻页后稍作停顿
            time.sleep(random.uniform(0.5, 1.0))
        return posts

    # ---------- 长文展开 ----------
    def get_full_text(self, mid):
        """长微博 isLongText=True 时，用 statuses/extend 取全文"""
        d = self._api_get(
            "https://m.weibo.cn/statuses/extend",
            params={"id": mid},
            referer="https://m.weibo.cn/detail/%s" % mid,
        )
        if d and d.get("data", {}).get("longTextContent"):
            return _strip_html(d["data"]["longTextContent"])
        return None

    # ---------- 抓评论 ----------
    def get_comments(self, mid, max_comments):
        """hotflow 登录态翻页抓评论；失败时回退 api/comments/show（无 cookie，上限约50）"""
        result = []
        max_id = 0
        while len(result) < max_comments:
            d = self._api_get(
                "https://m.weibo.cn/comments/hotflow",
                params={"id": mid, "mid": mid, "max_id_type": 0,
                        **({"max_id": max_id} if max_id > 0 else {})},
                referer="https://m.weibo.cn/detail/%s" % mid,
            )
            if d is None:
                break
            data = d.get("data") or {}
            comments = data.get("data") or []
            if not comments:
                break
            result.extend(comments)
            max_id = data.get("max_id") or 0
            if max_id == 0:
                break
        if not result:
            # 回退：无 cookie 老接口（最多约 50 条）
            result = self._get_comments_nocookie(mid, max_comments)
        return result[:max_comments]

    def _get_comments_nocookie(self, mid, max_comments):
        result = []
        page = 1
        while len(result) < max_comments and page <= 10:
            d = self._api_get(
                "https://m.weibo.cn/api/comments/show",
                params={"id": mid, "page": page},
                referer="https://m.weibo.cn/detail/%s" % mid,
            )
            if d is None:
                break
            data = d.get("data") or {}
            comments = data.get("data") or []
            if not comments:
                break
            result.extend(comments)
            max_page = data.get("max") or 0
            if max_page and page >= max_page:
                break
            page += 1
        return result

    # ---------- 状态存取 ----------
    def _load_state(self):
        if os.path.exists(self._state_path):
            try:
                with open(self._state_path, encoding="utf-8") as f:
                    p = json.load(f)
                self._posts_done = set(p.get("posts_done", []))
                self._total_comments = p.get("total_comments", 0)
            except Exception:
                pass

    def _save_state(self):
        p = {"posts_done": list(self._posts_done), "total_comments": self._total_comments}
        tmp = self._state_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(p, f, ensure_ascii=False)
        os.replace(tmp, self._state_path)

    # ---------- CSV 导出 ----------
    def _save_post(self, keyword, mid, info):
        f = self._post_path
        fields = ["关键词", "微博id", "用户昵称", "发布时间", "微博内容",
                  "转发数", "评论数", "点赞数", "发布于", "话题标签", "微博链接"]
        ex = os.path.exists(f) and os.path.getsize(f) > 0
        with open(f, "a+", newline="", encoding="utf-8-sig") as fh:
            w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
            if not ex:
                w.writeheader()
            w.writerow(info)

    def _save_comments(self, keyword, mid, comments):
        f = self._comment_path
        fields = ["关键词", "微博id", "评论id", "评论者昵称", "评论内容",
                  "评论时间", "评论点赞数", "评论来源"]
        rows = []
        for c in comments:
            text = c.get("text_raw") or _strip_html(c.get("text", ""))
            if not text:
                continue
            user = c.get("user") or {}
            rows.append({
                "关键词": keyword,
                "微博id": mid,
                "评论id": c.get("id", ""),
                "评论者昵称": user.get("screen_name", ""),
                "评论内容": text,
                "评论时间": c.get("created_at", ""),
                "评论点赞数": c.get("like_count", 0),
                "评论来源": _strip_html(c.get("source", "")),
            })
        if not rows:
            return
        ex = os.path.exists(f) and os.path.getsize(f) > 0
        with open(f, "a+", newline="", encoding="utf-8-sig") as fh:
            w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
            if not ex:
                w.writeheader()
            w.writerows(rows)

    # ---------- 主流程 ----------
    def run(self):
        self._log("目标评论数: %d，关键词 %d 组" % (TARGET_COMMENTS, len(self.keywords)))
        for keyword in self.keywords:
            if self._total_comments >= TARGET_COMMENTS:
                break
            self._log("\n===== 关键词: %s =====" % keyword)
            posts = self.search_posts(keyword, MAX_NOTES_PER_KEYWORD)
            self._log("搜到 %d 条帖子" % len(posts))
            for mblog in posts:
                if self._total_comments >= TARGET_COMMENTS:
                    break
                mid = str(mblog.get("id"))
                if mid in self._posts_done:
                    continue
                self._posts_done.add(mid)

                # 正文：先取搜索返回文本，长文则展开
                text = _strip_html(mblog.get("text", ""))
                if mblog.get("isLongText"):
                    full = self.get_full_text(mid)
                    if full:
                        text = full

                user = mblog.get("user") or {}
                self._save_post(keyword, mid, {
                    "关键词": keyword,
                    "微博id": mid,
                    "用户昵称": user.get("screen_name", ""),
                    "发布时间": mblog.get("created_at", ""),
                    "微博内容": text,
                    "转发数": mblog.get("reposts_count", 0),
                    "评论数": mblog.get("comments_count", 0),
                    "点赞数": mblog.get("attitudes_count", 0),
                    "发布于": _strip_html(mblog.get("source", "")),
                    "话题标签": _extract_topics(text),
                    "微博链接": "https://m.weibo.cn/detail/%s" % mid,
                })

                # 评论数 >0 才抓（评论数=0 直接跳过，省请求）
                if (mblog.get("comments_count") or 0) > 0:
                    comments = self.get_comments(mid, MAX_COMMENTS_PER_NOTE)
                    if comments:
                        self._save_comments(keyword, mid, comments)
                        self._total_comments += len(comments)
                        self._log("  微博 %s 抓到 %d 条评论，累计 %d" % (mid, len(comments), self._total_comments))

                self._save_state()

        self._log("\n完成！累计评论 %d 条" % self._total_comments)
        self._log("帖子: %s" % self._post_path)
        self._log("评论: %s" % self._comment_path)


if __name__ == "__main__":
    kws = KEYWORDS
    if len(sys.argv) > 1:
        kws = [k.strip() for k in sys.argv[1].split(",") if k.strip()]
    crawler = WeiboSearchComments(kws)
    crawler.run()
