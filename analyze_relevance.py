# -*- coding: utf-8 -*-
"""数据相关性诊断：判断现有微博数据对「AI旅游助手」创业方案的覆盖度"""
import csv, random
from collections import Counter


def read(path):
    with open(path, encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


posts = read('post_output/帖子.csv')
comments = read('post_output/评论.csv')
post_texts = [p.get('微博内容', '') for p in posts]
comment_texts = [c.get('评论内容', '') for c in comments]
all_text = post_texts + comment_texts

out = []
out.append('=== 微博数据相关性诊断 ===')
out.append(f'帖子 {len(posts)} 条，评论 {len(comments)} 条\n')

# 1. 帖子来源分布（判断营销号 vs 真实用户）
src = Counter(p.get('发布于', '') for p in posts)
out.append('[1] 帖子来源分布 top15:')
for s, c in src.most_common(15):
    out.append(f'  {s}: {c}')

# 2. AI 相关词
ai = ['AI', '人工智能', 'ChatGPT', '文心', '豆包', '讯飞', '大模型', 'AIGC', 'AI助手',
      'AI旅游', 'AI做攻略', '智能规划', '智能推荐', '生成式', 'GPT']
out.append('\n[2] AI相关词命中数（帖子+评论）:')
for w in ai:
    c = sum(1 for t in all_text if w in t)
    out.append(f'  {w}: {c}')

# 3. 竞品/平台名
comp = ['携程', '去哪儿', '马蜂窝', '飞猪', '同程', '小红书', '抖音', '穷游网', 'booking',
        'airbnb', '美团', '高德', '百度地图', '智行', '飞常准', 'booking', 'Agoda']
out.append('\n[3] 竞品/平台名命中数（帖子+评论）:')
for w in comp:
    c = sum(1 for t in all_text if w.lower() in t.lower())
    out.append(f'  {w}: {c}')

# 4. 负面/不满词（评论）
neg = ['难用', '不好用', '坑', '失望', '垃圾', '后悔', '踩雷', '避雷', '劝退', '太贵',
       '不推荐', '骗', '翻车', '无语', '离谱', '浪费', '踩坑', '鸡肋', '没用', '麻烦',
       '体验差', '不靠谱']
out.append('\n[4] 负面/不满词命中数（评论 44032 条）:')
for w in neg:
    c = sum(1 for t in comment_texts if w in t)
    out.append(f'  {w}: {c}')

# 5. 高互动帖子抽样（点赞排序前15）
out.append('\n[5] 高赞帖子抽样（点赞数排序 top15）:')
sorted_posts = sorted(posts, key=lambda p: int(p.get('点赞数', '0') or 0), reverse=True)[:15]
for p in sorted_posts:
    txt = (p.get('微博内容', '') or '').replace('\n', ' ')[:80]
    out.append(f"  [{p.get('点赞数')}赞] {txt}")

# 6. 随机评论抽样
out.append('\n[6] 随机评论抽样 20 条:')
random.seed(42)
for c in random.sample(comments, 20):
    txt = (c.get('评论内容', '') or '').replace('\n', ' ')[:60]
    out.append(f'  - {txt}')

with open('analysis_output/相关性诊断.txt', 'w', encoding='utf-8') as f:
    f.write('\n'.join(out))
print('done, 输出 analysis_output/相关性诊断.txt')
