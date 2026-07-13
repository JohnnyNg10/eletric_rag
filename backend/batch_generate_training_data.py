"""
批量调用LLM生成阶段C训练数据

处理所有生成提示词文件夹下的prompt文件，调用豆包Pro生成JSON格式训练数据
"""
import asyncio
import sys
from pathlib import Path
import json
import re
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent))

from app.core.generation import llm_client


async def generate_single(prompt_file: Path, output_file: Path) -> tuple[bool, Optional[dict], str, str]:
    """
    生成单个训练样本

    Returns:
        (成功标志, JSON结果, 查询内容, 错误信息)
    """
    try:
        # 读取提示词
        with open(prompt_file, "r", encoding="utf-8") as f:
            prompt = f.read()

        # 提取查询内容
        query_match = re.search(r"输入：查询：\{([^}]+)\}", prompt)
        query = query_match.group(1) if query_match else "未知"

        # 调用LLM
        response = llm_client.chat(
            messages=[
                {"role": "system", "content": "你是电力标准知识库的查询预处理专家。严格按照指令输出JSON格式，不要输出任何其他文字。"},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=1000
        )

        # 解析JSON
        try:
            result = json.loads(response)

            # 验证必需字段
            required_fields = [
                "vagueness_score", "strategy", "missing_dimension_keys",
                "options", "lane_suggestion", "lane_confidence", "lane_reason"
            ]
            missing = [f for f in required_fields if f not in result]

            if missing:
                return False, None, query, f"缺少字段: {missing}"

            # 保存到文件
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)

            return True, result, query, ""

        except json.JSONDecodeError as e:
            return False, None, query, f"JSON解析失败: {e}"

    except Exception as e:
        return False, None, "", f"API调用失败: {e}"


async def batch_generate():
    """批量生成训练数据"""

    # 配置路径
    prompt_dir = Path("../训练数据/生成提示词")
    output_dir = Path("../训练数据/训练样本")
    output_dir.mkdir(exist_ok=True)

    # 获取所有prompt文件
    prompt_files = sorted(prompt_dir.glob("prompt_*.txt"))

    if not prompt_files:
        print(f"[FAIL] 未找到prompt文件: {prompt_dir}")
        return

    print("=" * 70)
    print("批量生成阶段C训练数据")
    print("=" * 70)
    print(f"提示词目录: {prompt_dir}")
    print(f"输出目录:   {output_dir}")
    print(f"文件数量:   {len(prompt_files)}")
    print()

    # 统计变量
    total = len(prompt_files)
    success_count = 0
    failed_files = []
    all_results = []  # 保存所有成功的(查询, JSON结果)

    # 批量处理
    for i, prompt_file in enumerate(prompt_files, 1):
        # 构造输出文件名（prompt_001.txt -> sample_001.json）
        file_num = prompt_file.stem.split("_")[1]  # 提取数字部分
        output_file = output_dir / f"sample_{file_num}.json"

        print(f"[{i}/{total}] {prompt_file.name}")

        # 生成
        success, result, query, error = await generate_single(prompt_file, output_file)

        if success:
            print(f"  查询: {query[:50]}{'...' if len(query) > 50 else ''}")
            print(f"  [OK] 已保存到 {output_file.name}")
            print(f"  策略: {result['strategy']}, 路由: {result['lane_suggestion']}, score: {result['vagueness_score']}")
            success_count += 1
            all_results.append((query, result))
        else:
            print(f"  查询: {query[:50] if query else '提取失败'}")
            print(f"  [FAIL] {error}")
            failed_files.append((prompt_file.name, query, error))

        print()

        # 每10个暂停一下，避免API限流
        if i % 10 == 0 and i < total:
            print("-" * 70)
            print(f"已完成 {i}/{total}，暂停2秒...")
            print("-" * 70)
            await asyncio.sleep(2)

    # 汇总统计
    print("=" * 70)
    print("生成完成")
    print("=" * 70)
    print(f"总数: {total}")
    print(f"成功: {success_count}")
    print(f"失败: {len(failed_files)}")
    print(f"成功率: {success_count/total*100:.1f}%")

    if failed_files:
        print()
        print("-" * 70)
        print("失败列表")
        print("-" * 70)
        for filename, query, error in failed_files:
            print(f"{filename}")
            print(f"  查询: {query[:50] if query else '未知'}")
            print(f"  错误: {error}")

    # 生成训练集文件（JSONL格式）
    if all_results:
        print()
        print("=" * 70)
        print("生成训练集文件（Instruction Tuning格式）")
        print("=" * 70)

        # 固定的instruction（与修正版提示词一致）
        INSTRUCTION = """你是电力标准知识库的查询预处理专家。分析用户查询，输出JSON格式的预处理结果。

任务：
1. 评估笼统度（0-1分，0=非常明确，1=极度笼统）
2. 识别缺失维度（从以下枚举中选择）：
   - voltage_level: 电压等级
   - equipment_type: 设备类型
   - application_scene: 应用场景
   - neutral_grounding: 中性点接地方式
   - capacity_range: 容量范围
   - install_env: 安装环境
   - standard_series: 标准系列
   - protection_type: 保护类型
3. 根据笼统度判断策略：
   - none: 0-0.3明确
   - suggest: 0.3-0.6轻度笼统
   - clarify_optional: 0.6-0.8中度笼统
   - clarify_required: 0.8-1.0严重笼统
4. 生成澄清选项（strategy非none时）：
   - label: 5-12字简短标题
   - refined_query: 15-30字完整改写查询
5. 判断路由（fast/slow）及理由：
   - fast: 明确标准号/条款号，或单一维度查询
   - slow: 对比/差异/多跳推理/涉及多个标准的关联查询

输出JSON schema（严格遵守）：
{
  "vagueness_score": float (0-1),
  "strategy": "none" | "suggest" | "clarify_optional" | "clarify_required",
  "missing_dimension_keys": [string],
  "options": [
    {
      "label": string,
      "refined_query": string
    }
  ],
  "lane_suggestion": "fast" | "slow",
  "lane_confidence": float (0-1),
  "lane_reason": string
}

注意：
1. missing_dimension_keys必须从上述8个枚举中选择
2. strategy为none时，options为空数组[]
3. lane_reason需清晰说明为什么选择该路由"""

        # 构造训练样本
        training_samples = []
        for query, output_json in all_results:
            training_sample = {
                "instruction": INSTRUCTION,
                "input": f"查询：{query}",
                "output": json.dumps(output_json, ensure_ascii=False, indent=2)
            }
            training_samples.append(training_sample)

        # 保存为JSONL（每行一个JSON）
        train_file = Path("../训练数据/preprocess_e2e_train.jsonl")
        with open(train_file, "w", encoding="utf-8") as f:
            for sample in training_samples:
                f.write(json.dumps(sample, ensure_ascii=False) + "\n")

        print(f"[OK] 已生成训练集文件: {train_file}")
        print(f"     样本数量: {len(training_samples)}")
        print(f"     格式: JSONL (Instruction Tuning)")
        print()
        print("可直接用于Qwen2.5-1.5B LoRA微调")


async def main():
    print()
    await batch_generate()
    print()
    print("=" * 70)
    print("全部完成")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
