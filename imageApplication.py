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

# ------------------------------------
# 数据表设计：支持动态维度/子标签创建
# ------------------------------------
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
    parent TEXT,      -- 维度（大标签）
    name TEXT         -- 子标签
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


# ================================================
#          工具函数：查询维度、标签等
# ================================================
def get_all_dimensions():
    cursor.execute("SELECT DISTINCT parent FROM t_tags")
    rows = cursor.fetchall()
    return sorted([r[0] for r in rows if r[0]])


def get_tags_by_dimension(parent):
    cursor.execute("SELECT name FROM t_tags WHERE parent=?", (parent,))
    rows = cursor.fetchall()
    return sorted([r[0] for r in rows])


def insert_dimension(parent):
    """插入一个新维度（无子标签）"""
    if not parent:
        return

    # 插入一条无子标签的记录，维度能存下来
    cursor.execute("SELECT * FROM t_tags WHERE parent=? AND name=''", (parent,))
    if not cursor.fetchone():
        cursor.execute("INSERT INTO t_tags (parent, name) VALUES (?, '')", (parent,))
        conn.commit()


def insert_tag(parent, tag_name):
    """插入一个维度下的新子标签"""
    cursor.execute("SELECT * FROM t_tags WHERE parent=? AND name=?", (parent, tag_name))
    if not cursor.fetchone():
        cursor.execute("INSERT INTO t_tags (parent, name) VALUES (?, ?)", (parent, tag_name))
        conn.commit()


