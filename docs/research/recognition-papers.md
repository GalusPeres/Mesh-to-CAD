# Reading a scan like a designer: literature and implementable algorithms

Scope: triangle mesh of an engineered or consumer part, noise σ = 0.02–0.1 mm, mean edge length e. Target: a feature tree (sketch + extrude/revolve + boolean + fillet/chamfer), else a valid B-Rep, freeform only where nothing else fits. Existing kernel modules are named where they already cover a step (segmentation/auto.py, fitting/constrained.py, fitting/intent.py, recognition/outline.py, sketch/fit2d.py, cad/fillet.py, cad/booleans.py).

## 0. Bottom line

1. The Várady school architecture is still the right one: segment → classify primaries vs. blends → constrained fit → sharp-edge model → blends last. No learned method reaches 0.05 mm on real scans, and most of their code is unlicensed or non-commercial.
2. Mesh connectivity + jet normals + fit-filter-connect region growing (what you have) beats point-cloud RANSAC. Use RANSAC only as a proposal generator.
3. Build the feature tree from an attributed region adjacency graph (Joshi–Chang AAG on scan regions: convex / concave / tangent / blend edges). Do not build a full B-Rep by surface intersection first. Keep an OCCT cell-arrangement B-Rep builder as a fallback for parts that are not feature-like.
4. Design intent = GlobFit-style global relation discovery + Langbein-style greedy consistent subset + Benkő-style simultaneous constrained refit, with the fit covariance as the snap window.
5. Patents to steer around (not legal advice): Geomagic/Hexagon US8004517B1 (Morse-complex separators, "thickened feature skeleton"; active until 2027-12-17) and Dassault EP4345673A1 (fillet detection by integral curves of max-curvature direction + circle statistics; filed 2022). The algorithms below are region-based and differ from both.

---

## 1. Segmentation into primitive regions, incl. blends

**Papers and what to take from them**

- **Várady, Martin, Cox 1997** (survey). Edge-based segmentation (find high-curvature or discontinuity zones, then fill regions) vs. face-based (region growing with surface hypotheses). Surface hierarchy: plane → natural quadrics → torus → translational/rotational sweeps → freeform. Blends are fitted _after_ their primaries, which constrain them.
- **Benkő & Várady 2002 (GMP) / 2004 (CAD 36(6))**. For _smooth_ regions, where no sharp edge separates the faces, a curvature indicator separates highly curved "connecting" strips (blend candidates) from primaries. Primaries are grown from seeds, testing hypotheses in increasing complexity, including best-fit translational and rotational surfaces. What is left becomes connecting features (rolling-ball blends) and vertex blends. Geomagic's automated version (Várady, Facello, Terék 2007) is the patent above.
- **Schnabel, Wahl, Klein 2007, Efficient RANSAC.** Minimal sets use normals (plane 3 points, sphere/cylinder 2, cone 3, torus 4). Sampling is local in an octree. The score counts points with |d| < ε and normal deviation < α, restricted to the largest connected component of a parameter-space bitmap (cell β), evaluated lazily on subsets. It stops when P(missed shape of n points) < p_t; the per-draw success is ≈ n/(N·d·2^(k−1)). Scan settings: ε = 2.5–3σ (at least the faceting error), α = 10–15° with jet normals, β = 2–3× spacing, p_t = 0.01. Pitfalls: greedy extraction steals blend points, leaves ragged borders and spurious planes across fillets, and ignores connectivity.
- **Attene et al. 2006 (HFP)**: greedy merging of dual-graph clusters by the fit error of a plane, sphere or cylinder gives a hierarchy, O(n log n); code EfPiSoft is **GPL**. **Lavoué et al. 2005**: k-means on (κ1, κ2), region growing, boundary rectification along principal directions. Use it only as curvature pre-classification at jet scale.
- **Mizoguchi et al. 2006.** **Explicit fillet rules**: a cylinder between two planes, a torus between a cylinder and a plane, a sphere or torus vertex blend among three fillets. _Linear-extrusion sets_: plane normals ⟂ cylinder axes, axes parallel. _Revolution sets_: axes and normals parallel, centres on one line.
- **Le & Duan 2017.** Project along the dominant orientations, Hough lines and circles in 2D, lift to planes and cylinders, select by set cover. Robust for aligned prismatic parts.
- **Yan et al. 2012, VSA 2004, Wu & Kobbelt 2005.** Lloyd iterations (assign → refit → split/merge) for _boundary refinement_.
- **Slippage / line geometry (Gelfand & Guibas 2004; Pottmann & Randrup 1998).** C = Σ aᵢaᵢᵀ with aᵢ = [pᵢ×nᵢ ; nᵢ] (points centred and scaled to unit size). An eigenvector (r, t) with λ/N < (3σₙ)² (σₙ = normal noise in rad) is a slippable motion. r ≈ 0 means an extrusion along t. r·t ≈ 0 means a revolution about the axis with direction r through r×t/|r|². Otherwise the region is helical. About 20 lines of numpy; this is the extrusion/revolve classifier for region _sets_.

