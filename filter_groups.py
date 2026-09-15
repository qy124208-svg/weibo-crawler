# -*- coding: utf-8 -*-
"""B组剔明星 + C组剔开学季，重算词频与求助/负面占比
与 analyze_painpoints.py 完全一致的停用词/信号词/分词逻辑，仅多一道清洗。
"""
import csv, re, os, sys
from collections import Counter
import jieba

sys.stdout.reconfigure(encoding='utf-8')

OUT_DIR = 'analysis_output/刚需证明'
os.makedirs(OUT_DIR, exist_ok=True)

# ---------- 停用词（与 analyze_painpoints 一致） ----------
STOPWORDS = set('''的 了 是 我 你 他 她 它 我们 你们 他们 她们 和 与 及 或 就 都 也 很
会 要 能 在 有 不 这 那 这些 那些 这个 那个 一个 一种 一些 之 到 去 来 上 下 中 里 外
对 把 被 让 给 从 向 往 为 因为 所以 但是 但 如果 就是 还是 还有 以及 而 而且 并且 或者
自己 什么 怎么 怎样 为什么 没有 可以 可能 应该 一定 其实 不过 只是 已经 现在 时候 知道
觉得 真的 非常 特别 比较 一般 太 多 少 好 大 小 高 低 长 短 年 月 日 时 分 秒 今天 明天
昨天 每天 天天 一起 一下 一点 各种 所有 很多 这样 那样 如何 呀 啊 呢 吧 吗 哦 哈 哈哈
哈哈哈 嘿嘿 啦 咯 滴 大家 感觉 是不是 有没有 看到 全文 视频 微博 不是 只有 一直 直接
然后 不如 发现 这次 一样 两个 最后 不要 这么 这种 看看 真的 开始 小时 一天 一次 晚上
今年 不用 起来 出来 哪里 这样 那样 这里 看着 需要 那么 的话 有点 真是 谢谢 别人 一些
更多 相关 评论 发布 查看 链接 网页 添加 支持 老师 孩子 姐姐 宝宝 小伙伴 同城 本地
此微博 成为 通过 关注 点击 全文 展开 收起 不能 不会 作为'''.split())

DOMAIN_WORDS = ['穷游', '搭子', '穷游搭子', '旅游搭子', '青旅', '青年旅舍', '拼车', '拼房',
    '拼车拼房', '学生证', '毕业旅行', '毕业穷游', '义工旅行', 'gap year', 'gap', '骑行',
    '徒步', '露营', '沙发客', '民宿', '攻略', '路线', '预算', '省钱', '特价机票', '低价机票',
    '火车硬座', '绿皮火车', '硬座', '川藏线', '大环线', '结伴', '旅伴', '一个人旅行', '独自旅行',
    '说走就走', '穷游省钱', '免费景点', '半价', '门票', '住宿', '交通', '自由行', '跟团',
    '自助游', '背包客', '学生党', '大学生', '穷游攻略', '火车票', '机票', '酒店', '青旅床位',
    '民宿穷游', '穷游住宿', '穷游交通', '穷游吃饭', '拼车旅行', '顺风车', 'AI做攻略', 'AI规划']
for w in DOMAIN_WORDS:
    jieba.add_word(w)

HELP_WORDS = ['求带', '求推荐', '求攻略', '求搭子', '求教', '蹲一个', '蹲个', '在线等',
    '怎么安排', '怎么办', '求分享', '求助', '跪求', '求问', '求结伴', '求路线', '求行程',
    '怎么规划', '如何规划', '怎么省钱', '求省', '求推荐路线', '第一次去', '不知道怎么']

PAIN_WORDS = ['头疼', '麻烦', '崩溃', '太难', '焦虑', '心烦', '孤独', '害怕', '不敢',
    '太贵', '踩坑', '愁', '无奈', '绝望', '心累', '费力', '费劲', '看不懂', '复杂',
    '累死', '好累', '好难', '好贵', '贵死', '坑死', '劝退', '避雷', '踩雷', '不靠谱']

URL_RE = re.compile(r'https?://\S+')
AT_RE = re.compile(r'@\S+')
EMOJI_RE = re.compile(r'[\U0001F300-\U0001FAFF☀-➿️]')


def clean(text):
    if not text:
        return ''
    text = URL_RE.sub('', text)
    text = AT_RE.sub('', text)
    text = EMOJI_RE.sub('', text)
    return text.replace('\n', ' ').replace('\r', ' ').strip()


