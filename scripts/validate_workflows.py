import json
from pathlib import Path


def main() -> None:
    workflow_dir = Path(__file__).parents[1] / "n8n" / "workflows"
    files = sorted(workflow_dir.glob("*.json"))
    if not files:
        raise SystemExit("No n8n workflows found")
    for path in files:
        data = json.loads(path.read_text(encoding="utf-8"))
        missing = {"name", "nodes", "connections", "active", "settings"} - data.keys()
        if missing:
            raise ValueError(f"{path.name}: missing keys {sorted(missing)}")
        names = [node["name"] for node in data["nodes"]]
        ids = [node["id"] for node in data["nodes"]]
        if len(names) != len(set(names)) or len(ids) != len(set(ids)):
            raise ValueError(f"{path.name}: duplicate node name or id")
        print(f"OK {path.name}: {len(names)} nodes")


if __name__ == "__main__":
    main()
