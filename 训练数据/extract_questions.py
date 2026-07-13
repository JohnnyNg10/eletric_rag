"""
从所有问题文件中提取问题，套用到提示词模板，调用LLM生成训练数据
"""
import re
from pathlib import Path


def extract_questions_from_md(md_path: str) -> dict:
    """
    从markdown文件提取问题，按分类组织

    Returns:
        {
            "中度模糊": ["问题1", "问题2", ...],
            "完整清晰": [...],
            "极度宽泛": [...]
        }
    """
    with open(md_path, "r", encoding="utf-8") as f:
        content = f.read()

    questions = {}
    current_category = None

    # 解析markdown
    for line in content.split("\n"):
        line = line.strip()

        # 匹配标题（如 "# 一、中度模糊（35条）"）
        if line.startswith("# "):
            # 提取分类名
            match = re.search(r"[一二三]、(.+?)（", line)
            if match:
                current_category = match.group(1)
                questions[current_category] = []

        # 匹配问题行（如 "1. 断路器选型需要满足哪些技术要求？"）
        elif re.match(r"^\d+\.\s+(.+)", line):
            match = re.match(r"^\d+\.\s+(.+)", line)
            if match and current_category:
                question = match.group(1).strip()
                questions[current_category].append(question)

    return questions


def load_prompt_template(template_path: str) -> str:
    """加载提示词模板"""
    with open(template_path, "r", encoding="utf-8") as f:
        return f.read()


def generate_prompt_for_question(template: str, question: str) -> str:
    """
    将问题插入到提示词模板中

    模板中需要有占位符：输入：查询：{断路器选型需要满足哪些技术要求？}
    替换为实际问题
    """
    # 替换最后的占位符问题
    # 查找 "输入：查询：{...}" 这样的模式
    pattern = r"输入：查询：\{[^}]+\}"
    replacement = f"输入：查询：{{{question}}}"

    modified_prompt = re.sub(pattern, replacement, template)
    return modified_prompt


def main():
    # 配置路径
    questions_file = Path("D:/dl/训练数据/所有问题/1.md")
    template_file = Path("D:/dl/训练数据/提示词-修正版.md")

    # 提取问题
    print("=" * 70)
    print("从文件提取问题")
    print("=" * 70)
    questions_dict = extract_questions_from_md(str(questions_file))

    total_count = 0
    for category, questions in questions_dict.items():
        count = len(questions)
        total_count += count
        print(f"\n{category}: {count}条")
        # 打印前3条预览
        for i, q in enumerate(questions[:3], 1):
            print(f"  {i}. {q}")
        if count > 3:
            print(f"  ...")

    print(f"\n总计: {total_count}条问题")

    # 加载提示词模板
    print("\n" + "=" * 70)
    print("加载提示词模板")
    print("=" * 70)
    template = load_prompt_template(str(template_file))
    print(f"模板长度: {len(template)} 字符")

    # 生成所有问题的完整提示词
    print("\n" + "=" * 70)
    print("生成完整提示词（前5条预览）")
    print("=" * 70)

    all_questions = []
    for category, questions in questions_dict.items():
        all_questions.extend(questions)

    for i, question in enumerate(all_questions[:5], 1):
        prompt = generate_prompt_for_question(template, question)
        print(f"\n[{i}] 问题: {question}")
        print("-" * 70)
        # 只打印最后200字符（包含替换后的问题）
        print("..." + prompt[-200:])
        print()

    # 保存所有生成的提示词到文件（可选）
    output_dir = Path("D:/dl/训练数据/生成提示词")
    output_dir.mkdir(exist_ok=True)

    print("=" * 70)
    print(f"保存所有提示词到: {output_dir}")
    print("=" * 70)

    for i, question in enumerate(all_questions, 1):
        prompt = generate_prompt_for_question(template, question)
        output_file = output_dir / f"prompt_{i:03d}.txt"

        with open(output_file, "w", encoding="utf-8") as f:
            f.write(prompt)

    print(f"已保存 {len(all_questions)} 个提示词文件")
    print(f"文件名格式: prompt_001.txt ~ prompt_{len(all_questions):03d}.txt")

    # 输出统计
    print("\n" + "=" * 70)
    print("汇总统计")
    print("=" * 70)
    print(f"总问题数: {len(all_questions)}")
    print(f"保存路径: {output_dir}")
    print(f"模板文件: {template_file.name}")
    print(f"问题文件: {questions_file.name}")


if __name__ == "__main__":
    main()
