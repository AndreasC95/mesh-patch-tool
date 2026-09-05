"""
Interactive face extraction from a wireframe OBJ.

Hover an edge to highlight it, click connected edges to build a closed loop,
and the enclosed face is triangulated and committed automatically. Press 't'
to write the result to the output OBJ.
"""
import argparse
import os
import sys
import vtk
import math


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


class MeshVisualizer:
    """VTK rendering for a mesh (vertices + faces)."""

    def __init__(self, renderer):
        self.ren = renderer
        self.actor = vtk.vtkActor()
        self.actor.GetProperty().SetColor(0.2, 0.2, 1.0)  
        self.actor.GetProperty().SetOpacity(0.25)         
        self.ren.AddActor(self.actor)

    def set_mesh(self, vertices, faces):
        pts = vtk.vtkPoints()
        for x, y, z in vertices:
            pts.InsertNextPoint(x, y, z)

        polys = vtk.vtkCellArray()
        for face in faces:
            polys.InsertNextCell(len(face))
            for vid in face:
                polys.InsertCellPoint(vid)

        poly = vtk.vtkPolyData()
        poly.SetPoints(pts)
        poly.SetPolys(polys)

        mapper = vtk.vtkPolyDataMapper()
        mapper.SetInputData(poly)
        self.actor.SetMapper(mapper)


class WireframeVisualizer:
    """VTK rendering for a wireframe (vertices + polylines)."""

    def __init__(self):
        self.renderer = vtk.vtkRenderer()
        self.renderer.SetBackground(1.0, 1.0, 1.0)
        self.window = vtk.vtkRenderWindow()
        self.window.SetWindowName("Geometry Patching")
        self.window.AddRenderer(self.renderer)
        self.interactor = vtk.vtkRenderWindowInteractor()
        self.interactor.SetRenderWindow(self.window)
        self.polydata = None

        self.actor = vtk.vtkActor()
        self.actor.GetProperty().SetColor(0.0, 0.0, 0.0)
        self.renderer.AddActor(self.actor)

    def set_wireframe(self, vertices, lines):
        pts = vtk.vtkPoints()
        for x, y, z in vertices:
            pts.InsertNextPoint(x, y, z)

        cells = vtk.vtkCellArray()
        for line in lines:
            pl = vtk.vtkPolyLine()
            pl.GetPointIds().SetNumberOfIds(len(line))
            for i, vid in enumerate(line):
                pl.GetPointIds().SetId(i, vid)
            cells.InsertNextCell(pl)

        poly = vtk.vtkPolyData()
        poly.SetPoints(pts)
        poly.SetLines(cells)

        self.polydata = poly  # expose for external use

        mapper = vtk.vtkPolyDataMapper()
        mapper.SetInputData(self.polydata)
        self.actor.SetMapper(mapper)

        self.renderer.ResetCamera()

    def maximise(self):
        self.window.SetFullScreen(False)

        screen_w, screen_h = self.window.GetScreenSize()
        self.window.SetSize(screen_w, screen_h)
        self.window.SetPosition(0, 0)

    def show(self):
        self.window.Render()
        self.interactor.Initialize()
        self.interactor.Start()


