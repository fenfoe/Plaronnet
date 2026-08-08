import sys
import json
from PyQt5.QtCore import Qt, QRectF, QLineF
from PyQt5.QtGui import QPen, QColor, QFont, QPainter, QBrush, QFontMetrics
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QGraphicsView, QGraphicsScene,
    QGraphicsItem, QGraphicsLineItem, QMenu, QToolBar, QAction, 
    QInputDialog, QFileDialog, QMessageBox
)


def raw_json_to_graph(raw_data, root_label="ROOT"):
    """Recursively converts arbitrary raw JSON data into graph format."""
    nodes = []
    edges = []
    node_counter = [0]

    def get_node_type(val):
        if isinstance(val, dict):
            return "Domain"
        elif isinstance(val, list):
            return "URL"
        elif isinstance(val, (int, float)):
            return "IP"
        return "generic"

    def traverse(data, key_label, parent_id=None, depth=0, y_offset=[0]):
        node_counter[0] += 1
        node_id = f"node_{node_counter[0]}"
        node_type = get_node_type(data)
        
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


class Edge(QGraphicsLineItem):
    def __init__(self, source_node, target_node):
        super().__init__()
        self.source = source_node
        self.target = target_node
        
        # Enable selection and mouse interactions on the edge
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
        line = self.line()
        line.setP1(self.source.scenePos())
        line.setP2(self.target.scenePos())
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
        # Change pen depending on selection state
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
    TYPES = ["IP", "Domain", "URL", "generic"]

    def __init__(self, entity_id, label, entity_type="generic"):
        super().__init__()
        self.id = entity_id
        self.label = label
        self.entity_type = entity_type if entity_type in self.TYPES else "generic"
        self.edges = []

        self.setFlags(
            QGraphicsItem.ItemIsMovable |
            QGraphicsItem.ItemIsSelectable |
            QGraphicsItem.ItemSendsGeometryChanges
        )
        self.setZValue(1)

        self.min_width = 120
        self.height = 45
        self.font = QFont("Consolas", 8, QFont.Bold)

        self.color_map = {
            "IP": QColor("#1f6feb"),       # Blue
            "Domain": QColor("#238636"),   # Green
            "URL": QColor("#8957e5"),      # Purple
            "generic": QColor("#30363d")   # Dark Grey
        }

    def get_calculated_width(self):
        metrics = QFontMetrics(self.font)
        text_width = metrics.horizontalAdvance(self.label)
        return max(self.min_width, text_width + 28)

    def boundingRect(self):
        width = self.get_calculated_width()
        return QRectF(-width / 2, -self.height / 2, width, self.height)

    def paint(self, painter, option, widget):
        painter.setRenderHint(QPainter.Antialiasing)
        width = self.get_calculated_width()
        rect = QRectF(-width / 2, -self.height / 2, width, self.height)

        if self.isSelected():
            painter.setPen(QPen(QColor("#58a6ff"), 2, Qt.DashLine))
        else:
            painter.setPen(QPen(QColor("#30363d"), 1))

        painter.setBrush(QBrush(QColor("#161b22")))
        painter.drawRoundedRect(rect, 6, 6)

        badge_color = self.color_map.get(self.entity_type, self.color_map["generic"])
        badge_rect = QRectF(-width / 2, -self.height / 2, 8, self.height)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(badge_color))
        painter.drawRoundedRect(badge_rect, 2, 2)

        painter.setPen(QPen(QColor("#c9d1d9")))
        painter.setFont(self.font)
        text_rect = QRectF(-width / 2 + 14, -self.height / 2, width - 18, self.height)
        painter.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft, self.label)

    def add_edge(self, edge):
        if edge not in self.edges:
            self.edges.append(edge)

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionHasChanged:
            for edge in self.edges:
                edge.update_position()
        return super().itemChange(change, value)

    def set_type(self, new_type):
        if new_type in self.TYPES:
            self.entity_type = new_type
            self.update()

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

        count = len(selected_nodes)
        
        if count == 2:
            connect_action = menu.addAction("🔗 Connect Selected 2 Nodes")
            menu.addSeparator()
        else:
            connect_action = None

        title_text = f"Selected: {count} Node(s)" if count > 1 else f"Entity: {self.label}"
        title_action = menu.addAction(title_text)
        title_action.setEnabled(False)
        menu.addSeparator()

        if count == 1:
            change_type_menu = menu.addMenu("🏷️ Change Entity Type")
            type_actions = {}
            for t in self.TYPES:
                act = change_type_menu.addAction(t)
                if t == self.entity_type:
                    act.setCheckable(True)
                    act.setChecked(True)
                type_actions[act] = t

            transform_ip = menu.addAction("Transform: Resolve IP")
            transform_ports = menu.addAction("Transform: Scan Ports")
            add_child = menu.addAction("+ Add Connected Node")
            menu.addSeparator()
        else:
            change_type_menu = transform_ip = transform_ports = add_child = None

        delete_node = menu.addAction(f"Delete ({count} selected)" if count > 1 else "Delete Entity")

        action = menu.exec_(event.screenPos())

        if action == connect_action and count == 2:
            scene.connect_nodes(selected_nodes[0], selected_nodes[1])
        elif action == delete_node:
            scene.remove_entities(selected_nodes)
        elif count == 1:
            if action in type_actions:
                self.set_type(type_actions[action])
            elif action == transform_ip:
                scene.apply_transform_resolve_domain(self)
            elif action == transform_ports:
                scene.apply_transform_scan_ports(self)
            elif action == add_child:
                scene.add_manual_child(self)


