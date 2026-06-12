import asyncio
from datetime import datetime, timezone
from mcp.client.streamable_http import streamablehttp_client
from mcp import ClientSession
from src.config import MCP_SERVER_URL, MCP_SECRET_TOKEN


async def _call_write_tool(
    reservation_id: str,
    name: str,
    surname: str,
    car_number: str,
    start_datetime: str,
    end_datetime: str,
    space_type: str,
    approval_time: str,
) -> str:
    url = f"{MCP_SERVER_URL}/mcp"
    async with streamablehttp_client(url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "write_confirmed_reservation",
                {
                    "token": MCP_SECRET_TOKEN,
                    "reservation_id": reservation_id,
                    "name": name,
                    "surname": surname,
                    "car_number": car_number,
                    "start_datetime": start_datetime,
                    "end_datetime": end_datetime,
                    "approval_time": approval_time,
                    "space_type": space_type,
                },
            )
            if result.content:
                return result.content[0].text
            return "OK"


def call_mcp_write(
    reservation_id: str,
    name: str,
    surname: str,
    car_number: str,
    start_datetime: str,
    end_datetime: str,
    space_type: str,
    approval_time: str | None = None,
) -> str:
    """Synchronous wrapper — safe to call from FastAPI or any sync context."""
    if approval_time is None:
        approval_time = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    try:
        return asyncio.run(
            _call_write_tool(
                reservation_id=reservation_id,
                name=name,
                surname=surname,
                car_number=car_number,
                start_datetime=start_datetime,
                end_datetime=end_datetime,
                space_type=space_type,
                approval_time=approval_time,
            )
        )
    except Exception as e:
        print(f"[MCPClient] Failed to call MCP server: {e}")
        return f"ERROR: {e}"