class WireframeInteractivityStyle(vtk.vtkInteractorStyleTrackballCamera):
    def __init__(self, renderer):
        super().__init__()
        self.ren = renderer

        self.rotating = False
        self.panning = False
        self.last_xy = (0, 0)
        self.sensitivity = 0.25

        # injected later:
        self.sel = None
        self.saver = None
        self.loader = None   # expects .vertices
        self.faces = None    # expects .faces (list of loops)

        self.AddObserver("LeftButtonPressEvent", self._l_down)
        self.AddObserver("LeftButtonReleaseEvent", self._noop)

        self.AddObserver("RightButtonPressEvent", self._r_down)
        self.AddObserver("RightButtonReleaseEvent", self._r_up)

        self.AddObserver("MiddleButtonPressEvent", self._m_down)
        self.AddObserver("MiddleButtonReleaseEvent", self._m_up)

        self.AddObserver("MouseMoveEvent", self._move)

        self.AddObserver("KeyPressEvent", self._key)

    def _noop(self, obj, evt):
        return

    def _l_down(self, obj, evt):
        if self.sel is not None:
            self.sel.on_left_click()

    def _r_down(self, obj, evt):
        self.rotating = True
        self.last_xy = self.GetInteractor().GetEventPosition()

    def _r_up(self, obj, evt):
        self.rotating = False

    def _m_down(self, obj, evt):
        self.panning = True
        self.StartPan()

    def _m_up(self, obj, evt):
        self.panning = False
        self.EndPan()

    def _move(self, obj, evt):
        if self.panning:
            self.Pan()
            return

        if not self.rotating:
            return

        x, y = self.GetInteractor().GetEventPosition()
        lx, ly = self.last_xy
        dx, dy = x - lx, y - ly
        self.last_xy = (x, y)

        cam = self.ren.GetActiveCamera()
        cam.Azimuth(dx * self.sensitivity)
        cam.Elevation(dy * self.sensitivity)
        self.ren.ResetCameraClippingRange()
        self.GetInteractor().GetRenderWindow().Render()

    def _key(self, obj, evt):
        key = self.GetInteractor().GetKeySym()
        if key == "t" and self.saver and self.loader and self.faces:
            self.saver.save(self.loader.vertices, self.loader.lines, self.faces.faces)
            print(f"Saved extracted faces -> {self.saver.output_path}")


class WireframeInteractivity:
    """Installs style and injects dependencies."""

    def __init__(self, interactor, renderer, selection_mgr, loader, face_manager, saver):
        style = WireframeInteractivityStyle(renderer)
        style.sel = selection_mgr
        style.loader = loader
        style.faces = face_manager
        style.saver = saver
        interactor.SetInteractorStyle(style)


class EdgeHoverHighlighter:
    def __init__(self, interactor, renderer, polydata, pixel_tol=8):
        self.iren = interactor
        self.ren = renderer
        self.poly = polydata
        self.pixel_tol = pixel_tol

        self.hover_edge = None  # (vid0, vid1) or None

        self.h_pts = vtk.vtkPoints()
        self.h_lines = vtk.vtkCellArray()
        self.h_poly = vtk.vtkPolyData()
        self.h_poly.SetPoints(self.h_pts)
        self.h_poly.SetLines(self.h_lines)

        mapper = vtk.vtkPolyDataMapper()
        mapper.SetInputData(self.h_poly)

        self.h_actor = vtk.vtkActor()
        self.h_actor.SetMapper(mapper)
        self.h_actor.GetProperty().SetColor(0, 1, 0)
        self.h_actor.GetProperty().SetLineWidth(4)
        self.h_actor.VisibilityOff()
        self.ren.AddActor(self.h_actor)

        self.iren.AddObserver("MouseMoveEvent", self._on_move)

    def _project(self, p):
        self.ren.SetWorldPoint(p[0], p[1], p[2], 1.0)
        self.ren.WorldToDisplay()
        x, y, _ = self.ren.GetDisplayPoint()
        return x, y

    def _dist_point_seg(self, px, py, ax, ay, bx, by):
        vx, vy = bx - ax, by - ay
        wx, wy = px - ax, py - ay
        c1 = vx * wx + vy * wy
        if c1 <= 0:
            return math.hypot(px - ax, py - ay)
        c2 = vx * vx + vy * vy
        if c2 <= c1:
            return math.hypot(px - bx, py - by)
        t = c1 / c2
        ix, iy = ax + t * vx, ay + t * vy
        return math.hypot(px - ix, py - iy)

    def _on_move(self, obj, evt):
        mx, my = self.iren.GetEventPosition()

        pts = self.poly.GetPoints()
        lines = self.poly.GetLines()
        lines.InitTraversal()

        best = None
        best_d = self.pixel_tol

        ids = vtk.vtkIdList()
        while lines.GetNextCell(ids):
            for i in range(ids.GetNumberOfIds() - 1):
                a = ids.GetId(i)
                b = ids.GetId(i + 1)
                p0 = pts.GetPoint(a)
                p1 = pts.GetPoint(b)
                x0, y0 = self._project(p0)
                x1, y1 = self._project(p1)

                d = self._dist_point_seg(mx, my, x0, y0, x1, y1)
                if d < best_d:
                    best_d = d
                    best = (a, b, p0, p1)

        if best is None:
            self.hover_edge = None
            self.h_actor.VisibilityOff()
        else:
            a, b, p0, p1 = best
            self.hover_edge = (a, b)

            self.h_pts.Reset()
            self.h_lines.Reset()
            i0 = self.h_pts.InsertNextPoint(p0)
            i1 = self.h_pts.InsertNextPoint(p1)
            self.h_lines.InsertNextCell(2)
            self.h_lines.InsertCellPoint(i0)
            self.h_lines.InsertCellPoint(i1)
            self.h_poly.Modified()
            self.h_actor.VisibilityOn()

        self.iren.GetRenderWindow().Render()


