import re
import sys
import json
import uuid
import math
from PyQt5.QtCore import Qt, QRectF, QLineF
from PyQt5.QtGui import QPen, QColor, QFont, QPainter, QBrush, QFontMetrics
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QGraphicsView, QGraphicsScene,
    QGraphicsItem, QGraphicsLineItem, QMenu, QToolBar, QAction, 
    QFileDialog, QMessageBox, QDialog, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QTextEdit, QComboBox, QPushButton, QButtonGroup,
    QRadioButton, QWidget, QDockWidget, QFrame
)


def new_node_id():
    """Generate a globally-unique node id. Using uuid4 means ids never
    collide even after nodes have been deleted/re-added across sessions,
    unlike a counter derived from the current node count."""
    return f"node_{uuid.uuid4().hex}"


def raw_json_to_graph(raw_data, root_label="ROOT"):
    """Recursively converts raw JSON into graph format using Regex pattern matching for accuracy."""
    nodes = []
    edges = []

    # Regular Expressions for Entity Type Matching
    IP_REGEX = re.compile(r"^(?:[0-9]{1,3}\.){3}[0-9]{1,3}$")
    EMAIL_REGEX = re.compile(r"^[\w\.-]+@[\w\.-]+\.\w+$")
    URL_REGEX = re.compile(r"^https?://[^\s/$.?#].[^\s]*$", re.IGNORECASE)
    DOMAIN_REGEX = re.compile(r"^(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}$")
    PHONE_REGEX = re.compile(r"^\+?[0-9\s\-()]{7,15}$")

    def get_node_type(val, key=""):
        str_val = str(val).strip()
        key_lower = str(key).lower()

        if IP_REGEX.match(str_val):
            return "IP"
        if EMAIL_REGEX.match(str_val):
            return "email address"
        if URL_REGEX.match(str_val):
            return "URL"
        if DOMAIN_REGEX.match(str_val):
            return "domain name"
        if PHONE_REGEX.match(str_val):
            return "phone number"

        # Fallback key-based detection
        if any(k in key_lower for k in ["user", "person", "name", "author"]):
            return "person"
        if any(k in key_lower for k in ["location", "address", "city", "country"]):
            return "location"
        if any(k in key_lower for k in ["org", "company", "vendor"]):
            return "company"
        if any(k in key_lower for k in ["site", "web"]):
            return "website"
        if any(k in key_lower for k in ["event", "time", "date"]):
            return "event"

        return "domain name" if isinstance(val, dict) else "website" if isinstance(val, list) else "IP"

    def traverse(data, key_label, parent_id=None, depth=0, y_offset=[0]):
        node_id = new_node_id()
        
        node_type = get_node_type(data, key=key_label)
        display_label = str(key_label) if isinstance(data, (dict, list)) else f"{key_label}: {data}"

        x_pos = depth * 220
        y_pos = y_offset[0] * 60

        nodes.append({
            "id": node_id,
            "label": display_label,
            "type": node_type,
            "x": x_pos,
            "y": y_pos
        })

        if parent_id:
            edges.append({"source": parent_id, "target": node_id})

        if isinstance(data, dict):
            for k, v in data.items():
                traverse(v, k, parent_id=node_id, depth=depth + 1, y_offset=y_offset)
        elif isinstance(data, list):
            for idx, item in enumerate(data):
                item_label = f"[{idx}]" if isinstance(item, (dict, list)) else f"{key_label}[{idx}]"
                traverse(item, item_label, parent_id=node_id, depth=depth + 1, y_offset=y_offset)
        else:
            y_offset[0] += 1

    traverse(raw_data, root_label, parent_id=None, depth=0, y_offset=[0])
    return {"nodes": nodes, "edges": edges}


