"""Accumulates committed faces and draws them."""
import vtk

from triangulation import triangulate_concave_loop


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