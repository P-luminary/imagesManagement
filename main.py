import os
import sqlite3
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from PIL import Image, ImageTk
import shutil
import zipfile
import datetime

# -------------------------
# 初始化工程目录和数据库
# -------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FILES_DIR = os.path.join(BASE_DIR, "files")
DB_PATH = os.path.join(BASE_DIR, "images.db")

os.makedirs(FILES_DIR, exist_ok=True)

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

# 创建表
cursor.execute('''
CREATE TABLE IF NOT EXISTS t_files (
    file_id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_name TEXT,
    file_path TEXT,
    import_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS t_tags (
    tag_id INTEGER PRIMARY KEY AUTOINCREMENT,
    parent TEXT,
    name TEXT
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS t_files_tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id INTEGER,
    tag_id INTEGER,
    FOREIGN KEY(file_id) REFERENCES t_files(file_id),
    FOREIGN KEY(tag_id) REFERENCES t_tags(tag_id)
)
''')
conn.commit()

# -------------------------
# 标签示例
# -------------------------
# 可以根据需要修改或从数据库初始化
tag_hierarchy = {
    "场景": ["室内", "室外"],
    "材质": ["水泥", "瓷砖"]
}

# 初始化标签表
for parent, children in tag_hierarchy.items():
    for child in children:
        cursor.execute("SELECT * FROM t_tags WHERE parent=? AND name=?", (parent, child))
        if not cursor.fetchone():
            cursor.execute("INSERT INTO t_tags (parent, name) VALUES (?, ?)", (parent, child))
conn.commit()


# -------------------------
# GUI主界面
# -------------------------
class ImageManager(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("图片管理系统")
        self.geometry("800x600")

        self.tab_control = ttk.Notebook(self)
        self.tab_import = ttk.Frame(self.tab_control)
        self.tab_view = ttk.Frame(self.tab_control)
        self.tab_control.add(self.tab_import, text="导入图片")
        self.tab_control.add(self.tab_view, text="查看图片")
        self.tab_control.pack(expand=1, fill="both")

        self.setup_import_tab()
        self.setup_view_tab()

    # -------------------------
    # 导入图片tab
    # -------------------------
    def setup_import_tab(self):
        self.import_label = tk.Label(self.tab_import, text="选择图片文件：")
        self.import_label.pack(pady=10)

        self.select_btn = tk.Button(self.tab_import, text="选择图片", command=self.select_files)
        self.select_btn.pack(pady=5)

        # 标签选择
        self.tag_frame = tk.Frame(self.tab_import)
        self.tag_frame.pack(pady=10)

        tk.Label(self.tag_frame, text="大维度:").grid(row=0, column=0, padx=5, pady=5)
        self.parent_var = tk.StringVar()
        self.parent_cb = ttk.Combobox(self.tag_frame, textvariable=self.parent_var, values=list(tag_hierarchy.keys()))
        self.parent_cb.grid(row=0, column=1, padx=5, pady=5)
        self.parent_cb.bind("<<ComboboxSelected>>", self.update_children)

        tk.Label(self.tag_frame, text="子维度:").grid(row=0, column=2, padx=5, pady=5)
        self.child_var = tk.StringVar()
        self.child_cb = ttk.Combobox(self.tag_frame, textvariable=self.child_var)
        self.child_cb.grid(row=0, column=3, padx=5, pady=5)

        self.save_btn = tk.Button(self.tab_import, text="保存图片和标签", command=self.save_file_and_tag)
        self.save_btn.pack(pady=20)

        self.selected_files = []

    def select_files(self):
        files = filedialog.askopenfilenames(title="选择图片", filetypes=[("图片文件", "*.jpg *.png *.jpeg *.bmp")])
        if files:
            self.selected_files = files
            messagebox.showinfo("提示", f"已选择 {len(files)} 个文件")

    def update_children(self, event):
        parent = self.parent_var.get()
        if parent in tag_hierarchy:
            self.child_cb['values'] = tag_hierarchy[parent]
            self.child_var.set(tag_hierarchy[parent][0])

    def save_file_and_tag(self):
        if not self.selected_files:
            messagebox.showwarning("警告", "请先选择图片")
            return
        if not self.parent_var.get() or not self.child_var.get():
            messagebox.showwarning("警告", "请选择标签")
            return

        parent = self.parent_var.get()
        child = self.child_var.get()

        # 获取tag_id
        cursor.execute("SELECT tag_id FROM t_tags WHERE parent=? AND name=?", (parent, child))
        tag_id = cursor.fetchone()[0]

        for f in self.selected_files:
            file_name = os.path.basename(f)
            dest_path = os.path.join(FILES_DIR, f"{datetime.datetime.now().timestamp()}_{file_name}")
            shutil.copy(f, dest_path)
            cursor.execute("INSERT INTO t_files (file_name, file_path) VALUES (?, ?)", (file_name, dest_path))
            file_id = cursor.lastrowid
            cursor.execute("INSERT INTO t_files_tags (file_id, tag_id) VALUES (?, ?)", (file_id, tag_id))
        conn.commit()
        messagebox.showinfo("成功", "图片和标签保存成功！")
        self.selected_files = []

    # -------------------------
    # 查看图片tab
    # -------------------------
    def setup_view_tab(self):
        tk.Label(self.tab_view, text="输入标签名查询图片:").pack(pady=10)
        self.search_var = tk.StringVar()
        tk.Entry(self.tab_view, textvariable=self.search_var).pack(pady=5)
        tk.Button(self.tab_view, text="搜索", command=self.search_images).pack(pady=5)

        self.image_frame = tk.Frame(self.tab_view)
        self.image_frame.pack(fill="both", expand=True)

        self.download_btn = tk.Button(self.tab_view, text="下载压缩包", command=self.download_zip)
        self.download_btn.pack(pady=10)

        self.search_results = []

    def search_images(self):
        for widget in self.image_frame.winfo_children():
            widget.destroy()

        tag_name = self.search_var.get()
        if not tag_name:
            messagebox.showwarning("警告", "请输入标签名")
            return

        cursor.execute('''
            SELECT f.file_path FROM t_files f
            JOIN t_files_tags ft ON f.file_id = ft.file_id
            JOIN t_tags t ON ft.tag_id = t.tag_id
            WHERE t.name=?
        ''', (tag_name,))
        rows = cursor.fetchall()
        self.search_results = [r[0] for r in rows]

        for idx, img_path in enumerate(self.search_results):
            try:
                img = Image.open(img_path)
                img.thumbnail((100, 100))
                photo = ImageTk.PhotoImage(img)
                lbl = tk.Label(self.image_frame, image=photo)
                lbl.image = photo
                lbl.grid(row=idx//5, column=idx%5, padx=5, pady=5)
                lbl.bind("<Button-1>", lambda e, p=img_path: self.show_full_image(p))
            except:
                continue

    def show_full_image(self, path):
        top = tk.Toplevel(self)
        top.title("查看图片")
        img = Image.open(path)
        photo = ImageTk.PhotoImage(img)
        lbl = tk.Label(top, image=photo)
        lbl.image = photo
        lbl.pack()

    def download_zip(self):
        if not self.search_results:
            messagebox.showwarning("警告", "没有图片可下载")
            return
        zip_path = filedialog.asksaveasfilename(defaultextension=".zip", filetypes=[("Zip文件","*.zip")])
        if zip_path:
            with zipfile.ZipFile(zip_path, "w") as zf:
                for file_path in self.search_results:
                    zf.write(file_path, os.path.basename(file_path))
            messagebox.showinfo("成功", "图片已打包完成！")


if __name__ == "__main__":
    app = ImageManager()
    app.mainloop()