class AddEntityDialog(QDialog):
    TYPES = [
        "company", "domain name", "email address", "event",
        "IP", "location", "person", "phone number", "URL", "website"
    ]
    COLORS = ["#d9d9d9", "#d4ac0d", "#cb4335", "#212f3d", "#1f6feb", "#8957e5", "#238636", "#7e5109", "#d35400"]
    BADGES = ["none", "check", "alert", "cross", "question", "minus", "wait"]

    def __init__(self, parent=None, default_label="", default_type="IP", default_url=""):
        super().__init__(parent)
        self.setWindowTitle("ADD AN ENTITY")
        self.setMinimumWidth(700)
        self.setStyleSheet("""
            QDialog { background-color: #161b22; font-family: 'Segoe UI', sans-serif; }
            QLabel { font-weight: bold; color: #c9d1d9; font-size: 11px; }
            QLineEdit, QTextEdit, QComboBox { background: #0d1117; color: #c9d1d9; border: 1px solid #30363d; border-radius: 4px; padding: 6px; }
            
            /* Type buttons default state */
            QPushButton.type-chip { 
                background: #21262d; 
                border: 1px solid #30363d; 
                border-radius: 4px; 
                padding: 6px 10px; 
                font-weight: bold; 
                color: #c9d1d9; 
            }
            QPushButton.type-chip:hover { 
                background-color: #30363d; 
                border-color: #8b949e; 
            }
            /* High-contrast active/selected state */
            QPushButton.type-chip:checked { 
                background-color: #1f6feb !important; 
                color: #ffffff !important; 
                border: 1px solid #58a6ff !important; 
            }
            
            QPushButton { background: #21262d; color: #c9d1d9; border: 1px solid #30363d; border-radius: 4px; padding: 6px; }
        """)

        main_layout = QHBoxLayout(self)
        left_layout = QVBoxLayout()
        right_layout = QVBoxLayout()

        left_layout.addWidget(QLabel("BASICS"))
        self.value_input = QLineEdit(default_label)
        self.value_input.setPlaceholderText("value *")
        left_layout.addWidget(self.value_input)

        self.url_input = QLineEdit(default_url)
        self.url_input.setPlaceholderText("url")
        left_layout.addWidget(self.url_input)

        left_layout.addWidget(QLabel("TYPE AND COUNTRY 💡"))
        
        # Setup mutually exclusive button group for Entity Types
        self.type_group = QButtonGroup(self)
        self.type_group.setExclusive(True)

        chip_layout1 = QHBoxLayout()
        chip_layout2 = QHBoxLayout()

        for idx, t in enumerate(self.TYPES):
            btn = QPushButton(t)
            btn.setCheckable(True)
            btn.setProperty("class", "type-chip")
            
            if t.lower() == default_type.lower():
                btn.setChecked(True)
                
            self.type_group.addButton(btn)

            if idx < 5:
                chip_layout1.addWidget(btn)
            else:
                chip_layout2.addWidget(btn)

        # Fallback check if default_type didn't match
        if not self.type_group.checkedButton() and self.type_group.buttons():
            self.type_group.buttons()[0].setChecked(True)

        left_layout.addLayout(chip_layout1)
        left_layout.addLayout(chip_layout2)

        self.country_box = QComboBox()
        self.country_box.addItems(["country...", "United States", "Germany", "France", "United Kingdom", "Japan"])
        left_layout.addWidget(self.country_box)

        left_layout.addWidget(QLabel("OPTIONS"))
        color_layout = QHBoxLayout()
        color_layout.addWidget(QLabel("Color"))
        self.color_group = QButtonGroup(self)
        self.selected_color = self.COLORS[6]
        for c in self.COLORS:
            btn = QPushButton()
            btn.setFixedSize(20, 20)
            btn.setStyleSheet(f"background-color: {c}; border: 1px solid #30363d; border-radius: 2px;")
            btn.setCheckable(True)
            btn.clicked.connect(lambda checked, col=c: setattr(self, 'selected_color', col))
            self.color_group.addButton(btn)
            color_layout.addWidget(btn)
        left_layout.addLayout(color_layout)

        badge_layout = QHBoxLayout()
        badge_layout.addWidget(QLabel("Badge"))
        self.badge_box = QComboBox()
        self.badge_box.addItems(self.BADGES)
        badge_layout.addWidget(self.badge_box)
        left_layout.addLayout(badge_layout)

        size_layout = QHBoxLayout()
        size_layout.addWidget(QLabel("Size"))
        self.size_group = QButtonGroup(self)
        for sz in ["S", "M", "L"]:
            rbtn = QRadioButton(sz)
            rbtn.setStyleSheet("color: #c9d1d9;")
            if sz == "M":
                rbtn.setChecked(True)
            self.size_group.addButton(rbtn)
            size_layout.addWidget(rbtn)
        left_layout.addLayout(size_layout)

        right_layout.addWidget(QLabel("COMMENTS"))
        self.comments_input = QTextEdit()
        self.comments_input.setPlaceholderText("Enter comments or description...")
        right_layout.addWidget(self.comments_input)

        btn_layout = QHBoxLayout()
        cancel_btn = QPushButton("CANCEL")
        cancel_btn.clicked.connect(self.reject)
        add_btn = QPushButton("ADD")
        add_btn.setStyleSheet("background: #238636; color: white; font-weight: bold; border-radius: 4px; padding: 6px 16px;")
        add_btn.clicked.connect(self.accept)
        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(add_btn)

        right_layout.addLayout(btn_layout)

        main_layout.addLayout(left_layout, stretch=3)
        main_layout.addLayout(right_layout, stretch=2)

    def get_data(self):
        selected_type = "IP"
        if self.type_group.checkedButton():
            selected_type = self.type_group.checkedButton().text()

        selected_size = "M"
        for btn in self.size_group.buttons():
            if btn.isChecked():
                selected_size = btn.text()

        return {
            "label": self.value_input.text() or "New Entity",
            "url": self.url_input.text().strip(),
            "type": selected_type,
            "color": self.selected_color,
            "badge": self.badge_box.currentText(),
            "size": selected_size,
            "country": self.country_box.currentText(),
            "comments": self.comments_input.toPlainText()
        }


