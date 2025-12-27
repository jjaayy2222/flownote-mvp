# backend/api/endpoints/graph.py

from fastapi import APIRouter
from backend.database.connection import DatabaseConnection
import random

router = APIRouter(prefix="/graph", tags=["visualization"])


@router.get("/data")
async def get_graph_data():
    """
    PARA Graph View를 위한 노드와 엣지 데이터 반환 using React Flow format
    """
    nodes = []
    edges = []

    # helper for positions
    # PARA Categories layout (fixed)
    category_positions = {
        "Projects": {"x": 0, "y": 0},
        "Areas": {"x": 600, "y": 0},
        "Resources": {"x": 0, "y": 600},
        "Archive": {"x": 600, "y": 600},
    }

    # 1. Add Category Nodes
    for cat, pos in category_positions.items():
        nodes.append(
            {
                "id": cat,
                "type": "input",
                "data": {"label": cat},
                "position": pos,
                "style": {
                    "width": 120,
                    "height": 120,
                    "borderRadius": "50%",
                    "display": "flex",
                    "justifyContent": "center",
                    "alignItems": "center",
                    "backgroundColor": "#e0e7ff",
                    "border": "2px solid #6366f1",
                    "fontWeight": "bold",
                    "fontSize": "14px",
                    "color": "#3730a3",
                },
            }
        )

    db = DatabaseConnection()
    files = db.get_files_with_para()
    db.close()

    # 2. Add File Nodes and Edges
    for file in files:
        file_id = str(file["id"])
        filename = file["filename"]
        category = file["para_category"]

        if not category:
            category = "Unclassified"  # Handle unclassified files if needed

        # Skip if category is not in our main PARA (unless we want to show uncategorized)
        if category not in category_positions:
            continue

        # Random offset around the category
        base_pos = category_positions[category]
        offset_x = random.randint(-200, 200)
        offset_y = random.randint(-200, 200)

        # Avoid placing too close to center
        if abs(offset_x) < 80 and abs(offset_y) < 80:
            offset_x += 100

        file_node_id = f"file-{file_id}"

        nodes.append(
            {
                "id": file_node_id,
                "data": {"label": filename},
                "position": {
                    "x": base_pos["x"] + offset_x,
                    "y": base_pos["y"] + offset_y,
                },
                "style": {
                    "width": 100,
                    "height": 40,
                    "borderRadius": "20px",
                    "fontSize": "12px",
                    "display": "flex",
                    "justifyContent": "center",
                    "alignItems": "center",
                    "backgroundColor": "white",
                    "border": "1px solid #cbd5e1",
                },
            }
        )

        # Edge from Category to File
        edges.append(
            {
                "id": f"e-{category}-{file_node_id}",
                "source": category,
                "target": file_node_id,
                "animated": True,
            }
        )

    return {"nodes": nodes, "edges": edges}
