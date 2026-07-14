#!/usr/bin/env python3
# -*- coding: utf-8 -*-
query = "分布式电源接入380V配网时的保护配置"

category_keywords = {
    '配电': ['配电室', '配电柜', '配电系统', '配电装置', '配电网', '配网', '低压开关柜', '开关柜', '母线', '进线柜', '出线柜'],
    '继保': ['继电保护', '保护装置', '保护系统', '整定', '整定计算', '保护配置', '保护定值', '差动保护', '距离保护', '过流保护', '零序保护', '保护原理', '选择性', '灵敏性', '速动性'],
}

print("Query:", query)
print()

matched_categories = []
for category, keywords in category_keywords.items():
    matched = [kw for kw in keywords if kw in query]
    if matched:
        print(f"{category}: {matched}")
        matched_categories.append(category)

print()
print("Matched categories:", matched_categories)
result = None if len(matched_categories) > 1 else (matched_categories[0] if matched_categories else None)
print("Should return:", result)