class Edge(QGraphicsLineItem):
    def __init__(self, source_node, target_node):
        super().__init__()
        self.source = source_node
        self.target = target_node
        
        self.setFlags(QGraphicsItem.ItemIsSelectable)
        self.setAcceptHoverEvents(True)
        
        self.default_pen = QPen(QColor("#30363d"), 2, Qt.SolidLine)
        self.selected_pen = QPen(QColor("#f85149"), 3, Qt.DashLine)
        self.hover_pen = QPen(QColor("#58a6ff"), 3, Qt.SolidLine) 
        
        self.setPen(self.default_pen)
        self.setZValue(0)
        
        self.source.add_edge(self)
        self.target.add_edge(self)
        self.update_position()

    def update_position(self):
        line = QLineF(self.source.scenePos(), self.target.scenePos())
        self.setLine(line)

    def hoverEnterEvent(self, event):
        if not self.isSelected():
            self.setPen(self.hover_pen)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        if not self.isSelected():
            self.setPen(self.default_pen)
        super().hoverLeaveEvent(event)

    def paint(self, painter, option, widget):
        if self.isSelected():
            self.setPen(self.selected_pen)
        super().paint(painter, option, widget)

    def contextMenuEvent(self, event):
        menu = QMenu()
        menu.setStyleSheet("""
            QMenu { background-color: #161b22; color: #c9d1d9; border: 1px solid #30363d; }
            QMenu::item:selected { background-color: #f85149; color: white; }
        """)
        delete_action = menu.addAction("🗑️ Delete Edge")
        action = menu.exec_(event.screenPos())

        if action == delete_action:
            self.scene().remove_edge(self)


