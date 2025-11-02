import time

from sqlalchemy_utils import Ltree

from ingest.core.analysis import GraphAnalyzer, sanitize_for_ltree


def test_process_node_pass1_assigns_hierarchy_path_without_local_id(monkeypatch):
	# Freeze time to make generated identifiers deterministic for assertions
	fixed_ns = 123456789

	def fake_time_ns():
		return fixed_ns

	monkeypatch.setattr(time, "time_ns", fake_time_ns)

	analyzer = GraphAnalyzer(default_act_id="ITAA1997")
	act_root = sanitize_for_ltree("ITAA1997")

	root_node = {
		"ref_id": "ITAA1997:Division:5",
		"id": "Division_5",
		"type": "Division",
		"title": "Division 5",
		"children": [
			{
				"type": "Guide",
				"title": "Guide to Division 5",
				"content_md": "",
			}
		]
	}

	analyzer.process_node_pass1(root_node, ltree_path=act_root, sibling_index=0)

	root_entry = analyzer.node_registry["ITAA1997_Division_5"]
	assert isinstance(root_entry["hierarchy_path_ltree"], Ltree)
	assert str(root_entry["hierarchy_path_ltree"]) == "ITAA1997.Division_5"

	child_internal_id = None
	child_entry = None
	for internal_id, data in analyzer.node_registry.items():
		if data.get("title") == "Guide to Division 5":
			child_internal_id = internal_id
			child_entry = data
			break

	assert child_entry is not None, "Child node missing from registry"
	assert child_entry["parent_internal_id"] == "ITAA1997_Division_5"
	assert isinstance(child_entry["hierarchy_path_ltree"], Ltree)
	child_path = str(child_entry["hierarchy_path_ltree"])
	assert child_path.startswith("ITAA1997.Division_5.Guide_")
	assert child_internal_id is not None
	assert child_entry["hierarchy_path_ltree"] == Ltree(child_path)
