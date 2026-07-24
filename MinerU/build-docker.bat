@echo off
chcp 65001 >nul
echo ==========================================
echo   MinerU Docker 镜像构建脚本
echo ==========================================
echo.

:: 检查是否在 MinerU 目录
if not exist "pyproject.toml" (
    echo ❌ 错误: 请在 MinerU 项目根目录运行此脚本
    pause
    exit /b 1
)

if not exist "mineru" (
    echo ❌ 错误: 找不到 mineru 目录
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

:: 构建镜像
echo 🔨 开始构建 Docker 镜像...
echo    镜像名称: electric-rag-mineru:latest
echo    Python 版本: 3.13
echo    预计时间: 5-10 分钟
echo.

docker build -t electric-rag-mineru:latest .

if %errorlevel% equ 0 (
    echo.
    echo ==========================================
    echo ✅ 构建成功！
    echo ==========================================
    echo.
    echo 📦 镜像信息:
    docker images electric-rag-mineru:latest
    echo.
    echo 🚀 测试运行:
    echo    docker run -d --name mineru-test -p 8001:8001 electric-rag-mineru:latest
    echo    curl http://localhost:8001/health
    echo.
    echo 📝 查看日志:
    echo    docker logs -f mineru-test
    echo.
    echo 🛑 停止容器:
    echo    docker stop mineru-test ^&^& docker rm mineru-test
    echo.
) else (
    echo.
    echo ❌ 构建失败
    pause
    exit /b 1
)

pause
