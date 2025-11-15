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
    return sorted([r[0] for r in rows if r[0].strip() != ""])


def insert_dimension(parent):
    if not parent:
        return
    cursor.execute("SELECT * FROM t_tags WHERE parent=? AND name=''", (parent,))
    if not cursor.fetchone():
        cursor.execute("INSERT INTO t_tags (parent, name) VALUES (?, '')", (parent,))
        conn.commit()


def insert_tag(parent, tag_name):
    cursor.execute("SELECT * FROM t_tags WHERE parent=? AND name=?", (parent, tag_name))
    if not cursor.fetchone():
        cursor.execute("INSERT INTO t_tags (parent, name) VALUES (?, ?)", (parent, tag_name))
        conn.commit()


# ================================================================
#                      GUI 主界面
# ================================================================
class ImageManager(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("图片管理系统（动态维度 / 多标签）")
        self.geometry("900x720")

        self.selected_files = []
        # 记忆每个维度被勾选的子标签集合 {parent: set(tag1, tag2)}
        self.selected_tags_by_dim = {}

        self.tab_control = ttk.Notebook(self)
        self.tab_import = ttk.Frame(self.tab_control)
        self.tab_view = ttk.Frame(self.tab_control)
        self.tab_control.add(self.tab_import, text="导入图片")
        self.tab_control.add(self.tab_view, text="查看图片")
        self.tab_control.pack(expand=1, fill="both")

        # 预留并创建图片预览区（固定大小 300x300）
        self.preview_size = (300, 300)
        self.preview_photo = None  # 保持引用防止被 GC
        self.setup_import_tab()
        self.setup_view_tab()

    # ================================================================
    #                      导入图片 TAB
    # ================================================================
    def setup_import_tab(self):
        # 顶部预留图片区（固定尺寸）
        preview_frame = tk.Frame(self.tab_import, width=self.preview_size[0], height=self.preview_size[1], bd=1, relief="solid")
        preview_frame.pack(pady=10)
        preview_frame.pack_propagate(False)  # 固定尺寸，不随内容改变

        self.preview_label = tk.Label(preview_frame, text="未选择图片", anchor="center")
        self.preview_label.pack(expand=True, fill="both")

        # 选择图片按钮（放在预留区下方一行）
        btn_frame = tk.Frame(self.tab_import)
        btn_frame.pack(pady=6)
        tk.Button(btn_frame, text="选择图片", command=self.select_files).pack(side=tk.LEFT, padx=6)
        tk.Button(btn_frame, text="保存图片和标签", command=self.save_files).pack(side=tk.LEFT, padx=6)

        # 主体：标签选择区（不随预览区移动）
        self.tag_frame = tk.Frame(self.tab_import)
        self.tag_frame.pack(pady=10, fill="both", expand=False)

        # 大维度列表
        tk.Label(self.tag_frame, text="大维度列表：").grid(row=0, column=0, sticky="w")
        self.dim_listbox = tk.Listbox(self.tag_frame, height=8)
        self.dim_listbox.grid(row=1, column=0, sticky="nw")
        self.dim_listbox.bind("<<ListboxSelect>>", self.update_tag_checkboxes)

        # 大维度按钮
        tk.Button(self.tag_frame, text="新增大维度", command=self.add_dimension_window).grid(row=2, column=0, pady=3, sticky="w")
        tk.Button(self.tag_frame, text="编辑大维度", command=self.edit_dimension_window).grid(row=3, column=0, pady=3, sticky="w")
        tk.Button(self.tag_frame, text="删除大维度", command=self.delete_dimension).grid(row=4, column=0, pady=3, sticky="w")

        # 子标签多选区
        tk.Label(self.tag_frame, text="子标签（多选）:").grid(row=0, column=1, sticky="w")
        self.tag_check_frame = tk.Frame(self.tag_frame)
        self.tag_check_frame.grid(row=1, column=1, sticky="nw", padx=10)

        # 子标签按钮
        tk.Button(self.tag_frame, text="新增子标签", command=self.add_tag_window).grid(row=2, column=1, pady=3, sticky="w")
        tk.Button(self.tag_frame, text="编辑子标签", command=self.edit_tag_window).grid(row=3, column=1, pady=3, sticky="w")
        tk.Button(self.tag_frame, text="删除子标签", command=self.delete_tag).grid(row=4, column=1, pady=3, sticky="w")

        # refresh dims
        self.refresh_dimension_list()

    # ------------------ 选择图片 ------------------
    def select_files(self):
        files = filedialog.askopenfilenames(
            title="选择图片",
            filetypes=[("图片文件", "*.jpg *.png *.jpeg *.bmp")])
        if files:
            self.selected_files = files
            # 只展示第一张（要求）
            first = files[0]
            self.show_preview(first)
            messagebox.showinfo("提示", f"已选择 {len(files)} 张图片（仅预览第一张）")

    def show_preview(self, image_path):
        """在固定预览区显示图片，按比例缩放到 preview_size"""
        try:
            img = Image.open(image_path)
            img.thumbnail(self.preview_size)  # 等比缩放到框内
            # create a background image with desired size and paste centered (to keep consistent frame)
            bg = Image.new("RGBA", self.preview_size, (240, 240, 240, 255))
            w, h = img.size
            x = (self.preview_size[0] - w) // 2
            y = (self.preview_size[1] - h) // 2
            bg.paste(img, (x, y))
            self.preview_photo = ImageTk.PhotoImage(bg)
            self.preview_label.config(image=self.preview_photo, text="")
        except Exception as e:
            # 回退到文本提示
            self.preview_label.config(image="", text="无法打开图片")

    # ------------------ 刷新维度列表 ------------------
    def refresh_dimension_list(self):
        self.dim_listbox.delete(0, tk.END)
        for dim in get_all_dimensions():
            self.dim_listbox.insert(tk.END, dim)
        # 更新右侧勾选面板（保持记忆）
        self.update_tag_checkboxes(None)

    # ------------------ 更新子标签勾选状态 ------------------
    def update_tag_checkboxes(self, event):
        for w in self.tag_check_frame.winfo_children():
            w.destroy()

        selection = self.dim_listbox.curselection()
        if not selection:
            return

        parent = self.dim_listbox.get(selection[0])
        tags = get_tags_by_dimension(parent)

        self.tag_vars = {}
        selected_tags = self.selected_tags_by_dim.get(parent, set())

        for idx, tag in enumerate(tags):
            var = tk.BooleanVar()
            if tag in selected_tags:
                var.set(True)
            cb = tk.Checkbutton(self.tag_check_frame, text=tag, variable=var,
                                command=lambda p=parent, t=tag, v=var: self.update_selected_tags(p, t, v))
            cb.grid(row=idx, column=0, sticky="w")
            self.tag_vars[tag] = var

    def update_selected_tags(self, parent, tag, var):
        if parent not in self.selected_tags_by_dim:
            self.selected_tags_by_dim[parent] = set()
        if var.get():
            self.selected_tags_by_dim[parent].add(tag)
        else:
            self.selected_tags_by_dim[parent].discard(tag)

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

    # ------------------ 编辑大维度 ------------------
    def edit_dimension_window(self):
        selection = self.dim_listbox.curselection()
        if not selection:
            messagebox.showwarning("警告", "请选择大维度")
            return
        old_name = self.dim_listbox.get(selection[0])
        win = tk.Toplevel(self)
        win.title("编辑大维度")

        tk.Label(win, text="修改维度名称:").pack(pady=5)
        dim_var = tk.StringVar(value=old_name)
        tk.Entry(win, textvariable=dim_var).pack(pady=5)

        def save_edit():
            new_name = dim_var.get().strip()
            if new_name and new_name != old_name:
                cursor.execute("UPDATE t_tags SET parent=? WHERE parent=?", (new_name, old_name))
                conn.commit()
                # 更新记忆状态
                if old_name in self.selected_tags_by_dim:
                    self.selected_tags_by_dim[new_name] = self.selected_tags_by_dim.pop(old_name)
                self.refresh_dimension_list()
                win.destroy()

        tk.Button(win, text="保存", command=save_edit).pack(pady=10)

    # ------------------ 删除大维度 ------------------
    def delete_dimension(self):
        selection = self.dim_listbox.curselection()
        if not selection:
            messagebox.showwarning("警告", "请选择大维度")
            return
        dim_name = self.dim_listbox.get(selection[0])
        if messagebox.askyesno("确认", f"确定删除维度【{dim_name}】及其所有子标签吗？"):
            cursor.execute("SELECT tag_id FROM t_tags WHERE parent=?", (dim_name,))
            tag_ids = [r[0] for r in cursor.fetchall()]
            if tag_ids:
                cursor.execute(f"DELETE FROM t_files_tags WHERE tag_id IN ({','.join(['?']*len(tag_ids))})", tag_ids)
            cursor.execute("DELETE FROM t_tags WHERE parent=?", (dim_name,))
            conn.commit()
            self.selected_tags_by_dim.pop(dim_name, None)
            self.refresh_dimension_list()

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
                # 初始化记忆为未选中
                self.selected_tags_by_dim.setdefault(parent, set())
                self.selected_tags_by_dim[parent].discard(name)
                self.update_tag_checkboxes(None)
                win.destroy()

        tk.Button(win, text="保存", command=save_tag).pack(pady=10)

    # ------------------ 编辑子标签 ------------------
    def edit_tag_window(self):
        selection = self.dim_listbox.curselection()
        if not selection:
            messagebox.showwarning("警告", "请选择大维度")
            return
        parent = self.dim_listbox.get(selection[0])
        tags = get_tags_by_dimension(parent)
        if not tags:
            messagebox.showwarning("警告", "该维度没有子标签")
            return
        win = tk.Toplevel(self)
        win.title("编辑子标签")
        tk.Label(win, text=f"维度：{parent}").pack(pady=5)
        tk.Label(win, text="选择子标签:").pack(pady=5)
        tag_var = tk.StringVar(value=tags[0])
        tk.OptionMenu(win, tag_var, *tags).pack(pady=5)
        tk.Label(win, text="修改为:").pack(pady=5)
        new_var = tk.StringVar()
        tk.Entry(win, textvariable=new_var).pack(pady=5)

        def save_edit_tag():
            old_name = tag_var.get()
            new_name = new_var.get().strip()
            if new_name and new_name != old_name:
                cursor.execute("UPDATE t_tags SET name=? WHERE parent=? AND name=?", (new_name, parent, old_name))
                conn.commit()
                if parent in self.selected_tags_by_dim and old_name in self.selected_tags_by_dim[parent]:
                    self.selected_tags_by_dim[parent].remove(old_name)
                    self.selected_tags_by_dim[parent].add(new_name)
                self.update_tag_checkboxes(None)
                win.destroy()

        tk.Button(win, text="保存", command=save_edit_tag).pack(pady=10)

    # ------------------ 删除子标签 ------------------
    def delete_tag(self):
        selection = self.dim_listbox.curselection()
        if not selection:
            messagebox.showwarning("警告", "请先选择大维度")
            return
        parent = self.dim_listbox.get(selection[0])
        tags = get_tags_by_dimension(parent)
        if not tags:
            messagebox.showwarning("警告", "该维度没有子标签")
            return
        win = tk.Toplevel(self)
        win.title("删除子标签")
        tk.Label(win, text=f"维度：{parent}").pack(pady=5)
        tk.Label(win, text="选择子标签:").pack(pady=5)
        tag_var = tk.StringVar(value=tags[0])
        tk.OptionMenu(win, tag_var, *tags).pack(pady=5)

        def confirm_delete():
            tname = tag_var.get()
            if tname and messagebox.askyesno("确认", f"确定删除子标签【{tname}】吗？"):
                cursor.execute("SELECT tag_id FROM t_tags WHERE parent=? AND name=?", (parent, tname))
                r = cursor.fetchone()
                if r:
                    tag_id = r[0]
                    cursor.execute("DELETE FROM t_files_tags WHERE tag_id=?", (tag_id,))
                    cursor.execute("DELETE FROM t_tags WHERE tag_id=?", (tag_id,))
                    conn.commit()
                    if parent in self.selected_tags_by_dim:
                        self.selected_tags_by_dim[parent].discard(tname)
                self.update_tag_checkboxes(None)
                win.destroy()

        tk.Button(win, text="删除", command=confirm_delete).pack(pady=10)

    # ------------------ 保存图片 + 标签 ------------------
    def save_files(self):
        if not self.selected_files:
            messagebox.showwarning("警告", "请先选择图片")
            return

        chosen_tags = []
        for parent, tags in self.selected_tags_by_dim.items():
            chosen_tags.extend([(parent, t) for t in tags])

        if not chosen_tags:
            messagebox.showwarning("警告", "请至少选择一个维度或子标签")
            return

        for f in self.selected_files:
            file_name = os.path.basename(f)
            dest = os.path.join(FILES_DIR, f"{datetime.datetime.now().timestamp()}_{file_name}")
            shutil.copy(f, dest)

            cursor.execute("INSERT INTO t_files (file_name, file_path) VALUES (?, ?)", (file_name, dest))
            file_id = cursor.lastrowid

            for parent, tag in chosen_tags:
                cursor.execute("SELECT tag_id FROM t_tags WHERE parent=? AND name=?", (parent, tag))
                r = cursor.fetchone()
                if r:
                    tag_id = r[0]
                    cursor.execute("INSERT INTO t_files_tags (file_id, tag_id) VALUES (?, ?)", (file_id, tag_id))

        conn.commit()
        messagebox.showinfo("成功", "图片和标签保存成功！")
        self.selected_files = []
        # 保存完清空勾选状态
        self.selected_tags_by_dim = {}
        self.update_tag_checkboxes(None)
        # 清除预览显示（保留占位）
        self.preview_label.config(image="", text="未选择图片")
        self.preview_photo = None

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
