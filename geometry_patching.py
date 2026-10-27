"""
Interactive face extraction from a wireframe OBJ.

Hover an edge to highlight it, click connected edges to build a closed loop,
and the enclosed face is triangulated and committed automatically. Press 't'
to write the result to the output OBJ.
"""
import argparse
import os
import sys

from faces import FaceManager
from interaction import (
    EdgeHoverHighlighter,
    EdgeSelectionManager,
    WireframeInteractivity,
)
from obj_io import (
    MeshObjLoader,
    ObjFaceSaver,
    WireframeObjLoader,
    default_output_path,
)
from visualization import MeshVisualizer, WireframeVisualizer


class Main:
    def __init__(self, wire_path: str, mesh_path: str = "", output_path: str = ""):
        self.wire_path = wire_path
        self.mesh_path = mesh_path

        self.loader = WireframeObjLoader(wire_path)
        self.mesh_loader = MeshObjLoader(mesh_path) if mesh_path else None

        self.viewer = WireframeVisualizer()

        self.mesh_vis = None
        self.hover = None
        self.faces = None
        self.select = None
        self.interactivity = None

        # Pass mesh path to saver so it can read existing faces
        self.saver = ObjFaceSaver(
            output_path or default_output_path(wire_path),
            mesh_path=mesh_path
        )

    def run(self):
        # wireframe
        self.loader.load()
        self.viewer.set_wireframe(self.loader.vertices, self.loader.lines)

        # optional mesh
        if self.mesh_loader:
            self.mesh_loader.load()
            self.mesh_vis = MeshVisualizer(self.viewer.renderer)
            self.mesh_vis.set_mesh(self.mesh_loader.vertices, self.mesh_loader.faces)

        self.hover = EdgeHoverHighlighter(self.viewer.interactor, self.viewer.renderer, self.viewer.polydata, pixel_tol=8)
        self.faces = FaceManager(self.viewer.renderer, self.viewer.polydata.GetPoints())
        self.select = EdgeSelectionManager(self.viewer.interactor, self.viewer.renderer, self.viewer.polydata, self.hover, self.faces)
        self.interactivity = WireframeInteractivity(self.viewer.interactor, self.viewer.renderer, self.select, self.loader, self.faces, self.saver)

        print(f"Output will be written to: {self.saver.output_path}")
        print("Controls: hover an edge, left-click to select, 't' to save.")

        self.viewer.maximise()
        self.viewer.show()


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        prog="geometry_patching",
        description="Interactively extract faces from a wireframe OBJ by clicking edge loops.",
        epilog=(
            "Controls: right-drag rotates, middle-drag pans, left-click selects the "
            "highlighted edge, 't' saves the output OBJ."
        ),
    )
    parser.add_argument(
        "wireframe",
        help="Path to the wireframe OBJ (contains 'v' and 'l' entries).",
    )
    parser.add_argument(
        "-m", "--mesh",
        default="",
        help=(
            "Optional mesh OBJ (contains 'v' and 'f' entries) drawn as a translucent "
            "backdrop. Its existing faces are carried into the output. Must share "
            "vertex ordering with the wireframe."
        ),
    )
    parser.add_argument(
        "-o", "--output",
        default="",
        help=(
            "Output OBJ path. Defaults to '<wireframe-name>_faces.obj' in the "
            "current directory."
        ),
    )

    args = parser.parse_args(argv)

    if not os.path.isfile(args.wireframe):
        parser.error(f"wireframe file not found: {args.wireframe}")
    if args.mesh and not os.path.isfile(args.mesh):
        parser.error(f"mesh file not found: {args.mesh}")

    return args


def main(argv=None):
    args = parse_args(argv)
    Main(args.wireframe, args.mesh, args.output).run()
    return 0


if __name__ == "__main__":
    sys.exit(main())