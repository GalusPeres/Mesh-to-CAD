"""Automatic freeform surfacing: a scan becomes a network of B-spline patches.

Pipeline (`api.auto_surface`): a coarse triangle cage of the scan, one Catmull-Clark
step to an all-quad control cage, an iterative least-squares fit of the cage's limit
surface to the scan, one bicubic B-spline patch per cage quad, and a B-Rep shell
built directly from the quad topology (a solid when the cage is closed).
"""