**Learned methods.** ParSeNet (ECCV 2020), HPNet (ICCV 2021) and SED-Net (SIGGRAPH 2023, type + edge prediction) cluster per-point embeddings with mean-shift. Point2CAD (CVPR 2024) takes their labels, refits plane/sphere/cylinder/cone or an INR, then extends, intersects and trims. All are trained on ABC (about 10k normalised points), need a GPU, have a large domain gap to 1M-triangle scans, and need classical refits anyway. Licences: ParSeNet, HPNet and SED-Net have **none**. Point2CAD has LICENSE Apache-2.0 but README **CC BY-NC**, so treat it as NC. Not practical; reuse only Point2CAD's topology idea (§4).

**Recommended segmentation (S1–S7), mostly in place already**

1. Jet normals and curvature at scale h = 6–10 e (≥ 1 mm for σ = 0.1). Crease indicator: jet residual > 3σ (present).
2. Curvature noise floor κ₀ = 3 × the median |κ| on the largest planar region (measured per scan, not guessed). Faces are _flat_ if |κ1|, |κ2| < κ₀, _cylindrical-like_ if one is < κ₀, else doubly curved.
3. Seeds far from creases, fit-filter-connect growing with type chosen by BIC (present). Distance gate 3σ, normal gate 10–15°.
4. Leftover narrow strips between two grown regions are **blend candidates** (§2), not primaries. A cylinder or torus tangent to exactly two neighbours whose angular span ≈ φ (the angle between the neighbours' normals) and is < 180° is a fillet, not a primary.
5. Merge adjacent regions if one primitive explains both within 1.2× the RMS of the separate fits (present).
6. Border relaxation on the face graph: wave relaxation (present), or a graph cut (α-expansion) with data cost |d|/σ and a smoothness cost on dihedral angle.
7. Regions whose best primitive RMS > 3σ (or > the tolerance) are freeform (your quad net). Region _sets_ with one slippable motion become extrusion or revolve candidates.

---

## 2. Fillets, variable-radius blends, chamfers

**Papers.** Kós, Martin, Várady 2000 (CAGD 17(2)) recover constant-radius rolling-ball blends from the two primaries: the spine is the intersection of the primaries offset by r, and r is fitted. Kós 2001 extends this to variable radius (a radius function along the spine). Mizoguchi 2006 gives the classification rules. Benkő et al. 2002 put the blend into the simultaneous constrained fit (tangency as constraints). Lambourne et al. 2022 ("rounded voxel → prismatic CAD") confirm the strategy of reconstructing sharp then re-adding fillets.

**Algorithm (F1–F7).** Let A and B be fitted primaries with outward normals, φ the angle between their normals at the virtual edge (90° for a box edge), and s = +1 for a convex edge, −1 for a concave one (§3 test).

1. **Candidate.** A region R adjacent to exactly two primaries A and B (or a strip of unlabelled crease faces between them), narrow (width/length < 0.3), one principal curvature ≈ 1/r and roughly constant along R, the other ≈ 0 (straight edge) or matching the spine curvature. If R is already fitted as a cylinder, torus or sphere, apply the Mizoguchi conditions. Cylinder fillet between planes: axis ∥ n_A × n_B and dist(axis, A) = dist(axis, B) = r. Torus: axis coincides with the cylinder axis and the minor circle is tangent to both. Sphere or torus vertex blend: meets three fillets, all convex or all concave (sphere) or mixed (torus).
2. **Initial radius.** r₀ = median(1/κ_max) over the interior of R, or r₀ = w_arc/φ from the arc width w_arc of the strip.
3. **Spine and radius fit.** Ball centres satisfy d_A(c) = −s·r and d_B(c) = −s·r (offset intersection). For plane–plane the spine is a line, for plane–cylinder a circle, for the general case use OCCT `GeomAPI_IntSS` on `Geom_OffsetSurface`s. Minimise E(r) = Σ_p (dist(p, spine(r)) − r)² with a 1-D Brent search on [0.3 r₀, 3 r₀]. Robust: one parameter, no normals needed. For plane–plane it is equivalent to a cylinder fit with the axis fixed to the bisector line. Uncertainty: σ_r from the 1-D curvature of E.
4. **Tangency check.** The strip's boundary points must lie within 3σ + e of the rails, i.e. the spine projected onto A and B. The setback from the sharp edge is t = r·tan(φ/2) (t = r at 90°). If one side fails, R is a step face or a non-tangent blend, not a fillet.
5. **Variable radius.** Cut R with planes ⟂ spine every ~2r. In each slice the primaries are 2D lines and the circle tangent to both has its centre on the bisector at distance r/cos(φ/2) from the corner, so each slice is a 1-parameter fit. Fit r(s) as constant vs. linear (vs. cubic) with BIC; take the linear law only if it lowers RSS by > 30 % and the slope is > 3σ_slope. OCCT: `BRepFilletAPI_MakeFillet::Add(r1, r2, edge)` or `SetRadius` with (parameter, radius) pairs.
6. **Scanner rounding.** Scanners and meshing round sharp edges to a pseudo-radius of about 0.1–0.3 mm. Declare an edge _sharp_ if r < r_min = max(0.3 mm, 4e, 6σ) or if the arc spans fewer than about 4 sample rows. Do not offer such fillets. Fillets just above r_min should be reported with their σ_r.
7. **Chamfer.** A narrow planar region R between A and B with: n_R in the plane of n_A and n_B (|n_R·(n_A×n_B)|/|n_A×n_B| < sin 3°), both angles to the primaries ≥ 10°, long boundaries ∥ A∩B, aspect ratio < 0.3. Parameters: distances d₁ and d₂ from the virtual sharp edge to R∩A and R∩B. Snap to equal distance when |d₁ − d₂| < 2σ_d. OCCT `BRepFilletAPI_MakeChamfer` (`Add(d, edge)`, `AddDD`, `AddDA`).

Pitfalls: small fillets on thin walls fully consume a face (OCCT fails), tangent-chain fillets must be added in one operation, and convex/concave fillets meeting at a vertex need the same operation to get the correct vertex blend. Fit primaries _without_ the blend points (exclude a band of width t + 2e), otherwise the primaries bend toward the fillet.

---

## 3. Feature recognition and feature-tree inference

**Classical B-Rep feature recognition.** Joshi & Chang 1988: the attributed adjacency graph has faces as nodes and edges labelled convex (1) or concave (0). Delete faces whose edges are all convex (stock faces). The connected components that remain are feature candidates, matched against templates (pocket, slot, step, hole, boss). Sunil & Pande 2010 add hybrid graph+rule handling of interacting features, and Sunil & Pande 2008 apply it to STL sheet-metal parts after region segmentation, which is exactly your setting.

**Learned feature trees.** Point2Cyl (CVPR 2022, **MIT**) predicts extrusion instances and base/barrel labels. Its _solver_ needs no learning: axis e = argmin Σ_barrel (nᵢ·e)² + Σ_base |nᵢ×e|² (a 3×3 eigenproblem), sketch = barrel points projected ⟂ e, extent = range of base points along e. ExtrudeNet (ECCV 2022), SECAD-Net (CVPR 2023) and CSG-Stump (ICCV 2021) are all MIT and unsupervised, with roughly 1 % bbox accuracy. InverseCSG (2018, no licence) goes RANSAC → half-spaces → in/out samples → SAT program synthesis, taking minutes to hours. CAD-Recode (ICCV 2025, **CC BY-NC**) has an LLM emit CadQuery code. Point2Primitive (2025) and ComplexGen (2022, MIT) predict sketch curves or B-Rep complexes directly. None is metrology-grade or copes with fillets, drafts and domes. Reusable ideas: Point2Cyl's solver and InverseCSG's half-space labelling. Buonamici et al. 2018 refine a feature-tree template against the mesh by PSO, which is a model for the final "fit the inferred tree" step.

**AAG on segmented scans (R1–R8)**

1. **Region adjacency graph.** Nodes are regions with fitted primitives. Edges are shared boundaries: sample boundary points q and the boundary length. Blend and chamfer regions (§2) are collapsed into a _virtual sharp edge_ A–B carrying {type, r or d₁/d₂}. Vertex blends collapse into a virtual vertex.
2. **Convexity per edge.** At boundary sample q take points a ∈ A and b ∈ B at distance δ = 2–5 mm from q along the surfaces. The edge is concave if (b − q)·n_A > +3σ, convex if < −3σ, and _tangent_ if the normals at q differ by < 3° (smooth continuation, no edge). Use the majority over samples. A mixed label means an edge that changes convexity, so split it.
3. **Inner vs. outer cylinder/cone.** sgn((p − proj_axis(p))·n): negative means internal (hole/pocket wall), positive means external (boss/shaft).
4. **Direction candidates.** Plane normals and cylinder axes clustered on the Gauss sphere after intent snapping (§5). For each direction d, the _walls_ are regions slippable along d (planes with n ⟂ d, cylinders with axis ∥ d, general extrusions by slippage) and the _caps_ are planes with n ∥ d.
5. **Feature rules.**
   - _Through hole:_ internal cylinder (or wall chain) along d, both rims convex.
   - _Blind hole:_ plus a floor (plane ⟂ d, or a cone with 118° full angle) joined by a concave edge.
   - _Counterbore/countersink:_ coaxial stacked holes or cones.
   - _Boss/button:_ external wall loop along d, top cap with convex rim, base cap with concave rim. Height = distance between the caps.
   - _Pocket:_ internal wall loop, concave floor, convex rim to the stock face.
   - _Rib:_ a boss with two parallel walls at distance t ≪ length.
   - _Step:_ a wall + floor joined by a concave edge, open at both ends.
   - _Revolve:_ a region set sharing one axis (Mizoguchi conditions or slippage rotation). Profile = (r, z) of the boundaries.
6. **Sketch.** Project the boundary loop between walls and base cap onto the base plane and fit it with recognition/outline.py (circle/slot/rounded rect/ring segment), else with the sketch/fit2d.py profile. The walls themselves give better edges than the noisy boundary: intersect the fitted wall surfaces with the base plane (lines and circles) and use the boundary only for trimming.
7. **Consumer specifics.** _Draft:_ walls are cones or tilted planes with a common angle α to d, so use `BRepFeat_MakeDPrism` (draft prism) or extrude + `BRepOffsetAPI_DraftAngle`. _Domed/freeform top:_ extrude past the top, then cut with a half-space of the fitted top surface (your cad/trim.py). _Shell:_ pairs of offset-parallel regions at constant distance t become `BRepOffsetAPI_MakeThickSolid`.
8. **Order.** Base body (largest extrusion or revolve, chosen by slippage of the outer region set; else a primitive body from the stock faces) → additive features → subtractive features → chamfers → fillets (largest radius first, tangent chains together). Each step is verified against the scan (signed deviation on the region's points < 3σ + tolerance). A failed feature leaves its regions to the B-Rep fallback or to freeform.

Complexity: AAG construction is O(boundary faces). Rule matching is linear in the number of regions (tens to hundreds).

---

## 4. B-Rep topology from segmented regions

**Papers.** Benkő, Martin, Várady 2001: a _sharp-edge model_ from the primaries, then blends, with >3-valent vertices and smooth edges treated explicitly. Bénière et al. 2013: mesh primitives + a topology formalism for their intersections. Point2CAD: extend, intersect pairwise, trim at corners. PolyFit (2017, **GPL**): plane arrangement + ILP face selection. Shapiro & Vossler 1993: half-space separation for boundary-to-CSG.

**Route A: explicit topology (Várady).**

1. Use the RAG with blends collapsed (§3 R1).
2. Intersect each adjacent primary pair: analytic for plane–plane, plane–cylinder or cone (line, circle, ellipse) and coaxial quadrics (`IntAna_QuadQuadGeo`), else `GeomAPI_IntSS`. Keep the branch nearest to the boundary samples. Mean distance > 3σ + r_blend means a wrong pairing.
3. Vertices: at each triple junction of regions, Newton on d_A = d_B = d_C = 0 from the junction centroid (planes: 3×3 linear solve). If the condition number is > 1e4 (near-parallel or near-tangent surfaces), the vertex is ill-posed: merge with its neighbour or enforce a constraint first.
4. A junction of 4 or more surfaces is never exactly concurrent: either constrain it (§5) or insert a short edge.
5. Trim the curves between vertices, build wires and faces (`BRepBuilderAPI_MakeFace(surface, wire)`), sew them (`BRepBuilderAPI_Sewing`, tolerance 2σ), `ShapeFix_Shape`, check `BRepCheck_Analyzer`.
6. Fillets on the virtual sharp edges (§2).
   This route is fragile with missing tiny regions and near-tangencies.

**Route B: cell arrangement (recommended fallback; OCCT does the topology).**

1. Make each primary a bounded face: its surface trimmed to the region's extent, inflated by the largest adjacent blend setback + 2 mm. Faces of planes far from the region would cut through the part, so keep them local.
2. Run `BOPAlgo_MakerVolume` (or `BRepAlgoAPI_Splitter`) on all faces + the part bounding box to get closed cells.
3. Label each cell inside or outside with the generalized winding number of the scan mesh at 3–10 interior sample points (robust to holes in the scan). Thin cells are labelled by a majority vote.
4. Optional, PolyFit-style: penalise result faces without scan support (support fraction < 0.5) and flip cells by a small graph cut.
5. Fuse the inside cells, then `ShapeUpgrade_UnifySameDomain` and `BRepCheck`.
6. Fillets and chamfers by mapping each virtual sharp edge to the result edge whose two adjacent faces carry the primaries' tags and whose midpoint is nearest.
   Cost: O(n²) face intersections. Fine for ≤ 150–200 faces (seconds).

**OCCT hints.** Snap coincident and coaxial values _before_ booleans. Fuzzy value 1e-5–1e-4 mm. Extrude bosses from slightly below the base plane, so they overlap instead of touching. `BRepPrimAPI_MakeHalfSpace` needs a finite box: intersect with one before booleans. Fillets: one `MakeFillet` per tangent-chain group. On failure, retry with r·0.98, then per-edge, then report. Check `NbFaultyContours` (your cad/fillet.py already does). Use the builder history (`Modified`/`Generated`) to keep region tags.

---

## 5. Beautification and design intent

**Papers.**

- **Benkő et al. 2002**: a simultaneous fit of several surfaces under g(θ) = 0 (parallel, perpendicular, coaxial, tangent, symmetric, equal radius) by Lagrange multipliers and Newton. Redundancy is caught by rank and sequential addition.
- **Langbein, Marshall, Martin 2004**: detect approximate regularities (Gauss-sphere orientation clusters, special angles, equal distances, symmetries). Order them by priority, reject simple inconsistencies by rules, then add them _one at a time_ and solve by quasi-Newton. A constraint that breaks solvability or tolerance is dropped.
- **GlobFit 2011**: works on RANSAC primitives in three stages: orientation (parallel, orthogonal, equal angle), placement (coplanar, coaxial), equality (radius, length). Each stage clusters parameters, picks a non-redundant subset and accepts a constrained refit only within an error bound. The code has **no licence**, so reimplement it.
- **Pauly et al. 2008** (patterns by transformation-space voting) and **Mitra et al. 2006** (partial symmetry).
- CGAL Shape_regularization is **GPL**.

**Algorithm (D1–D7)**, extending fitting/intent.py from per-primitive to global:

1. **Directions.** Mean-shift on the Gauss sphere (±d identified), bandwidth max(1°, 3σ_dir). Then snap clusters to the part axes (present). Among cluster representatives, test orthogonal, parallel and special angles (30/45/60°) within 3σ_dir.
2. **Placement.** Within a parallel class: coplanar planes (equal offset within 3σ_off), coaxial cylinders, cones and tori (axis distance < 3σ_axis), concentric circles in sketches, and symmetric pairs: two planes with opposite normals give a mid-plane, and the mid-planes are clustered.
3. **Equality.** Cluster radii, fillet radii, hole sizes and boss heights. Two values are equal if |a − b| < 3·√(σ_a² + σ_b²). The covariances come from fitting/constrained.py.
4. **Patterns.** Among equal features: linear (centres collinear, spacing CV < 2 %), circular (centres on a circle ⟂ the common axis, angles ≈ k·360°/n), grid (two spacing vectors from a pairwise difference histogram). Mirror: candidate planes from pairs of congruent features, verified by reflecting the scan (one-sided distance < 2σ on > 90 % of points).
5. **Round values** inside the uncertainty window: integer mm > 0.5 > 0.1, standard drills, threads and clearances (M3: 2.5 tap, 3.2/3.4 clearance), angles in 0.5°/1° steps (present).
6. **Consistent subset (Langbein + GlobFit).** Order candidates by stage (orientation → placement → equality → values) and inside a stage by normalised deviation |Δ|/σ. Before solving, apply rules that skip redundant ones: parallelism is transitive, so one direction parameter per class; orthogonality only between class representatives along a spanning tree. Add one at a time, refit simultaneously, and keep it if total RMS ≤ 1.05× the unconstrained RMS and no region exceeds its tolerance.
7. **Parametrise** instead of adding Lagrange constraints where possible: a parallel class shares one direction, a coaxial set shares an axis, equal radii share one parameter. The system stays small and well-conditioned. Use scipy `least_squares` with soft-L1 loss on point residuals. Use penalties only for constraints that cannot be parametrised (tangency, symmetry).

Pitfalls: snapping order matters (directions first, else offsets snap to tilted frames). Over-eager equal-radius merges for 0.1 mm-different holes: require the covariance test _and_ a user-visible list. Re-run blend fits after primaries move.

---

## 6. 2D profiles, slots, ring segments

**Papers.** Rosin & West 1995 (IEEE PAMI 17): recursive splitting of curves into lines and arcs, picking the representation by significance (length/error). The modern equivalent is your fit2d.py (DP with BIC over prefix moments). Line/circle Hough in 2D: Le & Duan 2017.

**Algorithm (P1–P6).**

1. **Profile source.** Prefer _wall surfaces ∩ sketch plane_ (exact lines and circles from 3D fits). Fall back to a planar section of the mesh, or the boundary loop resampled at step 2e.
2. **Segment** lines and arcs by DP + BIC (present), tolerance 3σ.
3. **Joints.** Tangent (G1) if the direction change is < 3–5°, else a corner. Short arcs between two lines with tangent joints are _sketch fillets_: re-parametrise them as (line₁, line₂, r).
4. **Constrained refit** of the whole loop with shared endpoints, tangency, horizontal/vertical to the sketch frame, equal radii, concentric arcs, and symmetry about the profile's principal axis (accepted with the §5 RMS rule).
5. **Named shapes** (recognition/outline.py), as nested models with an F-test or BIC rather than fixed factors:
   - _Circle_ (3 parameters).
   - _Slot_: two semicircles of radius w/2 joined by two parallel tangent lines. Test: two arcs, sweep 180° ± 5°, equal radius, lines parallel.
   - _Rounded rectangle_: 4 lines, pairwise ∥ and ⟂, 4 equal corner arcs.
   - _Ring segment_: two concentric arcs (r_in, r_out) + two _radial_ lines whose extensions pass within 2σ of the arc centre. Corner radius 0 to (r_out − r_in)/2. The upper bound is a _curved slot_.
   - _Polygon / regular polygon_: equal sides and angles.
     Free profiles stay line+arc chains.
6. **Snap** the dimensions with §5. Express the sketch with constraints (equal, tangent, concentric) so it is editable.

Pitfalls: boundary loops of bosses include the fillet foot, so take the loop _at the virtual sharp edge_ (wall ∩ base), not the region border. Small radii (< 4e) are indistinguishable from corners, so declare them sharp.

---

## 7. Code and licences

| Item                                                                              | Licence                                              | Use                                       |
| --------------------------------------------------------------------------------- | ---------------------------------------------------- | ----------------------------------------- |
| OCCT / OCP                                                                        | LGPL-2.1 + exception                                 | yes (in use)                              |
| numpy, scipy, scikit-learn (mean-shift, DBSCAN), trimesh                          | BSD / MIT                                            | yes                                       |
| pyRANSAC-3D                                                                       | Apache-2.0                                           | proposals only (simple)                   |
| Open3D                                                                            | MIT                                                  | plane RANSAC, normals                     |
| Geometric Tools (GTE: ApprCylinder3, ApprCone3, ApprTorus3)                       | Boost                                                | reference fitters                         |
| Point2Cyl, ExtrudeNet, SECAD-Net, CSG-Stump, ComplexGen, UV-Net                   | MIT                                                  | ideas, solver code                        |
| Point2CAD                                                                         | LICENSE Apache-2.0 vs README CC BY-NC: **ambiguous** | ideas only                                |
| Schnabel PrimitiveShapes                                                          | "research purposes only"                             | no                                        |
| CGAL (Shape detection, regularization), PolyFit, KSR, EfPiSoft, MeshLab/pymeshlab | **GPL**                                              | no (only via a separate process, if ever) |
| GlobFit, ParSeNet, HPNet, SED-Net, InverseCSG                                     | no licence                                           | no                                        |
| CAD-Recode                                                                        | **CC BY-NC 4.0**                                     | no                                        |

---

## 8. Recommended end-to-end pipeline

| #   | Step                                                                                                                                                            | Builds on                         | New work | Runtime (1–2 M faces, reduced copy) |
| --- | --------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------- | -------- | ----------------------------------- |
| 0   | Repair, jet normals, crease zones, alignment                                                                                                                    | present                           | –        | seconds                             |
| 1   | Segmentation S1–S7 + κ₀ noise floor + blend-candidate strips                                                                                                    | segmentation/auto.py              | 2–3 d    | 5–20 s                              |
| 2   | **Region adjacency graph** with convex / concave / tangent labels, inner/outer cylinders                                                                        | –                                 | 2–3 d    | < 1 s                               |
| 3   | **Fillet/chamfer recognition** F1–F7 (radius by offset-spine Brent fit, scanner rounding threshold, chamfer rules), collapse into virtual sharp edges           | step 2                            | 4–6 d    | < 1 s per blend                     |
| 4   | **Global design intent** D1–D7 (directions → placement → equality → patterns → values), simultaneous parametrised refit                                         | fitting/intent.py, constrained.py | 6–8 d    | 1–5 s                               |
| 5   | **Feature recognition** R4–R8: base extrude/revolve by slippage, holes/bosses/pockets/ribs/buttons; outlines by outline.py/fit2d.py; drafts, domed tops, shells | outline.py, sketch                | 6–10 d   | < 1 s                               |
| 6   | **Build the feature tree** in the existing document (sketch, extrude/revolve, combine, fillet), verifying each feature against the scan                         | features/_, cad/_                 | 4–6 d    | OCCT seconds                        |
| 7   | **Fallback B-Rep** Route B (MakerVolume cells + winding-number labels) for region sets not explained by features                                                | cad/booleans.py                   | 6–10 d   | 2–30 s                              |
| 8   | Freeform patches for residual regions (quad net), stitched by trim/sew                                                                                          | freeform-net                      | 3–5 d    | –                                   |
| 9   | Deviation report per feature/face; user accepts or rejects suggestions                                                                                          | inspection                        | 2 d      | –                                   |

**Build first:** 2 → 3 → 5 (holes/bosses/pockets on aligned prismatic parts) → 6. That gives an editable tree for the bulk of engineered parts within about 3–4 weeks. Then 4 (intent quality), 7 (robustness), and the consumer-part extras (drafts, domes, shells, patterns). Do not build learned segmentation; revisit only if a permissively licensed model trained on real scans appears.

**Main risks:** (a) small fillets near the noise floor, so be explicit with r_min; (b) near-tangent primaries, which make vertices and convexity ill-posed, so use tangent labels and constrain before intersecting; (c) OCCT fillet failures on thin faces, so use the retry ladder; (d) wrong blend/primary split on consumer parts, so keep the user in the loop with the region graph visible.

---

## References

1. T. Várady, R.R. Martin, J. Cox, _Reverse engineering of geometric models – an introduction_, CAD 29(4):255–268, 1997. doi:10.1016/S0010-4485(96)00054-1
2. P. Benkő, T. Várady, _Direct segmentation of smooth, multiple point regions_, GMP 2002, 169–178. doi:10.1109/GMAP.2002.1027508
3. P. Benkő, T. Várady, _Segmentation methods for smooth point regions of conventional engineering objects_, CAD 36(6):511–523, 2004. doi:10.1016/S0010-4485(03)00159-3
4. P. Benkő, T. Várady, _Best fit translational and rotational surfaces for reverse engineering shapes_, Math. of Surfaces IX, 2000. doi:10.1007/978-1-4471-0495-7_5
5. T. Várady, M. Facello, Z. Terék, _Automatic extraction of surface structures in digital shape reconstruction_, CAD 39(5):379–388, 2007. doi:10.1016/j.cad.2007.02.011. Patent US8004517B1: https://patents.google.com/patent/US8004517B1
6. R. Schnabel, R. Wahl, R. Klein, _Efficient RANSAC for point-cloud shape detection_, CGF 26(2):214–226, 2007. doi:10.1111/j.1467-8659.2007.01016.x
7. M. Attene, B. Falcidieno, M. Spagnuolo, _Hierarchical mesh segmentation based on fitting primitives_, Visual Computer 22(3):181–193, 2006. doi:10.1007/s00371-006-0375-x. Code: https://efpisoft.sourceforge.net (GPL)
8. G. Lavoué, F. Dupont, A. Baskurt, _A new CAD mesh segmentation method, based on curvature tensor analysis_, CAD 37(10):975–987, 2005. doi:10.1016/j.cad.2004.09.001
9. T. Mizoguchi, H. Date, S. Kanai, T. Kishinami, _Segmentation of scanned mesh into analytic surfaces based on robust curvature estimation and region growing_, GMP 2006, LNCS 4077:644–654. doi:10.1007/11802914_52
10. T. Le, Y. Duan, _A primitive-based 3D segmentation algorithm for mechanical CAD models_, CAGD 52–53:231–246, 2017. doi:10.1016/j.cagd.2017.02.009
11. D.-M. Yan, W. Wang, Y. Liu, Z. Yang, _Variational mesh segmentation via quadric surface fitting_, CAD 44(11):1072–1082, 2012. doi:10.1016/j.cad.2012.04.005
12. D. Cohen-Steiner, P. Alliez, M. Desbrun, _Variational shape approximation_, SIGGRAPH 2004. doi:10.1145/1015706.1015817; J. Wu, L. Kobbelt, _Structure recovery via hybrid variational surface approximation_, CGF 24(3), 2005. doi:10.1111/j.1467-8659.2005.00852.x
13. N. Gelfand, L. Guibas, _Shape segmentation using local slippage analysis_, SGP 2004. doi:10.1145/1057432.1057461
14. H. Pottmann, T. Randrup, _Rotational and helical surface approximation for reverse engineering_, Computing 60:307–322, 1998. doi:10.1007/BF02684378; H. Pottmann et al., _Line geometry for 3D shape understanding and reconstruction_, ECCV 2004. doi:10.1007/978-3-540-24670-1_23
15. Y. Li, X. Wu, Y. Chrysathou, A. Sharf, D. Cohen-Or, N. Mitra, _GlobFit: consistently fitting primitives by discovering global relations_, ACM TOG 30(4), 2011. doi:10.1145/2010324.1964947. Code: https://github.com/yangyanli/globfit (no licence)
16. G. Sharma et al., _ParSeNet_, ECCV 2020. arXiv:2003.12181
17. S. Yan et al., _HPNet: deep primitive segmentation using hybrid representations_, ICCV 2021. arXiv:2105.10620
18. Y. Li et al., _Surface and edge detection for primitive fitting of point clouds (SED-Net)_, SIGGRAPH 2023. doi:10.1145/3588432.3591522
19. Y. Liu, A. Obukhov, J.D. Wegner, K. Schindler, _Point2CAD: reverse engineering CAD models from 3D point clouds_, CVPR 2024. arXiv:2312.04962. https://github.com/prs-eth/point2cad
20. G. Kós, R.R. Martin, T. Várady, _Methods to recover constant radius rolling ball blends in reverse engineering_, CAGD 17(2):127–160, 2000. doi:10.1016/S0167-8396(99)00043-6; G. Kós, _Recovering variable radius rolling ball blends in reverse engineering_, Int. J. Manuf. Sci. Prod. 3(2–4):151–158, 2001
21. Dassault Systèmes, _Fillet detection method_, EP4345673A1 (filed 2022)
22. J.G. Lambourne et al., _Reconstructing editable prismatic CAD from rounded voxel models_, SIGGRAPH Asia 2022. doi:10.1145/3550469.3555424
23. S. Joshi, T.C. Chang, _Graph-based heuristics for recognition of machined features from a 3D solid model_, CAD 20(2):58–66, 1988. doi:10.1016/0010-4485(88)90050-4
24. B. Sunil, S.S. Pande, _Automatic recognition of features from freeform surface CAD models_, CAD 40(4), 2008; _An approach to recognize interacting features from B-Rep CAD models of prismatic machined parts using a hybrid (graph and rule based) technique_, Computers in Industry 61, 2010
25. M.A. Uy et al., _Point2Cyl_, CVPR 2022. arXiv:2112.09329 (MIT)
26. D. Ren et al., _ExtrudeNet_, ECCV 2022. arXiv:2209.15632 (MIT); P. Li et al., _SECAD-Net_, CVPR 2023. arXiv:2303.10613 (MIT); D. Ren et al., _CSG-Stump_, ICCV 2021. arXiv:2108.11305 (MIT)
27. T. Du et al., _InverseCSG: automatic conversion of 3D models to CSG trees_, ACM TOG 37(6), 2018. doi:10.1145/3272127.3275006
28. D. Rukhovich et al., _CAD-Recode_, ICCV 2025. arXiv:2412.14042 (CC BY-NC); _Point2Primitive_, 2025. arXiv:2505.02043; H. Guo et al., _ComplexGen_, SIGGRAPH 2022. arXiv:2205.14573 (MIT)
29. F. Buonamici et al., _Reverse engineering of mechanical parts: a template-based approach_, JCDE 5(2):145–159, 2018. doi:10.1016/j.jcde.2017.11.009
30. P. Benkő, R.R. Martin, T. Várady, _Algorithms for reverse engineering boundary representation models_, CAD 33(11):839–851, 2001. doi:10.1016/S0010-4485(01)00100-2
31. R. Bénière, G. Subsol, G. Gesquière, F. Le Breton, W. Puech, _A comprehensive process of reverse engineering from 3D meshes to CAD models_, CAD 45(11):1382–1393, 2013. doi:10.1016/j.cad.2013.06.004
32. L. Nan, P. Wonka, _PolyFit_, ICCV 2017. doi:10.1109/ICCV.2017.258 (GPL)
33. V. Shapiro, D. Vossler, _Separation for boundary to CSG conversion_, ACM TOG 12(1):35–55, 1993. doi:10.1145/169728.169723
34. P. Benkő, G. Kós, T. Várady, L. Andor, R.R. Martin, _Constrained fitting in reverse engineering_, CAGD 19(3):173–205, 2002. doi:10.1016/S0167-8396(01)00085-1
35. F.C. Langbein, A.D. Marshall, R.R. Martin, _Choosing consistent constraints for beautification of reverse engineered geometric models_, CAD 36(3):261–278, 2004. doi:10.1016/S0010-4485(03)00108-8
36. M. Pauly et al., _Discovering structural regularity in 3D geometry_, SIGGRAPH 2008. doi:10.1145/1360612.1360642; N. Mitra, L. Guibas, M. Pauly, _Partial and approximate symmetry detection for 3D geometry_, SIGGRAPH 2006. doi:10.1145/1141911.1141924
37. S. Oesau, Y. Verdie, C. Jamin, P. Alliez, F. Lafarge, L. Guibas, _Planar shape detection and regularization in tandem_, CGF 35(1):203–215, 2016. doi:10.1111/cgf.12720 (CGAL, GPL)
38. P.L. Rosin, G.A.W. West, _Nonparametric segmentation of curves into various representations_, IEEE PAMI 17(12):1140–1153, 1995. doi:10.1109/34.476507
