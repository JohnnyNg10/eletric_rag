"""Test Volcengine Ark LLM client."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

os.environ.setdefault("ARK_API_KEY", "eab97c56-c7fd-499e-a701-4f51bb84be96")

from app.core.generation.llm_client import LLMClient

client = LLMClient()

print("=== Non-streaming test ===")
response = client.chat([
    {"role": "system", "content": "你是电力国标知识库助手，请简洁回答。"},
    {"role": "user", "content": "GB/T 14285是什么标准？一句话回答。"},
])
print(f"Response: {response}\n")

print("=== Streaming test ===")
print("Stream: ", end="", flush=True)
for delta in client.chat_stream([
    {"role": "system", "content": "你是电力国标知识库助手，请简洁回答。"},
    {"role": "user", "content": "继电保护的基本要求有哪些？用3点列举。"},
]):
    print(delta, end="", flush=True)
print("\n\nAll tests passed.")