class EntityNode(QGraphicsItem):
    TYPES = [
        "company", "domain name", "email address", "event",
        "IP", "location", "person", "phone number", "URL", "website"
    ]

    ICON_MAP = {
        "IP": "🌐",
        "domain name": "🌐",
        "URL": "🔗",
        "website": "💻",
        "person": "👤",
        "location": "📍",
        "email address": "✉️",
        "phone number": "📞",
        "company": "🏢",
        "event": "📅"
    }

    def __init__(self, entity_id, label, entity_type="IP", color="#238636", comments="", badge="none", size="M", url=""):
        super().__init__()
        self.id = entity_id
        self.label = label
        self.url = url
        self.entity_type = entity_type
        self.accent_color = QColor(color)
        self.comments = comments
        self.badge = badge
        self.node_size = size
        self.edges = []

        self.setFlags(
            QGraphicsItem.ItemIsMovable |
            QGraphicsItem.ItemIsSelectable |
            QGraphicsItem.ItemSendsGeometryChanges
        )
        self.setZValue(1)

        self.radius_map = {"S": 30, "M": 42, "L": 55}
        self.radius = self.radius_map.get(self.node_size, 42)

    def boundingRect(self):
        r = self.radius + 15
        return QRectF(-r, -r, r * 2, r * 2 + 25)

    def paint(self, painter, option, widget):
        painter.setRenderHint(QPainter.Antialiasing)
        r = self.radius

        # Halo Ring on Node Selection
        if self.isSelected():
            halo_pen = QPen(self.accent_color, 12)
            painter.setPen(halo_pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(QRectF(-r - 6, -r - 6, (r + 6) * 2, (r + 6) * 2))

        painter.setPen(QPen(QColor("#30363d"), 2))
        painter.setBrush(QBrush(QColor("#21262d")))
        painter.drawEllipse(QRectF(-r, -r, r * 2, r * 2))

        inner_r = r * 0.55
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(QColor("#161b22")))
        painter.drawEllipse(QRectF(-inner_r, -inner_r, inner_r * 2, inner_r * 2))

        # Dynamic Icon Rendering
        painter.setPen(QPen(QColor("#ffffff")))
        painter.setFont(QFont("Segoe UI Emoji", int(inner_r * 0.55)))
        icon = self.ICON_MAP.get(self.entity_type, "🏷️")
        painter.drawText(QRectF(-inner_r, -inner_r, inner_r * 2, inner_r * 2), Qt.AlignCenter, icon)

        # Bottom Text Banner
        painter.setFont(QFont("Segoe UI", 10, QFont.Bold))
        metrics = QFontMetrics(painter.font())
        tw = metrics.horizontalAdvance(self.label) + 16
        th = 22
        lbl_rect = QRectF(-tw / 2, r + 4, tw, th)

        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(QColor("#161b22")))
        painter.drawRoundedRect(lbl_rect, 4, 4)

        painter.setPen(QPen(QColor("#c9d1d9")))
        painter.drawText(lbl_rect, Qt.AlignCenter, self.label)

    def add_edge(self, edge):
        if edge not in self.edges:
            self.edges.append(edge)

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionHasChanged:
            for edge in self.edges:
                edge.update_position()
            if self.scene() and hasattr(self.scene(), 'node_selected_callback') and self.scene().node_selected_callback:
                self.scene().node_selected_callback(self)
        return super().itemChange(change, value)

    def contextMenuEvent(self, event):
        menu = QMenu()
        menu.setStyleSheet("""
            QMenu { background-color: #161b22; color: #c9d1d9; border: 1px solid #30363d; }
            QMenu::item:selected { background-color: #1f6feb; color: white; }
        """)
        scene = self.scene()
        selected_nodes = [item for item in scene.selectedItems() if isinstance(item, EntityNode)]

        if self not in selected_nodes:
            scene.clearSelection()
            self.setSelected(True)
            selected_nodes = [self]

        if len(selected_nodes) == 2:
            connect_act = menu.addAction("🔗 Connect Selected Nodes")
            if menu.exec_(event.screenPos()) == connect_act:
                scene.connect_nodes(selected_nodes[0], selected_nodes[1])
            return

        edit_act = menu.addAction("✏️ Edit Entity")
        add_child_act = menu.addAction("+ Add Connected Entity")
        delete_act = menu.addAction("🗑️ Delete Entity")

        action = menu.exec_(event.screenPos())
        if action == edit_act:
            dlg = AddEntityDialog(None, default_label=self.label, default_type=self.entity_type, default_url=self.url)
            dlg.comments_input.setText(self.comments)
            if dlg.exec_() == QDialog.Accepted:
                data = dlg.get_data()
                self.label = data["label"]
                self.url = data["url"]
                self.entity_type = data["type"]
                self.accent_color = QColor(data["color"])
                self.comments = data["comments"]
                self.node_size = data["size"]
                self.radius = self.radius_map.get(self.node_size, 42)
                self.update()
                if scene.node_selected_callback:
                    scene.node_selected_callback(self)
        elif action == add_child_act:
            scene.add_manual_child(self)
        elif action == delete_act:
            scene.remove_entities(selected_nodes)


