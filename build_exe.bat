@echo off
chcp 65001 >nul
echo ====================================
echo    图片管理系统 - 打包工具
echo ====================================
echo.

echo [1/4] 检查依赖...
python -m pip install --upgrade pip
pip install -r requirements.txt

echo.
echo [2/4] 清理旧文件...
if exist "dist" rmdir /s /q dist
if exist "build" rmdir /s /q build
if exist "*.spec" del /q *.spec

echo.
echo [3/4] 开始打包 exe...
pyinstaller --name="图片管理系统" ^
    --onefile ^
    --windowed ^
    --icon=NONE ^
    --add-data="files;files" ^
    imageApplication.py

echo.
echo [4/4] 复制必要文件到 dist...
if not exist "dist\files" mkdir "dist\files"
if exist "files\*" copy /Y "files\*" "dist\files\"
if exist "images.db" copy /Y "images.db" "dist\"

echo.
echo ====================================
echo    打包完成！
echo ====================================
echo.
echo 可执行文件位置: dist\图片管理系统.exe
echo.
echo 使用说明:
echo 1. 将 dist\图片管理系统.exe 复制到任意目录
echo 2. 首次运行会自动创建 files 文件夹和 images.db
echo 3. 如需迁移，将 exe、files 文件夹、images.db 一起复制即可
echo.
pause

