"""左侧分类树：按当前分组维度统计各档位的视频数量。"""

from __future__ import annotations

from typing import Dict, List, Sequence, Tuple

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QTreeWidget, QTreeWidgetItem

from .. import classify
from .list_model import VideoItem

PATH_ROLE = int(Qt.ItemDataRole.UserRole) + 1


class CategoryTree(QTreeWidget):
    categorySelected = Signal(list)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setHeaderHidden(True)
        self.setUniformRowHeights(True)
        self.setAnimated(False)
        self.setExpandsOnDoubleClick(True)
        self.itemSelectionChanged.connect(self._on_selection_changed)

    def rebuild(self, items: Sequence[VideoItem], dimensions: Sequence[str]) -> None:
        previous_path = self.selected_path()
        expanded = self._expanded_paths()

        tree: Dict[str, dict] = {}
        for item in items:
            labels = classify.group_path(item.labels, dimensions)
            ranks = [classify.rank_of(item.labels, dimension) for dimension in dimensions]
            node = tree
            for depth, label in enumerate(labels):
                entry = node.setdefault(label, {"count": 0, "rank": ranks[depth], "children": {}})
                entry["count"] += 1
                node = entry["children"]

        self.blockSignals(True)
        self.clear()
        root = QTreeWidgetItem(["全部（{}）".format(len(items))])
        root.setData(0, PATH_ROLE, [])
        self.addTopLevelItem(root)
        _populate(root, tree, [])
        root.setExpanded(True)
        for path in expanded:
            widget_item = self._find(path)
            if widget_item is not None:
                widget_item.setExpanded(True)
        target = self._find(previous_path) or root
        self.setCurrentItem(target)
        self.blockSignals(False)

    def selected_path(self) -> List[str]:
        current = self.currentItem()
        if current is None:
            return []
        return list(current.data(0, PATH_ROLE) or [])

    def _on_selection_changed(self) -> None:
        self.categorySelected.emit(self.selected_path())

    def _expanded_paths(self) -> List[List[str]]:
        paths: List[List[str]] = []

        def walk(item: QTreeWidgetItem) -> None:
            if item.isExpanded():
                paths.append(list(item.data(0, PATH_ROLE) or []))
            for index in range(item.childCount()):
                walk(item.child(index))

        for index in range(self.topLevelItemCount()):
            walk(self.topLevelItem(index))
        return paths

    def _find(self, path: Sequence[str]):
        if self.topLevelItemCount() == 0:
            return None
        current = self.topLevelItem(0)
        for label in path:
            match = None
            for index in range(current.childCount()):
                child = current.child(index)
                child_path = child.data(0, PATH_ROLE) or []
                if child_path and child_path[-1] == label:
                    match = child
                    break
            if match is None:
                return None
            current = match
        return current


def _populate(parent: QTreeWidgetItem, node: Dict[str, dict], prefix: List[str]) -> None:
    for label, entry in _sorted_entries(node):
        path = prefix + [label]
        child = QTreeWidgetItem(["{}（{}）".format(label, entry["count"])])
        child.setData(0, PATH_ROLE, path)
        parent.addChild(child)
        _populate(child, entry["children"], path)


def _sorted_entries(node: Dict[str, dict]) -> List[Tuple[str, dict]]:
    return sorted(node.items(), key=lambda pair: (pair[1]["rank"], pair[0]))
