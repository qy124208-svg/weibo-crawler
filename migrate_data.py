"""
从旧版 progress.json 迁移数据到新版 state.json + 重新生成14字段CSV
用法: python migrate_data.py
"""
import json, os, csv

OLD_STATE = os.path.join(os.path.dirname(__file__), 'weibo_one_spider-main', 'output', 'progress.json')
NEW_STATE = os.path.join(os.path.dirname(__file__), 'city_output', 'state.json')
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), 'city_output')

USER_FIELDS = ['uid', '昵称', '性别', '所在地', 'IP属地', '认证类型', '认证信息',
               '简介', '粉丝数', '关注数', '微博数', '注册时间', '用户主页链接', '质量标记']

def main():
    # 1. 读取旧版
    if not os.path.exists(OLD_STATE):
        print(f'旧版状态文件不存在: {OLD_STATE}')
        return
    with open(OLD_STATE, encoding='utf-8') as f:
        old = json.load(f)

    confirmed_users = old.get('confirmed_users', {})
    posts_collected = old.get('posts_collected', {})
    tried_uids = old.get('tried_uids', [])

    print(f'旧版数据:')
    for city, users in confirmed_users.items():
        print(f'  {city}: {len(users)}人')
    print(f'  tried: {len(tried_uids)}个')
    print(f'  posts_collected: {sum(len(v) for v in posts_collected.values())}个')

    # 2. 转为新版格式
    # confirmed: {city: {uid: {14字段}}} — 与新版 _save 格式一致
    confirmed = {}
    for city, users in confirmed_users.items():
        confirmed[city] = users  # 已经是 {uid: {info}} 格式

    # collected: {city: [uid]}
    collected = {}
    for city in confirmed_users:
        collected[city] = posts_collected.get(city, [])

    new_state = {
        'confirmed': confirmed,
        'collected': collected,
        'tried': tried_uids,
    }

    # 3. 备份旧state.json
    backup = NEW_STATE + '.bak'
    if os.path.exists(NEW_STATE):
        os.rename(NEW_STATE, backup)
        print(f'\n已备份旧state.json → {backup}')

    # 4. 写入新版state.json
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(NEW_STATE, 'w', encoding='utf-8') as f:
        json.dump(new_state, f, ensure_ascii=False)
    print(f'已写入新版state.json: {NEW_STATE}')

    # 5. 重新生成14字段CSV
    for city, users in confirmed_users.items():
        user_list = list(users.values())
        if not user_list:
            continue
        csv_path = os.path.join(OUTPUT_DIR, f'{city}_用户.csv')
        with open(csv_path, 'w', newline='', encoding='utf-8-sig') as f:
            w = csv.DictWriter(f, fieldnames=USER_FIELDS, extrasaction='ignore')
            w.writeheader()
            w.writerows(user_list)
        print(f'已生成 {city}_用户.csv: {len(user_list)}人 ({len(USER_FIELDS)}字段)')

    # 6. 验证
    print(f'\n========== 验证 ==========')
    with open(NEW_STATE, encoding='utf-8') as f:
        verify = json.load(f)
    for city in ['南京', '杭州', '青岛', '郑州']:
        c = verify.get('confirmed', {}).get(city, {})
        if isinstance(c, dict):
            sample = list(c.values())[:1]
            fields = list(sample[0].keys()) if sample else []
            print(f'{city}: {len(c)}人, 字段: {fields}')
        else:
            print(f'{city}: {len(c)}条(列表格式)')

    print('\n✅ 迁移完成！现在可以启动 GUI: python weibo_city_crawl_gui.py')


if __name__ == '__main__':
    main()
