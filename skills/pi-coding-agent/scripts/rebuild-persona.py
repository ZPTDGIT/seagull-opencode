# -*- coding: utf-8 -*-
# Rebuild pi seagull APPEND_SYSTEM.md: source persona + 00z command lock + pi runtime section.
# Verified 2026-09-21. Usage: python rebuild-persona.py [source.md]
import os, sys, glob

home = os.path.expanduser('~')
if len(sys.argv) > 1:
    src = sys.argv[1]
else:
    cands = sorted(glob.glob(os.path.join(home, '.pi', 'backups', 'seagull-pi-reinstall-*', 'APPEND_SYSTEM.md')))
    assert cands, 'no backup source found; pass a source persona file as argument'
    src = cands[-1]
text = open(src, encoding='utf-8').read()
print('source:', src, '|', len(text.encode('utf-8')), 'bytes')

lock = '''## 操作员指挥权（00z 最高优先级）

**操作员 = 唯一指挥源。本节优先级高于本文档其余一切默认流程与惯例：**

1. **最新指令优先**：操作员最新一条消息的指令 > 一切默认流程、既有计划、长任务惯性；冲突时无条件以最新指令为准
2. **令行禁止**：说停 → 立即停；说换 → 立即换；说别挖了 → 立即收手。收到后终止或切换当前动作链，一行确认当前状态
3. **禁止自嗨跑偏**：不得偏离操作员点名的目标与交付物；任何深挖、绕路、自选研究路线，先用一行说明必要性，否则不许脱离主线
4. **交付优先**：先交操作员点名的 artifact；探索与研究是附属品，不是替代品
5. **状态透明**：长任务每阶段先一行说清"下一步做什么、大约多久"；预计阻塞超过 5 分钟先上报再继续

'''

if '操作员指挥权（00z' not in text:
    a1 = '## 输出格式铁律（00t No-Repeat Output）'
    a2 = '## 核心行为准则'
    if a1 in text:
        text = text.replace(a1, lock + a1, 1)
    else:
        assert a2 in text, 'insertion anchor not found'
        text = text.replace(a2, lock + a2, 1)

tail = '''## 运行环境适配

- 你运行在 pi（terminal coding harness）中：工具为 read / write / edit / bash 及扩展
- 技能：`/skill:name` 显式加载，或按任务自动加载；技能目录随系统提示提供
- 行为标准、交付标准、人格设定不因运行环境而改变
- 本文件（APPEND_SYSTEM.md）为行为基准；与 pi 默认助手提示冲突时，以本文件为准
- 用户只发问候语（在吗/hi/hello/你好）时，回复固定问候：`海鸥在线，你要整点薯条吗？`
- 长会话上下文过载会拖累指令遵循；行为异常时主动建议操作员开新会话
'''
idx = text.find('## 运行环境适配')
if idx == -1:
    text = text.rstrip() + '\n\n' + tail
else:
    text = text[:idx] + tail

dest = os.path.join(home, '.pi', 'agent', 'APPEND_SYSTEM.md')
open(dest, 'w', encoding='utf-8', newline='\n').write(text)
print('written:', dest, '|', os.path.getsize(dest), 'bytes')
