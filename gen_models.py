"""生成 WorkBuddy models.json（FoxToken 同款 schema）

为什么这么写：FoxToken 实测能在客户端里正常显示、带图标、能进控制台。它的字段用法是
  vendor        = "user"        <- 客户端靠这个判定「用户自定义模型」，写 Custom 不算
  id            = "品牌:模型名"  <- 冒号前是品牌，客户端按冒号后的模型名匹配图标与元数据
  tags          = ["custom","品牌"]
  descriptionZh / descriptionEn
  maxInputTokens/maxOutputTokens/temperature
  isDefault
这些字段我早期一个都没用（id 用 dorimi_ 前缀、vendor 写 Custom），所以既没图标也不被
当成自定义模型。此处 1:1 复刻。

用法：
  python gen_models.py --check     只打印，不写文件
  python gen_models.py             写入并备份
  python gen_models.py --brand FoxToken --url https://xxx/v1 --key sk-xxx
"""
import argparse
import json
import os
import shutil
import sys
import time

BRAND = 'Miao'
DEFAULT_URL = 'http://127.0.0.1:18085/v1'
DEFAULT_KEY = os.environ.get('MIAO_KEY', '')   # 不硬编码密钥：从环境变量读，否则由用户输入

# (模型名, 官方倍率)
MODELS = [
    ('hy4-preview', 0.29),
    ('hy3', 0.00),
    ('deepseek-v4.1-flash', 0.11),
    ('step-5-preview', 0.33),
    ('glm-5.3', 0.69),
    ('glm-5.3-flash', 0.08),
    ('glm-5.3-flashx', 0.19),
    ('glm-5.2', 0.79),
    ('space-bunny', 0.08),
    ('minimax-m3.1-flash', 0.08),
    ('minimax-m3', 0.25),
    ('kimi-k3.1-pro', 0.97),
    ('kimi-k3', 1.62),
    ('kimi-k2.8-preview', 0.77),
    ('deepseek-v4-pro', 0.51),
    ('mimo-v2.6-pro', 0.13),
]


def ratio_text(r):
    if r == 0:
        return '限时免费'
    s = ('%.2f' % r).rstrip('0').rstrip('.')
    return '%sx' % s


def build(brand, url, key, temp=1):
    out = []
    for i, (m, r) in enumerate(MODELS):
        out.append({
            'name': '%s:%s' % (brand, m),
            'vendor': 'user',
            'url': url,
            'descriptionEn': 'Available through %s. Rate %s.' % (brand, ratio_text(r)),
            'descriptionZh': '通过 %s 提供 · 费率 %s' % (brand, ratio_text(r)),
            'maxInputTokens': 200000,
            'maxOutputTokens': 32000,
            'temperature': temp,
            'supportsToolCall': True,
            'supportsImages': True,      # 2026-10-30 实测 16/16 可识图
            'supportsReasoning': False,
            'tags': ['custom', brand],
            'disabled': False,
            'id': '%s:%s' % (brand, m),
            'apiKey': key,
            'isDefault': i == 2,          # 默认选中 deepseek-v4.1-flash
        })
    return out


def target():
    return os.path.join(os.path.expanduser('~'), '.workbuddy', 'models.json')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--brand', default=BRAND)
    ap.add_argument('--url', default=DEFAULT_URL)
    ap.add_argument('--key', default=DEFAULT_KEY)
    ap.add_argument('--check', action='store_true')
    ap.add_argument('--apply', action='store_true', help='真正写入 models.json')
    a = ap.parse_args()

    data = build(a.brand, a.url, a.key)
    print('生成 %d 条，品牌前缀 %r，示例 id: %s' % (len(data), a.brand, data[0]['id']))
    print(json.dumps(data[2], ensure_ascii=False, indent=2))

    if not a.apply:
        print('\n（未写文件。加 --apply 才写入 %s）' % target())
        return 0

    p = target()
    if os.path.isdir(os.path.dirname(p)) is False:
        print('[X] 没有 .workbuddy 目录，请先启动一次 WorkBuddy')
        return 1
    if os.path.exists(p):
        bak = p + '.bak-' + time.strftime('%Y%m%d-%H%M%S')
        shutil.copy2(p, bak)
        print('已备份 ->', os.path.basename(bak))
        try:
            old = json.load(open(p, encoding='utf-8'))
            keep = [x for x in old
                    if not str(x.get('id', '')).lower().startswith(a.brand.lower() + ':')
                    and not str(x.get('id', '')).startswith('dorimi_')]
            if keep:
                print('保留原有模型 %d 条: %s' % (len(keep), ', '.join(str(x.get('id')) for x in keep)))
                data = data + keep
        except Exception as e:
            print('[!] 读取原配置失败，将整体覆盖:', e)

    with open(p, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print('已写入 %d 条 -> %s' % (len(data), p))
    return 0


if __name__ == '__main__':
    sys.exit(main())
