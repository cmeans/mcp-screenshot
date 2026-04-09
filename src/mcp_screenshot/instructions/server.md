This server captures screenshots of the user's screen for AI agent analysis.

**When to use**: Call `screenshot` when you need to see what's on screen — to verify
visual output, read UI state, check rendering, or identify screen coordinates for
targeted capture.

**Workflow**:
1. Call `screenshot()` with no arguments to capture the full screen
2. Examine the image, identify the region of interest, then call
   `screenshot(region=[x, y, width, height])` to capture just that area in detail

**Coordinate system**: Origin (0, 0) is the top-left corner of the screen.
The region parameter uses pixel coordinates: [x, y, width, height].

**Multi-monitor**: Use `monitor=0` for all monitors combined (default),
`monitor=1` for the primary monitor, `monitor=2` for the secondary, etc.

**Output modes**: `base64` returns the image directly for analysis (default).
`file` saves to disk. `clipboard` copies to the system clipboard.