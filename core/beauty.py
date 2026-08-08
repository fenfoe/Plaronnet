import html


def render_host_page_html(ip, recs):
    """Render a clean, high-contrast dark dashboard with distinct card sections."""
    ports_sorted = sorted(recs, key=lambda r: r[1])
    distinct_ports = sorted(set(r[1] for r in recs))
    
    cards = ""
    for r in ports_sorted:
        _, port, service, banner, version, http_server, tls_issuer, tls_exp, ts = r
        
        banner_clean = html.escape(banner or "—")
        if len(banner_clean) > 400:
            banner_clean = banner_clean[:400] + "\n..."
        
        extra = ""
        if http_server:
            extra += f'''
            <div style="margin-top: 6px; color: #a5d6ff;">
                <span style="color: #8b949e; font-weight: bold;">HTTP Server:</span> {html.escape(http_server)}
            </div>'''
        if tls_issuer:
            extra += f'''
            <div style="margin-top: 6px; color: #d2a8ff;">
                <span style="color: #8b949e; font-weight: bold;">TLS Issuer:</span> {html.escape(tls_issuer)} 
                <span style="color: #8b949e;">(expires {html.escape(tls_exp or '?')})</span>
            </div>'''

        cards += f"""
        <div style="
            background: #161b22;
            border: 1px solid #30363d;
            border-radius: 6px;
            margin-bottom: 20px;
            overflow: hidden;
        ">
            <!-- Distinct Section Header Bar -->
            <div style="
                background: #21262d;
                padding: 10px 14px;
                border-bottom: 1px solid #30363d;
                display: flex;
                align-items: center;
            ">
                <span style="
                    background: #238636;
                    color: #ffffff;
                    font-size: 8.5pt;
                    font-weight: bold;
                    padding: 2px 8px;
                    border-radius: 12px;
                    margin-right: 8px;
                ">PORT {port}</span>
                <span style="color: #58a6ff; font-weight: bold; font-size: 11pt;">
                    {html.escape(service or 'unknown').upper()}
                </span>
            </div>

            <!-- Card Body Content -->
            <div style="padding: 14px;">
                <div style="font-size: 9.5pt; color: #c9d1d9; margin-bottom: 4px;">
                    <span style="color: #8b949e;">Version:</span> 
                    <span style="color: #7ee787; font-weight: bold;">{html.escape(version or '—')}</span>
                </div>

                {extra}

                <div style="color: #484f58; font-size: 8.5pt; margin-top: 6px; margin-bottom: 10px;">
                    Scanned: {ts}
                </div>

                <!-- Terminal-style Raw Banner Box -->
                <div style="
                    background: #0d1117;
                    border: 1px solid #21262d;
                    border-radius: 4px;
                    padding: 10px;
                ">
                    <div style="color: #8b949e; font-size: 8pt; margin-bottom: 4px; text-transform: uppercase;">Raw Banner Response</div>
                    <pre style="
                        color: #7d8590;
                        margin: 0;
                        white-space: pre-wrap;
                        word-break: break-all;
                        font-family: 'Consolas', 'Courier New', monospace;
                        font-size: 9pt;
                    ">{banner_clean}</pre>
                </div>
            </div>
        </div>"""

    ports_str = ', '.join(str(p) for p in distinct_ports)
    
    return f"""
    <html>
    <body style="
        background: #0d1117;
        color: #c9d1d9;
        font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, sans-serif;
        margin: 0;
        padding: 16px;
    ">
        <!-- Host Header Banner -->
        <div style="
            border-bottom: 1px solid #21262d;
            padding-bottom: 12px;
            margin-bottom: 18px;
        ">
            <h1 style="color: #f0f6fc; margin: 0 0 6px 0; font-size: 18pt; font-family: monospace;">{html.escape(ip)}</h1>
            <div style="color: #8b949e; font-size: 9.5pt;">
                <strong style="color: #58a6ff;">{len(recs)}</strong> record(s) on file &nbsp;&bull;&nbsp; 
                <strong style="color: #58a6ff;">{len(distinct_ports)}</strong> distinct port(s): <code style="color: #7ee787;">{ports_str}</code>
            </div>
        </div>

        {cards}
    </body>
    </html>
    """