class SideDetailsPanel(QDockWidget):
    """Side panel displaying detailed node metadata on selection."""
    def __init__(self, parent=None):
        super().__init__("Entity Information", parent)
        self.setFixedWidth(320)
        self.current_node = None
        
        container = QWidget()
        container.setStyleSheet("background: #161b22; font-family: 'Segoe UI', sans-serif;")
        layout = QVBoxLayout(container)

        header = QHBoxLayout()
        self.type_icon = QLabel("📍")
        self.type_label = QLabel("IP")
        self.type_label.setStyleSheet("font-weight: bold; color: #58a6ff;")
        self.group_label = QLabel("DETAILS")
        self.group_label.setStyleSheet("color: #8b949e; font-style: italic;")
        header.addWidget(self.type_icon)
        header.addWidget(self.type_label)
        header.addWidget(self.group_label)
        header.addStretch()
        layout.addLayout(header)

        self.title = QLabel("Select an Entity")
        self.title.setStyleSheet("font-size: 18px; font-weight: bold; color: #c9d1d9;")
        layout.addWidget(self.title)

        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("color: #30363d;")
        layout.addWidget(line)

        # Make the notes editable
        self.notes = QTextEdit()
        self.notes.setReadOnly(False) 
        self.notes.setStyleSheet("""
            QTextEdit {
                background: #0d1117; 
                color: #c9d1d9; 
                border: 1px solid #30363d; 
                border-radius: 4px; 
                padding: 6px;
                font-size: 12px;
            }
        """)
        self.notes.setPlaceholderText("Type additional comments or notes here...")
        
        # Connect text changes to auto-save to the node
        self.notes.textChanged.connect(self.save_notes_to_node)
        layout.addWidget(self.notes)

        self.setWidget(container)

    def display_node(self, node):
        if not self.isVisible():
            self.show()

        self.notes.blockSignals(True)
        self.current_node = node

        if not node:
            self.title.setText("Select an Entity")
            self.type_label.setText("-")
            self.notes.clear()
            self.notes.setEnabled(False)
        else:
            self.notes.setEnabled(True)
            icon = EntityNode.ICON_MAP.get(node.entity_type, "🏷️")
            self.type_icon.setText(icon)
            self.type_label.setText(node.entity_type.upper())
            self.title.setText(node.label)

            content = ""
            if node.url:
                content += f"🔗 URL: {node.url}\n\n"
            content += node.comments if node.comments else ""

            self.notes.setPlainText(content)

        self.notes.blockSignals(False)

    def save_notes_to_node(self):
        """Saves current text back to the active EntityNode in real-time."""
        if self.current_node:
            self.current_node.comments = self.notes.toPlainText()