# ================================================
#                   GUI 主界面
# ================================================
class ImageManager(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("图片管理系统（动态维度 / 多标签）")
        self.geometry("900x650")

        self.tab_control = ttk.Notebook(self)
        self.tab_import = ttk.Frame(self.tab_control)
        self.tab_view = ttk.Frame(self.tab_control)
        self.tab_control.add(self.tab_import, text="导入图片")
        self.tab_control.add(self.tab_view, text="查看图片")
        self.tab_control.pack(expand=1, fill="both")

        self.selected_files = []

        self.setup_import_tab()
        self.setup_view_tab()

    # ================================================================
    #                      导入图片 TAB
    # ================================================================
    def setup_import_tab(self):
        tk.Label(self.tab_import, text="选择图片文件：").pack(pady=10)
        tk.Button(self.tab_import, text="选择图片", command=self.select_files).pack(pady=5)

        # 标签选择区
        self.tag_frame = tk.Frame(self.tab_import)
        self.tag_frame.pack(pady=15)

        # 大维度列表
        tk.Label(self.tag_frame, text="大维度列表：").grid(row=0, column=0)
        self.dim_listbox = tk.Listbox(self.tag_frame, height=8)
        self.dim_listbox.grid(row=1, column=0)
        self.dim_listbox.bind("<<ListboxSelect>>", self.update_tag_checkboxes)

        # 新增维度按钮
        tk.Button(self.tag_frame, text="新增大维度", command=self.add_dimension_window)\
            .grid(row=2, column=0, pady=5)

        # 子标签多选区
        tk.Label(self.tag_frame, text="子标签（多选）:").grid(row=0, column=1)
        self.tag_check_frame = tk.Frame(self.tag_frame)
        self.tag_check_frame.grid(row=1, column=1)

        # 新增子标签按钮
        tk.Button(self.tag_frame, text="新增子标签", command=self.add_tag_window)\
            .grid(row=2, column=1)

        tk.Button(self.tab_import, text="保存图片和标签", command=self.save_files)\
            .pack(pady=20)

        self.refresh_dimension_list()

    def select_files(self):
        files = filedialog.askopenfilenames(
            title="选择图片",
            filetypes=[("图片文件", "*.jpg *.png *.jpeg *.bmp")])
        if files:
            self.selected_files = files
            messagebox.showinfo("提示", f"已选择 {len(files)} 张图片")

    def refresh_dimension_list(self):
        """刷新左侧维度列表"""
        self.dim_listbox.delete(0, tk.END)
        for dim in get_all_dimensions():
            self.dim_listbox.insert(tk.END, dim)

    def update_tag_checkboxes(self, event):
        """当选择维度时，加载对应子标签（多选）"""
        for w in self.tag_check_frame.winfo_children():
            w.destroy()

        selection = self.dim_listbox.curselection()
        if not selection:
            return

        parent = self.dim_listbox.get(selection[0])
        tags = get_tags_by_dimension(parent)

        self.tag_vars = {}
        for idx, tag in enumerate(tags):
            if tag.strip() == "":
                continue
            var = tk.BooleanVar()
            cb = tk.Checkbutton(self.tag_check_frame, text=tag, variable=var)
            cb.grid(row=idx, column=0, sticky="w")
            self.tag_vars[tag] = var

    # ------------------ 新增大维度 ------------------
    def add_dimension_window(self):
        win = tk.Toplevel(self)
        win.title("新增大维度")

        tk.Label(win, text="维度名称:").pack(pady=5)
        dim_var = tk.StringVar()
        tk.Entry(win, textvariable=dim_var).pack(pady=5)

        def save_dim():
            val = dim_var.get().strip()
            if val:
                insert_dimension(val)
                self.refresh_dimension_list()
                win.destroy()

        tk.Button(win, text="保存", command=save_dim).pack(pady=10)

    # ------------------ 新增子标签 ------------------
    def add_tag_window(self):
        selection = self.dim_listbox.curselection()
        if not selection:
            messagebox.showwarning("警告", "请先选择大维度")
            return

        parent = self.dim_listbox.get(selection[0])

        win = tk.Toplevel(self)
        win.title("新增子标签")

        tk.Label(win, text=f"维度：{parent}").pack(pady=5)
        tk.Label(win, text="子标签名称:").pack(pady=5)

        tag_var = tk.StringVar()
        tk.Entry(win, textvariable=tag_var).pack()

        def save_tag():
            name = tag_var.get().strip()
            if name:
                insert_tag(parent, name)
                self.update_tag_checkboxes(None)
                win.destroy()

        tk.Button(win, text="保存", command=save_tag).pack(pady=10)

    # ------------------ 保存图片 + 标签 ------------------
    def save_files(self):
        if not self.selected_files:
            messagebox.showwarning("警告", "请先选择图片")
            return

        selection = self.dim_listbox.curselection()
        if not selection:
            messagebox.showwarning("警告", "请选择一个维度")
            return

        parent = self.dim_listbox.get(selection[0])

        chosen_tags = [t for t, v in self.tag_vars.items() if v.get()]
        if not chosen_tags:
            messagebox.showwarning("警告", "请至少选择一个子标签")
            return

        # 保存文件与标签
        for f in self.selected_files:
            file_name = os.path.basename(f)
            dest = os.path.join(FILES_DIR, f"{datetime.datetime.now().timestamp()}_{file_name}")
            shutil.copy(f, dest)

            cursor.execute("INSERT INTO t_files (file_name, file_path) VALUES (?, ?)", (file_name, dest))
            file_id = cursor.lastrowid

            # 保存标签关联
            for tag in chosen_tags:
                cursor.execute("SELECT tag_id FROM t_tags WHERE parent=? AND name=?", (parent, tag))
                tag_id = cursor.fetchone()[0]
                cursor.execute("INSERT INTO t_files_tags (file_id, tag_id) VALUES (?, ?)", (file_id, tag_id))

        conn.commit()
        messagebox.showinfo("成功", "图片和标签保存成功！")
        self.selected_files = []

    # ================================================================
    #                      查看图片 TAB
    # ================================================================
    def setup_view_tab(self):
        tk.Label(self.tab_view, text="输入【子标签】搜索图片:").pack(pady=10)
        self.search_var = tk.StringVar()
        tk.Entry(self.tab_view, textvariable=self.search_var).pack()

        tk.Button(self.tab_view, text="搜索", command=self.search_images).pack(pady=5)

        self.image_frame = tk.Frame(self.tab_view)
        self.image_frame.pack(fill="both", expand=True)

        tk.Button(self.tab_view, text="下载压缩包", command=self.download_zip).pack(pady=10)

        self.search_results = []

    def search_images(self):
        for w in self.image_frame.winfo_children():
            w.destroy()

        tag_name = self.search_var.get().strip()
        if not tag_name:
            messagebox.showwarning("警告", "请输入子标签名称")
            return

        cursor.execute('''
            SELECT f.file_path 
            FROM t_files f
            JOIN t_files_tags ft ON f.file_id = ft.file_id
            JOIN t_tags t ON t.tag_id = ft.tag_id
            WHERE t.name = ?
        ''', (tag_name,))

        rows = cursor.fetchall()
        self.search_results = [r[0] for r in rows]

        for idx, path in enumerate(self.search_results):
            try:
                img = Image.open(path)
                img.thumbnail((120, 120))
                photo = ImageTk.PhotoImage(img)

                lbl = tk.Label(self.image_frame, image=photo)
                lbl.image = photo
                lbl.grid(row=idx // 6, column=idx % 6, padx=5, pady=5)
                lbl.bind("<Button-1>", lambda e, p=path: self.show_full_image(p))
            except:
                continue

    def show_full_image(self, path):
        win = tk.Toplevel(self)
        win.title("查看图片")
        img = Image.open(path)
        photo = ImageTk.PhotoImage(img)
        lbl = tk.Label(win, image=photo)
        lbl.image = photo
        lbl.pack()

    def download_zip(self):
        if not self.search_results:
            messagebox.showwarning("警告", "没有图片可下载")
            return

        zip_path = filedialog.asksaveasfilename(
            defaultextension=".zip",
            filetypes=[("Zip文件", "*.zip")]
        )
        if zip_path:
            with zipfile.ZipFile(zip_path, "w") as zf:
                for p in self.search_results:
                    zf.write(p, os.path.basename(p))
            messagebox.showinfo("成功", "压缩包已生成！")


if __name__ == "__main__":
    app = ImageManager()
    app.mainloop()
