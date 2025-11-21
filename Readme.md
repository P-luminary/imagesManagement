代码和db以及file文件都处于同级目录下
项目GitHub地址：https://github.com/P-luminary/imagesManagement
clone命令：git clone https://github.com/P-luminary/imagesManagement.git

项目文件结构如下：
【项目工程】
|
|
|--files(这里面保存图片文件)
|--xxx.py
|--images.db
|--Readme.md



项目架构
数据库结构：
  t_files - 存储图片文件信息（ID、文件名、路径、导入时间）
  t_tags - 存储标签（parent=大维度，name=子标签）
 t_files_tags - 文件与标签的多对多关联表
功能模块：
导入图片标签页：
 左侧：维度和子标签管理（增删改操作）
 右侧：图片预览区
 保存时图片会复制到 files/ 目录，文件名添加时间戳前缀
 路径以相对路径形式存储到数据库
查看图片标签页：
 左侧：折叠式手风琴面板，显示所有维度和子标签（多选）
 右侧：6列网格缩略图展示
 支持 OR/AND 搜索模式
 缩略图默认全选，可取消勾选
 双击查看大图
 可将选中图片打包下载为 ZIP
技术特点：
 使用 Tkinter + PIL/Pillow 构建 GUI
 Canvas + Scrollbar 实现滚动区域
 路径解析函数支持相对/绝对路径
 我已经理解了项目结构和功能逻辑。请