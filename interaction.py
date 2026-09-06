"""Mouse/keyboard handling, edge hovering, and loop construction."""
import math

import vtk


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