class EdgeSelectionManager:
    def __init__(self, interactor, renderer, polydata, hover, face_manager):
        self.iren = interactor
        self.ren = renderer
        self.poly = polydata
        self.hover = hover
        self.faces = face_manager
        self.head_id = None
        self.tail_id = None

        self.edges = []        # directed chain [(a,b), ...]
        self.edge_set = set()  # undirected edges in current selection

        # red selected edges overlay
        self.e_pts = vtk.vtkPoints()
        self.e_lines = vtk.vtkCellArray()
        self.e_poly = vtk.vtkPolyData()
        self.e_poly.SetPoints(self.e_pts)
        self.e_poly.SetLines(self.e_lines)

        e_mapper = vtk.vtkPolyDataMapper()
        e_mapper.SetInputData(self.e_poly)

        self.e_actor = vtk.vtkActor()
        self.e_actor.SetMapper(e_mapper)
        self.e_actor.GetProperty().SetColor(1, 0, 0)
        self.e_actor.GetProperty().SetLineWidth(4)
        self.ren.AddActor(self.e_actor)

    def on_left_click(self):
        he = self.hover.hover_edge
        if not he:
            return

        a, b = he

        u = (a, b) if a < b else (b, a)

        # prevent duplicates only within current chain
        if u in self.edge_set:
            return

        # first edge
        if not self.edges:
            self.edges.append((a, b))
            self.head_id = a
            self.tail_id = b
            self.edge_set.add(u)
            self._update_red_edges()
            self.iren.GetRenderWindow().Render()
            return

        # Given clicked edge endpoints (a,b)
        if a == self.tail_id:
            self.edges.append((a, b))
            self.tail_id = b
        elif b == self.tail_id:
            self.edges.append((b, a))
            self.tail_id = a
        elif a == self.head_id:
            # connect at head: prepend with correct direction
            self.edges.insert(0, (b, a))
            self.head_id = b
        elif b == self.head_id:
            self.edges.insert(0, (a, b))
            self.head_id = a
        else:
            print("REJECT: edge does not connect to head or tail")
            return

        self._update_red_edges()

        loop = self._try_build_loop_vertices()
        if loop:
            self.faces.add_face(loop)   
            self.clear_selection()     

        self.iren.GetRenderWindow().Render()

    def clear_selection(self):
        self.edges.clear()
        self.edge_set.clear()
        self.head_id = None
        self.tail_id = None
        self.e_pts.Reset()
        self.e_lines.Reset()
        self.e_poly.Modified()

    def _update_red_edges(self):
        pts0 = self.poly.GetPoints()
        self.e_pts.Reset()
        self.e_lines.Reset()

        for a, b in self.edges:
            i0 = self.e_pts.InsertNextPoint(pts0.GetPoint(a))
            i1 = self.e_pts.InsertNextPoint(pts0.GetPoint(b))
            self.e_lines.InsertNextCell(2)
            self.e_lines.InsertCellPoint(i0)
            self.e_lines.InsertCellPoint(i1)

        self.e_poly.Modified()

    def _try_build_loop_vertices(self):
        if len(self.edges) < 3:
            return None

        verts = [self.edges[0][0], self.edges[0][1]]
        for a, b in self.edges[1:]:
            if a != verts[-1]:
                return None
            verts.append(b)

        if verts[-1] != verts[0]:
            return None

        deg = {}
        for a, b in self.edges:
            deg[a] = deg.get(a, 0) + 1
            deg[b] = deg.get(b, 0) + 1
        if any(v != 2 for v in deg.values()):
            return None

        return verts[:-1]


