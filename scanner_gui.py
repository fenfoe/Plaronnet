import os
import sys
import json
import shutil
import tempfile
import webbrowser
import concurrent.futures
from datetime import datetime

from PyQt5.QtWidgets import (
    QApplication, QWidget, QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTableWidget, QTableWidgetItem, QCheckBox, QTextEdit,
    QFileDialog, QMessageBox, QHeaderView, QSpinBox, QTabWidget,
    QToolButton, QListWidget, QTextBrowser, QSplitter, QToolBar, QAction, QInputDialog
)
from PyQt5.QtCore import QThread, pyqtSignal, Qt

from core.detailed_scan import DETAILED_SCAN_MODULES
from core.beauty import render_host_page_html, CYBERPUNK_QSS
from core.db_functions import DB_PATH, init_db, save_entry_to_db, search_db, db_stats
from core.scan import COMMON_PORTS, WEB_PORTS, set_tor_enabled, scan_host, expand_targets
from core.graph import (
    AddEntityDialog, InteractiveGraphScene, GraphView, EntityNode,
    SideDetailsPanel, raw_json_to_graph, new_node_id
)


class ScanWorker(QThread):
    host_done = pyqtSignal(dict)
    log = pyqtSignal(str)
    finished_all = pyqtSignal()

    def __init__(self, targets, ports, use_tor, session_dir, max_workers=30):
        super().__init__()
        self.targets = targets
        self.ports = ports
        self.use_tor = use_tor
        self.session_dir = session_dir
        self.max_workers = max_workers

    def run(self):
        set_tor_enabled(self.use_tor)
        self.log.emit(
            f"Starting scan of {len(self.targets)} host(s), "
            f"{len(self.ports)} port(s) each. Tor: {'ON' if self.use_tor else 'off'}"
        )
        # Tor circuits don't handle high concurrency well; cap workers low.
        workers = 5 if self.use_tor else self.max_workers
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
            futures = {
                ex.submit(scan_host, ip, self.ports, self.session_dir): ip
                for ip in self.targets
            }
            for future in concurrent.futures.as_completed(futures):
                ip = futures[future]
                try:
                    data = future.result()
                except Exception as e:
                    self.log.emit(f"Error scanning {ip}: {e}")
                    continue
                self.host_done.emit(data)
        self.finished_all.emit()


class DetailedScanWorker(QThread):
    """Runs every registered detailed-scan module against one IP."""
    module_done = pyqtSignal(str, dict)
    finished_all = pyqtSignal()

    def __init__(self, ip, use_tor=False):
        super().__init__()
        self.ip = ip
        self.use_tor = use_tor

    def run(self):
        set_tor_enabled(self.use_tor)
        for name, fn in DETAILED_SCAN_MODULES:
            try:
                result = fn(self.ip)
                if not isinstance(result, dict):
                    result = {"result": result}
            except Exception as e:
                result = {"error": str(e)}
            self.module_done.emit(name, result)
        self.finished_all.emit()
    

class GraphTabWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # 1. Main horizontal layout to hold the Graph View + Right Details Panel
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 2. Instantiate Side Details Panel
        self.details_panel = SideDetailsPanel(self)

        # 3. Instantiate Scene with callback to update details panel on selection
        self.scene = InteractiveGraphScene(node_selected_callback=self.details_panel.display_node)
        self.view = GraphView(self.scene)

        # 4. Toolbar Setup
        toolbar = QToolBar("Graph Toolbar")
        toolbar.setStyleSheet("""
            QToolBar { background-color: #161b22; border-bottom: 1px solid #30363d; padding: 4px; }
            QToolButton { color: #c9d1d9; font-weight: bold; padding: 4px 10px; margin-right: 4px; border: 1px solid #30363d; border-radius: 4px; }
            QToolButton:hover { background-color: #21262d; border-color: #58a6ff; }
        """)

        import_btn = QAction("📂 Import JSON", self)
        import_btn.triggered.connect(self.import_json_dialog)
        toolbar.addAction(import_btn)

        export_btn = QAction("💾 Export JSON", self)
        export_btn.triggered.connect(self.export_json_dialog)
        toolbar.addAction(export_btn)

        toolbar.addSeparator()

        add_root_btn = QAction("➕ New Root Node", self)
        add_root_btn.triggered.connect(self.add_root_node)
        toolbar.addAction(add_root_btn)

        layout_btn = QAction("⚡ Auto Layout", self)
        layout_btn.triggered.connect(lambda checked=False: self.scene.auto_layout())
        toolbar.addAction(layout_btn)

        main_layout.addWidget(toolbar)

        # 5. Splitter/Container layout to place View and Details Panel side-by-side
        content_widget = QWidget()
        content_layout = QHBoxLayout(content_widget)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        
        content_layout.addWidget(self.view, stretch=4)
        content_layout.addWidget(self.details_panel, stretch=1)

        main_layout.addWidget(content_widget)

    def import_json_dialog(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Import JSON", "", "JSON Files (*.json)")
        if file_path:
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)

                if isinstance(data, dict) and "nodes" in data and "edges" in data:
                    graph_data = data
                else:
                    filename = file_path.split("/")[-1].split("\\")[-1]
                    graph_data = raw_json_to_graph(data, root_label=filename)

                self.scene.load_from_json(graph_data)
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to load JSON file:\n{str(e)}")

    def export_json_dialog(self):
        file_path, _ = QFileDialog.getSaveFileName(self, "Export Graph JSON", "graph_output.json", "JSON Files (*.json)")
        if file_path:
            try:
                data = self.scene.export_to_json()
                with open(file_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=4)
                QMessageBox.information(self, "Export Successful", f"Graph exported to:\n{file_path}")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to save JSON file:\n{str(e)}")

    def add_root_node(self):
        dlg = AddEntityDialog(self)
        if dlg.exec_() == QDialog.Accepted:
            data = dlg.get_data()
            node_id = new_node_id()
            
            node = EntityNode(
                entity_id=node_id,
                label=data["label"],
                entity_type=data["type"],
                url=data["url"],
                color=data["color"],
                comments=data["comments"],
                badge=data["badge"],
                size=data["size"]
            )
            
            center_pos = self.view.mapToScene(self.view.viewport().rect().center())
            node.setPos(center_pos)
            
            self.scene.addItem(node)
            self.scene.nodes[node_id] = node

# ---------------------------------------------------------------------------
# GUI
# ---------------------------------------------------------------------------

class ScannerWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PLARONNET // mini recon console")
        self.resize(1050, 680)
        self.results = []
        # Temp dir for saved page snapshots. Wiped after each scan and on close.
        self.session_dir = tempfile.mkdtemp(prefix="scanner_pages_")
        # Persistent SQLite DB — survives across sessions.
        self.db_conn = init_db()
        self._build_ui()

    def _build_ui(self):
        outer = QVBoxLayout(self)

        header_row = QHBoxLayout()
        self.menu_btn = QToolButton()
        self.menu_btn.setText("☰")
        self.menu_btn.setToolTip("Show/hide tab menu")
        self.menu_btn.setFixedWidth(40)
        self.menu_btn.clicked.connect(self.toggle_tabs_visible)
        header_row.addWidget(self.menu_btn)

        title = QLabel("◢◤ PLARONNET — MINI RECON CONSOLE ◢◤")
        title.setObjectName("titleLabel")
        title.setAlignment(Qt.AlignCenter)
        header_row.addWidget(title, stretch=1)
        outer.addLayout(header_row)

        self.tabs = QTabWidget()
        self.tabs.tabBar().setVisible(False)
        outer.addWidget(self.tabs)
        tabs = self.tabs

        scan_tab = QWidget()
        tabs.addTab(scan_tab, "SCAN")
        layout = QVBoxLayout(scan_tab)

        # Targets row
        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Targets:"))
        self.targets_input = QLineEdit()
        self.targets_input.setPlaceholderText(
            "192.168.1.1, 192.168.1.10-20, example.com"
        )
        row1.addWidget(self.targets_input)
        self.load_file_btn = QPushButton("LOAD FROM FILE...")
        self.load_file_btn.clicked.connect(self.load_targets_from_file)
        row1.addWidget(self.load_file_btn)
        layout.addLayout(row1)

        # Ports row
        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Ports (blank = common ports):"))
        self.ports_input = QLineEdit()
        self.ports_input.setPlaceholderText("22,80,443  or leave blank")
        row2.addWidget(self.ports_input)
        row2.addWidget(QLabel("Timeout(s):"))
        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(1, 10)
        self.timeout_spin.setValue(2)
        row2.addWidget(self.timeout_spin)
        layout.addLayout(row2)

        # Options row
        row3 = QHBoxLayout()
        self.tor_checkbox = QCheckBox("Route through Tor (torsocks-equivalent, SOCKS5 127.0.0.1:9050)")
        row3.addWidget(self.tor_checkbox)
        self.scan_btn = QPushButton("▶ START SCAN")
        self.scan_btn.clicked.connect(self.start_scan)
        row3.addWidget(self.scan_btn)
        self.save_btn = QPushButton("SAVE JSON")
        self.save_btn.clicked.connect(self.save_results)
        row3.addWidget(self.save_btn)
        self.cleanup_btn = QPushButton("WIPE CACHE")
        self.cleanup_btn.clicked.connect(self.cleanup_temp_pages)
        row3.addWidget(self.cleanup_btn)
        layout.addLayout(row3)

        # Results table
        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(
            ["IP", "Port", "Service", "Version/Fingerprint", "Banner",
             "Page Title (dbl-click)", "TLS Cert", "HTTP Server"]
        )
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.Stretch)
        self.table.cellDoubleClicked.connect(self.on_cell_double_clicked)
        layout.addWidget(self.table)

        # Log box
        layout.addWidget(QLabel("LOG:"))
        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setMaximumHeight(110)
        layout.addWidget(self.log_box)

        # --- Detailed Scan tab ---
        detail_tab = QWidget()
        tabs.addTab(detail_tab, "DETAILED SCAN")
        d_layout = QVBoxLayout(detail_tab)

        row4 = QHBoxLayout()
        self.detail_tor_checkbox = QCheckBox("Route through Tor (torsocks-equivalent, SOCKS5 127.0.0.1:9050)")
        row4.addWidget(self.detail_tor_checkbox)
        d_layout.addLayout(row4)

        d_row = QHBoxLayout()
        d_row.addWidget(QLabel("Target IP:"))
        self.detail_ip_input = QLineEdit()
        self.detail_ip_input.setPlaceholderText("8.8.8.8")
        d_row.addWidget(self.detail_ip_input)
        self.detail_scan_btn = QPushButton("▶ RUN ANALYSIS")
        self.detail_scan_btn.clicked.connect(self.start_detailed_scan)
        d_row.addWidget(self.detail_scan_btn)
        self.save_detail_btn = QPushButton("💾 SAVE JSON")
        self.save_detail_btn.setEnabled(False)
        self.save_detail_btn.clicked.connect(self.save_detail_results)
        d_row.addWidget(self.save_detail_btn)
        d_layout.addLayout(d_row)

        self.detail_view = QTextBrowser()
        self.detail_view.setOpenExternalLinks(True)
        d_layout.addWidget(self.detail_view)

        self.last_detail_ip = None
        self.last_detail_results = {}

        # --- Search DB tab ---
        search_tab = QWidget()
        tabs.addTab(search_tab, "SEARCH DB")
        s_layout = QVBoxLayout(search_tab)
        s_layout.setContentsMargins(12, 12, 12, 12)
        s_layout.setSpacing(8)

        # Top Bar: Query Input + Search Button
        s_row = QHBoxLayout()
        s_row.setSpacing(10)

        query_label = QLabel("Query:")
        query_label.setStyleSheet("font-weight: bold; color: #00f0ff;")
        s_row.addWidget(query_label)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("ip, banner text, service, version, header... (SQL LIKE match)")
        self.search_input.returnPressed.connect(self.run_search)
        s_row.addWidget(self.search_input)

        self.search_btn = QPushButton("SEARCH")
        self.search_btn.setCursor(Qt.PointingHandCursor)
        self.search_btn.clicked.connect(self.run_search)
        s_row.addWidget(self.search_btn)

        s_layout.addLayout(s_row)

        # Stats Bar
        self.stats_label = QLabel("")
        self.stats_label.setStyleSheet("color: #a9b7c6; font-size: 9pt; padding: 2px 0px;")
        s_layout.addWidget(self.stats_label)

        # Main Splitter: Occupies full remaining space beneath the search bar
        main_splitter = QSplitter(Qt.Horizontal)
        main_splitter.setChildrenCollapsible(False)

        self.search_list = QListWidget()
        self.search_list.currentRowChanged.connect(self.show_host_page)
        main_splitter.addWidget(self.search_list)

        self.host_view = QTextBrowser()
        self.host_view.setOpenExternalLinks(True)
        main_splitter.addWidget(self.host_view)

        # Balance space: 1 part list width, 2 parts view width
        main_splitter.setStretchFactor(0, 1)
        main_splitter.setStretchFactor(1, 2)

        s_layout.addWidget(main_splitter, 1)

        self._search_grouped = {}

        # --- Graph tab ---
        graph_tab = QWidget()
        tabs.addTab(graph_tab, "GRAPH")
        g_layout = QVBoxLayout(graph_tab)
        g_layout.setContentsMargins(0, 0, 0, 0)

        self.graph_widget = GraphTabWidget()
        g_layout.addWidget(self.graph_widget)

        self._refresh_stats()

    def toggle_tabs_visible(self):
        bar = self.tabs.tabBar()
        bar.setVisible(not bar.isVisible())

    def load_targets_from_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Load targets", "", "Text files (*.txt);;All files (*)")
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                raw = f.read()
        except OSError as e:
            QMessageBox.warning(self, "Could not read file", str(e))
            return

        lines = []
        for line in raw.splitlines():
            line = line.split("#", 1)[0].strip()
            if line:
                lines.append(line)

        if not lines:
            QMessageBox.information(self, "Empty file", "No targets found in that file.")
            return

        existing = self.targets_input.text().strip()
        combined = ", ".join(lines)
        self.targets_input.setText(f"{existing}, {combined}" if existing else combined)
        self.append_log(f"Loaded {len(lines)} target(s) from {os.path.basename(path)}")

    def start_scan(self):
        raw_targets = self.targets_input.text().strip()
        if not raw_targets:
            QMessageBox.warning(self, "Missing targets", "Enter at least one target host/IP.")
            return

        targets = expand_targets(raw_targets)

        raw_ports = self.ports_input.text().strip()
        if raw_ports:
            try:
                ports = [int(p.strip()) for p in raw_ports.split(",") if p.strip()]
            except ValueError:
                QMessageBox.warning(self, "Bad ports", "Ports must be comma-separated numbers.")
                return
        else:
            ports = list(COMMON_PORTS.keys())

        self.table.setRowCount(0)
        self.results = []
        self.scan_btn.setEnabled(False)
        self.scan_btn.setText("Scanning...")

        # Fresh temp dir for this scan's page snapshots
        os.makedirs(self.session_dir, exist_ok=True)

        self.worker = ScanWorker(targets, ports, self.tor_checkbox.isChecked(), self.session_dir)
        self.worker.host_done.connect(self.add_result)
        self.worker.log.connect(self.append_log)
        self.worker.finished_all.connect(self.scan_finished)
        self.worker.start()

    def add_result(self, data):
        ip = data["ip"]
        open_ports = data["open_ports"]
        if not open_ports:
            self.append_log(f"{ip}: no open ports found")
            return
        self.results.append(data)
        for port, info in open_ports.items():
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(ip))
            self.table.setItem(row, 1, QTableWidgetItem(str(port)))
            self.table.setItem(row, 2, QTableWidgetItem(info["service_guess"]))
            self.table.setItem(row, 3, QTableWidgetItem(info.get("version") or ""))
            self.table.setItem(row, 4, QTableWidgetItem(info["banner"][:200]))

            html_path = info.get("html_path")
            title = info.get("page_title")
            if html_path:
                title_item = QTableWidgetItem(title or "(no <title>) — double-click to view")
                title_item.setData(Qt.UserRole, html_path)
            elif port in WEB_PORTS:
                title_item = QTableWidgetItem("(page fetch failed)")
            else:
                title_item = QTableWidgetItem("")
            self.table.setItem(row, 5, title_item)

            tls = info.get("tls")
            if tls:
                tls_text = f"{tls.get('subject','?')} (exp {tls.get('not_after','?')})"
            else:
                tls_text = "" if port != 443 else "(cert fetch failed)"
            self.table.setItem(row, 6, QTableWidgetItem(tls_text))

            self.table.setItem(row, 7, QTableWidgetItem(info.get("http_server") or ""))

            # Persist every result to the searchable DB
            save_entry_to_db(self.db_conn, ip, port, info)

        self.append_log(f"{ip}: {len(open_ports)} open port(s)")
        self._refresh_stats()

    def on_cell_double_clicked(self, row, column):
        if column != 5:
            return
        item = self.table.item(row, 5)
        if not item:
            return
        html_path = item.data(Qt.UserRole)
        if not html_path or not os.path.exists(html_path):
            QMessageBox.information(
                self, "Not available",
                "No cached page for this entry (not a web port, fetch failed, "
                "or the cache has already been deleted)."
            )
            return
        webbrowser.open(f"file://{html_path}")

    def run_search(self):
        query = self.search_input.text().strip()
        self.search_list.clear()
        self.host_view.clear()
        self._search_grouped = {}
        if not query:
            return
        rows = search_db(self.db_conn, query)
        grouped = {}
        for r in rows:
            grouped.setdefault(r[0], []).append(r)
        self._search_grouped = grouped
        for ip, recs in grouped.items():
            last_seen = max(r[8] for r in recs)
            self.search_list.addItem(f"{ip}  —  {len(recs)} record(s), last seen {last_seen[:16]}")
        self.stats_label.setText(f"{len(grouped)} host(s), {len(rows)} record(s) matched")
        if grouped:
            self.search_list.setCurrentRow(0)

    def show_host_page(self, row_idx):
        if row_idx < 0 or not self._search_grouped:
            return
        ip = list(self._search_grouped.keys())[row_idx]
        recs = self._search_grouped[ip]
        self.host_view.setHtml(render_host_page_html(ip, recs))

    def start_detailed_scan(self):
        ip = self.detail_ip_input.text().strip()
        if not ip:
            QMessageBox.warning(self, "Missing IP", "Enter a single IP address to analyze.")
            return
        self.last_detail_ip = ip
        self.last_detail_results = {}
        self.save_detail_btn.setEnabled(False)
        self.detail_scan_btn.setEnabled(False)
        self.detail_scan_btn.setText("Analyzing...")
        self._detail_html = f"<h1 style='color:#ff00c8;'>{ip}</h1>"
        self.detail_view.setHtml(self._detail_html)

        self.detail_worker = DetailedScanWorker(ip)
        self.detail_worker.module_done.connect(self.on_detail_module_done)
        self.detail_worker.finished_all.connect(self.on_detail_finished)
        self.detail_worker.start()

    def on_detail_module_done(self, name, result):
        self.last_detail_results[name] = result
        body = json.dumps(result, indent=2, default=str)
        body_escaped = body.replace("<", "&lt;").replace(">", "&gt;")
        self._detail_html += f"""
        <div style="border:1px solid #ff00c8; margin:8px 0; padding:8px; background:#0f0722;">
            <div style="color:#00fff9; font-weight:bold; font-size:12pt;">{name}</div>
            <pre style="color:#39ff14; white-space:pre-wrap;">{body_escaped}</pre>
        </div>"""
        self.detail_view.setHtml(self._detail_html)

    def on_detail_finished(self):
        self.detail_scan_btn.setEnabled(True)
        self.detail_scan_btn.setText("▶ RUN ANALYSIS")
        self.save_detail_btn.setEnabled(True)
        # Persist the active-scan module's ports into the DB too, so a
        # detailed scan also shows up later in Search DB.
        port_data = self.last_detail_results.get("Active Port Scan (this tool)")
        if isinstance(port_data, dict):
            for port, info in port_data.items():
                if isinstance(info, dict):
                    save_entry_to_db(self.db_conn, self.last_detail_ip, port, info)
            self._refresh_stats()

    def save_detail_results(self):
        if not self.last_detail_ip or not self.last_detail_results:
            QMessageBox.information(self, "Nothing to save", "Run a detailed scan first.")
            return
        default_name = f"detailed_scan_{self.last_detail_ip.replace(':', '_')}.json"
        path, _ = QFileDialog.getSaveFileName(self, "Save detailed scan", default_name, "JSON (*.json)")
        if path:
            payload = {
                "ip": self.last_detail_ip,
                "timestamp": datetime.utcnow().isoformat(),
                "modules": self.last_detail_results,
            }
            with open(path, "w") as f:
                json.dump(payload, f, indent=2, default=str)
            self.append_log(f"Saved detailed scan results to {path}")

    def _refresh_stats(self):
        total, hosts = db_stats(self.db_conn)
        self.stats_label.setText(f"Database: {total} record(s) across {hosts} host(s)")

    def append_log(self, msg):
        self.log_box.append(msg)

    def scan_finished(self):
        self.scan_btn.setEnabled(True)
        self.scan_btn.setText("Start Scan")
        self.append_log("Scan complete.")
        self.cleanup_temp_pages(auto=True)

    def cleanup_temp_pages(self, auto=False):
        """Delete all saved HTML snapshots for this session. Table rows and
        JSON export are unaffected — only the on-disk page cache is removed.
        Note: only saved page snapshots are deleted; scan_results.json you
        explicitly export via 'Save Results' is kept."""
        removed = 0
        if os.path.isdir(self.session_dir):
            for fname in os.listdir(self.session_dir):
                fpath = os.path.join(self.session_dir, fname)
                try:
                    os.remove(fpath)
                    removed += 1
                except OSError:
                    pass
        # Clear stored paths in the table so double-click gives a clean message
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 5)
            if item:
                item.setData(Qt.UserRole, None)
        if removed or not auto:
            self.append_log(f"Deleted {removed} cached page file(s) from {self.session_dir}")

    def closeEvent(self, event):
        shutil.rmtree(self.session_dir, ignore_errors=True)
        try:
            self.db_conn.close()
        except Exception:
            pass
        event.accept()

    def save_results(self):
        if not self.results:
            QMessageBox.information(self, "Nothing to save", "Run a scan first.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Save results", "scan_results.json", "JSON (*.json)")
        if path:
            with open(path, "w") as f:
                json.dump(self.results, f, indent=2)
            self.append_log(f"Saved results to {path}")


def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(CYBERPUNK_QSS)
    win = ScannerWindow()
    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
