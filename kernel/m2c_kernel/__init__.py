"""Mesh-to-CAD geometry kernel.

The kernel runs as a separate process next to the Electron application and owns
all geometry: the scan, the document with its feature history, and every
computation on them. It talks to the application through the framed protocol in
`m2c_kernel.protocol`.
"""

__version__ = "0.1.0"
