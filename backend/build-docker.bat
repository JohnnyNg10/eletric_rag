@echo off
chcp 65001 >nul
echo ==========================================
echo   Backend Docker 镜像构建脚本
echo ==========================================
echo.

:: 检查是否在 backend 目录
if not exist "pyproject.toml" (
    echo ❌ 错误: 请在 backend 目录运行此脚本
    pause
    exit /b 1
)

if not exist "app" (
    echo ❌ 错误: 找不到 app 目录
    pause
    exit /b 1
)

:: 检查 Docker
where docker >nul 2>nul
if %errorlevel% neq 0 (
    echo ❌ Docker 未安装或未启动
    echo    请安装 Docker Desktop for Windows
    pause
    exit /b 1
)

echo 📋 检查依赖文件...
if not exist "uv.lock" (
    echo ⚠️  警告: uv.lock 不存在
    where uv >nul 2>nul
    if %errorlevel% equ 0 (
        echo    尝试生成 uv.lock...
        uv lock
    ) else (
        echo ❌ uv 未安装，无法生成 uv.lock
        pause
        exit /b 1
    )
)

echo ✅ 依赖文件检查完成
echo.

:: 检查模型目录
echo 📦 检查 AI 模型...
if not exist "models" (
    echo ❌ 错误: models/ 目录不存在
    echo    请先下载模型：
    echo    mkdir models ^&^& cd models
    echo    git clone https://huggingface.co/BAAI/bge-large-zh-v1.5
    echo    git clone https://huggingface.co/BAAI/bge-reranker-large
    echo    git clone https://huggingface.co/BAAI/bge-reranker-base
    echo    git clone https://huggingface.co/naver/efficient-splade-VI-BT-large-query
    pause
    exit /b 1
)

:: 检查关键模型
set MISSING=0
if not exist "models\bge-large-zh-v1.5" (
    echo ⚠️  缺失: bge-large-zh-v1.5
    set MISSING=1
)
if not exist "models\bge-reranker-large" (
    echo ⚠️  缺失: bge-reranker-large
    set MISSING=1
)

if %MISSING%==1 (
    echo.
    set /p CONTINUE="是否继续构建？(y/n): "
    if /i not "%CONTINUE%"=="y" (
        exit /b 1
    )
) else (
    echo ✅ 所有模型文件完整
)

echo.

:: 构建镜像
echo 🔨 开始构建 Docker 镜像...
echo    镜像名称: electric-rag-backend:latest
echo    Python 版本: 3.13
echo    预计时间: 10-15 分钟（包含 ~3.3GB 模型）
echo.

docker build -t electric-rag-backend:latest .

if %errorlevel% equ 0 (
    echo.
    echo ==========================================
    echo ✅ 构建成功！
    echo ==========================================
    echo.
    echo 📦 镜像信息:
    docker images electric-rag-backend:latest
    echo.
    echo 🚀 测试运行（需要配置环境变量）:
    echo    docker run -d --name backend-test \
    echo      -p 8000:8000 \
    echo      -e MYSQL_HOST=host.docker.internal \
    echo      -e REDIS_HOST=host.docker.internal \
    echo      -e ARK_API_KEY=your_key \
    echo      electric-rag-backend:latest
    echo.
    echo 📝 查看日志:
    echo    docker logs -f backend-test
    echo.
    echo 🛑 停止容器:
    echo    docker stop backend-test ^&^& docker rm backend-test
    echo.
) else (
    echo.
    echo ❌ 构建失败
    pause
    exit /b 1
)

pause
