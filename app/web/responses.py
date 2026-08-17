import json
from typing import Any

from fastapi.responses import JSONResponse


class SafeJSONResponse(JSONResponse):
    def render(self, content: Any) -> bytes:
        rendered = json.dumps(
            content,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        )
        return (
            rendered.replace("&", "\\u0026")
            .replace("<", "\\u003c")
            .replace(">", "\\u003e")
            .encode("utf-8")
        )
