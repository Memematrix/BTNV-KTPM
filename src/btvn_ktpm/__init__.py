def main() -> None:
    import uvicorn

    uvicorn.run("src.main:app", host="127.0.0.1", port=8000, proxy_headers=False, app_dir=".")
