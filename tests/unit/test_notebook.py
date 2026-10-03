import json
from pathlib import Path

NOTEBOOK = (
    Path(__file__).parents[2] / "output" / "jupyter-notebook" / "sap-flowguard-end-to-end.ipynb"
)


def test_end_to_end_notebook_is_clean_and_compilable():
    data = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    assert data["nbformat"] == 4
    assert len(data["cells"]) >= 20
    assert data["metadata"]["kernelspec"]["name"] == "python3"
    for index, cell in enumerate(data["cells"]):
        if cell["cell_type"] != "code":
            continue
        assert cell["execution_count"] is None
        assert cell["outputs"] == []
        compile("".join(cell["source"]), f"notebook-cell-{index}", "exec")
