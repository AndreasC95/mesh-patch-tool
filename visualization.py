"""VTK rendering for the wireframe and the optional backdrop mesh."""
import vtk


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