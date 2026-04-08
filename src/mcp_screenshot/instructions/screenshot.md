Capture a screenshot of the screen or a specific region.

Use this tool to see what's currently displayed on screen. Ideal for verifying
visual output, reading UI elements, checking rendered content, or getting
coordinates for a follow-up targeted capture.

Args:
    region: Optional [x, y, width, height] in pixels to capture a specific area.
        Omit to capture the entire screen/monitor. Origin (0,0) is top-left.
    monitor: Monitor index. 0 = all monitors combined (default), 1 = primary,
        2 = secondary, etc.
    output: How to return the capture.
        "base64" (default) — returns the image directly for visual analysis.
        "file" — saves as PNG to file_path.
        "clipboard" — copies the image to the system clipboard.
    file_path: Required when output="file". Path where the PNG will be saved.
    auto_crop: If true, trims uniform-color borders from the captured image.

Returns:
    For output="base64": the screenshot image for direct visual analysis.
    For output="file": confirmation message with the saved file path.
    For output="clipboard": confirmation that the image was copied.

Platform notes:
    - macOS: Requires Screen Recording permission in System Settings.
    - Linux: Requires a running display server (X11 or XWayland).
    - Windows: Works out of the box.