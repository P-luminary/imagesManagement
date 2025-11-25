#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
图片管理系统 - 打包脚本
使用 PyInstaller 将 Python 程序打包成独立的 exe 可执行文件
"""

import os
import shutil
import subprocess
import sys

def print_step(step, total, message):
    """打印步骤信息"""
    print(f"\n{'='*50}")
    print(f"[{step}/{total}] {message}")
    print('='*50)

def main():
    print("\n" + "="*50)
    print("    图片管理系统 - 打包工具")
    print("="*50)
    
    # Step 1: 检查和安装依赖
    print_step(1, 5, "检查依赖...")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "--upgrade", "pip"])
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
        print("✓ 依赖安装完成")
    except subprocess.CalledProcessError as e:
        print(f"✗ 依赖安装失败: {e}")
        return False
    
    # Step 2: 清理旧文件
    print_step(2, 5, "清理旧文件...")
    dirs_to_clean = ["dist", "build"]
    for dir_name in dirs_to_clean:
        if os.path.exists(dir_name):
            shutil.rmtree(dir_name)
            print(f"✓ 已删除 {dir_name} 目录")
    
    # 删除 .spec 文件
    for file in os.listdir("."):
        if file.endswith(".spec"):
            os.remove(file)
            print(f"✓ 已删除 {file}")
    
    # Step 3: 打包 exe
    print_step(3, 5, "开始打包 exe...")
    pyinstaller_cmd = [
        "pyinstaller",
        "--name=图片管理系统",
        "--onefile",
        "--windowed",
        "--noconfirm",
        "imageApplication.py"
    ]
    
    try:
        subprocess.check_call(pyinstaller_cmd)
        print("✓ exe 打包完成")
    except subprocess.CalledProcessError as e:
        print(f"✗ 打包失败: {e}")
        return False
    
    # Step 4: 复制数据文件
    print_step(4, 5, "复制必要文件...")
    
    # 创建 files 目录
    dist_files = os.path.join("dist", "files")
    os.makedirs(dist_files, exist_ok=True)
    print(f"✓ 已创建 {dist_files} 目录")
    
    # 复制现有图片（如果有）
    if os.path.exists("files") and os.listdir("files"):
        for file in os.listdir("files"):
            src = os.path.join("files", file)
            dst = os.path.join(dist_files, file)
            shutil.copy2(src, dst)
        print(f"✓ 已复制 {len(os.listdir('files'))} 个图片文件")
    else:
        print("ℹ files 目录为空或不存在")
    
    # 复制数据库（如果有）
    if os.path.exists("images.db"):
        shutil.copy2("images.db", os.path.join("dist", "images.db"))
        print("✓ 已复制 images.db")
    else:
        print("ℹ images.db 不存在（首次运行会自动创建）")
    
    # Step 5: 创建使用说明
    print_step(5, 5, "生成使用说明...")
    readme_content = """
使用说明
========

1. 运行 "图片管理系统.exe" 启动程序
2. 程序会自动在同目录下创建 files 文件夹和 images.db 数据库
3. 如需迁移到其他电脑，将以下文件一起复制：
   - 图片管理系统.exe
   - files 文件夹
   - images.db 数据库文件

注意：三者必须在同一目录！
"""
    
    readme_path = os.path.join("dist", "使用说明.txt")
    with open(readme_path, "w", encoding="utf-8") as f:
        f.write(readme_content)
    print(f"✓ 已生成 {readme_path}")
    
    # 完成
    print("\n" + "="*50)
    print("    打包完成！")
    print("="*50)
    print(f"\n可执行文件位置: dist{os.sep}图片管理系统.exe")
    print("\n可以将 dist 文件夹整体移动到其他位置或电脑使用")
    print("\n" + "="*50 + "\n")
    
    return True

if __name__ == "__main__":
    try:
        success = main()
        if not success:
            sys.exit(1)
    except KeyboardInterrupt:
        print("\n\n打包已取消")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ 发生错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

