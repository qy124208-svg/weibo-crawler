# -*- coding: utf-8 -*-
"""问卷数据分析：统计六大刚需结论的占比（survey_data.csv）"""
import csv, sys
from collections import Counter

sys.stdout.reconfigure(encoding='utf-8')

PATH = r'survey_data.csv'  # TODO: 改为你的问卷数据文件路径
OUT = r'问卷数据分析结果.md'

with open(PATH, encoding='utf-8-sig', newline='') as f:
    rows = list(csv.DictReader(f))

# 剔除注意力筛选题未通过的
clean = [r for r in rows if r.get('Q24_注意力筛选', '').strip() == '非常同意']
bad = [r for r in rows if r.get('Q24_注意力筛选', '').strip() != '非常同意']

def pct(n, total):
    return f'{n} ({n/total*100:.1f}%)'

def stat(rows, key):
    """单选：各选项频次"""
    c = Counter(r.get(key, '').strip() for r in rows if r.get(key, '').strip())
    return c

def multi_hit(rows, key, kw):
    """多选：命中某关键词的人数/比例"""
    n = sum(1 for r in rows if kw in (r.get(key, '') or ''))
    return n

lines = []
N0 = len(rows)
N = len(clean)
lines.append(f'# 问卷数据分析结果\n')
lines.append(f'- 原始样本：{N0} 份')
lines.append(f'- 剔除注意力筛选未通过：{len(bad)} 份（编号：{", ".join(r["编号"] for r in bad)}）')
lines.append(f'- **有效样本：{N} 份**\n')

# ===== 结论① 做攻略难 =====
lines.append('## 结论① 做攻略难（三高刚需）\n')
lines.append(f'### Q10 做攻略的真实感受\n')
for k, v in stat(clean, 'Q10_做攻略感受').most_common():
    lines.append(f'- {k}：{pct(v, N)}')
pain = multi_hit(clean, 'Q9_规划困难', '攻略信息太多')
route = multi_hit(clean, 'Q9_规划困难', '不知道怎么安排路线')
lines.append(f'\n### Q9 规划最大困难（多选，N={N}）\n')
lines.append(f'- 攻略信息太多、看得累：{pct(pain, N)}')
lines.append(f'- 不知道怎么安排路线：{pct(route, N)}')
lines.append(f'- 不知道去哪、纠结：{pct(multi_hit(clean, "Q9_规划困难", "不知道去哪"), N)}')
lines.append(f'- 不知道怎么省钱：{pct(multi_hit(clean, "Q9_规划困难", "不知道怎么省钱"), N)}')
lines.append(f'- 订票订房麻烦：{pct(multi_hit(clean, "Q9_规划困难", "订票订房"), N)}')

# ===== 结论② 找搭子难 =====
lines.append('\n## 结论② 找搭子难（孤独+安全）\n')
lines.append(f'### Q12 结伴意愿\n')
for k, v in stat(clean, 'Q12_结伴意愿').most_common():
    lines.append(f'- {k}：{pct(v, N)}')
lines.append(f'\n### Q13 搭子最大顾虑（多选，N={N}）\n')
for kw in ['安全风险', '性格不合', '财务纠纷', '临时毁约', '没有顾虑']:
    lines.append(f'- {kw}：{pct(multi_hit(clean, "Q13_搭子顾虑", kw), N)}')
lines.append(f'\n### Q14 实名认证后意愿\n')
for k, v in stat(clean, 'Q14_实名后意愿').most_common():
    lines.append(f'- {k}：{pct(v, N)}')

# ===== 结论③ 省钱人群底色 =====
lines.append('\n## 结论③ 省钱人群底色\n')
lines.append(f'### Q5 单次预算\n')
for k, v in stat(clean, 'Q5_单次预算').most_common():
    lines.append(f'- {k}：{pct(v, N)}')
low = sum(1 for r in clean if r.get('Q5_单次预算', '').strip() in ('500元以下', '500-1000元'))
lines.append(f'\n- **单次预算 ≤1000 元合计：{pct(low, N)}**')
lines.append(f'\n### Q23 是否主动找学生优惠\n')
for k, v in stat(clean, 'Q23_找学生优惠').most_common():
    lines.append(f'- {k}：{pct(v, N)}')

# ===== 结论④ AI空白机会 =====
lines.append('\n## 结论④ AI 空白机会\n')
lines.append(f'### Q15 是否用过 AI 规划\n')
for k, v in stat(clean, 'Q15_用过AI').most_common():
    lines.append(f'- {k}：{pct(v, N)}')
lines.append(f'\n### Q16 是否愿意用 AI\n')
for k, v in stat(clean, 'Q16_愿意用AI').most_common():
    lines.append(f'- {k}：{pct(v, N)}')
lines.append(f'\n### Q17 AI 应怎么帮\n')
for k, v in stat(clean, 'Q17_AI怎么帮').most_common():
    lines.append(f'- {k}：{pct(v, N)}')

# ===== 结论⑤ 三合一意愿 =====
lines.append('\n## 结论⑤ 三合一功能使用意愿\n')
lines.append(f'### Q21 三合一使用意愿\n')
for k, v in stat(clean, 'Q21_三合一意愿').most_common():
    lines.append(f'- {k}：{pct(v, N)}')
will = sum(1 for r in clean if r.get('Q21_三合一意愿', '').strip() in ('非常愿意', '愿意'))
lines.append(f'\n- **愿意+非常愿意 合计：{pct(will, N)}**')

# ===== 结论⑥ 付费方式 =====
lines.append('\n## 结论⑥ 付费方式\n')
lines.append(f'### Q22 可接受收费方式（多选，N={N}）\n')
for kw in ['基础功能免费', '按次付费', '预订赚取佣金', '看广告']:
    lines.append(f'- {kw}：{pct(multi_hit(clean, "Q22_收费方式", kw), N)}')

# ===== 画像补充 =====
lines.append('\n## 画像补充\n')
lines.append(f'### Q1 年级\n')
for k, v in stat(clean, 'Q1_年级').most_common():
    lines.append(f'- {k}：{pct(v, N)}')
lines.append(f'\n### Q3 生活费\n')
for k, v in stat(clean, 'Q3_生活费').most_common():
    lines.append(f'- {k}：{pct(v, N)}')

text = '\n'.join(lines)
with open(OUT, 'w', encoding='utf-8') as f:
    f.write(text)
print(text)
print(f'\n已写入 {OUT}')
