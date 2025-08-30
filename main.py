import os
import aiohttp
from aiohttp import web

async def fetch_image(request):
    image_url = request.rel_url.query.get('url', None)

    if not image_url or not image_url.startswith('https://image.tmdb.org/t/p/'):
        return web.Response(status=400, text="Invalid URL.")

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(image_url) as resp:
                if resp.status == 200:
                    image_data = await resp.read()
                    return web.Response(body=image_data, content_type=resp.content_type)
                else:
                    return web.Response(status=resp.status, text="Failed to fetch image.")
    except Exception as e:
        return web.Response(status=500, text=f"Error: {e}")

app = web.Application()
app.router.add_get('/', fetch_image)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    web.run_app(app, port=port)