class InteractiveGraphScene(QGraphicsScene):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setBackgroundBrush(QBrush(QColor("#0d1117")))
        self.nodes = {}
        self.edges_list = []

    def load_from_json(self, json_data):
        self.clear()
        self.nodes.clear()
        self.edges_list.clear()

        for item in json_data.get("nodes", []):
            node = EntityNode(str(item["id"]), item["label"], item.get("type", "generic"))
            node.setPos(item.get("x", 0), item.get("y", 0))
            self.addItem(node)
            self.nodes[str(item["id"])] = node

        for conn in json_data.get("edges", []):
            src = self.nodes.get(str(conn["source"]))
            tgt = self.nodes.get(str(conn["target"]))
            if src and tgt:
                self.connect_nodes(src, tgt)

    def export_to_json(self):
        nodes_data = []
        for node_id, node in self.nodes.items():
            pos = node.scenePos()
            nodes_data.append({
                "id": str(node_id),
                "label": node.label,
                "type": node.entity_type,
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
        """Creates an edge between two existing nodes if not connected already."""
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

    def auto_layout(self, cols_per_row=4):
        """
        Arranges nodes in a balanced 2D Pyramid/Grid layout.
        Each parent arranges its direct children into a grid of 'cols_per_row'
        width, spreading both horizontally and vertically.
        """
        if not self.nodes:
            return

        import math

        if not isinstance(cols_per_row, int) or cols_per_row < 1:
            cols_per_row = 4

        # 1. Find root nodes (nodes with no incoming edges)
        targets = {edge.target for edge in self.edges_list}
        roots = [node for node in self.nodes.values() if node not in targets]
        if not roots:
            roots = [next(iter(self.nodes.values()))]

        visited = set()
        global_y = [0.0]

        
        X_SPACING = 240
        Y_SPACING = 65

        def layout_subtree(node, depth):
            if node.id in visited:
                return 0
            visited.add(node.id)

            children = []
            for edge in node.edges:
                child = edge.target if edge.source == node else edge.source
                if child.id not in visited:
                    children.append(child)

            if not children:
                y_pos = global_y[0] * Y_SPACING
                node.setPos(depth * X_SPACING, y_pos)
                global_y[0] += 1.0
                return 1.0

            num_children = len(children)
            cols = min(cols_per_row, num_children)
            rows = math.ceil(num_children / cols)

            start_y = global_y[0]

            for idx, child in enumerate(children):
                col = idx % cols
                row = idx // cols
                child_depth = depth + 1 + col
                
                layout_subtree(child, child_depth)

            end_y = global_y[0] - 1.0
            avg_y = ((start_y + end_y) / 2.0) * Y_SPACING
            node.setPos(depth * X_SPACING, avg_y)

            return (end_y - start_y + 1.0)

        for root in roots:
            layout_subtree(root, 0)
            global_y[0] += 1.5

    def apply_transform_resolve_domain(self, parent_node):
        new_id = f"node_{len(self.nodes) + 1}"
        new_node = EntityNode(new_id, f"sub.{parent_node.label}", entity_type="Domain")
        pos = parent_node.scenePos()
        new_node.setPos(pos.x() + 220, pos.y() + 60)
        
        self.addItem(new_node)
        self.nodes[new_id] = new_node
        self.connect_nodes(parent_node, new_node)

    def apply_transform_scan_ports(self, parent_node):
        ports = ["80/tcp", "443/tcp"]
        pos = parent_node.scenePos()
        for i, port in enumerate(ports):
            new_id = f"node_{len(self.nodes) + 1}"
            new_node = EntityNode(new_id, port, entity_type="URL")
            new_node.setPos(pos.x() + 220, pos.y() - 30 + (i * 60))
            
            self.addItem(new_node)
            self.nodes[new_id] = new_node
            self.connect_nodes(parent_node, new_node)

    def add_manual_child(self, parent_node):
        label, ok = QInputDialog.getText(None, "Add Node", "Enter entity label:")
        if ok and label:
            entity_type, type_ok = QInputDialog.getItem(
                None, "Select Type", "Entity Type:", EntityNode.TYPES, 0, False
            )
            if not type_ok:
                entity_type = "generic"

            new_id = f"node_{len(self.nodes) + 1}"
            new_node = EntityNode(new_id, label, entity_type=entity_type)
            pos = parent_node.scenePos()
            new_node.setPos(pos.x() + 200, pos.y())
            
            self.addItem(new_node)
            self.nodes[new_id] = new_node
            self.connect_nodes(parent_node, new_node)

    def remove_entity(self, node):
        for edge in list(node.edges):
            if edge in self.edges_list:
                self.edges_list.remove(edge)
            if edge in edge.source.edges:
                edge.source.edges.remove(edge)
            if edge in edge.target.edges:
                edge.target.edges.remove(edge)
            self.removeItem(edge)
        
        if node.id in self.nodes:
            del self.nodes[node.id]
        self.removeItem(node)

    def remove_entities(self, nodes_to_remove):
        for node in list(nodes_to_remove):
            self.remove_entity(node)

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
        # Shift + Left Click to start drag-connecting nodes
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
