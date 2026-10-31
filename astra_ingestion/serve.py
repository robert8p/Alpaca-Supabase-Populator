"""Run the production ASGI service without starting ingestion workers."""


def main():
    from .config import Settings

    settings = Settings.from_env()
    try:
        import uvicorn
    except ImportError as exc:
        raise RuntimeError("Install the pinned ingestion ASGI runtime dependencies") from exc
    uvicorn.run(
        "astra_ingestion.api:create_app",
        factory=True,
        host=settings.host,
        port=settings.port,
        workers=1,
        limit_concurrency=4,
        timeout_keep_alive=5,
        timeout_graceful_shutdown=15,
        proxy_headers=False,
        server_header=False,
        access_log=False,
        log_level="warning",
    )


if __name__ == "__main__":
    main()