CYBERPUNK_QSS = """
QWidget {
    background-color: #0d1117;
    color: #c9d1d9;
    font-family: 'Consolas', 'Courier New', monospace;
    font-size: 10pt;
}

/* --- Labels --- */
QLabel { 
    color: #a9b7c6; 
}

QLabel#titleLabel {
    color: #00f0ff;
    font-size: 16pt;
    font-weight: bold;
    letter-spacing: 2px;
}

/* --- Input Controls --- */
QLineEdit, QSpinBox, QTextEdit {
    background-color: #161b22;
    color: #f0f6fc;
    border: 1px solid #30363d;
    border-radius: 6px;
    padding: 6px;
    selection-background-color: #1f6feb;
    selection-color: #ffffff;
}

QLineEdit:focus, QSpinBox:focus, QTextEdit:focus {
    border: 1px solid #58a6ff;
}

/* --- Buttons --- */
QPushButton {
    background-color: #21262d;
    color: #c9d1d9;
    border: 1px solid #30363d;
    padding: 6px 16px;
    border-radius: 6px;
    font-weight: bold;
}

QPushButton:hover {
    background-color: #30363d;
    color: #f0f6fc;
    border-color: #8b949e;
}

QPushButton:pressed {
    background-color: #161b22;
}

QPushButton:disabled {
    color: #524765;
    border-color: #271c3f;
    background-color: #140d25;
}

/* --- Checkboxes --- */
QCheckBox {
    color: #e2f1f8;
    spacing: 8px;
}

QCheckBox::indicator {
    width: 14px;
    height: 14px;
    border: 1px solid #00f0ff;
    border-radius: 2px;
    background: #160e29;
}

QCheckBox::indicator:checked {
    background-color: #ff2a85;
    border-color: #ff2a85;
}

/* --- Tables --- */
QTableWidget {
    background-color: #120b22;
    color: #00ff9f;
    gridline-color: #261942;
    border: 1px solid #3d2b5e;
    selection-background-color: #ff2a85;
    selection-color: #ffffff;
    alternate-background-color: #160e29;
}

QHeaderView::section {
    background-color: #1f143a;
    color: #00f0ff;
    border: none;
    border-bottom: 2px solid #ff2a85;
    border-right: 1px solid #261942;
    padding: 6px;
    font-weight: bold;
}

/* --- Tabs --- */
QTabWidget::pane {
    border: 1px solid #3d2b5e;
    top: -1px;
    background-color: #0e091b;
}

QTabBar::tab {
    background: #160e29;
    color: #a9b7c6;
    padding: 8px 20px;
    border: 1px solid #261942;
    border-bottom: none;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
    margin-right: 2px;
}

QTabBar::tab:selected {
    background: #ff2a85;
    color: #ffffff;
    font-weight: bold;
    border-color: #ff2a85;
}

QTabBar::tab:hover:!selected {
    color: #00f0ff;
    background: #1f143a;
}

/* --- Scrollbars --- */
QScrollBar:vertical {
    background: #0e091b;
    width: 10px;
    margin: 0px;
}

QScrollBar::handle:vertical {
    background: #3d2b5e;
    border-radius: 5px;
    min-height: 20px;
}

QScrollBar::handle:vertical:hover {
    background: #ff2a85;
}

QScrollBar:horizontal {
    background: #0e091b;
    height: 10px;
    margin: 0px;
}

QScrollBar::handle:horizontal {
    background: #3d2b5e;
    border-radius: 5px;
    min-width: 20px;
}

QScrollBar::handle:horizontal:hover {
    background: #ff2a85;
}

QScrollBar::add-line, QScrollBar::sub-line {
    border: none;
    background: none;
}

/* --- Dialogs --- */
QMessageBox {
    background-color: #0e091b;
}

/* --- Host Selection List --- */
QListWidget {
    background-color: #0d1117;
    border: 1px solid #30363d;
    border-radius: 6px;
    padding: 4px;
}

QListWidget::item {
    padding: 8px 10px;
    border-radius: 4px;
    margin-bottom: 2px;
}

QListWidget::item:hover {
    background-color: #1f143a;
    color: #00f0ff;
    border: 1px solid #3d2b5e;
}

QListWidget::item:selected {
    background-color: #ff2a85;
    color: #ffffff;
    font-weight: bold;
}

/* --- Host Detail View (QTextBrowser) --- */
QTextBrowser {
    background-color: #120b22;
    border: 1px solid #3d2b5e;
    border-radius: 4px;
    padding: 12px;
    color: #e2f1f8;
    selection-background-color: #ff2a85;
    selection-color: #ffffff;
}

/* --- Splitter Handle Styling --- */
QSplitter::handle {
    background-color: #1e1436;
    margin: 0px 4px;
}

QSplitter::handle:hover {
    background-color: #ff2a85;
}
"""
