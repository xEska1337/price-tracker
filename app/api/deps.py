from app.state import Runtime, runtime


async def get_runtime() -> Runtime:
    return runtime
