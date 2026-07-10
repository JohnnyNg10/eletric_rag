"""
测试模型下载功能

Usage:
    python test_model_download.py
"""
import sys
import os
from pathlib import Path

# 添加backend目录到路径
backend_dir = Path(__file__).parent
sys.path.insert(0, str(backend_dir))

from app.core.embedding.model_loader import get_download_manager
from app.config import settings

def test_check_models():
    """测试检查模型是否存在"""
    print("=" * 60)
    print("Testing: Check Model Existence")
    print("=" * 60)

    manager = get_download_manager(settings.MODELS_DIR)

    models = {
        "embedding": settings.EMBEDDING_MODEL,
        "reranker_large": settings.RERANKER_MODEL_LARGE,
        "reranker_base": settings.RERANKER_MODEL_BASE,
        "sparse": settings.SPARSE_MODEL,
    }

    results = {}
    for purpose, model_name in models.items():
        exists = manager.check_model_exists(model_name)
        results[purpose] = exists
        print(f"  [{purpose}] {model_name}: {'✓ Found' if exists else '✗ Missing'}")

    print()
    return results

def test_download_single_model():
    """测试下载单个模型"""
    print("=" * 60)
    print("Testing: Download Single Model")
    print("=" * 60)

    manager = get_download_manager(settings.MODELS_DIR)

    # 测试下载最小的模型
    test_model = settings.RERANKER_MODEL_BASE  # ~400MB

    print(f"Testing download: {test_model}")
    print("Note: This will download ~400MB of data")
    print()

    response = input("Continue? (y/n): ")
    if response.lower() != 'y':
        print("Skipped")
        return False

    # 获取代理配置
    proxy = os.environ.get("HTTP_PROXY") or os.environ.get("HTTPS_PROXY")
    if proxy:
        print(f"Using proxy: {proxy}")
    else:
        print("No proxy configured. Set HTTP_PROXY if needed:")
        print("  export HTTP_PROXY=http://127.0.0.1:7897")
        print()

    try:
        model_path = manager.download_model(test_model, proxy=proxy)
        print(f"\n✓ Download successful: {model_path}")
        return True
    except Exception as e:
        print(f"\n✗ Download failed: {e}")
        return False

def test_download_all_models():
    """测试下载所有模型"""
    print("=" * 60)
    print("Testing: Download All Models")
    print("=" * 60)

    manager = get_download_manager(settings.MODELS_DIR)

    models = {
        "embedding": settings.EMBEDDING_MODEL,
        "reranker_large": settings.RERANKER_MODEL_LARGE,
        "reranker_base": settings.RERANKER_MODEL_BASE,
        "sparse": settings.SPARSE_MODEL,
    }

    print("This will download approximately 3.3GB of data:")
    for purpose, model_name in models.items():
        print(f"  - [{purpose}] {model_name}")
    print()

    response = input("Continue? (y/n): ")
    if response.lower() != 'y':
        print("Skipped")
        return False

    # 获取代理配置
    proxy = os.environ.get("HTTP_PROXY") or os.environ.get("HTTPS_PROXY")
    if proxy:
        print(f"Using proxy: {proxy}\n")
    else:
        print("No proxy configured. Set HTTP_PROXY if needed:")
        print("  export HTTP_PROXY=http://127.0.0.1:7897\n")

    try:
        results = manager.download_all_models(models, proxy=proxy)
        print(f"\n✓ Downloaded {len(results)}/{len(models)} models successfully")
        return len(results) == len(models)
    except Exception as e:
        print(f"\n✗ Download failed: {e}")
        return False

def main():
    """主测试函数"""
    print("\n" + "=" * 60)
    print("Model Download Test Suite")
    print("=" * 60)
    print(f"Models directory: {Path(settings.MODELS_DIR).absolute()}")
    print(f"Auto download: {settings.AUTO_DOWNLOAD_MODELS}")
    print()

    # 测试1: 检查模型
    results = test_check_models()
    missing_count = sum(1 for exists in results.values() if not exists)

    if missing_count == 0:
        print("✓ All models are already downloaded!")
        print("\nTests completed. You can start the application.")
        return

    print(f"\nFound {missing_count} missing model(s)")
    print()

    # 询问是否下载
    print("Options:")
    print("  1. Download single model (test)")
    print("  2. Download all models")
    print("  3. Skip")
    print()

    choice = input("Choose option (1/2/3): ")

    if choice == "1":
        test_download_single_model()
    elif choice == "2":
        test_download_all_models()
    else:
        print("Skipped. You can download models later by:")
        print("  1. Set AUTO_DOWNLOAD_MODELS=True in .env")
        print("  2. Start the application: uvicorn app.main:app")
        print("  3. Or run this script again")

    print("\n" + "=" * 60)
    print("Test completed")
    print("=" * 60)

if __name__ == "__main__":
    main()
