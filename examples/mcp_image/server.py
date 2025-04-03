import asyncio
import io
from PIL import Image as PILImage
from mcp.server.fastmcp import FastMCP, Image

app = FastMCP("image")

@app.tool()
def screenshot() -> Image:
    """Take a screenshot of the current screen

    Returns:
        Screenshot image that can be displayed in the conversation
    """
    img = PILImage.open("Screenshot.png")
    img_bytes = io.BytesIO()
    img.save(img_bytes, format="PNG")
    return Image(data=img_bytes.getvalue(), format="png")

if __name__ == "__main__":
    asyncio.run(app.run())
