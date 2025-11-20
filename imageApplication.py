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
    return sorted([r[0] for r in rows if r[0] and r[0].strip() != ""])


def insert_dimension(parent):
    if not parent:
        return
    cursor.execute("SELECT * FROM t_tags WHERE parent=? AND name=''", (parent,))
    if not cursor.fetchone():
        cursor.execute("INSERT INTO t_tags (parent, name) VALUES (?, '')", (parent,))
        conn.commit()


def insert_tag(parent, tag_name):
    if not parent or not tag_name:
        return
    cursor.execute("SELECT * FROM t_tags WHERE parent=? AND name=?", (parent, tag_name))
    if not cursor.fetchone():
        cursor.execute("INSERT INTO t_tags (parent, name) VALUES (?, ?)", (parent, tag_name))
        conn.commit()


# -------------------------
# 路径解析帮助函数
# -------------------------
def resolve_path(db_path_value):
    """
    把数据库里存的路径（可能是绝对路径，也可能是相对路径）解析为可打开的绝对路径。
    规则：
      - 如果 db_path_value 是绝对路径（os.path.isabs），直接返回；
      - 否则按 BASE_DIR/db_path_value 拼接并返回。
    """
    if not db_path_value:
        return None
    if os.path.isabs(db_path_value):
        return db_path_value
    return os.path.join(BASE_DIR, db_path_value)


