# -*- coding: utf-8 -*-
"""剔除饭圈帖子 + 重算词频/词云
饭圈污染源：SMTR25（SM娱乐练习生组合）及其成员名，通过滚雪球话题带入。
输入: post_output/帖子.csv + 评论.csv
输出: post_output/帖子_去饭圈.csv + 评论_去饭圈.csv + analysis_output/ 重新统计结果
"""
import csv, re, os, sys
from collections import Counter
import jieba

sys.stdout.reconfigure(encoding='utf-8')

POST_PATH = 'post_output/帖子.csv'
COMMENT_PATH = 'post_output/评论.csv'
OUT_POST = 'post_output/帖子_去饭圈.csv'
OUT_COMMENT = 'post_output/评论_去饭圈.csv'
OUT_DIR = 'analysis_output'
FONT = 'C:/Windows/Fonts/simhei.ttf'

# ---------- 饭圈黑名单（SMTR25 组合 + 成员名，命中即剔除整条帖子） ----------
FANDOM_WORDS = ['SMTR25', 'SMTR', 'SMTOWN', 'SM娱乐', 'Reply High School',
    '松河', '李松河', 'SONGHA', '翰飞', '李翰飞', 'HANBI', '李河民', '河民',
    '吴弦俊', '弦俊', 'HARUTA', 'hamin', 'Hamin', 'Daniel', 'TATA', 'NICHOLAS',
    '晴太', 'Justin', 'Kassho', '威神V', 'wayv', 'WayV', '姚琛', '钱锟',
    'phantom', '花少2', '花儿与少年']

# ---------- 停用词（与 text_mining.py 完全一致） ----------
STOPWORDS = set('''的 了 是 我 你 他 她 它 我们 你们 他们 她们 和 与 及 或 就 都 也 很
会 要 能 在 有 不 这 那 这些 那些 这个 那个 一个 一种 一些 之 到 去 来 上 下 中 里 外
对 把 被 让 给 从 向 往 为 因为 所以 但是 但 如果 就是 还是 还有 以及 而 而且 并且 或者
自己 什么 怎么 怎样 为什么 没有 可以 可能 应该 一定 其实 不过 只是 已经 现在 时候 知道
觉得 真的 非常 特别 比较 一般 太 多 少 好 大 小 高 低 长 短 年 月 日 时 分 秒 今天 明天
昨天 每天 天天 一起 一下 一点 各种 所有 很多 这样 那样 如何 呀 啊 呢 吧 吗 哦 哈 哈哈
哈哈哈 嘿嘿 啦 咯 滴 大家 感觉 真的 是不是 有没有 什么 怎么 时候 知道 觉得 看到 看到
还有 就是 因为 所以 但是 如果 可以 应该 可能 已经 现在 这个 那个 这些 那些'''.split())
STOPWORDS.update('''全文 视频 微博 不是 只有 一直 直接 然后 不如 发现 这次 一样 两个
最后 不要 这么 这种 看看 真的 开始 小时 一天 一次 晚上 今年 不用 就是 还是 还有 因为
所以 但是 如果 可以 应该 可能 已经 现在 这个 那个 这些 那些 起来 出来 哪里 怎么 什么
这样 那样 如何 大家 感觉 知道 觉得 看到 有没有 是不是 不能 不会 作为 这里 看着 需要
那么 的话 有点 真是 谢谢 别人 一些 更多 相关 评论 发布 查看 链接 网页 添加 支持 老师
孩子 姐姐 宝宝 小伙伴 同城 本地 此微博 成为 通过 关注 点击 全文 展开 收起'''.split())

NAME_BLACKLIST = set('''李松河 李河民 hamin 柳河 李翰飞 吴弦俊 李翰飞hanbi HARUTA
Daniel 李松河唯一中日韩全域大top 李松河唯一真金白银大top 李翰飞全维ace 吴弦俊视觉中心'''.split())

DOMAIN_WORDS = ['穷游', '搭子', '穷游搭子', '旅游搭子', '青旅', '青年旅舍', '拼车', '拼房',
    '拼车拼房', '学生证', '毕业旅行', '毕业穷游', '义工旅行', 'gap year', 'gap', '骑行',
    '徒步', '露营', '沙发客', '民宿', '攻略', '路线', '预算', '省钱', '特价机票', '低价机票',
    '火车硬座', '绿皮火车', '硬座', '川藏线', '大环线', '结伴', '旅伴', '一个人旅行', '独自旅行',
    '说走就走', '穷游省钱', '免费景点', '半价', '门票', '住宿', '交通', '自由行', '跟团',
    '自助游', '背包客', '学生党', '大学生', '穷游攻略', '火车票', '机票', '酒店', '青旅床位',
    '民宿穷游', '穷游住宿', '穷游交通', '穷游吃饭', '拼车旅行', '顺风车']
