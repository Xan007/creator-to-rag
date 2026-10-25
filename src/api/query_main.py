import os

import uvicorn

from config.env import getenv


def main():
    uvicorn.run(
        "src.api.public:app",
        host=getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT") or getenv("PORT", "8000")),
    )


if __name__ == "__main__":
    main()