class InteractiveGraphScene(QGraphicsScene):
    def __init__(self, node_selected_callback=None, parent=None):
        super().__init__(parent)
        self.setBackgroundBrush(QBrush(QColor("#0d1117")))
        self.nodes = {}
        self.edges_list = []
        self.node_selected_callback = node_selected_callback
        self.selectionChanged.connect(self.handle_selection_changed)

    def handle_selection_changed(self):
        selected = [item for item in self.selectedItems() if isinstance(item, EntityNode)]
        if selected and self.node_selected_callback:
            self.node_selected_callback(selected[0])
        elif self.node_selected_callback:
            self.node_selected_callback(None)

    def load_from_json(self, json_data):
        self.clear()
        self.nodes.clear()
        self.edges_list.clear()

        for item in json_data.get("nodes", []):
            # Fall back to a fresh uuid if an incoming file has no id, a
            # blank id, or (for old exports) a duplicate id already seen
            # in this file — guarantees no in-scene collisions on import.
            raw_id = str(item.get("id", "")).strip()
            node_id = raw_id if raw_id and raw_id not in self.nodes else new_node_id()

            node = EntityNode(
                node_id,
                item.get("label", "Unnamed"),
                entity_type=item.get("type", "IP"),
                url=item.get("url", ""),
                comments=item.get("comments", ""),
                color=item.get("color", "#238636"),
                badge=item.get("badge", "none"),
                size=item.get("size", "M")
            )
            node.setPos(item.get("x", 0), item.get("y", 0))
            self.addItem(node)
            self.nodes[node_id] = node

        for conn in json_data.get("edges", []):
            src_id = str(conn.get("source") or conn.get("from") or "")
            tgt_id = str(conn.get("target") or conn.get("to") or "")
            src_node = self.nodes.get(src_id)
            tgt_node = self.nodes.get(tgt_id)
            if src_node and tgt_node:
                self.connect_nodes(src_node, tgt_node)

        for edge in self.edges_list:
            edge.update_position()

    def export_to_json(self):
        nodes_data = []
        for node_id, node in self.nodes.items():
            pos = node.scenePos()
            nodes_data.append({
                "id": str(node_id),
                "label": node.label,
                "url": node.url,
                "type": node.entity_type,
                "comments": node.comments,
                "color": node.accent_color.name(),
                "badge": node.badge,
                "size": node.node_size,
                "x": round(pos.x(), 2),
                "y": round(pos.y(), 2)
            })

        edges_data = []
        for edge in self.edges_list:
            edges_data.append({
                "source": str(edge.source.id),
                "target": str(edge.target.id)
            })

        return {"nodes": nodes_data, "edges": edges_data}

    def connect_nodes(self, source_node, target_node):
        if source_node == target_node:
            return None
            
        for edge in self.edges_list:
            if (edge.source == source_node and edge.target == target_node) or \
               (edge.source == target_node and edge.target == source_node):
                return edge

        edge = Edge(source_node, target_node)
        self.addItem(edge)
        self.edges_list.append(edge)
        return edge

    def auto_layout(self, radius_step=180):
        """Radial layout: the root sits at the center and each connection
        hop moves outward one ring, like the spokes of a wheel/snowflake.
        Each node's angular slice is sized proportionally to how many
        descendants it has, so a branch with many children gets more
        angular room than a lone leaf."""
        if not self.nodes:
            return

        targets = {edge.target for edge in self.edges_list}
        roots = [node for node in self.nodes.values() if node not in targets]
        if not roots:
            roots = [next(iter(self.nodes.values()))]

        def get_children(node, seen):
            children = []
            for edge in node.edges:
                child = edge.target if edge.source == node else edge.source
                if child.id not in seen:
                    children.append(child)
            return children

        # Pass 1: weight each node by its descendant-leaf count, so
        # branches get angular space proportional to how much they contain.
        weight_cache = {}
        weighed = set()

        def compute_weight(node):
            if node.id in weighed:
                return 0
            weighed.add(node.id)
            children = get_children(node, weighed)
            if not children:
                weight_cache[node.id] = 1
                return 1
            total = sum(compute_weight(c) for c in children)
            weight_cache[node.id] = max(total, 1)
            return weight_cache[node.id]

        for root in roots:
            compute_weight(root)

        # If there's more than one disconnected root, don't stack them all
        # at the exact center — start them one ring out instead.
        depth_offset = 0 if len(roots) == 1 else 1

        visited = set()

        def place(node, depth, angle_start, angle_end):
            if node.id in visited:
                return
            visited.add(node.id)

            effective_depth = depth + depth_offset
            angle_mid = (angle_start + angle_end) / 2.0
            if effective_depth == 0:
                x, y = 0.0, 0.0
            else:
                r = effective_depth * radius_step
                x = r * math.cos(angle_mid)
                y = r * math.sin(angle_mid)
            node.setPos(x, y)

            children = get_children(node, visited)
            if not children:
                return

            total_weight = sum(weight_cache.get(c.id, 1) for c in children)
            cursor = angle_start
            span_total = angle_end - angle_start
            for c in children:
                w = weight_cache.get(c.id, 1)
                span = span_total * (w / total_weight) if total_weight else span_total / len(children)
                place(c, depth + 1, cursor, cursor + span)
                cursor += span

        total_root_weight = sum(weight_cache.get(r.id, 1) for r in roots) or 1
        two_pi = 2 * math.pi
        cursor = 0.0
        for root in roots:
            w = weight_cache.get(root.id, 1)
            span = two_pi * (w / total_root_weight)
            place(root, 0, cursor, cursor + span)
            cursor += span

    def add_manual_child(self, parent_node):
        dlg = AddEntityDialog(None, default_label="")
        if dlg.exec_() == QDialog.Accepted:
            data = dlg.get_data()
            new_id = new_node_id()
            new_node = EntityNode(
                new_id, 
                data["label"], 
                entity_type=data["type"],
                url=data["url"],
                color=data["color"],
                comments=data["comments"],
                badge=data["badge"],
                size=data["size"]
            )
            pos = parent_node.scenePos()
            new_node.setPos(pos.x() + 180, pos.y() + 120)
            
            self.addItem(new_node)
            self.nodes[new_id] = new_node
            self.connect_nodes(parent_node, new_node)

    def remove_entity(self, node):
        for edge in list(node.edges):
            self.remove_edge(edge)
        
        if node.id in self.nodes:
            del self.nodes[node.id]
        self.removeItem(node)

    def remove_entities(self, nodes_to_remove):
        for node in list(nodes_to_remove):
            self.remove_entity(node)
        if self.node_selected_callback:
            self.node_selected_callback(None)

    def remove_edge(self, edge):
        if edge in self.edges_list:
            self.edges_list.remove(edge)
        if edge in edge.source.edges:
            edge.source.edges.remove(edge)
        if edge in edge.target.edges:
            edge.target.edges.remove(edge)
        self.removeItem(edge)

    def remove_edges(self, edges_to_remove):
        for edge in list(edges_to_remove):
            self.remove_edge(edge)