# ================================================================
#                      GUI 主界面（左右布局 + 折叠查看面板）
# ================================================================
class ImageManager(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("图片管理系统")
        self.geometry("1000x720")

        # 导入相关
        self.selected_files = []
        # 记忆每个维度被勾选的子标签集合（导入页） {parent: set(tag1, tag2)}
        self.selected_tags_by_dim = {}

        # 查看页相关属性：提前初始化，避免在导入页面刷新时访问未创建的 UI 引发 AttributeError
        self.view_accordion_frames = {}      # parent -> {'header_btn': btn, 'content': frame, 'open': bool}
        self.view_tag_vars = {}             # parent -> {tag: BooleanVar}
        self.view_selected_tags_by_dim = {} # parent -> set(tag)
        # UI 容器占位（实际在 setup_view_tab 创建）
        self.left_inner = None
        self.thumb_inner = None

        # 预览设置
        self.preview_size = (300, 300)
        self.preview_photo = None  # 保持引用防止被 GC
        self.preview_name_var = tk.StringVar(value="")

        # 使用 Notebook（导入 / 查看）
        self.tab_control = ttk.Notebook(self)
        self.tab_import = ttk.Frame(self.tab_control)
        self.tab_view = ttk.Frame(self.tab_control)
        self.tab_control.add(self.tab_import, text="导入图片")
        self.tab_control.add(self.tab_view, text="查看图片")
        self.tab_control.pack(expand=1, fill="both")

        # 注意：先创建查看页的控件（保证 left_inner/thumb_inner 存在），然后再创建导入页
        # 这样即便导入页 refresh 调用 view 刷新也不会出现未创建属性的访问
        self.setup_view_tab()
        self.setup_import_tab()

    # ================================================================
    #                      导入图片 TAB（左右布局）
    # ================================================================
    def setup_import_tab(self):
        container = tk.Frame(self.tab_import)
        container.pack(fill="both", expand=True, padx=10, pady=10)

        left_frame = tk.Frame(container)
        left_frame.pack(side=tk.LEFT, fill="both", expand=True)

        right_frame = tk.Frame(container, width=360)
        right_frame.pack(side=tk.RIGHT, fill="y")
        right_frame.pack_propagate(False)

        # ----------------- 左侧（维度 + 子标签 管理） -----------------
        tk.Label(left_frame, text="大维度列表：").grid(row=0, column=0, sticky="w")
        self.dim_listbox = tk.Listbox(left_frame, height=18, exportselection=False)
        self.dim_listbox.grid(row=1, column=0, rowspan=10, sticky="nwes", padx=(0, 10))
        self.dim_listbox.bind("<<ListboxSelect>>", self.update_tag_checkboxes)

        btn_dim_frame = tk.Frame(left_frame)
        btn_dim_frame.grid(row=11, column=0, pady=6, sticky="w")
        tk.Button(btn_dim_frame, text="新增大维度", command=self.add_dimension_window).pack(side=tk.LEFT, padx=4)
        tk.Button(btn_dim_frame, text="编辑大维度", command=self.edit_dimension_window).pack(side=tk.LEFT, padx=4)
        tk.Button(btn_dim_frame, text="删除大维度", command=self.delete_dimension).pack(side=tk.LEFT, padx=4)

        tk.Label(left_frame, text="子标签（多选）:").grid(row=0, column=1, sticky="w")
        self.tag_check_frame = tk.Frame(left_frame)
        self.tag_check_frame.grid(row=1, column=1, rowspan=10, sticky="nw")

        btn_tag_frame = tk.Frame(left_frame)
        btn_tag_frame.grid(row=11, column=1, pady=6, sticky="w")
        tk.Button(btn_tag_frame, text="新增子标签", command=self.add_tag_window).pack(side=tk.LEFT, padx=4)
        tk.Button(btn_tag_frame, text="编辑子标签", command=self.edit_tag_window).pack(side=tk.LEFT, padx=4)
        tk.Button(btn_tag_frame, text="删除子标签", command=self.delete_tag).pack(side=tk.LEFT, padx=4)

        left_frame.grid_columnconfigure(0, weight=0)
        left_frame.grid_columnconfigure(1, weight=1)
        left_frame.grid_rowconfigure(1, weight=1)

        # ----------------- 右侧（图片预览 + 操作） -----------------
        preview_container = tk.Frame(right_frame, width=self.preview_size[0], height=self.preview_size[1], bd=1, relief="solid")
        preview_container.pack(pady=10)
        preview_container.pack_propagate(False)
        self.preview_label = tk.Label(preview_container, text="未选择图片", anchor="center")
        self.preview_label.pack(expand=True, fill="both")

        tk.Label(right_frame, textvariable=self.preview_name_var, wraplength=320, anchor="w", justify="left").pack(pady=(6, 0), padx=6, fill="x")

        op_frame = tk.Frame(right_frame)
        op_frame.pack(pady=12)
        tk.Button(op_frame, text="选择图片", command=self.select_files).pack(side=tk.LEFT, padx=6)
        tk.Button(op_frame, text="保存图片和标签", command=self.save_files).pack(side=tk.LEFT, padx=6)

        # refresh dims (safe: refresh_view_tags checks left_inner existence)
        self.refresh_dimension_list()

    # ------------------ 选择图片 ------------------
    def select_files(self):
        files = filedialog.askopenfilenames(
            title="选择图片",
            filetypes=[("图片文件", "*.jpg *.png *.jpeg *.bmp")])
        if files:
            self.selected_files = files
            first = files[0]
            self.show_preview(first)
            self.preview_name_var.set(os.path.basename(first))
            messagebox.showinfo("提示", f"已选择 {len(files)} 张图片（仅预览第一张）")

    def show_preview(self, image_path):
        try:
            img = Image.open(image_path)
            img.thumbnail(self.preview_size)
            bg = Image.new("RGBA", self.preview_size, (240, 240, 240, 255))
            w, h = img.size
            x = (self.preview_size[0] - w) // 2
            y = (self.preview_size[1] - h) // 2
            bg.paste(img, (x, y))
            self.preview_photo = ImageTk.PhotoImage(bg)
            self.preview_label.config(image=self.preview_photo, text="")
        except Exception:
            self.preview_label.config(image="", text="无法打开图片")
            self.preview_name_var.set("")

    # ------------------ 刷新维度列表 ------------------
    def refresh_dimension_list(self):
        self.dim_listbox.delete(0, tk.END)
        for dim in get_all_dimensions():
            self.dim_listbox.insert(tk.END, dim)
        self.update_tag_checkboxes(None)
        # refresh view tags (safe: function checks existence of left_inner)
        self.refresh_view_tags()

    # ------------------ 更新子标签勾选状态（导入页） ------------------
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

    # ------------------ 新增/编辑/删除 维度/子标签（导入页操作会刷新查看页标签） ------------------
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
                if old_name in self.selected_tags_by_dim:
                    self.selected_tags_by_dim[new_name] = self.selected_tags_by_dim.pop(old_name)
                self.refresh_dimension_list()
                win.destroy()

        tk.Button(win, text="保存", command=save_edit).pack(pady=10)

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
                self.selected_tags_by_dim.setdefault(parent, set())
                self.selected_tags_by_dim[parent].discard(name)
                self.update_tag_checkboxes(None)
                # 刷新查看页的标签展示（safe）
                self.refresh_view_tags()
                win.destroy()

        tk.Button(win, text="保存", command=save_tag).pack(pady=10)

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
                self.refresh_view_tags()
                win.destroy()

        tk.Button(win, text="保存", command=save_edit_tag).pack(pady=10)

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
                self.refresh_view_tags()
                win.destroy()

        tk.Button(win, text="删除", command=confirm_delete).pack(pady=10)

    # ------------------ 保存图片 + 标签（导入页，保存相对路径） ------------------
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
            timestamp = datetime.datetime.now().timestamp()
            new_filename = f"{timestamp}_{file_name}"
            dest_abs = os.path.join(FILES_DIR, new_filename)
            shutil.copy(f, dest_abs)

            rel_path = os.path.relpath(dest_abs, BASE_DIR)
            cursor.execute("INSERT INTO t_files (file_name, file_path) VALUES (?, ?)", (file_name, rel_path))
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
        self.selected_tags_by_dim = {}
        self.update_tag_checkboxes(None)
        self.preview_label.config(image="", text="未选择图片")
        self.preview_photo = None
        self.preview_name_var.set("")

    # ================================================================
    #                      查看图片 TAB（折叠维度面板 + AND/OR）
    # ================================================================
    def setup_view_tab(self):
        # top controls: mode + buttons
        top_frame = tk.Frame(self.tab_view)
        top_frame.pack(fill="x", pady=6, padx=6)

        tk.Label(top_frame, text="搜索模式：").pack(side=tk.LEFT, padx=(2, 6))
        self.search_mode_var = tk.StringVar(value="OR")
        tk.Radiobutton(top_frame, text="OR（任一）", variable=self.search_mode_var, value="OR").pack(side=tk.LEFT, padx=4)
        tk.Radiobutton(top_frame, text="AND（全部）", variable=self.search_mode_var, value="AND").pack(side=tk.LEFT, padx=4)

        tk.Button(top_frame, text="搜索", command=self.search_images_by_selected).pack(side=tk.RIGHT, padx=6)
        tk.Button(top_frame, text="清除选择", command=self.clear_view_selections).pack(side=tk.RIGHT, padx=6)

        # main view area: left accordion tags, right thumbnails
        main = tk.Frame(self.tab_view)
        main.pack(fill="both", expand=True, padx=6, pady=6)

        # left: accordion for dimensions & tags (scrollable)
        left_panel = tk.Frame(main, width=320)
        left_panel.pack(side=tk.LEFT, fill="y")
        left_panel.pack_propagate(False)

        # add a canvas + scrollbar to left_panel to support many dims
        self.left_canvas = tk.Canvas(left_panel, borderwidth=0)
        vsb = tk.Scrollbar(left_panel, orient="vertical", command=self.left_canvas.yview)
        # left_inner is the frame that will hold accordion content
        self.left_inner = tk.Frame(self.left_canvas)

        self.left_inner.bind(
            "<Configure>",
            lambda e: self.left_canvas.configure(scrollregion=self.left_canvas.bbox("all"))
        )
        self.left_canvas.create_window((0, 0), window=self.left_inner, anchor="nw")
        self.left_canvas.configure(yscrollcommand=vsb.set)

        self.left_canvas.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        # right: thumbnails area (scrollable)
        right_panel = tk.Frame(main)
        right_panel.pack(side=tk.LEFT, fill="both", expand=True)

        # thumbnail canvas with scrollbar
        self.thumb_canvas = tk.Canvas(right_panel)
        self.thumb_vsb = tk.Scrollbar(right_panel, orient="vertical", command=self.thumb_canvas.yview)
        self.thumb_inner = tk.Frame(self.thumb_canvas)

        self.thumb_inner.bind(
            "<Configure>",
            lambda e: self.thumb_canvas.configure(scrollregion=self.thumb_canvas.bbox("all"))
        )
        self.thumb_canvas.create_window((0, 0), window=self.thumb_inner, anchor="nw")
        self.thumb_canvas.configure(yscrollcommand=self.thumb_vsb.set)

        self.thumb_canvas.pack(side="left", fill="both", expand=True)
        self.thumb_vsb.pack(side="right", fill="y")

        # download button below
        bottom_frame = tk.Frame(self.tab_view)
        bottom_frame.pack(fill="x", pady=(4, 8))
        tk.Button(bottom_frame, text="下载选中结果为ZIP", command=self.download_zip).pack(side=tk.RIGHT, padx=10)

        # initial build of accordion
        self.refresh_view_tags()

        # search results list (absolute paths)
        self.search_results = []

    def refresh_view_tags(self):
        """
        (Re)build the accordion left panel based on current t_tags.
        Keeps previous checked state when possible.

        This function is safe to call even before the view UI is constructed:
        - if left_inner is None (view not initialized), just return early.
        """
        # If view panel not yet created, skip
        if self.left_inner is None:
            return

        # save previous selected states
        prev = {}
        for parent, tagmap in self.view_tag_vars.items():
            prev[parent] = {t: v.get() for t, v in tagmap.items()}

        # clear existing widgets
        for w in self.left_inner.winfo_children():
            w.destroy()
        self.view_accordion_frames.clear()
        self.view_tag_vars.clear()

        dims = get_all_dimensions()
        if not dims:
            tk.Label(self.left_inner, text="暂无维度/标签，先到导入页新增标签").pack(anchor="w", padx=6, pady=6)
            return

        for parent in dims:
            # header (acts as toggle)
            header = tk.Frame(self.left_inner)
            header.pack(fill="x", pady=(2, 2))
            btn = tk.Button(header, text=f"▸  {parent}", anchor="w", relief="flat")
            btn.pack(fill="x")

            # content frame with checkboxes (initially hidden)
            content = tk.Frame(self.left_inner, relief="groove", bd=0)
            content.pack(fill="x", padx=8, pady=(0, 4))
            content.pack_forget()  # hide initially

            # build tag checkboxes
            tags = get_tags_by_dimension(parent)
            tag_vars = {}
            for idx, tag in enumerate(tags):
                var = tk.BooleanVar(value=prev.get(parent, {}).get(tag, False))
                cb = tk.Checkbutton(content, text=tag, variable=var,
                                    command=lambda p=parent, t=tag, v=var: self._on_view_tag_toggle(p, t, v))
                cb.grid(row=idx, column=0, sticky="w", padx=6, pady=2)
                tag_vars[tag] = var

            self.view_accordion_frames[parent] = {'header_btn': btn, 'content': content, 'open': False}
            self.view_tag_vars[parent] = tag_vars

            # toggle action
            def make_toggle(p=parent):
                def toggle():
                    item = self.view_accordion_frames[p]
                    if item['open']:
                        item['content'].pack_forget()
                        item['header_btn'].config(text=f"▸  {p}")
                        item['open'] = False
                    else:
                        item['content'].pack(fill="x", padx=8, pady=(0, 4))
                        item['header_btn'].config(text=f"▾  {p}")
                        item['open'] = True
                return toggle

            btn.config(command=make_toggle(parent))

        # rebuild view_selected_tags_by_dim
        self.view_selected_tags_by_dim = {}
        for parent, tagmap in self.view_tag_vars.items():
            self.view_selected_tags_by_dim[parent] = set(t for t, v in tagmap.items() if v.get())

    def _on_view_tag_toggle(self, parent, tag, var):
        if var.get():
            self.view_selected_tags_by_dim.setdefault(parent, set()).add(tag)
        else:
            if parent in self.view_selected_tags_by_dim:
                self.view_selected_tags_by_dim[parent].discard(tag)

    def clear_view_selections(self):
        for parent, tagmap in self.view_tag_vars.items():
            for tag, var in tagmap.items():
                var.set(False)
        self.view_selected_tags_by_dim = {}
        # clear thumbnails
        if self.thumb_inner:
            for w in self.thumb_inner.winfo_children():
                w.destroy()
        self.search_results = []

    # ================================================================
    # 更新 search_images_by_selected，让缩略图可选中
    # ================================================================
    def search_images_by_selected(self):
        # collect selected tags across all dims
        selected = []
        for parent, tagvars in self.view_tag_vars.items():
            for tag, var in tagvars.items():
                if var.get():
                    selected.append((parent, tag))

        if not selected:
            messagebox.showwarning("提示", "请在左侧选择至少一个子标签再搜索")
            return

        # map selected tags to tag_ids
        tag_ids = []
        for parent, tag in selected:
            cursor.execute("SELECT tag_id FROM t_tags WHERE parent=? AND name=?", (parent, tag))
            r = cursor.fetchone()
            if r:
                tag_ids.append(r[0])

        if not tag_ids:
            messagebox.showinfo("提示", "所选标签未在数据库中找到（已被删除？）")
            return

        mode = self.search_mode_var.get()
        placeholder = ",".join("?" * len(tag_ids))
        if mode == "OR":
            sql = f"""
                SELECT DISTINCT f.file_id, f.file_path
                FROM t_files f
                JOIN t_files_tags ft ON f.file_id = ft.file_id
                WHERE ft.tag_id IN ({placeholder})
            """
        else:
            sql = f"""
                SELECT f.file_id, f.file_path
                FROM t_files f
                JOIN t_files_tags ft ON f.file_id = ft.file_id
                WHERE ft.tag_id IN ({placeholder})
                GROUP BY f.file_id
                HAVING COUNT(DISTINCT ft.tag_id) = {len(tag_ids)}
            """
        cursor.execute(sql, tag_ids)
        rows = cursor.fetchall()

        # resolve and filter existing paths
        abs_paths = [resolve_path(r[1]) for r in rows if r[1] and os.path.exists(resolve_path(r[1]))]

        # clear previous thumbnails
        for w in self.thumb_inner.winfo_children():
            w.destroy()

        if not abs_paths:
            messagebox.showinfo("提示", "未找到匹配且存在的图片文件")
            self.search_results = []
            self.thumb_selected_vars = {}
            return

        self.search_results = abs_paths
        self.thumb_selected_vars = {}  # 保存每个缩略图选中状态

        # populate thumbnail grid in thumb_inner
        cols = 6
        for idx, path in enumerate(self.search_results):
            try:
                img = Image.open(path)
                img.thumbnail((120, 120))
                photo = ImageTk.PhotoImage(img)

                frame = tk.Frame(self.thumb_inner, bd=1, relief="solid")
                frame.grid(row=idx // cols, column=idx % cols, padx=6, pady=6)

                lbl = tk.Label(frame, image=photo)
                lbl.image = photo
                lbl.pack()
                lbl.bind("<Double-Button-1>", lambda e, p=path: self.show_full_image(p))

                # 勾选框，默认选中
                var = tk.BooleanVar(value=True)
                chk = tk.Checkbutton(frame, text=os.path.basename(path), variable=var, anchor="w", justify="left")
                chk.pack(fill="x")
                self.thumb_selected_vars[path] = var
            except Exception:
                continue

    def show_full_image(self, path):
        abs_p = resolve_path(path) if not os.path.isabs(path) else path
        try:
            win = tk.Toplevel(self)
            win.title("查看图片")
            img = Image.open(abs_p)
            # scale large image to reasonable window if necessary
            w, h = img.size
            max_w, max_h = 1000, 800
            if w > max_w or h > max_h:
                img.thumbnail((max_w, max_h))
            photo = ImageTk.PhotoImage(img)
            lbl = tk.Label(win, image=photo)
            lbl.image = photo
            lbl.pack()
        except Exception:
            messagebox.showerror("错误", "打开图片失败（文件可能不存在）")


    # ================================================================
    # 修改 download_zip，只下载被选中的图片
    # ================================================================
    def download_zip(self):
        if not hasattr(self, "thumb_selected_vars") or not self.thumb_selected_vars:
            messagebox.showwarning("警告", "没有图片可下载")
            return

        selected_paths = [p for p, var in self.thumb_selected_vars.items() if var.get()]
        if not selected_paths:
            messagebox.showwarning("警告", "没有选中图片")
            return

        zip_path = filedialog.asksaveasfilename(
            defaultextension=".zip",
            filetypes=[("Zip文件", "*.zip")]
        )
        if zip_path:
            with zipfile.ZipFile(zip_path, "w") as zf:
                for p in selected_paths:
                    zf.write(p, os.path.basename(p))
            messagebox.showinfo("成功", "压缩包已生成！")


if __name__ == "__main__":
    app = ImageManager()
    app.mainloop()