def _vsub(a, b): return (a[0]-b[0], a[1]-b[1], a[2]-b[2])
def _vdot(a, b): return a[0]*b[0] + a[1]*b[1] + a[2]*b[2]
def _vcross(a, b):
    return (a[1]*b[2]-a[2]*b[1],
            a[2]*b[0]-a[0]*b[2],
            a[0]*b[1]-a[1]*b[0])
def _vlen(a): return math.sqrt(_vdot(a, a))


def _newell_normal(points3):
    # stable polygon normal for (nearly) planar loops
    nx = ny = nz = 0.0
    n = len(points3)
    for i in range(n):
        x0, y0, z0 = points3[i]
        x1, y1, z1 = points3[(i+1) % n]
        nx += (y0 - y1) * (z0 + z1)
        ny += (z0 - z1) * (x0 + x1)
        nz += (x0 - x1) * (y0 + y1)
    return (nx, ny, nz)


def _make_basis_from_normal(n):
    # returns orthonormal (u,v) spanning plane with normal n
    nl = _vlen(n)
    if nl < 1e-12:
        return None
    n = (n[0]/nl, n[1]/nl, n[2]/nl)
    # pick a vector not parallel to n
    a = (1.0, 0.0, 0.0) if abs(n[0]) < 0.9 else (0.0, 1.0, 0.0)
    u = _vcross(a, n)
    ul = _vlen(u)
    if ul < 1e-12:
        a = (0.0, 0.0, 1.0)
        u = _vcross(a, n)
        ul = _vlen(u)
        if ul < 1e-12:
            return None
    u = (u[0]/ul, u[1]/ul, u[2]/ul)
    v = _vcross(n, u)
    return u, v, n


def _project_2d(points3, origin3, u, v):
    pts2 = []
    for p in points3:
        d = _vsub(p, origin3)
        pts2.append((_vdot(d, u), _vdot(d, v)))
    return pts2


def _area2(poly2):
    a = 0.0
    n = len(poly2)
    for i in range(n):
        x0, y0 = poly2[i]
        x1, y1 = poly2[(i+1) % n]
        a += x0*y1 - x1*y0
    return a


def _is_ccw(poly2):
    return _area2(poly2) > 0


def _cross2(a, b, c):
    # z-component of cross((b-a),(c-a)) in 2D
    return (b[0]-a[0])*(c[1]-a[1]) - (b[1]-a[1])*(c[0]-a[0])


def _pt_in_tri(p, a, b, c, eps=1e-12):
    # barycentric sign test (inclusive)
    c1 = _cross2(a, b, p)
    c2 = _cross2(b, c, p)
    c3 = _cross2(c, a, p)
    has_neg = (c1 < -eps) or (c2 < -eps) or (c3 < -eps)
    has_pos = (c1 > eps) or (c2 > eps) or (c3 > eps)
    return not (has_neg and has_pos)


