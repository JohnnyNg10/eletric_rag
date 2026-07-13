"""
测试单次LLM调用生成预处理训练数据

使用豆包Pro API，根据提示词生成阶段C训练数据格式的JSON输出
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app.core.generation import llm_client
import json


async def test_single_call():
    """测试单次调用"""

    # 读取第一个提示词文件
    prompt_file = Path("../训练数据/生成提示词/prompt_001.txt")

    if not prompt_file.exists():
        print(f"[FAIL] 提示词文件不存在: {prompt_file}")
        print(f"   请先运行: python ../训练数据/extract_questions.py")
        return

    with open(prompt_file, "r", encoding="utf-8") as f:
        prompt = f.read()

    print("=" * 70)
    print("测试LLM调用生成训练数据")
    print("=" * 70)
    print(f"提示词文件: {prompt_file.name}")
    print(f"提示词长度: {len(prompt)} 字符")

    # 提取查询内容（用于显示）
    import re
    query_match = re.search(r"输入：查询：\{([^}]+)\}", prompt)
    query = query_match.group(1) if query_match else "未知"
    print(f"查询问题: {query}")
    print()

    # 调用LLM
    print("-" * 70)
    print("调用豆包Pro API...")
    print("-" * 70)

    try:
        response = llm_client.chat(
            messages=[
                {"role": "system", "content": "你是电力标准知识库的查询预处理专家。严格按照指令输出JSON格式，不要输出任何其他文字。"},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=1000
        )

        print("[OK] API调用成功")
        print()

        # 解析响应
        print("=" * 70)
        print("LLM响应")
        print("=" * 70)
        print(response)
        print()

        # 验证JSON格式
        print("=" * 70)
        print("JSON格式验证")
        print("=" * 70)

        try:
            result = json.loads(response)
            print("[OK] JSON解析成功")
            print()

            # 检查必需字段
            required_fields = [
                "vagueness_score",
                "strategy",
                "missing_dimension_keys",
                "options",
                "lane_suggestion",
                "lane_confidence",
                "lane_reason"
            ]

            missing_fields = []
            for field in required_fields:
                if field not in result:
                    missing_fields.append(field)

            if missing_fields:
                print(f"[FAIL] 缺少必需字段: {missing_fields}")
            else:
                print("[OK] 所有必需字段完整")

            # 显示关键字段
            print()
            print("-" * 70)
            print("关键字段预览")
            print("-" * 70)
            print(f"vagueness_score:  {result.get('vagueness_score')}")
            print(f"strategy:         {result.get('strategy')}")
            print(f"missing_dims:     {result.get('missing_dimension_keys')}")
            print(f"options数量:      {len(result.get('options', []))}")
            print(f"lane_suggestion:  {result.get('lane_suggestion')}")
            print(f"lane_confidence:  {result.get('lane_confidence')}")
            print(f"lane_reason:      {result.get('lane_reason', '')[:50]}...")

            # 显示options详情
            if result.get('options'):
                print()
                print("-" * 70)
                print("澄清选项详情")
                print("-" * 70)
                for i, opt in enumerate(result['options'], 1):
                    print(f"[{i}] {opt.get('label', '')}")
                    print(f"    {opt.get('refined_query', '')}")

            # 格式化输出完整JSON（用于保存）
            print()
            print("=" * 70)
            print("格式化JSON输出（可直接作为训练数据）")
            print("=" * 70)
            formatted = json.dumps(result, ensure_ascii=False, indent=2)
            print(formatted)

            # 保存到文件
            output_file = Path("../训练数据/测试输出/test_001.json")
            output_file.parent.mkdir(exist_ok=True)

            with open(output_file, "w", encoding="utf-8") as f:
                f.write(formatted)

            print()
            print(f"[OK] 已保存到: {output_file}")

        except json.JSONDecodeError as e:
            print(f"[FAIL] JSON解析失败: {e}")
            print(f"   LLM可能输出了额外文字，需要清理")

    except Exception as e:
        print(f"[FAIL] API调用失败: {e}")
        import traceback
        traceback.print_exc()


async def main():
    print()
    await test_single_call()
    print()
    print("=" * 70)
    print("测试完成")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
