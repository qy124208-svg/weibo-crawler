# -*- coding: utf-8 -*-
"""四组痛点词分组采集：每组 3000 帖 + 附带评论，按组独立存储，关滚雪球。

用法: python run_group_collect.py
输出: group_output/A_做攻略难/{帖子.csv,评论.csv} ... 每组独立目录
断点续传：每组 post_state.json，中断后重跑自动续采。
"""
from weibo_city_crawl import WeiboPostCollector

GROUPS = [
    ('A_做攻略难', [
        '做攻略 累', '攻略 看不完', '第一次去 不知道怎么安排', '旅游攻略 太杂',
        '求攻略', '求推荐 路线', '行程 怎么安排', '攻略 踩坑', '避雷',
        '做攻略 头疼', '攻略 太多', '旅游规划 麻烦', '懒得做攻略', '求旅游攻略',
    ]),
    ('B_找搭子难', [
        '找搭子', '旅游搭子', '结伴旅行', '一个人旅行 孤独', '一个人 不敢去',
        '找旅伴', '组队旅行', '求带', '蹲一个搭子', '独行 害怕',
        '拼车拼房', '结伴', '找驴友', '一个人旅游',
    ]),
    ('C_省钱难', [
        '学生 没钱 旅行', '预算 不够', '穷游 怎么省钱', '旅游 太贵',
        '学生党 省钱', '学生证 优惠', '花最少的钱', '穷游 多少钱', '省钱 攻略',
        '大学生 预算', '穷游 预算', '旅游 省钱', '没钱 旅游', '穷游 花费',
    ]),
    ('D_现有工具不满', [
        'AI做攻略', 'ChatGPT 旅游', '豆包 旅游', '携程 吐槽', '攻略软件 难用',
        'AI推荐 不靠谱', 'AI 旅游 规划', '智能 行程', '旅游 App 难用', '携程 避雷',
        '飞猪 吐槽', 'AI 助手 旅游', '文心 旅游', 'AI旅行',
    ]),
]

TARGET_PER_GROUP = 3000


if __name__ == '__main__':
    for name, kws in GROUPS:
        print(f'\n{"=" * 60}')
        print(f'开始采集组 [{name}]：关键词 {len(kws)} 个，目标 {TARGET_PER_GROUP} 帖')
        print('=' * 60)
        c = WeiboPostCollector(
            target_posts=TARGET_PER_GROUP,
            seed_keywords=kws,
            max_pages=30,
            grab_comments=True,
            max_comments_per_post=30,
            output_dir=f'group_output/{name}',
            snowball=False,
        )
        c.collect()
        print(f'\n组 [{name}] 结束：帖子 {len(c.seen_mids)}，评论 {c.total_comments}')
