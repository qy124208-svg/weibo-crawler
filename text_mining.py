# -*- coding: utf-8 -*-
"""微博文本挖掘：词频 / 话题 / 情感 / 词云
输入: post_output/帖子.csv + 评论.csv
输出: analysis_output/ 目录
"""
import csv, re, os, sys
from collections import Counter
import jieba
import jieba.analyse
import numpy as np

sys.stdout.reconfigure(encoding='utf-8')

# ---------- 配置 ----------
POST_PATH = 'post_output/帖子.csv'
COMMENT_PATH = 'post_output/评论.csv'
OUT_DIR = 'analysis_output'
FONT = 'C:/Windows/Fonts/simhei.ttf'
COMMENT_SENTIMENT_SAMPLE = 5000   # 评论情感抽样条数（SnowNLP 慢，抽样加速）
os.makedirs(OUT_DIR, exist_ok=True)

# ---------- 停用词 ----------
STOPWORDS = set('''的 了 是 我 你 他 她 它 我们 你们 他们 她们 和 与 及 或 就 都 也 很
会 要 能 在 有 不 这 那 这些 那些 这个 那个 一个 一种 一些 之 到 去 来 上 下 中 里 外
对 把 被 让 给 从 向 往 为 因为 所以 但是 但 如果 就是 还是 还有 以及 而 而且 并且 或者
自己 什么 怎么 怎样 为什么 没有 可以 可能 应该 一定 其实 不过 只是 已经 现在 时候 知道
觉得 真的 非常 特别 比较 一般 太 多 少 好 大 小 高 低 长 短 年 月 日 时 分 秒 今天 明天
昨天 每天 天天 一起 一下 一点 各种 所有 很多 这样 那样 如何 呀 啊 呢 吧 吗 哦 哈 哈哈
哈哈哈 嘿嘿 啦 咯 滴 大家 感觉 真的 是不是 有没有 什么 怎么 时候 知道 觉得 看到 看到
还有 就是 因为 所以 但是 如果 可以 应该 可能 已经 现在 这个 那个 这些 那些'''.split())

# 追加平台词/虚词/噪声停用词
STOPWORDS.update('''全文 视频 微博 不是 只有 一直 直接 然后 不如 发现 这次 一样 两个
最后 不要 这么 这种 看看 真的 开始 小时 一天 一次 晚上 今年 不用 就是 还是 还有 因为
所以 但是 如果 可以 应该 可能 已经 现在 这个 那个 这些 那些 起来 出来 哪里 怎么 什么
这样 那样 如何 大家 感觉 知道 觉得 看到 有没有 是不是 不能 不会 作为 这里 看着 需要
那么 的话 有点 真是 谢谢 别人 一些 更多 相关 评论 发布 查看 链接 网页 添加 支持 老师
孩子 姐姐 宝宝 小伙伴 同城 本地 此微博 成为 通过 关注 点击 全文 展开 收起'''.split())

# 饭圈人名/英文专名黑名单（评论数据被追星话题污染，过滤）
NAME_BLACKLIST = set('''李松河 李河民 hamin 柳河 李翰飞 吴弦俊 李翰飞hanbi HARUTA
Daniel 李松河唯一中日韩全域大top 李松河唯一真金白银大top 李翰飞全维ace 吴弦俊视觉中心'''.split())

# ---------- 领域自定义词典（提高穷游/旅游分词准确度） ----------
DOMAIN_WORDS = ['穷游', '搭子', '穷游搭子', '旅游搭子', '青旅', '青年旅舍', '拼车', '拼房',
    '拼车拼房', '学生证', '毕业旅行', '毕业穷游', '义工旅行', 'gap year', 'gap', '骑行',
    '徒步', '露营', '沙发客', '民宿', '攻略', '路线', '预算', '省钱', '特价机票', '低价机票',
    '火车硬座', '绿皮火车', '硬座', '川藏线', '大环线', '结伴', '旅伴', '一个人旅行', '独自旅行',
    '说走就走', '穷游省钱', '免费景点', '半价', '门票', '住宿', '交通', '自由行', '跟团',
    '自助游', '背包客', '学生党', '大学生', '穷游攻略', '火车票', '机票', '酒店', '青旅床位',
    '民宿穷游', '穷游住宿', '穷游交通', '穷游吃饭', '拼车旅行', '顺风车']
for w in DOMAIN_WORDS:
    jieba.add_word(w)

# ---------- 工具 ----------
URL_RE = re.compile(r'https?://\S+')
AT_RE = re.compile(r'@\S+')
EMOJI_RE = re.compile(r'[\U0001F300-\U0001FAFF\u2600-\u27BF\uFE0F]')
TOPIC_RE = re.compile(r'#([^#\s]{1,30})#')


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


