"""测试 category 匹配逻辑"""

category_keywords = {
    '配电': [
        '配电室', '配电柜', '配电系统', '配电装置', '配电网',
        '低压开关柜', '开关柜', '母线', '进线柜', '出线柜'
    ],
    '变电': [
        '变电站', '变压器', '变电设备', '变电所',
        '主变', '副变', '变电容量', '变电运行', '变电检修',
        '油浸式', '干式变压器'
    ],
    '继保': [
        '继电保护', '保护装置', '保护系统',
        '整定', '整定计算', '保护配置', '保护定值',
        '差动保护', '距离保护', '过流保护', '零序保护',
        '保护原理', '选择性', '灵敏性', '速动性'
    ],
    '输电': [
        '输电线路', '架空线', '电缆',
        '输电走廊', '导线', '绝缘子', '杆塔', '输电容量'
    ],
    '安全': [
        '安全距离', '安全措施', '防护', '接地', '防雷',
        '安全净距', '防护等级', 'IP等级', '接地电阻', '接地装置'
    ],
}

query = "分布式电源接入380V配网时的保护配置及技术要求"

print(f"Query: {query}\n")

# 检查每个类别的匹配情况
for category, keywords in category_keywords.items():
    matched = [kw for kw in keywords if kw in query]
    if matched:
        print(f"{category}: {matched}")

# 原逻辑：返回第一个匹配
print("\n原逻辑（返回第一个匹配）：")
for category, keywords in category_keywords.items():
    if any(keyword in query for keyword in keywords):
        print(f"  → {category}")
        break