class GraphView(QGraphicsView):
    def __init__(self, scene):
        super().__init__(scene)
        self.setRenderHint(QPainter.Antialiasing)
        self.setDragMode(QGraphicsView.RubberBandDrag)
        self.setViewportUpdateMode(QGraphicsView.FullViewportUpdate)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setBackgroundBrush(QBrush(QColor("#0d1117")))

        self.drag_line = None
        self.drag_start_node = None

    def wheelEvent(self, event):
        zoom_factor = 1.15 if event.angleDelta().y() > 0 else (1 / 1.15)
        self.scale(zoom_factor, zoom_factor)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Delete, Qt.Key_Backspace):
            selected_items = self.scene().selectedItems()
            selected_nodes = [item for item in selected_items if isinstance(item, EntityNode)]
            selected_edges = [item for item in selected_items if isinstance(item, Edge)]
            
            if selected_edges:
                self.scene().remove_edges(selected_edges)
            if selected_nodes:
                self.scene().remove_entities(selected_nodes)
        else:
            super().keyPressEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and event.modifiers() & Qt.ShiftModifier:
            item = self.itemAt(event.pos())
            if isinstance(item, EntityNode):
                self.drag_start_node = item
                scene_pos = self.mapToScene(event.pos())
                self.drag_line = QGraphicsLineItem(QLineF(scene_pos, scene_pos))
                self.drag_line.setPen(QPen(QColor("#58a6ff"), 2, Qt.DashLine))
                self.scene().addItem(self.drag_line)
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.drag_line and self.drag_start_node:
            scene_pos = self.mapToScene(event.pos())
            line = self.drag_line.line()
            line.setP2(scene_pos)
            self.drag_line.setLine(line)
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.drag_line and self.drag_start_node:
            self.scene().removeItem(self.drag_line)
            self.drag_line = None
            target_item = self.itemAt(event.pos())
            if isinstance(target_item, EntityNode) and target_item != self.drag_start_node:
                self.scene().connect_nodes(self.drag_start_node, target_item)
            self.drag_start_node = None
            return
        super().mouseReleaseEvent(event)