for w in DOMAIN_WORDS:
    jieba.add_word(w)

URL_RE = re.compile(r'https?://\S+')
AT_RE = re.compile(r'@\S+')
EMOJI_RE = re.compile(r'[\U0001F300-\U0001FAFF\u2600-\u27BF\uFE0F]')


def clean(text):
    if not text:
        return ''
    text = URL_RE.sub('', text)
    text = AT_RE.sub('', text)
    text = EMOJI_RE.sub('', text)
    text = text.replace('\n', ' ').replace('\r', ' ').strip()
    return text


def segment(text):
    words = []
    for w in jieba.cut(clean(text)):
        w = w.strip()
        if len(w) < 2 or w in STOPWORDS or w.isdigit():
            continue
        if w in NAME_BLACKLIST:
            continue
        if re.fullmatch(r'[\.·…]+', w) or re.fullmatch(r'#+', w):
            continue
        words.append(w)
    return words


def is_fandom(text):
    if not text:
        return False
    t = text.lower()
    return any(w.lower() in t for w in FANDOM_WORDS)


def write_counter(path, counter, n=100):
    with open(path, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f)
        w.writerow(['词语', '频次'])
        for word, cnt in counter.most_common(n):
            w.writerow([word, cnt])


# ---------- 读帖子 ----------
with open(POST_PATH, encoding='utf-8-sig', newline='') as f:
    fieldnames = next(csv.reader(f))
    reader = csv.DictReader(f, fieldnames=fieldnames)
    posts = list(reader)

clean_posts = []
removed = 0
for p in posts:
    text = p.get('微博内容', '') or ''
    topics = p.get('话题标签', '') or ''
    if is_fandom(text) or is_fandom(topics):
        removed += 1
        continue
    clean_posts.append(p)

clean_mids = {p.get('微博id', '') for p in clean_posts}
print(f'帖子：原始 {len(posts)} → 剔除饭圈 {removed} → 干净 {len(clean_posts)}')

# ---------- 读评论，按 mid 过滤 ----------
with open(COMMENT_PATH, encoding='utf-8-sig', newline='') as f:
    cfields = next(csv.reader(f))
    creader = csv.DictReader(f, fieldnames=cfields)
    comments = list(creader)

clean_comments = [c for c in comments if c.get('微博id', '') in clean_mids]
print(f'评论：原始 {len(comments)} → 干净 {len(clean_comments)}')

# ---------- 写干净 CSV ----------
if clean_posts:
    with open(OUT_POST, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(clean_posts)
if clean_comments:
    with open(OUT_COMMENT, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=cfields)
        w.writeheader()
        w.writerows(clean_comments)
print(f'已写 {OUT_POST} / {OUT_COMMENT}')

# ---------- 重算词频 ----------
print('\n重新分词统计...')
post_counter = Counter()
for p in clean_posts:
    post_counter.update(segment(p.get('微博内容', '')))
comment_counter = Counter()
for c in clean_comments:
    comment_counter.update(segment(c.get('评论内容', '')))

write_counter(os.path.join(OUT_DIR, '高频词_帖子_去饭圈.csv'), post_counter)
write_counter(os.path.join(OUT_DIR, '高频词_评论_去饭圈.csv'), comment_counter)
print(f'  帖子词频 top15: {[w for w, _ in post_counter.most_common(15)]}')
print(f'  评论词频 top15: {[w for w, _ in comment_counter.most_common(15)]}')

# ---------- 重生成词云 ----------
from wordcloud import WordCloud
for counter, name in [(post_counter, '词云_帖子_去饭圈.png'), (comment_counter, '词云_评论_去饭圈.png')]:
    wc = WordCloud(font_path=FONT, width=1200, height=700, background_color='white',
                   max_words=200, colormap='viridis', random_state=42)
    wc.generate_from_frequencies(counter)
    wc.to_file(os.path.join(OUT_DIR, name))
print(f'已生成去饭圈词云')

print('\n完成。')