def segment(text):
    words = []
    for w in jieba.cut(clean(text)):
        w = w.strip()
        if len(w) < 2 or w in STOPWORDS or w.isdigit():
            continue
        if re.fullmatch(r'[\.·…]+', w) or re.fullmatch(r'#+', w):
            continue
        words.append(w)
    return words


def is_hit(text, topics, words):
    s = f'{text} {topics}'
    return any(w in s for w in words)


def read(path, col):
    with open(path, encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def write_posts(path, posts, fieldnames):
    with open(path, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(posts)


def write_counter(path, counter, n=30):
    with open(path, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f)
        w.writerow(['词语', '频次'])
        for word, cnt in counter.most_common(n):
            w.writerow([word, cnt])


def process(name, blacklist, label):
    d = f'group_output/{name}'
    posts = read(f'{d}/帖子.csv', '微博内容')
    comments = read(f'{d}/评论.csv', '评论内容')
    pfields = posts[0].keys() if posts else []
    cfields = comments[0].keys() if comments else []

    removed = 0
    clean_posts = []
    for p in posts:
        if is_hit(p.get('微博内容', ''), p.get('话题标签', ''), blacklist):
            removed += 1
            continue
        clean_posts.append(p)
    clean_mids = {p.get('微博id', '') for p in clean_posts}
    clean_comments = [c for c in comments if c.get('微博id', '') in clean_mids]

    # 写清洗后 CSV
    write_posts(f'{d}/帖子_清洗.csv', clean_posts, pfields)
    write_posts(f'{d}/评论_清洗.csv', clean_comments, cfields)

    # 重算词频
    pc = Counter()
    for p in clean_posts:
        pc.update(segment(p.get('微博内容', '')))
    cc = Counter()
    for c in clean_comments:
        cc.update(segment(c.get('评论内容', '')))
    write_counter(f'{OUT_DIR}/高频词_{name}_帖子_清洗.csv', pc)
    write_counter(f'{OUT_DIR}/高频词_{name}_评论_清洗.csv', cc)

    # 重算求助/负面占比
    clean_texts = [p.get('微博内容', '') for p in clean_posts]
    help_posts = sum(1 for t in clean_texts if t and any(w in t for w in HELP_WORDS))
    pain_posts = sum(1 for t in clean_texts if t and any(w in t for w in PAIN_WORDS))

    print(f'\n===== [{name}] {label} =====')
    print(f'帖子 {len(posts)} → 剔除 {removed} → 干净 {len(clean_posts)}')
    print(f'评论 {len(comments)} → 干净 {len(clean_comments)}')
    print(f'求助帖 {help_posts} ({help_posts/len(clean_posts):.1%})  负面帖 {pain_posts} ({pain_posts/len(clean_posts):.1%})')
    print(f'帖子top15: {[w for w, _ in pc.most_common(15)]}')
    print(f'评论top10: {[w for w, _ in cc.most_common(10)]}')

    return {
        'name': name, 'label': label,
        '原帖': len(posts), '原评': len(comments),
        '剔除': removed, '净帖': len(clean_posts), '净评': len(clean_comments),
        '求助': help_posts, '求助占比': f'{help_posts/len(clean_posts):.1%}',
        '负面': pain_posts, '负面占比': f'{pain_posts/len(clean_posts):.1%}',
        '帖子top10': [w for w, _ in pc.most_common(10)],
    }


B_STAR = ['杨洋', '花少', '花儿与少年', '演唱会', '追星', '爱豆', '应援', '站姐', '接机', '饭圈',
          '刘宇宁', '摩登兄弟', '地球超新鲜', '开始推理吧', '去你的岛']
C_SCHOOL = ['新生', '开学', '三件套', '录取', '通知书', '报到', '军训', '入学', '学费']

results = [
    process('B_找搭子难', B_STAR, '剔明星'),
    process('C_省钱难', C_SCHOOL, '剔开学季'),
]

with open(f'{OUT_DIR}/清洗对比.txt', 'w', encoding='utf-8') as f:
    for r in results:
        f.write(f"[{r['name']}] {r['label']}\n")
        f.write(f"  帖子 {r['原帖']} → 剔除{r['剔除']} → 干净{r['净帖']}   评论 {r['原评']} → 干净{r['净评']}\n")
        f.write(f"  求助{r['求助']}({r['求助占比']})  负面{r['负面']}({r['负面占比']})\n")
        f.write(f"  帖子top10: {r['帖子top10']}\n\n")

print('\n完成，输出到', OUT_DIR)