def triangulate_concave_loop(loop_vids, points3, planarity_eps=1e-4):
    """
    loop_vids: [v0, v1, ...] original vertex ids, in loop order
    points3:   [(x,y,z), ...] coordinates, parallel to loop_vids
    returns: list of triangles as [(a,b,c), ...] using ORIGINAL vertex ids (not offset)
    """
    n = len(loop_vids)
    if n < 3 or len(points3) != n:
        return []

    pts3 = list(points3)
    normal = _newell_normal(pts3)
    basis = _make_basis_from_normal(normal)
    if basis is None:
        return []
    u, v, nrm = basis

    origin = pts3[0]

    # optional: planarity check (distance to plane along normal)
    for p in pts3:
        d = _vsub(p, origin)
        dist = abs(_vdot(d, nrm))
        if dist > planarity_eps:
            # not planar enough -> refuse (or you can still project and continue)
            return []

    poly2 = _project_2d(pts3, origin, u, v)

    # ensure CCW winding for ear clipping
    if not _is_ccw(poly2):
        loop_vids = list(reversed(loop_vids))
        poly2 = list(reversed(poly2))

    # ear clipping on index list
    idx = list(range(len(loop_vids)))
    triangles = []

    def is_convex(i0, i1, i2):
        return _cross2(poly2[i0], poly2[i1], poly2[i2]) > 1e-12

    guard = 0
    while len(idx) > 3 and guard < 10000:
        guard += 1
        ear_found = False

        for k in range(len(idx)):
            i_prev = idx[(k-1) % len(idx)]
            i_curr = idx[k]
            i_next = idx[(k+1) % len(idx)]

            if not is_convex(i_prev, i_curr, i_next):
                continue

            a = poly2[i_prev]; b = poly2[i_curr]; c = poly2[i_next]

            # no other point inside ear
            ok = True
            for j in idx:
                if j in (i_prev, i_curr, i_next):
                    continue
                if _pt_in_tri(poly2[j], a, b, c):
                    ok = False
                    break
            if not ok:
                continue

            # commit ear triangle using ORIGINAL ids
            triangles.append((loop_vids[i_prev], loop_vids[i_curr], loop_vids[i_next]))
            del idx[k]
            ear_found = True
            break

        if not ear_found:
            # polygon likely self-intersecting or numerically nasty
            return []

    if len(idx) == 3:
        triangles.append((loop_vids[idx[0]], loop_vids[idx[1]], loop_vids[idx[2]]))

    return triangles


class FaceManager:
    def __init__(self, renderer, source_points):
        self.ren = renderer
        self.src_pts = source_points  # vtkPoints from wireframe polydata

        self.pts = vtk.vtkPoints()
        self.polys = vtk.vtkCellArray()

        self.poly = vtk.vtkPolyData()
        self.poly.SetPoints(self.pts)
        self.poly.SetPolys(self.polys)

        mapper = vtk.vtkPolyDataMapper()
        mapper.SetInputData(self.poly)

        self.actor = vtk.vtkActor()
        self.actor.SetMapper(mapper)
        self.actor.GetProperty().SetColor(1, 1, 0)
        self.actor.GetProperty().SetOpacity(1)
        self.actor.GetProperty().EdgeVisibilityOn() 
        self.ren.AddActor(self.actor)

        self.faces = []  # store loops for export later

    def add_face(self, loop_vids):
        # triangulate loop -> triangles in ORIGINAL vertex ids
        pts3 = [self.src_pts.GetPoint(vid) for vid in loop_vids]
        tris = triangulate_concave_loop(loop_vids, pts3, planarity_eps=1e-4)
        if not tris:
            print("Triangulation failed (non-planar / self-intersecting / degenerate). Face skipped.")
            return

        # store triangles for export
        for a, b, c in tris:
            self.faces.append([a, b, c])

        # insert triangles into VTK polydata (using NEW local points appended)
        for a, b, c in tris:
            start = self.pts.GetNumberOfPoints()
            self.pts.InsertNextPoint(self.src_pts.GetPoint(a))
            self.pts.InsertNextPoint(self.src_pts.GetPoint(b))
            self.pts.InsertNextPoint(self.src_pts.GetPoint(c))

            self.polys.InsertNextCell(3)
            self.polys.InsertCellPoint(start + 0)
            self.polys.InsertCellPoint(start + 1)
            self.polys.InsertCellPoint(start + 2)

        self.pts.Modified()
        self.polys.Modified()
        self.poly.Modified()


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


def default_output_path(wire_path: str) -> str:
    """Derive '<name>_faces.obj' in the current directory from the wireframe path."""
    stem = os.path.splitext(os.path.basename(wire_path))[0]
    return os.path.join(os.getcwd(), f"{stem}_faces.obj")


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
