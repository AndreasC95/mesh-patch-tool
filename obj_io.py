"""OBJ loading and writing."""
import os


class WireframeObjLoader:
    """Loads a wireframe OBJ (v + l). Stores vertices and polylines (0-based)."""

    def __init__(self, path: str):
        self.path = path
        self.vertices = []  # [(x,y,z), ...]
        self.lines = []     # [[i0,i1,...], ...]

    def load(self):
        self.vertices.clear()
        self.lines.clear()

        with open(self.path, "r", encoding="utf-8", errors="ignore") as f:
            for raw in f:
                s = raw.strip()
                if not s or s.startswith("#"):
                    continue
                tag, *rest = s.split()

                if tag == "v" and len(rest) >= 3:
                    self.vertices.append((float(rest[0]), float(rest[1]), float(rest[2])))

                elif tag == "l" and len(rest) >= 2:
                    idx = [int(r.split("/")[0]) - 1 for r in rest]  # OBJ is 1-based
                    if min(idx) < 0 or max(idx) >= len(self.vertices):
                        raise ValueError(f"Line index out of range: {s}")
                    self.lines.append(idx)

        if not self.vertices or not self.lines:
            raise ValueError("OBJ must contain at least one 'v' and one 'l'.")
        return self


class MeshObjLoader:
    """Loads a mesh OBJ (v + f). Stores vertices and faces (0-based)."""

    def __init__(self, path: str):
        self.path = path
        self.vertices = []  # [(x,y,z), ...]
        self.faces = []     # [[i0,i1,i2,...], ...]

    def load(self):
        self.vertices.clear()
        self.faces.clear()

        with open(self.path, "r", encoding="utf-8", errors="ignore") as f:
            for raw in f:
                s = raw.strip()
                if not s or s.startswith("#"):
                    continue
                tag, *rest = s.split()

                if tag == "v" and len(rest) >= 3:
                    self.vertices.append((float(rest[0]), float(rest[1]), float(rest[2])))

                elif tag == "f" and len(rest) >= 3:
                    idx = [int(r.split("/")[0]) - 1 for r in rest]
                    if min(idx) < 0 or max(idx) >= len(self.vertices):
                        raise ValueError(f"Face index out of range: {s}")
                    self.faces.append(idx)

        if not self.vertices or not self.faces:
            raise ValueError("Mesh OBJ must contain at least one 'v' and one 'f'.")
        return self


class ObjFaceSaver:
    """Writes vertices + lines from wireframe + faces from mesh + new extracted faces to output OBJ."""

    def __init__(self, output_path: str, mesh_path: str = ""):
        self.output_path = output_path
        self.mesh_path = mesh_path

    def save(self, vertices, lines, new_faces):
        # Load existing faces from mesh file if it exists
        existing_faces = []
        if self.mesh_path and os.path.exists(self.mesh_path):
            with open(self.mesh_path, 'r') as f:
                for line in f:
                    if line.startswith('f '):
                        parts = line.strip().split()[1:]
                        face_indices = [int(p.split('/')[0]) - 1 for p in parts]
                        existing_faces.append(face_indices)

        # Write output
        with open(self.output_path, "w", encoding="utf-8") as f:

            for x, y, z in vertices:
                f.write(f"v {x} {y} {z}\n")

            for line in lines:
                idx = " ".join(str(i + 1) for i in line)
                f.write(f"l {idx}\n")

            for face in existing_faces:
                idx = " ".join(str(i + 1) for i in face)
                f.write(f"f {idx}\n")

            for face in new_faces:
                idx = " ".join(str(i + 1) for i in face)
                f.write(f"f {idx}\n")


def default_output_path(wire_path: str) -> str:
    """Derive '<name>_faces.obj' in the current directory from the wireframe path."""
    stem = os.path.splitext(os.path.basename(wire_path))[0]
    return os.path.join(os.getcwd(), f"{stem}_faces.obj")