def read_col(path, col):
    with open(path, encoding='utf-8-sig', newline='') as f:
        r = csv.DictReader(f)
        return [row.get(col, '') for row in r]


def write_counter(path, counter, n=100):
    with open(path, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f)
        w.writerow(['词语', '频次'])
        for word, cnt in counter.most_common(n):
            w.writerow([word, cnt])


# ---------- 1. 读数据 ----------
print('=' * 50)
print('读取数据...')
posts = read_col(POST_PATH, '微博内容')
post_topics = read_col(POST_PATH, '话题标签')
comments = read_col(COMMENT_PATH, '评论内容')
print(f'帖子 {len(posts)} 条，评论 {len(comments)} 条')

# ---------- 2. 词频 ----------
print('\n[词频] 分词统计中...')
post_counter, comment_counter = Counter(), Counter()
for i, t in enumerate(posts):
    post_counter.update(segment(t))
    if (i + 1) % 2000 == 0:
        print(f'  帖子分词 {i + 1}/{len(posts)}')
for i, t in enumerate(comments):
    comment_counter.update(segment(t))
    if (i + 1) % 10000 == 0:
        print(f'  评论分词 {i + 1}/{len(comments)}')

write_counter(os.path.join(OUT_DIR, '高频词_帖子.csv'), post_counter)
write_counter(os.path.join(OUT_DIR, '高频词_评论.csv'), comment_counter)
print(f'  帖子词频 top10: {[w for w, _ in post_counter.most_common(10)]}')
print(f'  评论词频 top10: {[w for w, _ in comment_counter.most_common(10)]}')

# ---------- 3. 话题标签 ----------
print('\n[话题] 统计中...')
topic_counter = Counter()
for line in post_topics:
    if not line:
        continue
    for t in line.split(','):
        t = t.strip().strip('#')
        if t:
            topic_counter[t] += 1
write_counter(os.path.join(OUT_DIR, '高频话题.csv'), topic_counter, n=80)
print(f'  独立话题 {len(topic_counter)} 个，top10: {[t for t, _ in topic_counter.most_common(10)]}')

# ---------- 4. 情感分析（SnowNLP） ----------
if '--skip-sentiment' not in sys.argv:
    print('\n[情感] SnowNLP 打分中（较慢，请耐心）...')
    from snownlp import SnowNLP


    def sentiment(texts, sample=None):
        if sample and len(texts) > sample:
            idx = np.random.RandomState(42).choice(len(texts), sample, replace=False)
            texts = [texts[i] for i in idx]
        scores = []
        for i, t in enumerate(texts):
            try:
                scores.append(SnowNLP(clean(t)).sentiments)
            except Exception:
                scores.append(0.5)
            if (i + 1) % 1000 == 0:
                print(f'  进度 {i + 1}/{len(texts)}')
        return scores


    def dist(scores, label):
        pos = sum(1 for s in scores if s > 0.6)
        neu = sum(1 for s in scores if 0.4 <= s <= 0.6)
        neg = sum(1 for s in scores if s < 0.4)
        n = len(scores)
        with open(os.path.join(OUT_DIR, f'情感分布_{label}.csv'), 'w', newline='', encoding='utf-8-sig') as f:
            w = csv.writer(f)
            w.writerow(['情感', '条数', '占比'])
            w.writerow(['正面', pos, f'{pos / n:.2%}'])
            w.writerow(['中性', neu, f'{neu / n:.2%}'])
            w.writerow(['负面', neg, f'{neg / n:.2%}'])
        print(f'  [{label}] 正面 {pos / n:.1%} / 中性 {neu / n:.1%} / 负面 {neg / n:.1%}（样本 {n}）')


    post_scores = sentiment(posts)
    dist(post_scores, '帖子')
    comment_scores = sentiment(comments, sample=COMMENT_SENTIMENT_SAMPLE)
    dist(comment_scores, '评论')
else:
    print('\n[情感] 已跳过（--skip-sentiment，复用已有结果）')

# ---------- 5. 词云 ----------
print('\n[词云] 生成中...')
from wordcloud import WordCloud
for counter, name in [(post_counter, '词云_帖子.png'), (comment_counter, '词云_评论.png')]:
    wc = WordCloud(font_path=FONT, width=1200, height=700, background_color='white',
                   max_words=200, colormap='viridis', random_state=42)
    wc.generate_from_frequencies(counter)
    wc.to_file(os.path.join(OUT_DIR, name))
    print(f'  已生成 {name}')

print('\n' + '=' * 50)
print(f'全部完成，输出目录: {OUT_DIR}/')
for f in sorted(os.listdir(OUT_DIR)):
    print(f'  - {f}')
