"""Vector helpers and ear-clipping triangulation of a closed loop."""
import math


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